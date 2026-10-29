/* STAFL-Plattform · Leergut – Oberfläche der Leergutkonten: Anmeldung über den Status, alle Daten aus leergut_start,
   Reiter über location.hash („#konten/<partner>“), Hell/Dunkel am Konto (theme.js).
   Ansichten: Übersicht (Fristen, offene Abschreibungen, Leergut bei Kunden mit Abholliste, Salden), Konten (nach Name
   oder Wert; Saldo wie im Palettenkonto der Spedition:
   gesamt · davon bestätigt · davon offen, Bewegungen mit laufendem Saldo), Abstimmungen, Dachser-Abschreibungen (mit
   „Dachser-Liste einlesen“: Text oder .eml, der Server liest und gleicht ab),
   Bilanz zum Stichtag mit CSV und Inventur, Einstellungen (Partner, Lademittel, WinAB-Kundenbericht, Datenpaket).
   WinAB-Bericht „Lademittelbewegungen Kunden“ (.XLS): liest der Browser mit StockCore (stock-core.js), abgleichen und buchen
   macht der Server; Kundenkonten aus WinAB stehen in Übersicht und Bilanz zusammengefasst in einer Zeile.
   Eingabemasken: Bewegung buchen, Auszug erfassen/bearbeiten, Abschreibung, Inventur, Partner, Lademittel, Storno.
   Vorzeichen überall: + der Partner schuldet uns, − wir schulden dem Partner (Abgang +, Zugang −).
   Rechte prüft der Server bei jeder Aktion (GR-103); ausgeblendete Knöpfe sind nur Anzeige. Kein Inline-Skript (CSP). */
