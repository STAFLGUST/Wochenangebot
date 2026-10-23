"""CRM · Vertrieb (Modul crm, Oberfläche crm.intern unter /module/crm/).

Geprüft: Freigabe (in Entwicklung, nur mit Testfreigabe für eingetragene Tester), Rechte crm.sehen / crm.bearbeiten /
crm.exportieren serverseitig (GR-103) inkl. ohne Anmeldung, ohne CSRF, falsche Methode; Kunden kommen aus den
Kundenstammdaten der Verwaltung (nur lesend, E-1: das CRM schreibt das Dokument „kunden“ nie, keine Zugangsdaten in der
Antwort); Kundenblatt (nur mitgeschickte Felder, gleichzeitiges Bearbeiten verschiedener Felder, Prüfungen und Grenzen);
Aktivitäten (Letzter Kontakt, nächster Schritt, Bestellung → letzter Auftrag, Schnappschuss von Firma/Kundennummer nach
GR-106); Interessenten; CSV-Export (Recht, BOM, keine Formeln); Protokoll ohne Kontaktdaten und Notizen; Oberfläche
(Cockpit, Kunden, Kundenblatt, Wiedervorlagen, Pipeline, Karte, Auswertung, hell/dunkel; Desktop und 390 px).
Nur synthetische Testdaten.
"""
import datetime as dt
import json
import os
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def dokument(name):
    raw = storage_raw(name)
    if not raw:
        return None
    if raw.startswith('<?php'):
        raw = raw.split('\n', 1)[1]
    return json.loads(raw)


HEUTE = dt.date.today().isoformat()

# ── Testdaten: Vertreter, Kundengruppe, Kunden (Stammdaten der Verwaltung) ──
storage_write('vertreter', {'rev': 1, 'groups': [{'nr': '11', 'name': 'Vera Vertrieb', 'kurz': 'VV', 'telefon': '', 'plz': '', 'ort': '', 'land': ''},
                                                 {'nr': '12', 'name': 'Tom Tour', 'kurz': 'TT', 'telefon': '', 'plz': '', 'ort': '', 'land': ''}]})
storage_write('kundengruppen', {'rev': 1, 'groups': [{'nr': '5', 'name': 'Fleischereien Nord', 'klasse': '', 'kategorie': ''}]})


def kunde(i, nr, firma, plz, ort, land='', aktiv=True, vt='11', vt2='', angebote=None, **extra):
    return {'id': i, 'nr': nr, 'gruppe': '5', 'vertreter': vt, 'vertreter2': vt2, 'firma': firma, 'ansprechpartner': extra.get('ap', ''),
            'strasse': 'Musterweg 1', 'plz': plz, 'ort': ort, 'land': land, 'email': extra.get('email', ''), 'telefon': extra.get('tel', ''), 'notiz': '',
            'angebote': angebote or [], 'active': aktiv, 'login': extra.get('login'), 'mailAngebot': True, 'created': '2026-10-01T08:00:00Z', 'changed': '2026-10-01T08:00:00Z'}


KUNDEN = {'rev': 3, 'updatedAt': '2026-10-01T08:00:00Z', 'customers': [
    kunde('kaaa111111111', '900001', 'Musterfleischerei Nord GmbH', '20095', 'Hamburg', ap='Frau Beispiel, Herr Test', tel='040 1234567', email='einkauf@musterfleischerei.example',
          angebote=['std'], login={'username': 'muster-nord', 'hash': 'platzhalter-kein-echter-hash', 'active': True}),
    kunde('kbbb222222222', '900002', 'Beispiel Catering KG', '24103', 'Kiel', vt='12', vt2='11', tel='0431 99887766'),
    kunde('kccc333333333', '900003', 'Probe Markt Ost', '1067', 'Dresden', ap='Herr Probe'),                    # PLZ ohne führende 0
    kunde('kddd444444444', '900004', 'Alpen Feinkost', '6020', 'Innsbruck', land='Österreich'),                  # Ausland: kein Kartenpunkt
    kunde('keee555555555', '900005', 'Ruhender Handel', '28195', 'Bremen', aktiv=False),
    kunde('kfff666666666', '900006', 'Test-Gastro Süd', '80331', 'München', vt=''),
]}
storage_write('kunden', KUNDEN)
kunden_vorher = storage_raw('kunden')

