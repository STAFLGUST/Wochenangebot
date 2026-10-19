/* Angebot aufbereiten: gleicher Kern wie die Website (app/assets/offer-core.js), damit Merklisten-Schlüssel,
   Reihenfolge und Merkmale übereinstimmen. Hier nur Anzeige, Suche und Formatierung. */
// eslint-disable-next-line @typescript-eslint/no-require-imports
const OfferCore = require('../../../app/assets/offer-core.js');

export type Preis = { status: 'value' | 'request' | 'none'; value?: number; label?: string; raw?: string };
export type Artikel = {
  id: string; code: string; name: string; category: string; origin: string | null; condition: string; groupId: string;
  price: Preis; altPrices: Preis[]; sale?: boolean; regular?: number;
  // aus enrichOffer
  group: string; section: string; features: string[]; brand: string | null; key: string; order: number;
};
export type Gruppe = { id: string; name: string; section: string; count: number };
export type Fracht = { aktiv: boolean; frei: number | null; staffeln: { unter: number; kosten: number }[]; hinweis: string[] };
export type Angebot = {
  meta: { title?: string; week?: number; year?: number; offerId?: string; offerName?: string; weekStart?: string; weekEnd?: string };
  sections: string[]; groups: Gruppe[]; items: Artikel[]; publishedAt: string;
};
export type AngebotAntwort = { offer: any; fracht: Fracht; company?: string };

export const ZUSTAND: Record<string, string> = OfferCore.CONDITION_LABELS;

export function aufbereiten(antwort: AngebotAntwort): { angebot: Angebot; fracht: Fracht } {
  const e = OfferCore.enrichOffer(antwort.offer);
  return {
    angebot: { meta: e.meta, sections: e.sections, groups: e.groups, items: e.items, publishedAt: String(antwort.offer.publishedAt || antwort.offer.savedAt || '') },
    fracht: antwort.fracht || { aktiv: false, frei: null, staffeln: [], hinweis: [] },
  };
}

/* ---------- Zahlen (ohne Intl, damit es auf allen Geräten gleich aussieht) ---------- */
function gruppiert(n: string): string { return n.replace(/\B(?=(\d{3})+(?!\d))/g, '.'); }
export function zahl(v: number, min = 0, max = 2): string {
  if (!Number.isFinite(v)) return '–';
  const neg = v < 0; const a = Math.abs(v);
  let s = a.toFixed(max);
  if (max > min) s = s.replace(new RegExp('0{1,' + (max - min) + '}$'), '');
  s = s.replace(/\.$/, '');
  const [i, f] = s.split('.');
  return (neg ? '−' : '') + gruppiert(i) + (f ? ',' + f : '');
}
export const preisZahl = (v: number) => zahl(v, 2, 3);
export const euro = (v: number) => zahl(v, 2, 2) + ' €';
export const kg = (v: number) => zahl(v, 0, 2);

export function preisText(p: Preis | undefined): string {
  if (!p) return '–';
  return p.status === 'value' && typeof p.value === 'number' ? preisZahl(p.value) : p.status === 'request' ? 'auf Anfrage' : '–';
}
export function titel(a: Angebot): string {
  const m = a.meta || {};
  return m.title || (m.week ? `Freibleibendes Angebot für die KW ${m.week}${m.year ? ' – ' + m.year : ''}` : 'Angebot');
}
/** „Fleischmeister“ weglassen, wenn Gruppe oder Bereich die Marke schon nennen (wie Website) */
export function anzeigeName(it: Pick<Artikel, 'name' | 'group' | 'section'>): string {
  if (!/fleischmeister/i.test((it.group || '') + ' ' + (it.section || ''))) return it.name;
  const n = it.name.replace(/(\s*,\s*|\s+)?[„"“]?fleischmeister[“"”]?/gi, '').replace(/\s+,/g, ',').replace(/,\s*,/g, ',').replace(/^[\s,]+|[\s,]+$/g, '').replace(/\s{2,}/g, ' ');
  return n || it.name;
}
export function datum(iso: string | undefined | null): string {
  if (!iso) return '';
  const tag = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (tag) return `${tag[3]}.${tag[2]}.${tag[1]}`;
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${p(d.getDate())}.${p(d.getMonth() + 1)}.${d.getFullYear()}`;
}
export function datumZeit(iso: string | undefined | null): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return '';
  const p = (n: number) => String(n).padStart(2, '0');
  return `${datum(iso)}, ${p(d.getHours())}:${p(d.getMinutes())} Uhr`;
}

/* ---------- Suche ---------- */
const FOLD: Record<string, string> = { 'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 'ss', 'é': 'e', 'è': 'e', 'á': 'a', 'à': 'a', 'ó': 'o', 'í': 'i', 'ú': 'u', 'ç': 'c', 'ñ': 'n' };
export const falten = (s: string) => s.toLowerCase().replace(/[äöüßéèáàóíúçñ]/g, (c) => FOLD[c] || c).replace(/[„“”"]/g, '');

export type Filter = { q: string; bereich: string | null; nurMerkliste: boolean; merkliste: Set<string> };
export function filtern(items: Artikel[], f: Filter): Artikel[] {
  const words = falten(f.q).split(/\s+/).filter(Boolean);
  return items.filter((it) => {
    if (f.bereich && it.section !== f.bereich) return false;
    if (f.nurMerkliste && !f.merkliste.has(it.key)) return false;
    if (!words.length) return true;
    const hay = falten([it.code, it.name, it.group, it.section, it.category, ZUSTAND[it.condition] || '', it.features.join(' '), it.brand || '', it.sale ? 'sonderposten' : ''].join(' '));
    return words.every((w) => hay.includes(w));
  });
}

export type Abschnitt = { titel: string; bereich: string; gruppeId: string; data: Artikel[] };
/** Liste in Gruppen (für SectionList): Reihenfolge wie im Angebot */
export function abschnitte(a: Angebot, items: Artikel[]): Abschnitt[] {
  const by = new Map<string, Artikel[]>();
  for (const it of items) { const l = by.get(it.groupId); if (l) l.push(it); else by.set(it.groupId, [it]); }
  return a.groups.filter((g) => by.has(g.id)).map((g) => ({ titel: g.name, bereich: g.section, gruppeId: g.id, data: by.get(g.id)! }));
}
