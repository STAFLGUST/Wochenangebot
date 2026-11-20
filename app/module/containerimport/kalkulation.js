/* STAFL-Plattform · Modul Container-Import – Reiter „Kalkulation“ (Auftrag des Inhabers 20.11.2026): Einstandspreis je
   Position und Ertrag je Teil für einen Container. Liste der Container mit dem Stand ihrer Kalkulation; je Container Kopf
   (Kurs, Seefracht, Provision, Nebenkosten), Teile (Abnehmer, Versicherung, Rückvergütung, WKZ), Positionen (Zollregime,
   Ursprung, KN-Code, Gewichte, Preise) und Sätze mit Quelle (überschreibbar nur mit Vermerk); Ergebnis je Position, je Teil
   und gesamt, Kontingente, Vergleich mit/ohne Mercosur-Kontingent, Prüfhinweise; Fassungen (vorläufig → endgültig
   festschreiben → neue Fassung nur mit Grund), Druckansicht (A4 quer) und CSV.
   Was gezeigt wird, sagt ansicht() ('neu' | 'entwurf' | 'endgueltig' | 'aelter'); daraus folgen Bearbeitbarkeit, Knöpfe,
   Marke, Dateiname und Druckkopf. Gerechnet wird nur auf dem Server: bei jeder Eingabe fragt die Seite
   containerimport_kalkulation_rechnen (speichert nichts) und zeigt die Antwort; Speichern und Festschreiben rechnen dort neu.
   Regeln und Sätze: app/api/module/containerimport/kalkulation.php. Hilfen und Zustand über die Brücke window.STAFL_CI
   (fehlerText, zeigeAnmeldung, herunterladen …); die Datei trägt ihren Reiter dort ein. Der Druck schreibt die Kalkulation
   in einen eigenen Block (.kk-druck, A4 quer) in #ci-druck und leert ihn danach – der EUDR-Druck erbt nie das Querformat.
   Zahlen werden nur in der Anzeige gerundet. Fremde Texte nur maskiert, in der CSV gegen Formeln geschützt. */
