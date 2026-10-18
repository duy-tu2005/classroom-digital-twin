"""Check staged source for private file paths and known local credentials.

Prints locations only, never credential values. Run before committing/pushing.
This is a guard for this project's known credentials, not a complete secret scanner.
"""
from pathlib import Path
import re
import subprocess
import sys
import json

ROOT = Path(__file__).resolve().parent.parent

def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT)

paths = [p.decode('utf-8') for p in git('diff', '--cached', '--name-only', '-z', '--diff-filter=ACM').split(b'\0') if p]
private_values = set()
credential_sources = {}
for relative in ['.env.local', 'deployment/.env', 'firmware/secrets.h', '.wokwi-ci-token.private']:
    source = ROOT / relative
    if not source.is_file():
        continue
    content = source.read_text(encoding='utf-8-sig')
    if relative.endswith('.private'):
        if len(content.strip()) >= 8:
            private_values.add(content.strip())
        continue
    for line in content.splitlines():
        if re.search(r'PASSWORD|TOKEN|PRIVATE_KEY|ACCESS_KEY|SECRET', line, re.I):
            match = re.search(r'=\s*(.*?)\s*;?\s*$', line)
            if match:
                value = match.group(1).rstrip(';').strip().strip('"\'')
                # Public factory bootstrap password, already documented by the
                # platform; not the generated administrator/tenant password.
                if line.split('=', 1)[0].strip() == 'TB_SYSADMIN_INITIAL_PASSWORD' and value == 'sysadmin':
                    continue
                if len(value) >= 8 and not value.startswith(('YOUR_', 'CHANGE_ME')):
                    private_values.add(value)
                    credential_sources[value] = relative + ':' + line.split('=', 1)[0].strip()

patterns = {
    'private key block': re.compile(rb'-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----'),
    'GitHub access token': re.compile(rb'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b'),
    'AWS access key ID': re.compile(rb'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'JWT-shaped value': re.compile(rb'\beyJ[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\.[A-Za-z0-9_-]{15,}\b'),
}
issues = []
total = 0
for name in paths:
    p = Path(name)
    if (p.name == 'secrets.h' or p.name in ['.env', '.env.local', '.wokwi-ci-token.private']
            or p.suffix.lower() in ['.pem', '.key', '.zip', '.dump', '.sql', '.pfx']
            or any(part in ['backups', '.pio', '.runtime', 'report'] for part in p.parts)):
        issues.append({'file': name, 'kind': 'private/generated file path'})
    blob = git('show', ':' + name)
    total += len(blob)
    if p.suffix.lower() in ['.png', '.jpg', '.jpeg', '.webp']:
        continue
    for secret in private_values:
        if secret.encode('utf-8') in blob:
            issues.append({'file': name, 'kind': 'contains a known local credential',
                           'credentialSource': credential_sources.get(secret, 'private token file')})
            break
    for label, pattern in patterns.items():
        if pattern.search(blob):
            issues.append({'file': name, 'kind': label})

print(json.dumps({'stagedFiles': len(paths), 'stagedBytes': total,
                  'knownCredentialValuesChecked': len(private_values), 'issues': issues}, ensure_ascii=False))
sys.exit(1 if issues else 0)
