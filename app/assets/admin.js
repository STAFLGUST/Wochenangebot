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
  /* CSV-Zelle: Trennzeichen maskieren und Formel-Injection verhindern (=, +, -, @ am Anfang) */
  const csvCell = (v) => {
    let t = String(v ?? '');
    if (/^[=+\-@\t\r]/.test(t) && !/^-?\d[\d.,]*$/.test(t)) t = "'" + t;
    return /[;"\r\n]/.test(t) ? '"' + t.replace(/"/g, '""') + '"' : t;
  };
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
    if (res.status === 401 && !['login', 'login_2fa', 'setup', 'change_password'].includes(action)) {
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
  let authCtx = null;                              // { prevUser, expired } während einer laufenden Anmeldung
  function showAuth(mode) {
    authMode = mode;
    $('#screen-auth').hidden = false;
    if (mode !== 'expired' && !(authCtx && authCtx.expired)) $('#screen-editor').hidden = true;
    const setup = mode === 'setup', newpw = mode === 'newpw', code = mode === 'code', tf = mode === 'twofa';
    $('#auth-intro').textContent = setup
      ? 'Ersteinrichtung: Legen Sie den ersten Administrator-Zugang an (Passwort mindestens 10 Zeichen). Weitere Nutzer legen Sie danach unter „Nutzer“ an.'
      : newpw ? `Hallo ${me ? me.name : ''}, bitte legen Sie jetzt ein eigenes Passwort fest.`
        : code ? 'Bitte den 6-stelligen Code aus Ihrer Authenticator-App eingeben – oder einen Ihrer Wiederherstellungscodes.'
          : tf ? `Hallo ${me ? me.name : ''}, für Ihren Zugang ist die Zwei-Faktor-Anmeldung vorgeschrieben. Bitte richten Sie sie jetzt ein.`
            : mode === 'expired' ? 'Ihre Sitzung ist abgelaufen. Bitte erneut anmelden – Ihre Änderungen bleiben erhalten.'
              : 'Bitte melden Sie sich mit Ihrem Benutzernamen an.';
    const hideUser = newpw || code || tf;
    $('#au-user-wrap').hidden = hideUser;
    $('#au-user').required = !hideUser;
    $('#au-name-wrap').hidden = !setup;
    $('#pw1').closest('label').hidden = code || tf;
    $('#pw1').required = !(code || tf);
    $('#pw2-wrap').hidden = !(setup || newpw);
    $('#au-code-wrap').hidden = !code;
    $('#au-code').required = code;
    $('#auth-twofa').hidden = !tf;
    $('#auth-submit').hidden = tf;
    $('#pw1-lbl').textContent = newpw ? 'Neues Passwort' : 'Passwort';
    $('#pw1').autocomplete = setup || newpw ? 'new-password' : 'current-password';
    $('#auth-submit').textContent = setup ? 'Zugang anlegen' : newpw ? 'Passwort speichern' : code ? 'Bestätigen' : 'Anmelden';
    $('#auth-err').textContent = '';
    $('#pw1').value = ''; $('#pw2').value = ''; $('#au-code').value = '';
    if (mode === 'expired' && me) $('#au-user').value = me.username;
    $('#screen-auth').classList.toggle('overlay', mode === 'expired' || !!(authCtx && authCtx.expired));
    if (tf) renderTwofaSetup($('#auth-twofa'), () => finishLogin());
    setTimeout(() => (code ? $('#au-code') : (newpw || $('#au-user').value) ? $('#pw1') : $('#au-user')).focus(), 30);
  }
  async function afterLogin(r, pw) {
    csrf = r.csrf;
    me = r.user;
    if (r.recoveryLeft != null) toast(`Mit Wiederherstellungscode angemeldet – noch ${r.recoveryLeft} Codes übrig. Bei Bedarf unter „Zwei-Faktor-Anmeldung“ neu einrichten.`, 8000);
    if (me.mustChange) { loginPw = pw; showAuth('newpw'); return; }
    if (me.needTwofa) { showAuth('twofa'); return; }
    await finishLogin();
  }
  async function finishLogin() {
    const ctx = authCtx || {};
    authCtx = null;
    $('#screen-auth').classList.remove('overlay');
    if (ctx.expired && model && ctx.prevUser === me.id) { $('#screen-auth').hidden = true; $('#screen-editor').hidden = false; applyRole(); if (!ro) saveNow(); }
    else await openEditor();
  }
  $('#auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (authMode === 'twofa') { $('#auth-twofa [data-tf="enable"]')?.click(); return; }
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
        if (me.needTwofa) showAuth('twofa'); else await finishLogin();
        return;
      }
      if (authMode === 'code') {
        const r = await api('login_2fa', { body: { code: $('#au-code').value.trim() } });
        await afterLogin(r, loginPw);
        return;
      }
      authCtx = { prevUser: me && me.id, expired: authMode === 'expired' };
      const r = await api(authMode === 'setup' ? 'setup' : 'login', { body: { username: $('#au-user').value.trim(), name: $('#au-name').value.trim(), password: pw } });
      if (r.need2fa) { loginPw = pw; showAuth('code'); return; }
      await afterLogin(r, pw);
    } catch (ex) {
      err.textContent = ex.message;
      if (authMode === 'code' && /Anmeldung ist abgelaufen|erneut anmelden/i.test(ex.message)) setTimeout(() => showAuth(authCtx && authCtx.expired ? 'expired' : 'login'), 1800);
    } finally {
      $('#auth-submit').disabled = false;
    }
  });

  /* Zwei-Faktor einrichten (Anmeldeschirm und Dialog) */
  async function renderTwofaSetup(host, onDone, password = '') {
    host.innerHTML = '<div class="loading"><div class="spinner"></div>Wird vorbereitet …</div>';
    let r;
    try { r = await api('twofa_begin', { body: { password } }); } catch (ex) { host.innerHTML = `<div class="err-box">${esc(ex.message)}</div>`; return; }
    let svg = '';
    try { const q = window.qrcode(0, 'M'); q.addData(r.uri); q.make(); svg = q.createSvgTag({ cellSize: 4, margin: 2, scalable: true }); } catch { svg = ''; }
    host.innerHTML = `<div class="tf-setup">
        <ol class="tf-steps"><li>Authenticator-App auf dem Handy öffnen (z. B. Microsoft Authenticator, Google Authenticator oder 2FAS) und diesen QR-Code scannen.</li><li>Den 6-stelligen Code aus der App hier eingeben.</li></ol>
        <div class="tf-qr" aria-label="QR-Code für die Authenticator-App">${svg}</div>
        <details class="tf-manual"><summary>QR-Code lässt sich nicht scannen?</summary><p>In der App „Schlüssel manuell eingeben“ wählen und diesen Schlüssel eintragen:</p><code class="tf-secret">${esc(r.secret.replace(/(.{4})/g, '$1 ').trim())}</code></details>
        <label class="fld"><span>Code aus der App</span><input data-tf="code" inputmode="numeric" autocomplete="one-time-code" maxlength="7" placeholder="123456"></label>
        <p class="form-err" data-tf="err" role="alert"></p>
        <button type="button" class="btn primary wide" data-tf="enable">Bestätigen und einschalten</button>
      </div>`;
    const input = host.querySelector('[data-tf="code"]');
    setTimeout(() => input.focus(), 30);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); host.querySelector('[data-tf="enable"]').click(); } });
    host.querySelector('[data-tf="enable"]').addEventListener('click', async (e) => {
      const btn = e.currentTarget, er = host.querySelector('[data-tf="err"]');
      er.textContent = '';
      btn.disabled = true;
      try {
        const res = await api('twofa_enable', { body: { code: input.value.trim() } });
        me = res.user;
        showRecovery(host, res.recovery, onDone);
      } catch (ex) { er.textContent = ex.message; btn.disabled = false; input.select(); }
    });
  }
  function showRecovery(host, codes, onDone) {
    const txt = `Wiederherstellungscodes – Wochenangebot ${company} (${me.username})\nJeder Code funktioniert genau einmal, falls das Handy nicht verfügbar ist.\n\n${codes.join('\n')}\n`;
    host.innerHTML = `<div class="tf-setup">
        <p class="tf-ok">${icon('check')} Zwei-Faktor-Anmeldung ist eingeschaltet.</p>
        <p class="hint" style="margin:0">Bewahren Sie diese <strong>Wiederherstellungscodes</strong> sicher auf (ausdrucken oder im Passwort-Manager). Jeder Code funktioniert einmal, falls Ihr Handy nicht verfügbar ist. Sie werden nur jetzt angezeigt.</p>
        <div class="tf-codes">${codes.map((c) => `<code>${esc(c)}</code>`).join('')}</div>
        <div class="row-actions" style="justify-content:flex-start"><button type="button" class="btn sm" data-tf="copy">${icon('copy', 'sm')}Kopieren</button><button type="button" class="btn sm" data-tf="dl">${icon('download', 'sm')}Als Datei speichern</button></div>
        <label class="check"><input type="checkbox" data-tf="ack"> Ich habe die Codes sicher aufbewahrt.</label>
        <button type="button" class="btn primary wide" data-tf="done" disabled>Weiter</button>
      </div>`;
    host.querySelector('[data-tf="ack"]').addEventListener('change', (e) => { host.querySelector('[data-tf="done"]').disabled = !e.target.checked; });
    host.querySelector('[data-tf="copy"]').addEventListener('click', async () => { try { await navigator.clipboard.writeText(txt); toast('Codes kopiert.'); } catch { toast('Kopieren nicht möglich – bitte als Datei speichern.'); } });
    host.querySelector('[data-tf="dl"]').addEventListener('click', () => {
      const a = document.createElement('a');
      a.href = URL.createObjectURL(new Blob([txt], { type: 'text/plain;charset=utf-8' }));
      a.download = `Wiederherstellungscodes_${me.username}.txt`;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(a.href), 2000);
    });
    host.querySelector('[data-tf="done"]').addEventListener('click', () => onDone());
  }
  /* Menü: eigene Zwei-Faktor-Anmeldung verwalten */
  function openTwofaDialog() {
    const d = $('#dlg-twofa');
    const head = `<div class="dlg-head"><div><h2 id="tf-title">Zwei-Faktor-Anmeldung</h2><p>Zusätzlich zum Passwort wird bei der Anmeldung ein Code aus einer Authenticator-App abgefragt.</p></div><button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>`;
    const done = () => { d.close(); toast('Zwei-Faktor-Anmeldung ist eingeschaltet.'); applyRole(); };
    if (!me.twofa) {
      $('#twofa-body').innerHTML = `${head}<div class="dlg-body" id="tf-host"></div>`;
      d.showModal();
      renderTwofaSetup($('#tf-host'), done);
      return;
    }
    $('#twofa-body').innerHTML = `${head}<div class="dlg-body" id="tf-host">
        <p class="tf-ok">${icon('check')} Eingeschaltet für <strong>${esc(me.username)}</strong>.</p>
        ${me.twofaRequired ? '<p class="hint">Für Ihre Rolle ist die Zwei-Faktor-Anmeldung vorgeschrieben.</p>' : ''}
        <div class="row-actions" style="justify-content:flex-start">
          <button type="button" class="btn" data-tfd="renew">Neu einrichten (neues Handy / neue Codes)</button>
          ${me.twofaRequired ? '' : '<button type="button" class="btn" data-tfd="off" style="color:var(--accent)">Ausschalten</button>'}
        </div>
        <div id="tf-off" hidden><label class="fld"><span>Aktuelles Passwort eingeben</span><input type="password" id="tf-pw" autocomplete="current-password"></label><p class="form-err" id="tf-err"></p><button type="button" class="btn primary" data-tfd="off-go">Ausschalten</button></div>
      </div>`;
    d.showModal();
  }
  $('#dlg-twofa').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-tfd]');
    if (!b) return;
    const a = b.dataset.tfd;
    if (a === 'renew' || a === 'off') {
      $('#tf-off').hidden = false;
      const go = $('#tf-off button');
      go.dataset.tfd = a === 'renew' ? 'renew-go' : 'off-go';
      go.textContent = a === 'renew' ? 'Neu einrichten' : 'Ausschalten';
      $('#tf-pw').focus();
    }
    if (a === 'renew-go') renderTwofaSetup($('#tf-host'), () => { $('#dlg-twofa').close(); toast('Zwei-Faktor-Anmeldung neu eingerichtet.'); }, $('#tf-pw').value);
    if (a === 'off-go') {
      try { const r = await api('twofa_disable', { body: { password: $('#tf-pw').value } }); me = r.user; $('#dlg-twofa').close(); toast('Zwei-Faktor-Anmeldung ausgeschaltet.'); }
      catch (ex) { $('#tf-err').textContent = ex.message; }
    }
  });

  /* Rolle auf die Oberfläche anwenden */
  function applyRole() {
    ro = !can('editor');
    document.body.classList.toggle('ro', ro);
    document.body.classList.toggle('is-admin', can('admin'));
    $('#vt-users').hidden = !can('admin');
    $('#vt-log').hidden = !can('admin');
    $('#vt-sec').hidden = !can('admin');
    $('#side-admin').hidden = !can('admin');
    $('#menu-user').innerHTML = me ? `<strong>${esc(me.name)}</strong><span>${esc(me.username)} · ${esc(ROLE_LABEL[me.role])}</span>` : '';
    if (!can('admin') && (currentView === 'users' || currentView === 'log' || currentView === 'sec')) setView('edit');
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
  /* Bezeichnungen/Herkunft vereinheitlichen: „frisch“ nur im Zustand, Marke „Fleischmeister“ in der Bezeichnung, Herkunft als Kürzel */
  function normalizeNames(m) {
    const gb = new Map(m.groups.map((g) => [g.id, g]));
    let n = 0;
    for (const it of m.items) if (C.normalizeItem(it, gb.get(it.groupId))) n++;
    return n;
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
    loadAux();
    if (ro) loadMaster().catch(() => {});
    if (!ro) {
      const n = normalizeNames(model);
      if (n) { saveNote = { type: 'cleanup', count: n }; changed({ render: true }); toast(`${plural(n, 'Artikel', 'Artikel')} vereinheitlicht (ohne „frisch“, Marke Fleischmeister, Herkunft als Kürzel). Zum Übernehmen veröffentlichen.`, 7000); }
      loadMaster().then(() => migrateMaster()).catch(() => {});
    }
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
    renderNoPrice();
    if (prevKey !== `${model.meta.year}-${model.meta.week}`) loadPrev().then(refreshAux, () => {});
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
    renderNoPrice();
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
    const origins = new Set(C.ORIGIN_CODES);
    model.items.forEach((i) => { if (i.origin) origins.add(i.origin); });
    $('#dl-origins').innerHTML = [...origins].map((o) => `<option value="${esc(o)}">`).join('');
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
      ${prevCellHTML(it)}
      <td class="e-price">${label}<input class="in num${bad ? ' invalid' : ''}" data-f="price" value="${esc(bad ? invalid.get(it.id) : priceToInput(it.price))}" placeholder="ohne Preis" aria-label="Preis in Euro je kg" inputmode="decimal">${was}${alts}</td>
      ${stockCellHTML(it)}
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
          <th class="e-code">Art.-Nr.</th><th class="e-name">Bezeichnung</th><th class="e-cat">Fleischart</th><th class="e-origin">Herkunft</th><th class="e-cond">Zustand</th>${auxHeadHTML()}<th class="e-act"><span class="sr-only">Aktionen</span></th>
        </tr></thead><tbody>${items.map(rowHTML).join('')}</tbody></table>
        <div class="gfoot"><button type="button" class="btn ghost" data-act="add-item">${icon('plus')}Artikel hinzufügen</button></div>
      </section>`;
    });
    host.innerHTML = out;
    host.classList.toggle('no-stock', !stock);
    host.classList.toggle('no-prev', !prevWeek);
    lockInputs(host);
  }

  /* ======================= Bearbeiten ======================= */
  function applyField(it, f, el) {
    const v = el.value;
    if (f === 'code') { const c = v.trim(); it.code = c || null; el.value = c; }
    else if (f === 'name') {
      const typed = C.clean(v);
      if (!typed) { el.value = it.name; toast('Die Bezeichnung darf nicht leer sein.'); return false; }
      const n = C.stripFrisch(typed);
      if (n !== typed) { el.value = n; if (it.condition !== 'frisch-gefroren') it.condition = 'frisch'; toast('„frisch“ steht im Zustand, nicht in der Bezeichnung.'); }
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
  $('#ed-q').addEventListener('input', () => setTimeout(renderNoPrice, 150));

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
        <div class="fld span2" id="item-stock"></div>
        <div class="fld span2" id="item-hist"></div>
        <p class="form-err span2" id="item-err" role="alert"></p>
      </div>
      <div class="dlg-foot">
        <span class="left">
          <button type="button" class="btn sm ghost" data-ia="up"${pos <= 0 ? ' disabled' : ''}>${icon('up', 'sm')}Nach oben</button>
          <button type="button" class="btn sm ghost" data-ia="down"${pos >= sameGroup.length - 1 ? ' disabled' : ''}>${icon('down', 'sm')}Nach unten</button>
          <button type="button" class="btn sm ghost" data-ia="dup">${icon('copy', 'sm')}Duplizieren</button>
          ${it.code ? `<button type="button" class="btn sm ghost" data-ia="to-master" title="Bezeichnung, Fleischart, Herkunft und Zustand als Stammdaten für ${esc(it.code)} speichern">${icon('check', 'sm')}Als Stammdaten speichern</button>` : ''}
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
    fillItemStock(it);
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
    } else if (a === 'to-master') {
      saveItemToMaster(it);
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
  window.addEventListener('drop', (e) => {
    const f = e.dataTransfer?.files?.[0];
    if (!f || !model) return;
    e.preventDefault();
    if (ro) return;
    if (currentView === 'edit') importFile(f);
    else if (currentView === 'stock') stockImportFile(f);
  });

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
      normalizeNames(model);
      const nm = applyMasterTo(model);
      invalid.clear(); autoAttr.clear();
      dlgImport.close();
      renderMeta();
      changed({ render: true });
      toast(`Import übernommen: ${plural(d.items.length, 'Position', 'Positionen')}${nm ? `, ${plural(nm, 'Artikel', 'Artikel')} nach Stammdaten angepasst` : ''}. Prüfen, ggf. anpassen, dann veröffentlichen.`, 6000);
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
    const rv = (kind, id) => `<button type="button" class="btn sm ghost rv-btn" data-rv="${kind}" data-rid="${esc(id)}" title="Diese Änderung zurücknehmen">${icon('undo', 'sm')}Rückgängig</button>`;
    let body = '';
    if (v.errors.length) body += sec('Bitte zuerst korrigieren', `<ul class="plist">${v.errors.map((e) => `<li class="err"><span>${esc(e)}</span><span></span></li>`).join('')}</ul>`);
    if (!published) body += `<p class="notice">Erste Veröffentlichung: ${plural(model.items.length, 'Artikel', 'Artikel')} in ${plural(model.groups.length, 'Gruppe', 'Gruppen')}.</p>`;
    else {
      if (metaChanged()) body += sec('Kopfdaten', `<ul class="plist"><li><span>KW ${esc(published.meta.week)}/${esc(published.meta.year)} → KW ${esc(model.meta.week)}/${esc(model.meta.year)}</span><span>${esc(model.meta.notice || '')}</span>${rv('meta', 'meta')}</li></ul>`);
      if (diff.priceChanged.length) body += sec(`Preisänderungen (${diff.priceChanged.length})`, list(diff.priceChanged, (it) => `<li><span>${esc(it.code || '—')} · ${esc(it.name)}</span><span>${esc(priceShort(before.get(it.id).price))} → <strong>${esc(priceShort(it.price))}</strong></span>${rv('price', it.id)}</li>`, 50));
      if (diff.added.length) body += sec(`Neu (${diff.added.length})`, list(diff.added, (it) => `<li><span>${esc(it.code || '—')} · ${esc(it.name)}</span><span>${esc(priceShort(it.price))}</span>${rv('added', it.id)}</li>`, 50));
      if (diff.changed.length) body += sec(`Bearbeitet (${diff.changed.length})`, list(diff.changed, (it) => `<li><span>${esc(it.code || '—')} · ${esc(it.name)}${changedFields(before.get(it.id), it)}</span><span>${esc(gById(it.groupId)?.name || '')}</span>${rv('changed', it.id)}</li>`, 50));
      if (diff.removed.length) body += sec(`Entfernt (${diff.removed.length})`, list(diff.removed, (it) => `<li><span>${esc(it.code || '—')} · ${esc(it.name)}</span><span>${esc(priceShort(it.price))}</span>${rv('removed', it.id)}</li>`, 50));
      if (!metaChanged() && !diff.priceChanged.length && !diff.added.length && !diff.changed.length && !diff.removed.length) body += '<p class="notice">Keine Änderungen gegenüber der veröffentlichten Fassung.</p>';
    }
    if (v.warnings.length) body += `<p class="hint">${v.warnings.map(esc).join('<br>')}</p>`;
    const can = !v.errors.length;
    $('#publish-body').innerHTML = `<div class="dlg-head"><div><h2 id="pub-title">Veröffentlichen</h2><p>Nach dem Veröffentlichen sehen alle Besucher der Angebotsseite diesen Stand. Der bisherige Stand wird als Version gesichert.</p></div><button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">${body}</div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="button" class="btn primary" data-ia="publish"${can ? '' : ' disabled'}>${icon('send')}Jetzt veröffentlichen</button></div>`;
    dlgPublish.showModal();
  }
  const FIELD_LABEL = { code: 'Art.-Nr.', name: 'Bezeichnung', category: 'Fleischart', origin: 'Herkunft', condition: 'Zustand' };
  function changedFields(o, it) {
    if (!o) return '';
    const f = Object.keys(FIELD_LABEL).filter((k) => (o[k] || '') !== (it[k] || ''));
    return f.length ? `<span class="rv-f">${f.map((k) => `${esc(FIELD_LABEL[k])}: ${esc(o[k] || '—')} → ${esc(it[k] || '—')}`).join(' · ')}</span>` : '';
  }
  /* Eine einzelne Änderung gegenüber der veröffentlichten Fassung zurücknehmen */
  function revertChange(kind, id) {
    if (kind === 'meta') { model.meta = clone(published.meta); return; }
    const pub = published.items;
    if (kind === 'added') { const i = model.items.findIndex((x) => x.id === id); if (i >= 0) model.items.splice(i, 1); invalid.delete(id); return; }
    if (kind === 'price' || kind === 'changed') {
      const it = model.items.find((x) => x.id === id), o = diff.before[id];
      if (!it || !o) return;
      const keep = { id: it.id, groupId: model.groups.some((g) => g.id === o.groupId) ? o.groupId : it.groupId };
      if (kind === 'price') { it.price = clone(o.price); it.altPrices = clone(o.altPrices || []); if ('priceText' in o) it.priceText = o.priceText; }
      else Object.assign(it, clone(o), keep);
      invalid.delete(id);
      return;
    }
    if (kind === 'removed') {
      const o = pub.find((x) => x.id === id);
      if (!o) return;
      if (!model.groups.some((g) => g.id === o.groupId)) {
        const g = published.groups.find((x) => x.id === o.groupId);
        if (g) model.groups.push(clone(g));
      }
      const copy = clone(o);
      if (model.items.some((x) => x.id === copy.id)) copy.id = uid('n');
      // hinter den nächsten veröffentlichten Vorgänger derselben Gruppe einsortieren
      let at = -1;
      for (let i = pub.indexOf(o) - 1; i >= 0 && at < 0; i--) if (pub[i].groupId === o.groupId) at = model.items.findIndex((x) => x.id === pub[i].id);
      if (at >= 0) model.items.splice(at + 1, 0, copy);
      else { const f = model.items.findIndex((x) => x.groupId === copy.groupId); if (f >= 0) model.items.splice(f, 0, copy); else model.items.push(copy); }
    }
  }
  function revertText(kind, id) {
    const it = model.items.find((x) => x.id === id) || published.items.find((x) => x.id === id);
    const nm = it ? `„${esc(it.code ? it.code + ' · ' : '')}${esc(it.name)}“` : '';
    const o = diff.before[id];
    if (kind === 'meta') return ['Kopfdaten zurücksetzen?', `Kalenderwoche und Hinweis werden wieder auf den veröffentlichten Stand gesetzt (KW ${esc(published.meta.week)}/${esc(published.meta.year)}).`];
    if (kind === 'price') return ['Preisänderung zurücknehmen?', `Der Preis von ${nm} wird von <strong>${esc(priceShort(it.price))}</strong> wieder auf <strong>${esc(priceShort(o.price))}</strong> gesetzt.`];
    if (kind === 'added') return ['Neuen Artikel entfernen?', `${nm} wird wieder aus dem Entwurf entfernt.`];
    if (kind === 'changed') return ['Bearbeitung zurücknehmen?', `${nm} wird wieder auf den veröffentlichten Stand gesetzt${o && o.name !== it.name ? ` (Bezeichnung „${esc(o.name)}“)` : ''}.`];
    return ['Artikel wiederherstellen?', `${nm} wird wieder in den Entwurf aufgenommen – mit dem zuletzt veröffentlichten Preis ${esc(priceShort(it.price))}.`];
  }
  dlgPublish.addEventListener('click', async (e) => {
    if (e.target === dlgPublish || e.target.closest('[data-close]')) { dlgPublish.close(); return; }
    const r = e.target.closest('[data-rv]');
    if (r) {
      const [title, text] = revertText(r.dataset.rv, r.dataset.rid);
      if (!(await confirmBox(title, `${text}<br><br>Die Änderung ist danach aus dem Entwurf entfernt; veröffentlicht wird sie erst mit „Jetzt veröffentlichen“.`, 'Ja, rückgängig machen', true))) return;
      pushUndo();
      revertChange(r.dataset.rv, r.dataset.rid);
      changed({ render: true });
      openPublish();
      toast('Änderung zurückgenommen.');
      return;
    }
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
      normalizeNames(model);
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
    if (a === 'twofa') openTwofaDialog();
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
    return 'n:' + (it.code || '') + '|' + nk(C.stripFrisch(it.name)) + '|' + nk(it.group);
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
  const VIEWS = ['edit', 'hist', 'stock', 'master', 'users', 'log', 'sec'];
  function setView(v) {
    if ((v === 'users' || v === 'log' || v === 'sec') && !can('admin')) v = 'edit';
    currentView = v;
    for (const k of VIEWS) {
      $('#vt-' + k).setAttribute('aria-selected', k === v);
      $('#view-' + k).hidden = k !== v;
    }
    document.body.classList.toggle('in-hist', v === 'hist');
    document.body.classList.toggle('in-other', v !== 'edit');
    if (v === 'edit' && model) loadAux();
    if (v === 'hist') renderHistView();
    if (v === 'stock') renderStockView();
    if (v === 'master') renderMasterView();
    if (v === 'users') renderUsersView();
    if (v === 'log') renderLogView();
    if (v === 'sec') renderSecView();
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
    try { await api('history_delete', { body: { id: w.id } }); prevKey = ''; await loadHistory(true); renderHistView(); toast(`${wkLong(w)} entfernt.`); } catch (ex) { toast(ex.message); }
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
    prevKey = '';
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

  /* ======================= Bestand (Mengen, MHD – nur im Eingabebereich) ======================= */
  const S = window.StockCore;
  let stock = null, stockLoaded = false, stockLoading = null, stockQ = '';
  const fmtKg = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const kgText = (v) => (v == null || !Number.isFinite(v) ? '—' : fmtKg.format(v) + ' kg');
  const mhdShort = (iso) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(2, 4)}` : '—');
  function isoToday(plus = 0) {
    const d = new Date();
    d.setHours(12, 0, 0, 0);
    d.setDate(d.getDate() + plus);
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  }
  /* MHD-Kennzeichnung relativ zum heutigen Datum */
  function mhdClass(iso) {
    if (!iso) return '';
    const days = Math.round((Date.parse(iso + 'T12:00:00Z') - Date.parse(isoToday() + 'T12:00:00Z')) / 864e5);
    if (days < 0) return 'mhd-past';
    if (days <= 4) return 'mhd-0-4';
    if (days <= 7) return 'mhd-5-7';
    if (days <= 14) return 'mhd-8-14';
    return '';
  }
  const SKULL = '<span class="mhd-skull" title="MHD abgelaufen" aria-label="MHD abgelaufen">&#x2620;&#xFE0E;</span>';
  const mhdKgHTML = (a) => `${mhdClass(a.mhd) === 'mhd-past' ? SKULL : ''}${esc(kgText(a.mhdKg))}`;
  const isMhdQuery = (q) => fold(q).replace(/\s+/g, '') === 'mhd';

  async function loadStock(force) {
    if (stockLoaded && !force) return stock;
    if (!stockLoading) stockLoading = api('stock').then((r) => { stock = r.stock || null; stockLoaded = true; return stock; }).finally(() => { stockLoading = null; });
    return stockLoading;
  }
  /* Verkaufspreise der Angebotswoche (aktueller Entwurf) je Artikelnummer */
  function offerPriceMap() {
    const m = new Map();
    for (const it of (model ? model.items : [])) {
      if (!it.code) continue;
      const k = S.normCode(it.code);
      if (!m.has(k)) m.set(k, []);
      m.get(k).push(it);
    }
    return m;
  }
  function stockItems() {
    const prices = offerPriceMap();
    return stock.articles.map((a, i) => {
      const cand = prices.get(S.normCode(a.code)) || [];
      const main = cand.find((x) => x.price.status === 'value') || cand.find((x) => x.price.status === 'request') || null;
      return { ...a, idx: i, wg: S.warengruppe(a.code), offer: cand, price: main ? main.price : null, cls: mhdClass(a.mhd), _hay: fold(a.code + ' ' + a.name) };
    });
  }
  const vkText = (p) => (!p ? '—' : p.status === 'value' ? fmtNum.format(p.value) + ' €' : p.status === 'request' ? 'a. Anfr.' : '—');
  const sum = (list, f) => list.reduce((t, a) => t + (Number.isFinite(a[f]) ? a[f] : 0), 0);
  /* Normale Suche: Warengruppen, MHD-markierte zuerst (früheste oben), dann Artikelnummer; MHD-Abfrage: flach bis heute + 14 Tage */
  /* Sortierung per Klick auf die Spaltenüberschrift (leere Werte immer unten) */
  let stockSort = store.get('stockSort', null);   // { key, dir } oder null = Standard
  const byCode = (a, b) => a.code.localeCompare(b.code, 'de', { numeric: true });
  const vkNum = (a) => (a.price && a.price.status === 'value' ? a.price.value : null);
  const SORT_GET = { code: null, name: (a) => a.name, vk: vkNum, kg: (a) => a.kg, mhd: (a) => a.mhd, mhdKg: (a) => a.mhdKg };
  function colCompare(a, b) {
    if (!stockSort) return 0;
    const { key, dir } = stockSort;
    if (key === 'code') return dir * byCode(a, b);
    const va = SORT_GET[key](a), vb = SORT_GET[key](b);
    if (va == null || vb == null) return (va == null) - (vb == null);
    return dir * (typeof va === 'string' ? va.localeCompare(vb, 'de', { numeric: true }) : va - vb);
  }
  function stockResult(q) {
    const all = stockItems();
    if (isMhdQuery(q)) {
      const lim = isoToday(14);
      const list = all.filter((a) => a.mhd && a.mhd <= lim).sort((a, b) => colCompare(a, b) || a.mhd.localeCompare(b.mhd) || byCode(a, b));
      return { flat: true, list, groups: null };
    }
    const toks = fold(q).split(/\s+/).filter(Boolean);
    const list = all.filter((a) => toks.every((t) => a._hay.includes(t)));
    const rank = (a) => (a.cls ? 0 : 1);
    // Warengruppe → MHD-markierte zuerst (früheste oben) → gewählte Spalte → Artikelnummer
    list.sort((a, b) => a.wg.order - b.wg.order || rank(a) - rank(b) || (rank(a) === 0 ? a.mhd.localeCompare(b.mhd) : 0) || colCompare(a, b) || byCode(a, b));
    const groups = [];
    for (const a of list) { const g = groups[groups.length - 1]; if (g && g.label === a.wg.label) g.items.push(a); else groups.push({ label: a.wg.label, items: [a] }); }
    return { flat: false, list, groups };
  }
  const sortTh = (key, cls, label) => {
    const on = stockSort && stockSort.key === key;
    const dir = on ? (stockSort.dir > 0 ? 'ascending' : 'descending') : 'none';
    return `<th class="${cls}" aria-sort="${dir}"><button type="button" class="sort-btn${on ? ' on' : ''}" data-ssort="${key}" title="Nach ${esc(label.replace('<br>', ' '))} sortieren">${label}<span class="sort-ind" aria-hidden="true">${on ? (stockSort.dir > 0 ? '▲' : '▼') : ''}</span></button></th>`;
  };
  const stockHead = () => `<tr>${sortTh('code', 's-code', 'Art.<br>Nr')}${sortTh('name', 's-name', 'Art.<br>Bez.')}${sortTh('vk', 's-vk', `VK<br>KW ${esc(model && model.meta.week || '')}`)}${sortTh('kg', 's-kg', 'Kg<br>verfüg.')}${sortTh('mhd', 's-mhd', 'Kürz.<br>MHD')}${sortTh('mhdKg', 's-mkg', 'Kg kürz.<br>MHD')}</tr>`;
  const stockRow = (a) => `<tr class="srow" data-sidx="${a.idx}" tabindex="0">
      <td class="s-code">${esc(a.code)}</td><td class="s-name" title="${esc(a.name)}">${esc(a.name)}</td>
      <td class="s-vk" data-l="VK">${esc(vkText(a.price))}</td><td class="s-kg" data-l="Kg verfüg.">${esc(kgText(a.kg))}</td>
      <td class="s-mhd ${a.cls}" data-l="Kürz. MHD">${esc(mhdShort(a.mhd))}</td><td class="s-mkg ${a.cls}" data-l="Kg kürz. MHD"><span>${mhdKgHTML(a)}</span></td></tr>`;
  const totalRow = (label, list, cls) => `<tr class="${cls}"><td colspan="3">${esc(label)}</td><td class="s-kg">${esc(kgText(sum(list, 'kg')))}</td><td class="s-mhd"></td><td class="s-mkg">${esc(kgText(sum(list, 'mhdKg')))}</td></tr>`;
  function stockTableHTML(res) {
    let body;
    if (res.flat) body = `<tbody>${res.list.map(stockRow).join('')}</tbody>`;
    else body = res.groups.map((g, i) => `<tbody class="wg">${i ? '<tr class="wg-gap" aria-hidden="true"><td colspan="6"></td></tr>' : ''}<tr class="wg-h"><td colspan="6">${esc(g.label)}</td></tr>${g.items.map(stockRow).join('')}${totalRow('Summe ' + g.label, g.items, 'wg-sum')}</tbody>`).join('');
    return `<table class="stab${res.flat ? ' flat' : ''}"><thead>${stockHead()}</thead>${body}<tfoot>${totalRow('Gesamtsumme Menge verfügbar', res.list, 'st-total')}</tfoot></table>`;
  }
  const legendHTML = () => `<div class="mhd-legend" aria-label="MHD-Kennzeichnung"><span class="mhd-past">${SKULL} abgelaufen</span><span class="mhd-0-4">heute – 4 Tage</span><span class="mhd-5-7">5 – 7 Tage</span><span class="mhd-8-14">8 – 14 Tage</span></div>`;

  async function renderStockView() {
    const host = $('#view-stock');
    if (!stockLoaded) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Bestand wird geladen …</div>';
    try { await loadStock(); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    if (!stock) {
      host.innerHTML = `<div class="ed-empty"><h3>Noch kein Bestand übernommen</h3><p>Laden Sie die Bestandsliste aus WinAB hoch (z. B. „Bestand_16.10.26.XLS“). Mengen und MHD erscheinen nur hier im Eingabebereich – nie auf der öffentlichen Angebotsseite.</p>
        ${ro ? '' : `<div class="row-actions"><button type="button" class="btn primary" data-st="import">${icon('upload')}Bestandsliste hochladen</button></div>`}</div>`;
      return;
    }
    const age = stock.date ? Math.round((Date.parse(isoToday() + 'T12:00:00Z') - Date.parse(stock.date + 'T12:00:00Z')) / 864e5) : null;
    host.innerHTML = `
      <div class="st-info${age != null && age > 2 ? ' old' : ''}">
        <div><strong>Bestand vom ${stock.date ? esc(dmy(stock.date)) : 'unbekannten Datum'}</strong>${age != null && age > 2 ? ` <span class="st-age">· ${age} Tage alt</span>` : ''}<span class="sub">${esc(stock.source || '')}${stock.importedAt ? ` · übernommen ${esc(dateTime(stock.importedAt))}${stock.importedBy ? ' von ' + esc(stock.importedBy) : ''}` : ''} · nur eingelagerte Ware</span></div>
        ${legendHTML()}
      </div>
      <div class="ed-toolbar">
        <div class="search">${icon('search')}<input id="st-q" type="search" autocomplete="off" placeholder="Nummer, Bezeichnung … oder „MHD“" aria-label="Bestand durchsuchen" value="${esc(stockQ)}"></div>
        <span class="ed-hint" id="st-count"></span>
        <span class="st-actions">
          <button type="button" class="btn" data-st="print">${icon('print')}Drucken</button>
          <button type="button" class="btn" data-st="csv">${icon('download')}CSV</button>
          ${ro ? '' : `<button type="button" class="btn primary" data-st="import">${icon('upload')}Bestand hochladen</button>`}
        </span>
      </div>
      <div id="st-list"></div>`;
    renderStockList();
  }
  function renderStockList() {
    const host = $('#st-list');
    if (!host || !stock) return;
    const res = stockResult(stockQ);
    const mq = isMhdQuery(stockQ);
    $('#st-count').innerHTML = mq
      ? `<strong>${fmtInt.format(res.list.length)}</strong> Artikel mit MHD bis ${esc(dmy(isoToday(14)))} (früheste zuerst)`
      : `<strong>${fmtInt.format(res.list.length)}</strong> von ${fmtInt.format(stock.articles.length)} Artikeln${stockQ ? '' : ' · Tipp: „MHD“ eingeben'}`;
    host.innerHTML = res.list.length ? `<div class="gcard st-card">${stockTableHTML(res)}</div>`
      : `<div class="ed-empty"><h3>Keine Treffer</h3><p>${mq ? 'Kein Artikel mit MHD in den nächsten 14 Tagen oder bereits abgelaufen.' : 'Kein Artikel, dessen Nummer oder Bezeichnung zum Suchbegriff passt.'}</p></div>`;
  }
  $('#view-stock').addEventListener('input', (e) => {
    if (e.target.id === 'st-q') { clearTimeout(qTimer); qTimer = setTimeout(() => { stockQ = e.target.value.trim(); renderStockList(); }, 120); }
  });
  $('#view-stock').addEventListener('click', (e) => {
    const sb = e.target.closest('[data-ssort]');
    if (sb) {
      const key = sb.dataset.ssort;
      // 1. Klick aufsteigend, 2. absteigend, 3. zurück zur Standardsortierung
      if (!stockSort || stockSort.key !== key) stockSort = { key, dir: key === 'kg' || key === 'mhdKg' ? -1 : 1 };
      else if (stockSort.dir === (key === 'kg' || key === 'mhdKg' ? -1 : 1)) stockSort = { key, dir: -stockSort.dir };
      else stockSort = null;
      store.set('stockSort', stockSort);
      renderStockList();
      $(`#st-list [data-ssort="${key}"]`)?.focus();
      return;
    }
    const b = e.target.closest('[data-st]');
    if (b) {
      const a = b.dataset.st;
      if (a === 'import') { if (!ro) $('#stock-file-input').click(); }
      if (a === 'print') printStock();
      if (a === 'csv') stockCSV();
      return;
    }
    const tr = e.target.closest('tr.srow');
    if (tr) openStockItem(+tr.dataset.sidx);
  });
  $('#view-stock').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr.srow')) openStockItem(+e.target.dataset.sidx); });

  /* Detail: Partien eines Artikels */
  const dlgSA = $('#dlg-stock-item');
  function openStockItem(idx) {
    const a = stockItems()[idx];
    if (!a) return;
    const gname = (id) => (model.groups.find((g) => g.id === id) || {}).name || '';
    const offerTxt = a.offer.length
      ? a.offer.map((o) => `${esc(priceShort(o.price))}${o.price.label ? ' (' + esc(o.price.label) + ')' : ''} <span class="muted">· ${esc(gname(o.groupId))}</span>`).join('<br>')
      : '<span class="muted">nicht im aktuellen Angebot</span>';
    $('#stock-item-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="sa-title">${esc(a.name)}</h2><p>Art.-Nr. ${esc(a.code)} · ${esc(a.wg.label)} · Bestand vom ${stock.date ? esc(dmy(stock.date)) : '?'}</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        <div class="cmp-stats hstats">
          <div><span>Kg verfügbar</span><strong>${esc(kgText(a.kg))}</strong></div>
          <div><span>Kürzestes MHD</span><strong class="${a.cls}">${esc(mhdShort(a.mhd))}</strong></div>
          <div><span>Kg kürz. MHD</span><strong class="${a.cls}">${mhdKgHTML(a)}</strong></div>
          <div><span>VK KW ${esc(model.meta.week || '')}</span><strong>${esc(vkText(a.price))}</strong></div>
        </div>
        <h3 class="d-h"><span>Eingelagerte Partien</span><span>${plural(a.lots.length, 'Partie', 'Partien')}</span></h3>
        <table class="etab lottab"><thead><tr><th>Partie</th><th>Ankunft</th><th>MHD</th><th class="num">Kolli</th><th class="num">Kg netto</th></tr></thead><tbody>
          ${a.lots.map((l) => `<tr><td class="ch-code">${esc(l.lot || '—')}</td><td>${l.arrival ? esc(dmy(l.arrival)) : '—'}</td><td class="${mhdClass(l.mhd)}">${l.mhd ? esc(dmy(l.mhd)) : '<span class="muted">ohne MHD</span>'}</td><td class="num">${l.kolli == null ? '—' : esc(fmtInt.format(l.kolli))}</td><td class="num">${esc(kgText(l.kg))}</td></tr>`).join('')}
        </tbody></table>
        <h3 class="d-h"><span>Im Angebot (Entwurf KW ${esc(model.meta.week || '?')})</span></h3>
        <p style="margin:0">${offerTxt}</p>
      </div>`;
    dlgSA.showModal();
  }

  /* Bestand im Artikel-Dialog des Angebots */
  async function fillItemStock(it) {
    const slot = $('#item-stock');
    if (!slot) return;
    try { await loadStock(); } catch { return; }
    if (!stock || !$('#item-stock')) return;
    const a = it.code && stock.articles.find((x) => S.normCode(x.code) === S.normCode(it.code));
    const cls = a ? mhdClass(a.mhd) : '';
    $('#item-stock').innerHTML = `<span>Bestand (Stand ${stock.date ? esc(mhdShort(stock.date)) : '?'}, nur intern)</span>` + (a
      ? `<div class="item-stock">${esc(kgText(a.kg))} verfügbar · kürz. MHD <strong class="${cls}">${esc(mhdShort(a.mhd))}</strong> · <strong class="${cls}">${mhdKgHTML(a)}</strong></div>`
      : `<div class="muted" style="font-size:13px">${it.code ? 'Kein eingelagerter Bestand zu dieser Artikelnummer.' : 'Ohne Artikelnummer kein Bestandsabgleich.'}</div>`);
  }

  /* Bestandsliste hochladen */
  const dlgSI = $('#dlg-stock-import');
  let stockPending = null;
  $('#stock-file-input').addEventListener('change', (e) => { const f = e.target.files[0]; e.target.value = ''; if (f) stockImportFile(f); });
  async function stockImportFile(file) {
    if (ro) return;
    stockPending = null;
    const head = (t, sub) => `<div class="dlg-head"><div><h2 id="si-title">${t}</h2>${sub ? `<p>${sub}</p>` : ''}</div><button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>`;
    $('#stock-import-body').innerHTML = `${head('Bestandsliste', esc(file.name))}<div class="dlg-body"><div class="loading"><div class="spinner"></div>Datei wird gelesen …</div></div>`;
    if (!dlgSI.open) dlgSI.showModal();
    try {
      if (file.size > 30 * 1024 * 1024) throw new Error('Die Datei ist größer als 30 MB.');
      const r = S.parseStockWorkbook(await S.readStockWorkbook(await file.arrayBuffer()), file.name);
      if (!r.articles.length) throw new Error('Keine Artikel mit eingelagertem Bestand gefunden.');
      stockPending = r;
      try { await loadStock(); } catch { /* ignore */ }
      const total = sum(r.articles, 'kg');
      const other = Object.entries(r.stats.other).map(([k, v]) => `${fmtInt.format(v)} × „${esc(k)}“`).join(', ');
      const soon = r.articles.filter((a) => a.mhd && a.mhd <= isoToday(14)).length;
      $('#stock-import-body').innerHTML = `${head('Bestandsliste prüfen', esc(file.name))}
        <div class="dlg-body">
          <div class="imp-sum">
            <div><span>Artikel mit Bestand</span><strong>${fmtInt.format(r.articles.length)}</strong></div>
            <div><span>Kg eingelagert</span><strong>${esc(fmtKg.format(total))}</strong></div>
            <div><span>MHD ≤ 14 Tage</span><strong>${fmtInt.format(soon)}</strong></div>
          </div>
          <label class="fld" style="max-width:220px"><span>Bestandsdatum</span><input type="date" id="si-date" value="${esc(r.date || isoToday())}" required></label>
          <ul class="issues">
            <li class="info"><span class="lvl">Info</span><span>Berücksichtigt: ${fmtInt.format(r.stats.stored)} Partien mit Status „eingelagert“.${other ? ` Nicht berücksichtigt: ${other}.` : ''}</span></li>
            ${r.stats.skipped ? `<li class="info"><span class="lvl">Info</span><span>${fmtInt.format(r.stats.skipped)} Zeilen ohne gültige Artikelnummer übersprungen (z. B. „Etiketten“).</span></li>` : ''}
            ${r.stats.noMhd ? `<li class="info"><span class="lvl">Info</span><span>${fmtInt.format(r.stats.noMhd)} eingelagerte Partien ohne MHD – zählen zur verfügbaren Menge, nicht zum kürzesten MHD.</span></li>` : ''}
            ${!r.date ? '<li class="warn"><span class="lvl">Prüfen</span><span>Kein Datum in der Datei gefunden – bitte Bestandsdatum eintragen.</span></li>' : ''}
            ${stock ? `<li class="info"><span class="lvl">Info</span><span>Ersetzt den bisherigen Bestand vom ${stock.date ? esc(dmy(stock.date)) : '?'} (${fmtInt.format(stock.articles.length)} Artikel).</span></li>` : ''}
          </ul>
          <p class="hint">Mengen und MHD sind nur im Eingabebereich sichtbar, nicht auf der öffentlichen Angebotsseite.</p>
        </div>
        <div class="dlg-foot"><button type="button" class="btn" data-si="again">Andere Datei</button><span class="spacer"></span><button type="button" class="btn" data-close>Abbrechen</button><button type="button" class="btn primary" data-si="apply">${icon('check')}Bestand übernehmen</button></div>`;
    } catch (ex) {
      $('#stock-import-body').innerHTML = `${head('Bestandsliste nicht lesbar', esc(file.name))}<div class="dlg-body"><div class="err-box">${esc(ex.message || String(ex))}</div><p class="hint">Erwartet wird die Bestandsliste aus WinAB (.xls oder .xlsx) mit den Spalten Art.-Nr., Bezeichnung, Status, MHD und netto.</p></div>
        <div class="dlg-foot"><button type="button" class="btn" data-close>Schließen</button><button type="button" class="btn primary" data-si="again">Andere Datei wählen</button></div>`;
    }
  }
  dlgSI.addEventListener('click', async (e) => {
    const a = e.target.closest('[data-si]')?.dataset.si;
    if (a === 'again') { $('#stock-file-input').click(); return; }
    if (a !== 'apply' || !stockPending) return;
    const date = $('#si-date').value;
    if (!/^\d{4}-\d{2}-\d{2}$/.test(date)) { $('#si-date').focus(); return; }
    const btn = e.target.closest('[data-si]');
    btn.disabled = true;
    try {
      const r = await api('stock_import', { body: { date, source: stockPending.source, articles: stockPending.articles } });
      stock = r.stock; stockLoaded = true; stockPending = null; stockIdxFor = null;
      refreshAux();
      dlgSI.close();
      toast(`Bestand vom ${dmy(date)} übernommen: ${plural(stock.articles.length, 'Artikel', 'Artikel')}.`, 5000);
      if (currentView === 'stock') renderStockView(); else setView('stock');
    } catch (ex) {
      btn.disabled = false;
      $('#stock-import-body .dlg-body').insertAdjacentHTML('afterbegin', `<p class="err-box" style="margin:0 0 12px">${esc(ex.message)}</p>`);
    }
  });

  /* CSV (aktuelle Auswahl) */
  function stockCSV() {
    const res = stockResult(stockQ);
    const q = csvCell;
    const n2 = (v) => (v == null || !Number.isFinite(v) ? '' : fmtKg.format(v).replace(/\./g, ''));
    const lines = [['Art.-Nr.', 'Bezeichnung', `VK KW ${model.meta.week || ''}`, 'Kg verfügbar', 'Kürz. MHD', 'Kg kürz. MHD', 'Warengruppe', `Bestand vom`].join(';')];
    for (const a of res.list) lines.push([a.code, a.name, a.price && a.price.status === 'value' ? fmtNum.format(a.price.value).replace(/\./g, '') : a.price && a.price.status === 'request' ? 'a. Anfr.' : '', n2(a.kg), mhdShort(a.mhd).replace('—', ''), n2(a.mhdKg), a.wg.label, stock.date ? dmy(stock.date) : ''].map(q).join(';'));
    const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const el = document.createElement('a');
    el.href = URL.createObjectURL(blob);
    el.download = `Bestand_${stock.date || isoToday()}${isMhdQuery(stockQ) ? '_MHD' : stockQ ? '_Auswahl' : ''}.csv`;
    document.body.appendChild(el); el.click(); el.remove();
    setTimeout(() => URL.revokeObjectURL(el.href), 2000);
  }
  /* Druck / PDF (DIN A4) */
  function printStock() {
    const res = stockResult(stockQ);
    const w = window.open('', '_blank');
    if (!w) { toast('Druckfenster wurde blockiert – bitte Pop-ups für diese Seite erlauben.'); return; }
    const title = `Bestand vom ${stock.date ? dmy(stock.date) : '?'}${isMhdQuery(stockQ) ? ` – MHD bis ${dmy(isoToday(14))}` : stockQ ? ` – Suche „${stockQ}“` : ''}`;
    w.document.write(`<!doctype html><html lang="de"><head><meta charset="utf-8"><title>${esc(title)}</title><style>
      @page { size: A4; margin: 12mm 10mm; }
      * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      body { font: 9.5pt/1.3 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: #1b1a18; margin: 0; }
      h1 { font-size: 13pt; margin: 0 0 2px; } .meta { color: #666; font-size: 8.5pt; margin: 0 0 8px; }
      table { width: 100%; border-collapse: collapse; } th, td { padding: 2.5px 5px; border-bottom: .5pt solid #ddd; }
      th { font-size: 8pt; text-align: center; vertical-align: bottom; border-bottom: 1pt solid #999; }
      td.s-name { white-space: nowrap; } .s-code { width: 44px; } .s-vk, .s-kg, .s-mkg { text-align: right; white-space: nowrap; } .s-mhd { text-align: center; white-space: nowrap; }
      .s-mkg { font-weight: 700; } thead { display: table-header-group; } tr { break-inside: avoid; }
      .wg-h td { font-weight: 700; padding-top: 8px; border-bottom: 1pt solid #999; } .wg-sum td, .st-total td { font-weight: 700; background: #f3f1ee; }
      .wg-gap td { border: 0; height: 6px; padding: 0; } .st-total td { border-top: 1.5pt solid #333; }
      .mhd-past { background: #343a40; color: #fff; } .mhd-0-4 { background: #dc2626; color: #111; } .mhd-5-7 { background: #ea580c; color: #111; } .mhd-8-14 { background: #fdba74; color: #111; } .mhd-skull { font-size: 1.15em; margin-right: 3px; }
    </style></head><body><h1>${esc(company ? company + ' · ' : '')}${esc(title)}</h1>
      <p class="meta">${fmtInt.format(res.list.length)} Artikel · nur eingelagerte Ware · VK = Entwurf KW ${esc(model.meta.week || '?')}/${esc(model.meta.year || '')} · gedruckt ${esc(dateTime(new Date().toISOString()))} · intern – nicht zur Weitergabe</p>
      ${stockTableHTML(res).replace(/ tabindex="0"/g, '').replace(/<button[^>]*>/g, '').replace(/<\/button>/g, '')}
      </body></html>`);
    w.document.close();
    setTimeout(() => { try { w.focus(); w.print(); } catch { /* Fenster geschlossen */ } }, 300);
  }

  /* ======================= Angebot: Vorwoche, Bestand, Bestand ohne Preis ======================= */
  let prevWeek = null, prevKey = '', prevMap = new Map();
  let stockIdx = new Map(), stockIdxFor = null;
  async function loadPrev() {
    if (!model) return;
    const key = `${model.meta.year}-${model.meta.week}`;
    if (key === prevKey) return;
    prevKey = key;
    const r = await api('history_prev', { query: `&week=${encodeURIComponent(model.meta.week || '')}&year=${encodeURIComponent(model.meta.year || '')}` });
    if (prevKey !== key) return;
    prevWeek = r.week;
    prevMap = new Map();
    for (const it of (prevWeek ? prevWeek.items : [])) {
      if (!it.code) continue;
      const k = S.normCode(it.code);
      if (!prevMap.has(k)) prevMap.set(k, []);
      prevMap.get(k).push(it);
    }
  }
  async function loadAux() {
    await Promise.all([loadStock().catch(() => {}), loadPrev().catch(() => {})]);
    refreshAux();
  }
  function stockOf(code) {
    if (!stock || !code) return null;
    if (stockIdxFor !== stock) { stockIdx = new Map(stock.articles.map((a) => [S.normCode(a.code), a])); stockIdxFor = stock; }
    return stockIdx.get(S.normCode(code)) || null;
  }
  function prevOf(it) {
    const list = it.code ? prevMap.get(S.normCode(it.code)) : null;
    if (!list || !list.length) return null;
    const n = fold(C.stripFrisch(it.name));
    return list.find((x) => fold(C.stripFrisch(x.name)) === n) || list.find((x) => x.price && x.price.status === 'value') || list[0];
  }
  const prevLabel = () => (prevWeek ? `KW ${prevWeek.week}/${String(prevWeek.year).slice(2)}` : '');
  function auxHeadHTML() {
    return `<th class="e-prev" title="Preis aus dem Preisverlauf${prevWeek ? ' (KW ' + esc(prevWeek.week) + '/' + esc(prevWeek.year) + ')' : ''}">Vorwoche<small>${esc(prevLabel())}</small></th>`
      + `<th class="e-price">Preis €/kg<small>KW ${esc(model && model.meta.week || '')}</small></th>`
      + `<th class="e-stock" title="Verfügbarer Bestand (eingelagert)${stock && stock.date ? ' · Stand ' + esc(dmy(stock.date)) : ''}">Bestand kg<small>${stock && stock.date ? 'Stand ' + esc(mhdShort(stock.date)) : ''}</small></th>`;
  }
  function prevCellHTML(it) {
    const p = prevOf(it);
    const t = !p ? '—' : p.price.status === 'value' ? fmtNum.format(p.price.value) : p.price.status === 'request' ? 'a. Anfr.' : '—';
    const cur = it.price, pv = p && p.price.status === 'value' ? p.price.value : null;
    const d = pv != null && cur.status === 'value' ? Math.round((cur.value - pv) * 1000) / 1000 : null;
    const delta = d ? `<span class="pdelta ${d > 0 ? 'up' : 'down'}">${d > 0 ? '+' : '−'}${fmtNum.format(Math.abs(d))}</span>` : '';
    return `<td class="e-prev${p ? '' : ' none'}" title="${p ? esc(`Preis ${prevLabel()}: ${priceShort(p.price)}`) : 'In der Vorwoche nicht im Angebot'}">${esc(t)}${delta}</td>`;
  }
  function stockCellHTML(it) {
    const a = stockOf(it.code);
    if (!a) return `<td class="e-stock none" title="${it.code ? 'Kein eingelagerter Bestand' : 'Ohne Artikelnummer kein Bestandsabgleich'}">—</td>`;
    const cls = mhdClass(a.mhd);
    return `<td class="e-stock" title="${esc(`${kgText(a.kg)} verfügbar · kürz. MHD ${mhdShort(a.mhd)}${a.mhdKg != null ? ' (' + kgText(a.mhdKg) + ')' : ''}`)}">${cls ? `<span class="mhd-dot ${cls}" aria-label="MHD ${esc(mhdShort(a.mhd))}"></span>` : ''}${esc(fmtKg.format(a.kg))}</td>`;
  }
  /* Spalten nach dem Laden von Bestand/Vorwoche aktualisieren, ohne Eingabefelder neu zu zeichnen */
  function refreshAux() {
    if (!model) return;
    const host = $('#groups');
    host.classList.toggle('no-stock', !stock);
    host.classList.toggle('no-prev', !prevWeek);
    for (const tr of $$('thead tr', host)) {
      $$('th.e-prev, th.e-price, th.e-stock', tr).forEach((th) => th.remove());
      const tmp = document.createElement('tr');
      tmp.innerHTML = auxHeadHTML();
      tr.querySelector('th.e-act').before(...tmp.children);
    }
    for (const tr of $$('tr[data-id]', host)) {
      const it = iById(tr.dataset.id);
      if (!it) continue;
      const tmp = document.createElement('tr');
      tmp.innerHTML = prevCellHTML(it) + stockCellHTML(it);
      const [pc, sc] = [...tmp.children];
      tr.querySelector('td.e-prev').replaceWith(pc);
      tr.querySelector('td.e-stock').replaceWith(sc);
    }
    renderNoPrice();
  }

  /* Bestand ohne Preis: eingelagerte Artikel, die im Angebot keinen Preis haben */
  let npOpen = store.get('npOpen', true);
  function noPriceList() {
    if (!stock || !model) return [];
    const byCode = new Map();
    for (const it of model.items) if (it.code) { const k = S.normCode(it.code); if (!byCode.has(k)) byCode.set(k, []); byCode.get(k).push(it); }
    const out = [];
    for (const a of stock.articles) {
      const items = byCode.get(S.normCode(a.code)) || [];
      if (items.some((x) => x.price.status === 'value' || x.price.status === 'request')) continue;
      out.push({ a, items, wg: S.warengruppe(a.code), cls: mhdClass(a.mhd) });
    }
    const rank = (x) => (x.cls ? 0 : 1);
    return out.sort((x, y) => x.wg.order - y.wg.order || rank(x) - rank(y) || (rank(x) === 0 ? x.a.mhd.localeCompare(y.a.mhd) : 0) || x.a.code.localeCompare(y.a.code, 'de', { numeric: true }));
  }
  function renderNoPrice() {
    const host = $('#noprice-panel');
    if (!host) return;
    if (!stock || !model) { host.hidden = true; return; }
    const all = noPriceList();
    const toks = fold(filterQ).split(/\s+/).filter(Boolean);
    const list = toks.length ? all.filter((x) => { const h = fold(x.a.code + ' ' + x.a.name); return toks.every((t) => h.includes(t)); }) : all;
    host.hidden = false;
    const kg = list.reduce((t, x) => t + x.a.kg, 0);
    const rows = list.map((x) => {
      const p = prevOf({ code: x.a.code, name: x.a.name });
      const inOffer = x.items.length;
      return `<tr data-npcode="${esc(x.a.code)}">
        <td class="np-code">${esc(x.a.code)}</td><td class="np-name">${esc(x.a.name)}</td><td class="np-wg">${esc(x.wg.label)}</td>
        <td class="np-kg">${esc(kgText(x.a.kg))}</td><td class="np-mhd"><span class="${x.cls}">${esc(mhdShort(x.a.mhd))}</span></td>
        <td class="np-prev">${p && p.price.status === 'value' ? esc(fmtNum.format(p.price.value)) : p && p.price.status === 'request' ? 'a. Anfr.' : '—'}</td>
        <td class="np-act">${ro ? (inOffer ? '<span class="muted">im Angebot ohne Preis</span>' : '') : inOffer
          ? '<button type="button" class="btn sm" data-np="goto">Preis eintragen</button>'
          : `<button type="button" class="btn sm" data-np="add">${icon('plus', 'sm')}Ins Angebot</button>`}</td>
      </tr>`;
    }).join('');
    host.innerHTML = `<div class="np-card${npOpen ? ' open' : ''}">
      <button type="button" class="np-head" data-np="toggle" aria-expanded="${npOpen}">
        <span class="np-title">Bestand ohne Preis <span class="np-badge">${fmtInt.format(all.length)}</span></span>
        <span class="np-sub">Eingelagert, aber im Angebot KW ${esc(model.meta.week || '?')} ohne Preis · ${esc(kgText(all.reduce((t, x) => t + x.a.kg, 0)))} · Bestand vom ${stock.date ? esc(dmy(stock.date)) : '?'}</span>
        ${icon('chev', 'np-chev')}
      </button>
      ${npOpen ? (list.length ? `<div class="np-body"><table class="etab nptab"><thead><tr><th class="np-code">Art.-Nr.</th><th class="np-name">Bezeichnung</th><th class="np-wg">Warengruppe</th><th class="np-kg">Kg verfüg.</th><th class="np-mhd">Kürz. MHD</th><th class="np-prev" title="Preis ${esc(prevLabel())}">Vorwoche</th><th class="np-act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${rows}</tbody>
          ${toks.length ? `<tfoot><tr><td colspan="7" class="muted">${plural(list.length, 'Treffer', 'Treffer')} zur Suche · ${esc(kgText(kg))}</td></tr></tfoot>` : ''}</table></div>`
        : `<p class="np-empty">${all.length ? 'Kein Treffer zur Suche.' : 'Alle Artikel mit eingelagertem Bestand haben einen Preis.'}</p>`) : ''}
    </div>`;
  }
  $('#noprice-panel').addEventListener('click', (e) => {
    const b = e.target.closest('[data-np]');
    if (!b) return;
    const act = b.dataset.np;
    if (act === 'toggle') { npOpen = !npOpen; store.set('npOpen', npOpen); renderNoPrice(); return; }
    const code = b.closest('tr[data-npcode]')?.dataset.npcode;
    if (!code || ro) return;
    if (act === 'goto') {
      const it = model.items.find((x) => x.code && S.normCode(x.code) === S.normCode(code));
      if (!it) return;
      if (filterQ || onlyChanges) { filterQ = ''; onlyChanges = false; $('#ed-q').value = ''; $('#only-changes').checked = false; renderGroups(); }
      const inp = $(`tr[data-id="${CSS.escape(it.id)}"] input[data-f="price"]`);
      if (inp) { inp.scrollIntoView({ block: 'center', behavior: 'smooth' }); inp.focus(); inp.select(); }
    }
    if (act === 'add') openAddStock(code);
  });

  /* Artikel aus dem Bestand ins Angebot übernehmen */
  const dlgAS = $('#dlg-add-stock');
  let addCode = null;
  function suggestGroup(code) {
    const n = Number(code), wg = S.warengruppe(code).order;
    let best = null, dist = Infinity;
    for (const it of model.items) {
      if (!it.code || !/^\d+$/.test(it.code) || S.warengruppe(it.code).order !== wg) continue;
      const d = Math.abs(Number(it.code) - n);
      if (d < dist) { dist = d; best = it.groupId; }
    }
    return best || (model.groups[0] && model.groups[0].id);
  }
  function openAddStock(code) {
    const a = stockOf(code);
    if (!a) return;
    if (!model.groups.length) { toast('Bitte zuerst eine Angebotsgruppe anlegen.'); return; }
    addCode = code;
    const gsel = suggestGroup(code);
    const p = prevOf({ code: a.code, name: a.name });
    const cls = mhdClass(a.mhd);
    $('#add-stock-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="as-title">Ins Angebot übernehmen</h2><p>Art.-Nr. ${esc(a.code)} · ${esc(kgText(a.kg))} verfügbar · kürz. MHD <span class="${cls}">${esc(mhdShort(a.mhd))}</span></p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body form-grid two">
        <label class="fld span2"><span>Bezeichnung im Angebot${masterOf(a.code) ? ' <small class="muted">(aus Stammdaten)</small>' : ''}</span><input name="name" value="${esc(masterOf(a.code) ? masterOf(a.code).name : C.stripFrisch(a.name))}" maxlength="200" required></label>
        <label class="fld"><span>Angebotsgruppe</span><select name="groupId">${model.groups.map((g) => `<option value="${esc(g.id)}"${g.id === gsel ? ' selected' : ''}>${esc(g.name)}</option>`).join('')}</select></label>
        <label class="fld"><span>Preis €/kg (KW ${esc(model.meta.week || '')})</span><input name="price" inputmode="decimal" placeholder="${p && p.price.status === 'value' ? 'Vorwoche ' + esc(fmtNum.format(p.price.value)) : 'z. B. 12,50'}"></label>
        <p class="form-err span2" id="as-err" role="alert"></p>
      </div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="submit" class="btn primary">${icon('plus')}Übernehmen</button></div>`;
    dlgAS.showModal();
    $('#add-stock-body [name="price"]').focus();
  }
  $('#add-stock-body').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = e.target, a = stockOf(addCode);
    if (!a || ro) return;
    const name = C.clean(f.elements.name.value);
    if (!name) { $('#as-err').textContent = 'Bitte eine Bezeichnung angeben.'; return; }
    const price = inputToPrice(f.elements.price.value.trim());
    if (!price) { $('#as-err').textContent = 'Preis nicht lesbar – z. B. 12,50, „a. Anfr.“ oder leer.'; return; }
    pushUndo();
    const g = gById(f.elements.groupId.value);
    const it = newItem(g.id);
    const me0 = masterOf(a.code);
    Object.assign(it, C.suggestAttributes(a.name, g.name, g.section), me0 ? { category: me0.category, origin: me0.origin, condition: me0.condition } : {}, { code: a.code, name: C.stripFrisch(name), price });
    autoAttr.delete(it.id);
    dlgAS.close();
    changed({ render: true });
    toast(`„${name}“ in „${g.name}“ übernommen${price.status === 'value' ? ' – ' + priceShort(price) : ''}.`, 4500);
  });

  /* ======================= Stammdaten (je Artikelnummer) ======================= */
  let master = null, masterLoading = null, masterQ = '', masterTimer = null, masterSaving = false, masterQueued = false, masterErr = null;
  async function loadMaster(force) {
    if (master && !force) return master;
    if (!masterLoading) masterLoading = api('master').then((r) => { master = r.master; return master; }).finally(() => { masterLoading = null; });
    return masterLoading;
  }
  const mKey = (c) => S.normCode(c);
  function masterOf(code) { return master && code ? master.articles.find((a) => mKey(a.code) === mKey(code)) || null : null; }
  function draftByCode(m = model) {
    const map = new Map();
    for (const it of (m ? m.items : [])) if (it.code) { const k = mKey(it.code); if (!map.has(k)) map.set(k, []); map.get(k).push(it); }
    return map;
  }
  const M_FIELDS = ['name', 'category', 'origin', 'condition'];
  const differs = (e, it) => M_FIELDS.some((f) => (e[f] || '') !== (it[f] || ''));
  /* Stammdaten auf Artikel anwenden (nur eindeutige Artikelnummern) */
  function applyMasterTo(m, onlyCode) {
    if (!master || !master.articles.length) return 0;
    const by = draftByCode(m);
    let n = 0;
    for (const e of master.articles) {
      if (onlyCode && mKey(e.code) !== mKey(onlyCode)) continue;
      const list = by.get(mKey(e.code));
      if (!list || list.length !== 1 || !differs(e, list[0])) continue;
      const it = list[0];
      for (const f of M_FIELDS) it[f] = e[f] ?? null;
      delete it.nameRaw;
      autoAttr.delete(it.id);
      n++;
    }
    return n;
  }
  /* Stammdaten an die Regeln anpassen (einmalig je Änderung der Regeln, danach ohne Wirkung) */
  function migrateMaster() {
    if (ro || !master || !master.articles.length || !model) return 0;
    const by = draftByCode();
    const gb = new Map(model.groups.map((g) => [g.id, g]));
    let n = 0;
    for (const e of master.articles) {
      const list = by.get(mKey(e.code));
      const g = list && list.length === 1 ? gb.get(list[0].groupId) : null;
      if (C.normalizeItem(e, g)) n++;
    }
    if (n) { saveMaster(); if (currentView === 'master') renderMasterView(); }
    return n;
  }
  function addFromDraft() {
    const by = draftByCode();
    let n = 0;
    for (const [k, list] of by) {
      if (list.length !== 1 || masterOf(k)) continue;
      const it = list[0];
      master.articles.push({ code: it.code, name: C.stripFrisch(it.name), category: it.category, origin: it.origin || null, condition: it.condition });
      n++;
    }
    master.articles.sort((a, b) => a.code.localeCompare(b.code, 'de', { numeric: true }));
    return n;
  }
  function setMasterState(st, msg) {
    const el = $('#ms-state');
    if (!el) return;
    el.className = 'ms-state ' + st;
    el.innerHTML = st === 'saving' ? 'Speichert …' : st === 'error' ? `Nicht gespeichert: ${esc(msg || '')} <button type="button" class="link-btn" data-ma="retry">Erneut</button>` : master && master.updatedAt ? `Gespeichert · ${esc(timeOnly(master.updatedAt))} Uhr` : '';
  }
  function masterChanged() { clearTimeout(masterTimer); setMasterState('saving'); masterTimer = setTimeout(saveMaster, 700); }
  async function saveMaster() {
    clearTimeout(masterTimer);
    if (ro || !master) return;
    if (masterSaving) { masterQueued = true; return; }
    masterSaving = true;
    setMasterState('saving');
    try {
      const r = await api('master_save', { body: { rev: master.rev, articles: master.articles } });
      master.rev = r.rev; master.updatedAt = r.updatedAt; masterErr = null;
      setMasterState('saved');
    } catch (e) { masterErr = e.message; setMasterState('error', e.message); }
    finally { masterSaving = false; if (masterQueued) { masterQueued = false; saveMaster(); } }
  }
  function offerStatus(e, by) {
    const list = by.get(mKey(e.code));
    if (!list) return '<span class="muted" title="Nicht im aktuellen Angebot">—</span>';
    if (list.length > 1) return `<span class="muted" title="Artikelnummer ${list.length}× im Angebot – wird nicht automatisch abgeglichen">${list.length}× im Angebot</span>`;
    if (differs(e, list[0])) return ro ? '<span class="m-diff">abweichend</span>' : `<button type="button" class="m-diff" data-ma="apply1" title="Angebot: ${esc(list[0].name)} · ${esc(list[0].category)} · ${esc(list[0].origin || '–')} · ${esc(C.CONDITION_LABELS[list[0].condition])} – klicken, um die Stammdaten zu übernehmen">abweichend</button>`;
    return `<span class="m-ok" title="Angebot entspricht den Stammdaten">${icon('check', 'sm')}</span>`;
  }
  async function renderMasterView() {
    const host = $('#view-master');
    if (!master) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Stammdaten werden geladen …</div>';
    try { await loadMaster(); await loadStock().catch(() => {}); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    migrateMaster();
    if (!ro && !master.articles.length && model && model.items.length) {
      const n = addFromDraft();
      if (n) { saveMaster(); toast(`Stammdaten angelegt: ${plural(n, 'Artikel', 'Artikel')} aus dem aktuellen Angebot übernommen.`, 5000); }
    }
    const by = draftByCode();
    const dup = [...by.values()].filter((l) => l.length > 1).length;
    const missing = [...by.entries()].filter(([k, l]) => l.length === 1 && !masterOf(k)).length;
    const dev = master.articles.filter((e) => { const l = by.get(mKey(e.code)); return l && l.length === 1 && differs(e, l[0]); }).length;
    host.innerHTML = `
      <div class="st-info">
        <div><strong>Stammdaten</strong><span class="sub">Bezeichnung, Fleischart, Herkunft und Zustand je Artikelnummer – werden beim Excel-Import automatisch übernommen. „frisch“ gehört in den Zustand, nicht in die Bezeichnung.</span></div>
        <span class="ms-state" id="ms-state"></span>
      </div>
      <div class="ed-toolbar">
        <div class="search">${icon('search')}<input id="ms-q" type="search" autocomplete="off" placeholder="Nummer, Bezeichnung, Herkunft …" aria-label="Stammdaten durchsuchen" value="${esc(masterQ)}"></div>
        <span class="ed-hint" id="ms-count"></span>
        ${ro ? '' : `<span class="st-actions">
          <button type="button" class="btn" data-ma="from-draft"${missing ? '' : ' disabled'} title="Artikelnummern aus dem Angebot, die noch keine Stammdaten haben">${icon('plus')}Aus Angebot ergänzen${missing ? ` (${missing})` : ''}</button>
          <button type="button" class="btn" data-ma="apply-all"${dev ? '' : ' disabled'} title="Abweichende Artikel im Entwurf an die Stammdaten anpassen">${icon('check')}Auf Angebot anwenden${dev ? ` (${dev})` : ''}</button>
          <button type="button" class="btn primary" data-ma="new">${icon('plus')}Artikel anlegen</button>
        </span>`}
      </div>
      ${dup ? `<p class="hint" style="margin:-4px 0 12px">${plural(dup, 'Artikelnummer kommt', 'Artikelnummern kommen')} im Angebot mehrfach vor (verschiedene Artikel unter einer Nummer) und ${dup === 1 ? 'wird' : 'werden'} nicht automatisch abgeglichen.</p>` : ''}
      <div id="ms-list"></div>`;
    setMasterState(masterErr ? 'error' : 'saved', masterErr);
    renderMasterList();
  }
  function renderMasterList() {
    const host = $('#ms-list');
    if (!host || !master) return;
    const toks = fold(masterQ).split(/\s+/).filter(Boolean);
    const list = master.articles.filter((e) => { if (!toks.length) return true; const h = fold([e.code, e.name, e.origin, e.category, C.CONDITION_LABELS[e.condition]].join(' ')); return toks.every((t) => h.includes(t)); });
    $('#ms-count').textContent = `${fmtInt.format(list.length)} von ${plural(master.articles.length, 'Artikel', 'Artikeln')}`;
    const by = draftByCode();
    const rows = list.slice(0, 1500).map((e) => {
      const st = stockOf(e.code);
      return `<tr data-mcode="${esc(e.code)}">
        <td class="m-code">${esc(e.code)}</td>
        <td class="m-name"><input class="in" data-mf="name" value="${esc(e.name)}" maxlength="200" aria-label="Bezeichnung">${st && fold(st.name) !== fold(e.name) ? `<div class="m-winab" title="Bezeichnung in WinAB / Bestandsliste">WinAB: ${esc(st.name)}</div>` : ''}</td>
        <td class="m-cat"><select class="in" data-mf="category" aria-label="Fleischart">${CAT_OPTS(e.category)}</select></td>
        <td class="m-origin"><input class="in" data-mf="origin" value="${esc(e.origin || '')}" list="dl-origins" placeholder="nicht angegeben" maxlength="60" aria-label="Herkunft"></td>
        <td class="m-cond"><select class="in" data-mf="condition" aria-label="Zustand">${COND_OPTS(e.condition)}</select></td>
        <td class="m-offer">${offerStatus(e, by)}</td>
        <td class="m-act">${ro ? '' : `<button type="button" class="ibtn danger" data-ma="del" aria-label="Stammsatz ${esc(e.code)} löschen">${icon('trash')}</button>`}</td>
      </tr>`;
    }).join('');
    host.innerHTML = list.length ? `<div class="gcard"><table class="etab mtab"><thead><tr><th class="m-code">Art.-Nr.</th><th class="m-name">Bezeichnung</th><th class="m-cat">Fleischart</th><th class="m-origin">Herkunft</th><th class="m-cond">Zustand</th><th class="m-offer">Angebot</th><th class="m-act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="ed-empty"><h3>${master.articles.length ? 'Keine Treffer' : 'Noch keine Stammdaten'}</h3><p>${master.articles.length ? 'Suchbegriff anpassen.' : 'Mit „Aus Angebot ergänzen“ oder „Artikel anlegen“ beginnen.'}</p></div>`;
    lockInputs(host);
  }
  $('#view-master').addEventListener('input', (e) => {
    if (e.target.id === 'ms-q') { clearTimeout(qTimer); qTimer = setTimeout(() => { masterQ = e.target.value.trim(); renderMasterList(); }, 120); }
  });
  $('#view-master').addEventListener('change', (e) => {
    const el = e.target, tr = el.closest('tr[data-mcode]');
    if (!tr || !el.dataset.mf || ro) return;
    const ent = masterOf(tr.dataset.mcode);
    if (!ent) return;
    const f = el.dataset.mf;
    if (f === 'name') {
      const typed = C.clean(el.value);
      if (!typed) { el.value = ent.name; toast('Die Bezeichnung darf nicht leer sein.'); return; }
      const n = C.stripFrisch(typed);
      if (n !== typed) { if (ent.condition !== 'frisch-gefroren') { ent.condition = 'frisch'; tr.querySelector('[data-mf="condition"]').value = 'frisch'; } toast('„frisch“ steht im Zustand, nicht in der Bezeichnung.'); }
      ent.name = n; el.value = n;
    } else if (f === 'origin') { ent.origin = C.clean(el.value) || null; el.value = ent.origin || ''; }
    else ent[f] = el.value;
    tr.querySelector('.m-offer').innerHTML = offerStatus(ent, draftByCode());
    masterChanged();
  });
  $('#view-master').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-ma]');
    if (!b || ro) return;
    const a = b.dataset.ma, code = b.closest('tr[data-mcode]')?.dataset.mcode;
    if (a === 'retry') { saveMaster(); return; }
    if (a === 'from-draft') { const n = addFromDraft(); saveMaster(); toast(`${plural(n, 'Artikel', 'Artikel')} aus dem Angebot ergänzt.`); renderMasterView(); return; }
    if (a === 'apply-all' || a === 'apply1') {
      const preview = clone(model);
      const n = applyMasterTo(preview, a === 'apply1' ? code : null);
      if (!n) return;
      if (a === 'apply-all' && !(await confirmBox('Stammdaten auf das Angebot anwenden?', `${plural(n, 'Artikel', 'Artikel')} im Entwurf ${n === 1 ? 'wird' : 'werden'} an die Stammdaten angepasst (Bezeichnung, Fleischart, Herkunft, Zustand). Mit „Rückgängig“ wiederherstellbar.`, 'Anwenden'))) return;
      pushUndo();
      applyMasterTo(model, a === 'apply1' ? code : null);
      saveNote = { type: 'master' };
      changed({ render: true });
      toast(`${plural(n, 'Artikel', 'Artikel')} im Entwurf nach Stammdaten angepasst – noch nicht veröffentlicht.`, 5000);
      renderMasterView();
      return;
    }
    if (a === 'del' && code) {
      const ent = masterOf(code);
      if (!(await confirmBox('Stammsatz löschen?', `${esc(ent.code)} · ${esc(ent.name)} wird aus den Stammdaten entfernt. Das Angebot bleibt unverändert.`, 'Löschen', true))) return;
      master.articles = master.articles.filter((x) => x !== ent);
      saveMaster();
      renderMasterView();
      return;
    }
    if (a === 'new') openMasterNew();
  });

  /* Neuer Stammsatz */
  const dlgMN = $('#dlg-master-new');
  function openMasterNew(code = '') {
    $('#master-new-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="mn-title">Artikel anlegen</h2><p>Stammdaten gelten für alle künftigen Wochen und werden beim Excel-Import übernommen.</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body form-grid two">
        <label class="fld"><span>Artikelnummer</span><input name="code" value="${esc(code)}" maxlength="20" required autocomplete="off"></label>
        <label class="fld"><span>Zustand</span><select name="condition">${COND_OPTS('frisch')}</select></label>
        <label class="fld span2"><span>Bezeichnung</span><input name="name" maxlength="200" required></label>
        <label class="fld"><span>Fleischart</span><select name="category">${CAT_OPTS('Rind')}</select></label>
        <label class="fld"><span>Herkunft</span><input name="origin" list="dl-origins" placeholder="nicht angegeben" maxlength="60"></label>
        <p class="form-err span2" id="mn-err" role="alert"></p>
      </div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="submit" class="btn primary">${icon('plus')}Anlegen</button></div>`;
    dlgMN.showModal();
    $('#master-new-body [name="code"]').focus();
  }
  $('#master-new-body').addEventListener('change', (e) => {
    if (e.target.name !== 'code') return;
    const f = e.currentTarget.elements, st = stockOf(e.target.value.trim());
    if (st && !f.name.value) {
      const n = C.stripFrisch(st.name);
      f.name.value = n;
      const sug = C.suggestAttributes(st.name, '', '');
      f.category.value = sug.category; f.condition.value = sug.condition; if (sug.origin) f.origin.value = sug.origin;
    }
  });
  $('#master-new-body').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = e.target.elements, err = $('#mn-err');
    const code = f.code.value.trim();
    if (!/^[0-9A-Za-z./-]{1,20}$/.test(code)) { err.textContent = 'Ungültige Artikelnummer.'; return; }
    if (masterOf(code)) { err.textContent = `Für ${code} gibt es bereits Stammdaten.`; return; }
    const typed = C.clean(f.name.value);
    if (!typed) { err.textContent = 'Bitte eine Bezeichnung angeben.'; return; }
    const name = C.stripFrisch(typed);
    master.articles.push({ code, name, category: f.category.value, origin: C.clean(f.origin.value) || null, condition: name !== typed && f.condition.value !== 'frisch-gefroren' ? 'frisch' : f.condition.value });
    master.articles.sort((x, y) => x.code.localeCompare(y.code, 'de', { numeric: true }));
    dlgMN.close();
    saveMaster();
    masterQ = code;
    renderMasterView();
    toast(`Stammdaten für ${code} angelegt.`);
  });

  /* Artikel-Dialog: aktuellen Artikel als Stammdaten speichern */
  async function saveItemToMaster(it) {
    if (ro || !it.code) return;
    try { await loadMaster(); } catch (e) { toast(e.message); return; }
    const ent = masterOf(it.code);
    const rec = { code: ent ? ent.code : it.code, name: C.stripFrisch(it.name), category: it.category, origin: it.origin || null, condition: it.condition };
    if (ent) Object.assign(ent, rec); else { master.articles.push(rec); master.articles.sort((x, y) => x.code.localeCompare(y.code, 'de', { numeric: true })); }
    await saveMaster();
    toast(masterErr ? `Nicht gespeichert: ${masterErr}` : `Stammdaten für ${it.code} ${ent ? 'aktualisiert' : 'angelegt'}.`);
  }

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
        <td class="u-st">${u.active ? '<span class="st-ok">aktiv</span>' : '<span class="st-err">deaktiviert</span>'}${u.twofa ? ' <span class="tf-badge" title="Zwei-Faktor-Anmeldung eingerichtet">2FA</span>' : ''}${u.lockedUntil ? `<div class="sub st-err">gesperrt bis ${esc(timeOnly(new Date(u.lockedUntil * 1000).toISOString()))} Uhr</div>` : ''}${u.mustChange ? '<div class="sub">muss Passwort ändern</div>' : ''}</td>
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
        ${self ? '<p class="hint span2">Das eigene Passwort ändern Sie über „Passwort ändern“ im Menü.</p>' : `<div class="fld span2"><span>${u ? 'Neues Passwort setzen <small class="muted">(leer lassen = unverändert)</small>' : 'Passwort'}</span>
          <div class="pw-row"><input name="password" type="text" autocomplete="new-password" minlength="10" maxlength="200" placeholder="mindestens 10 Zeichen"${u ? '' : ' required'}><button type="button" class="btn" data-uact="gen">Vorschlag</button></div>
        </div>`}
        ${self ? '' : `<label class="check span2"><input type="checkbox" name="mustChange" checked> Nutzer muss das Passwort bei der nächsten Anmeldung ändern</label>`}
        ${u && u.twofa && !self ? '<label class="check span2"><input type="checkbox" name="reset2fa"> Zwei-Faktor-Anmeldung zurücksetzen (z. B. Handy verloren – wird beim nächsten Anmelden neu eingerichtet)</label>' : ''}
        ${u && u.lockedUntil ? `<p class="span2 st-err" style="margin:0">Zugang nach Fehlversuchen gesperrt bis ${esc(timeOnly(new Date(u.lockedUntil * 1000).toISOString()))} Uhr – Entsperren unter „Sicherheit“.</p>` : ''}
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
    const pw = f.password ? f.password.value.trim() : '';
    if (pw && pw.length < 10) { err.textContent = 'Das Passwort muss mindestens 10 Zeichen lang sein.'; return; }
    const u = editUid ? users.find((x) => x.id === editUid) : null;
    const body = {
      id: editUid || '', name: f.name.value.trim(), username: u ? u.username : f.username.value.trim(),
      role: (f.querySelector('[name="role"]:checked') || {}).value || (u && u.role), active: f.active.checked,
      password: pw, mustChange: f.mustChange ? f.mustChange.checked : false, reset2fa: f.reset2fa ? f.reset2fa.checked : false,
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
    ['stock', 'Bestand'],
    ['master', 'Stammdaten'],
    ['auth', 'Anmeldungen'],
    ['user', 'Nutzerverwaltung'],
    ['security', 'Sicherheit'],
  ];
  const typeOf = (a) => ({ draft: 'offer', import: 'offer', discard: 'offer', publish: 'publish', history: 'history', stock: 'stock', master: 'master', login: 'auth', logout: 'auth', login_fail: 'auth', password: 'auth', setup: 'user', user: 'user', security: 'security', twofa: 'auth' }[a] || '');
  const ACTION_LABEL = { draft: 'Entwurf bearbeitet', import: 'Entwurf ersetzt', discard: 'Entwurf verworfen', publish: 'Veröffentlicht', history: 'Preisverlauf', stock: 'Bestand', master: 'Stammdaten', login: 'Anmeldung', logout: 'Abmeldung', login_fail: 'Anmeldung fehlgeschlagen', password: 'Passwort', setup: 'Einrichtung', user: 'Nutzerverwaltung', security: 'Sicherheit', twofa: 'Zwei-Faktor' };
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
  const entryText = (e) => ((e.a === 'draft' && e.s === 'Entwurf bearbeitet') || (e.a === 'master' && e.s === 'Stammdaten bearbeitet') ? `${e.s}: ${draftSummary(e.d)}` : e.s);
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
    const q = csvCell;
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

  /* ======================= Sicherheit (nur Administrator) ======================= */
  let secData = null;
  const uaShort = (ua) => {
    const b = /Edg\//.test(ua) ? 'Edge' : /OPR\//.test(ua) ? 'Opera' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
    const o = /iPhone|iPad/.test(ua) ? 'iPhone/iPad' : /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows' : /Mac OS X/.test(ua) ? 'Mac' : /Linux/.test(ua) ? 'Linux' : '';
    return o ? `${b} · ${o}` : b;
  };
  let geoSel = new Set(), geoQ = '';
  const EUROPE = ['AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI', 'FR', 'GR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT', 'NL', 'PL', 'PT', 'RO', 'SE', 'SI', 'SK', 'CH', 'GB', 'NO', 'IS', 'LI'];
  let regionNames = null;
  try { regionNames = new Intl.DisplayNames(['de'], { type: 'region' }); } catch { /* alter Browser */ }
  const ccName = (c) => { let n = ''; try { n = regionNames ? regionNames.of(c) : ''; } catch { /* unbekannt */ } return n && n !== c ? n : c; };
  const ccSort = (a, b) => ccName(a).localeCompare(ccName(b), 'de');
  function geoChips() {
    const list = [...geoSel].sort(ccSort);
    return list.length ? list.map((c) => `<span class="geo-chip">${esc(ccName(c))} <span class="sub">${esc(c)}</span><button type="button" data-geo-del="${esc(c)}" aria-label="${esc(ccName(c))} entfernen">×</button></span>`).join('')
      : '<span class="sub">Noch kein Land ausgewählt.</span>';
  }
  const IP_RE = /^(\d{1,3}(\.\d{1,3}){3}|[0-9a-f:]*:[0-9a-f:.]+)$/i;
  let geoIp = null, geoIpTimer;
  function geoIpHit() {
    if (!geoIp || geoIp.ip !== geoQ) return IP_RE.test(geoQ) ? '<p class="sec-empty">IP-Adresse wird gesucht …</p>' : '';
    if (geoIp.error) return `<p class="sec-empty">${esc(geoIp.error)}</p>`;
    if (!geoIp.country) return `<p class="sec-empty"><span class="mono-s">${esc(geoIp.ip)}</span> – ${geoIp.private ? 'interne Adresse, keinem Land zugeordnet' : 'kein Land bekannt'}.</p>`;
    const c = geoIp.country;
    return `<label class="geo-opt geo-iphit"><input type="checkbox" data-geo-cc="${esc(c)}"${geoSel.has(c) ? ' checked' : ''}> <span><span class="mono-s">${esc(geoIp.ip)}</span> → ${esc(ccName(c))}</span><span class="sub">${esc(c)}</span></label>`;
  }
  function geoLookup() {
    clearTimeout(geoIpTimer);
    if (!IP_RE.test(geoQ)) { geoIp = null; return; }
    const ip = geoQ;
    geoIpTimer = setTimeout(async () => {
      try { const r = await api('geo_lookup', { query: '&ip=' + encodeURIComponent(ip) }); geoIp = { ip, country: r.country, private: r.private }; }
      catch (ex) { geoIp = { ip, error: ex.message }; }
      if (geoQ === ip && $('#geo-list')) $('#geo-list').innerHTML = geoList();
    }, 250);
  }
  function geoList() {
    if (IP_RE.test(geoQ)) return geoIpHit();
    const q = geoQ.toLowerCase();
    const all = (secData.geoCountries || []).filter((c) => !q || c.toLowerCase() === q || ccName(c).toLowerCase().includes(q)).sort(ccSort);
    return all.length ? all.map((c) => `<label class="geo-opt"><input type="checkbox" data-geo-cc="${esc(c)}"${geoSel.has(c) ? ' checked' : ''}> <span>${esc(ccName(c))}</span><span class="sub">${esc(c)}</span></label>`).join('')
      : '<p class="sec-empty">Kein Land gefunden.</p>';
  }
  function geoRefresh() {
    const f = $('#sec-form');
    if (!f) return;
    $('#geo-chips').innerHTML = geoChips();
    $('#geo-count').textContent = geoSel.size ? `${geoSel.size} ausgewählt` : '';
    const allow = f.elements.geoMode.value === 'allow';
    const mc = secData.myCountry;
    const blocked = mc && f.elements.geoEnabled.checked && (allow ? !geoSel.has(mc) : geoSel.has(mc));
    const ok = $('#geo-me');
    ok.className = 'geo-me' + (blocked ? ' bad' : '');
    ok.innerHTML = mc ? `Sie greifen gerade aus <strong>${esc(ccName(mc))}</strong> zu${blocked ? ' – mit dieser Auswahl würden Sie sich aussperren.' : '.'}` : 'Ihr Land ist nicht bekannt (interne Adresse) – Sie werden nicht gesperrt.';
    $('#geo-sel-label').textContent = allow ? 'Erlaubte Länder' : 'Gesperrte Länder';
  }
  const IDLE = [[15, '15 Minuten'], [30, '30 Minuten'], [60, '1 Stunde'], [120, '2 Stunden'], [240, '4 Stunden'], [480, '8 Stunden'], [720, '12 Stunden']];
  function backupCard(b, card) {
    if (!b || !b.t) return card('warn', 'Datensicherung', 'noch keine automatische Sicherung', 'Wird nach dem nächsten Server-Update täglich erstellt');
    const age = (Date.now() - new Date(b.t).getTime()) / 3600000;
    const when = `${dateTime(b.t)} Uhr`;
    if (!b.ok) return card('bad', 'Datensicherung', `letzter Versuch ${esc(when)} fehlgeschlagen`, esc(b.meldung || (b.fehler ? `${b.fehler} Datei(en) fehlerhaft` : 'Server prüfen')));
    if (b.inhalt === false) return card('warn', 'Datensicherung', `${esc(when)} · nur Archiv geprüft`, esc(b.meldung || 'Inhalt nicht geprüft'));
    if (age > 48) return card('bad', 'Datensicherung', `letzte Sicherung ${esc(when)}`, 'Älter als 2 Tage – Server prüfen');
    return card('ok', 'Datensicherung', `${esc(when)} · geprüft`, `${b.anzahl} Stände auf dem Server (${(b.groesse / 1024 / 1024).toFixed(1).replace('.', ',')} MB je Stand)`);
  }
  function deployCard(r, card) {
    if (!r || !r.t) return card('warn', 'Bereitstellung', 'Änderungen gehen ohne Freigabe live', 'Release-Modus noch nicht eingerichtet');
    const sha = esc(String(r.sha || '').slice(0, 7));
    if (!r.ok) return card('bad', 'Bereitstellung', `aktiv: ${sha} · ${esc(dateTime(r.t))} Uhr`, esc(r.meldung || 'Letztes Release fehlgeschlagen'));
    return card('ok', 'Bereitstellung', `Release ${sha} · ${esc(dateTime(r.t))} Uhr`, 'nur freigegebene, geprüfte Versionen');
  }
  function secCards(d) {
    const S = d.settings, users = d.users.filter((u) => u.active);
    const with2 = users.filter((u) => u.twofa).length, admins = users.filter((u) => u.role === 'admin'), admNo2 = admins.filter((u) => !u.twofa).length;
    const locked = d.users.filter((u) => u.lockedUntil).length, blocked = d.blockedIps.filter((x) => x.until).length;
    const card = (lvl, title, text, hint) => `<div class="sec-card ${lvl}"><span class="sec-dot"></span><div><strong>${esc(title)}</strong><span>${text}</span>${hint ? `<em>${hint}</em>` : ''}</div></div>`;
    return [
      card(d.https ? 'ok' : 'bad', 'Verbindung', d.https ? 'Verschlüsselt (HTTPS)' : 'Nicht verschlüsselt', d.https ? '' : 'Seite nur über https:// aufrufen'),
      card(with2 === users.length ? 'ok' : admNo2 ? 'bad' : 'warn', 'Zwei-Faktor-Anmeldung', `${with2} von ${users.length} aktiven Zugängen`, admNo2 ? `${admNo2} Administrator${admNo2 === 1 ? '' : 'en'} ohne Zwei-Faktor` : S.twofa === 'off' ? 'Pflicht ist ausgeschaltet' : ''),
      card(S.ipEnabled ? 'ok' : 'warn', 'Zugriff Eingabebereich', S.ipEnabled ? `nur von ${S.adminIps.length} freigegebene${S.adminIps.length === 1 ? 'r Adresse' : 'n Adressen'}` : 'aus dem ganzen Internet erreichbar', S.ipEnabled ? '' : 'Empfehlung: IP-Freigabe einschalten oder Zwei-Faktor-Pflicht'),
      card(d.fails24 >= 20 ? 'bad' : d.fails24 >= 5 ? 'warn' : 'ok', 'Fehlgeschlagene Anmeldungen', `${fmtInt.format(d.fails24)} in den letzten 24 Stunden`, d.fails24 >= 20 ? 'Möglicher Angriff – Liste unten prüfen' : ''),
      card(blocked || locked ? 'warn' : 'ok', 'Gesperrt', `${blocked} IP-Adresse${blocked === 1 ? '' : 'n'} · ${locked} Zugang${locked === 1 ? '' : 'e'}`, ''),
      backupCard(d.backup, card),
      deployCard(d.deployment, card),
      card(S.geoEnabled ? 'ok' : 'warn', 'Ländersperre', S.geoEnabled ? `${S.geoMode === 'allow' ? `nur ${S.geoCountries.length} Länder erlaubt` : `${S.geoCountries.length} ${S.geoCountries.length === 1 ? 'Land' : 'Länder'} gesperrt`} · ${S.geoScope === 'all' ? 'ganze Seite' : 'Eingabebereich'}` : 'aus', S.geoEnabled ? `${fmtInt.format(d.geoBlocked7 || 0)} abgewiesene Zugriffe in 7 Tagen` : 'Optional: Zugriffe aus bestimmten Ländern sperren'),
      card(S.pwMin >= 12 && S.pwComplex ? 'ok' : 'warn', 'Passwortregeln', `mind. ${S.pwMin} Zeichen${S.pwComplex ? ', gemischte Zeichen' : ''}`, S.pwMin >= 12 && S.pwComplex ? '' : 'Empfehlung: 12 Zeichen und Komplexität'),
    ].join('');
  }
  async function renderSecView() {
    const host = $('#view-sec');
    if (!secData) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Sicherheitsübersicht wird geladen …</div>';
    try { secData = await api('security_status'); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    const d = secData, S = d.settings;
    geoSel = new Set(S.geoCountries || []); geoQ = '';
    const G = d.geo;
    const geoStatRows = (d.geoStats || []).map((x) => `<tr><td>${esc(ccName(x.cc))} <span class="sub">${esc(x.cc)}</span></td><td class="num-s">${fmtInt.format(x.n)}</td><td class="num-s">${esc(dateTime(x.last))}</td></tr>`).join('');
    const no2 = d.users.filter((u) => u.active && !u.twofa);
    const sessRows = d.sessions.map((x) => `<tr><td><div class="nm">${esc(x.name)}</div><div class="sub uname">${esc(x.username)}</div></td><td class="mono-s">${esc(x.ip)}</td><td>${esc(uaShort(x.ua))}</td>
        <td class="num-s">${esc(dateTime(x.created))}</td><td class="num-s">${esc(dateTime(x.seen))}</td>
        <td class="act">${x.current ? '<span class="muted">diese Sitzung</span>' : `<button type="button" class="btn sm" data-sec="end" data-sid="${esc(x.sid)}">Beenden</button>`}</td></tr>`).join('');
    const ipRows = d.blockedIps.map((x) => `<tr><td class="mono-s">${esc(x.ip)}</td><td class="num-s">${x.n ? fmtInt.format(x.n) + ' Fehlversuch' + (x.n === 1 ? '' : 'e') : ''}</td><td>${x.until ? `<span class="st-err">gesperrt bis ${esc(timeOnly(x.until))} Uhr</span>` : '<span class="muted">beobachtet</span>'}</td><td class="act"><button type="button" class="btn sm" data-sec="unblock" data-key="${esc(x.key)}">Aufheben</button></td></tr>`).join('');
    const lockRows = d.users.filter((u) => u.lockedUntil).map((u) => `<tr><td><div class="nm">${esc(u.name)}</div><div class="sub uname">${esc(u.username)}</div></td><td colspan="2"><span class="st-err">gesperrt bis ${esc(timeOnly(new Date(u.lockedUntil * 1000).toISOString()))} Uhr</span></td><td class="act"><button type="button" class="btn sm" data-sec="unlock" data-uid="${esc(u.id)}">Entsperren</button></td></tr>`).join('');
    const failRows = d.fails.map((f) => `<tr><td class="num-s">${esc(dateTime(f.t))}</td><td>${esc(f.u || '—')}</td><td class="mono-s">${esc(f.ip)}</td><td>${esc(f.s)}</td></tr>`).join('');
    host.innerHTML = `
      <div class="sec-grid">${secCards(d)}</div>
      <form class="gcard sec-form" id="sec-form" autocomplete="off">
        <h3 class="sec-h">Einstellungen</h3>
        <div class="sec-rows">
          <label class="fld"><span>Zwei-Faktor-Anmeldung verpflichtend</span><select name="twofa">
            <option value="off"${S.twofa === 'off' ? ' selected' : ''}>freiwillig</option>
            <option value="admins"${S.twofa === 'admins' ? ' selected' : ''}>für Administratoren</option>
            <option value="all"${S.twofa === 'all' ? ' selected' : ''}>für alle Zugänge</option></select>
            <small>Wer sie noch nicht eingerichtet hat, wird beim nächsten Anmelden dazu aufgefordert.</small></label>
          <label class="fld"><span>Automatisch abmelden nach Inaktivität</span><select name="idleMinutes">${IDLE.map(([v, l]) => `<option value="${v}"${S.idleMinutes === v ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
          <div class="fld"><span>Passwörter</span><div class="sec-inline"><label>mindestens <input type="number" name="pwMin" min="10" max="32" value="${S.pwMin}"> Zeichen</label>
            <label class="check"><input type="checkbox" name="pwComplex"${S.pwComplex ? ' checked' : ''}> Groß-/Kleinbuchstaben, Ziffern oder Sonderzeichen verlangen</label></div>
            <small>Gilt für neue Passwörter. Allerweltspasswörter und der eigene Benutzername sind immer gesperrt.</small></div>
          <div class="fld"><span>Kontosperre</span><div class="sec-inline"><label>nach <input type="number" name="lockAfter" min="3" max="20" value="${S.lockAfter}"> Fehlversuchen</label><label>für <input type="number" name="lockMinutes" min="5" max="1440" value="${S.lockMinutes}"> Minuten</label></div>
            <small>Zusätzlich wird jede IP-Adresse nach 5 Fehlversuchen für 10 Minuten gesperrt.</small></div>
          <div class="fld span2"><span>Eingabebereich nur von bestimmten Internetadressen</span>
            <label class="check"><input type="checkbox" name="ipEnabled"${S.ipEnabled ? ' checked' : ''}> IP-Freigabe einschalten – die öffentliche Angebotsseite bleibt für alle erreichbar</label>
            <textarea name="adminIps" rows="3" placeholder="eine Adresse oder ein Bereich pro Zeile, z. B. 80.147.24.150 oder 80.147.24.0/24">${esc(S.adminIps.join('\n'))}</textarea>
            <div class="sec-inline"><small>Ihre aktuelle Adresse: <strong class="mono-s">${esc(d.myIp)}</strong>${d.myCountry ? ` · ${esc(ccName(d.myCountry))}` : ''}</small><button type="button" class="btn sm" data-sec="addip">${icon('plus', 'sm')}Hinzufügen</button></div></div>
          <div class="fld span2 geo-box" id="geo-box"><span>Länder sperren</span>
            <label class="check"><input type="checkbox" name="geoEnabled"${S.geoEnabled ? ' checked' : ''}> Ländersperre einschalten</label>
            <div class="geo-opts">
              <div class="geo-radio" role="radiogroup" aria-label="Art der Sperre">
                <label class="check"><input type="radio" name="geoMode" value="block"${S.geoMode !== 'allow' ? ' checked' : ''}> ausgewählte Länder sperren</label>
                <label class="check"><input type="radio" name="geoMode" value="allow"${S.geoMode === 'allow' ? ' checked' : ''}> nur ausgewählte Länder erlauben</label>
              </div>
              <label class="geo-scope">gilt für <select name="geoScope">
                <option value="admin"${S.geoScope !== 'all' ? ' selected' : ''}>nur den Eingabebereich</option>
                <option value="all"${S.geoScope === 'all' ? ' selected' : ''}>die ganze Seite (auch öffentliches Angebot)</option></select></label>
            </div>
            <div class="geo-me" id="geo-me"></div>
            <div class="geo-pick">
              <div class="geo-selbox"><div class="geo-hd"><strong id="geo-sel-label">Gesperrte Länder</strong><span class="sub" id="geo-count"></span>
                <span class="geo-quick"><button type="button" class="btn sm ghost" data-sec="geo-eu" title="EU-Länder sowie Schweiz, Großbritannien, Norwegen, Island und Liechtenstein">Europa auswählen</button><button type="button" class="btn sm ghost" data-sec="geo-none">Auswahl leeren</button></span></div>
                <div class="geo-chips" id="geo-chips"></div></div>
              <div class="geo-search"><input type="search" id="geo-q" placeholder="Land oder IP-Adresse, z. B. China, CN oder 1.0.1.1" aria-label="Land oder IP-Adresse suchen"><div class="geo-list" id="geo-list">${geoList()}</div></div>
            </div>
            <small>Adressen aus der IP-Freigabeliste oben sind immer erlaubt. Adressen ohne bekannte Länderzuordnung werden nicht gesperrt. Die Zuordnung stimmt in den allermeisten Fällen, kann aber über VPN-Dienste umgangen werden – sie ergänzt Passwort und Zwei-Faktor-Anmeldung, ersetzt sie aber nicht.</small>
            <div class="sec-inline geo-db"><small>${G ? `Länderdaten: Stand ${esc(new Date(G.date + 'T12:00:00Z').toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }))} · ${fmtInt.format(G.v4 + G.v6)} Adressbereiche` : '<span class="st-err">Länderdaten fehlen</span>'}</small><button type="button" class="btn sm" data-sec="geo-update">${icon('download', 'sm')}Länderdaten aktualisieren</button></div>
          </div>
        </div>
        <p class="form-err" id="sec-err" role="alert"></p>
        <div class="sec-foot"><button type="submit" class="btn primary">${icon('check')}Einstellungen speichern</button></div>
      </form>
      ${geoStatRows ? `<section class="gcard sec-block"><h3 class="sec-h">Abgewiesene Zugriffe nach Land <span class="muted">(7 Tage: ${fmtInt.format(d.geoBlocked7 || 0)})</span><button type="button" class="btn sm ghost sec-h-act" data-sec="geo-clear">Zurücksetzen</button></h3>
        <table class="etab sectab"><thead><tr><th>Land</th><th class="num-s">Zugriffe gesamt</th><th class="num-s">zuletzt</th></tr></thead><tbody>${geoStatRows}</tbody></table></section>` : ''}
      <section class="gcard sec-block"><h3 class="sec-h">Aktive Sitzungen <span class="muted">(${d.sessions.length})</span></h3>
        <table class="etab sectab"><thead><tr><th>Nutzer</th><th>IP-Adresse</th><th>Gerät</th><th>angemeldet</th><th>zuletzt aktiv</th><th class="act"></th></tr></thead><tbody>${sessRows}</tbody></table></section>
      <section class="gcard sec-block"><h3 class="sec-h">Sperren</h3>
        ${ipRows || lockRows ? `<table class="etab sectab"><thead><tr><th>IP-Adresse / Zugang</th><th></th><th>Status</th><th class="act"></th></tr></thead><tbody>${lockRows}${ipRows}</tbody></table>` : '<p class="sec-empty">Keine gesperrten IP-Adressen oder Zugänge.</p>'}</section>
      <section class="gcard sec-block"><h3 class="sec-h">Zugänge ohne Zwei-Faktor-Anmeldung <span class="muted">(${no2.length})</span></h3>
        ${no2.length ? `<p class="sec-list">${no2.map((u) => `<span class="role-b r-${esc(u.role)}">${esc(u.name)} · ${esc(u.username)}</span>`).join(' ')}</p>` : '<p class="sec-empty">Alle aktiven Zugänge nutzen die Zwei-Faktor-Anmeldung.</p>'}</section>
      <section class="gcard sec-block"><h3 class="sec-h">Fehlgeschlagene Anmeldungen <span class="muted">(7 Tage)</span></h3>
        ${failRows ? `<table class="etab sectab"><thead><tr><th>Zeitpunkt</th><th>Benutzername</th><th>IP-Adresse</th><th>Vorgang</th></tr></thead><tbody>${failRows}</tbody></table>` : '<p class="sec-empty">Keine fehlgeschlagenen Anmeldungen.</p>'}</section>
      <p class="hint sec-note">Weitere Schutzmaßnahmen sind fest eingebaut: HTTPS mit HSTS, Schutz gegen eingeschleuste Skripte (Content-Security-Policy), Schutz gegen fremde Formulare (CSRF), sichere Sitzungs-Cookies, gesperrte Datenordner und ein lückenloses Protokoll.</p>`;
    geoRefresh();
  }
  $('#view-sec').addEventListener('input', (e) => {
    if (e.target.id === 'geo-q') { geoQ = e.target.value.trim(); geoLookup(); $('#geo-list').innerHTML = geoList(); }
  });
  $('#view-sec').addEventListener('change', (e) => {
    const cc = e.target.dataset && e.target.dataset.geoCc;
    if (cc) { if (e.target.checked) geoSel.add(cc); else geoSel.delete(cc); $('#sec-err').textContent = ''; geoRefresh(); return; }
    if (['geoEnabled', 'geoMode'].includes(e.target.name)) geoRefresh();
  });
  $('#view-sec').addEventListener('click', async (e) => {
    const del = e.target.closest('[data-geo-del]');
    if (del) { geoSel.delete(del.dataset.geoDel); geoRefresh(); $('#geo-list').innerHTML = geoList(); return; }
    const b = e.target.closest('[data-sec]');
    if (!b) return;
    const a = b.dataset.sec;
    if (a === 'geo-eu' || a === 'geo-none') {
      if (a === 'geo-none') geoSel.clear(); else EUROPE.forEach((c) => geoSel.add(c));
      geoRefresh(); $('#geo-list').innerHTML = geoList(); return;
    }
    if (a === 'geo-update') {
      b.disabled = true; const t = b.innerHTML; b.innerHTML = '<span class="spinner sm"></span>Wird geladen …';
      try { const r = await api('geo_update', { body: {} }); toast(`Länderdaten aktualisiert (Stand ${new Date(r.geo.date + 'T12:00:00Z').toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' })}).`); secData.geo = r.geo; renderSecView(); }
      catch (ex) { toast(ex.message); b.disabled = false; b.innerHTML = t; }
      return;
    }
    if (a === 'geo-clear') {
      try { await api('geo_clear_stats', { body: {} }); toast('Zähler zurückgesetzt.'); renderSecView(); } catch (ex) { toast(ex.message); }
      return;
    }
    if (a === 'addip') {
      const ta = $('#sec-form [name="adminIps"]');
      const list = ta.value.split(/\s+/).filter(Boolean);
      if (!list.includes(secData.myIp)) ta.value = [...list, secData.myIp].join('\n');
      return;
    }
    try {
      if (a === 'end') await api('session_end', { body: { sid: b.dataset.sid } });
      if (a === 'unblock') await api('ip_unblock', { body: { key: b.dataset.key } });
      if (a === 'unlock') await api('user_unlock', { body: { id: b.dataset.uid } });
      toast(a === 'end' ? 'Sitzung beendet.' : a === 'unblock' ? 'IP-Sperre aufgehoben.' : 'Zugang entsperrt.');
      renderSecView();
    } catch (ex) { toast(ex.message); }
  });
  $('#view-sec').addEventListener('submit', async (e) => {
    if (e.target.id !== 'sec-form') return;
    e.preventDefault();
    const f = e.target.elements;
    const body = {
      twofa: f.twofa.value, idleMinutes: +f.idleMinutes.value, pwMin: +f.pwMin.value, pwComplex: f.pwComplex.checked,
      lockAfter: +f.lockAfter.value, lockMinutes: +f.lockMinutes.value, ipEnabled: f.ipEnabled.checked,
      adminIps: f.adminIps.value.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean),
      geoEnabled: f.geoEnabled.checked, geoMode: f.geoMode.value, geoScope: f.geoScope.value, geoCountries: [...geoSel],
    };
    $('#sec-err').textContent = '';
    const S0 = secData.settings;
    if (body.geoEnabled && !body.geoCountries.length) { $('#sec-err').textContent = body.geoMode === 'allow' ? 'Bitte mindestens ein erlaubtes Land auswählen.' : 'Bitte mindestens ein Land zum Sperren auswählen.'; return; }
    if (body.geoEnabled && (!S0.geoEnabled || S0.geoMode !== body.geoMode || S0.geoScope !== body.geoScope || S0.geoCountries.join() !== [...body.geoCountries].sort().join())) {
      const names = body.geoCountries.sort(ccSort).map(ccName);
      const what = body.geoMode === 'allow' ? `Zugriffe sind danach nur noch aus ${names.length > 8 ? names.length + ' ausgewählten Ländern' : names.join(', ')} möglich.` : `Zugriffe aus ${names.length > 8 ? names.length + ' Ländern' : names.join(', ')} werden danach abgewiesen.`;
      const where = body.geoScope === 'all' ? 'Das gilt für die ganze Seite – auch Kunden in diesen Ländern sehen das Angebot dann nicht.' : 'Das gilt nur für den Eingabebereich; das öffentliche Angebot bleibt für alle sichtbar.';
      if (!(await confirmBox('Ländersperre speichern?', `${esc(what)} ${esc(where)} Im Notfall lässt sich die Sperre auf dem Server zurücksetzen (siehe LIESMICH).`, 'Speichern'))) return;
    }
    if (body.ipEnabled && !(await confirmBox('IP-Freigabe einschalten?', `Der Eingabebereich ist danach nur noch von ${body.adminIps.map(esc).join(', ')} erreichbar. Die öffentliche Angebotsseite bleibt frei. Im Notfall lässt sich die Freigabe auf dem Server zurücksetzen (siehe LIESMICH).`, 'Einschalten'))) return;
    try {
      await api('security_save', { body });
      toast('Sicherheitseinstellungen gespeichert.');
      renderSecView();
    } catch (ex) { $('#sec-err').textContent = ex.message; }
  });

  /* Höhe der Kopfleiste für die links angeheftete Navigation */
  try {
    const tb = $('#topbar');
    const setH = () => document.documentElement.style.setProperty('--topbar-h', tb.offsetHeight + 'px');
    new ResizeObserver(setH).observe(tb); setH();
  } catch { /* ältere Browser: fester Wert aus CSS */ }

  /* ======================= Start ======================= */
  (async function boot() {
    try {
      const s = await api('status');
      company = s.company || '';
      $$('[data-company]').forEach((el) => { el.textContent = company; el.hidden = !company; });
      if (s.setupRequired) { showAuth('setup'); return; }
      if (s.setupLocked) throw Object.assign(new Error('Es ist kein Zugang vorhanden oder die Nutzerdaten sind nicht lesbar. Eine Ersteinrichtung im Browser ist aus Sicherheitsgründen gesperrt – bitte den Zugang auf dem Server wiederherstellen (deploy/passwort-zuruecksetzen.sh).'), { status: 403 });
      if (!s.loggedIn) { showAuth('login'); return; }
      csrf = s.csrf;
      me = s.user;
      if (me.mustChange) { try { await api('logout', { body: {} }); } catch { /* ignore */ } me = null; showAuth('login'); return; }
      if (me.needTwofa) { showAuth('twofa'); return; }
      await openEditor();
    } catch (e) {
      document.body.innerHTML = `<main class="auth"><div class="auth-card"><h1 style="margin:0;font-size:18px">Eingabebereich nicht erreichbar</h1><p class="auth-intro">${esc(e.message)}</p>${e.status === 403 ? '' : '<p class="auth-intro">Die Seite muss über den Webserver aufgerufen werden, PHP muss aktiv sein.</p>'}</div></main>`;
    }
  })();
})();
