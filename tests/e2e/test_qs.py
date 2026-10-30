"""Qualitätssicherung (Modul qs, Oberfläche qs.intern unter /module/qs/) – QM-System: Dokumentenlenkung, QM-Handbuch,
Prüfplan, Maßnahmen.

Geprüft: Register (fertig und produktiv unter qs.dashboard-stafl.de, Kachel verfügbar, keine Testfreigabe über die Modulverwaltung, ohne Tester-Eintrag erreichbar);
Rechte serverseitig (GR-103): ohne Anmeldung, ohne QM-Recht, ansehen, Kontrollen durchführen, bearbeiten, freigeben, verwalten;
ohne CSRF, GET auf schreibende Aktion; Kapitel, Personen mit Verknüpfung zu Mitarbeitern (unbekannt, doppelt), Einstellung
„Überprüfung fällig nach“ (6–120 Monate); Dokumente (Pflichtfelder, Nr. eindeutig, Ablage nur Pfad oder http(s), neues
gelenktes Dokument als Entwurf, Ordner ohne Versionen, Stand 409); Ablauf einer Version (einreichen, prüfen, freigeben, prüfen
und freigeben, zurückgeben mit Grund, verwerfen, Schritt passt nicht 409, Versionsnummer erst bei der Freigabe, Datum =
Freigabedatum, vorige Version „ersetzt“); 4-Augen-Prinzip (auch Administratoren); Einziehen; Überprüfung nach 3 Jahren und
„ohne Änderung überprüft“; Handbuch; Prüfplan (rollende Intervalle mit Vorlauf und Monatsende, „bei Bedarf“, Kalender-Intervalle
täglich/arbeitstäglich ohne Wochenende und Hamburger Feiertage/wöchentlich/monatlich mit versäumten Perioden, Quote und
Monatsverlauf, Zuweisung an Mitarbeiter); Nachweise (Zukunft, Abweichung nur mit Bemerkung, nur zugewiesene Kontrollen mit
„Kontrollen durchführen“, Maßnahme nur mit „bearbeiten“, stornieren nur eigene, storniert zählt nicht); Maßnahmen im Aufbau des
IFS-Maßnahmenplans (Nummer je Jahr, Bewertung, Korrektur, Ursache, wirksam nur mit Freigaberecht und Notiz, abgeschlossene nur
mit Freigaberecht ändern); CSV (BOM, keine Formeln, Protokoll); Datenpaket (Format, Vorschau mit Fehlern je Eintrag, nichts halb
übernommen, nur leer oder „ersetzen“, Versionen aus der Excel, Kürzel als Schnappschuss, Einstellungen bleiben); Protokoll ohne
Texte; Oberfläche (Übersicht mit Kennzahlen und „Ihre Aufgaben“, Dokumente mit Zustandsfilter und Seitenleiste bis zur Freigabe
durch eine zweite Person, Überprüfung, Handbuch mit Ziel, Suche und Verweisen, Jahresplan mit Nachweis und Maßnahme, eigene
Kontrolle mit „Kontrollen durchführen“, Maßnahmen-Tafel und IFS-Maske, Einstellungen mit Mitarbeitern, Überprüfungsfrist und
Datenpaket, nur ansehen, 1280/390 px hell und dunkel ohne waagerechtes Scrollen, ohne Recht nur Hinweis, keine JavaScript-Fehler).
Nur erfundene Testdaten.
"""
import datetime
import json
import os

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH

PW = 'Sicheres-Passwort-1'
HIER = os.path.dirname(os.path.abspath(__file__))
PAKET_DATEI = os.path.join(HIER, '..', 'fixtures', 'qs', 'datenpaket.json')
HEUTE = datetime.date.today()
JAHR = HEUTE.strftime('%Y')
res = []
fehler = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def tag(delta):
    return (HEUTE + datetime.timedelta(days=delta)).isoformat()


def ostern(j):
    a, b, c = j % 19, j // 100, j % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l_ = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l_) // 451
    mo = (h + l_ - 7 * m + 114) // 31
    return datetime.date(j, mo, (h + l_ - 7 * m + 114) % 31 + 1)


def feiertag_hamburg(d):
    o = ostern(d.year)
    beweglich = {o + datetime.timedelta(days=x) for x in (-2, 1, 39, 50)}
    return d in beweglich or (d.month, d.day) in ((1, 1), (5, 1), (10, 3), (10, 31), (12, 25), (12, 26))


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
NUTZER = (('lisa', 'Lisa Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['qs.sehen']}),
          ('bernd', 'Bernd Bearbeiter', 'editor', 'Bearbeit-Konto-34', {'grant': ['qs.bearbeiten']}),
          ('quinn', 'Quinn QMB', 'editor', 'Freigabe-Konto-56', {'grant': ['qs.freigeben']}),
          ('fritz', 'Fritz Freigabe', 'editor', 'Freigabe-Konto-78', {'grant': ['qs.freigeben']}),
          ('vera', 'Vera Verwalten', 'editor', 'Verwalt-Konto-90', {'grant': ['qs.verwalten']}),
          ('otto', 'Otto Ohne', 'editor', 'Ohne-Konto-11', {}),
          ('kai', 'Kai Kontrolle', 'editor', 'Kontroll-Konto-22', {'grant': ['qs.nachweis']}))
for u, n, r, p, extra in NUTZER:
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
K = {}
for i, (u, _, _, p, _) in enumerate(NUTZER):
    K[u] = Client(f'198.51.100.{10 + i}'); K[u].call('login', {'username': u, 'password': p})
L, Be, Q, F, V, O, KA, N = K['lisa'], K['bernd'], K['quinn'], K['fritz'], K['vera'], K['otto'], K['kai'], Client('198.51.100.30')

# ── Register und Freigabe ──
mod = {m['id']: m for m in A.call('module_status')[1]['module']}['qs']
ob = {o['id']: o for o in mod['oberflaechen']}
check('Register: Qualitätssicherung fertig und produktiv (Entscheidung des Inhabers 30.10.2026), Adresse qs.dashboard-stafl.de/module/qs/',
      mod['name'] == 'Qualitätssicherung' and ob['intern']['entwicklung'] == 'fertig' and ob['intern']['freigabe'] == 'produktiv'
      and ob['intern']['adresse'] == 'https://qs.dashboard-stafl.de/module/qs/', (mod['name'], ob['intern']))
check('Kachel: verfügbar, Ziel qs.intern', mod['kachel']['status'] == 'verfuegbar' and mod['kachel']['zugang'] is True and mod['kachel']['ziel'] == 'qs.intern', mod['kachel'])
check('QS-Portal (extern) bleibt geplant und gesperrt', ob['portal']['art'] == 'extern' and ob['portal']['entwicklung'] == 'geplant' and not ob['portal']['zugang'])
st, r = A.call('modul_freigabe_save', {'bereich': 'qs.intern', 'freigabe': 'test', 'grund': 'Test'})
check('Produktivbereich: keine Testfreigabe über die Modulverwaltung (nur über ein Release)', st == 422, (st, r))
check('produktiv ohne Tester-Eintrag: Administrator und Mitarbeiter mit QM-Recht erreichen das Modul', A.call('qs_start')[0] == 200 and L.call('qs_start')[0] == 200)

# ── Rechte ──
check('ohne Anmeldung: kein Zugang (401/404)', N.call('qs_start')[0] in (401, 404))
check('ohne QM-Recht (nur Modulzugang der Rolle): 403', O.call('qs_start')[0] == 403)
st, r = L.call('qs_start')
check('Ansehen: Start ok, ohne weitere Rechte, leer, eigene Kennung ohne Kürzel', st == 200 and r['rechte'] == {'nachweis': False, 'bearbeiten': False, 'freigeben': False, 'verwalten': False}
      and r['leer'] is True and r['ich']['id'] == ids['lisa'] and r['ich']['kuerzel'] == [], r)
check('Auswahllisten: Arten, Intervalle (arbeitstäglich … bei Bedarf), Quellen, Bewertungen, Status', list(r['arten']) == ['A', 'F', 'L', 'E', 'V', 'X', 'O'] and r['gelenkt'] == ['A', 'F', 'L', 'E', 'V']
      and list(r['intervalle'])[0] == 'arbeitstaeglich' and list(r['intervalle'])[-1] == 'anlass' and 'laufend' not in r['intervalle'] and 'extern' in r['quellen']
      and r['bewertungen'] == ['', 'A', 'B', 'C', 'D', 'Major', 'KO'] and list(r['massnStatus'])[-2:] == ['wirksam', 'verworfen'], r)
check('Einstellungen: Überprüfung nach 36 Monaten (Standard)', r['einstellungen'] == {'ueberpruefungMonate': 36}, r['einstellungen'])
mnamen = {m['name']: m for m in r['mitarbeiter']}
check('Mitarbeiterliste für Zuweisungen (Name, Kennung, mit Anmeldung)', 'Kai Kontrolle' in mnamen and mnamen['Kai Kontrolle']['id'] == ids['kai'] and mnamen['Kai Kontrolle']['zugang'] is True, r['mitarbeiter'])
check('Kontrollen durchführen: nur Nachweise', KA.call('qs_start')[1]['rechte'] == {'nachweis': True, 'bearbeiten': False, 'freigeben': False, 'verwalten': False})
check('Bearbeiten: Nachweise und bearbeiten', Be.call('qs_start')[1]['rechte'] == {'nachweis': True, 'bearbeiten': True, 'freigeben': False, 'verwalten': False})
check('Freigeben: bearbeiten und freigeben', Q.call('qs_start')[1]['rechte'] == {'nachweis': True, 'bearbeiten': True, 'freigeben': True, 'verwalten': False})
check('Verwalten: bearbeiten und verwalten (nicht freigeben)', V.call('qs_start')[1]['rechte'] == {'nachweis': True, 'bearbeiten': True, 'freigeben': False, 'verwalten': True})

# ── Kapitel, Personen, Einstellungen ──
KAP = [{'id': '1.1', 'titel': 'Managementsystem', 'zustaendig': 'QB', 'vertreter': 'QV'}, {'id': '1.4.', 'titel': 'Qualitätssicherung', 'zustaendig': 'QB'},
       {'id': '2.1', 'titel': 'Einkauf / Wareneingang', 'zustaendig': 'GF'}, {'id': '1.10', 'titel': 'Zehn (Sortierung)'}]
PERS = [{'id': 'QB', 'name': 'Quinn Beispiel', 'funktion': 'QMB', 'mitarbeiter': ids['quinn']}, {'id': 'QV', 'name': 'Vera Vertretung', 'funktion': 'Stellv. QMB', 'mitarbeiter': ids['kai']},
        {'id': 'GF', 'name': 'Geschäftsführung'}]
check('Kapitel nur mit „verwalten“ (Freigabe 403)', Q.call('qs_stamm_save', {'kapitel': KAP})[0] == 403)
for name, kap in (('Nummer Text', [{'id': 'eins', 'titel': 'X'}]), ('ohne Titel', [{'id': '1.1', 'titel': ''}]), ('doppelt', [{'id': '1.1', 'titel': 'A'}, {'id': '1.1', 'titel': 'B'}]),
                  ('zu tief', [{'id': '1.2.3.4', 'titel': 'X'}]), ('keine Liste', 'abc')):
    st, r = V.call('qs_stamm_save', {'kapitel': kap})
    check(f'Kapitel: {name} → 422', st == 422 and r.get('error'), (st, r))
for name, pers in (('Kürzel leer', [{'id': '', 'name': 'X'}]), ('Kürzel zu lang', [{'id': 'ABCDEFGHIJKLM', 'name': 'X'}]), ('ohne Name', [{'id': 'AB', 'name': ''}]),
                   ('doppelt (Groß/Klein)', [{'id': 'AB', 'name': 'X'}, {'id': 'ab', 'name': 'Y'}]),
                   ('unbekannter Mitarbeiter', [{'id': 'AB', 'name': 'X', 'mitarbeiter': 'u-gibt-es-nicht'}]),
                   ('Mitarbeiter mit zwei Kürzeln', [{'id': 'AB', 'name': 'X', 'mitarbeiter': ids['kai']}, {'id': 'CD', 'name': 'Y', 'mitarbeiter': ids['kai']}])):
    st, r = V.call('qs_stamm_save', {'personen': pers})
    check(f'Personen: {name} → 422', st == 422 and r.get('error'), (st, r))
for name, wert in (('5 Monate', 5), ('121 Monate', 121), ('Text', 'drei Jahre')):
    st, r = V.call('qs_stamm_save', {'einstellungen': {'ueberpruefungMonate': wert}})
    check(f'Überprüfung: {name} → 422', st == 422 and '6 bis 120' in r.get('error', ''), (st, r))
st, r = V.call('qs_stamm_save', {'kapitel': KAP, 'personen': PERS, 'einstellungen': {'ueberpruefungMonate': '24'}})
check('Kapitel und Personen gespeichert: Nummer ohne Schlusspunkt, natürlich sortiert (1.4 vor 1.10), Verknüpfung, 24 Monate', st == 200 and [k['id'] for k in r['kapitel']] == ['1.1', '1.4', '1.10', '2.1']
      and [p['id'] for p in r['personen']] == ['QB', 'QV', 'GF'] and all(k['aktiv'] for k in r['kapitel']) and r['personen'][0]['mitarbeiter'] == ids['quinn'] and r['personen'][2]['mitarbeiter'] == ''
      and r['einstellungen']['ueberpruefungMonate'] == 24, r)
check('eigene Kürzel aus der Verknüpfung (Quinn QB, Kai QV)', Q.call('qs_start')[1]['ich']['kuerzel'] == ['QB'] and KA.call('qs_start')[1]['ich']['kuerzel'] == ['QV'])
check('Stamm: veralteter Stand 409', V.call('qs_stamm_save', {'rev': 0, 'personen': PERS})[0] == 409)
check('Einstellungen zurück auf 36 Monate', V.call('qs_stamm_save', {'einstellungen': {'ueberpruefungMonate': 36}})[1]['einstellungen']['ueberpruefungMonate'] == 36)

# ── Dokumente ──
D1 = {'kapitel': '1.4', 'art': 'F', 'nr': '1.4-F01', 'titel': 'Probenahmeprotokoll', 'zustaendig': 'QB', 'vertreter': 'QV', 'ablage': '1.4 Qualitätssicherung/Probenahme.xlsx'}
check('Dokument: nur ansehen 403', L.call('qs_dokument_save', D1)[0] == 403)
check('Dokument: Kontrollen durchführen 403', KA.call('qs_dokument_save', D1)[0] == 403)
csrf = Be.csrf; Be.csrf = ''
check('Dokument ohne CSRF: 403', Be.call('qs_dokument_save', D1)[0] == 403)
Be.csrf = csrf
check('schreibende Aktion per GET: 405', Be.call('qs_dokument_save')[0] == 405)
for name, b in (('ohne Titel', {'titel': ''}), ('Nr. nicht nach der Struktur', {'nr': '1.4-X01'}), ('Kapitel unbekannt', {'kapitel': '9.9'}), ('ohne Kapitel', {'kapitel': ''}),
                ('Art unbekannt', {'art': 'Z'}), ('Ablage javascript:', {'ablage': 'javascript:alert(1)'}), ('Ablage mit Umbruch', {'ablage': 'a\nb'}),
                ('Titel zu lang', {'titel': 'x' * 201})):
    st, r = Be.call('qs_dokument_save', {**D1, **b})
    check(f'Dokument: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = Be.call('qs_dokument_save', {**D1, 'aenderungen': ''})
d1 = r.get('dokument', {})
v = (d1.get('versionen') or [{}])[0]
check('Dokument angelegt: Entwurf ohne Versionsnummer, „Neu angelegt“, Ersteller, ohne Überprüfung', st == 200 and d1['zustand'] == 'entwurf' and len(d1['versionen']) == 1 and v['nr'] is None
      and v['status'] == 'entwurf' and v['aenderungen'] == 'Neu angelegt' and v['erstellt']['von'] == 'Bernd Bearbeiter' and v['bearbeiter'] == [ids['bernd']] and d1['ueberpruefung'] is None, r)
check('Dokumenten-Nr. doppelt (Groß/Klein egal) → 422', Be.call('qs_dokument_save', {**D1, 'nr': '1.4-f01'})[0] == 422)
st, r = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'O', 'nr': '', 'titel': 'Befunde', 'ablage': 'https://dms.example.invalid/befunde'})
ordner = r.get('dokument', {})
check('Ordner ohne Nr. und ohne Versionen (nicht gelenkt), Ablage als http(s)', st == 200 and ordner['zustand'] == 'register' and ordner['versionen'] == [], r)
check('Ordner: keine Versionen (422)', Be.call('qs_version_save', {'dokument': ordner['id'], 'aenderungen': 'x', 'grund': 'y'})[0] == 422)
st, r = Be.call('qs_dokument_save', {**D1, 'id': d1['id'], 'rev': d1['rev'], 'titel': 'Probenahmeprotokoll (Mikrobiologie)'})
check('Angaben ändern mit Stand, Verlauf „Titel geändert“', st == 200 and r['dokument']['rev'] == d1['rev'] + 1 and 'Titel geändert' in r['dokument']['verlauf'][-1]['was'], r)
check('Angaben: veralteter Stand 409 mit aktuellem Eintrag', (lambda x: x[0] == 409 and x[1].get('code') == 'konflikt' and x[1]['eintrag']['id'] == d1['id'])(Be.call('qs_dokument_save', {**D1, 'id': d1['id'], 'rev': d1['rev']})))
check('Angaben: unbekanntes Dokument 404', Be.call('qs_dokument_save', {**D1, 'id': 'dnix', 'rev': 1})[0] == 404)
check('Ordner ↔ gelenkt nicht bei vorhandenen Versionen (422)', Be.call('qs_dokument_save', {**D1, 'id': d1['id'], 'rev': d1['rev'] + 1, 'art': 'O'})[0] == 422)


