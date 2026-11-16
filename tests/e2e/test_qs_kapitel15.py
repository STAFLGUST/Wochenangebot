"""QM-System – Kapitel 1.5 „Mitarbeiter“ samt Unterkapiteln 1.5.x (personenbezogene Unterlagen, Entscheidung des Inhabers 16.11.2026):
alles daraus sieht nur, wer „bearbeiten“ darf (qs_sichtbar, qs_dok_sichtbar in module/qs/qs.php). Ausnahme: eine selbst zugewiesene Prüfung
mit ihren Nachweisen und eine selbst zugewiesene Maßnahme – nicht mehr.

Geprüft an jedem Leseweg: qs_start (Dokumente, Handbuch, Prüfplan, Nachweise, Maßnahmen, Zahlen je Ordner, Zahl der Nachweise), CSV aller
drei Listen, Audit-Bericht (Ansicht und Excel), qs_datei, qs_archiv, qs_archiv_zip, qs_ablage_export (auch je Kapitel), Organigramm-Vorschau,
Verfahrensdoku (qs_verfahren, Antwort nach dem Speichern, PDF des Arbeitsstands, ZIP für Prüfungen), Protokoll ohne Namen; Grenze „1.50“
bleibt sichtbar; Oberfläche für „ansehen“ und „Nachweise“ (1280/390 px, keine JavaScript-Fehler). Nur erfundene Testdaten.
"""
import io
import json
import os
import re
import zipfile
import zlib

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import SH
from qs_hilfe import PW, check, ende, pdf, hochladen, roh, nutzer, anmelden, text, ohne_scrollen

NUTZER = (('lisa', 'Lisa Lesen', 'viewer', 'Leserin-Konto-12', {'grant': ['qs.sehen']}),
          ('nina', 'Nina Nachweis', 'viewer', 'Nachweis-Konto-23', {'grant': ['qs.nachweis']}),
          ('vf', 'Vera Verfahren', 'viewer', 'Verfahr-Konto-77', {'grant': ['qs.verfahren_bearbeiten']}),
          ('bernd', 'Bernd Bearbeiter', 'editor', 'Bearbeit-Konto-34', {'grant': ['qs.bearbeiten']}),
          ('quinn', 'Quinn QMB', 'editor', 'Freigabe-Konto-56', {'grant': ['qs.freigeben']}))
A, K, ids = nutzer(NUTZER)
L, N, VF, Be, Q = K['lisa'], K['nina'], K['vf'], K['bernd'], K['quinn']
V = Client('198.51.100.20'); V.call('login', {'username': 'admin', 'password': PW})
KAP = [{'id': '1.4', 'titel': 'Qualitätssicherung'}, {'id': '1.5', 'titel': 'Mitarbeiter'}, {'id': '1.5.1', 'titel': 'Gesundheitszeugnisse'},
       {'id': '1.50', 'titel': 'Sonstiges'}]
PERSONEN = [{'id': 'NN', 'name': 'Nina Nachweis', 'funktion': 'Lager', 'mitarbeiter': ids['nina']}, {'id': 'QB', 'name': 'Quinn QMB', 'funktion': 'QMB', 'mitarbeiter': ids['quinn']}]
st, r = V.call('qs_stamm_save', {'kapitel': KAP, 'personen': PERSONEN})
check('Kapitel 1.4, 1.5, Unterkapitel 1.5.1 und 1.50; Personen mit Kürzel', st == 200, r)
heute = Be.call('qs_start')[1]['heute']


def dok(did, cli=None):
    return {x['id']: x for x in (cli or Be).call('qs_start')[1]['dokumente']}[did]


def schritt(did, s, cli):
    return cli.call('qs_version_schritt', {'dokument': did, 'rev': dok(did)['rev'], 'schritt': s})[0]


def ordner(kap, titel, datei):
    did = Be.call('qs_dokument_save', {'kapitel': kap, 'art': 'O', 'nr': '', 'titel': titel})[1]['dokument']['id']
    return did, hochladen(Be, did, '', datei, pdf(titel))[1]['datei']


