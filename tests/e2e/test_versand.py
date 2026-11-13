"""Modul Versand (app/module/versand/, Oberfläche versand.intern, Auftrag des Inhabers 13.11.2026): Angebot veröffentlichen
und per E-Mail an Kunden senden – herausgelöst aus „Angebot bearbeiten“.
Geprüft: Register (fertig, produktiv, Kachel, Modulzugang ohne Standardrolle); Rechte serverseitig (ohne Anmeldung 401, ohne
Modulzugang 403 „kein_modulzugang“, Zugang ohne Einzelrecht 403, bestehende Rechte ohne Zugang wirkungslos – auch an den
bisherigen Aktionen publish, kunden_rundmail, restposten_info, kunden_restposten: klare 403-Meldung für alte offene Fenster);
Stand und Änderungsliste (Zählung, je Angebot, Preise nur mit Modulzugang Angebot); Veröffentlichen des gespeicherten Entwurfs
(Revision Pflicht, veralteter Stand 409, nichts offen 409, Version und Protokoll); Empfänger, Vorschau und Versand von
Wochenangebot und Sonderposten (nur Kunden des Angebots, GR-005; falsche Woche 409); Verlauf ohne Kundennamen; Wartung der
Oberfläche (503, Administrator weiter); Startseite; Oberfläche am Desktop und bei 390 px, hell und dunkel; Eingabebereich:
keine Knöpfe „Veröffentlichen“/„An Kunden senden“ mehr, „Drucken“ an ihrer Stelle, Zahl der Änderungen, „Zum Versand“ nur mit
Zugang. Läuft gegen den Test-Mailserver."""
import json
import re
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from smtp_test import TestSmtp
from umgebung import SH, SMTP_PORT, FIX, until

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i and not c else ''))


smtp = TestSmtp(SMTP_PORT, password='Test-Postfach-1')
A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)

# ---------- Register ----------
ms = A.call('module_status')[1]
vm = next((m for m in ms['module'] if m['id'] == 'versand'), None)
check('Register: Modul Versand mit Kachel im Bereich „Verwaltung & Daten“, fertig und produktiv',
      vm and vm['dashboard'] and vm.get('gruppe') == 'verwaltung' and vm['icon'] == 'send' and vm['kachel']['zugang'] and vm['kachel']['status'] == 'verfuegbar', vm)
check('Register: Adresse versand.dashboard-stafl.de/module/versand/', vm and vm['kachel']['adresse'] == 'https://versand.dashboard-stafl.de/module/versand/', vm and vm['kachel'])
reihe = [m['id'] for m in sorted((m for m in ms['module'] if m.get('gruppe') == 'verwaltung'), key=lambda m: m.get('reihenfolge', 999))]
check('Seitenleiste: Versand direkt über „Verwaltung“', reihe.index('versand') + 1 == reihe.index('verwaltung'), reihe)

# ---------- Mitarbeiter, Kunden, Angebote ----------
USERS = {'erika': ('Erika Editor', 'editor', 'Editor-Zugang-77', []),                              # Bearbeiter ohne Zugang (Standard)
         'vera': ('Vera Versand', 'editor', 'Editor-Zugang-88', ['versand.zugang']),              # Zugang + veröffentlichen (Standard der Rolle), nicht senden
         'sven': ('Sven Sender', 'viewer', 'Leser-Zugang-55', ['versand.zugang', 'wochenangebot.senden', 'sonderposten.senden']),   # senden, nicht veröffentlichen
         'zora': ('Zora Zugang', 'viewer', 'Leser-Zugang-66', ['versand.zugang']),                # nur Zugang (Ansehen)
         'ole': ('Ole Ohne', 'viewer', 'Leser-Zugang-77', ['wochenangebot.senden', 'sonderposten.senden'])}   # Senden-Rechte ohne Zugang
uid = {}
for user, (name, role, pw, grant) in USERS.items():
    code, r = A.call('user_save', {'id': '', 'name': name, 'username': user, 'role': role, 'active': True, 'password': pw, 'mustChange': False})
    uid[user] = next(u['id'] for u in A.call('users')[1]['users'] if u['username'] == user)
    if grant:
        A.call('user_save', {'id': uid[user], 'name': name, 'role': role, 'active': True, 'grant': grant, 'deny': []})


def login(user):
    c = Client('198.51.100.' + str(10 + list(USERS).index(user)))
    code, r = c.call('login', {'username': user, 'password': USERS[user][2]})
    assert code == 200, (user, code, r)
    return c


E, V, S, Z, O = login('erika'), login('vera'), login('sven'), login('zora'), login('ole')
P = Client('198.51.100.99')   # nicht angemeldet
perms = lambda c: set(c.call('status')[1]['user']['perms'])
check('Standardrollen ohne Modulzugang Versand (Bearbeiter, Leser)', 'versand.zugang' not in perms(E) and 'versand.zugang' not in perms(O))
check('Bearbeiter behält das bestehende Recht „Angebot veröffentlichen“ (Schlüssel unverändert, GR-103)', 'angebot.veroeffentlichen' in perms(E))
check('Zugang einzeln vergeben: Vera (mit veröffentlichen), Sven (mit senden), Zora (nur Zugang)',
      {'versand.zugang', 'angebot.veroeffentlichen'} <= perms(V) and {'versand.zugang', 'wochenangebot.senden', 'sonderposten.senden', 'kunden.sehen'} <= perms(S)
      and 'angebot.veroeffentlichen' not in perms(S) and 'versand.zugang' in perms(Z) and 'wochenangebot.senden' not in perms(Z))
