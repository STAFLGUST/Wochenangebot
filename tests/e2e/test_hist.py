"""Testgruppe hist: Preisverlauf – Import alter Angebotslisten, Zeiträume, Datendialog; Frühere Wochen ansehen (KW wechseln,
Angebot wählen, Quelle Wochenablage/Veröffentlichung/Version/Preisverlauf, Rechte); Wochenablage je KW (ablegen, ersetzen,
damalige Angebotsdefinitionen, alte Versionen retten, nie auf der Kundenseite)."""
import sys
from umgebung import BASE  # Testserver je Gruppe (parallel)
import datetime, glob, json, os, re
from kunden_hilfe import Client
from playwright.sync_api import sync_playwright
from versand_hilfe import veroeffentlichen
B = BASE
from umgebung import SH, FIX, REPO, WORK, XL44, storage_raw, storage_write, trennstufe, datenordner, _storage_raw
res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))

RUHE = "document.getAnimations().every((x) => x.playState !== 'running')"   # Fenster fertig eingeblendet (Bildschirmfoto)


def api_get(pg, q):
    return pg.evaluate("""async (q) => { const r = await fetch('/api/?action=' + q); let j = null; try { j = await r.json(); } catch (e) {} return [r.status, j]; }""", q)


def api_post(pg, action, body):
    return pg.evaluate("""async ([a, b]) => { const s = await (await fetch('/api/?action=status')).json();
      const r = await fetch('/api/?action=' + a, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-CSRF-Token': s.csrf || ''}, body: JSON.stringify(b)});
      let j = null; try { j = await r.json(); } catch (e) {} return [r.status, j]; }""", [action, body])


def api_post_bestaetigt(pg, action, body):
    r = api_post(pg, action, body)
    if r[0] == 403 and (r[1] or {}).get('code') == 'confirmation_required':
        api_post(pg, 'reauth', {'password': 'Sicheres-Passwort-1'}); r = api_post(pg, action, body)
    return r


def woche(pg, kw, oid='std'):
    r = api_get(pg, f'angebot_woche&woche={kw}&angebot={oid}')
    return r[0], r[1] or {}


def dok(name):
    """Gespeichertes Dokument (ohne PHP-Schutzzeile) oder None – so, wie der Testserver es liest"""
    raw = storage_raw(name)
    return json.loads(raw.split('?>\n', 1)[-1]) if raw else None


def ablage_namen():
    """Wochen in der Wochenablage angebot-woche/* (Dateien oder Datenbank)"""
    ordner = datenordner('angebot-woche/2026-01')
    if os.path.isfile(ordner + '/.sqlite-active'):
        import sqlite3
        with sqlite3.connect(ordner + '/.sqlite/store.sqlite') as db:
            return sorted(r[0].split('/', 1)[1] for r in db.execute("SELECT name FROM documents WHERE name LIKE 'angebot-woche/%'"))
    d = ordner + '/angebot-woche'
    return sorted(f[:-4] for f in os.listdir(d) if f.endswith('.php')) if os.path.isdir(d) else []


def rahmen_hat(pg, text):
    """warten, bis die Angebotsseite im Fenster den Text zeigt (während des Ladens gibt es kurz kein body)"""
    pg.wait_for_function("""(t) => { const d = document.querySelector('#fw-frame').contentDocument; return !!(d && d.body && d.body.innerText.includes(t)); }""", arg=text)


def preis_von(antwort, code):
    it = next((i for i in ((antwort.get('offer') or {}).get('items') or []) if i.get('code') == code), None)
    return it and (it['price'].get('value') if it['price'].get('status') == 'value' else it['price'].get('status')), it