'use strict';
(() => {
  const API = '../../api/';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const TABS = ['uebersicht', 'konten', 'abstimmungen', 'abschreibungen', 'bilanz', 'einstellungen'];
  const KURZ = { e2: 'E2', h1: 'H1', eu: 'EUR', haken: 'Haken', e1: 'E1', be2: 'Blaue E2', kuebel: 'Kübel' };
  const S = { csrf: '', d: null, pmap: new Map(), kmap: new Map(), konto: {}, tab: 'uebersicht', kontoId: '', kunde: '', alleBew: false, toast: 0, paket: null, bilanz: null, edit: {} };

  /* ---------- Aufruf der API: wirft nie, liefert { status, data, json } ---------- */
  async function api(action, body, query = '') {
    let res;
    try {
      res = await fetch(API + '?action=' + action + query, {
        method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
        headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': S.csrf } : {}, body: body ? JSON.stringify(body) : undefined,
      });
    } catch { return { status: 0, data: {}, json: false }; }
    let data = null;
    try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
    return { status: res.status, data: data || {}, json: data !== null };
  }
  const fehlerText = (r, fallback) => (r.data && r.data.error) || (r.status === 0 ? 'Keine Verbindung zum Server.' : `${fallback} (${r.status}).`);
  function toast(text, fehlerhaft = false) {
    const t = $('#lg-toast');
    t.textContent = text; t.className = 'lg-toast zeigen' + (fehlerhaft ? ' fehler' : '');
    clearTimeout(S.toast); S.toast = setTimeout(() => { t.className = 'lg-toast'; }, fehlerhaft ? 4500 : 2400);
  }
  function fehler(text) { $('#lg-login').hidden = true; $('#lg-app').hidden = true; $('#lg-err').hidden = false; $('#lg-err').textContent = text; }
  function zeigeAnmeldung() { $$('dialog[open]').forEach((d) => d.close()); $('#lg-login').hidden = false; $('#lg-app').hidden = true; $('#lg-user').hidden = true; }
  const initialen = (name) => { const t = String(name || '').trim().split(/[\s.\-_]+/).filter(Boolean); return (t.length > 1 ? t[0][0] + t[1][0] : (t[0] || '?').slice(0, 2)).toLocaleUpperCase('de-DE'); };

  /* ---------- Formate ---------- */
  const obj = (m) => (m && typeof m === 'object' && !Array.isArray(m) ? m : {});   // PHP liefert leere Zuordnungen als []
  const zahl = (n) => Number(n).toLocaleString('de-DE');
  const vz = (n) => (n > 0 ? '+' + zahl(n) : n < 0 ? '−' + zahl(-n) : '0');
  const vzKlasse = (n) => (n > 0 ? 'lg-plus' : n < 0 ? 'lg-minus' : 'lg-null');
  const vzHtml = (n) => `<span class="${vzKlasse(n)}">${vz(n)}</span>`;
  const datum = (iso) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}` : '');
  const zeitpunkt = (t) => { const d = new Date(t); return isNaN(d) ? '' : d.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' }); };
  const euro = (n) => Number(n).toLocaleString('de-DE', { style: 'currency', currency: 'EUR' });
  const lm = (id) => (S.d.lademittel.find((l) => l.id === id) || { id, name: id, wert: null });
  const kurz = (id) => KURZ[id] || lm(id).name;
  const sortiertLm = (ids) => S.d.lademittel.map((l) => l.id).filter((id) => ids.has(id));
  /* Mengen „E2 +12 · H1 −3“ (nur Werte ≠ 0) */
  function mengen(m, { vorzeichen = true, leer = '—' } = {}) {
    const e = Object.entries(obj(m)).filter(([, n]) => n);
    if (!e.length) return `<span class="lg-null">${leer}</span>`;
    const ids = sortiertLm(new Set(e.map(([k]) => k)));
    return `<span class="lg-mengen">${ids.map((id) => { const n = obj(m)[id]; return `<span><small>${esc(kurz(id))}</small>${vorzeichen ? vzHtml(n) : zahl(n)}</span>`; }).join('')}</span>`;
  }
  /* Ganze Zahl aus einer Eingabe („1.200“, „−15“); '' → 0, ungültig → NaN */
  function ganz(v) {
    const t = String(v ?? '').trim().replace(/[\s.]/g, '').replace(/[−–]/g, '-');
    if (t === '') return 0;
    return /^[+-]?\d{1,7}$/.test(t) ? parseInt(t, 10) : NaN;
  }
  const delta = (b) => { const d = {}; for (const [k, n] of Object.entries(obj(b.abgang))) d[k] = (d[k] || 0) + n; for (const [k, n] of Object.entries(obj(b.zugang))) d[k] = (d[k] || 0) - n; return d; };
  function saldoBis(bewegungen, stichtag) {
    const s = {};
    for (const b of bewegungen) { if (b.storno || (stichtag && b.datum > stichtag)) continue; for (const [k, n] of Object.entries(delta(b))) s[k] = (s[k] || 0) + n; }
    for (const k of Object.keys(s)) if (!s[k]) delete s[k];
    return s;
  }
  const minus = (a, b) => { const d = { ...obj(a) }; for (const [k, n] of Object.entries(obj(b))) d[k] = (d[k] || 0) - n; for (const k of Object.keys(d)) if (!d[k]) delete d[k]; return d; };
  const leerMap = (m) => !Object.values(obj(m)).some((n) => n);
  const statusChip = (st, liste) => `<span class="lg-chip s-${esc(st)}">${esc((liste || {})[st] || st)}</span>`;
  function fristChip(a) {
    if (a.status === 'widersprochen') return '<span class="lg-chip rot">Widersprochen</span>';
    if (a.status !== 'offen') return statusChip(a.status, S.d.abstStatus);
    if (!a.fristBis) return '<span class="lg-chip">ohne Frist</span>';
    const t = a.restTage;
    const text = t < 0 ? `${-t} ${-t === 1 ? 'Tag' : 'Tage'} drüber` : t === 0 ? 'heute' : t === 1 ? 'morgen' : `noch ${t} Tage`;
    return `<span class="lg-chip ${esc(a.ampel)}" title="Frist bis ${esc(datum(a.fristBis))}">${text}</span>`;
  }
  const partnerName = (id) => (S.pmap.get(id) || { name: '(unbekannt)' }).name;
  const mehrereFirmen = () => new Set(S.d.partner.map((p) => p.mandant)).size > 1;
  const partnerSub = (p) => [S.d.arten[p.art] || p.art, mehrereFirmen() ? S.d.mandanten[p.mandant] : ''].filter(Boolean).join(' · ');
  const nachName = (a, b) => String(a.name).localeCompare(String(b.name), 'de', { sensitivity: 'base' });
  const darf = (r) => !!(S.d && S.d.rechte && S.d.rechte[r]);
  const istWinab = (p) => !!(p && p.quelle === 'winab');   // beim WinAB-Import angelegtes Kundenkonto
  const tageBis = (iso) => (iso ? Math.max(0, Math.round((Date.parse(S.d.heute + 'T12:00:00Z') - Date.parse(iso + 'T12:00:00Z')) / 86400000)) : null);
  /* Leergut bei Kunden: Konten der Art Kunde mit Saldo, nach Wert. „Ohne Rückgabe seit“ nur, wenn der Kunde uns schuldet:
     letzte Rückgabe, ohne Rückgabe die erste Lieferung (gleiche Regel wie die Abholliste des Servers). */
  function kundenLeergut() {
    return S.d.partner.filter((p) => p.art === 'kunde' && !leerMap(obj(S.kmap.get(p.id)?.saldo))).map((p) => {
      const k = S.kmap.get(p.id), s = obj(k.saldo);
      const stueck = Object.values(s).reduce((a, n) => a + (n > 0 ? n : 0), 0);
      const seit = stueck > 0 && !k.rueckgabeUnbekannt ? (k.letzteRueckgabe || k.ersteAbgabe || '') : '';
      return { p, k, saldo: s, stueck, euro: euroVon(s), seit, tage: tageBis(seit) };
    }).sort((a, b) => (b.euro.betrag - a.euro.betrag) || (b.stueck - a.stueck) || nachName(a.p, b.p));
  }
  const rueckgabeChip = (z) => (z.tage === null ? '' : `<span class="lg-chip ${z.tage >= 60 ? 'rot' : z.tage >= 30 ? 'gelb' : 'gruen'}" title="${z.k.letzteRueckgabe ? 'seit der letzten Rückgabe' : 'noch nie zurückgegeben – seit der ersten Lieferung'}">${z.tage === 0 ? 'heute' : `seit ${zahl(z.tage)} ${z.tage === 1 ? 'Tag' : 'Tagen'}`}</span>`);

  /* Rückweg zum Dashboard auf der echten Adresse */
  if (/(^|\.)dashboard-stafl\.de$/.test(location.hostname)) $('#lg-zurueck').href = 'https://dashboard-stafl.de/';

  /* ---------- Hell/Dunkel ---------- */
  const dunkel = () => document.documentElement.getAttribute('data-theme') === 'dark'
    || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  function themaKnopf() {
    const d = dunkel(), b = $('#lg-theme');
    b.innerHTML = `<svg class="i" aria-hidden="true"><use href="#i-${d ? 'sun' : 'moon'}"/></svg>`;
    b.setAttribute('aria-label', d ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }
  $('#lg-theme').addEventListener('click', () => { document.documentElement.setAttribute('data-theme', dunkel() ? 'light' : 'dark'); themaKnopf(); });
  document.addEventListener('stafl-theme', themaKnopf);

  /* ---------- Reiter ---------- */
  function zeigeTab(tab, teil = '') {
    if (!TABS.includes(tab) || (tab === 'einstellungen' && !darf('verwalten'))) tab = 'uebersicht';
    S.tab = tab;
    $$('#lg-tabs [role="tab"]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
    $$('.lg-tab').forEach((x) => { x.hidden = x.dataset.tab !== tab; });
    if (tab === 'konten' && teil) zeigeKonto(teil);
    else if (tab === 'konten' && S.kontoId) history.replaceState(null, '', '#konten/' + S.kontoId);
    else history.replaceState(null, '', '#' + tab);
    if (tab === 'bilanz') ladeBilanz();
  }
  $('#lg-tabs').addEventListener('click', (ev) => { const b = ev.target.closest('[role="tab"]'); if (b) zeigeTab(b.dataset.tab); });
  window.addEventListener('hashchange', () => {   // Zurück-Knopf und Links mit #…
    if (!S.d) return;
    const [tab, teil] = location.hash.slice(1).split('/');
    if (tab !== S.tab || (teil && teil !== S.kontoId)) zeigeTab(tab || 'uebersicht', teil || '');
  });
  document.addEventListener('click', (ev) => {
    const g = ev.target.closest('[data-gehe]');
    if (g) { ev.preventDefault(); zeigeTab(g.dataset.gehe, g.dataset.teil || ''); window.scrollTo({ top: 0 }); }
  });

  /* ---------- Daten ---------- */
  function setzeDaten(d) {
    S.d = d;
    S.pmap = new Map(d.partner.map((p) => [p.id, p]));
    S.kmap = new Map(d.konten.map((k) => [k.id, k]));
    S.konto = {};
  }
  async function neuLaden() {
    const r = await api('leergut_start');
    if (r.status === 401) { zeigeAnmeldung(); return false; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Aktualisieren fehlgeschlagen'), true); return false; }
    setzeDaten(r.data); renderAlles(); return true;
  }
  async function kontoLaden(id) {
    if (S.konto[id]) return S.konto[id];
    const r = await api('leergut_konto', null, '&partner=' + encodeURIComponent(id));
    if (r.status === 401) { zeigeAnmeldung(); return null; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Konto konnte nicht geladen werden'), true); return null; }
    S.konto[id] = r.data;
    return r.data;
  }
  function renderAlles() {
    $('#lg-tabs [data-tab="einstellungen"]').hidden = !darf('verwalten');
    $('#lg-schnell').hidden = !darf('bearbeiten') || !S.d.partner.some((p) => p.aktiv);
    $('#lg-d-neu').hidden = !darf('bearbeiten');
    $('#lg-d-dachser').hidden = !darf('bearbeiten');
    $('#lg-i-neu').hidden = !darf('bearbeiten');
    renderUebersicht(); renderKontoliste(); renderAbstimmungen(); renderAbschreibungen(); renderInventur();
    if (darf('verwalten')) renderEinstellungen();
    if (S.kontoId && S.pmap.has(S.kontoId)) zeigeKonto(S.kontoId, false);
    if (S.tab === 'bilanz') ladeBilanz();
  }

  /* ---------- Übersicht ---------- */
  function renderUebersicht() {
    const d = S.d;
    $('#lg-u-leer').hidden = !d.leer;
    if (d.leer && darf('verwalten')) $('#lg-u-leer p').innerHTML = 'Partner einzeln anlegen oder alle auf einmal aus dem Datenpaket der bisherigen Excel-Liste übernehmen: <a href="#einstellungen" data-gehe="einstellungen">Einstellungen</a>.';
    const offen = d.abstimmungen.filter((a) => a.status === 'offen');
    const drueber = offen.filter((a) => a.ampel === 'rot').length;
    const wider = d.abstimmungen.filter((a) => a.status === 'widersprochen').length;
    const abOffen = d.abschreibungen.filter((x) => x.status === 'offen');
    const abSumme = {}; abOffen.forEach((x) => { for (const [k, n] of Object.entries(obj(x.menge))) abSumme[k] = (abSumme[k] || 0) + n; });
    const aktiv = d.partner.filter((p) => p.aktiv).length;
    const mitSaldo = d.konten.filter((k) => !leerMap(k.saldo)).length;
    $('#lg-u-kpis').innerHTML = `
      <div class="lg-kpi"><span>Leergutkonten</span><b>${zahl(aktiv)}</b><small>${zahl(mitSaldo)} mit offenem Saldo</small></div>
      <div class="lg-kpi${drueber ? ' warn' : ''}"><span>Offene Auszüge</span><b>${zahl(offen.length)}</b><small>${drueber ? `${zahl(drueber)} mit abgelaufener Frist` : 'keine Frist abgelaufen'}</small></div>
      <div class="lg-kpi"><span>Widersprochen</span><b>${zahl(wider)}</b><small>in Klärung mit dem Partner</small></div>
      <div class="lg-kpi"><span>Abschreibungen offen</span><b>${zahl(abOffen.length)}</b><small>${leerMap(abSumme) ? 'nichts zu prüfen' : Object.entries(abSumme).map(([k, n]) => `${esc(kurz(k))} ${zahl(n)}`).join(' · ')}</small></div>`;

    // Fristen: offene nach Restzeit, dann widersprochene
    const liste = d.abstimmungen.filter((a) => a.status === 'offen' || a.status === 'widersprochen')
      .sort((a, b) => (a.status === b.status ? 0 : a.status === 'offen' ? -1 : 1) || ((a.fristBis ? a.restTage : 9999) - (b.fristBis ? b.restTage : 9999)) || String(b.stichtag).localeCompare(a.stichtag));
    $('#lg-u-fristen').innerHTML = liste.length ? `<ul class="lg-fristen">${liste.slice(0, 12).map((a) => `<li><button type="button" class="lg-frist" data-abst="${esc(a.id)}">
        <span class="lg-tage">${fristChip(a)}</span>
        <span><b>${esc(partnerName(a.partner))}</b><span class="lg-sub">Auszug zum ${esc(datum(a.stichtag))}${a.fristBis ? ' · Frist ' + esc(datum(a.fristBis)) : ''}</span></span>
        <span>${leerMap(a.differenz) ? '<span class="lg-chip gruen">keine Differenz</span>' : mengen(a.differenz)}</span></button></li>`).join('')}</ul>
        ${liste.length > 12 ? `<p class="lg-fussnote"><a href="#abstimmungen" data-gehe="abstimmungen">${zahl(liste.length - 12)} weitere unter Abstimmungen</a></p>` : ''}`
      : '<p class="lg-leerzeile">Keine offenen Auszüge – alle Abstimmungen erledigt.</p>';

    // Offene Abschreibungen je Kunde
    const jeKunde = new Map();
    abOffen.forEach((x) => { const k = jeKunde.get(x.empfaenger) || { n: 0, m: {} }; k.n++; for (const [id, n] of Object.entries(obj(x.menge))) k.m[id] = (k.m[id] || 0) + n; jeKunde.set(x.empfaenger, k); });
    const kunden = [...jeKunde.entries()].sort((a, b) => b[1].n - a[1].n);
    $('#lg-u-abschr').innerHTML = kunden.length ? `<table class="lg-tabelle lg-karten"><thead><tr><th>Kunde</th><th class="lg-zahl">Fälle</th><th>Menge</th></tr></thead><tbody>
        ${kunden.slice(0, 8).map(([name, k]) => `<tr class="lg-klick" data-kunde="${esc(name)}"><td class="lg-name lg-voll">${esc(name)}</td><td class="lg-zahl" data-label="Fälle">${zahl(k.n)}</td><td data-label="Menge">${mengen(k.m, { vorzeichen: false })}</td></tr>`).join('')}</tbody></table>`
      : '<p class="lg-leerzeile">Keine offenen Abschreibungen.</p>';

    // Leergut bei Kunden: die zehn mit dem höchsten Wert
    const kl = kundenLeergut();
    $('#lg-u-kunden-panel').hidden = !kl.length;
    if (kl.length) {
      const offenK = kl.filter((z) => z.stueck > 0), wert = offenK.reduce((a, z) => a + z.euro.betrag, 0), lange = offenK.filter((z) => z.tage >= 60).length;
      $('#lg-u-kunden-sum').textContent = `${zahl(offenK.length)} ${offenK.length === 1 ? 'Kunde hat' : 'Kunden haben'} Leergut von uns im Wert von ${euro(Math.round(wert * 100) / 100)}`
        + (lange ? ` · ${zahl(lange)} seit mindestens 60 Tagen ohne Rückgabe.` : '.') + ' Nur bewertete Lademittel zählen zum Wert.'
        + (kl.some((z) => z.k.rueckgabeUnbekannt) ? ' Letzte Rückgabe „unbekannt“: den WinAB-Bericht unter Einstellungen noch einmal wählen.' : '');
      $('#lg-u-kunden').innerHTML = `<table class="lg-tabelle lg-karten"><thead><tr><th>Kunde</th><th>Saldo</th><th class="lg-zahl">Wert</th><th>Letzte Lieferung</th><th>Letzte Rückgabe</th></tr></thead><tbody>
        ${kl.slice(0, 10).map((z) => `<tr class="lg-klick" data-konto="${esc(z.p.id)}"><td class="lg-voll"><span class="lg-name">${esc(z.p.name)}</span>${z.p.kundenNr ? `<span class="lg-sub">WinAB-Kd. ${esc(z.p.kundenNr)}</span>` : ''}</td>
          <td data-label="Saldo">${mengen(z.saldo)}</td><td class="lg-zahl" data-label="Wert">${z.euro.betrag ? euro(z.euro.betrag) + (z.euro.vollstaendig ? '' : '*') : '—'}</td>
          <td data-label="Letzte Lieferung">${z.k.letzteAbgabe ? esc(datum(z.k.letzteAbgabe)) : '<span class="lg-null">—</span>'}</td>
          <td data-label="Letzte Rückgabe">${z.k.rueckgabeUnbekannt ? '<span class="lg-null" title="Den WinAB-Bericht unter Einstellungen noch einmal wählen – dann zählen auch Rückgaben aus reinem Tausch.">unbekannt</span>'
            : z.k.letzteRueckgabe ? esc(datum(z.k.letzteRueckgabe)) : '<span class="lg-null">noch nie</span>'} ${rueckgabeChip(z)}</td></tr>`).join('')}</tbody></table>
        ${kl.length > 10 ? `<p class="lg-fussnote">${zahl(kl.length - 10)} weitere unter „Alle Kunden“ und in der Abholliste.</p>` : ''}`;
    }

    // Salden je Konto (Kundenkonten aus WinAB zusammengefasst in einer Zeile)
    const konten = d.partner.filter((p) => !istWinab(p) && (p.aktiv || !leerMap(obj(S.kmap.get(p.id)?.saldo)))).sort(nachName);
    const wk = d.partner.filter(istWinab), wSaldo = {};
    let wMit = 0;
    wk.forEach((p) => { const s = obj(S.kmap.get(p.id)?.saldo); if (!leerMap(s)) wMit++; for (const [k, n] of Object.entries(s)) wSaldo[k] = (wSaldo[k] || 0) + n; });
    const ids = new Set(Object.keys(wSaldo).filter((k) => wSaldo[k]));
    konten.forEach((p) => Object.keys(obj(S.kmap.get(p.id)?.saldo)).forEach((k) => ids.add(k)));
    if (!ids.size) { ids.add('e2'); ids.add('h1'); }
    const lms = sortiertLm(ids);
    const summe = {};
    const zeilen = konten.map((p) => {
      const k = S.kmap.get(p.id) || {}; const s = obj(k.saldo); const la = k.letzteAbstimmung;
      lms.forEach((id) => { summe[id] = (summe[id] || 0) + (s[id] || 0); });
      return `<tr class="lg-klick" data-konto="${esc(p.id)}"><td class="lg-voll"><span class="lg-name">${esc(p.name)}</span><span class="lg-sub">${esc(partnerSub(p))}</span></td>
        ${lms.map((id) => `<td class="lg-zahl lg-mobil-weg">${s[id] ? vzHtml(s[id]) : '<span class="lg-null">·</span>'}</td>`).join('')}
        <td class="lg-nur-mobil" data-label="Saldo">${mengen(s, { leer: 'ausgeglichen' })}</td>
        <td data-label="Letzte Abstimmung">${la ? `${esc(datum(la.stichtag))} ${statusChip(la.status, d.abstStatus)}` : '<span class="lg-null">—</span>'}</td>
        <td data-label="Differenz laut Partner">${la ? (leerMap(la.differenz) ? '<span class="lg-null">keine</span>' : mengen(la.differenz)) : ''}</td></tr>`;
    });
    if (wk.length) {
      lms.forEach((id) => { summe[id] = (summe[id] || 0) + (wSaldo[id] || 0); });
      zeilen.push(`<tr class="lg-klick" data-kunden="1"><td class="lg-voll"><span class="lg-name">Kunden aus WinAB</span><span class="lg-sub">${zahl(wMit)} von ${zahl(wk.length)} Kundenkonten mit Saldo</span></td>
        ${lms.map((id) => `<td class="lg-zahl lg-mobil-weg">${wSaldo[id] ? vzHtml(wSaldo[id]) : '<span class="lg-null">·</span>'}</td>`).join('')}
        <td class="lg-nur-mobil" data-label="Saldo">${mengen(wSaldo, { leer: 'ausgeglichen' })}</td><td data-label="Letzte Abstimmung"><span class="lg-null">—</span></td><td></td></tr>`);
    }
    $('#lg-u-salden').innerHTML = konten.length || wk.length ? `<table class="lg-tabelle lg-karten"><thead><tr><th>Konto</th>${lms.map((id) => `<th class="lg-zahl">${esc(kurz(id))}</th>`).join('')}<th>Letzte Abstimmung</th><th>Differenz laut Partner</th></tr></thead>
      <tbody>${zeilen.join('')}</tbody><tfoot><tr><td class="lg-voll">Summe aller Konten</td>${lms.map((id) => `<td class="lg-zahl lg-mobil-weg">${vzHtml(summe[id] || 0)}</td>`).join('')}<td class="lg-nur-mobil lg-voll">${mengen(summe, { leer: 'ausgeglichen' })}</td><td></td><td></td></tr></tfoot></table>`
      : '<p class="lg-leerzeile">Noch keine Konten.</p>';
  }
  $('#lg-u-fristen').addEventListener('click', (ev) => { const b = ev.target.closest('[data-abst]'); if (b) oeffneAuszug({ id: b.dataset.abst }); });
  const zeigeKunden = () => { $('#lg-k-art').value = 'kunde'; $('#lg-k-sort').value = 'wert'; renderKontoliste(); zeigeTab('konten'); window.scrollTo({ top: 0 }); };
  $('#lg-u-kunden').addEventListener('click', (ev) => { const r = ev.target.closest('[data-konto]'); if (r) zeigeTab('konten', r.dataset.konto); });
  $('#lg-u-kunden-alle').addEventListener('click', () => zeigeKunden());
  $('#lg-u-kunden-csv').addEventListener('click', () => ladeCsv({ liste: 'kunden' }, `Leergut-Kunden_${S.d.heute}.csv`));
  $('#lg-u-salden').addEventListener('click', (ev) => { if (ev.target.closest('[data-kunden]')) { zeigeKunden(); return; } const r = ev.target.closest('[data-konto]'); if (r) zeigeTab('konten', r.dataset.konto); });
  $('#lg-u-abschr').addEventListener('click', (ev) => { const r = ev.target.closest('[data-kunde]'); if (r) { S.kunde = r.dataset.kunde; $('#lg-d-status').value = 'offen'; renderAbschreibungen(); zeigeTab('abschreibungen'); } });

  /* ---------- Konten ---------- */
  function fuelleFilter() {
    const art = $('#lg-k-art'), firma = $('#lg-k-firma');
    const a = art.value, f = firma.value;
    art.innerHTML = '<option value="">Alle Arten</option>' + Object.entries(S.d.arten).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');
    firma.innerHTML = '<option value="">Alle Firmen</option>' + Object.entries(S.d.mandanten).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');
    art.value = a; firma.value = f;
    firma.hidden = !mehrereFirmen();
  }
  function renderKontoliste() {
    fuelleFilter();
    const q = $('#lg-k-suche').value.trim().toLocaleLowerCase('de-DE');
    const art = $('#lg-k-art').value, firma = $('#lg-k-firma').value, inaktiv = $('#lg-k-inaktiv').checked, nachWert = $('#lg-k-sort').value === 'wert';
    const wert = (p) => euroVon(obj(S.kmap.get(p.id)?.saldo)).betrag;
    const liste = S.d.partner.filter((p) => (inaktiv || p.aktiv) && (!art || p.art === art) && (!firma || p.mandant === firma)
      && (!q || [p.name, p.kontoNr, p.kundenNr, p.lieferanten, p.ansprechpartner].join(' ').toLocaleLowerCase('de-DE').includes(q)))
      .sort((a, b) => (nachWert ? wert(b) - wert(a) : 0) || nachName(a, b));
    $('#lg-k-liste').innerHTML = liste.length ? liste.map((p) => {
      const k = S.kmap.get(p.id) || {};
      const punkt = k.ueberfaellig ? 'rot' : k.abstimmungenOffen ? 'gelb' : '';
      return `<li class="${p.aktiv ? '' : 'lg-inaktiv'}"><button type="button" data-konto="${esc(p.id)}" aria-current="${p.id === S.kontoId}">
        <span class="lg-name">${esc(p.name)}</span><span class="lg-punkt ${punkt}" title="${punkt === 'rot' ? 'Frist abgelaufen' : punkt ? 'Auszug offen' : ''}"></span>
        ${mengen(k.saldo, { leer: 'ausgeglichen' })}${nachWert && wert(p) ? `<span class="lg-listwert">${euro(wert(p))}</span>` : ''}</button></li>`;
    }).join('') : '<li class="lg-leerzeile">Kein Konto gefunden.</li>';
  }
  ['#lg-k-suche', '#lg-k-art', '#lg-k-firma', '#lg-k-inaktiv', '#lg-k-sort'].forEach((s) => $(s).addEventListener('input', renderKontoliste));
  $('#lg-k-liste').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-konto]');
    if (!b) return;
    zeigeKonto(b.dataset.konto);
    if (matchMedia('(max-width: 860px)').matches) $('#lg-k-detail').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  const kontoLms = (p, bewegungen) => {
    const ids = new Set(p.lademittel || []);
    Object.keys(obj(S.kmap.get(p.id)?.saldo)).forEach((k) => ids.add(k));
    (bewegungen || []).forEach((b) => Object.keys(delta(b)).forEach((k) => ids.add(k)));
    return sortiertLm(ids);
  };
  async function zeigeKonto(id, hash = true) {
    if (!S.pmap.has(id)) return;
    if (S.kontoId !== id) S.alleBew = false;
    S.kontoId = id;
    if (hash && S.tab === 'konten') history.replaceState(null, '', '#konten/' + id);
    $$('#lg-k-liste [data-konto]').forEach((b) => b.setAttribute('aria-current', String(b.dataset.konto === id)));
    const box = $('#lg-k-detail');
    if (!S.konto[id] && box.dataset.konto !== id) box.innerHTML = '<p class="lg-leer-text lg-glas">Konto wird geladen …</p>';   // beim Aktualisieren alten Stand stehen lassen
    const k = await kontoLaden(id);
    if (!k || S.kontoId !== id) return;
    const p = k.partner, ko = S.kmap.get(id) || {}, lms = kontoLms(p, k.bewegungen);
    const best = ko.bestaetigt, la = ko.letzteAbstimmung;
    const meta = [`<span class="lg-chip">${esc(S.d.arten[p.art] || p.art)}</span>`, `<span class="lg-chip firma">${esc(S.d.mandanten[p.mandant] || p.mandant)}</span>`,
      p.aktiv ? '' : '<span class="lg-chip">inaktiv</span>', p.kontoNr ? `<span>Konto-Nr. ${esc(p.kontoNr)}</span>` : '', p.kundenNr ? `<span>WinAB-Kd. ${esc(p.kundenNr)}</span>` : '',
      p.fristTage ? `<span>Widerspruch binnen ${zahl(p.fristTage)} Tagen</span>` : '<span>ohne Widerspruchsfrist</span>',
      p.ansprechpartner ? `<span>${esc(p.ansprechpartner)}</span>` : '',
      p.email ? `<a href="mailto:${esc(p.email.replace(/\s/g, ''))}">${esc(p.email)}</a>` : ''].filter(Boolean).join('');
    const knoepfe = [
      darf('bearbeiten') && p.aktiv ? `<button class="btn primary sm" type="button" data-k-aktion="bewegung"><svg class="i" aria-hidden="true"><use href="#i-plus"/></svg>Bewegung</button>` : '',
      darf('bearbeiten') ? `<button class="btn sm" type="button" data-k-aktion="auszug"><svg class="i" aria-hidden="true"><use href="#i-dokument"/></svg>Auszug erfassen</button>` : '',
      p.email ? `<a class="btn sm" href="${esc(saldoMail(p, ko))}"><svg class="i" aria-hidden="true"><use href="#i-mail"/></svg>Saldo anfragen</a>` : '',
      darf('verwalten') ? `<button class="btn sm ghost" type="button" data-k-aktion="partner"><svg class="i" aria-hidden="true"><use href="#i-stift"/></svg>Partner</button>` : ''].join('');
    const karten = lms.map((lid) => {
      const g = obj(ko.saldo)[lid] || 0, b = best ? (obj(best.saldo)[lid] || 0) : null, o = obj(ko.offenSeitBestaetigung)[lid] || 0;
      const w = lm(lid).wert;
      const lp = la && la.saldo !== null ? (obj(la.saldo)[lid] || 0) : null;
      return `<section class="lg-saldo lg-glas"><h3>${esc(lm(lid).name)}</h3><span class="lg-gross ${vzKlasse(g)}">${vz(g)}</span>
        ${w !== null && w !== undefined && g ? `<span class="lg-wert">${euro(g * w)} · ${euro(w)} je Stück</span>` : ''}
        <dl><dt>davon bestätigt${best ? ' (' + esc(datum(best.stichtag)) + ')' : ''}</dt><dd>${b === null ? '—' : vzHtml(b)}</dd>
        <dt>davon offen</dt><dd>${vzHtml(o)}</dd>
        ${lp !== null ? `<dt>laut Partner (${esc(datum(la.stichtag))})</dt><dd>${vzHtml(lp)}</dd>` : ''}</dl></section>`;
    }).join('');
    box.dataset.konto = id;
    box.innerHTML = `
      <section class="lg-kontokopf lg-glas"><div><h2>${esc(p.name)}</h2><div class="lg-meta">${meta}</div>
        ${p.lieferanten ? `<p class="lg-notiz">Lieferanten über dieses Konto: ${esc(p.lieferanten)}</p>` : ''}${p.notiz ? `<p class="lg-notiz">${esc(p.notiz)}</p>` : ''}</div>
        <div class="lg-knopfreihe">${knoepfe}</div></section>
      <div class="lg-salden">${karten || '<p class="lg-leer-text lg-glas">Noch keine Bewegungen.</p>'}</div>
      <p class="lg-hilfe">„Bestätigt“ ist unser Saldo bis zum Stichtag des letzten bestätigten Auszugs, „offen“ alles danach. + der Partner schuldet uns · − wir schulden dem Partner.</p>
      <section class="lg-panel lg-glas"><div class="lg-panelkopf"><h2>Abstimmungen</h2></div>${abstTabelle(k.abstimmungen, false)}</section>
      <section class="lg-panel lg-glas"><div class="lg-panelkopf"><h2>Bewegungen</h2><span class="lg-hilfe">${((n) => `${zahl(n)} ${n === 1 ? 'Buchung' : 'Buchungen'}`)(k.bewegungen.filter((b) => !b.storno).length)}${ko.letzteBewegung ? ', zuletzt am ' + esc(datum(ko.letzteBewegung)) : ''}</span></div>${bewegungsTabelle(k, lms)}</section>`;
  }
  function saldoMail(p, ko) {
    const s = obj(ko.saldo);
    const zeilen = kontoLms(p, []).map((id) => { const n = s[id] || 0; return `${lm(id).name}: ${n === 0 ? 'ausgeglichen' : zahl(Math.abs(n)) + ' Stück ' + (n > 0 ? 'zu unseren Gunsten' : 'zu Ihren Gunsten')}`; });
    const heute = datum(S.d.heute);
    const text = `Guten Tag,\n\nnach unserer Buchhaltung beträgt der Leergutsaldo zum ${heute}:\n\n${zeilen.join('\n')}\n\nBitte bestätigen Sie uns den Saldo oder senden Sie uns Ihren Kontoauszug.\n\nMit freundlichen Grüßen\n${S.d.name || ''}\nStandard-Fleisch`;
    return `mailto:${p.email.replace(/\s/g, '')}?subject=${encodeURIComponent('Leergutsaldo zum ' + heute + (p.kontoNr ? ' – Konto ' + p.kontoNr : ''))}&body=${encodeURIComponent(text)}`;
  }
  function bewegungsTabelle(k, lms) {
    if (!k.bewegungen.length) return '<p class="lg-leerzeile">Noch keine Bewegungen auf diesem Konto.</p>';
    const lauf = {}; const zeilen = [];
    for (const b of k.bewegungen) {
      const d = delta(b);
      if (!b.storno) for (const [id, n] of Object.entries(d)) lauf[id] = (lauf[id] || 0) + n;
      zeilen.push({ b, d, stand: { ...lauf } });
    }
    zeilen.reverse();
    const zeigen = S.alleBew ? zeilen : zeilen.slice(0, 150);
    const html = zeigen.map(({ b, d, stand }) => `<tr class="${b.storno ? 'lg-storniert' : ''}">
        <td data-label="Datum">${esc(datum(b.datum))}</td><td data-label="Art">${esc(S.d.typen[b.typ] || b.typ)}${b.quelle === 'import' ? '<span class="lg-sub">aus Excel</span>' : ''}</td>
        <td class="lg-voll">${b.beleg ? `<b>${esc(b.beleg)}</b> ` : ''}${esc(b.text)}${b.storno ? `<span class="lg-sub lg-ohne-strich">storniert von ${esc(b.storno.von)}: ${esc(b.storno.grund)}</span>` : ''}</td>
        ${lms.map((id) => `<td class="lg-zahl${d[id] ? '' : ' lg-mobil-weg'}" data-label="${esc(kurz(id))}">${d[id] ? vzHtml(d[id]) + `<span class="lg-sub">= ${vz(stand[id] || 0)}</span>` : '<span class="lg-null">·</span>'}</td>`).join('')}
        <td class="lg-zahl lg-ohne-strich">${!b.storno && darf('bearbeiten') ? `<button class="btn sm ghost" type="button" data-storno="${esc(b.id)}">Stornieren</button>` : ''}</td></tr>`).join('');
    return `<div class="lg-tabelle-wrap"><table class="lg-tabelle lg-karten"><thead><tr><th>Datum</th><th>Art</th><th>Beleg / Text</th>${lms.map((id) => `<th class="lg-zahl">${esc(kurz(id))}<small>Bewegung · Saldo</small></th>`).join('')}<th></th></tr></thead><tbody>${html}</tbody></table></div>
      ${zeilen.length > zeigen.length ? `<div class="lg-knopfreihe"><button class="btn sm" type="button" data-k-aktion="alle">Alle ${zahl(zeilen.length)} Bewegungen zeigen</button></div>` : ''}`;
  }
  $('#lg-k-detail').addEventListener('click', (ev) => {
    const a = ev.target.closest('[data-k-aktion]'), st = ev.target.closest('[data-storno]'), ab = ev.target.closest('[data-abst]');
    if (st) { oeffneStorno(st.dataset.storno); return; }
    if (ab) { oeffneAuszug({ id: ab.dataset.abst }); return; }
    if (!a) return;
    if (a.dataset.kAktion === 'bewegung') oeffneBewegung(S.kontoId);
    if (a.dataset.kAktion === 'auszug') oeffneAuszug({ partner: S.kontoId });
    if (a.dataset.kAktion === 'partner') oeffnePartner(S.kontoId);
    if (a.dataset.kAktion === 'alle') { S.alleBew = true; zeigeKonto(S.kontoId, false); }
  });

  /* ---------- Abstimmungen ---------- */
  function abstTabelle(liste, mitPartner) {
    if (!liste.length) return '<p class="lg-leerzeile">Keine Abstimmungen.</p>';
    return `<div class="lg-tabelle-wrap"><table class="lg-tabelle lg-karten"><thead><tr>${mitPartner ? '<th>Partner</th>' : ''}<th>Stichtag</th><th>Eingang</th><th>Frist</th><th>Saldo laut Partner</th><th>Unser Saldo</th><th>Differenz</th><th>Status</th></tr></thead><tbody>
      ${liste.map((a) => `<tr class="lg-klick" data-abst="${esc(a.id)}">${mitPartner ? `<td class="lg-voll"><span class="lg-name">${esc(partnerName(a.partner))}</span>${a.quelle ? `<span class="lg-sub">${esc(a.quelle)}</span>` : ''}</td>` : ''}
        <td data-label="Stichtag">${esc(datum(a.stichtag))}</td><td data-label="Eingang">${esc(datum(a.eingang)) || '—'}</td>
        <td data-label="Frist">${a.fristBis ? esc(datum(a.fristBis)) + (a.status === 'offen' ? ' ' + fristChip(a) : '') : '—'}</td>
        <td data-label="Laut Partner">${mengen(a.saldo, { leer: 'ausgeglichen' })}</td><td data-label="Unser Saldo">${mengen(a.eigenJetzt, { leer: 'ausgeglichen' })}</td>
        <td data-label="Differenz">${leerMap(a.differenz) ? '<span class="lg-chip gruen">keine</span>' : mengen(a.differenz)}</td>
        <td data-label="Status">${statusChip(a.status, S.d.abstStatus)}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function renderAbstimmungen() {
    const sel = $('#lg-a-partner'), v = sel.value;
    const mit = [...new Set(S.d.abstimmungen.map((a) => a.partner))].map((id) => S.pmap.get(id)).filter(Boolean).sort(nachName);
    sel.innerHTML = '<option value="">Alle Partner</option>' + mit.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    sel.value = mit.some((p) => p.id === v) ? v : '';
    const st = $('#lg-a-status').value;
    const liste = S.d.abstimmungen.filter((a) => (!st || a.status === 'offen' || a.status === 'widersprochen') && (!sel.value || a.partner === sel.value))
      .sort((a, b) => (st ? ((a.fristBis ? a.restTage ?? 9999 : 9999) - (b.fristBis ? b.restTage ?? 9999 : 9999)) : 0) || String(b.stichtag).localeCompare(a.stichtag) || partnerName(a.partner).localeCompare(partnerName(b.partner), 'de'));
    $('#lg-a-liste').innerHTML = liste.length ? abstTabelle(liste, true) : `<p class="lg-leerzeile">${st ? 'Keine offenen oder widersprochenen Auszüge.' : 'Noch keine Abstimmungen erfasst.'}</p>`;
  }
  ['#lg-a-status', '#lg-a-partner'].forEach((s) => $(s).addEventListener('input', renderAbstimmungen));
  $('#lg-a-liste').addEventListener('click', (ev) => { const r = ev.target.closest('[data-abst]'); if (r) oeffneAuszug({ id: r.dataset.abst }); });

  /* ---------- Abschreibungen ---------- */
  const abWert = (m) => { let e = 0, voll = true; for (const [k, n] of Object.entries(obj(m))) { const w = lm(k).wert; if (w === null || w === undefined) voll = false; else e += n * w; } return { e, voll }; };
  function renderAbschreibungen() {
    const st = $('#lg-d-status').value, q = $('#lg-d-suche').value.trim().toLocaleLowerCase('de-DE');
    const basis = S.d.abschreibungen.filter((x) => !st || x.status === st);
    const jeKunde = new Map(); basis.forEach((x) => jeKunde.set(x.empfaenger, (jeKunde.get(x.empfaenger) || 0) + 1));
    if (S.kunde && !jeKunde.has(S.kunde)) S.kunde = '';
    const kunden = [...jeKunde.entries()].sort((a, b) => b[1] - a[1]);
    $('#lg-d-kunden').innerHTML = kunden.length > 1 ? `<div class="lg-kunden" role="group" aria-label="Nach Kunde filtern">${kunden.slice(0, 14).map(([k, n]) => `<button type="button" data-kunde="${esc(k)}" aria-pressed="${k === S.kunde}">${esc(k)} <b>${zahl(n)}</b></button>`).join('')}</div>` : '';
    const liste = basis.filter((x) => (!S.kunde || x.empfaenger === S.kunde) && (!q || [x.empfaenger, x.empfaengerNr, x.ort, x.sendung, x.rechnung, x.notiz].join(' ').toLocaleLowerCase('de-DE').includes(q)))
      .sort((a, b) => String(b.zugestellt).localeCompare(a.zugestellt));
    const summe = {}; liste.forEach((x) => { for (const [k, n] of Object.entries(obj(x.menge))) summe[k] = (summe[k] || 0) + n; });
    const sw = abWert(summe);
    $('#lg-d-liste').innerHTML = liste.length ? `<table class="lg-tabelle lg-karten"><thead><tr><th>Zugestellt</th><th>Empfänger</th><th>Sendung</th><th>Menge</th><th class="lg-zahl">Wert</th><th>Status</th><th>WinAB</th></tr></thead><tbody>
      ${liste.map((x) => { const w = abWert(x.menge); return `<tr class="${darf('bearbeiten') ? 'lg-klick' : ''}" data-abschr="${esc(x.id)}">
        <td data-label="Zugestellt">${esc(datum(x.zugestellt))}</td><td class="lg-voll"><span class="lg-name">${esc(x.empfaenger)}</span><span class="lg-sub">${esc([x.empfaengerNr, x.ort].filter(Boolean).join(' · '))}</span></td>
        <td data-label="Sendung">${esc(x.sendung) || '—'}</td><td data-label="Menge">${mengen(x.menge, { vorzeichen: false })}</td>
        <td class="lg-zahl" data-label="Wert">${w.e ? euro(w.e) : '—'}</td><td data-label="Status">${statusChip(x.status, S.d.abschrStatus)}</td><td data-label="WinAB">${esc(x.rechnung) || '—'}</td></tr>`; }).join('')}</tbody>
      <tfoot><tr><td class="lg-voll">${zahl(liste.length)} ${liste.length === 1 ? 'Fall' : 'Fälle'}</td><td></td><td></td><td data-label="Menge">${mengen(summe, { vorzeichen: false })}</td><td class="lg-zahl" data-label="Wert">${sw.e ? euro(sw.e) : '—'}</td><td></td><td></td></tr></tfoot></table>`
      : `<p class="lg-leerzeile">${st === 'offen' ? 'Keine offenen Abschreibungen.' : 'Keine Abschreibungen gefunden.'}</p>`;
  }
  ['#lg-d-status', '#lg-d-suche'].forEach((s) => $(s).addEventListener('input', renderAbschreibungen));
  $('#lg-d-kunden').addEventListener('click', (ev) => { const b = ev.target.closest('[data-kunde]'); if (b) { S.kunde = S.kunde === b.dataset.kunde ? '' : b.dataset.kunde; renderAbschreibungen(); } });
  $('#lg-d-liste').addEventListener('click', (ev) => { const r = ev.target.closest('[data-abschr]'); if (r && darf('bearbeiten')) oeffneAbschreibung(r.dataset.abschr); });
  $('#lg-d-neu').addEventListener('click', () => oeffneAbschreibung(''));

  /* Dachser-Liste einlesen: Text der Mail oder .eml → Vorschau (Server liest und gleicht ab) → übernehmen */
  const gleicheMengen = (a, b) => { const x = obj(a), y = obj(b); return Object.keys({ ...x, ...y }).every((k) => (x[k] || 0) === (y[k] || 0)); };
  function dachserZuruecksetzen() { S.dachser = null; $('#dl-uebernehmen').disabled = true; $('#dl-vorschau').innerHTML = ''; $('#dl-meldung').textContent = ''; $('#dl-meldung').className = 'lg-meldung'; }
  $('#lg-d-dachser').addEventListener('click', () => { $('#dl-text').value = ''; $('#dl-dateiname').textContent = ''; dachserZuruecksetzen(); oeffne($('#dlg-dachser')); $('#dl-text').focus(); });
  $('#dl-text').addEventListener('input', () => { $('#dl-dateiname').textContent = ''; dachserZuruecksetzen(); });
  $('#dl-datei').addEventListener('change', async (ev) => {
    const f = ev.target.files[0]; ev.target.value = '';
    if (!f) return;
    dachserZuruecksetzen();
    if (f.size > 2 * 1024 * 1024) { $('#dl-meldung').textContent = 'Die Datei ist zu groß (höchstens 2 MB).'; return; }
    const b = new Uint8Array(await f.arrayBuffer());
    let t;
    try { t = new TextDecoder('utf-8', { fatal: true }).decode(b); } catch { t = new TextDecoder('windows-1252').decode(b); }
    $('#dl-text').value = t; $('#dl-dateiname').textContent = f.name;
    dachserPruefen();
  });
  async function dachserPruefen() {
    const text = $('#dl-text').value, m = $('#dl-meldung');
    dachserZuruecksetzen();
    if (!text.trim()) { m.textContent = 'Bitte zuerst den Text der Mail einfügen oder die Mail als Datei wählen.'; return; }
    $('#dl-pruefen').disabled = true;
    const r = await api('leergut_dachser_import', { text, vorschau: true });
    $('#dl-pruefen').disabled = false;
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { m.textContent = fehlerText(r, 'Die Liste konnte nicht geprüft werden'); return; }
    const d = r.data;
    if (d.fehler.length) { $('#dl-vorschau').innerHTML = `<p class="lg-meldung">${zahl(d.fehler.length)} unlesbare Zeilen – nichts übernommen:</p><ul class="lg-fehlerliste">${d.fehler.map((x) => `<li>Zeile ${zahl(x.zeile)}: ${esc(x.text)}</li>`).join('')}</ul>`; return; }
    if (d.text) $('#dl-text').value = d.text;   // gespeicherte Mail (.eml): lesbarer Text statt Mailquelltext
    const z = d.zahlen, lmName = (id) => esc(kurz(id));
    const kacheln = [['zeilen', z.zeilen, 'Zeilen in der Liste'], ['sendungen', z.sendungen, 'Sendungen'], ['neu', z.neu, 'Neu'], ['ergaenzt', z.ergaenzt, 'Ergänzt'],
      ['schon', z.schon, 'Schon erfasst'], ['abweichend', z.abweichend, 'Andere Menge']];
    const saldoOk = !leerMap(d.saldo) && gleicheMengen(d.summe, d.saldo);
    $('#dl-vorschau').innerHTML = `<div class="lg-vorschau">${kacheln.map(([k, n, t]) => `<div data-z="${k}"><b>${zahl(n)}</b><span>${t}</span></div>`).join('')}</div>
      <p class="lg-wsumme">Summe der Liste${d.per ? ' per ' + esc(datum(d.per)) : ''}: ${mengen(d.summe, { vorzeichen: false })}
        ${leerMap(d.saldo) ? '<span class="lg-chip">ohne Saldo laut Dachser</span>' : saldoOk ? '<span class="lg-chip gruen">stimmt mit dem Saldo laut Dachser überein</span>'
          : `<span class="lg-chip rot">Saldo laut Dachser: ${esc(Object.entries(d.saldo).map(([k, n]) => kurz(k) + ' ' + zahl(n)).join(' · '))}</span>`}</p>
      ${z.ignoriert ? `<p class="lg-hinweis">${zahl(z.ignoriert)} ${z.ignoriert === 1 ? 'neuer Fall' : 'neue Fälle'} bei REWE nur mit H1 – laut Leitfaden „Nicht zu beachten“.</p>` : ''}
      ${d.doppelt.length ? `<p class="lg-meldung">Mehrfach in der Liste – Dachser rechnet sie mehrfach ab, ggf. widersprechen:</p><ul class="lg-fehlerliste">${d.doppelt.map((x) => `<li>Sendung ${esc(x.sendung)} (${esc(x.empfaenger)}): ${lmName(x.lm)}</li>`).join('')}</ul>` : ''}
      ${d.abweichend.length ? `<p class="lg-meldung">Andere Menge als erfasst – nicht geändert, bitte prüfen:</p><ul class="lg-fehlerliste">${d.abweichend.map((x) => `<li>Sendung ${esc(x.sendung)} (${esc(x.empfaenger)}): erfasst ${lmName(x.lm)} ${zahl(x.erfasst)}, laut Dachser ${zahl(x.dachser)}</li>`).join('')}</ul>` : ''}
      ${Object.keys(obj(d.unbekannt)).length ? `<p class="lg-meldung">Nicht übernommen, weil das Packmittel im Modul fehlt: ${esc(Object.entries(d.unbekannt).map(([k, n]) => `${k} (${zahl(n)})`).join(', '))}.</p>` : ''}`;
    if (!z.neu && !z.ergaenzt) { m.className = 'lg-meldung ok'; m.textContent = 'Alles schon erfasst – es gibt nichts Neues.'; return; }
    S.dachser = d.text || text; $('#dl-uebernehmen').disabled = false;
  }
  $('#dl-pruefen').addEventListener('click', dachserPruefen);
  $('#dl-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (!S.dachser) return;
    const knopf = $('#dl-uebernehmen'), m = $('#dl-meldung');
    knopf.disabled = true;
    const r = await api('leergut_dachser_import', { text: S.dachser });
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { knopf.disabled = false; m.className = 'lg-meldung'; m.textContent = fehlerText(r, 'Übernehmen fehlgeschlagen'); return; }
    const z = r.data.zahlen;
    $('#dlg-dachser').close();
    toast(`Dachser-Liste übernommen: ${zahl(z.neu)} neu, ${zahl(z.ergaenzt)} ergänzt`);
    await neuLaden();
  });

  /* ---------- Bilanz und Inventur ---------- */
  async function ladeBilanz() {
    const feld = $('#lg-b-tag');
    if (!feld.value) feld.value = S.d.heute;
    const r = await api('leergut_bilanz', null, '&stichtag=' + encodeURIComponent(feld.value));
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { $('#lg-b-tabelle').innerHTML = `<p class="lg-meldung">${esc(fehlerText(r, 'Bilanz konnte nicht berechnet werden'))}</p>`; return; }
    const b = S.bilanz = r.data.bilanz;
    const ids = new Set(); b.zeilen.forEach((z) => Object.keys(obj(z.saldo)).forEach((k) => ids.add(k))); Object.keys(obj(b.bestand)).forEach((k) => ids.add(k));
    if (!ids.size) { ids.add('e2'); ids.add('h1'); }
    const lms = sortiertLm(ids), mehr = mehrereFirmen();
    const zelle = (m, id) => { const n = obj(m)[id] || 0; return `<td class="lg-zahl lg-mobil-weg">${n ? vzHtml(n) : '<span class="lg-null">·</span>'}</td>`; };
    const mobil = (m) => `<td class="lg-nur-mobil" data-label="Saldo">${mengen(m, { leer: 'ausgeglichen' })}</td>`;
    const zeile = (titel, m, e, cls = 'lg-summe') => `<tr class="${cls}"><td class="lg-voll" colspan="2">${titel}</td>${lms.map((id) => zelle(m, id)).join('')}${mobil(m)}<td class="lg-zahl" data-label="Wert">${euro(e.betrag)}${e.vollstaendig ? '' : '*'}</td><td></td></tr>`;
    const einzeln = b.zeilen.filter((z) => !istWinab(S.pmap.get(z.partner))), wz = {};
    b.zeilen.filter((z) => istWinab(S.pmap.get(z.partner))).forEach((z) => {
      const g = wz[z.mandant] = wz[z.mandant] || { partner: '', kunden: true, name: '', n: 0, art: 'kunde', mandant: z.mandant, saldo: {}, abstimmung: null };
      g.n++; for (const [k, n] of Object.entries(obj(z.saldo))) g.saldo[k] = (g.saldo[k] || 0) + n;
    });
    Object.values(wz).forEach((g) => { g.name = `Kunden aus WinAB (${zahl(g.n)} Konten)`; g.euro = euroVon(g.saldo); einzeln.push(g); });
    const nach = einzeln.sort((x, y) => (x.mandant === y.mandant ? 0 : x.mandant === 'standard' ? -1 : 1) || String(x.name).localeCompare(y.name, 'de'));
    let html = '', letzte = null;
    for (const z of nach) {
      if (mehr && z.mandant !== letzte) {
        if (letzte !== null) html += zeile('Summe ' + esc(S.d.mandanten[letzte]), b.jeMandant[letzte], euroVon(b.jeMandant[letzte]));
        html += `<tr class="lg-gruppe"><td class="lg-voll" colspan="${lms.length + 4}"><b>${esc(S.d.mandanten[z.mandant] || z.mandant)}</b></td></tr>`;
        letzte = z.mandant;
      }
      html += `<tr class="lg-klick" ${z.kunden ? 'data-kunden="1"' : `data-konto="${esc(z.partner)}"`}><td class="lg-voll"><span class="lg-name">${esc(z.name)}</span></td><td data-label="Art">${esc(S.d.arten[z.art] || z.art)}</td>
        ${lms.map((id) => zelle(z.saldo, id)).join('')}${mobil(z.saldo)}<td class="lg-zahl" data-label="Wert">${z.euro.betrag ? euro(z.euro.betrag) + (z.euro.vollstaendig ? '' : '*') : '—'}</td>
        <td data-label="Letzte Abstimmung">${z.abstimmung ? esc(datum(z.abstimmung.stichtag)) + ' ' + statusChip(z.abstimmung.status, S.d.abstStatus) : '<span class="lg-null">—</span>'}</td></tr>`;
    }
    if (mehr && letzte !== null) html += zeile('Summe ' + esc(S.d.mandanten[letzte]), b.jeMandant[letzte], euroVon(b.jeMandant[letzte]));
    html += zeile('Summe aller Konten', b.summe, b.euro.konten);
    if (b.inventur) html += zeile(`Eigener Bestand (Inventur ${esc(datum(b.inventur.stichtag))})`, b.bestand, b.euro.bestand);
    html += zeile('<b>Gesamt</b>', b.gesamt, b.euro.gesamt);
    $('#lg-b-tabelle').innerHTML = b.zeilen.length || b.inventur ? `<table class="lg-tabelle lg-karten"><thead><tr><th>Konto</th><th>Art</th>${lms.map((id) => `<th class="lg-zahl">${esc(kurz(id))}</th>`).join('')}<th class="lg-zahl">Wert</th><th>Letzte Abstimmung</th></tr></thead><tbody>${html}</tbody></table>`
      : '<p class="lg-leerzeile">Zum Stichtag gibt es noch keine Salden.</p>';
    const ohneWert = S.d.lademittel.filter((l) => ids.has(l.id) && (l.wert === null || l.wert === undefined)).map((l) => l.name);
    $('#lg-b-fuss').textContent = `Bewertung: ${S.d.lademittel.filter((l) => l.wert !== null && l.wert !== undefined).map((l) => `${l.name} ${euro(l.wert)}`).join(', ') || 'keine Werte hinterlegt'}.`
      + (ohneWert.length ? ` * ohne Wert: ${ohneWert.join(', ')}.` : '') + (b.inventur ? '' : ' Für den eigenen Bestand fehlt eine Inventur bis zum Stichtag.');
  }
  const euroVon = (m) => { let e = 0, v = true; for (const [k, n] of Object.entries(obj(m))) { const w = lm(k).wert; if (w === null || w === undefined) v = false; else e += n * w; } return { betrag: Math.round(e * 100) / 100, vollstaendig: v }; };
  $('#lg-b-tag').addEventListener('change', ladeBilanz);
  $('#lg-b-tabelle').addEventListener('click', (ev) => { if (ev.target.closest('[data-kunden]')) { zeigeKunden(); return; } const r = ev.target.closest('[data-konto]'); if (r) zeigeTab('konten', r.dataset.konto); });
  /* CSV vom Server (Bilanz oder Abholliste) herunterladen – der Server vermerkt es im Protokoll */
  async function ladeCsv(body, dateiname) {
    let res;
    try {
      res = await fetch(API + '?action=leergut_export', { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': S.csrf }, body: JSON.stringify(body) });
    } catch { toast('Keine Verbindung zum Server.', true); return; }
    if (res.status === 401) { zeigeAnmeldung(); return; }
    if (!res.ok) { let d = {}; try { d = await res.json(); } catch { /* keine JSON-Antwort */ } toast(d.error || `CSV konnte nicht erstellt werden (${res.status}).`, true); return; }
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob()); a.download = dateiname;
    document.body.append(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
  }
  $('#lg-b-csv').addEventListener('click', () => { const tag = $('#lg-b-tag').value || S.d.heute; ladeCsv({ stichtag: tag }, `Leergut-Bilanz_${tag}.csv`); });
  function renderInventur() {
    const liste = [...S.d.inventur].sort((a, b) => String(b.stichtag).localeCompare(a.stichtag));
    $('#lg-i-liste').innerHTML = liste.length ? `<table class="lg-tabelle lg-karten"><thead><tr><th>Stichtag</th><th>Positionen</th><th>Bestand</th><th>Notiz</th></tr></thead><tbody>
      ${liste.map((i) => { const s = {}; i.positionen.forEach((p) => { for (const [k, n] of Object.entries(obj(p.werte))) s[k] = (s[k] || 0) + n; });
        return `<tr class="${darf('bearbeiten') ? 'lg-klick' : ''}" data-inventur="${esc(i.id)}"><td class="lg-name" data-label="Stichtag">${esc(datum(i.stichtag))}</td>
        <td data-label="Positionen">${i.positionen.map((p) => esc(p.name)).join(', ')}</td><td data-label="Bestand">${mengen(s, { vorzeichen: false })}</td><td data-label="Notiz">${esc(i.notiz)}</td></tr>`; }).join('')}</tbody></table>`
      : '<p class="lg-leerzeile">Noch keine Inventur erfasst.</p>';
  }
  $('#lg-i-liste').addEventListener('click', (ev) => { const r = ev.target.closest('[data-inventur]'); if (r && darf('bearbeiten')) oeffneInventur(r.dataset.inventur); });
  $('#lg-i-neu').addEventListener('click', () => oeffneInventur(''));

  /* ---------- Einstellungen ---------- */
  function renderEinstellungen() {
    const nWinab = S.d.partner.filter(istWinab).length;
    $('#lg-e-kunden-zeile').hidden = !nWinab; $('#lg-e-kunden-text').textContent = `Kundenkonten aus WinAB zeigen (${zahl(nWinab)})`;
    const liste = S.d.partner.filter((p) => $('#lg-e-kunden').checked || !istWinab(p)).sort((a, b) => (a.aktiv === b.aktiv ? 0 : a.aktiv ? -1 : 1) || nachName(a, b));
    $('#lg-e-partner').innerHTML = liste.length ? `<table class="lg-tabelle lg-karten"><thead><tr><th>Name</th><th>Art</th><th>Firma</th><th class="lg-zahl">Frist</th><th>E-Mail</th><th>Lademittel</th><th></th></tr></thead><tbody>
      ${liste.map((p) => `<tr class="lg-klick" data-partner="${esc(p.id)}"><td class="lg-voll"><span class="lg-name">${esc(p.name)}</span>${p.kontoNr || p.kundenNr ? `<span class="lg-sub">${[p.kontoNr ? 'Konto-Nr. ' + esc(p.kontoNr) : '', p.kundenNr ? 'WinAB-Kd. ' + esc(p.kundenNr) : ''].filter(Boolean).join(' · ')}</span>` : ''}</td>
        <td data-label="Art">${esc(S.d.arten[p.art] || p.art)}</td><td data-label="Firma">${esc(S.d.mandanten[p.mandant] || p.mandant)}</td>
        <td class="lg-zahl" data-label="Frist">${p.fristTage ? zahl(p.fristTage) + ' Tage' : '—'}</td><td data-label="E-Mail">${esc(p.email) || '—'}</td>
        <td data-label="Lademittel">${(p.lademittel || []).map((id) => esc(kurz(id))).join(', ')}</td><td>${p.aktiv ? '' : '<span class="lg-chip">inaktiv</span>'}</td></tr>`).join('')}</tbody></table>`
      : '<p class="lg-leerzeile">Noch keine Partner – einzeln anlegen oder das Datenpaket übernehmen.</p>';
    $('#lg-e-lm').innerHTML = S.d.lademittel.map((l) => lmZeile(l)).join('');
  }
  const lmZeile = (l) => `<tr data-id="${esc(l.id || '')}"><td data-label="Bezeichnung"><input class="lg-eingabe" data-f="name" maxlength="40" value="${esc(l.name || '')}" aria-label="Bezeichnung"></td>
    <td class="lg-zahl" data-label="Wert je Stück (€)"><input class="lg-eingabe" data-f="wert" inputmode="decimal" maxlength="10" value="${l.wert === null || l.wert === undefined ? '' : esc(Number(l.wert).toFixed(2).replace('.', ','))}" aria-label="Wert je Stück in Euro" placeholder="ohne Wert"></td>
    <td data-label="Aktiv"><input type="checkbox" data-f="aktiv" ${l.aktiv !== false ? 'checked' : ''} aria-label="aktiv"></td></tr>`;
  $('#lg-e-partner-neu').addEventListener('click', () => oeffnePartner(''));
  $('#lg-e-kunden').addEventListener('change', renderEinstellungen);
  $('#lg-e-partner').addEventListener('click', (ev) => { const r = ev.target.closest('[data-partner]'); if (r) oeffnePartner(r.dataset.partner); });
  $('#lg-e-lm-plus').addEventListener('click', () => { $('#lg-e-lm').insertAdjacentHTML('beforeend', lmZeile({ name: '', wert: null, aktiv: true })); $('#lg-e-lm tr:last-child input').focus(); });
  $('#lg-e-lm-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const lademittel = $$('#lg-e-lm tr').map((tr) => ({ ...(tr.dataset.id ? { id: tr.dataset.id } : {}), name: $('[data-f="name"]', tr).value.trim(), wert: $('[data-f="wert"]', tr).value.trim(), aktiv: $('[data-f="aktiv"]', tr).checked }))
      .filter((l) => l.id || l.name);
    const d = await senden(ev.target, 'leergut_lademittel_save', { lademittel });
    if (d) { toast('Lademittel gespeichert'); await neuLaden(); }
  });

  /* Datenpaket: Datei lesen → Vorschau prüfen → übernehmen */
  $('#lg-e-datei').addEventListener('change', async (ev) => {
    const f = ev.target.files[0], m = $('#lg-e-import-meldung');
    S.paket = null; $('#lg-e-vorschau').innerHTML = ''; $('#lg-e-import-knoepfe').hidden = true; m.textContent = ''; m.className = 'lg-meldung';
    if (!f) return;
    $('#lg-e-dateiname').textContent = f.name;
    if (f.size > 5.5 * 1024 * 1024) { m.textContent = 'Die Datei ist zu groß (höchstens 5,5 MB).'; return; }
    let paket;
    try { paket = JSON.parse(await f.text()); } catch { m.textContent = 'Die Datei ist kein gültiges Datenpaket (JSON).'; return; }
    const r = await api('leergut_import', { paket, vorschau: true });
    ev.target.value = '';
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { m.textContent = fehlerText(r, 'Das Datenpaket konnte nicht geprüft werden'); return; }
    const z = r.data.zahlen, fe = r.data.fehler || [];
    const teile = { partner: 'Partner', bewegungen: 'Bewegungen', abstimmungen: 'Abstimmungen', abschreibungen: 'Abschreibungen', inventur: 'Inventuren', lademittel: 'Lademittel' };
    $('#lg-e-vorschau').innerHTML = `<div class="lg-vorschau">${Object.entries(teile).map(([k, v]) => `<div><b>${zahl(z[k] || 0)}</b><span>${v}</span></div>`).join('')}</div>
      ${fe.length ? `<p class="lg-meldung">${zahl(fe.length)} Fehler – das Paket wird erst übernommen, wenn alle behoben sind:</p><ul class="lg-fehlerliste">${fe.map((x) => `<li>${esc(teile[x.teil] || x.teil)}, Eintrag ${zahl(x.zeile)}: ${esc(x.text)}</li>`).join('')}</ul>` : ''}`;
    if (fe.length) return;
    S.paket = paket;
    $('#lg-e-import-knoepfe').hidden = false;
    $('#lg-e-ersetzen-zeile').hidden = r.data.leer;
    $('#lg-e-ersetzen').checked = false;
    $('#lg-e-uebernehmen').disabled = !r.data.leer;
    m.className = 'lg-meldung ok';
    m.textContent = r.data.leer ? 'Das Paket ist fehlerfrei und kann übernommen werden.' : 'Das Paket ist fehlerfrei. Im Modul sind schon Daten – sie werden beim Übernehmen vollständig ersetzt.';
  });
  $('#lg-e-ersetzen').addEventListener('change', (ev) => { $('#lg-e-uebernehmen').disabled = !ev.target.checked; });
  $('#lg-e-uebernehmen').addEventListener('click', async (ev) => {
    if (!S.paket) return;
    const m = $('#lg-e-import-meldung');
    ev.target.disabled = true;
    const r = await api('leergut_import', { paket: S.paket, ersetzen: $('#lg-e-ersetzen').checked });
    ev.target.disabled = false;
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { m.className = 'lg-meldung'; m.textContent = fehlerText(r, 'Übernehmen fehlgeschlagen'); return; }
    S.paket = null; $('#lg-e-import-knoepfe').hidden = true; $('#lg-e-vorschau').innerHTML = ''; $('#lg-e-dateiname').textContent = 'Keine Datei gewählt'; m.textContent = '';
    const z = r.data.zahlen;
    toast(`Übernommen: ${zahl(z.partner)} Partner, ${zahl(z.bewegungen)} Bewegungen, ${zahl(z.abstimmungen)} Abstimmungen`);
    S.kontoId = '';
    await neuLaden();
    zeigeTab('uebersicht');
  });

  /* ---------- WinAB-Bericht „Lademittelbewegungen Kunden“ (.XLS) ----------
     Der Browser liest den Bericht (StockCore, wie die Bestandsliste) und erkennt die Zeilen an ihrem Inhalt, nicht an
     festen Spalten: Kopf je Kunde und Lademittel („Lademittel“, Nr., Name), Bewegungen (Kd.-Nr., Name, Belegnr.,
     Belegart, Datum TTMMJJJJ, Zugang/Abgang, Menge), Summenzeilen, Berichtsdatum und Auswertungszeitraum.
     Übernommen werden Lieferscheine, Gutschriften und Rechnungen. Sammelrechnungen wiederholen die Lieferscheine,
     Offerten bewegen nichts, Karton ist kein Leergut. Den Abgleich (neu, gleich, geändert, ausgeglichen) macht der Server. */
  const WINAB_ARTEN = ['Lieferschein', 'Gutschrift', 'Rechnung'];
  const normName = (t) => String(t || '').toLowerCase().replace(/[^a-z0-9äöüß]+/g, '');
  function winabLm(name) {
    const n = normName(name);
    if (n.includes('karton')) return '-';
    const gleich = S.d.lademittel.find((l) => normName(l.name) === n);
    if (gleich) return gleich.id;
    const id = n.startsWith('e2') ? 'e2' : n.startsWith('e1') ? 'e1' : n.startsWith('h1') ? 'h1' : n.includes('europalette') ? 'eu'
      : n.includes('kübel') || n.includes('kuebel') ? 'kuebel' : n.includes('haken') ? 'haken' : '';
    return id && S.d.lademittel.some((l) => l.id === id) ? id : '';
  }
  function winabDatum(v) {
    let j, m, t;
    if (typeof v === 'number' && Number.isInteger(v) && v >= 1010000 && v <= 31129999) { const s = String(v).padStart(8, '0'); [t, m, j] = [s.slice(0, 2), s.slice(2, 4), s.slice(4)]; }
    else { const x = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec(String(v ?? '').trim()); if (!x) return ''; [, t, m, j] = x; }
    const d = new Date(Date.UTC(+j, +m - 1, +t));
    return d.getUTCFullYear() === +j && d.getUTCMonth() === +m - 1 && d.getUTCDate() === +t ? d.toISOString().slice(0, 10) : '';
  }
  function leseWinab(sheets, datei) {
    const kunden = new Map(), belege = new Map(), lmNamen = new Map(), fehlerListe = [];
    const daten = new Map();   // je Kunde: erste/letzte Lieferung und letzte Rückgabe laut Bericht – auch aus reinem Tausch
    const info = { zeilen: 0, sammel: 0, karton: 0, andere: {}, unbekannt: {}, ohneBeleg: 0, ohneWirkung: 0, sammelwert: [] };
    let titel = false, stand = '', von = '', bis = '', block = null;
    const fehlerhaft = (i, text) => { if (fehlerListe.length < 20) fehlerListe.push(`Zeile ${i + 1}: ${text}`); };
    for (const sh of sheets) sh.grid.forEach((r, i) => {
      const z = [];
      (r || []).forEach((v) => { if (typeof v === 'string') { v = v.replace(/\s+/g, ' ').trim(); if (v) z.push(v); } else if (typeof v === 'number') z.push(v); });
      if (!z.length) return;
      if (z.includes('Lademittelbewegungen Kunden')) titel = true;
      const dz = z.find((v) => typeof v === 'string' && /^Datum:\s*\d/.test(v));
      if (dz && !stand) stand = winabDatum(dz.replace(/^Datum:\s*/, ''));
      const iA = z.indexOf('Auswertungszeitraum');
      if (iA >= 0) { von = winabDatum(z[iA + 1]); const iB = z.indexOf('bis', iA); bis = iB > 0 ? winabDatum(z[iB + 1]) : ''; return; }
      if (z.includes('Bewegungsart')) return;   // Spaltenkopf
      const iS = z.indexOf('Summe');
      if (iS >= 0 && z[iS + 1] === 'Lademittel') { if (!block && !kunden.size) info.sammelwert.push({ nr: z[iS + 2], wert: typeof z[iS + 3] === 'number' ? z[iS + 3] : 0 }); block = null; return; }
      const iL = z.indexOf('Lademittel'), iK = z.findIndex((v) => typeof v === 'number');
      if (iL > 0 && typeof z[iL + 1] === 'number' && iK >= 0 && iK < iL) {
        const kd = String(z[iK]), name = z.slice(iK + 1, iL).filter((v) => typeof v === 'string').join(' ');
        if (!/^\d{1,12}$/.test(kd)) { fehlerhaft(i, 'Kundennummer nicht lesbar'); block = null; return; }
        lmNamen.set(z[iL + 1], String(z[iL + 2] || ''));
        block = { kd, nr: z[iL + 1], lm: winabLm(z[iL + 2]), lmName: String(z[iL + 2] || 'Lademittel ' + z[iL + 1]) };
        if (!kunden.get(kd)) kunden.set(kd, name);
        return;
      }
      const iB = z.findIndex((v) => v === 'Zugang' || v === 'Abgang');
      if (iB < 3) return;   // Hinweise, Seitenköpfe
      info.zeilen++;
      const menge = z[iB + 1], tag = winabDatum(z[iB - 1]), art = String(z[iB - 2]), kd = String(z[iK]);
      if (!block) { fehlerhaft(i, 'Bewegung ohne Kopfzeile „Lademittel“'); return; }
      if (kd !== block.kd) { fehlerhaft(i, `Kundennummer ${kd} passt nicht zur Kopfzeile (${block.kd})`); return; }
      if (typeof menge !== 'number' || !Number.isInteger(menge)) { fehlerhaft(i, 'Menge nicht lesbar'); return; }
      if (!tag) { fehlerhaft(i, 'Datum nicht lesbar'); return; }
      if (/^sammel/i.test(art)) { info.sammel++; return; }
      if (!WINAB_ARTEN.includes(art)) { info.andere[art] = (info.andere[art] || 0) + 1; return; }
      if (block.lm === '-') { info.karton++; return; }
      if (!block.lm) { info.unbekannt[block.lmName] = (info.unbekannt[block.lmName] || 0) + 1; return; }
      const bn = iB - 3 > iK ? z[iB - 3] : '';
      if (bn === '' || typeof bn !== 'number') { info.ohneBeleg++; return; }
      const dt = daten.get(kd) || { ersteLieferung: '', letzteLieferung: '', letzteRueckgabe: '' };
      if (z[iB] === 'Abgang') { if (!dt.ersteLieferung || tag < dt.ersteLieferung) dt.ersteLieferung = tag; if (tag > dt.letzteLieferung) dt.letzteLieferung = tag; }
      else if (tag > dt.letzteRueckgabe) dt.letzteRueckgabe = tag;
      daten.set(kd, dt);
      const key = `${kd}|${art}|${bn}`;
      const b = belege.get(key) || { kd, art, beleg: String(bn), datum: tag, abgang: {}, zugang: {} };
      if (tag < b.datum) b.datum = tag;
      const seite = z[iB] === 'Abgang' ? b.abgang : b.zugang;
      seite[block.lm] = (seite[block.lm] || 0) + Math.abs(menge);
      belege.set(key, b);
    });
    if (!titel) throw new Error('Das ist nicht der WinAB-Bericht „Lademittelbewegungen Kunden“.');
    if (!von || !bis) throw new Error('Der Auswertungszeitraum am Ende des Berichts fehlt – bitte den vollständigen Bericht verwenden.');
    if (fehlerListe.length) throw new Error('Der Bericht hat nicht das erwartete Format. ' + fehlerListe.slice(0, 5).join(' · '));
    if (stand && stand < bis) bis = stand;   // WinAB nennt „bis 31.12.2078“; gebucht ist bis zum Berichtsdatum
    const liste = [];
    for (const b of belege.values()) {
      for (const s of [b.abgang, b.zugang]) for (const k of Object.keys(s)) if (!s[k]) delete s[k];
      if (leerMap(delta(b))) info.ohneWirkung++; else liste.push(b);
    }
    info.sammelwert = info.sammelwert.map((x) => ({ name: lmNamen.get(x.nr) || 'Lademittel ' + x.nr, wert: x.wert }));
    return { bericht: { datei: String(datei || '').slice(0, 120), von, bis, datum: stand }, kunden: [...kunden].map(([nr, name]) => ({ nr, name: name || 'Kunde ' + nr, ...(daten.get(nr) || {}) })), belege: liste, info };
  }
  function zeigeWinabVorschau(w, r) {
    const z = r.zahlen, inf = w.info;
    const anz = (n, eins, mehr) => (n ? `${zahl(n)} ${n === 1 ? eins : mehr}` : '');
    const weg = [anz(inf.sammel, 'Zeile aus Sammelrechnungen', 'Zeilen aus Sammelrechnungen'), anz(inf.karton, 'Kartonzeile', 'Kartonzeilen'),
      ...Object.entries(inf.andere).map(([a, n]) => `${zahl(n)} × ${a}`), anz(inf.ohneBeleg, 'Zeile ohne Belegnr.', 'Zeilen ohne Belegnr.'),
      anz(inf.ohneWirkung, 'Beleg ohne Wirkung', 'Belege ohne Wirkung') + (inf.ohneWirkung ? ' (gleich viel abgegeben wie zurückgenommen)' : '')].filter(Boolean);
    const unb = Object.entries(inf.unbekannt);
    const kacheln = [['kunden', w.kunden.length, 'Kunden im Bericht'], ['belege', w.belege.length, 'Belege mit Wirkung'], ['neuKd', z.kunden, 'Neue Kundenkonten'],
      ['neu', z.neu, 'Neue Belege'], ['gleich', z.gleich, 'Unverändert'], ['geaendert', z.geaendert, 'Geändert'], ['ausgeglichen', z.ausgeglichen, 'Ausgeglichen']];
    $('#lg-w-vorschau').innerHTML = `<div class="lg-vorschau">${kacheln.map(([k, n, t]) => `<div data-z="${k}"><b>${zahl(n)}</b><span>${t}</span></div>`).join('')}</div>
      <p class="lg-hinweis">Bericht vom ${esc(datum(w.bericht.datum || w.bericht.bis))} · übernommen wird der Zeitraum ${esc(datum(w.bericht.von))} bis ${esc(datum(w.bericht.bis))}.${weg.length ? ' Weggelassen: ' + esc(weg.join(', ')) + '.' : ''}</p>
      ${unb.length ? `<p class="lg-meldung">Nicht übernommen, weil das Lademittel im Modul fehlt: ${esc(unb.map(([n, c]) => `${n} (${zahl(c)} Zeilen)`).join(', '))}. Unter „Lademittel“ anlegen und den Bericht erneut wählen.</p>` : ''}
      ${z.geaendert || z.ausgeglichen ? `<p class="lg-meldung">${zahl(z.geaendert + z.ausgeglichen)} schon übernommene Belege werden storniert${z.geaendert ? ' und neu gebucht' : ''}, weil WinAB sie geändert hat oder sie nicht mehr im Bericht stehen. Den Bericht deshalb immer für alle Lademittel ziehen.</p>` : ''}
      ${z.daten ? `<p class="lg-hinweis">Letzte Lieferung und Rückgabe laut Bericht (auch aus reinem Tausch) für ${zahl(z.daten)} ${z.daten === 1 ? 'Kundenkonto' : 'Kundenkonten'} aktualisiert.</p>` : ''}
      <p class="lg-wsumme">Saldo aller Kundenkonten aus WinAB danach (${zahl(z.konten)} mit Saldo): ${mengen(r.summe, { leer: 'ausgeglichen' })}</p>
      ${inf.sammelwert.length ? `<p class="lg-hinweis">Nur zur Information – Gesamtwert oben im WinAB-Bericht (WinAB-Vorzeichen, Minus = mehr an Kunden abgegeben als zurückgenommen): ${esc(inf.sammelwert.map((x) => `${x.name} ${vz(x.wert)}`).join(' · '))}</p>` : ''}`;
  }
  $('#lg-w-datei').addEventListener('change', async (ev) => {
    const f = ev.target.files[0], m = $('#lg-w-meldung');
    S.winab = null; $('#lg-w-vorschau').innerHTML = ''; $('#lg-w-knoepfe').hidden = true; m.textContent = ''; m.className = 'lg-meldung';
    if (!f) return;
    $('#lg-w-dateiname').textContent = f.name;
    ev.target.value = '';
    if (f.size > 40 * 1024 * 1024) { m.textContent = 'Die Datei ist zu groß (höchstens 40 MB).'; return; }
    let w;
    try {
      const b = new Uint8Array(await f.arrayBuffer());
      if (b[0] === 0x50 && b[1] === 0x4b && !window.OfferCore) throw new Error('Bitte den Bericht so verwenden, wie WinAB ihn speichert (.XLS) – .xlsx wird hier nicht gelesen.');
      w = leseWinab(await window.StockCore.readStockWorkbook(b.buffer), f.name);
    } catch (e) { m.textContent = e && e.message ? e.message : 'Die Datei konnte nicht gelesen werden.'; return; }
    if (!w.belege.length && !w.kunden.length) { m.textContent = 'Im Bericht stehen keine Kundenbewegungen.'; return; }
    m.className = 'lg-meldung ok'; m.textContent = 'Bericht gelesen – Abgleich wird geprüft …';
    const r = await api('leergut_winab_import', { bericht: w.bericht, kunden: w.kunden, belege: w.belege, vorschau: true });
    if (r.status === 401) { zeigeAnmeldung(); return; }
    m.className = 'lg-meldung'; m.textContent = '';
    if (r.status !== 200 || !r.data.ok) { m.textContent = fehlerText(r, 'Der Bericht konnte nicht geprüft werden'); return; }
    if ((r.data.fehler || []).length) {
      $('#lg-w-vorschau').innerHTML = `<p class="lg-meldung">${zahl(r.data.fehler.length)} Fehler – nichts übernommen:</p><ul class="lg-fehlerliste">${r.data.fehler.map((x) => `<li>Beleg ${zahl(x.zeile)}: ${esc(x.text)}</li>`).join('')}</ul>`;
      return;
    }
    zeigeWinabVorschau(w, r.data);
    const z = r.data.zahlen;
    if (!z.kunden && !z.neu && !z.geaendert && !z.ausgeglichen && !z.daten) { m.className = 'lg-meldung ok'; m.textContent = 'Alles schon übernommen – es gibt nichts Neues.'; return; }
    S.winab = w;
    $('#lg-w-knoepfe').hidden = false;
  });
  $('#lg-w-uebernehmen').addEventListener('click', async (ev) => {
    const w = S.winab, m = $('#lg-w-meldung');
    if (!w) return;
    ev.target.disabled = true;
    const r = await api('leergut_winab_import', { bericht: w.bericht, kunden: w.kunden, belege: w.belege });
    ev.target.disabled = false;
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { m.className = 'lg-meldung'; m.textContent = fehlerText(r, 'Übernehmen fehlgeschlagen'); return; }
    S.winab = null; $('#lg-w-knoepfe').hidden = true; $('#lg-w-vorschau').innerHTML = ''; $('#lg-w-dateiname').textContent = 'Keine Datei gewählt';
    const z = r.data.zahlen;
    m.className = 'lg-meldung ok';
    m.textContent = `Übernommen: ${zahl(z.kunden)} neue Kundenkonten, ${zahl(z.neu)} neue Belege, ${zahl(z.geaendert)} geändert, ${zahl(z.ausgeglichen)} ausgeglichen.`;
    toast('WinAB-Bericht übernommen');
    await neuLaden();
  });

  /* ---------- Eingabemasken: gemeinsame Hilfen ---------- */
  $$('.lg-dialog').forEach((dlg) => dlg.addEventListener('click', (ev) => { if (ev.target.closest('[data-schliessen]')) dlg.close(); }));
  function oeffne(dlg) { $$('.lg-meldung', dlg).forEach((m) => { m.textContent = ''; }); $$('[aria-invalid]', dlg).forEach((x) => x.removeAttribute('aria-invalid')); dlg.showModal(); }
  async function senden(form, action, body) {
    const knopf = form.querySelector('[type="submit"]'), m = form.querySelector('.lg-meldung');
    m.textContent = ''; m.className = 'lg-meldung';
    knopf.disabled = true;
    const r = await api(action, body);
    knopf.disabled = false;
    if (r.status === 200 && r.data.ok) return r.data;
    if (r.status === 401) { zeigeAnmeldung(); return null; }
    m.textContent = fehlerText(r, 'Speichern fehlgeschlagen');
    if (r.status === 409 && r.data.code === 'konflikt') await neuLaden();
    return null;
  }
  /* Mengen aus Eingaben mit data-lm (und optional data-seite) einsammeln; ungültige markieren */
  function sammle(inputs, negativ) {
    const m = {}; let ok = true;
    inputs.forEach((x) => {
      const n = ganz(x.value);
      const falsch = Number.isNaN(n) || (!negativ && n < 0);
      if (falsch) x.setAttribute('aria-invalid', 'true'); else x.removeAttribute('aria-invalid');
      if (falsch) ok = false; else if (n) m[x.dataset.lm] = (m[x.dataset.lm] || 0) + n;
    });
    return ok ? m : null;
  }
  const partnerOptionen = (auswahl, nurAktiv) => [...S.d.partner].filter((p) => !nurAktiv || p.aktiv || p.id === auswahl).sort((a, b) => (a.aktiv === b.aktiv ? 0 : a.aktiv ? -1 : 1) || nachName(a, b))
    .map((p) => `<option value="${esc(p.id)}"${p.id === auswahl ? ' selected' : ''}>${esc(p.name)}${p.aktiv ? '' : ' (inaktiv)'}</option>`).join('');
  const aktiveLm = () => S.d.lademittel.filter((l) => l.aktiv !== false).map((l) => l.id);
  const optionen = (liste, wahl) => Object.entries(liste).map(([k, v]) => `<option value="${esc(k)}"${k === wahl ? ' selected' : ''}>${esc(v)}</option>`).join('');
  function nachSpeichern(text, partner) {
    toast(text);
    neuLaden().then(() => { if (partner && S.tab === 'konten') zeigeKonto(partner, false); });
  }

  /* ---------- Bewegung buchen ---------- */
  function oeffneBewegung(partner) {
    const sel = $('#bw-partner');
    const wahl = partner && S.pmap.get(partner)?.aktiv ? partner : (S.tab === 'konten' && S.pmap.get(S.kontoId)?.aktiv ? S.kontoId : '');
    sel.innerHTML = (wahl ? '' : '<option value="">Partner wählen …</option>') + partnerOptionen(wahl, true);
    $('#bw-datum').value = S.d.heute; $('#bw-typ').innerHTML = optionen(S.d.typen, 'bewegung');
    $('#bw-beleg').value = ''; $('#bw-text').value = ''; $('#bw-alle').checked = false;
    bwZeilen();
    oeffne($('#dlg-bewegung'));
    (wahl ? $('#bw-datum') : sel).focus();
  }
  function bwZeilen() {
    const p = S.pmap.get($('#bw-partner').value);
    const alt = {}; $$('#bw-mengen input').forEach((x) => { if (x.value) alt[x.dataset.seite + x.dataset.lm] = x.value; });
    let ids = $('#bw-alle').checked || !p ? aktiveLm() : kontoLms(p, []).filter((id) => aktiveLm().includes(id) || obj(S.kmap.get(p.id)?.saldo)[id]);
    if (!ids.length) ids = aktiveLm();
    $('#bw-mengen').innerHTML = ids.map((id) => `<tr><td class="lg-voll lg-name">${esc(lm(id).name)}</td>
      <td class="lg-zahl" data-label="Abgang"><input class="lg-eingabe" data-lm="${esc(id)}" data-seite="a" inputmode="numeric" maxlength="9" value="${esc(alt['a' + id] || '')}" aria-label="Abgang ${esc(lm(id).name)}"></td>
      <td class="lg-zahl" data-label="Zugang"><input class="lg-eingabe" data-lm="${esc(id)}" data-seite="z" inputmode="numeric" maxlength="9" value="${esc(alt['z' + id] || '')}" aria-label="Zugang ${esc(lm(id).name)}"></td>
      <td class="lg-zahl" data-label="Saldo danach" data-danach="${esc(id)}"></td></tr>`).join('');
    bwDanach();
  }
  function bwDanach() {
    const s = obj(S.kmap.get($('#bw-partner').value)?.saldo);
    $$('#bw-mengen [data-danach]').forEach((td) => {
      const id = td.dataset.danach;
      const a = ganz($(`#bw-mengen [data-seite="a"][data-lm="${CSS.escape(id)}"]`).value), z = ganz($(`#bw-mengen [data-seite="z"][data-lm="${CSS.escape(id)}"]`).value);
      td.innerHTML = Number.isNaN(a) || Number.isNaN(z) ? '<span class="lg-null">?</span>' : vzHtml((s[id] || 0) + a - z);
    });
  }
  $('#bw-partner').addEventListener('change', bwZeilen);
  $('#bw-alle').addEventListener('change', bwZeilen);
  $('#bw-mengen').addEventListener('input', bwDanach);
  $('#lg-neu-bewegung').addEventListener('click', () => oeffneBewegung(''));
  $('#bw-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const m = $('#bw-meldung');
    const abgang = sammle($$('#bw-mengen [data-seite="a"]'), false), zugang = sammle($$('#bw-mengen [data-seite="z"]'), false);
    if (!$('#bw-partner').value) { m.textContent = 'Bitte einen Partner wählen.'; return; }
    if (!abgang || !zugang) { m.textContent = 'Bitte nur ganze Stückzahlen ohne Vorzeichen eintragen.'; return; }
    if (leerMap(abgang) && leerMap(zugang)) { m.textContent = 'Bitte mindestens eine Menge bei Abgang oder Zugang eintragen.'; return; }
    const partner = $('#bw-partner').value;
    const d = await senden(ev.target, 'leergut_bewegung_save', { partner, datum: $('#bw-datum').value, typ: $('#bw-typ').value, beleg: $('#bw-beleg').value, text: $('#bw-text').value, abgang, zugang });
    if (!d) return;
    $('#dlg-bewegung').close();
    nachSpeichern('Bewegung gebucht – ' + partnerName(partner), partner);
  });

  /* ---------- Stornieren ---------- */
  function oeffneStorno(id) {
    const b = (S.konto[S.kontoId]?.bewegungen || []).find((x) => x.id === id);
    if (!b) return;
    S.edit.storno = b;
    $('#st-text').innerHTML = `${esc(partnerName(b.partner))}, ${esc(datum(b.datum))} (${esc(S.d.typen[b.typ] || b.typ)})${b.beleg ? ', Beleg ' + esc(b.beleg) : ''}: ${mengen(delta(b))}`;
    $('#st-grund').value = '';
    oeffne($('#dlg-storno')); $('#st-grund').focus();
  }
  $('#st-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    if (!$('#st-grund').value.trim()) { $('#st-meldung').textContent = 'Bitte einen Grund angeben.'; return; }
    const b = S.edit.storno;
    const d = await senden(ev.target, 'leergut_bewegung_storno', { id: b.id, grund: $('#st-grund').value });
    if (!d) return;
    $('#dlg-storno').close();
    nachSpeichern('Bewegung storniert', b.partner);
  });

  /* ---------- Auszug (Abstimmung) erfassen / bearbeiten ---------- */
  async function oeffneAuszug({ id = '', partner = '' }) {
    const a = id ? S.d.abstimmungen.find((x) => x.id === id) : null;
    if (id && !a) return;
    const nurLesen = !darf('bearbeiten');
    S.edit.auszug = a;
    const wahl = a ? a.partner : (partner || (S.tab === 'konten' ? S.kontoId : ''));
    $('#az-titel').textContent = a ? `Auszug ${partnerName(a.partner)} zum ${datum(a.stichtag)}` : 'Auszug erfassen';
    $('#az-partner').innerHTML = (wahl ? '' : '<option value="">Partner wählen …</option>') + partnerOptionen(wahl, !a);
    $('#az-partner').disabled = !!a;
    $('#az-stichtag').value = a ? a.stichtag : S.d.heute;
    $('#az-eingang').value = a ? a.eingang : S.d.heute;
    $('#az-frist').value = a ? a.fristBis : '';
    $('#az-status').innerHTML = optionen(S.d.abstStatus, a ? a.status : 'offen');
    $('#az-quelle').value = a ? a.quelle : ''; $('#az-notiz').value = a ? a.notiz : '';
    $('#az-verlauf').innerHTML = a ? [...(a.verlauf || [])].reverse().map((v) => `<li>${esc(zeitpunkt(v.t))} · ${esc(v.von)}: ${esc(v.was)}</li>`).join('')
      + (a.herkunft === 'import' ? '<li>aus der bisherigen Excel-Liste übernommen</li>' : '') : '';
    $$('#az-form input, #az-form select, #az-form textarea').forEach((x) => { if (x.id !== 'az-partner') x.disabled = nurLesen; });
    $('#az-form [type="submit"]').hidden = nurLesen; $('#az-umkehren').hidden = nurLesen;
    await azZeilen(a ? obj(a.saldo) : null);
    oeffne($('#dlg-auszug'));
  }
  async function azZeilen(werte) {
    const pid = $('#az-partner').value, p = S.pmap.get(pid);
    const alt = {}; $$('#az-mengen input').forEach((x) => { if (x.value) alt[x.dataset.lm] = x.value; });
    const quelle = werte || alt;
    const ids = new Set(p ? kontoLms(p, []) : ['e2', 'h1']); Object.keys(quelle).forEach((k) => ids.add(k));
    $('#az-mengen').innerHTML = sortiertLm(ids).map((id) => `<tr><td class="lg-voll lg-name">${esc(lm(id).name)}</td>
      <td class="lg-zahl" data-label="Laut Partner"><input class="lg-eingabe" data-lm="${esc(id)}" inputmode="text" maxlength="10" value="${esc(werte ? (werte[id] ? String(werte[id]) : '') : (alt[id] || ''))}" aria-label="Saldo laut Partner ${esc(lm(id).name)}" placeholder="0"></td>
      <td class="lg-zahl" data-label="Unser Saldo" data-eigen="${esc(id)}"></td><td class="lg-zahl" data-label="Differenz" data-diff="${esc(id)}"></td></tr>`).join('');
    if (p) await kontoLaden(pid);
    azRechnen();
  }
  function azRechnen() {
    const pid = $('#az-partner').value, k = S.konto[pid];
    const eigen = k ? saldoBis(k.bewegungen, $('#az-stichtag').value) : {};
    $$('#az-mengen [data-eigen]').forEach((td) => {
      const id = td.dataset.eigen, n = ganz($(`#az-mengen input[data-lm="${CSS.escape(id)}"]`).value), e = eigen[id] || 0;
      td.innerHTML = k ? vzHtml(e) : '<span class="lg-null">—</span>';
      const diff = $(`#az-mengen [data-diff="${CSS.escape(id)}"]`);
      diff.innerHTML = Number.isNaN(n) ? '<span class="lg-null">?</span>' : !k ? '' : n - e ? vzHtml(n - e) : '<span class="lg-chip gruen">keine</span>';
    });
    const p = S.pmap.get(pid), ein = $('#az-eingang').value;
    $('#az-frist-hilfe').textContent = !$('#az-frist').value && p && p.fristTage && ein
      ? `leer = automatisch ${datum(new Date(Date.parse(ein + 'T12:00:00Z') + p.fristTage * 86400000).toISOString().slice(0, 10))} (Eingang + ${p.fristTage} Tage)` : '';
  }
  $('#az-partner').addEventListener('change', () => azZeilen(null));
  ['#az-stichtag', '#az-eingang', '#az-frist'].forEach((s) => $(s).addEventListener('input', azRechnen));
  $('#az-mengen').addEventListener('input', azRechnen);
  $('#az-umkehren').addEventListener('click', () => {
    $$('#az-mengen input').forEach((x) => { const n = ganz(x.value); if (!Number.isNaN(n) && n) x.value = String(-n); });
    azRechnen();
  });
  $('#lg-neu-auszug').addEventListener('click', () => oeffneAuszug({}));
  $('#az-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const a = S.edit.auszug, partner = a ? a.partner : $('#az-partner').value;
    if (!partner) { $('#az-meldung').textContent = 'Bitte einen Partner wählen.'; return; }
    const saldo = sammle($$('#az-mengen input'), true);
    if (!saldo) { $('#az-meldung').textContent = 'Bitte nur ganze Stückzahlen eintragen (mit − für „wir schulden dem Partner“).'; return; }
    const body = { partner, stichtag: $('#az-stichtag').value, eingang: $('#az-eingang').value, fristBis: $('#az-frist').value, saldo, status: $('#az-status').value, quelle: $('#az-quelle').value, notiz: $('#az-notiz').value };
    if (a) { body.id = a.id; body.rev = a.rev; }
    const d = await senden(ev.target, 'leergut_abstimmung_save', body);
    if (!d) return;
    $('#dlg-auszug').close();
    const x = d.abstimmung;
    nachSpeichern(`Auszug gespeichert – ${S.d.abstStatus[x.status] || x.status}${leerMap(x.differenz) ? ', keine Differenz' : ''}`, partner);
  });

  /* ---------- Dachser-Abschreibung ---------- */
  function oeffneAbschreibung(id) {
    const x = id ? S.d.abschreibungen.find((y) => y.id === id) : null;
    if (id && !x) return;
    S.edit.abschr = x;
    $('#ds-titel').textContent = x ? `Abschreibung ${x.empfaenger}` : 'Abschreibung erfassen';
    $('#ds-empfaenger').value = x ? x.empfaenger : ''; $('#ds-nr').value = x ? x.empfaengerNr : ''; $('#ds-ort').value = x ? x.ort : '';
    $('#ds-auftrag').value = x ? x.auftrag : ''; $('#ds-zugestellt').value = x ? x.zugestellt : ''; $('#ds-sendung').value = x ? x.sendung : '';
    $('#ds-grund').value = x ? x.grund : 'Abschreibung lt. Empfänger';
    $('#ds-status').innerHTML = optionen(S.d.abschrStatus, x ? x.status : 'offen');
    $('#ds-rechnung').value = x ? x.rechnung : ''; $('#ds-notiz').value = x ? x.notiz : '';
    const werte = x ? obj(x.menge) : {};
    const ids = new Set(aktiveLm().filter((l) => ['e2', 'h1', 'eu'].includes(l) || lm(l).wert !== null)); Object.keys(werte).forEach((k) => ids.add(k));
    $('#ds-mengen').innerHTML = sortiertLm(ids).map((l) => `<label>${esc(lm(l).name)}<input class="lg-eingabe" data-lm="${esc(l)}" inputmode="numeric" maxlength="9" value="${werte[l] ? esc(String(werte[l])) : ''}"></label>`).join('');
    $('#ds-verlauf').innerHTML = x ? [...(x.verlauf || [])].reverse().map((v) => `<li>${esc(zeitpunkt(v.t))} · ${esc(v.von)}: ${esc(v.was)}</li>`).join('') : '';
    dsWert();
    oeffne($('#dlg-abschr'));
    $('#ds-empfaenger').focus();
  }
  function dsWert() {
    const m = {}; $$('#ds-mengen input').forEach((i) => { const n = ganz(i.value); if (n > 0) m[i.dataset.lm] = n; });
    const w = abWert(m);
    $('#ds-wert').textContent = w.e ? `Wert bei Berechnung an den Kunden: ${euro(w.e)}${w.voll ? '' : ' (ohne Lademittel ohne Wert)'}.` : '';
  }
  $('#ds-mengen').addEventListener('input', dsWert);
  $('#ds-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const menge = sammle($$('#ds-mengen input'), false);
    if (!menge) { $('#ds-meldung').textContent = 'Bitte nur ganze Stückzahlen ohne Vorzeichen eintragen.'; return; }
    const x = S.edit.abschr;
    const body = { empfaenger: $('#ds-empfaenger').value, empfaengerNr: $('#ds-nr').value, ort: $('#ds-ort').value, auftrag: $('#ds-auftrag').value, zugestellt: $('#ds-zugestellt').value,
      sendung: $('#ds-sendung').value, grund: $('#ds-grund').value, menge, status: $('#ds-status').value, rechnung: $('#ds-rechnung').value, notiz: $('#ds-notiz').value };
    if (x) { body.id = x.id; body.rev = x.rev; }
    const d = await senden(ev.target, 'leergut_abschreibung_save', body);
    if (!d) return;
    $('#dlg-abschr').close();
    nachSpeichern('Abschreibung gespeichert – ' + (S.d.abschrStatus[d.abschreibung.status] || ''));
  });

  /* ---------- Inventur ---------- */
  const INV_VORLAGE = ['Lager (WinAB-Inventur)', 'Unbenutzte Kisten', 'Bei Abholern'];
  let invLms = [];
  function oeffneInventur(id) {
    const x = id ? S.d.inventur.find((y) => y.id === id) : null;
    if (id && !x) return;
    S.edit.inventur = x;
    $('#iv-titel').textContent = x ? `Inventur zum ${datum(x.stichtag)}` : 'Inventur erfassen';
    $('#iv-stichtag').value = x ? x.stichtag : S.d.heute;
    $('#iv-notiz').value = x ? x.notiz : '';
    const ids = new Set(aktiveLm().filter((l) => ['e2', 'h1'].includes(l) || lm(l).wert !== null));
    (x ? x.positionen : []).forEach((p) => Object.keys(obj(p.werte)).forEach((k) => ids.add(k)));
    invLms = sortiertLm(ids);
    $('#iv-kopf').innerHTML = `<tr><th>Position</th>${invLms.map((l) => `<th class="lg-zahl">${esc(kurz(l))}</th>`).join('')}<th></th></tr>`;
    $('#iv-zeilen').innerHTML = (x ? x.positionen : INV_VORLAGE.map((name) => ({ name, werte: {} }))).map(ivZeile).join('');
    oeffne($('#dlg-inventur'));
  }
  const ivZeile = (p) => `<tr><td class="lg-voll"><input class="lg-eingabe" data-f="name" maxlength="60" value="${esc(p.name)}" aria-label="Position"></td>
    ${invLms.map((l) => `<td class="lg-zahl" data-label="${esc(kurz(l))}"><input class="lg-eingabe" data-lm="${esc(l)}" inputmode="numeric" maxlength="9" value="${obj(p.werte)[l] ? esc(String(obj(p.werte)[l])) : ''}" aria-label="${esc(lm(l).name)}"></td>`).join('')}
    <td><button class="btn sm ghost" type="button" data-weg aria-label="Position entfernen">×</button></td></tr>`;
  $('#iv-plus').addEventListener('click', () => { if ($$('#iv-zeilen tr').length < 12) $('#iv-zeilen').insertAdjacentHTML('beforeend', ivZeile({ name: '', werte: {} })); });
  $('#iv-zeilen').addEventListener('click', (ev) => { const b = ev.target.closest('[data-weg]'); if (b && $$('#iv-zeilen tr').length > 1) b.closest('tr').remove(); });
  $('#iv-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    let ok = true;
    const positionen = $$('#iv-zeilen tr').map((tr) => { const werte = sammle($$('[data-lm]', tr), false); if (!werte) ok = false; return { name: $('[data-f="name"]', tr).value.trim(), werte: werte || {} }; })
      .filter((p) => p.name || !leerMap(p.werte));
    if (!ok) { $('#iv-meldung').textContent = 'Bitte nur ganze Stückzahlen ohne Vorzeichen eintragen.'; return; }
    const x = S.edit.inventur;
    const body = { stichtag: $('#iv-stichtag').value, positionen, notiz: $('#iv-notiz').value };
    if (x) { body.id = x.id; body.rev = x.rev; }
    const d = await senden(ev.target, 'leergut_inventur_save', body);
    if (!d) return;
    $('#dlg-inventur').close();
    nachSpeichern('Inventur gespeichert');
  });

  /* ---------- Partner ---------- */
  function oeffnePartner(id) {
    const p = id ? S.pmap.get(id) : null;
    if (id && !p) return;
    S.edit.partner = p;
    $('#pa-titel').textContent = p ? `Partner ${p.name}` : 'Partner anlegen';
    $('#pa-name').value = p ? p.name : ''; $('#pa-art').innerHTML = optionen(S.d.arten, p ? p.art : 'lieferant');
    $('#pa-firma').innerHTML = optionen(S.d.mandanten, p ? p.mandant : 'standard');
    $('#pa-konto').value = p ? p.kontoNr : ''; $('#pa-kdnr').value = p ? (p.kundenNr || '') : ''; $('#pa-frist').value = p ? (p.fristTage || '') : '14';
    $('#pa-email').value = p ? p.email : ''; $('#pa-ansprech').value = p ? p.ansprechpartner : ''; $('#pa-lieferanten').value = p ? p.lieferanten : '';
    $('#pa-notiz').value = p ? p.notiz : ''; $('#pa-aktiv').checked = p ? !!p.aktiv : true;
    const gewaehlt = new Set(p ? p.lademittel : ['e2', 'h1']);
    $('#pa-lm').innerHTML = S.d.lademittel.filter((l) => l.aktiv !== false || gewaehlt.has(l.id)).map((l) => `<label class="lg-check"><input type="checkbox" value="${esc(l.id)}"${gewaehlt.has(l.id) ? ' checked' : ''}> ${esc(l.name)}</label>`).join('');
    oeffne($('#dlg-partner'));
    $('#pa-name').focus();
  }
  $('#pa-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const p = S.edit.partner;
    const body = { name: $('#pa-name').value, art: $('#pa-art').value, mandant: $('#pa-firma').value, kontoNr: $('#pa-konto').value, kundenNr: $('#pa-kdnr').value.trim(), fristTage: $('#pa-frist').value.trim(),
      email: $('#pa-email').value, ansprechpartner: $('#pa-ansprech').value, lieferanten: $('#pa-lieferanten').value, notiz: $('#pa-notiz').value,
      lademittel: $$('#pa-lm input:checked').map((x) => x.value), aktiv: $('#pa-aktiv').checked };
    if (p) { body.id = p.id; body.rev = p.rev; }
    const d = await senden(ev.target, 'leergut_partner_save', body);
    if (!d) return;
    $('#dlg-partner').close();
    nachSpeichern('Partner gespeichert – ' + d.partner.name, d.partner.id);
  });

  /* ---------- Start ---------- */
  async function laden() {
    const st = await api('status');
    if (st.status === 401 && !st.json) { zeigeAnmeldung(); return; }   // zentrale Sitzung abgelaufen (Webserver)
    if (st.status === 403 && st.data.code === 'reauth_required' && typeof st.data.anmelden === 'string' && st.data.anmelden.startsWith('/oidc/')) {
      location.assign(st.data.anmelden + encodeURIComponent(location.href)); return;
    }
    if (st.status === 403 && st.data.error) { fehler(st.data.error); return; }
    if (st.status !== 200 || !st.data.loggedIn) { zeigeAnmeldung(); return; }
    S.csrf = st.data.csrf || '';
    if (window.STAFL_THEME) { window.STAFL_THEME.konto(st.data.user, S.csrf, API); themaKnopf(); }
    const name = st.data.user ? (st.data.user.name || st.data.user.username || '') : '';
    $('#lg-user').hidden = false; $('#lg-user-name').textContent = name; $('#lg-initialen').textContent = initialen(name);
    const r = await api('leergut_start');
    if (r.status === 404) { fehler('Das Leergut ist für Sie noch nicht freigegeben.'); return; }
    if (r.status === 503) { fehler(r.data.error || 'Das Leergut wird gerade gewartet.'); return; }
    if (r.status === 403) { fehler(r.data.error || 'Dafür fehlt Ihnen die Berechtigung.'); return; }
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { fehler(fehlerText(r, 'Das Leergut konnte nicht geladen werden')); return; }
    setzeDaten(r.data);
    $('#lg-login').hidden = true; $('#lg-app').hidden = false;
    const [tab, teil] = location.hash.slice(1).split('/');
    if (tab === 'konten' && teil) S.kontoId = teil;
    renderAlles();
    zeigeTab(tab || 'uebersicht', teil || '');
  }
  themaKnopf();
  document.addEventListener('DOMContentLoaded', () => { laden().catch(() => fehler('Keine Verbindung zum Server.')); });
})();
