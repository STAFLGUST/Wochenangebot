/* STAFL-Plattform · Controlling · Umsatzstatistik, Reiter „Auswertung“: Umsätze aus der Warenwirtschaft (Import unter
   Verwaltung → Import, Importart „Umsätze je Kunde und Artikel“). Aufbau nach dem Designvorschlag vom 01.11.2026: oben nur
   Zeitraum, „mit Vorjahr“, Knopf „Filter“ (Pop-up mit Vertreter, Kundengruppe, Artikelgruppe, Fleischart, Kunden, Artikel) und
   die Suche nach Kunde, Artikel oder Gruppe; darunter Kennzahlen, die Rangliste (Vertreter, Kundengruppen, Kunden, Artikelgruppen,
   Artikel; weitere Gliederungen nach Fleischart und Zeit) nach Umsatz, Menge, Rohmarge oder Rohmarge % – höchste oder niedrigste
   zuerst (Reihenfolge vom Server, Rohmarge nur mit EK-Recht) –, alle Spalten auf Wunsch, Monatsverlauf und die größten
   Veränderungen zum Vorjahr in der gewählten Kennzahl. Rohmarge = Umsatz mit EK − EK-Wert (früher „DB“). Klick auf eine Zeile oder einen Suchtreffer öffnet die Details im Pop-up (umsatz-details.js) –
   die Seite bleibt stehen. Daten: controlling_umsatz_daten (Stand, Auswahllisten) und controlling_umsatz_auswertung (Summen),
   gerechnet wird auf dem Server. Einkaufswerte und Rohmarge liefert er nur mit controlling.umsatz_ek und
   bestand.einkaufspreise; hier werden sie nur ein- oder ausgeblendet. Beträge in Cent, Mengen in Tausendstel.
   Meldet sich bei controlling.js an (STAFL_CONTROLLING.umsatzAuswertung, Formate in STAFL_CONTROLLING.umsatzFormat). */
