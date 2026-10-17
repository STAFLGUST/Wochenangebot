"""HTTP-Client mit eigener Sitzung für API-Tests (IP über X-Forwarded-For, wie hinter dem eigenen Proxy)."""
import http.cookiejar
import json
import urllib.error
import urllib.request

B = 'http://127.0.0.1:8790'
API = B + '/api/?action='


class Client:
    def __init__(self, ip='198.51.100.1'):
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ''
        self.ip = ip

    def call(self, action, data=None, raw=False):
        headers = {'X-Forwarded-For': self.ip, 'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf}
        req = urllib.request.Request(API + action, data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            r = self.http.open(req)
        except urllib.error.HTTPError as e:
            r = e
        body = r.read()
        try:
            j = json.loads(body)
        except ValueError:
            j = {}
        if isinstance(j, dict) and j.get('csrf'):
            self.csrf = j['csrf']
        return (r.code, j, body.decode('utf-8', 'replace')) if raw else (r.code, j)
