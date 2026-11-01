/* STAFL-Plattform · Controlling · Bereich Umsatzstatistik, Reiter „Monatsmeldung“: Kg, Umsatz, Deckungsbeitrag und Spanne je
   Vertreter und Monat eines Jahres – Kennzahlen, Vertretertabelle mit Anteilen, Monatsvergleich (Balken/Linie). Die Werte
   rechnet der Server aus den importierten Umsatzdaten (Aktion controlling_umsatz&jahr=JJJJ, keine Erfassung von Hand mehr);
   DB und Spanne nur mit den Rechten für Einkaufswerte (sonst leer). Grundlage: Modul „Gust 1“ aus dem Modulbausatz.
   Meldet sich bei controlling.js an (STAFL_CONTROLLING.bereich).
   Reiter „Auswertung“ (Umsätze aus der Warenwirtschaft): umsatz-auswertung.js – zuerst geöffnet, sobald Daten importiert sind. */
'use strict';
(() => {
  const C = window.STAFL_CONTROLLING;
  const esc = C.esc;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const ist = (v) => v !== null && v !== undefined && v !== '' && Number.isFinite(Number(v));
  const fmt = (n, d = 2) => !ist(n) ? '–' : new Intl.NumberFormat('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d }).format(Number(n));
  const kg = (n) => !ist(n) ? '–' : new Intl.NumberFormat('de-DE', { maximumFractionDigits: 3 }).format(Number(n));   // Kg ohne überflüssige Nullen
  const euro = (n) => !ist(n) ? '–' : new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(n));
  const pct = (n) => !ist(n) ? '–' : new Intl.NumberFormat('de-DE', { style: 'percent', minimumFractionDigits: 2, maximumFractionDigits: 2 }).format(Number(n));
  const summe = (werte) => { const a = werte.filter(ist).map(Number); return a.length ? a.reduce((x, y) => x + y, 0) : null; };
  const schnitt = (werte) => { const a = werte.filter(ist).map(Number); return a.length ? a.reduce((x, y) => x + y, 0) / a.length : null; };
  const quote = (teil, ganz) => ist(teil) && ist(ganz) && Number(ganz) !== 0 ? Number(teil) / Number(ganz) : null;
  const KENNZAHL = { umsatz: 'Umsatz', db: 'DB', kg: 'Kg', spanne: 'Spanne' };

  const S = { box: null, d: null, rechte: {}, jahr: String(new Date().getFullYear()), monate: new Set(), vertreter: new Set(), kennzahl: 'umsatz', tab: 'uebersicht' };
  const MONATE = () => S.d ? S.d.monate : [];
  const monatsname = (nr) => (MONATE().find((m) => m.nr === nr) || { name: nr }).name;
  const reps = () => S.d ? S.d.vertreter : [];
  const gewMonate = () => MONATE().map((m) => m.nr).filter((nr) => S.monate.has(nr));
  const gewReps = () => reps().filter((r) => S.vertreter.has(r.nr));
  const monatsdaten = (jahr, monat) => (S.d && S.d.jahre && S.d.jahre[jahr] && S.d.jahre[jahr][monat]) || {};
  const wert = (monat, nr, k) => { const r = monatsdaten(S.jahr, monat)[nr]; return r && ist(r[k]) ? Number(r[k]) : null; };
  const summeAus = (monate, auswahl, k) => summe(monate.flatMap((m) => auswahl.map((r) => wert(m, r.nr, k))));
  const gesamt = (monate, auswahl) => { const kg = summeAus(monate, auswahl, 'kg'), umsatz = summeAus(monate, auswahl, 'umsatz'), db = summeAus(monate, auswahl, 'db'); return { kg, umsatz, db, spanne: quote(db, umsatz) }; };
  const zeitraumText = (monate) => monate.length === MONATE().length ? `Jahr ${S.jahr}` : monate.length === 1 ? `${monatsname(monate[0])} ${S.jahr}` : monate.length ? `${monate.length} ausgewählte Monate ${S.jahr}` : 'Keine Monate ausgewählt';
  const anzeige = (k, v) => k === 'umsatz' || k === 'db' ? euro(v) : k === 'kg' ? (ist(v) ? `${kg(v)} kg` : '–') : pct(v);

  /* ---------- Gerüst des Bereichs ---------- */
  const GERUEST = `
    <div class="ctl-intro"><div><p class="ctl-eyebrow">Vertrieb · Kennzahlen</p><h1>Umsatzstatistik</h1>
      <p class="ctl-intro-text">Umsätze aus der Warenwirtschaft nach Vertreter, Kunde und Artikel – dazu die Monatsmeldung je Vertreter.</p></div><p class="ctl-notiz ctl-stand" id="ctl-u-stand"></p></div>
    <nav class="ctl-tabs stafl-streifen" id="ctl-u-tabs" role="tablist" aria-label="Umsatzstatistik"><button type="button" role="tab" data-tab="auswertung" aria-selected="false">Auswertung</button><button type="button" role="tab" data-tab="uebersicht" aria-selected="true">Monatsmeldung</button></nav>
    <section class="ctl-filterzeile" id="ctl-u-filter" aria-label="Filter">
      <label for="ctl-u-jahr">Jahr</label><select id="ctl-u-jahr"></select>
      <details class="ctl-filter" id="ctl-u-zeitfilter"><summary id="ctl-u-zeitfilter-titel">Alle Monate</summary><div class="ctl-filterliste" id="ctl-u-monatsoptionen"></div></details>
      <details class="ctl-filter" id="ctl-u-vertreterfilter"><summary id="ctl-u-vertreterfilter-titel">Alle Vertreter</summary><div class="ctl-filterliste" id="ctl-u-vertreteroptionen"></div></details>
      <label class="ctl-visuellabel" for="ctl-u-kennzahl">Vergleich</label><select id="ctl-u-kennzahl"><option value="umsatz">Umsatz im Vergleich</option><option value="db">DB im Vergleich</option><option value="kg">Kg im Vergleich</option><option value="spanne">Spanne im Vergleich</option></select>
    </section>
    <section id="ctl-u-auswertung" hidden></section>
    <section id="ctl-u-uebersicht">
      <div class="ctl-kpis" id="ctl-u-kpis" aria-live="polite"></div>
      <section class="ctl-panel ctl-glas ctl-tabellenpanel"><div class="ctl-panelkopf"><div><h2 id="ctl-u-tabelle-titel">Vertreter</h2><p class="ctl-hilfe" id="ctl-u-anteil-hinweis"></p></div></div>
        <div class="ctl-tabelle-wrap"><table class="ctl-tabelle ctl-vertretertabelle"><thead><tr><th>Vertreter</th><th class="ctl-zahl">Kg</th><th class="ctl-anteil">Anteil</th><th class="ctl-zahl">Umsatz</th><th class="ctl-anteil">Anteil</th><th class="ctl-zahl">DB</th><th class="ctl-anteil">Anteil</th><th class="ctl-zahl">Spanne</th><th>Vergleich</th></tr></thead><tbody id="ctl-u-vertreterzeilen"></tbody></table></div>
        <p class="ctl-fussnote" id="ctl-u-fussnote">Spanne = DB ÷ Umsatz. Anteile beziehen sich auf die Summe der ausgewählten Vertreter im gewählten Zeitraum.</p>
      </section>
      <section class="ctl-panel ctl-glas ctl-monatspanel"><div class="ctl-panelkopf ctl-monatskopf"><div><h2>Monatsvergleich</h2><p class="ctl-hilfe" id="ctl-u-diagrammhinweis"></p></div>
          <div class="ctl-diagrammfilter"><label class="ctl-visuellabel" for="ctl-u-monatskennzahl">Kennzahl</label><select id="ctl-u-monatskennzahl"><option value="umsatz">Umsatz</option><option value="db">DB</option><option value="kg">Kg</option><option value="spanne">Spanne</option></select>
          <label class="ctl-visuellabel" for="ctl-u-diagrammart">Diagramm</label><select id="ctl-u-diagrammart"><option value="balken">Balken</option><option value="linie">Linie</option></select></div></div>
        <div class="ctl-diagramm" id="ctl-u-diagramm"></div>
        <div class="ctl-tabelle-wrap ctl-monatstabelle-wrap"><table class="ctl-tabelle ctl-monatstabelle"><thead><tr><th>Monat</th><th class="ctl-zahl">Kg</th><th class="ctl-zahl">Umsatz</th><th class="ctl-zahl">DB</th><th class="ctl-zahl">Spanne</th><th>Status</th></tr></thead><tbody id="ctl-u-monatszeilen"></tbody></table></div>
      </section>
    </section>
`;

  /* ---------- Filter ---------- */
  /* Jahre mit importierten Umsätzen (ohne Daten: das laufende Jahr) */
  function jahre() {
    const liste = (S.d && S.d.jahreListe) || [];
    return [...new Set([...liste, S.jahr])].filter((y) => /^\d{4}$/.test(y)).sort((a, b) => Number(b) - Number(a));
  }
  function zeichneJahre() {
    const liste = jahre();
    if (!liste.includes(S.jahr)) S.jahr = liste[0];
    $('#ctl-u-jahr').innerHTML = liste.map((y) => `<option value="${esc(y)}">${esc(y)}</option>`).join('');
    $('#ctl-u-jahr').value = S.jahr;
  }
  function zeichneMonatsfilter() {
    const alle = S.monate.size === MONATE().length, gew = gewMonate();
    $('#ctl-u-zeitfilter-titel').textContent = alle ? 'Alle Monate' : gew.length === 1 ? monatsname(gew[0]) : gew.length ? `${gew.length} Monate` : 'Keine Monate';
    $('#ctl-u-monatsoptionen').innerHTML = `<label class="ctl-filter-alle"><input type="checkbox" data-alle-monate ${alle ? 'checked' : ''}>Alle Monate</label>`
      + MONATE().map((m) => `<label><input type="checkbox" data-monat="${esc(m.nr)}" ${S.monate.has(m.nr) ? 'checked' : ''}>${esc(m.name)}</label>`).join('');
  }
  function zeichneVertreterfilter() {
    const alle = S.vertreter.size === reps().length && reps().length > 0, gew = gewReps();
    $('#ctl-u-vertreterfilter-titel').textContent = alle ? 'Alle Vertreter' : gew.length === 1 ? gew[0].anzeige : gew.length ? `${gew.length} Vertreter` : 'Keine Vertreter';
    $('#ctl-u-vertreteroptionen').innerHTML = `<label class="ctl-filter-alle"><input type="checkbox" data-alle-vertreter ${alle ? 'checked' : ''}>Alle</label>`
      + reps().map((r) => `<label><input type="checkbox" data-vertreter="${esc(r.nr)}" ${S.vertreter.has(r.nr) ? 'checked' : ''}>${esc(r.anzeige)}</label>`).join('');
  }

  /* ---------- Übersicht ---------- */
  function zeichneKennzahlen(monate, auswahl) {
    const t = gesamt(monate, auswahl), text = zeitraumText(monate);
    $('#ctl-u-kpis').innerHTML = [['Kg', kg(t.kg)], ['Umsatz', euro(t.umsatz)], ['DB', euro(t.db)], ['Spanne', pct(t.spanne)]]
      .map(([n, v]) => `<div class="ctl-kpi ctl-glas"><span>${esc(n)}</span><b>${esc(v)}</b><small>${esc(text)}</small></div>`).join('');
  }
  function zeichneVertreter(monate, auswahl) {
    const k = S.kennzahl, t = gesamt(monate, auswahl);
    const zeilen = auswahl.map((r) => {
      const z = gesamt(monate, [r]);
      return { ...z, name: r.anzeige, anteilKg: quote(z.kg, t.kg), anteilUmsatz: quote(z.umsatz, t.umsatz), anteilDb: quote(z.db, t.db) };
    }).sort((a, b) => (ist(b[k]) ? Number(b[k]) : -Infinity) - (ist(a[k]) ? Number(a[k]) : -Infinity));
    const max = Math.max(1, ...zeilen.map((z) => Math.abs(Number(z[k]) || 0)));
    $('#ctl-u-tabelle-titel').textContent = `Vertreter · ${zeitraumText(monate)}`;
    $('#ctl-u-anteil-hinweis').textContent = monate.length === MONATE().length ? 'Anteile am Jahrestotal' : monate.length === 1 ? 'Anteile am Monatstotal' : 'Anteile am Total der ausgewählten Monate';
    const anteil = { kg: 'anteilKg', umsatz: 'anteilUmsatz', db: 'anteilDb' }[k];
    const html = zeilen.map((z) => {
      const vergleich = k === 'spanne' ? z.spanne : z[anteil];
      const breite = ist(z[k]) ? Math.max(0, Math.min(100, Math.abs(Number(z[k])) / max * 100)) : 0;
      return `<tr><td class="ctl-rep" data-label="Vertreter">${esc(z.name)}</td><td class="ctl-zahl" data-label="Kg">${esc(kg(z.kg))}</td><td class="ctl-anteil">${esc(pct(z.anteilKg))}</td>
        <td class="ctl-zahl" data-label="Umsatz">${esc(euro(z.umsatz))}</td><td class="ctl-anteil">${esc(pct(z.anteilUmsatz))}</td><td class="ctl-zahl" data-label="DB">${esc(euro(z.db))}</td>
        <td class="ctl-anteil">${esc(pct(z.anteilDb))}</td><td class="ctl-zahl" data-label="Spanne">${esc(pct(z.spanne))}</td>
        <td data-label="${esc(KENNZAHL[k])} im Vergleich"><div class="ctl-barlabel"><span>${ist(z[k]) ? esc(pct(vergleich)) : 'Keine Daten'}</span></div><progress max="100" value="${breite}" aria-label="${esc(KENNZAHL[k])} ${esc(pct(vergleich))}"></progress></td></tr>`;
    });
    if (!zeilen.length) html.push(`<tr><td class="ctl-empty" colspan="9">${monate.length ? 'Bitte mindestens einen Vertreter auswählen.' : 'Bitte Monate auswählen.'}</td></tr>`);
    html.push(`<tr class="ctl-total"><td data-label="Vertreter">Summe</td><td class="ctl-zahl" data-label="Kg">${esc(kg(t.kg))}</td><td class="ctl-anteil">${ist(t.kg) ? '100,00 %' : '–'}</td>
      <td class="ctl-zahl" data-label="Umsatz">${esc(euro(t.umsatz))}</td><td class="ctl-anteil">${ist(t.umsatz) ? '100,00 %' : '–'}</td><td class="ctl-zahl" data-label="DB">${esc(euro(t.db))}</td>
      <td class="ctl-anteil">${ist(t.db) ? '100,00 %' : '–'}</td><td class="ctl-zahl" data-label="Spanne">${esc(pct(t.spanne))}</td><td></td></tr>`);
    $('#ctl-u-vertreterzeilen').innerHTML = html.join('');
  }
  const monatsstatus = (monat, auswahl) => !auswahl.length ? 'Keine Vertreter ausgewählt'
    : auswahl.some((r) => ['kg', 'umsatz', 'db'].some((k) => wert(monat, r.nr, k) !== null)) ? 'Daten vorhanden' : 'Noch keine Daten';
  const einzeln = (auswahl) => auswahl.length > 1 && auswahl.length < reps().length;   // Teilauswahl mehrerer Vertreter: je Vertreter getrennt
  function liniendiagramm(monate, k, auswahl, summen) {
    if (!monate.length) return '<div class="ctl-empty">Bitte Monate auswählen.</div>';
    const reihen = einzeln(auswahl)
      ? auswahl.map((r) => ({ name: r.anzeige, werte: monate.map((m) => gesamt([m], [r])[k]) }))
      : [{ name: auswahl.length === 1 ? auswahl[0].anzeige : 'Summe der Auswahl', werte: summen.map((t) => t[k]) }];
    const zahlen = reihen.flatMap((x) => x.werte).filter(ist).map(Number);
    if (!zahlen.length) return '<div class="ctl-empty">Für die Auswahl liegen keine Werte vor.</div>';
    let tief = Math.min(0, ...zahlen), hoch = Math.max(0, ...zahlen); if (tief === hoch) hoch = tief + 1;
    const W = 900, oben = 24, basis = 230, links = 58, rechts = 16, pw = W - links - rechts, ph = basis - oben;
    const x = (i) => monate.length === 1 ? links + pw / 2 : links + i * pw / (monate.length - 1), y = (v) => basis - (Number(v) - tief) / (hoch - tief) * ph;
    const farben = ['#347a55', '#39769a', '#bb7540', '#8b65a5', '#d05a62', '#5597a3', '#7d8c3b', '#b35c91', '#4e6d59', '#7474b8', '#ca9b32', '#5d8190'];
    const skala = Array.from({ length: 5 }, (_, i) => tief + (hoch - tief) * i / 4), beschr = (v) => k === 'spanne' ? pct(v) : fmt(v, 0);
    const spalten = 3, breite = 285, legY = 282, h = legY + Math.ceil(reihen.length / spalten) * 23 + 10;
    let svg = `<div class="ctl-linien-wrap"><svg class="ctl-liniendiagramm" viewBox="0 0 ${W} ${h}" role="img" aria-label="Liniendiagramm ${esc(KENNZAHL[k])} nach Monat"><title>${esc(KENNZAHL[k])} nach Monat</title>`;
    skala.forEach((v) => { const yy = y(v); svg += `<line x1="${links}" y1="${yy}" x2="${W - rechts}" y2="${yy}" stroke="rgba(100,110,100,.22)"/><text x="${links - 7}" y="${yy + 4}" text-anchor="end">${esc(beschr(v))}</text>`; });
    svg += `<line x1="${links}" y1="${oben}" x2="${links}" y2="${basis}" stroke="rgba(100,110,100,.35)"/><line x1="${links}" y1="${y(0)}" x2="${W - rechts}" y2="${y(0)}" stroke="rgba(100,110,100,.45)" stroke-dasharray="4 4"/>`;
    monate.forEach((m, i) => { svg += `<text x="${x(i)}" y="${basis + 22}" text-anchor="middle">${esc(monatsname(m).slice(0, 3))}</text>`; });
    reihen.forEach((r, ri) => {
      const farbe = farben[ri % farben.length], punkte = r.werte.map((v, i) => ist(v) ? [x(i), y(v)] : null), ok = punkte.filter(Boolean);
      if (ok.length > 1) svg += `<polyline fill="none" stroke="${farbe}" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round" points="${ok.map((p) => p.join(',')).join(' ')}"/>`;
      punkte.forEach((p, i) => { if (p) svg += `<circle cx="${p[0]}" cy="${p[1]}" r="4" fill="${farbe}"><title>${esc(r.name)} · ${esc(monatsname(monate[i]))}: ${esc(anzeige(k, r.werte[i]))}</title></circle>`; });
    });
    reihen.forEach((r, i) => { const xx = links + (i % spalten) * breite, yy = legY + Math.floor(i / spalten) * 23, farbe = farben[i % farben.length]; svg += `<line x1="${xx}" y1="${yy}" x2="${xx + 20}" y2="${yy}" stroke="${farbe}" stroke-width="3"/><text x="${xx + 27}" y="${yy + 4}">${esc(r.name)}</text>`; });
    return svg + '</svg></div>';
  }
  function zeichneMonate(monate, auswahl) {
    const k = $('#ctl-u-monatskennzahl').value || 'umsatz', art = $('#ctl-u-diagrammart').value || 'balken';
    const summen = monate.map((m) => ({ monat: m, ...gesamt([m], auswahl) }));
    $('#ctl-u-diagrammhinweis').textContent = !monate.length ? 'Bitte Monate auswählen.'
      : art === 'linie' && einzeln(auswahl) ? `${KENNZAHL[k]} je Vertreter – eine Linie je Vertreter.` : `${KENNZAHL[k]} der Auswahl nach Monat.`;
    if (art === 'linie') $('#ctl-u-diagramm').innerHTML = liniendiagramm(monate, k, auswahl, summen);
    else {
      const top = Math.max(1, ...summen.map((z) => Math.abs(Number(z[k]) || 0)));
      $('#ctl-u-diagramm').innerHTML = `<div class="ctl-balkenliste">${summen.map((z) => { const b = ist(z[k]) ? Math.max(0, Math.min(100, Math.abs(Number(z[k])) / top * 100)) : 0; const status = monatsstatus(z.monat, auswahl); return `<div class="ctl-monatsbalken"><div class="ctl-monatsname">${esc(monatsname(z.monat))}<small>${esc(status)}</small></div><progress max="100" value="${b}" aria-label="${esc(monatsname(z.monat))} ${esc(anzeige(k, z[k]))}"></progress><div class="ctl-monatswert">${esc(anzeige(k, z[k]))}</div></div>`; }).join('')}</div>`;
    }
    const zeile = (titel, z, status = '', klasse = '') => `<tr${klasse ? ` class="${klasse}"` : ''}><td class="ctl-rep" data-label="Monat">${esc(titel)}</td><td class="ctl-zahl" data-label="Kg">${esc(kg(z.kg))}</td><td class="ctl-zahl" data-label="Umsatz">${esc(euro(z.umsatz))}</td><td class="ctl-zahl" data-label="DB">${esc(euro(z.db))}</td><td class="ctl-zahl" data-label="Spanne">${esc(pct(z.spanne))}</td><td data-label="Status">${esc(status)}</td></tr>`;
    let html = monate.length ? summen.map((t) => { const st = monatsstatus(t.monat, auswahl); return zeile(`${monatsname(t.monat)} ${S.jahr}`, t, st, st === 'Daten vorhanden' ? '' : 'ctl-ohne-daten'); }).join('') : '<tr><td colspan="6" class="ctl-empty">Bitte Monate auswählen.</td></tr>';
    if (monate.length > 1) {
      html += zeile(monate.length === MONATE().length ? 'Jahr gesamt' : 'Zeitraum gesamt', gesamt(monate, auswahl), '', 'ctl-total');
      html += zeile('Durchschnitt je Monat', { kg: schnitt(summen.map((x) => x.kg)), umsatz: schnitt(summen.map((x) => x.umsatz)), db: schnitt(summen.map((x) => x.db)), spanne: schnitt(summen.map((x) => x.spanne)) }, 'Monate mit Werten', 'ctl-total');
    }
    $('#ctl-u-monatszeilen').innerHTML = html;
  }
  function zeichneUebersicht() {
    if (!S.d) return;
    const monate = gewMonate(), auswahl = gewReps();
    zeichneKennzahlen(monate, auswahl); zeichneVertreter(monate, auswahl); zeichneMonate(monate, auswahl);
    const g = S.d.geaendert;
    $('#ctl-u-stand').textContent = g && g.t ? `Aus den importierten Umsatzdaten · letzter Import ${new Date(g.t).toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' })}${g.vonName ? ' · ' + g.vonName : ''}`
      : 'Noch keine Umsatzdaten importiert (Verwaltung → Import → „Umsätze je Kunde und Artikel“).';
    $('#ctl-u-fussnote').textContent = 'Kg, Umsatz und DB aus den importierten Umsatzdaten (berechnete Positionen); Vertreter = Hauptvertreter des Kunden nach den heutigen Stammdaten. Spanne = DB ÷ Umsatz. Anteile beziehen sich auf die Summe der ausgewählten Vertreter im gewählten Zeitraum.'
      + (S.d.rechte && S.d.rechte.ek ? '' : ' DB und Spanne nur mit den Rechten „Umsatzauswertung: Einkaufswerte …“ und „Einkaufspreise (EK) ansehen“.');
  }
  function zeigeTab(tab) {
    if (!tab) tab = S.mitDaten ? 'auswertung' : 'uebersicht';   // ohne Angabe: Auswertung, sobald Umsatzdaten importiert sind
    S.tab = tab === 'auswertung' ? 'auswertung' : 'uebersicht';
    $$('#ctl-u-tabs [role="tab"]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === S.tab)));
    $('#ctl-u-uebersicht').hidden = S.tab !== 'uebersicht'; $('#ctl-u-filter').hidden = S.tab !== 'uebersicht';
    $('#ctl-u-auswertung').hidden = S.tab !== 'auswertung'; $('#ctl-u-stand').hidden = S.tab === 'auswertung';
    if (S.tab === 'auswertung' && !S.auswertungGeladen && C.umsatzAuswertung) { S.auswertungGeladen = true; C.umsatzAuswertung.anzeigen($('#ctl-u-auswertung')); }
    C.hashSetzen(S.tab === (S.mitDaten ? 'auswertung' : 'uebersicht') ? '' : S.tab);
  }

  /* ---------- Laden ---------- */
  function setzeDaten(d) {
    S.d = d;
    const vorhanden = new Set(d.vertreter.map((r) => r.nr));
    S.vertreter = S.vertreter.size ? new Set([...S.vertreter].filter((nr) => vorhanden.has(nr))) : new Set(vorhanden);
    if (!S.vertreter.size) S.vertreter = new Set(vorhanden);
  }
  /* Ein Jahr vom Server laden (die Werte rechnet der Server aus den Umsatzdaten) */
  async function jahrLaden(jahr) {
    $('#ctl-u-uebersicht').classList.add('laedt');
    const r = await C.api('controlling_umsatz', null, '&jahr=' + encodeURIComponent(jahr));
    $('#ctl-u-uebersicht').classList.remove('laedt');
    if (r.status === 401) { C.zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { C.toast(C.fehlerText(r, 'Das Jahr konnte nicht geladen werden'), true); return; }
    setzeDaten(r.data); S.jahr = r.data.jahr;
    zeichneJahre(); zeichneVertreterfilter(); zeichneUebersicht();
  }
  async function anzeigen(box, rechte, tab) {
    S.box = box; S.rechte = rechte;
    box.innerHTML = '<p class="ctl-hilfe">Umsatzstatistik wird geladen …</p>';
    const r = await C.api('controlling_umsatz');
    if (r.status === 401) { C.zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { box.innerHTML = `<p class="ctl-fehler" role="alert">${esc(C.fehlerText(r, 'Die Umsatzstatistik konnte nicht geladen werden'))}</p>`; return; }
    box.innerHTML = GERUEST;
    setzeDaten(r.data);
    S.mitDaten = !!(r.data.umsatzdaten && r.data.umsatzdaten.vorhanden);
    S.monate = new Set(MONATE().map((m) => m.nr));
    S.jahr = r.data.jahr;   // jüngstes Jahr mit Umsatzdaten
    zeichneJahre(); zeichneMonatsfilter(); zeichneVertreterfilter(); zeichneUebersicht();

    $('#ctl-u-tabs').addEventListener('click', (ev) => { const b = ev.target.closest('[role="tab"]'); if (b) zeigeTab(b.dataset.tab); });
    $('#ctl-u-jahr').addEventListener('change', () => jahrLaden($('#ctl-u-jahr').value));
    $('#ctl-u-monatsoptionen').addEventListener('change', (ev) => {
      const c = ev.target.closest('input[type="checkbox"]'); if (!c) return;
      if (c.hasAttribute('data-alle-monate')) S.monate = c.checked ? new Set(MONATE().map((m) => m.nr)) : new Set();
      else if (c.checked) S.monate.add(c.dataset.monat); else S.monate.delete(c.dataset.monat);
      zeichneMonatsfilter(); zeichneUebersicht();
    });
    $('#ctl-u-vertreteroptionen').addEventListener('change', (ev) => {
      const c = ev.target.closest('input[type="checkbox"]'); if (!c) return;
      if (c.hasAttribute('data-alle-vertreter')) S.vertreter = c.checked ? new Set(reps().map((r) => r.nr)) : new Set();
      else if (c.checked) S.vertreter.add(c.dataset.vertreter); else S.vertreter.delete(c.dataset.vertreter);
      zeichneVertreterfilter(); zeichneUebersicht();
    });
    document.addEventListener('click', (ev) => { ['#ctl-u-zeitfilter', '#ctl-u-vertreterfilter'].forEach((id) => { const f = $(id); if (f && f.open && !f.contains(ev.target)) f.open = false; }); });
    $('#ctl-u-kennzahl').addEventListener('change', () => { S.kennzahl = $('#ctl-u-kennzahl').value; zeichneUebersicht(); });
    $('#ctl-u-monatskennzahl').addEventListener('change', zeichneUebersicht);
    $('#ctl-u-diagrammart').addEventListener('change', zeichneUebersicht);
    zeigeTab(tab);
  }

  C.bereich('umsatz', { anzeigen });
})();
