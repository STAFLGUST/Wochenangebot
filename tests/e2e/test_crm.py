"""CRM · Vertrieb (Modul crm, Oberfläche crm.intern unter /module/crm/).

Geprüft: Freigabe (produktiv seit 23.10.2026: jeder Mitarbeiter mit CRM-Recht, keine Testfreigabe), Rechte crm.sehen / crm.bearbeiten /
crm.exportieren serverseitig (GR-103) inkl. ohne Anmeldung, ohne CSRF, falsche Methode; Kunden kommen aus den
Kundenstammdaten der Verwaltung (nur lesend, E-1: das CRM schreibt das Dokument „kunden“ nie, keine Zugangsdaten in der
Antwort); Kundenblatt (nur mitgeschickte Felder, gleichzeitiges Bearbeiten verschiedener Felder, Prüfungen und Grenzen);
Aktivitäten (Letzter Kontakt, nächster Schritt, Bestellung → letzter Auftrag, Schnappschuss von Firma/Kundennummer nach
GR-106); Interessenten; CSV-Export (Recht, BOM, keine Formeln); Protokoll ohne Kontaktdaten und Notizen; Oberfläche
(Cockpit, Kunden, Kundenblatt, Wiedervorlagen, Pipeline, Karte, Auswertung, hell/dunkel; Desktop und 390 px).
Reiter „MHD-Ware“ (Recht crm.mhd_ware): MHD-Liste des Bestands ohne Preise (Reihenfolge, Stufen), Käufer aus den Umsatzdaten
(Zeitraum 3/6/12 Monate, Liefertage, Gutschrift, ohne Berechnung zählt nicht, Kunde ohne Stammsatz, keine Beträge), Suche nach
anderem Artikel, Wiedervorlage (Recht bearbeiten und MHD-Ware, Text vom Server, Notiz im Verlauf, nicht doppelt, eigener Schritt
nie gekürzt, frühere Wiedervorlage bleibt, vorgezogene im Protokoll, Grenzen), Rechte; Oberfläche mit Farben, Zeitraum, Vertreter, „kauft regelmäßig“, Auswahl, Kundenblatt, 1280/390 px.
Nur synthetische Testdaten.
"""
import datetime as dt
import json
import os
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH, storage_raw, storage_sqlite, storage_write

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
            'strasse': extra.get('strasse', 'Musterweg 1'), 'plz': plz, 'ort': ort, 'land': land, 'email': extra.get('email', ''), 'telefon': extra.get('tel', ''), 'notiz': '',
            'angebote': angebote or [], 'active': aktiv, 'login': extra.get('login'), 'mailAngebot': True, 'created': '2026-10-01T08:00:00Z', 'changed': '2026-10-01T08:00:00Z'}


KUNDEN = {'rev': 3, 'updatedAt': '2026-10-01T08:00:00Z', 'customers': [
    kunde('kaaa111111111', '900001', 'Musterfleischerei Nord GmbH', '20095', 'Hamburg', ap='Frau Beispiel, Herr Test', strasse='Musterstr. 10', tel='040 1234567', email='einkauf@musterfleischerei.example',
          angebote=['std'], login={'username': 'muster-nord', 'hash': 'platzhalter-kein-echter-hash', 'active': True}),
    kunde('kbbb222222222', '900002', 'Beispiel Catering KG', '24103', 'Kiel', vt='12', vt2='11', tel='0431 99887766'),
    kunde('kccc333333333', '900003', 'Probe Markt Ost', '1067', 'Dresden', ap='Herr Probe'),                    # PLZ ohne führende 0
    kunde('kddd444444444', '900004', 'Alpen Feinkost', '6020', 'Innsbruck', land='Österreich'),                  # Ausland: kein Kartenpunkt
    kunde('keee555555555', '900005', 'Ruhender Handel', '28195', 'Bremen', aktiv=False),
    kunde('kfff666666666', '900006', 'Test-Gastro Süd', '80331', 'München', vt='', strasse='Testgasse 9'),   # Nummer unbekannt: Straße
]}
storage_write('kunden', KUNDEN)
kunden_vorher = storage_raw('kunden')

A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
for u, n, r, p, extra in (('verena', 'Verena Sehen', 'viewer', 'Leserin-Zugang-1', {'grant': ['crm.sehen']}),
                          ('bert', 'Bert Bearbeiter', 'editor', 'Bearbeiter-Zugang-1', {'grant': ['crm.bearbeiten']}),
                          ('xena', 'Xena Export', 'editor', 'Editor-Zugang-77', {'grant': ['crm.bearbeiten', 'crm.exportieren']}),
                          ('otto', 'Otto Ohne', 'editor', 'Konto-Passwort-9', {}),
                          ('nora', 'Nora Neu', 'editor', 'Merk-Kennwort-31', {'grant': ['crm.sehen']})):
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
check('Register: CRM fertig und produktiv, Adresse crm.dashboard-stafl.de/module/crm/', ob['entwicklung'] == 'fertig' and ob['freigabe'] == 'produktiv'
      and ob['zugang'] and ob['adresse'] == 'https://crm.dashboard-stafl.de/module/crm/', ob)
