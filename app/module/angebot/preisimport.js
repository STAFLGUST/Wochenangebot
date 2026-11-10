/* STAFL-Plattform · Angebot · Darstellung der Vorschau „Artikelpreise (CSV)“ in der Importzentrale (Verwaltung → Import).
   Registriert sich als window.WA.importDarstellung.angebot_preise (Vertrag: docs/plattform/schnittstellen/import.md) und
   zeigt die „details“ der Vorschau des Servers (module/angebot/import.php, angebot_preise_ergebnis):
   - Angebotswoche bisher → neu, Kacheln Erhöht / Gesenkt / Neuer Preis / Bitte prüfen (≥ 10 %) / Unverändert · Fehler;
   - Kundengruppen ohne Angebot zum einzelnen Anhaken (Standard: keine) – setzt die Option „gruppen“, der Server rechnet die
     Vorschau neu; angelegt werden die Angebote erst beim Übernehmen;
   - Preisänderungen je Angebot: Suche, Reiter je Angebot, Filter, Tabelle Bisher (durchgestrichen) → Neu mit Änderung in
     € und %; auf dem Handy als Karten. Suche, Reiter und Filter ändern nur die Liste (keine neue Anfrage).
   Rechnet nichts, was gespeichert wird – übernommen wird ausschließlich, was der Server aus der Datei ermittelt (GR-103).
   Wird von admin/index.html nach admin-import.js geladen; Gestaltung in preisimport.css. */
