/* STAFL-Plattform · CRM · Einzelangebot beim Kunden (Kunden-Pop-up, Reiter „Angebote“; Auftrag des Inhabers 01.11.2026)
   Wie in der Angebotsübersicht des Eingabebereichs: Einzelangebote des Kunden ansehen, ein neues anlegen, Positionen über die
   Artikelsuche (Wochenpreis, Bestand) oder frei eintragen, speichern, im Portal freigeben bzw. die Freigabe beenden, als PDF
   ansehen, per E-Mail senden (Positionen als Liste oder PDF im Anhang; Bestätigung wie im Eingabebereich: Passwort bzw. erneute
   Anmeldung bei Keycloak) und löschen. Daten nur über die Aktionen crm_einzel_* (Rechte einzelangebote.* und crm.sehen prüft der
   Server; Daten und Regeln beim Angebot). Wird von crm.js aufgerufen (window.STAFL_CRM_EINZEL). */
'use strict';
(() => {
  const NF2 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const F = window.STAFL_FORMAT;   // Zahlen und Einheiten wie auf allen Seiten (app/assets/format.js)
  const NFKG = { format: (v) => F.zahl(v, 2, 2) };   // Menge in kg (Einheit steht daneben)
  const STATUS = { entwurf: ['Entwurf', 'info'], freigegeben: ['Im Portal', 'ok'], zurueckgezogen: ['Zurückgezogen', ''] };
  const MERK = 'crm.einzel.senden';   // nach der Bestätigung bei Keycloak: Versand fortsetzen (nur sessionStorage, keine Geheimnisse)
  const E = { key: '', host: null, c: null, daten: null, ed: null, fracht: [], dirty: false, artikel: null, treffer: [], verwerfen: false, loeschen: false, mail: false, pw: false, weiter: null };

  /* Zahl aus deutscher Eingabe („12,50“, „1.234,5“; bei Mengen auch „1.200“ = 1200) – wie im Eingabebereich */
  function zahl(v, art) {
    let t = String(v ?? '').trim().replace(/\s/g, '');
    if (t === '') return null;
    const tausend = t.includes(',') ? /^[1-9]\d{0,2}(\.\d{3})+,\d+$/.test(t) : art === 'qty' && /^[1-9]\d{0,2}(\.\d{3})+$/.test(t);
    t = tausend ? t.replace(/\./g, '').replace(',', '.') : t.replace(',', '.');
    const n = /^\d+(\.\d+)?$/.test(t) ? Number(t) : NaN;
    return Number.isFinite(n) ? n : NaN;
  }
  const text = (v) => (v == null || Number.isNaN(v) ? '' : String(Math.round(v * 100) / 100).replace('.', ','));
  const preisText = (v) => (v == null || Number.isNaN(v) ? '' : (Math.round(v * 100) / 100).toFixed(2).replace('.', ','));   // Preise immer mit zwei Stellen
  const euro = (v) => NF2.format(v) + ' €';
  const plus = (tage) => { const d = new Date(); d.setDate(d.getDate() + tage); return d.toLocaleDateString('sv-SE'); };
  const fold = (s) => String(s || '').toLocaleLowerCase('de').normalize('NFD').replace(/[̀-ͯ]/g, '');
  const kurz = (code) => { const s = String(code || '').trim(); return /^\d+$/.test(s) ? (s.replace(/^0+/, '') || '0') : s.toUpperCase(); };
  const darf = () => !!(E.daten && E.daten.bearbeiten);
  function statusPille(a) {
    const abgelaufen = a.gueltigBis && a.gueltigBis < E.c.heute();
    const [t, cls] = a.status === 'freigegeben' && abgelaufen ? ['Abgelaufen', 'warn'] : (STATUS[a.status] || [a.status, '']);
    return `<span class="crm-pille ${cls}">${E.c.esc(t)}</span>`;
  }
  /* Summe der Positionen mit Menge und Preis (wie der Server: Cent je kg × kg) */
  function summen(pos) {
    let kg = 0, sum = 0;
    for (const p of pos) { const q = zahl(p.qty, 'qty'), pr = zahl(p.price); if (q > 0) { kg += q; if (pr >= 0 && pr !== null) sum += Math.round(Math.round(pr * 100) * q) / 100; } }
    return { kg, sum };
  }

  /* ---------- Laden ---------- */
  async function liste() {
    const r = await E.c.api('crm_einzel_liste', null, '&key=' + encodeURIComponent(E.key));
    if (!E.host || !E.host.isConnected) return;
    if (r.status !== 200 || !r.data.ok) { E.host.innerHTML = `<p class="crm-fehler">${E.c.esc(E.c.fehlerText(r, 'Einzelangebote nicht geladen'))}</p>`; return; }
    E.daten = r.data;
    if (E.weiter && E.weiter.key === E.key) { const w = E.weiter; E.weiter = null; await oeffnen(w.id, w); return; }
    zeichnen();
  }
  async function oeffnen(id, weiter = null) {
    const r = await E.c.api('crm_einzel_detail', null, '&key=' + encodeURIComponent(E.key) + '&id=' + encodeURIComponent(id));
    if (r.status !== 200 || !r.data.ok) { E.c.toast(E.c.fehlerText(r, 'Einzelangebot nicht geladen'), true); return; }
    E.ed = r.data.angebot; E.fracht = r.data.fracht || []; E.dirty = false; E.verwerfen = false; E.loeschen = false; E.mail = !!weiter; E.pw = false;
    E.ed.positions = E.ed.positions.map((p) => ({ ...p, qty: text(p.qty), price: preisText(p.price) }));
    zeichnen();
    if (weiter) {
      const f = $('#ez-mail'); if (f) { f.note.value = weiter.note || ''; for (const x of f.querySelectorAll('[name="format"]')) x.checked = x.value === (weiter.format || 'liste'); }
      E.c.toast('Anmeldung bestätigt – jetzt erneut „Senden“ wählen.');
    }
  }
  async function artikelLaden() {
    if (E.artikel || !darf()) return;
    const r = await E.c.api('crm_einzel_artikel');
    if (r.status === 200 && r.data.ok) E.artikel = r.data.articles;
  }
  const $ = (s) => (E.host ? E.host.querySelector(s) : null);

  /* ---------- Zeichnen ---------- */
  function zeichnen() {
    if (!E.host || !E.daten) return;
    E.host.innerHTML = E.ed ? editor() : listeHtml();
    if (E.ed) suchTreffer();
  }
  function listeHtml() {
    const c = E.c, d = E.daten;
    const zeilen = d.liste.map((a) => `<li><button type="button" class="crm-ez-zeile" data-ez-oeffnen="${c.esc(a.id)}"><span class="was"><b>${c.esc(a.nr)}${a.titel ? ' · ' + c.esc(a.titel) : ''}</b>
      <small>${[a.gueltigBis ? 'gültig bis ' + c.de(a.gueltigBis) : 'ohne Ablauf', `${a.positionCount} ${a.positionCount === 1 ? 'Position' : 'Positionen'}`, a.summen.summe ? euro(a.summen.summe) : '',
        `geändert ${c.deZeit(a.changed)}${a.changedBy ? ' von ' + a.changedBy : ''}`].filter(Boolean).map(c.esc).join(' · ')}</small></span>${statusPille(a)}</button></li>`).join('');
    return `<div class="crm-ez-kopf"><div><h3>Einzelangebote</h3><p class="crm-klein">Angebot nur für diesen Kunden – im Kundenportal sichtbar nach der Freigabe${d.portal ? '' : '; der Kunde hat keinen Portalzugang, also per E-Mail oder PDF'}.</p></div>
        ${darf() ? `<button type="button" class="btn primary" data-ez="neu">${c.icon('plus')}Neues Einzelangebot</button>` : ''}</div>
      ${zeilen ? `<ul class="crm-ez-liste">${zeilen}</ul>` : '<p class="crm-leer">Noch keine Einzelangebote für diesen Kunden.</p>'}`;
  }
  function positionZeile(p, i) {
    const c = E.c, b = darf(), dis = b ? '' : ' disabled';
    const a = p.code && E.artikel ? E.artikel.find((x) => kurz(x.code) === kurz(p.code)) : null;
    const std = a && a.stdPrice && a.stdPrice.status === 'value' ? a.stdPrice.value : null;
    const pr = zahl(p.price);
    const abw = std && pr > 0 ? (pr - std) / std * 100 : null;
    const info = [p.code, std ? `Wochenpreis ${F.euroKg(std)}` : '', a && a.totalKg !== undefined ? `Bestand ${NFKG.format(a.totalKg)} kg` : ''].filter(Boolean).join(' · ');
    return `<tr data-pos="${i}"><td class="name"><input type="text" data-p="name" maxlength="200" value="${c.esc(p.name)}" aria-label="Bezeichnung"${dis}><small>${c.esc(info || 'freie Position')}</small></td>
      <td data-label="Menge kg"><input type="text" inputmode="decimal" data-p="qty" value="${c.esc(p.qty)}" aria-label="Menge in kg" placeholder="kg"${dis}></td>
      <td data-label="Preis €/kg"><input type="text" inputmode="decimal" data-p="price" value="${c.esc(p.price)}" aria-label="Preis in € je kg" placeholder="auf Anfrage"${dis}>${abw !== null && Math.abs(abw) >= 1 ? `<small class="crm-ck-d ${abw < 0 ? 'minus' : 'plus'}">${F.veraenderung(abw / 100)} zum Wochenpreis</small>` : ''}</td>
      <td data-label="Notiz"><input type="text" data-p="notiz" maxlength="200" value="${c.esc(p.notiz || '')}" aria-label="Notiz"${dis}></td>
      <td class="knopf">${b ? `<button type="button" class="crm-rund klein" data-ez-weg="${i}" aria-label="Position entfernen">${c.icon('x')}</button>` : ''}</td></tr>`;
  }
  function editor() {
    const c = E.c, ed = E.ed, b = darf(), dis = b ? '' : ' disabled', neu = !ed.id;
    const s = summen(ed.positions);
    const gesendet = (ed.gesendet || []).slice(-3).reverse();
    const kannSenden = !neu && !E.dirty && ed.positions.length && ed.status !== 'zurueckgezogen';
    return `<div class="crm-ez-kopf"><button type="button" class="btn" data-ez="liste">${E.verwerfen ? 'Änderungen verwerfen?' : '‹ Alle Einzelangebote'}</button>${neu ? '' : statusPille(ed)}</div>
      <div class="crm-ez-titel"><h3>${neu ? 'Neues Einzelangebot' : c.esc(ed.nr)}</h3><span class="crm-klein" id="ez-stand">${E.dirty ? 'nicht gespeichert' : neu ? '' : `gespeichert ${c.deZeit(ed.changed)}${ed.changedBy ? ' von ' + c.esc(ed.changedBy) : ''}`}</span></div>
      <div class="crm-felder crm-ez-felder">
        <label>Titel<input type="text" data-k="titel" maxlength="120" value="${c.esc(ed.titel || '')}" placeholder="z. B. Angebot KW 46"${dis}></label>
        <label>Gültig bis<input type="date" data-k="gueltigBis" value="${c.esc(ed.gueltigBis || '')}"${dis}></label>
        <label class="breit">Hinweis an den Kunden<textarea data-k="hinweis" maxlength="1000" placeholder="erscheint im Portal, in der E-Mail und im PDF"${dis}>${c.esc(ed.hinweis || '')}</textarea></label>
      </div>
      <div class="crm-tabelle-rahmen crm-ez-rahmen"><table class="crm-tabelle crm-ez-pos crm-ck-karten"><thead><tr><th>Artikel</th><th>Menge kg</th><th>Preis €/kg</th><th>Notiz</th><th></th></tr></thead>
        <tbody>${ed.positions.map(positionZeile).join('') || '<tr><td colspan="5" class="crm-leer">Noch keine Positionen – Artikel unten suchen oder eine freie Position anlegen.</td></tr>'}</tbody></table></div>
      ${b ? `<div class="crm-ez-suche"><label class="crm-suche"><span class="sr-only">Artikel suchen</span>${c.icon('search')}<input type="search" id="ez-suche" placeholder="Artikel hinzufügen: Nummer oder Bezeichnung …" autocomplete="off"></label>
        <button type="button" class="btn" data-ez="frei">${c.icon('plus')}Freie Position</button><div class="crm-ez-treffer" id="ez-treffer" role="listbox" aria-label="Artikel" hidden></div></div>` : ''}
      <p class="crm-ez-summe">${ed.positions.length} ${ed.positions.length === 1 ? 'Position' : 'Positionen'}${s.kg ? ` · ${NFKG.format(s.kg)} kg` : ''}${s.sum ? ` · <b>${euro(s.sum)}</b>` : ''}</p>
      ${E.fracht.length ? `<p class="crm-klein">${E.fracht.map(c.esc).join(' ')}</p>` : ''}
      <p class="crm-meldung" id="ez-meldung" role="status"></p>
      <div class="crm-knoepfe crm-ez-knoepfe">
        ${b ? `<button type="button" class="btn primary" data-ez="speichern">Speichern</button>` : ''}
        ${b && !neu ? (ed.status === 'freigegeben' ? '<button type="button" class="btn" data-ez-status="entwurf">Freigabe beenden</button>' : '<button type="button" class="btn" data-ez-status="freigegeben">Im Portal freigeben</button>') : ''}
        ${!neu ? `<a class="btn" href="../../api/?action=crm_einzel_pdf&key=${encodeURIComponent(E.key)}&id=${encodeURIComponent(ed.id)}" target="_blank" rel="noopener" data-ez-pdf>PDF ansehen</a>` : ''}
        ${b && !neu ? `<button type="button" class="btn" data-ez="mail"${kannSenden ? '' : ' disabled title="Erst speichern; braucht Positionen"'}>${c.icon('mail')}Per E-Mail senden</button>` : ''}
        <span class="crm-platz"></span>
        ${b && !neu ? `<button type="button" class="btn gefahr" data-ez="loeschen">${E.loeschen ? 'Wirklich löschen?' : 'Löschen'}</button>` : ''}
      </div>
      ${b && !neu && E.mail ? mailForm() : ''}
      ${gesendet.length ? `<p class="crm-klein crm-ez-gesendet">${gesendet.map((g) => `${g.ok ? 'Gesendet' : 'Nicht zugestellt'} ${c.esc(c.deZeit(g.t))} an ${c.esc(g.to)}${g.format === 'pdf' ? ' (PDF)' : ''} · ${c.esc(g.by)}`).join('<br>')}</p>` : ''}`;
  }
  function mailForm() {
    const c = E.c, an = E.daten.email;
    return `<form class="crm-ez-mail" id="ez-mail" novalidate><h4>Per E-Mail an ${an ? c.esc(an) : 'den Kunden'}</h4>
      ${an ? '' : '<p class="crm-meldung fehler">Für diesen Kunden ist keine E-Mail-Adresse hinterlegt (Verwaltung → Kunden).</p>'}
      <div class="crm-seg" role="radiogroup" aria-label="Format"><label><input type="radio" name="format" value="liste" checked> Positionen in der E-Mail</label><label><input type="radio" name="format" value="pdf"> PDF im Anhang</label></div>
      <label>Nachricht (optional)<textarea name="note" maxlength="1000" placeholder="z. B. Wie besprochen …"></textarea></label>
      ${E.pw ? '<label>Zur Bestätigung Ihr Passwort<input type="password" name="pw" autocomplete="current-password"></label>' : ''}
      <div class="crm-knoepfe"><button type="button" class="btn" data-ez="mail-ab">Abbrechen</button><button type="submit" class="btn primary" id="ez-senden"${an ? '' : ' disabled'}>Senden</button></div></form>`;
  }
  function meldung(t, art = 'fehler') { const m = $('#ez-meldung'); if (m) { m.textContent = t; m.className = 'crm-meldung ' + art; } }
  function geaendert() {
    E.dirty = true; E.verwerfen = false; E.loeschen = false;
    const s = $('#ez-stand'); if (s) s.textContent = 'nicht gespeichert';
    const sm = summen(E.ed.positions), z = $('.crm-ez-summe');
    if (z) z.innerHTML = `${E.ed.positions.length} ${E.ed.positions.length === 1 ? 'Position' : 'Positionen'}${sm.kg ? ` · ${NFKG.format(sm.kg)} kg` : ''}${sm.sum ? ` · <b>${euro(sm.sum)}</b>` : ''}`;
    const m = $('[data-ez="mail"]'); if (m) m.disabled = true;
  }

  /* ---------- Artikelsuche ---------- */
  function suchTreffer() {
    const box = $('#ez-treffer'), feld = $('#ez-suche');
    if (!box || !feld) return;
    const q = fold(feld.value.trim());
    if (q.length < 2 || !E.artikel) { box.hidden = true; box.innerHTML = ''; return; }
    E.treffer = E.artikel.filter((a) => fold(a.code + ' ' + a.name).includes(q)).slice(0, 8);
    box.innerHTML = E.treffer.length ? E.treffer.map((a, i) => `<button type="button" role="option" data-ez-treffer="${i}"><b>${E.c.esc(a.name || 'Artikel ' + a.code)}</b>
      <small>${[a.code, a.stdPrice && a.stdPrice.status === 'value' ? 'Wochenpreis ' + F.euroKg(a.stdPrice.value) : a.inOffer ? 'im Wochenangebot' : '', a.totalKg !== undefined ? `Bestand ${NFKG.format(a.totalKg)} kg` : ''].filter(Boolean).map(E.c.esc).join(' · ')}</small></button>`).join('')
      : '<p class="crm-leer">Kein Artikel gefunden.</p>';
    box.hidden = false;
  }
  function hinzufuegen(a) {
    const std = a && a.stdPrice && a.stdPrice.status === 'value' ? a.stdPrice.value : null;
    E.ed.positions.push(a ? { code: a.code, name: a.name || 'Artikel ' + a.code, qty: '', price: preisText(std), notiz: '' } : { code: '', name: '', qty: '', price: '', notiz: '' });
    geaendert(); zeichnen();
    const z = E.host.querySelector(`tr[data-pos="${E.ed.positions.length - 1}"] [data-p="${a ? 'qty' : 'name'}"]`); if (z) z.focus();
  }

  /* ---------- Speichern, Status, Löschen, E-Mail ---------- */
  async function speichern() {
    const ed = E.ed, pos = [];
    for (const p of ed.positions) {
      const qty = zahl(p.qty, 'qty'), price = zahl(p.price);
      if (!String(p.name || '').trim()) { meldung('Jede Position braucht eine Bezeichnung.'); return false; }
      if (Number.isNaN(qty)) { meldung(`Menge bei „${p.name}“ bitte als Zahl angeben (z. B. 25 oder 12,5).`); return false; }
      if (Number.isNaN(price)) { meldung(`Preis bei „${p.name}“ bitte als Zahl angeben (z. B. 12,50) oder leer lassen (auf Anfrage).`); return false; }
      pos.push({ code: p.code || '', name: String(p.name).trim(), qty, price, notiz: p.notiz || '' });
    }
    const r = await E.c.api('crm_einzel_save', { key: E.key, id: ed.id || '', revision: ed.revision, titel: ed.titel || '', gueltigBis: ed.gueltigBis || '', hinweis: ed.hinweis || '', positions: pos });
    if (r.status !== 200 || !r.data.ok) { meldung(E.c.fehlerText(r, 'Speichern fehlgeschlagen')); return false; }
    const neu = !ed.id;
    E.ed = { ...r.data.angebot, positions: r.data.angebot.positions.map((p) => ({ ...p, qty: text(p.qty), price: preisText(p.price) })) };
    E.dirty = false;
    E.c.toast(neu ? `Einzelangebot ${E.ed.nr} angelegt.` : 'Einzelangebot gespeichert.');
    await nachLaden();
    return true;
  }
  async function nachLaden() {
    const r = await E.c.api('crm_einzel_liste', null, '&key=' + encodeURIComponent(E.key));
    if (r.status === 200 && r.data.ok) E.daten = r.data;
    zeichnen();
  }
  async function status(s) {
    if (E.dirty && !(await speichern())) return;
    const r = await E.c.api('crm_einzel_status', { key: E.key, id: E.ed.id, revision: E.ed.revision, status: s });
    if (r.status !== 200 || !r.data.ok) { meldung(E.c.fehlerText(r, 'Status nicht geändert')); return; }
    E.ed = { ...r.data.angebot, positions: r.data.angebot.positions.map((p) => ({ ...p, qty: text(p.qty), price: preisText(p.price) })) };
    E.c.toast(s === 'freigegeben' ? (E.daten.portal ? 'Im Portal freigegeben – der Kunde sieht das Angebot nach der Anmeldung.' : 'Freigegeben – der Kunde hat aber keinen Portalzugang.') : 'Freigabe beendet.');
    await nachLaden();
  }
  async function loeschen() {
    if (!E.loeschen) { E.loeschen = true; zeichnen(); return; }
    const r = await E.c.api('crm_einzel_loeschen', { key: E.key, id: E.ed.id });
    if (r.status !== 200 || !r.data.ok) { meldung(E.c.fehlerText(r, 'Nicht gelöscht')); return; }
    E.c.toast(`Einzelangebot ${E.ed.nr} gelöscht.`);
    E.ed = null; E.dirty = false; E.loeschen = false;
    await nachLaden();
  }
  async function senden(f) {
    const body = { key: E.key, id: E.ed.id, format: (f.querySelector('[name="format"]:checked') || {}).value || 'liste', note: f.note.value };
    const knopf = $('#ez-senden'); if (knopf) knopf.disabled = true;
    if (E.pw && f.pw) {
      const pr = await E.c.api('reauth', { password: f.pw.value });
      if (pr.status !== 200) { if (knopf) knopf.disabled = false; meldung(E.c.fehlerText(pr, 'Passwort nicht bestätigt')); f.pw.value = ''; f.pw.focus(); return; }
    }
    const r = await E.c.api('crm_einzel_senden', body);
    if (r.status === 403 && r.data.code === 'reauth_required' && typeof r.data.anmelden === 'string' && r.data.anmelden.startsWith('/oidc/')) {
      try { sessionStorage.setItem(MERK, JSON.stringify({ key: E.key, id: E.ed.id, format: body.format, note: body.note })); } catch { /* ohne Speicher: erneut eingeben */ }
      location.assign(r.data.anmelden + encodeURIComponent(location.href));
      return;
    }
    if (r.status === 403 && r.data.code === 'confirmation_required') {
      E.pw = true; const note = body.note, fmt = body.format;
      zeichnen();
      const nf = $('#ez-mail'); nf.note.value = note; for (const x of nf.querySelectorAll('[name="format"]')) x.checked = x.value === fmt;
      meldung('Bitte bestätigen Sie den Versand mit Ihrem Passwort.', 'ok'); nf.pw.focus();
      return;
    }
    if (r.status !== 200 || !r.data.ok) { if (knopf) knopf.disabled = false; meldung(E.c.fehlerText(r, 'E-Mail nicht gesendet')); return; }
    E.ed = { ...r.data.angebot, positions: r.data.angebot.positions.map((p) => ({ ...p, qty: text(p.qty), price: preisText(p.price) })) };
    E.mail = false; E.pw = false;
    E.c.toast(`E-Mail an ${E.daten.email} gesendet.`);
    zeichnen();
  }

  /* ---------- Bedienung (nur innerhalb des Reiters) ---------- */
  document.addEventListener('input', (e) => {
    if (!E.host || !E.host.contains(e.target) || !E.ed) return;
    const t = e.target;
    if (t.id === 'ez-suche') { suchTreffer(); return; }
    if (t.dataset.k) { E.ed[t.dataset.k] = t.value; geaendert(); return; }
    const tr = t.closest('tr[data-pos]');
    if (tr && t.dataset.p) { E.ed.positions[+tr.dataset.pos][t.dataset.p] = t.value; geaendert(); }
  });
  document.addEventListener('keydown', (e) => {
    if (!E.host || e.target.id !== 'ez-suche') return;
    if (e.key === 'Enter') { e.preventDefault(); if (E.treffer.length) { hinzufuegen(E.treffer[0]); const f = $('#ez-suche'); if (f) f.value = ''; } }
    if (e.key === 'Escape') { e.preventDefault(); e.stopPropagation(); e.target.value = ''; suchTreffer(); }
  });
  document.addEventListener('click', async (e) => {
    if (!E.host || !E.host.contains(e.target)) return;
    const t = e.target;
    const o = t.closest('[data-ez-oeffnen]'); if (o) { await artikelLaden(); oeffnen(o.dataset.ezOeffnen); return; }
    const tr = t.closest('[data-ez-treffer]'); if (tr) { hinzufuegen(E.treffer[+tr.dataset.ezTreffer]); return; }
    const weg = t.closest('[data-ez-weg]'); if (weg) { E.ed.positions.splice(+weg.dataset.ezWeg, 1); geaendert(); zeichnen(); return; }
    const st = t.closest('[data-ez-status]'); if (st) { status(st.dataset.ezStatus); return; }
    const a = (t.closest('[data-ez]') || {}).dataset;
    if (!a || !a.ez) return;
    if (a.ez === 'neu') {
      await artikelLaden();
      E.ed = { id: '', revision: 0, titel: '', gueltigBis: plus(7), hinweis: '', positions: [], status: 'entwurf', gesendet: [] };
      E.fracht = []; E.dirty = false; E.mail = false; E.pw = false; zeichnen();
      const s = $('#ez-suche'); if (s) s.focus();
      return;
    }
    if (a.ez === 'liste') { if (E.dirty && !E.verwerfen) { E.verwerfen = true; zeichnen(); return; } E.ed = null; E.dirty = false; E.verwerfen = false; zeichnen(); return; }
    if (a.ez === 'frei') { hinzufuegen(null); return; }
    if (a.ez === 'speichern') { speichern(); return; }
    if (a.ez === 'loeschen') { loeschen(); return; }
    if (a.ez === 'mail') { E.mail = true; E.pw = false; zeichnen(); const f = $('#ez-mail textarea'); if (f) f.focus(); return; }
    if (a.ez === 'mail-ab') { E.mail = false; E.pw = false; zeichnen(); }
  });
  document.addEventListener('submit', (e) => { if (e.target.id === 'ez-mail') { e.preventDefault(); senden(e.target); } });

  window.STAFL_CRM_EINZEL = {
    /* Reiter zeichnen; beim Wechsel des Kunden beginnt alles neu, sonst bleibt der Stand (auch ungespeicherte Eingaben) */
    zeichne(host, key, c) {
      E.c = c;
      if (E.key !== key) Object.assign(E, { key, daten: null, ed: null, fracht: [], dirty: false, verwerfen: false, loeschen: false, mail: false, pw: false });
      E.host = host;
      if (E.daten) zeichnen(); else { host.innerHTML = '<p class="crm-leer">Einzelangebote werden geladen …</p>'; liste(); }
    },
    ungespeichert: () => !!(E.ed && E.dirty),
    verwerfen() { E.ed = null; E.dirty = false; },
    /* Nach der Bestätigung bei Keycloak: Kunde, dessen Einzelangebot versendet werden sollte (oder null) */
    fortsetzen() {
      let w = null;
      try { w = JSON.parse(sessionStorage.getItem(MERK) || 'null'); sessionStorage.removeItem(MERK); } catch { /* ohne Speicher */ }
      if (!w || typeof w.key !== 'string' || typeof w.id !== 'string') return null;
      E.weiter = w;
      return w.key;
    },
  };
})();
