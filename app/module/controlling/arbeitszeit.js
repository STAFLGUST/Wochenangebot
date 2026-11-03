/* STAFL-Plattform · Controlling · Bereich Arbeitszeit (Auftrag des Inhabers 02.11.2026): Auswertung des Zeitberichts der
   Zeiterfassung – Kennzahlen (Soll, Ist, Saldo bereinigt, Stempelfehler), Monatsverlauf des Saldos, Liste je Mitarbeiter
   bzw. Abteilung und Liste der Stempelfehler; Pop-up je Mitarbeiter mit allen Tagen des Zeitraums, CSV je Liste.
   „Bereinigt“ = nur Tage ohne Stempelfehler; „laut Zeiterfassung“ = alle Tage, wie die Zeiterfassung sie rechnet. Tage mit
   Stempelfehlern werden nie geschätzt, nur markiert. Alle Werte rechnet der Server (module/controlling/arbeitszeit.php):
   controlling_arbeitszeit_daten, controlling_arbeitszeit, controlling_arbeitszeit_detail (Recht controlling.arbeitszeit_sehen).
   Meldet sich bei controlling.js an (STAFL_CONTROLLING.bereich); CSV und Symbole aus umsatz-auswertung.js (umsatzFormat). */
'use strict';
(() => {
  const C = window.STAFL_CONTROLLING;
  const esc = C.esc;
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const F = () => C.umsatzFormat;

  /* ---------- Formate (Werte in Minuten) ---------- */
  const NF = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 });
  const std = (m) => { if (m === null || m === undefined) return '—'; const a = Math.abs(m); return `${m < 0 ? '−' : ''}${NF.format(Math.floor(a / 60))}:${String(a % 60).padStart(2, '0')}`; };
  const stdVz = (m) => (m > 0 ? '+' : '') + std(m);
  const stdDez = (m) => F().zahl(m / 60, 2);   // CSV: Stunden als Dezimalzahl
  const tag = (d) => (d ? `${d.slice(8, 10)}.${d.slice(5, 7)}.${d.slice(0, 4)}` : '');
  const WT = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
  const wt = (d) => WT[new Date(Number(d.slice(0, 4)), Number(d.slice(5, 7)) - 1, Number(d.slice(8, 10))).getDay()];
  const MON = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  const monat = (m, kurz) => { const n = MON[Number(m.slice(5, 7)) - 1]; return (kurz ? n.slice(0, 3) : n) + ' ' + m.slice(0, 4); };
  const anzahl = (n, eins, viele) => `${NF.format(n)} ${n === 1 ? eins : viele}`;
  const LISTE_ANFANG = 200;
  const LUECKE = 1 / 3;   // Anteil der Arbeitstage (Soll > 0) mit Stempelfehlern, ab dem ein Mitarbeiter als „Zeiterfassung lückenhaft“ gilt
  const SORT = {
    name: ['Name', (z) => z.name, true, true],
    saldoOk: ['Saldo bereinigt (höchster zuerst)', (z) => z.saldoOk, false],
    saldoOkAuf: ['Saldo bereinigt (niedrigster zuerst)', (z) => z.saldoOk, true],
    fehlerTage: ['Stempelfehler (meiste zuerst)', (z) => z.fehlerTage, false],
    ist: ['Ist bereinigt (höchstes zuerst)', (z) => z.istOk, false],
  };

  const S = { box: null, g: null, d: null, von: '', bis: '', abt: '', ansicht: 'personen', sort: 'name', suche: '', fehlerArt: '', alle: false, laden: 0, detailNr: 0 };

  /* ---------- Gerüst ---------- */
  const GERUEST = () => `
    <div class="ctl-intro"><div><p class="ctl-eyebrow">Personal · aus dem Zeitbericht der Zeiterfassung</p><h1>Arbeitszeit</h1>
      <p class="ctl-intro-text">Soll, Ist und Saldo je Mitarbeiter und Abteilung – Tage mit Stempelfehlern werden markiert und nicht mitgerechnet.</p></div>
      <p class="ctl-notiz ctl-stand" id="ctl-az-stand"></p></div>
    <div class="ctl-ua-leiste ctl-glas" id="ctl-az-leiste">
      <div class="ctl-seg" role="group" aria-label="Zeitraum" id="ctl-az-zeit"><button type="button" data-zeit="jahr">Jahr</button><button type="button" data-zeit="monat">Letzter voller Monat</button></div>
      <span class="ctl-az-monate"><label>von <input type="month" id="ctl-az-von"></label><label>bis <input type="month" id="ctl-az-bis"></label></span>
      <label class="ctl-az-abt"><span class="ctl-visuellabel">Abteilung</span><select id="ctl-az-abt"><option value="">Alle Abteilungen</option></select></label>
      <label class="ctl-b-suche">${F().ICON.suche}<span class="sr-only">Mitarbeiter suchen</span><input type="search" id="ctl-az-suche" placeholder="Mitarbeiter oder Nummer suchen" autocomplete="off"></label>
    </div>
    <p class="ctl-fehler" id="ctl-az-fehler" role="alert" hidden></p>
    <div id="ctl-az-inhalt"><p class="ctl-hilfe">Arbeitszeit wird geladen …</p></div>
    <dialog class="modal wide ctl-dialog ctl-dialog-detail ctl-az-dlg" id="ctl-az-dialog" aria-labelledby="ctl-az-d-titel"></dialog>`;

  function anfrage(extra = {}) {
    const p = new URLSearchParams();
    if (S.von) p.set('von', S.von);
    if (S.bis) p.set('bis', S.bis);
    if (S.abt) p.set('abt', S.abt);
    Object.entries(extra).forEach(([k, v]) => p.set(k, v));
    return '&' + p.toString();
  }
  async function laden() {
    const nr = ++S.laden;
    $('#ctl-az-fehler', S.box).hidden = true;
    const r = await C.api('controlling_arbeitszeit', null, anfrage());
    if (nr !== S.laden) return;
    if (r.status === 401) { C.zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { const f = $('#ctl-az-fehler', S.box); f.textContent = C.fehlerText(r, 'Die Arbeitszeit konnte nicht geladen werden'); f.hidden = false; return; }
    S.d = r.data; S.von = S.d.zeitraum.von; S.bis = S.d.zeitraum.bis;
    zeichne();
  }

  /* ---------- Darstellung ---------- */
  function standText() {
    const st = S.g.stand;
    if (!st.bis) return 'Noch kein Zeitbericht importiert.';
    const imp = (st.importe || [])[0];
    return `Zeitbericht bis <b>${esc(tag(st.bis))}</b>${imp ? `<br>importiert am ${esc(window.STAFL_FORMAT.datum(imp.t))}${imp.wer ? ` von ${esc(imp.wer)}` : ''}` : ''}`;
  }
  function kachel(name, wert, sub, extra = '') { return `<div class="ctl-kpi ctl-glas${extra}"><span>${name}</span><b title="${esc(wert)}">${esc(wert)}</b><small>${sub}</small></div>`; }
  function kennzahlen() {
    const s = S.d.summe;
    const k = [];
    k.push(kachel('Soll', std(s.sollOk) + ' Std.', `${esc(anzahl(s.tageOk, 'Tag', 'Tage'))} ohne Stempelfehler gewertet`));
    k.push(kachel('Ist', std(s.istOk) + ' Std.', `gearbeitet${s.abwOk ? `, dazu ${esc(std(s.abwOk))} Std. Abwesenheit` : ''}`));
    k.push(kachel('Saldo bereinigt', stdVz(s.saldoOk) + ' Std.', `laut Zeiterfassung ${esc(stdVz(s.saldo))} Std. (alle Tage)`, s.saldoOk < 0 ? ' minus' : ''));
    k.push(kachel('Stempelfehler', anzahl(s.fehlerTage, 'Tag', 'Tage'), s.fehlerTage ? `nicht gewertet, dort ${esc(stdVz(s.saldoFehler))} Std. Saldo${s.ohne ? ` · ${esc(NF.format(s.ohne))} ohne jeden Stempel` : ''}` : 'keine im Zeitraum', s.fehlerTage ? ' warn' : ''));
    return `<div class="ctl-kpis ctl-az-kpis" id="ctl-az-kpis">${k.join('')}</div>`;
  }
  function verlauf() {
    const mon = S.d.monate;
    if (!mon.length) return '';
    const max = Math.max(60, ...mon.map((m) => Math.abs(m.saldoOk)));
    const zeilen = mon.map((m) => {
      const b = Math.round((Math.abs(m.saldoOk) / max) * 100);
      return `<li class="ctl-az-mon"><span class="name">${esc(monat(m.m, true))}</span>
        <span class="ctl-az-spur" aria-hidden="true"><i class="${m.saldoOk < 0 ? 'neg' : 'pos'}" style="--w:${b}%"></i></span>
        <span class="zahl" data-label="Saldo bereinigt">${esc(stdVz(m.saldoOk))}</span>
        <span class="zahl leise" data-label="Soll / Ist">${esc(std(m.sollOk))} / ${esc(std(m.istOk))}</span>
        <span class="zahl leise" data-label="Stempelfehler">${m.fehlerTage ? `<span class="ctl-az-marke">${esc(anzahl(m.fehlerTage, 'Fehler', 'Fehler'))}</span>` : '—'}</span></li>`;
    }).join('');
    return `<section class="ctl-panel ctl-glas ctl-az-panel" id="ctl-az-verlauf"><div class="ctl-panelkopf"><div><h2>Je Monat</h2>
      <p class="ctl-hilfe">Saldo bereinigt (Ist + Abwesenheit − Soll an Tagen ohne Stempelfehler), daneben Soll und Ist in Stunden.</p></div></div>
      <ol class="ctl-az-monate-liste">${zeilen}</ol></section>`;
  }
  const suchtreffer = (z) => { const q = S.suche.trim().toLocaleLowerCase('de-DE'); return !q || z.name.toLocaleLowerCase('de-DE').includes(q) || String(z.nr || '').toLocaleLowerCase('de-DE').includes(q); };
  function sortiert(liste) {
    const [, wert, auf, text] = SORT[S.sort] || SORT.name;
    return liste.slice().sort((a, b) => (text ? a.name.localeCompare(b.name, 'de') : (auf ? wert(a) - wert(b) : wert(b) - wert(a)) || a.name.localeCompare(b.name, 'de')));
  }
  const luecke = (z) => z.fehlerTage > 0 && z.fehlerTage / Math.max(z.arbeitstage, z.fehlerTage) >= LUECKE;
  function personenHtml() {
    const alle = sortiert(S.d.personen.filter(suchtreffer));
    if (!S.d.personen.length) return '<p class="ctl-empty">Keine Mitarbeiter im Zeitraum.</p>';
    if (!alle.length) return '<p class="ctl-empty">Kein Treffer für die Suche.</p>';
    const kopf = `<div class="ctl-az-zeile ctl-az-zeilenkopf" aria-hidden="true"><span>Mitarbeiter</span><span class="zahl">Soll</span><span class="zahl">Ist</span><span class="zahl">Abwesenheit</span><span class="zahl">Saldo bereinigt</span><span class="zahl">laut Zeiterfassung</span><span class="zahl">Stempelfehler</span><span></span></div>`;
    const reihen = alle.map((z) => `<li><button type="button" class="ctl-az-zeile" data-p="${esc(z.id)}">
      <span class="name"><b>${esc(z.name)}</b><small>${esc([z.nr ? 'Nr. ' + z.nr : 'ohne Nummer', z.abt || 'ohne Abteilung'].join(' · '))}</small></span>
      <span class="zahl" data-label="Soll">${esc(std(z.sollOk))}</span>
      <span class="zahl" data-label="Ist">${esc(std(z.istOk))}</span>
      <span class="zahl" data-label="Abwesenheit">${esc(std(z.abwOk))}</span>
      <span class="zahl saldo${z.saldoOk < 0 ? ' neg' : ''}" data-label="Saldo bereinigt"><b>${esc(stdVz(z.saldoOk))}</b></span>
      <span class="zahl leise" data-label="laut Zeiterfassung">${esc(stdVz(z.saldo))}</span>
      <span class="zahl" data-label="Stempelfehler">${z.fehlerTage ? `${esc(NF.format(z.fehlerTage))}${luecke(z) ? ' <span class="ctl-az-marke stark" title="Mindestens ein Drittel der Arbeitstage mit Stempelfehlern – Zeiterfassung lückenhaft">lückenhaft</span>' : ''}` : '—'}</span>
      <span class="pfeil">${F().ICON.weiter}</span></button></li>`).join('');
    return `${kopf}<ol class="ctl-az-liste" id="ctl-az-zeilen">${reihen}</ol><p class="ctl-hilfe ctl-az-anzahl">${esc(anzahl(alle.length, 'Mitarbeiter', 'Mitarbeiter'))}</p>`;
  }
  function abteilungenHtml() {
    const alle = S.d.abteilungen;
    if (!alle.length) return '<p class="ctl-empty">Keine Abteilungen im Zeitraum.</p>';
    const kopf = `<div class="ctl-az-zeile ctl-az-zeilenkopf abt" aria-hidden="true"><span>Abteilung</span><span class="zahl">Mitarbeiter</span><span class="zahl">Soll</span><span class="zahl">Ist</span><span class="zahl">Saldo bereinigt</span><span class="zahl">Ø je Mitarbeiter</span><span class="zahl">Stempelfehler</span></div>`;
    const reihen = alle.map((z) => `<li><div class="ctl-az-zeile abt" data-abt="${esc(z.id)}">
      <span class="name"><b>${esc(z.name)}</b></span>
      <span class="zahl" data-label="Mitarbeiter">${esc(NF.format(z.personen))}</span>
      <span class="zahl" data-label="Soll">${esc(std(z.sollOk))}</span>
      <span class="zahl" data-label="Ist">${esc(std(z.istOk))}</span>
      <span class="zahl saldo${z.saldoOk < 0 ? ' neg' : ''}" data-label="Saldo bereinigt"><b>${esc(stdVz(z.saldoOk))}</b></span>
      <span class="zahl leise" data-label="Ø je Mitarbeiter">${esc(stdVz(Math.round(z.saldoOk / Math.max(1, z.personen))))}</span>
      <span class="zahl" data-label="Stempelfehler">${z.fehlerTage ? esc(NF.format(z.fehlerTage)) : '—'}</span></div></li>`).join('');
    return `${kopf}<ol class="ctl-az-liste">${reihen}</ol><p class="ctl-hilfe ctl-az-anzahl">Abteilung = jüngste Angabe des Mitarbeiters im Zeitbericht.</p>`;
  }
  const stempelText = (st) => (st && st.length ? st.map(([k, g]) => `${k || '?'}–${g || '?'}`).join(', ') : 'kein Stempel');
  const fehlerMarken = (f) => f.map((c) => `<span class="ctl-az-marke">${esc(S.g.fehlerarten[c] || c)}</span>`).join('');
  function fehlerHtml() {
    const namen = Object.fromEntries(S.g.personen.map((p) => [p.id, p]));
    const liste = S.d.fehler.filter((f) => (!S.fehlerArt || f.fehler.includes(S.fehlerArt)) && suchtreffer(namen[f.p] || { name: '?', nr: '' }));
    const z = S.alle ? liste : liste.slice(0, LISTE_ANFANG);
    const arten = Object.entries(S.g.fehlerarten).map(([id, n]) => `<option value="${esc(id)}"${id === S.fehlerArt ? ' selected' : ''}>${esc(n)}</option>`).join('');
    const wahl = `<div class="ctl-az-fehlerwahl"><label class="ctl-visuellabel" for="ctl-az-art">Fehlerart</label><select id="ctl-az-art"><option value="">Alle Fehlerarten</option>${arten}</select></div>`;
    if (!S.d.fehler.length) return wahl + '<p class="ctl-empty">Keine Stempelfehler im Zeitraum.</p>';
    if (!liste.length) return wahl + '<p class="ctl-empty">Keine Stempelfehler für diese Auswahl.</p>';
    const kopf = `<div class="ctl-az-zeile ctl-az-zeilenkopf fehler" aria-hidden="true"><span>Tag</span><span>Mitarbeiter</span><span>Fehler</span><span>Stempel</span><span class="zahl">Soll</span><span class="zahl">Ist</span><span class="zahl">Saldo laut ZE</span></div>`;
    const reihen = z.map((f) => { const p = namen[f.p] || { name: '?' }; return `<li><button type="button" class="ctl-az-zeile fehler" data-p="${esc(f.p)}">
      <span data-label="Tag">${esc(wt(f.d))} ${esc(tag(f.d))}</span>
      <span class="name"><b>${esc(p.name)}</b></span>
      <span class="marken" data-label="Fehler">${fehlerMarken(f.fehler)}</span>
      <span class="stempel" data-label="Stempel">${esc(stempelText(f.stempel))}</span>
      <span class="zahl" data-label="Soll">${esc(std(f.soll))}</span>
      <span class="zahl" data-label="Ist">${esc(std(f.ist))}</span>
      <span class="zahl leise" data-label="Saldo laut ZE">${esc(stdVz(f.saldo))}</span></button></li>`; }).join('');
    const mehr = !S.alle && liste.length > LISTE_ANFANG ? `<button type="button" class="btn ctl-b-alle" id="ctl-az-alle">Alle ${esc(NF.format(liste.length))} zeigen</button>` : '';
    const gekuerzt = S.d.fehlerGesamt > S.d.fehler.length ? ` Der Server liefert die jüngsten ${esc(NF.format(S.d.fehler.length))} von ${esc(NF.format(S.d.fehlerGesamt))} – bitte den Zeitraum verkleinern.` : '';
    return `${wahl}${kopf}<ol class="ctl-az-liste" id="ctl-az-fehlerliste">${reihen}</ol><div class="ctl-b-listenfuss"><span class="ctl-hilfe">${esc(NF.format(z.length))} von ${esc(NF.format(liste.length))} Tagen.${gekuerzt}</span>${mehr}</div>`;
  }
  const ANSICHT = { personen: ['Mitarbeiter', personenHtml], abteilungen: ['Abteilungen', abteilungenHtml], fehler: ['Stempelfehler', fehlerHtml] };
  function liste() {
    const sortWahl = S.ansicht === 'personen' ? `<label class="ctl-visuellabel" for="ctl-az-sort">Sortieren nach</label><select id="ctl-az-sort">${Object.entries(SORT).map(([id, s]) => `<option value="${id}"${id === S.sort ? ' selected' : ''}>${s[0]}</option>`).join('')}</select>` : '';
    return `<section class="ctl-panel ctl-glas ctl-az-panel" id="ctl-az-liste"><div class="ctl-b-listenkopf"><div class="ctl-b-listentitel"><h2>Übersicht</h2>
      <div class="ctl-seg klein" role="group" aria-label="Ansicht" id="ctl-az-ansicht">${Object.entries(ANSICHT).map(([id, a]) => `<button type="button" data-ansicht="${id}" aria-pressed="${id === S.ansicht}">${a[0]}${id === 'fehler' && S.d.summe.fehlerTage ? ` <span class="ctl-ua-zahl">${esc(NF.format(S.d.fehlerGesamt))}</span>` : ''}</button>`).join('')}</div></div>
      <div class="ctl-b-listenwahl">${sortWahl}<button type="button" class="btn ctl-b-csv" id="ctl-az-csv"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>CSV</button></div></div>
      <div id="ctl-az-listenbox">${ANSICHT[S.ansicht][1]()}</div>
      <p class="ctl-fussnote"><b>Saldo bereinigt</b> = Ist + Abwesenheit − Soll, nur an Tagen ohne Stempelfehler. <b>Laut Zeiterfassung</b> = derselbe Saldo über alle Tage, wie die Zeiterfassung ihn rechnet.
      Stempelfehler: Kommen oder Gehen fehlt, Kommen = Gehen, länger als ${esc(NF.format(S.g.grenzen.lang / 60))} Stunden (meist vergessenes Gehen), Soll ohne Stempel und ohne Abwesenheit, Saldo passt nicht zu den Stunden.
      Solche Tage bitte in der Zeiterfassung nachtragen und den Zeitbericht neu importieren – hier wird nichts geschätzt. Heute und spätere Tage zählen erst mit dem nächsten Import.</p></section>`;
  }
  function zeichne() {
    $('#ctl-az-stand', S.box).innerHTML = standText();
    $('#ctl-az-von', S.box).value = S.von; $('#ctl-az-bis', S.box).value = S.bis;
    const jahr = S.von === S.bis.slice(0, 4) + '-01', monatW = S.von === S.bis;
    $$('#ctl-az-zeit [data-zeit]', S.box).forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.zeit === 'jahr' ? jahr && !monatW : monatW)));
    if (!S.g.stand.bis) {
      $('#ctl-az-inhalt', S.box).innerHTML = `<section class="ctl-panel ctl-glas ctl-b-leer" id="ctl-az-leer"><h2>Noch kein Zeitbericht</h2><p>Den Zeitbericht der Zeiterfassung als Excel-Datei exportieren und unter
        Verwaltung → Import („Arbeitszeit (Zeitbericht)“) hochladen${S.g.rechte.importieren ? '' : ' – dafür braucht es das Recht „Zeitbericht der Zeiterfassung importieren“'}. Ein neuer Import ersetzt den Zeitraum seiner Datei.</p></section>`;
      return;
    }
    $('#ctl-az-inhalt', S.box).innerHTML = kennzahlen() + verlauf() + liste();
  }
  function listeNeu() { $('#ctl-az-listenbox', S.box).innerHTML = ANSICHT[S.ansicht][1](); }

  /* ---------- Pop-up: Tage eines Mitarbeiters ---------- */
  async function detailOeffnen(pid) {
    const dlg = $('#ctl-az-dialog', S.box);
    dlg.innerHTML = `<div class="dlg"><div class="dlg-head"><div><p class="ctl-eyebrow">Mitarbeiter</p><h2 id="ctl-az-d-titel">Wird geladen …</h2></div>
      <button type="button" class="ctl-rund" data-zu aria-label="Schließen">${F().ICON.zu}</button></div><div class="dlg-body"><p class="ctl-hilfe">Tage werden gelesen …</p></div></div>`;
    $('[data-zu]', dlg).addEventListener('click', () => dlg.close());
    if (!dlg.open) dlg.showModal();
    const nr = ++S.detailNr;
    const r = await C.api('controlling_arbeitszeit_detail', null, anfrage({ p: pid }));
    if (nr !== S.detailNr || !dlg.open) return;
    if (r.status === 401) { dlg.close(); C.zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { $('.dlg-body', dlg).innerHTML = `<p class="ctl-fehler" role="alert">${esc(C.fehlerText(r, 'Die Tage konnten nicht geladen werden'))}</p>`; return; }
    const d = r.data, s = d.summe, p = d.person;
    $('#ctl-az-d-titel', dlg).textContent = p.name;
    const zeilen = d.tage.map((t) => `<tr class="${t.fehler.length ? 'fehler' : t.laufend ? 'laufend' : ''}"><td>${esc(wt(t.d))} ${esc(tag(t.d))}</td><td>${esc(stempelText(t.stempel))}</td>
      <td class="zahl">${esc(std(t.soll))}</td><td class="zahl">${esc(std(t.ist))}</td><td class="zahl">${t.abw ? esc(std(t.abw)) : '—'}</td><td class="zahl">${esc(stdVz(t.saldo))}</td>
      <td>${t.laufend ? '<span class="ctl-az-marke leise">noch offen</span>' : fehlerMarken(t.fehler)}</td></tr>`).join('');
    $('.dlg-body', dlg).innerHTML = `<p class="ctl-b-d-sub">${esc([p.nr ? 'Nr. ' + p.nr : 'ohne Nummer', p.abt || 'ohne Abteilung', `${monat(d.zeitraum.von)} – ${monat(d.zeitraum.bis)}`].join(' · '))}</p>
      <div class="ctl-kpis ctl-az-kpis klein">${kachel('Soll', std(s.sollOk) + ' Std.', 'Tage ohne Fehler')}${kachel('Ist', std(s.istOk) + ' Std.', s.abwOk ? `dazu ${esc(std(s.abwOk))} Std. Abwesenheit` : 'gearbeitet')}
      ${kachel('Saldo bereinigt', stdVz(s.saldoOk) + ' Std.', `laut Zeiterfassung ${esc(stdVz(s.saldo))} Std.`, s.saldoOk < 0 ? ' minus' : '')}${kachel('Stempelfehler', NF.format(s.fehlerTage), s.fehlerTage ? `dort ${esc(stdVz(s.saldoFehler))} Std. Saldo` : 'keine', s.fehlerTage ? ' warn' : '')}</div>
      <div class="ctl-tabelle-wrap"><table class="ctl-tabelle ctl-az-tage" id="ctl-az-tage"><thead><tr><th>Tag</th><th>Stempel</th><th class="zahl">Soll</th><th class="zahl">Ist</th><th class="zahl">Abwesenheit</th><th class="zahl">Saldo</th><th>Hinweis</th></tr></thead>
      <tbody>${zeilen || '<tr><td colspan="7">Keine Tage im Zeitraum.</td></tr>'}</tbody></table></div>
      <div class="dlg-foot"><button type="button" class="btn ctl-b-csv" data-csv><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11M7 10l5 5 5-5M5 20h14"/></svg>CSV</button></div>`;
    $('[data-csv]', dlg).addEventListener('click', () => {
      const kopf = ['Tag', 'Stempel', 'Soll Std.', 'Ist Std.', 'Abwesenheit Std.', 'Saldo Std.', 'Stempelfehler', 'noch offen'];
      F().csvLaden(`Arbeitszeit ${p.name} ${d.zeitraum.von} bis ${d.zeitraum.bis}.csv`, [kopf, ...d.tage.map((t) => [tag(t.d), stempelText(t.stempel), stdDez(t.soll), stdDez(t.ist), stdDez(t.abw), stdDez(t.saldo),
        t.fehler.map((c) => S.g.fehlerarten[c] || c).join(', '), t.laufend ? 'ja' : ''])]);
    });
  }

  /* ---------- CSV der Liste ---------- */
  function csv() {
    const z = S.d.zeitraum, Z = stdDez;
    if (S.ansicht === 'fehler') {
      const namen = Object.fromEntries(S.g.personen.map((p) => [p.id, p.name]));
      const liste = S.d.fehler.filter((f) => !S.fehlerArt || f.fehler.includes(S.fehlerArt));
      F().csvLaden(`Stempelfehler ${z.von} bis ${z.bis}.csv`, [['Tag', 'Mitarbeiter', 'Stempelfehler', 'Stempel', 'Soll Std.', 'Ist Std.', 'Saldo laut ZE Std.'],
        ...liste.map((f) => [tag(f.d), namen[f.p] || '?', f.fehler.map((c) => S.g.fehlerarten[c] || c).join(', '), stempelText(f.stempel), Z(f.soll), Z(f.ist), Z(f.saldo)])]);
      return;
    }
    const pers = S.ansicht === 'personen';
    const kopf = [pers ? 'Mitarbeiter' : 'Abteilung', ...(pers ? ['Nummer', 'Abteilung'] : ['Mitarbeiter']), 'Soll Std.', 'Ist Std.', 'Abwesenheit Std.', 'Saldo bereinigt Std.', 'Saldo laut ZE Std.', 'Tage gewertet', 'Tage mit Stempelfehler', 'davon ohne Stempel'];
    const liste = pers ? sortiert(S.d.personen.filter(suchtreffer)) : S.d.abteilungen;
    F().csvLaden(`Arbeitszeit ${pers ? 'Mitarbeiter' : 'Abteilungen'} ${z.von} bis ${z.bis}.csv`, [kopf, ...liste.map((x) => [x.name, ...(pers ? [x.nr, x.abt] : [String(x.personen)]),
      Z(x.sollOk), Z(x.istOk), Z(x.abwOk), Z(x.saldoOk), Z(x.saldo), String(x.tageOk), String(x.fehlerTage), String(x.ohne)])]);
  }

  /* ---------- Ereignisse ---------- */
  /* jüngster vollständig importierter Monat: endet der Zeitbericht vor dem Monatsende, der Monat davor */
  function letzterMonat() {
    const b = S.g.stand.bis || '';
    if (!b) return '';
    const j = Number(b.slice(0, 4)), m = Number(b.slice(5, 7));
    if (Number(b.slice(8, 10)) === new Date(j, m, 0).getDate()) return b.slice(0, 7);
    return m === 1 ? `${j - 1}-12` : `${j}-${String(m - 1).padStart(2, '0')}`;
  }
  function verbinden() {
    const box = S.box;
    box.addEventListener('click', (ev) => {
      const t = ev.target;
      const zeit = t.closest('#ctl-az-zeit [data-zeit]');
      if (zeit && S.g.stand.bis) {
        const m = letzterMonat();
        if (zeit.dataset.zeit === 'jahr') { S.bis = S.g.stand.bis.slice(0, 7); S.von = S.bis.slice(0, 4) + '-01'; } else { S.von = m; S.bis = m; }
        S.alle = false; laden(); return;
      }
      const ans = t.closest('#ctl-az-ansicht [data-ansicht]');
      if (ans) { S.ansicht = ans.dataset.ansicht; S.alle = false; $('#ctl-az-liste', box).outerHTML = liste(); return; }
      if (t.closest('#ctl-az-alle')) { S.alle = true; listeNeu(); return; }
      if (t.closest('#ctl-az-csv')) { csv(); return; }
      const zeile = t.closest('[data-p]');
      if (zeile && box.contains(zeile) && !t.closest('dialog')) detailOeffnen(zeile.dataset.p);
    });
    box.addEventListener('change', (ev) => {
      const t = ev.target;
      if (t.id === 'ctl-az-sort') { S.sort = t.value; listeNeu(); }
      else if (t.id === 'ctl-az-art') { S.fehlerArt = t.value; S.alle = false; listeNeu(); }
      else if (t.id === 'ctl-az-abt') { S.abt = t.value; S.alle = false; laden(); }
      else if (t.id === 'ctl-az-von' || t.id === 'ctl-az-bis') {
        const v = $('#ctl-az-von', box).value, b = $('#ctl-az-bis', box).value;
        if (v && b && v <= b) { S.von = v; S.bis = b; S.alle = false; laden(); }
      }
    });
    let warte = 0;
    box.addEventListener('input', (ev) => {
      if (ev.target.id !== 'ctl-az-suche') return;
      S.suche = ev.target.value; clearTimeout(warte);
      warte = setTimeout(() => { if (S.d && S.g.stand.bis && S.ansicht !== 'abteilungen') listeNeu(); }, 120);
    });
  }

  C.bereich('arbeitszeit', {
    async anzeigen(box) {
      S.box = box;
      box.innerHTML = GERUEST();
      verbinden();
      const r = await C.api('controlling_arbeitszeit_daten');
      if (r.status === 401) { C.zeigeAnmeldung(); return; }
      if (r.status !== 200 || !r.data.ok) { const f = $('#ctl-az-fehler', box); f.textContent = C.fehlerText(r, 'Die Arbeitszeit konnte nicht geladen werden'); f.hidden = false; $('#ctl-az-inhalt', box).innerHTML = ''; return; }
      S.g = r.data;
      $('#ctl-az-abt', box).innerHTML = '<option value="">Alle Abteilungen</option>' + S.g.abteilungen.map((a) => `<option value="${esc(a)}">${esc(a)}</option>`).join('') + '<option value="_">ohne Abteilung</option>';
      await laden();
    },
  });
})();