# ── Bestand: geschützte Einträge tragen eindeutige Merkmale (GEHEIM), die Gegenproben in 1.4 und 1.50 „Kontroll…“ ──
O151, f151 = ordner('1.5.1', 'Zeugnisordner Muster', 'Zeugnis-Muster.pdf')
O150, f150 = ordner('1.50', 'Kontrollordner 150', 'Kontrolle-150.pdf')
r = Be.call('qs_dokument_save', {'kapitel': '1.5', 'art': 'A', 'nr': '', 'titel': 'Personalakte Beispiel'})[1]['dokument']
A15 = r['id']
f15 = hochladen(Be, A15, r['versionen'][0]['id'], 'Akte-Beispiel.pdf', pdf('Akte'))[1]['datei']
check('1.5-A01 freigegeben', schritt(A15, 'einreichen', Be) == 200 and schritt(A15, 'pruefen_freigeben', Q) == 200 and dok(A15)['nr'] == '1.5-A01')
r = Be.call('qs_dokument_save', {'kapitel': '1.5.1', 'art': 'L', 'nr': '', 'titel': 'Organigramm Personal'})[1]['dokument']
L151 = r['id']
og = [{'id': 'k1', 'titel': 'Leitung', 'ueber': '', 'art': 'linie', 'personen': [], 'vertretung': '', 'hinweis': ''}]
check('Organigramm im Entwurf (1.5.1) gespeichert', Be.call('qs_organigramm_save', {'dokument': L151, 'rev': dok(L151)['rev'], 'organigramm': {'knoten': og}})[0] == 200)
check('Handbuch-Abschnitte 1.5.1 und 1.4', Q.call('qs_abschnitt_save', {'kapitel': '1.5.1', 'nr': '1', 'titel': 'Handbuch Zeugnisse', 'text': 'Zeugnisse prüfen'})[0] == 200
      and Q.call('qs_abschnitt_save', {'kapitel': '1.4', 'nr': '1', 'titel': 'Kontrollhandbuch', 'text': 'x'})[0] == 200)
P151 = Q.call('qs_pruefung_save', {'kapitel': '1.5.1', 'titel': 'Zeugnisprüfung Nina', 'intervall': 'jaehrlich', 'ausfuehrende': [ids['nina']]})[1]['pruefung']['id']
P15 = Q.call('qs_pruefung_save', {'kapitel': '1.5', 'titel': 'Unterweisung Personal', 'intervall': 'jaehrlich'})[1]['pruefung']['id']
P14 = Q.call('qs_pruefung_save', {'kapitel': '1.4', 'titel': 'Kontrollprüfung', 'intervall': 'jaehrlich'})[1]['pruefung']['id']
nw = lambda cli, p, t: cli.call('qs_nachweis_save', {'pruefung': p, 'datum': heute, 'ergebnis': 'io', 'bemerkung': t})[0]
check('Nachweise: Nina für ihre Prüfung (1.5.1), nicht für eine fremde aus 1.5', nw(N, P151, 'Nachweis Zeugnis ok') == 200 and nw(N, P15, 'x') == 403
      and nw(Be, P15, 'Nachweis Unterweisung ok') == 200 and nw(Be, P14, 'Kontrollnachweis') == 200)
mn = lambda kap, zust, t: Be.call('qs_massnahme_save', {'kapitel': kap, 'quelle': 'intern', 'feststellung': t, 'zustaendig': zust, 'status': 'offen'})[0]
check('Maßnahmen: 1.5 für Nina (NN), 1.5.1 für QB, 1.4', mn('1.5', 'QB / NN', 'Maßnahme Zeugnis nachholen') == 200 and mn('1.5.1', 'QB', 'Maßnahme Unterweisung nachholen') == 200
      and mn('1.4', 'QB', 'Kontrollmaßnahme') == 200)
