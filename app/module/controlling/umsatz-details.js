/* STAFL-Plattform · Controlling · Umsatzstatistik: Pop-ups der Auswertung (Designvorschlag 01.11.2026 – Details im Pop-up statt
   Umbau der Seite). Ein Vertreter, eine Kundengruppe, eine Artikelgruppe, eine Fleischart: Kennzahlen mit Vorjahr, Monatsbalken,
   Kunden (Suche, Klick → Kunde) und meistgekaufte Artikel (Klick → Artikel). Ein Kunde: Kennzahlen mit letztem Kauf und
   Liefertagen, Reiter „Artikel“ (Suche, Menge, Umsatz, Ø Preis, ± Vorjahr, zuletzt; „nicht mehr gekauft“ = im Vorjahr ja, jetzt
   nicht) und „Lieferungen“. Ein Artikel: seine Käufer. „Zurück“ führt zum vorigen Pop-up, „Als Filter übernehmen“ setzt den
   Filter der Seite. Listen sortierbar nach Umsatz, Menge, Rohmarge oder Rohmarge % (höchste/niedrigste zuerst; Vorgabe = Kennzahl
   der Rangliste), z. B. die Artikel eines Kunden oder die Käufer eines Artikels nach Rohmarge. Daten: controlling_umsatz_detail mit
   Zeitraum und Filtern der Seite (umsatz-auswertung.js, Schnittstelle „kontext“); EK-Werte und Rohmarge nur, wenn der Server sie
   liefert (controlling.umsatz_ek und bestand.einkaufspreise). */
