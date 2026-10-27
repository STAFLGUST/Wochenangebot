/* STAFL-Plattform · Sicherheit (Modul sicherheit, Oberfläche sicherheit.intern; docs/plattform/modul-sicherheit.md)
   Reiter: Lagebild (mit Wochenbericht und Bereitschaft), Notfall (mit Leitfaden und Probealarm), Firewall & Sperren,
   Anmeldung & Sitzungen, Dateiprüfung, Ereignisse, Einstellungen & Vorlagen, Konten (privilegierte und ungenutzte), System
   (Betrieb, Wartung, Module und Freigaben, Diagnose – bis 27.10.2026 Verwaltung → System). Hauptansichten zeigen Lage, Listen und Zustände; Details, Bearbeiten und Bestätigungen öffnen sich in
   einem Dialog (#sic-dlg, nie verschachtelt; mehrstufige Vorgänge ersetzen seinen Inhalt). Alle Rechte prüft der Server bei
   jeder Aktion (GR-103) – ausgeblendete Reiter und Knöpfe sind nur Anzeige. Bestätigung sensibler Aktionen: auf Keycloak-Hosts
   erneute Anmeldung (reauth_required, Rücksprung hierher), sonst Passwort im Dialog (confirmation_required → reauth).
   Kein Inline-Skript (Content-Security-Policy); Texte vom Server immer über esc(). */