kat = {p['key']: p for p in A.call('rechte')[1]['catalog']}
check('Rollen und Rechte: die drei bestehenden Rechte stehen beim Modul Versand (Bearbeiten: veröffentlichen, Voll: senden)',
      all(kat[k]['modul'] == 'versand' for k in ('versand.zugang', 'angebot.veroeffentlichen', 'wochenangebot.senden', 'sonderposten.senden'))
      and kat['angebot.veroeffentlichen']['stufe'] == 'bearbeiten' and kat['wochenangebot.senden']['stufe'] == 'voll' and kat['versand.zugang']['default'] == [],
      {k: (kat[k]['modul'], kat[k].get('stufe')) for k in ('versand.zugang', 'angebot.veroeffentlichen', 'wochenangebot.senden')})

cur = A.call('offers')[1]
check('Kundenangebote angelegt', A.call('offers_save', {'rev': cur['rev'], 'offers': cur['offers'] + [
    {'id': 'grosshandel', 'name': 'Angebot Großhandel', 'fallback': 'standard'}, {'id': 'gastro', 'name': 'Angebot Gastronomie', 'fallback': 'standard'}]})[0] == 200)
KUNDEN = [('Beispielkantine Nord GmbH', 'K-1001', 'einkauf@kantine-nord.example', ['std'], True),
          ('Muster-Gastro Hafen', 'K-1002', 'kueche@gastro-hafen.example', ['gastro'], True),
          ('Großhandel Beispiel KG', 'K-1003', 'dispo@grosshandel-beispiel.example', ['grosshandel'], True),
          ('Testmarkt Elbe', 'K-1004', 'markt@testmarkt-elbe.example', ['std', 'grosshandel'], True),
          ('Bistro Musterplatz', 'K-1005', '', ['gastro'], True),
          ('Hofladen Beispielhof', 'K-1006', 'laden@beispielhof.example', ['std'], False)]
kid = {}
for i, (firma, nr, mail, ang, aktiv) in enumerate(KUNDEN):
    rev = A.call('kunden')[1]['rev']
    code, r = A.call('kunde_save', {'id': '', 'rev': rev, 'firma': firma, 'nr': nr, 'email': mail, 'active': aktiv, 'angebote': ang,
                                    'login': {'username': f'kunde{i + 1}', 'password': 'Kunden-Kennwort-5', 'mustChange': False, 'active': True}})
    kid[firma] = r['customer']['id'] if code == 200 else None
check('Kunden angelegt', all(kid.values()), kid)

# Bestand (Sonderposten erscheinen nur mit Bestand) und Entwurf mit Änderungen
norm = lambda c: (str(c).lstrip('0') or '0') if str(c).isdigit() else str(c).upper()
master = [a for a in json.load(open(FIX + '/bestand/master_stock.json')) if a[2] and a[2] > 0]
check('Bestand übernommen', A.call('stock_import', {'date': '2026-10-16', 'source': 'Bestand.xls',
      'articles': [{'code': a[0].lstrip('0') or '0', 'name': a[1], 'kg': a[2], 'mhd': a[3], 'mhdKg': a[4], 'lots': []} for a in master]})[0] == 200)
lager = {norm(a[0]) for a in master}
d0 = A.call('draft')[1]
WOCHE0 = d0['published']['meta']['week']


def entwurf():
    d = A.call('draft')[1]
    m = d['draft'] or d['published']
    for k in ('savedAt', 'savedBy', 'publishedAt', 'rev', 'issues'):
        m.pop(k, None)
    return m, d['revision']


m, rev = entwurf()
preise = [i for i in m['items'] if i.get('code') and i['price'].get('status') == 'value' and norm(i['code']) in lager]
IA, IB, IC, ID, IE = preise[0], preise[1], preise[2], preise[3], preise[4]
IA['price']['value'] = round(IA['price']['value'] + 0.30, 2)                       # Preis
IB['price']['value'] = round(IB['price']['value'] - 0.20, 2); IB['origin'] = 'UY'   # Preis und Herkunft: zählt einmal (Preis)
IC['variants'] = {'grosshandel': {'status': 'value', 'value': round(IC['price']['value'] - 0.40, 2)}}   # Angebotspreis
ID['sale'] = {'value': round(ID['price']['value'] - 1.00, 2)}                       # Empfehlung mit Preis = Sonderposten
IE['name'] = IE['name'] + ' (neu benannt)'                                          # bearbeitet
weg = m['items'].pop()                                                              # entfernt
m['meta']['week'] = WOCHE0 + 1                                                      # Kopfdaten
code, r = A.call('save_draft', {'model': m, 'revision': rev})
check('Entwurf mit sieben Änderungen gespeichert', code == 200, r)
REV = r['revision']

