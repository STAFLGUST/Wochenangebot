#!/usr/bin/env python3
"""Übernimmt eine Fassung der offenen Metadatenbank GEOS-EUDR (Thünen-Institut, MIT-Lizenz) in den Geodaten-Katalog des
Container-Imports (app/api/module/containerimport/geodatenkatalog.json).

Quelle: https://github.com/GEOS-EUDR-RepoHub/Metadatabase-Geodata-EUDR, Ordner data/ – je Thema eine Tabelle
`[Thema]_GeosEUDR_Thuenen_vX.Y.tsv` (die .csv dort ist ebenfalls tabulatorgetrennt). „NR“ = nicht berichtet,
„NA“ = nicht zutreffend; beide bleiben als Wort erhalten, leere Zellen werden null.

Das Werkzeug ruft nichts aus dem Netz ab: die Datei vorher selbst holen (git clone oder Download) und den Commit nennen.
Ein Thema wird ersetzt, andere Themen in der Zieldatei bleiben (weitere Themen-Dateien nacheinander einlesen).
Bricht ab, ohne zu schreiben, wenn sich der Aufbau ändert (andere Spalten, Hauptversion ≠ 1, unbekannte Einstufung
„EUDR forest definition conform?“, doppelte oder ungültige Item-ID) – dann Werkzeug und Oberfläche anpassen.

Aufruf:
  python3 werkzeuge/eudr_geodatenkatalog.py <pfad-zur-tsv> [--commit <sha>] [--zitat <Zitiervorschlag>]
                                            [--abgerufen JJJJ-MM-TT] [--ziel <json>]
"""
import argparse
import csv
import datetime
import json
import re
import sys
from pathlib import Path

ZIEL = Path(__file__).resolve().parent.parent / 'app/api/module/containerimport/geodatenkatalog.json'
QUELLE = {
    'name': 'GEOS-EUDR: A curated metadatabase for supporting EUDR supply chain monitoring',
    'url': 'https://github.com/GEOS-EUDR-RepoHub/Metadatabase-Geodata-EUDR',
    'lizenz': 'MIT', 'lizenzdatei': 'geodatenkatalog-LIZENZ.txt',
    'urheber': 'Thünen-Institut, GEOS-EUDR: Juliana Freitas Beyer, Margret Köthke, Melvin Lippe',
}
THEMEN = {'ForestCover_TreeExtent': 'Wald und Baumbedeckung (Forest/Tree Cover)'}   # sonst bleibt der Name aus der Datei
# Spalten der Hauptversion 1 in dieser Reihenfolge → Schlüssel im Katalog (None = nicht übernommen)
SPALTEN = [
    ('Item-ID', 'id'), ('Dataset Name and Abbreviation', 'name'), ('Data Producer / Responsible Organization', 'hersteller'),
    ('Primary Publication / Citation', 'zitat'), ('Link to Publication/Technical Report', 'link_veroeffentlichung'),
    ('Repository Link (GEE)', 'link_gee'), ('Repository Link (Other)', 'link_andere'), ('Mapped Classes / Class Definitions', 'klassen'),
    ('Forest/Tree Cover Definition (Thresholds: Height; Minimum area; Canopy cover)', 'walddefinition'),
    ('EUDR forest definition conform?', 'eudrKonform'), ('Extent (Global / Regional / National)', 'ausdehnung'),
    ('Spatial Resolution (m)', 'aufloesungM'), ('Start Year', 'vonJahr'), ('End Year', 'bisJahr'), ('Temporal Resolution', 'zeitlich'),
    ('Sensor/Primary Data Source', 'sensor'), ('Input Metric/Indices/Features', None),
    ('Classification Method(s) (Specific)/Classifier', 'methode'),
    ('Classification (Category) - Supervised ML, Deep Learning, Rule-based/Threshold-based, Expert-driven, Unsupervised, Hybrid, Visual interpretation', 'kategorie'),
    ('Number of Training Samples', None), ('Validation Approach', 'validierung_ansatz'),
    ('Reference Dataset for Validation (Data Name and Period)', 'validierung_referenz'),
    ('Number of Testing and/or Validation Samples', 'validierung_stichproben'), ('Overall Thematic Accuracy (OA)', 'genauigkeit_oa'),
    ("Producer's and User's Accuracy (target class)", 'genauigkeit_paUa'), ('Other Accuracy Metric(s)', 'genauigkeit_weitere'),
    ('Additional Accuracy Information', 'genauigkeit_zusatz'), ('Reported limitations', 'grenzen'),
]
KONFORM = {'yes': 'ja', 'no': 'nein', 'no/unclear': 'nein_unklar', 'unclear': 'unklar', 'partly': 'teilweise', 'partially': 'teilweise',
           'partial': 'teilweise', 'nr': 'nicht_berichtet', '': 'nicht_berichtet', 'na': 'nicht_zutreffend'}