NINA = ['Zeugnisprüfung Nina', 'Nachweis Zeugnis ok', 'Maßnahme Zeugnis nachholen']
GEHEIM = NINA + ['Zeugnisordner Muster', 'Zeugnis-Muster.pdf', 'Personalakte Beispiel', 'Akte-Beispiel.pdf', 'Organigramm Personal', 'Handbuch Zeugnisse',
                 'Unterweisung Personal', 'Nachweis Unterweisung ok', 'Maßnahme Unterweisung nachholen']
KONTROLLE = ['Kontrollordner 150', 'Kontrollhandbuch', 'Kontrollprüfung', 'Kontrollnachweis', 'Kontrollmaßnahme']


def drin(raw, liste):
    return [x for x in liste if x in raw]


# ── qs_start: Liste und Suche (im Browser über dieselbe Liste), Zahlen ──
st, r, raw = L.call('qs_start', raw=True)
check('qs_start „ansehen“: nichts aus 1.5 und 1.5.x – Dokumente, Handbuch, Prüfplan, Nachweise, Maßnahmen', st == 200 and not drin(raw, GEHEIM), drin(raw, GEHEIM))
check('… die Gegenproben aus 1.4 und 1.50 bleiben sichtbar („1.50“ ist kein Unterkapitel von 1.5)', drin(raw, KONTROLLE) == KONTROLLE, drin(raw, KONTROLLE))
check('… Zahlen: je Ordner nur sichtbare, Nachweise insgesamt nur sichtbare', O151 not in r['ablageZahlen'] and O150 in r['ablageZahlen'] and r['nachweiseGesamt'] == 1,
      (r['ablageZahlen'], r['nachweiseGesamt']))
st, r, raw = N.call('qs_start', raw=True)
check('qs_start „Nachweise“: genau die eigene Prüfung mit ihrem Nachweis und die eigene Maßnahme aus 1.5.x', drin(raw, GEHEIM) == NINA
      and [p['id'] for p in r['pruefungen'] if p['kapitel'].startswith('1.5')] == [P151] and r['nachweiseGesamt'] == 2, drin(raw, GEHEIM))
st, r, raw = Be.call('qs_start', raw=True)
check('qs_start „bearbeiten“: alles (Dateien im Ordner erst im Ordnerbaum)', drin(raw, GEHEIM) == [x for x in GEHEIM if x != 'Zeugnis-Muster.pdf'] and r['nachweiseGesamt'] == 3 and O151 in r['ablageZahlen'], drin(raw, GEHEIM))

# ── CSV ──
for liste in ('dokumente', 'pruefplan', 'massnahmen'):
    roh_ = {n: c.call('qs_export', {'liste': liste}, raw=True)[2] for n, c in (('lisa', L), ('nina', N), ('bernd', Be))}
    check(f'CSV {liste}: „ansehen“ ohne 1.5, „Nachweise“ nur Eigenes, „bearbeiten“ alles', not drin(roh_['lisa'], GEHEIM) and set(drin(roh_['nina'], GEHEIM)) <= set(NINA)
          and drin(roh_['bernd'], GEHEIM) and (liste == 'dokumente' or drin(roh_['nina'], NINA)), {n: drin(x, GEHEIM) for n, x in roh_.items()})

# ── Audit-Bericht (Ansicht und Excel) ──
q = f'qs_bericht&von={heute[:8]}01&bis={heute}'


def excel(cli):
    st_, z = roh(cli, q.replace('qs_bericht', 'qs_bericht_excel'))
    zf = zipfile.ZipFile(io.BytesIO(z))
    return ''.join(zf.read(n).decode('utf-8', 'replace') for n in zf.namelist() if n.endswith('.xml'))


for n, cli in (('lisa', L), ('nina', N)):
    b = cli.call(q, raw=True)[2] + excel(cli)
    check(f'Audit-Bericht und Excel „{n}“: nichts aus 1.5 außer Eigenem', set(drin(b, GEHEIM)) <= (set(NINA) if n == 'nina' else set()), drin(b, GEHEIM))