A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
for u, n, r, p, extra in (('verena', 'Verena Sehen', 'viewer', 'Leserin-Zugang-1', {'grant': ['crm.sehen']}),
                          ('bert', 'Bert Bearbeiter', 'editor', 'Bearbeiter-Zugang-1', {'grant': ['crm.bearbeiten']}),
                          ('xena', 'Xena Export', 'editor', 'Editor-Zugang-77', {'grant': ['crm.bearbeiten', 'crm.exportieren']}),
                          ('otto', 'Otto Ohne', 'editor', 'Konto-Passwort-9', {}),
                          ('nora', 'Nora Nichttester', 'editor', 'Merk-Kennwort-31', {'grant': ['crm.sehen']})):
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
V = Client('198.51.100.3'); V.call('login', {'username': 'verena', 'password': 'Leserin-Zugang-1'})
Bb = Client('198.51.100.4'); Bb.call('login', {'username': 'bert', 'password': 'Bearbeiter-Zugang-1'})
X = Client('198.51.100.5'); X.call('login', {'username': 'xena', 'password': 'Editor-Zugang-77'})
O = Client('198.51.100.6'); O.call('login', {'username': 'otto', 'password': 'Konto-Passwort-9'})
Nn = Client('198.51.100.7'); Nn.call('login', {'username': 'nora', 'password': 'Merk-Kennwort-31'})
N = Client('198.51.100.8')

# ── Freigabe ──
mod = {m['id']: m for m in A.call('module_status')[1]['module']}['crm']
ob = mod['oberflaechen'][0]
check('Register: CRM in Entwicklung, ohne Freigabe, Adresse crm.dashboard-stafl.de/module/crm/', ob['entwicklung'] == 'in_entwicklung' and ob['freigabe'] == 'keine'
      and ob['adresse'] == 'https://crm.dashboard-stafl.de/module/crm/', ob)
check('ohne Freigabe: auch Administrator 404', A.call('crm_start')[0] == 404)
st, r = A.call('modul_freigabe_save', {'bereich': 'crm.intern', 'freigabe': 'produktiv', 'grund': 'Test'})
check('keine Produktivfreigabe für ein Modul in Entwicklung (422)', st == 422, (st, r))
st, r = A.call('modul_freigabe_save', {'bereich': 'crm.intern', 'freigabe': 'test', 'grund': 'Abnahme Vertrieb'})
check('Testfreigabe gesetzt', st == 200, r)
st, r = A.call('modul_tester_save', {'bereich': 'crm.intern', 'tester': [ids['admin'], ids['verena'], ids['bert'], ids['xena'], ids['otto']], 'grund': 'Abnahme'})
check('Tester eingetragen', st == 200, r)
check('nicht eingetragener Mitarbeiter (mit crm.sehen): 404', Nn.call('crm_start')[0] == 404)
check('ohne Anmeldung: kein Zugang (401/404)', N.call('crm_start')[0] in (401, 404) and N.call('crm_kunde_save', {'key': 'kaaa111111111', 'felder': {'segment': 'Catering'}})[0] in (401, 404))

# ── Rechte (GR-103) ──
check('Tester ohne CRM-Recht: 403', O.call('crm_start')[0] == 403 and O.call('crm_verlauf&key=kaaa111111111')[0] == 403)
st, d = V.call('crm_start')
check('crm.sehen: Start ok, ohne Bearbeiten/Export', st == 200 and d['rechte'] == {'bearbeiten': False, 'exportieren': False, 'stammdaten': False}, d.get('rechte'))
for a, b in (('crm_kunde_save', {'key': 'kaaa111111111', 'felder': {'segment': 'Catering'}}), ('crm_aktivitaet', {'key': 'kaaa111111111', 'art': 'Telefonat', 'notiz': 'x'}),
             ('crm_interessent_save', {'firma': 'Neu GmbH'}), ('crm_export', {})):
    check(f'{a}: nur ansehen → 403', V.call(a, b)[0] == 403)
check('crm_export: ohne Exportrecht 403 (bearbeiten genügt nicht)', Bb.call('crm_export', {})[0] == 403)
check('Speichern nur per POST (405)', Bb.call('crm_kunde_save')[0] == 405)
csrf = Bb.csrf; Bb.csrf = ''
check('ohne CSRF-Token: 403', Bb.call('crm_kunde_save', {'key': 'kaaa111111111', 'felder': {'segment': 'Catering'}})[0] == 403)
Bb.csrf = csrf
st, d = A.call('crm_start')
check('Administrator: alle Rechte inkl. Stammdaten-Verweis', st == 200 and d['rechte'] == {'bearbeiten': True, 'exportieren': True, 'stammdaten': True}, d.get('rechte'))