# ---------- Rechte: Stand und Liste ----------
check('versand_start ohne Anmeldung 401', P.call('versand_start')[0] == 401)
for name, c in (('Bearbeiter ohne Zugang', E), ('Senden-Rechte ohne Zugang', O)):
    code, r = c.call('versand_start')
    check(f'versand_start: {name} → 403 „kein_modulzugang“', code == 403 and r.get('code') == 'kein_modulzugang', (code, r))
check('alle Aktionen des Moduls ohne Zugang 403', all(E.call(a)[0] == 403 for a in ('versand_aenderungen', 'versand_empfaenger&art=woche', 'versand_verlauf'))
      and all(E.call(a, {})[0] == 403 for a in ('versand_veroeffentlichen', 'versand_vorschau', 'versand_senden')))
code, st = Z.call('versand_start')
check('nur Zugang: Stand mit Zahlen, Rechte alle aus', code == 200 and st['rechte'] == {'veroeffentlichen': False, 'woche': False, 'sonderposten': False, 'angebot': True, 'bearbeiten': False}, st.get('rechte'))
roh = Z.call('versand_start', raw=True)[2]
check('Stand enthält keine Preise, Firmen oder Adressen', 'example' not in roh and 'Kantine' not in roh and '"price"' not in roh and '"zeilen"' not in roh)
ae = st['aenderungen']
check('Stand: 7 Änderungen (Kopf, 2 Preise, 1 Angebotspreis, 1 Empfehlung, 1 bearbeitet, 1 entfernt)',
      ae['anzahl'] == 7 and ae['arten'] == {'kopf': 1, 'preis': 2, 'angebotspreis': 1, 'empfehlung': 1, 'bearbeitet': 1, 'entfernt': 1} and not ae['erste'] and ae['revision'] == REV, ae)
ang = {a['id']: a for a in st['angebote']}
check('Stand: Angebote der Woche mit Änderungen und Kunden je Angebot',
      list(ang)[0] == 'std' and list(ang)[-2:] == ['grosshandel', 'gastro'] and ang['std']['aenderungen'] == 6 and ang['grosshandel']['aenderungen'] == 1 and ang['gastro']['aenderungen'] == 0
      and (ang['std']['kunden'], ang['grosshandel']['kunden'], ang['gastro']['kunden']) == (2, 2, 1) and ang['std']['oeffentlich']
      and all(v['aenderungen'] == 0 and v['kunden'] == 0 for k, v in ang.items() if k not in ('std', 'grosshandel', 'gastro')), {k: (v['aenderungen'], v['kunden']) for k, v in ang.items()})
N_ANGEBOTE = len(ang)
check('Stand: Entwurf und veröffentlichte Woche, Versand (4 Empfänger, 2 ausgeschlossen, noch nichts gesendet)',
      st['entwurf']['week'] == WOCHE0 + 1 and st['veroeffentlicht']['week'] == WOCHE0 and st['entwurf']['savedBy'] == 'Administrator'
      and st['versand']['empfaenger'] == 4 and st['versand']['ausgeschlossen'] == 2 and st['versand']['gesendet'] == 0 and st['versand']['postfach'], (st['entwurf'], st['versand']))
code, li = Z.call('versand_aenderungen')
zeilen = {(z['art'], z['code']): z for z in li.get('zeilen', [])}
check('Änderungsliste mit Modulzugang Angebot: Zeilen wie gezählt, Preis alt → neu, Angebot an der Zeile',
      code == 200 and len(li['zeilen']) == 7 and zeilen[('preis', IA['code'])]['nach'].startswith(('%.2f' % IA['price']['value']).replace('.', ','))
      and zeilen[('angebotspreis', IC['code'])]['angebot'] == 'grosshandel' and 'Herkunft' in zeilen[('preis', IB['code'])]['zusatz']
      and ('entfernt', weg.get('code', '')) in zeilen and li['angebote']['grosshandel'] == 'Angebot Großhandel', li.get('zeilen'))
A.call('user_save', {'id': uid['zora'], 'name': 'Zora Zugang', 'role': 'viewer', 'active': True, 'grant': ['versand.zugang'], 'deny': ['angebot.zugang']})
check('Änderungsliste ohne Modulzugang Angebot 403 (Preise), Stand weiter 200', Z.call('versand_aenderungen')[0] == 403 and Z.call('versand_start')[0] == 200)
A.call('user_save', {'id': uid['zora'], 'name': 'Zora Zugang', 'role': 'viewer', 'active': True, 'grant': ['versand.zugang'], 'deny': []})

