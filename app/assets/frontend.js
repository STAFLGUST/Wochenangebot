/* Wochenangebot – öffentliches Frontend */
(function () {
'use strict';
/* ==========================================================================
   Anwendung
   ========================================================================== */

const { CATEGORY_ORDER, CONDITION_LABELS, PRICE_STATUS_LABELS } = window.OfferCore;
const STORAGE = 'wochenangebot.';
const PREVIEW = new URLSearchParams(location.search).has('vorschau');
/* Kundenangebot (?angebot=edeka): nur nach Anmeldung; ohne Angabe das öffentliche Wochenangebot */
let OFFER = (() => { const v = new URLSearchParams(location.search).get('angebot') || ''; return /^[a-z0-9-]{1,40}$/.test(v) && v !== 'std' ? v : ''; })();
let COMPANY = '';

/* ---------- Hilfsfunktionen ---------- */
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
const icon = (name, cls = '') => `<svg class="i ${cls}" aria-hidden="true"><use href="#i-${name}"/></svg>`;
const plural = (n, one, many) => `${fmtInt.format(n)} ${n === 1 ? one : many}`;

const store = {
  get(k, d) { try { const v = localStorage.getItem(STORAGE + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(STORAGE + k, JSON.stringify(v)); return true; } catch { return false; } },
  del(k) { try { localStorage.removeItem(STORAGE + k); } catch { /* ignore */ } },
};

const fmtNum = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 3 });
const fmtInt = new Intl.NumberFormat('de-DE');
const fmtPct = new Intl.NumberFormat('de-DE', { style: 'percent', maximumFractionDigits: 0 });
const collator = new Intl.Collator('de', { numeric: true, sensitivity: 'base' });
const dmy = (iso) => { const [y, m, d] = iso.split('-'); return `${d}.${m}.${y}`; };
const dm = (iso) => { const [, m, d] = iso.split('-'); return `${d}.${m}.`; };
const today = () => new Date().toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });

const FOLD = { 'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 's', 'é': 'e', 'è': 'e', 'ê': 'e', 'ë': 'e', 'á': 'a', 'à': 'a', 'â': 'a', 'ó': 'o', 'ò': 'o', 'ô': 'o', 'í': 'i', 'ì': 'i', 'î': 'i', 'ï': 'i', 'ú': 'u', 'ù': 'u', 'û': 'u', 'ç': 'c', 'ñ': 'n', 'œ': 'o', 'æ': 'a' };
/* Zeichenweise, längenerhaltende Normalisierung (für Suche und Hervorhebung) */
function fold(s) {
  s = String(s ?? '');
  let o = '';
  for (let i = 0; i < s.length; i++) { const c = s[i].toLowerCase(); const f = FOLD[c] ?? c; o += f.length === 1 ? f : f[0]; }
  return o;
}

const NONE = '__none';
const COND_LABEL = CONDITION_LABELS;
const COND_ORDER = ['frisch', 'gefroren', 'frisch-gefroren', 'dry-aged', 'unbekannt'];
const CAT_CLASS = { 'Rind': 'cat-rind', 'Kalb': 'cat-kalb', 'Schwein': 'cat-schwein', 'Lamm & Schaf': 'cat-lamm', 'Geflügel': 'cat-gefluegel', 'Knochen': 'cat-knochen', 'Sonstiges': 'cat-sonst' };
const CAT_MONO = { 'Rind': 'R', 'Kalb': 'K', 'Schwein': 'S', 'Lamm & Schaf': 'L', 'Geflügel': 'G', 'Knochen': 'Kn', 'Sonstiges': '·' };
const HIGHLIGHT_FEATURES = ['Sonderposten', 'Dry Aged', 'Grain Fed', 'ex chilled', 'Prime Steer', 'Black Angus'];
const SYN_CAT = { 'Rind': 'rindfleisch beef', 'Kalb': 'kalbfleisch', 'Schwein': 'schweinefleisch', 'Lamm & Schaf': 'lammfleisch schaf', 'Geflügel': 'huhn', 'Knochen': '' };
const SYN_ORIGIN = {
  'Neuseeland': 'nz nzl', 'Argentinien': 'arg', 'Deutschland / EU': 'deutschland eu europa', 'Brasilien': 'brasil',
  '4xD': 'deutschland 4 x d', '3xD': 'deutschland 3 x d', 'D': 'deutschland', 'EG': 'eu europa europäische gemeinschaft', 'NZ': 'neuseeland nzl',
  'ARG': 'argentinien', 'UY': 'uruguay', 'PY': 'paraguay', 'BR': 'brasilien brasil', 'AUS': 'australien', 'IRL': 'irland',
  'DK': 'dänemark', 'SCO': 'schottland', 'CA': 'kanada', 'USA': 'usa', 'ES': 'spanien iberico',
};
/* Kürzel → Klartext für Filter und Detailansicht */
const ORIGIN_NAME = {
  '4xD': '4 x Deutschland', '3xD': '3 x Deutschland', 'D': 'Deutschland', 'EG': 'Europäische Gemeinschaft', 'NZ': 'Neuseeland', 'ARG': 'Argentinien',
  'UY': 'Uruguay', 'PY': 'Paraguay', 'BR': 'Brasilien', 'AUS': 'Australien', 'IRL': 'Irland', 'DK': 'Dänemark', 'SCO': 'Schottland', 'CA': 'Kanada', 'USA': 'USA', 'ES': 'Spanien',
};
const SYN_COND = { 'frisch': 'frisch', 'gefroren': 'gefroren gefr tk tiefgekühlt', 'frisch-gefroren': 'frisch gefroren', 'dry-aged': 'dry aged', 'unbekannt': '' };

/* ---------- Daten ---------- */
let DATA, PUBLISHED_AT = null;

function prepare(raw) {
  const items = raw.items.map((it) => {
    const o = { ...it };
    if (it.sale) o.features = [...it.features, 'Sonderposten'];   // Sonderpreis „solange der Vorrat reicht“ (filterbar)
    const p = it.price;
    const priceTerms = [p, ...it.altPrices].map((x) => x.status === 'value' ? fmtNum.format(x.value) : x.status === 'request' ? 'auf anfrage' : 'ohne preis').join(' ');
    /* Suche nur über Nummer, Bezeichnung und echte Artikelmerkmale – nicht über Gruppennamen,
       damit z. B. „Roastbeef“ keine anderen Teilstücke aus der Gruppe „Roastbeef am Knochen“ zeigt */
    o._hay = fold([it.code, it.name, it.nameRaw, it.category, SYN_CAT[it.category], it.origin, SYN_ORIGIN[it.origin],
      COND_LABEL[it.condition], SYN_COND[it.condition], o.features.join(' '), it.sale ? 'sonderpreis restposten' : '', it.brand, priceTerms]
      .filter(Boolean).join(' ¦ '));
    o._cmp = it.category + '|' + it.cut;
    return o;
  });
  const byId = new Map(items.map((i) => [i.id, i]));
  const groupTotal = new Map();
  for (const i of items) groupTotal.set(i.groupId, (groupTotal.get(i.groupId) || 0) + 1);
  const cmpMap = new Map();
  for (const i of items) { if (!cmpMap.has(i._cmp)) cmpMap.set(i._cmp, []); cmpMap.get(i._cmp).push(i); }
  const priced = items.filter((i) => i.price.status === 'value').map((i) => i.price.value);
  return {
    meta: raw.meta, sections: raw.sections, groups: raw.groups, issues: raw.issues || [], items, byId, groupTotal, cmpMap,
    minPrice: priced.length ? Math.min(...priced) : null,
    maxPrice: priced.length ? Math.max(...priced) : null,
  };
}

async function loadData() {
  const res = await fetch('api/?action=offer' + (PREVIEW ? '&draft=1' : '') + (OFFER ? '&angebot=' + encodeURIComponent(OFFER) : ''), { credentials: 'same-origin', cache: 'no-cache' });
  let body = null;
  try { body = await res.json(); } catch { /* keine JSON-Antwort */ }
  if (res.status === 503 && body && body.wartung) throw Object.assign(new Error(body.error), { wartung: { message: body.error, until: body.until } });
  if (res.status === 401 && !PREVIEW) throw Object.assign(new Error('Dieses Angebot ist nur nach Anmeldung sichtbar.'), { needLogin: true });
  if (!res.ok || !body || !body.ok) {
    throw Object.assign(new Error(body && body.error ? body.error : 'Das Angebot konnte nicht geladen werden (' + res.status + ').'), { status: res.status });
  }
  COMPANY = body.company || '';
  PUBLISHED_AT = body.offer.publishedAt || body.offer.savedAt || null;
  DATA = prepare(window.OfferCore.enrichOffer(body.offer));
}

/* ---------- Zustand ---------- */
const FACETS = [
  { id: 'cat', param: 'art', label: 'Fleischart', set: 'cats', get: (i) => i.category },
  { id: 'origin', param: 'herkunft', label: 'Herkunft', set: 'origins', get: (i) => i.origin || NONE },
  { id: 'cond', param: 'zustand', label: 'Zustand', set: 'conds', get: (i) => i.condition },
  { id: 'feat', param: 'merkmal', label: 'Merkmale', set: 'feats', multi: (i) => i.features, pills: true },
  { id: 'pstat', param: 'preis', label: 'Preisangabe', set: 'pstat', get: (i) => i.price.status },
];
const state = {
  q: '', cats: new Set(), origins: new Set(), conds: new Set(), feats: new Set(), pstat: new Set(),
  min: null, max: null, sortKey: 'offer', sortDir: 'asc', view: 'liste', tab: 'all',
};
let favs = new Set(store.get('merkliste', []));
let current = [];
let tokens = [];
let printPrepared = false;

function optionLabel(f, v) {
  if (f.id === 'origin') return v === NONE ? 'Nicht angegeben' : ORIGIN_NAME[v] ? `${v} · ${ORIGIN_NAME[v]}` : v;
  if (f.id === 'cond') return COND_LABEL[v] || v;
  if (f.id === 'pstat') return PRICE_STATUS_LABELS[v] || v;
  return v;
}
function facetOptions(f) {
  const count = new Map();
  for (const it of DATA.items) for (const v of f.multi ? f.multi(it) : [f.get(it)]) count.set(v, (count.get(v) || 0) + 1);
  let vals = [...count.keys()];
  if (f.id === 'cat') vals.sort((a, b) => CATEGORY_ORDER.indexOf(a) - CATEGORY_ORDER.indexOf(b));
  else if (f.id === 'cond') vals.sort((a, b) => COND_ORDER.indexOf(a) - COND_ORDER.indexOf(b));
  else if (f.id === 'pstat') vals.sort((a, b) => ['value', 'request', 'none'].indexOf(a) - ['value', 'request', 'none'].indexOf(b));
  else vals.sort((a, b) => (a === NONE) - (b === NONE) || count.get(b) - count.get(a) || collator.compare(a, b));
  return vals;
}
function activeFilterCount() {
  return FACETS.reduce((n, f) => n + state[f.set].size, 0) + (state.min != null || state.max != null ? 1 : 0);
}
const hasFilters = () => activeFilterCount() > 0 || !!state.q.trim();

/* ---------- Filtern & Sortieren ---------- */
function passes(it, skip) {
  if (state.tab === 'fav' && !favs.has(it.key)) return false;
  if (skip !== 'q') for (const t of tokens) if (!it._hay.includes(t)) return false;
  for (const f of FACETS) {
    if (f.id === skip) continue;
    const sel = state[f.set];
    if (!sel.size) continue;
    if (f.multi) { if (!f.multi(it).some((v) => sel.has(v))) return false; }
    else if (!sel.has(f.get(it))) return false;
  }
  if (skip !== 'range' && (state.min != null || state.max != null)) {
    if (it.price.status !== 'value') return false;
    if (state.min != null && it.price.value < state.min) return false;
    if (state.max != null && it.price.value > state.max) return false;
  }
  return true;
}
const rankP = (i) => ({ value: 0, request: 1, none: 2 })[i.price.status];
function sortItems(list, key = state.sortKey, dir = state.sortDir) {
  const d = dir === 'desc' ? -1 : 1;
  const nullsLast = (a, b, va, vb, cmp) => (!va && !vb ? a.order - b.order : !va ? 1 : !vb ? -1 : d * cmp(va, vb) || a.order - b.order);
  const by = {
    offer: (a, b) => a.order - b.order,
    price: (a, b) => rankP(a) - rankP(b) || (rankP(a) === 0 ? d * (a.price.value - b.price.value) : 0) || a.order - b.order,
    name: (a, b) => d * collator.compare(a.name, b.name) || a.order - b.order,
    code: (a, b) => nullsLast(a, b, a.code, b.code, collator.compare),
    cat: (a, b) => d * (CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category)) || a.order - b.order,
    origin: (a, b) => nullsLast(a, b, a.origin, b.origin, collator.compare),
    cond: (a, b) => d * (COND_ORDER.indexOf(a.condition) - COND_ORDER.indexOf(b.condition)) || a.order - b.order,
  };
  return list.slice().sort(by[key] || by.offer);
}
function compute() {
  tokens = fold(state.q).split(/\s+/).filter(Boolean);
  current = sortItems(DATA.items.filter((i) => passes(i)));
}