'use strict';
(() => {
  const C = window.STAFL_CONTROLLING;
  const esc = C.esc, F = C.umsatzFormat;
  const $ = (s, el = document) => el.querySelector(s);
  const ART = { vertreter: 'Vertreter', kundengruppe: 'Kundengruppe', kunde: 'Kunde', vkgruppe: 'Artikelgruppe', fleischart: 'Fleischart', artikel: 'Artikel' };
  const LISTE_ANFANG = 100, ARTIKEL_ANFANG = 10;
  const D = { ctx: null, stapel: [], d: null, reiter: 'artikel', suche: '', alle: false, laden: 0, verbunden: new WeakSet(), rang: 'umsatz', auf: false };

  const heute = () => { const t = new Date(); return new Date(t.getFullYear(), t.getMonth(), t.getDate()); };
  const tageSeit = (iso) => Math.round((heute() - new Date(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)))) / 86400000);
  const seitText = (iso) => { const n = tageSeit(iso); return n <= 0 ? 'heute' : n === 1 ? 'gestern' : `vor ${F.ganz(n)} Tagen`; };
  const WOCHENTAG = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
  const wochentag = (iso) => WOCHENTAG[new Date(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10))).getDay()];

  async function oeffnen(dim, wert, ctx, neu = true) {
    D.ctx = ctx;
    const dlg = ctx.dialog;
    if (!D.verbunden.has(dlg)) { verbinden(dlg); D.verbunden.add(dlg); }
    if (neu) { D.stapel = []; D.rang = ctx.rang || 'umsatz'; D.auf = !!ctx.auf; }
    D.stapel.push({ dim, wert });
    D.reiter = dim === 'kunde' ? 'artikel' : 'kunden'; D.suche = ''; D.alle = false; D.d = null;
    dlg.innerHTML = `<div class="dlg"><div class="dlg-head"><div><p class="ctl-eyebrow">${esc(ART[dim])}</p><h2 id="ctl-ua-d-titel">Wird geladen …</h2></div>
      <button type="button" class="ctl-rund" data-schliessen aria-label="Schließen">${F.ICON.zu}</button></div><div class="dlg-body"><p class="ctl-hilfe">Umsätze werden zusammengezählt …</p></div></div>`;
    if (!dlg.open) dlg.showModal();
    const nr = ++D.laden;
    const r = await C.api('controlling_umsatz_detail', null, ctx.anfrage({ dim, wert }));
    if (nr !== D.laden || !dlg.open) return;
    if (r.status === 401) { dlg.close(); C.zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { $('.dlg-body', dlg).innerHTML = `<p class="ctl-fehler" role="alert">${esc(C.fehlerText(r, 'Die Details konnten nicht geladen werden'))}</p>`; $('#ctl-ua-d-titel', dlg).textContent = ART[dim]; return; }
    D.d = r.data;
    zeichne();
  }

  /* ---------- Bausteine ---------- */
  function kachel(name, wert, sub = '', voll = '') {
    return `<div class="ctl-ud-kpi"><span>${esc(name)}</span><b title="${esc(voll || wert)}">${esc(wert)}</b><small>${sub}</small></div>`;
  }
  function kennzahlen() {
    const d = D.d, s = d.summe, v = d.summeVj;
    const k = [kachel('Umsatz', F.euroKachel(s.umsatz), v ? F.deltaHtml(s.umsatz, v.umsatz) + ' zum Vorjahr' : '', F.euro(s.umsatz)),
      kachel('Menge', F.menge(s.menge), v ? F.deltaHtml(s.menge, v.menge) + ' zum Vorjahr' : '')];
    if (d.ek) k.push(kachel('Rohmarge', F.euroKachel(F.db(s)), `${esc(F.pct(F.spanne(s)))}${v ? ' · ' + F.ppHtml(F.spanne(s), F.spanne(v)) + ' zum VJ' : ''}`, F.euro(F.db(s))));
    else k.push(kachel('Ø Preis', F.preis(s), v ? `Vorjahr ${esc(F.preis(v))}` : ''));
    if (d.dim === 'kunde') {
      const tage = d.tage || [];
      const rhythmus = tage.length > 1 ? Math.max(1, Math.round(tageSeit(tage[tage.length - 1].tag) - tageSeit(tage[0].tag)) / (tage.length - 1)) : null;
      const pause = D.ctx && D.ctx.pause ? D.ctx.pause(d.wert) : null;   // aus der Liste „Bestellpausen“ der Seite
      k.push(kachel('Letzter Kauf', s.zuletzt ? F.tag(s.zuletzt) : '–', pause ? `<span class="ctl-ua-marke pause">Bestellpause</span>seit ${esc(F.ganz(pause.pause))} Tagen`
        : s.zuletzt ? esc(seitText(s.zuletzt)) : 'im Zeitraum keiner'));
      k.push(kachel('Liefertage', F.ganz(tage.length), rhythmus ? `etwa alle ${esc(F.ganz(Math.round(rhythmus)))} Tage` : ''));
    } else {
      const dk = v ? s.kunden - v.kunden : null;
      k.push(kachel(d.dim === 'artikel' ? 'Käufer' : 'Kunden', F.ganz(s.kunden), dk === null ? `${esc(F.ganz(s.artikel))} Artikel` : `<span class="ctl-ua-delta ${dk >= 0 ? 'plus' : 'minus'}">${dk >= 0 ? '+' : '−'}${esc(F.ganz(Math.abs(dk)))}</span> zum Vorjahr`));
    }
    return `<div class="ctl-ud-kpis${k.length > 4 ? ' fuenf' : ''}">${k.join('')}</div>`;
  }
  const passt = (z) => { const q = D.suche.trim().toLocaleLowerCase('de-DE'); return !q || z.name.toLocaleLowerCase('de-DE').includes(q) || z.nr.toLocaleLowerCase('de-DE').includes(q); };
  const suchfeld = (platzhalter) => `<label class="ctl-ud-suche">${F.ICON.suche}<input type="search" data-ud-suche value="${esc(D.suche)}" placeholder="${esc(platzhalter)}" aria-label="${esc(platzhalter)}"></label>`;

  /* Sortierung der Listen: Kennzahl (Rohmarge nur mit EK-Werten) und Richtung */
  function sortierwahl() {
    const opt = Object.entries(F.RANG).filter(([, k]) => !k.ek || D.d.ek);
    return `<div class="ctl-ud-sortierung"><label>Sortiert nach <select data-ud-rang>${opt.map(([id, k]) => `<option value="${id}"${id === D.rang ? ' selected' : ''}>${esc(k.name)}</option>`).join('')}</select></label>
      <button type="button" class="ctl-ua-richtung" data-ud-richtung aria-pressed="${D.auf}">${D.auf ? '↑ niedrigste zuerst' : '↓ höchste zuerst'}</button></div>`;
  }
  const geordnet = (l) => F.rangSortieren(l, D.rang, D.auf);
  const trenner = (l, i) => (l[i].klein && (i === 0 || !l[i - 1].klein) ? '<p class="ctl-ud-trenner">Wenig Umsatz mit Einkaufspreis – Rohmarge % wenig aussagekräftig</p>' : '');
  const ekZellen = (w) => `<span class="ctl-zahl${F.db(w) < 0 ? ' ctl-ua-negativ' : ''}" data-label="Rohmarge">${esc(F.euro(F.db(w)))}</span><span class="ctl-zahl" data-label="Rohmarge %">${esc(F.pct(F.spanne(w)))}</span>`;
  /* Kunden einer Gruppe bzw. Käufer eines Artikels (mit EK-Recht mit Rohmarge je Kunde) */
  function kundenListe() {
    const d = D.d, alle = geordnet(d.kunden.filter(passt)), zeigen = D.alle ? alle : alle.slice(0, LISTE_ANFANG), mitMenge = d.dim === 'artikel', k = F.RANG[D.rang];
    const cls = `${mitMenge ? ' mit-menge' : ''}${d.ek ? ' mit-ek' : ''}`;
    const kopf = `<div class="ctl-ud-zeile kopf${cls}" aria-hidden="true"><span>Kunde</span>${mitMenge ? '<span>Menge</span>' : ''}<span>Umsatz</span>${d.ek ? '<span>Rohmarge</span><span>%</span>' : ''}<span>${d.vorjahr ? '± VJ' : ''}</span><span>Zuletzt</span><span></span></div>`;
    return `<section class="ctl-ud-teil" aria-label="${d.dim === 'artikel' ? 'Käufer dieses Artikels' : 'Kunden'}">
      <div class="ctl-ud-teilkopf"><h3>${d.dim === 'artikel' ? 'Wer kauft diesen Artikel?' : 'Kunden'} <small>${esc(F.ganz(d.kundenGesamt))}</small></h3>${suchfeld('Kunde suchen')}</div>
      ${alle.length ? kopf + zeigen.map((z, i) => `${trenner(zeigen, i)}<button type="button" class="ctl-ud-zeile${cls}" data-ud-oeffnen="kunde" data-wert="${esc(z.nr)}">
        <span class="ctl-ud-name"><b>${esc(z.name)}</b><small>${esc(z.sub)}</small></span>${mitMenge ? `<span class="ctl-zahl" data-label="Menge">${esc(F.menge(z.werte.menge))}</span>` : ''}
        <b class="ctl-zahl" data-label="Umsatz">${esc(F.euro(z.werte.umsatz))}</b>${d.ek ? ekZellen(z.werte) : ''}<span class="ctl-zahl" data-label="± VJ ${esc(k.name)}">${d.vorjahr ? k.delta(z.werte, z.vj) : ''}</span>
        <span class="ctl-zahl ctl-ud-leise" data-label="Zuletzt">${z.zuletzt ? esc(F.tag(z.zuletzt)) : '–'}</span>${F.ICON.weiter}</button>`).join('')
        + (alle.length > zeigen.length ? `<button type="button" class="ctl-ua-link ctl-ua-mehr" data-ud-alle>Alle ${esc(F.ganz(alle.length))} anzeigen</button>` : '')
      : '<p class="ctl-hilfe">Keine Kunden für diese Suche.</p>'}</section>`;
  }
  /* Meistgekaufte Artikel (Gruppe, Vertreter …) */
  function artikelBalken() {
    const d = D.d, k = F.RANG[D.rang], l = geordnet(d.artikel.filter((z) => z.werte.pos > 0)), max = Math.max(1e-9, ...l.map((z) => Math.abs(k.wert(z.werte) || 0)));
    const zeigen = D.alle ? l : l.slice(0, ARTIKEL_ANFANG);
    return `<section class="ctl-ud-teil" aria-label="Artikel"><div class="ctl-ud-teilkopf"><h3>Artikel nach ${esc(k.name)} <small>${esc(F.ganz(l.length))}</small></h3></div>
      ${zeigen.map((z, i) => { const w = k.wert(z.werte); return `${trenner(zeigen, i)}<button type="button" class="ctl-ud-artikel" data-ud-oeffnen="artikel" data-wert="${esc(z.nr)}">
        <span class="ctl-ud-artikelkopf"><span><b>${esc(z.name)}</b> <small>${esc(z.nr)}</small></span><b class="ctl-zahl${w < 0 ? ' ctl-ua-negativ' : ''}">${esc(w === null ? '–' : k.text(w))}</b></span>
        <span class="ctl-ua-spur${w < 0 ? ' minus' : ''}"><span style="width:${Math.min(100, (Math.abs(w || 0) / max) * 100).toFixed(1)}%"></span></span></button>`; }).join('') || '<p class="ctl-hilfe">Keine Artikel.</p>'}
      ${l.length > zeigen.length ? `<button type="button" class="ctl-ua-link ctl-ua-mehr" data-ud-alle>Alle ${esc(F.ganz(l.length))} anzeigen</button>` : ''}</section>`;
  }
  /* Kunde: seine Artikel */
  function kundeArtikel() {
    const d = D.d, gekauft = d.artikel.filter((z) => z.kaeufe > 0), alle = geordnet(gekauft.filter(passt)), zeigen = D.alle ? alle : alle.slice(0, LISTE_ANFANG), k = F.RANG[D.rang];   // gekauft = Kauf im Zeitraum (keine reine Gutschrift)
    const verloren = d.vorjahr ? d.artikel.filter((z) => !(z.kaeufe > 0) && z.vj && z.vj.umsatz > 0).slice(0, 12) : [];
    const ek = d.ek;
    const kopf = `<div class="ctl-ud-zeile kopf artikel${ek ? ' mit-ek' : ''}" aria-hidden="true"><span>Artikel</span><span>Menge</span><span>Umsatz</span><span>Ø Preis</span>${ek ? '<span>Rohmarge</span><span>%</span>' : ''}<span>${d.vorjahr ? '± VJ' : ''}</span><span>Zuletzt</span></div>`;
    return (verloren.length ? `<div class="ctl-ud-verloren" role="note"><b>Nicht mehr gekauft – im Vorjahr ja, in diesem Zeitraum nicht</b>
        <div>${verloren.map((z) => `<button type="button" class="ctl-ud-verlchip" data-ud-oeffnen="artikel" data-wert="${esc(z.nr)}">${esc(z.name)} <small>VJ ${esc(F.euroKurz(z.vj.umsatz))}</small></button>`).join('')}</div>
        <small>Ansatz fürs nächste Gespräch mit dem Kunden.</small></div>` : '')
      + `<div class="ctl-ud-teilkopf"><h3>Gekaufte Artikel <small>${esc(F.ganz(gekauft.length))}</small></h3>${suchfeld('Artikel dieses Kunden suchen')}</div>`
      + (alle.length ? kopf + zeigen.map((z, i) => `${trenner(zeigen, i)}<button type="button" class="ctl-ud-zeile artikel${ek ? ' mit-ek' : ''}" data-ud-oeffnen="artikel" data-wert="${esc(z.nr)}">
          <span class="ctl-ud-name"><b>${esc(z.name)}</b><small>${esc(z.sub)}</small></span><span class="ctl-zahl" data-label="Menge">${esc(F.menge(z.werte.menge))}</span>
          <b class="ctl-zahl" data-label="Umsatz">${esc(F.euro(z.werte.umsatz))}</b><span class="ctl-zahl" data-label="Ø Preis">${esc(F.preis(z.werte))}</span>
          ${ek ? ekZellen(z.werte) : ''}<span class="ctl-zahl" data-label="± VJ ${esc(k.name)}">${d.vorjahr ? k.delta(z.werte, z.vj) : ''}</span>
          <span class="ctl-zahl ctl-ud-leise" data-label="Zuletzt">${z.zuletzt ? esc(F.tag(z.zuletzt)) : '–'}</span></button>`).join('')
        + (alle.length > zeigen.length ? `<button type="button" class="ctl-ua-link ctl-ua-mehr" data-ud-alle>Alle ${esc(F.ganz(alle.length))} anzeigen</button>` : '')
      : '<p class="ctl-hilfe">Keine Artikel für diese Suche.</p>');
  }
  function kundeLieferungen() {
    const t = D.d.tage || [];
    return t.length ? `<div class="ctl-ud-zeile kopf tage" aria-hidden="true"><span>Liefertag</span><span>Positionen</span><span>Menge</span><span>Umsatz</span></div>`
      + t.slice(0, 400).map((x) => `<div class="ctl-ud-zeile tage"><span class="ctl-ud-name"><b>${esc(wochentag(x.tag))}, ${esc(F.tag(x.tag))}</b></span><span class="ctl-zahl" data-label="Positionen">${esc(F.ganz(x.werte.pos))}</span>
        <span class="ctl-zahl" data-label="Menge">${esc(F.menge(x.werte.menge))}</span><b class="ctl-zahl" data-label="Umsatz">${esc(F.euro(x.werte.umsatz))}</b></div>`).join('')
      : '<p class="ctl-hilfe">Im Zeitraum keine Lieferungen mit Berechnung.</p>';
  }

  function zeichne() {
    const dlg = D.ctx.dialog, d = D.d;
    const filter = D.ctx.filterText(d.dim);
    const zeit = `${F.monatsname(d.anfrage.von)} – ${F.monatsname(d.anfrage.bis)}${d.vorjahr ? ' · mit Vorjahr' : ''}`;
    const sub = d.dim === 'kunde' && d.kunde ? [d.wert, d.kunde.ort, d.kunde.gruppe, d.kunde.vertreter ? 'Vertreter ' + d.kunde.vertreter : ''].filter(Boolean).join(' · ') : d.sub;
    const inhalt = d.dim === 'kunde'
      ? `<div class="ctl-ud-reiterzeile"><div class="ctl-seg klein ctl-ud-reiter" role="tablist" aria-label="Ansicht des Kunden"><button type="button" role="tab" data-ud-reiter="artikel" aria-selected="${D.reiter === 'artikel'}">Artikel</button><button type="button" role="tab" data-ud-reiter="lieferungen" aria-selected="${D.reiter === 'lieferungen'}">Lieferungen</button></div>
        ${sortierwahl()}</div><div class="ctl-ud-reiterinhalt" role="tabpanel">${D.reiter === 'lieferungen' ? kundeLieferungen() : kundeArtikel()}</div>`
      : d.dim === 'artikel' ? sortierwahl() + kundenListe() : `${sortierwahl()}<div class="ctl-ud-spalten${d.ek ? ' breit' : ''}">${kundenListe()}${artikelBalken()}</div>`;
    const name = d.dim === 'kunde' ? d.name : d.name.replace(/^\S+ – /, '');
    const eyebrow = d.dim === 'kunde' ? 'Kunde' : d.dim === 'artikel' ? 'Artikel ' + d.wert : d.wert === '_' ? ART[d.dim] : `${ART[d.dim]} ${d.wert}${d.dim !== 'fleischart' && d.dim !== 'vertreter' && d.sub ? ' · ' + d.sub : ''}`;
    dlg.innerHTML = `<div class="dlg ctl-ud" data-dim="${esc(d.dim)}">
      <div class="dlg-head">${D.stapel.length > 1 ? `<button type="button" class="ctl-rund ctl-ud-zurueck" data-ud-zurueck aria-label="Zurück">${F.ICON.zurueck}</button>` : ''}
        <div class="ctl-ud-titel"><p class="ctl-eyebrow">${esc(eyebrow)}</p><h2 id="ctl-ua-d-titel">${esc(name)}</h2>
          <p>${esc([d.dim === 'kunde' || d.dim === 'artikel' ? sub : '', zeit, filter].filter(Boolean).join(' · '))}</p></div>
        <button type="button" class="ctl-rund" data-schliessen aria-label="Schließen">${F.ICON.zu}</button></div>
      <div class="dlg-body">${kennzahlen()}
        <div class="ctl-ud-monate"><div class="ctl-ua-svgwrap" data-ud-diagramm></div></div>
        ${inhalt}</div>
      <div class="dlg-foot"><button type="button" class="btn ctl-ud-filter" data-ud-filter>Als Filter übernehmen</button><button type="button" class="btn" data-ud-csv>CSV</button>
        <span class="spacer"></span><button type="button" class="btn primary" data-schliessen>Schließen</button></div></div>`;
    const dia = $('[data-ud-diagramm]', dlg);
    dia.innerHTML = F.monatsSvg(d.monate, 'umsatz', !!d.vorjahr, dia.clientWidth || 600, 120);
  }
  /* Nur die Liste neu zeichnen (Suche, alle anzeigen, Reiter) – Eingabefeld behält den Fokus */
  function zeichneListe() {
    const dlg = D.ctx.dialog, aktiv = document.activeElement && document.activeElement.matches('[data-ud-suche]');
    const ziel = D.d.dim === 'kunde' ? $('.ctl-ud-reiterinhalt', dlg) : D.d.dim === 'artikel' ? $('.ctl-ud-teil', dlg) : $('.ctl-ud-spalten', dlg);
    const html = D.d.dim === 'kunde' ? (D.reiter === 'lieferungen' ? kundeLieferungen() : kundeArtikel()) : D.d.dim === 'artikel' ? kundenListe() : kundenListe() + artikelBalken();
    if (D.d.dim === 'artikel') ziel.outerHTML = html; else ziel.innerHTML = html;
    dlg.querySelectorAll('[data-ud-reiter]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.udReiter === D.reiter)));
    const so = $('.ctl-ud-sortierung', dlg);
    if (so) { so.outerHTML = sortierwahl(); $('.ctl-ud-sortierung', dlg).hidden = D.d.dim === 'kunde' && D.reiter === 'lieferungen'; }   // Lieferungen: keine Sortierung
    if (aktiv) { const f = $('[data-ud-suche]', dlg); if (f) { f.focus(); f.setSelectionRange(f.value.length, f.value.length); } }
  }
  function csv() {
    const d = D.d, zahl = F.zahl, name = d.name.replace(/^\S+ – /, '');
    if (d.dim === 'kunde' && D.reiter === 'lieferungen') {
      F.csvLaden(`Lieferungen ${name} ${d.anfrage.von} bis ${d.anfrage.bis}.csv`, [['Liefertag', 'Positionen', 'Menge', 'Umsatz €'],
        ...(d.tage || []).map((t) => [F.tag(t.tag), zahl(t.werte.pos, 0), zahl(t.werte.menge / 1000, 3), zahl(t.werte.umsatz / 100, 2)])]);
      return;
    }
    const l = geordnet(d.dim === 'kunde' ? d.artikel : d.kunden);
    const was = d.dim === 'kunde' ? 'Artikel' : 'Kunde';
    F.csvLaden(`${d.dim === 'kunde' ? 'Artikel von' : d.dim === 'artikel' ? 'Käufer von' : 'Kunden von'} ${name} ${d.anfrage.von} bis ${d.anfrage.bis}.csv`,
      [[was, 'Nummer', 'Umsatz €', ...(d.vorjahr ? ['Umsatz Vorjahr €'] : []), 'Menge', 'Positionen', 'Zuletzt', ...(d.ek ? ['Rohmarge €', 'Rohmarge %'] : [])],
        ...l.map((z) => [z.name, z.nr, zahl(z.werte.umsatz / 100, 2), ...(d.vorjahr ? [z.vj ? zahl(z.vj.umsatz / 100, 2) : ''] : []), zahl(z.werte.menge / 1000, 3), zahl(z.werte.pos, 0),
          z.zuletzt ? F.tag(z.zuletzt) : '', ...(d.ek ? [zahl(F.db(z.werte) / 100, 2), F.spanne(z.werte) === null ? '' : zahl(F.spanne(z.werte) * 100, 1)] : [])])]);
  }
  function verbinden(dlg) {
    dlg.addEventListener('click', (ev) => {
      if (ev.target === dlg || ev.target.closest('[data-schliessen]')) { dlg.close(); return; }
      if (!D.d) return;
      const o = ev.target.closest('[data-ud-oeffnen]');
      if (o) { oeffnen(o.dataset.udOeffnen, o.dataset.wert, D.ctx, false); return; }
      if (ev.target.closest('[data-ud-zurueck]')) { D.stapel.pop(); const v = D.stapel.pop(); if (v) oeffnen(v.dim, v.wert, D.ctx, false); return; }
      const r = ev.target.closest('[data-ud-reiter]');
      if (r) { D.reiter = r.dataset.udReiter; D.alle = false; zeichneListe(); return; }
      if (ev.target.closest('[data-ud-alle]')) { D.alle = true; zeichneListe(); return; }
      if (ev.target.closest('[data-ud-richtung]')) { D.auf = !D.auf; zeichneListe(); return; }
      if (ev.target.closest('[data-ud-filter]')) { const { dim, wert } = D.d, name = D.d.name.replace(/^\S+ – /, ''); dlg.close(); D.ctx.filterSetzen(dim, wert); C.toast(`Filter gesetzt: ${ART[dim]} ${name}`); return; }
      if (ev.target.closest('[data-ud-csv]')) csv();
    });
    dlg.addEventListener('input', (ev) => { if (ev.target.matches('[data-ud-suche]') && D.d) { D.suche = ev.target.value; D.alle = false; zeichneListe(); } });
    dlg.addEventListener('change', (ev) => { if (ev.target.matches('[data-ud-rang]') && D.d) { D.rang = ev.target.value; D.auf = false; zeichneListe(); } });
    dlg.addEventListener('close', () => { D.laden++; D.stapel = []; D.d = null; });
  }

  C.umsatzDetails = { oeffnen };
})();