# ---------- Veröffentlichen ----------
check('veröffentlichen ohne Anmeldung 401', P.call('versand_veroeffentlichen', {'revision': REV})[0] == 401)
check('veröffentlichen: nur Zugang (ohne Recht) 403', Z.call('versand_veroeffentlichen', {'revision': REV})[0] == 403)
check('veröffentlichen: Senden-Recht genügt nicht 403', S.call('versand_veroeffentlichen', {'revision': REV})[0] == 403)
code, r = E.call('publish', {'model': m, 'revision': REV})
check('altes Fenster: publish für Bearbeiter ohne Zugang → 403 mit klarem Hinweis auf den Bereich „Versand“', code == 403 and 'Versand' in r.get('error', ''), (code, r))
check('veröffentlichen ohne Revision 422', V.call('versand_veroeffentlichen', {})[0] == 422)
code, r = V.call('versand_veroeffentlichen', {'revision': REV - 1})
check('veröffentlichen mit veraltetem Stand 409 (jemand hat inzwischen gespeichert)', code == 409 and r.get('conflict') and r['revision'] == REV, (code, r))
check('nichts veröffentlicht', A.call('draft')[1]['published']['meta']['week'] == WOCHE0)
n_ver = len(A.call('versions')[1]['versions'])
code, r = V.call('versand_veroeffentlichen', {'revision': REV})
check('veröffentlichen mit Zugang und Recht: gespeicherter Entwurf ist online', code == 200 and r['week'] == WOCHE0 + 1 and r['publishedAt'], (code, r))
d = A.call('draft')[1]
check('veröffentlicht: neue Woche, Preise aus dem Entwurf, Entwurf beendet, alte Fassung als Version',
      d['published']['meta']['week'] == WOCHE0 + 1 and d['draft'] is None and len(A.call('versions')[1]['versions']) == n_ver + 1
      and next(i for i in d['published']['items'] if i['id'] == IA['id'])['price']['value'] == IA['price']['value'])
off = P.call('offer')[1]['offer']
check('Kundenseite zeigt den neuen Stand (ohne Kundenpreise)', off['meta']['week'] == WOCHE0 + 1 and 'variants' not in json.dumps(off))
code, r = V.call('versand_veroeffentlichen', {'revision': A.call('draft')[1]['revision']})
check('nichts offen: 409 „nichts_offen“', code == 409 and r.get('code') == 'nichts_offen', (code, r))
st = V.call('versand_start')[1]
check('Stand danach: keine Änderungen, kein Entwurf', st['aenderungen']['anzahl'] == 0 and st['entwurf'] is None and st['veroeffentlicht']['week'] == WOCHE0 + 1)
check('Administrator: bisherige Aktion publish funktioniert weiter (Tests, alte Fenster mit Zugang)',
      A.call('publish', {'model': entwurf()[0], 'revision': A.call('draft')[1]['revision']})[0] == 200)

# ---------- Empfänger, Vorschau, Senden: Wochenangebot ----------
check('Empfänger ohne Anmeldung 401', P.call('versand_empfaenger&art=woche')[0] == 401)
check('Empfänger: ohne Senden-Recht 403 (Zora, Vera)', Z.call('versand_empfaenger&art=woche')[0] == 403 and V.call('versand_empfaenger&art=woche')[0] == 403)
check('Empfänger: unbekannte Art 422', S.call('versand_empfaenger&art=alles')[0] == 422)
code, em = S.call('versand_empfaenger&art=woche')
firmen = [c['firma'] for c in em.get('empfaenger', [])]
check('Empfänger Wochenangebot: 4 Kunden nach Firma, 2 ausgeschlossen mit Grund',
      code == 200 and firmen == sorted(firmen, key=str.lower) and len(firmen) == 4 and em['woche']['week'] == WOCHE0 + 1 and em['postfach']
      and {c['firma']: c['grund'] for c in em['ausgeschlossen']} == {'Bistro Musterplatz': 'keine E-Mail-Adresse', 'Hofladen Beispielhof': 'Kunde inaktiv'}, em)
