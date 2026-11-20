#!/usr/bin/env python3
"""Rechenkern der Kalkulation je Container (app/api/module/containerimport/kalkulation.php) gegen von Hand nachgerechnete
Erwartungen – jede Formel einzeln, mit erfundenen Zahlen (GR-007).

Fall „Grundfall“ (Kurs 1,25 USD/€, 4.000 kg, Teil A: zwei Hilton-Positionen Ursprung UY, Teil B: Mercosur-Kontingent UY und
Drittlandszoll AR gefroren): Seefracht 2.500 USD = 2.000 € → 0,50 €/kg; Versicherungswert je Teil mit Frachtanteil nach kg;
Prämie je kg des Teils; Einkaufsprovision 50 €/t nicht im Zollwert; Nebenkosten (Nachlauf, Finanzierung, Zahlungskosten,
Zuschlag) je kg; Ist, Soll, VK, Rohertrag, Marge, Aufschlag, Rückvergütung, WKZ, Rohgewinn; Kontingente mit
Schlachtkörperäquivalent; Zoll je Regime; Vergleich mit/ohne Mercosur-Kontingent; anteilig Hilton.
Grenzfälle: Provision im Zollwert, kein Kurs, 0 kg, Teil ohne Gewicht, Position ohne Gewicht, kein VK, Drittland ohne
KN-Code, gekühlt/gefroren, EU-Ursprung, falsches Ursprungsland für Hilton/Mercosur, Hilton vor dem Stichtag, Satz
überschrieben (mit/ohne Vermerk), anderer Satz, Seefracht in €, Imag. EK weicht ab, ungültige Eingaben.

  python3 tests/unit/test_ci_kalkulation.py
"""
import copy
import json
import os
import subprocess

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..'))
PASS = FAIL = 0


def check(name, ok, info=''):
    global PASS, FAIL
    if ok:
        PASS += 1; print('PASS', name)
    else:
        FAIL += 1; print('FAIL', name, str(info)[:600])


def rechnen(eingabe, saetze=None):
    r = subprocess.run(['php', os.path.join(REPO, 'tests', 'unit', 'ci_kalkulation.php')], input=json.dumps({'eingabe': eingabe, 'saetze': saetze}),
                       capture_output=True, text=True, check=True)
    return json.loads(r.stdout)


def nahe(a, b, eps=1e-9):
    return a is not None and abs(a - b) <= eps * max(1.0, abs(b))


def texte(r, stufe=None):
    return [h['text'] for h in r['ergebnis']['hinweise'] if stufe is None or h['stufe'] == stufe]


GRUND = {
    'kopf': {'kurs': 1.25, 'datum': '2026-10-01', 'seefracht': 2500, 'seefrachtWaehrung': 'USD', 'provisionT': 50, 'provisionEinkauf': True,
             'nachlauf': 1000, 'nachlaufKg': 0.10, 'zins': 6, 'tage': 60, 'zahlPromille': 2, 'zahlFix': 40, 'imagGewinn': 10},
    'teile': [{'id': 'a', 'name': 'Teil A', 'abnehmer': 'Kunde Beispiel', 'versicherung': 0.5, 'rueckverguetung': 1, 'wkz': 100},
              {'id': 'b', 'name': 'Teil B', 'versicherung': 0.4}],
    'positionen': [
        {'teil': 'a', 'artikel': 'Roastbeef', 'rl': True, 'regime': 'hilton', 'land': 'UY', 'kn': '0201 30 00', 'kartons': 10, 'brutto': 1050, 'netto': 1000, 'preis': 12.5, 'waehrung': 'USD', 'imagEk': 11, 'vk': 13},
        {'teil': 'a', 'artikel': 'Entrecote', 'regime': 'hilton', 'land': 'UY', 'kn': '02013000', 'kartons': 5, 'brutto': 520, 'netto': 500, 'preis': 15, 'waehrung': 'EUR', 'imagEk': 20, 'vk': 18},
        {'teil': 'b', 'artikel': 'roastbeef ', 'rl': True, 'regime': 'mercosur', 'land': 'UY', 'kn': '02013000', 'kartons': 20, 'brutto': 2080, 'netto': 2000, 'preis': 10, 'waehrung': 'USD'},
        {'teil': 'b', 'artikel': 'Hüfte', 'regime': 'drittland', 'land': 'AR', 'kn': '02023090', 'kartons': 5, 'brutto': 520, 'netto': 500, 'preis': 8, 'waehrung': 'EUR'},
    ],
}

