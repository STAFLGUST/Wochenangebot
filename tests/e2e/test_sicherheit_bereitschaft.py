"""Bereitschaft im Modul Sicherheit (lib/bereitschaft.php, docs/plattform/modul-sicherheit.md §8).

Geprüft: Leitfaden (Vorlage, Speichern nur Administrator, Prüfung von Schritten und Ansprechpartnern, Vorlage zurück,
Abhaken nur im Notfall und nur mit „Notfall auslösen“, abgehakte Schritte bleiben beim Notfall); Probealarm (Recht wie
Auslösen, keine Wirkung auf Sitzungen, Firewall, Notfall; Bereitschaftsprüfung; Test-Meldung an die Empfänger; Pause
zwischen zwei Probealarmen; nicht im Notfall; „gesehen“ mit Reaktionszeit, nicht für den eigenen, Rechte; ohne
Empfänger vermerkt); Wochenbericht (Ansehen mit „Sicherheit ansehen“, Senden und Einstellen nur Administrator, Inhalt
der E-Mail, automatischer Versand genau einmal je Woche über die Statusabfrage, erster Aufruf ohne Versand, ausgeschaltet
kein Versand, Protokoll); ungenutzte Zugänge (Zeitraum, nie angemeldet, laufende Sitzung zählt nicht, Rechte, Deaktivieren
mit Sitzungsende, nicht der eigene, doppelt 409, Konfigurationsprüfung). Oberfläche: Lagebild (Wochenbericht, Bereitschaft,
Bericht im Dialog), Notfall (Leitfaden bearbeiten, Probealarm in Schritten, Übungen, im Notfall abhaken mit Fortschritt),
Band „Probealarm – gesehen“, Konten (ungenutzte Zugänge, Zeitraum, Deaktivieren im Dialog), hell/dunkel, 1440/390 px,
keine JavaScript-Fehler. Nur synthetische Testdaten.
"""
import datetime
import json
import sys
import time
import zoneinfo

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from order_setup import setup
from umgebung import SH, storage_raw, storage_write, until

PW = 'Sicheres-Passwort-1'
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def doc(name):
    raw = storage_raw(name)
    if not raw:
        return None
    if raw.startswith('<?php'):
        raw = raw.split('\n', 1)[1]
    return json.loads(raw)


def berlin():
    return datetime.datetime.now(zoneinfo.ZoneInfo('Europe/Berlin'))


def woche():
    j, w, _ = berlin().isocalendar()
    return f'{j}-W{w:02d}'


smtp, A, K, K2, kid, payload, nr = setup()
mails = lambda a, t='': [m for m in smtp.messages if a in m['to'] and t in m['subject']]   # noqa: E731
ab7 = berlin().hour >= 7   # automatischer Wochenbericht frühestens ab 7 Uhr (Ortszeit des Servers)

# Erster Statusaufruf eines Mitarbeiters: Woche nur vermerkt, kein Bericht (keine Überraschungs-Mail nach dem Einspielen)
A.call('status')
b0 = (doc('sicherheit-bereitschaft') or {}).get('bericht', {})
check('erster Aufruf: Woche vermerkt (ab 7 Uhr), kein Versand', (b0.get('woche') == woche()) == ab7 and not b0.get('verlauf'), b0)

for u, n, r, p, extra in (('bea', 'Bea Bearbeiterin', 'editor', 'Kollegin-Zugang-3', {}),
                          ('nina', 'Nina Notfall', 'editor', 'Notfall-Zugang-7', {'grant': ['sicherheit.notfall']}),
                          ('sven', 'Sven Sicht', 'viewer', 'Leser-Zugang-55', {'grant': ['sicherheit.sehen']}),
                          ('olga', 'Olga Alt', 'editor', 'Alter-Zugang-44', {}),
                          ('otto', 'Otto Selten', 'viewer', 'Seltener-Zugang-8', {})):
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
Be = Client('198.51.100.11'); Ni = Client('198.51.100.12'); Sv = Client('198.51.100.13')
check('Anmeldungen der Testkonten', all(c.call('login', {'username': u, 'password': p})[0] == 200 for c, u, p in (
    (Be, 'bea', 'Kollegin-Zugang-3'), (Ni, 'nina', 'Notfall-Zugang-7'), (Sv, 'sven', 'Leser-Zugang-55'))))
P = Client('198.51.100.20')

# ── Rechte ──
for name, c, erwartet in (('Bearbeiterin ohne Recht', Be, 403), ('anonym', P, 401)):
    check(f'{name}: Probealarm, gesehen, Leitfaden, Bericht, Konten gesperrt ({erwartet})', all(x == erwartet for x in (
        c.call('sicherheit_probealarm', {})[0], c.call('sicherheit_probe_gesehen', {'id': 'x'})[0], c.call('sicherheit_leitfaden', {'schritte': []})[0],
        c.call('sicherheit_bericht')[0], c.call('sicherheit_bericht_senden', {})[0], c.call('sicherheit_konto_deaktivieren', {'id': 'x'})[0])))