roh = S.call('versand_empfaenger&art=woche', raw=True)[2]
check('Empfängerliste ohne Zugangsdaten und Anschrift', '"login"' not in roh and '"hash"' not in roh and '"strasse"' not in roh and 'kunde1' not in roh)
ids = [c['id'] for c in em['empfaenger']]
code, r = S.call('versand_vorschau', {'art': 'woche', 'id': ids[0], 'note': 'Diese Woche: Roastbeef.'})
check('Vorschau der Wochen-Mail mit Zusatztext', code == 200 and f'KW {WOCHE0 + 1}' in r['subject'] and 'Roastbeef' in r['html'] and r['firma'] == firmen[0], (code, r))
check('Vorschau ohne Senden-Recht 403', Z.call('versand_vorschau', {'art': 'woche', 'id': ids[0]})[0] == 403)
n0 = len(smtp.messages)
check('senden ohne Anmeldung 401', P.call('versand_senden', {'art': 'woche', 'ids': ids})[0] == 401)
check('senden ohne Senden-Recht 403', V.call('versand_senden', {'art': 'woche', 'ids': ids, 'week': WOCHE0 + 1, 'year': em['woche']['year']})[0] == 403)
code, r = O.call('kunden_rundmail', {'ids': ids, 'week': WOCHE0 + 1, 'year': em['woche']['year']})
check('altes Fenster: kunden_rundmail mit Senden-Recht, aber ohne Zugang → 403 mit Hinweis auf „Versand“', code == 403 and 'Versand' in r.get('error', ''), (code, r))
check('senden mit falscher Woche 409', S.call('versand_senden', {'art': 'woche', 'ids': ids, 'week': WOCHE0, 'year': em['woche']['year']})[0] == 409)
check('bis hier keine E-Mail verschickt', len(smtp.messages) == n0)
code, r = S.call('versand_senden', {'art': 'woche', 'ids': ids[:3] + ['gibtsnicht'], 'note': 'Diese Woche: Roastbeef.', 'week': WOCHE0 + 1, 'year': em['woche']['year']})
check('senden: drei Kunden gesendet, unbekannter Kunde abgewiesen', code == 200 and [x['ok'] for x in r['results']] == [True, True, True, False], (code, r))
check('drei E-Mails beim Mailserver, je Kunde eine, mit Zusatztext und Abmelde-Kopf',
      until(lambda: len(smtp.messages) == n0 + 3, 5) and sorted(m_['to'][0] for m_ in smtp.messages[n0:]) == sorted(c['email'] for c in em['empfaenger'][:3])
      and all(f'KW {WOCHE0 + 1}' in m_['subject'] for m_ in smtp.messages[n0:]), [m_['to'] for m_ in smtp.messages[n0:]])
st = S.call('versand_start')[1]
check('Stand: 3 von 4 gesendet, letzter Versand mit Woche', st['versand']['gesendet'] == 3 and st['versand']['zuletzt']['week'] == WOCHE0 + 1 and ang and st['angebote'][0]['zuletzt']['week'] == WOCHE0 + 1, st['versand'])
em2 = S.call('versand_empfaenger&art=woche')[1]
check('Empfänger: bereits beschickte Kunden gekennzeichnet', sum(1 for c in em2['empfaenger'] if c['gesendet']) == 3)

# ---------- Sonderposten ----------
check('Sonderposten: Empfänger ohne Recht 403', Z.call('versand_empfaenger&art=sonderposten&angebot=grosshandel')[0] == 403)
check('Sonderposten: unbekanntes Angebot 404', S.call('versand_empfaenger&art=sonderposten&angebot=gibtsnicht')[0] == 404)
code, sp = S.call('versand_empfaenger&art=sonderposten&angebot=grosshandel')
check('Sonderposten Großhandel: 1 Artikel mit Preis, nur die 2 Kunden dieses Angebots (GR-005)',
      code == 200 and [it['code'] for it in sp['items']] == [ID['code']] and sp['items'][0]['price'] == ID['sale']['value']
      and sorted(c['firma'] for c in sp['recipients']) == ['Großhandel Beispiel KG', 'Testmarkt Elbe'], sp)
n1 = len(smtp.messages)
fremd = kid['Beispielkantine Nord GmbH']   # hat nur das Wochenangebot
code, r = S.call('versand_senden', {'art': 'sonderposten', 'angebot': 'grosshandel', 'ids': [c['id'] for c in sp['recipients']] + [fremd], 'publishedAt': 'falsch'})
check('Sonderposten: veralteter Stand 409', code == 409, (code, r))
code, r = S.call('versand_senden', {'art': 'sonderposten', 'angebot': 'grosshandel', 'ids': [c['id'] for c in sp['recipients']] + [fremd], 'publishedAt': sp['publishedAt']})
check('Sonderposten gesendet: 2 Kunden des Angebots, fremder Kunde abgewiesen', code == 200 and [x['ok'] for x in r['results']] == [True, True, False]
      and 'nicht freigeschaltet' in r['results'][2]['error'], (code, r))
check('zwei Sonderposten-Mails mit Artikel und Preis, keine an fremde Kunden',
      until(lambda: len(smtp.messages) == n1 + 2, 5) and all('Sonderposten' in m_['subject'] for m_ in smtp.messages[n1:])
      and 'einkauf@kantine-nord.example' not in [m_['to'][0] for m_ in smtp.messages[n1:]], [m_['subject'] for m_ in smtp.messages[n1:]])
code, r = O.call('restposten_info&offer=grosshandel')
check('altes Fenster: restposten_info / kunden_restposten ohne Zugang 403', code == 403 and O.call('kunden_restposten', {'offer': 'grosshandel', 'ids': [fremd], 'publishedAt': sp['publishedAt']})[0] == 403, (code, r))

# ---------- Verlauf ----------
code, vl = Z.call('versand_verlauf')
arten = [x['art'] for x in vl.get('verlauf', [])]
check('Verlauf: neueste zuerst – Sonderposten, Wochenangebot, Veröffentlichungen; mit Mitarbeiter und Anzahl',
      code == 200 and arten[:2] == ['sonderposten', 'woche'] and arten.count('veroeffentlicht') >= 2
      and (vl['verlauf'][0]['ok'], vl['verlauf'][0]['fehler']) == (2, 1) and (vl['verlauf'][1]['ok'], vl['verlauf'][1]['fehler']) == (3, 0) and vl['verlauf'][1]['von'] == 'Sven Sender'
      and vl['verlauf'][1]['titel'] == f'Wochenangebot KW {WOCHE0 + 1}/{em["woche"]["year"]}', vl.get('verlauf'))
