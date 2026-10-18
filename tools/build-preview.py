"""Build a clearly-labelled, local-only UI preview using the real widget assets."""
from pathlib import Path
import json
root=Path(__file__).resolve().parents[1]
widget=root/'thingsboard/widgets'
out=root/'preview'
out.mkdir(exist_ok=True)
html=(widget/'classroom.html').read_text(encoding='utf-8').replace('__CLASSROOM_IMAGE__','../assets/classroom-overview-v2.png')
css=(widget/'classroom.css').read_text(encoding='utf-8')
js=(widget/'classroom.js').read_text(encoding='utf-8')
stub='''var sample={temperature:26,humidity:60,occupancy:3,total_entered:5,total_exited:2,ir_a_blocked:false,ir_b_blocked:false,counter_state:'IDLE',counter_errors:0,counter_needs_calibration:false,health_score:100,observed_state:'NORMAL',online:true,last_seen:Date.now(),fan_state:false,fan_mode:'AUTO',light1_state:false,light2_state:false,light3_state:false,light4_state:false};
var previewHttp={post:function(url,body){return {subscribe:function(ok){
    setTimeout(function(){
        var m=body.method;
        if(m==='resetPeopleCounter')Object.assign(sample,{occupancy:0,total_entered:0,total_exited:0,counter_errors:0,counter_needs_calibration:false});
        if(/^setLight[1-4]$/.test(m))sample['light'+m.slice(-1)+'_state']=body.params;
        if(m==='setFan'){sample.fan_state=body.params;sample.fan_mode='MANUAL';}
        if(m==='setFanMode')sample.fan_mode=body.params;
        sample.last_seen=Date.now();updateSample();ok({success:true});
    },120);
    return {unsubscribe:function(){}};
}};}};
var previewWidget={ctx:{$container:[document.querySelector('#widget')],settings:{deviceId:'preview',sceneLighting:__LIGHTING_LAYOUT__},
    $scope:{$injector:{get:function(){return previewHttp;}}},servicesMap:new Map([['http','http']]),data:[]}};
function updateSample(){previewWidget.ctx.data=Object.keys(sample).map(function(k){return{dataKey:{name:k},data:[[Date.now(),sample[k]]]};});if(previewWidget.onDataUpdated)previewWidget.onDataUpdated();}
updateSample();setInterval(function(){sample.last_seen=Date.now();updateSample();},5000);
'''
stub=stub.replace('__LIGHTING_LAYOUT__',json.dumps(json.loads((widget/'lighting-layout.json').read_text(encoding='utf-8'))))
page='<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Classroom Twin - Local Preview</title><style>body{margin:0;background:#e9eff4;padding:22px;font-family:Arial}#preview-label{margin:0 auto 14px;max-width:1280px;color:#536c7a;font-size:12px}#widget{max-width:1280px;margin:auto}.cl-twin{height:auto!important;overflow:visible!important}</style><style>'+css+'</style><p id="preview-label">BẢN XEM TRƯỚC GIAO DIỆN · dữ liệu mô phỏng local · không gửi lệnh AWS</p><div id="widget">'+html+'</div><script>'+stub+'</script><script>new Function("self",'+repr(js+'\nself.onInit();')+')(previewWidget);</script></html>'
(out/'index.html').write_text(page,encoding='utf-8')
print('Preview ready: preview/index.html')

