#!/usr/bin/env python3
"""Kleiner Ausschnitt aus einer Protomaps-Basiskarte (PMTiles, OpenStreetMap-Daten, ODbL) – für Testdaten und lokale
Vorschau der Detailkarte. Im Betrieb lädt deploy/karte-laden.sh die ganze Karte mit dem offiziellen Werkzeug go-pmtiles.

Liest nur die benötigten Bytes (HTTP-Range mit curl, oder eine lokale Datei) und schreibt eine neue PMTiles-Datei. Mehrere Bereiche mit eigener
Zoomstufe sind möglich, z. B. Deutschland grob und ein Stadtteil fein:

  python3 werkzeuge/karte_auszug.py https://build.protomaps.com/20261026.pmtiles ziel.pmtiles \\
      --bereich 5.5,47.2,15.5,55.1:0-7 --bereich 9.98,53.54,10.02,53.56:8-15

Benötigt: pip install pmtiles (Bibliothek von Protomaps).
"""
import argparse
import gzip
import json
import math
import subprocess
import sys

from pmtiles.tile import Compression, deserialize_directory, deserialize_header, find_tile, zxy_to_tileid
from pmtiles.writer import Writer


def lade(url, start, laenge):
    if url.startswith(('http://', 'https://')):   # Range-Abruf mit curl (wie ein üblicher Download)
        daten = subprocess.run(['curl', '-sSf', '--max-time', '300', '-r', f'{start}-{start + laenge - 1}', url],
                               check=True, capture_output=True).stdout
    else:                                          # lokale Datei
        with open(url, 'rb') as f:
            f.seek(start); daten = f.read(laenge)
    if len(daten) != laenge:
        raise SystemExit(f'Unerwartete Länge {len(daten)} statt {laenge} (Server ohne Range-Unterstützung?)')
    return daten


def entpacken(daten, art):
    return gzip.decompress(daten) if art == Compression.GZIP else daten


def kacheln(lon1, lat1, lon2, lat2, z):
    n = 2 ** z

    def xy(lon, lat):
        lat = max(-85.0511, min(85.0511, lat))
        x = int((lon + 180.0) / 360.0 * n)
        y = int((1.0 - math.log(math.tan(math.radians(lat)) + 1 / math.cos(math.radians(lat))) / math.pi) / 2.0 * n)
        return min(n - 1, max(0, x)), min(n - 1, max(0, y))
    x1, y1 = xy(lon1, lat2)
    x2, y2 = xy(lon2, lat1)
    for x in range(x1, x2 + 1):
        for y in range(y1, y2 + 1):
            yield z, x, y


def main():
    a = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    a.add_argument('quelle'); a.add_argument('ziel')
    a.add_argument('--bereich', action='append', required=True, help='lon1,lat1,lon2,lat2:zmin-zmax')
    o = a.parse_args()
    kopf = deserialize_header(lade(o.quelle, 0, 127))
    art = kopf['internal_compression']
    wurzel = deserialize_directory(lade(o.quelle, kopf['root_offset'], kopf['root_length']))   # entpackt selbst (gzip)
    blaetter = {}

    def eintrag(tid):
        verz = wurzel
        for _ in range(4):
            e = find_tile(verz, tid)
            if e is None:
                return None
            if e.run_length > 0:
                return e
            key = (e.offset, e.length)
            if key not in blaetter:
                blaetter[key] = deserialize_directory(lade(o.quelle, kopf['leaf_directory_offset'] + e.offset, e.length))
            verz = blaetter[key]
        return None

    gesucht = {}
    zmin_alle, zmax_alle, box = 99, 0, [180, 90, -180, -90]
    for b in o.bereich:
        flaeche, zooms = b.split(':')
        lon1, lat1, lon2, lat2 = (float(v) for v in flaeche.split(','))
        z1, z2 = (int(v) for v in zooms.split('-'))
        zmin_alle, zmax_alle = min(zmin_alle, z1), max(zmax_alle, z2)
        box = [min(box[0], lon1), min(box[1], lat1), max(box[2], lon2), max(box[3], lat2)]
        for z in range(z1, z2 + 1):
            for zz, x, y in kacheln(lon1, lat1, lon2, lat2, z):
                tid = zxy_to_tileid(zz, x, y)
                e = eintrag(tid)
                if e is not None:
                    gesucht[tid] = (e.offset, e.length)
    # Zusammenhängende Bereiche der Datei gemeinsam laden (wenige große statt vieler kleiner Anfragen)
    stuecke = sorted(set(gesucht.values()))
    puffer, laufend = {}, []
    for off, ln in stuecke:
        if laufend and off - (laufend[-1][0] + laufend[-1][1]) < 65536 and off + ln - laufend[0][0] < 16 * 2 ** 20:
            laufend.append((off, ln)); continue
        if laufend:
            puffer[(laufend[0][0], laufend[-1][0] + laufend[-1][1])] = None
        laufend = [(off, ln)]
    if laufend:
        puffer[(laufend[0][0], laufend[-1][0] + laufend[-1][1])] = None
    daten = {}
    for (anf, ende) in puffer:
        block = lade(o.quelle, kopf['tile_data_offset'] + anf, ende - anf)
        for off, ln in stuecke:
            if anf <= off and off + ln <= ende:
                daten[(off, ln)] = block[off - anf:off - anf + ln]
    meta_roh = entpacken(lade(o.quelle, kopf['metadata_offset'], kopf['metadata_length']), art)
    meta = json.loads(meta_roh)
    meta['description'] = 'Ausschnitt für Tests und Vorschau (werkzeuge/karte_auszug.py) aus: ' + o.quelle.rsplit('/', 1)[-1]
    with open(o.ziel, 'wb') as f:
        w = Writer(f)
        for tid in sorted(gesucht):
            w.write_tile(tid, daten[gesucht[tid]])
        w.finalize({
            'tile_type': kopf['tile_type'], 'tile_compression': kopf['tile_compression'],
            'min_zoom': zmin_alle, 'max_zoom': zmax_alle,
            'min_lon_e7': int(box[0] * 1e7), 'min_lat_e7': int(box[1] * 1e7), 'max_lon_e7': int(box[2] * 1e7), 'max_lat_e7': int(box[3] * 1e7),
            'center_zoom': zmax_alle, 'center_lon_e7': int((box[0] + box[2]) / 2 * 1e7), 'center_lat_e7': int((box[1] + box[3]) / 2 * 1e7),
        }, meta)
    groesse = sum(ln for _, ln in set(gesucht.values()))
    print(f'{len(gesucht)} Kacheln, {groesse / 1e6:.1f} MB Kacheldaten, {len(puffer)} Abrufe → {o.ziel}', file=sys.stderr)


if __name__ == '__main__':
    main()
