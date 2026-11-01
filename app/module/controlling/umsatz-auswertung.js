/* STAFL-Plattform · Controlling · Umsatzstatistik, Reiter „Auswertung“: Umsätze aus der Warenwirtschaft (Import unter
   Verwaltung → Import, Importart „Umsätze je Kunde und Artikel“). Filter: Zeitraum, Vertreter, Kundengruppe, Kunde,
   Artikelgruppe (VK-Gruppe), Fleischart, Artikel; Gliederung nach Zeit oder Merkmal mit Vorjahr; Klick auf eine Zeile führt
   eine Ebene tiefer (z. B. Vertreter → Kunden → Artikel); Monatsverlauf; CSV der Tabelle.
   Daten: Aktionen controlling_umsatz_daten (Stand, Auswahllisten) und controlling_umsatz_auswertung (Summen) – gerechnet
   wird auf dem Server. Einkaufswerte, Deckungsbeitrag und Spanne liefert er nur mit controlling.umsatz_ek und bestand.einkaufspreise; hier
   werden die Spalten nur ein- oder ausgeblendet. Beträge kommen in Cent, Mengen in Tausendstel.
   Meldet sich bei controlling.js an (STAFL_CONTROLLING.umsatzAuswertung); umsatz.js öffnet den Reiter. */