check('Kachel verfügbar', mod['kachel']['status'] == 'verfuegbar' and mod['kachel']['zugang'] is True, mod['kachel'])
st, r = A.call('modul_freigabe_save', {'bereich': 'crm.intern', 'freigabe': 'test', 'grund': 'Test'})
check('Produktivbereich: keine Testfreigabe über die Modulverwaltung (nur über ein Release)', st == 422, (st, r))
check('jeder Mitarbeiter mit „CRM ansehen“: Start ok (nie als Tester eingetragen)', Nn.call('crm_start')[0] == 200)
check('ohne Anmeldung: 401', N.call('crm_start')[0] == 401 and N.call('crm_kunde_save', {'key': 'kaaa111111111', 'felder': {'segment': 'Catering'}})[0] == 401)

# ── Rechte (GR-103) ──
check('Tester ohne CRM-Recht: 403', O.call('crm_start')[0] == 403 and O.call('crm_verlauf&key=kaaa111111111')[0] == 403)
st, d = V.call('crm_start')
check('crm.sehen: Start ok, ohne Bearbeiten/Export', st == 200 and d['rechte'] == {'bearbeiten': False, 'exportieren': False, 'stammdaten': False, 'mhd': False}, d.get('rechte'))
for a, b in (('crm_kunde_save', {'key': 'kaaa111111111', 'felder': {'segment': 'Catering'}}), ('crm_aktivitaet', {'key': 'kaaa111111111', 'art': 'Telefonat', 'notiz': 'x'}),
             ('crm_interessent_save', {'firma': 'Neu GmbH'}), ('crm_export', {})):
    check(f'{a}: nur ansehen → 403', V.call(a, b)[0] == 403)
check('crm_export: ohne Exportrecht 403 (bearbeiten genügt nicht)', Bb.call('crm_export', {})[0] == 403)

# ── Genaue Lage der Anschriften (crm_karte, Adressverzeichnis lib/adressen.php; Testadressen tests/fixtures/karte/adressen.json) ──
check('crm_karte: ohne CRM-Recht 403, ohne Anmeldung 401', O.call('crm_karte')[0] == 403 and N.call('crm_karte')[0] == 401)
st, d = V.call('crm_karte')
pk = d.get('punkte', {}) if st == 200 else {}
check('crm_karte (crm.sehen): Hausnummer genau aus dem Adressverzeichnis („Musterstr. 10“ = Musterstraße 10)',
      st == 200 and pk.get('kaaa111111111') == [53.55012, 9.99018, 'h'], (st, pk))
check('crm_karte: unbekannte Hausnummer → Straßenmitte, unbekannte Straße/Ausland → kein Eintrag (Karte: PLZ-Mittelpunkt)',
      (pk.get('kfff666666666') or [0, 0, ''])[2] == 's' and set(pk) == {'kaaa111111111', 'kfff666666666'}, pk)
check('crm_karte: Stand des Verzeichnisses (Anzahl Adressen), ohne Pfade oder Dateinamen', d.get('stand', {}).get('adressen') == 6 and 'sqlite' not in json.dumps(d), d.get('stand'))
check('Speichern nur per POST (405)', Bb.call('crm_kunde_save')[0] == 405)
csrf = Bb.csrf; Bb.csrf = ''
check('ohne CSRF-Token: 403', Bb.call('crm_kunde_save', {'key': 'kaaa111111111', 'felder': {'segment': 'Catering'}})[0] == 403)
Bb.csrf = csrf
st, d = A.call('crm_start')
check('Administrator: alle Rechte inkl. Stammdaten-Verweis', st == 200 and d['rechte'] == {'bearbeiten': True, 'exportieren': True, 'stammdaten': True, 'mhd': True}, d.get('rechte'))

