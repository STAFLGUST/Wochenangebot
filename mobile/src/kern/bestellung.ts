/* Bestellwunsch in der App: Mengen merken, Summen und Frachtanteil als Vorschau.
   Verbindlich rechnet nur der Server (AGENTS.md Regel 10); er prüft auch, ob das Angebot noch aktuell ist. */
import type { Artikel, Fracht } from './angebot';

export type Warenkorb = Record<string, number>;   // Artikel-ID → kg

/** Eingabe „1.234,5“ / „12,5“ / „12.5“ → Zahl; leer → 0; ungültig → NaN (wie Website) */
export function mengeLesen(v: string): number {
  const t = String(v ?? '').trim().replace(/\s/g, '').replace(/\.(?=\d{3}(\D|$))/g, '').replace(',', '.');
  if (t === '') return 0;
  return /^\d{1,5}(\.\d{1,2})?$/.test(t) && +t <= 99999 ? +t : NaN;
}
export function mengeText(q: number | undefined): string {
  if (!q) return '';
  return String(Math.round(q * 100) / 100).replace('.', ',');
}
export function setzen(w: Warenkorb, id: string, q: number): Warenkorb {
  const n = { ...w };
  if (q > 0 && Number.isFinite(q)) n[id] = Math.round(q * 100) / 100; else delete n[id];
  return n;
}
/** in Cent rechnen, wie der Server */
export const zeilenSumme = (preis: number, q: number) => Math.round(Math.round(preis * 100) * q) / 100;

export type Zeile = { it: Artikel; q: number; summe: number | null };
export type Summen = { zeilen: Zeile[]; kg: number; summe: number; anfrage: number; fehlend: string[] };
export function summen(w: Warenkorb, items: Artikel[]): Summen {
  const by = new Map(items.map((i) => [i.id, i]));
  const zeilen: Zeile[] = []; const fehlend: string[] = [];
  let kgSum = 0, summe = 0, anfrage = 0;
  for (const [id, q] of Object.entries(w)) {
    const it = by.get(id);
    if (!it) { fehlend.push(id); continue; }
    const s = it.price.status === 'value' && typeof it.price.value === 'number' ? zeilenSumme(it.price.value, q) : null;
    if (s === null) anfrage++; else summe += s;
    kgSum += q;
    zeilen.push({ it, q, summe: s });
  }
  zeilen.sort((a, b) => a.it.order - b.it.order);
  return { zeilen, kg: Math.round(kgSum * 100) / 100, summe: Math.round(summe * 100) / 100, anfrage, fehlend };
}
/** Frachtanteil wie auf dem Server (lib/fracht.php): kleinste Grenze, die noch über der Menge liegt */
export function frachtFuer(f: Fracht | null | undefined, kgSum: number): { kosten: number; unter: number | null; frei: number | null } {
  if (!f || !f.aktiv || !f.frei || !(kgSum > 0)) return { kosten: 0, unter: null, frei: f && f.aktiv ? f.frei : null };
  let hit: { unter: number; kosten: number } | null = null;
  for (const st of f.staffeln) if (kgSum < st.unter) hit = st;
  return { kosten: hit ? hit.kosten : 0, unter: hit ? hit.unter : null, frei: f.frei };
}

export type Kopf = { angebot: string; publishedAt: string; termin: string; referenz: string; bemerkung: string };
export function nutzdaten(k: Kopf, w: Warenkorb) {
  return { angebot: k.angebot || 'std', publishedAt: k.publishedAt, termin: k.termin, referenz: k.referenz, bemerkung: k.bemerkung,
           positions: Object.entries(w).map(([id, qty]) => ({ id, qty })) };
}
/** Fingerabdruck der Nutzdaten: gleiche Daten → gleiche Übermittlungskennung (Wiederholung ohne Doppelbestellung) */
export function fingerabdruck(payload: unknown): string {
  const s = JSON.stringify(payload);
  let h1 = 0x811c9dc5, h2 = 0x01000193;
  for (let i = 0; i < s.length; i++) {
    const c = s.charCodeAt(i);
    h1 = Math.imul(h1 ^ c, 16777619) >>> 0;
    h2 = Math.imul(h2 + c, 2246822519) >>> 0;
  }
  return h1.toString(16).padStart(8, '0') + h2.toString(16).padStart(8, '0') + s.length.toString(16);
}
export type Versuch = { fp: string; key: string };
/** Kennung je bewusster Übermittlung; bei Netzfehlern mit gleichen Daten wiederverwenden (docs/bestell-api-v1.md) */
export function versuchFuer(alt: Versuch | null, payload: unknown, neueKennung: () => string): Versuch {
  const fp = fingerabdruck(payload);
  return alt && alt.fp === fp ? alt : { fp, key: neueKennung() };
}
/** Wunschdatum: TT.MM.JJJJ → JJJJ-MM-TT (leer erlaubt) */
export function terminLesen(s: string): string | null {
  const t = s.trim();
  if (!t) return '';
  const m = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(t);
  if (!m) return null;
  const d = new Date(Date.UTC(+m[3], +m[2] - 1, +m[1]));
  if (d.getUTCDate() !== +m[1] || d.getUTCMonth() !== +m[2] - 1) return null;
  return d.toISOString().slice(0, 10);
}