DATEINAME = re.compile(r'^(?P<thema>[A-Za-z][A-Za-z0-9_]*?)_Geos[A-Za-z]+_Thuenen_v(?P<haupt>\d+)\.(?P<neben>\d+)\.(?:tsv|csv)$')
URL = re.compile(r'https?://[^\s|]+')


class Abbruch(Exception):
    """Die Datei passt nicht zum erwarteten Aufbau – nichts wird geschrieben."""


def text(roh):
    """Zelle als Text: Tabulatoren und Mehrfach-Leerzeichen weg, Aufzählungspunkte je auf eine eigene Zeile; leer → None."""
    t = re.sub(r'[ \t\r]+', ' ', roh.replace('\r\n', '\n')).strip()
    t = re.sub(r'\s*•\s*', '\n• ', t).strip()
    return t or None


def verweise(roh):
    """Verweise einer Zelle → [{text, url}]; text ist die Beschriftung vor der Adresse („V2 ->“ → „V2“), Rest am Ende hängt an der letzten."""
    t = text(roh) or ''
    liste, vorher = [], 0
    for m in URL.finditer(t):
        url = m.group(0).rstrip('.,;')
        liste.append({'text': beschriftung(t[vorher:m.start()]), 'url': url})
        vorher = m.start() + len(url)
    rest = beschriftung(t[vorher:])
    if liste and rest:
        liste[-1]['text'] = f"{liste[-1]['text']} – {rest}" if liste[-1]['text'] else rest
    return liste


def beschriftung(stueck):
    s = re.sub(r'\s*-[\s-]*>\s*$', '', stueck.strip(' |;,.\n')).strip(' |;,.')
    if s.startswith('(') and s.endswith(')') and s.count('(') == 1:
        s = s[1:-1]
    return s.strip() or None


def eintrag(zeile, thema, nr):
    w = {schluessel: text(wert) for (_, schluessel), wert in zip(SPALTEN, zeile) if schluessel}
    if not re.fullmatch(r'[A-Z]{2,6}\d{2,4}', w['id'] or ''):
        raise Abbruch(f'Zeile {nr}: ungültige Item-ID {w["id"]!r}')
    konform = (w['eudrKonform'] or '').lower()
    if konform not in KONFORM:
        raise Abbruch(f'{w["id"]}: unbekannte Einstufung „EUDR forest definition conform?“ = {w["eudrKonform"]!r} – Werkzeug und Oberfläche anpassen')
    name, hinweis = w['name'] or '', None
    m = re.fullmatch(r'(.*?)\s*\[(.+)\]', name, re.S)   # FNF17: lange Anmerkung in eckigen Klammern hinter dem Namen
    if m:
        name, hinweis = m.group(1), m.group(2).strip()
    return {
        'id': w['id'], 'thema': thema, 'name': name, 'hinweis': hinweis, 'hersteller': w['hersteller'], 'zitat': w['zitat'],
        'links': {'veroeffentlichung': verweise(zeile[4]), 'gee': verweise(zeile[5]), 'andere': verweise(zeile[6])},
        'klassen': w['klassen'], 'walddefinition': w['walddefinition'], 'eudrKonform': KONFORM[konform], 'ausdehnung': w['ausdehnung'],
        'aufloesungM': w['aufloesungM'], 'vonJahr': w['vonJahr'], 'bisJahr': w['bisJahr'], 'zeitlich': w['zeitlich'], 'sensor': w['sensor'],
        'methode': w['methode'], 'kategorie': w['kategorie'],
        'validierung': {'ansatz': w['validierung_ansatz'], 'referenz': w['validierung_referenz'], 'stichproben': w['validierung_stichproben']},
        'genauigkeit': {'oa': w['genauigkeit_oa'], 'paUa': w['genauigkeit_paUa'], 'weitere': w['genauigkeit_weitere'], 'zusatz': w['genauigkeit_zusatz']},
        'grenzen': w['grenzen'],
    }