'use strict';
(() => {
  const C = window.STAFL_CONTROLLING;
  const esc = C.esc;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];

  /* ---------- Formate (auch für die Pop-ups) ---------- */
  const NF = (d) => new Intl.NumberFormat('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d });
  const euro = (cent) => cent === null || cent === undefined ? '–' : new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(cent / 100);
  const euroKachel = (cent) => (cent !== null && Math.abs(cent) >= 1e10 ? NF(2).format(cent / 1e8) + ' Mio. €' : euro(cent));   // ab 100 Mio. € kurz (voller Wert im Hinweis)
  const euroKurz = (cent) => Math.abs(cent) >= 1e8 ? NF(1).format(cent / 1e8) + ' Mio. €' : Math.abs(cent) >= 1e5 ? NF(0).format(cent / 1e5) + ' Tsd. €' : euro(cent);
  const menge = (milli) => milli === null || milli === undefined ? '–' : NF(Math.abs(milli) < 100000 ? 1 : 0).format(milli / 1000);
  const ganz = (n) => n === null || n === undefined ? '–' : NF(0).format(n);
  const pct = (q) => q === null || !Number.isFinite(q) ? '–' : new Intl.NumberFormat('de-DE', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(q);
  const quote = (a, b) => (b ? a / b : null);
  const preis = (w) => (w && w.menge ? euro(Math.round((w.umsatz / w.menge) * 1000)) : '–');   // € je Mengeneinheit
  const db = (w) => (w && 'ek' in w ? w.umsatzEk - w.ek : null);
  const spanne = (w) => (w && 'ek' in w ? quote(w.umsatzEk - w.ek, w.umsatzEk) : null);
  const MONATSNAMEN = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  const monatsname = (m, kurz = false) => { const n = MONATSNAMEN[Number(m.slice(5, 7)) - 1]; return `${kurz ? n.slice(0, 3) : n} ${kurz ? m.slice(2, 4) : m.slice(0, 4)}`; };
  const tag = (d) => (d ? `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}` : '');
  const plusMonate = (m, n) => { let j = Number(m.slice(0, 4)), mo = Number(m.slice(5, 7)) + n; while (mo < 1) { mo += 12; j--; } while (mo > 12) { mo -= 12; j++; } return `${j}-${String(mo).padStart(2, '0')}`; };
  const delta = (jetzt, vor) => (vor ? (jetzt - vor) / Math.abs(vor) : null);
  const deltaHtml = (jetzt, vor) => {
    const d = delta(jetzt, vor);
    if (d === null) return jetzt && vor === 0 ? '<span class="ctl-ua-delta plus">neu</span>' : '<span class="ctl-ua-delta">–</span>';
    return `<span class="ctl-ua-delta ${d >= 0 ? 'plus' : 'minus'}">${d >= 0 ? '+' : ''}${pct(d)}</span>`;
  };
  /* Veränderung in Prozentpunkten (Rohmarge %) */
  const ppHtml = (jetzt, vor) => {
    if (jetzt === null || vor === null || vor === undefined) return '<span class="ctl-ua-delta">–</span>';
    const d = (jetzt - vor) * 100;
    if (Math.abs(d) < 0.05) return '<span class="ctl-ua-delta">±0,0 Pp</span>';
    return `<span class="ctl-ua-delta ${d >= 0 ? 'plus' : 'minus'}">${d >= 0 ? '+' : '−'}${NF(1).format(Math.abs(d))} Pp</span>`;
  };
  /* Kennzahlen der Ranglisten (Seite und Pop-ups): Wert, Text, Veränderung zum Vorjahr; Rohmarge nur mit EK-Werten */
  const RANG = {
    umsatz: { name: 'Umsatz', wert: (w) => w.umsatz, text: (v) => euro(v), kurz: (v) => euroKurz(v), delta: (w, vj) => deltaHtml(w.umsatz, vj ? vj.umsatz : 0) },
    menge: { name: 'Menge', wert: (w) => w.menge, text: (v) => menge(v), kurz: (v) => menge(v), delta: (w, vj) => deltaHtml(w.menge, vj ? vj.menge : 0) },
    db: { name: 'Rohmarge', ek: true, wert: (w) => db(w), text: (v) => euro(v), kurz: (v) => euroKurz(v), delta: (w, vj) => deltaHtml(db(w), vj ? db(vj) : 0) },
    spanne: { name: 'Rohmarge %', ek: true, wert: (w) => spanne(w), text: (v) => pct(v), kurz: (v) => pct(v), delta: (w, vj) => ppHtml(spanne(w), vj ? spanne(vj) : null) },
  };
  const RANG_ANTEIL_MIN = 0.001, RANG_CENT_MIN = 10000;   // wie der Server: Rohmarge % erst ab 0,1 % des Umsatzes mit EK (mind. 100 €)
  /* Liste nach Kennzahl ordnen (für die Pop-ups; die Rangliste der Seite ordnet der Server); setzt z.klein bei Rohmarge % */
  function rangSortieren(liste, rang, auf) {
    const k = RANG[rang] || RANG.umsatz;
    const schwelle = rang === 'spanne' ? Math.max(RANG_CENT_MIN, Math.round(liste.reduce((s, z) => s + (z.werte.umsatzEk || 0), 0) * RANG_ANTEIL_MIN)) : null;
    return liste.map((z) => ({ ...z, klein: rang === 'spanne' ? (k.wert(z.werte) === null || z.werte.umsatzEk < schwelle) : false }))
      .sort((a, b) => (a.klein - b.klein) || ((x, y) => (auf ? x - y : y - x))(k.wert(a.werte) ?? -Infinity, k.wert(b.werte) ?? -Infinity) || (b.werte.umsatz - a.werte.umsatz) || a.name.localeCompare(b.name, 'de'));
  }
  /* CSV mit Semikolon und BOM (Excel), Zahlen deutsch ohne Tausenderpunkt; Texte, die Excel als Formel lesen würde
     (=, +, @, Tab, „-“ ohne Ziffer), beginnen mit einem Apostroph (CSV-Injection) – negative Zahlen bleiben Zahlen */
  const zahl = (v, d) => (v === null || v === undefined ? '' : NF(d).format(v).replace(/\./g, ''));
  const zelle = (x) => { let s = String(x ?? '').replace(/[\r\n]+/g, ' '); if (/^[=+@\t]/.test(s) || /^-(?![\d,])/.test(s)) s = "'" + s; return `"${s.replace(/"/g, '""')}"`; };
  function csvLaden(datei, zeilen) {
    const text = '\ufeff' + zeilen.map((r) => r.map(zelle).join(';')).join('\r\n') + '\r\n';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
    a.download = datei.replace(/[\\/:*?"<>|]+/g, ' ');
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  /* Monatsbalken (Umsatz, Menge oder DB) mit Vorjahrespunkten als SVG – Seite und Pop-up */
  function monatsSvg(mon, k, mitVj, platz = 360, H = 190) {
    const wertVon = (w) => (!w ? null : k === 'db' ? db(w) : w[k]);
    const werte = mon.map((m) => wertVon(m.werte) || 0), vj = mon.map((m) => (mitVj ? wertVon(m.vj) : null));
    const max = Math.max(1, ...werte.map(Math.abs), ...vj.filter((x) => x !== null).map(Math.abs));
    const W = Math.max(mon.length * 34, Math.round(platz)), unten = 24, oben = 10, hoehe = H - unten - oben, breite = W / mon.length;   // so breit wie die Fläche; bei vielen Monaten waagerecht blättern
    const y = (v) => oben + hoehe - (Math.max(0, v) / max) * hoehe;
    const fmt = k === 'menge' ? menge : euroKurz;
    let svg = `<svg class="ctl-ua-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${k === 'menge' ? 'Menge' : k === 'db' ? 'Deckungsbeitrag' : 'Umsatz'} je Monat${mitVj ? ' mit Vorjahr' : ''}">`;
    mon.forEach((m, i) => {
      const x = i * breite, b = Math.min(56, Math.max(6, breite * 0.56)), v = werte[i];
      svg += `<g><title>${esc(monatsname(m.monat))}: ${esc(fmt(v))}${vj[i] !== null ? ` · Vorjahr ${esc(fmt(vj[i]))}` : ''}</title>`
        + `<rect class="ctl-ua-balken" x="${(x + (breite - b) / 2).toFixed(1)}" y="${y(v).toFixed(1)}" width="${b.toFixed(1)}" height="${(oben + hoehe - y(v)).toFixed(1)}" rx="3"></rect>`
        + (breite >= 26 || i % 2 === 0 ? `<text class="ctl-ua-achse" x="${(x + breite / 2).toFixed(1)}" y="${H - 7}" text-anchor="middle">${esc(breite >= 44 ? monatsname(m.monat, true) : m.monat.endsWith('-01') ? m.monat.slice(0, 4) : MONATSNAMEN[Number(m.monat.slice(5, 7)) - 1].slice(0, 3))}</text>` : '') + '</g>';
    });
    const punkte = vj.map((v, i) => (v === null ? null : `${(i * breite + breite / 2).toFixed(1)},${y(v).toFixed(1)}`)).filter(Boolean);
    if (punkte.length > 1) svg += `<polyline class="ctl-ua-vjlinie" points="${punkte.join(' ')}"></polyline>`;
    punkte.forEach((p) => { const [px, py] = p.split(','); svg += `<circle class="ctl-ua-vjpunkt" cx="${px}" cy="${py}" r="3"></circle>`; });
    return svg + '</svg>';
  }
  const ICON = {
    filter: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M7 12h10M10 18h4"/></svg>',
    suche: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><circle cx="11" cy="11" r="6.5"/><path d="m20 20-4-4"/></svg>',
    weiter: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="m9.5 5.5 6.5 6.5-6.5 6.5"/></svg>',
    zurueck: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="m14.5 5.5-6.5 6.5 6.5 6.5"/></svg>',
    zu: '<svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  };
  C.umsatzFormat = { NF, euro, euroKachel, euroKurz, menge, ganz, pct, quote, preis, db, spanne, monatsname, tag, plusMonate, delta, deltaHtml, ppHtml, RANG, rangSortieren, zahl, csvLaden, monatsSvg, ICON, MONATSNAMEN };

  const OHNE = '_';
  /* Filter: Kennung in der Anfrage → Liste der Grunddaten, Bezeichnung, Merkmal (dim) */
  const FILTER = [
    { id: 'v', liste: 'vertreter', name: 'Vertreter', ohne: 'ohne Vertreter', nach: 'vertreter', hinweis: 'Hauptvertreter des Kunden' },
    { id: 'kg', liste: 'kundengruppen', name: 'Kundengruppe', ohne: 'ohne Kundengruppe', nach: 'kundengruppe' },
    { id: 'ag', liste: 'vkgruppen', name: 'Artikelgruppe', ohne: 'ohne Artikelgruppe', nach: 'vkgruppe', hinweis: 'VK-Gruppe' },
    { id: 'fa', liste: 'fleischarten', name: 'Fleischart', ohne: 'ohne Fleischart', nach: 'fleischart' },
    { id: 'k', liste: 'kunden', name: 'Kunde', suche: true, nach: 'kunde' },
    { id: 'a', liste: 'artikel', name: 'Artikel', suche: true, nach: 'artikel' },
  ];
  const HAUPT = [['vertreter', 'Vertreter'], ['kundengruppe', 'Kundengruppen'], ['kunde', 'Kunden'], ['vkgruppe', 'Artikelgruppen'], ['artikel', 'Artikel']];
  const WEITERE = [['fleischart', 'Fleischart'], ['monat', 'Monat'], ['quartal', 'Quartal'], ['jahr', 'Jahr'], ['kw', 'Kalenderwoche']];
  const ZEITLICH = ['monat', 'quartal', 'jahr', 'kw'];
  const RANG_ANFANG = 50;   // Rangliste: zuerst die 50 umsatzstärksten, Rest auf Klick

  const S = { box: null, g: null, von: '', bis: '', nach: 'kundengruppe', rang: 'umsatz', auf: false, vj: true, filter: {}, sort: null, d: null, laden: 0, kennzahl: 'umsatz', ansicht: 'rang', rangAlle: false,
              eigen: false, entwurf: null, fsuche: {}, treffer: [], aktiv: -1 };
  FILTER.forEach((f) => { S.filter[f.id] = new Set(); S.fsuche[f.id] = ''; });

  const optionen = (f) => {
    const l = S.g.optionen[f.liste] || [];
    const o = f.liste === 'fleischarten' ? l.map((x) => ({ nr: x, name: x })) : l.map((x) => ({ nr: x.nr, name: f.suche ? `${x.name} (${x.nr})` : `${x.nr} – ${x.name}` }));
    return f.ohne ? o.concat([{ nr: OHNE, name: f.ohne }]) : o;
  };
  const optionName = (f, nr) => (optionen(f).find((o) => o.nr === nr) || { name: nr }).name;
  const filterZahl = (filter = S.filter) => FILTER.reduce((n, f) => n + filter[f.id].size, 0);

  /* ---------- Gerüst ---------- */
  function geruest() {
    const monate = S.g.stand.monate;
    const opt = monate.slice().reverse().map((m) => `<option value="${m}">${esc(monatsname(m))}</option>`).join('');
    return `
      <p class="ctl-hilfe ctl-ua-stand" id="ctl-ua-stand"></p>
      <section class="ctl-ua-leiste ctl-glas" aria-label="Zeitraum, Filter und Suche">
        <div class="ctl-seg" role="group" aria-label="Zeitraum" id="ctl-ua-zeit">
          <button type="button" data-zeit="jahr">Dieses Jahr</button><button type="button" data-zeit="vorjahr">Vorjahr</button><button type="button" data-zeit="12">12 Monate</button><button type="button" data-zeit="alles">Alles</button><button type="button" data-zeit="eigen">Eigener Zeitraum</button></div>
        <div class="ctl-ua-eigen" id="ctl-ua-eigen" hidden><label for="ctl-ua-von">Von</label><select id="ctl-ua-von">${opt}</select><label for="ctl-ua-bis">bis</label><select id="ctl-ua-bis">${opt}</select></div>
        <label class="ctl-ua-check"><input type="checkbox" id="ctl-ua-vj" checked> mit Vorjahr</label>
        <button type="button" class="ctl-ua-filterknopf" id="ctl-ua-filterknopf" aria-haspopup="dialog">${ICON.filter}Filter<span class="ctl-ua-zahl" id="ctl-ua-filterzahl" hidden></span></button>
        <div class="ctl-ua-suchfeld">${ICON.suche}
          <input type="search" id="ctl-ua-suche" placeholder="Kunde, Artikel oder Gruppe suchen" aria-label="Kunde, Artikel oder Gruppe suchen – öffnet die Details im Pop-up"
            role="combobox" aria-expanded="false" aria-controls="ctl-ua-treffer" aria-autocomplete="list" autocomplete="off">
          <div class="ctl-ua-treffer" id="ctl-ua-treffer" role="listbox" aria-label="Treffer" hidden></div></div>
        <div class="ctl-ua-chips" id="ctl-ua-chips"></div>
      </section>
      <p class="ctl-fehler" id="ctl-ua-fehler" role="alert" hidden></p>
      <div class="ctl-kpis ctl-ua-kpis" id="ctl-ua-kpis" aria-live="polite"></div>
      <div class="ctl-ua-raster">
        <section class="ctl-panel ctl-glas ctl-ua-rangpanel" aria-labelledby="ctl-ua-titel">
          <div class="ctl-panelkopf ctl-ua-rangkopf"><div><h2 id="ctl-ua-titel">Rangliste</h2><p class="ctl-hilfe" id="ctl-ua-tabelle-hinweis"></p></div>
            <div class="ctl-ua-rangwahl"><div class="ctl-seg" role="group" aria-label="Rangliste nach" id="ctl-ua-nach">${HAUPT.map(([id, n]) => `<button type="button" data-nach="${id}">${esc(n)}</button>`).join('')}</div>
              <label class="ctl-sr" for="ctl-ua-nach-mehr">Weitere Gliederung</label><select id="ctl-ua-nach-mehr"><option value="">Weitere …</option>${WEITERE.map(([id, n]) => `<option value="${id}">${esc(n)}</option>`).join('')}</select></div>
            <div class="ctl-ua-rangwahl ctl-ua-kennzahlwahl"><span class="ctl-ua-wahllabel" id="ctl-ua-rang-label">Sortiert nach</span><div class="ctl-seg" role="group" aria-labelledby="ctl-ua-rang-label" id="ctl-ua-rangnach">${Object.entries(RANG).filter(([, k]) => !k.ek || S.g.rechte.ek).map(([id, k]) => `<button type="button" data-rang="${id}">${esc(k.name)}</button>`).join('')}</div>
              <button type="button" class="ctl-ua-richtung" id="ctl-ua-richtung" aria-pressed="false" title="Reihenfolge umkehren"></button></div></div>
          <div id="ctl-ua-liste" class="ctl-ua-liste"></div>
          <div class="ctl-ua-rangfuss"><div class="ctl-seg klein" role="group" aria-label="Darstellung" id="ctl-ua-ansicht"><button type="button" data-ansicht="rang">Rangliste</button><button type="button" data-ansicht="tabelle">Alle Spalten</button></div>
            <span class="ctl-hilfe" id="ctl-ua-klickhinweis"></span><button type="button" class="btn sm" id="ctl-ua-csv">CSV</button></div>
          <p class="ctl-fussnote" id="ctl-ua-fussnote"></p></section>
        <aside class="ctl-ua-seite">
          <section class="ctl-panel ctl-glas ctl-monatspanel"><div class="ctl-panelkopf"><div><h2>Monatsverlauf</h2><p class="ctl-hilfe" id="ctl-ua-verlauf-hinweis"></p></div>
            <div class="ctl-diagrammfilter"><label class="ctl-visuellabel" for="ctl-ua-kennzahl">Kennzahl</label><select id="ctl-ua-kennzahl"><option value="umsatz">Umsatz</option><option value="menge">Menge</option>${S.g.rechte.ek ? '<option value="db">Rohmarge</option>' : ''}</select></div></div>
            <div class="ctl-diagramm ctl-ua-diagramm" id="ctl-ua-diagramm"></div></section>
          <section class="ctl-panel ctl-glas ctl-ua-veraenderung" id="ctl-ua-veraenderung-panel" hidden><div class="ctl-panelkopf"><div><h2>Größte Veränderungen zum Vorjahr</h2><p class="ctl-hilfe" id="ctl-ua-veraenderung-hinweis"></p></div></div>
            <div id="ctl-ua-veraenderung"></div></section>
        </aside>
      </div>
      <dialog class="modal wide ctl-dialog" id="ctl-ua-filterdialog" aria-labelledby="ctl-ua-f-titel"></dialog>
      <dialog class="modal wide ctl-dialog ctl-dialog-detail" id="ctl-ua-dialog" aria-labelledby="ctl-ua-d-titel"></dialog>`;
  }

  /* ---------- Filter: Chips auf der Seite, Pop-up zum Wählen ---------- */
  function zeichneFilter() {
    const chips = [];
    FILTER.forEach((f) => S.filter[f.id].forEach((nr) => chips.push(`<button type="button" class="ctl-ua-chip aktiv" data-weg="${f.id}" data-wert="${esc(nr)}" title="Filter entfernen">${esc(f.name)}: ${esc(optionName(f, nr))} ×</button>`)));
    $('#ctl-ua-chips', S.box).innerHTML = chips.join('') + (chips.length ? '<button type="button" class="ctl-ua-link" id="ctl-ua-zuruecksetzen">Alle Filter entfernen</button>' : '');
    const n = filterZahl();
    $('#ctl-ua-filterzahl', S.box).hidden = !n; $('#ctl-ua-filterzahl', S.box).textContent = String(n);
    $('#ctl-ua-filterknopf', S.box).classList.toggle('aktiv', n > 0);
  }
  function filterDialog() {
    S.entwurf = {}; FILTER.forEach((f) => { S.entwurf[f.id] = new Set(S.filter[f.id]); S.fsuche[f.id] = ''; });
    const dlg = $('#ctl-ua-filterdialog', S.box);
    dlg.innerHTML = `<div class="dlg"><div class="dlg-head"><div><p class="ctl-eyebrow">Umsatzstatistik</p><h2 id="ctl-ua-f-titel">Filter</h2><p>Gelten für Kennzahlen, Rangliste, Monatsverlauf und die Pop-ups.</p></div>
        <button type="button" class="ctl-rund" data-schliessen aria-label="Schließen">${ICON.zu}</button></div>
      <div class="dlg-body ctl-ua-fbody">${FILTER.map((f) => f.suche ? `<div class="ctl-ua-fgruppe" data-fgruppe="${f.id}"><label class="ctl-ua-flabel" for="ctl-ua-fs-${f.id}">${esc(f.name === 'Kunde' ? 'Kunden' : 'Artikel')} <small>gezielt auswählen</small></label>
          <div class="ctl-ua-token"><span data-tokens="${f.id}"></span><input type="search" id="ctl-ua-fs-${f.id}" data-ftoken="${f.id}" placeholder="Name oder Nummer eingeben …" autocomplete="off"></div><div class="ctl-ua-ftreffer" data-ftreffer="${f.id}"></div></div>`
        : `<fieldset class="ctl-ua-fgruppe" data-fgruppe="${f.id}"><legend class="ctl-ua-flabel">${esc(f.name)}${f.hinweis ? ` <small>${esc(f.hinweis)}</small>` : ''}</legend>
          ${optionen(f).length > 14 ? `<input type="search" class="ctl-ua-fsuche" data-fsuche="${f.id}" placeholder="${esc(f.name)} suchen …" aria-label="${esc(f.name)} suchen">` : ''}<div class="ctl-ua-fchips" data-fchips="${f.id}"></div></fieldset>`).join('')}</div>
      <div class="dlg-foot"><button type="button" class="ctl-ua-link" data-freset>Alles zurücksetzen</button><span class="spacer"></span><button type="button" class="btn" data-schliessen>Abbrechen</button><button type="button" class="btn primary" data-fanwenden id="ctl-ua-fanwenden">Anwenden</button></div></div>`;
    zeichneEntwurf();
    dlg.showModal();
  }
  function zeichneEntwurf() {
    const dlg = $('#ctl-ua-filterdialog', S.box);
    FILTER.forEach((f) => {
      const gew = S.entwurf[f.id], q = S.fsuche[f.id].trim().toLocaleLowerCase('de-DE');
      if (f.suche) {
        $(`[data-tokens="${f.id}"]`, dlg).innerHTML = [...gew].map((nr) => `<span class="ctl-ua-tok">${esc(optionName(f, nr))}<button type="button" data-tokweg="${f.id}" data-wert="${esc(nr)}" aria-label="${esc(optionName(f, nr))} entfernen">×</button></span>`).join('');
        const treffer = q ? optionen(f).filter((o) => !gew.has(o.nr) && o.name.toLocaleLowerCase('de-DE').includes(q)).slice(0, 8) : [];
        $(`[data-ftreffer="${f.id}"]`, dlg).innerHTML = treffer.map((o) => `<button type="button" data-tokdazu="${f.id}" data-wert="${esc(o.nr)}">${esc(o.name)}</button>`).join('')
          + (q && !treffer.length ? '<p class="ctl-hilfe">Keine Treffer.</p>' : '');
      } else {
        $(`[data-fchips="${f.id}"]`, dlg).innerHTML = optionen(f).filter((o) => gew.has(o.nr) || !q || o.name.toLocaleLowerCase('de-DE').includes(q))
          .map((o) => `<button type="button" class="ctl-ua-fchip" aria-pressed="${gew.has(o.nr)}" data-fchip="${f.id}" data-wert="${esc(o.nr)}">${esc(o.name)}</button>`).join('') || '<p class="ctl-hilfe">Keine Treffer.</p>';
      }
    });
    const n = filterZahl(S.entwurf);
    $('#ctl-ua-fanwenden', dlg).textContent = n ? `${n} ${n === 1 ? 'Filter' : 'Filter'} anwenden` : 'Ohne Filter anzeigen';
  }
  function filterVerbinden() {
    const dlg = $('#ctl-ua-filterdialog', S.box);
    dlg.addEventListener('click', (ev) => {
      if (ev.target === dlg || ev.target.closest('[data-schliessen]')) { dlg.close(); return; }
      const c = ev.target.closest('[data-fchip]');
      if (c) { const s = S.entwurf[c.dataset.fchip]; if (s.has(c.dataset.wert)) s.delete(c.dataset.wert); else s.add(c.dataset.wert); zeichneEntwurf(); return; }
      const dazu = ev.target.closest('[data-tokdazu]');
      if (dazu) { S.entwurf[dazu.dataset.tokdazu].add(dazu.dataset.wert); S.fsuche[dazu.dataset.tokdazu] = ''; $(`[data-ftoken="${dazu.dataset.tokdazu}"]`, dlg).value = ''; zeichneEntwurf(); $(`[data-ftoken="${dazu.dataset.tokdazu}"]`, dlg).focus(); return; }
      const weg = ev.target.closest('[data-tokweg]');
      if (weg) { S.entwurf[weg.dataset.tokweg].delete(weg.dataset.wert); zeichneEntwurf(); return; }
      if (ev.target.closest('[data-freset]')) { FILTER.forEach((f) => S.entwurf[f.id].clear()); zeichneEntwurf(); return; }
      if (ev.target.closest('[data-fanwenden]')) { FILTER.forEach((f) => { S.filter[f.id] = new Set(S.entwurf[f.id]); }); dlg.close(); zeichneFilter(); laden(); }
    });
    dlg.addEventListener('input', (ev) => {
      const s = ev.target.closest('[data-fsuche],[data-ftoken]'); if (!s) return;
      S.fsuche[s.dataset.fsuche || s.dataset.ftoken] = s.value; zeichneEntwurf();
    });
    dlg.addEventListener('keydown', (ev) => {
      const s = ev.target.closest('[data-ftoken]');
      if (s && ev.key === 'Enter') { ev.preventDefault(); const t = $(`[data-ftreffer="${s.dataset.ftoken}"] button`, dlg); if (t) t.click(); }
    });
  }
  function anfrage(extra = {}) {
    const p = new URLSearchParams({ von: S.von, bis: S.bis, vj: S.vj ? '1' : '0', ...extra });
    FILTER.forEach((f) => { if (S.filter[f.id].size) p.set(f.id, [...S.filter[f.id]].join(',')); });
    return '&' + p.toString();
  }
  /* Text der aktiven Filter (ohne das Merkmal des Pop-ups) */
  function filterText(ohneDim) {
    const t = [];
    FILTER.forEach((f) => { if (f.nach !== ohneDim && S.filter[f.id].size) t.push(`${f.name} ${[...S.filter[f.id]].map((nr) => optionName(f, nr)).join(', ')}`); });
    return t.length ? 'Filter: ' + t.join(' · ') : '';
  }

  /* ---------- Suche: Kunde, Artikel, Vertreter, Kundengruppe, Artikelgruppe → Pop-up ---------- */
  function suchen(text) {
    const q = text.trim().toLocaleLowerCase('de-DE'), box = $('#ctl-ua-treffer', S.box), feld = $('#ctl-ua-suche', S.box);
    S.treffer = []; S.aktiv = -1;
    if (q.length >= 2 || /^\d+$/.test(q)) {
      const passt = (s) => s.toLocaleLowerCase('de-DE').includes(q);
      const art = [['kunden', 'kunde', 'Kunde', 8], ['artikel', 'artikel', 'Artikel', 8], ['vertreter', 'vertreter', 'Vertreter', 3], ['kundengruppen', 'kundengruppe', 'Kundengruppe', 3], ['vkgruppen', 'vkgruppe', 'Artikelgruppe', 3]];
      art.forEach(([liste, dim, name, max]) => {
        (S.g.optionen[liste] || []).filter((o) => passt(o.name) || passt(o.nr)).slice(0, max).forEach((o) => S.treffer.push({ dim, nr: o.nr, name: o.name, art: name }));
      });
    }
    box.innerHTML = S.treffer.map((t, i) => `<button type="button" role="option" id="ctl-ua-tr-${i}" aria-selected="false" data-treffer="${i}"><span><b>${esc(t.name)}</b> <small>${esc(t.nr)}</small></span><small>${esc(t.art)}</small></button>`).join('')
      + (q.length >= 2 && !S.treffer.length ? '<p class="ctl-hilfe">Keine Treffer.</p>' : '');
    box.hidden = !box.innerHTML; feld.setAttribute('aria-expanded', String(!box.hidden)); feld.removeAttribute('aria-activedescendant');
  }
  function trefferWaehlen(i) {
    const t = S.treffer[i]; if (!t) return;
    $('#ctl-ua-treffer', S.box).hidden = true; $('#ctl-ua-suche', S.box).setAttribute('aria-expanded', 'false');
    details(t.dim, t.nr);
  }

  /* ---------- Laden und Zeichnen ---------- */
  async function laden() {
    const nr = ++S.laden;
    $('#ctl-ua-liste', S.box).classList.add('laedt');
    const r = await C.api('controlling_umsatz_auswertung', null, anfrage({ nach: S.nach, rang: S.rang, auf: S.auf ? '1' : '0' }));
    if (nr !== S.laden) return;
    $('#ctl-ua-liste', S.box).classList.remove('laedt');
    if (r.status === 401) { C.zeigeAnmeldung(); return; }
    const fehler = $('#ctl-ua-fehler', S.box);
    if (r.status !== 200 || !r.data.ok) { fehler.hidden = false; fehler.textContent = C.fehlerText(r, 'Die Auswertung konnte nicht geladen werden'); return; }
    fehler.hidden = true;
    S.d = r.data;
    zeichne();
  }
  function vjText() {
    const v = S.d.vorjahr;
    if (!v) return '';
    return `Vorjahr: ${monatsname(v.von)} – ${monatsname(v.bis)}${v.bisTag ? ` (bis ${v.bisTag}. wie im laufenden Monat)` : ''}`;
  }
  function zeichneKennzahlen() {
    const s = S.d.summe, v = S.d.summeVj;
    const k = [
      ['Umsatz', euroKachel(s.umsatz), v ? deltaHtml(s.umsatz, v.umsatz) + ' zum Vorjahr' : '', euro(s.umsatz)],
      ['Menge', menge(s.menge), v ? deltaHtml(s.menge, v.menge) + ' zum Vorjahr' : ''],
      ['Ø Preis', preis(s), v ? `Vorjahr ${esc(preis(v))}` : ''],
      ['Kunden', ganz(s.kunden), `${ganz(s.artikel)} Artikel · ${ganz(s.pos)} Positionen`],
    ];
    if (S.d.ek) {
      k.push(['Rohmarge', euroKachel(db(s)), v ? deltaHtml(db(s), db(v)) + ' zum Vorjahr' : '', euro(db(s))]);
      k.push(['Rohmarge %', pct(spanne(s)), v ? ppHtml(spanne(s), spanne(v)) + ' zum Vorjahr' : `EK für ${esc(pct(quote(s.umsatzEk, s.umsatz)))} des Umsatzes`,
        `${pct(spanne(s))} – Einkaufspreise liegen für ${pct(quote(s.umsatzEk, s.umsatz))} des Umsatzes vor`]);
    }
    $('#ctl-ua-kpis', S.box).classList.toggle('mit-ek', !!S.d.ek);
    $('#ctl-ua-kpis', S.box).innerHTML = k.map(([n, w, sub, voll]) => `<div class="ctl-kpi ctl-glas"><span>${esc(n)}</span><b title="${esc(voll || w)}">${esc(w)}</b><small>${sub}</small></div>`).join('');
  }
  function zeichneVerlauf() {
    const platz = $('#ctl-ua-diagramm', S.box).clientWidth || 360;
    $('#ctl-ua-diagramm', S.box).innerHTML = `<div class="ctl-ua-svgwrap">${monatsSvg(S.d.monate, S.kennzahl, !!S.d.vorjahr, platz)}</div>`;
    $('#ctl-ua-verlauf-hinweis', S.box).innerHTML = `Balken: ${esc(monatsname(S.d.anfrage.von))} – ${esc(monatsname(S.d.anfrage.bis))}${S.d.vorjahr ? ' · <span class="ctl-ua-legende-vj"></span> Vorjahr' : ''}`;
  }
  /* Spalten der Tabelle „Alle Spalten“ (ohne EK-Recht ohne Rohmarge) */
  function spalten() {
    const s = [
      { id: 'umsatz', name: 'Umsatz', wert: (z) => z.werte.umsatz, text: (z) => euro(z.werte.umsatz) },
      { id: 'anteil', name: 'Anteil', wert: (z) => quote(z.werte.umsatz, S.d.summe.umsatz), text: (z) => pct(quote(z.werte.umsatz, S.d.summe.umsatz)) },
    ];
    if (S.d.vorjahr) {
      s.push({ id: 'vj', name: 'Vorjahr', wert: (z) => (z.vj ? z.vj.umsatz : null), text: (z) => (z.vj ? euro(z.vj.umsatz) : '–') });
      s.push({ id: 'delta', name: '± Vorjahr', wert: (z) => delta(z.werte.umsatz, z.vj && z.vj.umsatz), html: (z) => deltaHtml(z.werte.umsatz, z.vj ? z.vj.umsatz : null) });
    }
    s.push({ id: 'menge', name: 'Menge', wert: (z) => z.werte.menge, text: (z) => menge(z.werte.menge) });
    s.push({ id: 'preis', name: 'Ø Preis', wert: (z) => (z.werte.menge ? z.werte.umsatz / z.werte.menge : null), text: (z) => preis(z.werte) });
    if (S.d.ek) {
      s.push({ id: 'db', name: 'Rohmarge', wert: (z) => db(z.werte), text: (z) => euro(db(z.werte)) });
      s.push({ id: 'spanne', name: 'Rohmarge %', wert: (z) => spanne(z.werte), text: (z) => pct(spanne(z.werte)) });
    }
    if (S.d.anfrage.nach !== 'kunde') s.push({ id: 'kunden', name: 'Kunden', wert: (z) => z.werte.kunden, text: (z) => ganz(z.werte.kunden) });
    s.push({ id: 'pos', name: 'Positionen', wert: (z) => z.werte.pos, text: (z) => ganz(z.werte.pos) });
    return s;
  }
  function sortiert() {
    const z = S.d.zeilen.slice();
    if (!S.sort) return z;
    const sp = spalten().find((x) => x.id === S.sort.id);
    if (!sp && S.sort.id !== 'name') return z;
    const f = S.sort.id === 'name' ? (x) => x.name : sp.wert;
    return z.sort((a, b) => {
      const x = f(a), y = f(b);
      if (x === y) return 0;
      if (x === null || x === undefined) return 1;
      if (y === null || y === undefined) return -1;
      const c = typeof x === 'string' ? x.localeCompare(y, 'de-DE', { numeric: true }) : x - y;
      return S.sort.ab ? -c : c;
    });
  }
  const gliederungName = (id) => { const g = S.g.gliederungen.find((x) => x.id === id); return g ? g.name : id; };
  /* Zweite Angabe unter dem Wert: was zur Kennzahl gehört (Umsatz zur Menge, Rohmarge % zur Rohmarge …) */
  function rangNebenwert(w, rang) {
    if (rang === 'menge') return euro(w.umsatz);
    if (rang === 'db') return `${pct(spanne(w))} von ${euroKurz(w.umsatzEk)}`;
    if (rang === 'spanne') return `${euro(db(w))} von ${euroKurz(w.umsatzEk)}`;
    return '';
  }
  function zeichneRangliste() {
    const nach = S.d.anfrage.nach, zeitlich = ZEITLICH.includes(nach), zeilen = sortiert(), rang = S.d.anfrage.rang || 'umsatz', k = RANG[rang];
    const max = Math.max(1e-9, ...zeilen.map((z) => Math.abs(k.wert(z.werte) || 0)));
    const summe = k.wert(S.d.summe);
    const zeigen = S.rangAlle ? zeilen : zeilen.slice(0, RANG_ANFANG);
    const kopf = `<div class="ctl-ua-rangzeile ctl-ua-rangkopfzeile" aria-hidden="true"><span>${zeitlich ? '' : '#'}</span><span>${esc(gliederungName(nach))}</span><span>${rang === 'spanne' ? '' : 'Anteil'}</span><span>${esc(k.name)}</span><span>${S.d.vorjahr ? '± Vorjahr' : ''}</span><span></span></div>`;
    let nr = 0, kleinKopf = false;
    $('#ctl-ua-liste', S.box).innerHTML = zeilen.length ? `${kopf}<ol class="ctl-ua-rang${zeitlich ? ' zeitlich' : ''}" id="ctl-ua-rang" data-rang="${rang}">${zeigen.map((z) => {
      const w = k.wert(z.werte), neben = rangNebenwert(z.werte, rang);
      const trenner = z.klein && !kleinKopf ? (kleinKopf = true, `<li class="ctl-ua-rangtrenner">Wenig Umsatz mit Einkaufspreis (unter ${esc(euro(S.d.rangSchwelle))}) – Rohmarge % wenig aussagekräftig</li>`) : '';
      return `${trenner}<li${z.klein ? ' class="klein"' : ''}><button type="button" class="ctl-ua-rangzeile" data-zeile="${esc(z.schluessel)}">
        <span class="ctl-ua-rangnr">${zeitlich || z.klein ? '' : ++nr}</span><span class="ctl-ua-rangname"><b class="ctl-ua-name">${esc(z.name)}</b>${z.sub ? `<small class="ctl-ua-sub">${esc(z.sub)}</small>` : ''}</span>
        <span class="ctl-ua-rangbalken"><span class="ctl-ua-spur${w < 0 ? ' minus' : ''}"><span style="width:${Math.min(100, (Math.abs(w || 0) / max) * 100).toFixed(1)}%"></span></span><small>${rang === 'spanne' ? '' : esc(pct(quote(w, summe)))}</small></span>
        <span class="ctl-ua-rangwert"><b class="${w < 0 ? 'ctl-ua-negativ' : ''}">${esc(w === null ? '–' : k.text(w))}</b>${neben ? `<small>${esc(neben)}</small>` : ''}</span>
        <span class="ctl-ua-rangdelta">${S.d.vorjahr ? k.delta(z.werte, z.vj) : ''}</span>${ICON.weiter}</button></li>`;
    }).join('')}</ol>`
        + (zeilen.length > zeigen.length ? `<button type="button" class="ctl-ua-link ctl-ua-mehr" id="ctl-ua-rang-alle">Alle ${ganz(zeilen.length)} anzeigen</button>` : '')
      : '<p class="ctl-empty">Keine Umsätze für diese Auswahl.</p>';
  }
  function zeichneTabelle() {
    const nach = S.d.anfrage.nach, sp = spalten();
    const pfeil = (id) => (S.sort && S.sort.id === id ? (S.sort.ab ? ' ↓' : ' ↑') : '');
    const zeilen = sortiert();
    const s = S.d.summe, summe = { name: 'Summe', werte: s, vj: S.d.summeVj };
    $('#ctl-ua-liste', S.box).innerHTML = `<div class="ctl-ua-tabwrap"><table class="ctl-tabelle ctl-ua-tabelle">
      <thead id="ctl-ua-kopf"><tr><th><button type="button" class="ctl-ua-sort" data-sort="name">${esc(gliederungName(nach))}${pfeil('name')}</button></th>${sp.map((x) => `<th class="ctl-zahl"><button type="button" class="ctl-ua-sort" data-sort="${x.id}">${esc(x.name)}${pfeil(x.id)}</button></th>`).join('')}</tr></thead>
      <tbody id="ctl-ua-zeilen">${zeilen.length ? zeilen.map((z) => `<tr class="ctl-ua-klick" tabindex="0" data-zeile="${esc(z.schluessel)}">
        <td class="ctl-rep"><span class="ctl-ua-name">${esc(z.name)}</span>${z.sub ? `<span class="ctl-ua-sub">${esc(z.sub)}</span>` : ''}</td>
        ${sp.map((x) => `<td class="ctl-zahl" data-label="${esc(x.name)}">${x.html ? x.html(z) : esc(x.text(z))}</td>`).join('')}</tr>`).join('')
      : `<tr><td colspan="${sp.length + 1}" class="ctl-empty">Keine Umsätze für diese Auswahl.</td></tr>`}</tbody>
      <tfoot id="ctl-ua-fuss">${zeilen.length ? `<tr class="ctl-total"><td class="ctl-rep">Summe</td>${sp.map((x) => `<td class="ctl-zahl">${x.id === 'anteil' ? '100,0 %' : x.html ? x.html(summe) : esc(x.text(summe))}</td>`).join('')}</tr>` : ''}</tfoot></table></div>`;
  }
  /* Größte Veränderungen: je drei Zeilen mit dem größten Plus und Minus in der Kennzahl der Rangliste (Rohmarge % → Rohmarge
     in Euro; nur Merkmale, nicht Zeit) */
  function zeichneVeraenderung() {
    const panel = $('#ctl-ua-veraenderung-panel', S.box), nach = S.d.anfrage.nach;
    const rang = S.d.anfrage.rang === 'spanne' ? 'db' : (S.d.anfrage.rang || 'umsatz'), k = RANG[rang];
    const z = S.d.vorjahr && !ZEITLICH.includes(nach) ? S.d.zeilen.map((x) => ({ x, d: k.wert(x.werte) - (x.vj ? k.wert(x.vj) : 0) })).filter((y) => y.d !== 0) : [];
    panel.hidden = !z.length;
    if (!z.length) return;
    const plus = z.filter((y) => y.d > 0).sort((a, b) => b.d - a.d).slice(0, 3), minus = z.filter((y) => y.d < 0).sort((a, b) => a.d - b.d).slice(0, 3);
    $('#ctl-ua-veraenderung-hinweis', S.box).textContent = `${HAUPT.concat(WEITERE).find(([id]) => id === nach)[1]} · ${k.name}${rang === 'menge' ? '' : ' in Euro'}`;
    $('#ctl-ua-veraenderung', S.box).innerHTML = plus.concat(minus).map(({ x, d }) => `<button type="button" class="ctl-ua-veraend" data-zeile="${esc(x.schluessel)}">
        <span><b>${esc(x.name)}</b><small>${x.vj && k.wert(x.vj) ? `${esc(k.kurz(k.wert(x.vj)))} → ${esc(k.kurz(k.wert(x.werte)))}` : `im Vorjahr ohne ${esc(k.name)}`}</small></span>
        <b class="ctl-ua-delta ${d > 0 ? 'plus' : 'minus'}">${d > 0 ? '+' : '−'}${esc(k.kurz(Math.abs(d)))}</b></button>`).join('');
  }
  function zeichneListe() {
    const nach = S.d.anfrage.nach;
    $$('#ctl-ua-nach [data-nach]', S.box).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.nach === nach)));
    $('#ctl-ua-nach-mehr', S.box).value = WEITERE.some(([id]) => id === nach) ? nach : '';
    $$('#ctl-ua-ansicht [data-ansicht]', S.box).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.ansicht === S.ansicht)));
    const rang = S.d.anfrage.rang || 'umsatz', auf = !!S.d.anfrage.auf;
    $$('#ctl-ua-rangnach [data-rang]', S.box).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.rang === rang)));
    const ri = $('#ctl-ua-richtung', S.box);
    ri.setAttribute('aria-pressed', String(auf)); ri.textContent = auf ? '↑ niedrigste zuerst' : '↓ höchste zuerst'; ri.hidden = ZEITLICH.includes(nach);
    $('#ctl-ua-titel', S.box).textContent = `Rangliste · ${gliederungName(nach)}`;
    $('#ctl-ua-tabelle-hinweis', S.box).textContent = `${monatsname(S.d.anfrage.von)} – ${monatsname(S.d.anfrage.bis)}${S.d.vorjahr ? ' · ' + vjText() : ''}`;
    $('#ctl-ua-klickhinweis', S.box).textContent = ZEITLICH.includes(nach) ? (nach === 'kw' ? '' : 'Klick auf eine Zeile wählt diesen Zeitraum.') : 'Klick auf eine Zeile öffnet die Details im Pop-up.';
    if (S.ansicht === 'tabelle') zeichneTabelle(); else zeichneRangliste();
    const s = S.d.summe;
    const mehr = S.d.zeilenGesamt > S.d.zeilen.length ? `Angezeigt: ${ganz(S.d.zeilen.length)} von ${ganz(S.d.zeilenGesamt)} Zeilen (die ersten nach ${RANG[S.d.anfrage.rang || 'umsatz'].name}). ` : '';
    const ohne = s.posOhne ? `Zusätzlich ${ganz(s.posOhne)} Positionen ohne Berechnung (z. B. Leergut, Menge ${menge(s.mengeOhne)}) – nicht in Menge und Umsatz. ` : '';
    $('#ctl-ua-fussnote', S.box).textContent = `${mehr}${ohne}Menge und Ø Preis je Mengeneinheit der Warenwirtschaft. Zuordnung zu Vertreter, Kundengruppe und Artikelgruppe nach den heutigen Stammdaten.${S.d.ek ? ' Rohmarge = Umsatz − EK-Wert der Positionen mit Einkaufspreis, Rohmarge % = Rohmarge ÷ deren Umsatz.' : ''}`;
  }
  function zeichneZeitraum() {
    const m = S.g.stand.monate, letzter = m[m.length - 1], j = letzter.slice(0, 4);
    const vor = { jahr: [`${j}-01`, letzter], vorjahr: [`${Number(j) - 1}-01`, `${Number(j) - 1}-12`], 12: [plusMonate(letzter, -11), letzter], alles: [m[0], letzter] };
    const begrenzt = ([v, b]) => [v < m[0] ? m[0] : v, b > letzter ? letzter : b];
    let aktiv = S.eigen ? 'eigen' : Object.keys(vor).find((k) => { const [v, b] = begrenzt(vor[k]); return v === S.von && b === S.bis; }) || 'eigen';
    $$('#ctl-ua-zeit [data-zeit]', S.box).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.zeit === aktiv)));
    $('#ctl-ua-eigen', S.box).hidden = aktiv !== 'eigen';
    return vor;
  }
  function zeichne() {
    zeichneKennzahlen(); zeichneVerlauf(); zeichneListe(); zeichneVeraenderung(); zeichneZeitraum();
  }

  /* ---------- Bedienung ---------- */
  function zeitraum(von, bis) {
    const m = S.g.stand.monate;
    S.von = von < m[0] ? m[0] : von; S.bis = bis > m[m.length - 1] ? m[m.length - 1] : bis;
    if (S.von > S.bis) S.von = S.bis;
    $('#ctl-ua-von', S.box).value = S.von; $('#ctl-ua-bis', S.box).value = S.bis;
  }
  function gliederung(nach) { S.nach = nach; S.sort = null; S.rangAlle = false; laden(); }
  function rangliste(rang, auf) { S.rang = rang; S.auf = auf; S.sort = null; S.rangAlle = false; laden(); }
  /* Klick auf eine Zeile: Merkmal → Pop-up; Monat/Quartal/Jahr → dieser Zeitraum */
  function zeileGewaehlt(schluessel) {
    const nach = S.d.anfrage.nach;
    if (!ZEITLICH.includes(nach)) { details(nach, schluessel); return; }
    if (nach === 'kw') return;
    S.eigen = false;
    if (nach === 'monat') { zeitraum(schluessel, schluessel); S.nach = 'kundengruppe'; }
    else if (nach === 'jahr') { zeitraum(`${schluessel}-01`, `${schluessel}-12`); S.nach = 'monat'; }
    else { const j = schluessel.slice(0, 4), q = Number(schluessel.slice(6)); zeitraum(`${j}-${String(q * 3 - 2).padStart(2, '0')}`, `${j}-${String(q * 3).padStart(2, '0')}`); S.nach = 'monat'; }
    S.sort = null; laden();
  }
  /* Pop-up: Schnittstelle zu umsatz-details.js */
  const kontext = {
    get dialog() { return $('#ctl-ua-dialog', S.box); },
    get grunddaten() { return S.g; },
    anfrage, filterText,
    get rang() { return S.rang; }, get auf() { return S.auf; },
    filterSetzen(dim, wert) {
      const f = FILTER.find((x) => x.nach === dim); if (!f) return;
      S.filter[f.id] = new Set([wert]); zeichneFilter(); laden();
    },
    vjText: () => (S.d ? vjText() : ''),
  };
  function details(dim, wert) { if (C.umsatzDetails) C.umsatzDetails.oeffnen(dim, wert, kontext); }

  function csv() {
    const gl = gliederungName(S.d.anfrage.nach);
    const kopf = [gl, 'Nummer', 'Umsatz €', ...(S.d.vorjahr ? ['Umsatz Vorjahr €'] : []), 'Menge', 'Kolli', 'Positionen', 'Kunden', ...(S.d.ek ? ['EK-Wert €', 'Umsatz mit EK €', 'Rohmarge €', 'Rohmarge %'] : [])];
    const zeilen = sortiert().map((z) => [z.name, z.schluessel, zahl(z.werte.umsatz / 100, 2), ...(S.d.vorjahr ? [z.vj ? zahl(z.vj.umsatz / 100, 2) : ''] : []), zahl(z.werte.menge / 1000, 3),
      zahl(z.werte.kolli, 0), zahl(z.werte.pos, 0), zahl(z.werte.kunden, 0),
      ...(S.d.ek ? [zahl(z.werte.ek / 100, 2), zahl(z.werte.umsatzEk / 100, 2), zahl(db(z.werte) / 100, 2), spanne(z.werte) === null ? '' : zahl(spanne(z.werte) * 100, 1)] : [])]);
    csvLaden(`Umsatz nach ${gl} ${S.d.anfrage.von} bis ${S.d.anfrage.bis}.csv`, [kopf, ...zeilen]);
  }
  function verbinden() {
    const b = S.box;
    $('#ctl-ua-von', b).addEventListener('change', () => { S.eigen = true; zeitraum($('#ctl-ua-von', b).value, S.bis < $('#ctl-ua-von', b).value ? $('#ctl-ua-von', b).value : S.bis); laden(); });
    $('#ctl-ua-bis', b).addEventListener('change', () => { S.eigen = true; zeitraum(S.von > $('#ctl-ua-bis', b).value ? $('#ctl-ua-bis', b).value : S.von, $('#ctl-ua-bis', b).value); laden(); });
    $('#ctl-ua-vj', b).addEventListener('change', () => { S.vj = $('#ctl-ua-vj', b).checked; laden(); });
    $('#ctl-ua-zeit', b).addEventListener('click', (ev) => {
      const k = ev.target.closest('[data-zeit]'); if (!k) return;
      if (k.dataset.zeit === 'eigen') { S.eigen = true; zeichneZeitraum(); $('#ctl-ua-von', b).focus(); return; }
      S.eigen = false;
      const [von, bis] = zeichneZeitraum()[k.dataset.zeit];
      zeitraum(von, bis); laden();
    });
    $('#ctl-ua-nach', b).addEventListener('click', (ev) => { const k = ev.target.closest('[data-nach]'); if (k) gliederung(k.dataset.nach); });
    $('#ctl-ua-nach-mehr', b).addEventListener('change', () => { const v = $('#ctl-ua-nach-mehr', b).value; if (v) gliederung(v); });
    $('#ctl-ua-rangnach', b).addEventListener('click', (ev) => { const k = ev.target.closest('[data-rang]'); if (k && k.dataset.rang !== S.rang) rangliste(k.dataset.rang, false); });
    $('#ctl-ua-richtung', b).addEventListener('click', () => rangliste(S.rang, !S.auf));
    $('#ctl-ua-ansicht', b).addEventListener('click', (ev) => { const k = ev.target.closest('[data-ansicht]'); if (k && S.d) { S.ansicht = k.dataset.ansicht; zeichneListe(); } });
    $('#ctl-ua-filterknopf', b).addEventListener('click', filterDialog);
    filterVerbinden();
    const feld = $('#ctl-ua-suche', b);
    feld.addEventListener('input', () => suchen(feld.value));
    feld.addEventListener('focus', () => { if (feld.value) suchen(feld.value); });
    feld.addEventListener('keydown', (ev) => {
      if (ev.key === 'ArrowDown' || ev.key === 'ArrowUp') {
        if (!S.treffer.length) return;
        ev.preventDefault();
        S.aktiv = (S.aktiv + (ev.key === 'ArrowDown' ? 1 : -1) + S.treffer.length) % S.treffer.length;
        $$('#ctl-ua-treffer [role="option"]', b).forEach((o, i) => o.setAttribute('aria-selected', String(i === S.aktiv)));
        feld.setAttribute('aria-activedescendant', `ctl-ua-tr-${S.aktiv}`);
      } else if (ev.key === 'Enter') { ev.preventDefault(); trefferWaehlen(S.aktiv >= 0 ? S.aktiv : 0); }
      else if (ev.key === 'Escape') { $('#ctl-ua-treffer', b).hidden = true; feld.setAttribute('aria-expanded', 'false'); }
    });
    $('#ctl-ua-treffer', b).addEventListener('click', (ev) => { const t = ev.target.closest('[data-treffer]'); if (t) trefferWaehlen(Number(t.dataset.treffer)); });
    document.addEventListener('click', (ev) => { if (!ev.target.closest('.ctl-ua-suchfeld')) { $('#ctl-ua-treffer', b).hidden = true; feld.setAttribute('aria-expanded', 'false'); } });
    b.addEventListener('click', (ev) => {
      if (ev.target.closest('dialog')) return;
      const weg = ev.target.closest('[data-weg]');
      if (weg) { S.filter[weg.dataset.weg].delete(weg.dataset.wert); zeichneFilter(); laden(); return; }
      if (ev.target.closest('#ctl-ua-zuruecksetzen')) { FILTER.forEach((f) => S.filter[f.id].clear()); zeichneFilter(); laden(); return; }
      const so = ev.target.closest('[data-sort]');
      if (so) { const id = so.dataset.sort; S.sort = S.sort && S.sort.id === id ? { id, ab: !S.sort.ab } : { id, ab: id !== 'name' }; zeichneListe(); return; }
      if (ev.target.closest('#ctl-ua-csv')) { if (S.d) csv(); return; }
      if (ev.target.closest('#ctl-ua-rang-alle')) { S.rangAlle = true; zeichneListe(); return; }
      const z = ev.target.closest('[data-zeile]');
      if (z && S.d) zeileGewaehlt(z.dataset.zeile);
    });
    b.addEventListener('keydown', (ev) => { const z = ev.target.closest('tr[data-zeile]'); if (z && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); zeileGewaehlt(z.dataset.zeile); } });
    $('#ctl-ua-kennzahl', b).addEventListener('change', () => { S.kennzahl = $('#ctl-ua-kennzahl', b).value; if (S.d) zeichneVerlauf(); });
  }

  async function anzeigen(box) {
    S.box = box;
    box.innerHTML = '<p class="ctl-hilfe">Umsatzdaten werden geladen …</p>';
    const r = await C.api('controlling_umsatz_daten');
    if (r.status === 401) { C.zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { box.innerHTML = `<p class="ctl-fehler" role="alert">${esc(C.fehlerText(r, 'Die Umsatzdaten konnten nicht geladen werden'))}</p>`; return; }
    S.g = r.data;
    if (!S.g.stand.monate.length) {
      box.innerHTML = `<section class="ctl-panel ctl-glas ctl-ua-leer"><h2>Noch keine Umsatzdaten</h2><p class="ctl-hilfe">Die Kundenumsatztabelle der Warenwirtschaft wird unter
        <strong>Verwaltung → Import → „Umsätze je Kunde und Artikel“</strong> hochgeladen${S.g.rechte.importieren ? '' : ' (Recht „Umsatzdaten importieren“, bitte an einen Administrator wenden)'}.
        Danach stehen hier Umsatz, Menge${S.g.rechte.ek ? ', Rohmarge' : ''} und Vorjahresvergleich nach Vertreter, Kundengruppe, Kunde, Artikelgruppe und Artikel bereit.</p></section>`;
      return;
    }
    box.innerHTML = geruest();
    const st = S.g.stand, letzter = st.monate[st.monate.length - 1];
    const imp = st.importe[0];
    $('#ctl-ua-stand', box).textContent = `Umsätze der Warenwirtschaft vom ${tag(st.von)} bis ${tag(st.bis)}${imp ? ` · letzter Import ${new Date(imp.t).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })}${imp.vonName ? ' (' + imp.vonName + ')' : ''}` : ''}`;
    zeitraum(`${letzter.slice(0, 4)}-01`, letzter);
    verbinden(); zeichneFilter();
    await laden();
  }

  C.umsatzAuswertung = { anzeigen };
})();
