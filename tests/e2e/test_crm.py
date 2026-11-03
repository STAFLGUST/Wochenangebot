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
Cockpit (crm_cockpit) und Übersicht im Kunden-Pop-up (crm_kunde_umsatz): Mein Cockpit (Vertreter am Mitarbeiter, Vertreter 2 zählt),
Master-Cockpit (crm.master: Vergleich, Ansicht je Vertreter, ohne Vertreter, Umsatz ohne Stammsatz), Summen gegen die Testzeilen,
Signale (Bestellpause = Regel der Umsatzstatistik, kauft weniger, Artikel weg, neu), Rechte € und kg einzeln (nichts davon in der
Antwort), nie EK/DB/Spanne; Oberfläche (Umschalter, Vertreter-Auswahl, Pop-up-Reiter, Kundenliste „Meine Kunden · Alle · Mit
Signal“, Handy-Karten, dunkel). Einzelangebot beim Kunden (crm_einzel_*): Rechte (einzelangebote.sehen/bearbeiten und crm.sehen),
Kunde aus dem Pop-up, fremde Angebote 404, gleiche Prüfungen und Protokoll wie im Eingabebereich, Freigabe, PDF, Löschen, Bestätigung
beim Versand; Oberfläche (Reiter „Angebote“, Artikelsuche, Summe, Speichern, Freigabe, Warnung beim Schließen, 1280/390 px).
Nur synthetische Testdaten.

