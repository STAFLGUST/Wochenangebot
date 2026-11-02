"""Controlling · Umsatzdaten der Warenwirtschaft: Import über die Importzentrale (in Teilen) und Umsatzauswertung.

Geprüft: Registrierung (Eigentümer Controlling, Recht controlling.umsatz_importieren, große Datei in Teilen);
Rechte serverseitig (GR-103): Import nur mit Recht, Auswertung nur mit controlling.umsatz_sehen, Einkaufswerte und DB nur
mit controlling.umsatz_ek und bestand.einkaufspreise (GR-008, je eines allein genügt nicht; verlassen sonst den Server nicht); Vorschau je Monat (neu, geändert, unverändert, entfällt),
Hinweise (Zeitraum, Belegköpfe, ohne Berechnung, unbekannte Kunden/Artikel, Rückgang); Teile: Prüfsumme (unabhängig in
Python berechnet = Server = Browser), Sortierung, Werte, fremder Mitarbeiter, fehlender Teil, veralteter Stand 409;
Übernahme: nur geänderte Monate, dieselbe Datei erneut ändert nichts, Randmonate nur im Zeitraum der Datei ersetzt (übrige
Tage bleiben), Monat ohne Umsätze im Zeitraum entfällt, Zwischenablage aufgeräumt (auch alte Reste), Importverlauf,
Protokoll ohne Beträge; Auswertung: Summen je Vertreter, Kundengruppe, Kunde, Artikelgruppe, Fleischart, Artikel, Monat,
Quartal, Jahr, KW gegen unabhängig gerechnete Werte, Filter (auch „ohne“), Vorjahr (im laufenden Monat bis zum gleichen
Tag), ungültige Anfragen; Bestellpausen (Stammkunden mit ungewöhnlich langer Pause, unabhängig gerechnet, Filter, Stichtag, Rechte); Pop-up-Details (controlling_umsatz_detail): Kunden und Artikel mit letztem Kauf, Preisspiegel (Ø Preis aller Kunden je Artikel), Liefertage des
Kunden, Vorjahr, Filter der Seite, Rechte; Oberfläche: Import im Browser mit dem Leser des Controllings (Fortschritt,
Ergebnis), Reiter Auswertung zuerst, Leiste, Kennzahlen, Rangliste, Pop-ups (Vertreter → Kunde → zurück, Suche, Lieferungen,
„Als Filter übernehmen“), Suche öffnet Pop-ups, Filter-Pop-up, alle Spalten mit Sortierung, CSV, Monatsmeldung weiter
erreichbar; 1280 und 390 px (Pop-up als Blatt von unten), hell und dunkel, keine JavaScript-Fehler. Nur synthetische Testdaten.

Testdaten: Vertreter V1 Vera Vertrieb, V2 Viktor Verkauf; Kundengruppen 10 Gastronomie, 20 Großhandel; Artikelgruppen 100 Rind
und Kalb, 200 Schwein. Kunden 2000001 Gasthaus Eiche (V1, 10), 2000002 Handel Nord (V1, 20), 2000003 Kantine Süd (V2, 10),
2000004 Imbiss Ohne (ohne Vertreter und Gruppe), 2000005 ohne Stammsatz; Artikel 40100 Rinderhüfte, 40200 Schweinenacken,
40300 Kalbsrücken, 40400 ohne Stammsatz, 1 E2-Kiste (Leergut, ohne Berechnung). Positionen zufällig mit festem Startwert
(positionen(): rund 4 % Gutschriften, 15 % ohne EK, 2 % doppelt). Importe nacheinander: POS_A 02.01.2025–30.10.2026; POS_B
ersetzt 10.–20.10.2026 (Menge ×2, ohne 2000005); POS_C ersetzt März 2025 durch ein Drittel, April 2025 entfällt; POS_E ersetzt
Juni 2026 (2000004 nur eine Gutschrift = verloren, 2000003 nur jede vierte Position); im Browser POS_D 01.09.–30.10.2026
(Menge ×1,5). POS_JETZT ist jeweils der gespeicherte Stand – Grundlage aller unabhängigen Rechnungen (erwartet(), letzte(),
kaeufer(), abc_soll()). Nutzer: ina (importieren), sam (ansehen), eka (beide EK-Rechte), ede und bea (je nur eines), olaf (ohne).
"""
import datetime as dt
import hashlib
import json
import os
import random
import re
import urllib.parse

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import BASE, SH, WORK, storage_raw, storage_sqlite, storage_write

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    """Prüfung festhalten und als PASS/FAIL ausgeben (bei FAIL mit Ist-Wert)."""
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:500]) if i and not c else ''))


def dokument(name):
    """Gespeichertes Dokument direkt aus der Speicherschicht (None = fehlt)."""
    raw = storage_raw(name)
    if not raw:
        return None
    if raw.startswith('<?php'):
        raw = raw.split('\n', 1)[1]
    return json.loads(raw)


# ── Stammdaten (synthetisch) ──
storage_write('vertreter', {'rev': 1, 'groups': [{'nr': 'V1', 'name': 'Vera Vertrieb', 'kurz': 'VV'}, {'nr': 'V2', 'name': 'Viktor Verkauf', 'kurz': 'VK'}]})
storage_write('kundengruppen', {'rev': 1, 'groups': [{'nr': '10', 'name': 'Gastronomie', 'klasse': 'A'}, {'nr': '20', 'name': 'Großhandel'}]})
storage_write('vkgruppen', {'rev': 1, 'groups': [{'nr': '100', 'name': 'Rind und Kalb'}, {'nr': '200', 'name': 'Schwein'}]})
KUNDEN = {'2000001': ('Gasthaus Eiche', 'V1', '10'), '2000002': ('Handel Nord', 'V1', '20'), '2000003': ('Kantine Süd', 'V2', '10'), '2000004': ('Imbiss Ohne', '', '')}
storage_write('kunden', {'rev': 1, 'customers': [{'id': 'k' + nr, 'nr': nr, 'firma': f, 'vertreter': v, 'gruppe': g, 'plz': '20095', 'ort': 'Hamburg', 'active': True, 'angebote': []}
                                                  for nr, (f, v, g) in KUNDEN.items()]})
ARTIKEL = {'40100': ('Rinderhüfte', 'Rind', '100'), '40200': ('Schweinenacken', 'Schwein', '200'), '40300': ('Kalbsrücken', 'Kalb', '100'), '1': ('E2-Kiste', 'Sonstiges', '')}
storage_write('stammdaten', {'rev': 1, 'articles': [dict({'code': c, 'name': n, 'category': k, 'origin': None, 'condition': 'frisch'}, **({'vkGruppe': g} if g else {}))
                                                     for c, (n, k, g) in ARTIKEL.items()]})
INFO_K = {nr: {'vertreter': v or '_', 'kundengruppe': g or '_'} for nr, (_, v, g) in KUNDEN.items()}
INFO_K['2000005'] = {'vertreter': '_', 'kundengruppe': '_'}                    # nicht in den Kundenstammdaten
INFO_A = {c: {'vkgruppe': g or '_', 'fleischart': k} for c, (_, k, g) in ARTIKEL.items()}
INFO_A['40400'] = {'vkgruppe': '_', 'fleischart': '_'}                         # nicht in den Artikelstammdaten

# ── Synthetische Kundenumsatztabelle: Positionen (Datum, Kunde, Artikel, Kolli, Menge, Preis, Betrag, EK) ──
rnd = random.Random(20261101)


def de(v, stellen):
    """Zahl im deutschen Format wie die Warenwirtschaft („1.347,25“)"""
    s = f'{abs(v):,.{stellen}f}'.replace(',', 'X').replace('.', ',').replace('X', '.')
    return ('-' if v < 0 else '') + s


def positionen(von, bis, faktor=1.0, ohne_kunden=()):
    """Zufällige Positionen (Datum, Kunde, Artikel, Kolli, Menge, Preis, Betrag, EK) an Werktagen; Gutschriften, ohne EK, doppelt, Leergut."""
    out = []
    d = von
    while d <= bis:
        if d.weekday() < 5 and rnd.random() < 0.6:
            for k in [k for k in ('2000001', '2000002', '2000003', '2000004', '2000005') if k not in ohne_kunden]:
                for a in ('40100', '40200', '40300', '40400'):
                    if rnd.random() < 0.35:
                        menge = round(rnd.uniform(5, 300) * faktor, 3)
                        if rnd.random() < 0.04:
                            menge = -menge                                      # Gutschrift
                        preis = round(rnd.uniform(3, 18), 2)
                        betrag = round(menge * preis, 2)
                        ek = round(preis * rnd.uniform(0.7, 0.95), 2) if rnd.random() < 0.85 else None
                        p = (d, k, a, rnd.randint(1, 30), menge, preis, betrag, ek)
                        out.append(p)
                        if rnd.random() < 0.02:
                            out.append(p)                                       # zwei gleiche Positionen an einem Tag
                if rnd.random() < 0.3:
                    out.append((d, k, '1', None, float(rnd.randint(1, 20)), None, None, None))   # Leergut ohne Berechnung
        d += dt.timedelta(days=1)
    return out


def csv_text(pos, kaputt=0):
    """Kundenumsatztabelle wie aus der Warenwirtschaft (Belegköpfe, Leerzeile, kaputt = Zeilen mit ungültigem Datum)."""
    z = ['"Kunde";"Datum";"Artikel";"Kolli";"Menge";"Preis";"Gesamtbetrag";"EKPreis"']
    for d, k, a, ko, m, p, b, ek in pos:
        datum = d.strftime('%d.%m.%Y')
        if rnd.random() < 0.3:
            z.append(f'"{k}";"{datum}";;;;;;')                                   # Belegkopf ohne Artikel
        z.append(';'.join(f'"{x}"' if x != '' else '' for x in (k, datum, a, '' if ko is None else str(ko), de(m, 3), '' if p is None else de(p, 2),
                                                                  '' if b is None else de(b, 2), '' if ek is None else de(ek, 2))))
    for i in range(kaputt):
        z.insert(3 + i, '"2000001";"31.02.2026";"40100";"1";"1,000";"1,00";"1,00";"1,00"')
    z.insert(5, '')                                                              # Leerzeile
    return '\r\n'.join(z) + '\r\n'


def cent(v):
    """Euro → Cent (gerundet)."""
    return int(round(v * 100))


def milli(v):
    """Menge → Tausendstel (gerundet)."""
    return int(round(v * 1000))


