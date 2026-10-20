/* ==========================================================================
   Wochenangebot – Eingabebereich, Einzelangebote (Angebot je Kunde)
   Kunde über eine Suche wählen (Firma, Kundennummer, Ort, Ansprechpartner …). Artikel frei suchen (Stammdaten, Bestand,
   Wochenangebot), nach VK-Gruppen filtern (mehrere wählbar) und sortieren; Treffer als Tabelle mit gesamt verfügbarem
   Bestand und Wochenpreis, Details je Artikel (Merkmale, Partien mit MHD, erwartete Ankünfte mit ETA). Alle Treffer der
   gewählten VK-Gruppen auf einmal übernehmen. Abweichung des eigenen Preises als farbiger Punkt.
   Speichern, im Portal freigeben, drucken (PDF, mit Logo) und per E-Mail senden. Server: app/api/aktionen/einzelangebote.php
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const { $, $$, api, esc, icon, toast, confirmBox, dateTime, plural, fold, may } = W;
  const host = $('#view-einzel');
  const dlgMail = $('#dlg-einzel-mail');
  const fmt2 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtKg = (v) => new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 }).format(v);
  const dmy = (iso) => { if (!iso) return ''; const [y, m, d] = String(iso).slice(0, 10).split('-'); return `${d}.${m}.${y}`; };
  const key = (c) => { const s = String(c || '').trim(); return /^\d+$/.test(s) ? (s.replace(/^0+/, '') || '0') : s.toUpperCase(); };
  const zahl = (v) => { const t = String(v ?? '').trim().replace(/\s/g, '').replace(/\.(?=\d{3}(\D|$))/g, '').replace(',', '.'); if (t === '') return null; const n = Number(t); return Number.isFinite(n) ? n : NaN; };
  const pText = (v) => (v == null || Number.isNaN(v) ? '' : v.toFixed(2).replace('.', ','));
  const zText = (v) => (v == null ? '' : String(Math.round(v * 100) / 100).replace('.', ','));
  const STATUS = { entwurf: 'Entwurf', freigegeben: 'Im Portal freigegeben', zurueckgezogen: 'Zurückgezogen' };
  const isoPlus = (days) => { const d = new Date(); d.setDate(d.getDate() + days); return d.toISOString().slice(0, 10); };

  const COND = { frisch: 'frisch', gefroren: 'gefroren', unbekannt: '' };
  const OHNE_VK = '–';   // Auswahl „ohne VK-Gruppe“
  const MAX_TREFFER = 200;

  let liste = null, kunden = null, idx = null, idxMeta = null, ed = null, dirty = false, q = '', listQ = '', nurBestand = false, nurAngebot = false;
  let vkSel = new Set(), vkQ = '', sortBy = 'vk', offen = new Set(), kq = null, kAkt = 0, logoUrl = null;
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
    for (const v of [...vkSel]) if (v !== OHNE_VK && !idxMeta.vk.has(v)) vkSel.delete(v);
  }

  async function render() {
    if (!liste) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Einzelangebote werden geladen …</div>';
    ladeLogo();
    try { await laden(); await ladeIndex(); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    if (ed) renderEditor(); else renderListe();
  }

  /* ---------- Übersicht ---------- */
  function renderListe() {
    const toks = fold(listQ).split(/\s+/).filter(Boolean);
    const l = liste.filter((e) => { const hay = fold([e.nr, e.firma, e.kundeNr, e.titel, STATUS[e.status]].join(' ')); return toks.every((t) => hay.includes(t)); });
    host.innerHTML = `
      <div class="ed-toolbar">
        <div class="search">${icon('search')}<input id="ez-lq" type="search" autocomplete="off" placeholder="Einzelangebote finden: Nummer, Kunde, Titel …" aria-label="Einzelangebote suchen" value="${esc(listQ)}"></div>
        <span class="ed-hint">${plural(l.length, 'Einzelangebot', 'Einzelangebote')}</span>
        ${darf() ? `<button type="button" class="btn primary" id="ez-neu">${icon('plus')}Neues Einzelangebot</button>` : ''}
      </div>
      ${!liste.length ? `<div class="ed-empty"><h3>Noch keine Einzelangebote</h3><p>Ein Einzelangebot gilt für genau einen Kunden: Artikel suchen, Preise und Mengen eintragen, dann im Portal freigeben, drucken oder per E-Mail senden.</p></div>`
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
    dirty = false; q = '';
    renderEditor();
  }
  async function oeffnen(id) {
    try { const r = await api('einzel_detail&id=' + encodeURIComponent(id)); ed = r.angebot; ed.fracht = r.fracht; dirty = false; q = ''; renderEditor(); }
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
    const ro = !darf();
    const k = ed.kid ? kunden.get(ed.kid) : null;
    host.innerHTML = `
      <div class="ez-top">
        <button type="button" class="btn ghost" id="ez-zurueck">${icon('chev', 'ez-back')}Alle Einzelangebote</button>
        <h2>${ed.id ? `Einzelangebot ${esc(ed.nr)}` : 'Neues Einzelangebot'} ${ed.id ? statusChip(ed) : ''}</h2>
        <span class="ez-dirty" id="ez-dirty"${dirty ? '' : ' hidden'}>nicht gespeichert</span>
      </div>
      <div class="ez-grid">
        <section class="ez-main">
          <div class="gcard ez-kopf"><div class="form-grid two">
            <div class="fld span2 ez-kwahl"><span id="ez-kunde-l">Kunde</span><div class="ez-kbox">${icon('search')}<input id="ez-kunde" type="text" role="combobox" aria-autocomplete="list" aria-expanded="false" aria-controls="ez-kunde-list" aria-labelledby="ez-kunde-l" autocomplete="off" spellcheck="false" placeholder="Kunde suchen: Firma, Kundennummer, Ort, Ansprechpartner …" value="${esc(kLabel(k))}"${ro ? ' disabled' : ''}></div><ul id="ez-kunde-list" class="ez-klist" role="listbox" aria-label="Kunden" hidden></ul></div>
            <label class="fld"><span>Titel <small class="muted">(optional)</small></span><input id="ez-titel" maxlength="120" value="${esc(ed.titel || '')}" placeholder="${esc(k ? 'Angebot für ' + k.firma : 'z. B. Angebot Grillsaison')}"${ro ? ' disabled' : ''}></label>
            <label class="fld"><span>Gültig bis</span><input id="ez-bis" type="date" value="${esc(ed.gueltigBis || '')}"${ro ? ' disabled' : ''}></label>
            <label class="fld span2"><span>Hinweis an den Kunden <small class="muted">(optional, erscheint im Angebot)</small></span><textarea id="ez-hinweis" rows="2" maxlength="1000"${ro ? ' disabled' : ''}>${esc(ed.hinweis || '')}</textarea></label>
          </div>${k ? `<p class="hint ez-kinfo">${esc([k.ansprechpartner, k.strasse, [k.plz, k.ort].filter(Boolean).join(' '), k.email].filter(Boolean).join(' · '))}${k.login && k.login.active ? '' : ' · <span class="st-warn">kein Portal-Zugang – Freigabe im Portal sieht der Kunde erst mit Zugang</span>'}</p>` : ''}</div>
          <div class="gcard ez-pos"><div id="ez-pos"></div></div>
          <div class="ez-actions">
            ${ro ? '' : `<button type="button" class="btn primary" id="ez-save">${icon('check')}Speichern</button>`}
            ${ro || !ed.id ? '' : ed.status === 'freigegeben' ? `<button type="button" class="btn" id="ez-entfreigeben">${icon('undo')}Freigabe beenden</button>` : `<button type="button" class="btn" id="ez-freigeben">${icon('eye')}Im Portal freigeben</button>`}
            <button type="button" class="btn" id="ez-druck"${ed.positions.length ? '' : ' disabled'}>${icon('print')}Drucken / PDF</button>
            ${ro || !ed.id ? '' : `<button type="button" class="btn" id="ez-mail">${icon('mail')}Per E-Mail senden</button>`}
            ${ro || !ed.id ? '' : `<span class="sp"></span><button type="button" class="btn ghost" id="ez-del" style="color:var(--accent)">${icon('trash', 'sm')}Löschen</button>`}
          </div>
          ${ed.id ? `<p class="hint ez-verlauf">Angelegt ${esc(dateTime(ed.created))} von ${esc(ed.createdBy || '')} · geändert ${esc(dateTime(ed.changed))}${ed.status === 'freigegeben' && ed.freigegebenAt ? ` · im Portal seit ${esc(dateTime(ed.freigegebenAt))}` : ''}${(ed.gesendet || []).length ? ' · per E-Mail: ' + ed.gesendet.slice(-3).map((g) => `${esc(dateTime(g.t))} an ${esc(g.to)}${g.ok ? '' : ' (nicht zugestellt)'}`).join(', ') : ''}</p>` : ''}
        </section>
        ${ro ? '' : `<aside class="ez-suche gcard">
          <h3 class="d-h"><span>Artikel suchen</span></h3>
          <div class="search">${icon('search')}<input id="ez-q" type="search" autocomplete="off" placeholder="Nummer, Bezeichnung oder Herkunft …" aria-label="Artikel suchen" value="${esc(q)}"></div>
          <div class="ez-tools">
            <div class="ez-vk"><button type="button" class="btn sm ez-vk-btn" id="ez-vk" aria-haspopup="dialog" aria-expanded="false" aria-controls="ez-vk-pop"></button>
              <div class="ez-vk-pop" id="ez-vk-pop" role="dialog" aria-label="VK-Gruppen wählen" hidden></div></div>
            <label class="ez-sort"><span>Sortierung</span><select id="ez-sort" aria-label="Sortierung">${[['vk', 'VK-Gruppe'], ['code', 'Art.-Nr.'], ['name', 'Bezeichnung'], ['bestand', 'Verfügbar']].map(([v, t]) => `<option value="${v}"${sortBy === v ? ' selected' : ''}>${t}</option>`).join('')}</select></label>
          </div>
          <div class="ez-vk-chips" id="ez-vk-chips"></div>
          <div class="ez-filter"><label class="check"><input type="checkbox" id="ez-f-bestand"${nurBestand ? ' checked' : ''}> nur mit Bestand</label><label class="check"><input type="checkbox" id="ez-f-angebot"${nurAngebot ? ' checked' : ''}> nur im Wochenangebot</label></div>
          <p class="hint">${idxMeta && idxMeta.bestand ? `Bestand vom ${esc(dmy(idxMeta.bestand.date))}` : 'Kein Bestand geladen'}${idxMeta && idxMeta.angebot ? ` · Wochenpreis KW ${esc(idxMeta.angebot.week)}/${esc(idxMeta.angebot.year)}` : ''}</p>
          <div id="ez-treffer"></div>
        </aside>`}
      </div>`;
    renderPos();
    if (!ro) { renderVk(); renderTreffer(); }
  }
  function renderPos() {
    const ro = !darf();
    const el = $('#ez-pos');
    if (!ed.positions.length) { el.innerHTML = `<div class="ez-leer">${icon('box')}<p>${ro ? 'Keine Positionen.' : 'Noch keine Positionen – rechts Artikel suchen und hinzufügen.'}</p></div>`; return; }
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
  /* ---------- Artikelsuche: VK-Gruppen, Tabelle, Details ---------- */
  const vkName = (nr) => { const g = nr && idxMeta && idxMeta.vk.get(nr); return g && g.name ? g.name : ''; };
  const vkText = (nr) => (nr === OHNE_VK || !nr ? 'ohne VK-Gruppe' : nr + (vkName(nr) ? ' · ' + vkName(nr) : ''));
  /* Treffer ohne VK-Filter (für die Anzahl je Gruppe) bzw. mit */
  function passt(a, toks) {
    if (nurBestand && !(a.totalKg > 0)) return false;
    if (nurAngebot && !a.inOffer) return false;
    if (!toks.length) return true;
    const hay = fold([a.code, a.name, a.origin, a.vk, vkName(a.vk)].join(' '));
    return toks.every((t) => hay.includes(t));
  }
  const vkPasst = (a) => !vkSel.size || vkSel.has(a.vk || OHNE_VK);
  function treffer() {
    const toks = fold(q).split(/\s+/).filter(Boolean);
    const l = [...idx.values()].filter((a) => vkPasst(a) && passt(a, toks));
    const nat = (x, y) => String(x).localeCompare(String(y), 'de', { numeric: true });
    const cmp = {
      code: (a, b) => nat(a.code, b.code),
      name: (a, b) => (a.name || '').localeCompare(b.name || '', 'de') || nat(a.code, b.code),
      bestand: (a, b) => (b.totalKg || 0) - (a.totalKg || 0) || nat(a.code, b.code),
      vk: (a, b) => (!a.vk) - (!b.vk) || nat(a.vk || '', b.vk || '') || nat(a.code, b.code),
    }[sortBy] || ((a, b) => nat(a.code, b.code));
    return l.sort(cmp);
  }
  /* Knopf, Auswahlfenster und Chips der VK-Gruppen */
  function renderVk() {
    const btn = $('#ez-vk'), chips = $('#ez-vk-chips');
    if (!btn || !idx) return;
    btn.innerHTML = `${icon('tag', 'sm')}VK-Gruppen: ${vkSel.size ? `<b>${vkSel.size} gewählt</b>` : 'alle'}${icon('chev', 'sm')}`;
    chips.innerHTML = [...vkSel].map((v) => `<span class="ez-chip">${esc(vkText(v))}<button type="button" data-vk-weg="${esc(v)}" aria-label="${esc(vkText(v))} entfernen" title="Entfernen">${icon('x', 'sm')}</button></span>`).join('');
    chips.hidden = !vkSel.size;
    const pop = $('#ez-vk-pop');
    if (!pop.hidden) renderVkPop();
  }
  function renderVkPop() {
    const pop = $('#ez-vk-pop');
    const toks = fold(q).split(/\s+/).filter(Boolean);
    const n = new Map();
    for (const a of idx.values()) if (passt(a, toks)) n.set(a.vk || OHNE_VK, (n.get(a.vk || OHNE_VK) || 0) + 1);
    const gt = fold(vkQ).split(/\s+/).filter(Boolean);
    const gruppen = [...idxMeta.vk.values()].filter((g) => gt.every((t) => fold(g.nr + ' ' + (g.name || '')).includes(t)));
    const ohne = [...idx.values()].some((a) => !a.vk) && gt.every((t) => fold('ohne vk-gruppe').includes(t));
    const zeile = (nr, label) => { const k = n.get(nr) || 0; return `<label class="check ez-vk-z${k ? '' : ' leer'}"><input type="checkbox" data-vk="${esc(nr)}"${vkSel.has(nr) ? ' checked' : ''}><span class="ez-vk-t">${label}</span><span class="ez-vk-n">${k}</span></label>`; };
    const ae = document.activeElement, hatFokus = ae && ae.id === 'ez-vk-q', fokVk = ae && ae.dataset && ae.dataset.vk;
    pop.innerHTML = `<div class="ez-vk-kopf"><div class="search">${icon('search')}<input id="ez-vk-q" type="search" autocomplete="off" placeholder="VK-Gruppe suchen, z. B. Rind Argentinien" aria-label="VK-Gruppe suchen" value="${esc(vkQ)}"></div>
        <div class="ez-vk-akt">${gruppen.length > 1 ? `<button type="button" class="btn sm ghost" id="ez-vk-alle">Gefundene wählen</button>` : ''}<button type="button" class="btn sm ghost" id="ez-vk-keine"${vkSel.size ? '' : ' disabled'}>Auswahl aufheben</button></div></div>
      <div class="ez-vk-liste">${gruppen.map((g) => zeile(g.nr, `<b>${esc(g.nr)}</b> ${esc(g.name || '(ohne Bezeichnung)')}`)).join('')}${ohne ? zeile(OHNE_VK, '<i>ohne VK-Gruppe</i>') : ''}
        ${!gruppen.length && !ohne ? `<p class="hint">${idxMeta.vk.size ? 'Keine VK-Gruppe gefunden.' : 'Den Artikeln sind noch keine VK-Gruppen zugeordnet (Stammdaten → Artikelstammdaten).'}</p>` : ''}</div>
      <p class="hint ez-vk-fuss">Zahl = Treffer mit den übrigen Filtern.</p>`;
    if (hatFokus) { const i = $('#ez-vk-q'); i.focus(); i.setSelectionRange(vkQ.length, vkQ.length); }
    else if (fokVk !== undefined) { const c = pop.querySelector(`[data-vk="${CSS.escape(fokVk)}"]`); if (c) c.focus(); }
  }
  function vkPopAuf(auf) {
    const pop = $('#ez-vk-pop'), btn = $('#ez-vk');
    if (!pop) return;
    pop.hidden = !auf; btn.setAttribute('aria-expanded', String(auf));
    if (!auf) vkQ = '';   // Gruppensuche beim nächsten Öffnen leer
    if (auf) { renderVkPop(); $('#ez-vk-q').focus(); }
  }
  function verfuegbarHTML(a) {
    if (!a || a.totalKg === undefined) return '<span class="muted">—</span>';
    if (!(a.totalKg > 0)) return '<span class="ez-kein">kein Bestand</span>';
    return `<b class="ez-bst">${esc(fmtKg(a.totalKg))} kg</b>${a.incomingKg > 0 ? `<span class="ez-erw">davon ${esc(fmtKg(a.incomingKg))} kg erwartet</span>` : ''}`;
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
      <h4>Eingelagerte Partien</h4>${lotsHTML}<h4>Erwartete Ankünfte</h4>${incHTML}`;
  }
  function renderTreffer() {
    const el = $('#ez-treffer');
    if (!idx) { el.innerHTML = ''; return; }
    const drin = new Set(ed.positions.map((p) => key(p.code)));
    const alle = treffer();
    const l = alle.slice(0, MAX_TREFFER);
    const neu = alle.filter((a) => !drin.has(key(a.code)));
    let grp = null;
    const zeilen = l.map((a) => {
      const k = key(a.code), auf = offen.has(k), ist = drin.has(k);
      let h = '';
      if (sortBy === 'vk' && (a.vk || OHNE_VK) !== grp) {
        grp = a.vk || OHNE_VK;
        const anz = alle.filter((x) => (x.vk || OHNE_VK) === grp).length;
        h += `<tr class="ez-grp"><td colspan="4">${esc(vkText(grp))} <span class="muted">· ${anz}</span></td></tr>`;
      }
      h += `<tr class="ez-art${auf ? ' auf' : ''}" data-code="${esc(a.code)}">
        <td class="ez-tt-a"><span class="ez-code">${esc(a.code)}</span><span class="ez-li-n">${esc(a.name || '(ohne Bezeichnung)')}</span></td>
        <td class="num ez-tt-v">${verfuegbarHTML(a)}</td>
        <td class="num ez-tt-p">${a.stdPrice ? stdText(a.stdPrice) : '<span class="muted" title="nicht im Wochenangebot">–</span>'}</td>
        <td class="ez-tt-b"><button type="button" class="ibtn" data-info="${esc(a.code)}" aria-expanded="${auf}" aria-label="Details zu ${esc(a.code)}" title="Partien, Bestand, Ankünfte">${icon('info', 'sm')}</button><button type="button" class="btn sm" data-add="${esc(a.code)}"${ist ? ' disabled' : ''} aria-label="${ist ? 'bereits im Angebot' : esc(a.code) + ' hinzufügen'}" title="${ist ? 'bereits im Angebot' : 'Hinzufügen'}">${ist ? icon('check', 'sm') : icon('plus', 'sm')}</button></td></tr>`;
      if (auf) h += `<tr class="ez-det" data-det="${esc(a.code)}"><td colspan="4">${detailHTML(a)}</td></tr>`;
      return h;
    }).join('');
    el.innerHTML = `<div class="ez-tr-kopf"><span>${plural(alle.length, 'Artikel', 'Artikel')}</span>${vkSel.size && neu.length ? `<button type="button" class="btn sm" id="ez-alle">${icon('plus', 'sm')}Alle ${neu.length} hinzufügen</button>` : ''}</div>`
      + (l.length ? `<table class="ez-tt"><colgroup><col><col class="c-v"><col class="c-p"><col class="c-b"></colgroup><thead><tr><th>Artikel</th><th class="num">Verfügbar</th><th class="num">Wochen&shy;preis</th><th aria-label="Aktionen"></th></tr></thead><tbody>${zeilen}</tbody></table>` : '<p class="hint">Kein Artikel gefunden.</p>')
      + (alle.length > l.length ? `<p class="hint">… ${alle.length - l.length} weitere – Suche eingrenzen.</p>` : '')
      + `<button type="button" class="btn sm ghost" id="ez-frei">${icon('plus', 'sm')}Freie Position${q.trim() ? ` „${esc(q.trim().slice(0, 40))}“` : ''}</button>`;
  }
  function hinzufuegen(a) {
    ed.positions.push({ code: a.code, name: a.name, qty: null, price: a.stdPrice && a.stdPrice.status === 'value' ? a.stdPrice.value : null, notiz: '' });
  }
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

  /* ---------- Drucken / PDF ---------- */
  /* Logo als data:-Adresse vorladen: das Druckfenster (about:blank) zeigt es dann sofort, gedruckt wird erst nach dem Laden */
  function ladeLogo() {
    if (logoUrl) return Promise.resolve(logoUrl);
    return fetch(new URL('../assets/logo-standard-fleisch.png', location.href), { credentials: 'same-origin' })
      .then((r) => (r.ok ? r.blob() : Promise.reject(new Error(String(r.status)))))
      .then((b) => new Promise((res) => { const fr = new FileReader(); fr.onload = () => res((logoUrl = String(fr.result))); fr.onerror = () => res(null); fr.readAsDataURL(b); }))
      .catch(() => null);
  }
  const bilderGeladen = (doc) => Promise.all([...doc.images].map((i) => (i.complete && i.naturalWidth ? null
    : new Promise((r) => { i.addEventListener('load', r, { once: true }); i.addEventListener('error', r, { once: true }); setTimeout(r, 4000); }))));
  async function drucken() {
    // Fenster sofort im Klick öffnen (sonst blockiert der Browser es nach dem Speichern), Inhalt folgt
    const w = window.open('', '_blank');
    if (!w) { toast('Das Druckfenster wurde vom Browser blockiert. Bitte Pop-ups für diese Seite erlauben.'); return; }
    try { w.document.write('<!doctype html><meta charset="utf-8"><title>Angebot wird vorbereitet …</title><p style="font:14px sans-serif;padding:24px">Angebot wird vorbereitet …</p>'); } catch { /* geschlossen */ }
    if (dirty && !(await speichern())) { w.close(); return; }
    const k = kunden.get(ed.kid) || {};
    const logo = (await ladeLogo()) || new URL('../assets/logo-standard-fleisch.png', location.href).href;
    if (!ed.fracht) { try { ed.fracht = (await api('einzel_detail&id=' + encodeURIComponent(ed.id))).fracht; } catch { ed.fracht = []; } }
    const { kg: kgS, sum } = summen();
    const html = `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>${esc(ed.nr)} – ${esc(k.firma || '')}</title><style>
      @page { size: A4; margin: 16mm 16mm 18mm; } body { font: 10.5pt/1.45 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #111; margin: 0; }
      .kopf { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #8c1d2c; padding-bottom: 10px; margin-bottom: 18px; }
      .kopf img { height: 54px; width: auto; display: block; } .abs { font-size: 9pt; color: #555; text-align: right; }
      .adr { min-height: 30mm; margin-bottom: 14px; } .adr .k { font-size: 8pt; color: #777; margin-bottom: 4px; }
      h1 { font-size: 15pt; margin: 0 0 2px; } .meta { color: #555; margin-bottom: 14px; }
      table { width: 100%; border-collapse: collapse; } th { text-align: left; font-size: 8.5pt; color: #555; border-bottom: 1.5px solid #111; padding: 5px 6px; }
      td { padding: 6px; border-bottom: 1px solid #e3e3e0; vertical-align: top; } .r { text-align: right; white-space: nowrap; } .n { font-size: 8.5pt; color: #666; }
      tfoot td { border-bottom: 0; border-top: 1.5px solid #111; font-weight: 600; } .hinweis { margin: 14px 0; white-space: pre-wrap; } .klein { font-size: 8.5pt; color: #555; margin-top: 14px; }
    </style></head><body>
      <div class="kopf"><img src="${esc(logo)}" alt="Standard-Fleisch" width="170" height="54"><div class="abs">Standard-Fleisch<br>Angebot ${esc(ed.nr)}<br>${esc(new Date().toLocaleDateString('de-DE'))}</div></div>
      <div class="adr"><div class="k">Angebot für</div><strong>${esc(k.firma || '')}</strong>${k.ansprechpartner ? '<br>' + esc(k.ansprechpartner) : ''}${k.strasse ? '<br>' + esc(k.strasse) : ''}${k.plz || k.ort ? '<br>' + esc([k.plz, k.ort].filter(Boolean).join(' ')) : ''}${k.nr ? `<br><span class="n">Kundennummer ${esc(k.nr)}</span>` : ''}</div>
      <h1>${esc(ed.titel || 'Angebot ' + ed.nr)}</h1>
      <div class="meta">Angebot ${esc(ed.nr)}${ed.gueltigBis ? ' · gültig bis ' + esc(dmy(ed.gueltigBis)) : ''}</div>
      <table><thead><tr><th>Art.-Nr.</th><th>Artikel</th><th class="r">Menge</th><th class="r">Preis €/kg</th><th class="r">Betrag</th></tr></thead><tbody>
        ${ed.positions.map((p) => `<tr><td>${esc(p.code || '')}</td><td>${esc(p.name)}${p.notiz ? `<div class="n">${esc(p.notiz)}</div>` : ''}</td><td class="r">${p.qty != null ? esc(fmtKg(p.qty)) + ' kg' : ''}</td><td class="r">${p.price != null ? esc(fmt2.format(p.price)) : 'auf Anfrage'}</td><td class="r">${p.qty != null && p.price != null ? esc(fmt2.format(Math.round(Math.round(p.price * 100) * p.qty) / 100)) + ' €' : ''}</td></tr>`).join('')}
      </tbody>${kgS ? `<tfoot><tr><td colspan="2">Summe</td><td class="r">${esc(fmtKg(kgS))} kg</td><td></td><td class="r">${esc(fmt2.format(sum))} €</td></tr></tfoot>` : ''}</table>
      ${ed.hinweis ? `<div class="hinweis">${esc(ed.hinweis)}</div>` : ''}
      <div class="klein">Preise freibleibend, netto; abgerechnet wird nach tatsächlichem Gewicht.${(ed.fracht || []).length ? '<br>' + ed.fracht.map(esc).join('<br>') : ''}</div>
    </body></html>`;
    if (w.closed) return;
    w.document.open(); w.document.write(html); w.document.close();
    await bilderGeladen(w.document);
    setTimeout(() => { try { w.focus(); w.print(); } catch { /* Fenster geschlossen */ } }, 50);
  }

  /* ---------- E-Mail ---------- */
  async function mailDialog() {
    if (dirty && !(await speichern())) return;
    const k = kunden.get(ed.kid) || {};
    $('#einzel-mail-body').innerHTML = `
      <div class="dlg-head"><div><h2 id="em-title">Angebot ${esc(ed.nr)} per E-Mail senden</h2><p>an ${esc(k.firma || '')}${k.email ? ' · ' + esc(k.email) : ''}</p></div>
        <button class="btn icon ghost" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        ${k.email ? '' : '<p class="hint st-err">Für diesen Kunden ist keine E-Mail-Adresse hinterlegt (Stammdaten → Kunden).</p>'}
        <label class="fld"><span>Persönliche Nachricht <small class="muted">(optional)</small></span><textarea name="note" rows="3" maxlength="1000"></textarea></label>
        <p class="hint">Die E-Mail enthält alle Positionen mit Preisen${ed.gueltigBis ? ', die Gültigkeit' : ''} und – wenn freigegeben und der Kunde einen Zugang hat – den Link ins Portal.${ed.status !== 'freigegeben' ? ' Das Angebot ist noch nicht im Portal freigegeben.' : ''}</p>
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
    try { const r = await api('einzel_senden', { body: { id: ed.id, note: e.target.note.value } }); const fr = ed.fracht; ed = r.angebot; ed.fracht = fr; dlgMail.close(); toast(`Angebot ${ed.nr} per E-Mail gesendet.`); renderEditor(); }
    catch (ex) { $('#em-err').textContent = ex.message; btn.disabled = false; }
  });

  /* ---------- Ereignisse ---------- */
  host.addEventListener('input', (e) => {
    const t = e.target;
    if (t.id === 'ez-lq') { listQ = t.value; renderListe(); $('#ez-lq').focus(); $('#ez-lq').setSelectionRange(listQ.length, listQ.length); return; }
    if (t.id === 'ez-q') { q = t.value; renderTreffer(); if (!$('#ez-vk-pop').hidden) renderVkPop(); return; }
    if (t.id === 'ez-kunde') { kq = t.value; kAkt = 0; renderKundenListe(); return; }
    if (t.id === 'ez-vk-q') { vkQ = t.value; renderVkPop(); return; }
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
  host.addEventListener('change', (e) => {
    const t = e.target;
    if (t.id === 'ez-f-bestand') { nurBestand = t.checked; renderVk(); renderTreffer(); return; }
    if (t.id === 'ez-f-angebot') { nurAngebot = t.checked; renderVk(); renderTreffer(); return; }
    if (t.id === 'ez-sort') { sortBy = t.value; renderTreffer(); return; }
    if (t.dataset.vk !== undefined) { if (t.checked) vkSel.add(t.dataset.vk); else vkSel.delete(t.dataset.vk); renderVk(); renderTreffer(); return; }
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
    if (t.closest('#ez-vk')) { vkPopAuf($('#ez-vk-pop').hidden); return; }
    if (t.closest('#ez-vk-keine')) { vkSel.clear(); renderVk(); renderTreffer(); return; }
    if (t.closest('#ez-vk-alle')) { $$('#ez-vk-pop [data-vk]').forEach((c) => vkSel.add(c.dataset.vk)); renderVk(); renderTreffer(); return; }
    const weg = t.closest('[data-vk-weg]');
    if (weg) { vkSel.delete(weg.dataset.vkWeg); renderVk(); renderTreffer(); return; }
    const info = t.closest('[data-info]');
    if (info) {
      const k = key(info.dataset.info);
      if (offen.has(k)) offen.delete(k); else offen.add(k);
      renderTreffer();
      const b = $(`#ez-treffer [data-info="${CSS.escape(info.dataset.info)}"]`); if (b) b.focus();
      return;
    }
    if (t.closest('#ez-alle')) {
      const drin = new Set(ed.positions.map((p) => key(p.code)));
      const neu = treffer().filter((a) => !drin.has(key(a.code)));
      if (!neu.length) return;
      if (ed.positions.length + neu.length > 300) { toast(`Zu viele Positionen: höchstens 300 je Einzelangebot (jetzt ${ed.positions.length}, dazu ${neu.length}).`, 6000); return; }
      if (neu.length > 25 && !(await confirmBox(`${neu.length} Artikel hinzufügen?`, 'Alle Treffer der gewählten VK-Gruppen werden mit dem Wochenpreis (sonst „auf Anfrage“) übernommen.', 'Hinzufügen'))) return;
      kopfLesen();
      neu.forEach(hinzufuegen);
      markDirty(); renderPos(); renderTreffer();
      toast(`${plural(neu.length, 'Artikel', 'Artikel')} hinzugefügt.`);
      return;
    }
    const add = t.closest('[data-add]');
    if (add) {
      kopfLesen();
      hinzufuegen(idx.get(key(add.dataset.add)));
      markDirty(); renderPos(); renderTreffer();
      const last = $$('#ez-pos tr[data-i] [data-f="price"]').pop(); if (last) last.focus();
      return;
    }
    if (t.closest('#ez-frei')) { kopfLesen(); ed.positions.push({ code: '', name: q.trim() || 'Freie Position', qty: null, price: null, notiz: '' }); markDirty(); renderPos(); return; }
    const del = t.closest('[data-del]');
    if (del) { kopfLesen(); ed.positions.splice(+del.dataset.del, 1); markDirty(); renderPos(); renderTreffer(); return; }
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
      if (e.key === 'Escape' && kq !== null) { e.preventDefault(); e.stopPropagation(); kundeSchliessen(); return; }
    }
    if (e.key === 'Escape' && e.target.closest('#ez-vk-pop')) { e.stopPropagation(); vkPopAuf(false); $('#ez-vk').focus(); }
  });
  host.addEventListener('focusin', (e) => {
    if (e.target.id === 'ez-kunde' && kq === null) { kq = ''; kAkt = 0; renderKundenListe(); e.target.select(); }
  });
  host.addEventListener('focusout', (e) => {
    if (e.target.id === 'ez-kunde' && !(e.relatedTarget && e.relatedTarget.closest('.ez-kwahl'))) kundeSchliessen();
  });
  host.addEventListener('mousedown', (e) => { if (e.target.closest('#ez-kunde-list')) e.preventDefault(); });   // Fokus bleibt im Suchfeld
  document.addEventListener('click', (e) => {
    const pop = $('#ez-vk-pop');
    if (pop && !pop.hidden && !e.target.closest('.ez-vk') && document.contains(e.target)) vkPopAuf(false);
  });

  W.views.einzel = () => { idx = null; render(); };
})();
