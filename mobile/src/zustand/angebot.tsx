/* Angebot, Merkliste und Bestellentwurf (Kunden und Gäste).
   Das zuletzt geladene Angebot bleibt auf dem Gerät, damit es auch ohne Netz lesbar ist – mit deutlichem Hinweis,
   dass Preise dann ohne Gewähr sind. Senden geht nur online; der Server prüft Preise und Aktualität erneut. */
import * as Crypto from 'expo-crypto';
import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { ApiFehler } from '../kern/api';
import { Angebot, AngebotAntwort, aufbereiten, Fracht } from '../kern/angebot';
import { Kopf, nutzdaten, setzen, terminLesen, Versuch, versuchFuer, Warenkorb } from '../kern/bestellung';
import { ablage } from '../kern/speicher';
import { useSitzung } from './sitzung';

type Gespeichert = { antwort: AngebotAntwort; geladen: string };
export type Quittung = { nr: string; total: number; totalQty: number; positions: number; onRequest: number;
  fracht: { kosten: number; unter: number | null } | null; copy: string | null; delivery: string; replayed: boolean };

type Ctx = {
  auswahl: { id: string; name: string }[];
  angebotId: string;
  setAngebotId: (id: string) => void;
  angebot: Angebot | null;
  fracht: Fracht | null;
  laedt: boolean;
  fehler: string;
  offline: boolean;            // Anzeige aus dem Zwischenspeicher
  geladen: string;             // Zeitpunkt der Daten (ISO)
  laden: () => Promise<void>;
  merkliste: Set<string>;
  merken: (key: string) => void;
  merklisteLeeren: () => void;
  korb: Warenkorb;
  menge: (id: string, q: number) => void;
  korbLeeren: () => void;
  kopf: Omit<Kopf, 'angebot' | 'publishedAt'>;
  setKopf: (k: Omit<Kopf, 'angebot' | 'publishedAt'>) => void;
  senden: () => Promise<Quittung>;
};
const AngebotCtx = createContext<Ctx | null>(null);
export const useAngebot = () => { const c = useContext(AngebotCtx); if (!c) throw new Error('AngebotProvider fehlt'); return c; };

const LEER_KOPF = { termin: '', referenz: '', bemerkung: '' };