# ── Kunden aus den Stammdaten (nur lesend) ──
st, d = Bb.call('crm_start')
kd = {k['key']: k for k in d['kunden']}
k1 = kd['kaaa111111111']
check('alle 6 Kunden der Verwaltung, keine Interessenten', st == 200 and len(d['kunden']) == 6 and all(k['art'] == 'kunde' for k in d['kunden']), len(d.get('kunden', [])))
check('Stammfelder übernommen (Nummer, Firma, Anschrift, Telefon, E-Mail, Ansprechpartner, Vertreter, Gruppe)', k1['nr'] == '900001' and k1['firma'] == 'Musterfleischerei Nord GmbH'
      and k1['plz'] == '20095' and k1['telefon'] == '040 1234567' and k1['email'] == 'einkauf@musterfleischerei.example' and k1['vertreter'] == '11'
      and k1['gruppe'] == 'Fleischereien Nord' and k1['gruppeNr'] == '5' and k1['ansprechpartner'] == 'Frau Beispiel, Herr Test', k1)
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
# inaktiver Kunde ohne Kundenblatt: „Aktiv in der Wiedervorlage“ einschalten wird gespeichert (Vergleich mit dem echten Standard „nein“)
st, r = Bb.call('crm_kunde_save', {'key': 'keee555555555', 'felder': {'anrufAktiv': True}})
check('inaktiver Kunde: Wiedervorlage einschalten gespeichert', st == 200 and r['kunde']['crm']['anrufAktiv'] is True, r)
check('… bleibt nach dem Neuladen eingeschaltet', {k_['key']: k_ for k_ in Bb.call('crm_start')[1]['kunden']}['keee555555555']['crm']['anrufAktiv'] is True)
check('… wieder ausschalten', Bb.call('crm_kunde_save', {'key': 'keee555555555', 'felder': {'anrufAktiv': False}})[1]['kunde']['crm']['anrufAktiv'] is False)
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
check('Interessent: PLZ ohne Ziffern → 422', Bb.call('crm_interessent_save', {'firma': 'X GmbH', 'plz': 'abcde'})[0] == 422)
check('Interessent: deutsche PLZ nicht fünfstellig → 422', Bb.call('crm_interessent_save', {'firma': 'X GmbH', 'plz': '2276', 'land': 'Deutschland'})[0] == 422)
st, r = Bb.call('crm_interessent_save', {'id': INT['key'], 'firma': 'Neukunde Grillhaus', 'plz': '1010', 'ort': 'Wien', 'land': 'Österreich', 'vertreter': '12'})
check('Interessent: ausländische PLZ (Österreich, 4 Ziffern) angenommen', st == 200 and r['kunde']['plz'] == '1010', (st, r))
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
    pg.fill('#k-suche', 'fleischereien nord'); pg.wait_for_function("document.querySelectorAll('#k-tabelle tbody tr').length === 5")
    check('Suche nach Kundengruppe (Name): alle aktiven Kunden der Gruppe, keine Interessenten', 'Neukunde Grillhaus' not in pg.inner_text('#k-tabelle')
          and 'Fleischereien Nord' in pg.inner_text('#k-tabelle tbody tr:first-child'))
    pg.fill('#k-suche', 'KG 5'); pg.wait_for_function("document.querySelectorAll('#k-tabelle tbody tr').length === 5")
    check('Suche nach Kundengruppe (Nummer „KG 5“)', 'Musterfleischerei Nord' in pg.inner_text('#k-tabelle'))
    check('Suchfeld nennt die Kundengruppe', 'Kundengruppe' in pg.get_attribute('#k-suche', 'placeholder'))
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
    # Genaue Lage aus dem Adressverzeichnis: Hamburg auf Hausnummer genau, München an der Straße, übrige am PLZ-Mittelpunkt
    pt_haus, pt_strasse = '#km-pts .pt[data-plz="a53.55012,9.99018"]', '#km-pts .pt[data-plz="a48.13702,11.57549"]'
    check('Karte: Kunde mit bekannter Anschrift auf Hausnummer genau statt am PLZ-Mittelpunkt',
          pg.locator(pt_haus).count() == 1 and pg.locator('#km-pts .pt[data-plz="20095"]').count() == 0 and pg.locator(pt_strasse).count() == 1)
    check('Karte: Hinweis zur Genauigkeit (Hausnummer, Straße, Postleitzahl) mit Stand des Verzeichnisses',
          '1 auf Hausnummer genau' in kt and '1 an der Straße' in kt and 'am Mittelpunkt der Postleitzahl' in kt and 'OpenStreetMap-Adressverzeichnis' in kt, kt[-400:])
    pg.locator(pt_strasse).dispatch_event('click'); pg.wait_for_selector('#km-pop:not([hidden])')
    check('Karte: Punkt an der Straße ist als solcher gekennzeichnet', 'Hausnummer nicht gefunden' in pg.inner_text('#km-pop') and 'Testgasse 9' in pg.inner_text('#km-pop'))
    pg.locator(pt_haus).dispatch_event('click')
    pg.wait_for_function("document.querySelector('#km-pop').textContent.includes('Musterfleischerei')")
    pop = pg.inner_text('#km-pop')
    check('Karte: Klick zeigt Kunden an der Anschrift', 'Musterfleischerei Nord GmbH' in pop and 'Musterstr. 10' in pop and 'nicht gefunden' not in pop, pop)
    pg.click('#km-pop [data-oeffnen]'); pg.wait_for_selector('#dlg-kunde[open]')
    check('… und öffnet das Kundenblatt', pg.text_content('#kunde-titel') == 'Musterfleischerei Nord GmbH')
    pg.click('#dlg-kunde [data-schliessen]')
    pg.check('#km-nein'); pg.wait_for_function("document.querySelectorAll('#km-pts .pt').length === 6")
    check('Karte: inaktive Kunden zuschaltbar', pg.locator('#km-pts .pt.aus').count() == 1)
    pg.screenshot(path=os.path.join(SH, 'crm_karte_1280.png'), full_page=False)

    # Nielsen-Gebiete (nielsen.json): Zahlen je Gebiet, Filter mit Ausschnitt, Flächen mit Beschriftung
    pg.uncheck('#km-nein'); pg.wait_for_function("document.querySelectorAll('#km-pts .pt').length === 5")
    opt = {o['value']: o['text'] for o in pg.eval_on_selector_all('#km-gebiet option', 'os => os.map((o) => ({ value: o.value, text: o.textContent }))')}
    check('Nielsen: Auswahl mit allen 8 Gebieten und Zahl der Kunden je Gebiet (Dresden VII, München IV, Hamburg/Kiel I)',
          list(opt) == ['', 'I', 'II', 'IIIa', 'IIIb', 'IV', 'V', 'VI', 'VII'] and opt['VII'].endswith('(1)') and opt['IV'].endswith('(1)')
          and int(opt['I'].rsplit('(', 1)[1].rstrip(')')) >= 2 and opt['II'].endswith('(0)'), opt)
    vb_alle = pg.get_attribute('#km-svg', 'viewBox')
    pg.select_option('#km-gebiet', 'VII'); pg.wait_for_function("document.querySelectorAll('#km-pts .pt').length === 1")
    check('Nielsen-Filter VII: nur Kunden des Gebiets, Ausschnitt auf das Gebiet, Gebiet hervorgehoben',
          pg.locator('#km-pts .pt[data-plz="01067"]').count() == 1 and pg.get_attribute('#km-svg', 'viewBox') != vb_alle
          and pg.locator('#km-flaechen path.hervor[data-gebiet="VII"]').count() == 1 and pg.locator('#km-flaechen path').count() == 1)
    pg.locator('#km-pts .pt[data-plz="01067"]').dispatch_event('click'); pg.wait_for_selector('#km-pop:not([hidden])')
    check('Infokarte nennt das Nielsen-Gebiet', 'Nielsen VII · Sachsen, Thüringen' in pg.inner_text('#km-pop'), pg.inner_text('#km-pop'))
    pg.check('#km-gebiete'); pg.wait_for_function("document.querySelectorAll('#km-flaechen path').length === 8")
    gt = pg.text_content('#km-flaechen-text')
    check('Gebiete zeigen: alle 8 Flächen mit Name und Kundenzahl', pg.locator('#km-flaechen-text text').count() == 8 and 'Nielsen VII1 Kunde' in gt and 'Nielsen II0 Kunden' in gt, gt[:200])
    pg.select_option('#km-gebiet', ''); pg.wait_for_function("document.querySelectorAll('#km-pts .pt').length === 5")
    check('Alle Gebiete: wieder alle Punkte, Flächen bleiben eingeschaltet', pg.locator('#km-flaechen path').count() == 8 and pg.is_checked('#km-gebiete'))
    pg.screenshot(path=os.path.join(SH, 'crm_karte_nielsen_1280.png'), full_page=False)
    pg.uncheck('#km-gebiete'); pg.wait_for_function("document.querySelectorAll('#km-flaechen path').length === 0")
    # Kundensuche auf der Karte: Trefferliste, Enter zeigt den Kunden, Filter werden passend gestellt
    pg.fill('#km-suche', 'probe markt'); pg.wait_for_selector('#km-treffer:not([hidden]) .km-treffer-zeile')
    check('Kartensuche: Treffer mit Firma, Kundennummer und Ort', 'Probe Markt Ost' in pg.inner_text('#km-treffer') and 'KN 900003' in pg.inner_text('#km-treffer'), pg.inner_text('#km-treffer'))
    pg.press('#km-suche', 'Enter'); pg.wait_for_selector('#km-pop:not([hidden]) li.treffer')
    check('Kartensuche: Enter zoomt zum Kunden und öffnet die Infokarte mit ihm hervorgehoben', 'Probe Markt Ost' in pg.inner_text('#km-pop li.treffer') and pg.is_hidden('#km-treffer')
          and pg.get_attribute('#km-svg', 'viewBox') != vb_alle)
    pg.select_option('#km-gebiet', 'IV'); pg.wait_for_function("document.querySelectorAll('#km-pts .pt').length === 1")
    pg.fill('#km-suche', 'ruhend'); pg.wait_for_selector('#km-treffer:not([hidden]) .km-treffer-zeile')
    check('Kartensuche findet auch ausgeblendete (inaktive) Kunden', 'inaktiv' in pg.inner_text('#km-treffer'))
    pg.click('#km-treffer .km-treffer-zeile'); pg.wait_for_selector('#km-pop:not([hidden]) li.treffer')
    check('… Auswahl schaltet inaktive Kunden zu und hebt den Gebietsfilter auf', pg.is_checked('#km-nein') and pg.input_value('#km-gebiet') == '' and 'Ruhender Handel' in pg.inner_text('#km-pop li.treffer'))
    pg.fill('#km-suche', 'Alpen'); pg.wait_for_selector('#km-treffer:not([hidden]) .km-treffer-zeile'); pg.press('#km-suche', 'Enter')
    pg.wait_for_selector('#crm-toast.zeigen')
    check('Kartensuche: Kunde ohne Kartenpunkt (Ausland) – Hinweis statt Sprung', 'kein Kartenpunkt' in pg.text_content('#crm-toast'), pg.text_content('#crm-toast'))
    pg.fill('#km-suche', 'gibt es nicht'); pg.wait_for_selector('#km-treffer:not([hidden])')
    check('Kartensuche ohne Treffer: Hinweis', 'Kein Kunde gefunden' in pg.inner_text('#km-treffer'))
    pg.press('#km-suche', 'Escape'); pg.wait_for_selector('#km-treffer', state='hidden')
    pg.fill('#km-suche', ''); pg.uncheck('#km-nein'); pg.wait_for_function("document.querySelectorAll('#km-pts .pt').length === 5")
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
    pg.fill('#k-suche', 'fleischereien'); pg.wait_for_function("document.querySelectorAll('#k-tabelle tbody tr').length === 5")
    check('390 px: Kunden mit Kundengruppe ohne seitliches Scrollen der Seite', pg.evaluate("document.documentElement.scrollWidth") <= 390)
    pg.screenshot(path=os.path.join(SH, 'crm_kunden_390.png'), full_page=False)
    pg.fill('#k-suche', ''); pg.wait_for_function("document.querySelectorAll('#k-tabelle tbody tr').length > 5")
    pg.click('#k-tabelle button[data-oeffnen="kaaa111111111"]'); pg.wait_for_selector('#dlg-kunde[open] #verlauf li')
    check('390 px: Kundenblatt passt in die Breite', pg.evaluate("document.querySelector('#dlg-kunde').scrollWidth <= document.querySelector('#dlg-kunde').clientWidth + 1"))
    pg.screenshot(path=os.path.join(SH, 'crm_kundenblatt_390.png'), full_page=False)
    pg.click('#dlg-kunde [data-schliessen]')
    pg.click('#crm-tabs button[data-tab="karte"]'); pg.wait_for_selector('#km-pts .pt')
    pg.screenshot(path=os.path.join(SH, 'crm_karte_390.png'), full_page=False)
    ctx.close()
    br.close()