# ---------- Grundfall ----------
r = rechnen(GRUND)
e = r['ergebnis']
check('Grundfall vollständig gerechnet', e['vollstaendig'], e['hinweise'])
check('Eingabe ist nach der Prüfung stabil (zweimal geprüft = gleich)', r['nochmal'])
check('KN-Code ohne Leerzeichen gespeichert', r['eingabe']['positionen'][0]['kn'] == '02013000')
g = e['gesamt']
check('Seefracht 2.500 USD / 1,25 = 2.000 €; Fracht/kg = 2.000 / 4.000 kg = 0,50', nahe(g['seefracht'], 2000) and nahe(g['frachtKg'], 0.5))
check('Provision 50 €/t = 0,05 €/kg', nahe(g['provisionKg'], 0.05))
check('Finanzierung = Warenwert 37.500 € × 6 % × 60/360 = 375', nahe(g['finanzierung'], 375))
check('Zahlungskosten = 37.500 × 2 ‰ + 40 = 115', nahe(g['zahlungskosten'], 115))
check('Nebenkosten/kg = (1.000 + 375 + 115) / 4.000 + 0,10 = 0,4725', nahe(g['nebenkostenKg'], 0.4725))
ta, tb = e['teile']
check('Teil A: Vers.-Wert = (17.500 + 2.000 × 1.500/4.000) × 1,1 = 20.075; Prämie 0,5 % = 100,375; je kg 100,375/1.500',
      nahe(ta['frachtanteil'], 750) and nahe(ta['versWert'], 20075) and nahe(ta['praemie'], 100.375) and nahe(ta['versKg'], 100.375 / 1500), ta)
check('Teil B: Vers.-Wert = (20.000 + 1.250) × 1,1 = 23.375; Prämie 0,4 % = 93,5; je kg 0,0374',
      nahe(tb['versWert'], 23375) and nahe(tb['praemie'], 93.5) and nahe(tb['versKg'], 0.0374), tb)
p1, p2, p3, p4 = e['positionen']
vA = 100.375 / 1500
check('Pos. 1: Preis 12,50 USD = 10 €; Hilton Ursprung UY ab 01.05.2026 = 0 %', nahe(p1['preisEur'], 10) and p1['satz'] == 'hilton_mercosur' and p1['zollKg'] == 0 and nahe(p1['betragUsd'], 12500))
check('Pos. 1: Zollwert ohne Einkaufsprovision = 10 + 0,50 + Vers./kg', nahe(p1['zollwertKg'], 10.5 + vA))
check('Pos. 1: Einstand = 10 + 0,50 + Vers./kg + 0,05 + 0 + 0,4725; Ist = × 1.000 kg',
      nahe(p1['einstandVorNkKg'], 10.55 + vA) and nahe(p1['einstandKg'], 11.0225 + vA) and nahe(p1['ist'], (11.0225 + vA) * 1000))
check('Pos. 1: Soll = 11 × 1.000, VK-Wert = 13 × 1.000, Anteil am Teil 1.000/1.500', nahe(p1['soll'], 11000) and nahe(p1['vkWert'], 13000) and nahe(p1['anteilTeil'], 2 / 3))
check('Pos. 2: Preis in € bleibt 15; kein Betrag in USD', nahe(p2['preisEur'], 15) and p2['betragUsd'] is None and nahe(p2['einstandKg'], 16.0225 + vA))
check('Pos. 3: Mercosur 7,5 % auf Zollwert 8 + 0,50 + 0,0374 = 8,5374 → 0,640305 €/kg; SKE = 2.000 × 1,3',
      p3['satz'] == 'mercosur' and nahe(p3['zollwertKg'], 8.5374) and nahe(p3['zollKg'], 0.640305) and nahe(p3['ske'], 2600) and nahe(p3['einstandKg'], 8.5874 + 0.640305 + 0.4725))
