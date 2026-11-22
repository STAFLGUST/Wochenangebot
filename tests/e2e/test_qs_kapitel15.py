"""QM-System – Kapitel 1.5 „Mitarbeiter“ samt Unterkapiteln 1.5.x (personenbezogene Unterlagen, Entscheidung des Inhabers 16.11.2026):
alles daraus sieht nur, wer „bearbeiten“ darf (qs_sichtbar, qs_dok_sichtbar in module/qs/qs.php). Ausnahme: eine selbst zugewiesene Prüfung
mit ihren Nachweisen und eine selbst zugewiesene Maßnahme – nicht mehr.

Geprüft an jedem Leseweg: qs_start (Dokumente, Handbuch, Prüfplan, Nachweise, Maßnahmen, Zahlen je Ordner, Zahl der Nachweise), CSV aller
drei Listen, Audit-Bericht (Ansicht und Excel), qs_datei, qs_archiv, qs_archiv_zip, qs_ablage_export (auch je Kapitel), Organigramm-Vorschau,
Verfahrensdoku (qs_verfahren, Antwort nach dem Speichern, PDF des Arbeitsstands und freigegebener Fassungen samt Änderungszeilen, ZIP für Prüfungen), Protokoll ohne Namen; Grenze „1.50“
bleibt sichtbar; Ordner „1.5 …“ außerhalb von Kapitel 1.5 ebenso – als Ordner-Dokument (Titel) und als Unterordner (pfad der Datei), aus dem
Import einer zweiten Firma (Bereich 90, auch „HACCP/1.5 Mitarbeiter/…“) und von Hand in Kapitel 1.4 abgelegt, Name einer im Entwurf gelöschten
Datei im Verlauf, auch „alt_1.5 …“ und „Kopie von 1.5.1 …“; Oberfläche für „ansehen“ und „Nachweise“ (1280/390 px, keine JavaScript-Fehler). Nur erfundene Testdaten.
"""
import datetime
import io
import json
import os
import re
import zipfile
import zlib

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client
from umgebung import SH
from umgebung import storage_write
from qs_hilfe import PW, check, ende, pdf, hochladen, roh, nutzer, anmelden, text, ohne_scrollen, speicher, neu_zaehlen

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
# Audit run-3: auch eine freigegebene Fassung (Schnappschuss mit allen Dokumenten) und ihre gespeicherten Änderungszeilen – gefiltert beim Lesen
morgen = (datetime.date.fromisoformat(heute) + datetime.timedelta(days=1)).isoformat()
check('Fassung 2 freigegeben (neuer Abschnitt, 1.5-A01 jetzt Version 2)', V.call('qs_verfahren_freigeben', {'doku': VD, 'rev': r['doku']['rev'], 'grund': 'Zweitfassung',
                                                                                                         'gueltigAb': morgen})[0] == 200)
f2 = {n: next(d for d in c.call('qs_verfahren')[1]['dokus'] if d['id'] == VD)['fassungen'][1]['aenderungen'] for n, c in (('vf', VF), ('admin', V))}
check('qs_verfahren, Änderungen der Fassung 2: ohne Zeile zum 1.5-Dokument für „verfahren_sehen“, mit für „bearbeiten“',
      not any('Personalakte' in z or '1.5-A01' in z for z in f2['vf']) and any('Personalakte Beispiel' in z for z in f2['admin']) and any('Reisekosten' in z for z in f2['vf']), f2)
for q_ in ('&fassung=2', '&fassung=1', f'&von={heute[:8]}01&bis={morgen}'):
    pdf_ = {n: b''.join(zlib.decompress(x) for x in re.findall(rb'stream\n(.*?)\nendstream', roh(c, f'qs_verfahren_export&doku={VD}{q_}')[1], re.S))
            for n, c in (('vf', VF), ('admin', V))}
    check(f'PDF ({q_[1:]}): ohne Titel und Version des 1.5-Dokuments für „verfahren_sehen“, mit für „bearbeiten“', b'Personalakte Beispiel' not in pdf_['vf']
          and b'Version 2 vom' not in pdf_['vf'] and b'Personalakte Beispiel' in pdf_['admin'] and (b'Reisekosten' in pdf_['vf']) == (q_ != '&fassung=1'))

