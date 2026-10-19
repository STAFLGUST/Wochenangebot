#!/usr/bin/env python3
"""Baut die Landkarte für die Auswertung (app/assets/karte.json) aus Natural Earth (gemeinfrei),
weitergegeben als TopoJSON im npm-Paket „world-atlas“ (ISC).

Europa (für die Ansicht Deutschland/Europa) in mittlerer Auflösung 1:50 Mio., die übrige Welt in 1:110 Mio.
Projektion: Web-Mercator, 1 Einheit = 0,01 Längengrad (Welt = 36000 Einheiten breit), Ganzzahlen, relative Pfade.

Aufruf (einmalig, Ergebnis wird mit eingecheckt):
  npm pack world-atlas@2.0.2 && tar xzf world-atlas-2.0.2.tgz
  python3 werkzeuge/karte_bauen.py package/countries-50m.json package/countries-110m.json
"""
import json, math, os, sys

SCALE = 100.0            # Einheiten je Längengrad
EUROPA = (-32.0, 27.0, 50.0, 72.0)   # lon_min, lat_min, lon_max, lat_max: hier die feinere Fassung


def proj(lon, lat):
    lat = max(-85.0, min(85.0, lat))
    x = (lon + 180.0) * SCALE
    y = (180.0 - math.degrees(math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)))) * SCALE
    return x, y


def decode(topo):
    t = topo['transform']
    sx, sy = t['scale']; tx, ty = t['translate']
    arcs = []
    for arc in topo['arcs']:
        x = y = 0; pts = []
        for dx, dy in arc:
            x += dx; y += dy
            pts.append((x * sx + tx, y * sy + ty))
        arcs.append(pts)
    return arcs


def ring(arcs, idx):
    pts = []
    for i in idx:
        a = arcs[i] if i >= 0 else list(reversed(arcs[~i]))
        pts.extend(a if not pts else a[1:])
    return pts


def polygons(geom):
    if geom['type'] == 'Polygon': return [geom['arcs']]
    if geom['type'] == 'MultiPolygon': return geom['arcs']
    return []


def bbox(pts):
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return min(xs), min(ys), max(xs), max(ys)


def inside(b, area):
    return not (b[2] < area[0] or b[0] > area[2] or b[3] < area[1] or b[1] > area[3])


def path(pts):
    out = []; last = None
    for lon, lat in pts:
        x, y = proj(lon, lat)
        p = (int(round(x)), int(round(y)))
        if p == last: continue
        out.append(p if last is None else (p[0] - last[0], p[1] - last[1]))
        last = p
    if len(out) < 3: return ''
    first = out[0]
    rest = ' '.join(f'{dx} {dy}' for dx, dy in out[1:])
    return f'M{first[0]} {first[1]}l{rest}z'


def countries(topo, keep):
    arcs = decode(topo)
    res = {}
    for g in topo['objects']['countries']['geometries']:
        cid = str(g.get('id', '')) or g.get('properties', {}).get('name', '')
        parts = []
        for poly in polygons(g):
            rings = [ring(arcs, r) for r in poly]
            if not rings or not rings[0]: continue
            if not keep(bbox(rings[0])): continue
            parts.extend(filter(None, (path(r) for r in rings)))
        if parts: res.setdefault(cid, []).extend(parts)
    return res


def main():
    fine, coarse = sys.argv[1], sys.argv[2]
    tf = json.load(open(fine)); tc = json.load(open(coarse))
    a = countries(tf, lambda b: inside(b, EUROPA))
    b = countries(tc, lambda b: not inside(b, EUROPA))
    merged = {}
    for src in (a, b):
        for k, v in src.items(): merged.setdefault(k, []).extend(v)
    x0, y0 = proj(-180, 85); x1, y1 = proj(180, -60)
    data = {'quelle': 'Natural Earth (gemeinfrei) über world-atlas 2.0.2', 'skala': SCALE,
            'box': [0, int(y0), int(x1 - x0), int(y1 - y0)],
            'laender': [''.join(v) for _, v in sorted(merged.items())]}
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'app', 'assets', 'karte.json')
    with open(out, 'w') as f: json.dump(data, f, separators=(',', ':'))
    print(f'{out}: {os.path.getsize(out) // 1024} KB, {len(merged)} Länder')


if __name__ == '__main__':
    main()