check('Pos. 4: Drittland gefroren 12,8 % + 304,1 €/100 kg → 8,5374 × 0,128 + 3,041', p4['satz'] == 'drittland_gefroren' and nahe(p4['zollKg'], 8.5374 * 0.128 + 3.041) and p4['ske'] is None)
istA = (11.0225 + vA) * 1000 + (16.0225 + vA) * 500
check('Teil A: Kartons, Brutto, Netto, R/L (nur Roastbeef), USD-Betrag, Warenwert',
      [ta['kartons'], ta['brutto'], ta['netto'], ta['rl']] == [15, 1570, 1500, 1000] and nahe(ta['betragUsd'], 12500) and nahe(ta['warenwert'], 17500), ta)
check('Teil A: Ist, Soll, VK 22.000, Rohertrag = VK − Ist', nahe(ta['ist'], istA) and nahe(ta['soll'], 21000) and nahe(ta['vkWert'], 22000) and nahe(ta['rohertrag'], 22000 - istA))
check('Teil A: Marge vom VK, Aufschlag vom Ist, € je kg', nahe(ta['marge'], (22000 - istA) / 22000) and nahe(ta['aufschlag'], (22000 - istA) / istA) and nahe(ta['eurKg'], (22000 - istA) / 1500))
check('Teil A: Rückvergütung 1 % von 22.000 = 220, WKZ 100, Rohgewinn = Rohertrag − 220 − 100',
      nahe(ta['rueckverguetung'], 220) and nahe(ta['wkz'], 100) and nahe(ta['rohgewinn'], 22000 - istA - 320))
check('Teil B ohne VK: kein Rohertrag, keine Marge, kein Soll – „VK fehlt“',
      tb['vkWert'] is None and tb['rohertrag'] is None and tb['marge'] is None and tb['soll'] is None and tb['rohgewinn'] is None
      and any('Teil B' in t and 'VK fehlt' in t for t in texte(r)))
check('Gesamt ohne vollständigen VK: kein Rohertrag', g['vkWert'] is None and g['rohertrag'] is None and g['rohgewinn'] is None)
check('Gesamt: Netto 4.000, Ist = Summe der Positionen', g['netto'] == 4000 and nahe(g['ist'], sum(p['ist'] for p in e['positionen'])))
check('Zoll je Regime', nahe(e['zollJeRegime']['hilton'], 0) and nahe(e['zollJeRegime']['mercosur'], 0.640305 * 2000) and nahe(e['zollJeRegime']['drittland'], (8.5374 * 0.128 + 3.041) * 500))
check('Kontingente: Hilton 1.500 kg, Mercosur 2.000 kg = 2.600 kg SKE', e['kontingente'] == {'hilton': 1500, 'mercosur': 2000, 'mercosurSke': 2600}, e['kontingente'])
v = e['vergleich']
ohne = (8.5374 * 0.128 + 3.034) * 2000 + (8.5374 * 0.128 + 3.041) * 500
check('Vergleich No-Hilton (Mercosur-Ursprung): mit Quote 7,5 % vs. Drittlandszoll je KN', v['positionen'] == 2 and v['kg'] == 2500 and nahe(v['mitQuote'], 0.640305 * 2500)
      and nahe(v['ohneQuote'], ohne) and nahe(v['ersparnis'], ohne - 0.640305 * 2500), v)
check('Anteilig Hilton: Roastbeef 1.000 kg Hilton von 3.000 kg (Schreibweise egal)', len(e['anteilig']) == 1 and nahe(e['anteilig'][0]['anteilHilton'], 1 / 3)
      and e['anteilig'][0]['regime'] == {'hilton': 1000, 'mercosur': 2000}, e['anteilig'])
check('Hinweise: Imag. EK 20 weicht > 10 % vom Einstand ab (Pos. 2), Imag. EK 11 nicht (Pos. 1)',
      any(h['pos'] == 1 and 'Imag. EK' in h['text'] for h in e['hinweise']) and not any(h['pos'] == 0 and 'Imag. EK' in h['text'] for h in e['hinweise']))
