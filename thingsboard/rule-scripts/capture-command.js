// Mirror only valid commands; do not overwrite expected states of other outputs.
var result = {};
var method = String(msg.method || '');
var p = msg.params;
var value = typeof p === 'boolean' ? p : p && typeof p.state === 'boolean' ? p.state : p && typeof p.value === 'boolean' ? p.value : null;
for (var i = 1; i <= 4; i++) {
    if (method === 'setLight' + i && value !== null) {
        result['expected_light' + i + '_state'] = value;
        result['expected_light' + i + '_ts'] = Date.now();
    }
}
if (method === 'setFan' && value !== null) { result.expected_fan_state = value; result.expected_fan_ts = Date.now(); }
return {msg:result, metadata:metadata, msgType:'POST_ATTRIBUTES_REQUEST'};