b = Be.call(q, raw=True)[2] + excel(Be)
check('Audit-Bericht „bearbeiten“: mit 1.5 (Gegenprobe)', {'Personalakte Beispiel', 'Unterweisung Personal', 'Handbuch Zeugnisse', 'Maßnahme Unterweisung nachholen'} <= set(drin(b, GEHEIM)), drin(b, GEHEIM))

# ── Direkte Abrufe: 403 ohne „bearbeiten“ (auch mit zugewiesener Prüfung), 200 mit ──
for was, abruf in (('Datei im Ordner 1.5.1', 'qs_datei&id=' + f151), ('Datei der gültigen Version 1.5', 'qs_datei&id=' + f15), ('Ordnerbaum 1.5.1', f'qs_archiv&dok={O151}'),
                   ('Ordner 1.5.1 als ZIP', f'qs_archiv_zip&dok={O151}'), ('Organigramm-Vorschau 1.5.1', f'qs_organigramm_vorschau&dokument={L151}')):
    check(f'{was}: „ansehen“ und „Nachweise“ 403, „bearbeiten“ 200', roh(L, abruf)[0] == 403 and roh(N, abruf)[0] == 403 and roh(Be, abruf)[0] == 200)
check('Gegenprobe 1.50: Datei und Ordnerbaum für „ansehen“ 200', roh(L, 'qs_datei&id=' + f150)[0] == 200 and roh(L, f'qs_archiv&dok={O150}')[0] == 200)
for abfrage in ('qs_ablage_export&alle=1', 'qs_ablage_export&kapitel=1.5.1&alle=1', 'qs_ablage_export&kapitel=1.5&alle=1'):
    namen = {n: ' '.join(zipfile.ZipFile(io.BytesIO(roh(c, abfrage)[1])).namelist()) for n, c in (('lisa', L), ('bernd', Be))}
    check(f'ZIP-Export ({abfrage.split("&", 1)[1]}): ohne 1.5 für „ansehen“, mit für „bearbeiten“', not drin(namen['lisa'], GEHEIM)
          and ('Zeugnis-Muster.pdf' in namen['bernd'] or 'kapitel=1.5&' in abfrage) and ('Akte-Beispiel.pdf' in namen['bernd'] or '1.5.1' in abfrage), namen)

# ── Verfahrensdoku: verknüpftes 1.5-Dokument, danach eine neue Version davon ──
st, r = V.call('qs_verfahren_save', {'titel': 'VD Lohn', 'gesellschaft': 'Muster GmbH', 'verantwortlich': ''})
VD = r['doku']['id']
st, r = V.call('qs_verfahren_abschnitt_save', {'doku': VD, 'teil': 'anwender', 'titel': 'Lohn', 'text': 'siehe QM', 'verweise': ['1.5-A01'], 'fertig': True})
check('Verfahrensdoku mit Verweis auf 1.5-A01, Fassung 1 freigegeben', st == 200 and V.call('qs_verfahren_freigeben', {'doku': VD, 'rev': r['doku']['rev'], 'grund': 'Erstfassung',
                                                                                                                      'gueltigAb': heute[:8] + '01'})[0] == 200)