def dok(cli, did):
    return {x['id']: x for x in cli.call('qs_start')[1]['dokumente']}[did]


def schritt(cli, did, s, **extra):
    x = dok(A, did)
    return cli.call('qs_version_schritt', {'dokument': did, 'rev': x['rev'], 'schritt': s, **extra})


# ── Ablauf: Entwurf → Prüfung → Freigabe ──
check('Prüfen eines Entwurfs, der nicht eingereicht ist → 409', schritt(Q, d1['id'], 'pruefen')[0] == 409)
check('Unbekannter Schritt → 422', schritt(Be, d1['id'], 'abkuerzen')[0] == 422)
check('Einreichen: nur ansehen 403', schritt(L, d1['id'], 'einreichen')[0] == 403)
check('Überprüft vermerken: nicht ohne gültige Version (409)', schritt(Q, d1['id'], 'ueberprueft')[0] == 409)
st, r = schritt(Be, d1['id'], 'einreichen')
check('Einreichen: in Prüfung', st == 200 and r['dokument']['zustand'] == 'pruefung' and r['dokument']['versionen'][0]['status'] == 'pruefung', r)
check('Entwurf in Prüfung ist nicht mehr änderbar (409)', Be.call('qs_version_save', {'dokument': d1['id'], 'aenderungen': 'x', 'grund': 'y'})[0] == 409)
check('Prüfen nur mit Freigaberecht (Bearbeiter 403)', schritt(Be, d1['id'], 'pruefen')[0] == 403)
check('Freigeben vor dem Prüfen → 409', schritt(Q, d1['id'], 'freigeben')[0] == 409)
st, r = schritt(Q, d1['id'], 'pruefen')
check('Geprüft durch eine zweite Person (Name, Zeitpunkt)', st == 200 and r['dokument']['versionen'][0]['status'] == 'geprueft' and r['dokument']['versionen'][0]['geprueft']['von'] == 'Quinn QMB', r)
st, r = schritt(F, d1['id'], 'freigeben')
v1 = r.get('dokument', {}).get('versionen', [{}])[0]
check('Freigabe: Version 1, Datum = heute, gültig, Freigeber vermerkt', st == 200 and v1['nr'] == 1 and v1['datum'] == HEUTE.isoformat() and v1['status'] == 'freigegeben'
      and v1['freigegeben']['von'] == 'Fritz Freigabe' and r['dokument']['zustand'] == 'gueltig', r)
u = r['dokument']['ueberpruefung']
check('Überprüfung: seit Freigabe, fällig in 36 Monaten, noch nicht fällig', u['seit'] == HEUTE.isoformat() and u['faellig'] is False and u['faelligAb'][:4] == str(HEUTE.year + 3), u)
check('Kein offener Entwurf mehr → Schritt 409', schritt(Q, d1['id'], 'einreichen')[0] == 409)

# Überarbeitung: Änderungen und Grund Pflicht; 4-Augen-Prinzip
check('Überarbeitung ohne Änderungen/Grund → 422', Q.call('qs_version_save', {'dokument': d1['id'], 'aenderungen': 'Ablauf ergänzt', 'grund': ''})[0] == 422)
st, r = Q.call('qs_version_save', {'dokument': d1['id'], 'aenderungen': 'Ablauf ergänzt', 'grund': 'Internes Audit'})
check('Überarbeitung begonnen (Entwurf von Quinn), gültige Version bleibt', st == 200 and r['dokument']['zustand'] == 'entwurf' and len(r['dokument']['versionen']) == 2
      and r['dokument']['versionen'][0]['status'] == 'freigegeben', r)
check('zweiter Entwurf neben dem ersten nicht möglich – derselbe wird geändert', Be.call('qs_version_save', {'dokument': d1['id'], 'aenderungen': 'Ablauf ergänzt, Formular', 'grund': 'Internes Audit'})[0] == 200
      and len(dok(A, d1['id'])['versionen']) == 2)