# ── Bereich einer zweiten Firma (Kapitel 90): Kapitelordner „1.5 Mitarbeiter“ wird Ordner-Dokument dieses Titels, tiefer liegt er im pfad ──
MF = [('Matthies Fleischwaren/1.5 Mitarbeiter', 'Matthies-Akte.pdf'), ('Matthies Fleischwaren/1.50 Sonstiges', 'Matthies-150.pdf'),
      ('Matthies Fleischwaren/HACCP-Matthies/1.5 Mitarbeiter/Gesundheitszeugnisse', 'Matthies-Zeugnis.pdf'),
      ('Matthies Fleischwaren/HACCP-Matthies/1.50 Sonstiges', 'Matthies-HACCP-150.pdf'), ('Matthies Fleischwaren/HACCP-Matthies', 'Matthies-HACCP.pdf')]
MW = {'wurzel': {'name': 'Matthies Fleischwaren', 'art': 'neu', 'kapitel': '90', 'titel': 'Matthies Fleischwaren'}}
st, r = V.call('qs_sammel_plan', {'ordner': [[o, [[n, len(pdf(n))]]] for o, n in MF], **MW, 'anlegen': True})
ups = [hochladen(V, '', '', n, pdf(n), {'sammeln': True, 'herkunft': o})[1]['upload'] for o, n in MF]
st2, r2 = V.call('qs_import_eintragen', {**MW, 'uploads': [{'upload': u, 'status': 'ablage', 'ver': '', 'ohne': False} for u in ups]})
md = {d['titel']: d['id'] for d in Be.call('qs_start')[1]['dokumente'] if d['kapitel'] == '90'}
M15, M150, MH = md.get('1.5 Mitarbeiter'), md.get('1.50 Sonstiges'), md.get('HACCP-Matthies')
fm = {f['name']: f['id'] for d in (M15, M150, MH) if d for f in Be.call(f'qs_archiv&dok={d}')[1]['dateien']}
check('Import Bereich 90: Ordner „1.5 Mitarbeiter“, „1.50 Sonstiges“ und „HACCP-Matthies“ (Zeugnis im pfad „1.5 Mitarbeiter/…“)', st == 200 and st2 == 200
      and M15 and M150 and MH and set(fm) == {n for _, n in MF}, (r, r2, md, fm))
st, r, raw = L.call('qs_start', raw=True)
check('qs_start „ansehen“: Bereichs-Ordner „1.5 Mitarbeiter“ fehlt (auch in den Zahlen), „1.50 Sonstiges“ bleibt',
      M15 not in [d['id'] for d in r['dokumente']] and M15 not in r['ablageZahlen'] and M150 in [d['id'] for d in r['dokumente']])
for was, abruf in (('Ordnerbaum', f'qs_archiv&dok={M15}'), ('ZIP', f'qs_archiv_zip&dok={M15}'), ('Datei', 'qs_datei&id=' + fm.get('Matthies-Akte.pdf', '')),
                   ('Datei im Unterordner HACCP-Matthies/1.5 Mitarbeiter', 'qs_datei&id=' + fm.get('Matthies-Zeugnis.pdf', ''))):
    check(f'Bereich 90, 1.5 Mitarbeiter – {was}: „ansehen“ und „Nachweise“ 403, „bearbeiten“ 200', roh(L, abruf)[0] == 403 and roh(N, abruf)[0] == 403 and roh(Be, abruf)[0] == 200)
baum = lambda cli, d: sorted(f['name'] + '@' + f['pfad'] for f in cli.call(f'qs_archiv&dok={d}')[1]['dateien'])
zipn = lambda cli, q: ' '.join(zipfile.ZipFile(io.BytesIO(roh(cli, q)[1])).namelist())
check('Ordnerbaum HACCP-Matthies: „ansehen“ ohne den Unterordner „1.5 Mitarbeiter“, „1.50 Sonstiges“ bleibt; „bearbeiten“ alles',
      baum(L, MH) == ['Matthies-HACCP-150.pdf@1.50 Sonstiges', 'Matthies-HACCP.pdf@'] and len(baum(Be, MH)) == 3, (baum(L, MH), baum(Be, MH)))