/* ---------- Bausteine ---------- */
function hl(text, toks = tokens) {
  text = String(text ?? '');
  if (!toks.length) return esc(text);
  const f = fold(text);
  const on = new Uint8Array(text.length);
  for (const t of toks) for (let i = f.indexOf(t); i !== -1; i = f.indexOf(t, i + 1)) on.fill(1, i, i + t.length);
  let out = '', open = false;
  for (let i = 0; i < text.length; i++) {
    if (on[i] && !open) { out += '<mark>'; open = true; }
    if (!on[i] && open) { out += '</mark>'; open = false; }
    out += esc(text[i]);
  }
  return out + (open ? '</mark>' : '');
}
const monoHTML = (cat, cls = '') => `<span class="mono ${cls} ${CAT_CLASS[cat] || 'cat-sonst'}" aria-hidden="true">${esc(CAT_MONO[cat] || '·')}</span>`;
const condBadge = (c) => `<span class="badge cond-${c}">${esc(COND_LABEL[c] || c)}</span>`;
function starHTML(it) {
  const on = favs.has(it.key);
  return `<button type="button" class="star" data-fav="${esc(it.key)}" aria-pressed="${on}" aria-label="${on ? 'Von der Merkliste entfernen' : 'Auf die Merkliste setzen'}: ${esc(it.name)}" title="${on ? 'Von der Merkliste entfernen' : 'Merken'}">${icon('star')}</button>`;
}
function tagHTML(it, withBrand) {
  const t = HIGHLIGHT_FEATURES.filter((f) => it.features.includes(f)).map((f) => `<span class="tag${f === 'Sonderposten' ? ' sale' : ''}">${esc(f)}</span>`);
  if (withBrand && it.brand) t.unshift(`<span class="tag brand">${esc(it.brand)}</span>`);
  return t.length ? `<div class="tags">${t.join('')}</div>` : '';
}
function priceMain(p) {
  if (p.status === 'value') return `<span class="pv">${fmtNum.format(p.value)}</span><span class="pu">€/kg</span>`;
  if (p.status === 'request') return '<span class="p-req">auf Anfrage</span>';
  return `<span class="p-none" title="In der Angebotsliste ohne Preis${p.raw ? ' („' + esc(p.raw) + '“)' : ''}">ohne Preis</span>`;
}
const priceShort = (p) => (p.status === 'value' ? fmtNum.format(p.value) + ' €/kg' : p.status === 'request' ? 'auf Anfrage' : 'ohne Preis');
function priceHTML(it) {
  if (it.sale) {
    return `<span class="price sale" title="Sonderposten – solange der Vorrat reicht">${it.regular != null ? `<s class="p-was">${fmtNum.format(it.regular)} €/kg</s>` : ''}<span>${priceMain(it.price)}</span><span class="sale-note">solange der Vorrat reicht</span></span>`;
  }
  const main = `<span>${it.price.label ? `<span class="pl">${esc(it.price.label)}</span>` : ''}${priceMain(it.price)}</span>`;
  const alts = it.altPrices.map((p) => `<span class="p-alt"><span class="pl">${esc(p.label)}</span>${esc(priceShort(p))}</span>`).join('');
  return `<span class="price">${main}${alts}</span>`;
}

/* ---------- Kopf, Kennzahlen, Navigation ---------- */
function renderStatic() {
  const m = DATA.meta;
  const kw = m.week ? `KW ${esc(m.week)}${m.year ? `<span class="opt-sm"> · ${esc(m.year)}</span>` : ''}` : 'KW ?';
  document.title = `${offerTitle()} ${m.week ? 'KW ' + m.week + ' ' + (m.year || '') : ''}`.trim() + (COMPANY ? ' – ' + COMPANY : '');
  if (OFFER) { const h = $('#topbar h1'); if (h && h.firstChild && h.firstChild.nodeType === 3) h.firstChild.textContent = offerTitle() + ' '; }
  $('#company').textContent = COMPANY;
  $('#company').hidden = !COMPANY;
  const ini = COMPANY.split(/[\s-]+/).filter((w) => /^[A-Za-zÄÖÜäöü]/.test(w)).slice(0, 2).map((w) => w[0].toUpperCase()).join('');
  $('.brand-mark').textContent = ini || 'W';
  $('#kw-pill').innerHTML = kw;

  const sub = [];
  sub.push(`<span><span class="dot"></span><strong>${esc(m.notice || 'Angebot')}</strong><span class="opt-sm">${m.week ? ` für KW ${m.week}${m.year ? '/' + m.year : ''}` : ''}</span></span>`);
  if (m.weekStart) sub.push(`<span><span class="opt-sm">Angebotswoche: </span>Mo ${dm(m.weekStart)} – So ${dmy(m.weekEnd)}</span>`);
  sub.push('<span class="opt-sm">Preise in € je kg</span>');
  sub.push(`<span class="opt-sm"><strong>${fmtInt.format(DATA.items.length)}</strong> Artikel</span>`);
  $('#subbar').innerHTML = sub.join('');

  const items = DATA.items;
  const cats = CATEGORY_ORDER.filter((c) => items.some((i) => i.category === c));
  $('#quicknav').innerHTML = cats.map((c) => {
    const n = items.filter((i) => i.category === c).length;
    return `<button type="button" class="qn" data-cat="${esc(c)}" aria-pressed="false">${monoHTML(c)}${esc(c)} <span class="n">${n}</span></button>`;
  }).join('');

  const stand = PUBLISHED_AT ? new Date(PUBLISHED_AT).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
  $('#foot').innerHTML = `
    <p>${esc(m.notice || 'Angebot')} · Preise in € je kg${stand ? ` · Stand: ${esc(stand)} Uhr` : ''}</p>
    <p>${esc(COMPANY)}</p>`;

  renderBanner();
  buildFilters();
}

function offerTitle() { return (DATA && DATA.meta && DATA.meta.offerName) || 'Wochenangebot'; }
function renderBanner() {
  const b = $('#preview-banner');
  if (!PREVIEW && KUNDE) {
    const list = KUNDE.angebote;
    b.hidden = false;
    const own = list.some((o) => o.id === (OFFER || 'std'));
    b.innerHTML = `<div class="banner-inner k-banner">${icon('user')}<p>Angemeldet als <strong>${esc(KUNDE.firma)}</strong>${KUNDE.ansprechpartner ? ' · ' + esc(KUNDE.ansprechpartner) : ''}${!own && list.length ? ' – dieses Angebot ist nicht für Sie freigeschaltet; Bestellen ist nur in Ihren Angeboten möglich.' : ''}</p>
      ${!own && list.length === 1 ? `<div class="k-switch"><button type="button" class="btn sm on" data-kswitch="${esc(list[0].id)}">Zu ${esc(list[0].name)}</button></div>` : ''}
      ${list.length > 1 ? `<div class="k-switch" role="tablist" aria-label="Angebot wählen">${list.map((o) => `<button type="button" role="tab" class="btn sm${o.id === (OFFER || 'std') ? ' on' : ''}" aria-selected="${o.id === (OFFER || 'std')}" data-kswitch="${esc(o.id)}">${esc(o.name)}</button>`).join('')}</div>` : ''}</div>`;
    return;
  }
  if (!PREVIEW && OFFER) {
    b.hidden = false;
    b.innerHTML = `<div class="banner-inner">${icon('info')}<p><strong>${esc(offerTitle())}</strong> – Kundenangebot, nur für angemeldete Nutzer sichtbar.</p></div>`;
    return;
  }
  if (!PREVIEW) { b.hidden = true; return; }
  b.hidden = false;
  b.innerHTML = `<div class="banner-inner">${icon('info')}<p><strong>Vorschau des Entwurfs${OFFER ? ' · ' + esc(offerTitle()) : ''}</strong> – diese Fassung ist noch nicht veröffentlicht und nur für angemeldete Bearbeiter sichtbar.</p>
    <div class="banner-actions"><a class="btn sm" href="admin/">Zurück zum Eingabebereich</a></div></div>`;
}

/* ---------- Filter-Panel ---------- */
/* Desktop: jede Filtergruppe als Aufklappmenü in der Leiste über der Liste; schmale Fenster: alle offen in der Seitenleiste */
const mqDrawer = window.matchMedia('(max-width: 1024px)');
const fdrop = (id, label, inner) => `<details class="fdrop" data-fd="${id}"><summary><span class="fd-l">${esc(label)}</span><span class="fd-val"></span>${icon('chev', 'sm')}</summary><div class="fd-pop">${inner}</div></details>`;
function syncDrops() { for (const d of $$('.fdrop')) d.open = mqDrawer.matches; }
function buildFilters() {
  const parts = FACETS.map((f) => {
    const vals = facetOptions(f);
    for (const v of [...state[f.set]]) if (!vals.includes(v)) state[f.set].delete(v);
    if (f.pills) {
      return fdrop(f.id, f.label, `<fieldset class="facet" data-facet="${f.id}"><legend>${esc(f.label)}</legend><div class="pills">${vals.map((v) =>
        `<button type="button" class="pill" data-facet="${f.id}" data-value="${esc(v)}" aria-pressed="${state[f.set].has(v)}">${esc(optionLabel(f, v))} <span class="n" data-n></span></button>`).join('')}</div></fieldset>`);
    }
    return fdrop(f.id, f.label, `<fieldset class="facet" data-facet="${f.id}"><legend>${esc(f.label)}</legend>${vals.map((v) =>
      `<label class="opt"><input type="checkbox" data-facet="${f.id}" value="${esc(v)}"${state[f.set].has(v) ? ' checked' : ''}><span class="lbl">${esc(optionLabel(f, v))}</span><span class="n" data-n></span></label>`).join('')}</fieldset>`);
  });
  const span = DATA.minPrice != null ? `Spanne im Angebot: ${fmtNum.format(DATA.minPrice)} – ${fmtNum.format(DATA.maxPrice)} €/kg` : '';
  parts.splice(4, 0, fdrop('price', 'Preis je kg', `<fieldset class="facet"><legend>Preis je kg</legend>
    <div class="range">
      <div class="field"><input id="pmin" inputmode="decimal" autocomplete="off" placeholder="von" aria-label="Mindestpreis in Euro je Kilogramm" value="${state.min != null ? fmtNum.format(state.min) : ''}"><span class="unit">€</span></div>
      <span aria-hidden="true">–</span>
      <div class="field"><input id="pmax" inputmode="decimal" autocomplete="off" placeholder="bis" aria-label="Höchstpreis in Euro je Kilogramm" value="${state.max != null ? fmtNum.format(state.max) : ''}"><span class="unit">€</span></div>
    </div><p class="hint" id="price-hint" data-default="${esc(span)}">${esc(span)}</p></fieldset>`));
  $('#filters-body').innerHTML = parts.join('');
  syncDrops();
}

function updateFacetUI() {
  for (const f of FACETS) {
    const base = DATA.items.filter((i) => passes(i, f.id));
    const count = new Map();
    for (const it of base) for (const v of f.multi ? f.multi(it) : [f.get(it)]) count.set(v, (count.get(v) || 0) + 1);
    for (const el of $$(`input[data-facet="${f.id}"], .pill[data-facet="${f.id}"]`, $('#filters-body'))) {
      const val = el.tagName === 'INPUT' ? el.value : el.dataset.value;
      const n = count.get(val) || 0;
      const sel = state[f.set].has(val);
      const wrap = el.tagName === 'INPUT' ? el.closest('.opt') : el;
      wrap.querySelector('[data-n]').textContent = n;
      wrap.classList.toggle('zero', !n && !sel);
      if (el.tagName === 'INPUT') el.checked = sel; else el.setAttribute('aria-pressed', sel);
    }
  }
  for (const f of FACETS) {
    const d = $(`.fdrop[data-fd="${f.id}"]`);
    if (!d) continue;
    const sel = [...state[f.set]];
    d.classList.toggle('on', sel.length > 0);
    d.querySelector('.fd-val').textContent = sel.length === 1 ? optionLabel(f, sel[0]) : sel.length ? String(sel.length) : '';
  }
  const dp = $('.fdrop[data-fd="price"]');
  if (dp) {
    dp.classList.toggle('on', state.min != null || state.max != null);
    dp.querySelector('.fd-val').textContent = state.min != null || state.max != null ? `${state.min != null ? fmtNum.format(state.min) : '…'}–${state.max != null ? fmtNum.format(state.max) : '…'} €` : '';
  }
  const n = activeFilterCount();
  $('#btn-reset').disabled = !n;
  const fc = $('#filter-count');
  fc.hidden = !n; fc.textContent = n;
  $('#btn-filters-apply').textContent = `${plural(current.length, 'Treffer', 'Treffer')} anzeigen`;

  for (const b of $$('.qn')) b.setAttribute('aria-pressed', state.cats.size === 1 && state.cats.has(b.dataset.cat));
}

/* ---------- Ergebnisliste ---------- */
function describeFilters() {
  const parts = [];
  if (state.q.trim()) parts.push(`Suche „${state.q.trim()}“`);
  for (const f of FACETS) if (state[f.set].size) parts.push(`${f.label}: ${[...state[f.set]].map((v) => optionLabel(f, v)).join(', ')}`);
  if (state.min != null || state.max != null) parts.push(`Preis ${state.min != null ? fmtNum.format(state.min) : '…'}–${state.max != null ? fmtNum.format(state.max) : '…'} €/kg`);
  if (state.tab === 'fav') parts.unshift('Merkliste');
  return parts.join(' · ');
}

function renderChips() {
  const chips = [];
  if (state.q.trim()) chips.push({ k: 'q', t: `<b>Suche:</b> „${esc(state.q.trim())}“` });
  for (const f of FACETS) for (const v of state[f.set]) chips.push({ k: f.id, v, t: `<b>${esc(f.label)}:</b> ${esc(optionLabel(f, v))}` });
  if (state.min != null || state.max != null) chips.push({ k: 'range', t: `<b>Preis:</b> ${state.min != null ? fmtNum.format(state.min) : '…'} – ${state.max != null ? fmtNum.format(state.max) : '…'} €/kg` });
  $('#chips').innerHTML = chips.map((c) => `<span class="chip">${c.t}<button type="button" data-chip="${c.k}" data-value="${esc(c.v ?? '')}" aria-label="Filter entfernen">${icon('x', 'sm')}</button></span>`).join('') +
    (chips.length > 1 ? '<button type="button" class="link-btn" data-act="reset-all" style="font-size:12.5px">Alle zurücksetzen</button>' : '');
}

function renderHits() {
  const n = current.length, total = DATA.items.length;
  const q = state.q.trim();
  let html;
  if (state.tab === 'fav') html = `<strong>${fmtInt.format(n)}</strong> ${n === 1 ? 'gemerkter Artikel' : 'gemerkte Artikel'}${hasFilters() ? ' (gefiltert)' : ''}`;
  else if (n === total && !hasFilters()) html = `<strong>${fmtInt.format(total)}</strong> Artikel`;
  else html = `<strong>${fmtInt.format(n)}</strong> von ${fmtInt.format(total)} Artikeln${q ? ` für „${esc(q)}“` : ''}`;
  $('#hits').innerHTML = html;
}

function renderFavbar() {
  const bar = $('#favbar');
  if (state.tab !== 'fav') { bar.hidden = true; return; }
  const present = DATA.items.filter((i) => favs.has(i.key)).length;
  const missing = [...favs].filter((k) => !DATA.items.some((i) => i.key === k)).length;
  bar.hidden = false;
  bar.innerHTML = `<span>${plural(present, 'Artikel', 'Artikel')} auf Ihrer Merkliste – ${favRemote ? 'gespeichert in Ihrem Kundenkonto (auf allen Geräten)' : 'gespeichert in diesem Browser'}.${missing ? ` ${plural(missing, 'gemerkter Artikel ist', 'gemerkte Artikel sind')} in dieser Woche nicht im Angebot. <button type="button" class="link-btn" data-act="fav-prune">Entfernen</button>` : ''}</span>
    <span class="favbar-actions">
      <button type="button" class="btn sm" data-act="fav-print"${present ? '' : ' disabled'}>${icon('print', 'sm')}Drucken</button>
      <button type="button" class="btn sm" data-act="fav-csv"${present ? '' : ' disabled'}>${icon('file', 'sm')}CSV</button>
      <button type="button" class="btn sm ghost" data-act="fav-clear"${favs.size ? '' : ' disabled'}>${icon('trash', 'sm')}Leeren</button>
    </span>`;
}

