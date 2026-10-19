/* Verbindung zur Schnittstelle des Portals (docs/app-api.md).
   Die App nutzt dieselben Sitzungen wie die Website: Die Kennung steht in der Kopfzeile „X-WA-Sitzung“ statt in einem
   Cookie, Schreibzugriffe tragen das CSRF-Kennzeichen der Anmeldung. Preise, Fracht und Rechte prüft nur der Server. */

export const APP_API_VERSION = 1;

export type Server = {
  /** Basisadresse ohne abschließenden Schrägstrich, z. B. https://angebot-stafl.de */
  base: string;
  /** nur für die Testumgebung (vom Nutzer im Gerät eingegeben, nie im Quellcode) */
  basic?: { user: string; pass: string } | null;
};

export class ApiFehler extends Error {
  status: number;
  code?: string;
  wartung: boolean;
  offline: boolean;
  constructor(message: string, status: number, extra: { code?: string; wartung?: boolean; offline?: boolean } = {}) {
    super(message);
    this.name = 'ApiFehler';
    this.status = status;
    this.code = extra.code;
    this.wartung = !!extra.wartung;
    this.offline = !!extra.offline;
  }
}

type Abfrage = Record<string, string | number | undefined | null>;
export type Aufruf = { body?: unknown; query?: Abfrage; timeoutMs?: number };
type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export function base64(s: string): string {
  const bytes = typeof TextEncoder !== 'undefined'
    ? Array.from(new TextEncoder().encode(s), (b) => String.fromCharCode(b)).join('')
    : unescape(encodeURIComponent(s));
  if (typeof btoa === 'function') return btoa(bytes);
  const abc = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/';
  let out = '';
  for (let i = 0; i < bytes.length; i += 3) {
    const n = (bytes.charCodeAt(i) << 16) | ((bytes.charCodeAt(i + 1) || 0) << 8) | (bytes.charCodeAt(i + 2) || 0);
    out += abc[(n >> 18) & 63] + abc[(n >> 12) & 63] + (i + 1 < bytes.length ? abc[(n >> 6) & 63] : '=') + (i + 2 < bytes.length ? abc[n & 63] : '=');
  }
  return out;
}

export function adresse(base: string, action: string, query?: Abfrage): string {
  let url = base.replace(/\/+$/, '') + '/api/?action=' + encodeURIComponent(action);
  for (const [k, v] of Object.entries(query || {})) if (v !== undefined && v !== null && v !== '') url += '&' + encodeURIComponent(k) + '=' + encodeURIComponent(String(v));
  return url;
}

/** Zulässige Serveradresse: https, für Entwicklung auch http auf localhost/privaten Adressen */
export function serverPruefen(raw: string): string | null {
  const s = raw.trim().replace(/\/+$/, '');
  const m = /^(https?):\/\/([^/?#\s]+)$/i.exec(s);
  if (!m) return null;
  const host = m[2].replace(/:\d+$/, '').toLowerCase();
  if (m[1].toLowerCase() === 'http' && !/^(localhost|127\.0\.0\.1|10\.\d+\.\d+\.\d+|192\.168\.\d+\.\d+|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+)$/.test(host)) return null;
  return s;
}

export class Api {
  sid = '';
  csrf = '';
  server: Server;
  version: string;
  private fetchImpl: FetchLike;
  /** wird bei jeder neuen Sitzungskennung aufgerufen (zum sicheren Speichern) */
  onSitzung: (sid: string) => void = () => {};

  constructor(server: Server, version: string, fetchImpl?: FetchLike) {
    this.server = server;
    this.version = version;
    this.fetchImpl = fetchImpl || ((i, init) => fetch(i, init));
  }

  async call<T = Record<string, unknown>>(action: string, opt: Aufruf = {}): Promise<T> {
    const headers: Record<string, string> = { Accept: 'application/json', 'X-WA-Client': 'app', 'X-WA-App-Version': this.version };
    if (this.sid) headers['X-WA-Sitzung'] = this.sid;
    if (this.server.basic && this.server.basic.user) headers.Authorization = 'Basic ' + base64(this.server.basic.user + ':' + this.server.basic.pass);
    const post = opt.body !== undefined;
    if (post) {
      headers['Content-Type'] = 'application/json';
      headers['X-CSRF-Token'] = this.csrf;
    }
    const ctrl = typeof AbortController !== 'undefined' ? new AbortController() : null;
    const timer = ctrl ? setTimeout(() => ctrl.abort(), opt.timeoutMs ?? 20000) : null;
    let res: Response;
    try {
      res = await this.fetchImpl(adresse(this.server.base, action, opt.query), {
        method: post ? 'POST' : 'GET', headers, body: post ? JSON.stringify(opt.body) : undefined,
        credentials: 'omit', cache: 'no-store', signal: ctrl ? ctrl.signal : undefined,
      });
    } catch {
      throw new ApiFehler('Keine Verbindung zum Server. Bitte Internetverbindung prüfen.', 0, { offline: true });
    } finally {
      if (timer) clearTimeout(timer);
    }
    const neu = res.headers.get('x-wa-sitzung');
    if (neu !== null && neu !== this.sid) {
      this.sid = neu.trim();
      this.onSitzung(this.sid);
    }
    let data: any = null;
    try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
    if (data && typeof data.csrf === 'string' && data.csrf) this.csrf = data.csrf;
    // 401 ohne JSON kommt vom vorgeschalteten Kennwortschutz der Testumgebung, nicht von der Schnittstelle
    if (res.status === 401 && !data) throw new ApiFehler('Der Server verlangt eine zusätzliche Anmeldung (Testumgebung). Bitte unter „Server“ Benutzer und Passwort der Testumgebung eintragen.', 401, { code: 'basic_auth' });
    if (!res.ok || !data || data.ok !== true) {
      const msg = data && typeof data.error === 'string' ? data.error : 'Der Server hat nicht wie erwartet geantwortet (' + res.status + ').';
      throw new ApiFehler(msg, res.status, { code: data?.code, wartung: !!data?.wartung });
    }
    return data as T;
  }

  /** Sitzung lokal vergessen (z. B. nach Abmelden) */
  vergessen() {
    this.sid = '';
    this.csrf = '';
    this.onSitzung('');
  }
}