def fruehere_wochen_pruefen(a, br, errs):
    """Frühere Wochen ansehen (nur Mitarbeiter mit Modulzugang Angebot, nur lesend): Quelle je KW, Auflösung auf dem Server,
    Rechte, Grenzfälle, Fenster mit KW-Wechsel (Desktop, 390 px)."""
    a.set_viewport_size({'width': 1440, 'height': 950})
    a.click('#vt-edit'); a.wait_for_selector('#view-edit:not([hidden]) tr[data-id]')
    # Vorbereitung: KW 43 mit Edeka-Preis, eigener Bezeichnung und Werbung veröffentlichen, danach KW 44 mit anderen Preisen
    d = api_get(a, 'draft')[1]
    m = d['draft'] or d['published']
    it = {i['code']: i for i in m['items']}
    it['10601'].setdefault('variants', {})['edeka'] = {'status': 'value', 'value': 22}
    it['10601'].setdefault('namen', {})['edeka'] = 'Roastbeef Edeka'
    m['meta'].setdefault('werbung', {})['edeka'] = {'titel': 'Edeka-Woche', 'artikel': [{'id': it['10601']['id']}]}
    r = api_post(a, 'save_draft', {'revision': d['revision'], 'model': m})
    check('Frühere Wochen · Vorbereitung: KW 43 mit Edeka-Preis, Bezeichnung und Werbung', r[0] == 200, r)
    ab0 = dok('angebot-woche/2026-43')
    pub0 = d['published']['publishedAt']
    v0 = next((i for i in (ab0 or {}).get('modell', {}).get('items', []) if i.get('code') == '10601'), {})
    check('Wochenablage: Veröffentlichung legt KW 43 ab (Stand, Modell, Angebotsdefinitionen)', ab0 and ab0.get('stand') == pub0 and ab0.get('quelle') == 'veroeffentlichung'
          and v0.get('price', {}).get('value') == 25.5 and {'id': 'edeka', 'name': 'Wochenangebot Edeka', 'fallback': 'standard'} in ab0.get('angebote', [])
          and ablage_namen() == ['2026-43'], (ab0 or {}).get('stand'))
    veroeffentlichen(a)
    pub43 = api_get(a, 'draft')[1]['published']['publishedAt']
    ab1 = dok('angebot-woche/2026-43')
    v1 = next((i for i in (ab1 or {}).get('modell', {}).get('items', []) if i.get('code') == '10601'), {})
    groesse = len(storage_raw('angebot-woche/2026-43') or '')
    print(f'INFO Wochenablage KW 43: {groesse / 1024:.0f} KB (Modell {len(json.dumps(ab1["modell"])) / 1024:.0f} KB, Definitionen {len(json.dumps(ab1["angebote"]))} Byte)')
    check('… zweite Veröffentlichung derselben KW ersetzt die Ablage (ein Dokument je KW)', ab1.get('stand') == pub43 != pub0 and v1.get('variants', {}).get('edeka') == {'status': 'value', 'value': 22}
          and ablage_namen() == ['2026-43'] and 0 < groesse < 400 * 1024, (ab1.get('stand'), pub43, ablage_namen(), groesse))
    d = api_get(a, 'draft')[1]
    m = d['draft'] or d['published']
    it = {i['code']: i for i in m['items']}
    m['meta']['week'] = 44
    it['10601']['price'] = {'status': 'value', 'value': 26}
    it['10601']['variants']['edeka'] = {'status': 'value', 'value': 23}
    it['10601'].pop('namen', None)
    m['meta']['werbung']['edeka'] = {'titel': 'Edeka KW 44', 'artikel': [{'id': it['10601']['id']}]}
    r = api_post(a, 'save_draft', {'revision': d['revision'], 'model': m})
    check('Frühere Wochen · Vorbereitung: KW 44 mit anderen Preisen', r[0] == 200, r)
    veroeffentlichen(a)

    # Quelle je KW und Auflösung auf dem Server
    c, w = woche(a, '2026-44')
    check('KW 44 (aktuell veröffentlicht, aus der Wochenablage): Wochenangebot mit neuem Preis', c == 200 and w.get('quelle') == 'ablage' and preis_von(w, '10601')[0] == 26
          and w.get('kw') == 44 and w.get('jahr') == 2026 and w.get('vorige') == '2026-43', (c, w.get('quelle'), preis_von(w, '10601')[0], w.get('vorige')))
    c, w = woche(a, '2026-43', 'edeka')
    p, i = preis_von(w, '10601')
    check('KW 43 (Wochenablage): letzter Stand der Woche mit Edeka-Preis, Bezeichnung und Werbung, damalige Einstellung', c == 200 and w.get('quelle') == 'ablage' and p == 22
          and w.get('einstellung') == 'damals' and ablage_namen() == ['2026-43', '2026-44']
          and i.get('name') == 'Roastbeef Edeka' and (w['offer']['meta'].get('werbung') or {}).get('titel') == 'Edeka-Woche' and w.get('stand') == pub43
          and w['angebot'] == {'id': 'edeka', 'name': 'Wochenangebot Edeka'}, (c, w.get('quelle'), p, i, w.get('stand'), pub43))
    roh = json.dumps(w, ensure_ascii=False)
    check('… nur Edeka aufgelöst: keine variants/sale-Struktur, keine anderen Angebote', '"variants"' not in roh and '"offers"' not in roh and 'Edeka KW 44' not in roh)
    c, w = woche(a, '2026-43')
    roh = json.dumps(w, ensure_ascii=False)
    check('KW 43 Wochenangebot: Wochenpreis, ohne Kundenpreise und Werbung der Kundenangebote', c == 200 and preis_von(w, '10601')[0] == 25.5 and '"variants"' not in roh
          and 'Edeka-Woche' not in roh and 'Roastbeef Edeka' not in roh, preis_von(w, '10601')[0])
    c, w = woche(a, '2026-42')
    c2, w2 = woche(a, '2026-42', 'edeka')
    check('KW 42 (nur Preisverlauf): einfache Liste nach Gruppen, ohne Werbung und Bereiche', c == 200 and w.get('quelle') == 'historie' and w.get('artikel', 0) > 200
          and not w['offer']['meta'].get('werbung') and w['offer']['sections'] == [] and len(w['offer']['groups']) > 1 and preis_von(w, '10601')[0] not in (None, 22, 23), (c, w.get('quelle'), w.get('artikel')))
    check('… Kundenangebot „folgt dem Wochenangebot“ mit den Wochenpreisen', c2 == 200 and w2.get('quelle') == 'historie' and preis_von(w2, '10601')[0] == preis_von(w, '10601')[0])
    c, w = woche(a, '2026-30')
    check('Woche ohne Daten: kein Angebot, nächste gespeicherte Woche genannt', c == 200 and w.get('quelle') is None and w.get('offer') is None and w.get('vorige') is None
          and w.get('naechste') == '2026-36' and w.get('erste') == '2026-36', (w.get('quelle'), w.get('vorige'), w.get('naechste')))
    c, w = woche(a, '2026-50')
    check('… nach der letzten Woche: vorige gespeicherte Woche genannt', c == 200 and w.get('offer') is None and w.get('vorige') == '2026-44' and w.get('naechste') is None)
    check('Ungültige KW 422, unbekanntes Angebot 404', woche(a, '2026-60')[0] == 422 and woche(a, '2026-ab')[0] == 422 and woche(a, '2025-53')[0] == 422
          and woche(a, '2026-43', 'gibt-es-nicht')[0] == 404 and woche(a, '2026-43', 'e-123')[0] == 404)
    # Rechte: ohne Anmeldung, Kunde, ohne Modulzugang Angebot; Leser darf ansehen (nur lesend)
    check('Rechte: ohne Anmeldung 401', Client('198.51.100.71').call('angebot_woche&woche=2026-43&angebot=edeka')[0] == 401)
    kd = api_get(a, 'kunden')[1]
    r = api_post_bestaetigt(a, 'kunde_save', {'id': '', 'rev': kd['rev'], 'firma': 'Kantine Woche', 'nr': 'K-72', 'email': 'woche@example.org', 'active': True, 'angebote': ['edeka'],
                                              'login': {'username': 'kantine.woche', 'password': 'Kantine-Kennwort-5', 'mustChange': False, 'active': True}})
    K = Client('198.51.100.72')
    angemeldet = r[0] == 200 and K.call('kunde_login', {'username': 'kantine.woche', 'password': 'Kantine-Kennwort-5'})[0] == 200
    check('Rechte: Kunde (Edeka freigeschaltet) bekommt keine frühere Woche (401)', angemeldet and K.call('angebot_woche&woche=2026-43&angebot=edeka')[0] == 401
          and K.call('offer&angebot=edeka')[0] == 200, r[0])
    for nm, rolle, deny in (('Vera', 'viewer', []), ('Ohne', 'editor', ['angebot.zugang'])):
        api_post_bestaetigt(a, 'user_save', {'name': nm, 'username': nm.lower() + '.woche', 'role': rolle, 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False, 'grant': [], 'deny': deny})
    L, O = Client('198.51.100.73'), Client('198.51.100.74')
    L.call('login', {'username': 'vera.woche', 'password': 'Bearbeiter-Zugang-1'}); O.call('login', {'username': 'ohne.woche', 'password': 'Bearbeiter-Zugang-1'})
    c, w = L.call('angebot_woche&woche=2026-43&angebot=edeka')
    check('Rechte: Leser mit Modulzugang sieht die Woche mit Kundenpreisen', c == 200 and preis_von(w, '10601')[0] == 22, c)
    check('Rechte: ohne Modulzugang Angebot 403', O.call('angebot_woche&woche=2026-43')[0] == 403)

    # Fenster: Menü ⋯ → „Frühere Wochen“, öffnet „Diese Woche“
    jetzt = datetime.date.today().isocalendar()
    diese = f'{jetzt[0]}-{jetzt[1]:02d}'
    a.click('#btn-more'); a.wait_for_selector('#menu-more [data-act="wochen"]:not([hidden])')
    a.click('#menu-more [data-act="wochen"]'); a.wait_for_selector('#dlg-wochen[open]')
    a.wait_for_function("(kw) => location.hash === '#woche/' + kw", arg=diese)
    titel = lambda: a.inner_text('#fw-titel').replace('\xa0', ' ')
    if diese > '2026-44':
        a.wait_for_selector('#fw-leer:not([hidden]) [data-fw="gehe"]')
        check('Fenster: diese Woche ohne gespeichertes Angebot – Hinweis und Sprung zur letzten Woche', 'kein Angebot gespeichert' in a.inner_text('#fw-leer')
              and f'KW {jetzt[1]}/{jetzt[0]}' in titel() and a.is_hidden('[data-fw="heute"]') and a.is_disabled('[data-fw="vor"]'), titel())
        a.wait_for_function(RUHE); a.screenshot(path=SH + '/fruehere-wochen-leer.png')
        a.click('#fw-leer [data-fw="gehe"]')
    else:
        a.click('[data-fw="zurueck"]')
    a.wait_for_function("location.hash === '#woche/2026-44'")
    rahmen = a.frame_locator('#fw-frame')
    rahmen.locator('tr.row').first.wait_for()
    check('KW 44 in der Angebotsseite: Titel, „Diese Woche“, Wochenpreis', 'Wochenangebot · KW 44/2026' in titel() and a.is_visible('[data-fw="heute"]')
          and '26,00' in rahmen.locator('body').inner_text(), titel())
    a.select_option('#fw-angebot', 'edeka')
    a.wait_for_function("document.querySelector('#fw-titel').textContent.includes('Edeka')")
    rahmen.locator('tr.row').first.wait_for()
    rahmen_hat(a, '23,00')
    check('Angebot wählen: Edeka mit eigenem Preis', '23,00' in rahmen.locator('body').inner_text())
    a.click('[data-fw="zurueck"]'); a.wait_for_function("location.hash === '#woche/2026-43' && document.querySelector('#fw-titel').textContent.includes('43')")
    rahmen_hat(a, 'Roastbeef Edeka')
    t = rahmen.locator('body').inner_text()
    check('‹ KW 43: Edeka-Preis, eigene Bezeichnung und Werbung der damaligen Woche, Einstellung gespeichert (kein Hinweis)', '22,00' in t and 'Roastbeef Edeka' in t and 'Edeka-Woche' in t
          and a.is_hidden('#fw-hinweis') and 'zuletzt veröffentlicht' in a.inner_text('#fw-sub'), a.inner_text('#fw-sub'))
    a.wait_for_function(RUHE); a.screenshot(path=SH + '/fruehere-wochen.png')
    a.click('[data-fw="zurueck"]'); a.wait_for_function("location.hash === '#woche/2026-42'")
    a.wait_for_selector('#fw-hinweis:not([hidden])')
    check('‹ KW 42: nur Preisstand mit Hinweis', 'nur noch der Preisstand' in a.inner_text('#fw-hinweis') and 'nur Preisstand' in a.inner_text('#fw-sub'))
    a.click('[data-fw="vor"]'); a.wait_for_function("location.hash === '#woche/2026-43'")
    a.click('[data-fw="heute"]'); a.wait_for_function("(kw) => location.hash === '#woche/' + kw", arg=diese)
    check('„Diese Woche“ springt zur aktuellen KW', a.is_hidden('[data-fw="heute"]'))
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-wochen', state='hidden')
    a.wait_for_function("location.hash === ''")
    check('Schließen entfernt #woche aus der Adresse', a.evaluate('location.hash') == '')
    # Aufruf über die Adresse #woche/JJJJ-WW (gewähltes Angebot bleibt gemerkt)
    a.goto(B + '/admin/#woche/2026-43'); a.wait_for_selector('#dlg-wochen[open]')
    a.wait_for_function("document.querySelector('#fw-titel').textContent.includes('Edeka') && document.querySelector('#fw-titel').textContent.includes('43/2026')")
    check('Adresse #woche/2026-43 öffnet das Fenster in KW 43 (Angebot gemerkt)', a.input_value('#fw-angebot') == 'edeka')
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-wochen', state='hidden')
    # 390 px
    mp = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True); merr = []
    mp.on('pageerror', lambda x: merr.append(str(x)))
    mp.goto(B + '/admin/#woche/2026-43'); mp.wait_for_selector('#screen-auth:not([hidden])')
    mp.fill('#au-user', 'admin'); mp.fill('#pw1', 'Sicheres-Passwort-1'); mp.click('#auth-submit')
    mp.wait_for_selector('#dlg-wochen[open]')
    rahmen_hat(mp, '25,50')
    breite = mp.evaluate("[document.documentElement.scrollWidth, Math.round(document.querySelector('#dlg-wochen').getBoundingClientRect().width)]")
    check('390 px: Fenster füllt den Bildschirm, kein seitliches Scrollen, keine JS-Fehler', breite[0] <= 390 and breite[1] <= 390 and not merr, (breite, merr))
    mp.wait_for_function(RUHE); mp.screenshot(path=SH + '/fruehere-wochen-mobil.png'); mp.close()



