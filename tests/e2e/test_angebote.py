"""Mehrere Angebote: Kundenangebote mit eigenen Preisen, eigene Artikelliste je Angebot (Artikel hinzufügen wie im
Einzelangebot, entfernen nur im gewählten Angebot, Umstellung „folgt dem Wochenangebot“ → eigene Liste), Verwaltung,
Übernahme, Excel-Import ohne Verlust der Kundenangebote, Veröffentlichen, Auslieferung nur an Berechtigte (Regel:
Kundenpreise nie öffentlich), Werbung je Angebot (Fenster, Prüfung, Auslieferung nur des eigenen Eintrags, Angebotsseite), zweite Werbung rechts daneben,
Angebotsauswahl unter den Bereichen der Seitenleiste; Kundenangebot kopieren (alles außer den Kunden, in den Entwurf)."""
import sys
from umgebung import shot
from umgebung import BASE  # Testserver je Gruppe (parallel)
import json, re
from playwright.sync_api import sync_playwright
from versand_hilfe import veroeffentlichen
from umgebung import SH, storage_raw, storage_write
from testdaten import de, preis
from kunden_hilfe import Client
B = BASE
res = []
def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))

def login(pg, user, pw):
    pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
    pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit'); pg.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
def post(pg, action, body):
    return pg.evaluate("""async ([a, b]) => { const s = await (await fetch('/api/?action=status')).json();
      const r = await fetch('/api/?action=' + a, {method:'POST', headers:{'Content-Type':'application/json','X-CSRF-Token':s.csrf || ''}, body: JSON.stringify(b)}); let j=null; try { j = await r.json(); } catch(e) {} return [r.status, j]; }""", [action, body])
def get(pg, q):
    return pg.evaluate("""async (q) => { const r = await fetch('/api/?action=' + q); let j=null; try { j = await r.json(); } catch(e) {} return [r.status, j]; }""", q)
def bestaetigt(pg, toast_text, timeout=15000):
    # Löschen braucht eine Bestätigung jünger als 5 Minuten (Anmeldung zählt). Läuft der Test unter Last länger, fragt
    # die Oberfläche nach dem Passwort – dann bestätigen, statt am Zeitfenster zu scheitern.
    sel = f'#toast.show:has-text("{toast_text}")'
    pg.wait_for_function("""(t) => document.querySelector('#dlg-reauth[open]')
        || ((x) => x && x.classList.contains('show') && x.textContent.includes(t))(document.querySelector('#toast'))""", arg=toast_text, timeout=timeout)
    if pg.locator('#dlg-reauth[open]').count():
        pg.fill('#reauth-password', 'Sicheres-Passwort-1'); pg.click('#reauth-submit')
        pg.wait_for_selector(sel, timeout=timeout)
def post_bestaetigt(pg, action, body):
    r = post(pg, action, body)
    if r[0] == 403 and (r[1] or {}).get('code') == 'confirmation_required':
        post(pg, 'reauth', {'password': 'Sicheres-Passwort-1'}); r = post(pg, action, body)
    return r
def row(pg, code): return pg.locator(f'tr[data-id]:has(input[data-f="code"][value="{code}"])').first
def wait_saved(pg): pg.wait_for_function("document.querySelector('#save-state').className.includes('saved') || /Keine Änderungen/.test(document.querySelector('#save-state').textContent)", timeout=8000)
def tab(pg, label): return pg.locator(f'#offer-bar [data-offer]:has-text("{label}")').first
def zahl(pg, label): return int(tab(pg, label).locator('.ob-z').inner_text().replace('.', ''))
def codes(pg): return pg.locator('#groups tr[data-id] input[data-f=code]').evaluate_all('e => e.map(x => x.value)')
def hinzufuegen(pg, q, preise):
    """„Artikel hinzufügen“: Suche, markieren, Preis je Artikel, übernehmen"""
    pg.click('#btn-add-art'); pg.wait_for_selector('#dlg-ez-pick[open] #ezp-q')
    pg.fill('#ezp-q', q)
    for code, pr in preise.items():
        pg.wait_for_selector(f'#ezp-list tr[data-code="{code}"]'); pg.click(f'#ezp-list tr[data-code="{code}"] .ezp-n')
        if pr is not None: pg.fill(f'#ezp-list [data-preis="{code}"]', pr)
    pg.click('#ezp-ok'); pg.wait_for_selector('#dlg-ez-pick', state='hidden')
def item(offer, code): return next((i for i in offer['items'] if i['code'] == code), None)

P10601, P10823 = preis('10601'), preis('10823')


RUHE = "document.getAnimations().every((x) => x.playState !== 'running')"   # Fenster fertig eingeblendet (Bildschirmfoto)


def dok(name):
    """Gespeichertes Dokument (ohne PHP-Schutzzeile) oder None"""
    raw = storage_raw(name)
    return json.loads(raw.split('?>\n', 1)[-1]) if raw else None


def ohne_kennung(o):
    """Aufgelöstes Angebot ohne Name/ID des Angebots – zum Vergleich Quelle ↔ Kopie"""
    m = {k: v for k, v in o['meta'].items() if k not in ('offerId', 'offerName')}
    return {'items': o['items'], 'groups': o['groups'], 'sections': o['sections'], 'meta': m}


