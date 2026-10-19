/// <reference types="jest" />
declare const __dirname: string;
/* Reine Logik der App (ohne Oberfläche): Verbindung, Angebot, Bestellwunsch, Versionen */
import { adresse, Api, ApiFehler, base64, serverPruefen } from '../src/kern/api';
import { anzeigeName, aufbereiten, datum, euro, falten, filtern, kg, preisText, preisZahl, titel, zahl } from '../src/kern/angebot';
import { fingerabdruck, frachtFuer, mengeLesen, mengeText, nutzdaten, setzen, summen, terminLesen, versuchFuer, zeilenSumme } from '../src/kern/bestellung';
import { UEBERGAENGE } from '../src/kern/status';
import { versionVergleich, zuAlt } from '../src/kern/version';

// eslint-disable-next-line @typescript-eslint/no-require-imports
const fs = require('fs');
// eslint-disable-next-line @typescript-eslint/no-require-imports
const path = require('path');
// eslint-disable-next-line @typescript-eslint/no-require-imports
const OfferCore = require('../../app/assets/offer-core.js');

/* Testangebot aus den Testdaten des Repos (tests/fixtures/data-seed/angebot.php) */
function seedOffer() {
  const raw: string = fs.readFileSync(path.join(__dirname, '../../tests/fixtures/data-seed/angebot.php'), 'utf8');
  return JSON.parse(raw.slice(raw.indexOf('\n') + 1));
}
const FRACHT = { aktiv: true, frei: 300, staffeln: [{ unter: 300, kosten: 30 }, { unter: 200, kosten: 35 }], hinweis: ['x'] };

type Antwort = { status: number; json?: unknown; headers?: Record<string, string> };
function fakeFetch(antworten: Antwort[], log: { url: string; init: RequestInit }[]) {
  return async (url: string, init?: RequestInit) => {
    log.push({ url, init: init || {} });
    const a = antworten.shift();
    if (!a) throw new TypeError('Network request failed');
    const h = new Map(Object.entries(a.headers || {}).map(([k, v]) => [k.toLowerCase(), v]));
    return {
      status: a.status, ok: a.status >= 200 && a.status < 300,
      headers: { get: (k: string) => (h.has(k.toLowerCase()) ? h.get(k.toLowerCase())! : null) },
      json: async () => { if (a.json === undefined) throw new SyntaxError('kein JSON'); return a.json; },
    } as unknown as Response;
  };
}