check('„Sicherheit ansehen“: Bericht ja; Probealarm, Leitfaden, Senden, Einstellen, Konten, Deaktivieren nein',
      Sv.call('sicherheit_bericht')[0] == 200 and all(Sv.call(a, b)[0] == 403 for a, b in (
          ('sicherheit_probealarm', {}), ('sicherheit_leitfaden', {'standard': True}), ('sicherheit_bericht_senden', {}),
          ('sicherheit_bericht_einstellen', {'an': False, 'tag': 1}), ('sicherheit_konto_deaktivieren', {'id': 'x'}), ('sicherheit_leitfaden_haken', {'schritt': 'lage'}))))
check('„Notfall auslösen“: kein Bericht, kein Leitfaden-Speichern', Ni.call('sicherheit_bericht')[0] == 403 and Ni.call('sicherheit_leitfaden', {'standard': True})[0] == 403)
check('Konten (ungenutzte) nur Administrator', Sv.call('sicherheit_konten')[0] == 403 and Ni.call('sicherheit_konten')[0] == 403)

# ── Leitfaden ──
st, r = Sv.call('sicherheit_lage')
L = r.get('leitfaden', {})
check('Leitfaden: Vorlage mit 8 Schritten, keine Ansprechpartner, für „Sicherheit ansehen“ sichtbar',
      st == 200 and L.get('standard') is True and len(L.get('schritte', [])) == 8 and L.get('kontakte') == [] and L['schritte'][0]['id'] == 'ausloesen', L)
check('Leitfaden: Vorlage enthält Meldepflicht (72 Stunden)', any('72 Stunden' in s['text'] for s in L.get('schritte', [])))
st, r = Ni.call('sicherheit_lage')
check('„Notfall auslösen“ sieht Leitfaden und Übungen', st == 200 and len(r['leitfaden']['schritte']) == 8 and 'proben' in r)
for fall, body, text in (
        ('Ansprechpartner ohne Telefon und E-Mail', {'standard': True, 'kontakte': [{'name': 'Max Muster'}]}, 'Telefon oder E-Mail'),
        ('ungültige E-Mail', {'standard': True, 'kontakte': [{'name': 'Max', 'email': 'kein-at'}]}, 'E-Mail'),
        ('ungültige Telefonnummer', {'standard': True, 'kontakte': [{'name': 'Max', 'telefon': '<b>'}]}, 'Telefon'),
        ('Ansprechpartner ohne Name und Aufgabe', {'standard': True, 'kontakte': [{'telefon': '0400 123'}]}, 'Name oder Aufgabe'),
        ('Schritt ohne Überschrift', {'schritte': [{'titel': '', 'text': 'nur Text'}]}, 'Überschrift'),
        ('keine Schritte', {'schritte': []}, 'mindestens einen Schritt'),
        ('zu viele Schritte', {'schritte': [{'titel': f'Schritt {i}'} for i in range(16)]}, 'Höchstens 15')):
    st, r = A.call('sicherheit_leitfaden', body)
    check(f'Leitfaden: {fall} → 422', st == 422 and text in r.get('error', ''), (st, r))
schritte = [{'id': 'ausloesen', 'titel': 'Notfall auslösen', 'text': 'Sofort.'}, {'titel': 'Firma Muster IT anrufen', 'text': 'Rufbereitschaft.'},
            {'id': 'ausloesen', 'titel': 'Doppelte Kennung', 'text': ''}]
kontakte = [{'rolle': 'IT-Dienstleister', 'name': 'Muster IT', 'telefon': '+49 (0) 40 123-456', 'email': 'notfall@example.org'},
            {'rolle': 'Geschäftsführung', 'name': '', 'telefon': '0171 000000', 'email': ''}, {'rolle': '', 'name': '', 'telefon': '', 'email': ''}]
st, r = A.call('sicherheit_leitfaden', {'schritte': schritte, 'kontakte': kontakte, 'hinweis': 'Ordner „Notfall“ im Büro.'})
L = r.get('leitfaden', {})
ids = [s['id'] for s in L.get('schritte', [])]
check('Leitfaden gespeichert: eigene Schritte, Kennungen eindeutig, leere Zeilen ignoriert', st == 200 and L['standard'] is False and len(ids) == 3
      and ids[0] == 'ausloesen' and len(set(ids)) == 3 and len(L['kontakte']) == 2 and L['hinweis'] == 'Ordner „Notfall“ im Büro.' and L['von'] == 'Administrator', (st, L))
check('Leitfaden im Protokoll (Vorgang Notfall, ohne Benachrichtigung)', any(e['s'] == 'Notfall-Leitfaden geändert' for e in A.call('sicherheit_ereignisse&art=notfall')[1]['ereignisse']))
st, r = A.call('sicherheit_leitfaden_haken', {'schritt': 'ausloesen', 'erledigt': True})
check('Abhaken außerhalb eines Notfalls: 409', st == 409, (st, r))

# ── Probealarm ──
st, r = A.call('sicherheit_probealarm', {})
p0 = r.get('probe', {})
k = {x['k']: x for x in p0.get('punkte', [])}
check('Probealarm ohne Empfänger: ausgeführt, Meldung als Lücke vermerkt', st == 200 and k.get('meldung', {}).get('stufe') == 'bad'
      and p0['mail'] == {'an': 0, 'ok': 0, 'fehler': 'keine Empfänger eingetragen'}, (st, r))