# ── Kunden aus den Stammdaten (nur lesend) ──
st, d = Bb.call('crm_start')
kd = {k['key']: k for k in d['kunden']}
k1 = kd['kaaa111111111']
check('alle 6 Kunden der Verwaltung, keine Interessenten', st == 200 and len(d['kunden']) == 6 and all(k['art'] == 'kunde' for k in d['kunden']), len(d.get('kunden', [])))
check('Stammfelder übernommen (Nummer, Firma, Anschrift, Telefon, E-Mail, Ansprechpartner, Vertreter, Gruppe)', k1['nr'] == '900001' and k1['firma'] == 'Musterfleischerei Nord GmbH'
      and k1['plz'] == '20095' and k1['telefon'] == '040 1234567' and k1['email'] == 'einkauf@musterfleischerei.example' and k1['vertreter'] == '11'
      and k1['gruppe'] == 'Fleischereien Nord' and k1['ansprechpartner'] == 'Frau Beispiel, Herr Test', k1)
check('Angebote nur als Namen', k1['angebote'] == ['Wochenangebot'], k1['angebote'])
roh = json.dumps(d)
check('keine Zugangsdaten der Kunden in der Antwort', 'muster-nord' not in roh and 'platzhalter-kein-echter-hash' not in roh and '"login"' not in roh)
check('Standard-Kundenblatt: Bestandskunde, nicht zugeordnet, aktiv in der Wiedervorlage wie der Kunde', k1['crm']['phase'] == 'Bestandskunde'
      and k1['crm']['segment'] == 'Nicht zugeordnet' and k1['crm']['anrufAktiv'] is True and kd['keee555555555']['crm']['anrufAktiv'] is False, k1['crm'])
check('Vertreter und Auswahllisten', [v['name'] for v in d['vertreter']] == ['Vera Vertrieb', 'Tom Tour'] and 'Dienstag - wöchentlich' in d['rhythmen']
      and 'Freitag - 14-tägig (ungerade KW)' in d['rhythmen'] and d['phasen'][0] == 'Interessent' and 'Telefonat' in d['arten'])

# ── Kundenblatt ──
st, r = Bb.call('crm_kunde_save', {'key': 'kaaa111111111', 'felder': {'segment': 'Fleischerei', 'phase': 'Angebot', 'rhythmus1': 'Dienstag - wöchentlich',
                                                                      'potenzialKg': '120,5', 'preisKg': 7.9, 'dbKg': '1,25', 'wiedervorlage': HEUTE, 'naechsterSchritt': 'Angebot nachfassen'}})
c = r.get('kunde', {}).get('crm', {})
check('Kundenblatt gespeichert (Komma-Zahlen, Datum, Auswahl)', st == 200 and c['segment'] == 'Fleischerei' and c['phase'] == 'Angebot' and c['potenzialKg'] == 120.5
      and c['dbKg'] == 1.25 and c['rhythmus1'] == 'Dienstag - wöchentlich' and c['geaendertVon'] == 'Bert Bearbeiter', (st, r))
# zwei Personen, verschiedene Felder: beide bleiben erhalten
X.call('crm_kunde_save', {'key': 'kaaa111111111', 'felder': {'anrufStatus': 'Nochmal'}})
Bb.call('crm_kunde_save', {'key': 'kaaa111111111', 'felder': {'praeferenz': 'vormittags anrufen'}})
c = dokument('crm-kunden')['eintraege']['kaaa111111111']
check('gleichzeitiges Bearbeiten verschiedener Felder überschreibt nichts', c['anrufStatus'] == 'Nochmal' and c['praeferenz'] == 'vormittags anrufen' and c['segment'] == 'Fleischerei', c)
st, r = Bb.call('crm_kunde_save', {'key': 'kbbb222222222', 'felder': {'kontakte': [{'name': 'Clara Koch', 'funktion': 'Küchenchefin', 'telefon': '0431 1111', 'email': 'c.koch@beispiel.example'},
                                                                                   {'name': '', 'funktion': '', 'telefon': '', 'email': ''}]}})