check('Ordner-ZIP HACCP-Matthies: „ansehen“ ohne Zeugnis, „bearbeiten“ mit; Unterordner „1.5 Mitarbeiter“ einzeln für „ansehen“ 404',
      'Matthies-Zeugnis' not in zipn(L, f'qs_archiv_zip&dok={MH}') and 'Matthies-HACCP-150' in zipn(L, f'qs_archiv_zip&dok={MH}')
      and 'Matthies-Zeugnis' in zipn(Be, f'qs_archiv_zip&dok={MH}') and roh(L, f'qs_archiv_zip&dok={MH}&pfad=1.5%20Mitarbeiter')[0] == 404)
check('Gegenprobe Bereich 90, 1.50: Datei und Ordnerbaum für „ansehen“ 200', roh(L, 'qs_datei&id=' + fm.get('Matthies-150.pdf', ''))[0] == 200
      and roh(L, f'qs_archiv&dok={M150}')[0] == 200)
for abfrage in ('qs_ablage_export&alle=1', 'qs_ablage_export&kapitel=90&alle=1'):
    namen = {n: ' '.join(zipfile.ZipFile(io.BytesIO(roh(c, abfrage)[1])).namelist()) for n, c in (('lisa', L), ('bernd', Be))}
    check(f'ZIP-Export ({abfrage.split("&", 1)[1]}): Ordner 1.5 im Bereich (auch als Unterordner) nur für „bearbeiten“, 1.50 für beide',
          'Matthies-Akte' not in namen['lisa'] and 'Matthies-Zeugnis' not in namen['lisa'] and 'Matthies-150' in namen['lisa'] and 'Matthies-HACCP-150' in namen['lisa']
          and 'Matthies-Akte' in namen['bernd'] and 'Matthies-Zeugnis' in namen['bernd'], namen)

# ── Von Hand in Kapitel 1.4: Ordner-Dokument „1.5.1 Zeugnisse“ und Unterordner „Akten/1.5 Mitarbeiter“ eines anderen Ordners ──
H151, h151 = ordner('1.4', '1.5.1 Zeugnisse', 'Hand-Zeugnis.pdf')
H14, h14 = ordner('1.4', 'Ablage Personal', 'Hand-Liste.pdf')
hp = {n: hochladen(Be, H14, '', n, pdf(n), {'pfad': p})[1]['datei'] for n, p in (('Hand-Akte.pdf', 'Akten/1.5 Mitarbeiter'), ('Hand-150.pdf', 'Akten/1.50 Sonstiges'),
                                                                                 ('Hand-Alt.pdf', 'Akten/alt_1.5 Mitarbeiter'), ('Hand-Kopie.pdf', 'Kopie von 1.5.1 Zeugnisse'))}
st, r = L.call('qs_start')
check('Kapitel 1.4: Ordner „1.5.1 Zeugnisse“ fehlt für „ansehen“, „Ablage Personal“ bleibt', H151 not in [d['id'] for d in r['dokumente']]
      and H14 in [d['id'] for d in r['dokumente']])
check('… Ordnerbaum „Ablage Personal“: „ansehen“ ohne „Akten/1.5 Mitarbeiter“, mit „Akten/1.50 Sonstiges“',
      baum(L, H14) == ['Hand-150.pdf@Akten/1.50 Sonstiges', 'Hand-Liste.pdf@'] and len(baum(Be, H14)) == 5, (baum(L, H14), baum(Be, H14)))
for was, abruf in (('Datei im Ordner 1.5.1', 'qs_datei&id=' + h151), ('Datei im Unterordner 1.5', 'qs_datei&id=' + hp['Hand-Akte.pdf']),
                   ('Datei im Unterordner „alt_1.5 …“', 'qs_datei&id=' + hp['Hand-Alt.pdf']), ('Datei im Unterordner „Kopie von 1.5.1 …“', 'qs_datei&id=' + hp['Hand-Kopie.pdf'])):
    check(f'Kapitel 1.4, {was}: „ansehen“ 403, „bearbeiten“ 200', roh(L, abruf)[0] == 403 and roh(Be, abruf)[0] == 200)