def wochenablage_pruefen(a):
    """Wochenablage angebot-woche/<JJJJ-WW>: damalige Angebotsdefinitionen, Angebot, das es damals nicht gab, alte Versionen
    werden vor dem Löschen gerettet, nie auf der Kundenseite."""
    a.set_viewport_size({'width': 1440, 'height': 950})
    # Damalige Einstellung: Edeka heute umbenannt und mit eigener Artikelliste, dazu ein neues Angebot
    cur = api_get(a, 'offers')[1]
    neu = [{**o, 'name': 'Wochenangebot Edeka Neu', 'fallback': 'hidden'} if o['id'] == 'edeka' else o for o in cur['offers']] + [{'id': 'metro-woche', 'name': 'Wochenangebot Metro Woche', 'fallback': 'hidden'}]
    r = api_post(a, 'offers_save', {'rev': cur['rev'], 'offers': neu})
    check('Wochenablage · Vorbereitung: Edeka umbenannt und auf eigene Artikelliste, neues Angebot', r[0] == 200, r)
    alle = len(woche(a, '2026-43')[1]['offer']['items'])
    c, w = woche(a, '2026-43', 'edeka')
    check('Damalige Einstellung: Edeka in KW 43 mit damaligem Namen und „folgt dem Wochenangebot“', c == 200 and w.get('einstellung') == 'damals'
          and w['angebot']['name'] == 'Wochenangebot Edeka' and w.get('artikel') == alle and preis_von(w, '10601')[0] == 22, (w.get('einstellung'), w.get('angebot'), w.get('artikel'), alle))
    namen = {o['id']: o['name'] for o in w.get('angebote', [])}
    check('… Auswahl der Woche: damalige Namen, heutige Angebote ergänzt', namen.get('edeka') == 'Wochenangebot Edeka' and namen.get('metro-woche') == 'Wochenangebot Metro Woche', namen)
    c, w = woche(a, '2026-42', 'edeka')
    check('… ohne Ablage (Preisverlauf): heutige Einstellung (eigene Liste ohne eigene Preise = leer)', c == 200 and w.get('einstellung') == 'heute' and w.get('artikel') == 0
          and w['angebot']['name'] == 'Wochenangebot Edeka Neu', (w.get('einstellung'), w.get('artikel')))
    c, w = woche(a, '2026-43', 'metro-woche')
    check('Angebot, das es in der Woche noch nicht gab: kein Angebot, Hinweis', c == 200 and w.get('fehlt') is True and w.get('offer') is None, (c, w.get('fehlt')))
    a.goto(B + '/admin/#woche/2026-43'); a.wait_for_selector('#dlg-wochen[open] #fw-angebot')
    a.select_option('#fw-angebot', 'metro-woche'); a.wait_for_selector('#fw-leer:not([hidden])')
    check('… im Fenster: „gab es in KW 43/2026 noch nicht“', 'gab es in KW' in a.inner_text('#fw-leer') and 'noch nicht' in a.inner_text('#fw-leer'), a.inner_text('#fw-leer'))
    a.wait_for_function(RUHE); a.screenshot(path=SH + '/fruehere-wochen-fehlt.png')
    a.select_option('#fw-angebot', 'std'); a.keyboard.press('Escape'); a.wait_for_selector('#dlg-wochen', state='hidden')

    # Alte Versionen: vor dem Löschen (keep_versions = 60) in die Ablage retten, wenn die KW dort keinen neueren Stand hat
    vorhanden = len(api_get(a, 'versions')[1]['versions'])
    weg = vorhanden + 1   # so viele der ältesten Versionen löscht die nächste Veröffentlichung
    basis = api_get(a, 'draft')[1]['published']
    for i in range(60):
        v = json.loads(json.dumps(basis))
        v['meta']['week'] = 20 if i < weg else 21
        v['publishedAt'] = f'2020-01-01T00:00:{i:02d}.000Z'
        next(x for x in v['items'] if x['code'] == '10601')['price'] = {'status': 'value', 'value': 100 + i}
        storage_write(f'versionen/20200101-{i:06d}-abcdef', v)
    d = api_get(a, 'draft')[1]
    m = d['draft'] or d['published']
    m['meta']['notice'] = 'Wochenablage-Test'
    api_post(a, 'save_draft', {'revision': d['revision'], 'model': m})
    a.wait_for_selector('#screen-editor:not([hidden])')
    veroeffentlichen(a)
    gerettet = dok('angebot-woche/2026-20')
    v20 = next((x for x in (gerettet or {}).get('modell', {}).get('items', []) if x.get('code') == '10601'), {})
    ids = [x['id'] for x in api_get(a, 'versions')[1]['versions']]
    check('Gelöschte alte Versionen gerettet: neuester Stand der KW, ohne Definitionen; nicht gelöschte KW nicht abgelegt', gerettet and gerettet.get('quelle') == 'version'
          and gerettet.get('angebote') is None and gerettet.get('stand') == f'2020-01-01T00:00:{weg - 1:02d}.000Z' and v20.get('price', {}).get('value') == 100 + weg - 1
          and '2026-21' not in ablage_namen() and not any(x.startswith('20200101-') and int(x[9:15]) < weg for x in ids) and len(ids) == 60, ((gerettet or {}).get('stand'), weg, len(ids)))
    c, w = woche(a, '2026-20')
    c2, w2 = woche(a, '2026-20', 'bela')
    check('… frühere Wochen zeigen die gerettete Woche (Kundenangebot nach heutiger Einstellung)', c == 200 and w.get('quelle') == 'ablage' and preis_von(w, '10601')[0] == 100 + weg - 1
          and c2 == 200 and w2.get('einstellung') == 'heute', (w.get('quelle'), preis_von(w, '10601')[0]))
    c, w = woche(a, '2026-21')
    check('… nicht gelöschte Versionen weiter aus versionen/*', c == 200 and w.get('quelle') == 'version' and preis_von(w, '10601')[0] == 159, (w.get('quelle'), preis_von(w, '10601')[0]))

    # Nie auf der Kundenseite: intern in jeder Trennstufe; getrennt liegt die Ablage nur im internen Ordner
    import sys
    sys.path.insert(0, os.path.join(REPO, 'deploy'))
    import daten_trennen as dt
    intern = all(dt.ist_intern('angebot-woche/2026-43', dt.kundenseite(stufe=st)) for st in range(1, dt.ZIELSTUFE + 1))
    getrennt = trennstufe() == 0 or (_storage_raw(os.environ['UDATA'], 'angebot-woche/2026-43') is None and datenordner('angebot-woche/2026-43') == os.environ.get('UINTERN'))
    check('Wochenablage nie auf der Kundenseite (intern ab Trennstufe 1; getrennt nur im internen Ordner)', intern and getrennt, (intern, trennstufe()))