check('Ansprechpartner gespeichert, leere Zeile weggelassen', st == 200 and r['kunde']['crm']['kontakte'] == [{'name': 'Clara Koch', 'funktion': 'Küchenchefin', 'telefon': '0431 1111', 'email': 'c.koch@beispiel.example'}], r)
for name, felder in (('unbekanntes Segment', {'segment': 'Raumfahrt'}), ('ungültiges Datum', {'wiedervorlage': '2026-02-30'}), ('negative Menge', {'potenzialKg': -3}),
                     ('Text statt Zahl', {'dbKg': 'viel'}), ('ungültige E-Mail eines Ansprechpartners', {'kontakte': [{'name': 'A', 'email': 'kein-mail'}]}),
                     ('zu viele Ansprechpartner', {'kontakte': [{'name': f'P{i}'} for i in range(13)]}), ('zu lange Notiz', {'notiz': 'x' * 2001}),
                     ('unbekannter Rhythmus', {'rhythmus1': 'Sonntag - stündlich'}), ('Aktiv kein Wahrheitswert', {'anrufAktiv': 'ja'}), ('unbekanntes Feld', {'firma': 'Umbenannt'})):
    check(f'Kundenblatt: {name} → 422', Bb.call('crm_kunde_save', {'key': 'kaaa111111111', 'felder': felder})[0] == 422)
check('Kundenblatt: unbekannter Kunde → 404', Bb.call('crm_kunde_save', {'key': 'kzzz999999999', 'felder': {'segment': 'Catering'}})[0] == 404)
check('Kundenblatt: ohne Felder → 422', Bb.call('crm_kunde_save', {'key': 'kaaa111111111', 'felder': {}})[0] == 422)
check('Stammdaten unverändert (CRM schreibt das Dokument „kunden“ nie, E-1)', storage_raw('kunden') == kunden_vorher)

# ── Aktivitäten ──
st, r = Bb.call('crm_aktivitaet', {'key': 'kbbb222222222', 'art': 'Telefonat', 'notiz': 'Bedarf KW 44 besprochen', 'naechster': 'Muster schicken', 'faellig': HEUTE})
check('Aktivität gespeichert: letzter Kontakt heute, nächster Schritt mit Wiedervorlage', st == 200 and r['kunde']['crm']['letzterKontakt'] == HEUTE
      and r['kunde']['crm']['naechsterSchritt'] == 'Muster schicken' and r['kunde']['crm']['wiedervorlage'] == HEUTE and r['aktivitaet']['von'] == 'Bert Bearbeiter', r)
st, r = X.call('crm_aktivitaet', {'key': 'kbbb222222222', 'art': 'Bestellung', 'notiz': '240 kg Hüfte'})
check('Bestellung setzt „Letzter Auftrag“, nächster Schritt bleibt', st == 200 and r['kunde']['crm']['letzterAuftrag'] == HEUTE and r['kunde']['crm']['naechsterSchritt'] == 'Muster schicken', r)
check('Aktivität ohne Ergebnis und nächsten Schritt → 422', Bb.call('crm_aktivitaet', {'key': 'kbbb222222222', 'art': 'Notiz'})[0] == 422)
check('Wiedervorlage ohne nächsten Schritt → 422', Bb.call('crm_aktivitaet', {'key': 'kbbb222222222', 'art': 'Notiz', 'notiz': 'x', 'faellig': HEUTE})[0] == 422)
check('unbekannte Art → 422', Bb.call('crm_aktivitaet', {'key': 'kbbb222222222', 'art': 'Fax', 'notiz': 'x'})[0] == 422)
# Schnappschuss (GR-106): Firma in den Stammdaten umbenennen – der Verlauf behält den alten Namen
k2 = json.loads(json.dumps(KUNDEN)); k2['customers'][1]['firma'] = 'Beispiel Catering Neu GmbH'; storage_write('kunden', k2)
st, r = V.call('crm_verlauf&key=kbbb222222222')
check('Verlauf: neueste zuerst, mit Schnappschuss von Firma und Kundennummer (GR-106)', st == 200 and [a['art'] for a in r['aktivitaeten']] == ['Bestellung', 'Telefonat']
      and all(a['firma'] == 'Beispiel Catering KG' and a['nr'] == '900002' for a in r['aktivitaeten']), r)
check('… Liste zeigt den neuen Namen aus den Stammdaten', {k['key']: k for k in V.call('crm_start')[1]['kunden']}['kbbb222222222']['firma'] == 'Beispiel Catering Neu GmbH')
storage_write('kunden', KUNDEN)
check('Verlauf: unbekannter Kunde → 404', V.call('crm_verlauf&key=k-gibt-es-nicht')[0] == 404)
check('Verlauf ohne interne Kennung der Person', 'vonId' not in json.dumps(r))