function thHTML(key, label, cls) {
  const active = state.sortKey === key;
  const aria = active ? ` aria-sort="${state.sortDir === 'asc' ? 'ascending' : 'descending'}"` : '';
  return `<th class="${cls}" scope="col"${aria}><button type="button" data-sort="${key}" title="Nach ${esc(label)} sortieren">${esc(label)}${icon(active && state.sortDir === 'desc' ? 'sort' : 'sort-up', 'sm sort-ind')}</button></th>`;
}

function groupHeaderInfo(list) {
  const shown = new Map();
  for (const i of list) shown.set(i.groupId, (shown.get(i.groupId) || 0) + 1);
  return (gid) => { const s = shown.get(gid) || 0, t = DATA.groupTotal.get(gid) || 0; return s === t ? plural(t, 'Artikel', 'Artikel') : `${s} von ${t} Artikeln`; };
}

function renderTable(list, grouped) {
  const info = groupHeaderInfo(list);
  const rows = [];
  let sec = null, grp = null;
  for (const it of list) {
    if (grouped) {
      if (it.section !== sec) { sec = it.section; if (sec) rows.push(`<tr class="s-row"><th colspan="${KORDER ? 8 : 7}" scope="colgroup"><div class="s-in">${esc(sec)}</div></th></tr>`); }
      if (it.groupId !== grp) { grp = it.groupId; rows.push(`<tr class="g-row"><th colspan="${KORDER ? 8 : 7}" scope="colgroup"><div class="g-in"><span class="g-name">${esc(it.group)}</span><span class="g-meta">${info(grp)}</span></div></th></tr>`); }
    }
    rows.push(`<tr class="row" data-id="${it.id}">
      <td class="c-fav">${starHTML(it)}</td>
      <td class="c-code">${it.code ? hl(it.code) : '<span class="muted" title="Ohne Artikelnummer">—</span>'}</td>
      <td class="c-name"><button type="button" class="name-btn" data-open="${it.id}" title="Details und Preisvergleich anzeigen">${hl(it.name)}</button>
        <div class="m-meta">${esc([it.code, it.category, it.origin, COND_LABEL[it.condition]].filter(Boolean).join(' · '))}</div>${tagHTML(it, !grouped)}</td>
      <td class="c-cat"><span class="cat-cell">${monoHTML(it.category)}${esc(it.category)}</span></td>
      <td class="c-origin">${it.origin ? hl(it.origin) : '<span class="muted" title="In der Liste nicht angegeben">—</span>'}${grouped ? '' : `<div class="sub">${esc(it.group)}</div>`}</td>
      <td class="c-cond">${condBadge(it.condition)}</td>
      <td class="c-price">${priceHTML(it)}</td>${KORDER ? `<td class="c-qty">${qtyHTML(it)}</td>` : ''}</tr>`);
  }
  return `<table class="grid"><caption class="sr-only">Artikel der Angebotsliste</caption><thead><tr>
    <th class="c-fav" scope="col"><span class="sr-only">Merken</span></th>
    ${thHTML('code', 'Art.-Nr.', 'c-code')}${thHTML('name', 'Bezeichnung', 'c-name')}${thHTML('cat', 'Fleischart', 'c-cat')}
    ${thHTML('origin', grouped ? 'Herkunft' : 'Herkunft / Gruppe', 'c-origin')}${thHTML('cond', 'Zustand', 'c-cond')}${thHTML('price', 'Preis €/kg', 'c-price')}${KORDER ? '<th class="c-qty" scope="col"><span class="qty-h">Menge kg</span></th>' : ''}
  </tr></thead><tbody>${rows.join('')}</tbody></table>`;
}

/* ---------- Angebotsliste (Standard): Aufbau wie die gedruckte Liste – Abschnitte, Gruppen in Spalten, Nr. · Bezeichnung · € / Kg ---------- */
const plPrice = (p) => (p.status === 'value' ? fmtNum.format(p.value) : p.status === 'request' ? 'a. Anfr.' : '–');
/* Text in Anführungszeichen (z. B. „Fleischmeister“) hervorheben wie in der Druckliste */
const plGroupName = (n) => esc(n).replace(/(&quot;|„|“|”)([^&„“”]{2,40}?)(&quot;|“|”)/g, '<em class="al-brand">„$2“</em>');
/* Preisspalten einer Gruppe: Beschriftungen in Reihenfolge des Auftretens (z. B. Flugware, Schiffsware) */
function plLabels(items) {
  const labels = [];
  // Zusatzpreise links, Hauptpreis rechts – wie in der Druckliste (Flugware | Schiffsware)
  for (const it of items) for (const p of it.altPrices) if (p.label && !labels.includes(p.label)) labels.push(p.label);
  for (const it of items) if (it.price.label && !labels.includes(it.price.label)) labels.push(it.price.label);
  const cols = Math.max(1, labels.length, ...items.map((i) => 1 + i.altPrices.length));
  while (labels.length < cols) labels.push('');
  return labels;
}
function plRow(it, labels) {
  const cells = labels.map(() => null);
  const free = [];
  for (const p of [it.price, ...it.altPrices]) { const k = p.label ? labels.indexOf(p.label) : -1; if (k >= 0 && !cells[k]) cells[k] = p; else free.push(p); }
  for (const p of free) { const k = p === it.price ? cells.lastIndexOf(null) : cells.indexOf(null); if (k >= 0) cells[k] = p; }   // ohne Beschriftung: Hauptpreis rechts
  const td = cells.map((p, i) => `<td class="c-price al-p${p && p.status !== 'value' ? ' al-np' : ''}">${p ? (it.sale && p === it.price ? `${it.regular != null ? `<s class="p-was al-was">${fmtNum.format(it.regular)}</s>` : ''}<span class="al-sale" title="Sonderposten – solange der Vorrat reicht">${plPrice(p)}</span>` : plPrice(p)) : ''}</td>`);
  return `<tr class="row" data-id="${it.id}">
    <td class="c-fav">${starHTML(it)}</td>
    <td class="c-code">${it.code ? hl(it.code) : ''}</td>
    <td class="c-name"><button type="button" class="name-btn" data-open="${it.id}" title="Details und Preisvergleich anzeigen">${hl(it.name)}</button>${it.sale ? '<span class="tag sale al-tag" title="Sonderpreis, solange der Vorrat reicht">Sonderposten</span>' : ''}</td>
    ${td.join('')}${KORDER ? `<td class="c-qty">${qtyHTML(it)}</td>` : ''}</tr>`;
}
function plBlock(title, items) {
  const labels = plLabels(items), cols = labels.length;
  return `<div class="al-grp"><table class="al-tab"><thead><tr class="al-h"><th colspan="3" scope="colgroup">${title}</th><th class="al-eh"${cols > 1 ? ` colspan="${cols}"` : ''}>€ / Kg</th>${KORDER ? '<th class="al-qh"><span class="sr-only">Menge </span>kg</th>' : ''}</tr>
    ${cols > 1 ? `<tr class="al-sub"><th colspan="3"></th>${labels.map((l) => `<th>${esc(l)}</th>`).join('')}${KORDER ? '<th></th>' : ''}</tr>` : ''}</thead>
    <tbody>${items.map((i) => plRow(i, labels)).join('')}</tbody></table></div>`;
}
function renderListe(list, grouped) {
  const m = DATA.meta || {};
  const stand = PUBLISHED_AT ? new Date(PUBLISHED_AT).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '';
  const head = `<div class="al-head"><h2>${esc(m.offerName && m.offerName !== 'Wochenangebot' ? m.offerName + ' · ' : '')}${esc(m.title || (m.week ? `Freibleibendes Angebot für die KW ${m.week}${m.year ? ' - ' + m.year : ''}` : 'Angebot'))}</h2>${stand ? `<span>${esc(stand)}</span>` : ''}</div>`;
  if (!grouped) {
    const lbl = { price: 'Preis', name: 'Bezeichnung', code: 'Artikelnummer', cat: 'Fleischart', origin: 'Herkunft', cond: 'Zustand' }[state.sortKey] || '';
    return `<div class="al">${head}<section class="al-sec"><div class="al-cols al-flow">${plBlock(`Alle Artikel, sortiert nach ${esc(lbl)}`, list)}</div></section></div>`;
  }
  const out = [];
  let sec, buf = [], grp = null, items = [];
  const flushGrp = () => { if (items.length) buf.push(plBlock(plGroupName(items[0].group), items)); items = []; };
  const flushSec = () => { flushGrp(); if (buf.length) out.push(`<section class="al-sec">${sec ? `<h3 class="al-st">${esc(sec)}</h3>` : ''}<div class="al-cols">${buf.join('')}</div></section>`); buf = []; };
  for (const it of list) {
    if (it.section !== sec) { flushSec(); sec = it.section; grp = null; }
    if (it.groupId !== grp) { flushGrp(); grp = it.groupId; }
    items.push(it);
  }
  flushSec();
  return `<div class="al">${head}${out.join('')}</div>`;
}

function cardHTML(it, grouped) {
  const feats = HIGHLIGHT_FEATURES.filter((f) => it.features.includes(f)).map((f) => `<span class="tag${f === 'Sonderposten' ? ' sale' : ''}">${esc(f)}</span>`).join('');
  return `<article class="card" data-id="${it.id}">
    <div class="card-top">${monoHTML(it.category)}<span class="code">${it.code ? 'Art.-Nr. ' + hl(it.code) : 'ohne Art.-Nr.'}</span>${starHTML(it)}</div>
    <h3 class="card-name"><button type="button" class="name-btn" data-open="${it.id}" title="Details und Preisvergleich anzeigen">${hl(it.name)}</button></h3>
    <p class="card-meta">${esc(it.category)}${it.origin ? ' · ' + hl(it.origin) : ''}</p>
    <div class="card-tags">${condBadge(it.condition)}${!grouped && it.brand ? `<span class="tag brand">${esc(it.brand)}</span>` : ''}${feats}</div>
    ${grouped ? '' : `<p class="card-group">${esc(it.group)}</p>`}
    <div class="card-price">${priceHTML(it)}</div>
    ${KORDER ? `<label class="card-qty"><span>Menge kg</span>${qtyHTML(it)}</label>` : ''}
  </article>`;
}

function renderCards(list, grouped) {
  if (!grouped) return `<div class="cards">${list.map((i) => cardHTML(i, false)).join('')}</div>`;
  const info = groupHeaderInfo(list);
  let out = '', sec = null, grp = null, buf = [];
  const flush = () => { if (buf.length) { out += `<div class="cards">${buf.join('')}</div></div>`; buf = []; } };
  for (const it of list) {
    if (it.section !== sec) { flush(); if (sec !== null) out += '</section>'; sec = it.section; grp = null; out += `<section class="cards-section">${sec ? `<h2>${esc(sec)}</h2>` : ''}`; }
    if (it.groupId !== grp) { flush(); grp = it.groupId; out += `<div class="cards-group"><h3>${esc(it.group)} <span>${info(grp)}</span></h3>`; }
    buf.push(cardHTML(it, true));
  }
  flush();
  return out + (sec !== null ? '</section>' : '');
}

function renderEmpty() {
  if (state.tab === 'fav' && !favs.size) {
    return `<div class="empty"><div class="empty-ico">${icon('star')}</div><h3>Ihre Merkliste ist leer</h3>
      <p>Markieren Sie Artikel mit dem Stern, um sie hier zu sammeln, gesammelt auszudrucken oder als CSV zu exportieren.</p>
      <div class="row-actions"><button type="button" class="btn" data-act="tab-all">Zum Angebot</button></div></div>`;
  }
  const q = state.q.trim();
  return `<div class="empty"><div class="empty-ico">${icon('search')}</div><h3>Keine Artikel gefunden</h3>
    <p>${q ? `Für „${esc(q)}“` : 'Für diese Auswahl'}${activeFilterCount() ? ' mit den aktiven Filtern' : ''} gibt es ${state.tab === 'fav' ? 'auf Ihrer Merkliste ' : ''}keine Treffer. Prüfen Sie die Schreibweise oder lockern Sie die Filter.</p>
    <div class="row-actions">${q ? '<button type="button" class="btn" data-act="clear-q">Suche leeren</button>' : ''}${activeFilterCount() ? '<button type="button" class="btn" data-act="reset-filters">Filter zurücksetzen</button>' : ''}</div></div>`;
}

function renderList() {
  const grouped = state.sortKey === 'offer';
  $('#list').innerHTML = !current.length ? renderEmpty() : state.view === 'cards' ? renderCards(current, grouped) : state.view === 'table' ? renderTable(current, grouped) : renderListe(current, grouped);
}

function render() {
  compute();
  renderOrderbar();
  renderHits();
  renderChips();
  updateFacetUI();
  renderFavbar();
  renderList();
  $('#sort').value = `${state.sortKey}-${state.sortDir}`;
  for (const b of $$('.seg button')) b.setAttribute('aria-pressed', b.dataset.view === state.view);
  $('#tab-all').setAttribute('aria-selected', state.tab === 'all');
  $('#tab-fav').setAttribute('aria-selected', state.tab === 'fav');
  $('#q-clear').hidden = !state.q;
  $('#q-kbd').hidden = !!state.q;
  syncUrl();
}

