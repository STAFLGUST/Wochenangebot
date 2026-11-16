/* STAFL-Plattform · QM-System: Ordner-Import – einen ganzen Ordner (oder ein ZIP) einmal wählen, der Server legt jede Datei an
   der richtigen Stelle ab (Regeln nur dort: qs_sammel_plan, module/qs/ablage.php). Ablauf: Ordner lesen → Plan (Vorschau je oberstem
   Ordner, Zuordnung wählen, Nachtragen in gültige Versionen nur mit Häkchen) → Plan mit anlegen (neue Bereiche und Ordner-Dokumente)
   → Uploads mit LAUFEND gleichzeitig (qs_datei_hochladen mit sammeln) → je Bündel ein Eintrag (qs_import_eintragen) → Bericht als CSV.
   Fortsetzen: denselben Ordner erneut wählen, Abgelegtes zeigt der Plan als „schon abgelegt“. Nutzt die Brücke window.STAFL_QS. */
'use strict';
(() => {
  const Q = window.STAFL_QS;
  const { $, $$, S, esc, api, toast, fehlerText, zeigeAnmeldung, chip } = Q;
  const LAUFEND = 3, ZEILEN = 500;
  /* Status einer Datei: Text, Farbe, Gruppe (Filter und Zahlen), ablegbar (wird hochgeladen) */
  const ST = {
    ablage: ['ins Archiv', 'gruen', 'neu', true], dokument: ['in den Entwurf', 'gruen', 'neu', true], nachtragen: ['in die gültige Version', 'gelb', 'neu', true],
    eingang: ['in den Eingang', 'gelb', 'eingang', true], vorhanden: ['schon abgelegt', '', 'vorhanden', false],
    aus: ['nicht übernommen', '', 'weg', false], system: ['Systemdatei', '', 'weg', false], export: ['aus einem Export', '', 'weg', false],
    art: ['Dateiart nicht erlaubt', '', 'weg', false], leer: ['leer', '', 'weg', false], gross: ['zu groß', 'rot', 'weg', false], voll: ['Eingang voll', 'rot', 'weg', false],
    laeuft: ['wird hochgeladen …', 'blau', 'lauf', false], hochgeladen: ['wird eingetragen …', 'blau', 'lauf', false],
    abgelegt: ['abgelegt', 'gruen', 'fertig', false], imEingang: ['im Eingang', 'gelb', 'fertig', false], verworfen: ['früher gelöscht', '', 'weg', false],
    fehler: ['Fehler', 'rot', 'fehler', false],
  };
  const FILTER = [['', 'Alle'], ['neu', 'Neu'], ['eingang', 'Eingang'], ['vorhanden', 'Schon abgelegt'], ['weg', 'Übersprungen'], ['fertig', 'Fertig'], ['fehler', 'Fehler']];
  const I = { liste: [], ordner: [], plan: null, wahl: {}, filter: '', nachtragen: false, lauf: null };
  const gb = (b) => (b >= 1073741824 ? `${(b / 1073741824).toLocaleString('de-DE', { maximumFractionDigits: 2 })} GB` : Q.groesseText(b));
  const status = (e) => ST[e.status] || ['', '', 'weg', false];
  const dateienText = (n) => Q.archiv.dateienText(n);

  /* ---------- Ordner, Ziehen und ZIP lesen: Liste { pfad (Ordner), name, groesse, holen } ---------- */
  const eintrag = (voll, groesse, holen) => { const t = voll.split('/').filter(Boolean); return { name: t.pop() || '', pfad: t.join('/'), groesse, holen }; };
  async function ordnerLesen(e, pfad, aus) {
    if (aus.length > S.d.ablage.importMax) return;
    if (e.isFile) { const f = await new Promise((ok, nein) => e.file(ok, nein)); aus.push(eintrag(pfad + f.name, f.size, async () => f)); return; }
    if (!e.isDirectory) return;
    const leser = e.createReader();
    for (;;) {
      const teil = await new Promise((ok, nein) => leser.readEntries(ok, nein));
      if (!teil.length) break;
      for (const x of teil) await ordnerLesen(x, pfad + e.name + '/', aus);
    }
  }
  const CP437 = 'ÇüéâäàåçêëèïîìÄÅÉæÆôöòûùÿÖÜ¢£¥₧ƒáíóúñÑªº¿⌐¬½¼¡«»░▒▓│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌█▄▌▐▀αßΓπΣσµτΦΘΩδ∞φε∩≡±≥≤⌠⌡÷≈°∙·√ⁿ²■ ';
  const cp437 = (b) => [...b].map((c) => (c < 128 ? String.fromCharCode(c) : CP437[c - 128])).join('');
  async function zipLesen(file) {
    const ende = new DataView(await file.slice(Math.max(0, file.size - 65557)).arrayBuffer());
    let e = -1;
    for (let i = ende.byteLength - 22; i >= 0; i--) if (ende.getUint32(i, true) === 0x06054b50) { e = i; break; }
    if (e < 0) throw new Error('Die Datei ist kein ZIP-Archiv.');
    const anz = ende.getUint16(e + 10, true), cdGroesse = ende.getUint32(e + 12, true), cdPos = ende.getUint32(e + 16, true);
    if (anz === 0xffff || cdPos === 0xffffffff) throw new Error('Dieses ZIP ist zu groß (ZIP64) – bitte den Ordner selbst wählen.');
    const cd = new DataView(await file.slice(cdPos, cdPos + cdGroesse).arrayBuffer()), aus = [];
    let p = 0;
    for (let i = 0; i < anz && aus.length <= S.d.ablage.importMax; i++) {
      if (cd.getUint32(p, true) !== 0x02014b50) throw new Error('Das ZIP-Archiv ist beschädigt.');
      const flags = cd.getUint16(p + 8, true), methode = cd.getUint16(p + 10, true), komp = cd.getUint32(p + 20, true), roh = cd.getUint32(p + 24, true);
      const nl = cd.getUint16(p + 28, true), xl = cd.getUint16(p + 30, true), kl = cd.getUint16(p + 32, true), lokal = cd.getUint32(p + 42, true);
      const b = new Uint8Array(cd.buffer, cd.byteOffset + p + 46, nl), name = (flags & 0x800) ? new TextDecoder().decode(b) : cp437(b);
      p += 46 + nl + xl + kl;
      if (!name.endsWith('/')) aus.push(eintrag(name.replace(/\\/g, '/'), roh, () => zipEintrag(file, lokal, komp, methode, flags, name)));
    }
    return aus;
  }
  async function zipEintrag(file, lokal, komp, methode, flags, name) {
    if (flags & 1) throw new Error('verschlüsselt im ZIP');
    const kopf = new DataView(await file.slice(lokal, lokal + 30).arrayBuffer());
    if (kopf.getUint32(0, true) !== 0x04034b50) throw new Error('ZIP-Eintrag beschädigt');
    const start = lokal + 30 + kopf.getUint16(26, true) + kopf.getUint16(28, true), roh = file.slice(start, start + komp);
    if (methode === 0) return new File([roh], name.split('/').pop());
    if (methode === 8 && 'DecompressionStream' in window) return new File([await new Response(roh.stream().pipeThrough(new DecompressionStream('deflate-raw'))).blob()], name.split('/').pop());
    throw new Error('Packverfahren im ZIP nicht unterstützt – bitte den Ordner selbst wählen');
  }

  /* ---------- Plan vom Server: Dateien je Ordner gebündelt (hält die Anfrage unter 6 MB) ---------- */
  async function planen(anlegen = false) {
    const r = await api('qs_sammel_plan', { ordner: I.ordner.map((o) => [o.pfad, o.dateien.map((e) => [e.name, e.groesse])]), wahl: I.wahl, anlegen });
    if (r.status === 401) { zeigeAnmeldung(); return false; }
    if (r.status !== 200 || !r.data.ok) { meldung(fehlerText(r, 'Der Plan konnte nicht erstellt werden')); return false; }
    I.plan = r.data;
    I.liste.forEach((e, i) => { e.plan = r.data.dateien[i]; e.status = e.plan.schonDa ? 'vorhanden' : e.plan.status; e.grund = e.plan.schonDa ? '' : e.plan.grund || ''; });
    for (const z of r.data.oberste) if (z.art !== 'auto') I.wahl[z.name] = { art: z.art, ...(z.kapitel ? { kapitel: z.kapitel } : {}), ...(z.titel ? { titel: z.titel } : {}) };
    return true;
  }
  async function laden(quelle) {
    meldung('Dateien werden gelesen …', true);
    let liste;
    try { liste = await quelle; } catch (err) { meldung(err.message || String(err)); return; }
    if (liste.length > S.d.ablage.importMax) { meldung(`Mehr als ${Q.zahl(S.d.ablage.importMax)} Dateien – bitte Kapitel einzeln importieren.`); return; }
    if (!liste.length) { meldung('Keine Dateien gefunden.'); return; }
    const je = new Map();
    for (const e of liste) { if (!je.has(e.pfad)) je.set(e.pfad, { pfad: e.pfad, dateien: [] }); je.get(e.pfad).dateien.push(e); }
    I.ordner = [...je.values()]; I.liste = I.ordner.flatMap((o) => o.dateien); I.wahl = {}; I.filter = ''; I.nachtragen = false; I.lauf = null;
    meldung('Plan wird erstellt …', true);
    if (!(await planen())) return;
    const gemerkt = wahlLaden(I.plan.wurzel || '');
    if (Object.keys(gemerkt).length) { I.wahl = gemerkt; if (!(await planen())) { I.wahl = {}; if (!(await planen())) return; } }
    meldung('', true); zeichnen();
  }
  /* Ordnerpfad ohne den weggelassenen gewählten Ordner – so bereinigt ihn der Server wie im Plan */
  const rel = (e) => { const t = e.pfad.split('/').filter(Boolean); if (I.plan.wurzel && t[0] === I.plan.wurzel) t.shift(); return t.join('/'); };
  const oben = (e) => rel(e).split('/')[0];
  const WAHL = 'qs-import-wahl:';   // Zuordnung der obersten Ordner je gewähltem Ordner (Fortsetzen nach Neuladen)
  const wahlLaden = (w) => { try { return JSON.parse(localStorage.getItem(WAHL + w) || '{}'); } catch { return {}; } };
  const wahlMerken = () => { try { localStorage.setItem(WAHL + (I.plan.wurzel || ''), JSON.stringify(I.wahl)); } catch { /* ohne Speicher */ } };
  const zielText = (e) => {
    const p = e.plan || {};
    if (p.ziel === 'eingang' || e.status === 'imEingang') return 'Eingang';
    if (/^neu:/.test(p.ziel || '')) { const n = I.plan.neu[Number(p.ziel.slice(4))]; return n ? `${n.titel} (neu, ${Q.kapitelText(n.kapitel)})` : ''; }
    const x = S.d.dokumente.find((y) => y.id === p.ziel);
    return x ? `${x.nr ? x.nr + ' ' : ''}${x.titel}` : '';
  };
  const hochladen = (e) => status(e)[3];
  /* Nachtragen in gültige Versionen nur mit Häkchen – sonst in den Eingang (mit dem ganzen Ordnerpfad) */
  const inEingang = (p) => p.status === 'eingang' || (p.status === 'nachtragen' && !I.nachtragen);

  /* ---------- Vorschau ---------- */
  function meldung(text, ok = false) { $('#im-meldung').className = 'qm-meldung' + (ok ? ' ok' : ''); $('#im-meldung').textContent = text; }
  function wahlHtml(z) {
    if (z.art === 'auto') return `<b>${esc(Q.kapitelText(z.kapitel))}</b><span class="qm-sub">an der Kapitelnummer erkannt</span>`;
    const w = I.wahl[z.name] || { art: 'eingang' }, gesperrt = !!I.lauf;
    const opt = [['eingang', 'Eingang'], ['aus', 'nicht übernehmen'], ...S.d.kapitel.map((k) => [`kapitel:${k.id}`, `${k.bereich ? 'Bereich' : 'Kapitel'} ${k.id} ${k.titel}`]),
      ...(Q.darf('verwalten') ? [['neu', 'Neuer Bereich …']] : [])];
    const wert = w.art === 'kapitel' ? `kapitel:${w.kapitel}` : w.art;
    let h = `<select class="qm-eingabe" data-im-wahl="${esc(z.name)}" aria-label="Zuordnung für ${esc(z.name)}"${gesperrt ? ' disabled' : ''}>${opt.map(([k, t]) => `<option value="${esc(k)}"${k === wert ? ' selected' : ''}>${esc(t)}</option>`).join('')}</select>`;
    if (w.art === 'neu') h += `<span class="qm-im-bereich"><input class="qm-eingabe" data-im-nr="${esc(z.name)}" value="${esc(w.kapitel || '')}" aria-label="Nummer des Bereichs" inputmode="decimal"${gesperrt ? ' disabled' : ''}><input class="qm-eingabe" data-im-titel="${esc(z.name)}" value="${esc(w.titel || '')}" aria-label="Titel des Bereichs"${gesperrt ? ' disabled' : ''}></span>`;
    return h;
  }
  function zahlen(liste) {
    const z = { n: liste.length, b: 0, neu: 0, vorhanden: 0, weg: 0, fertig: 0, fehler: 0 };
    for (const e of liste) {
      const g = status(e)[2];
      z.b += e.groesse;
      if (hochladen(e)) z.neu++;
      if (g in z && g !== 'neu') z[g]++;
    }
    return z;
  }
  function zeichnen() {
    const P = I.plan, L = I.lauf;
    $('#im-ergebnis').hidden = !P;
    if (!P) return;
    const auto = P.oberste.filter((z) => z.art === 'auto').map((z) => z.kapitel);
    $('#im-wurzel').innerHTML = `Gewählter Ordner: <b>${esc(P.wurzel || (I.ordner[0] && I.ordner[0].pfad.split('/')[0]) || '—')}</b> · ${dateienText(I.liste.length)} · ${gb(I.liste.reduce((s, e) => s + e.groesse, 0))}`
      + ` · erkannte Kapitel: <b>${auto.length ? esc(auto.join(', ')) : 'keine'}</b>`;
    $('#im-warnung').hidden = !auto.length;
    const je = new Map(P.oberste.map((z) => [z.name, []])), lose = [];
    for (const e of I.liste) (je.get(oben(e)) || lose).push(e);
    const zeile = (name, z, l) => { const c = zahlen(l); return `<tr><td class="qm-voll" data-label="Ordner"><span class="qm-name">${esc(name)}</span></td><td data-label="Zuordnung" class="qm-im-wahl">${z}</td>`
      + `<td class="qm-zahl" data-label="Dateien">${Q.zahl(c.n)}<span class="qm-sub">${gb(c.b)}</span></td><td class="qm-zahl" data-label="neu">${Q.zahl(c.neu)}</td><td class="qm-zahl" data-label="schon da">${Q.zahl(c.vorhanden)}</td><td class="qm-zahl" data-label="übersprungen">${Q.zahl(c.weg)}</td></tr>`; };
    $('#im-oberste').innerHTML = `<table class="qm-tabelle qm-karten qm-im-tabelle"><thead><tr><th>Oberster Ordner</th><th>Zuordnung</th><th class="qm-zahl">Dateien</th><th class="qm-zahl">neu</th><th class="qm-zahl">schon da</th><th class="qm-zahl">übersprungen</th></tr></thead><tbody>`
      + P.oberste.map((z) => zeile(z.name, wahlHtml(z), je.get(z.name))).join('') + (lose.length ? zeile('lose Dateien', '<b>Eingang</b>', lose) : '') + '</tbody></table>';
    const nt = I.liste.filter((e) => e.status === 'nachtragen');
    $('#im-nachtragen').hidden = !nt.length;
    if (nt.length) {
      $('#im-nachtragen-an').checked = I.nachtragen; $('#im-nachtragen-an').disabled = !!L;
      $('#im-nachtragen-text').textContent = `${dateienText(nt.length)} als aktuelle Fassung in gültige Versionen nachtragen`;
      $('#im-nachtragen-liste').innerHTML = nt.slice(0, ZEILEN).map((e) => `<li>${esc(e.pfad ? e.pfad + '/' : '')}<b>${esc(e.name)}</b> → ${esc(zielText(e))}</li>`).join('');
    }
    const c = zahlen(I.liste);
    $('#im-zahlen').innerHTML = [['Dateien', c.n], ['neu', c.neu], ['schon abgelegt', c.vorhanden], ['übersprungen', c.weg], ['neue Ordner', P.neu.length], ['neue Bereiche', Object.keys(P.bereiche || {}).length]]
      .concat(L ? [['fertig', c.fertig], ['Fehler', c.fehler]] : []).map(([n, w]) => `<div><b>${Q.zahl(w)}</b><span>${esc(n)}</span></div>`).join('');
    const gruppe = (g) => I.liste.filter((e) => status(e)[2] === g).length;
    $('#im-filter').innerHTML = FILTER.map(([k, n]) => { const z = k ? gruppe(k) : I.liste.length; return k && !z && I.filter !== k ? '' : `<button type="button" data-im-filter="${k}" aria-pressed="${I.filter === k}">${esc(n)} <b>${Q.zahl(z)}</b></button>`; }).join('');
    listeZeichnen();
    const offen = I.liste.filter(hochladen).length;
    $('#im-los').hidden = !!L; $('#im-los').disabled = !offen;
    $('#im-los').textContent = offen === 1 ? '1 Datei importieren' : `${Q.zahl(offen)} Dateien importieren`;
    $('#im-stopp').hidden = !L || L.ende; $('#im-csv').hidden = !L || !L.ende;
    $('#im-fortschritt').hidden = !L; $('#im-stand').hidden = !L;
  }
  function dateiZeile(e) {
    const [text, farbe] = status(e);
    return `<tr><td class="qm-voll" data-label="Datei"><span class="qm-name">${esc(e.name)}</span><span class="qm-sub">${esc(e.pfad || '—')} · ${esc(Q.groesseText(e.groesse))}</span></td>`
      + `<td data-label="Ziel">${esc(zielText(e) || '—')}${e.plan && e.plan.pfad && e.plan.ziel !== 'eingang' ? `<span class="qm-sub">${esc(e.plan.pfad.split('/').join(' / '))}</span>` : ''}</td>`
      + `<td data-label="Status" class="qm-sa-status">${chip(text + (e.grund ? ` · ${e.grund}` : '') + (e.status === 'laeuft' && e.empfangen ? ` ${Math.round(100 * e.empfangen / e.groesse)} %` : ''), farbe)}</td></tr>`;
  }
  function listeZeichnen() {
    const l = I.liste.filter((e) => !I.filter || status(e)[2] === I.filter);
    $('#im-liste').innerHTML = `<table class="qm-tabelle qm-karten qm-sa-tabelle"><thead><tr><th>Datei</th><th>Ziel</th><th>Status</th></tr></thead><tbody>${l.slice(0, ZEILEN).map(dateiZeile).join('') || Q.leerzeile(3, 'Keine Dateien in dieser Auswahl.')}</tbody></table>`
      + (l.length > ZEILEN ? `<p class="qm-hilfe">Angezeigt: ${Q.zahl(ZEILEN)} von ${Q.zahl(l.length)} Dateien.</p>` : '');
  }

  /* ---------- Lauf: LAUFEND Uploads gleichzeitig, fertige Uploads gebündelt eintragen, Fehler halten nicht an ---------- */
  function fortschritt() {
    const L = I.lauf, sek = (Date.now() - L.start) / 1000, rate = L.gesendet / Math.max(sek, 1), rest = Math.max(0, L.bytes - L.gesendet);
    $('#im-fortschritt').max = L.bytes || 1; $('#im-fortschritt').value = L.gesendet;
    $('#im-stand').textContent = `${Q.zahl(L.erledigt)} von ${dateienText(L.dateien)} · ${L.gesendet ? gb(L.gesendet) : '0 KB'} von ${gb(L.bytes)}`
      + (L.ende ? '' : rate > 0 && L.gesendet ? ` · noch etwa ${Q.zahl(Math.max(1, Math.round(rest / rate / 60)))} min` : '');
  }
  async function eintragenJetzt(alle) {
    const L = I.lauf, n = S.d.ablage.buendel;
    while (L.fertig.length >= (alle ? 1 : n)) {
      const teil = L.fertig.splice(0, n);
      const r = await api('qs_import_eintragen', { uploads: teil.map((e) => e.upload) });
      if (r.status === 401) { L.abbrechen = true; L.anmelden = true; return; }
      for (const e of teil) {
        const x = r.status === 200 && r.data.ok ? r.data.uploads[e.upload] : { status: 'fehler', grund: fehlerText(r, 'Eintragen fehlgeschlagen') };
        e.status = { abgelegt: e.ein ? 'imEingang' : 'abgelegt', eingang: 'imEingang', vorhanden: 'vorhanden', verworfen: 'verworfen' }[x && x.status] || 'fehler';
        e.grund = x && x.grund ? x.grund : '';
        L.erledigt++;
      }
      zeichnen(); fortschritt();
    }
  }
  const eintragen = (alle = false) => { I.lauf.kette = I.lauf.kette.then(() => eintragenJetzt(alle)); return I.lauf.kette; };
  async function arbeiter() {
    const L = I.lauf;
    while (!L.abbrechen && L.warte.length) {
      const e = L.warte.shift(), vorher = { gesendet: 0 };
      e.status = 'laeuft'; e.empfangen = 0;
      let f;
      try { f = await e.holen(); } catch (err) { e.status = 'fehler'; e.grund = err.message || 'nicht lesbar'; L.erledigt++; continue; }
      const p = e.plan;
      e.ein = inEingang(p);
      const r = await Q.dateiSenden(f, e.ein ? 'eingang' : p.ziel, e.ein ? '' : p.ver || '', (pos) => { L.gesendet += pos - vorher.gesendet; vorher.gesendet = pos; e.empfangen = pos; },
        { sammeln: true, pfad: e.ein ? rel(e) : p.pfad || '', herkunft: rel(e) });
      if (r.anmelden) { L.abbrechen = true; L.anmelden = true; return; }
      if (r.fehler) { e.status = 'fehler'; e.grund = r.fehler; L.erledigt++; continue; }
      e.status = 'hochgeladen'; e.upload = r.upload; L.fertig.push(e);
      if (L.fertig.length >= S.d.ablage.buendel) await eintragen();
    }
  }
  async function starten() {
    if (I.lauf) return;
    $('#im-los').disabled = true;
    meldung('Neue Ordner und Bereiche werden angelegt …', true);
    if (!(await planen(true))) { $('#im-los').disabled = false; return; }
    wahlMerken();
    await Q.neuLaden();
    const warte = I.liste.filter(hochladen);
    I.lauf = { warte, fertig: [], kette: Promise.resolve(), start: Date.now(), gesendet: 0, bytes: warte.reduce((s, e) => s + e.groesse, 0), dateien: warte.length, erledigt: 0, abbrechen: false, ende: false };
    meldung('');
    zeichnen(); fortschritt();
    const takt = setInterval(() => { fortschritt(); listeZeichnen(); }, 1000);
    await Promise.all(Array.from({ length: LAUFEND }, arbeiter));
    await eintragen(true);
    clearInterval(takt);
    const L = I.lauf;
    L.ende = true;
    for (const e of L.warte) e.grund = 'abgebrochen, nicht hochgeladen';
    if (L.anmelden) { $('#dlg-import').close(); zeigeAnmeldung(); return; }
    await Q.neuLaden();
    if (!$('#dlg-import').open) return;
    zeichnen(); fortschritt();
    const c = zahlen(I.liste);
    meldung(`${dateienText(I.liste.filter((e) => e.status === 'abgelegt').length)} abgelegt, ${Q.zahl(I.liste.filter((e) => e.status === 'imEingang').length)} im Eingang`
      + ` · schon abgelegt ${Q.zahl(c.vorhanden)} · übersprungen ${Q.zahl(c.weg)} · Fehler ${Q.zahl(c.fehler)}` + (L.abbrechen ? ` – abgebrochen, ${Q.zahl(L.warte.length)} nicht hochgeladen` : '') + '.', !c.fehler);
    toast(c.fehler ? `${dateienText(c.fehler)} mit Fehler – Bericht als CSV` : 'Ordner-Import abgeschlossen', !!c.fehler);
  }
  function berichtCsv() {
    const z = (v) => { const t = String(v ?? ''); return /^[=+\-@]/.test(t) ? `'${t}` : t; };   // keine Formeln in Excel
    const zeilen = [['Ordner', 'Datei', 'Größe (Bytes)', 'Ergebnis', 'Ziel', 'Grund'], ...I.liste.map((e) => [e.pfad, e.name, e.groesse, status(e)[0], zielText(e), e.grund])];
    const csv = '﻿' + zeilen.map((r) => r.map((v) => `"${z(v).replace(/"/g, '""')}"`).join(';')).join('\r\n');
    Q.speichereDatei(new Blob([csv], { type: 'text/csv;charset=utf-8' }), `QM-Ordner-Import_${S.d.heute}.csv`);
  }

  /* ---------- Ereignisse ---------- */
  function oeffnen() {
    if (!I.lauf || I.lauf.ende) { I.plan = null; I.liste = []; I.lauf = null; }
    meldung('');
    zeichnen();
    Q.oeffne($('#dlg-import'));
  }
  $('#qm-d-import').addEventListener('click', oeffnen);
  $('#im-ordner-knopf').addEventListener('click', () => { $('#im-ordner').value = ''; $('#im-ordner').click(); });
  $('#im-zip-knopf').addEventListener('click', () => { $('#im-zip').value = ''; $('#im-zip').click(); });
  $('#im-ordner').addEventListener('change', (ev) => { if (!I.lauf || I.lauf.ende) laden(Promise.resolve([...ev.target.files].map((f) => eintrag(f.webkitRelativePath || f.name, f.size, async () => f)))); });
  $('#im-zip').addEventListener('change', (ev) => { const f = ev.target.files[0]; if (f && (!I.lauf || I.lauf.ende)) laden(zipLesen(f)); });
  $('#im-drop').addEventListener('drop', (ev) => {   // Ordner sind nur während des Ereignisses lesbar
    if (!ev.dataTransfer || (I.lauf && !I.lauf.ende)) return;
    const eintraege = [...(ev.dataTransfer.items || [])].filter((it) => it.kind === 'file').map((it) => (it.webkitGetAsEntry ? it.webkitGetAsEntry() : null)).filter(Boolean);
    const dateien = [...ev.dataTransfer.files];
    if (dateien.length === 1 && /\.zip$/i.test(dateien[0].name) && !(eintraege[0] && eintraege[0].isDirectory)) { laden(zipLesen(dateien[0])); return; }
    if (eintraege.length) laden((async () => { const aus = []; for (const e of eintraege) await ordnerLesen(e, '', aus); return aus; })());
    else laden(Promise.resolve(dateien.map((f) => eintrag(f.name, f.size, async () => f))));
  });
  $('#im-oberste').addEventListener('change', async (ev) => {
    const el = ev.target, name = el.dataset.imWahl ?? el.dataset.imNr ?? el.dataset.imTitel;
    if (name === undefined) return;
    const z = I.plan.oberste.find((x) => x.name === name);
    if (el.dataset.imWahl !== undefined) I.wahl[name] = el.value.startsWith('kapitel:') ? { art: 'kapitel', kapitel: el.value.slice(8) } : el.value === 'neu' ? { art: 'neu', ...z.vorschlag } : { art: el.value };
    else I.wahl[name] = { ...I.wahl[name], [el.dataset.imNr !== undefined ? 'kapitel' : 'titel']: el.value.trim() };
    meldung('Plan wird erstellt …', true);
    if (await planen()) { wahlMerken(); meldung('', true); zeichnen(); }
  });
  $('#im-nachtragen-an').addEventListener('change', (ev) => { I.nachtragen = ev.target.checked; zeichnen(); });
  $('#im-filter').addEventListener('click', (ev) => { const b = ev.target.closest('[data-im-filter]'); if (b) { I.filter = b.dataset.imFilter; zeichnen(); } });
  $('#im-form').addEventListener('submit', (ev) => { ev.preventDefault(); starten(); });
  $('#im-stopp').addEventListener('click', () => { if (I.lauf) { I.lauf.abbrechen = true; $('#im-stopp').disabled = true; meldung('Wird nach den laufenden Dateien angehalten …', true); } });
  $('#im-csv').addEventListener('click', berichtCsv);
  const laeuft = () => I.lauf && !I.lauf.ende;
  $$('#dlg-import [data-im-zu]').forEach((b) => b.addEventListener('click', () => { if (laeuft()) toast('Der Import läuft noch – „Abbrechen“ hält nach den laufenden Dateien an.', true); else $('#dlg-import').close(); }));
  $('#dlg-import').addEventListener('cancel', (ev) => { if (laeuft()) { ev.preventDefault(); toast('Der Import läuft noch – „Abbrechen“ hält nach den laufenden Dateien an.', true); } });

})();
