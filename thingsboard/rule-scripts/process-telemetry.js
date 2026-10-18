// ThingsBoard transformation node: incoming Device telemetry + enriched metadata.
function n(v, fallback) { var x = Number(v); return v !== null && v !== undefined && v !== '' && isFinite(x) ? x : fallback; }
function b(v) { return v === true || v === 'true' || v === 1 || v === '1'; }
function prev(key, fallback) {
    var v = metadata[key];
    if (v === null || v === undefined || v === '') return fallback;
    try { var obj = JSON.parse(v); return obj && obj.value !== undefined ? obj.value : obj; } catch (e) { return v; }
}
function config(key, fallback) { return n(metadata['ss_' + key], fallback); }
var now = n(metadata.ts, Date.now());
var faults = [];
function fault(type, score, details) { faults.push({type:type, score:score, details:details}); }
var temp = n(msg.temperature, NaN);
var valid = b(msg.sensor_valid) && isFinite(temp) && temp >= -40 && temp <= 80;
var invalidCount = valid ? 0 : n(prev('invalid_count', 0), 0) + 1;
if (invalidCount >= 3) fault('INVALID_SENSOR', 80, {samples:invalidCount});
if (valid) {
    if (temp > config('temp_critical_high', 32)) fault('HIGH_TEMPERATURE', 90, {value:temp});
    else if (temp > config('temp_warn_high', 28)) fault('HIGH_TEMPERATURE', 40, {value:temp});
    else if (temp < config('temp_warn_low', 18)) fault('LOW_TEMPERATURE', 35, {value:temp});
}
var rssi = n(msg.rssi, -127);
if (rssi <= config('weak_rssi_critical', -90)) fault('WEAK_SIGNAL', 80, {rssi:rssi});
else if (rssi <= config('weak_rssi_warning', -85)) fault('WEAK_SIGNAL', 30, {rssi:rssi});
var mismatched = [];
for (var i = 1; i <= 4; i++) {
    var key = 'light' + i + '_state';
    var expected = metadata['ss_expected_' + key];
    var commandTs = config('expected_light' + i + '_ts', 0);
    if (commandTs > 0 && expected !== undefined && expected !== null && now - commandTs >= 10000 && b(msg[key]) !== b(expected)) mismatched.push(key);
    msg['expected_' + key] = commandTs <= 0 || expected === undefined || expected === null ? b(msg[key]) : b(expected);
}
var mode = String(msg.fan_mode || 'AUTO').toUpperCase();
if (mode === 'MANUAL' && config('expected_fan_ts', 0) > 0 && metadata.ss_expected_fan_state !== undefined &&
    now - config('expected_fan_ts', 0) >= 10000 && b(msg.fan_state) !== b(metadata.ss_expected_fan_state)) mismatched.push('fan_state');
var mismatchCount = mismatched.length ? n(prev('actuator_mismatch_count', 0), 0) + 1 : 0;
if (mismatchCount >= config('actuator_mismatch_samples', 3)) fault('ACTUATOR_MISMATCH', 70, {outputs:mismatched, samples:mismatchCount});
var best = {type:'NONE', score:0, details:{}};
var names = [];
for (var j = 0; j < faults.length; j++) { names.push(faults[j].type); if (faults[j].score > best.score) best = faults[j]; }
var previousState = String(prev('observed_state', 'INIT'));
var recovery = best.score === 0 && previousState !== 'NORMAL' ? n(prev('recovery_count', 0), 0) + 1 : 0;
var state = best.score >= 50 ? 'ANOMALY' : best.score >= 20 ? 'WARNING' :
    previousState === 'NORMAL' || recovery >= 3 ? 'NORMAL' : 'RECOVERY';
msg.online = true;
msg.last_seen = now;
msg.observed_state = state;
msg.expected_state = 'NORMAL';
msg.state_match = state === 'NORMAL';
msg.health_score = Math.max(0, 100 - best.score);
msg.anomaly_score = best.score;
msg.anomaly = best.score > 0;
msg.anomaly_type = best.type;
msg.active_anomalies = JSON.stringify(names);
msg.anomaly_details = JSON.stringify(best.details);
msg.invalid_count = invalidCount;
msg.actuator_mismatch_count = mismatchCount;
msg.recovery_count = recovery;
msg.lights_on_count = 0;
for (var k = 1; k <= 4; k++) if (b(msg['light'+k+'_state'])) msg.lights_on_count++;
metadata.prevAlarmType = String(prev('anomaly_type', 'NONE'));
metadata.alarmType = best.type;
metadata.alarmSeverity = best.score >= 80 ? 'CRITICAL' : best.score >= 50 ? 'MAJOR' : 'WARNING';
return {msg:msg, metadata:metadata, msgType:msgType};