Be.call('qs_version_save', {'dokument': A15, 'aenderungen': 'neu', 'grund': 'Test', 'dateien': True})
check('1.5-A01 Version 2 freigegeben (seit der Fassung geändert)', schritt(A15, 'einreichen', Be) == 200 and schritt(A15, 'pruefen_freigeben', Q) == 200)
st, r, raw = VF.call('qs_verfahren', raw=True)
check('qs_verfahren ohne „bearbeiten“: Abweichung ohne Kennung und Titel des 1.5-Dokuments', st == 200 and 'Personalakte Beispiel' not in raw and A15 not in raw, raw[:300])
check('… mit „bearbeiten“ (Gegenprobe) genannt', 'Personalakte Beispiel' in V.call('qs_verfahren', raw=True)[2])
st, r, raw = VF.call('qs_verfahren_abschnitt_save', {'doku': VD, 'teil': 'anwender', 'titel': 'Reisekosten', 'text': 'x', 'fertig': True}, raw=True)
check('Antwort nach dem Speichern (verfahren_bearbeiten ohne „bearbeiten“): ebenso ohne', st == 200 and 'Personalakte Beispiel' not in raw and A15 not in raw)
von_bis = f'&von={heute[:8]}01&bis={heute}&dokumente=1'
zip_ = {n: zipfile.ZipFile(io.BytesIO(roh(c, f'qs_verfahren_export&doku={VD}{von_bis}')[1])).namelist() for n, c in (('vf', VF), ('admin', V))}
check('ZIP für Prüfungen: ohne Dateien aus 1.5 für „verfahren_sehen“, mit für „bearbeiten“', not any('Akte-Beispiel' in x for x in zip_['vf'])
      and any('Akte-Beispiel' in x for x in zip_['admin']), zip_)
pdf_ = {n: b''.join(zlib.decompress(x) for x in re.findall(rb'stream\n(.*?)\nendstream', roh(c, f'qs_verfahren_export&doku={VD}&fassung=0')[1], re.S))
        for n, c in (('vf', VF), ('admin', V))}
check('PDF des Arbeitsstands: ohne Titel des 1.5-Dokuments, mit für „bearbeiten“', b'Personalakte Beispiel' not in pdf_['vf'] and b'Personalakte Beispiel' in pdf_['admin'])

# ── Protokoll: Vorgänge aus 1.5 ohne Namen ──
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll ohne Namen aus 1.5 (sieht, wer „protokoll.sehen“ hat), mit Kapitelnummer', not drin(log, GEHEIM) and '(Kapitel 1.5.1, personenbezogen)' in log
      and '(Kapitel 1.5, personenbezogen)' in log and 'Kontrollprüfung' in log, drin(log, GEHEIM))

# ── Oberfläche: „ansehen“ und „Nachweise“ (Nachweise der eigenen Prüfung erfassen bleibt möglich) ──
with sync_playwright() as p:
    br = p.chromium.launch()
    for user, pw, ip, breite in (('lisa', 'Leserin-Konto-12', '198.51.100.10', 1280), ('nina', 'Nachweis-Konto-23', '198.51.100.11', 1280),
                                 ('nina', 'Nachweis-Konto-23', '198.51.100.11', 390)):
        ctx, pg = anmelden(br, user, pw, ip, breite, 'light', 844 if breite < 500 else 900)
        sichtbar = ''
        for tab in ('dokumente', 'handbuch', 'pruefplan', 'massnahmen', 'uebersicht'):
            pg.click(f'#qm-tabs [data-tab="{tab}"]'); pg.wait_for_selector(f'#qm-t-{tab}:not([hidden])')
            sichtbar += text(pg, f'#qm-t-{tab}')
        erwartet = ['Zeugnisprüfung Nina', 'Maßnahme Zeugnis nachholen'] if user == 'nina' else []
        check(f'{user} {breite}px: Oberfläche zeigt aus 1.5 nur Eigenes, Gegenprobe sichtbar', [x for x in drin(sichtbar, GEHEIM) if x != 'Nachweis Zeugnis ok'] == erwartet
              and 'Kontrollprüfung' in sichtbar, drin(sichtbar, GEHEIM))
        pg.click('#qm-tabs [data-tab="pruefplan"]'); pg.wait_for_selector('#qm-t-pruefplan:not([hidden])')
        check(f'{user} {breite}px: ohne waagerechtes Scrollen', ohne_scrollen(pg, '#qm-t-pruefplan'))
        pg.screenshot(path=os.path.join(SH, f'qs_kapitel15_{user}_{breite}.png'), full_page=True)
        ctx.close()
    br.close()
ende()
