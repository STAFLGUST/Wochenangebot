/* ==========================================================================
   Wochenangebot – Eingabebereich, Verwaltung
   Mitarbeiter, Bestellungen, Kunden, E-Mail, Protokoll. Sicherheit und System (Betrieb, Wartung, Module und Freigaben, seit
   27.10.2026): eigenes Modul app/module/sicherheit/. Hilfen und Zustand kommen aus admin.js
   (window.WA, Zustand über Getter: W.me, W.offers, W.stdPublic, W.wartungSt); die Ansichten werden dort
   über W.views aufgerufen.
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const { $, $$, api, esc, icon, toast, confirmBox, dateTime, timeOnly, plural, fold, fmtNum, fmtInt, csvCell, ROLE_LABEL, offerName, offerShort, loadOffers, pendingCount, setView, OSTD, may } = W;
  const isAdmin = () => W.me && W.me.role === 'admin';
  // Vertraute Geräte (Browser, auf denen sich der Zugang angemeldet hat; kommen auch bei einer fremd ausgelösten Sperre durch)
  const geraeteText = (g) => `${plural(g.length, 'Gerät', 'Geräte')}: ${g.slice(0, 3).map((x) => `${x.name}, zuletzt ${dateTime(x.zuletzt)}`).join(' · ')}${g.length > 3 ? ' …' : ''}`;
  const mailInfo = () => (isAdmin() ? api('mail_status') : api('mail_info').catch(() => ({ configured: false })));   // Postfach-Details nur für Administratoren; sonst Kurzinfo (eingerichtet, Woche)
  let qTimer = null;

  /* ======================= Mitarbeiter (Administrator; Personalstelle: nur HR-Angaben) =======================
     Mitarbeiter = Nutzer der Plattform. Auch Kollegen ohne Anmeldung (z. B. Lager) sind Mitarbeiter („ohne Anmeldung“)
     – für die Urlaubsverwaltung. HR-Angaben (Abteilung, Arbeitstage, Urlaubsanspruch) kommen aus app/module/hr/verwaltung-hr.js (W.hr). */
  let users = null, rights = null, twofaModus = 'off';
  const ROLE_DESC = {
    admin: 'Alle Rechte, dazu Mitarbeiter und Rechte, Sicherheit und E-Mail-Einstellungen',
    editor: 'Rechte laut Tabelle „Rollen und Rechte“ (Standard: Angebot bearbeiten und veröffentlichen, Bestellungen, Bestand)',
    viewer: 'Rechte laut Tabelle „Rollen und Rechte“ (Standard: nur ansehen)',
  };
  /* Rollen eines Mitarbeiters (Hauptrolle + weitere; Namen aus „rechte“) – Rollen und Rechte verwaltet admin-rollen.js */
  const rollenVon = (u) => (u.rollen && u.rollen.length ? u.rollen : [u.role]);
  const rollenName = (r) => (rights && rights.roleLabels && rights.roleLabels[r]) || ROLE_LABEL[r] || r;
  const rollenRechte = (ids) => new Set(ids.flatMap((r) => (rights && rights.roles[r]) || []));
  const exceptions = (u) => (u.role === 'admin' ? '' : [u.grant.length ? `+${u.grant.length}` : '', u.deny.length ? `−${u.deny.length}` : ''].filter(Boolean).join(' / '));
  const roleBadge = (r) => `<span class="role-b r-${['admin', 'editor', 'viewer'].includes(r) ? esc(r) : 'eigen'}">${esc(rollenName(r))}</span>`;
  const roleBadges = (u) => rollenVon(u).map(roleBadge).join(' ');
  const hrAn = () => !!(W.hr && may('hr.verwalten'));
  /* Zentrale Anmeldung (Keycloak-Host): es gibt nur das Passwort von Keycloak – kein Passwort der Anwendung im Dialog,
     stattdessen der Abschnitt „Zentrale Anmeldung“ (anmeldekonto, lib/anmeldekonten.php) */
  const zentral = () => !!(W.me && W.me.zentral);
  async function renderUsersView() {
    const host = $('#view-users');
    if (!isAdmin()) { if (W.hr) W.hr.renderNurHr(host); return; }   // Personalstelle: nur HR-Angaben
    if (!users) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Mitarbeiter werden geladen …</div>';
    try { [users, rights] = await Promise.all([api('users').then((r) => { twofaModus = r.twofaModus || 'off'; return r.users; }), api('rechte'), hrAn() ? W.hr.laden().catch(() => null) : null]); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    const order = { admin: 0, editor: 1, viewer: 2 };
    const aktivRang = (u) => (u.active ? 2 : u.zugang === false ? 1 : 0);
    const list = users.slice().sort((a, b) => (aktivRang(b) - aktivRang(a)) || (u0(a) - u0(b)) || (order[a.role] ?? 3) - (order[b.role] ?? 3) || a.name.localeCompare(b.name, 'de'));
    function u0(u) { return u.zugang === false ? 1 : 0; }
    const hr = hrAn() && W.hr.daten;
    const rows = list.map((u) => { const z = hr ? W.hr.zelle(u.id) : null; return `<tr data-uid="${esc(u.id)}" tabindex="0" class="${u.active || u.zugang === false ? '' : 'inactive'}">
        <td class="u-name"><div class="nm">${esc(u.name)}${u.id === W.me.id ? ' <span class="muted">(Sie)</span>' : ''}</div><div class="sub uname">${u.zugang === false ? 'ohne Anmeldung' : esc(u.username)}</div>${u.email ? `<div class="sub u-mail">${esc(u.email)}</div>` : ''}</td>
        ${hr ? `<td class="u-abt">${z.abteilung}</td>` : ''}
        <td>${u.zugang === false ? '<span class="muted">–</span>' : roleBadges(u)}${u.zugang !== false && exceptions(u) ? ` <span class="rm-exc" title="Abweichende Rechte: ${u.grant.length} zusätzlich erlaubt, ${u.deny.length} verboten">${esc(exceptions(u))}</span>` : ''}</td>
        <td class="u-st">${u.zugang === false ? '<span class="muted">ohne Anmeldung</span>' : u.active ? '<span class="st-ok">aktiv</span>' : '<span class="st-err">deaktiviert</span>'}${u.twofa ? ' <span class="tf-badge" title="Zwei-Faktor-Anmeldung eingerichtet">2FA</span>' : ''}${u.twofaPflicht ? ` <span class="tf-badge tf-pflicht" title="Zwei-Faktor-Anmeldung für diesen Zugang verpflichtend${u.twofa || u.passkeys ? '' : ' – noch nicht eingerichtet, wird bei der nächsten Anmeldung verlangt'}">2FA-Pflicht</span>` : ''}${u.passkeys ? ` <span class="tf-badge pk-badge" title="${u.passkeys === 1 ? '1 Passkey' : u.passkeys + ' Passkeys'} eingerichtet">${u.passkeys === 1 ? 'Passkey' : u.passkeys + ' Passkeys'}</span>` : ''}${u.lockedUntil ? `<div class="sub st-err">gesperrt bis ${esc(timeOnly(new Date(u.lockedUntil * 1000).toISOString()))} Uhr</div>` : ''}${u.mustChange && !zentral() ? '<div class="sub">muss Passwort ändern</div>' : ''}</td>
        <td class="u-last">${u.zugang === false ? '<span class="muted">–</span>' : u.lastLogin ? esc(dateTime(u.lastLogin)) : '<span class="muted">noch nie</span>'}</td>
        ${hr ? `<td class="u-urlaub num">${z.urlaub}</td>` : ''}
        <td class="u-act"><button type="button" class="btn sm" data-uedit="${esc(u.id)}">Bearbeiten</button></td>
      </tr>`; }).join('');
    const ohne = users.filter((u) => u.zugang === false).length, aus = users.filter((u) => !u.active && u.zugang !== false).length;
    host.innerHTML = `
      <div class="ed-toolbar">
        <span class="ed-hint">${plural(users.length, 'Mitarbeiter', 'Mitarbeiter')} · ${plural(users.filter((u) => u.active).length, 'aktiver Zugang', 'aktive Zugänge')}${ohne ? ` · ${ohne} ohne Anmeldung` : ''}${aus ? ` · ${aus} deaktiviert` : ''}</span>
        <button type="button" class="btn primary" id="user-add">${icon('plus')}Mitarbeiter anlegen</button>
      </div>
      ${hr ? W.hr.altbestand() : ''}
      <div class="gcard"><table class="etab utab"><thead><tr><th>Name / Benutzername</th>${hr ? '<th class="u-abt">Abteilung</th>' : ''}<th>Rolle</th><th class="u-st">Status</th><th class="u-last">Letzte Anmeldung</th>${hr ? `<th class="u-urlaub num">Urlaub ${new Date().getFullYear()}</th>` : ''}<th class="u-act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${rows}</tbody></table></div>
      <section class="gcard us-rollen-link"><p><strong>Rollen und Rechte</strong><br><span class="hint">Welche Module eine Rolle öffnen und was sie darin sehen und bearbeiten darf – auch eigene Rollen anlegen.</span></p>
        <button type="button" class="btn" id="us-zu-rollen">${icon('key')}Rollen und Rechte verwalten</button></section>`;
  }
  $('#view-users').addEventListener('click', (e) => {
    if (e.target.closest('#user-add')) { openUser(null); return; }
    if (e.target.closest('#us-zu-rollen')) { W.setView('rollen'); return; }
    const tr = e.target.closest('tr[data-uid]');
    if (tr) openUser(tr.dataset.uid);
  });
  $('#view-users').addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr[data-uid]')) openUser(e.target.dataset.uid); });

  const dlgUser = $('#dlg-user');
  /* Rollen zur Auswahl (aus „rechte“: Administrator, Standardrollen, eigene) – Fallback: die drei bisherigen */
  const rollenListe = () => (rights && rights.rollen ? rights.rollen : ['admin', 'editor', 'viewer'].map((id) => ({ id, name: ROLE_LABEL[id], beschreibung: ROLE_DESC[id] })));
  const startRollen = (u) => (u ? rollenVon(u) : ['editor']);
  let editUid = null;
  function genPassword(n = 14) {   // 14: Passwort der Anwendung (12 Zeichen + Striche) · 16: zentrale Anmeldung (mindestens 12 Zeichen ohne Striche)
    const chars = 'abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789';
    const a = new Uint32Array(n);
    crypto.getRandomValues(a);
    const s = [...a].map((x) => chars[x % chars.length]).join('').replace(/(.{4})(?=.)/g, '$1-');
    return n === 14 ? s.slice(0, 14) : s;
  }
  function userRightsRows(u, rollen) {
    if (!rights || rollen.includes('admin')) return '';
    const base = rollenRechte(rollen);
    const val = (k) => (u && u.grant.includes(k) ? 'grant' : u && u.deny.includes(k) ? 'deny' : '');
    return `<table class="etab urtab"><tbody>${rights.catalog.map((p) => `<tr><td>${esc(p.label)}<div class="sub">${esc(p.group)}</div></td><td><select data-ur="${esc(p.key)}" aria-label="${esc(p.label)}">
      <option value=""${val(p.key) === '' ? ' selected' : ''}>wie Rolle (${base.has(p.key) ? 'ja' : 'nein'})</option><option value="grant"${val(p.key) === 'grant' ? ' selected' : ''}>erlauben</option><option value="deny"${val(p.key) === 'deny' ? ' selected' : ''}>verbieten</option></select></td></tr>`).join('')}</tbody></table>`;
  }
  /* Zwei-Faktor-Pflicht je Mitarbeiter: gesperrt, wenn die Sicherheitseinstellung den Zugang ohnehin verpflichtet (alle bzw.
     Administratoren) oder beim eigenen Zugang (gesperrt = nicht mitgesendet = unverändert); entscheidend ist der Server
     (twofa_required, user_save) */
  const PFLICHT_HINWEIS = 'Ohne eingerichteten zweiten Faktor (Authenticator-App oder Passkey) wird die Einrichtung bei der nächsten Anmeldung verlangt. Gilt für die Anmeldung hier und über die STAFL-Anmeldung.';
  const pflichtDurchEinstellung = (role) => (twofaModus === 'all' ? 'Die Sicherheitseinstellung verpflichtet bereits alle Zugänge.'
    : twofaModus === 'admins' && role === 'admin' ? 'Für Administratoren ist die Zwei-Faktor-Anmeldung immer verpflichtend.' : '');
  function pflichtZeigen(role) {
    const box = $('#user-body [name="twofaPflicht"]'); if (!box) return;
    const self = !!editUid && editUid === W.me.id, zwang = pflichtDurchEinstellung(role);
    if (!box.disabled || box.dataset.wahl === undefined) box.dataset.wahl = box.checked ? '1' : '';   // eigene Auswahl merken, falls die Sperre wieder entfällt
    box.disabled = !!zwang || self;
    box.checked = !!zwang || box.dataset.wahl === '1';
    $('#us-2fa-hint').textContent = zwang || (self ? 'Die Pflicht für den eigenen Zugang kann nur ein anderer Administrator ändern.'
      : role === 'admin' ? 'Über die STAFL-Anmeldung ist der zweite Faktor für Administratoren immer Pflicht; das Häkchen verlangt ihn auch bei der Anmeldung hier.' : PFLICHT_HINWEIS);
  }
  /* Gewählte Rollen im Dialog: Administrator schließt alle anderen aus, ohne Auswahl bleibt die bisherige Hauptrolle */
  const gewaehlteRollen = () => $$('#user-body [name="rollen"]:checked').map((x) => x.value);
  dlgUser.addEventListener('change', (e) => {
    if (e.target.name === 'zugang') { zugangZeigen(); return; }
    if (e.target.name !== 'rollen') return;
    if (e.target.checked && e.target.value === 'admin') for (const x of $$('#user-body [name="rollen"]')) { if (x.value !== 'admin') x.checked = false; }
    if (e.target.checked && e.target.value !== 'admin') { const ad = $('#user-body [name="rollen"][value="admin"]'); if (ad) ad.checked = false; }
    const gew = gewaehlteRollen();
    pflichtZeigen(gew.includes('admin') ? 'admin' : gew[0] || '');
    const box = $('#ur-box'); if (!box) return;
    const u = editUid ? users.find((x) => x.id === editUid) : null;
    box.hidden = gew.includes('admin');
    if (box.hidden) return;   // Auswahl bleibt erhalten, falls wieder eine andere Rolle gewählt wird
    const keep = {}; for (const s2 of $$('#ur-list [data-ur]')) keep[s2.dataset.ur] = s2.value;
    $('#ur-list').innerHTML = userRightsRows(u, gew);
    for (const s2 of $$('#ur-list [data-ur]')) if (keep[s2.dataset.ur] !== undefined) s2.value = keep[s2.dataset.ur];
  });
  /* Benutzername aus Vor- und Nachname wie auf dem Server (benutzername_vorschlag): „vorname-nachname“, Umlaute ae/oe/ue/ss */
  function unameVorschlag(vor, nach) {
    const teil = (x) => String(x || '').toLowerCase().trim().replace(/ä/g, 'ae').replace(/ö/g, 'oe').replace(/ü/g, 'ue').replace(/ß/g, 'ss')
      .normalize('NFD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
    const basis = [teil(vor), teil(nach)].filter(Boolean).join('-').slice(0, 32).replace(/-+$/, '');
    if (basis.length < 2) return '';
    const belegt = new Set((users || []).map((x) => x.username.toLowerCase()));
    let u = basis, n = 2;
    while (belegt.has(u)) { const suf = '-' + n++; u = basis.slice(0, 32 - suf.length).replace(/-+$/, '') + suf; }
    return u;
  }
  const teileName = (u) => {   // ältere Zugänge haben nur „name“: letztes Wort = Nachname
    if (!u) return ['', ''];
    if (u.vorname || u.nachname) return [u.vorname, u.nachname];
    const t = String(u.name || '').trim().split(/\s+/);
    return t.length > 1 ? [t.slice(0, -1).join(' '), t[t.length - 1]] : [t[0] || '', ''];
  };
  const mailInfoText = (u) => (u && u.mailInfo ? `Zugangsdaten zuletzt per E-Mail: ${dateTime(u.mailInfo.t)} an ${u.mailInfo.to}${u.mailInfo.mitPasswort ? ' (mit Startpasswort)' : ''}${u.mailInfo.ok ? '' : ' – nicht zugestellt'}` : '');
  /* ---------- Zentrale Anmeldung (Keycloak): Zustand und Aktionen für ein Mitarbeiterkonto ---------- */
  const kaAbschnitt = () => `<fieldset class="span2 ka" id="ka" data-nurzugang><legend>Zentrale Anmeldung</legend>
      <p class="ka-status" id="ka-status"><span class="muted">Wird geladen …</span></p>
      <div class="ka-knoepfe" id="ka-knoepfe"></div>
      <div class="ka-pw" id="ka-pw" hidden>
        <div class="fld"><span>Neues Passwort</span><div class="pw-row"><input name="ka_pw" type="text" autocomplete="new-password" minlength="12" maxlength="200" placeholder="mindestens 12 Zeichen" aria-label="Neues Passwort"><button type="button" class="btn" data-ka="gen">Vorschlag</button></div></div>
        <label class="check"><input type="checkbox" name="ka_aendern" checked> muss bei der nächsten Anmeldung ein eigenes Passwort festlegen</label>
        <p class="hint" id="ka-nur-temporaer" hidden>Bei Administratoren und Konten mit Pflicht zum zweiten Faktor immer: Das Passwort gilt nur bis zur nächsten Anmeldung.</p>
        <div class="ka-knoepfe"><button type="button" class="btn" data-ka="pw-ab">Ausblenden</button><button type="button" class="btn primary" data-ka="passwort">Passwort setzen</button></div>
      </div>
      <p class="ka-meldung" id="ka-meldung" role="status"></p>
    </fieldset>`;
  let kaKonto = null;
  function kaZeigen(k) {
    kaKonto = k;
    const st = $('#ka-status'), kn = $('#ka-knoepfe');
    if (!st) return;
    const t = [];
    if (k.fehler) { st.innerHTML = `<span class="st-err">${esc(k.fehler)}</span>`; kn.innerHTML = ''; return; }
    if (!k.eingerichtet) { st.innerHTML = `<span class="muted">${esc(k.hinweis || 'Noch nicht eingerichtet.')}</span>`; kn.innerHTML = ''; return; }
    if (!k.vorhanden) {
      st.innerHTML = `<span class="st-warn">Noch kein Konto in der zentralen Anmeldung – der Mitarbeiter kann sich nicht anmelden.</span>${k.hinweis ? `<br><span class="muted">${esc(k.hinweis)}</span>` : ''}`;
      kn.innerHTML = k.fremd ? '' : `<button type="button" class="btn" data-ka="anlegen">${icon('plus', 'sm')}Konto anlegen</button>`;
      return;
    }
    t.push(k.aktiv ? '<span class="st-ok">Konto aktiv</span>' : '<span class="st-err">Konto in Keycloak gesperrt</span>');
    if (k.gesperrt) t.push(`<span class="st-err">vorübergehend gesperrt nach ${esc(String(k.fehlversuche))} Fehlversuchen</span>`);
    t.push(k.passwort ? 'Passwort gesetzt' : '<span class="st-warn">noch kein Passwort</span>');
    if (k.passwortAendern) t.push('muss bei der nächsten Anmeldung ein eigenes Passwort festlegen');
    if (k.einmalcode) t.push(k.einmalcode === 1 ? 'Einmalcode eingerichtet' : `${k.einmalcode} Einmalcode-Geräte`);
    if (k.passkeys) t.push(k.passkeys === 1 ? '1 Passkey' : `${k.passkeys} Passkeys`);
    st.innerHTML = t.join(' · ');
    // Administratoren und Pflicht-Konten: Passwort nur vorübergehend (der Server erzwingt es ebenfalls)
    const cb = $('#user-body [name="ka_aendern"]'), nur = !!k.nurTemporaer;
    if (cb) { if (nur) cb.checked = true; cb.disabled = nur; }
    if ($('#ka-nur-temporaer')) $('#ka-nur-temporaer').hidden = !nur;
    kn.innerHTML = `<button type="button" class="btn" data-ka="pw-auf">${icon('key', 'sm')}Passwort setzen …</button>`
      + (k.email ? `<button type="button" class="btn" data-ka="link">${icon('mail', 'sm')}Link zum Passwort-Festlegen per Mail</button>` : '')
      + (k.gesperrt || !k.aktiv ? `<button type="button" class="btn" data-ka="entsperren">${icon('check', 'sm')}Entsperren</button>` : '');
  }
  async function kaLaden(id) {
    try { const r = await api('anmeldekonto', { query: '&id=' + encodeURIComponent(id) }); kaZeigen(r.konto); }
    catch (ex) { kaZeigen({ eingerichtet: true, fehler: ex.message }); }
  }
  async function kaAktion(was, knopf) {
    const m = $('#ka-meldung'), body = { id: editUid, was };
    m.textContent = ''; m.className = 'ka-meldung';
    if (was === 'passwort') {
      body.passwort = $('#user-body [name="ka_pw"]').value;
      body.aendern = $('#user-body [name="ka_aendern"]').checked;
      if (body.passwort.length < 12) { m.textContent = 'Das Passwort muss mindestens 12 Zeichen lang sein.'; m.classList.add('form-err'); return; }
    }
    if (knopf) knopf.disabled = true;
    try {
      const r = await api('anmeldekonto_aendern', { body });
      kaZeigen(r.konto);
      m.classList.add('st-ok');
      m.textContent = was === 'passwort' ? ((r.temporaer ?? body.aendern) ? 'Passwort gesetzt – bitte persönlich weitergeben; bei der ersten Anmeldung legt der Mitarbeiter ein eigenes fest.' : 'Passwort gesetzt.')
        : was === 'link' ? `Mail mit Link an ${r.an} geschickt (${72} Stunden gültig).` : was === 'entsperren' ? 'Konto entsperrt.' : 'Konto angelegt – jetzt Passwort setzen oder den Link per Mail schicken.';
      if (was === 'passwort') { $('#ka-pw').hidden = false; $('#user-body [name="ka_pw"]').readOnly = true; $('#ka-pw [data-ka="passwort"]').hidden = true; $('#ka-pw [data-ka="gen"]').hidden = true; }
    } catch (ex) { m.textContent = ex.message; m.classList.add('form-err'); }
    if (knopf) knopf.disabled = false;
  }
  dlgUser.addEventListener('click', (e) => {
    const k = e.target.closest('[data-ka]');
    if (!k) return;
    const a = k.dataset.ka;
    if (a === 'pw-auf') { $('#ka-pw').hidden = false; const i = $('#user-body [name="ka_pw"]'); i.readOnly = false; i.value = ''; $('#ka-pw [data-ka="passwort"]').hidden = false; $('#ka-pw [data-ka="gen"]').hidden = false; i.focus(); return; }
    if (a === 'pw-ab') { $('#ka-pw').hidden = true; return; }
    if (a === 'gen') { const i = $('#user-body [name="ka_pw"]'); i.value = genPassword(16); i.select(); return; }
    kaAktion(a, k);
  });

  let unameManuell = false, fertigInfo = null;
  function openUser(id) {
    const u = id ? users.find((x) => x.id === id) : null;
    editUid = id; unameManuell = false; fertigInfo = null;
    const self = u && u.id === W.me.id;
    const [vor, nach] = teileName(u);
    const zugang = !u || u.zugang !== false;
    $('#user-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="us-title">${u ? 'Mitarbeiter bearbeiten' : 'Mitarbeiter anlegen'}</h2><p>${u ? `Angelegt ${esc(dateTime(u.created))}${u.createdBy ? ' von ' + esc(u.createdBy) : ''}` : 'Mit Anmeldung: Benutzername und Passwort. Ohne Anmeldung: nur für die Urlaubsverwaltung (z. B. Lager).'}</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Abbrechen">${icon('x')}</button></div>
      <div class="dlg-body form-grid two">
        <label class="fld"><span>Vorname</span><input name="vorname" value="${esc(vor)}" maxlength="40" required autocomplete="off" placeholder="z. B. Max"></label>
        <label class="fld"><span>Nachname</span><input name="nachname" value="${esc(nach)}" maxlength="40"${u ? '' : ' required'} autocomplete="off" placeholder="z. B. Mustermann"></label>
        ${self ? '' : `<div class="fld span2"><span>Anmeldung</span><div class="role-pick us-zugang">
          <label class="role-opt"><input type="radio" name="zugang" value="1"${zugang ? ' checked' : ''}><span><strong>Mit Anmeldung</strong><small>Meldet sich an, sieht seine Anwendungen und seinen Urlaub</small></span></label>
          <label class="role-opt"><input type="radio" name="zugang" value="0"${zugang ? '' : ' checked'}><span><strong>Ohne Anmeldung</strong><small>Nur in der Urlaubsverwaltung (Kalender, Export) – kein Zugang</small></span></label></div></div>`}
        <label class="fld" data-nurzugang><span>E-Mail <small class="muted">(für die Zugangsdaten)</small></span><input name="email" type="email" value="${esc(u ? u.email : '')}" maxlength="160" autocomplete="off" spellcheck="false" placeholder="z. B. max.mustermann@standard-fleisch.de"></label>
        <label class="fld" data-nurzugang><span>Benutzername${u ? '' : ' <small class="muted">(automatisch)</small>'}</span><input name="username" value="${esc(u ? u.username : '')}" maxlength="32" autocapitalize="none" spellcheck="false" placeholder="vorname-nachname"${u ? ' disabled' : ' required'}></label>
        ${u ? '' : '<p class="hint span2 us-uhint" id="us-uhint" data-nurzugang>Wird aus Vorname-Nachname gebildet (Umlaute als ae/oe/ue/ss); bei Bedarf überschreibbar.</p>'}
        <div class="fld span2" data-nurzugang><span>Rollen <small class="muted">(mehrere möglich – die Rechte addieren sich)</small></span>
          <div class="role-pick${rollenListe().length > 3 ? ' mehr' : ''}">${rollenListe().map((r) => `<label class="role-opt"><input type="checkbox" name="rollen" value="${esc(r.id)}"${startRollen(u).includes(r.id) ? ' checked' : ''}${self ? ' disabled' : ''}><span><strong>${esc(r.name)}</strong><small>${esc(r.beschreibung || ROLE_DESC[r.id] || '')}</small></span></label>`).join('')}</div>
        </div>
        <label class="check span2" data-nurzugang><input type="checkbox" name="active"${!u || u.active || !zugang ? ' checked' : ''}${self ? ' disabled' : ''}> Zugang aktiv${self ? ' <span class="muted">(eigener Zugang)</span>' : ''}</label>
        ${zentral() ? (u && !self && zugang ? kaAbschnitt() : u ? '' : '<p class="hint span2" data-nurzugang>Das Passwort vergibt die zentrale Anmeldung: nach dem Anlegen im Abschnitt „Zentrale Anmeldung“ das Konto anlegen und ein Passwort setzen oder den Link per Mail schicken.</p>')
          : self ? '<p class="hint span2">Das eigene Passwort ändern Sie über „Passwort ändern“ im Menü.</p>' : `<div class="fld span2" data-nurzugang><span>${u && zugang ? 'Neues Passwort setzen <small class="muted">(leer lassen = unverändert)</small>' : 'Passwort'}</span>
          <div class="pw-row"><input name="password" type="text" autocomplete="new-password" minlength="10" maxlength="200" placeholder="mindestens 10 Zeichen"${u && zugang ? '' : ' data-pflicht'}><button type="button" class="btn" data-uact="gen">Vorschlag</button></div>
        </div>`}
        ${self || zentral() ? '' : `<label class="check span2" data-nurzugang><input type="checkbox" name="mustChange" checked> Mitarbeiter muss das Passwort bei der nächsten Anmeldung ändern</label>`}
        <div class="span2 us-2fa" data-nurzugang><label class="check"><input type="checkbox" name="twofaPflicht"${u && u.twofaPflicht ? ' checked' : ''}> Zwei-Faktor-Anmeldung verpflichtend</label><p class="hint" id="us-2fa-hint"></p></div>
        ${u && u.twofa && !self && !zentral() ? '<label class="check span2"><input type="checkbox" name="reset2fa"> Zwei-Faktor-Anmeldung zurücksetzen (z. B. Handy verloren – wird beim nächsten Anmelden neu eingerichtet)</label>' : ''}
        ${u && u.passkeys && !self && !zentral() ? `<label class="check span2"><input type="checkbox" name="resetPasskeys"> Alle Passkeys entfernen (${u.passkeys === 1 ? '1 Passkey' : u.passkeys + ' Passkeys'}, z. B. Gerät verloren)</label>` : ''}
        ${u && u.geraete && u.geraete.length && !self && !zentral() ? `<label class="check span2"><input type="checkbox" name="resetGeraete"> Vertraute Geräte entfernen (${esc(geraeteText(u.geraete))})</label>` : ''}
        <details class="span2 ur-box" id="ur-box" data-nurzugang${u && (u.grant.length || u.deny.length) ? ' open' : ''}${startRollen(u).includes('admin') ? ' hidden' : ''}><summary>Abweichende Rechte für diesen Mitarbeiter${u && exceptions(u) ? ` <span class="rm-exc">${esc(exceptions(u))}</span>` : ''}</summary>
          <p class="hint">Normalerweise gelten die Rechte der Rolle. Hier können Sie einzelne Rechte zusätzlich erlauben oder verbieten.</p>
          <div id="ur-list">${userRightsRows(u, startRollen(u))}</div></details>
        ${u && u.lockedUntil ? `<p class="span2 st-err" style="margin:0">Zugang nach Fehlversuchen gesperrt bis ${esc(timeOnly(new Date(u.lockedUntil * 1000).toISOString()))} Uhr – Entsperren im Modul Sicherheit (Anmeldung &amp; Sitzungen).</p>` : ''}
        ${u && u.mailInfo ? `<p class="hint span2" style="margin:0">${esc(mailInfoText(u))}</p>` : ''}
        ${hrAn() ? W.hr.formular(u ? u.id : null) : ''}
        <p class="form-err span2" id="user-err" role="alert"></p>
      </div>
      <div class="dlg-foot">
        <span class="left">${u && !self ? `<button type="button" class="btn sm ghost" data-uact="del" style="color:var(--accent)">${icon('trash', 'sm')}Mitarbeiter löschen</button>` : ''}${u && !self && u.email && u.active && !zentral() ? `<button type="button" class="btn sm ghost" data-uact="mail" data-nurzugang>${icon('mail', 'sm')}Zugangsdaten per E-Mail</button>` : ''}</span>
        <button type="button" class="btn" data-close>Abbrechen</button>
        <button type="submit" class="btn primary">${u ? 'Speichern' : 'Mitarbeiter anlegen'}</button>
      </div>`;
    pflichtZeigen(startRollen(u).includes('admin') ? 'admin' : 'editor');
    zugangZeigen();
    dlgUser.showModal();
    if ($('#ka')) kaLaden(u.id);
    $('#user-body [name="vorname"]').focus();
  }
  /* Mit/ohne Anmeldung: Felder für Anmeldung, Rolle, Passwort, zweiten Faktor und Rechte nur mit Anmeldung */
  function zugangZeigen() {
    const r = $('#user-body [name="zugang"]:checked');
    const mit = !r || r.value === '1';
    for (const el of $$('#user-body [data-nurzugang]')) el.hidden = !mit || (el.id === 'ur-box' && gewaehlteRollen().includes('admin'));
    const pw = $('#user-body [name="password"]');
    if (pw) pw.required = mit && pw.hasAttribute('data-pflicht');
  }
  /* Nach dem Anlegen (bzw. neuem Passwort): Zusammenfassung und „Zugangsdaten per E-Mail senden“ */
  function zeigeFertig(u, pw, neu) {
    fertigInfo = { id: u.id, pw };
    const mitPwMoeglich = !!(pw && u.mustChange);
    $('#user-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="us-title">${neu ? 'Mitarbeiter angelegt' : 'Neues Passwort gesetzt'}</h2><p>${esc(u.name)} · ${esc(rollenVon(u).map(rollenName).join(', '))}</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body us-fertig">
        <dl class="us-daten"><dt>Benutzername</dt><dd><code>${esc(u.username)}</code></dd>
          ${pw ? `<dt>${neu ? 'Startpasswort' : 'Neues Passwort'}</dt><dd><code id="us-pw">${esc(pw)}</code> <button type="button" class="btn sm ghost" data-uact="copy">${icon('copy', 'sm')}Kopieren</button></dd>` : ''}
          <dt>E-Mail</dt><dd>${u.email ? esc(u.email) : '<span class="muted">keine hinterlegt</span>'}</dd></dl>
        ${u.email ? `<div class="us-mail">
            ${mitPwMoeglich ? `<label class="check"><input type="checkbox" id="us-mitpw" checked><span>${neu ? 'Startpasswort' : 'Neues Passwort'} in die E-Mail aufnehmen <small class="muted">(muss bei der ersten Anmeldung geändert werden)</small></span></label>`
              : pw ? '<p class="hint">Das Passwort wird nicht mitgesendet, weil es nicht bei der ersten Anmeldung geändert werden muss – bitte separat weitergeben.</p>' : ''}
            <p class="hint">Die E-Mail enthält Benutzername, Link zum Eingabebereich und den Hinweis zur ersten Anmeldung.</p>
            <p class="us-mail-st" id="us-mail-st" role="status"></p></div>`
          : `<p class="hint">${pw ? 'Passwort jetzt sicher weitergeben. ' : ''}Für eine E-Mail mit den Zugangsdaten bitte eine E-Mail-Adresse hinterlegen (Mitarbeiter bearbeiten).</p>`}
        <p class="form-err" id="user-err" role="alert"></p>
      </div>
      <div class="dlg-foot">${u.email ? `<button type="button" class="btn" data-close>Fertig</button><button type="button" class="btn primary" data-uact="sendmail">${icon('mail')}Zugangsdaten per E-Mail senden</button>` : '<button type="button" class="btn primary" data-close>Fertig</button>'}</div>`;
    const b = $('#user-body [data-uact="sendmail"]') || $('#user-body [data-close]'); if (b) b.focus();
  }
  async function sendeZugang(id, pw) {
    const r = await api('user_mail', { body: { id, password: pw || '' } });
    const i = users.findIndex((x) => x.id === id); if (i >= 0) users[i] = r.user;
    return r.user;
  }
  dlgUser.addEventListener('input', (e) => {
    const f = $('#user-body');
    if (editUid || fertigInfo || !f.username) return;
    if (e.target.name === 'username') { unameManuell = e.target.value.trim() !== ''; return; }
    if ((e.target.name === 'vorname' || e.target.name === 'nachname') && !unameManuell) f.username.value = unameVorschlag(f.vorname.value, f.nachname.value);
  });
  dlgUser.addEventListener('click', async (e) => {
    const a = e.target.closest('[data-uact]')?.dataset.uact;
    if (a === 'gen') { const i = $('#user-body [name="password"]'); i.value = genPassword(); i.select(); return; }
    if (a === 'copy') { try { await navigator.clipboard.writeText(fertigInfo.pw); toast('Passwort kopiert.'); } catch { const c = $('#us-pw'); if (c) getSelection().selectAllChildren(c); } return; }
    if (a === 'sendmail') {
      const btn = e.target.closest('button'), st = $('#us-mail-st'), mit = $('#us-mitpw');
      btn.disabled = true; $('#user-err').textContent = '';
      try {
        const u = await sendeZugang(fertigInfo.id, mit && mit.checked ? fertigInfo.pw : '');
        st.innerHTML = `${icon('check', 'sm')} E-Mail an ${esc(u.mailInfo.to)} gesendet${u.mailInfo.mitPasswort ? ' (mit Passwort)' : ''}.`;
        st.className = 'us-mail-st st-ok';
        btn.innerHTML = `${icon('mail')}Erneut senden`;
        renderUsersView();
      } catch (ex) { $('#user-err').textContent = ex.message; }
      btn.disabled = false;
      return;
    }
    if (a === 'mail') {
      const u = users.find((x) => x.id === editUid);
      if (!(await confirmBox('Zugangsdaten per E-Mail senden?', `${esc(u.name)} erhält an ${esc(u.email)} Benutzername und Link zum Eingabebereich – ohne Passwort (das wird nicht gespeichert und muss separat weitergegeben werden).`, 'Senden'))) return;
      try { const nu = await sendeZugang(u.id, ''); toast(`Zugangsdaten an ${nu.mailInfo.to} gesendet.`); renderUsersView(); dlgUser.close(); } catch (ex) { $('#user-err').textContent = ex.message; }
      return;
    }
    if (a === 'del') {
      const u = users.find((x) => x.id === editUid);
      if (!(await confirmBox('Mitarbeiter löschen?', `„${esc(u.name)}“ (${esc(u.username)}) wird gelöscht. Die Einträge im Protokoll und in der Urlaubsverwaltung bleiben erhalten. Alternativ können Sie den Zugang nur deaktivieren oder auf „ohne Anmeldung“ stellen.`, 'Löschen', true))) return;
      try { await api('user_delete', { body: { id: u.id } }); dlgUser.close(); toast(`Mitarbeiter „${u.username}“ gelöscht.`); renderUsersView(); } catch (ex) { $('#user-err').textContent = ex.message; }
    }
  });
  $('#user-body').addEventListener('submit', async (e) => {
    e.preventDefault();
    if (fertigInfo) return;
    const f = e.target, err = $('#user-err');
    err.textContent = '';
    const zr = f.querySelector('[name="zugang"]:checked');
    const zugang = !zr || zr.value === '1';
    const pw = f.password && zugang ? f.password.value.trim() : '';
    if (pw && pw.length < 10) { err.textContent = 'Das Passwort muss mindestens 10 Zeichen lang sein.'; return; }
    const u = editUid ? users.find((x) => x.id === editUid) : null;
    const body = { zugang,
      id: editUid || '', vorname: f.vorname.value.trim(), nachname: f.nachname.value.trim(), email: f.email.value.trim(),
      username: u ? u.username : f.username.value.trim(),
      role: zugang ? gewaehlteRollen()[0] || (u && u.role) : (u && u.zugang !== false ? u.role : 'viewer'), active: f.active.checked,
      password: pw, mustChange: f.mustChange ? f.mustChange.checked : false, reset2fa: f.reset2fa ? f.reset2fa.checked : false,
      resetPasskeys: f.resetPasskeys ? f.resetPasskeys.checked : false, resetGeraete: f.resetGeraete ? f.resetGeraete.checked : false,
    };
    if (zugang && !(u && u.id === W.me.id)) {   // eigener Zugang: Rollen gesperrt (nicht mitgesendet = unverändert)
      body.rollen = gewaehlteRollen();
      if (!body.rollen.length) { err.textContent = 'Bitte mindestens eine Rolle wählen.'; return; }
    }
    if (f.twofaPflicht && !f.twofaPflicht.disabled) body.twofaPflicht = f.twofaPflicht.checked;   // gesperrt = unverändert
    if ($('#ur-list [data-ur]')) { body.grant = $$('#ur-list [data-ur]').filter((x) => x.value === 'grant').map((x) => x.dataset.ur); body.deny = $$('#ur-list [data-ur]').filter((x) => x.value === 'deny').map((x) => x.dataset.ur); }
    const btn = f.querySelector('[type="submit"]');
    btn.disabled = true;
    try {
      const r = await api('user_save', { body });
      editUid = r.user.id;   // ab jetzt Bearbeiten (falls die HR-Angaben scheitern, legt ein zweiter Klick keinen zweiten Mitarbeiter an)
      try { if (hrAn()) await W.hr.speichern(r.user.id, f); }
      catch (ex2) { renderUsersView(); err.textContent = 'Mitarbeiter gespeichert, Urlaubsangaben nicht: ' + ex2.message; return; }
      if (zentral() && zugang && !u) {   // Passwort vergibt Keycloak: gleich weiter zum Abschnitt „Zentrale Anmeldung“
        await renderUsersView();
        openUser(r.user.id);
        toast(`Mitarbeiter „${r.user.name}“ angelegt – jetzt das Konto in der zentralen Anmeldung anlegen.`);
        return;
      }
      renderUsersView();
      if (zugang && (!u || (pw && r.user.id !== W.me.id))) { zeigeFertig(r.user, pw, !u); return; }   // Abschluss mit „Zugangsdaten per E-Mail senden“
      dlgUser.close();
      toast(u ? `Änderungen an „${r.user.name}“ gespeichert.` : `Mitarbeiter „${r.user.name}“ ohne Anmeldung angelegt.`);
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
          <td class="ord-sum">${plural(o.positionCount, 'Position', 'Positionen')}<div class="sub">${esc(fmtNum.format(o.total))} €${o.onRequest ? ' + a. Anfr.' : ''}${o.fracht && o.fracht.kosten ? ' + Fracht' : ''}</div></td>
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
  /* ======================= Einkauf: Fehlmengen offener Bestellwünsche (alle Mitarbeiter; Melden ab Bearbeiter) ======================= */
  const fmtQty = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 3 });
  const eur2 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });   // Preise wie im Portal und in der E-Mail (Cent)
  const qty = (v) => fmtQty.format(v) + ' kg';
  let ekSel = null, ekData = null;
  async function renderEinkaufView() {
    const host = $('#view-einkauf');
    if (!host.innerHTML) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Einkauf wird geladen …</div>';
    let r;
    try { r = ekData = await api('einkauf'); } catch (e) { host.innerHTML = `<div class="err-box" role="alert">${esc(e.message)}</div>`; return; }
    const st = r.stock;
    const ref = st ? (st.importedAt || st.date) : null;
    const age = ref ? Math.floor((Date.now() - new Date(ref).getTime()) / 86400000) : null;
    const stand = st ? `${st.date ? dmyIso(st.date) : 'unbekanntem Datum'}${st.importedAt ? ` (übernommen ${dateTime(st.importedAt)})` : ''}` : '';
    const codes = r.items.map((i) => i.code);
    ekSel = ekSel === null ? new Set(r.items.filter((i) => i.neu).map((i) => i.code)) : new Set([...ekSel].filter((c) => codes.includes(c)));
    const rows = r.items.map((it) => `<tr data-ek="${esc(it.code)}">
        ${r.canSend ? `<td class="ek-sel"><input type="checkbox" data-eksel="${esc(it.code)}"${ekSel.has(it.code) ? ' checked' : ''} aria-label="${esc(it.code)} ${esc(it.name)} auswählen"></td>` : ''}
        <td class="ek-code">${esc(it.code)}</td>
        <td class="ek-art"><div class="nm">${esc(it.name)}</div><div class="sub">${it.orders.map((o) => `${esc(o.nr)}${o.firma ? ' · ' + esc(o.firma) : ''}: ${esc(qty(o.qty))}${o.termin ? ' · ' + esc(dmyIso(o.termin)) : ''}`).join('<br>')}</div></td>
        <td class="num" data-l="Bestellt">${esc(qty(it.ordered))}</td>
        <td class="num" data-l="Bestand">${esc(qty(it.available))}</td>
        <td class="num ek-short" data-l="Fehlmenge">${esc(qty(it.short))}</td>
        <td class="ek-termin" data-l="Termin">${it.termin ? esc(dmyIso(it.termin)) : '<span class="muted">offen</span>'}</td>
        <td class="ek-st">${it.gemeldet ? `<span class="${it.neu ? 'st-warn' : 'st-ok'}">${it.neu ? 'mehr als gemeldet' : 'gemeldet'}</span><div class="sub">${esc(dateTime(it.gemeldet.t))}${it.gemeldet.by ? ' · ' + esc(it.gemeldet.by) : ''}${it.neu ? ' · damals ' + esc(qty(it.gemeldet.kg)) : ''}</div>` : '<span class="ek-new">neu</span>'}</td>
      </tr>`).join('');
    host.innerHTML = `
      <div class="gcard ek-head">
        <div class="ek-kpis">
          <div><strong>${r.items.length}</strong><span>Artikel mit Fehlmenge</span></div>
          <div><strong>${esc(qty(r.shortTotal))}</strong><span>Fehlmenge gesamt</span></div>
          <div><strong>${r.openOrders}</strong><span>offene Bestellwünsche</span></div>
        </div>
        ${st ? `<p class="hint">Bestellte Mengen aus offenen Bestellwünschen (Neu, In Bearbeitung, Bestätigt) gegenüber dem Bestand vom ${esc(stand)}.</p>` : ''}
        ${!st ? '<p class="st-warn ek-warn">Es ist keine Bestandsliste vorhanden. Bitte unter „Bestand“ eine aktuelle Liste übernehmen – erst dann lassen sich Fehlmengen berechnen.</p>'
          : age >= 3 ? `<p class="st-warn ek-warn">Der Bestand ist ${age} Tage alt. Für verlässliche Fehlmengen bitte unter „Bestand“ eine aktuelle Liste übernehmen.</p>` : ''}
        ${r.ohneNr ? `<p class="hint">${esc(plural(r.ohneNr, 'Position', 'Positionen'))} ohne Artikelnummer ${r.ohneNr === 1 ? 'ist' : 'sind'} nicht berücksichtigt.</p>` : ''}
      </div>
      ${r.items.length ? `<div class="gcard ek-wrap"><table class="etab ektab"><thead><tr>${r.canSend ? `<th class="ek-sel"><input type="checkbox" id="ek-all" aria-label="Alle auswählen"${ekSel.size === r.items.length ? ' checked' : ''}></th>` : ''}<th>Art.-Nr.</th><th>Artikel / Bestellwünsche</th><th class="num">Bestellt</th><th class="num">Bestand</th><th class="num">Fehlmenge</th><th>Termin</th><th>Status</th></tr></thead><tbody>${rows}</tbody></table></div>`
        : st ? '<div class="gcard ek-empty"><p>Keine Fehlmengen – alle offenen Bestellwünsche sind durch den Bestand gedeckt.</p></div>' : ''}
      ${r.canSend && r.items.length ? `<form class="gcard sec-form ek-send" id="ek-form" autocomplete="off">
        <h3 class="sec-h">Einkauf benachrichtigen</h3>
        ${!r.recipients ? '<p class="st-warn">Noch keine Empfänger für „Einkaufsbedarf“. Ein Administrator legt sie unter Verwaltung → E-Mail → Benachrichtigungen fest.</p>' : !r.mail ? '<p class="st-warn">Der E-Mail-Versand ist noch nicht eingerichtet (Verwaltung → E-Mail).</p>' : `<p class="hint">Die E-Mail enthält die ausgewählten Artikel mit Fehlmenge, Bestellwünschen und Terminen (an ${esc(plural(r.recipients, 'Empfänger', 'Empfänger'))}).</p>`}
        <label class="fld"><span>Hinweis an den Einkauf <small>(optional)</small></span><textarea name="note" rows="2" maxlength="1000" placeholder="z. B. Termin für Kunde X ist fest zugesagt"></textarea></label>
        <p class="form-err" id="ek-err" role="alert"></p>
        <div class="sec-foot"><button type="submit" class="btn primary" id="ek-send">${icon('send', 'sm')}<span id="ek-btn-l"></span></button></div>
      </form>` : ''}`;
    ekCount();
  }
  function ekCount() {
    const l = $('#ek-btn-l');
    if (!l || !ekData) return;
    const n = ekSel.size;
    l.textContent = n ? `${n} Artikel melden` : 'Bitte Artikel auswählen';
    $('#ek-send').disabled = !n || !ekData.recipients || !ekData.mail;
    const all = $('#ek-all'); if (all) { all.checked = n === ekData.items.length; all.indeterminate = n > 0 && n < ekData.items.length; }
  }
  $('#view-einkauf').addEventListener('change', (e) => {
    if (e.target.id === 'ek-all') { ekSel = new Set(e.target.checked ? ekData.items.map((i) => i.code) : []); $$('#view-einkauf [data-eksel]').forEach((c) => { c.checked = e.target.checked; }); ekCount(); return; }
    const c = e.target.dataset.eksel;
    if (c) { if (e.target.checked) ekSel.add(c); else ekSel.delete(c); ekCount(); }
  });
  $('#view-einkauf').addEventListener('submit', async (e) => {
    if (e.target.id !== 'ek-form') return;
    e.preventDefault();
    const err = $('#ek-err'), btn = $('#ek-send');
    err.textContent = ''; btn.disabled = true;
    try {
      const r = await api('einkauf_melden', { body: { codes: [...ekSel], note: e.target.note.value } });
      const bad = r.results.filter((x) => !x.ok);
      toast(`Einkauf benachrichtigt (${r.results.filter((x) => x.ok).map((x) => x.to).join(', ')}).${bad.length ? ' Nicht zugestellt: ' + bad.map((x) => x.to).join(', ') : ''}`, 6000);
      ekSel = null;
      renderEinkaufView();
    } catch (ex) { err.textContent = ex.message; ekCount(); }
  });
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
          ${o.positions.map((p) => `<tr><td class="mono">${esc(p.code || '—')}</td><td>${esc(p.name)}</td><td class="r">${esc(qty(p.qty))}</td><td class="r">${p.price == null ? 'auf Anfrage' : esc(eur2.format(p.price)) + ' €'}</td><td class="r">${p.sum == null ? '–' : esc(fmtNum.format(p.sum)) + ' €'}</td></tr>`).join('')}
        </tbody><tfoot><tr><td class="ord-nr"></td><td><strong>${o.fracht && o.fracht.kosten ? 'Warenwert (ca.)' : 'Summe (ca.)'}</strong></td><td class="r">${esc(qty(o.totalQty || 0))}</td><td></td><td class="r"><strong>${esc(fmtNum.format(o.total))} €</strong></td></tr>${o.fracht && o.fracht.kosten ? `<tr class="ord-fr"><td class="ord-nr"></td><td colspan="3">Frachtanteil (unter ${esc(fmtInt.format(o.fracht.unter))} kg, automatisch aufgeschlagen)</td><td class="r">${esc(fmtNum.format(o.fracht.kosten))} €</td></tr><tr><td class="ord-nr"></td><td colspan="3"><strong>Gesamt (ca.)</strong></td><td class="r"><strong>${esc(fmtNum.format(o.total + o.fracht.kosten))} €</strong></td></tr>` : ''}</tfoot></table>
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
    if (!may('bestellungen.bearbeiten')) {   // nur ansehen
      for (const el of $$('#order-edit-form select, #order-edit-form input, #order-edit-form textarea')) el.disabled = true;
      for (const el of $$('#order-edit-form [type="submit"], #order-edit-form [data-order-mail]')) el.hidden = true;
    }
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
  let kunden = null, kundenRev = 0, kundenQ = '', kundenG = '', kundenV = '', mailSt = null;
  const MAIL_TYP = { woche: 'Wochenangebot', angebot: 'Angebotslink', invite: 'Einladung', reset: 'Passwort-Link', test: 'Testmail', hinweis: 'Hinweis Abmeldung', bestellung: 'Bestellwunsch', bestellkopie: 'Kopie Bestellwunsch', restposten: 'Sonderposten', benachrichtigung: 'Benachrichtigung', einkauf: 'Einkaufsbedarf', einzelangebot: 'Einzelangebot' };
  const dlgKunde = $('#dlg-kunde');
  let editKid = null;
  const offerChip = (id, perGruppe) => `<span class="k-chip${id === OSTD ? ' std' : ''}${perGruppe ? ' grp' : ''}"${perGruppe ? ` title="${id === OSTD ? 'automatisch: Kundengruppe ohne eigenes Angebot' : 'über die Kundengruppe freigeschaltet'}"` : ''}>${esc(offerShort(id))}</span>`;
  const K_MAX = 500;   // Zeilen in der Kundenliste (Suche/Filter grenzt ein)
  function kVertreterOpts() {
    const n = new Map(); let ohne = 0;
    for (const c of kunden) { const v = [...new Set([c.vertreter, c.vertreter2].filter(Boolean))]; if (!v.length) ohne++; for (const x of v) n.set(x, (n.get(x) || 0) + 1); }
    const vs = VT.groups() || [];
    return `<option value="">Alle Vertreter</option><option value="-"${kundenV === '-' ? ' selected' : ''}>Ohne Vertreter (${fmtInt.format(ohne)})</option>`
      + vs.filter((g) => n.has(g.nr) || kundenV === g.nr).map((g) => `<option value="${esc(g.nr)}"${kundenV === g.nr ? ' selected' : ''}>${esc(g.name)}${g.kurz && g.kurz !== g.name ? ` (${esc(g.kurz)})` : ''} · ${fmtInt.format(n.get(g.nr) || 0)}</option>`).join('')
      + [...n.keys()].filter((nr) => !vs.some((g) => g.nr === nr)).map((nr) => `<option value="${esc(nr)}"${kundenV === nr ? ' selected' : ''}>${esc(nr)} · nicht mehr vorhanden (${n.get(nr)})</option>`).join('');
  }
  function kGruppenOpts() {
    const n = new Map(); let ohne = 0;
    for (const c of kunden) { if (c.gruppe) n.set(c.gruppe, (n.get(c.gruppe) || 0) + 1); else ohne++; }
    const gs = KG.groups() || [];
    return `<option value="">Alle Kundengruppen</option><option value="-"${kundenG === '-' ? ' selected' : ''}>Ohne Kundengruppe (${fmtInt.format(ohne)})</option>`
      + gs.filter((g) => n.has(g.nr) || kundenG === g.nr).map((g) => `<option value="${esc(g.nr)}"${kundenG === g.nr ? ' selected' : ''}>${esc(g.nr)} · ${esc(g.name)} (${fmtInt.format(n.get(g.nr) || 0)})</option>`).join('')
      + [...n.keys()].filter((nr) => !gs.some((g) => g.nr === nr)).map((nr) => `<option value="${esc(nr)}"${kundenG === nr ? ' selected' : ''}>${esc(nr)} · nicht mehr vorhanden (${n.get(nr)})</option>`).join('');
  }
  async function renderKundenView() {
    const host = $('#view-kunden');
    if (!kunden) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Kunden werden geladen …</div>';
    try {
      const [r, m] = await Promise.all([api('kunden'), mailInfo(), W.offers.length ? null : loadOffers(), loadKGruppen().catch(() => null), VT.load().catch(() => null)]);
      kunden = r.customers; kundenRev = r.rev; mailSt = m;
    } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    host.innerHTML = `
      <div class="ed-toolbar">
        <div class="search">${icon('search')}<input id="k-q" type="search" autocomplete="off" placeholder="Kunden finden: Firma, Nummer, Ort, Ansprechpartner …" aria-label="Kunden suchen" value="${esc(kundenQ)}"></div>
        <label class="select k-gfilter"><span class="sr-only">Kundengruppe</span><select id="k-g" aria-label="Nach Kundengruppe filtern">${kGruppenOpts()}</select>${icon('chev', 'sm')}</label>
        <label class="select k-gfilter"><span class="sr-only">Vertreter</span><select id="k-v" aria-label="Nach Vertreter filtern">${kVertreterOpts()}</select>${icon('chev', 'sm')}</label>
        <span class="ed-hint" id="k-count"></span>
        ${may('kunden.bearbeiten') ? `<button type="button" class="btn" id="k-import" title="Kundenstammdaten-Export der Warenwirtschaft (CSV) einlesen">${icon('upload')}CSV importieren</button><input type="file" id="k-file" accept=".csv,text/csv,text/plain" hidden>` : ''}
        <button type="button" class="btn" id="k-mailcfg"${isAdmin() ? '' : ' hidden'} title="E-Mail-Versand: Einstellungen, Signatur, Testmail">${icon('mail')}E-Mail${mailSt.configured ? '' : ' <span class="k-warn">nicht eingerichtet</span>'}</button>
        ${may('wochenangebot.senden') ? `<button type="button" class="btn" id="k-rund">${icon('send')}Wochenangebot versenden</button>` : ''}
        ${may('kunden.bearbeiten') ? `<button type="button" class="btn primary" id="k-add">${icon('plus')}Kunde anlegen</button>` : ''}
      </div>
      <div id="k-list"></div>
      <p class="hint k-note">Kunden melden sich auf der Angebotsseite über „Kunden-Login“ an und sehen nur ihre freigeschalteten Angebote – direkt beim Kunden oder über seine Kundengruppe (Stammdaten → Angebote). ${W.stdPublic ? 'Das Wochenangebot ist derzeit zusätzlich öffentlich ohne Anmeldung sichtbar (umstellbar unter Stammdaten → Angebote).' : 'Das Wochenangebot ist derzeit nicht öffentlich – nur freigeschaltete Kunden sehen es.'}</p>`;
    renderKundenList();
  }
  function renderKundenList() {
    const toks = fold(kundenQ).split(/\s+/).filter(Boolean);
    const list = kunden.filter((c) => {
      if (kundenG && (kundenG === '-' ? c.gruppe : c.gruppe !== kundenG)) return false;
      if (kundenV && (kundenV === '-' ? (c.vertreter || c.vertreter2) : c.vertreter !== kundenV && c.vertreter2 !== kundenV)) return false;
      const hay = fold([c.nr, c.firma, c.ansprechpartner, c.ort, c.plz, c.email, c.login && c.login.username, c.gruppe ? kgName(c.gruppe) : '', vtName(c.vertreter), vtName(c.vertreter2)].join(' ')); return toks.every((t) => hay.includes(t));
    });
    $('#k-count').textContent = plural(list.length, 'Kunde', 'Kunden') + (list.length !== kunden.length ? ` von ${fmtInt.format(kunden.length)}` : '') + (list.length > K_MAX ? ` – die ersten ${fmtInt.format(K_MAX)} angezeigt, Suche oder Gruppe eingrenzen` : '');
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
    host.innerHTML = `<div class="gcard"><table class="etab utab ktab"><thead><tr><th>Firma / Ansprechpartner</th><th class="k-addr">Ort</th><th>Freigeschaltete Angebote</th><th class="u-st">Zugang</th><th class="u-last">Letzte Anmeldung</th><th class="u-act"><span class="sr-only">Aktion</span></th></tr></thead><tbody>${list.slice(0, K_MAX).map((c) => `
      <tr data-kid="${esc(c.id)}" tabindex="0" class="${c.active ? '' : 'inactive'}">
        <td class="u-name"><div class="nm">${esc(c.firma)}${c.nr ? ` <span class="muted">· ${esc(c.nr)}</span>` : ''}</div><div class="sub">${esc(c.ansprechpartner || '')}${c.email ? `${c.ansprechpartner ? ' · ' : ''}${esc(c.email)}` : ''}</div>${c.gruppe ? `<div class="sub k-gruppe" title="Kundengruppe">${icon('users', 'sm')}${esc(kgName(c.gruppe) || 'Gruppe ' + c.gruppe + ' (nicht mehr vorhanden)')}</div>` : ''}${c.vertreter || c.vertreter2 ? `<div class="sub k-gruppe k-vt" title="Vertreter">${icon('user', 'sm')}${[c.vertreter, c.vertreter2].filter(Boolean).map((nr) => esc(vtName(nr) || 'Vertreter ' + nr + ' (nicht mehr vorhanden)')).join(' · ')}</div>` : ''}</td>
        <td class="k-addr">${esc([c.plz, c.ort].filter(Boolean).join(' '))}</td>
        <td class="k-offers">${c.angebote.length ? c.angebote.map((o) => offerChip(o, !(c.angeboteDirekt || c.angebote).includes(o))).join(' ') : '<span class="muted">keines</span>'}${mailLine(c)}</td>
        <td class="u-st">${st(c)}${c.login ? `<div class="sub uname">${esc(c.login.username)}</div>` : ''}</td>
        <td class="u-last">${c.login && c.login.lastLogin ? esc(dateTime(c.login.lastLogin)) : '<span class="muted">noch nie</span>'}</td>
        <td class="u-act"><button type="button" class="btn sm" data-kedit="${esc(c.id)}">Bearbeiten</button></td>
      </tr>`).join('')}</tbody></table></div>`;
  }
  $('#view-kunden').addEventListener('input', (e) => { if (e.target.id === 'k-q') { kundenQ = e.target.value; renderKundenList(); } });
  $('#view-kunden').addEventListener('change', (e) => {
    if (e.target.id === 'k-g') { kundenG = e.target.value; renderKundenList(); return; }
    if (e.target.id === 'k-v') { kundenV = e.target.value; renderKundenList(); return; }
    if (e.target.id === 'k-file' && e.target.files[0]) { const f = e.target.files[0]; e.target.value = ''; kImportDatei(f); }
  });
  const dmyTs = (ts) => new Date(ts * 1000).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric' });
  const wkCur = () => (mailSt && mailSt.week) || null;
  const sentThisWeek = (c) => { const w = wkCur(); return !!(w && c.weekly && c.weekly.week === w.week && c.weekly.year === w.year); };
  function mailLine(c) {
    const parts = [];
    if (c.mailAngebot === false && c.abgemeldet) parts.push(`<span class="st-warn">vom Wochenangebot abgemeldet ${esc(dateTime(c.abgemeldet.t))}</span>`);
    else if (c.mailAngebot === false) parts.push('<span class="muted">kein Wochenangebot per <span class="nobr">E-Mail</span></span>');
    else if (sentThisWeek(c)) parts.push(`<span class="st-ok">${icon('check', 'sm')}KW ${c.weekly.week} gesendet ${esc(dateTime(c.weekly.t))}</span>`);
    if (c.mailLast && !c.mailLast.ok) parts.push(`<span class="st-err">${esc(MAIL_TYP[c.mailLast.typ] || 'E-Mail')} nicht zugestellt</span>`);
    return parts.length ? `<div class="sub k-mail">${parts.join(' · ')}</div>` : '';
  }
  $('#view-kunden').addEventListener('click', (e) => {
    if (e.target.closest('#k-add')) { openKunde(null); return; }
    if (e.target.closest('#k-import')) { $('#k-file').click(); return; }
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
    const has = (o) => (c ? (c.angeboteDirekt || c.angebote).includes(o) : false);
    const perGruppe = (o) => !!(c && (c.angeboteGruppe || []).includes(o));
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
          <label class="fld"><span>Kundengruppe</span><select name="gruppe"><option value="">– keine –</option>${(KG.groups() || []).map((g) => `<option value="${esc(g.nr)}"${c && c.gruppe === g.nr ? ' selected' : ''}>${esc(g.nr)} · ${esc(g.name)}</option>`).join('')}${c && c.gruppe && !(KG.groups() || []).some((g) => g.nr === c.gruppe) ? `<option value="${esc(c.gruppe)}" selected>${esc(c.gruppe)} (nicht mehr vorhanden)</option>` : ''}</select></label>
          ${['vertreter', 'vertreter2'].map((f, k) => `<label class="fld"><span>${k ? 'Vertreter 2' : 'Vertreter'}</span><select name="${f}"><option value="">– keiner –</option>${(VT.groups() || []).map((g) => `<option value="${esc(g.nr)}"${c && c[f] === g.nr ? ' selected' : ''}>${esc(g.name)}${g.kurz && g.kurz !== g.name ? ` (${esc(g.kurz)})` : ''} · ${esc(g.nr)}</option>`).join('')}${c && c[f] && !(VT.groups() || []).some((g) => g.nr === c[f]) ? `<option value="${esc(c[f])}" selected>${esc(c[f])} (nicht mehr vorhanden)</option>` : ''}</select></label>`).join('')}
          ${fld('ansprechpartner', 'Ansprechpartner', 120, ' placeholder="z. B. Frau Beispiel"', 'span2')}
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
          <div class="k-offers-pick">${[OSTD, ...W.offers.map((o) => o.id)].map((o) => `<label class="check"><input type="checkbox" name="angebot" value="${esc(o)}"${has(o) ? ' checked' : ''}> ${esc(offerName(o))}${o === OSTD && W.stdPublic ? ' <small class="muted">(ohnehin öffentlich)</small>' : ''}${perGruppe(o) ? ` <small class="k-viagr">${icon('users', 'sm')}${o === OSTD ? 'automatisch' : 'über Kundengruppe'}</small>` : ''}</label>`).join('')}</div>
          <p class="hint">Der Kunde sieht nach der Anmeldung diese Angebote und zusätzlich das Angebot seiner Kundengruppe (Stammdaten → Angebote); hat die Gruppe kein eigenes Angebot, automatisch das Wochenangebot. Ist mehr als eines freigeschaltet, kann er zwischen ihnen wechseln.</p>
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
            ${!l || !l.hasPassword ? `<div class="span2 k-pwwahl" role="radiogroup" aria-label="Passwort"><span class="k-pwlbl">Passwort</span><div class="k-pwmode">
              <label class="k-pwopt${mailOk ? '' : ' off'}"><input type="radio" name="pwmode" value="invite"${!pwMode ? ' checked' : ''}${mailOk ? '' : ' disabled'}><span class="k-pwic">${icon('mail')}</span><span class="k-pwtx"><strong>Einladung per E-Mail</strong><small>${mailOk ? 'Der Kunde bekommt einen Link (7 Tage gültig) und legt sein Passwort selbst fest.' : 'Erst möglich, wenn der E-Mail-Versand eingerichtet ist (Verwaltung → E-Mail).'}</small></span></label>
              <label class="k-pwopt"><input type="radio" name="pwmode" value="manual"${pwMode ? ' checked' : ''}><span class="k-pwic">${icon('key')}</span><span class="k-pwtx"><strong>Startpasswort vergeben</strong><small>Sie legen ein Passwort fest und geben es dem Kunden weiter; er ändert es bei der ersten Anmeldung.</small></span></label></div></div>` : ''}
            <div class="fld k-pwfld"${pwMode ? '' : ' hidden'}><span>${l && l.hasPassword ? 'Neues Passwort <small class="muted">(leer = unverändert)</small>' : 'Startpasswort'}</span>
              <div class="pw-row"><input name="password" type="text" autocomplete="new-password" minlength="10" maxlength="200" placeholder="mindestens 10 Zeichen"><button type="button" class="btn" data-kact="gen">Vorschlag</button></div></div>
            <label class="check span2 k-pwfld"${pwMode ? '' : ' hidden'}><input type="checkbox" name="mustChange" checked> Kunde muss das Passwort bei der ersten Anmeldung ändern</label>
            <label class="check span2"><input type="checkbox" name="loginActive"${!l || l.active ? ' checked' : ''}> Zugang aktiv</label>
            ${l && l.lockedUntil ? `<label class="check span2 st-err"><input type="checkbox" name="unlock" checked> Sperre nach Fehlversuchen aufheben (gesperrt bis ${esc(timeOnly(new Date(l.lockedUntil * 1000).toISOString()))} Uhr)</label>` : ''}
            ${l && l.geraete && l.geraete.length ? `<label class="check span2"><input type="checkbox" name="geraeteEntfernen"> Vertraute Geräte entfernen (${esc(geraeteText(l.geraete))})</label>` : ''}
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
    if (!may('kunden.bearbeiten')) {   // nur ansehen
      for (const el of $$('#kunde-body input, #kunde-body select, #kunde-body textarea')) el.disabled = true;
      for (const el of $$('#kunde-body [type="submit"], #kunde-body [data-kact]')) el.hidden = true;
    }
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
  // Eine Fehlermeldung zum vorigen Speichern gilt nach jeder Eingabe nicht mehr
  $('#kunde-body').addEventListener('input', () => { $('#kunde-err').textContent = ''; });
  $('#kunde-body').addEventListener('submit', async (e) => {
    e.preventDefault();
    const f = e.target, err = $('#kunde-err');
    err.textContent = '';
    const c = editKid ? kunden.find((x) => x.id === editKid) : null;
    const body = { id: editKid || '', rev: kundenRev, active: f.active.checked, mailAngebot: f.mailAngebot.checked, angebote: $$('#kunde-body [name="angebot"]:checked').map((x) => x.value) };
    const invite = !!(f.pwmode && [...f.querySelectorAll('[name="pwmode"]')].find((x) => x.checked && x.value === 'invite'));
    if (c && c.abgemeldet && c.mailAngebot === false && body.mailAngebot
      && !(await confirmBox('Wochenangebot wieder einschalten?', `„${esc(c.firma)}“ hat sich am ${esc(dateTime(c.abgemeldet.t))} selbst abgemeldet. Bitte nur wieder einschalten, wenn der Kunde ausdrücklich zugestimmt hat.`, 'Kunde hat zugestimmt'))) return;
    for (const k of ['firma', 'nr', 'gruppe', 'vertreter', 'vertreter2', 'ansprechpartner', 'strasse', 'plz', 'ort', 'land', 'email', 'telefon', 'notiz']) body[k] = f[k].value.trim();
    const pw = invite ? '' : f.password.value.trim();
    if (f.hasLogin.checked) {
      if (pw && pw.length < 10) { err.textContent = 'Das Passwort muss mindestens 10 Zeichen lang sein.'; return; }
      if (!invite && !(c && c.login && c.login.hasPassword) && !pw) { err.textContent = 'Bitte ein Startpasswort festlegen (z. B. über „Vorschlag“).'; f.password.focus(); return; }
      if (invite && !body.email) { err.textContent = 'Für die Einladung per E-Mail bitte die E-Mail-Adresse angeben.'; f.email.focus(); return; }
      body.login = { username: f.username.value.trim(), password: pw, mustChange: f.mustChange.checked, active: f.loginActive.checked, unlock: !!(f.unlock && f.unlock.checked), geraeteEntfernen: !!(f.geraeteEntfernen && f.geraeteEntfernen.checked), invite };
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

  /* ---------- Kundenstammdaten aus der Warenwirtschaft importieren (CSV) ----------
     Gelesen werden Nummer, Name1 (sonst Alpha), Strasse, PLZ, Ort, Land, Telefon, EMail und Gruppe; Umsätze, Kreditlimit,
     Konditionen, Vertreter usw. bleiben in der Warenwirtschaft. Abgleich und Prüfung macht der Server (kunden_import). */
  const dlgKI = $('#dlg-k-import');
  let kImp = null;
  const landName = (() => { let dn = null; try { dn = new Intl.DisplayNames(['de'], { type: 'region' }); } catch { /* alter Browser */ } return (c) => { const v = (c || '').trim(); if (!/^[A-Za-z]{2}$/.test(v) || !dn) return v; try { return dn.of(v.toUpperCase()) || v; } catch { return v; } }; })();
  function kAusCsv(buf) {
    const rows = csvZeilen(csvText(buf));
    if (!rows.length) throw new Error('Die Datei ist leer.');
    const kopf = rows[0].map((c) => fold(c).replace(/[^a-z0-9]/g, ''));
    const sp = (...n) => kopf.findIndex((k) => n.includes(k));
    const i = { nr: sp('nummer', 'kundennummer', 'kdnr'), alpha: sp('alpha', 'suchname', 'kurzname'), firma: sp('name1', 'firma', 'name'), strasse: sp('strasse'), plz: sp('plz'), ort: sp('ort'),
      land: sp('land'), telefon: sp('telefon', 'tel'), email: sp('email', 'mail'), gruppe: sp('gruppe', 'kundengruppe'), vertreter: sp('vertreter', 'vertreter1'), vertreter2: sp('vertreter2') };
    if (i.nr < 0 || (i.firma < 0 && i.alpha < 0)) throw new Error('Spalten „Nummer“ und „Name1“ nicht gefunden. Erwartet wird der Kundendaten-Export der Warenwirtschaft (Semikolon getrennt).');
    if (i.strasse < 0 && i.email < 0 && i.gruppe < 0) throw new Error('Das ist vermutlich der Vertreter-Export. Bitte unter Stammdaten → Vertreter importieren; hier wird der Kundendaten-Export erwartet.');
    if (kopf.includes('bezeichnung1') || kopf.includes('vgrp')) throw new Error('Das ist der Artikelstammdaten-Export. Bitte unter Stammdaten → Artikelstammdaten importieren.');
    const v = (r, k) => (i[k] >= 0 ? (r[i[k]] || '').trim().replace(/\s{2,}/g, ' ') : '');
    const out = [];
    for (const [n, r] of rows.slice(1).entries()) {
      const alpha = v(r, 'alpha');
      const mails = v(r, 'email').split(/[;,\s]+/).filter((m) => /^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$/.test(m));
      const x = { nr: v(r, 'nr'), firma: v(r, 'firma') || alpha.replace(/^\*\s*/, ''), strasse: v(r, 'strasse'), plz: v(r, 'plz'), ort: v(r, 'ort'), land: landName(v(r, 'land')),
        telefon: v(r, 'telefon'), email: mails[0] || (v(r, 'email') && !v(r, 'email').includes('@') ? '' : v(r, 'email')), gruppe: v(r, 'gruppe'), vertreter: v(r, 'vertreter'), vertreter2: v(r, 'vertreter2'), stern: alpha.startsWith('*') || v(r, 'firma').startsWith('*'),
        zeile: n + 2 };   // Zeile in der Datei (Kopfzeile = 1) – Anzeige in der Vorschau der Importzentrale
      if (!x.nr && !x.firma) continue;
      out.push(x);
    }
    if (!out.length) throw new Error('Keine Kunden in der Datei gefunden.');
    return out;
  }
  async function kImportDatei(file) {
    let rows;
    try { rows = kAusCsv(await file.arrayBuffer()); } catch (ex) { toast(ex.message, 8000); return; }
    kImp = { file, rows, ohneStern: true, anlegen: true, res: null };
    dlgKI.showModal();
    await kImportPruefen();
  }
  const kImpRows = () => kImp.rows.filter((r) => !(kImp.ohneStern && r.stern)).map(({ stern, zeile, ...r }) => r);
  async function kImportPruefen() {
    const body = $('#k-import-body');
    const stern = kImp.rows.filter((r) => r.stern).length;
    const head = `<div class="dlg-head"><div><h2 id="ki-title">Kunden importieren</h2><p>${esc(kImp.file.name)} · ${plural(kImp.rows.length, 'Zeile', 'Zeilen')}</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>`;
    const opts = `<div class="ki-opts">
        <label class="check"><input type="checkbox" data-ki="stern"${kImp.ohneStern ? ' checked' : ''}> Mit „*“ markierte Kunden überspringen <small class="muted">(${fmtInt.format(stern)} in der Datei – in der Warenwirtschaft als nicht mehr aktiv gekennzeichnet)</small></label>
        <label class="check"><input type="checkbox" data-ki="anlegen"${kImp.anlegen ? ' checked' : ''}> Neue Kunden anlegen <small class="muted">(aus: nur bestehende Kunden aktualisieren)</small></label></div>`;
    body.innerHTML = head + `<div class="dlg-body">${opts}<div class="loading"><div class="spinner"></div>Abgleich mit den vorhandenen Kunden …</div></div>`;
    try { kImp.res = await api('kunden_import', { body: { pruefen: true, rows: kImpRows(), anlegen: kImp.anlegen } }); }
    catch (ex) { body.innerHTML = head + `<div class="dlg-body">${opts}<div class="err-box">${esc(ex.message)}</div></div><div class="dlg-foot"><button type="button" class="btn" data-close>Schließen</button></div>`; return; }
    const r = kImp.res, s = r.stat;
    const nix = !s.neu && !s.aktualisiert;
    const gname = (nr) => kgName(nr) || '';
    const fremd = Object.entries(r.gruppenUnbekannt || {}), fremdV = Object.entries(r.vertreterUnbekannt || {});
    body.innerHTML = head + `<div class="dlg-body">${opts}
        <div class="cmp-stats"><div><span>Neu</span><strong id="ki-neu">${fmtInt.format(s.neu)}</strong></div><div><span>Aktualisiert</span><strong id="ki-akt">${fmtInt.format(s.aktualisiert)}</strong></div><div><span>Unverändert</span><strong id="ki-gleich">${fmtInt.format(s.unveraendert)}</strong></div></div>
        ${r.beispiele.neu.length ? `<h3 class="d-h"><span>Neu</span></h3><ul class="kg-prev">${r.beispiele.neu.map((x) => `<li><span class="muted">${esc(x.nr)}</span> ${esc(x.firma)}${x.ort ? ` <span class="muted">· ${esc(x.ort)}</span>` : ''}${x.gruppe ? ` <span class="muted">· ${esc(gname(x.gruppe) || 'Gruppe ' + x.gruppe)}</span>` : ''}</li>`).join('')}${s.neu > r.beispiele.neu.length ? `<li class="muted">… und ${fmtInt.format(s.neu - r.beispiele.neu.length)} weitere</li>` : ''}</ul>` : ''}
        ${r.beispiele.aktualisiert.length ? `<h3 class="d-h"><span>Aktualisiert</span></h3><ul class="kg-prev">${r.beispiele.aktualisiert.map((x) => `<li><span class="muted">${esc(x.nr)}</span> ${esc(x.firma)} <span class="muted">· ${esc(x.felder.join(', '))}</span></li>`).join('')}${s.aktualisiert > r.beispiele.aktualisiert.length ? `<li class="muted">… und ${fmtInt.format(s.aktualisiert - r.beispiele.aktualisiert.length)} weitere</li>` : ''}</ul>` : ''}
        <p class="hint">Abgleich über die Kundennummer (bei Kunden ohne Nummer über Firma und PLZ). Bei bestehenden Kunden werden Kundengruppe, Adresse, Land und Telefon übernommen; Firma und E-Mail nur, wenn sie noch leer sind. Zugang, Freischaltungen und Notizen bleiben unverändert. Neue Kunden bekommen keinen Zugang und kein Wochenangebot per E-Mail (dafür ist ihr Einverständnis nötig); ihre Angebote ergeben sich aus der Kundengruppe. Umsätze, Kreditlimit, Konditionen und Vertreter werden nicht übernommen.</p>
        ${fremd.length ? `<p class="hint st-warn">Kundengruppe nicht in der Liste (Stammdaten → Kundengruppen), Gruppe bleibt leer: ${esc(fremd.map(([nr, n]) => `${nr} (${n})`).join(', '))}</p>` : ''}
        ${fremdV.length ? `<p class="hint st-warn">Vertreter nicht in der Liste (Stammdaten → Vertreter), Feld bleibt leer: ${esc(fremdV.map(([nr, n]) => `${nr} (${n})`).join(', '))}</p>` : ''}
        ${s.ohneFirma || s.doppelt || s.mailUngueltig || s.nichtAngelegt ? `<p class="hint" id="ki-skip">${[s.ohneFirma ? `${fmtInt.format(s.ohneFirma)} ohne Firma übersprungen` : '', s.doppelt ? `${s.doppelt}× doppelte Kundennummer übersprungen` : '', s.mailUngueltig ? `${s.mailUngueltig}× ungültige E-Mail-Adresse leer gelassen` : '', s.nichtAngelegt ? `${fmtInt.format(s.nichtAngelegt)} neue Kunden nicht angelegt` : ''].filter(Boolean).join(' · ')}</p>` : ''}
        ${nix ? '<p class="hint">Keine Änderungen – die Kundendaten sind bereits aktuell.</p>' : ''}
        <p class="kerr" id="ki-err" role="alert"></p></div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="button" class="btn primary" data-ki="ok"${nix ? ' disabled' : ''}>${icon('check')}Übernehmen</button></div>`;
  }
  $('#k-import-body').addEventListener('change', (e) => {
    const a = e.target.dataset.ki;
    if (a === 'stern') { kImp.ohneStern = e.target.checked; kImportPruefen(); }
    if (a === 'anlegen') { kImp.anlegen = e.target.checked; kImportPruefen(); }
  });
  $('#k-import-body').addEventListener('click', async (e) => {
    if (e.target.closest('[data-close]')) { dlgKI.close(); return; }
    const b = e.target.closest('[data-ki="ok"]');
    if (!b) return;
    b.disabled = true;
    try {
      const r = await api('kunden_import', { body: { rev: kImp.res.rev, rows: kImpRows(), anlegen: kImp.anlegen, quelle: kImp.file.name } });
      dlgKI.close();
      toast(`Kunden übernommen: ${fmtInt.format(r.stat.neu)} neu, ${fmtInt.format(r.stat.aktualisiert)} aktualisiert.`, 5000);
      kunden = null; renderKundenView();
    } catch (ex) { $('#ki-err').textContent = ex.message; b.disabled = false; if (ex.status === 409) kImportPruefen(); }
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
      ${m.testumgebung ? '<div class="gcard sec-form" id="ml-testpost"><h3 class="sec-h">Testpostfach</h3><p class="hint">Testumgebung: Es werden keine E-Mails versendet. Alles, was sonst verschickt würde (Wochenangebot, Sonderposten, Bestellwünsche, Einladungen …), landet hier.</p><div id="ml-tp-list"><div class="loading"><div class="spinner"></div>wird geladen …</div></div><iframe id="ml-tp-prev" sandbox="" title="Vorschau der E-Mail" hidden></iframe></div>' : ''}
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
          <p class="span2 ml-oto">Bestellwünsche gehen an: <strong>${m.orders.to.length ? esc(m.orders.to.join(', ')) : 'noch keine Adresse'}</strong> <span class="sub">– einstellbar unten unter „Benachrichtigungen“.</span></p>
          <label class="check span2"><input type="checkbox" name="copy"${m.orders.copy ? ' checked' : ''}> Kunde erhält eine Eingangsbestätigung mit allen Positionen an seine E-Mail-Adresse</label>
        </div>
        ${m.orders.enabled && !m.configured ? '<p class="st-warn ml-ohint">Aktiv wird die Bestellfunktion erst, wenn oben das Postfach für den Versand eingerichtet ist.</p>' : ''}
        <p class="form-err" id="ml-oerr" role="alert"></p>
        <div class="sec-foot"><button type="submit" class="btn">${icon('check', 'sm')}Speichern</button></div>
      </form>
      ${frachtCard(m)}
      ${notifyCard(m)}
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
    if (m.testumgebung) renderTestpost();
  }
  /* Fracht: frachtfrei ab … kg, Frachtanteil je Staffel; daraus entsteht der Hinweis unter dem Angebot (Bildschirm und Druck) */
  const frRow = (st) => `<div class="fr-row"><label class="fld"><span>Unter</span><span class="fr-in"><input name="fr-unter" type="number" min="1" max="100000" step="1" inputmode="numeric" value="${st ? esc(st.unter) : ''}" aria-label="Gewichtsgrenze in kg"> kg</span></label>
      <label class="fld"><span>Frachtanteil</span><span class="fr-in"><input name="fr-kosten" type="number" min="0" max="10000" step="0.01" inputmode="decimal" value="${st ? esc(st.kosten) : ''}" aria-label="Frachtanteil in Euro"> € pro Sendung</span></label>
      <button type="button" class="btn icon ghost" data-fr="rm" aria-label="Staffel entfernen">${icon('trash', 'sm')}</button></div>`;
  function frachtCard(m) {
    const f = m.fracht;
    if (!f) return '';
    return `<form class="gcard sec-form" id="ml-fracht" autocomplete="off">
        <h3 class="sec-h">Fracht und Hinweis im Angebot</h3>
        <p class="hint">Liegt ein Bestellwunsch unter der Gewichtsgrenze, wird der Frachtanteil automatisch aufgeschlagen und der Kunde sieht vor dem Absenden einen Hinweis. Die größte Grenze ist die Mindestmenge für frachtfreie Lieferung.</p>
        <label class="check"><input type="checkbox" name="aktiv"${f.aktiv ? ' checked' : ''}> Frachtregel anwenden</label>
        <div class="fr-list" id="fr-list">${(f.staffeln.length ? f.staffeln : [null]).map(frRow).join('')}</div>
        <button type="button" class="btn sm" data-fr="add">${icon('plus', 'sm')}Staffel hinzufügen</button>
        <label class="fld fr-zus"><span>Zusatz im Hinweis <small>(z. B. Telefonnummern, je Zeile)</small></span><textarea name="zusatz" rows="3" maxlength="600">${esc(f.zusatz)}</textarea></label>
        <div class="fr-prev"><span class="sub">So steht der Hinweis unter dem Angebot und im Druck:</span><div class="al-note">${(m.frachtHinweis || []).map((l, i) => `<p${i === 0 ? ' class="lead"' : ''}>${esc(l)}</p>`).join('')}</div></div>
        <p class="form-err" id="ml-frerr" role="alert"></p>
        <div class="sec-foot"><span class="sub">${f.updatedAt ? `Geändert ${esc(dateTime(f.updatedAt))}${f.updatedBy ? ' von ' + esc(f.updatedBy) : ''}` : 'Voreinstellung – noch nicht gespeichert'}</span><button type="submit" class="btn">${icon('check', 'sm')}Speichern</button></div>
      </form>`;
  }
  /* Benachrichtigungen an Mitarbeiter: je Ereignis an/aus und Empfänger */
  function notifyCard(m) {
    const n = m.notify;
    if (!n) return '';
    return `<form class="gcard sec-form" id="ml-notify" autocomplete="off">
        <h3 class="sec-h">Benachrichtigungen</h3>
        <p class="hint">Wer bekommt bei welchem Ereignis eine E-Mail? Je Ereignis höchstens ${n.max} Adressen, mit Komma getrennt.</p>
        <div class="nt-list">${n.events.map((e) => `<div class="nt-row" data-ev="${esc(e.key)}">
          <div class="nt-what">
            ${e.manuell ? '<span class="nt-fix on" title="Versand auf Knopfdruck">Knopf</span>' : e.fest ? `<span class="nt-fix${e.on ? ' on' : ''}">${e.on ? 'an' : 'aus'}</span>` : `<label class="nt-sw"><input type="checkbox" name="on-${esc(e.key)}"${e.on ? ' checked' : ''} aria-label="${esc(e.label)} an"><span>${e.on ? 'an' : 'aus'}</span></label>`}
            <div><strong>${esc(e.label)}</strong><small>${esc(e.text)}${e.fest ? ' An, solange die Bestellfunktion oben eingeschaltet ist.' : ''}</small></div>
          </div>
          <label class="fld nt-to"><span>Empfänger</span><input name="to-${esc(e.key)}" value="${esc(e.to.join(', '))}" maxlength="500" autocapitalize="none" spellcheck="false" placeholder="${e.ersatz !== null ? (e.ersatz ? 'leer = ' + esc(e.ersatz) + ' (Antwortadresse)' : 'leer = Antwortadresse des Postfachs') : 'z. B. it@standard-fleisch.de'}"></label>
          <button type="button" class="btn sm" data-ml="ntest" data-ev="${esc(e.key)}"${m.configured && (e.to.length || e.ersatz) ? '' : ' disabled'} title="${m.configured ? (e.to.length || e.ersatz ? 'Test-E-Mail an die gespeicherten Empfänger' : 'Erst Empfänger speichern') : 'Erst das Postfach einrichten'}">${icon('send', 'sm')}Test</button>
        </div>`).join('')}</div>
        <p class="form-err" id="ml-nerr" role="alert"></p>
        <div class="sec-foot"><span class="sub">${n.updatedAt ? `Geändert ${esc(dateTime(n.updatedAt))}${n.updatedBy ? ' von ' + esc(n.updatedBy) : ''}` : ''}</span><button type="submit" class="btn">${icon('check', 'sm')}Speichern</button></div>
      </form>`;
  }
  async function renderTestpost() {
    const host = $('#ml-tp-list');
    if (!host) return;
    try {
      const r = await api('testpostfach');
      host.innerHTML = r.mails.length ? `<div class="ml-logwrap"><table class="ctab"><thead><tr><th>Zeit</th><th>An</th><th>Betreff</th></tr></thead><tbody>${r.mails.map((x, i) => `<tr data-tp="${i}" tabindex="0" style="cursor:pointer"><td>${esc(dateTime(x.t))}</td><td>${esc(x.to)}</td><td>${esc(x.subject)}</td></tr>`).join('')}</tbody></table></div>` : '<p class="sec-empty">Noch keine E-Mails im Testpostfach.</p>';
    } catch (ex) { host.innerHTML = `<div class="err-box">${esc(ex.message)}</div>`; }
  }
  $('#view-mail').addEventListener('click', async (e) => {
    const tr = e.target.closest('tr[data-tp]');
    if (!tr) return;
    try {
      const r = await api('testpostfach', { query: '&i=' + encodeURIComponent(tr.dataset.tp) });
      const f = $('#ml-tp-prev'); f.hidden = false; f.srcdoc = r.mail.html || `<pre>${esc(r.mail.text)}</pre>`; f.scrollIntoView({ block: 'nearest' });
    } catch (ex) { toast(ex.message); }
  });
  $('#view-mail').addEventListener('change', (e) => {
    if (e.target.name && e.target.name.startsWith('on-')) { const s = e.target.nextElementSibling; if (s) s.textContent = e.target.checked ? 'an' : 'aus'; }
    if (e.target.name === 'secure') { const p = $('#ml-form [name="port"]'); if (['465', '587', ''].includes(p.value)) p.value = e.target.value === 'ssl' ? 465 : 587; }
  });
  $('#view-mail').addEventListener('click', (e) => {
    const a = e.target.closest('[data-fr]')?.dataset.fr;
    if (a === 'add') { if ($$('#fr-list .fr-row').length < 5) $('#fr-list').insertAdjacentHTML('beforeend', frRow(null)); }
    else if (a === 'rm') e.target.closest('.fr-row').remove();
  });
  $('#view-mail').addEventListener('submit', async (e) => {
    if (e.target.id === 'ml-fracht') {
      e.preventDefault();
      const f = e.target, err = $('#ml-frerr'), btn = f.querySelector('[type="submit"]');
      err.textContent = ''; btn.disabled = true;
      const staffeln = $$('#fr-list .fr-row').map((r) => ({ unter: r.querySelector('[name="fr-unter"]').value, kosten: r.querySelector('[name="fr-kosten"]').value.replace(',', '.') })).filter((x) => x.unter !== '' || x.kosten !== '');
      try {
        const r = await api('fracht_save', { body: { aktiv: f.aktiv.checked, staffeln, zusatz: f.zusatz.value } });
        mailSt.fracht = r.fracht; mailSt.frachtHinweis = r.hinweis;
        toast('Fracht und Hinweis gespeichert. Gilt ab sofort für neue Bestellwünsche und das Angebot.', 5000);
        renderMailView();
      } catch (ex) { err.textContent = ex.message; } finally { btn.disabled = false; }
      return;
    }
    if (e.target.id === 'ml-orders') {
      e.preventDefault();
      const f = e.target, err = $('#ml-oerr'), btn = f.querySelector('[type="submit"]');
      err.textContent = ''; btn.disabled = true;
      try {
        const r = await api('bestell_settings_save', { body: { enabled: f.enabled.checked, copy: f.copy.checked } });
        mailSt.orders = r.orders;
        toast(r.orders.enabled ? (r.active ? 'Gespeichert – Kunden können jetzt Bestellwünsche senden.' : 'Gespeichert – aktiv, sobald das Postfach eingerichtet ist.') : 'Gespeichert – Bestellfunktion ist ausgeschaltet.', 5000);
        renderMailView();
      } catch (ex) { err.textContent = ex.message; } finally { btn.disabled = false; }
      return;
    }
    if (e.target.id === 'ml-notify') {
      e.preventDefault();
      const f = e.target, err = $('#ml-nerr'), btn = f.querySelector('[type="submit"]');
      err.textContent = ''; btn.disabled = true;
      const events = {};
      mailSt.notify.events.forEach((x) => { events[x.key] = { to: f.elements['to-' + x.key].value, on: x.fest || x.manuell ? x.on : f.elements['on-' + x.key].checked }; });
      try {
        const r = await api('benachrichtigung_save', { body: { events } });
        mailSt.notify = r.notify; mailSt.orders = r.orders;
        toast('Benachrichtigungen gespeichert.');
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
    if (a === 'ntest') {
      const err = $('#ml-nerr'); err.textContent = ''; b.disabled = true;
      try {
        const r = await api('benachrichtigung_test', { body: { event: b.dataset.ev } });
        const bad = r.results.filter((x) => !x.ok);
        if (bad.length) err.textContent = 'Nicht zugestellt: ' + bad.map((x) => `${x.to} (${x.error})`).join(', ');
        else toast(`Test-Benachrichtigung an ${r.results.map((x) => x.to).join(', ')} gesendet.`, 5000);
      } catch (ex) { err.textContent = ex.message; } finally { b.disabled = false; }
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
    try { const [m, k] = await Promise.all([mailInfo(), api('kunden')]); mailSt = m; kunden = k.customers; kundenRev = k.rev; } catch (ex) { toast(ex.message); return; }
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
    ['user', 'Mitarbeiter'],
    ['kunden', 'Kunden (Stammdaten, Anmeldungen, E-Mails, Bestellwünsche)'],
    ['security', 'Sicherheit'],
  ];
  const typeOf = (a) => ({ draft: 'offer', import: 'offer', discard: 'offer', offers: 'offer', publish: 'publish', history: 'history', stock: 'stock', einkauf: 'stock', master: 'master', login: 'auth', logout: 'auth', login_fail: 'auth', password: 'auth', setup: 'user', user: 'user', security: 'security', wartung: 'security', twofa: 'auth', reauth: 'auth', reauth_fail: 'auth', customers: 'kunden', kunde_login: 'kunden', kunde_login_fail: 'kunden', kunde_password: 'kunden', mail: 'kunden', kunde_abmeldung: 'kunden', bestellung: 'kunden', einzelangebot: 'kunden' }[a] || '');
  const ACTION_LABEL = { einkauf: 'Einkauf', wartung: 'Wartungsmodus', bestellung: 'Bestellwunsch', kunde_abmeldung: 'Abmeldung Wochenangebot', mail: 'E-Mail', customers: 'Kunden', kunde_login: 'Kunden-Anmeldung', kunde_login_fail: 'Kunden-Anmeldung fehlgeschlagen', kunde_password: 'Kunden-Passwort', offers: 'Angebote', draft: 'Entwurf bearbeitet', import: 'Entwurf ersetzt', discard: 'Entwurf verworfen', publish: 'Veröffentlicht', history: 'Preisverlauf', stock: 'Bestand', master: 'Stammdaten', login: 'Anmeldung', logout: 'Abmeldung', login_fail: 'Anmeldung fehlgeschlagen', password: 'Passwort', setup: 'Einrichtung', user: 'Mitarbeiter', security: 'Sicherheit', twofa: 'Zwei-Faktor', reauth: 'Verwaltungsaktion bestätigt', reauth_fail: 'Passwortbestätigung fehlgeschlagen', protokoll_aufbewahrung: 'Aufbewahrung' };
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
        <label class="select" title="Aufbewahrung: laufender Monat und die ${esc(String(logData.aufbewahrung || 6))} Monate davor – ältere Monate werden automatisch gelöscht"><span class="sr-only">Monat</span><select id="log-month">${months.map((m) => `<option value="${m}"${m === logMonth ? ' selected' : ''}>${esc(monthLabel(m))}</option>`).join('')}</select>${icon('chev', 'sm')}</label>
        <label class="select"><span class="sr-only">Mitarbeiter</span><select id="log-user"><option value="">Alle Mitarbeiter</option>${names.map(([u, n]) => `<option value="${esc(u)}"${u === logUser ? ' selected' : ''}>${esc(n)} (${esc(u)})</option>`).join('')}</select>${icon('chev', 'sm')}</label>
        <label class="select"><span class="sr-only">Vorgang</span><select id="log-type">${LOG_TYPES.map(([v, l]) => `<option value="${v}"${v === logType ? ' selected' : ''}>${esc(l)}</option>`).join('')}</select>${icon('chev', 'sm')}</label>
        <span class="ed-hint" id="log-count"></span>
        <button type="button" class="btn" id="log-csv">${icon('download')}CSV</button>
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
    $('#log-count').textContent = plural(list.length, 'Eintrag', 'Einträge') + (list.some((e) => e.masked) ? ' · Kundendaten nur mit Recht „Kunden ansehen“' : '');
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
    host.innerHTML = `<div class="gcard"><table class="etab ltab"><thead><tr><th class="l-time">Zeit</th><th class="l-user">Mitarbeiter</th><th>Vorgang</th><th class="l-more"><span class="sr-only">Details</span></th></tr></thead><tbody>${rows.join('')}</tbody></table></div>`;
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

  W.openRund = openRund;

  /* ======================= Stammdaten → Gruppenlisten (Kundengruppen, VK-Gruppen) ======================= */
  /* Liste aus der Warenwirtschaft (Nummer, Bezeichnung, Klasse, Kategorie). CSV-Import im Browser (Semikolon, Windows-1252
     oder UTF-8), Vorschau mit neu/geändert/entfallen; gespeichert wird die ganze Liste. Kunden verweisen über „gruppe“ auf
     eine Kundengruppe, Artikel (Stammdaten) über „vkGruppe“ auf eine VK-Gruppe. */
  /* CSV lesen: UTF-8, sonst Windows-1252 (Export der Warenwirtschaft); Semikolon, Anführungszeichen */
  function csvZeilen(text) {
    const rows = []; let row = [], cell = '', q = false;
    for (let i = 0; i < text.length; i++) {
      const ch = text[i];
      if (q) { if (ch === '"') { if (text[i + 1] === '"') { cell += '"'; i++; } else q = false; } else cell += ch; continue; }
      if (ch === '"') q = true;
      else if (ch === ';') { row.push(cell); cell = ''; }
      else if (ch === '\n' || ch === '\r') { if (ch === '\r' && text[i + 1] === '\n') i++; row.push(cell); rows.push(row); row = []; cell = ''; }
      else cell += ch;
    }
    if (cell !== '' || row.length) { row.push(cell); rows.push(row); }
    return rows.filter((r) => r.some((c) => c.trim() !== ''));
  }
  function csvText(buf) {
    let text;
    try { text = new TextDecoder('utf-8', { fatal: true }).decode(buf); } catch { text = new TextDecoder('windows-1252').decode(buf); }
    return text.replace(/^﻿/, '');
  }
  W.csvZeilen = csvZeilen; W.csvText = csvText;

  /* Felder der Gruppenlisten (Kundengruppen, VK-Gruppen); Vertreter haben eigene Felder (cfg.felder) */
  const GRUPPEN_FELDER = [
    { k: 'name', label: 'Bezeichnung', max: 120, req: true, csv: ['bezeichnung', 'name'], span2: true },
    { k: 'klasse', label: 'Klasse', max: 20, csv: ['klasse'], cls: 'kg-k' },
    { k: 'kategorie', label: 'Kategorie', max: 20, csv: ['kategorie'], cls: 'kg-k' },
  ];
  function gruppenListe(cfg) {
    const { liste, p, eine, viele } = cfg;
    const F = cfg.felder || GRUPPEN_FELDER, FN = F.find((f) => f.k === 'name');
    const neuText = cfg.neuText || 'Gruppe anlegen', loeschText = cfg.loeschText || 'Gruppe löschen', andereText = cfg.andereText || 'eine andere Gruppe gewählt wird';
    const spaltenText = 'Nummer; ' + F.map((f) => f.label).join('; ');
    let groups = null, rev = 0, zahl = null, q = '', meta = null;
    const host = $(cfg.view), dlg = $(`#dlg-${p}ruppe`), dlgI = $(`#dlg-${p}-import`), body = $(`#${p}ruppe-body`), bodyI = $(`#${p}-import-body`);
    async function load() {
      const r = await api(liste);
      groups = r.groups; rev = r.rev; zahl = r[cfg.zaehler] || null; meta = { at: r.updatedAt, by: r.updatedBy };
      return groups;
    }
    const name = (nr) => { const g = (groups || []).find((x) => x.nr === nr); return g ? g.name : ''; };
    const anzahl = (nr) => (zahl ? zahl[nr] || 0 : 0);
    async function render() {
      if (!groups) host.innerHTML = `<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>${esc(viele)} werden geladen …</div>`;
      try { await load(); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
      const edit = may('stammdaten.bearbeiten');
      host.innerHTML = `
        <div class="ed-toolbar">
          <div class="search">${icon('search')}<input id="${p}-q" type="search" autocomplete="off" placeholder="${esc(eine)} finden: Nummer, ${esc(FN.label)} …" aria-label="${esc(viele)} suchen" value="${esc(q)}"></div>
          <span class="ed-hint" id="${p}-count"></span>
          ${edit ? `<button type="button" class="btn" id="${p}-import">${icon('upload')}CSV importieren</button><input type="file" id="${p}-file" accept=".csv,text/csv,text/plain" hidden>
          <button type="button" class="btn primary" id="${p}-add">${icon('plus')}${esc(neuText)}</button>` : ''}
        </div>
        <div id="${p}-list"></div>
        <p class="hint">${esc(cfg.hinweis)} ${meta && meta.at ? `Zuletzt geändert ${esc(dateTime(meta.at))}${meta.by ? ' von ' + esc(meta.by) : ''}.` : ''}</p>`;
      renderList();
    }
    function renderList() {
      const toks = fold(q).split(/\s+/).filter(Boolean);
      const list = groups.filter((g) => { const hay = fold([g.nr, ...F.map((f) => g[f.k])].join(' ')); return toks.every((t) => hay.includes(t)); });
      $(`#${p}-count`).textContent = plural(list.length, eine, viele) + (list.length !== groups.length ? ` von ${groups.length}` : '');
      const el = $(`#${p}-list`);
      if (!groups.length) { el.innerHTML = `<div class="ed-empty"><h3>Noch keine ${esc(viele)}</h3><p>${may('stammdaten.bearbeiten') ? `Importieren Sie die Liste als CSV aus der Warenwirtschaft (Spalten ${esc(cfg.csvText || spaltenText)}) oder legen Sie Einträge einzeln an.` : 'Ein Bearbeiter kann die Liste importieren.'}</p></div>`; return; }
      if (!list.length) { el.innerHTML = '<div class="ed-empty"><h3>Keine Treffer</h3><p>Suchbegriff anpassen.</p></div>'; return; }
      const edit = may('stammdaten.bearbeiten');
      el.innerHTML = `<div class="gcard"><table class="etab kgtab"><thead><tr><th class="kg-nr">Nummer</th>${F.filter((f) => !f.versteckt).map((f) => `<th${f.cls ? ` class="${f.cls}"` : ''}>${esc(f.label)}</th>`).join('')}${zahl ? `<th class="kg-n">${esc(cfg.zaehlerSpalte)}</th>` : ''}${edit ? '<th class="u-act"><span class="sr-only">Aktion</span></th>' : ''}</tr></thead><tbody>${list.map((g) => `
        <tr data-kg="${esc(g.nr)}"${edit ? ' tabindex="0"' : ''}><td class="kg-nr">${esc(g.nr)}</td>${F.filter((f) => !f.versteckt).map((f) => `<td${f.cls ? ` class="${f.cls}"` : ''}>${esc(g[f.k] || '')}</td>`).join('')}${zahl ? `<td class="kg-n">${zahl[g.nr] ? esc(String(zahl[g.nr])) : '<span class="muted">–</span>'}</td>` : ''}${edit ? `<td class="u-act"><button type="button" class="btn sm" data-kgedit="${esc(g.nr)}">Bearbeiten</button></td>` : ''}</tr>`).join('')}</tbody></table></div>`;
    }
    async function save(list, quelle) {
      const r = await api(liste + '_save', { body: { rev, groups: list, quelle: quelle || '' } });
      groups = r.groups; rev = r.rev;
      return r;
    }
    function open(nr) {
      const g = nr ? groups.find((x) => x.nr === nr) : null;
      const n = g ? anzahl(g.nr) : 0;
      body.innerHTML = `
        <div class="dlg-head"><div><h2 id="${p}-title">${g ? esc(g.name) : esc(eine) + ' anlegen'}</h2><p>${g ? `Nummer ${esc(g.nr)}${n ? ` · ${plural(n, cfg.zEine, cfg.zViele)} zugeordnet` : ''}` : 'Nummer wie in der Warenwirtschaft.'}</p></div>
          <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
        <div class="dlg-body"><div class="form-grid two">
          <label class="fld"><span>Nummer</span><input name="nr" value="${esc(g ? g.nr : '')}" maxlength="10" required${g ? ' readonly' : ''} inputmode="numeric"></label>
          ${F.map((f) => `<label class="fld${f.span2 ? ' span2' : ''}"><span>${esc(f.label)}</span><input name="${f.k}" value="${esc(g ? g[f.k] || '' : '')}" maxlength="${f.max}"${f.req ? ' required' : ' placeholder="optional"'}></label>`).join('')}
        </div><p class="kerr" id="${p}-err" role="alert"></p></div>
        <div class="dlg-foot"><span class="left">${g ? `<button type="button" class="btn sm ghost" data-kg-del style="color:var(--accent)">${icon('trash', 'sm')}${esc(loeschText)}</button>` : ''}</span><button type="button" class="btn" data-close>Abbrechen</button><button type="submit" class="btn primary">${icon('check')}Speichern</button></div>`;
      body.dataset.nr = nr || '';
      dlg.showModal();
      body.querySelector('[name="' + (g ? 'name' : 'nr') + '"]').focus();
    }
    body.addEventListener('submit', async (e) => {
      e.preventDefault();
      const f = e.target, nr = f.dataset.nr;
      const row = { nr: f.nr.value.trim() };
      for (const x of F) row[x.k] = f.elements[x.k].value.trim();
      if (!nr && groups.some((x) => x.nr === row.nr)) { $(`#${p}-err`).textContent = `Die Nummer ${row.nr} ist bereits vergeben.`; return; }
      const list = nr ? groups.map((x) => (x.nr === nr ? row : x)) : [...groups, row];
      try { await save(list); dlg.close(); toast(nr ? `${eine} „${row.name}“ gespeichert.` : `${eine} „${row.name}“ angelegt.`); render(); }
      catch (ex) { $(`#${p}-err`).textContent = ex.message; }
    });
    body.addEventListener('click', async (e) => {
      if (e.target.closest('[data-close]')) { dlg.close(); return; }
      if (!e.target.closest('[data-kg-del]')) return;
      const nr = body.dataset.nr, g = groups.find((x) => x.nr === nr);
      const n = anzahl(nr);
      if (!(await confirmBox(`${eine} löschen?`, `„${esc(g.name)}“ (${esc(nr)}) wird gelöscht.${n ? ` ${plural(n, cfg.zEine, cfg.zViele)} ${n === 1 ? 'behält' : 'behalten'} die Nummer, bis ${andereText}.` : ''}`, 'Löschen', true))) return;
      try { await save(groups.filter((x) => x.nr !== nr)); dlg.close(); toast(`${eine} „${g.name}“ gelöscht.`); render(); }
      catch (ex) { $(`#${p}-err`).textContent = ex.message; }
    });
    function ausCsv(buf) {
      const rows = csvZeilen(csvText(buf));
      if (!rows.length) throw new Error('Die Datei ist leer.');
      const kopf = rows[0].map((c) => fold(c).replace(/[^a-z]/g, ''));
      const sp = (...n) => kopf.findIndex((k) => n.includes(k));
      const kopfZ = rows[0].map((c) => fold(c).replace(/[^a-z0-9]/g, ''));
      const iNr = sp('nummer', 'nr', ...cfg.nrSpalten), idx = Object.fromEntries(F.map((f) => [f.k, kopfZ.findIndex((k) => f.csv.includes(k))]));
      if (kopf.includes('bezeichnung1') || kopf.includes('gtin') || kopfZ.includes('bezeichnung1')) throw new Error(`Das ist der Artikelstammdaten-Export. Bitte unter Stammdaten → Artikelstammdaten importieren; hier wird die Liste „${viele}“ erwartet.`);
      if (kopfZ.includes('rgempf') || (kopfZ.includes('vertreter') && kopfZ.includes('gruppe'))) throw new Error(`Das ist der Kundendaten-Export. Bitte unter Stammdaten → Kunden importieren; hier wird die Liste „${viele}“ erwartet.`);
      const fehlt = cfg.pruefeKopf ? cfg.pruefeKopf(kopfZ) : '';
      if (fehlt) throw new Error(fehlt);
      if (iNr < 0 || idx.name < 0) throw new Error(`Spalten „Nummer“ und „${FN.label}“ nicht gefunden. Erwartet wird die Liste „${viele}“ aus der Warenwirtschaft (${cfg.csvText || spaltenText}).`);
      const out = [], fehler = [], fehlerZeilen = [], zeileVon = new Map();
      rows.slice(1).forEach((r, i) => {
        const g = { nr: (r[iNr] || '').trim() };
        for (const f of F) g[f.k] = idx[f.k] >= 0 ? (r[idx[f.k]] || '').trim().replace(/\s{2,}/g, ' ') : '';
        if (!g.nr && !g.name) return;
        if (!/^[0-9A-Za-z._-]{1,10}$/.test(g.nr) || !g.name) { fehler.push(`Zeile ${i + 2}`); fehlerZeilen.push({ zeile: i + 2, schluessel: g.nr, text: `Nummer oder ${FN.label} fehlt/ungültig – übersprungen` }); return; }
        zeileVon.set(g, i + 2);
        out.push(g);
      });
      const doppelt = out.filter((g, i) => out.findIndex((x) => x.nr === g.nr) !== i).map((g) => g.nr);
      if (doppelt.length) throw new Error(`Nummer doppelt in der Datei: ${[...new Set(doppelt)].join(', ')}`);
      if (!out.length) throw new Error(`Keine ${viele} in der Datei gefunden.`);
      return { groups: out, fehler, fehlerZeilen, zeileVon };
    }
    async function importDatei(file) {
      let res;
      try { res = ausCsv(await file.arrayBuffer()); } catch (ex) { toast(ex.message, 8000); return; }
      const alt = new Map(groups.map((g) => [g.nr, g]));
      const neu = res.groups.filter((g) => !alt.has(g.nr));
      const werte = (g) => JSON.stringify(F.map((f) => g[f.k] || ''));
      const geaendert = res.groups.filter((g) => alt.has(g.nr) && werte(g) !== werte(alt.get(g.nr)));
      const nrs = new Set(res.groups.map((g) => g.nr));
      const weg = groups.filter((g) => !nrs.has(g.nr));
      const wegMit = weg.filter((g) => anzahl(g.nr));
      const liste = (l) => l.slice(0, 8).map((g) => `<li><span class="muted">${esc(g.nr)}</span> ${esc(g.name)}</li>`).join('') + (l.length > 8 ? `<li class="muted">… und ${l.length - 8} weitere</li>` : '');
      const nix = !neu.length && !geaendert.length && !weg.length;
      bodyI.innerHTML = `
        <div class="dlg-head"><div><h2 id="${p}i-title">${esc(viele)} importieren</h2><p>${esc(file.name)} · ${plural(res.groups.length, eine, viele)}</p></div>
          <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
        <div class="dlg-body">
          <div class="cmp-stats"><div><span>Neu</span><strong id="${p}i-neu">${neu.length}</strong></div><div><span>Geändert</span><strong id="${p}i-geaendert">${geaendert.length}</strong></div><div><span>Entfallen</span><strong id="${p}i-weg">${weg.length}</strong></div></div>
          ${neu.length ? `<h3 class="d-h"><span>Neu</span></h3><ul class="kg-prev">${liste(neu)}</ul>` : ''}
          ${geaendert.length ? `<h3 class="d-h"><span>Geändert</span></h3><ul class="kg-prev">${liste(geaendert)}</ul>` : ''}
          ${weg.length ? `<h3 class="d-h"><span>Nicht mehr in der Datei – werden entfernt</span></h3><ul class="kg-prev">${liste(weg)}</ul>` : ''}
          ${wegMit.length ? `<p class="hint st-warn">${plural(wegMit.length, 'entfallender Eintrag hat', 'entfallende Einträge haben')} zugeordnete ${esc(cfg.zViele)}; diese behalten die Nummer, bis ${andereText}.</p>` : ''}
          ${res.fehler.length ? `<p class="hint st-warn">Übersprungen (Nummer oder ${esc(FN.label)} fehlt/ungültig): ${esc(res.fehler.slice(0, 10).join(', '))}${res.fehler.length > 10 ? ' …' : ''}</p>` : ''}
          ${nix ? '<p class="hint">Keine Änderungen – die Liste ist bereits aktuell.</p>' : ''}
          <p class="kerr" id="${p}i-err" role="alert"></p>
        </div>
        <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="button" class="btn primary" id="${p}i-ok"${nix ? ' disabled' : ''}>${icon('check')}Übernehmen</button></div>`;
      dlgI.showModal();
      $(`#${p}i-ok`).onclick = async () => {
        $(`#${p}i-ok`).disabled = true;
        try { const r = await save(res.groups, file.name); dlgI.close(); toast(`${viele} übernommen: ${r.neu} neu, ${r.geaendert} geändert, ${r.entfernt} entfernt.`, 5000); render(); }
        catch (ex) { $(`#${p}i-err`).textContent = ex.message; $(`#${p}i-ok`).disabled = false; }
      };
    }
    bodyI.addEventListener('click', (e) => { if (e.target.closest('[data-close]')) dlgI.close(); });
    host.addEventListener('input', (e) => { if (e.target.id === `${p}-q`) { q = e.target.value; renderList(); } });
    host.addEventListener('change', (e) => { if (e.target.id === `${p}-file` && e.target.files[0]) { const f = e.target.files[0]; e.target.value = ''; importDatei(f); } });
    host.addEventListener('click', (e) => {
      if (e.target.closest(`#${p}-import`)) { $(`#${p}-file`).click(); return; }
      if (e.target.closest(`#${p}-add`)) { open(null); return; }
      const tr = e.target.closest('tr[data-kg]');
      if (tr && may('stammdaten.bearbeiten')) open(tr.dataset.kg);
    });
    host.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr[data-kg]') && may('stammdaten.bearbeiten')) open(e.target.dataset.kg); });
    /* Leser für die Importzentrale: dieselbe CSV-Prüfung wie hier; Vergleich und Speichern macht der Server */
    const importLeser = {
      async lesen([file]) {
        const res = ausCsv(await file.arrayBuffer());
        return { daten: { groups: res.groups.map((g) => ({ ...g, zeile: res.zeileVon.get(g) })) }, zeilen: res.groups.length, fehler: res.fehlerZeilen, hinweise: [] };
      },
      nachher() { groups = null; },
    };
    return { load, render, name, groups: () => groups, importLeser };
  }
  const KG = gruppenListe({ liste: 'kundengruppen', p: 'kg', view: '#view-gruppen', eine: 'Kundengruppe', viele: 'Kundengruppen', nrSpalten: ['gruppe', 'kundengruppe'],
    zaehler: 'kunden', zaehlerSpalte: 'Kunden', zEine: 'Kunde', zViele: 'Kunden', hinweis: 'Kundengruppen ordnen Kunden zu (Kunde bearbeiten → Kundengruppe).' });
  const VG = gruppenListe({ liste: 'vkgruppen', p: 'vg', view: '#view-vkgruppen', eine: 'VK-Gruppe', viele: 'VK-Gruppen', nrSpalten: ['gruppe', 'vkgruppe', 'vgrp'],
    zaehler: 'artikel', zaehlerSpalte: 'Artikel', zEine: 'Artikel', zViele: 'Artikel', hinweis: 'VK-Gruppen ordnen Artikel zu (Stammdaten → Artikelstammdaten, Spalte VK-Gruppe; beim Import der Artikelstammdaten aus der Spalte „VGrp“).' });
  const VT = gruppenListe({ liste: 'vertreter', p: 'vt', view: '#view-vertreter', eine: 'Vertreter', viele: 'Vertreter', nrSpalten: ['vertreter', 'vertreternr'],
    felder: [
      { k: 'name', label: 'Name', max: 120, req: true, csv: ['name1', 'name'], span2: true },
      { k: 'kurz', label: 'Kurzname', max: 40, csv: ['alpha', 'kurzname', 'suchname'], cls: 'kg-k' },
      { k: 'telefon', label: 'Telefon', max: 40, csv: ['telefon', 'tel'], cls: 'kg-k' },
      { k: 'plz', label: 'PLZ', max: 10, csv: ['plz'], versteckt: true },
      { k: 'ort', label: 'Ort', max: 80, csv: ['ort'], cls: 'kg-k' },
      { k: 'land', label: 'Land', max: 60, csv: ['land'], versteckt: true },
    ],
    csvText: 'Nummer; Alpha; Name1; Land; PLZ; Ort; Telefon', neuText: 'Vertreter anlegen', loeschText: 'Vertreter löschen', andereText: 'ein anderer Vertreter gewählt wird',
    pruefeKopf: (k) => (k.includes('bezeichnung') && !k.includes('name1') ? 'Das ist eine Gruppenliste. Vertreter bitte mit dem Vertreter-Export der Warenwirtschaft (Nummer; Alpha; Name1 …) importieren.' : ''),
    zaehler: 'kunden', zaehlerSpalte: 'Kunden', zEine: 'Kunde', zViele: 'Kunden', hinweis: 'Vertreter werden den Kunden zugeordnet (Kunde bearbeiten → Vertreter und Vertreter 2; beim Kundenimport aus den Spalten „Vertreter“ und „Vertreter2“).' });
  const loadKGruppen = KG.load, kgName = KG.name;
  /* Leser der Verwaltung für die Importzentrale (admin-import.js, docs/plattform/schnittstellen/import.md) */
  Object.assign(W.importLeser, {
    kunden: {
      async lesen([file]) {
        const rows = kAusCsv(await file.arrayBuffer());
        return { daten: { rows }, zeilen: rows.length, fehler: [], hinweise: [] };   // „*“-Kunden: Option und Hinweis vom Server
      },
      nachher() { kunden = null; },
    },
    kundengruppen: KG.importLeser, vkgruppen: VG.importLeser, vertreter: VT.importLeser,
  });
  const vtName = (nr) => VT.name(nr);

  W.views = { users: renderUsersView, orders: renderOrdersView, einkauf: renderEinkaufView, kunden: renderKundenView, gruppen: KG.render, vkgruppen: VG.render, vertreter: VT.render, mail: renderMailView, log: renderLogView };
})();
