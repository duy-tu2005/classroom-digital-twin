"""End-to-end AWS widget/MQTT/rule/Alarm test on temporary QA entities.

This deliberately uses a simulated MQTT client, not the production Wokwi token.
All QA entities are removed at the end; production device state is unchanged.
"""
import base64
import copy
import hashlib
import json
import sys
import threading
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/.runtime'));sys.path.insert(0,str(ROOT/'thingsboard'));sys.path.insert(0,str(ROOT/'tools'))
import paho.mqtt.client as mqtt
from playwright.sync_api import sync_playwright
from api import Client,env_file,eid,uid
from lighting_qa import mask_coverage

cfg=env_file(ROOT/'deployment/.env');rt=env_file(ROOT/'.env.local')
auth=Client(rt['TB_BASE_URL']).post('/api/auth/login',{'username':cfg['TB_USERNAME'],'password':cfg['TB_PASSWORD']})
c=Client(rt['TB_BASE_URL'],api_key=None);c.auth='Bearer '+auth['token']
stamp=str(int(time.time()))
created=[];results=[];stop=threading.Event();connected=threading.Event()
state={'temperature':26,'humidity':60,'sensor_valid':True,'rssi':-60,
    'occupancy':0,'total_entered':0,'total_exited':0,'ir_a_blocked':False,'ir_b_blocked':False,
    'counter_state':'IDLE','counter_errors':0,'counter_needs_calibration':False,
    'fan_state':False,'fan_mode':'AUTO','light1_state':False,'light2_state':False,'light3_state':False,'light4_state':False}
lock=threading.RLock();counter=[0];broker=None
def save(kind,payload):
    item=c.post('/api/'+kind,payload);created.append((kind,uid(item)));return item
def latest(kind,identity,keys):
    d=c.get(f'/api/plugins/telemetry/{kind}/{identity}/values/timeseries',{'keys':','.join(keys)})
    return {k:v[-1]['value'] for k,v in d.items() if v}
def poll(check,seconds=15):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if check():return
        time.sleep(.5)
    raise AssertionError('AWS feedback did not reach the expected state')
