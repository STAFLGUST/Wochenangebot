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
    if (res.status === 401 && !['login', 'login_2fa', 'setup', 'change_password', 'passkey_login_begin', 'passkey_login'].includes(action)) {
      showAuth('expired');
      throw Object.assign(new Error('Sitzung abgelaufen – bitte erneut anmelden.'), { status: 401 });
    }
    if (res.status === 503 && data?.wartung && data.bereich) {
      showEingabeWartung(data);
      throw Object.assign(new Error(data.error || 'Wartungsarbeiten.'), { status: 503, wartung: true });
    }
    // Zentrale Anmeldung (Keycloak-Host): Bestätigung durch erneute Anmeldung bei Keycloak, danach zurück auf diese Seite
    if (res.status === 403 && data?.code === 'reauth_required' && typeof data.anmelden === 'string' && data.anmelden.startsWith('/oidc/')) {
      try { if (unsaved()) await saveNow(); } catch { /* Entwurf bleibt lokal erhalten */ }
      location.assign(data.anmelden + encodeURIComponent(location.href));
      throw Object.assign(new Error(data.error || 'Bitte erneut anmelden.'), { status: 403 });
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
  /* Bereiche und das Recht, das sie sichtbar macht (ohne Eintrag: alle; ADMIN_VIEWS: nur Administratoren) */
  const VIEW_PERM = { einzel: 'einzelangebote.sehen', hist: 'preisverlauf.sehen', stock: 'bestand.sehen', einkauf: 'einkauf.sehen', master: 'stammdaten.sehen', orders: 'bestellungen.sehen', kunden: 'kunden.sehen', gruppen: 'stammdaten.sehen', vkgruppen: 'stammdaten.sehen', angebote: 'angebote.verwalten', vertreter: 'stammdaten.sehen', auswertung: 'auswertung.sehen', log: 'protokoll.sehen', mail: '', users: '', sec: '', schutz: '', importe: '' };
  /* Verwaltung unter eigener Adresse (verwaltung.dashboard-stafl.de): nur ihre Bereiche – Anzeige, die Rechte prüft der Server */
  /* Angebot unter der zentralen Anmeldung (angebot.dashboard-stafl.de): Angebotsbereiche ohne Verwaltung. Ohne Bereich
     (bisheriger Zugang angebot-stafl.de/admin/) bleibt alles sichtbar. */
  const BEREICH_VIEWS = {
    'verwaltung.verwaltung': ['master', 'vkgruppen', 'kunden', 'gruppen', 'vertreter', 'importe', 'auswertung', 'mail', 'users', 'log', 'sec', 'schutz'],
    'angebot.eingabe': ['orders', 'edit', 'einzel', 'hist', 'stock', 'einkauf', 'angebote'],
  };
  function viewAllowed(v) {
    const nur = BEREICH_VIEWS[me && me.bereich];
    if (nur && !nur.includes(v)) return false;
    if (['mail', 'users', 'sec', 'schutz'].includes(v)) return can('admin');
    if (v === 'gruppen' || v === 'vertreter') return may('stammdaten.sehen') || may('kunden.sehen');
    if (v === 'importe') return !!(window.WA && window.WA.importSichtbar && window.WA.importSichtbar());   // Importzentrale (admin-import.js)
    return !VIEW_PERM[v] || may(VIEW_PERM[v]);
  }
  /* Einzelrecht (Administrator: alle) – die verbindliche Prüfung macht der Server */
  const may = (p) => !!me && (me.role === 'admin' || (me.perms || []).includes(p));
  let ro = true;                                   // Nur-Ansicht (Entwurf bearbeiten)
  let roHist = true, roStock = true, roMaster = true; // Nur-Ansicht je Bereich
  let authMode = 'login';
  let loginPw = '';                                // nur für den Pflicht-Passwortwechsel direkt nach der Anmeldung
  let authCtx = null;                              // { prevUser, expired } während einer laufenden Anmeldung
  let authMethods = [];                            // zweiter Schritt: 'totp' und/oder 'passkey'
  function showAuth(mode) {
    authMode = mode;
    $('#screen-auth').hidden = false;
    if (mode !== 'expired' && !(authCtx && authCtx.expired)) $('#screen-editor').hidden = true;
    const setup = mode === 'setup', newpw = mode === 'newpw', code = mode === 'code', tf = mode === 'twofa', pk = mode === 'passkey';
    $('#auth-intro').textContent = setup
      ? 'Ersteinrichtung: Legen Sie den ersten Administrator-Zugang an (Passwort mindestens 10 Zeichen). Weitere Nutzer legen Sie danach unter „Nutzer“ an.'
      : newpw ? (me && me.mustChangeGrund === 'datenleck' ? `Hallo ${me.name}, Ihr bisheriges Passwort ist in bekannten Datenlecks aufgetaucht und gilt deshalb als unsicher. Bitte legen Sie jetzt ein neues Passwort fest.` : `Hallo ${me ? me.name : ''}, bitte legen Sie jetzt ein eigenes Passwort fest.`)
        : code ? 'Bitte den 6-stelligen Code aus Ihrer Authenticator-App eingeben – oder einen Ihrer Wiederherstellungscodes.'
          : pk ? 'Bitte bestätigen Sie die Anmeldung mit Ihrem Passkey – per Fingerabdruck, Gesicht oder PIN Ihres Geräts.'
          : tf ? `Hallo ${me ? me.name : ''}, für Ihren Zugang ist die Zwei-Faktor-Anmeldung vorgeschrieben. Bitte richten Sie sie jetzt ein.`
            : mode === 'expired' ? 'Ihre Sitzung ist abgelaufen. Bitte erneut anmelden – Ihre Änderungen bleiben erhalten.'
              : 'Bitte melden Sie sich mit Ihrem Benutzernamen an.';
    const hideUser = newpw || code || tf || pk;
    $('#au-user-wrap').hidden = hideUser;
    $('#au-user').required = !hideUser;
    $('#au-name-wrap').hidden = !setup;
    $('#pw1').closest('label').hidden = code || tf || pk;
    $('#pw1').required = !(code || tf || pk);
    $('#pw2-wrap').hidden = !(setup || newpw);
    $('#au-code-wrap').hidden = !code;
    $('#au-code').required = code;
    $('#auth-twofa').hidden = !tf;
    $('#auth-submit').hidden = tf;
    $('#pw1-lbl').textContent = newpw ? 'Neues Passwort' : 'Passwort';
    $('#pw1').autocomplete = setup || newpw ? 'new-password' : 'current-password';
    $('#auth-submit').textContent = setup ? 'Zugang anlegen' : newpw ? 'Passwort speichern' : code ? 'Bestätigen' : pk ? 'Mit Passkey bestätigen' : 'Anmelden';
    // Passkey: Anmeldung ohne Benutzername, statt des Codes oder statt der Authenticator-App einrichten
    $('#auth-passkey').hidden = !(PK_OK && (mode === 'login' || mode === 'expired' || tf || (code && authMethods.includes('passkey'))));
    $('#auth-passkey span').textContent = code ? 'Stattdessen Passkey verwenden' : tf ? 'Stattdessen Passkey einrichten' : 'Mit Passkey anmelden';
    $('#auth-err').textContent = '';
    $('#pw1').value = ''; $('#pw2').value = ''; $('#au-code').value = '';
    if (mode === 'expired' && me) $('#au-user').value = me.username;
    $('#screen-auth').classList.toggle('overlay', mode === 'expired' || !!(authCtx && authCtx.expired));
    if (tf) {
      // Einrichtung braucht das aktuelle Passwort (direkt nach der Anmeldung bekannt, nach dem Neuladen erneut abfragen)
      if (loginPw) renderTwofaSetup($('#auth-twofa'), () => finishLogin(), loginPw);
      else {
        $('#auth-twofa').innerHTML = `<div class="fld"><span>Aktuelles Passwort</span><input type="password" id="tf-pw-login" autocomplete="current-password"></div>
          <button type="button" class="btn primary wide" id="tf-pw-weiter">Weiter</button>`;
        const weiter = () => { const v = $('#tf-pw-login').value; if (!v) return; loginPw = v; renderTwofaSetup($('#auth-twofa'), () => finishLogin(), v); };
        $('#tf-pw-weiter').addEventListener('click', weiter);
        $('#tf-pw-login').addEventListener('keydown', (e) => { if (e.key === 'Enter') { e.preventDefault(); weiter(); } });
      }
    }
    setTimeout(() => (code ? $('#au-code') : pk ? $('#auth-submit') : (newpw || $('#au-user').value) ? $('#pw1') : $('#au-user')).focus(), 30);
  }
  async function afterLogin(r, pw) {
    csrf = r.csrf;
    me = r.user;
    if (r.recoveryLeft != null) toast(`Mit Wiederherstellungscode angemeldet – noch ${r.recoveryLeft} Codes übrig. Bei Bedarf unter „Zwei-Faktor-Anmeldung“ neu einrichten.`, 8000);
    if (me.mustChange) { loginPw = pw; showAuth('newpw'); return; }
    if (me.needTwofa) { loginPw = pw; showAuth('twofa'); return; }   // nur bis zur Einrichtung des zweiten Faktors
    loginPw = '';   // nach erfolgreicher Anmeldung nicht im Speicher behalten
    await finishLogin();
  }
  async function finishLogin() {
    loginPw = '';
    const ctx = authCtx || {};
    authCtx = null;
    $('#screen-auth').classList.remove('overlay');
    if (ctx.expired && model && ctx.prevUser === me.id) { $('#screen-auth').hidden = true; $('#screen-editor').hidden = false; applyRole(); if (!ro) saveNow(); }
    else if (ctx.prevUser && ctx.prevUser !== me.id) location.replace(location.pathname);   // anderer Nutzer: ohne Daten des vorigen neu starten
    else await openEditor();
  }
  $('#auth-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (authMode === 'twofa') { $('#auth-twofa [data-tf="enable"]')?.click(); return; }
    if (authMode === 'passkey') { passkeyLogin(true); return; }
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
      if (r.need2fa) {
        loginPw = pw; authMethods = r.methods || ['totp']; showAuth(authMethods.includes('totp') ? 'code' : 'passkey');
        // Zugang gesperrt (z. B. nach fremden Fehlversuchen): mit Authenticator-App oder Passkey geht es trotzdem weiter
        if (r.gesperrtBis) $('#auth-intro').textContent = `Dieser Zugang ist wegen zu vieler Fehlversuche bis ${r.gesperrtBis} Uhr gesperrt. Mit dem Code aus Ihrer Authenticator-App (oder einem Wiederherstellungscode) können Sie sich trotzdem anmelden – mit Passkey über „Mit Passkey anmelden“ auf der Anmeldeseite. Sonst: bitte bis dahin warten oder einen Administrator bitten, den Zugang zu entsperren.`;
        return;
      }
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
    try { r = await api('twofa_begin', { body: { password } }); } catch (ex) {
      if (ex.status === 422 && host.id === 'auth-twofa') { loginPw = ''; showAuth('twofa'); $('#auth-err').textContent = ex.message; return; }   // falsches Passwort: erneut fragen
      host.innerHTML = `<div class="err-box">${esc(ex.message)}</div>`; return;
    }
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
      $('#twofa-body').innerHTML = `${head}<div class="dlg-body" id="tf-host"><form id="tf-start"><label class="fld"><span>Aktuelles Passwort eingeben</span><input type="password" id="tf-pw0" autocomplete="current-password" required></label>
        <button type="submit" class="btn primary">Weiter</button></form></div>`;
      d.showModal();
      $('#tf-start').addEventListener('submit', (e) => { e.preventDefault(); renderTwofaSetup($('#tf-host'), done, $('#tf-pw0').value); });
      setTimeout(() => $('#tf-pw0').focus(), 30);
      return;
    }
    $('#twofa-body').innerHTML = `${head}<div class="dlg-body" id="tf-host">
        <p class="tf-ok">${icon('check')} Eingeschaltet für <strong>${esc(me.username)}</strong>.</p>
        ${me.twofaRequired ? `<p class="hint">Für Ihren Zugang ist die Zwei-Faktor-Anmeldung vorgeschrieben${me.passkeys ? ' – Ihre Passkeys erfüllen sie auch ohne Authenticator-App' : ''}.</p>` : ''}
        <div class="row-actions" style="justify-content:flex-start">
          <button type="button" class="btn" data-tfd="renew">Neu einrichten (neues Handy / neue Codes)</button>
          ${me.twofaRequired && !me.passkeys ? '' : '<button type="button" class="btn" data-tfd="off" style="color:var(--accent)">Ausschalten</button>'}
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

  /* ======================= Passkeys (WebAuthn) ======================= */
  const PK_OK = !!(window.PublicKeyCredential && navigator.credentials && navigator.credentials.create);
  const b64u = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf))).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const unb64u = (t) => Uint8Array.from(atob(t.replace(/-/g, '+').replace(/_/g, '/') + '==='.slice((t.length + 3) % 4)), (c) => c.charCodeAt(0));
  const pkIds = (l) => (l || []).map((c) => ({ ...c, id: unb64u(c.id) }));
  function pkError(ex) {
    if (ex && (ex.name === 'NotAllowedError' || ex.name === 'AbortError')) return 'Abgebrochen.';
    if (ex && ex.name === 'InvalidStateError') return 'Dieser Passkey ist auf diesem Gerät bereits eingerichtet.';
    if (ex && ex.name === 'SecurityError') return 'Passkeys sind unter dieser Adresse nicht möglich.';
    if (ex && ex.status !== undefined) return ex.message;
    return 'Der Passkey konnte nicht verwendet werden.';
  }
  /* Neuen Passkey einrichten (immer mit aktuellem Passwort) */
  async function passkeyRegister(password, name) {
    const o = (await api('passkey_begin', { body: { password } })).options;
    const cred = await navigator.credentials.create({ publicKey: { ...o, challenge: unb64u(o.challenge), user: { ...o.user, id: unb64u(o.user.id) }, excludeCredentials: pkIds(o.excludeCredentials) } });
    const r = cred.response;
    const res = await api('passkey_register', { body: { id: cred.id, clientDataJSON: b64u(r.clientDataJSON), attestationObject: b64u(r.attestationObject), transports: r.getTransports ? r.getTransports() : [], name } });
    me = res.user;
    return res;
  }
  /* Anmelden mit Passkey: ohne Benutzername oder (second) als zweiter Schritt nach dem Passwort */
  async function passkeyLogin(second) {
    const err = $('#auth-err'), btns = [$('#auth-submit'), $('#auth-passkey')];
    err.textContent = '';
    if (!PK_OK) { err.textContent = 'Dieser Browser unterstützt keine Passkeys.'; return; }
    btns.forEach((b) => { b.disabled = true; });
    try {
      if (!second) authCtx = { prevUser: me && me.id, expired: authMode === 'expired' };
      const o = (await api('passkey_login_begin', { body: { second } })).options;
      const cred = await navigator.credentials.get({ publicKey: { ...o, challenge: unb64u(o.challenge), allowCredentials: pkIds(o.allowCredentials) } });
      const r = cred.response;
      const res = await api('passkey_login', { body: { id: cred.id, clientDataJSON: b64u(r.clientDataJSON), authenticatorData: b64u(r.authenticatorData), signature: b64u(r.signature), userHandle: r.userHandle ? b64u(r.userHandle) : null } });
      await afterLogin(res, '');
    } catch (ex) {
      err.textContent = pkError(ex);
      if (second && /Anmeldung ist abgelaufen|erneut anmelden/i.test(ex.message || '')) setTimeout(() => showAuth(authCtx && authCtx.expired ? 'expired' : 'login'), 1800);
    } finally {
      btns.forEach((b) => { b.disabled = false; });
    }
  }
  $('#auth-passkey').addEventListener('click', async () => {
    if (authMode !== 'twofa') { passkeyLogin(authMode === 'code'); return; }
    const err = $('#auth-err'), b = $('#auth-passkey');
    err.textContent = ''; b.disabled = true;
    if (!loginPw) { err.textContent = 'Bitte zuerst oben das aktuelle Passwort eingeben und „Weiter“ wählen.'; b.disabled = false; return; }
    try { await passkeyRegister(loginPw, ''); toast('Passkey eingerichtet.'); await finishLogin(); } catch (ex) { err.textContent = pkError(ex); } finally { b.disabled = false; }
  });
  /* Menü: eigene Passkeys verwalten */
  let pkList = [], pkMax = 10, pkDel = null;
  const pkHead = `<div class="dlg-head"><div><h2 id="pk-title">Passkeys</h2><p>Anmelden ohne Passwort – mit Fingerabdruck, Gesichtserkennung oder der PIN Ihres Geräts. Ein Passkey gilt auch als zweiter Faktor.</p></div><button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>`;
  async function openPasskeyDialog() {
    $('#passkeys-body').innerHTML = `${pkHead}<div class="dlg-body"><div class="loading"><div class="spinner"></div>Wird geladen …</div></div>`;
    $('#dlg-passkeys').showModal();
    try { const r = await api('passkey_list'); pkList = r.passkeys; pkMax = r.max; pkDel = null; renderPasskeys(); }
    catch (ex) { $('#passkeys-body .dlg-body').innerHTML = `<div class="err-box">${esc(ex.message)}</div>`; }
  }
  function renderPasskeys() {
    const del = pkDel && pkList.find((p) => p.ref === pkDel);
    const full = pkList.length >= pkMax;
    const rows = pkList.map((p) => `<li class="pk-item${p.ref === pkDel ? ' sel' : ''}">
        <div class="pk-main"><input class="pk-name" data-pkname="${esc(p.ref)}" value="${esc(p.name)}" maxlength="60" aria-label="Name des Passkeys">
          <span class="sub">Hinzugefügt ${esc(dateTime(p.created))} · ${p.lastUsed ? 'zuletzt verwendet ' + esc(dateTime(p.lastUsed)) : 'noch nicht verwendet'}</span></div>
        <button type="button" class="btn sm ghost pk-del" data-pkdel="${esc(p.ref)}" aria-label="Passkey „${esc(p.name)}“ entfernen">${icon('trash', 'sm')}<span>Entfernen</span></button></li>`).join('');
    const addOff = !del && (full || !PK_OK);
    $('#passkeys-body').innerHTML = `${pkHead}<div class="dlg-body">
        ${pkList.length ? `<ul class="pk-list">${rows}</ul>` : '<p class="hint" style="margin:0">Noch kein Passkey eingerichtet.</p>'}
        <form class="pk-form" id="pk-form">
          <h3 class="pk-h">${del ? `Passkey „${esc(del.name)}“ entfernen` : 'Passkey hinzufügen'}</h3>
          ${del ? '' : !PK_OK ? '<p class="hint" style="margin:0">Dieser Browser unterstützt keine Passkeys.</p>' : full ? `<p class="hint" style="margin:0">Es sind höchstens ${pkMax} Passkeys möglich. Bitte zuerst einen entfernen.</p>`
            : '<label class="fld"><span>Name <small class="muted">(optional)</small></span><input name="name" maxlength="60" placeholder="z. B. Laptop Büro" autocomplete="off"></label>'}
          ${addOff ? '' : '<label class="fld"><span>Aktuelles Passwort</span><input name="password" type="password" autocomplete="current-password" required></label>'}
          <p class="form-err" id="pk-err" role="alert"></p>
          ${addOff ? '' : `<div class="pk-actions">${del ? '<button type="button" class="btn" data-pkcancel>Abbrechen</button>' : ''}<button type="submit" class="btn primary" id="pk-submit">${del ? 'Entfernen' : 'Passkey hinzufügen'}</button></div>`}
        </form></div>`;
  }
  $('#dlg-passkeys').addEventListener('click', (e) => {
    const d = e.target.closest('[data-pkdel]');
    if (d) { pkDel = d.dataset.pkdel; renderPasskeys(); $('#pk-form [name="password"]').focus(); return; }
    if (e.target.closest('[data-pkcancel]')) { pkDel = null; renderPasskeys(); }
  });
  $('#dlg-passkeys').addEventListener('change', async (e) => {
    const ref = e.target.dataset.pkname;
    if (!ref) return;
    const name = e.target.value.trim();
    const old = pkList.find((p) => p.ref === ref);
    if (!name) { e.target.value = old ? old.name : ''; return; }
    try { pkList = (await api('passkey_rename', { body: { ref, name } })).passkeys; toast('Name gespeichert.'); }
    catch (ex) { $('#pk-err').textContent = ex.message; }
  });
  $('#dlg-passkeys').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.dataset.pkname) { e.preventDefault(); e.target.blur(); } });
  $('#dlg-passkeys').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target, err = $('#pk-err'), btn = $('#pk-submit'), d = $('#dlg-passkeys');
    const pwIn = $('[name="password"]', f), nameIn = $('[name="name"]', f);
    const password = pwIn ? pwIn.value : '';
    err.textContent = ''; btn.disabled = true; d.dataset.busy = '1';
    try {
      if (pkDel) {
        const name = (pkList.find((p) => p.ref === pkDel) || {}).name || '';
        const r = await api('passkey_delete', { body: { ref: pkDel, password } });
        me = r.user; pkList = r.passkeys; pkDel = null;
        toast(`Passkey „${name}“ entfernt.`);
      } else {
        const r = await passkeyRegister(password, nameIn ? nameIn.value.trim() : '');
        pkList = r.passkeys;
        toast('Passkey hinzugefügt.');
      }
      renderPasskeys();
    } catch (ex) {
      err.textContent = pkError(ex);
      btn.disabled = false;
      if (pwIn) { pwIn.value = ''; pwIn.focus(); }
    } finally { delete d.dataset.busy; }
  });

  /* Rolle auf die Oberfläche anwenden */
  function applyRole() {
    ro = !may('angebot.bearbeiten');
    roHist = !may('preisverlauf.bearbeiten'); roStock = !may('bestand.importieren'); roMaster = !may('stammdaten.bearbeiten');
    document.body.classList.toggle('ro', ro);
    document.body.classList.toggle('ro-hist', roHist);   // Preisverlauf hochladen/löschen hängt am eigenen Recht, nicht am Entwurfsrecht
    document.body.classList.toggle('is-admin', can('admin'));
    for (const v of VIEWS) $('#vt-' + v).hidden = !viewAllowed(v);
    const verw = !!(me && me.bereich === 'verwaltung.verwaltung');
    document.body.classList.toggle('bereich-verwaltung', verw);
    $('#topbar h1').textContent = verw ? 'Verwaltung' : 'Eingabebereich';
    document.title = verw ? 'Verwaltung · STAFL' : 'Wochenangebot · Eingabebereich';
    $('#btn-send').hidden = !may('wochenangebot.senden');
    $('#btn-publish').hidden = !may('angebot.veroeffentlichen');
    if (!may('wochenangebot.senden')) $('#send-hint').hidden = true;
    $('#side-admin').hidden = !['importe', 'auswertung', 'mail', 'users', 'log', 'sec', 'schutz'].some(viewAllowed);
    $('#side-stamm').hidden = !['master', 'vkgruppen', 'angebote', 'kunden', 'gruppen', 'vertreter'].some(viewAllowed);
    $('#menu-user').innerHTML = me ? `<strong>${esc(me.name)}</strong><span>${esc(me.username)} · ${esc(ROLE_LABEL[me.role])}</span>` : '';
    if (!viewAllowed(currentView)) setView(VIEWS.find(viewAllowed) || 'edit');
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
  /* Wartung des Eingabebereichs: Mitarbeiter ohne Administratorrechte sehen nur den Wartungshinweis (der Server weist
     ihre Aktionen mit 503 ab, lib/module.php); Administratoren arbeiten weiter und sehen einen Hinweis. */
  let wartungEingabe = null;
  function showEingabeWartung(w) {
    $('#ew-text').textContent = w.error || w.message || 'Der Eingabebereich wird gerade gewartet. Bitte versuchen Sie es später erneut.';
    const bis = w.until ? new Date(w.until).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '';
    $('#ew-bis').hidden = !bis; $('#ew-bis').textContent = bis ? `Voraussichtlich wieder verfügbar ab ${bis} Uhr.` : '';
    $('#screen-editor').hidden = true; $('#screen-auth').hidden = true; $('#screen-wartung').hidden = false;
  }
  document.addEventListener('click', async (e) => {
    if (e.target.closest('#ew-retry')) location.reload();
    if (e.target.closest('#ew-logout')) { try { await api('logout', { body: {} }); } catch { /* ignore */ } location.reload(); }
  });

  /* Wartungsmodus: Hinweis für alle Mitarbeiter oben im Eingabebereich */
  let wartungSt = null;
  const wartungBis = (w) => (w && w.until ? ` · voraussichtlich bis ${new Date(w.until).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' })} Uhr` : '');
  function renderWartungBanner() {
    const b = $('#adm-wartung');
    if (!b) return;
    const ew = wartungEingabe && !wartungEingabe.geplant;
    b.hidden = !wartungSt && !ew;
    const teile = [];
    if (ew) teile.push(`<strong>Eingabebereich in Wartung</strong> – nur Administratoren können gerade arbeiten${esc(wartungBis(wartungEingabe))}.`);
    if (wartungSt) teile.push(`<strong>Wartungsmodus aktiv</strong> – Kunden sehen auf der Angebotsseite nur einen Wartungshinweis${esc(wartungBis(wartungSt))}.`);
    if (!b.hidden) b.innerHTML = `${icon('info', 'sm')}<span>${teile.join('<br>')}</span>${can('admin') ? '<button type="button" class="btn sm" data-wartung="goto">Verwalten</button>' : ''}`;
  }
  async function refreshWartung() {
    try {
      const st = await api('status');
      wartungSt = st.wartung || null; wartungEingabe = st.wartungEingabe || null;
      if (st.eingabeGesperrt) showEingabeWartung({ error: (st.wartungEingabe && st.wartungEingabe.message) || '', until: st.wartungEingabe && st.wartungEingabe.until });
    } catch { /* Hinweis später */ }
    renderWartungBanner();
  }
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
    if (currentView === 'edit' && !ro) importFile(f);
    else if (currentView === 'stock' && !roStock) stockImportFile(f);
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
      <span class="ob-act">${may('sonderposten.senden') ? `<button type="button" class="btn sm ghost" data-ob="restposten" title="Sonderposten dieses Angebots per E-Mail an dessen Kunden senden">${icon('mail', 'sm')}Sonderposten senden</button>` : ''}${!ro && curOffer !== OSTD ? `<button type="button" class="btn sm ghost" data-ob="copy">${icon('copy', 'sm')}Preise übernehmen</button>` : ''}${may('angebote.verwalten') ? `<button type="button" class="btn sm ghost" data-ob="manage">${icon('list', 'sm')}Angebote verwalten</button>` : ''}</span></div>
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

  /* Stammdaten → Angebote: anlegen, umbenennen, Regel für Artikel ohne eigenen Preis, Kundengruppen, löschen (Administrator).
     Kunden einer zugeordneten Kundengruppe sehen das Angebot ohne eigene Freischaltung (Server: customer_offers). */
  let offerEdit = null, ofDirty = false, ofKg = [], ofKunden = null, ofPick = null;
  const slug = (t) => {
    const x = fold(t).replace(/^wochenangebot\s*/, '').replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 32) || 'angebot';
    return /^e-/.test(x) || /^\d+$/.test(x) ? `angebot-${x}`.slice(0, 40) : x;   // „e-…“ gehört Einzelangeboten, reine Zahlen gehen in JSON-Schlüsseln kaputt
  };
  function openOffers() { setView('angebote'); }
  function ofReset() {
    offerEdit = offers.map((o) => ({ ...o, gruppen: [...(o.gruppen || [])] }));
    offerEdit.stdPublic = stdPublic;
    offerEdit.rev = offersRev;   // Stand beim Beginn der Bearbeitung – sonst würde ein zwischendurch geladener Stand fremde Änderungen überschreiben
    ofDirty = false;
  }
  async function renderOffersView() {
    const host = $('#view-angebote');
    if (!offerEdit) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Angebote werden geladen …</div>';
    try {
      const [, g, k] = await Promise.all([ofDirty ? null : loadOffers(), api('kundengruppen').catch(() => ({ groups: [] })), may('kunden.sehen') ? api('kunden').catch(() => null) : null]);
      ofKg = g.groups || []; ofKunden = k ? k.customers : null;
    } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    if (!ofDirty) ofReset();
    renderOffersBody();
  }
  const kgName = (nr) => (ofKg.find((g) => g.nr === nr) || {}).name || '';
  /* Kundengruppe → Angebot (Stand der Eingabe); jede Gruppe gehört zu höchstens einem Angebot */
  const ofGruppeBei = (nr, ausser) => offerEdit.find((o, i) => i !== ausser && (o.gruppen || []).includes(nr));
  function ofKundenZahl(id, gruppen) {
    if (!ofKunden) return null;
    if (id === OSTD) return ofKunden.filter((c) => (c.angeboteDirekt || c.angebote || []).includes(OSTD) || (c.gruppe && !ofGruppeBei(c.gruppe, -1))).length;
    return ofKunden.filter((c) => (c.angeboteDirekt || c.angebote || []).includes(id) || (c.gruppe && gruppen.includes(c.gruppe))).length;
  }
  function ofChips(gruppen, key) {
    const edit = may('angebote.verwalten');
    return `<div class="of-chips">${gruppen.length ? gruppen.map((nr) => `<span class="of-chip${kgName(nr) ? '' : ' fremd'}" title="${esc(kgName(nr) || 'Kundengruppe nicht mehr vorhanden')}">${esc(nr)} · ${esc(kgName(nr) || 'nicht vorhanden')}</span>`).join('') : '<span class="muted">keine</span>'}
      ${edit ? `<button type="button" class="btn sm ghost" data-ofa="gruppen" data-ofk="${esc(key)}">${icon('users', 'sm')}${gruppen.length ? 'Ändern' : 'Zuordnen'}</button>` : ''}</div>`;
  }
  function renderOffersBody(err = '') {
    const host = $('#view-angebote');
    const admin = may('angebote.loeschen'), edit = may('angebote.verwalten');
    const kz = (id, gr) => { const n = ofKundenZahl(id, gr); return n === null ? '<span class="muted">–</span>' : fmtInt.format(n); };
    host.innerHTML = `
      <div class="st-info"><div><strong>Angebote</strong><span class="sub">Alle Angebote nutzen dieselbe Artikelliste; Preise werden je Angebot unter „Angebot bearbeiten“ eingetragen. Kundenangebote sind nur nach Anmeldung sichtbar, nie auf der öffentlichen Seite. Jede Kundengruppe lässt sich genau einem Angebot zuordnen; ihre Kunden sehen dieses Angebot automatisch. Kundengruppen ohne eigenes Angebot bekommen automatisch das Wochenangebot. Beim Kunden direkt freigeschaltete Angebote kommen jeweils hinzu; Kunden ohne Kundengruppe sehen nur diese.</span></div>
        <span class="ms-state${ofDirty ? ' saving' : ''}" id="of-state">${ofDirty ? 'Nicht gespeichert' : ''}</span></div>
      <div class="gcard of-card"><table class="etab oftab"><thead><tr><th>Angebot</th><th>Kundengruppen</th><th class="of-fb">Artikel ohne eigenen Preis</th><th class="num-s">Eigene Preise</th><th class="num-s">Kunden</th><th class="act"></th></tr></thead><tbody>
        <tr class="of-std" data-ofk="std"><td><strong>Wochenangebot</strong><div class="sub">Standard · ${offerEdit.stdPublic ? 'öffentlich ohne Anmeldung' : 'nur für angemeldete Kunden'}</div>
          ${admin ? `<label class="check of-pub"><input type="checkbox" data-ofa-pub${offerEdit.stdPublic ? ' checked' : ''}> Öffentlich ohne Anmeldung sichtbar</label>` : ''}</td>
          <td><span class="sub of-auto">${ofKg.length ? `alle übrigen Kundengruppen (${fmtInt.format(ofKg.filter((g) => !ofGruppeBei(g.nr, -1)).length)} von ${fmtInt.format(ofKg.length)})` : 'Kundengruppen ohne eigenes Angebot'}</span></td><td class="of-fb"><span class="sub">–</span></td><td class="num-s" data-l="Eigene Preise">–</td><td class="num-s" data-l="Kunden">${kz(OSTD, [])}</td><td class="act"></td></tr>
        ${offerEdit.map((o, i) => `<tr data-oi="${i}" data-ofk="${i}"><td><input class="in" data-of="name" value="${esc(o.name)}" maxlength="80" aria-label="Name des Angebots"${edit ? '' : ' disabled'}></td>
          <td>${ofChips(o.gruppen, String(i))}</td>
          <td class="of-fb"><select class="in" data-of="fallback" aria-label="Artikel ohne eigenen Preis"${edit ? '' : ' disabled'}><option value="standard"${o.fallback !== 'hidden' ? ' selected' : ''}>Standardpreis zeigen</option><option value="hidden"${o.fallback === 'hidden' ? ' selected' : ''}>nicht anzeigen</option></select></td>
          <td class="num-s" data-l="Eigene Preise">${o.isNew ? '<span class="sub">neu</span>' : fmtInt.format(ownCount(o.id))}</td>
          <td class="num-s" data-l="Kunden">${o.isNew ? kz('', o.gruppen) : kz(o.id, o.gruppen)}</td>
          <td class="act">${admin || o.isNew ? `<button type="button" class="ibtn danger" data-ofa="del" aria-label="Angebot ${esc(o.name)} löschen" title="${o.isNew ? 'Entfernen' : 'Löschen'}">${icon('trash')}</button>` : ''}</td></tr>`).join('')}
      </tbody></table></div>
      ${edit ? `<div class="of-actions"><button type="button" class="btn" data-ofa="add">${icon('plus')}Angebot hinzufügen</button>${ro ? '' : `<button type="button" class="btn" data-ofa="preise" title="Artikelpreise der Warenwirtschaft (CSV) in den Entwurf übernehmen: ohne Kundengruppe = Wochenangebot, mit Kundengruppe = Angebot der Gruppe">${icon('upload')}Preise importieren</button><input type="file" id="of-file" accept=".csv,text/csv,text/plain" hidden>`}<span class="sp"></span>
        <button type="button" class="btn" data-ofa="reset"${ofDirty ? '' : ' disabled'}>Verwerfen</button><button type="button" class="btn primary" data-ofa="save"${ofDirty ? '' : ' disabled'}>${icon('check')}Speichern</button></div>` : ''}
      <p class="form-err" id="of-err" role="alert">${esc(err)}</p>
      <p class="hint">${ofKunden ? 'Kunden = direkt freigeschaltet oder über eine zugeordnete Kundengruppe (Stand der Eingabe, vor dem Speichern).' : ''} Kundengruppen pflegen: Stammdaten → Kundengruppen; Gruppe eines Kunden: Stammdaten → Kunden.</p>`;
  }
  function ofMark() { ofDirty = true; const s = $('#of-state'); if (s) { s.textContent = 'Nicht gespeichert'; s.className = 'ms-state saving'; } for (const b of $$('#view-angebote [data-ofa="save"], #view-angebote [data-ofa="reset"]')) b.disabled = false; }
  const ofGruppenVon = (key) => offerEdit[+key].gruppen;
  /* Kundengruppen wählen */
  const dlgOfG = $('#dlg-of-gruppen');
  function openOfGruppen(key) {
    const name = offerEdit[+key].name;
    ofPick = { key, sel: new Set(ofGruppenVon(key)), q: '' };
    const nKunden = (nr) => (ofKunden ? ofKunden.filter((c) => c.gruppe === nr).length : null);
    const fremd = [...ofPick.sel].filter((nr) => !ofKg.some((g) => g.nr === nr));
    const belegt = (nr) => (ofPick.sel.has(nr) ? null : ofGruppeBei(nr, +key));
    $('#of-gruppen-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="ofg-title">Kundengruppen für „${esc(name)}“</h2><p>Kunden dieser Gruppen sehen das Angebot nach der Anmeldung automatisch. Gruppen, die schon einem anderen Angebot zugeordnet sind, sind gesperrt.</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        ${ofKg.length ? `<div class="search">${icon('search')}<input id="ofg-q" type="search" autocomplete="off" placeholder="Gruppe finden: Nummer, Bezeichnung …" aria-label="Kundengruppen suchen"></div>
        <div class="ofg-bar"><span class="sub" id="ofg-n"></span><button type="button" class="link-btn" data-ofg="none">Keine</button></div>
        <ul class="ofg-list">${[...ofKg, ...fremd.map((nr) => ({ nr, name: 'nicht mehr vorhanden', fremd: true }))].map((g) => `<li data-hay="${esc(fold(g.nr + ' ' + g.name))}"${belegt(g.nr) ? ' class="belegt"' : ''}><label class="check"><input type="checkbox" value="${esc(g.nr)}"${ofPick.sel.has(g.nr) ? ' checked' : ''}${belegt(g.nr) ? ' disabled' : ''}> <span class="muted">${esc(g.nr)}</span> ${esc(g.name)}${nKunden(g.nr) ? ` <small class="muted">· ${plural(nKunden(g.nr), 'Kunde', 'Kunden')}</small>` : ''}${belegt(g.nr) ? ` <small class="ofg-bei">bei „${esc(belegt(g.nr).name)}“</small>` : ''}</label></li>`).join('')}</ul>`
          : '<p class="hint">Noch keine Kundengruppen angelegt – bitte zuerst unter Stammdaten → Kundengruppen importieren.</p>'}
      </div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="button" class="btn primary" data-ofg="ok"${ofKg.length ? '' : ' disabled'}>${icon('check')}Übernehmen</button></div>`;
    ofgCount();
    dlgOfG.showModal();
    const q = $('#ofg-q'); if (q) q.focus();
  }
  function ofgCount() { const n = $('#ofg-n'); if (n) n.textContent = `${plural(ofPick.sel.size, 'Gruppe', 'Gruppen')} gewählt`; }
  $('#of-gruppen-body').addEventListener('input', (e) => {
    if (e.target.id !== 'ofg-q') return;
    const toks = fold(e.target.value).split(/\s+/).filter(Boolean);
    for (const li of $$('#of-gruppen-body .ofg-list li')) li.hidden = !toks.every((t) => li.dataset.hay.includes(t));
  });
  $('#of-gruppen-body').addEventListener('change', (e) => {
    if (e.target.type !== 'checkbox') return;
    if (e.target.checked) ofPick.sel.add(e.target.value); else ofPick.sel.delete(e.target.value);
    ofgCount();
  });
  $('#of-gruppen-body').addEventListener('click', (e) => {
    if (e.target.closest('[data-close]')) { dlgOfG.close(); return; }
    const a = e.target.closest('[data-ofg]')?.dataset.ofg;
    if (a === 'none') { ofPick.sel.clear(); for (const x of $$('#of-gruppen-body .ofg-list input:not(:disabled)')) x.checked = false; ofgCount(); return; }
    if (a === 'ok') {
      const list = [...ofPick.sel].sort((x, y) => x.localeCompare(y, 'de', { numeric: true }));
      offerEdit[+ofPick.key].gruppen = list;
      dlgOfG.close(); ofMark(); renderOffersBody();
    }
  });
  $('#view-angebote').addEventListener('input', (e) => {
    const tr = e.target.closest('[data-oi]');
    if (tr && e.target.dataset.of) { offerEdit[+tr.dataset.oi][e.target.dataset.of] = e.target.value; ofMark(); }
  });
  $('#view-angebote').addEventListener('change', (e) => {
    if (e.target.id === 'of-file' && e.target.files[0]) { const f = e.target.files[0]; e.target.value = ''; ofPreiseDatei(f); return; }
    if (e.target.matches('[data-ofa-pub]')) { offerEdit.stdPublic = e.target.checked; ofMark(); renderOffersBody(); return; }
    const tr = e.target.closest('[data-oi]');
    if (tr && e.target.dataset.of) { offerEdit[+tr.dataset.oi][e.target.dataset.of] = e.target.value; ofMark(); }
  });
  $('#view-angebote').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-ofa]');
    if (!b) return;
    const a = b.dataset.ofa;
    if (a === 'gruppen') { openOfGruppen(b.dataset.ofk); return; }
    if (a === 'preise') { $('#of-file').click(); return; }
    if (a === 'reset') { ofReset(); renderOffersBody(); return; }
    if (a === 'add') {
      offerEdit.push({ id: '', name: 'Wochenangebot ', fallback: 'standard', gruppen: [], isNew: true });
      ofMark(); renderOffersBody();
      const inp = $$('#view-angebote [data-of="name"]').pop(); inp.focus(); inp.setSelectionRange(inp.value.length, inp.value.length);
      return;
    }
    if (a === 'del') {
      const i = +b.closest('[data-oi]').dataset.oi, o = offerEdit[i];
      if (!o.isNew) {
        const n = ownCount(o.id);
        if (!(await confirmBox('Angebot löschen?', `„${esc(o.name)}“ wird beim Speichern gelöscht${n ? ` – mit ${n} eigenen Preis${n === 1 ? '' : 'en'}` : ''}. Das lässt sich nicht rückgängig machen.`, 'Löschen', true))) return;
      }
      offerEdit.splice(i, 1);
      ofMark(); renderOffersBody();
      return;
    }
    if (a === 'save') {
      const used = new Set(offers.map((o) => o.id));
      const list = offerEdit.map((o) => {
        let id = o.id;
        if (!id) { const base = slug(o.name); id = base; let k = 2; while (used.has(id) || id === OSTD) id = `${base}-${k++}`; used.add(id); }
        return { id, name: C.clean(o.name), fallback: o.fallback === 'hidden' ? 'hidden' : 'standard', gruppen: o.gruppen || [] };
      });
      b.disabled = true;
      try {
        const body = { rev: offerEdit.rev, offers: list };
        if (may('angebote.loeschen')) body.stdPublic = !!offerEdit.stdPublic;
        const r = await api('offers_save', { body });
        offers = r.offers; offersRev = r.rev; stdPublic = r.stdPublic !== false;
        const gone = new Set([OSTD, ...list.map((o) => o.id)]);
        let dropped = false;
        for (const it of model.items) {
          if (it.variants) for (const k of Object.keys(it.variants)) if (!gone.has(k)) { delete it.variants[k]; dropped = true; }
          if (it.sale && it.sale.offers) { for (const k of Object.keys(it.sale.offers)) if (!gone.has(k)) { delete it.sale.offers[k]; dropped = true; } if (!Object.keys(it.sale.offers).length) delete it.sale.offers; }
        }
        if (!knownOffer(curOffer)) curOffer = OSTD;
        ofReset();
        toast('Angebote gespeichert.');
        diff = C.diffOffers(published, model);
        renderOfferBar(); renderGroups(); renderChanges(); updatePublishBtn();
        if (dropped) changed({ render: true });
        renderOffersBody();
      } catch (ex) { b.disabled = false; renderOffersBody(ex.message); }
    }
  });

  /* Preise aus der Warenwirtschaft importieren (CSV „Artikelpreise“: Preis-Art; Kundengruppe; Artikel; Preis).
     Zeilen ohne Kundengruppe = Wochenangebot (Preis im Entwurf), mit Kundengruppe = Preis im Angebot dieser Gruppe.
     Eingetragen wird in den Entwurf (zum Übernehmen veröffentlichen); Artikel, die nicht im Angebot stehen, und Preise,
     die nicht in der Datei stehen, bleiben unverändert. Kundengruppen ohne Angebot: auf Wunsch je ein Angebot anlegen. */
  const dlgOfP = $('#dlg-of-preise');
  let ofImp = null;
  function preiseAusCsv(buf) {
    const rows = window.WA.csvZeilen(window.WA.csvText(buf));
    if (!rows.length) throw new Error('Die Datei ist leer.');
    const kopf = rows[0].map((c) => fold(c).replace(/[^a-z0-9]/g, ''));
    const sp = (...n) => kopf.findIndex((k) => n.includes(k));
    const iArt = sp('artikel', 'artikelnummer', 'nummer'), iGr = sp('kundengruppe', 'gruppe'), iPr = sp('preis', 'vk', 'vkpreis');
    if (iArt < 0 || iPr < 0 || iGr < 0) throw new Error('Spalten „Kundengruppe“, „Artikel“ und „Preis“ nicht gefunden. Erwartet wird die Artikelpreis-Liste der Warenwirtschaft (Preis-Art; Kundengruppe; Artikel; Preis).');
    const out = [];
    let leer = 0, fehler = 0;
    for (const r of rows.slice(1)) {
      const code = (r[iArt] || '').trim(), gruppe = (r[iGr] || '').trim(), roh = (r[iPr] || '').trim();
      if (!code) continue;
      if (!roh) { leer++; continue; }
      const p = C.parsePrice(roh);
      if (p.status !== 'value') { fehler++; continue; }
      out.push({ code, gruppe, value: p.value });
    }
    if (!out.length) throw new Error('Keine Preise in der Datei gefunden.');
    return { rows: out, leer, fehler };
  }
  function ofPreisPlan() {
    const anlegen = ofImp.anlegen;
    const bei = new Map();
    for (const o of offers) for (const g of (o.gruppen || [])) if (!bei.has(g)) bei.set(g, o.id);
    const items = new Map();
    for (const it of model.items) if (it.code) { const k = mKey(it.code); if (!items.has(k)) items.set(k, []); items.get(k).push(it); }
    const ziele = new Map(), fehltGruppe = new Map(), nichtIm = new Set(), gesetzt = new Map();
    let konflikt = 0;
    for (const r of ofImp.data.rows) {
      let ziel = OSTD;
      if (r.gruppe) {
        ziel = bei.get(r.gruppe) || (anlegen ? 'neu:' + r.gruppe : null);
        if (!bei.has(r.gruppe)) fehltGruppe.set(r.gruppe, (fehltGruppe.get(r.gruppe) || 0) + 1);
        if (!ziel) continue;
      }
      const list = items.get(mKey(r.code));
      if (!list) { nichtIm.add(r.code); continue; }
      const key = ziel + '|' + mKey(r.code);
      if (gesetzt.has(key)) { if (gesetzt.get(key) !== r.value) konflikt++; continue; }
      gesetzt.set(key, r.value);
      const z = ziele.get(ziel) || { preise: 0, geaendert: 0, neu: 0, aend: [] };
      for (const it of list) {
        const alt = ziel === OSTD ? it.price : ziel.startsWith('neu:') ? null : (it.variants || {})[ziel];
        if (alt && alt.status === 'value' && Math.abs(alt.value - r.value) < 0.00005) continue;
        if (alt && alt.status === 'value') z.geaendert++; else z.neu++;
        z.aend.push({ it, value: r.value });
      }
      z.preise++;
      ziele.set(ziel, z);
    }
    return { ziele, fehltGruppe, nichtIm, konflikt };
  }
  async function ofPreiseDatei(file) {
    if (ro) { toast('Preise importieren dürfen nur Nutzer, die das Angebot bearbeiten dürfen.'); return; }
    if (ofDirty) { toast('Bitte zuerst die Änderungen an den Angeboten speichern oder verwerfen.', 6000); return; }
    let data;
    try { data = preiseAusCsv(await file.arrayBuffer()); } catch (ex) { toast(ex.message, 8000); return; }
    ofImp = { file, data, anlegen: true };
    renderOfPreise();
    dlgOfP.showModal();
  }
  function renderOfPreise(err = '') {
    const plan = ofImp.plan = ofPreisPlan();
    const name = (z) => (z === OSTD ? 'Wochenangebot' : z.startsWith('neu:') ? `Wochenangebot ${kgName(z.slice(4)) || z.slice(4)} (neu)` : offerName(z));
    const gruppenVon = (z) => (z === OSTD ? 'ohne Kundengruppe' : z.startsWith('neu:') ? z.slice(4) : (offers.find((o) => o.id === z) || {}).gruppen?.join(', ') || '');
    const ziele = [...plan.ziele.entries()].sort((a, b) => (a[0] === OSTD ? -1 : b[0] === OSTD ? 1 : name(a[0]).localeCompare(name(b[0]), 'de')));
    const summe = ziele.reduce((n, [, z]) => n + z.aend.length, 0);
    const fehlt = [...plan.fehltGruppe.entries()];
    const platz = OFFER_MAX_UI - offers.length;
    $('#of-preise-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="ofp-title">Preise importieren</h2><p>${esc(ofImp.file.name)} · ${plural(ofImp.data.rows.length, 'Preis', 'Preise')}</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        ${fehlt.length ? `<div class="ofp-fehlt"><p class="hint st-warn">${plural(fehlt.length, 'Kundengruppe hat', 'Kundengruppen haben')} noch kein Angebot: ${esc(fehlt.slice(0, 12).map(([nr, n]) => `${nr}${kgName(nr) ? ' ' + kgName(nr) : ''} (${n})`).join(', '))}${fehlt.length > 12 ? ' …' : ''}</p>
          <label class="check"><input type="checkbox" data-ofp="anlegen"${ofImp.anlegen ? ' checked' : ''}${fehlt.length > platz ? ' disabled' : ''}> Für ${fehlt.length === 1 ? 'diese Kundengruppe ein Angebot' : `diese ${fehlt.length} Kundengruppen je ein Angebot`} anlegen <small class="muted">(„Wochenangebot &lt;Gruppe&gt;“, ohne eigenen Preis: Standardpreis zeigen)</small></label>
          ${fehlt.length > platz ? `<p class="hint">Es sind höchstens ${OFFER_MAX_UI} Angebote möglich.</p>` : ''}</div>` : ''}
        <table class="etab ofptab"><thead><tr><th>Angebot</th><th>Kundengruppe</th><th class="num-s">Preise</th><th class="num-s">geändert</th><th class="num-s">neu</th></tr></thead><tbody>
          ${ziele.map(([z, v]) => `<tr data-ofp-ziel="${esc(z)}"><td>${esc(name(z))}</td><td class="sub">${esc(gruppenVon(z))}</td><td class="num-s">${fmtInt.format(v.preise)}</td><td class="num-s">${fmtInt.format(v.geaendert)}</td><td class="num-s">${fmtInt.format(v.neu)}</td></tr>`).join('') || '<tr><td colspan="5" class="muted">Keine Preise zuzuordnen.</td></tr>'}
        </tbody></table>
        <p class="hint">Eingetragen wird in den Entwurf – erst mit „Veröffentlichen“ sehen die Kunden die Preise. Preise, die nicht in der Datei stehen, bleiben unverändert.${plan.nichtIm.size ? ` ${plural(plan.nichtIm.size, 'Artikelnummer steht', 'Artikelnummern stehen')} nicht im Angebot und ${plan.nichtIm.size === 1 ? 'wird' : 'werden'} übersprungen.` : ''}${ofImp.data.leer ? ` ${fmtInt.format(ofImp.data.leer)} Zeilen ohne Preis übersprungen.` : ''}${ofImp.data.fehler ? ` ${ofImp.data.fehler} unlesbare Preise übersprungen.` : ''}${plan.konflikt ? ` ${plan.konflikt}× unterschiedliche Preise für denselben Artikel im selben Angebot (mehrere Gruppen) – der erste gilt.` : ''}</p>
        <p class="kerr" id="ofp-err" role="alert">${esc(err)}</p>
      </div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="button" class="btn primary" data-ofp="ok"${summe || (ofImp.anlegen && fehlt.length) ? '' : ' disabled'}>${icon('check')}${summe ? `${fmtInt.format(summe)} Preise eintragen` : 'Übernehmen'}</button></div>`;
  }
  const OFFER_MAX_UI = 100;
  $('#of-preise-body').addEventListener('change', (e) => { if (e.target.dataset.ofp === 'anlegen') { ofImp.anlegen = e.target.checked; renderOfPreise(); } });
  $('#of-preise-body').addEventListener('click', async (e) => {
    if (e.target.closest('[data-close]')) { dlgOfP.close(); return; }
    const b = e.target.closest('[data-ofp="ok"]');
    if (!b) return;
    b.disabled = true;
    try {
      const neu = ofImp.anlegen ? [...ofImp.plan.fehltGruppe.keys()] : [];
      const ids = new Map();
      if (neu.length) {   // Angebote für Kundengruppen ohne Angebot anlegen
        const used = new Set(offers.map((o) => o.id)), names = new Set(offers.map((o) => fold(o.name)));
        const list = offers.map((o) => ({ id: o.id, name: o.name, fallback: o.fallback || 'standard', gruppen: o.gruppen || [] }));
        for (const nr of neu) {
          let nm = `Wochenangebot ${kgName(nr) || 'Kundengruppe ' + nr}`.slice(0, 80);
          if (names.has(fold(nm))) nm = `${nm.slice(0, 70)} (${nr})`;
          names.add(fold(nm));
          const base = slug(nm); let id = base, k = 2; while (used.has(id) || id === OSTD) id = `${base}-${k++}`; used.add(id);
          list.push({ id, name: nm, fallback: 'standard', gruppen: [nr] });
          ids.set('neu:' + nr, id);
        }
        const r = await api('offers_save', { body: { rev: offersRev, offers: list } });
        offers = r.offers; offersRev = r.rev; stdPublic = r.stdPublic !== false;
      }
      pushUndo();
      let n = 0;
      for (const [ziel, z] of ofImp.plan.ziele) {
        const oid = ziel.startsWith('neu:') ? ids.get(ziel) : ziel;
        if (!oid) continue;
        for (const { it, value } of z.aend) {
          if (oid === OSTD) it.price = { status: 'value', value, ...(it.price && it.price.label ? { label: it.price.label } : {}) };
          else { it.variants = it.variants || {}; it.variants[oid] = { status: 'value', value }; }
          n++;
        }
      }
      dlgOfP.close();
      ofReset();
      if (n) { saveNote = { type: 'import', file: `Preise ${ofImp.file.name}` }; changed({ render: true }); }
      diff = C.diffOffers(published, model);
      renderOfferBar(); renderChanges(); updatePublishBtn();
      renderOffersBody();
      toast(`${fmtInt.format(n)} Preise im Entwurf eingetragen${neu.length ? `, ${plural(neu.length, 'Angebot', 'Angebote')} angelegt` : ''} – zum Übernehmen veröffentlichen.`, 7000);
    } catch (ex) { b.disabled = false; renderOfPreise(ex.message); }
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
    if (!may('angebot.veroeffentlichen')) return;
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
      showSendHint(model.meta.week, model.meta.year);
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
    if (a === 'passkeys') openPasskeyDialog();
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
      let r = null;
      try { r = await api('logout', { body: {} }); } catch { /* ignore */ }
      // Zentrale Anmeldung (Keycloak-Host): auch dort abmelden; sonst Seite neu laden – zwischengespeicherte Daten
      // (Bestand, Kunden, Stammdaten …) gehören nicht dem nächsten Nutzer
      if (r && typeof r.abmelden === 'string' && r.abmelden.startsWith('/oidc/')) location.replace(r.abmelden);
      else location.replace(location.pathname);
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
  /* Versand an Kunden: Knopf oben und Hinweis direkt nach dem Veröffentlichen (an jedem Tag möglich) */
  function showSendHint(week, year) {
    const h = $('#send-hint');
    if (!can('admin')) { h.hidden = true; return; }
    h.innerHTML = `<div class="send-in">${icon('check', 'sm')}<span><strong>KW ${esc(week)}/${esc(year)} ist online.</strong> Jetzt per E-Mail an Ihre Kunden senden?</span><button type="button" class="btn sm primary" data-send="open">${icon('mail', 'sm')}An Kunden senden</button><button type="button" class="btn sm ghost icon" data-send="close" aria-label="Hinweis schließen">${icon('x', 'sm')}</button></div>`;
    h.hidden = false;
  }
  const openSend = () => { if (window.WA.openRund) window.WA.openRund(); };
  $('#btn-send').addEventListener('click', openSend);
  $('#send-hint').addEventListener('click', (e) => {
    const a = e.target.closest('[data-send]')?.dataset.send;
    if (a === 'close') $('#send-hint').hidden = true;
    if (a === 'open') { $('#send-hint').hidden = true; openSend(); }
  });
  $('#btn-publish').addEventListener('click', () => { if (document.activeElement && document.activeElement.matches('.in, .fld input')) document.activeElement.blur(); setTimeout(openPublish, 0); });
  $('#btn-add-group').addEventListener('click', addGroup);
  $('#btn-preview').addEventListener('click', async () => {
    const w = window.open('', '_blank');
    if (unsaved()) await saveNow();
    const u = '../?vorschau=1' + (curOffer !== OSTD ? '&angebot=' + encodeURIComponent(curOffer) : '');
    if (w) w.location = u; else location.href = u;
  });
  $('#save-state').addEventListener('click', (e) => { if (e.target.closest('[data-act="retry-save"]')) saveNow(); });
  /* Dialoge schließen per Klick daneben, Escape oder [data-close]. Dialoge mit data-fest (Formulare wie „Nutzer anlegen“)
     schließen nur über ihre Knöpfe – ein Klick daneben oder Escape verwirft keine Eingaben. */
  for (const d of $$('dialog')) {
    d.addEventListener('click', (e) => {
      const daneben = e.target === d;
      if (daneben && d.dataset.fest !== undefined) return;
      if (daneben || e.target.closest('[data-close]')) { if (d.id !== 'dlg-confirm' && !d.dataset.busy) d.close(); }
    });
    d.addEventListener('cancel', (e) => { if (d.dataset.fest !== undefined) e.preventDefault(); });
  }

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
  const VIEWS = ['orders', 'edit', 'einzel', 'hist', 'stock', 'einkauf', 'master', 'vkgruppen', 'angebote', 'kunden', 'gruppen', 'vertreter', 'importe', 'auswertung', 'mail', 'users', 'log', 'sec', 'schutz'];
  const ADMIN_VIEWS = ['mail', 'users', 'sec', 'schutz'];
  function setView(v) {
    if (!viewAllowed(v)) v = viewAllowed('edit') ? 'edit' : (VIEWS.find(viewAllowed) || 'edit');
    currentView = v;
    for (const k of VIEWS) {
      $('#vt-' + k).setAttribute('aria-selected', k === v);
      $('#view-' + k).hidden = k !== v;
    }
    document.body.classList.toggle('in-hist', v === 'hist');
    document.body.classList.toggle('in-other', v !== 'edit');
    document.body.classList.toggle('in-einzel', v === 'einzel');
    if (v === 'edit' && model) loadAux();
    if (v === 'hist') renderHistView();
    if (v === 'stock') renderStockView();
    if (v === 'master') renderMasterView();
    if (v === 'angebote') renderOffersView();
    if (v === 'users' && window.WA.views.users) window.WA.views.users();
    if (v === 'orders' && window.WA.views.orders) window.WA.views.orders();
    if (v === 'einkauf' && window.WA.views.einkauf) window.WA.views.einkauf();
    if (v === 'kunden' && window.WA.views.kunden) window.WA.views.kunden();
    if (v === 'gruppen' && window.WA.views.gruppen) window.WA.views.gruppen();
    if (v === 'vkgruppen' && window.WA.views.vkgruppen) window.WA.views.vkgruppen();
    if (v === 'vertreter' && window.WA.views.vertreter) window.WA.views.vertreter();
    if (v === 'einzel' && window.WA.views.einzel) window.WA.views.einzel();
    if (v === 'importe' && window.WA.views.importe) window.WA.views.importe();   // Importzentrale (admin-import.js)
    if (v === 'auswertung' && window.WA.views.auswertung) window.WA.views.auswertung();
    if (v === 'mail' && window.WA.views.mail) window.WA.views.mail();
    if (v === 'log' && window.WA.views.log) window.WA.views.log();
    if (v === 'sec' && window.WA.views.sec) window.WA.views.sec();
    if (v === 'schutz' && window.WA.views.schutz) window.WA.views.schutz();
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
    if (!del || roHist) return;
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
  /* Eine Angebotsliste als Woche lesen (Angebotsleser offer-core.js) – hier und in der Importzentrale */
  async function histAusDatei(file) {
    if (!/\.(xlsx|xlsm)$/i.test(file.name)) throw new Error('keine .xlsx-Datei');
    const m = C.parseOfferWorkbook(await C.xlsxReadWorkbook(await file.arrayBuffer()), file.name);
    if (!m.items.length) throw new Error('keine Artikel gefunden');
    const gn = new Map(m.groups.map((g) => [g.id, g.name]));
    const items = m.items.map((it) => {
      const row = { code: it.code, name: it.name, group: gn.get(it.groupId) || '', category: it.category, price: it.price };
      if (it.altPrices && it.altPrices.length) row.altPrices = it.altPrices;
      return row;
    });
    return { items, week: m.meta.week, year: m.meta.year, warn: m.issues.filter((x) => x.level === 'warn').length };
  }
  const dlgHI = $('#dlg-hist-import');
  let hiEntries = [];
  $('#hist-file-input').addEventListener('change', (e) => { const files = [...e.target.files]; e.target.value = ''; if (files.length) histImportFiles(files); });
  async function histImportFiles(files) {
    if (roHist) return;
    const base = dlgHI.open ? hiEntries.filter((en) => en.status !== 'gespeichert') : [];
    const added = files.map((f) => ({ file: f, status: 'lesen' }));
    hiEntries = base.concat(added);
    renderHistImport();
    if (!dlgHI.open) dlgHI.showModal();
    try { await loadHistory(); } catch { /* Liste ggf. leer */ }
    for (const en of added) {
      try {
        Object.assign(en, await histAusDatei(en.file));
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
    if (currentView !== 'hist' || !model || roHist) return;
    const files = [...(e.dataTransfer?.files || [])];
    if (files.length) { e.preventDefault(); e.stopImmediatePropagation(); histImportFiles(files); }
  }, true);

  /* ======================= Bestand (Mengen, MHD – nur im Eingabebereich) ======================= */
  const S = window.StockCore;
  let stockPrices = null;
  let stock = null, stockLoaded = false, stockLoading = null, stockQ = '';
  const fmtKg = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  /* kaufmännisch auf 0,01 kg runden – über ganze Gramm, damit ,xx5 nicht durch Gleitkomma-Reste nach unten kippt */
  const kg2 = (v) => { const g = Math.round(v * 1000); return (g < 0 ? -Math.round(-g / 10) : Math.round(g / 10)) / 100; };
  const kgText = (v) => (v == null || !Number.isFinite(v) ? '—' : fmtKg.format(kg2(v)) + ' kg');
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
    if (!stockLoading) stockLoading = api('stock').then((r) => { stock = r.stock || null; stockPrices = r.prices || null; stockLoaded = true; return stock; }).finally(() => { stockLoading = null; });
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
    const prices = S.weekPriceMap(stockPrices?.current), previous = S.weekPriceMap(stockPrices?.previous);
    const offers = offerPriceMap();
    const rows = new Map(stock.articles.map((a) => [S.normCode(a.code), { ...a, incoming: [] }]));
    for (const delivery of (stock.incoming || [])) {
      const key = S.normCode(delivery.code);
      if (!rows.has(key)) rows.set(key, { code: delivery.code, name: delivery.name, kg: null, mhd: null, mhdKg: null, lots: [], incoming: [] });
      rows.get(key).incoming.push(delivery);
    }
    return [...rows.values()].map((a, idx) => {
      const key = S.normCode(a.code), price = prices.get(key), prevPrice = previous.get(key);
      a.incoming.sort((x, y) => (x.arrival || '9999').localeCompare(y.arrival || '9999'));
      return { ...a, idx, wg: S.warengruppe(a.code), offer: offers.get(key) || [], price, prevPrice,
        incomingKg: sum(a.incoming, 'kg'), totalKg: (a.kg ?? 0) + sum(a.incoming, 'kg'), cls: mhdClass(a.mhd), _hay: fold(a.code + ' ' + a.name) };
    });
  }
  const stockPriceNumber = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  const stockWeekLabel = (which) => stockPrices?.[which] ? `KW ${stockPrices[which].week}/${stockPrices[which].year}` : 'KW unbekannt';
  const stockPriceText = (p) => !stockPrices?.allowed ? 'keine Berechtigung' : p?.status === 'ambiguous' ? 'mehrere Preisangaben' : p?.status === 'value' ? `${stockPriceNumber.format(p.value)} €${p.label ? ' · ' + p.label : '/kg'}` : p?.status === 'request' ? 'auf Anfrage' : '—';
  const incomingHTML = (a) => a.incoming.length ? `<ul class="st-incoming">${a.incoming.map((d) => `<li><strong>${esc(kgText(d.kg))}</strong> · ${d.arrival ? 'ETA ' + esc(dmy(d.arrival)) : 'ETA unbekannt'}${d.marke || d.lot ? ` <small>${d.marke ? esc(d.marke) + (d.lot ? ' · ' : '') : ''}${d.lot ? 'Partie ' + esc(d.lot) : ''}</small>` : ''}</li>`).join('')}</ul>` : '<span class="muted">keine Zugangsdaten</span>';
  const vkText = (p) => (!p ? '—' : p.status === 'value' ? fmtNum.format(p.value) + ' €' : p.status === 'request' ? 'a. Anfr.' : '—');
  /* Summe in ganzen Gramm (exakt, unabhängig von der Reihenfolge) */
  const sum = (list, f) => list.reduce((t, a) => t + (Number.isFinite(a[f]) ? Math.round(a[f] * 1000) : 0), 0) / 1000;
  /* Normale Suche: Warengruppen, MHD-markierte zuerst (früheste oben), dann Artikelnummer; MHD-Abfrage: flach bis heute + 14 Tage */
  /* Sortierung per Klick auf die Spaltenüberschrift (leere Werte immer unten) */
  let stockSort = store.get('stockSort', null);   // { key, dir } oder null = Standard
  const byCode = (a, b) => a.code.localeCompare(b.code, 'de', { numeric: true });
  const vkNum = (a) => (a.price && a.price.status === 'value' ? a.price.value : null);
  const SORT_GET = { code: null, name: (a) => a.name, vk: vkNum, kg: (a) => a.kg, incomingKg: (a) => a.incomingKg, totalKg: (a) => a.totalKg, mhd: (a) => a.mhd, mhdKg: (a) => a.mhdKg };
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
  const stockHead = () => `<tr>${sortTh('code', 's-code', 'Art.-Nr.')}${sortTh('name', 's-name', 'Art. Bezeichnung')}${sortTh('vk', 's-vk', `Aktueller Preis<br>${esc(stockWeekLabel('current'))}`)}<th>Preis Vorwoche<br>${esc(stockWeekLabel('previous'))}</th>${sortTh('kg', 's-kg', 'Eingelagerter<br>Bestand')}${sortTh('mhd', 's-mhd', 'Kürz.<br>MHD')}${sortTh('mhdKg', 's-mkg', 'Kg kürz.<br>MHD')}${sortTh('incomingKg', 's-registered', 'Erfasster<br>Bestand')}${sortTh('totalKg', 's-total-kg', 'Gesamt<br>verfügbar')}<th>Erwartete Zugänge</th></tr>`;
  const stockRow = (a, print = false) => `<tr class="srow" data-sidx="${a.idx}" tabindex="0">
      <td class="s-code">${esc(a.code)}</td><td class="s-name" title="${esc(a.name)}">${esc(a.name)}</td>
      <td class="s-vk" data-l="Aktuell ${esc(stockWeekLabel('current'))}">${esc(stockPriceText(a.price))}</td>
      <td class="s-prev" data-l="Vorwoche ${esc(stockWeekLabel('previous'))}">${esc(stockPriceText(a.prevPrice))}</td>
      <td class="s-kg" data-l="Eingelagerter Bestand">${a.kg == null ? '—' : esc(kgText(a.kg))}</td>
      <td class="s-mhd ${a.cls}" data-l="Kürz. MHD">${esc(mhdShort(a.mhd))}</td><td class="s-mkg ${a.cls}" data-l="Kg kürz. MHD"><span>${mhdKgHTML(a)}</span></td>
      <td class="s-registered" data-l="Erfasster Bestand">${esc(kgText(a.incomingKg))}</td><td class="s-total-kg" data-l="Gesamt verfügbar">${esc(kgText(a.totalKg))}</td>
      <td class="s-incoming" data-l="Erwartete Zugänge">${print ? incomingHTML(a) : a.incoming.length ? `<button type="button" class="btn sm" data-incoming="${a.idx}" aria-haspopup="dialog" aria-label="Erwartete Zugänge für ${esc(a.name)} anzeigen">Zugänge (${a.incoming.length})</button>` : '—'}</td></tr>`;
  const totalRow = (label, list, cls) => `<tr class="${cls}"><td colspan="4">${esc(label)}</td><td class="s-kg" data-l="Eingelagerter Bestand">${esc(kgText(sum(list, 'kg')))}</td><td class="s-mhd"></td><td class="s-mkg" data-l="Kg kürz. MHD">${esc(kgText(sum(list, 'mhdKg')))}</td><td class="s-registered" data-l="Erfasster Bestand">${esc(kgText(sum(list, 'incomingKg')))}</td><td class="s-total-kg" data-l="Gesamt verfügbar">${esc(kgText(sum(list, 'totalKg')))}</td><td class="s-incoming"></td></tr>`;
  function stockTableHTML(res, print = false) {
    const rows = (list) => list.map((a) => stockRow(a, print)).join('');
    let body;
    if (res.flat) body = `<tbody>${rows(res.list)}</tbody>`;
    else body = res.groups.map((g, i) => `<tbody class="wg">${i ? '<tr class="wg-gap" aria-hidden="true"><td colspan="10"></td></tr>' : ''}<tr class="wg-h"><td colspan="10">${esc(g.label)}</td></tr>${rows(g.items)}${totalRow('Summe ' + g.label, g.items, 'wg-sum')}</tbody>`).join('');
    return `<table class="stab${res.flat ? ' flat' : ''}"><thead>${stockHead()}</thead>${body}<tfoot>${totalRow('Gesamtsumme', res.list, 'st-total')}</tfoot></table>`;
  }
  const legendHTML = () => `<div class="mhd-legend" aria-label="MHD-Kennzeichnung"><span class="mhd-past">${SKULL} abgelaufen</span><span class="mhd-0-4">heute – 4 Tage</span><span class="mhd-5-7">5 – 7 Tage</span><span class="mhd-8-14">8 – 14 Tage</span></div>`;

  async function renderStockView() {
    const host = $('#view-stock');
    if (!stockLoaded) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Bestand wird geladen …</div>';
    try { await loadStock(true); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    if (!stock) {
      host.innerHTML = `<div class="ed-empty"><h3>Noch kein Bestand übernommen</h3><p>Laden Sie die Bestandsliste aus WinAB hoch (z. B. „Bestand_16.10.26.XLS“). Mengen und MHD erscheinen nur hier im Eingabebereich – nie auf der öffentlichen Angebotsseite.</p>
        ${roStock ? '' : `<div class="row-actions"><button type="button" class="btn primary" data-st="import">${icon('upload')}Bestandsliste hochladen</button></div>`}</div>`;
      return;
    }
    const age = stock.date ? Math.round((Date.parse(isoToday() + 'T12:00:00Z') - Date.parse(stock.date + 'T12:00:00Z')) / 864e5) : null;
    host.innerHTML = `
      <div class="st-info${age != null && age > 2 ? ' old' : ''}">
        <div><strong>Bestand vom ${stock.date ? esc(dmy(stock.date)) : 'unbekannten Datum'}</strong>${age != null && age > 2 ? ` <span class="st-age">· ${age} Tage alt</span>` : ''}<span class="sub">${esc(stock.source || '')}${stock.importedAt ? ` · übernommen ${esc(dateTime(stock.importedAt))}${stock.importedBy ? ' von ' + esc(stock.importedBy) : ''}` : ''} · Mengenstand aus dem letzten Import</span><span class="sub">Preise: gespeicherte Wochenstände des Standardangebots, €/kg (abweichende Preisbasis ausdrücklich angegeben). Eingelagert = im Lager. Erfasst = noch nicht eingetroffen. Gesamt verfügbar = eingelagerter + erfasster Bestand.</span></div>
        ${legendHTML()}
      </div>
      <div class="ed-toolbar">
        <div class="search">${icon('search')}<input id="st-q" type="search" autocomplete="off" placeholder="Nummer, Bezeichnung … oder „MHD“" aria-label="Bestand durchsuchen" value="${esc(stockQ)}"></div>
        <span class="ed-hint" id="st-count"></span>
        <span class="st-actions">
          <button type="button" class="btn" data-st="print">${icon('print')}Drucken</button>
          <button type="button" class="btn" data-st="pdf" title="PDF ohne Preise, erfassten Bestand, Gesamt verfügbar und erwartete Zugänge">${icon('file')}PDF</button>
          <button type="button" class="btn" data-st="csv">${icon('download')}CSV</button>
          ${roStock ? '' : `<button type="button" class="btn primary" data-st="import">${icon('upload')}Bestand hochladen</button>`}
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
      : `<strong>${fmtInt.format(res.list.length)}</strong> von ${fmtInt.format(stockItems().length)} Artikeln${stockQ ? '' : ' · Tipp: „MHD“ eingeben'}`;
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
      if (a === 'import') { if (!roStock) $('#stock-file-input').click(); }
      if (a === 'print') printStock();
      if (a === 'pdf') stockPDF(b);
      if (a === 'csv') stockCSV();
      return;
    }
    const incoming = e.target.closest('[data-incoming]');
    if (incoming) { openStockIncoming(+incoming.dataset.incoming); return; }
    const tr = e.target.closest('tr.srow');
    if (tr) openStockItem(+tr.dataset.sidx);
  });
  $('#view-stock').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr.srow')) openStockItem(+e.target.dataset.sidx); });

  /* Detail: Partien eines Artikels */
  const dlgSA = $('#dlg-stock-item');
  function openStockIncoming(idx) {
    const a = stockItems()[idx];
    if (!a) return;
    $('#stock-item-body').innerHTML = `<div class="dlg-head"><div><h2 id="sa-title">Erwartete Zugänge</h2><p>${esc(a.code)} · ${esc(a.name)}</p></div><button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body"><p class="hint">Status „erfasst“ · Stand ${stock.date ? esc(dmy(stock.date)) : 'unbekannt'} · noch nicht im eingelagerten Bestand enthalten.</p>${incomingHTML(a)}</div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Schließen</button></div>`;
    dlgSA.showModal();
  }
  /* Partien eines Artikels mit Summe (Kolli, Kg netto) und – mit Recht „bestand.einkaufspreise“ – EK-Preis je Partie.
     In der Summenzeile steht beim EK der nach kg gewichtete Durchschnitt der Partien mit Preis. */
  const eur = (v) => fmtKg.format(Math.round(v * 100) / 100) + ' €';
  function lotTableHTML(lots) {
    const mitEk = may('bestand.einkaufspreise');
    const kolli = lots.filter((l) => Number.isFinite(l.kolli));
    const ekLots = lots.filter((l) => Number.isFinite(l.ek) && Number.isFinite(l.kg) && l.kg > 0);
    const ekKg = ekLots.reduce((t, l) => t + Math.round(l.kg * 1000), 0);
    const ekAvg = ekKg ? ekLots.reduce((t, l) => t + l.ek * Math.round(l.kg * 1000), 0) / ekKg : null;
    const mitMarke = lots.some((l) => l.marke);   // Bestand vor der Marken-Spalte: Spalte weglassen
    const row = (l) => `<tr>${mitMarke ? `<td class="lot-marke">${l.marke ? esc(l.marke) : '<span class="muted">—</span>'}</td>` : ''}<td class="ch-code">${esc(l.lot || '—')}${mitMarke && l.marke ? `<small class="lot-marke-sub">${esc(l.marke)}</small>` : ''}</td><td class="lot-ank">${l.arrival ? esc(dmy(l.arrival)) : '—'}</td><td class="${mhdClass(l.mhd)}">${l.mhd ? esc(dmy(l.mhd)) : '<span class="muted">ohne MHD</span>'}</td><td class="num">${l.kolli == null ? '—' : esc(fmtInt.format(l.kolli))}</td><td class="num">${esc(kgText(l.kg))}</td>${mitEk ? `<td class="num lot-ek">${Number.isFinite(l.ek) ? esc(eur(l.ek)) : '<span class="muted">—</span>'}</td>` : ''}</tr>`;
    return `<div class="lot-scroll"><table class="etab lottab"><thead><tr>${mitMarke ? '<th class="lot-marke">Marke</th>' : ''}<th>Partie</th><th class="lot-ank">Ankunft</th><th>MHD</th><th class="num">Kolli</th><th class="num">Kg netto</th>${mitEk ? '<th class="num" title="Einkaufspreis je kg">EK-Preis</th>' : ''}</tr></thead><tbody>
          ${lots.map(row).join('')}
        </tbody>${lots.length ? `<tfoot><tr class="lot-sum">${mitMarke ? '<td class="lot-marke"></td>' : ''}<td>Summe</td><td class="lot-ank"></td><td></td><td class="num">${kolli.length ? esc(fmtInt.format(sum(kolli, 'kolli'))) : '—'}</td><td class="num">${esc(kgText(sum(lots, 'kg')))}</td>${mitEk ? `<td class="num" title="nach kg gewichteter Durchschnitt">${ekAvg == null ? '<span class="muted">—</span>' : 'Ø ' + esc(eur(ekAvg))}</td>` : ''}</tr></tfoot>` : ''}</table></div>
        ${mitEk && lots.length && !ekLots.length ? '<p class="hint" style="margin:6px 0 0">EK-Preise erscheinen ab der nächsten hochgeladenen Bestandsliste (Spalte „Preis“/„EKPreis“).</p>' : ''}`;
  }
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
          <div><span>Eingelagerter Bestand</span><strong>${a.kg == null ? '—' : esc(kgText(a.kg))}</strong></div>
          <div><span>Kürzestes MHD</span><strong class="${a.cls}">${esc(mhdShort(a.mhd))}</strong></div>
          <div><span>Kg kürz. MHD</span><strong class="${a.cls}">${mhdKgHTML(a)}</strong></div>
          <div><span>Aktuell ${esc(stockWeekLabel('current'))}</span><strong>${esc(stockPriceText(a.price))}</strong></div>
          <div><span>Vorwoche ${esc(stockWeekLabel('previous'))}</span><strong>${esc(stockPriceText(a.prevPrice))}</strong></div>
          <div><span>Erfasster Bestand</span><strong>${esc(kgText(a.incomingKg))}</strong></div><div><span>Gesamt verfügbar</span><strong>${esc(kgText(a.totalKg))}</strong></div>
        </div>
        <h3 class="d-h"><span>Erwartete Zugänge (Status „erfasst“)</span></h3>${incomingHTML(a)}
        <h3 class="d-h"><span>Eingelagerte Partien</span><span>${plural(a.lots.length, 'Partie', 'Partien')}</span></h3>
        ${lotTableHTML(a.lots)}
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

  /* Bestandsliste lesen (Leser des Moduls Bestand: stock-core.js) – hier und in der Importzentrale */
  async function stockAusDatei(file) {
    if (file.size > 30 * 1024 * 1024) throw new Error('Die Datei ist größer als 30 MB.');
    const r = S.parseStockWorkbook(await S.readStockWorkbook(await file.arrayBuffer()), file.name);
    if (!r.articles.length && !r.incoming.length) throw new Error('Keine eingelagerten Partien oder erwarteten Zugänge gefunden.');
    return r;
  }

  /* Bestandsliste hochladen */
  const dlgSI = $('#dlg-stock-import');
  let stockPending = null;
  $('#stock-file-input').addEventListener('change', (e) => { const f = e.target.files[0]; e.target.value = ''; if (f) stockImportFile(f); });
  async function stockImportFile(file) {
    if (roStock) return;
    stockPending = null;
    const head = (t, sub) => `<div class="dlg-head"><div><h2 id="si-title">${t}</h2>${sub ? `<p>${sub}</p>` : ''}</div><button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>`;
    $('#stock-import-body').innerHTML = `${head('Bestandsliste', esc(file.name))}<div class="dlg-body"><div class="loading"><div class="spinner"></div>Datei wird gelesen …</div></div>`;
    if (!dlgSI.open) dlgSI.showModal();
    try {
      const r = await stockAusDatei(file);
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
            <li class="info"><span class="lvl">Info</span><span>Berücksichtigt: ${fmtInt.format(r.stats.stored)} Partien mit Status „eingelagert“ und ${fmtInt.format(r.stats.expected)} erwartete Zugänge mit Status „erfasst“ (separat, nicht im Bestand).${other ? ` Nicht berücksichtigt: ${other}.` : ''}</span></li>
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
      const r = await api('stock_import', { body: { date, source: stockPending.source, articles: stockPending.articles, incoming: stockPending.incoming } });
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
    const lines = [['Art.-Nr.', 'Bezeichnung', `Aktuell ${stockWeekLabel('current')}`, `Vorwoche ${stockWeekLabel('previous')}`, 'Eingelagerter Bestand kg', 'Kürz. MHD', 'Kg kürz. MHD', 'Erfasster Bestand kg', 'Gesamt verfügbar kg', 'Erwartete Zugänge (Menge kg / ETA / Partie)', 'Warengruppe', 'Bestand vom'].map(q).join(';')];
    for (const a of res.list) lines.push([a.code, a.name, stockPriceText(a.price), stockPriceText(a.prevPrice), n2(a.kg), mhdShort(a.mhd).replace('—', ''), n2(a.mhdKg), n2(a.incomingKg), n2(a.totalKg), a.incoming.map((d) => `${n2(d.kg)} kg / ${d.arrival ? dmy(d.arrival) : 'ETA unbekannt'} / ${d.lot || '—'}`).join(' | '), a.wg.label, stock.date ? dmy(stock.date) : ''].map(q).join(';'));
    const blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const el = document.createElement('a');
    el.href = URL.createObjectURL(blob);
    el.download = `Bestand_${stock.date || isoToday()}${isMhdQuery(stockQ) ? '_MHD' : stockQ ? '_Auswahl' : ''}.csv`;
    document.body.appendChild(el); el.click(); el.remove();
    setTimeout(() => URL.revokeObjectURL(el.href), 2000);
  }
  /* PDF zum Weitergeben (Server, lib/bestand-pdf.php): nur Art.-Nr., Bezeichnung, eingelagerter Bestand, kürzestes MHD,
     Kg kürz. MHD – ohne Preise, erfassten Bestand, Gesamt verfügbar und Zugänge. Auswahl, Reihenfolge und Gruppen wie
     angezeigt; die Mengen nimmt der Server aus dem gespeicherten Bestand. */
  async function stockPDF(btn) {
    const res = stockResult(stockQ);
    const rows = [];
    if (res.flat) for (const a of res.list) rows.push({ c: a.code });
    else for (const g of res.groups) { rows.push({ g: g.label }); for (const a of g.items) rows.push({ c: a.code }); }
    if (btn) btn.disabled = true;
    try {
      const r = await fetch(API + '?action=stock_pdf', { method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf || '' }, body: JSON.stringify({ rows, q: isMhdQuery(stockQ) ? '' : stockQ, mhd: isMhdQuery(stockQ) }) });
      if (r.status === 401) { showAuth('expired'); return; }
      if (!r.ok || !(r.headers.get('Content-Type') || '').includes('application/pdf')) {
        let msg = `PDF konnte nicht erstellt werden (${r.status}).`;
        try { const j = await r.json(); if (j.error) msg = j.error; } catch { /* keine JSON-Antwort */ }
        throw new Error(msg);
      }
      const name = (/filename="([^"]+)"/.exec(r.headers.get('Content-Disposition') || '') || [])[1] || `Bestand_${stock.date || isoToday()}.pdf`;
      const url = URL.createObjectURL(await r.blob());
      const el = document.createElement('a');
      el.href = url; el.download = name;
      document.body.appendChild(el); el.click(); el.remove();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
      toast(`PDF „${name}“ erstellt.`);
    } catch (e) {
      toast(e.message || 'PDF konnte nicht erstellt werden.');
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  /* Druck / PDF (DIN A4) */
  function printStock() {
    const res = stockResult(stockQ);
    const w = window.open('', '_blank');
    if (!w) { toast('Druckfenster wurde blockiert – bitte Pop-ups für diese Seite erlauben.'); return; }
    const title = `Bestand vom ${stock.date ? dmy(stock.date) : '?'}${isMhdQuery(stockQ) ? ` – MHD bis ${dmy(isoToday(14))}` : stockQ ? ` – Suche „${stockQ}“` : ''}`;
    w.document.write(`<!doctype html><html lang="de"><head><meta charset="utf-8"><title>${esc(title)}</title><style>
      @page { size: A4 landscape; margin: 10mm; }
      * { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      body { font: 9.5pt/1.3 -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: #1b1a18; margin: 0; }
      h1 { font-size: 13pt; margin: 0 0 2px; } .meta { color: #666; font-size: 8.5pt; margin: 0 0 8px; }
      table { width: 100%; border-collapse: collapse; } th, td { padding: 2.5px 5px; border-bottom: .5pt solid #ddd; }
      th { font-size: 8pt; text-align: center; vertical-align: bottom; border-bottom: 1pt solid #999; }
      td.s-name { white-space: normal; } .st-incoming { margin:0; padding-left:12px; } .st-price-change.up { color:#b91c1c; } .st-price-change.down { color:#15803d; } .s-code { width: 44px; } .s-vk, .s-prev, .s-kg, .s-mkg, .s-registered, .s-total-kg { text-align: right; white-space: nowrap; } .s-mhd { text-align: center; white-space: nowrap; }
      .s-mkg { font-weight: 700; } thead { display: table-header-group; } tr { break-inside: avoid; }
      .wg-h td { font-weight: 700; padding-top: 8px; border-bottom: 1pt solid #999; } .wg-sum td, .st-total td { font-weight: 700; background: #f3f1ee; }
      .wg-gap td { border: 0; height: 6px; padding: 0; } .st-total td { border-top: 1.5pt solid #333; }
      .mhd-past { background: #d9d6d2; color: #1f1d1a; } .mhd-0-4 { background: #fbe0dd; color: #8f1d14; } .mhd-5-7 { background: #fde7d3; color: #7a3209; } .mhd-8-14 { background: #fbf0c9; color: #6b4a05; } .mhd-past, .mhd-0-4, .mhd-5-7, .mhd-8-14 { font-weight: 700; } .mhd-skull { font-size: 1.15em; margin-right: 3px; }
    </style></head><body><h1>${esc(company ? company + ' · ' : '')}${esc(title)}</h1>
      <p class="meta">${fmtInt.format(res.list.length)} Artikel · Bestand und erwartete Zugänge getrennt · Standardpreise ${esc(stockWeekLabel('current'))} / ${esc(stockWeekLabel('previous'))} · gedruckt ${esc(dateTime(new Date().toISOString()))} · intern – nicht zur Weitergabe</p>
      ${stockTableHTML(res, true).replace(/ tabindex="0"/g, '').replace(/<button[^>]*>/g, '').replace(/<\/button>/g, '')}
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
    await Promise.all([may('bestand.sehen') ? loadStock().catch(() => {}) : Promise.resolve(), loadPrev().catch(() => {})]);
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
      restBusy = true; dlgRest.dataset.busy = '1'; restCount();
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
      restBusy = false; delete dlgRest.dataset.busy; restCount();
      toast(badN ? `${okN} gesendet, ${badN} nicht zugestellt.` : `Sonderposten an ${plural(okN, 'Kunden', 'Kunden')} gesendet.`, 6000);
    }
  });

  /* ======================= Stammdaten (je Artikelnummer) ======================= */
  let master = null, masterLoading = null, masterQ = '', masterTimer = null, masterSaving = false, masterQueued = false, masterErr = null;
  let vkg = [], vkgMap = new Map(), masterVk = '';   // VK-Gruppen (Stammdaten → VK-Gruppen), Filter in der Artikelliste
  async function loadVkGruppen() {
    try { vkg = (await api('vkgruppen')).groups || []; } catch { vkg = []; }
    vkgMap = new Map(vkg.map((g) => [g.nr, g]));
    const dl = $('#dl-vkgruppen');
    if (dl) dl.innerHTML = vkg.map((g) => `<option value="${esc(g.nr)}">${esc(g.name)}</option>`).join('');
  }
  const vkName = (nr) => (nr && vkgMap.get(nr) ? vkgMap.get(nr).name : '');
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
    if (roMaster || !master || !master.articles.length || !model) return 0;
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
    if (roMaster || !master) return;
    if (masterSaving) { masterQueued = true; return; }
    masterSaving = true;
    setMasterState('saving');
    try {
      const r = await api('master_save', { body: { rev: master.rev, articles: master.articles } });
      master.rev = r.rev; master.updatedAt = r.updatedAt; masterErr = null;
      setMasterState('saved');
    } catch (e) {
      masterErr = e.message; setMasterState('error', e.message);
      if (e.status === 409) {   // jemand anderes hat gespeichert: aktuellen Stand laden statt endlos mit altem Stand zu scheitern
        masterErr = null;
        try { await loadMaster(true); toast('Die Stammdaten wurden inzwischen an anderer Stelle geändert – der aktuelle Stand wurde geladen. Bitte die letzte Änderung prüfen.', 8000); if (currentView === 'master') renderMasterView(); } catch { /* bleibt beim Fehlerhinweis */ }
      }
    }
    finally { masterSaving = false; if (masterQueued) { masterQueued = false; saveMaster(); } }
  }
  function offerStatus(e, by) {
    const list = by.get(mKey(e.code));
    if (!list) return '<span class="muted" title="Nicht im aktuellen Angebot">—</span>';
    if (list.length > 1) return `<span class="muted" title="Artikelnummer ${list.length}× im Angebot – wird nicht automatisch abgeglichen">${list.length}× im Angebot</span>`;
    if (differs(e, list[0])) return (ro || roMaster) ? '<span class="m-diff">abweichend</span>' : `<button type="button" class="m-diff" data-ma="apply1" title="Angebot: ${esc(list[0].name)} · ${esc(list[0].category)} · ${esc(list[0].origin || '–')} · ${esc(C.CONDITION_LABELS[list[0].condition])} – klicken, um die Stammdaten zu übernehmen">abweichend</button>`;
    return `<span class="m-ok" title="Angebot entspricht den Stammdaten">${icon('check', 'sm')}</span>`;
  }
  async function renderMasterView() {
    const host = $('#view-master');
    if (!master) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Stammdaten werden geladen …</div>';
    try { await loadMaster(); await Promise.all([loadStock().catch(() => {}), loadVkGruppen()]); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    migrateMaster();
    if (!roMaster && !master.articles.length && model && model.items.length) {
      const n = addFromDraft();
      if (n) { saveMaster(); toast(`Stammdaten angelegt: ${plural(n, 'Artikel', 'Artikel')} aus dem aktuellen Angebot übernommen.`, 5000); }
    }
    const by = draftByCode();
    const dup = [...by.values()].filter((l) => l.length > 1).length;
    const missing = [...by.entries()].filter(([k, l]) => l.length === 1 && !masterOf(k)).length;
    const dev = master.articles.filter((e) => { const l = by.get(mKey(e.code)); return l && l.length === 1 && differs(e, l[0]); }).length;
    host.innerHTML = `
      <div class="st-info">
        <div><strong>Stammdaten</strong><span class="sub">Bezeichnung, Fleischart, Herkunft, Zustand und VK-Gruppe je Artikelnummer – werden beim Excel-Import automatisch übernommen. „frisch“ gehört in den Zustand, nicht in die Bezeichnung.</span></div>
        <span class="ms-state" id="ms-state"></span>
      </div>
      <div class="ed-toolbar">
        <div class="search">${icon('search')}<input id="ms-q" type="search" autocomplete="off" placeholder="Nummer, Bezeichnung, Herkunft …" aria-label="Stammdaten durchsuchen" value="${esc(masterQ)}"></div>
        <label class="select ms-vk"><span class="sr-only">VK-Gruppe</span><select id="ms-vk" aria-label="Nach VK-Gruppe filtern">${vkFilterOpts()}</select>${icon('chev', 'sm')}</label>
        <span class="ed-hint" id="ms-count"></span>
        ${roMaster ? '' : `<span class="st-actions">
          <button type="button" class="btn" data-ma="import" title="Artikelstammdaten-Export der Warenwirtschaft (CSV) einlesen: neue Artikel, VK-Gruppe und GTIN">${icon('upload')}CSV importieren</button><input type="file" id="ms-file" accept=".csv,text/csv,text/plain" hidden>
          <button type="button" class="btn" data-ma="from-draft"${missing ? '' : ' disabled'} title="Artikelnummern aus dem Angebot, die noch keine Stammdaten haben">${icon('plus')}Aus Angebot ergänzen${missing ? ` (${missing})` : ''}</button>
          ${ro ? '' : `<button type="button" class="btn" data-ma="apply-all"${dev ? '' : ' disabled'} title="Abweichende Artikel im Entwurf an die Stammdaten anpassen">${icon('check')}Auf Angebot anwenden${dev ? ` (${dev})` : ''}</button>`}
          <button type="button" class="btn primary" data-ma="new">${icon('plus')}Artikel anlegen</button>
        </span>`}
      </div>
      ${dup ? `<p class="hint" style="margin:-4px 0 12px">${plural(dup, 'Artikelnummer kommt', 'Artikelnummern kommen')} im Angebot mehrfach vor (verschiedene Artikel unter einer Nummer) und ${dup === 1 ? 'wird' : 'werden'} nicht automatisch abgeglichen.</p>` : ''}
      <div id="ms-list"></div>`;
    setMasterState(masterErr ? 'error' : 'saved', masterErr);
    renderMasterList();
  }
  function vkFilterOpts() {
    const n = new Map();
    let ohne = 0;
    for (const e of master.articles) { if (e.vkGruppe) n.set(e.vkGruppe, (n.get(e.vkGruppe) || 0) + 1); else ohne++; }
    const fremd = [...n.keys()].filter((nr) => !vkgMap.has(nr));
    return `<option value="">Alle VK-Gruppen</option><option value="-"${masterVk === '-' ? ' selected' : ''}>Ohne VK-Gruppe (${fmtInt.format(ohne)})</option>`
      + vkg.map((g) => `<option value="${esc(g.nr)}"${masterVk === g.nr ? ' selected' : ''}>${esc(g.nr)} · ${esc(g.name)} (${fmtInt.format(n.get(g.nr) || 0)})</option>`).join('')
      + fremd.map((nr) => `<option value="${esc(nr)}"${masterVk === nr ? ' selected' : ''}>${esc(nr)} · nicht in der Liste (${fmtInt.format(n.get(nr))})</option>`).join('');
  }
  function renderMasterList() {
    const host = $('#ms-list');
    if (!host || !master) return;
    const toks = fold(masterQ).split(/\s+/).filter(Boolean);
    const list = master.articles.filter((e) => {
      if (masterVk && (masterVk === '-' ? e.vkGruppe : e.vkGruppe !== masterVk)) return false;
      if (!toks.length) return true;
      const h = fold([e.code, e.name, e.origin, e.category, C.CONDITION_LABELS[e.condition], e.vkGruppe, vkName(e.vkGruppe), e.gtin].join(' '));
      return toks.every((t) => h.includes(t));
    });
    $('#ms-count').textContent = `${fmtInt.format(list.length)} von ${plural(master.articles.length, 'Artikel', 'Artikeln')}${list.length > 1500 ? ' – die ersten 1.500 angezeigt, Suche oder VK-Gruppe eingrenzen' : ''}`;
    const by = draftByCode();
    const rows = list.slice(0, 1500).map((e) => {
      const st = stockOf(e.code);
      return `<tr data-mcode="${esc(e.code)}">
        <td class="m-code">${esc(e.code)}</td>
        <td class="m-name"><input class="in" data-mf="name" value="${esc(e.name)}" maxlength="200" aria-label="Bezeichnung">${st && fold(st.name) !== fold(e.name) ? `<div class="m-winab" title="Bezeichnung in WinAB / Bestandsliste">WinAB: ${esc(st.name)}</div>` : ''}</td>
        <td class="m-cat"><select class="in" data-mf="category" aria-label="Fleischart">${CAT_OPTS(e.category)}</select></td>
        <td class="m-origin"><input class="in" data-mf="origin" value="${esc(e.origin || '')}" list="dl-origins" placeholder="nicht angegeben" maxlength="60" aria-label="Herkunft"></td>
        <td class="m-cond"><select class="in" data-mf="condition" aria-label="Zustand">${COND_OPTS(e.condition)}</select></td>
        <td class="m-vk"><input class="in" data-mf="vkGruppe" value="${esc(e.vkGruppe || '')}" list="dl-vkgruppen" placeholder="–" maxlength="10" aria-label="VK-Gruppe"><div class="m-vkname${e.vkGruppe && !vkName(e.vkGruppe) ? ' st-warn' : ''}">${e.vkGruppe ? esc(vkName(e.vkGruppe) || 'nicht in der Liste') : ''}</div></td>
        <td class="m-offer">${offerStatus(e, by)}</td>
        <td class="m-act">${roMaster ? '' : `<button type="button" class="ibtn danger" data-ma="del" aria-label="Stammsatz ${esc(e.code)} löschen">${icon('trash')}</button>`}</td>
      </tr>`;
    }).join('');
    host.innerHTML = list.length ? `<div class="gcard"><table class="etab mtab"><thead><tr><th class="m-code">Art.-Nr.</th><th class="m-name">Bezeichnung</th><th class="m-cat">Fleischart</th><th class="m-origin">Herkunft</th><th class="m-cond">Zustand</th><th class="m-vk">VK-Gruppe</th><th class="m-offer">Angebot</th><th class="m-act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${rows}</tbody></table></div>`
      : `<div class="ed-empty"><h3>${master.articles.length ? 'Keine Treffer' : 'Noch keine Stammdaten'}</h3><p>${master.articles.length ? 'Suchbegriff anpassen.' : 'Mit „Aus Angebot ergänzen“ oder „Artikel anlegen“ beginnen.'}</p></div>`;
    lockInputs(host);
  }
  $('#view-master').addEventListener('input', (e) => {
    if (e.target.id === 'ms-q') { clearTimeout(qTimer); qTimer = setTimeout(() => { masterQ = e.target.value.trim(); renderMasterList(); }, 120); }
  });
  $('#view-master').addEventListener('change', (e) => {
    if (e.target.id === 'ms-vk') { masterVk = e.target.value; renderMasterList(); return; }
    if (e.target.id === 'ms-file' && e.target.files[0]) { const f = e.target.files[0]; e.target.value = ''; masterImportDatei(f); return; }
    const el = e.target, tr = el.closest('tr[data-mcode]');
    if (!tr || !el.dataset.mf || roMaster) return;
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
    else if (f === 'vkGruppe') {
      const nr = el.value.trim();
      if (nr && (!/^[0-9A-Za-z._-]{1,10}$/.test(nr) || (vkg.length && !vkgMap.has(nr)))) { el.value = ent.vkGruppe || ''; toast(`Die VK-Gruppe „${nr}“ gibt es nicht. Bitte unter Stammdaten → VK-Gruppen anlegen.`, 6000); return; }
      if (nr) ent.vkGruppe = nr; else delete ent.vkGruppe;
      el.value = nr;
      const nm = tr.querySelector('.m-vkname'); nm.textContent = nr ? vkName(nr) || 'nicht in der Liste' : ''; nm.classList.toggle('st-warn', !!nr && !vkName(nr));
    }
    else ent[f] = el.value;
    tr.querySelector('.m-offer').innerHTML = offerStatus(ent, draftByCode());
    masterChanged();
  });
  $('#view-master').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-ma]');
    if (!b || roMaster) return;
    const a = b.dataset.ma, code = b.closest('tr[data-mcode]')?.dataset.mcode;
    if (a === 'retry') { saveMaster(); return; }
    if (a === 'import') { $('#ms-file').click(); return; }
    if (a === 'from-draft') { const n = addFromDraft(); saveMaster(); toast(`${plural(n, 'Artikel', 'Artikel')} aus dem Angebot ergänzt.`); renderMasterView(); return; }
    if ((a === 'apply-all' || a === 'apply1') && ro) return;   // Entwurf darf nicht bearbeitet werden
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

  /* Artikelstammdaten-Export der Warenwirtschaft (CSV) einlesen. Übernommen werden Nummer, Bezeichnung1 (neue Artikel;
     Fleischart, Zustand und Herkunft werden aus Bezeichnung, Bezeichnung2 und VK-Gruppe vorgeschlagen), VK-Gruppe (Spalte
     „VGrp“) und GTIN. Gepflegte Bezeichnungen und Merkmale bestehender Artikel bleiben unverändert; Artikel, die nicht in der
     Datei stehen, bleiben erhalten. EK, Bestand, Umsatz und Lieferant werden bewusst nicht übernommen (keine Stammdaten). */
  const dlgMI = $('#dlg-ms-import');
  function masterAusCsv(buf) {
    const rows = window.WA.csvZeilen(window.WA.csvText(buf));
    if (!rows.length) throw new Error('Die Datei ist leer.');
    const kopf = rows[0].map((c) => fold(c).replace(/[^a-z0-9]/g, ''));
    const sp = (...n) => kopf.findIndex((k) => n.includes(k));
    const iNr = sp('nummer', 'artikelnummer', 'artnr'), iName = sp('bezeichnung1', 'bezeichnung'), iName2 = sp('bezeichnung2'), iVk = sp('vgrp', 'vkgruppe', 'vkgrp'), iGtin = sp('gtin', 'ean');
    if (iNr < 0 || iName < 0) throw new Error('Spalten „Nummer“ und „Bezeichnung1“ nicht gefunden. Erwartet wird der Artikelstammdaten-Export der Warenwirtschaft (Semikolon getrennt).');
    if (iVk < 0 && kopf.includes('klasse')) throw new Error('Das ist eine Gruppenliste. VK-Gruppen bitte unter Stammdaten → VK-Gruppen importieren.');
    const out = [], fehler = [], seen = new Set(), fehlerZeilen = [];   // fehlerZeilen: je Zeile für die Importzentrale
    let ohneName = 0, doppelt = 0;
    rows.slice(1).forEach((r, i) => {
      const code = (r[iNr] || '').trim();
      const name = C.clean(r[iName] || '');
      const zeile = i + 2;
      if (!code) return;
      if (!/^[0-9A-Za-z./-]{1,20}$/.test(code)) { fehler.push(code); fehlerZeilen.push({ zeile, schluessel: code, text: 'keine gültige Artikelnummer – übersprungen' }); return; }   // z. B. Kostenkonten („wek 19%“)
      if (!name || !/[A-Za-zÄÖÜäöüß]/.test(name)) { ohneName++; fehlerZeilen.push({ zeile, schluessel: code, text: 'Bezeichnung fehlt – übersprungen' }); return; }
      const k = mKey(code);
      if (seen.has(k)) { doppelt++; fehlerZeilen.push({ zeile, schluessel: code, text: 'Artikelnummer steht mehrfach in der Datei – nur die erste Zeile zählt' }); return; }
      seen.add(k);
      const vk = iVk >= 0 ? (r[iVk] || '').trim() : '', gtin = iGtin >= 0 ? (r[iGtin] || '').replace(/\s+/g, '') : '';
      out.push({ code, name, name2: iName2 >= 0 ? C.clean(r[iName2] || '') : '', vkGruppe: /^[0-9A-Za-z._-]{1,10}$/.test(vk) ? vk : '', gtin: /^\d{8,14}$/.test(gtin) ? gtin : '', zeile });
    });
    if (!out.length) throw new Error('Keine Artikel mit Nummer und Bezeichnung in der Datei gefunden.');
    return { rows: out, fehler, ohneName, doppelt, fehlerZeilen };
  }
  function masterNeuAus(r) {
    const sug = C.suggestAttributes(r.name, [vkName(r.vkGruppe), r.name2].filter(Boolean).join(' '), '');
    const e = { code: r.code, name: r.name, category: sug.category, origin: sug.origin || null, condition: sug.condition };
    C.normalizeItem(e);   // „frisch“ aus der Bezeichnung in den Zustand, Herkunft vereinheitlichen
    const kurz = e.name.replace(/[\s,]+(?:fri|fr)\.?$/, '');   // abgekürztes „frisch“ der Warenwirtschaft („…,Hac.Horiz.,fri“)
    if (kurz !== e.name && kurz.length > 2) { e.name = kurz; if (e.condition === 'unbekannt') e.condition = 'frisch'; }
    if (r.vkGruppe) e.vkGruppe = r.vkGruppe;
    if (r.gtin) e.gtin = r.gtin;
    return e;
  }
  /* Gelesene Zeilen mit den Stammdaten zusammenführen: neue Artikel mit vorgeschlagenen Merkmalen, bestehende nur um
     VK-Gruppe/GTIN ergänzt (leere Felder in der Datei löschen nichts). Liefert auch die vollständige neue Liste –
     dieselbe Regel für den Import hier und in der Importzentrale (dort prüft und vergleicht der Server die Liste). */
  function masterZusammenfuehren(res, basis) {
    const by = new Map();
    for (const e of basis) if (!by.has(mKey(e.code))) by.set(mKey(e.code), e);
    const neu = [], ergaenzt = [];
    let gleich = 0;
    for (const r of res.rows) {
      const ent = by.get(mKey(r.code));
      if (!ent) { neu.push(masterNeuAus(r)); continue; }
      const vk = r.vkGruppe || ent.vkGruppe || '', gtin = r.gtin || ent.gtin || '';
      if (vk !== (ent.vkGruppe || '') || gtin !== (ent.gtin || '')) ergaenzt.push({ ent, vk, gtin }); else gleich++;
    }
    const erg = new Map(ergaenzt.map((x) => [x.ent, x]));
    const articles = basis.map((e) => { const x = erg.get(e); if (!x) return e; const c = { ...e }; if (x.vk) c.vkGruppe = x.vk; if (x.gtin) c.gtin = x.gtin; return c; }).concat(neu);
    articles.sort((a, b) => a.code.localeCompare(b.code, 'de', { numeric: true }));
    return { neu, ergaenzt, gleich, articles };
  }
  const masterFremdeVk = (res) => {
    const fremd = new Map();
    if (vkg.length) for (const r of res.rows) if (r.vkGruppe && !vkgMap.has(r.vkGruppe)) fremd.set(r.vkGruppe, (fremd.get(r.vkGruppe) || 0) + 1);
    return fremd;
  };
  async function masterImportDatei(file) {
    let res;
    try { await loadVkGruppen(); res = masterAusCsv(await file.arrayBuffer()); } catch (ex) { toast(ex.message, 8000); return; }
    const { neu, ergaenzt, gleich } = masterZusammenfuehren(res, master.articles);
    const inDatei = new Set(res.rows.map((r) => mKey(r.code)));
    const nichtInDatei = master.articles.filter((e) => !inDatei.has(mKey(e.code))).length;
    const fremd = masterFremdeVk(res);
    const mitVk = res.rows.filter((r) => r.vkGruppe).length;
    const nix = !neu.length && !ergaenzt.length;
    const li = (l, f) => l.slice(0, 8).map(f).join('') + (l.length > 8 ? `<li class="muted">… und ${fmtInt.format(l.length - 8)} weitere</li>` : '');
    $('#ms-import-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="msi-title">Artikelstammdaten importieren</h2><p>${esc(file.name)} · ${plural(res.rows.length, 'Artikel', 'Artikel')} · ${fmtInt.format(mitVk)} mit VK-Gruppe</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        <div class="cmp-stats"><div><span>Neu</span><strong id="msi-neu">${fmtInt.format(neu.length)}</strong></div><div><span>VK-Gruppe/GTIN ergänzt</span><strong id="msi-erg">${fmtInt.format(ergaenzt.length)}</strong></div><div><span>Unverändert</span><strong id="msi-gleich">${fmtInt.format(gleich)}</strong></div></div>
        ${!vkg.length ? '<p class="hint st-warn">Die VK-Gruppen-Liste ist noch leer. Am besten zuerst unter Stammdaten → VK-Gruppen die Liste importieren – dann helfen die Gruppennamen beim Vorschlag von Fleischart, Herkunft und Zustand.</p>' : ''}
        ${neu.length ? `<h3 class="d-h"><span>Neu – Merkmale vorgeschlagen, danach in der Liste prüfbar</span></h3><ul class="kg-prev">${li(neu, (e) => `<li><span class="muted">${esc(e.code)}</span> ${esc(e.name)} <span class="muted">· ${esc(e.category)} · ${esc(C.CONDITION_LABELS[e.condition] || e.condition)}${e.origin ? ' · ' + esc(e.origin) : ''}${e.vkGruppe ? ' · ' + esc(vkName(e.vkGruppe) || 'VK ' + e.vkGruppe) : ''}</span></li>`)}</ul>` : ''}
        ${ergaenzt.length ? `<h3 class="d-h"><span>Bestehende Artikel – VK-Gruppe/GTIN</span></h3><ul class="kg-prev">${li(ergaenzt, (x) => `<li><span class="muted">${esc(x.ent.code)}</span> ${esc(x.ent.name)} <span class="muted">· ${esc(vkName(x.vk) || (x.vk ? 'VK ' + x.vk : ''))}</span></li>`)}</ul>` : ''}
        <p class="hint">Bezeichnung, Fleischart, Herkunft und Zustand bestehender Artikel bleiben unverändert.${nichtInDatei ? ` ${plural(nichtInDatei, 'Artikel steht', 'Artikel stehen')} nicht in der Datei und ${nichtInDatei === 1 ? 'bleibt' : 'bleiben'} erhalten.` : ''} EK, Bestand, Umsatz und Lieferant werden nicht übernommen.</p>
        ${fremd.size ? `<p class="hint st-warn">VK-Gruppe nicht in der Liste: ${esc([...fremd].slice(0, 8).map(([nr, n]) => `${nr} (${n})`).join(', '))}${fremd.size > 8 ? ' …' : ''} – wird trotzdem eingetragen; bitte unter Stammdaten → VK-Gruppen ergänzen.</p>` : ''}
        ${res.ohneName || res.doppelt || res.fehler.length ? `<p class="hint" id="msi-skip">Übersprungen: ${[res.ohneName ? plural(res.ohneName, 'Zeile', 'Zeilen') + ' ohne Bezeichnung' : '', res.doppelt ? `${res.doppelt}× doppelte Nummer` : '', res.fehler.length ? `${res.fehler.length}× keine gültige Artikelnummer (${esc(res.fehler.slice(0, 5).join(', '))}${res.fehler.length > 5 ? ' …' : ''})` : ''].filter(Boolean).join(' · ')}</p>` : ''}
        ${nix ? '<p class="hint">Keine Änderungen – die Stammdaten sind bereits aktuell.</p>' : ''}
        <p class="kerr" id="msi-err" role="alert"></p>
      </div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="button" class="btn primary" id="msi-ok"${nix ? ' disabled' : ''}>${icon('check')}Übernehmen</button></div>`;
    dlgMI.showModal();
    $('#msi-ok').onclick = async () => {
      $('#msi-ok').disabled = true;
      const vorher = master.articles;
      master.articles = masterZusammenfuehren(res, master.articles).articles;   // auf den Stand beim Klick anwenden
      clearTimeout(masterTimer);
      while (masterSaving) await new Promise((r) => setTimeout(r, 100));
      await saveMaster();
      if (masterErr) { const msg = masterErr; master.articles = vorher; masterErr = null; setMasterState('saved'); $('#msi-err').textContent = msg; $('#msi-ok').disabled = false; return; }
      dlgMI.close();
      toast(`Artikelstammdaten übernommen: ${fmtInt.format(neu.length)} neu, ${fmtInt.format(ergaenzt.length)} ergänzt.`, 5000);
      renderMasterView();
    };
  }
  $('#ms-import-body').addEventListener('click', (e) => { if (e.target.closest('[data-close]')) dlgMI.close(); });

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
    if (roMaster || !it.code) return;
    try { await loadMaster(); } catch (e) { toast(e.message); return; }
    const ent = masterOf(it.code);
    const rec = { code: ent ? ent.code : it.code, name: C.stripFrisch(it.name), category: it.category, origin: it.origin || null, condition: it.condition };
    if (ent) Object.assign(ent, rec); else { master.articles.push(rec); master.articles.sort((x, y) => x.code.localeCompare(y.code, 'de', { numeric: true })); }
    await saveMaster();
    toast(masterErr ? `Nicht gespeichert: ${masterErr}` : `Stammdaten für ${it.code} ${ent ? 'aktualisiert' : 'angelegt'}.`);
  }

  /* ======================= Schnittstelle für admin-verwaltung.js ======================= */
  /* Leser für die Importzentrale (admin-import.js): die Dateien liest weiter der Leser des Daten-Eigentümers, der hier
     schon für den Import an Ort und Stelle läuft. lesen(dateien) → { daten (an den Server), zeilen, fehler, hinweise,
     optionen }; nachher() leert zwischengespeicherte Stände nach der Übernahme. Vertrag: docs/plattform/schnittstellen/import.md */
  const IMPORT_LESER = {
    stammdaten: {
      async lesen([file]) {
        const [m] = await Promise.all([api('master'), loadVkGruppen()]);
        const basis = m.master || { rev: 0, articles: [] };
        const res = masterAusCsv(await file.arrayBuffer());
        const z = masterZusammenfuehren(res, basis.articles || []);
        const fremd = [...masterFremdeVk(res)];
        const hinweise = [];
        if (!vkg.length) hinweise.push({ stufe: 'warn', text: 'Die VK-Gruppen-Liste ist noch leer. Am besten zuerst die VK-Gruppen importieren – die Gruppennamen helfen beim Vorschlag von Fleischart, Herkunft und Zustand.' });
        if (fremd.length) hinweise.push({ stufe: 'warn', text: `VK-Gruppe nicht in der Liste: ${fremd.slice(0, 8).map(([nr, n]) => `${nr} (${n})`).join(', ')}${fremd.length > 8 ? ' …' : ''} – wird trotzdem eingetragen; bitte unter Stammdaten → VK-Gruppen ergänzen.` });
        if (z.neu.length) hinweise.push({ stufe: 'info', text: 'Neue Artikel: Fleischart, Herkunft und Zustand werden aus Bezeichnung und VK-Gruppe vorgeschlagen und lassen sich danach unter Stammdaten → Artikelstammdaten prüfen.' });
        return { daten: { rev: basis.rev || 0, articles: z.articles, zeilen: Object.fromEntries(res.rows.map((r) => [r.code, r.zeile])) }, zeilen: res.rows.length, fehler: res.fehlerZeilen, hinweise };
      },
      nachher() { master = null; },
    },
    bestand: {
      async lesen([file]) {
        const r = await stockAusDatei(file);
        const other = Object.entries(r.stats.other).map(([k, v]) => `${fmtInt.format(v)} × „${k}“`).join(', ');
        const hinweise = [];
        if (!r.date) hinweise.push({ stufe: 'warn', text: 'Kein Datum in der Datei gefunden – bitte das Bestandsdatum prüfen.' });
        if (other) hinweise.push({ stufe: 'info', text: `Nicht berücksichtigt (anderer Status): ${other}.` });
        if (r.stats.skipped) hinweise.push({ stufe: 'info', text: `${fmtInt.format(r.stats.skipped)} Zeilen ohne gültige Artikelnummer übersprungen (z. B. „Etiketten“).` });
        if (r.stats.noMhd) hinweise.push({ stufe: 'info', text: `${fmtInt.format(r.stats.noMhd)} eingelagerte Partien ohne MHD – zählen zur verfügbaren Menge, nicht zum kürzesten MHD.` });
        return { daten: { articles: r.articles, incoming: r.incoming }, zeilen: r.stats.rows, fehler: [], hinweise, optionen: { datum: r.date || isoToday() } };
      },
      async nachher() { try { await loadStock(true); stockIdxFor = null; refreshAux(); } catch { /* wird beim nächsten Öffnen geladen */ } },
    },
    preisverlauf: {
      async lesen(files) {
        const wochen = [], fehler = [];
        for (const f of files) {
          try { const w = await histAusDatei(f); wochen.push({ datei: f.name, week: w.week ?? null, year: w.year ?? null, items: w.items }); }
          catch (ex) { fehler.push({ datei: f.name, text: ex.message }); }
        }
        if (!wochen.length) throw new Error(fehler.length === 1 ? `${fehler[0].datei}: ${fehler[0].text}` : 'Keine der Dateien ließ sich als Angebotsliste lesen.');
        return { daten: { wochen }, zeilen: wochen.length, fehler, hinweise: [] };
      },
      nachher() { hist = null; prevKey = ''; },   // Preisverlauf und Vorwochenpreise beim nächsten Öffnen neu laden
    },
  };

  window.WA = {
    importLeser: IMPORT_LESER,
    $, $$, api, esc, icon, toast, confirmBox, dateTime, timeOnly, plural, fold, fmtNum, fmtInt, csvCell, ROLE_LABEL, offerName, offerShort,
    loadOffers, pendingCount, setView, renderWartungBanner, wartungBis, OSTD, may,
    get me() { return me; }, get offers() { return offers; }, get stdPublic() { return stdPublic; },
    get wartungSt() { return wartungSt; }, set wartungSt(v) { wartungSt = v; },
    get wartungEingabe() { return wartungEingabe; }, set wartungEingabe(v) { wartungEingabe = v; },
    views: {},
  };

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
      document.body.classList.toggle('is-test', !!s.testumgebung);   // Kennzeichen „Testumgebung“
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