def kopieren_pruefen(a, br, v):
    """Kundenangebot kopieren (Inhaber 13.11.2026): offer_kopieren nimmt alles außer den Kunden mit – eigene Preise, eigene
    Bezeichnungen, Empfehlungen je Angebot, Werbung, Regel der Artikelliste (damit auch ausgeblendete Artikel) – in den
    Entwurf; Original und veröffentlichtes Angebot bleiben unverändert. Rechte, Grenzfälle, Oberfläche (Desktop, 390 px)."""
    # Vorbereitung: Kundengruppe 71 bei „Bela“ (folgt dem Wochenangebot), dazu im Entwurf eigener Preis + Bezeichnung,
    # ausgeblendeter Artikel, „auf Anfrage“ mit Sonderposten nur für Bela, Werbung
    kg = get(a, 'kundengruppen')[1]
    post_bestaetigt(a, 'kundengruppen_save', {'rev': kg['rev'], 'groups': kg['groups'] + [{'nr': '71', 'name': 'Testgruppe Bela'}]})
    cur = get(a, 'offers')[1]
    r = post(a, 'offers_save', {'rev': cur['rev'], 'offers': [{**o, 'gruppen': ['71'] if o['id'] == 'bela' else o.get('gruppen', [])} for o in cur['offers']]})
    check('Kopieren · Vorbereitung: Kundengruppe 71 bei Bela', r[0] == 200 and next(o for o in r[1]['offers'] if o['id'] == 'bela').get('gruppen') == ['71'], r)
    d = get(a, 'draft')[1]
    mdl = d['draft'] or d['published']
    it = {i['code']: i for i in mdl['items']}
    it['10601'].setdefault('variants', {})['bela'] = {'status': 'value', 'value': 11.5}
    it['10601'].setdefault('namen', {})['bela'] = 'Bela-Spezial'
    it['10823'].setdefault('variants', {})['bela'] = {'status': 'hidden'}
    it['10701'].setdefault('variants', {})['bela'] = {'status': 'request'}
    it['10701']['sale'] = {'mark': True, 'offers': {'bela': {'value': 7.77}}}
    mdl['meta'].setdefault('werbung', {})['bela'] = {'titel': 'Bela-Aktion', 'artikel': [{'id': it['10601']['id'], 'text': 'nur diese Woche'}]}
    r = post(a, 'save_draft', {'revision': d['revision'], 'model': mdl})
    check('Kopieren · Vorbereitung: Bela mit eigenem Preis, ausgeblendetem Artikel, Bezeichnung, Sonderposten und Werbung', r[0] == 200, r)
    rev0 = (r[1] or {}).get('revision')
    n_bela = sum(1 for i in mdl['items'] if ((i.get('variants') or {}).get('bela') or {}).get('status') != 'hidden')
    bela_vorher = get(a, 'offer&angebot=bela&draft=1')[1]['offer']
    entwurf_vorher, pub_vorher, of0 = dok('entwurf'), dok('angebot'), get(a, 'offers')[1]
    body = lambda **k: {'quelle': 'bela', 'name': 'Kopie von Wochenangebot Bela', 'rev': of0['rev'], 'revision': rev0, **k}

    # Rechte: ohne Anmeldung, Kunde, Leser, ohne „Entwurf bearbeiten“, ohne Modulzugang, ohne CSRF
    check('Kopieren: ohne Anmeldung 401', Client('198.51.100.61').call('offer_kopieren', body())[0] == 401)
    kd = get(a, 'kunden')[1]
    r = post_bestaetigt(a, 'kunde_save', {'id': '', 'rev': kd['rev'], 'firma': 'Kantine Kopie', 'nr': 'K-71', 'email': 'kopie@example.org', 'active': True, 'angebote': ['bela'],
                                         'login': {'username': 'kantine.kopie', 'password': 'Kantine-Kennwort-5', 'mustChange': False, 'active': True}})
    K = Client('198.51.100.62')
    check('Kopieren · Vorbereitung: Kunde angemeldet', r[0] == 200 and K.call('kunde_login', {'username': 'kantine.kopie', 'password': 'Kantine-Kennwort-5'})[0] == 200, r)
    check('Kopieren: Kunde 401 (keine Mitarbeiteraktion)', K.call('offer_kopieren', body())[0] == 401)
    for nm, deny in (('Kopa', ['angebot.bearbeiten']), ('Kopz', ['angebot.zugang'])):
        post_bestaetigt(a, 'user_save', {'name': nm, 'username': nm.lower(), 'role': 'editor', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False, 'grant': [], 'deny': deny})
    V, Ka, Kz = Client('198.51.100.63'), Client('198.51.100.64'), Client('198.51.100.65')
    V.call('login', {'username': 'vera', 'password': 'Leserin-Zugang-1'})
    Ka.call('login', {'username': 'kopa', 'password': 'Bearbeiter-Zugang-1'}); Kz.call('login', {'username': 'kopz', 'password': 'Bearbeiter-Zugang-1'})
    check('Kopieren: Leser 403', V.call('offer_kopieren', body())[0] == 403)
    check('Kopieren: „Kundenangebote anlegen“ ohne „Entwurf bearbeiten“ 403', Ka.call('offer_kopieren', body())[0] == 403)
    check('Kopieren: ohne Modulzugang Angebot 403', Kz.call('offer_kopieren', body())[0] == 403)
    ohne = a.evaluate("""async (b) => { const r = await fetch('/api/?action=offer_kopieren', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(b)}); return r.status; }""", body())
    check('Kopieren: ohne CSRF-Token abgewiesen', ohne in (401, 403), ohne)
    check('Kopieren: nur per POST', get(a, 'offer_kopieren')[0] == 405)
    check('… nichts angelegt, Entwurf unverändert', get(a, 'offers')[1]['rev'] == of0['rev'] and dok('entwurf') == entwurf_vorher)

    # Grenzfälle: Quelle, Name, veraltete Stände, höchstens 100 Angebote
    check('Kopieren: unbekanntes Angebot 404', post(a, 'offer_kopieren', body(quelle='gibt-es-nicht'))[0] == 404 and post(a, 'offer_kopieren', body(quelle='../x'))[0] == 404)
    check('Kopieren: Name zu kurz, vergeben oder „Wochenangebot“ 422', post(a, 'offer_kopieren', body(name='x'))[0] == 422
          and post(a, 'offer_kopieren', body(name='wochenangebot bela'))[0] == 422 and post(a, 'offer_kopieren', body(name='Wochenangebot'))[0] == 422)
    check('Kopieren: veraltete Angebotsliste 409', post(a, 'offer_kopieren', body(rev=of0['rev'] - 1))[0] == 409)
    r = post(a, 'offer_kopieren', body(revision=rev0 - 1))
    check('Kopieren: veralteter Entwurf 409 mit Konflikt', r[0] == 409 and (r[1] or {}).get('conflict') is True, r)
    voll = dok('angebote')
    storage_write('angebote', {**voll, 'offers': voll['offers'] + [{'id': f'voll-{i}', 'name': f'Voll {i}', 'fallback': 'hidden'} for i in range(100 - len(voll['offers']))]})
    r = post(a, 'offer_kopieren', body())
    storage_write('angebote', voll)
    check('Kopieren: höchstens 100 Kundenangebote (422)', r[0] == 422 and '100' in (r[1] or {}).get('error', ''), r)
    check('… weiterhin nichts angelegt', get(a, 'offers')[1]['rev'] == of0['rev'] and dok('entwurf') == entwurf_vorher)

    # Kopie von „Bela“: alles außer den Kunden, in den Entwurf
    r = post(a, 'offer_kopieren', body())
    k1 = r[1] or {}
    neu1 = k1.get('id', '')
    check('Kopieren: Bela kopiert (neue ID, Entwurfsrevision +1, Artikelzahl wie Bela)', r[0] == 200 and neu1 and neu1 not in [o['id'] for o in of0['offers']]
          and k1.get('revision') == rev0 + 1 and k1.get('artikel') == n_bela and k1.get('namen') == 1 and k1.get('empfehlungen') == 1 and k1.get('werbung') is True, k1)
    defs = {o['id']: o for o in get(a, 'offers')[1]['offers']}
    check('… Angebot ohne Kundengruppen, gleiche Regel „folgt dem Wochenangebot“; Bela behält Gruppe 71',
          defs.get(neu1, {}).get('name') == 'Kopie von Wochenangebot Bela' and defs[neu1].get('fallback') == 'standard' and not defs[neu1].get('gruppen')
          and defs['bela'].get('gruppen') == ['71'], defs.get(neu1))
    kopie = get(a, f'offer&angebot={neu1}&draft=1')[1]['offer']
    check('… aufgelöst genau wie Bela (Artikel, Preise, Bezeichnungen, Sonderposten, Bereiche, Werbung)', ohne_kennung(kopie) == ohne_kennung(bela_vorher))
    x = {i['code']: i for i in kopie['items']}
    check('… eigener Preis und eigene Bezeichnung, ausgeblendeter Artikel fehlt, Werbung', x.get('10601', {}).get('price') == {'status': 'value', 'value': 11.5}
          and x['10601'].get('name') == 'Bela-Spezial' and '10823' not in x and (kopie['meta'].get('werbung') or {}).get('titel') == 'Bela-Aktion', x.get('10601'))
    en = dok('entwurf')
    roh = all((i.get('variants') or {}).get(neu1) == (i.get('variants') or {}).get('bela') and (i.get('namen') or {}).get(neu1) == (i.get('namen') or {}).get('bela')
              and ((i.get('sale') or {}).get('offers') or {}).get(neu1) == ((i.get('sale') or {}).get('offers') or {}).get('bela') for i in en['items'])
    check('… im Entwurf je Artikel dieselben Einträge (variants, namen, sale.offers) und dieselbe Werbung', roh and en['meta']['werbung'].get(neu1) == en['meta']['werbung'].get('bela')
          and en['rev'] == rev0 + 1)
    unver = lambda m: [((i.get('variants') or {}).get('bela'), (i.get('namen') or {}).get('bela'), ((i.get('sale') or {}).get('offers') or {}).get('bela')) for i in m['items']]
    bela_nach = get(a, 'offer&angebot=bela&draft=1')[1]['offer']
    check('… Original unverändert (Entwurf und Auflösung), veröffentlichtes Angebot unverändert', unver(en) == unver(entwurf_vorher)
          and ohne_kennung(bela_nach) == ohne_kennung(bela_vorher) and bela_nach['meta']['offerName'] == 'Wochenangebot Bela' and dok('angebot') == pub_vorher)
    check('… Kunden sehen die Kopie nicht (nicht zugeordnet)', K.call(f'offer&angebot={neu1}')[0] == 403 and K.call('offer&angebot=bela')[0] == 200)
    log = json.dumps(get(a, 'log')[1], ensure_ascii=False)
    check('… Protokoll „als Kopie von“ mit Inhalt', 'als Kopie von „Wochenangebot Bela“' in log and '1 eigene Bezeichnung' in log)

    # Wochenangebot als Quelle: eigene Artikelliste mit allen Artikeln des Wochenangebots und dem Wochenpreis als eigenem Preis
    cur, d = get(a, 'offers')[1], get(a, 'draft')[1]
    r = post(a, 'offer_kopieren', {'quelle': 'std', 'name': 'Kopie von Wochenangebot', 'rev': cur['rev'], 'revision': d['revision']})
    neu2 = (r[1] or {}).get('id', '')
    std_e, k2 = get(a, 'offer&angebot=std&draft=1')[1]['offer'], get(a, f'offer&angebot={neu2}&draft=1')[1]['offer'] if r[0] == 200 else {'items': [], 'meta': {}}
    preise = lambda o: [(i['code'], i['name'], i['price'].get('value') if i['price']['status'] == 'value' else 'request', bool(i.get('sale'))) for i in o['items']]
    check('Kopieren: Wochenangebot als Quelle – eigene Artikelliste, alle Artikel mit Wochenpreis, Werbung', r[0] == 200
          and next((o for o in r[1]['offers'] if o['id'] == neu2), {}).get('fallback') == 'hidden' and preise(k2) == preise(std_e) and len(k2['items']) > 0
          and k2['meta'].get('werbung') == std_e['meta'].get('werbung'), (r[0], preise(k2)[:3], preise(std_e)[:3]))
    # gelöschte IDs werden nie wieder vergeben (wie offers_save)
    cur, d = get(a, 'offers')[1], get(a, 'draft')[1]
    r = post(a, 'offer_kopieren', {'quelle': 'edeka', 'name': 'Wochenangebot Metro', 'rev': cur['rev'], 'revision': d['revision']})
    gel = dok('angebote').get('geloescht', [])
    check('Kopieren: nie die ID eines gelöschten Angebots', r[0] == 200 and r[1]['id'].startswith('metro-') and r[1]['id'] not in gel, (r[1] or {}).get('id'))
    # „sonder-…“ ist Sonderangeboten vorbehalten (#355): die Kopie bleibt ein gewöhnliches Kundenangebot
    cur, d = get(a, 'offers')[1], get(a, 'draft')[1]
    r = post(a, 'offer_kopieren', {'quelle': 'bela', 'name': 'Sonder Bela', 'rev': cur['rev'], 'revision': d['revision']})
    neu_s = next((o for o in (r[1] or {}).get('offers', []) if o['name'] == 'Sonder Bela'), {})
    check('Kopieren: Name „Sonder …“ ergibt keine Sonderangebots-ID, Kopie ohne Gültigkeit und Gruppen', r[0] == 200
          and not neu_s.get('id', 'sonder-').startswith('sonder-') and 'art' not in neu_s and 'sonderGruppen' not in neu_s and not neu_s.get('gruppen'), neu_s)
    # ohne Entwurf (gerade veröffentlicht): Kopie auf Basis des veröffentlichten Angebots
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    veroeffentlichen(a)
    cur, d = get(a, 'offers')[1], get(a, 'draft')[1]
    r = post(a, 'offer_kopieren', {'quelle': 'bela', 'name': 'Bela nach Veröffentlichung', 'rev': cur['rev'], 'revision': d['revision']})
    neu3 = (r[1] or {}).get('id', '')
    check('Kopieren ohne offenen Entwurf: Entwurf aus dem veröffentlichten Angebot, Kopie wie Bela', d['draft'] is None and r[0] == 200 and dok('entwurf')['rev'] == d['revision'] + 1
          and ohne_kennung(get(a, f'offer&angebot={neu3}&draft=1')[1]['offer']) == ohne_kennung(get(a, 'offer&angebot=bela')[1]['offer']), (d['draft'] is None, r[0]))

    # Oberfläche: Stammdaten → Angebote, Knopf je Angebot, Fenster mit vorbelegtem Namen, danach neues Angebot im Editor gewählt
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.click('#vt-angebote'); a.wait_for_selector('#view-angebote:not([hidden]) tr[data-oi]')
    n_knopf = a.locator('#view-angebote [data-ofa=kopieren]').count()
    check('Stammdaten → Angebote: „Kopieren“ beim Wochenangebot und bei jedem Kundenangebot', a.locator('#view-angebote tr.of-std [data-ofa=kopieren]').count() == 1
          and n_knopf == a.locator('#view-angebote tr[data-oi]').count() + 1, n_knopf)
    a.screenshot(path=SH + '/angebot-kopieren-liste.png')
    a.click('#view-angebote [data-ofa=kopieren][data-ofid="bela"]'); a.wait_for_selector('#dlg-angebot-kopieren[open] #ak-name')
    t = a.inner_text('#dlg-angebot-kopieren')
    check('Fenster: Name vorbelegt (vergebener Name mit Nummer), Inhalt und Hinweis zu Kunden', a.input_value('#ak-name') == 'Kopie von Wochenangebot Bela (2)'
          and '1 eigene Bezeichnung' in t and 'Werbung' in t and 'Kundengruppen' in t and 'veröffentlicht' in t, t)
    a.wait_for_function(RUHE); a.screenshot(path=SH + '/angebot-kopieren.png')
    a.fill('#ak-name', 'kopie von wochenangebot bela'); a.click('#ak-ok')
    a.wait_for_function("document.querySelector('#ak-err').textContent.includes('bereits vergeben')")
    check('Fenster: vergebener Name → Hinweis, Fenster bleibt offen', a.locator('#dlg-angebot-kopieren[open]').count() == 1)
    a.fill('#ak-name', 'Wochenangebot Bela Sommer'); a.click('#ak-ok')
    a.wait_for_selector('#dlg-angebot-kopieren', state='hidden')
    a.wait_for_selector('#view-edit:not([hidden])'); a.wait_for_selector('#offer-bar [aria-selected="true"]:has-text("Bela Sommer")')
    check('… danach im Editor gewählt: Kopie mit allen Artikeln von Bela, Name im Kopf, Hinweis', zahl(a, 'Bela Sommer') == n_bela and 'Wochenangebot Bela Sommer' in a.inner_text('#oh-name')
          and 'angelegt' in a.inner_text('#toast'), (zahl(a, 'Bela Sommer'), n_bela))
    a.wait_for_function("!/pending|saving/.test(document.querySelector('#save-state').className)")
    a.screenshot(path=SH + '/angebot-kopieren-editor.png')
    neu4 = next((o['id'] for o in get(a, 'offers')[1]['offers'] if o['name'] == 'Wochenangebot Bela Sommer'), '')
    check('… Kopie aus der Oberfläche wie Bela aufgelöst', neu4 and ohne_kennung(get(a, f'offer&angebot={neu4}&draft=1')[1]['offer']) == ohne_kennung(get(a, 'offer&angebot=bela&draft=1')[1]['offer']))
    a.click('#offer-head [data-ob=kopieren]'); a.wait_for_selector('#dlg-angebot-kopieren[open] #ak-name')
    check('Editor: „Kopieren“ im Kopf des gewählten Angebots, Name vorbelegt', a.input_value('#ak-name') == 'Kopie von Wochenangebot Bela Sommer')
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-angebot-kopieren', state='hidden')
    v.reload(); v.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    check('Leser: kein „Kopieren“', v.locator('[data-ob=kopieren], [data-ofa=kopieren]').count() == 0)
    # 390 px: Fenster passt ohne seitliches Scrollen
    m = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True); merr = []
    m.on('pageerror', lambda x: merr.append(str(x)))
    login(m, 'admin', 'Sicheres-Passwort-1')
    m.click('#offer-head [data-ob=kopieren]'); m.wait_for_selector('#dlg-angebot-kopieren[open] #ak-name')
    bw = m.evaluate("document.querySelector('#dlg-angebot-kopieren').getBoundingClientRect().right")
    sw = m.evaluate('document.documentElement.scrollWidth')
    check('390 px: Fenster „Angebot kopieren“ passt, kein seitliches Scrollen, keine JS-Fehler', bw <= 390 and sw <= 390 and not merr, (bw, sw, merr))
    m.wait_for_function(RUHE); m.screenshot(path=SH + '/angebot-kopieren-mobil.png'); m.close()

