"""Rollen und Rechte: eigene Rollen (anlegen, umbenennen, kopieren, löschen), Modulzugang „<modul>.zugang“ je Rolle,
mehrere Rollen je Mitarbeiter, Standardrollen unverändert, Durchsetzung auf dem Server (GR-103), Protokoll und die
Oberfläche (Verwaltung → Rollen und Rechte, Mitarbeiterdialog, Dashboard ohne Kacheln ohne Zugang).
CRM-Rechte „Master-Cockpit“ (ohne Standard) und „Umsätze in €“/„Mengen in kg“ (Standard an, auch in eigenen und älteren
gespeicherten Rollen, einzeln abschaltbar, ohne CRM-Zugang zu geben) und das Feld „Vertreter im CRM“ am Mitarbeiter
(nur vorhandene Vertreter, Rückfall/ältere Oberfläche, Protokoll, Mitarbeiterdialog).
Neues Design (02.11.2026): Stufen je Modul (Kein · Ansehen · Bearbeiten · Voll, „Angepasst“), sensible Rechte einzeln,
Vorschau-Bilder (Beispieldaten), „Auf einen Blick“, Rollen vergleichen mit „Was darf …?“, 390 px mit aufklappbaren Modulen.

Testdaten: Vertreter 11 Vera Vertrieb, 12 Tom Tour (Stammdaten → Vertreter); nur synthetische Daten.

Der Testserver hat keinen eigenen Host (kein WA_OBERFLAECHE): gesperrt wird nach der Oberfläche der Aktion – HR-Aktionen
(hr.intern) brauchen „hr.zugang“, der gemeinsame Eingabebereich (angebot.eingabe) regelt die Sichtbarkeit über die
Einzelrechte. Die Sperre je Host prüft die Gruppe „rollen_host“ (WA_OBERFLAECHE=bestand.intern).
"""
import json
import sys
from playwright.sync_api import sync_playwright
from kunden_hilfe import Client, B
from umgebung import SH, storage_raw, storage_write

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)) if i else ''))


def dokument(name):
    raw = storage_raw(name)
    if not raw:
        return None
    if raw.startswith('<?php'):
        raw = raw.split('\n', 1)[1]
    return json.loads(raw)


A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
for name, user, role, pw in [('Lars Lager', 'lars', 'viewer', 'Lager-Zugang-551'), ('Vera Vertrieb', 'vera', 'editor', 'Vertrieb-Zugang-77'),
                             ('Paula Personal', 'paula', 'viewer', 'Personal-Zugang-66')]:
    code, r = A.call('user_save', {'id': '', 'name': name, 'username': user, 'role': role, 'active': True, 'password': pw, 'mustChange': False})
    check(f'Mitarbeiter {user} angelegt', code == 200, r)
uid = {u['username']: u['id'] for u in A.call('users')[1]['users']}


def anmelden(user, pw):
    c = Client('198.51.100.%d' % (20 + len(user)))
    c.call('login', {'username': user, 'password': pw})
    return c


L, V, P = anmelden('lars', 'Lager-Zugang-551'), anmelden('vera', 'Vertrieb-Zugang-77'), anmelden('paula', 'Personal-Zugang-66')
rechte = lambda c: set((c.call('status')[1].get('user') or {}).get('perms') or [])

# ---------- Katalog und Standard ----------
code, rr = A.call('rechte')
check('Übersicht: Rollen, Module und Katalog', code == 200 and [r['id'] for r in rr['rollen']] == ['admin', 'viewer', 'editor']
      and {m['id'] for m in rr['module']} >= {'angebot', 'bestand', 'hr', 'verwaltung', 'import'}, code)
ZUGANG = {p['key'] for p in rr['catalog'] if p['kind'] == 'zugang'}
KAT = {p['key']: p for p in rr['catalog']}
check('Katalog: Erklärung je Recht (HR), sonst leer – Bezeichnungen in Alltagssprache', all(len(KAT[k]['hilfe']) > 80 for k in ('hr.antrag', 'hr.verwalten', 'hr.genehmigen', 'hr.uebersicht'))
      and KAT['bestand.sehen']['hilfe'] == '' and KAT['hr.verwalten']['label'] == 'Personalstelle: Urlaubsverwaltung pflegen'
      and 'nie für sich selbst' in KAT['hr.verwalten']['hilfe'] and 'nie den Grund' in KAT['hr.antrag']['hilfe'], {k: KAT[k]['label'] for k in KAT if k.startswith('hr.')})
STUFEN_ERWARTET = {'voll': {'angebot.veroeffentlichen', 'angebote.loeschen', 'wochenangebot.senden', 'sonderposten.senden', 'leergut.verwalten', 'crm.master',
                              'rewe.alle', 'rewe.verwalten', 'rewe.exportieren', 'qs.freigeben', 'qs.verwalten', 'hr.genehmigen', 'hr.uebersicht',
                              'marketing.freigeben', 'marketing.verwalten'},
                   'sensibel': {'bestand.einkaufspreise', 'crm.exportieren', 'controlling.umsatz_ek', 'controlling.bestand_ek', 'controlling.arbeitszeit_sehen',
                                'controlling.arbeitszeit_importieren', 'hr.verwalten',
                                'kunden.bearbeiten', 'sicherheit.notfall'}}
check('Katalog: Stufe je Recht für die Darstellung (Zugang, Art „sehen“ → Ansehen, „machen“ → Bearbeiten, Voll, Sensibel)',
      all(p['stufe'] == ('zugang' if p['kind'] == 'zugang' else 'sensibel' if p['key'] in STUFEN_ERWARTET['sensibel'] else 'voll' if p['key'] in STUFEN_ERWARTET['voll']
                         else 'ansehen' if p['kind'] == 'sehen' else 'bearbeiten') and p['sensibel'] == (p['stufe'] == 'sensibel') for p in rr['catalog'])
      and STUFEN_ERWARTET['voll'] | STUFEN_ERWARTET['sensibel'] <= set(KAT), {p['key']: p['stufe'] for p in rr['catalog'] if p['stufe'] in ('voll', 'sensibel')})
