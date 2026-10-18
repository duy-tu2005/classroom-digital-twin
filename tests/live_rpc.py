"""Verify RPC on the actual Wokwi firmware; restore original outputs afterward."""
import argparse
import json
import hashlib
import re
import subprocess
import sys
import time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'thingsboard'))
from api import Client,env_file
parser=argparse.ArgumentParser();parser.add_argument('--wait-online',type=int,default=180);args=parser.parse_args()
subprocess.run([sys.executable,str(ROOT/'tests/wiring_test.py')],check=True)
version=re.search(r'FIRMWARE_VERSION\[\]\s*=\s*"([^"]+)"',(ROOT/'firmware/config.h').read_text())[1]
cfg=env_file(ROOT/'deployment/.env');rt=env_file(ROOT/'.env.local')
c=Client(rt['TB_BASE_URL'],cfg['TB_USERNAME'],cfg['TB_PASSWORD'])
device=rt['TB_DEVICE_ID']
def latest(keys):
    data=c.get('/api/plugins/telemetry/DEVICE/'+device+'/values/timeseries',{'keys':','.join(keys)})
    return {key:series[-1]['value'] for key,series in data.items() if series}
def truth(v):return v is True or str(v).lower() in ('true','1')
def rpc(method,params):
    if method in ['setLight1','setLight2','setLight3','setLight4','setFan']:
        name='light'+method[-1] if method.startswith('setLight') else 'fan'
        c.post('/api/plugins/telemetry/DEVICE/'+device+'/attributes/SERVER_SCOPE',{
            'expected_'+name+'_state':params,'expected_'+name+'_ts':int(time.time()*1000)})
    # Setters are idempotent; retry one dropped reply without flipping the output twice.
    for attempt in range(2):
        try:
            result=c.post('/api/rpc/twoway/'+device,{'method':method,'params':params,'timeout':20000})
            break
        except RuntimeError as error:
            if attempt or 'HTTP 504' not in str(error):raise
            print('[live] '+method+' reply timed out; retrying the same target state once',flush=True)
    if not result or result.get('success') is not True:raise AssertionError('RPC rejected: '+str(result))
    return result
def await_values(expected):
    deadline=time.monotonic()+12
    while time.monotonic()<deadline:
        values=latest(list(expected))
        if all(truth(values.get(k))==v if isinstance(v,bool) else values.get(k)==v for k,v in expected.items()):return values
        time.sleep(.6)
    raise AssertionError('Telemetry did not confirm '+str(expected))
deadline=time.monotonic()+args.wait_online
print('[live] Waiting for fresh Wokwi telemetry, firmware '+version+'...',flush=True)
while True:
    values=latest(['online','last_seen','firmware_version'])
    if truth(values.get('online')) and values.get('firmware_version')==version and int(values.get('last_seen',0))>int(time.time()*1000)-12000:break
    if time.monotonic()>deadline:raise SystemExit('Wokwi did not remain online. Keep the simulator tab visible and restart it.')
    time.sleep(2)
original=rpc('getStatus',{})
print('[live] Actual firmware replied to getStatus',flush=True)
results=[]
try:
    for i in range(1,5):rpc('setLight'+str(i),False)
    for i in range(1,5):
        response=rpc('setLight'+str(i),True)
        assert response.get('gpio')==[16,17,18,19][i-1] and response.get('pin_state') is True,response
        expected={f'light{j}_state':j==i for j in range(1,5)}
        feedback=await_values(expected)
        results.append({'test':'independent_light_'+str(i),'passed':True,'feedback':feedback})
        print('[live] Light '+str(i)+' ON; other three OFF: confirmed',flush=True)
        time.sleep(1.2)
        rpc('setLight'+str(i),False)
        await_values({f'light{i}_state':False})
    for on in [True,False]:
        rpc('setFan',on)
        values=await_values({'fan_state':on,'fan_mode':'MANUAL'})
        results.append({'test':'manual_fan_'+str(on),'passed':True,'feedback':values})
    rpc('setFanMode','AUTO');await_values({'fan_mode':'AUTO'})
    results.append({'test':'restore_occupancy_auto_mode','passed':True})
    counter=rpc('getPeopleCounter',{})
    assert all(key in counter for key in ['occupancy','total_entered','total_exited','ir_a_blocked','ir_b_blocked','counter_state']),counter
    assert int(counter['occupancy'])>=0,counter
    results.append({'test':'read_actual_ir_counter_status','passed':True,'feedback':counter})
    rejected=c.post('/api/rpc/twoway/'+device,{'method':'resetPeopleCounter','params':{},'timeout':20000})
    assert rejected.get('success') is False and rejected.get('error')=='CONFIRM_EMPTY_ROOM_REQUIRED',rejected
    results.append({'test':'reject_unconfirmed_counter_reset','passed':True})
finally:
    for i in range(1,5):rpc('setLight'+str(i),truth(original.get(f'light{i}_state')))
    if original.get('fan_mode')=='MANUAL':rpc('setFan',truth(original.get('fan_state')))
    else:rpc('setFanMode','AUTO')
out=ROOT/'tests/results';out.mkdir(parents=True,exist_ok=True)
(out/'live-rpc.json').write_text(json.dumps({'testedAt':int(time.time()*1000),'deviceId':device,
    'firmware_version':version,'diagramSha256':hashlib.sha256((ROOT/'firmware/diagram.json').read_bytes()).hexdigest(),
    'scope':'RPC, GPIO telemetry and static wiring validation; not optical LED feedback','results':results},indent=2),encoding='utf-8')
print('[live] All actual firmware RPC tests passed. Original state restored.',flush=True)