'use strict';
(() => {
  const C = window.STAFL_CONTROLLING;
  const esc = C.esc;
  const $ = (s, el = document) => el.querySelector(s);
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
  const OHNE = '_';
  /* Filter: Kennung in der Anfrage → Liste der Grunddaten, Bezeichnung */
  const FILTER = [
    { id: 'v', liste: 'vertreter', name: 'Vertreter', ohne: 'ohne Vertreter', nach: 'vertreter' },
    { id: 'kg', liste: 'kundengruppen', name: 'Kundengruppe', ohne: 'ohne Kundengruppe', nach: 'kundengruppe' },
    { id: 'k', liste: 'kunden', name: 'Kunde', suche: true, nach: 'kunde' },
    { id: 'ag', liste: 'vkgruppen', name: 'Artikelgruppe', ohne: 'ohne Artikelgruppe', nach: 'vkgruppe' },
    { id: 'fa', liste: 'fleischarten', name: 'Fleischart', ohne: 'ohne Fleischart', nach: 'fleischart' },
    { id: 'a', liste: 'artikel', name: 'Artikel', suche: true, nach: 'artikel' },
  ];
  /* Eine Ebene tiefer: Gliederung → nächste Gliederung (Filter wird gesetzt) */
  const TIEFER = { vertreter: 'kunde', kundengruppe: 'kunde', kunde: 'artikel', vkgruppe: 'artikel', fleischart: 'vkgruppe', artikel: 'kunde', monat: 'kunde', quartal: 'monat', jahr: 'monat' };
  const ZEITLICH = ['monat', 'quartal', 'jahr', 'kw'];

  const S = { box: null, g: null, von: '', bis: '', nach: 'monat', vj: true, filter: {}, sort: null, d: null, laden: 0, kennzahl: 'umsatz', suche: {} };
  FILTER.forEach((f) => { S.filter[f.id] = new Set(); S.suche[f.id] = ''; });

  const optionen = (f) => {
    const l = S.g.optionen[f.liste] || [];
    const o = f.liste === 'fleischarten' ? l.map((x) => ({ nr: x, name: x })) : l.map((x) => ({ nr: x.nr, name: f.liste === 'kunden' || f.liste === 'artikel' ? `${x.name} (${x.nr})` : `${x.nr} – ${x.name}` }));
    return f.ohne ? o.concat([{ nr: OHNE, name: f.ohne }]) : o;
  };
  const optionName = (f, nr) => (optionen(f).find((o) => o.nr === nr) || { name: nr }).name;

  /* ---------- Gerüst ---------- */
  function geruest() {
    const monate = S.g.stand.monate;
    const opt = monate.slice().reverse().map((m) => `<option value="${m}">${esc(monatsname(m))}</option>`).join('');
    return `
      <p class="ctl-hilfe ctl-ua-stand" id="ctl-ua-stand"></p>
      <section class="ctl-filterzeile ctl-ua-filter" aria-label="Zeitraum und Filter">
        <label for="ctl-ua-von">Von</label><select id="ctl-ua-von">${opt}</select>
        <label for="ctl-ua-bis">bis</label><select id="ctl-ua-bis">${opt}</select>
        <div class="ctl-ua-schnell" role="group" aria-label="Zeitraum schnell wählen">
          <button type="button" class="ctl-ua-chip" data-zeit="jahr">Dieses Jahr</button><button type="button" class="ctl-ua-chip" data-zeit="vorjahr">Vorjahr</button>
          <button type="button" class="ctl-ua-chip" data-zeit="12">12 Monate</button><button type="button" class="ctl-ua-chip" data-zeit="alles">Alles</button></div>
        <label class="ctl-ua-check"><input type="checkbox" id="ctl-ua-vj" checked> Vorjahr</label>
      </section>
      <section class="ctl-filterzeile ctl-ua-filter" aria-label="Filter">
        ${FILTER.map((f) => `<details class="ctl-filter" data-filter="${f.id}"><summary>${esc(f.name)}</summary><div class="ctl-filterliste ctl-ua-liste">
          ${f.suche ? `<input type="search" class="ctl-ua-suche" data-suche="${f.id}" placeholder="${esc(f.name)} suchen …" aria-label="${esc(f.name)} suchen">` : ''}<div data-optionen="${f.id}"></div></div></details>`).join('')}
        <button type="button" class="ctl-ua-chip" id="ctl-ua-zuruecksetzen" hidden>Filter zurücksetzen</button>
      </section>
      <div class="ctl-ua-chips" id="ctl-ua-chips"></div>
      <p class="ctl-fehler" id="ctl-ua-fehler" role="alert" hidden></p>
      <div class="ctl-kpis ctl-ua-kpis" id="ctl-ua-kpis" aria-live="polite"></div>
      <section class="ctl-panel ctl-glas ctl-monatspanel"><div class="ctl-panelkopf"><div><h2>Monatsverlauf</h2><p class="ctl-hilfe" id="ctl-ua-verlauf-hinweis"></p></div>
        <div class="ctl-diagrammfilter"><label class="ctl-visuellabel" for="ctl-ua-kennzahl">Kennzahl</label><select id="ctl-ua-kennzahl"><option value="umsatz">Umsatz</option><option value="menge">Menge</option>${S.g.rechte.ek ? '<option value="db">Deckungsbeitrag</option>' : ''}</select></div></div>
        <div class="ctl-diagramm ctl-ua-diagramm" id="ctl-ua-diagramm"></div></section>
      <section class="ctl-panel ctl-glas ctl-tabellenpanel"><div class="ctl-panelkopf"><div><h2 id="ctl-ua-titel">Gliederung</h2><p class="ctl-hilfe" id="ctl-ua-tabelle-hinweis"></p></div>
        <div class="ctl-diagrammfilter ctl-ua-gliederung"><label class="ctl-visuellabel" for="ctl-ua-nach">Gliedern nach</label><select id="ctl-ua-nach">${S.g.gliederungen.map((x) => `<option value="${x.id}">nach ${esc(x.name)}</option>`).join('')}</select>
          <button type="button" class="btn sm" id="ctl-ua-csv">CSV</button></div></div>
        <div class="ctl-ua-tabwrap"><table class="ctl-tabelle ctl-ua-tabelle"><thead id="ctl-ua-kopf"></thead><tbody id="ctl-ua-zeilen"></tbody><tfoot id="ctl-ua-fuss"></tfoot></table></div>
        <p class="ctl-fussnote" id="ctl-ua-fussnote"></p></section>`;
  }

  /* ---------- Filter ---------- */
  function zeichneFilter() {
    FILTER.forEach((f) => {
      const box = $(`[data-optionen="${f.id}"]`, S.box), gew = S.filter[f.id];
      const summary = $(`[data-filter="${f.id}"] summary`, S.box);
      summary.textContent = gew.size === 0 ? `${f.name}: alle` : gew.size === 1 ? `${f.name}: ${optionName(f, [...gew][0])}` : `${f.name}: ${gew.size}`;
      summary.classList.toggle('aktiv', gew.size > 0);
      const q = S.suche[f.id].trim().toLocaleLowerCase('de-DE');
      const alle = optionen(f);
      const passt = alle.filter((o) => !gew.has(o.nr) && (!q || o.name.toLocaleLowerCase('de-DE').includes(q)));
      const zeigen = alle.filter((o) => gew.has(o.nr)).concat(passt.slice(0, f.suche ? 150 : 1000));
      box.innerHTML = zeigen.map((o) => `<label><input type="checkbox" data-wert="${esc(o.nr)}"${gew.has(o.nr) ? ' checked' : ''}>${esc(o.name)}</label>`).join('')
        + (passt.length > 150 && f.suche ? `<p class="ctl-hilfe">… ${ganz(passt.length - 150)} weitere – bitte suchen</p>` : '') + (!zeigen.length ? '<p class="ctl-hilfe">Keine Treffer.</p>' : '');
    });
    const chips = [];
    FILTER.forEach((f) => S.filter[f.id].forEach((nr) => chips.push(`<button type="button" class="ctl-ua-chip aktiv" data-weg="${f.id}" data-wert="${esc(nr)}" title="Filter entfernen">${esc(f.name)}: ${esc(optionName(f, nr))} ×</button>`)));
    $('#ctl-ua-chips', S.box).innerHTML = chips.join('');
    $('#ctl-ua-zuruecksetzen', S.box).hidden = !chips.length;
  }
  function anfrage() {
    const p = new URLSearchParams({ von: S.von, bis: S.bis, nach: S.nach, vj: S.vj ? '1' : '0' });
    FILTER.forEach((f) => { if (S.filter[f.id].size) p.set(f.id, [...S.filter[f.id]].join(',')); });
    return '&' + p.toString();
  }

  /* ---------- Laden und Zeichnen ---------- */
  async function laden() {
    const nr = ++S.laden;
    $('#ctl-ua-zeilen', S.box).classList.add('laedt');
    const r = await C.api('controlling_umsatz_auswertung', null, anfrage());
    if (nr !== S.laden) return;
    $('#ctl-ua-zeilen', S.box).classList.remove('laedt');
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
  const delta = (jetzt, vor) => (vor ? (jetzt - vor) / Math.abs(vor) : null);
  const deltaHtml = (jetzt, vor) => {
    const d = delta(jetzt, vor);
    if (d === null) return '<span class="ctl-ua-delta">–</span>';
    return `<span class="ctl-ua-delta ${d >= 0 ? 'plus' : 'minus'}">${d >= 0 ? '+' : ''}${pct(d)}</span>`;
  };
  function zeichneKennzahlen() {
    const s = S.d.summe, v = S.d.summeVj;
    const k = [
      ['Umsatz', euroKachel(s.umsatz), v ? deltaHtml(s.umsatz, v.umsatz) + ' zum Vorjahr' : '', euro(s.umsatz)],
      ['Menge', menge(s.menge), v ? deltaHtml(s.menge, v.menge) + ' zum Vorjahr' : ''],
      ['Ø Preis', preis(s), v ? `Vorjahr ${esc(preis(v))}` : ''],
      ['Kunden', ganz(s.kunden), `${ganz(s.artikel)} Artikel · ${ganz(s.pos)} Positionen`],
    ];
    if (S.d.ek) {
      k.push(['Deckungsbeitrag', euroKachel(db(s)), v ? deltaHtml(db(s), db(v)) + ' zum Vorjahr' : '', euro(db(s))]);
      k.push(['Spanne', pct(spanne(s)), `EK für ${pct(quote(s.umsatzEk, s.umsatz))} des Umsatzes`]);
    }
    $('#ctl-ua-kpis', S.box).classList.toggle('mit-ek', !!S.d.ek);
    $('#ctl-ua-kpis', S.box).innerHTML = k.map(([n, w, sub, voll]) => `<div class="ctl-kpi ctl-glas"><span>${esc(n)}</span><b title="${esc(voll || w)}">${esc(w)}</b><small>${sub}</small></div>`).join('');
  }
  function wertVon(w, k) { return !w ? null : k === 'db' ? db(w) : w[k]; }
  function zeichneVerlauf() {
    const k = S.kennzahl, mon = S.d.monate;
    const werte = mon.map((m) => wertVon(m.werte, k) || 0), vj = mon.map((m) => wertVon(m.vj, k));
    const max = Math.max(1, ...werte.map(Math.abs), ...vj.filter((x) => x !== null).map(Math.abs));
    const platz = $('#ctl-ua-diagramm', S.box).clientWidth || 800;   // so breit wie die Fläche; bei vielen Monaten waagerecht blättern
    const W = Math.max(mon.length * 34, platz), H = 190, unten = 26, oben = 10, hoehe = H - unten - oben, breite = W / mon.length;
    const y = (v) => oben + hoehe - (Math.max(0, v) / max) * hoehe;
    const fmt = k === 'menge' ? menge : euroKurz;
    let svg = `<svg class="ctl-ua-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc($('#ctl-ua-kennzahl', S.box).selectedOptions[0].textContent)} je Monat${S.d.vorjahr ? ' mit Vorjahr' : ''}">`;
    mon.forEach((m, i) => {
      const x = i * breite, b = Math.min(56, Math.max(6, breite * 0.56));
      const v = werte[i];
      svg += `<g><title>${esc(monatsname(m.monat))}: ${esc(fmt(v))}${vj[i] !== null ? ` · Vorjahr ${esc(fmt(vj[i]))}` : ''}</title>`
        + `<rect class="ctl-ua-balken" x="${(x + (breite - b) / 2).toFixed(1)}" y="${y(v).toFixed(1)}" width="${b.toFixed(1)}" height="${(oben + hoehe - y(v)).toFixed(1)}" rx="3"></rect>`
        + (breite >= 26 || i % 2 === 0 ? `<text class="ctl-ua-achse" x="${(x + breite / 2).toFixed(1)}" y="${H - 8}" text-anchor="middle">${esc(breite >= 44 ? monatsname(m.monat, true) : m.monat.endsWith('-01') ? m.monat.slice(0, 4) : MONATSNAMEN[Number(m.monat.slice(5, 7)) - 1].slice(0, 3))}</text>` : '') + '</g>';
    });
    const punkte = vj.map((v, i) => (v === null ? null : `${(i * breite + breite / 2).toFixed(1)},${y(v).toFixed(1)}`)).filter(Boolean);
    if (punkte.length > 1) svg += `<polyline class="ctl-ua-vjlinie" points="${punkte.join(' ')}"></polyline>`;
    punkte.forEach((p) => { const [px, py] = p.split(','); svg += `<circle class="ctl-ua-vjpunkt" cx="${px}" cy="${py}" r="3"></circle>`; });
    svg += '</svg>';
    $('#ctl-ua-diagramm', S.box).innerHTML = `<div class="ctl-ua-svgwrap">${svg}</div>`;
    $('#ctl-ua-verlauf-hinweis', S.box).innerHTML = `Balken: ${esc(monatsname(S.d.anfrage.von))} – ${esc(monatsname(S.d.anfrage.bis))}${S.d.vorjahr ? ' · <span class="ctl-ua-legende-vj"></span> Vorjahr' : ''}`;
  }
  /* Spalten der Tabelle (ohne EK-Recht ohne DB und Spanne) */
  function spalten() {
    const s = [
      { id: 'umsatz', name: 'Umsatz', wert: (z) => z.werte.umsatz, text: (z) => euro(z.werte.umsatz) },
      { id: 'anteil', name: 'Anteil', wert: (z) => quote(z.werte.umsatz, S.d.summe.umsatz), text: (z) => pct(quote(z.werte.umsatz, S.d.summe.umsatz)) },
    ];
    if (S.d.vorjahr) {
      s.push({ id: 'vj', name: 'Vorjahr', wert: (z) => (z.vj ? z.vj.umsatz : null), text: (z) => (z.vj ? euro(z.vj.umsatz) : '–') });
      s.push({ id: 'delta', name: '± Vorjahr', wert: (z) => delta(z.werte.umsatz, z.vj && z.vj.umsatz), html: (z) => deltaHtml(z.werte.umsatz, z.vj && z.vj.umsatz) });
    }
    s.push({ id: 'menge', name: 'Menge', wert: (z) => z.werte.menge, text: (z) => menge(z.werte.menge) });
    s.push({ id: 'preis', name: 'Ø Preis', wert: (z) => (z.werte.menge ? z.werte.umsatz / z.werte.menge : null), text: (z) => preis(z.werte) });
    if (S.d.ek) {
      s.push({ id: 'db', name: 'DB', wert: (z) => db(z.werte), text: (z) => euro(db(z.werte)) });
      s.push({ id: 'spanne', name: 'Spanne', wert: (z) => spanne(z.werte), text: (z) => pct(spanne(z.werte)) });
    }
    if (!['kunde'].includes(S.d.anfrage.nach)) s.push({ id: 'kunden', name: 'Kunden', wert: (z) => z.werte.kunden, text: (z) => ganz(z.werte.kunden) });
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
  function zeichneTabelle() {
    const nach = S.d.anfrage.nach, sp = spalten();
    const gl = S.g.gliederungen.find((x) => x.id === nach);
    $('#ctl-ua-titel', S.box).textContent = `Nach ${gl ? gl.name : nach}`;
    $('#ctl-ua-tabelle-hinweis', S.box).textContent = `${monatsname(S.d.anfrage.von)} – ${monatsname(S.d.anfrage.bis)}${S.d.vorjahr ? ' · ' + vjText() : ''}${TIEFER[nach] ? ' · Zeile anklicken: eine Ebene tiefer' : ''}`;
    const pfeil = (id) => (S.sort && S.sort.id === id ? (S.sort.ab ? ' ↓' : ' ↑') : '');
    $('#ctl-ua-kopf', S.box).innerHTML = `<tr><th><button type="button" class="ctl-ua-sort" data-sort="name">${esc(gl ? gl.name : '')}${pfeil('name')}</button></th>${sp.map((s) => `<th class="ctl-zahl"><button type="button" class="ctl-ua-sort" data-sort="${s.id}">${esc(s.name)}${pfeil(s.id)}</button></th>`).join('')}</tr>`;
    const zeilen = sortiert();
    const klickbar = !!TIEFER[nach];
    $('#ctl-ua-zeilen', S.box).innerHTML = zeilen.length ? zeilen.map((z) => `<tr${klickbar ? ` class="ctl-ua-klick" tabindex="0" data-tiefer="${esc(z.schluessel)}"` : ''}>
        <td class="ctl-rep"><span class="ctl-ua-name">${esc(z.name)}</span>${z.sub ? `<span class="ctl-ua-sub">${esc(z.sub)}</span>` : ''}</td>
        ${sp.map((s) => `<td class="ctl-zahl" data-label="${esc(s.name)}">${s.html ? s.html(z) : esc(s.text(z))}</td>`).join('')}</tr>`).join('')
      : `<tr><td colspan="${sp.length + 1}" class="ctl-empty">Keine Umsätze für diese Auswahl.</td></tr>`;
    const s = S.d.summe;
    const summe = { name: 'Summe', werte: s, vj: S.d.summeVj };
    $('#ctl-ua-fuss', S.box).innerHTML = zeilen.length ? `<tr class="ctl-total"><td class="ctl-rep">Summe</td>${sp.map((x) => `<td class="ctl-zahl">${x.id === 'anteil' ? '100,0 %' : x.html ? x.html(summe) : esc(x.text(summe))}</td>`).join('')}</tr>` : '';
    const mehr = S.d.zeilenGesamt > S.d.zeilen.length ? `Angezeigt: ${ganz(S.d.zeilen.length)} von ${ganz(S.d.zeilenGesamt)} Zeilen (die umsatzstärksten). ` : '';
    const ohne = s.posOhne ? `Zusätzlich ${ganz(s.posOhne)} Positionen ohne Berechnung (z. B. Leergut, Menge ${menge(s.mengeOhne)}) – nicht in Menge und Umsatz. ` : '';
    $('#ctl-ua-fussnote', S.box).textContent = `${mehr}${ohne}Menge und Ø Preis je Mengeneinheit der Warenwirtschaft. Zuordnung zu Vertreter, Kundengruppe und Artikelgruppe nach den heutigen Stammdaten.${S.d.ek ? ' DB = Umsatz − EK-Wert der Positionen mit Einkaufspreis, Spanne = DB ÷ deren Umsatz.' : ''}`;
  }
  function zeichne() {
    zeichneKennzahlen(); zeichneVerlauf(); zeichneTabelle();
    $('#ctl-ua-nach', S.box).value = S.d.anfrage.nach;
  }

  /* ---------- Bedienung ---------- */
  function zeitraum(von, bis) {
    const m = S.g.stand.monate;
    S.von = von < m[0] ? m[0] : von; S.bis = bis > m[m.length - 1] ? m[m.length - 1] : bis;
    if (S.von > S.bis) S.von = S.bis;
    $('#ctl-ua-von', S.box).value = S.von; $('#ctl-ua-bis', S.box).value = S.bis;
  }
  function tiefer(schluessel) {
    const nach = S.d.anfrage.nach, ziel = TIEFER[nach];
    if (!ziel) return;
    if (ZEITLICH.includes(nach)) {
      if (nach === 'monat') zeitraum(schluessel, schluessel);
      else if (nach === 'jahr') zeitraum(`${schluessel}-01`, `${schluessel}-12`);
      else { const j = schluessel.slice(0, 4), q = Number(schluessel.slice(6)); zeitraum(`${j}-${String(q * 3 - 2).padStart(2, '0')}`, `${j}-${String(q * 3).padStart(2, '0')}`); }
    } else {
      const f = FILTER.find((x) => x.nach === nach);
      S.filter[f.id] = new Set([schluessel]);
    }
    S.nach = ziel; S.sort = null;
    zeichneFilter(); laden();
  }
  function csv() {
    const sp = spalten(), gl = S.g.gliederungen.find((x) => x.id === S.d.anfrage.nach);
    const zahl = (v, d) => (v === null || v === undefined ? '' : NF(d).format(v).replace(/\./g, ''));
    const kopf = [gl.name, 'Nummer', 'Umsatz €', ...(S.d.vorjahr ? ['Umsatz Vorjahr €'] : []), 'Menge', 'Kolli', 'Positionen', 'Kunden', ...(S.d.ek ? ['EK-Wert €', 'Umsatz mit EK €', 'DB €', 'Spanne %'] : [])];
    const zeilen = sortiert().map((z) => [z.name, z.schluessel, zahl(z.werte.umsatz / 100, 2), ...(S.d.vorjahr ? [z.vj ? zahl(z.vj.umsatz / 100, 2) : ''] : []), zahl(z.werte.menge / 1000, 3),
      zahl(z.werte.kolli, 0), zahl(z.werte.pos, 0), zahl(z.werte.kunden, 0),
      ...(S.d.ek ? [zahl(z.werte.ek / 100, 2), zahl(z.werte.umsatzEk / 100, 2), zahl(db(z.werte) / 100, 2), spanne(z.werte) === null ? '' : zahl(spanne(z.werte) * 100, 1)] : [])]);
    const text = '﻿' + [kopf, ...zeilen].map((r) => r.map((x) => `"${String(x).replace(/"/g, '""')}"`).join(';')).join('\r\n') + '\r\n';
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([text], { type: 'text/csv;charset=utf-8' }));
    a.download = `Umsatz nach ${gl.name} ${S.d.anfrage.von} bis ${S.d.anfrage.bis}.csv`;
    document.body.append(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }
  function verbinden() {
    const b = S.box;
    $('#ctl-ua-von', b).addEventListener('change', () => { zeitraum($('#ctl-ua-von', b).value, S.bis < $('#ctl-ua-von', b).value ? $('#ctl-ua-von', b).value : S.bis); laden(); });
    $('#ctl-ua-bis', b).addEventListener('change', () => { zeitraum(S.von > $('#ctl-ua-bis', b).value ? $('#ctl-ua-bis', b).value : S.von, $('#ctl-ua-bis', b).value); laden(); });
    $('#ctl-ua-vj', b).addEventListener('change', () => { S.vj = $('#ctl-ua-vj', b).checked; laden(); });
    b.querySelector('.ctl-ua-schnell').addEventListener('click', (ev) => {
      const k = ev.target.closest('[data-zeit]'); if (!k) return;
      const m = S.g.stand.monate, letzter = m[m.length - 1], j = letzter.slice(0, 4);
      if (k.dataset.zeit === 'jahr') zeitraum(`${j}-01`, letzter);
      else if (k.dataset.zeit === 'vorjahr') zeitraum(`${Number(j) - 1}-01`, `${Number(j) - 1}-12`);
      else if (k.dataset.zeit === '12') zeitraum(plusMonate(letzter, -11), letzter);
      else zeitraum(m[0], letzter);
      laden();
    });
    b.addEventListener('change', (ev) => {
      const c = ev.target.closest('[data-optionen] input[type="checkbox"]'); if (!c) return;
      const id = c.closest('[data-optionen]').dataset.optionen;
      if (c.checked) S.filter[id].add(c.dataset.wert); else S.filter[id].delete(c.dataset.wert);
      zeichneFilter(); laden();
    });
    b.addEventListener('input', (ev) => { const s = ev.target.closest('[data-suche]'); if (s) { S.suche[s.dataset.suche] = s.value; zeichneFilter(); s.focus(); } });
    b.addEventListener('click', (ev) => {
      const weg = ev.target.closest('[data-weg]');
      if (weg) { S.filter[weg.dataset.weg].delete(weg.dataset.wert); zeichneFilter(); laden(); return; }
      if (ev.target.closest('#ctl-ua-zuruecksetzen')) { FILTER.forEach((f) => S.filter[f.id].clear()); zeichneFilter(); laden(); return; }
      const so = ev.target.closest('[data-sort]');
      if (so) { const id = so.dataset.sort; S.sort = S.sort && S.sort.id === id ? { id, ab: !S.sort.ab } : { id, ab: id !== 'name' }; zeichneTabelle(); return; }
      if (ev.target.closest('#ctl-ua-csv')) { if (S.d) csv(); return; }
      const z = ev.target.closest('[data-tiefer]');
      if (z && S.d) tiefer(z.dataset.tiefer);
    });
    b.addEventListener('keydown', (ev) => { const z = ev.target.closest('[data-tiefer]'); if (z && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); tiefer(z.dataset.tiefer); } });
    $('#ctl-ua-nach', b).addEventListener('change', () => { S.nach = $('#ctl-ua-nach', b).value; S.sort = null; laden(); });
    $('#ctl-ua-kennzahl', b).addEventListener('change', () => { S.kennzahl = $('#ctl-ua-kennzahl', b).value; if (S.d) zeichneVerlauf(); });
    document.addEventListener('click', (ev) => { b.querySelectorAll('details.ctl-filter[open]').forEach((d) => { if (!d.contains(ev.target)) d.open = false; }); });
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
        Danach stehen hier Umsatz, Menge${S.g.rechte.ek ? ', Deckungsbeitrag' : ''} und Vorjahresvergleich nach Vertreter, Kundengruppe, Kunde, Artikelgruppe und Artikel bereit.</p></section>`;
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