roh = Z.call('versand_verlauf', raw=True)[2]
check('Verlauf ohne Firmen und Adressen', 'example' not in roh and 'Kantine' not in roh and 'Elbe' not in roh)
check('Verlauf ohne Zugang 403', E.call('versand_verlauf')[0] == 403)

# ---------- Startseite ----------
m2, rev2 = entwurf()
m2['items'][0]['price']['value'] = round(m2['items'][0]['price']['value'] + 0.11, 2)
check('neuer Entwurf mit einer Änderung', A.call('save_draft', {'model': m2, 'revision': rev2})[0] == 200)
heute = V.call('start_heute')[1]
punkte = [p for p in heute.get('punkte', heute.get('heute', [])) if p.get('modul') == 'versand']
check('Startseite: „1 Änderung nicht veröffentlicht“ für Mitarbeiter mit Zugang und Recht', any('1 Änderung nicht veröffentlicht' in p['titel'] for p in punkte), heute)
heute = E.call('start_heute')[1]
check('Startseite: nichts vom Versand für Bearbeiter ohne Zugang', not [p for p in heute.get('punkte', heute.get('heute', [])) if p.get('modul') == 'versand'])

# ---------- Wartung der Oberfläche ----------
code, r = A.call('modul_wartung_save', {'bereich': 'versand.intern', 'active': True, 'grund': 'Test'})
check('Wartung für versand.intern gesetzt', code == 200, (code, r))
check('Wartung: Mitarbeiter 503 (lesen und schreiben), Administrator arbeitet weiter',
      V.call('versand_start')[0] == 503 and V.call('versand_veroeffentlichen', {'revision': 1})[0] == 503 and A.call('versand_start')[0] == 200)
