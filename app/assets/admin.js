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
  let base = null;           // zuletzt mit dem Server abgeglichener Stand (Grundlage für den Abgleich)
  let editors = [];          // andere Mitarbeiter, die gerade im Eingabebereich sind
  let savedAt = null;
  let diff = null;
  let undoStack = [];
  const invalid = new Map(); // Artikel-ID → ungültiger Preistext
  const autoAttr = new Set();// neue Artikel: Attribute folgen der Bezeichnung
  let filterQ = '', onlyChanges = false;
  /* Mehrere Angebote: Standard („Wochenangebot“) + Kundenangebote mit eigenen Preisen je Artikel (it.variants[id]) */
  const OSTD = 'std';
  let offers = [], offersRev = 0, stdPublic = true;
  let curOffer = store.get('angebot', OSTD);
  const offerDef = (id) => offers.find((o) => o.id === id) || null;
  const offerName = (id) => (id === OSTD ? 'Wochenangebot' : (offerDef(id) || {}).name || id);
  const offerShort = (id) => (id === OSTD ? 'Wochenangebot' : offerName(id).replace(/^Wochenangebot[\s–-]*/i, '') || offerName(id));
  const knownOffer = (id) => id === OSTD || !!offerDef(id);
  /* Wirksamer Preis eines Artikels in einem Angebot; null = dort ausgeblendet */
  /* Ausgeblendet in einem Angebot (Auge) – auch im Wochenangebot (variants.std = {status: 'hidden'}) */
  const isHid = (it, oid) => !!(it && it.variants && it.variants[oid] && it.variants[oid].status === 'hidden');
  /* Sonderposten ohne Bestand werden in allen Angeboten automatisch ausgeblendet (wie auf dem Server) */
  const soldOut = (it) => !!(stock && it.code && !stockOf(it.code));
  function effPrice(it, oid) {
    if (oid === OSTD) return isHid(it, OSTD) ? null : it.price || { status: 'none' };
    const v = it.variants && it.variants[oid];
    if (v) return v.status === 'hidden' ? null : v.status === 'value' ? { status: 'value', value: v.value } : { status: 'request' };
    const d = offerDef(oid);
    return d && d.fallback === 'hidden' ? null : (it.price || { status: 'none' });
  }
  function variantShort(v, oid) {
    if (oid === OSTD) return v && v.status === 'hidden' ? 'ausgeblendet' : 'sichtbar';
    if (!v) { const d = offerDef(oid); return d && d.fallback === 'hidden' ? 'ausgeblendet (kein eigener Preis)' : 'Standardpreis'; }
    if (v.status === 'hidden') return 'ausgeblendet';
    return v.status === 'value' ? fmtNum.format(v.value) + ' €/kg' : 'auf Anfrage';
  }
  const ownCount = (oid) => (model ? model.items.filter((i) => i.variants && i.variants[oid] && i.variants[oid].status !== 'hidden').length : 0);
  const vChanges = () => (diff && diff.variantChanged ? diff.variantChanged.filter((c) => knownOffer(c.offer)) : []);
  const sChanges = () => (diff && diff.saleChanged ? diff.saleChanged : []);
  const saleText = (sl) => {
    if (!sl) return 'kein Sonderpreis';
    const ex = Object.entries(sl.offers || {}).map(([o, x]) => `${offerShort(o)}: ${x.status === 'none' ? 'keiner' : fmtNum.format(x.value)}`);
    return `${fmtNum.format(sl.value)} €/kg${ex.length ? ' (' + ex.join(', ') + ')' : ''}`;
  };

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
    if (res.status === 403 && data?.code === 'confirmation_required' && !opts.confirmationRetry) {
      await confirmAdminAction();
      return api(action, { ...opts, confirmationRetry: true });
    }
    if (!res.ok || !data || !data.ok) {
      const msg = data && data.error ? data.error : res.status === 404 && !data ? 'API nicht gefunden – liegt der Ordner „api“ auf dem Server und ist PHP aktiv?' : `Serverfehler (${res.status}).`;
      throw Object.assign(new Error(msg), { status: res.status });
    }
    return data;
  }

  /* Passwort nur für die Bestätigung übertragen, nicht speichern oder erneut mitsenden. */
  let adminConfirmation = null;
  function confirmAdminAction() {
    if (adminConfirmation) return adminConfirmation;
    adminConfirmation = new Promise((resolve, reject) => {
      const d = $('#dlg-reauth'), form = $('#reauth-form'), input = $('#reauth-password');
      const err = $('#reauth-error'), btn = $('#reauth-submit');
      let settled = false;
      form.reset(); err.textContent = ''; btn.disabled = false;
      const finish = (error = null) => {
        if (settled) return;
        settled = true;
        d.removeEventListener('close', onClose);
        if (d.open) d.close();
        form.reset(); form.onsubmit = null;
        adminConfirmation = null;
        if (error) reject(error); else resolve();
      };
      const onClose = () => finish(new Error('Bestätigung abgebrochen. Die Änderung wurde nicht ausgeführt.'));
      d.addEventListener('close', onClose);
      form.onsubmit = async (e) => {
        e.preventDefault();
        if (btn.disabled) return;
        btn.disabled = true; err.textContent = '';
        const password = input.value;
        input.value = '';
        try {
          await api('reauth', { body: { password } });
          finish();
        } catch (ex) {
          if (settled) return;
          if (ex.status === 401) { finish(ex); return; }
          err.textContent = ex.message;
          btn.disabled = false; input.focus();
        }
      };
      d.showModal(); input.focus();
    });
    return adminConfirmation;
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
    $('#vt-orders').hidden = !can('editor');
    $('#vt-kunden').hidden = !can('admin');
    $('#vt-mail').hidden = !can('admin');
    $('#vt-log').hidden = !can('admin');
    $('#vt-sec').hidden = !can('admin');
    $('#side-admin').hidden = !can('admin');
    $('#menu-user').innerHTML = me ? `<strong>${esc(me.name)}</strong><span>${esc(me.username)} · ${esc(ROLE_LABEL[me.role])}</span>` : '';
    if (!can('admin') && ADMIN_VIEWS.includes(currentView)) setView('edit');
    if (!can('editor') && currentView === 'orders') setView('edit');
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
    delete c.savedAt; delete c.savedBy; delete c.publishedAt; delete c.rev; delete c.issues;
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
  /* Wartungsmodus: Hinweis für alle Mitarbeiter oben im Eingabebereich */
  let wartungSt = null;
  const wartungBis = (w) => (w && w.until ? ` · voraussichtlich bis ${new Date(w.until).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })} Uhr` : '');
  function renderWartungBanner() {
    const b = $('#adm-wartung');
    if (!b) return;
    b.hidden = !wartungSt;
    if (wartungSt) b.innerHTML = `${icon('info', 'sm')}<span><strong>Wartungsmodus aktiv</strong> – Kunden sehen auf der Angebotsseite nur einen Wartungshinweis${esc(wartungBis(wartungSt))}.</span>${can('admin') ? '<button type="button" class="btn sm" data-wartung="goto">Verwalten</button>' : ''}`;
  }
  async function refreshWartung() { try { wartungSt = (await api('status')).wartung || null; } catch { /* Hinweis später */ } renderWartungBanner(); }
  document.addEventListener('click', (e) => { if (e.target.closest('[data-wartung="goto"]')) setView('sec'); });

  async function openEditor() {
    refreshWartung();
    const d = await api('draft');
    published = d.published ? strip(d.published) : null;
    model = d.draft ? strip(d.draft) : published ? clone(published) : emptyModel();
    base = clone(model);
    revision = d.revision || 0;
    savedAt = d.draftSavedAt;
    $('#screen-editor').hidden = false;
    $('#screen-auth').hidden = true;
    undoStack = [];
    invalid.clear();
    applyRole();
    await loadOffers().catch(() => {});
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
    startSync();
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
    lastSaveState = [st, msg];
    el.innerHTML = `<span class="dot"></span><span>${text}</span>${editorsHTML()}`;
  }
  let lastSaveState = ['clean'];
  function editorsHTML() {
    if (!editors.length) return '';
    const names = editors.map((e) => e.name).filter(Boolean);
    const shown = names.slice(0, 3).join(', ') + (names.length > 3 ? ` und ${names.length - 3} weitere` : '');
    return `<span class="editors" title="Ebenfalls gerade im Eingabebereich: ${esc(names.join(', '))}">${icon('users', 'sm')}Auch hier: ${esc(shown)}</span>`;
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
    renderOfferBar();
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
    const sent = clone(model);
    try {
      const r = await api('save_draft', { body: { model: sent, revision, note } });
      if (saveNote === note) saveNote = null;
      revision = r.revision;
      base = sent;
      savedAt = r.savedAt;
      saveError = null;
      conflictTries = 0;
      setSaveState(C.sameModel(base, model) ? 'saved' : 'pending');
      if (pendingRemote) renderRemote();
    } catch (e) {
      if (e.status === 409 && conflictTries < 3) {
        // Jemand anderes hat inzwischen gespeichert: dessen Stand übernehmen, eigene Änderungen darauf anwenden, erneut speichern
        conflictTries++;
        try { await pullRemote(); queued = true; } catch (e2) { saveError = e2.message; setSaveState('error', e2.message); }
      } else {
        saveError = e.message;
        if (e.status !== 401) setSaveState('error', e.message);
      }
    } finally {
      saving = false;
      if (queued) { queued = false; saveNow(); }
    }
  }
  const unsaved = () => saving || saveTimer && $('#save-state').classList.contains('pending') || !!saveError;
  let conflictTries = 0;

  /* ======================= Gemeinsames Bearbeiten =======================
     Alle paar Sekunden: Stand des Entwurfs abfragen. Haben andere gespeichert, werden deren Änderungen
     übernommen und mit den eigenen zusammengeführt (je Feld, je Artikel, je Kundenpreis). */
  let syncTimer = null, pendingRemote = null, pulling = false, pullPromise = null;
  const savePending = () => saving || queued || $('#save-state').classList.contains('pending');
  function startSync() {
    clearInterval(syncTimer);
    syncTimer = setInterval(syncTick, 8000);
  }
  document.addEventListener('visibilitychange', () => { if (!document.hidden) syncTick(); });
  async function syncTick() {
    if (!model || !csrf || document.hidden || $('#screen-editor').hidden || !$('#screen-auth').hidden) return;
    if (pendingRemote) renderRemote();
    let d;
    try { d = await api('draft_ping', { body: {} }); } catch { return; }
    const ed = d.editors || [];
    if (JSON.stringify(ed) !== JSON.stringify(editors)) { editors = ed; setSaveState(...lastSaveState); }
    if ((d.offersRev || 0) !== offersRev) { try { await loadOffers(); renderOfferBar(); renderRemote([]); } catch { /* später */ } }
    if (d.revision !== revision && !savePending() && !pulling) pullRemote().catch(() => {});
  }
  /* Laufenden Abgleich abwarten und danach frisch holen – wer gerade einen Konflikt auflöst,
     braucht den Stand nach der fremden Speicherung, nicht den eines älteren Abrufs. */
  async function pullRemote() {
    while (pullPromise) { try { await pullPromise; } catch { /* weiter mit frischem Abruf */ } }
    pulling = true;
    pullPromise = pullOnce();
    try { return await pullPromise; } finally { pullPromise = null; pulling = false; }
  }
  async function pullOnce() {
    {
      const d = await api('draft', { query: '&bg=1' });
      const theirs = d.draft ? strip(d.draft) : d.published ? strip(d.published) : emptyModel();
      published = d.published ? strip(d.published) : null;
      const r = C.mergeModels(base, model, theirs);
      base = theirs;
      revision = d.revision || 0;
      savedAt = d.draftSavedAt;
      if (r.changed) {
        model = r.model;
        for (const id of r.removed) invalid.delete(id);
        undoStack = []; $('#btn-undo').disabled = true;
      }
      renderRemote(r.remoteItems);
      const who = d.draftSavedBy || 'Jemand anderes';
      if (r.conflicts.length) {
        const c = r.conflicts[0];
        toast(c.field === 'deleted'
          ? `„${c.name}“ wurde ${c.by === 'mine' ? 'von Ihnen' : 'von ' + who} gelöscht – die Änderung daran entfällt.`
          : `${who} hat „${c.name}“ ebenfalls geändert – Ihre Eingabe gilt${r.conflicts.length > 1 ? ` (${r.conflicts.length} Felder)` : ''}.`, 7000);
      } else if (r.changed) {
        toast(`Änderungen von ${who} übernommen.`);
      }
      if (!ro && !C.sameModel(base, model)) {
        setSaveState('pending');
        clearTimeout(saveTimer);
        saveTimer = setTimeout(saveNow, 700);
      } else if (!saving) setSaveState(d.draft ? 'saved' : 'clean');
      return r;
    }
  }
  /* Neu zeichnen, ohne eine angefangene Eingabe zu zerstören */
  function editingNow() {
    const a = document.activeElement;
    if ($('dialog[open]')) return true;
    return !!(a && a.closest && a.closest('#screen-editor') && /^(INPUT|TEXTAREA)$/.test(a.tagName) && a.value !== a.defaultValue);
  }
  function renderRemote(ids) {
    if (ids) pendingRemote = [...new Set([...(pendingRemote || []), ...ids])];
    if (!pendingRemote || editingNow()) return;
    const hit = pendingRemote;
    pendingRemote = null;
    const a = document.activeElement;
    const tr = a && a.closest ? a.closest('tr[data-id]') : null;
    const f = a && a.dataset ? a.dataset.f : null;
    const metaId = a && /^m-/.test(a.id || '') ? a.id : null;
    let sel = null; try { sel = [a.selectionStart, a.selectionEnd]; } catch { /* kein Textfeld */ }
    renderMeta();
    diff = C.diffOffers(published, model);
    renderOfferBar();
    renderGroups();
    renderNoPrice();
    renderChanges();
    updatePublishBtn();
    const n = tr && f ? $(`tr[data-id="${CSS.escape(tr.dataset.id)}"] [data-f="${f}"]`) : metaId ? $('#' + metaId) : null;
    if (n) { n.focus(); try { if (sel && sel[0] != null) n.setSelectionRange(sel[0], sel[1]); } catch { /* kein Textfeld */ } }
    for (const id of hit) {
      const row = $(`tr[data-id="${CSS.escape(id)}"]`);
      if (row) { row.classList.add('remote-hit'); setTimeout(() => row.classList.remove('remote-hit'), 2600); }
    }
  }
  document.addEventListener('focusout', () => setTimeout(() => { if (pendingRemote) renderRemote(); }, 60));
  document.addEventListener('close', () => setTimeout(() => { if (pendingRemote) renderRemote(); }, 0), true);
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
    renderOfferBar();
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
    const vAll = vChanges(), sc = sChanges();
    const vh = vAll.filter((c) => c.offer === OSTD), vc = vAll.filter((c) => c.offer !== OSTD);
    const n = diff.added.length + diff.removed.length + diff.priceChanged.length + diff.changed.length + vAll.length + sc.length + (metaChanged() ? 1 : 0);
    if (!n) { el.innerHTML = ''; return; }
    const parts = [];
    if (metaChanged()) parts.push(`<span class="chg-pill k-edit"><i></i>Kopfdaten geändert</span>`);
    if (diff.priceChanged.length) parts.push(`<span class="chg-pill k-price"><i></i><b>${diff.priceChanged.length}</b> Preis${diff.priceChanged.length === 1 ? '' : 'e'} geändert</span>`);
    if (diff.added.length) parts.push(`<span class="chg-pill k-new"><i></i><b>${diff.added.length}</b> neu</span>`);
    if (diff.changed.length) parts.push(`<span class="chg-pill k-edit"><i></i><b>${diff.changed.length}</b> bearbeitet</span>`);
    if (diff.removed.length) parts.push(`<span class="chg-pill k-del"><i></i><b>${diff.removed.length}</b> entfernt</span>`);
    if (vc.length) {
      const per = new Map(); vc.forEach((c) => per.set(c.offer, (per.get(c.offer) || 0) + 1));
      parts.push(`<span class="chg-pill k-price" title="${esc([...per].map(([o, k]) => `${offerShort(o)}: ${k}`).join(' · '))}"><i></i><b>${vc.length}</b> Angebotspreis${vc.length === 1 ? '' : 'e'} geändert</span>`);
    }
    if (vh.length) parts.push(`<span class="chg-pill k-edit"><i></i><b>${vh.length}</b> im Wochenangebot aus-/eingeblendet</span>`);
    if (sc.length) parts.push(`<span class="chg-pill k-price"><i></i><b>${sc.length}</b> Sonderpreis${sc.length === 1 ? '' : 'e'} geändert</span>`);
    el.innerHTML = `<div class="chg has"><strong>Unveröffentlichte Änderungen:</strong>${parts.join('')}</div>`;
  }
  const pendingCount = () => (!model ? 0 : !published ? model.items.length : diff.added.length + diff.removed.length + diff.priceChanged.length + diff.changed.length + vChanges().length + sChanges().length + (metaChanged() ? 1 : 0));
  function updatePublishBtn() {
    const b = $('#btn-publish');
    const n = pendingCount();
    b.innerHTML = `${icon('send')}<span class="lbl">Veröffentlichen</span>${n ? `<span class="badge-n">${published ? n : '!'}</span>` : ''}`;
  }

  const CAT_OPTS = (sel) => C.CATEGORY_ORDER.map((c) => `<option${c === sel ? ' selected' : ''}>${esc(c)}</option>`).join('');
  const COND_OPTS = (sel) => C.CONDITIONS.map((c) => `<option value="${c}"${c === sel ? ' selected' : ''}>${esc(C.CONDITION_LABELS[c])}</option>`).join('');

  function rowState(it) {
    if (diff.added.includes(it.id)) return 'is-new';
    if (sChanges().some((c) => c.id === it.id)) return 'is-price';
    if (curOffer !== OSTD) {
      if (vChanges().some((c) => c.id === it.id && c.offer === curOffer)) return 'is-price';
      const d = offerDef(curOffer);
      if (diff.priceChanged.includes(it.id) && !(it.variants && it.variants[curOffer]) && !(d && d.fallback === 'hidden')) return 'is-price';
      return diff.changed.includes(it.id) ? 'is-edit' : '';
    }
    if (diff.priceChanged.includes(it.id)) return 'is-price';
    if (diff.changed.includes(it.id) || vChanges().some((c) => c.id === it.id && c.offer === OSTD)) return 'is-edit';
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
      ${curOffer === OSTD ? stdCellHTML(it, bad, label, was, alts) : variantCellHTML(it, st)}
      ${stockCellHTML(it)}
      <td class="e-act"><button type="button" class="ibtn" data-act="item" aria-label="Details zu ${esc(it.name)}" title="Details, Zusatzpreise, verschieben, löschen">${icon('dots')}</button></td>
    </tr>`;
  }
  function eyeHTML(hid) {
    return `<button type="button" class="vtog${hid ? ' on' : ''}" data-act="v-hide" title="${hid ? 'Wieder im Angebot zeigen' : 'In diesem Angebot ausblenden'}" aria-label="${hid ? 'Wieder zeigen' : 'Ausblenden'}" aria-pressed="${hid ? 'true' : 'false'}">${icon('eye', 'sm')}</button>`;
  }
  function saleBtnHTML(it) {
    const a = stockOf(it.code), hot = !it.sale && a && mhdClass(a.mhd);
    return `<button type="button" class="vtog sale${it.sale ? ' on' : hot ? ' hot' : ''}" data-act="sale" title="${it.sale ? 'Sonderpreis bearbeiten' : hot ? `Kurzes MHD (${esc(mhdShort(a.mhd))}) – Sonderpreis festlegen` : 'Sonderpreis festlegen (solange der Vorrat reicht)'}" aria-label="Sonderpreis">${icon('tag', 'sm')}</button>`;
  }
  function saleTagHTML(it) {
    if (!it.sale) return '';
    const v = C.saleFor(it, curOffer);
    if (v == null) return '<span class="sale-tag off">kein Sonderpreis in diesem Angebot</span>';
    const out = soldOut(it);
    return `<button type="button" class="sale-tag${out ? ' out' : ''}" data-act="sale" title="${out ? 'Kein Bestand mehr – wird in allen Angeboten automatisch ausgeblendet' : 'Sonderpreis – solange der Vorrat reicht'}">${out ? 'ohne Bestand · ausgeblendet' : 'Sonderpreis ' + esc(fmtNum.format(v))}</button>`;
  }
  function stdCellHTML(it, bad, label, was, alts) {
    const hid = isHid(it, OSTD);
    return `<td class="e-price e-var std${hid ? ' is-hidden' : ''}">${label}<div class="vrow"><input class="in num${bad ? ' invalid' : ''}" data-f="price" value="${esc(bad ? invalid.get(it.id) : priceToInput(it.price))}" placeholder="${hid ? 'ausgeblendet' : 'ohne Preis'}" aria-label="Preis in Euro je kg" inputmode="decimal"${hid ? ' disabled' : ''}>${saleBtnHTML(it)}${eyeHTML(hid)}</div>${saleTagHTML(it)}${was}${alts}</td>`;
  }
  function variantCellHTML(it, st) {
    const v = it.variants && it.variants[curOffer];
    const d = offerDef(curOffer);
    const key = it.id + '|' + curOffer;
    const bad = invalid.has(key);
    const hiddenOwn = v && v.status === 'hidden';
    const hidden = hiddenOwn || (!v && d && d.fallback === 'hidden');
    const val = bad ? invalid.get(key) : v && !hiddenOwn ? priceToInput(effPrice(it, curOffer)) : '';
    const ph = hiddenOwn ? 'ausgeblendet' : !v ? (d && d.fallback === 'hidden' ? 'ausgeblendet' : 'Std. ' + (priceToInput(it.price) || 'ohne Preis')) : 'ohne Preis';
    const ch = st === 'is-price' && vChanges().find((c) => c.id === it.id && c.offer === curOffer);
    const was = ch ? `<span class="was" title="Veröffentlichter Preis in diesem Angebot">bisher <s>${esc(variantShort(ch.from, curOffer))}</s></span>` : '';
    return `<td class="e-price e-var${hidden ? ' is-hidden' : ''}${v && !hiddenOwn ? ' own' : ''}"><div class="vrow"><input class="in num${bad ? ' invalid' : ''}" data-f="vprice" value="${esc(val)}" placeholder="${esc(ph)}" aria-label="Preis ${esc(offerShort(curOffer))} in Euro je kg" inputmode="decimal"${hiddenOwn ? ' disabled' : ''}>`
      + `${saleBtnHTML(it)}${eyeHTML(hiddenOwn)}</div>${saleTagHTML(it)}${was}</td>`;
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
    else if (f === 'vprice') {
      const key = it.id + '|' + curOffer, t = v.trim();
      if (!t) {
        invalid.delete(key);
        if (it.variants) delete it.variants[curOffer];
      } else {
        const p = inputToPrice(t);
        if (!p || p.status === 'none') { invalid.set(key, v); el.classList.add('invalid'); toast('Preis nicht lesbar – bitte z. B. 23,30 oder „a. Anfr.“ eingeben; leer = ' + (offerDef(curOffer) && offerDef(curOffer).fallback === 'hidden' ? 'ausgeblendet.' : 'Standardpreis.')); return 'invalid'; }
        invalid.delete(key);
        it.variants = it.variants || {};
        it.variants[curOffer] = p.status === 'value' ? { status: 'value', value: p.value } : { status: 'request' };
      }
      if (it.variants && !Object.keys(it.variants).length) delete it.variants;
    }
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
    if (act === 'sale' && tr) { openSale(tr.dataset.id); return; }
    if (act === 'v-hide' && tr) {
      const it = iById(tr.dataset.id);
      if (!it) return;
      pushUndo();
      const v = it.variants && it.variants[curOffer];
      if (v && v.status === 'hidden') { delete it.variants[curOffer]; if (!Object.keys(it.variants).length) delete it.variants; }
      else { it.variants = it.variants || {}; it.variants[curOffer] = { status: 'hidden' }; invalid.delete(it.id + '|' + curOffer); }
      changed({ row: it.id });
      renderOfferBar();
      return;
    }
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

  /* ======================= Angebote (Standard + Kundenangebote) ======================= */
  async function loadOffers() {
    const r = await api('offers');
    offers = r.offers || [];
    offersRev = r.rev || 0;
    stdPublic = r.stdPublic !== false;
    if (!knownOffer(curOffer)) curOffer = OSTD;
  }
  function renderOfferBar() {
    const host = $('#offer-bar');
    if (!host || !model) return;
    host.hidden = false;
    const ids = [OSTD, ...offers.map((o) => o.id)];
    const d = offerDef(curOffer);
    const hint = curOffer === OSTD
      ? `Grundpreise des Wochenangebots (öffentliche Angebotsseite). ${icon('eye', 'sm')} blendet einen Artikel nur hier aus, ${icon('tag', 'sm')} setzt einen Sonderpreis (solange der Vorrat reicht). Kundenangebote oben auswählen.`
      : `Eigene Preise für <strong>${esc(offerName(curOffer))}</strong>. Feld leer = ${d && d.fallback === 'hidden' ? 'Artikel wird in diesem Angebot <strong>nicht angezeigt</strong>' : '<strong>Standardpreis</strong> gilt'}; ${icon('eye', 'sm')} blendet einen Artikel nur hier aus, ${icon('tag', 'sm')} setzt einen Sonderpreis. Artikel, Bezeichnungen und Gruppen gelten für alle Angebote.`;
    host.innerHTML = `<div class="ob-row"><span class="ob-l">Preise für</span>
      <div class="ob-tabs" role="tablist" aria-label="Angebot wählen">${ids.map((id) => { const n = id === OSTD ? 0 : ownCount(id); return `<button role="tab" type="button" data-offer="${esc(id)}" aria-selected="${id === curOffer}"${id === OSTD ? ' class="std"' : ''}>${esc(offerShort(id))}${id !== OSTD ? `<small title="eigene Preise">${n}</small>` : ''}</button>`; }).join('')}</div>
      <span class="ob-act">${!ro && can('admin') ? `<button type="button" class="btn sm ghost" data-ob="restposten" title="Sonderposten dieses Angebots per E-Mail an dessen Kunden senden">${icon('mail', 'sm')}Sonderposten senden</button>` : ''}${!ro && curOffer !== OSTD ? `<button type="button" class="btn sm ghost" data-ob="copy">${icon('copy', 'sm')}Preise übernehmen</button>` : ''}${!ro ? `<button type="button" class="btn sm ghost" data-ob="manage">${icon('list', 'sm')}Angebote verwalten</button>` : ''}</span></div>
      <p class="ob-hint">${hint}</p>`;
    const site = $('#btn-site');
    if (site) site.href = '../' + (curOffer !== OSTD ? '?angebot=' + encodeURIComponent(curOffer) : '');
  }
  function setOffer(id) {
    if (!knownOffer(id) || id === curOffer) return;
    if (document.activeElement && document.activeElement.matches('.in')) document.activeElement.dispatchEvent(new Event('change', { bubbles: true }));
    curOffer = id;
    store.set('angebot', id);
    renderOfferBar();
    renderGroups();
    renderNoPrice();
  }
  $('#offer-bar').addEventListener('click', (e) => {
    const t = e.target.closest('[data-offer]');
    if (t) { setOffer(t.dataset.offer); return; }
    const b = e.target.closest('[data-ob]');
    if (!b) return;
    if (b.dataset.ob === 'manage') openOffers();
    if (b.dataset.ob === 'copy') openCopy();
    if (b.dataset.ob === 'restposten') openRestposten(curOffer);
  });
  $('#offer-bar').addEventListener('keydown', (e) => {
    if (!e.target.matches('[data-offer]') || !['ArrowLeft', 'ArrowRight'].includes(e.key)) return;
    const tabs = $$('#offer-bar [data-offer]'), i = tabs.indexOf(e.target);
    const n = tabs[(i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length];
    setOffer(n.dataset.offer); $(`#offer-bar [data-offer="${CSS.escape(n.dataset.offer)}"]`).focus();
  });

  /* Angebote verwalten: anlegen, umbenennen, Regel für Artikel ohne eigenen Preis, löschen (Administrator) */
  const dlgOffers = $('#dlg-offers');
  let offerEdit = [];
  const slug = (t) => fold(t).replace(/^wochenangebot\s*/, '').replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 32) || 'angebot';
  function openOffers() {
    offerEdit = offers.map((o) => ({ ...o }));
    offerEdit.stdPublic = stdPublic;
    renderOffersDlg();
    dlgOffers.showModal();
  }
  function renderOffersDlg(err = '') {
    const admin = can('admin');
    $('#offers-body').innerHTML = `<div class="dlg-head"><div><h2 id="of-title">Angebote verwalten</h2><p>Alle Angebote nutzen dieselbe Artikelliste; Preise werden je Angebot eingetragen. Kundenangebote sind nur nach Anmeldung sichtbar (Mitarbeiter oder freigeschaltete Kunden), nie auf der öffentlichen Seite.</p></div><button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        <table class="etab oftab"><thead><tr><th>Name</th><th>Artikel ohne eigenen Preis</th><th class="num-s">Eigene Preise</th><th class="act"></th></tr></thead><tbody>
          <tr class="of-std"><td><strong>Wochenangebot</strong><div class="sub">Standard · ${offerEdit.stdPublic ? 'öffentlich ohne Anmeldung' : 'nur für angemeldete Kunden'}</div></td><td colspan="3">${admin ? `<label class="check"><input type="checkbox" data-ofa-pub${offerEdit.stdPublic ? ' checked' : ''}> Öffentlich ohne Anmeldung sichtbar</label><div class="sub">Ausgeschaltet sehen das Wochenangebot nur Kunden, denen es unter „Kunden“ freigeschaltet ist.</div>` : `<span class="sub">${offerEdit.stdPublic ? 'öffentlich' : 'nur mit Kunden-Anmeldung'} (ändern: Administrator)</span>`}</td></tr>
          ${offerEdit.map((o, i) => `<tr data-oi="${i}"><td><input class="in" data-of="name" value="${esc(o.name)}" maxlength="80" aria-label="Name des Angebots"></td>
            <td><select class="in" data-of="fallback" aria-label="Artikel ohne eigenen Preis"><option value="standard"${o.fallback !== 'hidden' ? ' selected' : ''}>Standardpreis zeigen</option><option value="hidden"${o.fallback === 'hidden' ? ' selected' : ''}>nicht anzeigen</option></select></td>
            <td class="num-s">${o.isNew ? '<span class="sub">neu</span>' : fmtInt.format(ownCount(o.id))}</td>
            <td class="act">${admin || o.isNew ? `<button type="button" class="ibtn danger" data-ofa="del" aria-label="Angebot ${esc(o.name)} löschen" title="${o.isNew ? 'Entfernen' : 'Löschen'}">${icon('trash')}</button>` : ''}</td></tr>`).join('')}
        </tbody></table>
        <button type="button" class="btn sm" data-ofa="add">${icon('plus', 'sm')}Angebot hinzufügen</button>
        <p class="form-err" id="of-err" role="alert">${esc(err)}</p>
      </div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="button" class="btn primary" data-ofa="save">${icon('check')}Speichern</button></div>`;
  }
  $('#offers-body').addEventListener('input', (e) => {
    const tr = e.target.closest('[data-oi]');
    if (tr && e.target.dataset.of) offerEdit[+tr.dataset.oi][e.target.dataset.of] = e.target.value;
  });
  $('#offers-body').addEventListener('change', (e) => {
    if (e.target.matches('[data-ofa-pub]')) { offerEdit.stdPublic = e.target.checked; renderOffersDlg(); return; }
    const tr = e.target.closest('[data-oi]');
    if (tr && e.target.dataset.of) offerEdit[+tr.dataset.oi][e.target.dataset.of] = e.target.value;
  });
  $('#offers-body').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-ofa]');
    if (!b) return;
    const a = b.dataset.ofa;
    if (a === 'add') {
      offerEdit.push({ id: '', name: 'Wochenangebot ', fallback: 'standard', isNew: true });
      renderOffersDlg();
      const inp = $$('#offers-body [data-of="name"]').pop(); inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length);
      return;
    }
    if (a === 'del') {
      const i = +b.closest('[data-oi]').dataset.oi, o = offerEdit[i];
      if (!o.isNew) {
        const n = ownCount(o.id);
        if (!(await confirmBox('Angebot löschen?', `„${esc(o.name)}“ wird beim Speichern gelöscht${n ? ` – mit ${n} eigenen Preis${n === 1 ? '' : 'en'}` : ''}. Das lässt sich nicht rückgängig machen.`, 'Löschen', true))) return;
      }
      offerEdit.splice(i, 1);
      renderOffersDlg();
      return;
    }
    if (a === 'save') {
      const used = new Set(offers.map((o) => o.id));
      const list = offerEdit.map((o) => {
        let id = o.id;
        if (!id) { const base = slug(o.name); id = base; let k = 2; while (used.has(id) || id === OSTD) id = `${base}-${k++}`; used.add(id); }
        return { id, name: C.clean(o.name), fallback: o.fallback === 'hidden' ? 'hidden' : 'standard' };
      });
      b.disabled = true;
      try {
        const body = { rev: offersRev, offers: list };
        if (can('admin')) body.stdPublic = !!offerEdit.stdPublic;
        const r = await api('offers_save', { body });
        offers = r.offers; offersRev = r.rev; stdPublic = r.stdPublic !== false;
        const gone = new Set([OSTD, ...list.map((o) => o.id)]);
        let dropped = false;
        for (const it of model.items) {
          if (it.variants) for (const k of Object.keys(it.variants)) if (!gone.has(k)) { delete it.variants[k]; dropped = true; }
          if (it.sale && it.sale.offers) { for (const k of Object.keys(it.sale.offers)) if (!gone.has(k)) { delete it.sale.offers[k]; dropped = true; } if (!Object.keys(it.sale.offers).length) delete it.sale.offers; }
        }
        if (!knownOffer(curOffer)) curOffer = OSTD;
        dlgOffers.close();
        toast('Angebote gespeichert.');
        diff = C.diffOffers(published, model);
        renderOfferBar(); renderGroups(); renderChanges(); updatePublishBtn();
        if (dropped) changed({ render: true });
      } catch (ex) { b.disabled = false; renderOffersDlg(ex.message); }
    }
  });

  /* Preise übernehmen: aus dem Standard oder einem anderen Angebot, optional mit Auf-/Abschlag */
  const dlgCopy = $('#dlg-offer-copy');
  function openCopy() {
    const ids = [OSTD, ...offers.map((o) => o.id)].filter((id) => id !== curOffer);
    $('#offer-copy-body').innerHTML = `<div class="dlg-head"><div><h2 id="oc-title">Preise übernehmen</h2><p>Ziel: <strong>${esc(offerName(curOffer))}</strong>. Übernommene Preise sind danach eigene Preise dieses Angebots und lassen sich einzeln ändern.</p></div><button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body form-grid two">
        <label class="fld"><span>Aus Angebot</span><select name="src">${ids.map((id) => `<option value="${esc(id)}">${esc(offerName(id))}</option>`).join('')}</select></label>
        <label class="fld"><span>Auf-/Abschlag in %</span><input name="pct" type="number" step="0.5" value="0" inputmode="decimal"></label>
        <label class="fld"><span>Runden auf</span><select name="round"><option value="0.01">0,01 €</option><option value="0.05" selected>0,05 €</option><option value="0.1">0,10 €</option></select></label>
        <label class="fld"><span>Welche Artikel</span><select name="mode"><option value="empty">nur Artikel ohne eigenen Preis</option><option value="all">alle (eigene Preise überschreiben)</option></select></label>
        <p class="hint span2">„Auf Anfrage“ wird übernommen, Artikel ohne Preis werden übersprungen. Mit „Rückgängig“ lässt sich die Übernahme zurücknehmen.</p>
      </div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="submit" class="btn primary">${icon('copy')}Übernehmen</button></div>`;
    dlgCopy.showModal();
  }
  $('#offer-copy-body').addEventListener('submit', (e) => {
    e.preventDefault();
    const f = e.target.elements, src = f.src.value, pct = Number(String(f.pct.value).replace(',', '.')) || 0, step = Number(f.round.value), all = f.mode.value === 'all';
    if (Math.abs(pct) > 50) { toast('Auf-/Abschlag bitte zwischen −50 und +50 %.'); return; }
    pushUndo();
    let n = 0;
    for (const it of model.items) {
      const has = it.variants && it.variants[curOffer];
      if (has && !all) continue;
      const p = src === OSTD ? it.price : (it.variants && it.variants[src]) || null;
      if (!p || (p.status !== 'value' && p.status !== 'request')) continue;
      it.variants = it.variants || {};
      it.variants[curOffer] = p.status === 'value' ? { status: 'value', value: Math.round(Math.round(p.value * (1 + pct / 100) / step) * step * 100) / 100 } : { status: 'request' };
      invalid.delete(it.id + '|' + curOffer);
      n++;
    }
    dlgCopy.close();
    changed({ render: true });
    toast(n ? `${plural(n, 'Preis', 'Preise')} aus „${offerShort(src)}“ übernommen${pct ? ` (${pct > 0 ? '+' : ''}${fmtNum.format(pct)} %)` : ''}.` : 'Keine Preise übernommen.');
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
      const vc = vChanges();
      if (vc.length) body += sec(`Angebotspreise (${vc.length})`, `<ul class="plist">${vc.slice(0, 80).map((c) => { const it = byId.get(c.id); return it ? `<li><span><b class="ob-tag">${esc(offerShort(c.offer))}</b> ${esc(it.code || '—')} · ${esc(it.name)}</span><span>${esc(variantShort(c.from, c.offer))} → <strong>${esc(variantShort(c.to, c.offer))}</strong></span>${rv('variant', c.id + '|' + c.offer)}</li>` : ''; }).join('')}${vc.length > 80 ? `<li><span>… und ${vc.length - 80} weitere</span><span></span></li>` : ''}</ul>`);
      const sc = sChanges();
      if (sc.length) body += sec(`Sonderpreise – solange der Vorrat reicht (${sc.length})`, `<ul class="plist">${sc.slice(0, 80).map((c) => { const it = byId.get(c.id); return it ? `<li><span>${esc(it.code || '—')} · ${esc(it.name)}</span><span>${esc(saleText(c.from))} → <strong>${esc(saleText(c.to))}</strong></span>${rv('sale', c.id)}</li>` : ''; }).join('')}</ul>`);
      if (!metaChanged() && !diff.priceChanged.length && !diff.added.length && !diff.changed.length && !diff.removed.length && !vc.length && !sc.length) body += '<p class="notice">Keine Änderungen gegenüber der veröffentlichten Fassung.</p>';
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
    if (kind === 'sale') {
      const it = model.items.find((x) => x.id === id), c = sChanges().find((x) => x.id === id);
      if (!it || !c) return;
      if (c.from) it.sale = clone(c.from); else delete it.sale;
      return;
    }
    if (kind === 'variant') {
      const [iid, oid] = id.split('|');
      const it = model.items.find((x) => x.id === iid), c = vChanges().find((x) => x.id === iid && x.offer === oid);
      if (!it || !c) return;
      if (c.from) { it.variants = it.variants || {}; it.variants[oid] = clone(c.from); } else if (it.variants) { delete it.variants[oid]; if (!Object.keys(it.variants).length) delete it.variants; }
      invalid.delete(iid + '|' + oid);
      return;
    }
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
    if (kind === 'sale') {
      const it = model.items.find((x) => x.id === id), c = sChanges().find((x) => x.id === id);
      return ['Sonderpreis zurücknehmen?', `Der Sonderpreis von „${esc(it ? (it.code ? it.code + ' · ' : '') + it.name : id)}“ wird von <strong>${esc(saleText(c && c.to))}</strong> wieder auf <strong>${esc(saleText(c && c.from))}</strong> gesetzt.`];
    }
    if (kind === 'variant') {
      const [iid, oid] = id.split('|');
      const it = model.items.find((x) => x.id === iid), c = vChanges().find((x) => x.id === iid && x.offer === oid);
      return ['Angebotspreis zurücknehmen?', `Der Preis von „${esc(it ? (it.code ? it.code + ' · ' : '') + it.name : iid)}“ im Angebot <strong>${esc(offerName(oid))}</strong> wird von <strong>${esc(variantShort(c && c.to, oid))}</strong> wieder auf <strong>${esc(variantShort(c && c.from, oid))}</strong> gesetzt.`];
    }
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
      while (saving || pulling) await new Promise((res) => setTimeout(res, 100));
      queued = false;
      const r = await api('publish', { body: { model, revision } });
      published = clone(model);
      base = clone(model);
      hist = null;
      revision = r.revision ?? 0;
      savedAt = null;
      dlgPublish.close();
      diff = C.diffOffers(published, model);
      renderAll();
      setSaveState('clean');
      toast(`Veröffentlicht: KW ${model.meta.week}/${model.meta.year} ist jetzt online (${dateTime(r.publishedAt)} Uhr).`, 6000);
    } catch (ex) {
      let msg = ex.message;
      if (ex.status === 409) {
        // andere haben inzwischen gespeichert: übernehmen und die Zusammenfassung neu zeigen
        try { await pullRemote(); openPublish(); msg += ' Die Änderungen sind jetzt übernommen – bitte prüfen und erneut veröffentlichen.'; } catch { /* Meldung bleibt */ }
      }
      const pb = $('[data-ia="publish"]');
      if (pb) { pb.disabled = false; pb.innerHTML = `${icon('send')}${ex.status === 409 ? 'Jetzt veröffentlichen' : 'Erneut versuchen'}`; }
      $('#publish-body .dlg-body').insertAdjacentHTML('afterbegin', `<p class="err-box" style="margin:0 0 12px">${esc(msg)}</p>`);
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
    if (a === 'open-site') window.open('../' + (curOffer !== OSTD ? '?angebot=' + encodeURIComponent(curOffer) : ''), '_blank', 'noopener');
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
        while (saving || pulling) await new Promise((res) => setTimeout(res, 100));
        queued = false;
        let r;
        try { r = await api('discard_draft', { body: { revision } }); } catch (ex) {
          if (ex.status !== 409) throw ex;
          await pullRemote().catch(() => {});
          toast(ex.message + ' Die Änderungen sind übernommen – bitte prüfen und bei Bedarf erneut verwerfen.', 8000);
          return;
        }
        pushUndo();
        model = published ? clone(published) : emptyModel();
        base = clone(model);
        revision = r.revision ?? 0; savedAt = null; invalid.clear(); autoAttr.clear();
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
    const u = '../?vorschau=1' + (curOffer !== OSTD ? '&angebot=' + encodeURIComponent(curOffer) : '');
    if (w) w.location = u; else location.href = u;
  });
  $('#save-state').addEventListener('click', (e) => { if (e.target.closest('[data-act="retry-save"]')) saveNow(); });
  for (const d of $$('dialog')) d.addEventListener('click', (e) => { if (e.target === d || e.target.closest('[data-close]')) { if (d.id !== 'dlg-confirm' && !d.dataset.busy) d.close(); } });

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
  const VIEWS = ['orders', 'edit', 'hist', 'stock', 'master', 'kunden', 'mail', 'users', 'log', 'sec'];
  const ADMIN_VIEWS = ['kunden', 'mail', 'users', 'log', 'sec'];
  function setView(v) {
    if (v === 'orders' && !can('editor')) v = 'edit';
    if (ADMIN_VIEWS.includes(v) && !can('admin')) v = 'edit';
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
    if (v === 'orders') renderOrdersView();
    if (v === 'kunden') renderKundenView();
    if (v === 'mail') renderMailView();
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
      + `<th class="e-price">Preis €/kg<small>KW ${esc(model && model.meta.week || '')}${curOffer !== OSTD ? ' · ' + esc(offerShort(curOffer)) : ''}</small></th>`
      + `<th class="e-stock" title="Verfügbarer Bestand (eingelagert)${stock && stock.date ? ' · Stand ' + esc(dmy(stock.date)) : ''}">Bestand kg<small>${stock && stock.date ? 'Stand ' + esc(mhdShort(stock.date)) : ''}</small></th>`;
  }
  function prevCellHTML(it) {
    const h = prevOf(it);
    const pp = h ? effPrice(h, curOffer) : null;   // Vorwochenpreis in diesem Angebot (Preisverlauf enthält die Angebotspreise)
    const p = pp ? { price: pp } : null;
    const t = !p ? '—' : p.price.status === 'value' ? fmtNum.format(p.price.value) : p.price.status === 'request' ? 'a. Anfr.' : '—';
    const cur = effPrice(it, curOffer) || { status: 'none' }, pv = p && p.price.status === 'value' ? p.price.value : null;
    const d = pv != null && cur.status === 'value' ? Math.round((cur.value - pv) * 1000) / 1000 : null;
    const delta = d ? `<span class="pdelta ${d > 0 ? 'up' : 'down'}">${d > 0 ? '+' : '−'}${fmtNum.format(Math.abs(d))}</span>` : '';
    return `<td class="e-prev${p ? '' : ' none'}" title="${p ? esc(`Preis ${prevLabel()}: ${priceShort(p.price)}`) : 'In der Vorwoche nicht im Angebot'}">${esc(t)}${delta}</td>`;
  }
  function stockCellHTML(it) {
    const a = stockOf(it.code);
    if (!a) return it.code
      ? `<td class="e-stock none"><span class="nostock" title="Kein verfügbarer Bestand${stock && stock.date ? ' (Bestand vom ' + esc(dmy(stock.date)) + ')' : ''}" aria-label="Kein verfügbarer Bestand">0</span></td>`
      : '<td class="e-stock none" title="Ohne Artikelnummer kein Bestandsabgleich">—</td>';
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
      const sb = tr.querySelector('.vtog.sale');
      if (sb) { const t2 = document.createElement('div'); t2.innerHTML = saleBtnHTML(it) + saleTagHTML(it); sb.replaceWith(t2.firstElementChild); const tag = tr.querySelector('.sale-tag'); if (tag && t2.firstElementChild) tag.replaceWith(t2.firstElementChild); }
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
    renderMhd();
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

  /* ======================= Sonderposten (kurzes MHD, solange der Vorrat reicht) ======================= */
  /* Sonderpreis je Artikel: Grundpreis für alle Angebote, je Angebot änderbar (eigener Sonderpreis / keiner) */
  const dlgSale = $('#dlg-sale');
  let saleId = null;
  function openSale(id) {
    const it = iById(id);
    if (!it) return;
    saleId = id;
    const sl = it.sale || null, a = stockOf(it.code), cls = a ? mhdClass(a.mhd) : '';
    const ids = [OSTD, ...offers.map((o) => o.id)];
    const rows = ids.map((oid) => {
      const o = sl && sl.offers && sl.offers[oid];
      const mode = !o ? 'base' : o.status === 'none' ? 'none' : 'own';
      const hid = isHid(it, oid), norm = effPrice(it, oid);
      const normTxt = hid ? `<span class="muted" title="Mit dem Auge in diesem Angebot ausgeblendet – auch der Sonderpreis erscheint dort nicht">${icon('eye', 'sm')} ausgeblendet</span>` : norm ? esc(priceShort(norm)) : '<span class="muted" title="Dieses Angebot zeigt nur Artikel mit eigenem Preis – mit Sonderpreis erscheint der Artikel trotzdem">nicht im Sortiment</span>';
      return `<tr data-soid="${esc(oid)}"><td>${esc(offerShort(oid))}</td><td class="sp-norm">${normTxt}</td>
        <td><select class="in" data-sm aria-label="Sonderpreis ${esc(offerShort(oid))}"><option value="base"${mode === 'base' ? ' selected' : ''}>wie oben</option><option value="own"${mode === 'own' ? ' selected' : ''}>eigener Sonderpreis</option><option value="none"${mode === 'none' ? ' selected' : ''}>kein Sonderpreis</option></select></td>
        <td class="sp-own"><input class="in num" data-sv inputmode="decimal" value="${mode === 'own' ? esc(fmtNum.format(o.value)) : ''}" placeholder="€/kg" aria-label="Eigener Sonderpreis ${esc(offerShort(oid))}"${mode === 'own' ? '' : ' hidden'}></td></tr>`;
    }).join('');
    const stockLine = !it.code ? `<p class="notice k-pend">${icon('info', 'sm')}<span>Ohne Artikelnummer ist kein Bestandsabgleich möglich – der Sonderposten wird dann nicht automatisch ausgeblendet.</span></p>`
      : !stock ? '' : !a ? `<p class="notice k-pend">${icon('info', 'sm')}<span>Laut Bestand vom ${esc(dmy(stock.date || ''))} ist <strong>kein Bestand</strong> vorhanden – der Sonderposten wird in allen Angeboten automatisch ausgeblendet.</span></p>` : '';
    $('#sale-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="sp-title">Sonderpreis – solange der Vorrat reicht</h2><p>${esc(it.code || '—')} · ${esc(it.name)}${a ? ` · ${esc(kgText(a.kg))} verfügbar · kürz. MHD <span class="${cls}">${esc(mhdShort(a.mhd))}</span>` : ''}</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        ${stockLine}
        <label class="fld sp-base"><span>Sonderpreis €/kg <small class="muted">(gilt für alle Angebote)</small></span><input name="value" inputmode="decimal" value="${sl ? esc(fmtNum.format(sl.value)) : ''}" placeholder="z. B. 9,90" required></label>
        <table class="etab sptab"><thead><tr><th>Angebot</th><th class="sp-norm">Normalpreis</th><th>Sonderpreis</th><th></th></tr></thead><tbody>${rows}</tbody></table>
        <p class="hint">Kunden sehen „Sonderposten – solange der Vorrat reicht“ und den bisherigen Preis durchgestrichen. Ist laut Bestandsliste kein Bestand mehr da, wird der Artikel in allen Angeboten automatisch ausgeblendet. Wirksam nach dem Veröffentlichen.</p>
        <p class="form-err" id="sp-err" role="alert"></p>
      </div>
      <div class="dlg-foot">${sl ? `<span class="left"><button type="button" class="btn ghost danger" data-sp="remove">${icon('trash', 'sm')}Sonderpreis entfernen</button></span>` : ''}<button type="button" class="btn" data-close>Abbrechen</button><button type="submit" class="btn primary">${icon('check')}Übernehmen</button></div>`;
    dlgSale.showModal();
    $('#sale-body [name="value"]').focus();
  }
  $('#sale-body').addEventListener('change', (e) => {
    if (!e.target.matches('[data-sm]')) return;
    const inp = e.target.closest('tr').querySelector('[data-sv]');
    inp.hidden = e.target.value !== 'own';
    if (!inp.hidden) inp.focus();
  });
  $('#sale-body').addEventListener('click', (e) => {
    if (e.target.closest('[data-close]')) { dlgSale.close(); return; }
    if (!e.target.closest('[data-sp="remove"]') || ro) return;
    const it = iById(saleId);
    if (!it) return;
    pushUndo();
    delete it.sale;
    dlgSale.close();
    changed({ row: it.id });
    toast('Sonderpreis entfernt (wirksam nach dem Veröffentlichen).');
  });
  $('#sale-body').addEventListener('submit', (e) => {
    e.preventDefault();
    const it = iById(saleId);
    if (!it || ro) return;
    const err = (m) => { $('#sp-err').textContent = m; };
    const base = C.parsePrice(e.target.elements.value.value);
    if (base.status !== 'value' || base.invalid) { err('Bitte einen Sonderpreis in €/kg angeben, z. B. 9,90.'); return; }
    const offersOut = {};
    for (const tr of $$('#sale-body tr[data-soid]')) {
      const oid = tr.dataset.soid, mode = tr.querySelector('[data-sm]').value;
      if (mode === 'none') offersOut[oid] = { status: 'none' };
      if (mode === 'own') {
        const p = C.parsePrice(tr.querySelector('[data-sv]').value);
        if (p.status !== 'value' || p.invalid) { err(`Eigener Sonderpreis für „${offerShort(oid)}“ fehlt oder ist nicht lesbar.`); return; }
        offersOut[oid] = { value: p.value };
      }
    }
    pushUndo();
    it.sale = { value: base.value, ...(Object.keys(offersOut).length ? { offers: offersOut } : {}), since: (it.sale && it.sale.since) || isoToday() };
    dlgSale.close();
    changed({ row: it.id });
    toast(`Sonderpreis ${fmtNum.format(base.value)} €/kg für „${it.name}“ gesetzt – wirksam nach dem Veröffentlichen.`, 5000);
  });

  /* Liste: Artikel mit kurzem oder überschrittenem MHD (Farbskala der Bestandsliste) */
  let mhdOpen = store.get('mhdOpen', true);
  function mhdList() {
    if (!stock || !model) return [];
    const byCode = new Map();
    for (const it of model.items) if (it.code) { const k = S.normCode(it.code); if (!byCode.has(k)) byCode.set(k, []); byCode.get(k).push(it); }
    return stock.articles.filter((a) => mhdClass(a.mhd)).map((a) => ({ a, items: byCode.get(S.normCode(a.code)) || [], cls: mhdClass(a.mhd) }))
      .sort((x, y) => x.a.mhd.localeCompare(y.a.mhd) || x.a.code.localeCompare(y.a.code, 'de', { numeric: true }));
  }
  function renderMhd() {
    const host = $('#mhd-panel');
    if (!host) return;
    if (!stock || !model) { host.hidden = true; return; }
    const all = mhdList();
    const toks = fold(filterQ).split(/\s+/).filter(Boolean);
    const list = toks.length ? all.filter((x) => { const h = fold(x.a.code + ' ' + x.a.name + ' ' + x.items.map((i) => i.name).join(' ')); return toks.every((t) => h.includes(t)); }) : all;
    const withSale = all.filter((x) => x.items.some((i) => i.sale)).length;
    host.hidden = false;
    const rows = list.map((x) => {
      const it = x.items[0];
      const cur = it ? effPrice(it, curOffer) : null, sp = it ? C.saleFor(it, curOffer) : null;
      return `<tr data-mcode="${esc(x.a.code)}"${it ? ` data-mid="${esc(it.id)}"` : ''}>
        <td class="np-code">${esc(x.a.code)}</td><td class="np-name">${esc(it ? it.name : x.a.name)}${!it ? ' <span class="muted">(nicht im Angebot)</span>' : ''}</td>
        <td class="np-kg">${esc(kgText(x.a.kg))}</td><td class="np-mhd"><span class="${x.cls}">${esc(mhdShort(x.a.mhd))}</span></td>
        <td class="np-prev">${it ? (cur ? esc(priceShort(cur)) : '<span class="muted">ausgeblendet</span>') : '—'}</td>
        <td class="np-prev">${sp != null ? `<strong class="sp-val">${esc(fmtNum.format(sp))}</strong>` : '—'}</td>
        <td class="np-act">${ro ? '' : it
          ? `<button type="button" class="btn sm${it.sale ? '' : ' primary'}" data-mp="sale">${icon('tag', 'sm')}${it.sale ? 'Sonderpreis ändern' : 'Sonderpreis'}</button>`
          : `<button type="button" class="btn sm" data-mp="add">${icon('plus', 'sm')}Ins Angebot</button>`}</td>
      </tr>`;
    }).join('');
    host.innerHTML = `<div class="np-card mhd-card${mhdOpen ? ' open' : ''}">
      <button type="button" class="np-head" data-mp="toggle" aria-expanded="${mhdOpen}">
        <span class="np-title">Kurzes MHD – Sonderposten <span class="np-badge">${fmtInt.format(all.length)}</span></span>
        <span class="np-sub">MHD überschritten oder in höchstens 14 Tagen (Farbskala) · ${plural(withSale, 'Artikel', 'Artikel')} mit Sonderpreis · Preise für ${esc(offerShort(curOffer))} · ohne Bestand automatisch ausgeblendet</span>
        ${icon('chev', 'np-chev')}
      </button>
      ${mhdOpen ? (list.length ? `<div class="np-body"><table class="etab nptab"><thead><tr><th class="np-code">Art.-Nr.</th><th class="np-name">Bezeichnung</th><th class="np-kg">Kg verfüg.</th><th class="np-mhd">Kürz. MHD</th><th class="np-prev">Preis</th><th class="np-prev">Sonderpreis</th><th class="np-act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${rows}</tbody></table></div>`
        : `<p class="np-empty">${all.length ? 'Kein Treffer zur Suche.' : 'Keine Artikel mit kurzem oder überschrittenem MHD im Bestand.'}</p>`) : ''}
    </div>`;
  }
  $('#mhd-panel').addEventListener('click', (e) => {
    const b = e.target.closest('[data-mp]');
    if (!b) return;
    if (b.dataset.mp === 'toggle') { mhdOpen = !mhdOpen; store.set('mhdOpen', mhdOpen); renderMhd(); return; }
    const tr = b.closest('tr[data-mcode]');
    if (!tr || ro) return;
    if (b.dataset.mp === 'sale' && tr.dataset.mid) openSale(tr.dataset.mid);
    if (b.dataset.mp === 'add') openAddStock(tr.dataset.mcode);
  });

  /* Sonderposten eines Angebots per E-Mail – nur an Kunden, denen genau dieses Angebot freigeschaltet ist */
  const dlgRest = $('#dlg-rest');
  let restInfo = null, restSel = new Set(), restBusy = false;
  async function openRestposten(oid) {
    let info;
    try { info = await api('restposten_info', { query: '&offer=' + encodeURIComponent(oid) }); } catch (ex) { toast(ex.message); return; }
    restInfo = info;
    const ok = info.recipients.filter((c) => !c.reason), no = info.recipients.filter((c) => c.reason);
    restSel = new Set(ok.map((c) => c.id));
    const pend = pendingCount();
    const items = info.items;
    $('#rest-body').innerHTML = `<div class="dlg-head"><div><h2 id="rp-title">Sonderposten „${esc(info.offer.name)}“ versenden</h2><p>Nur Kunden mit dem Angebot <strong>${esc(info.offer.name)}</strong> erhalten diese E-Mail – jeder einzeln, mit den Sonderpreisen dieses Angebots. Andere Angebote und Kunden bleiben unsichtbar.</p></div><button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        ${!info.mailReady ? '<div class="err-box">Der E-Mail-Versand ist noch nicht eingerichtet (Verwaltung → E-Mail).</div>' : ''}
        ${pend ? `<div class="notice k-pend">${icon('info', 'sm')}<span>Es gibt ${plural(pend, 'unveröffentlichte Änderung', 'unveröffentlichte Änderungen')} im Entwurf. Versendet wird der <strong>veröffentlichte</strong> Stand – neue Sonderpreise bitte zuerst veröffentlichen.</span></div>` : ''}
        ${items.length ? `<h3 class="d-h"><span>${plural(items.length, 'Sonderposten', 'Sonderposten')}</span></h3><ul class="plist">${items.map((x) => `<li><span>${esc(x.code || '—')} · ${esc(x.name)}</span><span><strong>${esc(fmtNum.format(x.price))} €/kg</strong>${x.regular != null ? ` <s class="muted">${esc(fmtNum.format(x.regular))}</s>` : ''}</span></li>`).join('')}</ul>`
          : `<div class="err-box">Im veröffentlichten Angebot „${esc(info.offer.name)}“ ist kein Sonderposten mit Bestand enthalten. Sonderpreise festlegen (${icon('tag', 'sm')}) und veröffentlichen.</div>`}
        <h3 class="d-h"><span>Empfänger</span></h3>
        ${ok.length ? `<div class="k-rlist"><label class="check k-rall"><input type="checkbox" id="rp-all"> Alle auswählen</label>
          <table class="etab ktab k-rtab"><tbody>${ok.map((c) => `<tr data-rid="${esc(c.id)}"><td class="k-rchk"><input type="checkbox" data-psel="${esc(c.id)}" checked aria-label="${esc(c.firma)} auswählen"></td>
            <td><div class="nm">${esc(c.firma)}</div><div class="sub">${esc(c.email)}</div></td><td class="k-rst"><span class="k-res"></span></td></tr>`).join('')}</tbody></table></div>`
          : `<p class="hint">Kein Kunde mit E-Mail-Adresse hat das Angebot „${esc(info.offer.name)}“ freigeschaltet.</p>`}
        ${no.length ? `<details class="k-no"><summary>${plural(no.length, 'Kunde', 'Kunden')} dieses Angebots nicht berücksichtigt</summary><ul>${no.map((c) => `<li>${esc(c.firma)} – ${esc(c.reason)}</li>`).join('')}</ul></details>` : ''}
        <label class="fld"><span>Zusatztext <small class="muted">(optional)</small></span><textarea id="rp-note" rows="2" maxlength="1000" placeholder="z. B. Abholung oder Lieferung bis Freitag möglich."></textarea></label>
        <div class="k-prevwrap" hidden><iframe id="rp-prev" sandbox="" title="Vorschau der E-Mail"></iframe></div>
        <p class="form-err" id="rp-err" role="alert"></p>
      </div>
      <div class="dlg-foot"><span class="left"><button type="button" class="btn sm ghost" data-rp="prev"${items.length ? '' : ' disabled'}>${icon('eye', 'sm')}Vorschau</button></span><button type="button" class="btn" data-close>Schließen</button><button type="button" class="btn primary" data-rp="send">${icon('send')}<span id="rp-n"></span></button></div>`;
    restCount();
    dlgRest.showModal();
  }
  function restCount() {
    const n = restSel.size;
    $('#rp-n').textContent = n ? `An ${plural(n, 'Kunden', 'Kunden')} senden` : 'Kunden auswählen';
    $('#rest-body [data-rp="send"]').disabled = !n || restBusy || !restInfo.items.length || !restInfo.mailReady;
    const all = $('#rp-all'), boxes = $$('#rest-body [data-psel]');
    if (all) { all.checked = boxes.length && boxes.every((b) => b.checked); all.indeterminate = !all.checked && boxes.some((b) => b.checked); }
  }
  dlgRest.addEventListener('cancel', (e) => { if (restBusy) e.preventDefault(); });
  dlgRest.addEventListener('change', (e) => {
    if (e.target.id === 'rp-all') for (const b of $$('#rest-body [data-psel]')) { b.checked = e.target.checked; b.checked ? restSel.add(b.dataset.psel) : restSel.delete(b.dataset.psel); }
    if (e.target.dataset.psel) e.target.checked ? restSel.add(e.target.dataset.psel) : restSel.delete(e.target.dataset.psel);
    restCount();
  });
  dlgRest.addEventListener('click', async (e) => {
    if (e.target.closest('[data-close]') && !restBusy) { dlgRest.close(); return; }
    const a = e.target.closest('[data-rp]')?.dataset.rp;
    if (a === 'prev') {
      try {
        const r = await api('kunden_mail_vorschau', { body: { id: [...restSel][0] || '', type: 'restposten', offer: restInfo.offer.id, note: $('#rp-note').value } });
        $('#rest-body .k-prevwrap').hidden = false;
        $('#rp-prev').srcdoc = r.html;
      } catch (ex) { $('#rp-err').textContent = ex.message; }
    }
    if (a === 'send') {
      const ids = [...restSel];
      if (!(await confirmBox('Sonderposten versenden?', `${plural(restInfo.items.length, 'Sonderposten', 'Sonderposten')} aus „${esc(restInfo.offer.name)}“ gehen jetzt per E-Mail an ${plural(ids.length, 'Kunden', 'Kunden')} dieses Angebots.`, 'Jetzt senden'))) return;
      restBusy = true; restCount();
      const note = $('#rp-note').value;
      let okN = 0, badN = 0;
      $('#rp-err').textContent = '';
      for (let i = 0; i < ids.length; i += 10) {
        const part = ids.slice(i, i + 10);
        for (const id of part) $(`#rest-body tr[data-rid="${CSS.escape(id)}"] .k-res`).innerHTML = '<span class="spinner sm"></span>';
        $('#rp-n').textContent = `Wird gesendet … ${i}/${ids.length}`;
        try {
          const r = await api('kunden_restposten', { body: { offer: restInfo.offer.id, ids: part, note, publishedAt: restInfo.publishedAt } });
          for (const x of r.results) {
            const cell = $(`#rest-body tr[data-rid="${CSS.escape(x.id)}"] .k-res`);
            if (x.ok) { okN++; restSel.delete(x.id); const cb = $(`#rest-body [data-psel="${CSS.escape(x.id)}"]`); if (cb) cb.checked = false; } else badN++;
            if (cell) cell.innerHTML = x.ok ? `<span class="st-ok">${icon('check', 'sm')}gesendet</span>` : `<span class="st-err">${esc(x.error)}</span>`;
          }
        } catch (ex) {
          badN += part.length;
          for (const id of part) $(`#rest-body tr[data-rid="${CSS.escape(id)}"] .k-res`).innerHTML = `<span class="st-err">${esc(ex.message)}</span>`;
          if (ex.status === 409 || ex.status === 401 || ex.status === 403) { $('#rp-err').textContent = ex.message; break; }
        }
      }
      restBusy = false; restCount();
      toast(badN ? `${okN} gesendet, ${badN} nicht zugestellt.` : `Sonderposten an ${plural(okN, 'Kunden', 'Kunden')} gesendet.`, 6000);
    }
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

  /* Bestellverwaltung: Versandzustand und Bearbeitung bleiben getrennt. */
  const ORDER_LABELS = { neu: 'Neu', in_bearbeitung: 'In Bearbeitung', bestaetigt: 'Bestätigt', erledigt: 'Erledigt', storniert: 'Storniert' };
  const ORDER_NEXT = { neu: ['in_bearbeitung', 'storniert'], in_bearbeitung: ['neu', 'bestaetigt', 'storniert'], bestaetigt: ['in_bearbeitung', 'erledigt', 'storniert'], erledigt: [], storniert: [] };
  const ORDER_MAIL = { neu: ['st-warn', 'Zustellung ungeklärt'], gesendet: ['st-ok', 'Vom Mailserver angenommen'], fehler: ['st-err', 'Versand nicht bestätigt'] };
  const orderBadge = (w) => `<span class="ord-st ord-${esc(w)}">${esc(ORDER_LABELS[w] || w)}</span>`;
  const orderMail = (d, pending = 0) => { const m = pending ? ['st-warn', 'Versandaufträge offen'] : ORDER_MAIL[d] || ['', d || '']; return `<span class="${m[0]}">${esc(m[1])}</span>`; };
  const dmyIso = (s) => (s && /^\d{4}-\d{2}-\d{2}/.test(s) ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : '');
  let orderOffset = 0, orderQuery = '', orderFilter = '', orderStaff = [], orderEdit = null;
  async function renderOrdersView() {
    const host = $('#view-orders');
    if (!host.innerHTML) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Bestellwünsche werden geladen …</div>';
    try {
      const r = await api('bestellungen', { query: '&offset=' + orderOffset + '&q=' + encodeURIComponent(orderQuery) + '&workflow=' + encodeURIComponent(orderFilter) });
      orderStaff = r.assignees || [];
      const staffName = (id) => (orderStaff.find((u) => u.id === id) || {}).name || '';
      const rows = r.orders.map((o) => `<tr data-order-nr="${esc(o.nr)}" tabindex="0">
          <td class="ord-nr"><div class="nm">${esc(o.nr)}</div><div class="sub">${esc(dateTime(o.t))}</div></td>
          <td><div class="nm">${esc(o.firma)}</div><div class="sub">${esc(o.angebotName || '')}${o.referenz ? ' · Ref. ' + esc(o.referenz) : ''}</div>${o.mailPending ? `<div class="ord-mobile-mail form-err">${esc(plural(o.mailPending, 'Versandauftrag', 'Versandaufträge'))} offen</div>` : ''}</td>
          <td class="ord-wish">${o.termin ? esc(dmyIso(o.termin)) : '<span class="muted">offen</span>'}</td>
          <td class="ord-sum">${plural(o.positionCount, 'Position', 'Positionen')}<div class="sub">${esc(fmtNum.format(o.total))} €${o.onRequest ? ' + a. Anfr.' : ''}</div></td>
          <td>${orderBadge(o.workflow)}${o.assignee ? `<div class="sub">${esc(staffName(o.assignee))}</div>` : ''}</td>
          <td class="ord-mail">${orderMail(o.delivery, o.mailPending)}${o.mailPending ? `<br><span class="form-err">${esc(plural(o.mailPending, 'Versandauftrag', 'Versandaufträge'))} offen</span>` : ''}</td>
        </tr>`).join('');
      host.innerHTML = `<form id="orders-filter" class="ed-toolbar ord-filter">
          <label class="search">${icon('search')}<input name="q" type="search" value="${esc(orderQuery)}" placeholder="Nummer, Firma oder Referenz" aria-label="Bestellwunsch suchen"></label>
          <select name="workflow" class="in" aria-label="Status"><option value="">Alle Status</option>${Object.entries(ORDER_LABELS).map(([k, v]) => `<option value="${k}"${orderFilter === k ? ' selected' : ''}>${v}</option>`).join('')}</select>
          <button class="btn" type="submit">Anzeigen</button>
          <span class="ed-hint">${plural(r.total, 'Bestellwunsch', 'Bestellwünsche')} · Bearbeitungsstatus ist intern und keine Auftragsbestätigung</span>
        </form>
        ${r.orders.length ? `<div class="gcard"><table class="etab ordtab"><thead><tr><th>Nummer / Eingang</th><th>Kunde</th><th class="ord-wish">Wunschtermin</th><th class="ord-sum">Umfang</th><th>Status</th><th class="ord-mail">E-Mail</th></tr></thead><tbody>${rows}</tbody></table></div>`
          : `<p class="hint">${orderQuery || orderFilter ? 'Keine Bestellwünsche zu dieser Auswahl.' : 'Noch keine Bestellwünsche eingegangen.'}</p>`}
        ${r.total > r.limit ? `<div class="ed-toolbar ord-pager"><button type="button" class="btn sm" data-orders-page="-1"${orderOffset === 0 ? ' disabled' : ''}>Zurück</button><span class="ed-hint">${Math.min(orderOffset + 1, r.total)}–${Math.min(orderOffset + r.limit, r.total)} von ${r.total}</span><button type="button" class="btn sm" data-orders-page="1"${orderOffset + r.limit >= r.total ? ' disabled' : ''}>Weiter</button></div>` : ''}`;
    } catch (e) { host.innerHTML = `<div class="err-box" role="alert">${esc(e.message)}</div><button type="button" class="btn" data-orders-reload>Erneut laden</button>`; }
  }
  async function openOrder(nr) {
    let o;
    try { o = orderEdit = (await api('bestellung', { query: '&nr=' + encodeURIComponent(nr) })).order; } catch (e) { toast(e.message); return; }
    const d = $('#dlg-order-admin');
    const states = [o.workflow, ...(ORDER_NEXT[o.workflow] || [])];
    const closed = !(ORDER_NEXT[o.workflow] || []).length;
    const k = o.kunde;
    const staffName = (id) => (orderStaff.find((u) => u.id === id) || {}).name || '';
    d.innerHTML = `<form class="dlg" id="order-edit-form">
      <div class="dlg-head"><div><h2 id="order-admin-title">${esc(o.nr)} · ${esc(o.firma)}</h2><p>${esc(o.angebotName || '')}${o.week ? ` · KW ${esc(o.week)}/${esc(o.year)}` : ''} · Eingang ${esc(dateTime(o.t))} · ${orderMail(o.delivery, o.mailPending)}${o.deliveryError ? ` <span class="muted">(${esc(o.deliveryError)})</span>` : ''}</p></div>
        <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        <div class="ord-meta">
          <div><span>Kunde</span>${k ? `<strong>${esc(k.firma || o.firma)}</strong>${esc([k.nr ? 'Kd.-Nr. ' + k.nr : '', k.ansprechpartner].filter(Boolean).join(' · '))}<br>${esc([k.email, k.telefon].filter(Boolean).join(' · '))}` : '<span class="muted">Kein Kontaktschnappschuss (älterer Vorgang)</span>'}</div>
          <div><span>Wunschtermin</span>${o.termin ? esc(dmyIso(o.termin)) : 'offen'}${o.referenz ? `<br><span>Referenz</span>${esc(o.referenz)}` : ''}</div>
        </div>
        ${o.bemerkung ? `<p class="ord-note"><strong>Bemerkung des Kunden:</strong> ${esc(o.bemerkung)}</p>` : ''}
        <table class="etab ordpos"><thead><tr><th>Art.-Nr.</th><th>Artikel</th><th class="r">Menge</th><th class="r">Preis</th><th class="r">Summe</th></tr></thead><tbody>
          ${o.positions.map((p) => `<tr><td class="mono">${esc(p.code || '—')}</td><td>${esc(p.name)}</td><td class="r">${esc(fmtNum.format(p.qty))} kg</td><td class="r">${p.price == null ? 'a. Anfr.' : esc(fmtNum.format(p.price)) + ' €'}</td><td class="r">${p.sum == null ? '–' : esc(fmtNum.format(p.sum)) + ' €'}</td></tr>`).join('')}
        </tbody><tfoot><tr><td colspan="2"><strong>Summe (ca.)</strong></td><td class="r">${esc(fmtNum.format(o.totalQty || 0))} kg</td><td></td><td class="r"><strong>${esc(fmtNum.format(o.total))} €</strong></td></tr></tfoot></table>
        ${o.onRequest ? `<p class="hint">Zuzüglich ${plural(o.onRequest, 'Position', 'Positionen')} mit Preis auf Anfrage.</p>` : ''}
        <section class="ord-outbox"><h3>E-Mail-Versand</h3>
          <p class="hint">Erfolgreich bedeutet: vom Mailserver angenommen. Bei einem Verbindungsabbruch kann eine E-Mail trotz fehlender Bestätigung angekommen sein. Vor erneutem Versand bitte prüfen.</p>
          ${(o.outbox || []).length ? o.outbox.map((j) => `<div class="ord-mailjob"><strong>${j.kind === 'bestellkopie' ? 'Kundenkopie' : 'Interner Empfänger'} · ${esc(j.to)}</strong><p>${esc(({queued:'Wartet auf Versand',sending:'Versand läuft oder wurde unterbrochen – Status prüfen',sent:'Vom Mailserver angenommen',failed:'Versand nicht bestätigt'})[j.state] || j.state)} · Versuche: ${esc(j.attempts)} · ${esc(dateTime(j.updatedAt))}</p>${j.error ? `<p class="form-err">${esc(j.error)}</p>` : ''}${j.state !== 'sent' ? `<button type="button" class="btn sm" data-order-mail="${esc(j.id)}">${j.attempts ? 'Erneuten Versand prüfen' : 'Versand starten'}</button>` : ''}${j.history.length ? `<details><summary>Versandverlauf</summary><ul>${j.history.map((h) => `<li>${esc(dateTime(h.t))} · ${esc(h.by)} · Versuch ${esc(h.attempt)} · ${esc(({sending:'Gestartet',sent:'Angenommen',failed:'Nicht bestätigt'})[h.state] || h.state)}</li>`).join('')}</ul></details>` : ''}</div>`).join('') : '<p class="hint">Für diesen älteren Vorgang liegen keine einzelnen Versandaufträge vor. Ein gezielter Neuversand ist hier nicht möglich.</p>'}
        </section>
        <div class="form-grid two">
          <label class="fld"><span>Bearbeitungsstatus</span><select name="workflow"${closed ? ' disabled' : ''}>${states.map((s) => `<option value="${s}"${o.workflow === s ? ' selected' : ''}>${ORDER_LABELS[s]}</option>`).join('')}</select></label>
          <label class="fld"><span>Verantwortlich</span><select name="assignee"><option value="">Nicht zugeordnet</option>${orderStaff.map((u) => `<option value="${esc(u.id)}"${o.assignee === u.id ? ' selected' : ''}>${esc(u.name)}</option>`).join('')}</select></label>
          <label class="fld span2"><span>Interne Notiz <small class="muted">(für Kunden nicht sichtbar)</small></span><textarea name="note" rows="3" maxlength="2000">${esc(o.note || '')}</textarea></label>
        </div>
        <p class="hint">Statusänderungen sind intern – es wird keine Bestätigung an den Kunden gesendet. Kunden sehen „Eingegangen“, „In Bearbeitung“, „Erledigt“ oder „Storniert“. Erledigte oder stornierte Vorgänge bleiben abgeschlossen.</p>
        ${o.history.length ? `<details class="ord-hist"><summary>Änderungsverlauf (${o.history.length})</summary><ul>${o.history.slice().reverse().map((h) => `<li><span>${esc(dateTime(h.t))} · ${esc(h.by)}</span><span>${h.from !== h.to ? `${esc(ORDER_LABELS[h.from] || h.from)} → ` : ''}<strong>${esc(ORDER_LABELS[h.to] || h.to)}</strong>${h.assignee ? ' · ' + esc(staffName(h.assignee) || 'zugeordnet') : ''}${h.note ? ' · „' + esc(h.note) + '“' : ''}</span></li>`).join('')}</ul></details>` : ''}
        <p class="form-err" id="order-edit-error" role="alert"></p>
      </div>
      <div class="dlg-foot"><span class="left"><button type="button" class="btn ghost" data-order-refresh>Neu laden</button></span><button type="button" class="btn" data-close>Abbrechen</button><button type="submit" class="btn primary">${icon('check')}Speichern</button></div></form>`;
    if (!d.open) d.showModal();
  }
  $('#view-orders').addEventListener('submit', (e) => { if (e.target.id !== 'orders-filter') return; e.preventDefault(); orderQuery = e.target.q.value; orderFilter = e.target.workflow.value; orderOffset = 0; renderOrdersView(); });
  $('#view-orders').addEventListener('click', (e) => {
    const b = e.target.closest('button');
    if (b && b.hasAttribute('data-orders-page')) { orderOffset = Math.max(0, orderOffset + Number(b.dataset.ordersPage) * 25); renderOrdersView(); return; }
    if (b && b.hasAttribute('data-orders-reload')) { renderOrdersView(); return; }
    const tr = e.target.closest('tr[data-order-nr]');
    if (tr) openOrder(tr.dataset.orderNr);
  });
  $('#view-orders').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr[data-order-nr]')) openOrder(e.target.dataset.orderNr); });
  $('#dlg-order-admin').addEventListener('click', async (e) => {
    if (e.target === e.currentTarget || e.target.closest('[data-close]')) { e.currentTarget.close(); return; }
    if (e.target.closest('[data-order-refresh]')) openOrder(orderEdit.nr);
    const retry = e.target.closest('[data-order-mail]');
    if (retry) {
      const o = orderEdit, j = o.outbox.find((x) => x.id === retry.dataset.orderMail);
      if (!j || !(await confirmBox('E-Mail versenden?', `Bestellwunsch ${esc(o.nr)} an ${esc(j.to)}. Bei einem früheren Verbindungsabbruch kann die Nachricht bereits angekommen sein. Bitte prüfen. Nur diese Nachricht wird gesendet; es entsteht keine neue Bestellung. Ungespeicherte Änderungen im Dialog werden verworfen.`, 'Versand bestätigen', true))) return;
      retry.disabled = true;
      try {
        const r = await api('bestellung_mail_retry', { body: {nr:o.nr, jobId:j.id, attempts:j.attempts, confirm:true} });
        const sent = r.order.outbox.find((x) => x.id === j.id).state === 'sent';
        await openOrder(o.nr); renderOrdersView(); toast(sent ? 'Mailserver hat die Nachricht angenommen.' : 'Versand weiterhin nicht bestätigt. Bitte Fehlerhinweis prüfen.', 6000);
      } catch (ex) { $('#order-edit-error').textContent = ex.message; retry.disabled = false; }
    }
  });
  $('#dlg-order-admin').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target, btn = f.querySelector('[type=submit]');
    btn.disabled = true;
    try {
      await api('bestellung_save', { body: { nr: orderEdit.nr, revision: orderEdit.revision, workflow: f.workflow.value, assignee: f.assignee.value, note: f.note.value } });
      $('#dlg-order-admin').close();
      toast(`${orderEdit.nr} gespeichert.`);
      renderOrdersView();
    } catch (ex) { $('#order-edit-error').textContent = ex.message; } finally { btn.disabled = false; }
  });

  /* ======================= Kunden (Administrator) =======================
     Kundenstammdaten, Freischaltung der Angebote und Zugang zur Angebotsseite (Benutzername + Passwort).
     Passwörter werden nur als Hash gespeichert und nie angezeigt. */
  let kunden = null, kundenRev = 0, kundenQ = '', mailSt = null;
  const MAIL_TYP = { woche: 'Wochenangebot', angebot: 'Angebotslink', invite: 'Einladung', reset: 'Passwort-Link', test: 'Testmail', hinweis: 'Hinweis Abmeldung', bestellung: 'Bestellwunsch', bestellkopie: 'Kopie Bestellwunsch' };
  const dlgKunde = $('#dlg-kunde');
  let editKid = null;
  const offerChip = (id) => `<span class="k-chip${id === OSTD ? ' std' : ''}">${esc(offerShort(id))}</span>`;
  async function renderKundenView() {
    const host = $('#view-kunden');
    if (!kunden) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Kunden werden geladen …</div>';
    try {
      const [r, m] = await Promise.all([api('kunden'), api('mail_status'), offers.length ? null : loadOffers()]);
      kunden = r.customers; kundenRev = r.rev; mailSt = m;
    } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    host.innerHTML = `
      <div class="ed-toolbar">
        <div class="search">${icon('search')}<input id="k-q" type="search" autocomplete="off" placeholder="Kunden finden: Firma, Nummer, Ort, Ansprechpartner …" aria-label="Kunden suchen" value="${esc(kundenQ)}"></div>
        <span class="ed-hint" id="k-count"></span>
        <button type="button" class="btn" id="k-mailcfg" title="E-Mail-Versand: Einstellungen, Signatur, Testmail">${icon('mail')}E-Mail${mailSt.configured ? '' : ' <span class="k-warn">nicht eingerichtet</span>'}</button>
        <button type="button" class="btn" id="k-rund">${icon('send')}Wochenangebot versenden</button>
        <button type="button" class="btn primary" id="k-add">${icon('plus')}Kunde anlegen</button>
      </div>
      <div id="k-list"></div>
      <p class="hint k-note">Kunden melden sich auf der Angebotsseite über „Kunden-Login“ an und sehen nur die hier freigeschalteten Angebote. ${stdPublic ? 'Das Wochenangebot ist derzeit zusätzlich öffentlich ohne Anmeldung sichtbar (umstellbar unter Angebot bearbeiten → Angebote verwalten).' : 'Das Wochenangebot ist derzeit nicht öffentlich – nur freigeschaltete Kunden sehen es.'}</p>`;
    renderKundenList();
  }
  function renderKundenList() {
    const toks = fold(kundenQ).split(/\s+/).filter(Boolean);
    const list = kunden.filter((c) => { const hay = fold([c.nr, c.firma, c.ansprechpartner, c.ort, c.plz, c.email, c.login && c.login.username].join(' ')); return toks.every((t) => hay.includes(t)); });
    $('#k-count').textContent = plural(list.length, 'Kunde', 'Kunden') + (list.length !== kunden.length ? ` von ${kunden.length}` : '');
    const host = $('#k-list');
    if (!kunden.length) { host.innerHTML = '<div class="ed-empty"><h3>Noch keine Kunden</h3><p>Legen Sie Kunden mit Ansprechpartner, Adresse und Zugang an und schalten Sie die passenden Angebote frei.</p></div>'; return; }
    if (!list.length) { host.innerHTML = '<div class="ed-empty"><h3>Keine Treffer</h3><p>Suchbegriff anpassen.</p></div>'; return; }
    const st = (c) => {
      const l = c.login;
      if (!c.active) return '<span class="st-err">Kunde inaktiv</span>';
      if (!l) return '<span class="muted">kein Zugang</span>';
      if (!l.active) return '<span class="st-err">Zugang deaktiviert</span>';
      if (!l.hasPassword) return `<span class="st-warn">${l.link ? `Einladung offen bis ${esc(dmyTs(l.link.exp))}` : 'noch kein Passwort'}</span>`;
      return `<span class="st-ok">Zugang aktiv</span>${l.lockedUntil ? `<div class="sub st-err">gesperrt bis ${esc(timeOnly(new Date(l.lockedUntil * 1000).toISOString()))} Uhr</div>` : ''}${l.mustChange ? '<div class="sub">Startpasswort noch nicht geändert</div>' : ''}`;
    };
    host.innerHTML = `<div class="gcard"><table class="etab utab ktab"><thead><tr><th>Firma / Ansprechpartner</th><th class="k-addr">Ort</th><th>Freigeschaltete Angebote</th><th class="u-st">Zugang</th><th class="u-last">Letzte Anmeldung</th><th class="u-act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${list.map((c) => `
      <tr data-kid="${esc(c.id)}" tabindex="0" class="${c.active ? '' : 'inactive'}">
        <td class="u-name"><div class="nm">${esc(c.firma)}${c.nr ? ` <span class="muted">· ${esc(c.nr)}</span>` : ''}</div><div class="sub">${esc(c.ansprechpartner || '')}${c.email ? `${c.ansprechpartner ? ' · ' : ''}${esc(c.email)}` : ''}</div></td>
        <td class="k-addr">${esc([c.plz, c.ort].filter(Boolean).join(' '))}</td>
        <td class="k-offers">${c.angebote.length ? c.angebote.map(offerChip).join(' ') : '<span class="muted">keines</span>'}${mailLine(c)}</td>
        <td class="u-st">${st(c)}${c.login ? `<div class="sub uname">${esc(c.login.username)}</div>` : ''}</td>
        <td class="u-last">${c.login && c.login.lastLogin ? esc(dateTime(c.login.lastLogin)) : '<span class="muted">noch nie</span>'}</td>
        <td class="u-act"><button type="button" class="btn sm" data-kedit="${esc(c.id)}">Bearbeiten</button></td>
      </tr>`).join('')}</tbody></table></div>`;
  }
  $('#view-kunden').addEventListener('input', (e) => { if (e.target.id === 'k-q') { kundenQ = e.target.value; renderKundenList(); } });
  const dmyTs = (ts) => new Date(ts * 1000).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const wkCur = () => (mailSt && mailSt.week) || null;
  const sentThisWeek = (c) => { const w = wkCur(); return !!(w && c.weekly && c.weekly.week === w.week && c.weekly.year === w.year); };
  function mailLine(c) {
    const parts = [];
    if (c.mailAngebot === false && c.abgemeldet) parts.push(`<span class="st-warn">vom Wochenangebot abgemeldet ${esc(dateTime(c.abgemeldet.t))}</span>`);
    else if (c.mailAngebot === false) parts.push('<span class="muted">kein Wochenangebot per E-Mail</span>');
    else if (sentThisWeek(c)) parts.push(`<span class="st-ok">${icon('check', 'sm')}KW ${c.weekly.week} gesendet ${esc(dateTime(c.weekly.t))}</span>`);
    if (c.mailLast && !c.mailLast.ok) parts.push(`<span class="st-err">${esc(MAIL_TYP[c.mailLast.typ] || 'E-Mail')} nicht zugestellt</span>`);
    return parts.length ? `<div class="sub k-mail">${parts.join(' · ')}</div>` : '';
  }
  $('#view-kunden').addEventListener('click', (e) => {
    if (e.target.closest('#k-add')) { openKunde(null); return; }
    if (e.target.closest('#k-mailcfg')) { openMailCfg(); return; }
    if (e.target.closest('#k-rund')) { openRund(); return; }
    const tr = e.target.closest('tr[data-kid]');
    if (tr) openKunde(tr.dataset.kid);
  });
  $('#view-kunden').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr[data-kid]')) openKunde(e.target.dataset.kid); });
  /* Vorschlag für den Benutzernamen aus der Firma */
  const unameFrom = (t) => fold(t).replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss').replace(/\b(gmbh|co|kg|ag|ug|ohg|e\.?k|mbh|und|&)\b/g, ' ').replace(/[^a-z0-9]+/g, '.').replace(/^\.+|\.+$/g, '').slice(0, 32);
  function openKunde(id) {
    const c = id ? kunden.find((x) => x.id === id) : null;
    editKid = id;
    const l = c && c.login;
    const has = (o) => (c ? c.angebote.includes(o) : false);
    const mailOk = !!(mailSt && mailSt.configured);
    const pwMode = !!(l && l.hasPassword) || !mailOk;      // true = Passwortfeld zeigen
    const fld = (n, label, max, attrs = '', cls = '') => `<label class="fld${cls ? ' ' + cls : ''}"><span>${label}</span><input name="${n}" value="${esc(c ? c[n] || '' : '')}" maxlength="${max}"${attrs}></label>`;
    $('#kunde-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="kd-title">${c ? esc(c.firma) : 'Kunde anlegen'}</h2><p>${c ? `Angelegt ${esc(dateTime(c.created))}${c.changed && c.changed !== c.created ? ` · geändert ${esc(dateTime(c.changed))}` : ''}` : 'Stammdaten, freigeschaltete Angebote und Zugang zur Angebotsseite.'}</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        <fieldset class="k-set"><legend>Stammdaten</legend><div class="form-grid two">
          ${fld('firma', 'Firma / Name', 120, ' required placeholder="z. B. Gasthaus Muster GmbH"', 'span2')}
          ${fld('nr', 'Kundennummer', 30, ' placeholder="optional"')}
          ${fld('ansprechpartner', 'Ansprechpartner', 120, ' placeholder="z. B. Frau Beispiel"')}
          ${fld('strasse', 'Straße und Hausnummer', 120, '', 'span2')}
          ${fld('plz', 'PLZ', 10, ' inputmode="numeric"')}
          ${fld('ort', 'Ort', 80)}
          ${fld('email', 'E-Mail', 160, ' type="email" autocapitalize="none" spellcheck="false"')}
          ${fld('telefon', 'Telefon', 40, ' type="tel"')}
          ${fld('land', 'Land', 60, ' placeholder="Deutschland"')}
          <label class="fld span2"><span>Notiz <small class="muted">(nur intern)</small></span><textarea name="notiz" maxlength="500" rows="2">${esc(c ? c.notiz || '' : '')}</textarea></label>
          <label class="check span2"><input type="checkbox" name="active"${!c || c.active ? ' checked' : ''}> Kunde aktiv <small class="muted">(inaktive Kunden können sich nicht anmelden)</small></label>
          <label class="check span2"><input type="checkbox" name="mailAngebot"${!c || c.mailAngebot !== false ? ' checked' : ''}> Wochenangebot per E-Mail erhalten <small class="muted">(nur mit Einverständnis des Kunden)</small></label>
          ${c && c.abgemeldet && c.mailAngebot === false ? `<p class="hint span2 st-warn k-abm-note">Der Kunde hat sich am ${esc(dateTime(c.abgemeldet.t))} selbst über den Link in der E-Mail abgemeldet. Die E-Mail-Adresse bleibt gespeichert.</p>` : ''}
        </div></fieldset>
        <fieldset class="k-set"><legend>Freigeschaltete Angebote</legend>
          <div class="k-offers-pick">${[OSTD, ...offers.map((o) => o.id)].map((o) => `<label class="check"><input type="checkbox" name="angebot" value="${esc(o)}"${has(o) ? ' checked' : ''}> ${esc(offerName(o))}${o === OSTD && stdPublic ? ' <small class="muted">(ohnehin öffentlich)</small>' : ''}</label>`).join('')}</div>
          <p class="hint">Der Kunde sieht nach der Anmeldung nur diese Angebote. Ist mehr als eines freigeschaltet, kann er zwischen ihnen wechseln.</p>
        </fieldset>
        ${c ? `<fieldset class="k-set"><legend>E-Mail an den Kunden</legend>
          <div class="k-mailact">
            <button type="button" class="btn sm" data-kact="m-zugang"${mailOk && c.email && l && l.active ? '' : ' disabled'}>${icon('key', 'sm')}${l && !l.hasPassword ? 'Einladung erneut senden' : 'Link zum Passwort-Zurücksetzen senden'}</button>
            <button type="button" class="btn sm" data-kact="m-angebot"${mailOk && c.email && c.angebote.length && c.mailAngebot !== false ? '' : ' disabled'} title="${c.mailAngebot === false ? 'Kunde erhält keine Angebotsmails' : ''}">${icon('link', 'sm')}Angebotslink senden</button>
          </div>
          <p class="hint">${!mailOk ? 'Der E-Mail-Versand ist noch nicht eingerichtet (Verwaltung → E-Mail).' : !c.email ? 'Keine E-Mail-Adresse hinterlegt.' : `An ${esc(c.email)}. Ein Passwort-Link ist ${l && !l.hasPassword ? '7 Tage' : '2 Tage'} gültig und nur einmal verwendbar.`}${c.mailLast ? ` Letzte E-Mail: ${esc(MAIL_TYP[c.mailLast.typ] || '')}, ${esc(dateTime(c.mailLast.t))} ${c.mailLast.ok ? '✓' : '– nicht zugestellt'}.` : ''}</p>
        </fieldset>` : ''}
        <fieldset class="k-set"><legend>Zugang zur Angebotsseite</legend>
          <label class="check"><input type="checkbox" name="hasLogin"${!c || l ? ' checked' : ''}> Zugang einrichten (Benutzerkennung und Passwort)</label>
          <div class="form-grid two k-login"${!c || l ? '' : ' hidden'}>
            <label class="fld${pwMode ? '' : ' span2'}"><span>Benutzerkennung</span><input name="username" value="${esc(l ? l.username : '')}" maxlength="32" autocapitalize="none" spellcheck="false" placeholder="z. B. gasthaus.muster"></label>
            ${!l || !l.hasPassword ? `<div class="fld span2"><span>Passwort</span><div class="k-pwmode">
              <label class="check"><input type="radio" name="pwmode" value="invite"${!pwMode ? ' checked' : ''}${mailOk ? '' : ' disabled'}> Einladung per E-Mail – der Kunde legt sein Passwort über einen Link selbst fest${mailOk ? '' : ' <small class="muted">(E-Mail-Versand noch nicht eingerichtet)</small>'}</label>
              <label class="check"><input type="radio" name="pwmode" value="manual"${pwMode ? ' checked' : ''}> Startpasswort selbst vergeben und weitergeben</label></div></div>` : ''}
            <div class="fld k-pwfld"${pwMode ? '' : ' hidden'}><span>${l && l.hasPassword ? 'Neues Passwort <small class="muted">(leer = unverändert)</small>' : 'Startpasswort'}</span>
              <div class="pw-row"><input name="password" type="text" autocomplete="new-password" minlength="10" maxlength="200" placeholder="mindestens 10 Zeichen"><button type="button" class="btn" data-kact="gen">Vorschlag</button></div></div>
            <label class="check span2 k-pwfld"${pwMode ? '' : ' hidden'}><input type="checkbox" name="mustChange" checked> Kunde muss das Passwort bei der ersten Anmeldung ändern</label>
            <label class="check span2"><input type="checkbox" name="loginActive"${!l || l.active ? ' checked' : ''}> Zugang aktiv</label>
            ${l && l.lockedUntil ? `<label class="check span2 st-err"><input type="checkbox" name="unlock" checked> Sperre nach Fehlversuchen aufheben (gesperrt bis ${esc(timeOnly(new Date(l.lockedUntil * 1000).toISOString()))} Uhr)</label>` : ''}
            ${l ? `<p class="hint span2">Letzte Anmeldung: ${l.lastLogin ? esc(dateTime(l.lastLogin)) : 'noch nie'}${l.pwSet ? ` · Passwort gesetzt ${esc(dateTime(l.pwSet))}` : ''}${c.sessions ? ` · ${plural(c.sessions, 'aktive Sitzung', 'aktive Sitzungen')}` : ''}${l.mustChange ? ' · Startpasswort noch nicht geändert' : ''}${l.link ? ` · ${l.link.p === 'invite' ? 'Einladung' : 'Passwort-Link'} gültig bis ${esc(dmyTs(l.link.exp))}` : ''}</p>` : ''}
          </div>
          ${l ? '<p class="hint k-nologin" hidden>Beim Speichern wird der Zugang entfernt und der Kunde abgemeldet.</p>' : ''}
        </fieldset>
        <p class="form-err" id="kunde-err" role="alert"></p>
      </div>
      <div class="dlg-foot">
        <span class="left">${c ? `<button type="button" class="btn sm ghost" data-kact="del" style="color:var(--accent)">${icon('trash', 'sm')}Kunde löschen</button>` : ''}</span>
        <button type="button" class="btn" data-close>Abbrechen</button>
        <button type="submit" class="btn primary">${c ? 'Speichern' : 'Kunde anlegen'}</button>
      </div>`;
    dlgKunde.showModal();
    $('#kunde-body [name="firma"]').focus();
  }
  $('#kunde-body').addEventListener('change', (e) => {
    if (e.target.name === 'pwmode') { for (const el of $$('#kunde-body .k-pwfld')) el.hidden = e.target.value !== 'manual'; return; }
    if (e.target.name === 'hasLogin') {
      $('#kunde-body .k-login').hidden = !e.target.checked;
      const n = $('#kunde-body .k-nologin'); if (n) n.hidden = e.target.checked;
    }
  });
  $('#kunde-body').addEventListener('input', (e) => {
    if (e.target.name !== 'firma' || editKid) return;
    const u = $('#kunde-body [name="username"]');
    if (!u.dataset.touched) u.value = unameFrom(e.target.value);
  });
  $('#kunde-body').addEventListener('keydown', (e) => { if (e.target.name === 'username') e.target.dataset.touched = '1'; });
  dlgKunde.addEventListener('click', async (e) => {
    const a = e.target.closest('[data-kact]')?.dataset.kact;
    if (a === 'gen') { const i = $('#kunde-body [name="password"]'); i.value = genPassword(); i.select(); return; }
    if (a === 'm-zugang' || a === 'm-angebot') {
      const c = kunden.find((x) => x.id === editKid), btn = e.target.closest('[data-kact]');
      const what = a === 'm-angebot' ? 'den Link zum Angebot' : c.login && !c.login.hasPassword ? 'eine neue Einladung (ein bisheriger Link wird ungültig)' : 'einen Link zum Festlegen eines neuen Passworts (das bisherige Passwort bleibt gültig, bis der Kunde ein neues festlegt)';
      if (!(await confirmBox('E-Mail senden?', `„${esc(c.firma)}“ erhält an ${esc(c.email)} ${what}.`, 'Senden'))) return;
      btn.disabled = true;
      try { await kundeMail(c, a === 'm-angebot' ? 'angebot' : 'zugang'); dlgKunde.close(); renderKundenView(); }
      catch (ex) { $('#kunde-err').textContent = ex.message; btn.disabled = false; }
      return;
    }
    if (a === 'del') {
      const c = kunden.find((x) => x.id === editKid);
      if (!(await confirmBox('Kunde löschen?', `„${esc(c.firma)}“ wird mit Stammdaten und Zugang gelöscht; eine laufende Anmeldung endet sofort. Die Einträge im Protokoll bleiben erhalten. Alternativ den Kunden nur auf „inaktiv“ setzen.`, 'Löschen', true))) return;
      try { const r = await api('kunde_delete', { body: { id: c.id, rev: kundenRev } }); kundenRev = r.rev; dlgKunde.close(); toast(`Kunde „${c.firma}“ gelöscht.`); renderKundenView(); }
      catch (ex) { $('#kunde-err').textContent = ex.message; }
    }
  });
  $('#kunde-body').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target, err = $('#kunde-err');
    err.textContent = '';
    const c = editKid ? kunden.find((x) => x.id === editKid) : null;
    const body = { id: editKid || '', rev: kundenRev, active: f.active.checked, mailAngebot: f.mailAngebot.checked, angebote: $$('#kunde-body [name="angebot"]:checked').map((x) => x.value) };
    const invite = !!(f.pwmode && [...f.querySelectorAll('[name="pwmode"]')].find((x) => x.checked && x.value === 'invite'));
    if (c && c.abgemeldet && c.mailAngebot === false && body.mailAngebot
      && !(await confirmBox('Wochenangebot wieder einschalten?', `„${esc(c.firma)}“ hat sich am ${esc(dateTime(c.abgemeldet.t))} selbst abgemeldet. Bitte nur wieder einschalten, wenn der Kunde ausdrücklich zugestimmt hat.`, 'Kunde hat zugestimmt'))) return;
    for (const k of ['firma', 'nr', 'ansprechpartner', 'strasse', 'plz', 'ort', 'land', 'email', 'telefon', 'notiz']) body[k] = f[k].value.trim();
    const pw = invite ? '' : f.password.value.trim();
    if (f.hasLogin.checked) {
      if (pw && pw.length < 10) { err.textContent = 'Das Passwort muss mindestens 10 Zeichen lang sein.'; return; }
      if (!invite && !(c && c.login && c.login.hasPassword) && !pw) { err.textContent = 'Bitte ein Startpasswort festlegen (z. B. über „Vorschlag“).'; f.password.focus(); return; }
      if (invite && !body.email) { err.textContent = 'Für die Einladung per E-Mail bitte die E-Mail-Adresse angeben.'; f.email.focus(); return; }
      body.login = { username: f.username.value.trim(), password: pw, mustChange: f.mustChange.checked, active: f.loginActive.checked, unlock: !!(f.unlock && f.unlock.checked), invite };
    } else if (c && c.login) {
      if (!(await confirmBox('Zugang entfernen?', `Der Zugang „${esc(c.login.username)}“ wird entfernt; der Kunde kann sich nicht mehr anmelden. Die Stammdaten bleiben erhalten.`, 'Zugang entfernen', true))) return;
      body.login = { remove: true };
    } else body.login = null;
    const btn = f.querySelector('[type="submit"]');
    btn.disabled = true;
    try {
      const r = await api('kunde_save', { body });
      kundenRev = r.rev;
      dlgKunde.close();
      const sendInvite = invite && r.customer.login && !r.customer.login.hasPassword && (!c || !c.login || !c.login.link || body.email !== c.email || body.login.username !== c.login.username);
      if (sendInvite) {
        try { await kundeMail(r.customer, 'zugang'); } catch (ex) { toast(`Kunde gespeichert, aber die Einladung wurde nicht versendet: ${ex.message}`, 9000); }
        renderKundenView();
        return;
      }
      toast(pw && body.login ? `Gespeichert. Zugangsdaten für „${r.customer.login.username}“ jetzt sicher an den Kunden weitergeben – das Passwort wird nicht noch einmal angezeigt.` : c ? `Änderungen an „${r.customer.firma}“ gespeichert.` : `Kunde „${r.customer.firma}“ angelegt.`, pw ? 7000 : 3200);
      renderKundenView();
    } catch (ex) { err.textContent = ex.message; if (ex.status === 409) { kunden = null; } } finally { btn.disabled = false; }
  });

  /* ---------- E-Mail an Kunden ---------- */
  async function kundeMail(c, type) {
    const r = await api('kunde_mail', { body: { id: c.id, type } });
    toast(`${MAIL_TYP[r.typ]} an ${c.email} gesendet.`, 4500);
    return r;
  }
  /* ======================= E-Mail-Einstellungen (Administrator) =======================
     Postfach (SMTP) und Absender, Signatur, Testmail, Versandprotokoll. Das Passwort wird nur gesendet,
     nie angezeigt; der Server speichert es verschlüsselt. */
  const MAIL_PRESETS = {
    hostinger: { label: 'Hostinger', host: 'smtp.hostinger.com', port: 465, secure: 'ssl' },
    ionos: { label: 'IONOS', host: 'smtp.ionos.de', port: 587, secure: 'starttls' },
  };
  function openMailCfg() { setView('mail'); }
  async function renderMailView() {
    const host = $('#view-mail');
    if (!mailSt) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>E-Mail-Einstellungen werden geladen …</div>';
    try { mailSt = await api('mail_status'); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    const m = mailSt, s = m.smtp, a = m.account || {};
    const secLabel = (x) => (x === 'ssl' ? 'SSL' : x === 'starttls' ? 'STARTTLS' : 'unverschlüsselt (nur lokal)');
    const status = m.configured && s
      ? `<div class="sec-card ${s.passError ? 'bad' : 'ok'}"><span class="sec-dot"></span><div><strong>${s.passError ? 'Passwort muss neu eingegeben werden' : 'E-Mail-Versand eingerichtet'}</strong><span>${esc(s.fromName)} &lt;${esc(s.from)}&gt; über ${esc(s.host)}:${esc(s.port)} (${esc(secLabel(s.secure))})${s.replyTo ? ` · Antworten an ${esc(s.replyTo)}` : ''}</span><em>${s.source === 'env' ? 'Werte aus der Server-Datei .env – hier gespeicherte Werte hätten Vorrang.' : `Gespeichert ${a.updatedAt ? esc(dateTime(a.updatedAt)) : ''}${a.updatedBy ? ' von ' + esc(a.updatedBy) : ''}. Links in E-Mails führen zu ${esc(m.baseUrl || '–')}.`}</em></div></div>`
      : `<div class="sec-card warn"><span class="sec-dot"></span><div><strong>Noch nicht eingerichtet</strong><span>Tragen Sie unten das Postfach ein, über das die E-Mails an Kunden versendet werden.</span>${m.baseUrl ? '' : '<em>Außerdem fehlt die Adresse der Seite für Links (DOMAIN in .env).</em>'}</div></div>`;
    const log = (m.log || []).slice(0, 50);
    host.innerHTML = `
      <div class="sec-grid">${status}</div>
      <form class="gcard sec-form" id="ml-form" autocomplete="off">
        <h3 class="sec-h">Postfach für den Versand</h3>
        <div class="ml-presets"><span class="sub">Vorlage:</span>${Object.entries(MAIL_PRESETS).map(([k, p]) => `<button type="button" class="btn sm" data-ml="preset" data-p="${k}">${esc(p.label)}</button>`).join('')}</div>
        <div class="sec-rows">
          <label class="fld"><span>Mailserver (SMTP)</span><input name="host" value="${esc(a.host || '')}" maxlength="253" autocapitalize="none" spellcheck="false" placeholder="z. B. smtp.hostinger.com" required></label>
          <div class="sec-rows ml-pair">
            <label class="fld"><span>Verschlüsselung</span><select name="secure">
              <option value="ssl"${(a.secure || 'ssl') === 'ssl' ? ' selected' : ''}>SSL (Port 465)</option>
              <option value="starttls"${a.secure === 'starttls' ? ' selected' : ''}>STARTTLS (Port 587)</option></select></label>
            <label class="fld"><span>Port</span><input name="port" type="number" min="1" max="65535" value="${esc(a.port || 465)}" required></label>
          </div>
          <label class="fld"><span>Benutzername</span><input name="user" value="${esc(a.user || '')}" maxlength="160" autocapitalize="none" spellcheck="false" autocomplete="off" placeholder="meist die E-Mail-Adresse des Postfachs"></label>
          <label class="fld"><span>Passwort</span><input name="password" type="password" autocomplete="new-password" maxlength="500" placeholder="${a.password ? '•••••••• gespeichert – leer lassen = unverändert' : 'Passwort des Postfachs'}">
            <small>Wird verschlüsselt gespeichert und nie wieder angezeigt. Bei geändertem Server oder Benutzer bitte erneut eingeben.</small></label>
        </div>
        <h3 class="sec-h ml-h2">Absender</h3>
        <div class="sec-rows">
          <label class="fld"><span>Absenderadresse</span><input name="from" type="email" value="${esc(a.from || '')}" maxlength="160" autocapitalize="none" spellcheck="false" placeholder="z. B. versand@angebot-stafl.de" required>
            <small>Muss zum Postfach passen, sonst lehnt der Mailserver ab oder die E-Mails landen im Spam.</small></label>
          <label class="fld"><span>Absendername</span><input name="fromName" value="${esc(a.fromName || '')}" maxlength="80" placeholder="Standard-Fleisch"></label>
          <label class="fld"><span>Antworten an <small>(optional)</small></span><input name="replyTo" type="email" value="${esc(a.replyTo || '')}" maxlength="160" autocapitalize="none" spellcheck="false" placeholder="z. B. verkauf@standard-fleisch.de">
            <small>Antworten der Kunden landen dort – z. B. das Postfach, das Sie täglich lesen.</small></label>
        </div>
        <p class="form-err" id="ml-err" role="alert"></p>
        <div class="sec-foot ml-foot">${m.account ? `<button type="button" class="btn ghost" data-ml="remove">${icon('trash', 'sm')}Einstellungen entfernen</button>` : ''}<button type="submit" class="btn primary">${icon('check')}Speichern und Verbindung prüfen</button></div>
      </form>
      <form class="gcard sec-form" id="ml-orders" autocomplete="off">
        <h3 class="sec-h">Bestellwünsche aus dem Portal</h3>
        <label class="check"><input type="checkbox" name="enabled"${m.orders.enabled ? ' checked' : ''}> Angemeldete Kunden können im Portal Mengen eingeben und einen Bestellwunsch senden</label>
        <div class="sec-rows ml-orows">
          <label class="fld span2"><span>Bestellwünsche senden an</span><input name="to" value="${esc(m.orders.to.join(', '))}" maxlength="500" autocapitalize="none" spellcheck="false" placeholder="z. B. bestellung@standard-fleisch.de, verkauf@standard-fleisch.de">
            <small>Eine oder mehrere Adressen (mit Komma getrennt, höchstens 5). Die E-Mail enthält Kundendaten, Positionen mit den Preisen des Kunden und die Summe; „Antworten“ geht direkt an den Kunden.</small></label>
          <label class="check span2"><input type="checkbox" name="copy"${m.orders.copy ? ' checked' : ''}> Kunde erhält eine Eingangsbestätigung mit allen Positionen an seine E-Mail-Adresse</label>
        </div>
        ${m.orders.enabled && !m.configured ? '<p class="st-warn ml-ohint">Aktiv wird die Bestellfunktion erst, wenn oben das Postfach für den Versand eingerichtet ist.</p>' : ''}
        <p class="form-err" id="ml-oerr" role="alert"></p>
        <div class="sec-foot"><button type="submit" class="btn">${icon('check', 'sm')}Speichern</button></div>
      </form>
      <div class="gcard sec-form">
        <h3 class="sec-h">Signatur</h3>
        <label class="fld"><span>Erscheint unter jeder E-Mail</span><textarea id="ml-sig" rows="5" maxlength="600" placeholder="Mit freundlichen Grüßen&#10;Standard-Fleisch …&#10;Anschrift, Telefon">${esc(m.signature)}</textarea>
          <small>Tipp: Anschrift, Telefon und Geschäftsführung ergänzen – geschäftliche E-Mails sollten den Absender vollständig nennen.</small></label>
        <div class="sec-foot"><button type="button" class="btn" data-ml="sig">${icon('check', 'sm')}Signatur speichern</button></div>
      </div>
      <div class="gcard sec-form">
        <h3 class="sec-h">Testmail</h3>
        <div class="k-test"><label class="fld grow"><span>Senden an</span><input id="ml-to" type="email" autocomplete="email" placeholder="ihre.adresse@standard-fleisch.de"></label><button type="button" class="btn" data-ml="test"${m.configured ? '' : ' disabled'}>${icon('send', 'sm')}Testmail senden</button></div>
        <p class="form-err" id="ml-err2" role="alert"></p>
      </div>
      <div class="gcard sec-form">
        <h3 class="sec-h">Zuletzt versendet</h3>
        ${log.length ? `<div class="ml-logwrap"><table class="ctab"><thead><tr><th>Zeit</th><th>Art</th><th>Kunde</th><th>An</th><th>Ergebnis</th></tr></thead><tbody>${log.map((x) => `<tr><td>${esc(dateTime(x.t))}</td><td>${esc(MAIL_TYP[x.typ] || x.typ)}</td><td>${esc(x.firma || '')}</td><td>${esc(x.to)}</td><td>${x.ok ? '<span class="st-ok">zugestellt</span>' : `<span class="st-err">${esc(x.error)}</span>`}</td></tr>`).join('')}</tbody></table></div>` : '<p class="sec-empty">Noch keine E-Mails versendet.</p>'}
      </div>`;
  }
  $('#view-mail').addEventListener('change', (e) => {
    if (e.target.name === 'secure') { const p = $('#ml-form [name="port"]'); if (['465', '587', ''].includes(p.value)) p.value = e.target.value === 'ssl' ? 465 : 587; }
  });
  $('#view-mail').addEventListener('submit', async (e) => {
    if (e.target.id === 'ml-orders') {
      e.preventDefault();
      const f = e.target, err = $('#ml-oerr'), btn = f.querySelector('[type="submit"]');
      err.textContent = ''; btn.disabled = true;
      try {
        const r = await api('bestell_settings_save', { body: { enabled: f.enabled.checked, to: f.to.value, copy: f.copy.checked } });
        mailSt.orders = r.orders;
        toast(r.orders.enabled ? (r.active ? 'Gespeichert – Kunden können jetzt Bestellwünsche senden.' : 'Gespeichert – aktiv, sobald das Postfach eingerichtet ist.') : 'Gespeichert – Bestellfunktion ist ausgeschaltet.', 5000);
        renderMailView();
      } catch (ex) { err.textContent = ex.message; } finally { btn.disabled = false; }
      return;
    }
    if (e.target.id !== 'ml-form') return;
    e.preventDefault();
    const f = e.target, err = $('#ml-err'), btn = f.querySelector('[type="submit"]');
    err.textContent = '';
    const body = { host: f.host.value.trim(), port: +f.port.value, secure: f.secure.value, user: f.user.value.trim(), password: f.password.value, from: f.from.value.trim(), fromName: f.fromName.value.trim(), replyTo: f.replyTo.value.trim() };
    btn.disabled = true;
    try {
      const r = await api('mail_konto_save', { body });
      f.password.value = '';
      if (r.connection.ok) toast('Gespeichert – Verbindung und Anmeldung am Mailserver erfolgreich. Jetzt eine Testmail senden.', 6000);
      else toast('Gespeichert, aber die Verbindung ist fehlgeschlagen – Details unten.', 6000);
      await renderMailView();
      if (!r.connection.ok) $('#ml-err').textContent = 'Verbindungsprüfung: ' + r.connection.error;
    } catch (ex) { err.textContent = ex.message; } finally { btn.disabled = false; }
  });
  $('#view-mail').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-ml]');
    if (!b) return;
    const a = b.dataset.ml;
    if (a === 'preset') {
      const p = MAIL_PRESETS[b.dataset.p], f = $('#ml-form');
      f.host.value = p.host; f.port.value = p.port; f.secure.value = p.secure;
      if (!f.user.value && f.from.value) f.user.value = f.from.value;
      f.user.focus();
      return;
    }
    if (a === 'remove') {
      if (!(await confirmBox('Einstellungen entfernen?', 'Postfach, Absender und gespeichertes Passwort werden gelöscht. Danach werden – falls vorhanden – die Werte aus der Server-Datei .env verwendet, sonst ist der Versand ausgeschaltet.', 'Entfernen', true))) return;
      try { await api('mail_konto_save', { body: { remove: true } }); toast('Postfach-Einstellungen entfernt.'); renderMailView(); } catch (ex) { $('#ml-err').textContent = ex.message; }
      return;
    }
    const err = a === 'test' ? $('#ml-err2') : $('#ml-err');
    err.textContent = '';
    b.disabled = true;
    try {
      if (a === 'sig') { const r = await api('mail_save', { body: { signature: $('#ml-sig').value } }); mailSt.signature = r.signature; toast('Signatur gespeichert.'); }
      if (a === 'test') { const to = $('#ml-to').value.trim(); await api('mail_test', { body: { to } }); toast(`Testmail an ${to} gesendet – bitte Posteingang (und Spam-Ordner) prüfen.`, 6000); await renderMailView(); $('#ml-to').value = to; }
    } catch (ex) { err.textContent = ex.message; } finally { b.disabled = false; }
  });

  /* Wochenangebot an Kunden versenden */
  const dlgRund = $('#dlg-rund');
  let rundSel = new Set(), rundBusy = false;
  const rundWhy = (c) => (!c.active ? 'Kunde inaktiv' : !c.email ? 'keine E-Mail-Adresse' : !c.login || !c.login.active ? 'kein aktiver Zugang' : !c.angebote.length ? 'kein Angebot freigeschaltet' : c.mailAngebot === false ? (c.abgemeldet ? 'hat sich vom Wochenangebot abgemeldet' : 'möchte kein Wochenangebot per E-Mail') : '');
  async function openRund() {
    try { const [m, k] = await Promise.all([api('mail_status'), api('kunden')]); mailSt = m; kunden = k.customers; kundenRev = k.rev; } catch (ex) { toast(ex.message); return; }
    if (!mailSt.configured) { toast('Bitte zuerst das Postfach für den E-Mail-Versand einrichten.', 5000); openMailCfg(); return; }
    const w = wkCur();
    const ok = kunden.filter((c) => !rundWhy(c)), no = kunden.filter((c) => rundWhy(c));
    rundSel = new Set(ok.filter((c) => c.login.hasPassword && !sentThisWeek(c)).map((c) => c.id));
    const pend = pendingCount();
    $('#rund-body').innerHTML = `<div class="dlg-head"><div><h2 id="rd-title">${w ? `Wochenangebot KW ${w.week}/${w.year} versenden` : 'Wochenangebot versenden'}</h2><p>${w ? `Angebotswoche ${esc(w.from)} – ${esc(w.to)}. Jeder Kunde erhält eine eigene E-Mail mit Links zu seinen freigeschalteten Angeboten (ohne Preise in der E-Mail).` : ''}</p></div><button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        ${!w ? '<div class="err-box">Es ist noch kein Angebot veröffentlicht.</div>' : ''}
        ${w && pend ? `<div class="notice k-pend">${icon('info', 'sm')}<span>Es gibt ${plural(pend, 'unveröffentlichte Änderung', 'unveröffentlichte Änderungen')} im Entwurf. Kunden sehen den <strong>veröffentlichten</strong> Stand – bei Bedarf zuerst veröffentlichen.</span></div>` : ''}
        ${ok.length ? `<div class="k-rlist"><label class="check k-rall"><input type="checkbox" id="rd-all"> Alle auswählen</label>
          <table class="etab ktab k-rtab"><tbody>${ok.map((c) => `<tr data-rid="${esc(c.id)}"><td class="k-rchk"><input type="checkbox" data-rsel="${esc(c.id)}"${rundSel.has(c.id) ? ' checked' : ''} aria-label="${esc(c.firma)} auswählen"></td>
            <td><div class="nm">${esc(c.firma)}</div><div class="sub">${esc(c.email)}</div></td><td class="k-offers">${c.angebote.map(offerChip).join(' ')}</td>
            <td class="k-rst">${sentThisWeek(c) ? `<span class="st-warn">KW ${w.week} bereits gesendet ${esc(dateTime(c.weekly.t))}</span>` : !c.login.hasPassword ? '<span class="st-warn">noch kein Passwort festgelegt</span>' : ''}<span class="k-res"></span></td></tr>`).join('')}</tbody></table></div>` : '<p class="hint">Keine Kunden mit E-Mail-Adresse, aktivem Zugang und freigeschaltetem Angebot.</p>'}
        ${no.length ? `<details class="k-no"><summary>${plural(no.length, 'Kunde', 'Kunden')} nicht berücksichtigt</summary><ul>${no.map((c) => `<li>${esc(c.firma)} – ${esc(rundWhy(c))}</li>`).join('')}</ul></details>` : ''}
        <label class="fld"><span>Zusatztext <small class="muted">(optional, erscheint in jeder E-Mail)</small></span><textarea id="rd-note" rows="3" maxlength="1000" placeholder="z. B. Diese Woche besonders günstig: Roastbeef aus Uruguay."></textarea></label>
        <div class="k-prevwrap" hidden><iframe id="rd-prev" sandbox="" title="Vorschau der E-Mail"></iframe></div>
        <p class="form-err" id="rd-err" role="alert"></p>
      </div>
      <div class="dlg-foot"><span class="left"><button type="button" class="btn sm ghost" data-rd="prev"${ok.length ? '' : ' disabled'}>${icon('eye', 'sm')}Vorschau</button></span><button type="button" class="btn" data-close>Schließen</button><button type="button" class="btn primary" data-rd="send"${w ? '' : ' disabled'}>${icon('send')}<span id="rd-n"></span></button></div>`;
    rundCount();
    dlgRund.showModal();
  }
  function rundCount() {
    const n = rundSel.size;
    $('#rd-n').textContent = n ? `An ${plural(n, 'Kunden', 'Kunden')} senden` : 'Kunden auswählen';
    $('#rund-body [data-rd="send"]').disabled = !n || rundBusy || !wkCur();
    const all = $('#rd-all'), boxes = $$('#rund-body [data-rsel]');
    if (all) { all.checked = boxes.length && boxes.every((b) => b.checked); all.indeterminate = !all.checked && boxes.some((b) => b.checked); }
  }
  dlgRund.addEventListener('cancel', (e) => { if (rundBusy) e.preventDefault(); });
  dlgRund.addEventListener('change', (e) => {
    if (e.target.id === 'rd-all') { for (const b of $$('#rund-body [data-rsel]')) { b.checked = e.target.checked; b.checked ? rundSel.add(b.dataset.rsel) : rundSel.delete(b.dataset.rsel); } }
    if (e.target.dataset.rsel) e.target.checked ? rundSel.add(e.target.dataset.rsel) : rundSel.delete(e.target.dataset.rsel);
    rundCount();
  });
  dlgRund.addEventListener('click', async (e) => {
    const a = e.target.closest('[data-rd]')?.dataset.rd;
    if (a === 'prev') {
      const id = [...rundSel][0] || ($('#rund-body [data-rsel]') || {}).dataset?.rsel || '';
      try {
        const r = await api('kunden_mail_vorschau', { body: { id, type: 'woche', note: $('#rd-note').value } });
        $('#rund-body .k-prevwrap').hidden = false;
        $('#rd-prev').srcdoc = r.html;
        $('#rd-prev').title = `Vorschau: ${r.subject} (an ${r.to})`;
      } catch (ex) { $('#rd-err').textContent = ex.message; }
    }
    if (a === 'send') {
      const w = wkCur(), ids = [...rundSel];
      const again = ids.filter((id) => sentThisWeek(kunden.find((c) => c.id === id))).length;
      if (!(await confirmBox('Wochenangebot versenden?', `Das Wochenangebot KW ${w.week}/${w.year} geht jetzt per E-Mail an ${plural(ids.length, 'Kunden', 'Kunden')}.${again ? ` <strong>${again} davon haben es diese Woche schon erhalten.</strong>` : ''}`, 'Jetzt senden'))) return;
      rundBusy = true; dlgRund.dataset.busy = '1'; rundCount();
      const note = $('#rd-note').value;
      let okN = 0, badN = 0;
      $('#rd-err').textContent = '';
      for (let i = 0; i < ids.length; i += 10) {
        const part = ids.slice(i, i + 10);
        for (const id of part) $(`#rund-body tr[data-rid="${CSS.escape(id)}"] .k-res`).innerHTML = '<span class="spinner sm"></span>';
        $('#rd-n').textContent = `Wird gesendet … ${i}/${ids.length}`;
        try {
          const r = await api('kunden_rundmail', { body: { ids: part, note, week: w.week, year: w.year } });
          for (const x of r.results) {
            const cell = $(`#rund-body tr[data-rid="${CSS.escape(x.id)}"] .k-res`);
            if (x.ok) { okN++; rundSel.delete(x.id); const cb = $(`#rund-body [data-rsel="${CSS.escape(x.id)}"]`); if (cb) cb.checked = false; }
            else badN++;
            if (cell) cell.innerHTML = x.ok ? `<span class="st-ok">${icon('check', 'sm')}gesendet</span>` : `<span class="st-err">${esc(x.error)}</span>`;
          }
        } catch (ex) {
          badN += part.length;
          for (const id of part) $(`#rund-body tr[data-rid="${CSS.escape(id)}"] .k-res`).innerHTML = `<span class="st-err">${esc(ex.message)}</span>`;
          if (ex.status === 409 || ex.status === 401 || ex.status === 403) { $('#rd-err').textContent = ex.message; break; }
        }
      }
      rundBusy = false; delete dlgRund.dataset.busy;
      rundCount();
      toast(badN ? `${okN} gesendet, ${badN} nicht zugestellt – Details in der Liste.` : `Wochenangebot an ${plural(okN, 'Kunden', 'Kunden')} gesendet.`, 6000);
      try { const r = await api('kunden'); kunden = r.customers; kundenRev = r.rev; renderKundenList(); } catch { /* Liste später */ }
    }
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
    ['kunden', 'Kunden (Stammdaten, Anmeldungen, E-Mails, Bestellwünsche)'],
    ['security', 'Sicherheit'],
  ];
  const typeOf = (a) => ({ draft: 'offer', import: 'offer', discard: 'offer', offers: 'offer', publish: 'publish', history: 'history', stock: 'stock', master: 'master', login: 'auth', logout: 'auth', login_fail: 'auth', password: 'auth', setup: 'user', user: 'user', security: 'security', wartung: 'security', twofa: 'auth', reauth: 'auth', reauth_fail: 'auth', customers: 'kunden', kunde_login: 'kunden', kunde_login_fail: 'kunden', kunde_password: 'kunden', mail: 'kunden', kunde_abmeldung: 'kunden', bestellung: 'kunden' }[a] || '');
  const ACTION_LABEL = { wartung: 'Wartungsmodus', bestellung: 'Bestellwunsch', kunde_abmeldung: 'Abmeldung Wochenangebot', mail: 'E-Mail', customers: 'Kunden', kunde_login: 'Kunden-Anmeldung', kunde_login_fail: 'Kunden-Anmeldung fehlgeschlagen', kunde_password: 'Kunden-Passwort', offers: 'Angebote', draft: 'Entwurf bearbeitet', import: 'Entwurf ersetzt', discard: 'Entwurf verworfen', publish: 'Veröffentlicht', history: 'Preisverlauf', stock: 'Bestand', master: 'Stammdaten', login: 'Anmeldung', logout: 'Abmeldung', login_fail: 'Anmeldung fehlgeschlagen', password: 'Passwort', setup: 'Einrichtung', user: 'Nutzerverwaltung', security: 'Sicherheit', twofa: 'Zwei-Faktor', reauth: 'Verwaltungsaktion bestätigt', reauth_fail: 'Passwortbestätigung fehlgeschlagen' };
  function draftSummary(d) {
    let p = 0, n = 0, r = 0, o = 0;
    for (const c of d || []) { const f = c.k.split('|')[1]; if (f === 'price' || String(f).startsWith('v:')) p++; else if (f === '+') n++; else if (f === '-') r++; else o++; }
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
      const cls = f === 'price' || String(f).startsWith('v:') ? 'ch-price' : f === '+' ? 'ch-new' : f === '-' ? 'ch-del' : '';
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
    const ds = b.datensaetze ? `${fmtInt.format(b.datensaetze)} Datensätze${b.speicher === 'sqlite' ? ' (Datenbank)' : ''} · ` : '';
    return card('ok', 'Datensicherung', `${esc(when)} · geprüft`, `${ds}${b.anzahl} Stände auf dem Server (${(b.groesse / 1024 / 1024).toFixed(1).replace('.', ',')} MB je Stand)`);
  }
  const mb = (n) => (n / 1024 / 1024).toFixed(1).replace('.', ',');
  const gb = (n) => (n / 1024 / 1024 / 1024).toFixed(1).replace('.', ',');
  function wartungCard(w, card) {
    return w ? card('warn', 'Wartungsmodus', 'aktiv – Kunden sehen einen Wartungshinweis', `seit ${esc(dateTime(w.since))} Uhr${esc(wartungBis(w))}`)
      : card('ok', 'Wartungsmodus', 'aus – Angebotsseite normal erreichbar', '');
  }
  function storageCard(d, card) {
    const st = d.storage || {};
    return card('ok', 'Datenablage', st.mode === 'sqlite' ? `SQLite-Datenbank · ${fmtInt.format(st.documents || 0)} Datensätze` : `Dateien · ${fmtInt.format(st.documents || 0)} Datensätze`,
      `${mb(st.bytes || 0)} MB${d.php ? ` · PHP ${esc(d.php)}` : ''}`);
  }
  function diskCard(k, card) {
    if (!k || !k.free || !k.total) return card('warn', 'Speicherplatz', 'unbekannt', '');
    const lvl = k.free < 1024 ** 3 ? 'bad' : k.free < 5 * 1024 ** 3 ? 'warn' : 'ok';
    return card(lvl, 'Speicherplatz', `${gb(k.free)} GB frei von ${gb(k.total)} GB`, lvl === 'ok' ? '' : 'Bald aufräumen oder Speicher erweitern');
  }
  function mailCard(m, card) {
    if (!m || !m.configured) return card('warn', 'E-Mail-Versand', 'nicht eingerichtet', 'Verwaltung → E-Mail');
    return card(m.failed7 ? 'warn' : 'ok', 'E-Mail-Versand', `${fmtInt.format(m.sent7)} zugestellt in 7 Tagen`, m.failed7 ? `${fmtInt.format(m.failed7)} nicht zugestellt – Versandliste unter E-Mail prüfen` : '');
  }
  function ordersCard(o, card) {
    if (!o) return '';
    if (!o.enabled) return card('warn', 'Bestellwünsche', 'Bestellfunktion aus', 'Verwaltung → E-Mail → Bestellwünsche');
    return card(o.failed7 ? 'warn' : 'ok', 'Bestellwünsche', `${fmtInt.format(o.n7)} in den letzten 7 Tagen`, o.failed7 ? `${o.failed7} nicht per E-Mail zugestellt` : o.last ? `zuletzt ${esc(o.lastNr || '')} am ${esc(dateTime(o.last))} Uhr` : 'noch keine');
  }
  function customersCard(c, card) {
    if (!c) return '';
    return card('ok', 'Kunden', `${fmtInt.format(c.active)} aktiv · ${fmtInt.format(c.withLogin)} mit Zugang`, c.online ? `${fmtInt.format(c.online)} gerade angemeldet` : 'niemand angemeldet');
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
      wartungCard(d.wartung, card),
      backupCard(d.backup, card),
      deployCard(d.deployment, card),
      storageCard(d, card),
      diskCard(d.disk, card),
      mailCard(d.mail, card),
      ordersCard(d.orders, card),
      customersCard(d.customers, card),
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
      <form class="gcard sec-form wartung-form${d.wartung ? ' on' : ''}" id="wartung-form" autocomplete="off">
        <h3 class="sec-h">Wartungsmodus</h3>
        <p class="hint" style="margin-top:0">Pausiert die Angebotsseite für Kunden (Angebot, Anmeldung, Merkliste, Bestellwünsche). Sie und alle Mitarbeiter arbeiten im Eingabebereich und auf der Angebotsseite normal weiter; Abmeldelinks aus E-Mails funktionieren weiterhin.</p>
        <div class="sec-rows">
          <label class="fld span2"><span>Hinweis für Kunden</span><textarea name="message" rows="2" maxlength="500" placeholder="Wir aktualisieren gerade unser Angebotsportal. In Kürze sind wir wieder für Sie da.">${esc(d.wartung ? d.wartung.message : '')}</textarea></label>
          <label class="fld"><span>Voraussichtlich bis <small>(optional)</small></span><input type="datetime-local" name="until" value="${esc(d.wartung && d.wartung.until ? d.wartung.until : '')}"></label>
        </div>
        <div class="sec-foot wartung-foot">${d.wartung ? `<span class="st-warn">Aktiv seit ${esc(dateTime(d.wartung.since))} Uhr</span><button type="button" class="btn" data-wartung="save">Hinweis speichern</button><button type="button" class="btn primary" data-wartung="off">Wartungsmodus beenden</button>`
          : '<button type="button" class="btn primary" data-wartung="on">Wartungsmodus einschalten</button>'}</div>
        <p class="form-err" id="wartung-err" role="alert"></p>
      </form>
      <p class="hint">Sensible Verwaltungsaktionen benötigen eine höchstens fünf Minuten alte Anmeldung oder Passwortbestätigung. Die Bestätigung gilt nur für diese Sitzung. Nach fünf falschen Passwortbestätigungen sind weitere Bestätigungen und sensible Verwaltungsaktionen für zehn Minuten gesperrt.</p>
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
    const wb = e.target.closest('#wartung-form [data-wartung]');
    if (wb) {
      const f = $('#wartung-form'), a = wb.dataset.wartung, err = $('#wartung-err');
      err.textContent = '';
      if (a === 'on' && !(await confirmBox('Wartungsmodus einschalten?', 'Kunden sehen auf der Angebotsseite dann nur noch den Wartungshinweis und können sich nicht anmelden oder bestellen, bis Sie den Wartungsmodus wieder beenden.', 'Einschalten'))) return;
      wb.disabled = true;
      try {
        const r = await api('wartung_save', { body: { active: a !== 'off', message: f.message.value, until: f.until.value } });
        wartungSt = r.wartung; renderWartungBanner();
        toast(a === 'on' ? 'Wartungsmodus eingeschaltet.' : a === 'off' ? 'Wartungsmodus beendet – die Angebotsseite ist wieder erreichbar.' : 'Hinweis gespeichert.', 4500);
        renderSecView();
      } catch (ex) { err.textContent = ex.message; wb.disabled = false; }
      return;
    }
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