namen = zipn(L, 'qs_ablage_export&kapitel=1.4&alle=1') + zipn(L, f'qs_archiv_zip&dok={H14}')
check('… Ablage-Export und Ordner-ZIP für „ansehen“ ohne beide, mit „Hand-150“', 'Hand-Zeugnis' not in namen and 'Hand-Akte' not in namen and 'Hand-150' in namen, namen)

# ── Ältere Dateien am Dokument (qs-dokumente, „dateien“, GR-006) im Unterordner „1.5 Mitarbeiter“: auch in qs_start nur für Bearbeiter ──
alt = {n: hochladen(Be, 'eingang', '', n + '.pdf', pdf(n), {'pfad': p})[1]['datei'] for n, p in (('Alt-Akte', 'Akten/1.5 Mitarbeiter'), ('Plan', 'Akten/1.5 Mitarbeiter'),
                                                                                             ('Alt-Liste', 'Akten/1.50 Sonstiges'))}
ab = speicher('qs-ablage'); alte = [f for f in ab['liste'] if f['id'] in alt.values()]
ab['liste'] = [f for f in ab['liste'] if f['id'] not in alt.values()]; storage_write('qs-ablage', ab)
d_ = speicher('qs-dokumente'); x_ = next(x for x in d_['liste'] if x['id'] == H14)
x_['dateien'] = [{**{k: v for k, v in f.items() if k != 'ziel'}, 'name': 'Plan' if f['name'] == 'Plan.pdf' else f['name']} for f in alte]
x_['verlauf'] = x_.get('verlauf', []) + [{'t': '2026-11-02T08:00:00+00:00', 'von': 'Bernd Bearbeiter', 'was': f'Planung angepasst; Datei entfernt: {n}'} for n in ('Alt-Akte.pdf', 'Plan', 'Alt-Liste.pdf')]
storage_write('qs-dokumente', d_)
neu_zaehlen(Be)
sl, sb = json.dumps(L.call('qs_start')[1], ensure_ascii=False), json.dumps(Be.call('qs_start')[1], ensure_ascii=False)
check('ältere Dateien am Dokument „Ablage Personal“: qs_start „ansehen“ ohne Name und pfad aus „1.5 Mitarbeiter“ (auch im Verlauf), „Alt-Liste“ bleibt',
      'Alt-Akte' not in sl and 'Akten/1.5 Mitarbeiter' not in sl and 'Datei entfernt: Plan' not in sl and 'Alt-Liste.pdf' in sl, re.findall(r'.{60}(?:Alt-Akte|Akten/1\.5 |entfernt: Plan).{20}', sl))
check('… Verlaufstext nur ganze Namen ersetzt („Planung“ bleibt), „bearbeiten“ sieht alles',
      'Planung angepasst; Datei entfernt: personenbezogene Datei' in sl and 'Alt-Akte.pdf' in sb and 'Akten/1.5 Mitarbeiter' in sb and 'Datei entfernt: Plan"' in sb)

# ── Aus dem Eingang einem Entwurf in 1.4 zugeordnet: die Datei behält ihren pfad „QM/1.5 Mitarbeiter/…“ und bleibt geschützt ──
r = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'A', 'nr': '', 'titel': 'Kontrollanweisung Eingang'})[1]['dokument']
E14 = r['id']
fe = hochladen(Be, 'eingang', '', 'Eingang-Akte.pdf', pdf('Eingang-Akte'), {'pfad': 'QM/1.5 Mitarbeiter/Akten'})[1]['datei']
check('Eingangsdatei mit pfad „…/1.5 Mitarbeiter/…“ dem Entwurf zugeordnet und freigegeben', Be.call('qs_datei_zuordnen', {'dateien': [fe], 'dokument': E14, 'version': r['versionen'][0]['id']})[0] == 200
      and schritt(E14, 'einreichen', Be) == 200 and schritt(E14, 'pruefen_freigeben', Q) == 200)
check('… Einzeldownload: „ansehen“ 403, „bearbeiten“ 200', roh(L, 'qs_datei&id=' + fe)[0] == 403 and roh(Be, 'qs_datei&id=' + fe)[0] == 200)
dl, db = dok(E14, L), dok(E14, Be)
check('… Dokumentliste (qs_start, auch Grundlage der Einzelansicht): Name der Datei fehlt für „ansehen“, für „bearbeiten“ dabei',
      'Eingang-Akte' not in json.dumps(L.call('qs_start')[1], ensure_ascii=False) and [f['name'] for f in dl['versionen'][0]['dateien']] == []
      and [f['name'] for f in db['versionen'][0]['dateien']] == ['Eingang-Akte.pdf'], (dl['versionen'][0]['dateien'], db['versionen'][0]['dateien']))
