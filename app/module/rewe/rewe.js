/* STAFL-Plattform · REWE – Oberfläche der Vordisposition Dry Aged: Anmeldung über den Status, Stammdaten aus rewe_start,
   Reiter über location.hash („#woche/2026-45“, „#markt/<id>“, „#abschluss/2026-45“), Hell/Dunkel am Konto (theme.js).
   Ansichten: Meine Woche (eigene Liste der Lieferwoche, gruppiert nach Zentrallager und Direktbelieferung; Antwort je Markt
   mit einem Klick, Mengen, fällige Daueraufträge bestätigen, ruhende Märkte als eigene Liste; Verlauf mit Vorbestellungen der
   nächsten Wochen; Klick auf Name oder Adresse öffnet die Marktkarte mit Hinweis, Notizen, Verlauf und Wiedervorlagen),
   Daueraufträge (alle sichtbaren Daueraufträge, bearbeiten, neu anlegen), Märkte mit Marktakte
   (Wochenverlauf je Jahr, Notizen und Wiedervorlagen, Zuständigkeit und Lieferweg mit Historie, Ansprechpartner),
   Zuweisung (Märkte und Lieferweg ab KW, Team „alle Listen“ und „Wochenabschluss“), Wochenabschluss (Summen, Hinweise,
   Excel für WinAB als Einzelaufträge, „in WinAB erfasst“), Einstellungen (Lieferwege, Artikel, Datenpaket der Excel-Listen).
   Rechte prüft der Server bei jeder Aktion (GR-103); ausgeblendete Knöpfe sind nur Anzeige. Kein Inline-Skript (CSP). */
