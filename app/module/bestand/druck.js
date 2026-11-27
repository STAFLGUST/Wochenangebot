/* STAFL-Plattform · Bestand · Druckfassung der Bestandsliste (Knopf „Drucken“, DIN A4 quer; Inhaber 26.11.2026).
   Abgeschottet von der Bildschirmansicht: Die Druckfassung bekommt nur fertige Werte (Daten unten) und setzt Tabelle und
   Stylesheet selbst – sie nutzt weder Markup noch CSS der Bestandsliste. Änderungen an Liste, Filtern oder admin.css
   ändern den Druck deshalb nicht; geändert wird er nur hier (Prüfung: tests/e2e/test_stock.py, Abschnitt „Druck“).
   Für andere Module: WA.bestand.druck.drucken(daten) öffnet das Druckfenster, WA.bestand.druck.html(daten) liefert das Dokument.
   daten = { titel, preise (false = ohne Preisspalten), kw: { aktuell, vorwoche }, flach, gruppen: [{ titel, zeilen: [Zeile], summe }], gesamt }
     Zeile = { nr, name, merkmale, preis, vorwoche, kg, mhd, stufe ('past'|'0-4'|'5-7'|'8-14'|''), mhdKg, erfasst, eta,
               etaAlt, gesamt, zugaenge: [{ kg, eta, info }] } – alle Werte schon als Text (kg, €, Datum)
     Summe = { titel, kg, mhdKg, erfasst, gesamt }
   Wird von admin/index.html nach admin.js geladen. */
