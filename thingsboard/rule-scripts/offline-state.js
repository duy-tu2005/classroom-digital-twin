var previousType = metadata.anomaly_type || 'NONE';
try { var p = JSON.parse(previousType); previousType = p && p.value !== undefined ? p.value : p; } catch (ignore) {}
metadata.prevAlarmType = String(previousType);
metadata.alarmType = 'CONNECTION_LOST';
metadata.alarmSeverity = 'CRITICAL';
return {msg:{online:false, observed_state:'OFFLINE', expected_state:'NORMAL', state_match:false,
    health_score:0, anomaly_score:100, anomaly:true, anomaly_type:'CONNECTION_LOST',
    active_anomalies:'["CONNECTION_LOST"]', recovery_count:0,
    anomaly_details:JSON.stringify({reason:'No device activity for 20 seconds'})},
    metadata:metadata, msgType:'POST_TELEMETRY_REQUEST'};