/* ---------- Merkliste ---------- */
function updateFavCount() { $('#fav-count').textContent = DATA.items.filter((i) => favs.has(i.key)).length; renderMerk(); }
/* Merkliste als Spalte neben der Liste (breite Fenster) */
function renderMerk() {
  const host = $('#merk');
  if (!host || !DATA) return;
  const list = DATA.items.filter((i) => favs.has(i.key));
  const shown = list.slice(0, 8);
  const pr = (it) => (it.price.status === 'value' ? fmtNum.format(it.price.value) : it.price.status === 'request' ? 'a. Anfr.' : '–');
  let order = '';
  if (KORDER) {
    const t = cart.size ? cartTotals() : null;
    order = `<div class="merk-order"><div class="merk-h"><h2>Bestellwunsch</h2>${t ? `<span>${plural(t.n, 'Position', 'Positionen')}</span>` : ''}</div>
      ${t ? `<p class="merk-sum">${fmtQty.format(t.kg)} kg · ca. ${fmtEur.format(t.sum)} €${t.req ? ` <span class="muted">+ ${t.req} auf Anfrage</span>` : ''}</p><button type="button" class="btn primary" data-merk="order">${icon('send', 'sm')}Bestellwunsch prüfen</button>`
        : '<p class="merk-hint">Mengen in der Spalte „Menge kg“ eintragen – hier erscheint dann Ihr Bestellwunsch.</p>'}</div>`;
  }
  host.innerHTML = `${order}<div class="merk-h"><h2>Merkliste</h2><span>${plural(list.length, 'Artikel', 'Artikel')}</span></div>
    ${list.length ? `<ul>${shown.map((it) => `<li><button type="button" class="merk-n" data-merk-open="${esc(it.id)}"><span>${esc(it.name)}</span><span class="m-c">${esc(it.code || '')}</span></button><span class="m-p${it.sale ? ' sale' : ''}">${esc(pr(it))}</span></li>`).join('')}</ul>
      ${list.length > shown.length ? `<p class="merk-more">+ ${plural(list.length - shown.length, 'weiterer Artikel', 'weitere Artikel')}</p>` : ''}`
      : '<p class="merk-empty">Noch nichts gemerkt. Mit dem Stern neben einem Artikel kommt er hierher.</p>'}
    <button type="button" class="btn" data-merk="show"${list.length ? '' : ' disabled'}>Merkliste anzeigen</button>`;
}
/* Ohne Anmeldung: Merkliste im Browser. Angemeldete Kunden: im Kundenkonto auf dem Server (auf allen Geräten gleich). */
let favRemote = false, favTimer = null, favBusy = Promise.resolve();
function saveFavs() {
  if (favRemote) {
    clearTimeout(favTimer);
    favTimer = setTimeout(() => {
      const keys = [...favs];
      favBusy = favBusy.then(() => kundeApi('kunde_merkliste_save', { keys })).catch((ex) => {
        toast(ex.status === 401 ? 'Sitzung abgelaufen – bitte neu anmelden, damit die Merkliste gespeichert wird.' : 'Merkliste konnte nicht gespeichert werden: ' + ex.message, 5000);
      });
    }, 350);
    return;
  }
  if (!store.set('merkliste', [...favs])) toast('Merkliste konnte im Browser nicht gespeichert werden (Speicher gesperrt).');
}
/* Beim ersten Anmelden wird eine im Browser angelegte Merkliste ins Kundenkonto übernommen */
async function kundeMerklisteLaden() {
  try {
    const r = await kundeApi('kunde_merkliste');
    favRemote = true;
    const local = store.get('merkliste', []);
    if (!r.exists && local.length) { favs = new Set(local); saveFavs(); }
    else favs = new Set(r.keys);
  } catch { /* Server nicht erreichbar: Browser-Merkliste weiter nutzen */ }
}
window.addEventListener('pagehide', () => {
  if (!favRemote || !favTimer) return;
  clearTimeout(favTimer); favTimer = null;
  try { fetch('api/?action=kunde_merkliste_save', { method: 'POST', keepalive: true, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': KCSRF }, body: JSON.stringify({ keys: [...favs] }) }); } catch { /* ignorieren */ }
});
function toggleFav(key) {
  if (favs.has(key)) favs.delete(key); else favs.add(key);
  saveFavs();
  const on = favs.has(key);
  for (const b of $$('.star')) {
    if (b.dataset.fav !== key) continue;
    b.setAttribute('aria-pressed', on);
    const name = b.getAttribute('aria-label').split(': ').slice(1).join(': ');
    b.setAttribute('aria-label', `${on ? 'Von der Merkliste entfernen' : 'Auf die Merkliste setzen'}: ${name}`);
    b.title = on ? 'Von der Merkliste entfernen' : 'Merken';
  }
  updateFavCount();
  const db = $('[data-fav-detail]');
  if (db && db.dataset.key === key) setDetailFavBtn(db, on);
  if (state.tab === 'fav') render(); else renderFavbar();
}
const favItems = () => sortItems(DATA.items.filter((i) => favs.has(i.key)), 'offer', 'asc');

/* ---------- Detailansicht ---------- */
const dlgDetail = $('#dlg-detail');
function comparables(it) {
  const list = DATA.cmpMap.get(it._cmp) || [];
  return list.filter((i) => i.price.status === 'value').length >= 2 ? list : [];
}
function cmpListHTML(list, curId) {
  const priced = sortItems(list.filter((i) => i.price.status === 'value'), 'price', 'asc');
  const rest = list.filter((i) => i.price.status !== 'value');
  const max = Math.max(...priced.map((i) => i.price.value));
  const min = priced.length ? priced[0].price.value : null;
  const li = (i) => {
    const v = i.price.status === 'value' ? i.price.value : null;
    const cls = [i.id === curId ? 'cur' : '', v != null && v === min ? 'min' : ''].join(' ').trim();
    return `<li class="${cls}"><button type="button" data-open="${i.id}">
      <span class="c-nm">${esc(i.name)}${v != null && v === min ? '<span class="flag">günstigste</span>' : ''}</span>
      <span class="c-sb">${esc([i.code ? 'Art.-Nr. ' + i.code : null, i.origin, COND_LABEL[i.condition], i.group].filter(Boolean).join(' · '))}${i.altPrices.length ? ' · ' + esc(i.price.label || '') : ''}</span>
      <span class="c-pr">${v != null ? fmtNum.format(v) + ' <span class="pu">€/kg</span>' : `<span class="muted" style="font-weight:500">${esc(priceShort(i.price))}</span>`}</span>
      ${v != null ? `<span class="bar"><i style="width:${Math.max(4, (v / max) * 100).toFixed(1)}%"></i></span>` : ''}
    </button></li>`;
  };
  return `<ul class="cmp">${priced.map(li).join('')}${rest.map(li).join('')}</ul>`;
}
function setDetailFavBtn(b, on) {
  b.innerHTML = `${icon('star')}${on ? 'Gemerkt' : 'Auf die Merkliste'}`;
  b.classList.toggle('primary', !on);
  b.setAttribute('aria-pressed', on);
  b.querySelector('svg').style.fill = on ? 'currentColor' : 'none';
}
function openDetail(id) {
  const it = DATA.byId.get(id);
  if (!it) return;
  for (const d of [$('#dlg-compare')]) if (d.open) d.close();
  const m = DATA.meta;
  const prices = it.sale
    ? `<div class="row sale"><span><span class="pl">Sonderpreis je kg – solange der Vorrat reicht</span>${it.regular != null ? `<s class="p-was">statt ${fmtNum.format(it.regular)} €/kg</s>` : ''}</span><span>${priceMain(it.price)}</span></div>`
    : [it.price, ...it.altPrices].map((p) => `<div class="row"><span>${p.label ? `<span class="pl">${esc(p.label)}</span>` : '<span class="pl">Preis je kg</span>'}</span><span>${priceMain(p)}</span></div>`).join('');
  const same = (it.sameCode || []).map((x) => DATA.byId.get(x)).filter(Boolean);
  const cmp = comparables(it);
  const dd = (label, val) => `<dt>${esc(label)}</dt><dd>${val}</dd>`;
  $('#detail-body').innerHTML = `
    <div class="dlg-head">
      <div style="min-width:0">
        <div class="d-top">${monoHTML(it.category, 'lg')}<div><div class="d-code">${it.code ? 'Art.-Nr. ' + esc(it.code) : 'Ohne Artikelnummer'}</div><div class="muted" style="font-size:12.5px">${esc(it.group)}</div></div></div>
        <h2 class="d-title" id="d-title">${esc(it.name)}</h2>
      </div>
      <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button>
    </div>
    <div class="dlg-body">
      <div class="d-price">${prices}<p class="note">${esc(m.notice || 'Angebot')} · KW ${esc(m.week ?? '?')}/${esc(m.year ?? '?')} · Preis in € je kg</p></div>
      <dl class="d-list">
        ${dd('Fleischart', esc(it.category))}
        ${dd('Herkunft', it.origin ? esc(it.origin) : '<span class="muted">In der Liste nicht angegeben</span>')}
        ${dd('Zustand', condBadge(it.condition))}
        ${dd('Merkmale', it.features.length ? `<span class="tags" style="margin:0">${it.features.map((f) => `<span class="tag">${esc(f)}</span>`).join('')}</span>` : '<span class="muted">—</span>')}
        ${it.brand ? dd('Marke', esc(it.brand)) : ''}
        ${dd('Angebotsgruppe', esc(it.group))}
        ${it.section ? dd('Bereich', esc(it.section)) : ''}
      </dl>
      ${same.length ? `<div class="notice">Die Artikelnummer ${esc(it.code)} steht ${same.length + 1}× in der Liste: ${same.map((s) => `<button type="button" class="link-btn" data-open="${s.id}">${esc(s.name)} (${esc(s.group)})</button>`).join(', ')}.</div>` : ''}
      ${cmp.length ? `<h3 class="d-h"><span>Preisvergleich · ${esc(it.category)} · ${esc(it.cut)}</span><button type="button" class="link-btn" data-cmp="${esc(it._cmp)}" style="text-transform:none;letter-spacing:0;font-size:12.5px">Vollansicht</button></h3>${cmpListHTML(cmp, it.id)}` : ''}
    </div>
    <div class="dlg-foot">${KORDER ? `<label class="d-qty"><span>Menge kg</span>${qtyHTML(it)}</label>` : ''}<button type="button" class="btn" data-close>Schließen</button><button type="button" class="btn" data-fav-detail data-key="${esc(it.key)}"></button></div>`;
  setDetailFavBtn($('[data-fav-detail]'), favs.has(it.key));
  if (!dlgDetail.open) dlgDetail.showModal();
  $('.dlg-body', dlgDetail).scrollTop = 0;
}

/* ---------- Preisvergleich ---------- */
const dlgCompare = $('#dlg-compare');
let cmpSel = { cat: null, cut: null };
function validCompareSets() {
  const sets = [];
  for (const [k, list] of DATA.cmpMap) {
    const n = list.filter((i) => i.price.status === 'value').length;
    if (n >= 2) { const [cat, cut] = k.split('|'); sets.push({ k, cat, cut, n, list }); }
  }
  return sets;
}
function openCompare(key) {
  const sets = validCompareSets();
  if (!sets.length) { toast('Keine vergleichbaren Artikel mit Preis vorhanden.'); return; }
  if (key) { const [cat, cut] = key.split('|'); cmpSel = { cat, cut }; }
  if (!sets.some((s) => s.cat === cmpSel.cat && s.cut === cmpSel.cut)) {
    const wantCat = cmpSel.cat || (state.cats.size === 1 ? [...state.cats][0] : 'Rind');
    const pref = sets.filter((s) => s.cat === wantCat);
    const pool = pref.length ? pref : sets;
    const best = pool.slice().sort((a, b) => b.n - a.n)[0];
    cmpSel = { cat: best.cat, cut: best.cut };
  }
  if (dlgDetail.open) dlgDetail.close();
  renderCompare(sets);
  if (!dlgCompare.open) dlgCompare.showModal();
}
function renderCompare(sets = validCompareSets()) {
  const cats = CATEGORY_ORDER.filter((c) => sets.some((s) => s.cat === c));
  const cuts = sets.filter((s) => s.cat === cmpSel.cat).sort((a, b) => b.n - a.n || collator.compare(a.cut, b.cut));
  const set = sets.find((s) => s.cat === cmpSel.cat && s.cut === cmpSel.cut);
  const vals = set.list.filter((i) => i.price.status === 'value').map((i) => i.price.value);
  const lo = Math.min(...vals), hi = Math.max(...vals);
  $('#compare-body').innerHTML = `
    <div class="dlg-head"><div><h2 id="cmp-title">Preisvergleich</h2><p>Vergleichbare Positionen (gleiche Fleischart und gleiches Teilstück) dieser Angebotswoche.</p></div>
      <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
    <div class="dlg-body">
      <div class="cmp-controls">
        <label>Fleischart<span class="select"><select id="cmp-cat">${cats.map((c) => `<option${c === cmpSel.cat ? ' selected' : ''}>${esc(c)}</option>`).join('')}</select>${icon('chev', 'sm')}</span></label>
        <label>Teilstück<span class="select"><select id="cmp-cut">${cuts.map((s) => `<option value="${esc(s.cut)}"${s.cut === cmpSel.cut ? ' selected' : ''}>${esc(s.cut)} (${s.list.length})</option>`).join('')}</select>${icon('chev', 'sm')}</span></label>
      </div>
      <div class="cmp-stats">
        <div><span>Günstigste</span><strong>${fmtNum.format(lo)} €</strong></div>
        <div><span>Teuerste</span><strong>${fmtNum.format(hi)} €</strong></div>
        <div><span>Spanne</span><strong>${fmtNum.format(hi - lo)} €</strong></div>
      </div>
      ${cmpListHTML(set.list, null)}
      <p class="hint">Preise je kg laut Angebotsliste. Positionen unterscheiden sich teils in Zuschnitt, Gewichtsklasse, Qualität oder Zustand – bitte Bezeichnung beachten.</p>
    </div>`;
}

/* ---------- Druck ---------- */
const dlgPrint = $('#dlg-print');
function openPrint(scope) {
  const counts = { all: DATA.items.length, filtered: current.length, fav: favItems().length };
  for (const el of $$('[data-n]', dlgPrint)) el.textContent = fmtInt.format(counts[el.dataset.n]);
  for (const r of $$('input[name="scope"]', dlgPrint)) r.disabled = !counts[r.value];
  $('#print-filter-desc').textContent = describeFilters() || 'Entspricht derzeit dem gesamten Angebot';
  const pick = scope || (hasFilters() || state.tab === 'fav' ? 'filtered' : 'all');
  const radio = $(`input[name="scope"][value="${pick}"]`, dlgPrint);
  (radio && !radio.disabled ? radio : $('input[name="scope"][value="all"]', dlgPrint)).checked = true;
  $('input[name="grouped"]', dlgPrint).checked = state.sortKey === 'offer' || pick !== 'filtered';
  dlgPrint.showModal();
}

function printPriceCell(p) {
  if (p.status === 'value') return `<span class="p-p">${fmtNum.format(p.value)}</span>`;
  if (p.status === 'request') return '<span class="p-p req">auf Anfrage</span>';
  return '<span class="p-p none">–</span>';
}
function printAltNote(it) {
  if (!it.altPrices.length && !it.price.label) return '';
  return `<small>${[it.price, ...it.altPrices].map((p) => `${esc(p.label || 'Preis')}: ${esc(priceShort(p))}`).join(' · ')}</small>`;
}
function buildPrint({ scope, layout, grouped }) {
  const m = DATA.meta;
  let list = scope === 'all' ? DATA.items.slice() : scope === 'fav' ? favItems() : current.slice();
  if (grouped) list = sortItems(list, 'offer', 'asc');
  const scopeText = scope === 'all' ? 'Gesamtes Angebot' : scope === 'fav' ? 'Merkliste' : (describeFilters() || 'Gesamtes Angebot');
  const head = `<header class="p-head">
      <div>${COMPANY ? `<div class="p-company">${esc(COMPANY)}</div>` : ''}
        <h1 class="p-title">Wochenangebot <span>KW ${esc(m.week ?? '?')} / ${esc(m.year ?? '?')}</span></h1>
        <div class="p-sub">${esc(m.notice || 'Angebot')}${m.weekStart ? ` · Angebotswoche ${dm(m.weekStart)}–${dmy(m.weekEnd)}` : ''} · Preise in € je kg · „–“ = ohne Preisangabe</div></div>
      <div class="p-meta"><strong>${esc(scopeText)}</strong><br>${plural(list.length, 'Position', 'Positionen')}<br>Stand: ${today()}</div>
    </header>`;
  let body = '';
  if (layout === 'table') {
    const rows = [];
    let sec = null, grp = null;
    for (const it of list) {
      if (grouped) {
        if (it.section !== sec) { sec = it.section; if (sec) rows.push(`<tr class="sr"><td colspan="6">${esc(sec)}</td></tr>`); }
        if (it.groupId !== grp) { grp = it.groupId; rows.push(`<tr class="gr"><td colspan="6">${esc(it.group)}</td></tr>`); }
      }
      rows.push(`<tr><td class="p-c">${esc(it.code || '—')}</td><td>${esc(it.name)}${printAltNote(it)}${grouped ? '' : `<small style="display:block;color:#777">${esc(it.group)}</small>`}</td><td>${esc(it.category)}</td><td>${esc(it.origin || '—')}</td><td>${esc(COND_LABEL[it.condition])}</td><td class="r">${printPriceCell(it.price)}</td></tr>`);
    }
    body = `<table class="p-table"><thead><tr><th>Art.-Nr.</th><th>Bezeichnung</th><th>Fleischart</th><th>Herkunft</th><th>Zustand</th><th class="r">€/kg</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
  } else {
    const row = (it) => `<div class="p-row"><span class="p-c">${esc(it.code || '—')}</span><span class="p-n">${esc(it.name)}${printAltNote(it)}</span>${printPriceCell(it.price)}</div>`;
    if (grouped) {
      let sec = null, grp = null, out = '';
      for (const it of list) {
        if (it.section !== sec) { if (grp !== null) out += '</div>'; grp = null; sec = it.section; if (sec) out += `<div class="p-section">${esc(sec)}</div>`; }
        if (it.groupId !== grp) { if (grp !== null) out += '</div>'; grp = it.groupId; out += `<div class="p-group"><div class="p-gh">${esc(it.group)}<span>€/kg</span></div>`; }
        out += row(it);
      }
      body = `<div class="p-cols">${out}${grp !== null ? '</div>' : ''}</div>`;
    } else {
      body = `<div class="p-cols"><div class="p-group"><div class="p-gh">Artikel<span>€/kg</span></div>${list.map(row).join('')}</div></div>`;
    }
  }
  $('#print-root').innerHTML = `<div class="p-doc">${head}${body}</div>`;

  let ps = $('#page-style');
  if (!ps) { ps = document.createElement('style'); ps.id = 'page-style'; document.head.appendChild(ps); }
  const label = `${COMPANY ? COMPANY + ' · ' : ''}${m.notice || 'Angebot'} KW ${m.week ?? '?'}/${m.year ?? '?'} · Preise in € je kg`.replace(/["\\]/g, '');
  ps.textContent = `@page { @bottom-left { content: "${label}"; font: 7.5pt ${getComputedStyle(document.body).fontFamily.replace(/"/g, "'")}; color: #777; } @bottom-right { content: "Seite " counter(page) " von " counter(pages); font: 7.5pt sans-serif; color: #777; } }`;
  document.title = `Wochenangebot KW ${m.week ?? ''} ${m.year ?? ''}${scope === 'fav' ? ' – Merkliste' : ''}`;
}
function doPrint(opts) {
  for (const d of $$('dialog[open]')) d.close();
  buildPrint(opts);
  printPrepared = true;
  setTimeout(() => window.print(), 60);
}
window.addEventListener('beforeprint', () => {
  if (!printPrepared) buildPrint({ scope: hasFilters() || state.tab === 'fav' ? 'filtered' : 'all', layout: 'compact', grouped: state.sortKey === 'offer' });
});
window.addEventListener('afterprint', () => {
  printPrepared = false;
  $('#print-root').innerHTML = '';
  renderStaticTitle();
});
function renderStaticTitle() {
  const m = DATA.meta;
  document.title = `Wochenangebot ${m.week ? 'KW ' + m.week + ' ' + (m.year || '') : ''}`.trim() + (COMPANY ? ' – ' + COMPANY : '');
}

/* ---------- CSV ---------- */
function csvCell(v) {
  let s = String(v ?? '');
  if (/^[=+\-@\t\r]/.test(s) && !/^-?\d[\d.,]*$/.test(s)) s = "'" + s;
  return /[";\r\n]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}
function exportCSV(list, suffix) {
  if (!list.length) { toast('Keine Artikel zum Exportieren.'); return; }
  const m = DATA.meta;
  const head = ['Artikelnummer', 'Bezeichnung', 'Fleischart', 'Herkunft', 'Angebotsgruppe', 'Bereich', 'Zustand', 'Merkmale', 'Preis €/kg', 'Preisangabe', 'Weitere Preise', 'Kalenderwoche'];
  const lines = [head.map(csvCell).join(';')];
  for (const it of list) {
    const p = it.price;
    lines.push([
      it.code || '', it.name, it.category, it.origin || '', it.group, it.section, COND_LABEL[it.condition], it.features.join(', '),
      p.status === 'value' ? fmtNum.format(p.value) : '',
      (p.label ? p.label + ': ' : '') + PRICE_STATUS_LABELS[p.status],
      it.altPrices.map((a) => `${a.label}: ${priceShort(a)}`).join(' | '),
      m.week ? `KW ${m.week}/${m.year ?? ''}` : '',
    ].map(csvCell).join(';'));
  }
  download(`${offerTitle().replace(/[^A-Za-z0-9ÄÖÜäöüß]+/g, '_')}_KW${m.week ?? ''}_${m.year ?? ''}_${suffix}.csv`, '\ufeff' + lines.join('\r\n'), 'text/csv;charset=utf-8');
  toast(`${plural(list.length, 'Artikel', 'Artikel')} als CSV exportiert.`);
}
function download(name, content, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url; a.download = name; a.rel = 'noopener';
  document.body.appendChild(a); a.click(); a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

/* ---------- Teilen ---------- */
async function copyText(text) {
  try { await navigator.clipboard.writeText(text); return true; } catch { /* Fallback */ }
  const ta = document.createElement('textarea');
  ta.value = text; ta.setAttribute('readonly', ''); ta.style.cssText = 'position:fixed;top:0;left:0;opacity:0';
  document.body.appendChild(ta); ta.select();
  let ok = false; try { ok = document.execCommand('copy'); } catch { ok = false; }
  ta.remove();
  return ok;
}
async function shareLink(withState) {
  const url = withState ? location.href : location.href.split('#')[0];
  const ok = await copyText(url);
  const local = location.protocol === 'file:' ? ' Hinweis: Die Seite ist lokal geöffnet – der Link funktioniert nur auf diesem Rechner.' : '';
  toast(ok ? (withState ? 'Link mit Suche und Filtern kopiert.' : 'Link kopiert.') + local : 'Kopieren nicht möglich – bitte die Adresse aus der Adresszeile kopieren.');
}

/* ---------- URL-Zustand ---------- */
function syncUrl() {
  const p = new URLSearchParams();
  if (state.q.trim()) p.set('suche', state.q.trim());
  for (const f of FACETS) if (state[f.set].size) p.set(f.param, [...state[f.set]].join(','));
  if (state.min != null) p.set('von', String(state.min));
  if (state.max != null) p.set('bis', String(state.max));
  if (state.sortKey !== 'offer') p.set('sortierung', `${state.sortKey}-${state.sortDir}`);
  if (state.view !== 'liste') p.set('ansicht', state.view === 'cards' ? 'karten' : 'tabelle');
  const h = p.toString();
  const url = location.pathname + location.search + (h ? '#' + h : '');
  if (url !== location.pathname + location.search + location.hash) { try { history.replaceState(null, '', url); } catch { /* ignore */ } }
}
function readUrl() {
  const p = new URLSearchParams(location.hash.slice(1));
  state.q = p.get('suche') || '';
  for (const f of FACETS) state[f.set] = new Set((p.get(f.param) || '').split(',').filter(Boolean));
  const num = (v) => (v != null && v !== '' && Number.isFinite(Number(v)) ? Number(v) : null);
  state.min = num(p.get('von')); state.max = num(p.get('bis'));
  const [k, d] = (p.get('sortierung') || 'offer-asc').split('-');
  if (['offer', 'price', 'name', 'code', 'cat', 'origin', 'cond'].includes(k)) { state.sortKey = k; state.sortDir = d === 'desc' ? 'desc' : 'asc'; }
  state.view = { karten: 'cards', tabelle: 'table' }[p.get('ansicht')] || 'liste';   // Standard: Angebotsliste wie gedruckt
  $('#q').value = state.q;
}

/* ---------- Toast ---------- */
let toastTimer;
function toast(msg, ms = 3200) {
  const t = $('#toast');
  t.textContent = msg;
  t.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => t.classList.remove('show'), ms);
}

/* ---------- Design (hell/dunkel) ---------- */
function effectiveTheme() {
  const t = document.documentElement.getAttribute('data-theme');
  return t || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
}
function updateThemeBtn() {
  const dark = effectiveTheme() === 'dark';
  const b = $('#btn-theme');
  b.innerHTML = icon(dark ? 'sun' : 'moon');
  b.setAttribute('aria-label', dark ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
}

/* ---------- Mobile Filter ---------- */
function setFiltersOpen(open) {
  $('#filters').classList.toggle('open', open);
  $('#filter-backdrop').classList.toggle('open', open);
  $('#btn-filters-open').setAttribute('aria-expanded', open);
  if (open) setTimeout(() => $('#filters-body input, #filters-body button')?.focus(), 220);
}

/* ---------- Ereignisse ---------- */
function resetFilters(alsoSearch) {
  for (const f of FACETS) state[f.set].clear();
  state.min = state.max = null;
  $('#pmin') && ($('#pmin').value = '');
  $('#pmax') && ($('#pmax').value = '');
  priceHint();
  if (alsoSearch) { state.q = ''; $('#q').value = ''; }
  render();
}
function parseDec(v) {
  const s = String(v).trim().replace(/\s|€/g, '').replace(',', '.');
  if (!s) return null;
  const n = Number(s);
  return Number.isFinite(n) && n >= 0 ? n : NaN;
}
function priceHint(err) {
  const h = $('#price-hint');
  if (!h) return;
  h.classList.toggle('err', !!err);
  h.textContent = err || (state.min != null || state.max != null ? 'Positionen ohne Preis sind bei aktivem Preisfilter ausgeblendet.' : h.dataset.default);
}
let priceTimer;
function onPriceInput() {
  clearTimeout(priceTimer);
  priceTimer = setTimeout(() => {
    const a = parseDec($('#pmin').value), b = parseDec($('#pmax').value);
    if (Number.isNaN(a) || Number.isNaN(b)) { priceHint('Bitte eine Zahl eingeben, z. B. 12,50'); return; }
    if (a != null && b != null && a > b) { priceHint('„von“ ist größer als „bis“.'); return; }
    state.min = a; state.max = b;
    priceHint();
    render();
  }, 220);
}

function scrollToResults() {
  const r = $('.results');
  const top = r.getBoundingClientRect().top;
  if (top > window.innerHeight * 0.5 || top < 0) window.scrollTo({ top: window.scrollY + top - (parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--header-h')) || 0) - 12, behavior: 'smooth' });
}

function bind() {
  const q = $('#q');
  q.addEventListener('input', () => { state.q = q.value; render(); });
  q.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') { if (q.value) { q.value = ''; state.q = ''; render(); } else q.blur(); }
    if (e.key === 'Enter') { e.preventDefault(); scrollToResults(); }
  });
  $('#q-clear').addEventListener('click', () => { q.value = ''; state.q = ''; render(); q.focus(); });
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && !e.ctrlKey && !e.metaKey && !/^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName) && !$('dialog[open]')) { e.preventDefault(); q.focus(); q.select(); }
    if (e.key === 'Escape' && $('#filters').classList.contains('open')) setFiltersOpen(false);
  });

  /* Filter */
  $('#filters-body').addEventListener('change', (e) => {
    const el = e.target;
    if (el.matches('input[type="checkbox"][data-facet]')) {
      const f = FACETS.find((x) => x.id === el.dataset.facet);
      if (el.checked) state[f.set].add(el.value); else state[f.set].delete(el.value);
      render();
    }
  });
  $('#filters-body').addEventListener('click', (e) => {
    const p = e.target.closest('.pill[data-facet]');
    if (!p) return;
    const f = FACETS.find((x) => x.id === p.dataset.facet);
    const v = p.dataset.value;
    if (state[f.set].has(v)) state[f.set].delete(v); else state[f.set].add(v);
    render();
  });
  $('#filters-body').addEventListener('input', (e) => { if (e.target.id === 'pmin' || e.target.id === 'pmax') onPriceInput(); });
  $('#btn-reset').addEventListener('click', () => resetFilters(false));
  $('#btn-filters-open').addEventListener('click', () => setFiltersOpen(true));
  $('#btn-filters-close').addEventListener('click', () => setFiltersOpen(false));
  $('#btn-filters-apply').addEventListener('click', () => { setFiltersOpen(false); scrollToResults(); });
  $('#filter-backdrop').addEventListener('click', () => setFiltersOpen(false));

  $('#chips').addEventListener('click', (e) => {
    const b = e.target.closest('[data-chip]');
    if (b) {
      const k = b.dataset.chip;
      if (k === 'q') { state.q = ''; $('#q').value = ''; }
      else if (k === 'range') { state.min = state.max = null; $('#pmin').value = ''; $('#pmax').value = ''; priceHint(); }
      else { const f = FACETS.find((x) => x.id === k); state[f.set].delete(b.dataset.value); }
      render();
      return;
    }
    if (e.target.closest('[data-act="reset-all"]')) resetFilters(true);
  });

  $('#quicknav').addEventListener('click', (e) => {
    const b = e.target.closest('.qn');
    if (!b) return;
    const c = b.dataset.cat;
    const only = state.cats.size === 1 && state.cats.has(c);
    state.cats = only ? new Set() : new Set([c]);
    if (state.tab === 'fav' && !only) state.tab = 'all';
    render();
    if (!only) scrollToResults();
  });
  /* Toolbar */
  $('#sort').addEventListener('change', (e) => { const [k, d] = e.target.value.split('-'); state.sortKey = k; state.sortDir = d; render(); });
  for (const b of $$('.seg button')) b.addEventListener('click', () => { state.view = b.dataset.view; render(); });
  /* Filter-Aufklappmenüs: nur eines offen, schließen bei Klick daneben oder Escape (nicht in der Seitenleiste) */
  $('#filters-body').addEventListener('toggle', (e) => {
    if (mqDrawer.matches || !e.target.open) return;
    for (const d of $$('.fdrop[open]')) if (d !== e.target) d.open = false;
  }, true);
  $('#filters-body').addEventListener('click', (e) => {
    const sm = e.target.closest('summary');
    if (!sm) return;
    if (mqDrawer.matches) { e.preventDefault(); return; }
    for (const d of $$('.fdrop[open]')) if (d !== sm.parentElement) d.open = false;
  });
  document.addEventListener('click', (e) => { if (!mqDrawer.matches && !e.target.closest('.fdrop')) for (const d of $$('.fdrop[open]')) d.open = false; });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape' || mqDrawer.matches) return;
    const d = $('.fdrop[open]'); if (d) { d.open = false; d.querySelector('summary').focus(); }
  });
  mqDrawer.addEventListener('change', syncDrops);
  $('#merk').addEventListener('click', (e) => {
    const o = e.target.closest('[data-merk-open]');
    if (o) { openDetail(o.dataset.merkOpen); return; }
    const a = e.target.closest('[data-merk]');
    if (!a) return;
    if (a.dataset.merk === 'order') { openOrder(); return; }
    state.tab = 'fav'; render();
    $('#main').scrollIntoView({ block: 'start' });
  });
  $('#tab-all').addEventListener('click', () => { state.tab = 'all'; render(); });
  $('#tab-fav').addEventListener('click', () => { state.tab = 'fav'; render(); });
  $('.tabs').addEventListener('keydown', (e) => {
    if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') return;
    state.tab = state.tab === 'all' ? 'fav' : 'all';
    render();
    $(state.tab === 'all' ? '#tab-all' : '#tab-fav').focus();
  });
  $('#btn-compare').addEventListener('click', () => openCompare());

  /* Liste */
  $('#list').addEventListener('click', (e) => {
    const fav = e.target.closest('[data-fav]');
    if (fav) { e.stopPropagation(); toggleFav(fav.dataset.fav); return; }
    const s = e.target.closest('[data-sort]');
    if (s) {
      const k = s.dataset.sort;
      if (state.sortKey === k) state.sortDir = state.sortDir === 'asc' ? 'desc' : 'asc';
      else { state.sortKey = k; state.sortDir = 'asc'; }
      render();
      return;
    }
    const act = e.target.closest('[data-act]');
    if (act) {
      const a = act.dataset.act;
      if (a === 'clear-q') { state.q = ''; $('#q').value = ''; render(); }
      if (a === 'reset-filters') resetFilters(true);
      if (a === 'tab-all') { state.tab = 'all'; render(); }
      return;
    }
    // Details nur über die Bezeichnung – ein Klick irgendwo in die Zeile (z. B. ins Mengenfeld) öffnet nichts
    const open = e.target.closest('[data-open]');
    if (open) openDetail(open.dataset.open);
  });

  $('#favbar').addEventListener('click', (e) => {
    const a = e.target.closest('[data-act]')?.dataset.act;
    if (a === 'fav-print') openPrint('fav');
    if (a === 'fav-csv') exportCSV(favItems(), 'Merkliste');
    if (a === 'fav-clear' && confirm('Alle Artikel von der Merkliste entfernen?')) { favs.clear(); saveFavs(); updateFavCount(); render(); }
    if (a === 'fav-prune') { favs = new Set([...favs].filter((k) => DATA.items.some((i) => i.key === k))); saveFavs(); updateFavCount(); render(); }
  });

  /* Kopf */
  $('#btn-print').addEventListener('click', () => openPrint());
  $('#btn-theme').addEventListener('click', () => {
    const next = effectiveTheme() === 'dark' ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', next);
    store.set('theme', next);
    updateThemeBtn();
  });
  matchMedia('(prefers-color-scheme: dark)').addEventListener?.('change', updateThemeBtn);

  const menuBtn = $('#btn-more'), menu = $('#menu-more');
  const setMenu = (open) => { menu.hidden = !open; menuBtn.setAttribute('aria-expanded', open); if (open) menu.querySelector('button').focus(); };
  menuBtn.addEventListener('click', () => setMenu(menu.hidden));
  document.addEventListener('click', (e) => { if (!menu.hidden && !e.target.closest('.menu-wrap')) setMenu(false); });
  menu.addEventListener('keydown', (e) => {
    const items = $$('button', menu);
    const i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    if (e.key === 'Escape') { setMenu(false); menuBtn.focus(); }
  });

  /* Globale Aktionen */
  document.addEventListener('click', (e) => {
    const el = e.target.closest('[data-action]');
    if (!el) return;
    const a = el.dataset.action;
    if (!menu.hidden) setMenu(false);
    if (a === 'csv-filtered') exportCSV(current, state.tab === 'fav' ? 'Merkliste' : hasFilters() ? 'Auswahl' : 'Gesamt');
    if (a === 'csv-all') exportCSV(sortItems(DATA.items, 'offer', 'asc'), 'Gesamt');
    if (a === 'csv-fav') exportCSV(favItems(), 'Merkliste');
    if (a === 'copy-link') shareLink(false);
    if (a === 'copy-link-state') shareLink(true);
  });

  /* Dialoge */
  for (const d of $$('dialog')) {
    if (d.id.startsWith('dlg-kunde') || d.id === 'dlg-order') continue;   // eigene Behandlung in bindKunde()/bindOrder()
    d.addEventListener('click', (e) => {
      if (e.target === d) d.close();
      if (e.target.closest('[data-close]')) d.close();
    });
  }
  dlgDetail.addEventListener('click', (e) => {
    const fb = e.target.closest('[data-fav-detail]');
    if (fb) { toggleFav(fb.dataset.key); return; }
    const c = e.target.closest('[data-cmp]');
    if (c) { openCompare(c.dataset.cmp); return; }
    const o = e.target.closest('[data-open]');
    if (o) openDetail(o.dataset.open);
  });
  dlgCompare.addEventListener('change', (e) => {
    if (e.target.id === 'cmp-cat') { cmpSel.cat = e.target.value; cmpSel.cut = null; openCompare(); }
    if (e.target.id === 'cmp-cut') { cmpSel.cut = e.target.value; renderCompare(); }
  });
  dlgCompare.addEventListener('click', (e) => { const o = e.target.closest('[data-open]'); if (o) openDetail(o.dataset.open); });

  $('#print-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    doPrint({ scope: fd.get('scope'), layout: fd.get('layout'), grouped: fd.get('grouped') === 'on' });
  });

  window.addEventListener('hashchange', () => { readUrl(); buildFilters(); render(); });

  /* Kopfhöhe für klebende Tabellenköpfe */
  const setH = () => document.documentElement.style.setProperty('--header-h', $('#topbar').offsetHeight + 'px');
  if ('ResizeObserver' in window) new ResizeObserver(setH).observe($('#topbar'));
  setH();
}

/* ---------- Bestellwunsch (nur angemeldete Kunden, wenn freigeschaltet) ----------
   Mengen werden je Kunde und Angebot im Browser gemerkt, bis der Bestellwunsch gesendet ist.
   Preise berechnet der Server beim Senden selbst aus dem veröffentlichten Angebot. */
let KORDER = false;
let cart = new Map();
const fmtQty = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 });
const fmtEur = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cartKey = () => `bestellung.${KUNDE ? KUNDE.username : '-'}.${OFFER || 'std'}`;
function parseQty(v) {
  const t = String(v ?? '').trim().replace(/\s/g, '').replace(/\.(?=\d{3}(\D|$))/g, '').replace(',', '.');
  if (t === '') return 0;
  return /^\d{1,5}(\.\d{1,2})?$/.test(t) && +t <= 99999 ? +t : NaN;
}
function qtyHTML(it) {
  const q = cart.get(it.id);
  return `<input class="qty" type="text" inputmode="decimal" autocomplete="off" data-qty="${esc(it.id)}" value="${q ? fmtQty.format(q) : ''}" placeholder="–" aria-label="Menge in kg: ${esc(it.name)}">`;
}
function loadCart() {
  const raw = store.get(cartKey(), {});
  cart = new Map();
  let gone = 0;
  for (const [id, q] of Object.entries(raw || {})) { if (DATA.byId.has(id) && q > 0) cart.set(id, q); else gone++; }
  if (gone) { saveCart(); toast(`${plural(gone, 'Position wurde', 'Positionen wurden')} aus Ihrem Bestellwunsch entfernt, weil sie nicht mehr im Angebot ${gone === 1 ? 'ist' : 'sind'}.`, 5000); }
}
function saveCart() { if (KUNDE) store.set(cartKey(), Object.fromEntries(cart)); }
const lineSum = (it, q) => Math.round(Math.round(it.price.value * 100) * q) / 100;   // in Cent, wie der Server
function cartTotals() {
  let sum = 0, kg = 0, req = 0;
  for (const [id, q] of cart) {
    const it = DATA.byId.get(id); if (!it) continue;
    kg += q;
    if (it.price.status === 'value') sum += lineSum(it, q); else req++;
  }
  return { n: cart.size, sum, kg, req };
}
function renderOrderbar() {
  renderMerk();
  const bar = $('#orderbar');
  if (!bar) return;
  if (!KORDER || !cart.size) { bar.hidden = true; document.body.classList.remove('has-orderbar'); return; }
  const t = cartTotals();
  bar.hidden = false; document.body.classList.add('has-orderbar');
  bar.innerHTML = `<div class="orderbar-in"><span class="ob-sum"><strong>${plural(t.n, 'Position', 'Positionen')}</strong> · ${fmtQty.format(t.kg)} kg · ca. ${fmtEur.format(t.sum)} €${t.req ? ` <span class="muted">+ ${t.req} auf Anfrage</span>` : ''}</span>
    <span class="ob-act"><button type="button" class="btn ghost sm" data-order="clear">Leeren</button><button type="button" class="btn primary" data-order="open">${icon('send')}Bestellwunsch prüfen</button></span></div>`;
}
function setQty(id, q, input) {
  if (Number.isNaN(q)) { if (input) { input.classList.add('invalid'); input.title = 'Bitte eine Menge in kg eingeben, z. B. 12,5'; } return; }
  if (input) { input.classList.remove('invalid'); input.title = ''; }
  if (q > 0) cart.set(id, q); else cart.delete(id);
  saveCart();
  for (const el of $$(`.qty[data-qty="${CSS.escape(id)}"]`)) if (el !== input) el.value = q ? fmtQty.format(q) : '';
  renderOrderbar();
}
function orderLines() {
  return [...cart].map(([id, q]) => ({ it: DATA.byId.get(id), q })).filter((x) => x.it).sort((a, b) => a.it.order - b.it.order);
}
function openOrder() {
  const d = $('#dlg-order'), t = cartTotals(), m = DATA.meta;
  const min = new Date().toISOString().slice(0, 10);
  $('#order-body').innerHTML = `<div class="dlg-head"><div><h2 id="or-title">Bestellwunsch prüfen</h2><p>${esc(offerTitle())}${m.week ? ` · KW ${esc(m.week)}/${esc(m.year || '')}` : ''} · ${esc(KUNDE.firma)}</p></div><button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
    <div class="dlg-body">
      <table class="otab"><thead><tr><th>Artikel</th><th class="r">Menge kg</th><th class="r">Preis €/kg</th><th class="r">Summe</th><th></th></tr></thead><tbody>
      ${orderLines().map(({ it, q }) => `<tr><td><div class="o-name">${esc(it.name)}</div><div class="sub">${esc([it.code, it.group].filter(Boolean).join(' · '))}</div></td>
        <td class="r"><input class="qty" type="text" inputmode="decimal" data-qty="${esc(it.id)}" value="${fmtQty.format(q)}" aria-label="Menge in kg: ${esc(it.name)}"></td>
        <td class="r">${it.price.status === 'value' ? fmtEur.format(it.price.value) : '<span class="muted">auf Anfrage</span>'}</td>
        <td class="r o-sum" data-sum="${esc(it.id)}">${it.price.status === 'value' ? fmtEur.format(lineSum(it, q)) + ' €' : '–'}</td>
        <td class="r"><button type="button" class="ibtn" data-order="rm" data-id="${esc(it.id)}" aria-label="Position entfernen: ${esc(it.name)}">${icon('x', 'sm')}</button></td></tr>`).join('')}
      </tbody><tfoot><tr><td><strong>Summe (ca.)</strong></td><td class="r" id="or-kg"><strong>${fmtQty.format(t.kg)}</strong></td><td></td><td class="r" id="or-sum"><strong>${fmtEur.format(t.sum)} €</strong></td><td></td></tr></tfoot></table>
      <p class="o-note" id="or-req"${t.req ? '' : ' hidden'}>Zzgl. Positionen mit Preis auf Anfrage.</p>
      <div class="o-fields">
        <label class="kfld"><span>Wunschtermin (optional)</span><input type="date" id="or-termin" min="${min}"></label>
        <label class="kfld"><span>Ihre Bestellnummer / Referenz (optional)</span><input type="text" id="or-ref" maxlength="60"></label>
        <label class="kfld o-wide"><span>Bemerkung (optional)</span><textarea id="or-bem" rows="3" maxlength="1000" placeholder="z. B. Zuschnitt, Verpackung, Lieferhinweise"></textarea></label>
      </div>
      <p class="o-note">Unverbindlicher Bestellwunsch – verbindlich wird die Bestellung erst mit unserer Bestätigung. Preise laut Angebot (freibleibend, netto); abgerechnet wird nach tatsächlichem Gewicht.</p>
      <p class="kerr" id="or-err" role="alert"></p>
    </div>
    <div class="dlg-foot"><button class="btn" type="button" data-close>Weiter auswählen</button><button class="btn primary" type="button" data-order="send">${icon('send')}Bestellwunsch senden</button></div>`;
  if (!d.open) d.showModal();
}
function refreshOrderDialog() {
  const t = cartTotals();
  if (!t.n) { $('#dlg-order').close(); return; }
  for (const { it, q } of orderLines()) { const c = $(`#order-body [data-sum="${CSS.escape(it.id)}"]`); if (c) c.textContent = it.price.status === 'value' ? fmtEur.format(lineSum(it, q)) + ' €' : '–'; }
  $('#or-kg').innerHTML = `<strong>${fmtQty.format(t.kg)}</strong>`;
  $('#or-sum').innerHTML = `<strong>${fmtEur.format(t.sum)} €</strong>`;
  $('#or-req').hidden = !t.req;
}
let lastOrderAttempt = null;
async function sendOrder(btn) {
  const err = $('#or-err');
  err.textContent = '';
  if ($('#order-body .qty.invalid')) { err.textContent = 'Bitte die markierten Mengen korrigieren.'; return; }
  btn.disabled = true;
  try {
    const payload = {
      angebot: OFFER || 'std', publishedAt: PUBLISHED_AT || '', termin: $('#or-termin').value, referenz: $('#or-ref').value, bemerkung: $('#or-bem').value,
      positions: [...cart].map(([id, qty]) => ({ id, qty })),
    };
    const fingerprint = [...new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(payload))))].map(x=>x.toString(16).padStart(2,'0')).join('');
    const attemptStore = 'wochenangebot.orderAttempt.' + KUNDE.username;
    try { lastOrderAttempt = JSON.parse(sessionStorage.getItem(attemptStore)) || lastOrderAttempt; } catch { /* session memory still protects immediate retries */ }
    if (!lastOrderAttempt || lastOrderAttempt.fingerprint !== fingerprint) lastOrderAttempt = { fingerprint, key: crypto.randomUUID() };
    try { sessionStorage.setItem(attemptStore, JSON.stringify(lastOrderAttempt)); } catch { /* private browser */ }
    const r = await kundeApi('kunde_bestellung', { ...payload, requestId: lastOrderAttempt.key });
    // Only a received success clears the attempt; errors keep the key for retries.
    lastOrderAttempt = null;
    try { sessionStorage.removeItem(attemptStore); } catch { /* private browser */ }

    cart.clear(); saveCart(); renderOrderbar();
    for (const el of $$('#list .qty')) el.value = '';
    $('#order-body').innerHTML = `<div class="dlg-head"><div><h2 id="or-title">Vielen Dank!</h2><p>Bestellwunsch ${esc(r.nr)}</p></div><button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body o-done"><div class="empty-ico">${icon('check')}</div><p>Ihr Bestellwunsch <strong>${esc(r.nr)}</strong> (${plural(r.positions, 'Position', 'Positionen')}, ${fmtQty.format(r.totalQty)} kg, ca. ${fmtEur.format(r.total)} €) ${r.delivery === 'fehler' || r.delivery === 'neu' ? 'ist gespeichert. Die E-Mail-Zustellung ist noch nicht bestätigt; bitte nicht nochmals als neuen Vorgang absenden. Bei Rückfragen nennen Sie uns die Bestellnummer.' : 'wurde an uns übermittelt. Wir melden uns mit der Bestätigung.'}</p>
        ${r.copy ? `<p class="muted">Eine Kopie haben wir an ${esc(r.copy)} gesendet.</p>` : ''}</div>
      <div class="dlg-foot"><button class="btn primary" type="button" data-close>Fertig</button></div>`;
  } catch (ex) {
    err.textContent = ex.message;
    btn.disabled = false;
    if (ex.status === 409 && /aktualisiert|nicht mehr enthalten/.test(ex.message)) {
      err.textContent = ex.message + ' Die Seite wird gleich neu geladen; Ihre Mengen bleiben erhalten.';
      setTimeout(() => location.reload(), 2500);
    }
  }
}
function bindOrder() {
  const onQty = (e, final) => {
    const el = e.target.closest('.qty');
    if (!el) return;
    const q = parseQty(el.value);
    if (final || !Number.isNaN(q)) setQty(el.dataset.qty, q, el);
    if (final && !Number.isNaN(q)) el.value = q ? fmtQty.format(q) : '';
    if ($('#dlg-order').open) refreshOrderDialog();
  };
  for (const host of [$('#list'), $('#order-body'), $('#detail-body')]) {
    host.addEventListener('input', (e) => onQty(e, false));
    host.addEventListener('change', (e) => onQty(e, true));
    host.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter' || !e.target.matches('.qty')) return;
      e.preventDefault();
      const all = $$('.qty', host), i = all.indexOf(e.target);
      (all[i + 1] || e.target).focus();
      if (all[i + 1]) all[i + 1].select(); else e.target.blur();
    });
  }
  $('#orderbar').addEventListener('click', (e) => {
    const a = e.target.closest('[data-order]')?.dataset.order;
    if (a === 'open') openOrder();
    if (a === 'clear' && confirm('Alle Mengen aus dem Bestellwunsch entfernen?')) { cart.clear(); saveCart(); render(); }
  });
  const d = $('#dlg-order');
  d.addEventListener('click', (e) => {
    if (e.target === d || e.target.closest('[data-close]')) { d.close(); return; }
    const b = e.target.closest('[data-order]');
    if (!b) return;
    if (b.dataset.order === 'rm') { setQty(b.dataset.id, 0); for (const el of $$(`#list .qty[data-qty="${CSS.escape(b.dataset.id)}"]`)) el.value = ''; b.closest('tr').remove(); refreshOrderDialog(); }
    if (b.dataset.order === 'send') sendOrder(b);
  });
}