check('Bereitschaftsprüfung: alle Prüfpunkte', set(k) == {'meldung', 'ausloeser', 'beender', 'zweifaktor', 'kontakte', 'selbstsperre', 'sicherung', 'zentral'}, sorted(k))
check('Prüfpunkte: Auslösen (2 Personen) ok, Beenden (1 Administrator) Hinweis, Ansprechpartner ok, zentrale Anmeldung nur Info',
      k['ausloeser']['stufe'] == 'ok' and k['beender']['stufe'] == 'warn' and k['kontakte']['stufe'] == 'ok' and k['zentral']['stufe'] == 'info'
      and p0['gesamt'] == 7, {x: k[x]['stufe'] for x in k})
st, r = Ni.call('sicherheit_probealarm', {})
check('zweiter Probealarm innerhalb von 5 Minuten: 429', st == 429, (st, r))
# Pause nachstellen (erster Probealarm 10 Minuten früher), Empfänger eintragen
d = doc('sicherheit-bereitschaft'); d['proben'][0]['t'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 600)); storage_write('sicherheit-bereitschaft', d)
check('Benachrichtigung „Sicherheitsereignisse“ an it@ eingerichtet', A.call('benachrichtigung_save', {'events': {'sicherheit': {'on': True, 'to': 'it@example.org, chef@example.org'}}})[0] == 200)
fw_vorher = doc('firewall'); sitz_vorher = len(doc('sitzungen') or {})
vor = len(smtp.messages)
st, r = Ni.call('sicherheit_probealarm', {})
p1 = r.get('probe', {})
check('Probealarm durch Mitarbeiterin mit „Notfall auslösen“', st == 200 and p1.get('vonName') == 'Nina Notfall' and p1['mail']['an'] == 2 and p1['mail']['ok'] == 2, (st, p1.get('mail')))
check('… Meldung ok, Bereitschaft gezählt', {x['k']: x['stufe'] for x in p1['punkte']}['meldung'] == 'ok' and p1['ok'] == sum(1 for x in p1['punkte'] if x['stufe'] == 'ok'))
until(lambda: len(mails('it@example.org', 'PROBEALARM')) >= 1, 10)
m = (mails('it@example.org', 'PROBEALARM') or [None])[0]
check('Test-Meldung: Betreff „PROBEALARM (Übung) – keine Wirkung“, Bitte um Bestätigung, Link zur Sicherheitszentrale',
      m and 'keine Wirkung' in m['subject'] and 'Probealarm gesehen' in m['text'] and 'Nina Notfall' in m['text']
      and 'sicherheit.dashboard-stafl.de/module/sicherheit/#notfall' in m['text'], m and (m['subject'], m['text'][:600]))
check('… an beide Empfänger, je einmal', len(mails('chef@example.org', 'PROBEALARM')) == 1 and len(mails('it@example.org', 'PROBEALARM')) == 1)
check('keine Wirkung: kein Notfall, Firewall unverändert, keine Sitzung beendet, Bearbeiterin arbeitet weiter',
      not (doc('sicherheit-notfall') or {}).get('aktiv') and doc('firewall') == fw_vorher and len(doc('sitzungen') or {}) >= sitz_vorher
      and Be.call('stock')[0] == 200 and K.call('kunde_status')[1].get('kunde'))
st, r = Sv.call('sicherheit_lage')
check('offener Probealarm für „Sicherheit ansehen“ (nicht selbst ausgelöst)', st == 200 and (r.get('probeOffen') or {}).get('id') == p1['id'], r.get('probeOffen'))
check('… nicht für die Auslöserin', Ni.call('sicherheit_lage')[1].get('probeOffen') is None)
check('Bearbeiterin ohne Recht kann nicht bestätigen (403)', Be.call('sicherheit_probe_gesehen', {'id': p1['id']})[0] == 403)
check('falsche Kennung: 409', Sv.call('sicherheit_probe_gesehen', {'id': 'abc'})[0] == 409)
check('eigenen Probealarm nicht bestätigen: 409', Ni.call('sicherheit_probe_gesehen', {'id': p1['id']})[0] == 409)
st, r = Sv.call('sicherheit_probe_gesehen', {'id': p1['id']})
q = (r.get('probe') or {}).get('quittiert', [])
check('„gesehen“: Name und Reaktionszeit vermerkt', st == 200 and len(q) == 1 and q[0]['name'] == 'Sven Sicht' and 0 <= q[0]['sek'] < 120, (st, q))
st, r = Sv.call('sicherheit_probe_gesehen', {'id': p1['id']})
check('zweites „gesehen“: kein doppelter Eintrag', st == 200 and len(r['probe']['quittiert']) == 1)
check('danach kein offener Probealarm mehr', Sv.call('sicherheit_lage')[1].get('probeOffen') is None)
st, r = A.call('sicherheit_probe_gesehen', {'id': p1['id']})
check('Administrator bestätigt ebenfalls', st == 200 and len(r['probe']['quittiert']) == 2)
ev = A.call('sicherheit_ereignisse&art=notfall')[1]['ereignisse']
check('Protokoll: Probealarm durchgeführt und gesehen', any(e['s'] == 'Probealarm durchgeführt (Übung ohne Wirkung)' for e in ev) and any(e['s'].startswith('Probealarm gesehen') for e in ev))