def truth(v):return str(v).lower() in ('true','1')
try:
    prod_device=c.get('/api/device/'+rt['TB_DEVICE_ID'])
    prod_asset=c.get('/api/asset/'+rt['TB_ASSET_ID'])
    dev=save('device',{'name':'QA_Classroom_Node_'+stamp,'type':'ESP32_Classroom_Profile','deviceProfileId':prod_device['deviceProfileId']})
    asset=save('asset',{'name':'QA_Classroom_Asset_'+stamp,'type':'Classroom_Profile','assetProfileId':prod_asset['assetProfileId']})
    device_id,asset_id=uid(dev),uid(asset)
    c.post('/api/plugins/telemetry/DEVICE/'+device_id+'/attributes/SERVER_SCOPE',{'inactivityTimeout':20000})
    c.post('/api/v2/relation',{'from':eid('ASSET',asset_id),'to':eid('DEVICE',device_id),'type':'Contains','typeGroup':'COMMON'})
    token=c.get('/api/device/'+device_id+'/credentials')['credentialsId']
    source=c.get('/api/dashboard/'+rt['TB_DASHBOARD_ID'])
    config=copy.deepcopy(source['configuration'])
    scene=next(w for w in config['widgets'].values() if w['type']=='latest')['config']['settings']
    assert scene['sceneLighting']['version']==4
    assert scene['sceneLighting']['orientation']=='transverse'
    assert scene['sceneLighting']['coverage']=='full-scene'
    assert scene['sceneLighting']==json.loads((ROOT/'thingsboard/widgets/lighting-layout.json').read_text(encoding='utf-8'))
    deployed_image=base64.b64decode(scene['sceneImage'].split(',',1)[1])
    assert hashlib.sha256(deployed_image).digest()==hashlib.sha256((ROOT/'assets/classroom-overview-v2.png').read_bytes()).digest()
    results.append({'test':'approved_corner_image_and_transverse_layout','passed':True})
    for alias in config['entityAliases'].values():
        ref=alias['filter']['singleEntity'];ref['id']=device_id if ref['entityType']=='DEVICE' else asset_id
    for widget in config['widgets'].values():
        if widget['type']=='latest':widget['config']['settings']['deviceId']=device_id
    dashboard=save('dashboard',{'title':'QA Classroom Pipeline '+stamp,'configuration':config})
    broker=mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,client_id='Classroom-QA-'+stamp)
    broker.username_pw_set(token)
    def publish():
        with lock:
            counter[0]+=1
            payload=dict(state,sequence=counter[0],uptime_s=counter[0]*2)
        broker.publish('v1/devices/me/telemetry',json.dumps(payload))
    def on_connect(client,userdata,flags,reason,properties):
        if reason.is_failure:raise RuntimeError('MQTT authentication failed')
        client.subscribe('v1/devices/me/rpc/request/+',qos=1);connected.set()
    def on_message(client,userdata,message):
        req=json.loads(message.payload);method=req['method'];params=req['params']
        value=params if isinstance(params,bool) else params.get('state') if isinstance(params,dict) else None
        with lock:
            if method.startswith('setLight'):state['light'+method[-1]+'_state']=value
            elif method=='setFan':state.update(fan_state=value,fan_mode='MANUAL')
            elif method=='setFanMode':state['fan_mode']=params
            elif method=='resetPeopleCounter':
                assert params.get('confirmEmpty') is True
                state.update(occupancy=0,total_entered=0,total_exited=0,counter_errors=0,counter_needs_calibration=False,fan_state=False)
            response={'success':True,'value':value,**state}
        client.publish(message.topic.replace('/request/','/response/'),json.dumps(response));publish()
    broker.on_connect=on_connect;broker.on_message=on_message
    broker.connect(rt['TB_MQTT_HOST'],1883,keepalive=30);broker.loop_start()
    assert connected.wait(10),'MQTT connect timeout'
    def background():
        while not stop.is_set():publish();stop.wait(2)
    thread=threading.Thread(target=background,daemon=True);thread.start()
    poll(lambda:truth(latest('DEVICE',device_id,['online']).get('online')))
    shots=ROOT/'docs/screenshots';shots.mkdir(parents=True,exist_ok=True)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        context=browser.new_context(viewport={'width':1600,'height':1200},timezone_id='Asia/Ho_Chi_Minh')
        storage={}
        for source_key,key in [('token','jwt_token'),('refreshToken','refresh_token')]:
            jwt=auth[source_key];encoded=jwt.split('.')[1];obj=json.loads(base64.urlsafe_b64decode(encoded+'='*(-len(encoded)%4)))
            storage[key]=jwt;storage[key+'_expiration']=str(obj['exp']*1000)
        context.add_init_script('for(const[k,v]of Object.entries('+json.dumps(storage)+'))localStorage.setItem(k,v);')
        context.add_init_script('window.__qaWsClose=[];window.WebSocket=new Proxy(WebSocket,{construct(Target,args){const ws=new Target(...args);ws.addEventListener("close",e=>window.__qaWsClose.push({code:e.code,reason:e.reason,clean:e.wasClean}));return ws;}});')
        page=context.new_page();errors=[];frames=[];sent=[];page.on('pageerror',lambda e:errors.append(str(e)))
        def observe_socket(ws):
            ws.on('framereceived',lambda payload:frames.append(payload) if len(frames)<500 else None)
            ws.on('socketerror',lambda error:errors.append('WebSocket: '+str(error)))
            ws.on('framesent',lambda payload:sent.append(payload) if len(sent)<20 and 'token' not in str(payload).lower() else None)
        page.on('websocket',observe_socket)
        page.goto(rt['TB_BASE_URL']+'/dashboards/'+uid(dashboard),wait_until='domcontentloaded')
        page.locator('.cl-twin').wait_for(timeout=60000)
        assert page.locator('.cl-header h1').inner_text().rstrip('.')=='Classroom A302'
        assert page.locator('.cl-lit-scene').count()==1
        masks=[]
        for i in range(1,5):
            button=page.locator('.cl-light-control[data-light="'+str(i)+'"]')
            page.wait_for_function('(i)=>!document.querySelector(".cl-light-control[data-light=\\\""+i+"\\\"]").disabled',arg=i)
            with page.expect_response(lambda r:'/api/rpc/twoway/' in r.url and r.request.method=='POST') as resp:
                button.click()
            assert resp.value.status==200,resp.value.status
            assert resp.value.json()['success'] is True
            intent=c.get('/api/plugins/telemetry/DEVICE/'+device_id+'/values/attributes/SERVER_SCOPE',{'keys':f'expected_light{i}_state,expected_light{i}_ts'})
            intent={a['key']:a['value'] for a in intent}
            assert intent[f'expected_light{i}_state'] is True and intent[f'expected_light{i}_ts']>0,intent
            feedback=latest('DEVICE',device_id,[f'light{j}_state' for j in range(1,5)]+['online','last_seen'])
            print('[AWS QA] RPC light',i,'feedback',feedback,flush=True)
            try:
                page.wait_for_function('(i)=>document.querySelector(".cl-lit-scene").dataset.activeLights===String(i)',arg=i)
            except Exception:
                print('[AWS QA] Widget DOM',json.dumps(page.locator('.cl-twin').inner_text(),ensure_ascii=True),flush=True)
                print('[AWS QA] Browser errors',errors,flush=True)
                print('[AWS QA] WebSocket close',page.evaluate('window.__qaWsClose'),flush=True)
                print('[AWS QA] WebSocket received',json.dumps([f for f in frames if 'ENTITY_DATA' in str(f)][-5:],ensure_ascii=True),flush=True)
                page.locator('.cl-twin').screenshot(path=str(shots/'qa-aws-failure.png'))
                raise
            feedback=latest('DEVICE',device_id,[f'light{j}_state' for j in range(1,5)])
            assert all(truth(feedback.get(f'light{j}_state'))==(j==i) for j in range(1,5)),feedback
            masks.append(page.locator('.cl-lit-scene').evaluate('(el)=>getComputedStyle(el).maskImage'))
            if i==1:
                coverage=mask_coverage(page,scene['sceneLighting']['boardProbes'])
                assert min(coverage['probeAlpha'])>=254,coverage
                results.append({'test':'light_1_fully_illuminates_board','passed':True,'coverage':coverage})
            page.locator('.cl-twin').screenshot(path=str(shots/f'qa-aws-light-{i}.png'))
            results.append({'test':'widget_rpc_light_'+str(i),'passed':True,'feedback':feedback})
            button.click();page.wait_for_function('()=>document.querySelector(".cl-lit-scene").dataset.activeLights===""')
        assert len(set(masks))==4 and all('image/svg+xml' in mask for mask in masks)
        for i in range(1,5):page.locator('.cl-light-control[data-light="'+str(i)+'"]').click()
        page.wait_for_function('()=>document.querySelector(".cl-lit-scene").dataset.activeLights==="1,2,3,4"')
        page.wait_for_timeout(650)
        page.locator('.cl-twin').screenshot(path=str(shots/'qa-aws-all-lights.png'))
        coverage=mask_coverage(page)
        assert coverage['dimPixels']==0,coverage
        results.append({'test':'four_lights_cover_entire_scene_without_dark_seams','passed':True,'coverage':coverage})
        feedback=latest('DEVICE',device_id,[f'light{j}_state' for j in range(1,5)])
        assert all(truth(value) for value in feedback.values()) and len(feedback)==4
        results.append({'test':'four_lanes_on_together','passed':True,'feedback':feedback})
        for i in range(1,5):page.locator('.cl-light-control[data-light="'+str(i)+'"]').click()
        page.wait_for_function('()=>document.querySelector(".cl-lit-scene").dataset.activeLights===""')
        fan=page.locator('[data-fan]');fan.click()
        page.wait_for_function('()=>document.querySelector(".cl-fan-toggle").classList.contains("is-on")')
        assert latest('DEVICE',device_id,['fan_mode'])['fan_mode']=='MANUAL'
        page.locator('.cl-twin').screenshot(path=str(shots/'qa-aws-fan-manual.png'))
        fan.click();page.wait_for_function('()=>!document.querySelector(".cl-fan-toggle").classList.contains("is-on")')
        page.locator('[data-mode="AUTO"]').click()
        page.wait_for_function('()=>document.querySelector("[data-mode=\\\"AUTO\\\"]").classList.contains("is-selected")')
        results.append({'test':'widget_rpc_fan_manual_and_auto','passed':True})
        # Synthetic counter telemetry is confined to this QA device, not Wokwi.
        # The real C++ crossing algorithm is tested separately in people-counter.test.cpp.
        with lock:state.update(occupancy=3,total_entered=5,total_exited=2,fan_state=True)
        publish()
        page.wait_for_function('()=>document.querySelector("[data-value=occupancy]").textContent==="3"')
        page.wait_for_function('()=>document.querySelector(".cl-fan-toggle").classList.contains("is-on")')
        poll(lambda:latest('ASSET',asset_id,['occupancy']).get('occupancy')=='3')
        assert page.locator('.cl-people-count [data-value="occupancy"]').inner_text()=='3'
        results.append({'test':'counter_telemetry_device_asset_widget','passed':True})
        with lock:state.update(occupancy=1,total_entered=2,total_exited=1)
        publish()
        page.wait_for_function('()=>document.querySelector("[data-value=occupancy]").textContent==="1"')
        page.locator('.cl-twin').screenshot(path=str(shots/'qa-aws-counter-one.png'))
        with lock:state.update(occupancy=3,total_entered=5,total_exited=2)
        publish()
        page.wait_for_function('()=>document.querySelector("[data-value=occupancy]").textContent==="3"')
        with lock:state.update(ir_a_blocked=True,counter_state='ENTERING')
        publish()
        page.wait_for_function('()=>document.querySelector("[data-gate=a]").classList.contains("is-blocked")')
        assert page.locator('[data-counter]').is_disabled()
        with lock:state.update(ir_a_blocked=False,counter_state='IDLE')
        publish()
        page.wait_for_function('()=>!document.querySelector("[data-counter]").disabled')
        page.once('dialog',lambda dialog:dialog.dismiss())
        page.locator('[data-counter]').click()
        assert page.locator('[data-value="occupancy"]').first.inner_text()=='3','Cancel must retain count'
        page.once('dialog',lambda dialog:dialog.accept())
        page.locator('[data-counter]').click()
        page.wait_for_function('()=>document.querySelector("[data-value=occupancy]").textContent==="0"')
        results.append({'test':'counter_gate_indicators_and_confirmed_empty_reset','passed':True})
        # An actual stale command must still raise a mismatch after grace + 3 samples.
        c.post('/api/plugins/telemetry/DEVICE/'+device_id+'/attributes/SERVER_SCOPE',{
            'expected_light1_state':True,'expected_light1_ts':int(time.time()*1000)-20000})
        poll(lambda:latest('ASSET',asset_id,['anomaly_type']).get('anomaly_type')=='ACTUATOR_MISMATCH',seconds=20)
        c.post('/api/plugins/telemetry/DEVICE/'+device_id+'/attributes/SERVER_SCOPE',{
            'expected_light1_state':False,'expected_light1_ts':int(time.time()*1000)-20000})
        poll(lambda:latest('ASSET',asset_id,['observed_state']).get('observed_state')=='NORMAL',seconds=20)
        results.append({'test':'recorded_intent_mismatch_and_recovery','passed':True})
        assert not errors,errors
        assert not page.evaluate('window.__qaWsClose'),'Dashboard WebSocket unexpectedly disconnected'
        results.append({'test':'shared_websocket_remains_connected','passed':True})
        with lock:state['temperature']=35
        poll(lambda:latest('ASSET',asset_id,['anomaly_type']).get('anomaly_type')=='HIGH_TEMPERATURE')
        twin=latest('ASSET',asset_id,['health_score','anomaly_score','observed_state'])
        assert twin['health_score']=='10' and twin['observed_state']=='ANOMALY',twin
        alarms=c.get('/api/alarm/ASSET/'+asset_id,{'pageSize':100,'page':0})['data']
        assert any(a['type']=='HIGH_TEMPERATURE' and 'ACTIVE' in a['status'] for a in alarms),alarms
        page.wait_for_function('()=>document.querySelector("[data-value=temperature]").textContent.startsWith("35") && document.querySelector("[data-value=health_score]").textContent==="10"')
        page.locator('.cl-twin').screenshot(path=str(shots/'qa-aws-alarm-temperature.png'))
        results.append({'test':'rule_chain_high_temperature_and_alarm','passed':True,'twin':twin})
        with lock:state['temperature']=26
        poll(lambda:latest('ASSET',asset_id,['observed_state']).get('observed_state')=='NORMAL',seconds=20)
        alarms=c.get('/api/alarm/ASSET/'+asset_id,{'pageSize':100,'page':0})['data']
        assert any(a['type']=='HIGH_TEMPERATURE' and 'CLEARED' in a['status'] for a in alarms)
        page.wait_for_function('()=>document.querySelector("[data-value=health_score]").textContent==="100"')
        page.locator('.cl-twin').screenshot(path=str(shots/'qa-aws-recovery.png'))
        results.append({'test':'recovery_and_alarm_clear','passed':True})
        browser.close()
    stop.set();thread.join(timeout=3);broker.disconnect();broker.loop_stop();broker=None
    poll(lambda:latest('ASSET',asset_id,['observed_state']).get('observed_state')=='OFFLINE',seconds=40)
    alarms=c.get('/api/alarm/ASSET/'+asset_id,{'pageSize':100,'page':0})['data']
    assert any(a['type']=='CONNECTION_LOST' and 'ACTIVE' in a['status'] for a in alarms)
    results.append({'test':'offline_state_and_connection_lost_alarm','passed':True})
    print('[AWS QA] Widget, four light zones, fan, Rule Engine and alarm passed.',flush=True)
    out=ROOT/'tests/results';out.mkdir(exist_ok=True)
    (out/'aws-pipeline.json').write_text(json.dumps({'source':'isolated QA MQTT client, not production Wokwi','results':results,'testedAt':int(time.time()*1000)},indent=2),encoding='utf-8')
finally:
    stop.set()
    if broker:broker.disconnect();broker.loop_stop()
    for kind,identity in reversed(created):
        try:c.request('DELETE','/api/'+kind+'/'+identity)
        except Exception as exc:print('QA cleanup failed for '+kind+': '+str(exc),file=sys.stderr)
