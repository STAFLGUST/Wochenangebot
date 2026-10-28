#!/usr/bin/env python3
"""Adressverzeichnis für die CRM-Karte aus OpenStreetMap (ODbL): Straße + Hausnummer + PLZ/Ort → Koordinate.

Läuft auf dem Server in einem Container (deploy/adressen-laden.sh) mit pyosmium und schreibt eine SQLite-Datei, die
die Anwendung nur liest (app/api/lib/adressen.php). Keine fremden Dienste beim Nachschlagen: alles bleibt auf dem Server.

  python3 adressen.py quelle.osm.pbf ziel.sqlite      # OpenStreetMap-Auszug (z. B. Deutschland von Geofabrik)
  python3 adressen.py --json eintraege.json ziel.sqlite  # Testdaten (tests/fixtures/karte/adressen.json), ohne pyosmium

Vorgehen (wenig Arbeitsspeicher, auch für ganz Deutschland): 1. Durchlauf – Punkte und Gebäude mit addr:housenumber;
von Gebäuden (Wegen) nur der erste und der mittlere Eckpunkt (gegenüberliegende Ecken: ihr Mittel liegt im Gebäude).
2. Durchlauf – nur diese Eckpunkte. Zwischenstände in einer SQLite-Arbeitsdatei, am Ende kompakt in die Zieldatei.
Adressen an Multipolygon-Relationen (selten) fehlen; dort hilft die Straßen-Genauigkeit.

Schreibweisen werden vereinheitlicht (norm_text, norm_strasse, norm_nr) – dieselben Regeln stehen in
app/api/lib/adressen.php; die gemeinsamen Prüffälle in tests/fixtures/karte/normalisierung.json halten beide gleich.
Format (Tabelle info, format = 1): strassen(id, plz, ort, name, lat, lon, anzahl), adressen(strasse, nr, lat, lon);
Koordinaten als ganze Zahlen (Grad × 100000, etwa 1 m).
"""
import json
import os
import re
import sqlite3
import sys
import time

FORMAT = 1
FAKTOR = 100000
_ZEICHEN = {'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss', 'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e', 'á': 'a', 'à': 'a',
            'â': 'a', 'å': 'a', 'ç': 'c', 'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i', 'ñ': 'n', 'ó': 'o', 'ò': 'o', 'ô': 'o',
            'ø': 'o', 'ú': 'u', 'ù': 'u', 'û': 'u', 'ý': 'y', 'æ': 'ae', 'œ': 'oe', 'ł': 'l', 'š': 's', 'ž': 'z', 'č': 'c'}


def norm_text(s):
    """Kleinbuchstaben, Umlaute ausgeschrieben, nur a–z und 0–9 (für Orte)."""
    s = (s or '').lower()
    s = ''.join(_ZEICHEN.get(c, c) for c in s)
    return re.sub(r'[^a-z0-9]', '', s)


def norm_strasse(s):
    """Wie norm_text, „str.“/„str“ am Wortende wird „strasse“ (Hauptstr. = Hauptstraße = Haupt-Straße)."""
    s = (s or '').lower()
    s = ''.join(_ZEICHEN.get(c, c) for c in s)
    s = re.sub(r'str\.?(?![a-z])', 'strasse', s)
    return re.sub(r'[^a-z0-9]', '', s)


def norm_nr(s):
    """Hausnummer: Kleinbuchstaben ohne Leerzeichen, nur Ziffern, Buchstaben, - und / (12 A → 12a)."""
    return re.sub(r'[^0-9a-z/-]', '', (s or '').lower())


def norm_plz(s):
    s = re.sub(r'\D', '', s or '')
    return s if len(s) == 5 else ''


def nummern(roh):
    """Mehrere Hausnummern an einem Objekt („12;14“, „12, 14“) einzeln; Bereiche („12-14“) bleiben ganz."""
    return [n for n in (norm_nr(t) for t in re.split(r'[;,]', roh or '')) if n]


