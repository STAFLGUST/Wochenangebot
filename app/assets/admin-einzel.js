/* ==========================================================================
   Wochenangebot – Eingabebereich, Einzelangebote (Angebot je Kunde)
   Kunde über eine Suche wählen (Firma, Kundennummer, Ort, Ansprechpartner …). Artikel über das Fenster „Artikel
   hinzufügen“: links die VK-Gruppen (mit Anzahl), rechts die Artikel der gewählten Gruppe als Tabelle mit Häkchen,
   eingelagertem und erwartetem Bestand, kürzestem MHD und Wochenpreis; Details je Artikel (Partien, Ankünfte mit ETA).
   Die Suche oben findet jederzeit Artikel in allen Gruppen. Mehrere markierte Artikel auf einmal übernehmen.
   Abweichung des eigenen Preises vom Wochenpreis als farbiger Punkt.
   Drucken / PDF öffnet das Einzelangebot auf der Angebotsseite mit deren Druckdialog (wie für Kunden).
   E-Mail wahlweise mit den Positionen als Liste oder mit dem Angebot als PDF im Anhang (Design der Angebotsansicht).
   Server: app/api/aktionen/einzelangebote.php
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const { $, $$, api, esc, icon, toast, confirmBox, dateTime, plural, fold, may } = W;
  const host = $('#view-einzel');
  const dlgMail = $('#dlg-einzel-mail');
  const dlgPick = $('#dlg-ez-pick');
  const fmt2 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtKg = (v) => new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 }).format(v);
  const dmy = (iso) => { if (!iso) return ''; const [y, m, d] = String(iso).slice(0, 10).split('-'); return `${d}.${m}.${y}`; };
  const key = (c) => { const s = String(c || '').trim(); return /^\d+$/.test(s) ? (s.replace(/^0+/, '') || '0') : s.toUpperCase(); };
  const zahl = (v) => { const t = String(v ?? '').trim().replace(/\s/g, '').replace(/\.(?=\d{3}(\D|$))/g, '').replace(',', '.'); if (t === '') return null; const n = Number(t); return Number.isFinite(n) ? n : NaN; };
  const pText = (v) => (v == null || Number.isNaN(v) ? '' : v.toFixed(2).replace('.', ','));
  const zText = (v) => (v == null ? '' : String(Math.round(v * 100) / 100).replace('.', ','));
  const nat = (x, y) => String(x).localeCompare(String(y), 'de', { numeric: true });
  const STATUS = { entwurf: 'Entwurf', freigegeben: 'Im Portal freigegeben', zurueckgezogen: 'Zurückgezogen' };
  const isoPlus = (days) => { const d = new Date(); d.setDate(d.getDate() + days); return d.toISOString().slice(0, 10); };
  const COND = { frisch: 'frisch', gefroren: 'gefroren', unbekannt: '' };
  const OHNE_VK = '–';         // Gruppe „ohne VK-Gruppe“
  const ALLE = '*';            // alle Gruppen
  const MAX_ZEILEN = 400;
  const MAX_POS = 300;

  let liste = null, kunden = null, idx = null, idxMeta = null, ed = null, dirty = false, listQ = '', kq = null, kAkt = 0, mailFormat = 'liste';
  const pk = { q: '', grp: null, sel: new Set(), offen: new Set(), nurBestand: true, nurAngebot: false };   // Auswahlfenster
  const darf = () => may('einzelangebote.bearbeiten');

  /* Abweichung vom Wochenangebotspreis: Punkt + Prozent */
  function abw(price, std) {
    if (price == null || Number.isNaN(price) || !std || std.status !== 'value' || !(std.value > 0)) return '';
    const p = (price - std.value) / std.value * 100;
    const r = Math.round(p);
    const cls = Math.abs(p) < 1 ? 'ab-gleich' : p < -10 ? 'ab-stark' : p < 0 ? 'ab-unter' : 'ab-ueber';
    const txt = Math.abs(p) < 1 ? 'wie Wochenpreis' : `${Math.abs(r)} % ${p < 0 ? 'unter' : 'über'} Wochenpreis`;
    return `<span class="ez-abw ${cls}" title="${esc(txt)}" data-abw="${r}"><i></i>${Math.abs(p) < 1 ? '±0 %' : (p < 0 ? '−' : '+') + Math.abs(r) + ' %'}</span>`;
  }
  const stdText = (p) => (!p ? '<span class="muted">nicht im Angebot</span>' : p.status === 'value' ? fmt2.format(p.value) + ' €' : p.status === 'request' ? 'a. Anfr.' : '–');
  function bestandHTML(a, kurz) {
    if (!a || a.totalKg === undefined) return '<span class="muted">—</span>';
    if (!(a.totalKg > 0)) return '<span class="ez-kein">kein Bestand</span>';
    const t = `Eingelagert ${fmtKg(a.kg)} kg · Erfasst ${fmtKg(a.incomingKg)} kg · Gesamt verfügbar ${fmtKg(a.totalKg)} kg`;
    if (kurz) return `<span class="ez-bst" title="${esc(t)}">${esc(fmtKg(a.totalKg))} kg</span>`;
    return `<span class="ez-bst ez-bst3"><span>Eingelagert <b>${esc(fmtKg(a.kg))} kg</b></span><span>Erfasst <b>${esc(fmtKg(a.incomingKg))} kg</b></span><span>Gesamt verfügbar <b>${esc(fmtKg(a.totalKg))} kg</b></span></span>`;
  }

  async function laden() {
    const [l, k] = await Promise.all([api('einzel_liste'), kunden ? null : api('kunden')]);
    liste = l.list;
    if (k) kunden = new Map(k.customers.map((c) => [c.id, c]));
  }
  async function ladeIndex() {
    if (idx || !darf()) return;
    const r = await api('einzel_artikel');
    idx = new Map(r.articles.map((a) => [key(a.code), a]));
    idxMeta = { bestand: r.bestand, angebot: r.angebot, ek: !!r.ek, vk: new Map((r.vkGruppen || []).map((g) => [g.nr, g])) };
    if (!r.bestand) pk.nurBestand = false;
  }
  function koerper() {   // Kopfleiste: Drucken / E-Mail des geöffneten Einzelangebots
    document.body.classList.toggle('ez-editor', !!ed);
    document.body.classList.toggle('ez-gespeichert', !!(ed && ed.id));
    document.body.classList.toggle('ez-darf', darf());
  }

  async function render() {
    if (!liste) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Einzelangebote werden geladen …</div>';
    try { await laden(); await ladeIndex(); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    if (ed) renderEditor(); else renderListe();
  }

  /* ---------- Übersicht ---------- */
  function renderListe() {
    koerper();
    const toks = fold(listQ).split(/\s+/).filter(Boolean);
    const l = liste.filter((e) => { const hay = fold([e.nr, e.firma, e.kundeNr, e.titel, STATUS[e.status]].join(' ')); return toks.every((t) => hay.includes(t)); });
    host.innerHTML = `
      <div class="ed-toolbar">
        <div class="search">${icon('search')}<input id="ez-lq" type="search" autocomplete="off" placeholder="Einzelangebote finden: Nummer, Kunde, Titel …" aria-label="Einzelangebote suchen" value="${esc(listQ)}"></div>
        <span class="ed-hint">${plural(l.length, 'Einzelangebot', 'Einzelangebote')}</span>
        ${darf() ? `<button type="button" class="btn primary" id="ez-neu">${icon('plus')}Neues Einzelangebot</button>` : ''}
      </div>
      ${!liste.length ? `<div class="ed-empty"><h3>Noch keine Einzelangebote</h3><p>Ein Einzelangebot gilt für genau einen Kunden: Artikel auswählen, Preise und Mengen eintragen, dann im Portal freigeben, drucken oder per E-Mail senden.</p></div>`
        : !l.length ? '<div class="ed-empty"><h3>Keine Treffer</h3><p>Suchbegriff anpassen.</p></div>'
        : `<div class="gcard"><table class="etab eztab"><thead><tr><th>Nummer</th><th>Kunde</th><th class="ez-m">Titel</th><th class="num">Pos.</th><th class="num ez-m">Warenwert</th><th>Gültig bis</th><th>Status</th><th class="ez-m">Geändert</th></tr></thead><tbody>
          ${l.map((e) => `<tr data-ez="${esc(e.id)}" tabindex="0"><td class="ez-nr">${esc(e.nr)}</td><td>${esc(e.firma)}${e.kundeNr ? ` <span class="muted">· ${esc(e.kundeNr)}</span>` : ''}</td><td class="ez-m">${esc(e.titel || '')}</td><td class="num">${e.positionCount}</td>
            <td class="num ez-m">${e.summen.summe ? esc(fmt2.format(e.summen.summe)) + ' €' : '<span class="muted">–</span>'}</td><td>${e.gueltigBis ? esc(dmy(e.gueltigBis)) : '<span class="muted">offen</span>'}</td>
            <td>${statusChip(e)}</td><td class="ez-m">${esc(dateTime(e.changed))}<div class="sub">${esc(e.changedBy || '')}</div></td></tr>`).join('')}
        </tbody></table></div>`}`;
  }
  function statusChip(e) {
    const abgelaufen = e.gueltigBis && e.gueltigBis < new Date().toISOString().slice(0, 10);
    if (e.status === 'freigegeben' && abgelaufen) return '<span class="ez-st ab">abgelaufen</span>';
    return `<span class="ez-st ${esc(e.status)}">${esc(STATUS[e.status] || e.status)}</span>`;
  }

  /* ---------- Bearbeiten ---------- */
  function neu() {
    ed = { id: '', revision: 0, kid: '', titel: '', gueltigBis: isoPlus(14), hinweis: '', positions: [], status: 'entwurf', gesendet: [] };
    dirty = false;
    renderEditor();
  }
  async function oeffnen(id) {
    try { const r = await api('einzel_detail&id=' + encodeURIComponent(id)); ed = r.angebot; ed.fracht = r.fracht; dirty = false; renderEditor(); }
    catch (e) { toast(e.message); }
  }
  /* ---------- Kundenauswahl mit Suche ---------- */
  const kLabel = (c) => (c ? c.firma + (c.nr ? ' · ' + c.nr : '') + (c.ort ? ' · ' + c.ort : '') : '');
  /* Treffer: alle Suchwörter in Firma, Nummer, Ort, PLZ, Ansprechpartner, E-Mail, Straße; Nummer genau > Firma beginnt > Wortanfang > enthalten */
  function kundenTreffer(text) {
    const toks = fold(text).split(/\s+/).filter(Boolean);
    const l = [];
    for (const c of kunden.values()) {
      const hay = fold([c.firma, c.nr, c.plz, c.ort, c.ansprechpartner, c.email, c.strasse, c.gruppe].join(' '));
      if (!toks.every((t) => hay.includes(t))) continue;
      const f = fold(c.firma), t0 = toks[0] || '';
      const rang = !t0 ? 3 : fold(c.nr) === t0 ? 0 : f.startsWith(t0) ? 1 : (' ' + f).includes(' ' + t0) ? 2 : 3;
      l.push({ c, rang });
    }
    return l.sort((a, b) => a.rang - b.rang || (a.c.active === false) - (b.c.active === false) || a.c.firma.localeCompare(b.c.firma, 'de')).map((x) => x.c);
  }
  function renderKundenListe() {
    const ul = $('#ez-kunde-list'), inp = $('#ez-kunde');
    if (!ul || kq === null) { if (ul) { ul.hidden = true; inp.setAttribute('aria-expanded', 'false'); } return; }
    const alle = kundenTreffer(kq), l = alle.slice(0, 50);
    kAkt = Math.min(kAkt, Math.max(l.length - 1, 0));
    ul.innerHTML = l.length ? l.map((c, i) => `<li role="option" id="ez-ko-${i}" data-kid="${esc(c.id)}" class="${i === kAkt ? 'akt' : ''}" aria-selected="${c.id === ed.kid}">
        <span class="ez-ko-f">${esc(c.firma)}${c.active === false ? ' <span class="ez-tag">inaktiv</span>' : ''}${c.login && c.login.active ? '' : ' <span class="ez-tag">kein Portal</span>'}</span>
        <span class="ez-ko-d">${esc([c.nr ? 'Nr. ' + c.nr : '', [c.plz, c.ort].filter(Boolean).join(' '), c.ansprechpartner].filter(Boolean).join(' · '))}</span></li>`).join('')
        + (alle.length > l.length ? `<li class="ez-ko-mehr" aria-disabled="true">… ${alle.length - l.length} weitere – Suche eingrenzen</li>` : '')
      : '<li class="ez-ko-mehr" aria-disabled="true">Kein Kunde gefunden</li>';
    ul.hidden = false;
    inp.setAttribute('aria-expanded', 'true');
    if (l.length) inp.setAttribute('aria-activedescendant', 'ez-ko-' + kAkt); else inp.removeAttribute('aria-activedescendant');
    const akt = ul.querySelector('li.akt'); if (akt) akt.scrollIntoView({ block: 'nearest' });
  }
  function kundeSchliessen() {
    kq = null; renderKundenListe();
    const inp = $('#ez-kunde'); if (inp) { inp.value = kLabel(kunden.get(ed.kid)); inp.removeAttribute('aria-activedescendant'); }
  }
  function kundeWaehlen(id) {
    kq = null;
    if (id !== ed.kid) { kopfLesen(); ed.kid = id; markDirty(); }
    renderEditor();
    const t = $('#ez-titel'); if (t) t.focus();
  }
  function renderEditor() {
    koerper();
    const ro = !darf();
    const k = ed.kid ? kunden.get(ed.kid) : null;
    host.innerHTML = `
      <div class="ez-top">
        <button type="button" class="btn ghost" id="ez-zurueck">${icon('chev', 'ez-back')}Alle Einzelangebote</button>
        <h2>${ed.id ? `Einzelangebot ${esc(ed.nr)}` : 'Neues Einzelangebot'} ${ed.id ? statusChip(ed) : ''}</h2>
        <span class="ez-dirty" id="ez-dirty"${dirty ? '' : ' hidden'}>nicht gespeichert</span>
      </div>
      <section class="ez-main">
        <div class="gcard ez-kopf"><div class="form-grid two">
          <div class="fld span2 ez-kwahl"><span id="ez-kunde-l">Kunde</span><div class="ez-kbox">${icon('search')}<input id="ez-kunde" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="ez-kunde-list" aria-labelledby="ez-kunde-l" autocomplete="off" spellcheck="false" placeholder="Kunde suchen: Firma, Kundennummer, Ort, Ansprechpartner …" value="${esc(kLabel(k))}"${ro ? ' disabled' : ''}></div><ul id="ez-kunde-list" class="ez-klist" role="listbox" aria-label="Kunden" hidden></ul></div>
          <label class="fld"><span>Titel <small class="muted">(optional)</small></span><input id="ez-titel" maxlength="120" value="${esc(ed.titel || '')}" placeholder="${esc(k ? 'Angebot für ' + k.firma : 'z. B. Angebot Grillsaison')}"${ro ? ' disabled' : ''}></label>
          <label class="fld"><span>Gültig bis</span><input id="ez-bis" type="date" value="${esc(ed.gueltigBis || '')}"${ro ? ' disabled' : ''}></label>
          <label class="fld span2"><span>Hinweis an den Kunden <small class="muted">(optional, erscheint im Angebot)</small></span><textarea id="ez-hinweis" rows="2" maxlength="1000"${ro ? ' disabled' : ''}>${esc(ed.hinweis || '')}</textarea></label>
        </div>${k ? `<p class="hint ez-kinfo">${esc([k.ansprechpartner, k.strasse, [k.plz, k.ort].filter(Boolean).join(' '), k.email].filter(Boolean).join(' · '))}${k.login && k.login.active ? '' : ' · <span class="st-warn">kein Portal-Zugang – Freigabe im Portal sieht der Kunde erst mit Zugang</span>'}</p>` : ''}</div>
        <div class="gcard ez-pos">
          <div class="ez-pos-kopf"><h3>Positionen</h3><span class="ez-pos-n" id="ez-pos-n"></span>
            ${ro ? '' : `<span class="sp"></span><button type="button" class="btn ghost" id="ez-frei">${icon('plus', 'sm')}Freie Position</button><button type="button" class="btn primary" id="ez-add">${icon('plus')}Artikel hinzufügen</button>`}</div>
          <div id="ez-pos"></div></div>
        <div class="ez-actions">
          ${ro ? '' : `<button type="button" class="btn primary" id="ez-save">${icon('check')}Speichern</button>`}
          ${ro || !ed.id ? '' : ed.status === 'freigegeben' ? `<button type="button" class="btn" id="ez-entfreigeben">${icon('undo')}Freigabe beenden</button>` : `<button type="button" class="btn" id="ez-freigeben">${icon('eye')}Im Portal freigeben</button>`}
          <button type="button" class="btn" id="ez-druck"${ed.positions.length ? '' : ' disabled'}>${icon('print')}Drucken / PDF</button>
          ${ro || !ed.id ? '' : `<button type="button" class="btn" id="ez-mail">${icon('mail')}Per E-Mail senden</button>`}
          ${ro || !ed.id ? '' : `<span class="sp"></span><button type="button" class="btn ghost" id="ez-del" style="color:var(--accent)">${icon('trash', 'sm')}Löschen</button>`}
        </div>
        ${ed.id ? `<p class="hint ez-verlauf">Angelegt ${esc(dateTime(ed.created))} von ${esc(ed.createdBy || '')} · geändert ${esc(dateTime(ed.changed))}${ed.status === 'freigegeben' && ed.freigegebenAt ? ` · im Portal seit ${esc(dateTime(ed.freigegebenAt))}` : ''}${(ed.gesendet || []).length ? ' · per E-Mail: ' + ed.gesendet.slice(-3).map((g) => `${esc(dateTime(g.t))} an ${esc(g.to)}${g.format === 'pdf' ? ' (PDF)' : ''}${g.ok ? '' : ' (nicht zugestellt)'}`).join(', ') : ''}</p>` : ''}
      </section>`;
    renderPos();
  }
  function renderPos() {
    const ro = !darf();
    const el = $('#ez-pos');
    const n = $('#ez-pos-n'); if (n) n.textContent = ed.positions.length ? plural(ed.positions.length, 'Position', 'Positionen') : '';
    const druck = $('#ez-druck'); if (druck) druck.disabled = !ed.positions.length;
    if (!ed.positions.length) {
      el.innerHTML = `<div class="ez-leer">${icon('box')}<p>${ro ? 'Keine Positionen.' : 'Noch keine Positionen.'}</p>${ro ? '' : `<button type="button" class="btn" data-pick-open>${icon('plus', 'sm')}Artikel nach VK-Gruppe auswählen</button>`}</div>`;
      return;
    }
    el.innerHTML = `<table class="etab ezpos"><thead><tr><th>Art.-Nr.</th><th>Artikel</th><th class="ez-b">Verfügbar</th><th class="num">Wochenpreis</th><th class="num">Preis €/kg</th><th class="ez-a">Abw.</th><th class="num">Menge kg</th>${ro ? '' : '<th></th>'}</tr></thead><tbody>
      ${ed.positions.map((p, i) => { const a = p.code ? idx && idx.get(key(p.code)) : null; return `<tr data-i="${i}">
        <td class="ez-code">${esc(p.code || '—')}</td>
        <td class="ez-name">${ro ? esc(p.name) : `<input class="ez-in-name" data-f="name" value="${esc(p.name)}" maxlength="200" aria-label="Bezeichnung">`}${ro ? (p.notiz ? `<div class="sub">${esc(p.notiz)}</div>` : '') : `<input class="ez-in-notiz" data-f="notiz" value="${esc(p.notiz || '')}" maxlength="200" placeholder="Notiz (optional)" aria-label="Notiz">`}</td>
        <td class="ez-b" data-l="Verfügbar">${bestandHTML(a, true)}</td>
        <td class="num ez-std" data-l="Wochenpreis">${a ? stdText(a.stdPrice) : '<span class="muted">–</span>'}</td>
        <td class="num" data-l="Preis €/kg">${ro ? (p.price != null ? esc(fmt2.format(p.price)) : 'a. Anfr.') : `<input class="ez-in-num" data-f="price" inputmode="decimal" value="${esc(pText(p.price))}" placeholder="a. Anfr." aria-label="Preis je kg">`}</td>
        <td class="ez-a" data-l="Abweichung" data-abw-cell>${abw(p.price, a && a.stdPrice)}</td>
        <td class="num" data-l="Menge kg">${ro ? (p.qty != null ? esc(fmtKg(p.qty)) : '') : `<input class="ez-in-num" data-f="qty" inputmode="decimal" value="${esc(zText(p.qty))}" placeholder="—" aria-label="Menge in kg">`}</td>
        ${ro ? '' : `<td class="ez-x"><button type="button" class="ibtn danger" data-del="${i}" aria-label="Position entfernen" title="Entfernen">${icon('x', 'sm')}</button></td>`}</tr>`; }).join('')}
      </tbody><tfoot><tr><td colspan="2">${plural(ed.positions.length, 'Position', 'Positionen')}</td><td class="ez-b"></td><td></td><td class="num" colspan="3" id="ez-summe">${summeHTML()}</td>${ro ? '' : '<td></td>'}</tr></tfoot></table>`;
  }
  function summen() {
    let kg = 0, sum = 0;
    for (const p of ed.positions) if (p.qty != null && !Number.isNaN(p.qty)) { kg += p.qty; if (p.price != null && !Number.isNaN(p.price)) sum += Math.round(Math.round(p.price * 100) * p.qty) / 100; }
    return { kg, sum };
  }
  function summeHTML() { const { kg, sum } = summen(); return kg ? `${esc(fmtKg(kg))} kg · Warenwert ca. <strong>${esc(fmt2.format(sum))} €</strong>` : '<span class="muted">Mengen optional</span>'; }
  const hinzufuegen = (a) => ed.positions.push({ code: a.code, name: a.name, qty: null, price: a.stdPrice && a.stdPrice.status === 'value' ? a.stdPrice.value : null, notiz: '' });

  /* ---------- Fenster „Artikel hinzufügen“: VK-Gruppen links, Artikel rechts, Suche über alle Gruppen ---------- */
  const vkName = (nr) => { const g = nr && idxMeta && idxMeta.vk.get(nr); return g && g.name ? g.name : ''; };
  const vkText = (nr) => (nr === OHNE_VK || !nr ? 'ohne VK-Gruppe' : nr + (vkName(nr) ? ' · ' + vkName(nr) : ''));
  const grpVon = (a) => a.vk || OHNE_VK;
  const drinSet = () => new Set(ed.positions.map((p) => key(p.code)));
  function passt(a, toks) {
    if (pk.nurBestand && !(a.totalKg > 0)) return false;
    if (pk.nurAngebot && !a.inOffer) return false;
    if (!toks.length) return true;
    const hay = fold([a.code, a.name, a.origin, a.vk, vkName(a.vk)].join(' '));
    return toks.every((t) => hay.includes(t));
  }
  /* Treffer der Filter/Suche (ohne Gruppenwahl) und Anzahl je Gruppe */
  function pickBasis() {
    const toks = fold(pk.q).split(/\s+/).filter(Boolean);
    const l = [...idx.values()].filter((a) => passt(a, toks));
    const n = new Map();
    for (const a of l) n.set(grpVon(a), (n.get(grpVon(a)) || 0) + 1);
    return { l, n };
  }
  /* Angezeigte Artikel: gewählte Gruppe, sonst (bei Suche) alle Gruppen; sortiert nach Gruppe und Artikelnummer */
  function pickZeilen(basis) {
    const g = pk.grp || (pk.q.trim() ? ALLE : null);
    if (!g) return null;
    return basis.l.filter((a) => g === ALLE || grpVon(a) === g)
      .sort((a, b) => (!a.vk) - (!b.vk) || nat(a.vk || '', b.vk || '') || nat(a.code, b.code));
  }
  function pickOeffnen() {
    if (!idx) return;
    pk.sel.clear(); pk.offen.clear(); pk.q = '';
    if (pk.grp && pk.grp !== ALLE && pk.grp !== OHNE_VK && !idxMeta.vk.has(pk.grp)) pk.grp = null;
    const k = ed.kid ? kunden.get(ed.kid) : null;
    $('#ez-pick-body').innerHTML = `
      <div class="dlg-head ezp-head">
        <div class="ezp-t"><h2 id="ezp-title">Artikel hinzufügen</h2><p>${esc([ed.nr || 'Neues Einzelangebot', k ? k.firma : ''].filter(Boolean).join(' · '))}</p></div>
        <div class="search ezp-q">${icon('search')}<input id="ezp-q" type="search" autocomplete="off" placeholder="Artikel in allen Gruppen suchen: Nummer, Bezeichnung, Herkunft …" aria-label="Artikel in allen Gruppen suchen"></div>
        <div class="ezp-f">${idxMeta.bestand ? `<label class="check"><input type="checkbox" id="ezp-bestand"${pk.nurBestand ? ' checked' : ''}> nur mit Bestand</label>` : ''}<label class="check"><input type="checkbox" id="ezp-angebot"${pk.nurAngebot ? ' checked' : ''}> nur im Wochenangebot</label></div>
        <button class="btn icon ghost ezp-x" type="button" data-pick-close aria-label="Schließen">${icon('x')}</button>
      </div>
      <div class="ezp-main">
        <nav class="ezp-nav" aria-label="VK-Gruppen"><div class="ezp-nav-h">VK-Gruppen</div><div id="ezp-grp"></div></nav>
        <label class="ezp-grp-m"><span>VK-Gruppe</span><select id="ezp-grp-sel" aria-label="VK-Gruppe wählen"></select></label>
        <section class="ezp-list" id="ezp-list" aria-live="polite"></section>
      </div>
      <div class="dlg-foot ezp-foot"><span class="ezp-anz" id="ezp-anz"></span><span class="spacer"></span>
        <button type="button" class="btn" data-pick-close>Abbrechen</button><button type="button" class="btn primary" id="ezp-ok" disabled>${icon('plus')}<span>Hinzufügen</span></button></div>`;
    renderPick();
    dlgPick.showModal();
    $('#ezp-q').focus();
  }
  function renderPick() { const b = pickBasis(); renderPickNav(b); renderPickList(b); renderPickFoot(); }
  function renderPickNav(basis) {
    const gruppen = [...idxMeta.vk.values()];
    const ohne = [...idx.values()].some((a) => !a.vk);
    const eintrag = (nr, label) => { const n = nr === ALLE ? basis.l.length : basis.n.get(nr) || 0; return { nr, label, n }; };
    const l = [eintrag(ALLE, 'Alle Gruppen'), ...gruppen.map((g) => eintrag(g.nr, g.name || '(ohne Bezeichnung)')), ...(ohne ? [eintrag(OHNE_VK, 'ohne VK-Gruppe')] : [])];
    const akt = pk.grp || (pk.q.trim() ? ALLE : null);
    $('#ezp-grp').innerHTML = l.map((g) => `<button type="button" class="ezp-g${g.n ? '' : ' leer'}" data-grp="${esc(g.nr)}" aria-pressed="${akt === g.nr}">
        <span class="ezp-g-nr">${g.nr === ALLE || g.nr === OHNE_VK ? '' : esc(g.nr)}</span><span class="ezp-g-n">${esc(g.label)}</span><span class="ezp-g-z">${g.n}</span></button>`).join('')
      + (!gruppen.length ? '<p class="hint">Den Artikeln sind noch keine VK-Gruppen zugeordnet (Stammdaten → Artikelstammdaten).</p>' : '');
    $('#ezp-grp-sel').innerHTML = `<option value=""${akt ? '' : ' selected'}>– VK-Gruppe wählen –</option>` + l.map((g) => `<option value="${esc(g.nr)}"${akt === g.nr ? ' selected' : ''}>${esc((g.nr === ALLE || g.nr === OHNE_VK ? '' : g.nr + ' · ') + g.label)} (${g.n})</option>`).join('');
  }
  function detailHTML(a) {
    const merk = [a.category, a.origin, COND[a.condition] || ''].filter((x) => x && x !== 'Sonstiges');
    const kopf = `<div class="ez-det-m"><span>VK-Gruppe <b>${esc(a.vk ? vkText(a.vk) : '—')}</b></span>${merk.length ? `<span>${esc(merk.join(' · '))}</span>` : ''}
      <span>Wochenpreis <b>${a.inOffer ? stdText(a.stdPrice) : 'nicht im Angebot'}</b></span></div>`;
    if (a.totalKg === undefined) return kopf + '<p class="hint">Bestand nur mit dem Recht „Bestand ansehen“.</p>';
    const ek = idxMeta && idxMeta.ek;
    const lots = a.lots || [], inc = a.incoming || [];
    const lotsHTML = lots.length ? `<div class="ez-dtw"><table class="ez-dt"><thead><tr><th>Partie</th><th>Eingang</th><th>MHD</th><th class="num">Kolli</th><th class="num">kg</th>${ek ? '<th class="num">EK €/kg</th>' : ''}</tr></thead><tbody>
        ${lots.map((l) => `<tr><td>${esc(l.lot || '—')}</td><td>${esc(dmy(l.arrival)) || '—'}</td><td>${esc(dmy(l.mhd)) || '—'}</td><td class="num">${l.kolli != null ? esc(fmtKg(l.kolli)) : '—'}</td><td class="num">${esc(fmtKg(l.kg))}</td>${ek ? `<td class="num">${l.ek != null ? esc(fmt2.format(l.ek)) : '—'}</td>` : ''}</tr>`).join('')}</tbody></table></div>`
      : `<p class="hint">${a.kg > 0 ? 'Keine Partiedaten in der Bestandsliste.' : 'Kein eingelagerter Bestand.'}</p>`;
    const incHTML = inc.length ? `<div class="ez-dtw"><table class="ez-dt"><thead><tr><th>Partie</th><th>Ankunft (ETA)</th><th class="num">kg</th></tr></thead><tbody>
        ${inc.map((z) => `<tr><td>${esc(z.lot || '—')}</td><td>${z.arrival ? esc(dmy(z.arrival)) : '<span class="muted">ETA unbekannt</span>'}</td><td class="num">${esc(fmtKg(z.kg))}</td></tr>`).join('')}</tbody></table></div>`
      : '<p class="hint">Keine erwarteten Ankünfte.</p>';
    return kopf + `<div class="ez-det-s">${bestandHTML(a)}${a.mhd ? `<span>kürzestes MHD <b>${esc(dmy(a.mhd))}</b></span>` : ''}</div>
      <div class="ez-det-2"><div><h4>Eingelagerte Partien</h4>${lotsHTML}</div><div><h4>Erwartete Ankünfte</h4>${incHTML}</div></div>`;
  }
  function renderPickList(basis) {
    const el = $('#ezp-list');
    const zeilen = pickZeilen(basis);
    if (!zeilen) {
      el.innerHTML = `<div class="ezp-start">${icon('tag')}<h3>Zuerst eine VK-Gruppe wählen</h3><p>Links die VK-Gruppe anklicken, dann die Artikel markieren und gesammelt hinzufügen. Über das Suchfeld oben finden Sie jederzeit Artikel aus allen Gruppen.</p></div>`;
      return;
    }
    const drin = drinSet();
    const mitB = !!idxMeta.bestand;
    const g = pk.grp || ALLE;
    const frei = zeilen.filter((a) => !drin.has(key(a.code)));
    const alleMarkiert = frei.length && frei.every((a) => pk.sel.has(key(a.code)));
    const kg = zeilen.reduce((s, a) => s + (a.totalKg || 0), 0);
    const titel = g === ALLE ? (pk.q.trim() ? `Suche „${pk.q.trim()}“ in allen Gruppen` : 'Alle Gruppen') : vkText(g);
    const l = zeilen.slice(0, MAX_ZEILEN);
    let grp = null;
    const cols = mitB ? 8 : 5;
    el.innerHTML = `<div class="ezp-lkopf"><div><h3>${esc(titel)}</h3><p>${plural(zeilen.length, 'Artikel', 'Artikel')}${mitB ? ` · ${esc(fmtKg(Math.round(kg * 100) / 100))} kg verfügbar` : ''}${idxMeta.bestand ? ` · Bestand vom ${esc(dmy(idxMeta.bestand.date))}` : ''}${idxMeta.angebot ? ` · Wochenpreis KW ${esc(idxMeta.angebot.week)}` : ''}</p></div>
        ${frei.length ? `<button type="button" class="btn sm" id="ezp-alle" data-alle="${alleMarkiert ? 'aus' : 'an'}">${alleMarkiert ? 'Markierung aufheben' : (g === ALLE ? 'Alle Treffer markieren' : 'Alle dieser Gruppe markieren')}</button>` : ''}</div>
      ${l.length ? `<div class="ezp-tw"><table class="ezp-tab"><thead><tr><th class="ezp-c"><span class="sr-only">Auswahl</span></th><th>Art.-Nr.</th><th>Bezeichnung</th>${mitB ? '<th class="num">Eingelagert</th><th class="num ezp-m">Erwartet</th><th class="ezp-m">kürz. MHD</th>' : ''}<th class="num">Wochenpreis</th><th class="ezp-i"><span class="sr-only">Details</span></th></tr></thead><tbody>
        ${l.map((a) => {
          const k = key(a.code), ist = drin.has(k), sel = pk.sel.has(k), auf = pk.offen.has(k);
          let h = '';
          if (g === ALLE && grpVon(a) !== grp) { grp = grpVon(a); h += `<tr class="ezp-gr"><td colspan="${cols}">${esc(vkText(grp))}</td></tr>`; }
          const merk = [a.origin, COND[a.condition] || ''].filter(Boolean).join(' · ');
          h += `<tr class="ezp-z${sel ? ' sel' : ''}${ist ? ' drin' : ''}${auf ? ' auf' : ''}" data-code="${esc(a.code)}">
            <td class="ezp-c"><input type="checkbox" data-sel="${esc(a.code)}"${sel || ist ? ' checked' : ''}${ist ? ' disabled' : ''} aria-label="${esc(a.code + ' ' + (a.name || ''))} auswählen"></td>
            <td class="ezp-nr">${esc(a.code)}</td>
            <td class="ezp-n"><span>${esc(a.name || '(ohne Bezeichnung)')}</span>${ist ? ' <span class="ez-tag ezp-drin">im Angebot</span>' : ''}${merk ? `<small>${esc(merk)}</small>` : ''}
              ${mitB ? `<small class="ezp-mob">${a.totalKg > 0 ? esc(fmtKg(a.totalKg)) + ' kg verfügbar' : 'kein Bestand'}</small>` : ''}</td>
            ${mitB ? `<td class="num ezp-kg">${a.kg > 0 ? `<b>${esc(fmtKg(a.kg))} kg</b>` : '<span class="ez-kein">kein Bestand</span>'}</td>
              <td class="num ezp-m">${a.incomingKg > 0 ? esc(fmtKg(a.incomingKg)) + ' kg' : '<span class="muted">–</span>'}</td>
              <td class="ezp-m">${a.mhd ? esc(dmy(a.mhd)) : '<span class="muted">–</span>'}</td>` : ''}
            <td class="num ezp-p">${a.stdPrice ? stdText(a.stdPrice) : '<span class="muted" title="nicht im Wochenangebot">–</span>'}</td>
            <td class="ezp-i"><button type="button" class="ibtn" data-info="${esc(a.code)}" aria-expanded="${auf}" aria-label="Details zu ${esc(a.code)}" title="Partien, Bestand, Ankünfte">${icon('info', 'sm')}</button></td></tr>`;
          if (auf) h += `<tr class="ezp-det" data-det="${esc(a.code)}"><td colspan="${cols}">${detailHTML(a)}</td></tr>`;
          return h;
        }).join('')}</tbody></table></div>` : '<p class="hint ezp-leer">Keine Artikel – Filter oder Suche anpassen.</p>'}
      ${zeilen.length > l.length ? `<p class="hint">… ${zeilen.length - l.length} weitere – Suche eingrenzen.</p>` : ''}`;
  }
  function renderPickFoot() {
    const n = pk.sel.size;
    const zuviel = ed.positions.length + n > MAX_POS;
    $('#ezp-anz').innerHTML = n ? `<b>${plural(n, 'Artikel', 'Artikel')} ausgewählt</b> · Preise werden mit dem Wochenpreis vorbelegt${zuviel ? ` · <span class="st-err">höchstens ${MAX_POS} Positionen je Einzelangebot</span>` : ''}` : 'Artikel markieren, um sie hinzuzufügen.';
    const ok = $('#ezp-ok');
    ok.disabled = !n || zuviel;
    ok.querySelector('span').textContent = n ? `${plural(n, 'Artikel', 'Artikel')} hinzufügen` : 'Hinzufügen';
  }
  function pickUebernehmen() {
    const drin = drinSet();
    const neuL = [...idx.values()].filter((a) => pk.sel.has(key(a.code)) && !drin.has(key(a.code)))
      .sort((a, b) => (!a.vk) - (!b.vk) || nat(a.vk || '', b.vk || '') || nat(a.code, b.code));
    if (!neuL.length || ed.positions.length + neuL.length > MAX_POS) return;
    kopfLesen();
    neuL.forEach(hinzufuegen);
    dlgPick.close();
    markDirty(); renderPos();
    toast(`${plural(neuL.length, 'Artikel', 'Artikel')} hinzugefügt.`);
  }
  function pickGruppe(g) {
    pk.grp = g || null; pk.offen.clear();
    const b = pickBasis(); renderPickNav(b); renderPickList(b);
    const lst = $('#ezp-list'); if (lst) lst.scrollTop = 0;
  }
  dlgPick.addEventListener('input', (e) => {
    if (e.target.id === 'ezp-q') {
      if (!pk.q.trim() && e.target.value.trim()) pk.grp = null;   // neue Suche gilt für alle Gruppen; per Klick auf eine Gruppe eingrenzen
      pk.q = e.target.value; pk.offen.clear(); const b = pickBasis(); renderPickNav(b); renderPickList(b);
    }
  });
  dlgPick.addEventListener('change', (e) => {
    const t = e.target;
    if (t.id === 'ezp-bestand') { pk.nurBestand = t.checked; renderPick(); return; }
    if (t.id === 'ezp-angebot') { pk.nurAngebot = t.checked; renderPick(); return; }
    if (t.id === 'ezp-grp-sel') { pickGruppe(t.value); return; }
    if (t.dataset.sel !== undefined) {
      const k = key(t.dataset.sel);
      if (t.checked) pk.sel.add(k); else pk.sel.delete(k);
      const tr = t.closest('tr'); if (tr) tr.classList.toggle('sel', t.checked);
      renderPickFoot();
      const b = pickBasis(), z = pickZeilen(b) || [], drin = drinSet(), frei = z.filter((a) => !drin.has(key(a.code)));
      const btn = $('#ezp-alle');
      if (btn) { const alle = frei.length && frei.every((a) => pk.sel.has(key(a.code))); btn.dataset.alle = alle ? 'aus' : 'an'; btn.textContent = alle ? 'Markierung aufheben' : ((pk.grp || ALLE) === ALLE ? 'Alle Treffer markieren' : 'Alle dieser Gruppe markieren'); }
    }
  });
  dlgPick.addEventListener('click', (e) => {
    const t = e.target;
    if (t.closest('[data-pick-close]')) { dlgPick.close(); return; }
    const g = t.closest('[data-grp]');
    if (g) { pickGruppe(g.dataset.grp); return; }
    const info = t.closest('[data-info]');
    if (info) {
      const k = key(info.dataset.info);
      if (pk.offen.has(k)) pk.offen.delete(k); else pk.offen.add(k);
      const lst = $('#ezp-list'), top = lst.scrollTop;
      renderPickList(pickBasis());
      lst.scrollTop = top;
      const b = $(`#ezp-list [data-info="${CSS.escape(info.dataset.info)}"]`); if (b) b.focus();
      return;
    }
    const alle = t.closest('#ezp-alle');
    if (alle) {
      const drin = drinSet(), z = pickZeilen(pickBasis()) || [];
      for (const a of z) if (!drin.has(key(a.code))) { if (alle.dataset.alle === 'an') pk.sel.add(key(a.code)); else pk.sel.delete(key(a.code)); }
      const lst = $('#ezp-list'), top = lst.scrollTop;
      renderPickList(pickBasis()); renderPickFoot();
      lst.scrollTop = top;
      return;
    }
    if (t.closest('#ezp-ok')) { pickUebernehmen(); return; }
    // Klick auf die Zeile (außer Knöpfe/Häkchen) wählt den Artikel
    const z = t.closest('tr.ezp-z');
    if (z && !t.closest('input, button')) { const c = z.querySelector('[data-sel]'); if (c && !c.disabled) { c.checked = !c.checked; c.dispatchEvent(new Event('change', { bubbles: true })); } }
  });

  function markDirty() { dirty = true; const d = $('#ez-dirty'); if (d) d.hidden = false; }
  function kopfLesen() {
    if (!$('#ez-titel')) return;
    ed.titel = $('#ez-titel').value.trim(); ed.gueltigBis = $('#ez-bis').value; ed.hinweis = $('#ez-hinweis').value;
  }
  async function speichern() {
    kopfLesen();
    const bad = ed.positions.find((p) => Number.isNaN(p.price) || Number.isNaN(p.qty));
    if (bad) { toast(`Bitte Preis bzw. Menge bei „${bad.name}“ prüfen.`); return false; }
    try {
      const r = await api('einzel_save', { body: { id: ed.id, revision: ed.revision, kid: ed.kid, titel: ed.titel, gueltigBis: ed.gueltigBis, hinweis: ed.hinweis,
        positions: ed.positions.map((p) => ({ code: p.code, name: p.name, qty: p.qty, price: p.price, notiz: p.notiz || '' })) } });
      const fr = ed.fracht;
      ed = r.angebot; ed.fracht = fr; dirty = false;
      liste = null;
      toast(`Einzelangebot ${ed.nr} gespeichert.`);
      renderEditor();
      return true;
    } catch (e) { toast(e.message, 6000); return false; }
  }
  async function status(s) {
    if (dirty && !(await speichern())) return;
    try { const r = await api('einzel_status', { body: { id: ed.id, revision: ed.revision, status: s } }); const fr = ed.fracht; ed = r.angebot; ed.fracht = fr; toast(s === 'freigegeben' ? 'Im Portal freigegeben – der Kunde sieht das Angebot nach der Anmeldung.' : 'Freigabe beendet.'); renderEditor(); }
    catch (e) { toast(e.message, 6000); }
  }

  /* ---------- Drucken / PDF: wie auf der Angebotsseite (deren Druckdialog, z. B. Angebotsliste A4 quer) ---------- */
  async function drucken() {
    if (!ed.positions.length) { toast('Bitte zuerst Positionen eintragen.'); return; }
    const w = window.open('', '_blank');   // sofort im Klick öffnen, sonst blockiert der Browser das Fenster nach dem Speichern
    if (!w) { toast('Das Druckfenster wurde vom Browser blockiert. Bitte Pop-ups für diese Seite erlauben.'); return; }
    try { w.document.write('<!doctype html><meta charset="utf-8"><title>Angebot wird vorbereitet …</title><p style="font:14px sans-serif;padding:24px">Angebot wird vorbereitet …</p>'); } catch { /* geschlossen */ }
    if ((dirty || !ed.id) && !(await speichern())) { w.close(); return; }
    if (w.closed) return;
    w.location.href = new URL('../?angebot=e-' + encodeURIComponent(ed.id) + '&drucken=1', location.href).href;
  }

  /* ---------- E-Mail ---------- */
  async function mailDialog() {
    if (dirty && !(await speichern())) return;
    const k = kunden.get(ed.kid) || {};
    const fmtR = (v, t, s) => `<label class="radio"><input type="radio" name="format" value="${v}"${mailFormat === v ? ' checked' : ''}><span class="r-t">${t}<span class="r-s">${s}</span></span></label>`;
    $('#einzel-mail-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="em-title">Angebot ${esc(ed.nr)} per E-Mail senden</h2><p>an ${esc(k.firma || '')}${k.email ? ' · ' + esc(k.email) : ''}</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        ${k.email ? '' : '<p class="hint st-err">Für diesen Kunden ist keine E-Mail-Adresse hinterlegt (Stammdaten → Kunden).</p>'}
        <fieldset class="choice ez-format"><legend>So kommt das Angebot an</legend>
          ${fmtR('liste', 'Als Liste in der E-Mail', 'Alle Positionen mit Preisen direkt im Text der E-Mail (wie bisher)')}
          ${fmtR('pdf', 'Als PDF im Anhang', 'Kurze Nachricht; das Angebot im Design der Angebotsansicht (A4 quer, mit Logo) als PDF-Datei')}
        </fieldset>
        <p class="hint ez-pdf-vorschau"><a href="../api/?action=einzel_pdf&amp;id=${encodeURIComponent(ed.id)}" target="_blank" rel="noopener">${icon('file', 'sm')}PDF-Vorschau öffnen</a></p>
        <label class="fld"><span>Persönliche Nachricht <small class="muted">(optional)</small></span><textarea name="note" rows="3" maxlength="1000"></textarea></label>
        <p class="hint">Die E-Mail enthält${ed.gueltigBis ? ' die Gültigkeit und' : ''} – wenn freigegeben und der Kunde einen Zugang hat – den Link ins Portal.${ed.status !== 'freigegeben' ? ' Das Angebot ist noch nicht im Portal freigegeben.' : ''}</p>
        <p class="kerr" id="em-err" role="alert"></p>
      </div>
      <div class="dlg-foot"><button type="button" class="btn" data-close>Abbrechen</button><button type="submit" class="btn primary"${k.email ? '' : ' disabled'}>${icon('send')}Senden</button></div>`;
    dlgMail.showModal();
  }
  $('#einzel-mail-body').addEventListener('click', (e) => { if (e.target.closest('[data-close]')) dlgMail.close(); });
  $('#einzel-mail-body').addEventListener('submit', async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector('[type=submit]');
    btn.disabled = true;
    const format = (e.target.querySelector('input[name="format"]:checked') || {}).value || 'liste';
    mailFormat = format;
    try {
      const r = await api('einzel_senden', { body: { id: ed.id, note: e.target.note.value, format } });
      const fr = ed.fracht; ed = r.angebot; ed.fracht = fr; dlgMail.close();
      toast(`Angebot ${ed.nr} per E-Mail gesendet${format === 'pdf' ? ' (PDF im Anhang)' : ''}.`); renderEditor();
    } catch (ex) { $('#em-err').textContent = ex.message; btn.disabled = false; }
  });

  /* ---------- Kopfleiste: Drucken / E-Mail des geöffneten Einzelangebots ---------- */
  $('#btn-ez-druck').addEventListener('click', () => { if (ed) { kopfLesen(); drucken(); } });
  $('#btn-ez-mail').addEventListener('click', () => { if (ed && ed.id && darf()) { kopfLesen(); mailDialog(); } });

  /* ---------- Ereignisse ---------- */
  host.addEventListener('input', (e) => {
    const t = e.target;
    if (t.id === 'ez-lq') { listQ = t.value; renderListe(); $('#ez-lq').focus(); $('#ez-lq').setSelectionRange(listQ.length, listQ.length); return; }
    if (t.id === 'ez-kunde') { kq = t.value; kAkt = 0; renderKundenListe(); return; }
    if (['ez-titel', 'ez-bis', 'ez-hinweis'].includes(t.id)) { markDirty(); return; }
    const tr = t.closest('tr[data-i]');
    if (tr && t.dataset.f) {
      const p = ed.positions[+tr.dataset.i];
      if (t.dataset.f === 'name' || t.dataset.f === 'notiz') p[t.dataset.f] = t.value;
      else {
        const v = zahl(t.value);
        p[t.dataset.f] = v;
        t.classList.toggle('invalid', Number.isNaN(v) || (v != null && (v < 0 || (t.dataset.f === 'qty' && (v === 0 || v > 99999)))));
        if (t.dataset.f === 'price') { const a = p.code ? idx && idx.get(key(p.code)) : null; tr.querySelector('[data-abw-cell]').innerHTML = abw(v, a && a.stdPrice); }
        const su = $('#ez-summe'); if (su) su.innerHTML = summeHTML();
      }
      markDirty();
    }
  });
  host.addEventListener('click', async (e) => {
    const t = e.target;
    if (t.closest('#ez-neu')) { neu(); return; }
    const row = t.closest('tr[data-ez]');
    if (row && !ed) { oeffnen(row.dataset.ez); return; }
    if (t.closest('#ez-zurueck')) {
      if (dirty && !(await confirmBox('Änderungen verwerfen?', 'Das Einzelangebot hat ungespeicherte Änderungen.', 'Verwerfen', true))) return;
      ed = null; dirty = false; render(); return;
    }
    const ko = t.closest('#ez-kunde-list li[data-kid]');
    if (ko) { kundeWaehlen(ko.dataset.kid); return; }
    if (t.closest('#ez-add, [data-pick-open]')) { kopfLesen(); pickOeffnen(); return; }
    if (t.closest('#ez-frei')) {
      kopfLesen(); ed.positions.push({ code: '', name: 'Freie Position', qty: null, price: null, notiz: '' }); markDirty(); renderPos();
      const inp = $(`#ez-pos tr[data-i="${ed.positions.length - 1}"] [data-f="name"]`); if (inp) { inp.focus(); inp.select(); }
      return;
    }
    const del = t.closest('[data-del]');
    if (del) { kopfLesen(); ed.positions.splice(+del.dataset.del, 1); markDirty(); renderPos(); return; }
    if (t.closest('#ez-save')) { speichern(); return; }
    if (t.closest('#ez-freigeben')) { status('freigegeben'); return; }
    if (t.closest('#ez-entfreigeben')) { status('entwurf'); return; }
    if (t.closest('#ez-druck')) { kopfLesen(); drucken(); return; }
    if (t.closest('#ez-mail')) { kopfLesen(); mailDialog(); return; }
    if (t.closest('#ez-del')) {
      if (!(await confirmBox('Einzelangebot löschen?', `${esc(ed.nr)} wird gelöscht${ed.status === 'freigegeben' ? ' und verschwindet beim Kunden aus dem Portal' : ''}.`, 'Löschen', true))) return;
      try { await api('einzel_loeschen', { body: { id: ed.id } }); toast(`Einzelangebot ${ed.nr} gelöscht.`); ed = null; dirty = false; render(); } catch (ex) { toast(ex.message); }
    }
  });
  host.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.matches('tr[data-ez]')) { oeffnen(e.target.dataset.ez); return; }
    if (e.target.id === 'ez-kunde') {
      const n = $$('#ez-kunde-list li[data-kid]').length;
      if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
        e.preventDefault();
        if (kq === null) { kq = ''; kAkt = 0; } else if (n) kAkt = (kAkt + (e.key === 'ArrowDown' ? 1 : n - 1)) % n;
        renderKundenListe(); return;
      }
      if (e.key === 'Enter') { e.preventDefault(); const li = $$('#ez-kunde-list li[data-kid]')[kAkt]; if (kq !== null && li) kundeWaehlen(li.dataset.kid); return; }
      if (e.key === 'Escape' && kq !== null) { e.preventDefault(); e.stopPropagation(); kundeSchliessen(); }
    }
  });
  host.addEventListener('focusin', (e) => {
    if (e.target.id === 'ez-kunde' && kq === null) { kq = ''; kAkt = 0; renderKundenListe(); e.target.select(); }
  });
  host.addEventListener('focusout', (e) => {
    if (e.target.id === 'ez-kunde' && !(e.relatedTarget && e.relatedTarget.closest('.ez-kwahl'))) kundeSchliessen();
  });
  host.addEventListener('mousedown', (e) => { if (e.target.closest('#ez-kunde-list')) e.preventDefault(); });   // Fokus bleibt im Suchfeld

  W.views.einzel = () => { idx = null; render(); };
})();