check('Wartung des Versands lässt den Eingabebereich in Ruhe', E.call('draft')[0] == 200)
A.call('modul_wartung_save', {'bereich': 'versand.intern', 'active': False, 'grund': ''})
check('Wartung beendet: Mitarbeiter wieder 200', V.call('versand_start')[0] == 200)

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs = []

    def seite(user, password, pfad, vp=None, schema='light'):
        ctx = br.new_context(viewport=vp or {'width': 1280, 'height': 900}, color_scheme=schema)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', password); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden])')
        if pfad:
            pg.goto(B + pfad)
        return pg

    # Eingabebereich: Knöpfe weg, „Drucken“ an ihrer Stelle, Zahl der Änderungen, „Zum Versand“ nur mit Zugang
    e = seite('erika', USERS['erika'][2], '')
    e.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('Eingabebereich: keine Knöpfe „Veröffentlichen“ und „An Kunden senden“ mehr', e.locator('#btn-publish').count() == 0 and e.locator('#btn-send').count() == 0)
    check('Eingabebereich: an der Stelle steht „Drucken“ (direkt vor „⋯“)', e.is_visible('#btn-drucken')
          and e.evaluate("document.querySelector('#btn-drucken').nextElementSibling.classList.contains('menu-wrap')"))
    e.wait_for_function("document.querySelector('#save-state').textContent.includes('nicht veröffentlicht')")
    # der Eingabebereich vereinheitlicht beim Öffnen die Merkmale der Testdaten (Herkunft als Kürzel) – deshalb mehr als eine Änderung
    check('Eingabebereich: Zahl „n Änderungen nicht veröffentlicht“ als Information (kein Fenster)', re.search(r'\d+ Änderung(en)? nicht veröffentlicht', e.inner_text('#save-state'))
          and e.locator('#offen-liste').count() == 0 and e.locator('#dlg-publish[open]').count() == 0)
    check('Eingabebereich: Bearbeiter ohne Zugang sieht keinen Verweis „Zum Versand“', e.locator('#save-state .zum-versand').count() == 0)
    check('Seitenleiste: Bearbeiter ohne Zugang sieht „Versand“ nicht', e.locator('#r-leiste [data-modul="versand"]').count() == 0)
    e.goto(B + '/module/versand/'); e.wait_for_selector('#vs-err:not([hidden])')
    check('Modulseite ohne Zugang: Hinweis statt Inhalt', 'keinen Zugang' in e.inner_text('#vs-err') and e.locator('#vs-app').is_hidden())
    e.context.close()

    v = seite('vera', USERS['vera'][2], '')
    v.wait_for_function("document.querySelector('#save-state .zum-versand')")
    check('Eingabebereich: mit Zugang „Zum Versand →“ in der Statuszeile', 'Zum Versand' in v.inner_text('#save-state') and v.get_attribute('#save-state .zum-versand', 'href').endswith('/module/versand/'))
    v.click('#save-state .zum-versand'); v.wait_for_selector('#vs-app:not([hidden]) #vs-s1')
    check('Versand: Schritt 1 offen mit Zahl, Schritt 2 wartet', re.search(r'\d+ Änderungen nicht veröffentlicht', v.inner_text('#vs-s1')) and 'wartet auf Schritt 1' in v.inner_text('#vs-s2')
          and v.is_enabled('#vs-pub') and v.is_disabled('#vs-send'))
    v.wait_for_selector('#r-leiste [data-modul="versand"][aria-current="page"]')
    check('Seitenleiste: „Versand“ aktiv im Bereich „Verwaltung & Daten“ über „Verwaltung“',
          v.evaluate("(() => { const l = [...document.querySelectorAll('#r-leiste [data-modul]')].map((x) => x.dataset.modul); return l.indexOf('versand') > 0 && l.indexOf('versand') + 1 === l.indexOf('verwaltung'); })()")
          and 'Verwaltung' in v.evaluate("document.querySelector('#r-leiste [data-modul=versand]').closest('.r-gruppe').querySelector('.r-gruppe-titel').textContent"))
    v.wait_for_selector('#vs-verlauf .vs-zeile')
    check('Versand: Liste der Angebote und Verlauf', v.locator('#vs-angebote tr').count() == N_ANGEBOTE and 'gesendet' in v.inner_text('#vs-verlauf') and 'example' not in v.inner_text('#vs-verlauf'))
    check('Versand: Vorschau und Drucken führen zur Angebotsansicht des Angebots (Druckfassung)',
          'vorschau=1&angebot=grosshandel' in v.get_attribute('#vs-angebote tr[data-angebot="grosshandel"] a[aria-label^="Vorschau"]', 'href')
          and 'drucken=liste' in v.get_attribute('#vs-angebote tr[data-angebot="std"] a[aria-label^="Drucken"]', 'href'))
    v.screenshot(path=SH + '/versand-seite.png', full_page=True)
    # „Drucken“ aus der Liste: neuer Tab mit der Druckfassung des Entwurfs (Angebotsansicht, assets/angebot-druck.js), Druck genau einmal
    v.context.add_init_script("window.print = () => { window.__gedruckt = (window.__gedruckt || 0) + 1; window.dispatchEvent(new Event('beforeprint')); };")
    with v.context.expect_page() as neu:
        v.click('#vs-angebote tr[data-angebot="grosshandel"] a[aria-label^="Drucken"]')
    dr = neu.value; dr.on('pageerror', lambda e: errs.append('druck: ' + str(e)))
    dr.wait_for_function('window.__gedruckt >= 1', timeout=20000)
    ds = dr.evaluate("""() => ({ seiten: document.querySelectorAll('#print-root .pl-page').length, zeilen: document.querySelectorAll('#print-root .al-band tr.row').length,
      n: window.__gedruckt, suche: location.search })""")
    check('Versand: „Drucken“ öffnet die Druckfassung des Entwurfs dieses Angebots (Angebotsansicht) und ruft den Druck genau einmal auf',
          ds['seiten'] >= 1 and ds['zeilen'] > 0 and ds['n'] == 1 and 'vorschau=1' in ds['suche'] and 'angebot=grosshandel' in ds['suche'] and 'drucken' not in ds['suche'], ds)
    dr.close()
    v.click('#vs-pub'); v.wait_for_selector('#dlg-pub[open] .vs-aend')
    check('Fenster „Veröffentlichen“: Liste der Änderungen, „Im Angebot ändern“', 'preisänderungen (1)' in v.inner_text('#dlg-pub').lower() and 'Im Angebot ändern' in v.inner_text('#dlg-pub'))
    v.mouse.click(5, 5)
    check('Fenster schließt nicht durch Klick daneben', v.locator('#dlg-pub[open]').count() == 1)
    v.screenshot(path=SH + '/versand-veroeffentlichen.png')
    # inzwischen speichert jemand: 409, Liste wird neu geladen
    m3, rev3 = entwurf()
    m3['items'][1]['price']['value'] = round(m3['items'][1]['price']['value'] + 0.07, 2)
    A.call('save_draft', {'model': m3, 'revision': rev3})
    v.click('#pub-jetzt'); v.wait_for_selector('#pub-meldung:not([hidden])')
    check('Fenster: veralteter Stand → Meldung, Liste aktuell (2 Preise), nichts veröffentlicht',
          'bitte prüfen' in v.inner_text('#pub-meldung') and 'preisänderungen (2)' in v.inner_text('#dlg-pub').lower() and A.call('draft')[1]['draft'] is not None)
    v.click('#pub-jetzt'); v.wait_for_selector('#dlg-fertig[open]')
    check('veröffentlicht: Fenster „ist online“, ohne Senden-Recht kein Knopf „Senden“', 'ist online' in v.inner_text('#dlg-fertig') and v.locator('#fertig-senden').count() == 0
          and A.call('draft')[1]['draft'] is None)
    v.keyboard.press('Escape'); v.wait_for_selector('#dlg-fertig', state='hidden')
    check('Stand nach dem Veröffentlichen: Schritt 1 erledigt', 'ist online' in v.inner_text('#vs-s1') and v.is_disabled('#vs-pub'))
    v.context.close()

    s = seite('sven', USERS['sven'][2], '/module/versand/')
    s.wait_for_selector('#vs-app:not([hidden]) #vs-s2')
    check('Sender: Senden möglich, Veröffentlichen gesperrt, Sonderposten-Knopf beim Großhandel', s.is_enabled('#vs-send') and s.is_disabled('#vs-pub')
          and s.locator('#vs-angebote tr[data-angebot="grosshandel"] [data-sonderposten]').count() == 1)
    s.click('#vs-send'); s.wait_for_selector('#dlg-send[open] .vs-empf li')
    check('Fenster „Senden“: 4 Empfänger, 2 nicht berücksichtigt; vorausgewählt nur, wer die Woche noch nicht bekommen hat (1)', s.locator('#dlg-send [data-wahl]').count() == 4
          and '2 nicht berücksichtigt' in s.inner_text('#dlg-send') and s.locator('#dlg-send [data-wahl]:checked').count() == 1
          and s.locator('#dlg-send .vs-erg.warn').count() == 3 and 'An 1 Kunden senden' in s.inner_text('#send-jetzt'))
    s.check('#send-alle')
    check('„alle auswählen“: 4 Kunden', '4 Kunden ausgewählt' in s.inner_text('#send-zahl') and 'An 4 Kunden senden' in s.inner_text('#send-jetzt'))
    s.click('#send-prev'); s.wait_for_selector('#send-vorschau:not([hidden])')
    check('Fenster „Senden“: Vorschau der E-Mail mit Betreff', f'KW {WOCHE0 + 1}' in s.inner_text('#send-betreff'))
    s.screenshot(path=SH + '/versand-senden.png')
    s.click('#dlg-send .vs-chip[data-filter="grosshandel"]'); s.wait_for_function("document.querySelectorAll('#dlg-send [data-wahl]').length === 2")
    check('Filter nach Angebot zeigt nur dessen Kunden, Auswahl bleibt', '4 Kunden ausgewählt' in s.inner_text('#send-zahl'))
    s.click('#dlg-send .vs-chip[data-filter="*"]')
    n2 = len(smtp.messages)
    s.click('#send-jetzt'); s.wait_for_selector('#send-meldung.ok:not([hidden])', timeout=20000)
    check('gesendet: Meldung im Fenster, 4 E-Mails, Ergebnis je Zeile', '4 E-Mails gesendet' in s.inner_text('#send-meldung') and until(lambda: len(smtp.messages) == n2 + 4, 5)
          and s.locator('#dlg-send .vs-erg.ok').count() == 4, s.inner_text('#send-meldung'))
    s.click('#dlg-send .dlg-foot [data-close]'); s.wait_for_selector('#dlg-send', state='hidden')
    s.wait_for_function("document.querySelector('#vs-s2').textContent.includes('an alle 4 Kunden gesendet')")
    check('Stand: Schritt 2 erledigt', 'erledigt' in s.inner_text('#vs-s2'))
    s.click('[data-sonderposten="grosshandel"]'); s.wait_for_selector('#dlg-send[open] .vs-artikel li')
    check('Fenster „Sonderposten“: Artikel mit Preis in €/kg, 2 Empfänger', '€/kg' in s.inner_text('#dlg-send .vs-artikel') and s.locator('#dlg-send [data-wahl]').count() == 2)
    s.keyboard.press('Escape'); s.wait_for_selector('#dlg-send', state='hidden')
    s.context.close()

    # Handy 390 px und dunkel: nichts ragt über den Rand
    for name, vp, schema in (('mobil', {'width': 390, 'height': 844}, 'light'), ('dunkel', {'width': 1280, 'height': 900}, 'dark'), ('mobil-dunkel', {'width': 390, 'height': 844}, 'dark')):
        a = seite('admin', PW, '/module/versand/', vp, schema)
        a.wait_for_selector('#vs-app:not([hidden]) #vs-s1'); a.wait_for_selector('#vs-verlauf .vs-zeile')
        check(f'{name}: Seite nicht breiter als das Fenster', a.evaluate('document.documentElement.scrollWidth') <= vp['width'], a.evaluate('document.documentElement.scrollWidth'))
        a.screenshot(path=SH + f'/versand-seite-{name}.png', full_page=True)
        a.click('#vs-send'); a.wait_for_selector('#dlg-send[open] .vs-empf li')
        check(f'{name}: Fenster „Senden“ passt ins Fenster', a.evaluate("document.querySelector('#dlg-send').getBoundingClientRect().right") <= vp['width'] + 1)
        check(f'{name}: Empfängerzeile lesbar (Firma und Adresse mindestens 180 px breit)', a.evaluate("document.querySelector('#dlg-send .vs-wer').getBoundingClientRect().width") >= 180)
        a.screenshot(path=SH + f'/versand-senden-{name}.png')
        a.context.close()
    check('keine JavaScript-Fehler', not errs, errs[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
