"""Rename the deployed classroom in place. Never provisions or resets a device."""
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


def rename_labels(value):
    """Change human-readable labels only, not IDs, FQNs or base64 scene images."""
    if isinstance(value, list):
        return [rename_labels(item) for item in value]
    if isinstance(value, dict):
        return {key: item.replace('A101', 'A302') if key in {'name','title','label','alias'} and isinstance(item,str)
                else rename_labels(item) for key,item in value.items()}
    return value


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    runtime = env_file(ROOT / '.env.local')
    config = env_file(ROOT / 'deployment/.env')
    client = Client(runtime['TB_BASE_URL'], config['TB_USERNAME'], config['TB_PASSWORD'])
    widget_stub = client.get('/api/widgetType', {'fqn':'tenant.classroom_a101_scene'})
    paths = {
        'asset': '/api/asset/' + runtime['TB_ASSET_ID'],
        'dashboard': '/api/dashboard/' + runtime['TB_DASHBOARD_ID'],
        'rule-chain': '/api/ruleChain/' + runtime['TB_RULE_CHAIN_ID'],
        'rule-chain-metadata': '/api/ruleChain/' + runtime['TB_RULE_CHAIN_ID'] + '/metadata',
        'widget-classroom': '/api/widgetType/' + uid(widget_stub),
    }
    before = {key:client.get(path) for key,path in paths.items()}
    desired = {key:rename_labels(copy.deepcopy(value)) for key,value in before.items()}
    desired['asset'].update(name='Classroom_A302', label='Classroom A302')
    desired['dashboard']['title'] = 'Classroom A302 - Digital Twin'
    desired['rule-chain']['name'] = 'Classroom A302 - Digital Twin Processing'
    desired['widget-classroom']['name'] = 'Classroom A302 - Interactive Twin'
    source = ROOT / 'thingsboard/widgets'
    html = (source / 'classroom.html').read_text(encoding='utf-8').replace('__CLASSROOM_IMAGE__','data:,')
    old_export = json.loads((ROOT / 'thingsboard/exports/widget-classroom.json').read_text(encoding='utf-8'))
    live_descriptor = before['widget-classroom']['descriptor']
    assert live_descriptor['templateHtml'] in (old_export['descriptor']['templateHtml'], html), 'Live HTML contains an unreviewed edit.'
    assert live_descriptor['controllerScript'] == (source / 'classroom.js').read_text(encoding='utf-8')
    assert live_descriptor['templateCss'] == (source / 'classroom.css').read_text(encoding='utf-8')
    desired['widget-classroom']['descriptor']['templateHtml'] = html
    dashboard_widgets = before['dashboard']['configuration']['widgets']
    for widget_id, widget in dashboard_widgets.items():
        after = desired['dashboard']['configuration']['widgets'][widget_id]
        assert after['id'] == widget['id']
        assert after['typeFullFqn'] == widget['typeFullFqn']
        settings = widget.get('config',{}).get('settings',{})
        new_settings = after.get('config',{}).get('settings',{})
        for key in ['deviceId','sceneImage','sceneLighting']:
            assert settings.get(key) == new_settings.get(key)
    assert desired['rule-chain-metadata']['connections'] == before['rule-chain-metadata']['connections']
    for old, new in zip(before['rule-chain-metadata']['nodes'], desired['rule-chain-metadata']['nodes']):
        assert old['id'] == new['id'] and old['configuration'] == new['configuration']
    changes = [key for key in paths if before[key] != desired[key]]
    print('Server:', runtime['TB_BASE_URL'])
    print('Rename in place:', ', '.join(changes) or 'already A302')
    print('Dashboard ID:', runtime['TB_DASHBOARD_ID'])
    if not args.apply:
        print('Read-only plan. Use --apply to save.')
        return
    stamp = datetime.now(timezone(timedelta(hours=7))).strftime('%Y%m%d-%H%M%S')
    if changes:
        backup = ROOT / 'backups/ui' / ('before-rename-a302-' + stamp)
        backup.mkdir(parents=True, exist_ok=False)
        for key in paths:
            write_json(backup / (key + '.json'), before[key])
        print('Backup:', backup.relative_to(ROOT))
    save_paths = {'asset':'/api/asset', 'dashboard':'/api/dashboard', 'rule-chain':'/api/ruleChain',
                  'rule-chain-metadata':'/api/ruleChain/metadata', 'widget-classroom':'/api/widgetType'}
    for key in ['asset','rule-chain','rule-chain-metadata','widget-classroom','dashboard']:
        if key in changes:
            payload = desired[key]
            if key == 'rule-chain-metadata':
                # Updating the chain name increments its version. Re-read its
                # metadata rather than sending our now-stale version number.
                current = client.get(paths[key])
                assert current['connections'] == before[key]['connections']
                assert len(current['nodes']) == len(before[key]['nodes'])
                for old,new in zip(before[key]['nodes'],current['nodes']):
                    assert old['id'] == new['id'] and old['configuration'] == new['configuration']
                payload = rename_labels(current)
            client.post(save_paths[key], payload)
    final = {key:client.get(path) for key,path in paths.items()}
    for key in ['asset','dashboard','rule-chain','widget-classroom']:
        assert uid(final[key]) == uid(before[key]), 'An entity ID changed.'
    assert final['asset']['name'] == 'Classroom_A302'
    assert final['asset']['label'] == 'Classroom A302'
    assert final['dashboard']['title'] == 'Classroom A302 - Digital Twin'
    assert final['dashboard']['configuration'] == desired['dashboard']['configuration']
    assert final['rule-chain']['name'] == desired['rule-chain']['name']
    assert final['widget-classroom']['descriptor'] == desired['widget-classroom']['descriptor']
    meta = final['rule-chain-metadata']
    assert meta['connections'] == before['rule-chain-metadata']['connections']
    for old,new in zip(desired['rule-chain-metadata']['nodes'],meta['nodes']):
        for field in ['id','name','type','configuration']:
            assert old[field] == new[field], 'Unexpected rule node change: ' + field
    for key,value in final.items():
        write_json(ROOT / 'thingsboard/exports' / (key + '.json'), value)
    print('PASS A302: IDs, dashboard bindings, scene image, controller and rule logic preserved.')


if __name__ == '__main__':
    main()