describe('Verbindung (Api)', () => {
  test('Adresse mit Abfrage, leere Werte weggelassen', () => {
    expect(adresse('https://x.de/', 'offer', { angebot: 'kantine', leer: '', nix: undefined })).toBe('https://x.de/api/?action=offer&angebot=kantine');
  });
  test('App-Kennzeichen, Sitzung aus Kopfzeile, CSRF bei POST', async () => {
    const log: { url: string; init: RequestInit }[] = [];
    const api = new Api({ base: 'https://x.de' }, '1.0.0', fakeFetch([
      { status: 200, json: { ok: true, csrf: 'c1' }, headers: { 'X-WA-Sitzung': 'sid-neu-1234567890abcdef' } },
      { status: 200, json: { ok: true } },
    ], log));
    const gesehen: string[] = [];
    api.onSitzung = (s) => gesehen.push(s);
    await api.call('kunde_login', { body: { username: 'a', password: 'b' } });
    expect(api.sid).toBe('sid-neu-1234567890abcdef');
    expect(api.csrf).toBe('c1');
    expect(gesehen).toEqual(['sid-neu-1234567890abcdef']);
    const h0 = log[0].init.headers as Record<string, string>;
    expect(h0['X-WA-Client']).toBe('app');
    expect(h0['Content-Type']).toBe('application/json');
    expect(log[0].init.method).toBe('POST');
    expect(log[0].init.credentials).toBe('omit');   // nie Cookies – Sitzung nur über Kopfzeile
    await api.call('kunde_status');
    const h1 = log[1].init.headers as Record<string, string>;
    expect(h1['X-WA-Sitzung']).toBe('sid-neu-1234567890abcdef');
    expect(h1['X-CSRF-Token']).toBeUndefined();
    expect(log[1].init.method).toBe('GET');
  });
  test('leere Kennung nach Abmelden wird übernommen', async () => {
    const api = new Api({ base: 'https://x.de' }, '1.0.0', fakeFetch([{ status: 200, json: { ok: true }, headers: { 'X-WA-Sitzung': '' } }], []));
    api.sid = 'vorher';
    await api.call('kunde_logout', { body: {} });
    expect(api.sid).toBe('');
  });
  test('Fehler mit Meldung, Status und Wartung', async () => {
    const api = new Api({ base: 'https://x.de' }, '1.0.0', fakeFetch([
      { status: 503, json: { ok: false, wartung: true, error: 'Kurze Pause' } },
      { status: 401, json: { ok: false, error: 'Bitte erneut anmelden.' } },
    ], []));
    await expect(api.call('offer')).rejects.toMatchObject({ status: 503, wartung: true, message: 'Kurze Pause' });
    await expect(api.call('bestellungen')).rejects.toMatchObject({ status: 401, message: 'Bitte erneut anmelden.' });
  });
  test('ohne Netz: offline-Fehler', async () => {
    const api = new Api({ base: 'https://x.de' }, '1.0.0', fakeFetch([], []));
    const e = await api.call('offer').catch((x) => x);
    expect(e).toBeInstanceOf(ApiFehler);
    expect(e.offline).toBe(true);
  });
  test('Kennwortschutz der Testumgebung: Basic-Kopfzeile, 401 ohne JSON verständlich', async () => {
    const log: { url: string; init: RequestInit }[] = [];
    const api = new Api({ base: 'https://test.x.de', basic: { user: 'test', pass: 'ä-geheim' } }, '1.0.0', fakeFetch([{ status: 401 }], log));
    const e = await api.call('app_info').catch((x) => x);
    expect((log[0].init.headers as Record<string, string>).Authorization).toBe('Basic ' + base64('test:ä-geheim'));
    expect(e.code).toBe('basic_auth');
  });
  test('base64 wie btoa (UTF-8)', () => {
    expect(base64('test:abc')).toBe('dGVzdDphYmM=');
    expect(base64('ä')).toBe('w6Q=');
  });
  test('Serveradressen: https, http nur lokal', () => {
    expect(serverPruefen(' https://test.angebot-stafl.de/ ')).toBe('https://test.angebot-stafl.de');
    expect(serverPruefen('http://angebot-stafl.de')).toBeNull();
    expect(serverPruefen('http://192.168.1.20:8080')).toBe('http://192.168.1.20:8080');
    expect(serverPruefen('https://x.de/pfad')).toBeNull();
    expect(serverPruefen('javascript:alert(1)')).toBeNull();
  });
});

describe('Angebot', () => {
  const seed = seedOffer();
  const { angebot } = aufbereiten({ offer: seed, fracht: FRACHT });
  test('gleiche Merklisten-Schlüssel wie die Website (offer-core.js)', () => {
    const web = OfferCore.enrichOffer(seed).items.map((i: { key: string }) => i.key);
    expect(angebot.items.map((i) => i.key)).toEqual(web);
    expect(angebot.items.length).toBeGreaterThan(200);
    expect(new Set(web).size).toBe(web.length);
  });
  test('Titel, Bereiche, Stand', () => {
    expect(titel(angebot)).toMatch(/KW 43/);
    expect(angebot.sections.length).toBe(4);
    expect(angebot.publishedAt).toBe(seed.publishedAt);
  });
  test('Zahlen deutsch', () => {
    expect(zahl(1234.5, 2, 2)).toBe('1.234,50');
    expect(preisZahl(23.3)).toBe('23,30');
    expect(preisZahl(1.255)).toBe('1,255');
    expect(euro(1234567.891)).toBe('1.234.567,89 €');
    expect(kg(120)).toBe('120');
    expect(kg(12.5)).toBe('12,5');
    expect(preisText({ status: 'request' })).toBe('auf Anfrage');
    expect(preisText({ status: 'none' })).toBe('–');
  });
  test('Datum ohne Zeitzonenversatz', () => {
    expect(datum('2026-10-20')).toBe('20.10.2026');
  });
  test('„Fleischmeister“ unter Fleischmeister-Überschrift weglassen', () => {
    expect(anzeigeName({ name: 'Roastbeef Fleischmeister, frisch', group: 'Färse "Fleischmeister"', section: '' })).toBe('Roastbeef, frisch');
    expect(anzeigeName({ name: 'Roastbeef Fleischmeister', group: 'Färse', section: '' })).toBe('Roastbeef Fleischmeister');
  });
  test('Suche: mehrere Wörter, Umlaute, Bereich, Merkliste', () => {
    const alle = angebot.items;
    const r = filtern(alle, { q: 'roastbeef', bereich: null, nurMerkliste: false, merkliste: new Set() });
    expect(r.length).toBeGreaterThan(0);
    expect(r.every((i) => falten(i.name + i.group).includes('roastbeef'))).toBe(true);
    expect(filtern(alle, { q: alle[0].code, bereich: null, nurMerkliste: false, merkliste: new Set() }).some((i) => i.id === alle[0].id)).toBe(true);
    const b = angebot.sections[1];
    expect(filtern(alle, { q: '', bereich: b, nurMerkliste: false, merkliste: new Set() }).every((i) => i.section === b)).toBe(true);
    expect(filtern(alle, { q: '', bereich: null, nurMerkliste: true, merkliste: new Set([alle[3].key]) }).map((i) => i.id)).toEqual([alle[3].id]);
    expect(falten('Hüfte Größe')).toBe('hufte grosse');
  });
});