Testdaten: Vertreter 11 Vera Vertrieb, 12 Tom Tour; Kundengruppe 5 Fleischereien Nord. Kunden 900001 Musterfleischerei Nord
(Hamburg, Kundenzugang, Angebot std), 900002 Beispiel Catering (Kiel, Vertreter 12 und 11), 900003 Probe Markt Ost (Dresden,
PLZ ohne führende 0), 900004 Alpen Feinkost (Österreich, kein Kartenpunkt), 900005 Ruhender Handel (inaktiv), 900006 Test-Gastro
Süd (ohne Vertreter). Nutzer: verena (sehen), bert (bearbeiten), xena (bearbeiten und exportieren), otto (ohne Recht), nora
(sehen); für die MHD-Ware mia (sehen und MHD-Ware) und max (bearbeiten und MHD-Ware). MHD-Ware: Bestand relativ zu heute
(700001 abgelaufen, 700002 in 3 Tagen, 700003 in 10 Tagen, 700004 in 30 Tagen = nicht in der Liste) und Umsatzzeilen ROH
relativ zu heute (Käufe vor 10/40/70/120/200 Tagen für 3/6/12 Monate, Gutschrift, ohne Berechnung, Kunde 999999 ohne Stammsatz).
Cockpit: Umsatzzeilen über zwei Jahre bis zum Stand (heute − 2), wöchentlich: 900001 kauft 40100 seit 70 Tagen nicht mehr, 900002
seit 35 Tagen nichts (Bestellpause), 900003 kauft −50 % zum Vorjahr, 900006 neu (vor 20 Tagen), 999999 ohne Stammsatz, Leergut;
EK-Werte als Erkennungszahl (777777/888888). Nutzer vv (Vertreter 11), gf (Master), vk (nur kg), vn (ohne € und kg).
"""
import datetime as dt
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

from auth_helpers import expire_session
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
check('crm.sehen: Start ok, ohne Bearbeiten/Export; Umsätze in € und Mengen in kg Standard an, kein Master-Cockpit', st == 200
      and d['rechte'] == {'bearbeiten': False, 'exportieren': False, 'stammdaten': False, 'mhd': False, 'euro': True, 'kg': True, 'master': False, 'einzel': False, 'einzelBearbeiten': False}
      and d['ich'] == '', d.get('rechte'))
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
check('Administrator: alle Rechte inkl. Stammdaten-Verweis und Master-Cockpit', st == 200
      and d['rechte'] == {'bearbeiten': True, 'exportieren': True, 'stammdaten': True, 'mhd': True, 'euro': True, 'kg': True, 'master': True, 'einzel': True, 'einzelBearbeiten': True}, d.get('rechte'))

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
Bb.call('crm_interessent_save', {'firma': '\x01\t=HYPERLINK("http://x.example")', 'ort': 'Kiel'})   # auch nach Steuerzeichen/Tabulator
check('Stammdaten weiterhin unverändert', storage_raw('kunden') == kunden_vorher)

# ── CSV-Export ──
st, _, body = X.call('crm_export', {}, raw=True)
zeilen = body.lstrip('﻿').splitlines()
check('CSV: Kopf, alle Kunden und Interessenten', st == 200 and zeilen[0].startswith('"Art";"Kundennummer";"Firma"') and len(zeilen) == 1 + 6 + 2, (st, zeilen[:2], len(zeilen)))
check('CSV: Kundenblatt-Werte (Segment, Wann, Komma-Zahlen, weitere Ansprechpartner)', any('"Musterfleischerei Nord GmbH"' in z and '"Fleischerei"' in z and '"Dienstag - wöchentlich"' in z
      and '"120,5"' in z for z in zeilen) and any('Clara Koch, Küchenchefin' in z for z in zeilen))
check('CSV: keine Formeln (Zelle beginnt nicht mit =, auch nicht nach Tabulator)', any('"\'=HYPERLINK' in z for z in zeilen) and not any(';"=' in z or ';"\t' in z for z in zeilen))
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
    pg.wait_for_selector('#tab-cockpit .crm-ck-kpis')
    kp = pg.inner_text('#tab-cockpit')
    check('Cockpit ohne zugeordneten Vertreter: Hinweis, Kennzahlen, Heute dran (Wiedervorlagen), letzte Aktivität, keine Umsätze', 'Aktive Kunden' in kp
          and 'Angebot nachfassen' in kp and 'Muster schicken' in kp and 'Erstgespräch vor Ort' in kp and 'kein Vertreter zugeordnet' in kp and '€' not in kp, kp[:500])
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

    # Kunden-Pop-up: Übersicht (ohne Umsatzdaten: Hinweis), Kundenblatt, Verlauf
    pg.click('#k-tabelle button[data-oeffnen="kaaa111111111"]'); pg.wait_for_selector('#dlg-kunde[open] [data-ku-panel="uebersicht"]:not([hidden])')
    pg.wait_for_function("document.querySelector('[data-ku-panel=\"uebersicht\"]').textContent.includes('Noch keine Umsatzdaten')")
    check('Pop-up: Reiter Übersicht · Kundenblatt · Verlauf, Übersicht zuerst (ohne Umsatzdaten mit Hinweis)', [t.strip() for t in pg.eval_on_selector_all('#kunde-reiter [data-ku-tab]', 'b => b.map((x) => x.childNodes[0].textContent)')] == ['Übersicht', 'Kundenblatt', 'Verlauf']
          and 'nächster schritt' in pg.inner_text('[data-ku-panel="uebersicht"]').lower() and 'Angebot nachfassen' in pg.inner_text('[data-ku-panel="uebersicht"]'))
    pg.click('#kunde-reiter [data-ku-tab="kundenblatt"]'); pg.wait_for_selector('#kunde-inhalt [data-ku-panel="kundenblatt"]:not([hidden])')
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
    pg.click('#kunde-aktionen [data-ku-tab="verlauf"]'); pg.wait_for_selector('#dlg-kunde[open] #verlauf li')
    check('Knopf „Aktivität“ im Kopf öffnet den Verlauf mit dem Eingabefeld', pg.evaluate("document.activeElement.id") == 'akt-notiz')
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
    # „Wann“ bedient sich wie jedes Menü: Escape schließt (Fokus zurück), ein Klick daneben ebenso
    pg.click('#wv-wann summary'); pg.wait_for_selector('#wv-wann[open]')
    pg.keyboard.press('Escape'); pg.wait_for_function("!document.querySelector('#wv-wann').open")
    check('Filter „Wann“: Escape schließt die Auswahl, Fokus auf dem Titel', pg.evaluate("document.activeElement.matches('#wv-wann summary')"))
    pg.click('#wv-wann summary'); pg.wait_for_selector('#wv-wann[open]')
    pg.click('.crm-kopf .crm-modul'); pg.wait_for_function("!document.querySelector('#wv-wann').open")
    check('Filter „Wann“: Klick daneben schließt die Auswahl', True)
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
    check('390 px: Wiedervorlagen als Karten – nichts abgeschnitten oder innen seitlich verschoben', pg.is_hidden('#wv-tabelle thead')
          and pg.evaluate("[...document.querySelectorAll('#wv-tabelle tbody tr')].every((t) => t.scrollWidth <= t.clientWidth + 1 && getComputedStyle(t).display === 'grid')")
          and pg.evaluate("document.querySelector('#wv-rahmen').scrollWidth <= document.querySelector('#wv-rahmen').clientWidth + 1"))
    pg.screenshot(path=os.path.join(SH, 'crm_wiedervorlagen_390.png'), full_page=False)
    pg.click('#crm-tabs button[data-tab="kunden"]'); pg.wait_for_selector('#k-tabelle')
    pg.fill('#k-suche', 'fleischereien'); pg.wait_for_function("document.querySelectorAll('#k-tabelle tbody tr').length === 5")
    check('390 px: Kunden mit Kundengruppe ohne seitliches Scrollen der Seite', pg.evaluate("document.documentElement.scrollWidth") <= 390)
    check('390 px: Kundenliste als Karten (Firma, Segment, Phase, Vertreter, nächster Schritt) ohne inneres Seitwärtsscrollen', pg.is_hidden('#k-tabelle thead')
          and pg.evaluate("[...document.querySelectorAll('#k-tabelle tbody tr')].every((t) => t.scrollWidth <= t.clientWidth + 1 && getComputedStyle(t).display === 'grid')")
          and pg.evaluate("document.querySelector('#k-tabelle').scrollWidth <= document.querySelector('#k-tabelle').parentElement.clientWidth + 1"))
    pg.screenshot(path=os.path.join(SH, 'crm_kunden_390.png'), full_page=False)
    pg.fill('#k-suche', ''); pg.wait_for_function("document.querySelectorAll('#k-tabelle tbody tr').length > 5")
    pg.click('#k-tabelle button[data-oeffnen="kaaa111111111"]'); pg.wait_for_selector('#dlg-kunde[open] [data-ku-panel="uebersicht"]:not([hidden])')
    pg.click('#kunde-reiter [data-ku-tab="kundenblatt"]'); pg.wait_for_selector('#kunde-inhalt [data-ku-panel="kundenblatt"]:not([hidden])')
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

# ── Cockpit je Verkäufer, Master-Cockpit und Übersicht im Kunden-Pop-up (Umsätze über das Controlling, Inhaber 01.11.2026) ──
# Umsatzzeilen relativ zum Stand E (= heute − 2): wöchentliche Käufe über zwei Jahre (t = Tage vor E)
E = heute_d - dt.timedelta(days=2)
ZEILEN = []   # (Datum, Kunde, Artikel, Menge in Tausendstel kg, Umsatz in Cent, berechnet)
for t in range(0, 729, 7):
    ZEILEN.append((t, '900001', '700002', 50000, 60000, 1))                        # 12 €/kg, jede Woche
    if t >= 70:
        ZEILEN.append((t, '900001', '40100', 5000, 10000, 1))                      # seit 70 Tagen nicht mehr → „Artikel weg“
    if t >= 30:
        ZEILEN.append((t, '900002', '700002', 30000, 30000, 1))                    # seit 35 Tagen nichts → Bestellpause
    ZEILEN.append((t, '900003', '700002', 25000 if t <= 90 else 50000, 25000 if t <= 90 else 50000, 1))   # 10 €/kg, −50 % → kauft weniger
    if t % 14 == 0:
        ZEILEN.append((t, '999999', '700002', 10000, 10000, 1))                    # ohne Kundenstammsatz
for t in (20, 13, 6):
    ZEILEN.append((t, '900006', '700003', 10000, 15000, 1))                        # erster Kauf vor 20 Tagen → neu
ZEILEN.append((0, '900001', '90000', 99000, 0, 0))                                  # Leergut ohne Berechnung: zählt nie
MON = {}
for t_, k_, a_, m_, u_, b_ in ZEILEN:
    d_ = E - dt.timedelta(days=t_)
    MON.setdefault(d_.strftime('%Y-%m'), []).append([d_.day, k_, a_, 1, m_, u_, 777777 if b_ else 0, 888888 if b_ else 0, 1, b_])
for m_, z_ in MON.items():
    z_.sort(key=lambda r_: (r_[0], r_[1], r_[2], r_[9]))
    storage_write('controlling-umsatzdaten/' + m_, {'monat': m_, 'hash': '0' * 64, 'zeilen': z_})
storage_write('controlling-umsatzdaten', {'rev': 2, 'monate': {m_: {'hash': '0' * 64, 'zeilen': len(z_), 'ersterTag': z_[0][0], 'letzterTag': z_[-1][0]} for m_, z_ in sorted(MON.items())},
                                          'kunden': ['900001', '900002', '900003', '900006', '999999'], 'artikel': ['40100', '700002', '700003', '90000'], 'importe': []})


def vj(d_):
    try:
        return d_.replace(year=d_.year - 1)
    except ValueError:
        return d_.replace(year=d_.year - 1, day=28)


def summe(kunden, von, bis):
    u = m = 0
    for t_, k_, a_, m_, u_, b_ in ZEILEN:
        d_ = E - dt.timedelta(days=t_)
        if b_ and k_ in kunden and von <= d_ <= bis:
            u += u_; m += m_
    return {'umsatz': u, 'menge': m}


J365 = (E - dt.timedelta(days=364), E)
MONAT = (E.replace(day=1), E)
VJMONAT = (vj(E).replace(day=1), vj(E))
VERA = {'900001', '900002', '900003'}   # Vertreter 11 oder Vertreter 2 = 11 (900004/900005 ohne Umsätze)
for u, n, r_, p_, extra in (('vv', 'Vera Verkauf', 'viewer', 'Editor-Zugang-77', {'grant': ['crm.sehen'], 'vertreter': '11'}),
                            ('gf', 'Gesa Führung', 'editor', 'Konto-Passwort-9', {'grant': ['crm.master']}),
                            ('vk', 'Karl Kilo', 'viewer', 'Merk-Kennwort-31', {'grant': ['crm.sehen'], 'deny': ['crm.umsatz_euro'], 'vertreter': '11'}),
                            ('vn', 'Nina Ohnezahl', 'viewer', 'Weg-Kennwort-42', {'grant': ['crm.sehen'], 'deny': ['crm.umsatz_euro', 'crm.umsatz_kg'], 'vertreter': '11'})):
    st, r = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r_, 'active': True, 'password': p_, 'mustChange': False, **extra})
    assert st == 200, r
VV = Client('198.51.100.31'); VV.call('login', {'username': 'vv', 'password': 'Editor-Zugang-77'})
GF = Client('198.51.100.32'); GF.call('login', {'username': 'gf', 'password': 'Konto-Passwort-9'})
VK = Client('198.51.100.33'); VK.call('login', {'username': 'vk', 'password': 'Merk-Kennwort-31'})
VN = Client('198.51.100.34'); VN.call('login', {'username': 'vn', 'password': 'Weg-Kennwort-42'})
st, d = VV.call('crm_start')
check('crm_start: eigener Vertreter und Rechte € und kg, kein Master', st == 200 and d['ich'] == '11' and d['rechte']['euro'] and d['rechte']['kg'] and not d['rechte']['master'])
check('Cockpit ohne Anmeldung 401, ohne CRM-Recht 403', N.call('crm_cockpit')[0] == 401 and O.call('crm_cockpit')[0] == 403 and O.call('crm_kunde_umsatz&key=kaaa111111111')[0] == 403)
st, c = VV.call('crm_cockpit')
z = c.get('kennzahlen') or {}
sig = {(x['nr'], x['art']): x for x in c.get('signale', [])}
check('Mein Cockpit: Ansicht des eigenen Vertreters (Vertreter oder Vertreter 2), Stand = letzter Tag der Umsatzdaten', st == 200 and c['ansicht'] == 'vertreter' and c['vertreter'] == '11'
      and c['stand'] == E.isoformat() and z['kunden'] == 4 and z['mitKauf'] == 3, (st, c.get('ansicht'), c.get('stand'), z.get('kunden')))
check('Mein Cockpit: 365 Tage, Monat und Vorjahresmonat bis zum Stand = Summe der eigenen Kunden (ohne Leergut)', z['j365'] == summe(VERA, *J365) and z['monat'] == summe(VERA, *MONAT)
      and z['vjMonat'] == summe(VERA, *VJMONAT) and z['jahr'] == summe(VERA, dt.date(E.year, 1, 1), E), (z.get('j365'), summe(VERA, *J365)))
check('Signale: Bestellpause (gleiche Regel wie die Umsatzstatistik) mit üblichem Monatsumsatz', ('900002', 'pause') in sig and sig[('900002', 'pause')]['pause'] == 35
      and sig[('900002', 'pause')]['abstand'] == 7 and sig[('900002', 'pause')]['umsatzMonat'] > 0 and sig[('900002', 'pause')]['key'] == 'kbbb222222222', sig.get(('900002', 'pause')))
w3 = sig.get(('900003', 'weniger'), {})
check('Signale: kauft weniger – 3 Monate −50 % Menge zum Vorjahr, vor allem der Artikel', w3.get('anteil') == -0.5 and w3.get('basis') == 'vorjahr'
      and w3.get('vorAllem', {}).get('nr') == '700002' and w3.get('menge') == 13 * 25000, w3)
wg = sig.get(('900001', 'weg'), {})
check('Signale: Artikel nicht mehr gekauft (40100 seit 70 Tagen, sonst wöchentlich), Kunde kauft weiter', wg.get('anzahl') == 1 and wg['artikel'][0]['nr'] == '40100'
      and wg['artikel'][0]['pause'] == 70 and wg['artikel'][0]['abstand'] == 7, wg)
check('Signale: nur eigene Kunden (neuer Kunde ohne Vertreter fehlt), nie Kunden ohne Stammsatz', not any(k_ in ('900006', '999999') for k_, _ in sig) and ('900001', 'weniger') not in sig, sorted(sig))
check('Top-Kunden: nach Umsatz, mit 12 Monaten und letztem Kauf', [t_['nr'] for t_ in c['top']] == ['900001', '900003', '900002'] and c['top'][0]['j365'] == summe({'900001'}, *J365) and len(c['top'][0]['reihe']) == 12
      and c['top'][1]['zuletzt'] == E.isoformat() and c['top'][2]['zuletzt'] == (E - dt.timedelta(days=35)).isoformat(), [t_['nr'] for t_ in c['top']])
roh = json.dumps(c)
check('Cockpit ohne Einkaufswerte, DB oder Spanne', '777777' not in roh and '888888' not in roh and '"ek' not in roh.lower() and 'spanne' not in roh.lower())
check('Verkäufer ohne Master: andere Vertreter und Master → 403', VV.call('crm_cockpit&vertreter=12')[0] == 403 and VV.call('crm_cockpit&vertreter=alle')[0] == 403
      and VV.call('crm_cockpit&vertreter=_')[0] == 403 and VV.call('crm_cockpit&vertreter=11')[0] == 200)
st, c = V.call('crm_cockpit')
check('ohne zugeordneten Vertreter und ohne Master: Ansicht „ohne“ – keine Zahlen', st == 200 and c['ansicht'] == 'ohne' and c['kennzahlen'] is None and c['signale'] == [] and c['top'] == []
      and V.call('crm_cockpit&vertreter=11')[0] == 403)
st, c = GF.call('crm_cockpit')
z = c.get('kennzahlen') or {}
vg = {x['nr']: x for x in c.get('vergleich') or []}
ALLE = {'900001', '900002', '900003', '900006', '999999'}
check('Master-Cockpit (crm.master, ohne eigenen Vertreter): alle Kunden inkl. Umsatz ohne Stammsatz', st == 200 and c['ansicht'] == 'master' and z['j365'] == summe(ALLE, *J365)
      and z['ohneStammsatz'] == 1 and z['kunden'] == 5, (st, c.get('ansicht'), z))
check('Master: Vertreter im Vergleich – Kunden mit zwei Vertretern zählen bei beiden, „ohne Vertreter“', set(vg) == {'11', '12', '_'} and vg['11']['j365'] == summe(VERA, *J365)
      and vg['12']['j365'] == summe({'900002'}, *J365) and vg['_']['j365'] == summe({'900006'}, *J365) and vg['11']['kunden'] == 4 and vg['_']['kunden'] == 1
      and vg['11']['signale'] == {'pause': 1, 'weniger': 2, 'weg': 1, 'neu': 0} and vg['_']['signale']['neu'] == 1 and vg['11']['monat'] == summe(VERA, *MONAT), vg)
check('Master: Signal „neu dabei“ (erster Kauf vor 20 Tagen, 3 Lieferungen)', any(x['nr'] == '900006' and x['art'] == 'neu' and x['erster'] == (E - dt.timedelta(days=20)).isoformat() and x['kauftage'] == 3 for x in c['signale']))
st, c = GF.call('crm_cockpit&vertreter=12')
check('Master: Ansicht eines Vertreters (12: nur Beispiel Catering)', st == 200 and c['ansicht'] == 'vertreter' and c['vertreter'] == '12' and c['kennzahlen']['j365'] == summe({'900002'}, *J365)
      and c['vergleich'] is None and {x['nr'] for x in c['signale']} == {'900002'})
st, c = GF.call('crm_cockpit&vertreter=_')
check('Master: Kunden ohne Vertreter', st == 200 and c['ansicht'] == 'ohne_vertreter' and c['kennzahlen']['j365'] == summe({'900006'}, *J365))
check('Master: unbekannter Vertreter 404, ungültige Angabe 422', GF.call('crm_cockpit&vertreter=99')[0] == 404 and GF.call('crm_cockpit&vertreter=' + 'a%3Bb')[0] == 422)
check('Administrator: Master-Cockpit', A.call('crm_cockpit')[1].get('ansicht') == 'master')
st, c = VK.call('crm_cockpit')
roh = json.dumps(c)
check('Nur kg (€ verboten): keine Umsätze im Cockpit, Mengen ja, Top-Kunden nach Menge', st == 200 and '"umsatz' not in roh and c['kennzahlen']['j365'] == {'menge': summe(VERA, *J365)['menge']}
      and [t_['nr'] for t_ in c['top']] == ['900001', '900003', '900002'] and 'mengeMonat' in json.dumps([x for x in c['signale'] if x['art'] == 'pause']), roh[:300])
st, c = VN.call('crm_cockpit')
roh = json.dumps(c)
check('Ohne € und kg: Signale ja (mit Prozent), aber keine Beträge, Mengen oder Rangliste', st == 200 and '"umsatz' not in roh and '"menge' not in roh and c['top'] == []
      and c['kennzahlen']['j365'] == {} and any(x['art'] == 'weniger' and x['anteil'] == -0.5 for x in c['signale']), roh[:300])
# Übersicht im Kunden-Pop-up
st, u = VV.call('crm_kunde_umsatz&key=kaaa111111111')
k = u.get('kunde') or {}
art = {a['nr']: a for a in k.get('artikel', [])}
check('Pop-up: 365 Tage mit Vorjahr, letzter Kauf, Rhythmus (alle 7 Tage, Wochentag)', st == 200 and k['w']['j365'] == summe({'900001'}, *J365)
      and k['w']['v365'] == summe({'900001'}, E - dt.timedelta(days=729), E - dt.timedelta(days=365)) and k['zuletzt'] == E.isoformat()
      and k['rhythmus']['abstand'] == 7 and k['rhythmus']['wochentage'] == [E.isoweekday()], (st, k.get('w'), k.get('rhythmus')))
check('Pop-up: 12 Monate mit Vorjahr', len(k['monate']) == 12 and k['monate'][-1]['monat'] == E.strftime('%Y-%m') and k['monate'][-1]['jetzt']['umsatz'] > 0)
check('Pop-up: Top-Artikel mit Vorjahr und Ø Preis aller Kunden (Cent je kg), Leergut nicht dabei', list(art) == ['700002', '40100'] and art['700002']['j365']['menge'] > 0
      and 0 < art['700002']['preisAlle'] < 1200 and '90000' not in art, k.get('artikel'))
check('Pop-up: Preisniveau – zahlt mehr als der Ø aller Kunden', k['preisniveau'] is not None and k['preisniveau'] > 0, k.get('preisniveau'))
check('Pop-up: Auffällig – Artikel 40100 nicht mehr gekauft', [a['nr'] for a in k['auffaellig']['weg']] == ['40100'] and k['auffaellig']['weniger'] == [] and k['signale'][0]['art'] == 'weg')
st, u = VV.call('crm_kunde_umsatz&key=kccc333333333')
k = u.get('kunde') or {}
check('Pop-up: Signal „kauft weniger“ und Artikel „kauft weniger“ (−50 %)', any(x['art'] == 'weniger' for x in k['signale']) and k['auffaellig']['weniger'][0]['nr'] == '700002'
      and k['auffaellig']['weniger'][0]['anteil'] == -0.5, k.get('auffaellig'))
st, u = VV.call('crm_kunde_umsatz&key=kfff666666666')
k = u.get('kunde') or {}
check('Pop-up: neuer Kunde – Signal und Artikel „neu“ (auch für Kunden anderer Vertreter sichtbar)', st == 200 and [x['art'] for x in k['signale']] == ['neu'] and k['auffaellig']['neu'][0]['nr'] == '700003')
check('Pop-up: Kunde ohne Umsätze, Interessent', VV.call('crm_kunde_umsatz&key=kddd444444444')[1]['kunde'] is None and VV.call('crm_kunde_umsatz&key=' + INT['key'])[1]['kunde'] is None
      and VV.call('crm_kunde_umsatz&key=k-gibt-es-nicht')[0] == 404)
st, u = VK.call('crm_kunde_umsatz&key=kaaa111111111')
roh = json.dumps(u)
check('Pop-up nur kg: keine Umsätze, kein Preis, kein Preisniveau', st == 200 and '"umsatz' not in roh and u['kunde']['preisniveau'] is None and all(a['preisAlle'] is None for a in u['kunde']['artikel']))
st, u = VN.call('crm_kunde_umsatz&key=kaaa111111111')
roh = json.dumps(u)
check('Pop-up ohne € und kg: Artikel und Signale ohne Zahlen', st == 200 and '"umsatz' not in roh and '"menge' not in roh and u['kunde']['artikel'][0]['nr'] == '700002' and '777777' not in roh)
roh = json.dumps(VV.call('crm_kunde_umsatz&key=kaaa111111111')[1])
check('Pop-up ohne Einkaufswerte, DB oder Spanne', '777777' not in roh and '888888' not in roh and '"ek' not in roh.lower())
st, pz = A.call('controlling_umsatz_pausen&bis=' + E.strftime('%Y-%m'))
check('Umsatzstatistik: Bestellpausen mit derselben Regel (gemeinsame Funktion) – Beispiel Catering', st == 200 and [x['nr'] for x in pz['zeilen']] == ['900002'] and pz['zeilen'][0]['pause'] == 35, pz)

with sync_playwright() as p:
    br = p.chromium.launch()

    def seite(user, pw, ip, breite=1280, thema='light'):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin', color_scheme=thema)
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e))); pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/crm/'); pg.wait_for_selector('#tab-cockpit .crm-ck-kpis')
        return ctx, pg

    ctx, pg = seite('vv', 'Editor-Zugang-77', '198.51.100.31')
    t = pg.inner_text('#tab-cockpit')
    tl = t.lower()   # Überschriften und Kennzeichen erscheinen in Großbuchstaben (CSS)
    check('UI Mein Cockpit: Titel, Vertreter, Umsatz und Menge des Monats mit Vorjahr, Signale', 'Mein Cockpit' in t and 'vertreter 11' in tl and 'vera vertrieb' in tl
          and f'Umsatz {["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"][E.month - 1]}' in t and 'zum Vorjahr' in t, t[:600])
    check('UI Heute dran: Bestellpause mit Anrufen-Knopf', 'BESTELLPAUSE' in t.upper() and 'seit 35 Tagen nichts' in t and pg.locator('#tab-cockpit .crm-ck-liste li.h a.crm-ck-tel').count() >= 1)
    check('UI Signale: kauft weniger, nicht mehr gekauft', 'kauft weniger' in tl and 'Probe Markt Ost' in t and '−50,0 %' in t and 'artikel nicht mehr gekauft' in tl and 'seit 10 Wochen nicht mehr' in t, t[:900])
    check('UI Top-Kunden mit 12-Monats-Balken', pg.locator('#tab-cockpit .crm-ck-top .crm-ck-zeile:not(.kopf)').count() == 3 and pg.locator('#tab-cockpit .crm-ck-balken').first.locator('i').count() == 12)
    check('UI ohne Master: kein Umschalter', pg.locator('[data-ck-wahl]').count() == 0)
    pg.screenshot(path=os.path.join(SH, 'crm_mein_cockpit_1280.png'), full_page=True)
    pg.click('#tab-cockpit .crm-ck-top button[data-oeffnen="kaaa111111111"]')
    pg.wait_for_selector('#dlg-kunde[open] .crm-ku-kpis')
    ue = pg.inner_text('[data-ku-panel="uebersicht"]')
    check('UI Pop-up Übersicht: Umsatz/Menge 12 Monate, Ø Preis zum Ø, letzter Kauf, Rhythmus', 'umsatz 12 monate' in ue.lower() and 'menge 12 monate' in ue.lower() and 'zum Ø aller Kunden' in ue
          and 'alle 7 Tage' in ue and 'letzter kauf' in ue.lower(), ue[:500])
    check('UI Pop-up: Monatsbalken mit Vorjahr, Top-Artikel, nicht mehr gekauft', pg.locator('.crm-ku-saeule').count() == 12 and 'top-artikel' in ue.lower() and 'nicht mehr gekauft' in ue.lower()
          and 'Artikel 40100' in ue, ue[:900])
    check('UI Pop-up: Kunde passt in den Dialog (kein seitliches Scrollen)', pg.evaluate("document.querySelector('#dlg-kunde').scrollWidth <= document.querySelector('#dlg-kunde').clientWidth + 1"))
    pg.screenshot(path=os.path.join(SH, 'crm_kunde_uebersicht_1280.png'), full_page=False)
    pg.click('#dlg-kunde [data-schliessen]')
    pg.click('#tab-cockpit button[data-oeffnen="kccc333333333"]')
    pg.wait_for_selector('#dlg-kunde[open] .crm-ku-hinweis.minus')
    check('UI Pop-up: Hinweis „kauft weniger“ oben', 'kauft weniger' in pg.inner_text('.crm-ku-hinweise').lower() and '−50,0 % Menge' in pg.inner_text('.crm-ku-hinweise'))
    pg.click('#dlg-kunde [data-schliessen]')
    pg.click('#crm-tabs button[data-tab="kunden"]'); pg.wait_for_selector('#k-tabelle')
    check('UI Kunden: zuerst die eigenen Kunden, Auswahl Meine Kunden · Alle · Mit Signal', pg.get_attribute('[data-k-chip="mein"]', 'aria-pressed') == 'true'
          and pg.locator('#k-tabelle tbody tr').count() == 4 and pg.is_visible('[data-k-chip="signal"]'))
    pg.click('[data-k-chip="signal"]'); pg.wait_for_function("document.querySelectorAll('#k-tabelle tbody tr').length === 3")
    check('UI Kunden „Mit Signal“: Kennzeichen in der Liste', 'Bestellpause' in pg.inner_text('#k-tabelle') and 'kauft weniger' in pg.inner_text('#k-tabelle'))
    pg.click('[data-k-chip="alle"]'); pg.wait_for_function("document.querySelectorAll('#k-tabelle tbody tr').length > 4")
    ctx.close()

    ctx, pg = seite('gf', 'Konto-Passwort-9', '198.51.100.32')
    t = pg.inner_text('#tab-cockpit')
    check('UI Master-Cockpit: Vertrieb gesamt, Vertreter im Vergleich, auffällige Kunden, Kunden ohne Vertreter', 'Vertrieb gesamt' in t and 'vertreter im vergleich' in t.lower()
          and '11 – Vera Vertrieb' in t and 'ohne Vertreter' in t and 'auffällige kunden' in t.lower() and pg.get_attribute('[data-ck-wahl="alle"]', 'aria-pressed') == 'true', t[:600])
    pg.screenshot(path=os.path.join(SH, 'crm_master_cockpit_1280.png'), full_page=True)
    pg.click('#tab-cockpit .crm-ck-vergleich button[data-ck-wahl="12"]')
    pg.wait_for_function("document.querySelector('#tab-cockpit h1').textContent.includes('Tom Tour')")
    check('UI Master: „Ansicht öffnen“ zeigt die Verkäufer-Ansicht des Vertreters', 'Beispiel Catering' in pg.inner_text('#tab-cockpit') and pg.is_visible('#ck-vertreter')
          and pg.input_value('#ck-vertreter') == '12')
    pg.select_option('#ck-vertreter', '11'); pg.wait_for_function("document.querySelector('#tab-cockpit h1').textContent.includes('Vera Vertrieb')")
    check('UI Master: Vertreter-Auswahl', 'Probe Markt Ost' in pg.inner_text('#tab-cockpit'))
    pg.click('[data-ck-wahl="alle"]'); pg.wait_for_function("document.querySelector('#tab-cockpit h1').textContent === 'Vertrieb gesamt'")
    pg.click('[data-ck-modus="vertreter"]'); pg.wait_for_function("document.querySelector('#tab-cockpit h1').textContent.startsWith('Cockpit ·')")
    check('UI Master: Umschalter Verkäufer-Ansicht', pg.is_visible('#ck-vertreter'))
    ctx.close()

    ctx, pg = seite('vn', 'Weg-Kennwort-42', '198.51.100.34')
    t = pg.inner_text('#tab-cockpit')
    t = pg.inner_text('#tab-cockpit .crm-ck-kpis') + pg.inner_text('#tab-cockpit .crm-ck-raster >> nth=0')   # ohne Notizen der Aktivitäten (frei getippt)
    check('UI ohne € und kg: Kennzahlen, Heute dran und Signale ohne Beträge und Mengen', '€' not in t and not re.search(r'\d\s?(kg|t)\b', t) and 'kauft weniger' in t.lower(),
          [t[max(0, m_.start() - 40):m_.end() + 10] for m_ in re.finditer(r'€|\d\s?(kg|t)\b', t)][:5])
    pg.click('#tab-cockpit button[data-oeffnen="kccc333333333"]'); pg.wait_for_selector('#dlg-kunde[open] .crm-ku-kpis')
    ue = pg.inner_text('[data-ku-panel="uebersicht"]')
    check('UI Pop-up ohne € und kg: keine Zahlen, Hinweis', '€' not in ue and 'ausgeblendet' in ue and 'top-artikel' in ue.lower(), ue[:400])
    ctx.close()

    ctx, pg = seite('vv', 'Editor-Zugang-77', '198.51.100.31', breite=390, thema='dark')
    bw = pg.evaluate('document.documentElement.scrollWidth')
    check('390 px dunkel: Mein Cockpit ohne seitliches Scrollen', bw <= 390, bw)
    pg.screenshot(path=os.path.join(SH, 'crm_mein_cockpit_390.png'), full_page=True)
    pg.click('#tab-cockpit .crm-ck-top button[data-oeffnen="kaaa111111111"]'); pg.wait_for_selector('#dlg-kunde[open] .crm-ku-kpis')
    check('390 px: Pop-up passt in die Breite', pg.evaluate("document.querySelector('#dlg-kunde').scrollWidth <= document.querySelector('#dlg-kunde').clientWidth + 1"))
    pg.screenshot(path=os.path.join(SH, 'crm_kunde_uebersicht_390.png'), full_page=False)
    pg.click('#dlg-kunde [data-schliessen]')
    pg.click('#crm-tabs button[data-tab="kunden"]'); pg.wait_for_selector('#k-tabelle')
    pg.screenshot(path=os.path.join(SH, 'crm_kunden_karten_390.png'), full_page=False)
    ctx.close()
    ctx, pg = seite('gf', 'Konto-Passwort-9', '198.51.100.32', breite=390)
    check('390 px: Master-Cockpit ohne seitliches Scrollen (Vergleich als Karten)', pg.evaluate('document.documentElement.scrollWidth') <= 390 and pg.is_hidden('.crm-ck-vergleich thead'))
    pg.screenshot(path=os.path.join(SH, 'crm_master_cockpit_390.png'), full_page=True)
    ctx.close()
    br.close()

# ── Einzelangebot beim Kunden (Kunden-Pop-up, Reiter „Angebote“; Funktionen des Angebots, Rechte einzelangebote.*) ──
for u, n, r_, p_, extra in (('ea', 'Anna Angebot', 'viewer', 'Max-Zugang-12345', {'grant': ['crm.sehen', 'einzelangebote.bearbeiten']}),
                            ('es', 'Sven Sehen', 'viewer', 'Zweiter-Zugang-4711', {'grant': ['crm.sehen', 'einzelangebote.sehen']}),
                            ('ko', 'Kai Ohne', 'viewer', 'Dritter-Zugang-4712', {'grant': ['einzelangebote.bearbeiten']})):
    st, r = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r_, 'active': True, 'password': p_, 'mustChange': False, **extra})
    assert st == 200, r
EA = Client('198.51.100.41'); EA.call('login', {'username': 'ea', 'password': 'Max-Zugang-12345'})
ES = Client('198.51.100.42'); ES.call('login', {'username': 'es', 'password': 'Zweiter-Zugang-4711'})
KO = Client('198.51.100.43'); KO.call('login', {'username': 'ko', 'password': 'Dritter-Zugang-4712'})
st, d = EA.call('crm_start')
check('crm_start: Rechte für Einzelangebote', d['rechte']['einzel'] is True and d['rechte']['einzelBearbeiten'] is True and ES.call('crm_start')[1]['rechte']['einzelBearbeiten'] is False)
check('Einzelangebote im CRM: ohne Recht „Einzelangebote ansehen“ 403, ohne „CRM ansehen“ 403, ohne Anmeldung 401', VV.call('crm_einzel_liste&key=kaaa111111111')[0] == 403
      and KO.call('crm_einzel_liste&key=kaaa111111111')[0] == 403 and KO.call('crm_einzel_save', {'key': 'kaaa111111111', 'positions': []})[0] == 403 and N.call('crm_einzel_liste&key=kaaa111111111')[0] == 401)
st, d = EA.call('crm_einzel_liste&key=kaaa111111111')
check('Liste eines Kunden: leer, E-Mail und Portalzugang des Kunden', st == 200 and d['liste'] == [] and d['email'] == 'einkauf@musterfleischerei.example' and d['portal'] is True and d['bearbeiten'] is True, d)
check('Interessent und unbekannter Kunde: keine Einzelangebote (404)', EA.call('crm_einzel_liste&key=' + INT['key'])[0] == 404 and EA.call('crm_einzel_liste&key=kzzz999999999')[0] == 404)
st, d = EA.call('crm_einzel_artikel')
roh = json.dumps(d)
art = {a['code']: a for a in d.get('articles', [])}
check('Artikelsuche: Artikel mit Wochenpreis und Bestand, ohne Partien und Einkaufspreise', st == 200 and art.get('700002', {}).get('kg') == 120.25 and art['10000']['inOffer'] is True
      and art['10000']['stdPrice']['value'] > 0 and '"lots"' not in roh and '"ek"' not in roh and '"incoming"' not in roh, roh[:300])
check('Artikelsuche nur mit „bearbeiten“', ES.call('crm_einzel_artikel')[0] == 403)
POS = [{'code': '700002', 'name': 'Test Bald', 'qty': 25, 'price': 12.5, 'notiz': 'frisch'}, {'code': '', 'name': 'Sonderposten nach Absprache', 'qty': None, 'price': None, 'notiz': ''}]
st, r = EA.call('crm_einzel_save', {'key': 'kaaa111111111', 'kid': 'kbbb222222222', 'titel': 'Angebot KW 46', 'gueltigBis': tag(7), 'hinweis': 'Wie besprochen.', 'positions': POS})
ez = r.get('angebot', {})
check('Einzelangebot im CRM angelegt: Nummer, Kunde aus dem Pop-up (mitgeschickter Kunde ignoriert), Summe', st == 200 and re.match(r'^E-\d{4}-\d{4}$', ez.get('nr', ''))
      and ez['kid'] == 'kaaa111111111' and ez['firma'] == 'Musterfleischerei Nord GmbH' and ez['summen'] == {'kg': 25.0, 'summe': 312.5} and ez['status'] == 'entwurf', (st, r))
check('… erscheint in der Angebotsübersicht des Eingabebereichs (gleiche Daten)', any(x['id'] == ez['id'] and x['firma'] == 'Musterfleischerei Nord GmbH' for x in A.call('einzel_liste')[1]['list']))
check('… nur in der Liste dieses Kunden', [x['id'] for x in EA.call('crm_einzel_liste&key=kaaa111111111')[1]['liste']] == [ez['id']] and EA.call('crm_einzel_liste&key=kbbb222222222')[1]['liste'] == [])
check('Einzelangebot eines anderen Kunden: nicht über dessen Pop-up (404)', EA.call('crm_einzel_detail&key=kbbb222222222&id=' + ez['id'])[0] == 404
      and EA.call('crm_einzel_save', {'key': 'kbbb222222222', 'id': ez['id'], 'revision': ez['revision'], 'positions': POS})[0] == 404
      and EA.call('crm_einzel_status', {'key': 'kbbb222222222', 'id': ez['id'], 'revision': ez['revision'], 'status': 'freigegeben'})[0] == 404
      and EA.call('crm_einzel_loeschen', {'key': 'kbbb222222222', 'id': ez['id']})[0] == 404)
check('nur ansehen: Liste, Einzelangebot und PDF ja, Speichern nein', ES.call('crm_einzel_detail&key=kaaa111111111&id=' + ez['id'])[0] == 200
      and ES.call('crm_einzel_save', {'key': 'kaaa111111111', 'positions': POS})[0] == 403 and ES.call('crm_einzel_status', {'key': 'kaaa111111111', 'id': ez['id'], 'revision': 1, 'status': 'freigegeben'})[0] == 403)
st, _, pdf = ES.call('crm_einzel_pdf&key=kaaa111111111&id=' + ez['id'], raw=True)
check('PDF des Einzelangebots', st == 200 and pdf.startswith('%PDF'), (st, pdf[:20]))
for name_, pos_, code_ in (('Position ohne Bezeichnung', [{'name': '', 'qty': 1, 'price': 1}], 422), ('negative Menge', [{'name': 'X', 'qty': -2, 'price': 1}], 422),
                            ('Preis keine Zahl', [{'name': 'X', 'qty': 1, 'price': 'viel'}], 422)):
    check(f'Prüfung beim Angebot: {name_} → {code_}', EA.call('crm_einzel_save', {'key': 'kaaa111111111', 'positions': pos_})[0] == code_)
check('Änderung mit altem Stand → 409', EA.call('crm_einzel_save', {'key': 'kaaa111111111', 'id': ez['id'], 'revision': 99, 'positions': POS})[0] == 409)
st, r = EA.call('crm_einzel_status', {'key': 'kaaa111111111', 'id': ez['id'], 'revision': ez['revision'], 'status': 'freigegeben'})
check('Im Portal freigegeben (für den Kunden sichtbar)', st == 200 and r['angebot']['status'] == 'freigegeben' and r['angebot']['sichtbar'] is True, r)
expire_session(next(c.value for h in EA.http.handlers if hasattr(h, 'cookiejar') for c in h.cookiejar if c.name == 'WA_ADMIN'))   # Bestätigung beim Anmelden abgelaufen
check('E-Mail aus dem CRM verlangt die Bestätigung (Schlüssel einzel_senden)', (lambda x: x[0] == 403 and x[1].get('code') == 'confirmation_required')(EA.call('crm_einzel_senden', {'key': 'kaaa111111111', 'id': ez['id']})))
st, r = EA.call('crm_einzel_save', {'key': 'kaaa111111111', 'positions': [{'name': 'Wegwerf', 'qty': 1, 'price': 1}]})
st2, _ = EA.call('crm_einzel_loeschen', {'key': 'kaaa111111111', 'id': r['angebot']['id']})
check('Löschen im CRM', st == 200 and st2 == 200 and all(x['id'] != r['angebot']['id'] for x in A.call('einzel_liste')[1]['list']))
log = json.dumps([e for e in (dokument('protokoll/' + dt.datetime.now(dt.timezone.utc).strftime('%Y-%m')) or []) if e.get('a') == 'einzelangebot'], ensure_ascii=False)
check('Protokoll wie im Eingabebereich (angelegt, freigegeben, gelöscht)', f'Einzelangebot {ez["nr"]} für „Musterfleischerei Nord GmbH“ angelegt' in log and f'Einzelangebot {ez["nr"]} im Portal freigegeben' in log and 'gelöscht' in log, log[:300])

with sync_playwright() as p:
    br = p.chromium.launch()
    for breite in (1280, 390):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': '198.51.100.41'}, locale='de-DE', timezone_id='Europe/Berlin')
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        # erwartet: 403 „Bestätigung nötig“ beim Versand (meldet der Browser als Ladefehler)
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and '403 (Forbidden)' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'ea'); pg.fill('#pw1', 'Max-Zugang-12345'); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/crm/#kunden'); pg.wait_for_selector('#k-tabelle')
        pg.click('#k-tabelle button[data-oeffnen="kaaa111111111"]'); pg.wait_for_selector('#dlg-kunde[open]')
        pg.click('#kunde-reiter [data-ku-tab="angebote"]'); pg.wait_for_selector('.crm-ez-liste [data-ez-oeffnen]')
        check(f'{breite}px: Reiter „Angebote“ mit dem Einzelangebot des Kunden', ez['nr'] in pg.inner_text('[data-ku-panel="angebote"]') and 'Im Portal' in pg.inner_text('.crm-ez-liste'))
        pg.click('[data-ez="neu"]'); pg.wait_for_selector('#ez-suche')
        pg.fill('#ez-suche', '700002'); pg.wait_for_selector('#ez-treffer [data-ez-treffer]')
        check(f'{breite}px: Artikelsuche mit Treffer', '700002' in pg.inner_text('#ez-treffer'))
        pg.click('#ez-treffer [data-ez-treffer="0"]'); pg.wait_for_selector('tr[data-pos="0"]')
        pg.fill('tr[data-pos="0"] [data-p="qty"]', '12,5'); pg.fill('tr[data-pos="0"] [data-p="price"]', '13,90'); pg.fill('[data-k="titel"]', f'Test UI {breite}')
        pg.wait_for_function("document.querySelector('.crm-ez-summe').textContent.includes('173,75')")
        check(f'{breite}px: Summe aus Menge × Preis (Menge mit 2 Stellen wie überall)', '12,50 kg' in pg.inner_text('.crm-ez-summe'), pg.inner_text('.crm-ez-summe'))
        if breite == 1280:
            pg.click('#dlg-kunde [data-schliessen]'); pg.wait_for_selector('#crm-toast.zeigen')
            check('Schließen mit ungespeichertem Einzelangebot: Warnung, Pop-up bleibt offen', pg.is_visible('#dlg-kunde') and 'nicht gespeichert' in pg.text_content('#crm-toast'))
        pg.click('[data-ez="speichern"]'); pg.wait_for_function("document.querySelector('.crm-ez-titel h3').textContent.startsWith('E-')")
        nr = pg.text_content('.crm-ez-titel h3')
        check(f'{breite}px: gespeichert mit Nummer', nr.startswith('E-') and any(x['nr'] == nr and x['kid'] == 'kaaa111111111' and x['titel'] == f'Test UI {breite}' for x in A.call('einzel_liste')[1]['list']), nr)
        pg.click('[data-ez-status="freigegeben"]'); pg.wait_for_selector('[data-ez-status="entwurf"]')
        check(f'{breite}px: im Portal freigegeben', 'Im Portal' in pg.inner_text('.crm-ez-kopf'))
        if breite == 390:
            check('390 px: Editor ohne seitliches Scrollen im Pop-up', pg.evaluate("document.querySelector('#dlg-kunde').scrollWidth <= document.querySelector('#dlg-kunde').clientWidth + 1"))
        pg.screenshot(path=os.path.join(SH, f'crm_einzelangebot_{breite}.png'), full_page=False)
        pg.click('[data-ez="mail"]'); pg.wait_for_selector('#ez-mail')
        expire_session(next(c['value'] for c in ctx.cookies() if c['name'].endswith('WA_ADMIN')))
        pg.click('#ez-senden'); pg.wait_for_selector('#ez-mail [name="pw"]')
        check(f'{breite}px: E-Mail – Bestätigung mit Passwort im Formular', 'Passwort' in pg.inner_text('#ez-mail'))
        pg.click('[data-ez="liste"]'); pg.wait_for_selector('.crm-ez-liste')
        check(f'{breite}px: zurück zur Liste – neues Angebot steht oben', nr in pg.inner_text('.crm-ez-liste li:first-child'))
        pg.click('#dlg-kunde [data-schliessen]'); pg.wait_for_selector('#dlg-kunde', state='hidden')
        ctx.close()
    br.close()

check('keine JavaScript-Fehler', not fehler, fehler)
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