class Ziel:
    """Arbeitsdatei: Rohdaten sammeln, am Ende Straßen bilden und kompakt in die Zieldatei schreiben."""

    def __init__(self, arbeit):
        if os.path.exists(arbeit):
            os.remove(arbeit)
        self.db = sqlite3.connect(arbeit)
        self.db.executescript('''
            PRAGMA journal_mode = OFF; PRAGMA synchronous = OFF; PRAGMA cache_size = -200000;
            CREATE TABLE roh(plz TEXT, ort TEXT, strasse TEXT, nr TEXT, lat INTEGER, lon INTEGER);
            CREATE TABLE wege(n0 INTEGER, n1 INTEGER, plz TEXT, ort TEXT, strasse TEXT, nr TEXT);
            CREATE TABLE knoten(id INTEGER PRIMARY KEY, lat INTEGER, lon INTEGER);''')
        self.puffer, self.wpuffer, self.kpuffer = [], [], []

    @staticmethod
    def schluessel(tags):
        """(plz, ort, strasse, [nummern]) aus den addr:*-Angaben oder None (ohne Straße bzw. ohne PLZ und Ort)."""
        strasse = norm_strasse(tags.get('addr:street') or tags.get('addr:place') or '')
        plz, ort = norm_plz(tags.get('addr:postcode', '')), norm_text(tags.get('addr:city', ''))
        nrn = nummern(tags.get('addr:housenumber', ''))
        if not strasse or not nrn or not (plz or ort):
            return None
        return plz, ort, strasse, nrn

    def punkt(self, k, lat, lon):
        plz, ort, strasse, nrn = k
        for n in nrn:
            self.puffer.append((plz, ort, strasse, n, round(lat * FAKTOR), round(lon * FAKTOR)))
        if len(self.puffer) > 50000:
            self.db.executemany('INSERT INTO roh VALUES (?,?,?,?,?,?)', self.puffer); self.puffer = []

    def weg(self, k, n0, n1):
        plz, ort, strasse, nrn = k
        for n in nrn:
            self.wpuffer.append((n0, n1, plz, ort, strasse, n))
        if len(self.wpuffer) > 50000:
            self.db.executemany('INSERT INTO wege VALUES (?,?,?,?,?,?)', self.wpuffer); self.wpuffer = []

    def knoten(self, i, lat, lon):
        self.kpuffer.append((i, round(lat * FAKTOR), round(lon * FAKTOR)))
        if len(self.kpuffer) > 50000:
            self.db.executemany('INSERT OR IGNORE INTO knoten VALUES (?,?,?)', self.kpuffer); self.kpuffer = []

    def fertig(self, ziel, quelle):
        db = self.db
        db.executemany('INSERT INTO roh VALUES (?,?,?,?,?,?)', self.puffer)
        db.executemany('INSERT INTO wege VALUES (?,?,?,?,?,?)', self.wpuffer)
        db.executemany('INSERT OR IGNORE INTO knoten VALUES (?,?,?)', self.kpuffer)
        # Gebäude: Mittel aus erstem und mittlerem Eckpunkt
        db.execute('''INSERT INTO roh SELECT w.plz, w.ort, w.strasse, w.nr, (a.lat + b.lat) / 2, (a.lon + b.lon) / 2
                      FROM wege w JOIN knoten a ON a.id = w.n0 JOIN knoten b ON b.id = w.n1''')
        db.executescript('''
            DROP TABLE wege; DROP TABLE knoten;
            CREATE TABLE info(schluessel TEXT PRIMARY KEY, wert TEXT);
            CREATE TABLE strassen(id INTEGER PRIMARY KEY, plz TEXT NOT NULL, ort TEXT NOT NULL, name TEXT NOT NULL,
                                  lat INTEGER NOT NULL, lon INTEGER NOT NULL, anzahl INTEGER NOT NULL);
            INSERT INTO strassen(plz, ort, name, lat, lon, anzahl)
                SELECT plz, ort, strasse, CAST(round(avg(lat)) AS INTEGER), CAST(round(avg(lon)) AS INTEGER), count(*)
                FROM roh GROUP BY plz, ort, strasse ORDER BY plz, ort, strasse;
            CREATE UNIQUE INDEX strassen_genau ON strassen(plz, ort, name);
            CREATE TABLE adressen(strasse INTEGER NOT NULL, nr TEXT NOT NULL, lat INTEGER NOT NULL, lon INTEGER NOT NULL,
                                  PRIMARY KEY(strasse, nr)) WITHOUT ROWID;
            INSERT OR IGNORE INTO adressen SELECT s.id, r.nr, r.lat, r.lon
                FROM roh r JOIN strassen s ON s.plz = r.plz AND s.ort = r.ort AND s.name = r.strasse ORDER BY s.id, r.nr;
            DROP TABLE roh; DROP INDEX strassen_genau;
            CREATE INDEX strassen_plz ON strassen(plz, name);
            CREATE INDEX strassen_ort ON strassen(ort, name);''')
        n_adr = db.execute('SELECT count(*) FROM adressen').fetchone()[0]
        n_str = db.execute('SELECT count(*) FROM strassen').fetchone()[0]
        db.executemany('INSERT INTO info VALUES (?, ?)', [('format', str(FORMAT)), ('quelle', quelle), ('adressen', str(n_adr)),
                       ('strassen', str(n_str)), ('erzeugt', time.strftime('%Y-%m-%d', time.gmtime()))])
        db.commit()
        if os.path.exists(ziel):
            os.remove(ziel)
        db.execute('VACUUM INTO ?', (ziel,))
        db.close()
        return n_adr, n_str


