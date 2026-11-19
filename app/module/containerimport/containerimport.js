/* STAFL-Plattform · Modul Container-Import – Container (ein Einkauf bei einem Lieferanten, eine Partienummer) mit ihren
   Farmern; Reiter EUDR: Hilfen und Kontrollen zur EU-Verordnung über entwaldungsfreie Lieferketten (Aufträge des Inhabers
   18. und 19.11.2026; Gestaltung „C2“).
   Begriffe: die Seite sagt „Container“ und „Farmer“; im Code und in den Daten heißen sie „sendung“ und „betrieb“
   (bestehende Daten und Aktionsnamen, siehe app/api/module/containerimport/eudr.php).
   Ansichten: Container (Lieferant, Schlachthof, Nummern, Stand, Risikoprofil), Schlachthöfe (Stammdaten unter dem Lieferanten,
   eigene Datei schlachthoefe.js über die Brücke window.STAFL_CI), Farmer (Geolokalisierung, Bericht, eigene Gegenprüfung), Karte.
   Daten: containerimport_start (Stand), containerimport_eudr_pruefen (Dateien prüfen, ohne zu speichern),
   containerimport_eudr_betriebe_save, _original, _gegenpruefung, _sendung_save, _sendung_abschluss (jede Antwort bringt den neuen
   Stand mit), containerimport_eudr_export (GeoJSON für das EU-Informationssystem), containerimport_eudr_whisp (Whisp für
   einen Betrieb abfragen; speichert nichts, Deutung in eudr-whisp.js).
   Unterlagen einlesen: Entwaldungsberichte (PDF) liest der Browser mit pdf.js (assets/vendor/pdfjs, eudr-bericht.js);
   Lieferanten-GeoJSON und eingefügte Koordinaten prüft der Server. Am Betrieb stehen Name und Prüfsumme der Datei. Beim
   Übernehmen gehen die Originale – wenn angehakt – in Teilen an containerimport_eudr_original und von dort in den Eingang
   des QM-Systems (Entscheidung des Inhabers 18.11.2026). Alle Regeln (Umrechnung, Prüfung der Flächen, Risikoprofil) liegen auf dem Server; diese Seite zeigt an.
   Fenster schließen nur über ×, „Schließen“ oder Escape (theme.js). Rechte prüft der Server bei jeder Aktion (GR-103);
   ausgeblendete Knöpfe sind nur Anzeige. Kein Inline-Skript (CSP); fremde Texte nur maskiert. */