check('Hinweis bei Drittlandszoll für Mercosur-Ursprung: Kontingent möglich', any(h['pos'] == 3 and 'Mercosur-Kontingent möglich' in h['text'] for h in e['hinweise']))
check('Grundfall ohne Fehler und ohne Warnung zu Ländern', not texte(r, 'fehler') and not any('EU' in t or 'gibt es nicht' in t for t in texte(r)))


def fall(**aenderung):
    """Kopie des Grundfalls mit Änderungen: kopf={…}, pos={stelle: {…}}, teile=[…], positionen=[…], ueberschrieben={…}"""
    x = copy.deepcopy(GRUND)
    x['kopf'].update(aenderung.pop('kopf', {}))
    for i, d in aenderung.pop('pos', {}).items():
        x['positionen'][i].update(d)
    x.update(aenderung)
    return rechnen(x)


# ---------- Provision im Zollwert ----------
r2 = fall(kopf={'provisionEinkauf': False})['ergebnis']
check('Provision keine Einkaufsprovision: Zollwert + 0,05, Zoll Drittland + 0,05 × 12,8 %, Hilton weiter 0',
      nahe(r2['positionen'][3]['zollwertKg'], 8.5874) and nahe(r2['positionen'][3]['zollKg'] - p4['zollKg'], 0.0064) and r2['positionen'][0]['zollKg'] == 0
      and nahe(r2['positionen'][3]['einstandKg'] - p4['einstandKg'], 0.0064))

# ---------- Unvollständig ----------
r3 = fall(kopf={'kurs': None})
check('kein Kurs bei USD-Preisen: unvollständig, Fehler „Kurs fehlt“, keine Zahlen', not r3['ergebnis']['vollstaendig'] and 'Kurs USD/€ fehlt.' in texte(r3, 'fehler') and 'positionen' not in r3['ergebnis'])
r3b = fall(kopf={'kurs': None, 'seefrachtWaehrung': 'EUR'}, pos={0: {'waehrung': 'EUR'}, 2: {'waehrung': 'EUR'}})
check('ohne USD braucht es keinen Kurs; Seefracht in € bleibt 2.500', r3b['ergebnis']['vollstaendig'] and nahe(r3b['ergebnis']['gesamt']['seefracht'], 2500), texte(r3b))
r4 = fall(pos={i: {'netto': 0} for i in range(4)})
check('Summe Netto 0: unvollständig mit Fehler, keine Division durch 0', not r4['ergebnis']['vollstaendig'] and any('Summe Netto ist 0' in t for t in texte(r4, 'fehler')))
check('ohne Datum: unvollständig', not fall(kopf={'datum': ''})['ergebnis']['vollstaendig'])
r5 = fall(pos={3: {'kn': ''}})
check('Drittland ohne KN-Code: unvollständig mit Hinweis auf die KN-Codes', not r5['ergebnis']['vollstaendig'] and any('0201 30 00' in t for t in texte(r5, 'fehler')))
check('Drittland mit KN eines anderen Fleischs: unvollständig', not fall(pos={3: {'kn': '0206 29 91'}})['ergebnis']['vollstaendig'])
check('ohne Ursprungsland: unvollständig', not fall(pos={0: {'land': ''}})['ergebnis']['vollstaendig'])

# ---------- Teil und Position ohne Gewicht ----------
r6 = fall(teile=GRUND['teile'] + [{'id': 'c', 'name': 'Teil C', 'versicherung': 1}])
tc = r6['ergebnis']['teile'][2]
r6b = fall(teile=GRUND['teile'] + [{'id': 'c', 'name': 'Teil C', 'versicherung': 1}], pos={2: {'vk': 10}, 3: {'vk': 14}})['ergebnis']
check('ein leerer Teil verhindert den Gesamtertrag nicht', r6b['gesamt']['rohertrag'] is not None and r6b['teile'][2]['rohertrag'] is None)
check('Teil ohne Positionen: 0 kg, Vers./kg 0, Warnung, kein VK – keine Division durch 0',
      r6['ergebnis']['vollstaendig'] and tc['netto'] == 0 and tc['versKg'] == 0 and tc['vkWert'] is None and any('Teil C' in t and 'kein Nettogewicht' in t for t in texte(r6, 'warnung')))
