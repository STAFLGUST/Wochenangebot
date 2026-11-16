"""QM-System – Ordner-Import (qs_sammel_plan, qs_import_eintragen, module/qs/ablage.php) und Ordnerbaum (qs_archiv, qs_archiv_zip).

Geprüft: Regeln nur auf dem Server – ganze Fallliste aus beiden Reviews als Tabelle (Nummer nur im Kapitelordner, der genau wie das
Kapitel heißt, mit leerem Rest oder Titel, oder im Ordner exakt „Nr Titel“ nur mit Dokumentenliste.csv ganz oben; andere Ordner mit
Kapitelnummer nur Archiv mit ihrem Namen im pfad; nie unter „_…“/„alt…“, nie in fremden obersten Ordnern, nie per Nummer eines
Bereichs; ein offener Entwurf geht der gültigen Version vor; Archiv je Kapitel und Unterordner der ersten Ebene mit pfad, „Weitere
Dateien“, Systemdateien, Dateiart, leer); Wurzel: ohne Antwort startet nichts, wenn darin Kapitelordner stehen (Matthies kommt nie zu
Standard-Fleisch), heißt sie wie ein Bereich, gilt dieser; Zuordnung der obersten Ordner (Wahl des Nutzers gilt immer, Eingang, nicht
übernehmen, Kapitel, neuer Bereich nur mit „verwalten“ und Nummer 90–99); Freigaben je oberstem Ordner (Nachtragen Vorgabe aus,
Entwürfe Vorgabe an, einzelne Dateien abwählbar); Anlegen von Bereichen und Ordner-Dokumenten ohne zweiten Plan; gebündeltes Eintragen
mit Ziel vom Server (Status inzwischen anders → Eingang, Häkchen fehlt → Eingang, fremder Upload, gleiche Datei, früher im Eingang
gelöscht nur für den Eingang, gesperrtes Ziel, gültige Version nur mit „freigeben“, 4-Augen-Prinzip, ein Verlaufseintrag); Abbruch
beim Schreiben (keine gültige Version ohne Datei, keine verwaisten Dateien); Fortsetzen; Grenzen; ältere Dateien am Ordner (GR-006);
Ordnerbaum und ZIP; Rechte; Protokoll mit Anzahl. Oberfläche: Wurzel-Frage, Zuordnung, Freigaben je Ordner mit gruppierten Nummern,
Hinweis auf den Bearbeiter, Fortschritt, Bericht als CSV, Fortsetzen, Abbruch, Ordnerbaum (aufklappen, Suche, ZIP), 1280/390 px hell und
dunkel, keine JavaScript-Fehler. Nur erfundene Testdaten.
"""
import csv
import glob
import io
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import SH, datenordner, storage_sqlite, storage_write
from qs_hilfe import (ABLAGE, check, ende, pdf, docx_w, blob_pfad, blobs, speicher, hochladen, roh, nutzer, fuellen, leeren, neu_zaehlen, anmelden,
                      text, ohne_scrollen)

NEU = 'neu'   # Ziel: neues Ordner-Dokument (Kapitel und Titel im zweiten und dritten Feld)
SF = {'name': 'QM-System', 'art': 'sf'}   # Antwort auf die Wurzel-Frage: der gewählte Ordner gehört zu Standard-Fleisch


def plan(cli, pfade, angaben=None, anlegen=False):
    """Plan für Pfade („Ordner/…/Datei“ oder (Pfad, Größe)); Rückgabe (Status, Antwort, {Pfad: Eintrag})"""
    je = {}
    for p in pfade:
        p, g = p if isinstance(p, tuple) else (p, 1000)
        o, _, n = p.rpartition('/')
        je.setdefault(o, []).append((n, g, p))
    st, r = cli.call('qs_sammel_plan', {'ordner': [[o, [[n, g] for n, g, _ in l]] for o, l in je.items()], **(angaben or {}), 'anlegen': anlegen})
    flach = [p for l in je.values() for _, _, p in l]
    return st, r, ({p: e for p, e in zip(flach, r['dateien'])} if st == 200 else {})


def sammeln(cli, pfad, inhalt):
    """Upload für den Ordner-Import: nur Name und Herkunft (Ordnerpfad wie gewählt) – Rückgabe der fertige Upload (noch nicht eingetragen)"""
    o, _, n = pfad.rpartition('/')
    st, r = hochladen(cli, '', '', n, inhalt, {'sammeln': True, 'herkunft': o})
    assert st == 200 and r.get('upload'), r
    return r['upload']


def eintragen(cli, ups, angaben=None, **extra):
    """ups: [(Upload, Plan-Eintrag)] – erwarteter Status und Version wie im Plan"""
    return cli.call('qs_import_eintragen', {**(angaben or {}), **extra, 'uploads': [{'upload': u, 'status': e['status'], 'ver': e.get('ver', ''), 'ohne': bool(e.get('ohne'))}
                                                                                  for u, e in ups]})


def dok(did):
    return {x['id']: x for x in L.call('qs_start')[1]['dokumente']}[did]


def dok_titel(titel, kap):
    return next((x for x in L.call('qs_start')[1]['dokumente'] if x['titel'] == titel and x['kapitel'] == kap), None)


def archiv(did, cli=None):
    return (cli or L).call(f'qs_archiv&dok={did}')[1].get('dateien', [])


def eingang():
    return {f['id']: f for f in Be.call('qs_eingang')[1].get('dateien', [])}


def benutzt():
    """Kennungen, auf die qs-dokumente (auch Rohfassungen) und qs-ablage zeigen"""
    ids = {f['id'] for f in speicher('qs-ablage').get('liste', [])}
    for x in speicher('qs-dokumente')['liste']:
        for f in x.get('dateien', []) + [f for v in x.get('versionen', []) for f in v.get('dateien', [])]:
            ids |= {f['id']} | ({f['roh']} if f.get('roh') else set())
    return ids


NUTZER = (('lisa', 'Lisa Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['qs.sehen']}),
          ('bernd', 'Bernd Bearbeiter', 'editor', 'Bearbeit-Konto-34', {'grant': ['qs.bearbeiten']}),
          ('quinn', 'Quinn QMB', 'editor', 'Freigabe-Konto-56', {'grant': ['qs.freigeben']}),
          ('vera', 'Vera Verwalten', 'editor', 'Verwalt-Konto-90', {'grant': ['qs.verwalten', 'qs.freigeben']}))
A, K, ids = nutzer(NUTZER)
L, Be, Q, V = K['lisa'], K['bernd'], K['quinn'], K['vera']
KAP = [{'id': '1.4', 'titel': 'Qualitätssicherung'}, {'id': '2.2', 'titel': 'Lager'}, {'id': '2.4', 'titel': 'Versand'}]
check('Kapitel', V.call('qs_stamm_save', {'kapitel': KAP})[0] == 200)
st, r, _ = plan(V, ['_Matthies Fleischwaren/a.pdf', 'X/b.pdf'], {'wahl': {'_Matthies Fleischwaren': {'art': 'neu', 'kapitel': '90', 'titel': 'Matthies Fleischwaren'}}}, anlegen=True)
check('Bereich 90 „Matthies Fleischwaren“ angelegt (zweite Firma)', st == 200 and any(k['id'] == '90' and k.get('bereich') for k in speicher('qs-stamm')['kapitel']), r)


def gelenkt(kap, art, nr, titel, gueltig=True):
    r = Be.call('qs_dokument_save', {'kapitel': kap, 'art': art, 'nr': '', 'titel': titel})[1]['dokument']
    if nr:   # Nummer wie aus einem Datenpaket (ohne erzwungene Struktur)
        d_ = speicher('qs-dokumente'); next(x for x in d_['liste'] if x['id'] == r['id'])['nr'] = nr; storage_write('qs-dokumente', d_)
    if gueltig:
        hochladen(Be, r['id'], r['versionen'][0]['id'], 'Erstfassung.pdf', pdf(titel))
        assert Be.call('qs_version_schritt', {'dokument': r['id'], 'rev': dok(r['id'])['rev'], 'schritt': 'einreichen'})[0] == 200
        assert Q.call('qs_version_schritt', {'dokument': r['id'], 'rev': dok(r['id'])['rev'], 'schritt': 'pruefen_freigeben'})[0] == 200
    return dok(r['id'])


D1 = gelenkt('1.4', 'F', '1.4-F01', 'Temperaturkontrolle')
D2 = gelenkt('2.2', 'F', '2.2-F03', 'Wareneingang')
D3 = gelenkt('2.2', 'A', '2.2.1.1-A01', 'Reinigung Kühlhaus')
D4 = gelenkt('1.4', 'L', 'HACCP-Plan', 'HACCP-Plan')
D5 = gelenkt('1.4', 'F', '', 'Probenahme', gueltig=False)   # nur Entwurf (1.4-F02)
D6 = gelenkt('1.4', 'F', '1.4-F03', 'Reinigung')   # gültig und dazu ein offener Entwurf
check('Überarbeitung von 1.4-F03 begonnen (offener Entwurf neben der gültigen Version)', Be.call('qs_version_save', {'dokument': D6['id'], 'aenderungen': 'neu', 'grund': 'Test'})[0] == 200)
D6 = dok(D6['id'])
D8 = gelenkt('1.4', 'F', '1.4-F05', 'Kalibrierung')
M1 = gelenkt('90', 'F', '1.4-F07', 'Temperatur Matthies')   # Bereich der zweiten Firma: Nummern aus deren Datenpaket
M2 = gelenkt('90', 'F', '1.4-F5', 'Kalibrierung Matthies')
O1 = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'O', 'nr': '', 'titel': 'Reinigungsnachweise'})[1]['dokument']['id']
check('gelenkte Dokumente mit gültiger Version, Entwurf, Ordner', D1['nr'] == '1.4-F01' and D5['nr'] == '1.4-F02' and D3['nr'] == '2.2.1.1-A01' and O1)
DOK = {D1['id']: 'd1', D2['id']: 'd2', D3['id']: 'd3', D4['id']: 'd4', D5['id']: 'd5', D6['id']: 'd6', D8['id']: 'd8', M1['id']: 'm1', M2['id']: 'm2', O1: 'o1'}