'use strict';
(() => {
  const API = '../../api/';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (n, k = '') => `<svg class="i${k ? ' ' + k : ''}" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const fmtInt = new Intl.NumberFormat('de-DE');
  const zahl = (n) => fmtInt.format(+n || 0);
  const plural = (n, a, b) => `${zahl(n)} ${n === 1 ? a : b}`;
  const datum = (s) => { const d = new Date(s); return isNaN(d) ? '' : d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' }); };
  const zeit = (s) => { const d = new Date(s); return isNaN(d) ? '' : d.toLocaleString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }); };
  const uhr = (s) => { const d = new Date(s); return isNaN(d) ? '' : d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }); };
  const sekZeit = (t) => zeit(new Date(t * 1000).toISOString());
  const sekUhr = (t) => new Date(t * 1000).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const ECHT = /(^|\.)dashboard-stafl\.de$/.test(location.hostname);
  const VERWALTUNG = ECHT ? 'https://verwaltung.dashboard-stafl.de/admin/' : '../../admin/';
  if (ECHT) $('#sic-zurueck').href = 'https://dashboard-stafl.de/';
  let regionen = null;
  try { regionen = new Intl.DisplayNames(['de'], { type: 'region' }); } catch { /* alter Browser */ }
  const land = (c) => { let n = ''; try { n = regionen ? regionen.of(c) : ''; } catch { /* unbekannt */ } return n && n !== c ? n : c; };
  const landSort = (a, b) => land(a).localeCompare(land(b), 'de');
  const geraet = (ua) => {
    if (!ua) return '—';
    if (/bot|crawl|spider|curl|python|go-http|wget|scan/i.test(ua)) return ua.slice(0, 40);
    const b = /Edg\//.test(ua) ? 'Edge' : /OPR\//.test(ua) ? 'Opera' : /Firefox\//.test(ua) ? 'Firefox' : /Chrome\//.test(ua) ? 'Chrome' : /Safari\//.test(ua) ? 'Safari' : 'Browser';
    const o = /iPhone|iPad/.test(ua) ? 'iPhone/iPad' : /Android/.test(ua) ? 'Android' : /Windows/.test(ua) ? 'Windows' : /Mac OS X/.test(ua) ? 'Mac' : /Linux/.test(ua) ? 'Linux' : '';
    return o ? `${b} · ${o}` : b;
  };
  const initialen = (n) => { const t = String(n || '').trim().split(/[\s.\-_]+/).filter(Boolean);
    return (t.length > 1 ? t[0][0] + t[1][0] : (t[0] || '?').slice(0, 2)).toLocaleUpperCase('de-DE'); };
  const STUFE = { ok: 'in Ordnung', warn: 'Hinweis', bad: 'kritisch', info: 'Info' };
  const punkt = (l) => `<span class="sic-punkt ${esc(l)}" title="${esc(STUFE[l] || l)}"><span class="sr-only">${esc(STUFE[l] || l)}</span></span>`;
  const DAUER = { 10: '10 Minuten', 60: '1 Stunde', 360: '6 Stunden', 1440: '1 Tag', 10080: '7 Tage' };
  const IDLE = [[15, '15 Minuten'], [30, '30 Minuten'], [60, '1 Stunde'], [120, '2 Stunden'], [240, '4 Stunden'], [480, '8 Stunden'], [720, '12 Stunden']];
  const EUROPA = ['AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI', 'FR', 'GR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT', 'NL', 'PL', 'PT', 'RO', 'SE', 'SI', 'SK', 'CH', 'GB', 'NO', 'IS', 'LI'];
  const IP_RE = /^(\d{1,3}(\.\d{1,3}){3}|[0-9a-f:]*:[0-9a-f:.]+)$/i;
  const NOTFALL_ENTWURF = 'sic-notfall-entwurf';

  const S = { me: null, csrf: '', rechte: {}, lage: null, sec: null, fw: null, datei: null, ev: null, konten: null, system: null, module: null, tab: '',
    fwFilter: '', fwLetzte: 0, fwTimer: 0, evF: { tage: 7, art: '', q: '' }, geo: { sel: new Set(), q: '', ip: null } };

  /* ---------- Schnittstelle ---------- */
  class ApiFehler extends Error { constructor(msg, status, data) { super(msg); this.status = status; this.data = data || {}; } }
  async function api(action, { body = null, query = '' } = {}) {
    let res;
    try {
      res = await fetch(API + '?action=' + action + query, { method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
        headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': S.csrf } : {}, body: body ? JSON.stringify(body) : undefined });
    } catch { throw new ApiFehler('Keine Verbindung zum Server.', 0); }
    let data = null;
    try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
    if (!res.ok || !data || data.ok === false) {
      const d = data || {};
      if (res.status === 401 && !data) { zeigeAnmeldung(); }
      throw new ApiFehler(d.error || `Anfrage fehlgeschlagen (${res.status}).`, res.status, d);
    }
    return data;
  }
  /* Aufruf mit Bestätigung: Passwort im Dialog (Testserver, alter Eingabebereich) bzw. erneute Anmeldung bei Keycloak.
     merken: Entwurf, der nach dem Rücksprung von Keycloak wiederhergestellt wird (nur sessionStorage, keine Geheimnisse). */
  async function aufruf(action, opts = {}, merken = null) {
    try { return await api(action, opts); } catch (e) {
      if (e.data.code === 'reauth_required' && typeof e.data.anmelden === 'string' && e.data.anmelden.startsWith('/oidc/')) {
        if (merken) { try { sessionStorage.setItem(merken[0], JSON.stringify(merken[1])); } catch { /* ohne Speicher: erneut eingeben */ } }
        location.assign(e.data.anmelden + encodeURIComponent(location.href));
        return new Promise(() => {});
      }
      if (e.data.code === 'confirmation_required') {
        if (!(await passwortBestaetigen())) throw new ApiFehler('Abgebrochen.', 0, { abbruch: true });
        return api(action, opts);
      }
      throw e;
    }
  }

  /* ---------- Hinweise, Dialog ---------- */
  let toastZeit = 0;
  function toast(text, fehler = false) {
    const t = $('#sic-toast');
    t.textContent = text; t.className = 'sic-toast zeigen' + (fehler ? ' fehler' : '');
    clearTimeout(toastZeit); toastZeit = setTimeout(() => { t.className = 'sic-toast'; }, fehler ? 4500 : 2400);
  }
  const dlg = $('#sic-dlg');
  let dlgZurueck = null, dlgHandler = null;
  const dKopf = (titel, sub = '', art = '') => `<div class="sic-dkopf${art ? ' ' + art : ''}"><div><h2 id="sic-dlg-titel">${esc(titel)}</h2>${sub ? `<p class="sic-dsub">${sub}</p>` : ''}</div>
    <button type="button" class="sic-rund klein sic-dzu" data-d="zu" aria-label="Schließen">${icon('x')}</button></div>`;
  const dFuss = (html) => `<p class="sic-dfehler" id="d-err" role="alert"></p><div class="sic-dfuss">${html}</div>`;
  /* Dialog öffnen bzw. Inhalt ersetzen (nächster Schritt); Fokus auf das erste Eingabefeld bzw. den Hauptknopf */
  function dialog(html, { breit = false, handler = null, fokus = '' } = {}) {
    if (!dlg.open) dlgZurueck = document.activeElement;
    dlg.className = 'sic-dialog' + (breit ? ' breit' : '');
    dlg.innerHTML = `<form method="dialog" class="sic-dform" novalidate>${html}</form>`;
    dlgHandler = handler;
    if (!dlg.open) dlg.showModal();
    const f = (fokus && $(fokus, dlg)) || $('[autofocus]', dlg) || $('.sic-dinhalt input:not([type=hidden]):not([disabled]):not([type=checkbox]):not([type=radio]), .sic-dinhalt textarea, .sic-dinhalt select', dlg)
      || $('.sic-dfuss .btn.primary, .sic-dfuss .btn.gefahr', dlg) || $('.sic-dzu', dlg);
    if (f) f.focus();
  }
  function dialogZu() { if (dlg.open) dlg.close(); }
  const dFehler = (t) => { const e = $('#d-err', dlg); if (e) e.textContent = t || ''; };
  dlg.addEventListener('close', () => {
    dlg.innerHTML = ''; dlgHandler = null;
    if (dlgZurueck && dlgZurueck.isConnected) dlgZurueck.focus();
    dlgZurueck = null;
  });
  dlg.addEventListener('click', (e) => {
    if (e.target.closest('.sic-pwschritt')) return;
    const b = e.target.closest('[data-d]');
    if (!b) return;
    e.preventDefault();
    if (b.dataset.d === 'zu') { dialogZu(); return; }
    if (dlgHandler) lauf(b, () => dlgHandler(b.dataset.d, b, $('form', dlg)));
  });
  dlg.addEventListener('submit', (e) => {
    e.preventDefault();
    if (e.target.classList.contains('sic-pwschritt')) return;   // eigener Ablauf (passwortBestaetigen)
    const b = e.submitter || $('.sic-dfuss [type=submit]', dlg);
    if (dlgHandler) lauf(b, () => dlgHandler('submit', b, e.target));
  });
  /* Knopf während eines Vorgangs sperren; Fehler im Dialog bzw. als Hinweis zeigen */
  async function lauf(b, fn) {
    if (b && b.disabled) return;
    if (b) b.disabled = true;
    try { await fn(); } catch (ex) {
      if (ex && ex.data && ex.data.abbruch) return;
      if (dlg.open && $('#d-err', dlg)) dFehler(ex.message); else toast(ex.message, true);
    } finally { if (b && b.isConnected) b.disabled = false; }
  }
  /* Rückfrage im Dialog (ersetzt dessen Inhalt; kein zweiter Dialog) */
  function frage(titel, text, ja, gefahr = false) {
    return new Promise((ok) => {
      let fertig = false;
      const ende = (w) => { if (fertig) return; fertig = true; dlg.removeEventListener('close', zu); ok(w); };
      const zu = () => ende(false);
      dialog(`${dKopf(titel)}<div class="sic-dinhalt"><p>${text}</p></div>${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn ${gefahr ? 'gefahr' : 'primary'}">${esc(ja)}</button>`)}`,
        { handler: async (a) => { if (a === 'submit') ende(true); } });
      dlg.addEventListener('close', zu);
    });
  }
  /* Passwortbestätigung (Testserver/alter Eingabebereich) im selben Dialog: Ist ein Formular offen, legt sich der Schritt
     darüber und das Formular bleibt mit allen Eingaben erhalten (Abbrechen kehrt dorthin zurück); sonst eigener Dialog. */
  function passwortBestaetigen() {
    return new Promise((ok) => {
      const vorher = dlg.open ? $('.sic-dform', dlg) : null;
      if (!dlg.open) { dlgZurueck = document.activeElement; dlg.className = 'sic-dialog'; dlg.innerHTML = ''; dlgHandler = null; dlg.showModal(); }
      if (vorher) vorher.hidden = true;
      const box = document.createElement('form');
      box.className = 'sic-dform sic-pwschritt'; box.noValidate = true;
      box.innerHTML = `${dKopf('Bitte bestätigen', 'Sensible Aktion – Bestätigung mit Ihrem Passwort').replace('data-d="zu"', 'data-pw="nein"')}<div class="sic-dinhalt">
          <label class="sic-feld">Aktuelles Passwort<input type="password" id="sic-pw" autocomplete="current-password" required></label></div>
        <p class="sic-dfehler" id="sic-pw-err" role="alert"></p><div class="sic-dfuss"><button type="button" class="btn" data-pw="nein">Abbrechen</button><button type="submit" class="btn primary" id="sic-pw-ok">Bestätigen</button></div>`;
      dlg.append(box);
      $('#sic-pw', box).focus();
      const ende = (w) => {
        box.remove(); dlg.removeEventListener('cancel', esc); dlg.removeEventListener('close', zu);
        if (vorher && vorher.isConnected) { vorher.hidden = false; const k = $('.sic-dfuss [type=submit]', vorher); if (k) k.focus(); } else if (dlg.open) dialogZu();
        ok(w);
      };
      const esc = (e) => { e.preventDefault(); ende(false); };
      const zu = () => ok(false);
      dlg.addEventListener('cancel', esc);
      dlg.addEventListener('close', zu);
      box.addEventListener('click', (e) => { if (e.target.closest('[data-pw="nein"]')) { e.preventDefault(); ende(false); } });
      box.addEventListener('submit', async (e) => {
        e.preventDefault(); e.stopPropagation();
        const feld = $('#sic-pw', box), knopf = $('#sic-pw-ok', box);
        if (!feld.value) { $('#sic-pw-err', box).textContent = 'Bitte das Passwort eingeben.'; return; }
        knopf.disabled = true;
        try { await api('reauth', { body: { password: feld.value } }); ende(true); }
        catch (ex) { feld.value = ''; $('#sic-pw-err', box).textContent = ex.message; knopf.disabled = false; feld.focus(); }
      });
    });
  }
  function herunterladen(name, inhalt, typ) {
    const url = URL.createObjectURL(new Blob([inhalt], { type: typ }));
    const a = Object.assign(document.createElement('a'), { href: url, download: name });
    document.body.append(a); a.click(); a.remove(); setTimeout(() => URL.revokeObjectURL(url), 2000);
  }

  /* ---------- Rahmen: Anmeldung, Fehler, Reiter, Notfallband ---------- */
  function zeigeAnmeldung() { $('#sic-app').hidden = true; $('#sic-login').hidden = false; }
  function fehler(t) { $('#sic-app').hidden = true; const e = $('#sic-err'); e.textContent = t; e.hidden = false; }
  const TABS = { lage: 'sehen', notfall: '', firewall: 'admin', sitzungen: 'admin', datei: 'admin', ereignisse: 'sehen', einstellungen: 'admin', konten: 'admin', system: 'admin' };
  const erlaubt = (t) => t in TABS && (!TABS[t] || !!S.rechte[TABS[t]]);
  function zeigeTab(t) {
    if (!erlaubt(t)) t = S.rechte.sehen ? 'lage' : 'notfall';
    S.tab = t;
    for (const b of $$('#sic-tabs [data-tab]')) b.setAttribute('aria-selected', String(b.dataset.tab === t));
    for (const p of $$('.sic-tab')) p.hidden = p.id !== 'tab-' + t;
    if (location.hash.slice(1) !== t) history.replaceState(null, '', '#' + t);
    if (S.lage) notfallBand();
    clearInterval(S.fwTimer);
    LADEN[t]().catch((ex) => { $('#tab-' + t).innerHTML = `<div class="sic-meldung fehler">${esc(ex.message)}</div>`; });
  }
  $('#sic-tabs').addEventListener('click', (e) => { const b = e.target.closest('[data-tab]'); if (b) zeigeTab(b.dataset.tab); });
  $('#sic-tabs').addEventListener('keydown', (e) => {
    if (!['ArrowRight', 'ArrowLeft'].includes(e.key)) return;
    const l = $$('#sic-tabs [data-tab]:not([hidden])'), i = l.findIndex((b) => b.dataset.tab === S.tab);
    const n = l[(i + (e.key === 'ArrowRight' ? 1 : l.length - 1)) % l.length];
    if (n) { zeigeTab(n.dataset.tab); n.focus(); }
  });
  document.addEventListener('click', (e) => { const g = e.target.closest('[data-geh]'); if (g && erlaubt(g.dataset.geh)) { e.preventDefault(); zeigeTab(g.dataset.geh); window.scrollTo({ top: 0 }); } });
  $('#sic-neu').addEventListener('click', () => { S.sec = null; S.fw = null; zeigeTab(S.tab); toast('Aktualisiert.'); });

  function notfallBand() {
    const n = S.lage && S.lage.notfall;
    const band = $('#sic-notfallband'), pille = $('#sic-lage-pille');
    pille.hidden = false;
    pille.className = 'sic-lage-pille' + (n ? ' aktiv' : '');
    pille.innerHTML = n ? `${icon('alarm')}<span>Notfall aktiv</span>` : `<span class="sic-livepunkt" aria-hidden="true"></span><span>Normalbetrieb</span>`;
    band.hidden = !n || S.tab === 'notfall';   // im Reiter Notfall zeigt der Kopfbereich dasselbe
    if (n) band.innerHTML = `${icon('alarm')}<div><strong>Notfallmodus aktiv</strong> seit ${esc(zeit(n.seit))} Uhr${n.von ? ` · ausgelöst von ${esc(n.von)}` : ''}${n.grund ? ` · ${esc(n.grund)}` : ''}
      <span class="sub">Kunden sehen Wartung, Mitarbeiter ohne Administratorrolle sind ausgesperrt, E-Mail-Versand pausiert.</span></div>${S.tab !== 'notfall' ? '<button type="button" class="btn sm" data-geh="notfall">Zum Notfall</button>' : ''}`;
  }
  /* Offener Probealarm (Übung): Band in allen Reitern, bis man ihn als „gesehen“ bestätigt */
  function probeBand() {
    const p = S.lage && S.lage.probeOffen, b = $('#sic-probeband');
    b.hidden = !p;
    if (p) b.innerHTML = `${icon('uebung')}<div><strong>Probealarm – Übung ohne Wirkung</strong> · ${esc(p.vonName)} um ${esc(uhr(p.t))} Uhr
      <span class="sub">Bitte bestätigen Sie, dass die Meldung bei Ihnen angekommen ist. Es wurde nichts gesperrt.</span></div>
      <button type="button" class="btn sm" id="probe-gesehen" data-id="${esc(p.id)}">${icon('check')}Gesehen</button>`;
  }
  async function lageLaden() { S.lage = await api('sicherheit_lage'); S.rechte = S.lage.rechte; notfallBand(); probeBand(); return S.lage; }

  /* ---------- gemeinsame Bausteine ---------- */
  /* Mini-Verlauf (Balken, letzter Wert kräftig) für Karten mit Zeitreihe */
  const miniBalken = (w) => {
    if (!w || !w.length) return '';
    const max = Math.max(1, ...w);
    return `<svg class="sic-mini" viewBox="0 0 ${w.length * 9} 26" aria-hidden="true">${w.map((v, i) => { const h = Math.max(2, Math.round((v / max) * 24)); return `<rect x="${i * 9}" y="${26 - h}" width="6" height="${h}" rx="2"${i === w.length - 1 ? '' : ' opacity=".45"'}></rect>`; }).join('')}</svg>`;
  };
  const karte = (l, titel, wert, text, ziel = '', reihe = null) => {
    const inhalt = `<span class="sic-kpunkt"></span><div><span class="sic-ktitel">${esc(titel)}</span><span class="sic-kzeile"><strong class="sic-kwert${/^[\d\s.,:/%+–-]+$/.test(String(wert).replace(/<[^>]*>/g, '')) ? ' num' : ''}">${wert}</strong>${miniBalken(reihe)}</span>${text ? `<span class="sic-ktext">${text}</span>` : ''}</div>`;
    return ziel && erlaubt(ziel) ? `<button type="button" class="sic-karte ${l}" data-geh="${ziel}">${inhalt}</button>` : `<div class="sic-karte ${l}">${inhalt}</div>`;
  };
  const leer = (t) => `<p class="sic-leer">${t}</p>`;
  const dauerSek = (s) => (s >= 3600 ? `${Math.floor(s / 3600)} Std. ${Math.floor((s % 3600) / 60)} Min.` : s >= 60 ? `${Math.floor(s / 60)} Min.` : `${Math.max(0, s)} Sek.`);
  const block = (titel, inhalt, extra = '', id = '') => `<section class="sic-block sic-glas"${id ? ` id="${id}"` : ''}><div class="sic-bkopf"><h3>${titel}</h3>${extra}</div>${inhalt}</section>`;
  function sicherungKarte(b, ziel = '') {
    if (!b || !b.t) return karte('warn', 'Datensicherung', 'keine', 'noch keine automatische Sicherung', ziel);
    const alter = (Date.now() - new Date(b.t).getTime()) / 3600000;
    if (!b.ok) return karte('bad', 'Datensicherung', 'fehlgeschlagen', esc(b.meldung || zeit(b.t)), ziel);
    if (alter > 48) return karte('bad', 'Datensicherung', 'veraltet', `letzte ${esc(zeit(b.t))} Uhr`, ziel);
    return karte('ok', 'Datensicherung', 'geprüft', `${esc(zeit(b.t))} Uhr${b.anzahl ? ` · ${b.anzahl} Stände` : ''}`, ziel);
  }
  function bereitstellungKarte(r, ziel = '') {
    if (!r || !r.t) return karte('warn', 'Bereitstellung', 'ohne Freigabe', 'Release-Modus noch nicht eingerichtet', ziel);
    return r.ok ? karte('ok', 'Bereitstellung', esc(String(r.sha || '').slice(0, 7)), `freigegeben · ${esc(zeit(r.t))} Uhr`, ziel)
      : karte('bad', 'Bereitstellung', esc(String(r.sha || '').slice(0, 7)), esc(r.meldung || 'letztes Release fehlgeschlagen'), ziel);
  }
  function verlaufSvg(tl) {
    if (!tl || !tl.length) return '';
    const max = Math.max(1, ...tl.map((d) => d.staff + d.kunde + d.reauth));
    const W = 28, H = 96;
    const balken = tl.map((d, i) => {
      let y = H;
      const r = [['staff', d.staff], ['kunde', d.kunde], ['reauth', d.reauth]].map(([k, n]) => { const h = Math.round((n / max) * (H - 4)); y -= h; return n ? `<rect class="tl-${k}" x="${i * W + 5}" y="${y}" width="${W - 10}" height="${h}" rx="3"></rect>` : ''; }).join('');
      const lab = `${d.d.slice(8, 10)}.${d.d.slice(5, 7)}.: ${d.staff} Mitarbeiter, ${d.kunde} Kunden, ${d.reauth} Passwortbestätigung · ${d.ok} erfolgreiche Anmeldungen · ${d.geo} per Ländersperre abgewiesen`;
      return `<g><title>${esc(lab)}</title><rect class="tl-hit" x="${i * W}" y="0" width="${W}" height="${H}"></rect>${r}<text x="${i * W + W / 2}" y="${H + 14}" text-anchor="middle">${esc(d.d.slice(8, 10))}</text></g>`;
    }).join('');
    const sum = (k) => tl.reduce((a, d) => a + d[k], 0);
    return `<div class="sic-tl"><svg viewBox="0 0 ${tl.length * W} ${H + 18}" role="img" aria-label="Fehlgeschlagene Anmeldungen der letzten 14 Tage">${balken}</svg></div>
      <p class="sic-legende"><span><i class="tl-staff"></i>Mitarbeiter ${zahl(sum('staff'))}</span><span><i class="tl-kunde"></i>Kunden ${zahl(sum('kunde'))}</span><span><i class="tl-reauth"></i>Passwortbestätigung ${zahl(sum('reauth'))}</span><span>erfolgreich ${zahl(sum('ok'))}</span><span>Ländersperre ${zahl(sum('geo'))}</span></p>`;
  }
  const pruefZeilen = (l) => l.map((c) => `<tr class="cf-${esc(c.level)}"><td>${punkt(c.level)}</td><td><div class="sic-nm">${esc(c.title)}</div><div class="sub">${esc(c.area)}</div></td><td>${esc(c.text)}${c.hint ? `<div class="sub nur-schmal">${esc(c.hint)}</div>` : ''}</td><td class="sub nicht-schmal">${esc(c.hint || '')}</td></tr>`).join('');
  const EV_ART = { anmeldung: 'Anmeldung', kunden: 'Kunden', konten: 'Zugänge', einstellungen: 'Einstellungen', notfall: 'Notfall' };
  const evZeile = (e, i) => `<tr class="sic-klick" data-ev="${i}" tabindex="0"><td class="num-s">${esc(zeit(e.t))}</td><td><span class="sic-pille ${e.stufe}">${esc(EV_ART[e.art] || e.art)}</span></td>
    <td><div class="sic-nm">${esc(e.s)}</div>${e.d && e.d.length ? `<div class="sub">${plural(e.d.length, 'Änderung', 'Änderungen')}</div>` : ''}</td><td>${esc(e.n || e.u || '—')}${e.u && e.n ? `<div class="sub">${esc(e.u)}</div>` : ''}</td><td class="mono-s">${esc(e.ip || '')}</td></tr>`;
  function evDialog(e) {
    const det = (e.d || []).map((c) => `<tr><td>${esc([c.name, c.f].filter(Boolean).join(' · '))}</td><td>${esc(c.from || '')}</td><td>${esc(c.to || '')}</td></tr>`).join('');
    dialog(`${dKopf(e.s, `${esc(zeit(e.t))} Uhr · ${esc(EV_ART[e.art] || e.art)}`)}<div class="sic-dinhalt">
      <dl class="sic-dl"><dt>Vorgang</dt><dd class="mono-s">${esc(e.a)}</dd><dt>Benutzer</dt><dd>${esc(e.n || '—')}${e.u ? ` <span class="sub">${esc(e.u)}</span>` : ''}</dd>
        <dt>Rolle</dt><dd>${esc(e.r || '—')}</dd><dt>IP-Adresse</dt><dd class="mono-s">${esc(e.ip || '—')}</dd></dl>
      ${det ? `<table class="sic-tabelle klein"><thead><tr><th>Feld</th><th>vorher</th><th>nachher</th></tr></thead><tbody>${det}</tbody></table>` : ''}</div>
      ${dFuss('<button type="button" class="btn primary" data-d="zu">Schließen</button>')}`, { breit: !!det });
  }

  /* ======================= Lagebild ======================= */
  async function lageTab() {
    const host = $('#tab-lage');
    if (!S.lage) host.innerHTML = '<div class="sic-laden"><span class="sic-spinner"></span>Lagebild wird geladen …</div>';
    await lageLaden();
    const L = S.lage.lage, K = L.kennzahlen, E = L.einstellungen, n = S.lage.notfall;
    const dp = L.dateipruefung;
    const dpKarte = !dp ? karte('warn', 'Dateiprüfung', 'offen', 'noch keine Prüfung', 'datei')
      : karte(dp.counts.critical ? 'bad' : dp.counts.warnings ? 'warn' : 'ok', 'Dateiprüfung', dp.counts.critical ? `${dp.counts.critical} kritisch` : dp.counts.warnings ? `${dp.counts.warnings} Warnungen` : 'unauffällig', `zuletzt ${esc(zeit(dp.ranAt))} Uhr`, 'datei');
    const tl7 = (L.timeline || []).slice(-7).map((d) => d.staff + d.kunde + d.reauth);
    const karten = [
      karte(K.fehl24 >= 20 ? 'bad' : K.fehl24 >= 5 ? 'warn' : 'ok', 'Fehlanmeldungen (24 h)', zahl(K.fehl24), `${zahl(K.anmeldungen24)} erfolgreiche Anmeldungen`, 'sitzungen', tl7),
      karte(K.gesperrteAdressen || K.gesperrteKonten ? 'warn' : 'ok', 'Gesperrt', zahl(K.gesperrteAdressen + K.gesperrteKonten), `${plural(K.gesperrteAdressen, 'Adresse', 'Adressen')} · ${plural(K.gesperrteKonten, 'Zugang', 'Zugänge')}`, 'firewall'),
      karte(K.adminsOhneZweiFaktor ? 'bad' : K.ohneZweiFaktor ? 'warn' : 'ok', 'Zwei-Faktor-Anmeldung', `${zahl(K.zugaenge - K.ohneZweiFaktor)} / ${zahl(K.zugaenge)}`, K.adminsOhneZweiFaktor ? `${plural(K.adminsOhneZweiFaktor, 'Administrator', 'Administratoren')} ohne zweiten Faktor` : K.ohneZweiFaktor ? `${zahl(K.ohneZweiFaktor)} Zugänge ohne zweiten Faktor` : 'alle Zugänge geschützt', 'konten'),
      karte('ok', 'Aktive Sitzungen', zahl(K.sitzungen), `${zahl(K.kundenOnline)} Kunden angemeldet`, 'sitzungen'),
      karte(E.waf === 'sperren' && E.autoSperre ? 'ok' : E.waf === 'aus' ? 'bad' : 'warn', 'Firewall', E.waf === 'sperren' ? 'sperrt' : E.waf === 'protokoll' ? 'protokolliert' : 'aus', `${E.autoSperre ? 'automatische Sperre an' : 'automatische Sperre aus'} · Bedrohungsliste ${E.feed ? 'an' : 'aus'}`, 'firewall'),
      dpKarte, sicherungKarte(L.backup, 'system'), bereitstellungKarte(L.deployment, 'system'),
    ];
    const maxIp = Math.max(1, ...(L.topIps || []).map((x) => x.n));
    const tops = (L.topIps || []).map((x, i) => `<tr class="sic-klick" data-topip="${i}" tabindex="0"><td class="mono-s">${esc(x.ip)}${x.blocked ? ' <span class="sic-pille bad">gesperrt</span>' : ''}</td>
      <td class="num-s"><span class="ip-n"><span class="ip-balken" style="--anteil:${Math.max(6, Math.round((x.n / maxIp) * 100))}%"></span>${zahl(x.n)}</span></td><td>${x.cc ? esc(land(x.cc)) : '<span class="sub">unbekannt</span>'}</td><td class="num-s">${esc(zeit(x.last))}</td></tr>`).join('');
    const evl = L.ereignisse.map((e, i) => `<li><button type="button" data-lev="${i}"><span class="ev-zeit num">${esc(uhr(e.t))}</span><span class="ev-punkt ${esc(e.stufe)}" aria-hidden="true"></span>
      <span class="ev-text"><span class="sic-nm">${esc(e.s)}</span><span class="sub">${esc(EV_ART[e.art] || e.art)}${e.n ? ' · ' + esc(e.n) : ''} · ${esc(datum(e.t))}</span></span></button></li>`).join('');
    host.innerHTML = `
      <div class="sic-oben">
        <div class="sic-gesamt sic-glas" id="sic-gesamt"></div>
        ${abwehrHtml(L, K)}
        ${konsoleHtml()}
      </div>
      <div class="sic-karten">${karten.join('')}</div>
      <div class="sic-zwei">
        ${block(`Fehlgeschlagene Anmeldungen <span class="sub">14 Tage</span>`, verlaufSvg(L.timeline))}
        ${block(`Auffällige Adressen <span class="sub">7 Tage</span>`, tops ? `<div class="sic-tabrahmen"><table class="sic-tabelle"><thead><tr><th>IP-Adresse</th><th class="num-s">Fehlversuche</th><th>Land</th><th class="num-s">zuletzt</th></tr></thead><tbody>${tops}</tbody></table></div>` : leer('Keine fehlgeschlagenen Anmeldungen in den letzten 7 Tagen.'))}
      </div>
      <div class="sic-zwei breit-links">
        ${block('Konfigurationsprüfung', `<div class="sic-tabrahmen"><table class="sic-tabelle cftab" id="sic-cftab"><thead><tr><th class="lv-h"><span class="sr-only">Stufe</span></th><th>Prüfung</th><th>Befund</th><th class="nicht-schmal">Empfehlung</th></tr></thead>
          <tbody>${pruefZeilen(L.config || [])}</tbody><tbody id="sic-bchecks"><tr><td></td><td colspan="3" class="sub">Browser-Prüfungen laufen …</td></tr></tbody></table></div>
          <p class="sic-hinweis">Angezeigt werden Hinweise und kritische Befunde. Der Server selbst (Betriebssystem, SSH, Updates) ist aus der Anwendung nicht einsehbar und wird separat geprüft.</p>`,
          '<button type="button" class="btn sm" id="sic-cf-alle" aria-pressed="false">Alle anzeigen</button>')}
        ${block(`Letzte Ereignisse <span class="sic-live" aria-hidden="true"><span class="sic-livepunkt"></span>laufend</span>`, L.ereignisse.length ? `<ul class="sic-evliste">${evl}</ul>
          <button type="button" class="btn sm" data-geh="ereignisse">Alle Ereignisse</button>` : leer('Keine Sicherheitsereignisse in den letzten 7 Tagen.'))}
      </div>
      <div class="sic-zwei">${berichtBlock()}${bereitBlock()}</div>
      ${S.rechte.notfall && !n ? `<div class="sic-mobilnotfall"><button type="button" class="btn gefahr gross" data-notfall-start>${icon('alarm')}Notfall auslösen …</button></div>` : ''}`;
    gesamt();
    cfKnopf();
    browserPruefungen();
  }
  /* Wochenbericht: Versand, Empfänger, letzter Versand; Ansehen im Dialog (wie die E-Mail) */
  function berichtBlock() {
    const B = S.lage.bericht;
    if (!B) return '';
    const l = B.verlauf[0];
    return block(`Wochenbericht <span class="sub">E-Mail</span>`, `<dl class="sic-dl eng">
        <dt>Versand</dt><dd>${B.an ? `jeden ${esc(B.tage[B.tag])}${B.naechster ? ` <span class="sub">· nächster ${esc(zeit(B.naechster))} Uhr</span>` : ''}` : '<span class="sic-pille">aus</span>'}</dd>
        <dt>Empfänger</dt><dd>${B.empfaenger.length ? esc(B.empfaenger.join(', ')) : '<span class="sic-pille bad">keine eingetragen</span>'}</dd>
        <dt>zuletzt</dt><dd>${l ? `${esc(zeit(l.t))} Uhr${l.ok ? ` <span class="sub">· ${l.auto ? 'automatisch' : esc(l.von)}</span>` : ` <span class="sic-pille bad">${esc(l.fehler || 'nicht zugestellt')}</span>`}` : 'noch nicht versendet'}</dd></dl>
      <div class="sic-knoepfe sic-blockfuss"><button type="button" class="btn sm" data-bericht>${icon('bericht')}Bericht ansehen</button>${S.rechte.admin ? `<button type="button" class="btn sm" data-geh="einstellungen">Einstellen</button>` : ''}</div>`, '', 'sic-berichtblock');
  }
  /* Bereitschaft: letzter Probealarm, Leitfaden und Ansprechpartner */
  function bereitBlock() {
    const P = (S.lage.proben || [])[0], L = S.lage.leitfaden;
    return block('Bereitschaft für den Ernstfall', `<dl class="sic-dl eng">
        <dt>Letzter Probealarm</dt><dd>${P ? `${esc(datum(P.t))} <span class="sub">· ${zahl(P.ok)} von ${zahl(P.gesamt)} in Ordnung · ${plural(P.quittiert.length, 'Bestätigung', 'Bestätigungen')}</span>` : '<span class="sic-pille warn">noch keiner</span>'}</dd>
        <dt>Leitfaden</dt><dd>${L.standard ? 'Vorlage' : 'eigene Schritte'} <span class="sub">· ${plural(L.schritte.length, 'Schritt', 'Schritte')}</span></dd>
        <dt>Ansprechpartner</dt><dd>${L.kontakte.length ? esc(L.kontakte.map((k) => k.name || k.rolle).join(', ')) : '<span class="sic-pille warn">keine eingetragen</span>'}</dd></dl>
      <div class="sic-knoepfe sic-blockfuss"><button type="button" class="btn sm" data-geh="notfall">Zum Leitfaden</button>${S.rechte.notfall && !S.lage.notfall ? `<button type="button" class="btn sm" data-probe-start>${icon('uebung')}Probealarm …</button>` : ''}</div>`);
  }
  async function berichtDialog() {
    const r = await api('sicherheit_bericht');
    const B = r.bericht, E = r.einstellungen;
    const ST = { ok: 'alles in Ordnung', warn: 'mit Hinweisen', bad: 'Handlungsbedarf' };
    const teil = B.abschnitte.map((a) => `<section class="br-abschnitt ${esc(a.stufe)}"><h4>${punkt(a.stufe)}${esc(a.titel)}</h4>
        <table class="sic-tabelle klein"><tbody>${a.zeilen.map((z) => `<tr><td class="lv-h">${punkt(z[2] || 'info')}</td><td>${esc(z[0])}</td><td class="num-s"><strong>${esc(z[1])}</strong></td></tr>`).join('')}</tbody></table>
        ${a.liste.length ? `<ul class="br-liste">${a.liste.map((x) => `<li>${esc(x)}</li>`).join('')}</ul>` : ''}${a.hinweis ? `<p class="sic-hinweis">${esc(a.hinweis)}</p>` : ''}</section>`).join('');
    dialog(`${dKopf('Sicherheitsbericht', `${esc(datum(B.von))} – ${esc(datum(B.bis))} · <span class="sic-pille ${esc(B.stufe)}">${ST[B.stufe] || ''}</span>`)}<div class="sic-dinhalt">
        <div class="br-raster">${teil}</div>
        <p class="sic-hinweis">So sieht auch die E-Mail aus${E.an ? ` – automatisch jeden ${esc(E.tage[E.tag])}` : ''}. Empfänger: ${E.empfaenger.length ? esc(E.empfaenger.join(', ')) : 'noch keine (Verwaltung → E-Mail → Benachrichtigungen → Sicherheitsereignisse)'}.</p></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Schließen</button>${S.rechte.admin ? `<button type="button" class="btn primary" data-d="senden"${E.empfaenger.length ? '' : ' disabled'}>${icon('post')}Jetzt senden</button>` : ''}`)}`,
    { breit: true, handler: async (a) => {
      if (a !== 'senden') return;
      const x = await api('sicherheit_bericht_senden', { body: {} });
      S.lage.bericht = x.einstellungen;
      dialogZu();
      toast(x.versand.ok ? `Bericht an ${plural(x.versand.ok, 'Empfänger', 'Empfänger')} gesendet.` : `Bericht nicht zugestellt: ${x.versand.fehler || 'unbekannter Fehler'}`, !x.versand.ok);
      const bb = $('#sic-berichtblock');
      if (bb) bb.outerHTML = berichtBlock();
    } });
  }
  function gesamt() {
    const el = $('#sic-gesamt');
    if (!el) return;
    const lv = $$('#tab-lage .sic-karte, #tab-lage tr[class^="cf-"]').map((x) => (/\b(bad|cf-bad)\b/.test(x.className) ? 'bad' : /\b(warn|cf-warn)\b/.test(x.className) ? 'warn' : /\b(ok|cf-ok)\b/.test(x.className) ? 'ok' : 'info'));
    const n = (k) => lv.filter((x) => x === k).length;
    const w = n('bad') ? 'bad' : n('warn') ? 'warn' : 'ok';
    const ring = lv.length ? Math.round((n('ok') / Math.max(1, n('ok') + n('warn') + n('bad'))) * 100) : 100;
    el.className = 'sic-gesamt sic-glas ' + w;
    // Ring in Abschnitten: in Ordnung (grün), Hinweise (bernstein), kritisch (rot) – Anteil an allen bewerteten Prüfungen
    const r = 52, U = 2 * Math.PI * r, summe = Math.max(1, n('ok') + n('warn') + n('bad'));
    let start = 0;
    const teil = (k, kl) => { const len = (n(k) / summe) * U; const svg = len > 0.5 ? `<circle class="${kl}" cx="64" cy="64" r="${r}" stroke-dasharray="${Math.max(0, len - 3).toFixed(1)} ${U.toFixed(1)}" stroke-dashoffset="${(-start).toFixed(1)}"></circle>` : ''; start += len; return svg; };
    const ringe = teil('ok', 'r-ok') + teil('warn', 'r-warn') + teil('bad', 'r-bad');
    el.innerHTML = `<svg class="sic-ringsvg" viewBox="0 0 128 128" role="img" aria-label="${ring} Prozent der Prüfungen in Ordnung"><circle class="r-grund" cx="64" cy="64" r="${r}"></circle><g transform="rotate(-90 64 64)">${ringe}</g>
        <text x="64" y="70" text-anchor="middle" class="r-zahl">${ring}</text><text x="64" y="90" text-anchor="middle" class="r-einheit">Prozent</text></svg>
      <div><span class="sic-ueber">Sicherheitslage</span><strong>${w === 'bad' ? 'Handlungsbedarf' : w === 'warn' ? 'In Ordnung, mit Hinweisen' : 'Alles in Ordnung'}</strong>
      <span class="sic-chips"><span class="sic-pille ok">${zahl(n('ok'))} in Ordnung</span><span class="sic-pille warn">${plural(n('warn'), 'Hinweis', 'Hinweise')}</span><span class="sic-pille ${n('bad') ? 'bad' : ''}">${zahl(n('bad'))} kritisch</span></span>
      <span class="sub">Stand ${esc(uhr(S.lage.zeit))} Uhr · Ihre Adresse <span class="mono-s">${esc(S.lage.ich.ip)}</span></span></div>`;
  }
  /* Abwehr der letzten 24 Stunden: Angriffsmuster, abgewiesene Anfragen, gesperrte Adressen und Verlauf je Stunde */
  function abwehrHtml(L, K) {
    const st = L.stunden || [];
    const max = Math.max(1, ...st.map((x) => x.angriffe + x.abgewiesen));
    const balken = st.map((x, i) => {
      const ha = Math.round((x.abgewiesen / max) * 82), hn = Math.round((x.angriffe / max) * 82);
      const tipp = `${String((new Date().getHours() + 1 + i) % 24).padStart(2, '0')} Uhr: ${x.angriffe} Angriffsmuster, ${x.abgewiesen} abgewiesen`;
      return `<g><title>${esc(tipp)}</title>${ha ? `<rect class="ab-abgewiesen" x="${i * 20 + 3}" y="${88 - ha}" width="14" height="${ha}" rx="3"></rect>` : ''}${hn ? `<rect class="ab-angriff" x="${i * 20 + 3}" y="${88 - ha - hn - (ha ? 2 : 0)}" width="14" height="${hn}" rx="3"></rect>` : ''}</g>`;
    }).join('');
    return `<section class="sic-abwehr sic-glas" aria-label="Abwehr der letzten 24 Stunden">
      <div class="sic-bkopf"><span class="sic-ueber">Abwehr · letzte 24 Stunden</span><span class="sic-live"><span class="sic-livepunkt"></span>live</span></div>
      <div class="ab-zahlen"><button type="button" data-geh="firewall"><strong class="num">${zahl(K.angriffe24)}</strong><span>Angriffsversuche erkannt</span></button>
        <button type="button" data-geh="firewall"><strong class="num">${zahl(K.abgewiesen24)}</strong><span>Anfragen abgewiesen</span></button>
        <button type="button" data-geh="firewall"><strong class="num${K.gesperrteAdressen ? ' rot' : ''}">${zahl(K.gesperrteAdressen)}</strong><span>Adressen gesperrt</span></button></div>
      ${st.length ? `<svg class="ab-verlauf" viewBox="0 0 480 90" preserveAspectRatio="none" role="img" aria-label="Angriffsmuster und abgewiesene Anfragen je Stunde"><line x1="0" y1="89" x2="480" y2="89"></line>${balken}</svg>
      <p class="sic-legende"><span><i class="ab-abgewiesen"></i>abgewiesen</span><span><i class="ab-angriff"></i>Angriffsmuster</span><span class="ab-achse num">vor 24 h · jetzt</span></p>` : ''}
    </section>`;
  }
  /* Notfall-Konsole im Lagebild: Zustand, Auslösen (Recht), Probealarm, Leitfaden, letzte Übung */
  function konsoleHtml() {
    const r = S.lage, n = r.notfall, P = (r.proben || [])[0], LF = r.leitfaden;
    if (n) {
      return `<section class="sic-konsole aktiv sic-glas" aria-label="Notfall-Konsole"><div class="sic-bkopf"><span class="sic-ueber">Notfallmodus aktiv</span></div>
        <strong class="ko-titel">seit ${esc(uhr(n.seit))} Uhr${n.von ? ` · ${esc(n.von)}` : ''}</strong>${n.grund ? `<span>${esc(n.grund)}</span>` : ''}
        <button type="button" class="btn primary" data-geh="notfall">Zum Notfall</button></section>`;
    }
    const gesehen = P ? `${P.quittiert.length} ${P.quittiert.length === 1 ? 'Bestätigung' : 'Bestätigungen'}` : '';
    return `<section class="sic-konsole sic-glas" aria-label="Notfall-Konsole">
      <div class="sic-bkopf"><span class="sic-ueber">Notfall-Konsole</span><span class="sic-pille ok">Normalbetrieb · bereit</span></div>
      ${r.rechte.notfall ? `<button type="button" class="ko-ausloesen" data-notfall-start><span class="ko-icon">${icon('alarm')}</span><span><strong>Notfall auslösen</strong><span>Kunden: Wartung · Mitarbeiter gesperrt · Mails pausiert</span></span></button>
        <div class="ko-knoepfe"><button type="button" class="btn" data-probe-start>${icon('uebung')}Probealarm</button><button type="button" class="btn" data-geh="notfall">Leitfaden</button></div>`
        : `<p class="sic-hinweis">Auslösen dürfen Administratoren und Mitarbeiter mit dem Recht „Notfall auslösen“.</p><div class="ko-knoepfe"><button type="button" class="btn" data-geh="notfall">Leitfaden</button></div>`}
      <span class="sub">${P ? `Letzter Probealarm ${esc(datum(P.t))} · ${zahl(P.ok)} von ${zahl(P.gesamt)} in Ordnung · ${gesehen}` : 'Noch kein Probealarm – einmal üben lohnt sich.'}</span>
      <span class="sub">Leitfaden: ${plural(LF.schritte.length, 'Schritt', 'Schritte')} · ${LF.kontakte.length ? plural(LF.kontakte.length, 'Ansprechpartner', 'Ansprechpartner') : 'noch keine Ansprechpartner'}</span>
    </section>`;
  }
  /* Prüfungen aus Sicht des Browsers: Sicherheits-Header, gesperrte Ordner, Uhrzeit */
  async function browserPruefungen() {
    const rows = [];
    const add = (level, title, text, hint = '') => rows.push({ level, area: 'Browser', title, text, hint });
    try {
      const r = await fetch('/', { cache: 'no-store', credentials: 'same-origin' });
      const h = (n) => r.headers.get(n) || '';
      const csp = h('content-security-policy');
      add(csp ? (/script-src[^;]*'self'/.test(csp) && !/unsafe-eval/.test(csp) && !/script-src[^;]*unsafe-inline/.test(csp) ? 'ok' : 'warn') : 'bad', 'Schutz gegen eingeschleuste Skripte (CSP)', csp ? 'gesetzt' : 'fehlt', csp ? '' : 'Content-Security-Policy im Webserver setzen.');
      const https = location.protocol === 'https:';
      add(!https ? 'info' : h('strict-transport-security') ? 'ok' : 'bad', 'HTTPS erzwingen (HSTS)', !https ? 'nur über HTTPS prüfbar' : h('strict-transport-security') || 'fehlt');
      add(/nosniff/i.test(h('x-content-type-options')) ? 'ok' : 'warn', 'MIME-Typ-Schutz', h('x-content-type-options') || 'fehlt');
      const frame = h('x-frame-options') || (/frame-ancestors/.test(csp) ? 'frame-ancestors (CSP)' : '');
      add(frame ? 'ok' : 'warn', 'Schutz gegen Einbetten (Clickjacking)', frame || 'fehlt');
      add(h('referrer-policy') ? 'ok' : 'warn', 'Referrer-Policy', h('referrer-policy') || 'fehlt');
      const sd = Date.parse(h('date'));
      if (!Number.isNaN(sd)) { const d = Math.round((Date.now() - sd) / 1000); add(Math.abs(d) > 120 ? 'warn' : 'ok', 'Uhrzeit Server/Browser', Math.abs(d) <= 2 ? 'stimmt überein' : `Abweichung ${d} s`, Math.abs(d) > 120 ? 'Uhrzeit prüfen (Zwei-Faktor-Codes hängen davon ab).' : ''); }
    } catch (e) { add('warn', 'Sicherheits-Header', 'nicht prüfbar'); }
    try {
      const r = await fetch(API + '?action=status', { cache: 'no-store', credentials: 'same-origin' });
      const pb = r.headers.get('x-powered-by') || '';
      add(pb ? 'warn' : 'ok', 'Server-Software verborgen', pb ? `sichtbar: ${pb}` : 'keine Versionsangabe (X-Powered-By)', pb ? 'Header X-Powered-By entfernen.' : '');
    } catch { /* nicht prüfbar */ }
    for (const [pfad, titel] of [['/data/nutzer.php', 'Datenordner'], ['/api/lib/kern.php', 'Programmdateien']]) {
      try {
        const r = await fetch(pfad, { cache: 'no-store', credentials: 'omit' });
        const t = r.status === 200 ? await r.text() : '';
        const leck = r.status === 200 && /"(hash|username|password)"/.test(t);
        add(leck ? 'bad' : 'ok', `${titel} von außen gesperrt`, leck ? `lesbar (${pfad})` : `gesperrt (Status ${r.status})`, leck ? 'Sofort Webserver-Regeln prüfen!' : '');
      } catch { add('info', `${titel} von außen gesperrt`, 'nicht prüfbar'); }
    }
    const t = $('#sic-bchecks');
    if (t) { t.innerHTML = pruefZeilen(rows); gesamt(); cfKnopf(); }
  }
  /* Konfigurationsprüfung: standardmäßig nur Hinweise und Kritisches, „Alle anzeigen“ blendet die erfüllten Prüfungen ein */
  function cfKnopf() {
    const b = $('#sic-cf-alle'), t = $('#sic-cftab');
    if (!b || !t) return;
    const alle = t.classList.contains('alle'), ok = $$('tr.cf-ok', t).length;
    b.textContent = alle ? 'Nur Hinweise' : `Alle anzeigen (${zahl(ok)} in Ordnung)`;
    b.setAttribute('aria-pressed', String(alle));
  }
  $('#tab-lage').addEventListener('click', (e) => {
    if (e.target.closest('#sic-cf-alle')) { $('#sic-cftab').classList.toggle('alle'); cfKnopf(); return; }
    const t = e.target.closest('[data-topip]');
    if (t) { topIpDialog(S.lage.lage.topIps[+t.dataset.topip]); return; }
    const v = e.target.closest('[data-lev]');
    if (v) evDialog(S.lage.lage.ereignisse[+v.dataset.lev]);
  });
  $('#tab-lage').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('[data-topip]')) topIpDialog(S.lage.lage.topIps[+e.target.dataset.topip]); });
  function topIpDialog(x) {
    dialog(`${dKopf(x.ip, 'Auffällige Adresse · 7 Tage')}<div class="sic-dinhalt"><dl class="sic-dl">
        <dt>Fehlversuche</dt><dd>${zahl(x.n)}${x.kunde ? ` <span class="sub">(${zahl(x.kunde)} bei der Kunden-Anmeldung)</span>` : ''}</dd>
        <dt>Land</dt><dd>${x.cc ? `${esc(land(x.cc))} <span class="sub">${esc(x.cc)}</span>` : 'unbekannt'}</dd>
        <dt>Benutzernamen</dt><dd>${esc((x.users || []).join(', ') || '—')}</dd><dt>zuletzt</dt><dd>${esc(zeit(x.last))} Uhr</dd>
        <dt>Zustand</dt><dd>${x.blocked ? '<span class="sic-pille bad">durch die Anmeldebremse gesperrt</span>' : 'nicht gesperrt'}</dd></dl>
        ${S.rechte.admin ? '<p class="sic-hinweis">Sperren gilt für Eingabebereich, Angebotsseite und App.</p>' : ''}</div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Schließen</button>${S.rechte.admin ? `<button type="button" class="btn gefahr" data-d="sperren">${icon('lock')}Einen Tag sperren</button>` : ''}`)}`,
    { handler: async (a) => {
      if (a !== 'sperren') return;
      await aufruf('fw_sperren', { body: { ip: x.ip, minuten: 1440, grund: 'aus dem Lagebild (Fehlanmeldungen)' } });
      dialogZu(); toast('Adresse für einen Tag gesperrt.');
    } });
  }

  /* ======================= Notfall ======================= */
  const WIRKUNG_ICON = { kunden: 'kunden', mitarbeiter: 'team', sitzungen: 'tuer', mail: 'post', firewall: 'wand', meldung: 'glocke' };
  async function notfallTab() {
    const host = $('#tab-notfall');
    await lageLaden();
    const r = S.lage, n = r.notfall, W = r.wirkungen, Z = W.zahlen;
    const hero = n ? `<section class="sic-held aktiv sic-glas" aria-live="polite">
        <div class="sic-held-icon sic-alarmring"><span class="welle" aria-hidden="true"></span><span class="welle zwei" aria-hidden="true"></span>${icon('alarm', 'gross')}</div>
        <div class="sic-held-text"><span class="sic-ueber">Notfallmodus aktiv</span><h2>Seit ${esc(uhr(n.seit))} Uhr · <span class="num" id="nf-dauer" data-seit="${esc(n.seit)}">${esc(laufzeit(n.seit))}</span></h2>
          ${n.grund !== undefined ? `<p><strong>Grund:</strong> ${esc(n.grund)} · <strong>ausgelöst von</strong> ${esc(n.von)}</p><p class="sub">Hinweis für Kunden: „${esc(n.kundentext)}“</p>` : '<p>Einzelheiten sehen Administratoren.</p>'}</div>
        <div class="sic-held-knopf">${r.rechte.beenden ? `<button type="button" class="btn primary gross" id="nf-aus">${icon('unlock')}Notfall beenden …</button>` : '<p class="sub">Beenden können nur Administratoren.</p>'}</div>
      </section>`
      : `<section class="sic-held sic-glas">
        <div class="sic-held-icon">${icon('schild', 'gross')}</div>
        <div class="sic-held-text"><span class="sic-ueber">Normalbetrieb</span><h2>Kein Notfall aktiv</h2>
          <p>Bei einem Sicherheitsvorfall – etwa einem übernommenen Konto, auffälligen Änderungen oder einem laufenden Angriff – sperrt der Notfallmodus mit einem Schritt alle Zugänge außer denen der Administratoren.</p></div>
        <div class="sic-held-knopf">${r.rechte.notfall ? `<button type="button" class="btn gefahr gross" id="nf-an">${icon('alarm')}Notfall auslösen …</button>
          <button type="button" class="btn" data-probe-start>${icon('uebung')}Probealarm …</button><span class="sub">Übung ohne Wirkung</span>` : '<p class="sub">Auslösen dürfen Administratoren und Mitarbeiter mit dem Recht „Notfall auslösen“.</p>'}</div>
      </section>`;
    const punkte = W.punkte.map(([k, t]) => `<li>${icon(WIRKUNG_ICON[k] || 'check')}<span>${esc(t)}</span></li>`).join('');
    const verlauf = (r.verlauf || []).map((v, i) => `<tr class="sic-klick" data-nfv="${i}" tabindex="0"><td class="num-s">${esc(zeit(v.seit))}</td><td>${esc(dauerText(v.seit, v.bis))}</td><td>${esc(v.von)}</td><td>${esc(v.beendetVon)}</td><td>${esc(v.grund)}</td></tr>`).join('');
    const lf = leitfadenHtml();
    const unten = r.rechte.sehen ? `<div class="sic-zwei">${block('Letzte Notfälle', verlauf ? `<div class="sic-tabrahmen"><table class="sic-tabelle"><thead><tr><th>Beginn</th><th>Dauer</th><th>ausgelöst von</th><th>beendet von</th><th>Grund</th></tr></thead><tbody>${verlauf}</tbody></table></div>` : leer('Bisher wurde kein Notfall ausgelöst.'))}${probenHtml()}</div>`
      : r.rechte.notfall ? probenHtml() : '';
    // im Notfall: Wirkung als Kennzahlen und der Verlauf dieses Notfalls (Ereignisse seit Beginn)
    const kacheln = n ? `<div class="sic-karten wirkung">${[
      karte('ok', 'Angebotsseite', 'Wartung', 'Kunden sehen den neutralen Hinweis'),
      karte('ok', 'Mitarbeiter ohne Administratorrolle', 'gesperrt', 'Administratoren arbeiten weiter'),
      ...(n.wirkung ? [karte('ok', 'Sitzungen beendet', zahl((+n.wirkung.mitarbeiterSitzungen || 0) + (+n.wirkung.kundenSitzungen || 0)), `${zahl(n.wirkung.mitarbeiterSitzungen)} Mitarbeiter · ${zahl(n.wirkung.kundenSitzungen)} Kunden${n.wirkung.keycloak ? ` · ${zahl(n.wirkung.keycloak.beendet)} bei Keycloak` : ''}`)] : []),
      karte('ok', 'E-Mail-Versand', 'pausiert', 'Benachrichtigungen gehen weiter'),
      ...(n.wirkung ? [karte(/^nicht angewendet/.test(n.wirkung.firewall || '') ? 'warn' : 'ok', 'Firewall', /angewendet/.test(n.wirkung.firewall || '') && !/^nicht/.test(n.wirkung.firewall || '') ? 'Notfall' : 'unverändert', esc(n.wirkung.firewall || ''))] : []),
    ].join('')}</div>` : '';
    const seit = n ? Date.parse(n.seit) : 0;
    const evNf = n && r.lage ? (r.lage.ereignisse || []).filter((e) => Date.parse(e.t) >= seit) : [];
    const nfVerlauf = n && r.rechte.sehen ? block('Verlauf dieses Notfalls', evNf.length ? `<ul class="sic-evliste">${evNf.map((e) => `<li><span class="ev-zeile"><span class="ev-zeit num">${esc(uhr(e.t))}</span><span class="ev-punkt ${esc(e.stufe)}" aria-hidden="true"></span><span class="ev-text"><span class="sic-nm">${esc(e.s)}</span><span class="sub">${esc(e.n || e.u || '')}</span></span></span></li>`).join('')}</ul>
      <button type="button" class="btn sm" data-geh="ereignisse">Alle Ereignisse</button>` : leer('Seit Beginn des Notfalls noch keine weiteren Ereignisse.')) : '';
    host.innerHTML = `${hero}${n ? lf + kacheln : ''}
      <div class="sic-zwei">
        ${n ? nfVerlauf || '' : ''}
        ${n ? '' : block('Was beim Auslösen passiert', `<ul class="sic-wirkungen">${punkte}</ul>
          <p class="sic-zahlen"><span><strong>${zahl(Z.mitarbeiterSitzungen)}</strong> Mitarbeitersitzungen ohne Administratorrolle</span><span><strong>${zahl(Z.kundenOnline)}</strong> Kunden angemeldet</span><span><strong>${zahl(Z.adminSitzungen)}</strong> Administratorsitzungen</span></p>`)}
        ${block('Gesperrte Bereiche', `<p class="sic-hinweis">Im Notfall antworten diese Anwendungen Mitarbeitern ohne Administratorrolle mit „gesperrt“:</p>
          <p class="sic-chips">${W.bereiche.map((b) => `<span class="sic-chip">${esc(b)}</span>`).join('')}</p>
          <p class="sic-hinweis">Immer erreichbar bleiben das Dashboard, die zentrale Anmeldung und diese Sicherheitszentrale. Ein Server-Werkzeug beendet den Notfall auch ohne Oberfläche: <span class="mono-s">sh deploy/notfall-aus.sh</span>.</p>`)}
      </div>
      ${n ? '' : lf}${unten}`;
    laufzeitStarten();
    entwurfFortsetzen();
  }
  /* Laufzeit des Notfalls (Std:Min:Sek), jede Sekunde neu – nur solange der Reiter Notfall sichtbar ist */
  function laufzeit(seit) {
    const s = Math.max(0, Math.floor((Date.now() - Date.parse(seit)) / 1000));
    const zwei = (x) => String(x).padStart(2, '0');
    return `${zwei(Math.floor(s / 3600))}:${zwei(Math.floor((s % 3600) / 60))}:${zwei(s % 60)}`;
  }
  let laufzeitTimer = 0;
  function laufzeitStarten() {
    clearInterval(laufzeitTimer);
    const el = $('#nf-dauer');
    if (!el) return;
    laufzeitTimer = setInterval(() => { if (!el.isConnected) { clearInterval(laufzeitTimer); return; } el.textContent = laufzeit(el.dataset.seit); }, 1000);
  }

  /* ---------- Leitfaden für den Ernstfall (im Notfall abhakbar) ---------- */
  function leitfadenHtml() {
    const r = S.lage, L = r.leitfaden, n = r.notfall, H = L.haken || {};
    const abhaken = !!n && r.rechte.notfall;
    const fertig = L.schritte.filter((x) => H[x.id]).length;
    const jetzt = n ? (L.schritte.find((x) => !H[x.id]) || {}).id : null;   // im Notfall: der nächste offene Schritt
    const schritte = L.schritte.map((x, i) => {
      const h = H[x.id];
      const marke = abhaken ? `<button type="button" class="lf-marke" data-lf="${esc(x.id)}" aria-pressed="${h ? 'true' : 'false'}" title="${h ? 'Zurücknehmen' : 'Als erledigt abhaken'}"><span class="sr-only">${esc(x.titel)}: ${h ? 'erledigt' : 'offen'}</span>${h ? icon('check') : `<span aria-hidden="true">${i + 1}</span>`}</button>`
        : `<span class="lf-marke" aria-hidden="true">${h ? icon('check') : i + 1}</span>`;
      return `<li class="lf-schritt${h ? ' erledigt' : ''}${x.id === jetzt ? ' jetzt' : ''}">${marke}<div><strong>${esc(x.titel)}</strong>${x.text ? `<p>${esc(x.text)}</p>` : ''}${h ? `<span class="sub">erledigt ${esc(uhr(h.t))} Uhr · ${esc(h.name)}</span>` : ''}</div>${x.id === jetzt ? '<span class="sic-pille warn lf-jetzt">jetzt</span>' : ''}</li>`;
    }).join('');
    const wege = (k) => [k.telefon ? `<a href="tel:${esc(k.telefon.replace(/[^0-9+]/g, ''))}">${icon('telefon')}${esc(k.telefon)}</a>` : '', k.email ? `<a href="mailto:${esc(k.email)}">${icon('post')}${esc(k.email)}</a>` : ''].join('');
    const kontakte = L.kontakte.length ? `<ul class="lf-kontakte">${L.kontakte.map((k) => `<li><span class="sic-av" aria-hidden="true">${esc(initialen(k.name || k.rolle))}</span><div><strong>${esc(k.name || k.rolle)}</strong>${k.name && k.rolle ? `<span class="sub">${esc(k.rolle)}</span>` : ''}<span class="lf-wege">${wege(k)}</span></div></li>`).join('')}</ul>`
      : leer(r.rechte.admin ? 'Noch keine Ansprechpartner – über „Bearbeiten“ Telefonnummern von Geschäftsführung und IT-Dienstleister eintragen.' : 'Noch keine Ansprechpartner eingetragen.');
    const anteil = Math.round((fertig / Math.max(1, L.schritte.length)) * 100);
    const fortschritt = n ? `<div class="lf-stand"><div class="lf-balken" role="progressbar" aria-label="Erledigte Schritte" aria-valuemin="0" aria-valuemax="${L.schritte.length}" aria-valuenow="${fertig}"><span style="--anteil:${anteil}%"></span></div>
      <span><strong>${zahl(fertig)}</strong> von ${zahl(L.schritte.length)} Schritten erledigt${abhaken ? '' : ' <span class="sub">(abhaken: Recht „Notfall auslösen“)</span>'}</span></div>` : '';
    return block(`Leitfaden für den Ernstfall${L.standard ? ' <span class="sic-pille">Vorlage</span>' : ''}`, `${fortschritt}
      <div class="lf-raster"><ol class="lf-schritte">${schritte}</ol><div class="lf-seite"><h4>${icon('telefon')}Ansprechpartner</h4>${kontakte}${L.hinweis ? `<p class="lf-notiz">${esc(L.hinweis)}</p>` : ''}</div></div>
      ${L.geaendert ? `<p class="sic-hinweis">Zuletzt geändert ${esc(zeit(L.geaendert))} Uhr von ${esc(L.von)}.</p>` : ''}`,
    r.rechte.admin ? `<button type="button" class="btn sm" id="lf-bearbeiten">${icon('stift')}Bearbeiten …</button>` : '', 'sic-leitfaden');
  }
  function leitfadenNeu(fokus = '') {
    const el = $('#sic-leitfaden');
    if (!el) return;
    el.outerHTML = leitfadenHtml();
    const f = fokus && $(`#sic-leitfaden [data-lf="${CSS.escape(fokus)}"]`);
    if (f) f.focus();
  }
  function leitfadenDialog() {
    const L = S.lage.leitfaden;
    const sZeile = (x = { id: '', titel: '', text: '' }) => `<div class="lf-ed-zeile" data-id="${esc(x.id)}"><div class="lf-ed-felder">
        <input type="text" class="lf-ed-titel" maxlength="80" placeholder="Überschrift, z. B. Ansprechpartner informieren" value="${esc(x.titel)}" aria-label="Überschrift">
        <textarea class="lf-ed-text" rows="2" maxlength="400" placeholder="Was ist zu tun?" aria-label="Beschreibung">${esc(x.text)}</textarea></div>
      <div class="lf-ed-knoepfe"><button type="button" class="sic-rund klein" data-d="hoch" aria-label="Nach oben" title="Nach oben">${icon('hoch')}</button><button type="button" class="sic-rund klein" data-d="weg" aria-label="Schritt entfernen" title="Entfernen">${icon('x')}</button></div></div>`;
    const kZeile = (k = {}) => `<div class="lf-ed-kontakt">
        <input type="text" class="k-rolle" maxlength="60" placeholder="Aufgabe, z. B. IT-Dienstleister" value="${esc(k.rolle || '')}" aria-label="Aufgabe">
        <input type="text" class="k-name" maxlength="80" placeholder="Name" value="${esc(k.name || '')}" aria-label="Name">
        <input type="tel" class="k-tel" maxlength="40" placeholder="Telefon" value="${esc(k.telefon || '')}" aria-label="Telefon">
        <input type="email" class="k-mail" maxlength="120" placeholder="E-Mail" value="${esc(k.email || '')}" aria-label="E-Mail">
        <button type="button" class="sic-rund klein" data-d="k-weg" aria-label="Ansprechpartner entfernen" title="Entfernen">${icon('x')}</button></div>`;
    dialog(`${dKopf('Leitfaden bearbeiten', 'Schritte und Ansprechpartner für den Ernstfall')}<div class="sic-dinhalt">
        <h4>Schritte</h4><div class="lf-ed-liste" id="lf-ed-schritte">${L.schritte.map(sZeile).join('')}</div>
        <div class="sic-knoepfe"><button type="button" class="btn sm" data-d="s-plus">${icon('plus')}Schritt hinzufügen</button><button type="button" class="btn sm" data-d="vorlage">Vorlage einsetzen</button></div>
        <h4>Ansprechpartner</h4><div class="lf-ed-liste" id="lf-ed-kontakte">${(L.kontakte.length ? L.kontakte : [{}]).map(kZeile).join('')}</div>
        <div class="sic-knoepfe"><button type="button" class="btn sm" data-d="k-plus">${icon('plus')}Ansprechpartner hinzufügen</button></div>
        <label class="sic-feld">Hinweis <small>(optional, z. B. wo die Unterlagen für den Notfall liegen – keine Passwörter eintragen)</small><textarea id="lf-hinweis" rows="2" maxlength="500">${esc(L.hinweis)}</textarea></label>
        <p class="sic-hinweis">Sichtbar für Administratoren und Mitarbeiter mit „Notfall auslösen“ oder „Sicherheit ansehen“.</p></div>
      ${dFuss('<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">Speichern</button>')}`,
    { breit: true, fokus: '.lf-ed-titel', handler: async (a, b) => {
      const liste = $('#lf-ed-schritte', dlg), kliste = $('#lf-ed-kontakte', dlg);
      if (a === 's-plus') { liste.insertAdjacentHTML('beforeend', sZeile()); $('.lf-ed-zeile:last-child .lf-ed-titel', liste).focus(); return; }
      if (a === 'k-plus') { kliste.insertAdjacentHTML('beforeend', kZeile()); $('.lf-ed-kontakt:last-child .k-rolle', kliste).focus(); return; }
      if (a === 'vorlage') { liste.innerHTML = L.vorlage.map(sZeile).join(''); $('.lf-ed-titel', liste).focus(); return; }
      if (a === 'weg' || a === 'k-weg') { const z = b.closest('.lf-ed-zeile, .lf-ed-kontakt'), nb = z.nextElementSibling || z.previousElementSibling; z.remove(); if (nb) $('input', nb).focus(); return; }
      if (a === 'hoch') { const z = b.closest('.lf-ed-zeile'); if (z.previousElementSibling) z.parentNode.insertBefore(z, z.previousElementSibling); b.focus(); return; }
      if (a !== 'submit') return;
      const schritte = $$('.lf-ed-zeile', dlg).map((z) => ({ id: z.dataset.id, titel: $('.lf-ed-titel', z).value.trim(), text: $('.lf-ed-text', z).value.trim() })).filter((x) => x.titel || x.text);
      const kontakte = $$('.lf-ed-kontakt', dlg).map((z) => ({ rolle: $('.k-rolle', z).value.trim(), name: $('.k-name', z).value.trim(), telefon: $('.k-tel', z).value.trim(), email: $('.k-mail', z).value.trim() }))
        .filter((k) => k.rolle || k.name || k.telefon || k.email);
      const wieVorlage = JSON.stringify(schritte.map((x) => [x.titel, x.text])) === JSON.stringify(L.vorlage.map((x) => [x.titel, x.text]));
      const r = await api('sicherheit_leitfaden', { body: { schritte, standard: wieVorlage, kontakte, hinweis: $('#lf-hinweis', dlg).value } });
      S.lage.leitfaden = { ...r.leitfaden, haken: L.haken || {} };
      dialogZu(); toast('Leitfaden gespeichert.');
      if (S.tab === 'notfall') leitfadenNeu(); else if (S.tab === 'lage') lageTab();
    } });
  }

  /* ---------- Probealarm (Übung ohne Wirkung) ---------- */
  function probenHtml() {
    const l = S.lage.proben || [];
    const stufe = (p) => (p.punkte.some((x) => x.stufe === 'bad') ? 'bad' : p.ok < p.gesamt ? 'warn' : 'ok');
    const zeilen = l.map((p, i) => `<tr class="sic-klick" data-probe="${i}" tabindex="0"><td class="num-s">${esc(zeit(p.t))}</td><td>${esc(p.vonName)}</td>
      <td><span class="sic-pille ${stufe(p)}">${zahl(p.ok)} / ${zahl(p.gesamt)}</span></td>
      <td>${p.mail.ok ? `${zahl(p.mail.ok)} von ${zahl(p.mail.an)}` : '<span class="sic-pille bad">nicht zugestellt</span>'}</td>
      <td>${p.quittiert.length ? `${zahl(p.quittiert.length)} <span class="sub">· schnellste ${esc(dauerSek(Math.min(...p.quittiert.map((q) => q.sek))))}</span>` : '<span class="sub">noch niemand</span>'}</td></tr>`).join('');
    return block('Übungen <span class="sub">Probealarm</span>', zeilen ? `<div class="sic-tabrahmen"><table class="sic-tabelle"><thead><tr><th>Zeit</th><th>ausgelöst von</th><th>Bereitschaft</th><th>Meldung</th><th>gesehen</th></tr></thead><tbody>${zeilen}</tbody></table></div>`
      : leer('Noch kein Probealarm. Er prüft die Bereitschaft und schickt eine Test-Meldung – ohne jede Wirkung.'),
    S.rechte.notfall && !S.lage.notfall ? `<button type="button" class="btn sm" data-probe-start>${icon('uebung')}Probealarm …</button>` : '');
  }
  function probeDialog() {
    if (S.lage.notfall) { toast('Während eines Notfalls ist kein Probealarm möglich.', true); return; }
    dialog(`${dKopf('Probealarm', 'Übung für den Ernstfall – ohne jede Wirkung')}<div class="sic-dinhalt">
        <p>Der Probealarm ändert nichts: Niemand wird gesperrt oder abgemeldet, Kunden merken nichts.</p>
        <ul class="sic-wirkungen klein uebung">
          <li>${icon('check')}<span>Bereitschaft prüfen: Empfänger der Meldung, Vertretung beim Auslösen und Beenden, zweiter Faktor der Administratoren, Ansprechpartner, Schutz vor Selbstaussperrung, Datensicherung.</span></li>
          <li>${icon('glocke')}<span>Test-Meldung an die Empfänger der Sicherheitsereignisse. Wer sie sieht, bestätigt hier mit „Gesehen“ – die Reaktionszeit wird festgehalten.</span></li></ul></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">${icon('uebung')}Probealarm starten</button>`)}`,
    { handler: async (a) => {
      if (a !== 'submit') return;
      const r = await api('sicherheit_probealarm', { body: {} });
      S.lage.proben = r.proben;
      probeErgebnis(r.probe, true);
      if (S.tab === 'notfall') notfallTab(); else if (S.tab === 'lage') lageTab();
    } });
  }
  function probeErgebnis(p, neu = false) {
    const w = p.punkte.some((x) => x.stufe === 'bad') ? 'bad' : p.ok < p.gesamt ? 'warn' : 'ok';
    const anteil = Math.round((p.ok / Math.max(1, p.gesamt)) * 100);
    const punkte = p.punkte.map((x) => `<li>${punkt(x.stufe)}<div><strong>${esc(x.titel)}</strong><span>${esc(x.text)}</span>${x.hinweis ? `<span class="sub">${esc(x.hinweis)}</span>` : ''}</div></li>`).join('');
    const gesehen = p.quittiert.length ? `<ul class="sic-verlauf">${p.quittiert.map((q) => `<li>${icon('check')}<strong>${esc(q.name)}</strong><span class="sub">nach ${esc(dauerSek(q.sek))}</span></li>`).join('')}</ul>`
      : leer(neu ? 'Die Empfänger bestätigen die Meldung hier mit „Gesehen“ – danach steht hier, wie schnell.' : 'Noch niemand hat den Probealarm bestätigt.');
    dialog(`${dKopf(neu ? 'Probealarm ausgeführt' : `Probealarm vom ${datum(p.t)}`, `${esc(zeit(p.t))} Uhr · ${esc(p.vonName)} · keine Wirkung`)}<div class="sic-dinhalt">
        <div class="pb-kopf ${w}"><div class="sic-ring" style="--wert:${anteil}" role="img" aria-label="${zahl(p.ok)} von ${zahl(p.gesamt)} Prüfpunkten in Ordnung"><span>${zahl(p.ok)}<small>/${zahl(p.gesamt)}</small></span></div>
          <div><strong>${w === 'ok' ? 'Bereit für den Ernstfall' : w === 'warn' ? 'Bereit, mit Lücken' : 'Lücken mit Handlungsbedarf'}</strong>
          <span>${p.mail.ok ? `Test-Meldung an ${plural(p.mail.ok, 'Empfänger', 'Empfänger')} zugestellt` : `Test-Meldung nicht zugestellt${p.mail.fehler ? ` – ${esc(p.mail.fehler)}` : ''}`}</span></div></div>
        <ul class="pb-punkte">${punkte}</ul><h4>Gesehen</h4>${gesehen}</div>
      ${dFuss('<button type="button" class="btn primary" data-d="zu">Schließen</button>')}`, { breit: true });
  }
  function dauerText(a, b) {
    const s = Math.max(0, (new Date(b) - new Date(a)) / 1000);
    return s >= 3600 ? `${Math.floor(s / 3600)} Std. ${Math.floor((s % 3600) / 60)} Min.` : `${Math.max(1, Math.floor(s / 60))} Min.`;
  }
  $('#tab-notfall').addEventListener('click', (e) => {
    if (e.target.closest('#nf-an')) notfallAuslosen();
    if (e.target.closest('#nf-aus')) notfallBeenden();
    if (e.target.closest('#lf-bearbeiten')) leitfadenDialog();
    const h = e.target.closest('[data-lf]');
    if (h) {
      lauf(h, async () => {
        const id = h.dataset.lf;
        const r = await api('sicherheit_leitfaden_haken', { body: { schritt: id, erledigt: h.getAttribute('aria-pressed') !== 'true' } });
        S.lage.leitfaden.haken = r.haken;
        leitfadenNeu(id);
      });
      return;
    }
    const v = e.target.closest('[data-nfv]');
    if (v) notfallVerlaufDialog(S.lage.verlauf[+v.dataset.nfv]);
    const pr = e.target.closest('[data-probe]');
    if (pr) probeErgebnis(S.lage.proben[+pr.dataset.probe]);
  });
  $('#tab-notfall').addEventListener('keydown', (e) => {
    if (e.key !== 'Enter') return;
    if (e.target.matches('[data-nfv]')) notfallVerlaufDialog(S.lage.verlauf[+e.target.dataset.nfv]);
    if (e.target.matches('[data-probe]')) probeErgebnis(S.lage.proben[+e.target.dataset.probe]);
  });
  /* überall: Probealarm starten, als gesehen bestätigen, Wochenbericht ansehen */
  document.addEventListener('click', (e) => {
    const ps = e.target.closest('[data-probe-start]');
    if (ps) { probeDialog(); return; }
    const ns = e.target.closest('[data-notfall-start]');
    if (ns) { if (S.lage && !S.lage.notfall) notfallAuslosen(); return; }
    const g = e.target.closest('#probe-gesehen');
    if (g) {
      lauf(g, async () => {
        const r = await api('sicherheit_probe_gesehen', { body: { id: g.dataset.id } });
        S.lage.probeOffen = null; probeBand();
        const i = (S.lage.proben || []).findIndex((p) => p.id === r.probe.id);
        if (i >= 0) S.lage.proben[i] = r.probe;
        toast('Danke – Ihre Bestätigung ist vermerkt.');
        if (S.tab === 'notfall') notfallTab();
      });
      return;
    }
    const br = e.target.closest('[data-bericht]');
    if (br) lauf(br, berichtDialog);
  });
  function notfallVerlaufDialog(v) {
    const w = v.wirkung || {};
    const hk = Object.entries(v.haken || {}).sort((a, b) => String(a[1].t).localeCompare(String(b[1].t)));
    const titel = (id) => (S.lage.leitfaden.schritte.find((x) => x.id === id) || { titel: id }).titel;
    const haken = hk.length ? `<h4>Leitfaden <span class="sub">${plural(hk.length, 'Schritt', 'Schritte')} abgehakt</span></h4><ul class="sic-verlauf">${hk.map(([id, x]) => `<li>${icon('check')}<strong>${esc(titel(id))}</strong><span class="sub">${esc(uhr(x.t))} Uhr · ${esc(x.name)}</span></li>`).join('')}</ul>` : '';
    dialog(`${dKopf('Notfall vom ' + datum(v.seit), `${esc(zeit(v.seit))} – ${esc(zeit(v.bis))} Uhr · ${esc(dauerText(v.seit, v.bis))}`)}<div class="sic-dinhalt"><dl class="sic-dl">
      <dt>Grund</dt><dd>${esc(v.grund)}</dd><dt>ausgelöst von</dt><dd>${esc(v.von)}</dd><dt>beendet von</dt><dd>${esc(v.beendetVon)}</dd>${v.notiz ? `<dt>Notiz</dt><dd>${esc(v.notiz)}</dd>` : ''}
      <dt>Sitzungen beendet</dt><dd>${zahl(w.mitarbeiterSitzungen)} Mitarbeiter · ${zahl(w.kundenSitzungen)} Kunden</dd><dt>Firewall</dt><dd>${esc(w.firewall || '—')}</dd>
      <dt>Einstellungen danach</dt><dd>${esc(v.einstellungen || '—')}</dd></dl>${haken}</div>${dFuss('<button type="button" class="btn primary" data-d="zu">Schließen</button>')}`);
  }
  /* Auslösen in Schritten: 1 Wirkung → 2 Grund, Optionen, Bestätigungswort → 3 Bestätigung (Passwort bzw. erneute Anmeldung) */
  function notfallAuslosen(entwurf = null) {
    const W = S.lage.wirkungen, Z = W.zahlen;
    const e = entwurf || { grund: '', kundentext: '', firewall: true, admins: false, keycloak: false };
    const schritt1 = () => dialog(`${dKopf('Notfall auslösen', 'Schritt 1 von 2 · Wirkung', 'gefahr')}<div class="sic-dinhalt">
        <p>Der Notfallmodus greift sofort und überall:</p>
        <ul class="sic-wirkungen klein">${W.punkte.map(([k, t]) => `<li>${icon(WIRKUNG_ICON[k] || 'check')}<span>${esc(t)}</span></li>`).join('')}</ul>
        <p class="sic-meldung warn">Betroffen jetzt: <strong>${plural(Z.mitarbeiterSitzungen, 'Mitarbeitersitzung', 'Mitarbeitersitzungen')}</strong> und <strong>${plural(Z.kundenOnline, 'angemeldeter Kunde', 'angemeldete Kunden')}</strong>.</p></div>
      ${dFuss('<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn gefahr">Weiter</button>')}`,
    { breit: true, handler: async (a) => { if (a === 'submit') schritt2(); } });
    const schritt2 = (hinweis = '') => dialog(`${dKopf('Notfall auslösen', 'Schritt 2 von 2 · Grund und Bestätigung', 'gefahr')}<div class="sic-dinhalt">
        ${hinweis ? `<p class="sic-meldung ok">${hinweis}</p>` : ''}
        <label class="sic-feld">Grund <small>(Pflicht, nur für Administratoren und Berechtigte sichtbar)</small><textarea id="nf-grund" rows="2" maxlength="300" required placeholder="z. B. Verdacht auf fremden Zugriff auf ein Konto">${esc(e.grund)}</textarea></label>
        <label class="sic-feld">Hinweis für Kunden <small>(optional, neutral formulieren)</small><textarea id="nf-kunde" rows="2" maxlength="500" placeholder="Unser Angebotsportal ist vorübergehend nicht erreichbar. Bitte versuchen Sie es später erneut.">${esc(e.kundentext)}</textarea></label>
        <fieldset class="sic-optionen"><legend>Optionen</legend>
          <label class="sic-check"><input type="checkbox" id="nf-fw"${e.firewall ? ' checked' : ''}><span>Firewall auf Vorlage „Notfall“ <span class="sub">(bisherige Einstellungen werden gesichert und beim Beenden wiederhergestellt)</span></span></label>
          ${S.rechte.admin ? `<label class="sic-check"><input type="checkbox" id="nf-admins"${e.admins ? ' checked' : ''}><span>Auch andere Administratoren abmelden <span class="sub">(z. B. bei Verdacht auf ein Administratorkonto; Ihre Sitzung bleibt)</span></span></label>` : ''}
          ${W.keycloak ? `<label class="sic-check"><input type="checkbox" id="nf-kc"${e.keycloak ? ' checked' : ''}><span>Sitzungen in der zentralen Anmeldung beenden <span class="sub">(betroffene Konten werden bei Keycloak abgemeldet)</span></span></label>` : ''}
        </fieldset>
        <div class="sic-halten-bereich"><button type="button" class="sic-halten" id="nf-los" aria-describedby="nf-halten-hinweis"><span class="sic-halten-fuell" aria-hidden="true"></span>
          <span class="sic-halten-text">${icon('alarm')}<span id="nf-los-text">Gedrückt halten: Notfall auslösen</span></span></button>
          <p class="sic-hinweis" id="nf-halten-hinweis">1,5 Sekunden gedrückt halten – mit Maus, Finger oder Leertaste. Ein kurzer Klick löst nichts aus.</p></div></div>
      ${dFuss('<button type="button" class="btn" data-d="zurueck">Zurück</button><button type="button" class="btn" data-d="zu">Abbrechen</button>')}`,
    { breit: true, fokus: e.grund ? '#nf-los' : '#nf-grund', handler: async (a) => {
      const lies = () => ({ grund: $('#nf-grund', dlg).value.trim(), kundentext: $('#nf-kunde', dlg).value.trim(), firewall: $('#nf-fw', dlg).checked,
        admins: !!($('#nf-admins', dlg) || {}).checked, keycloak: !!($('#nf-kc', dlg) || {}).checked });
      if (a === 'zurueck') { Object.assign(e, lies()); schritt1(); return; }
      if (a !== 'ausloesen') return;   // nur nach vollständigem Gedrückthalten (haltenStart), nie per Klick oder Eingabetaste
      const b = lies();
      if (b.grund.length < 5) { dFehler('Bitte kurz den Grund angeben (mindestens 5 Zeichen).'); $('#nf-grund', dlg).focus(); return; }
      Object.assign(e, b);
      const r = await aufruf('sicherheit_notfall_an', { body: { ...b, wort: W.wort } }, [NOTFALL_ENTWURF, b]);
      try { sessionStorage.removeItem(NOTFALL_ENTWURF); } catch { /* ohne Speicher */ }
      const w = r.notfall.wirkung || {};
      dialog(`${dKopf('Notfallmodus ist aktiv', esc(zeit(r.notfall.seit)) + ' Uhr', 'gefahr')}<div class="sic-dinhalt">
          <dl class="sic-dl"><dt>Mitarbeitersitzungen beendet</dt><dd>${zahl(w.mitarbeiterSitzungen)}</dd><dt>Kundensitzungen beendet</dt><dd>${zahl(w.kundenSitzungen)}</dd>
          <dt>Firewall</dt><dd>${esc(w.firewall || '—')}</dd></dl>
          <p class="sic-hinweis">Die Empfänger der Sicherheitsereignisse werden benachrichtigt. Beenden können nur Administratoren – hier im Reiter „Notfall“ oder auf dem Server.</p></div>
        ${dFuss('<button type="button" class="btn primary" data-d="zu">Verstanden</button>')}`);
      toast('Notfallmodus ausgelöst.');
      await notfallTab();
    } });
    if (entwurf) schritt2('Anmeldung bestätigt – bitte den Knopf erneut gedrückt halten, um auszulösen.'); else schritt1();
  }
  /* Gedrückt halten statt Bestätigungswort: 1,5 s mit Maus, Finger oder Leertaste/Eingabetaste; loslassen bricht ab */
  const HALTEN_MS = 1500;
  let halten = null;
  function haltenStart(k) {
    if (halten || k.disabled) return;
    const g = $('#nf-grund', dlg);
    if (g && g.value.trim().length < 5) { dFehler('Bitte kurz den Grund angeben (mindestens 5 Zeichen).'); g.focus(); return; }
    dFehler('');
    k.classList.remove('fertig'); k.classList.add('haelt');
    const text = $('#nf-los-text', dlg), beginn = performance.now();
    const schritt = (jetzt) => {
      const anteil = Math.min(1, (jetzt - beginn) / HALTEN_MS);
      k.style.setProperty('--anteil', (anteil * 100).toFixed(1) + '%');
      if (anteil < 1) { if (text) text.textContent = `Weiter halten … ${Math.round(anteil * 100)} %`; halten.raf = requestAnimationFrame(schritt); return; }
      halten = null;
      k.classList.remove('haelt'); k.classList.add('fertig');
      if (text) text.textContent = 'Wird ausgelöst …';
      if (dlgHandler) lauf(k, async () => {
        try { await dlgHandler('ausloesen', k, $('form', dlg)); } finally {
          if (k.isConnected) { k.classList.remove('fertig'); k.style.setProperty('--anteil', '0%'); if (text) text.textContent = 'Gedrückt halten: Notfall auslösen'; }
        }
      });
    };
    halten = { raf: requestAnimationFrame(schritt), knopf: k };
  }
  function haltenStopp() {
    if (!halten) return;
    cancelAnimationFrame(halten.raf);
    const k = halten.knopf; halten = null;
    k.classList.remove('haelt'); k.style.setProperty('--anteil', '0%');
    const text = $('#nf-los-text', dlg); if (text) text.textContent = 'Gedrückt halten: Notfall auslösen';
  }
  dlg.addEventListener('pointerdown', (e) => { const k = e.target.closest('#nf-los'); if (k && e.button === 0) { e.preventDefault(); k.focus(); haltenStart(k); } });
  dlg.addEventListener('pointerup', haltenStopp);
  dlg.addEventListener('pointercancel', haltenStopp);
  dlg.addEventListener('pointerout', (e) => { if (halten && e.target.closest('#nf-los') && !(e.relatedTarget && e.relatedTarget.closest && e.relatedTarget.closest('#nf-los'))) haltenStopp(); });
  dlg.addEventListener('keydown', (e) => { if (e.target.id === 'nf-los' && (e.key === ' ' || e.key === 'Enter')) { e.preventDefault(); if (!e.repeat) haltenStart(e.target); } });
  dlg.addEventListener('keyup', (e) => { if (e.target.id === 'nf-los' && (e.key === ' ' || e.key === 'Enter')) haltenStopp(); });
  dlg.addEventListener('close', haltenStopp);
  function entwurfFortsetzen() {
    let e = null;
    try { e = JSON.parse(sessionStorage.getItem(NOTFALL_ENTWURF) || 'null'); } catch { /* ohne Speicher */ }
    if (!e) return;
    try { sessionStorage.removeItem(NOTFALL_ENTWURF); } catch { /* ohne Speicher */ }
    if (!S.lage.notfall && S.rechte.notfall && !dlg.open) notfallAuslosen(e);
  }
  function notfallBeenden() {
    const n = S.lage.notfall;
    dialog(`${dKopf('Notfall beenden', 'Mitarbeiter und Kunden haben danach wieder Zugang')}<div class="sic-dinhalt">
        <p>Vor dem Beenden prüfen: betroffene Konten gesperrt bzw. Passwörter geändert, Protokoll und Dateiprüfung durchgesehen.</p>
        ${n.firewallGesichert && n.optionen && n.optionen.firewall ? `<label class="sic-check"><input type="checkbox" id="nf-zurueck" checked><span>Sicherheits- und Firewall-Einstellungen wie vor dem Notfall wiederherstellen <span class="sub">(ohne Haken bleiben die strengen Einstellungen)</span></span></label>`
          : '<p class="sub">Die Firewall wurde beim Auslösen nicht geändert.</p>'}
        <label class="sic-feld">Notiz <small>(optional, z. B. Ursache und Maßnahmen)</small><textarea id="nf-notiz" rows="2" maxlength="300"></textarea></label>
        <p class="sic-hinweis">Eine von Hand eingeschaltete Wartung der Angebotsseite bleibt bestehen. Gesperrte Adressen bleiben gesperrt.</p></div>
      ${dFuss('<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">Notfall beenden</button>')}`,
    { breit: true, handler: async (a) => {
      if (a !== 'submit') return;
      const r = await aufruf('sicherheit_notfall_aus', { body: { firewall: !!($('#nf-zurueck', dlg) || {}).checked, notiz: $('#nf-notiz', dlg).value } });
      dialog(`${dKopf('Notfall beendet', `Dauer ${esc(r.ende.dauer)}`)}<div class="sic-dinhalt"><dl class="sic-dl"><dt>Einstellungen</dt><dd>${esc(r.ende.einstellungen)}</dd></dl>
          <p class="sic-hinweis">Alle Mitarbeiter können wieder arbeiten; die Angebotsseite ist wieder erreichbar (sofern keine Wartung von Hand eingeschaltet ist).</p></div>
        ${dFuss('<button type="button" class="btn primary" data-d="zu">Schließen</button>')}`);
      toast('Notfallmodus beendet.');
      await notfallTab();
    } });
  }

  /* ======================= Firewall & Sperren ======================= */
  const FILTER = [['', 'Alle'], ['gesperrt', 'Abgewiesen'], ['anmeldung', 'Anmeldungen'], ['fehler', 'Fehler']];
  const fwSchluessel = (e) => [e.t, e.ip, e.m, e.q, e.st, e.why, e.ua, e.u, e.n || 1].join('\u0001');
  const fwKlasse = (e) => (/^(Gesperrt|Firewall|Falle)/.test(e.why || '') || e.st === 403 ? 'bad' : e.st >= 400 || /fehlgeschlagen/.test(e.why || '') ? 'warn' : 'ok');
  const fwZeile = (e) => `<tr class="fw-row ${fwKlasse(e)}"><td class="num-s">${esc(sekUhr(e.t))}<div class="sub">${esc(new Date(e.t * 1000).toLocaleDateString('de-DE'))}</div></td>
    <td class="mono-s">${esc(e.ip)}${e.cc ? `<div class="sub">${esc(land(e.cc))}</div>` : ''}</td>
    <td><span class="sic-st">${e.st || '—'}</span> ${esc(e.why || 'Anfrage')}${e.n > 1 ? ` <span class="sub">(${zahl(e.n)}×)</span>` : ''}<div class="sub mono-s fw-q">${esc(e.m || '')} ${esc(e.q || '')}</div></td>
    <td class="fw-ua">${esc(geraet(e.ua))}${e.u ? `<div class="sub">${esc(e.u)}</div>` : ''}</td>
    <td class="act">${e.ip && e.ip !== S.fw.meineIp ? `<button type="button" class="btn sm" data-fw="sperr-ip" data-ip="${esc(e.ip)}">${icon('lock')}Sperren</button>` : ''}</td></tr>`;
  const verkehr = (l) => l.length ? `<div class="sic-tabrahmen"><table class="sic-tabelle fw-verkehr"><thead><tr><th>Zeit</th><th>Adresse</th><th>Vorgang</th><th>Gerät</th><th class="act"><span class="sr-only">Aktion</span></th></tr></thead><tbody id="fw-rows">${l.map(fwZeile).join('')}</tbody></table></div>`
    : leer('Noch keine Einträge. Angezeigt werden abgewiesene und auffällige Anfragen, Anmeldungen und – während eines Mitschnitts – alle Anfragen.');
  async function fwLaden(mitSec = true) {   // Filterwechsel: nur der Verkehr neu (mitSec = false)
    const [fw, sec] = await Promise.all([api('fw_status', { query: S.fwFilter ? '&filter=' + S.fwFilter : '' }), mitSec || !S.sec ? api('security_status') : Promise.resolve(S.sec)]);
    S.fw = fw; S.sec = sec;
    if (fw.feedVeraltet) {
      api('fw_feed_auffrischen', { body: {} }).then((r) => { if (r && r.aufgefrischt && S.fw) { S.fw.feed = r.feed; if (S.tab === 'firewall' && !$('#tab-firewall').contains(document.activeElement)) fwZeichnen(); } }).catch(() => {});
    }
  }
  async function firewallTab() {
    if (!S.fw) $('#tab-firewall').innerHTML = '<div class="sic-laden"><span class="sic-spinner"></span>Firewall wird geladen …</div>';
    await fwLaden();
    fwZeichnen();
    S.fwTimer = setInterval(fwLive, 5000);
  }
  function fwZeichnen() {
    const d = S.fw, F = d.fw, Z = d.zahlen, sec = S.sec;
    const feed = d.feed ? `${zahl(d.feed.anzahl)} Netze · Stand ${esc(zeit(d.feed.stand))}` : 'noch nicht geladen';
    const sperren = [
      ...d.manuell.map((e) => `<tr><td class="mono-s">${esc(e.ip)}</td><td>von Hand${e.grund ? ' – ' + esc(e.grund) : ''}<div class="sub">${esc(e.von || '')} · ${esc(zeit(e.t))}</div></td><td class="num-s">${e.bis ? 'bis ' + esc(sekZeit(e.bis)) : 'dauerhaft'}</td><td class="act"><button type="button" class="btn sm" data-fw="frei" data-ip="${esc(e.ip)}">Freigeben</button></td></tr>`),
      ...d.auto.map((e) => `<tr><td class="mono-s">${esc(e.ip)}</td><td>automatisch – ${esc(e.grund || '')}<div class="sub">${esc(zeit(e.t))}${e.n > 1 ? ' · ' + e.n + '. Sperre' : ''}</div></td><td class="num-s">bis ${esc(sekZeit(e.bis))}</td><td class="act"><button type="button" class="btn sm" data-fw="frei" data-ip="${esc(e.ip)}">Freigeben</button></td></tr>`)].join('');
    const bremse = sec.blockedIps.map((x) => `<tr><td class="mono-s">${esc(x.ip)}</td><td>${x.n ? plural(x.n, 'Fehlversuch', 'Fehlversuche') : ''}<div class="sub">${x.bereich === 'kunde' ? 'Kunden-Anmeldung' : 'Mitarbeiter-Anmeldung'}</div></td><td>${x.until ? `<span class="sic-pille bad">bis ${esc(uhr(x.until))} Uhr</span>` : '<span class="sub">beobachtet</span>'}</td><td class="act"><button type="button" class="btn sm" data-fw="bremse" data-key="${esc(x.key)}" data-ip="${esc(x.ip)}">Aufheben</button></td></tr>`).join('');
    const laender = (sec.geoStats || []).map((x) => `<tr><td>${esc(land(x.cc))} <span class="sub">${esc(x.cc)}</span></td><td class="num-s">${zahl(x.n)}</td><td class="num-s">${esc(zeit(x.last))}</td></tr>`).join('');
    $('#tab-firewall').innerHTML = `
      <div class="sic-karten vier">
        ${karte(F.waf === 'sperren' ? 'ok' : F.waf === 'protokoll' ? 'warn' : 'bad', 'Firewall', esc(d.modi[F.waf] || F.waf), F.autoSperre ? `sperrt nach ${plural(F.treffer, 'Treffer', 'Treffern')} für ${esc(DAUER[F.sperrMinuten] || F.sperrMinuten + ' Min.')}` : 'automatische Sperre aus')}
        ${karte(Z.angriffe ? 'warn' : 'ok', 'Angriffsversuche (24 h)', zahl(Z.angriffe), `${zahl(Z.abgewiesen)} Anfragen gesperrter Adressen abgewiesen`)}
        ${karte(Z.gesperrteAdressen ? 'warn' : 'ok', 'Gesperrte Adressen', zahl(Z.gesperrteAdressen), `${zahl(Z.anmeldungFehl)} fehlgeschlagene Anmeldungen (24 h)`)}
        ${karte(F.feed && d.feed ? 'ok' : 'warn', 'Bedrohungsliste', F.feed ? 'aktiv' : 'aus', feed)}
      </div>
      <div class="sic-leiste"><button type="button" class="btn" data-fw="einstellungen">${icon('wand')}Firewall-Einstellungen …</button><button type="button" class="btn" data-fw="sperren-neu">${icon('lock')}Adresse sperren …</button>
        <span class="sub">Ihre Adresse: <span class="mono-s">${esc(d.meineIp)}</span> – interne und freigegebene Adressen werden nie gesperrt.</span></div>
      ${block('Live-Verkehr', `<div id="fw-verkehr">${verkehr(d.verkehr)}</div>`, `<div class="sic-filter" role="group" aria-label="Filter">${FILTER.map(([k, l]) => `<button type="button" class="btn sm${S.fwFilter === k ? ' an' : ''}" data-fw-filter="${k}" aria-pressed="${S.fwFilter === k}">${l}</button>`).join('')}</div>
        <span class="sic-live" aria-live="polite">${d.mitschnitt ? `${icon('eye')}Mitschnitt bis ${esc(sekUhr(d.mitschnitt))}` : '<span class="sic-livepunkt"></span>alle 5 Sekunden'}</span>`)}
      <div class="sic-zwei">
        ${block('Gesperrte Adressen <span class="sub">Firewall</span>', sperren ? `<div class="sic-tabrahmen"><table class="sic-tabelle"><thead><tr><th>Adresse</th><th>Grund</th><th>Dauer</th><th class="act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${sperren}</tbody></table></div>${d.autoGesamt > d.auto.length ? `<p class="sic-hinweis">… und ${d.autoGesamt - d.auto.length} weitere automatische Sperren.</p>` : ''}` : leer('Derzeit ist keine Adresse gesperrt.'))}
        ${block('Anmeldebremse <span class="sub">Fehlversuche je Adresse</span>', bremse ? `<div class="sic-tabrahmen"><table class="sic-tabelle"><thead><tr><th>Adresse</th><th>Versuche</th><th>Status</th><th class="act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${bremse}</tbody></table></div>` : leer('Keine beobachteten oder gesperrten Adressen.'), '', 'sic-bremse')}
      </div>
      ${laender ? block(`Abgewiesene Zugriffe nach Land <span class="sub">7 Tage: ${zahl(sec.geoBlocked7)}</span>`, `<div class="sic-tabrahmen"><table class="sic-tabelle"><thead><tr><th>Land</th><th class="num-s">gesamt</th><th class="num-s">zuletzt</th></tr></thead><tbody>${laender}</tbody></table></div>`, '<button type="button" class="btn sm" data-fw="geo-null">Zurücksetzen</button>') : ''}`;
    S.fwLetzte = d.verkehr.length ? d.verkehr[0].t : Math.floor(Date.now() / 1000);
  }
  async function fwLive() {
    if (S.tab !== 'firewall' || document.hidden || !S.fw) return;
    try {
      const r = await api('fw_verkehr', { query: `&seit=${Math.max(0, S.fwLetzte - 1)}${S.fwFilter ? '&filter=' + S.fwFilter : ''}` });
      const gesehen = new Set(S.fw.verkehr.map(fwSchluessel));
      const neu = r.verkehr.filter((e) => !gesehen.has(fwSchluessel(e)));
      if (!neu.length) return;
      S.fwLetzte = Math.max(S.fwLetzte, neu[0].t);
      S.fw.verkehr = [...neu, ...S.fw.verkehr].slice(0, 200);
      const v = $('#fw-verkehr');
      if (v) v.innerHTML = verkehr(S.fw.verkehr);
    } catch { /* nächster Versuch */ }
  }
  function fwUebernehmen(r) { if (r) { S.fw = { ...S.fw, ...r }; if (S.tab === 'firewall') fwZeichnen(); } }
  $('#tab-firewall').addEventListener('click', (e) => {
    const f = e.target.closest('[data-fw-filter]');
    if (f) { S.fwFilter = f.dataset.fwFilter; lauf(f, async () => { await fwLaden(false); fwZeichnen(); }); return; }
    const b = e.target.closest('[data-fw]');
    if (!b) return;
    const a = b.dataset.fw, ip = b.dataset.ip;
    if (a === 'einstellungen') fwEinstellungen();
    if (a === 'sperren-neu') fwSperrDialog('');
    if (a === 'sperr-ip') fwSperrDialog(ip, 'aus dem Live-Verkehr');
    if (a === 'frei') lauf(null, async () => {
      if (!(await frage('Sperre aufheben?', `Die Adresse <span class="mono-s">${esc(ip)}</span> kann danach wieder zugreifen.`, 'Freigeben'))) return;
      fwUebernehmen(await aufruf('fw_freigeben', { body: { ip } })); dialogZu(); toast('Sperre aufgehoben.');
    });
    if (a === 'bremse') lauf(null, async () => {
      if (!(await frage('Anmeldebremse aufheben?', `Fehlversuche und Sperre der Adresse <span class="mono-s">${esc(ip)}</span> werden zurückgesetzt.`, 'Aufheben'))) return;
      await aufruf('ip_unblock', { body: { key: b.dataset.key } }); dialogZu(); S.sec = null; toast('Sperre aufgehoben.'); await firewallTab();
    });
    if (a === 'geo-null') lauf(null, async () => {
      if (!(await frage('Länderstatistik zurücksetzen?', 'Die Zähler der abgewiesenen Zugriffe je Land werden gelöscht. Die Ländersperre selbst bleibt unverändert.', 'Zurücksetzen'))) return;
      await aufruf('geo_clear_stats', { body: {} }); dialogZu(); S.sec = null; toast('Zähler zurückgesetzt.'); await firewallTab();
    });
  });
  function fwSperrDialog(ip, grund = '') {
    dialog(`${dKopf(ip ? 'Adresse sperren' : 'Adresse oder Bereich sperren', 'gilt für Eingabebereich, Angebotsseite, App und alle Anwendungen')}<div class="sic-dinhalt">
        <label class="sic-feld">Adresse oder Bereich<input id="fs-ip" class="mono-s" value="${esc(ip)}" placeholder="203.0.113.7 oder 203.0.113.0/24" maxlength="49" required></label>
        <div class="sic-felder zwei"><label class="sic-feld">Dauer<select id="fs-min"><option value="0">dauerhaft</option>${Object.entries(DAUER).map(([v, l]) => `<option value="${v}"${v === '1440' ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
          <label class="sic-feld">Grund <small>(optional)</small><input id="fs-grund" maxlength="80" value="${esc(grund)}"></label></div></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn gefahr">${icon('lock')}Sperren</button>`)}`,
    { fokus: ip ? '#fs-min' : '#fs-ip', handler: async (a) => {
      if (a !== 'submit') return;
      fwUebernehmen(await aufruf('fw_sperren', { body: { ip: $('#fs-ip', dlg).value.trim(), minuten: +$('#fs-min', dlg).value, grund: $('#fs-grund', dlg).value } }));
      dialogZu(); toast('Adresse gesperrt.');
    } });
  }
  function fwEinstellungen() {
    const d = S.fw, F = d.fw;
    const feed = d.feed ? `${zahl(d.feed.anzahl)} Netze · Stand ${esc(zeit(d.feed.stand))}` : 'noch nicht geladen';
    dialog(`${dKopf('Firewall und automatische Sperre')}<div class="sic-dinhalt" id="fw-form">
        <label class="sic-feld">Angriffsmuster in Anfragen<select name="waf">${Object.entries(d.modi).map(([k, l]) => `<option value="${k}"${F.waf === k ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>
          <small>Erkennt eingeschleuste Befehle (SQL, Skripte, Pfade, Code) und bekannte Angriffswerkzeuge. Anfragen angemeldeter Mitarbeiter werden nur in der Adresse geprüft.</small></label>
        <div class="sic-feld"><span>Automatisch sperren</span><div class="sic-inline"><label class="sic-check"><input type="checkbox" name="autoSperre"${F.autoSperre ? ' checked' : ''}><span>nach</span></label>
          <label><input type="number" name="treffer" min="1" max="50" value="${F.treffer}"> Treffern in 10 Minuten</label>
          <label>für <select name="sperrMinuten">${d.sperrMinuten.map((v) => `<option value="${v}"${F.sperrMinuten === v ? ' selected' : ''}>${esc(DAUER[v] || v + ' Min.')}</option>`).join('')}</select></label></div>
          <small>Treffer: Angriffsmuster und Zugriffe auf typische Angriffsziele (z. B. /wp-login.php, /.env).</small></div>
        <div class="sic-feld"><span>Fehlerbremse</span><label>sperren ab <input type="number" name="fehlerLimit" min="0" max="500" value="${F.fehlerLimit}"> fehlerhaften Anfragen in 5 Minuten</label><small>0 = aus. Zählt unbekannte Aktionen und ungültige Anfragen ohne Anmeldung.</small></div>
        <div class="sic-feld"><span>Bedrohungsliste</span><label class="sic-check"><input type="checkbox" name="feed"${F.feed ? ' checked' : ''}><span>Adressen aus der Spamhaus-DROP-Liste sperren</span></label>
          <small>${feed}</small><div><button type="button" class="btn sm" data-d="feed">${icon('download')}Jetzt aktualisieren</button></div></div>
        <label class="sic-feld">Nie sperren <small>(eine Adresse oder ein Bereich je Zeile)</small><textarea name="erlaubt" rows="2" placeholder="z. B. Büro: 80.147.24.0/24">${esc((F.erlaubt || []).join('\n'))}</textarea>
          <small>Zusätzlich zu den freigegebenen Adressen (IP-Freigabe). Tipp: vor einem Notfall die Büroadresse eintragen.</small></label>
        <label class="sic-feld">Mitschnitt aller Anfragen<select name="mitschnittMinuten"><option value="">${d.mitschnitt ? 'läuft bis ' + esc(sekUhr(d.mitschnitt)) : 'aus'}</option><option value="15">15 Minuten starten</option><option value="60">60 Minuten starten</option>${d.mitschnitt ? '<option value="0">beenden</option>' : ''}</select></label></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">${icon('check')}Speichern</button>`)}`,
    { breit: true, handler: async (a, b, form) => {
      if (a === 'feed') { toast('Bedrohungsliste wird geladen …'); fwUebernehmen(await aufruf('fw_feed_update', { body: {} })); toast('Bedrohungsliste aktualisiert.'); return; }
      if (a !== 'submit') return;
      const el = (n) => form.querySelector(`[name="${n}"]`);
      const body = { waf: el('waf').value, autoSperre: el('autoSperre').checked, treffer: +el('treffer').value, sperrMinuten: +el('sperrMinuten').value,
        fehlerLimit: +el('fehlerLimit').value, feed: el('feed').checked, erlaubt: el('erlaubt').value.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean) };
      if (el('mitschnittMinuten').value !== '') body.mitschnittMinuten = +el('mitschnittMinuten').value;
      fwUebernehmen(await aufruf('fw_save', { body })); dialogZu(); toast('Gespeichert.');
    } });
  }

  /* ======================= Anmeldung & Sitzungen ======================= */
  async function sitzungenTab() {
    const host = $('#tab-sitzungen');
    if (!S.sec) host.innerHTML = '<div class="sic-laden"><span class="sic-spinner"></span>Sitzungen werden geladen …</div>';
    S.sec = await api('security_status');
    const d = S.sec;
    const sitz = d.sessions.map((x) => `<tr><td><div class="sic-nm">${esc(x.name)}</div><div class="sub">${esc(x.username)}${x.role === 'admin' ? ' · Administrator' : ''}</div></td><td class="mono-s">${esc(x.ip)}</td><td>${esc(geraet(x.ua))}</td>
      <td class="num-s">${esc(zeit(x.created))}</td><td class="num-s">${esc(zeit(x.seen))}</td><td class="act">${x.current ? '<span class="sub">diese Sitzung</span>' : `<button type="button" class="btn sm" data-si="ende" data-sid="${esc(x.sid)}" data-name="${esc(x.name)}">Beenden</button>`}</td></tr>`).join('');
    const gesperrt = d.users.filter((u) => u.lockedUntil).map((u) => `<tr><td><div class="sic-nm">${esc(u.name)}</div><div class="sub">${esc(u.username)}</div></td><td><span class="sic-pille bad">gesperrt bis ${esc(uhr(new Date(u.lockedUntil * 1000).toISOString()))} Uhr</span></td><td class="act"><button type="button" class="btn sm" data-si="entsperren" data-uid="${esc(u.id)}" data-name="${esc(u.name)}">Entsperren</button></td></tr>`).join('');
    const fehl = d.fails.map((f) => `<tr><td class="num-s">${esc(zeit(f.t))}</td><td>${esc(f.u || '—')}</td><td class="mono-s">${esc(f.ip)}</td><td>${esc(f.s)}</td></tr>`).join('');
    const ohne = d.users.filter((u) => u.active && u.zugang !== false && !u.twofa && !u.passkeys);
    host.innerHTML = `
      <div class="sic-karten vier">
        ${karte('ok', 'Aktive Sitzungen', zahl(d.sessions.length), `${zahl(d.customers ? d.customers.online : 0)} Kunden angemeldet`)}
        ${karte(d.fails24 >= 20 ? 'bad' : d.fails24 >= 5 ? 'warn' : 'ok', 'Fehlanmeldungen (24 h)', zahl(d.fails24), `${zahl(d.fails.length)} in 7 Tagen angezeigt`)}
        ${karte(gesperrt ? 'warn' : 'ok', 'Gesperrte Zugänge', zahl(d.users.filter((u) => u.lockedUntil).length), `Kontosperre nach ${d.settings.lockAfter} Fehlversuchen`)}
        ${karte(ohne.some((u) => u.role === 'admin') ? 'bad' : ohne.length ? 'warn' : 'ok', 'Ohne Zwei-Faktor', zahl(ohne.length), 'aktive Zugänge mit eigenem Passwort', 'konten')}
      </div>
      ${block(`Aktive Sitzungen <span class="sub">${zahl(d.sessions.length)}</span>`, sitz ? `<div class="sic-tabrahmen"><table class="sic-tabelle"><thead><tr><th>Mitarbeiter</th><th>IP-Adresse</th><th>Gerät</th><th class="num-s">angemeldet</th><th class="num-s">zuletzt aktiv</th><th class="act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${sitz}</tbody></table></div>` : leer('Keine aktiven Sitzungen.'), '', 'sic-sitzungen')}
      <div class="sic-zwei">
        ${block('Gesperrte Zugänge', gesperrt ? `<div class="sic-tabrahmen"><table class="sic-tabelle"><tbody>${gesperrt}</tbody></table></div>` : leer('Kein Zugang ist gesperrt.'))}
        ${block(`Zugänge ohne Zwei-Faktor <span class="sub">${zahl(ohne.length)}</span>`, ohne.length ? `<p class="sic-chips">${ohne.map((u) => `<span class="sic-chip${u.role === 'admin' ? ' bad' : ''}">${esc(u.name)} · ${esc(u.username)}</span>`).join('')}</p>` : leer('Alle aktiven Zugänge nutzen die Zwei-Faktor-Anmeldung.'))}
      </div>
      ${block('Fehlgeschlagene Anmeldungen <span class="sub">7 Tage</span>', fehl ? `<div class="sic-tabrahmen"><table class="sic-tabelle"><thead><tr><th class="num-s">Zeitpunkt</th><th>Benutzername</th><th>IP-Adresse</th><th>Vorgang</th></tr></thead><tbody>${fehl}</tbody></table></div>` : leer('Keine fehlgeschlagenen Anmeldungen.'))}`;
  }
  $('#tab-sitzungen').addEventListener('click', (e) => {
    const b = e.target.closest('[data-si]');
    if (!b) return;
    lauf(null, async () => {
      if (b.dataset.si === 'ende') {
        if (!(await frage('Sitzung beenden?', `${esc(b.dataset.name)} wird auf diesem Gerät abgemeldet. Auf Keycloak-Hosts genügt eine erneute Anmeldung – zum Aussperren den Zugang sperren.`, 'Beenden', true))) return;
        await aufruf('session_end', { body: { sid: b.dataset.sid } }); dialogZu(); toast('Sitzung beendet.');
      } else {
        if (!(await frage('Zugang entsperren?', `${esc(b.dataset.name)} kann sich danach wieder anmelden; die Fehlversuche werden zurückgesetzt.`, 'Entsperren'))) return;
        await aufruf('user_unlock', { body: { id: b.dataset.uid } }); dialogZu(); toast('Zugang entsperrt.');
      }
      await sitzungenTab();
    });
  });

  /* ======================= Dateiprüfung ======================= */
  const IP_STUFE = { kritisch: 'bad', warnung: 'warn', hinweis: 'info', ok: 'ok' };
  const IP_ART = { geaendert: 'verändert', fehlt: 'fehlt', unbekannt: 'unbekannt', verdaechtig: 'verdächtig', daten: 'Datenordner' };
  async function dateiTab(lauf_ = false) {
    const host = $('#tab-datei');
    if (!S.datei) host.innerHTML = '<div class="sic-laden"><span class="sic-spinner"></span>Dateiprüfung wird geladen …</div>';
    S.datei = await api('security_integrity', lauf_ ? { body: { run: true } } : {});
    const r = S.datei.result;
    const knopf = `<button type="button" class="btn primary" data-ip="run">${icon('check')}Jetzt prüfen</button>`;
    if (!r) { host.innerHTML = `<section class="sic-held sic-glas"><div class="sic-held-icon">${icon('datei', 'gross')}</div><div class="sic-held-text"><h2>Noch keine Dateiprüfung</h2><p>Vergleicht alle Programmdateien mit der freigegebenen Fassung und sucht nach Schadcode-Mustern.</p></div><div class="sic-held-knopf">${knopf}</div></section>`; return; }
    const c = r.counts, l = c.critical ? 'bad' : c.warnings ? 'warn' : 'ok';
    const befunde = r.items.slice(0, 200).map((x, i) => `<tr class="sic-klick" data-befund="${i}" tabindex="0"><td>${punkt(IP_STUFE[x.stufe] || 'info')}</td><td class="mono-s sic-pfad">${esc(x.path)}</td><td>${esc(IP_ART[x.art] || x.art)}</td><td>${esc(x.text)}${x.signatur ? ` <strong>Muster: ${esc(x.signatur)}</strong>` : ''}</td></tr>`).join('');
    const mehr = r.items.length - 200 + (r.truncated || 0);
    const komp = (r.components || []).map((x) => `<tr><td>${punkt(IP_STUFE[x.stufe] || 'info')}</td><td><span class="sic-nm">${esc(x.name)}</span> <span class="mono-s">${esc(x.version)}</span></td><td>${esc(x.text)}</td></tr>`).join('');
    const hist = (S.datei.history || []).slice(0, 8).map((h) => `<li>${punkt(h.counts.critical ? 'bad' : h.counts.warnings ? 'warn' : 'ok')}${esc(zeit(h.ranAt))} Uhr · ${zahl(h.counts.critical)} kritisch · ${zahl(h.counts.warnings)} Warnungen <span class="sub">${h.auto ? 'automatisch' : esc(h.by || '')}</span></li>`).join('');
    host.innerHTML = `
      <section class="sic-held sic-glas ${l === 'ok' ? '' : l}"><div class="sic-held-icon">${icon('datei', 'gross')}</div>
        <div class="sic-held-text"><span class="sic-ueber">Letzte Prüfung ${esc(zeit(r.ranAt))} Uhr${r.auto ? ' (automatisch)' : r.by ? ` (${esc(r.by)})` : ''}</span>
          <h2>${l === 'ok' ? 'Keine Auffälligkeiten' : `${zahl(c.critical)} kritisch · ${plural(c.warnings, 'Warnung', 'Warnungen')}`}</h2>
          <p>${zahl(c.checked)} Dateien und Datensätze geprüft · ${zahl(c.modified)} verändert · ${zahl(c.missing)} fehlen · ${zahl(c.unknown)} unbekannt · ${zahl(c.suspicious)} verdächtig · ${zahl(r.ms)} ms</p>
          ${r.partial ? `<p class="sic-meldung warn">Unvollständig: ${esc(r.partialText)}.</p>` : ''}</div>
        <div class="sic-held-knopf">${knopf}</div></section>
      ${befunde ? block(`Befunde <span class="sub">${zahl(r.items.length)}</span>`, `<div class="sic-tabrahmen"><table class="sic-tabelle"><thead><tr><th class="lv-h"><span class="sr-only">Stufe</span></th><th>Datei</th><th>Art</th><th>Befund</th></tr></thead><tbody>${befunde}</tbody></table></div>${mehr > 0 ? `<p class="sic-hinweis">… und ${zahl(mehr)} weitere.</p>` : ''}`) : ''}
      <div class="sic-zwei">
        ${block('Komponenten', `<div class="sic-tabrahmen"><table class="sic-tabelle"><tbody>${komp}</tbody></table></div>`)}
        ${block('Verlauf', hist ? `<ul class="sic-verlauf">${hist}</ul>` : leer('Noch kein Verlauf.'))}
      </div>
      <p class="sic-hinweis">Läuft automatisch einmal am Tag beim Öffnen; neue Befunde gehen als Sicherheitsereignis per E-Mail an die eingetragenen Empfänger.</p>`;
  }
  $('#tab-datei').addEventListener('click', (e) => {
    const r = e.target.closest('[data-ip="run"]');
    if (r) { lauf(r, async () => { r.innerHTML = '<span class="sic-spinner klein"></span>Wird geprüft …'; await dateiTab(true); toast(S.datei.result && S.datei.result.ok ? 'Dateiprüfung: keine Auffälligkeiten.' : 'Dateiprüfung abgeschlossen – bitte Befunde ansehen.'); }); return; }
    const z = e.target.closest('[data-befund]');
    if (z) befundDialog(S.datei.result.items[+z.dataset.befund]);
  });
  $('#tab-datei').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('[data-befund]')) befundDialog(S.datei.result.items[+e.target.dataset.befund]); });
  function befundDialog(x) {
    const RAT = { geaendert: 'Die Datei weicht von der freigegebenen Fassung ab. Wurde nicht über ein Release eingespielt? Dann Ursache klären und den freigegebenen Stand neu einspielen.',
      fehlt: 'Die Datei gehört zur freigegebenen Fassung, fehlt aber auf dem Server. Freigegebenen Stand neu einspielen.',
      unbekannt: 'Diese Datei gehört nicht zur freigegebenen Fassung. Herkunft prüfen und entfernen, wenn sie nicht bekannt ist.',
      verdaechtig: 'Typisches Muster von Schadcode gefunden. Sofort prüfen – im Zweifel Notfallmodus auslösen und den Server untersuchen lassen.',
      daten: 'Auffälligkeit im Datenordner. Herkunft prüfen.' };
    dialog(`${dKopf('Befund der Dateiprüfung', esc(IP_ART[x.art] || x.art))}<div class="sic-dinhalt"><dl class="sic-dl">
      <dt>Datei</dt><dd class="mono-s sic-pfad">${esc(x.path)}</dd><dt>Stufe</dt><dd>${punkt(IP_STUFE[x.stufe] || 'info')} ${esc(x.stufe)}</dd><dt>Befund</dt><dd>${esc(x.text)}</dd>
      ${x.signatur ? `<dt>Muster</dt><dd><strong>${esc(x.signatur)}</strong></dd>` : ''}</dl><p class="sic-hinweis">${esc(RAT[x.art] || '')}</p></div>${dFuss('<button type="button" class="btn primary" data-d="zu">Schließen</button>')}`);
  }

  /* ======================= Ereignisse ======================= */
  let evTimer = 0;
  async function ereignisseTab() {
    const host = $('#tab-ereignisse');
    if (!$('#ev-liste', host)) {
      host.innerHTML = `<div class="sic-leiste ev-leiste">
          <div class="sic-filter" id="ev-arten" role="group" aria-label="Art"></div>
          <label class="sic-suche"><span class="sr-only">Suchen</span>${icon('search')}<input type="search" id="ev-q" placeholder="Beschreibung, Benutzer, IP …" value="${esc(S.evF.q)}"></label>
          <label class="sic-wahl"><span class="sr-only">Zeitraum</span><select id="ev-tage">${[[1, 'letzter Tag'], [7, '7 Tage'], [30, '30 Tage'], [90, '90 Tage']].map(([v, l]) => `<option value="${v}"${S.evF.tage === v ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
          ${S.rechte.admin ? `<button type="button" class="btn" id="ev-export">${icon('download')}Exportieren …</button>` : ''}</div>
        <div id="ev-liste" class="sic-block sic-glas"><div class="sic-laden"><span class="sic-spinner"></span>Ereignisse werden geladen …</div></div>`;
    }
    const f = S.evF;
    S.ev = await api('sicherheit_ereignisse', { query: `&tage=${f.tage}&art=${encodeURIComponent(f.art)}&q=${encodeURIComponent(f.q)}` });
    const d = S.ev;
    $('#ev-arten').innerHTML = [['', 'Alle', d.arten.reduce((a, x) => a + x.n, 0)], ...d.arten.map((x) => [x.key, x.label, x.n])]
      .map(([k, l, n]) => `<button type="button" class="btn sm${f.art === k ? ' an' : ''}" data-art="${k}" aria-pressed="${f.art === k}">${esc(l)} <span class="sic-zahl">${zahl(n)}</span></button>`).join('');
    $('#ev-liste').innerHTML = d.ereignisse.length ? `<div class="sic-tabrahmen"><table class="sic-tabelle ev-tab"><thead><tr><th class="num-s">Zeit</th><th>Art</th><th>Vorgang</th><th>Benutzer</th><th>IP-Adresse</th></tr></thead><tbody>${d.ereignisse.map(evZeile).join('')}</tbody></table></div>
      ${d.ereignisse.length >= 300 ? '<p class="sic-hinweis">Die neuesten 300 Ereignisse – für ältere den Zeitraum verkleinern oder exportieren.</p>' : ''}` : leer('Keine passenden Ereignisse.');
  }
  $('#tab-ereignisse').addEventListener('click', (e) => {
    const a = e.target.closest('[data-art]');
    if (a) { S.evF.art = a.dataset.art; lauf(a, ereignisseTab); return; }
    const z = e.target.closest('[data-ev]');
    if (z) { evDialog(S.ev.ereignisse[+z.dataset.ev]); return; }
    if (e.target.closest('#ev-export')) exportDialog();
  });
  $('#tab-ereignisse').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('[data-ev]')) evDialog(S.ev.ereignisse[+e.target.dataset.ev]); });
  $('#tab-ereignisse').addEventListener('input', (e) => {
    if (e.target.id !== 'ev-q') return;
    S.evF.q = e.target.value.trim(); clearTimeout(evTimer); evTimer = setTimeout(() => ereignisseTab().catch((ex) => toast(ex.message, true)), 300);
  });
  $('#tab-ereignisse').addEventListener('change', (e) => { if (e.target.id === 'ev-tage') { S.evF.tage = +e.target.value; ereignisseTab().catch((ex) => toast(ex.message, true)); } });
  function exportDialog() {
    dialog(`${dKopf('Sicherheitsprotokoll exportieren', 'CSV für Excel · enthält IP-Adressen und Namen')}<div class="sic-dinhalt">
        <label class="sic-feld">Zeitraum<select id="ex-tage"><option value="7">7 Tage</option><option value="30">30 Tage</option><option value="90" selected>90 Tage</option><option value="365">365 Tage</option></select></label>
        <p class="sic-hinweis">Der Export wird protokolliert und verlangt eine Bestätigung. Die Datei nur sicher aufbewahren und weitergeben.</p></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">${icon('download')}Exportieren</button>`)}`,
    { handler: async (a) => {
      if (a !== 'submit') return;
      const r = await aufruf('security_export', { body: { days: +$('#ex-tage', dlg).value } });
      herunterladen(r.filename, r.csv, 'text/csv;charset=utf-8'); dialogZu(); toast(`${zahl(r.count)} Einträge exportiert.`);
    } });
  }

  /* ======================= Einstellungen & Vorlagen ======================= */
  const SEC_LABEL = { twofa: 'Zwei-Faktor-Pflicht', pwMin: 'Passwort-Mindestlänge', pwComplex: 'Passwort-Komplexität', pwLeak: 'Datenleck-Prüfung', idleMinutes: 'Abmeldung nach Inaktivität (Min.)',
    lockAfter: 'Kontosperre nach Fehlversuchen', lockMinutes: 'Kontosperre (Min.)' };
  const FW_LABEL = { waf: 'Firewall', autoSperre: 'Automatische Sperre', treffer: 'Treffer bis zur Sperre', sperrMinuten: 'Sperrdauer', fehlerLimit: 'Fehlerbremse', feed: 'Bedrohungsliste', mitschnittMinuten: 'Mitschnitt (Min.)' };
  const TWOFA = { off: 'freiwillig', admins: 'für Administratoren', all: 'für alle Zugänge' };
  const wertText = (k, v) => (typeof v === 'boolean' ? (v ? 'an' : 'aus') : k === 'twofa' ? TWOFA[v] || v : k === 'sperrMinuten' ? DAUER[v] || v + ' Min.' : k === 'waf' && S.fw ? S.fw.modi[v] || v : String(v ?? '—'));
  async function einstellungenTab() {
    const host = $('#tab-einstellungen');
    if (!S.sec || !S.fw) host.innerHTML = '<div class="sic-laden"><span class="sic-spinner"></span>Einstellungen werden geladen …</div>';
    [S.sec, S.fw] = await Promise.all([api('security_status'), api('fw_status')]);
    einstZeichnen();
  }
  function einstZeichnen() {
    const d = S.sec, St = d.settings, G = d.geo, B = S.lage && S.lage.bericht;
    const VKARTE = { standard: ['schild', 'Ausgewogen für den Alltag.'], streng: ['lock', 'Mehr Schutz bei erhöhtem Risiko.'], notfall: ['alarm', 'Startet den Notfallmodus: Firewall „Notfall“ und alle Zugänge außer Administratoren gesperrt.'] };
    const vorlagen = Object.entries(S.fw.vorlagen).map(([k, v]) => `<div class="sic-vorlage ${k}"><div class="sic-vkopf">${icon(VKARTE[k] ? VKARTE[k][0] : 'schild')}<strong>${esc(k === 'notfall' ? 'Notfall' : v.label)}</strong></div>
      <p>${esc(k === 'notfall' ? VKARTE.notfall[1] : v.text)}</p>
      ${k === 'notfall' ? (S.rechte.notfall ? `<button type="button" class="btn gefahr" data-v="notfall" id="vorlage-notfall">${icon('alarm')}Notfallmodus starten …</button>` : '') : `<button type="button" class="btn" data-v="${esc(k)}">Vorschau und anwenden …</button>`}</div>`).join('');
    const aus = (d.bestaetigung || []).filter((b) => !b.fest && !b.noetig).length;
    const zusammen = (titel, zeilen, knopf, id) => `<section class="sic-einst sic-glas" id="${id}"><div class="sic-bkopf"><h3>${titel}</h3><button type="button" class="btn sm" data-e="${id}">Bearbeiten …</button></div><dl class="sic-dl eng">${zeilen.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>${knopf || ''}</section>`;
    $('#tab-einstellungen').innerHTML = `
      ${block('Vorlagen', `<div class="sic-vorlagen">${vorlagen}</div><p class="sic-hinweis">Vorlagen ändern Firewall und Sicherheitseinstellungen (Zwei-Faktor-Pflicht, Passwörter, Sitzungsdauer, Kontosperre) – nicht die Listen der freigegebenen Adressen und Länder.</p>`,
        `<div class="sic-knoepfe"><button type="button" class="btn sm" data-e="export">${icon('download')}Export</button><button type="button" class="btn sm" data-e="import">${icon('upload')}Import …</button></div>`)}
      <div class="sic-einstgitter">
        ${zusammen('Anmeldung und Passwörter', [['Zwei-Faktor-Pflicht', esc(TWOFA[St.twofa] || St.twofa)], ['Abmelden nach', esc((IDLE.find((x) => x[0] === St.idleMinutes) || [0, St.idleMinutes + ' Min.'])[1])],
          ['Passwörter', `mind. ${St.pwMin} Zeichen${St.pwComplex ? ', gemischt' : ''}${St.pwLeak ? ', Datenleck-Prüfung' : ''}`], ['Kontosperre', `nach ${St.lockAfter} Fehlversuchen für ${St.lockMinutes} Min.`]], '', 'e-anmeldung')}
        ${zusammen('IP-Freigabe', [['Status', St.ipEnabled ? `<span class="sic-pille ok">an</span> ${plural(St.adminIps.length, 'Adresse', 'Adressen')}` : '<span class="sic-pille">aus</span> aus dem ganzen Internet erreichbar'],
          ['Ihre Adresse', `<span class="mono-s">${esc(d.myIp)}</span>`]], '', 'e-ip')}
        ${zusammen('Ländersperre', [['Status', St.geoEnabled ? `<span class="sic-pille ok">an</span> ${St.geoMode === 'allow' ? `nur ${plural(St.geoCountries.length, 'Land', 'Länder')} erlaubt` : `${plural(St.geoCountries.length, 'Land', 'Länder')} gesperrt`}` : '<span class="sic-pille">aus</span>'],
          ['gilt für', St.geoScope === 'all' ? 'die ganze Seite' : 'den Eingabebereich'], ['Länderdaten', G ? `Stand ${esc(datum(G.date + 'T12:00:00Z'))}` : '<span class="sic-pille bad">fehlen</span>']],
          `<button type="button" class="btn sm" data-e="geo-update">${icon('download')}Länderdaten aktualisieren</button>`, 'e-geo')}
        ${zusammen('Passwortbestätigung', [['gilt', `${St.bestaetigungMinuten || 5} Minuten`], ['Aktionen', `${zahl((d.bestaetigung || []).length - aus)} mit Bestätigung${aus ? ` · <strong>${aus} ohne</strong>` : ''}`]], '', 'e-bst')}
        ${B ? zusammen('Wochenbericht', [['Versand', B.an ? `<span class="sic-pille ok">an</span> jeden ${esc(B.tage[B.tag])}` : '<span class="sic-pille">aus</span>'],
          ['Empfänger', B.empfaenger.length ? esc(B.empfaenger.join(', ')) : '<span class="sic-pille bad">keine eingetragen</span>']],
          `<button type="button" class="btn sm" data-bericht>${icon('bericht')}Bericht ansehen</button>`, 'e-bericht') : ''}
      </div>
      <p class="sic-hinweis">Fest eingebaut: HTTPS mit HSTS, Content-Security-Policy, CSRF-Schutz, sichere Sitzungs-Cookies, gesperrte Datenordner und ein lückenloses Protokoll.</p>`;
  }
  $('#tab-einstellungen').addEventListener('click', (e) => {
    const v = e.target.closest('[data-v]');
    if (v) { if (v.dataset.v === 'notfall') { lageLaden().then(() => notfallAuslosen()).catch((ex) => toast(ex.message, true)); } else vorlageDialog(v.dataset.v); return; }
    const b = e.target.closest('[data-e]');
    if (!b) return;
    const a = b.dataset.e;
    if (a === 'e-anmeldung') anmeldungDialog();
    if (a === 'e-ip') ipDialog();
    if (a === 'e-geo') geoDialog();
    if (a === 'e-bst') bstDialog();
    if (a === 'e-bericht') berichtEinstellen();
    if (a === 'export') lauf(b, async () => { const r = await api('fw_export'); herunterladen(`sicherheitseinstellungen-${new Date().toISOString().slice(0, 10)}.json`, JSON.stringify(r.export, null, 2), 'application/json'); toast('Einstellungen exportiert.'); });
    if (a === 'import') importDialog();
    if (a === 'geo-update') lauf(b, async () => { const r = await aufruf('geo_update', { body: {} }); S.sec.geo = r.geo; einstZeichnen(); toast(`Länderdaten aktualisiert (Stand ${datum(r.geo.date + 'T12:00:00Z')}).`); });
  });
  function berichtEinstellen() {
    const B = S.lage.bericht;
    dialog(`${dKopf('Wochenbericht', 'Zusammenfassung der letzten 7 Tage per E-Mail')}<div class="sic-dinhalt">
        <label class="sic-check"><input type="checkbox" id="br-an"${B.an ? ' checked' : ''}><span>Wöchentlich senden <span class="sub">an die Empfänger der Sicherheitsereignisse${B.empfaenger.length ? `: ${esc(B.empfaenger.join(', '))}` : ' (noch keine eingetragen)'}</span></span></label>
        <label class="sic-feld">Wochentag<select id="br-tag">${[1, 2, 3, 4, 5, 6, 7].map((t) => `<option value="${t}"${t === B.tag ? ' selected' : ''}>${esc(B.tage[t])}</option>`).join('')}</select></label>
        <p class="sic-hinweis">Versand ab 7 Uhr mit der ersten Anmeldung eines Mitarbeiters an diesem Tag (ist an dem Tag niemand angemeldet, am nächsten). Nach dem Einschalten kommt der erste Bericht in der folgenden Woche – sofort geht es mit „Bericht ansehen“ → „Jetzt senden“.
          Empfänger ändern: <a class="sic-link" href="${VERWALTUNG}#mail">Verwaltung → E-Mail ${icon('extern')}</a></p></div>
      ${dFuss('<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">Speichern</button>')}`,
    { handler: async (a) => {
      if (a !== 'submit') return;
      const r = await api('sicherheit_bericht_einstellen', { body: { an: $('#br-an', dlg).checked, tag: +$('#br-tag', dlg).value } });
      S.lage.bericht = r.einstellungen;
      dialogZu(); toast('Wochenbericht gespeichert.'); einstZeichnen();
    } });
  }
  function vorlageDialog(k) {
    const v = S.fw.vorlagen[k], w = v.werte || { sec: {}, fw: {} }, St = S.sec.settings, F = S.fw.fw;
    const zeilen = [...Object.entries(w.sec).map(([x, n]) => [SEC_LABEL[x] || x, wertText(x, St[x]), wertText(x, n)]), ...Object.entries(w.fw).map(([x, n]) => [FW_LABEL[x] || x, wertText(x, F[x]), wertText(x, n)])];
    const geaendert = zeilen.filter(([, a, b]) => a !== b).length;
    dialog(`${dKopf(`Vorlage „${v.label}“`, esc(v.text))}<div class="sic-dinhalt">
        <table class="sic-tabelle klein vorschau"><thead><tr><th>Einstellung</th><th>jetzt</th><th>danach</th></tr></thead><tbody>${zeilen.map(([l, a, b]) => `<tr class="${a !== b ? 'neu' : ''}"><td>${esc(l)}</td><td>${esc(a)}</td><td>${a !== b ? `<strong>${esc(b)}</strong>` : esc(b)}</td></tr>`).join('')}</tbody></table>
        <p class="sic-hinweis">${geaendert ? `${plural(geaendert, 'Einstellung ändert sich', 'Einstellungen ändern sich')}.` : 'Die Einstellungen entsprechen bereits dieser Vorlage.'} Adresslisten und Länder bleiben unverändert.</p></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary"${geaendert ? '' : ' disabled'}>Vorlage anwenden</button>`)}`,
    { breit: true, handler: async (a) => {
      if (a !== 'submit') return;
      const r = await aufruf('fw_vorlage', { body: { vorlage: k } });
      S.fw = { ...S.fw, ...r }; S.sec.settings = r.sec; einstZeichnen(); dialogZu(); toast(`Vorlage „${v.label}“ angewendet.`);
    } });
  }
  function importDialog() {
    let daten = null;
    dialog(`${dKopf('Einstellungen importieren', 'aus einer zuvor exportierten Datei')}<div class="sic-dinhalt">
        <label class="sic-feld">Datei (JSON)<input type="file" id="im-datei" accept="application/json,.json"></label>
        <div id="im-vorschau"></div><p class="sic-hinweis">Übernimmt Firewall und Sicherheitseinstellungen; Listen der Adressen und Länder bleiben unverändert.</p></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary" id="im-los" disabled>${icon('upload')}Importieren</button>`)}`,
    { handler: async (a) => {
      if (a !== 'submit' || !daten) return;
      const r = await aufruf('fw_import', { body: { export: daten } });
      S.fw = { ...S.fw, ...r }; S.sec = null; dialogZu(); toast('Einstellungen übernommen.'); await einstellungenTab();
    } });
    $('#im-datei', dlg).addEventListener('change', async (e) => {
      daten = null; $('#im-los', dlg).disabled = true; dFehler('');
      try {
        const x = JSON.parse(await e.target.files[0].text());
        if (!x || x.art !== 'wochenangebot-sicherheit') throw new Error('Die Datei ist kein Export der Sicherheitseinstellungen.');
        daten = x;
        $('#im-vorschau', dlg).innerHTML = `<p class="sic-meldung ok">Export vom ${esc(zeit(x.stand))} Uhr · ${zahl(Object.keys(x.sicherheit || {}).length)} Sicherheits- und ${zahl(Object.keys(x.firewall || {}).length)} Firewall-Einstellungen.</p>`;
        $('#im-los', dlg).disabled = false;
      } catch (ex) { dFehler(ex.name === 'SyntaxError' ? 'Die Datei ist keine gültige JSON-Datei.' : ex.message); }
    });
  }
  /* Speichern der Einstellungen: immer vollständig (security_save erwartet alle Felder) */
  async function secSpeichern(aenderung, text) {
    const r = await aufruf('security_save', { body: { ...S.sec.settings, ...aenderung } });
    S.sec.settings = r.settings; einstZeichnen(); dialogZu(); toast(text);
  }
  function anmeldungDialog() {
    const St = S.sec.settings;
    dialog(`${dKopf('Anmeldung und Passwörter')}<div class="sic-dinhalt" id="sec-form">
        <label class="sic-feld">Zwei-Faktor-Anmeldung verpflichtend<select name="twofa">${Object.entries(TWOFA).map(([k, l]) => `<option value="${k}"${St.twofa === k ? ' selected' : ''}>${l}</option>`).join('')}</select>
          <small>Wer sie noch nicht eingerichtet hat, wird beim nächsten Anmelden dazu aufgefordert. Auf den Keycloak-Hosts gilt zusätzlich die Pflicht der zentralen Anmeldung.</small></label>
        <label class="sic-feld">Automatisch abmelden nach Inaktivität<select name="idleMinutes">${IDLE.map(([v, l]) => `<option value="${v}"${St.idleMinutes === v ? ' selected' : ''}>${l}</option>`).join('')}</select></label>
        <div class="sic-feld"><span>Passwörter</span><label>mindestens <input type="number" name="pwMin" min="10" max="32" value="${St.pwMin}"> Zeichen</label>
          <label class="sic-check"><input type="checkbox" name="pwComplex"${St.pwComplex ? ' checked' : ''}><span>Groß-/Kleinbuchstaben, Ziffern oder Sonderzeichen verlangen</span></label>
          <label class="sic-check"><input type="checkbox" name="pwLeak"${St.pwLeak ? ' checked' : ''}><span>Gegen bekannte Datenlecks prüfen <span class="sub">(übertragen werden nur die ersten 5 Zeichen eines Prüfwerts, nie das Passwort)</span></span></label></div>
        <div class="sic-feld"><span>Kontosperre</span><div class="sic-inline"><label>nach <input type="number" name="lockAfter" min="3" max="20" value="${St.lockAfter}"> Fehlversuchen</label><label>für <input type="number" name="lockMinutes" min="5" max="1440" value="${St.lockMinutes}"> Minuten</label></div>
          <small>Zusätzlich wird jede Adresse nach 5 Fehlversuchen für 10 Minuten gesperrt.</small></div></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">${icon('check')}Speichern</button>`)}`,
    { breit: true, handler: async (a, b, form) => {
      if (a !== 'submit') return;
      const el = (n) => form.querySelector(`[name="${n}"]`);
      await secSpeichern({ twofa: el('twofa').value, idleMinutes: +el('idleMinutes').value, pwMin: +el('pwMin').value, pwComplex: el('pwComplex').checked, pwLeak: el('pwLeak').checked,
        lockAfter: +el('lockAfter').value, lockMinutes: +el('lockMinutes').value }, 'Sicherheitseinstellungen gespeichert.');
    } });
  }
  function ipDialog() {
    const St = S.sec.settings;
    let bestaetigt = false;
    const form = () => dialog(`${dKopf('IP-Freigabe', 'Eingabebereich und Anwendungen nur von bestimmten Internetadressen')}<div class="sic-dinhalt">
        <label class="sic-check"><input type="checkbox" id="ip-an"${St.ipEnabled ? ' checked' : ''}><span>IP-Freigabe einschalten – die öffentliche Angebotsseite bleibt für alle erreichbar</span></label>
        <label class="sic-feld">Freigegebene Adressen <small>(eine Adresse oder ein Bereich pro Zeile)</small><textarea id="ip-liste" rows="4" placeholder="z. B. 80.147.24.150 oder 80.147.24.0/24">${esc(St.adminIps.join('\n'))}</textarea></label>
        <p class="sic-inline"><span class="sub">Ihre aktuelle Adresse: <strong class="mono-s">${esc(S.sec.myIp)}</strong>${S.sec.myCountry ? ` · ${esc(land(S.sec.myCountry))}` : ''}</span><button type="button" class="btn sm" data-d="meine">${icon('plus')}Hinzufügen</button></p></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">${icon('check')}Speichern</button>`)}`,
    { handler: async (a) => {
      const ta = $('#ip-liste', dlg);
      if (a === 'meine') { const l = ta.value.split(/\s+/).filter(Boolean); if (!l.includes(S.sec.myIp)) ta.value = [...l, S.sec.myIp].join('\n'); return; }
      if (a !== 'submit') return;
      const an = $('#ip-an', dlg).checked, liste = ta.value.split(/[\s,;]+/).map((x) => x.trim()).filter(Boolean);
      if (an && !bestaetigt) {
        const ich = liste.includes(S.sec.myIp);
        if (!(await frage('IP-Freigabe einschalten?', `Der Eingabebereich ist danach nur noch von ${liste.map(esc).join(', ') || 'keiner Adresse'} erreichbar.${ich ? '' : ' <strong>Ihre eigene Adresse fehlt in der Liste.</strong>'} Im Notfall lässt sich die Freigabe auf dem Server zurücksetzen (deploy/ip-freigabe-aus.sh).`, 'Einschalten', !ich))) return;
      }
      await secSpeichern({ ipEnabled: an, adminIps: liste }, 'IP-Freigabe gespeichert.');
    } });
    form();
  }
  /* Ländersperre mit Auswahl (Suche nach Land oder IP-Adresse) */
  function geoDialog() {
    const St = S.sec.settings, g = S.geo;
    g.sel = new Set(St.geoCountries || []); g.q = ''; g.ip = null;
    dialog(`${dKopf('Ländersperre', 'Zugriffe aus bestimmten Ländern abweisen')}<div class="sic-dinhalt geo-box" id="geo-box">
        <label class="sic-check"><input type="checkbox" name="geoEnabled"${St.geoEnabled ? ' checked' : ''}><span>Ländersperre einschalten</span></label>
        <div class="sic-inline"><label class="sic-check"><input type="radio" name="geoMode" value="block"${St.geoMode !== 'allow' ? ' checked' : ''}><span>ausgewählte Länder sperren</span></label>
          <label class="sic-check"><input type="radio" name="geoMode" value="allow"${St.geoMode === 'allow' ? ' checked' : ''}><span>nur ausgewählte Länder erlauben</span></label>
          <label>gilt für <select name="geoScope"><option value="admin"${St.geoScope !== 'all' ? ' selected' : ''}>den Eingabebereich</option><option value="all"${St.geoScope === 'all' ? ' selected' : ''}>die ganze Seite</option></select></label></div>
        <p class="geo-me" id="geo-me"></p>
        <div class="geo-wahl"><div class="geo-kopf"><strong id="geo-sel-label">Gesperrte Länder</strong><span class="sub" id="geo-count"></span>
          <span class="sic-knoepfe"><button type="button" class="btn sm" data-d="geo-eu">Europa</button><button type="button" class="btn sm" data-d="geo-leer">Leeren</button></span></div>
          <div class="geo-chips" id="geo-chips"></div></div>
        <div class="geo-suche"><input type="search" id="geo-q" placeholder="Land oder IP-Adresse, z. B. China, CN oder 1.0.1.1" aria-label="Land oder IP-Adresse suchen"><div class="geo-list" id="geo-list"></div></div>
        <p class="sic-hinweis">Freigegebene Adressen sind immer erlaubt; Adressen ohne bekanntes Land werden nicht gesperrt. Ergänzt Passwort und Zwei-Faktor-Anmeldung, ersetzt sie aber nicht.</p></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">${icon('check')}Speichern</button>`)}`,
    { breit: true, fokus: '#geo-q', handler: async (a, b, form) => {
      if (a === 'geo-eu') { EUROPA.forEach((c) => g.sel.add(c)); geoAuffrischen(); return; }
      if (a === 'geo-leer') { g.sel.clear(); geoAuffrischen(); return; }
      if (a === 'geo-weg') { g.sel.delete(b.dataset.cc); geoAuffrischen(); return; }
      if (a !== 'submit') return;
      const an = form.querySelector('[name=geoEnabled]').checked, modus = form.querySelector('[name=geoMode]:checked').value, scope = form.querySelector('[name=geoScope]').value;
      const laender = [...g.sel].sort();
      if (an && !laender.length) { dFehler(modus === 'allow' ? 'Bitte mindestens ein erlaubtes Land auswählen.' : 'Bitte mindestens ein Land zum Sperren auswählen.'); return; }
      if (an && (!St.geoEnabled || St.geoMode !== modus || St.geoScope !== scope || St.geoCountries.join() !== laender.join())) {
        const namen = laender.sort(landSort).map(land);
        const was = modus === 'allow' ? `Zugriffe sind danach nur noch aus ${namen.length > 8 ? namen.length + ' ausgewählten Ländern' : namen.join(', ')} möglich.` : `Zugriffe aus ${namen.length > 8 ? namen.length + ' Ländern' : namen.join(', ')} werden danach abgewiesen.`;
        const wo = scope === 'all' ? 'Das gilt für die ganze Seite – auch Kunden in diesen Ländern sehen das Angebot nicht.' : 'Das gilt nur für den Eingabebereich; das öffentliche Angebot bleibt für alle sichtbar.';
        if (!(await frage('Ländersperre speichern?', `${esc(was)} ${esc(wo)}`, 'Speichern'))) return;
      }
      await secSpeichern({ geoEnabled: an, geoMode: modus, geoScope: scope, geoCountries: laender }, 'Ländersperre gespeichert.');
    } });
    geoAuffrischen();
  }
  function geoListe() {
    const g = S.geo;
    if (IP_RE.test(g.q)) {
      if (!g.ip || g.ip.ip !== g.q) return leer('IP-Adresse wird gesucht …');
      if (g.ip.error) return leer(esc(g.ip.error));
      if (!g.ip.country) return leer(`<span class="mono-s">${esc(g.ip.ip)}</span> – ${g.ip.private ? 'interne Adresse, keinem Land zugeordnet' : 'kein Land bekannt'}.`);
      const c = g.ip.country;
      return `<label class="geo-opt geo-iphit"><input type="checkbox" data-geo-cc="${esc(c)}"${g.sel.has(c) ? ' checked' : ''}> <span><span class="mono-s">${esc(g.ip.ip)}</span> → ${esc(land(c))}</span><span class="sub">${esc(c)}</span></label>`;
    }
    const q = g.q.toLowerCase();
    const alle = (S.sec.geoCountries || []).filter((c) => !q || c.toLowerCase() === q || land(c).toLowerCase().includes(q)).sort(landSort);
    return alle.length ? alle.map((c) => `<label class="geo-opt"><input type="checkbox" data-geo-cc="${esc(c)}"${g.sel.has(c) ? ' checked' : ''}> <span>${esc(land(c))}</span><span class="sub">${esc(c)}</span></label>`).join('') : leer('Kein Land gefunden.');
  }
  function geoAuffrischen() {
    const g = S.geo, f = $('#geo-box', dlg);
    if (!f) return;
    const l = [...g.sel].sort(landSort);
    $('#geo-chips', dlg).innerHTML = l.length ? l.map((c) => `<span class="sic-chip">${esc(land(c))} <span class="sub">${esc(c)}</span><button type="button" data-d="geo-weg" data-cc="${esc(c)}" aria-label="${esc(land(c))} entfernen">×</button></span>`).join('') : '<span class="sub">Noch kein Land ausgewählt.</span>';
    $('#geo-count', dlg).textContent = g.sel.size ? `${g.sel.size} ausgewählt` : '';
    const allow = f.querySelector('[name=geoMode]:checked').value === 'allow', mc = S.sec.myCountry;
    const gesperrt = mc && f.querySelector('[name=geoEnabled]').checked && (allow ? !g.sel.has(mc) : g.sel.has(mc));
    const me = $('#geo-me', dlg);
    me.className = 'geo-me' + (gesperrt ? ' bad' : '');
    me.innerHTML = mc ? `Sie greifen gerade aus <strong>${esc(land(mc))}</strong> zu${gesperrt ? ' – mit dieser Auswahl würden Sie sich aussperren.' : '.'}` : 'Ihr Land ist nicht bekannt (interne Adresse) – Sie werden nicht gesperrt.';
    $('#geo-sel-label', dlg).textContent = allow ? 'Erlaubte Länder' : 'Gesperrte Länder';
    $('#geo-list', dlg).innerHTML = geoListe();
  }
  let geoTimer = 0;
  dlg.addEventListener('input', (e) => {
    if (e.target.id !== 'geo-q') return;
    const g = S.geo;
    g.q = e.target.value.trim();
    clearTimeout(geoTimer);
    if (IP_RE.test(g.q)) {
      const ip = g.q;
      geoTimer = setTimeout(async () => {
        try { const r = await api('geo_lookup', { query: '&ip=' + encodeURIComponent(ip) }); g.ip = { ip, country: r.country, private: r.private }; } catch (ex) { g.ip = { ip, error: ex.message }; }
        if (g.q === ip && $('#geo-list', dlg)) $('#geo-list', dlg).innerHTML = geoListe();
      }, 250);
    }
    $('#geo-list', dlg).innerHTML = geoListe();
  });
  dlg.addEventListener('change', (e) => {
    const cc = e.target.dataset && e.target.dataset.geoCc;
    if (cc) { if (e.target.checked) S.geo.sel.add(cc); else S.geo.sel.delete(cc); dFehler(''); geoAuffrischen(); return; }
    if (['geoEnabled', 'geoMode'].includes(e.target.name)) geoAuffrischen();
  });
  function bstDialog() {
    const d = S.sec, St = d.settings, gruppen = [];
    for (const b of d.bestaetigung || []) { let g = gruppen.find((x) => x.name === b.group); if (!g) gruppen.push((g = { name: b.group, l: [] })); g.l.push(b); }
    dialog(`${dKopf('Passwortbestätigung', 'Welche Aktionen eine frische Anmeldung bzw. das Passwort verlangen')}<div class="sic-dinhalt" id="bst-form">
        <label class="sic-feld">Bestätigung gilt<select name="bestaetigungMinuten">${(d.bestaetigungMinuten || [5]).map((m) => `<option value="${m}"${(St.bestaetigungMinuten || 5) === m ? ' selected' : ''}>${m} Minuten</option>`).join('')}</select></label>
        <div class="bst-gitter">${gruppen.map((g) => `<fieldset class="bst-g${g.l.every((b) => b.fest) ? ' fest' : ''}"><legend>${esc(g.name)}</legend>${g.l.map((b) => b.fest
          ? `<label class="sic-check fest" title="Immer mit Bestätigung"><input type="checkbox" checked disabled><span>${icon('lock')}${esc(b.label)}</span></label>`
          : `<label class="sic-check"><input type="checkbox" name="bst" value="${esc(b.key)}"${b.noetig ? ' checked' : ''}><span>${esc(b.label)}</span></label>`).join('')}</fieldset>`).join('')}</div>
        <p class="sic-hinweis">Ohne Haken genügen Anmeldung und Berechtigung. Aktionen an Zugängen, Rechten und Sicherheit verlangen immer eine Bestätigung.</p></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">${icon('check')}Speichern</button>`)}`,
    { breit: true, handler: async (a, b, form) => {
      if (a !== 'submit') return;
      const aus = $$('input[name="bst"]', form).filter((c) => !c.checked).map((c) => c.value);
      const neuAus = aus.filter((k) => !(St.bestaetigungAus || []).includes(k));
      const minuten = +form.querySelector('[name=bestaetigungMinuten]').value;
      if (neuAus.length && !(await frage('Passwortbestätigung abschalten?', `Für ${neuAus.length === 1 ? 'diese Aktion' : `diese ${neuAus.length} Aktionen`} genügen danach Anmeldung und Berechtigung: ${(d.bestaetigung || []).filter((x) => neuAus.includes(x.key)).map((x) => esc(x.label)).join(', ')}.`, 'Abschalten', true))) return;
      await secSpeichern({ bestaetigungAus: aus, bestaetigungMinuten: minuten }, 'Passwortbestätigung gespeichert.');
      S.sec = await api('security_status'); einstZeichnen();
    } });
  }

  /* ======================= Konten: privilegierte und ungenutzte ======================= */
  async function kontenTab() {
    const host = $('#tab-konten');
    if (!S.konten) host.innerHTML = '<div class="sic-laden"><span class="sic-spinner"></span>Konten werden geladen …</div>';
    S.konten = await api('sicherheit_konten', { query: '&tage=' + (S.kontenTage || 90) });
    const d = S.konten, Z = d.zahlen, U = d.ungenutzt;
    const schutz = (k) => k.zentral ? '<span class="sic-pille ok">zentrale Anmeldung</span>' : k.zweiFaktor ? `<span class="sic-pille ok">${k.passkeys ? 'Passkey' : 'Einmalcode'}</span>` : '<span class="sic-pille bad">nur Passwort</span>';
    const zeilen = d.konten.map((k, i) => `<tr class="sic-klick${k.aktiv ? '' : ' aus'}" data-konto="${i}" tabindex="0"><td><span class="sic-av${k.admin ? ' admin' : ''}" aria-hidden="true">${esc(initialen(k.name))}</span><div class="sic-nm">${esc(k.name)}</div><div class="sub">${esc(k.username)}${k.aktiv ? '' : ' · gesperrt'}</div></td>
      <td>${k.admin ? '<span class="sic-pille warn">Administrator</span>' : esc(k.rollen)}</td><td>${k.admin ? '<span class="sub">alle Rechte</span>' : k.rechte.map((r) => `<span class="sic-chip klein" title="${esc(r.label)}">${esc(r.key)}</span>`).join(' ')}</td>
      <td>${schutz(k)}${k.lockedUntil ? ' <span class="sic-pille bad">gesperrt</span>' : ''}</td><td class="num-s">${k.lastLogin ? esc(zeit(k.lastLogin)) : '<span class="sub">nie</span>'}</td><td class="num-s">${zahl(k.sitzungen.length)}</td></tr>`).join('');
    host.innerHTML = `
      <div class="sic-karten vier">
        ${karte(Z.admins > 3 ? 'warn' : 'ok', 'Administratoren', zahl(Z.admins), Z.admins > 3 ? 'nur so viele wie nötig' : 'aktive Konten')}
        ${karte('ok', 'Weitere privilegierte Konten', zahl(Z.weitere), 'mit sicherheitsrelevanten Rechten')}
        ${karte(Z.ohneZweiFaktor ? 'bad' : 'ok', 'Ohne zweiten Faktor', zahl(Z.ohneZweiFaktor), Z.ohneZweiFaktor ? 'Einmalcode oder Passkey einrichten lassen' : 'alle geschützt')}
        ${karte('ok', 'Dürfen Notfall auslösen', zahl(Z.notfall), 'Administratoren und Recht „Notfall auslösen“')}
      </div>
      ${block(`Privilegierte Konten <span class="sub">${zahl(d.konten.length)}</span>`, `<div class="sic-tabrahmen"><table class="sic-tabelle konten"><thead><tr><th>Konto</th><th>Rolle</th><th>Sicherheitsrelevante Rechte</th><th>Anmeldeschutz</th><th class="num-s">letzte Anmeldung</th><th class="num-s">Sitzungen</th></tr></thead><tbody>${zeilen}</tbody></table></div>
        <p class="sic-hinweis">Rollen und Rechte ändern Sie in der <a href="${VERWALTUNG}#users" class="sic-link">Verwaltung → Mitarbeiter ${icon('extern')}</a>.</p>`)}
      ${ungenutztHtml(U)}`;
  }
  function ungenutztHtml(U) {
    const zeilen = U.konten.map((k, i) => `<tr><td><span class="sic-av${k.admin ? ' admin' : ''}" aria-hidden="true">${esc(initialen(k.name))}</span><div class="sic-nm">${esc(k.name)}</div><div class="sub">${esc(k.username)}</div></td>
      <td>${k.admin ? '<span class="sic-pille warn">Administrator</span>' : esc(k.rollen)}</td>
      <td class="num-s">${k.nie ? `<span class="sic-pille warn">nie angemeldet</span><div class="sub">angelegt ${esc(datum(k.created))}</div>` : esc(datum(k.lastLogin))}</td>
      <td class="num-s">${zahl(k.tage)} Tage</td>
      <td class="act">${S.me && k.id === S.me.id ? '<span class="sub">Ihr Zugang</span>' : `<button type="button" class="btn sm" data-deakt="${i}">${icon('lock')}Deaktivieren …</button>`}</td></tr>`).join('');
    return block(`Ungenutzte Zugänge <span class="sub">${zahl(U.konten.length)}</span>`, `${zeilen ? `<div class="sic-tabrahmen"><table class="sic-tabelle ungenutzt"><thead><tr><th>Konto</th><th>Rolle</th><th class="num-s">letzte Anmeldung</th><th class="num-s">ungenutzt</th><th class="act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${zeilen}</tbody></table></div>`
      : leer(`Alle aktiven Zugänge wurden in den letzten ${zahl(U.tage)} Tagen genutzt.`)}
      <p class="sic-hinweis">Gezählt wird die letzte Anmeldung – bei der zentralen Anmeldung die letzte Anmeldung bei Keycloak; Zugänge mit laufender Sitzung zählen nicht. Deaktivierte Zugänge lassen sich unter <a href="${VERWALTUNG}#users" class="sic-link">Verwaltung → Mitarbeiter ${icon('extern')}</a> wieder aktivieren.</p>`,
    `<label class="sic-wahl"><span class="sr-only">Zeitraum</span><select id="ung-tage">${U.wahl.map((t) => `<option value="${t}"${t === U.tage ? ' selected' : ''}>seit ${t} Tagen</option>`).join('')}</select></label>`, 'sic-ungenutzt');
  }
  function deaktDialog(k) {
    dialog(`${dKopf(`Zugang „${k.name}“ deaktivieren?`, esc(k.username), 'gefahr')}<div class="sic-dinhalt">
        <dl class="sic-dl"><dt>letzte Anmeldung</dt><dd>${k.nie ? `nie <span class="sub">(angelegt ${esc(datum(k.created))})</span>` : `${esc(zeit(k.lastLogin))} Uhr <span class="sub">(vor ${zahl(k.tage)} Tagen)</span>`}</dd>
          <dt>Rolle</dt><dd>${k.admin ? 'Administrator' : esc(k.rollen)}</dd></dl>
        <p>${esc(k.name)} kann sich danach nicht mehr anmelden; laufende Sitzungen enden sofort. Daten wie Urlaub, Protokoll und Vorgänge bleiben erhalten.</p>
        <p class="sic-hinweis">Wieder aktivieren: Verwaltung → Mitarbeiter. Die Änderung steht im Protokoll und wird als Sicherheitsereignis gemeldet.</p></div>
      ${dFuss('<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn gefahr">Deaktivieren</button>')}`,
    { handler: async (a) => {
      if (a !== 'submit') return;
      await aufruf('sicherheit_konto_deaktivieren', { body: { id: k.id } });
      dialogZu(); toast(`Zugang „${k.username}“ deaktiviert.`);
      await kontenTab();
    } });
  }
  $('#tab-konten').addEventListener('click', (e) => {
    const x = e.target.closest('[data-deakt]');
    if (x) { deaktDialog(S.konten.ungenutzt.konten[+x.dataset.deakt]); return; }
    const z = e.target.closest('[data-konto]'); if (z) kontoDialog(S.konten.konten[+z.dataset.konto]);
  });
  $('#tab-konten').addEventListener('change', (e) => {
    if (e.target.id !== 'ung-tage') return;
    S.kontenTage = +e.target.value;
    kontenTab().then(() => { const w = $('#ung-tage'); if (w) w.focus(); }).catch((ex) => toast(ex.message, true));
  });
  $('#tab-konten').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('[data-konto]')) kontoDialog(S.konten.konten[+e.target.dataset.konto]); });
  function kontoDialog(k) {
    const sitz = k.sitzungen.map((s) => `<tr><td class="mono-s">${esc(s.ip)}</td><td>${esc(geraet(s.ua))}</td><td class="num-s">${esc(zeit(s.seen))}</td><td class="act">${s.current ? '<span class="sub">diese</span>' : `<button type="button" class="btn sm" data-d="ende" data-sid="${esc(s.sid)}">Beenden</button>`}</td></tr>`).join('');
    dialog(`${dKopf(k.name, `${esc(k.username)} · ${k.admin ? 'Administrator' : esc(k.rollen)}${k.aktiv ? '' : ' · gesperrt'}`)}<div class="sic-dinhalt">
        <dl class="sic-dl"><dt>Anmeldeschutz</dt><dd>${k.zentral ? 'zentrale Anmeldung (Keycloak)' : k.zweiFaktor ? `zweiter Faktor (${[k.totp ? 'Einmalcode' : '', k.passkeys ? plural(k.passkeys, 'Passkey', 'Passkeys') : ''].filter(Boolean).join(', ')})` : '<strong>nur Passwort</strong>'}</dd>
          <dt>letzte Anmeldung</dt><dd>${k.lastLogin ? esc(zeit(k.lastLogin)) + ' Uhr' : 'nie'}</dd><dt>vertraute Geräte</dt><dd>${zahl(k.geraete)}</dd>
          ${k.mustChange ? '<dt>Passwort</dt><dd>muss beim nächsten Anmelden geändert werden</dd>' : ''}${k.lockedUntil ? `<dt>Sperre</dt><dd><span class="sic-pille bad">bis ${esc(uhr(new Date(k.lockedUntil * 1000).toISOString()))} Uhr</span></dd>` : ''}</dl>
        ${k.admin ? '<p class="sic-hinweis">Administratoren haben alle Rechte, auch Notfall beenden, Einstellungen und Zugänge.</p>' : `<h4>Sicherheitsrelevante Rechte</h4><ul class="sic-rechte">${k.rechte.map((r) => `<li><span class="mono-s">${esc(r.key)}</span> ${esc(r.label)}</li>`).join('')}</ul>`}
        <h4>Sitzungen <span class="sub">${zahl(k.sitzungen.length)}</span></h4>${sitz ? `<table class="sic-tabelle klein"><tbody>${sitz}</tbody></table>` : leer('Keine aktive Sitzung.')}</div>
      ${dFuss(`<a class="btn" href="${VERWALTUNG}#users">${icon('extern')}In der Verwaltung</a>${k.lockedUntil ? '<button type="button" class="btn" data-d="entsperren">Entsperren</button>' : ''}${k.sitzungen.some((s) => !s.current) ? '<button type="button" class="btn gefahr" data-d="alle">Alle Sitzungen beenden</button>' : ''}<button type="button" class="btn primary" data-d="zu">Schließen</button>`)}`,
    { breit: true, handler: async (a, b) => {
      if (a === 'ende') { await aufruf('session_end', { body: { sid: b.dataset.sid } }); toast('Sitzung beendet.'); }
      else if (a === 'alle') { await aufruf('session_end', { body: { uid: k.id } }); toast('Sitzungen beendet.'); }
      else if (a === 'entsperren') { await aufruf('user_unlock', { body: { id: k.id } }); toast('Zugang entsperrt.'); }
      else return;
      await kontenTab();
      const neu = S.konten.konten.find((x) => x.id === k.id);
      if (neu) kontoDialog(neu); else dialogZu();
    } });
  }

  /* ======================= System: Betrieb, Wartung, Module und Freigaben, Diagnose (nur Administratoren) ======================= */
  /* Bis 27.10.2026 Verwaltung → System. Daten: betrieb_status (lib/diagnose.php betrieb_daten, dazu die Auswahl der Tester)
     und module_status (lib/module.php). Wartung, Freigabe und Tester verlangen eine Bestätigung – auf Keycloak-Hosts die erneute
     Anmeldung; danach öffnet sich der Dialog mit den Eingaben wieder (Entwurf nur in sessionStorage). Was erlaubt ist,
     entscheidet der Server: die Oberfläche bietet nur die Werte an, die module_status nennt. */
  const SYSTEM_ENTWURF = 'sic-system-entwurf';
  const SY_BEREICH = { 'angebot.kunden': 'Angebotsseite (Kunden)', 'angebot.eingabe': 'Eingabebereich (Mitarbeiter)', alle: 'alle Bereiche (Notfallmodus)' };
  const SY_ZUSTAND = { normal: 'normal', wartung: 'Wartung', 'wartung geplant': 'Wartung geplant' };
  const MV_ENTW = { geplant: 'Geplant', in_entwicklung: 'In Entwicklung', in_pruefung: 'In Prüfung', fertig: 'Fertig' };
  const MV_FREI = { keine: 'Nicht freigegeben', test: 'Testbetrieb (nur Tester)', produktiv: 'Produktiv', deaktiviert: 'Deaktiviert' };
  const DIAG = [['storage', 'Datenablage prüfen', 'Lesbarkeit und Unversehrtheit aller Datensätze'], ['mail', 'E-Mail-Verbindung prüfen', 'Verbindung und Anmeldung am Mailserver, ohne E-Mail'],
    ['files', 'Dateien und Speicher', 'Schreibrechte, Schreibschutz, freier Speicher'], ['php', 'PHP-Umgebung', 'Version, Erweiterungen, Grenzwerte, Serverzeit']];
  const mbZahl = (n) => (n / 1024 / 1024).toFixed(1).replace('.', ',');
  const gbZahl = (n) => (n / 1024 ** 3).toFixed(1).replace('.', ',');
  const syBis = (w) => (w && w.until ? `${esc(zeit(w.until))} Uhr` : '<span class="sub">offen</span>');
  let syDiag = [];   // letzte Diagnosen (neueste zuerst, nur Anzeige)
  async function systemTab() {
    const host = $('#tab-system');
    if (!S.system) host.innerHTML = '<div class="sic-laden"><span class="sic-spinner"></span>System wird geladen …</div>';
    const [d, m] = await Promise.all([api('betrieb_status'), api('module_status')]);
    S.system = d; S.module = m;
    systemZeichnen();
    systemEntwurf();
  }
  function systemKarten(d) {
    const n = d.notfall, b = d.backup, st = d.storage || {}, k = d.disk, ml = d.mail, o = d.orders, c = d.customers;
    let sich;
    if (!b || !b.t) sich = karte('warn', 'Datensicherung', 'keine', 'noch keine automatische Sicherung – entsteht nach dem nächsten Server-Update täglich');
    else if (!b.ok) sich = karte('bad', 'Datensicherung', 'fehlgeschlagen', `${esc(zeit(b.t))} Uhr · ${esc(b.meldung || (b.fehler ? `${b.fehler} Datei(en) fehlerhaft` : 'Server prüfen'))}`);
    else if (b.inhalt === false) sich = karte('warn', 'Datensicherung', 'nur Archiv geprüft', `${esc(zeit(b.t))} Uhr · ${esc(b.meldung || 'Inhalt nicht geprüft')}`);
    else if ((Date.now() - new Date(b.t).getTime()) / 3600000 > 48) sich = karte('bad', 'Datensicherung', 'veraltet', `letzte ${esc(zeit(b.t))} Uhr – älter als 2 Tage, Server prüfen`);
    else sich = karte('ok', 'Datensicherung', 'geprüft', `${esc(zeit(b.t))} Uhr · ${b.datensaetze ? `${zahl(b.datensaetze)} Datensätze${b.speicher === 'sqlite' ? ' (Datenbank)' : ''} · ` : ''}${plural(+b.anzahl || 0, 'Stand', 'Stände')} je ${mbZahl(+b.groesse || 0)} MB`);
    const frei = k && k.free && k.total ? (k.free < 1024 ** 3 ? 'bad' : k.free < 5 * 1024 ** 3 ? 'warn' : 'ok') : 'warn';
    return [
      n ? karte('bad', 'Notfallmodus', 'aktiv', `seit ${esc(zeit(n.seit))} Uhr – Mitarbeiter ohne Administratorrolle gesperrt`, 'notfall') : karte('ok', 'Notfallmodus', 'aus', 'Normalbetrieb', 'notfall'),
      sich,
      bereitstellungKarte(d.deployment),
      karte('ok', 'Datenablage', st.mode === 'sqlite' ? 'SQLite' : 'Dateien', `${zahl(st.documents || 0)} Datensätze · ${mbZahl(st.bytes || 0)} MB${d.php ? ` · PHP ${esc(d.php)}` : ''}`),
      k && k.free && k.total ? karte(frei, 'Speicherplatz', `${gbZahl(k.free)} GB`, `frei von ${gbZahl(k.total)} GB${frei === 'ok' ? '' : ' – bald aufräumen oder erweitern'}`) : karte('warn', 'Speicherplatz', 'unbekannt', ''),
      !ml || !ml.configured ? karte('warn', 'E-Mail-Versand', 'nicht eingerichtet', 'Verwaltung → E-Mail')
        : karte(ml.failed7 ? 'warn' : 'ok', 'E-Mail-Versand', zahl(ml.sent7), `zugestellt in 7 Tagen${ml.failed7 ? ` · ${zahl(ml.failed7)} nicht zugestellt (Versandliste unter Verwaltung → E-Mail)` : ''}`),
      !o ? '' : !o.enabled ? karte('warn', 'Bestellwünsche', 'aus', 'Bestellfunktion ausgeschaltet (Verwaltung → E-Mail → Bestellwünsche)')
        : karte(o.failed7 ? 'warn' : 'ok', 'Bestellwünsche', zahl(o.n7), `in 7 Tagen${o.failed7 ? ` · ${zahl(o.failed7)} nicht per E-Mail zugestellt` : o.last ? ` · zuletzt ${esc(o.lastNr || '')} am ${esc(zeit(o.last))} Uhr` : ' · noch keine'}`),
      !c ? '' : karte('ok', 'Kunden', zahl(c.active), `aktiv · ${zahl(c.withLogin)} mit Zugang · ${c.online ? `${zahl(c.online)} gerade angemeldet` : 'niemand angemeldet'}`),
    ].join('');
  }
  function systemWartung(d) {
    const w = d.wartung, e = d.wartungEingabe;
    const karte_ = (titel, id, zeilen, knoepfe, art = '') => `<section class="sic-einst sic-glas sy-wartung${art ? ' ' + art : ''}" id="${id}"><div class="sic-bkopf"><h3>${titel}</h3></div>
      <dl class="sic-dl eng">${zeilen.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl><div class="sic-knoepfe sic-blockfuss">${knoepfe}</div></section>`;
    const kunden = w && w.notfall
      ? karte_('Wartungsmodus · Angebotsseite', 'sy-kunden', [['Zustand', '<span class="sic-pille bad">gesperrt durch den Notfallmodus</span>'], ['Kunden sehen', 'den Hinweis des Notfallmodus']],
        `<button type="button" class="btn sm" data-geh="notfall">Zum Notfall</button><button type="button" class="btn sm" data-sy="kunden-an">Wartungsmodus einschalten …</button>`, 'bad')
      : w ? karte_('Wartungsmodus · Angebotsseite', 'sy-kunden', [['Zustand', `<span class="sic-pille warn">Wartung</span> <span class="sub">seit ${esc(zeit(w.since))} Uhr</span>`],
        ['Hinweis für Kunden', w.message ? esc(w.message) : '<span class="sub">Standardtext</span>'], ['voraussichtlich bis', syBis(w)]],
        `<button type="button" class="btn sm" data-sy="kunden-bearbeiten">Hinweis bearbeiten …</button><button type="button" class="btn sm primary" data-sy="kunden-aus">Wartungsmodus beenden …</button>`, 'warn')
      : karte_('Wartungsmodus · Angebotsseite', 'sy-kunden', [['Zustand', '<span class="sic-pille ok">normal</span> <span class="sub">Kunden sehen das Angebot</span>'],
        ['wirkt auf', 'Angebot, Anmeldung, Merkliste und Bestellwünsche der Kunden – Mitarbeiter arbeiten weiter']], '<button type="button" class="btn sm" data-sy="kunden-an">Wartungsmodus einschalten …</button>');
    const eingabe = e
      ? karte_('Wartung · Eingabebereich', 'sy-eingabe', [['Zustand', e.geplant ? `<span class="sic-pille info">geplant</span> <span class="sub">ab ${esc(zeit(e.ab))} Uhr</span>` : `<span class="sic-pille warn">Wartung</span> <span class="sub">seit ${esc(zeit(e.since))} Uhr</span>`],
        ['Grund', esc(e.grund || '—')], ['Hinweis für Mitarbeiter', e.message ? esc(e.message) : '<span class="sub">Standardtext</span>'], ['voraussichtlich bis', syBis(e)]],
        `<button type="button" class="btn sm" data-sy="eingabe-bearbeiten">Bearbeiten …</button><button type="button" class="btn sm primary" data-sy="eingabe-aus">Wartung beenden …</button>`, e.geplant ? '' : 'warn')
      : karte_('Wartung · Eingabebereich', 'sy-eingabe', [['Zustand', '<span class="sic-pille ok">normal</span> <span class="sub">alle Mitarbeiter arbeiten</span>'],
        ['wirkt auf', 'alle Mitarbeiter außer Administratoren (z. B. für eine Datenübernahme) – Kunden sind nicht betroffen']], '<button type="button" class="btn sm" data-sy="eingabe-an">Wartung starten oder planen …</button>');
    return kunden + eingabe;
  }
  function syBereiche() {
    const out = [];
    for (const m of (S.module && S.module.module) || []) for (const o of m.oberflaechen || []) out.push({ ziel: `${m.id}.${o.id}`, modul: m, o });
    return out;
  }
  function systemModule() {
    const zeilen = syBereiche().map(({ ziel, modul, o }) => {
      const v = o.verwaltung || {};
      const quelle = v.laufzeit ? `<div class="sub">geändert von ${esc(v.laufzeit.von)} · ${esc(v.laufzeit.grund)}</div>` : !v.aenderbar ? '<div class="sub">nur über ein Release</div>' : '';
      const tester = (v.tester || []).map((t) => esc(t.name) + (t.aktiv ? '' : ' (gesperrt)')).join(', ');
      const kann = v.aenderbar || v.tester_moeglich;
      const fl = o.freigabe === 'produktiv' ? 'ok' : o.freigabe === 'test' ? 'info' : o.freigabe === 'deaktiviert' ? 'bad' : '';
      return `<tr data-mvziel="${esc(ziel)}"${kann ? ` class="sic-klick" tabindex="0"` : ''}><td><div class="sic-nm">${esc(modul.name)}</div><div class="sub">${esc(o.name)}${o.art === 'extern' ? ' · extern' : ''}</div></td>
        <td>${esc(MV_ENTW[o.entwicklung] || o.entwicklung)}</td><td><span class="sic-pille ${fl}">${esc(MV_FREI[o.freigabe] || o.freigabe)}</span>${quelle}</td>
        <td>${o.betrieb === 'wartung' ? '<span class="sic-pille warn">Wartung</span>' : '<span class="sub">normal</span>'}</td><td>${tester || '<span class="sub">—</span>'}</td>
        <td class="act">${kann ? `<button type="button" class="btn sm" data-sy="modul" data-ziel="${esc(ziel)}">Ändern …</button>` : ''}</td></tr>`;
    }).join('');
    return block('Module und Freigaben', `<div class="sic-tabrahmen"><table class="sic-tabelle mvtab"><thead><tr><th>Bereich</th><th>Entwicklung</th><th>Freigabe</th><th>Betrieb</th><th>Tester</th><th class="act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${zeilen}</tbody></table></div>
      <p class="sic-hinweis">Der Entwicklungsstand kommt aus dem Code; die Freigabe lässt sich hier nur innerhalb dessen ändern, was der Code zulässt („produktiv“ erst, wenn ein Modul als fertig ausgeliefert ist). Laufende Produktivbereiche, die Sicherheitszentrale und das Dashboard werden nur über ein Release gesteuert. Jede Änderung wird mit Grund protokolliert und muss bestätigt werden.</p>`, '', 'sy-module');
  }
  function systemVerlauf(d) {
    const namen = {};
    for (const b of syBereiche()) namen[b.ziel] = `${b.modul.name} · ${b.o.name}`;
    const l = (d.wartungVerlauf || []).slice(0, 12).map((v) => `<li><span class="num-s sub">${esc(zeit(v.t))}</span><span><strong>${esc(SY_BEREICH[v.bereich] || namen[v.bereich] || v.bereich)}</strong>: ${esc(SY_ZUSTAND[v.alt] || v.alt)} → <strong>${esc(SY_ZUSTAND[v.neu] || v.neu)}</strong>
      <span class="sub">· ${esc(v.wer)}${v.grund ? ` · ${esc(v.grund)}` : ''}</span></span></li>`).join('');
    return block('Verlauf <span class="sub">Wartung, Freigaben, Tester</span>', l ? `<ul class="sic-verlauf sy-verlauf">${l}</ul>` : leer('Noch keine Änderungen.'), '', 'sy-verlauf');
  }
  const diagHtml = () => syDiag.map((x) => `<div class="sy-diag ${x.r.ok ? 'ok' : 'bad'}" data-res="${esc(x.k)}"><div class="sy-diag-kopf">${punkt(x.r.ok ? 'ok' : 'bad')}<strong>${esc(x.label)}</strong><span class="sub">${esc(x.uhr)} Uhr · ${zahl(x.r.ms)} ms</span></div>
      <table class="sic-tabelle klein"><tbody>${x.r.items.map((i) => `<tr><td class="lv-h">${punkt(i.level)}</td><td>${esc(i.label)}</td><td class="mono-s">${esc(i.value)}</td></tr>`).join('')}</tbody></table></div>`).join('');
  function systemZeichnen() {
    const d = S.system;
    $('#tab-system').innerHTML = `
      <div class="sic-karten">${systemKarten(d)}</div>
      <div class="sic-einstgitter">${systemWartung(d)}</div>
      ${systemModule()}
      <div class="sic-zwei">
        ${block('Diagnose', `<p class="sic-hinweis" style="margin-top:0">Alle Prüfungen lesen nur – es werden keine Daten verändert und keine Befehle auf dem Server ausgeführt.</p>
          <div class="sic-knoepfe sy-diag-knoepfe">${DIAG.map(([k, l, t]) => `<button type="button" class="btn sm" data-diag="${k}" title="${esc(t)}">${esc(l)}</button>`).join('')}</div>
          <div id="sy-diag-erg" class="sy-diag-erg" aria-live="polite">${diagHtml()}</div>`, '', 'sy-diagnose')}
        ${systemVerlauf(d)}
      </div>`;
  }
  /* Entwurf nach der erneuten Anmeldung (Keycloak) wieder öffnen – mit Hinweis, dass nur noch gespeichert werden muss */
  function systemEntwurf() {
    let e = null;
    try { e = JSON.parse(sessionStorage.getItem(SYSTEM_ENTWURF) || 'null'); sessionStorage.removeItem(SYSTEM_ENTWURF); } catch { /* ohne Speicher */ }
    if (!e || typeof e !== 'object' || dlg.open) return;
    const h = 'Anmeldung bestätigt – bitte noch einmal speichern.';
    if (e.art === 'kunden') kundenDialog(e.modus, e.werte, h);
    else if (e.art === 'eingabe') eingabeDialog(e.modus, e.werte, h);
    else if (e.art === 'modul' && syBereiche().some((b) => b.ziel === e.ziel)) modulDialog(e.ziel, e.werte, h);
  }
  const syHinweis = (h) => (h ? `<p class="sic-meldung ok">${esc(h)}</p>` : '');
  async function sySpeichern(action, body, entwurf, text) {
    const r = await aufruf(action, { body }, [SYSTEM_ENTWURF, entwurf]);
    try { sessionStorage.removeItem(SYSTEM_ENTWURF); } catch { /* ohne Speicher */ }
    dialogZu(); toast(text);
    await systemTab();
    return r;
  }
  /* Wartungsmodus der Angebotsseite (wartung_save): an, Hinweis ändern, aus */
  function kundenDialog(modus, werte = null, hinweis = '') {
    const w = S.system.wartung && !S.system.wartung.notfall ? S.system.wartung : null;
    const v = werte || { message: w ? w.message || '' : '', until: w && w.until ? w.until : '' };
    if (modus === 'aus') {
      dialog(`${dKopf('Wartungsmodus beenden?', 'Angebotsseite für Kunden')}<div class="sic-dinhalt">${syHinweis(hinweis)}
          <p>Kunden sehen danach wieder das Angebot und können sich anmelden und bestellen.</p></div>
        ${dFuss('<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">Wartungsmodus beenden</button>')}`,
      { handler: async (a) => {
        if (a !== 'submit') return;
        await sySpeichern('wartung_save', { active: false, message: v.message, until: '' }, { art: 'kunden', modus, werte: v }, 'Wartungsmodus beendet – die Angebotsseite ist wieder erreichbar.');
      } });
      return;
    }
    const an = modus === 'an';
    dialog(`${dKopf(an ? 'Wartungsmodus einschalten' : 'Hinweis zum Wartungsmodus', 'Angebotsseite für Kunden')}<div class="sic-dinhalt">${syHinweis(hinweis)}
        ${an ? '<p>Kunden sehen auf der Angebotsseite dann nur noch den Hinweis und können sich nicht anmelden oder bestellen, bis Sie den Wartungsmodus beenden. Sie und alle Mitarbeiter arbeiten normal weiter; Abmeldelinks aus E-Mails funktionieren weiterhin.</p>' : ''}
        ${S.system.wartung && S.system.wartung.notfall ? '<p class="sic-meldung fehler">Die Angebotsseite ist gerade durch den Notfallmodus gesperrt. Ein hier eingeschalteter Wartungsmodus bleibt nach dem Notfall bestehen.</p>' : ''}
        <label class="sic-feld">Hinweis für Kunden <small>(optional)</small><textarea id="sy-k-text" rows="3" maxlength="500" placeholder="Wir aktualisieren gerade unser Angebotsportal. In Kürze sind wir wieder für Sie da.">${esc(v.message)}</textarea></label>
        <label class="sic-feld">Voraussichtlich bis <small>(optional)</small><input type="datetime-local" id="sy-k-bis" value="${esc(v.until || '')}"></label></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">${an ? 'Wartungsmodus einschalten' : 'Hinweis speichern'}</button>`)}`,
    { handler: async (a) => {
      if (a !== 'submit') return;
      const neu = { message: $('#sy-k-text', dlg).value, until: $('#sy-k-bis', dlg).value };
      await sySpeichern('wartung_save', { active: true, ...neu }, { art: 'kunden', modus, werte: neu }, an ? 'Wartungsmodus eingeschaltet.' : 'Hinweis gespeichert.');
    } });
  }
  /* Wartung des Eingabebereichs (modul_wartung_save, immer mit Bestätigung): starten bzw. planen, ändern, beenden */
  function eingabeDialog(modus, werte = null, hinweis = '') {
    const e = S.system.wartungEingabe;
    const v = werte || { grund: e ? e.grund || '' : '', message: e ? e.message || '' : '', ab: e && e.ab ? e.ab : '', until: e && e.until ? e.until : '' };
    if (modus === 'aus') {
      dialog(`${dKopf('Wartung des Eingabebereichs beenden?', e && e.geplant ? 'geplante Wartung verwerfen' : 'Eingabebereich wieder für alle')}<div class="sic-dinhalt">${syHinweis(hinweis)}
          <p>Alle Mitarbeiter können danach wieder im Eingabebereich arbeiten.</p>
          <label class="sic-feld">Grund <small>(optional, wird protokolliert)</small><input id="sy-e-ende" maxlength="200" value="${esc(werte ? werte.grund : '')}" placeholder="z. B. Datenübernahme abgeschlossen"></label></div>
        ${dFuss('<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">Wartung beenden</button>')}`,
      { fokus: '.sic-dfuss .btn.primary', handler: async (a) => {
        if (a !== 'submit') return;
        const grund = $('#sy-e-ende', dlg).value;
        await sySpeichern('modul_wartung_save', { bereich: 'angebot.eingabe', active: false, grund }, { art: 'eingabe', modus, werte: { grund } }, 'Wartung beendet – der Eingabebereich ist wieder für alle freigegeben.');
      } });
      return;
    }
    const an = modus === 'an';
    dialog(`${dKopf(an ? 'Wartung des Eingabebereichs' : 'Wartung des Eingabebereichs ändern', 'Mitarbeiter ohne Administratorrolle sehen nur den Wartungshinweis')}<div class="sic-dinhalt">${syHinweis(hinweis)}
        <p class="sic-hinweis" style="margin-top:0">Ohne Beginn startet die Wartung sofort: offene Bearbeitungen werden unterbrochen. Administratoren arbeiten weiter, Kunden sind nicht betroffen.</p>
        <label class="sic-feld">Grund <small>(Pflicht, nur für Administratoren sichtbar)</small><input id="sy-e-grund" maxlength="200" value="${esc(v.grund)}" placeholder="z. B. Datenübernahme Stammdaten" required></label>
        <label class="sic-feld">Hinweis für Mitarbeiter <small>(optional)</small><textarea id="sy-e-text" rows="2" maxlength="500" placeholder="Der Eingabebereich wird gerade gewartet. Bitte versuchen Sie es später erneut.">${esc(v.message)}</textarea></label>
        <div class="sic-felder zwei"><label class="sic-feld">Beginn <small>(optional, sonst sofort)</small><input type="datetime-local" id="sy-e-ab" value="${esc(v.ab || '')}"></label>
          <label class="sic-feld">Voraussichtlich bis <small>(optional)</small><input type="datetime-local" id="sy-e-bis" value="${esc(v.until || '')}"></label></div></div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Abbrechen</button><button type="submit" class="btn primary">${an ? 'Wartung starten bzw. planen' : 'Änderungen speichern'}</button>`)}`,
    { handler: async (a) => {
      if (a !== 'submit') return;
      const neu = { grund: $('#sy-e-grund', dlg).value.trim(), message: $('#sy-e-text', dlg).value, ab: $('#sy-e-ab', dlg).value, until: $('#sy-e-bis', dlg).value };
      if (neu.grund.length < 3) { dFehler('Bitte einen Grund angeben (wird protokolliert).'); $('#sy-e-grund', dlg).focus(); return; }
      const r = await sySpeichern('modul_wartung_save', { bereich: 'angebot.eingabe', active: true, ...neu }, { art: 'eingabe', modus, werte: neu },
        neu.ab && new Date(neu.ab) > new Date() ? 'Wartung geplant.' : an ? 'Wartung gestartet.' : 'Gespeichert.');
      return r;
    } });
  }
  /* Freigabe und Tester eines Bereichs (modul_freigabe_save, modul_tester_save – getrennt gespeichert, je mit Bestätigung) */
  function modulDialog(ziel, werte = null, hinweis = '') {
    const b = syBereiche().find((x) => x.ziel === ziel);
    if (!b) return;
    const v = b.o.verwaltung || {}, jetzt = new Set((v.tester || []).map((t) => t.id));
    const wahl = werte ? new Set(werte.tester || []) : jetzt;
    const nutzer = (S.system.nutzer || []).filter((u) => u.active || jetzt.has(u.id)).sort((x, y) => x.name.localeCompare(y.name, 'de'));
    dialog(`${dKopf(`${b.modul.name} · ${b.o.name}`, `${esc(MV_ENTW[b.o.entwicklung] || b.o.entwicklung)} · jetzt: ${esc(MV_FREI[b.o.freigabe] || b.o.freigabe)}`)}<div class="sic-dinhalt">${syHinweis(hinweis)}
        <div class="sic-felder zwei">
          ${v.aenderbar ? `<label class="sic-feld">Freigabe <small>(nur, was der Entwicklungsstand zulässt)</small><select id="mv-freigabe">${(v.moeglich || []).map((f) => `<option value="${esc(f)}"${f === (werte && werte.freigabe ? werte.freigabe : b.o.freigabe) ? ' selected' : ''}>${esc(MV_FREI[f] || f)}</option>`).join('')}</select></label>` : '<p class="sic-hinweis">Die Freigabe dieses Bereichs wird nur über ein Release gesteuert.</p>'}
          <label class="sic-feld">Grund <small>(Pflicht für die Freigabe, wird protokolliert)</small><input id="mv-grund" maxlength="200" value="${esc(werte ? werte.grund || '' : '')}" placeholder="z. B. Abnahme durch die Fachabteilung"></label></div>
        ${v.tester_moeglich ? `<fieldset class="sic-optionen"><legend>Tester – nur sie sehen den Bereich im Testbetrieb (Administratoren nur, wenn eingetragen)</legend>
          ${nutzer.length ? `<div class="sy-tester">${nutzer.map((u) => `<label class="sic-check"><input type="checkbox" name="mv-tester" value="${esc(u.id)}"${wahl.has(u.id) ? ' checked' : ''}><span>${esc(u.name)} <span class="sub">${esc(u.username)}${u.active ? '' : ' · gesperrt'}</span></span></label>`).join('')}</div>` : leer('Keine aktiven Mitarbeiterkonten.')}</fieldset>` : ''}</div>
      ${dFuss(`<button type="button" class="btn" data-d="zu">Schließen</button>${v.tester_moeglich ? '<button type="button" class="btn" data-d="tester">Tester speichern</button>' : ''}${v.aenderbar ? '<button type="button" class="btn primary" data-d="freigabe">Freigabe speichern</button>' : ''}`)}`,
    { breit: true, handler: async (a) => {
      if (a !== 'freigabe' && a !== 'tester') return;
      const lies = () => ({ freigabe: ($('#mv-freigabe', dlg) || {}).value || '', grund: $('#mv-grund', dlg).value, tester: $$('[name="mv-tester"]:checked', dlg).map((x) => x.value) });
      const n = lies();
      if (a === 'freigabe') {
        const r = await aufruf('modul_freigabe_save', { body: { bereich: ziel, freigabe: n.freigabe, grund: n.grund } }, [SYSTEM_ENTWURF, { art: 'modul', ziel, werte: n }]);
        toast(`Freigabe gespeichert: ${MV_FREI[r.freigabe.neu] || r.freigabe.neu}.`);
      } else {
        await aufruf('modul_tester_save', { body: { bereich: ziel, tester: n.tester, grund: n.grund } }, [SYSTEM_ENTWURF, { art: 'modul', ziel, werte: n }]);
        toast(n.tester.length ? `Tester gespeichert (${zahl(n.tester.length)}).` : 'Keine Tester mehr eingetragen.');
      }
      try { sessionStorage.removeItem(SYSTEM_ENTWURF); } catch { /* ohne Speicher */ }
      await systemTab();
      modulDialog(ziel);   // aktueller Stand; zum Weiterarbeiten offen
    } });
  }
  async function diagnose(k, knopf) {
    const r = (await api('security_diag', { body: { check: k } })).result;
    syDiag = [{ k, r, label: (DIAG.find((x) => x[0] === k) || [k, k])[1], uhr: new Date().toLocaleTimeString('de-DE') }, ...syDiag.filter((x) => x.k !== k)].slice(0, 4);
    const erg = $('#sy-diag-erg');
    if (erg) erg.innerHTML = diagHtml();
    if (knopf && knopf.isConnected) knopf.focus();
  }
  $('#tab-system').addEventListener('click', (e) => {
    const dg = e.target.closest('[data-diag]');
    if (dg) { lauf(dg, () => diagnose(dg.dataset.diag, dg)); return; }
    const b = e.target.closest('[data-sy]');
    if (b) {
      const [art, modus] = b.dataset.sy.split('-');
      if (art === 'kunden') kundenDialog(modus);
      else if (art === 'eingabe') eingabeDialog(modus);
      else if (art === 'modul') modulDialog(b.dataset.ziel);
      return;
    }
    const z = e.target.closest('tr.sic-klick[data-mvziel]');
    if (z) modulDialog(z.dataset.mvziel);
  });
  $('#tab-system').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr.sic-klick[data-mvziel]')) modulDialog(e.target.dataset.mvziel); });

  const LADEN = { lage: lageTab, notfall: notfallTab, firewall: firewallTab, sitzungen: sitzungenTab, datei: () => dateiTab(false), ereignisse: ereignisseTab, einstellungen: einstellungenTab, konten: kontenTab, system: systemTab };

  /* ---------- Hell/Dunkel ---------- */
  function themaKnopf() {
    const b = $('#sic-theme');
    const dunkel = document.documentElement.dataset.theme === 'dark' || (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
    b.innerHTML = icon(dunkel ? 'sun' : 'moon');
    b.setAttribute('aria-label', dunkel ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }
  $('#sic-theme').addEventListener('click', () => {
    const dunkel = document.documentElement.dataset.theme === 'dark' || (!document.documentElement.dataset.theme && matchMedia('(prefers-color-scheme: dark)').matches);
    const neu = dunkel ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', neu);   // theme.js merkt die Wahl am Konto (Beobachter)
    try { localStorage.setItem('wochenangebot.theme', JSON.stringify(neu)); } catch { /* ohne Speicher */ }
    themaKnopf();
  });

  /* ---------- Start ---------- */
  async function start() {
    let st;
    try { st = await api('status'); } catch (e) {
      if (e.status === 403 && e.data.code === 'reauth_required' && typeof e.data.anmelden === 'string' && e.data.anmelden.startsWith('/oidc/')) { location.assign(e.data.anmelden + encodeURIComponent(location.href)); return; }
      if (e.status === 401) { zeigeAnmeldung(); return; }
      fehler(e.message); return;
    }
    if (!st.loggedIn) { zeigeAnmeldung(); return; }
    S.csrf = st.csrf || ''; S.me = st.user;
    if (window.STAFL_THEME) { window.STAFL_THEME.konto(st.user, S.csrf, API); themaKnopf(); }
    const name = st.user ? (st.user.name || st.user.username || '') : '';
    $('#sic-user').hidden = false; $('#sic-user-name').textContent = name; $('#sic-initialen').textContent = initialen(name);
    try { await lageLaden(); } catch (e) {
      if (e.status === 404) { fehler('Die Sicherheitszentrale ist für Sie nicht freigegeben.'); return; }
      fehler(e.data.code === 'kein_modulzugang' || e.status === 403 ? 'Für die Sicherheitszentrale fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.' : e.message); return;
    }
    for (const b of $$('#sic-tabs [data-tab]')) b.hidden = !erlaubt(b.dataset.tab);
    $('#sic-login').hidden = true; $('#sic-app').hidden = false;
    zeigeTab(location.hash.slice(1));
  }
  themaKnopf();
  /* Uhr im Kopf (Leitstand): Wochentag, Datum, Uhrzeit – nur Anzeige */
  const uhrKopf = () => { const d = new Date(); $('#sic-uhr').textContent = d.toLocaleDateString('de-DE', { weekday: 'short', day: '2-digit', month: '2-digit' }) + ' · ' + d.toLocaleTimeString('de-DE'); };
  uhrKopf(); setInterval(uhrKopf, 1000);
  window.addEventListener('hashchange', () => { const t = location.hash.slice(1); if (t && t !== S.tab && !$('#sic-app').hidden) zeigeTab(t); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden && S.tab === 'firewall') fwLive(); });
  start().catch(() => fehler('Keine Verbindung zum Server.'));
})();