(function () {
  'use strict';
  const W = window.WA;
  if (!W) return;
  const { esc, fmtInt } = W;
  const euro = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 4 });
  const proz = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const SEITE = 300;   // Preiszeilen je Schritt („Weitere anzeigen“) – die Liste bleibt auch bei großen Dateien flüssig
  const FILTER = [['alle', 'Alle Änderungen'], ['hoch', 'Erhöht'], ['runter', 'Gesenkt'], ['neu', 'Neuer Preis'], ['pruefen', 'Bitte prüfen']];
  const anz = (n, eins, viele) => `${fmtInt.format(n)} ${n === 1 ? eins : viele}`;
  const PFEIL = {
    hoch: '<svg aria-hidden="true" width="10" height="10" viewBox="0 0 12 12"><path d="M6 2 11 9H1Z" fill="currentColor"/></svg>',
    runter: '<svg aria-hidden="true" width="10" height="10" viewBox="0 0 12 12"><path d="M6 10 11 3H1Z" fill="currentColor"/></svg>',
    neu: '<svg aria-hidden="true" width="10" height="10" viewBox="0 0 12 12"><path d="M6 1v10M1 6h10" stroke="currentColor" stroke-width="2"/></svg>',
    pruefen: '<svg aria-hidden="true" width="12" height="12" viewBox="0 0 12 12"><path d="M6 1 11 11H1Z" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M6 5v2.5" stroke="currentColor" stroke-width="1.6"/></svg>',
  };

  /* Zeile der Details [Artikelnummer, Artikel, bisher|null, neu, Dateizeile, prüfen 1/0] → Anzeige */
  function zeile(r) {
    const [code, name, alt, neu, nr, pruefen] = r;
    const art = alt === null ? 'neu' : neu > alt ? 'hoch' : 'runter';
    let diff = 'bisher ohne Preis';
    if (art !== 'neu') {
      const vz = art === 'hoch' ? '+' : '−';
      diff = `${vz}${euro.format(Math.abs(neu - alt))} €${alt > 0 ? ` · ${vz}${proz.format(Math.abs(neu - alt) / alt * 100)} %` : ''}`;
    }
    return { code, name, alt, neu, nr, pruefen: !!pruefen, art, diff };
  }
  const passt = (z, f) => f === 'alle' || (f === 'pruefen' ? z.pruefen : z.art === f);

  function zustand(ctx) {
    const z = ctx.zustand;
    if (!z.filter) Object.assign(z, { filter: 'alle', angebot: 'alle', suche: '', anzahl: SEITE });
    if (z.angebot !== 'alle' && !ctx.details.angebote.some((a) => a.id === z.angebot)) z.angebot = 'alle';   // z. B. Gruppe abgewählt
    return z;
  }

  /* ---------- Kopf: Angebotswoche und Kacheln ---------- */
  function wocheHTML(w) {
    const neu = `<b>${esc(w.neu)}</b>`;
    const t = !w.alt ? `Angebotswoche wird ${neu}.` : w.alt === w.neu ? `Angebotswoche bleibt ${neu}.` : `Entwurf bisher ${esc(w.alt)} → wird ${neu}.`;
    return `<p class="pi-woche" id="pi-woche">${t} Eingetragen wird in den Entwurf – Kunden sehen die Preise erst nach „Veröffentlichen“ im Angebotseditor. Preise, die nicht in der Datei stehen, bleiben unverändert.</p>`;
  }
  function kachelnHTML(k, fehler) {
    const kachel = (id, cls, label, wert, extra = '') => `<div class="pi-kachel ${cls}${wert ? ' hat' : ''}"><span>${PFEIL[cls] || ''}${label}</span><strong id="pi-${id}">${fmtInt.format(wert)}${extra}</strong></div>`;
    return `<section class="pi-kacheln" aria-label="Zusammenfassung">
      ${kachel('hoch', 'hoch', 'Erhöht', k.hoch)}${kachel('runter', 'runter', 'Gesenkt', k.runter)}${kachel('neu', 'neu', 'Neuer Preis', k.neu)}
      ${kachel('pruefen', 'pruefen', 'Bitte prüfen (≥ 10 %)', k.pruefen)}
      <div class="pi-kachel gleich"><span>Unverändert · Fehler</span><strong id="pi-gleich">${fmtInt.format(k.unveraendert)} <small>· ${anz(fehler, 'Fehler', 'Fehler')}</small></strong></div>
    </section>`;
  }
  /* Fehlerhafte Zeilen (Leser und Server) – aufklappbar, werden nicht übernommen */
  function fehlerHTML(list) {
    if (!list.length) return '';
    return `<details class="pi-karte pi-fehler" id="pi-fehler"><summary>${anz(list.length, 'fehlerhafte Zeile', 'fehlerhafte Zeilen')} – ${list.length === 1 ? 'wird' : 'werden'} nicht übernommen</summary>
      <ul>${list.slice(0, 200).map((x) => `<li><span class="pi-dz">${x.zeile != null ? 'Zeile ' + fmtInt.format(x.zeile) : '—'}</span>${x.schluessel ? `<span class="pi-nr">${esc(x.schluessel)}</span>` : ''}<span>${esc(x.text)}</span></li>`).join('')}</ul>
      ${list.length > 200 ? `<p class="hint">Angezeigt werden die ersten 200.</p>` : ''}</details>`;
  }

  /* ---------- Kundengruppen ohne Angebot: einzeln anhaken ---------- */
  function gruppenHTML(d, ctx) {
    if (!d.ohne.length) return '';
    const wahl = new Set(ctx.optionen.gruppen || []);
    const n = d.ohne.filter((g) => wahl.has(g.nr)).length;
    return `<section class="pi-karte pi-gruppen" aria-labelledby="pi-gruppen-titel">
      <div class="pi-karte-kopf">
        <div><h3 id="pi-gruppen-titel">Kundengruppen ohne Angebot</h3>
          <p>Für jede angehakte Gruppe wird beim Übernehmen ein eigenes Angebot mit eigener Artikelliste angelegt. Nicht angehakte Gruppen bleiben ohne Angebot – ihre Preise werden nicht übernommen.</p></div>
        <div class="pi-wahl"><span id="pi-gewaehlt" role="status">${ctx.aktualisiert ? 'Vorschau wird aktualisiert …' : `${fmtInt.format(n)} von ${fmtInt.format(d.ohne.length)} ausgewählt`}</span>
          <button type="button" class="btn sm" data-pi-alle${n === d.ohne.length ? ' disabled' : ''}>Alle</button><button type="button" class="btn sm" data-pi-keine${n ? '' : ' disabled'}>Keine</button></div>
      </div>
      ${d.zuViele ? `<p class="pi-warn" role="alert">${PFEIL.pruefen}${esc(d.zuViele)}</p>` : ''}
      <ul class="pi-gliste">${d.ohne.map((g) => {
        const an = wahl.has(g.nr);
        const status = !an ? 'Preise werden nicht übernommen' : d.zuViele ? 'Wird nicht angelegt – zu viele Angebote' : `Neues Angebot „${g.angebot}“ wird angelegt`;
        return `<li class="${an ? (d.zuViele ? 'an zu' : 'an') : ''}"><input type="checkbox" id="pi-g-${esc(g.nr)}" data-pi-gruppe="${esc(g.nr)}"${an ? ' checked' : ''}>
          <label for="pi-g-${esc(g.nr)}"><b>Gruppe ${esc(g.nr)}${g.name ? ' · ' + esc(g.name) : ''}</b></label>
          <span class="pi-anz">${anz(g.preise, 'Preis', 'Preise')}</span><span class="pi-status">${esc(status)}</span></li>`;
      }).join('')}</ul>
    </section>`;
  }

  /* ---------- Preisänderungen je Angebot ---------- */
  function listeHTML(d, z) {
    const q = W.SU.woerter(z.suche);
    let rest = z.anzahl, mehr = 0, treffer = 0;
    const teile = [];
    for (const a of d.angebote) {
      if (z.angebot !== 'alle' && z.angebot !== a.id) continue;
      const rows = [];
      for (const r of a.zeilen) {
        const x = zeile(r);
        if (!passt(x, z.filter) || !W.SU.findet(q, x.code, x.name)) continue;
        treffer++;
        if (rest-- > 0) rows.push(x); else mehr++;
      }
      if (!rows.length) continue;
      const info = [a.gruppen, a.hoch && `${fmtInt.format(a.hoch)} erhöht`, a.runter && `${fmtInt.format(a.runter)} gesenkt`, a.neu && anz(a.neu, 'neuer Preis', 'neue Preise')].filter(Boolean).join(' · ');
      teile.push(`<tbody data-pi-ang="${esc(a.id)}"><tr class="pi-ang"><th colspan="6" scope="colgroup"><b>${esc(a.name)}</b><span>${esc(info)}</span></th></tr>
        ${rows.map((x) => `<tr class="pi-z ${x.art}${x.pruefen ? ' pruefen' : ''}" data-pi-art="${x.art}">
          <td class="pi-nr">${esc(x.code)}</td>
          <td class="pi-name">${esc(x.name)}${x.nr != null ? `<span class="pi-dz">Zeile ${fmtInt.format(x.nr)}</span>` : ''}</td>
          <td class="pi-alt">${x.alt === null ? '<span class="pi-ohne">–</span>' : `<s>${euro.format(x.alt)}</s>`}</td>
          <td class="pi-neu">${euro.format(x.neu)}</td>
          <td class="pi-diff"><span class="pi-pill ${x.art}">${PFEIL[x.art]}${esc(x.diff)}</span></td>
          <td class="pi-hinw">${x.pruefen ? `<span class="pi-pruefen">${PFEIL.pruefen}Bitte prüfen</span>` : ''}</td></tr>`).join('')}</tbody>`);
    }
    if (!treffer) return '<p class="pi-leer">Keine Preise in dieser Auswahl.</p>';
    return `<table class="pi-tab"><thead><tr><th scope="col">Art.-Nr.</th><th scope="col">Artikel</th><th scope="col" class="r">Bisher €/kg</th><th scope="col" class="r">Neu €/kg</th><th scope="col" class="r">Änderung</th><th scope="col">Hinweis</th></tr></thead>${teile.join('')}</table>
      ${mehr ? `<div class="pi-mehr"><button type="button" class="btn" data-pi-mehr>Weitere ${fmtInt.format(Math.min(mehr, SEITE))} anzeigen</button><span>noch ${fmtInt.format(mehr)} von ${fmtInt.format(treffer)}</span></div>` : ''}
      ${d.gekuerzt ? `<p class="hint">Angezeigt werden die ersten ${fmtInt.format(d.angebote.reduce((s, a) => s + a.zeilen.length, 0))} Preisänderungen; ${fmtInt.format(d.gekuerzt)} weitere werden ebenfalls übernommen. Die Zahlen oben zählen alle.</p>` : ''}`;
  }
  function aenderungenHTML(d, z) {
    const k = d.kpi;
    const alle = k.hoch + k.runter + k.neu;
    if (!alle) return `<section class="pi-karte" aria-labelledby="pi-aend-titel"><h3 id="pi-aend-titel">Preisänderungen je Angebot</h3><p class="pi-leer">Keine Preisänderungen – alle Preise der Datei sind bereits eingetragen.</p></section>`;
    const zahl = { alle, hoch: k.hoch, runter: k.runter, neu: k.neu, pruefen: k.pruefen };
    const tabs = [{ id: 'alle', name: 'Alle Angebote', n: alle }].concat(d.angebote.map((a) => ({ id: a.id, name: a.name, n: a.hoch + a.runter + a.neu })));
    return `<section class="pi-karte" aria-labelledby="pi-aend-titel">
      <div class="pi-karte-kopf"><h3 id="pi-aend-titel">Preisänderungen je Angebot</h3>
        <label class="pi-suche"><svg aria-hidden="true" width="16" height="16" viewBox="0 0 16 16"><circle cx="7" cy="7" r="5" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="m11 11 3.5 3.5" stroke="currentColor" stroke-width="1.6"/></svg>
          <input type="search" data-pi-suche placeholder="Artikel oder Nummer suchen" aria-label="Artikel oder Nummer suchen" value="${esc(z.suche)}" autocomplete="off"></label></div>
      ${tabs.length > 2 ? `<div class="pi-tabs" role="group" aria-label="Angebot">${tabs.map((t) => `<button type="button" data-pi-angebot="${esc(t.id)}" aria-pressed="${z.angebot === t.id}">${esc(t.name)} <span>${fmtInt.format(t.n)}</span></button>`).join('')}</div>` : ''}
      <div class="seg txt pi-filter" role="group" aria-label="Filter">${FILTER.map(([id, label]) => `<button type="button" data-pi-filter="${id}" aria-pressed="${z.filter === id}"${id !== 'alle' && !zahl[id] ? ' disabled' : ''}>${label} <span>${fmtInt.format(zahl[id])}</span></button>`).join('')}</div>
      <div id="pi-liste" class="pi-liste">${listeHTML(d, z)}</div>
    </section>`;
  }

  /* ---------- Vertrag mit der Importzentrale ---------- */
  function html(ctx) {
    const d = ctx.details;
    if (!d || !d.kpi || !Array.isArray(d.angebote) || !Array.isArray(d.ohne)) throw new Error('Unbekanntes Format der Vorschau');   // dann einheitliche Vorschau
    const z = zustand(ctx);
    return `<div class="pi" data-pi>
      ${wocheHTML(d.woche || {})}
      ${kachelnHTML(d.kpi, ctx.zahlen.fehler || 0)}
      ${ctx.hinweiseHTML((ctx.leserHinweise || []).concat(d.hinweise || []))}
      ${fehlerHTML(ctx.fehler || [])}
      ${gruppenHTML(d, ctx)}
      ${aenderungenHTML(d, z)}
    </div>`;
  }
  function binden(root, ctx) {
    const box = root.querySelector('[data-pi]');
    if (!box) return;
    const d = ctx.details, z = ctx.zustand;
    const liste = () => {
      const l = box.querySelector('#pi-liste');
      if (l) l.innerHTML = listeHTML(d, z);
      box.querySelectorAll('[data-pi-angebot]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.piAngebot === z.angebot)));
      box.querySelectorAll('[data-pi-filter]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.piFilter === z.filter)));
    };
    const gruppen = (list, fokus) => { z.fokus = fokus; ctx.setzen('gruppen', list); };
    box.addEventListener('change', (e) => {
      const g = e.target.closest('[data-pi-gruppe]');
      if (!g) return;
      const wahl = new Set(ctx.optionen.gruppen || []);
      if (g.checked) wahl.add(g.dataset.piGruppe); else wahl.delete(g.dataset.piGruppe);
      gruppen(d.ohne.map((x) => x.nr).filter((nr) => wahl.has(nr)), `[data-pi-gruppe="${g.dataset.piGruppe}"]`);
    });
    box.addEventListener('click', (e) => {
      const b = e.target.closest('button');
      if (!b || b.disabled) return;
      if ('piAlle' in b.dataset) gruppen(d.ohne.map((x) => x.nr), '[data-pi-keine]');
      else if ('piKeine' in b.dataset) gruppen([], '[data-pi-alle]');
      else if ('piAngebot' in b.dataset) { z.angebot = b.dataset.piAngebot; z.anzahl = SEITE; liste(); }
      else if ('piFilter' in b.dataset) { z.filter = b.dataset.piFilter; z.anzahl = SEITE; liste(); }
      else if ('piMehr' in b.dataset) { z.anzahl += SEITE; liste(); }
    });
    const suche = box.querySelector('[data-pi-suche]');
    if (suche) suche.addEventListener('input', () => { z.suche = suche.value; z.anzahl = SEITE; liste(); });
    if (z.fokus) { box.querySelector(z.fokus)?.focus({ preventScroll: true }); if (!ctx.aktualisiert) z.fokus = null; }
  }

  W.importDarstellung = W.importDarstellung || {};
  W.importDarstellung.angebot_preise = { html, binden };
})();