# ── Notfall: Leitfaden abhaken ──
d = doc('sicherheit-bereitschaft'); d['proben'][0]['t'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 600)); storage_write('sicherheit-bereitschaft', d)
st, r = Ni.call('sicherheit_notfall_an', {'grund': 'Übungsnotfall im Test', 'wort': 'NOTFALL', 'firewall': False})
check('Notfall ausgelöst (Vorbereitung)', st == 200, (st, r))
# der Notfall beendet die Sitzungen von Mitarbeitern ohne Administratorrolle – neu anmelden (das Modul Sicherheit bleibt erreichbar)
Ni.call('login', {'username': 'nina', 'password': 'Notfall-Zugang-7'}); Sv.call('login', {'username': 'sven', 'password': 'Leser-Zugang-55'})
st, r = Ni.call('sicherheit_probealarm', {})
check('Probealarm während eines Notfalls: 409', st == 409, (st, r))
st, r = Ni.call('sicherheit_leitfaden_haken', {'schritt': ids[1], 'erledigt': True})
check('Schritt abgehakt (Name, Zeit)', st == 200 and r['haken'].get(ids[1], {}).get('name') == 'Nina Notfall', (st, r))
check('unbekannter Schritt: 422', Ni.call('sicherheit_leitfaden_haken', {'schritt': 'gibt-es-nicht', 'erledigt': True})[0] == 422)
check('„Sicherheit ansehen“ hakt nicht ab (403)', Sv.call('sicherheit_leitfaden_haken', {'schritt': ids[0], 'erledigt': True})[0] == 403)
A.call('sicherheit_leitfaden_haken', {'schritt': ids[0], 'erledigt': True})
A.call('sicherheit_leitfaden_haken', {'schritt': ids[2], 'erledigt': True})
st, r = A.call('sicherheit_leitfaden_haken', {'schritt': ids[2], 'erledigt': False})
check('zurücknehmen', st == 200 and set(r['haken']) == {ids[0], ids[1]}, r)
st, r = A.call('sicherheit_lage')
check('Lage im Notfall: abgehakte Schritte am Leitfaden', set(r['leitfaden']['haken']) == {ids[0], ids[1]})
st, r = A.call('sicherheit_notfall_aus', {'notiz': 'Übung beendet'})
check('Notfall beendet', st == 200, (st, r))
st, r = A.call('sicherheit_lage')
v0 = (r.get('verlauf') or [{}])[0]
check('Verlauf: abgehakte Schritte bleiben beim Notfall', set(v0.get('haken', {})) == {ids[0], ids[1]} and not r['leitfaden']['haken'], v0.get('haken'))
check('Anmeldungen nach dem Notfall', Be.call('login', {'username': 'bea', 'password': 'Kollegin-Zugang-3'})[0] == 200)

# ── Wochenbericht ──
st, r = Sv.call('sicherheit_bericht')
Bt = r.get('bericht', {})
check('Bericht: Abschnitte Konfiguration, Anmeldungen, Firewall, Zugänge, Notfall, Betrieb', st == 200
      and [a['k'] for a in Bt.get('abschnitte', [])] == ['gesamt', 'anmeldung', 'firewall', 'konten', 'notfall', 'betrieb'] and Bt.get('stufe') in ('ok', 'warn', 'bad'), Bt)
nf = next(a for a in Bt['abschnitte'] if a['k'] == 'notfall')
check('Bericht: Notfall der Woche und Probealarme aufgeführt', any('Übungsnotfall im Test' in x for x in nf['liste']) and sum(1 for x in nf['liste'] if x.startswith('Probealarm')) == 2, nf)
E = r.get('einstellungen', {})
check('Einstellungen: an, Montag, Empfänger der Sicherheitsereignisse', E.get('an') is True and E.get('tag') == 1 and E.get('empfaenger') == ['it@example.org', 'chef@example.org'], E)
for fall, body in (('Wochentag 0', {'an': True, 'tag': 0}), ('Wochentag 8', {'an': True, 'tag': 8})):
    check(f'Einstellen: {fall} → 422', A.call('sicherheit_bericht_einstellen', body)[0] == 422)
vor = len(mails('it@example.org', 'Sicherheit: Wochenbericht'))
st, r = A.call('sicherheit_bericht_senden', {})
check('jetzt senden: an beide Empfänger', st == 200 and r['versand']['ok'] == 2 and r['versand']['auto'] is False and r['einstellungen']['verlauf'][0]['von'] == 'Administrator', (st, r))
until(lambda: len(mails('it@example.org', 'Sicherheit: Wochenbericht')) > vor, 10)
m = (mails('it@example.org', 'Sicherheit: Wochenbericht') or [None])[-1]
check('E-Mail: Abschnitte, Notfall, Link, kein Passwort', m and all(t in m['text'] for t in ('KONFIGURATIONSPRÜFUNG', 'ANMELDUNGEN', 'FIREWALL', 'ZUGÄNGE', 'NOTFALL UND ÜBUNGEN', 'BETRIEB',
      'Übungsnotfall im Test', 'sicherheit.dashboard-stafl.de/module/sicherheit/#lage')) and 'Sicheres-Passwort' not in m['text'] and '<table' in m['html'], m and m['text'][:900])