# ── Reiter „MHD-Ware“: MHD-Liste des Bestands und Käufer aus den Umsatzdaten ──
heute_d = dt.date.today()
tag = lambda n: (heute_d + dt.timedelta(days=n)).isoformat()   # noqa: E731
st, r = A.call('stock_import', {'date': heute_d.isoformat(), 'source': 'Test-MHD.xls', 'articles': [
    {'code': '700001', 'name': 'Test Abgelaufen', 'kg': 40.0, 'mhd': tag(-2), 'mhdKg': 15.5, 'lots': []},
    {'code': '700002', 'name': 'Test Bald <b>fett</b>', 'kg': 120.25, 'mhd': tag(3), 'mhdKg': 60.0, 'lots': []},
    {'code': '700003', 'name': 'Test Zwei Wochen', 'kg': 80.0, 'mhd': tag(10), 'mhdKg': 80.0, 'lots': []},
    {'code': '700004', 'name': 'Test Später', 'kg': 300.0, 'mhd': tag(30), 'mhdKg': 300.0, 'lots': []}], 'incoming': []})
check('MHD-Ware: Bestand mit MHD relativ zu heute übernommen', st == 200, r)
# Umsatzzeilen [Tag, Kunde, Artikel, Kolli, Menge (Tausendstel), Umsatz (Cent), EK, Umsatz mit EK, Positionen, berechnet]
ROH = [(-10, '900001', '700002', 50000, 1), (-40, '900001', '700002', 30000, 1), (-70, '900001', '700002', 20000, 1), (-10, '900001', '700002', 3000, 0),
       (-20, '900002', '700002', 10000, 1), (-15, '900002', '700002', -2000, 1), (-120, '900003', '700002', 5000, 1), (-5, '999999', '700002', 7000, 1),
       (-3, '900003', '700001', 4000, 1), (-8, '900002', '40100', 9000, 1), (-200, '900001', '700003', 1000, 1)]