# ── Interessenten ──
st, r = Bb.call('crm_interessent_save', {'firma': 'Neukunde Grillhaus', 'ansprechpartner': 'Herr Grill', 'plz': '22765', 'ort': 'Hamburg', 'telefon': '040 555', 'vertreter': '12'})
INT = r.get('kunde', {})
check('Interessent angelegt: Phase Interessent, ohne Kundennummer', st == 200 and INT['art'] == 'interessent' and INT['key'].startswith('i') and INT['nr'] == ''
      and INT['crm']['phase'] == 'Interessent' and INT['vertreter'] == '12', r)
check('Interessent: unbekannter Vertreter → 422', Bb.call('crm_interessent_save', {'firma': 'X GmbH', 'vertreter': '99'})[0] == 422)
check('Interessent: ohne Firma → 422', Bb.call('crm_interessent_save', {'firma': ' '})[0] == 422)
check('Interessent: ungültige E-Mail → 422', Bb.call('crm_interessent_save', {'firma': 'X GmbH', 'email': 'nein'})[0] == 422)
st, r = Bb.call('crm_interessent_save', {'id': INT['key'], 'firma': 'Neukunde Grillhaus GmbH', 'plz': '22765', 'ort': 'Hamburg', 'vertreter': '12'})
check('Interessent geändert (gleicher Schlüssel)', st == 200 and r['kunde']['key'] == INT['key'] and r['kunde']['firma'] == 'Neukunde Grillhaus GmbH', r)
check('Interessent: unbekannte ID → 404', Bb.call('crm_interessent_save', {'id': 'igibtesnicht', 'firma': 'X GmbH'})[0] == 404)
check('Kundenblatt und Aktivität auch für Interessenten', Bb.call('crm_kunde_save', {'key': INT['key'], 'felder': {'segment': 'Gastronomie', 'phase': 'Erstkontakt'}})[0] == 200
      and Bb.call('crm_aktivitaet', {'key': INT['key'], 'art': 'Besuch', 'notiz': 'Erstgespräch vor Ort'})[0] == 200)
Bb.call('crm_interessent_save', {'firma': '=HYPERLINK("http://x.example")', 'ort': 'Kiel'})
check('Stammdaten weiterhin unverändert', storage_raw('kunden') == kunden_vorher)

# ── CSV-Export ──
st, _, body = X.call('crm_export', {}, raw=True)
zeilen = body.lstrip('﻿').splitlines()
check('CSV: Kopf, alle Kunden und Interessenten', st == 200 and zeilen[0].startswith('"Art";"Kundennummer";"Firma"') and len(zeilen) == 1 + 6 + 2, (st, zeilen[:2], len(zeilen)))
check('CSV: Kundenblatt-Werte (Segment, Wann, Komma-Zahlen, weitere Ansprechpartner)', any('"Musterfleischerei Nord GmbH"' in z and '"Fleischerei"' in z and '"Dienstag - wöchentlich"' in z
      and '"120,5"' in z for z in zeilen) and any('Clara Koch, Küchenchefin' in z for z in zeilen))
check('CSV: keine Formeln (Zelle beginnt nicht mit =)', any('"\'=HYPERLINK' in z for z in zeilen) and not any(';"=' in z for z in zeilen))
X.call('crm_export', {})

# ── Protokoll: ohne Kontaktdaten und Notizen ──
log = dokument('protokoll/' + dt.datetime.now(dt.timezone.utc).strftime('%Y-%m')) or []
crm_log = [e for e in log if e.get('a') == 'crm']
txt = json.dumps(crm_log, ensure_ascii=False)
check('Protokoll: Kundenblätter (zusammengefasst), Interessenten, Export', any(e['s'] == 'CRM: Kundenblätter bearbeitet' for e in crm_log)
      and any(e['s'] == 'CRM: Interessent angelegt' for e in crm_log) and any(e['s'].startswith('CRM: Liste als CSV') for e in crm_log), [e['s'] for e in crm_log])
check('Protokoll: Auswahlwerte ja, Kontaktdaten/Notizen nein', 'Fleischerei' in txt and '900001' in txt and 'c.koch@' not in txt and 'vormittags' not in txt
      and 'Clara' not in txt and 'Musterfleischerei' not in txt, txt[:300])

