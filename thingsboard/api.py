"""Small dependency-free ThingsBoard CE REST client."""
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


def env_file(path):
    result = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
            if '=' in line and not line.strip().startswith('#'):
                key, value = line.split('=', 1)
                result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def eid(kind, value):
    return {'entityType': kind, 'id': value}


def uid(entity):
    return entity['id']['id'] if isinstance(entity['id'], dict) else entity['id']


class Client:
    def __init__(self, url, username=None, password=None, api_key=None):
        self.url = url.rstrip('/')
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        self.auth = 'ApiKey ' + api_key if api_key else None
        if not self.auth and username:
            self.auth = 'Bearer ' + self.request('POST', '/api/auth/login', {'username': username, 'password': password})['token']

    def request(self, method, path, body=None, query=None, accept='application/json'):
        target = self.url + path
        if query: target += '?' + urllib.parse.urlencode(query)
        headers = {'Accept': accept}
        if self.auth: headers['X-Authorization'] = self.auth
        payload = None if body is None else json.dumps(body).encode('utf-8')
        if payload is not None: headers['Content-Type'] = 'application/json'
        req = urllib.request.Request(target, data=payload, headers=headers, method=method)
        try:
            with self.opener.open(req, timeout=90) as response:
                raw = response.read()
                if not raw: return None
                if 'json' in response.headers.get('Content-Type', ''): return json.loads(raw)
                return raw.decode('utf-8')
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'{method} {path}: HTTP {exc.code}: {exc.read().decode("utf-8", errors="replace")}') from exc

    def get(self, path, query=None): return self.request('GET', path, query=query)
    def post(self, path, body, query=None): return self.request('POST', path, body, query)
    def pages(self, path, **query):
        result, page = [], 0
        while True:
            data = self.get(path, dict(pageSize=100, page=page, **query))
            result.extend(data.get('data', []))
            if not data.get('hasNext'): return result
            page += 1


def provision(url, username, password, system_user, system_password, title, initial_password=None):
    used_password = system_password
    try: system = Client(url, system_user, system_password)
    except RuntimeError:
        if not initial_password: raise
        system = Client(url, system_user, initial_password)
        used_password = initial_password
    if system.get('/api/auth/user')['authority'] != 'SYS_ADMIN': raise RuntimeError('SYS_ADMIN required for tenant provisioning')
    tenants = system.pages('/api/tenants')
    tenant = next((t for t in tenants if t.get('title') == title), None)
    if not tenant: tenant = system.post('/api/tenant', {'title': title, 'region': 'Global', 'country': 'Vietnam'})
    tenant_id = uid(tenant)
    users = system.pages('/api/tenant/' + tenant_id + '/users')
    user = next((u for u in users if u.get('email') == username), None)
    if not user:
        user = system.post('/api/user', {'tenantId': eid('TENANT', tenant_id), 'authority':'TENANT_ADMIN',
            'email':username, 'firstName':'Classroom', 'lastName':'Digital Twin'}, {'sendActivationMail':'false'})
    try: link = system.request('GET', '/api/user/' + uid(user) + '/activationLink', accept='text/plain')
    except RuntimeError as exc:
        if 'already activated' in str(exc).lower(): link = None
        else: raise
    if link:
        token = urllib.parse.parse_qs(urllib.parse.urlsplit(link).query)['activateToken'][0]
        Client(url).post('/api/noauth/activate', {'activateToken':token, 'password':password})
    if used_password != system_password:
        system.post('/api/auth/changePassword', {'currentPassword':used_password,'newPassword':system_password})


def wait(url, seconds=300):
    deadline = time.monotonic() + seconds
    probe = Client(url)
    while time.monotonic() < deadline:
        try: probe.request('GET', '/', accept='text/html'); return
        except (RuntimeError, OSError): time.sleep(2)
    raise RuntimeError('ThingsBoard HTTP endpoint did not become ready')
