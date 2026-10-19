/* Anmeldung und Verbindung: Server, Grunddaten (app_info), angemeldeter Kunde oder Mitarbeiter.
   Kunden und Mitarbeiter nutzen die vorhandenen Aktionen der Website (kunde_login, login, login_2fa …). */
import Constants from 'expo-constants';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { Platform } from 'react-native';
import { Api, ApiFehler, Server } from '../kern/api';
import { ablage, geheim } from '../kern/speicher';
import { zuAlt } from '../kern/version';

export const APP_VERSION: string = (Constants.expoConfig && Constants.expoConfig.version) || '1.0.0';
export const SERVER_LIVE = 'https://angebot-stafl.de';
export const SERVER_TEST = 'https://test.angebot-stafl.de';

export type AppInfo = {
  apiVersion: number; minAppVersion: string; company: string; stdPublic: boolean; bestellfunktion: boolean; testumgebung: boolean;
  wartung: { message: string; until: string | null } | null; links: Record<string, string>;
};
export type Kunde = { firma: string; ansprechpartner: string; username: string; mustChange: boolean; angebote: { id: string; name: string }[] };
export type Mitarbeiter = { id: string; username: string; name: string; role: string; mustChange: boolean; needTwofa: boolean; perms: string[] };
export type Rolle = 'gast' | 'kunde' | 'team';

type Ctx = {
  bereit: boolean;
  api: Api;
  server: Server;
  info: AppInfo | null;
  infoFehler: string;
  zuAlt: boolean;
  rolle: Rolle;
  kunde: Kunde | null;
  mitarbeiter: Mitarbeiter | null;
  bestellung: boolean;         // Kunde darf Bestellwünsche senden
  hinweis: string;             // z. B. „Sitzung abgelaufen“
  setHinweis: (s: string) => void;
  neuLaden: () => Promise<void>;
  kundeAnmelden: (u: string, p: string) => Promise<Kunde>;
  kundePasswort: (alt: string, neu: string) => Promise<void>;
  teamAnmelden: (u: string, p: string) => Promise<'code' | 'ok'>;
  teamCode: (code: string) => Promise<void>;
  abmelden: (grund?: string) => Promise<void>;
  serverSetzen: (s: Server) => Promise<void>;
  /** bei 401 einer Folgeanfrage: lokal abmelden */
  abgelaufen: (e: unknown) => boolean;
};

const SitzungCtx = createContext<Ctx | null>(null);
export const useSitzung = () => { const c = useContext(SitzungCtx); if (!c) throw new Error('SitzungProvider fehlt'); return c; };

