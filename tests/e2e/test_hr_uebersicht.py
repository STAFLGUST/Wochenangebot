"""HR · Urlaubsübersicht aller Mitarbeiter (Recht hr.uebersicht, Personalstelle hr.verwalten sieht sie auch).

Geprüft: Rechte serverseitig (GR-103: ohne Recht 403, ohne Anmeldung 401, mit hr.uebersicht oder hr.verwalten 200,
hr.uebersicht öffnet keine Personalstellen-Aktionen), Recht im Katalog (zuweisbar, ohne Standardrollen), Summen je
Mitarbeiter (Anspruch, genommen/geplant/beantragt, Rest, Krank- und Gleittage nur genehmigt und nur Arbeitstage –
4-Tage-Woche, Feiertage, freie Tage), nur Mitarbeiter im Urlaubsplan, Datenschutz (keine Zeiträume, Notizen, Gründe in
der Antwort), Oberfläche (Reiter nur mit Recht, Jahr wechseln, Abteilungsfilter, Summenzeile; Desktop, 390 px, dunkel).
Gleittage-Konto (Inhaber 02.11.2026): ohne Gewährung kein Konto und kein Gleittag-Antrag; Gewähren nur Personalstelle (nicht für
sich selbst, nicht für Mitarbeiter außerhalb des Urlaubsplans), halbe Tage, Korrektur nur mit Grund, Storno; Konto ab der ersten
Gewährung, Rest unbegrenzt ins Folgejahr, genehmigte/beantragte Gleittage zählen; Antrag nur bis zum verfügbaren Rest und je
Kalenderjahr, Zurückziehen; Personalstelle trägt auch darüber hinaus ein (Hinweis); Übersicht mit Gleittage-Rest; Gründe nur für
Person und Personalstelle, Protokoll ohne Grund; Oberfläche (Streifen „Gleittage“, Umschalter im Antrag, Dialog „Gleittage
gewähren“, Spalte in der Übersicht).
Kalender nur mit der eigenen Abteilung (Inhaber 11.11.2026): Mitarbeiter bekommen nur ihre Abteilung und sich selbst (auch nicht in
der Antwort), ohne Person im Urlaubsplan nichts, ohne Abteilung nur sich; Personalstelle und Urlaubsübersicht alle; Auswahl und
Zähler im Kalender (390 px).
Urlaubskalender (Recht hr.kalender, Inhaber 11.11.2026): im Kalender bei Kollegen der eigenen Abteilung genehmigter Urlaub „U“
und Gleittag „U+“ (Personalstelle und eigene Zeile „G“), alles andere „A“ (Krank, Unentschuldigt, freie Tage, andere Abteilungen – nicht ausgeblendet), keine offenen
oder stornierten Einträge, keine Gründe/Notizen/Konten; ohne eigene Person im Urlaubsplan oder ohne Abteilung bei niemandem;
Abteilung als Text (Groß-/Kleinschreibung egal) und aus den Stammdaten (Nummer, umbenannt, gelöscht); keine Übersicht,
Jahresplanung, Verwaltung oder Export (403); Katalog (sensibel, ohne Standardrollen, setzt hr.antrag voraus); über eine eigene
Rolle vergeben und wieder entzogen; ohne hr.antrag wirkungslos; ohne Recht und mit hr.uebersicht weiter nur „A“; Personalstelle
unverändert; Oberfläche (Legende U/U+ mit Abteilung, „U+“ passt in die Zelle, Desktop und 390 px). Nur Testdaten.
"""
import datetime as dt
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

from kunden_hilfe import Client, B
from umgebung import SH

PW = 'Sicheres-Passwort-1'
res = []


def check(n, c, i=''):
    res.append(bool(c)); print(('PASS ' if c else 'FAIL ') + n + (('  ' + str(i)[:400]) if i else ''))


def montag(jahr, monat, woche=1):
    d = dt.date(jahr, monat, 1)
    while d.weekday() != 0: d += dt.timedelta(days=1)
    return d + dt.timedelta(weeks=woche - 1)


def iso(d): return d.isoformat()


Y = dt.date.today().year + 1           # alles im nächsten Jahr: genehmigter Urlaub zählt als „geplant“
FEB = montag(Y, 2)
MRZ = montag(Y, 3, 2)
AUG = montag(Y, 8, 2)

A = Client('198.51.100.2')
check('Administrator angemeldet', A.call('login', {'username': 'admin', 'password': PW})[0] == 200)
# Urlaubskalender als Einstellung über die Rollen: eigene Rolle (z. B. Schichtleitung) mit hr.kalender
st, r_ = A.call('rolle_save', {'name': 'Schichtleitung Test', 'beschreibung': 'Urlaubskalender', 'rechte': ['hr.zugang', 'hr.kalender']})
assert st == 200, r_
SL = r_['id']
check('Rolle mit hr.kalender: Voraussetzung hr.antrag ergänzt', set(next(x for x in r_['rollen'] if x['id'] == SL)['rechte']) == {'hr.zugang', 'hr.kalender', 'hr.antrag'}, r_['rollen'])
for u, n, r, p, extra in (('lena', 'Lena Leser', 'viewer', 'Leser-Zugang-77', {}), ('paul', 'Paul Personal', 'viewer', 'Personal-Zugang-77', {'grant': ['hr.verwalten']}),
                          ('uwe', 'Uwe Uebersicht', 'viewer', 'Personal-Zugang-77', {'grant': ['hr.uebersicht']}),
                          ('kai', 'Kai Kalender', 'viewer', 'Personal-Zugang-77', {'grant': ['hr.kalender']}),
                          ('sina', 'Sina Schicht', SL, 'Personal-Zugang-77', {'rollen': [SL]})):
    st, r_ = A.call('user_save', {'id': '', 'name': n, 'username': u, 'role': r, 'active': True, 'password': p, 'mustChange': False, **extra})
    assert st == 200, r_
st, r_ = A.call('user_save', {'id': '', 'vorname': 'Andre', 'nachname': 'Vierzig', 'role': 'viewer', 'active': True, 'zugang': False})
assert st == 200, r_
ids = {u['username']: u['id'] for u in A.call('users')[1]['users']}
L = Client('198.51.100.4'); L.call('login', {'username': 'lena', 'password': 'Leser-Zugang-77'})
P = Client('198.51.100.5'); P.call('login', {'username': 'paul', 'password': 'Personal-Zugang-77'})
U = Client('198.51.100.6'); U.call('login', {'username': 'uwe', 'password': 'Personal-Zugang-77'})
N = Client('198.51.100.7')
K = Client('198.51.100.8'); K.call('login', {'username': 'kai', 'password': 'Personal-Zugang-77'})
S = Client('198.51.100.9'); S.call('login', {'username': 'sina', 'password': 'Personal-Zugang-77'})

rev = P.call('mitarbeiter_hr')[1]['rev']


def hr(uid, **werte):
    global rev
    rev = P.call('mitarbeiter_hr')[1]['rev']   # aktueller Stand (Gleittage gewähren ändert die Mitarbeiterliste auch)
    # eigene Urlaubsangaben ändert eine andere Person der Personalstelle (Vier-Augen-Prinzip) – für Paul der Administrator
    st, r =(A if uid == ids['paul'] else P).call('mitarbeiter_hr_save', {'nutzer': uid, 'rev': rev, **werte})
    assert st == 200, r
    rev = r['rev']


