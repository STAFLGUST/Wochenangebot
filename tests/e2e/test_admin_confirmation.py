"""Sensible Aktionen, kontoweite Bestätigungsbremse und Dateisperren über echte HTTP-Anfragen."""
import concurrent.futures
import fcntl
import json
import os
from pathlib import Path
import sys
import time
from auth_helpers import Client, PW, read_users, expire_confirmation_lock
from umgebung import storage_docs, storage_lock, storage_sqlite

results = []
def check(name, condition):
    results.append(bool(condition))
    print(('PASS ' if condition else 'FAIL ') + name)

anon = Client()
check('anonymous reauth denied', anon.call('reauth', {'password': PW})[0] == 401)
check('reauth requires POST', anon.call('reauth')[0] == 405)
a, b = Client(), Client('192.0.2.2')
check('admin login works', a.login()[0] == 200 and b.login()[0] == 200)
uid = a.call('status')[1]['user']['id']
check('reauth requires CSRF', a.call('reauth', {'password': PW}, csrf='wrong')[0] == 403)
viewer_body = {'username': 'viewer', 'name': 'Test Viewer', 'role': 'viewer', 'active': True, 'password': 'Leser-Geheimnis-123', 'mustChange': False}
check('fresh login permits admin action', a.call('user_save', viewer_body)[0] == 200)
v = Client('192.0.2.3'); v.login('viewer', 'Leser-Geheimnis-123')
check('viewer cannot reauthenticate as admin', v.call('reauth', {'password': 'Leser-Geheimnis-123'})[0] == 403)
a.expire(); b.expire()
data_dir = Path(os.environ['UDATA'])
def snapshot():
    return {k: v for k, v in storage_docs().items() if k != 'sitzungen'}
before = snapshot()
for action in ['user_save', 'user_delete', 'security_save', 'session_end', 'ip_unblock', 'user_unlock', 'geo_update', 'geo_clear_stats', 'kunde_save', 'kunde_delete', 'mail_konto_save', 'mail_save', 'bestell_settings_save', 'mail_test', 'kunde_mail', 'kunden_rundmail']:
    status, response = a.call(action, {})
    check(action + ' requires recent confirmation', status == 403 and response.get('code') == 'confirmation_required')
check('blocked requests have no business-data side effects', snapshot() == before)
check('reading still works after expiry', a.call('users')[0] == 200 and a.call('draft')[0] == 200)
check('wrong confirmation rejected', a.call('reauth', {'password': 'Wrong-Confirmation-123'})[0] == 422)
check('wrong confirmation grants no permission', a.call('geo_clear_stats', {})[0] == 403)
check('correct confirmation accepted', a.call('reauth', {'password': PW})[0] == 200)
check('confirmed action succeeds', a.call('geo_clear_stats', {})[0] == 200)
check('confirmation is session scoped', b.call('geo_clear_stats', {})[0] == 403)
a.expire()
check('permission expires again', a.call('geo_clear_stats', {})[0] == 403)
# One shared quota across password change and admin confirmation, across sessions/IPs.
for i in range(5):
    client = a if i % 2 == 0 else b
    action = 'reauth' if i % 2 == 0 else 'change_password'
    payload = {'password': 'Wrong-Confirmation-123', 'current': 'Wrong-Confirmation-123'}
    status, response = client.call(action, payload)
    expected = 429 if i == 4 else (422 if action == 'reauth' else 401)
    check('shared confirmation attempt ' + str(i + 1), status == expected)
check('correct password cannot bypass active lock', b.call('reauth', {'password': PW})[0] == 429)
c = Client('192.0.2.4'); c.login()
check('new login cannot bypass confirmation lock', c.call('geo_clear_stats', {})[0] == 429)
check('locked account can still read', c.call('draft')[0] == 200)
expire_confirmation_lock()
check('confirmation works after lock expiry', a.call('reauth', {'password': PW})[0] == 200)
check('successful confirmation clears failures', not read_users()['users'][0].get('confirmFailures'))
# Session version invalidation: another admin resets this administrator's password.
second = a.call('user_save', {'username': 'second', 'name': 'Second Admin', 'role': 'admin', 'active': True, 'password': 'Weiteres-Geheimnis-123', 'mustChange': False})
check('confirmed admin can create another admin', second[0] == 200)
other_admin = Client('192.0.2.5'); other_admin.login('second', 'Weiteres-Geheimnis-123')
reset = {'id': uid, 'name': 'Administrator', 'role': 'admin', 'active': True, 'password': 'Replacement-Passwort-123', 'mustChange': False}
check('other admin password reset succeeds', other_admin.call('user_save', reset)[0] == 200)
check('password reset invalidates confirmed session', a.call('geo_clear_stats', {})[0] == 401)
check('revoked session cannot reauthenticate', a.call('reauth', {'password': 'Replacement-Passwort-123'})[0] == 401)
# Never continue an authentication write when the file lock cannot be acquired.
if storage_sqlite():
    # SQLite: dauerhaft gehaltene Schreibtransaktion → nach Wartezeit Fehler statt Weiterschreiben
    with storage_lock('nutzer'):
        check('user lock failure fails closed', other_admin.call('reauth', {'password': 'Weiteres-Geheimnis-123'})[0] == 500)
else:
    lock = data_dir / '.nutzer.lock'
    lock.unlink(); lock.mkdir()
    check('user lock failure fails closed', other_admin.call('reauth', {'password': 'Weiteres-Geheimnis-123'})[0] == 500)
    lock.rmdir()
check('confirmation recovers when lock available', other_admin.call('reauth', {'password': 'Weiteres-Geheimnis-123'})[0] == 200)
# attempts_record must participate in the existing logins lock (ip_unblock uses it too).
with concurrent.futures.ThreadPoolExecutor() as pool:
    with storage_lock('logins'):
        task = pool.submit(Client('192.0.2.99').login, 'unknown', 'Wrong-Confirmation-123')
        time.sleep(1)
        check('IP attempt waits for exclusive lock', not task.done())
    check('IP attempt resumes after unlock', task.result()[0] == 401)
logs = '\n'.join(storage_docs('protokoll').values())
check('confirmation success and failure audited', 'reauth_fail' in logs and 'Sensible Verwaltungsaktionen' in logs)
check('audit contains no submitted passwords', all(pw not in logs for pw in [PW, 'Wrong-Confirmation-123', 'Weiteres-Geheimnis-123', 'Replacement-Passwort-123']))
print(f'{sum(results)}/{len(results)} passed')
sys.exit(0 if all(results) else 1)
