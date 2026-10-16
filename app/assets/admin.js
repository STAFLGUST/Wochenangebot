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
  const ROLE_RANK = { viewer: 1, editor: 2, admin: 3 };
  const ROLE_LABEL = { viewer: 'Nur ansehen', editor: 'Bearbeiter', admin: 'Administrator' };
  let me = null;                                   // angemeldeter Nutzer
  const can = (role) => !!me && ROLE_RANK[me.role] >= ROLE_RANK[role];
  let ro = true;                                   // Nur-Ansicht
  let authMode = 'login';
  let loginPw = '';                                // nur für den Pflicht-Passwortwechsel direkt nach der Anmeldung
  function showAuth(mode) {
    authMode = mode;
    $('#screen-auth').hidden = false;
    if (mode !== 'expired') $('#screen-editor').hidden = true;
    const setup = mode === 'setup', newpw = mode === 'newpw';
    $('#auth-intro').textContent = setup
      ? 'Ersteinrichtung: Legen Sie den ersten Administrator-Zugang an (Passwort mindestens 10 Zeichen). Weitere Nutzer legen Sie danach unter „Nutzer“ an.'
      : newpw ? `Hallo ${me ? me.name : ''}, bitte legen Sie jetzt ein eigenes Passwort fest (mindestens 10 Zeichen).`
        : mode === 'expired' ? 'Ihre Sitzung ist abgelaufen. Bitte erneut anmelden – Ihre Änderungen bleiben erhalten.'
          : 'Bitte melden Sie sich mit Ihrem Benutzernamen an.';
    $('#au-user-wrap').hidden = newpw;
    $('#au-user').required = !newpw;
    $('#au-name-wrap').hidden = !setup;
    $('#pw2-wrap').hidden = !(setup || newpw);
    $('#pw1-lbl').textContent = newpw ? 'Neues Passwort' : 'Passwort';
    $('#pw1').autocomplete = setup || newpw ? 'new-password' : 'current-password';
    $('#auth-submit').textContent = setup ? 'Zugang anlegen' : newpw ? 'Passwort speichern' : 'Anmelden';
    $('#auth-err').textContent = '';
    $('#pw1').value = ''; $('#pw2').value = '';
    if (mode === 'expired' && me) $('#au-user').value = me.username;
    $('#screen-auth').classList.toggle('overlay', mode === 'expired');
    setTimeout(() => ((newpw || $('#au-user').value) ? $('#pw1') : $('#au-user')).focus(), 30);
  }
  $('#auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const pw = $('#pw1').value;
    const err = $('#auth-err');
    err.textContent = '';
    if (authMode === 'setup' || authMode === 'newpw') {
      if (pw.length < 10) { err.textContent = 'Das Passwort muss mindestens 10 Zeichen lang sein.'; return; }
      if (pw !== $('#pw2').value) { err.textContent = 'Die beiden Passwörter stimmen nicht überein.'; return; }
    }
    $('#auth-submit').disabled = true;
    try {
      if (authMode === 'newpw') {
        const r = await api('change_password', { body: { current: loginPw, password: pw } });
        loginPw = '';
        me = r.user;
        toast('Passwort gespeichert.');
        await openEditor();
        return;
      }
      const prevUser = me && me.id;
      const r = await api(authMode === 'setup' ? 'setup' : 'login', { body: { username: $('#au-user').value.trim(), name: $('#au-name').value.trim(), password: pw } });
      csrf = r.csrf;
      me = r.user;
      if (me.mustChange) { loginPw = pw; showAuth('newpw'); return; }
      $('#screen-auth').classList.remove('overlay');
      if (authMode === 'expired' && model && prevUser === me.id) { $('#screen-auth').hidden = true; $('#screen-editor').hidden = false; applyRole(); if (!ro) saveNow(); }
      else await openEditor();
    } catch (ex) {
      err.textContent = ex.message;
    } finally {
      $('#auth-submit').disabled = false;
    }
  });

  /* Rolle auf die Oberfläche anwenden */
  function applyRole() {
    ro = !can('editor');
    document.body.classList.toggle('ro', ro);
    document.body.classList.toggle('is-admin', can('admin'));
    $('#vt-users').hidden = !can('admin');
    $('#vt-log').hidden = !can('admin');
    $('#menu-user').innerHTML = me ? `<strong>${esc(me.name)}</strong><span>${esc(me.username)} · ${esc(ROLE_LABEL[me.role])}</span>` : '';
    if (!can('admin') && (currentView === 'users' || currentView === 'log')) setView('edit');
  }
  /* Nur-Ansicht: Eingabefelder sperren (Suche/Filter bleiben bedienbar) */
  function lockInputs(root) {
    if (!ro || !root) return;
    for (const el of root.querySelectorAll('input, select, textarea')) {
      if (el.closest('.ed-toolbar') || el.closest('.keep-enabled')) continue;
      el.disabled = true;
    }
  }

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
    applyRole();
    renderAll();
    setSaveState(d.draft ? 'saved' : 'clean');
    if (currentView !== 'edit') setView(currentView);
  }

  /* ======================= Speichern ======================= */
  let saveTimer = null, saving = false, queued = false, saveError = null;
  function setSaveState(st, msg) {
    const el = $('#save-state');
    el.className = 'save-state ' + st;
    const hasChanges = diff && (diff.added.length + diff.removed.length + diff.priceChanged.length + diff.changed.length + (metaChanged() ? 1 : 0)) > 0;
    let text;
    if (ro) text = `${icon('lock', 'sm')} Nur Ansicht – ${hasChanges ? 'Entwurf mit unveröffentlichten Änderungen' : 'keine offenen Änderungen'}`;
    else if (st === 'pending' || st === 'saving') text = 'Speichert …';
    else if (st === 'error') text = `Nicht gespeichert: ${esc(msg || saveError || '')} <button type="button" class="link-btn" data-act="retry-save">Erneut versuchen</button>`;
    else if (!hasChanges && !published) text = 'Noch nichts veröffentlicht';
    else if (!hasChanges) text = 'Keine Änderungen gegenüber der veröffentlichten Fassung';
    else text = `Entwurf gespeichert${savedAt ? ' · ' + timeOnly(savedAt) + ' Uhr' : ''} · <strong>noch nicht veröffentlicht</strong>`;
    el.innerHTML = `<span class="dot"></span><span>${text}</span>`;
  }
  function changed(opts = {}) {
    if (ro) return;
    diff = C.diffOffers(published, model);
    if (opts.render) renderGroups(); else if (opts.row) updateRow(opts.row);
    renderChanges();
    renderMetaInfo();
    updatePublishBtn();
    setSaveState('pending');
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveNow, 700);
  }
  let saveNote = null;       // Hinweis für das Protokoll (Excel-Import, Version geladen)
  async function saveNow() {
    clearTimeout(saveTimer);
    if (ro || !model) return;
    if (saving) { queued = true; return; }
    saving = true;
    setSaveState('saving');
    const note = saveNote;
    try {
      const r = await api('save_draft', { body: { model, revision, note } });
      if (saveNote === note) saveNote = null;
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
    if (ro || !undoStack.length) return;
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
    for (const id of ['#m-week', '#m-year', '#m-notice']) $(id).disabled = ro;
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
    lockInputs(nr);
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
    lockInputs(host);
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
    if (ro) return;
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
    if (ro) return;
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
        <div class="fld span2" id="item-hist"></div>
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
    if (ro) {
      lockInputs($('#item-body'));
      $('#it-title').textContent = 'Artikel';
      $('#item-body .dlg-head p').textContent = 'Nur Ansicht – Ihre Rolle erlaubt keine Änderungen.';
    }
    if (!dlgItem.open) dlgItem.showModal();
    fillItemHistory(it);
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
    if (ro && b.dataset.ia !== 'hist-open') return;
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
  function pickFile() { if (!ro) fileInput.click(); }
  fileInput.addEventListener('change', () => { const f = fileInput.files[0]; fileInput.value = ''; if (f) importFile(f); });
  window.addEventListener('dragover', (e) => { if ([...(e.dataTransfer?.types || [])].includes('Files')) e.preventDefault(); });
  window.addEventListener('drop', (e) => { const f = e.dataTransfer?.files?.[0]; if (f && model) { e.preventDefault(); if (!ro && currentView === 'edit') importFile(f); } });

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
      saveNote = { type: 'import', file: d.meta.source || '' };
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
    if (ro) return;
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
      hist = null;
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
        ? `<ul class="vlist">${cur}${r.versions.map((v) => `<li><div><div class="v-t">KW ${esc(v.week ?? '?')}/${esc(v.year ?? '?')}</div><div class="v-s">${plural(v.items, 'Artikel', 'Artikel')} · veröffentlicht ${esc(dateTime(v.publishedAt))} Uhr${v.source ? ' · ' + esc(v.source) : ''}</div></div>${ro ? '' : `<button type="button" class="btn sm" data-ver="${esc(v.id)}">Als Entwurf laden</button>`}</li>`).join('')}</ul>`
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
      if (ro) return;
      pushUndo();
      model = strip(r.model);
      saveNote = { type: 'version' };
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
      if (ro) return;
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
      csrf = null; model = null; me = null; hist = null;
      $('#au-user').value = '';
      showAuth('login');
    }
  });

  $('#pw-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = new FormData(e.target);
    const err = $('#pw-err');
    if (f.get('password') !== f.get('password2')) { err.textContent = 'Die neuen Passwörter stimmen nicht überein.'; return; }
    try {
      const r = await api('change_password', { body: { current: f.get('current'), password: f.get('password') } });
      me = r.user;
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
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's' && model && !ro) { e.preventDefault(); if (document.activeElement.matches('.in')) document.activeElement.dispatchEvent(new Event('change', { bubbles: true })); saveNow(); }
  });

  const setH = () => document.documentElement.style.setProperty('--header-h', ($('#topbar').offsetHeight || 0) + 'px');
  if ('ResizeObserver' in window) new ResizeObserver(setH).observe($('#topbar'));

  /* ======================= Preisverlauf ======================= */
  let hist = null;            // { weeks, series, dup }
  let histLoading = null;
  let histQ = '', histOnlyChanged = false, histSort = 'offer';
  /* Zeitraum: Anzahl Kalenderwochen zurück ab der neuesten Woche */
  const RANGES = [['1W', 1, '1 Woche'], ['1M', 4, '1 Monat'], ['3M', 13, '3 Monate'], ['6M', 26, '6 Monate'], ['12M', 52, '12 Monate'], ['Alle', Infinity, 'gesamter Zeitraum']];
  let histRange = RANGES.some((r) => r[0] === store.get('histRange', '3M')) ? store.get('histRange', '3M') : '3M';
  let currentView = 'edit';

  const nk = (s) => String(s || '').toLowerCase().replace(/[^a-z0-9äöüß]+/g, '');
  const wkLabel = (w) => `KW ${w.week}/${String(w.year).slice(2)}`;
  const wkLong = (w) => `KW ${w.week}/${w.year}`;
  const numVal = (p) => (p && p.price && p.price.status === 'value' ? p.price.value : null);
  const fmtDelta = (d) => (d > 0 ? '+' : d < 0 ? '−' : '±') + fmtNum.format(Math.abs(d));

  /* Artikel-Schlüssel über alle Wochen: Artikelnummer; bei mehrfach vergebenen Nummern zusätzlich Bezeichnung + Gruppe */
  function seriesKey(it, dup) {
    if (it.code && !dup.has(it.code)) return 'c:' + it.code;
    return 'n:' + (it.code || '') + '|' + nk(it.name) + '|' + nk(it.group);
  }
  function buildHistory(weeks) {
    weeks = weeks.slice().sort((a, b) => a.year * 100 + a.week - (b.year * 100 + b.week));
    for (const w of weeks) w.ord = Math.round(Date.parse(C.isoWeekRange(w.week, w.year).start) / (7 * 864e5));
    const dup = new Set();
    for (const w of weeks) {
      const c = new Map();
      for (const it of w.items) if (it.code) c.set(it.code, (c.get(it.code) || 0) + 1);
      for (const [k, n] of c) if (n > 1) dup.add(k);
    }
    const map = new Map();
    weeks.forEach((w, wi) => {
      w.items.forEach((it, ii) => {
        const key = seriesKey(it, dup);
        let s = map.get(key);
        if (!s) { s = { key, code: it.code, points: new Array(weeks.length).fill(null) }; map.set(key, s); }
        if (s.points[wi]) return;
        s.points[wi] = it;
        s.name = it.name; s.group = it.group; s.category = it.category; s.order = ii; s.lastWi = wi;
      });
    });
    const L = weeks.length - 1;
    const series = [...map.values()].map((s) => {
      s.vals = s.points.map(numVal);
      const nums = s.vals.filter((v) => v != null);
      s.min = nums.length ? Math.min(...nums) : null;
      s.max = nums.length ? Math.max(...nums) : null;
      s.avg = nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null;
      s.weeksCount = s.points.filter(Boolean).length;
      s.inLatest = !!s.points[L];
      s.cur = s.inLatest ? s.points[L] : null;
      s.delta = L > 0 && s.vals[L] != null && s.vals[L - 1] != null ? Number((s.vals[L] - s.vals[L - 1]).toFixed(4)) : null;
      let changes = 0, last = null;
      for (const v of s.vals) { if (v == null) continue; if (last != null && v !== last) changes++; last = v; }
      s.changes = changes;
      s.hay = nk([s.code, s.name, s.group, s.category].join(' '));
      return s;
    });
    return { weeks, series, dup };
  }
  /* Wochen-Indizes im gewählten Zeitraum */
  function rangeIdx(H) {
    const L = H.weeks.length - 1;
    if (L < 0) return [];
    const back = (RANGES.find((r) => r[0] === histRange) || RANGES[2])[1];
    const from = H.weeks[L].ord - back;
    const idx = [];
    H.weeks.forEach((w, i) => { if (w.ord >= from) idx.push(i); });
    return idx;
  }
  /* Kennzahlen eines Artikels im Zeitraum */
  function statsFor(s, idx) {
    const vals = idx.map((i) => s.vals[i]);
    const nums = vals.filter((v) => v != null);
    const L = idx[idx.length - 1];
    let firstI = null;
    for (const i of idx) if (s.vals[i] != null) { firstI = i; break; }
    const last = s.vals[L];
    let changes = 0, prev = null;
    for (const v of vals) { if (v == null) continue; if (prev != null && v !== prev) changes++; prev = v; }
    return {
      vals,
      min: nums.length ? Math.min(...nums) : null,
      max: nums.length ? Math.max(...nums) : null,
      avg: nums.length ? nums.reduce((a, b) => a + b, 0) / nums.length : null,
      weeksCount: idx.filter((i) => s.points[i]).length,
      delta: last != null && firstI != null && firstI !== L ? Number((last - s.vals[firstI]).toFixed(4)) : null,
      deltaFrom: firstI,
      changes,
    };
  }
  const rangeSeg = () => `<div class="seg txt" role="group" aria-label="Zeitraum">${RANGES.map(([k, , t]) => `<button type="button" data-hrange="${k}" aria-pressed="${histRange === k}" title="${t}">${k}</button>`).join('')}</div>`;
  function setRange(k) { histRange = k; store.set('histRange', k); }

  async function loadHistory(force) {
    if (hist && !force) return hist;
    if (!histLoading) histLoading = api('history_data').then((r) => { hist = buildHistory(r.weeks); return hist; }).finally(() => { histLoading = null; });
    return histLoading;
  }

  /* Mini-Verlauf */
  function sparkSVG(vals, w = 132, h = 30) {
    const nums = vals.filter((v) => v != null);
    if (!nums.length) return `<svg class="spark" width="${w}" height="${h}" aria-hidden="true"></svg>`;
    const lo = Math.min(...nums), hi = Math.max(...nums), pad = 4;
    const n = vals.length;
    const x = (i) => (n === 1 ? w / 2 : pad + (i * (w - 2 * pad)) / (n - 1));
    const y = (v) => (hi === lo ? h / 2 : h - pad - ((v - lo) * (h - 2 * pad)) / (hi - lo));
    let d = '', pen = false;
    vals.forEach((v, i) => { if (v == null) { pen = false; return; } d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1) + ' '; pen = true; });
    let li = vals.length - 1; while (li >= 0 && vals[li] == null) li--;
    return `<svg class="spark" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" aria-hidden="true"><path d="${d}"/><circle cx="${x(li).toFixed(1)}" cy="${y(vals[li]).toFixed(1)}" r="2.6"/></svg>`;
  }

  /* Ansicht umschalten */
  const VIEWS = ['edit', 'hist', 'users', 'log'];
  function setView(v) {
    if ((v === 'users' || v === 'log') && !can('admin')) v = 'edit';
    currentView = v;
    for (const k of VIEWS) {
      $('#vt-' + k).setAttribute('aria-selected', k === v);
      $('#view-' + k).hidden = k !== v;
    }
    document.body.classList.toggle('in-hist', v === 'hist');
    document.body.classList.toggle('in-other', v !== 'edit');
    if (v === 'hist') renderHistView();
    if (v === 'users') renderUsersView();
    if (v === 'log') renderLogView();
  }
  for (const k of VIEWS) $('#vt-' + k).addEventListener('click', () => setView(k));

  async function renderHistView() {
    const host = $('#view-hist');
    if (!hist) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Preisverlauf wird geladen …</div>';
    try { await loadHistory(); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    const H = hist;
    host.innerHTML = `
      ${H.weeks.length < 2 ? `<div class="notice hist-empty"><p>Für einen Verlauf werden mindestens zwei Wochen benötigt. Laden Sie frühere Angebotslisten hoch – mehrere Dateien auf einmal sind möglich. Jede Veröffentlichung wird ab jetzt automatisch übernommen.</p><button type="button" class="btn primary" id="hist-upload">${icon('upload')}Alte Angebote hochladen</button></div>` : ''}
      <div class="ed-toolbar">
        <div class="search">${icon('search')}<input id="hist-q" type="search" autocomplete="off" placeholder="Artikel finden: Nummer, Bezeichnung, Gruppe …" aria-label="Artikel im Preisverlauf suchen" value="${esc(histQ)}"></div>
        ${rangeSeg()}
        <label class="check"><input type="checkbox" id="hist-only"${histOnlyChanged ? ' checked' : ''}> Nur mit Preisänderung im Zeitraum</label>
        <label class="select"><span class="sr-only">Sortierung</span><select id="hist-sort">
          ${[['offer', 'Angebotsreihenfolge'], ['up', 'Größte Erhöhung'], ['down', 'Größte Senkung'], ['changes', 'Häufigste Änderungen'], ['code', 'Artikelnummer'], ['name', 'Bezeichnung']].map(([v, l]) => `<option value="${v}"${histSort === v ? ' selected' : ''}>${l}</option>`).join('')}
        </select>${icon('chev', 'sm')}</label>
        <span class="ed-hint" id="hist-count"></span>
      </div>
      <div id="hist-list"></div>`;
    $('#hist-data span').innerHTML = `Daten<em> · ${esc(plural(H.weeks.length, 'Woche', 'Wochen'))}</em>`;
    if (dlgHD.open) renderHistData();
    renderHistList();
  }
  function renderHistList() {
    const H = hist;
    const host = $('#hist-list');
    if (!host) return;
    if (!H.weeks.length) { host.innerHTML = ''; $('#hist-count').textContent = ''; return; }
    const toks = nk(histQ) ? histQ.toLowerCase().split(/\s+/).map(nk).filter(Boolean) : [];
    const idx = rangeIdx(H);
    const st = new Map(H.series.map((s) => [s, statsFor(s, idx)]));
    let list = H.series.filter((s) => {
      const x = st.get(s);
      return x.weeksCount > 0 && (!histOnlyChanged || x.changes > 0) && toks.every((t) => s.hay.includes(t));
    });
    const L = H.weeks.length - 1;
    const by = {
      offer: (a, b) => (b.inLatest - a.inLatest) || (b.lastWi - a.lastWi) || a.order - b.order,
      up: (a, b) => (st.get(b).delta ?? -Infinity) - (st.get(a).delta ?? -Infinity),
      down: (a, b) => (st.get(a).delta ?? Infinity) - (st.get(b).delta ?? Infinity),
      changes: (a, b) => st.get(b).changes - st.get(a).changes || (b.inLatest - a.inLatest),
      code: (a, b) => (!a.code) - (!b.code) || String(a.code || '').localeCompare(String(b.code || ''), 'de', { numeric: true }),
      name: (a, b) => a.name.localeCompare(b.name, 'de'),
    };
    list.sort(by[histSort] || by.offer);
    $('#hist-count').textContent = `${plural(list.length, 'Artikel', 'Artikel')} · ${wkLong(H.weeks[idx[0]])} – ${wkLong(H.weeks[L])}`;
    const rows = list.map((s) => {
      const x = st.get(s);
      const cur = s.cur ? priceShort(s.cur.price) : '';
      const d = x.delta;
      return `<tr data-skey="${esc(s.key)}" tabindex="0">
        <td class="h-code">${esc(s.code || '—')}</td>
        <td class="h-name"><div class="nm">${esc(s.name)}</div><div class="sub">${esc(s.group)}${s.inLatest ? '' : ` · <span class="gone">nicht mehr im Angebot (zuletzt ${esc(wkLabel(H.weeks[s.lastWi]))})</span>`}</div></td>
        <td class="h-spark">${sparkSVG(x.vals)}</td>
        <td class="h-cur num">${s.inLatest ? esc(cur) : '<span class="muted">—</span>'}</td>
        <td class="h-delta num">${d == null ? '<span class="muted">—</span>' : d === 0 ? '<span class="muted">±0</span>' : `<span class="delta ${d > 0 ? 'up' : 'down'}" title="gegenüber ${esc(wkLong(H.weeks[x.deltaFrom]))}">${fmtDelta(d)}</span>`}</td>
        <td class="h-range num">${x.min == null ? '<span class="muted">—</span>' : x.min === x.max ? fmtNum.format(x.min) : `${fmtNum.format(x.min)} – ${fmtNum.format(x.max)}`}</td>
        <td class="h-weeks num">${x.weeksCount}</td>
      </tr>`;
    }).join('');
    host.innerHTML = list.length ? `<div class="gcard"><table class="etab htab"><thead><tr>
        <th class="h-code">Art.-Nr.</th><th class="h-name">Bezeichnung</th><th class="h-spark">Verlauf</th><th class="h-cur num">Aktuell €/kg</th><th class="h-delta num" title="Aktueller Preis gegenüber dem ersten Preis im gewählten Zeitraum">Änderung ${esc(histRange === 'Alle' ? '' : histRange)}</th><th class="h-range num">Spanne</th><th class="h-weeks num">Wochen</th>
      </tr></thead><tbody>${rows}</tbody></table></div>`
      : '<div class="ed-empty"><h3>Keine Artikel gefunden</h3><p>Suchbegriff oder Filter anpassen.</p></div>';
  }
  $('#view-hist').addEventListener('input', (e) => {
    if (e.target.id === 'hist-q') { clearTimeout(qTimer); qTimer = setTimeout(() => { histQ = e.target.value.trim(); renderHistList(); }, 120); }
  });
  $('#view-hist').addEventListener('change', (e) => {
    if (e.target.id === 'hist-only') { histOnlyChanged = e.target.checked; renderHistList(); }
    if (e.target.id === 'hist-sort') { histSort = e.target.value; renderHistList(); }
  });
  $('#view-hist').addEventListener('click', async (e) => {
    if (e.target.closest('#hist-upload')) { $('#hist-file-input').click(); return; }
    const rb = e.target.closest('[data-hrange]');
    if (rb) {
      setRange(rb.dataset.hrange);
      for (const b of $$('#view-hist [data-hrange]')) b.setAttribute('aria-pressed', b.dataset.hrange === histRange);
      renderHistList();
      return;
    }
    const tr = e.target.closest('tr[data-skey]');
    if (tr) openSeries(tr.dataset.skey);
  });
  $('#view-hist').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr[data-skey]')) openSeries(e.target.dataset.skey); });

  /* ---------- Daten: gespeicherte Wochen verwalten ---------- */
  const dlgHD = $('#dlg-hist-data');
  const dShort = (iso) => { const [, m, d] = iso.split('-'); return `${d}.${m}.`; };
  const savedShort = (iso) => (iso ? new Date(iso).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : '');
  function renderHistData() {
    const H = hist;
    const rows = H.weeks.slice().reverse().map((w) => {
      const r = C.isoWeekRange(w.week, w.year);
      const items = w.items || [];
      const priced = items.filter((it) => it.price && it.price.status === 'value').length;
      const pub = w.origin !== 'Import';
      return `<tr>
        <td class="hd-wk">${esc(wkLong(w))}</td>
        <td class="hd-range">${esc(dShort(r.start))}–${esc(dShort(r.end))}</td>
        <td class="num">${fmtInt.format(items.length)}</td>
        <td class="num hd-priced">${fmtInt.format(priced)}</td>
        <td class="hd-src"><span class="hd-orig${pub ? ' pub' : ''}">${pub ? 'Veröffentlichung' : 'Import'}</span>${w.source ? `<div class="sub" title="${esc(w.source)}">${esc(w.source)}</div>` : ''}</td>
        <td class="hd-saved" title="${esc(dateTime(w.savedAt))}">${esc(savedShort(w.savedAt))}</td>
        <td class="hd-act"><button type="button" class="btn icon ghost sm" data-hdel="${esc(w.id)}" aria-label="${esc(wkLong(w))} aus dem Preisverlauf entfernen" title="Woche entfernen">${icon('trash')}</button></td>
      </tr>`;
    }).join('');
    const first = H.weeks[0], last = H.weeks[H.weeks.length - 1];
    $('#hist-data-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="hd-title">Daten im Preisverlauf</h2><p>${H.weeks.length ? `${plural(H.weeks.length, 'Woche', 'Wochen')} · ${esc(wkLong(first))} – ${esc(wkLong(last))}. Jede Veröffentlichung wird automatisch übernommen; eine erneut hochgeladene Woche ersetzt die vorhandene.` : 'Noch keine Wochen gespeichert.'}</p></div>
        <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">${H.weeks.length ? `<table class="etab hdtab"><thead><tr><th>Woche</th><th class="hd-range">Zeitraum</th><th class="num">Artikel</th><th class="num hd-priced">mit Preis</th><th class="hd-src">Herkunft</th><th class="hd-saved">Gespeichert</th><th class="hd-act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${rows}</tbody></table>` : ''}</div>
      <div class="dlg-foot"><button type="button" class="btn" data-hd="upload">${icon('upload')}Alte Angebote hochladen</button><span class="spacer"></span><button type="button" class="btn" data-close>Schließen</button></div>`;
  }
  $('#hist-data').addEventListener('click', () => { if (!hist) return; renderHistData(); dlgHD.showModal(); });
  dlgHD.addEventListener('click', async (e) => {
    if (e.target === dlgHD || e.target.closest('[data-close]')) { dlgHD.close(); return; }
    if (e.target.closest('[data-hd="upload"]')) { dlgHD.close(); $('#hist-file-input').click(); return; }
    const del = e.target.closest('[data-hdel]');
    if (!del || ro) return;
    const w = hist.weeks.find((x) => x.id === del.dataset.hdel);
    if (!w || !(await confirmBox('Woche entfernen?', `${esc(wkLong(w))} wird aus dem Preisverlauf entfernt. Die Excel-Datei kann jederzeit erneut hochgeladen werden.`, 'Entfernen', true))) return;
    try { await api('history_delete', { body: { id: w.id } }); await loadHistory(true); renderHistView(); toast(`${wkLong(w)} entfernt.`); } catch (ex) { toast(ex.message); }
  });

  /* ---------- Detail: Diagramm + Wochentabelle ---------- */
  const dlgSeries = $('#dlg-series');
  function chartSVG(s, weeks, vals) {
    const W = 680, H = 240, l = 52, r = 34, t = 14, b = 34;
    const nums = vals.filter((v) => v != null);
    if (!nums.length) return '<p class="notice">In keiner Woche mit Preis.</p>';
    const vmin = Math.min(...nums), vmax = Math.max(...nums);
    const span0 = vmax - vmin || Math.max(0.5, vmax * 0.05);
    const raw = (span0 * 1.3) / 4, mag = 10 ** Math.floor(Math.log10(raw));
    const stepY = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((x) => x >= raw);
    let lo = Math.max(0, Math.floor((vmin - span0 * 0.15) / stepY) * stepY);
    let hi = Math.ceil((vmax + span0 * 0.15) / stepY) * stepY;
    if (hi === lo) hi = lo + stepY;
    const n = weeks.length;
    const x = (i) => (n === 1 ? (l + W - r) / 2 : l + (i * (W - l - r)) / (n - 1));
    const y = (v) => t + ((hi - v) * (H - t - b)) / (hi - lo);
    let grid = '';
    for (let v = lo; v <= hi + stepY / 1e6; v += stepY) {
      const yy = y(v).toFixed(1);
      grid += `<line class="gl" x1="${l}" x2="${W - r}" y1="${yy}" y2="${yy}"/><text class="yl" x="${l - 8}" y="${yy}" dy="0.32em" text-anchor="end">${fmtNum.format(Math.round(v * 100) / 100)}</text>`;
    }
    const step = Math.max(1, Math.ceil(n / 10));
    let xl = '';
    weeks.forEach((w, i) => { if (i % step === 0 || i === n - 1) xl += `<text class="xl" x="${x(i).toFixed(1)}" y="${H - 10}" text-anchor="middle">${esc(wkLabel(w))}</text>`; });
    let d = '', pen = false, dots = '';
    vals.forEach((v, i) => {
      if (v == null) { pen = false; return; }
      d += (pen ? 'L' : 'M') + x(i).toFixed(1) + ' ' + y(v).toFixed(1) + ' ';
      pen = true;
      dots += `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3.6"><title>${esc(wkLong(weeks[i]))}: ${fmtNum.format(v)} €/kg</title></circle>`;
    });
    return `<svg class="hchart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Preisverlauf ${esc(s.name)}">${grid}${xl}<path class="ln" d="${d}"/>${dots}</svg>`;
  }
  async function openSeries(key) {
    await loadHistory();
    const s = hist.series.find((x) => x.key === key);
    if (!s) return;
    const idx = rangeIdx(hist);
    const W = idx.map((i) => hist.weeks[i]);
    const x = statsFor(s, idx);
    const cur = s.inLatest ? s.cur : null;
    let prev = null;
    for (let i = idx[0] - 1; i >= 0; i--) if (s.vals[i] != null) { prev = s.vals[i]; break; }
    const rows = [];
    idx.forEach((wi) => {
      const w = hist.weeks[wi];
      const i = wi;
      const p = s.points[i];
      const v = s.vals[i];
      const ch = v != null && prev != null ? v - prev : null;
      if (v != null) prev = v;
      rows.push(`<tr${p ? '' : ' class="muted"'}><td>${esc(wkLong(w))}</td><td class="num">${p ? esc(priceShort(p.price)) : 'nicht im Angebot'}</td>
        <td class="num">${ch == null || Math.abs(ch) < 1e-9 ? '' : `<span class="delta ${ch > 0 ? 'up' : 'down'}">${fmtDelta(ch)}</span>`}</td>
        <td>${p && p.name !== s.name ? esc(p.name) : ''}${p && (p.altPrices || []).length ? `<span class="muted"> ${p.altPrices.map((a) => esc((a.label || '') + ': ' + priceShort(a))).join(' · ')}</span>` : ''}</td>
        <td class="muted">${p && p.group !== s.group ? esc(p.group) : ''}</td></tr>`);
    });
    $('#series-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="ser-title">${esc(s.name)}</h2><p>${s.code ? 'Art.-Nr. ' + esc(s.code) + ' · ' : ''}${esc(s.group)}${s.inLatest ? '' : ' · nicht mehr im Angebot'}</p></div>
        <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        <div class="ser-range">${rangeSeg()}<span class="muted">${esc(wkLong(W[0]))} – ${esc(wkLong(W[W.length - 1]))}${x.delta ? ` · Änderung <span class="delta ${x.delta > 0 ? 'up' : 'down'}">${fmtDelta(x.delta)} €</span>` : ''}</span></div>
        <div class="cmp-stats hstats">
          <div><span>Aktuell</span><strong>${cur ? esc(priceShort(cur.price)) : '—'}</strong></div>
          <div><span>Tiefster</span><strong>${x.min != null ? fmtNum.format(x.min) + ' €' : '—'}</strong></div>
          <div><span>Höchster</span><strong>${x.max != null ? fmtNum.format(x.max) + ' €' : '—'}</strong></div>
          <div><span>Durchschnitt</span><strong>${x.avg != null ? fmtNum.format(Math.round(x.avg * 100) / 100) + ' €' : '—'}</strong></div>
        </div>
        ${chartSVG(s, W, x.vals)}
        <h3 class="d-h"><span>Wochenwerte</span><span>${plural(x.weeksCount, 'Woche', 'Wochen')} im Angebot · ${plural(x.changes, 'Preisänderung', 'Preisänderungen')}</span></h3>
        <table class="etab wtab"><thead><tr><th>Woche</th><th class="num">Preis</th><th class="num">Änderung</th><th>Abweichende Bezeichnung / Zusatzpreise</th><th>Gruppe</th></tr></thead>
        <tbody>${rows.reverse().join('')}</tbody></table>
      </div>`;
    dlgSeries.dataset.skey = key;
    if (!dlgSeries.open) dlgSeries.showModal();
  }
  dlgSeries.addEventListener('click', (e) => {
    const rb = e.target.closest('[data-hrange]');
    if (!rb) return;
    setRange(rb.dataset.hrange);
    openSeries(dlgSeries.dataset.skey);
    if (currentView === 'hist' && $('#hist-list')) {
      for (const b of $$('#view-hist [data-hrange]')) b.setAttribute('aria-pressed', b.dataset.hrange === histRange);
      renderHistList();
    }
  });

  /* Verlauf im Artikel-Dialog des Editors */
  async function fillItemHistory(it) {
    const slot = $('#item-hist');
    if (!slot) return;
    slot.innerHTML = '<span>Preisverlauf</span><div class="muted" style="font-size:13px">wird geladen …</div>';
    let H;
    try { H = await loadHistory(); } catch { slot.innerHTML = ''; return; }
    if (!$('#item-hist') || itemId !== it.id) return;
    const g = gById(it.groupId);
    const key = seriesKey({ code: it.code, name: it.name, group: g ? g.name : '' }, H.dup);
    const s = H.series.find((x) => x.key === key);
    if (!s || s.weeksCount < 1) { slot.innerHTML = '<span>Preisverlauf</span><div class="muted" style="font-size:13px">Noch keine Werte aus früheren Wochen.</div>'; return; }
    const x = statsFor(s, rangeIdx(H));
    const rl = (RANGES.find((r) => r[0] === histRange) || RANGES[2])[2];
    slot.innerHTML = `<span>Preisverlauf · ${esc(rl)}</span><div class="item-hist">${sparkSVG(x.vals, 160, 34)}
      <div class="ih-txt">${plural(x.weeksCount, 'Woche', 'Wochen')}${x.min != null ? ` · ${fmtNum.format(x.min)} – ${fmtNum.format(x.max)} €/kg` : ''}${x.delta ? ` · Änderung <span class="delta ${x.delta > 0 ? 'up' : 'down'}">${fmtDelta(x.delta)}</span>` : ''}</div>
      <button type="button" class="btn sm ghost" data-ia="hist-open" data-skey="${esc(s.key)}">${icon('chart', 'sm')}Verlauf öffnen</button></div>`;
  }
  dlgItem.addEventListener('click', (e) => {
    const b = e.target.closest('[data-ia="hist-open"]');
    if (!b) return;
    dlgItem.close();
    setView('hist');
    openSeries(b.dataset.skey);
  });

  /* ---------- Alte Angebote hochladen (mehrere Dateien) ---------- */
  const dlgHI = $('#dlg-hist-import');
  let hiEntries = [];
  $('#hist-file-input').addEventListener('change', (e) => { const files = [...e.target.files]; e.target.value = ''; if (files.length) histImportFiles(files); });
  async function histImportFiles(files) {
    if (ro) return;
    const base = dlgHI.open ? hiEntries.filter((en) => en.status !== 'gespeichert') : [];
    const added = files.map((f) => ({ file: f, status: 'lesen' }));
    hiEntries = base.concat(added);
    renderHistImport();
    if (!dlgHI.open) dlgHI.showModal();
    try { await loadHistory(); } catch { /* Liste ggf. leer */ }
    for (const en of added) {
      try {
        if (!/\.(xlsx|xlsm)$/i.test(en.file.name)) throw new Error('keine .xlsx-Datei');
        const m = C.parseOfferWorkbook(await C.xlsxReadWorkbook(await en.file.arrayBuffer()), en.file.name);
        if (!m.items.length) throw new Error('keine Artikel gefunden');
        const gn = new Map(m.groups.map((g) => [g.id, g.name]));
        en.items = m.items.map((it) => {
          const row = { code: it.code, name: it.name, group: gn.get(it.groupId) || '', category: it.category, price: it.price };
          if (it.altPrices && it.altPrices.length) row.altPrices = it.altPrices;
          return row;
        });
        en.week = m.meta.week; en.year = m.meta.year;
        en.warn = m.issues.filter((x) => x.level === 'warn').length;
        en.status = 'ok';
      } catch (ex) { en.status = 'fehler'; en.error = ex.message; }
      renderHistImport();
    }
  }
  function hiFlags() {
    const seen = new Map();
    hiEntries.forEach((en, i) => {
      en.dupOf = null;
      if (en.status !== 'ok' || !en.week || !en.year) return;
      const id = `${en.year}-${String(en.week).padStart(2, '0')}`;
      en.id = id;
      if (seen.has(id)) hiEntries[seen.get(id)].dupOf = i;
      seen.set(id, i);
      en.exists = !!(hist && hist.weeks.some((w) => w.id === id));
    });
  }
  function renderHistImport() {
    hiFlags();
    const ready = hiEntries.filter((en) => en.status === 'ok' && en.week && en.year && en.dupOf == null);
    const rows = hiEntries.map((en, i) => {
      let st;
      if (en.status === 'lesen') st = '<span class="muted">wird gelesen …</span>';
      else if (en.status === 'fehler') st = `<span class="st-err">${esc(en.error)}</span>`;
      else if (en.status === 'gespeichert') st = '<span class="st-ok">übernommen</span>';
      else if (!en.week || !en.year) st = '<span class="st-err">KW/Jahr eintragen</span>';
      else if (en.dupOf != null) st = '<span class="st-warn">doppelt – spätere Datei zählt</span>';
      else if (en.exists) st = '<span class="st-warn">ersetzt vorhandene Woche</span>';
      else st = `<span class="st-ok">neu</span>${en.warn ? ` <span class="muted">· ${en.warn} Hinweis${en.warn === 1 ? '' : 'e'}</span>` : ''}`;
      const editable = en.status === 'ok';
      return `<tr data-i="${i}"><td class="hi-file" title="${esc(en.file.name)}">${esc(en.file.name)}</td>
        <td><input class="in num" data-hf="week" type="number" min="1" max="53" value="${esc(en.week ?? '')}" aria-label="Kalenderwoche"${editable ? '' : ' disabled'}></td>
        <td><input class="in num" data-hf="year" type="number" min="2000" max="2100" value="${esc(en.year ?? '')}" aria-label="Jahr"${editable ? '' : ' disabled'}></td>
        <td class="num">${en.items ? fmtInt.format(en.items.length) : ''}</td><td>${st}</td></tr>`;
    }).join('');
    const busy = hiEntries.some((en) => en.status === 'lesen' || en.status === 'speichert');
    $('#hist-import-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="hi-title">Alte Angebote hochladen</h2><p>Jede Datei wird als eine Woche im Preisverlauf gespeichert. Kalenderwoche und Jahr werden aus der Tabelle oder dem Dateinamen erkannt und lassen sich hier korrigieren. Das aktuelle Angebot bleibt unverändert.</p></div>
        <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body"><table class="etab hitab"><thead><tr><th>Datei</th><th class="num">KW</th><th class="num">Jahr</th><th class="num">Artikel</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table>
        <p class="hint" id="hi-progress"></p></div>
      <div class="dlg-foot"><button type="button" class="btn" data-hi="more">Weitere Dateien</button><span class="spacer"></span><button type="button" class="btn" data-close>Schließen</button>
        <button type="button" class="btn primary" data-hi="save"${ready.length && !busy ? '' : ' disabled'}>${icon('check')}${ready.length === 1 ? '1 Woche übernehmen' : `${ready.length} Wochen übernehmen`}</button></div>`;
  }
  dlgHI.addEventListener('change', (e) => {
    const tr = e.target.closest('tr[data-i]');
    if (!tr || !e.target.dataset.hf) return;
    const n = parseInt(e.target.value, 10);
    hiEntries[+tr.dataset.i][e.target.dataset.hf] = Number.isInteger(n) ? n : null;
    renderHistImport();
  });
  dlgHI.addEventListener('click', async (e) => {
    if (e.target === dlgHI || e.target.closest('[data-close]')) { dlgHI.close(); return; }
    const a = e.target.closest('[data-hi]')?.dataset.hi;
    if (a === 'more') { $('#hist-file-input').click(); return; }
    if (a !== 'save') return;
    const todo = hiEntries.filter((en) => en.status === 'ok' && en.week && en.year && en.dupOf == null && en.week >= 1 && en.week <= 53);
    let done = 0, failed = 0;
    for (const en of todo) {
      en.status = 'speichert';
      $('#hi-progress').textContent = `Speichere ${done + failed + 1} von ${todo.length} …`;
      try { await api('history_import', { body: { week: en.week, year: en.year, source: en.file.name, items: en.items } }); en.status = 'gespeichert'; done++; }
      catch (ex) { en.status = 'fehler'; en.error = ex.message; failed++; }
    }
    try { await loadHistory(true); } catch { /* ignore */ }
    renderHistImport();
    $('#hi-progress').textContent = `${plural(done, 'Woche', 'Wochen')} übernommen${failed ? `, ${failed} fehlgeschlagen` : ''}.`;
    if (currentView === 'hist') renderHistView(); else setView('hist');
    toast(`${plural(done, 'Woche', 'Wochen')} in den Preisverlauf übernommen.`);
  });
  window.addEventListener('drop', (e) => {
    if (currentView !== 'hist' || !model || ro) return;
    const files = [...(e.dataTransfer?.files || [])];
    if (files.length) { e.preventDefault(); e.stopImmediatePropagation(); histImportFiles(files); }
  }, true);

  /* ======================= Nutzerverwaltung (Administrator) ======================= */
  let users = null;
  const ROLE_DESC = {
    admin: 'Alles, zusätzlich Nutzerverwaltung und Protokoll',
    editor: 'Angebot bearbeiten, importieren, veröffentlichen, Preisverlauf pflegen',
    viewer: 'Eingabebereich und Preisverlauf nur ansehen',
  };
  const roleBadge = (r) => `<span class="role-b r-${esc(r)}">${esc(ROLE_LABEL[r] || r)}</span>`;
  async function renderUsersView() {
    const host = $('#view-users');
    if (!users) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Nutzer werden geladen …</div>';
    try { users = (await api('users')).users; } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    const order = { admin: 0, editor: 1, viewer: 2 };
    const list = users.slice().sort((a, b) => (b.active - a.active) || order[a.role] - order[b.role] || a.name.localeCompare(b.name, 'de'));
    const rows = list.map((u) => `<tr data-uid="${esc(u.id)}" tabindex="0" class="${u.active ? '' : 'inactive'}">
        <td class="u-name"><div class="nm">${esc(u.name)}${u.id === me.id ? ' <span class="muted">(Sie)</span>' : ''}</div><div class="sub uname">${esc(u.username)}</div></td>
        <td>${roleBadge(u.role)}</td>
        <td class="u-st">${u.active ? '<span class="st-ok">aktiv</span>' : '<span class="st-err">deaktiviert</span>'}${u.mustChange ? '<div class="sub">muss Passwort ändern</div>' : ''}</td>
        <td class="u-last">${u.lastLogin ? esc(dateTime(u.lastLogin)) : '<span class="muted">noch nie</span>'}</td>
        <td class="u-act"><button type="button" class="btn sm" data-uedit="${esc(u.id)}">Bearbeiten</button></td>
      </tr>`).join('');
    host.innerHTML = `
      <div class="ed-toolbar">
        <span class="ed-hint">${plural(users.filter((u) => u.active).length, 'aktiver Zugang', 'aktive Zugänge')}${users.some((u) => !u.active) ? ` · ${users.filter((u) => !u.active).length} deaktiviert` : ''}</span>
        <button type="button" class="btn primary" id="user-add">${icon('plus')}Nutzer anlegen</button>
      </div>
      <div class="gcard"><table class="etab utab"><thead><tr><th>Name / Benutzername</th><th>Rolle</th><th class="u-st">Status</th><th class="u-last">Letzte Anmeldung</th><th class="u-act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${rows}</tbody></table></div>
      <dl class="role-legend">${['admin', 'editor', 'viewer'].map((r) => `<div><dt>${roleBadge(r)}</dt><dd>${esc(ROLE_DESC[r])}</dd></div>`).join('')}</dl>`;
  }
  $('#view-users').addEventListener('click', (e) => {
    if (e.target.closest('#user-add')) { openUser(null); return; }
    const tr = e.target.closest('tr[data-uid]');
    if (tr) openUser(tr.dataset.uid);
  });
  $('#view-users').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr[data-uid]')) openUser(e.target.dataset.uid); });

  const dlgUser = $('#dlg-user');
  let editUid = null;
  function genPassword() {
    const chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const a = new Uint32Array(14);
    crypto.getRandomValues(a);
    return [...a].map((x) => chars[x % chars.length]).join('').replace(/(.{4})(?=.)/g, '$1-').slice(0, 14);
  }
  function openUser(id) {
    const u = id ? users.find((x) => x.id === id) : null;
    editUid = id;
    const self = u && u.id === me.id;
    $('#user-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="us-title">${u ? 'Nutzer bearbeiten' : 'Nutzer anlegen'}</h2><p>${u ? `Angelegt ${esc(dateTime(u.created))}${u.createdBy ? ' von ' + esc(u.createdBy) : ''}` : 'Der Nutzer meldet sich mit Benutzername und Passwort an.'}</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body form-grid two">
        <label class="fld"><span>Name</span><input name="name" value="${esc(u ? u.name : '')}" maxlength="80" required placeholder="z. B. Max Mustermann"></label>
        <label class="fld"><span>Benutzername</span><input name="username" value="${esc(u ? u.username : '')}" maxlength="32" autocapitalize="none" spellcheck="false" placeholder="z. B. mmustermann"${u ? ' disabled' : ' required'}></label>
        <div class="fld span2"><span>Rolle</span>
          <div class="role-pick">${['admin', 'editor', 'viewer'].map((r) => `<label class="role-opt"><input type="radio" name="role" value="${r}"${(u ? u.role : 'editor') === r ? ' checked' : ''}${self ? ' disabled' : ''}><span><strong>${esc(ROLE_LABEL[r])}</strong><small>${esc(ROLE_DESC[r])}</small></span></label>`).join('')}</div>
        </div>
        <label class="check span2"><input type="checkbox" name="active"${!u || u.active ? ' checked' : ''}${self ? ' disabled' : ''}> Zugang aktiv${self ? ' <span class="muted">(eigener Zugang)</span>' : ''}</label>
        <div class="fld span2"><span>${u ? 'Neues Passwort setzen <small class="muted">(leer lassen = unverändert)</small>' : 'Passwort'}</span>
          <div class="pw-row"><input name="password" type="text" autocomplete="new-password" minlength="10" maxlength="200" placeholder="mindestens 10 Zeichen"${u ? '' : ' required'}><button type="button" class="btn" data-uact="gen">Vorschlag</button></div>
        </div>
        ${self ? '' : `<label class="check span2"><input type="checkbox" name="mustChange" checked> Nutzer muss das Passwort bei der nächsten Anmeldung ändern</label>`}
        <p class="form-err span2" id="user-err" role="alert"></p>
      </div>
      <div class="dlg-foot">
        <span class="left">${u && !self ? `<button type="button" class="btn sm ghost" data-uact="del" style="color:var(--accent)">${icon('trash', 'sm')}Nutzer löschen</button>` : ''}</span>
        <button type="button" class="btn" data-close>Abbrechen</button>
        <button type="submit" class="btn primary">${u ? 'Speichern' : 'Nutzer anlegen'}</button>
      </div>`;
    dlgUser.showModal();
    $('#user-body [name="name"]').focus();
  }
  dlgUser.addEventListener('click', async (e) => {
    const a = e.target.closest('[data-uact]')?.dataset.uact;
    if (a === 'gen') { const i = $('#user-body [name="password"]'); i.value = genPassword(); i.select(); return; }
    if (a === 'del') {
      const u = users.find((x) => x.id === editUid);
      if (!(await confirmBox('Nutzer löschen?', `Der Zugang „${esc(u.username)}“ (${esc(u.name)}) wird gelöscht. Die Einträge im Protokoll bleiben erhalten. Alternativ können Sie den Zugang nur deaktivieren.`, 'Löschen', true))) return;
      try { await api('user_delete', { body: { id: u.id } }); dlgUser.close(); toast(`Nutzer „${u.username}“ gelöscht.`); renderUsersView(); } catch (ex) { $('#user-err').textContent = ex.message; }
    }
  });
  $('#user-body').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target, err = $('#user-err');
    err.textContent = '';
    const pw = f.password.value.trim();
    if (pw && pw.length < 10) { err.textContent = 'Das Passwort muss mindestens 10 Zeichen lang sein.'; return; }
    const u = editUid ? users.find((x) => x.id === editUid) : null;
    const body = {
      id: editUid || '', name: f.name.value.trim(), username: u ? u.username : f.username.value.trim(),
      role: (f.querySelector('[name="role"]:checked') || {}).value || (u && u.role), active: f.active.checked,
      password: pw, mustChange: f.mustChange ? f.mustChange.checked : false,
    };
    const btn = f.querySelector('[type="submit"]');
    btn.disabled = true;
    try {
      await api('user_save', { body });
      dlgUser.close();
      toast(u ? `Änderungen an „${u.username}“ gespeichert.` : `Nutzer „${body.username.toLowerCase()}“ angelegt.`);
      if (pw) toast(`${u ? 'Neues Passwort für' : 'Nutzer angelegt –'} „${(u ? u.username : body.username).toLowerCase()}“: Passwort jetzt sicher weitergeben.`, 6000);
      renderUsersView();
    } catch (ex) { err.textContent = ex.message; } finally { btn.disabled = false; }
  });

  /* ======================= Protokoll (Administrator) ======================= */
  let logData = null, logMonth = '', logUser = '', logType = '', logQ = '';
  const logOpen = new Set();
  const LOG_TYPES = [
    ['', 'Alle Vorgänge'],
    ['offer', 'Angebot bearbeitet / importiert'],
    ['publish', 'Veröffentlichungen'],
    ['history', 'Preisverlauf'],
    ['auth', 'Anmeldungen'],
    ['user', 'Nutzerverwaltung'],
  ];
  const typeOf = (a) => ({ draft: 'offer', import: 'offer', discard: 'offer', publish: 'publish', history: 'history', login: 'auth', logout: 'auth', login_fail: 'auth', password: 'auth', setup: 'user', user: 'user' }[a] || '');
  const ACTION_LABEL = { draft: 'Entwurf bearbeitet', import: 'Entwurf ersetzt', discard: 'Entwurf verworfen', publish: 'Veröffentlicht', history: 'Preisverlauf', login: 'Anmeldung', logout: 'Abmeldung', login_fail: 'Anmeldung fehlgeschlagen', password: 'Passwort', setup: 'Einrichtung', user: 'Nutzerverwaltung' };
  function draftSummary(d) {
    let p = 0, n = 0, r = 0, o = 0;
    for (const c of d || []) { const f = c.k.split('|')[1]; if (f === 'price') p++; else if (f === '+') n++; else if (f === '-') r++; else o++; }
    const parts = [];
    if (p) parts.push(`${plural(p, 'Preis', 'Preise')} geändert`);
    if (n) parts.push(`${plural(n, 'Artikel', 'Artikel')} neu`);
    if (r) parts.push(`${plural(r, 'Artikel', 'Artikel')} entfernt`);
    if (o) parts.push(plural(o, 'weitere Änderung', 'weitere Änderungen'));
    return parts.join(', ');
  }
  const entryText = (e) => (e.a === 'draft' ? `Entwurf bearbeitet: ${draftSummary(e.d)}` : e.s);
  async function loadLog(month) {
    logData = await api('log', { query: month ? '&month=' + encodeURIComponent(month) : '' });
    logMonth = logData.month;
  }
  const monthLabel = (m) => { const [y, mo] = m.split('-'); return new Date(Date.UTC(+y, +mo - 1, 15)).toLocaleDateString('de-DE', { month: 'long', year: 'numeric' }); };
  async function renderLogView(reload = true) {
    const host = $('#view-log');
    if (reload) {
      if (!logData) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Protokoll wird geladen …</div>';
      try { await loadLog(logMonth); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    }
    const months = logData.months.includes(logMonth) ? logData.months : [logMonth, ...logData.months];
    const names = [...new Map(logData.entries.filter((e) => e.u).map((e) => [e.u, e.n || e.u])).entries()].sort((a, b) => a[1].localeCompare(b[1], 'de'));
    host.innerHTML = `
      <div class="ed-toolbar">
        <div class="search">${icon('search')}<input id="log-q" type="search" autocomplete="off" placeholder="Suchen: Artikel, Nummer, Text …" aria-label="Protokoll durchsuchen" value="${esc(logQ)}"></div>
        <label class="select"><span class="sr-only">Monat</span><select id="log-month">${months.map((m) => `<option value="${m}"${m === logMonth ? ' selected' : ''}>${esc(monthLabel(m))}</option>`).join('')}</select>${icon('chev', 'sm')}</label>
        <label class="select"><span class="sr-only">Nutzer</span><select id="log-user"><option value="">Alle Nutzer</option>${names.map(([u, n]) => `<option value="${esc(u)}"${u === logUser ? ' selected' : ''}>${esc(n)} (${esc(u)})</option>`).join('')}</select>${icon('chev', 'sm')}</label>
        <label class="select"><span class="sr-only">Vorgang</span><select id="log-type">${LOG_TYPES.map(([v, l]) => `<option value="${v}"${v === logType ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>${icon('chev', 'sm')}</label>
        <span class="ed-hint" id="log-count"></span>
        <button type="button" class="btn" id="log-csv">${icon('upload')}CSV</button>
      </div>
      <div id="log-list"></div>`;
    renderLogList();
  }
  function logFiltered() {
    const toks = fold(logQ).split(/\s+/).filter(Boolean);
    return logData.entries.filter((e) => {
      if (logUser && e.u !== logUser) return false;
      if (logType && typeOf(e.a) !== logType) return false;
      if (!toks.length) return true;
      const hay = fold([e.u, e.n, entryText(e), ...(e.d || []).map((c) => [c.code, c.name, c.f, c.from, c.to].join(' '))].join(' '));
      return toks.every((t) => hay.includes(t));
    });
  }
  function changesTable(d) {
    if (!d || !d.length) return '';
    return `<table class="ctab"><thead><tr><th>Art.-Nr.</th><th>Artikel / Bereich</th><th>Feld</th><th>Vorher</th><th>Nachher</th></tr></thead><tbody>${d.map((c) => {
      const f = c.k.split('|')[1];
      const cls = f === 'price' ? 'ch-price' : f === '+' ? 'ch-new' : f === '-' ? 'ch-del' : '';
      return `<tr class="${cls}"><td class="ch-code">${esc(c.code || '')}</td><td>${esc(c.name)}</td><td>${esc(c.f)}</td><td class="c-from">${c.from === '' ? '<span class="muted">—</span>' : esc(c.from)}</td><td class="c-to">${c.to === '' ? '<span class="muted">—</span>' : esc(c.to)}</td></tr>`;
    }).join('')}</tbody></table>`;
  }
  function renderLogList() {
    const list = logFiltered();
    $('#log-count').textContent = plural(list.length, 'Eintrag', 'Einträge');
    const host = $('#log-list');
    if (!list.length) { host.innerHTML = `<div class="ed-empty"><h3>Keine Einträge</h3><p>${logData.entries.length ? 'Filter anpassen oder anderen Monat wählen.' : 'In diesem Monat wurde noch nichts protokolliert.'}</p></div>`; return; }
    let day = '';
    const rows = [];
    for (const e of list) {
      const d = new Date(e.t);
      const dl = d.toLocaleDateString('de-DE', { weekday: 'long', day: '2-digit', month: '2-digit', year: 'numeric' });
      if (dl !== day) { day = dl; rows.push(`<tr class="lday"><td colspan="4">${esc(dl)}</td></tr>`); }
      const key = e.t + '|' + e.u + '|' + e.a;
      const hasD = e.d && e.d.length;
      const isOpen = logOpen.has(key);
      rows.push(`<tr class="lrow t-${esc(typeOf(e.a))}${e.a === 'login_fail' ? ' warn' : ''}${hasD ? ' has-d' : ''}" data-key="${esc(key)}"${hasD ? ' tabindex="0"' : ''}>
        <td class="l-time">${esc(d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }))}</td>
        <td class="l-user">${e.u ? `<div class="nm">${esc(e.n || e.u)}</div><div class="sub uname">${esc(e.u)}</div>` : '<span class="muted">—</span>'}</td>
        <td class="l-act"><span class="l-kind">${esc(ACTION_LABEL[e.a] || e.a)}</span><div>${esc(entryText(e))}</div></td>
        <td class="l-more">${hasD ? `<button type="button" class="btn sm ghost" data-ltoggle aria-expanded="${isOpen}">${isOpen ? 'Weniger' : `Details (${e.d.length})`}</button>` : `<span class="sub" title="IP-Adresse">${esc(e.ip || '')}</span>`}</td>
      </tr>`);
      if (hasD && isOpen) rows.push(`<tr class="ldet"><td></td><td colspan="3">${changesTable(e.d)}<div class="sub">IP-Adresse ${esc(e.ip || '—')}</div></td></tr>`);
    }
    host.innerHTML = `<div class="gcard"><table class="etab ltab"><thead><tr><th class="l-time">Zeit</th><th class="l-user">Nutzer</th><th>Vorgang</th><th class="l-more"><span class="sr-only">Details</span></th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
  }
  $('#view-log').addEventListener('input', (e) => {
    if (e.target.id === 'log-q') { clearTimeout(qTimer); qTimer = setTimeout(() => { logQ = e.target.value.trim(); renderLogList(); }, 150); }
  });
  $('#view-log').addEventListener('change', async (e) => {
    if (e.target.id === 'log-month') { logMonth = e.target.value; logUser = ''; await renderLogView(true); }
    if (e.target.id === 'log-user') { logUser = e.target.value; renderLogList(); }
    if (e.target.id === 'log-type') { logType = e.target.value; renderLogList(); }
  });
  $('#view-log').addEventListener('click', (e) => {
    if (e.target.closest('#log-csv')) { logCSV(); return; }
    const tr = e.target.closest('tr.lrow.has-d');
    if (!tr) return;
    const k = tr.dataset.key;
    if (logOpen.has(k)) logOpen.delete(k); else logOpen.add(k);
    renderLogList();
  });
  $('#view-log').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr.lrow.has-d')) e.target.click(); });
  function logCSV() {
    const q = (v) => { const t = String(v ?? ''); return /[;"\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t; };
    const lines = [['Datum', 'Uhrzeit', 'Benutzername', 'Name', 'Vorgang', 'Beschreibung', 'Art.-Nr.', 'Artikel', 'Feld', 'Vorher', 'Nachher', 'IP-Adresse'].join(';')];
    for (const e of logFiltered()) {
      const d = new Date(e.t);
      const base = [d.toLocaleDateString('de-DE'), d.toLocaleTimeString('de-DE'), e.u, e.n, ACTION_LABEL[e.a] || e.a, entryText(e)];
      if (e.d && e.d.length) for (const c of e.d) lines.push([...base, c.code, c.name, c.f, c.from, c.to, e.ip].map(q).join(';'));
      else lines.push([...base, '', '', '', '', '', e.ip].map(q).join(';'));
    }
    const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `Protokoll_${logMonth}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 2000);
  }

  /* ======================= Start ======================= */
  (async function boot() {
    try {
      const s = await api('status');
      company = s.company || '';
      $$('[data-company]').forEach((el) => { el.textContent = company; el.hidden = !company; });
      if (s.setupRequired) { showAuth('setup'); return; }
      if (!s.loggedIn) { showAuth('login'); return; }
      csrf = s.csrf;
      me = s.user;
      if (me.mustChange) { try { await api('logout', { body: {} }); } catch { /* ignore */ } me = null; showAuth('login'); return; }
      await openEditor();
    } catch (e) {
      document.body.innerHTML = `<main class="auth"><div class="auth-card"><h1 style="margin:0;font-size:18px">Eingabebereich nicht erreichbar</h1><p class="auth-intro">${esc(e.message)}</p><p class="auth-intro">Die Seite muss über den Webserver aufgerufen werden, PHP muss aktiv sein.</p></div></main>`;
    }
  })();
})();
