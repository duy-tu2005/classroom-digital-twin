"""Update only the classroom widget UI, without resetting entities or counters."""
import argparse
import copy
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'thingsboard'))
from api import Client, env_file, uid

sys.stdout.reconfigure(encoding='utf-8')
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--apply', action='store_true', help='Save the UI to ThingsBoard; otherwise read-only.')
args = parser.parse_args()
runtime = env_file(ROOT / '.env.local')
config = env_file(ROOT / 'deployment/.env')
client = Client(runtime['TB_BASE_URL'], config['TB_USERNAME'], config['TB_PASSWORD'])
stub = client.get('/api/widgetType', {'fqn': 'tenant.classroom_a101_scene'})
before = client.get('/api/widgetType/' + uid(stub))
export_path = ROOT / 'thingsboard/exports/widget-classroom.json'
old_export = json.loads(export_path.read_text(encoding='utf-8'))
widget_path = ROOT / 'thingsboard/widgets'
new_fields = {
    'templateHtml': (widget_path / 'classroom.html').read_text(encoding='utf-8').replace('__CLASSROOM_IMAGE__', 'data:,'),
    'templateCss': (widget_path / 'classroom.css').read_text(encoding='utf-8'),
}
for key, desired in new_fields.items():
    if before['descriptor'][key] not in (old_export['descriptor'][key], desired):
        raise RuntimeError('Live ' + key + ' differs from the saved export; refusing to overwrite another edit.')
assert before['descriptor']['controllerScript'] == (widget_path / 'classroom.js').read_text(encoding='utf-8')
assert 'Số người hiện trong lớp học' in new_fields['templateHtml']
assert new_fields['templateHtml'].count('data-value="occupancy"') == 2
print('Target:', runtime['TB_BASE_URL'], before['fqn'])
changed = any(before['descriptor'][key] != value for key, value in new_fields.items())
print('UI update needed:', changed)
if args.apply and changed:
    stamp = datetime.now(timezone(timedelta(hours=7))).strftime('%Y%m%d-%H%M%S')
    backup = ROOT / 'backups/ui' / ('widget-before-occupancy-panel-' + stamp + '.json')
    backup.parent.mkdir(parents=True, exist_ok=True)
    backup.write_text(json.dumps(before, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    payload = copy.deepcopy(before)
    payload['descriptor'].update(new_fields)
    client.post('/api/widgetType', payload)
    after = client.get('/api/widgetType/' + uid(before))
    for key, value in new_fields.items():
        assert after['descriptor'][key] == value
    for key, value in before['descriptor'].items():
        if key not in new_fields:
            assert after['descriptor'][key] == value, 'Unexpected change to ' + key
    export_path.write_text(json.dumps(after, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Saved and verified widget UI. Controller, firmware and counters unchanged.')
    print('Rollback copy:', backup.relative_to(ROOT))
elif not args.apply:
    print('Read-only check complete. Use --apply to save.')