(function () {
  'use strict';
  const W = window.WA;
  if (!W) return;
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

  const CSS = `
    @page { size: A4 landscape; margin: 9mm 9mm 11mm; @bottom-left { content: "intern – nicht zur Weitergabe"; font: 7pt Geist, Arial, sans-serif; color: #77716a; }
            @bottom-right { content: "Seite " counter(page) " von " counter(pages); font: 7pt Geist, Arial, sans-serif; color: #77716a; } }
    * { box-sizing: border-box; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
    body { margin: 0; font: 8.5pt/1.25 Geist, -apple-system, "Segoe UI", Roboto, Arial, sans-serif; color: #1b1a18; }
    h1 { font-size: 12pt; font-weight: 650; margin: 0 0 5px; }
    table { width: 100%; border-collapse: collapse; table-layout: fixed; }
    col.nr { width: 5%; } col.name { width: 19%; } col.preis { width: 5.5%; } col.kg { width: 9%; } col.mhd { width: 6.5%; } col.zu { width: 22.5%; }
    table.ohne-preise col.zu { width: 33.5%; }
    thead { display: table-header-group; }
    th { font-size: 7pt; font-weight: 600; color: #5f5a56; text-align: right; vertical-align: bottom; padding: 0 4px 3px; border-bottom: 1pt solid #1b1a18; }
    th.l { text-align: left; } th.c { text-align: center; }
    td { padding: 2.2px 4px; border-bottom: .4pt solid #dedad5; vertical-align: top; text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
    td.l { text-align: left; } td.c { text-align: center; }
    td.name, td.p { white-space: normal; overflow-wrap: anywhere; }
    .merk { display: block; font-size: 7pt; color: #77716a; }
    .eta { display: block; font-size: 6.5pt; font-weight: 600; color: #5f5a56; } .eta.alt { color: #b45309; }
    td.zu { text-align: left; font-size: 7pt; white-space: normal; color: #3d3935; }
    td.zu span { display: block; overflow-wrap: anywhere; padding-left: 8px; text-indent: -8px; }   /* lange Marken brechen um, Partie bleibt sichtbar */
    tr { break-inside: avoid; }
    tr.gk td { padding-top: 7px; font-weight: 700; font-size: 8.5pt; text-align: left; border-bottom: .8pt solid #1b1a18; break-after: avoid; }
    tr.sum td, tr.gesamt td { font-size: 8pt; }
    tr.sum td { font-weight: 700; background: #f3f1ee; border-bottom: 0; }
    tr.gesamt td { font-weight: 700; background: #ebe8e4; border-top: 1.2pt solid #1b1a18; border-bottom: 0; }
    tr.abstand td { border: 0; height: 4px; padding: 0; }
    .past { background: #dcd8d3; } .s0-4 { background: #fbe0dd; color: #8f1d14; } .s5-7 { background: #fde7d3; color: #7a3209; } .s8-14 { background: #fbf0c9; color: #6b4a05; }
    .past, .s0-4, .s5-7, .s8-14 { font-weight: 700; }
    .legende { display: flex; gap: 10px; margin: 0 0 6px; font-size: 7pt; } .legende span { padding: 1px 5px; }`;

  const stufe = (s) => (s === 'past' ? 'past' : s ? 's' + s : '');
  const zeile = (z, flach, preise) => {
    const m = stufe(z.stufe);
    return `<tr class="z"><td class="l">${esc(z.nr)}</td><td class="l name">${esc(z.name)}${!flach && z.merkmale ? `<span class="merk">${esc(z.merkmale)}</span>` : ''}</td>`
      + `${preise ? `<td class="p">${esc(z.preis)}</td><td class="p">${esc(z.vorwoche)}</td>` : ''}<td>${esc(z.kg)}</td>`
      + `<td class="c ${m}">${esc(z.mhd)}</td><td class="${m}">${z.stufe === 'past' ? '† ' : ''}${esc(z.mhdKg)}</td>`
      + `<td>${esc(z.erfasst)}${z.eta ? `<span class="eta${z.etaAlt ? ' alt' : ''}">ETA ${esc(z.eta)}</span>` : ''}</td><td>${esc(z.gesamt)}</td>`
      + `<td class="zu">${(z.zugaenge || []).map((d) => `<span>${esc(d.kg)} · ${esc(d.eta)}${d.info ? ' · ' + esc(d.info) : ''}</span>`).join('') || '—'}</td></tr>`;
  };
  const summe = (s, cls, preise) => (s ? `<tr class="${cls}"><td class="l" colspan="${preise ? 4 : 2}">${esc(s.titel)}</td><td>${esc(s.kg)}</td><td></td><td>${esc(s.mhdKg)}</td><td>${esc(s.erfasst)}</td><td>${esc(s.gesamt)}</td><td></td></tr>` : '');

  function html(d) {
    const preise = d.preise !== false, sp = preise ? 10 : 8;   // ohne Preisrecht keine Preisspalten (statt „keine Berechtigung“ je Zeile)
    const kopf = `<tr><th class="l">Art.-Nr.</th><th class="l">Bezeichnung</th>${preise ? `<th>Preis<br>${esc(d.kw?.aktuell)}</th><th>Vorwoche<br>${esc(d.kw?.vorwoche)}</th>` : ''}`
      + '<th>Eingelagerter<br>Bestand</th><th class="c">Kürz.<br>MHD</th><th>Menge<br>kürz. MHD</th><th>Erfasster<br>Bestand</th><th>Gesamt<br>verfügbar</th><th class="l">Erwartete Zugänge<br>(kg · ETA · Partie)</th></tr>';
    const body = (d.gruppen || []).map((g, i) => `<tbody>${i && !d.flach ? `<tr class="abstand"><td colspan="${sp}"></td></tr>` : ''}`
      + `${g.titel ? `<tr class="gk"><td colspan="${sp}">${esc(g.titel)}</td></tr>` : ''}${g.zeilen.map((z) => zeile(z, d.flach, preise)).join('')}${summe(g.summe, 'sum', preise)}</tbody>`).join('');
    const schrift = new URL('../assets/fonts/geist-latin-wght-normal.woff2', location.href).href;
    return `<!doctype html><html lang="de"><head><meta charset="utf-8"><title>${esc(d.titel)}</title><style>
      @font-face { font-family: "Geist"; font-weight: 100 900; src: url("${esc(schrift)}") format("woff2"); }${CSS}</style></head>
      <body class="bestand-druck"><h1>${esc(d.titel)}</h1>
      <div class="legende"><span class="past">† MHD abgelaufen</span><span class="s0-4">heute – 4 Tage</span><span class="s5-7">5 – 7 Tage</span><span class="s8-14">8 – 14 Tage</span></div>
      <table${preise ? '' : ' class="ohne-preise"'}><colgroup><col class="nr"><col class="name">${preise ? '<col class="preis"><col class="preis">' : ''}<col class="kg"><col class="mhd"><col class="kg"><col class="kg"><col class="kg"><col class="zu"></colgroup>
      <thead>${kopf}</thead>${body}<tbody>${summe(d.gesamt, 'gesamt', preise)}</tbody></table></body></html>`;
  }

  function drucken(daten) {
    const w = window.open('', '_blank');
    if (!w) { W.toast('Druckfenster wurde blockiert – bitte Pop-ups für diese Seite erlauben.'); return; }
    w.document.write(html(daten));
    w.document.close();
    const los = () => { try { w.focus(); w.print(); } catch { /* Fenster geschlossen */ } };
    setTimeout(() => { try { w.document.fonts.ready.then(los); } catch { los(); } }, 300);   // erst die Schrift, dann der Druckdialog
  }

  W.bestand = W.bestand || {};
  W.bestand.druck = { html, drucken };
})();