def lesen(pfad):
    """Tabelle eines Themas → (Thema mit Version, Einträge). Wirft Abbruch bei abweichendem Aufbau."""
    m = DATEINAME.match(pfad.name)
    if not m:
        raise Abbruch(f'Dateiname {pfad.name!r} folgt nicht dem Muster [Thema]_GeosEUDR_Thuenen_vX.Y.tsv')
    if m['haupt'] != '1':
        raise Abbruch(f'Hauptversion v{m["haupt"]}.{m["neben"]}: neuer Aufbau – Spalten prüfen und das Werkzeug anpassen')
    roh = pfad.read_text(encoding='utf-8-sig')
    zeilen = list(csv.reader(roh.splitlines(), delimiter='\t' if '\t' in roh.split('\n', 1)[0] else ','))
    kopf = [re.sub(r'\s+', ' ', k).strip() for k in zeilen[0]] if zeilen else []
    erwartet = [k for k, _ in SPALTEN]
    if kopf != erwartet:
        fehlt, neu = [k for k in erwartet if k not in kopf], [k for k in kopf if k not in erwartet]
        raise Abbruch('Spalten passen nicht zur Hauptversion 1' + (f'; fehlt: {fehlt}' if fehlt else '') + (f'; neu: {neu}' if neu else '')
                      + ('' if fehlt or neu else '; Reihenfolge geändert'))
    eintraege, gesehen = [], set()
    for nr, zeile in enumerate(zeilen[1:], start=2):
        if not any(z.strip() for z in zeile):
            continue
        if len(zeile) != len(SPALTEN):
            raise Abbruch(f'Zeile {nr}: {len(zeile)} statt {len(SPALTEN)} Zellen')
        e = eintrag(zeile, m['thema'], nr)
        if e['id'] in gesehen:
            raise Abbruch(f'Item-ID {e["id"]} kommt doppelt vor')
        gesehen.add(e['id']); eintraege.append(e)
    if not eintraege:
        raise Abbruch('keine Einträge in der Datei')
    thema = {'id': m['thema'], 'name': THEMEN.get(m['thema'], m['thema'].replace('_', ' ')), 'version': f'{m["haupt"]}.{m["neben"]}',
             'datei': pfad.name, 'eintraege': len(eintraege)}
    return thema, eintraege


def main(argv=None):
    a = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    a.add_argument('tabelle', type=Path)
    a.add_argument('--commit', default='', help='Commit der Quelle (git log -1 --format=%%h im Klon)')
    a.add_argument('--zitat', default='', help='Zitiervorschlag aus dem README der Quelle (Pflicht für ein neues Thema)')
    a.add_argument('--abgerufen', default=datetime.date.today().isoformat())
    a.add_argument('--ziel', type=Path, default=ZIEL)
    o = a.parse_args(argv)
    try:
        if not re.fullmatch(r'[0-9a-f]{0,40}', o.commit):
            raise Abbruch('--commit: nur der Hex-Wert des Commits')
        datetime.date.fromisoformat(o.abgerufen)
        thema, neu = lesen(o.tabelle)
        alt = json.loads(o.ziel.read_text(encoding='utf-8')) if o.ziel.exists() else {'themen': [], 'eintraege': []}
        vorher = next((t for t in alt['themen'] if t['id'] == thema['id']), {})
        thema.update(quelleCommit=o.commit or None, abgerufen=o.abgerufen, zitiervorschlag=o.zitat or vorher.get('zitiervorschlag'))
        if not thema['zitiervorschlag']:
            raise Abbruch('Zitiervorschlag fehlt: --zitat mit dem Text aus „Suggested Citation“ im README der Quelle angeben')
        andere = [e for e in alt['eintraege'] if e['thema'] != thema['id']]
        doppelt = {e['id'] for e in andere} & {e['id'] for e in neu}
        if doppelt:
            raise Abbruch(f'Item-IDs schon in einem anderen Thema: {sorted(doppelt)}')
    except (Abbruch, OSError, ValueError, json.JSONDecodeError, csv.Error) as f:
        print(f'Abbruch, nichts geschrieben: {f}', file=sys.stderr)
        return 1
    katalog = {'schema': 1, 'quelle': QUELLE,
               'themen': sorted([t for t in alt['themen'] if t['id'] != thema['id']] + [thema], key=lambda t: t['id']),
               'eintraege': sorted(andere + neu, key=lambda e: e['id'])}
    o.ziel.write_text(json.dumps(katalog, ensure_ascii=False, indent=1) + '\n', encoding='utf-8')
    print(f'{o.ziel}: Thema {thema["id"]} v{thema["version"]} mit {len(neu)} Einträgen, insgesamt {len(katalog["eintraege"])}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