check('Katalog: Umsätze in € bleibt ein normales Recht (Standard an, Entscheidung Inhaber 01.11.2026)', KAT['crm.umsatz_euro']['stufe'] == 'ansehen')
check('Katalog: Vorschau-Bild je wichtigem Recht, Modulzugang zeigt die Kachel',
      all(p['vorschau'] == 'kachel' for p in rr['catalog'] if p['kind'] == 'zugang') and KAT['bestand.einkaufspreise']['vorschau'] == 'ek'
      and KAT['sicherheit.notfall']['vorschau'] == 'notfall' and KAT['angebot.bearbeiten']['vorschau'] == '' and len({p['vorschau'] for p in rr['catalog']} - {''}) == 13,
      sorted({p['vorschau'] for p in rr['catalog']}))
check('Modulzugang für jede Kachel des Registers', ZUGANG == {f'{m}.zugang' for m in ['angebot', 'bestand', 'leergut', 'crm', 'rewe', 'qs', 'einkauf', 'containerimport', 'import', 'hr', 'marketing', 'controlling', 'verwaltung', 'sicherheit']}, sorted(ZUGANG))
check('Modulzugang gehört zum Modul, Standard: beide Standardrollen (außer Register-Feld zugang_rollen: Sicherheit und Controlling ohne)',
      all(p['modul'] == p['key'].split('.')[0] and p['default'] == ([] if p['key'] in ('sicherheit.zugang', 'controlling.zugang') else ['viewer', 'editor']) for p in rr['catalog'] if p['kind'] == 'zugang'))
ZUGANG_STD = ZUGANG - {'sicherheit.zugang', 'controlling.zugang'}
check('Sicherheit: Standardrollen ohne Modulzugang', 'sicherheit.zugang' not in rechte(L) and 'sicherheit.zugang' not in rechte(V))
check('Rechte sind Modulen zugeordnet (Register)', next(p for p in rr['catalog'] if p['key'] == 'kunden.sehen')['modul'] == 'verwaltung'
      and next(p for p in rr['catalog'] if p['key'] == 'preisverlauf.sehen')['modul'] == 'angebot')
check('Bestand: alle Mitarbeiter öffnen weiter alle Module', ZUGANG_STD <= rechte(L) and ZUGANG_STD <= rechte(V))
check('Ältere Oberfläche (rechte_save ohne Modulzugang) entzieht ihn nicht',
      A.call('rechte_save', {'roles': {'viewer': ['preisverlauf.sehen', 'bestand.sehen', 'stammdaten.sehen', 'einkauf.sehen', 'hr.antrag']}})[0] == 200 and ZUGANG_STD <= rechte(L))

# ---------- Eigene Rolle anlegen ----------
check('Bearbeiter darf keine Rollen anlegen', V.call('rolle_save', {'name': 'Hack', 'rechte': ['kunden.bearbeiten']})[0] == 403)
check('Name ist Pflicht', A.call('rolle_save', {'name': ' ', 'rechte': []})[0] == 422)
check('Name doppelt (auch Standardrolle)', A.call('rolle_save', {'name': 'bearbeiter', 'rechte': []})[0] == 422)
check('Administratorrolle ist fest', A.call('rolle_save', {'id': 'admin', 'name': 'Chef', 'rechte': []})[0] == 422)
code, r = A.call('rolle_save', {'name': 'Lager', 'beschreibung': 'Nur Bestand', 'rechte': ['bestand.zugang', 'bestand.einkaufspreise', 'nutzer.verwalten']})
check('Rolle „Lager“ angelegt', code == 200 and r['id'].startswith('r') and len(r['id']) == 9, r)
LAGER = r['id']
lg = next(x for x in r['rollen'] if x['id'] == LAGER)
check('Voraussetzung ergänzt, Unbekanntes ignoriert', set(lg['rechte']) == {'bestand.zugang', 'bestand.einkaufspreise', 'bestand.sehen'} and lg['art'] == 'eigen', lg)

# ---------- Rolle zuordnen ----------
code, r = A.call('user_save', {'id': uid['lars'], 'name': 'Lars Lager', 'rollen': [LAGER], 'active': True})
check('Mitarbeiter bekommt eine eigene Rolle', code == 200 and r['user']['role'] == LAGER and r['user']['rollen'] == [LAGER], r)
st = L.call('status')[1]['user']
check('Rechte genau laut Rolle', set(st['perms']) == {'bestand.zugang', 'bestand.einkaufspreise', 'bestand.sehen'} and st['rollenName'] == 'Lager', st)
check('Lager sieht Bestand mit EK, nicht den Preisverlauf', L.call('stock')[0] == 200 and L.call('history_list')[0] == 403)
# Angebotsinhalte (Entwurf, Versionen, Kundenangebote mit Kundenpreisen) nur mit Modulzugang Angebot – unabhängig vom Host (GR-103)
OID = A.call('offers')[1]['offers'][0]['id']
for name, (code, r) in [('Entwurf', L.call('draft')), ('Versionen', L.call('versions')), ('Version', L.call('version&id=20260101-000000-abcdef')),
                        ('Kundenangebot', L.call('offer&angebot=' + OID)), ('Vorschau des Entwurfs', L.call('offer&draft=1')), ('Liste der Kundenangebote', L.call('offers'))]:
    check(f'Ohne Modulzugang Angebot: {name} 403 (ohne Seitensperre)', code == 403 and r.get('code') != 'kein_modulzugang', (code, r))
