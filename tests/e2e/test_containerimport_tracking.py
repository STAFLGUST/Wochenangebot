"""Container-Import: Reiter „Tracking“ (Aktion containerimport_tracking_save, app/api/module/containerimport/tracking.php,
Oberfläche app/module/containerimport/tracking.js) – erste Stufe ohne fremde Dienste.
Geprüft: Rechte (speichern nur mit „EUDR bearbeiten“, CSRF, kein GET); Schiff, Reederei, Konnossement, Häfen, Abfahrt und
Ankunft am Container; ungültige Angaben (Reederei außerhalb der Liste, Datum, Ankunft vor Abfahrt); Revision (409);
fehlende Angaben behalten ihren Wert; ältere Container ohne die Felder bleiben lesbar (GR-006); das Speichern des
Containers im Reiter EUDR lässt die Angaben stehen; nach dem Abschluss der Bewertung weiter pflegbar, die Bewertung bleibt;
Protokoll. Oberfläche: Reiter wechseln, Liste nach Ankunft mit „in … Tagen“ und „überfällig“, Suche, Angekommene
ein- und ausblenden, Fenster mit Vorschlag der Reederei nach dem Kürzel, Verweis zur Sendungsverfolgung (wird nie
abgerufen), Leser ohne Speichern, Handy 390 px. Alle Namen und Nummern sind erfunden (GR-007)."""
import datetime
import os
from playwright.sync_api import sync_playwright
from containerimport_hilfe import check, ende, nutzer_anlegen, container, container_anlegen, kalender, seite as seite_oeffnen
from umgebung import SH, shot, storage_raw, storage_write, _json

A, I, L = nutzer_anlegen()
tag = kalender(I)


def anlegen(partie, **mehr):
    return container_anlegen(I, partie, **mehr)


def tracking(c, **angaben):
    """Tracking speichern → (Status, Antwort, der Container danach)."""
    st, r = I.call('containerimport_tracking_save', {'id': c['id'], 'rev': c['rev'], **angaben})
    return st, r, container(r, c['partie'])


def vorbereiten(c, **angaben):
    """Tracking für die Oberfläche unten setzen – muss gelingen."""
    st, r, c = tracking(c, **angaben)
    assert st == 200, (st, r)
    return c


# ---------- Stand und Rechte ----------
c1 = anlegen('P-280001', container='MSKU 907032 3')
check('ein neuer Container hat leere Angaben zum Tracking', [c1.get(k) for k in ('schiff', 'reederei', 'bl', 'abgangshafen', 'zielhafen', 'etd', 'eta')] == [''] * 7, c1)
check('nur ansehen: Speichern 403', L.call('containerimport_tracking_save', {'id': c1['id'], 'rev': c1['rev'], 'schiff': 'X'})[0] == 403)
csrf = I.csrf; I.csrf = ''
check('ohne CSRF: 403', I.call('containerimport_tracking_save', {'id': c1['id'], 'rev': c1['rev'], 'schiff': 'X'})[0] == 403)
I.csrf = csrf
check('per GET: 405', I.call('containerimport_tracking_save')[0] == 405)
check('unbekannter Container: 404', I.call('containerimport_tracking_save', {'id': 'sgibtesnicht', 'rev': 1})[0] == 404)

# ---------- Speichern ----------
ANGABEN = {'schiff': 'Beispiel Express', 'reederei': 'maersk', 'bl': 'BL-TEST-0001', 'abgangshafen': 'Santos', 'zielhafen': 'Hamburg', 'etd': tag(-10), 'eta': tag(12), 'stand': 'unterwegs'}
st, r, c1 = tracking(c1, **ANGABEN)
check('Tracking gespeichert: Schiff, Reederei, Konnossement, Häfen, Abfahrt, Ankunft und Stand stehen am Container',
      st == 200 and {k: c1.get(k) for k in ANGABEN} == ANGABEN and c1.get('container') == 'MSKU 907032 3' and c1.get('rev') == 2, (st, r.get('error'), c1))
check('ungültig: Reederei außerhalb der Liste, kein Datum, Datum als Zahl oder Liste, Ankunft vor Abfahrt, Stand außerhalb der Liste – je 422, nichts gespeichert',
      [tracking(c1, **x)[0] for x in ({'reederei': 'gibtesnicht'}, {'eta': '12.12.2026'}, {'eta': 20261212}, {'etd': [tag(1)]}, {'etd': tag(5), 'eta': tag(4)}, {'stand': 'verschollen'})] == [422] * 6
      and container(I.call('containerimport_start')[1], 'P-280001') == c1)
