/* ==========================================================================
   Eingabebereich – Fenster „Artikel hinzufügen“ (gemeinsam für „Angebot bearbeiten“ und Einzelangebote)
   Links die VK-Gruppen (mit Anzahl), rechts die Artikel der gewählten Gruppe als Tabelle mit Häkchen, eingelagertem
   und erwartetem Bestand (mit nächster ETA), kürzestem MHD und Wochenpreis; Details je Artikel (Partien, Ankünfte).
   Die Suche oben findet jederzeit Artikel in allen Gruppen. Mehrere markierte Artikel auf einmal übernehmen.
   Optional (Angebot bearbeiten): Preisfeld je markiertem Artikel und Angabe, in welcher Angebotsgruppe er landet.
   Daten liefert der Server (einzel_artikel(): Stammdaten mit VK-Gruppe, Wochenpreis, Bestand nur mit Recht);
   was übernommen wird, entscheidet der Aufrufer (Rückruf „uebernehmen“). Ein Fenster (#dlg-ez-pick) für alle Aufrufer.
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const { $, esc, icon, plural, fold } = W;
  const dlg = $('#dlg-ez-pick');
  const fmt2 = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtKg = (v) => new Intl.NumberFormat('de-DE', { maximumFractionDigits: 2 }).format(v);
  const dmy = (iso) => { if (!iso) return ''; const [y, m, d] = String(iso).slice(0, 10).split('-'); return `${d}.${m}.${y}`; };
  const dm = (iso) => { if (!iso) return ''; const [, m, d] = String(iso).slice(0, 10).split('-'); return `${d}.${m}.`; };
  /* Schlüssel einer Artikelnummer: führende Nullen zählen nicht, Buchstaben ohne Groß-/Kleinschreibung */
  const key = (c) => { const s = String(c || '').trim(); return /^\d+$/.test(s) ? (s.replace(/^0+/, '') || '0') : s.toUpperCase(); };
  const nat = (x, y) => String(x).localeCompare(String(y), 'de', { numeric: true });
  const COND = { frisch: 'frisch', gefroren: 'gefroren', unbekannt: '' };
  const OHNE_VK = '–';         // Gruppe „ohne VK-Gruppe“
  const ALLE = '*';            // alle Gruppen
  const MAX_ZEILEN = 400;

  const stdText = (p) => (!p ? '<span class="muted">nicht im Angebot</span>' : p.status === 'value' ? fmt2.format(p.value) + ' €' : p.status === 'request' ? 'a. Anfr.' : '–');
  function bestandHTML(a, kurz) {
    if (!a || a.totalKg === undefined) return '<span class="muted">—</span>';
    if (!(a.totalKg > 0)) return '<span class="ez-kein">kein Bestand</span>';
    const t = `Eingelagert ${fmtKg(a.kg)} kg · Erfasst ${fmtKg(a.incomingKg)} kg · Gesamt verfügbar ${fmtKg(a.totalKg)} kg`;
    if (kurz) return `<span class="ez-bst" title="${esc(t)}">${esc(fmtKg(a.totalKg))} kg</span>`;
    return `<span class="ez-bst ez-bst3"><span>Eingelagert <b>${esc(fmtKg(a.kg))} kg</b></span><span>Erfasst <b>${esc(fmtKg(a.incomingKg))} kg</b></span><span>Gesamt verfügbar <b>${esc(fmtKg(a.totalKg))} kg</b></span></span>`;
  }
  /* Nächste erwartete Ankunft (frühestes Datum; ohne Datum: keine Angabe) */
  function naechsteEta(a) {
    const d = (a.incoming || []).map((z) => z.arrival).filter(Boolean).sort();
    return d.length ? d[0] : '';
  }

  /* Aufrufer und Zustand des geöffneten Fensters:
     cfg = { artikel: Map(key → Artikel), meta: { bestand, angebot, ek, vk: Map(nr → {nr, name}) }, titel, sub,
             zustand: {grp, nurBestand, nurAngebot} (bleibt beim Aufrufer erhalten), drin(): Set(key) schon enthalten,
             drinText, angebotText (Filter „nur im …“), preis: null | {titel, vorschlag(a), platzhalter(a), fest(a)?: Text statt Eingabe},
             Artikel optional mit nr (angezeigte Nummer, z. B. '' für Positionen ohne Artikelnummer),
             ziel: null | (a) → Text der Zielgruppe, zielHinweis, fussText, max, maxText, extra: [{id, label, icon}],
             onExtra(id), vorauswahl: [Artikelnummern], q: Suchtext beim Öffnen,
             uebernehmen(liste, preise: Map(key → Eingabe)) → true (schließen) | Fehlertext } */
  let cfg = null;
  const pk = { q: '', sel: new Set(), offen: new Set(), preise: new Map() };
  const z = () => cfg.zustand;
  const vkName = (nr) => { const g = nr && cfg.meta.vk.get(nr); return g && g.name ? g.name : ''; };
  const vkText = (nr) => (nr === OHNE_VK || !nr ? 'ohne VK-Gruppe' : nr + (vkName(nr) ? ' · ' + vkName(nr) : ''));
  const grpVon = (a) => a.vk || OHNE_VK;
  const drinSet = () => (cfg.drin ? cfg.drin() : new Set());
  function passt(a, toks) {
    if (z().nurBestand && !(a.totalKg > 0)) return false;
    if (z().nurAngebot && !a.inOffer) return false;
    if (!toks.length) return true;
    const hay = fold([a.code, a.name, a.origin, a.vk, vkName(a.vk)].join(' '));
    return toks.every((t) => hay.includes(t));
  }
  /* Treffer der Filter/Suche (ohne Gruppenwahl) und Anzahl je Gruppe */
  function pickBasis() {
    const toks = fold(pk.q).split(/\s+/).filter(Boolean);
    const l = [...cfg.artikel.values()].filter((a) => passt(a, toks));
    const n = new Map();
    for (const a of l) n.set(grpVon(a), (n.get(grpVon(a)) || 0) + 1);
    return { l, n };
  }
  /* Angezeigte Artikel: gewählte Gruppe, sonst (bei Suche) alle Gruppen; sortiert nach Gruppe und Artikelnummer */
  function pickZeilen(basis) {
    const g = z().grp || (pk.q.trim() ? ALLE : null);
    if (!g) return null;
    return basis.l.filter((a) => g === ALLE || grpVon(a) === g)
      .sort((a, b) => (!a.vk) - (!b.vk) || nat(a.vk || '', b.vk || '') || nat(a.code, b.code));
  }
  function oeffnen(c) {
    cfg = c;
    if (!cfg.artikel) return;
    pk.sel.clear(); pk.offen.clear(); pk.preise.clear(); pk.q = cfg.q || '';
    if (z().grp && z().grp !== ALLE && z().grp !== OHNE_VK && !cfg.meta.vk.has(z().grp)) z().grp = null;
    if (!cfg.meta.bestand) z().nurBestand = false;
    for (const code of cfg.vorauswahl || []) { const k = key(code); if (cfg.artikel.has(k) && !drinSet().has(k)) pk.sel.add(k); }
    if (pk.q) z().grp = null;
    $('#ez-pick-body').innerHTML = `
      <div class="dlg-head ezp-head">
        <div class="ezp-t"><h2 id="ezp-title">${esc(cfg.titel || 'Artikel hinzufügen')}</h2><p>${cfg.subHTML || esc(cfg.sub || '')}</p></div>
        <div class="search ezp-q">${icon('search')}<input id="ezp-q" type="search" autocomplete="off" placeholder="Artikel in allen Gruppen suchen: Nummer, Bezeichnung, Herkunft …" aria-label="Artikel in allen Gruppen suchen" value="${esc(pk.q)}"></div>
        <div class="ezp-f">${cfg.meta.bestand ? `<label class="check"><input type="checkbox" id="ezp-bestand"${z().nurBestand ? ' checked' : ''}> nur mit Bestand</label>` : ''}<label class="check"><input type="checkbox" id="ezp-angebot"${z().nurAngebot ? ' checked' : ''}> ${esc(cfg.angebotText || 'nur im Wochenangebot')}</label></div>
        <button class="btn icon ghost ezp-x" type="button" data-pick-close aria-label="Schließen">${icon('x')}</button>
      </div>
      <div class="ezp-main">
        <nav class="ezp-nav" aria-label="VK-Gruppen"><div class="ezp-nav-h">VK-Gruppen</div><div id="ezp-grp"></div></nav>
        <label class="ezp-grp-m"><span>VK-Gruppe</span><select id="ezp-grp-sel" aria-label="VK-Gruppe wählen"></select></label>
        <section class="ezp-list" id="ezp-list" aria-live="polite"></section>
      </div>
      <div class="dlg-foot ezp-foot"><div class="ezp-anz" id="ezp-anz"></div><span class="spacer"></span>
        ${(cfg.extra || []).map((x) => `<button type="button" class="btn ghost ezp-extra" data-pick-extra="${esc(x.id)}">${x.icon ? icon(x.icon, 'sm') : ''}${esc(x.label)}</button>`).join('')}
        <button type="button" class="btn" data-pick-close>Abbrechen</button><button type="button" class="btn primary" id="ezp-ok" disabled>${icon('plus')}<span>Hinzufügen</span></button></div>`;
    renderPick();
    if (!dlg.open) dlg.showModal();
    const q = $('#ezp-q'); q.focus(); if (pk.q) q.select();
  }
  function renderPick() { const b = pickBasis(); renderPickNav(b); renderPickList(b); renderPickFoot(); }
  function renderPickNav(basis) {
    const gruppen = [...cfg.meta.vk.values()];
    const ohne = [...cfg.artikel.values()].some((a) => !a.vk);
    const eintrag = (nr, label) => { const n = nr === ALLE ? basis.l.length : basis.n.get(nr) || 0; return { nr, label, n }; };
    const l = [eintrag(ALLE, 'Alle Gruppen'), ...gruppen.map((g) => eintrag(g.nr, g.name || '(ohne Bezeichnung)')), ...(ohne ? [eintrag(OHNE_VK, 'ohne VK-Gruppe')] : [])];
    const akt = z().grp || (pk.q.trim() ? ALLE : null);
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
    const ek = cfg.meta.ek;
    const lots = a.lots || [], inc = a.incoming || [];
    const lotsHTML = lots.length ? `<div class="ez-dtw"><table class="ez-dt"><thead><tr><th>Partie</th><th>Eingang</th><th>MHD</th><th class="num">Kolli</th><th class="num">kg</th>${ek ? '<th class="num">EK €/kg</th>' : ''}</tr></thead><tbody>
        ${lots.map((l) => `<tr><td>${esc(l.lot || '—')}</td><td>${esc(dmy(l.arrival)) || '—'}</td><td>${esc(dmy(l.mhd)) || '—'}</td><td class="num">${l.kolli != null ? esc(fmtKg(l.kolli)) : '—'}</td><td class="num">${esc(fmtKg(l.kg))}</td>${ek ? `<td class="num">${l.ek != null ? esc(fmt2.format(l.ek)) : '—'}</td>` : ''}</tr>`).join('')}</tbody></table></div>`
      : `<p class="hint">${a.kg > 0 ? 'Keine Partiedaten in der Bestandsliste.' : 'Kein eingelagerter Bestand.'}</p>`;
    const incHTML = inc.length ? `<div class="ez-dtw"><table class="ez-dt"><thead><tr><th>Partie</th><th>Ankunft (ETA)</th><th class="num">kg</th></tr></thead><tbody>
        ${inc.map((x) => `<tr><td>${esc(x.lot || '—')}</td><td>${x.arrival ? esc(dmy(x.arrival)) : '<span class="muted">ETA unbekannt</span>'}</td><td class="num">${esc(fmtKg(x.kg))}</td></tr>`).join('')}</tbody></table></div>`
      : '<p class="hint">Keine erwarteten Ankünfte.</p>';
    return kopf + `<div class="ez-det-s">${bestandHTML(a)}${a.mhd ? `<span>kürzestes MHD <b>${esc(dmy(a.mhd))}</b></span>` : ''}</div>
      <div class="ez-det-2"><div><h4>Eingelagerte Partien</h4>${lotsHTML}</div><div><h4>Erwartete Ankünfte</h4>${incHTML}</div></div>`;
  }
  function preisFeld(a, k) {
    if (!cfg.preis) return '';
    const fest = cfg.preis.fest ? cfg.preis.fest(a) : null;   // z. B. Preis eines Artikels, der schon im Angebot steht
    if (fest != null) return `<td class="num ezp-pr"><span class="ezp-fest">${esc(fest)}</span></td>`;
    if (!pk.sel.has(k)) return '<td class="num ezp-pr"><span class="muted">–</span></td>';
    const v = pk.preise.has(k) ? pk.preise.get(k) : cfg.preis.vorschlag(a);
    return `<td class="num ezp-pr"><input class="in num ezp-pin" data-preis="${esc(a.code)}" inputmode="decimal" value="${esc(v)}" placeholder="${esc(cfg.preis.platzhalter ? cfg.preis.platzhalter(a) : '')}" aria-label="Preis für ${esc(a.code)} in Euro je kg"></td>`;
  }
  function renderPickList(basis) {
    const el = $('#ezp-list');
    const zeilen = pickZeilen(basis);
    if (!zeilen) {
      el.innerHTML = `<div class="ezp-start">${icon('tag')}<h3>Zuerst eine VK-Gruppe wählen</h3><p>Links die VK-Gruppe anklicken, dann die Artikel markieren und gesammelt hinzufügen. Über das Suchfeld oben finden Sie jederzeit Artikel aus allen Gruppen.</p></div>`;
      return;
    }
    const drin = drinSet();
    const mitB = !!cfg.meta.bestand;
    const g = z().grp || ALLE;
    const frei = zeilen.filter((a) => !drin.has(key(a.code)));
    const alleMarkiert = frei.length && frei.every((a) => pk.sel.has(key(a.code)));
    const kg = zeilen.reduce((s, a) => s + (a.totalKg || 0), 0);
    const titel = g === ALLE ? (pk.q.trim() ? `Suche „${pk.q.trim()}“ in allen Gruppen` : 'Alle Gruppen') : vkText(g);
    const l = zeilen.slice(0, MAX_ZEILEN);
    let grp = null;
    const cols = (mitB ? 8 : 5) + (cfg.preis ? 1 : 0);
    el.innerHTML = `<div class="ezp-lkopf"><div><h3>${esc(titel)}</h3><p>${plural(zeilen.length, 'Artikel', 'Artikel')}${mitB ? ` · ${esc(fmtKg(Math.round(kg * 100) / 100))} kg verfügbar` : ''}${cfg.meta.bestand ? ` · Bestand vom ${esc(dmy(cfg.meta.bestand.date))}` : ''}${cfg.meta.angebot && cfg.meta.angebot.week ? ` · Wochenpreis KW ${esc(cfg.meta.angebot.week)}` : ''}</p></div>
        ${frei.length ? `<button type="button" class="btn sm" id="ezp-alle" data-alle="${alleMarkiert ? 'aus' : 'an'}">${alleMarkiert ? 'Markierung aufheben' : (g === ALLE ? 'Alle Treffer markieren' : 'Alle dieser Gruppe markieren')}</button>` : ''}</div>
      ${l.length ? `<div class="ezp-tw"><table class="ezp-tab${cfg.preis ? ' mit-preis' : ''}"><thead><tr><th class="ezp-c"><span class="sr-only">Auswahl</span></th><th class="ezp-nr">Art.-Nr.</th><th>Bezeichnung</th>${mitB ? '<th class="num">Eingelagert</th><th class="num ezp-m">Erwartet</th><th class="ezp-m">kürz. MHD</th>' : ''}<th class="num ezp-wp">Wochenpreis</th>${cfg.preis ? `<th class="num ezp-pr">${esc(cfg.preis.titel || 'Preis')}</th>` : ''}<th class="ezp-i"><span class="sr-only">Details</span></th></tr></thead><tbody>
        ${l.map((a) => {
          const k = key(a.code), ist = drin.has(k), sel = pk.sel.has(k), auf = pk.offen.has(k);
          let h = '';
          if (g === ALLE && grpVon(a) !== grp) { grp = grpVon(a); h += `<tr class="ezp-gr"><td colspan="${cols}">${esc(vkText(grp))}</td></tr>`; }
          const merk = [a.origin, COND[a.condition] || ''].filter(Boolean).join(' · ');
          const eta = naechsteEta(a);
          h += `<tr class="ezp-z${sel ? ' sel' : ''}${ist ? ' drin' : ''}${auf ? ' auf' : ''}" data-code="${esc(a.code)}">
            <td class="ezp-c"><input type="checkbox" data-sel="${esc(a.code)}"${sel || ist ? ' checked' : ''}${ist ? ' disabled' : ''} aria-label="${esc(a.code + ' ' + (a.name || ''))} auswählen"></td>
            <td class="ezp-nr">${esc(a.nr !== undefined ? a.nr : a.code)}</td>
            <td class="ezp-n"><span>${esc(a.name || '(ohne Bezeichnung)')}</span>${ist ? ` <span class="ez-tag ezp-drin">${esc(cfg.drinText || 'im Angebot')}</span>` : ''}${merk ? `<small>${esc(merk)}</small>` : ''}
              ${mitB ? `<small class="ezp-mob">${cfg.preis && (a.nr !== undefined ? a.nr : a.code) ? esc(a.nr !== undefined ? a.nr : a.code) + ' · ' : ''}${a.totalKg > 0 ? esc(fmtKg(a.totalKg)) + ' kg verfügbar' : 'kein Bestand'}${cfg.preis && a.stdPrice ? ' · Wochenpreis ' + stdText(a.stdPrice) : ''}</small>` : ''}</td>
            ${mitB ? `<td class="num ezp-kg">${a.kg > 0 ? `<b>${esc(fmtKg(a.kg))} kg</b>` : '<span class="ez-kein">kein Bestand</span>'}</td>
              <td class="num ezp-m">${a.incomingKg > 0 ? esc(fmtKg(a.incomingKg)) + ' kg' + (eta ? `<small class="ezp-eta">ETA ${esc(dm(eta))}</small>` : '') : '<span class="muted">–</span>'}</td>
              <td class="ezp-m">${a.mhd ? esc(dmy(a.mhd)) : '<span class="muted">–</span>'}</td>` : ''}
            <td class="num ezp-p">${a.stdPrice ? stdText(a.stdPrice) : '<span class="muted" title="nicht im Wochenangebot">–</span>'}</td>
            ${preisFeld(a, k)}
            <td class="ezp-i"><button type="button" class="ibtn" data-info="${esc(a.code)}" aria-expanded="${auf}" aria-label="Details zu ${esc(a.code)}" title="Partien, Bestand, Ankünfte">${icon('info', 'sm')}</button></td></tr>`;
          if (auf) h += `<tr class="ezp-det" data-det="${esc(a.code)}"><td colspan="${cols}">${detailHTML(a)}</td></tr>`;
          return h;
        }).join('')}</tbody></table></div>` : '<p class="hint ezp-leer">Keine Artikel – Filter oder Suche anpassen.</p>'}
      ${zeilen.length > l.length ? `<p class="hint">… ${zeilen.length - l.length} weitere – Suche eingrenzen.</p>` : ''}`;
    spannen();
  }
  /* Gruppen- und Detailzeilen überspannen nur die sichtbaren Spalten: auf dem Handy blendet das Stylesheet Spalten aus –
     ein zu großes colspan erzeugt sonst leere Spalten, die der Bezeichnung (feste Tabellenbreite) den Platz nehmen */
  function spannen() {
    const t = $('#ezp-list .ezp-tab');
    if (!t) return;
    const n = [...t.tHead.rows[0].cells].filter((c) => getComputedStyle(c).display !== 'none').length;
    for (const td of t.querySelectorAll('tr.ezp-gr > td, tr.ezp-det > td')) td.colSpan = n;
  }
  addEventListener('resize', () => { if (cfg && dlg.open) spannen(); });
  const gewaehlt = () => [...cfg.artikel.values()].filter((a) => pk.sel.has(key(a.code)) && !drinSet().has(key(a.code)))
    .sort((a, b) => (!a.vk) - (!b.vk) || nat(a.vk || '', b.vk || '') || nat(a.code, b.code));
  function renderPickFoot(fehler) {
    const n = pk.sel.size;
    const zuviel = cfg.max != null && n > cfg.max;
    let ziele = '';
    if (n && cfg.ziel) {
      const pro = new Map();
      for (const a of gewaehlt()) { const t = cfg.ziel(a); pro.set(t, (pro.get(t) || 0) + 1); }
      ziele = `<span class="ezp-ziele">${[...pro].map(([t, k]) => `<span class="ezp-ziel">${icon('list', 'sm')}${esc(t)}${k > 1 ? ` (${k})` : ''}</span>`).join('')}</span>`;
    }
    $('#ezp-anz').innerHTML = (n ? `<b>${plural(n, 'Artikel', 'Artikel')} ausgewählt</b>${cfg.ziel ? (n === 1 ? ' – landet in:' : ' – landen in:') : ''}${ziele}${cfg.fussText ? ' · ' + esc(cfg.fussText) : ''}${zuviel ? ` · <span class="st-err">${esc(cfg.maxText || '')}</span>` : ''}`
      : esc(cfg.leerText || 'Artikel markieren, um sie hinzuzufügen.'))
      + (cfg.zielHinweis ? `<small class="ezp-zh">${esc(cfg.zielHinweis)}</small>` : '')
      + (fehler ? `<span class="st-err ezp-err" role="alert">${esc(fehler)}</span>` : '');
    const ok = $('#ezp-ok');
    ok.disabled = !n || zuviel;
    ok.querySelector('span').textContent = n ? `${plural(n, 'Artikel', 'Artikel')} ${cfg.okVerb || 'hinzufügen'}` : (cfg.okLeer || 'Hinzufügen');
  }
  function pickUebernehmen() {
    const neuL = gewaehlt();
    if (!neuL.length || (cfg.max != null && neuL.length > cfg.max)) return;
    for (const inp of dlg.querySelectorAll('[data-preis]')) pk.preise.set(key(inp.dataset.preis), inp.value);
    const preise = new Map(neuL.map((a) => [key(a.code), pk.preise.has(key(a.code)) ? pk.preise.get(key(a.code)) : (cfg.preis ? cfg.preis.vorschlag(a) : '')]));
    const r = cfg.uebernehmen(neuL, preise);
    if (r === true) dlg.close();
    else if (typeof r === 'string') renderPickFoot(r);
  }
  function pickGruppe(g) {
    z().grp = g || null; pk.offen.clear();
    const b = pickBasis(); renderPickNav(b); renderPickList(b);
    const lst = $('#ezp-list'); if (lst) lst.scrollTop = 0;
  }
  /* Preisfelder behalten ihre Eingabe beim Neuzeichnen (Gruppenwechsel, Suche) */
  function preiseMerken() { for (const inp of dlg.querySelectorAll('[data-preis]')) pk.preise.set(key(inp.dataset.preis), inp.value); }
  dlg.addEventListener('input', (e) => {
    if (!cfg) return;
    if (e.target.id === 'ezp-q') {
      preiseMerken();
      if (!pk.q.trim() && e.target.value.trim()) z().grp = null;   // neue Suche gilt für alle Gruppen; per Klick auf eine Gruppe eingrenzen
      pk.q = e.target.value; pk.offen.clear(); const b = pickBasis(); renderPickNav(b); renderPickList(b);
    }
    if (e.target.dataset.preis !== undefined) {
      pk.preise.set(key(e.target.dataset.preis), e.target.value);
      if ($('#ezp-anz .ezp-err')) renderPickFoot();   // Hinweis auf unlesbaren Preis verschwindet bei neuer Eingabe
    }
  });
  dlg.addEventListener('change', (e) => {
    if (!cfg) return;
    const t = e.target;
    if (t.id === 'ezp-bestand') { preiseMerken(); z().nurBestand = t.checked; renderPick(); return; }
    if (t.id === 'ezp-angebot') { preiseMerken(); z().nurAngebot = t.checked; renderPick(); return; }
    if (t.id === 'ezp-grp-sel') { preiseMerken(); pickGruppe(t.value); return; }
    if (t.dataset.sel !== undefined) {
      const k = key(t.dataset.sel);
      if (t.checked) pk.sel.add(k); else pk.sel.delete(k);
      const tr = t.closest('tr'); if (tr) tr.classList.toggle('sel', t.checked);
      if (cfg.preis && tr) {   // Preisfeld der Zeile ein-/ausblenden, ohne die Liste neu zu zeichnen
        const a = cfg.artikel.get(k), td = tr.querySelector('td.ezp-pr');
        if (a && td) { const tmp = document.createElement('tr'); tmp.innerHTML = preisFeld(a, k); td.replaceWith(tmp.firstElementChild); }
        const inp = t.checked && tr.querySelector('[data-preis]'); if (inp && !inp.value) inp.focus();
      }
      renderPickFoot();
      const b = pickBasis(), zl = pickZeilen(b) || [], drin = drinSet(), frei = zl.filter((a) => !drin.has(key(a.code)));
      const btn = $('#ezp-alle');
      if (btn) { const alle = frei.length && frei.every((a) => pk.sel.has(key(a.code))); btn.dataset.alle = alle ? 'aus' : 'an'; btn.textContent = alle ? 'Markierung aufheben' : ((z().grp || ALLE) === ALLE ? 'Alle Treffer markieren' : 'Alle dieser Gruppe markieren'); }
    }
  });
  dlg.addEventListener('keydown', (e) => {   // Enter im Preisfeld: nächstes Preisfeld, im letzten übernehmen
    if (e.key !== 'Enter' || e.target.dataset.preis === undefined) return;
    e.preventDefault();
    const alle = [...dlg.querySelectorAll('[data-preis]')], i = alle.indexOf(e.target);
    if (alle[i + 1]) { alle[i + 1].focus(); alle[i + 1].select(); } else pickUebernehmen();
  });
  dlg.addEventListener('click', (e) => {
    if (!cfg) return;
    const t = e.target;
    if (t.closest('[data-pick-close]')) { dlg.close(); return; }
    const x = t.closest('[data-pick-extra]');
    if (x) { preiseMerken(); if (cfg.onExtra) cfg.onExtra(x.dataset.pickExtra, gewaehlt()); return; }
    const g = t.closest('[data-grp]');
    if (g) { preiseMerken(); pickGruppe(g.dataset.grp); return; }
    const info = t.closest('[data-info]');
    if (info) {
      preiseMerken();
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
      preiseMerken();
      const drin = drinSet(), zl = pickZeilen(pickBasis()) || [];
      for (const a of zl) if (!drin.has(key(a.code))) { if (alle.dataset.alle === 'an') pk.sel.add(key(a.code)); else pk.sel.delete(key(a.code)); }
      const lst = $('#ezp-list'), top = lst.scrollTop;
      renderPickList(pickBasis()); renderPickFoot();
      lst.scrollTop = top;
      return;
    }
    if (t.closest('#ezp-ok')) { pickUebernehmen(); return; }
    // Klick auf die Zeile (außer Knöpfe/Häkchen/Preisfeld) wählt den Artikel
    const zr = t.closest('tr.ezp-z');
    if (zr && !t.closest('input, button')) { const c = zr.querySelector('[data-sel]'); if (c && !c.disabled) { c.checked = !c.checked; c.dispatchEvent(new Event('change', { bubbles: true })); } }
  });
  dlg.addEventListener('close', () => { if (cfg && cfg.onClose) cfg.onClose(); });

  W.artikelwahl = { oeffnen, key, stdText, bestandHTML, schliessen: () => { if (dlg.open) dlg.close(); } };
})();
