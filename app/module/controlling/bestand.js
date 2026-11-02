/* STAFL-Plattform · Controlling · Bereich Bestandsverlauf (Designvorschlag 02.11.2026): Entwicklung des Bestands aus den täglich
   hochgeladenen Bestandslisten mit dem Absatz aus den Umsatzdaten – Kennzahlen (Bestand heute, Reichweite, Umschlag, Lagerwert
   bzw. Artikel am Lager), Diagramm (Bestand je Liste, Absatz je Tag), Liste je Artikel, Artikelgruppe oder Fleischart mit
   Mini-Verlauf und Hinweisen „lange am Lager“, „knapp“, „kein Absatz“, Pop-up je Zeile mit jeder Liste des Zeitraums, CSV.
   Daten: controlling_bestand_daten, controlling_bestand, controlling_bestand_detail (module/controlling/bestand.php) – alle
   Werte rechnet der Server; Lagerwert nur, wenn er ihn liefert (controlling.bestand_ek und bestand.einkaufspreise, GR-008).
   Meldet sich bei controlling.js an (STAFL_CONTROLLING.bereich); CSV und Symbole aus umsatz-auswertung.js (umsatzFormat). */
'use strict';
(() => {
  const C = window.STAFL_CONTROLLING;
  const esc = C.esc;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const F = () => C.umsatzFormat;

  /* ---------- Formate ---------- */
  const NF = (d) => new Intl.NumberFormat('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d });
  const ist = (v) => v !== null && v !== undefined && Number.isFinite(Number(v));
  const kg = (v) => (!ist(v) ? '–' : NF(Math.abs(v) < 100 && v % 1 !== 0 ? 1 : 0).format(v) + ' kg');
  const euro = (v) => (!ist(v) ? '–' : new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', minimumFractionDigits: 0, maximumFractionDigits: 0 }).format(v));
  const tage = (v) => (!ist(v) ? '–' : (v < 10 ? NF(v % 1 ? 1 : 0).format(v) : NF(0).format(v)) + (Math.round(v * 10) === 10 ? ' Tag' : ' Tage'));
  const mal = (v) => (!ist(v) ? '–' : NF(1).format(v) + ' ×');
  const tag = (d) => (d ? `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}` : '');
  const tagKurz = (d) => (d ? `${d.slice(8, 10)}.${d.slice(5, 7)}.` : '');
  const WOCHENTAG = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
  const wochentag = (d) => WOCHENTAG[new Date(Number(d.slice(0, 4)), Number(d.slice(5, 7)) - 1, Number(d.slice(8, 10))).getDay()];
  const tagnr = (d) => Math.round(Date.UTC(Number(d.slice(0, 4)), Number(d.slice(5, 7)) - 1, Number(d.slice(8, 10))) / 86400000);
  const delta = (z) => {
    if (z.delta === null || z.delta === undefined) return z.kg > 0 && !z.kgStart ? 'neu' : '–';
    if (Math.abs(z.delta) < 0.5) return '±0 %';
    return (z.delta > 0 ? '+' : '−') + NF(0).format(Math.abs(z.delta)) + ' %';
  };
  const HINWEIS = { lange: ['lange am Lager', 'lange'], knapp: ['knapp', 'knapp'], ohne: ['kein Absatz', 'ohne'] };
  const marke = (h) => (h && HINWEIS[h] ? `<span class="ctl-b-marke ${HINWEIS[h][1]}">${HINWEIS[h][0]}</span>` : '');
  const NACH = { artikel: ['Artikel', 'Artikel'], vkgruppe: ['Artikelgruppe', 'Artikelgruppen'], fleischart: ['Fleischart', 'Fleischarten'] };
  const ZEIT = [['30', '30 Tage'], ['90', '90 Tage'], ['365', '12 Monate'], ['eigen', 'Eigener Zeitraum']];
  const OHNE = '_';
  const FILTER = [{ id: 'ag', liste: 'vkgruppen', name: 'Artikelgruppe', ohne: 'ohne Artikelgruppe', nach: 'vkgruppe' },
                  { id: 'fa', liste: 'fleischarten', name: 'Fleischart', ohne: 'ohne Fleischart', nach: 'fleischart' }];
  /* Sortierungen der Liste: Wert, Richtung (null-Werte immer ans Ende) */
  const SORT = {
    kg: ['Bestand (höchster zuerst)', (z) => z.kg, false],
    reichweite: ['Reichweite (längste zuerst)', (z) => z.reichweite, false],
    reichweiteAuf: ['Reichweite (kürzeste zuerst)', (z) => z.reichweite, true],
    umschlagAuf: ['Umschlag (langsamster zuerst)', (z) => z.umschlag, true],
    umschlag: ['Umschlag (schnellster zuerst)', (z) => z.umschlag, false],
    delta: ['Veränderung (größter Zuwachs)', (z) => z.delta, false],
    deltaAuf: ['Veränderung (größter Rückgang)', (z) => z.delta, true],
    absatz: ['Absatz (höchster zuerst)', (z) => z.absatz, false],
    ekWert: ['Lagerwert (höchster zuerst)', (z) => z.ekWert, false, true],
  };
  const ANFANG = 50;

  const S = { box: null, g: null, d: null, zeit: '30', von: '', bis: '', nach: 'artikel', filter: {}, sort: 'kg', nur: false, suche: '', alle: false,
              wert: 'kg', laden: 0, detail: null, detailNr: 0, ro: null };

  /* ---------- Diagramm: Bestand je Liste (Linie, Punkte), darunter Absatz je Tag (Balken) ---------- */
  function schritt(spanne) {
    const roh = spanne / 3, p = Math.pow(10, Math.floor(Math.log10(Math.max(roh, 1e-9)))), n = roh / p;
    return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
  }
  function diagramm(reihe, absatzReihe, z, wert, breite, H) {
    const W = Math.max(280, Math.round(breite)), istEuro = wert === 'ekWert';
    const L = istEuro ? 70 : 54, R = 14, T = 16, unten = 22;
    const mitBalken = absatzReihe.length > 0, balkenH = mitBalken ? Math.round(H * 0.2) : 0, luecke = mitBalken ? 26 : 0;
    const linieUnten = H - unten - balkenH - luecke;
    const t0 = tagnr(z.von), span = Math.max(1, tagnr(z.bis) - t0), innen = W - L - R;
    const x = (d) => L + ((tagnr(d) - t0) / span) * innen;
    const werte = reihe.map((r) => Number(r[wert] || 0));
    let lo = werte.length ? Math.min(...werte) : 0, hi = werte.length ? Math.max(...werte) : 1;
    if (hi - lo < 1) { hi += 1; lo = Math.max(0, lo - 1); }
    const pad = (hi - lo) * 0.15; lo = Math.max(0, lo - pad); hi += pad;
    const st = schritt(hi - lo); lo = Math.floor(lo / st) * st; hi = Math.ceil(hi / st) * st;
    const y = (v) => T + ((hi - v) / (hi - lo || 1)) * (linieUnten - T);
    const achse = (v) => (istEuro ? euro(v) : NF(0).format(v));
    const name = istEuro ? 'Lagerwert' : 'Bestand';
    let svg = `<svg class="ctl-b-svg" width="${W}" height="${H}" viewBox="0 0 ${W} ${H}" role="img" aria-label="${esc(name)} je Liste${mitBalken ? ' und Absatz je Tag' : ''} vom ${esc(tag(z.von))} bis ${esc(tag(z.bis))}">`;
    for (let v = lo; v <= hi + st / 2; v += st) {
      svg += `<line class="ctl-b-gitter" x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}"></line><text class="ctl-b-achse" x="${L - 8}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end">${esc(achse(v))}</text>`;
    }
    if (mitBalken) {
      const yb = H - unten, amax = Math.max(1, ...absatzReihe.map((a) => a.kg)), bw = Math.max(1.5, Math.min(14, (innen / span) * 0.62));
      svg += `<line class="ctl-b-gitter" x1="${L}" x2="${W - R}" y1="${yb}" y2="${yb}"></line><text class="ctl-b-achse" x="${L - 8}" y="${yb - balkenH + 4}" text-anchor="end">${esc(NF(0).format(amax))}</text>`;
      absatzReihe.forEach((a) => {
        const h = Math.max(1, (a.kg / amax) * balkenH);
        svg += `<rect class="ctl-b-balken" x="${(x(a.d) - bw / 2).toFixed(1)}" y="${(yb - h).toFixed(1)}" width="${bw.toFixed(1)}" height="${h.toFixed(1)}" rx="1.5"><title>${esc(wochentag(a.d))} ${esc(tag(a.d))}: Absatz ${esc(kg(a.kg))}</title></rect>`;
      });
    }
    const n = Math.max(2, Math.min(6, Math.floor(innen / 110)));
    for (let i = 0; i < n; i++) {
      const d = new Date((t0 + Math.round((span * i) / (n - 1))) * 86400000).toISOString().slice(0, 10);
      svg += `<text class="ctl-b-achse" x="${x(d).toFixed(1)}" y="${H - 6}" text-anchor="${i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'}">${esc(tagKurz(d))}</text>`;
    }
    if (reihe.length) {
      const pts = reihe.map((r, i) => `${x(r.d).toFixed(1)},${y(werte[i]).toFixed(1)}`);
      if (reihe.length > 1) svg += `<path class="ctl-b-flaeche" d="M${pts[0].split(',')[0]} ${linieUnten}L${pts.join('L')}L${pts[pts.length - 1].split(',')[0]} ${linieUnten}Z"></path><polyline class="ctl-b-linie" points="${pts.join(' ')}"></polyline>`;
      const r0 = reihe.length > 60 ? 2.2 : 3.4;
      reihe.forEach((r, i) => {
        svg += `<circle class="ctl-b-punkt" cx="${pts[i].split(',')[0]}" cy="${pts[i].split(',')[1]}" r="${r0}"><title>${esc(wochentag(r.d))} ${esc(tag(r.d))}: ${esc(istEuro ? euro(werte[i]) : kg(werte[i]))}${!istEuro && r.zugang ? ` · erwartet ${esc(kg(r.zugang))}` : ''}</title></circle>`;
      });
      const [lx, ly] = pts[pts.length - 1].split(',').map(Number);
      svg += `<text class="ctl-b-wert" x="${Math.min(lx, W - R).toFixed(1)}" y="${Math.max(12, ly - 10).toFixed(1)}" text-anchor="end">${esc(istEuro ? euro(werte[werte.length - 1]) : kg(werte[werte.length - 1]))}</text>`;
    }
    return svg + '</svg>';
  }
  function spark(werte) {
    if (!werte || werte.length < 2) return '<svg class="ctl-b-spark" viewBox="0 0 110 28" aria-hidden="true"></svg>';
    const mn = Math.min(...werte), mx = Math.max(...werte), sp = mx - mn || 1;
    const pts = werte.map((w, i) => `${(3 + (i * 104) / (werte.length - 1)).toFixed(1)},${(25 - ((w - mn) / sp) * 22).toFixed(1)}`).join(' ');
    return `<svg class="ctl-b-spark" viewBox="0 0 110 28" aria-hidden="true"><polyline points="${pts}"></polyline></svg>`;
  }

  /* ---------- Gerüst ---------- */
  const GERUEST = () => `
    <div class="ctl-intro"><div><p class="ctl-eyebrow">Bestand · aus den täglichen Bestandslisten</p><h1>Bestandsverlauf</h1>
      <p class="ctl-intro-text">Wie sich der Bestand entwickelt, wie lange er reicht und wie schnell er sich dreht – je Artikel und Gruppe.</p></div>
      <p class="ctl-notiz ctl-stand" id="ctl-b-stand"></p></div>
    <div class="ctl-ua-leiste ctl-glas" id="ctl-b-leiste">
      <div class="ctl-seg" role="group" aria-label="Zeitraum" id="ctl-b-zeit">${ZEIT.map(([id, n]) => `<button type="button" data-zeit="${id}" aria-pressed="${id === S.zeit}">${n}</button>`).join('')}</div>
      <span class="ctl-b-eigen" id="ctl-b-eigen" hidden><label>von <input type="date" id="ctl-b-von"></label><label>bis <input type="date" id="ctl-b-bis"></label></span>
      <button type="button" class="ctl-ua-filterknopf" id="ctl-b-filterknopf">${F().ICON.filter}Filter<span class="ctl-ua-zahl" id="ctl-b-filterzahl" hidden></span></button>
      <span class="ctl-b-chips" id="ctl-b-chips"></span>
      <label class="ctl-b-suche">${F().ICON.suche}<span class="sr-only">Artikel suchen</span><input type="search" id="ctl-b-suche" placeholder="Artikel oder Nummer suchen" autocomplete="off"></label>
    </div>
    <p class="ctl-fehler" id="ctl-b-fehler" role="alert" hidden></p>
    <div id="ctl-b-inhalt"><p class="ctl-hilfe">Bestandsverlauf wird geladen …</p></div>
    <dialog class="modal wide ctl-dialog ctl-dialog-detail ctl-b-dlg" id="ctl-b-dialog" aria-labelledby="ctl-b-d-titel"></dialog>
    <dialog class="modal wide ctl-dialog" id="ctl-b-filterdialog" aria-labelledby="ctl-b-f-titel"></dialog>`;

  function anfrage(extra = {}) {
    const p = new URLSearchParams();
    if (S.zeit === 'eigen' && S.von && S.bis) { p.set('von', S.von); p.set('bis', S.bis); } else p.set('tage', S.zeit === 'eigen' ? '30' : S.zeit);
    p.set('nach', S.nach);
    FILTER.forEach((f) => { const w = S.filter[f.id]; if (w && w.size) p.set(f.id, [...w].join(',')); });
    Object.entries(extra).forEach(([k, v]) => p.set(k, v));
    return '&' + p.toString();
  }

  async function laden() {
    const nr = ++S.laden;
    $('#ctl-b-fehler', S.box).hidden = true;
    const r = await C.api('controlling_bestand', null, anfrage());
    if (nr !== S.laden) return;
    if (r.status === 401) { C.zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { const f = $('#ctl-b-fehler', S.box); f.textContent = C.fehlerText(r, 'Der Bestandsverlauf konnte nicht geladen werden'); f.hidden = false; return; }
    S.d = r.data;
    if (S.zeit !== 'eigen') { S.von = S.d.zeitraum.von; S.bis = S.d.zeitraum.bis; }
    zeichne();
  }

  /* ---------- Darstellung ---------- */
  function standText() {
    const d = S.d, z = d.zeitraum;
    if (!d.stand.listen) return 'Noch keine Bestandsliste gespeichert.';
    const teile = [`Stand: Liste vom <b>${esc(tag(z.letzte || d.stand.letzte))}</b> · ${esc(NF(0).format(z.listen))} ${z.listen === 1 ? 'Liste' : 'Listen'} im Zeitraum`];
    teile.push(d.stand.umsatzBis ? `Absatz aus den Umsatzdaten bis <b>${esc(tag(z.absatzBis || d.stand.umsatzBis))}</b>` : 'noch keine Umsatzdaten');
    return teile.join('<br>');
  }
  function kachel(name, wert, sub, extra = '') { return `<div class="ctl-kpi ctl-glas${extra}"><span>${name}</span><b title="${esc(wert)}">${esc(wert)}</b><small>${sub}</small></div>`; }
  function kennzahlen() {
    const d = S.d, s = d.summen, z = d.zeitraum, ek = d.rechte.ek;
    const k = [];
    const zu = s.zugang > 0 ? ` · dazu ${esc(kg(s.zugang))} erwartet` : '';
    k.push(kachel('Bestand heute', kg(s.kg), z.listen > 1 ? `${esc(delta(s))} ggü. ${esc(tagKurz(z.erste))}${zu}` : (zu ? zu.slice(3) : 'eine Liste im Zeitraum')));
    const auff = [s.lange ? `${NF(0).format(s.lange)} lange am Lager` : '', s.knapp ? `${NF(0).format(s.knapp)} knapp` : ''].filter(Boolean).join(', ');
    k.push(kachel('Reichweite', tage(s.reichweite), s.absatz === null ? 'ohne Umsatzdaten im Zeitraum' : `bei Ø ${esc(kg(s.absatzJeTag))} Absatz je Tag${auff ? ' · ' + esc(auff) : ''}`));
    k.push(kachel('Umschlag', mal(s.umschlag), s.umschlag === null ? 'ohne Umsatzdaten im Zeitraum' : `in ${esc(NF(0).format(z.absatzTage))} Tagen · hochgerechnet ${esc(mal(s.umschlagJahr))} im Jahr`));
    if (ek) {
      const anteil = s.kg > 0 ? Math.round((s.ekKg / s.kg) * 100) : null;
      k.push(kachel('Lagerwert (EK)', euro(s.ekWert), s.ekKg > 0 ? `Ø ${esc(new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(s.ekWert / s.ekKg))} je kg${anteil !== null && anteil < 100 ? ` · ${anteil} % der Menge mit EK` : ''}` : 'ohne Einkaufspreise'));
    } else {
      k.push(kachel('Artikel am Lager', NF(0).format(s.artikel), `in ${esc(NF(0).format(s.partien))} Partien`));
    }
    return `<div class="ctl-kpis ctl-b-kpis" id="ctl-b-kpis">${k.join('')}</div>`;
  }
  function entwicklung() {
    const ek = S.d.rechte.ek;
    return `<section class="ctl-panel ctl-glas ctl-b-panel" id="ctl-b-entwicklung"><div class="ctl-panelkopf ctl-b-kopf"><div><h2>Entwicklung</h2>
      <p class="ctl-hilfe">Bestand am Tag jeder Liste${S.d.absatzReihe.length ? ', darunter der Absatz je Tag aus den Umsatzdaten' : ''}.</p></div>
      ${ek ? `<div class="ctl-seg klein" role="group" aria-label="Wert" id="ctl-b-wert"><button type="button" data-wert="kg" aria-pressed="${S.wert === 'kg'}">Menge (kg)</button><button type="button" data-wert="ekWert" aria-pressed="${S.wert === 'ekWert'}">Lagerwert (€)</button></div>` : ''}</div>
      <div class="ctl-b-diagramm" id="ctl-b-diagramm"></div>
      <div class="ctl-b-legende"><span><i class="linie"></i>${S.wert === 'ekWert' ? 'Lagerwert (€)' : 'Bestand (kg)'}</span><span><i class="punkt"></i>Tag mit Bestandsliste</span>${S.d.absatzReihe.length && S.wert === 'kg' ? '<span><i class="balken"></i>Absatz je Tag (kg, aus den Umsatzdaten)</span>' : ''}</div></section>`;
  }
  function sichtbareZeilen() {
    const q = S.suche.trim().toLocaleLowerCase('de-DE');
    let z = S.d.zeilen.filter((x) => (!S.nur || x.hinweis) && (!q || x.name.toLocaleLowerCase('de-DE').includes(q) || String(x.sub || '').toLocaleLowerCase('de-DE').includes(q) || String(x.key).toLocaleLowerCase('de-DE').includes(q)));
    const [, wert, auf] = SORT[S.sort] || SORT.kg;
    z = z.slice().sort((a, b) => {
      const x = wert(a), y = wert(b);
      if (!ist(x) || !ist(y)) return (!ist(x)) - (!ist(y)) || b.kg - a.kg;
      return (auf ? x - y : y - x) || b.kg - a.kg || a.name.localeCompare(b.name, 'de');
    });
    return z;
  }
  function zeilenHtml() {
    const ek = S.d.rechte.ek, alle = sichtbareZeilen(), z = S.alle ? alle : alle.slice(0, ANFANG);
    if (!S.d.zeilen.length) return '<p class="ctl-empty">Keine Artikel im Zeitraum.</p>';
    if (!alle.length) return `<p class="ctl-empty">${S.nur ? 'Nichts auffällig.' : 'Kein Treffer für die Suche.'}</p>`;
    const kopf = `<div class="ctl-b-zeile ctl-b-zeilenkopf${ek ? ' ek' : ''}" aria-hidden="true"><span>${NACH[S.nach][0]}</span><span class="zahl">Bestand</span><span class="zahl">ggü. ${esc(tagKurz(S.d.zeitraum.erste))}</span><span>Verlauf</span><span class="zahl">Absatz</span><span>Reichweite</span><span class="zahl">Umschlag</span>${ek ? '<span class="zahl">Lagerwert (EK)</span>' : ''}<span></span></div>`;
    const reihen = z.map((x) => `<li><button type="button" class="ctl-b-zeile${ek ? ' ek' : ''}" data-key="${esc(x.key)}">
      <span class="name"><b>${esc(x.name)}</b>${x.sub ? `<small>${esc(x.sub)}${S.nach !== 'artikel' ? ` · ${esc(NF(0).format(x.artikel))} Artikel` : ''}</small>` : S.nach !== 'artikel' ? `<small>${esc(NF(0).format(x.artikel))} Artikel</small>` : ''}</span>
      <span class="zahl kg" data-label="Bestand">${esc(kg(x.kg))}</span>
      <span class="zahl delta" data-label="ggü. Beginn">${esc(delta(x))}</span>
      <span class="spark">${spark(x.spark)}</span>
      <span class="zahl" data-label="Absatz">${esc(kg(x.absatz))}</span>
      <span class="rw" data-label="Reichweite"><b>${esc(tage(x.reichweite))}</b>${marke(x.hinweis)}</span>
      <span class="zahl" data-label="Umschlag">${esc(mal(x.umschlag))}</span>
      ${ek ? `<span class="zahl" data-label="Lagerwert">${x.kg > 0 && !x.ekKg ? 'ohne EK' : esc(euro(x.ekWert))}</span>` : ''}
      <span class="pfeil">${F().ICON.weiter}</span></button></li>`).join('');
    const mehr = !S.alle && alle.length > ANFANG ? `<button type="button" class="btn ctl-b-alle" id="ctl-b-alle">Alle ${esc(NF(0).format(alle.length))} zeigen</button>` : '';
    return `${kopf}<ol class="ctl-b-rang" id="ctl-b-zeilen">${reihen}</ol><div class="ctl-b-listenfuss"><span class="ctl-hilfe">${esc(NF(0).format(z.length))} von ${esc(NF(0).format(alle.length))} ${NACH[S.nach][alle.length === 1 ? 0 : 1]}</span>${mehr}</div>`;
  }
  function liste() {
    const ek = S.d.rechte.ek;
    if (S.sort === 'ekWert' && !ek) S.sort = 'kg';
    return `<section class="ctl-panel ctl-glas ctl-b-panel" id="ctl-b-liste"><div class="ctl-b-listenkopf"><div class="ctl-b-listentitel"><h2>Je Artikel und Gruppe</h2>
      <div class="ctl-seg klein" role="group" aria-label="Gliederung" id="ctl-b-nach">${Object.entries(NACH).map(([id, n]) => `<button type="button" data-nach="${id}" aria-pressed="${id === S.nach}">${n[0]}</button>`).join('')}</div></div>
      <div class="ctl-b-listenwahl"><label class="ctl-visuellabel" for="ctl-b-sort">Sortieren nach</label><select id="ctl-b-sort">${Object.entries(SORT).filter(([, s]) => ek || !s[3]).map(([id, s]) => `<option value="${id}"${id === S.sort ? ' selected' : ''}>${s[0]}</option>`).join('')}</select>
      <label class="ctl-ua-check"><input type="checkbox" id="ctl-b-nur"${S.nur ? ' checked' : ''}>nur auffällige</label>
      <button type="button" class="btn ctl-b-csv" id="ctl-b-csv"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>CSV</button></div></div>
      <div id="ctl-b-zeilenbox">${zeilenHtml()}</div>
      <p class="ctl-fussnote"><b>Reichweite</b> = Bestand heute ÷ Ø Absatz je Kalendertag im Zeitraum. <b>Umschlag</b> = Absatz im Zeitraum ÷ Ø Bestand im Zeitraum.
      „Lange am Lager“ ab ${esc(NF(0).format(S.d.grenzen.lange))} Tagen Reichweite, „knapp“ unter ${esc(NF(0).format(S.d.grenzen.knapp))} Tagen, „kein Absatz“ = Bestand ohne Verkauf im Zeitraum.
      Absatz = berechnete Menge aus den Umsatzdaten, nur von Artikeln, die im Zeitraum im Bestand waren. Menge in kg.${ek ? ' Lagerwert = Menge × Einkaufspreis der Partien mit EK.' : ''}</p></section>`;
  }
  function zeichne() {
    const d = S.d;
    $('#ctl-b-stand', S.box).innerHTML = standText();
    $$('#ctl-b-zeit button', S.box).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.zeit === S.zeit)));
    $('#ctl-b-eigen', S.box).hidden = S.zeit !== 'eigen';
    $('#ctl-b-von', S.box).value = S.von; $('#ctl-b-bis', S.box).value = S.bis;
    chips();
    if (!d.stand.listen) {
      $('#ctl-b-inhalt', S.box).innerHTML = `<section class="ctl-panel ctl-glas ctl-b-leer"><h2>Noch kein Bestandsverlauf</h2><p>Der Verlauf beginnt mit dem nächsten Hochladen der Bestandsliste
        (Bestand → Bestandsliste hochladen oder Verwaltung → Import). Jede Liste wird als Tagesstand gespeichert – je mehr Tage zusammenkommen, desto aussagekräftiger werden Reichweite und Umschlag.</p></section>`;
      return;
    }
    if (S.wert === 'ekWert' && !d.rechte.ek) S.wert = 'kg';
    $('#ctl-b-inhalt', S.box).innerHTML = kennzahlen() + (d.zeitraum.listen ? entwicklung() : `<section class="ctl-panel ctl-glas ctl-b-leer"><p>Im gewählten Zeitraum gibt es keine Bestandsliste. Bitte einen anderen Zeitraum wählen.</p></section>`) + liste();
    diagrammZeichnen();
  }
  function diagrammZeichnen() {
    const box = $('#ctl-b-diagramm', S.box);
    if (!box || !S.d) return;
    const mobil = box.clientWidth < 560;
    box.innerHTML = diagramm(S.d.reihe, S.wert === 'kg' ? S.d.absatzReihe : [], S.d.zeitraum, S.wert, box.clientWidth || 900, mobil ? 230 : 300);
  }
  function chips() {
    const g = S.g, html = [];
    FILTER.forEach((f) => {
      const w = S.filter[f.id];
      if (!w || !w.size) return;
      const namen = [...w].map((v) => (v === OHNE ? f.ohne : f.liste === 'vkgruppen' ? ((g.optionen.vkgruppen.find((x) => x.nr === v) || {}).name || v) : v));
      html.push(`<span class="ctl-b-chip">${esc(f.name)}: ${esc(namen.slice(0, 2).join(', ') + (namen.length > 2 ? ` +${namen.length - 2}` : ''))}<button type="button" data-chip="${f.id}" aria-label="Filter ${esc(f.name)} entfernen">${F().ICON.zu}</button></span>`);
    });
    $('#ctl-b-chips', S.box).innerHTML = html.join('');
    const n = FILTER.reduce((s, f) => s + (S.filter[f.id] && S.filter[f.id].size ? 1 : 0), 0);
    $('#ctl-b-filterzahl', S.box).hidden = !n; $('#ctl-b-filterzahl', S.box).textContent = String(n);
  }

  /* ---------- Filter (Pop-up) ---------- */
  function filterOeffnen() {
    const dlg = $('#ctl-b-filterdialog', S.box), g = S.g;
    const optionen = (f) => [...(f.liste === 'vkgruppen' ? g.optionen.vkgruppen.map((x) => [x.nr, x.name ? `${x.name} (${x.nr})` : x.nr]) : g.optionen.fleischarten.map((x) => [x, x])), [OHNE, f.ohne]];
    dlg.innerHTML = `<form class="dlg" method="dialog"><div class="dlg-head"><div><p class="ctl-eyebrow">Bestandsverlauf</p><h2 id="ctl-b-f-titel">Filter</h2></div>
      <button type="button" class="ctl-rund" data-zu aria-label="Schließen">${F().ICON.zu}</button></div><div class="dlg-body ctl-b-filter">
      ${FILTER.map((f) => `<fieldset><legend>${esc(f.name)}</legend><div class="ctl-b-filteroptionen">${optionen(f).map(([v, n]) => `<label><input type="checkbox" data-f="${f.id}" value="${esc(v)}"${S.filter[f.id] && S.filter[f.id].has(v) ? ' checked' : ''}>${esc(n)}</label>`).join('')}</div></fieldset>`).join('')}
      </div><div class="dlg-foot"><button type="button" class="btn" data-leeren>Zurücksetzen</button><button type="submit" class="btn primary" data-uebernehmen>Übernehmen</button></div></form>`;
    $('[data-zu]', dlg).addEventListener('click', () => dlg.close());
    $('[data-leeren]', dlg).addEventListener('click', () => $$('input[type="checkbox"]', dlg).forEach((c) => { c.checked = false; }));
    $('form', dlg).addEventListener('submit', (ev) => {
      ev.preventDefault();
      FILTER.forEach((f) => { S.filter[f.id] = new Set($$(`input[data-f="${f.id}"]:checked`, dlg).map((c) => c.value)); });
      dlg.close(); S.alle = false; laden();
    });
    dlg.showModal();
  }

  /* ---------- Detail (Pop-up) ---------- */
  async function detailOeffnen(key) {
    const dlg = $('#ctl-b-dialog', S.box), dim = S.nach;
    dlg.innerHTML = `<div class="dlg"><div class="dlg-head"><div><p class="ctl-eyebrow">${esc(NACH[dim][0])}</p><h2 id="ctl-b-d-titel">Wird geladen …</h2></div>
      <button type="button" class="ctl-rund" data-zu aria-label="Schließen">${F().ICON.zu}</button></div><div class="dlg-body"><p class="ctl-hilfe">Listen werden gelesen …</p></div></div>`;
    $('[data-zu]', dlg).addEventListener('click', () => dlg.close());
    if (!dlg.open) dlg.showModal();
    const nr = ++S.detailNr;
    const r = await C.api('controlling_bestand_detail', null, anfrage({ dim, wert: key }));
    if (nr !== S.detailNr || !dlg.open) return;
    if (r.status === 401) { dlg.close(); C.zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { $('.dlg-body', dlg).innerHTML = `<p class="ctl-fehler" role="alert">${esc(C.fehlerText(r, 'Die Details konnten nicht geladen werden'))}</p>`; return; }
    S.detail = r.data;
    detailZeichnen(dlg);
  }
  function detailZeichnen(dlg) {
    const d = S.detail, z = d.zeile, ek = d.rechte.ek, zr = d.zeitraum;
    /* Absatz seit der vorigen Liste (bei der ersten: seit Beginn des Zeitraums), höchstens bis zum letzten Tag mit Umsatzdaten */
    const seit = new Map();
    d.reihe.forEach((t, i) => {
      const vor = i ? d.reihe[i - 1].d : '';
      if (!zr.absatzBis || vor >= zr.absatzBis) { seit.set(t.d, null); return; }
      const summe = d.absatzReihe.filter((a) => a.d > vor && a.d <= t.d).reduce((s, a) => s + a.kg, 0);
      seit.set(t.d, { kg: Math.round(summe * 10) / 10, bis: t.d > zr.absatzBis ? zr.absatzBis : null });
    });
    const absatzText = (t) => { const a = seit.get(t.d); return !a ? 'noch offen' : kg(a.kg) + (a.bis ? ` bis ${tagKurz(a.bis)}` : ''); };
    const k = [`<div class="ctl-ud-kpi"><span>Bestand</span><b>${esc(kg(z.kg))}</b><small>${zr.listen > 1 ? `${esc(delta(z))} ggü. ${esc(tagKurz(zr.erste))}` : ''}</small></div>`,
      `<div class="ctl-ud-kpi${z.hinweis === 'lange' ? ' lange' : z.hinweis === 'knapp' ? ' knapp' : ''}"><span>Reichweite</span><b>${esc(tage(z.reichweite))}</b><small>${z.hinweis ? esc(HINWEIS[z.hinweis][0]) : z.absatz !== null && z.absatz !== undefined ? `Absatz ${esc(kg(z.absatz))}` : ''}</small></div>`,
      `<div class="ctl-ud-kpi"><span>Umschlag</span><b>${esc(mal(z.umschlag))}</b><small>${ist(z.umschlagJahr) ? `≈ ${esc(mal(z.umschlagJahr))} im Jahr` : ''}</small></div>`,
      ek ? `<div class="ctl-ud-kpi"><span>Lagerwert (EK)</span><b>${esc(euro(z.ekWert))}</b><small>${z.ekKg > 0 ? `Ø ${esc(new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR' }).format(z.ekWert / z.ekKg))} je kg` : ''}</small></div>`
        : `<div class="ctl-ud-kpi"><span>Partien</span><b>${esc(NF(0).format(z.partien || 0))}</b><small>${z.zugang > 0 ? `${esc(kg(z.zugang))} erwartet` : ''}</small></div>`];
    const reihen = d.reihe.slice().reverse().map((t) => `<tr><td>${esc(wochentag(t.d))} ${esc(tagKurz(t.d))}</td><td class="ctl-zahl"><b>${esc(kg(t.kg))}</b></td><td class="ctl-zahl">${t.zugang ? esc(kg(t.zugang)) : '–'}</td>
      <td class="ctl-zahl">${esc(NF(0).format(t.partien))}</td>${ek ? `<td class="ctl-zahl">${esc(euro(t.ekWert))}</td>` : ''}<td class="ctl-zahl">${esc(absatzText(t))}</td></tr>`).join('');
    $('#ctl-b-d-titel', dlg).textContent = z.name;
    $('.dlg-head p', dlg).textContent = `${NACH[d.dim][0]} · ${tag(zr.von)} – ${tag(zr.bis)}`;
    const body = $('.dlg-body', dlg);
    body.innerHTML = `${z.sub ? `<p class="ctl-hilfe ctl-b-d-sub">${esc(z.sub)}</p>` : ''}<div class="ctl-ud-kpis">${k.join('')}</div>
      <div class="ctl-b-diagramm ctl-b-d-diagramm" id="ctl-b-d-diagramm"></div>
      <div class="ctl-b-tabelle"><table class="ctl-tabelle"><thead><tr><th>Liste vom</th><th class="ctl-zahl">Bestand</th><th class="ctl-zahl">erwartet</th><th class="ctl-zahl">Partien</th>${ek ? '<th class="ctl-zahl">Lagerwert</th>' : ''}<th class="ctl-zahl">Absatz seit voriger Liste</th></tr></thead><tbody>${reihen || `<tr><td colspan="${ek ? 6 : 5}" class="ctl-empty">Keine Liste im Zeitraum.</td></tr>`}</tbody></table></div>`;
    const foot = document.createElement('div');
    foot.className = 'dlg-foot';
    foot.innerHTML = `<span class="ctl-hilfe">${zr.absatzBis ? `Absatz aus den Umsatzdaten bis ${esc(tag(zr.absatzBis))}` : 'ohne Umsatzdaten im Zeitraum'} · ${esc(NF(0).format(zr.listen))} ${zr.listen === 1 ? 'Liste' : 'Listen'}</span>
      ${d.dim !== 'artikel' ? '<button type="button" class="btn" data-als-filter>Als Filter übernehmen</button>' : ''}<button type="button" class="btn" data-d-csv>Alle Tage als CSV</button>`;
    $('.dlg', dlg).append(foot);
    const zeichneDiagramm = () => { const b = $('#ctl-b-d-diagramm', dlg); if (b) b.innerHTML = diagramm(d.reihe, d.absatzReihe, zr, 'kg', b.clientWidth || 700, b.clientWidth < 560 ? 200 : 240); };
    zeichneDiagramm();
    const af = $('[data-als-filter]', dlg);
    if (af) af.addEventListener('click', () => { const f = FILTER.find((x) => x.nach === d.dim); S.filter[f.id] = new Set([z.key]); dlg.close(); S.nach = 'artikel'; S.alle = false; laden(); });
    $('[data-d-csv]', dlg).addEventListener('click', () => {
      const kopf = ['Liste vom', 'Bestand kg', 'erwartet kg', 'Partien', ...(ek ? ['Lagerwert €'] : []), 'Absatz seit voriger Liste kg', 'Absatz bis'];
      const zeilen = d.reihe.map((t) => { const a = seit.get(t.d); return [tag(t.d), F().zahl(t.kg, 1), F().zahl(t.zugang, 1), String(t.partien), ...(ek ? [F().zahl(t.ekWert, 2)] : []), a ? F().zahl(a.kg, 1) : '', a ? tag(a.bis || t.d) : '']; });
      F().csvLaden(`Bestandsverlauf ${z.name} ${tag(zr.von)} bis ${tag(zr.bis)}.csv`, [kopf, ...zeilen]);
    });
  }

  /* ---------- CSV der Liste ---------- */
  function csv() {
    const ek = S.d.rechte.ek, z = S.d.zeitraum, Z = F().zahl;
    const kopf = [NACH[S.nach][0], S.nach === 'artikel' ? 'Nummer · Gruppe' : 'Hinweis', 'Bestand kg', 'Veränderung %', 'Ø Bestand kg', 'Absatz kg', 'Reichweite Tage', 'Umschlag', 'Umschlag je Jahr', 'erwartet kg', 'Partien', 'Hinweis', ...(ek ? ['Lagerwert €'] : [])];
    const zeilen = sichtbareZeilen().map((x) => [x.name, x.sub || '', Z(x.kg, 1), Z(x.delta, 1), Z(x.oKg, 1), Z(x.absatz, 1), Z(x.reichweite, 1), Z(x.umschlag, 2), Z(x.umschlagJahr, 1), Z(x.zugang, 1), String(x.partien),
      x.hinweis ? HINWEIS[x.hinweis][0] : '', ...(ek ? [Z(x.ekWert, 2)] : [])]);
    F().csvLaden(`Bestandsverlauf ${NACH[S.nach][1]} ${tag(z.von)} bis ${tag(z.bis)}.csv`, [kopf, ...zeilen]);
  }

  /* ---------- Ereignisse ---------- */
  function verbinden() {
    const box = S.box;
    box.addEventListener('click', (ev) => {
      const t = ev.target;
      const zeit = t.closest('#ctl-b-zeit [data-zeit]');
      if (zeit) {
        S.zeit = zeit.dataset.zeit; S.alle = false;
        if (S.zeit === 'eigen') { zeichne(); $('#ctl-b-von', box).focus(); return; }
        laden(); return;
      }
      if (t.closest('#ctl-b-filterknopf')) { filterOeffnen(); return; }
      const chip = t.closest('[data-chip]');
      if (chip) { S.filter[chip.dataset.chip] = new Set(); laden(); return; }
      const nach = t.closest('#ctl-b-nach [data-nach]');
      if (nach) { S.nach = nach.dataset.nach; S.alle = false; S.suche = ''; $('#ctl-b-suche', box).value = ''; laden(); return; }
      const wert = t.closest('#ctl-b-wert [data-wert]');
      if (wert) { S.wert = wert.dataset.wert; zeichne(); return; }
      if (t.closest('#ctl-b-alle')) { S.alle = true; $('#ctl-b-zeilenbox', box).innerHTML = zeilenHtml(); return; }
      if (t.closest('#ctl-b-csv')) { csv(); return; }
      const zeile = t.closest('#ctl-b-zeilen [data-key]');
      if (zeile) detailOeffnen(zeile.dataset.key);
    });
    box.addEventListener('change', (ev) => {
      const t = ev.target;
      if (t.id === 'ctl-b-sort') { S.sort = t.value; $('#ctl-b-zeilenbox', box).innerHTML = zeilenHtml(); }
      else if (t.id === 'ctl-b-nur') { S.nur = t.checked; $('#ctl-b-zeilenbox', box).innerHTML = zeilenHtml(); }
      else if (t.id === 'ctl-b-von' || t.id === 'ctl-b-bis') {
        const v = $('#ctl-b-von', box).value, b = $('#ctl-b-bis', box).value;
        if (v && b && v <= b) { S.von = v; S.bis = b; laden(); }
      }
    });
    let warte = 0;
    box.addEventListener('input', (ev) => {
      if (ev.target.id !== 'ctl-b-suche') return;
      S.suche = ev.target.value; clearTimeout(warte);
      warte = setTimeout(() => { if (S.d && S.d.stand.listen) $('#ctl-b-zeilenbox', box).innerHTML = zeilenHtml(); }, 120);
    });
    let rz = 0;
    window.addEventListener('resize', () => { clearTimeout(rz); rz = setTimeout(() => { if (!box.hidden) diagrammZeichnen(); }, 120); });
  }

  C.bereich('bestand', {
    async anzeigen(box) {
      S.box = box;
      box.innerHTML = GERUEST();
      verbinden();
      const r = await C.api('controlling_bestand_daten');
      if (r.status === 401) { C.zeigeAnmeldung(); return; }
      if (r.status !== 200 || !r.data.ok) { const f = $('#ctl-b-fehler', box); f.textContent = C.fehlerText(r, 'Der Bestandsverlauf konnte nicht geladen werden'); f.hidden = false; $('#ctl-b-inhalt', box).innerHTML = ''; return; }
      S.g = r.data;
      await laden();
    },
  });
})();