check('veralteter Stand: 409', I.call('containerimport_tracking_save', {'id': c1['id'], 'rev': 1, 'schiff': 'X'})[0] == 409)
st, r, c1 = tracking(c1, eta=tag(14))
check('nur eine Angabe geschickt: die übrigen behalten ihren Wert', st == 200 and c1.get('eta') == tag(14) and c1.get('schiff') == 'Beispiel Express' and c1.get('zielhafen') == 'Hamburg' and c1.get('stand') == 'unterwegs', (st, r.get('error')))
st, r, c1 = tracking(c1, schiff='', eta=tag(12))
check('eine Angabe lässt sich leeren', st == 200 and c1.get('schiff') == '' and c1.get('eta') == tag(12), (st, r.get('error')))
st, r, c1 = tracking(c1, schiff='Beispiel Express', container='msku 907032-4')
check('Containernummer im Tracking geändert: gespeichert, falsche Prüfziffer nur als Hinweis', st == 200 and c1.get('container') == 'msku 907032-4' and c1.get('containerPruefung') == 'pruefziffer', (st, r.get('error')))
st, r, c1 = tracking(c1, container='MSKU 907032 3')

# ---------- Zusammenspiel mit dem Reiter EUDR ----------
st, r = I.call('containerimport_eudr_sendung_save', {**{k: v for k, v in c1.items() if k not in ANGABEN or k == 'stand'}, 'ware': 'Rindfleisch, gekühlt, ohne Knochen'})
c1 = container(r, 'P-280001')
check('Container im Reiter EUDR gespeichert (älterer Stand der Seite ohne die Felder): die Angaben zum Tracking bleiben',
      st == 200 and c1.get('ware') == 'Rindfleisch, gekühlt, ohne Knochen' and c1.get('schiff') == 'Beispiel Express' and c1.get('eta') == tag(12), (st, r.get('error'), c1))
st, r = I.call('containerimport_eudr_sendung_abschluss', {'id': c1['id'], 'rev': c1['rev'], 'ergebnis': 'nicht_vernachlaessigbar', 'begruendung': 'Unterlagen fehlen noch – Test des Trackings.'})
c1 = container(r, 'P-280001')
bewertung = (c1.get('abschluss'), c1.get('profil'))
st, r, c1 = tracking(c1, eta=tag(13), schiff='Beispiel Express II', stand='dokumente')
check('nach dem Abschluss der Bewertung: Tracking weiter pflegbar, Abschluss und Risikoprofil bleiben unverändert (GR-106)',
      st == 200 and c1.get('eta') == tag(13) and c1.get('schiff') == 'Beispiel Express II' and bewertung[0] and (c1.get('abschluss'), c1.get('profil')) == bewertung, (st, r.get('error')))
c2 = anlegen('P-280002')
doc = _json(storage_raw('containerimport-eudr-sendungen'))
for k in ('schiff', 'reederei', 'bl', 'abgangshafen', 'zielhafen', 'etd', 'eta'):
    next(s for s in doc['liste'] if s['partie'] == 'P-280002').pop(k, None)
storage_write('containerimport-eudr-sendungen', doc)
c2 = container(I.call('containerimport_start')[1], 'P-280002')
st, r, c2 = tracking(c2, schiff='Altbestand')
check('Container aus der Zeit vor dem Tracking: lesbar mit leeren Angaben, Speichern ergänzt sie', st == 200 and c2.get('schiff') == 'Altbestand' and c2.get('eta') == '' and c2.get('reederei') == '', (st, r.get('error')))
verlauf = str(A.call('log')[1])
check('Protokoll nennt das Speichern des Trackings', 'Tracking des Containers „P-280001“ gespeichert' in verlauf, verlauf[:300])

# Für die Liste: überfällig, bald, angekommen, ohne Ankunft
c2 = vorbereiten(c2, schiff='Altbestand', eta='', stand='gekauft')
c3 = vorbereiten(anlegen('P-280003', container='HLXU 123456 7'), schiff='Fracht <b>Stern</b>', reederei='hapag', abgangshafen='Montevideo', zielhafen='Rotterdam', etd=tag(-30), eta=tag(-2), stand='unterwegs')
vorbereiten(anlegen('P-280004'), schiff='Morgenfähre', reederei='sonst', zielhafen='Hamburg', eta=tag(1), stand='unterwegs')
vorbereiten(anlegen('P-280005'), schiff='Schon Da', zielhafen='Hamburg', eta=tag(-20), stand='angekommen')

