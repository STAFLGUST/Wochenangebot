/* ==========================================================================
   Wochenangebot – Eingabebereich
   Bearbeitet einen Entwurf auf dem Server (automatisch gespeichert).
   Erst „Veröffentlichen“ macht die Änderungen auf der öffentlichen Seite sichtbar.
   ========================================================================== */
(function () {
  'use strict';

  const C = window.OfferCore;
  const API = '../api/';

  /* ---------- Hilfen ---------- */
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ESC[c]);
  const icon = (n, cls = '') => `<svg class="i ${cls}" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const fmtNum = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 3 });
  const fmtInt = new Intl.NumberFormat('de-DE');
  const plural = (n, one, many) => `${fmtInt.format(n)} ${n === 1 ? one : many}`;
  const clone = (o) => JSON.parse(JSON.stringify(o));
  const uid = (p) => p + Date.now().toString(36) + Math.random().toString(36).slice(2, 7);
  const dmy = (iso) => { const [y, m, d] = iso.split('-'); return `${d}.${m}.${y}`; };
  const dm = (iso) => { const [, m, d] = iso.split('-'); return `${d}.${m}.`; };
  const dateTime = (iso) => (iso ? new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '');
  const timeOnly = (iso) => (iso ? new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) : '');
  const FOLD = { 'ä': 'a', 'ö': 'o', 'ü': 'u', 'ß': 's', 'é': 'e', 'è': 'e', 'ê': 'e', 'á': 'a', 'à': 'a', 'ó': 'o', 'ô': 'o', 'í': 'i', 'ú': 'u', 'ç': 'c', 'ñ': 'n', 'œ': 'o' };
  const fold = (s) => String(s ?? '').toLowerCase().replace(/[^\u0000-\u007f]/g, (c) => FOLD[c] ?? c);
  const store = {
    get(k, d) { try { const v = localStorage.getItem('wochenangebot.' + k); return v == null ? d : JSON.parse(v); } catch { return d; } },
    set(k, v) { try { localStorage.setItem('wochenangebot.' + k, JSON.stringify(v)); } catch { /* ignore */ } },
  };

  function priceToInput(p) {
    if (!p) return '';
    if (p.status === 'value') return fmtNum.format(p.value);
    if (p.status === 'request') return 'a. Anfr.';
    return '';
  }
  const priceShort = (p) => (p.status === 'value' ? fmtNum.format(p.value) + ' €/kg' : p.status === 'request' ? 'auf Anfrage' : 'ohne Preis');
  function inputToPrice(v, label) {
    const p = C.parsePrice(v);
    if (p.invalid) return null;
    const out = { status: p.status };
    if (p.status === 'value') out.value = p.value;
    if (p.status !== 'value' && p.raw) out.raw = p.raw;
    if (label) out.label = label;
    return out;
  }

  /* ---------- Zustand ---------- */
  let csrf = null;
  let company = '';
  let model = null;          // Entwurf (wird bearbeitet)
  let published = null;      // veröffentlichter Stand
  let revision = 0;
  let savedAt = null;
  let diff = null;
  let undoStack = [];
  const invalid = new Map(); // Artikel-ID → ungültiger Preistext
  const autoAttr = new Set();// neue Artikel: Attribute folgen der Bezeichnung
  let filterQ = '', onlyChanges = false;

  /* ---------- API ---------- */
  async function api(action, opts = {}) {
    const headers = { 'X-CSRF-Token': csrf || '' };
    if (opts.body) headers['Content-Type'] = 'application/json';
    let res;
    try {
      res = await fetch(API + '?action=' + action + (opts.query || ''), {
        method: opts.body ? 'POST' : 'GET', credentials: 'same-origin', headers, body: opts.body ? JSON.stringify(opts.body) : undefined, cache: 'no-store',
      });
    } catch {
      throw Object.assign(new Error('Keine Verbindung zum Server.'), { status: 0 });
    }
    let data = null;
    try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
    if (res.status === 401 && !['login', 'setup', 'change_password'].includes(action)) {
      showAuth('expired');
      throw Object.assign(new Error('Sitzung abgelaufen – bitte erneut anmelden.'), { status: 401 });
    }
    if (!res.ok || !data || !data.ok) {
      const msg = data && data.error ? data.error : res.status === 404 && !data ? 'API nicht gefunden – liegt der Ordner „api“ auf dem Server und ist PHP aktiv?' : `Serverfehler (${res.status}).`;
      throw Object.assign(new Error(msg), { status: res.status });
    }
    return data;
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

  /* ---------- Bestätigungsdialog ---------- */
  function confirmBox(title, text, okLabel = 'OK', danger = false) {
    return new Promise((resolve) => {
      const d = $('#dlg-confirm');
      $('#confirm-body').innerHTML = `<div class="dlg-head"><div><h2 id="cf-title">${esc(title)}</h2></div></div>
        <div class="dlg-body"><p style="margin:0;color:var(--text-2)">${text}</p></div>
        <div class="dlg-foot"><button type="button" class="btn" data-v="0">Abbrechen</button><button type="button" class="btn primary" data-v="1">${esc(okLabel)}</button></div>`;
      if (danger) $('#confirm-body .btn.primary').style.cssText = '';
      const done = (v) => { d.removeEventListener('close', onClose); if (d.open) d.close(); resolve(v); };
      const onClose = () => done(false);
      d.addEventListener('close', onClose);
      $('#confirm-body').onclick = (e) => { const b = e.target.closest('[data-v]'); if (b) done(b.dataset.v === '1'); };
      d.showModal();
      $('#confirm-body .btn.primary').focus();
    });
  }

  /* ======================= Anmeldung ======================= */
  let authMode = 'login';
  function showAuth(mode) {
    authMode = mode;
    $('#screen-auth').hidden = false;
    if (mode !== 'expired') $('#screen-editor').hidden = true;
    const setup = mode === 'setup';
    $('#auth-intro').textContent = setup
      ? 'Ersteinrichtung: Legen Sie das Passwort für den Eingabebereich fest (mindestens 10 Zeichen). Bitte sicher aufbewahren.'
      : mode === 'expired' ? 'Ihre Sitzung ist abgelaufen. Bitte erneut anmelden – Ihre Änderungen bleiben erhalten.'
        : 'Bitte melden Sie sich an, um das Wochenangebot zu bearbeiten.';
    $('#pw2-wrap').hidden = !setup;
    $('#pw1').autocomplete = setup ? 'new-password' : 'current-password';
    $('#auth-submit').textContent = setup ? 'Passwort festlegen' : 'Anmelden';
    $('#auth-err').textContent = '';
    $('#pw1').value = ''; $('#pw2').value = '';
    if (mode === 'expired') { $('#screen-auth').classList.add('overlay'); }
    setTimeout(() => $('#pw1').focus(), 30);
  }
  $('#auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const pw = $('#pw1').value;
    const err = $('#auth-err');
    err.textContent = '';
    if (authMode === 'setup') {
      if (pw.length < 10) { err.textContent = 'Das Passwort muss mindestens 10 Zeichen lang sein.'; return; }
      if (pw !== $('#pw2').value) { err.textContent = 'Die beiden Passwörter stimmen nicht überein.'; return; }
    }
    $('#auth-submit').disabled = true;
    try {
      const r = await api(authMode === 'setup' ? 'setup' : 'login', { body: { password: pw } });
      csrf = r.csrf;
      $('#screen-auth').hidden = true;
      $('#screen-auth').classList.remove('overlay');
      if (authMode === 'expired' && model) { $('#screen-editor').hidden = false; saveNow(); }
      else await openEditor();
    } catch (ex) {
      err.textContent = ex.message;
    } finally {
      $('#auth-submit').disabled = false;
    }
  });

  /* ======================= Editor laden ======================= */
  function emptyModel() {
    const d = new Date();
    const t = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    const day = t.getUTCDay() || 7;
    t.setUTCDate(t.getUTCDate() + 4 - day);
    const y = t.getUTCFullYear();
    const week = Math.ceil(((t - Date.UTC(y, 0, 1)) / 86400000 + 1) / 7);
    return { meta: { week, year: y, notice: 'Freibleibendes Angebot' }, sections: [], groups: [], items: [] };
  }
  function strip(m) {
    const c = clone(m);
    delete c.savedAt; delete c.publishedAt; delete c.rev; delete c.issues;
    c.items.forEach((i) => { i.altPrices = i.altPrices || []; });
    return c;
  }
  async function openEditor() {
    const d = await api('draft');
    published = d.published ? strip(d.published) : null;
    model = d.draft ? strip(d.draft) : published ? clone(published) : emptyModel();
    revision = d.revision || 0;
    savedAt = d.draftSavedAt;
    $('#screen-editor').hidden = false;
    $('#screen-auth').hidden = true;
    undoStack = [];
    invalid.clear();
    renderAll();
    setSaveState(d.draft ? 'saved' : 'clean');
  }

  /* ======================= Speichern ======================= */
  let saveTimer = null, saving = false, queued = false, saveError = null;
  function setSaveState(st, msg) {
    const el = $('#save-state');
    el.className = 'save-state ' + st;
    const hasChanges = diff && (diff.added.length + diff.removed.length + diff.priceChanged.length + diff.changed.length + (metaChanged() ? 1 : 0)) > 0;
    let text;
    if (st === 'pending' || st === 'saving') text = 'Speichert …';
    else if (st === 'error') text = `Nicht gespeichert: ${esc(msg || saveError || '')} <button type="button" class="link-btn" data-act="retry-save">Erneut versuchen</button>`;
    else if (!hasChanges && !published) text = 'Noch nichts veröffentlicht';
    else if (!hasChanges) text = 'Keine Änderungen gegenüber der veröffentlichten Fassung';
    else text = `Entwurf gespeichert${savedAt ? ' · ' + timeOnly(savedAt) + ' Uhr' : ''} · <strong>noch nicht veröffentlicht</strong>`;
    el.innerHTML = `<span class="dot"></span><span>${text}</span>`;
  }
  function changed(opts = {}) {
    diff = C.diffOffers(published, model);
    if (opts.render) renderGroups(); else if (opts.row) updateRow(opts.row);
    renderChanges();
    renderMetaInfo();
    updatePublishBtn();
    setSaveState('pending');
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, 700);
  }
  async function saveNow() {
    clearTimeout(saveTimer);
    if (saving) { queued = true; return; }
    saving = true;
    setSaveState('saving');
    try {
      const r = await api('save_draft', { body: { model, revision } });
      revision = r.revision;
      savedAt = r.savedAt;
      saveError = null;
      setSaveState('saved');
    } catch (e) {
      saveError = e.message;
      if (e.status !== 401) setSaveState('error', e.message);
    } finally {
      saving = false;
      if (queued) { queued = false; saveNow(); }
    }
  }
  const unsaved = () => saving || saveTimer && $('#save-state').classList.contains('pending') || !!saveError;
  window.addEventListener('beforeunload', (e) => { if (model && unsaved()) { e.preventDefault(); e.returnValue = ''; } });

  /* ---------- Rückgängig ---------- */
  function pushUndo() {
    undoStack.push(JSON.stringify(model));
    if (undoStack.length > 50) undoStack.shift();
    $('#btn-undo').disabled = false;
  }
  function undo() {
    if (!undoStack.length) return;
    model = JSON.parse(undoStack.pop());
    invalid.clear();
    $('#btn-undo').disabled = !undoStack.length;
    renderMeta();
    changed({ render: true });
    toast('Letzte Änderung rückgängig gemacht.');
  }

  /* ======================= Darstellung ======================= */
  const gById = (id) => model.groups.find((g) => g.id === id);
  const iById = (id) => model.items.find((i) => i.id === id);
  function metaChanged() {
    if (!published) return false;
    const a = published.meta, b = model.meta;
    return a.week !== b.week || a.year !== b.year || (a.notice || '') !== (b.notice || '');
  }

  function renderAll() {
    $$('[data-company]').forEach((el) => { el.textContent = company; el.hidden = !company; });
    renderMeta();
    diff = C.diffOffers(published, model);
    renderGroups();
    renderChanges();
    updatePublishBtn();
  }

  function renderMeta() {
    $('#m-week').value = model.meta.week ?? '';
    $('#m-year').value = model.meta.year ?? '';
    $('#m-notice').value = model.meta.notice || '';
    renderMetaInfo();
  }
  function renderMetaInfo() {
    const m = model.meta;
    let txt = '';
    if (m.week && m.year && m.week >= 1 && m.week <= 53) {
      const r = C.isoWeekRange(m.week, m.year);
      txt = `Angebotswoche: <strong>Mo ${dm(r.start)} – So ${dmy(r.end)}</strong>`;
    } else txt = '<span style="color:var(--accent)">Bitte Kalenderwoche und Jahr angeben.</span>';
    if (published && published.meta.week) txt += ` · Veröffentlicht ist KW ${esc(published.meta.week)}/${esc(published.meta.year)}`;
    $('#m-info').innerHTML = txt;
    // Datalists
    const origins = new Set(['Deutschland / EU', 'Argentinien', 'Uruguay', 'Paraguay', 'Brasilien', 'Australien', 'Neuseeland', 'Irland', 'Dänemark', 'Südamerika']);
    model.items.forEach((i) => { if (i.origin) origins.add(i.origin); });
    $('#dl-origins').innerHTML = [...origins].sort((a, b) => a.localeCompare(b, 'de')).map((o) => `<option value="${esc(o)}">`).join('');
    const secs = [...new Set(model.groups.map((g) => g.section).filter(Boolean))];
    $('#dl-sections').innerHTML = secs.map((s) => `<option value="${esc(s)}">`).join('');
  }

  function renderChanges() {
    const el = $('#changes');
    if (!published) {
      el.innerHTML = `<div class="chg has">${icon('info')}<span>Noch keine Veröffentlichung vorhanden – nach dem Veröffentlichen erscheint das Angebot auf der öffentlichen Seite.</span></div>`;
      return;
    }
    const n = diff.added.length + diff.removed.length + diff.priceChanged.length + diff.changed.length + (metaChanged() ? 1 : 0);
    if (!n) { el.innerHTML = ''; return; }
    const parts = [];
    if (metaChanged()) parts.push(`<span class="chg-pill k-edit"><i></i>Kopfdaten geändert</span>`);
    if (diff.priceChanged.length) parts.push(`<span class="chg-pill k-price"><i></i><b>${diff.priceChanged.length}</b> Preis${diff.priceChanged.length === 1 ? '' : 'e'} geändert</span>`);
    if (diff.added.length) parts.push(`<span class="chg-pill k-new"><i></i><b>${diff.added.length}</b> neu</span>`);
    if (diff.changed.length) parts.push(`<span class="chg-pill k-edit"><i></i><b>${diff.changed.length}</b> bearbeitet</span>`);
    if (diff.removed.length) parts.push(`<span class="chg-pill k-del"><i></i><b>${diff.removed.length}</b> entfernt</span>`);
    el.innerHTML = `<div class="chg has"><strong>Unveröffentlichte Änderungen:</strong>${parts.join('')}</div>`;
  }
  function updatePublishBtn() {
    const b = $('#btn-publish');
    const n = !published ? model.items.length : diff.added.length + diff.removed.length + diff.priceChanged.length + diff.changed.length + (metaChanged() ? 1 : 0);
    b.innerHTML = `${icon('send')}<span class="lbl">Veröffentlichen</span>${n ? `<span class="badge-n">${published ? n : '!'}</span>` : ''}`;
  }

  const CAT_OPTS = (sel) => C.CATEGORY_ORDER.map((c) => `<option${c === sel ? ' selected' : ''}>${esc(c)}</option>`).join('');
  const COND_OPTS = (sel) => C.CONDITIONS.map((c) => `<option value="${c}"${c === sel ? ' selected' : ''}>${esc(C.CONDITION_LABELS[c])}</option>`).join('');

  function rowState(it) {
    if (diff.added.includes(it.id)) return 'is-new';
    if (diff.priceChanged.includes(it.id)) return 'is-price';
    if (diff.changed.includes(it.id)) return 'is-edit';
    return '';
  }
  function matchesFilter(it) {
    if (onlyChanges && !rowState(it)) return false;
    if (!filterQ) return true;
    const hay = fold([it.code, it.name, it.origin, it.category, C.CONDITION_LABELS[it.condition]].join(' '));
    return fold(filterQ).split(/\s+/).filter(Boolean).every((t) => hay.includes(t));
  }
  function rowHTML(it) {
    const st = rowState(it);
    const bad = invalid.has(it.id);
    const before = diff.before[it.id];
    const was = st === 'is-price' && before ? `<span class="was" title="Veröffentlichter Preis">bisher <s>${esc(priceShort(before.price))}</s></span>` : '';
    const label = it.price.label ? `<span class="was">${esc(it.price.label)}</span>` : '';
    const alts = (it.altPrices || []).length ? `<div class="alts">${it.altPrices.map((p) => `<button type="button" data-act="item" title="Zusatzpreis bearbeiten">${esc(p.label)}: ${esc(p.status === 'value' ? fmtNum.format(p.value) : priceShort(p))}</button>`).join('')}</div>` : '';
    return `<tr data-id="${esc(it.id)}" class="${st}${matchesFilter(it) ? '' : ' hidden-row'}">
      <td class="e-code"><input class="in mono" data-f="code" value="${esc(it.code || '')}" placeholder="—" aria-label="Artikelnummer" maxlength="20"></td>
      <td class="e-name"><input class="in" data-f="name" value="${esc(it.name)}" aria-label="Bezeichnung" maxlength="200">${st === 'is-new' ? '<span class="newtag">neu</span>' : ''}</td>
      <td class="e-cat"><select class="in" data-f="category" aria-label="Fleischart">${CAT_OPTS(it.category)}</select></td>
      <td class="e-origin"><input class="in" data-f="origin" value="${esc(it.origin || '')}" list="dl-origins" placeholder="nicht angegeben" aria-label="Herkunft" maxlength="60"></td>
      <td class="e-cond"><select class="in" data-f="condition" aria-label="Zustand">${COND_OPTS(it.condition)}</select></td>
      <td class="e-price">${label}<input class="in num${bad ? ' invalid' : ''}" data-f="price" value="${esc(bad ? invalid.get(it.id) : priceToInput(it.price))}" placeholder="ohne Preis" aria-label="Preis in Euro je kg" inputmode="decimal">${was}${alts}</td>
      <td class="e-act"><button type="button" class="ibtn" data-act="item" aria-label="Details zu ${esc(it.name)}" title="Details, Zusatzpreise, verschieben, löschen">${icon('dots')}</button></td>
    </tr>`;
  }
  function updateRow(id) {
    const find = () => $(`tr[data-id="${CSS.escape(id)}"]`);
    let tr = find();
    const it = iById(id);
    if (!tr || !it) return;
    const ae = document.activeElement;
    const focusF = ae && tr.contains(ae) ? ae.dataset.f : null;
    if (focusF) { ae.blur(); tr = find(); if (!tr) return; } // blur kann ein weiteres „change“ auslösen
    const tmp = document.createElement('tbody');
    tmp.innerHTML = rowHTML(it);
    const nr = tmp.firstElementChild;
    tr.replaceWith(nr);
    if (focusF) nr.querySelector(`[data-f="${focusF}"]`)?.focus();
  }

  function renderGroups() {
    const host = $('#groups');
    if (!model.groups.length) {
      host.innerHTML = `<div class="ed-empty"><h3>Noch keine Artikel</h3><p>Importieren Sie die Excel-Angebotsliste oder legen Sie eine Angebotsgruppe an und tragen Sie Artikel ein.</p>
        <div class="row-actions"><button type="button" class="btn primary" data-act="import">${icon('upload')}Excel importieren</button><button type="button" class="btn" data-act="add-group">${icon('plus')}Gruppe anlegen</button></div></div>`;
      return;
    }
    let out = '', sec = null;
    model.groups.forEach((g, gi) => {
      const items = model.items.filter((i) => i.groupId === g.id);
      const visible = items.filter(matchesFilter);
      const hide = (filterQ || onlyChanges) && !visible.length;
      if ((g.section || '') !== sec) { sec = g.section || ''; if (sec && !hide) out += `<h2 class="gsec">${esc(sec)}</h2>`; }
      out += `<section class="gcard" data-gid="${esc(g.id)}"${hide ? ' hidden' : ''}>
        <div class="ghead">
          <input class="in g-name" data-gf="name" value="${esc(g.name)}" aria-label="Name der Angebotsgruppe" maxlength="200">
          <input class="in g-sec" data-gf="section" value="${esc(g.section || '')}" list="dl-sections" placeholder="Bereich (optional)" aria-label="Bereich" maxlength="200">
          <span class="g-count">${plural(items.length, 'Artikel', 'Artikel')}</span>
          <span class="g-actions">
            <button type="button" class="ibtn" data-act="g-up" aria-label="Gruppe nach oben"${gi === 0 ? ' disabled' : ''}>${icon('up')}</button>
            <button type="button" class="ibtn" data-act="g-down" aria-label="Gruppe nach unten"${gi === model.groups.length - 1 ? ' disabled' : ''}>${icon('down')}</button>
            <button type="button" class="ibtn danger" data-act="g-del" aria-label="Gruppe löschen">${icon('trash')}</button>
          </span>
        </div>
        <table class="etab"><thead><tr>
          <th class="e-code">Art.-Nr.</th><th class="e-name">Bezeichnung</th><th class="e-cat">Fleischart</th><th class="e-origin">Herkunft</th><th class="e-cond">Zustand</th><th class="e-price" style="text-align:right">Preis €/kg</th><th class="e-act"><span class="sr-only">Aktionen</span></th>
        </tr></thead><tbody>${items.map(rowHTML).join('')}</tbody></table>
        <div class="gfoot"><button type="button" class="btn ghost" data-act="add-item">${icon('plus')}Artikel hinzufügen</button></div>
      </section>`;
    });
    host.innerHTML = out;
  }

  /* ======================= Bearbeiten ======================= */
  function applyField(it, f, el) {
    const v = el.value;
    if (f === 'code') { const c = v.trim(); it.code = c || null; el.value = c; }
    else if (f === 'name') {
      const n = C.clean(v);
      if (!n) { el.value = it.name; toast('Die Bezeichnung darf nicht leer sein.'); return false; }
      it.name = n;
      delete it.nameRaw;
      if (autoAttr.has(it.id)) { const g = gById(it.groupId); Object.assign(it, C.suggestAttributes(n, g ? g.name : '', g ? g.section : '')); }
    } else if (f === 'category') it.category = v;
    else if (f === 'condition') it.condition = v;
    else if (f === 'origin') it.origin = C.clean(v) || null;
    else if (f === 'price') {
      const p = inputToPrice(v, it.price.label);
      if (!p) { invalid.set(it.id, v); el.classList.add('invalid'); toast('Preis nicht lesbar – bitte z. B. 23,30 oder „a. Anfr.“ eingeben.'); return 'invalid'; }
      invalid.delete(it.id);
      it.price = p;
    }
    if (f === 'category' || f === 'origin' || f === 'condition') autoAttr.delete(it.id);
    return true;
  }

  $('#groups').addEventListener('change', (e) => {
    const el = e.target;
    if (!el.isConnected) return;
    const tr = el.closest('tr[data-id]');
    if (tr && el.dataset.f) {
      const it = iById(tr.dataset.id);
      if (!it) return;
      const snapshot = JSON.stringify(model);
      const r = applyField(it, el.dataset.f, el);
      if (r === false) return;
      if (JSON.stringify(model) !== snapshot) { undoStack.push(snapshot); $('#btn-undo').disabled = false; }
      if (r === 'invalid') { updatePublishBtn(); return; }
      changed({ row: it.id });
      return;
    }
    const gcard = el.closest('[data-gid]');
    if (gcard && el.dataset.gf) {
      const g = gById(gcard.dataset.gid);
      const v = C.clean(el.value);
      if (el.dataset.gf === 'name' && !v) { el.value = g.name; toast('Die Gruppe braucht einen Namen.'); return; }
      pushUndo();
      g[el.dataset.gf] = v;
      changed({ render: el.dataset.gf === 'section' });
      renderMetaInfo();
    }
  });

  /* Enter springt in die gleiche Spalte der nächsten Zeile – schnelle Preiseingabe */
  $('#groups').addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || !e.target.matches('input.in[data-f]')) return;
    e.preventDefault();
    const f = e.target.dataset.f;
    const all = $$(`tr[data-id]:not(.hidden-row) input[data-f="${f}"]`).filter((x) => x.offsetParent);
    const i = all.indexOf(e.target);
    e.target.dispatchEvent(new Event('change', { bubbles: true }));
    const next = all[i + (e.shiftKey ? -1 : 1)];
    setTimeout(() => { const n = next && $(`tr[data-id="${CSS.escape(next.closest('tr').dataset.id)}"] input[data-f="${f}"]`); if (n) { n.focus(); n.select(); } }, 0);
  });

  function newItem(groupId, after) {
    const g = gById(groupId);
    const it = { id: uid('n'), code: null, name: 'Neuer Artikel', ...C.suggestAttributes('', g ? g.name : '', g ? g.section : ''), groupId, price: { status: 'none' }, altPrices: [] };
    if (after) {
      const idx = model.items.indexOf(after);
      model.items.splice(idx + 1, 0, it);
    } else {
      let idx = -1;
      model.items.forEach((x, i) => { if (x.groupId === groupId) idx = i; });
      if (idx < 0) {
        const gi = model.groups.findIndex((x) => x.id === groupId);
        idx = model.items.findIndex((x) => model.groups.findIndex((y) => y.id === x.groupId) > gi) - 1;
        if (idx < -1) idx = model.items.length - 1;
      }
      model.items.splice(idx + 1, 0, it);
    }
    autoAttr.add(it.id);
    return it;
  }

  $('#groups').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-act]');
    if (!b) return;
    const act = b.dataset.act;
    const gcard = b.closest('[data-gid]');
    const g = gcard && gById(gcard.dataset.gid);
    const tr = b.closest('tr[data-id]');
    if (act === 'item' && tr) { openItem(tr.dataset.id); return; }
    if (act === 'import') { pickFile(); return; }
    if (act === 'add-group') { addGroup(); return; }
    if (!g) return;
    const gi = model.groups.indexOf(g);
    if (act === 'add-item') {
      pushUndo();
      const it = newItem(g.id);
      changed({ render: true });
      const inp = $(`tr[data-id="${CSS.escape(it.id)}"] input[data-f="name"]`);
      if (inp) { inp.scrollIntoView({ block: 'center', behavior: 'smooth' }); inp.focus(); inp.select(); }
    } else if (act === 'g-up' || act === 'g-down') {
      const j = act === 'g-up' ? gi - 1 : gi + 1;
      if (j < 0 || j >= model.groups.length) return;
      pushUndo();
      [model.groups[gi], model.groups[j]] = [model.groups[j], model.groups[gi]];
      changed({ render: true });
      $(`[data-gid="${CSS.escape(g.id)}"] [data-act="${act}"]`)?.focus();
    } else if (act === 'g-del') {
      const n = model.items.filter((i) => i.groupId === g.id).length;
      if (n && !(await confirmBox('Gruppe löschen?', `„${esc(g.name)}“ enthält ${plural(n, 'Artikel', 'Artikel')}. Gruppe und Artikel werden aus dem Entwurf entfernt.`, 'Löschen', true))) return;
      pushUndo();
      model.groups.splice(gi, 1);
      model.items = model.items.filter((i) => i.groupId !== g.id);
      changed({ render: true });
      toast(`Gruppe „${g.name}“ gelöscht – mit „Rückgängig“ wiederherstellbar.`);
    }
  });

  function addGroup() {
    pushUndo();
    const last = model.groups[model.groups.length - 1];
    const g = { id: uid('g'), name: 'Neue Gruppe', section: last ? last.section : '' };
    model.groups.push(g);
    newItem(g.id);
    changed({ render: true });
    const inp = $(`[data-gid="${CSS.escape(g.id)}"] [data-gf="name"]`);
    if (inp) { inp.scrollIntoView({ block: 'center', behavior: 'smooth' }); inp.focus(); inp.select(); }
  }

  /* Kopfdaten */
  for (const [id, f] of [['#m-week', 'week'], ['#m-year', 'year'], ['#m-notice', 'notice']]) {
    $(id).addEventListener('change', (e) => {
      pushUndo();
      if (f === 'notice') model.meta.notice = C.clean(e.target.value);
      else { const n = parseInt(e.target.value, 10); model.meta[f] = Number.isInteger(n) ? n : null; }
      changed();
    });
  }

  /* Suche / Filter im Editor */
  let qTimer;
  $('#ed-q').addEventListener('input', (e) => { clearTimeout(qTimer); qTimer = setTimeout(() => { filterQ = e.target.value.trim(); renderGroups(); }, 120); });
  $('#only-changes').addEventListener('change', (e) => { onlyChanges = e.target.checked; renderGroups(); });

  /* ======================= Artikel-Dialog ======================= */
  const dlgItem = $('#dlg-item');
  let itemId = null;
  function openItem(id) {
    const it = iById(id);
    if (!it) return;
    itemId = id;
    const groups = model.groups.map((g) => `<option value="${esc(g.id)}"${g.id === it.groupId ? ' selected' : ''}>${esc(g.name)}</option>`).join('');
    const sameGroup = model.items.filter((i) => i.groupId === it.groupId);
    const pos = sameGroup.indexOf(it);
    $('#item-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="it-title">Artikel bearbeiten</h2><p>${it.cell ? `Aus Excel-Zelle ${esc(it.cell)} · ` : ''}Änderungen werden sofort in den Entwurf übernommen.</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body form-grid two">
        <label class="fld"><span>Artikelnummer</span><input name="code" value="${esc(it.code || '')}" maxlength="20" autocomplete="off"></label>
        <label class="fld"><span>Angebotsgruppe</span><select name="groupId">${groups}</select></label>
        <label class="fld span2"><span>Bezeichnung</span><input name="name" value="${esc(it.name)}" maxlength="200" required autocomplete="off"></label>
        <label class="fld"><span>Fleischart</span><select name="category">${CAT_OPTS(it.category)}</select></label>
        <label class="fld"><span>Zustand</span><select name="condition">${COND_OPTS(it.condition)}</select></label>
        <label class="fld"><span>Herkunft</span><input name="origin" value="${esc(it.origin || '')}" list="dl-origins" placeholder="nicht angegeben" maxlength="60"></label>
        <label class="fld"><span>Preis €/kg</span><input name="price" value="${esc(invalid.get(it.id) ?? priceToInput(it.price))}" placeholder="ohne Preis" inputmode="decimal"></label>
        <label class="fld"><span>Bezeichnung des Preises (optional)</span><input name="priceLabel" value="${esc(it.price.label || '')}" placeholder="z. B. Schiffsware" maxlength="40"></label>
        <div class="fld span2"><span>Zusatzpreise (z. B. Flugware)</span>
          <div class="altlist" id="altlist">${(it.altPrices || []).map((p, k) => altRow(p, k)).join('')}</div>
          <div><button type="button" class="btn sm ghost" data-ia="alt-add">${icon('plus', 'sm')}Zusatzpreis</button></div>
        </div>
        <p class="form-err span2" id="item-err" role="alert"></p>
      </div>
      <div class="dlg-foot">
        <span class="left">
          <button type="button" class="btn sm ghost" data-ia="up"${pos <= 0 ? ' disabled' : ''}>${icon('up', 'sm')}Nach oben</button>
          <button type="button" class="btn sm ghost" data-ia="down"${pos >= sameGroup.length - 1 ? ' disabled' : ''}>${icon('down', 'sm')}Nach unten</button>
          <button type="button" class="btn sm ghost" data-ia="dup">${icon('copy', 'sm')}Duplizieren</button>
          <button type="button" class="btn sm ghost" data-ia="del" style="color:var(--accent)">${icon('trash', 'sm')}Löschen</button>
        </span>
        <button type="submit" class="btn primary">Fertig</button>
      </div>`;
    if (!dlgItem.open) dlgItem.showModal();
  }
  const altRow = (p, k) => `<div class="altrow" data-k="${k}"><input data-alt="label" value="${esc(p.label || '')}" placeholder="Bezeichnung, z. B. Flugware" maxlength="40" aria-label="Bezeichnung des Zusatzpreises"><input data-alt="price" value="${esc(priceToInput(p))}" placeholder="Preis" inputmode="decimal" aria-label="Zusatzpreis"><button type="button" class="ibtn danger" data-ia="alt-del" aria-label="Zusatzpreis entfernen">${icon('trash')}</button></div>`;

  dlgItem.addEventListener('change', (e) => {
    const it = iById(itemId);
    if (!it) return;
    const el = e.target, err = $('#item-err');
    err.textContent = '';
    const snap = JSON.stringify(model);
    if (el.name === 'price') {
      const r = applyField(it, 'price', el);
      el.classList.toggle('invalid', r === 'invalid');
      if (r === 'invalid') { err.textContent = 'Preis nicht lesbar – z. B. 23,30, „a. Anfr.“ oder leer.'; return; }
    } else if (el.name === 'priceLabel') {
      const l = C.clean(el.value);
      if (l) it.price.label = l; else delete it.price.label;
    } else if (el.name === 'groupId') {
      const idx = model.items.indexOf(it);
      model.items.splice(idx, 1);
      it.groupId = el.value;
      let last = -1;
      model.items.forEach((x, i) => { if (x.groupId === it.groupId) last = i; });
      model.items.splice(last + 1, 0, it);
    } else if (el.dataset.alt) {
      const k = +el.closest('.altrow').dataset.k;
      const ap = it.altPrices[k];
      if (el.dataset.alt === 'label') ap.label = C.clean(el.value) || 'Weiterer Preis';
      else {
        const p = inputToPrice(el.value, ap.label);
        if (!p) { el.classList.add('invalid'); err.textContent = 'Zusatzpreis nicht lesbar.'; return; }
        el.classList.remove('invalid');
        it.altPrices[k] = p;
      }
    } else if (el.name) {
      if (applyField(it, el.name, el) === false) return;
      if (el.name === 'name' && autoAttr.has(it.id)) {
        dlgItem.querySelector('[name="category"]').value = it.category;
        dlgItem.querySelector('[name="condition"]').value = it.condition;
        dlgItem.querySelector('[name="origin"]').value = it.origin || '';
      }
    }
    if (JSON.stringify(model) !== snap) { undoStack.push(snap); $('#btn-undo').disabled = false; }
    changed({ render: true });
  });
  dlgItem.addEventListener('click', async (e) => {
    if (e.target === dlgItem || e.target.closest('[data-close]')) { dlgItem.close(); return; }
    const b = e.target.closest('[data-ia]');
    if (!b) return;
    const it = iById(itemId);
    if (!it) return;
    const a = b.dataset.ia;
    if (a === 'alt-add') {
      pushUndo();
      it.altPrices = it.altPrices || [];
      if (it.altPrices.length >= 5) { toast('Maximal 5 Zusatzpreise.'); return; }
      it.altPrices.push({ status: 'none', label: 'Weiterer Preis' });
      changed({ render: true });
      openItem(it.id);
      $$('#altlist [data-alt="label"]').pop()?.select();
    } else if (a === 'alt-del') {
      pushUndo();
      it.altPrices.splice(+b.closest('.altrow').dataset.k, 1);
      changed({ render: true });
      openItem(it.id);
    } else if (a === 'up' || a === 'down') {
      const same = model.items.filter((i) => i.groupId === it.groupId);
      const k = same.indexOf(it);
      const other = same[a === 'up' ? k - 1 : k + 1];
      if (!other) return;
      pushUndo();
      const i1 = model.items.indexOf(it), i2 = model.items.indexOf(other);
      [model.items[i1], model.items[i2]] = [model.items[i2], model.items[i1]];
      changed({ render: true });
      openItem(it.id);
    } else if (a === 'dup') {
      pushUndo();
      const copy = Object.assign(clone(it), { id: uid('n') });
      delete copy.cell; delete copy.nameRaw;
      model.items.splice(model.items.indexOf(it) + 1, 0, copy);
      changed({ render: true });
      openItem(copy.id);
      toast('Artikel dupliziert – jetzt die Kopie bearbeiten.');
    } else if (a === 'del') {
      pushUndo();
      model.items.splice(model.items.indexOf(it), 1);
      invalid.delete(it.id);
      dlgItem.close();
      changed({ render: true });
      toast(`„${it.name}“ gelöscht – mit „Rückgängig“ wiederherstellbar.`);
    }
  });
  $('#item-body').addEventListener('submit', (e) => { e.preventDefault(); dlgItem.close(); });

  /* ======================= Excel-Import ======================= */
  const dlgImport = $('#dlg-import');
  let pending = null;
  const fileInput = $('#file-input');
  function pickFile() { fileInput.click(); }
  fileInput.addEventListener('change', () => { const f = fileInput.files[0]; fileInput.value = ''; if (f) importFile(f); });
  window.addEventListener('dragover', (e) => { if ([...(e.dataTransfer?.types || [])].includes('Files')) e.preventDefault(); });
  window.addEventListener('drop', (e) => { const f = e.dataTransfer?.files?.[0]; if (f && model) { e.preventDefault(); importFile(f); } });

  const impHead = (t, s) => `<div class="dlg-head"><div><h2 id="imp-title">${t}</h2>${s ? `<p>${s}</p>` : ''}</div><button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>`;
  async function importFile(file) {
    if (!dlgImport.open) dlgImport.showModal();
    const body = $('#import-body');
    if (!/\.(xlsx|xlsm)$/i.test(file.name)) { importError(`„${file.name}“ ist keine .xlsx-Datei. Ältere .xls-Dateien bitte in Excel als „Excel-Arbeitsmappe (.xlsx)“ speichern.`); return; }
    if (file.size > 25 * 1024 * 1024) { importError('Die Datei ist größer als 25 MB.'); return; }
    body.innerHTML = `${impHead('Excel-Import', esc(file.name))}<div class="dlg-body"><div class="loading"><div class="spinner"></div>Datei wird gelesen …</div></div>`;
    try {
      const parsed = C.parseOfferWorkbook(await C.xlsxReadWorkbook(await file.arrayBuffer()), file.name);
      if (!parsed.items.length) throw new Error('In der Datei wurden keine Artikel gefunden.');
      pending = parsed;
      renderImport(parsed);
    } catch (e) { importError(e.message || String(e)); }
  }
  function importError(msg) {
    $('#import-body').innerHTML = `${impHead('Import nicht möglich')}<div class="dlg-body"><div class="err-box">${esc(msg)}</div><p class="hint">Der Entwurf bleibt unverändert.</p></div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Schließen</button><button type="button" class="btn primary" data-ia="again">Andere Datei wählen</button></div>`;
  }
  function issuesHTML(issues) {
    if (!issues.length) return '<p class="notice">Alle Zeilen wurden eindeutig erkannt.</p>';
    const s = issues.slice().sort((a, b) => (a.level === 'warn' ? 0 : 1) - (b.level === 'warn' ? 0 : 1));
    return `<ul class="issues">${s.map((x) => `<li class="${x.level}"><span class="lvl">${x.level === 'warn' ? 'Prüfen' : 'Info'}</span><span>${esc(x.message)}</span>${x.cell ? `<span class="cell">Zelle ${esc(x.cell)}</span>` : ''}</li>`).join('')}</ul>`;
  }
  function renderImport(d) {
    const ref = published || model;
    const df = C.diffOffers(ref, d);
    const nVal = d.items.filter((i) => i.price.status === 'value').length;
    const warn = d.issues.filter((x) => x.level === 'warn').length;
    const draftDirty = published && C.diffOffers(published, model);
    const hasDraftEdits = draftDirty && (draftDirty.added.length + draftDirty.removed.length + draftDirty.priceChanged.length + draftDirty.changed.length) > 0;
    $('#import-body').innerHTML = `${impHead(d.meta.week ? `KW ${esc(d.meta.week)} / ${esc(d.meta.year ?? '?')} erkannt` : 'Datei gelesen', `${esc(d.meta.source)} · Blatt „${esc(d.meta.sheetName)}“`)}
      <div class="dlg-body">
        <div class="imp-sum">
          <div><span>Positionen</span><strong>${fmtInt.format(d.items.length)}</strong></div>
          <div><span>Gruppen</span><strong>${fmtInt.format(d.groups.length)}</strong></div>
          <div><span>Mit Preis</span><strong>${fmtInt.format(nVal)}</strong></div>
        </div>
        <p class="diff">Gegenüber ${published ? `der veröffentlichten KW ${esc(published.meta.week)}` : 'dem Entwurf'}: <span><b>${df.added.length}</b> neu</span><span><b>${df.removed.length}</b> entfallen</span><span><b>${df.priceChanged.length}</b> Preisänderungen</span></p>
        ${hasDraftEdits ? '<p class="err-box" style="margin:0 0 14px">Der aktuelle Entwurf enthält unveröffentlichte manuelle Änderungen. Der Import ersetzt den Entwurf vollständig (mit „Rückgängig“ wiederherstellbar).</p>' : ''}
        <h3 class="d-h"><span>Hinweise zur Übernahme${warn ? ` · ${warn} zu prüfen` : ''}</span></h3>
        ${issuesHTML(d.issues)}
      </div>
      <div class="dlg-foot"><button type="button" class="btn" data-ia="again">Andere Datei</button><span class="spacer"></span><button type="button" class="btn" data-close>Abbrechen</button><button type="button" class="btn primary" data-ia="apply">${icon('check')}Als Entwurf übernehmen</button></div>`;
  }
  dlgImport.addEventListener('click', (e) => {
    if (e.target === dlgImport || e.target.closest('[data-close]')) { dlgImport.close(); return; }
    const a = e.target.closest('[data-ia]')?.dataset.ia;
    if (a === 'again') pickFile();
    if (a === 'apply' && pending) {
      pushUndo();
      const d = pending;
      pending = null;
      model = { meta: { week: d.meta.week, year: d.meta.year, notice: d.meta.notice || model.meta.notice || '', title: d.meta.title, source: d.meta.source, sheetName: d.meta.sheetName }, sections: d.sections, groups: d.groups, items: d.items };
      invalid.clear(); autoAttr.clear();
      dlgImport.close();
      renderMeta();
      changed({ render: true });
      toast(`Import übernommen: ${plural(d.items.length, 'Position', 'Positionen')}. Prüfen, ggf. anpassen, dann veröffentlichen.`, 5000);
    }
  });

  /* ======================= Veröffentlichen ======================= */
  const dlgPublish = $('#dlg-publish');
  function openPublish() {
    const v = C.validateModel(model);
    if (invalid.size) v.errors.unshift(`${plural(invalid.size, 'Preis ist', 'Preise sind')} nicht lesbar – bitte korrigieren (rot markiert).`);
    const before = new Map(Object.entries(diff.before));
    const byId = new Map(model.items.map((i) => [i.id, i]));
    const list = (ids, fn, max = 12) => {
      const arr = ids.map((x) => (typeof x === 'string' ? byId.get(x) : x)).filter(Boolean);
      return `<ul class="plist">${arr.slice(0, max).map(fn).join('')}${arr.length > max ? `<li><span>… und ${arr.length - max} weitere</span><span></span></li>` : ''}</ul>`;
    };
    const sec = (title, html) => `<h3 class="d-h"><span>${title}</span></h3>${html}`;
    let body = '';
    if (v.errors.length) body += sec('Bitte zuerst korrigieren', `<ul class="plist">${v.errors.map((e) => `<li class="err"><span>${esc(e)}</span><span></span></li>`).join('')}</ul>`);
    if (!published) body += `<p class="notice">Erste Veröffentlichung: ${plural(model.items.length, 'Artikel', 'Artikel')} in ${plural(model.groups.length, 'Gruppe', 'Gruppen')}.</p>`;
    else {
      if (metaChanged()) body += sec('Kopfdaten', `<ul class="plist"><li><span>KW ${esc(published.meta.week)}/${esc(published.meta.year)} → KW ${esc(model.meta.week)}/${esc(model.meta.year)}</span><span>${esc(model.meta.notice || '')}</span></li></ul>`);
      if (diff.priceChanged.length) body += sec(`Preisänderungen (${diff.priceChanged.length})`, list(diff.priceChanged, (it) => `<li><span>${esc(it.code || '—')} · ${esc(it.name)}</span><span>${esc(priceShort(before.get(it.id).price))} → <strong>${esc(priceShort(it.price))}</strong></span></li>`));
      if (diff.added.length) body += sec(`Neu (${diff.added.length})`, list(diff.added, (it) => `<li><span>${esc(it.code || '—')} · ${esc(it.name)}</span><span>${esc(priceShort(it.price))}</span></li>`));
      if (diff.changed.length) body += sec(`Bearbeitet (${diff.changed.length})`, list(diff.changed, (it) => `<li><span>${esc(it.code || '—')} · ${esc(it.name)}</span><span>${esc(gById(it.groupId)?.name || '')}</span></li>`));
      if (diff.removed.length) body += sec(`Entfernt (${diff.removed.length})`, list(diff.removed, (it) => `<li><span>${esc(it.code || '—')} · ${esc(it.name)}</span><span>${esc(priceShort(it.price))}</span></li>`));
      if (!metaChanged() && !diff.priceChanged.length && !diff.added.length && !diff.changed.length && !diff.removed.length) body += '<p class="notice">Keine Änderungen gegenüber der veröffentlichten Fassung.</p>';
    }
    if (v.warnings.length) body += `<p class="hint">${v.warnings.map(esc).join('<br>')}</p>`;
    const can = !v.errors.length;
    $('#publish-body').innerHTML = `<div class="dlg-head"><div><h2 id="pub-title">Veröffentlichen</h2><p>Nach dem Veröffentlichen sehen alle Besucher der Angebotsseite diesen Stand. Der bisherige Stand wird als Version gesichert.</p></div><button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">${body}</div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="button" class="btn primary" data-ia="publish"${can ? '' : ' disabled'}>${icon('send')}Jetzt veröffentlichen</button></div>`;
    dlgPublish.showModal();
  }
  dlgPublish.addEventListener('click', async (e) => {
    if (e.target === dlgPublish || e.target.closest('[data-close]')) { dlgPublish.close(); return; }
    const b = e.target.closest('[data-ia="publish"]');
    if (!b) return;
    b.disabled = true;
    b.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px"></div>Wird veröffentlicht …';
    try {
      clearTimeout(saveTimer);
      const r = await api('publish', { body: { model } });
      published = clone(model);
      revision = 0;
      savedAt = null;
      dlgPublish.close();
      diff = C.diffOffers(published, model);
      renderAll();
      setSaveState('clean');
      toast(`Veröffentlicht: KW ${model.meta.week}/${model.meta.year} ist jetzt online (${dateTime(r.publishedAt)} Uhr).`, 6000);
    } catch (ex) {
      b.disabled = false;
      b.innerHTML = `${icon('send')}Erneut versuchen`;
      $('#publish-body .dlg-body').insertAdjacentHTML('afterbegin', `<p class="err-box" style="margin:0 0 12px">${esc(ex.message)}</p>`);
    }
  });

  /* ======================= Versionen ======================= */
  const dlgVer = $('#dlg-versions');
  async function openVersions() {
    $('#versions-body').innerHTML = `<div class="dlg-head"><div><h2 id="ver-title">Frühere Veröffentlichungen</h2><p>Eine Version kann als Entwurf geladen, geprüft und erneut veröffentlicht werden.</p></div><button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body"><div class="loading"><div class="spinner"></div>Wird geladen …</div></div>`;
    dlgVer.showModal();
    try {
      const r = await api('versions');
      const cur = published ? `<li><div><div class="v-t">KW ${esc(published.meta.week)}/${esc(published.meta.year)} · aktuell online</div><div class="v-s">${plural(published.items.length, 'Artikel', 'Artikel')}</div></div><span class="v-s">aktuell</span></li>` : '';
      $('#versions-body .dlg-body').innerHTML = r.versions.length || cur
        ? `<ul class="vlist">${cur}${r.versions.map((v) => `<li><div><div class="v-t">KW ${esc(v.week ?? '?')}/${esc(v.year ?? '?')}</div><div class="v-s">${plural(v.items, 'Artikel', 'Artikel')} · veröffentlicht ${esc(dateTime(v.publishedAt))} Uhr${v.source ? ' · ' + esc(v.source) : ''}</div></div><button type="button" class="btn sm" data-ver="${esc(v.id)}">Als Entwurf laden</button></li>`).join('')}</ul>`
        : '<p class="notice">Noch keine früheren Veröffentlichungen.</p>';
    } catch (e) {
      $('#versions-body .dlg-body').innerHTML = `<div class="err-box">${esc(e.message)}</div>`;
    }
  }
  dlgVer.addEventListener('click', async (e) => {
    if (e.target === dlgVer || e.target.closest('[data-close]')) { dlgVer.close(); return; }
    const b = e.target.closest('[data-ver]');
    if (!b) return;
    try {
      const r = await api('version', { query: '&id=' + encodeURIComponent(b.dataset.ver) });
      pushUndo();
      model = strip(r.model);
      invalid.clear(); autoAttr.clear();
      dlgVer.close();
      renderMeta();
      changed({ render: true });
      toast('Version als Entwurf geladen – zum Übernehmen veröffentlichen.', 5000);
    } catch (ex) { toast(ex.message); }
  });

  /* ======================= Menü & Kopf ======================= */
  const menuBtn = $('#btn-more'), menu = $('#menu-more');
  const setMenu = (open) => { menu.hidden = !open; menuBtn.setAttribute('aria-expanded', open); if (open) menu.querySelector('button').focus(); };
  menuBtn.addEventListener('click', () => setMenu(menu.hidden));
  document.addEventListener('click', (e) => { if (!menu.hidden && !e.target.closest('.menu-wrap')) setMenu(false); });
  menu.addEventListener('keydown', (e) => {
    const items = $$('button', menu), i = items.indexOf(document.activeElement);
    if (e.key === 'ArrowDown') { e.preventDefault(); items[(i + 1) % items.length].focus(); }
    if (e.key === 'ArrowUp') { e.preventDefault(); items[(i - 1 + items.length) % items.length].focus(); }
    if (e.key === 'Escape') { setMenu(false); menuBtn.focus(); }
  });
  menu.addEventListener('click', async (e) => {
    const a = e.target.closest('[data-act]')?.dataset.act;
    if (!a) return;
    setMenu(false);
    if (a === 'versions') openVersions();
    if (a === 'open-site') window.open('../', '_blank', 'noopener');
    if (a === 'password') { $('#pw-form').reset(); $('#pw-err').textContent = ''; $('#dlg-password').showModal(); }
    if (a === 'theme') {
      const cur = document.documentElement.getAttribute('data-theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      const next = cur === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      store.set('theme', next);
    }
    if (a === 'discard') {
      if (!(await confirmBox('Entwurf verwerfen?', published ? 'Alle unveröffentlichten Änderungen werden verworfen. Der Entwurf entspricht danach wieder der veröffentlichten Fassung.' : 'Der gesamte Entwurf wird gelöscht.', 'Verwerfen', true))) return;
      try {
        clearTimeout(saveTimer);
        await api('discard_draft', { body: {} });
        pushUndo();
        model = published ? clone(published) : emptyModel();
        revision = 0; savedAt = null; invalid.clear(); autoAttr.clear();
        renderAll();
        setSaveState('clean');
        toast('Entwurf verworfen.');
      } catch (ex) { toast(ex.message); }
    }
    if (a === 'logout') {
      if (unsaved()) await saveNow();
      try { await api('logout', { body: {} }); } catch { /* ignore */ }
      csrf = null; model = null;
      showAuth('login');
    }
  });

  $('#pw-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const err = $('#pw-err');
    if (f.get('password') !== f.get('password2')) { err.textContent = 'Die neuen Passwörter stimmen nicht überein.'; return; }
    try {
      await api('change_password', { body: { current: f.get('current'), password: f.get('password') } });
      $('#dlg-password').close();
      toast('Passwort geändert.');
    } catch (ex) { err.textContent = ex.message; }
  });

  $('#btn-undo').addEventListener('click', undo);
  $('#btn-import').addEventListener('click', pickFile);
  $('#btn-publish').addEventListener('click', () => { if (document.activeElement && document.activeElement.matches('.in, .fld input')) document.activeElement.blur(); setTimeout(openPublish, 0); });
  $('#btn-add-group').addEventListener('click', addGroup);
  $('#btn-preview').addEventListener('click', async () => {
    const w = window.open('', '_blank');
    if (unsaved()) await saveNow();
    if (w) w.location = '../?vorschau=1'; else location.href = '../?vorschau=1';
  });
  $('#save-state').addEventListener('click', (e) => { if (e.target.closest('[data-act="retry-save"]')) saveNow(); });
  for (const d of $$('dialog')) d.addEventListener('click', (e) => { if (e.target === d || e.target.closest('[data-close]')) { if (d.id !== 'dlg-confirm') d.close(); } });

  document.addEventListener('keydown', (e) => {
    const inField = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement.tagName);
    if ((e.ctrlKey || e.metaKey) && !e.shiftKey && e.key.toLowerCase() === 'z' && !inField && !$('dialog[open]') && model) { e.preventDefault(); undo(); }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && model) { e.preventDefault(); if (document.activeElement.matches('.in')) document.activeElement.dispatchEvent(new Event('change', { bubbles: true })); saveNow(); }
  });

  const setH = () => document.documentElement.style.setProperty('--header-h', ($('#topbar').offsetHeight || 0) + 'px');
  if ('ResizeObserver' in window) new ResizeObserver(setH).observe($('#topbar'));

  /* ======================= Start ======================= */
  (async function boot() {
    try {
      const s = await api('status');
      company = s.company || '';
      $$('[data-company]').forEach((el) => { el.textContent = company; el.hidden = !company; });
      if (s.setupRequired) { showAuth('setup'); return; }
      if (!s.loggedIn) { showAuth('login'); return; }
      csrf = s.csrf;
      await openEditor();
    } catch (e) {
      document.body.innerHTML = `<main class="auth"><div class="auth-card"><h1 style="margin:0;font-size:18px">Eingabebereich nicht erreichbar</h1><p class="auth-intro">${esc(e.message)}</p><p class="auth-intro">Die Seite muss über den Webserver aufgerufen werden, PHP muss aktiv sein.</p></div></main>`;
    }
  })();
})();