export function AngebotProvider({ children }: { children: React.ReactNode }) {
  const { api, server, rolle, kunde, abgelaufen, bereit, info } = useSitzung();
  const wer = rolle === 'kunde' && kunde ? kunde.username : 'gast';
  const srv = server.base.replace(/^https?:\/\//, '');
  const [angebotId, setAngebotIdState] = useState('std');
  const [daten, setDaten] = useState<{ angebot: Angebot; fracht: Fracht } | null>(null);
  const [laedt, setLaedt] = useState(false);
  const [fehler, setFehler] = useState('');
  const [offline, setOffline] = useState(false);
  const [geladen, setGeladen] = useState('');
  const [merkliste, setMerkliste] = useState<Set<string>>(new Set());
  const [korb, setKorb] = useState<Warenkorb>({});
  const [kopf, setKopfState] = useState(LEER_KOPF);
  const merkTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const merkRemote = useRef(false);

  const cacheKey = `angebot.${srv}.${wer}.${angebotId}`;
  const korbKey = `korb.${srv}.${wer}.${angebotId}`;
  const merkKey = `merkliste.${srv}.${wer}`;
  const versuchKey = `versuch.${srv}.${wer}`;

  // Auswahl: freigeschaltete Angebote des Kunden, dazu das öffentliche Wochenangebot
  const auswahl = useMemo(() => {
    const l = rolle === 'kunde' && kunde ? [...kunde.angebote] : [];
    if ((info?.stdPublic ?? true) && !l.some((o) => o.id === 'std')) l.unshift({ id: 'std', name: 'Wochenangebot' });
    return l.length ? l : [{ id: 'std', name: 'Wochenangebot' }];
  }, [rolle, kunde, info]);
  // gewähltes Angebot je Kunde merken; nur freigeschaltete zulassen
  useEffect(() => {
    if (!bereit) return;
    (async () => {
      const gew = await ablage.get<string>(`angebotwahl.${srv}.${wer}`, 'std');
      setAngebotIdState(auswahl.some((o) => o.id === gew) ? gew : auswahl[0].id);
    })();
  }, [bereit, auswahl, srv, wer]);
  const setAngebotId = useCallback((id: string) => { setAngebotIdState(id); ablage.set(`angebotwahl.${srv}.${wer}`, id); }, [srv, wer]);

  const laden = useCallback(async () => {
    setLaedt(true); setFehler('');
    try {
      const r = await api.call<AngebotAntwort>('offer', { query: { angebot: angebotId === 'std' ? undefined : angebotId } });
      const g: Gespeichert = { antwort: { offer: r.offer, fracht: r.fracht }, geladen: new Date().toISOString() };
      setDaten(aufbereiten(g.antwort)); setGeladen(g.geladen); setOffline(false);
      ablage.set(cacheKey, g);
    } catch (e) {
      if (abgelaufen(e)) return;
      const g = await ablage.get<Gespeichert | null>(cacheKey, null);
      if (e instanceof ApiFehler && e.offline && g) {
        setDaten(aufbereiten(g.antwort)); setGeladen(g.geladen); setOffline(true);
      } else {
        setFehler(e instanceof Error ? e.message : 'Das Angebot konnte nicht geladen werden.');
        if (!(e instanceof ApiFehler && e.offline)) setDaten(null);
      }
    } finally {
      setLaedt(false);
    }
  }, [api, angebotId, cacheKey, abgelaufen]);

  // Merkliste: angemeldete Kunden auf dem Server (wie Website), Gäste nur auf dem Gerät
  useEffect(() => {
    if (!bereit) return;
    let aus = false;
    (async () => {
      let lokal = await ablage.get<string[]>(merkKey, []);
      // erste Anmeldung auf diesem Gerät: als Gast gemerkte Artikel übernehmen
      if (!lokal.length && rolle === 'kunde') lokal = await ablage.get<string[]>(`merkliste.${srv}.gast`, []);
      if (!aus) setMerkliste(new Set(lokal));
      merkRemote.current = false;
      if (rolle === 'kunde' && kunde && !kunde.mustChange) {
        try {
          const r = await api.call<{ keys: string[]; exists: boolean }>('kunde_merkliste');
          const keys = !r.exists && lokal.length ? lokal : r.keys;
          if (!aus) { setMerkliste(new Set(keys)); merkRemote.current = true; }
          if (!r.exists && lokal.length) api.call('kunde_merkliste_save', { body: { keys } }).catch(() => {});
        } catch { /* offline: lokale Liste */ }
      }
    })();
    return () => { aus = true; };
  }, [bereit, rolle, kunde, api, merkKey, srv]);

  const merklisteSpeichern = useCallback((s: Set<string>) => {
    const keys = [...s];
    ablage.set(merkKey, keys);
    if (!merkRemote.current) return;
    if (merkTimer.current) clearTimeout(merkTimer.current);
    merkTimer.current = setTimeout(() => { api.call('kunde_merkliste_save', { body: { keys } }).catch((e) => abgelaufen(e)); }, 600);
  }, [api, merkKey, abgelaufen]);
  const merken = useCallback((key: string) => {
    setMerkliste((alt) => { const n = new Set(alt); if (n.has(key)) n.delete(key); else n.add(key); merklisteSpeichern(n); return n; });
  }, [merklisteSpeichern]);
  const merklisteLeeren = useCallback(() => { const n = new Set<string>(); setMerkliste(n); merklisteSpeichern(n); }, [merklisteSpeichern]);

  // Bestellentwurf je Kunde und Angebot auf dem Gerät
  useEffect(() => {
    if (!bereit) return;
    (async () => {
      setKorb(await ablage.get<Warenkorb>(korbKey, {}));
      setKopfState(await ablage.get(korbKey + '.kopf', LEER_KOPF));
    })();
  }, [bereit, korbKey]);
  const menge = useCallback((id: string, q: number) => {
    setKorb((alt) => { const n = setzen(alt, id, q); ablage.set(korbKey, n); return n; });
  }, [korbKey]);
  const korbLeeren = useCallback(() => { setKorb({}); ablage.set(korbKey, {}); setKopfState(LEER_KOPF); ablage.set(korbKey + '.kopf', LEER_KOPF); }, [korbKey]);
  const setKopf = useCallback((k: typeof LEER_KOPF) => { setKopfState(k); ablage.set(korbKey + '.kopf', k); }, [korbKey]);

  useEffect(() => { if (bereit) laden(); }, [bereit, laden]);

  const senden = useCallback(async () => {
    if (!daten) throw new ApiFehler('Kein Angebot geladen.', 0);
    if (offline) throw new ApiFehler('Ohne Internetverbindung kann kein Bestellwunsch gesendet werden. Ihr Entwurf bleibt gespeichert.', 0, { offline: true });
    const termin = terminLesen(kopf.termin);
    if (termin === null) throw new ApiFehler('Bitte das Wunschdatum als TT.MM.JJJJ eingeben oder leer lassen.', 422);
    const payload = nutzdaten({ ...kopf, termin, referenz: kopf.referenz.trim(), bemerkung: kopf.bemerkung.trim(), angebot: angebotId, publishedAt: daten.angebot.publishedAt }, korb);
    const alt = await ablage.get<Versuch | null>(versuchKey, null);
    const v = versuchFuer(alt, payload, () => Crypto.randomUUID());
    await ablage.set(versuchKey, v);   // bleibt bis zur Erfolgsantwort – auch wenn die App zwischendurch beendet wird
    try {
      const r = await api.call<Quittung>('kunde_bestellung', { body: { ...payload, requestId: v.key }, timeoutMs: 45000 });
      await ablage.del(versuchKey);
      korbLeeren();
      return r;
    } catch (e) {
      abgelaufen(e);
      throw e;
    }
  }, [api, daten, offline, kopf, angebotId, korb, versuchKey, korbLeeren, abgelaufen]);

  const value = useMemo<Ctx>(() => ({
    auswahl, angebotId, setAngebotId, angebot: daten ? daten.angebot : null, fracht: daten ? daten.fracht : null, laedt, fehler, offline, geladen, laden,
    merkliste, merken, merklisteLeeren, korb, menge, korbLeeren, kopf, setKopf, senden,
  }), [auswahl, angebotId, setAngebotId, daten, laedt, fehler, offline, geladen, laden, merkliste, merken, merklisteLeeren, korb, menge, korbLeeren, kopf, setKopf, senden]);
  return <AngebotCtx.Provider value={value}>{children}</AngebotCtx.Provider>;
}