r7 = fall(pos={1: {'netto': 0}})
check('Position ohne Gewicht: Warnung, Wert 0, Anteil 0', r7['ergebnis']['vollstaendig'] and any(h['pos'] == 1 and 'ohne Nettogewicht' in h['text'] for h in r7['ergebnis']['hinweise'])
      and r7['ergebnis']['positionen'][1]['ist'] == 0 and r7['ergebnis']['positionen'][1]['anteilTeil'] == 0)

# ---------- VK vollständig → Gesamtertrag ----------
r8 = fall(pos={2: {'vk': 10}, 3: {'vk': 14}})['ergebnis']
vkB = 20000 + 7000
check('VK überall: Teil B und Gesamt mit Rohertrag; Gesamt-Rohgewinn = Summe Rohertrag − Rückvergütung − WKZ',
      nahe(r8['teile'][1]['vkWert'], vkB) and nahe(r8['gesamt']['vkWert'], 22000 + vkB) and nahe(r8['gesamt']['rohertrag'], 22000 + vkB - r8['gesamt']['ist'])
      and nahe(r8['gesamt']['rohgewinn'], r8['gesamt']['rohertrag'] - 220 - 100) and nahe(r8['gesamt']['rueckverguetung'], 220))

# ---------- Gekühlt / gefroren, EU-Ursprung, falsche Länder, Stichtag ----------
r9 = fall(pos={3: {'kn': '0201 30 00'}})['ergebnis']
check('Drittland gekühlt (0201 30 00): 303,4 €/100 kg statt 304,1', r9['positionen'][3]['satz'] == 'drittland_frisch' and nahe(r9['positionen'][3]['zollKg'], 8.5374 * 0.128 + 3.034))
r10 = fall(pos={3: {'regime': 'eu', 'land': 'PL', 'kn': ''}})
check('EU-Ursprung (PL): kein Zoll, keine Warnung', r10['ergebnis']['positionen'][3]['zollKg'] == 0 and not any(h['pos'] == 3 for h in r10['ergebnis']['hinweise']))
r11 = fall(pos={3: {'land': 'PL'}})
check('Drittlandszoll für EU-Ursprung: Warnung', any(h['pos'] == 3 and 'liegt in der EU' in h['text'] for h in r11['ergebnis']['hinweise']))
r12 = fall(pos={3: {'regime': 'eu', 'land': 'AR'}})
check('EU-Ursprung gewählt, Land AR: Warnung, Zoll 0 wie gewählt', any(h['pos'] == 3 and 'nicht in der EU' in h['text'] for h in r12['ergebnis']['hinweise']) and r12['ergebnis']['positionen'][3]['zollKg'] == 0)
r13 = fall(pos={0: {'land': 'ZA'}})
check('Hilton für Ursprung ZA: Warnung, Satz 20 %', any(h['pos'] == 0 and 'gibt es nicht für Ursprung ZA' in h['text'] for h in r13['ergebnis']['hinweise']) and r13['ergebnis']['positionen'][0]['satz'] == 'hilton')
r14 = fall(pos={0: {'land': 'AU'}})['ergebnis']
check('Hilton für Ursprung AU: 20 %, keine Warnung zum Land', r14['positionen'][0]['satz'] == 'hilton' and nahe(r14['positionen'][0]['zollKg'], (10.5 + vA) * 0.2)
      and not any(h['pos'] == 0 and 'Imag. EK' not in h['text'] for h in r14['hinweise']), r14['hinweise'])
