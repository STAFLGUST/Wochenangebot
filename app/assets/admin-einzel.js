/* ==========================================================================
   Wochenangebot – Eingabebereich, Einzelangebote (Angebot je Kunde)
   Kunde über eine Suche wählen (Firma, Kundennummer, Ort, Ansprechpartner …). Artikel über das gemeinsame Fenster
   „Artikel hinzufügen“ (admin-artikelwahl.js): VK-Gruppen links, Artikel mit Bestand, ETA, MHD und Wochenpreis rechts,
   Suche über alle Gruppen, mehrere markierte Artikel auf einmal übernehmen.
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
  const fmt2 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtKg = (v) => new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 }).format(v);
  const dmy = (iso) => { if (!iso) return ''; const [y, m, d] = String(iso).slice(0, 10).split('-'); return `${d}.${m}.${y}`; };
  const key = (c) => { const s = String(c || '').trim(); return /^\d+$/.test(s) ? (s.replace(/^0+/, '') || '0') : s.toUpperCase(); };
  /* Zahl aus deutscher Eingabe: „1.234,5“ (Tausenderpunkte) oder „12,5“. Ohne Komma gilt ein Punkt als Dezimalzeichen
     („0.125“ = 0,125; Preis „12.345“ = 12,345 wie im Wochenangebot) – nur bei Mengen ist „1.200“ = 1200 kg. */
  const zahl = (v, art) => {
    let t = String(v ?? '').trim().replace(/\s/g, '');
    if (t === '') return null;
    const tausend = t.includes(',') ? /^[1-9]\d{0,2}(\.\d{3})+,\d+$/.test(t) : art === 'qty' && /^[1-9]\d{0,2}(\.\d{3})+$/.test(t);
    t = tausend ? t.replace(/\./g, '').replace(',', '.') : t.replace(',', '.');
    const n = /^\d+(\.\d+)?$/.test(t) ? Number(t) : NaN;
    return Number.isFinite(n) ? n : NaN;
  };
  const pText = (v) => (v == null || Number.isNaN(v) ? '' : v.toFixed(2).replace('.', ','));
  const zText = (v) => (v == null ? '' : String(Math.round(v * 100) / 100).replace('.', ','));
  const STATUS = { entwurf: 'Entwurf', freigegeben: 'Im Portal freigegeben', zurueckgezogen: 'Zurückgezogen' };
  const isoPlus = (days) => { const d = new Date(); d.setDate(d.getDate() + days); return d.toLocaleDateString('sv-SE'); };   // Ortszeit (toISOString wäre UTC)
  const MAX_POS = 300;

  let liste = null, kunden = null, idx = null, idxMeta = null, ed = null, dirty = false, listQ = '', kq = null, kAkt = 0, mailFormat = 'liste';
  const pk = { grp: null, nurBestand: true, nurAngebot: false };   // Auswahlfenster: gewählte VK-Gruppe und Filter bleiben erhalten
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
  const { stdText, bestandHTML } = W.artikelwahl;   // Wochenpreis- und Bestandsanzeige wie im Auswahlfenster

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
        : `<div class="gcard"><table class="etab eztab"><thead><tr><th>Nummer</th><th>Kunde</th><th class="ez-m">Titel</th><th class="num ez-s">Pos.</th><th class="num ez-m">Warenwert</th><th class="ez-s">Gültig bis</th><th>Status</th><th class="ez-m">Geändert</th></tr></thead><tbody>
          ${l.map((e) => `<tr data-ez="${esc(e.id)}" tabindex="0"><td class="ez-nr">${esc(e.nr)}</td><td>${esc(e.firma)}${e.kundeNr ? ` <span class="muted">· ${esc(e.kundeNr)}</span>` : ''}</td><td class="ez-m">${esc(e.titel || '')}</td><td class="num ez-s">${e.positionCount}</td>
            <td class="num ez-m">${e.summen.summe ? esc(fmt2.format(e.summen.summe)) + ' €' : '<span class="muted">–</span>'}</td><td class="ez-s">${e.gueltigBis ? esc(dmy(e.gueltigBis)) : '<span class="muted">offen</span>'}</td>
            <td>${statusChip(e)}${e.gueltigBis ? `<div class="sub ez-bis-m">bis ${esc(dmy(e.gueltigBis))}</div>` : ''}</td><td class="ez-m">${esc(dateTime(e.changed))}<div class="sub">${esc(e.changedBy || '')}</div></td></tr>`).join('')}
        </tbody></table></div>`}`;
  }
  function statusChip(e) {
    const abgelaufen = e.gueltigBis && e.gueltigBis < new Date().toLocaleDateString('sv-SE');
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

  /* ---------- Fenster „Artikel hinzufügen“ (gemeinsames Fenster: admin-artikelwahl.js) ---------- */
  const drinSet = () => new Set(ed.positions.map((p) => key(p.code)));
  function pickOeffnen() {
    if (!idx) return;
    const k = ed.kid ? kunden.get(ed.kid) : null;
    W.artikelwahl.oeffnen({
      artikel: idx, meta: idxMeta, zustand: pk,
      titel: 'Artikel hinzufügen', sub: [ed.nr || 'Neues Einzelangebot', k ? k.firma : ''].filter(Boolean).join(' · '),
      drin: drinSet, drinText: 'im Angebot', angebotText: 'nur im Wochenangebot',
      fussText: 'Preise werden mit dem Wochenpreis vorbelegt',
      max: MAX_POS - ed.positions.length, maxText: `höchstens ${MAX_POS} Positionen je Einzelangebot`,
      uebernehmen(neuL) {
        kopfLesen();
        neuL.forEach(hinzufuegen);
        markDirty(); renderPos();
        toast(`${plural(neuL.length, 'Artikel', 'Artikel')} hinzugefügt.`);
        return true;
      },
    });
  }

  function markDirty() { dirty = true; const d = $('#ez-dirty'); if (d) d.hidden = false; }
  function kopfLesen() {
    if (!$('#ez-titel')) return;
    ed.titel = $('#ez-titel').value.trim(); ed.gueltigBis = $('#ez-bis').value; ed.hinweis = $('#ez-hinweis').value;
  }
  let busy = false;   // Doppelklick auf Speichern/Freigeben: nur eine Anfrage (sonst zwei neue Einzelangebote)
  async function speichern() {
    if (busy) return false;
    kopfLesen();
    const bad = ed.positions.find((p) => Number.isNaN(p.price) || Number.isNaN(p.qty));
    if (bad) { toast(`Bitte Preis bzw. Menge bei „${bad.name}“ prüfen.`); return false; }
    busy = true;
    try {
      const r = await api('einzel_save', { body: { id: ed.id, revision: ed.revision, kid: ed.kid, titel: ed.titel, gueltigBis: ed.gueltigBis, hinweis: ed.hinweis,
        positions: ed.positions.map((p) => ({ code: p.code, name: p.name, qty: p.qty, price: p.price, notiz: p.notiz || '' })) } });
      const fr = ed.fracht;
      ed = r.angebot; ed.fracht = fr; dirty = false;
      liste = null;
      toast(`Einzelangebot ${ed.nr} gespeichert.`);
      renderEditor();
      return true;
    } catch (e) { toast(e.message, 6000); return false; } finally { busy = false; }
  }
  async function status(s) {
    if (busy) return;
    if (dirty && !(await speichern())) return;
    busy = true;
    try { const r = await api('einzel_status', { body: { id: ed.id, revision: ed.revision, status: s } }); const fr = ed.fracht; ed = r.angebot; ed.fracht = fr; toast(s === 'freigegeben' ? 'Im Portal freigegeben – der Kunde sieht das Angebot nach der Anmeldung.' : 'Freigabe beendet.'); renderEditor(); }
    catch (e) { toast(e.message, 6000); } finally { busy = false; }
  }

  /* ---------- Drucken / PDF: wie auf der Angebotsseite (deren Druckdialog, z. B. Angebotsliste A4 quer) ---------- */
  async function drucken() {
    if (!ed.positions.length) { toast('Bitte zuerst Positionen eintragen.'); return; }
    const w = window.open('', '_blank');   // sofort im Klick öffnen, sonst blockiert der Browser das Fenster nach dem Speichern
    if (!w) { toast('Das Druckfenster wurde vom Browser blockiert. Bitte Pop-ups für diese Seite erlauben.'); return; }
    try { w.document.write('<!doctype html><meta charset="utf-8"><title>Angebot wird vorbereitet …</title><p style="font:14px sans-serif;padding:24px">Angebot wird vorbereitet …</p>'); } catch { /* geschlossen */ }
    if ((dirty || !ed.id) && !(await speichern())) { w.close(); return; }
    if (w.closed) return;
    // index.html statt „../“: auf angebot.dashboard-stafl.de leitet „/“ in den Eingabebereich um (siehe angebotsseite in admin.js)
    w.location.href = new URL('../index.html?angebot=e-' + encodeURIComponent(ed.id) + '&drucken=1', location.href).href;
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
    if (['ez-titel', 'ez-bis', 'ez-hinweis'].includes(t.id)) { kopfLesen(); markDirty(); return; }   // sofort übernehmen, sonst gehen Eingaben beim Neuzeichnen verloren
    const tr = t.closest('tr[data-i]');
    if (tr && t.dataset.f) {
      const p = ed.positions[+tr.dataset.i];
      if (t.dataset.f === 'name' || t.dataset.f === 'notiz') p[t.dataset.f] = t.value;
      else {
        const v = zahl(t.value, t.dataset.f);
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

  W.views.einzel = () => { idx = null; kunden = null; render(); };   // Kunden neu laden (neue Kunden, geänderte E-Mail-Adressen)
  window.addEventListener('beforeunload', (e) => { if (ed && dirty) { e.preventDefault(); e.returnValue = ''; } });
})();