# automatischer Versand: Woche zurückstellen → nächste Statusabfrage eines Mitarbeiters sendet genau einmal
d = doc('sicherheit-bereitschaft'); d['bericht']['woche'] = '2020-W01'; storage_write('sicherheit-bereitschaft', d)
vor = len(mails('it@example.org', 'Sicherheit: Wochenbericht'))
Be.call('status'); Sv.call('status')
if ab7:
    until(lambda: len(mails('it@example.org', 'Sicherheit: Wochenbericht')) > vor, 10)
    d = doc('sicherheit-bereitschaft')['bericht']
    check('automatisch: genau ein Bericht, Woche vermerkt, im Verlauf „automatisch“', len(mails('it@example.org', 'Sicherheit: Wochenbericht')) == vor + 1 and d['woche'] == woche()
          and d['verlauf'][0]['auto'] is True and d['verlauf'][0]['ok'] == 2, d)
else:
    check('vor 7 Uhr: kein automatischer Bericht', len(mails('it@example.org', 'Sicherheit: Wochenbericht')) == vor and doc('sicherheit-bereitschaft')['bericht']['woche'] == '2020-W01')
st, r = A.call('sicherheit_bericht_einstellen', {'an': False, 'tag': 3})
check('ausschalten: gespeichert', st == 200 and r['einstellungen']['an'] is False and r['einstellungen']['tag'] == 3 and r['einstellungen']['naechster'] is None, r)
check('… im Protokoll (Sicherheitsereignis)', any(e['s'] == 'Wochenbericht der Sicherheit ausgeschaltet' for e in A.call('sicherheit_ereignisse&art=einstellungen')[1]['ereignisse']))
d = doc('sicherheit-bereitschaft'); d['bericht']['woche'] = '2020-W01'; storage_write('sicherheit-bereitschaft', d)
vor = len(mails('it@example.org', 'Sicherheit: Wochenbericht'))
Be.call('status')
# ein Versand würde vor der Antwort die Woche vermerken (unter Sperre) – unverändert heißt: kein Versand
check('ausgeschaltet: kein automatischer Bericht', len(mails('it@example.org', 'Sicherheit: Wochenbericht')) == vor and doc('sicherheit-bereitschaft')['bericht']['woche'] == '2020-W01')
st, r = A.call('sicherheit_bericht_einstellen', {'an': True, 'tag': 1})
check('wieder einschalten: erster Bericht erst in der nächsten Woche', st == 200 and doc('sicherheit-bereitschaft')['bericht']['woche'] == woche()
      and r['einstellungen']['naechster'] > berlin().isoformat()[:10], doc('sicherheit-bereitschaft')['bericht'])

# ── Ungenutzte Zugänge ──
n = doc('nutzer')
alt = lambda tage: time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - tage * 86400))   # noqa: E731
for u in n['users']:
    if u['username'] == 'olga':
        u['created'] = alt(400); u['lastLogin'] = None
    if u['username'] == 'otto':
        u['created'] = alt(500); u['lastLogin'] = alt(200)
    if u['username'] == 'bea':
        u['lastLogin'] = alt(300)   # alte Anmeldung, aber laufende Sitzung → zählt nicht
storage_write('nutzer', n)
st, r = A.call('sicherheit_konten&tage=90')
U = {x['username']: x for x in r.get('ungenutzt', {}).get('konten', [])}
check('ungenutzt (90 Tage): nie angemeldet und lange nicht angemeldet', st == 200 and U.get('olga', {}).get('nie') is True and U.get('otto', {}).get('tage', 0) >= 199
      and r['ungenutzt']['tage'] == 90 and r['ungenutzt']['wahl'] == [30, 60, 90, 180, 365], sorted(U))
