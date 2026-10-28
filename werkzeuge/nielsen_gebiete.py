#!/usr/bin/env python3
"""Nielsen-Gebiete für die CRM-Karte (app/module/crm/nielsen.json) aus den Bundesländern von Natural Earth erzeugen.

Nielsen-Gebiete sind Zusammenfassungen von Bundesländern (Einteilung der Handelsforschung, z. B. NielsenIQ
„Universen“): I Hamburg, Bremen, Schleswig-Holstein, Niedersachsen · II Nordrhein-Westfalen · IIIa Hessen,
Rheinland-Pfalz, Saarland · IIIb Baden-Württemberg · IV Bayern · V Berlin · VI Mecklenburg-Vorpommern, Brandenburg,
Sachsen-Anhalt · VII Thüringen, Sachsen.

Grenzen: Natural Earth 1:10 Mio. „admin 1“ (gemeinfrei), zusammengefasst und vereinfacht (etwa 300 m) – genau genug für
die Übersicht und die Zuordnung der Kunden; direkt an einer Landesgrenze kann ein Kunde im Nachbargebiet landen.
Ergebnis wird eingecheckt (GeoJSON, Koordinaten auf 4 Nachkommastellen, je Gebiet Beschriftungspunkt und Rahmen).

Aufruf (einmalig bzw. bei neuer Natural-Earth-Fassung; braucht shapely):
  curl -LO https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_1_states_provinces.geojson
  python3 werkzeuge/nielsen_gebiete.py ne_10m_admin_1_states_provinces.geojson
"""
import json
import os
import sys

from shapely.geometry import mapping, shape
from shapely.ops import polylabel, unary_union

GEBIETE = [   # id, Kurzname, Bundesländer (ISO 3166-2)
    ('I', 'Nord', ['DE-HH', 'DE-HB', 'DE-SH', 'DE-NI']),
    ('II', 'Nordrhein-Westfalen', ['DE-NW']),
    ('IIIa', 'Mitte', ['DE-HE', 'DE-RP', 'DE-SL']),
    ('IIIb', 'Baden-Württemberg', ['DE-BW']),
    ('IV', 'Bayern', ['DE-BY']),
    ('V', 'Berlin', ['DE-BE']),
    ('VI', 'Nordost', ['DE-MV', 'DE-BB', 'DE-ST']),
    ('VII', 'Sachsen, Thüringen', ['DE-SN', 'DE-TH']),
]
TOLERANZ = 0.003   # Grad (≈ 300 m)
BESCHRIFTUNG = {'V': (13.40, 52.71)}   # Berlin: Beschriftung knapp nördlich, damit sie die Kundenpunkte der Stadt nicht verdeckt


def runden(geo):
    def r(c):
        if isinstance(c[0], (int, float)):
            return [round(c[0], 4), round(c[1], 4)]
        return [r(x) for x in c]
    return {'type': geo['type'], 'coordinates': r(geo['coordinates'])}


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    with open(sys.argv[1], encoding='utf-8') as f:
        quelle = json.load(f)
    laender = {f['properties'].get('iso_3166_2'): f for f in quelle['features'] if f['properties'].get('adm0_a3') == 'DEU'}
    fehlen = [k for _, _, ks in GEBIETE for k in ks if k not in laender]
    if fehlen:
        sys.exit('Bundesländer fehlen in der Quelle: ' + ', '.join(fehlen))
    features = []
    for gid, kurz, codes in GEBIETE:
        flaeche = unary_union([shape(laender[c]['geometry']).buffer(0) for c in codes]).buffer(0)
        einfach = flaeche.simplify(TOLERANZ, preserve_topology=True)
        groesstes = max(getattr(einfach, 'geoms', [einfach]), key=lambda g: g.area)
        punkt = polylabel(groesstes, tolerance=0.01)
        if gid in BESCHRIFTUNG:
            punkt = type(punkt)(*BESCHRIFTUNG[gid])
        x1, y1, x2, y2 = flaeche.bounds
        features.append({'type': 'Feature', 'id': gid, 'geometry': runden(mapping(einfach)), 'properties': {
            'id': gid, 'name': f'Nielsen {gid}', 'kurz': kurz,
            'laender': [laender[c]['properties']['name'] for c in codes],
            'beschriftung': [round(punkt.x, 4), round(punkt.y, 4)], 'rahmen': [round(x1, 3), round(y1, 3), round(x2, 3), round(y2, 3)]}})
    ziel = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'module', 'crm', 'nielsen.json')
    with open(ziel, 'w', encoding='utf-8') as f:
        json.dump({'type': 'FeatureCollection',
                   'quelle': 'Nielsen-Gebiete aus Bundesländern; Grenzen: Natural Earth 1:10 Mio. (gemeinfrei), vereinfacht – werkzeuge/nielsen_gebiete.py',
                   'features': features}, f, ensure_ascii=False, separators=(',', ':'))
    print(f'geschrieben: app/module/crm/nielsen.json ({os.path.getsize(ziel) // 1024} KB, {len(features)} Gebiete)', file=sys.stderr)


if __name__ == '__main__':
    main()