MON = {}
for d_, k_, a_, m_, b_ in ROH:
    t_ = heute_d + dt.timedelta(days=d_)
    MON.setdefault(t_.strftime('%Y-%m'), []).append([t_.day, k_, a_, 1, m_, 123456 if b_ else 0, 0, 0, 1, b_])
if not storage_sqlite():
    os.makedirs(os.path.join(os.environ['UDATA'], 'controlling-umsatzdaten'), exist_ok=True)
for m_, z_ in MON.items():
    z_.sort(key=lambda r_: (r_[0], r_[1], r_[2], r_[9]))
    storage_write('controlling-umsatzdaten/' + m_, {'monat': m_, 'hash': '0' * 64, 'zeilen': z_})
storage_write('controlling-umsatzdaten', {'rev': 1, 'monate': {m_: {'hash': '0' * 64, 'zeilen': len(z_), 'ersterTag': z_[0][0], 'letzterTag': z_[-1][0]} for m_, z_ in sorted(MON.items())},
                                          'kunden': ['900001', '900002', '900003', '999999'], 'artikel': ['40100', '700001', '700002', '700003'], 'importe': []})
for u, n, r_, p_, extra in (('mia', 'Mia MHD', 'viewer', 'Mhd-Zugang-41', {'grant': ['crm.sehen', 'crm.mhd_ware']}),
                            ('max', 'Max Vertrieb', 'editor', 'Weg-Kennwort-42', {'grant': ['crm.bearbeiten', 'crm.mhd_ware']})):
    st, r = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r_, 'active': True, 'password': p_, 'mustChange': False, **extra})
    assert st == 200, r
