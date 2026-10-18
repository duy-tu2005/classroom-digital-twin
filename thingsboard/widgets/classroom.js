var root, values = {}, pending = {}, subscriptions = [], tick, lightingMasks = {};
function truth(v) { return v === true || v === 'true' || v === 1 || v === '1'; }
function text(key, value) { if (!root) return; root.querySelectorAll('[data-value="'+key+'"]').forEach(function(el){el.textContent=value;}); }
function message(value, error) { var el = root.querySelector('.cl-message'); el.textContent = value; el.classList.toggle('is-error', !!error); }
function connected() { return truth(values.online) && Number(values.last_seen) > Date.now() - 20000; }
// u runs across room width; v runs from the board to the rear.
// Extend each band across the whole image, including walls and the board.
function planePoint(quad, u, v) {
    return [0,1].map(function(axis){return (1-v)*((1-u)*quad[0][axis]+u*quad[1][axis])+v*((1-u)*quad[3][axis]+u*quad[2][axis]);});
}
function clipHalfPlane(polygon, a, b, keepRear) {
    var sign=keepRear ? 1 : -1;
    function distance(p){return sign*((b[0]-a[0])*(p[1]-a[1])-(b[1]-a[1])*(p[0]-a[0]));}
    var result=[];
    polygon.forEach(function(current,i){
        var previous=polygon[(i+polygon.length-1)%polygon.length];
        var dc=distance(current), dp=distance(previous), inside=dc>=0, wasInside=dp>=0;
        if (inside!==wasInside) {
            var t=dp/(dp-dc);
            result.push([previous[0]+t*(current[0]-previous[0]),previous[1]+t*(current[1]-previous[1])]);
        }
        if (inside) result.push(current);
    });
    return result;
}
function coveragePolygon(layout,lane) {
    var m=layout.coverageMargin, polygon=[[-m,-m],[1+m,-m],[1+m,1+m],[-m,1+m]], quad=layout.projectionQuad;
    if (lane.range[0]>0) polygon=clipHalfPlane(polygon,planePoint(quad,0,lane.range[0]),planePoint(quad,1,lane.range[0]),true);
    if (lane.range[1]<1) polygon=clipHalfPlane(polygon,planePoint(quad,0,lane.range[1]),planePoint(quad,1,lane.range[1]),false);
    return polygon;
}
function lightingSvg(layout,enabled) {
    // One union path, then one blur: neighboring ON bands have no compositing seams.
    var paths=layout.lanes.filter(function(lane){return enabled.indexOf(lane.id)!==-1;}).map(function(lane){
        return 'M'+coveragePolygon(layout,lane).map(function(p){return p.map(function(x){return (x*1000).toFixed(2);}).join(',');}).join(' L')+' Z';
    }).join(' ');
    return '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="0 0 1000 1000" preserveAspectRatio="none"><defs><filter id="soft" x="-30%" y="-30%" width="160%" height="160%" color-interpolation-filters="sRGB"><feGaussianBlur stdDeviation="'+(layout.edgeSoftness*1000)+'"/></filter></defs><path d="'+paths+'" fill="white" filter="url(#soft)"/></svg>';
}
function initLighting() {
    var layout=self.ctx.settings.sceneLighting;
    if (!layout || !layout.lanes || layout.lanes.length!==4) return;
    for (var state=0;state<16;state++) {
        var enabled=layout.lanes.filter(function(lane){return !!(state & (1<<(lane.id-1)));}).map(function(lane){return lane.id;});
        lightingMasks[enabled.join(',')]='url("data:image/svg+xml,'+encodeURIComponent(lightingSvg(layout,enabled))+'")';
    }
    layout.lanes.forEach(function(lane){
        var pin=root.querySelector('.cl-pin[data-light="'+lane.id+'"]');
        pin.style.left=(lane.marker[0]*100)+'%';pin.style.top=(lane.marker[1]*100)+'%';
        pin.title=lane.label+' · ngang lớp, từ tường trái sang tường phải';
    });
}
function render() {
    if (!root) return;
    var online = connected(), lightsOn = 0, enabled=[];
    root.classList.toggle('cl-online', online);
    root.classList.toggle('cl-fan-running', online && truth(values.fan_state));
    for (var i = 1; i <= 4; i++) {
        var on = truth(values['light'+i+'_state']);
        if (on) { lightsOn++; enabled.push(i); }
        root.querySelectorAll('[data-light="'+i+'"]').forEach(function(el){
            el.classList.toggle('is-on', on); el.setAttribute('aria-pressed', String(on));
            el.disabled = !online || !!pending['light'+el.getAttribute('data-light')];
        });
    }
    var litScene=root.querySelector('.cl-lit-scene'), key=enabled.join(',');
    if (litScene.getAttribute('data-active-lights')!==key) {
        var mask=lightingMasks[key];
        litScene.style.maskImage=mask;litScene.style.webkitMaskImage=mask;
        litScene.setAttribute('data-active-lights',key);
    }
    litScene.classList.toggle('is-on',lightsOn>0);
    text('lights_on_count', lightsOn);
    // Gentle bounce only; the union mask itself guarantees complete coverage at 4/4.
    root.style.setProperty('--cl-ambient',String(0.55+lightsOn*0.025));
    text('temperature', values.sensor_valid !== undefined && !truth(values.sensor_valid) ? '—' : values.temperature !== undefined ? Number(values.temperature).toFixed(1) : '—');
    text('humidity', values.humidity !== undefined ? Number(values.humidity).toFixed(0) : '—');
    var hasCounter = values.occupancy !== undefined;
    text('occupancy', hasCounter ? values.occupancy : '—');
    text('occupancy_note', !hasCounter ? 'Chờ firmware đếm người' : !online ? 'Số cuối nhận · đang ngoại tuyến' : truth(values.counter_needs_calibration) ? 'Ước tính · cần hiệu chuẩn' : 'Hai tia A/B · GPIO13 / 27');
    ['total_entered','total_exited'].forEach(function(key){text(key,values[key] === undefined ? '—' : values[key]);});
    ['a','b'].forEach(function(gate){
        var known=values['ir_'+gate+'_blocked'] !== undefined, blocked=truth(values['ir_'+gate+'_blocked']);
        text('ir_'+gate, !known ? 'chờ' : blocked ? 'bị chắn' : 'thông');
        root.querySelector('[data-gate="'+gate+'"]').classList.toggle('is-blocked',blocked);
    });
    var counterStates={IDLE:'Cửa thông',ENTERING:'Đang đi vào',EXITING:'Đang đi ra',BLOCKED:'Chuỗi tia lỗi / quá thời gian'};
    text('counter_state',hasCounter ? counterStates[values.counter_state] || 'Chờ hai tia' : 'Chờ firmware đếm người');
    text('counter_note',truth(values.counter_needs_calibration) ? 'Số đếm chưa được xác nhận hoặc đã có chuỗi tia lỗi ('+Number(values.counter_errors||0)+'). Chỉ hiệu chuẩn khi phòng thực sự trống.' : 'Wokwi: giữ A → giữ B → nhả A → nhả B để vào; đảo thứ tự để ra. Đây là tín hiệu giả lập, không phải đo quang học.');
    root.querySelector('.cl-counter-note').classList.toggle('is-warning',truth(values.counter_needs_calibration));
    root.querySelector('[data-counter]').disabled=!online||!hasCounter||!!pending.counter||truth(values.ir_a_blocked)||truth(values.ir_b_blocked)||values.counter_state!=='IDLE';
    text('health_score', values.health_score === undefined ? '—' : online ? values.health_score : 0);
    var states = {INIT:'Khởi tạo', NORMAL:'Bình thường', WARNING:'Cần chú ý', ANOMALY:'Bất thường', RECOVERY:'Đang phục hồi', OFFLINE:'Mất kết nối'};
    text('observed_state', online ? states[values.observed_state] || 'Chờ đánh giá' : 'Mất kết nối');
    text('connection', online ? 'ESP32 trực tuyến' : 'ESP32 ngoại tuyến');
    var ts = Number(values.last_seen);
    text('updated', ts ? 'Cập nhật '+new Date(ts).toLocaleTimeString('vi-VN') : 'Chờ dữ liệu ESP32');
    text('fan_badge', (online ? 'Quạt đang ' : 'Lần cuối: quạt ')+(truth(values.fan_state) ? 'bật' : 'tắt'));
    var welcome=root.querySelector('.cl-message');
    if (online && welcome.textContent === 'Chờ kết nối ESP32 để điều khiển.') welcome.textContent='Điều khiển đã sẵn sàng. Hình ảnh theo phản hồi ESP32.';
    var mode = values.fan_mode || 'AUTO';
    root.querySelectorAll('[data-mode]').forEach(function(el){el.classList.toggle('is-selected', el.getAttribute('data-mode') === mode);el.disabled=!online||!!pending.fan;});
    var fanButton = root.querySelector('[data-fan]');
    fanButton.textContent = truth(values.fan_state) ? 'Tắt quạt' : 'Bật quạt';
    fanButton.classList.toggle('is-on', truth(values.fan_state));
    fanButton.disabled = !online || !!pending.fan;
}
function send(method, params, target) {
    if (!connected() || pending[target]) return;
    pending[target] = true;
    message('Đang gửi lệnh đến ESP32…', false); render();
    // Angular HttpClient uses the signed-in tenant's auth interceptor; no device token in widget.
    var http = self.ctx.$scope.$injector.get(self.ctx.servicesMap.get('http'));
    function dispatch() {
    var sub = http.post('/api/rpc/twoway/'+self.ctx.settings.deviceId, {method:method, params:params, timeout:10000}).subscribe(function(response){
        delete pending[target];
        if (response && response.success === false) message('Thiết bị từ chối: '+(response.error || 'Lệnh không hợp lệ'), true);
        else message('ESP32 đã xác nhận. Đang cập nhật trạng thái phản hồi.', false);
        // Output and illumination update exclusively from telemetry onDataUpdated.
        render();
    }, function(error){
        delete pending[target];
        message('Không nhận được phản hồi. Kiểm tra Wokwi và kết nối MQTT.', true); render();
    });
    subscriptions.push(sub);
    }
    // REST RPC may bypass the device Rule Chain. Record the authenticated user's
    // intent explicitly; never assume false defaults are actual requested states.
    var intent={}, channel=/^setLight([1-4])$/.exec(method);
    if(channel || method==='setFan') {
        var output=channel ? 'light'+channel[1] : 'fan';
        intent['expected_'+output+'_state']=params;
        intent['expected_'+output+'_ts']=Date.now();
        var saved=http.post('/api/plugins/telemetry/DEVICE/'+self.ctx.settings.deviceId+'/attributes/SERVER_SCOPE',intent).subscribe(dispatch,function(){
            delete pending[target];message('Không lưu được trạng thái yêu cầu; chưa gửi lệnh điều khiển.',true);render();
        });
        subscriptions.push(saved);
    } else dispatch();
}
self.onInit = function() {
    root = self.ctx.$container[0].querySelector('.cl-twin');
    if (self.ctx.settings.sceneImage) root.querySelectorAll('.cl-scene img').forEach(function(img){img.src=self.ctx.settings.sceneImage;});
    initLighting();
    root.querySelectorAll('[data-light]').forEach(function(el){el.onclick=function(){var ch=el.getAttribute('data-light');send('setLight'+ch,!truth(values['light'+ch+'_state']),'light'+ch);};});
    root.querySelectorAll('[data-mode]').forEach(function(el){el.onclick=function(){send('setFanMode',el.getAttribute('data-mode'),'fan');};});
    root.querySelector('[data-fan]').onclick=function(){send('setFan',!truth(values.fan_state),'fan');};
    root.querySelector('[data-counter]').onclick=function(){
        if(window.confirm('Bạn xác nhận phòng hiện không có ai? Số người và tổng lượt vào/ra sẽ về 0.')) send('resetPeopleCounter',{confirmEmpty:true},'counter');
    };
    tick = setInterval(render, 1000);
    self.onDataUpdated();
};
self.onDataUpdated = function() {
    (self.ctx.data || []).forEach(function(series){if (series.data && series.data.length) values[series.dataKey.name] = series.data[series.data.length-1][1];});
    render();
};
self.onResize = render;
self.onDestroy = function(){clearInterval(tick);subscriptions.forEach(function(sub){sub.unsubscribe();});};
self.typeParameters = function(){return {singleEntity:true};};
