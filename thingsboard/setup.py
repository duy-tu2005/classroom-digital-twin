#!/usr/bin/env python3
"""Idempotent deployment of the Classroom A302 Digital Twin (ThingsBoard CE)."""
import argparse
import base64
import copy
import json
import os
import sys
import time
import uuid
from pathlib import Path
from api import Client, eid, uid, env_file, provision, wait

ROOT = Path(__file__).resolve().parents[1]
CHAIN = 'Classroom A302 - Digital Twin Processing'
DEVICE = 'ESP32_Classroom_Node'
ASSET = 'Classroom_A302'
DASHBOARD = 'Classroom A302 - Digital Twin'
PEOPLE_KEYS = ['occupancy','total_entered','total_exited','ir_a_blocked','ir_b_blocked',
               'counter_state','counter_errors','counter_needs_calibration']
KEYS = ['temperature','humidity','rssi','sensor_valid','fan_state','fan_mode',*PEOPLE_KEYS,
        'light1_state','light2_state','light3_state','light4_state','health_score',
        'observed_state','online','last_seen','lights_on_count']

def log(msg): print('[classroom] ' + msg, flush=True)
def script(name): return (ROOT / 'thingsboard/rule-scripts' / name).read_text(encoding='utf-8')
def stable(label): return str(uuid.uuid5(uuid.NAMESPACE_URL, 'classroom-digital-twin://' + label))
def find(items, name): return next((x for x in items if x.get('name', x.get('title')) == name), None)
def transform(js): return {'scriptLang':'JS','jsScript':js,'tbelScript':'return {msg:msg,metadata:metadata,msgType:msgType};'}
def filter_js(js): return {'scriptLang':'JS','jsScript':js,'tbelScript':'return false;'}
def attrs_config(scope): return {'processingSettings':{'type':'ON_EVERY_MESSAGE'},'scope':scope,
    'notifyDevice':False,'sendAttributesUpdatedNotification':False,'updateAttributesOnlyOnValueChange':True}
def ts_config(): return {'defaultTTL':0,'useServerTs':False,'processingSettings':{'type':'ON_EVERY_MESSAGE'}}
def parent_config(): return {'originatorSource':'RELATED','relationsQuery':{'direction':'TO','maxLevel':1,
    'filters':[{'relationType':'Contains','entityTypes':['ASSET'],'negate':False}],'fetchLastLevelOnly':False},
    'entityType':None,'entityNamePattern':None}
def alarm_config(kind, create=False):
    cfg = {'alarmType':kind,'scriptLang':'JS','alarmDetailsBuildJs':
        "return {health_score:msg.health_score,anomaly_score:msg.anomaly_score,observed_state:msg.observed_state,details:msg.anomaly_details};",
        'alarmDetailsBuildTbel':'return {};'}
    if create: cfg.update(severity='${alarmSeverity}',dynamicSeverity=True,propagate=False,
        propagateToOwner=False,propagateToTenant=False,useMessageAlarmData=False,overwriteAlarmDetails=True,relationTypes=[])
    return cfg