check('Standardrolle mit Modulzugang: Entwurf, Versionen, Kundenangebot, Liste weiter offen', all(V.call(a_)[0] == 200 for a_ in ('draft', 'versions', 'offers', 'offer&angebot=' + OID)))
check('Öffentliches Wochenangebot ohne Anmeldung unverändert', Client('198.51.100.90').call('offer')[0] == 200)
code, r = A.call('rolle_save', {'name': 'Kundenservice', 'rechte': ['verwaltung.zugang', 'kunden.sehen']})
KS = r['id']
assert A.call('user_save', {'id': '', 'name': 'Kurt Kunde', 'username': 'kurt', 'rollen': [KS], 'active': True, 'password': 'Kunden-Zugang-88', 'mustChange': False})[0] == 200
K = anmelden('kurt', 'Kunden-Zugang-88')
check('Kundenverwaltung ohne Modulzugang Angebot: Liste der Kundenangebote (Namen) ja, Entwurf und Kundenpreise nein',
      K.call('offers')[0] == 200 and K.call('draft')[0] == 403 and K.call('offer&angebot=' + OID)[0] == 403)
uid['kurt'] = next(u_['id'] for u_ in A.call('users')[1]['users'] if u_['username'] == 'kurt')
check('Ausnahme je Mitarbeiter (für „Was darf …?“)', A.call('user_save', {'id': uid['kurt'], 'name': 'Kurt Kunde', 'rollen': [KS], 'active': True, 'grant': ['einkauf.sehen'], 'deny': []})[0] == 200
      and 'einkauf.sehen' in rechte(K))
code, r = L.call('hr_start')
check('Ohne HR-Zugang: HR gesperrt (Server)', code == 403 and r.get('code') == 'kein_modulzugang' and r.get('modul') == 'hr', r)
ms = {m['id']: m for m in L.call('module_status')[1]['module']}
check('Dashboard: nur Kacheln mit Zugang', ms['bestand']['kachel']['recht'] and ms['bestand']['kachel']['zugang']
      and not ms['angebot']['kachel']['recht'] and not ms['angebot']['kachel']['zugang'] and not ms['hr']['kachel']['recht'], {k: v['kachel']['recht'] for k, v in ms.items() if v['kachel']})
check('Unbekannte Rolle wird abgelehnt', A.call('user_save', {'id': uid['lars'], 'name': 'Lars Lager', 'rollen': ['rdeadbeef'], 'active': True})[0] == 422)
check('Leere Rollenliste wird abgelehnt', A.call('user_save', {'id': uid['lars'], 'name': 'Lars Lager', 'rollen': [], 'active': True})[0] == 422)

# ---------- Mehrere Rollen ----------
code, r = A.call('rolle_save', {'name': 'Personalstelle', 'rechte': ['hr.zugang', 'hr.verwalten']})
PERS = r['id']
code, r = A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': [PERS, 'editor'], 'active': True})
check('Zwei Rollen: Standardrolle wird Hauptrolle (Rückfall nie mit mehr Rechten)', code == 200 and r['user']['role'] == 'editor' and set(r['user']['rollen']) == {'editor', PERS}, r)
pv = rechte(V)
check('Rechte addieren sich', {'angebot.bearbeiten', 'hr.verwalten', 'hr.antrag', 'hr.zugang'} <= pv and 'kunden.sehen' not in pv, sorted(pv))
check('Personalstelle öffnet die HR-Verwaltung', V.call('hr_verwaltung')[0] == 200)
code, r = A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['admin', PERS], 'active': True})
check('Administrator schließt weitere Rollen aus', code == 200 and r['user']['role'] == 'admin' and r['user']['rollen'] == ['admin'], r)
A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor', PERS], 'active': True})
check('Eigene Rollen nicht änderbar', A.call('user_save', {'id': uid['admin'], 'name': 'Administrator', 'rollen': ['editor'], 'active': True})[0] == 422)
check('Ältere Oberfläche (nur „role“) behält weitere Rollen', A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'role': 'editor', 'active': True})[0] == 200
      and 'hr.verwalten' in rechte(V))
code, r = A.call('bestellungen')
check('Bestellungen zuweisen: alle mit Bearbeitungsrecht (statt Rollenname)', code == 200 and {a['id'] for a in r['assignees']} >= {uid['vera'], uid['admin']}
      and uid['lars'] not in {a['id'] for a in r['assignees']}, r.get('assignees'))

# ---------- CRM: Master-Cockpit, Umsätze in €, Mengen in kg (Auftrag des Inhabers 01.11.2026) ----------
EK = {'crm.umsatz_euro', 'crm.umsatz_kg'}
kat = {p['key']: p for p in A.call('rechte')[1]['catalog']}
check('Katalog: Master-Cockpit ohne Standardrolle, setzt „CRM ansehen“ voraus', kat['crm.master']['default'] == [] and kat['crm.master']['requires'] == ['crm.sehen']
      and kat['crm.master']['eigene'] is False and kat['crm.master']['modul'] == 'crm', kat.get('crm.master'))
check('Katalog: CRM € und kg Standard an (Standardrollen und eigene Rollen), ohne Voraussetzung',
      all(kat[k]['default'] == ['viewer', 'editor'] and kat[k]['requires'] == [] and kat[k]['eigene'] is True and kat[k]['modul'] == 'crm' for k in EK), [kat.get(k) for k in EK])
check('Standardrolle: € und kg an – „CRM ansehen“ und Master kommen dadurch nicht dazu', EK <= rechte(V) and 'crm.sehen' not in rechte(V) and 'crm.master' not in rechte(V), sorted(rechte(V)))
check('Eigene Rolle mit dem neuen Katalog gespeichert: nur die gewählten Rechte (Lager ohne € und kg)', not (EK & rechte(L)), sorted(rechte(L)))
rollen_vorher, rechte_vorher = dokument('rollen'), dokument('rechte')
# Daten von vor den neuen Rechten (Rückfall/Bestand): eigene Rolle und Rollenrechte ohne „bekannt“
alt = json.loads(json.dumps(rollen_vorher))
for r_ in alt['eigene'].values():
    r_.pop('bekannt', None)