namen = {n: zipn(c, 'qs_ablage_export&kapitel=1.4&alle=1') + zipn(c, 'qs_ablage_export') for n, c in (('lisa', L), ('bernd', Be))}
check('… Ablage-Export: Datei der Version fehlt für „ansehen“, für „bearbeiten“ dabei', 'Eingang-Akte' not in namen['lisa'] and 'Hand-150' in namen['lisa']
      and 'Eingang-Akte' in namen['bernd'], namen)
# Audit run-3: im Entwurf endgültig gelöscht – der Name steht danach in keiner Liste mehr, nur im Verlauf (Eintrag merkt sich pfad)
r = Be.call('qs_dokument_save', {'kapitel': '1.4', 'art': 'A', 'nr': '', 'titel': 'Kontrollanweisung Entwurf'})[1]['dokument']
fg = hochladen(Be, 'eingang', '', 'Eingang-Geloescht.pdf', pdf('Eingang-Geloescht'), {'pfad': 'QM/1.5 Mitarbeiter/Akten'})[1]['datei']
check('Eingangsdatei mit pfad „…/1.5 Mitarbeiter/…“ dem Entwurf zugeordnet und dort gelöscht',
      Be.call('qs_datei_zuordnen', {'dateien': [fg], 'dokument': r['id'], 'version': r['versionen'][0]['id']})[0] == 200
      and Be.call('qs_datei_entfernen', {'datei': fg, 'rev': dok(r['id'])['rev'], 'grund': ''})[0] == 200)
vl, vb = (json.dumps(dok(r['id'], c)['versionen'][0]['verlauf'], ensure_ascii=False) for c in (L, Be))
check('… Verlauf: „ansehen“ ohne Namen und pfad („Datei entfernt: personenbezogene Datei“), „bearbeiten“ mit',
      'Eingang-Geloescht' not in vl and '1.5 Mitarbeiter' not in vl and 'Datei entfernt: personenbezogene Datei' in vl and 'Datei entfernt: Eingang-Geloescht.pdf' in vb, (vl, vb))
st, r = V.call('qs_verfahren_save', {'titel': 'VD Kontrolle', 'gesellschaft': 'Muster GmbH', 'verantwortlich': ''})
VD2 = r['doku']['id']
st, r = V.call('qs_verfahren_abschnitt_save', {'doku': VD2, 'teil': 'anwender', 'titel': 'Kontrolle', 'text': 'siehe QM', 'verweise': [dok(E14)['nr']], 'fertig': True})
check('… Verfahrensdoku mit Verweis darauf freigegeben', st == 200 and V.call('qs_verfahren_freigeben', {'doku': VD2, 'rev': r['doku']['rev'], 'grund': 'Erstfassung', 'gueltigAb': heute[:8] + '01'})[0] == 200)
zip_ = {n: ' '.join(zipfile.ZipFile(io.BytesIO(roh(c, f'qs_verfahren_export&doku={VD2}{von_bis}')[1])).namelist()) for n, c in (('vf', VF), ('admin', V))}
check('… ZIP der Verfahrensdoku: Datei fehlt für „verfahren_sehen“, für „bearbeiten“ dabei', 'Eingang-Akte' not in zip_['vf'] and 'Eingang-Akte' in zip_['admin'], zip_)

# ── Protokoll: Vorgänge aus 1.5 ohne Namen ──
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll ohne Namen aus 1.5 (sieht, wer „protokoll.sehen“ hat), mit Kapitelnummer', not drin(log, GEHEIM) and '(Kapitel 1.5.1, personenbezogen)' in log
      and '(Kapitel 1.5, personenbezogen)' in log and 'Kontrollprüfung' in log, drin(log, GEHEIM))
check('… auch der Bereichs-Ordner „1.5 Mitarbeiter“ (ZIP-Download) nur mit Kapitelnummer', '(Kapitel 90, personenbezogen)' in log and 'Matthies-Akte' not in log)

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