# ── Oberfläche ──
with sync_playwright() as p:
    br = p.chromium.launch()

    def anmelden(user, pw, ip, breite=1280, thema=None):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin',
                             color_scheme=thema or 'light')
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/crm/'); pg.wait_for_selector('#crm-app:not([hidden])')
        return ctx, pg

    ctx, pg = anmelden('bert', 'Bearbeiter-Zugang-1', '198.51.100.4')
    kp = pg.inner_text('#tab-cockpit')
    check('Cockpit: Kennzahlen, Wiedervorlage fällig, letzte Aktivität', 'Aktive Kunden' in kp and 'Angebot nachfassen' in kp and 'Muster schicken' in kp and 'Erstgespräch vor Ort' in kp, kp[:500])
    check('Reiter Wiedervorlagen mit Zahl der fälligen', pg.text_content('#crm-faellig').strip() == '2', pg.text_content('#crm-faellig'))
    pg.screenshot(path=os.path.join(SH, 'crm_cockpit_1280.png'), full_page=True)

    pg.click('#crm-tabs button[data-tab="kunden"]'); pg.wait_for_selector('#k-tabelle')
    check('Kunden: nur aktive (Standard) – Ruhender Handel ausgeblendet, Interessenten dabei', 'Ruhender Handel' not in pg.inner_text('#k-tabelle')
          and 'Neukunde Grillhaus GmbH' in pg.inner_text('#k-tabelle'))
    pg.fill('#k-suche', 'küchenchefin'); pg.wait_for_function("document.querySelectorAll('#k-tabelle tbody tr').length === 1")
    check('Suche findet Ansprechpartner aus dem Kundenblatt', 'Beispiel Catering KG' in pg.inner_text('#k-tabelle'))
    check('Suchfeld behält den Fokus', pg.evaluate("document.activeElement.id") == 'k-suche')
    pg.fill('#k-suche', '')
    pg.select_option('#k-vertreter', '12'); pg.wait_for_function("document.querySelectorAll('#k-tabelle tbody tr').length === 2")
    check('Filter Vertreter (auch Vertreter 2)', 'Beispiel Catering' in pg.inner_text('#k-tabelle') and 'Neukunde Grillhaus' in pg.inner_text('#k-tabelle'))
    pg.select_option('#k-vertreter', '')
    sel = pg.locator('#k-tabelle select[data-feld="segment"][data-key="kfff666666666"]')
    sel.select_option('Gastronomie'); pg.wait_for_function("document.querySelector('#crm-toast').classList.contains('zeigen')")
    check('Segment direkt in der Tabelle gespeichert', dokument('crm-kunden')['eintraege']['kfff666666666']['segment'] == 'Gastronomie')
    pg.screenshot(path=os.path.join(SH, 'crm_kunden_1280.png'), full_page=False)

    # Kundenblatt
    pg.click('#k-tabelle button[data-oeffnen="kaaa111111111"]'); pg.wait_for_selector('#dlg-kunde[open] #verlauf li')
    inh = pg.inner_text('#kunde-inhalt')
    check('Kundenblatt: Stammdaten aus der Verwaltung (nur lesend)', '900001' in inh and 'Fleischereien Nord' in inh and 'Vera Vertrieb' in inh and 'Wochenangebot' in inh
          and 'Pflege in der Verwaltung' in inh and pg.locator('#kunde-inhalt .crm-stamm input').count() == 0, inh[:300])
    pg.fill('#kunde-inhalt input[data-blatt="naechsterSchritt"]', 'Probe liefern'); pg.press('#kunde-inhalt input[data-blatt="naechsterSchritt"]', 'Tab')
    pg.wait_for_function("document.querySelector('#blatt-status').textContent === 'Gespeichert.'")
    check('Feld beim Verlassen gespeichert', dokument('crm-kunden')['eintraege']['kaaa111111111']['naechsterSchritt'] == 'Probe liefern')
    pg.fill('#kunde-inhalt input[data-blatt="dbKg"]', 'abc'); pg.press('#kunde-inhalt input[data-blatt="dbKg"]', 'Tab')
    pg.wait_for_function("document.querySelector('#blatt-status').classList.contains('fehler')")
    check('ungültige Zahl: Hinweis, alter Wert bleibt', pg.input_value('#kunde-inhalt input[data-blatt="dbKg"]') == '1,25' and dokument('crm-kunden')['eintraege']['kaaa111111111']['dbKg'] == 1.25)
    pg.click('[data-kontakt-neu]')
    zeile = pg.locator('#kontakte [data-kontakt]').last
    zeile.locator('[data-k="name"]').fill('Dora Disponentin'); zeile.locator('[data-k="telefon"]').fill('040 7654321')
    pg.click('[data-kontakte-speichern]'); pg.wait_for_function("document.querySelector('#blatt-status').textContent === 'Ansprechpartner gespeichert.'")
    check('Ansprechpartner im Kundenblatt hinzugefügt', dokument('crm-kunden')['eintraege']['kaaa111111111']['kontakte'][0]['name'] == 'Dora Disponentin')
    pg.select_option('#akt-art', 'Besuch'); pg.fill('#akt-notiz', 'Kühlhaus besichtigt'); pg.fill('#akt-naechster', 'Preise schicken')
    pg.click('#akt-speichern'); pg.wait_for_function("document.querySelector('#verlauf') && document.querySelector('#verlauf').textContent.includes('Kühlhaus besichtigt')")
    check('Aktivität im Kundenblatt protokolliert, Verlauf aktualisiert', 'Preise schicken' in pg.inner_text('#verlauf') and 'Bert Bearbeiter' in pg.inner_text('#verlauf'))
    pg.screenshot(path=os.path.join(SH, 'crm_kundenblatt_1280.png'), full_page=False)
    pg.click('#dlg-kunde [data-schliessen]')

    # Wiedervorlagen
    pg.click('#crm-tabs button[data-tab="wiedervorlagen"]'); pg.wait_for_selector('#wv-tabelle')
    pg.select_option('#wv-tabelle select[data-feld="rhythmus1"][data-key="kbbb222222222"]', 'Montag - wöchentlich')
    pg.wait_for_function("document.querySelector('#crm-toast').classList.contains('zeigen')")
    st_sel = pg.locator('#wv-tabelle select[data-feld="anrufStatus"][data-key="kbbb222222222"]')
    st_sel.select_option('Erledigt'); pg.wait_for_function("document.querySelector('#wv-tabelle select[data-feld=\"anrufStatus\"][data-key=\"kbbb222222222\"]').className === 'st-Erledigt'")
    e2 = dokument('crm-kunden')['eintraege']['kbbb222222222']
    check('Wiedervorlage: Wann und Erledigt direkt gespeichert, Farbe folgt dem Status', e2['rhythmus1'] == 'Montag - wöchentlich' and e2['anrufStatus'] == 'Erledigt', e2)
    reihen = pg.eval_on_selector_all('#wv-tabelle tbody tr', 'r => r.map(x => x.querySelector(".crm-firma").textContent)')
    check('Reihenfolge bleibt beim Bearbeiten stehen', reihen == pg.eval_on_selector_all('#wv-tabelle tbody tr', 'r => r.map(x => x.querySelector(".crm-firma").textContent)'))
    pg.click('#wv-wann summary'); pg.check('#wv-wann input[value="Dienstag - wöchentlich"]')
    pg.wait_for_function("document.querySelectorAll('#wv-tabelle tbody tr').length === 1")
    check('Filter „Wann“ (Mehrfachauswahl)', 'Musterfleischerei Nord' in pg.inner_text('#wv-tabelle'))
    pg.click('#wv-wann-alle'); pg.click('#wv-wann summary')
    pg.select_option('#wv-termin', 'ueber'); pg.wait_for_function("document.querySelector('#wv-tabelle tbody').textContent.includes('Keine Kunden')")
    check('Filter „Wiedervorlage überfällig“ (keine überfälligen)', True)
    pg.select_option('#wv-termin', 'alle')
    pg.screenshot(path=os.path.join(SH, 'crm_wiedervorlagen_1280.png'), full_page=False)

    # Pipeline, Karte, Auswertung
    pg.click('#crm-tabs button[data-tab="pipeline"]'); pg.wait_for_selector('.crm-board')
    check('Pipeline: Phase Angebot enthält den Kunden', 'Musterfleischerei Nord' in pg.inner_text('.crm-spalte[data-phase="Angebot"]'))
    pg.screenshot(path=os.path.join(SH, 'crm_pipeline_1280.png'), full_page=False)
    pg.click('#crm-tabs button[data-tab="karte"]'); pg.wait_for_selector('#km-pts .pt')
    n_pts = pg.locator('#km-pts .pt').count()
    kt = pg.inner_text('#tab-karte')
    check('Karte: deutsche PLZ als Punkte (auch PLZ ohne führende 0), Ausland/ohne PLZ ohne Punkt', n_pts == 5 and pg.locator('#km-pts .pt[data-plz="01067"]').count() == 1
      and '2 ohne Kartenpunkt' in kt, (n_pts, kt[:200]))
    pg.locator('#km-pts .pt[data-plz="20095"]').dispatch_event('click')
    pg.wait_for_selector('#km-pop:not([hidden])')
    check('Karte: Klick zeigt Kunden am Ort', 'Musterfleischerei Nord GmbH' in pg.inner_text('#km-pop'))
    pg.click('#km-pop [data-oeffnen]'); pg.wait_for_selector('#dlg-kunde[open]')
    check('… und öffnet das Kundenblatt', pg.text_content('#kunde-titel') == 'Musterfleischerei Nord GmbH')
    pg.click('#dlg-kunde [data-schliessen]')
    pg.check('#km-nein'); pg.wait_for_function("document.querySelectorAll('#km-pts .pt').length === 6")
    check('Karte: inaktive Kunden zuschaltbar', pg.locator('#km-pts .pt.aus').count() == 1)
    pg.screenshot(path=os.path.join(SH, 'crm_karte_1280.png'), full_page=False)
    pg.click('#crm-tabs button[data-tab="auswertung"]'); pg.wait_for_selector('#tab-auswertung .crm-tabelle')
    aw = pg.inner_text('#tab-auswertung')
    check('Auswertung: Vertreter, ohne Vertreter, Aktivitäten nach Art', 'Vera Vertrieb' in aw and 'Ohne Vertreter' in aw and 'Telefonat' in aw and 'Bestellung' in aw, aw[:400])
    check('Export-Knopf ohne Exportrecht ausgeblendet', pg.locator('#crm-export').is_hidden())
    ctx.close()

    # Nur ansehen: keine Eingabefelder
    ctx, pg = anmelden('verena', 'Leserin-Zugang-1', '198.51.100.3')
    pg.click('#crm-tabs button[data-tab="kunden"]'); pg.wait_for_selector('#k-tabelle')
    check('nur ansehen: keine Auswahlfelder, kein „Interessent“', pg.locator('#k-tabelle select').count() == 0 and pg.locator('[data-neu-interessent]').count() == 0)
    pg.click('#k-tabelle button[data-oeffnen="kbbb222222222"]'); pg.wait_for_selector('#dlg-kunde[open]')
    check('nur ansehen: Kundenblatt gesperrt, keine Aktivität', pg.locator('#kunde-inhalt [data-blatt]:not([disabled])').count() == 0 and pg.locator('#akt-form').count() == 0)
    ctx.close()

    # Export-Recht, dunkles Design, Handy
    ctx, pg = anmelden('xena', 'Editor-Zugang-77', '198.51.100.5', thema='dark')
    check('Export-Knopf mit Exportrecht', pg.locator('#crm-export').is_visible())
    with pg.expect_download() as dl:
        pg.click('#crm-export')
    check('CSV-Download über die Oberfläche', dl.value.suggested_filename.startswith('CRM_') and dl.value.suggested_filename.endswith('.csv'), dl.value.suggested_filename)
    bg = pg.evaluate("getComputedStyle(document.body).backgroundColor")
    check('dunkles Design', bg == 'rgb(18, 16, 17)', bg)
    pg.screenshot(path=os.path.join(SH, 'crm_cockpit_dunkel_1280.png'), full_page=True)
    ctx.close()

    ctx, pg = anmelden('bert', 'Bearbeiter-Zugang-1', '198.51.100.4', breite=390)
    breit = pg.evaluate("document.documentElement.scrollWidth")
    check('390 px: Cockpit ohne seitliches Scrollen', breit <= 390, breit)
    pg.screenshot(path=os.path.join(SH, 'crm_cockpit_390.png'), full_page=True)
    pg.click('#crm-tabs button[data-tab="wiedervorlagen"]'); pg.wait_for_selector('#wv-tabelle')
    check('390 px: Wiedervorlagen ohne seitliches Scrollen der Seite', pg.evaluate("document.documentElement.scrollWidth") <= 390)
    pg.screenshot(path=os.path.join(SH, 'crm_wiedervorlagen_390.png'), full_page=False)
    pg.click('#crm-tabs button[data-tab="kunden"]'); pg.wait_for_selector('#k-tabelle')
    pg.click('#k-tabelle button[data-oeffnen="kaaa111111111"]'); pg.wait_for_selector('#dlg-kunde[open] #verlauf li')
    check('390 px: Kundenblatt passt in die Breite', pg.evaluate("document.querySelector('#dlg-kunde').scrollWidth <= document.querySelector('#dlg-kunde').clientWidth + 1"))
    pg.screenshot(path=os.path.join(SH, 'crm_kundenblatt_390.png'), full_page=False)
    pg.click('#dlg-kunde [data-schliessen]')
    pg.click('#crm-tabs button[data-tab="karte"]'); pg.wait_for_selector('#km-pts .pt')
    pg.screenshot(path=os.path.join(SH, 'crm_karte_390.png'), full_page=False)
    ctx.close()
    br.close()

check('keine JavaScript-Fehler', not fehler, fehler)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