describe('Bestellwunsch', () => {
  test('Mengen lesen wie die Website', () => {
    expect(mengeLesen('12,5')).toBe(12.5);
    expect(mengeLesen('1.234,5')).toBe(1234.5);
    expect(mengeLesen('')).toBe(0);
    expect(mengeLesen('12,345')).toBeNaN();
    expect(mengeLesen('100000')).toBeNaN();
    expect(mengeLesen('-1')).toBeNaN();
    expect(mengeText(12.5)).toBe('12,5');
  });
  test('setzen: 0 entfernt, Rundung auf 0,01', () => {
    let w = setzen({}, 'a', 1.234);
    expect(w).toEqual({ a: 1.23 });
    w = setzen(w, 'a', 0);
    expect(w).toEqual({});
  });
  test('Summen in Cent wie der Server, Anfragepreise gezählt, Fehlende gemeldet', () => {
    const { angebot } = aufbereiten({ offer: seedOffer(), fracht: FRACHT });
    const it = angebot.items.find((i) => i.price.status === 'value')!;
    const s = summen({ [it.id]: 3.33, weg: 1 }, angebot.items);
    expect(s.summe).toBe(zeilenSumme(it.price.value!, 3.33));
    expect(s.kg).toBe(3.33);
    expect(s.fehlend).toEqual(['weg']);
    expect(zeilenSumme(10.995, 3)).toBe(33);   // 1100 Cent × 3
  });
  test('Fracht wie lib/fracht.php', () => {
    expect(frachtFuer(FRACHT, 120)).toEqual({ kosten: 35, unter: 200, frei: 300 });
    expect(frachtFuer(FRACHT, 200)).toEqual({ kosten: 30, unter: 300, frei: 300 });
    expect(frachtFuer(FRACHT, 300)).toEqual({ kosten: 0, unter: null, frei: 300 });
    expect(frachtFuer({ ...FRACHT, aktiv: false }, 10).kosten).toBe(0);
    expect(frachtFuer(FRACHT, 0).kosten).toBe(0);
  });
  test('Übermittlungskennung: gleiche Daten → gleiche Kennung, andere Daten → neue', () => {
    const p1 = nutzdaten({ angebot: 'std', publishedAt: 't', termin: '', referenz: 'A', bemerkung: '' }, { x: 1 });
    let n = 0;
    const neu = () => 'k' + (++n);
    const v1 = versuchFuer(null, p1, neu);
    expect(versuchFuer(v1, JSON.parse(JSON.stringify(p1)), neu).key).toBe(v1.key);
    expect(versuchFuer(v1, { ...p1, referenz: 'B' }, neu).key).not.toBe(v1.key);
    expect(fingerabdruck(p1)).toBe(fingerabdruck(JSON.parse(JSON.stringify(p1))));
  });
  test('Wunschtermin TT.MM.JJJJ', () => {
    expect(terminLesen('')).toBe('');
    expect(terminLesen('5.1.2027')).toBe('2027-01-05');
    expect(terminLesen('31.02.2027')).toBeNull();
    expect(terminLesen('2027-01-05')).toBeNull();
  });
});

describe('Versionen und Status', () => {
  test('Vergleich', () => {
    expect(versionVergleich('1.0.0', '1.0.0')).toBe(0);
    expect(versionVergleich('1.2.0', '1.10.0')).toBe(-1);
    expect(zuAlt('1.0.0', '1.0.1')).toBe(true);
    expect(zuAlt('1.1.0', '1.0.9')).toBe(false);
    expect(zuAlt('1.0.0', null)).toBe(false);
  });
  test('Statusübergänge wie orders.php', () => {
    const php: string = fs.readFileSync(path.join(__dirname, '../../app/api/orders.php'), 'utf8');
    const m = /\$allowed = \[(.*?)\];/.exec(php)!;
    const server = JSON.parse('{' + m[1].replace(/'/g, '"').replace(/=>/g, ':') + '}');
    expect(server).toEqual(UEBERGAENGE);
  });
});