hr(ids['lena'], abteilung='Verwaltung', pos=1, jahr=Y, anspruch=30)
hr(ids['andre-vierzig'], abteilung='Lager', pos=2, arbeitstage=[1, 2, 3, 4], jahr=Y, anspruch=24)
for x in ('admin', 'paul', 'uwe', 'kai', 'sina'):
    hr(ids[x], aktiv=False)
PL, PA = ids['lena'], ids['andre-vierzig']

# ── Rechte ──
kat = {x['key']: x for x in A.call('rechte')[1]['catalog']}
check('Recht im Katalog: Gruppe HR, keine Standardrollen, setzt hr.antrag voraus', kat.get('hr.uebersicht', {}).get('default') == []
      and kat['hr.uebersicht']['requires'] == ['hr.antrag'] and kat['hr.uebersicht']['group'] == 'HR', kat.get('hr.uebersicht'))
check('ohne Anmeldung: 401', N.call('hr_uebersicht')[0] == 401)
check('ohne Recht: 403', L.call('hr_uebersicht')[0] == 403)
check('mit hr.uebersicht: 200', U.call('hr_uebersicht')[0] == 200)
check('Personalstelle (hr.verwalten): 200', P.call('hr_uebersicht')[0] == 200)
check('Administrator: 200', A.call('hr_uebersicht')[0] == 200)
check('hr.uebersicht öffnet keine Personalstelle (hr_verwaltung, Export, Einträge 403)', U.call('hr_verwaltung')[0] == 403
      and U.call('hr_export', {'jahr': Y, 'monate': [2]})[0] == 403 and U.call('hr_eintrag_save', {'person': PL, 'art': 'K', 'von': iso(FEB), 'bis': iso(FEB)})[0] == 403)
check('hr_start meldet die Übersicht nur mit Recht', U.call('hr_start')[1].get('uebersicht') is True and P.call('hr_start')[1].get('uebersicht') is True
      and L.call('hr_start')[1].get('uebersicht') is False)
check('ungültiges Jahr: 400er-Antwort', U.call('hr_uebersicht&jahr=1800')[0] >= 400)
# Urlaubskalender (hr.kalender): sensibel, ohne Standardrollen, nur Kalender – keine Zahlen, Konten oder Personalstelle (GR-103)
kk = kat.get('hr.kalender', {})
check('hr.kalender im Katalog: Gruppe HR, keine Standardrollen, setzt hr.antrag voraus, sensibel (einzeln freigeben)', kk.get('default') == [] and kk.get('requires') == ['hr.antrag']
      and kk.get('group') == 'HR' and kk.get('kind') == 'sehen' and kk.get('stufe') == 'sensibel' and kk.get('sensibel') is True, kk)
check('… Erklärung nennt den Datenschutz (Krankheitstage ableitbar)', 'Krankheitstage' in kk.get('hilfe', '') and 'nur an Personen vergeben' in kk.get('hilfe', ''), kk.get('hilfe'))
std = {x['id']: set(x['rechte']) for x in A.call('rechte')[1]['rollen']}
check('… Standardrollen ohne hr.kalender, Lena (nur Standardrolle) ohne', 'hr.kalender' not in std['viewer'] | std['editor']
      and 'hr.kalender' not in L.call('status')[1]['user']['perms'] and 'hr.kalender' in K.call('status')[1]['user']['perms'])
st, r = K.call('hr_start')
check('hr.kalender: Start ohne Übersicht, Genehmigen oder Personalstelle', st == 200 and r['uebersicht'] is False and r['genehmigen'] is False and r['verwalten'] is False, (st, r.get('uebersicht')))
kein = {a_: K.call(a_, b_)[0] for a_, b_ in (('hr_uebersicht', None), (f'hr_uebersicht&jahr={Y}', None), ('hr_planung', None), (f'hr_planung&jahr={Y}', None),
                                              ('hr_verwaltung', None), ('hr_offen', None), ('mitarbeiter_hr', None), ('hr_export', {'jahr': Y, 'monate': [2]}),
                                              ('hr_planung_freigeben', {'jahr': Y, 'ids': ['a1']}), ('hr_eintrag_save', {'person': ids['lena'], 'art': 'U', 'von': iso(FEB), 'bis': iso(FEB)}))}
check('hr.kalender öffnet keine Zahlen, Konten oder Personalstelle: Übersicht, Jahresplanung, Verwaltung, Anträge, Export, Einträge 403', set(kein.values()) == {403}, kein)
check('Kalender ohne Anmeldung: 401', N.call(f'hr_monat&jahr={Y}&monat=2')[0] == 401)

# ── Daten (Personalstelle trägt ein, Lena beantragt) ──
def eintrag(person, art, von, bis, notiz=''):
    st, r = P.call('hr_eintrag_save', {'person': person, 'art': art, 'von': iso(von), 'bis': iso(bis), 'notiz': notiz})
    assert st == 200, r
    return r['eintrag']['id']


eintrag(PL, 'U', FEB, FEB + dt.timedelta(days=2))                                         # 3 Tage Urlaub (geplant)
eintrag(PL, 'K', FEB + dt.timedelta(days=7), FEB + dt.timedelta(days=8), 'Arztbesuch-Notiz')  # 2 Krankheitstage
eintrag(PL, 'G', MRZ, MRZ)                                                                # 1 Gleittag
weih = dt.date(Y, 12, 22)
eintrag(PL, 'K', weih, weih + dt.timedelta(days=6))                                       # über Weihnachten
erw_weih = sum(1 for i in range(7) if (weih + dt.timedelta(days=i)).weekday() < 5 and (weih + dt.timedelta(days=i)).strftime('%m-%d') not in ('12-25', '12-26'))
# Lena beantragt zuerst (Vertretung Pflicht): danach ist Andre krank – vorher lehnte der Server ab (Vertretung abwesend, 10.11.2026)
st, r = L.call('hr_antrag', {'von': iso(AUG), 'bis': iso(AUG + dt.timedelta(days=1)), 'notiz': 'Sommerreise-Notiz', 'vertretung': ids['andre-vierzig']})
check('Lena beantragt 2 Tage', st == 200, r)
eintrag(PA, 'K', AUG, AUG + dt.timedelta(days=4))                                         # Mo–Fr, 4-Tage-Woche: 4
storno = eintrag(PA, 'G', AUG + dt.timedelta(days=7), AUG + dt.timedelta(days=7))
check('stornierter Gleittag', P.call('hr_eintrag_save', {'id': storno, 'stornieren': True})[0] == 200)

st, r, raw = U.call('hr_uebersicht&jahr=' + str(Y), raw=True)
z = {x['id']: x for x in r['zeilen']}
check('nur Mitarbeiter im Urlaubsplan', set(z) == {PL, PA}, sorted(z))
lz = z.get(PL, {})
# Betriebsurlaub 24./31.12. (verpflichtend, Inhaber 10.11.2026): automatisch je ½ Tag an Arbeitstagen – nicht, wenn krank
def bu(arbeitstage, krank=()):
    return 0.5 * sum(1 for d in (dt.date(Y, 12, 24), dt.date(Y, 12, 31)) if d.weekday() + 1 in arbeitstage and d not in krank)