(() => {
  'use strict';
  const C = window.STAFL_CI, F = window.STAFL_FORMAT;
  const { S, $, esc, icon, marke, tag, api, toast, titel, sendung, suchfeld, fokusBehalten, fehlerText, zeigeAnmeldung, herunterladen } = C;
  S.suche.kalkulation = '';
  /* start = Stand des Reiters (Sätze, Auswahllisten, Übersicht); id/kalk/container = geöffneter Container; nr = gezeigte
     Fassung; e = Eingabe; erg = Ergebnis des Servers; geaendert = ungespeichert; neu = neue Fassung wird angelegt */
  const K = { start: null, laedt: false, id: '', kalk: null, container: null, nr: 0, e: null, erg: null, geaendert: false, neu: false, festschreiben: false, verwerfen: false, timer: 0, anfrage: 0, norm: null };
  const zt = (v) => (typeof v === 'number' ? String(v).replace('.', ',') : v ?? '');   // Text der Eingabe bleibt, wie getippt („1.000“)
  const geld = (v) => (v === null || v === undefined ? '—' : F.euro(v));
  const proKg = (v) => (v === null || v === undefined ? '—' : `${F.zahl(v, 2, 4)} €/kg`);
  const kgText = (v) => (v === null || v === undefined ? '—' : `${F.zahl(v, 0, 2)} kg`);
  const pz = (v) => (v === null || v === undefined ? '—' : F.prozent(v));
  const satzText = (s) => `${F.zahl(s.wert, 0, 3)} %${s.spez > 0 ? ` + ${F.zahl(s.spez, 0, 3)} €/100 kg` : ''}`;
  const fassung = () => (K.kalk ? K.kalk.fassungen[K.nr] : null);
  const letzte = () => (K.kalk ? K.kalk.fassungen.length - 1 : -1);
  /* Was gezeigt wird: 'neu' (noch keine Fassung oder eine neue entsteht), 'entwurf' (offene letzte Fassung),
     'endgueltig' (letzte Fassung, festgeschrieben), 'aelter' (eine frühere Fassung – immer festgeschrieben) */
  const ansicht = () => (K.neu || !fassung() ? 'neu' : K.nr !== letzte() ? 'aelter' : fassung().stand);
  const bearbeitbar = () => K.start.rechte.bearbeiten && ['neu', 'entwurf'].includes(ansicht());
  /* Stand in einem Satz (Druckkopf, erste Zeile der CSV) */
  function standText() {
    const f = fassung(), a = ansicht();
    return (a === 'neu' ? (f ? 'neue Fassung, nicht gespeichert' : 'nicht gespeichert')
      : `Fassung ${f.nr} · ${K.start.staende[f.stand]}${f.endgueltig ? ` (${tag(f.endgueltig.wer.t)}, ${f.endgueltig.wer.von})` : ''}`)
      + (K.geaendert ? ' · mit ungespeicherten Änderungen' : '');
  }
  function antwortOk(r, fallback) {
    if (r.status === 401) { zeigeAnmeldung(); return false; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, fallback), true); return false; }
    return true;
  }

  /* ---------- Reiter: Liste der Container ---------- */
  async function startLaden() {
    K.laedt = true;
    const r = await api('containerimport_kalkulation_start');
    K.laedt = false;
    if (!antwortOk(r, 'Die Kalkulation konnte nicht geladen werden')) return;
    K.start = r.data;
    if (S.reiter === 'kalkulation') zeichnen();
  }
  function zeichnen() {
    const ziel = $('#ci-bereich-kalkulation');
    if (!K.start) { ziel.innerHTML = '<p class="ci-leise">Kalkulation wird geladen …</p>'; if (!K.laedt) startLaden(); return; }
    if (K.id) { if (!$('#kk-editor') || $('#kk-editor').dataset.id !== K.id) editor(); return; }   // offene Eingaben nie durch fremdes Neuzeichnen verlieren
    const u = K.start.uebersicht;
    const liste = S.d.sendungen.filter((s) => (s.aktiv || u[s.id]) && C.SU.findet(S.suche.kalkulation, s.partie, s.akte, s.container, s.lieferant, s.ware))
      .sort((a, b) => !!u[b.id] - !!u[a.id] || b.erstellt.t.localeCompare(a.erstellt.t));
    const stand = (x) => (x ? marke(`Fassung ${x.nr} · ${K.start.staende[x.stand]}`, x.stand === 'endgueltig' ? 'ok' : 'warn') : marke('keine'));
    ziel.innerHTML = `<p class="ci-t-lage">Einstandspreis je Position und Ertrag je Abnehmer für einen Container. Gerechnet wird auf dem Server; Zollsätze ${esc(K.start.taric)}.</p>
      <div class="ci-suchzeile">${suchfeld('Partie, Akte, Container, Lieferant, Ware', 'Kalkulation', 'kalkulation', 'kk-suche')}</div>`
      + (liste.length ? `<div class="r-karte"><table class="ci-tab" id="kk-liste"><thead><tr><th scope="col">Container</th><th scope="col">Lieferant</th><th scope="col">Kalkulation</th><th scope="col">Zuletzt</th></tr></thead><tbody>${liste.map((s) => `
        <tr data-kalk="${esc(s.id)}" tabindex="0"><td><span class="ci-name">${esc(titel(s))}</span><span class="ci-unter">${esc(s.ware || '—')}</span></td>
          <td data-t="Lieferant">${esc(s.lieferant)}</td><td data-t="Kalkulation">${stand(u[s.id])}</td>
          <td data-t="Zuletzt">${u[s.id] ? `${tag(u[s.id].geaendert.t)} · ${esc(u[s.id].geaendert.von)}` : '—'}</td></tr>`).join('')}</tbody></table></div>`
        : `<div class="r-karte"><p class="ci-leer">${S.suche.kalkulation ? 'Kein Container passt zur Suche.' : 'Noch kein Container. Container legen Sie im Reiter „EUDR“ an.'}</p></div>`);
  }

  /* ---------- Container öffnen, neue Eingabe ---------- */
  async function oeffnen(id) {
    const r = await api('containerimport_kalkulation_laden', null, '&sendung=' + encodeURIComponent(id));
    if (!antwortOk(r, 'Die Kalkulation konnte nicht geladen werden')) return;
    Object.assign(K, { id, kalk: r.data.kalkulation, container: r.data.container, neu: false, geaendert: false, festschreiben: false });
    zeigeFassung(letzte());
    if (!K.kalk) rechnen();
  }
  function zeigeFassung(nr) {
    K.nr = nr;
    const f = fassung();
    K.e = f ? JSON.parse(JSON.stringify(f.eingabe)) : neueEingabe();
    K.erg = f ? f.ergebnis : null;
    K.norm = f ? f.eingabe : null;   // vom Server geprüfte Eingabe (Zahlen als Zahlen) – für die CSV-Datei
    editor();
  }
  function neueEingabe() {
    return { kopf: { ...K.start.vorgabe, datum: S.d.heute }, teile: [{ id: 't1', name: 'Teil 1', abnehmer: '', versicherung: null, rueckverguetung: null, wkz: null }],
      positionen: [], ueberschrieben: {}, notiz: '' };
  }
  const neuePosition = (teil) => ({ teil, artikel: '', rl: false, regime: 'hilton', land: (K.container && K.container.land) || '', kn: '', kartons: null, brutto: null, netto: null, preis: null, waehrung: 'USD', imagEk: null, vk: null, wertzoll: null, spezifisch: null, vermerk: '' });

  /* ---------- Eingabe ---------- */
  function editor() {
    const darf = bearbeitbar(), aus = darf ? '' : ' disabled', f = fassung(), a = ansicht(), e = K.e, s = sendung(K.id) || K.container;
    const ein = (name, wert, platz = '', art = 'text') => `<input data-k="${name}" type="${art}" value="${esc(art === 'date' ? wert : zt(wert))}"${art === 'text' ? ' inputmode="decimal"' : ''}${platz ? ` placeholder="${esc(platz)}"` : ''}${aus}>`;
    const kfeld = (label, name, einheit, platz, hilfe = '') => `<label class="ci-feld"><span>${esc(label)}</span><span class="kk-mit">${ein(name, e.kopf[name], platz)}<i>${esc(einheit)}</i></span>${hilfe ? `<small>${esc(hilfe)}</small>` : ''}</label>`;
    const wahl = (attr, wert, liste) => `<select ${attr}${aus}>${liste.map(([v, t]) => `<option value="${esc(v)}"${String(wert) === String(v) ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
    const pf = (name, wert, art = 'zahl', breite = '') => `<input data-f="${name}" class="${breite}" value="${esc(art === 'zahl' ? zt(wert) : wert ?? '')}"${art === 'zahl' ? ' inputmode="decimal"' : ''}${aus}>`;
    const teile = e.teile.map((t) => [t.id, t.name]);
    const fassungen = K.kalk ? K.kalk.fassungen.map((x, i) => `<button class="ci-chip" type="button" data-kk-fassung="${i}" aria-pressed="${i === K.nr && a !== 'neu'}">Fassung ${x.nr} · ${esc(K.start.staende[x.stand])}</button>`).join('') : '';
    const knoepfe = !K.start.rechte.bearbeiten ? '' : {
      neu: `<button class="ci-knopf primaer" type="button" id="kk-speichern">${f ? 'Neue Fassung speichern' : 'Entwurf speichern'}</button>`,
      entwurf: '<button class="ci-knopf primaer" type="button" id="kk-speichern">Entwurf speichern</button><button class="ci-knopf" type="button" id="kk-fest">Endgültig festschreiben</button>',
      endgueltig: '<button class="ci-knopf" type="button" id="kk-neu">Neue Fassung anlegen</button>', aelter: '' }[a];
    const ueber = e.ueberschrieben || {};
    // festgeschrieben: die wirksamen Sätze von damals (überschriebene tragen ihre Vorgabe mit)
    const saetze = a === 'endgueltig' || a === 'aelter' ? f.ergebnis.saetze : K.start.saetze;
    $('#ci-bereich-kalkulation').innerHTML = `<div id="kk-editor" data-id="${esc(K.id)}">
      <div class="ci-leisteoben"><div class="ci-filter"><button class="ci-knopf klein" type="button" id="kk-zurueck">← Alle Container</button>${fassungen}${K.neu ? '<span class="ci-chip" aria-pressed="true">neue Fassung</span>' : ''}</div>
        <div class="ci-knoepfe">${knoepfe}<button class="ci-knopf" type="button" id="kk-csv">${icon('runter')}CSV</button><button class="ci-knopf" type="button" id="kk-druck">${icon('druck')}Drucken</button></div></div>
      <h2 class="kk-titel">Kalkulation ${esc(titel(s))} <span class="ci-leise">${esc([s.lieferant, s.ware].filter(Boolean).join(' · '))}</span> ${a === 'neu' ? marke('neu', 'warn') : marke(K.start.staende[f.stand], f.stand === 'endgueltig' ? 'ok' : 'warn')}<span id="kk-ungespeichert" class="ci-marke warn"${K.geaendert ? '' : ' hidden'}>nicht gespeichert</span></h2>
      ${a !== 'neu' ? `<p class="ci-klein ci-leise">Fassung ${f.nr}: angelegt ${tag(f.erstellt.t)} von ${esc(f.erstellt.von)}${f.grund ? ` · Grund: ${esc(f.grund)}` : ''}${f.endgueltig ? ` · endgültig festgeschrieben ${tag(f.endgueltig.wer.t)} von ${esc(f.endgueltig.wer.von)} – unveränderlich` : ' · vorläufig, rechnet mit den aktuellen Sätzen'}</p>` : ''}
      ${a === 'neu' && f ? `<label class="ci-feld breit"><span>Grund der neuen Fassung (Pflicht)</span><input id="kk-grund" placeholder="z. B. endgültige Gewichte laut Packliste"></label>` : ''}
      ${K.festschreiben ? `<div class="ci-abschluss kk-frage"><span>Fassung ${f.nr} endgültig festschreiben? Danach ist sie unveränderlich; Änderungen nur noch als neue Fassung mit Grund.</span><button class="ci-knopf primaer" type="button" id="kk-fest-ja">Festschreiben</button><button class="ci-knopf" type="button" id="kk-fest-nein">Abbrechen</button></div>` : ''}
      <section class="r-karte kk-block"><h3>Kopf</h3><div class="ci-raster kk-raster">
        ${kfeld('Kurs', 'kurs', 'USD je €', 'z. B. 1,10', 'Für den Zollwert gilt der Zollkurs (Art. 53 UZK).')}<label class="ci-feld"><span>Datum der Zollanmeldung</span>${ein('datum', e.kopf.datum, '', 'date')}<small>Erwartetes Datum der Zollanmeldung – maßgeblich für Satz und Stichtag (Art. 85 UZK).</small></label>
        <label class="ci-feld"><span>Seefracht</span><span class="kk-mit">${ein('seefracht', e.kopf.seefracht)}${wahl('data-k="seefrachtWaehrung"', e.kopf.seefrachtWaehrung, [['USD', 'USD'], ['EUR', '€']])}</span></label>
        ${kfeld('Provision', 'provisionT', '€/t')}<label class="ci-check kk-check"><input type="checkbox" data-k="provisionEinkauf"${e.kopf.provisionEinkauf ? ' checked' : ''}${aus}>Einkaufsprovision (nicht im Zollwert)</label>
        ${kfeld('Nachlauf', 'nachlauf', '€')}${kfeld('Zuschlag Nachlauf', 'nachlaufKg', '€/kg', 'z. B. 0,13 bei Anlieferung bei Dritten')}
        ${kfeld('Zinssatz', 'zins', '%')}${kfeld('Zinstage', 'tage', 'Tage', 'ganze Tage')}${kfeld('Zahlungskosten', 'zahlPromille', '‰')}${kfeld('Zahlungskosten fix', 'zahlFix', '€')}${kfeld('Imaginärer Gewinn (Vers.-Wert)', 'imagGewinn', '%')}
      </div></section>
      <section class="r-karte kk-block"><h3>Teile <span class="ci-leise">· Abnehmer mit eigener Versicherung, Rückvergütung und WKZ</span></h3><div class="kk-scroll"><table class="kk-tab" id="kk-teile">
        <thead><tr><th>Teil</th><th>Abnehmer</th><th>Versicherung % (inkl. Krieg)</th><th>Rückvergütung % vom VK</th><th>WKZ €</th><th></th></tr></thead><tbody>${e.teile.map((t, i) => `
        <tr data-teil="${i}" data-id="${esc(t.id)}"><td>${pf('name', t.name, 'text')}</td><td>${pf('abnehmer', t.abnehmer, 'text', 'breit')}</td><td>${pf('versicherung', t.versicherung)}</td><td>${pf('rueckverguetung', t.rueckverguetung)}</td><td>${pf('wkz', t.wkz)}</td>
          <td>${darf ? `<button class="ci-knopf klein" type="button" data-kk-teil-weg="${i}" aria-label="Teil entfernen">${icon('x')}</button>` : ''}</td></tr>`).join('')}</tbody></table></div>
        ${darf ? '<button class="ci-knopf klein" type="button" id="kk-teil-neu">' + icon('plus') + 'Teil</button>' : ''}</section>
      <section class="r-karte kk-block"><h3>Positionen <span class="ci-leise">· „anteilig Hilton“: denselben Artikel als zweite Position mit anderem Zollregime anlegen (Kopieren)</span></h3><div class="kk-scroll"><table class="kk-tab" id="kk-positionen">
        <thead><tr><th>#</th><th>Teil</th><th>Artikel</th><th>R/L</th><th>Zollregime</th><th>Ursprung</th><th>KN-Code</th><th>Kartons</th><th>Brutto kg</th><th>Netto kg</th><th>Preis</th><th></th><th>Imag. EK €/kg</th><th>VK €/kg</th><th></th></tr></thead><tbody>${e.positionen.map((p, i) => `
        <tr data-pos="${i}"><td>${i + 1}</td><td>${wahl('data-f="teil"', p.teil, teile)}</td><td>${pf('artikel', p.artikel, 'text', 'breit')}</td><td><input type="checkbox" data-f="rl" aria-label="Rump &amp; Loin"${p.rl ? ' checked' : ''}${aus}></td>
          <td>${wahl('data-f="regime"', p.regime, Object.entries(K.start.regime))}${p.regime === 'anderer' ? `<span class="kk-anders">${pf('wertzoll', p.wertzoll)}<i>%</i>${pf('spezifisch', p.spezifisch)}<i>€/100 kg</i>${pf('vermerk', p.vermerk, 'text', 'breit')}</span>` : ''}</td>
          <td>${pf('land', p.land, 'text', 'kurz')}</td><td><input data-f="kn" value="${esc(p.kn)}" list="kk-kn" class="mittel"${aus}></td>
          <td>${pf('kartons', p.kartons)}</td><td>${pf('brutto', p.brutto)}</td><td>${pf('netto', p.netto)}</td><td>${pf('preis', p.preis)}</td><td>${wahl('data-f="waehrung"', p.waehrung, [['USD', 'USD/kg'], ['EUR', '€/kg']])}</td>
          <td>${pf('imagEk', p.imagEk)}</td><td>${pf('vk', p.vk)}</td>
          <td class="kk-nb">${darf ? `<button class="ci-knopf klein" type="button" data-kk-kopie="${i}" title="Position kopieren" aria-label="Position ${i + 1} kopieren">⧉</button><button class="ci-knopf klein" type="button" data-kk-weg="${i}" aria-label="Position ${i + 1} entfernen">${icon('x')}</button>` : ''}</td></tr>`).join('')}</tbody></table></div>
        <datalist id="kk-kn">${Object.values(K.start.kn).map((k) => `<option value="${k.text}">${esc(k.name)}</option>`).join('')}</datalist>
        ${darf ? '<button class="ci-knopf klein" type="button" id="kk-pos-neu">' + icon('plus') + 'Position</button>' : ''}${e.positionen.length ? '' : '<p class="ci-leise ci-klein">Noch keine Position.</p>'}</section>
      <details class="r-karte kk-block" id="kk-saetze"${Object.keys(ueber).length ? ' open' : ''}><summary>Zollsätze <span class="ci-leise">· ${esc(K.start.taric)} · überschreiben nur mit Vermerk</span></summary>
        <div class="kk-scroll"><table class="kk-tab"><thead><tr><th>Satz</th><th>Vorgabe</th><th>Quelle</th><th>Überschreiben: Wertzoll %</th><th>€/100 kg</th><th>Vermerk</th></tr></thead><tbody>${Object.entries(saetze).map(([key, x]) => `
          <tr data-satz="${key}"><td>${esc(x.name)}${x.ab ? `<span class="ci-unter">ab ${tag(x.ab)}</span>` : ''}</td><td class="kk-nb">${satzText(x.vorgabe || x)}</td><td class="kk-quelle">${esc(x.quelle)}${x.laender ? `<span class="ci-unter">Ursprung ${esc(x.laender.join(', '))}</span>` : ''}</td>
          <td>${pf('wert', ueber[key] ? ueber[key].wert : null)}</td><td>${pf('spez', ueber[key] ? ueber[key].spez : null)}</td><td>${pf('vermerk', ueber[key] ? ueber[key].vermerk : '', 'text', 'breit')}</td></tr>`).join('')}</tbody></table></div></details>
      <label class="ci-feld breit kk-block"><span>Notiz</span><textarea data-k="notiz" rows="2"${aus}>${esc(e.notiz)}</textarea></label>
      <div id="kk-ergebnis" aria-live="polite"></div></div>`;
    ergebnis();
  }
  /* Eingabe aus den Feldern (Zahlen als Text – der Server liest auch „1.234,5“) */
  function lesen() {
    const ed = $('#kk-editor'), v = (el) => (el.type === 'checkbox' ? el.checked : el.value.trim());
    const kopf = { ...K.e.kopf };
    for (const el of ed.querySelectorAll('[data-k]')) if (el.dataset.k !== 'notiz') kopf[el.dataset.k] = v(el);
    const zeile = (tr) => Object.fromEntries([...tr.querySelectorAll('[data-f]')].map((el) => [el.dataset.f, v(el)]));
    const ueber = {};
    for (const tr of ed.querySelectorAll('tr[data-satz]')) { const z = zeile(tr); if (z.wert !== '' || z.spez !== '' || z.vermerk !== '') ueber[tr.dataset.satz] = z; }
    return { kopf, teile: [...ed.querySelectorAll('tr[data-teil]')].map((tr) => ({ id: tr.dataset.id, ...zeile(tr) })),
      positionen: [...ed.querySelectorAll('tr[data-pos]')].map((tr, i) => ({ ...K.e.positionen[i], ...zeile(tr) })), ueberschrieben: ueber, notiz: v($('[data-k="notiz"]', ed)) };
  }
  function geaendert(neuZeichnen = false) {
    K.e = lesen(); K.geaendert = true;
    if (neuZeichnen) fokusBehalten(editor); else $('#kk-ungespeichert').hidden = false;
    clearTimeout(K.timer); K.timer = setTimeout(rechnen, 350);
  }
  async function rechnen() {
    const nr = ++K.anfrage;
    const r = await api('containerimport_kalkulation_rechnen', { eingabe: K.e }, '', false);
    if (nr !== K.anfrage || !$('#kk-editor')) return;   // eine neuere Eingabe ist schon unterwegs
    if (r.status === 401) { zeigeAnmeldung(); return; }
    K.erg = r.status === 200 && r.data.ok ? r.data.ergebnis : { fehlerText: fehlerText(r, 'Die Kalkulation konnte nicht gerechnet werden') };
    K.norm = r.status === 200 && r.data.ok ? r.data.eingabe : null;
    ergebnis();
  }

  /* ---------- Ergebnis ---------- */
  function hinweise(erg) {
    const stufe = { fehler: ['Fehler', 'rot'], warnung: ['Warnung', 'warn'], hinweis: ['Hinweis', ''] };
    return erg.hinweise.length ? `<ul class="kk-hinweise" id="kk-hinweise">${erg.hinweise.map((h) => `<li data-stufe="${h.stufe}">${marke(stufe[h.stufe][0], stufe[h.stufe][1])} ${h.pos === null ? '' : `<b>Pos. ${h.pos + 1}:</b> `}${esc(h.text)}</li>`).join('')}</ul>` : '<p class="ci-leise" id="kk-hinweise">Keine Prüfhinweise.</p>';
  }
  const ZEILEN_TEIL = [['Netto', 'netto', kgText], ['davon R/L', 'rl', kgText], ['Kartons', 'kartons', (v) => F.zahl(v, 0, 0)], ['Betrag USD', 'betragUsd', (v) => `${F.zahl(v, 2, 2)} USD`], ['Warenwert', 'warenwert', geld],
    ['Vers.-Wert', 'versWert', geld], ['Vers.-Prämie', 'praemie', geld], ['Zoll', 'zoll', geld], ['Wert Ist (Einstand)', 'ist', geld], ['Wert Soll (Imag. EK)', 'soll', geld], ['VK-Wert', 'vkWert', geld],
    ['Rohertrag', 'rohertrag', geld], ['Marge vom VK', 'marge', pz], ['Aufschlag auf Ist', 'aufschlag', pz], ['Rohertrag je kg', 'eurKg', proKg], ['Rückvergütung', 'rueckverguetung', geld], ['WKZ', 'wkz', geld], ['Rohgewinn', 'rohgewinn', geld]];
  function ergebnis() {
    const ziel = $('#kk-ergebnis'), erg = K.erg;
    if (!ziel) return;
    if (!erg) { ziel.innerHTML = ''; return; }
    if (erg.fehlerText) { ziel.innerHTML = `<section class="r-karte kk-block"><h3>Prüfhinweise</h3><p class="ci-fehler" id="kk-hinweise">${esc(erg.fehlerText)}</p></section>`; return; }
    let html = `<section class="r-karte kk-block"><h3>Prüfhinweise</h3>${hinweise(erg)}</section>`;
    if (!erg.vollstaendig) { ziel.innerHTML = html + '<p class="ci-leise kk-block" id="kk-unvollstaendig">Kalkulation unvollständig – bitte die Fehler oben beheben.</p>'; return; }
    const e = K.e, g = erg.gesamt, rg = K.start.regime, namen = Object.fromEntries(e.teile.map((t) => [t.id, t.name]));
    html += `<section class="r-karte kk-block"><h3>Je Position <span class="ci-leise">· € je kg</span></h3><div class="kk-scroll"><table class="kk-tab kk-zahlen" id="kk-pos-ergebnis"><thead><tr><th>#</th><th class="kk-text">Artikel</th><th class="kk-text">Satz</th><th>Preis €</th><th>Fracht</th><th>Vers.</th><th>Prov.</th><th>Zollwert</th><th>Zoll</th><th>Einstand vor NK</th><th>Nebenk.</th><th>Einstand</th><th>Anteil Teil</th><th>Wert Ist</th><th>Soll</th><th>VK-Wert</th></tr></thead><tbody>${erg.positionen.map((r, i) => `
      <tr><td>${i + 1}</td><td class="kk-text">${esc(e.positionen[i].artikel)}<span class="ci-unter">${esc(namen[e.positionen[i].teil] || '')} · ${esc(rg[e.positionen[i].regime])}</span></td><td class="kk-text">${esc(r.satzName)}<span class="ci-unter">${satzText({ wert: r.wertzoll, spez: r.spezifisch })}</span></td>
        <td>${F.zahl(r.preisEur, 2, 4)}</td><td>${F.zahl(r.frachtKg, 2, 4)}</td><td>${F.zahl(r.versKg, 2, 4)}</td><td>${F.zahl(r.provisionKg, 2, 4)}</td><td>${F.zahl(r.zollwertKg, 2, 4)}</td><td>${F.zahl(r.zollKg, 2, 4)}</td>
        <td>${F.zahl(r.einstandVorNkKg, 2, 4)}</td><td>${F.zahl(r.nebenkostenKg, 2, 4)}</td><td><b>${F.zahl(r.einstandKg, 2, 4)}</b></td><td>${pz(r.anteilTeil)}</td><td>${geld(r.ist)}</td><td>${geld(r.soll)}</td><td>${geld(r.vkWert)}</td></tr>`).join('')}</tbody></table></div></section>`;
    const spalten = [...erg.teile.map((t) => [namen[t.id] || t.id, t]), ['Gesamt', g]];
    html += `<section class="r-karte kk-block"><h3>Je Teil und gesamt</h3><div class="kk-scroll"><table class="kk-tab kk-zahlen" id="kk-teil-ergebnis"><thead><tr><th></th>${spalten.map(([n]) => `<th>${esc(n)}</th>`).join('')}</tr></thead><tbody>${ZEILEN_TEIL.map(([label, k, fmt]) => `
      <tr data-zeile="${k}"><th scope="row">${label}</th>${spalten.map(([, x]) => `<td>${x[k] === undefined ? '' : x[k] === null ? (k === 'vkWert' ? 'VK fehlt' : '—') : fmt(x[k])}</td>`).join('')}</tr>`).join('')}</tbody></table></div>
      <p class="ci-klein ci-leise">Seefracht ${geld(g.seefracht)} (${proKg(g.frachtKg)}) · Provision ${proKg(g.provisionKg)} · Nebenkosten: Nachlauf ${geld(g.nachlauf)}, Finanzierung ${geld(g.finanzierung)}, Zahlungskosten ${geld(g.zahlungskosten)} → ${proKg(g.nebenkostenKg)}</p></section>`;
    const v = erg.vergleich, kg = erg.kgJeRegime;
    html += `<section class="r-karte kk-block" id="kk-kontingente"><h3>Kontingente und Zoll</h3><ul class="kk-liste">
      <li>Hilton-Kontingent: <b>${kgText(kg.hilton || 0)}</b></li><li>Mercosur-Kontingent: <b>${kgText(kg.mercosur || 0)}</b> = ${erg.mercosurSke === null ? 'Schlachtkörperäquivalent nicht ermittelbar (KN-Code, siehe Prüfhinweise)' : `${kgText(erg.mercosurSke)} Schlachtkörperäquivalent`}</li>
      ${Object.entries(erg.zollJeRegime).map(([r, z]) => `<li>Zoll ${esc(rg[r])}: <b>${geld(z)}</b> auf ${kgText(erg.kgJeRegime[r])}</li>`).join('')}
      ${v ? `<li id="kk-vergleich">Ohne Hilton, Ursprung Mercosur (${kgText(v.kg)}): Zoll mit Mercosur-Kontingent <b>${geld(v.mitQuote)}</b>, ohne Kontingent (Drittlandszoll) <b>${geld(v.ohneQuote)}</b> – Unterschied <b>${geld(v.ersparnis)}</b></li>` : ''}
      ${erg.anteilig.map((a) => `<li>Anteilig Hilton: ${esc(a.artikel)} – ${pz(a.anteilHilton)} im Hilton-Kontingent (${Object.entries(a.regime).map(([r, kg]) => `${esc(rg[r])} ${kgText(kg)}`).join(', ')})</li>`).join('')}</ul></section>`;
    ziel.innerHTML = html;
  }

  /* ---------- Speichern, Fassungen ---------- */
  async function speichern() {
    const grund = K.neu ? $('#kk-grund').value.trim() : '';
    if (K.neu && !grund) { toast('Bitte den Grund der neuen Fassung angeben.', true); $('#kk-grund').focus(); return; }
    const r = await api('containerimport_kalkulation_speichern', { sendung: K.id, rev: K.kalk ? K.kalk.rev : 0, eingabe: lesen(), grund });
    if (!antwortOk(r, 'Die Kalkulation konnte nicht gespeichert werden')) return;
    nachSpeichern(r.data);
    toast(grund ? 'Neue Fassung gespeichert.' : 'Kalkulation gespeichert.');
  }
  function nachSpeichern(d) {
    Object.assign(K, { kalk: d.kalkulation, container: d.container, neu: false, geaendert: false, festschreiben: false });
    K.start.uebersicht = d.uebersicht;
    zeigeFassung(letzte());
  }
  async function festschreiben() {
    const r = await api('containerimport_kalkulation_festschreiben', { sendung: K.id, rev: K.kalk.rev });
    if (!antwortOk(r, 'Die Kalkulation konnte nicht festgeschrieben werden')) return;
    nachSpeichern(r.data);
    toast('Kalkulation endgültig festgeschrieben.');
  }

  /* ---------- CSV und Druck ---------- */
  /* CSV mit Semikolon und BOM (Excel): Zahlen deutsch ohne Tausenderpunkt; Texte, die Excel als Formel lesen würde (=, +, @,
     Tab, „-“ ohne Ziffer), beginnen mit einem Apostroph (CSV-Injection, wie controlling/umsatz-auswertung.js) */
  const csvZelle = (x) => {
    if (x === null || x === undefined) return '';
    if (typeof x === 'number') return x.toLocaleString('de-DE', { useGrouping: false, maximumFractionDigits: 6 });
    let t = String(x).replace(/[\r\n]+/g, ' ');
    if (/^[=+@\t]/.test(t) || /^-(?![\d,])/.test(t)) t = "'" + t;
    return `"${t.replace(/"/g, '""')}"`;
  };
  function csv() {
    const e = K.norm, erg = K.erg, s = sendung(K.id) || K.container, f = fassung();
    if (!e || !erg || !erg.vollstaendig) { toast('Die Kalkulation ist unvollständig – keine Datei.', true); return; }
    const kopf = ['Pos', 'Teil', 'Artikel', 'R/L', 'Zollregime', 'Satz', 'Ursprung', 'KN', 'Kartons', 'Brutto kg', 'Netto kg', 'Preis', 'Währung', 'Preis €/kg', 'Fracht €/kg', 'Vers. €/kg', 'Provision €/kg', 'Zollwert €/kg', 'Zoll €/kg',
      'Einstand vor NK €/kg', 'Nebenkosten €/kg', 'Einstand €/kg', 'Wert Ist €', 'Imag. EK €/kg', 'Soll €', 'VK €/kg', 'VK-Wert €'];
    const namen = Object.fromEntries(e.teile.map((t) => [t.id, t.name]));
    const zeilen = [[`Kalkulation ${titel(s)}`, standText(), `erstellt ${F.datumZeit(new Date())} von ${S.d.name}`], [], kopf,
      ...erg.positionen.map((r, i) => { const p = e.positionen[i]; return [i + 1, namen[p.teil], p.artikel, p.rl ? 'ja' : '', K.start.regime[p.regime], r.satzName, p.land, p.kn, p.kartons, p.brutto, p.netto, p.preis, p.waehrung,
        r.preisEur, r.frachtKg, r.versKg, r.provisionKg, r.zollwertKg, r.zollKg, r.einstandVorNkKg, r.nebenkostenKg, r.einstandKg, r.ist, p.imagEk, r.soll, p.vk, r.vkWert]; }),
      [], ['Kennzahl', ...erg.teile.map((t) => namen[t.id]), 'Gesamt'], ...ZEILEN_TEIL.map(([label, k]) => [label, ...erg.teile.map((t) => t[k]), erg.gesamt[k]])];
    const nr = ansicht() === 'neu' ? 'neu' : f.nr;
    herunterladen(`Kalkulation_${String(s.partie || s.id).replace(/[^A-Za-z0-9_-]+/g, '_')}_Fassung_${nr}${K.geaendert ? '_ungespeichert' : ''}.csv`,
      new Blob(['\ufeff' + zeilen.map((z) => z.map(csvZelle).join(';')).join('\r\n') + '\r\n'], { type: 'text/csv;charset=utf-8' }));
  }
  /* Druckfassung in #ci-druck als eigener Block .kk-druck (A4 quer); false ohne Ergebnis */
  function druckInhalt() {
    const ed = $('#kk-ergebnis'), s = sendung(K.id) || K.container, k = K.e.kopf;
    if (!ed || !K.erg || K.erg.fehlerText) return false;
    $('#ci-druck').innerHTML = `<div class="kk-druck"><h1>Kalkulation ${esc(titel(s))}</h1>
      <p>${esc([s.lieferant, s.ware].filter(Boolean).join(' · '))} · ${esc(standText())} · gedruckt ${F.datumZeit(new Date())} von ${esc(S.d.name)}</p>
      <p>Kurs ${esc(zt(k.kurs))} USD/€ · Datum der Zollanmeldung ${tag(k.datum)} · Seefracht ${esc(zt(k.seefracht))} ${esc(k.seefrachtWaehrung)} · Provision ${esc(zt(k.provisionT))} €/t (${k.provisionEinkauf ? 'Einkaufsprovision, nicht im Zollwert' : 'im Zollwert'}) · Nachlauf ${esc(zt(k.nachlauf))} € + ${esc(zt(k.nachlaufKg))} €/kg · Zins ${esc(zt(k.zins))} % für ${esc(zt(k.tage))} Tage · Zahlungskosten ${esc(zt(k.zahlPromille))} ‰ + ${esc(zt(k.zahlFix))} € · Imag. Gewinn ${esc(zt(k.imagGewinn))} %</p>
      ${ed.innerHTML.replace(/ id="[^"]*"/g, '')}<p class="ci-d-fuss">Zollsätze ${esc(K.start.taric)}. Gerechnet vom Server; Beträge auf Cent gerundet angezeigt.</p></div>`;
    return true;
  }
  function drucken() {
    if (!druckInhalt()) { toast('Kein Ergebnis zum Drucken.', true); return; }
    window.print();
  }
  // Drucken über das Browsermenü im Reiter: Druckfassung frisch erzeugen. Danach leeren, damit nichts Altes stehen bleibt.
  window.addEventListener('beforeprint', () => { if (S.reiter === 'kalkulation' && K.id && $('#kk-editor')) druckInhalt(); });
  window.addEventListener('afterprint', () => { if ($('#ci-druck .kk-druck')) $('#ci-druck').innerHTML = ''; });

  /* ---------- Ereignisse ---------- */
  C.reiter.kalkulation = zeichnen;
  document.addEventListener('click', (ev) => {
    const t = ev.target;
    if (!t.closest('#ci-bereich-kalkulation')) { if (t.closest('#ci-neu')) K.start = null; return; }   // „Stand neu laden“: auch die Übersicht neu holen
    const zeile = t.closest('tr[data-kalk]');
    if (zeile) { oeffnen(zeile.dataset.kalk); return; }
    if (t.closest('#kk-zurueck')) {
      if (K.geaendert && !K.verwerfen) { K.verwerfen = true; toast('Ungespeicherte Änderungen – nochmals klicken, um sie zu verwerfen.', true); return; }
      Object.assign(K, { id: '', kalk: null, geaendert: false, verwerfen: false, neu: false }); zeichnen(); return;
    }
    const fa = t.closest('[data-kk-fassung]');
    if (fa) { if (K.geaendert) { toast('Bitte zuerst speichern.', true); return; } K.neu = false; K.festschreiben = false; zeigeFassung(+fa.dataset.kkFassung); return; }
    if (t.closest('#kk-speichern')) { speichern(); return; }
    if (t.closest('#kk-fest')) { if (K.geaendert) { toast('Bitte zuerst speichern – festgeschrieben wird der gespeicherte Stand.', true); return; } K.festschreiben = true; fokusBehalten(editor); return; }
    if (t.closest('#kk-fest-nein')) { K.festschreiben = false; editor(); return; }
    if (t.closest('#kk-fest-ja')) { festschreiben(); return; }
    if (t.closest('#kk-neu')) { K.neu = true; K.e = JSON.parse(JSON.stringify(fassung().eingabe)); editor(); rechnen(); $('#kk-grund').focus(); return; }
    if (t.closest('#kk-csv')) { csv(); return; }
    if (t.closest('#kk-druck')) { drucken(); return; }
    if (t.closest('#kk-pos-neu')) { K.e = lesen(); K.e.positionen.push(neuePosition(K.e.teile[K.e.teile.length - 1].id)); geaendertStruktur(); return; }
    if (t.closest('#kk-teil-neu')) {
      K.e = lesen();
      let n = K.e.teile.length + 1;
      while (K.e.teile.some((x) => x.id === 't' + n)) n++;
      K.e.teile.push({ id: 't' + n, name: 'Teil ' + n, abnehmer: '', versicherung: null, rueckverguetung: null, wkz: null }); geaendertStruktur(); return;
    }
    const kopie = t.closest('[data-kk-kopie]'), weg = t.closest('[data-kk-weg]'), teilWeg = t.closest('[data-kk-teil-weg]');
    if (kopie) { K.e = lesen(); const i = +kopie.dataset.kkKopie; K.e.positionen.splice(i + 1, 0, { ...K.e.positionen[i] }); geaendertStruktur(); return; }
    if (weg) { K.e = lesen(); K.e.positionen.splice(+weg.dataset.kkWeg, 1); geaendertStruktur(); return; }
    if (teilWeg) {
      K.e = lesen();
      const teil = K.e.teile[+teilWeg.dataset.kkTeilWeg];
      if (K.e.positionen.some((p) => p.teil === teil.id)) { toast('Der Teil hat noch Positionen.', true); return; }
      if (K.e.teile.length === 1) { toast('Mindestens ein Teil bleibt.', true); return; }
      K.e.teile = K.e.teile.filter((x) => x !== teil); geaendertStruktur();
    }
  });
  function geaendertStruktur() { K.geaendert = true; K.verwerfen = false; editor(); clearTimeout(K.timer); K.timer = setTimeout(rechnen, 100); }
  document.addEventListener('input', (ev) => { if (ev.target.closest('#kk-editor') && ev.target.id !== 'kk-grund' && !ev.target.matches('select')) { K.verwerfen = false; geaendert(false); } });
  document.addEventListener('change', (ev) => {
    if (!ev.target.closest('#kk-editor') || ev.target.id === 'kk-grund') return;
    K.verwerfen = false;
    if (ev.target.matches('select, [type=checkbox]')) geaendert(ev.target.dataset.f === 'regime' || ev.target.dataset.f === 'teil');
  });
})();