check('… laufende Sitzung zählt nicht (Bea), frisch angemeldete nicht', 'bea' not in U and 'sven' not in U and 'admin' not in U, sorted(U))
check('… älteste zuerst', [x['username'] for x in r['ungenutzt']['konten']][:2] == ['olga', 'otto'], [x['username'] for x in r['ungenutzt']['konten']])
U365 = {x['username'] for x in A.call('sicherheit_konten&tage=365')[1]['ungenutzt']['konten']}
check('365 Tage: Olga (angelegt vor 400 Tagen), nicht Otto (200 Tage)', U365 == {'olga'}, U365)
check('ungültiger Zeitraum: 422', A.call('sicherheit_konten&tage=45')[0] == 422)
cf = {c['title']: c for c in A.call('sicherheit_lage')[1]['lage']['config']}
check('Konfigurationsprüfung: unbenutzte Zugänge als Hinweis', cf['Unbenutzte Zugänge']['level'] == 'warn' and 'olga' in cf['Unbenutzte Zugänge']['text'], cf.get('Unbenutzte Zugänge'))
admin_id = next(u['id'] for u in n['users'] if u['username'] == 'admin')
st, r = A.call('sicherheit_konto_deaktivieren', {'id': admin_id})
check('eigenen Zugang nicht deaktivieren (403)', st == 403, (st, r))
check('unbekannter Zugang: 404', A.call('sicherheit_konto_deaktivieren', {'id': 'u000000000000'})[0] == 404)
bea_id = next(u['id'] for u in n['users'] if u['username'] == 'bea')
st, r = A.call('sicherheit_konto_deaktivieren', {'id': bea_id})
check('Zugang deaktiviert', st == 200 and r['user']['active'] is False and next(u for u in doc('nutzer')['users'] if u['id'] == bea_id)['active'] is False, (st, r))
check('… laufende Sitzung beendet (401)', Be.call('stock')[0] == 401)
check('… Anmeldung nicht mehr möglich', Be.call('login', {'username': 'bea', 'password': 'Kollegin-Zugang-3'})[0] != 200)
check('zweites Deaktivieren: 409', A.call('sicherheit_konto_deaktivieren', {'id': bea_id})[0] == 409)
ev = A.call('sicherheit_ereignisse&art=konten')[1]['ereignisse']
check('Protokoll: deaktiviert mit Grund', any('„bea“ deaktiviert (Sicherheit: ungenutzter Zugang)' in e['s'] for e in ev), [e['s'] for e in ev[:3]])
olga_id = next(u['id'] for u in n['users'] if u['username'] == 'olga')