const CUSTOMER_ORDER_LABELS = { neu: 'Eingegangen', in_bearbeitung: 'In Bearbeitung', bestaetigt: 'In Bearbeitung', erledigt: 'Erledigt', storniert: 'Storniert' };
const custState = (w) => `<span class="co-st co-${esc(w)}">${esc(CUSTOMER_ORDER_LABELS[w] || w)}</span>`;
const custDate = (iso) => (iso ? new Date(iso).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }) : '');
async function openCustomerOrders(offset = 0, nr = '') {
  const d = $('#dlg-customer-orders');
  const head = (sub) => `<div class="dlg-head"><div><h2 id="customer-orders-title">Meine Bestellwünsche</h2>${sub ? `<p>${sub}</p>` : ''}</div><button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>`;
  d.innerHTML = `<div class="dlg">${head('')}<div class="dlg-body"><div class="loading"><div class="spinner"></div>Bestellwünsche werden geladen …</div></div></div>`;
  if (!d.open) d.showModal();
  try {
    const r = await kundeApi(nr ? 'kunde_bestellung_detail&nr=' + encodeURIComponent(nr) : 'kunde_bestellungen&offset=' + offset);
    let body, foot;
    if (nr) {
      const o = r.order;
      body = `<div class="co-head"><strong>${esc(o.nr)}</strong>${custState(o.workflow)}</div>
        <p class="muted">${esc(o.angebotName || '')} · eingegangen am ${esc(custDate(o.t))}${o.termin ? ' · Wunschtermin ' + esc(dmy(o.termin)) : ''}${o.referenz ? ' · Ihre Referenz ' + esc(o.referenz) : ''}</p>
        ${o.bemerkung ? `<p class="co-note">${esc(o.bemerkung)}</p>` : ''}
        <table class="co-tab"><thead><tr><th>Artikel</th><th class="r">Menge</th><th class="r">Preis</th><th class="r">Summe</th></tr></thead><tbody>
        ${o.positions.map((p) => `<tr><td>${p.code ? `<span class="muted">${esc(p.code)}</span> ` : ''}${esc(p.name)}</td><td class="r">${fmtQty.format(p.qty)} kg</td><td class="r">${p.price == null ? 'a. Anfr.' : fmtEur.format(p.price) + ' €'}</td><td class="r">${p.sum == null ? '–' : fmtEur.format(p.sum) + ' €'}</td></tr>`).join('')}
        </tbody><tfoot><tr><td colspan="3"><strong>Summe (ca.)</strong></td><td class="r"><strong>${fmtEur.format(o.total)} €</strong></td></tr></tfoot></table>
        ${o.onRequest ? `<p class="muted">Zuzüglich ${plural(o.onRequest, 'Position', 'Positionen')} mit Preis auf Anfrage.</p>` : ''}
        <p class="muted">Ein Bestellwunsch ist noch keine Auftragsbestätigung. Wir melden uns bei Ihnen.</p>`;
      foot = `<button class="btn" type="button" data-customer-orders-page="0">${icon('chev', 'back')}Zur Übersicht</button><button class="btn primary" type="button" data-close>Schließen</button>`;
    } else {
      body = r.orders.length ? `<ul class="co-list">${r.orders.map((o) => `<li><button type="button" data-customer-order="${esc(o.nr)}"><span><strong>${esc(o.nr)}</strong><span class="muted">${esc(custDate(o.t))} · ${plural(o.positionCount, 'Position', 'Positionen')} · ${fmtEur.format(o.total)} €</span></span>${custState(o.workflow)}</button></li>`).join('')}</ul>`
        : '<p class="muted">Sie haben noch keine Bestellwünsche über das Portal gesendet.</p>';
      foot = (r.total > r.limit ? `<span class="left"><button class="btn sm" type="button" data-customer-orders-page="${Math.max(0, offset - r.limit)}"${offset === 0 ? ' disabled' : ''}>Zurück</button><button class="btn sm" type="button" data-customer-orders-page="${offset + r.limit}"${offset + r.limit >= r.total ? ' disabled' : ''}>Weiter</button></span>` : '') + '<button class="btn primary" type="button" data-close>Schließen</button>';
    }
    d.innerHTML = `<div class="dlg">${head(nr ? '' : `${plural(r.total, 'Vorgang', 'Vorgänge')}`)}<div class="dlg-body">${body}</div><div class="dlg-foot">${foot}</div></div>`;
  } catch (e) { d.innerHTML = `<div class="dlg">${head('')}<div class="dlg-body"><div class="err-box" role="alert">${esc(e.message)}</div></div><div class="dlg-foot"><button class="btn" type="button" data-close>Schließen</button></div></div>`; }
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-customer-order],[data-customer-orders-page]');
  if (b) openCustomerOrders(Number(b.dataset.customerOrdersPage || 0), b.dataset.customerOrder || '');
  const d = $('#dlg-customer-orders');
  if (d && (e.target === d || e.target.closest('#dlg-customer-orders [data-close]'))) d.close();
});