MIA = Client('198.51.100.21'); MIA.call('login', {'username': 'mia', 'password': 'Mhd-Zugang-41'})
MAX = Client('198.51.100.22'); MAX.call('login', {'username': 'max', 'password': 'Weg-Kennwort-42'})
katalog = {x['key']: x for x in A.call('rechte')[1].get('catalog', [])}
check('Recht „CRM: MHD-Ware“ im Katalog (ohne Standardrolle, setzt CRM ansehen voraus)', katalog.get('crm.mhd_ware', {}).get('default') == [] and katalog['crm.mhd_ware'].get('requires') == ['crm.sehen'], katalog.get('crm.mhd_ware'))
check('MHD-Ware: crm_start meldet das Recht', MIA.call('crm_start')[1]['rechte']['mhd'] is True and V.call('crm_start')[1]['rechte']['mhd'] is False)
for wer, cl in (('nur CRM ansehen', V), ('ohne CRM-Recht', O), ('CRM bearbeiten ohne MHD-Ware', Bb)):
    check(f'MHD-Ware {wer}: 403', cl.call('crm_mhd')[0] == 403 and cl.call('crm_mhd_kaeufer&artikel=700002')[0] == 403)
check('MHD-Ware ohne Anmeldung: 401', N.call('crm_mhd')[0] == 401)
st, d = MIA.call('crm_mhd')
art = {a['code']: a for a in d.get('artikel', [])}
check('MHD-Liste: Artikel bis heute + 14 Tage, früheste zuerst, Stufen wie im Bestand', st == 200 and [a['code'] for a in d['artikel']] == ['700001', '700002', '700003']
      and [a['stufe'] for a in d['artikel']] == ['abgelaufen', '0-4', '8-14'] and art['700002']['mhdKg'] == 60.0, d.get('artikel'))
check('MHD-Liste: Zahl der Käufer in den letzten 3 Monaten (ohne Berechnung zählt nicht)', {c: a['kaeufer'] for c, a in art.items()} == {'700001': 1, '700002': 3, '700003': 0}
      and d['monate'] == 3 and d['bis'] == heute_d.isoformat(), {c: a['kaeufer'] for c, a in art.items()})
check('MHD-Liste ohne Preise und Beträge', 'preis' not in json.dumps(d) and 'umsatz"' not in json.dumps(d).replace('umsatzBis"', '') and '123456' not in json.dumps(d))
check('MHD-Liste: Artikel der Umsatzdaten für die Suche', {a['nr'] for a in d['alle']} == {'40100', '700001', '700002', '700003'})
check('MHD-Liste 6 Monate: ein Käufer mehr, ungültiger Zeitraum → 3 Monate', {a['code']: a['kaeufer'] for a in MIA.call('crm_mhd&monate=6')[1]['artikel']}['700002'] == 4
      and MIA.call('crm_mhd&monate=99')[1]['monate'] == 3)
st, k = MIA.call('crm_mhd_kaeufer&artikel=700002')
kk = {x['kunde']: x for x in k.get('kaeufer', [])}
check('Käufer: neuester Kauf zuerst, Kunde ohne Stammsatz ohne Kundenblatt', st == 200 and [x['kunde'] for x in k['kaeufer']] == ['999999', '900001', '900002']
      and kk['999999']['key'] is None and kk['900001']['key'] == 'kaaa111111111', k.get('kaeufer'))
check('Käufer: Käufe = Liefertage, Menge mit Gutschrift, letzter Kauf', kk['900001']['kaeufe'] == 3 and kk['900001']['menge'] == 100000 and kk['900001']['zuletzt'] == tag(-10)
      and kk['900002']['kaeufe'] == 1 and kk['900002']['menge'] == 8000 and kk['900002']['zuletzt'] == tag(-20), kk)
check('Käufer: Artikel mit MHD aus der Liste, keine Beträge', k['artikel']['mhd'] == tag(3) and k['artikel']['stufe'] == '0-4' and '123456' not in json.dumps(k) and 'umsatz"' not in json.dumps(k).replace('umsatzBis"', ''))
st, k = MIA.call('crm_mhd_kaeufer&artikel=40100&monate=12')
check('Käufer eines anderen Artikels (nicht in der MHD-Liste)', st == 200 and [x['kunde'] for x in k['kaeufer']] == ['900002'] and k['artikel']['mhd'] is None, k)
check('Käufer: ungültiger Artikel → 422', MIA.call('crm_mhd_kaeufer&artikel=' + 'x%3By')[0] == 422)
WV = {'artikel': '700002', 'kunden': ['kccc333333333', 'kfff666666666'], 'datum': tag(2)}
check('Wiedervorlage: nur mit CRM bearbeiten → 403', MIA.call('crm_mhd_wiedervorlage', WV)[0] == 403)
check('Wiedervorlage: nur mit MHD-Ware → 403', Bb.call('crm_mhd_wiedervorlage', WV)[0] == 403)
Bb.call('crm_kunde_save', {'key': 'kfff666666666', 'felder': {'naechsterSchritt': 'Rückruf', 'wiedervorlage': tag(1)}})
st, r = MAX.call('crm_mhd_wiedervorlage', WV)
blatt = (dokument('crm-kunden') or {}).get('eintraege', {})
soll = f'MHD-Ware anbieten: Test Bald <b>fett</b> (700002), MHD {tag(3)[8:10]}.{tag(3)[5:7]}.'
check('Wiedervorlage angelegt: Text vom Server (Artikel, Nummer, MHD), Datum', st == 200 and r['anzahl'] == 2 and blatt['kccc333333333']['naechsterSchritt'] == soll
      and blatt['kccc333333333']['wiedervorlage'] == tag(2) and len(r['kunden']) == 2, (st, r.get('error'), blatt.get('kccc333333333')))