# ---------- Oberfläche ----------
with sync_playwright() as pw:
    br = pw.chromium.launch()
    errs, fremd = [], []

    def seite(user, vp=None, schema='light'):
        return seite_oeffnen(br, user, errs, fremd, vp, schema)

    zeilen = "[...document.querySelectorAll('#ci-tracking tbody tr')].map(r => r.cells[0].querySelector('.ci-name').textContent + '|' + r.cells[4].querySelector('.ci-marke').textContent)"
    p = seite('ina')
    check('Start: Reiter EUDR gewählt, Tracking verborgen', p.get_attribute('#ci-reiter-eudr', 'aria-selected') == 'true' and p.is_hidden('#ci-bereich-tracking') and p.is_visible('#ci-sichten'))
    p.click('#ci-reiter-tracking'); p.wait_for_selector('#ci-tracking')
    check('Reiter „Tracking“ gewählt: die Ansichten des Reiters EUDR sind verborgen', p.get_attribute('#ci-reiter-tracking', 'aria-selected') == 'true' and p.get_attribute('#ci-reiter-eudr', 'aria-selected') == 'false'
          and p.is_hidden('#ci-sichten') and p.is_hidden('#ci-inhalt'))
    check('Liste: nicht Angekommene nach Ankunft – überfällig zuerst, dann morgen, in 13 Tagen, zuletzt ohne Ankunft',
          p.evaluate(zeilen) == ['P-280003|seit 2 Tagen überfällig', 'P-280004|morgen', 'P-280001|in 13 Tagen', 'P-280002|Ankunft offen'], p.evaluate(zeilen))
    check('Kopfzeile nennt Zahl, Überfällige und die nächste Ankunft (morgen, nicht die überfällige); fremder Text im Schiffsnamen erscheint als Text',
          '4 Container sind noch nicht angekommen · 1 überfällig · nächste Ankunft ' + datetime.date.fromisoformat(tag(1)).strftime('%d.%m.%Y') in p.inner_text('.ci-t-lage')
          and 'Fracht <b>Stern</b>' in p.inner_text('#ci-tracking') and p.locator('#ci-tracking b').count() == 0 and 'Montevideo → Rotterdam' in p.inner_text('#ci-tracking'), p.inner_text('.ci-t-lage'))
    shot(p, os.path.join(SH, 'containerimport-tracking-1280.png'))
    p.check('#ci-t-angekommene'); p.wait_for_function("document.querySelectorAll('#ci-tracking tbody tr').length === 5")
    check('„Angekommene anzeigen“: der angekommene Container steht am Ende', p.evaluate(zeilen)[-1] == 'P-280005|angekommen', p.evaluate(zeilen))
    p.uncheck('#ci-t-angekommene'); p.wait_for_function("document.querySelectorAll('#ci-tracking tbody tr').length === 4")
    p.fill('#ci-t-suche', 'rotterdam'); p.wait_for_function("document.querySelectorAll('#ci-tracking tbody tr').length === 1")
    check('Suche findet über den Hafen und behält den Fokus', p.evaluate(zeilen) == ['P-280003|seit 2 Tagen überfällig'] and p.evaluate('document.activeElement.id') == 'ci-t-suche')
    p.fill('#ci-t-suche', 'gibt es nicht'); p.wait_for_selector('#ci-bereich-tracking .ci-leer')
    check('Suche ohne Treffer sagt das', p.inner_text('#ci-bereich-tracking .ci-leer') == 'Kein Container passt zur Suche.')
    p.fill('#ci-t-suche', ''); p.wait_for_selector('#ci-tracking')

    # Fenster: Vorschlag der Reederei, Speichern, Verweis
    p.focus(f'[data-tracking="{c2["id"]}"]'); p.keyboard.press('Enter'); p.wait_for_selector('#dlg-tracking[open]')
    check('Fenster „Tracking“ mit der Eingabetaste geöffnet; ohne Containernummer kein Verweis und kein Vorschlag', p.inner_text('#tracking-titel') == 'Tracking P-280002'
          and p.locator('#tracking-verweis').count() == 0 and p.input_value('#dlg-tracking [name=reederei]') == '')
    p.fill('#dlg-tracking [name=container]', 'MSKU 907032 3'); p.fill('#dlg-tracking [name=zielhafen]', 'Hamburg'); p.fill('#dlg-tracking [name=eta]', tag(30))
    p.select_option('#dlg-tracking [name=stand]', 'unterwegs'); p.click('#dlg-tracking button[type=submit]')
    p.wait_for_function("document.querySelector('#dlg-tracking').innerText.includes('vermutlich Maersk')")
    p.fill('#dlg-tracking [name=eta]', tag(30)); p.click('#dlg-tracking button[type=submit]'); p.wait_for_selector('#ci-toast.zeigen:not(.fehler)')
    c2 = container(I.call('containerimport_start')[1], 'P-280002')
    check('gespeichert: Angaben am Container; die Reederei wird nach dem Kürzel der Containernummer nur als Hinweis vorgeschlagen und auch beim erneuten Speichern nicht von selbst gespeichert',
          [c2[k] for k in ('container', 'zielhafen', 'eta', 'stand', 'reederei')] == ['MSKU 907032 3', 'Hamburg', tag(30), 'unterwegs', '']
          and p.input_value('#dlg-tracking [name=reederei]') == '' and p.evaluate("document.querySelector('#dlg-tracking').open"), c2)
    p.select_option('#dlg-tracking [name=reederei]', 'maersk'); p.click('#dlg-tracking button[type=submit]'); p.wait_for_selector('#tracking-verweis')
    check('Reederei gespeichert: Verweis zur Sendungsverfolgung mit der Containernummer, öffnet ein neues Fenster ohne Rückbezug',
          p.get_attribute('#tracking-verweis', 'href') == 'https://www.maersk.com/tracking/MSKU9070323' and p.get_attribute('#tracking-verweis', 'target') == '_blank'
          and p.get_attribute('#tracking-verweis', 'rel') == 'noopener noreferrer' and container(I.call('containerimport_start')[1], 'P-280002')['reederei'] == 'maersk', p.get_attribute('#tracking-verweis', 'href'))
    shot(p, os.path.join(SH, 'containerimport-tracking-fenster-1280.png'))
    p.fill('#dlg-tracking [name=etd]', tag(40)); p.click('#dlg-tracking button[type=submit]'); p.wait_for_selector('#ci-toast.zeigen.fehler')
    check('Fehler des Servers erscheint als Meldung, das Fenster bleibt offen', 'Ankunft liegt vor der Abfahrt' in p.inner_text('#ci-toast') and p.evaluate("document.querySelector('#dlg-tracking').open"))
    p.click('#dlg-tracking [data-zu]')
    check('Liste nach dem Speichern: neue Ankunft eingeordnet', p.evaluate(zeilen) == ['P-280003|seit 2 Tagen überfällig', 'P-280004|morgen', 'P-280001|in 13 Tagen', 'P-280002|in 30 Tagen'], p.evaluate(zeilen))
    p.click('#ci-reiter-eudr'); p.wait_for_selector('#ci-sendungen')
    check('zurück zum Reiter EUDR: Liste der Container wieder da, Tracking verborgen', p.is_visible('#ci-sendungen') and p.is_hidden('#ci-bereich-tracking'))
    p.context.close()

    le = seite('lea')
    le.click('#ci-reiter-tracking'); le.wait_for_selector('#ci-tracking')
    le.click(f'[data-tracking="{c3["id"]}"]'); le.wait_for_selector('#dlg-tracking[open]')
    check('nur ansehen: Fenster ohne Speichern, Felder gesperrt, Verweis vorhanden',
          le.locator('#dlg-tracking button[type=submit]').count() == 0 and le.is_disabled('#dlg-tracking [name=schiff]') and le.input_value('#dlg-tracking [name=schiff]') == 'Fracht <b>Stern</b>'
          and le.get_attribute('#tracking-verweis', 'href').endswith('?container=HLXU1234567'))
    le.context.close()

    m = seite('ina', {'width': 390, 'height': 844}, 'dark')
    m.click('#ci-reiter-tracking'); m.wait_for_selector('#ci-tracking')
    check('Handy 390 px: Liste ohne waagerechtes Scrollen', m.evaluate('document.documentElement.scrollWidth <= window.innerWidth'))
    shot(m, os.path.join(SH, 'containerimport-tracking-390-dunkel.png'))
    m.click(f'[data-tracking="{c1["id"]}"]'); m.wait_for_selector('#dlg-tracking[open]')
    check('Handy 390 px: Fenster einspaltig', m.evaluate("(() => { const b = document.querySelector('#dlg-tracking .ci-raster'), w = b.clientWidth; return [...b.querySelectorAll(':scope > .ci-feld')].every((f) => Math.abs(f.offsetWidth - w) <= 1); })()"))
    shot(m, os.path.join(SH, 'containerimport-tracking-fenster-390-dunkel.png'))
    m.context.close()
    br.close()
    check('die Seite hat keine fremden Server abgerufen (auch nicht die Reedereien)', fremd == [], fremd)

check('keine JavaScript-Fehler', not errs, errs)
ende()