r15 = fall(pos={2: {'land': 'AU'}})
check('Mercosur-Kontingent für Ursprung AU: Warnung', any(h['pos'] == 2 and 'nur für Ursprung AR, BR, PY, UY' in h['text'] for h in r15['ergebnis']['hinweise']))
r16 = fall(kopf={'datum': '2026-04-30'})
check('Hilton UY vor dem 01.05.2026: 20 % mit Hinweis; Mercosur-Kontingent vor dem Start: Warnung',
      r16['ergebnis']['positionen'][0]['satz'] == 'hilton' and any(h['pos'] == 0 and '01.05.2026' in h['text'] for h in r16['ergebnis']['hinweise'])
      and any(h['pos'] == 2 and 'erst ab dem 01.05.2026' in h['text'] for h in r16['ergebnis']['hinweise']))

# ---------- Sätze überschreiben, anderer Satz, Schnappschuss ----------
r17 = fall(ueberschrieben={'mercosur': {'wert': 5, 'spez': 10, 'vermerk': 'Testvermerk'}})
e17 = r17['ergebnis']
check('Satz überschrieben mit Vermerk: gerechnet mit 5 % + 10 €/100 kg, Warnung nennt Vorgabe und Vermerk',
      nahe(e17['positionen'][2]['zollKg'], 8.5374 * 0.05 + 0.1) and any('überschrieben' in t and '7,5 %' in t and 'Testvermerk' in t for t in texte(r17, 'warnung'))
      and e17['saetze']['mercosur']['vorgabe'] == {'wert': 7.5, 'spez': 0.0} and nahe(e17['vergleich']['mitQuote'], (8.5374 * 0.05 + 0.1) * 2500))
check('Satz überschrieben ohne Vermerk: unvollständig', not fall(ueberschrieben={'mercosur': {'wert': 5, 'spez': 0, 'vermerk': ''}})['ergebnis']['vollstaendig'])
check('unbekannter Satz zum Überschreiben: Eingabefehler', 'fehler' in fall(ueberschrieben={'gibtesnicht': {'wert': 1}}))
r18 = fall(pos={3: {'regime': 'anderer', 'wertzoll': 10, 'spezifisch': 100, 'vermerk': 'Testsatz'}})
check('anderer Satz mit Vermerk: 10 % + 100 €/100 kg, Hinweis', nahe(r18['ergebnis']['positionen'][3]['zollKg'], 8.5374 * 0.1 + 1) and any(h['pos'] == 3 and 'Testsatz' in h['text'] for h in r18['ergebnis']['hinweise']))
check('anderer Satz ohne Vermerk: unvollständig', not fall(pos={3: {'regime': 'anderer', 'wertzoll': 10}})['ergebnis']['vollstaendig'])
eigene = copy.deepcopy(e['saetze'])
eigene['mercosur']['wert'] = 0.0
check('Schnappschuss der Sätze wird benutzt (nicht die Tabelle im Code)', rechnen(GRUND, eigene)['ergebnis']['positionen'][2]['zollKg'] == 0)

# ---------- Eingabeprüfung ----------
for name, x in [('negativer Preis', {'pos': {0: {'preis': -1}}}), ('unbekannter Teil', {'pos': {0: {'teil': 'z'}}}), ('unbekanntes Regime', {'pos': {0: {'regime': 'quote'}}}),
                ('Land nicht zweistellig', {'pos': {0: {'land': 'Uruguay'}}}), ('KN mit Buchstaben', {'pos': {0: {'kn': '0201 3O 00'}}}),
                ('Kurs als Text', {'kopf': {'kurs': 'eins'}}), ('Datum falsch', {'kopf': {'datum': '01.10.2026'}}), ('Artikel leer', {'pos': {0: {'artikel': ' '}}}),
                ('Zins über 100 %', {'kopf': {'zins': 101}}), ('doppelte Teil-Kennung', {'teile': [GRUND['teile'][0], GRUND['teile'][0]]})]:
    check(f'Eingabefehler: {name}', 'fehler' in fall(**copy.deepcopy(x)), name)
check('deutsche Schreibweise „1.234,5“ wird gelesen', nahe(fall(pos={0: {'netto': '1.000,0'}})['eingabe']['positionen'][0]['netto'], 1000))

print(f'{PASS}/{PASS + FAIL} passed')
raise SystemExit(0 if FAIL == 0 else 1)