def lesen(pos):
    """Unabhängige Zusammenfassung wie der Leser (umsatz-import.js): je Monat sortierte Zeilen, Prüfsumme, Kennzahlen."""
    summen = {}
    for d, k, a, ko, m, p, b, ek in pos:
        ber = 1 if b is not None else 0
        s = summen.setdefault((d.strftime('%Y-%m'), d.day, k, a, ber), [0, 0, 0, 0, 0, 0])
        s[0] += ko or 0; s[1] += milli(m); s[5] += 1
        if ber:
            s[2] += cent(b)
            if ek is not None:
                s[3] += int(round(milli(m) * int(round(ek * 10000)) / 100000)); s[4] += cent(b)
    monate = {}
    for (mo, t, k, a, ber), s in summen.items():
        monate.setdefault(mo, []).append([t, k, a, s[0], s[1], s[2], s[3], s[4], s[5], ber])
    daten = {'version': 1, 'zeitraum': {'von': min(p[0] for p in pos).isoformat(), 'bis': max(p[0] for p in pos).isoformat()}, 'monate': {},
             'kunden': sorted({p[1] for p in pos}), 'artikel': sorted({p[2] for p in pos}), 'datei': {'zeilen': len(pos), 'ohneArtikel': 0, 'leer': 0}}
    teile = {}
    for mo in sorted(monate):
        z = sorted(monate[mo], key=lambda r: (r[0], r[1], r[2], r[9]))
        h = hashlib.sha256(json.dumps(z, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        daten['monate'][mo] = {'hash': h, 'zeilen': len(z), 'pos': sum(r[8] for r in z if r[9]), 'umsatz': sum(r[5] for r in z if r[9]),
                               'menge': sum(r[4] for r in z if r[9]), 'posOhne': sum(r[8] for r in z if not r[9])}
        teile[mo] = {'monat': mo, 'hash': h, 'zeilen': z}
    return daten, teile


def erwartet(pos, von, bis, dim, filt=None, bis_tag=None):
    """Umsatz (Cent) je Gliederung aus den Positionen gerechnet (unabhängig vom Server)"""
    out = {}
    for d, k, a, ko, m, p, b, ek in pos:
        mo = d.strftime('%Y-%m')
        if b is None or mo < von or mo > bis or (bis_tag and mo == bis and d.day > bis_tag):
            continue
        merk = {'kunde': k, 'artikel': a, **INFO_K[k], **INFO_A[a]}
        if filt and any(merk[f] not in w for f, w in filt.items()):
            continue
        key = {'monat': mo, 'jahr': mo[:4], 'quartal': f'{mo[:4]}-Q{(d.month - 1) // 3 + 1}', 'kw': f'{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}'}.get(dim) or merk[dim]
        out[key] = out.get(key, 0) + cent(b)
    return out


POS_A = positionen(dt.date(2025, 1, 2), dt.date(2026, 10, 30))
# ── Mitarbeiter ──
A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
NUTZER = (('ina', 'Ina Import', 'viewer', 'Import-Konto-12', {'grant': ['controlling.umsatz_importieren']}),
          ('sam', 'Sam Sehen', 'viewer', 'Sehen-Konto-34', {'grant': ['controlling.umsatz_sehen']}),
          ('eka', 'Eka Einkauf', 'viewer', 'Einkauf-Konto-56', {'grant': ['controlling.umsatz_ek', 'bestand.einkaufspreise']}),
          ('ede', 'Ede Nur-Controlling', 'viewer', 'Marge-Konto-90', {'grant': ['controlling.umsatz_ek']}),
          ('bea', 'Bea Nur-Bestand', 'viewer', 'Bestand-Konto-91', {'grant': ['controlling.umsatz_sehen', 'bestand.einkaufspreise']}),
          ('olaf', 'Olaf Ohne', 'editor', 'Ohne-Konto-78', {}))
for u, n, r, p, extra in NUTZER:
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
K = {}
for i, (u, _, _, p, _) in enumerate(NUTZER):
    K[u] = Client(f'198.51.100.{30 + i}'); assert K[u].call('login', {'username': u, 'password': p})[0] == 200
INA, SAM, EKA, OLAF, EDE, BEA = K['ina'], K['sam'], K['eka'], K['olaf'], K['ede'], K['bea']

# ── Registrierung ──
st, r = A.call('import_arten')
art = {a['id']: a for a in r.get('arten', [])}.get('umsatzdaten')
check('Importart „Umsätze je Kunde und Artikel“: Eigentümer Controlling, CSV, in Teilen, bis 200 MB', art and art['eigentuemer'] == 'controlling' and art['dateien'] == ['csv']
      and art['inTeilen'] is True and art['maxMb'] == 200 and art['ablauf'] == 'zentrale', art)
check('Importart sieht nur, wer das Recht hat', 'umsatzdaten' in [a['id'] for a in INA.call('import_arten')[1]['arten']]
      and 'umsatzdaten' not in [a['id'] for a in SAM.call('import_arten')[1]['arten']] and 'umsatzdaten' not in [a['id'] for a in OLAF.call('import_arten')[1]['arten']])
check('Recht importieren setzt Ansehen und Modulzugang voraus', INA.call('controlling_umsatz_daten')[0] == 200 and INA.call('controlling_start')[0] == 200)

# ── Vorschau, Teile, Übernahme ──
DATEN_A, TEILE_A = lesen(POS_A)
UP = 'a' * 32


def pruefen(cl, daten, upload=UP, **extra):
    """Vorschau des Imports (import_pruefen)."""
    return cl.call('import_pruefen', {'art': 'umsatzdaten', 'daten': daten, 'quelle': 'Umsatz-Test.csv', 'upload': upload, **extra})


def teil(cl, monat, daten, upload=UP):
    """Einen Monat als Teil übertragen (import_teil)."""
    return cl.call('import_teil', {'art': 'umsatzdaten', 'upload': upload, 'schluessel': monat, 'daten': daten, 'quelle': 'Umsatz-Test.csv'})


def uebernehmen(cl, daten, stand, upload=UP):
    """Import übernehmen (import_uebernehmen)."""
    return cl.call('import_uebernehmen', {'art': 'umsatzdaten', 'daten': daten, 'quelle': 'Umsatz-Test.csv', 'upload': upload, 'stand': stand})


check('ohne Recht: Vorschau 403', pruefen(SAM, DATEN_A)[0] == 403 and pruefen(OLAF, DATEN_A)[0] == 403)
check('ohne Recht: Teil 403', teil(SAM, '2025-01', TEILE_A['2025-01'])[0] == 403)
st, r = pruefen(INA, DATEN_A, upload='kein-upload')
check('ungültige Kennung des Imports: 422', st == 422 and 'Kennung' in r.get('error', ''), r)
st, r = INA.call('import_teil', {'art': 'kunden', 'upload': UP, 'schluessel': 'x', 'daten': {}})
check('Teil für eine Importart ohne Teile: 403 bzw. 422', st in (403, 422), (st, r))
st, r = A.call('import_teil', {'art': 'kunden', 'upload': UP, 'schluessel': 'x', 'daten': {}})
check('Teil für Kundenimport (Administrator): 422 nicht in Teilen', st == 422 and 'nicht in Teilen' in r.get('error', ''), r)
st, r = pruefen(INA, {**DATEN_A, 'version': 2})
check('unbekanntes Format: 422', st == 422, r)
st, r = pruefen(INA, {**DATEN_A, 'monate': {'2019-13': next(iter(DATEN_A['monate'].values()))}})
check('ungültiger Monat: 422', st == 422, r)

st, v = pruefen(INA, DATEN_A)
check('Vorschau: alle Monate neu, nichts entfällt', st == 200 and v['zahlen']['neu'] == len(DATEN_A['monate']) == 22 and v['zahlen']['entfaellt'] == 0 and v['pruefen'] is True, (st, v.get('zahlen')))
check('Vorschau: Teile = alle neuen Monate in Reihenfolge', v['teile'] == sorted(DATEN_A['monate']), v.get('teile'))
hin = ' '.join(h['text'] for h in v['hinweise'])
check('Vorschau: Hinweise Zeitraum, Positionen, ohne Berechnung', 'Zeitraum der Datei: ' in hin and 'ohne Gesamtbetrag' in hin and 'berechnete Positionen in 22 Monaten' in hin, hin)
check('Vorschau: unbekannte Kunden- und Artikelnummern als Warnung', any(h['stufe'] == 'warn' and '2000005' in h['text'] for h in v['hinweise'])
      and any(h['stufe'] == 'warn' and '40400' in h['text'] for h in v['hinweise']), v['hinweise'])
check('Vorschau: Zeilen je Monat mit Umsatz', len(v['zeilen']) == 22 and v['zeilen'][0]['schluessel'] == '2025-01' and v['zeilen'][0]['name'] == 'Januar 2025'
      and 'Umsatz' in v['zeilen'][0]['text'], v['zeilen'][:1])
check('Vorschau speichert nichts', dokument('controlling-umsatzdaten') is None)

st, r = uebernehmen(INA, DATEN_A, v['stand'])
check('Übernahme ohne übertragene Teile: 422, nichts gespeichert', st == 422 and 'nicht vollständig übertragen' in r.get('error', '') and dokument('controlling-umsatzdaten') is None, r)
m1 = TEILE_A['2025-01']
st, r = teil(INA, '2025-01', {**m1, 'hash': '0' * 64})
check('Teil mit falscher Prüfsumme: 422', st == 422 and 'Prüfsumme' in r.get('error', ''), r)
st, r = teil(INA, '2025-01', {**m1, 'zeilen': list(reversed(m1['zeilen']))})
check('Teil unsortiert: 422', st == 422 and 'sortiert' in r.get('error', ''), r)
schlecht = [list(m1['zeilen'][0])]; schlecht[0][0] = 32
st, r = teil(INA, '2025-01', {'monat': '2025-01', 'hash': '0' * 64, 'zeilen': schlecht})
check('Teil mit ungültigem Tag: 422', st == 422 and 'ungültige Werte' in r.get('error', ''), r)
schlecht = [list(m1['zeilen'][0])]; schlecht[0][5] = 1.5
st, r = teil(INA, '2025-01', {'monat': '2025-01', 'hash': '0' * 64, 'zeilen': schlecht})
check('Teil mit Kommazahl statt Cent: 422', st == 422, r)
st, r = teil(INA, '2025-02', m1)
check('Teil passt nicht zum Monat: 422', st == 422, r)
check('Teil ohne CSRF: 403', Client('198.51.100.99').call('import_teil', {'art': 'umsatzdaten'})[0] in (401, 403))
fehler_teile = [k for k in v['teile'] if teil(INA, k, TEILE_A[k])[0] != 200]
check('alle Teile übertragen (Prüfsumme aus Python = Server)', not fehler_teile, fehler_teile)
check('Teile liegen in der Zwischenablage', storage_raw(f'controlling-umsatzteile/{UP}-2025-01') is not None)
st, r = uebernehmen(INA, DATEN_A, v['stand'] + 1)
check('veralteter Stand: 409', st == 409, r)
st, r = uebernehmen(SAM, DATEN_A, v['stand'])
check('Übernahme ohne Recht: 403', st == 403)
# Teil eines anderen Mitarbeiters zählt nicht: Administrator mit Teilen von Ina
st, r = uebernehmen(A, DATEN_A, v['stand'])
check('Teile eines anderen Mitarbeiters werden nicht übernommen (422)', st == 422 and dokument('controlling-umsatzdaten') is None, r)
st, u = uebernehmen(INA, DATEN_A, v['stand'])
check('Übernahme: 22 Monate neu', st == 200 and u['zahlen']['neu'] == 22, (st, u.get('zahlen'), u.get('error')))
idx = dokument('controlling-umsatzdaten')
check('Verzeichnis: 22 Monate, Kunden und Artikel, Importverlauf mit Zeitraum und Name', idx and len(idx['monate']) == 22 and idx['rev'] == 1
      and idx['kunden'] == sorted(INFO_K) and sorted(idx['artikel']) == sorted(INFO_A) and idx['importe'][0]['vonName'] == 'Ina Import'
      and idx['importe'][0]['zeitraum'] == [DATEN_A['zeitraum']['von'], DATEN_A['zeitraum']['bis']] and idx['importe'][0]['neu'] == 22, idx and idx.get('importe'))
check('Monat gespeichert mit Prüfsumme der Datei', dokument('controlling-umsatzdaten/2025-03')['hash'] == DATEN_A['monate']['2025-03']['hash'])
check('Zwischenablage nach der Übernahme leer', storage_raw(f'controlling-umsatzteile/{UP}-2025-01') is None)
log = dokument('protokoll/' + dt.datetime.now(dt.timezone.utc).strftime('%Y-%m')) or []
ein = json.dumps([e for e in log if e.get('a') == 'controlling' and 'Umsatzdaten' in json.dumps(e, ensure_ascii=False)], ensure_ascii=False)
check('Protokoll: Übernahme mit Datei, Zeitraum und Monaten, ohne Beträge', 'Umsatzdaten aus „Umsatz-Test.csv“ übernommen' in ein and '22 neu' in ein and '€' not in ein
      and str(DATEN_A['monate']['2025-01']['umsatz']) not in ein, ein[:300])

# ── dieselbe Datei erneut: nichts geändert, keine Teile ──
st, v2 = pruefen(INA, DATEN_A, upload='b' * 32)
check('dieselbe Datei erneut: alles unverändert, keine Teile', st == 200 and v2['zahlen'] == {'neu': 0, 'geaendert': 0, 'entfaellt': 0, 'unveraendert': 22, 'fehler': 0}
      and v2['teile'] == [], v2.get('zahlen'))

# ── Randmonate: Datei vom 10. bis 20.10.2026 ersetzt nur diese Tage ──
POS_B = [p for p in positionen(dt.date(2026, 10, 10), dt.date(2026, 10, 20), faktor=2.0) if p[1] != '2000005']
POS_B = [p for p in POS_B if p[0] <= dt.date(2026, 10, 20)]
DATEN_B, TEILE_B = lesen(POS_B)
DATEN_B['zeitraum'] = {'von': '2026-10-10', 'bis': '2026-10-20'}
st, v = pruefen(INA, DATEN_B, upload='c' * 32)
check('Teilmonat: Oktober geändert, nur 10.–20., übrige Tage bleiben', st == 200 and v['zahlen']['geaendert'] == 1 and v['teile'] == ['2026-10']
      and 'nur 10.–20.' in v['zeilen'][0]['text'] and 'bleiben unverändert' in ' '.join(h['text'] for h in v['hinweise']), (v.get('zahlen'), v.get('zeilen')))
assert teil(INA, '2026-10', TEILE_B['2026-10'], upload='c' * 32)[0] == 200
st, u = uebernehmen(INA, DATEN_B, v['stand'], upload='c' * 32)
check('Teilmonat übernommen', st == 200 and u['zahlen']['geaendert'] == 1, u)
POS_AB = [p for p in POS_A if not (dt.date(2026, 10, 10) <= p[0] <= dt.date(2026, 10, 20))] + POS_B
okt = dokument('controlling-umsatzdaten/2026-10')['zeilen']
check('Oktober: Tage 1.–9. und 21.–30. aus der ersten Datei, 10.–20. aus der zweiten', sum(z[5] for z in okt if z[9]) == sum(cent(p[6]) for p in POS_AB if p[6] is not None and p[0].month == 10 and p[0].year == 2026)
      and any(z[0] < 10 for z in okt) and any(z[0] > 20 for z in okt))
check('Oktober: Verzeichnis passt zur gemergten Zeilenliste', dokument('controlling-umsatzdaten')['monate']['2026-10']['hash']
      == hashlib.sha256(json.dumps(okt, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest())
check('September unverändert', dokument('controlling-umsatzdaten/2026-09')['hash'] == DATEN_A['monate']['2026-09']['hash'])

# ── Monat ohne Umsätze im Zeitraum der Datei entfällt; deutlich weniger Positionen: Warnung ──
POS_C = [p for p in POS_A if p[0].year == 2025 and p[0].month == 3]
POS_C = POS_C[:len(POS_C) // 3]
DATEN_C, TEILE_C = lesen(POS_C)
DATEN_C['zeitraum'] = {'von': '2025-03-01', 'bis': '2025-04-30'}
st, v = pruefen(INA, DATEN_C, upload='d' * 32)
check('März geändert (weniger Positionen: Warnung), April entfällt', st == 200 and v['zahlen']['geaendert'] == 1 and v['zahlen']['entfaellt'] == 1 and v['teile'] == ['2025-03']
      and any(h['stufe'] == 'warn' and 'weniger Positionen' in h['text'] for h in v['hinweise']) and any(h['stufe'] == 'warn' and 'gelöscht' in h['text'] for h in v['hinweise']), v)
assert teil(INA, '2025-03', TEILE_C['2025-03'], upload='d' * 32)[0] == 200
# alter Rest einer abgebrochenen Übernahme (älter als ein Tag) wird aufgeräumt
REST = 'controlling-umsatzteile/' + 'e' * 32 + '-2025-05'
if not storage_sqlite():
    os.makedirs(os.path.join(os.environ['UDATA'], 'controlling-umsatzteile'), exist_ok=True)
storage_write(REST, {'von': 'x', 't': 0, 'monat': '2025-05', 'hash': '0' * 64, 'zeilen': []})
if storage_sqlite():
    import sqlite3
    with sqlite3.connect(os.environ['UDATA'] + '/.sqlite/store.sqlite') as db:
        db.execute('UPDATE documents SET mtime=? WHERE name=?', (1000, REST))
else:
    os.utime(os.path.join(os.environ['UDATA'], REST + '.php'), (1000, 1000))
st, u = uebernehmen(INA, DATEN_C, v['stand'], upload='d' * 32)
idx = dokument('controlling-umsatzdaten')
check('April gelöscht, März ersetzt', st == 200 and '2025-04' not in idx['monate'] and dokument('controlling-umsatzdaten/2025-04') is None
      and idx['monate']['2025-03']['pos'] == DATEN_C['monate']['2025-03']['pos'], (st, u.get('error')))
check('alte Reste der Zwischenablage aufgeräumt', storage_raw(REST) is None)
check('Importverlauf: neueste zuerst', [i['quelle'] for i in idx['importe']][:3] == ['Umsatz-Test.csv'] * 3 and idx['importe'][0]['entfallen'] == 1 and len(idx['importe']) == 3)
POS_JETZT = [p for p in POS_AB if not (p[0].year == 2025 and p[0].month in (3, 4))] + POS_C

# ── Juni 2026 neu: Kunde 2000004 nur mit einer Gutschrift (kein Kauf → „verloren“), Kunde 2000003 mit einem Viertel (ABC) ──
JUNI = [p for p in POS_JETZT if p[0].year == 2026 and p[0].month == 6]
POS_E = [p for p in JUNI if p[1] not in ('2000003', '2000004')] + [p for p in JUNI if p[1] == '2000003'][::4]
POS_E.append((dt.date(2026, 6, 15), '2000004', '40100', 1, -12.5, 8.4, -105.0, 7.1))
DATEN_E, TEILE_E = lesen(POS_E)
DATEN_E['zeitraum'] = {'von': '2026-06-01', 'bis': '2026-06-30'}
st, v = pruefen(INA, DATEN_E, upload='9' * 32)
assert st == 200 and v['teile'] == ['2026-06'], (st, v)
assert teil(INA, '2026-06', TEILE_E['2026-06'], upload='9' * 32)[0] == 200
st, u = uebernehmen(INA, DATEN_E, v['stand'], upload='9' * 32)
check('Juni 2026 ersetzt (Testdaten für neu/verloren und ABC)', st == 200 and u['zahlen']['geaendert'] == 1, (st, u))
POS_JETZT = [p for p in POS_JETZT if not (p[0].year == 2026 and p[0].month == 6)] + POS_E

# ── Auswertung (Server) ──
check('Auswertung ohne Recht: 403', OLAF.call('controlling_umsatz_auswertung')[0] == 403 and OLAF.call('controlling_umsatz_daten')[0] == 403)
check('Auswertung ohne Anmeldung: 401/404', Client('198.51.100.98').call('controlling_umsatz_auswertung')[0] in (401, 404))
st, g = SAM.call('controlling_umsatz_daten')
ERSTER, LETZTER = min(p_[0] for p_ in POS_JETZT), max(p_[0] for p_ in POS_JETZT)
check('Grunddaten: Stand, Rechte (ohne EK), Auswahllisten', st == 200 and g['stand']['von'] == ERSTER.isoformat() and g['stand']['bis'] == LETZTER.isoformat()
      and g['rechte'] == {'ek': False, 'importieren': False} and {v['nr'] for v in g['optionen']['vertreter']} == {'V1', 'V2'}
      and any(k['nr'] == '2000005' and k['bekannt'] is False for k in g['optionen']['kunden'])
      and any(a['nr'] == '40100' and a['name'] == 'Rinderhüfte' for a in g['optionen']['artikel']) and len(g['stand']['monate']) == 21, g.get('stand'))
check('Grunddaten ohne Beträge', 'umsatz' not in json.dumps(g['stand']))


def auswertung(cl, **q):
    """controlling_umsatz_auswertung mit Anfrage q → (Status, Antwort)."""
    st, r = cl.call('controlling_umsatz_auswertung&' + urllib.parse.urlencode(q))
    return st, r


def je(r):
    """Umsatz je Zeile der Rangliste {Schlüssel: Cent}."""
    return {z['schluessel']: z['werte']['umsatz'] for z in r['zeilen']}


fehler = []
for dim in ('vertreter', 'kundengruppe', 'kunde', 'vkgruppe', 'fleischart', 'artikel', 'monat', 'quartal', 'jahr', 'kw'):
    st, r = auswertung(SAM, von='2025-01', bis='2025-12', nach=dim, vj='0')
    if st != 200 or je(r) != erwartet(POS_JETZT, '2025-01', '2025-12', dim):
        fehler.append((dim, st, r.get('error'), je(r) if st == 200 else None, erwartet(POS_JETZT, '2025-01', '2025-12', dim)))
check('Summen je Gliederung = unabhängig gerechnet (alle zehn Gliederungen)', not fehler, fehler[:1])
st, r = auswertung(SAM, von='2025-01', bis='2025-12', nach='vertreter', vj='0')
check('Namen: Vertreter aus den Stammdaten, „ohne Vertreter“', {z['schluessel']: z['name'] for z in r['zeilen']} == {'V1': 'V1 – Vera Vertrieb', 'V2': 'V2 – Viktor Verkauf', '_': 'ohne Vertreter'})
check('Summe = Summe der Zeilen, Kunden gezählt', r['summe']['umsatz'] == sum(je(r).values()) and r['summe']['kunden'] == 5 and r['summeVj'] is None)
check('ohne EK-Recht: keine Einkaufswerte in der Antwort', 'ek' not in json.dumps(r['summe']) and '"umsatzEk"' not in json.dumps(r) and r['ek'] is False)
st, r = auswertung(SAM, von='2025-01', bis='2025-12', nach='kunde', vj='0')
kn = {z['schluessel']: (z['name'], z['sub']) for z in r['zeilen']}
check('Kunden: Firma aus den Stammdaten mit Nummer, Ort und Vertreter; unbekannter Kunde mit Nummer', kn['2000001'][0] == 'Gasthaus Eiche' and 'Vera Vertrieb' in kn['2000001'][1]
      and kn['2000005'] == ('Kunde 2000005', 'nicht in den Kundenstammdaten'), kn)
st, r = auswertung(SAM, von='2025-01', bis='2025-12', nach='artikel', vj='0')
check('ohne Berechnung (Leergut) zählt nicht zu Umsatz und Menge', '1' not in je(r) and r['summe']['posOhne'] > 0 and r['summe']['mengeOhne'] > 0)
# Filter
for filt, q in (({'vertreter': {'V1'}}, {'v': 'V1'}), ({'kundengruppe': {'10'}}, {'kg': '10'}), ({'vertreter': {'_'}}, {'v': '_'}), ({'vkgruppe': {'100'}, 'kunde': {'2000003'}}, {'ag': '100', 'k': '2000003'}),
                ({'fleischart': {'Schwein'}}, {'fa': 'Schwein'}), ({'artikel': {'40400'}}, {'a': '40400'}), ({'vertreter': {'V1', 'V2'}, 'fleischart': {'Rind', 'Kalb'}}, {'v': 'V1,V2', 'fa': 'Rind,Kalb'})):
    st, r = auswertung(SAM, von='2025-01', bis='2026-10', nach='kunde', vj='0', **q)
    check(f'Filter {q}: Summen wie unabhängig gerechnet', st == 200 and je(r) == erwartet(POS_JETZT, '2025-01', '2026-10', 'kunde', filt), (st, r.get('error')))
# Vorjahr: im laufenden Monat bis zum gleichen Tag
letzter = dt.date.fromisoformat(DATEN_A['zeitraum']['bis'])
st, r = auswertung(SAM, von='2026-01', bis='2026-10', nach='vertreter')
vj_soll = erwartet(POS_JETZT, '2025-01', '2025-10', 'vertreter', bis_tag=letzter.day if letzter.day < 31 else None)
check('Vorjahr je Vertreter (Oktober bis zum gleichen Tag)', st == 200 and {z['schluessel']: z['vj']['umsatz'] for z in r['zeilen'] if z['vj']} == vj_soll
      and r['vorjahr'] == {'von': '2025-01', 'bis': '2025-10', 'bisTag': letzter.day} and r['summeVj']['umsatz'] == sum(vj_soll.values()), (r.get('vorjahr'), r.get('error')))
st, r = auswertung(SAM, von='2026-01', bis='2026-03', nach='monat')
check('Zeitliche Gliederung: Vorjahr je Monat dem Monat zugeordnet, ganzer Monat', st == 200 and [z['schluessel'] for z in r['zeilen']] == ['2026-01', '2026-02', '2026-03']
      and r['zeilen'][0]['vj']['umsatz'] == erwartet(POS_JETZT, '2025-01', '2025-01', 'monat')['2025-01'] and r['vorjahr']['bisTag'] is None)
check('Monatsreihe: ein Eintrag je Monat mit Vorjahr', [m['monat'] for m in r['monate']] == ['2026-01', '2026-02', '2026-03'] and r['monate'][1]['vj'] is not None)
# EK nur mit Recht
st, r = auswertung(EKA, von='2025-01', bis='2025-12', nach='artikel', vj='0')
ek_soll = {}
for d, k, a, ko, m, p, b, ek in POS_JETZT:
    if b is not None and ek is not None and d.year == 2025:
        e = ek_soll.setdefault(a, [0, 0]); e[0] += int(round(milli(m) * int(round(ek * 10000)) / 100000)); e[1] += cent(b)
check('mit EK-Recht: EK-Wert und Umsatz mit EK je Artikel wie unabhängig gerechnet', st == 200 and r['ek'] is True
      and {z['schluessel']: [z['werte']['ek'], z['werte']['umsatzEk']] for z in r['zeilen']} == ek_soll, (st, r.get('error')))
st, g = EKA.call('controlling_umsatz_daten')
check('Grunddaten mit EK-Recht', g['rechte']['ek'] is True)
# Rangliste nach Kennzahl: DB (€ und %) je Kunde, höchste oder niedrigste zuerst – Reihenfolge vom Server
roh = {}
for d, k, a, ko, m, p, b, ek in POS_JETZT:
    if b is not None and d.year == 2025:
        e = roh.setdefault(k, [0, 0, 0, 0]); e[2] += cent(b); e[3] += milli(m)
        if ek is not None:
            e[0] += int(round(milli(m) * int(round(ek * 10000)) / 100000)); e[1] += cent(b)
db_soll = {k: e[1] - e[0] for k, e in roh.items()}
st, r = auswertung(EKA, von='2025-01', bis='2025-12', nach='kunde', vj='0', rang='db')
check('Rangliste nach DB: Kunden mit absteigendem DB (unabhängig gerechnet)', st == 200 and [z['schluessel'] for z in r['zeilen']] == sorted(db_soll, key=lambda k: -db_soll[k])
      and r['anfrage']['rang'] == 'db' and r['anfrage']['auf'] is False, (st, r.get('error'), [z['schluessel'] for z in r.get('zeilen', [])], db_soll))
st, r = auswertung(EKA, von='2025-01', bis='2025-12', nach='kunde', vj='0', rang='db', auf='1')
check('Rangliste nach DB, niedrigste zuerst', st == 200 and [z['schluessel'] for z in r['zeilen']] == sorted(db_soll, key=lambda k: db_soll[k]) and r['anfrage']['auf'] is True)
st, r = auswertung(EKA, von='2025-01', bis='2025-12', nach='artikel', vj='0', rang='spanne')
sp = {z['schluessel']: (z['werte']['umsatzEk'] - z['werte']['ek']) / z['werte']['umsatzEk'] for z in r.get('zeilen', []) if z['werte'].get('umsatzEk')}
gross = [z['schluessel'] for z in r.get('zeilen', []) if not z.get('klein')]
check('Rangliste nach Spanne: Artikel absteigend, wenig Umsatz mit EK (Schwelle) am Ende', st == 200 and gross == sorted(gross, key=lambda k: -sp[k])
      and r['rangSchwelle'] >= 10000 and all(z['werte']['umsatzEk'] < r['rangSchwelle'] for z in r['zeilen'] if z.get('klein'))
      and [z.get('klein', False) for z in r['zeilen']] == sorted([z.get('klein', False) for z in r['zeilen']]), (st, r.get('error'), gross, sp))
st, r = auswertung(SAM, von='2025-01', bis='2025-12', nach='kunde', vj='0', rang='menge')
check('Rangliste nach Menge (ohne EK-Recht erlaubt)', st == 200 and [z['werte']['menge'] for z in r['zeilen']] == sorted([z['werte']['menge'] for z in r['zeilen']], reverse=True)
      and r.get('rangSchwelle') is None, (st, r.get('error')))
for cl, wer in ((SAM, 'nur ansehen'), (EDE, 'nur controlling.umsatz_ek'), (BEA, 'nur bestand.einkaufspreise')):
    check(f'Rangliste nach DB {wer}: 403 (auch die Reihenfolge verriete den DB, GR-008)', auswertung(cl, nach='kunde', rang='db')[0] == 403
          and auswertung(cl, nach='kunde', rang='spanne')[0] == 403)
check('Rangliste: unbekannte Kennzahl → 422', auswertung(EKA, rang='marge')[0] == 422)


# ABC-Analyse und Vergleich zum Vorjahr (neu/verloren) – unabhängig gerechnet
def kaeufer(pos, von, bis, dim):
    """Merkmale mit Kauf (berechnete Position mit Menge > 0) im Zeitraum"""
    return {{'kunde': k, 'artikel': a, **INFO_K[k], **INFO_A[a]}[dim] for d, k, a, ko, m, p, b, ek in pos
            if b is not None and m > 0 and von <= d.strftime('%Y-%m') <= bis}


def abc_soll(werte):
    """A: die größten bis 80 % (die Zeile über der Grenze zählt noch mit), B bis 95 %, Rest C; Werte ≤ 0 sind C"""
    gesamt, kum, out = sum(v for v in werte.values() if v > 0), 0, {}
    for k in sorted(werte, key=lambda k: -werte[k]):
        vorher = kum / gesamt if gesamt else 1
        out[k] = 'C' if werte[k] <= 0 else 'A' if vorher < 0.8 else 'B' if vorher < 0.95 else 'C'
        kum += max(0, werte[k])
    return out


JUNI_JETZT, JUNI_VJ = kaeufer(POS_JETZT, '2026-06', '2026-06', 'kunde'), kaeufer(POS_JETZT, '2025-06', '2025-06', 'kunde')
st, r = auswertung(SAM, von='2026-06', bis='2026-06', nach='kunde')
wechsel = {z['schluessel']: z.get('wechsel') for z in r.get('zeilen', [])}
soll = {k: 'neu' if k in JUNI_JETZT - JUNI_VJ else 'verloren' if k in JUNI_VJ - JUNI_JETZT else None for k in JUNI_JETZT | JUNI_VJ}
check('neu/verloren je Kunde wie unabhängig gerechnet (Juni: nur Gutschrift = kein Kauf = verloren)', st == 200 and wechsel == soll and soll['2000004'] == 'verloren'
      and r['wechsel']['neu']['anzahl'] == len(JUNI_JETZT - JUNI_VJ) and r['wechsel']['verloren']['anzahl'] == len(JUNI_VJ - JUNI_JETZT), (st, r.get('error'), wechsel, soll))
umsatz_juni = erwartet(POS_JETZT, '2026-06', '2026-06', 'kunde')
abc_juni = abc_soll(umsatz_juni)
check('ABC nach Umsatz je Kunde wie unabhängig gerechnet (A, B und C)', {z['schluessel']: z.get('abc') for z in r['zeilen']} == abc_juni and abc_juni['2000004'] == 'C'
      and len(set(abc_juni.values())) >= 2 and {x: r['abc'][x]['anzahl'] for x in 'ABC'} == {x: list(abc_juni.values()).count(x) for x in 'ABC'}
      and abs(r['abc']['A']['anteil'] - sum(v for k, v in umsatz_juni.items() if abc_juni[k] == 'A') / sum(v for v in umsatz_juni.values() if v > 0)) < 1e-9
      and r['abc']['A']['anteil'] >= 0.8, (r.get('abc'), abc_juni))
vj_juni = erwartet(POS_JETZT, '2025-06', '2025-06', 'kunde')
verloren = sorted(JUNI_VJ - JUNI_JETZT, key=lambda k: -vj_juni[k])
st, r = auswertung(SAM, von='2026-06', bis='2026-06', nach='kunde', nur='verloren')
check('nur verloren: nur diese Zeilen, nach Vorjahresumsatz geordnet, Summe des Vorjahrs', st == 200 and [z['schluessel'] for z in r['zeilen']] == verloren and r['zeilenGesamt'] == len(verloren)
      and r['wechsel']['verloren']['umsatzVj'] == sum(vj_juni[k] for k in verloren) and r['anfrage']['nur'] == 'verloren' and '"umsatzEk"' not in json.dumps(r), (st, r.get('error'), [z['schluessel'] for z in r.get('zeilen', [])]))
st, r = auswertung(EKA, von='2026-06', bis='2026-06', nach='kunde', nur='verloren', rang='menge', auf='1')
check('nur verloren nach Menge (niedrigste zuerst): Reihenfolge nach der Vorjahresmenge', st == 200 and [z['vj']['menge'] for z in r['zeilen']] == sorted(z['vj']['menge'] for z in r['zeilen']), (st, r.get('error')))
st, r = auswertung(SAM, von='2026-04', bis='2026-04', nach='artikel', nur='neu')
april = kaeufer(POS_JETZT, '2026-04', '2026-04', 'artikel')
check('nur neu: April 2026 (Vorjahresmonat ohne Daten) – alle gekauften Artikel neu, ABC über die ganze Auswahl', st == 200 and {z['schluessel'] for z in r['zeilen']} == april
      and r['wechsel'] == {'neu': {'anzahl': len(april), 'umsatz': sum(erwartet(POS_JETZT, '2026-04', '2026-04', 'artikel').values())}, 'verloren': {'anzahl': 0, 'umsatzVj': 0}}
      and {z['schluessel']: z['abc'] for z in r['zeilen']} == abc_soll(erwartet(POS_JETZT, '2026-04', '2026-04', 'artikel')), (st, r.get('error'), r.get('wechsel')))
st, r = auswertung(SAM, von='2026-04', bis='2026-04', nach='artikel', nur='verloren')
check('nur verloren ohne Treffer: leere Liste', st == 200 and r['zeilen'] == [] and r['zeilenGesamt'] == 0)
db_juni = {}
for d, k, a, ko, m, p, b, ek in POS_JETZT:
    if b is not None and ek is not None and d.year == 2026 and d.month == 6:
        db_juni[k] = db_juni.get(k, 0) + cent(b) - int(round(milli(m) * int(round(ek * 10000)) / 100000))
for k in umsatz_juni:
    db_juni.setdefault(k, 0)
st, r = auswertung(EKA, von='2026-06', bis='2026-06', nach='kunde', rang='db')
check('ABC nach DB (mit EK-Recht) wie unabhängig gerechnet', st == 200 and {z['schluessel']: z['abc'] for z in r['zeilen']} == abc_soll(db_juni), (st, r.get('error'), r.get('abc')))
st, r = auswertung(EKA, von='2026-06', bis='2026-06', nach='kunde', rang='spanne')
check('ABC nicht bei Spanne (kein Anteil)', st == 200 and r['abc'] is None and all('abc' not in z for z in r['zeilen']))
st, r = auswertung(SAM, von='2026-06', bis='2026-06', nach='monat')
check('Zeit: weder ABC noch neu/verloren', st == 200 and r['abc'] is None and r['wechsel'] is None and all('wechsel' not in z and 'abc' not in z for z in r['zeilen']))
st, r = auswertung(SAM, von='2026-06', bis='2026-06', nach='kunde', vj='0')
check('ohne Vorjahr: ABC ja, neu/verloren nein', st == 200 and r['abc'] is not None and r['wechsel'] is None and all('wechsel' not in z for z in r['zeilen']))
for q, text in (({'nur': 'weg'}, 'neu oder verloren'), ({'nur': 'neu', 'vj': '0', 'nach': 'kunde'}, 'nur mit Vorjahr'), ({'nur': 'verloren', 'nach': 'monat'}, 'nur mit Vorjahr')):
    st, r = auswertung(SAM, **q)
    check(f'neu/verloren ungültig {q}: 422', st == 422 and text in r.get('error', ''), (st, r))
st, r = SAM.call('controlling_umsatz_detail&' + urllib.parse.urlencode({'dim': 'kunde', 'wert': '2000001', 'nur': 'neu'}))
check('Pop-up-Detail übergeht „nur“ (gilt nur für die Rangliste)', st == 200 and r['name'] == 'Gasthaus Eiche', (st, r.get('error')))


# Bestellpausen (Frühwarnung) – unabhängig gerechnet
def pausen_soll(pos, stichtag, filt=None):
    """Stammkunden (≥ 4 Kauftage in 182 Tagen bis zum Stichtag) mit Pause ≥ 7 Tage, ≥ 2 × Ø Abstand und länger als jede frühere Pause"""
    beginn = stichtag - dt.timedelta(days=181)
    tage, umsatz = {}, {}
    for d, k, a, ko, m, p, b, ek in pos:
        if b is None or d < beginn or d > stichtag:
            continue
        merk = {'kunde': k, 'artikel': a, **INFO_K[k], **INFO_A[a]}
        if filt and any(merk[f] not in w for f, w in filt.items()):
            continue
        umsatz[k] = umsatz.get(k, 0) + cent(b)
        if m > 0:
            tage.setdefault(k, set()).add(d)
    stamm, out = 0, {}
    for k, t in tage.items():
        t = sorted(t)
        if len(t) < 4:
            continue
        stamm += 1
        mittel = (t[-1] - t[0]).days / (len(t) - 1)
        laengste = max((t[i + 1] - t[i]).days for i in range(len(t) - 1))
        pause = (stichtag - t[-1]).days
        if pause >= 7 and pause >= 2 * mittel and pause > laengste:
            out[k] = {'letzter': t[-1].isoformat(), 'pause': pause, 'laengste': laengste, 'kauftage': len(t), 'umsatzMonat': umsatz[k] / len(t) * 30.4375 / mittel}
    return stamm, out


def pausen(cl, **q):
    """controlling_umsatz_pausen mit Anfrage q → (Status, Antwort)"""
    return cl.call('controlling_umsatz_pausen&' + urllib.parse.urlencode(q))


def pausen_gleich(r, soll):
    """Antwort der Bestellpausen = unabhängig gerechnet (Monatsumsatz auf 1 Cent genau), Reihenfolge nach Monatsumsatz"""
    ist = {z['nr']: z for z in r.get('zeilen', [])}
    return (set(ist) == set(soll) and all(ist[k][f] == soll[k][f] for k in soll for f in ('letzter', 'pause', 'laengste', 'kauftage'))
            and all(abs(ist[k]['umsatzMonat'] - soll[k]['umsatzMonat']) <= 1 for k in soll)
            and [z['umsatzMonat'] for z in r['zeilen']] == sorted((z['umsatzMonat'] for z in r['zeilen']), reverse=True))


stamm, soll = pausen_soll(POS_JETZT, dt.date(2026, 6, 30))
st, r = pausen(SAM, von='2026-06', bis='2026-06')
check('Bestellpausen Juni 2026: Stammkunden und auffällige Pausen wie unabhängig gerechnet (Imbiss Ohne nur mit Gutschrift)', st == 200 and r['stichtag'] == '2026-06-30'
      and r['von'] == '2025-12-31' and r['stammkunden'] == stamm and '2000004' in soll and pausen_gleich(r, soll) and r['gesamt'] == len(soll), (st, r.get('error'), r.get('zeilen'), soll))
check('Bestellpausen: Name und Zusatz aus den Stammdaten, Regel in der Antwort, keine Einkaufswerte', any(z['name'] == 'Imbiss Ohne' for z in r['zeilen'])
      and r['regel'] == {'tage': 182, 'kauftage': 4, 'faktor': 2, 'minTage': 7} and '"ek"' not in json.dumps(r) and 'umsatzEk' not in json.dumps(r))
for filt, q in (({'vertreter': {'V1'}}, {'v': 'V1'}), ({'artikel': {'40100'}}, {'a': '40100'}), ({'kunde': {'2000004', '2000001'}}, {'k': '2000004,2000001'})):
    stamm, soll = pausen_soll(POS_JETZT, dt.date(2026, 6, 30), filt)
    st, r = pausen(SAM, von='2026-01', bis='2026-06', **q)
    check(f'Bestellpausen mit Filter {q} wie unabhängig gerechnet', st == 200 and r['stammkunden'] == stamm and pausen_gleich(r, soll), (st, r.get('error'), r.get('zeilen'), soll))
stamm, soll = pausen_soll(POS_JETZT, LETZTER)
st, r = pausen(EKA, von='2026-01', bis='2026-10')
check('Bestellpausen bis zum letzten Tag mit Daten (Stichtag = Stand), auch mit EK-Recht ohne Einkaufswerte', st == 200 and r['stichtag'] == LETZTER.isoformat() and pausen_gleich(r, soll)
      and 'umsatzEk' not in json.dumps(r), (st, r.get('error'), r.get('stichtag')))
stamm, soll = pausen_soll(POS_JETZT, dt.date(2025, 12, 31))
st, r = pausen(SAM, von='2025-01', bis='2025-12')
check('Bestellpausen zum Ende des Vorjahres', st == 200 and r['stichtag'] == '2025-12-31' and r['stammkunden'] == stamm and pausen_gleich(r, soll), (st, r.get('error')))
check('Bestellpausen ohne Recht 403, ohne Anmeldung 401/404, ungültiger Zeitraum 422', pausen(OLAF)[0] == 403 and Client('198.51.100.96').call('controlling_umsatz_pausen')[0] in (401, 404)
      and pausen(SAM, von='2026-13')[0] == 422)
for cl, wer in ((EDE, 'nur controlling.umsatz_ek'), (BEA, 'nur bestand.einkaufspreise')):
    st, r = auswertung(cl, von='2025-01', bis='2025-12', nach='artikel', vj='0')
    check(f'{wer}: keine Einkaufswerte (GR-008, beide Rechte nötig)', st == 200 and r['ek'] is False and 'ek' not in r['summe'] and '"umsatzEk"' not in json.dumps(r) and all('ek' not in z['werte'] for z in r['zeilen']) and cl.call('controlling_umsatz_daten')[1]['rechte']['ek'] is False, (st, r.get('ek')))
# ungültige Anfragen
for q, text in (({'von': '2026-13'}, 'Zeitraum'), ({'von': '2026-05', 'bis': '2026-01'}, 'Zeitraum'), ({'nach': 'irgendwas'}, 'Gliederung'), ({'v': 'V1;DROP'}, 'Filter'),
                ({'von': '2010-01', 'bis': '2026-10'}, 'höchstens')):
    st, r = auswertung(SAM, **q)
    check(f'ungültige Anfrage {q}: 422', st == 422 and text in r.get('error', ''), (st, r))
st, r = auswertung(SAM)
check('Standard: laufendes Jahr bis zum letzten Monat mit Daten, nach Monat', st == 200 and r['anfrage'] == {'von': '2026-01', 'bis': '2026-10', 'nach': 'monat', 'vj': True, 'rang': 'umsatz', 'auf': False, 'nur': ''})
st, r = A.call('controlling_umsatz')
check('Monatsmeldung weiß von den Umsatzdaten (Reiter Auswertung zuerst)', st == 200 and r['umsatzdaten'] == {'vorhanden': True})

# ── Pop-ups: Detail eines Merkmals (controlling_umsatz_detail) ──
def detail(cl, **q):
    """controlling_umsatz_detail (Pop-up) mit Anfrage q → (Status, Antwort)."""
    return cl.call('controlling_umsatz_detail&' + urllib.parse.urlencode(q))


def letzte(pos, von, bis, nach, filt=None):
    """Letzter Kauf (berechnete Position mit Menge > 0, keine Gutschrift) je Kunde bzw. Artikel (unabhängig gerechnet)"""
    out = {}
    for d, k, a, ko, m, p, b, ek in pos:
        mo = d.strftime('%Y-%m')
        if b is None or m <= 0 or mo < von or mo > bis:
            continue
        merk = {'kunde': k, 'artikel': a, **INFO_K[k], **INFO_A[a]}
        if filt and any(merk[f] not in w for f, w in filt.items()):
            continue
        out[merk[nach]] = max(out.get(merk[nach], ''), d.isoformat())
    return out


V1 = {'vertreter': {'V1'}}
st, r = detail(SAM, dim='vertreter', wert='V1', von='2025-01', bis='2025-12', vj='0')
kun = {z['nr']: z['werte']['umsatz'] for z in r.get('kunden', [])}
art = {z['nr']: z['werte']['umsatz'] for z in r.get('artikel', [])}
check('Detail Vertreter: Kunden und Artikel wie unabhängig gerechnet', st == 200 and kun == erwartet(POS_JETZT, '2025-01', '2025-12', 'kunde', V1)
      and art == erwartet(POS_JETZT, '2025-01', '2025-12', 'artikel', V1) and r['name'] == 'V1 – Vera Vertrieb', (st, r.get('error'), kun))
check('Detail Vertreter: Summe, Anzahl Kunden und Artikel, Monatsreihe', r['summe']['umsatz'] == sum(kun.values()) and r['summe']['kunden'] == len(kun)
      and r['summe']['artikel'] == len(art) and len(r['monate']) == 12 and sum(m['werte']['umsatz'] for m in r['monate']) == r['summe']['umsatz'] and r['summeVj'] is None)
check('Detail Vertreter: letzter Kauf je Kunde und Artikel', {z['nr']: z['zuletzt'] for z in r['kunden']} == letzte(POS_JETZT, '2025-01', '2025-12', 'kunde', V1)
      and {z['nr']: z['zuletzt'] for z in r['artikel']} == letzte(POS_JETZT, '2025-01', '2025-12', 'artikel', V1) and 'tage' not in r)
check('Detail: Kunden zuerst nach Umsatz, Leergut nicht als Artikel', [z['werte']['umsatz'] for z in r['kunden']] == sorted(kun.values(), reverse=True) and '1' not in art)
check('Detail ohne EK-Recht: keine Einkaufswerte', r['ek'] is False and '"ek":' not in json.dumps(r).replace('"ek": false', '') and '"umsatzEk"' not in json.dumps(r))
K1 = {'kunde': {'2000001'}}
st, r = detail(SAM, dim='kunde', wert='2000001', von='2025-01', bis='2025-12', vj='0')
tage, kauftage, je_art = {}, set(), {}
for d, k, a, ko, m, p, b, ek in POS_JETZT:
    if k == '2000001' and b is not None and d.year == 2025:
        tage[d.isoformat()] = tage.get(d.isoformat(), 0) + cent(b)
        if m > 0:
            kauftage.add(d.isoformat()); je_art.setdefault(a, set()).add(d.isoformat())
tage = {t: v for t, v in tage.items() if t in kauftage}   # Liefertage: nur Tage mit Kauf (Gutschrift allein ist keiner)
check('Detail Kunde: seine Artikel mit letztem Kauf wie unabhängig gerechnet', st == 200 and {z['nr']: z['werte']['umsatz'] for z in r['artikel']} == erwartet(POS_JETZT, '2025-01', '2025-12', 'artikel', K1)
      and {z['nr']: z['zuletzt'] for z in r['artikel']} == letzte(POS_JETZT, '2025-01', '2025-12', 'artikel', K1) and 'kunden' not in r, (st, r.get('error')))
check('Detail Kunde: Käufe je Artikel = Tage mit Menge > 0 (Gutschrift zählt nicht)', {z['nr']: z['kaeufe'] for z in r['artikel'] if z['kaeufe']} == {a: len(t) for a, t in je_art.items()}, r.get('artikel', [])[:2])
check('Detail Kunde: Liefertage (neueste zuerst) mit Umsatz je Tag', {t['tag']: t['werte']['umsatz'] for t in r['tage']} == tage
      and [t['tag'] for t in r['tage']] == sorted(tage, reverse=True) and r['summe']['zuletzt'] == max(tage))
check('Detail Kunde: Name, Vertreter und Kundengruppe aus den Stammdaten', r['name'] == 'Gasthaus Eiche' and r['kunde'] == {'vertreter': 'Vera Vertrieb', 'gruppe': 'Gastronomie', 'ort': '20095 Hamburg'}, r.get('kunde'))
st, r = detail(SAM, dim='kunde', wert='2000001', von='2026-01', bis='2026-10')
vj_soll = erwartet(POS_JETZT, '2025-01', '2025-10', 'artikel', K1, bis_tag=letzter.day if letzter.day < 31 else None)
check('Detail Kunde mit Vorjahr: Vorjahr je Artikel (Oktober bis zum gleichen Tag)', st == 200 and {z['nr']: z['vj']['umsatz'] for z in r['artikel'] if z['vj']} == vj_soll
      and r['summeVj']['umsatz'] == sum(vj_soll.values()), (st, r.get('error')))
check('Detail Kunde mit Vorjahr: Liefertage nur im Zeitraum', all(t['tag'] >= '2026-01-01' for t in r['tage']))


def summe_je_artikel(pos, von, bis, filt=None):
    """Umsatz (Cent) und Menge (Tausendstel) je Artikel über alle Kunden – Vergleichsgrundlage des Preisspiegels"""
    out = {}
    for d, k, a, ko, m, p, b, ek in pos:
        mo = d.strftime('%Y-%m')
        if b is None or mo < von or mo > bis:
            continue
        merk = {'kunde': k, 'artikel': a, **INFO_K[k], **INFO_A[a]}
        if filt and any(merk[f] not in w for f, w in filt.items()):
            continue
        e = out.setdefault(a, {'umsatz': 0, 'menge': 0}); e['umsatz'] += cent(b); e['menge'] += milli(m)
    return out


st, r = detail(SAM, dim='kunde', wert='2000001', von='2025-01', bis='2025-12', vj='0')
alle_art = summe_je_artikel(POS_JETZT, '2025-01', '2025-12')
check('Preisspiegel: Kunden-Pop-up liefert je Artikel Umsatz und Menge aller Kunden (unabhängig gerechnet)', st == 200 and r['artikel']
      and all(z['vergleich'] == alle_art[z['nr']] for z in r['artikel']), [(z['nr'], z.get('vergleich'), alle_art.get(z['nr'])) for z in r.get('artikel', [])])
st, r = detail(SAM, dim='kunde', wert='2000001', von='2025-01', bis='2025-12', vj='0', fa='Rind', k='2000003')
alle_art = summe_je_artikel(POS_JETZT, '2025-01', '2025-12', {'fleischart': {'Rind'}})
check('Preisspiegel: übrige Filter der Seite gelten, der Kundenfilter nicht', st == 200 and r['artikel'] and all(z['vergleich'] == alle_art[z['nr']] for z in r['artikel']),
      [(z['nr'], z.get('vergleich')) for z in r.get('artikel', [])])
st, r = detail(SAM, dim='artikel', wert='40100', von='2025-01', bis='2025-12', vj='0')
check('Preisspiegel: Vergleichswerte nur im Kunden-Pop-up', st == 200 and all('vergleich' not in z for z in r['kunden']))
st, r = detail(SAM, dim='kunde', wert='2000001', von='2025-01', bis='2025-12', vj='0', fa='Rind', k='2000003')
check('Detail: Filter der Seite gelten weiter, das Merkmal ersetzt den gleichen Filter', st == 200 and {z['nr'] for z in r['artikel']} == set(erwartet(POS_JETZT, '2025-01', '2025-12', 'artikel', {'kunde': {'2000001'}, 'fleischart': {'Rind'}}))
      and r['wert'] == '2000001', (st, r.get('error'), [z['nr'] for z in r.get('artikel', [])]))
A1 = {'artikel': {'40100'}}
st, r = detail(SAM, dim='artikel', wert='40100', von='2025-01', bis='2025-12', vj='0')
check('Detail Artikel: seine Käufer mit Menge und letztem Kauf', st == 200 and {z['nr']: z['werte']['umsatz'] for z in r['kunden']} == erwartet(POS_JETZT, '2025-01', '2025-12', 'kunde', A1)
      and {z['nr']: z['zuletzt'] for z in r['kunden']} == letzte(POS_JETZT, '2025-01', '2025-12', 'kunde', A1) and 'artikel' not in r and r['name'] == 'Rinderhüfte', (st, r.get('error')))
st, r = detail(SAM, dim='vertreter', wert='_', von='2025-01', bis='2025-12', vj='0')
check('Detail „ohne Vertreter“', st == 200 and r['name'] == 'ohne Vertreter' and {z['nr'] for z in r['kunden']} == set(erwartet(POS_JETZT, '2025-01', '2025-12', 'kunde', {'vertreter': {'_'}})))
st, r = detail(SAM, dim='kunde', wert='2000005', von='2025-01', bis='2025-12', vj='0')
check('Detail Kunde ohne Stammsatz: Nummer als Name', st == 200 and r['name'] == 'Kunde 2000005' and r['kunde'] is None)
st, r = detail(EKA, dim='kundengruppe', wert='10', von='2025-01', bis='2025-12', vj='0')
check('Detail mit EK-Recht: EK-Wert je Kunde', st == 200 and r['ek'] is True and all('ek' in z['werte'] for z in r['kunden']) and 'ek' in r['summe'])
for cl, wer in ((EDE, 'nur controlling.umsatz_ek'), (BEA, 'nur bestand.einkaufspreise')):
    st, r = detail(cl, dim='kundengruppe', wert='10', von='2025-01', bis='2025-12', vj='0')
    check(f'Detail {wer}: keine Einkaufswerte (GR-008)', st == 200 and r['ek'] is False and 'ek' not in r['summe'] and all('ek' not in z['werte'] for z in r['kunden']), (st, r.get('ek')))
for q, text in (({'dim': 'irgendwas', 'wert': '1'}, 'Merkmal'), ({'dim': 'kunde', 'wert': ''}, 'Wert'), ({'dim': 'kunde', 'wert': '2000001;DROP'}, 'Wert'),
                ({'dim': 'kunde', 'wert': '2000001', 'von': '2026-13'}, 'Zeitraum')):
    st, r = detail(SAM, **q)
    check(f'Detail: ungültige Anfrage {q}: 422', st == 422 and text in r.get('error', ''), (st, r))
check('Detail ohne Recht: 403', detail(OLAF, dim='kunde', wert='2000001')[0] == 403)
check('Detail ohne Anmeldung: 401/404', Client('198.51.100.97').call('controlling_umsatz_detail&dim=kunde&wert=2000001')[0] in (401, 404))

# ── Oberfläche: Import im Browser, Auswertung ──
CSV = os.path.join(WORK, 'Umsatz-Browser.csv')
POS_D = positionen(dt.date(2026, 9, 1), dt.date(2026, 10, 30), faktor=1.5)
with open(CSV, 'w', encoding='cp1252', newline='') as f:
    f.write(csv_text(POS_D, kaputt=1))
errors = []
with sync_playwright() as p:
    br = p.chromium.launch()
    ctx = br.new_context(viewport={'width': 1280, 'height': 900}, accept_downloads=True)
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
    pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', 'ina'); pg.fill('#pw1', 'Import-Konto-12'); pg.click('#auth-submit')
    pg.wait_for_selector('#vt-importe:not([hidden])')
    pg.click('#vt-importe'); pg.wait_for_selector('#view-importe .imp-art[data-art="umsatzdaten"]')
    check('Importzentrale: Importart des Controllings mit Eigentümer', 'Controlling' in pg.text_content('#view-importe .imp-art[data-art="umsatzdaten"] .imp-eig')
          and 'in Teilen' not in pg.text_content('#view-importe .imp-art[data-art="umsatzdaten"]'), pg.locator('#view-importe .imp-art').all_text_contents())
    pg.set_input_files('#view-importe input[data-imp-datei="umsatzdaten"]', CSV)
    pg.wait_for_selector('#imp-geaendert')
    t = pg.inner_text('#view-importe')
    check('Browser-Vorschau: September und Oktober geändert, eine fehlerhafte Zeile (Datum)', pg.inner_text('#imp-geaendert') == '2' and pg.inner_text('#imp-fehler') == '1'
          and 'Ungültiges Datum' in t and 'Belegköpfe' in t, t[:600])
    pg.screenshot(path=SH + '/controlling-umsatzdaten-import-vorschau.png', full_page=True)
    pg.click('#imp-ok')
    pg.wait_for_selector('#imp-ergebnis')
    check('Browser: Teile übertragen und übernommen (Prüfsumme des Browsers = Server)', 'Import übernommen' in pg.inner_text('#imp-ergebnis'), pg.inner_text('#view-importe')[:300])
    DATEN_D, _ = lesen(POS_D)
    st, v = pruefen(INA, DATEN_D, upload='f' * 32)
    check('Browser-Leser = Python: dieselbe Datei aus Python danach unverändert (gleiche Prüfsummen)', st == 200 and v['zahlen']['unveraendert'] == 2 and not v['teile'], v.get('zahlen'))
    d1, d2 = min(p_[0] for p_ in POS_D), max(p_[0] for p_ in POS_D)
    POS_JETZT = [p_ for p_ in POS_JETZT if p_[0] < d1 or p_[0] > d2] + POS_D
    ERSTER, LETZTER = min(p_[0] for p_ in POS_JETZT), max(p_[0] for p_ in POS_JETZT)
    pg.screenshot(path=SH + '/controlling-umsatzdaten-import-ergebnis.png')
    ctx.close()

    def offen(dim):
        """Warten, bis das Pop-up des Merkmals offen ist; liefert seinen Text."""
        pg.wait_for_selector(f'#ctl-ua-dialog[open] .ctl-ud[data-dim="{dim}"]')
        return pg.text_content('#ctl-ua-dialog')

    for breite, thema in ((1280, 'light'), (390, 'dark')):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, color_scheme=thema, accept_downloads=True)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.on('console', lambda m: errors.append(m.text) if m.type == 'error' else None)
        pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', 'admin'); pg.fill('#pw1', PW); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden])')
        pg.goto(BASE + '/module/controlling/#umsatz')
        pg.wait_for_selector('#ctl-ua-rang li')
        check(f'{breite}px {thema}: Reiter Auswertung zuerst (Daten importiert)', pg.get_attribute('#ctl-u-tabs [data-tab="auswertung"]', 'aria-selected') == 'true'
              and pg.is_visible('#ctl-u-auswertung') and pg.is_hidden('#ctl-u-uebersicht'))
        kpi = pg.text_content('#ctl-ua-kpis')
        check(f'{breite}px {thema}: Kennzahlen mit DB und Spanne (Administrator)', 'Umsatz' in kpi and 'DB' in (kpi) and 'Spanne' in kpi and 'Rohmarge' not in kpi and 'zum Vorjahr' in kpi and 'Pp' in kpi, kpi)
        check(f'{breite}px {thema}: Stand der Daten (kurz, Herkunft im Hinweis)', f'Daten vom {ERSTER:%d.%m.%Y} bis {LETZTER:%d.%m.%Y} · Import' in pg.inner_text('#ctl-ua-stand')
              and 'Warenwirtschaft' in (pg.get_attribute('#ctl-ua-stand', 'title') or ''), pg.inner_text('#ctl-ua-stand'))
        check(f'{breite}px {thema}: einfacher Kopf – eine Bereichsleiste nur bei mehreren Bereichen, Überschrift mit Reitern in einer Zeile', pg.is_hidden('#ctl-bereiche')
              and pg.evaluate("innerWidth < 600 || Math.abs(document.querySelector('.ctl-u-kopf h1').getBoundingClientRect().top - document.querySelector('#ctl-u-tabs').getBoundingClientRect().top) < 30"))
        check(f'{breite}px {thema}: Rangliste mit zwei Bedienzeilen (Gliederung; Vergleich, ABC und Sortierung), Zeilen einzeilig', pg.evaluate(
              "innerWidth < 600 || (document.querySelector('#ctl-ua-rangfilter').contains(document.querySelector('#ctl-ua-rangnach')) && document.querySelector('#ctl-ua-liste').getBoundingClientRect().top - document.querySelector('.ctl-ua-rangpanel').getBoundingClientRect().top < 125)")
              and pg.evaluate("innerWidth < 600 || [...document.querySelectorAll('#ctl-ua-rang .ctl-ua-rangname')].every((e) => e.getBoundingClientRect().height < 26)"))
        check(f'{breite}px {thema}: Monatsverlauf als Balken mit Vorjahreslinie', pg.locator('#ctl-ua-diagramm rect.ctl-ua-balken').count() == 10 and pg.locator('#ctl-ua-diagramm polyline').count() == 1)
        check(f'{breite}px {thema}: Leiste – Zeitraum „Dieses Jahr“, Filter-Knopf, Suche', pg.get_attribute('#ctl-ua-zeit [data-zeit="jahr"]', 'aria-pressed') == 'true'
              and pg.is_visible('#ctl-ua-filterknopf') and pg.is_visible('#ctl-ua-suche') and pg.is_hidden('#ctl-ua-eigen'))
        rang = pg.locator('#ctl-ua-rang li').all_inner_texts()
        check(f'{breite}px {thema}: Rangliste zuerst nach Kundengruppen (Gastronomie, Großhandel, ohne)', pg.text_content('#ctl-ua-titel') == 'Rangliste · Kundengruppe' and len(rang) == 3
              and any('Gastronomie' in z for z in rang) and any('ohne Kundengruppe' in z for z in rang), rang)
        check(f'{breite}px {thema}: Größte Veränderungen zum Vorjahr', pg.is_visible('#ctl-ua-veraenderung-panel') and pg.locator('#ctl-ua-veraenderung [data-zeile]').count() >= 1)
        pg.click('#ctl-ua-nach [data-nach="vertreter"]')
        pg.wait_for_function("document.querySelector('#ctl-ua-titel').textContent === 'Rangliste · Vertreter'")
        rang = pg.locator('#ctl-ua-rang li').all_inner_texts()
        check(f'{breite}px {thema}: Rangliste nach Vertreter – drei Zeilen (V1, V2, ohne)', len(rang) == 3 and any('Vera Vertrieb' in z for z in rang) and any('ohne Vertreter' in z for z in rang), rang)
        wert_v1 = pg.text_content('#ctl-ua-rang [data-zeile="V1"] .ctl-ua-rangwert')
        pg.click('#ctl-ua-rang [data-zeile="V1"]')
        t = offen('vertreter')
        check(f'{breite}px {thema}: Klick auf Vertreter öffnet Pop-up mit seinen Kunden und Artikeln', 'Vera Vertrieb' in pg.text_content('#ctl-ua-d-titel')
              and pg.locator('#ctl-ua-dialog [data-ud-oeffnen="kunde"]').count() == 2 and 'Gasthaus Eiche' in t and 'Artikel nach Umsatz' in t
              and pg.locator('#ctl-ua-dialog [data-ud-diagramm] rect').count() == 10, t[:300])
        check(f'{breite}px {thema}: Pop-up-Umsatz = Zeile der Rangliste, Seite bleibt stehen', wert_v1 in pg.text_content('#ctl-ua-dialog .ctl-ud-kpi')
              and pg.text_content('#ctl-ua-titel') == 'Rangliste · Vertreter', (wert_v1, pg.text_content('#ctl-ua-dialog .ctl-ud-kpi')))
        if breite == 1280:
            pg.screenshot(path=SH + f'/controlling-umsatz-popup-vertreter-{breite}-{thema}.png')
        pg.click('#ctl-ua-dialog [data-ud-oeffnen="kunde"][data-wert="2000001"]')
        t = offen('kunde')
        check(f'{breite}px {thema}: Klick auf Kunde → Kunden-Pop-up mit seinen Artikeln', pg.text_content('#ctl-ua-d-titel') == 'Gasthaus Eiche' and 'Rinderhüfte' in t
              and 'Letzter Kauf' in t and 'Liefertage' in t and pg.is_visible('#ctl-ua-dialog [data-ud-zurueck]'), t[:300])
        check(f'{breite}px {thema}: Kunden-Pop-up – Preisniveau und Ø Preis je Artikel zum Ø aller Kunden', 'Preisniveau' in pg.text_content('#ctl-ua-dialog [data-ud-preisniveau]')
              and pg.locator('#ctl-ua-dialog button.ctl-ud-zeile.artikel .ctl-ud-preisabw').count() >= 3, pg.text_content('#ctl-ua-dialog .ctl-ud-reiterinhalt')[:300])
        pg.fill('#ctl-ua-dialog [data-ud-suche]', 'hüfte')
        pg.wait_for_function("document.querySelectorAll('#ctl-ua-dialog button.ctl-ud-zeile.artikel').length === 1")
        check(f'{breite}px {thema}: Artikel des Kunden suchen', 'Rinderhüfte' in pg.text_content('#ctl-ua-dialog button.ctl-ud-zeile.artikel')
              and pg.evaluate("document.activeElement.matches('[data-ud-suche]')"))
        pg.click('#ctl-ua-dialog [data-ud-reiter="lieferungen"]')
        pg.wait_for_selector('#ctl-ua-dialog .ctl-ud-zeile.tage:not(.kopf)')
        check(f'{breite}px {thema}: Reiter Lieferungen mit Liefertagen', pg.locator('#ctl-ua-dialog .ctl-ud-zeile.tage:not(.kopf)').count() > 3)
        if breite == 390:
            dw = pg.evaluate("(() => { const d = document.querySelector('#ctl-ua-dialog'); return [d.getBoundingClientRect().width, d.scrollWidth, d.getBoundingClientRect().bottom]; })()")
            check('390px: Pop-up als Blatt von unten, volle Breite, ohne waagerechtes Scrollen', abs(dw[0] - 390) <= 1 and dw[1] <= 391 and abs(dw[2] - 900) <= 1, dw)
            pg.click('#ctl-ua-dialog [data-ud-reiter="artikel"]')
            pg.wait_for_selector('#ctl-ua-dialog button.ctl-ud-zeile.artikel')
            pg.screenshot(path=SH + f'/controlling-umsatz-popup-kunde-{breite}-{thema}.png')
        else:
            pg.click('#ctl-ua-dialog [data-ud-reiter="artikel"]')
            pg.wait_for_selector('#ctl-ua-dialog button.ctl-ud-zeile.artikel')
            pg.screenshot(path=SH + f'/controlling-umsatz-popup-kunde-{breite}-{thema}.png')
        pg.click('#ctl-ua-dialog [data-ud-zurueck]')
        offen('vertreter')
        pg.click('#ctl-ua-dialog [data-ud-filter]')
        pg.wait_for_function("!document.querySelector('#ctl-ua-dialog').open && document.querySelector('#ctl-ua-filterzahl').textContent === '1'")
        pg.wait_for_function("document.querySelectorAll('#ctl-ua-rang li').length === 1")
        check(f'{breite}px {thema}: „Als Filter übernehmen“ setzt den Filter der Seite', 'Vertreter: V1 – Vera Vertrieb' in pg.inner_text('#ctl-ua-chips'), pg.inner_text('#ctl-ua-chips'))
        if breite == 1280:
            pg.screenshot(path=SH + f'/controlling-umsatzdaten-{breite}-{thema}.png', full_page=True)
            with pg.expect_download() as dl:
                pg.click('#ctl-ua-csv')
            text = open(dl.value.path(), encoding='utf-8-sig').read()
            check('CSV: Kopf, Zeilen, deutsche Zahlen', text.startswith('"Vertreter";"Nummer";"Umsatz €"') and 'Vera Vertrieb' in text and re.search(r'"\d+,\d{2}"', text), text[:200])
        pg.click('#ctl-ua-zuruecksetzen')
        pg.wait_for_function("document.querySelector('#ctl-ua-filterzahl').hidden && document.querySelectorAll('#ctl-ua-rang li').length === 3")
        pg.click('#ctl-ua-nach [data-nach="kunde"]')
        pg.wait_for_function("document.querySelector('#ctl-ua-titel').textContent === 'Rangliste · Kunde'")
        pg.click('#ctl-ua-ansicht [data-ansicht="tabelle"]')
        pg.wait_for_selector('#ctl-ua-zeilen tr[data-zeile]')
        kopf = pg.text_content('#ctl-ua-kopf')
        check(f'{breite}px {thema}: Ansicht „Alle Spalten“ mit DB und Spanne', 'Menge' in kopf and 'DB' in (kopf) and 'Spanne' in kopf and pg.locator('#ctl-ua-zeilen tr').count() == 5, kopf)
        if breite == 1280:
            pg.click('#ctl-ua-kopf [data-sort="name"]')
            pg.wait_for_function("document.querySelector('#ctl-ua-kopf [data-sort=\"name\"]').textContent.endsWith('↑')")
            namen = pg.locator('#ctl-ua-zeilen .ctl-ua-name').all_inner_texts()
            check('Sortierung nach Name (aufsteigend)', namen == sorted(namen, key=str.lower), namen)
        pg.click('#ctl-ua-ansicht [data-ansicht="rang"]')
        pg.wait_for_selector('#ctl-ua-rang li')
        # Rangliste nach DB: Reihenfolge wie die API, Richtung umkehren, Spanne mit Prozentpunkten
        jahr = {'von': f'{LETZTER.year}-01', 'bis': LETZTER.strftime('%Y-%m'), 'nach': 'kunde'}
        reihe = lambda: pg.eval_on_selector_all('#ctl-ua-rang li > button[data-zeile]', 'els => els.map((e) => e.dataset.zeile)')   # noqa: E731
        pg.click('#ctl-ua-rangnach [data-rang="db"]')
        pg.wait_for_selector('#ctl-ua-rang[data-rang="db"]')
        soll = [z['schluessel'] for z in auswertung(A, **jahr, rang='db')[1]['zeilen']]
        check(f'{breite}px {thema}: Rangliste Kunden nach DB – Reihenfolge des Servers, Wert und Spanne je Zeile', reihe() == soll
              and 'DB' in (pg.text_content('.ctl-ua-rangkopfzeile')) and ' von ' in pg.text_content('#ctl-ua-rang .ctl-ua-rangwert small'), (reihe(), soll))
        pg.click('#ctl-ua-richtung')
        pg.wait_for_function("document.querySelector('#ctl-ua-richtung').getAttribute('aria-pressed') === 'true' && document.querySelector('#ctl-ua-rang')")
        soll = [z['schluessel'] for z in auswertung(A, **jahr, rang='db', auf='1')[1]['zeilen']]
        check(f'{breite}px {thema}: DB – niedrigste zuerst', reihe() == soll and 'niedrigste' in pg.text_content('#ctl-ua-richtung'), (reihe(), soll))
        pg.click('#ctl-ua-rangnach [data-rang="spanne"]')
        pg.wait_for_selector('#ctl-ua-rang[data-rang="spanne"]')
        check(f'{breite}px {thema}: Spanne – wieder höchste zuerst, Veränderung in Prozentpunkten', pg.get_attribute('#ctl-ua-richtung', 'aria-pressed') == 'false'
              and 'Pp' in pg.text_content('#ctl-ua-rang') and reihe() == [z['schluessel'] for z in auswertung(A, **jahr, rang='spanne')[1]['zeilen']])
        pg.click('#ctl-ua-rangnach [data-rang="db"]')
        pg.wait_for_selector('#ctl-ua-rang[data-rang="db"]')
        pg.click('#ctl-ua-rang [data-zeile="2000001"]')
        offen('kunde')
        det = A.call('controlling_umsatz_detail&' + urllib.parse.urlencode({**jahr, 'dim': 'kunde', 'wert': '2000001'}))[1]
        soll = [z['name'] for z in sorted([z for z in det['artikel'] if z['kaeufe']], key=lambda z: -(z['werte']['umsatzEk'] - z['werte']['ek']))]
        ist = pg.eval_on_selector_all('#ctl-ua-dialog button.ctl-ud-zeile.artikel .ctl-ud-name b', 'els => els.map((e) => e.textContent)')
        check(f'{breite}px {thema}: Pop-up Kunde – Artikel nach DB (Vorgabe aus der Rangliste), DB-Spalten', pg.eval_on_selector('#ctl-ua-dialog [data-ud-rang]', 'e => e.value') == 'db'
              and ist == soll and 'DB' in (pg.text_content('#ctl-ua-dialog .ctl-ud-zeile.kopf')), (ist, soll))
        if breite == 1280:
            pg.screenshot(path=SH + f'/controlling-umsatz-db-kunde-{breite}-{thema}.png')
        pg.select_option('#ctl-ua-dialog [data-ud-rang]', 'menge')
        pg.wait_for_function("document.querySelector('#ctl-ua-dialog [data-ud-rang]').value === 'menge'")
        soll = [z['name'] for z in sorted([z for z in det['artikel'] if z['kaeufe']], key=lambda z: -z['werte']['menge'])]
        check(f'{breite}px {thema}: Pop-up – Artikel nach Menge umsortiert', pg.eval_on_selector_all('#ctl-ua-dialog button.ctl-ud-zeile.artikel .ctl-ud-name b', 'els => els.map((e) => e.textContent)') == soll)
        pg.keyboard.press('Escape')
        pg.wait_for_function("!document.querySelector('#ctl-ua-dialog').open")
        if breite == 1280:
            pg.screenshot(path=SH + f'/controlling-umsatz-rangliste-db-{breite}-{thema}.png', full_page=True)
        pg.click('#ctl-ua-rangnach [data-rang="umsatz"]')
        pg.wait_for_selector('#ctl-ua-rang[data-rang="umsatz"]')
        # ABC-Analyse und Neu/Verloren (Juni 2026: Kunde 2000004 nur mit Gutschrift)
        pg.click('#ctl-ua-zeit [data-zeit="eigen"]')
        pg.select_option('#ctl-ua-von', '2026-06')
        pg.select_option('#ctl-ua-bis', '2026-06')
        pg.wait_for_function("document.querySelector('#ctl-ua-tabelle-hinweis').textContent.startsWith('Juni 2026 – Juni 2026') && !document.querySelector('#ctl-ua-liste').classList.contains('laedt')")
        juni = auswertung(A, von='2026-06', bis='2026-06', nach='kunde')[1]
        abc_ist = pg.eval_on_selector_all('#ctl-ua-rang li > button[data-zeile]', 'els => Object.fromEntries(els.map((e) => [e.dataset.zeile, e.dataset.abc || null]))')
        check(f'{breite}px {thema}: ABC-Kennzeichen je Kunde wie der Server, Auswahl A/B/C mit Anzahl', abc_ist == {z['schluessel']: z.get('abc') for z in juni['zeilen']}
              and pg.locator('#ctl-ua-rang .ctl-ua-abcmarke').count() == len(juni['zeilen']) and 'ABC nach Umsatz' in pg.text_content('#ctl-ua-abc')
              and pg.text_content('#ctl-ua-abc [data-abc="A"]').startswith(f"A {juni['abc']['A']['anzahl']}"), (abc_ist, pg.text_content('#ctl-ua-abc')))
        check(f'{breite}px {thema}: Kennzeichen „verloren“ in der Zeile, Zahlen an Neu/Verloren', pg.is_visible('#ctl-ua-rang [data-zeile="2000004"] .ctl-ua-marke.verloren')
              and pg.text_content('#ctl-ua-nur [data-nur="verloren"]') == f"Verloren {juni['wechsel']['verloren']['anzahl']}", pg.text_content('#ctl-ua-nur'))
        pg.wait_for_selector('#ctl-ua-pausen [data-pause="2000004"]')
        p_soll = pausen(A, von='2026-06', bis='2026-06')[1]
        check(f'{breite}px {thema}: Bestellpausen – Liste wie der Server, Imbiss Ohne mit „seit … Tagen nichts“, Stand 30.06.2026',
              pg.eval_on_selector_all('#ctl-ua-pausen [data-pause]', 'els => els.map((e) => e.dataset.pause)') == [z['nr'] for z in p_soll['zeilen']][:5]
              and 'seit' in pg.text_content('#ctl-ua-pausen [data-pause="2000004"]') and 'Stand 30.06.2026' in pg.text_content('#ctl-ua-pausen-hinweis')
              and pg.text_content('#ctl-ua-pausen-zahl') == str(p_soll['gesamt']), pg.text_content('#ctl-ua-pausen-panel'))
        if breite == 390:
            pg.locator('#ctl-ua-pausen-panel').screenshot(path=SH + f'/controlling-umsatz-pausen-{breite}-{thema}.png')
        pg.click('#ctl-ua-pausen [data-pause="2000004"]')
        offen('kunde')
        check(f'{breite}px {thema}: Klick auf eine Bestellpause öffnet den Kunden mit Hinweis „Bestellpause“', pg.text_content('#ctl-ua-d-titel') == 'Imbiss Ohne'
              and 'Bestellpause' in pg.text_content('#ctl-ua-dialog .ctl-ud-kpis'), pg.text_content('#ctl-ua-dialog .ctl-ud-kpis'))
        pg.keyboard.press('Escape')
        pg.wait_for_function("!document.querySelector('#ctl-ua-dialog').open")
        pg.click('#ctl-ua-abc [data-abc="A"]')
        pg.wait_for_function("document.querySelector('#ctl-ua-abc [data-abc=\"A\"]').getAttribute('aria-pressed') === 'true'")
        check(f'{breite}px {thema}: Klick auf A zeigt nur die A-Kunden (Platz bleibt)', set(reihe()) == {z['schluessel'] for z in juni['zeilen'] if z.get('abc') == 'A'}
              and pg.is_visible('#ctl-ua-nurhinweis') and pg.text_content('#ctl-ua-rang .ctl-ua-rangnr').startswith('1'), reihe())
        pg.click('#ctl-ua-abc [data-abc="A"]')
        pg.wait_for_function(f"document.querySelectorAll('#ctl-ua-rang li > button').length === {len(juni['zeilen'])}")
        pg.click('#ctl-ua-nur [data-nur="verloren"]')
        pg.wait_for_selector('#ctl-ua-rang[data-nur="verloren"]')
        soll = [z['schluessel'] for z in auswertung(A, von='2026-06', bis='2026-06', nach='kunde', nur='verloren')[1]['zeilen']]
        check(f'{breite}px {thema}: Verloren – nur Kunden ohne Kauf im Juni, Werte aus dem Vorjahr, ohne ABC', reihe() == soll and '2000004' in soll
              and 'Umsatz Vorjahr' in pg.text_content('.ctl-ua-rangkopfzeile') and 'Im Vorjahreszeitraum gekauft, jetzt nicht' in pg.inner_text('#ctl-ua-nurhinweis')
              and pg.is_hidden('#ctl-ua-abc') and 'verloren' in pg.text_content('#ctl-ua-rang .ctl-ua-rangdelta'), (reihe(), soll))
        pg.screenshot(path=SH + f'/controlling-umsatz-verloren-{breite}-{thema}.png', full_page=breite == 1280)
        pg.click('#ctl-ua-nur [data-nur=""]')
        pg.wait_for_selector('#ctl-ua-rang[data-nur=""]')
        pg.screenshot(path=SH + f'/controlling-umsatz-abc-{breite}-{thema}.png', full_page=breite == 1280)
        pg.click('#ctl-ua-zeit [data-zeit="jahr"]')
        pg.wait_for_function("document.querySelector('#ctl-ua-tabelle-hinweis').textContent.startsWith('Januar 2026') && !document.querySelector('#ctl-ua-liste').classList.contains('laedt')")
        # Suche öffnet das Pop-up
        pg.fill('#ctl-ua-suche', 'kantine')
        pg.wait_for_function("document.querySelectorAll('#ctl-ua-treffer [role=\"option\"]').length === 1")
        pg.press('#ctl-ua-suche', 'Enter')
        offen('kunde')
        check(f'{breite}px {thema}: Suche nach Kunde öffnet sein Pop-up', pg.text_content('#ctl-ua-d-titel') == 'Kantine Süd')
        pg.keyboard.press('Escape')
        pg.wait_for_function("!document.querySelector('#ctl-ua-dialog').open")
        pg.fill('#ctl-ua-suche', '40300')
        pg.wait_for_function("[...document.querySelectorAll('#ctl-ua-treffer [role=\"option\"]')].some((o) => o.textContent.includes('Kalbsrücken'))")
        pg.click('#ctl-ua-treffer [role="option"]:has-text("Kalbsrücken")')
        t = offen('artikel')
        check(f'{breite}px {thema}: Suche nach Artikelnummer → Pop-up „Wer kauft diesen Artikel?“', 'Wer kauft diesen Artikel?' in t and pg.locator('#ctl-ua-dialog [data-ud-oeffnen="kunde"]').count() >= 3, t[:200])
        # Preisspiegel: Käufer nach Ø Preis, günstigster zuerst
        pg.select_option('#ctl-ua-dialog [data-ud-rang]', 'preis')
        pg.wait_for_function("document.querySelector('#ctl-ua-dialog [data-ud-rang]').value === 'preis'")
        pg.click('#ctl-ua-dialog [data-ud-richtung]')
        pg.wait_for_function("document.querySelector('#ctl-ua-dialog [data-ud-richtung]').getAttribute('aria-pressed') === 'true'")
        art = A.call('controlling_umsatz_detail&' + urllib.parse.urlencode({'von': f'{LETZTER.year}-01', 'bis': LETZTER.strftime('%Y-%m'), 'dim': 'artikel', 'wert': '40300'}))[1]
        soll = [z['nr'] for z in sorted([z for z in art['kunden'] if z['werte']['menge'] > 0], key=lambda z: z['werte']['umsatz'] / z['werte']['menge'])]
        ist = pg.eval_on_selector_all('#ctl-ua-dialog button.ctl-ud-zeile[data-ud-oeffnen="kunde"]', 'els => els.map((e) => e.dataset.wert)')
        check(f'{breite}px {thema}: Artikel-Pop-up – Ø Preis je Käufer mit Abweichung vom Ø, sortierbar nach Ø Preis (günstigster zuerst)', ist[:len(soll)] == soll
              and 'Ø Preis' in pg.text_content('#ctl-ua-dialog .ctl-ud-zeile.kopf') and pg.locator('#ctl-ua-dialog .ctl-ud-preisabw').count() >= 3
              and 'Ø Preis' in pg.text_content('#ctl-ua-dialog .ctl-ud-kpis'), (ist, soll))
        if breite == 390:
            pg.screenshot(path=SH + f'/controlling-umsatz-preisspiegel-{breite}-{thema}.png')
        elif breite == 1280:
            pg.screenshot(path=SH + f'/controlling-umsatz-preisspiegel-{breite}-{thema}.png')
        pg.click('#ctl-ua-dialog .dlg-head [data-schliessen]')
        pg.wait_for_function("!document.querySelector('#ctl-ua-dialog').open")
        # Filter im Pop-up
        pg.click('#ctl-ua-filterknopf')
        pg.wait_for_selector('#ctl-ua-filterdialog[open]')
        pg.click('#ctl-ua-filterdialog [data-fchip="fa"][data-wert="Rind"]')
        pg.fill('#ctl-ua-filterdialog [data-ftoken="k"]', 'eiche')
        pg.click('#ctl-ua-filterdialog [data-tokdazu="k"][data-wert="2000001"]')
        check(f'{breite}px {thema}: Filter-Pop-up – Auswahl erst mit „Anwenden“', pg.text_content('#ctl-ua-fanwenden') == '2 Filter anwenden' and pg.is_hidden('#ctl-ua-filterzahl'))
        if breite == 390:
            pg.screenshot(path=SH + f'/controlling-umsatz-filter-{breite}-{thema}.png')
        pg.click('#ctl-ua-fanwenden')
        pg.wait_for_function("!document.querySelector('#ctl-ua-filterdialog').open && document.querySelector('#ctl-ua-filterzahl').textContent === '2'")
        pg.wait_for_function("document.querySelectorAll('#ctl-ua-rang li').length === 1")
        check(f'{breite}px {thema}: Filter angewandt (Fleischart und Kunde als Chips)', 'Fleischart: Rind' in pg.inner_text('#ctl-ua-chips') and 'Gasthaus Eiche' in pg.inner_text('#ctl-ua-rang'))
        pg.click('#ctl-ua-zuruecksetzen')
        pg.wait_for_function("document.querySelector('#ctl-ua-filterzahl').hidden")
        bw = pg.evaluate('document.documentElement.scrollWidth')
        check(f'{breite}px {thema}: kein waagerechtes Scrollen der Seite', bw <= breite + 1, bw)
        if breite == 390:
            pg.screenshot(path=SH + f'/controlling-umsatzdaten-{breite}-{thema}.png', full_page=True)
        if breite == 1280:
            # Ansicht merken: nach dem Neuladen gleiche Gliederung, Kennzahl, Zeitraum und Filter; „Standardansicht“ setzt zurück
            fertig = "!document.querySelector('#ctl-ua-liste').classList.contains('laedt')"
            pg.click('#ctl-ua-nach [data-nach="artikel"]')
            pg.wait_for_function("document.querySelector('#ctl-ua-titel').textContent === 'Rangliste · Artikel'")
            pg.click('#ctl-ua-rangnach [data-rang="menge"]')
            pg.wait_for_selector('#ctl-ua-rang[data-rang="menge"]')
            pg.click('#ctl-ua-zeit [data-zeit="12"]')
            pg.wait_for_function("document.querySelector('#ctl-ua-zeit [data-zeit=\"12\"]').getAttribute('aria-pressed') === 'true' && " + fertig)
            pg.click('#ctl-ua-filterknopf'); pg.wait_for_selector('#ctl-ua-filterdialog[open]')
            pg.click('#ctl-ua-filterdialog [data-fchip="v"][data-wert="V1"]'); pg.click('#ctl-ua-fanwenden')
            pg.wait_for_function("document.querySelector('#ctl-ua-filterzahl').textContent === '1' && " + fertig)
            schluessel = lambda: pg.evaluate("Object.keys(localStorage).filter((k) => k.startsWith('controlling.umsatz.ansicht'))")   # noqa: E731
            check('Ansicht merken: im Browser je Mitarbeiter gespeichert, „Standardansicht“ sichtbar', schluessel() == ['controlling.umsatz.ansicht.admin'] and pg.is_visible('#ctl-ua-standard'), schluessel())
            pg.reload(); pg.wait_for_selector('#ctl-ua-rang li')
            pg.wait_for_function(fertig)
            check('Ansicht merken: nach dem Neuladen Artikel, Menge, 12 Monate und Filter Vertreter V1', pg.text_content('#ctl-ua-titel') == 'Rangliste · Artikel'
                  and pg.get_attribute('#ctl-ua-rangnach [data-rang="menge"]', 'aria-pressed') == 'true' and pg.get_attribute('#ctl-ua-zeit [data-zeit="12"]', 'aria-pressed') == 'true'
                  and 'Vertreter: V1 – Vera Vertrieb' in pg.inner_text('#ctl-ua-chips') and pg.get_attribute('#ctl-ua-rang', 'data-rang') == 'menge', pg.inner_text('#ctl-ua-chips'))
            pg.click('#ctl-ua-standard')
            pg.wait_for_function("document.querySelector('#ctl-ua-titel').textContent === 'Rangliste · Kundengruppe' && document.querySelector('#ctl-ua-filterzahl').hidden && " + fertig)
            check('Standardansicht: Kundengruppen, Umsatz, dieses Jahr, ohne Filter – nichts mehr gespeichert', pg.get_attribute('#ctl-ua-zeit [data-zeit="jahr"]', 'aria-pressed') == 'true'
                  and pg.get_attribute('#ctl-ua-rangnach [data-rang="umsatz"]', 'aria-pressed') == 'true' and pg.is_hidden('#ctl-ua-standard') and schluessel() == [], schluessel())
            pg.evaluate("localStorage.setItem('controlling.umsatz.ansicht.admin', '{kaputt')")
            pg.reload(); pg.wait_for_selector('#ctl-ua-rang li')
            check('Ansicht merken: unlesbarer Speicher → Standardansicht', pg.text_content('#ctl-ua-titel') == 'Rangliste · Kundengruppe')
        pg.click('#ctl-u-tabs [data-tab="uebersicht"]')
        check(f'{breite}px {thema}: Monatsmeldung weiter erreichbar', pg.is_visible('#ctl-u-uebersicht') and pg.url.endswith('#umsatz/uebersicht'))
        ctx.close()

    # nur ansehen: keine EK-Spalten, auch nicht im Pop-up
    ctx = br.new_context(viewport={'width': 1280, 'height': 900})
    pg = ctx.new_page()
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto(BASE + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', 'sam'); pg.fill('#pw1', 'Sehen-Konto-34'); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
    pg.goto(BASE + '/module/controlling/#umsatz'); pg.wait_for_selector('#ctl-ua-rang li')
    pg.click('#ctl-ua-ansicht [data-ansicht="tabelle"]'); pg.wait_for_selector('#ctl-ua-zeilen tr[data-zeile]')
    kopf = pg.text_content('#ctl-ua-kopf')
    check('nur ansehen: ohne DB und Spanne (Tabelle, Kennzahlen, Auswahl der Rangliste)', 'DB' not in kopf and 'Spanne' not in kopf and 'DB' not in pg.text_content('#ctl-ua-kpis') and 'Spanne' not in pg.text_content('#ctl-ua-kpis')
          and pg.locator('#ctl-ua-rangnach [data-rang]').count() == 2 and pg.locator('#ctl-ua-rangnach [data-rang="db"]').count() == 0, kopf)
    pg.click('#ctl-ua-zeilen tr[data-zeile="10"]')
    t = offen('kundengruppe')
    check('nur ansehen: Pop-up ohne DB und Spanne, mit Ø Preis, Sortierung ohne DB', 'DB' not in t and 'Spanne' not in t and 'Ø Preis' in t and 'Gastronomie' in pg.text_content('#ctl-ua-d-titel')
          and pg.eval_on_selector_all('#ctl-ua-dialog [data-ud-rang] option', 'els => els.map((e) => e.value)') == ['umsatz', 'menge', 'preis'], t[:200])
    # gemerkte Ansicht mit DB und unbekannten Filterwerten: ohne EK-Recht Umsatz, nur vorhandene Filterwerte
    pg.evaluate("""localStorage.setItem('controlling.umsatz.ansicht.sam', JSON.stringify({ v: 1, nach: 'kunde', rang: 'db', auf: true, vj: true, ansicht: 'rang', kennzahl: 'db',
                   zeit: 'eigen', von: '2026-06', bis: '2026-06', filter: { k: ['9999999', '2000001', '2000004'], v: ['V9'] }, nur: 'verloren' }))""")
    pg.reload(); pg.wait_for_selector('#ctl-ua-rang[data-nur="verloren"]')
    st, r = auswertung(SAM, von='2026-06', bis='2026-06', nach='kunde', k='2000001,2000004', nur='verloren', auf='1')
    check('nur ansehen: gemerkte DB wird zu Umsatz, unbekannte Filterwerte entfallen, Zeitraum und Verloren bleiben', pg.get_attribute('#ctl-ua-rangnach [data-rang="umsatz"]', 'aria-pressed') == 'true'
          and pg.get_attribute('#ctl-ua-nur [data-nur="verloren"]', 'aria-pressed') == 'true' and pg.text_content('#ctl-ua-filterzahl') == '2'
          and pg.eval_on_selector('#ctl-ua-kennzahl', 'e => e.value') == 'umsatz' and pg.eval_on_selector_all('#ctl-ua-rang li > button[data-zeile]', 'els => els.map((e) => e.dataset.zeile)') == [z['schluessel'] for z in r['zeilen']],
          (pg.inner_text('#ctl-ua-chips'), r.get('zeilen')))
    ctx.close()
    br.close()
check('keine JavaScript-Fehler', not errors, errors[:3])

print(f'\n{sum(res)}/{len(res)} passed')