/* ---------- Kunden-Anmeldung ----------
   Kunden melden sich mit Benutzerkennung und Passwort an und sehen nur die für sie freigeschalteten Angebote.
   Die Prüfung erfolgt auf dem Server; hier wird nur die Oberfläche gesteuert. */
let KUNDE = null, KCSRF = '', KSTAFF = false, KSTDPUB = true, KWARTUNG = null;
async function kundeApi(action, body) {
  let res, data = null;
  try {
    res = await fetch('api/?action=' + action, { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': KCSRF } : {}, body: body ? JSON.stringify(body) : undefined });
  } catch { throw new Error('Keine Verbindung zum Server.'); }
  try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
  if (!res.ok || !data || !data.ok) throw Object.assign(new Error(data && data.error ? data.error : 'Serverfehler (' + res.status + ').'), { status: res.status });
  return data;
}
function setOfferParam(id) {
  const u = new URL(location.href);
  if (id && id !== 'std') u.searchParams.set('angebot', id); else u.searchParams.delete('angebot');
  return u;
}
async function kundeStart() {
  let st;
  try { st = await kundeApi('kunde_status'); } catch { return; }   // ohne Antwort: wie bisher öffentlich laden
  KSTAFF = !!st.staff; KSTDPUB = st.stdPublic !== false; KWARTUNG = st.wartung || null;
  document.body.classList.toggle('is-test', !!st.testumgebung);   // Kennzeichen „Testumgebung“
  KUNDE = st.kunde || null; KCSRF = st.csrf || '';
  KORDER = !!(KUNDE && st.bestellung && !KUNDE.mustChange && !PREVIEW);
  renderKundeBtn();
  if (!KUNDE || KUNDE.mustChange) return;
  const ids = KUNDE.angebote.map((o) => o.id);
  if (!ids.length) return;
  // nicht freigeschaltet → erstes eigenes Angebot. Ist im selben Browser zusätzlich ein Mitarbeiter angemeldet,
  // gilt das nur für die Startseite; ein ausdrücklich verlinktes Angebot (?angebot=…) bleibt dann sichtbar.
  if (!ids.includes(OFFER || 'std') && (!KSTAFF || !OFFER)) {
    OFFER = ids[0] === 'std' ? '' : ids[0];
    history.replaceState(null, '', setOfferParam(OFFER).toString());
  }
}
function renderKundeBtn() {
  const host = $('#kunde-slot');
  if (!host || PREVIEW) return;
  if (!KUNDE) {
    host.innerHTML = `<button class="btn ghost" type="button" id="btn-kunde-login" title="Anmeldung für Kunden">${icon('user')}<span class="lbl">Kunden-Login</span></button>`;
    return;
  }
  host.innerHTML = `<div class="menu-wrap"><button class="btn ghost" type="button" id="btn-kunde" aria-haspopup="menu" aria-expanded="false" aria-controls="menu-kunde" title="Angemeldet als ${esc(KUNDE.firma)}">${icon('user')}<span class="lbl k-firma">${esc(KUNDE.firma)}</span></button>
    <div class="menu" id="menu-kunde" role="menu" hidden>
      <div class="menu-label">${esc(KUNDE.username)}</div>
      ${KUNDE.angebote.length > 1 ? KUNDE.angebote.map((o) => `<button role="menuitem" type="button" data-kswitch="${esc(o.id)}">${icon(o.id === (OFFER || 'std') ? 'check' : 'file')}${esc(o.name)}</button>`).join('') + '<hr>' : ''}
      <button role="menuitem" type="button" data-kact="orders">${icon('file')}Meine Bestellwünsche</button>
      <button role="menuitem" type="button" data-kact="pw">${icon('key')}Passwort ändern</button>
      <button role="menuitem" type="button" data-kact="logout">${icon('logout')}Abmelden</button>
    </div></div>`;
}
function renderLocked(msg, withLogin = true) {
  $('#list').innerHTML = `<div class="empty k-locked"><div class="empty-ico">${icon('lock')}</div><h3>${KUNDE ? 'Kundenbereich' : 'Anmeldung erforderlich'}</h3><p>${esc(msg)}</p>
    <div class="row-actions">${!KUNDE && withLogin ? `<button type="button" class="btn primary" data-kact="login">${icon('user')}Kunden-Login</button>` : ''}${KUNDE && KUNDE.mustChange ? `<button type="button" class="btn primary" data-kact="pwforce">${icon('key')}Passwort festlegen</button>` : ''}${KUNDE ? `<button type="button" class="btn" data-kact="logout">${icon('logout')}Abmelden</button>` : ''}${!KUNDE && OFFER && KSTDPUB ? '<a class="btn" href="./">Zum öffentlichen Wochenangebot</a>' : ''}</div></div>`;
  $('#subbar').textContent = '';
  for (const id of ['quicknav', 'hits', 'chips']) { const el = $('#' + id); if (el) el.textContent = ''; }
  document.body.classList.add('k-gate');
}
function openKundeLogin() {
  const d = $('#dlg-kunde-login');
  $('#kl-err').textContent = '';
  $('#kl-form').reset();
  if (!d.open) d.showModal();
  $('#kl-form [name="username"]').focus();
}
function openKundePw(forced) {
  const d = $('#dlg-kunde-pw');
  $('#kp-form').reset();
  $('#kp-err').textContent = '';
  d.dataset.forced = forced ? '1' : '';
  $('#kp-title').textContent = forced ? 'Eigenes Passwort festlegen' : 'Passwort ändern';
  $('#kp-intro').textContent = forced ? 'Sie melden sich zum ersten Mal mit dem Startpasswort an. Bitte legen Sie jetzt ein eigenes Passwort fest (mindestens 10 Zeichen).' : 'Mindestens 10 Zeichen. Andere angemeldete Geräte werden danach abgemeldet.';
  $('#kp-close').hidden = !!forced;
  $('#kp-cancel').textContent = forced ? 'Abmelden' : 'Abbrechen';
  if (!d.open) d.showModal();
  $('#kp-form [name="current"]').focus();
}
async function kundeLogout() {
  if (favRemote && favTimer) { clearTimeout(favTimer); favTimer = null; try { await kundeApi('kunde_merkliste_save', { keys: [...favs] }); } catch { /* weiter abmelden */ } }
  await favBusy;
  try { await kundeApi('kunde_logout', {}); } catch { /* trotzdem neu laden */ }
  location.href = setOfferParam('').pathname;
}
function bindKunde() {
  if (PREVIEW) return;
  const dl = $('#dlg-kunde-login'), dp = $('#dlg-kunde-pw');
  document.addEventListener('click', (e) => {
    if (e.target.closest('#btn-kunde-login, [data-kact="login"]')) { openKundeLogin(); return; }
    const kb = e.target.closest('#btn-kunde');
    const km = $('#menu-kunde');
    if (kb && km) { const open = km.hidden; km.hidden = !open; kb.setAttribute('aria-expanded', open); if (open) km.querySelector('button').focus(); return; }
    if (km && !km.hidden && !e.target.closest('#kunde-slot')) { km.hidden = true; $('#btn-kunde').setAttribute('aria-expanded', 'false'); }
    const sw = e.target.closest('[data-kswitch]');
    if (sw) { location.href = setOfferParam(sw.dataset.kswitch).toString(); return; }
    const a = e.target.closest('[data-kact]')?.dataset.kact;
    if (a === 'orders') { if(km)km.hidden=true;openCustomerOrders(); }
    if (a === 'pw') { if (km) km.hidden = true; openKundePw(!!(KUNDE && KUNDE.mustChange)); }
    if (a === 'pwforce') openKundePw(true);
    if (a === 'logout') kundeLogout();
  });
  document.addEventListener('keydown', (e) => {
    const km = $('#menu-kunde');
    if (e.key === 'Escape' && km && !km.hidden) { km.hidden = true; $('#btn-kunde').focus(); }
  });
  $('#kl-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target, btn = f.querySelector('[type="submit"]');
    $('#kl-err').textContent = '';
    btn.disabled = true;
    try {
      const r = await kundeApi('kunde_login', { username: f.username.value.trim(), password: f.password.value });
      KCSRF = r.csrf; KUNDE = r.kunde;
      dl.close();
      if (KUNDE.mustChange) { renderKundeBtn(); renderLocked('Bitte legen Sie zuerst ein eigenes Passwort fest.'); openKundePw(true); return; }
      location.reload();
    } catch (ex) { $('#kl-err').textContent = ex.message; f.password.value = ''; f.password.focus(); }
    finally { btn.disabled = false; }
  });
  dl.addEventListener('click', (e) => { if (e.target === dl || e.target.closest('[data-close]')) dl.close(); });
  dp.addEventListener('cancel', (e) => { if (dp.dataset.forced) e.preventDefault(); });
  dp.addEventListener('click', (e) => {
    if (e.target.closest('#kp-cancel')) { if (dp.dataset.forced) kundeLogout(); else dp.close(); return; }
    if (!dp.dataset.forced && (e.target === dp || e.target.closest('[data-close]'))) dp.close();
  });
  $('#kp-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target, err = $('#kp-err'), btn = f.querySelector('[type="submit"]');
    err.textContent = '';
    if (f.password.value !== f.password2.value) { err.textContent = 'Die beiden neuen Passwörter stimmen nicht überein.'; return; }
    if (f.password.value.length < 10) { err.textContent = 'Das neue Passwort muss mindestens 10 Zeichen lang sein.'; return; }
    btn.disabled = true;
    try {
      const r = await kundeApi('kunde_passwort', { current: f.current.value, password: f.password.value });
      KUNDE = r.kunde;
      const forced = dp.dataset.forced;
      dp.dataset.forced = '';
      dp.close();
      if (forced) { location.reload(); return; }
      toast('Neues Passwort gespeichert.');
    } catch (ex) {
      err.textContent = ex.message;
      if (ex.status === 401) setTimeout(() => location.reload(), 1500);
    } finally { btn.disabled = false; }
  });
}