check('Mitbearbeiter vermerkt (Quinn, Bernd)', dok(A, d1['id'])['versionen'][1]['bearbeiter'] == [ids['quinn'], ids['bernd']])
check('unverändert speichern ändert nichts', (lambda r0, r1: r1['rev'] == r0['rev'])(dok(A, d1['id']), Be.call('qs_version_save', {'dokument': d1['id'], 'aenderungen': 'Ablauf ergänzt, Formular', 'grund': 'Internes Audit'})[1]['dokument']))
check('Einreichen durch Quinn', schritt(Q, d1['id'], 'einreichen')[0] == 200)
st, r = schritt(Q, d1['id'], 'pruefen')
check('4-Augen-Prinzip: Ersteller prüft nicht (403)', st == 403 and '4-Augen' in r.get('error', ''), r)
check('4-Augen-Prinzip: auch nicht „prüfen und freigeben“ (403)', schritt(Q, d1['id'], 'pruefen_freigeben')[0] == 403)
check('Zurückgeben ohne Grund → 422', schritt(F, d1['id'], 'zurueck')[0] == 422)
st, r = schritt(F, d1['id'], 'zurueck', grund='Bitte Formular-Nr. nennen')
check('Zurückgegeben: wieder Entwurf, Verlauf mit Grund', st == 200 and r['dokument']['versionen'][1]['status'] == 'entwurf' and 'Bitte Formular-Nr. nennen' in r['dokument']['versionen'][1]['verlauf'][-1]['was'], r)
check('Einreichen nach Korrektur', Q.call('qs_version_save', {'dokument': d1['id'], 'aenderungen': 'Ablauf ergänzt, 1.4-F01', 'grund': 'Internes Audit'})[0] == 200 and schritt(Q, d1['id'], 'einreichen')[0] == 200)
st, r = schritt(F, d1['id'], 'pruefen_freigeben')
vs = r.get('dokument', {}).get('versionen', [])
check('Prüfen und freigeben in einem Schritt: Version 2 gültig, Version 1 ersetzt', st == 200 and [x['nr'] for x in vs] == [1, 2] and [x['status'] for x in vs] == ['ersetzt', 'freigegeben']
      and vs[1]['geprueft']['von'] == 'Fritz Freigabe' and vs[1]['aenderungen'] == 'Ablauf ergänzt, 1.4-F01' and 'ersetzt durch Version 2' in vs[0]['verlauf'][-1]['was'], vs)
# Administrator: ebenfalls 4-Augen
st, r = A.call('qs_version_save', {'dokument': d1['id'], 'aenderungen': 'Tippfehler', 'grund': 'Hinweis Lager'})
check('Administrator beginnt Überarbeitung und reicht ein', st == 200 and schritt(A, d1['id'], 'einreichen')[0] == 200)
check('4-Augen-Prinzip gilt auch für Administratoren (403)', schritt(A, d1['id'], 'pruefen_freigeben')[0] == 403)
check('Zurückgeben durch Quinn, Verwerfen durch Bernd', schritt(Q, d1['id'], 'zurueck', grund='nicht nötig')[0] == 200 and schritt(Be, d1['id'], 'verwerfen', grund='')[0] == 200)
x = dok(A, d1['id'])
check('Verworfen: Version bleibt sichtbar, Dokument weiter gültig (Version 2)', [v['status'] for v in x['versionen']] == ['ersetzt', 'freigegeben', 'verworfen'] and x['zustand'] == 'gueltig')
# Überprüfung ohne Änderung
check('Überprüft vermerken nur mit Freigaberecht (Bearbeiter 403)', schritt(Be, d1['id'], 'ueberprueft')[0] == 403)
st, r = schritt(Q, d1['id'], 'ueberprueft', grund='Inhalt weiter aktuell')
check('ohne Änderung überprüft: Name, Notiz, Verlauf, Frist ab heute, Version unverändert', st == 200 and r['dokument']['ueberprueft']['von'] == 'Quinn QMB'
      and r['dokument']['ueberprueft']['notiz'] == 'Inhalt weiter aktuell' and 'ohne Änderung überprüft' in r['dokument']['verlauf'][-1]['was']
      and r['dokument']['ueberpruefung']['seit'] == HEUTE.isoformat() and len(r['dokument']['versionen']) == 3, r)
# Einziehen
x = dok(A, d1['id'])
check('Einziehen nur mit Freigaberecht (Bearbeiter 403)', Be.call('qs_dokument_save', {**D1, 'id': d1['id'], 'rev': x['rev'], 'eingezogen': True, 'einzugGrund': 'alt'})[0] == 403)
check('Einziehen ohne Grund → 422', Q.call('qs_dokument_save', {**D1, 'id': d1['id'], 'rev': x['rev'], 'eingezogen': True})[0] == 422)
check('Entwurf vor dem Einziehen', Be.call('qs_version_save', {'dokument': d1['id'], 'aenderungen': 'neu', 'grund': 'neu'})[0] == 200)
x = dok(A, d1['id'])
st, r = Q.call('qs_dokument_save', {**D1, 'id': d1['id'], 'rev': x['rev'], 'eingezogen': True, 'einzugGrund': 'ersetzt durch DMS-Formular'})
check('Eingezogen: Zustand, offener Entwurf verworfen, Versionen bleiben, keine Überprüfung', st == 200 and r['dokument']['zustand'] == 'eingezogen' and r['dokument']['eingezogen']['grund'] == 'ersetzt durch DMS-Formular'
      and [v['status'] for v in r['dokument']['versionen']] == ['ersetzt', 'freigegeben', 'verworfen', 'verworfen'] and r['dokument']['ueberpruefung'] is None, r)
check('eingezogen: keine Überarbeitung (409), nicht überprüfbar (409)', Be.call('qs_version_save', {'dokument': d1['id'], 'aenderungen': 'x', 'grund': 'y'})[0] == 409
      and schritt(Q, d1['id'], 'ueberprueft')[0] == 409)
st, r = Q.call('qs_dokument_save', {**D1, 'id': d1['id'], 'rev': dok(A, d1['id'])['rev'], 'eingezogen': False})
check('Wieder gültig', st == 200 and r['dokument']['zustand'] == 'gueltig' and r['dokument']['eingezogen'] is None, r)

# ── Handbuch ──
H1 = {'kapitel': '1.1', 'nr': '2.0.14', 'titel': '4 Augen Prinzip', 'text': 'Erstellung und Prüfung durch zwei verschiedene Mitarbeiter.', 'verweise': '1.4-F01 Probenahmeprotokoll\n\n Schulungen ',
      'ifs': '1.2.1', 'zustaendig': 'QB', 'vertreter': 'QV', 'aenderung': '', 'grund': 'Aufbau'}