'use strict';
(() => {
  const API = '../../api/';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const TABS = ['woche', 'dauer', 'maerkte', 'zuweisung', 'abschluss', 'einstellungen'];
  const S = {
    csrf: '', d: null, tab: 'woche', kw: '', wer: '', filter: 'offen', suche: '', woche: null, offenSeg: new Set(), busy: new Set(), sichtbar: new Set(), bestelltZu: true, zeigeNach: '',
    dSuche: '', dRh: '', dLw: '', dStatus: '', dEdit: null, dOffen: '', zurueckFrage: '', zurueckTimer: 0,
    maerkte: null, mSuche: '', mLw: '', mKauf: '', akteId: '', akte: null, aKw: '', abschluss: null,
    zAuswahl: new Set(), zSuche: '', zWer: '', zLw: '', zKauf: '', paket: null, edit: null, notizMarkt: '', toast: 0,
  };

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
  /* Hinweis unten; mit aktion ({text, fn}) zusätzlich ein Knopf (z. B. „Rückgängig“), dann länger sichtbar */
  function toast(text, fehlerhaft = false, aktion = null) {
    const t = $('#rw-toast');
    t.textContent = text;
    if (aktion) {
      const b = document.createElement('button');
      b.type = 'button'; b.className = 'rw-toast-knopf'; b.dataset.rueck = ''; b.textContent = aktion.text;
      b.addEventListener('click', () => { clearTimeout(S.toast); t.className = 'rw-toast'; aktion.fn(); }, { once: true });
      t.append(b);
    }
    t.className = 'rw-toast zeigen' + (fehlerhaft ? ' fehler' : '') + (aktion ? ' mit-aktion' : '');
    clearTimeout(S.toast); S.toast = setTimeout(() => { t.className = 'rw-toast'; }, aktion ? 9000 : fehlerhaft ? 4500 : 2400);
  }
  function fehler(text) { $('#rw-login').hidden = true; $('#rw-app').hidden = true; $('#rw-err').hidden = false; $('#rw-err').textContent = text; }
  function zeigeAnmeldung() { $$('dialog[open]').forEach((d) => d.close()); $('#rw-login').hidden = false; $('#rw-app').hidden = true; $('#rw-user').hidden = true; }
  const initialen = (name) => { const t = String(name || '').trim().split(/[\s.\-_]+/).filter(Boolean); return (t.length > 1 ? t[0][0] + t[1][0] : (t[0] || '?').slice(0, 2)).toLocaleUpperCase('de-DE'); };
  const obj = (m) => (m && typeof m === 'object' && !Array.isArray(m) ? m : {});   // PHP liefert leere Zuordnungen als []
  const zahl = (n) => window.STAFL_FORMAT.zahl(n, 0, 2);   // echtes Minus wie überall (format.js)
  const maerkte = (n) => `${zahl(n)} ${Number(n) === 1 ? 'Markt' : 'Märkte'}`;   // Einzahl/Mehrzahl („1 Markt“, „3 Märkte“)
  const datum = (iso) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}` : '');
  const zeitpunkt = (t) => { const d = new Date(t); return isNaN(d) ? '' : window.STAFL_FORMAT.datumZeit(d); };   // 02.11.2026, 14:05 wie überall
  const darf = (r) => !!(S.d && S.d.rechte && S.d.rechte[r]);

  /* ---------- Kalenderwochen (ISO, „JJJJ-WW“) ---------- */
  function montag(kw) {
    const j = +kw.slice(0, 4), w = +kw.slice(5, 7);
    const d = new Date(Date.UTC(j, 0, 4)); const t = d.getUTCDay() || 7;
    d.setUTCDate(d.getUTCDate() - t + 1 + (w - 1) * 7);
    return d;
  }
  function isoKw(d) {
    const x = new Date(Date.UTC(d.getUTCFullYear(), d.getUTCMonth(), d.getUTCDate()));
    const t = x.getUTCDay() || 7; x.setUTCDate(x.getUTCDate() + 4 - t);
    const j = x.getUTCFullYear(); const w = Math.ceil(((x - Date.UTC(j, 0, 1)) / 86400000 + 1) / 7);
    return `${j}-${String(w).padStart(2, '0')}`;
  }
  const kwPlus = (kw, n) => { const d = montag(kw); d.setUTCDate(d.getUTCDate() + 7 * n); return isoKw(d); };
  const kwText = (kw) => (kw ? `KW ${+kw.slice(5)}/${kw.slice(0, 4)}` : '');
  const kwKurz = (kw) => (kw ? `KW ${+kw.slice(5)}` : '');
  const kwOk = (v) => /^\d{4}-\d{2}$/.test(v) && +v.slice(5) >= 1 && +v.slice(5) <= 53;
  function zeitraum(kw) { const a = montag(kw), b = new Date(a); b.setUTCDate(b.getUTCDate() + 6); const f = (d) => d.toISOString().slice(0, 10); return `${datum(f(a)).slice(0, 6)}–${datum(f(b))}`; }

  /* ---------- Bezeichnungen ---------- */
  const artikel = () => S.d.artikel.filter((a) => a.aktiv);
  const artName = (id) => (S.d.artikel.find((a) => a.id === id) || { name: id }).name;
  function mengenText(m) {
    const e = S.d.artikel.filter((a) => obj(m)[a.id]).map((a) => `${obj(m)[a.id]} ${a.name}`);
    return e.join(' + ');
  }
  const summe = (m) => Object.values(obj(m)).reduce((a, n) => a + n, 0);
  const personName = (id) => (S.d.personen.find((p) => p.id === id) || { name: '' }).name;
  const kaufChip = (k) => `<span class="rw-chip ${k === 'regelmaessig' ? 'gruen' : k === 'gelegentlich' || k === 'interessiert' ? 'blau' : ''}">${esc(S.d.kauf[k] || k)}</span>`;
  const lwOptionen = (alle, nurAktiv = true) => (alle ? `<option value="">${esc(alle)}</option>` : '') + S.d.lieferwege.filter((l) => !nurAktiv || l.aktiv).map((l) => `<option value="${esc(l.id)}">${esc(l.name)}</option>`).join('');
  const kaufOptionen = (alle) => (alle ? `<option value="">${esc(alle)}</option>` : '') + Object.entries(S.d.kauf).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');
  const personOptionen = (vorne = '') => vorne + S.d.personen.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
  const passt = (m, q) => !q || [m.ort, m.strasse, m.name, m.kdNr, m.reweNr, m.plz].some((x) => String(x || '').toLocaleLowerCase('de-DE').includes(q));

  /* Rückweg zum Dashboard auf der echten Adresse */
  if (/(^|\.)dashboard-stafl\.de$/.test(location.hostname)) $('#rw-zurueck').href = 'https://dashboard-stafl.de/';

  /* ---------- Hell/Dunkel ---------- */
  const dunkel = () => document.documentElement.getAttribute('data-theme') === 'dark'
    || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  function themaKnopf() {
    const d = dunkel(), b = $('#rw-theme');
    b.innerHTML = `<svg class="i" aria-hidden="true"><use href="#i-${d ? 'sun' : 'moon'}"/></svg>`;
    b.setAttribute('aria-label', d ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }
  $('#rw-theme').addEventListener('click', () => { document.documentElement.setAttribute('data-theme', dunkel() ? 'light' : 'dark'); themaKnopf(); });
  document.addEventListener('stafl-theme', themaKnopf);

  /* ---------- Reiter und Adresse ---------- */
  const erlaubt = (tab) => tab === 'woche' || tab === 'dauer' || tab === 'maerkte' || (tab === 'abschluss' && darf('exportieren')) || ((tab === 'zuweisung' || tab === 'einstellungen') && darf('verwalten'));
  function zeigeTab(tab, teil = '') {
    if (tab === 'markt') { S.akteId = teil; tab = 'maerkte'; } else if (tab === 'maerkte') S.akteId = '';
    if (!TABS.includes(tab) || !erlaubt(tab)) tab = 'woche';
    S.tab = tab;
    $$('#rw-tabs [role="tab"]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
    $$('.rw-tab').forEach((x) => { x.hidden = x.dataset.tab !== tab; });
    if (tab === 'woche') { if (teil && kwOk(teil)) S.kw = teil; history.replaceState(null, '', '#woche/' + S.kw); ladeWoche(); }
    else if (tab === 'maerkte') {
      history.replaceState(null, '', S.akteId ? '#markt/' + S.akteId : '#maerkte');
      $('#rw-m-liste').hidden = !!S.akteId; $('#rw-akte').hidden = !S.akteId;
      if (S.akteId) ladeAkte(S.akteId); else ladeMaerkte();
    } else if (tab === 'abschluss') { if (teil && kwOk(teil)) S.aKw = teil; history.replaceState(null, '', '#abschluss/' + S.aKw); ladeAbschluss(); }
    else if (tab === 'zuweisung') { history.replaceState(null, '', '#zuweisung'); ladeMaerkte(); }
    else if (tab === 'dauer') { if (teil) S.dOffen = teil; history.replaceState(null, '', '#dauer'); ladeMaerkte(); }
    else { history.replaceState(null, '', '#' + tab); renderEinstellungen(); }
  }
  $('#rw-tabs').addEventListener('click', (ev) => { const b = ev.target.closest('[role="tab"]'); if (b) zeigeTab(b.dataset.tab); });
  window.addEventListener('hashchange', () => {
    if (!S.d) return;
    const [tab, teil] = location.hash.slice(1).split('/');
    const jetzt = S.tab === 'maerkte' && S.akteId ? 'markt' : S.tab;
    if (tab !== jetzt || (teil && teil !== (tab === 'markt' ? S.akteId : tab === 'woche' ? S.kw : tab === 'abschluss' ? S.aKw : ''))) zeigeTab(tab || 'woche', teil || '');
  });
  document.addEventListener('click', (ev) => {
    const g = ev.target.closest('[data-gehe]');
    if (g) { ev.preventDefault(); const [t, x] = g.dataset.gehe.split('/'); zeigeTab(t, x || ''); window.scrollTo(0, 0); }
  });

  /* ================= Meine Woche ================= */
  async function ladeWoche() {
    const q = `&kw=${encodeURIComponent(S.kw)}` + (S.wer ? `&wer=${encodeURIComponent(S.wer)}` : '');
    const r = await api('rewe_woche', null, q);
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Die Woche konnte nicht geladen werden'), true); return; }
    S.woche = r.data.woche;
    renderWoche();
  }
  const nichtFaellig = (m) => !m.antwort && !m.dauerFaellig && m.dauer && m.dauer.rhythmus > 0 && m.dauerNaechste && !S.offenSeg.has(m.id);
  const erledigt = (m) => !!m.antwort || nichtFaellig(m);
  // Gerade beantwortete Märkte bleiben im Filter „Offen“ stehen (Mengen nachtragen), bis der Filter neu gewählt oder die Woche gewechselt wird
  const zeigen = (m) => S.filter === 'alle' || (S.filter === 'offen' ? !erledigt(m) || S.sichtbar.has(m.id) : erledigt(m));
  const neuAnsehen = () => { S.offenSeg.clear(); S.sichtbar.clear(); };
  function renderWoche() {
    const w = S.woche; if (!w) return;
    const eigen = !w.wer;
    $('#rw-w-titel').textContent = `${eigen ? 'Meine Woche' : w.werName} · ${kwText(w.kw)}`;   // KW 46/2026 wie überall
    const alleM = w.gruppen.flatMap((g) => g.maerkte);
    const ziel = w.kw === S.d.abfrage ? ' · aktuelle Abfragewoche' : '';
    $('#rw-w-sub').textContent = `Lieferwoche ${zeitraum(w.kw)}${ziel} · ${maerkte(alleM.length)}`;
    $('#rw-w-heute').hidden = w.kw === S.d.abfrage;
    // Kennzahlen aus den Zeilen (nicht fällige Daueraufträge gelten als erledigt)
    const fertig = alleM.filter(erledigt).length, best = alleM.filter((m) => m.antwort && m.antwort.status === 'bestellt');
    const mengen = {}; best.forEach((m) => Object.entries(obj(m.antwort.mengen)).forEach(([k, n]) => { mengen[k] = (mengen[k] || 0) + n; }));
    const dauerOffen = alleM.filter((m) => !m.antwort && m.dauerFaellig).length;
    const wv = alleM.filter((m) => m.wiedervorlagen.length);
    const pct = alleM.length ? Math.round(fertig / alleM.length * 100) : 0;
    $('#rw-w-kpis').innerHTML = `
      <div class="rw-kpi"><span>Erledigt</span><b>${fertig} <small>von ${alleM.length}</small></b><div class="rw-fortschritt" aria-hidden="true"><i style="width:${pct}%"></i></div></div>
      <div class="rw-kpi"><span>Bestellt</span><b>${best.length} <small>${best.length === 1 ? 'Markt' : 'Märkte'}</small></b><small>${esc(mengenText(mengen) || 'noch nichts')}</small></div>
      <div class="rw-kpi"><span>Daueraufträge zu bestätigen</span><b>${dauerOffen}</b><small>fällig nach Rhythmus</small></div>
      <div class="rw-kpi${wv.length ? ' warn' : ''}"><span>Wiedervorlagen fällig</span><b>${wv.length}</b><small>${esc(wv.slice(0, 3).map((m) => m.ort).join(' · ') || '—')}</small></div>`;
    bestelltHtml(w, best, mengen);
    $$('#rw-w-filter button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.f === S.filter)));
    const q = S.suche.trim().toLocaleLowerCase('de-DE');
    const html = w.gruppen.map((g) => {
      const zeilen = g.maerkte.filter((m) => passt(m, q) && zeigen(m));
      const offen = g.maerkte.filter((m) => !erledigt(m)).length;
      const faellig = g.maerkte.filter((m) => !m.antwort && m.dauerFaellig && m.darfAntworten);
      return `<section class="rw-gruppe rw-glas" data-gruppe="${esc(g.id)}">
        <div class="rw-gkopf">
          <span class="rw-gsymbol${g.art === 'direkt' ? ' direkt' : ''}"><svg class="i" aria-hidden="true"><use href="#i-${g.art === 'direkt' ? 'lkw' : 'lager'}"/></svg></span>
          <div><h2>${esc(g.name)}</h2><p class="rw-sub">${esc(g.art === 'lager' ? 'REWE-Zentrallager' : g.art === 'direkt' ? 'Lieferung direkt an den Markt' : 'Lieferweg fehlt')} · ${maerkte(g.maerkte.length)} · ${offen} offen${g.bestellschluss ? ' · Bestellschluss ' + esc(g.bestellschluss) : ''}</p></div>
          <div class="rw-rechts">${faellig.length ? `<button class="btn sm" type="button" data-gruppe-dauer="${esc(g.id)}"><svg class="i" aria-hidden="true"><use href="#i-check"/></svg>${faellig.length} ${faellig.length === 1 ? 'Dauerauftrag' : 'Daueraufträge'} bestätigen</button>` : ''}</div>
        </div>
        ${zeilen.length ? `<div class="rw-zkopf" aria-hidden="true"><span>Markt</span><span>Verlauf ${esc(kwKurz(kwPlus(w.kw, -8)))}–${esc(kwKurz(kwPlus(w.kw, -1)).slice(3))} · diese Woche · voraus bis ${esc(kwKurz(kwPlus(w.kw, 3)))}</span><span>Antwort ${esc(kwKurz(w.kw))}</span><span></span></div>` : ''}
        ${zeilen.map(zeileHtml).join('') || `<p class="rw-gfuss">${S.filter === 'offen' ? 'Alle Märkte dieser Gruppe sind erledigt.' : 'Keine Märkte für diesen Filter.'}</p>`}
      </section>`;
    }).join('');
    $('#rw-w-gruppen').innerHTML = (html || `<div class="rw-leer rw-glas"><h2>Keine Märkte in dieser Liste</h2><p>${darf('verwalten') ? 'Märkte weisen Sie unter „Zuweisung“ zu.' : 'Die Leitung weist Ihnen Märkte zu.'}</p></div>`) + ruhendHtml(w.ruhend || [], q);
    if (S.zeigeNach) {   // aus dem Verlauf eines Marktes in eine andere Woche gewechselt: Zeile zeigen
      const z = $(`.rw-zeile[data-id="${CSS.escape(S.zeigeNach)}"]`); S.zeigeNach = '';
      if (z) { z.scrollIntoView({ block: 'center' }); z.classList.add('blink'); setTimeout(() => z.classList.remove('blink'), 1600); }
    }
  }
  /* Übersicht der Bestellungen dieser Woche (eigene bzw. gewählte Liste): Markt, Lieferweg, Mengen – Klick zeigt die Zeile */
  function bestelltHtml(w, best, mengen) {
    const el = $('#rw-w-bestellt');
    el.hidden = !best.length;
    if (!best.length) { el.innerHTML = ''; return; }
    const ob = best.filter((m) => m.antwort.ohneBerechnung).length;
    el.innerHTML = `<details class="rw-panel rw-glas rw-bestellt"${S.bestelltZu ? '' : ' open'}>
      <summary class="rw-panelkopf"><h2>Bestellungen ${esc(kwKurz(w.kw))}${w.wer ? ' · ' + esc(w.werName) : ''}</h2>
        <span class="rw-sub">${best.length} ${best.length === 1 ? 'Markt' : 'Märkte'} · ${esc(mengenText(mengen))}${ob ? ` · ${ob} ohne Berechnung` : ''}</span></summary>
      <ul class="rw-bliste">${best.map((m) => `<li><button type="button" class="rw-beintrag" data-zeige="${esc(m.id)}">
        <span class="rw-bort">${esc(m.ort)}<span class="rw-sub">${esc([m.strasse, m.kdNr ? 'Kd. ' + m.kdNr : ''].filter(Boolean).join(' · '))}</span></span>
        <span class="rw-sub">${esc(m.lieferwegName || 'ohne Lieferweg')}${w.wer === '*' && m.zustaendigName ? ' · ' + esc(m.zustaendigName) : ''}</span>
        <span class="rw-bmenge">${esc(mengenText(m.antwort.mengen))}${m.antwort.ohneBerechnung ? ' <span class="rw-chip gelb">ohne Berechnung</span>' : ''}${m.antwort.nachtrag ? ' <span class="rw-chip akzent">Nachtrag</span>' : ''}</span>
      </button></li>`).join('')}</ul></details>`;
  }
  $('#rw-w-bestellt').addEventListener('toggle', (ev) => { if (ev.target.matches('details')) S.bestelltZu = !ev.target.open; }, true);
  $('#rw-w-bestellt').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-zeige]'); if (!b) return;
    const id = b.dataset.zeige;
    S.sichtbar.add(id);
    if (S.suche) { S.suche = ''; $('#rw-w-suche').value = ''; }
    renderWoche();
    const z = $(`.rw-zeile[data-id="${CSS.escape(id)}"]`);
    if (z) { z.scrollIntoView({ behavior: 'smooth', block: 'center' }); z.classList.add('blink'); setTimeout(() => z.classList.remove('blink'), 1600); }
  });
  /* Verlauf: acht Wochen davor, diese Woche (Rahmen) und drei Wochen danach (Vorbestellungen), die KW darunter.
     Künftige Wochen sind Knöpfe: ein Klick öffnet diese Woche mit der Zeile des Marktes – dort wird die Vorbestellung eingetragen. */
  function zelleHtml(v, art, m) {
    const leer = art === 'vor' ? 'keine Vorbestellung' : art === 'jetzt' ? 'noch offen' : 'nicht abgefragt';
    const t = `${kwKurz(v.kw)}: ${v.status ? S.d.antworten[v.status] + (v.menge ? ' ' + v.menge : '') : leer}`;
    const [cls, inhalt] = v.status === 'bestellt' ? ['b', String(v.menge)] : v.status === 'ne' ? ['n', 'ne'] : v.status === 'pause' ? ['p', 'P']
      : v.status === 'kein' ? ['', '–'] : art === 'vor' ? ['frei', '+'] : ['o', ''];
    const zelle = `<i class="rw-z ${cls}${art === 'jetzt' ? ' jetzt' : ''}${art === 'vor' && v.status ? ' vor' : ''}">${esc(inhalt)}</i><span>${+v.kw.slice(5)}</span>`;
    return art === 'vor' && m.darfAntworten
      ? `<button type="button" class="rw-zw" data-vor="${esc(v.kw)}" data-markt="${esc(m.id)}" title="${esc(t)} – Woche öffnen" aria-label="${esc(t)} – Woche öffnen">${zelle}</button>`
      : `<span class="rw-zw" title="${esc(t)}">${zelle}</span>`;
  }
  function verlaufText(m) {
    const best = m.verlauf.filter((v) => v.status === 'bestellt'), letzte = best[best.length - 1];
    const vor = (m.vorschau || []).filter((v) => v.status === 'bestellt');
    return [`Bestellt in ${best.length} von ${m.verlauf.length} Wochen`, letzte ? `zuletzt ${kwKurz(letzte.kw)}` : '',
      vor.length ? `vorbestellt ${vor.map((v) => `${kwKurz(v.kw)}: ${v.menge}`).join(', ')}` : ''].filter(Boolean).join(' · ');
  }
  const adresse = (m) => [m.strasse, [m.plz, m.ort].filter(Boolean).join(' ')].filter(Boolean).join(', ');
  function zeileHtml(m) {
    const a = m.antwort, w = S.woche, bus = S.busy.has(m.id);
    const chips = [];
    if (w.wer === '*' && m.zustaendigName) chips.push(`<span class="rw-chip">${esc(m.zustaendigName)}</span>`);
    if (m.dauerText) chips.push(`<span class="rw-chip gruen" title="${esc(m.dauerText)}">${esc(m.dauerText.replace('Dauerauftrag ', 'Dauer '))}</span>`);
    if (m.abfragetag) chips.push(`<span class="rw-chip gelb">${esc(S.d.tage[m.abfragetag])} anrufen</span>`);
    if (m.kauf !== 'regelmaessig') chips.push(kaufChip(m.kauf));
    m.wiedervorlagen.slice(0, 2).forEach((v) => chips.push(`<span class="rw-chip gelb" title="${esc(v.text)}">Wiedervorlage: ${esc(v.text.slice(0, 32))}${v.text.length > 32 ? '…' : ''}</span>`));
    if (!m.winab && m.kdNr) chips.push('<span class="rw-chip akzent" title="Die Kd.-Nr. fehlt im WinAB-Kundenstamm der Verwaltung">nicht im Kundenstamm</span>');
    const nz = m.notizen || 0, nzText = nz ? `${nz} ${nz === 1 ? 'Notiz' : 'Notizen'}` : '';
    const hinweis = m.hinweis || nz ? `<button type="button" class="rw-mhinweis" data-karte="${esc(m.id)}"${m.hinweis ? ` title="${esc(m.hinweis)}"` : ''}>
        <svg class="i" aria-hidden="true"><use href="#i-info"/></svg><span>${m.hinweis ? esc(m.hinweis.replace(/\s*\n\s*/g, ' · ')) : ''}${nz ? `${m.hinweis ? ' ' : ''}<b>${esc(nzText)}</b>` : ''}</span></button>` : '';
    let antwort = '';
    const dis = !m.darfAntworten || bus ? ' disabled' : '';
    if (!a && m.dauerFaellig && !S.offenSeg.has(m.id)) {
      antwort = `<div class="rw-dauerbox"><span>Dauerauftrag fällig: ${esc(mengenText(m.dauer.mengen))}</span>
        ${m.darfAntworten ? `<button class="btn sm" type="button" data-dauer-ok="${esc(m.id)}"${dis}>Bestätigen</button><button class="btn sm ghost" type="button" data-offen="${esc(m.id)}">Abweichend</button>` : ''}</div>`;
    } else if (nichtFaellig(m)) {
      antwort = `<div class="rw-nichtfaellig">Nicht fällig – nächste Lieferung ${esc(kwKurz(m.dauerNaechste))}${m.darfAntworten ? ` <button class="btn sm ghost" type="button" data-offen="${esc(m.id)}">Trotzdem abfragen</button>` : ''}</div>`;
    } else {
      antwort = `<div class="rw-seg antwort" role="group" aria-label="Antwort ${esc(m.ort)}">${Object.entries(S.d.antworten).map(([k, v]) =>
        `<button type="button" data-s="${k}" data-markt="${esc(m.id)}" aria-pressed="${a && a.status === k}"${dis}>${esc(v)}</button>`).join('')}</div>`;
      if (a && a.status === 'bestellt') {
        // Plus und Minus groß; die Zahl lässt sich auch direkt eintippen (Enter oder Feld verlassen speichert)
        antwort += `<div class="rw-mengen-eingabe">${artikel().map((ar) => `<div class="rw-menge"><span>${esc(ar.name)}</span><span class="rw-stepper">
          <button type="button" data-menge="${esc(ar.id)}" data-d="-1" data-markt="${esc(m.id)}" aria-label="${esc(ar.name)} weniger"${dis}>−</button>
          <input class="rw-mzahl" data-mzahl="${esc(ar.id)}" data-markt="${esc(m.id)}" inputmode="numeric" maxlength="3" value="${obj(a.mengen)[ar.id] || 0}" aria-label="${esc(ar.name)}: Menge"${dis}>
          <button type="button" data-menge="${esc(ar.id)}" data-d="1" data-markt="${esc(m.id)}" aria-label="${esc(ar.name)} mehr"${dis}>+</button></span></div>`).join('')}</div>`;
      }
      if (a) antwort += `<div class="rw-azeile"><input class="rw-eingabe rw-notizfeld" data-notiz="${esc(m.id)}" maxlength="300" value="${esc(a.notiz)}" placeholder="Notiz zur Woche (optional)" aria-label="Notiz zur Woche ${esc(m.ort)}"${dis}>
        ${a.status === 'bestellt' ? `<label class="rw-check"><input type="checkbox" data-ob="${esc(m.id)}"${a.ohneBerechnung ? ' checked' : ''}${dis}> ohne Berechnung</label>` : ''}</div>`;
    }
    const zurueck = a && m.darfAntworten ? `<button type="button" class="rw-zuruecksetzen${S.zurueckFrage === m.id ? ' frage' : ''}" data-zurueck="${esc(m.id)}"${dis}>${esc(S.zurueckFrage === m.id ? zurueckFrageText() : 'Zurücksetzen')}</button>` : '';
    const meta = a ? `<div class="rw-ameta">${a.nachtrag ? '<span class="rw-chip akzent">Nachtrag</span>' : ''}<span>Erfasst: ${esc(a.von)}${a.t ? ' · ' + esc(zeitpunkt(a.t)) : ''}</span>${zurueck}</div>` : '';
    const jetzt = { kw: w.kw, status: a ? a.status : '', menge: a ? summe(a.mengen) : 0 };
    const adr = adresse(m);
    return `<div class="rw-zeile${erledigt(m) ? ' erledigt' : ''}${S.sichtbar.has(m.id) && S.filter === 'offen' && erledigt(m) ? ' gerade' : ''}" data-id="${esc(m.id)}">
      <div class="rw-c-markt">
        <button type="button" class="rw-mname" data-karte="${esc(m.id)}" title="Marktkarte öffnen">${esc(m.ort)}</button>
        ${adr ? `<button type="button" class="rw-madresse" data-karte="${esc(m.id)}" title="Marktkarte öffnen">${esc(adr)}</button>` : ''}
        ${m.kdNr ? `<span class="rw-mkd">Kd. ${esc(m.kdNr)}</span>` : ''}
        ${chips.length ? `<div class="rw-hinweise">${chips.join('')}</div>` : ''}${hinweis}
      </div>
      <div class="rw-c-verlauf"><div class="rw-zellen" role="group" aria-label="Verlauf ${esc(m.ort)}">${m.verlauf.map((v) => zelleHtml(v, '', m)).join('')}${zelleHtml(jetzt, 'jetzt', m)}${(m.vorschau || []).map((v) => zelleHtml(v, 'vor', m)).join('')}</div>
        <p class="rw-vtext">${esc(verlaufText(m))}</p></div>
      <div class="rw-c-antwort rw-antwort">${meta}${antwort}</div>
      <a class="rw-c-akte rw-akte-link" href="#markt/${esc(m.id)}" data-gehe="markt/${esc(m.id)}" aria-label="Marktakte ${esc(m.ort)} öffnen"><svg class="i" aria-hidden="true"><use href="#i-rechts"/></svg></a>
    </div>`;
  }
  const zurueckFrageText = () => (S.woche && S.woche.abschluss && S.woche.abschluss.exportiert ? 'Schon an WinAB übergeben – wirklich zurücksetzen?' : 'Wirklich zurücksetzen?');
  function ruhendHtml(liste, q) {
    const z = liste.filter((m) => passt(m, q));
    if (!liste.length) return '';
    return `<details class="rw-panel rw-glas" id="rw-ruhend"><summary class="rw-panelkopf"><h2>Ruhende Märkte <span class="rw-sub">${liste.length} · seit längerer Zeit ohne Bestellung, nicht in der Abfrage</span></h2></summary>
      <div class="rw-tabelle-wrap"><table class="rw-tabelle rw-karten"><thead><tr><th>Markt</th><th>Lieferweg</th><th>Zuletzt bestellt</th><th>Hinweis</th><th></th></tr></thead><tbody>
      ${z.map((m) => `<tr><td data-label="Markt"><button type="button" class="rw-mname" data-karte="${esc(m.id)}" title="Marktkarte öffnen">${esc(m.ort)}</button><span class="rw-sub">${esc([m.strasse, m.kdNr ? 'Kd. ' + m.kdNr : ''].filter(Boolean).join(' · '))}</span></td>
        <td data-label="Lieferweg">${esc(m.lieferwegName)}</td><td data-label="Zuletzt bestellt">${esc(m.letzte ? kwText(m.letzte) : 'nie')}</td>
        <td data-label="Hinweis" class="rw-sub">${esc((m.hinweis || '').slice(0, 80))}</td>
        <td class="rw-voll"><a class="btn sm ghost" href="#markt/${esc(m.id)}" data-gehe="markt/${esc(m.id)}">Akte</a>${m.darfPflegen ? ` <button class="btn sm" type="button" data-wieder="${esc(m.id)}">Wieder abfragen</button>` : ''}</td></tr>`).join('')}
      </tbody></table></div></details>`;
  }
  /* Antwort senden; bei Erfolg Zeile aktualisieren, bei Konflikt neu laden. Ändert sich die Antwort (Bestellt, Kein Bedarf,
     … oder zurückgesetzt), bietet der Hinweis „Rückgängig“ an: stellt die vorige Antwort samt Mengen und Notiz wieder her. */
  async function sende(id, teil, mitRueck = true) {
    const m = S.woche.gruppen.flatMap((g) => g.maerkte).find((x) => x.id === id);
    if (!m || S.busy.has(id)) return;
    const a = m.antwort || {}, kw = S.woche.kw;
    const vorher = m.antwort ? { status: a.status, mengen: { ...obj(a.mengen) }, ohneBerechnung: !!a.ohneBerechnung, notiz: a.notiz || '' } : null;
    const body = { markt: id, kw: S.woche.kw, status: a.status || '', mengen: obj(a.mengen), ohneBerechnung: !!a.ohneBerechnung, notiz: a.notiz || '', r: a.r || 0, ...teil };
    if (body.status !== 'bestellt') { body.mengen = {}; body.ohneBerechnung = false; }
    S.busy.add(id); renderWoche();
    const r = await api('rewe_antwort', body);
    S.busy.delete(id);
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status === 409) { toast(r.data.error || 'Inzwischen geändert – neu geladen.', true); await ladeWoche(); return; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Speichern fehlgeschlagen'), true); renderWoche(); return; }
    m.antwort = r.data.antwort;
    S.offenSeg.delete(id);
    S.sichtbar.add(id);   // Zeile bleibt stehen (Mengen, Notiz), auch im Filter „Offen“
    renderWoche();
    const neu = m.antwort ? m.antwort.status : '';
    if (!mitRueck) toast(`${m.ort}: rückgängig gemacht`);
    else if (neu !== (vorher ? vorher.status : '')) {
      const was = neu ? S.d.antworten[neu] + (neu === 'bestellt' ? ' · ' + mengenText(m.antwort.mengen) : '') : 'Antwort zurückgesetzt';
      toast(`${m.ort}: ${was}`, false, { text: 'Rückgängig', fn: () => {
        if (!S.woche || S.woche.kw !== kw) { toast('Die Woche wurde gewechselt – bitte in der Woche selbst ändern.', true); return; }
        sende(id, vorher ? { ...vorher } : { status: '', notiz: '' }, false);
      } });
    }
  }
  const finde = (id) => S.woche.gruppen.flatMap((g) => g.maerkte).find((x) => x.id === id);
  $('#rw-w-gruppen').addEventListener('click', async (ev) => {
    const t = ev.target.closest('button'); if (!t || t.disabled) return;
    if (t.dataset.karte) { oeffneKarte(t.dataset.karte); return; }
    if (t.dataset.zurueck) {   // Antwort zurücksetzen (wieder offen): erst nachfragen, zweiter Klick setzt zurück
      const id = t.dataset.zurueck;
      if (S.zurueckFrage !== id) {
        S.zurueckFrage = id; t.textContent = zurueckFrageText(); t.classList.add('frage');
        clearTimeout(S.zurueckTimer);
        S.zurueckTimer = setTimeout(() => { if (S.zurueckFrage !== id) return; S.zurueckFrage = ''; const b = $(`[data-zurueck="${CSS.escape(id)}"]`); if (b) { b.textContent = 'Zurücksetzen'; b.classList.remove('frage'); } }, 5000);
        return;
      }
      S.zurueckFrage = ''; clearTimeout(S.zurueckTimer);
      sende(id, { status: '', notiz: '' }); return;
    }
    if (t.dataset.vor) {   // künftige Woche aus dem Verlauf: dort die Vorbestellung eintragen
      S.kw = t.dataset.vor; neuAnsehen(); S.sichtbar.add(t.dataset.markt); S.zeigeNach = t.dataset.markt; zeigeTab('woche', S.kw); return;
    }
    if (t.dataset.s) {
      const m = finde(t.dataset.markt), s = t.dataset.s;
      if (m.antwort && m.antwort.status === s) return;
      if (s === 'bestellt') {
        const vorschlag = summe(m.dauer && m.dauer.mengen) ? m.dauer.mengen : { [artikel()[0].id]: 1 };
        sende(m.id, { status: 'bestellt', mengen: m.antwort && summe(m.antwort.mengen) ? m.antwort.mengen : vorschlag });
      } else sende(m.id, { status: s });
    } else if (t.dataset.menge) {
      const m = finde(t.dataset.markt), neu = { ...obj(m.antwort.mengen) };
      neu[t.dataset.menge] = Math.max(0, (neu[t.dataset.menge] || 0) + Number(t.dataset.d));
      if (!summe(neu)) { toast('Mindestens eine Menge – sonst „Kein Bedarf“ wählen.', true); return; }
      sende(m.id, { status: 'bestellt', mengen: neu });
    } else if (t.dataset.dauerOk) {
      const m = finde(t.dataset.dauerOk); sende(m.id, { status: 'bestellt', mengen: m.dauer.mengen });
    } else if (t.dataset.offen) { S.offenSeg.add(t.dataset.offen); renderWoche(); }
    else if (t.dataset.gruppeDauer !== undefined) {
      const g = S.woche.gruppen.find((x) => x.id === t.dataset.gruppeDauer);
      const ids = g.maerkte.filter((m) => !m.antwort && m.dauerFaellig && m.darfAntworten).map((m) => m.id);
      t.disabled = true;
      const r = await api('rewe_dauer_uebernehmen', { kw: S.woche.kw, wer: S.wer, maerkte: ids });
      if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Übernehmen fehlgeschlagen'), true); t.disabled = false; return; }
      toast(`${r.data.uebernommen} ${r.data.uebernommen === 1 ? 'Dauerauftrag' : 'Daueraufträge'} bestätigt`);
      ladeWoche();
    } else if (t.dataset.wieder) {
      const r = await api('rewe_markt_save', { id: t.dataset.wieder, kauf: 'gelegentlich' });
      if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Ändern fehlgeschlagen'), true); return; }
      toast(`${r.data.markt.ort}: wieder in der Abfrage (gelegentlich)`); ladeWoche();
    }
  });
  $('#rw-w-gruppen').addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && ev.target.dataset.mzahl) ev.target.blur(); });
  $('#rw-w-gruppen').addEventListener('change', (ev) => {
    const t = ev.target;
    if (t.dataset.mzahl) {   // Menge eingetippt
      const m = finde(t.dataset.markt); if (!m || !m.antwort) return;
      const n = parseInt(t.value.replace(/\D/g, ''), 10);
      const neu = { ...obj(m.antwort.mengen), [t.dataset.mzahl]: Number.isFinite(n) && n > 0 ? Math.min(n, 999) : 0 };
      if (!summe(neu)) { toast('Mindestens eine Menge – sonst „Kein Bedarf“ wählen.', true); renderWoche(); return; }
      sende(m.id, { status: 'bestellt', mengen: neu });
    } else if (t.dataset.notiz) sende(t.dataset.notiz, { notiz: t.value.trim() });
    else if (t.dataset.ob) sende(t.dataset.ob, { ohneBerechnung: t.checked });
  });
  $('#rw-w-zurueck').addEventListener('click', () => { S.kw = kwPlus(S.kw, -1); neuAnsehen(); zeigeTab('woche', S.kw); });
  $('#rw-w-vor').addEventListener('click', () => { S.kw = kwPlus(S.kw, 1); neuAnsehen(); zeigeTab('woche', S.kw); });
  $('#rw-w-heute').addEventListener('click', () => { S.kw = S.d.abfrage; neuAnsehen(); zeigeTab('woche', S.kw); });
  $('#rw-w-wer').addEventListener('change', (ev) => { S.wer = ev.target.value; neuAnsehen(); ladeWoche(); });
  $('#rw-w-suche').addEventListener('input', (ev) => { S.suche = ev.target.value; renderWoche(); });
  $('#rw-w-filter').addEventListener('click', (ev) => { const b = ev.target.closest('[data-f]'); if (b) { S.filter = b.dataset.f; S.sichtbar.clear(); renderWoche(); } });

  /* ================= Märkte und Marktakte ================= */
  async function ladeMaerkte() {
    const r = await api('rewe_maerkte');
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Die Märkte konnten nicht geladen werden'), true); return; }
    S.maerkte = r.data.maerkte;
    if (S.tab === 'zuweisung') renderZuweisung(); else if (S.tab === 'dauer') renderDauer(); else renderMaerkte();
  }
  function renderMaerkte() {
    if (!S.maerkte) return;
    const q = S.mSuche.trim().toLocaleLowerCase('de-DE');
    const z = S.maerkte.filter((m) => passt(m, q) && (!S.mLw || m.lieferweg === S.mLw) && (!S.mKauf || m.kauf === S.mKauf));
    $('#rw-m-anzahl').textContent = `${z.length} von ${S.maerkte.length}`;
    $('#rw-m-neu').hidden = !darf('verwalten');
    const jahr = S.d.heute.slice(0, 4);
    $('#rw-m-tabelle').innerHTML = `<thead><tr><th>Markt</th><th>Kd.-Nr.</th><th>Lieferweg</th><th>Zuständig</th><th>Kaufbereitschaft</th><th>Dauerauftrag</th><th class="rw-zahl">${esc(jahr)}</th><th>Zuletzt</th></tr></thead><tbody>
      ${z.map((m) => `<tr class="rw-klick" data-gehe="markt/${esc(m.id)}" tabindex="0">
        <td data-label="Markt" class="rw-voll"><span class="rw-name">${esc(m.ort)}</span><span class="rw-sub">${esc([m.strasse, m.name].filter(Boolean).join(' · '))}</span></td>
        <td data-label="Kd.-Nr.">${esc(m.kdNr)}${m.kdNr && !m.winab ? ' <span class="rw-chip akzent" title="nicht im WinAB-Kundenstamm">?</span>' : ''}</td>
        <td data-label="Lieferweg">${esc(m.lieferwegName)}</td><td data-label="Zuständig">${esc(m.zustaendigName || '—')}</td>
        <td data-label="Kaufbereitschaft">${kaufChip(m.kauf)}</td><td data-label="Dauerauftrag" class="rw-sub">${esc((m.dauerText || '').replace('Dauerauftrag ', ''))}</td>
        <td data-label="Bestellungen ${esc(jahr)}" class="rw-zahl">${m.anzahlJahr || ''}</td><td data-label="Zuletzt">${esc(m.letzte ? kwText(m.letzte) : '—')}</td></tr>`).join('')
        || '<tr><td colspan="8" class="rw-leerzeile">Keine Märkte für diesen Filter.</td></tr>'}</tbody>`;
  }
  $('#rw-m-suche').addEventListener('input', (ev) => { S.mSuche = ev.target.value; renderMaerkte(); });
  $('#rw-m-lw').addEventListener('change', (ev) => { S.mLw = ev.target.value; renderMaerkte(); });
  $('#rw-m-kauf').addEventListener('change', (ev) => { S.mKauf = ev.target.value; renderMaerkte(); });
  $('#rw-m-tabelle').addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && ev.target.dataset.gehe) ev.target.click(); });
  $('#rw-m-neu').addEventListener('click', () => oeffneMarkt(null));

  async function ladeAkte(id) {
    const r = await api('rewe_markt', null, '&id=' + encodeURIComponent(id));
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status === 404) { toast('Markt nicht gefunden.', true); zeigeTab('maerkte'); return; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Die Akte konnte nicht geladen werden'), true); return; }
    S.akte = r.data;
    renderAkte();
  }
  /* Eintrag im Verlauf der Notizen (Marktakte und Marktkarte) */
  const notizLi = (n) => `<li>
    <time datetime="${esc(n.t)}">${esc(zeitpunkt(n.t).split(',')[0])}</time>
    <span class="rw-av${n.art === 'system' ? ' system' : ''}" aria-hidden="true">${n.art === 'system' ? '↻' : esc(initialen(n.von))}</span>
    <div><div class="rw-kopfzeile"><b>${esc(n.von)}</b><span class="rw-chip">${esc(S.d.notizArten[n.art] || n.art)}</span>
      ${n.wv ? `<span class="rw-chip ${n.erledigt ? 'gruen' : 'gelb'}">Wiedervorlage ${esc(datum(n.wv))}${n.erledigt ? ' · erledigt' : ''}</span>` : ''}</div>
      <p>${esc(n.text)}</p></div></li>`;
  /* Wochenraster je Jahr (Marktakte und Marktkarte): eine Zelle je KW, Farbe nach Antwort */
  function heatHtml(A) {
    const wochen = obj(A.wochen), z = obj(A.zahlen), jahr = S.d.heute.slice(0, 4);
    const jahre = [...new Set(Object.keys(wochen).map((k) => k.slice(0, 4)).concat([jahr]))].sort().reverse().slice(0, 7);
    return jahre.map((j) => {
      const n = (+j % 4 === 0 && +j % 100 !== 0) || +j % 400 === 0 ? 0 : 0; void n;
      const max = isoKw(new Date(Date.UTC(+j, 11, 28))).slice(5);
      const zellen = [];
      for (let w = 1; w <= 53; w++) {
        const k = `${j}-${String(w).padStart(2, '0')}`;
        if (w > +max) { zellen.push('<i class="leer" aria-hidden="true"></i>'); continue; }
        const e = wochen[k];
        const cls = e ? ({ bestellt: 'b', ne: 'n', pause: 'p', kein: '' }[e.status] ?? '') : (k > S.d.heute ? 'leer' : 'leer');
        const t = `${kwKurz(k)}: ${e ? S.d.antworten[e.status] + (e.status === 'bestellt' ? ' ' + mengenText(e.mengen) : '') + (e.notiz ? ' – ' + e.notiz : '') : 'keine Angabe'}`;
        zellen.push(`<i class="${cls}${k === S.d.abfrage ? ' jetzt' : ''}" title="${esc(t)}"></i>`);
      }
      return `<span class="jahr">${esc(j)}</span><div class="wochen" role="img" aria-label="${esc(j)}: ${obj(z[j]).lieferungen || 0} Bestellungen">${zellen.join('')}</div>`;
    }).join('');
  }
  function renderAkte() {
    const A = S.akte, m = A.markt, z = obj(A.zahlen);
    const jahr = S.d.heute.slice(0, 4), vorjahr = String(+jahr - 1);
    const heat = heatHtml(A);
    const notizen = A.notizen;
    const offeneWv = notizen.filter((n) => n.wv && !n.erledigt);
    const kontakte = m.ansprechpartner || [];
    const zuHist = m.zustaendigHist.map((h) => `${esc(h.name)} ab ${esc(kwText(h.ab))}`).reverse().join('<br>');
    const lwHist = m.lieferwegHist.map((h) => `${esc(h.name)} ab ${esc(kwText(h.ab))}`).reverse().join('<br>');
    const naechste = A.naechsteDauer ? ` · nächste Lieferung ${kwText(A.naechsteDauer)}` : '';
    $('#rw-akte').innerHTML = `
      <div class="rw-knopfreihe" style="justify-content:flex-start;margin:0 0 10px"><a class="btn sm ghost" href="#maerkte" data-gehe="maerkte"><svg class="i" aria-hidden="true"><use href="#i-links"/></svg>Alle Märkte</a></div>
      <section class="rw-aktekopf rw-glas">
        <div><h1>${esc(m.ort)}</h1>
          <div class="rw-meta"><span>${esc(m.name)}</span><span>${esc([m.strasse, [m.plz, m.ort].filter(Boolean).join(' ')].filter(Boolean).join(', '))}</span>
            ${m.kdNr ? `<span>Kd. ${esc(m.kdNr)}${m.winab ? ' (WinAB)' : ' – nicht im Kundenstamm'}</span>` : ''}${m.reweNr ? `<span>REWE-Markt ${esc(m.reweNr)}</span>` : ''}${m.region ? `<span>Region ${esc(m.region)}</span>` : ''}</div>
          <div class="rw-hinweise" style="margin-top:8px">${kaufChip(m.kauf)}<span class="rw-chip blau">${esc(m.lieferwegName || 'ohne Lieferweg')}</span>${m.zustaendigName ? `<span class="rw-chip">${esc(m.zustaendigName)}</span>` : ''}</div></div>
        <div class="rw-knopfreihe" style="margin:0">
          ${m.telefon ? `<a class="btn" href="tel:${esc(m.telefon.replace(/[^\d+]/g, ''))}"><svg class="i" aria-hidden="true"><use href="#i-telefon"/></svg>Anrufen</a>` : ''}
          ${A.darfPflegen ? `<button class="btn" type="button" id="rw-a-bearbeiten"><svg class="i" aria-hidden="true"><use href="#i-stift"/></svg>Bearbeiten</button>
          <button class="btn primary" type="button" id="rw-a-notiz"><svg class="i" aria-hidden="true"><use href="#i-plus"/></svg>Notiz</button>` : ''}
        </div>
      </section>
      <div class="rw-akte">
        <div>
          <section class="rw-panel rw-glas">
            <div class="rw-panelkopf"><h2>Wochenverlauf</h2><span class="rw-hilfe">jede Antwort der Abfrage · Lieferwoche</span></div>
            <div class="rw-zahlen">
              <div><span>Bestellungen ${esc(jahr)}</span><b>${obj(z[jahr]).lieferungen || 0}</b></div>
              <div><span>Bestellungen ${esc(vorjahr)}</span><b>${obj(z[vorjahr]).lieferungen || 0}</b></div>
              <div><span>Stück ${esc(jahr)}</span><b>${zahl(summe(obj(z[jahr]).mengen))}</b></div>
              <div><span>Letzte Bestellung</span><b>${esc(z.letzte ? kwKurz(z.letzte) + '/' + z.letzte.slice(2, 4) : '—')}</b></div>
            </div>
            <div class="rw-heat">${heat}</div>
            <div class="rw-legende"><span><i class="rw-z b"></i>bestellt</span><span><i class="rw-z"></i>kein Bedarf</span><span><i class="rw-z n"></i>nicht erreicht</span><span><i class="rw-z p"></i>Pause</span><span><i class="rw-z o"></i>keine Angabe</span></div>
          </section>
          <section class="rw-panel rw-glas">
            <div class="rw-panelkopf"><h2>Notizen und Verlauf</h2></div>
            <ol class="rw-verlaufsliste">${notizen.map(notizLi).join('') || '<li class="rw-leerzeile" style="display:block">Noch keine Notizen.</li>'}</ol>
          </section>
        </div>
        <aside>
          ${offeneWv.length ? `<section class="rw-panel rw-glas"><div class="rw-panelkopf"><h2>Wiedervorlagen</h2></div>${offeneWv.map((n) => `<div class="rw-wv"><p><b>${esc(datum(n.wv))}</b> · ${esc(n.text)}</p>${A.darfPflegen ? `<button class="btn sm" type="button" data-wv-erledigt="${esc(n.id)}">Erledigt</button>` : ''}</div>`).join('')}</section>` : ''}
          <section class="rw-panel rw-glas"><div class="rw-panelkopf"><h2>Zuständig und Lieferweg</h2></div>
            <dl class="rw-kv"><dt>Zuständig</dt><dd>${zuHist || '—'}</dd><dt>Lieferweg</dt><dd>${lwHist || '—'}</dd>
              <dt>Abfragetag</dt><dd>${esc(S.d.tage[m.abfragetag] || '—')}</dd>
              <dt>Dauerauftrag</dt><dd>${m.dauer.rhythmus ? esc(`${S.d.rhythmen[m.dauer.rhythmus]}: ${mengenText(m.dauer.mengen)} ab ${kwText(m.dauer.ab)}${m.dauer.pauseBis ? ', Pause bis ' + kwText(m.dauer.pauseBis) : ''}${naechste}`) : 'keiner'}</dd>
              ${m.telefon ? `<dt>Telefon</dt><dd>${esc(m.telefon)}</dd>` : ''}</dl></section>
          ${m.hinweis ? `<section class="rw-panel rw-glas"><div class="rw-panelkopf"><h2>Hinweis</h2></div><p class="rw-notiz" style="margin:0">${esc(m.hinweis)}</p></section>` : ''}
          <section class="rw-panel rw-glas"><div class="rw-panelkopf"><h2>Ansprechpartner</h2></div>
            ${kontakte.map((k) => `<div class="rw-kontakt"><span class="rw-av" aria-hidden="true">${esc(initialen(k.name))}</span><div><b>${esc(k.name)}</b><span class="rw-sub">${esc([k.rolle, k.telefon, k.email].filter(Boolean).join(' · '))}</span></div></div>`).join('') || '<p class="rw-hilfe" style="margin:0">Noch keine Ansprechpartner.</p>'}
            <p class="rw-hilfe" style="margin:8px 0 0">Nur im REWE-Modul sichtbar, nicht im CRM.</p></section>
        </aside>
      </div>`;
  }
  $('#rw-akte').addEventListener('click', async (ev) => {
    if (ev.target.closest('#rw-a-bearbeiten')) oeffneMarkt(S.akte.markt);
    else if (ev.target.closest('#rw-a-notiz')) oeffneNotiz(S.akte.markt.id);
    else {
      const b = ev.target.closest('[data-wv-erledigt]'); if (!b) return;
      b.disabled = true;
      const r = await api('rewe_notiz_save', { id: b.dataset.wvErledigt, erledigt: true });
      if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Speichern fehlgeschlagen'), true); b.disabled = false; return; }
      toast('Wiedervorlage erledigt'); ladeAkte(S.akteId);
    }
  });

  /* ---------- Eingabemaske Markt ---------- */
  function kontaktZeile(k = {}) {
    return `<div class="rw-formraster rw-kontaktzeile" style="grid-template-columns:repeat(4,minmax(0,1fr)) auto;align-items:end;margin-bottom:8px">
      <label>Name<input class="rw-eingabe" data-k="name" maxlength="80" value="${esc(k.name || '')}"></label>
      <label>Rolle<input class="rw-eingabe" data-k="rolle" maxlength="80" value="${esc(k.rolle || '')}" placeholder="z. B. Metzgerei"></label>
      <label>Telefon<input class="rw-eingabe" data-k="telefon" maxlength="60" value="${esc(k.telefon || '')}"></label>
      <label>E-Mail<input class="rw-eingabe" data-k="email" maxlength="120" value="${esc(k.email || '')}"></label>
      <button class="rw-dialog-schliessen" type="button" data-k-weg aria-label="Ansprechpartner entfernen">×</button></div>`;
  }
  function oeffneMarkt(m) {
    S.edit = m;
    const neu = !m, verw = darf('verwalten');
    $('#mk-titel').textContent = neu ? 'Markt anlegen' : `${m.ort} bearbeiten`;
    $('#mk-stamm').hidden = !verw; $('#mk-lw-feld').hidden = !neu; $('#mk-zu-feld').hidden = !neu;
    const e = m ? m.eigen : {};
    $('#mk-name').value = e.name || ''; $('#mk-kdnr').value = m ? m.kdNr : ''; $('#mk-rewenr').value = m ? m.reweNr : '';
    $('#mk-strasse').value = e.strasse || ''; $('#mk-plz').value = e.plz || ''; $('#mk-ort').value = e.ort || ''; $('#mk-region').value = m ? m.region : '';
    $('#mk-name').placeholder = m && m.winab ? `aus dem Kundenstamm: ${m.name}` : 'z. B. REWE Musterstadt';
    $('#mk-ort').placeholder = m && m.winab ? m.ort : '';
    $('#mk-lw').innerHTML = lwOptionen(''); $('#mk-zu').innerHTML = personOptionen('<option value="">niemand</option>');
    $('#mk-kauf').innerHTML = kaufOptionen(''); $('#mk-kauf').value = m ? m.kauf : 'regelmaessig';
    $('#mk-tag').innerHTML = Object.entries(S.d.tage).map(([k, v]) => `<option value="${esc(k)}">${esc(k ? v : 'kein fester Tag')}</option>`).join(''); $('#mk-tag').value = m ? m.abfragetag : '';
    $('#mk-telefon').value = e.telefon || ''; $('#mk-telefon').placeholder = m && m.winab && m.telefon ? `Kundenstamm: ${m.telefon}` : '';
    const d = m ? m.dauer : { rhythmus: 0, mengen: {}, ab: '', pauseBis: '' };
    $('#mk-rhythmus').innerHTML = Object.entries(S.d.rhythmen).map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join(''); $('#mk-rhythmus').value = String(d.rhythmus || 0);
    $('#mk-dab').value = d.ab || S.d.abfrage; $('#mk-dpause').value = d.pauseBis || '';
    $('#mk-dmengen').innerHTML = artikel().map((a) => `<label>${esc(a.name)}<input class="rw-eingabe" data-dm="${esc(a.id)}" inputmode="numeric" maxlength="3" value="${obj(d.mengen)[a.id] || ''}"></label>`).join('');
    $('#mk-kontakte').innerHTML = (m ? m.ansprechpartner : []).map(kontaktZeile).join('');
    $('#mk-hinweis').value = m ? m.hinweis : '';
    $('#mk-meldung').textContent = '';
    $('#dlg-markt').showModal();
  }
  $('#mk-kontakt-neu').addEventListener('click', () => { if ($$('.rw-kontaktzeile').length < 12) $('#mk-kontakte').insertAdjacentHTML('beforeend', kontaktZeile()); });
  $('#mk-kontakte').addEventListener('click', (ev) => { const b = ev.target.closest('[data-k-weg]'); if (b) b.closest('.rw-kontaktzeile').remove(); });
  $('#mk-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const m = S.edit, rh = +$('#mk-rhythmus').value;
    const mengen = {}; $$('[data-dm]').forEach((i) => { const n = parseInt(i.value, 10); if (n > 0) mengen[i.dataset.dm] = n; });
    const body = {
      kauf: $('#mk-kauf').value, abfragetag: $('#mk-tag').value, telefon: $('#mk-telefon').value.trim(), hinweis: $('#mk-hinweis').value,
      dauer: rh ? { rhythmus: rh, mengen, ab: $('#mk-dab').value.trim(), pauseBis: $('#mk-dpause').value.trim() } : { rhythmus: 0 },
      ansprechpartner: $$('.rw-kontaktzeile').map((z) => Object.fromEntries($$('[data-k]', z).map((i) => [i.dataset.k, i.value.trim()]))),
    };
    if (darf('verwalten')) Object.assign(body, { name: $('#mk-name').value.trim(), kdNr: $('#mk-kdnr').value.trim(), reweNr: $('#mk-rewenr').value.trim(),
      strasse: $('#mk-strasse').value.trim(), plz: $('#mk-plz').value.trim(), ort: $('#mk-ort').value.trim(), region: $('#mk-region').value.trim() });
    if (m) Object.assign(body, { id: m.id, rev: m.rev }); else Object.assign(body, { lieferweg: $('#mk-lw').value, zustaendig: $('#mk-zu').value });
    const r = await api('rewe_markt_save', body);
    if (r.status !== 200 || !r.data.ok) { $('#mk-meldung').textContent = fehlerText(r, 'Speichern fehlgeschlagen'); return; }
    $('#dlg-markt').close();
    toast(`${r.data.markt.ort} gespeichert`);
    if (!m) { zeigeTab('markt', r.data.markt.id); return; }
    if (S.tab === 'maerkte' && S.akteId) ladeAkte(S.akteId); else if (S.tab === 'woche') ladeWoche(); else ladeMaerkte();
  });

  /* ---------- Eingabemaske Notiz ---------- */
  function oeffneNotiz(markt) {
    S.notizMarkt = markt;
    $('#nz-art').innerHTML = Object.entries(S.d.notizArten).filter(([k]) => k !== 'system').map(([k, v]) => `<option value="${esc(k)}">${esc(v)}</option>`).join('');
    $('#nz-text').value = ''; $('#nz-wv').value = ''; $('#nz-meldung').textContent = '';
    $('#dlg-notiz').showModal();
  }
  $('#nz-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const r = await api('rewe_notiz_save', { markt: S.notizMarkt, art: $('#nz-art').value, text: $('#nz-text').value, wiedervorlage: $('#nz-wv').value });
    if (r.status !== 200 || !r.data.ok) { $('#nz-meldung').textContent = fehlerText(r, 'Speichern fehlgeschlagen'); return; }
    $('#dlg-notiz').close(); toast('Notiz gespeichert');
    if (S.akteId) ladeAkte(S.akteId);
  });
  $$('dialog').forEach((d) => d.addEventListener('click', (ev) => { if (ev.target.closest('[data-schliessen]')) d.close(); }));

  /* ================= Marktkarte (Fenster: Klick auf Name oder Adresse eines Marktes) =================
     Links der wichtige Hinweis (speichert von selbst), Ansprechpartner und Dauerauftrag; rechts Reiter Notizen (neue
     Notiz mit Art und Wiedervorlage), Verlauf der Wochen und offene Wiedervorlagen. Daten aus rewe_markt (wie die Akte). */
  const K = { id: '', akte: null, reiter: 'notizen', art: 'notiz', timer: 0, speichert: false };
  const dk = $('#dlg-karte');
  const kStatus = (t) => { const e = $('#kt-hstatus'); if (e) e.textContent = t; };
  async function oeffneKarte(id) {
    clearTimeout(K.timer);
    if (K.akte && K.id !== id) await hinweisSpeichern();
    const m = S.woche ? finde(id) : null;
    K.id = id; K.akte = null; K.reiter = 'notizen'; K.art = 'notiz';
    $('#kt-titel').textContent = m ? m.ort : 'Markt'; $('#kt-adresse').textContent = ''; $('#kt-chips').innerHTML = ''; $('#kt-knoepfe').innerHTML = '';
    $('#kt-inhalt').innerHTML = '<p class="rw-hilfe">Wird geladen …</p>';
    if (!dk.open) dk.showModal();
    await ladeKarte();
  }
  async function ladeKarte() {
    const id = K.id;
    const r = await api('rewe_markt', null, '&id=' + encodeURIComponent(id));
    if (id !== K.id) return;
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { $('#kt-inhalt').innerHTML = `<p class="rw-meldung">${esc(fehlerText(r, 'Die Marktkarte konnte nicht geladen werden'))}</p>`; return; }
    const offen = $('#kt-hinweis') && K.akte && K.akte.markt.id === id ? $('#kt-hinweis').value : null;   // getippter Hinweis bleibt stehen
    K.akte = r.data;
    renderKarte(offen);
  }
  function renderKarte(hinweisText = null) {
    const A = K.akte, m = A.markt, darfP = A.darfPflegen, id = esc(m.id), z = obj(A.zahlen), jahr = S.d.heute.slice(0, 4);
    $('#kt-titel').textContent = m.ort;
    $('#kt-adresse').innerHTML = [esc(adresse(m)), m.kdNr ? `<b>Kd. ${esc(m.kdNr)}</b>` : '', m.reweNr ? `REWE-Markt ${esc(m.reweNr)}` : ''].filter(Boolean).join(' · ');
    $('#kt-chips').innerHTML = kaufChip(m.kauf) + `<span class="rw-chip blau">${esc(m.lieferwegName || 'ohne Lieferweg')}</span>`
      + (m.abfragetag ? `<span class="rw-chip gelb">${esc(S.d.tage[m.abfragetag])} anrufen</span>` : '') + (m.zustaendigName ? `<span class="rw-chip">${esc(m.zustaendigName)}</span>` : '');
    $('#kt-knoepfe').innerHTML = (m.telefon ? `<a class="btn sm" href="tel:${esc(m.telefon.replace(/[^\d+]/g, ''))}"><svg class="i" aria-hidden="true"><use href="#i-telefon"/></svg>${esc(m.telefon)}</a>` : '')
      + `<a class="btn sm" href="#markt/${id}" data-gehe="markt/${id}" data-karte-zu>Marktakte</a>`;
    const notizen = A.notizen.filter((n) => n.art !== 'system'), offeneWv = A.notizen.filter((n) => n.wv && !n.erledigt);
    const kontakte = m.ansprechpartner || [], d = m.dauer;
    const arten = Object.entries(S.d.notizArten).filter(([k]) => k !== 'system');
    const reiter = [['notizen', `Notizen · ${notizen.length}`], ['verlauf', 'Verlauf der Wochen'], ['wv', `Wiedervorlagen · ${offeneWv.length}`]];
    $('#kt-inhalt').innerHTML = `
      <div class="rw-klinks">
        <section class="rw-ksektion">
          <div class="rw-kzeile"><h3><label for="kt-hinweis">Wichtiger Hinweis</label></h3><span class="rw-sub" id="kt-hstatus" aria-live="polite"></span></div>
          <textarea class="rw-eingabe rw-khinweis" id="kt-hinweis" rows="8" maxlength="4000" data-ohne-warnung${darfP ? '' : ' readonly'}
            placeholder="${darfP ? 'z. B. nur donnerstags anrufen, Anlieferung über die Rampe, Rechnung an die Zentrale …' : 'Kein Hinweis.'}">${esc(hinweisText ?? m.hinweis)}</textarea>
          ${darfP ? '<p class="rw-hilfe">Speichert von selbst und steht in der Wochenliste unter der Adresse.</p>' : ''}
        </section>
        <section class="rw-ksektion"><h3>Ansprechpartner</h3>
          ${kontakte.map((k) => `<div class="rw-kontakt"><span class="rw-av" aria-hidden="true">${esc(initialen(k.name))}</span><div><b>${esc(k.name)}</b><span class="rw-sub">${esc([k.rolle, k.telefon, k.email].filter(Boolean).join(' · '))}</span></div></div>`).join('')
            || '<p class="rw-hilfe">Noch keine Ansprechpartner (Marktakte → Bearbeiten).</p>'}</section>
        <section class="rw-ksektion"><h3>Dauerauftrag</h3>
          ${d.rhythmus ? `<dl class="rw-kv"><dt>Rhythmus</dt><dd>${esc(S.d.rhythmen[d.rhythmus])}</dd><dt>Menge</dt><dd>${esc(mengenText(d.mengen))}</dd>
            <dt>Nächste Lieferung</dt><dd>${esc(A.naechsteDauer ? kwText(A.naechsteDauer) : '—')}</dd>${d.pauseBis ? `<dt>Pause bis</dt><dd>${esc(kwText(d.pauseBis))}</dd>` : ''}</dl>` : '<p class="rw-hilfe">Kein Dauerauftrag.</p>'}
          ${darfP ? `<a class="btn sm" href="#dauer/${id}" data-gehe="dauer/${id}" data-karte-zu>${d.rhythmus ? 'Dauerauftrag bearbeiten' : 'Dauerauftrag anlegen'}</a>` : ''}</section>
      </div>
      <div class="rw-krechts">
        <div class="rw-seg rw-kreiter" role="tablist" aria-label="Marktkarte">${reiter.map(([k, t]) => `<button type="button" role="tab" data-kreiter="${k}" aria-selected="${K.reiter === k}">${esc(t)}</button>`).join('')}</div>
        <div class="rw-kpanel" data-kpanel="notizen" role="tabpanel"${K.reiter === 'notizen' ? '' : ' hidden'}>
          ${darfP ? `<div class="rw-kneu">
            <textarea class="rw-eingabe" id="kt-ntext" rows="3" maxlength="2000" placeholder="Neue Notiz, Telefonat oder Absprache …" aria-label="Neue Notiz"></textarea>
            <div class="rw-kneu-fuss">
              <div class="rw-seg" role="group" aria-label="Art der Notiz">${arten.map(([k, v]) => `<button type="button" data-kart="${esc(k)}" aria-pressed="${K.art === k}">${esc(v)}</button>`).join('')}</div>
              <label class="rw-kwv">Wiedervorlage<input class="rw-eingabe" id="kt-nwv" type="date"></label>
              <button class="btn primary" type="button" id="kt-nsave"><svg class="i" aria-hidden="true"><use href="#i-plus"/></svg>Hinzufügen</button>
            </div>
            <p class="rw-meldung" id="kt-nmeldung" role="alert"></p></div>` : ''}
          <ol class="rw-verlaufsliste">${A.notizen.map(notizLi).join('') || '<li class="rw-leerzeile" style="display:block">Noch keine Notizen.</li>'}</ol>
        </div>
        <div class="rw-kpanel" data-kpanel="verlauf" role="tabpanel"${K.reiter === 'verlauf' ? '' : ' hidden'}>
          <div class="rw-zahlen">
            <div><span>Bestellungen ${esc(jahr)}</span><b>${obj(z[jahr]).lieferungen || 0}</b></div>
            <div><span>Bestellungen ${esc(String(+jahr - 1))}</span><b>${obj(z[String(+jahr - 1)]).lieferungen || 0}</b></div>
            <div><span>Stück ${esc(jahr)}</span><b>${zahl(summe(obj(z[jahr]).mengen))}</b></div>
            <div><span>Letzte Bestellung</span><b>${esc(z.letzte ? kwKurz(z.letzte) + '/' + z.letzte.slice(2, 4) : '—')}</b></div>
          </div>
          <div class="rw-heat">${heatHtml(A)}</div>
          <div class="rw-legende"><span><i class="rw-z b"></i>bestellt</span><span><i class="rw-z"></i>kein Bedarf</span><span><i class="rw-z n"></i>nicht erreicht</span><span><i class="rw-z p"></i>Pause</span><span><i class="rw-z o"></i>keine Angabe</span></div>
        </div>
        <div class="rw-kpanel" data-kpanel="wv" role="tabpanel"${K.reiter === 'wv' ? '' : ' hidden'}>
          ${offeneWv.map((n) => `<div class="rw-wv"><p><b>${esc(datum(n.wv))}</b> · ${esc(n.text)}</p>${darfP ? `<button class="btn sm" type="button" data-kwv="${esc(n.id)}">Erledigt</button>` : ''}</div>`).join('')
            || '<p class="rw-hilfe">Keine offenen Wiedervorlagen. Eine Wiedervorlage legen Sie mit einer Notiz an.</p>'}
        </div>
      </div>`;
    if (hinweisText !== null && hinweisText !== m.hinweis) kStatus('noch nicht gespeichert');
  }
  /* Hinweis speichern (nach kurzer Pause beim Tippen, beim Verlassen des Feldes und beim Schließen) */
  async function hinweisSpeichern() {
    clearTimeout(K.timer);
    const f = $('#kt-hinweis');
    if (!f || !K.akte || !K.akte.darfPflegen || K.speichert) return;
    const m = K.akte.markt, text = f.value;
    if (text.trim() === String(m.hinweis || '').trim()) { if ($('#kt-hstatus') && $('#kt-hstatus').textContent !== '✓ gespeichert') kStatus(''); return; }
    K.speichert = true; kStatus('wird gespeichert …');
    const r = await api('rewe_markt_save', { id: m.id, rev: m.rev, hinweis: text });
    K.speichert = false;
    if (r.status === 409) { kStatus('nicht gespeichert'); toast((r.data.error || 'Inzwischen geändert.') + ' Ihr Text steht noch im Feld.', true); if (K.akte.markt.id === m.id) ladeKarte(); return; }
    if (r.status !== 200 || !r.data.ok) { kStatus('nicht gespeichert'); toast(fehlerText(r, 'Hinweis nicht gespeichert'), true); return; }
    if (K.akte && K.akte.markt.id === m.id) K.akte.markt = r.data.markt;
    if (K.akte && K.akte.markt.id === m.id && $('#kt-hinweis')) kStatus($('#kt-hinweis').value === text ? '✓ gespeichert' : 'noch nicht gespeichert');
    const w = S.woche ? finde(m.id) : null;
    if (w) { w.hinweis = r.data.markt.hinweis; renderWoche(); }
    if ($('#kt-hinweis') && K.akte && K.akte.markt.id === m.id && $('#kt-hinweis').value !== text) K.timer = setTimeout(hinweisSpeichern, 900);   // weitergetippt
  }
  dk.addEventListener('input', (ev) => { if (ev.target.id === 'kt-hinweis') { kStatus('noch nicht gespeichert'); clearTimeout(K.timer); K.timer = setTimeout(hinweisSpeichern, 900); } });
  dk.addEventListener('focusout', (ev) => { if (ev.target.id === 'kt-hinweis') hinweisSpeichern(); });
  dk.addEventListener('close', () => { hinweisSpeichern(); });
  dk.addEventListener('keydown', (ev) => { if (ev.target.id === 'kt-ntext' && ev.key === 'Enter' && (ev.ctrlKey || ev.metaKey)) { ev.preventDefault(); $('#kt-nsave').click(); } });
  dk.addEventListener('click', async (ev) => {
    const b = ev.target.closest('button, a'); if (!b || b.disabled) return;
    if (b.dataset.karteZu !== undefined) { dk.close(); return; }
    if (b.dataset.kreiter) {
      K.reiter = b.dataset.kreiter;
      $$('[data-kreiter]', dk).forEach((x) => x.setAttribute('aria-selected', String(x === b)));
      $$('[data-kpanel]', dk).forEach((x) => { x.hidden = x.dataset.kpanel !== K.reiter; });
      return;
    }
    if (b.dataset.kart) { K.art = b.dataset.kart; $$('[data-kart]', dk).forEach((x) => x.setAttribute('aria-pressed', String(x === b))); return; }
    if (b.id === 'kt-nsave') {
      const text = $('#kt-ntext').value.trim();
      if (!text) { $('#kt-nmeldung').textContent = 'Bitte einen Text eingeben.'; $('#kt-ntext').focus(); return; }
      b.disabled = true;
      const r = await api('rewe_notiz_save', { markt: K.id, art: K.art, text, wiedervorlage: $('#kt-nwv').value });
      b.disabled = false;
      if (r.status !== 200 || !r.data.ok) { $('#kt-nmeldung').textContent = fehlerText(r, 'Speichern fehlgeschlagen'); return; }
      $('#kt-ntext').value = ''; $('#kt-nwv').value = '';
      if (window.STAFL_FENSTER) window.STAFL_FENSTER.gespeichert(dk);
      toast('Notiz gespeichert');
      await ladeKarte();
      if (S.tab === 'woche') ladeWoche(); else if (S.akteId) ladeAkte(S.akteId);
      return;
    }
    if (b.dataset.kwv) {
      b.disabled = true;
      const r = await api('rewe_notiz_save', { id: b.dataset.kwv, erledigt: true });
      if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Speichern fehlgeschlagen'), true); b.disabled = false; return; }
      toast('Wiedervorlage erledigt'); await ladeKarte();
      if (S.tab === 'woche') ladeWoche();
    }
  });

  /* ================= Daueraufträge (alle sichtbaren Märkte mit Dauerauftrag; bearbeiten nur eigene, GR-103 prüft der Server) ================= */
  const dauerAktiv = (m) => !!(m.dauer && m.dauer.rhythmus > 0);
  const dauerPause = (m) => dauerAktiv(m) && !!m.dauer.pauseBis && m.dauer.pauseBis >= S.d.abfrage;
  const kwAbstand = (a, b) => Math.round((montag(b) - montag(a)) / 604800000);
  function naechsteLieferungen(e, n = 4) {
    const out = [];
    for (let i = 0, k = S.d.abfrage < e.ab ? e.ab : S.d.abfrage; i < 120 && out.length < n; i++, k = kwPlus(k, 1)) {
      if (e.pauseBis && k <= e.pauseBis) continue;
      if (kwAbstand(e.ab, k) % e.rhythmus === 0) out.push(k);
    }
    return out;
  }
  function kwWahl(wert, leer = '') {
    const liste = []; for (let i = -4; i <= 26; i++) liste.push(kwPlus(S.d.abfrage, i));
    if (wert && !liste.includes(wert)) liste.unshift(wert);
    return (leer ? `<option value="">${esc(leer)}</option>` : '') + liste.map((k) => `<option value="${esc(k)}"${k === wert ? ' selected' : ''}>${esc(kwText(k))} · ${esc(zeitraum(k))}</option>`).join('');
  }
  function renderDauer() {
    if (!S.maerkte) return;
    const alle = S.maerkte.filter(dauerAktiv);
    const q = S.dSuche.trim().toLocaleLowerCase('de-DE');
    const z = alle.filter((m) => passt(m, q) && (!S.dRh || String(m.dauer.rhythmus) === S.dRh) && (!S.dLw || m.lieferweg === S.dLw)
      && (!S.dStatus || (S.dStatus === 'pause' ? dauerPause(m) : S.dStatus === 'faellig' ? m.dauerNaechste === S.d.abfrage : !dauerPause(m))));
    const pausiert = alle.filter(dauerPause).length, faellig = alle.filter((m) => m.dauerNaechste === S.d.abfrage).length;
    $('#rw-d-sub').textContent = `${alle.length - pausiert} aktiv · ${pausiert} pausiert · ${faellig} in ${kwKurz(S.d.abfrage)} fällig`;
    $('#rw-d-neu').hidden = !S.maerkte.some((m) => m.darfPflegen && !dauerAktiv(m));
    $('#rw-d-tabelle').innerHTML = `<thead><tr><th>Markt</th><th>Rhythmus</th><th>Menge je Lieferung</th><th>Nächste Lieferung</th><th>Status</th><th></th></tr></thead><tbody>
      ${z.map((m) => `<tr class="${m.darfPflegen ? 'rw-klick' : ''}${S.dEdit && S.dEdit.id === m.id ? ' rw-gewaehlt' : ''}" data-dauer="${esc(m.id)}"${m.darfPflegen ? ' tabindex="0"' : ''}>
        <td data-label="Markt" class="rw-voll"><span class="rw-name">${esc(m.ort)}</span><span class="rw-sub">${esc([m.strasse, m.kdNr ? 'Kd. ' + m.kdNr : '', m.lieferwegName].filter(Boolean).join(' · '))}</span></td>
        <td data-label="Rhythmus">${esc(S.d.rhythmen[m.dauer.rhythmus] || '')}</td><td data-label="Menge je Lieferung">${esc(mengenText(m.dauer.mengen))}</td>
        <td data-label="Nächste Lieferung">${m.dauerNaechste ? esc(kwText(m.dauerNaechste)) + (m.dauerNaechste === S.d.abfrage ? ' <span class="rw-chip gelb">fällig</span>' : '') : '—'}</td>
        <td data-label="Status">${dauerPause(m) ? `<span class="rw-chip blau">Pause bis ${esc(kwText(m.dauer.pauseBis))}</span>` : '<span class="rw-chip gruen">aktiv</span>'}</td>
        <td class="rw-voll">${m.darfPflegen ? `<button class="btn sm" type="button" data-dauer-edit="${esc(m.id)}">Bearbeiten</button>` : ''}</td></tr>`).join('')
        || `<tr><td colspan="6" class="rw-leerzeile">${alle.length ? 'Keine Daueraufträge für diesen Filter.' : 'Noch keine Daueraufträge.'}</td></tr>`}</tbody>`;
    if (S.dOffen) { const m = S.maerkte.find((x) => x.id === S.dOffen); S.dOffen = ''; if (m && m.darfPflegen) { dauerBearbeiten(m); return; } }
    renderDauerEdit();
  }
  function dauerBearbeiten(m) {
    const d = m && dauerAktiv(m) ? m.dauer : null;
    S.dEdit = { id: m ? m.id : '', neu: !d, rev: m ? m.rev : 0, rhythmus: d ? d.rhythmus : 1, mengen: d ? { ...obj(d.mengen) } : { [artikel()[0].id]: 1 },
      ab: d ? d.ab : S.d.abfrage, pauseBis: d ? d.pauseBis : '', beenden: false };
    renderDauer();
    $('#rw-d-edit').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
  function renderDauerEdit() {
    const el = $('#rw-d-edit'), e = S.dEdit;
    el.hidden = !e; el.parentElement.classList.toggle('mit-edit', !!e);
    if (!e) { el.innerHTML = ''; return; }
    const m = e.id ? S.maerkte.find((x) => x.id === e.id) : null;
    const frei = S.maerkte.filter((x) => x.darfPflegen && (!dauerAktiv(x) || x.id === e.id));
    const kopf = e.neu ? `<h2>Neuer Dauerauftrag</h2><label class="rw-schmal">Markt<select class="rw-eingabe" id="rw-d-markt"><option value="">Markt wählen …</option>
        ${frei.map((x) => `<option value="${esc(x.id)}"${x.id === e.id ? ' selected' : ''}>${esc(x.ort)}${x.kdNr ? ' · Kd. ' + esc(x.kdNr) : ''}</option>`).join('')}</select></label>`
      : `<h2>${esc(m ? m.ort : '')}</h2><p class="rw-sub">${esc(m ? [m.strasse, m.kdNr ? 'Kd. ' + m.kdNr : '', m.lieferwegName].filter(Boolean).join(' · ') : '')}</p>`;
    const naechste = naechsteLieferungen(e);
    el.innerHTML = `<div class="rw-dialogkopf"><div class="rw-dkopf">${kopf}</div><button class="rw-dialog-schliessen" type="button" data-d-zu aria-label="Schließen">×</button></div>
      <div class="rw-schmal"><span>Rhythmus</span><div class="rw-seg rw-dseg" role="group" aria-label="Rhythmus">${[1, 2, 3, 4].map((x) => `<button type="button" data-d-rh="${x}" aria-pressed="${e.rhythmus === x}">${esc(S.d.rhythmen[x])}</button>`).join('')}</div></div>
      <div class="rw-schmal"><span>Menge je Lieferung</span><div class="rw-mengen-eingabe">${artikel().map((ar) => `<div class="rw-menge"><span>${esc(ar.name)}</span><span class="rw-stepper">
        <button type="button" data-d-menge="${esc(ar.id)}" data-d="-1" aria-label="${esc(ar.name)} weniger">−</button><input class="rw-mzahl" data-d-mzahl="${esc(ar.id)}" inputmode="numeric" maxlength="3" value="${obj(e.mengen)[ar.id] || 0}" aria-label="${esc(ar.name)}: Menge">
        <button type="button" data-d-menge="${esc(ar.id)}" data-d="1" aria-label="${esc(ar.name)} mehr">+</button></span></div>`).join('')}</div></div>
      <div class="rw-formraster"><label>Erste Lieferung<select class="rw-eingabe" id="rw-d-ab">${kwWahl(e.ab)}</select></label>
        <label>Pause bis<select class="rw-eingabe" id="rw-d-pause">${kwWahl(e.pauseBis, 'keine Pause')}</select></label></div>
      <p class="rw-dvorschau">${naechste.length ? 'Nächste Lieferungen: ' + esc(naechste.map(kwKurz).join(' · ')) : 'Keine Lieferung geplant.'}</p>
      <p class="rw-meldung" id="rw-d-meldung" role="alert"></p>
      <div class="rw-knopfreihe">${!e.neu ? `<button class="btn ghost" type="button" data-d-ende>${e.beenden ? 'Wirklich beenden?' : 'Beenden'}</button>` : ''}
        <button class="btn" type="button" data-d-zu>Abbrechen</button><button class="btn primary" type="button" data-d-speichern>Speichern</button></div>`;
  }
  async function dauerSpeichern(ende) {
    const e = S.dEdit, meld = (t) => { $('#rw-d-meldung').textContent = t; };
    if (!e.id) { meld('Bitte einen Markt wählen.'); return false; }
    const mengen = Object.fromEntries(Object.entries(e.mengen).filter(([, n]) => n > 0));
    if (!ende && !Object.keys(mengen).length) { meld('Bitte mindestens eine Menge angeben.'); return false; }
    const r = await api('rewe_markt_save', { id: e.id, rev: e.rev, dauer: ende ? { rhythmus: 0 } : { rhythmus: e.rhythmus, mengen, ab: e.ab, pauseBis: e.pauseBis } });
    if (r.status === 409) {
      const t = (r.data.error || 'Der Markt wurde inzwischen geändert.') + ' Bitte prüfen und erneut speichern.';
      await ladeMaerkte(); const m = S.maerkte && S.maerkte.find((x) => x.id === e.id); if (m && S.dEdit) S.dEdit.rev = m.rev; meld(t); return false;
    }
    if (r.status !== 200 || !r.data.ok) { meld(fehlerText(r, 'Speichern fehlgeschlagen')); return false; }
    toast(`${r.data.markt.ort}: Dauerauftrag ${ende ? 'beendet' : 'gespeichert'}`);
    S.dEdit = null; await ladeMaerkte();
    return true;
  }
  $('#rw-d-suche').addEventListener('input', (ev) => { S.dSuche = ev.target.value; renderDauer(); });
  $('#rw-d-rh').addEventListener('change', (ev) => { S.dRh = ev.target.value; renderDauer(); });
  $('#rw-d-lw').addEventListener('change', (ev) => { S.dLw = ev.target.value; renderDauer(); });
  $('#rw-d-status').addEventListener('change', (ev) => { S.dStatus = ev.target.value; renderDauer(); });
  $('#rw-d-neu').addEventListener('click', () => dauerBearbeiten(null));
  $('#rw-d-tabelle').addEventListener('click', (ev) => {
    const tr = ev.target.closest('[data-dauer]'); if (!tr) return;
    const m = S.maerkte.find((x) => x.id === tr.dataset.dauer); if (m && m.darfPflegen) dauerBearbeiten(m);
  });
  $('#rw-d-tabelle').addEventListener('keydown', (ev) => { if (ev.key === 'Enter' && ev.target.dataset.dauer) ev.target.click(); });
  $('#rw-d-edit').addEventListener('click', async (ev) => {
    const b = ev.target.closest('button'); if (!b || b.disabled || !S.dEdit) return;
    const e = S.dEdit;
    if (b.dataset.dZu !== undefined) { S.dEdit = null; renderDauer(); return; }
    if (b.dataset.dRh) { e.rhythmus = +b.dataset.dRh; e.beenden = false; renderDauerEdit(); return; }
    if (b.dataset.dMenge) { e.mengen[b.dataset.dMenge] = Math.max(0, (e.mengen[b.dataset.dMenge] || 0) + Number(b.dataset.d)); renderDauerEdit(); return; }
    if (b.dataset.dEnde !== undefined) { if (!e.beenden) { e.beenden = true; renderDauerEdit(); return; } b.disabled = true; if (!(await dauerSpeichern(true))) b.disabled = false; return; }
    if (b.dataset.dSpeichern !== undefined) { b.disabled = true; if (!(await dauerSpeichern(false))) b.disabled = false; }
  });
  $('#rw-d-edit').addEventListener('change', (ev) => {
    const t = ev.target, e = S.dEdit; if (!e) return;
    if (t.id === 'rw-d-markt') { const m = S.maerkte.find((x) => x.id === t.value); e.id = t.value; e.rev = m ? m.rev : 0; renderDauer(); }
    else if (t.id === 'rw-d-ab') { e.ab = t.value; renderDauerEdit(); }
    else if (t.id === 'rw-d-pause') { e.pauseBis = t.value; renderDauerEdit(); }
    else if (t.dataset.dMzahl) { const n = parseInt(t.value.replace(/\D/g, ''), 10); e.mengen[t.dataset.dMzahl] = Number.isFinite(n) && n > 0 ? Math.min(n, 999) : 0; renderDauerEdit(); }
  });

  /* ================= Zuweisung und Team ================= */
  function renderZuweisung() {
    if (!S.maerkte) return;
    const anzahl = (id) => S.maerkte.filter((m) => m.zustaendig === id).length;
    const ohne = S.maerkte.filter((m) => !m.zustaendig).length;
    $('#rw-z-personen').innerHTML = S.d.personen.map((p) => `<div class="rw-kpi" data-person="${esc(p.id)}"><span>${esc(p.name)}</span><b>${anzahl(p.id)} <small>${anzahl(p.id) === 1 ? 'Markt' : 'Märkte'}</small></b>
        <label class="rw-check"><input type="checkbox" data-team="alle"${p.teamAlle || p.rechtAlle ? ' checked' : ''}${p.rechtAlle ? ' disabled title="über die Rolle"' : ''}> alle Listen</label>
        <label class="rw-check"><input type="checkbox" data-team="export"${p.teamExport || p.rechtExport ? ' checked' : ''}${p.rechtExport ? ' disabled title="über die Rolle"' : ''}> Wochenabschluss</label></div>`).join('')
      + `<div class="rw-kpi"><span>Ohne Zuständigkeit</span><b>${ohne} <small>${ohne === 1 ? 'Markt' : 'Märkte'}</small></b><button class="btn sm" type="button" id="rw-team-speichern">Team speichern</button></div>`;
    $('#rw-z-fwer').innerHTML = personOptionen('<option value="">alle Mitarbeiter</option><option value="-">ohne Zuständigkeit</option>'); $('#rw-z-fwer').value = S.zWer;
    $('#rw-z-flw').innerHTML = lwOptionen('alle Lieferwege', false); $('#rw-z-flw').value = S.zLw;
    $('#rw-z-fkauf').innerHTML = kaufOptionen('alle Märkte'); $('#rw-z-fkauf').value = S.zKauf;
    const q = S.zSuche.trim().toLocaleLowerCase('de-DE');
    const z = S.maerkte.filter((m) => passt(m, q) && (!S.zWer || (S.zWer === '-' ? !m.zustaendig : m.zustaendig === S.zWer)) && (!S.zLw || m.lieferweg === S.zLw) && (!S.zKauf || m.kauf === S.zKauf));
    const alleGewaehlt = z.length && z.every((m) => S.zAuswahl.has(m.id));
    $('#rw-z-tabelle').innerHTML = `<thead><tr><th><input type="checkbox" id="rw-z-alle" aria-label="alle gezeigten auswählen"${alleGewaehlt ? ' checked' : ''}></th><th>Markt</th><th>Kd.-Nr.</th><th>Lieferweg</th><th>Zuständig</th><th>Kaufbereitschaft</th><th>Zuletzt</th></tr></thead><tbody>
      ${z.map((m) => `<tr${S.zAuswahl.has(m.id) ? ' style="background:var(--rw-accent-soft,rgba(140,29,44,.08))"' : ''}><td><input type="checkbox" data-wahl="${esc(m.id)}" aria-label="${esc(m.ort)} auswählen"${S.zAuswahl.has(m.id) ? ' checked' : ''}></td>
        <td data-label="Markt"><span class="rw-name">${esc(m.ort)}</span><span class="rw-sub">${esc(m.strasse)}</span></td><td data-label="Kd.-Nr.">${esc(m.kdNr)}</td>
        <td data-label="Lieferweg">${esc(m.lieferwegName)}</td><td data-label="Zuständig">${esc(m.zustaendigName || '—')}</td><td data-label="Kaufbereitschaft">${kaufChip(m.kauf)}</td>
        <td data-label="Zuletzt">${esc(m.letzte ? kwText(m.letzte) : '—')}</td></tr>`).join('') || '<tr><td colspan="7" class="rw-leerzeile">Keine Märkte für diesen Filter.</td></tr>'}</tbody>`;
    const n = S.zAuswahl.size;
    $('#rw-z-bulk').hidden = !n;
    $('#rw-z-anzahl').textContent = `${n} ${n === 1 ? 'Markt' : 'Märkte'} ausgewählt`;
    if (!$('#rw-z-nutzer').options.length) {
      $('#rw-z-nutzer').innerHTML = personOptionen('<option value="=">unverändert</option><option value="">niemand</option>');
      $('#rw-z-lw').innerHTML = '<option value="">unverändert</option>' + lwOptionen('');
      $('#rw-z-ab').value = S.d.abfrage;
    }
  }
  $('#rw-t-zuweisung').addEventListener('change', (ev) => {
    const t = ev.target;
    if (t.dataset.wahl) { if (t.checked) S.zAuswahl.add(t.dataset.wahl); else S.zAuswahl.delete(t.dataset.wahl); renderZuweisung(); }
    else if (t.id === 'rw-z-alle') { $$('[data-wahl]').forEach((c) => { if (t.checked) S.zAuswahl.add(c.dataset.wahl); else S.zAuswahl.delete(c.dataset.wahl); }); renderZuweisung(); }
    else if (t.id === 'rw-z-fwer') { S.zWer = t.value; renderZuweisung(); }
    else if (t.id === 'rw-z-flw') { S.zLw = t.value; renderZuweisung(); }
    else if (t.id === 'rw-z-fkauf') { S.zKauf = t.value; renderZuweisung(); }
  });
  $('#rw-z-suche').addEventListener('input', (ev) => { S.zSuche = ev.target.value; renderZuweisung(); });
  $('#rw-z-los').addEventListener('click', async () => {
    const body = { maerkte: [...S.zAuswahl], ab: $('#rw-z-ab').value.trim() };
    if ($('#rw-z-nutzer').value !== '=') body.nutzer = $('#rw-z-nutzer').value;
    if ($('#rw-z-lw').value) body.lieferweg = $('#rw-z-lw').value;
    const r = await api('rewe_zuweisen', body);
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Zuweisen fehlgeschlagen'), true); return; }
    toast(`${r.data.geaendert} ${r.data.geaendert === 1 ? 'Markt' : 'Märkte'} ab ${kwText(body.ab)} geändert`);
    S.zAuswahl.clear(); ladeMaerkte();
  });
  $('#rw-z-personen').addEventListener('click', async (ev) => {
    if (!ev.target.closest('#rw-team-speichern')) return;
    const team = {};
    $$('[data-person]').forEach((k) => {
      const p = S.d.personen.find((x) => x.id === k.dataset.person);
      const alle = $('[data-team="alle"]', k), ex = $('[data-team="export"]', k);
      team[p.id] = { alle: alle.checked && !alle.disabled, export: ex.checked && !ex.disabled };
    });
    const r = await api('rewe_team_save', { team });
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Speichern fehlgeschlagen'), true); return; }
    toast('Team gespeichert'); await neuStart();
  });

  /* ================= Wochenabschluss ================= */
  async function ladeAbschluss() {
    $('#rw-a-titel').textContent = `Wochenabschluss · ${kwKurz(S.aKw)}`;
    const r = await api('rewe_abschluss', null, '&kw=' + encodeURIComponent(S.aKw));
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Der Wochenabschluss konnte nicht geladen werden'), true); return; }
    S.abschluss = r.data.abschluss; renderAbschluss();
  }
  function balken(liste, cls) {
    const max = Math.max(1, ...liste.map((x) => summe(x.mengen)));
    return liste.map((x) => `<div class="rw-balken ${cls}"><span>${esc(x.name)}</span><span class="spur"><i style="width:${Math.round(summe(x.mengen) / max * 100)}%"></i></span>
      <span class="wert"><b>${zahl(summe(x.mengen))}</b> Stück · ${x.maerkte} ${x.maerkte === 1 ? 'Markt' : 'Märkte'}</span></div>`).join('') || '<p class="rw-leerzeile">Keine Bestellungen.</p>';
  }
  function renderAbschluss() {
    const a = S.abschluss;
    $('#rw-a-sub').textContent = `Lieferwoche ${zeitraum(a.kw)} · Bestellungen aller Listen · Erfassung in WinAB als Einzelauftrag je Markt`;
    const offen = a.offen.length + a.dauerOffen.length;
    const hinweise = (a.dauerOffen.length ? 1 : 0) + (a.ohneNr.length ? 1 : 0) + (a.nachtraege ? 1 : 0) + (a.ohneStamm ? 1 : 0);
    const stueck = a.zeilen.reduce((s, r) => s + r.menge, 0);
    const eb = $('#rw-a-erfasst');
    eb.hidden = !a.exportiert; eb.querySelector('span').textContent = a.erfasst ? 'In WinAB erfasst ✓' : 'Als in WinAB erfasst markieren';
    eb.classList.toggle('primary', false);
    $('#rw-a-export').disabled = !a.zeilen.length;
    const schritte = [
      [offen ? 'warn' : 'ok', '1', 'Abfrage', offen ? `${offen} ohne Antwort` : 'alle beantwortet'],
      [hinweise ? 'warn' : 'ok', '2', 'Prüfen', hinweise ? `${hinweise} ${hinweise === 1 ? 'Hinweis' : 'Hinweise'}` : 'nichts offen'],
      [a.exportiert ? 'ok' : 'jetzt', '3', 'Excel erstellt', a.exportiert ? `${zeitpunkt(a.exportiert.t)}, ${a.exportiert.von}` : 'noch nicht'],
      [a.erfasst ? 'ok' : '', '4', 'In WinAB erfasst', a.erfasst ? `${zeitpunkt(a.erfasst.t)}, ${a.erfasst.von}` : 'Haken nach der Eingabe'],
    ];
    const artSum = S.d.artikel.filter((x) => obj(a.artikel)[x.id]).map((x) => `${zahl(obj(a.artikel)[x.id])} ${x.name}`).join(' · ');
    $('#rw-a-inhalt').innerHTML = `
      <ol class="rw-schritte rw-glas">${schritte.map(([c, n, t, s]) => `<li><span class="nr ${c}">${c === 'ok' ? '✓' : n}</span><div><b>${esc(t)}</b><small>${esc(s)}</small></div></li>`).join('')}</ol>
      <div class="rw-kpis">
        <div class="rw-kpi"><span>Einzelaufträge</span><b>${a.maerkte}</b><small>ein Auftrag je Markt</small></div>
        <div class="rw-kpi"><span>Stück gesamt</span><b>${zahl(stueck)}</b><small>${esc(artSum || '—')}</small></div>
        <div class="rw-kpi${offen ? ' warn' : ''}"><span>Ohne Antwort</span><b>${offen}</b><small>${a.dauerOffen.length} Daueraufträge nicht bestätigt</small></div>
        <div class="rw-kpi${a.nachtraege ? ' warn' : ''}"><span>Nachträge</span><b>${a.nachtraege}</b><small>nach dem Export geändert</small></div>
      </div>
      <div class="rw-raster">
        <section class="rw-panel rw-glas"><div class="rw-panelkopf"><h2>Je Lieferweg</h2></div>${balken(a.lieferwege, '')}</section>
        <section class="rw-panel rw-glas"><div class="rw-panelkopf"><h2>Je Mitarbeiter</h2></div>${balken(a.personen, 'person')}</section>
      </div>
      ${a.dauerOffen.length ? `<div class="rw-hinweisleiste"><span><b>Daueraufträge ohne Bestätigung:</b> ${esc(a.dauerOffen.map((m) => `${m.ort} (${m.zustaendig || 'niemand'})`).join(', '))} – sie stehen erst nach der Bestätigung im Export.</span></div>` : ''}
      ${a.offen.length ? `<div class="rw-hinweisleiste grau"><span><b>${maerkte(a.offen.length)} ohne Antwort:</b> ${esc(a.offen.slice(0, 12).map((m) => m.ort).join(', '))}${a.offen.length > 12 ? ' …' : ''}</span></div>` : ''}
      ${a.ohneNr.length ? `<div class="rw-hinweisleiste grau"><span><b>Ohne WinAB-Artikelnummer:</b> ${esc(a.ohneNr.join(', '))} – unter Einstellungen eintragen.</span>${darf('verwalten') ? '<a class="btn sm" href="#einstellungen" data-gehe="einstellungen">Einstellungen</a>' : ''}</div>` : ''}
      ${a.ohneStamm ? `<div class="rw-hinweisleiste grau"><span><b>${a.ohneStamm} ${a.ohneStamm === 1 ? 'Markt' : 'Märkte'} nicht im WinAB-Kundenstamm</b> – Name und Anschrift kommen aus der REWE-Liste.</span></div>` : ''}
      ${a.nachtraege ? `<div class="rw-hinweisleiste"><span><b>${a.nachtraege} ${a.nachtraege === 1 ? 'Nachtrag' : 'Nachträge'}</b> nach dem letzten Export – in der Vorschau markiert. Excel neu erstellen oder in WinAB nachtragen.</span></div>` : ''}
      <section class="rw-panel rw-glas"><div class="rw-panelkopf"><h2>Vorschau Excel für WinAB</h2><span class="rw-chip gruen">${a.maerkte} Aufträge · ${a.zeilen.length} Positionen</span></div>
        <div class="rw-tabelle-wrap"><table class="rw-tabelle rw-karten"><thead><tr><th class="rw-zahl">Auftrag</th><th>Lieferweg</th><th>Kd.-Nr.</th><th>Markt</th><th>Artikel</th><th class="rw-zahl">Menge</th><th>Erfasst von</th><th>Hinweis</th></tr></thead><tbody>
        ${a.zeilen.map((r) => `<tr><td data-label="Auftrag" class="rw-zahl">${r.auftrag}</td><td data-label="Lieferweg">${esc(r.lieferweg)}</td><td data-label="Kd.-Nr.">${esc(r.kdNr)}</td>
          <td data-label="Markt">${esc([r.ort, r.strasse].filter(Boolean).join(', '))}</td><td data-label="Artikel">${esc(r.artikel)}${r.nr ? ` <span class="rw-sub">${esc(r.nr)}</span>` : ''}</td>
          <td data-label="Menge" class="rw-zahl"><b>${r.menge}</b></td><td data-label="Erfasst von">${esc(r.zustaendig)}</td>
          <td data-label="Hinweis">${r.nachtrag ? '<span class="rw-chip akzent">Nachtrag</span> ' : ''}${r.ohneBerechnung ? '<span class="rw-chip gelb">ohne Berechnung</span> ' : ''}${esc(r.notiz)}</td></tr>`).join('')
          || '<tr><td colspan="8" class="rw-leerzeile">In dieser Woche gibt es keine Bestellungen.</td></tr>'}</tbody></table></div></section>`;
  }
  $('#rw-a-zurueck').addEventListener('click', () => { S.aKw = kwPlus(S.aKw, -1); zeigeTab('abschluss', S.aKw); });
  $('#rw-a-vor').addEventListener('click', () => { S.aKw = kwPlus(S.aKw, 1); zeigeTab('abschluss', S.aKw); });
  $('#rw-a-export').addEventListener('click', async () => {
    let res;
    $('#rw-a-export').disabled = true;
    try {
      res = await fetch(API + '?action=rewe_export', { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': S.csrf }, body: JSON.stringify({ kw: S.aKw }) });
    } catch { toast('Keine Verbindung zum Server.', true); $('#rw-a-export').disabled = false; return; }
    if (res.status === 401) { zeigeAnmeldung(); return; }
    if (!res.ok) { let d = {}; try { d = await res.json(); } catch { /* keine JSON-Antwort */ } toast(d.error || `Excel konnte nicht erstellt werden (${res.status}).`, true); $('#rw-a-export').disabled = false; return; }
    const a = document.createElement('a');
    a.href = URL.createObjectURL(await res.blob()); a.download = `REWE_WinAB_${S.aKw.replace('-', '_KW')}.xlsx`;
    document.body.append(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
    toast('Excel erstellt'); ladeAbschluss();
  });
  $('#rw-a-erfasst').addEventListener('click', async () => {
    const r = await api('rewe_erfasst', { kw: S.aKw, erfasst: !S.abschluss.erfasst });
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Speichern fehlgeschlagen'), true); return; }
    toast(r.data.erfasst ? `${kwText(S.aKw)} als in WinAB erfasst markiert` : 'Haken zurückgenommen'); ladeAbschluss();
  });

  /* ================= Einstellungen ================= */
  function renderEinstellungen() {
    $('#rw-e-leer').hidden = !S.d.leer;
    $('#rw-e-lw').innerHTML = `<thead><tr><th>Name</th><th>Art</th><th>Bestellschluss</th><th>aktiv</th></tr></thead><tbody>${S.d.lieferwege.map((l) => `<tr data-lw="${esc(l.id)}">
      <td data-label="Name"><input class="rw-eingabe" data-f="name" maxlength="60" value="${esc(l.name)}" aria-label="Name"></td>
      <td data-label="Art"><select class="rw-eingabe" data-f="art" aria-label="Art">${Object.entries(S.d.lwArten).map(([k, v]) => `<option value="${k}"${l.art === k ? ' selected' : ''}>${esc(v)}</option>`).join('')}</select></td>
      <td data-label="Bestellschluss"><input class="rw-eingabe" data-f="bestellschluss" maxlength="40" value="${esc(l.bestellschluss || '')}" aria-label="Bestellschluss"></td>
      <td data-label="aktiv"><input type="checkbox" data-f="aktiv"${l.aktiv ? ' checked' : ''} aria-label="aktiv"></td></tr>`).join('')}</tbody>`;
    $('#rw-e-art').innerHTML = `<thead><tr><th>Name</th><th>Einheit</th><th>WinAB-Art.-Nr.</th><th>aktiv</th></tr></thead><tbody>${S.d.artikel.map((a) => `<tr data-art="${esc(a.id)}">
      <td data-label="Name"><input class="rw-eingabe" data-f="name" maxlength="60" value="${esc(a.name)}" aria-label="Name"></td>
      <td data-label="Einheit"><input class="rw-eingabe" data-f="einheit" maxlength="15" value="${esc(a.einheit)}" aria-label="Einheit"></td>
      <td data-label="WinAB-Art.-Nr."><input class="rw-eingabe" data-f="nr" maxlength="20" value="${esc(a.nr)}" placeholder="fehlt" aria-label="WinAB-Artikelnummer"></td>
      <td data-label="aktiv"><input type="checkbox" data-f="aktiv"${a.aktiv ? ' checked' : ''} aria-label="aktiv"></td></tr>`).join('')}</tbody>`;
    $('#rw-e-meldung').textContent = '';
    renderPaket();
  }
  const zeilenWerte = (sel, idAttr) => $$(sel).map((tr) => Object.fromEntries([['id', tr.getAttribute(idAttr) || '']].concat($$('[data-f]', tr).map((i) => [i.dataset.f, i.type === 'checkbox' ? i.checked : i.value.trim()]))));
  $('#rw-e-lw-neu').addEventListener('click', () => {
    $('#rw-e-lw tbody').insertAdjacentHTML('beforeend', `<tr data-lw=""><td data-label="Name"><input class="rw-eingabe" data-f="name" maxlength="60" placeholder="z. B. Zentrallager Musterstadt" aria-label="Name"></td>
      <td data-label="Art"><select class="rw-eingabe" data-f="art" aria-label="Art">${Object.entries(S.d.lwArten).map(([k, v]) => `<option value="${k}">${esc(v)}</option>`).join('')}</select></td>
      <td data-label="Bestellschluss"><input class="rw-eingabe" data-f="bestellschluss" maxlength="40" value="Freitag früh der Vorwoche" aria-label="Bestellschluss"></td><td data-label="aktiv"><input type="checkbox" data-f="aktiv" checked aria-label="aktiv"></td></tr>`);
  });
  $('#rw-e-art-neu').addEventListener('click', () => {
    $('#rw-e-art tbody').insertAdjacentHTML('beforeend', `<tr data-art=""><td data-label="Name"><input class="rw-eingabe" data-f="name" maxlength="60" aria-label="Name"></td>
      <td data-label="Einheit"><input class="rw-eingabe" data-f="einheit" maxlength="15" value="Stück" aria-label="Einheit"></td><td data-label="WinAB-Art.-Nr."><input class="rw-eingabe" data-f="nr" maxlength="20" aria-label="WinAB-Artikelnummer"></td>
      <td data-label="aktiv"><input type="checkbox" data-f="aktiv" checked aria-label="aktiv"></td></tr>`);
  });
  $('#rw-e-speichern').addEventListener('click', async () => {
    const lw = zeilenWerte('#rw-e-lw tbody tr', 'data-lw').filter((x) => x.id || x.name);
    const art = zeilenWerte('#rw-e-art tbody tr', 'data-art').filter((x) => x.id || x.name);
    const r = await api('rewe_stamm_save', { rev: S.d.stammRev, lieferwege: lw, artikel: art });
    if (r.status !== 200 || !r.data.ok) { $('#rw-e-meldung').className = 'rw-meldung'; $('#rw-e-meldung').textContent = fehlerText(r, 'Speichern fehlgeschlagen'); return; }
    Object.assign(S.d, { stammRev: r.data.rev, lieferwege: r.data.lieferwege, artikel: r.data.artikel });
    renderEinstellungen(); toast('Lieferwege und Artikel gespeichert');
  });
  /* Datenpaket: Datei lesen, Listen den Mitarbeitern zuordnen, Vorschau, übernehmen */
  $('#rw-e-datei').addEventListener('change', async (ev) => {
    const f = ev.target.files[0]; if (!f) return;
    $('#rw-e-dateiname').textContent = f.name;
    try { S.paket = { daten: JSON.parse(await f.text()), zuordnung: {}, vorschau: null }; }
    catch { S.paket = null; toast('Die Datei ist kein gültiges Datenpaket (JSON).', true); return; }
    await paketVorschau();
  });
  async function paketVorschau() {
    const r = await api('rewe_import', { paket: S.paket.daten, zuordnung: S.paket.zuordnung, vorschau: true });
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Vorschau fehlgeschlagen'), true); return; }
    S.paket.vorschau = r.data;
    if (!S.paket.vorgeschlagen) {   // einmalig: Listen nach Vornamen den Mitarbeitern vorschlagen (z. B. „Marko“ → Marko …)
      S.paket.vorgeschlagen = true;
      let neu = 0;
      Object.keys(obj(r.data.listen)).forEach((l) => { const id = listenVorschlag(l); if (id && !(l in S.paket.zuordnung)) { S.paket.zuordnung[l] = id; neu++; } });
      S.paket.vorschlaege = neu;
      if (neu) return paketVorschau();
    }
    renderPaket();
  }
  function listenVorschlag(liste) {
    const woerter = liste.toLocaleLowerCase('de').split(/[^a-zäöüß0-9]+/).filter(Boolean);
    const treffer = (S.d.personen || []).filter((p) => p.name.toLocaleLowerCase('de').split(/\s+/).some((t) => t.length > 2 && woerter.includes(t)));
    return treffer.length === 1 ? treffer[0].id : '';
  }
  function renderPaket() {
    const p = S.paket, el = $('#rw-e-vorschau');
    if (!p || !p.vorschau) { el.innerHTML = ''; return; }
    const v = p.vorschau, z = v.zahlen || {};
    el.innerHTML = `<div class="rw-vorschau">${[['maerkte', 'Märkte'], ['antworten', 'Wochenantworten'], ['bestellungen', 'Bestellungen'], ['stueck', 'Stück'], ['dauerauftraege', 'Daueraufträge'], ['notizen', 'Notizen'], ['lieferwege', 'Lieferwege']]
      .map(([k, t]) => `<div><b>${zahl(z[k] || 0)}</b><span>${t}</span></div>`).join('')}</div>
      ${p.vorschlaege ? `<p class="rw-hinweis" id="rw-e-vorschlag">${p.vorschlaege === 1 ? 'Eine Liste wurde' : p.vorschlaege + ' Listen wurden'} nach dem Namen einem Mitarbeiter zugeordnet – bitte prüfen.</p>` : ''}
      <div class="rw-formraster" style="margin-bottom:10px">${Object.entries(obj(v.listen)).map(([l, n]) => `<label>Liste „${esc(l)}“ (${maerkte(n)}) gehört zu
        <select class="rw-eingabe" data-liste="${esc(l)}">${personOptionen('<option value="">niemand (später zuweisen)</option>')}</select></label>`).join('')}</div>
      ${v.fehler.length ? `<ul class="rw-fehlerliste">${v.fehler.map((f) => `<li>${esc(f)}</li>`).join('')}</ul>` : ''}
      <div class="rw-knopfreihe">${v.leer ? '' : '<label class="rw-check"><input type="checkbox" id="rw-e-ersetzen"> Vorhandene Daten ersetzen</label>'}
        <button class="btn primary" type="button" id="rw-e-uebernehmen"${v.fehler.length ? ' disabled' : ''}>Datenpaket übernehmen</button></div>`;
    $$('[data-liste]', el).forEach((s) => { s.value = p.zuordnung[s.dataset.liste] || ''; });
  }
  $('#rw-e-vorschau').addEventListener('change', (ev) => {
    const s = ev.target.closest('[data-liste]'); if (!s) return;
    S.paket.zuordnung[s.dataset.liste] = s.value; paketVorschau();
  });
  $('#rw-e-vorschau').addEventListener('click', async (ev) => {
    if (!ev.target.closest('#rw-e-uebernehmen')) return;
    const ersetzen = !!($('#rw-e-ersetzen') && $('#rw-e-ersetzen').checked);
    const r = await api('rewe_import', { paket: S.paket.daten, zuordnung: S.paket.zuordnung, ersetzen });
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Übernehmen fehlgeschlagen'), true); return; }
    toast(`Datenpaket übernommen – ${maerkte(r.data.zahlen.maerkte)}`);
    S.paket = null; $('#rw-e-dateiname').textContent = ''; $('#rw-e-datei').value = '';
    await neuStart(); renderEinstellungen();
  });

  /* ---------- Start ---------- */
  function setzeStart(d) {
    S.d = d;
    $('#rw-tabs [data-tab="zuweisung"]').hidden = !darf('verwalten');
    $('#rw-tabs [data-tab="einstellungen"]').hidden = !darf('verwalten');
    $('#rw-tabs [data-tab="abschluss"]').hidden = !darf('exportieren');
    const wer = $('#rw-w-wer');
    wer.hidden = !darf('alle');
    if (darf('alle')) { wer.innerHTML = '<option value="">Meine Liste</option><option value="*">Alle Listen</option>' + S.d.personen.filter((p) => p.id !== S.d.ich).map((p) => `<option value="${esc(p.id)}">Liste von ${esc(p.name)}</option>`).join(''); wer.value = S.wer; }
    $('#rw-m-lw').innerHTML = lwOptionen('alle Lieferwege', false); $('#rw-m-lw').value = S.mLw;
    $('#rw-m-kauf').innerHTML = kaufOptionen('alle Kaufbereitschaften'); $('#rw-m-kauf').value = S.mKauf;
    $('#rw-d-rh').innerHTML = '<option value="">alle Rhythmen</option>' + [1, 2, 3, 4].map((x) => `<option value="${x}">${esc(d.rhythmen[x])}</option>`).join(''); $('#rw-d-rh').value = S.dRh;
    $('#rw-d-lw').innerHTML = lwOptionen('alle Lieferwege', false); $('#rw-d-lw').value = S.dLw;
    if (!S.kw) S.kw = d.abfrage;
    if (!S.aKw) S.aKw = d.abschlussKw;
  }
  async function neuStart() {
    const r = await api('rewe_start');
    if (r.status === 200 && r.data.ok) setzeStart(r.data);
  }
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
    $('#rw-user').hidden = false; $('#rw-user-name').textContent = name; $('#rw-initialen').textContent = initialen(name);
    const r = await api('rewe_start');
    if (r.status === 404) { fehler('Die REWE-Abfrage ist für Sie noch nicht freigegeben.'); return; }
    if (r.status === 503) { fehler(r.data.error || 'Die REWE-Abfrage wird gerade gewartet.'); return; }
    if (r.status === 403) { fehler(r.data.error || 'Dafür fehlt Ihnen die Berechtigung.'); return; }
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { fehler(fehlerText(r, 'Die REWE-Abfrage konnte nicht geladen werden')); return; }
    setzeStart(r.data);
    $('#rw-login').hidden = true; $('#rw-app').hidden = false;
    const [tab, teil] = location.hash.slice(1).split('/');
    zeigeTab(tab || 'woche', teil || '');
  }
  themaKnopf();
  document.addEventListener('DOMContentLoaded', () => { laden().catch(() => fehler('Keine Verbindung zum Server.')); });
})();