/* Link aus Einladung / Passwort zurücksetzen: …/#zugang=<Einmal-Code>. Der Code steht nur im Fragment
   (wird nicht an den Server übertragen und nicht protokolliert) und wird sofort aus der Adresse entfernt. */
async function kundeLinkStart() {
  const m = location.hash.match(/^#zugang=([A-Za-z0-9_-]{40,64})$/);
  if (!m) return false;
  const tok = m[1];
  history.replaceState(null, '', location.pathname + location.search);
  const d = $('#dlg-kunde-link');
  let info;
  try { info = await kundeApi('kunde_token_check', { token: tok }); }
  catch (ex) {
    renderLocked(ex.message);
    return true;
  }
  $('#kk-title').textContent = info.purpose === 'invite' ? 'Willkommen – Passwort festlegen' : 'Neues Passwort festlegen';
  $('#kk-intro').textContent = `${info.firma} · Benutzerkennung: ${info.username}. Bitte wählen Sie ein persönliches Passwort (mindestens 10 Zeichen).`;
  $('#kk-form [name="username"]').value = info.username;
  renderLocked('Bitte legen Sie Ihr Passwort fest.', false);
  d.addEventListener('cancel', (e) => e.preventDefault());
  $('#kk-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target, err = $('#kk-err'), btn = f.querySelector('[type="submit"]');
    err.textContent = '';
    if (f.password.value !== f.password2.value) { err.textContent = 'Die beiden Passwörter stimmen nicht überein.'; return; }
    if (f.password.value.length < 10) { err.textContent = 'Das Passwort muss mindestens 10 Zeichen lang sein.'; return; }
    btn.disabled = true;
    try {
      await kundeApi('kunde_token_set', { token: tok, password: f.password.value });
      d.close();
      location.replace(location.pathname + location.search);
    } catch (ex) { err.textContent = ex.message; btn.disabled = false; }
  });
  d.showModal();
  $('#kk-form [name="password"]').focus();
  return true;
}

