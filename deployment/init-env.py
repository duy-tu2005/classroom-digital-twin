"""Generate private deployment config; never overwrite an existing .env."""
import argparse
import secrets
from pathlib import Path
parser = argparse.ArgumentParser()
parser.add_argument('--host',default='localhost')
args = parser.parse_args()
root = Path(__file__).resolve().parent
path = root/'.env'
if path.exists(): print('[env] Existing .env kept')
else:
    text = (root/'.env.example').read_text(encoding='utf-8').replace('YOUR_SERVER_IP',args.host)
    for key in ['POSTGRES_PASSWORD','TB_PASSWORD','TB_SYSADMIN_PASSWORD']:
        text = text.replace(key+'=CHANGE_ME',key+'='+secrets.token_urlsafe(24))
    path.write_text(text,encoding='utf-8',newline='\n');path.chmod(0o600)
    print('[env] Created private deployment/.env with random passwords')