function standardServer(): Server {
  if (Platform.OS === 'web' && typeof window !== 'undefined' && window.location && /^https?:/.test(window.location.origin)) return { base: window.location.origin };
  return { base: SERVER_LIVE };
}
const sidKey = (base: string) => 'sitzung.' + base.replace(/^https?:\/\//, '');

export function SitzungProvider({ children }: { children: React.ReactNode }) {
  const [server, setServer] = useState<Server>(standardServer);
  const apiRef = useRef<Api>(new Api(server, APP_VERSION));
  const [bereit, setBereit] = useState(false);
  const [info, setInfo] = useState<AppInfo | null>(null);
  const [infoFehler, setInfoFehler] = useState('');
  const [rolle, setRolle] = useState<Rolle>('gast');
  const [kunde, setKunde] = useState<Kunde | null>(null);
  const [mitarbeiter, setMitarbeiter] = useState<Mitarbeiter | null>(null);
  const [bestellung, setBestellung] = useState(false);
  const [hinweis, setHinweis] = useState('');

  const verbinden = useCallback((s: Server) => {
    const api = new Api(s, APP_VERSION);
    api.onSitzung = (sid) => { if (sid) geheim.set(sidKey(s.base), sid); else geheim.del(sidKey(s.base)); };
    apiRef.current = api;
    return api;
  }, []);

  const lokalAbmelden = useCallback(() => {
    setRolle('gast'); setKunde(null); setMitarbeiter(null); setBestellung(false);
    ablage.set('rolle', 'gast');
  }, []);

  const zustandLesen = useCallback(async (api: Api) => {
    let i: AppInfo | null = null;
    try {
      i = await api.call<AppInfo & { ok: true }>('app_info');
      setInfo(i); setInfoFehler('');
    } catch (e) {
      setInfoFehler(e instanceof ApiFehler ? e.message : 'Keine Verbindung zum Server.');
      // ohne Verbindung: zuletzt bekannte Rolle anzeigen (Angebot aus dem Zwischenspeicher)
      const r = await ablage.get<Rolle>('rolle', 'gast');
      const k = await ablage.get<Kunde | null>('kunde', null);
      if (r === 'kunde' && k) { setRolle('kunde'); setKunde(k); }
      return;
    }
    try {
      const st = await api.call<{ kunde: Kunde | null; bestellung: boolean; csrf: string | null }>('kunde_status');
      if (st.kunde) {
        setKunde(st.kunde); setRolle('kunde'); setBestellung(!!st.bestellung && !st.kunde.mustChange);
        ablage.set('rolle', 'kunde'); ablage.set('kunde', st.kunde);
        return;
      }
    } catch { /* weiter prüfen */ }
    if ((await ablage.get<Rolle>('rolle', 'gast')) === 'team') {
      try {
        const st = await api.call<{ loggedIn: boolean; user: Mitarbeiter | null }>('status');
        if (st.loggedIn && st.user) { setMitarbeiter(st.user); setRolle('team'); return; }
      } catch { /* abgemeldet oder Zugriff von hier gesperrt */ }
    }
    lokalAbmelden();
  }, [lokalAbmelden]);

  const start = useCallback(async (s: Server) => {
    const api = verbinden(s);
    api.sid = (await geheim.get(sidKey(s.base))) || '';
    await zustandLesen(api);
    setBereit(true);
  }, [verbinden, zustandLesen]);

  useEffect(() => {
    (async () => {
      const gespeichert = await ablage.get<string | null>('server', null);
      const s: Server = gespeichert ? { base: gespeichert } : standardServer();
      if (gespeichert && gespeichert !== SERVER_LIVE) {
        const b = await geheim.get('basic.' + gespeichert);
        if (b) { try { s.basic = JSON.parse(b); } catch { /* ignorieren */ } }
      }
      setServer(s);
      await start(s);
    })();
  }, [start]);

  const neuLaden = useCallback(async () => { await zustandLesen(apiRef.current); }, [zustandLesen]);

  const kundeAnmelden = useCallback(async (u: string, p: string) => {
    const api = apiRef.current;
    const r = await api.call<{ kunde: Kunde }>('kunde_login', { body: { username: u.trim(), password: p } });
    setHinweis('');
    const st = await api.call<{ kunde: Kunde | null; bestellung: boolean }>('kunde_status');
    const k = st.kunde || r.kunde;
    setKunde(k); setRolle('kunde'); setBestellung(!!st.bestellung && !k.mustChange); setMitarbeiter(null);
    ablage.set('rolle', 'kunde'); ablage.set('kunde', k);
    return k;
  }, []);

  const kundePasswort = useCallback(async (alt: string, neu: string) => {
    const api = apiRef.current;
    const r = await api.call<{ kunde: Kunde }>('kunde_passwort', { body: { current: alt, password: neu } });
    const st = await api.call<{ kunde: Kunde | null; bestellung: boolean }>('kunde_status');
    const k = st.kunde || r.kunde;
    setKunde(k); setBestellung(!!st.bestellung && !k.mustChange); ablage.set('kunde', k);
  }, []);

  const teamFertig = useCallback(async (user: Mitarbeiter) => {
    if (user.mustChange || user.needTwofa) {
      try { await apiRef.current.call('logout', { body: {} }); } catch { /* egal */ }
      apiRef.current.vergessen();
      throw new ApiFehler(user.mustChange
        ? 'Bitte legen Sie zuerst im Eingabebereich der Website ein neues Passwort fest und melden Sie sich dann hier an.'
        : 'Bitte richten Sie zuerst im Eingabebereich der Website die Zwei-Faktor-Anmeldung ein und melden Sie sich dann hier an.', 403);
    }
    setMitarbeiter(user); setRolle('team'); setKunde(null); setBestellung(false); setHinweis('');
    ablage.set('rolle', 'team');
  }, []);

  const teamAnmelden = useCallback(async (u: string, p: string) => {
    const r = await apiRef.current.call<{ need2fa?: boolean; user?: Mitarbeiter }>('login', { body: { username: u.trim(), password: p } });
    if (r.need2fa) return 'code';
    await teamFertig(r.user as Mitarbeiter);
    return 'ok';
  }, [teamFertig]);

  const teamCode = useCallback(async (code: string) => {
    const r = await apiRef.current.call<{ user: Mitarbeiter }>('login_2fa', { body: { code: code.replace(/\s/g, '') } });
    await teamFertig(r.user);
  }, [teamFertig]);

  const abmelden = useCallback(async (grund?: string) => {
    const api = apiRef.current;
    try {
      if (rolle === 'kunde') await api.call('kunde_logout', { body: {} });
      else if (rolle === 'team') await api.call('logout', { body: {} });
    } catch { /* offline: lokal trotzdem abmelden */ }
    api.vergessen();
    lokalAbmelden();
    ablage.del('kunde');
    setHinweis(grund || '');
  }, [rolle, lokalAbmelden]);

  const abgelaufen = useCallback((e: unknown) => {
    if (e instanceof ApiFehler && e.status === 401 && e.code !== 'basic_auth' && rolle !== 'gast') {
      apiRef.current.vergessen();
      lokalAbmelden();
      setHinweis('Ihre Anmeldung ist abgelaufen. Bitte melden Sie sich erneut an.');
      return true;
    }
    return false;
  }, [rolle, lokalAbmelden]);

  const serverSetzen = useCallback(async (s: Server) => {
    await ablage.set('server', s.base);
    if (s.basic && s.basic.user) await geheim.set('basic.' + s.base, JSON.stringify(s.basic)); else await geheim.del('basic.' + s.base);
    lokalAbmelden();
    setServer(s);
    setBereit(false);
    await start(s);
  }, [lokalAbmelden, start]);

  const value = useMemo<Ctx>(() => ({
    bereit, api: apiRef.current, server, info, infoFehler, zuAlt: !!info && zuAlt(APP_VERSION, info.minAppVersion),
    rolle, kunde, mitarbeiter, bestellung, hinweis, setHinweis, neuLaden,
    kundeAnmelden, kundePasswort, teamAnmelden, teamCode, abmelden, serverSetzen, abgelaufen,
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }), [bereit, server, info, infoFehler, rolle, kunde, mitarbeiter, bestellung, hinweis, neuLaden, kundeAnmelden, kundePasswort, teamAnmelden, teamCode, abmelden, serverSetzen, abgelaufen]);

  return <SitzungCtx.Provider value={value}>{children}</SitzungCtx.Provider>;
}