def ensure_chain(client):
    chains = client.pages('/api/ruleChains', type='CORE')
    chain = find(chains, CHAIN) or find(chains, 'Classroom A101 - Digital Twin Processing')
    if not chain: chain = client.post('/api/ruleChain', {'name':CHAIN,'type':'CORE','root':False,'debugMode':False,
        'additionalInfo':{'description':'DHT22, two IR gates, bidirectional people counter, four lights and fan.'}})
    else:
        chain['name'] = CHAIN
        chain['additionalInfo'] = dict(chain.get('additionalInfo') or {},
            description='DHT22, two IR gates, bidirectional people counter, four lights and fan.')
        chain = client.post('/api/ruleChain', chain)
    classes = {'switch':'filter.TbMsgTypeSwitchNode','enrich':'metadata.TbGetAttributesNode',
        'transform':'transform.TbTransformMsgNode','filter':'filter.TbJsFilterNode','parent':'transform.TbChangeOriginatorNode',
        'timeseries':'telemetry.TbMsgTimeseriesNode','attributes':'telemetry.TbMsgAttributesNode',
        'create':'action.TbCreateAlarmNode','clear':'action.TbClearAlarmNode','rpc':'rpc.TbSendRPCRequestNode'}
    nodes, connections = [], []
    def node(kind, name, cfg, version=0, x=0, y=0):
        index = len(nodes)
        nodes.append({'type':'org.thingsboard.rule.engine.'+classes[kind],'name':name,'singletonMode':False,
            'debugSettings':None,'configurationVersion':version,'configuration':cfg,'additionalInfo':{'layoutX':x,'layoutY':y}})
        return index
    def link(src, dst, relation='Success'): connections.append({'fromIndex':src,'toIndex':dst,'type':relation})
    config_keys = ['temp_warn_low','temp_warn_high','temp_critical_high','weak_rssi_warning','weak_rssi_critical',
        'actuator_mismatch_samples','expected_fan_state','expected_fan_ts']
    for i in range(1,5): config_keys += [f'expected_light{i}_state',f'expected_light{i}_ts']
    enrich = {'fetchTo':'METADATA','clientAttributeNames':[],'sharedAttributeNames':[],
        'serverAttributeNames':config_keys,'latestTsKeyNames':['anomaly_type','observed_state','invalid_count','actuator_mismatch_count','recovery_count'],
        'tellFailureIfAbsent':False,'getLatestValueWithTs':True}
    router = node('switch','Message Type Switch',{'version':0},x=80,y=300)
    thresholds = node('enrich','Load classroom thresholds and previous state',enrich,1,320,80)
    compute = node('transform','Compute classroom health and state',transform(script('process-telemetry.js')),x=580,y=80)
    save_device = node('timeseries','Save enriched device telemetry',ts_config(),1,850,0)
    change_parent = node('parent','Originator: Classroom A302',parent_config(),x=850,y=130)
    payload = node('transform','Build classroom twin payload',transform(script('build-twin-payload.js')),x=1110,y=130)
    save_twin = node('timeseries','Save classroom twin history',ts_config(),1,1370,40)
    prep_attrs = node('transform','Prepare latest twin attributes',transform("return {msg:msg,metadata:metadata,msgType:'POST_ATTRIBUTES_REQUEST'};"),x=1370,y=140)
    save_attrs = node('attributes','Save latest classroom state',attrs_config('SERVER_SCOPE'),3,1630,140)
    changed = node('filter','Previous alarm changed?',filter_js(script('should-clear-previous-alarm.js')),x=1370,y=250)
    clear = node('clear','Clear previous classroom alarm',alarm_config('${prevAlarmType}'),x=1630,y=230)
    active = node('filter','Anomaly active?',filter_js(script('has-anomaly.js')),x=1890,y=290)
    create = node('create','Create or update classroom alarm',alarm_config('${alarmType}',True),x=2150,y=290)
    old = node('enrich','Load alarm before OFFLINE',dict(enrich,serverAttributeNames=[],latestTsKeyNames=['anomaly_type']),1,320,470)
    offline = node('transform','Build OFFLINE state',transform(script('offline-state.js')),x=580,y=470)
    client_attrs = node('attributes','Save client attributes',attrs_config('CLIENT_SCOPE'),3,320,740)
    rpc = node('rpc','Send RPC to classroom ESP32',{'timeoutInSeconds':15},x=320,y=850)
    capture_filter = node('filter','Is valid output command?',filter_js("return /^setLight[1-4]$/.test(msg.method) || msg.method === 'setFan';"),x=580,y=850)
    capture = node('transform','Capture requested output state',transform(script('capture-command.js')),x=850,y=850)
    expected = node('attributes','Save expected actuator state',attrs_config('SERVER_SCOPE'),3,1110,850)
    wake_parent = node('parent','ACTIVITY originator: classroom',parent_config(),x=320,y=610)
    wake_clear = node('clear','Clear CONNECTION_LOST',alarm_config('CONNECTION_LOST'),x=580,y=610)
    link(router,thresholds,'Post telemetry'); link(thresholds,compute); link(thresholds,compute,'Failure')
    link(compute,save_device); link(compute,change_parent); link(change_parent,payload)
    link(payload,save_twin); link(payload,prep_attrs); link(prep_attrs,save_attrs); link(payload,changed)
    link(changed,clear,'True'); link(changed,active,'False'); link(changed,active,'Failure')
    for relation in ['Cleared','False','Failure']: link(clear,active,relation)
    link(active,create,'True'); link(router,old,'Inactivity Event'); link(old,offline); link(old,offline,'Failure')
    link(offline,save_device); link(offline,change_parent)
    link(router,client_attrs,'Post attributes'); link(router,rpc,'RPC Request to Device'); link(router,capture_filter,'RPC Request to Device')
    link(capture_filter,capture,'True'); link(capture,expected)
    link(router,wake_parent,'Activity Event'); link(wake_parent,wake_clear)
    metadata = client.post('/api/ruleChain/metadata', {'ruleChainId':eid('RULE_CHAIN',uid(chain)),
        'firstNodeIndex':0,'nodes':nodes,'connections':connections,'ruleChainConnections':None})
    log(f'Rule Chain ready: {len(nodes)} nodes / {len(connections)} connections')
    return chain, metadata