storage_write('rollen', alt)
check('Eigene Rolle von früher (ohne „bekannt“): € und kg an, sonst unverändert', rechte(L) == {'bestand.zugang', 'bestand.einkaufspreise', 'bestand.sehen'} | EK, sorted(rechte(L)))
storage_write('rechte', {'roles': {r_: [k for k in rechte_vorher['roles'][r_] if k not in EK] for r_ in ('viewer', 'editor')}})
rr = A.call('rechte')[1]['roles']
check('Rollenrechte von früher (ohne „bekannt“): € und kg für beide Standardrollen an', EK <= set(rr['viewer']) and EK <= set(rr['editor']) and EK <= rechte(V), rr)
code, r = A.call('rolle_save', {'id': LAGER, 'name': 'Lager', 'rechte': ['bestand.zugang', 'bestand.einkaufspreise', 'crm.umsatz_kg']})
check('Eigene Rolle gespeichert: abgewähltes € bleibt aus, gewähltes kg an', code == 200 and 'crm.umsatz_euro' not in rechte(L) and 'crm.umsatz_kg' in rechte(L)
      and 'crm.umsatz_euro' in (next(x for x in dokument('rollen')['eigene'].values() if x['name'] == 'Lager').get('bekannt') or []), sorted(rechte(L)))
code, r = A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor', PERS], 'active': True, 'grant': ['crm.master'], 'deny': ['crm.umsatz_euro']})
check('Je Mitarbeiter: € verboten, kg bleibt; Master erlaubt ergänzt „CRM ansehen“', code == 200 and 'crm.umsatz_euro' not in rechte(V) and {'crm.umsatz_kg', 'crm.master', 'crm.sehen'} <= rechte(V), sorted(rechte(V)))
A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor', PERS], 'active': True, 'grant': [], 'deny': []})
A.call('rolle_save', {'id': LAGER, 'name': 'Lager', 'rechte': sorted(lg['rechte'])})
storage_write('rechte', rechte_vorher)
check('Zustand wiederhergestellt', rechte(L) == set(lg['rechte']) and EK <= rechte(V) and 'crm.sehen' not in rechte(V))

# ---------- Vertreter im CRM am Mitarbeiter (Feld „vertreter“) ----------
storage_write('vertreter', {'rev': 1, 'groups': [{'nr': '11', 'name': 'Vera Vertrieb', 'kurz': 'VV', 'telefon': '', 'plz': '', 'ort': '', 'land': ''},
                                                 {'nr': '12', 'name': 'Tom Tour', 'kurz': 'TT', 'telefon': '', 'plz': '', 'ort': '', 'land': ''}]})
code, r = A.call('users')
check('Mitarbeiterliste: Vertreter zur Auswahl (Nummer und Name), Feld je Mitarbeiter', code == 200 and r['vertreter'] == [{'nr': '11', 'name': 'Vera Vertrieb'}, {'nr': '12', 'name': 'Tom Tour'}]
      and all(u_['vertreter'] == '' for u_ in r['users']), r.get('vertreter'))