bu_l = bu([1, 2, 3, 4, 5], krank=[weih + dt.timedelta(days=i) for i in range(7)])
check(f'Lena: Anspruch 30, geplant 3 + {bu_l:g} Betriebsurlaub (am 24.12. krank: zählt nicht), beantragt 2, Rest {27 - bu_l:g}',
      (lz.get('anspruch'), lz.get('geplant'), lz.get('beantragt'), lz.get('genommen'), lz.get('rest')) == (30, 3 + bu_l, 2, 0, 27 - bu_l), lz)
check(f'Lena: Krank 2 + {erw_weih} über Weihnachten (ohne Wochenende und Feiertage), Gleittage 1', lz.get('krank') == 2 + erw_weih and lz.get('gleittage') == 1, lz)
az = z.get(PA, {})
check('Andre (4-Tage-Woche): Krank Mo–Fr = 4, stornierter Gleittag zählt nicht, Betriebsurlaub nur an seinen Arbeitstagen', az.get('krank') == 4 and az.get('gleittage') == 0
      and az.get('anspruch') == 24 and az.get('rest') == 24 - bu([1, 2, 3, 4]), az)
check('Reihenfolge nach Abteilung/Position', [x['id'] for x in r['zeilen']] == [PL, PA], [x['name'] for x in r['zeilen']])
check('Datenschutz: keine Zeiträume, Notizen, Gründe oder Entscheidungen in der Antwort',
      'Notiz' not in raw and not re.search(r'\d{4}-\d{2}-\d{2}', raw.replace('"heute":"' + r['heute'] + '"', '')) and 'entscheidung' not in raw
      and not any(k in x for x in r['zeilen'] for k in ('von', 'bis', 'notiz', 'eintraege', 'personalnummer')), raw[:300])