/* Abmeldelink aus der Angebotsmail: …/#abmelden=<Code>. Erst nach Klick auf „Abmelden“ wird abgemeldet
   (Link-Vorschauen von Mailprogrammen lösen so nichts aus). Die E-Mail-Adresse bleibt beim Händler gespeichert. */
async function abmeldenStart() {
  const m = location.hash.match(/^#abmelden=(k[a-f0-9]{12}\.[A-Za-z0-9_-]{32})$/);
  if (!m) return false;
  const tok = m[1];
  history.replaceState(null, '', location.pathname + location.search);
  document.body.classList.add('k-gate');
  $('#subbar').textContent = '';
  const host = $('#list');
  const show = (ico, title, text, actions = '') => {
    host.innerHTML = `<div class="empty k-locked k-abm"><div class="empty-ico">${icon(ico)}</div><h3>${esc(title)}</h3><p>${text}</p><div class="row-actions">${actions}</div><p class="kerr" id="abm-err" role="alert"></p></div>`;
  };
  let info;
  try { info = await kundeApi('kunde_abmelden_info', { token: tok }); }
  catch (ex) { show('info', 'Link ungültig', esc(ex.message), '<a class="btn" href="./">Zum Wochenangebot</a>'); return true; }
  const who = `<strong>${esc(info.firma)}</strong>${info.email ? ` (${esc(info.email)})` : ''}`;
  const ask = () => show('mail', 'Wochenangebot per E-Mail abbestellen', `Möchten Sie für ${who} das Wochenangebot von ${esc(info.company)} nicht mehr per E-Mail erhalten?`,
    `<button type="button" class="btn primary" data-abm="ab">Abmelden</button><a class="btn" href="./">Abbrechen</a>`);
  const done = () => show('check', 'Sie sind abgemeldet', `${who} erhält das Wochenangebot nicht mehr per E-Mail. Ihr Zugang zum Angebotsportal bleibt bestehen – das Angebot finden Sie dort jederzeit.`,
    `<a class="btn" href="./">Zum Angebotsportal</a><button type="button" class="btn ghost" data-abm="wieder">Versehentlich? Wieder anmelden</button>`);
  const again = () => show('check', 'Wieder angemeldet', `${who} erhält das Wochenangebot wieder per E-Mail.`, '<a class="btn" href="./">Zum Angebotsportal</a>');
  if (info.subscribed) ask(); else done();
  host.addEventListener('click', async (e) => {
    const b = e.target.closest('[data-abm]');
    if (!b) return;
    b.disabled = true;
    try {
      const r = await kundeApi('kunde_abmelden', { token: tok, wieder: b.dataset.abm === 'wieder' });
      if (r.subscribed) again(); else done();
    } catch (ex) { $('#abm-err').textContent = ex.message; b.disabled = false; }
  });
  return true;
}

/* Wartungsseite für Kunden und Besucher */
function renderWartung(w) {
  const bis = w.until ? new Date(w.until).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
  document.body.classList.add('k-gate', 'in-wartung');
  $('#subbar').textContent = '';
  for (const id of ['quicknav', 'hits', 'chips']) { const el = $('#' + id); if (el) el.textContent = ''; }
  const slot = $('#kunde-slot'); if (slot) slot.innerHTML = '';
  $('#list').innerHTML = `<div class="empty k-locked k-wartung"><div class="empty-ico">${icon('info')}</div><h3>Wartungsarbeiten</h3><p>${esc(w.message || '')}</p>${bis ? `<p class="muted">Voraussichtlich wieder erreichbar ab ${esc(bis)} Uhr.</p>` : ''}
    <div class="row-actions"><button type="button" class="btn" data-reload>Erneut versuchen</button></div></div>`;
}

/* ---------- Start ---------- */
(async function boot() {
  updateThemeBtn();
  bindKunde();
  if (!PREVIEW && await kundeLinkStart()) return;                    // Passwort über Link aus der E-Mail festlegen
  if (!PREVIEW && await abmeldenStart()) return;                     // Abmelden vom Wochenangebot (Link aus der E-Mail)
  try {
    if (!PREVIEW) await kundeStart();
    if (KWARTUNG && !KSTAFF) { renderWartung(KWARTUNG); return; }
    if (KWARTUNG && KSTAFF) { const wb = $('#wartung-banner'); wb.hidden = false; wb.innerHTML = `<div class="banner-inner wb-inner">${icon('info')}<p><strong>Wartungsmodus aktiv</strong> – Kunden sehen gerade nur den Wartungshinweis. Sie sehen die Seite, weil Sie im Eingabebereich angemeldet sind.</p></div>`; }
    if (KUNDE && KUNDE.mustChange) { renderLocked('Bitte legen Sie zuerst ein eigenes Passwort fest.'); openKundePw(true); return; }
    if (KUNDE && !KUNDE.mustChange) await kundeMerklisteLaden();
    if (KUNDE && !KUNDE.angebote.length && !KSTAFF) { renderLocked('Für Ihren Zugang ist derzeit kein Angebot freigeschaltet. Bitte wenden Sie sich an Ihren Ansprechpartner.', false); return; }
    await loadData();
  } catch (e) {
    if (e.wartung) { renderWartung(e.wartung); return; }
    if (e.needLogin) { renderLocked((OFFER ? 'Dieses Angebot' : 'Das Wochenangebot') + ' ist nur nach Anmeldung sichtbar. Bitte melden Sie sich mit Ihrer Benutzerkennung und Ihrem Passwort an.'); openKundeLogin(); return; }
    $('#list').innerHTML = `<div class="empty"><div class="empty-ico">${icon('info')}</div><h3>Angebot nicht verfügbar</h3><p>${esc(e.message)}</p>
      <div class="row-actions"><button type="button" class="btn" data-reload>Erneut versuchen</button></div></div>`;
    $('#subbar').textContent = '';
    if (location.protocol === 'file:') $('#list .empty p').textContent = 'Die Seite muss über den Webserver geöffnet werden (nicht als lokale Datei), damit das Angebot geladen werden kann.';
    return;
  }
  readUrl();
  if (KORDER) { if (!KUNDE.angebote.some((o) => o.id === (OFFER || 'std')) && !(KSTDPUB && !OFFER)) KORDER = false; else { loadCart(); bindOrder(); document.body.classList.add('can-order'); } }
  renderStatic();
  bind();
  render();
  updateFavCount();
})();
})();

document.addEventListener('click', (e) => { if (e.target.closest('[data-reload]')) location.reload(); });