'use strict';
(() => {
  const API = '../../api/';
  const PDFJS = new URL('../../assets/vendor/pdfjs/', document.currentScript.src).href;
  const TEIL = 2 * 1024 * 1024;            // Bytes je Teil beim Ablegen eines Originals (Base64 bleibt unter der Grenze des Servers)
  const MAX_ANFRAGE = 3 * 1024 * 1024;     // je Durchgang; der Server nimmt 6 MB an, braucht zum Prüfen aber ein Vielfaches an Speicher
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const F = window.STAFL_FORMAT, SU = window.STAFL_SUCHE;
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (n) => `<svg class="r-i" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const plural = (n, ein, viele) => `${n} ${n === 1 ? ein : viele}`;
  const S = { csrf: '', d: null, sicht: 'sendungen', suche: { sendungen: '', betriebe: '' }, archiv: false, karteSendung: '', lesen: null, toast: 0, sendet: false };

  /* ---------- Aufruf der API: wirft nie, liefert { status, data } ---------- */
  async function api(action, body, query = '', sperre = true) {   // sperre = false: Abfrage im Hintergrund, hält keine Eingabe auf
    if (sperre && body && S.sendet) return { status: 0, data: { error: 'Bitte einen Moment – die letzte Eingabe wird noch verarbeitet.' } };   // kein Doppeltes durch Doppelklick
    if (body && sperre) S.sendet = true;
    let res;
    try {
      res = await fetch(API + '?action=' + action + query, {
        method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
        headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': S.csrf } : {}, body: body ? JSON.stringify(body) : undefined,
      });
    } catch { return { status: 0, data: {} }; } finally { if (body && sperre) S.sendet = false; }
    let data = null;
    try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
    return { status: res.status, data: data || {} };
  }
  const fehlerText = (r, fallback) => (r.data && r.data.error) || (r.status === 0 ? 'Keine Verbindung zum Server.' : r.status === 413 ? 'Die Dateien sind zusammen zu groß (höchstens 3 MB je Durchgang).' : `${fallback} (${r.status}).`);
  function toast(text, fehlerhaft = false) {
    const t = $('#ci-toast');
    t.textContent = text; t.className = 'ci-toast zeigen' + (fehlerhaft ? ' fehler' : '');
    clearTimeout(S.toast); S.toast = setTimeout(() => { t.className = 'ci-toast'; }, fehlerhaft ? 6000 : 2800);
  }
  function fehler(text) { $('#ci-login').hidden = true; $('#ci-app').hidden = true; $('#ci-err').hidden = false; $('#ci-err').textContent = text; }
  function zeigeAnmeldung() { $$('dialog[open]').forEach((d) => d.close()); $('#ci-login').hidden = false; $('#ci-app').hidden = true; }
  /* Antwort einer speichernden Aktion: neuen Stand übernehmen. false = Fehler (Meldung gezeigt) */
  function uebernehmen(r, fallback) {
    if (r.status === 401) { zeigeAnmeldung(); return false; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, fallback), true); return false; }
    S.d = { ...S.d, ...r.data };
    zeichnen();
    return true;
  }

  /* ---------- Formate und Bezeichnungen ---------- */
  const ha = (v) => (v === null || v === undefined ? F.LEER : `${F.zahl(v, 2, 2)} ha`);
  const tag = (t) => (t ? F.datum(t) : '—');
  const marke = (text, klasse = '') => `<span class="ci-marke ${klasse}">${esc(text)}</span>`;
  const NACHWEIS = { konform: ['konform', 'ok'], nicht_konform: ['nicht konform', 'rot'], unbekannt: ['ohne Angabe', 'warn'] };
  const STAND = { ok: ['in Ordnung', 'ok'], hinweis: ['Hinweis', ''], offen: ['offen', 'warn'], kritisch: ['kritisch', 'rot'] };
  const GEO = { ok: ['einreichbar', 'ok'], hinweis: ['einreichbar · Hinweis', ''], fehler: ['fehlerhaft', 'rot'] };
  const DREI = [['offen', 'noch offen'], ['ja', 'ja, belegt'], ['nein', 'nein']];
  const ERGEBNIS = { vernachlaessigbar: ['Risiko vernachlässigbar', 'ok'], nicht_vernachlaessigbar: ['Risiko nicht vernachlässigbar', 'rot'] };
  const HINWEIS_NUMMER = { pruefziffer: 'Die Prüfziffer passt nicht – Tippfehler?', format: 'Üblich sind vier Buchstaben und sieben Ziffern, z. B. MSKU 907032 3.' };
  /* Lieferant im Eingabefeld: „Name (Nummer)“. Zur Wahl stehen die Stammdaten und die gespeicherte Verknüpfung des
     Containers, auch wenn der Lieferant dort inzwischen fehlt – nur ein genau so gewählter Text verknüpft. */
  const lieferantText = (l) => `${l.name} (${l.nr})`;
  const lieferantWahl = (s) => (s && s.lieferantNr && !S.d.lieferanten.some((l) => l.nr === s.lieferantNr) ? [{ nr: s.lieferantNr, name: s.lieferant }, ...S.d.lieferanten] : S.d.lieferanten);
  /* Eingabe im Feld „Lieferant“ → { lieferantNr, lieferant }; alt = der gespeicherte Eintrag (Container oder Schlachthof) */
  const lieferantAus = (text, alt) => {
    const g = lieferantWahl(alt).find((l) => lieferantText(l).toLowerCase() === text.toLowerCase());
    return { lieferantNr: g ? g.nr : '', lieferant: g ? g.name : text };   // ohne Treffer freier Text ohne Verknüpfung
  };
  /* Gleicher Lieferant = gleicher Schlüssel: mit Nummer der Stammdaten die Nummer, sonst der Name (wie ci_lieferant_schluessel
     auf dem Server). Danach richtet sich, welche Schlachthöfe im Fenster „Container“ zur Wahl stehen: die aktiven des
     Lieferanten; der gespeicherte bleibt wählbar, auch archiviert. */
  const lieferantSchluessel = (x) => (x.lieferantNr ? 'nr:' + x.lieferantNr : 'name:' + x.lieferant.toLowerCase());
  function schlachthofWahl(lieferant, aktuell) {
    const k = lieferantSchluessel(lieferant);
    const liste = S.d.schlachthoefe.filter((x) => (x.aktiv && lieferantSchluessel(x) === k) || x.id === aktuell).sort((a, b) => a.name.localeCompare(b.name, 'de'));
    return [['', liste.length ? '— kein Schlachthof —' : '— für diesen Lieferanten ist keiner angelegt —'], ...liste.map((x) => [x.id, x.name + (x.zulassung ? ` · ${x.zulassung}` : '') + (x.aktiv ? '' : ' (archiviert)')])];
  }
  const landName = (code) => (S.d.laender[code] ? S.d.laender[code].name : code);
  const betrieb = (id) => S.d.betriebe.find((b) => b.id === id);
  const sendung = (id) => S.d.sendungen.find((s) => s.id === id);
  const profilMarke = (p) => {
    const n = p.kriterien.filter((k) => k.stand === p.stand).length;
    return p.stand === 'ok' ? marke('kein Risiko erkennbar', 'ok') : marke(`${plural(n, 'Punkt', 'Punkte')} ${STAND[p.stand][0]}`, STAND[p.stand][1]);
  };
  /* Eigene Gegenprüfung eines Betriebs, wie der Server sie bewertet (jüngste je Portal): Marke und Portale mit Datum */
  const PRUEFUNG = { ok: ['ohne Befund', 'ok'], offen: ['offen', 'warn'], kritisch: ['Befund', 'rot'] };
  const pruefungText = (b) => b.pruefungenAktuell.map((p) => `${S.d.portale[p.portal].name} · ${tag(p.datum)}`).join(', ');

  /* ---------- Bausteine für Fenster und Formulare ---------- */
  const kopf = (id, titel, unter = '') => `<div class="dlg-head"><div><h2 id="${id}">${esc(titel)}</h2>${unter ? `<p>${unter}</p>` : ''}</div>
    <button class="ci-zu" type="button" data-zu aria-label="Schließen">${icon('x')}</button></div>`;
  function feld(label, name, wert, o = {}) {
    const attr = `name="${name}"${o.aus ? ' disabled' : ''}`;
    let eingabe;
    if (o.wahl) eingabe = `<select ${attr}>${o.wahl.map(([v, t]) => `<option value="${esc(v)}"${String(wert ?? '') === String(v) ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
    else if (o.lang) eingabe = `<textarea ${attr} rows="${o.lang}">${esc(wert ?? '')}</textarea>`;
    else eingabe = `<input ${attr} type="${o.typ || 'text'}" value="${esc(wert ?? '')}"${o.typ === 'date' ? ` max="2099-12-31"` : ''}${o.platz ? ` placeholder="${esc(o.platz)}"` : ''}${o.zahl ? ' inputmode="decimal"' : ''}${o.liste ? ` list="${o.liste}"` : ''}>`;
    return `<label class="ci-feld${o.breit ? ' breit' : ''}${o.zwei ? ' zwei' : ''}"><span>${esc(label)}</span>${eingabe}${o.hinweis ? `<small>${esc(o.hinweis)}</small>` : ''}</label>`;
  }
  /* Werte aller benannten Felder eines Formulars als Objekt (Kontrollkästchen mit gleichem Namen als Liste) */
  function werte(form) {
    const aus = {};
    for (const el of $$('[name]', form)) {
      if (el.type === 'checkbox') { if (el.dataset.liste !== undefined) { aus[el.name] = aus[el.name] || []; if (el.checked) aus[el.name].push(el.value); } else aus[el.name] = el.checked; }
      else aus[el.name] = el.value.trim();
    }
    return aus;
  }
  /* Auswahl der Länder; ein gespeicherter Code außerhalb der Liste (z. B. aus einem GeoJSON) bleibt wählbar */
  const laenderWahl = (aktuell) => [...Object.entries(S.d.laender).map(([c, l]) => [c, `${l.name} (${c})`]), ...(aktuell && !S.d.laender[aktuell] ? [[aktuell, aktuell]] : [])].sort((a, b) => a[1].localeCompare(b[1], 'de'));
  function oeffnen(dlg) { if (!dlg.open) dlg.showModal(); }
  /* Feld „Lieferant“ mit den Vorschlägen der Stammdaten (Fenster „Container“ und „Schlachthof“); kennung = id der Vorschlagsliste */
  function lieferantFeld(s, aus, neu, kennung) {
    const darf = S.d.rechte.bearbeiten, verknuepft = lieferantWahl(s).find((l) => l.nr === s.lieferantNr);   // die Stammdaten bekommt nur, wer bearbeiten darf
    const hinweis = verknuepft ? `Stammdaten Nr. ${s.lieferantNr}${!darf || S.d.lieferanten.includes(verknuepft) ? '' : ' – dort nicht mehr vorhanden'}`
      : !darf ? 'Nicht mit den Stammdaten verknüpft.' : S.d.lieferanten.length ? (neu ? 'Aus den Stammdaten wählen: Namen tippen und den Vorschlag anklicken.' : 'Nicht mit den Stammdaten verknüpft – Namen tippen und den Vorschlag anklicken.') : 'In der Verwaltung sind noch keine Lieferanten eingelesen – freier Text.';
    return feld('Lieferant', 'lieferant', verknuepft && !aus ? lieferantText(verknuepft) : s.lieferant, { aus, liste: kennung, hinweis })
      + `<datalist id="${kennung}">${lieferantWahl(s).map((l) => `<option value="${esc(lieferantText(l))}">`).join('')}</datalist>`;
  }
  const zahlText = (v) => (v === null || v === undefined || v === '' ? '' : String(v).replace('.', ','));

  /* ---------- Seite ---------- */
  function zeichnen() {
    const d = S.d, aktiv = d.betriebe.filter((b) => b.aktiv), offen = d.sendungen.filter((s) => s.aktiv && !s.abschluss);
    $('#ci-unterzeile').textContent = `${offen.length} Container in Prüfung · ${aktiv.length} Farmer`;
    const sichten = [['sendungen', 'Container', d.sendungen.filter((s) => s.aktiv).length], ['schlachthoefe', 'Schlachthöfe', d.schlachthoefe.filter((x) => x.aktiv).length], ['betriebe', 'Farmer', aktiv.length], ['karte', 'Karte', null]];
    $('#ci-sichten').innerHTML = sichten.map(([k, t, n]) => `<button class="ci-chip" type="button" data-sicht="${k}" aria-pressed="${S.sicht === k}">${t}${n === null ? '' : ` <b>${n}</b>`}</button>`).join('');
    $('#ci-knoepfe').innerHTML = d.rechte.bearbeiten
      ? `<button class="ci-knopf" type="button" id="ci-lesen">${icon('hoch')}Unterlagen einlesen</button><button class="ci-knopf primaer" type="button" id="ci-sendung-neu">${icon('plus')}Neuer Container</button>` : '';
    sichtZeichnen();
  }
  const SICHTEN = { sendungen: sendungenSicht, betriebe: betriebeSicht, karte: karteSicht };   // weitere Dateien tragen ihre Ansicht ein (Brücke STAFL_CI)
  const sichtZeichnen = () => SICHTEN[S.sicht]();

  const suchfeld = (platz, name) => `<input type="search" id="ci-suche" value="${esc(S.suche[S.sicht])}" placeholder="${platz}" aria-label="${name} durchsuchen">`;
  const suchzeile = (platz, name) => `<div class="ci-suchzeile">${suchfeld(platz, name)}</div>`;
  function sendungenSicht() {
    const liste = S.d.sendungen.filter((s) => (s.aktiv || S.archiv) && SU.findet(S.suche.sendungen, s.partie, s.akte, s.container, s.nummer, s.lieferant, s.lieferantNr, s.schlachthofName, s.ware, landName(s.land), s.dds.referenz))
      .sort((a, b) => b.erstellt.t.localeCompare(a.erstellt.t));
    const zeile = (s) => `<tr data-sendung="${esc(s.id)}" tabindex="0" class="${s.aktiv ? '' : 'ci-archiv'}">
      <td><span class="ci-name">${esc(s.name)}</span><span class="ci-unter">${esc([s.akte && `Akte ${s.akte}`, s.container && `Container ${s.container}`].filter(Boolean).join(' · ') || '—')}</span></td>
      <td data-t="Lieferant"><span>${esc(s.lieferant)}</span><span class="ci-unter">${esc(landName(s.land))}${s.lieferantNr ? ` · Nr. ${esc(s.lieferantNr)}` : ' · nicht mit den Stammdaten verknüpft'}${s.schlachthofName ? ` · ${esc(s.schlachthofName)}` : ''}</span></td>
      <td data-t="Ware"><span>${esc(s.ware || '—')}</span><span class="ci-unter">${s.mengeKg === null ? '' : F.kg(s.mengeKg)}${s.lose ? ` · Lose ${esc(s.lose)}` : ''}</span></td>
      <td data-t="Stand">${marke(S.d.staende[s.stand], s.stand === 'angekommen' ? 'ok' : '')}</td>
      <td data-t="Farmer" class="ci-r">${s.betriebe.length}</td>
      <td data-t="Risikoprofil">${profilMarke(s.profil)}</td>
      <td data-t="Bewertung">${s.abschluss ? marke(ERGEBNIS[s.abschluss.ergebnis][0], ERGEBNIS[s.abschluss.ergebnis][1]) + `<span class="ci-unter">${tag(s.abschluss.wer.t)} · ${esc(s.abschluss.wer.von)}</span>` : '<span class="ci-leise">in Prüfung</span>'}${s.dds.referenz ? `<span class="ci-unter">Sorgfaltserklärung <span class="ci-zahlen">${esc(s.dds.referenz)}</span></span>` : ''}</td></tr>`;
    $('#ci-inhalt').innerHTML = (S.d.sendungen.length ? suchzeile('Partie, Akte, Containernummer, Lieferant, Schlachthof, Ware', 'Container') : '') + (liste.length
      ? `<div class="r-karte"><table class="ci-tab" id="ci-sendungen"><thead><tr><th scope="col">Partie</th><th scope="col">Lieferant</th><th scope="col">Ware</th><th scope="col">Stand</th><th scope="col" class="ci-r">Farmer</th><th scope="col">Risikoprofil</th><th scope="col">Bewertung</th></tr></thead><tbody>${liste.map(zeile).join('')}</tbody></table></div>`
      : `<div class="r-karte"><p class="ci-leer">${S.d.sendungen.length ? 'Kein Container passt zur Suche.' : 'Noch kein Container. Legen Sie einen Container an und lesen Sie die Unterlagen des Lieferanten ein.'}</p></div>`) + archivSchalter();
  }
  const archivSchalter = () => `<label class="ci-check ci-archivwahl"><input type="checkbox" id="ci-archiv"${S.archiv ? ' checked' : ''}>Archivierte anzeigen</label>`;

  function betriebeSicht() {
    const woerter = S.suche.betriebe;
    const liste = S.d.betriebe.filter((b) => (b.aktiv || S.archiv) && SU.findet(woerter, b.name, b.erzeuger, b.kennung, b.region, b.ort, landName(b.land), b.quelle.lieferant))
      .sort((a, b) => a.name.localeCompare(b.name, 'de'));
    const zeile = (b) => {
      const n = S.d.sendungen.filter((s) => s.betriebe.includes(b.id)).length, p = PRUEFUNG[b.bewertung.gegenpruefung];
      return `<tr data-betrieb="${esc(b.id)}" tabindex="0" class="${b.aktiv ? '' : 'ci-archiv'}">
        <td><span class="ci-name"><i class="ci-ampel ${b.ampel}" aria-hidden="true"></i>${esc(b.name)}</span><span class="ci-unter">${esc(b.erzeuger || '—')}</span></td>
        <td data-t="Lage"><span>${esc(landName(b.land))}</span><span class="ci-unter">${esc([b.region, b.ort].filter(Boolean).join(' · '))}</span></td>
        <td data-t="Kennung" class="ci-zahlen">${esc(b.kennung || '—')}</td>
        <td data-t="Fläche" class="ci-r ci-zahlen">${ha(b.flaeche)}</td>
        <td data-t="Geolokalisierung">${marke(GEO[b.stand][0], GEO[b.stand][1])}</td>
        <td data-t="Bericht">${marke(NACHWEIS[b.bericht.entwaldung][0], NACHWEIS[b.bericht.entwaldung][1])}<span class="ci-unter">${b.bericht.datum ? tag(b.bericht.datum) : ''}</span></td>
        <td data-t="Gegenprüfung">${marke(p[0], p[1])}<span class="ci-unter">${esc(pruefungText(b))}</span></td>
        <td data-t="Container" class="ci-r">${n}</td></tr>`;
    };
    $('#ci-inhalt').innerHTML = suchzeile('Name, Erzeuger, Kennung, Region, Lieferant', 'Farmer')
      + (liste.length
        ? `<div class="r-karte"><table class="ci-tab" id="ci-betriebe"><thead><tr><th scope="col">Farmer</th><th scope="col">Lage</th><th scope="col">Kennung</th><th scope="col" class="ci-r">Fläche</th><th scope="col">Geolokalisierung</th><th scope="col">Bericht Entwaldung</th><th scope="col">Eigene Prüfung</th><th scope="col" class="ci-r">Container</th></tr></thead><tbody>${liste.map(zeile).join('')}</tbody></table></div>`
        : `<div class="r-karte"><p class="ci-leer">${S.d.betriebe.length ? 'Kein Farmer passt zur Suche.' : 'Noch kein Farmer. Über „Unterlagen einlesen“ kommen Berichte und GeoJSON-Dateien der Lieferanten herein.'}</p></div>`)
      + archivSchalter();
  }

  function karteSicht() {
    const s = S.karteSendung ? sendung(S.karteSendung) : null;
    const liste = S.d.betriebe.filter((b) => b.aktiv && (!s || s.betriebe.includes(b.id)));
    const wahl = [['', 'Alle Farmer'], ...S.d.sendungen.filter((x) => x.aktiv).map((x) => [x.id, `Container ${x.name}`])];
    $('#ci-inhalt').innerHTML = `<div class="ci-suchzeile"><select id="ci-karte-sendung" aria-label="Farmer eines Containers zeigen">${wahl.map(([v, t]) => `<option value="${esc(v)}"${v === S.karteSendung ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>
      <span class="ci-legende"><i class="ci-ampel gruen"></i>ohne offenen Punkt <i class="ci-ampel gelb"></i>Nachweis offen <i class="ci-ampel rot"></i>kritisch</span></div>
      <div class="ci-kartenraster"><div class="r-karte" id="ci-karte"></div>
      <ul class="r-karte ci-kartenliste">${liste.map((b) => `<li><button type="button" data-betrieb="${esc(b.id)}"><i class="ci-ampel ${b.ampel}" aria-hidden="true"></i><span><strong>${esc(b.name)}</strong><small>${esc([landName(b.land), b.region].filter(Boolean).join(' · '))} · ${ha(b.flaeche)}</small></span></button></li>`).join('') || '<li class="ci-leer">Keine Farmer.</li>'}</ul></div>
      <p class="ci-leise ci-klein">Grün: Wald Ende 2020 laut Karte der EU-Kommission (JRC) – ein Hinweis, kein Nachweis. Pink: Waldverlust seit 2021 (Universität Maryland über Global Forest Watch, 30 m). Pink innerhalb einer Fläche heißt: genau hinsehen und die Gegenprüfung machen. Das Satellitenbild ist von 2016 und zeigt nicht den heutigen Zustand. Die Bilder kommen direkt von EOX, der EU-Kommission und Global Forest Watch.</p>`;
    window.EUDR_KARTE.zeichnen($('#ci-karte'), { betriebe: liste, beiKlick: betriebOeffnen });
  }

  /* ---------- Fenster „Farmer“ ---------- */
  function betriebOeffnen(id) {
    const b = betrieb(id);
    if (!b) return;
    const darf = S.d.rechte.bearbeiten, aus = !darf;
    const nachweisWahl = Object.entries(NACHWEIS).map(([k, v]) => [k, v[0]]);
    const befunde = b.befunde.length
      ? `<ul class="ci-befunde">${b.befunde.map((f) => `<li class="${f.stufe}">${icon(f.stufe === 'fehler' ? 'warn' : 'info')}<span>${esc(f.text)}</span></li>`).join('')}</ul>`
      : `<p class="ci-meldung ok">${icon('haken')} Der Umriss erfüllt die Regeln des EU-Informationssystems.</p>`;
    const pruefungen = [...(b.pruefungen || [])].sort((x, y) => y.datum.localeCompare(x.datum));
    const portale = Object.entries(S.d.portale);
    $('#betrieb-inhalt').dataset.id = id;
    $('#betrieb-inhalt').innerHTML = kopf('betrieb-titel', b.name, `${esc(landName(b.land))}${b.kennung ? ` · Kennung ${esc(b.kennung)}` : ''} · ${ha(b.flaeche)} · ${plural(b.punkte, 'Punkt', 'Punkte')}`)
      + `<div class="dlg-body">
        <div class="ci-zweispaltig"><div>
          <div class="ci-k-wrap" id="betrieb-karte"></div>
          <p class="ci-klein ci-leise">Mittelpunkt ${b.mitte[1].toLocaleString('de-DE', { maximumFractionDigits: 5 })}° / ${b.mitte[0].toLocaleString('de-DE', { maximumFractionDigits: 5 })}° ·
            <a href="https://www.openstreetmap.org/?mlat=${b.mitte[1]}&amp;mlon=${b.mitte[0]}#map=12/${b.mitte[1]}/${b.mitte[0]}" target="_blank" rel="noopener noreferrer">In OpenStreetMap ansehen</a></p>
          <h3 class="ci-h">Prüfung der Geolokalisierung</h3>${befunde}
        </div><div class="ci-raster">
          ${feld('Name des Farmers', 'name', b.name, { breit: true, aus })}
          ${feld('Erzeuger (Eigentümer)', 'erzeuger', b.erzeuger, { breit: true, aus })}
          ${feld('Land', 'land', b.land, { wahl: laenderWahl(b.land), aus })}${feld('Kennung', 'kennung', b.kennung, { aus, hinweis: 'z. B. SIGOR-Nummer' })}
          ${feld('Region', 'region', b.region, { aus })}${feld('Ort', 'ort', b.ort, { aus })}
          ${feld('Angegebene Fläche (ha)', 'flaecheAngabe', zahlText(b.flaecheAngabe), { zahl: true, aus })}
          <div class="ci-feld"><span>Berechnete Fläche</span><output>${ha(b.geometrie.type === 'Point' ? null : b.flaeche)}</output></div>
        </div></div>

        <h3 class="ci-h">Bericht des Lieferanten</h3>
        <div class="ci-raster drei">
          ${feld('Datum der Analyse', 'b_datum', b.bericht.datum, { typ: 'date', aus })}
          ${feld('Entwaldung seit 31.12.2020', 'b_entwaldung', b.bericht.entwaldung, { wahl: nachweisWahl, aus })}
          ${feld('Entwaldete Fläche (ha)', 'b_entwaldungHa', zahlText(b.bericht.entwaldungHa), { zahl: true, aus })}
          ${feld('Schutzgebiete', 'b_schutzgebiet', b.bericht.schutzgebiet, { wahl: nachweisWahl, aus })}
          ${feld('Indigene Gebiete', 'b_indigen', b.bericht.indigen, { wahl: nachweisWahl, aus })}
          ${feld('Satellitenbilder bis (Jahr)', 'b_bilderBis', b.bericht.bilderBis ?? '', { zahl: true, aus })}
          ${feld('Landnutzungsplan', 'b_landnutzung', b.bericht.landnutzung, { wahl: nachweisWahl, aus })}
          ${feld('Umweltgenehmigung', 'b_umwelt', b.bericht.umwelt, { wahl: nachweisWahl, aus })}
        </div>
        <p class="ci-klein ci-leise">Quelle: ${esc({ bericht: 'Entwaldungsbericht', geojson: 'GeoJSON des Lieferanten', koordinaten: 'eingefügte Koordinaten' }[b.quelle.art])}${b.quelle.datei ? ` „${esc(b.quelle.datei)}“` : ''}${b.quelle.anbieter ? ` · ${esc(b.quelle.anbieter)}` : ''}${b.quelle.lieferant ? ` · von ${esc(b.quelle.lieferant)}` : ''}${b.quelle.bezug ? ` · Bezugssystem ${esc(b.quelle.bezug)}` : ''} · eingelesen ${tag(b.erstellt.t)} von ${esc(b.erstellt.von)}${b.quelle.sha256 ? ` · Prüfsumme <span class="ci-zahlen" title="SHA-256 der Datei: ${esc(b.quelle.sha256)}">${esc(b.quelle.sha256.slice(0, 12))}…</span> · ${b.quelle.qm ? `Original im QM-System, Eingang, Ordner „${esc(b.quelle.qm.pfad)}“` : 'Original nicht im QM-System abgelegt'}` : ''}</p>

        <h3 class="ci-h">Eigene Gegenprüfung der Entwaldung</h3>
        <p class="ci-klein">Unabhängig vom Bericht des Lieferanten: Fläche herunterladen, im Portal hochladen und das Ergebnis hier eintragen.</p>
        <div class="ci-auswertung" id="betrieb-auswertung" hidden></div>
        <div class="ci-portale"><button class="ci-knopf klein" type="button" data-export-betrieb="${esc(id)}">${icon('runter')}Fläche als GeoJSON</button>
          ${portale.filter(([, p]) => p.url).map(([, p]) => `<a class="ci-knopf klein" href="${esc(p.url)}" target="_blank" rel="noopener noreferrer" title="${esc(p.hinweis)}">${icon('aus')}${esc(p.name)}</a>`).join('')}
          ${S.d.rechte.whisp && b.geometrie.type !== 'Point' ? '<button class="ci-knopf klein" type="button" id="betrieb-whisp" title="Schickt den Umriss (ohne Namen) an Whisp und zeigt das Ergebnis hier">In Whisp prüfen</button>' : ''}</div>
        <div class="ci-auswertung" id="betrieb-whisp-ergebnis" hidden></div>
        ${pruefungen.length ? `<ul class="ci-pruefungen">${pruefungen.map((p) => `<li>${befundMarke(p.ergebnis)}<span><strong>${esc(S.d.portale[p.portal].name)}</strong> · ${tag(p.datum)}${p.verlustHa === null ? '' : ` · Baumverlust ${ha(p.verlustHa)}`}${p.bemerkung ? `<small>${esc(p.bemerkung)}</small>` : ''}</span><span class="ci-leise ci-klein">${esc(p.von)}</span></li>`).join('')}</ul>` : '<p class="ci-leise ci-klein">Noch keine Gegenprüfung eingetragen.</p>'}
        ${darf ? `<div class="ci-raster drei ci-neu-pruefung">
          ${feld('Portal', 'p_portal', 'gnw', { wahl: portale.map(([k, p]) => [k, p.name]) })}
          ${feld('Geprüft am', 'p_datum', S.d.heute, { typ: 'date' })}
          ${feld('Ergebnis', 'p_ergebnis', 'ohne_befund', { wahl: [['ohne_befund', 'ohne Befund'], ['befund', 'Befund: Baumverlust oder Warnmeldung']] })}
          ${feld('Baumverlust seit 2021 (ha)', 'p_verlustHa', '', { zahl: true })}
          ${feld('Bemerkung', 'p_bemerkung', '', { breit: true })}
          <div class="ci-feld ci-unten"><button class="ci-knopf" type="button" id="betrieb-pruefung">${icon('plus')}Gegenprüfung eintragen</button></div>
        </div>` : ''}
        ${feld('Notiz', 'notiz', b.notiz, { lang: 2, breit: true, aus })}
      </div>
      <div class="dlg-foot">${darf ? `<button class="ci-knopf" type="button" id="betrieb-archiv">${b.aktiv ? 'Archivieren' : 'Wiederherstellen'}</button>` : ''}<span class="spacer"></span>
        <button class="ci-knopf" type="button" data-zu>Schließen</button>${darf ? '<button class="ci-knopf primaer" type="submit">Speichern</button>' : ''}</div>`;
    oeffnen($('#dlg-betrieb'));
    window.EUDR_KARTE.zeichnen($('#betrieb-karte'), { betriebe: [b], einzeln: true });
    auswertungZeigen(b, darf);
  }
  const WALD_AB_HA = 0.5;   // ab so viel Verlust auf Wald von 2020 schlägt die Bildauswertung „Befund“ vor (Mindestgröße eines Waldes nach der EUDR)
  /* Bildauswertung im Fenster „Farmer“: Wald Ende 2020 und Waldverlust seit 2021 in der Fläche – eine Schätzung aus den
     Kartenbildern (eudr-auswertung.js). Ohne erreichbare Kartendienste oder für einen Punkt bleibt der Abschnitt verborgen.
     „Übernehmen“ füllt nur das Formular der Gegenprüfung; eingetragen wird erst mit dessen Knopf. */
  async function auswertungZeigen(b, darf) {
    const el = $('#betrieb-auswertung');
    let e;
    try { e = await window.EUDR_KARTE.auswerten(b.geometrie); } catch (f) { e = { fehler: true }; }
    if (!el.isConnected || !e) return;   // Fenster inzwischen neu aufgebaut oder Dienste nicht erreichbar
    el.hidden = false;
    if (e.fehler || e.zuGross) {
      el.innerHTML = `<p class="ci-klein ci-leise">Bildauswertung nicht möglich: ${e.fehler ? 'ein Kartendienst hat nicht geantwortet.' : 'die Fläche ist dafür zu groß (mehr als rund 35 × 35 km).'}</p>`;
      return;
    }
    const h = (v) => `${F.zahl(v, 1, 1)} ha`, jahre = Object.entries(e.jahre).filter(([, v]) => v >= 0.05);
    const passt = Math.abs(e.flaecheHa - b.flaeche) <= 0.03 * b.flaeche;
    const befund = e.verlustAufWaldHa >= WALD_AB_HA;
    el.dataset.verlust = befund ? e.verlustHa.toFixed(2) : ''; el.dataset.ergebnis = befund ? 'befund' : 'ohne_befund';
    el.dataset.text = `Bildauswertung im Container-Import: Wald Ende 2020 ${h(e.waldHa)}, Waldverlust 2021–${e.bis} ${h(e.verlustHa)}, davon ${h(e.verlustAufWaldHa)} auf Wald von 2020 (JRC GFC 2020, GFW Tree cover loss).`;
    el.innerHTML = `<p><strong>Bildauswertung der Fläche</strong> <span class="ci-leise">· Schätzung aus den Kartenbildern, kein Nachweis</span></p>
      <dl><dt>Wald Ende 2020 (Karte der EU)</dt><dd>${h(e.waldHa)} · ${F.zahl(e.flaecheHa ? e.waldHa / e.flaecheHa * 100 : 0, 0, 0)} % der Fläche</dd>
        <dt>Waldverlust 2021–${e.bis}</dt><dd>${e.verlustHa >= 0.05 ? `${marke(h(e.verlustHa), befund ? 'rot' : 'warn')} davon ${h(e.verlustAufWaldHa)} auf Wald von 2020${jahre.length ? ` <small>${jahre.map(([j, v]) => `${j}: ${F.zahl(v, 1, 1)}`).join(' · ')}</small>` : ''}` : marke('keiner erkannt', 'ok')}</dd>
        <dt>Verlust bis 2020 (vor dem Stichtag)</dt><dd>${h(e.vorherHa)}</dd></dl>
      <p class="ci-klein ci-leise">Ausgewertet ${h(e.flaecheHa)} (berechnete Fläche ${ha(b.flaeche)})${passt ? '' : ' – <strong>weicht ab, Ergebnis mit Vorsicht lesen</strong>'}. Quellen: Wald 2020 der EU-Kommission (JRC, 10 m), Baumverlust der Universität Maryland über Global Forest Watch (30 m). Baumverlust ist nicht immer Entwaldung (Brand, Ernte von Plantagen); kleine Werte können Rauschen sein.</p>
      ${darf ? '<button class="ci-knopf klein" type="button" id="betrieb-auswertung-nehmen">Werte in die Gegenprüfung übernehmen</button>' : ''}`;
  }
  /* Vorschlag (Bildauswertung oder Whisp) in das Formular der Gegenprüfung schreiben; der Bearbeiter entscheidet und trägt
     selbst ein. dataset: ergebnis ('' = kein Vorschlag: die Auswahl wird leer, damit nicht still „ohne Befund“ gespeichert wird), verlust (nur mit Befund gefüllt: der Server wertet
     jede Zahl über 0 im Feld „Baumverlust“ als kritisch, eudr_betrieb_bewertung – die Zahlen stehen in der Bemerkung), text. */
  function vorschlagNehmen(d, portal) {
    const w = $('#betrieb-inhalt').elements;
    w.p_portal.value = portal;
    w.p_ergebnis.value = d.ergebnis;
    w.p_verlustHa.value = zahlText(d.verlust); w.p_bemerkung.value = d.text;
    w.p_bemerkung.focus();
  }
  const befundMarke = (ergebnis) => marke(ergebnis === 'befund' ? 'Befund' : 'ohne Befund', ergebnis === 'befund' ? 'rot' : 'ok');
  const WHISP_PAUSE = 3000, WHISP_VERSUCHE = 100, WHISP_FEHLVERSUCHE = 3;   // alle drei Sekunden nachfragen, höchstens fünf Minuten; so viele Aussetzer in Folge sind erlaubt
  /* Whisp für den geöffneten Betrieb abfragen (Server: containerimport_eudr_whisp). Die Auswertung läuft bei Whisp; die Seite
     fragt nach, bis sie fertig ist – solange das Fenster offen ist. Ein einzelner Aussetzer (Netz, Drosselung) verwirft den
     Vorgang nicht. Die Vorgangsnummer geht per POST (nicht in die Adresse: mit ihr lässt sich das Ergebnis bei Whisp ohne
     Anmeldung abrufen) – deshalb ohne die Eingabesperre von api(). */
  async function whispPruefen() {
    const el = $('#betrieb-whisp-ergebnis'), knopf = $('#betrieb-whisp'), b = betrieb($('#betrieb-inhalt').dataset.id);
    const warte = (prozent) => { el.innerHTML = `<p class="ci-klein ci-leise" role="status">Whisp wertet die Fläche aus${prozent ? ` (${prozent} %)` : ''} … Das dauert meist unter einer Minute.</p>`; };
    const offen = () => el.isConnected && $('#dlg-betrieb').open;   // Fenster weder neu aufgebaut noch geschlossen
    knopf.disabled = true; el.hidden = false; warte();
    let r = await api('containerimport_eudr_whisp', { id: b.id }, '', false);
    const token = r.data.token;
    for (let n = 0, fehl = 0; r.status === 200 && !r.data.fertig && n < WHISP_VERSUCHE && offen(); n++) {
      warte(r.data.prozent);
      await new Promise((weiter) => setTimeout(weiter, WHISP_PAUSE));
      const s = await api('containerimport_eudr_whisp', { token }, '', false);
      if (s.status === 200) { r = s; fehl = 0; } else if (++fehl >= WHISP_FEHLVERSUCHE) r = s;
    }
    if (!el.isConnected) return;
    knopf.disabled = false;
    if (r.status === 200 && r.data.fertig) whispZeigen(el, r.data.ergebnis, b);
    else if (!offen()) el.hidden = true;   // geschlossen: beim nächsten Öffnen ist das Fenster ohnehin neu
    else el.innerHTML = `<p class="ci-klein"><strong>Whisp:</strong> ${esc(r.status === 200 ? 'Die Auswertung dauert ungewöhnlich lange. Bitte später erneut versuchen.' : fehlerText(r, 'Abfrage nicht möglich. Bitte später erneut versuchen.'))}</p>`;
  }
  /* Ergebnis von Whisp als Vorschlag zeigen (Deutung: eudr-whisp.js); „Übernehmen“ füllt nur das Formular */
  function whispZeigen(el, ergebnis, b) {
    const e = window.EUDR_WHISP.deuten(ergebnis, WALD_AB_HA);
    const passt = e.flaeche === null || Math.abs(e.flaeche - b.flaeche) <= 0.03 * b.flaeche;
    const jaNein = (v, farbeBeiJa) => (v === null ? marke('unbekannt') : marke(v ? 'ja' : 'nein', v ? farbeBeiJa : 'ok'));
    const wert = (v) => `${F.zahl(v, 1, 1)} ${esc(e.einheit)}`;
    el.dataset.ergebnis = e.vorschlag || ''; el.dataset.verlust = e.verlustHa === null ? '' : e.verlustHa.toFixed(2); el.dataset.text = e.text;
    el.innerHTML = `<p><strong>Ergebnis von Whisp</strong> <span class="ci-leise">· Auswertung der FAO aus öffentlichen Karten, kein Nachweis</span></p>
      <dl><dt>Baumbestand Ende 2020</dt><dd>${jaNein(e.wald, 'ok')}</dd>
        <dt>Störung vor 2020</dt><dd>${jaNein(e.vorher, 'ok')}</dd>
        <dt>Störung nach 2020</dt><dd>${jaNein(e.nachher, 'rot')}${e.stoerungen.length ? ` <small>${e.stoerungen.slice(0, 6).map(([k, v]) => `${esc(k)}: ${wert(v)}`).join(' · ')}</small>` : ''}</dd>
        ${e.risiken.length ? `<dt>Risiko laut Whisp</dt><dd>${e.risiken.map(([k, v]) => `${esc(k)}: ${esc(v)}`).join(' · ')}</dd>` : ''}
        <dt>Vorschlag</dt><dd>${e.vorschlag ? befundMarke(e.vorschlag) : `${marke('kein Vorschlag', 'warn')} bitte selbst beurteilen`}</dd></dl>
      <p class="ci-klein ci-leise">${e.flaeche === null ? '' : `Ausgewertet ${wert(e.flaeche)}${e.land ? ` in ${esc(e.land)}` : ''} (berechnete Fläche ${ha(b.flaeche)})${passt ? '' : ' – <strong>weicht ab, Ergebnis mit Vorsicht lesen</strong>'}. `}„Ja“ heißt bei Whisp: mehr als rund 10 % der Fläche (Störung vor 2020: mehr als die Hälfte). ${e.rind ? '' : 'Für Rinder gibt Whisp kein eigenes Risiko aus; der Vorschlag folgt der Regel für Ackerkulturen. '}Störungen sind auch Brand und Ernte.</p>
      <button class="ci-knopf klein" type="button" id="betrieb-whisp-nehmen">Werte in die Gegenprüfung übernehmen</button>`;
  }
  /* Felder des Fensters als Betrieb für den Server */
  function betriebAusFenster(b, w) {
    const jahr = Number(w.b_bilderBis);
    return {
      id: b.id, rev: b.rev, name: w.name, erzeuger: w.erzeuger, land: w.land, kennung: w.kennung, region: w.region, ort: w.ort, flaecheAngabe: w.flaecheAngabe, notiz: w.notiz, quelle: b.quelle,
      bericht: { datum: w.b_datum, entwaldung: w.b_entwaldung, entwaldungHa: w.b_entwaldungHa, schutzgebiet: w.b_schutzgebiet, indigen: w.b_indigen, landnutzung: w.b_landnutzung, umwelt: w.b_umwelt, bilderBis: Number.isInteger(jahr) && jahr > 0 ? jahr : null },
    };
  }
  async function betriebSpeichern(zusatz = {}) {
    const id = $('#betrieb-inhalt').dataset.id, b = betrieb(id);
    const r = await api('containerimport_eudr_betriebe_save', { betriebe: [{ ...betriebAusFenster(b, werte($('#betrieb-inhalt'))), ...zusatz }] });
    if (!uebernehmen(r, 'Der Farmer konnte nicht gespeichert werden')) return;
    toast('Farmer gespeichert.');
    betriebOeffnen(id);
  }
  async function pruefungEintragen() {
    const id = $('#betrieb-inhalt').dataset.id, w = werte($('#betrieb-inhalt'));
    if (!w.p_ergebnis) { toast('Bitte das Ergebnis wählen – dafür gab es keinen Vorschlag.', true); $('#betrieb-inhalt').elements.p_ergebnis.focus(); return; }
    const r = await api('containerimport_eudr_gegenpruefung', { id, portal: w.p_portal, datum: w.p_datum, ergebnis: w.p_ergebnis, verlustHa: w.p_verlustHa, bemerkung: w.p_bemerkung });
    if (!uebernehmen(r, 'Die Gegenprüfung konnte nicht eingetragen werden')) return;
    toast('Gegenprüfung eingetragen.');
    betriebOeffnen(id);
  }

  /* ---------- Fenster „Container“ ---------- */
  const kriterien = (p) => `<ul class="ci-kriterien">${p.kriterien.map((k) => `<li class="${k.stand}"><span class="ci-kr-stand">${marke(STAND[k.stand][0], STAND[k.stand][1])}</span>
    <span><strong>${esc(k.titel)}</strong><small>${esc(k.text)}${k.betriebe.length ? ` <em>${esc(k.betriebe.join(', '))}</em>` : ''}</small></span></li>`).join('')}</ul>`;
  function sendungOeffnen(id) {
    const neu = !id;
    const s = neu ? { id: '', rev: 0, partie: '', akte: '', container: '', stand: 'gekauft', nummer: '', lieferant: '', lieferantNr: '', land: 'PY', ware: '', hs: '', mengeKg: null, schlachtVon: '', schlachtBis: '', lose: '', betriebe: [],
      nachweis: { erklaerung: '', rueckverfolgung: 'offen', haltung: 'offen', legalitaet: 'offen' }, dds: { referenz: '', datum: '' }, notiz: '', aktiv: true, abschluss: null } : sendung(id);
    if (!s) return;
    const darf = S.d.rechte.bearbeiten, zu = !!s.abschluss, aus = !darf || zu;
    const nachtragbar = (wert) => aus && !(darf && wert === '');   // gesperrt – außer es fehlt noch: dann einmal nachtragen (eudr_sendung_nachtrag)
    const waehlbar = S.d.betriebe.filter((b) => b.aktiv || s.betriebe.includes(b.id)).sort((a, b) => a.name.localeCompare(b.name, 'de'));
    const gezeigt = zu ? s.abschluss.betriebe : waehlbar;
    const betriebe = gezeigt.length
      ? `<ul class="ci-wahl">${gezeigt.map((b) => `<li><label><input type="checkbox" name="betriebe" data-liste value="${esc(b.id)}"${zu || s.betriebe.includes(b.id) ? ' checked' : ''}${aus ? ' disabled' : ''}>
          <span><strong>${esc(b.name)}</strong><small>${esc([b.erzeuger, landName(b.land), b.region].filter(Boolean).join(' · '))} · ${ha(b.flaeche)}</small></span></label>${marke(GEO[b.stand][0], GEO[b.stand][1])}</li>`).join('')}</ul>`
      : '<p class="ci-leise ci-klein">Noch keine Farmer vorhanden – zuerst die Unterlagen des Lieferanten einlesen.</p>';
    const hofWahl = zu && s.schlachthof ? [[s.schlachthof, s.schlachthofName]] : schlachthofWahl(s, s.schlachthof);   // nach dem Abschluss der Name von damals
    const abschluss = zu ? `<div class="ci-abschluss">${marke(ERGEBNIS[s.abschluss.ergebnis][0], ERGEBNIS[s.abschluss.ergebnis][1])}<span>Bewertung abgeschlossen am ${tag(s.abschluss.wer.t)} von ${esc(s.abschluss.wer.von)}${s.abschluss.begruendung ? `<small>${esc(s.abschluss.begruendung)}</small>` : ''}</span></div>` : '';
    $('#sendung-inhalt').dataset.id = s.id;
    $('#sendung-inhalt').innerHTML = kopf('sendung-titel', neu ? 'Neuer Container' : `Container ${s.name}`, neu ? '' : `${esc(s.lieferant)} · ${esc(landName(s.land))}`)
      + `<div class="dlg-body">${abschluss}
        <div class="ci-raster drei">
          ${feld('Partienummer', 'partie', s.partie, { aus: nachtragbar(s.partie), platz: 'interne Referenz des Einkaufs' })}${feld('Aktennummer', 'akte', s.akte, { aus: !darf })}${feld('Containernummer', 'container', s.container, { aus: !darf, platz: 'z. B. MSKU 907032 3', hinweis: HINWEIS_NUMMER[s.containerPruefung] })}
          ${lieferantFeld(s, aus, neu, 'ci-lieferanten')}${feld('Schlachthof', 'schlachthof', s.schlachthof, { wahl: hofWahl, aus: nachtragbar(s.schlachthof) })}${feld('Herkunftsland', 'land', s.land, { wahl: laenderWahl(s.land), aus })}
          ${feld('Stand', 'stand', s.stand, { wahl: Object.entries(S.d.staende), aus: !darf })}${feld('Ware', 'ware', s.ware, { aus, platz: 'z. B. Rindfleisch, gekühlt, ohne Knochen' })}${feld('Zolltarifnummer', 'hs', s.hs, { aus, platz: 'z. B. 0201' })}
          ${feld('Menge netto (kg)', 'mengeKg', zahlText(s.mengeKg), { zahl: true, aus })}${feld('Schlachtung von', 'schlachtVon', s.schlachtVon, { typ: 'date', aus })}${feld('Schlachtung bis', 'schlachtBis', s.schlachtBis, { typ: 'date', aus })}
          ${feld('Auftragsnummer des Lieferanten', 'nummer', s.nummer, { aus, platz: 'z. B. FB26-001' })}
          ${feld('Schlachtlose', 'lose', s.lose, { aus, zwei: true, platz: 'z. B. 2101, 2102, 2103' })}
        </div>

        <h3 class="ci-h">Farmer dieses Containers</h3>${betriebe}
        ${!neu && gezeigt.some((b) => s.betriebe.includes(b.id)) ? '<div class="ci-k-wrap flach" id="sendung-karte"></div>' : ''}

        <h3 class="ci-h">Nachweise des Lieferanten</h3>
        <div class="ci-raster">
          ${feld('Erklärung des Lieferanten zur EUDR vom', 'n_erklaerung', s.nachweis.erklaerung, { typ: 'date', aus })}
          ${feld('Zuordnung Schlachtlos → Farmer belegt?', 'n_rueckverfolgung', s.nachweis.rueckverfolgung, { wahl: DREI, aus })}
          ${feld('Alle Haltungsbetriebe erfasst (Geburt, Aufzucht, Mast)?', 'n_haltung', s.nachweis.haltung, { wahl: DREI, aus })}
          ${feld('Nachweise zur Legalität liegen vor (Landtitel, Genehmigungen)?', 'n_legalitaet', s.nachweis.legalitaet, { wahl: DREI, aus })}
        </div>

        ${neu ? '' : `<h3 class="ci-h">Risikoprofil ${zu ? '<span class="ci-leise">· Stand beim Abschluss</span>' : '<span class="ci-leise">· Stand der gespeicherten Angaben</span>'}</h3>
        <p class="ci-vorschlag ${s.profil.stand}">${icon(s.profil.stand === 'ok' ? 'haken' : 'warn')}<span>${esc(s.profil.vorschlag)}</span></p>${kriterien(s.profil)}
        <p class="ci-klein ci-leise">Einstufung der Länder nach ${esc(s.profil.laenderStand)}.</p>`}

        <h3 class="ci-h">Sorgfaltserklärung im EU-Informationssystem (TRACES)</h3>
        <div class="ci-raster">${feld('Referenznummer', 'd_referenz', s.dds.referenz, { aus: !darf })}${feld('Abgegeben am', 'd_datum', s.dds.datum, { typ: 'date', aus: !darf })}</div>
        ${feld('Notiz', 'notiz', s.notiz, { lang: 2, breit: true, aus: !darf })}
      </div>
      <div class="dlg-foot">${neu ? '' : `<button class="ci-knopf" type="button" data-export-sendung="${esc(s.id)}">${icon('runter')}GeoJSON für TRACES</button><button class="ci-knopf" type="button" id="sendung-druck" title="Risikoprofil drucken">${icon('druck')}Drucken</button>`}
        <span class="spacer"></span>
        ${darf && !neu ? (zu ? '<button class="ci-knopf" type="button" id="sendung-oeffnen">Bewertung wieder öffnen</button>' : `<button class="ci-knopf" type="button" id="sendung-archiv">${s.aktiv ? 'Archivieren' : 'Wiederherstellen'}</button><button class="ci-knopf" type="button" id="sendung-abschliessen">Bewertung abschließen</button>`) : ''}
        <button class="ci-knopf" type="button" data-zu>Schließen</button>${darf ? '<button class="ci-knopf primaer" type="submit">Speichern</button>' : ''}</div>`;
    oeffnen($('#dlg-sendung'));
    const karte = $('#sendung-karte');
    if (karte) window.EUDR_KARTE.zeichnen(karte, { betriebe: gezeigt.filter((b) => s.betriebe.includes(b.id)) });
  }
  function sendungAusFenster() {
    const f = $('#sendung-inhalt'), w = werte(f), alt = sendung(f.dataset.id);
    return {
      id: f.dataset.id, rev: alt ? alt.rev : 0, aktiv: alt ? alt.aktiv : true, partie: w.partie, akte: w.akte, container: w.container, stand: w.stand, nummer: w.nummer,
      ...lieferantAus(w.lieferant, alt), schlachthof: w.schlachthof, land: w.land, ware: w.ware, hs: w.hs, mengeKg: w.mengeKg,
      schlachtVon: w.schlachtVon, schlachtBis: w.schlachtBis, lose: w.lose, betriebe: w.betriebe || [], notiz: w.notiz,
      nachweis: { erklaerung: w.n_erklaerung, rueckverfolgung: w.n_rueckverfolgung, haltung: w.n_haltung, legalitaet: w.n_legalitaet }, dds: { referenz: w.d_referenz, datum: w.d_datum },
    };
  }
  /* Lieferant im Fenster geändert: zur Wahl stehen nur seine Schlachthöfe; der gewählte bleibt, wenn er dazugehört */
  function schlachthofWahlNeu() {
    const f = $('#sendung-inhalt'), sel = $('[name=schlachthof]', f), vorher = sel.value, alt = sendung(f.dataset.id);
    const lieferant = lieferantAus($('[name=lieferant]', f).value.trim(), alt), gespeichert = alt && S.d.schlachthoefe.find((x) => x.id === alt.schlachthof);
    // der gespeicherte Schlachthof bleibt wählbar (auch archiviert), solange der Lieferant wieder seiner ist
    const aktuell = gespeichert && lieferantSchluessel(gespeichert) === lieferantSchluessel(lieferant) ? gespeichert.id : '';
    sel.innerHTML = schlachthofWahl(lieferant, aktuell).map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join('');
    // die Wahl bleibt, wenn sie zum Lieferanten gehört; eine dadurch verdrängte Wahl kommt zurück, sobald er wieder ihrer ist
    const wunsch = vorher || sel.dataset.verdraengt || '';
    sel.value = [...sel.options].some((o) => o.value === wunsch) ? wunsch : '';
    sel.dataset.verdraengt = sel.value ? '' : wunsch;
  }
  async function sendungSpeichern(zusatz = {}) {
    const r = await api('containerimport_eudr_sendung_save', { ...sendungAusFenster(), ...zusatz });
    if (!uebernehmen(r, 'Der Container konnte nicht gespeichert werden')) return false;
    toast('Container gespeichert.');
    sendungOeffnen(r.data.id);
    return true;
  }

  /* Fenster „Bewertung abschließen“ bzw. „wieder öffnen“ */
  function abschlussOeffnen(id, wiederOeffnen) {
    const s = sendung(id), p = s.profil;
    $('#abschluss-inhalt').dataset.id = id;
    $('#abschluss-inhalt').dataset.art = wiederOeffnen ? 'oeffnen' : 'abschluss';
    $('#abschluss-inhalt').innerHTML = wiederOeffnen
      ? kopf('abschluss-titel', 'Bewertung wieder öffnen', `Container ${esc(s.name)}`) + `<div class="dlg-body">${feld('Grund', 'grund', '', { lang: 3, breit: true, hinweis: 'Der bisherige Abschluss bleibt im Verlauf des Containers erhalten.' })}</div>
        <div class="dlg-foot"><button class="ci-knopf" type="button" data-zu>Abbrechen</button><button class="ci-knopf primaer" type="submit">Wieder öffnen</button></div>`
      : kopf('abschluss-titel', 'Bewertung abschließen', `Container ${esc(s.name)}`) + `<div class="dlg-body">
        <p class="ci-vorschlag ${p.stand}">${icon(p.stand === 'ok' ? 'haken' : 'warn')}<span>${esc(p.vorschlag)}</span></p>
        ${feld('Ergebnis der Risikobewertung', 'ergebnis', p.vernachlaessigbar === 'ja' ? 'vernachlaessigbar' : 'nicht_vernachlaessigbar', { breit: true, wahl: [
          ...(p.vernachlaessigbar === 'nein' ? [] : [['vernachlaessigbar', 'Risiko vernachlässigbar – Sorgfaltserklärung wird abgegeben']]), ['nicht_vernachlaessigbar', 'Risiko nicht vernachlässigbar – Ware wird nicht in Verkehr gebracht']] })}
        ${feld('Begründung', 'begruendung', '', { lang: 4, breit: true, hinweis: { ja: 'Was wurde geprüft, was wurde unternommen?', begruendung: 'Für „vernachlässigbar“ Pflicht, weil noch Punkte offen sind: Warum ist das Risiko trotzdem vernachlässigbar?',
          nein: 'Solange ein Kriterium kritisch ist, kann das Risiko nicht als vernachlässigbar bewertet werden.' }[p.vernachlaessigbar] })}
        <p class="ci-klein ci-leise">Mit dem Abschluss werden Risikoprofil und Farmer so festgehalten, wie sie jetzt sind. Spätere Änderungen an den Farmern ändern diese Bewertung nicht. Stand, Container- und Aktennummer lassen sich weiter pflegen.</p></div>
        <div class="dlg-foot"><button class="ci-knopf" type="button" data-zu>Abbrechen</button><button class="ci-knopf primaer" type="submit">Abschließen</button></div>`;
    oeffnen($('#dlg-abschluss'));
  }
  async function abschlussSenden() {
    const f = $('#abschluss-inhalt'), id = f.dataset.id, w = werte(f), s = sendung(id);
    const r = await api('containerimport_eudr_sendung_abschluss', f.dataset.art === 'oeffnen' ? { id, rev: s.rev, oeffnen: true, grund: w.grund } : { id, rev: s.rev, ergebnis: w.ergebnis, begruendung: w.begruendung });
    if (!uebernehmen(r, 'Die Bewertung konnte nicht gespeichert werden')) return;
    $('#dlg-abschluss').close();
    toast(f.dataset.art === 'oeffnen' ? 'Bewertung wieder geöffnet.' : 'Bewertung abgeschlossen.');
    sendungOeffnen(id);
  }

  /* ---------- GeoJSON-Datei und Druck ---------- */
  async function exportieren(query) {
    const r = await api('containerimport_eudr_export', null, query);
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Die Datei konnte nicht erzeugt werden'), true); return; }
    if (!r.data.geojson.features.length) { toast('Keine einreichbare Fläche – bitte zuerst die Fehler der Geolokalisierung klären.', true); return; }
    const a = document.createElement('a');
    a.href = URL.createObjectURL(new Blob([JSON.stringify(r.data.geojson)], { type: 'application/geo+json' }));
    a.download = r.data.datei;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 10000);
    toast(r.data.ausgelassen.length ? `Datei erzeugt – ohne ${r.data.ausgelassen.join(', ')} (Geolokalisierung fehlerhaft).` : `${r.data.datei} erzeugt.`, r.data.ausgelassen.length > 0);
  }
  function drucken(id) {
    const s = sendung(id), bs = s.abschluss ? s.abschluss.betriebe : S.d.betriebe.filter((b) => s.betriebe.includes(b.id));
    const zeile = (k, v) => (v ? `<tr><th scope="row">${esc(k)}</th><td>${v}</td></tr>` : '');
    $('#ci-druck').innerHTML = `<h1>Risikoprofil EUDR · Container ${esc(s.name)}</h1>
      <p>Verordnung (EU) 2023/1115 · Standard-Fleisch · gedruckt am ${F.datumZeit(new Date())} von ${esc(S.d.name)}</p>
      <table class="ci-d-kopf">${zeile('Partienummer', esc(s.partie))}${zeile('Aktennummer', esc(s.akte))}${zeile('Lieferant', esc(s.lieferant + (s.lieferantNr ? ` (Nr. ${s.lieferantNr})` : '')))}${zeile('Schlachthof', esc(s.schlachthofName))}${zeile('Auftragsnummer des Lieferanten', esc(s.nummer))}${zeile('Herkunftsland', esc(landName(s.land)))}${zeile('Ware', esc([s.ware, s.hs && `Zolltarifnummer ${s.hs}`].filter(Boolean).join(' · ')))}${zeile('Menge', s.mengeKg === null ? '' : F.kg(s.mengeKg))}
        ${zeile('Containernummer', esc(s.container))}${zeile('Schlachtung', s.schlachtVon ? `${tag(s.schlachtVon)}${s.schlachtBis ? ` bis ${tag(s.schlachtBis)}` : ''}` : '')}${zeile('Schlachtlose', esc(s.lose))}${zeile('Sorgfaltserklärung', esc([s.dds.referenz, s.dds.datum && tag(s.dds.datum)].filter(Boolean).join(' · ')))}</table>
      <h2>Farmer</h2>
      <table class="ci-d-tab"><thead><tr><th>Farmer</th><th>Erzeuger</th><th>Lage</th><th>Kennung</th><th>Fläche</th><th>Geolokalisierung</th><th>Bericht</th><th>Eigene Prüfung</th></tr></thead><tbody>
        ${bs.map((b) => `<tr><td>${esc(b.name)}</td><td>${esc(b.erzeuger)}</td><td>${esc([landName(b.land), b.region, b.ort].filter(Boolean).join(', '))}<br>${b.mitte[1]}° / ${b.mitte[0]}°</td><td>${esc(b.kennung)}</td><td>${ha(b.flaeche)}</td><td>${esc(GEO[b.stand][0])}</td><td>${esc(NACHWEIS[b.bericht.entwaldung][0])}${b.bericht.datum ? `, ${tag(b.bericht.datum)}` : ''}</td><td>${esc(PRUEFUNG[b.bewertung.gegenpruefung][0])}${b.pruefungenAktuell.length ? `<br>${esc(pruefungText(b))}` : ''}</td></tr>`).join('') || '<tr><td colspan="8">Keine Farmer zugeordnet.</td></tr>'}</tbody></table>
      <h2>Kriterien</h2>
      <table class="ci-d-tab"><thead><tr><th>Kriterium</th><th>Stand</th><th>Feststellung</th></tr></thead><tbody>${s.profil.kriterien.map((k) => `<tr><td>${esc(k.titel)}</td><td>${esc(STAND[k.stand][0])}</td><td>${esc(k.text)}${k.betriebe.length ? ` (${esc(k.betriebe.join(', '))})` : ''}</td></tr>`).join('')}</tbody></table>
      <h2>Ergebnis</h2>
      <p>${s.abschluss ? `<strong>${esc(ERGEBNIS[s.abschluss.ergebnis][0])}</strong> – abgeschlossen am ${tag(s.abschluss.wer.t)} von ${esc(s.abschluss.wer.von)}.${s.abschluss.begruendung ? `<br>${esc(s.abschluss.begruendung)}` : ''}` : `Bewertung noch nicht abgeschlossen. Vorschlag: ${esc(s.profil.vorschlag)}`}</p>
      <p class="ci-d-fuss">Einstufung der Länder nach ${esc(s.profil.laenderStand)}. Stichtag für Entwaldung: 31.12.2020.</p>`;
    window.print();
  }

  /* ---------- Fenster „Unterlagen einlesen“ ---------- */
  function lesenOeffnen(sendungId = '') {
    S.lesen = null;
    const s = sendungId ? sendung(sendungId) : null;
    const sendungen = [['', '– keinem Container zuordnen –'], ...S.d.sendungen.filter((x) => x.aktiv && !x.abschluss).map((x) => [x.id, `${x.name} · ${x.lieferant}`])];
    $('#lesen-inhalt').innerHTML = kopf('lesen-titel', 'Unterlagen einlesen', 'Entwaldungsberichte (PDF), GeoJSON-Dateien des Lieferanten oder eine Koordinatenliste')
      + `<div class="dlg-body">
        <div class="ci-raster drei">${feld('Herkunftsland', 'land', s ? s.land : 'PY', { wahl: laenderWahl(), hinweis: 'gilt, wenn die Datei kein Land nennt' })}${feld('Lieferant', 'lieferant', s ? s.lieferant : '')}${feld('Container', 'sendung', sendungId, { wahl: sendungen })}</div>
        <label class="ci-ablage" for="lesen-dateien">${icon('hoch')}<span><strong>Dateien auswählen</strong><small>PDF-Berichte liest Ihr Browser, GeoJSON-Dateien prüft der Server. Gespeichert werden Farmer, Umriss, Dateiname und Prüfsumme.</small></span>
          <input type="file" id="lesen-dateien" multiple accept=".pdf,.geojson,.json,application/pdf,application/geo+json,application/json"></label>
        <label class="ci-check"><input type="checkbox" name="qm" checked>Originaldateien beim Übernehmen im QM-System ablegen (Eingang, Ordner „EUDR“)</label>
        <details class="ci-einfuegen"><summary>Stattdessen eine Koordinatenliste einfügen</summary>
          <div class="ci-raster drei">${feld('Name des Farmers', 'k_name', '')}${feld('Bezugssystem', 'k_system', 'wgs84', { wahl: [['wgs84', 'WGS84: Längengrad, Breitengrad'], ['utm', 'UTM: Rechtswert, Hochwert']] })}
            ${feld('UTM-Zone und Halbkugel', 'k_zone', '21S', { platz: 'z. B. 21S', hinweis: 'nur bei UTM' })}</div>
          ${feld('Koordinaten', 'k_text', '', { lang: 4, breit: true, platz: 'je Punkt zwei Zahlen, z. B.  -57.000000, -23.500000', hinweis: 'Dezimalpunkt; Punkte durch Zeilenumbruch oder Komma getrennt' })}</details>
        <div id="lesen-ergebnis" aria-live="polite"></div>
      </div>
      <div class="dlg-foot"><span class="ci-fuss-links" id="lesen-zahl"></span><button class="ci-knopf" type="button" data-zu>Schließen</button>
        <button class="ci-knopf" type="button" id="lesen-pruefen">Prüfen</button><button class="ci-knopf primaer" type="submit" id="lesen-ok" disabled>Übernehmen</button></div>`;
    oeffnen($('#dlg-lesen'));
  }
  const hex = (puffer) => [...new Uint8Array(puffer)].map((b) => b.toString(16).padStart(2, '0')).join('');
  /* Textstücke einer PDF-Datei mit ihrer Lage, je Seite (pdf.js vom eigenen Server, erst beim ersten Bericht geladen) */
  async function pdfSeiten(bytes) {
    const pdfjs = await import(PDFJS + 'pdf.min.js');
    pdfjs.GlobalWorkerOptions.workerSrc = PDFJS + 'pdf.worker.min.js';
    const aufgabe = pdfjs.getDocument({ data: bytes, isEvalSupported: false }), doc = await aufgabe.promise;
    const seiten = [];
    for (let n = 1; n <= doc.numPages; n++) {
      const inhalt = await (await doc.getPage(n)).getTextContent();
      seiten.push(inhalt.items.filter((t) => typeof t.str === 'string').map((t) => ({ s: t.str, x: t.transform[4], y: t.transform[5], w: t.width })));
    }
    await aufgabe.destroy();
    return seiten;
  }
  /* Eine gewählte Datei in die Form bringen, die der Server prüft; { fehler } bei Dateien, die sich nicht lesen lassen */
  async function dateiVorbereiten(datei, gemeinsam) {
    const bytes = await datei.arrayBuffer();
    const kopfdaten = { datei: datei.name, sha256: hex(await crypto.subtle.digest('SHA-256', bytes)), ...gemeinsam };
    if (!/\.pdf$/i.test(datei.name)) return { art: 'geojson', text: new TextDecoder().decode(bytes), ...kopfdaten };
    let gelesen;
    try { gelesen = window.EUDR_BERICHT.lesen(await pdfSeiten(bytes.slice(0))); } catch (e) { console.warn('PDF nicht lesbar:', datei.name, e); return { fehler: `${datei.name}: Die PDF-Datei lässt sich nicht lesen (beschädigt oder mit Kennwort geschützt).` }; }
    if (gelesen && gelesen.fehler) return { fehler: `${datei.name}: ${gelesen.fehler}` };
    if (!gelesen) return { fehler: `${datei.name}: Keine Koordinatenliste gefunden – das ist kein Entwaldungsbericht mit Geolokalisierung (z. B. eine Erklärung oder ein gescanntes Dokument).` };
    return { art: 'bericht', anbieter: gelesen.anbieter, bezug: gelesen.bezug, ort: gelesen.ort, ...kopfdaten };
  }
  function eingefuegt(w, gemeinsam) {
    const zone = /^(\d{1,2})\s*([NS])$/i.exec(w.k_zone);
    return { art: 'koordinaten', datei: '', bezug: w.k_system === 'utm' ? `UTM ${w.k_zone.toUpperCase()}` : 'WGS84', ...gemeinsam,
      ort: { name: w.k_name, koordinaten: { system: w.k_system, zone: zone ? Number(zone[1]) : null, sued: zone ? zone[2].toUpperCase() === 'S' : true, punkte: window.EUDR_BERICHT.punkte(w.k_text) || [] } } };
  }
  async function lesenPruefen() {
    const f = $('#lesen-inhalt'), w = werte(f), knopf = $('#lesen-pruefen');
    const gemeinsam = { land: w.land, lieferant: w.lieferant };
    const dateien = [...$('#lesen-dateien').files];
    if (!dateien.length && !w.k_text) { toast('Bitte Dateien auswählen oder Koordinaten einfügen.', true); return; }
    knopf.disabled = true; knopf.setAttribute('aria-busy', 'true');
    $('#lesen-ergebnis').innerHTML = '<p class="ci-leise">Dateien werden gelesen und geprüft …</p>';
    const vorbereitet = await Promise.all(dateien.map((d) => dateiVorbereiten(d, gemeinsam)));
    if (w.k_text) vorbereitet.push(eingefuegt(w, gemeinsam));
    const lokal = vorbereitet.filter((v) => v.fehler).map((v) => v.fehler), senden = vorbereitet.filter((v) => !v.fehler);
    let ergebnis = [];
    if (senden.length) {
      if (JSON.stringify(senden).length > MAX_ANFRAGE) lokal.push('Die Dateien sind zusammen zu groß (höchstens 3 MB je Durchgang) – bitte in mehreren Schritten einlesen.');
      else {
        const r = await api('containerimport_eudr_pruefen', { dateien: senden });
        if (r.status === 401) { zeigeAnmeldung(); return; }
        if (r.status !== 200 || !r.data.ok) lokal.push(fehlerText(r, 'Die Prüfung ist fehlgeschlagen')); else ergebnis = r.data.dateien;
      }
    }
    knopf.disabled = false; knopf.removeAttribute('aria-busy');
    S.lesen = { sendung: w.sendung, orte: ergebnis.flatMap((d) => d.orte), qm: w.qm, lieferant: w.lieferant,
      originale: new Map(dateien.map((d, i) => [vorbereitet[i].sha256, d]).filter(([sha]) => sha)) };
    const gruppe = (d) => `<section class="ci-datei"><h4>${esc(d.datei || 'Eingefügte Koordinaten')}</h4>
      ${d.fehler.map((t) => `<p class="ci-meldung">${icon('warn')} ${esc(t)}</p>`).join('')}${d.hinweise.map((t) => `<p class="ci-meldung neutral">${icon('info')} ${esc(t)}</p>`).join('')}
      ${d.orte.length ? `<ul class="ci-wahl">${d.orte.map((o) => { const i = S.lesen.orte.indexOf(o); return `<li><label><input type="checkbox" data-ort="${i}" checked>
        <span><strong>${esc(o.name)}</strong><small>${esc([o.erzeuger, landName(o.land), o.region, o.kennung && `Kennung ${o.kennung}`].filter(Boolean).join(' · '))} · ${ha(o.flaeche)}${o.flaecheAngabe ? ` (angegeben ${ha(o.flaecheAngabe)})` : ''} · ${plural(o.punkte, 'Punkt', 'Punkte')}</small>
        ${o.befunde.map((b) => `<small class="ci-befund ${b.stufe}">${esc(b.text)}</small>`).join('')}</span></label>
        <span class="ci-rechts">${marke(GEO[o.stand][0], GEO[o.stand][1])}${marke(o.bekannt ? 'aktualisiert vorhandenen Farmer' : 'neu', o.bekannt ? '' : 'ok')}</span></li>`; }).join('')}</ul>` : ''}</section>`;
    $('#lesen-ergebnis').innerHTML = lokal.map((t) => `<p class="ci-meldung">${icon('warn')} ${esc(t)}</p>`).join('') + ergebnis.map(gruppe).join('');
    lesenZahl();
  }
  function lesenZahl() {
    const n = $$('#lesen-ergebnis [data-ort]:checked').length;
    $('#lesen-ok').disabled = !n || !S.d.rechte.bearbeiten;
    $('#lesen-ok').textContent = n ? `${n} Farmer übernehmen` : 'Übernehmen';
    $('#lesen-zahl').textContent = S.lesen && S.lesen.orte.some((o) => o.stand === 'fehler') ? 'Fehlerhafte Flächen werden mit ihrem Befund gespeichert, aber nicht an TRACES übergeben.' : '';
  }
  async function lesenUebernehmen() {
    if (!S.lesen) { lesenPruefen(); return; }   // Eingabetaste vor dem Prüfen
    const gewaehlt = $$('#lesen-ergebnis [data-ort]:checked').map((el) => S.lesen.orte[Number(el.dataset.ort)]);
    if (!gewaehlt.length) return;
    const r = await api('containerimport_eudr_betriebe_save', { sendung: S.lesen.sendung, betriebe: gewaehlt.map((o) => ({ ...o.eingabe, id: o.bekannt, rev: o.bekanntRev })) });
    if (!uebernehmen(r, 'Die Farmer konnten nicht gespeichert werden')) return;
    const pruefsummen = new Set(gewaehlt.map((o) => o.quelle.sha256));
    const originale = S.lesen.qm ? [...S.lesen.originale].filter(([sha]) => pruefsummen.has(sha)) : [];
    const fehler = [];
    for (const [i, [sha, datei]] of originale.entries()) {
      $('#lesen-zahl').textContent = `Originale werden im QM-System abgelegt … ${i + 1} von ${originale.length}`;
      const meldung = await originalAblegen(datei, sha, S.lesen.lieferant);
      if (meldung) fehler.push(`${datei.name}: ${meldung}`);
    }
    $('#dlg-lesen').close();
    const text = `${gewaehlt.length} Farmer übernommen${S.lesen.sendung ? ' und dem Container zugeordnet' : ''}`;
    if (fehler.length) toast(`${text}. Nicht im QM-System abgelegt – ${fehler.join('; ')}`, true);
    else toast(`${text}${originale.length ? `, ${plural(originale.length, 'Original', 'Originale')} im QM-System abgelegt` : ''}.`);
    if (S.lesen.sendung) sendungOeffnen(S.lesen.sendung); else if (S.sicht === 'sendungen') { S.sicht = 'betriebe'; zeichnen(); } else zeichnen();
  }
  /* Bytes als Base64 (in Stücken, damit lange Dateien den Aufrufstapel nicht sprengen) */
  function base64(bytes) {
    let text = '';
    for (let i = 0; i < bytes.length; i += 0x8000) text += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
    return btoa(text);
  }
  /* Eine Originaldatei in Teilen an den Server geben, der sie im Eingang des QM-Systems ablegt. '' oder die Fehlermeldung.
     Die Ablage kennt „.geojson“ nicht als Dateiart – solche Dateien heißen dort „.json“. */
  async function originalAblegen(datei, sha256, lieferant) {
    const name = datei.name.replace(/\.geojson$/i, '.json');
    let upload = '';
    for (let teil = 0; teil * TEIL < Math.max(datei.size, 1); teil++) {
      const daten = base64(new Uint8Array(await datei.slice(teil * TEIL, (teil + 1) * TEIL).arrayBuffer()));
      const r = await api('containerimport_eudr_original', { upload, teil, daten, name, groesse: datei.size, sha256, lieferant });
      if (r.status !== 200 || !r.data.ok) return fehlerText(r, 'Ablage fehlgeschlagen');
      if (r.data.fertig) { S.d = { ...S.d, ...r.data }; return ''; }
      upload = r.data.upload;
    }
    return 'Die Datei kam nicht vollständig an.';
  }

  /* ---------- Laden und Ereignisse ---------- */
  async function laden(still) {
    const r = await api('containerimport_start');
    if (r.status === 401) { zeigeAnmeldung(); return false; }
    if (r.status !== 200 || !r.data.ok) { if (still) toast(fehlerText(r, 'Der Stand konnte nicht geladen werden'), true); else fehler(fehlerText(r, 'Der Container-Import ist gerade nicht erreichbar')); return false; }
    S.d = r.data;
    $('#ci-login').hidden = true; $('#ci-err').hidden = true; $('#ci-app').hidden = false;
    zeichnen();
    return true;
  }
  const dunkel = () => document.documentElement.getAttribute('data-theme') === 'dark'
    || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  function themaKnopf() {
    const d = dunkel(), b = $('#ci-theme');
    b.innerHTML = icon(d ? 'sun' : 'moon');
    b.setAttribute('aria-label', d ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }

  document.addEventListener('click', (e) => {
    const t = e.target;
    const zu = t.closest('[data-zu]');
    if (zu) { zu.closest('dialog').close(); return; }
    const chip = t.closest('[data-sicht]');
    if (chip) { S.sicht = chip.dataset.sicht; zeichnen(); return; }
    if (t.closest('#ci-neu')) { laden(true).then((ok) => ok && toast('Stand neu geladen.')); return; }
    if (t.closest('#ci-lesen')) { lesenOeffnen(); return; }
    if (t.closest('#ci-sendung-neu')) { sendungOeffnen(''); return; }
    const es = t.closest('[data-export-sendung]');
    if (es) { exportieren('&sendung=' + encodeURIComponent(es.dataset.exportSendung)); return; }
    const eb = t.closest('[data-export-betrieb]');
    if (eb) { exportieren('&betrieb=' + encodeURIComponent(eb.dataset.exportBetrieb)); return; }
    if (t.closest('a, input, select, label, textarea')) return;
    const zb = t.closest('[data-betrieb]');
    if (zb) { betriebOeffnen(zb.dataset.betrieb); return; }
    const zs = t.closest('[data-sendung]');
    if (zs) { sendungOeffnen(zs.dataset.sendung); return; }
    const sid = $('#sendung-inhalt').dataset.id;
    if (t.closest('#sendung-druck')) { drucken(sid); return; }
    if (t.closest('#sendung-abschliessen')) { abschlussOeffnen(sid, false); return; }
    if (t.closest('#sendung-oeffnen')) { abschlussOeffnen(sid, true); return; }
    if (t.closest('#sendung-archiv')) { sendungSpeichern({ aktiv: !sendung(sid).aktiv }).then((ok) => ok && $('#dlg-sendung').close()); return; }
    if (t.closest('#betrieb-archiv')) { betriebSpeichern({ aktiv: !betrieb($('#betrieb-inhalt').dataset.id).aktiv }); return; }
    if (t.closest('#betrieb-pruefung')) { pruefungEintragen(); return; }
    if (t.closest('#betrieb-auswertung-nehmen')) { vorschlagNehmen($('#betrieb-auswertung').dataset, 'sonst'); return; }
    if (t.closest('#betrieb-whisp')) { whispPruefen(); return; }
    if (t.closest('#betrieb-whisp-nehmen')) { vorschlagNehmen($('#betrieb-whisp-ergebnis').dataset, 'whisp'); return; }
    if (t.closest('#lesen-pruefen')) { lesenPruefen(); return; }
  });
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || !e.target.matches('tr[tabindex]')) return;
    e.preventDefault();   // sonst träfe derselbe Tastendruck den Knopf „Schließen“ des eben geöffneten Fensters
    e.target.click();     // Zeile einer Liste öffnen wie mit der Maus
  });
  document.addEventListener('input', (e) => {
    if (e.target.id !== 'ci-suche') return;
    S.suche[S.sicht] = e.target.value;
    const stelle = e.target.selectionStart;
    sichtZeichnen();
    $('#ci-suche').focus(); $('#ci-suche').setSelectionRange(stelle, stelle);
  });
  document.addEventListener('change', (e) => {
    if (e.target.id === 'ci-archiv') { S.archiv = e.target.checked; zeichnen(); }
    if (e.target.name === 'lieferant' && e.target.form === $('#sendung-inhalt')) schlachthofWahlNeu();
    if (e.target.name === 'schlachthof') e.target.dataset.verdraengt = '';   // von Hand gewählt (auch „kein Schlachthof“): nichts mehr zurückholen
    if (e.target.id === 'ci-karte-sendung') { S.karteSendung = e.target.value; karteSicht(); }
    if (e.target.dataset.ort !== undefined) lesenZahl();
    if (e.target.id === 'lesen-dateien' && e.target.files.length) lesenPruefen();
  });
  $('#sendung-inhalt').addEventListener('submit', (e) => { e.preventDefault(); sendungSpeichern(); });
  $('#betrieb-inhalt').addEventListener('submit', (e) => { e.preventDefault(); betriebSpeichern(); });
  $('#abschluss-inhalt').addEventListener('submit', (e) => { e.preventDefault(); abschlussSenden(); });
  $('#lesen-inhalt').addEventListener('submit', (e) => { e.preventDefault(); lesenUebernehmen(); });
  $('#ci-theme').addEventListener('click', () => { document.documentElement.setAttribute('data-theme', dunkel() ? 'light' : 'dark'); themaKnopf(); });
  document.addEventListener('stafl-theme', themaKnopf);

  /* Brücke für weitere Dateien des Moduls (schlachthoefe.js): dieselben Hilfen und derselbe Zustand, keine zweite Kopie.
     Eine Datei trägt ihre Ansicht in sichten ein und hängt ihre eigenen Ereignisse an (docs/entwickler/06-oberflaechen.md). */
  window.STAFL_CI = { S, $, esc, icon, SU, feld, kopf, werte, api, uebernehmen, toast, oeffnen, landName, laenderWahl, lieferantFeld, lieferantAus, suchfeld, archivSchalter, sichten: SICHTEN };

  /* ---------- Start (nach dem Laden aller Dateien des Moduls) ---------- */
  document.addEventListener('DOMContentLoaded', async () => {
    themaKnopf();
    const st = await api('status');
    if (st.status !== 200) { fehler(fehlerText(st, 'Der Container-Import ist gerade nicht erreichbar')); return; }
    if (!st.data.loggedIn) { zeigeAnmeldung(); return; }
    S.csrf = st.data.csrf || '';
    if (window.STAFL_THEME) { window.STAFL_THEME.konto(st.data.user, S.csrf, API); themaKnopf(); }
    await laden(false);
  });
})();