def ensure_entities(client, chain):
    profiles = client.pages('/api/deviceProfiles')
    dp = find(profiles,'ESP32_Classroom_Profile')
    body = copy.deepcopy(dp) if dp else {'name':'ESP32_Classroom_Profile','type':'DEFAULT','transportType':'DEFAULT',
        'provisionType':'DISABLED','profileData':{'configuration':{'type':'DEFAULT'},'transportConfiguration':{'type':'DEFAULT'},
        'provisionConfiguration':{'type':'DISABLED','provisionDeviceSecret':None},'alarms':None}}
    body.update(defaultRuleChainId=eid('RULE_CHAIN',uid(chain)),description='DHT22 + two IR break-beam gates + 4 lights + fan output')
    dp = client.post('/api/deviceProfile',body)
    ap = find(client.pages('/api/assetProfiles'),'Classroom_Profile')
    ap = client.post('/api/assetProfile',dict(ap or {},name='Classroom_Profile',description='Classroom Digital Twin root asset'))
    assets = client.pages('/api/tenant/assets')
    asset = find(assets,ASSET) or find(assets,'Classroom_A101')
    asset = client.post('/api/asset',dict(asset or {},name=ASSET,type='Classroom_Profile',label='Classroom A302',assetProfileId=eid('ASSET_PROFILE',uid(ap))))
    device = find(client.pages('/api/tenant/devices'),DEVICE)
    device = client.post('/api/device',dict(device or {},name=DEVICE,type='ESP32_Classroom_Profile',label='ESP32 · DHT22 · hai tia IR · 4 đèn · quạt',deviceProfileId=eid('DEVICE_PROFILE',uid(dp))))
    client.post('/api/v2/relation',{'from':eid('ASSET',uid(asset)),'to':eid('DEVICE',uid(device)),'type':'Contains','typeGroup':'COMMON'})
    existing = client.get(f'/api/plugins/telemetry/DEVICE/{uid(device)}/values/attributes/SERVER_SCOPE')
    current = {x['key']:x['value'] for x in existing}
    defaults = {'inactivityTimeout':20000,'temp_warn_low':18,'temp_warn_high':28,'temp_critical_high':32,
        'weak_rssi_warning':-85,'weak_rssi_critical':-90,'actuator_mismatch_samples':3,'expected_fan_state':False,'expected_fan_ts':0}
    for i in range(1,5): defaults.update({f'expected_light{i}_state':False,f'expected_light{i}_ts':0})
    missing = {k:v for k,v in defaults.items() if k not in current}
    if missing: client.post(f'/api/plugins/telemetry/DEVICE/{uid(device)}/attributes/SERVER_SCOPE', missing)
    for kind, item in [('DEVICE',device),('ASSET',asset)]:
        latest = client.get(f'/api/plugins/telemetry/{kind}/{uid(item)}/values/timeseries',{'keys':'online'})
        if not latest:
            baseline = {'online':False,'last_seen':0,'observed_state':'INIT','health_score':0,'anomaly_score':0,'anomaly_type':'NONE',
                'fan_state':False,'fan_mode':'AUTO','lights_on_count':0,'recovery_count':0}
            baseline.update({f'light{i}_state':False for i in range(1,5)})
            client.post(f'/api/plugins/telemetry/{kind}/{uid(item)}/timeseries/ANY',baseline)
    views = {}
    for label, keys in [('Environment',['temperature','humidity','sensor_valid']),('PeopleCounter',PEOPLE_KEYS),('Fan',['fan_state','fan_mode']),
        *[(f'Light{i}',[f'light{i}_state']) for i in range(1,5)]]:
        name = 'Classroom_' + label + '_View'
        view = find(client.pages('/api/tenant/entityViews'), name)
        # Migrate our old PIR component in place: retain its ID, no duplicate view.
        if not view and label == 'PeopleCounter':
            view = find(client.pages('/api/tenant/entityViews'), 'Classroom_PIR_View')
        view = client.post('/api/entityView',dict(view or {},name=name,type='Classroom component',entityId=eid('DEVICE',uid(device)),
            startTimeMs=0,endTimeMs=0,keys={'timeseries':keys,'attributes':{'cs':[],'ss':[],'sh':[]}}))
        client.post('/api/v2/relation',{'from':eid('ASSET',uid(asset)),'to':eid('ENTITY_VIEW',uid(view)),'type':'Contains','typeGroup':'COMMON'})
        views[label] = view
    log('Device, Asset, Contains relation and 7 component views ready')
    return dp, ap, asset, device, views

