"""HTTP-Client und Zeitsteuerung ausschließlich für isolierte Testdaten/Sitzungen."""
import http.cookiejar
import json
import os
from pathlib import Path
import subprocess
import urllib.error
import urllib.request

BASE = 'http://127.0.0.1:8790/api/?action='
PW = 'Sicheres-Passwort-1'


class Client:
    def __init__(self, ip='127.0.0.1'):
        self.cookies = http.cookiejar.CookieJar()
        self.http = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))
        self.csrf = ''
        self.ip = ip

    def call(self, action, data=None, csrf=None):
        headers = {'X-Forwarded-For': self.ip, 'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf if csrf is None else csrf}
        req = urllib.request.Request(BASE + action, data=None if data is None else json.dumps(data).encode(), headers=headers)
        try:
            response = self.http.open(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        result = json.loads(response.read())
        if result.get('csrf'):
            self.csrf = result['csrf']
        return response.code, result

    def login(self, username='admin', password=PW):
        return self.call('login', {'username': username, 'password': password})

    def expire(self):
        sid = next(c.value for c in self.cookies if c.name == 'WA_ADMIN')
        expire_session(sid)


def expire_session(sid):
    # Simuliert Zeitablauf in der getrennten PHP-Sitzungsablage, ohne Produktions-Testendpunkt.
    subprocess.run(['php', '-d', 'session.save_path=' + os.environ['WA_SESSION_DIR'], '-r',
                    'session_id($argv[1]); session_start(); $_SESSION["adminConfirmedAt"] = time() - 301; session_write_close();', sid], check=True)


def read_users():
    return json.loads((Path(os.environ['UDATA']) / 'nutzer.php').read_text().split('\n', 1)[1])


def expire_confirmation_lock():
    path = Path(os.environ['UDATA']) / 'nutzer.php'
    guard = path.read_text().split('\n', 1)[0] + '\n'
    data = read_users()
    for u in data['users']:
        u['confirmUntil'] = 1
    path.write_text(guard + json.dumps(data))
