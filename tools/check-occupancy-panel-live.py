"""Read-only UI verification. Auth stays in memory; no device commands sent."""
import base64
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'thingsboard'))
from api import Client, env_file

runtime = env_file(ROOT / '.env.local')
config = env_file(ROOT / 'deployment/.env')
auth = Client(runtime['TB_BASE_URL']).post('/api/auth/login', {'username':config['TB_USERNAME'], 'password':config['TB_PASSWORD']})
client = Client(runtime['TB_BASE_URL'])
client.auth = 'Bearer ' + auth['token']
latest = client.get('/api/plugins/telemetry/ASSET/' + runtime['TB_ASSET_ID'] + '/values/timeseries', {'keys':'occupancy'})
assert latest.get('occupancy'), 'No recorded occupancy on the classroom asset.'
storage = {}
for source, key in [('token','jwt_token'),('refreshToken','refresh_token')]:
    token = auth[source]
    part = token.split('.')[1]
    claim = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
    storage[key], storage[key+'_expiration'] = token, str(claim['exp'] * 1000)
dependencies = Path(os.environ['USERPROFILE']) / '.cache/codex-runtimes/codex-primary-runtime/dependencies'
out = ROOT / 'tests/results/occupancy-panel-live.png'
out.parent.mkdir(parents=True, exist_ok=True)
payload = {'url':runtime['TB_BASE_URL'] + '/dashboards/' + runtime['TB_DASHBOARD_ID'],
           'storage':storage, 'expectedOccupancy':latest['occupancy'][0]['value'], 'screenshot':str(out)}
child_env = dict(os.environ, NODE_PATH=str(dependencies / 'node/node_modules'))
subprocess.run([str(dependencies / 'node/bin/node.exe'), str(ROOT / 'tests/occupancy-panel.test.cjs'), '--live'],
               input=json.dumps(payload), text=True, encoding='utf-8', env=child_env, check=True, timeout=90)