with sync_playwright() as p:
    br = p.chromium.launch()
    actx = br.new_context(viewport={'width': 1440, 'height': 950}); a = actx.new_page(); errs = []
    a.on('pageerror', lambda e: errs.append(str(e))); a.on('dialog', lambda d: d.accept())
    login(a, 'admin', 'Sicheres-Passwort-1')
    a.wait_for_timeout(600); wait_saved(a)
    # sauberer Ausgangspunkt
    veroeffentlichen(a)
    ids0 = a.locator('#offer-bar [data-offer]').evaluate_all('e => e.map(x => x.dataset.offer)')
    check('Angebotsliste links: Wochenangebot + 4 Kundenangebote', ids0 == ['std', 'chefs-culinar', 'handelshof-efs', 'edeka', 'bela'], ids0)
    check('standard selected by default', a.get_attribute('#offer-bar [data-offer="std"]', 'aria-selected') == 'true')
    n_std = len(codes(a))
    check('Liste zeigt Artikelzahl je Angebot; bestehende Angebote folgen dem Wochenangebot', zahl(a, 'Wochenangebot') == n_std and zahl(a, 'Edeka') == n_std
          and 'folgt dem Wochenangebot' in tab(a, 'Edeka').inner_text(), (zahl(a, 'Wochenangebot'), zahl(a, 'Edeka'), n_std))
    check('Leiste „Kurzes MHD“ zugeklappt (ohne Bestand: ausgeblendet), „Bestand ohne Preis“ entfallen', a.locator('#ed-panels .np-card.open').count() == 0 and a.locator('#noprice-panel').count() == 0)
    check('Angebotsauswahl unter den Bereichen der Seitenleiste (Desktop), nur bei „Angebot bearbeiten“', a.evaluate("document.querySelector('#offer-bar').parentElement.classList.contains('side-nav')")
          and a.evaluate("(() => { const t = document.querySelector('.side-tabs').getBoundingClientRect(), o = document.querySelector('#offer-bar').getBoundingClientRect(); return o.top >= t.bottom - 1 && Math.abs(o.left - t.left) < 30; })()"))
    a.click('#vt-hist'); a.wait_for_selector('#view-hist:not([hidden])')
    check('… in anderen Bereichen ausgeblendet', not a.locator('#offer-bar').is_visible())
    a.click('#vt-edit'); a.wait_for_selector('#offer-bar [data-offer="std"]', state='visible')
    # Edeka: eigene Preise
    tab(a, 'Edeka').click(); a.wait_for_timeout(200)
    th = a.locator('.gcard').first.locator('thead').inner_text()
    check('price header names offer', 'Edeka' in th, re.sub(r'\s+', ' ', th))
    vi = row(a, '10601').locator('input[data-f=vprice]')
    check('empty variant shows standard as placeholder', vi.input_value() == '' and vi.get_attribute('placeholder') == 'Std. ' + de(P10601), vi.get_attribute('placeholder'))
    vi.fill('22'); vi.press('Tab'); wait_saved(a)
    check('own price saved + formatted', row(a, '10601').locator('input[data-f=vprice]').input_value() == '22,00')
    check('row marked as price change', 'is-price' in row(a, '10601').get_attribute('class'))
    check('Knopf „Veröffentlichen“ nennt den Angebotspreis', '1 Angebotspreis geändert' in (a.get_attribute('#offen-zahl, #offen-liste', 'title') or ''), a.get_attribute('#offen-zahl, #offen-liste', 'title'))
    check('Kopf: Angebot „folgt dem Wochenangebot“ mit Hinweis zur Umstellung', 'Folgt dem Wochenangebot' in a.inner_text('#offer-head') and a.locator('#offer-head [data-ob=umstellen]').count() == 1)
    row(a, '10823').locator('[data-act=remove]').click(); wait_saved(a)
    check('✕ entfernt nur aus diesem Angebot', row(a, '10823').count() == 0 and zahl(a, 'Edeka') == n_std - 1 and zahl(a, 'Wochenangebot') == n_std)
    bad = row(a, '10701').locator('input[data-f=vprice]'); bad.fill('abc'); bad.press('Tab'); a.wait_for_timeout(200)
    check('invalid offer price rejected', 'invalid' in bad.get_attribute('class') and 'nicht lesbar' in a.inner_text('#toast'))
    bad.fill(''); bad.press('Tab'); wait_saved(a)
    a.screenshot(path=SH + '/angebote-edeka.png')
    # Standard unverändert
    tab(a, 'Wochenangebot').click(); a.wait_for_timeout(200)
    check('standard price untouched', row(a, '10601').locator('input[data-f=price]').input_value() == de(P10601))
    # Veröffentlichen mit Einzel-Rücknahme
    a.click('#offen-liste'); a.wait_for_selector('#dlg-publish[open]')
    t = a.inner_text('#publish-body').lower()
    check('publish dialog lists offer prices', 'angebotspreise (2)' in t and 'edeka' in t, t[:300])
    a.click('#publish-body li:has-text("10823") [data-rv=variant]')
    a.wait_for_selector('#dlg-confirm[open]'); check('confirm names offer', 'Edeka' in a.inner_text('#dlg-confirm')); a.click('#dlg-confirm [data-v="1"]'); a.wait_for_timeout(300)
    check('revert removes hidden flag', 'angebotspreise (1)' in a.inner_text('#publish-body').lower())
    a.click('#dlg-publish [data-close]'); veroeffentlichen(a)
    # Auslieferung
    pub = br.new_page()
    pub.goto(B + '/'); pub.wait_for_selector('tr.row')
    r = get(pub, 'offer')
    raw = json.dumps(r[1])
    check('public offer: no customer prices at all', r[0] == 200 and '"variants"' not in raw and item(r[1]['offer'], '10601')['price']['value'] == P10601, item(r[1]['offer'], '10601')['price'])
    r = get(pub, 'offer&angebot=edeka'); check('customer offer needs login (401)', r[0] == 401, r[0])
    r = get(pub, 'offer&angebot=edeka&draft=1'); check('customer draft needs login', r[0] == 401, r[0])
    r = get(pub, 'offer&angebot=../x'); check('invalid offer id rejected', r[0] in (401, 404), r[0])
    pub.goto(B + '/?angebot=edeka'); pub.wait_for_timeout(1200)
    check('frontend without login: hint, no prices', 'nur nach Anmeldung' in pub.inner_text('body') and pub.locator('tr.row').count() == 0)
    r = get(a, 'offer&angebot=edeka')
    o = r[1]['offer'] if r[0] == 200 else {'items': [], 'meta': {}}
    check('customer offer resolved for logged-in user', r[0] == 200 and item(o, '10601')['price'] == {'status': 'value', 'value': 22} and o['meta'].get('offerName') == 'Wochenangebot Edeka' and '"variants"' not in json.dumps(o), item(o, '10601'))
    check('fallback: other items show standard price', item(o, '10823') and item(o, '10823')['price']['value'] == P10823)
    f = actx.new_page(); f.goto(B + '/?angebot=edeka'); f.wait_for_selector('tr.row')
    check('frontend shows offer name + own price', 'Wochenangebot Edeka' in f.inner_text('#topbar h1') and '22,00' in f.inner_text('tr.row >> nth=0'), f.inner_text('#topbar h1'))
    f.screenshot(path=SH + '/angebote-frontend.png')
    # Neues Angebot: eigene Artikelliste (Voreinstellung)
    a.click('[data-ob=manage]'); a.wait_for_selector('#view-angebote:not([hidden]) tr[data-oi]')
    check('Angebote verwalten führt zu Stammdaten → Angebote', a.get_attribute('#vt-angebote', 'aria-selected') == 'true')
    a.click('[data-ofa=add]'); a.locator('#view-angebote [data-of=name]').last.fill('Wochenangebot Metro')
    check('neues Angebot: Voreinstellung „Eigene Artikelliste“', a.locator('#view-angebote tr[data-oi]').last.locator('[data-of=fallback]').input_value() == 'hidden')
    a.click('[data-ofa=save]'); a.wait_for_selector('#toast.show:has-text("Angebote gespeichert")', timeout=8000)
    a.click('#vt-edit'); a.wait_for_selector('#view-edit:not([hidden]) #groups'); a.wait_for_selector('#offer-bar:not([hidden])', state='visible')
    check('new offer tab appears', tab(a, 'Metro').count() == 1)
    tab(a, 'Metro').click(); a.wait_for_selector('#groups .ed-empty')
    check('eigene Artikelliste: leer, Hinweis und „Artikel hinzufügen“', 'Noch keine Artikel in diesem Angebot' in a.inner_text('#groups') and zahl(a, 'Metro') == 0
          and 'Eigene Artikelliste' in a.inner_text('#offer-head'))
    a.screenshot(path=SH + '/angebote-leer.png')
    # Artikel hinzufügen (Fenster wie im Einzelangebot): Preis je Artikel, Gruppe automatisch
    a.click('#btn-add-art'); a.wait_for_selector('#dlg-ez-pick[open] #ezp-q')
    check('Fenster: Ziel-Angebot im Kopf, Preisspalte „Preis hier“', 'Metro' in a.inner_text('#ez-pick-body .ezp-head') and a.locator('#ezp-angebot').count() == 1)
    a.fill('#ezp-q', '10601'); a.wait_for_selector('#ezp-list tr[data-code="10601"]'); a.click('#ezp-list tr[data-code="10601"] .ezp-n')
    check('markierter Artikel: Preisfeld mit Wochenpreis vorbelegt, Zielgruppe im Fuß', a.input_value('#ezp-list [data-preis="10601"]') == de(P10601) and 'landet in:' in a.inner_text('#ezp-anz'), a.inner_text('#ezp-anz'))
    a.fill('#ezp-list [data-preis="10601"]', '19x'); a.click('#ezp-ok'); a.wait_for_selector('#ezp-anz .ezp-err')
    check('unlesbarer Preis: Fenster bleibt offen mit Hinweis', 'nicht lesbar' in a.inner_text('#ezp-anz') and a.locator('#dlg-ez-pick[open]').count() == 1)
    a.fill('#ezp-list [data-preis="10601"]', '19,5')
    a.screenshot(path=SH + '/angebote-hinzufuegen.png')
    a.click('#ezp-ok'); a.wait_for_selector('#dlg-ez-pick', state='hidden'); wait_saved(a)
    check('übernommen: nur dieser Artikel mit eigenem Preis', codes(a) == ['10601'] and row(a, '10601').locator('input[data-f=vprice]').input_value() == '19,50' and zahl(a, 'Metro') == 1, codes(a))
    check('andere Angebote unverändert', zahl(a, 'Wochenangebot') == n_std and zahl(a, 'Edeka') == n_std)
    a.click('#btn-add-art'); a.wait_for_selector('#dlg-ez-pick[open] #ezp-q'); a.fill('#ezp-q', '10601'); a.wait_for_selector('#ezp-list tr[data-code="10601"]')
    check('bereits enthaltener Artikel nicht erneut wählbar', a.is_disabled('#ezp-list [data-sel="10601"]') and 'schon enthalten' in a.inner_text('#ezp-list tr[data-code="10601"]'))
    # Freie Position nur in diesem Angebot
    a.click('#dlg-ez-pick [data-pick-extra="frei"]'); a.wait_for_selector('#dlg-ez-pick', state='hidden')
    a.wait_for_function("document.activeElement && document.activeElement.dataset.f === 'name'")
    a.keyboard.type('Metro-Spezial Testartikel'); a.keyboard.press('Tab')
    neu = a.locator('tr[data-id]:has(input[data-f=name][value="Metro-Spezial Testartikel"])')
    neu.locator('input[data-f=vprice]').fill('8,8'); neu.locator('input[data-f=vprice]').press('Tab'); wait_saved(a)
    check('freie Position im Angebot', zahl(a, 'Metro') == 2 and neu.locator('input[data-f=vprice]').input_value() == '8,80')
    check('… erscheint in keinem anderen Angebot', zahl(a, 'Wochenangebot') == n_std and zahl(a, 'Edeka') == n_std and zahl(a, 'Bela') == n_std)
    vi = neu.locator('input[data-f=vprice]'); vi.fill(''); vi.press('Tab'); a.wait_for_timeout(200)
    check('eigene Liste: leerer Preis wird nicht übernommen (Hinweis auf ✕)', vi.input_value() == '8,80' and '✕' in a.inner_text('#toast'))
    # ✕: Artikel, der nur hier steht, wird gelöscht; Rückgängig holt ihn zurück
    neu.locator('[data-act=remove]').click(); a.wait_for_selector('#toast.show:has-text("gelöscht")')
    check('✕ in eigener Liste: nur hier → gelöscht', zahl(a, 'Metro') == 1 and 'in keinem anderen Angebot' in a.inner_text('#toast'))
    a.click('#btn-undo'); a.wait_for_function("document.querySelectorAll('#groups tr[data-id]').length === 2"); wait_saved(a)
    check('Rückgängig stellt die Position wieder her', zahl(a, 'Metro') == 2)
    # Vorschau des gewählten Kundenangebots (Entwurf, noch nicht veröffentlicht) im Fenster; Angebot umschaltbar
    a.click('#btn-preview'); a.wait_for_selector('#dlg-vorschau[open] #pv-stage:not(.laden)', timeout=15000)
    fr = a.frame_locator('#pv-frame')
    fr.locator('#list').get_by_text('Metro-Spezial').first.wait_for(timeout=10000)
    mid = a.input_value('#pv-offer')
    check('Vorschau zeigt das gewählte Kundenangebot (Entwurf)', mid != 'std' and f'&angebot={mid}' in (a.get_attribute('#pv-frame', 'src') or '') and '19,50' in fr.locator('#list').inner_text(), mid)
    a.select_option('#pv-offer', 'std'); a.wait_for_selector('#pv-stage:not(.laden)')
    fr.locator('#list').get_by_text(de(P10601)).first.wait_for(timeout=10000)
    check('… umgeschaltet aufs Wochenangebot: ohne die Metro-Position', 'Metro-Spezial' not in fr.locator('#list').inner_text())
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-vorschau', state='hidden')
    # Umstellen „folgt dem Wochenangebot“ → eigene Artikelliste (Edeka hat einen eigenen Preis: 10601 = 22,00)
    tab(a, 'Edeka').click(); a.wait_for_selector('#offer-head [data-ob=umstellen]')
    a.click('#offer-head [data-ob=umstellen]'); a.wait_for_selector('#dlg-confirm[open]')
    t = a.inner_text('#dlg-confirm')
    check('Umstellung: Hinweis „sofort“ und Zahl der Artikel mit eigenem Preis', 'sofort' in t and '1 Artikel' in t, t)
    a.click('#dlg-confirm [data-v="1"]'); a.wait_for_selector('#toast.show:has-text("eigene Artikelliste")')
    check('Edeka: eigene Artikelliste mit dem einen eigenen Artikel', codes(a) == ['10601'] and zahl(a, 'Edeka') == 1 and 'Eigene Artikelliste' in a.inner_text('#offer-head')
          and next(o for o in get(a, 'offers')[1]['offers'] if o['id'] == 'edeka')['fallback'] == 'hidden', codes(a))
    r = get(a, 'offer&angebot=edeka')
    check('… Kunden sehen sofort nur noch diesen Artikel', r[0] == 200 and [i['code'] for i in r[1]['offer']['items']] == ['10601'], [i['code'] for i in r[1]['offer']['items']][:5] if r[0] == 200 else r)
    # Aus anderem Angebot übernehmen: Wochenangebot −5 % in die eigene Liste
    a.click('#offer-head [data-ob=copy]'); a.wait_for_selector('#dlg-offer-copy[open]')
    a.select_option('#offer-copy-body [name=src]', 'std'); a.fill('#offer-copy-body [name=pct]', '-5'); a.click('#offer-copy-body [type=submit]'); wait_saved(a)
    exp = round(round(P10823 * 0.95 / 0.05) * 0.05, 2)
    check('Übernahme füllt die eigene Liste, eigener Preis bleibt', zahl(a, 'Edeka') > 100 and row(a, '10601').locator('input[data-f=vprice]').input_value() == '22,00'
          and row(a, '10823').locator('input[data-f=vprice]').input_value() == de(exp), (zahl(a, 'Edeka'), de(exp)))
    check('… Wochenangebot und Metro unverändert', zahl(a, 'Wochenangebot') == n_std and zahl(a, 'Metro') == 2)
    a.click('#btn-undo'); a.wait_for_function("document.querySelectorAll('#groups tr[data-id]').length === 1"); wait_saved(a)
    check('Übernahme mit Rückgängig zurückgenommen', zahl(a, 'Edeka') == 1)
    # Server: Gruppe mit VK-Gruppe bleibt im Entwurf, geht nie an Kunden; neue Angebote ohne Regel = eigene Liste
    d = get(a, 'draft')[1]; mdl = d['draft']
    mdl['groups'][0]['vk'] = '1600'; mdl['groups'][1]['vk'] = '<b>'
    r = post(a, 'save_draft', {'model': mdl, 'revision': d['revision']})
    d2 = get(a, 'draft')[1]['draft']
    check('Gruppe: VK-Gruppe gespeichert, ungültige verworfen', r[0] == 200 and d2['groups'][0].get('vk') == '1600' and 'vk' not in d2['groups'][1], d2['groups'][:2])
    r = get(a, 'offer&angebot=edeka&draft=1')
    check('… nicht in der Auslieferung (Vorschau Kundenangebot)', r[0] == 200 and '"vk"' not in json.dumps(r[1]), r[0])
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) #offer-bar:not([hidden])'); wait_saved(a)
    r = get(a, 'angebot_artikel')
    check('Artikel für „Artikel hinzufügen“: Stammdaten/Wochenangebot, ohne Einkaufspreise', r[0] == 200 and any(x['code'] == '10601' for x in r[1]['articles']) and r[1].get('ek') is False, r[0])
    # Preise übernehmen in Bela (+10 %, auf 0,05)
    tab(a, 'Bela').click(); a.click('[data-ob=copy]'); a.wait_for_selector('#dlg-offer-copy[open]')
    a.fill('#offer-copy-body [name=pct]', '10'); a.click('#offer-copy-body [type=submit]'); wait_saved(a)
    exp = round(round(P10823 * 1.1 / 0.05) * 0.05, 2)
    check('copy with surcharge + rounding', row(a, '10823').locator('input[data-f=vprice]').input_value() == de(exp), (row(a, '10823').locator('input[data-f=vprice]').input_value(), de(exp)))
    check('copy toast', 'übernommen' in a.inner_text('#toast'), a.inner_text('#toast'))
    a.click('#btn-undo'); a.wait_for_timeout(300)
    check('copy undoable', row(a, '10823').locator('input[data-f=vprice]').input_value() == '')
    veroeffentlichen(a)
    ids = {x['id']: x['name'] for x in get(a, 'offers')[1]['offers']}
    metro = next(k for k, v in ids.items() if 'Metro' in v)
    r = get(a, f'offer&angebot={metro}')
    mo = r[1]['offer']['items'] if r[0] == 200 else []
    check('eigene Artikelliste: nur ihre Artikel ausgeliefert', sorted(i['code'] or '' for i in mo) == ['', '10601'] and any(i['name'].startswith('Metro-Spezial') for i in mo)
          and next(i for i in mo if i['code'] == '10601')['price'] == {'status': 'value', 'value': 19.5}, [(i['code'], i['name']) for i in mo] or r)
    pubo = get(a, 'offer')[1]['offer']
    check('… freie Position nicht im Wochenangebot', not any(i['name'].startswith('Metro-Spezial') for i in pubo['items']))
    r = get(a, 'offer&angebot=bela')
    check('… nicht in Angeboten, die dem Wochenangebot folgen', r[0] == 200 and not any(i['name'].startswith('Metro-Spezial') for i in r[1]['offer']['items']))
    # Vorwoche je Angebot
    tab(a, 'Edeka').click(); a.fill('#m-week', str(int(a.input_value('#m-week')) + 1)); a.press('#m-week', 'Tab'); a.wait_for_timeout(1500)
    pc = row(a, '10601').locator('td.e-prev').inner_text().strip()
    check('Vorwoche shows previous offer price', pc.startswith('22,00'), pc)
    a.fill('#m-week', str(int(a.input_value('#m-week')) - 1)); a.press('#m-week', 'Tab'); wait_saved(a)
    # Werbung schalten: Wochenangebot über das Fenster (Reihenfolge, Hinweis), weitere Angebote über den Server (Prüfung)
    tab(a, 'Wochenangebot').click(); a.wait_for_selector('#btn-werbung')
    check('Werbung: Knopf in der Werkzeugleiste, noch ohne Zahl', a.locator('#btn-werbung').is_visible() and a.locator('#werb-n').is_hidden() and a.locator('#btn-add-group').count() == 0)
    a.click('#btn-werbung'); a.wait_for_selector('#dlg-werbung[open] #wb-auswahl')
    check('Fenster: Überschrift vorbelegt, noch keine Artikel', a.input_value('#wb-titel') == 'Unsere Empfehlung der Woche' and a.locator('#wb-liste [data-wid]').count() == 0)
    a.fill('#wb-titel', 'Aktion der Woche'); a.fill('#wb-text', 'Nur solange der Vorrat reicht.')
    id01, id23 = row(a, '10601').get_attribute('data-id'), row(a, '10823').get_attribute('data-id')
    # Artikelauswahl (gemeinsames Fenster): Filter „nur in diesem Angebot“ nicht vorausgewählt (Inhaber 05.11.2026),
    # Bestand ohne Filter, alle Gruppen
    a.click('#wb-auswahl'); a.wait_for_selector('#dlg-ez-pick[open] #ezp-list tr[data-code="10601"]')
    alle_n = a.locator('#ezp-list tr.ezp-z').count()
    check('Artikelauswahl für die Werbung: „nur in …“ nicht vorausgewählt, ohne Bestandsfilter, alle Gruppen', 'Werbung' in a.inner_text('#ez-pick-body .ezp-head')
          and not a.is_checked('#ezp-angebot') and 'Wochenangebot' in a.inner_text('label:has(#ezp-angebot)') and (a.locator('#ezp-bestand').count() == 0 or not a.is_checked('#ezp-bestand'))
          and alle_n > 100, alle_n)
    a.check('#ezp-angebot'); a.wait_for_selector('#ezp-list tr.ezp-z')   # Filter wirkt sofort (hier ohne Bestand: gleiche Artikel)
    check('… Filter von Hand: nur Artikel dieses Angebots', all(c in set(codes(a)) or c.startswith('~') for c in a.locator('#ezp-list tr.ezp-z').evaluate_all('e => e.map(x => x.dataset.code)')),
          a.locator('#ezp-list tr.ezp-z').count())
    for c in ('10823', '10601'):
        a.fill('#ezp-q', c); a.wait_for_selector(f'#ezp-list tr[data-code="{c}"]'); a.click(f'#ezp-list tr[data-code="{c}"] .ezp-n')
    check('… Preis im Angebot fest angezeigt (kein Eingabefeld)', a.locator('#ezp-list tr[data-code="10601"] [data-preis]').count() == 0 and de(P10601) in a.inner_text('#ezp-list tr[data-code="10601"] .ezp-pr'))
    a.screenshot(path=SH + '/werbung-auswahl.png')
    a.click('#ezp-ok'); a.wait_for_selector('#dlg-ez-pick', state='hidden')
    wl = a.locator('#wb-liste [data-wid]').evaluate_all('e => e.map(x => x.dataset.wid)')
    check('… übernommen in die Werbung', wl == [id01, id23] and '2 von 12' in a.inner_text('#wb-n') and a.locator('#dlg-werbung[open]').count() == 1, wl)
    a.click('#wb-auswahl'); a.wait_for_selector('#dlg-ez-pick[open] #ezp-list tr.ezp-z')
    check('erneut geöffnet: beworbene Artikel vorausgewählt', a.is_checked('#ezp-list [data-sel="10601"]') and a.is_checked('#ezp-list [data-sel="10823"]') and '2 Artikel' in a.inner_text('#ezp-anz'))
    a.keyboard.press('Escape'); a.wait_for_selector('#dlg-ez-pick', state='hidden')
    a.click(f'#wb-liste [data-wid="{id23}"] [data-wm=up]')
    check('Reihenfolge änderbar', a.locator('#wb-liste [data-wid]').evaluate_all('e => e.map(x => x.dataset.wid)') == [id23, id01])
    a.click(f'#wb-liste [data-wid="{id01}"] [data-wm=up]'); a.fill(f'#wb-liste [data-wt="{id01}"]', 'Top-Preis')
    a.screenshot(path=SH + '/werbung-fenster.png')
    a.click('#dlg-werbung [data-wa=ok]'); a.wait_for_selector('#dlg-werbung', state='hidden'); wait_saved(a)
    check('übernommen: Zahl am Knopf, beworbene Zeilen gekennzeichnet', a.inner_text('#werb-n') == '2' and 'e-werb' in (row(a, '10601').get_attribute('class') or '').split()
          and row(a, '10601').locator('.werbtag').count() == 1 and row(a, '10701').locator('.werbtag').count() == 0)
    check('Knopf „Veröffentlichen“ nennt die Werbung', 'Werbung geändert' in (a.get_attribute('#offen-zahl, #offen-liste', 'title') or ''), a.get_attribute('#offen-zahl, #offen-liste', 'title'))
    a.screenshot(path=SH + '/werbung-editor.png')
    tab(a, 'Edeka').click(); a.wait_for_selector('#offer-head:has-text("Edeka")')
    a.click('#btn-werbung'); a.click('#wb-auswahl'); a.wait_for_selector('#dlg-ez-pick[open] #ezp-list tr[data-code="10601"]')
    check('Edeka (eigene Liste): „nur in „Edeka““ nicht vorausgewählt, Auswahl zeigt auch Artikel außerhalb', not a.is_checked('#ezp-angebot') and a.locator('#ezp-list tr.ezp-z').count() > 1, a.locator('#ezp-list tr.ezp-z').count())
    a.check('#ezp-angebot'); a.wait_for_function("document.querySelectorAll('#ezp-list tr.ezp-z').length === 1")
    check('… Filter von Hand: nur der eine Artikel des Angebots', a.locator('#ezp-list tr.ezp-z').count() == 1)
    a.uncheck('#ezp-angebot'); a.fill('#ezp-q', '10823'); a.wait_for_selector('#ezp-list tr[data-code="10823"]'); a.click('#ezp-list tr[data-code="10823"] .ezp-n')
    check('… Filter aus: Artikel außerhalb des Angebots mit Preisfeld (Wochenpreis vorgeschlagen)', a.input_value('#ezp-list [data-preis="10823"]') == de(P10823))
    a.click('#ezp-ok'); a.wait_for_selector('#dlg-ez-pick', state='hidden'); a.wait_for_selector('#toast.show:has-text("aufgenommen")')
    check('… ins Angebot aufgenommen und in der Werbung', zahl(a, 'Edeka') == 2 and a.locator('#wb-liste [data-wid]').count() == 1 and row(a, '10823').locator('input[data-f=vprice]').input_value() == de(P10823))
    a.click('#dlg-werbung [data-wa=ok]'); a.wait_for_selector('#dlg-werbung', state='hidden'); wait_saved(a)
    check('… Edeka-Werbung mit dem Artikel', a.inner_text('#werb-n') == '1')
    a.click('#btn-undo'); a.wait_for_function("document.querySelector('#werb-n').hidden"); a.click('#btn-undo')
    a.wait_for_function("document.querySelectorAll('#groups tr[data-id]').length === 1"); wait_saved(a)
    check('Rückgängig: Werbung und Aufnahme zurückgenommen', zahl(a, 'Edeka') == 1 and a.locator('#werb-n').is_hidden())
    tab(a, 'Wochenangebot').click(); a.wait_for_selector('#werb-n:not([hidden])')
    d = get(a, 'draft')[1]; mdl = d['draft']
    w = mdl['meta'].get('werbung', {}).get('std', {})
    check('Entwurf: meta.werbung je Angebot mit Reihenfolge, Hinweis und Text', w.get('titel') == 'Aktion der Woche' and [x['id'] for x in w.get('artikel', [])] == [id01, id23]
          and w['artikel'][0].get('text') == 'Top-Preis' and w.get('text') == 'Nur solange der Vorrat reicht.', w)
    nur_metro = next(i['id'] for i in mdl['items'] if i['name'].startswith('Metro-Spezial'))
    bela_ids = [i['id'] for i in mdl['items'] if not (i.get('variants', {}).get('bela', {}).get('status') == 'hidden')][:15]
    mdl['meta']['werbung']['std']['artikel'].append({'id': nur_metro})   # nur in Metro – nie im Wochenangebot ausliefern
    mdl['meta']['werbung']['edeka'] = {'titel': 'E' * 100, 'text': 'x' * 300, 'artikel': [{'id': id01, 'text': 'y' * 60}, {'id': id23}, {'id': 'gibt-es-nicht'}, {'id': id01}]}
    mdl['meta']['werbung']['bela'] = {'titel': 'Bela-Aktion', 'artikel': [{'id': x} for x in bela_ids]}
    mdl['meta']['werbung']['unbekannt-xyz'] = {'titel': 'Werbung-XYZ-unbekannt', 'artikel': [{'id': id01}]}
    r = post(a, 'save_draft', {'model': mdl, 'revision': d['revision']})
    w2 = (get(a, 'draft')[1]['draft']['meta'] or {}).get('werbung', {})
    check('Server prüft die Werbung: Längen, unbekannte/doppelte Artikel, unbekannte Angebote, höchstens 12', r[0] == 200 and 'unbekannt-xyz' not in w2
          and len(w2['edeka']['titel']) == 80 and len(w2['edeka']['text']) == 240 and [x['id'] for x in w2['edeka']['artikel']] == [id01, id23]
          and len(w2['edeka']['artikel'][0]['text']) == 40 and len(w2['bela']['artikel']) == 12, (r[0], sorted(w2)))
    vo = get(a, 'offer&draft=1')[1]['offer']; ve = get(a, 'offer&angebot=edeka&draft=1')[1]['offer']
    check('Auslieferung (Vorschau): nur der eigene Eintrag, nur ausgelieferte Artikel', [x['id'] for x in vo['meta'].get('werbung', {}).get('artikel', [])] == [id01, id23]
          and nur_metro not in json.dumps(vo) and 'Bela-Aktion' not in json.dumps(vo) and 'Werbung-XYZ' not in json.dumps(vo)
          and [x['id'] for x in ve['meta'].get('werbung', {}).get('artikel', [])] == [id01] and 'Aktion der Woche' not in json.dumps(ve), (vo['meta'].get('werbung'), ve['meta'].get('werbung')))
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) #offer-bar:not([hidden])'); a.wait_for_selector('#groups tr[data-id]'); wait_saved(a)
    a.click('#offen-liste'); a.wait_for_selector('#dlg-publish[open]')
    t = a.inner_text('#publish-body').lower()
    check('Veröffentlichen-Dialog: Werbung je Angebot', 'werbung (3)' in t and 'aktion der woche' in t and 'bela-aktion' in t, t[:400])
    a.click('#publish-body li:has-text("Bela-Aktion") [data-rv=werbung]'); a.wait_for_selector('#dlg-confirm[open]')
    check('Rücknahme nennt das Angebot', 'Bela' in a.inner_text('#dlg-confirm')); a.click('#dlg-confirm [data-v="1"]')
    a.wait_for_function("document.querySelector('#publish-body').textContent.toLowerCase().includes('werbung (2)')")
    a.click('#dlg-publish [data-close]'); veroeffentlichen(a)
    po = get(pub, 'offer')[1]['offer']
    pw = po['meta'].get('werbung', {})
    check('öffentlich: nur die eigene Werbung, nur ausgelieferte Artikel', pw.get('titel') == 'Aktion der Woche' and [x['id'] for x in pw.get('artikel', [])] == [id01, id23]
          and nur_metro not in json.dumps(po) and 'EEEE' not in json.dumps(po) and 'Bela-Aktion' not in json.dumps(po), pw)
    eo = get(a, 'offer&angebot=edeka')[1]['offer']
    check('Kundenangebot: eigene Werbung, nur Artikel dieses Angebots', eo['meta'].get('werbung', {}).get('titel', '').startswith('EEE')
          and [x['id'] for x in eo['meta']['werbung']['artikel']] == [id01] and 'Aktion der Woche' not in json.dumps(eo), eo['meta'].get('werbung'))
    bo = get(a, 'offer&angebot=bela')[1]['offer']
    check('Angebot ohne eigene Werbung (folgt dem Wochenangebot): keine Werbung, Rücknahme wirkt', 'werbung' not in bo['meta'], bo['meta'].get('werbung'))
    pub.goto(B + '/'); pub.wait_for_selector('#list .werb-sec tr.row')
    wz = pub.locator('#list .werb-sec tr.row')
    check('Angebotsseite: Abschnitt oben wie die Liste – Überschrift, Text, Zeilen in Reihenfolge', pub.inner_text('.werb-st h3') == 'Aktion der Woche' and 'Vorrat' in pub.inner_text('.werb-st')
          and wz.count() == 2 and wz.first.get_attribute('data-id') == id01 and 'Top-Preis' in wz.first.inner_text() and de(P10601) in wz.first.inner_text()
          and wz.nth(1).locator('.werb-tag').count() == 0, pub.inner_text('.werb-sec')[:200].replace('\n', ' '))
    check('… vor den übrigen Abschnitten, Band in der Akzentfarbe (nicht gelb)', pub.evaluate("document.querySelector('#list .al-sec').classList.contains('werb-sec')")
          and pub.evaluate("getComputedStyle(document.querySelector('.werb-st')).backgroundColor") == pub.evaluate("getComputedStyle(document.querySelector('.tag.werb-tag')).backgroundColor"))
    check('… beworbene Zeilen der Liste gekennzeichnet', pub.locator('#list .al-sec:not(.werb-sec) tr.row.werb-an').count() == 2 and pub.locator('#list .al-sec:not(.werb-sec) tr.row.werb-an .tag.werb-tag').count() == 2)
    pub.screenshot(path=SH + '/werbung-angebotsseite.png')
    wz.nth(1).locator('.name-btn').click(); pub.wait_for_selector('#dlg-detail[open]')
    check('Bezeichnung im Abschnitt öffnet die Details wie in der Liste', 'Steakhüfte' in pub.inner_text('#dlg-detail') or '10823' in pub.inner_text('#dlg-detail'))
    pub.keyboard.press('Escape'); pub.wait_for_selector('#dlg-detail', state='hidden')
    pub.fill('#q', '10701'); pub.wait_for_function("!document.querySelector('#list .werb-sec')")
    check('Suche: Abschnitt ausgeblendet', pub.locator('#list .werb-sec').count() == 0)
    pm = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True); pm.on('pageerror', lambda x: errs.append('pm: ' + str(x)))
    pm.goto(B + '/'); pm.wait_for_selector('#list .werb-sec tr.row')
    sw = pm.evaluate('document.documentElement.scrollWidth'); check('Angebotsseite mobil: Block ohne seitliches Scrollen', sw <= 390, sw)
    pm.screenshot(path=SH + '/werbung-angebotsseite-mobil.png'); pm.close()
    check('kein Excel-Import mehr im Editor (Auftrag des Inhabers 04.11.2026)', a.locator('#btn-import').count() == 0)
    # Zweite Werbung (Wunsch des Inhabers): „Weitere Werbung“ im Fenster, Reiter, Prüfung, Auslieferung, rechts daneben
    tab(a, 'Wochenangebot').click(); a.wait_for_selector('#werb-n:not([hidden])')
    id701 = row(a, '10701').get_attribute('data-id')
    a.click('#btn-werbung'); a.wait_for_selector('#dlg-werbung[open] [data-wa=neu]')
    check('Fenster: Knopf „Weitere Werbung“ (rechts daneben), noch keine Reiter', a.locator('#wb-reiter .wb-tab').count() == 0 and 'rechts daneben' in a.inner_text('#wb-reiter'))
    a.click('[data-wa=neu]'); a.wait_for_selector('#wb-reiter .wb-tab[aria-selected="true"][data-wr="1"]')
    check('… zweiter Reiter aktiv, Überschrift vorbelegt, leer, kein weiterer Knopf', a.input_value('#wb-titel') == 'Aktion der Woche' and a.locator('#wb-liste [data-wid]').count() == 0
          and a.locator('[data-wa=neu]').count() == 0 and 'Werbung 2 entfernen' in a.inner_text('#wb-ende'))
    a.click('#dlg-werbung [data-wa=ok]')
    check('leere zweite Werbung: Hinweis statt Übernehmen', 'Werbung 2 hat noch keine Artikel' in a.inner_text('#wb-err') and a.locator('#dlg-werbung[open]').count() == 1)
    a.fill('#wb-titel', 'Zweite Aktion')
    a.click('#wb-auswahl'); a.wait_for_selector('#dlg-ez-pick[open] #ezp-q'); a.fill('#ezp-q', '10701'); a.wait_for_selector('#ezp-list tr[data-code="10701"]')
    a.click('#ezp-list tr[data-code="10701"] .ezp-n'); a.click('#ezp-ok'); a.wait_for_selector('#dlg-ez-pick', state='hidden')
    a.click('#wb-reiter [data-wr="0"]'); a.wait_for_selector('#wb-reiter [data-wr="0"][aria-selected="true"]')
    check('Reiter wechseln: erste Werbung unverändert', a.input_value('#wb-titel') == 'Aktion der Woche' and a.locator('#wb-liste [data-wid]').count() == 2
          and a.inner_text('#wb-reiter [data-wr="1"] .wb-tz') == '1')
    a.screenshot(path=SH + '/werbung-zwei.png')
    a.click('#dlg-werbung [data-wa=ok]'); a.wait_for_selector('#dlg-werbung', state='hidden'); wait_saved(a)
    w = (get(a, 'draft')[1]['draft']['meta'] or {}).get('werbung', {}).get('std', {})
    check('Entwurf: zweite Werbung in „weitere“', [x['id'] for x in w.get('artikel', [])] == [id01, id23] and w.get('weitere') == [{'titel': 'Zweite Aktion', 'artikel': [{'id': id701}]}]
          and a.inner_text('#werb-n') == '3 · 2×', (w, a.inner_text('#werb-n')))
    # Server: höchstens zwei Werbungen; leere erste rückt nach; Auslieferung nur ausgelieferter Artikel
    d = get(a, 'draft')[1]; mdl = d['draft']
    mdl['meta']['werbung']['edeka'] = {'titel': 'Leer', 'artikel': [{'id': 'gibt-es-nicht'}], 'weitere': [{'titel': 'Edeka 2', 'artikel': [{'id': id01}]}, {'titel': 'Edeka 3', 'artikel': [{'id': id01}]}]}
    mdl['meta']['werbung']['std']['weitere'].append({'titel': 'Dritte', 'artikel': [{'id': id01}]})
    r = post(a, 'save_draft', {'model': mdl, 'revision': d['revision']})
    w2 = (get(a, 'draft')[1]['draft']['meta'] or {}).get('werbung', {})
    check('Server: höchstens zwei Werbungen je Angebot, leere fallen weg (die nächste rückt nach)', r[0] == 200 and len(w2['std'].get('weitere', [])) == 1 and w2['std']['weitere'][0]['titel'] == 'Zweite Aktion'
          and w2['edeka'].get('titel') == 'Edeka 2' and [x['titel'] for x in w2['edeka'].get('weitere', [])] == ['Edeka 3'], (r[0], w2.get('std', {}).get('weitere'), w2.get('edeka')))
    vo = get(a, 'offer&draft=1')[1]['offer']['meta'].get('werbung', {})
    check('Auslieferung (Vorschau): zweite Werbung in „weitere“', [x['id'] for x in (vo.get('weitere') or [{}])[0].get('artikel', [])] == [id701] and 'Edeka 2' not in json.dumps(vo), vo)
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) #offer-bar:not([hidden])'); a.wait_for_selector('#groups tr[data-id]'); wait_saved(a)
    a.click('#offen-liste'); a.wait_for_selector('#dlg-publish[open]')
    check('Veröffentlichen-Dialog nennt beide Werbungen', 'Zweite Aktion' in a.inner_text('#publish-body'))
    a.click('#dlg-publish [data-close]'); veroeffentlichen(a)
    pub.goto(B + '/'); pub.wait_for_selector('#list .werb-duo .werb-sec tr.row')
    bx = pub.evaluate("[...document.querySelectorAll('#list .werb-duo > .werb-sec')].map((e) => { const r = e.getBoundingClientRect(); return [r.left, r.top, r.width, e.querySelector('h3').textContent]; })")
    check('Angebotsseite: zweite Werbung rechts neben der ersten', len(bx) == 2 and bx[1][0] > bx[0][0] + bx[0][2] - 1 and abs(bx[0][1] - bx[1][1]) < 2 and bx[1][3] == 'Zweite Aktion'
          and pub.locator('#list .werb-duo .werb-sec').nth(1).locator('tr.row').get_attribute('data-id') == id701, bx)
    check('… Artikel der zweiten Werbung in der Liste hervorgehoben', pub.locator(f'#list .al-sec:not(.werb-sec) tr.row.werb-an[data-id="{id701}"]').count() == 1)
    pub.screenshot(path=SH + '/werbung-zwei-angebotsseite.png')
    pm = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True); pm.on('pageerror', lambda x: errs.append('pm: ' + str(x)))
    pm.goto(B + '/'); pm.wait_for_selector('#list .werb-duo .werb-sec tr.row')
    bm = pm.evaluate("[...document.querySelectorAll('#list .werb-duo > .werb-sec')].map((e) => e.getBoundingClientRect().top)")
    sw = pm.evaluate('document.documentElement.scrollWidth')
    check('Angebotsseite mobil: zwei Werbungen untereinander, ohne seitliches Scrollen', len(bm) == 2 and bm[1] > bm[0] and sw <= 390, (bm, sw))
    pm.screenshot(path=SH + '/werbung-zwei-mobil.png'); pm.close()
    # Rechte
    post(a, 'user_save', {'name': 'Eddi', 'username': 'eddi', 'role': 'editor', 'active': True, 'password': 'Bearbeiter-Zugang-1', 'mustChange': False})
    post(a, 'user_save', {'name': 'Vera', 'username': 'vera', 'role': 'viewer', 'active': True, 'password': 'Leserin-Zugang-1', 'mustChange': False})
    e = br.new_page(viewport={'width': 1440, 'height': 950}); login(e, 'eddi', 'Bearbeiter-Zugang-1')
    cur = get(e, 'offers')[1]
    r = post(e, 'offers_save', {'rev': cur['rev'], 'offers': [o for o in cur['offers'] if o['id'] != metro]})
    check('editor cannot delete offers (403)', r[0] == 403, r)
    r = post(e, 'offers_save', {'rev': cur['rev'], 'offers': cur['offers'] + [{'id': 'test', 'name': 'Wochenangebot', 'fallback': 'standard'}]})
    check('duplicate/reserved name rejected', r[0] == 422, r)
    r = post(e, 'offers_save', {'rev': cur['rev'] - 1, 'offers': cur['offers']})
    check('stale revision rejected (409)', r[0] == 409, r[0])
    v = br.new_page(viewport={'width': 1440, 'height': 950}); login(v, 'vera', 'Leserin-Zugang-1')
    tv = v.locator('#offer-bar [data-offer]:has-text("Edeka")').first; tv.click(); v.wait_for_timeout(200)
    check('viewer: can switch, inputs locked, no manage', v.locator('tr[data-id] input[data-f=vprice]').first.is_disabled() and v.locator('[data-ob=manage]').count() == 0)
    check('viewer: kein „Artikel hinzufügen“, keine Artikelauswahl (403)', not v.locator('#btn-add-art').is_visible() and get(v, 'angebot_artikel')[0] == 403
          and not v.locator('tr[data-id] [data-act=remove]').first.is_visible())
    check('editor: Artikelauswahl erlaubt', get(e, 'angebot_artikel')[0] == 200)
    v.locator('#offer-bar [data-offer="std"]').click(); v.click('#btn-werbung'); v.wait_for_selector('#dlg-werbung[open]')
    check('viewer: Werbung nur ansehen (Felder gesperrt, kein Übernehmen)', v.is_disabled('#wb-titel') and v.locator('#dlg-werbung [data-wa]').count() == 0 and v.locator('#wb-liste [data-wid]').count() == 2)
    v.keyboard.press('Escape')
    # Admin löscht Angebot
    a.click('[data-ob=manage]'); a.wait_for_selector('#view-angebote:not([hidden]) tr[data-oi]')
    a.locator('#view-angebote tr[data-oi]:has(input[value*="Metro"]) [data-ofa=del]').click(); a.click('#dlg-confirm [data-v="1"]')
    a.click('[data-ofa=save]'); bestaetigt(a, 'Angebote gespeichert')
    a.click('#vt-edit'); a.wait_for_selector('#view-edit:not([hidden]) tr[data-id]')
    check('admin deletes offer: tab gone', tab(a, 'Metro').count() == 0)
    r = get(a, f'offer&angebot={metro}'); check('deleted offer not deliverable (404)', r[0] == 404, r[0])
    # Gleichnamiges Angebot neu anlegen: die alte ID (mit Kundenpreis 19,50 im veröffentlichten Angebot) wird nie wiederverwendet
    cur = get(a, 'offers')[1]
    r = post(a, 'offers_save', {'rev': cur['rev'], 'offers': cur['offers'] + [{'id': metro, 'name': 'Wochenangebot Metro', 'fallback': 'hidden'}]})
    neu = next((o for o in (r[1] or {}).get('offers', []) if o['name'] == 'Wochenangebot Metro'), {})
    check('neues Angebot mit Namen eines gelöschten: neue ID statt der alten', r[0] == 200 and neu.get('id') not in (None, metro) and neu['id'].startswith(metro + '-'), (r[0], neu))
    r = get(a, f"offer&angebot={neu.get('id')}")
    check('… keine alten Kundenpreise (Regel „ausblenden“: keine Artikel)', r[0] == 200 and r[1]['offer']['items'] == [], r[1]['offer']['items'][:2] if r[0] == 200 else r)
    check('… alte ID bleibt unbekannt (404)', get(a, f'offer&angebot={metro}')[0] == 404)
    cur = get(a, 'offers')[1]
    doc = json.loads(storage_raw('angebote')[storage_raw('angebote').index('{'):])
    check('… gelöschte ID vermerkt (geloescht)', metro in doc.get('geloescht', []), doc.get('geloescht'))
    # Speichern ohne „fallback“ (älterer Client): Einstellung bleibt; Felder einer neueren Fassung bleiben erhalten
    doc['zukunft'] = {'x': 1}
    for o in doc['offers']:
        if o['id'] == neu.get('id'): o['zukunftsfeld'] = 'bleibt'
    storage_write('angebote', doc)
    cur = get(a, 'offers')[1]
    r = post(a, 'offers_save', {'rev': cur['rev'], 'offers': [{'id': o['id'], 'name': o['name']} for o in cur['offers']]})
    nach = {o['id']: o for o in (r[1] or {}).get('offers', [])}
    check('ohne „fallback“: bisherige Einstellung bleibt (ausblenden)', r[0] == 200 and nach.get(neu.get('id'), {}).get('fallback') == 'hidden', r)
    doc = json.loads(storage_raw('angebote')[storage_raw('angebote').index('{'):])
    check('unbekannte Felder (Angebot und Dokument) bleiben erhalten', doc.get('zukunft') == {'x': 1} and next(o for o in doc['offers'] if o['id'] == neu.get('id')).get('zukunftsfeld') == 'bleibt' and metro in doc.get('geloescht', []), doc)
    cur = get(a, 'offers')[1]
    r = post_bestaetigt(a, 'offers_save', {'rev': cur['rev'], 'offers': [o for o in cur['offers'] if o['id'] != neu.get('id')]})
    check('… wieder gelöscht', r[0] == 200, r)
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    # Protokoll
    log = json.dumps(get(a, 'log')[1], ensure_ascii=False)
    check('audit: offers + offer prices logged', 'Angebote geändert' in log and 'Preis Wochenangebot Edeka' in log)
    check('audit: Werbung je Angebot protokolliert', 'Werbung Wochenangebot' in log and 'Aktion der Woche' in log)
    # Zwei Veröffentlichungen direkt nacheinander: verschiedene, steigende Stände (Bestellwünsche prüfen gegen genau diesen)
    d = get(a, 'draft')[1]
    mdl = d['draft'] or d['published']
    r1 = post(a, 'publish', {'revision': d['revision'], 'model': mdl})
    r2 = post(a, 'publish', {'revision': r1[1].get('revision') if r1[1] else None, 'model': mdl})
    p1, p2 = (r1[1] or {}).get('publishedAt', ''), (r2[1] or {}).get('publishedAt', '')
    check('zweimal in derselben Sekunde veröffentlicht: verschiedene, steigende Stände', r1[0] == 200 and r2[0] == 200 and p1 and p2 and p2 > p1 and p1[:19] <= p2[:19], (r1[0], r2[0], p1, p2))
    a.reload(); a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    kopieren_pruefen(a, br, v)
    # Mobil
    m = br.new_page(viewport={'width': 390, 'height': 844}, is_mobile=True); m.on('pageerror', lambda x: errs.append('m: ' + str(x)))
    login(m, 'admin', 'Sicheres-Passwort-1'); m.wait_for_timeout(300)
    sw = m.evaluate('document.documentElement.scrollWidth'); check('mobile no h-scroll', sw <= 390, sw)
    shot(m.locator('#offer-bar'), SH + '/angebote-mobil.png')
    check('no JS errors', not errs, errs)
    br.close()
print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