check('Handbuch: nur mit Freigaberecht (Bearbeiter 403)', Be.call('qs_abschnitt_save', H1)[0] == 403)
for name, b in (('ohne Prozessschritt', {'titel': ''}), ('Kapitel unbekannt', {'kapitel': '7.7'}), ('Verweise keine Liste', {'verweise': 5}), ('Text zu lang', {'text': 'x' * 20001})):
    st, r = Q.call('qs_abschnitt_save', {**H1, **b})
    check(f'Abschnitt: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = Q.call('qs_abschnitt_save', H1)
h1 = r.get('abschnitt', {})
check('Abschnitt angelegt: Verweise als Liste ohne Leerzeilen, erste Änderung „Neu angelegt“, Position 1', st == 200 and h1['verweise'] == ['1.4-F01 Probenahmeprotokoll', 'Schulungen']
      and h1['aenderungen'][0]['was'] == 'Neu angelegt' and h1['aenderungen'][0]['von'] == 'Quinn QMB' and h1['pos'] == 1, r)
h2 = Q.call('qs_abschnitt_save', {**H1, 'nr': '1.0', 'titel': 'Ziel', 'verweise': []})[1]['abschnitt']
check('zweiter Abschnitt im Kapitel: Position 2', h2['pos'] == 2)
check('Ändern ohne Änderung und Grund → 422', Q.call('qs_abschnitt_save', {**H1, 'id': h1['id'], 'rev': h1['rev'], 'text': 'Neu.', 'aenderung': '', 'grund': ''})[0] == 422)
st, r = Q.call('qs_abschnitt_save', {**H1, 'id': h1['id'], 'rev': h1['rev'], 'aenderung': 'egal', 'grund': 'egal'})
check('unverändert: kein neuer Stand', st == 200 and r['unveraendert'] is True and r['abschnitt']['rev'] == h1['rev'], r)
st, r = F.call('qs_abschnitt_save', {**H1, 'id': h1['id'], 'rev': h1['rev'], 'text': 'Erstellung/Überarbeitung und Prüfung durch zwei Personen.', 'aenderung': 'Text präzisiert', 'grund': 'IFS v3'})
check('Änderung mit Grund in der Änderungsliste', st == 200 and len(r['abschnitt']['aenderungen']) == 2 and r['abschnitt']['aenderungen'][-1] == {'datum': HEUTE.isoformat(), 'was': 'Text präzisiert', 'grund': 'IFS v3', 'von': 'Fritz Freigabe'}, r)
check('Abschnitt: veralteter Stand 409', Q.call('qs_abschnitt_save', {**H1, 'id': h1['id'], 'rev': h1['rev'], 'text': 'x', 'aenderung': 'a', 'grund': 'b'})[0] == 409)
h1 = r['abschnitt']
st, r = Q.call('qs_abschnitt_save', {**h1, 'verweise': h1['verweise'], 'entfallen': True, 'aenderung': 'entfällt', 'grund': 'Prozess eingestellt'})
check('Abschnitt als entfallen markiert (nicht gelöscht)', st == 200 and r['abschnitt']['entfallen']['von'] == 'Quinn QMB', r)
hb = L.call('qs_start')[1]['handbuch']
check('Handbuch in Reihenfolge Kapitel/Position', [(x['kapitel'], x['pos']) for x in hb] == [('1.1', 1), ('1.1', 2)], hb)
check('verwendetes Kapitel nicht entfernbar (422)', V.call('qs_stamm_save', {'kapitel': [k for k in KAP if k['id'] != '1.1']})[0] == 422)
check('unbenutztes Kapitel entfernbar, verwendetes deaktivierbar', V.call('qs_stamm_save', {'kapitel': [{**k, 'aktiv': k['id'] != '1.1'} for k in KAP if k['id'] != '1.10']})[0] == 200)
V.call('qs_stamm_save', {'kapitel': [k for k in KAP if k['id'] != '1.10']})

# ── Prüfplan: rollende Intervalle und „bei Bedarf“ ──
P1 = {'kapitel': '1.1', 'titel': 'Systembewertung', 'beschreibung': 'jährlich im Januar', 'intervall': 'jaehrlich', 'start': tag(-3), 'sollwert': 'Aktuell & angemessen',
      'massnahme': 'System anpassen', 'womit': 'Review', 'zustaendig': 'QB', 'vertreter': 'QV'}
check('Prüfung anlegen nur mit Freigaberecht (Bearbeiter 403)', Be.call('qs_pruefung_save', P1)[0] == 403)
for name, b in (('ohne Bezeichnung', {'titel': ''}), ('Intervall unbekannt', {'intervall': 'manchmal'}), ('altes Intervall „laufend“', {'intervall': 'laufend'}),
                ('Start ungültig', {'start': '2026-02-30'}), ('Kapitel unbekannt', {'kapitel': '8'}), ('Mitarbeiter unbekannt', {'ausfuehrende': ['u-nix']}),
                ('Mitarbeiter keine Liste', {'ausfuehrende': 'kai'})):
    st, r = Q.call('qs_pruefung_save', {**P1, **b})
    check(f'Prüfung: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = Q.call('qs_pruefung_save', P1)
p1 = r.get('pruefung', {})
check('Prüfung angelegt: erste Fälligkeit vor 3 Tagen → rot, 3 Tage drüber, rollend, Monatsverlauf', st == 200 and p1['faellig']['naechste'] == tag(-3) and p1['faellig']['ampel'] == 'rot'
      and p1['faellig']['restTage'] == -3 and p1['faellig']['art'] == 'rollend' and p1['faellig']['offen'] is True and p1['ausfuehrende'] == []
      and len(p1['faellig']['monate']) == 7 and p1['faellig']['monate'][-1]['m'] == HEUTE.strftime('%Y-%m'), r)
p2 = Q.call('qs_pruefung_save', {**P1, 'titel': 'Kalibrierung Thermometer', 'intervall': 'quartal', 'start': tag(5)})[1]['pruefung']
check('vierteljährlich, fällig in 5 Tagen → gelb (Vorlauf 14 Tage)', p2['faellig']['ampel'] == 'gelb' and p2['faellig']['restTage'] == 5, p2['faellig'])
p3 = Q.call('qs_pruefung_save', {**P1, 'titel': 'Mikrobiologische Untersuchung', 'intervall': 'anlass', 'start': ''})[1]['pruefung']
check('bei Bedarf: keine Fälligkeit', p3['faellig']['naechste'] == '' and p3['faellig']['ampel'] == '' and p3['faellig']['art'] == '', p3['faellig'])
p4 = Q.call('qs_pruefung_save', {**P1, 'titel': 'Begehung', 'intervall': 'halbjahr', 'start': ''})[1]['pruefung']
check('ohne Nachweis und ohne erste Fälligkeit: sofort fällig (rot)', p4['faellig']['ampel'] == 'rot' and p4['faellig']['naechste'] == '', p4['faellig'])
NW = {'pruefung': p1['id'], 'datum': tag(-1), 'ergebnis': 'io', 'bemerkung': '', 'durch': ''}
check('Nachweis: nur ansehen 403', L.call('qs_nachweis_save', NW)[0] == 403)
for name, b in (('in der Zukunft', {'datum': tag(1)}), ('ohne Datum', {'datum': ''}), ('Ergebnis unbekannt', {'ergebnis': 'naja'}), ('Abweichung ohne Bemerkung', {'ergebnis': 'abweichung'})):
    st, r = Be.call('qs_nachweis_save', {**NW, **b})
    check(f'Nachweis: {name} → 422', st == 422 and r.get('error'), (st, r))
check('Nachweis: unbekannte Prüfung 404', Be.call('qs_nachweis_save', {**NW, 'pruefung': 'pnix'})[0] == 404)
st, r = Be.call('qs_nachweis_save', NW)
n1 = r.get('nachweis', {})
naechstes = (HEUTE - datetime.timedelta(days=1)).replace(year=HEUTE.year + 1) if not (HEUTE - datetime.timedelta(days=1)).strftime('%m-%d') == '02-29' else None
check('Nachweis erfasst: durchgeführt von = Name, nächste Fälligkeit in einem Jahr (grün)', st == 200 and n1['durch'] == 'Bernd Bearbeiter' and r['pruefung']['faellig']['letzter'] == tag(-1)
      and (naechstes is None or r['pruefung']['faellig']['naechste'] == naechstes.isoformat()) and r['pruefung']['faellig']['ampel'] == 'gruen' and r['pruefung']['faellig']['offen'] is False, r)
st, r = Be.call('qs_nachweis_save', {'pruefung': p2['id'], 'datum': '2024-11-30', 'ergebnis': 'io'})
check('vierteljährlich ab 30.11.2024 → 28.02.2025 (Monatsende, kein Überlauf)', st == 200 and r['pruefung']['faellig']['naechste'] == '2025-02-28' and r['pruefung']['faellig']['ampel'] == 'rot', r)
st, r = Be.call('qs_nachweis_save', {'pruefung': p4['id'], 'datum': tag(0), 'ergebnis': 'abweichung', 'bemerkung': 'Kühlzelle 2: Kondenswasser an der Decke',
                                     'massnahme': {'korrektur': 'Ware umgelagert', 'massnahme': 'Abtauzyklus prüfen', 'zustaendig': 'QB', 'frist': tag(14)}})
m1 = r.get('massnahme') or {}
check('Abweichung mit Maßnahme: Nummer je Jahr, Quelle Prüfplan, Bezug, Korrektur, in beide Richtungen verknüpft', st == 200 and m1['nr'] == f'{JAHR}-001' and m1['quelle'] == 'pruefung'
      and 'Begehung' in m1['bezug'] and m1['feststellung'] == 'Kühlzelle 2: Kondenswasser an der Decke' and m1['korrektur'] == 'Ware umgelagert' and m1['pruefung'] == p4['id']
      and m1['nachweisId'] == r['nachweis']['id'] and r['nachweis']['massnahme'] == m1['id'] and m1['status'] == 'offen', r)
check('Stornieren ohne Grund → 422', Be.call('qs_nachweis_storno', {'id': n1['id'], 'grund': ''})[0] == 422)
check('Stornieren: nur ansehen 403', L.call('qs_nachweis_storno', {'id': n1['id'], 'grund': 'x'})[0] == 403)
check('Stornieren: fremder Nachweis mit „Kontrollen durchführen“ 403', KA.call('qs_nachweis_storno', {'id': n1['id'], 'grund': 'x'})[0] == 403)
st, r = Be.call('qs_nachweis_storno', {'id': n1['id'], 'grund': 'falsche Prüfung'})
check('storniert (bleibt sichtbar), nicht doppelt', st == 200 and r['nachweis']['storno']['grund'] == 'falsche Prüfung' and Be.call('qs_nachweis_storno', {'id': n1['id'], 'grund': 'x'})[0] == 409, r)
pr = {x['id']: x for x in L.call('qs_start')[1]['pruefungen']}
check('storniert zählt nicht: wieder fällig ab der ersten Fälligkeit', pr[p1['id']]['faellig']['naechste'] == tag(-3) and pr[p1['id']]['faellig']['anzahl'] == 0, pr[p1['id']]['faellig'])
st, r = Q.call('qs_pruefung_save', {**P1, 'id': p1['id'], 'rev': p1['rev'], 'aktiv': False})
check('Prüfung deaktiviert: ohne Ampel, Verlauf', st == 200 and r['pruefung']['faellig']['ampel'] == '' and 'aktiv' in r['pruefung']['verlauf'][-1]['was'], r)
check('inaktive Prüfung: kein Nachweis (409)', Be.call('qs_nachweis_save', NW)[0] == 409)
check('Prüfung: veralteter Stand 409', Q.call('qs_pruefung_save', {**P1, 'id': p1['id'], 'rev': p1['rev']})[0] == 409)

# ── Prüfplan: Kalender-Intervalle („täglich heißt täglich“), versäumte Perioden, Zuweisung ──
st, r = Q.call('qs_pruefung_save', {**P1, 'titel': 'Reinigungskontrolle', 'intervall': 'taeglich', 'start': tag(-9), 'zustaendig': 'GF', 'vertreter': ''})
p5 = r['pruefung']; f = p5['faellig']
check('täglich ab vor 9 Tagen ohne Nachweis: 9 Tage versäumt (neueste zuerst), heute offen, rot, Quote 0/9', st == 200 and f['art'] == 'kalender' and f['versaeumtAnzahl'] == 9
      and f['versaeumt'][0] == tag(-1) and f['versaeumt'][-1] == tag(-9) and f['offen'] is True and f['naechste'] == tag(0) and f['restTage'] == 0 and f['ampel'] == 'rot'
      and f['quote'] == {'erfuellt': 0, 'faellig': 9}, f)
check('nicht zugewiesen: „Kontrollen durchführen“ darf keinen Nachweis erfassen (403)', KA.call('qs_nachweis_save', {'pruefung': p5['id'], 'datum': tag(-1), 'ergebnis': 'io'})[0] == 403)
st, r = Q.call('qs_pruefung_save', {**P1, 'titel': 'Reinigungskontrolle', 'intervall': 'taeglich', 'start': tag(-9), 'zustaendig': 'GF', 'vertreter': '', 'id': p5['id'], 'rev': p5['rev'],
                                    'ausfuehrende': [ids['kai'], ids['kai'], ids['bernd']]})
check('Zuweisung an Mitarbeiter (doppelt nur einmal), Verlauf', st == 200 and r['pruefung']['ausfuehrende'] == [ids['kai'], ids['bernd']] and 'Durchführung' in r['pruefung']['verlauf'][-1]['was'], r)
st, r = KA.call('qs_nachweis_save', {'pruefung': p5['id'], 'datum': tag(-1), 'ergebnis': 'io'})
nk = r.get('nachweis', {})
check('zugewiesen: Nachweis durch Kai (gestern, nachgetragen)', st == 200 and nk['durch'] == 'Kai Kontrolle' and nk['erfasst']['vonId'] == ids['kai'], r)
st, r = KA.call('qs_nachweis_save', {'pruefung': p5['id'], 'datum': tag(-3), 'ergebnis': 'abweichung', 'bemerkung': 'Abfluss verschmutzt', 'massnahme': {'massnahme': 'x'}})
check('Maßnahme aus dem Nachweis nur mit „bearbeiten“ (403, nichts gespeichert)', st == 403 and len([n for n in L.call('qs_start')[1]['nachweise'] if n['pruefung'] == p5['id']]) == 1, r)
st, r = KA.call('qs_nachweis_save', {'pruefung': p5['id'], 'datum': tag(-3), 'ergebnis': 'abweichung', 'bemerkung': 'Abfluss verschmutzt'})
f = r['pruefung']['faellig']
check('zwei Tage erfüllt: 7 versäumt, Quote 2/9, gestern erfüllt → heute offen (gelb)', st == 200 and f['versaeumtAnzahl'] == 7 and tag(-1) not in f['versaeumt'] and tag(-3) not in f['versaeumt']
      and f['quote'] == {'erfuellt': 2, 'faellig': 9} and f['ampel'] == 'gelb' and f['offen'] is True and f['letztesErgebnis'] == 'io', f)
mv = {m['m']: m for m in f['monate']}
erw = {}
for dlt in range(-9, 0):
    mon = tag(dlt)[:7]; erw.setdefault(mon, [0, 0]); erw[mon][0] += 1; erw[mon][1] += dlt in (-1, -3)
check('Monatsverlauf: fällige und erfüllte Tage je Monat, Abweichung markiert', all(mv[k]['faellig'] == a and mv[k]['erfuellt'] == b for k, (a, b) in erw.items())
      and mv[tag(-3)[:7]]['abweichung'] is True, (f['monate'], erw))
st, r = KA.call('qs_nachweis_save', {'pruefung': p5['id'], 'datum': tag(0), 'ergebnis': 'io'})
check('heute erledigt: nicht mehr offen, nächste morgen, grün', st == 200 and r['pruefung']['faellig']['offen'] is False and r['pruefung']['faellig']['naechste'] == tag(1)
      and r['pruefung']['faellig']['ampel'] == 'gruen', r['pruefung']['faellig'])
st, r = KA.call('qs_nachweis_storno', {'id': nk['id'], 'grund': 'falscher Tag'})
check('eigenen Nachweis storniert (Kai)', st == 200 and r['nachweis']['storno']['von'] == 'Kai Kontrolle', r)
# Zuweisung über das Kürzel (Kai = QV): zuständig/Vertreter
p6 = Q.call('qs_pruefung_save', {**P1, 'titel': 'Temperaturkontrolle Lager', 'intervall': 'arbeitstaeglich', 'start': tag(-14), 'zustaendig': 'GF', 'vertreter': 'QV'})[1]['pruefung']
f = p6['faellig']
arbeit = [tag(d) for d in range(-14, 0) if (HEUTE + datetime.timedelta(days=d)).weekday() < 5 and not feiertag_hamburg(HEUTE + datetime.timedelta(days=d))]
heute_arbeit = HEUTE.weekday() < 5 and not feiertag_hamburg(HEUTE)
check('arbeitstäglich: nur Mo–Fr ohne Hamburger Feiertage versäumt, heute offen nur an Arbeitstagen', f['versaeumtAnzahl'] == len(arbeit) and f['versaeumt'] == list(reversed(arbeit))
      and f['offen'] is heute_arbeit and f['ampel'] == 'rot', (f, arbeit))
check('über das Kürzel (Vertreter QV = Kai) zugewiesen: Nachweis erlaubt', KA.call('qs_nachweis_save', {'pruefung': p6['id'], 'datum': arbeit[-1], 'ergebnis': 'io'})[0] == 200)
montag = HEUTE - datetime.timedelta(days=HEUTE.weekday())
p7 = Q.call('qs_pruefung_save', {**P1, 'titel': 'Schädlingskontrolle', 'intervall': 'woechentlich', 'start': tag(-21)})[1]['pruefung']
f = p7['faellig']
wochen = (montag - (HEUTE - datetime.timedelta(days=21) - datetime.timedelta(days=(HEUTE - datetime.timedelta(days=21)).weekday()))).days // 7
sonntag = (montag + datetime.timedelta(days=6)).isoformat()
check('wöchentlich: vergangene Wochen versäumt, diese Woche offen bis Sonntag (rot)', f['versaeumtAnzahl'] == wochen == 3 and f['offen'] is True and f['naechste'] == sonntag and f['ampel'] == 'rot', f)
st, r = Be.call('qs_nachweis_save', {'pruefung': p7['id'], 'datum': (montag - datetime.timedelta(days=3)).isoformat(), 'ergebnis': 'io'})
f = r['pruefung']['faellig']
check('Nachweis in der Vorwoche: 2 versäumt, zuletzt erfüllt → gelb (fällig bis Sonntag)', f['versaeumtAnzahl'] == 2 and f['ampel'] == 'gelb' and f['quote'] == {'erfuellt': 1, 'faellig': 3}, f)
erster = HEUTE.replace(day=1)
vor2 = (erster - datetime.timedelta(days=1)).replace(day=1)
vor2 = (vor2 - datetime.timedelta(days=1)).replace(day=1)
p8 = Q.call('qs_pruefung_save', {**P1, 'titel': 'Fremdkörperüberwachung', 'intervall': 'monatlich', 'start': vor2.isoformat()})[1]['pruefung']
f = p8['faellig']
monatsende = ((erster + datetime.timedelta(days=32)).replace(day=1) - datetime.timedelta(days=1)).isoformat()
check('monatlich: zwei Monate versäumt, dieser Monat offen bis Monatsende (rot)', f['versaeumtAnzahl'] == 2 and f['offen'] is True and f['naechste'] == monatsende and f['ampel'] == 'rot', f)
letzter_vormonat = erster - datetime.timedelta(days=1)
st, r = Be.call('qs_nachweis_save', {'pruefung': p8['id'], 'datum': letzter_vormonat.isoformat(), 'ergebnis': 'io'})
f = r['pruefung']['faellig']
check('Nachweis im Vormonat: 1 versäumt, nicht rot, Monatsverlauf Vormonat 1/1', f['versaeumtAnzahl'] == 1 and f['ampel'] in ('gelb', 'gruen')
      and {m['m']: m for m in f['monate']}[letzter_vormonat.strftime('%Y-%m')] == {'m': letzter_vormonat.strftime('%Y-%m'), 'faellig': 1, 'erfuellt': 1, 'abweichung': False}, f)

# ── Maßnahmen (Aufbau des IFS-Maßnahmenplans) ──
M = {'quelle': 'intern', 'bezug': 'Internes Audit 2026', 'kapitel': '1.1', 'anforderung': '4.8.2', 'bewertung': 'B', 'anforderungText': 'Messgeräte sind zu kalibrieren.',
     'feststellung': 'Thermometer nicht kalibriert', 'korrektur': 'Thermometer ausgetauscht', 'korrekturVerantwortlich': 'QB', 'korrekturFrist': tag(-5), 'korrekturErledigt': tag(-4),
     'nachweisDoku': 'Kalibrierprotokoll', 'ursache': 'Kalibrierintervall fehlte', 'massnahme': 'Kalibrierplan', 'zustaendig': 'QB', 'frist': tag(-2), 'status': 'offen'}
check('Maßnahme: nur ansehen 403, Kontrollen durchführen 403', L.call('qs_massnahme_save', M)[0] == 403 and KA.call('qs_massnahme_save', M)[0] == 403)
for name, b in (('ohne Feststellung', {'feststellung': ''}), ('Quelle unbekannt', {'quelle': 'xx'}), ('Status unbekannt', {'status': 'fertig'}), ('Frist ungültig', {'frist': '31.12.2026'}),
                ('Bewertung unbekannt', {'bewertung': 'E'}), ('Korrektur bis ungültig', {'korrekturFrist': '2026-13-01'}), ('Anforderung zu lang', {'anforderung': '1' * 21})):
    st, r = Be.call('qs_massnahme_save', {**M, **b})
    check(f'Maßnahme: {name} → 422', st == 422 and r.get('error'), (st, r))
st, r = Be.call('qs_massnahme_save', M)
m2 = r.get('massnahme', {})
check('Maßnahme erfasst: nächste Nummer, IFS-Felder, überfällig (Frist vorbei)', st == 200 and m2['nr'] == f'{JAHR}-002' and m2['ueberfaellig'] is True
      and all(m2[k] == M[k] for k in ('anforderung', 'bewertung', 'anforderungText', 'korrektur', 'korrekturVerantwortlich', 'korrekturFrist', 'korrekturErledigt', 'nachweisDoku', 'ursache')), r)
st, r = Be.call('qs_massnahme_save', {**M, 'id': m2['id'], 'rev': m2['rev'], 'status': 'umgesetzt', 'erledigtAm': tag(0)})
check('Bearbeiter: umgesetzt (nicht mehr überfällig)', st == 200 and r['massnahme']['status'] == 'umgesetzt' and r['massnahme']['ueberfaellig'] is False and r['massnahme']['erledigtAm'] == tag(0), r)
m2 = r['massnahme']
check('wirksam nur mit Freigaberecht (403)', Be.call('qs_massnahme_save', {**M, 'id': m2['id'], 'rev': m2['rev'], 'status': 'wirksam', 'wirksamkeitNotiz': 'ok'})[0] == 403)
check('wirksam ohne Notiz → 422', Q.call('qs_massnahme_save', {**M, 'id': m2['id'], 'rev': m2['rev'], 'status': 'wirksam'})[0] == 422)
st, r = Q.call('qs_massnahme_save', {**M, 'id': m2['id'], 'rev': m2['rev'], 'status': 'wirksam', 'wirksamkeitNotiz': 'Stichprobe 3 Thermometer, alle kalibriert',
                                     'freigabeVon': 'Auditor A', 'freigabeDatum': tag(0), 'freigabeNotiz': 'akzeptiert'})
check('wirksam: Wirksamkeitsprüfung mit Name und Notiz, Freigabe durch den Auditor, Verlauf', st == 200 and r['massnahme']['wirksamkeit']['von'] == 'Quinn QMB'
      and r['massnahme']['wirksamkeit']['notiz'].startswith('Stichprobe') and r['massnahme']['freigabeVon'] == 'Auditor A' and r['massnahme']['freigabeDatum'] == tag(0)
      and 'Umgesetzt → Wirksam' in r['massnahme']['verlauf'][-1]['was'], r)
m2 = r['massnahme']
check('abgeschlossene Maßnahme ändert nur das Freigaberecht (403)', Be.call('qs_massnahme_save', {**M, 'id': m2['id'], 'rev': m2['rev'], 'status': 'wirksam', 'bezug': 'anders'})[0] == 403)
st, r = Q.call('qs_massnahme_save', {**M, 'id': m2['id'], 'rev': m2['rev'], 'status': 'in_arbeit'})
check('wieder geöffnet: Wirksamkeit entfernt', st == 200 and r['massnahme']['wirksamkeit'] is None and r['massnahme']['status'] == 'in_arbeit', r)
check('verwerfen ohne Grund → 422', Q.call('qs_massnahme_save', {**M, 'id': m2['id'], 'rev': r['massnahme']['rev'], 'status': 'verworfen'})[0] == 422)
check('Maßnahme: veralteter Stand 409', Be.call('qs_massnahme_save', {**M, 'id': m2['id'], 'rev': 1})[0] == 409)

# ── CSV ──
Be.call('qs_dokument_save', {'kapitel': '2.1', 'art': 'L', 'nr': '2.1-L09', 'titel': '=HYPERLINK("http://x.invalid")', 'zustaendig': '@GF'})
for liste, kopf in (('dokumente', 'Überprüfung'), ('pruefplan', 'Versäumt seit Beginn'), ('massnahmen', 'IFS-Anforderung')):
    st, _, roh = L.call('qs_export', {'liste': liste}, raw=True)
    check(f'CSV {liste}: BOM, Kopf, Semikolon', st == 200 and roh.startswith('﻿') and kopf in roh.split('\r\n')[0] and ';' in roh, roh[:300])
    if liste == 'dokumente':
        check('CSV: keine Formeln (Titel und Kürzel mit Hochkomma), Version 2', '"\'=HYPERLINK' in roh and '"\'@GF"' in roh and '"1.4-F01";"Formblatt";"Probenahmeprotokoll";"2"' in roh, roh)
    if liste == 'pruefplan':
        check('CSV Prüfplan: Durchführung mit Mitarbeiternamen, Quote', 'Kai Kontrolle, Bernd Bearbeiter' in roh and ' von ' in roh, roh)
    if liste == 'massnahmen':
        check('CSV Maßnahmen: IFS-Anforderung, Bewertung, Korrektur', '"4.8.2";"B";"Thermometer nicht kalibriert";"Thermometer ausgetauscht"' in roh, roh)
check('CSV: unbekannte Liste 422, ohne Recht 403', L.call('qs_export', {'liste': 'geheim'})[0] == 422 and O.call('qs_export', {'liste': 'dokumente'})[0] == 403)

# ── Datenpaket ──
paket = json.load(open(PAKET_DATEI, encoding='utf-8'))
for x in paket['dokumente']:
    if x['nr'] == '1.4-F02':
        x['versionen'][0]['datum'] = tag(-30)   # aktuell freigegeben (Überprüfung erst in drei Jahren)
check('Datenpaket nur mit „verwalten“ (Freigabe 403)', Q.call('qs_import', {'paket': paket, 'vorschau': True})[0] == 403)
check('falsches Format → 422', V.call('qs_import', {'paket': {'format': 'stafl-leergut', 'version': 1}, 'vorschau': True})[0] == 422)
kaputt = json.loads(json.dumps(paket))
kaputt['dokumente'][1]['nr'] = kaputt['dokumente'][0]['nr']
kaputt['dokumente'][2]['versionen'].append({'nr': 2, 'datum': '2024-01-01'})
kaputt['dokumente'][6]['versionen'] = [{'nr': 1}]
kaputt['handbuch'][0]['kapitel'] = '9.9'
kaputt['pruefungen'][0]['intervall'] = 'nie'
kaputt['massnahmen'][0]['bewertung'] = 'Z'
st, r = V.call('qs_import', {'paket': kaputt, 'vorschau': True})
teile = sorted((f['teil'], f['zeile']) for f in r.get('fehler', []))
check('Vorschau: Fehler je Eintrag (doppelte Nr., doppelte Version, Ordner mit Version, Kapitel, Intervall, Bewertung)', st == 200
      and teile == [('dokumente', 2), ('dokumente', 3), ('dokumente', 7), ('handbuch', 1), ('massnahmen', 1), ('pruefungen', 1)] and r['leer'] is False, r)
anzahl_vorher = len(L.call('qs_start')[1]['dokumente'])
st, r = V.call('qs_import', {'paket': kaputt})
check('mit Fehlern: nichts übernommen (422)', st == 422 and len(L.call('qs_start')[1]['dokumente']) == anzahl_vorher == 3, r)
st, r = V.call('qs_import', {'paket': paket})
check('Daten vorhanden ohne „ersetzen“ → 409', st == 409, r)
V.call('qs_stamm_save', {'einstellungen': {'ueberpruefungMonate': 48}})
st, r = V.call('qs_import', {'paket': paket, 'ersetzen': True})
check('Datenpaket übernommen (ersetzt): Zahlen', st == 200 and r['zahlen'] == {'kapitel': 4, 'personen': 4, 'dokumente': 9, 'versionen': 7, 'handbuch': 5, 'pruefungen': 6, 'massnahmen': 1}, r)
d = L.call('qs_start')[1]
check('Einstellungen bleiben beim Ersetzen (48 Monate)', d['einstellungen']['ueberpruefungMonate'] == 48, d['einstellungen'])
V.call('qs_stamm_save', {'einstellungen': {'ueberpruefungMonate': 36}})
d = L.call('qs_start')[1]
dk = {x['nr'] or x['titel']: x for x in d['dokumente']}
l02 = dk['1.3-L02']
check('Excel-Versionen: höchste gilt, ältere ersetzt, Kürzel als Schnappschuss', [v['status'] for v in l02['versionen']] == ['ersetzt', 'freigegeben'] and l02['versionen'][1]['kuerzel'] == {'erstellt': 'QB', 'geprueft': 'QV', 'freigegeben': 'QB'}
      and l02['zustand'] == 'gueltig' and l02['versionen'][1]['aenderungen'] == 'Innereien ergänzt', l02)
check('ohne Version: „ohne“; Ordner/extern: Register; Version „1“ als Text; ohne Datum erlaubt', dk['1.4-F07']['zustand'] == 'ohne' and dk['Befunde']['zustand'] == 'register' and dk['HACCP-Zertifikat']['art'] == 'X'
      and dk['2.1-E01']['versionen'][0]['nr'] == 1 and dk['2.1-E01']['versionen'][0]['datum'] == '')
check('Überprüfung: Freigabe 2023 nach 36 Monaten fällig, ohne Datum fällig, vor 30 Tagen nicht', l02['ueberpruefung'] == {'seit': '2023-03-02', 'faelligAb': '2026-03-02', 'faellig': HEUTE.isoformat() >= '2026-03-02'}
      and dk['2.1-E01']['ueberpruefung']['faellig'] is True and dk['1.4-F02']['ueberpruefung']['faellig'] is False and dk['Befunde']['ueberpruefung'] is None)
check('Nachweise beim Ersetzen geleert, Handbuch je Kapitel nummeriert', d['nachweise'] == [] and [(x['kapitel'], x['pos']) for x in d['handbuch']] == [('1.1', 1), ('1.1', 2), ('1.1', 3), ('1.3', 1), ('1.4', 1)])
pp = {x['titel']: x for x in d['pruefungen']}
check('Prüfplan aus dem Paket: erste Fälligkeit, Kalender, bei Bedarf, noch nicht begonnen', pp['Systembewertung']['faellig']['naechste'] == '2026-01-31'
      and pp['Wareneingangsprüfung']['faellig']['art'] == 'kalender' and pp['Mikrobiologische Untersuchung']['faellig']['ampel'] == ''
      and pp['Fremdkörperüberwachung']['faellig']['ampel'] == 'gruen' and all(x['ausfuehrende'] == [] for x in d['pruefungen']))
m0 = d['massnahmen'][0]
check('Maßnahme aus dem Paket mit Nummer und IFS-Feldern', m0['nr'] == '2026-001' and m0['status'] == 'in_arbeit' and m0['anforderung'] == '4.8.2' and m0['bewertung'] == 'B'
      and m0['korrektur'] == 'Thermometer sofort nachkalibriert' and m0['ursache'] == 'Kalibrierintervall nicht festgelegt', m0)
check('Personen aus dem Paket ohne Verknüpfung', all(p_['mitarbeiter'] == '' for p_ in d['personen']), d['personen'])
# Für die Oberfläche: Kürzel verknüpfen (QB = Quinn, QV = Kai), Reinigungskontrolle Kai zuweisen
pers = [{**p_, 'mitarbeiter': {'QB': ids['quinn'], 'QV': ids['kai']}.get(p_['id'], '')} for p_ in d['personen']]
check('Verknüpfung nach dem Import', V.call('qs_stamm_save', {'personen': pers})[0] == 200)
rk = pp['Reinigungskontrolle Kühlhaus']
check('Reinigungskontrolle Kai zugewiesen', Q.call('qs_pruefung_save', {**{k: rk[k] for k in ('kapitel', 'titel', 'beschreibung', 'intervall', 'start', 'womit', 'sollwert', 'massnahme', 'zustaendig', 'vertreter', 'aktiv')},
                                                                         'id': rk['id'], 'rev': rk['rev'], 'ausfuehrende': [ids['kai']]})[0] == 200)

# ── Protokoll ──
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Dokument, Freigabe, Überprüfung, Handbuch, Nachweis, Maßnahme, CSV, Datenpaket', all(t in log for t in ('QM-System: Dokument 1.4-F01 Probenahmeprotokoll angelegt', 'Version 2 freigegeben',
      'ohne Änderung überprüft', 'QM-System: Handbuch 1.1 2.0.14', 'QM-System: Nachweis „Begehung“', f'Maßnahme {JAHR}-002 gespeichert', 'Dokumentenliste als CSV heruntergeladen',
      'QM-System: Datenpaket übernommen')), log[-3000:])