def data_key(name, label=None, color='#0891b2', units=None):
    return {'name':name,'label':label or name,'type':'timeseries','color':color,'units':units,'decimals':1,
        'settings':{'type':'line','yAxisId':'default'},'aggregationType':None,'usePostProcessing':False}

def common_config(title='', show=True):
    return {'title':title,'showTitle':show,'backgroundColor':'#ffffff','color':'#183b50','titleColor':'#183b50',
        'padding':'0px','borderRadius':'16px','dropShadow':False,'enableFullscreen':True,'showLegend':False,
        'titleFont':{'size':16,'sizeUnit':'px','family':'Roboto','weight':'600','style':'normal','lineHeight':'24px'},
        'settings':{},'actions':{}}

def ensure_scene_widget(client):
    # Keep this internal FQN stable so existing dashboard links remain valid.
    fqn = 'classroom_a101_scene'
    try:
        old = client.get('/api/widgetType',{'fqn':'tenant.'+fqn})
        old = client.get('/api/widgetType/'+uid(old))
    except RuntimeError as exc:
        if 'HTTP 404' not in str(exc): raise
        old = {}
    descriptor = {'type':'latest','sizeX':24,'sizeY':16,'resources':[],
        'templateHtml':(ROOT/'thingsboard/widgets/classroom.html').read_text(encoding='utf-8').replace('__CLASSROOM_IMAGE__','data:,'),
        'templateCss':(ROOT/'thingsboard/widgets/classroom.css').read_text(encoding='utf-8'),
        'controllerScript':(ROOT/'thingsboard/widgets/classroom.js').read_text(encoding='utf-8'),
        'settingsForm':[],'dataKeySettingsForm':[],'defaultConfig':json.dumps(common_config('Classroom',False))}
    payload = dict(old,name='Classroom A302 - Interactive Twin',fqn=fqn,deprecated=False,scada=False,descriptor=descriptor,
        description='Four lighting bands, IR A/B people counter and occupancy-controlled fan',tags=['classroom','digital twin'])
    saved = client.post('/api/widgetType', payload)
    bundle = find(client.pages('/api/widgetsBundles',tenantOnly='true'),'Classroom Digital Twin')
    if not bundle: bundle = client.post('/api/widgetsBundle',{'title':'Classroom Digital Twin','alias':'classroom_digital_twin'})
    client.post('/api/widgetsBundle/'+uid(bundle)+'/widgetTypeFqns',['tenant.'+saved['fqn']])
    return saved

