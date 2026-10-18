const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const dir = path.join(__dirname, '../thingsboard/rule-scripts');
const processTelemetry = new Function('msg', 'metadata', 'msgType', fs.readFileSync(path.join(dir,'process-telemetry.js'),'utf8'));
const capture = new Function('msg','metadata','msgType',fs.readFileSync(path.join(dir,'capture-command.js'),'utf8'));
const offline = new Function('msg','metadata','msgType',fs.readFileSync(path.join(dir,'offline-state.js'),'utf8'));
const now = Date.now();
const baseline = {temperature:26,sensor_valid:true,rssi:-60,occupancy:0,total_entered:0,total_exited:0,fan_mode:'AUTO',fan_state:false,
    light1_state:false,light2_state:false,light3_state:false,light4_state:false};
function run(msg={},meta={}) {return processTelemetry({...baseline,...msg},{ts:String(now),observed_state:JSON.stringify({value:'NORMAL'}),...meta},'POST_TELEMETRY_REQUEST').msg;}
assert.equal(run().health_score,100);
assert.equal(run({temperature:35}).anomaly_type,'HIGH_TEMPERATURE');
assert.equal(run({temperature:35}).health_score,10);
assert.equal(run({temperature:29}).observed_state,'WARNING');
assert.equal(run({temperature:16}).anomaly_type,'LOW_TEMPERATURE');
assert.equal(run({sensor_valid:false},{invalid_count:'{"value":2}'}).anomaly_type,'INVALID_SENSOR');
assert.equal(run({rssi:-95}).anomaly_type,'WEAK_SIGNAL');
const expected = {ss_expected_light1_state:'true',ss_expected_light1_ts:String(now-20000),actuator_mismatch_count:'{"value":2}'};
assert.equal(run({},expected).anomaly_type,'ACTUATOR_MISMATCH');
assert.equal(run({light1_state:true},expected).actuator_mismatch_count,0);
assert.equal(run({}, {...expected,ss_expected_light1_ts:String(now-2000)}).anomaly_type,'NONE');
assert.equal(run({fan_mode:'AUTO'},{ss_expected_fan_state:'true',actuator_mismatch_count:'{"value":2}'}).anomaly_type,'NONE');
assert.equal(run({fan_mode:'MANUAL'},{ss_expected_fan_state:'true',ss_expected_fan_ts:String(now-20000),actuator_mismatch_count:'{"value":2}'}).anomaly_type,'ACTUATOR_MISMATCH');
assert.equal(run({light1_state:true},{ss_expected_light1_state:'false',ss_expected_light1_ts:'0',actuator_mismatch_count:'{"value":2}'}).anomaly_type,'NONE');
assert.equal(run({fan_mode:'MANUAL',fan_state:true},{ss_expected_fan_state:'false',ss_expected_fan_ts:'0',actuator_mismatch_count:'{"value":2}'}).anomaly_type,'NONE');
assert.equal(run({occupancy:8,total_entered:10,total_exited:2}).occupancy,8);
assert.equal(run({}, {observed_state:'{"value":"OFFLINE"}',recovery_count:'{"value":0}'}).observed_state,'RECOVERY');
assert.equal(run({}, {observed_state:'{"value":"RECOVERY"}',recovery_count:'{"value":2}'}).observed_state,'NORMAL');
for (let i=1;i<=4;i++) {
    const result=capture({method:'setLight'+i,params:true},{},'RPC_CALL_FROM_SERVER_TO_DEVICE').msg;
    assert.equal(result['expected_light'+i+'_state'],true);
    assert.equal(Object.keys(result).length,2); // Only this channel changes.
}
assert.deepEqual(capture({method:'setLight1',params:'bad'},{},'RPC').msg,{});
assert.equal(offline({}, {anomaly_type:'{"value":"HIGH_TEMPERATURE"}'},'INACTIVITY_EVENT').msg.health_score,0);
console.log('Rule scenarios passed: thresholds, offline/recovery, command isolation and mismatch grace period.');