# ── Regeln: ganze Fallliste aus beiden Reviews (Erwartung: Status, Ziel, pfad) – Wurzel „QM-System“ als Standard-Fleisch bestätigt,
#    Nachtragen für „1.4 Qualitätssicherung“, „1.4 qualitätssicherung“, „1.4“ und „2.2 Lager“ freigegeben ──
G = 'QM-System/1.4 Qualitätssicherung'
FAELLE = [
    ('QM-System/_Firma/HACCP/1.4 QS/1.4-F01.xlsx', 'eingang', 'eingang', '_Firma/HACCP/1.4 QS'),
    (G + '/Checkliste/1.4-F01_2023.pdf', 'ablage', (NEU, '1.4', 'Checkliste'), ''),
    ('QM-System/2.4 Lager/2.2-F03_Kunde.pdf', 'ablage', (NEU, '2.4', 'Weitere Dateien'), '2.4 Lager'),   # Nummer, aber nicht genau das Kapitel
    (G + '/_alt/1.4-F01.doc', 'ablage', (NEU, '1.4', '_alt'), ''),
    ('QM-System/2.2 Lager/2.2.1.1-A01.docx', 'nachtragen', 'd3', None),
    ('QM-System/2.2 Lager/2.2.1.1.5-A01.docx', 'ablage', (NEU, '2.2', 'Weitere Dateien'), ''),
    (G + '/1.4-f01.pdf', 'nachtragen', 'd1', None),
    ('QM-System/1.4 qualitätssicherung/1.4-F1.pdf', 'nachtragen', 'd1', None),
    ('QM-System/1.4/1.4-F01 Temperaturkontrolle.docx', 'nachtragen', 'd1', None),
    ('QM-System/Handbuch/1.4 QS/1.4-F01.pdf', 'eingang', 'eingang', 'Handbuch/1.4 QS'),
    (G + '/1.4-F01_2023.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    (G + '/1.4-F01 alt.doc', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    (G + '/Kopie von 1.4-F01.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    (G + '/1.4-F01 ausgefüllt KW12 2023.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    (G + '/1.4-F01 Temperaturkontrolle/KW01-2023.pdf', 'ablage', (NEU, '1.4', '1.4-F01 Temperaturkontrolle'), ''),   # „Nr Titel“ nur im eigenen Export
    (G + '/1.4-F01 Temperaturkontrolle/Januar 2019.xlsx', 'ablage', (NEU, '1.4', '1.4-F01 Temperaturkontrolle'), ''),
    (G + '/1.4-F02 Probenahme/Probe KW1 2022.pdf', 'ablage', (NEU, '1.4', '1.4-F02 Probenahme'), ''),   # Aufzeichnungen nie in den Entwurf
    (G + '/1.4-F01 Aufzeichnungen 2019-2023/Januar.pdf', 'ablage', (NEU, '1.4', '1.4-F01 Aufzeichnungen 2019-2023'), ''),
    (G + '/1.4-F01 Firma B/1.4-F01.xlsx', 'ablage', (NEU, '1.4', '1.4-F01 Firma B'), ''),
    (G + '/1.4-F01 alt/1.4-F01.doc', 'ablage', (NEU, '1.4', '1.4-F01 alt'), ''),
    (G + '/1.4-F01 Archiv/1.4-F01 v3.doc', 'ablage', (NEU, '1.4', '1.4-F01 Archiv'), ''),
    (G + '/HACCP-Plan 2019.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    (G + '/HACCP-Plan/2019.pdf', 'ablage', (NEU, '1.4', 'HACCP-Plan'), ''),
    (G + '/Alt/1.4-F01.doc', 'ablage', (NEU, '1.4', 'Alt'), ''),
    (G + '/alte Stände/1.4-F01.doc', 'ablage', (NEU, '1.4', 'alte Stände'), ''),
    (G + '/Archiv/1.4-F01.doc', 'ablage', (NEU, '1.4', 'Archiv'), ''),
    (G + '/1.4-F01.pdf', 'nachtragen', 'd1', None),
    (G + '/1.4-F01.doc', 'nachtragen', 'd1', None),   # mehrere Dateien zu einer Nummer: jede einzeln abwählbar
    (G + '/1.4-F01.docx', 'nachtragen', 'd1', None),
    ('QM-System/Firma B/1.4 QS/1.4-F01.xlsx', 'eingang', 'eingang', 'Firma B/1.4 QS'),
    (G + '/Reinigungsnachweise/2023/KW1.pdf', 'ablage', 'o1', '2023'),
    (G + '/reinigungsnachweise/2024/KW1.pdf', 'ablage', 'o1', '2024'),   # Titel normalisiert: vorhandener Ordner
    (G + '/Firma B Reinigungsnachweise/KW1.pdf', 'ablage', (NEU, '1.4', 'Firma B Reinigungsnachweise'), ''),
    ('QM-System/_Firma B/Reinigungsnachweise/KW1.pdf', 'eingang', 'eingang', '_Firma B/Reinigungsnachweise'),
    (G + '/~$1.4-F01.docx', 'system', None, None),
    (G + '/.~lock.1.4-F01.docx#', 'system', None, None),
    (G + '/1.4-F01 (1).pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    (G + '/1.4-F01 - Kopie.docx', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    (G + '/1.4-F01_ALT.docx', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    (G + '/1.4-F01 Entwurf.docx', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    (G + '/1.4-F01.pdf.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    (G + '/1.4–F01.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),   # Gedankenstrich ist kein Trenner der Nummer
    (G + '/1.4-F01 Temperaturkontrolle.pdf', 'nachtragen', 'd1', None),
    (G + '/1.4-F01_Temperaturkontrolle.docx', 'nachtragen', 'd1', None),
    (G + '/1.4-F01 temperaturkontrolle.pdf', 'nachtragen', 'd1', None),
    (G + '/1.4 - F 01.pdf', 'nachtragen', 'd1', None),
    (G + '/1.4-F001.pdf', 'nachtragen', 'd1', None),
    (G + '/1.4-F01-Temperatur-Kontrolle.xlsx', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),
    (G + '/HACCP-Plan.pdf', 'nachtragen', 'd4', None),
    (G + '/1.4-F02 Probenahme.pdf', 'dokument', 'd5', None),
    (G + '/1.4-F03.pdf', 'dokument', 'd6', None),   # offener Entwurf geht der gültigen Version vor
    (G + '/1.4-F07.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), ''),   # Nummer eines Dokuments im Bereich: nie per Nummer
    (G + '/1.4-F5.pdf', 'nachtragen', 'd8', None),   # gleiche Nummer im Bereich zählt nicht
    (G + '/1.4-F01 Temperaturkontrolle/_ältere Versionen/Version 1/a.pdf', 'ablage', (NEU, '1.4', '1.4-F01 Temperaturkontrolle'), '_ältere Versionen/Version 1'),
    (G + '/1.4-F01 Temperaturkontrolle/Messungen/a.pdf', 'ablage', (NEU, '1.4', '1.4-F01 Temperaturkontrolle'), 'Messungen'),
    (G + '/Befunde/2023/Labor A/Teil 1/Teil 2/tief.pdf', 'ablage', (NEU, '1.4', 'Befunde'), '2023/Labor A/Teil 1/Teil 2'),
    ('QM-System/1.4 QS alt/1.4-F01.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), '1.4 QS alt'),   # alte Kopie des Kapitelordners
    ('QM-System/1.4 QS - Kopie/1.4-F01.docx', 'ablage', (NEU, '1.4', 'Weitere Dateien'), '1.4 QS - Kopie'),
    ('QM-System/1.4 Stand 2019/1.4-F01 Temperaturkontrolle.pdf', 'ablage', (NEU, '1.4', 'Weitere Dateien'), '1.4 Stand 2019'),
    ('QM-System/1.4 Stand 2019/Reinigung/KW1.pdf', 'ablage', (NEU, '1.4', 'Reinigung'), '1.4 Stand 2019'),
    ('QM-System/90 Matthies/1.4 QS/1.4-F01.pdf', 'eingang', 'eingang', '90 Matthies/1.4 QS'),   # Nummer eines Bereichs: nie erkannt
    ('QM-System/ 1.4 QS/1.4-F01.pdf', 'eingang', 'eingang', '1.4 QS'),
    ('QM-System/Zertifikat.pdf', 'eingang', 'eingang', ''),
    ('QM-System/Hinweise.txt', 'export', None, None),
    (G + '/setup.exe', 'art', None, None),
    ((G + '/leer.pdf', 0), 'leer', None, None),
]
FREI = {'freigaben': {n: {'nachtragen': True} for n in ('1.4 Qualitätssicherung', '1.4 qualitätssicherung', '1.4', '2.2 Lager')}}
st, r, pl = plan(Q, [f[0] for f in FAELLE], {'wurzel': SF, **FREI})
check('Plan: 200, Wurzel „QM-System“ bestätigt und weggelassen, kein eigener Export', st == 200 and r['wurzel']['name'] == 'QM-System' and r['wurzel']['weg']
      and r['wurzel']['frage'] and not r['offen'] and not r['export'], (st, r.get('error'), r.get('wurzel')))


def ist(e, neu):
    z = e.get('ziel')
    ziel = (NEU, neu[e['neu']]['kapitel'], neu[e['neu']]['titel']) if 'neu' in e else (DOK.get(z) or z) if z else None
    return e.get('status'), ziel, e.get('pfad') if e.get('status') in ('ablage', 'eingang') else None


for pfad_, status_, ziel_, p_ in FAELLE:
    schluessel = pfad_[0] if isinstance(pfad_, tuple) else pfad_
    erw = (status_, ziel_, p_)
    check(f'Regel: {schluessel} → {status_} {ziel_ or ""}', ist(pl.get(schluessel, {}), r.get('neu', [])) == erw, (ist(pl.get(schluessel, {}), r.get('neu', [])), erw, pl.get(schluessel)))
check('Plan: Gründe für Eingang und Art', pl['QM-System/Zertifikat.pdf'].get('grund') == 'lose Datei' and pl[G + '/setup.exe'].get('grund') == '.exe')
check('Plan: Kandidaten mit Dokument (gruppierbar), mehrere Dateien zu einer Nummer', all(pl[G + n].get('kandidat') == 'nachtragen' and pl[G + n].get('dok') == D1['id']
      for n in ('/1.4-F01.pdf', '/1.4-F01.doc', '/1.4-F01.docx')) and pl[G + '/1.4-F02 Probenahme.pdf'].get('kandidat') == 'dokument')
ob = {z['name']: z for z in r['oberste']}
check('oberste Ordner: Kapitelordner „genau“, Ordner mit Nummer nur als Vorschlag (Archiv, Name im pfad), andere Eingang mit Vorschlag für einen Bereich (nächste freie Nummer)',
      ob['1.4 Qualitätssicherung']['art'] == 'genau' and ob['1.4']['art'] == 'genau' and ob['1.4 QS alt']['art'] == 'kapitel' and ob['1.4 QS alt']['imPfad']
      and ob['1.4 QS alt']['erkannt'] == '1.4' and ob['_Firma']['art'] == 'eingang' and ob['_Firma']['bereichVorschlag'] == {'kapitel': '91', 'titel': 'Firma'}
      and ob['90 Matthies']['art'] == 'eingang' and not ob['90 Matthies']['erkannt'], ob)

# ── Wurzel: ohne Antwort startet nichts; Matthies kommt nie zu den Nummern von Standard-Fleisch (Review 2, HOCH 1) ──
st, r2, pl2 = plan(Q, [f[0] for f in FAELLE[:10]])
check('ohne Antwort: Plan offen, Kapitelordner „offen“, nichts in eine Version', st == 200 and r2['offen'] and r2['wurzel']['frage'] and pl2[G + '/1.4-f01.pdf']['status'] == 'offen'
      and not any(e.get('kandidat') or e['status'] in ('nachtragen', 'dokument') for e in pl2.values()), r2.get('wurzel'))
check('ohne Antwort: anlegen und starten abgelehnt (422)', plan(V, [f[0] for f in FAELLE[:10]], anlegen=True)[0] == 422)
MW = ['Matthies Werk/1.4 QS/1.4-F01.pdf', 'Matthies Werk/1.4 QS/1.4-F02 Probenahme.docx', 'Matthies Werk/1.4 Qualitätssicherung/1.4-F01.pdf']
st, r2, pl2 = plan(Q, MW, {'freigaben': {'1.4 Qualitätssicherung': {'nachtragen': True}}})
check('Ordner der Fremdfirma gewählt, ohne Bestätigung: alles offen, nie in Standard-Fleisch-Dokumente', r2['offen'] and all(e['status'] == 'offen' for e in pl2.values()), pl2)
st, r2, pl2 = plan(Q, MW, {'wurzel': {'name': 'Matthies Werk', 'art': 'kapitel', 'kapitel': '90'}})
n2 = r2.get('neu', [])
check('Bestätigt als Bereich 90: alles ins Archiv des Bereichs, Ordnername im pfad, nie per Nummer', not r2['offen'] and not r2['wurzel']['weg']
      and all(e['status'] == 'ablage' and n2[e['neu']]['kapitel'] == '90' and e['pfad'] == 'Matthies Werk' for e in pl2.values()), pl2)
st, r2, pl2 = plan(Q, ['Matthies Fleischwaren/1.4 QS/1.4-F01.pdf', 'Matthies Fleischwaren/1.4 QS/Reinigung/KW1.pdf'])
n2 = r2.get('neu', [])
check('Wurzel heißt wie ein Bereich: gilt automatisch, ohne Frage (Ordner je Unterordner, Name nicht doppelt)', not r2['wurzel']['frage'] and not r2['offen']
      and [ist(e, n2) for e in pl2.values()] == [('ablage', (NEU, '90', '1.4 QS'), ''), ('ablage', (NEU, '90', '1.4 QS'), 'Reinigung')], pl2)
st, r2, pl2 = plan(Q, ['_Firma/HACCP/1.4 QS/1.4-F01.xlsx', '_Firma/x.pdf'])
check('gewählter „_“-Ordner bleibt oberster Ordner (nie per Nummer, keine Frage)', not r2['wurzel']['weg'] and not r2['wurzel']['frage'] and pl2['_Firma/HACCP/1.4 QS/1.4-F01.xlsx']['status'] == 'eingang')
st, r2, _ = plan(Q, ['1.4 Qualitätssicherung/a.pdf', '1.4 Qualitätssicherung/b.pdf'])
check('Kapitelordner selbst gewählt: bleibt erhalten, keine Frage', not r2['wurzel']['weg'] and not r2['wurzel']['frage'] and r2['oberste'][0]['art'] == 'genau')

# ── Freigaben je oberstem Ordner, einzelne Dateien, eigener Export (Review 2, HOCH 2) ──
F1 = [G + '/1.4-F01.pdf', G + '/1.4-F01.doc', G + '/1.4-F02 Probenahme.pdf', 'QM-System/1.4/1.4-F01.docx']
st, r2, pl2 = plan(Q, F1, {'wurzel': SF})
check('Nachtragen: Vorgabe aus → Eingang (Grund „ohne Häkchen“), Kandidat bleibt sichtbar; Entwurf: Vorgabe an', pl2[G + '/1.4-F01.pdf']['status'] == 'eingang'
      and pl2[G + '/1.4-F01.pdf']['grund'] == 'ohne Häkchen' and pl2[G + '/1.4-F01.pdf']['kandidat'] == 'nachtragen' and pl2[G + '/1.4-F02 Probenahme.pdf']['status'] == 'dokument'
      and all(z['nachtragen'] is False and z['entwurf'] is True for z in r2['oberste']), pl2)
st, r2, pl2 = plan(Q, F1, {'wurzel': SF, 'freigaben': {'1.4 Qualitätssicherung': {'nachtragen': True, 'entwurf': False}}})
check('Häkchen je oberstem Ordner: nur dieser Ordner trägt nach, Entwurf abgewählt → Eingang', pl2[G + '/1.4-F01.pdf']['status'] == 'nachtragen'
      and pl2['QM-System/1.4/1.4-F01.docx']['status'] == 'eingang' and pl2[G + '/1.4-F02 Probenahme.pdf']['status'] == 'eingang', pl2)
st, r2, pl2 = plan(Q, F1, {'wurzel': SF, **FREI, 'ohne': [G + '/1.4-F01.doc']})
n2 = r2.get('neu', [])
check('einzelne Datei abgewählt: ins Archiv („Weitere Dateien“), die andere zur gleichen Nummer bleibt', ist(pl2[G + '/1.4-F01.doc'], n2) == ('ablage', (NEU, '1.4', 'Weitere Dateien'), '')
      and pl2[G + '/1.4-F01.doc'].get('kandidat') == 'nachtragen' and pl2[G + '/1.4-F01.pdf']['status'] == 'nachtragen', pl2)
st, r2, pl2 = plan(Q, F1 + [G + '/x.pdf'], {'wurzel': SF, 'wahl': {'1.4 Qualitätssicherung': {'art': 'eingang'}}})
check('ausdrückliche Wahl gilt auch für einen erkannten Kapitelordner', pl2[G + '/1.4-F01.pdf']['status'] == 'eingang' and 'kandidat' not in pl2[G + '/1.4-F01.pdf'], pl2)
st, r2, pl2 = plan(Q, ['QM-System/1.4 QS alt/1.4-F01.pdf', G + '/x.pdf'], {'wurzel': SF, 'wahl': {'1.4 QS alt': {'art': 'genau'}}, 'freigaben': {'1.4 QS alt': {'nachtragen': True}}})
check('Vorschlag ausdrücklich als „dieses Kapitel“ bestätigt: dann Nummern', pl2['QM-System/1.4 QS alt/1.4-F01.pdf']['status'] == 'nachtragen', pl2)
check('„dieses Kapitel“ ohne Kapitelnummer im Namen → 422', plan(Q, ['QM-System/Handbuch/a.pdf', G + '/x.pdf'], {'wurzel': SF, 'wahl': {'Handbuch': {'art': 'genau'}}})[0] == 422)
EXP = [G + '/1.4-F01 Temperaturkontrolle/KW01-2023.pdf', G + '/1.4-F01 Temperaturkontrolle/_ältere Versionen/Version 1/a.pdf', G + '/1.4-F02 Probenahme/x.pdf']
st, r2, pl2 = plan(Q, EXP + ['QM-System/Dokumentenliste.csv'], {'wurzel': SF, **FREI})
check('eigener ZIP-Export (Dokumentenliste.csv ganz oben): Ordner „Nr Titel“ ordnet zu, ältere Versionen übersprungen', r2['export']
      and pl2[EXP[0]]['status'] == 'nachtragen' and pl2[EXP[1]]['status'] == 'export' and pl2[EXP[2]]['status'] == 'dokument'
      and pl2['QM-System/Dokumentenliste.csv']['status'] == 'export', pl2)
st, r2, pl2 = plan(Q, EXP + [G + '/Dokumentenliste.csv'], {'wurzel': SF, **FREI})
check('Dokumentenliste.csv nicht ganz oben: kein Export, Unterordner ins Archiv', not r2['export'] and all(pl2[p]['status'] == 'ablage' for p in EXP), pl2)
st, r2, pl2 = plan(Be, [G + '/1.4-F01.pdf', G + '/1.4-F02 Probenahme.pdf'], {'wurzel': SF, **FREI})
check('ohne Freigaberecht: gültige Version → Eingang mit Grund, Entwurf möglich', pl2[G + '/1.4-F01.pdf']['grund'] == 'gültige Version nur mit Freigaberecht'
      and pl2[G + '/1.4-F02 Probenahme.pdf']['status'] == 'dokument', pl2)

# ── Zuordnung oberster Ordner, Bereich ──
W = {'_Firma': {'art': 'neu', 'kapitel': '91', 'titel': 'Firma'}, 'Handbuch': {'art': 'kapitel', 'kapitel': '1.4'}, 'Firma B': {'art': 'aus'}}
PF = [f[0] for f in FAELLE[:10]] + ['QM-System/Firma B/1.4 QS/1.4-F01.xlsx', 'QM-System/_Firma/1.4-F01.pdf']
check('neuer Bereich nur mit „verwalten“ (403)', plan(Q, PF, {'wurzel': SF, 'wahl': W})[0] == 403)
st, r, pl = plan(V, PF, {'wurzel': SF, 'wahl': W})
n_ = r.get('neu', [])
e1, e2, e3, e4 = (pl[p] for p in ('QM-System/_Firma/HACCP/1.4 QS/1.4-F01.xlsx', 'QM-System/Handbuch/1.4 QS/1.4-F01.pdf', 'QM-System/Firma B/1.4 QS/1.4-F01.xlsx', 'QM-System/_Firma/1.4-F01.pdf'))
check('Bereich: Ordner-Dokument je Unterordner, nie per Nummer; direkt darin „Weitere Dateien“', st == 200 and r['bereiche'] == {'91': 'Firma'}
      and ist(e1, n_) == ('ablage', (NEU, '91', 'HACCP'), '1.4 QS') and ist(e4, n_) == ('ablage', (NEU, '91', 'Weitere Dateien'), ''), (r.get('error'), e1, e4))
check('von Hand einem Kapitel zugeordnet: Archiv mit dem Ordnernamen, nie per Nummer', ist(e2, n_) == ('ablage', (NEU, '1.4', '1.4 QS'), 'Handbuch'), e2)
check('„nicht übernehmen“', e3 == {'status': 'aus', 'oben': e3.get('oben')}, e3)
for fall, wahl_, code in (('Nummer schon vergeben', {'art': 'neu', 'kapitel': '90', 'titel': 'Andere'}, 422), ('unbekanntes Kapitel', {'art': 'kapitel', 'kapitel': '7.7'}, 422),
                          ('Bereich unter 90', {'art': 'neu', 'kapitel': '3', 'titel': 'X'}, 422), ('Bereich 89', {'art': 'neu', 'kapitel': '89', 'titel': 'X'}, 422),
                          ('Bereich 100', {'art': 'neu', 'kapitel': '100', 'titel': 'X'}, 422), ('ohne Titel', {'art': 'neu', 'kapitel': '95', 'titel': ''}, 422)):
    check(f'Zuordnung abgelehnt – {fall}: {code}', plan(V, ['_Firma/a.pdf', 'X/b.pdf'], {'wahl': {'_Firma': wahl_}})[0] == code)
check('gleicher neuer Bereich ein zweites Mal (schon angelegt): wird wiederverwendet', plan(V, ['_M/a.pdf', 'X/b.pdf'], {'wahl': {'_M': {'art': 'neu', 'kapitel': '90', 'titel': 'Matthies Fleischwaren'}}})[0] == 200)
abl_rev = speicher('qs-dokumente')['rev']
st, r, pl = plan(V, PF, {'wurzel': SF, 'wahl': W}, anlegen=True)
stamm = speicher('qs-stamm')['kapitel']
haccp = dok_titel('HACCP', '91')
check('anlegen: Bereich 91, Ordner-Dokumente in einem Schreibvorgang, Plan mit ihren Kennungen (nicht neu gerechnet)', st == 200 and any(k['id'] == '91' and k.get('bereich') for k in stamm)
      and haccp and pl['QM-System/_Firma/HACCP/1.4 QS/1.4-F01.xlsx']['ziel'] == haccp['id'] and not any('neu' in e for e in r['dateien']) and not r['neu'] and not r['bereiche']
      and speicher('qs-dokumente')['rev'] == abl_rev + 1, (st, r.get('error')))
check('angelegte Ordner im Verlauf „angelegt (Ordner-Import)“', 'angelegt (Ordner-Import)' in json.dumps(haccp['verlauf'], ensure_ascii=False))
st, r, pl = plan(Q, ['_Firma/HACCP/1.4 QS/1.4-F01.xlsx', 'Y/a.pdf'], {'wahl': {'_Firma': {'art': 'kapitel', 'kapitel': '91'}}})
st, r2, pl2 = plan(Q, ['91 Firma/1.4-F01.pdf', 'Y/a.pdf'])
e_ = pl2.get('91 Firma/1.4-F01.pdf', {})
check('Bereich danach wählbar; ein Ordner „Nr Titel“ des Bereichs gilt als dieser Bereich – im Bereich weiter nie per Nummer', pl['_Firma/HACCP/1.4 QS/1.4-F01.xlsx']['ziel'] == haccp['id']
      and e_.get('status') == 'ablage' and 'kandidat' not in e_ and (r2['neu'][e_['neu']]['kapitel'] if 'neu' in e_ else dok(e_['ziel'])['kapitel']) == '91', (pl, pl2))
d_ = speicher('qs-dokumente'); alt_dok = json.loads(json.dumps(d_))
d_['liste'] += [{'id': f'dfuell{i:06d}', 'art': 'O', 'kapitel': '2.4', 'nr': '', 'titel': f'Füllung {i}', 'versionen': [], 'dateien': [], 'eingezogen': None, 'verlauf': [], 'rev': 1}
                for i in range(5000 - len(d_['liste']))]
storage_write('qs-dokumente', d_)
st, r, _ = plan(V, ['_Neu/Sub/a.pdf', 'X/b.pdf'], {'wahl': {'_Neu': {'art': 'neu', 'kapitel': '92', 'titel': 'Neu'}}}, anlegen=True)
check('anlegen prüft alle Grenzen vor dem Schreiben: zu viele Dokumente → 422, kein Bereich angelegt (Fehler 15)', st == 422
      and not any(k['id'] == '92' for k in speicher('qs-stamm')['kapitel']), (st, r.get('error')))
storage_write('qs-dokumente', alt_dok)

# ── Gebündeltes Eintragen: der Server berechnet das Ziel unter der Sperre neu ──
B1 = ['QM-System/1.4 Qualitätssicherung/Reinigungsnachweise/2023/KW1.pdf', 'QM-System/1.4 Qualitätssicherung/Reinigungsnachweise/2023/KW2.pdf', G + '/1.4-F01.pdf',
      G + '/1.4-F02 Probenahme.pdf', 'QM-System/Lose.pdf']
ANG = {'wurzel': SF, **FREI}
st, r, pl = plan(Q, B1, ANG)
KW1, KW2 = pdf('KW1'), pdf('KW2')
ab_vorher = speicher('qs-ablage').get('rev', 0)
u1 = sammeln(Q, B1[0], KW1)
check('sammeln: fertiger Upload bleibt liegen, noch nichts eingetragen', speicher('qs-ablage').get('rev', 0) == ab_vorher and glob.glob(os.path.join(ABLAGE, '.teile', u1 + '*')))
check('sammeln: Herkunft muss ein Text sein (422)', hochladen(Q, '', '', 'x.pdf', pdf('x'), {'sammeln': True, 'herkunft': ['a']})[0] == 422)
check('fremder Upload: Fehler, nichts eingetragen', eintragen(Be, [(u1, pl[B1[0]])], ANG)[1]['uploads'][u1]['status'] == 'fehler' and speicher('qs-ablage').get('rev', 0) == ab_vorher)
u2, u3, u4, u5 = sammeln(Q, B1[1], KW2), sammeln(Q, B1[2], pdf('F01 neu')), sammeln(Q, B1[3], pdf('F02 Entwurf')), sammeln(Q, B1[4], pdf('lose'))
verlauf_d1 = len(dok(D1['id'])['verlauf'])
st, r = eintragen(Q, [(u1, pl[B1[0]]), (u2, pl[B1[1]]), (u3, pl[B1[2]]), (u4, pl[B1[3]]), (u5, pl[B1[4]])], ANG)
u = r.get('uploads', {})
check('ein Aufruf trägt alle ein (Archiv, gültige Version, Entwurf, Eingang)', st == 200 and [u[x]['status'] for x in (u1, u2, u3, u4, u5)] == ['abgelegt'] * 4 + ['eingang'], r)
check('unbekannter Upload → Fehler je Upload', eintragen(Q, [('f' * 24, {'status': 'ablage'})], ANG)[1]['uploads']['f' * 24]['status'] == 'fehler')
a1 = {f['name']: f for f in archiv(O1)}
check('Archiv: Unterordner als pfad, ein Schreibvorgang für qs-ablage', a1['KW1.pdf']['pfad'] == '2023' and a1['KW2.pdf']['pfad'] == '2023' and speicher('qs-ablage')['rev'] == ab_vorher + 1, a1)
d1 = dok(D1['id']); g1 = [f for f in d1['versionen'][0]['dateien'] if f['name'] == '1.4-F01.pdf']
check('gültige Version: nachgetragen, ein Verlaufseintrag am Dokument', g1 and g1[0].get('nachgetragen') and len(d1['verlauf']) == verlauf_d1 + 1
      and d1['verlauf'][-1]['was'] == 'Datei zu Version 1 nachgetragen: 1.4-F01.pdf', d1['verlauf'][-1:])
d5 = dok(D5['id'])
check('Entwurf: wer hochgeladen hat, ist Bearbeiter (4-Augen-Prinzip)', ids['quinn'] in d5['versionen'][0]['bearbeiter'], d5['versionen'][0]['bearbeiter'])
# Häkchen fehlt beim Eintragen (über die API): nie nachtragen, sondern Eingang
u_ = sammeln(Q, G + '/1.4-F01 Temperaturkontrolle.pdf', pdf('ohne Häkchen'))
x_ = eintragen(Q, [(u_, {'status': 'nachtragen', 'ver': D1['versionen'][0]['id']})], {'wurzel': SF})[1]['uploads'][u_]
check('Häkchen fehlt beim Eintragen → Eingang (Grund), gültige Version unverändert', x_['status'] == 'eingang' and 'geändert' in x_.get('grund', '')
      and not any(f['name'] == '1.4-F01 Temperaturkontrolle.pdf' for f in dok(D1['id'])['versionen'][0]['dateien']), x_)
u_ = sammeln(Q, 'Matthies Werk/1.4 Qualitätssicherung/1.4-F01.pdf', pdf('Matthies ohne Antwort'))
x_ = eintragen(Q, [(u_, {'status': 'nachtragen', 'ver': D1['versionen'][0]['id']})], {'wurzel': {'name': 'Matthies Werk'}, 'freigaben': {'1.4 Qualitätssicherung': {'nachtragen': True}}})[1]['uploads'][u_]
check('Fremdfirma ohne Bestätigung der Wurzel beim Eintragen → Eingang, nie in Standard-Fleisch', x_['status'] == 'eingang' and eingang()[x_['datei']]['pfad'] == '1.4 Qualitätssicherung'
      and not any(f['sha256'] == __import__('hashlib').sha256(pdf('Matthies ohne Antwort')).hexdigest() for f in dok(D1['id'])['versionen'][0]['dateien']), x_)
# Entwurf inzwischen freigegeben (Review 2, MITTEL 3): der Plan sagte Entwurf, jetzt wäre es die gültige Version
D7 = gelenkt('1.4', 'F', '1.4-F09', 'Hygiene', gueltig=False)
st, r, pl7 = plan(Q, [G + '/1.4-F09 Hygiene.pdf'], ANG)
u7 = sammeln(Q, G + '/1.4-F09 Hygiene.pdf', pdf('Hygiene neu'))
hochladen(Be, D7['id'], D7['versionen'][0]['id'], 'Erstfassung.pdf', pdf('Hygiene'))
Be.call('qs_version_schritt', {'dokument': D7['id'], 'rev': dok(D7['id'])['rev'], 'schritt': 'einreichen'})
check('Entwurf freigegeben, während der Import läuft', Q.call('qs_version_schritt', {'dokument': D7['id'], 'rev': dok(D7['id'])['rev'], 'schritt': 'pruefen_freigeben'})[0] == 200
      and pl7[G + '/1.4-F09 Hygiene.pdf']['status'] == 'dokument')
x7 = eintragen(Q, [(u7, pl7[G + '/1.4-F09 Hygiene.pdf'])], ANG)[1]['uploads'][u7]
check('… dann kommt die Datei in den Eingang, nicht in die gültige Version', x7['status'] == 'eingang' and [f['name'] for f in dok(D7['id'])['versionen'][0]['dateien']] == ['Erstfassung.pdf'], x7)
u6 = sammeln(Q, B1[0], KW1)
st, r = eintragen(Q, [(u6, pl[B1[0]])], ANG)
check('gleiche Datei (Ziel, pfad, Name, Prüfsumme) → „vorhanden“, Datei wieder weg', r['uploads'][u6] == {'status': 'vorhanden', 'datei': a1['KW1.pdf']['id']} and len(archiv(O1)) == 2, r)
lid = next(i for i, f in eingang().items() if f['name'] == 'Lose.pdf')
Be.call('qs_eingang_loeschen', {'dateien': [lid]})
u8 = sammeln(Q, B1[4], pdf('lose'))
check('früher im Eingang gelöscht → „verworfen“, nicht wieder in den Eingang', eintragen(Q, [(u8, pl[B1[4]])], ANG)[1]['uploads'][u8]['status'] == 'verworfen'
      and not any(f['name'] == 'Lose.pdf' for f in eingang().values()))
st, r, plg = plan(Q, ['QM-System/1.4 Qualitätssicherung/Reinigungsnachweise/2024/Lose.pdf', G + '/x.pdf'], ANG)
u9 = sammeln(Q, 'QM-System/1.4 Qualitätssicherung/Reinigungsnachweise/2024/Lose.pdf', pdf('lose'))
check('„verworfen“ gilt nur für den Eingang: dieselbe Datei in einen Ordner wird abgelegt (Fehler 8)',
      eintragen(Q, [(u9, plg['QM-System/1.4 Qualitätssicherung/Reinigungsnachweise/2024/Lose.pdf'])], ANG)[1]['uploads'][u9]['status'] == 'abgelegt')
O2 = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'O', 'nr': '', 'titel': 'Gleich zu'})[1]['dokument']['id']
st, r, plz = plan(Q, [G + '/Gleich zu/Unter/Spaet.pdf'], ANG)
u10 = sammeln(Q, G + '/Gleich zu/Unter/Spaet.pdf', pdf('spät'))
Q.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'O', 'nr': '', 'titel': 'Gleich zu', 'id': O2, 'rev': dok(O2)['rev'], 'eingezogen': True, 'einzugGrund': 'zu'})
r10 = eintragen(Q, [(u10, plz[G + '/Gleich zu/Unter/Spaet.pdf'])], ANG)[1]['uploads'][u10]
e10 = eingang().get(r10.get('datei'), {})
check('Ziel inzwischen gesperrt → Eingang mit Grund und ganzem Ordnerpfad', plz[G + '/Gleich zu/Unter/Spaet.pdf']['ziel'] == O2 and r10['status'] == 'eingang' and r10.get('grund')
      and e10.get('pfad') == '1.4 Qualitätssicherung/Gleich zu/Unter', (r10, e10))
u11 = sammeln(Be, G + '/1.4-F01 Temperaturkontrolle.pdf', pdf('Bernd'))
r11 = eintragen(Be, [(u11, {'status': 'nachtragen', 'ver': D1['versionen'][0]['id']})], ANG)[1]['uploads'][u11]
check('gültige Version ohne Freigaberecht → Eingang', r11['status'] == 'eingang', r11)
check('Bündel: höchstens 100 Uploads, ungültige Angaben → 422; nur ansehen 403', Q.call('qs_import_eintragen', {'uploads': [{'upload': f'{i:024x}', 'status': 'ablage'} for i in range(101)]})[0] == 422
      and Q.call('qs_import_eintragen', {'uploads': [u1]})[0] == 422 and Q.call('qs_import_eintragen', {'uploads': [{'upload': u1, 'status': 'aus'}]})[0] == 422
      and L.call('qs_import_eintragen', {'uploads': [{'upload': u1, 'status': 'ablage'}]})[0] == 403 and L.call('qs_sammel_plan', {'ordner': []})[0] == 403)


def gross_docx(mb):
    b_ = io.BytesIO()
    with zipfile.ZipFile(b_, 'w', zipfile.ZIP_STORED) as z:
        z.writestr('[Content_Types].xml', '<Types/>'); z.writestr('word/document.xml', '<w:document/>'); z.writestr('word/media/bild.bin', os.urandom(mb * 1024 * 1024))
    return b_.getvalue()


vorher = blobs()
ug1, ug2 = sammeln(Q, G + '/1.4-F01.docx', gross_docx(21)), sammeln(Q, G + '/1.4-F01 Temperaturkontrolle.docx', gross_docx(21))
eg = {'status': 'nachtragen', 'ver': D1['versionen'][0]['id']}
rg = eintragen(Q, [(ug1, eg), (ug2, eg)], ANG)[1]['uploads']
check('Word/Excel-Nachträge je Bündel höchstens 40 MB (Lenkung unter der Sperre): der zweite → Fehler, seine Datei wieder weg', rg[ug1]['status'] == 'abgelegt'
      and rg[ug2]['status'] == 'fehler' and 'Bündel' in rg[ug2].get('grund', '') and len(blobs() - vorher) == 1, rg)
check('keine Reste unter .teile', not [x for x in glob.glob(os.path.join(ABLAGE, '.teile', '*')) if any(u_ in x for u_ in (u1, u2, u3, u4, u5, u6, u7, u8, u9, u10, u11, ug1, ug2))])


def lange_absaetze(n=6600, laenge=4500):
    """Word-Datei mit Platzhalter: entpackt rund 28 MB in 19.800 Textelementen (unter der Elementgrenze), gepackt rund 0,1 MB"""
    satz = 'Lorem ipsum dolor sit amet {{Titel}} ' * (laenge // 37)
    xml = ('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
           + ''.join(f'<w:p><w:r><w:t>{satz}{i}</w:t></w:r></w:p>' for i in range(n)) + '</w:body></w:document>')
    b_ = io.BytesIO()
    with zipfile.ZipFile(b_, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', '<Types/>'); z.writestr('word/document.xml', xml)
    return b_.getvalue()


# ── Große Word-Datei (Review 3, N2): über 8 MB XML gilt sie als nicht lesbar – sie liegt im Entwurf, nur ohne Platzhalter; das Bündel bleibt heil
#    (vorher erschöpfte das Lesen bei memory_limit 128M den Speicher, und das ganze Bündel endete mit 500) ──
GW, BG = lange_absaetze(), pdf('Begleitung N2')
st, r, plg = plan(Q, [(G + '/1.4-F02.docx', len(GW)), ('QM-System/Begleitung N2.pdf', len(BG))], ANG)
ugw, ubg = sammeln(Q, G + '/1.4-F02.docx', GW), sammeln(Q, 'QM-System/Begleitung N2.pdf', BG)
st, r = eintragen(Q, [(ugw, plg[G + '/1.4-F02.docx']), (ubg, plg['QM-System/Begleitung N2.pdf'])], ANG)
gf = next((f for f in dok(D5['id'])['versionen'][0].get('dateien', []) if f['name'] == '1.4-F02.docx'), {})
check('große Word-Datei (28 MB XML): Bündel heil, Datei im Entwurf ohne Platzhalter (nicht gelesen), Begleitdatei im Eingang', st == 200
      and plg[G + '/1.4-F02.docx']['status'] == 'dokument' and r['uploads'][ugw]['status'] == 'abgelegt' and r['uploads'][ubg]['status'] == 'eingang'
      and gf and 'platzhalter' not in gf, (st, r, gf))

# ── Abbruch beim Schreiben (Review 2, MITTEL 4): qs-ablage lässt sich nicht schreiben, nachdem qs-dokumente geschrieben ist (Dateimodus)
#    bzw. alles wird zurückgesetzt (SQLite). Danach zeigt keine Version auf eine fehlende Datei, und es bleibt keine verwaiste Datei ──
st, r, plb = plan(Q, [G + '/1.4-F05.docx', G + '/Reinigungsnachweise/2025/Abbruch.pdf'], ANG)
ua, ub = sammeln(Q, G + '/1.4-F05.docx', docx_w('Kalibrierung neu')), sammeln(Q, G + '/Reinigungsnachweise/2025/Abbruch.pdf', pdf('Abbruch'))
vorher = blobs()
ordner_ = datenordner('qs-ablage')
if storage_sqlite():
    with sqlite3.connect(ordner_ + '/.sqlite/store.sqlite') as db:
        db.execute("CREATE TRIGGER qs_ablage_kaputt BEFORE UPDATE ON documents WHEN NEW.name = 'qs-ablage' BEGIN SELECT RAISE(ABORT, 'Testfehler'); END")
else:
    os.rename(ordner_ + '/qs-ablage.php', ordner_ + '/qs-ablage.weg')
    os.makedirs(ordner_ + '/qs-ablage.php/x')
st, r = eintragen(Q, [(ua, plb[G + '/1.4-F05.docx']), (ub, plb[G + '/Reinigungsnachweise/2025/Abbruch.pdf'])], ANG)
if storage_sqlite():
    with sqlite3.connect(ordner_ + '/.sqlite/store.sqlite') as db:
        db.execute('DROP TRIGGER qs_ablage_kaputt')
else:
    shutil.rmtree(ordner_ + '/qs-ablage.php')
    os.rename(ordner_ + '/qs-ablage.weg', ordner_ + '/qs-ablage.php')
neu_ = blobs() - vorher
fehlt = {i for i in benutzt() if not os.path.isfile(blob_pfad(i)) and not i.startswith(('fuell', 'dfuell'))}
check('Abbruch beim Schreiben: Fehler gemeldet, keine Version zeigt auf eine fehlende Datei, keine verwaiste Datei', st >= 500 and not fehlt and neu_ <= benutzt(), (st, fehlt, neu_ - benutzt()))
d8v = [f['name'] for f in dok(D8['id'])['versionen'][0]['dateien']]
check('… im Dateimodus bleibt der Nachtrag (qs-dokumente war geschrieben), mit SQLite ist alles zurückgesetzt', ('1.4-F05.docx' in d8v) != storage_sqlite()
      and not any(f['name'] == 'Abbruch.pdf' for f in archiv(O1)), d8v)

# ── Fortsetzen: der Plan erkennt Abgelegtes – auch Dateien, die aus dem Eingang zugeordnet wurden ──
RN = G + '/Reinigungsnachweise'
st, r, pl = plan(Q, [(RN + '/2023/KW1.pdf', len(KW1)), (RN + '/2023/KW3.pdf', 10), (G + '/1.4-F01.pdf', len(pdf('F01 neu'))), ('QM-System/Notizen/a.pdf', len(pdf('Notiz')))], ANG)
check('erneuter Plan: abgelegte Datei „schon da“, neue nicht', pl[RN + '/2023/KW1.pdf'].get('schonDa') and not pl[RN + '/2023/KW3.pdf'].get('schonDa')
      and pl[G + '/1.4-F01.pdf'].get('schonDa') and 'kandidat' not in pl[G + '/1.4-F01.pdf'], pl)
un = sammeln(Q, 'QM-System/Notizen/a.pdf', pdf('Notiz'))
nid = eintragen(Q, [(un, pl['QM-System/Notizen/a.pdf'])], ANG)[1]['uploads'][un]['datei']
Be.call('qs_datei_zuordnen', {'dateien': [nid], 'dokument': O1})
check('aus dem Eingang zugeordnet: der Plan erkennt sie trotzdem', plan(Q, [('QM-System/Notizen/a.pdf', len(pdf('Notiz'))), G + '/x/y.pdf'], ANG)[2]['QM-System/Notizen/a.pdf'].get('schonDa'))

# ── Grenzen ──
check('höchstens 30 000 Dateien je Lauf (422)', Q.call('qs_sammel_plan', {'ordner': [['A', [[f'{i}.pdf', 1] for i in range(30001)]]]})[0] == 422)
check('ungültige Ordnerliste (422)', Q.call('qs_sammel_plan', {'ordner': [['A', [['a.pdf', 'x']]]]})[0] == 422 and Q.call('qs_sammel_plan', {'ordner': [[1, []]]})[0] == 422)
fuellen(Be, 10000 - len(archiv(O1)), O1, 'fuellung')
e_ = plan(Q, [RN + '/neu.pdf', G + '/y.pdf'], ANG)[2][RN + '/neu.pdf']
check('Ordner voll (10 000) → der Plan legt in den Eingang', e_['status'] == 'eingang' and e_['grund'] == 'Ordner voll', e_)
check('Hochladen in einen vollen Ordner → 422', hochladen(Be, O1, '', 'Zuviel.pdf', pdf('zu viel'))[0] == 422)
leeren(Be, 'fuellung')

# ── Ältere Dateien am Ordner (GR-006: dateien in qs-dokumente ohne pfad) ──
alt_id = hochladen(Be, 'eingang', '', 'Alt-Zertifikat.pdf', pdf('alt'))[1]['datei']
ab = speicher('qs-ablage'); alt = next(f for f in ab['liste'] if f['id'] == alt_id)
ab['liste'] = [f for f in ab['liste'] if f['id'] != alt_id]; storage_write('qs-ablage', ab)
d_ = speicher('qs-dokumente'); x_ = next(x for x in d_['liste'] if x['id'] == O1)
x_['dateien'] = [{k: v for k, v in alt.items() if k not in ('ziel', 'pfad')}]; storage_write('qs-dokumente', d_)
neu_zaehlen(Be)
a1 = {f['name']: f for f in archiv(O1)}
check('ältere Datei am Ordner: im Baum (ohne pfad), Download, Zahl in qs_start, Plan erkennt sie', a1['Alt-Zertifikat.pdf']['pfad'] == '' and roh(L, 'qs_datei&id=' + alt_id) == (200, pdf('alt'))
      and L.call('qs_start')[1]['ablageZahlen'][O1]['dateien'] == len([f for f in a1.values() if not f.get('entfernt')])
      and plan(Q, [(G + '/Alt-Zertifikat.pdf', 1), (RN + '/Alt-Zertifikat.pdf', len(pdf('alt')))], ANG)[2][RN + '/Alt-Zertifikat.pdf'].get('schonDa'))

# ── Ordnerbaum, ZIP je Unterordner, ZIP-Export ──
st, z = roh(L, f'qs_archiv_zip&dok={O1}&pfad=2023')
namen = sorted(zipfile.ZipFile(io.BytesIO(z)).namelist()) if st == 200 else []
check('ZIP eines Unterordners: Aufbau Ordner/pfad/Datei, nur dieser Unterordner, Inhalt gleich', namen == ['Reinigungsnachweise/2023/KW1.pdf', 'Reinigungsnachweise/2023/KW2.pdf']
      and zipfile.ZipFile(io.BytesIO(z)).read('Reinigungsnachweise/2023/KW1.pdf') == KW1, (st, namen))
st, z = roh(L, f'qs_archiv_zip&dok={O1}')
check('ZIP des ganzen Ordners mit älterer Datei', st == 200 and 'Reinigungsnachweise/Alt-Zertifikat.pdf' in zipfile.ZipFile(io.BytesIO(z)).namelist())
check('Ordnerbaum und ZIP: unbekanntes Dokument 404, leerer Unterordner 404, ohne Anmeldung kein Zugang', L.call('qs_archiv&dok=dnix')[0] == 404
      and roh(L, f'qs_archiv_zip&dok={O1}&pfad=gibtsnicht')[0] == 404 and Client('198.51.100.40').call(f'qs_archiv&dok={O1}')[0] in (401, 403, 404))
st, z = roh(L, 'qs_ablage_export')
namen = zipfile.ZipFile(io.BytesIO(z)).namelist()
check('ZIP-Export des QM-Systems: Archivdateien mit Unterordnern, ältere am Ordner, nichts aus dem Eingang', 'QM-System/1.4 Qualitätssicherung/Reinigungsnachweise/2023/KW1.pdf' in namen
      and 'QM-System/1.4 Qualitätssicherung/Reinigungsnachweise/Alt-Zertifikat.pdf' in namen and not any('Spaet.pdf' in n for n in namen), [n for n in namen if 'Reinigung' in n])
kw2 = next(f for f in archiv(O1) if f['name'] == 'KW2.pdf')['id']
check('Archivdatei entfernen: nur mit Grund, dann vermerkt (nicht gelöscht), nicht im Export', Be.call('qs_datei_entfernen', {'datei': kw2, 'grund': ''})[0] == 422
      and Be.call('qs_datei_entfernen', {'datei': kw2, 'grund': 'doppelt'})[0] == 200 and next(f for f in archiv(O1) if f['id'] == kw2)['entfernt']['grund'] == 'doppelt'
      and os.path.isfile(blob_pfad(kw2)) and roh(L, 'qs_datei&id=' + kw2)[0] == 404 and Be.call('qs_datei_entfernen', {'datei': kw2, 'grund': 'x'})[0] == 409)
check('ältere Datei am Ordner entfernen (vermerkt in qs-dokumente)', Be.call('qs_datei_entfernen', {'datei': alt_id, 'grund': 'ersetzt'})[0] == 200
      and next(f for f in archiv(O1) if f['id'] == alt_id).get('entfernt'))
st, r = L.call('qs_start')
aktiv_o1 = [f for f in archiv(O1) if not f.get('entfernt')]
check('qs_start: Zahl und Bytes je Ordner vom Server', r['ablageZahlen'][O1] == {'dateien': len(aktiv_o1), 'bytes': sum(f['groesse'] for f in aktiv_o1)}, r['ablageZahlen'].get(O1))
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Ordner-Import mit Anzahl, ohne Datei- und Ordnernamen', 'Ordner-Import: 5 Dateien abgelegt' in log and 'Ordner-Dokumente und 1 Bereiche angelegt' in log
      and 'KW1.pdf' not in log and 'Reinigungsnachweise (Unterordner)' in log and '2023' not in log.split('Reinigungsnachweise (Unterordner)')[0][-200:], log[-1500:])

# ── Oberfläche ──
tmp = tempfile.mkdtemp(prefix='qs-import-')
QMS = os.path.join(tmp, 'QM-System')
DATEIEN = {'1.4 Qualitätssicherung/1.4-F01 Temperaturkontrolle.pdf': pdf('F01 Fassung'),            # gültige Version → nur mit Häkchen
           '1.4 Qualitätssicherung/1.4-F01.docx': docx_w('F01 Word'),                             # zweite Datei zur selben Nummer
           '1.4 Qualitätssicherung/1.4-F02 Probenahme.docx': b'MZ' + pdf('F02 neu'),   # Inhalt passt nicht: Fehler, Lauf geht weiter
           '1.4 Qualitätssicherung/1.4-F02 Probenahme.pdf': pdf('F02 Entwurf 2'),
           '1.4 Qualitätssicherung/Reinigungsnachweise/2025/Januar/KW1.pdf': pdf('2025 KW1'),
           '1.4 Qualitätssicherung/Reinigungsnachweise/2025/Januar/KW2.pdf': pdf('2025 KW2'),
           '1.4 Qualitätssicherung/Reinigungsnachweise/2025/Februar/KW5.pdf': pdf('2025 KW5'),
           '1.4 Qualitätssicherung/_alt/1.4-F01 alt.pdf': pdf('F01 alt'),
           '1.4 QS alt/1.4-F01.pdf': pdf('F01 alte Kopie'),
           '2.2 Lager/Temperaturlisten/2025/Juli.pdf': pdf('Juli'),
           '_Matthies Fleischwaren/HACCP-Matthies/1.4 Qualitätssicherung/1.4-F01.pdf': pdf('Matthies'),
           '_in Bearbeitung/Entwurf Hygieneplan.pdf': pdf('Hygiene'),
           'Zertifikat IFS.pdf': pdf('IFS'), '.DS_Store': b'\0\0', 'Sonstiges/setup.exe': b'MZ' + b'\0' * 50}
for pfad_, inhalt in DATEIEN.items():
    os.makedirs(os.path.dirname(os.path.join(QMS, pfad_)), exist_ok=True)
    with open(os.path.join(QMS, pfad_), 'wb') as f_:
        f_.write(inhalt)

with sync_playwright() as p:
    br = p.chromium.launch()

    def zahl(pg, n):
        return pg.evaluate("n => { const d = [...document.querySelectorAll('#im-zahlen div')].find(x => x.querySelector('span').textContent === n); return d ? Number(d.querySelector('b').textContent.replace(/\\./g, '')) : -1; }", n)

    def zeilen(pg):
        return pg.evaluate("Object.fromEntries([...document.querySelectorAll('#im-liste tbody tr')].filter(t => t.querySelector('.qm-name')).map(t => [t.querySelector('.qm-name').textContent, t.querySelector('.qm-sa-status').textContent.trim()]))")

    def oberste(pg):
        return pg.evaluate("Object.fromEntries([...document.querySelectorAll('#im-oberste tbody tr')].map(t => [t.querySelector('.qm-name').textContent, t.querySelector('.qm-im-wahl').textContent.trim()]))")

    def warte_ende(pg):
        pg.wait_for_function("!document.querySelector('#im-csv').hidden")

    def neu_geplant(pg, aktion):
        """Aktion, die einen neuen Plan anfordert – wartet auf dessen Antwort"""
        with pg.expect_response(lambda x: 'qs_sammel_plan' in x.url):
            aktion()
        pg.wait_for_function("document.querySelector('#im-meldung').textContent === ''")

    def qm_waehlen(pg, wurzel_beantworten=True):
        pg.click('#qm-d-import'); pg.wait_for_selector('#dlg-import[open]')
        pg.set_input_files('#im-ordner', QMS)
        pg.wait_for_selector('#im-liste tr .qm-name')
        if wurzel_beantworten:
            neu_geplant(pg, lambda: pg.select_option('#im-wurzel-wahl', 'sf'))

    ctx, pg = anmelden(br, 'vera', 'Verwalt-Konto-90', '198.51.100.13')
    qm_waehlen(pg, False)
    check('Vorschau: gewählter Ordner, erkannte Kapitel, Hinweis', 'Gewählter Ordner: QM-System' in text(pg, '#im-wurzel') and 'erkannte Kapitel: 1.4, 2.2' in text(pg, '#im-wurzel')
          and pg.is_visible('#im-warnung'), text(pg, '#im-wurzel'))
    check('Wurzel-Frage: ohne Antwort ist nichts zugeordnet und Importieren gesperrt', pg.is_visible('#im-frage') and pg.input_value('#im-wurzel-wahl') == ''
          and pg.is_disabled('#im-los') and zeilen(pg).get('1.4-F01 Temperaturkontrolle.pdf') == 'Zuordnung offen'
          and 'Bereich 90 Matthies Fleischwaren' in text(pg, '#im-wurzel-wahl'), (zeilen(pg), text(pg, '#im-frage')))
    pg.screenshot(path=os.path.join(SH, 'qs_import_wurzel_1280.png'), full_page=True)
    neu_geplant(pg, lambda: pg.select_option('#im-wurzel-wahl', 'sf'))
    ob_ = oberste(pg)
    check('Vorschau: Kapitelordner erkannt, Vorschlag nur Archiv, Bereich gleichen Namens automatisch, lose Dateien in den Eingang',
          pg.input_value('#im-oberste [data-im-wahl="1.4 Qualitätssicherung"]') == 'genau' and pg.input_value('#im-oberste [data-im-wahl="1.4 QS alt"]') == 'kapitel:1.4'
          and 'Ordnername bleibt erhalten' in ob_.get('1.4 QS alt', '') and pg.input_value('#im-oberste [data-im-wahl="_Matthies Fleischwaren"]') == 'kapitel:90'
          and pg.input_value('#im-oberste [data-im-wahl="_in Bearbeitung"]') == 'eingang' and ob_.get('lose Dateien') == 'Eingang' and pg.is_enabled('#im-los'), ob_)
    frei = '#im-freigaben [data-im-frei="1.4 Qualitätssicherung"]'
    check('Freigaben je Ordner: Nachtragen aus (2 Dateien), Entwürfe an (2 Dateien, ein Entwurf), Hinweis auf den Bearbeiter',
          pg.is_visible('#im-freigaben') and not pg.is_checked(frei + '[data-im-art="nachtragen"]') and pg.is_checked(frei + '[data-im-art="entwurf"]')
          and '2 Dateien als aktuelle Fassung in gültige Versionen nachtragen' in text(pg, '#im-freigaben') and '2 Dateien in Entwürfe ablegen' in text(pg, '#im-freigaben')
          and 'Sie werden Bearbeiter dieses Entwurfs' in text(pg, '#im-freigaben'), text(pg, '#im-freigaben'))
    pg.click('#im-freigaben summary')
    check('gruppiert je Nummer: 1.4-F01 mit zwei Dateien, jede einzeln abwählbar', '1.4-F01 Temperaturkontrolle → gültige Version · 2 Dateien zu dieser Nummer' in text(pg, '#im-freigaben')
          and pg.locator('#im-freigaben [data-im-ohne]').count() == 4, text(pg, '#im-freigaben'))
    neu_geplant(pg, lambda: pg.uncheck('#im-freigaben [data-im-ohne="QM-System/1.4 Qualitätssicherung/1.4-F01.docx"]'))
    z_ = zeilen(pg)
    check('abgewählte Datei → ins Archiv, die andere ohne Häkchen in den Eingang; Entwurf bleibt', z_.get('1.4-F01.docx') == 'ins Archiv'
          and z_.get('1.4-F01 Temperaturkontrolle.pdf') == 'in den Eingang · ohne Häkchen' and z_.get('1.4-F02 Probenahme.pdf') == 'in den Entwurf'
          and z_.get('KW5.pdf') == 'ins Archiv' and z_.get('Zertifikat IFS.pdf') == 'in den Eingang · lose Datei' and z_.get('.DS_Store') == 'Systemdatei'
          and z_.get('setup.exe', '').startswith('Dateiart'), z_)
    pg.click('#im-freigaben summary')
    pg.screenshot(path=os.path.join(SH, 'qs_import_vorschau_1280.png'), full_page=True)
    neu_geplant(pg, lambda: pg.select_option('#im-oberste [data-im-wahl="_in Bearbeitung"]', 'neu'))
    check('neuer Bereich: Nummer und Titel vorgeschlagen, Plan zählt ihn', pg.input_value('#im-oberste [data-im-nr="_in Bearbeitung"]') == '92'
          and pg.input_value('#im-oberste [data-im-titel="_in Bearbeitung"]') == 'in Bearbeitung' and zahl(pg, 'neue Bereiche') == 1, zahl(pg, 'neue Bereiche'))
    pg.evaluate("""() => { const f = window.fetch; window.__weiter = new Promise((ok) => { window.__frei = ok; });
      window.fetch = async (...a) => { if (String(a[0]).includes('qs_import_eintragen') && !window.__gehalten) { window.__gehalten = true; await window.__weiter; } return f(...a); }; }""")
    pg.click('#im-los')
    pg.wait_for_function("document.querySelector('#im-stand').textContent.includes('von')")
    pg.wait_for_function("[...document.querySelectorAll('#im-liste .qm-sa-status')].some(t => t.textContent.includes('wird eingetragen'))")
    check('Lauf: Fortschritt mit Dateien und Größe, Abbrechen sichtbar, Auswahl gesperrt', ' von ' in text(pg, '#im-stand') and 'KB' in text(pg, '#im-stand') and pg.is_visible('#im-stopp')
          and pg.is_disabled('#im-oberste select') and pg.is_disabled('#im-wurzel-wahl'))
    pg.screenshot(path=os.path.join(SH, 'qs_import_fortschritt_1280.png'), full_page=True)
    pg.evaluate('window.__frei()')
    warte_ende(pg)
    z_ = zeilen(pg)
    meldung = text(pg, '#im-meldung')
    check('Bericht: abgelegt, im Eingang, Fehler hält den Lauf nicht an', z_.get('KW5.pdf') == 'abgelegt' and z_.get('1.4-F01 Temperaturkontrolle.pdf') == 'im Eingang · ohne Häkchen'
          and 'passt nicht' in z_.get('1.4-F02 Probenahme.docx', '') and z_.get('Juli.pdf') == 'abgelegt' and z_.get('1.4-F02 Probenahme.pdf') == 'abgelegt'
          and 'Dateien abgelegt' in meldung, (meldung, z_))
    pg.screenshot(path=os.path.join(SH, 'qs_import_bericht_1280.png'), full_page=True)
    with pg.expect_download() as dl:
        pg.click('#im-csv')
    zeilen_csv = list(csv.reader(io.StringIO(open(dl.value.path(), encoding='utf-8-sig').read()), delimiter=';'))
    check('Bericht als CSV: eine Zeile je Datei mit Ergebnis und Ziel', dl.value.suggested_filename.startswith('QM-Ordner-Import_') and len(zeilen_csv) == len(DATEIEN) + 1
          and ['QM-System/2.2 Lager/Temperaturlisten/2025', 'Juli.pdf', str(len(pdf('Juli'))), 'abgelegt', 'Temperaturlisten'] in [z[:5] for z in zeilen_csv], zeilen_csv[:4])
    rn = {f['name']: f for f in archiv(O1)}
    tl = dok_titel('Temperaturlisten', '2.2'); mh = dok_titel('HACCP-Matthies', '90'); we = dok_titel('Weitere Dateien', '1.4')
    check('Server: Ordnerstruktur erhalten, Fremdfirma im Bereich 90, Vorschlag mit Ordnername, gültige Version ohne Häkchen unberührt',
          rn['KW1.pdf']['pfad'] == '2025/Januar' and rn['KW5.pdf']['pfad'] == '2025/Februar' and tl and [f['pfad'] for f in archiv(tl['id'])] == ['2025']
          and mh and [f['pfad'] for f in archiv(mh['id'])] == ['1.4 Qualitätssicherung'] and we and sorted((f['name'], f['pfad']) for f in archiv(we['id']))
          == [('1.4-F01.docx', ''), ('1.4-F01.pdf', '1.4 QS alt')] and not any(f['name'] == '1.4-F01 Temperaturkontrolle.pdf' for f in dok(D1['id'])['versionen'][0]['dateien'])
          and any(f['name'] == '1.4-F01 Temperaturkontrolle.pdf' and f['pfad'] == '1.4 Qualitätssicherung' for f in eingang().values())
          and any(k['id'] == '92' and k.get('bereich') for k in speicher('qs-stamm')['kapitel']), (rn, tl, mh, we))
    pg.eval_on_selector('#im-ordner', 'e => { e.value = ""; }')
    pg.set_input_files('#im-ordner', QMS)
    pg.wait_for_function("document.querySelector('#im-liste tr .qm-name') && !document.querySelector('#im-csv').offsetParent")
    pg.wait_for_function("document.querySelector('#im-wurzel-wahl') && document.querySelector('#im-wurzel-wahl').value === 'sf'")
    z_ = zeilen(pg)
    check('denselben Ordner noch einmal: Antwort, Zuordnung und Abwahl gemerkt, Abgelegtes „schon abgelegt“, offen nur der Fehler', z_.get('KW5.pdf') == 'schon abgelegt'
          and z_.get('1.4-F01 Temperaturkontrolle.pdf') == 'schon abgelegt' and z_.get('1.4-F01.docx') == 'schon abgelegt' and z_.get('Entwurf Hygieneplan.pdf') == 'schon abgelegt'
          and text(pg, '#im-los') == '1 Datei importieren', (z_, text(pg, '#im-los')))
    check('Freigaben werden nie gemerkt: das Häkchen für gültige Versionen ist wieder aus', all(not c.is_checked() for c in pg.locator('#im-freigaben [data-im-art="nachtragen"]').all()))
    # Review 3 (M3): ein anderer Ordner gleichen Namens – etwa der der Fremdfirma – bekommt die gemerkte Antwort nicht (Schlüssel: Name, Zahl, Bytes);
    # N5: zerlegte Umlaute wie von macOS (NFD) gelten wie zusammengesetzte (Kapitelordner, Dateiname)
    QMS2 = os.path.join(tmp, 'zweiter', 'QM-System')
    for pfad_, inhalt in (('1.4 Qualita\u0308tssicherung/Pru\u0308fbericht N5.pdf', pdf('NFD')), ('1.4 Qualita\u0308tssicherung/1.4-F01.pdf', pdf('Fremdfirma'))):
        os.makedirs(os.path.dirname(os.path.join(QMS2, pfad_)), exist_ok=True)
        with open(os.path.join(QMS2, pfad_), 'wb') as f_:
            f_.write(inhalt)
    pg.eval_on_selector('#im-ordner', 'e => { e.value = ""; }')
    pg.set_input_files('#im-ordner', QMS2)
    pg.wait_for_function("document.querySelectorAll('#im-liste tbody tr .qm-name').length === 2 && document.querySelector('#im-meldung').textContent === ''")
    check('anderer Ordner „QM-System“: Wurzel-Frage offen, Importieren gesperrt (keine gemerkte Antwort)', pg.input_value('#im-wurzel-wahl') == '' and pg.is_disabled('#im-los')
          and zeilen(pg).get('1.4-F01.pdf') == 'Zuordnung offen', zeilen(pg))
    neu_geplant(pg, lambda: pg.select_option('#im-wurzel-wahl', 'sf'))
    wahl_ = pg.evaluate("[...document.querySelectorAll('#im-oberste [data-im-wahl]')].map(s => [s.dataset.imWahl, s.value])")
    check('zerlegte Umlaute: Kapitelordner „1.4 Qualitätssicherung“ genau erkannt', wahl_ == [['1.4 Qualitätssicherung', 'genau']], wahl_)
    pg.click('#im-los'); warte_ende(pg)
    we2 = sorted(f['name'] for f in archiv(dok_titel('Weitere Dateien', '1.4')['id']))
    check('… Dateiname zusammengesetzt abgelegt (NFC)', 'Prüfbericht N5.pdf' in we2 and 'Pru\u0308fbericht N5.pdf' not in we2, we2)
    pg.click('#dlg-import .qm-knopfreihe [data-im-zu]'); pg.wait_for_selector('#dlg-import', state='hidden')
    ctx.close()

    # Abbruch: der erste Upload wird festgehalten, bis „Abbrechen“ gedrückt ist; danach Neuladen und fortsetzen
    NACHW = os.path.join(tmp, 'Nachweise')
    for k in (1, 2, 3, 4):
        os.makedirs(os.path.join(NACHW, 'Labor A'), exist_ok=True)
        with open(os.path.join(NACHW, 'Labor A', f'Befund {k}.pdf'), 'wb') as f_:
            f_.write(pdf(f'Befund {k}'))
    ctx, pg = anmelden(br, 'bernd', 'Bearbeit-Konto-34', '198.51.100.11')
    pg.click('#qm-d-import'); pg.wait_for_selector('#dlg-import[open]')
    pg.set_input_files('#im-ordner', NACHW)
    pg.wait_for_function("document.querySelector('#im-los').textContent.startsWith('4 ')")
    check('ohne „verwalten“ kein neuer Bereich, ohne Kapitelordner keine Wurzel-Frage', pg.locator('#im-oberste option[value="neu"]').count() == 0 and pg.is_hidden('#im-frage'))
    pg.evaluate("""() => { const f = window.fetch; window.__weiter = new Promise((ok) => { window.__frei = ok; });
      window.fetch = async (...a) => { if (String(a[0]).includes('qs_datei_hochladen')) await window.__weiter; return f(...a); }; }""")
    pg.click('#im-los'); pg.wait_for_selector('#im-stopp:not([hidden])'); pg.click('#im-stopp'); pg.evaluate('window.__frei()')
    warte_ende(pg)
    check('abgebrochen: die drei laufenden Dateien fertig, der Rest nicht hochgeladen', '3 im Eingang' in text(pg, '#im-meldung') and 'abgebrochen, 1 nicht hochgeladen' in text(pg, '#im-meldung'), text(pg, '#im-meldung'))
    ctx.close()
    ctx, pg = anmelden(br, 'bernd', 'Bearbeit-Konto-34', '198.51.100.11')
    pg.click('#qm-d-import'); pg.wait_for_selector('#dlg-import[open]')
    pg.set_input_files('#im-ordner', NACHW)
    pg.wait_for_selector('#im-liste tr .qm-name')
    offen = int(text(pg, '#im-los').split()[0])
    check('nach Neuladen: nur der Rest ist offen', offen == 1, text(pg, '#im-los'))
    pg.click('#im-los'); warte_ende(pg)
    befunde = sorted((f['name'], f['pfad']) for f in eingang().values() if f['name'].startswith('Befund '))
    check('fortgesetzt: jede Datei genau einmal im Eingang, Pfad ohne den gewählten Ordner', befunde == [(f'Befund {k}.pdf', 'Labor A') for k in (1, 2, 3, 4)], befunde)
    ctx.close()

    # Ordnerbaum in der Seitenleiste
    for user, pw, ip, breite, thema in (('bernd', 'Bearbeit-Konto-34', '198.51.100.11', 1280, 'light'), ('lisa', 'Leserin-Konto-12', '198.51.100.10', 390, 'light'),
                                        ('lisa', 'Leserin-Konto-12', '198.51.100.10', 390, 'dark'), ('bernd', 'Bearbeit-Konto-34', '198.51.100.11', 1280, 'dark')):
        ctx, pg = anmelden(br, user, pw, ip, breite, thema, 844 if breite < 500 else 900)
        pg.click(f'#qm-d-liste tr[data-dok="{O1}"]'); pg.wait_for_selector('#dk-baum .qm-baum-ordner')
        if user == 'bernd' and thema == 'light':
            n_o1 = len([f for f in archiv(O1) if not f.get('entfernt')])
            check('Liste: Zahl der Dateien des Ordners aus qs_start', str(n_o1) in text(pg, f'#qm-d-liste tr[data-dok="{O1}"] .qm-anz'), text(pg, f'#qm-d-liste tr[data-dok="{O1}"]'))
            check('Baum: oberste Unterordner mit Zahl und ZIP, entfernte als Vermerk', pg.locator('#dk-baum-inhalt > .qm-baum-ordner').count() == 4
                  and pg.locator('#dk-baum-inhalt > .qm-baum-ordner .qm-baum-zip').count() == 4 and '2 Dateien entfernt' in text(pg, '#dk-baum'), text(pg, '#dk-baum'))
            pg.click('#dk-baum .qm-baum-ordner[data-pfad="2025"] > summary')
            pg.wait_for_selector('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"]')
            pg.click('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"] > summary')
            pg.wait_for_selector('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"] .qm-datei-name:has-text("KW2.pdf")')
            check('Baum: Unterordner füllen sich beim Aufklappen, Dateien mit Entfernen', pg.locator('#dk-baum [data-pfad="2025/Januar"] [data-datei-weg]').count() == 2)
            with pg.expect_download() as dl:
                pg.click('#dk-baum [data-pfad="2025/Januar"] .qm-datei-name:has-text("KW2.pdf")')
            check('Baum: Herunterladen über einen direkten Link', dl.value.suggested_filename == 'KW2.pdf' and open(dl.value.path(), 'rb').read() == pdf('2025 KW2'))
            with pg.expect_download() as dl:
                pg.click('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"] > summary .qm-baum-zip')
            check('Baum: Unterordner als ZIP', sorted(zipfile.ZipFile(dl.value.path()).namelist()) == ['Reinigungsnachweise/2025/Januar/KW1.pdf', 'Reinigungsnachweise/2025/Januar/KW2.pdf'])
            pg.fill('#dk-baum-suche', 'KW5')
            pg.wait_for_function("document.querySelectorAll('#dk-baum-inhalt .qm-datei').length === 1")
            check('Suche: Treffer mit Ordnerpfad', '2025 / Februar' in text(pg, '#dk-baum-inhalt'))
            pg.fill('#dk-baum-suche', '')
            pg.wait_for_selector('#dk-baum .qm-baum-ordner[data-pfad="2025"]')
            pg.click('#dk-baum .qm-baum-ordner[data-pfad="2025"] > summary')
            pg.wait_for_selector('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"]')
        else:
            pg.click('#dk-baum .qm-baum-ordner[data-pfad="2025"] > summary')
            pg.wait_for_selector('#dk-baum .qm-baum-ordner[data-pfad="2025/Januar"]')
            if user == 'lisa':
                check(f'{breite}px {thema}: nur ansehen – Baum ohne Entfernen und Ablagefeld, kein Import', pg.locator('#dk-baum [data-datei-weg]').count() == 0
                      and pg.locator('#qm-dk .qm-drop').count() == 0 and pg.is_hidden('#qm-d-import'))
        check(f'{breite}px {thema}: Ordnerbaum ohne waagerechtes Scrollen', ohne_scrollen(pg, '#qm-dk'))
        pg.screenshot(path=os.path.join(SH, f'qs_ordnerbaum_{user}_{breite}_{thema}.png'))
        ctx.close()
    for breite, thema in ((390, 'light'), (390, 'dark'), (1280, 'dark')):
        ctx, pg = anmelden(br, 'vera', 'Verwalt-Konto-90', '198.51.100.13', breite, thema, 844 if breite < 500 else 900)
        qm_waehlen(pg, False)
        pg.eval_on_selector('#im-frage', 'e => e.scrollIntoView({ block: "center" })')
        check(f'{breite}px {thema}: Wurzel-Frage ohne waagerechtes Scrollen', pg.is_visible('#im-frage') and ohne_scrollen(pg, '#dlg-import'))
        pg.screenshot(path=os.path.join(SH, f'qs_import_wurzel_{breite}_{thema}.png'))
        neu_geplant(pg, lambda: pg.select_option('#im-wurzel-wahl', 'sf'))
        pg.click('#im-freigaben summary')
        pg.eval_on_selector('#im-freigaben', 'e => e.scrollIntoView({ block: "start" })')
        check(f'{breite}px {thema}: Freigaben je Ordner und gruppierte Nummern ohne waagerechtes Scrollen', pg.is_visible('#im-freigaben [data-im-ohne]') and ohne_scrollen(pg, '#dlg-import'))
        pg.screenshot(path=os.path.join(SH, f'qs_import_vorschau_{breite}_{thema}.png'))
        pg.evaluate("""() => { const f = window.fetch; window.__weiter = new Promise((ok) => { window.__frei = ok; });
          window.fetch = async (...a) => { if (String(a[0]).includes('qs_datei_hochladen')) await window.__weiter; return f(...a); }; }""")
        pg.click('#im-los'); pg.wait_for_function("!document.querySelector('#im-stopp').hidden && document.querySelector('#im-stand').textContent.includes('von')")
        pg.eval_on_selector('#im-fortschritt', 'e => e.scrollIntoView({ block: "center" })')
        check(f'{breite}px {thema}: Fortschritt ohne waagerechtes Scrollen', ohne_scrollen(pg, '#dlg-import'))
        pg.screenshot(path=os.path.join(SH, f'qs_import_fortschritt_{breite}_{thema}.png'))
        pg.evaluate('window.__frei()'); warte_ende(pg)
        pg.eval_on_selector('#im-meldung', 'e => e.scrollIntoView({ block: "center" })')
        check(f'{breite}px {thema}: Bericht ohne waagerechtes Scrollen', ohne_scrollen(pg, '#dlg-import') and 'Fehler 1' in text(pg, '#im-meldung'), text(pg, '#im-meldung'))
        pg.screenshot(path=os.path.join(SH, f'qs_import_bericht_{breite}_{thema}.png'))
        ctx.close()
    shutil.rmtree(tmp, ignore_errors=True)
    br.close()
ende()