def ensure_dashboard(client, asset, device, scene):
    device_alias, asset_alias = stable('device-alias'), stable('asset-alias')
    aliases = {}
    for kind, item, alias in [('DEVICE',device,device_alias),('ASSET',asset,asset_alias)]:
        aliases[alias] = {'id':alias,'alias':item['name'],'filter':{'type':'singleEntity','resolveMultiple':False,'singleEntity':eid(kind,uid(item))}}
    widgets, layout = {}, {}
    def add(name, fqn, kind, config, row, col, sx, sy):
        wid = stable('widget-'+name)
        widgets[wid] = {'id':wid,'typeFullFqn':fqn,'type':kind,'sizeX':sx,'sizeY':sy,'config':config}
        layout[wid] = {'row':row,'col':col,'sizeX':sx,'sizeY':sy}
    def source(alias, keys): return {'type':'entity','name':'Classroom','entityAliasId':alias,'dataKeys':keys,'latestDataKeys':[]}
    image = 'data:image/png;base64,' + base64.b64encode((ROOT/'assets/classroom-overview-v2.png').read_bytes()).decode('ascii')
    cfg = common_config('Classroom A302',False)
    cfg['settings'] = {'deviceId':uid(device),'sceneImage':image,
        'sceneLighting':json.loads((ROOT/'thingsboard/widgets/lighting-layout.json').read_text(encoding='utf-8'))}
    cfg['datasources'] = [source(device_alias,[data_key(k) for k in KEYS])]
    add('scene','tenant.'+scene['fqn'],'latest',cfg,0,0,24,18)
    for label, title, alias, keys, col in [
        ('temperature','Nhiệt độ lớp học',device_alias,[data_key('temperature','Nhiệt độ','#d6a74e','°C')],0),
        ('network','Cường độ Wi-Fi',device_alias,[data_key('rssi','RSSI','#0891b2','dBm')],8),
        ('health','Sức khỏe Digital Twin',asset_alias,[data_key('health_score','Sức khỏe','#059669','%'),data_key('anomaly_score','Bất thường','#dc2626')],16)]:
        default = client.get('/api/widgetType',{'fqn':'system.time_series_chart'})
        cfg = json.loads(default['descriptor']['defaultConfig'])
        cfg.update(common_config(title)); cfg['settings'] = json.loads(default['descriptor']['defaultConfig']).get('settings',{})
        cfg['datasources'] = [source(alias,keys)]; cfg['useDashboardTimewindow'] = False
        # 15s x 1h = 240 buckets, below the server's timeseries interval cap.
        # An invalid chart query closes the shared WebSocket, including the scene.
        cfg['timewindow'] = {'displayValue':'','selectedTab':0,'realtime':{'realtimeType':0,'interval':15000,'timewindowMs':3600000},
            'history':{'historyType':0,'interval':15000,'timewindowMs':3600000},'aggregation':{'type':'AVG','limit':240}}
        cfg['showLegend'] = True
        add(label,'system.'+default['fqn'],default['descriptor']['type'],cfg,18,col,8,7)
    default = client.get('/api/widgetType',{'fqn':'system.time_series_chart'})
    cfg = json.loads(default['descriptor']['defaultConfig'])
    chart_settings = cfg.get('settings',{})
    cfg.update(common_config('Số người trong phòng · lịch sử đếm hai tia A/B'))
    cfg['settings'] = chart_settings
    cfg['datasources'] = [source(device_alias,[data_key('occupancy','Số người','#0891b2','người')])]
    cfg['useDashboardTimewindow'] = True
    add('occupancy','system.'+default['fqn'],default['descriptor']['type'],cfg,25,0,24,6)
    alarm = client.get('/api/widgetType',{'fqn':'system.alarm_widgets.alarms_table'})
    cfg = json.loads(alarm['descriptor']['defaultConfig']); saved_settings=cfg.get('settings',{});cfg.update(common_config('Cảnh báo Digital Twin lớp học'))
    cfg['settings'] = dict(saved_settings,displayDetails=True,displayActivity=True,displayPagination=True,defaultPageSize=10,
        allowAcknowledgment=True,allowClear=True,allowAssign=False,enableSearch=True,enableFilter=True)
    cfg['alarmSource']['entityAliasId']=asset_alias;cfg['alarmSource']['name']='Classroom A302';cfg['alarmSearchStatus']='ANY'
    add('alarms','system.'+alarm['fqn'],alarm['descriptor']['type'],cfg,31,0,24,8)
    configuration = {'widgets':widgets,'entityAliases':aliases,'filters':{},
        'states':{'default':{'name':'Digital Twin lớp học A302','root':True,'layouts':{'main':{'widgets':layout,'gridSettings':{
            'columns':24,'backgroundColor':'#edf2f6','color':'#183b50','margin':12,'outerMargin':True,'layoutType':'default',
            'autoFillHeight':False,'mobileAutoFillHeight':False,'mobileRowHeight':70}}}}},
        'timewindow':{'selectedTab':0,'realtime':{'realtimeType':0,'interval':15000,'timewindowMs':3600000},'aggregation':{'type':'AVG','limit':240}},
        'settings':{'stateControllerId':'entity','showTitle':True,'showDashboardTimewindow':True,'showDashboardExport':True,
            'showDashboardsSelect':True,'toolbarAlwaysOpen':True,'titleColor':'#183b50','showDashboardLogo':False,'dashboardCss':'.tb-dashboard {background:#edf2f6;}'} }
    dashboards = client.pages('/api/tenant/dashboards')
    old = find(dashboards,DASHBOARD) or find(dashboards,'Classroom A101 - Digital Twin')
    dashboard = client.post('/api/dashboard',dict(old or {},title=DASHBOARD,configuration=configuration,mobileHide=False))
    log('Dashboard ready: 4 light bands, IR A/B counter, occupancy fan, DHT22, charts and alarms')
    return dashboard

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url'); parser.add_argument('--mqtt-host');parser.add_argument('--runtime-dir')
    parser.add_argument('--export-dir');parser.add_argument('--wait-seconds',type=int,default=300)
    args=parser.parse_args()
    conf=dict(env_file(ROOT/'.env.local'),**env_file(ROOT/'deployment/.env'),**os.environ)
    url=args.base_url or conf.get('TB_BASE_URL','http://127.0.0.1:8080')
    mqtt_host=args.mqtt_host or conf.get('TB_MQTT_HOST','host.wokwi.internal')
    runtime=Path(args.runtime_dir or conf.get('TB_RUNTIME_DIR',ROOT))
    export=Path(args.export_dir or conf.get('TB_EXPORT_DIR',ROOT/'thingsboard/exports'))
    log('Waiting for '+url);wait(url,args.wait_seconds)
    if conf.get('TB_PROVISION_TENANT','false').lower()=='true':
        provision(url,conf['TB_USERNAME'],conf['TB_PASSWORD'],conf.get('TB_SYSADMIN_USERNAME','sysadmin@thingsboard.org'),
            conf['TB_SYSADMIN_PASSWORD'],conf.get('TB_TENANT_TITLE','Classroom Digital Twin'),conf.get('TB_SYSADMIN_INITIAL_PASSWORD'))
    client=Client(url,conf.get('TB_USERNAME'),conf.get('TB_PASSWORD'),conf.get('TB_API_KEY'))
    if client.get('/api/auth/user')['authority'] != 'TENANT_ADMIN': raise RuntimeError('TENANT_ADMIN is required')
    chain,metadata=ensure_chain(client)
    dp,ap,asset,device,views=ensure_entities(client,chain)
    scene=ensure_scene_widget(client)
    dashboard=ensure_dashboard(client,asset,device,scene)
    token=client.get('/api/device/'+uid(device)+'/credentials')['credentialsId']
    runtime.mkdir(parents=True,exist_ok=True);(runtime/'firmware').mkdir(exist_ok=True)
    secret='#pragma once\n#include <Arduino.h>\n'
    for k,v in {'WIFI_SSID':'Wokwi-GUEST','WIFI_PASSWORD':'','TB_MQTT_HOST':mqtt_host,'TB_DEVICE_TOKEN':token}.items(): secret+=f'constexpr char {k}[] = {json.dumps(v)};\n'
    secret+='constexpr uint16_t TB_MQTT_PORT = 1883;\n'
    (runtime/'firmware/secrets.h').write_text(secret,encoding='utf-8',newline='\n')
    base=conf.get('TB_PUBLIC_BASE_URL',url)
    env={'TB_BASE_URL':base,'TB_MQTT_HOST':mqtt_host,'TB_DEVICE_TOKEN':token,'TB_DEVICE_ID':uid(device),'TB_ASSET_ID':uid(asset),
        'TB_DASHBOARD_ID':uid(dashboard),'TB_RULE_CHAIN_ID':uid(chain)}
    (runtime/'.env.local').write_text(''.join(f'{k}={v}\n' for k,v in env.items()),encoding='utf-8',newline='\n')
    for p in [runtime/'.env.local',runtime/'firmware/secrets.h']: p.chmod(0o600)
    export.mkdir(parents=True,exist_ok=True)
    retired = export / 'entity-view-pir.json'
    if retired.exists():
        history = export / 'legacy'; history.mkdir(exist_ok=True)
        retired.rename(history / ('entity-view-pir-'+str(time.time_ns())+'.json'))
    artifacts={'rule-chain':chain,'rule-chain-metadata':metadata,'device':device,'asset':asset,'device-profile':dp,'asset-profile':ap,
        'dashboard':dashboard,'widget-classroom':scene,**{'entity-view-'+k.lower():v for k,v in views.items()}}
    artifacts['manifest']={'project':'Classroom Digital Twin','generatedAt':int(time.time()*1000),'containsSecrets':False,
        'dashboardUrl':base+'/dashboards/'+uid(dashboard),'entities':{k:uid(v) for k,v in [('device',device),('asset',asset),('dashboard',dashboard),('ruleChain',chain)]}}
    for name,data in artifacts.items(): (export/(name+'.json')).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    log('Runtime secrets saved; token not printed.')
    log('Dashboard: '+base+'/dashboards/'+uid(dashboard))
    return 0

if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'): sys.stdout.reconfigure(encoding='utf-8')
    try: raise SystemExit(main())
    except Exception as exc: print('[classroom] ERROR: '+str(exc),file=sys.stderr);raise SystemExit(1)