check('anderes Jahr: Konto ohne Einträge', all(x['krank'] == 0 and x['geplant'] == 0 for x in U.call('hr_uebersicht&jahr=' + str(Y - 2))[1]['zeilen']))
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll ohne Art der Abwesenheit (Krankheit)', not re.search(r'HR:[^"]*Krank', log) and 'Arztbesuch' not in log)

# ── Urlaubskalender (hr.kalender, Inhaber 11.11.2026): Urlaub der Kollegen der eigenen Abteilung, keine Tage/Konten ──
NOV = montag(Y, 11)
NOV_IDS = [eintrag(PA, 'U', NOV, NOV + dt.timedelta(days=2), 'Urlaub-Notiz'),                                        # Andre (Lager) Mo–Mi Urlaub
           eintrag(PL, 'X', NOV + dt.timedelta(days=1), NOV + dt.timedelta(days=1))]                                   # Lena (Verwaltung) freier Tag
st, r = P.call('hr_eintrag_save', {'person': PL, 'art': 'F', 'von': iso(NOV + dt.timedelta(days=3)), 'bis': iso(NOV + dt.timedelta(days=3)), 'mail': False})
assert st == 200, r                                                                                                    # Lena unentschuldigt (Do)
NOV_IDS.append(r['eintrag']['id'])
tg = lambda d: str(d.day)   # noqa: E731 – Schlüssel je Tag im Monatsplan


def monat(c, m):
    st_, r_, raw_ = c.call(f'hr_monat&jahr={Y}&monat={m}', raw=True)
    return st_, r_, raw_, {x['id']: x['tage'] for x in r_.get('personen', [])}


# Kalender nur mit der eigenen Abteilung (Inhaber 11.11.2026): Mitarbeiter bekommen nur ihre Abteilung (und sich selbst) –
# Personalstelle (hr.verwalten) und Urlaubsübersicht (hr.uebersicht) alle; auch mit hr.kalender
st, r, raw, z = monat(L, 11)
check('nur eigene Abteilung: Lena (Verwaltung) bekommt nur Verwaltung, Andre (Lager) gar nicht – auch nicht in der Antwort', st == 200
      and set(z) == {PL} and r.get('alleAbteilungen') is False and 'Andre' not in raw and 'Lager' not in raw and 'Urlaub-Notiz' not in raw, (sorted(z), r.get('alleAbteilungen')))
check('… eigene Zeile voll (x, F), Sicht „kollege“', r.get('sicht') == 'kollege' and z[PL].get(tg(NOV + dt.timedelta(days=1))) == 'x'
      and z[PL].get(tg(NOV + dt.timedelta(days=3))) == 'F', z[PL])
st, r, raw, z = monat(U, 8)
check('Urlaubsübersicht (hr.uebersicht): alle Abteilungen, Kollegen nur „A“ (Krankheit, freier Wochentag), Storno unsichtbar', st == 200 and r.get('alleAbteilungen') is True
      and {PL, PA} <= set(z) and z[PA].get(tg(AUG)) == 'A' and z[PA].get(tg(AUG + dt.timedelta(days=4))) == 'A' and tg(AUG + dt.timedelta(days=7)) not in z[PA]
      and '"K"' not in raw and r.get('sicht') == 'kollege', z.get(PA))
_, r, _, z = monat(P, 11)
check('Personalstelle: alle Abteilungen', r.get('alleAbteilungen') is True and {PL, PA} <= set(z), sorted(z))
st, r, raw, z = monat(K, 2)
check('ohne eigene Person im Urlaubsplan (auch mit hr.kalender): keine Zeilen, Sicht „kollege“', st == 200 and r.get('personen') == [] and r.get('sicht') == 'kollege'
      and r.get('urlaubAbteilung') is None and r.get('alleAbteilungen') is False, (st, r.get('sicht'), r.get('personen')))
hr(ids['kai'], aktiv=True, abteilung='verwaltung', pos=3)   # Kai im Urlaubsplan, Abteilung wie Lena (andere Schreibweise); Andre: Lager
st, r, raw, z = monat(K, 2)
check('hr.kalender mit eigener Abteilung: Sicht „urlaub“ (nicht voll), Abteilung genannt, nur Verwaltung (Lena und Kai)', st == 200 and r.get('sicht') == 'urlaub'
      and r.get('voll') is False and r.get('urlaubAbteilung') == 'verwaltung' and set(z) == {PL, ids['kai']}, (st, r.get('sicht'), r.get('urlaubAbteilung'), sorted(z)))
check('… gleiche Abteilung (Groß-/Kleinschreibung egal): genehmigter Urlaub als „U“', [z[PL].get(tg(FEB + dt.timedelta(days=i))) for i in range(3)] == ['U'] * 3, z[PL])
check('… Krankheit nur als „A“, nie Art, Grund oder Notiz', [z[PL].get(tg(FEB + dt.timedelta(days=i))) for i in (7, 8)] == ['A', 'A']
      and '"K"' not in raw and 'Krank' not in raw and 'Arzt' not in raw and 'otiz' not in raw, raw[:300])
_, ru, _, zu = monat(U, 2)
check('… Antwort wie bei Kollegen (nur „sicht“/„urlaubAbteilung“/„alleAbteilungen“ anders): keine Konten, Tage oder Zahlen je Person', set(r) == set(ru)
      and ru.get('sicht') == 'kollege' and ru.get('urlaubAbteilung') is None and all(set(x) == {'id', 'name', 'abteilung', 'ich', 'tage'} for x in r['personen'])
      and not {'konto', 'gleitKonto', 'zeilen', 'eintraege', 'offen'} & set(r), sorted(r))
check('ohne hr.kalender (nur hr.uebersicht): Urlaub weiter nur „A“', zu[PL].get(tg(FEB)) == 'A' and '"U"' not in json.dumps(ru), zu[PL])
_, r, _, z = monat(K, 3)
check('hr.kalender: genehmigter Gleittag der eigenen Abteilung als „U+“ (Inhaber 11.11.2026)', z[PL].get(tg(MRZ)) == 'U+' and '"G"' not in json.dumps(r['personen']), z[PL])
check('… Personalstelle und eigene Zeile weiter „G“, Kollegen ohne hr.kalender „A“', monat(P, 3)[3][PL].get(tg(MRZ)) == 'G' and monat(L, 3)[3][PL].get(tg(MRZ)) == 'G'
      and monat(U, 3)[3][PL].get(tg(MRZ)) == 'A')
st, r, raw, z = monat(K, 8)
check('… offener Urlaubsantrag der eigenen Abteilung unsichtbar (kein „U?“)', tg(AUG) not in z[PL] and tg(AUG + dt.timedelta(days=1)) not in z[PL]
      and '?' not in json.dumps(r['personen']) and 'Sommerreise' not in raw, z[PL])
st, r, raw, z = monat(K, 11)
check('… andere Abteilung (Lager) nicht ausgeliefert; eigene: freier Tag (X) und Unentschuldigt (F) nur „A“', PA not in z and '"U"' not in raw and 'Urlaub-Notiz' not in raw
      and z[PL].get(tg(NOV + dt.timedelta(days=1))) == 'A' and z[PL].get(tg(NOV + dt.timedelta(days=3))) == 'A' and '"F"' not in raw and '"x"' not in raw, (sorted(z), z.get(PL)))
_, r, _, z = monat(L, 11)
check('nur hr.antrag (Lena): Kai (gleiche Abteilung) wird geliefert, Andre nicht', set(z) == {PL, ids['kai']}, sorted(z))
_, r, _, z = monat(P, 11)
_, r2, _, z2 = monat(P, 8)
check('Personalstelle unverändert: Sicht „voll“ mit Art, freien Tagen und offenen Anträgen aller Abteilungen', r.get('sicht') == 'voll' and r.get('voll') is True
      and r.get('urlaubAbteilung') is None and z[PA].get(tg(NOV)) == 'U' and z[PL].get(tg(NOV + dt.timedelta(days=1))) == 'x'
      and z[PL].get(tg(NOV + dt.timedelta(days=3))) == 'F' and z2[PL].get(tg(AUG)) == 'U?' and z2[PA].get(tg(AUG)) == 'K', (z[PL], z2[PL]))
check('Administrator: Sicht „voll“, alle Abteilungen', (lambda x: x.get('sicht') == 'voll' and x.get('alleAbteilungen') is True)(A.call(f'hr_monat&jahr={Y}&monat=2')[1]))
check('hr.kalender: ungültiger Monat 422', K.call(f'hr_monat&jahr={Y}&monat=13')[0] == 422 and K.call('hr_monat&jahr=1800&monat=1')[0] >= 400)
# hr.kalender zusammen mit hr.uebersicht: alle Abteilungen, „U“ aber nur in der eigenen
assert A.call('user_save', {'id': ids['kai'], 'name': 'Kai Kalender', 'role': 'viewer', 'active': True, 'grant': ['hr.kalender', 'hr.uebersicht'], 'deny': []})[0] == 200
_, r, _, z = monat(K, 11)
_, r2, _, z2 = monat(K, 2)
check('hr.kalender + hr.uebersicht: alle Abteilungen, Lager nur „A“, Verwaltung „U“', r.get('alleAbteilungen') is True and z[PA].get(tg(NOV)) == 'A'
      and z2[PL].get(tg(FEB)) == 'U' and r2.get('sicht') == 'urlaub', (z.get(PA), z2.get(PL)))
assert A.call('user_save', {'id': ids['kai'], 'name': 'Kai Kalender', 'role': 'viewer', 'active': True, 'grant': ['hr.kalender'], 'deny': []})[0] == 200
# Abteilung wechseln: dann gilt die andere (Schreibweise egal)
hr(ids['kai'], abteilung='LAGER')
_, r, _, z = monat(K, 11)
check('Kai im Lager: jetzt nur Lager – Andres Urlaub „U“, Lena (Verwaltung) nicht geliefert', r.get('urlaubAbteilung') == 'LAGER' and z[PA].get(tg(NOV)) == 'U'
      and set(z) == {PA, ids['kai']}, (sorted(z), z.get(PA)))
# ohne Abteilung: nur die eigene Zeile – auch kein Kollege ohne Abteilung
hr(ids['kai'], abteilung=''); hr(PA, abteilung='')
_, r, _, z = monat(K, 11)
check('ohne eigene Abteilung: nur die eigene Zeile (auch nicht der Kollege ohne Abteilung), Sicht „kollege“', set(z) == {ids['kai']} and r.get('sicht') == 'kollege'
      and r.get('urlaubAbteilung') is None, (sorted(z), r.get('sicht')))
hr(PA, abteilung='Lager'); hr(ids['kai'], abteilung='verwaltung')
# Abteilungen aus den Stammdaten: Vergleich über die Nummer – auch nach dem Umbenennen (frühere Namen) und nach dem Löschen (Name)
rv = A.call('abteilungen')[1]['rev']
st, r_ = A.call('abteilungen_save', {'rev': rv, 'groups': [{'nr': '10', 'name': 'Verwaltung'}, {'nr': '20', 'name': 'Lager'}]})
_, r, _, z = monat(K, 2)
check('Stammdaten: „verwaltung“ und „Verwaltung“ = Nummer 10 → „U“, Lager nicht geliefert', st == 200 and r.get('urlaubAbteilung') == 'Verwaltung' and z[PL].get(tg(FEB)) == 'U'
      and PA not in z, (st, r.get('urlaubAbteilung'), sorted(z)))
st, r_ = A.call('abteilungen_save', {'rev': r_['rev'], 'groups': [{'nr': '10', 'name': 'Büro'}, {'nr': '20', 'name': 'Lager'}]})
_, r, _, z = monat(K, 2)
check('… umbenannt in „Büro“: weiter gleiche Abteilung („U“), Lager weiter nicht geliefert', st == 200 and r.get('urlaubAbteilung') == 'Büro' and z[PL].get(tg(FEB)) == 'U'
      and PA not in z, (r.get('urlaubAbteilung'), sorted(z)))
st, r_ = A.call('abteilungen_save', {'rev': r_['rev'], 'groups': []})
_, r, _, z = monat(K, 2)
check('… Stammdaten wieder leer: Vergleich über den Namen („U“)', st == 200 and r.get('urlaubAbteilung') == 'verwaltung' and z[PL].get(tg(FEB)) == 'U', (st, r.get('urlaubAbteilung')))
# über die Rolle vergeben und wieder entzogen – wirkt sofort (Rechte je Anfrage)
hr(ids['sina'], aktiv=True, abteilung='Verwaltung', pos=4)
_, r, _, z = monat(S, 2)
check('Rolle „Schichtleitung“ mit hr.kalender: Sicht „urlaub“', r.get('sicht') == 'urlaub' and z[PL].get(tg(FEB)) == 'U', (r.get('sicht'), z.get(PL)))
st, r_ = A.call('rolle_save', {'id': SL, 'name': 'Schichtleitung Test', 'beschreibung': 'Urlaubskalender', 'rechte': ['hr.zugang', 'hr.antrag']})
_, r, _, z = monat(S, 2)
check('… Recht aus der Rolle genommen: wieder nur „A“, weiter nur die eigene Abteilung', st == 200 and r.get('sicht') == 'kollege' and z[PL].get(tg(FEB)) == 'A'
      and PA not in z, (st, r.get('sicht'), sorted(z)))
hr(ids['sina'], aktiv=False)
# Grenzfall: hr.kalender ohne hr.antrag (verboten) – wirkungslos, kein Kalender
st, r_ = A.call('user_save', {'id': ids['kai'], 'name': 'Kai Kalender', 'role': 'viewer', 'active': True, 'grant': ['hr.kalender'], 'deny': ['hr.antrag']})
check('hr.kalender ohne hr.antrag: Recht entfällt, Kalender 403', st == 200 and 'hr.kalender' not in K.call('status')[1]['user']['perms']
      and K.call(f'hr_monat&jahr={Y}&monat=2')[0] == 403, (st, r_))
assert A.call('user_save', {'id': ids['kai'], 'name': 'Kai Kalender', 'role': 'viewer', 'active': True, 'grant': ['hr.kalender'], 'deny': []})[0] == 200
check('… wieder erlaubt: Sicht „urlaub“', K.call(f'hr_monat&jahr={Y}&monat=2')[1].get('sicht') == 'urlaub')
for x in NOV_IDS:
    assert P.call('hr_eintrag_save', {'id': x, 'stornieren': True})[0] == 200

# ── Gleittage-Konto (Inhaber 02.11.2026) ──
J0 = dt.date.today().year
check('ohne Gewährung: kein Gleittage-Konto in der Übersicht', all(x['gleitRest'] is None and x['gleitGewaehrt'] is None for x in U.call('hr_uebersicht&jahr=' + str(Y))[1]['zeilen']))
st, r = L.call('hr_start&jahr=' + str(Y))
check('ohne Gewährung: Konto inaktiv, Gleittag-Antrag 409', st == 200 and r['gleitKonto']['aktiv'] is False and r['gleittage'] == []
      and L.call('hr_antrag', {'art': 'G', 'von': iso(AUG + dt.timedelta(days=14)), 'bis': iso(AUG + dt.timedelta(days=14))})[0] == 409, r.get('gleitKonto'))
check('unbekannte Antragsart: 422', L.call('hr_antrag', {'art': 'K', 'von': iso(AUG + dt.timedelta(days=14)), 'bis': iso(AUG + dt.timedelta(days=14))})[0] == 422)
check('Gewähren nur Personalstelle (403), ohne Anmeldung 401', L.call('hr_gleittage_save', {'person': PL, 'tage': 2})[0] == 403
      and U.call('hr_gleittage_save', {'person': PL, 'tage': 2})[0] == 403 and N.call('hr_gleittage_save', {'person': PL, 'tage': 2})[0] == 401)


def gewaehren(tage, grund='', person=None, wer=None):
    return (wer or P).call('hr_gleittage_save', {'person': person or PL, 'tage': tage, 'grund': grund})


st, r = gewaehren(3, 'Inventur Test')
k = r.get('gleitKonto', {})
check('3 Tage gewährt: Konto beginnt heute, Rest 3', st == 200 and k.get('aktiv') is True and k.get('gewaehrt') == 3 and k.get('rest') == 3
      and k.get('beginn') == iso(dt.date.today()) and r['gleittage'][0]['grund'] == 'Inventur Test' and r['gleittage'][0]['von'] == 'Paul Personal', r)
st, r = gewaehren(0.5)
HALB = r['neu']
check('halber Tag gewährt: Rest 3,5', st == 200 and r['gleitKonto']['rest'] == 3.5, r.get('gleitKonto'))
check('ungültige Anzahl (0, Viertel, über 50): 422', gewaehren(0)[0] == 422 and gewaehren(0.25)[0] == 422 and gewaehren(51)[0] == 422 and gewaehren('x')[0] == 422)
check('Korrektur (negativ) nur mit Grund', gewaehren(-1)[0] == 422 and gewaehren(-1, 'Korrektur Test')[1]['gleitKonto']['rest'] == 2.5)
st, r = P.call('hr_gleittage_save', {'person': PL, 'id': HALB, 'stornieren': True})
check('Storno: zählt nicht mehr, bleibt sichtbar', st == 200 and r['gleitKonto']['rest'] == 2 and any(g['id'] == HALB and g['storniert'] for g in r['gleittage']), r.get('gleitKonto'))
check('Storno doppelt 409, unbekannt 404', P.call('hr_gleittage_save', {'person': PL, 'id': HALB, 'stornieren': True})[0] == 409
      and P.call('hr_gleittage_save', {'person': PL, 'id': 'gibt-es-nicht', 'stornieren': True})[0] == 404)
check('nie für sich selbst (403), nicht außerhalb des Urlaubsplans (422), unbekannt (422)', gewaehren(1, person=ids['paul'])[0] == 403
      and gewaehren(1, person=ids['admin'])[0] == 422 and gewaehren(1, person='u-gibt-es-nicht')[0] == 422)
st, r = L.call('hr_start&jahr=' + str(Y))
g = r['gleitKonto']
check(f'Folgejahr: Rest 2 übertragen, Gleittag im März geplant → Rest 1', g['aktiv'] and g['uebertrag'] == 2 and g['gewaehrt'] == 0 and g['geplant'] == 1 and g['rest'] == 1 and g['verfuegbar'] == 1, g)
check('Mitarbeiter sieht seine Gewährungen mit Grund (auch stornierte), ohne interne Kennungen', sorted(x['tage'] for x in r['gleittage']) == [-1, 0.5, 3]
      and 'Inventur Test' in json.dumps(r['gleittage'], ensure_ascii=False) and 'vonId' not in json.dumps(r) and all('t' not in x for x in r['gleittage']), r['gleittage'])
G1 = AUG + dt.timedelta(days=14)
check('Antrag über den Rest hinaus: 409 mit verfügbarer Zahl', (lambda s: s[0] == 409 and 'verfügbar 1' in s[1]['error'])(L.call('hr_antrag', {'art': 'G', 'von': iso(G1), 'bis': iso(G1 + dt.timedelta(days=1))})))
check('Gleittag über den Jahreswechsel: 422', L.call('hr_antrag', {'art': 'G', 'von': f'{Y}-12-31', 'bis': f'{Y + 1}-01-04'})[0] == 422)
st, r = L.call('hr_antrag', {'art': 'G', 'von': iso(G1), 'bis': iso(G1)})
GA = r.get('eintrag', {}).get('id')
check('Gleittag beantragt: Art G, beantragt, verfügbar 0', st == 200 and r['eintrag']['art'] == 'G' and r['eintrag']['status'] == 'beantragt' and r['gleitKonto']['beantragt'] == 1
      and r['gleitKonto']['verfuegbar'] == 0 and r['hinweis'] is None, r)
check('hr.kalender: offener Gleittag-Antrag der eigenen Abteilung unsichtbar (Personalstelle sieht „G?“)', str(G1.day) not in monat(K, G1.month)[3][PL]
      and monat(P, G1.month)[3][PL].get(str(G1.day)) == 'G?')
hr(ids['kai'], aktiv=False)   # Kai wieder aus dem Urlaubsplan (Summen der Übersicht unten: 2 Mitarbeiter)
check('weiterer Gleittag: 409 (Rest schon beantragt)', L.call('hr_antrag', {'art': 'G', 'von': iso(G1 + dt.timedelta(days=1)), 'bis': iso(G1 + dt.timedelta(days=1))})[0] == 409)
offen = [a for a in P.call('hr_verwaltung&jahr=' + str(Y))[1]['offen'] if a['id'] == GA]
check('Personalstelle/Genehmiger sehen den Gleittage-Rest am Antrag', offen and offen[0]['art'] == 'G' and offen[0]['gleitKonto']['rest'] == 1, offen)
check('Gleittag-Antrag zurückziehen', L.call('hr_antrag_zurueckziehen', {'id': GA})[0] == 200 and L.call('hr_start&jahr=' + str(Y))[1]['gleitKonto']['verfuegbar'] == 1)
OKT = montag(Y, 10)
st, r = P.call('hr_eintrag_save', {'person': PL, 'art': 'G', 'von': iso(OKT), 'bis': iso(OKT + dt.timedelta(days=1))})
check('Personalstelle trägt auch über das Konto hinaus ein – mit Hinweis', st == 200 and 'steht damit bei -1 Tagen' in (r.get('hinweis') or ''), r)
P.call('hr_eintrag_save', {'id': r['eintrag']['id'], 'stornieren': True})
st, r = P.call('hr_eintrag_save', {'person': PA, 'art': 'G', 'von': iso(OKT), 'bis': iso(OKT)})
check('… ohne Konto: Hinweis „noch kein Gleittage-Konto“', st == 200 and 'noch kein Gleittage-Konto' in (r.get('hinweis') or ''), r)
P.call('hr_eintrag_save', {'id': r['eintrag']['id'], 'stornieren': True})
st, r, raw = U.call('hr_uebersicht&jahr=' + str(Y), raw=True)
z = {x['id']: x for x in r['zeilen']}
check('Übersicht: Gleittage-Rest und gewährt (mit Übertrag), ohne Konto leer, ohne Gründe', z[PL]['gleitRest'] == 1 and z[PL]['gleitGewaehrt'] == 2 and z[PA]['gleitRest'] is None
      and 'Inventur' not in raw and 'Korrektur Test' not in raw, (z[PL], z[PA]))
check('Übersicht laufendes Jahr: 2 gewährt, Rest 2', (lambda zz: zz['gleitGewaehrt'] == 2 and zz['gleitRest'] == 2)({x['id']: x for x in U.call('hr_uebersicht&jahr=' + str(J0))[1]['zeilen']}[PL]))
v = {x['id']: x for x in P.call('hr_verwaltung&jahr=' + str(J0))[1]['personen']}
check('Personalstelle: Konto und Gewährungen je Mitarbeiter', v[PL]['gleitKonto']['rest'] == 2 and len(v[PL]['gleittage']) == 3 and v[PA]['gleitKonto']['aktiv'] is False)
log = json.dumps(A.call('log')[1], ensure_ascii=False)
check('Protokoll: Gewährung mit Anzahl, ohne Grund', 'Gleittage Lena Leser +3 gewährt' in log and 'Gewährung storniert' in log and 'Inventur Test' not in log and 'Korrektur Test' not in log)

# ── Oberfläche ──
fehler = []
with sync_playwright() as p:
    br = p.chromium.launch()

    def anmelden(user, pw, ip, breite=1280):
        ctx = br.new_context(viewport={'width': breite, 'height': 900}, extra_http_headers={'X-Forwarded-For': ip}, locale='de-DE', timezone_id='Europe/Berlin')
        pg = ctx.new_page(); pg.on('pageerror', lambda e: fehler.append(str(e)))
        pg.goto(B + '/admin/'); pg.wait_for_selector('#screen-auth:not([hidden])')
        pg.fill('#au-user', user); pg.fill('#pw1', pw); pg.click('#auth-submit')
        pg.wait_for_selector('#screen-auth', state='hidden')
        return ctx, pg

    for breite in (1280, 390):
        ctx, pg = anmelden('uwe', 'Personal-Zugang-77', '198.51.100.6', breite)
        pg.goto(B + '/module/hr/#uebersicht'); pg.wait_for_selector('#ueb-tabelle thead')
        check(f'{breite}px: Reiter Übersicht sichtbar, Anträge und Export nicht', pg.is_visible('[data-tab="uebersicht"]') and not pg.is_visible('[data-tab="antraege"]')
              and not pg.is_visible('[data-tab="export"]'))
        pg.click('#tab-uebersicht [data-ujahr="1"]')
        # neues Jahr geladen: Summenzeile mit dem Anspruch des Folgejahres (Titel wechselt schon vor der Antwort)
        pg.wait_for_function('(document.querySelector("#ueb-tabelle tfoot") || {}).textContent?.includes("54")')
        zeile = pg.text_content('#ueb-tabelle tbody')
        check(f'{breite}px: Tabelle mit Abteilungen und Zahlen', 'Verwaltung' in zeile and 'Lager' in zeile and 'Lena Leser' in zeile and 'Andre Vierzig' in zeile, zeile[:200])
        check(f'{breite}px: Summenzeile (2 Mitarbeiter, Anspruch 54)', 'Summe (2)' in pg.text_content('#ueb-tabelle tfoot') and '54' in pg.text_content('#ueb-tabelle tfoot'))
        check(f'{breite}px: kein waagerechtes Scrollen der Seite', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        pg.screenshot(path=os.path.join(SH, f'hr_uebersicht_{breite}.png'), full_page=True)
        if breite == 1280:
            pg.select_option('#ueb-abteilung', 'Lager')
            pg.wait_for_function('!document.querySelector("#ueb-tabelle tbody").textContent.includes("Lena")')
            check('Filter Abteilung: nur Lager, keine Summenzeile bei einer Person', 'Andre Vierzig' in pg.text_content('#ueb-tabelle tbody') and pg.locator('#ueb-tabelle tfoot').count() == 0)
            pg.select_option('#ueb-abteilung', '')
            pg.emulate_media(color_scheme='dark')
            pg.screenshot(path=os.path.join(SH, 'hr_uebersicht_1280_dunkel.png'), full_page=True)
        ctx.close()
    # Urlaubskalender (hr.kalender): Legende U/U+/abwesend, Urlaub der Kollegen sichtbar, Krankheit nur „abwesend“; keine Übersicht,
    # Jahresplanung, Anträge oder Export
    hr(ids['kai'], aktiv=True, abteilung='Verwaltung')
    for breite in (1280, 390):
        ctx, pg = anmelden('kai', 'Personal-Zugang-77', '198.51.100.8', breite)
        pg.goto(B + '/module/hr/#kalender'); pg.wait_for_selector('#kal-plan tbody tr')
        for _ in range(24):   # Monatsansicht bis Februar des Testjahres weiterblättern
            alt_ = pg.text_content('#kal-titel')
            if alt_ == f'Februar {Y}': break
            pg.click('#tab-kalender [data-monat="1"]'); pg.wait_for_function(f"document.querySelector('#kal-titel').textContent !== {json.dumps(alt_)}")
        LENA_ZEILE = "[...document.querySelectorAll('#kal-plan tbody tr')].find((tr) => tr.querySelector('th.name')?.textContent === 'Lena Leser')"
        pg.wait_for_function(f"document.querySelector('#kal-plan thead th:nth-child(2)').title.startsWith('01.02.{Y}') && ({LENA_ZEILE})?.querySelector('.hr-art.U')")
        zl = pg.evaluate(f"(() => {{ const tr = {LENA_ZEILE}; return {{ u: tr.querySelectorAll('.hr-art.U').length, a: tr.querySelectorAll('.hr-art.A').length, "
                         "titel: tr.querySelector('.hr-art.U').title }; })()")
        leg = pg.text_content('#kal-legende')
        check(f'{breite}px: hr.kalender – Lena mit 3 Tagen Urlaub (U) und 2 Tagen „abwesend“, nirgends Krank', zl == {'u': 3, 'a': 2, 'titel': 'Urlaub'}
              and pg.locator('#kal-plan .hr-art.K').count() == 0, zl)
        check(f'{breite}px: Legende U Urlaub, U+ Gleittag (nur Abteilung Verwaltung), abwesend – ohne Krank und beantragt',
              all(x in leg for x in ('UUrlaub', 'U+Gleittag', 'nur Abteilung Verwaltung', 'abwesend')) and 'Krank' not in leg and 'beantragt' not in leg
              and pg.locator('#kal-legende .hr-art.Uplus').count() == 1, leg)
        balken = [x.strip() for x in pg.locator('#kal-plan tr.abt th > span').evaluate_all('e => e.map((x) => x.textContent)')]
        check(f'{breite}px: nur die eigene Abteilung – Andre (Lager) fehlt, keine Abteilungs-Auswahl, Balken „Verwaltung 2“', pg.locator('#kal-plan th.name', has_text='Andre Vierzig').count() == 0
              and pg.locator('#kal-filter [data-abt]').count() == 0 and balken == ['Verwaltung2'], balken)
        check(f'{breite}px: Reiter Übersicht, Jahresplanung, Anträge und Export ausgeblendet', not any(pg.is_visible(f'[data-tab="{t}"]') for t in ('uebersicht', 'planung', 'antraege', 'export')))
        check(f'{breite}px: kein waagerechtes Scrollen der Seite (Kalender)', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        pg.screenshot(path=os.path.join(SH, f'hr_kalender_urlaub_{breite}.png'), full_page=True)
        # März: Lenas genehmigter Gleittag als „U+“ (Klasse „Uplus“, Farben wie Urlaub), passt in die Zelle – auch bei 390 px
        pg.click('#tab-kalender [data-monat="1"]')
        pg.wait_for_function(f"document.querySelector('#kal-plan thead th:nth-child(2)').title.startsWith('01.03.{Y}') && ({LENA_ZEILE})?.querySelector('.hr-art.Uplus')")
        up = pg.evaluate(f'''(() => {{ const tr = {LENA_ZEILE}, s = tr.querySelector('.hr-art.Uplus'), td = s.closest('td'), u = document.querySelector('#kal-legende .hr-art.U');
          s.scrollIntoView({{ inline: 'center', block: 'nearest' }});
          return {{ text: s.textContent, klasse: s.className, titel: s.title, passt: s.getBoundingClientRect().width <= td.clientWidth && td.scrollWidth <= td.clientWidth,
                    zeile: Math.round(s.getBoundingClientRect().height) <= 24, farbe: getComputedStyle(s).backgroundColor === getComputedStyle(u).backgroundColor,
                    g: document.querySelectorAll('#kal-plan .hr-art.G').length }}; }})()''')
        check(f'{breite}px: Gleittag als „U+“ (Klasse Uplus, Titel Gleittag, Farbe wie Urlaub), passt in die Zelle, kein „G“', up == {'text': 'U+', 'klasse': 'hr-art Uplus',
              'titel': 'Gleittag', 'passt': True, 'zeile': True, 'farbe': True, 'g': 0}, up)
        pg.screenshot(path=os.path.join(SH, f'hr_kalender_uplus_{breite}.png'), full_page=True)
        ctx.close()
    hr(ids['kai'], aktiv=False)
    # Abteilungs-Auswahl und Zähler: Urlaubsübersicht sieht alle Abteilungen, Mitarbeiterin (390 px) nur ihre eigene
    ctx, pg = anmelden('uwe', 'Personal-Zugang-77', '198.51.100.6')
    pg.goto(B + '/module/hr/#kalender'); pg.wait_for_selector('#kal-plan tr.abt')
    chips = [x.strip() for x in pg.locator('#kal-filter [data-abt]').all_inner_texts()]
    balken = [x.strip() for x in pg.locator('#kal-plan tr.abt th > span').evaluate_all('e => e.map((x) => x.textContent)')]
    check('Urlaubsübersicht im Kalender: alle Abteilungen mit Auswahl und Zählern', chips == ['Alle', 'Verwaltung', 'Lager'] and balken == ['Verwaltung1', 'Lager1'], (chips, balken))
    ctx.close()
    ctx, pg = anmelden('lena', 'Leser-Zugang-77', '198.51.100.4', 390)
    pg.goto(B + '/module/hr/#kalender'); pg.wait_for_selector('#kal-plan tr.abt')
    balken = [x.strip() for x in pg.locator('#kal-plan tr.abt th > span').evaluate_all('e => e.map((x) => x.textContent)')]
    check('390px Mitarbeiterin: nur die eigene Abteilung (Balken „Verwaltung 1“), keine Abteilungs-Auswahl, Andre fehlt, kein waagerechtes Scrollen',
          balken == ['Verwaltung1'] and pg.locator('#kal-filter [data-abt]').count() == 0 and pg.locator('#kal-plan th.name', has_text='Andre Vierzig').count() == 0
          and pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'), balken)
    pg.screenshot(path=os.path.join(SH, 'hr_kalender_eigene_abteilung_390.png'), full_page=True)
    ctx.close()
    ctx, pg = anmelden('lena', 'Leser-Zugang-77', '198.51.100.4')
    pg.goto(B + '/module/hr/#uebersicht'); pg.wait_for_selector('#mein-konto .hr-wert')
    check('ohne Recht: Reiter ausgeblendet, Adresse #uebersicht führt zu „Mein Urlaub“', not pg.is_visible('[data-tab="uebersicht"]') and pg.is_visible('#tab-mein'))
    ctx.close()

    # Gleittage: Übersicht nur lesend (hr.uebersicht), Gewähren (Personalstelle), Mitarbeiter beantragt
    ctx, pg = anmelden('uwe', 'Personal-Zugang-77', '198.51.100.6')
    pg.goto(B + '/module/hr/#uebersicht'); pg.wait_for_selector('#ueb-tabelle thead')
    check('Übersicht (nur ansehen): Spalte Gleittage-Rest, kein Gewähren', 'Gleittage-Rest' in pg.text_content('#ueb-tabelle thead') and not pg.is_visible('#ueb-gleit')
          and pg.locator('#ueb-tabelle [data-gleit]').count() == 0)
    ctx.close()
    for breite in (1280, 390):
        ctx, pg = anmelden('paul', 'Personal-Zugang-77', '198.51.100.5', breite)
        pg.goto(B + '/module/hr/#uebersicht'); pg.wait_for_selector(f'#ueb-tabelle [data-gleit="{PL}"]')
        if breite == 1280:
            pg.click('#ueb-gleit'); pg.wait_for_selector('#dlg-gleit[open] #gleit-person option[value="' + PL + '"]', state='attached')
            check('Dialog „Gleittage gewähren“: ohne eigene Person, ohne Mitarbeiter außerhalb des Urlaubsplans', pg.locator(f'#gleit-person option[value="{ids["paul"]}"]').count() == 0
                  and pg.locator(f'#gleit-person option[value="{ids["admin"]}"]').count() == 0)
            pg.select_option('#gleit-person', PL); pg.wait_for_selector('#gleit-konto .hr-wert')
            pg.fill('#gleit-tage', '1'); pg.fill('#gleit-grund', 'UI-Test Samstag'); pg.click('#gleit-speichern')
            pg.wait_for_function("document.querySelector('#gleit-liste').textContent.includes('UI-Test Samstag')")
            check('Gewährt über den Dialog: Meldung, Liste und Konto aktualisiert (Rest 3)', 'gewährt' in pg.text_content('#gleit-meldung')
                  and pg.text_content('#gleit-konto .hr-wert.haupt b').strip() == '3', pg.text_content('#gleit-konto'))
            pg.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
            pg.screenshot(path=os.path.join(SH, 'hr_gleittage_dialog_1280.png'))
            pg.click('#dlg-gleit [data-schliessen]')
        pg.click(f'#ueb-tabelle [data-gleit="{PL}"]'); pg.wait_for_selector('#dlg-gleit[open] #gleit-liste li button')
        check(f'{breite}px: Klick auf den Gleittage-Rest öffnet den Mitarbeiter', pg.input_value('#gleit-person') == PL
              and pg.evaluate("(() => { const d = document.querySelector('#dlg-gleit'); return d.scrollWidth <= d.clientWidth + 1; })()"))
        pg.wait_for_function("document.getAnimations().every((a) => a.playState !== 'running')")
        pg.screenshot(path=os.path.join(SH, f'hr_gleittage_dialog_{breite}.png'))
        pg.click('#dlg-gleit [data-schliessen]')
        ctx.close()
    for breite in (1280, 390):
        ctx, pg = anmelden('lena', 'Leser-Zugang-77', '198.51.100.4', breite)
        pg.goto(B + '/module/hr/'); pg.wait_for_selector('#mein-konto .hr-wert')
        pg.click('#tab-mein [data-jahr="1"]'); pg.wait_for_function(f"document.querySelector('#mein-titel').textContent.includes('{Y}')")
        pg.wait_for_selector('#mein-gleit:not([hidden])')
        gl = pg.text_content('#mein-gleit')
        check(f'{breite}px: Streifen Gleittage mit Rest und Gewährungen', '2 Tage Rest' in gl and 'aus dem Vorjahr' in gl, gl)
        check(f'{breite}px: Umschalter Urlaub/Gleittag im Antrag', pg.is_visible('#antrag-art'))
        if breite == 1280:
            pg.click('#antrag-art [data-art="G"]')
            check('Gleittag gewählt: Überschrift und Felder', pg.text_content('#antrag-titel') == 'Gleittag beantragen' and 'Erster Gleittag' in pg.text_content('#antrag'))
            G2 = montag(Y, 9)
            pg.fill('#antrag-von', iso(G2)); pg.dispatch_event('#antrag-von', 'change')
            pg.wait_for_function("document.querySelector('#antrag-tage').textContent.includes('Gleittag')")
            check('Rechnung: 1 Gleittag, noch frei', 'noch 2 Tage frei' in pg.text_content('#antrag-tage'), pg.text_content('#antrag-tage'))
            pg.click('#antrag-senden')
            pg.wait_for_function("document.querySelector('#mein-liste').textContent.includes('beantragt') && document.querySelector('#mein-liste .hr-art.G')")
            check('Gleittag-Antrag gestellt: in der Liste mit Zurückziehen', pg.locator('#mein-liste li:has(.hr-art.G) [data-zurueck]').count() >= 1)
            # Zurückziehen fragt vorher nach; Escape heißt „nein“ – der Antrag bleibt
            pg.click('#mein-liste li:has(.hr-art.G) [data-zurueck]')
            pg.wait_for_selector('#dlg-frage[open]')
            check('Zurückziehen: Rückfrage, Fokus auf „Abbrechen“', pg.evaluate('document.activeElement.id') == 'fr-nein', pg.evaluate('document.activeElement.id'))
            pg.keyboard.press('Escape'); pg.wait_for_function("!document.querySelector('#dlg-frage').open")
            check('Rückfrage mit Escape beantwortet: Antrag bleibt', pg.locator('#mein-liste li:has(.hr-art.G) [data-zurueck]').count() >= 1)
        pg.screenshot(path=os.path.join(SH, f'hr_gleittage_mein_{breite}.png'), full_page=True)
        check(f'{breite}px: kein waagerechtes Scrollen (Mein Urlaub mit Gleittagen)', pg.evaluate('document.documentElement.scrollWidth <= window.innerWidth + 1'))
        ctx.close()
    ctx, pg = anmelden('paul', 'Personal-Zugang-77', '198.51.100.5')
    pg.goto(B + '/module/hr/#antraege'); pg.wait_for_selector('#antraege-liste .hr-antrag')
    pg.wait_for_function("document.querySelector('#antraege-liste').textContent.includes('Gleittag')")
    check('Anträge: Gleittag mit Gleittage-Rest danach', 'Gleittage' in pg.text_content('#antraege-liste') and 'danach' in pg.text_content('#antraege-liste'))
    ctx.close()
    # Zurückziehen bestätigt: Antrag verschwindet aus der eigenen Liste
    ctx, pg = anmelden('lena', 'Leser-Zugang-77', '198.51.100.4', 1280)
    pg.goto(B + '/module/hr/'); pg.wait_for_selector('#mein-konto .hr-wert')
    pg.click('#tab-mein [data-jahr="1"]'); pg.wait_for_selector('#mein-liste li:has(.hr-art.G) [data-zurueck]')
    ZAHL_G = "[...document.querySelectorAll('#mein-liste li')].filter((li) => li.querySelector('.hr-art.G') && li.querySelector('[data-zurueck]')).length"
    vorher = pg.evaluate(ZAHL_G)
    pg.click('#mein-liste li:has(.hr-art.G) [data-zurueck]'); pg.wait_for_selector('#dlg-frage[open]')
    pg.click('#fr-ja')
    pg.wait_for_function(f"({ZAHL_G}) === {vorher - 1}")
    check('Zurückziehen bestätigt: Gleittag-Antrag zurückgezogen', 'zurückgezogen' in (pg.text_content('#antrag-meldung') + pg.text_content('#mein-info')))
    ctx.close()
    br.close()
check('keine JavaScript-Fehler', not fehler, fehler)

print(f'{sum(res)}/{len(res)} passed')
sys.exit(0 if all(res) else 1)
