/* ==========================================================================
   Wochenangebot – Eingabebereich, Einzelangebote (Angebot je Kunde)
   Artikel frei suchen (Stammdaten, Bestand, Wochenangebot) mit eingelagertem, erfasstem und gesamt verfügbarem
   Bestand sowie dem Wochenangebotspreis zum Vergleich; Abweichung des eigenen Preises als farbiger Punkt.
   Speichern, im Portal freigeben, drucken (PDF) und per E-Mail senden. Server: app/api/aktionen/einzelangebote.php
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

  let liste = null, kunden = null, idx = null, idxMeta = null, ed = null, dirty = false, q = '', listQ = '', nurBestand = false, nurAngebot = false;
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
    idxMeta = { bestand: r.bestand, angebot: r.angebot };
  }

  async function render() {
    if (!liste) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Einzelangebote werden geladen …</div>';
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
  function kundenOptionen() {
    const l = [...kunden.values()].sort((a, b) => a.firma.localeCompare(b.firma, 'de'));
    return `<option value="">– Kunde wählen –</option>` + l.map((c) => `<option value="${esc(c.id)}"${c.id === ed.kid ? ' selected' : ''}>${esc(c.firma)}${c.nr ? ' · ' + esc(c.nr) : ''}${c.ort ? ' · ' + esc(c.ort) : ''}</option>`).join('');
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
            <label class="fld span2"><span>Kunde</span><select id="ez-kunde"${ro ? ' disabled' : ''}>${kundenOptionen()}</select></label>
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
          <div class="search">${icon('search')}<input id="ez-q" type="search" autocomplete="off" placeholder="Nummer oder Bezeichnung …" aria-label="Artikel suchen" value="${esc(q)}"></div>
          <div class="ez-filter"><label class="check"><input type="checkbox" id="ez-f-bestand"${nurBestand ? ' checked' : ''}> nur mit Bestand</label><label class="check"><input type="checkbox" id="ez-f-angebot"${nurAngebot ? ' checked' : ''}> nur im Wochenangebot</label></div>
          <p class="hint">${idxMeta && idxMeta.bestand ? `Bestand vom ${esc(dmy(idxMeta.bestand.date))}` : 'Kein Bestand geladen'}${idxMeta && idxMeta.angebot ? ` · Wochenpreis KW ${esc(idxMeta.angebot.week)}/${esc(idxMeta.angebot.year)}` : ''}</p>
          <div id="ez-treffer"></div>
        </aside>`}
      </div>`;
    renderPos();
    if (!ro) renderTreffer();
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
  function renderTreffer() {
    const el = $('#ez-treffer');
    if (!idx) { el.innerHTML = ''; return; }
    const toks = fold(q).split(/\s+/).filter(Boolean);
    const drin = new Set(ed.positions.map((p) => key(p.code)));
    const alle = [...idx.values()].filter((a) => (!nurBestand || a.totalKg > 0) && (!nurAngebot || a.inOffer) && toks.every((t) => fold(a.code + ' ' + a.name).includes(t)));
    const l = alle.slice(0, 60);
    el.innerHTML = (l.length ? `<ul class="ez-list">${l.map((a) => `<li data-code="${esc(a.code)}">
        <div class="ez-li-t"><span class="ez-code">${esc(a.code)}</span> <span class="ez-li-n">${esc(a.name || '(ohne Bezeichnung)')}</span></div>
        <div class="ez-li-d">${bestandHTML(a)}</div>
        <div class="ez-li-d">Wochenpreis: ${stdText(a.stdPrice)}</div>
        <button type="button" class="btn sm" data-add="${esc(a.code)}"${drin.has(key(a.code)) ? ' disabled' : ''}>${drin.has(key(a.code)) ? 'im Angebot' : icon('plus', 'sm') + 'Hinzufügen'}</button></li>`).join('')}</ul>` : '<p class="hint">Kein Artikel gefunden.</p>')
      + (alle.length > l.length ? `<p class="hint">… ${alle.length - l.length} weitere – Suche eingrenzen.</p>` : '')
      + `<button type="button" class="btn sm ghost" id="ez-frei">${icon('plus', 'sm')}Freie Position${q.trim() ? ` „${esc(q.trim().slice(0, 40))}“` : ''}</button>`;
  }
  function markDirty() { dirty = true; const d = $('#ez-dirty'); if (d) d.hidden = false; }
  function kopfLesen() {
    if (!$('#ez-kunde')) return;
    ed.kid = $('#ez-kunde').value; ed.titel = $('#ez-titel').value.trim(); ed.gueltigBis = $('#ez-bis').value; ed.hinweis = $('#ez-hinweis').value;
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
  async function drucken() {
    if (dirty && !(await speichern())) return;
    const k = kunden.get(ed.kid) || {};
    if (!ed.fracht) { try { ed.fracht = (await api('einzel_detail&id=' + encodeURIComponent(ed.id))).fracht; } catch { ed.fracht = []; } }
    const { kg: kgS, sum } = summen();
    const base = location.href.replace(/admin\/.*$/, '');
    const html = `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>${esc(ed.nr)} – ${esc(k.firma || '')}</title><style>
      @page { size: A4; margin: 16mm 16mm 18mm; } body { font: 10.5pt/1.45 -apple-system, "Segoe UI", Helvetica, Arial, sans-serif; color: #111; margin: 0; }
      .kopf { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 2px solid #8c1d2c; padding-bottom: 10px; margin-bottom: 18px; }
      .kopf img { height: 54px; } .abs { font-size: 9pt; color: #555; text-align: right; }
      .adr { min-height: 30mm; margin-bottom: 14px; } .adr .k { font-size: 8pt; color: #777; margin-bottom: 4px; }
      h1 { font-size: 15pt; margin: 0 0 2px; } .meta { color: #555; margin-bottom: 14px; }
      table { width: 100%; border-collapse: collapse; } th { text-align: left; font-size: 8.5pt; color: #555; border-bottom: 1.5px solid #111; padding: 5px 6px; }
      td { padding: 6px; border-bottom: 1px solid #e3e3e0; vertical-align: top; } .r { text-align: right; white-space: nowrap; } .n { font-size: 8.5pt; color: #666; }
      tfoot td { border-bottom: 0; border-top: 1.5px solid #111; font-weight: 600; } .hinweis { margin: 14px 0; white-space: pre-wrap; } .klein { font-size: 8.5pt; color: #555; margin-top: 14px; }
    </style></head><body>
      <div class="kopf"><img src="${esc(base)}assets/logo-standard-fleisch.png" alt="Standard-Fleisch"><div class="abs">Standard-Fleisch<br>Angebot ${esc(ed.nr)}<br>${esc(new Date().toLocaleDateString('de-DE'))}</div></div>
      <div class="adr"><div class="k">Angebot für</div><strong>${esc(k.firma || '')}</strong>${k.ansprechpartner ? '<br>' + esc(k.ansprechpartner) : ''}${k.strasse ? '<br>' + esc(k.strasse) : ''}${k.plz || k.ort ? '<br>' + esc([k.plz, k.ort].filter(Boolean).join(' ')) : ''}${k.nr ? `<br><span class="n">Kundennummer ${esc(k.nr)}</span>` : ''}</div>
      <h1>${esc(ed.titel || 'Angebot ' + ed.nr)}</h1>
      <div class="meta">Angebot ${esc(ed.nr)}${ed.gueltigBis ? ' · gültig bis ' + esc(dmy(ed.gueltigBis)) : ''}</div>
      <table><thead><tr><th>Art.-Nr.</th><th>Artikel</th><th class="r">Menge</th><th class="r">Preis €/kg</th><th class="r">Betrag</th></tr></thead><tbody>
        ${ed.positions.map((p) => `<tr><td>${esc(p.code || '')}</td><td>${esc(p.name)}${p.notiz ? `<div class="n">${esc(p.notiz)}</div>` : ''}</td><td class="r">${p.qty != null ? esc(fmtKg(p.qty)) + ' kg' : ''}</td><td class="r">${p.price != null ? esc(fmt2.format(p.price)) : 'auf Anfrage'}</td><td class="r">${p.qty != null && p.price != null ? esc(fmt2.format(Math.round(Math.round(p.price * 100) * p.qty) / 100)) + ' €' : ''}</td></tr>`).join('')}
      </tbody>${kgS ? `<tfoot><tr><td colspan="2">Summe</td><td class="r">${esc(fmtKg(kgS))} kg</td><td></td><td class="r">${esc(fmt2.format(sum))} €</td></tr></tfoot>` : ''}</table>
      ${ed.hinweis ? `<div class="hinweis">${esc(ed.hinweis)}</div>` : ''}
      <div class="klein">Preise freibleibend, netto; abgerechnet wird nach tatsächlichem Gewicht.${(ed.fracht || []).length ? '<br>' + ed.fracht.map(esc).join('<br>') : ''}</div>
    </body></html>`;
    const w = window.open('', '_blank');
    if (!w) { toast('Das Druckfenster wurde vom Browser blockiert. Bitte Pop-ups für diese Seite erlauben.'); return; }
    w.document.open(); w.document.write(html); w.document.close();
    setTimeout(() => { try { w.focus(); w.print(); } catch { /* Fenster geschlossen */ } }, 400);
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
    if (t.id === 'ez-q') { q = t.value; renderTreffer(); return; }
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
    if (t.id === 'ez-kunde') { kopfLesen(); markDirty(); renderEditor(); return; }
    if (t.id === 'ez-f-bestand') { nurBestand = t.checked; renderTreffer(); return; }
    if (t.id === 'ez-f-angebot') { nurAngebot = t.checked; renderTreffer(); return; }
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
    const add = t.closest('[data-add]');
    if (add) {
      kopfLesen();
      const a = idx.get(key(add.dataset.add));
      ed.positions.push({ code: a.code, name: a.name, qty: null, price: a.stdPrice && a.stdPrice.status === 'value' ? a.stdPrice.value : null, notiz: '' });
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
  host.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.matches('tr[data-ez]')) oeffnen(e.target.dataset.ez); });

  W.views.einzel = () => { idx = null; render(); };
})();