def aus_osm(quelle, z):
    """Zwei Durchläufe über die OSM-Datei (pyosmium); Filter laufen in C++, Python sieht nur Adressen und deren Eckpunkte."""
    import osmium   # nur hier nötig (Container auf dem Server; Tests mit --json brauchen es nicht)
    ids = osmium.IdTracker()
    n = 0
    adr = osmium.filter.KeyFilter('addr:housenumber')
    for o in osmium.FileProcessor(quelle, osmium.osm.NODE | osmium.osm.WAY).with_filter(adr):
        k = Ziel.schluessel(o.tags)
        if k is None:
            continue
        if o.is_node():
            if o.location.valid():
                z.punkt(k, o.location.lat, o.location.lon)
        elif len(o.nodes) >= 1:
            n0, n1 = o.nodes[0].ref, o.nodes[len(o.nodes) // 2].ref
            ids.add_node(n0); ids.add_node(n1)
            z.weg(k, n0, n1)
        n += 1
        if n % 1000000 == 0:
            print(f'  {n // 1000000} Mio. Adressen gelesen', file=sys.stderr, flush=True)
    for o in osmium.FileProcessor(quelle, osmium.osm.NODE).with_filter(ids.id_filter()):
        if o.location.valid():
            z.knoten(o.id, o.location.lat, o.location.lon)


def aus_json(quelle, z):
    """Testdaten: Liste von {strasse, nr, plz, ort, lat, lon} (wie addr:* in OpenStreetMap)."""
    with open(quelle, encoding='utf-8') as f:
        for e in json.load(f)['adressen']:
            k = Ziel.schluessel({'addr:street': e['strasse'], 'addr:housenumber': e['nr'], 'addr:postcode': e.get('plz', ''), 'addr:city': e.get('ort', '')})
            if k:
                z.punkt(k, e['lat'], e['lon'])


def main(argv):
    json_modus = argv[:1] == ['--json']
    if json_modus:
        argv = argv[1:]
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    quelle, ziel = argv
    z = Ziel(ziel + '.arbeit')
    try:
        (aus_json if json_modus else aus_osm)(quelle, z)
        n_adr, n_str = z.fertig(ziel, os.path.basename(quelle))
    finally:
        if os.path.exists(ziel + '.arbeit'):
            os.remove(ziel + '.arbeit')
    print(f'{n_adr} Adressen an {n_str} Straßen → {ziel}', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