check('Wiedervorlage: bestehender Schritt bleibt dahinter, frühere Wiedervorlage bleibt', blatt['kfff666666666']['naechsterSchritt'] == soll + ' · Rückruf'
      and blatt['kfff666666666']['wiedervorlage'] == tag(1), blatt.get('kfff666666666'))
akt = lambda key: [a_ for a_ in dokument('crm-aktivitaeten')['liste'] if a_['key'] == key and a_['notiz'] == soll]   # noqa: E731
check('Wiedervorlage: Notiz im Verlauf mit Schnappschuss (Firma, Nummer), letzter Kontakt unverändert', len(akt('kccc333333333')) == 1 and akt('kccc333333333')[0]['art'] == 'Notiz'
      and akt('kccc333333333')[0]['nr'] == '900003' and akt('kccc333333333')[0]['firma'] == 'Probe Markt Ost' and not blatt['kccc333333333'].get('letzterKontakt'), akt('kccc333333333'))
MAX.call('crm_mhd_wiedervorlage', WV)
blatt = dokument('crm-kunden')['eintraege']
check('Wiedervorlage erneut: Schritt und Notiz nicht doppelt', blatt['kfff666666666']['naechsterSchritt'] == soll + ' · Rückruf' and blatt['kccc333333333']['naechsterSchritt'] == soll
      and len(akt('kccc333333333')) == 1 and len(akt('kfff666666666')) == 1)
lang = 'Langer eigener Schritt ' + 'x' * 120
Bb.call('crm_kunde_save', {'key': 'kddd444444444', 'felder': {'naechsterSchritt': lang}})
st, r = MAX.call('crm_mhd_wiedervorlage', {**WV, 'kunden': ['kddd444444444'], 'datum': tag(5)})
blatt = dokument('crm-kunden')['eintraege']
check('Wiedervorlage: langer eigener Schritt bleibt ungekürzt, Hinweis steht im Verlauf', st == 200 and blatt['kddd444444444']['naechsterSchritt'] == lang
      and blatt['kddd444444444']['wiedervorlage'] == tag(5) and len(akt('kddd444444444')) == 1, (st, blatt.get('kddd444444444')))
st, r = MAX.call('crm_mhd_wiedervorlage', {**WV, 'kunden': ['kfff666666666'], 'datum': tag(0)})
blatt = dokument('crm-kunden')['eintraege']
eintrag = [e for e in (dokument('protokoll/' + dt.datetime.now(dt.timezone.utc).strftime('%Y-%m')) or []) if e.get('s') == 'CRM: Wiedervorlage für MHD-Ware (1 Kunde)'][-1:]
check('Wiedervorlage früher: Datum vorgezogen, alter Wert im Protokoll', st == 200 and blatt['kfff666666666']['wiedervorlage'] == tag(0)
      and any(x.get('f') == 'Wiedervorlage am' and x.get('from') == tag(1) and x.get('to') == tag(0) for x in (eintrag[0].get('d', []) if eintrag else [])), eintrag)
for b_, code_ in (({**WV, 'kunden': []}, 422), ({**WV, 'kunden': ['kunbekannt99']}, 404), ({**WV, 'datum': '2026-02-30'}, 422), ({**WV, 'artikel': 'a;b'}, 422),
                  ({**WV, 'kunden': ['kccc333333333'] * 301}, 422)):
    check(f'Wiedervorlage ungültig → {code_}', MAX.call('crm_mhd_wiedervorlage', b_)[0] == code_)
log = [e for e in (dokument('protokoll/' + dt.datetime.now(dt.timezone.utc).strftime('%Y-%m')) or []) if e.get('a') == 'crm' and 'MHD-Ware' in e.get('s', '')]
check('Wiedervorlage im Protokoll (Anzahl, ohne Kunden)', any(e['s'] == 'CRM: Wiedervorlage für MHD-Ware (2 Kunden)' for e in log) and 'Probe Markt' not in json.dumps(log, ensure_ascii=False), log[-2:])