with sync_playwright() as p:
    br = p.chromium.launch(); a = br.new_page(viewport={'width': 1440, 'height': 950}); errs = []
    a.on('pageerror', lambda e: errs.append(str(e))); a.on('dialog', lambda d: d.accept())
    a.goto(B + '/admin/'); a.wait_for_selector('#screen-auth:not([hidden])')
    a.fill('#au-user', 'admin'); a.fill('#pw1', 'Sicheres-Passwort-1'); a.fill('#pw2', 'Sicheres-Passwort-1'); a.click('#auth-submit'); a.wait_for_selector('tr[data-id]')
    a.click('#vt-hist'); a.wait_for_selector('#hist-data')
    try: a.wait_for_function("/Woche/.test(document.querySelector('#hist-data').textContent)", timeout=10000)  # Daten werden nachgeladen
    except Exception: pass
    check('no week chips in view', a.locator('.wchip').count() == 0 and '1 Woche' in a.text_content('#hist-data'), a.inner_text('#hist-data'))
    a.click('#hist-data'); a.wait_for_selector('#dlg-hist-data[open]')
    check('data dialog: KW43 from publication', a.locator('.hdtab tbody tr').count() == 1 and 'KW 43/2026' in a.inner_text('.hdtab') and 'Veröffentlichung' in a.inner_text('.hdtab'), a.inner_text('#dlg-hist-data'))
    a.keyboard.press('Escape'); a.wait_for_timeout(200)
    check('hint for <2 weeks', 'mindestens zwei Wochen' in a.inner_text('#view-hist'))
    check('topbar edit buttons hidden', not a.locator('#btn-import').is_visible())
    files = sorted(f for f in glob.glob(FIX + '/angebote/*.xlsx') if 'KW 43' not in f and 'KW 44' not in f)  # KW 43 ist bereits veröffentlicht
    with a.expect_file_chooser() as fc: a.click('#hist-upload')
    fc.value.set_files(files)
    a.wait_for_function("document.querySelectorAll('#hist-import-body tr[data-i]').length==7 && ![...document.querySelectorAll('#hist-import-body td')].some(td=>td.textContent.includes('wird gelesen'))", timeout=20000)
    t = a.inner_text('#dlg-hist-import')
    check('7 files parsed, one needs KW', t.count('neu') >= 6 and 'KW/Jahr eintragen' in t, re.sub(r'\s+', ' ', t)[:300])
    a.screenshot(path=SH + '/hist-import.png')
    # Handy: Dateiliste ohne seitliches Scrollen im Fenster (Datei oben, darunter KW, Jahr, Artikel, Status)
    a.set_viewport_size({'width': 390, 'height': 844})
    a.wait_for_function("getComputedStyle(document.querySelector('.hitab thead')).display === 'none'")
    breit = a.evaluate("(() => { const d = document.querySelector('#dlg-hist-import'); return [d.scrollWidth, d.clientWidth]; })()")
    check('390 px: Alte Angebote hochladen ohne seitliches Scrollen', breit[0] <= breit[1] + 1, breit)
    a.screenshot(path=SH + '/hist-import-390.png')
    a.set_viewport_size({'width': 1440, 'height': 950})
    row = a.locator('#hist-import-body tr:has-text("Angebotsliste alt") input[data-hf="week"]'); row.fill('36'); row.press('Tab'); a.wait_for_timeout(150)
    yr = a.locator('#hist-import-body tr:has-text("Angebotsliste alt") input[data-hf="year"]')
    if not yr.input_value(): yr.fill('2026'); yr.press('Tab'); a.wait_for_timeout(150)
    check('manual KW fixes file', '7 Wochen übernehmen' in a.inner_text('#dlg-hist-import [data-hi="save"]'), a.inner_text('#dlg-hist-import [data-hi="save"]'))
    a.click('#dlg-hist-import [data-hi="save"]'); a.wait_for_function("document.querySelector('#hi-progress').textContent.includes('übernommen')", timeout=30000)
    check('saved 7 weeks', '7 Wochen übernommen' in a.inner_text('#hi-progress'), a.inner_text('#hi-progress'))
    a.click('#dlg-hist-import [data-close]'); a.wait_for_timeout(400)
    check('data button shows 8 weeks', '8 Wochen' in a.text_content('#hist-data'), a.inner_text('#hist-data'))
    check('upload notice gone with ≥2 weeks', a.locator('#hist-upload').count() == 0)
    n = a.locator('.htab tbody tr').count(); check('series rows ≈ 276', 270 <= n <= 285, n)
    a.screenshot(path=SH + '/hist-list.png')
    a.fill('#hist-q', '10601'); a.wait_for_timeout(300)
    check('search filters', a.locator('.htab tbody tr').count() == 1)
    a.locator('.htab tbody tr').first.click(); a.wait_for_selector('#dlg-series[open]')
    check('series detail has 8 week rows', a.locator('.wtab tbody tr').count() == 8)
    check('chart drawn with points', a.locator('.hchart circle').count() == 8)
    a.screenshot(path=SH + '/hist-detail.png')
    a.keyboard.press('Escape')
    a.fill('#hist-q', '10823'); a.wait_for_timeout(300)
    check('renamed article stays one series', a.locator('.htab tbody tr').count() == 1)
    a.locator('.htab tbody tr').first.click(); a.wait_for_selector('#dlg-series[open]')
    check('deviating name shown in week table', 'Steakhüfte frisch, Färse' in a.inner_text('#dlg-series .wtab'))
    a.keyboard.press('Escape')
    a.fill('#hist-q', '11617'); a.wait_for_timeout(300)
    wk = a.locator('.htab tbody tr td.h-weeks').first.inner_text().strip()
    check('late-listed item: 6 weeks', wk == '6', wk)
    a.fill('#hist-q', '11598'); a.wait_for_timeout(300); check('duplicate code → 2 series', a.locator('.htab tbody tr').count() == 2)
    a.fill('#hist-q', ''); a.wait_for_timeout(250)
    a.check('#hist-only'); a.wait_for_timeout(250); nchg = a.locator('.htab tbody tr').count(); check('only changed filter', 0 < nchg < 276, nchg)
    a.uncheck('#hist-only')
    check('range default 3M pressed', a.get_attribute('#view-hist [data-hrange="3M"]', 'aria-pressed') == 'true')
    a.fill('#hist-q', '10601'); a.wait_for_timeout(300)
    a.click('#view-hist [data-hrange="1M"]'); a.wait_for_timeout(250)
    wk1 = a.locator('.htab tbody tr td.h-weeks').first.inner_text().strip()
    check('1M → 5 weeks (KW 39–43)', wk1 == '5' and 'KW 39/2026' in a.inner_text('#hist-count'), (wk1, a.inner_text('#hist-count')))
    a.click('#view-hist [data-hrange="1W"]'); a.wait_for_timeout(250)
    wk2 = a.locator('.htab tbody tr td.h-weeks').first.inner_text().strip(); check('1W → 2 weeks', wk2 == '2', wk2)
    check('1W spark has 2 points', a.locator('.htab tbody tr .spark').count() == 1)
    a.locator('.htab tbody tr').first.click(); a.wait_for_selector('#dlg-series[open]')
    check('detail respects 1W', a.locator('.wtab tbody tr').count() == 2, a.locator('.wtab tbody tr').count())
    a.click('#dlg-series [data-hrange="Alle"]'); a.wait_for_timeout(250)
    check('detail range switch → 8 rows', a.locator('.wtab tbody tr').count() == 8 and a.locator('.hchart circle').count() == 8)
    a.screenshot(path=SH + '/hist-detail-range.png')
    a.keyboard.press('Escape'); a.wait_for_timeout(200)
    check('list followed detail range', a.get_attribute('#view-hist [data-hrange="Alle"]', 'aria-pressed') == 'true' and a.locator('.htab tbody tr td.h-weeks').first.inner_text().strip() == '8')
    a.reload(); a.wait_for_selector('tr[data-id]'); a.click('#vt-hist'); a.wait_for_selector('.htab')
    check('range persisted', a.get_attribute('#view-hist [data-hrange="Alle"]', 'aria-pressed') == 'true')
    a.click('#view-hist [data-hrange="3M"]'); a.fill('#hist-q', ''); a.wait_for_timeout(250)
    a.select_option('#hist-sort', 'up'); a.wait_for_timeout(250)
    first = a.locator('.htab tbody tr').first.locator('.h-delta').inner_text(); check('sort by increase', first.startswith('+'), first)
    a.click('#hist-data'); a.wait_for_selector('#dlg-hist-data[open]')
    t = a.inner_text('#dlg-hist-data'); check('data dialog lists 8 weeks newest first', a.locator('.hdtab tbody tr').count() == 8 and t.index('KW 43/2026\t') < t.index('KW 36/2026\t') and 'Angebotsliste alt.xlsx' in t and '19.10.–25.10.' in t, t[:200])
    a.screenshot(path=SH + '/hist-data.png')
    a.locator('.hdtab tbody tr:has-text("KW 37/2026") [data-hdel]').click(); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(700)
    check('week deleted, dialog stays open + updated', a.locator('#dlg-hist-data[open]').count() == 1 and a.locator('.hdtab tbody tr').count() == 7 and '7 Wochen' in a.text_content('#hist-data'))
    a.keyboard.press('Escape'); a.wait_for_timeout(200)
    a.click('#vt-edit'); a.locator('tr[data-id]:has(input[data-f="code"][value="10601"]) [data-act="item"]').click()
    a.wait_for_function("document.querySelector('#item-hist') && /Woche/.test(document.querySelector('#item-hist').textContent)", timeout=8000)
    check('item dialog shows history', '7 Wochen' in a.inner_text('#item-hist'), a.inner_text('#item-hist'))
    a.screenshot(path=SH + '/hist-item.png')
    a.click('#item-hist [data-ia="hist-open"]'); a.wait_for_selector('#dlg-series[open]'); check('jump to series from item', 'Roastbeef' in a.inner_text('#ser-title'))
    a.keyboard.press('Escape')
    a.click('#vt-edit'); i = a.locator('tr[data-id]:has(input[data-f="code"][value="10601"]) input[data-f="price"]'); i.fill('25,5'); i.press('Tab'); a.wait_for_timeout(1300)
    veroeffentlichen(a)
    a.click('#vt-hist'); a.wait_for_selector('.htab'); a.fill('#hist-q', '10601'); a.wait_for_timeout(300)
    check('publish updates current week in history', '25,50' in a.inner_text('.htab tbody tr .h-cur'), a.inner_text('.htab tbody tr .h-cur'))
    a.set_viewport_size({'width': 390, 'height': 844}); a.fill('#hist-q', ''); a.wait_for_timeout(300); a.screenshot(path=SH + '/hist-mobile.png')
    a.click('#hist-data'); a.wait_for_selector('#dlg-hist-data[open]'); a.wait_for_timeout(200); a.screenshot(path=SH + '/hist-data-mobile.png')
    dsw = a.evaluate("document.querySelector('#dlg-hist-data .dlg-body').scrollWidth - document.querySelector('#dlg-hist-data .dlg-body').clientWidth"); check('mobile data dialog fits', dsw <= 1, dsw)
    a.keyboard.press('Escape')
    sw = a.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    fruehere_wochen_pruefen(a, br, errs)
    wochenablage_pruefen(a)
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