check('Mitarbeiterliste nur für Administratoren', V.call('users')[0] == 403)
code, r = A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor', PERS], 'active': True, 'vertreter': '11'})
check('Vertreter zugeordnet', code == 200 and r['user']['vertreter'] == '11' and next(x for x in dokument('nutzer')['users'] if x['id'] == uid['vera'])['vertreter'] == '11', r.get('user', {}).get('vertreter'))
check('Unbekannter Vertreter → 422', A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor', PERS], 'active': True, 'vertreter': '99'})[0] == 422)
check('Ungültige Angabe (Liste, Sonderzeichen) → 422', A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor', PERS], 'active': True, 'vertreter': ['11']})[0] == 422
      and A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor', PERS], 'active': True, 'vertreter': '1;1'})[0] == 422)
check('Ältere Oberfläche (ohne Feld): Vertreter bleibt', A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor', PERS], 'active': True})[1]['user']['vertreter'] == '11')
storage_write('vertreter', {'rev': 2, 'groups': [{'nr': '12', 'name': 'Tom Tour', 'kurz': 'TT', 'telefon': '', 'plz': '', 'ort': '', 'land': ''}]})
code, r = A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor', PERS], 'active': True, 'vertreter': '11'})
check('Vertreter nicht mehr in den Stammdaten (z. B. nach Import): gespeicherte Nummer bleibt speicherbar', code == 200 and r['user']['vertreter'] == '11', (code, r.get('error')))
check('… aber nicht neu wählbar', A.call('user_save', {'id': uid['lars'], 'name': 'Lars Lager', 'rollen': [LAGER], 'active': True, 'vertreter': '11'})[0] == 422)
code, r = A.call('user_save', {'id': '', 'name': 'Tim Tour', 'username': 'tim', 'rollen': ['viewer'], 'active': True, 'password': 'Tour-Zugang-4711', 'mustChange': False, 'vertreter': '12'})
check('Neuer Mitarbeiter mit Vertreter', code == 200 and r['user']['vertreter'] == '12', r)
code, r = A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor', PERS], 'active': True, 'vertreter': ''})
check('Zuordnung entfernt (Feld gelöscht)', code == 200 and r['user']['vertreter'] == '' and 'vertreter' not in next(x for x in dokument('nutzer')['users'] if x['id'] == uid['vera']))
log = json.dumps(A.call('log')[1].get('entries') or [], ensure_ascii=False)
check('Protokoll: Vertreter (CRM) mit Nummer und Name', 'Vertreter (CRM)' in log and '12 – Tom Tour' in log, log[:300])
storage_write('vertreter', {'rev': 3, 'groups': [{'nr': '11', 'name': 'Vera Vertrieb', 'kurz': 'VV', 'telefon': '', 'plz': '', 'ort': '', 'land': ''},
                                                 {'nr': '12', 'name': 'Tom Tour', 'kurz': 'TT', 'telefon': '', 'plz': '', 'ort': '', 'land': ''}]})

# ---------- Standardrolle ändern, Modulzugang entziehen ----------
code, r = A.call('rolle_save', {'id': 'editor', 'name': 'Vertrieb Innendienst', 'rechte': sorted(set(next(x for x in A.call('rechte')[1]['rollen'] if x['id'] == 'editor')['rechte']) - {'hr.zugang'})})
check('Standardrolle umbenannt, Rechte geändert', code == 200 and next(x for x in r['rollen'] if x['id'] == 'editor')['name'] == 'Vertrieb Innendienst', r)
check('Rechte gelten sofort; HR bleibt über die zweite Rolle offen', 'hr.zugang' in rechte(V) and V.call('hr_start')[0] == 200)
A.call('user_save', {'id': uid['vera'], 'name': 'Vera Vertrieb', 'rollen': ['editor'], 'active': True})
check('Nur noch Standardrolle ohne HR-Zugang: HR gesperrt', V.call('hr_start')[1].get('code') == 'kein_modulzugang')
check('Status bleibt erreichbar (Rückweg, Abmelden)', V.call('status')[0] == 200)
rd = A.call('rechte')[1]
check('Neuer Name überall', rd['roleLabels']['editor'] == 'Vertrieb Innendienst' and V.call('status')[1]['user']['rollenName'] == 'Vertrieb Innendienst')

# ---------- Kopieren, Löschen, Protokoll ----------
code, r = A.call('rolle_save', {'name': 'Lager Nord', 'kopieVon': LAGER})
check('Rolle kopiert (Rechte der Vorlage)', code == 200 and set(next(x for x in r['rollen'] if x['id'] == r['id'])['rechte']) == set(lg['rechte']), r)
code, r = A.call('rolle_loeschen', {'id': LAGER})
check('Rolle in Verwendung wird nicht gelöscht', code == 422 and 'Lars Lager' in r.get('error', ''), r)
check('Standardrolle nicht löschbar', A.call('rolle_loeschen', {'id': 'viewer'})[0] == 422)
check('Bearbeiter darf nicht löschen', V.call('rolle_loeschen', {'id': LAGER})[0] == 403)
log = str(A.call('log')[1].get('entries') or [])
check('Protokoll: angelegt, geändert, Rechte', 'Rolle „Lager“ angelegt' in log and 'Rolle „Vertrieb Innendienst“ geändert' in log and 'Modul „HR“ öffnen' in log)

with sync_playwright() as pw:
    br = pw.chromium.launch()
    fehler = []

    def seite(user, password, w=1440, ziel='/admin/'):
        pg = br.new_page(viewport={'width': w, 'height': 950}, is_mobile=w < 500); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', password); pg.click('#auth-submit'); pg.wait_for_selector('#screen-auth', state='hidden')
        if ziel != '/admin/': pg.goto(B + ziel)
        return pg

    a = seite('admin', PW)
    a.wait_for_selector('#screen-editor:not([hidden]) tr[data-id]')
    a.click('#vt-rollen'); a.wait_for_selector('#view-rollen .rl-item.on')
    check('UI: Rollenliste mit Standard- und eigenen Rollen, gruppiert', a.locator('#view-rollen .rl-item').count() == 7 and a.locator('#view-rollen .rl-gruppe').count() == 3
          and 'Vertrieb Innendienst' in a.inner_text('#view-rollen .rl-liste') and 'Lager Nord' in a.inner_text('#view-rollen .rl-liste'))
    check('UI: je Modul eine Zeile mit Stufe, „Auf einen Blick“ mit jeder Kachel; bis 1500 px alle Module zugeklappt',
          a.locator('#view-rollen .rl-zeile[data-rl-modul]').count() >= len(ZUGANG) and a.locator('#view-rollen .rl-kachel').count() == len(ZUGANG)
          and a.locator('#rl-detail').count() == 0)
    a.wait_for_function("() => document.getAnimations().every((x) => x.playState !== 'running')")
    a.screenshot(path=SH + '/rollen-desktop.png', full_page=True)
    # Neue Rolle über die Oberfläche
    a.click('[data-rl-akt="neu"]'); a.wait_for_selector('#rl-name:focus')
    a.click('.rl-zeile[data-rl-modul="crm"] .rl-z-kopf'); a.wait_for_selector('#rl-detail [data-rl-key="crm.umsatz_euro"]')
    check('UI: neue Rolle mit „CRM: Umsätze in €“ und „Mengen in kg“ vorgewählt (Standard an)', a.is_checked('#rl-detail [data-rl-key="crm.umsatz_euro"]')
          and a.is_checked('#rl-detail [data-rl-key="crm.umsatz_kg"]') and not a.is_checked('#rl-detail [data-rl-key="crm.master"]'))
    check('UI: Modul ohne Zugang mit einzelnen Rechten heißt „Angepasst“', 'Angepasst' in a.inner_text('.rl-zeile[data-rl-modul="crm"]'))
    a.uncheck('#rl-detail [data-rl-key="crm.umsatz_euro"]')
    a.fill('#rl-name', 'Einkauf')
    gedrueckt = lambda m, st, ort='z': a.get_attribute(f'[data-rl-stufe="{m}:{st}"][data-ort="{ort}"]', 'aria-pressed') == 'true'
    an = lambda k: a.is_checked(f'#rl-detail [data-rl-key="{k}"]')
    a.click('[data-rl-stufe="einkauf:bearbeiten"][data-ort="z"]'); a.wait_for_selector('#rl-detail [data-rl-key="einkauf.melden"]:checked')
    check('UI: Stufe „Bearbeiten“ schaltet Zugang und alle Rechte des Moduls ein, Details zeigen das Modul',
          an('einkauf.zugang') and an('einkauf.sehen') and an('einkauf.melden') and gedrueckt('einkauf', 'bearbeiten') and gedrueckt('einkauf', 'bearbeiten', 'd'))
    check('UI: Fokus bleibt auf der gewählten Stufe', a.evaluate('document.activeElement.dataset.rlStufe') == 'einkauf:bearbeiten')
    check('UI: Einkauf hat keine Stufe „Voll“ („–“)', a.locator('[data-rl-stufe="einkauf:voll"]').count() == 0 and a.locator('.rl-zeile[data-rl-modul="einkauf"] .rl-st-leer').count() == 1)
    a.click('[data-rl-stufe="einkauf:ansehen"][data-ort="d"]'); a.wait_for_selector('#rl-detail [data-rl-key="einkauf.melden"]:not(:checked)')
    check('UI: Stufe „Ansehen“: nur lesen', an('einkauf.sehen') and not an('einkauf.melden') and gedrueckt('einkauf', 'ansehen'))
    a.click('[data-rl-stufe="einkauf:bearbeiten"][data-ort="d"]'); a.wait_for_selector('#rl-detail [data-rl-key="einkauf.melden"]:checked')
    a.click('[data-rl-stufe="bestand:ansehen"][data-ort="z"]'); a.wait_for_selector('#rl-detail [data-rl-key="bestand.sehen"]:checked')
    check('UI: sensibles Recht bleibt bei „Ansehen“ aus', not an('bestand.einkaufspreise') and 'sensibel aus' in a.inner_text('.rl-zeile[data-rl-modul="bestand"]'))
    a.check('#rl-detail [data-rl-key="bestand.einkaufspreise"]')
    check('UI: sensibles Recht einzeln an – Stufe bleibt „Ansehen“', gedrueckt('bestand', 'ansehen') and 'sensibel an' in a.inner_text('.rl-zeile[data-rl-modul="bestand"]'))
    a.click('[data-rl-stufe="bestand:bearbeiten"][data-ort="d"]'); a.wait_for_selector('#rl-detail [data-rl-key="bestand.importieren"]:checked')
    check('UI: Stufenwechsel ändert sensible Rechte nicht', an('bestand.einkaufspreise') and an('bestand.mhd_senden'))
    a.click('[data-rl-stufe="bestand:kein"][data-ort="d"]'); a.wait_for_selector('#rl-detail [data-rl-key="bestand.sehen"]:not(:checked)')
    check('UI: „Kein Zugang“ schaltet alles im Modul aus, auch sensible Rechte', a.locator('#rl-detail [data-rl-key]:checked').count() == 0)
    a.check('#rl-detail [data-rl-key="bestand.einkaufspreise"]')
    check('UI: Recht schaltet seine Voraussetzung ein', an('bestand.sehen'))
    a.uncheck('#rl-detail [data-rl-key="bestand.sehen"]')
    check('UI: Voraussetzung weg → abhängiges Recht weg', not an('bestand.einkaufspreise'))
    # Vorschau-Bilder (Beispieldaten, markiert, was das Recht freischaltet)
    a.click('#rl-detail [data-rl-vorschau="bestand.einkaufspreise"]'); a.wait_for_selector('#rl-detail figure.rv[data-rv="ek"]')
    vt = a.inner_text('#rl-detail .rl-v')
    check('UI: Vorschau zeigt die markierte EK-Spalte mit Beispieldaten und sagt, dass die Rolle sie nicht sieht',
          'EK €/kg' in vt and 'Beispieldaten' in vt and 'derzeit nicht' in vt and a.locator('#rl-detail .rl-v .rv-mark').count() == 1
          and a.get_attribute('#rl-detail [data-rl-vorschau="bestand.einkaufspreise"]', 'aria-expanded') == 'true', vt[:200])
    a.locator('#rl-detail .rl-r[data-rl-recht="bestand.einkaufspreise"]').screenshot(path=SH + '/rollen-vorschau-ek.png')
    a.screenshot(path=SH + '/rollen-desktop-offen.png', full_page=True)
    arten = sorted({p['vorschau'] for p in KAT.values() if p['vorschau']})
    fehlt = a.evaluate("arten => arten.filter((x) => !WA.rollenVorschau(x, 'Test', 'boxes').includes('rv-mark'))", arten)
    check('UI: zu jedem Vorschau-Eintrag im Katalog gibt es ein Bild mit Markierung', not fehlt and len(arten) == 13, fehlt)
    a.click('#rl-detail [data-rl-vorschau="bestand.einkaufspreise"]'); a.wait_for_selector('#rl-detail figure.rv', state='detached')
    # HR: Erklärungen, keine Stufe „Ansehen“
    a.click('.rl-zeile[data-rl-modul="hr"] .rl-z-kopf'); a.wait_for_selector('#rl-detail [data-rl-key="hr.antrag"]')
    hr_text = a.inner_text('#rl-detail')
    check('UI: HR-Rechte mit Erklärung und Voraussetzung, andere Module unverändert', a.locator('#rl-detail .rl-hilfe').count() == 4
          and 'sieht die Gründe' in hr_text and 'Setzt „Eigenen Urlaub und Gleittage beantragen“ voraus' in hr_text, hr_text[:300])
    check('UI: HR ohne Stufe „Ansehen“, Personalstelle unter „Sensibel“', a.locator('[data-rl-stufe="hr:ansehen"]').count() == 0
          and a.locator('#rl-detail .rl-abschn.sens [data-rl-key="hr.verwalten"]').count() == 1)
    a.locator('#rl-detail').screenshot(path=SH + '/rollen-hr-erklaerung.png')
    check('UI: „Auf einen Blick“: Einkauf „Bearbeiten“, HR ohne Zugang, Zahlen', 'Bearbeiten' in a.inner_text('.rl-kachel[data-rl-oeffnen="einkauf"]')
          and 'kein zugang' in a.inner_text('.rl-kachel[data-rl-oeffnen="hr"]').lower() and 'von %d Modulen' % len(ZUGANG) in a.inner_text('.rl-blick'))
    check('UI: Stand zeigt die neue Rolle', 'Neue Rolle' in a.inner_text('#rl-stand'))
    a.click('[data-rl-akt="speichern"]'); a.wait_for_selector('#view-rollen .rl-item.on[data-rl-wahl]:has-text("Einkauf")')
    a.wait_for_function("() => document.querySelector('#rl-stand').textContent.includes('Alles gespeichert')")
    ek = next(x for x in A.call('rechte')[1]['rollen'] if x['name'] == 'Einkauf')
    check('UI: Rolle gespeichert (abgewähltes € bleibt aus)', set(ek['rechte']) == {'einkauf.zugang', 'einkauf.sehen', 'einkauf.melden', 'crm.umsatz_kg'}, ek)
    check('UI: nach dem Speichern alles gespeichert', 'Alles gespeichert' in a.inner_text('#rl-stand'))
    # Wechsel mit ungespeicherten Änderungen fragt nach
    a.fill('#rl-name', 'Einkauf Hamburg')
    check('UI: ungespeicherte Änderung sichtbar (Stand, Liste)', 'nicht gespeichert' in a.inner_text('#rl-stand') and 'geändert' in a.inner_text('#view-rollen .rl-item.on'))
    a.click('#view-rollen .rl-item:has-text("Lager Nord")'); a.wait_for_selector('#dlg-confirm[open]')
    check('UI: ungespeicherte Änderungen werden nicht stillschweigend verworfen', 'verwerfen' in a.inner_text('#dlg-confirm'))
    a.click('#dlg-confirm [data-v="0"]'); a.wait_for_selector('#dlg-confirm:not([open])', state='attached')
    check('UI: nach Abbrechen bleibt die Rolle gewählt', 'Einkauf' in a.inner_text('#view-rollen .rl-item.on'))
    a.click('[data-rl-akt="verwerfen"]'); a.wait_for_function("() => document.querySelector('#rl-name').value === 'Einkauf'")
    # Rolle löschen (ohne Mitarbeiter)
    a.click('#view-rollen .rl-item:has-text("Lager Nord")'); a.wait_for_selector('#view-rollen .rl-item.on:has-text("Lager Nord")')
    a.click('[data-rl-akt="loeschen"]'); a.wait_for_selector('#dlg-confirm[open]')
    a.click('#dlg-confirm [data-v="1"]')
    a.wait_for_function("() => !document.querySelector('#view-rollen .rl-liste').textContent.includes('Lager Nord')")
    check('UI: Rolle gelöscht', all(x['name'] != 'Lager Nord' for x in A.call('rechte')[1]['rollen']))
    # Rollen vergleichen, „Was darf …?“
    a.click('[data-rl-akt="vergleich"]'); a.wait_for_selector('#view-rollen .rl-mx')
    rollen_ui = A.call('rechte')[1]['rollen']
    check('UI: Vergleich mit allen Rollen und Modulen', a.locator('.rl-mx thead th').count() == 1 + len(rollen_ui)
          and a.locator('.rl-mx tbody tr').count() >= len(ZUGANG)
          and 'Alle Rechte' in a.inner_text('.rl-mx tbody tr:first-child'))
    check('UI: nur Kachel offen, darin keine Rechte → „Nur Zugang“ (Standardrolle, Leergut)', a.inner_text('[data-rl-zelle="viewer|leergut"]').strip() == 'Nur Zugang'
          and a.inner_text('[data-rl-zelle="viewer|bestand"]').strip() == 'Ansehen', a.inner_text('[data-rl-zelle="viewer|leergut"]'))
    a.select_option('#rl-person', uid['kurt']); a.wait_for_function("() => document.querySelector('.rl-was').textContent.includes('Kurt Kunde hat')")
    was = a.inner_text('.rl-was')
    check('UI: „Was darf …?“ nennt Rollen, Ergebnis je Modul und persönliche Ausnahmen', 'Kundenservice' in was and 'Ausnahmen' in was
          and '+ Einkauf (Fehlmengen) ansehen' in was and a.locator('.rl-mx th.mein').count() == 1, was[:300])
    a.locator('.rl-vergleich').screenshot(path=SH + '/rollen-vergleich.png')
    a.click('[data-rl-zelle="viewer|bestand"]'); a.wait_for_selector('#view-rollen .rl-item.on[data-rl-wahl="viewer"]')
    check('UI: Klick auf eine Zelle öffnet Rolle und Modul', a.is_visible('#rl-detail [data-rl-key="bestand.sehen"]') and a.is_checked('#rl-detail [data-rl-key="bestand.sehen"]'))
    # breit (ab 1501 px): Rechte des Moduls daneben
    a.set_viewport_size({'width': 1700, 'height': 1000}); a.wait_for_selector('aside#rl-detail [data-rl-key="bestand.sehen"]')
    check('UI breit: Rechte des gewählten Moduls in der Seitenleiste, keine aufgeklappte Zeile', a.locator('.rl-zeile-det').count() == 0
          and 'on' in a.get_attribute('.rl-zeile[data-rl-modul="bestand"]', 'class').split())
    a.click('.rl-zeile[data-rl-modul="crm"] .rl-z-kopf'); a.wait_for_selector('aside#rl-detail [data-rl-key="crm.sehen"]')
    check('UI breit: Zeile wählen zeigt deren Rechte daneben', a.is_visible('aside#rl-detail [data-rl-stufe="crm:voll"]'))
    a.screenshot(path=SH + '/rollen-breit.png', full_page=True)
    a.set_viewport_size({'width': 1440, 'height': 950}); a.wait_for_selector('aside#rl-detail', state='detached')
    # Administrator: fest, nichts änderbar
    a.click('#view-rollen .rl-item[data-rl-wahl="admin"]'); a.wait_for_selector('#rl-name[disabled]')
    check('UI: Administrator fest (alles an, gesperrt)', a.locator('#view-rollen [data-rl-key]:not([disabled])').count() == 0
          and a.locator('#view-rollen [data-rl-stufe]:not([disabled])').count() == 0 and a.locator('#view-rollen [data-rl-key]:not(:checked)').count() == 0
          and not a.is_visible('[data-rl-akt="speichern"]'))
    # Mitarbeiterdialog: mehrere Rollen
    a.click('#vt-users'); a.wait_for_selector(f'[data-uedit="{uid["paula"]}"]')
    check('UI: Mitarbeiterliste zeigt Rollennamen', 'Lager' in a.inner_text(f'#view-users tr[data-uid="{uid["lars"]}"]'))
    a.click(f'[data-uedit="{uid["paula"]}"]'); a.wait_for_selector('#dlg-user[open] [name="rollen"]')
    vt_opt = a.eval_on_selector_all('#dlg-user [name="vertreter"] option', 'os => os.map((o) => o.textContent)')
    check('UI: Feld „Vertreter im CRM“ mit den Vertretern der Stammdaten', vt_opt == ['– keiner –', '11 – Vera Vertrieb', '12 – Tom Tour'], vt_opt)
    a.select_option('#dlg-user [name="vertreter"]', '12')
    a.check(f'#dlg-user [name="rollen"][value="{PERS}"]')
    a.check('#dlg-user [name="rollen"][value="admin"]')
    check('UI: Administrator wählt die anderen Rollen ab', not a.is_checked(f'#dlg-user [name="rollen"][value="{PERS}"]') and a.locator('#ur-box').is_hidden())
    a.check(f'#dlg-user [name="rollen"][value="{PERS}"]'); a.check('#dlg-user [name="rollen"][value="viewer"]')
    check('UI: andere Rolle wählt Administrator ab', not a.is_checked('#dlg-user [name="rollen"][value="admin"]'))
    a.screenshot(path=SH + '/rollen-mitarbeiter.png')
    a.click('#dlg-user button[type=submit]'); a.wait_for_selector('#dlg-user', state='hidden')
    pu = next(x for x in A.call('users')[1]['users'] if x['username'] == 'paula')
    check('UI: zwei Rollen und Vertreter gespeichert', set(pu['rollen']) == {'viewer', PERS} and pu['role'] == 'viewer' and pu['vertreter'] == '12', pu)
    # schmal
    a.set_viewport_size({'width': 390, 'height': 844})
    a.click('#vt-rollen'); a.wait_for_selector('#view-rollen .rl-item.on')
    check('390 px: keine Seitenleiste, Rechte höchstens eines Moduls unter seiner Zeile', a.locator('aside#rl-detail').count() == 0 and a.locator('.rl-zeile-det').count() <= 1)
    if a.locator('.rl-zeile[data-rl-modul="bestand"].on').count():
        a.click('.rl-zeile[data-rl-modul="bestand"] .rl-z-kopf'); a.wait_for_selector('.rl-zeile-det', state='detached')
    a.click('.rl-zeile[data-rl-modul="bestand"] .rl-z-kopf'); a.wait_for_selector('.rl-zeile-det [data-rl-key="bestand.sehen"]')
    check('390 px: Rechte direkt unter der Zeile', a.get_attribute('.rl-zeile[data-rl-modul="bestand"] .rl-z-kopf', 'aria-expanded') == 'true'
          and a.locator('.rl-zeile-det .rl-stufen button').count() >= 3)
    a.click('.rl-zeile-det [data-rl-vorschau="bestand.einkaufspreise"]'); a.wait_for_selector('.rl-zeile-det figure.rv')
    a.screenshot(path=SH + '/rollen-390.png', full_page=True)
    check('390 px: kein waagerechtes Scrollen', a.evaluate('document.documentElement.scrollWidth') <= 390)
    a.click('.rl-zeile[data-rl-modul="bestand"] .rl-z-kopf'); a.wait_for_selector('.rl-zeile-det', state='detached')
    check('390 px: erneut tippen klappt zu', a.get_attribute('.rl-zeile[data-rl-modul="bestand"] .rl-z-kopf', 'aria-expanded') == 'false')
    a.set_viewport_size({'width': 1440, 'height': 950}); a.emulate_media(color_scheme='dark')
    a.click('#view-rollen .rl-item:has-text("Personalstelle")'); a.wait_for_selector('#view-rollen .rl-item.on:has-text("Personalstelle")')
    a.screenshot(path=SH + '/rollen-dunkel.png')
    a.close()
    # Lager: Bestand ja, HR-Seite gesperrt, Dashboard nur mit Bestand
    lp = seite('lars', 'Lager-Zugang-551')
    lp.wait_for_selector('#screen-editor:not([hidden])')
    check('UI Lager: nur Bestand in der Seitenleiste', lp.is_visible('#vt-stock') and not lp.is_visible('#vt-hist') and not lp.is_visible('#vt-rollen'))
    lp.goto(B + '/dashboard/'); lp.wait_for_selector('#db-grid .db-tile'); lp.wait_for_selector('#db-heute-liste[aria-busy="false"]')
    kach = lp.eval_on_selector_all('#db-grid .db-tile', 'els => els.map(e => e.dataset.modul)')
    leiste = lp.eval_on_selector_all('#r-leiste .r-eintrag[data-modul]:not([data-modul="start"])', 'els => els.map(e => e.dataset.modul)')
    check('UI Lager: Dashboard zeigt nur Bestand (Favorit und Seitenleiste)', kach == ['bestand'] and leiste == ['bestand'], (kach, leiste))
    lp.screenshot(path=SH + '/rollen-dashboard-lager.png')
    lp.goto(B + '/module/hr/'); lp.wait_for_function("() => /Zugang/.test(document.body.innerText)")
    check('UI Lager: HR zeigt „kein Zugang“', 'Bereich „HR“' in lp.inner_text('body') or 'Kein Zugang' in lp.inner_text('body'), lp.inner_text('body')[:200])
    lp.close()
    check('keine Seitenfehler', not fehler, fehler[:3])
    br.close()

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