with sync_playwright() as p:
    br = p.chromium.launch()
    for breite, thema in ((1280, 'light'), (390, 'dark')):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': '198.51.100.22'}, locale='de-DE', timezone_id='Europe/Berlin', color_scheme=thema)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e))); pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'max'); pg.fill('#pw1', 'Weg-Kennwort-42'); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/crm/#mhd'); pg.wait_for_selector('#mhd-liste [data-mhd-artikel]')
        pg.wait_for_selector('#mhd-tabelle tbody tr')
        check(f'{breite}px: Reiter MHD-Ware sichtbar, Artikel in den Farben der MHD-Liste', pg.is_visible('#crm-tabs [data-tab="mhd"]') and pg.locator('#mhd-liste .crm-mhd-artikel').count() == 3
              and pg.get_attribute('#mhd-liste .crm-mhd-artikel >> nth=0', 'class').endswith('vorbei') and 'rot' in pg.get_attribute('#mhd-liste .crm-mhd-artikel >> nth=1', 'class')
              and '<b>fett</b>' in pg.text_content('#mhd-liste'))
        check(f'{breite}px: zuerst der dringendste Artikel mit seinen Käufern', pg.get_attribute('#mhd-liste .crm-mhd-artikel >> nth=0', 'aria-pressed') == 'true' and pg.locator('#mhd-tabelle tbody tr').count() == 1)
        pg.click('#mhd-liste [data-mhd-artikel="700002"]')
        pg.wait_for_function("document.querySelectorAll('#mhd-tabelle tbody tr').length === 3")
        t = pg.text_content('#mhd-kaeufer')
        check(f'{breite}px: Käufer mit Telefon und Kunde ohne Stammsatz', '040 1234567' in t and 'nicht in den Kundenstammdaten' in t and 'Musterfleischerei Nord GmbH' in t and '€' not in t, t[:300])
        pg.click('[data-mhd-monate="6"]')
        pg.wait_for_function("document.querySelectorAll('#mhd-tabelle tbody tr').length === 4")
        check(f'{breite}px: 6 Monate – ein Käufer mehr', 'Probe Markt Ost' in pg.text_content('#mhd-tabelle'))
        pg.select_option('#mhd-vertreter', '12')
        pg.wait_for_function("document.querySelectorAll('#mhd-tabelle tbody tr').length === 1")
        check(f'{breite}px: Filter Vertreter', 'Beispiel Catering KG' in pg.text_content('#mhd-tabelle'))
        pg.select_option('#mhd-vertreter', '')
        pg.check('#mhd-regel')
        pg.wait_for_function("document.querySelectorAll('#mhd-tabelle tbody tr').length === 1")
        check(f'{breite}px: „kauft regelmäßig“ (ab 3 Käufen)', 'Musterfleischerei Nord GmbH' in pg.text_content('#mhd-tabelle'))
        pg.uncheck('#mhd-regel')
        pg.wait_for_function("document.querySelectorAll('#mhd-tabelle tbody tr').length === 4")
        if breite == 1280:
            pg.screenshot(path=os.path.join(SH, 'crm_mhd_1280.png'), full_page=True)
            pg.check('[data-mhd-wahl="kbbb222222222"]')
            check('Auswahl zählt, Knopf aktiv', pg.text_content('#mhd-gewaehlt') == '1 Kunde ausgewählt' and pg.is_enabled('#mhd-wv'))
            pg.click('#mhd-wv')
            pg.wait_for_function("document.querySelector('#crm-toast').textContent.includes('Wiedervorlage für 1 Kunden angelegt')")
            pg.wait_for_selector('#mhd-tabelle .crm-mhd-schritt')
            check('Wiedervorlage über die Oberfläche: Schritt in der Zeile', 'MHD-Ware anbieten' in pg.text_content('#mhd-tabelle'))
            pg.fill('#mhd-suche', '40100')
            pg.click('.crm-mhd-treffer [data-mhd-artikel="40100"]')
            pg.wait_for_function("document.querySelector('#mhd-kaeufer h2') && document.querySelector('#mhd-kaeufer h2').textContent.includes('40100')")
            pg.wait_for_selector('#mhd-tabelle tbody tr')
            check('Suche nach anderem Artikel: seine Käufer', 'Nicht in der MHD-Liste' in pg.text_content('#mhd-kaeufer') and 'Beispiel Catering KG' in pg.text_content('#mhd-tabelle'))
            pg.click('#mhd-tabelle button[data-oeffnen="kbbb222222222"]'); pg.wait_for_selector('#dlg-kunde[open]')
            check('Kundenblatt aus der Käuferliste', 'Beispiel Catering KG' in pg.text_content('#kunde-titel'))
            pg.click('#dlg-kunde [data-schliessen]')
        else:
            bw = pg.evaluate('document.documentElement.scrollWidth')
            check('390px dunkel: MHD-Ware ohne seitliches Scrollen der Seite', bw <= 390, bw)
            pg.screenshot(path=os.path.join(SH, 'crm_mhd_390.png'), full_page=True)
        ctx.close()
    ctx = br.new_context(viewport={'width': 1280, 'height': 900}, extra_http_headers={'X-Forwarded-For': '198.51.100.3'})
    pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', 'verena'); pg.fill('#pw1', 'Leserin-Zugang-1'); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
    pg.goto(B + '/module/crm/#mhd'); pg.wait_for_selector('#crm-app:not([hidden])')
    check('ohne Recht MHD-Ware: Reiter ausgeblendet, Start im Cockpit', pg.is_hidden('#crm-tabs [data-tab="mhd"]') and pg.is_visible('#tab-cockpit'))
    ctx.close()
    br.close()

check('keine JavaScript-Fehler', not fehler, fehler)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