# ── Oberfläche ──
with sync_playwright() as p:
    br = p.chromium.launch()

    def anmelden(user, pw, ip, breite=1440, thema='light', hoehe=900, hash_=''):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin', color_scheme=thema)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/sicherheit/' + hash_); pg.wait_for_selector('#sic-app:not([hidden])')
        return ctx, pg

    def tab(pg, t):
        pg.click(f'#sic-tabs [data-tab="{t}"]')
        pg.wait_for_selector(f'#tab-{t}:not([hidden]) .sic-block, #tab-{t}:not([hidden]) .sic-held')

    def dialog_zu(pg):
        pg.keyboard.press('Escape'); pg.wait_for_selector('#sic-dlg', state='hidden')

    def breit_ok(pg):
        return pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1')

    ctx, pg = anmelden('admin', PW, '198.51.100.2')
    pg.wait_for_selector('#sic-berichtblock')
    lage = pg.inner_text('#tab-lage')
    check('Lagebild: Wochenbericht und Bereitschaft', all(t in lage for t in ('Wochenbericht', 'jeden Montag', 'it@example.org', 'Bereitschaft für den Ernstfall', 'Letzter Probealarm', 'Muster IT')), lage[-700:])
    pg.click('#tab-lage [data-bericht]'); pg.wait_for_selector('#sic-dlg[open] .br-raster')
    t = pg.inner_text('#sic-dlg')
    check('Dialog Wochenbericht: Abschnitte und „Jetzt senden“', all(x in t for x in ('Sicherheitsbericht', 'Anmeldungen', 'Firewall', 'Zugänge', 'Notfall und Übungen', 'Betrieb')) and pg.is_enabled('#sic-dlg [data-d="senden"]'))
    pg.screenshot(path=f'{SH}/sicherheit_bericht_1440.png')
    dialog_zu(pg)

    tab(pg, 'notfall')
    t = pg.inner_text('#tab-notfall')
    check('Notfall: Leitfaden mit Schritten und Ansprechpartnern, Übungen, Knopf Probealarm', all(x in t for x in ('Leitfaden für den Ernstfall', 'Firma Muster IT anrufen', 'Muster IT', 'Geschäftsführung', 'Übungen'))
          and pg.is_visible('#tab-notfall .sic-held [data-probe-start]') and pg.locator('#tab-notfall a[href^="tel:+4904"]').count() == 1, t[:600])
    pg.screenshot(path=f'{SH}/sicherheit_notfall_bereitschaft_1440.png', full_page=True)
    # Leitfaden bearbeiten: Schritt hinzufügen, nach oben schieben, speichern
    pg.click('#lf-bearbeiten'); pg.wait_for_selector('#sic-dlg[open] #lf-ed-schritte')
    check('Leitfaden-Dialog: Fokus in der ersten Überschrift', pg.evaluate("document.activeElement.classList.contains('lf-ed-titel')"))
    pg.click('#sic-dlg [data-d="s-plus"]')
    pg.fill('#lf-ed-schritte .lf-ed-zeile:last-child .lf-ed-titel', 'Neuer Schritt aus der Oberfläche')
    pg.click('#lf-ed-schritte .lf-ed-zeile:last-child [data-d="hoch"]')
    check('Schritt nach oben verschoben', pg.input_value('#lf-ed-schritte .lf-ed-zeile:nth-child(3) .lf-ed-titel') == 'Neuer Schritt aus der Oberfläche')
    pg.screenshot(path=f'{SH}/sicherheit_leitfaden_dialog_1440.png')
    pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg', state='hidden')
    pg.wait_for_function("document.querySelector('#sic-leitfaden').textContent.includes('Neuer Schritt aus der Oberfläche')")
    check('Leitfaden gespeichert: 4 Schritte, neuer an Stelle 3', [s['titel'] for s in doc('sicherheit-bereitschaft')['leitfaden']['schritte']][2] == 'Neuer Schritt aus der Oberfläche'
          and len(doc('sicherheit-bereitschaft')['leitfaden']['schritte']) == 4)
    # Probealarm über die Oberfläche (Pause nachstellen)
    d = doc('sicherheit-bereitschaft'); d['proben'][0]['t'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 600)); storage_write('sicherheit-bereitschaft', d)
    pg.click('#tab-notfall .sic-held [data-probe-start]'); pg.wait_for_selector('#sic-dlg[open] .sic-wirkungen.uebung')
    check('Probealarm Schritt 1: Erklärung „ohne jede Wirkung“', 'ohne jede Wirkung' in pg.inner_text('#sic-dlg'))
    pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg[open] .pb-punkte')
    t = pg.inner_text('#sic-dlg')
    check('Probealarm Ergebnis: Bereitschaft, Prüfpunkte, Meldung zugestellt', 'Probealarm ausgeführt' in t and 'Test-Meldung an 2 Empfänger zugestellt' in t and 'Wer den Notfall beenden kann' in t, t[:400])
    pg.screenshot(path=f'{SH}/sicherheit_probealarm_1440.png')
    dialog_zu(pg)
    pg.wait_for_function("document.querySelectorAll('#tab-notfall [data-probe]').length === 3")
    pg.click('#tab-notfall [data-probe="0"]'); pg.wait_for_selector('#sic-dlg[open] .pb-punkte')
    check('Übung im Verlauf: Details im Dialog', 'Gesehen' in pg.inner_text('#sic-dlg'))
    dialog_zu(pg)

    # Band „Probealarm“ bei einer anderen Person (Sicherheit ansehen), 390 px
    ctx2, ps = anmelden('sven', 'Leser-Zugang-55', '198.51.100.13', breite=390, hoehe=844)
    ps.wait_for_selector('#sic-probeband:not([hidden])')
    check('Band „Probealarm – Übung ohne Wirkung“ mit „Gesehen“', 'Übung ohne Wirkung' in ps.inner_text('#sic-probeband') and ps.is_visible('#probe-gesehen'))
    check('390 px: kein waagerechtes Scrollen (Lagebild)', breit_ok(ps))
    ps.screenshot(path=f'{SH}/sicherheit_probeband_390.png')
    ps.click('#probe-gesehen'); ps.wait_for_selector('#sic-probeband', state='hidden')
    check('gesehen: Band weg, vermerkt', any(q['name'] == 'Sven Sicht' for q in doc('sicherheit-bereitschaft')['proben'][0]['quittiert']))
    tab(ps, 'notfall')
    check('„Sicherheit ansehen“: Leitfaden ohne Bearbeiten, Übungen ohne Probealarm-Knopf', ps.is_visible('#sic-leitfaden') and ps.locator('#lf-bearbeiten').count() == 0
          and ps.locator('#tab-notfall [data-probe-start]').count() == 0)
    check('390 px: kein waagerechtes Scrollen (Notfall)', breit_ok(ps))
    ps.screenshot(path=f'{SH}/sicherheit_notfall_bereitschaft_390.png', full_page=True)
    ctx2.close()

    # Im Notfall: Leitfaden oben, abhaken mit Fortschritt
    d = doc('sicherheit-bereitschaft'); d['proben'][0]['t'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 600)); storage_write('sicherheit-bereitschaft', d)
    st, r = Ni.call('sicherheit_notfall_an', {'grund': 'Zweiter Übungsnotfall', 'wort': 'NOTFALL', 'firewall': False})
    assert st == 200, r
    pg.reload(); pg.wait_for_selector('#tab-notfall .sic-held.aktiv')
    check('Notfall aktiv: Leitfaden direkt unter dem Kopf, Fortschritt 0 von 4', pg.evaluate("document.querySelector('#tab-notfall .sic-held').nextElementSibling.id") == 'sic-leitfaden'
          and '0 von 4 Schritten erledigt' in pg.inner_text('#sic-leitfaden'))
    pg.click('#sic-leitfaden [data-lf="ausloesen"]')
    pg.wait_for_function("document.querySelector('#sic-leitfaden').textContent.includes('1 von 4')")
    check('abgehakt: Schritt erledigt, Name, Fokus bleibt', pg.get_attribute('#sic-leitfaden [data-lf="ausloesen"]', 'aria-pressed') == 'true' and 'Administrator' in pg.inner_text('#sic-leitfaden .lf-schritt.erledigt')
          and pg.evaluate("document.activeElement.dataset.lf") == 'ausloesen')
    pg.screenshot(path=f'{SH}/sicherheit_leitfaden_notfall_1440.png', full_page=True)
    pg.click('#sic-leitfaden [data-lf="ausloesen"]'); pg.wait_for_function("document.querySelector('#sic-leitfaden').textContent.includes('0 von 4')")
    pg.click('#sic-leitfaden [data-lf="ausloesen"]'); pg.wait_for_function("document.querySelector('#sic-leitfaden').textContent.includes('1 von 4')")
    check('Probealarm im Notfall nicht angeboten', pg.locator('#tab-notfall [data-probe-start]').count() == 0)
    A.call('sicherheit_notfall_aus', {})
    pg.reload(); pg.wait_for_selector('#tab-notfall .sic-held:not(.aktiv)')
    pg.click('#tab-notfall [data-nfv="0"]'); pg.wait_for_selector('#sic-dlg[open]')
    check('Verlauf des Notfalls: abgehakter Schritt', 'Notfall auslösen' in pg.inner_text('#sic-dlg') and '1 Schritt abgehakt' in pg.inner_text('#sic-dlg'))
    dialog_zu(pg)

    # Einstellungen: Wochenbericht
    tab(pg, 'einstellungen')
    pg.click('[data-e="e-bericht"]'); pg.wait_for_selector('#sic-dlg[open] #br-tag')
    pg.select_option('#br-tag', '5'); pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg', state='hidden')
    pg.wait_for_function("document.querySelector('#e-bericht').textContent.includes('Freitag')")
    check('Wochenbericht einstellen: Freitag gespeichert', doc('sicherheit-bereitschaft')['bericht']['tag'] == 5)

    # Konten: ungenutzte Zugänge, Zeitraum, Deaktivieren
    tab(pg, 'konten')
    pg.wait_for_selector('#sic-ungenutzt')
    t = pg.inner_text('#sic-ungenutzt')
    check('Konten: ungenutzte Zugänge (Olga nie, Otto), Reiter heißt „Konten“', 'Olga Alt' in t and 'nie angemeldet' in t and 'Otto Selten' in t
          and pg.inner_text('#sic-tabs [data-tab="konten"]') == 'Konten', t[:300])
    pg.select_option('#ung-tage', '365')
    pg.wait_for_function("!document.querySelector('#sic-ungenutzt').textContent.includes('Otto Selten')")
    check('Zeitraum 365 Tage: nur Olga, Auswahl behält den Fokus', 'Olga Alt' in pg.inner_text('#sic-ungenutzt') and pg.evaluate("document.activeElement.id") == 'ung-tage')
    pg.screenshot(path=f'{SH}/sicherheit_ungenutzt_1440.png', full_page=True)
    pg.click('#sic-ungenutzt [data-deakt="0"]'); pg.wait_for_selector('#sic-dlg[open]')
    check('Dialog Deaktivieren: Name, nie angemeldet, Hinweis', 'Olga Alt' in pg.inner_text('#sic-dlg') and 'nie' in pg.inner_text('#sic-dlg') and 'wieder aktivieren' in pg.inner_text('#sic-dlg').lower())
    pg.click('#sic-dlg .sic-dfuss [type=submit]'); pg.wait_for_selector('#sic-dlg', state='hidden')
    pg.wait_for_function("!document.querySelector('#sic-ungenutzt').textContent.includes('Olga Alt')")
    check('Olga deaktiviert', next(u for u in doc('nutzer')['users'] if u['id'] == olga_id)['active'] is False)
    ctx.close()

    # dunkel und 390 px (Administrator): Notfall mit Leitfaden, Probealarm-Dialog als Blatt
    d = doc('sicherheit-bereitschaft'); d['proben'][0]['t'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() - 600)); storage_write('sicherheit-bereitschaft', d)
    ctx, pg = anmelden('admin', PW, '198.51.100.2', breite=390, hoehe=844, thema='dark', hash_='#notfall')
    pg.wait_for_selector('#sic-leitfaden')
    check('390 px dunkel: kein waagerechtes Scrollen (Notfall)', breit_ok(pg))
    pg.screenshot(path=f'{SH}/sicherheit_notfall_bereitschaft_390_dunkel.png', full_page=True)
    pg.click('#lf-bearbeiten'); pg.wait_for_selector('#sic-dlg[open] #lf-ed-kontakte')
    check('390 px: Leitfaden-Dialog als Blatt, ohne waagerechtes Scrollen', pg.evaluate("(() => { const r = document.querySelector('#sic-dlg').getBoundingClientRect(); return r.bottom >= innerHeight - 2 && r.width >= innerWidth - 2 && document.querySelector('#sic-dlg').scrollWidth <= document.querySelector('#sic-dlg').clientWidth + 1; })()"))
    pg.screenshot(path=f'{SH}/sicherheit_leitfaden_dialog_390_dunkel.png')
    dialog_zu(pg)
    tab(pg, 'lage')
    pg.click('#tab-lage [data-bericht]'); pg.wait_for_selector('#sic-dlg[open] .br-raster')
    check('390 px: Bericht ohne waagerechtes Scrollen', pg.evaluate("document.querySelector('#sic-dlg').scrollWidth <= document.querySelector('#sic-dlg').clientWidth + 1"))
    pg.screenshot(path=f'{SH}/sicherheit_bericht_390_dunkel.png')
    ctx.close()
    br.close()

check('keine JavaScript-Fehler', not fehler, fehler[:5])
ok = sum(res)
print(f'{ok}/{len(res)} passed')
sys.exit(0 if ok == len(res) else 1)