check('Protokoll ohne Texte (Feststellung, Bemerkung, Grund des Einziehens, Notiz)', 'Kondenswasser' not in log and 'Thermometer nicht kalibriert' not in log and 'DMS-Formular' not in log
      and 'Inhalt weiter aktuell' not in log)

# ── Oberfläche ──
with sync_playwright() as p:
    br = p.chromium.launch()

    def text(pg, sel):
        return pg.inner_text(sel).replace('\xa0', ' ')

    def anmelden(user, pw, ip, breite=1280, thema='light', hoehe=900, ziel='#qm-app:not([hidden])'):
        ctx = br.new_context(viewport={'width': breite, 'height': hoehe}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin',
                             color_scheme=thema, accept_downloads=True)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.on('console', lambda m: fehler.append(m.text) if m.type == 'error' and 'Failed to load resource' not in m.text else None)
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        pg.goto(B + '/module/qs/'); pg.wait_for_selector(ziel)
        return ctx, pg

    def toast(pg, inhalt):
        pg.wait_for_function('t => document.querySelector("#qm-toast").classList.contains("zeigen") && document.querySelector("#qm-toast").textContent.includes(t)', arg=inhalt)
        return True

    # Quinn (QMB, Kürzel QB): Übersicht, Dokumente, Handbuch, Prüfplan, Maßnahmen
    ctx, pg = anmelden('quinn', 'Freigabe-Konto-56', '198.51.100.12')
    pg.wait_for_selector('#qm-u-kpis .qm-kpi')
    kpis = [pg.inner_text(f'#qm-u-kpis .qm-kpi:nth-child({i}) b') for i in range(1, 5)]
    check('Übersicht: Adresse #uebersicht, vier Kennzahlen (6 gültig, 5 Überprüfung fällig, 1 offene Maßnahme)', pg.url.endswith('#uebersicht') and kpis[0] == '6' and kpis[1] == '5' and kpis[3] == '1', kpis)
    check('Übersicht: Unterzeile mit Kapiteln und Dokumenten', '4 Kapitel' in text(pg, '#qm-unterzeile') and '7 gelenkte Dokumente' in text(pg, '#qm-unterzeile'), text(pg, '#qm-unterzeile'))
    check('Ihre Aufgaben: eigene Kontrollen (Kürzel QB) und eigene Maßnahme', 'Systembewertung' in text(pg, '#qm-u-aufgaben') and 'Ihre Kontrolle' in text(pg, '#qm-u-aufgaben')
          and '2026-001' in text(pg, '#qm-u-aufgaben') and 'Überprüfung fällig' in text(pg, '#qm-u-aufgaben'), text(pg, '#qm-u-aufgaben'))
    check('Fällige Prüfungen, Stand je Kapitel (4 Balken), offene Maßnahme', 'Systembewertung' in text(pg, '#qm-u-faellig') and pg.locator('#qm-u-kapitel [data-kap-dok]').count() == 4
          and '2026-001' in text(pg, '#qm-u-massn'))
    check('Freigaberecht: Handbuch- und Prüfplan-Knöpfe, ohne Einstellungen', pg.is_hidden('#qm-tabs [data-tab="einstellungen"]') and pg.locator('#qm-h-neu').get_attribute('hidden') is None)
    pg.screenshot(path=os.path.join(SH, 'qs_uebersicht_1280.png'), full_page=True)
    pg.click('#qm-u-kpis [data-kpi="ueberpruefung"]'); pg.wait_for_selector('#qm-t-dokumente:not([hidden])')
    check('Kennzahl „Überprüfung fällig“ öffnet die Dokumente gefiltert', pg.locator('#qm-d-zustand [data-zustand="ueberpruefung"][aria-pressed="true"]').count() == 1
          and pg.locator('#qm-d-liste tr[data-dok]').count() == 5 and pg.url.endswith('#dokumente'))
    pg.click('#qm-d-zustand [data-zustand=""]')
    check('Dokumente: Gruppen je Kapitel, Kürzel mit Namen', pg.locator('#qm-d-liste tr.qm-gruppe').count() == 4 and pg.locator('#qm-d-liste abbr[title^="Quinn Beispiel"]').count() >= 2)
    pg.fill('#qm-d-suche', 'haccp')
    check('Dokumente: Suche', pg.locator('#qm-d-liste tr[data-dok]').count() == 2)
    pg.fill('#qm-d-suche', ''); pg.click('#qm-d-zustand [data-zustand="register"]')
    check('Dokumente: Filter Ordner und externe Dokumente', pg.locator('#qm-d-liste tr[data-dok]').count() == 2)
    pg.click('#qm-d-zustand [data-zustand=""]')
    pg.screenshot(path=os.path.join(SH, 'qs_dokumente_1280.png'), full_page=True)
    pg.click(f'#qm-d-liste tr[data-dok="{l02["id"]}"]'); pg.wait_for_selector('#qm-dk:not([hidden]) h2')
    check('Seitenleiste: Titel, Versionen (2, 1), „Überprüfung fällig“, Überarbeiten und „Ohne Änderung überprüft“', text(pg, '#qm-dk h2') == 'HACCP-Analyse' and pg.locator('#qm-dk .qm-version').count() == 2
          and 'Überprüfung fällig' in text(pg, '#qm-dk .qm-chips') and pg.is_visible('#qm-dk [data-schritt="neu"]') and pg.is_visible('#qm-dk [data-schritt="ueberprueft"]')
          and pg.locator('#qm-d-liste tr.qm-gewaehlt').count() == 1)
    pg.click('#qm-dk [data-schritt="ueberprueft"]'); pg.wait_for_selector('#dlg-grund[open]')
    pg.fill('#gr-grund', 'Inhalt geprüft, aktuell'); pg.click('#gr-ok')
    toast(pg, 'Als überprüft vermerkt'); pg.wait_for_selector('#qm-dk .qm-chips >> text=nächste Überprüfung')
    check('ohne Änderung überprüft: nächste Überprüfung in drei Jahren, Vermerk mit Notiz', f'{HEUTE.year + 3}' in text(pg, '#qm-dk .qm-chips') and 'Inhalt geprüft, aktuell' in text(pg, '#qm-dk .qm-dl'))
    pg.click('#qm-dk [data-schritt="neu"]'); pg.wait_for_selector('#dk-meldung:not(:empty)')
    check('Überarbeitung ohne Stichworte: Fehler in der Seitenleiste', 'Änderungen' in text(pg, '#dk-meldung'), text(pg, '#dk-meldung'))
    pg.fill('#dk-aend', 'Gefahr Fremdkörper ergänzt'); pg.fill('#dk-grund', 'Internes Audit'); pg.click('#qm-dk [data-schritt="neu"]')
    pg.wait_for_selector('#qm-dk [data-schritt="einreichen"]')
    check('Entwurf: Ablauf Entwurf → Prüfung → Freigabe, Entwurf aktiv', pg.locator('#qm-dk .qm-schritte li').count() == 3 and 'Entwurf' in text(pg, '#qm-dk .qm-schritte li.jetzt'))
    pg.screenshot(path=os.path.join(SH, 'qs_dokument_entwurf_1280.png'))
    pg.click('#qm-dk [data-schritt="einreichen"]'); toast(pg, 'Zur Prüfung gegeben')
    pg.wait_for_selector('#qm-dk .qm-schritte li.jetzt >> text=Prüfung')
    check('eingereicht: kein „Prüfen“ für den Ersteller, Hinweis 4-Augen-Prinzip', pg.locator('#qm-dk [data-schritt="pruefen_freigeben"]').count() == 0 and '4-Augen-Prinzip' in text(pg, '#qm-dk'))
    pg.click('#qm-dk [data-dk="schliessen"]'); pg.wait_for_selector('#qm-dk', state='hidden')
    # Dokument anlegen: Nummernvorschlag nach der Struktur
    pg.click('#qm-d-neu'); pg.wait_for_selector('#dlg-dokform[open]')
    pg.select_option('#df-kapitel', '1.4'); pg.select_option('#df-art', 'F')
    check('Dokument anlegen: Nummer nach der Struktur vorgeschlagen (1.4-F08)', pg.input_value('#df-nr') == '1.4-F08', pg.input_value('#df-nr'))
    pg.select_option('#df-art', 'A')
    check('Art gewechselt: Vorschlag folgt (1.4-A02)', pg.input_value('#df-nr') == '1.4-A02', pg.input_value('#df-nr'))
    pg.click('#dlg-dokform .qm-knopfreihe [data-schliessen]')
    # Handbuch
    pg.click('#qm-tabs [data-tab="handbuch"]')
    check('Handbuch: Kapitel mit Anzahl, alle Abschnitte mit Kapitelköpfen', pg.locator('#qm-h-kapitel [data-kap]').count() == 5 and pg.locator('.qm-abschnitt').count() == 5 and pg.locator('.qm-kapitelkopf').count() == 3)
    pg.fill('#qm-h-suche', 'ccp')
    check('Handbuch: Suche mit Markierung', pg.locator('.qm-abschnitt').count() == 1 and pg.locator('.qm-abschnitt mark').count() >= 1)
    pg.fill('#qm-h-suche', ''); pg.click('#qm-h-kapitel [data-kap="1.1"]')
    check('Handbuch: Kapitel 1.1 mit Ziel als Einleitung', text(pg, '#qm-h-titel') == 'Managementsystem' and 'Einheitliche Gliederung' in text(pg, '#qm-h-ziel')
          and pg.locator('.qm-abschnitt').count() == 2 and 'Zuständig QB (Quinn Beispiel)' in text(pg, '#qm-h-meta'))
    pg.click('#qm-h-kapitel [data-kap="1.3"]')
    check('Handbuch: Kapitel 1.3 gewählt', text(pg, '#qm-h-titel') == 'HACCP' and pg.text_content('#qm-h-ueber') == 'Kapitel 1.3' and pg.locator('.qm-abschnitt').count() == 1 and pg.is_hidden('#qm-h-ziel'))
    pg.click('.qm-abschnitt button.qm-verweis'); pg.wait_for_selector('#qm-dk:not([hidden]) h2')
    check('Verweis „1.3-L02 HACCP-Analyse“ öffnet das Dokument', text(pg, '#qm-dk h2') == 'HACCP-Analyse' and pg.url.endswith('#dokumente'))
    pg.click('#qm-dk [data-dk="schliessen"]')
    pg.click('#qm-tabs [data-tab="handbuch"]')
    pg.click('.qm-abschnitt [data-abschnitt]'); pg.wait_for_selector('#dlg-abschnitt[open]')
    pg.fill('#ab-text', 'Prozessschritte mit nicht akzeptabler Gefährdung sind kritische Kontrollpunkte (CCP).'); pg.click('#ab-form [type="submit"]')
    pg.wait_for_selector('#ab-meldung:not(:empty)')
    check('Abschnitt ändern ohne Grund: Fehler im Dialog', 'Änderungsgrund' in text(pg, '#ab-meldung'))
    pg.fill('#ab-aend', 'Begriff CCP ausgeschrieben'); pg.fill('#ab-grund', 'Verständlichkeit'); pg.click('#ab-form [type="submit"]')
    pg.wait_for_selector('#dlg-abschnitt', state='hidden'); pg.wait_for_selector('.qm-abschnitt footer >> text=Begriff CCP ausgeschrieben')
    check('Abschnitt geändert: letzte Änderung im Fuß', 'Verständlichkeit' in text(pg, '.qm-abschnitt footer'))
    pg.click('#qm-h-kapitel [data-kap="1.1"]')
    pg.screenshot(path=os.path.join(SH, 'qs_handbuch_1280.png'), full_page=True)
    # Prüfplan: Jahresplan, Nachweis mit Abweichung und Maßnahme
    pg.click('#qm-tabs [data-tab="pruefplan"]')
    check('Jahresplan: sechs Prüfungen, 12 Monatsspalten, aktueller Monat markiert', pg.locator('#qm-p-liste .qm-plan-zeile[data-pruefung]').count() == 6
          and pg.locator('#qm-p-liste .qm-plan-zeile.kopf span').count() == 15 and pg.locator('#qm-p-liste .qm-plan-zeile.kopf .heute').count() == 1)
    we = '#qm-p-liste .qm-plan-zeile:has-text("Wareneingangsprüfung")'
    check('arbeitstäglich: erfüllte Tage je Monat und versäumte Tage', pg.locator(f'{we} .qm-quote').count() >= 2 and 'versäumt' in text(pg, we), text(pg, we))
    check('bei Bedarf: ohne Monatsraster', pg.locator('#qm-p-liste .qm-plan-zeile:has-text("Mikrobiologische Untersuchung") .qm-bedarf').count() == 1)
    bg = '#qm-p-liste .qm-plan-zeile:has-text("Begehung Veterinär")'
    pg.click(f'{bg} [data-nachweis]'); pg.wait_for_selector('#dlg-nachweis[open]')
    check('Nachweis: Datum heute, durchgeführt von Quinn, In Ordnung vorgewählt, ohne Maßnahme-Felder', pg.input_value('#nw-durch') == 'Quinn QMB' and pg.input_value('#nw-datum') == HEUTE.isoformat()
          and pg.is_hidden('#nw-massn-z'))
    pg.click('#dlg-nachweis [data-ergebnis="abweichung"]')
    check('Abweichung: Maßnahme-Felder mit Vorschlag aus der Prüfung', pg.is_visible('#nw-km') and pg.input_value('#nw-km') == 'Durch den QMB' and pg.input_value('#nw-mzust') == 'QB'
          and pg.is_checked('#nw-massn') and pg.is_hidden('#nw-massn-hinweis'))
    pg.fill('#nw-bem', 'Fliegengitter beschädigt'); pg.fill('#nw-korr', 'Öffnung abgedeckt'); pg.click('#nw-form [type="submit"]'); pg.wait_for_selector('#dlg-nachweis', state='hidden')
    toast(pg, 'Maßnahme')
    pg.wait_for_selector(f'{bg} .qm-pm.abw')
    check('Nachweis gespeichert: Abweichung im Monat, nächste Fälligkeit in 6 Monaten (grün)', pg.locator(f'{bg} .qm-chip.gruen').count() == 1)
    pg.click(f'{bg} .qm-plan-titel'); pg.wait_for_selector('#dlg-pruefung[open]')
    check('Prüfung: Nachweis mit verknüpfter Maßnahme', pg.locator('#pr-nachweise tbody tr').count() == 1 and pg.locator('#pr-nachweise [data-massn-auf]').count() == 1)
    pg.screenshot(path=os.path.join(SH, 'qs_pruefung_1280.png'))
    pg.click('#pr-knoepfe [data-schliessen]')
    pg.click(f'{we} .qm-plan-titel'); pg.wait_for_selector('#dlg-pruefung[open] #pr-versaeumt .qm-chip.rot')
    check('Prüfung arbeitstäglich: versäumte Tage mit Datum, Quote', 'versäumt' in text(pg, '#pr-versaeumt') and 'erfüllt' in text(pg, '#pr-meta'))
    pg.click('#pr-knoepfe [data-schliessen]')
    pg.screenshot(path=os.path.join(SH, 'qs_pruefplan_1280.png'), full_page=True)
    # Prüfung zuweisen
    pg.click('#qm-p-liste .qm-plan-zeile:has-text("Systembewertung") .qm-plan-titel'); pg.wait_for_selector('#dlg-pruefung[open]')
    pg.click('#pr-knoepfe [data-pr="aendern"]'); pg.wait_for_selector('#dlg-pruefform[open]')
    pg.fill('#pf-ma-suche', 'bernd')
    check('Mitarbeiter suchen: Treffer', pg.locator('#pf-ausfuehrende input').count() == 1)
    pg.check('#pf-ausfuehrende input'); pg.fill('#pf-ma-suche', '')
    check('Auswahl bleibt beim Leeren der Suche', pg.locator('#pf-ausfuehrende input:checked').count() == 1 and pg.locator('#pf-ausfuehrende input').count() >= 8)
    pg.click('#pf-form [type="submit"]'); pg.wait_for_selector('#dlg-pruefform', state='hidden')
    pg.wait_for_selector('#pr-felder >> text=Bernd Bearbeiter')
    check('Zuweisung gespeichert: „Durchführung durch“ in der Prüfung', 'Bernd Bearbeiter' in text(pg, '#pr-felder'))
    pg.click('#pr-knoepfe [data-schliessen]')
    # Maßnahmen: Tafel, Liste, IFS-Maske, wirksam
    pg.click('#qm-tabs [data-tab="massnahmen"]')
    check('Maßnahmen-Tafel: vier Spalten, zwei Karten (aus Audit und aus Prüfung)', pg.locator('#qm-m-liste .qm-spalte').count() == 4 and pg.locator('#qm-m-liste .qm-mkarte').count() == 2
          and 'Öffnung abgedeckt' not in text(pg, '#qm-m-liste .qm-spalte[data-spalte="offen"]') and 'Fliegengitter' in text(pg, '#qm-m-liste .qm-spalte[data-spalte="offen"]')
          and 'Kalibrierung eines Thermometers nicht dokumentiert' in text(pg, '#qm-m-liste .qm-spalte[data-spalte="in_arbeit"]'), text(pg, '#qm-m-liste'))
    pg.screenshot(path=os.path.join(SH, 'qs_massnahmen_1280.png'), full_page=True)
    pg.click('[data-ansicht="liste"]')
    check('Liste: nicht abgeschlossene Maßnahmen', pg.locator('#qm-m-liste tr[data-massn]').count() == 2 and pg.is_visible('#qm-m-status'))
    pg.click('#qm-m-liste tr:has-text("2026-001")'); pg.wait_for_selector('#dlg-massnahme[open]')
    check('IFS-Maske: Anforderung, Bewertung, Korrektur, Ursache aus dem Paket', pg.input_value('#ms-anf') == '4.8.2' and pg.input_value('#ms-bewertung') == 'B'
          and pg.input_value('#ms-korr') == 'Thermometer sofort nachkalibriert' and pg.input_value('#ms-ursache') == 'Kalibrierintervall nicht festgelegt')
    pg.screenshot(path=os.path.join(SH, 'qs_massnahme_1280.png'))
    pg.select_option('#ms-status', 'wirksam')
    check('wirksam gewählt: Feld Wirksamkeitsprüfung erscheint', pg.is_visible('#ms-notiz'))
    pg.fill('#ms-notiz', 'Kalibrierprotokoll 2026 liegt vor'); pg.click('#ms-speichern'); pg.wait_for_selector('#dlg-massnahme', state='hidden')
    pg.wait_for_function("document.querySelectorAll('#qm-m-liste tr[data-massn]').length === 1")
    check('abgeschlossene Maßnahme fällt aus „nicht abgeschlossen“', 'Fliegengitter' in text(pg, '#qm-m-liste'))
    ctx.close()

    # Fritz: prüft und gibt den Entwurf von Quinn frei
    ctx, pg = anmelden('fritz', 'Freigabe-Konto-78', '198.51.100.13')
    pg.wait_for_selector('#qm-u-aufgaben .qm-aufgabe[data-dok]')
    check('Übersicht: Entwurf von Quinn zum Prüfen', 'Entwurf von Quinn QMB' in text(pg, '#qm-u-aufgaben') and 'Prüfen' in text(pg, '#qm-u-aufgaben'))
    pg.click('#qm-u-aufgaben .qm-aufgabe[data-dok]'); pg.wait_for_selector('#qm-dk [data-schritt="pruefen_freigeben"]')
    pg.click('#qm-dk [data-schritt="pruefen_freigeben"]'); toast(pg, 'Version 3 freigegeben')
    pg.wait_for_function("document.querySelector('#qm-dk .qm-chips').textContent.includes('Version 3 gültig')")   # Toast kommt vor dem Neuladen
    check('Seitenleiste aktualisiert: drei Versionen, Version 3 gültig, Ablauf beendet', pg.locator('#qm-dk .qm-version').count() == 3 and 'Version 3 gültig' in text(pg, '#qm-dk .qm-chips') and pg.locator('#qm-dk .qm-schritte').count() == 0)
    ctx.close()

    # Kai (nur „Kontrollen durchführen“, Kürzel QV): eigene Kontrolle am Handy
    ctx, pg = anmelden('kai', 'Kontroll-Konto-22', '198.51.100.16', 390, 'light', 844)
    pg.wait_for_selector('#qm-u-aufgaben .qm-aufgabe')
    check('Kai: Ihre Aufgaben mit der zugewiesenen Kontrolle, keine Anlegen-Knöpfe', 'Reinigungskontrolle Kühlhaus' in text(pg, '#qm-u-aufgaben')
          and all(pg.is_hidden(s) for s in ('#qm-d-neu', '#qm-h-neu', '#qm-p-neu', '#qm-m-neu', '#qm-tabs [data-tab="einstellungen"]')))
    pg.screenshot(path=os.path.join(SH, 'qs_kontrolle_390_light.png'), full_page=True)
    pg.click('#qm-tabs [data-tab="pruefplan"]')
    check('Kai: Nachweis-Knopf nur bei der eigenen Kontrolle', pg.locator('#qm-p-liste [data-nachweis]').count() == 1)
    pg.check('#qm-p-meine')
    check('„nur meine“: eine Prüfung', pg.locator('#qm-p-liste .qm-plan-zeile[data-pruefung]').count() == 1)
    pg.click('#qm-tabs [data-tab="uebersicht"]')
    pg.click('#qm-u-aufgaben .qm-aufgabe[data-nachweis]'); pg.wait_for_selector('#dlg-nachweis[open]')
    pg.click('#dlg-nachweis [data-ergebnis="abweichung"]')
    check('Kai: bei Abweichung keine Maßnahme anlegen (nur Hinweis)', pg.is_disabled('#nw-massn') and not pg.is_checked('#nw-massn') and pg.is_hidden('#nw-km')
          and pg.is_hidden('#nw-massn-l') and pg.is_visible('#nw-massn-hinweis'))
    pg.screenshot(path=os.path.join(SH, 'qs_nachweis_390_light.png'))
    pg.click('#dlg-nachweis [data-ergebnis="io"]'); pg.click('#nw-form [type="submit"]'); pg.wait_for_selector('#dlg-nachweis', state='hidden')
    toast(pg, 'Nachweis gespeichert')
    pg.wait_for_function("!document.querySelector('#qm-u-aufgaben').textContent.includes('Reinigungskontrolle')")
    check('erledigt: Kontrolle verschwindet aus „Ihre Aufgaben“', 'Reinigungskontrolle' not in text(pg, '#qm-u-aufgaben'))
    check('390px: kein waagerechtes Scrollen (Kai)', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
    ctx.close()

    # Vera: Einstellungen und Datenpaket
    ctx, pg = anmelden('vera', 'Verwalt-Konto-90', '198.51.100.14')
    pg.click('#qm-tabs [data-tab="einstellungen"]')
    check('Einstellungen: Kapitel und Personen als Eingabezeilen, Verknüpfung, Überprüfungsfrist', pg.locator('#qm-e-kapitel tr').count() == 4 and pg.locator('#qm-e-personen tr').count() == 4
          and pg.input_value('#qm-e-personen tr:first-child [data-f="mitarbeiter"]') == ids['quinn'] and pg.input_value('#qm-e-monate') == '36')
    pg.select_option('#qm-e-personen tr:nth-child(4) [data-f="mitarbeiter"]', ids['kai'])
    pg.click('#qm-e-person-form [type="submit"]'); pg.wait_for_selector('#qm-e-person-meldung:not(:empty)')
    check('ein Mitarbeiter mit zwei Kürzeln: Fehler', 'nur mit einem Kürzel' in text(pg, '#qm-e-person-meldung'), text(pg, '#qm-e-person-meldung'))
    pg.select_option('#qm-e-personen tr:nth-child(4) [data-f="mitarbeiter"]', ids['bernd'])
    pg.click('#qm-e-person-form [type="submit"]'); toast(pg, 'Personen gespeichert')
    check('Personen gespeichert: EK = Bernd', [p_['mitarbeiter'] for p_ in L.call('qs_start')[1]['personen'] if p_['id'] == 'EK'] == [ids['bernd']])
    pg.click('#qm-e-kapitel-plus')
    pg.fill('#qm-e-kapitel tr:last-child [data-f="id"]', '3.1'); pg.fill('#qm-e-kapitel tr:last-child [data-f="titel"]', 'Technik, Infrastruktur')
    pg.click('#qm-e-kapitel-form [type="submit"]'); toast(pg, 'Kapitel gespeichert')
    check('Kapitel hinzugefügt', pg.locator('#qm-e-kapitel tr').count() == 5)
    pg.fill('#qm-e-monate', '3'); pg.click('#qm-e-einst-form [type="submit"]'); pg.wait_for_selector('#qm-e-einst-meldung:not(:empty)')
    check('Überprüfungsfrist 3 Monate: Fehler', '6 bis 120' in text(pg, '#qm-e-einst-meldung'))
    pg.fill('#qm-e-monate', '36'); pg.click('#qm-e-einst-form [type="submit"]'); toast(pg, 'Einstellung gespeichert')
    pg.set_input_files('#qm-e-datei', PAKET_DATEI); pg.wait_for_selector('#qm-e-vorschau .qm-vorschau')
    check('Datenpaket: Vorschau mit Zahlen, „ersetzen“ angeboten (Modul nicht leer)', '9' in text(pg, '#qm-e-vorschau') and pg.is_visible('#qm-e-ersetzen') and pg.is_enabled('#qm-e-uebernehmen'))
    pg.screenshot(path=os.path.join(SH, 'qs_einstellungen_1280.png'), full_page=True)
    pg.click('#qm-e-uebernehmen'); pg.wait_for_selector('#qm-e-meldung:not(:empty)')
    check('ohne „ersetzen“: Hinweis, nichts übernommen', 'ersetzen' in text(pg, '#qm-e-meldung'))
    ctx.close()

    # Nur ansehen: Handy und dunkel
    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden('lisa', 'Leserin-Konto-12', '198.51.100.10', breite, thema, 844 if breite < 500 else 900)
        pg.wait_for_selector('#qm-u-kpis .qm-kpi')
        check(f'{breite}px {thema}: nur ansehen (keine Anlegen-Knöpfe, keine Einstellungen, keine Nachweis-Knöpfe)', all(pg.is_hidden(s) for s in ('#qm-d-neu', '#qm-h-neu', '#qm-p-neu', '#qm-m-neu', '#qm-tabs [data-tab="einstellungen"]'))
              and pg.locator('[data-nachweis]').count() == 0)
        breit = []
        for tab in ('uebersicht', 'dokumente', 'handbuch', 'pruefplan', 'massnahmen'):
            pg.click(f'#qm-tabs [data-tab="{tab}"]')
            if not pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'):
                breit.append(tab)
            if breite == 390 or tab in ('uebersicht', 'pruefplan'):
                pg.screenshot(path=os.path.join(SH, f'qs_{tab}_{breite}_{thema}.png'), full_page=True)
        check(f'{breite}px {thema}: kein waagerechtes Scrollen', not breit, breit)
        pg.click('#qm-tabs [data-tab="dokumente"]'); pg.click(f'#qm-d-liste tr[data-dok="{l02["id"]}"]'); pg.wait_for_selector('#qm-dk:not([hidden]) h2')
        check(f'{breite}px {thema}: Dokument ohne Ablauf-Knöpfe, Seitenleiste passt in die Breite', pg.locator('#qm-dk [data-schritt]').count() == 0
              and pg.evaluate("(() => { const d = document.querySelector('#qm-dk'); const r = d.getBoundingClientRect(); return d.scrollWidth <= d.clientWidth + 1 && r.right <= window.innerWidth + 1; })()"))
        if breite == 390:
            pg.screenshot(path=os.path.join(SH, f'qs_dokument_{breite}_{thema}.png'))
        pg.click('#qm-dk [data-dk="schliessen"]'); pg.wait_for_selector('#qm-dk', state='hidden')
        if thema == 'dark':
            check(f'{breite}px: dunkler Grund', pg.evaluate('getComputedStyle(document.body).backgroundColor') == 'rgb(18, 16, 17)')
        ctx.close()

    ctx, pg = anmelden('otto', 'Ohne-Konto-11', '198.51.100.15', ziel='#qm-err:not([hidden])')
    check('ohne QM-Recht: Hinweis statt Inhalt', 'Berechtigung' in text(pg, '#qm-err') and pg.is_hidden('#qm-app'))
    ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

print(f'{sum(res)}/{len(res)} passed')
