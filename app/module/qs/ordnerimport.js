/* STAFL-Plattform · QM-System: Ordner-Import – einen ganzen Ordner (oder ein ZIP) einmal wählen, der Server legt jede Datei an
   der richtigen Stelle ab. Regeln und Pfade nur auf dem Server (module/qs/ablage.php, beschrieben in docs/entwickler/05-daten.md):
   der Browser schickt die Dateiliste und die Angaben des Nutzers (Wurzel, Zuordnung und Freigaben je oberstem Ordner, abgewählte
   Dateien) an qs_sammel_plan, zeigt den Plan, lädt mit LAUFEND gleichzeitig hoch (qs_datei_hochladen mit sammeln und herkunft) und
   trägt gebündelt ein (qs_import_eintragen mit dem erwarteten Status je Datei). Nutzt die Brücke window.STAFL_QS. */
'use strict';
(() => {
  const Q = window.STAFL_QS;
  const { $, $$, S, esc, api, toast, fehlerText, zeigeAnmeldung, chip, dateienText } = Q;
  const LAUFEND = 3, ZEILEN = 500;
  /* Status einer Datei: hoch = wird hochgeladen; gruppe für Filter und Zahlen */
  const st = (text, farbe, gruppe, hoch = false) => ({ text, farbe, gruppe, hoch });
  const ST = {
    ablage: st('ins Archiv', 'gruen', 'ablegen', true), dokument: st('in den Entwurf', 'gruen', 'ablegen', true),
    nachtragen: st('in die gültige Version', 'gelb', 'ablegen', true), eingang: st('in den Eingang', 'gelb', 'eingang', true),
    offen: st('Zuordnung offen', 'gelb', 'offen'), vorhanden: st('schon abgelegt', '', 'vorhanden'),
    aus: st('nicht übernommen', '', 'weg'), system: st('Systemdatei', '', 'weg'), export: st('aus einem Export', '', 'weg'),
    art: st('Dateiart nicht erlaubt', '', 'weg'), leer: st('leer', '', 'weg'), gross: st('zu groß', 'rot', 'weg'), voll: st('Eingang voll', 'rot', 'weg'),
    laeuft: st('wird hochgeladen …', 'blau', 'lauf'), hochgeladen: st('wird eingetragen …', 'blau', 'lauf'),
    abgelegt: st('abgelegt', 'gruen', 'fertig'), imEingang: st('im Eingang', 'gelb', 'fertig'), verworfen: st('früher gelöscht', '', 'weg'),
    fehler: st('Fehler', 'rot', 'fehler'),
  };
  const FILTER = [['', 'Alle'], ['ablegen', 'Neu'], ['eingang', 'Eingang'], ['offen', 'Offen'], ['vorhanden', 'Schon abgelegt'], ['weg', 'Übersprungen'], ['fertig', 'Fertig'], ['fehler', 'Fehler']];
  const I = { liste: [], ordner: [], plan: null, wurzel: {}, wahl: {}, freigaben: {}, ohne: new Set(), filter: '', lauf: null };
  const gb = (b) => (b >= 1073741824 ? `${(b / 1073741824).toLocaleString('de-DE', { maximumFractionDigits: 2 })} GB` : Q.groesseText(b));
  const status = (e) => ST[e.status] || st('', '', 'weg');
  const schluessel = (e) => `${e.pfad}/${e.name}`;   // abgewählte Datei: Ordnerpfad wie gewählt und Name (so vergleicht der Server)

  /* ---------- Ordner, Ziehen und ZIP lesen: Liste { pfad (Ordner), name, groesse, holen } ---------- */
  // macOS liefert Umlaute zerlegt (NFD); der Server vergleicht Kapitel- und Ordnernamen zusammengesetzt (NFC)
  const eintrag = (voll, groesse, holen) => { const t = voll.normalize('NFC').split('/').filter(Boolean); return { name: t.pop() || '', pfad: t.join('/'), groesse, holen }; };
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
  const angaben = () => ({ wurzel: { ...I.wurzel, name: I.plan ? I.plan.wurzel.name : '' }, wahl: I.wahl, freigaben: I.freigaben });
  async function planen(anlegen = false) {
    const r = await api('qs_sammel_plan', { ordner: I.ordner.map((o) => [o.pfad, o.dateien.map((e) => [e.name, e.groesse])]), ...angaben(), ohne: [...I.ohne], anlegen });
    if (r.status === 401) { zeigeAnmeldung(); return false; }
    if (r.status !== 200 || !r.data.ok) { meldung(fehlerText(r, 'Der Plan konnte nicht erstellt werden')); return false; }
    I.plan = r.data;
    I.liste.forEach((e, i) => { e.plan = r.data.dateien[i]; e.status = e.plan.schonDa ? 'vorhanden' : e.plan.status; e.grund = e.plan.schonDa ? '' : e.plan.grund || ''; });
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
    Object.assign(I, { ordner: [...je.values()], wurzel: {}, wahl: {}, freigaben: {}, ohne: new Set(), filter: '', lauf: null, plan: null });
    I.liste = I.ordner.flatMap((o) => o.dateien);
    meldung('Plan wird erstellt …', true);
    if (!(await planen())) return;
    const gemerkt = wahlLaden();
    if (gemerkt.wahl || gemerkt.wurzel) {
      Object.assign(I, { wurzel: gemerkt.wurzel || {}, wahl: gemerkt.wahl || {}, ohne: new Set(gemerkt.ohne || []) });
      if (!(await planen())) { Object.assign(I, { wurzel: {}, wahl: {}, ohne: new Set() }); if (!(await planen())) return; }
    }
    meldung('', true); zeichnen();
  }
  // Wurzel, Zuordnung der obersten Ordner und abgewählte Dateien je gewähltem Ordner (Fortsetzen nach Neuladen) – die Freigaben nie. Schlüssel
  // ist der Fingerabdruck (Name, Zahl der Dateien, Bytes): ein anderer Ordner gleichen Namens (etwa der der Fremdfirma) bekommt keine Antwort vorab
  const WAHL = 'qs-import-wahl:';
  const fingerabdruck = () => `${WAHL}${I.plan.wurzel.name}|${I.liste.length}|${I.liste.reduce((s, e) => s + e.groesse, 0)}`;
  const wahlLaden = () => { try { return JSON.parse(localStorage.getItem(fingerabdruck()) || '{}'); } catch { return {}; } };
  const wahlMerken = () => { try { localStorage.setItem(fingerabdruck(), JSON.stringify({ wurzel: I.wurzel, wahl: I.wahl, ohne: [...I.ohne] })); } catch { /* ohne Speicher */ } };
  const dokText = (id) => { const x = S.d.dokumente.find((y) => y.id === id); return x ? `${x.nr ? x.nr + ' ' : ''}${x.titel}` : ''; };
  const zielText = (e) => {
    const p = e.plan || {};
    if (p.ziel === 'eingang' || e.status === 'imEingang') return 'Eingang';
    if (p.neu !== undefined) { const n = I.plan.neu[p.neu]; return n ? `${n.titel} (neu, ${Q.kapitelText(n.kapitel)})` : ''; }
    return dokText(p.ziel);
  };

  /* ---------- Vorschau ---------- */
  function meldung(text, ok = false) { $('#im-meldung').className = 'qm-meldung' + (ok ? ' ok' : ''); $('#im-meldung').textContent = text; }
  const gesperrt = () => (I.lauf ? ' disabled' : '');
  const option = (k, t, wert) => `<option value="${esc(k)}"${k === wert ? ' selected' : ''}>${esc(t)}</option>`;
  const bereichFelder = (w, attr, name) => `<span class="qm-im-bereich"><input class="qm-eingabe" ${attr}-nr="${esc(name)}" value="${esc(w.kapitel || '')}" aria-label="Nummer des Bereichs (90 bis 99)" inputmode="numeric"${gesperrt()}>`
    + `<input class="qm-eingabe" ${attr}-titel="${esc(name)}" value="${esc(w.titel || '')}" aria-label="Titel des Bereichs"${gesperrt()}></span>`;
  /* Wohin gehört der gewählte Ordner? Nur wenn er wegfallen würde und darin Kapitelordner stehen – ohne Antwort startet nichts */
  function wurzelHtml(P) {
    const w = I.wurzel, wert = w.art === 'kapitel' ? `kapitel:${w.kapitel}` : w.art || '';
    const opt = [['', '— bitte wählen —'], ['sf', 'Standard-Fleisch: Kapitelordner darin zuordnen'], ...S.d.kapitel.filter((k) => k.bereich).map((k) => [`kapitel:${k.id}`, `Bereich ${k.id} ${k.titel}`]),
      ...(Q.darf('verwalten') ? [['neu', 'Neuer Bereich …']] : [])];
    return `<label class="qm-feld"><span>Wohin gehört der Ordner „${esc(P.wurzel.name)}“? Darin stehen Ordner mit Kapitelnummer.</span>`
      + `<select class="qm-eingabe" id="im-wurzel-wahl"${gesperrt()}>${opt.map(([k, t]) => option(k, t, wert)).join('')}</select></label>`
      + (w.art === 'neu' ? bereichFelder(w, 'data-im-wurzel', P.wurzel.name) : '')
      + `<p class="qm-hilfe">Gehört er zu einer anderen Firma, wählen Sie ihren Bereich – dort wird nie per Dokumenten-Nummer zugeordnet.</p>`;
  }
  function wahlHtml(z) {
    if (z.wurzel) return `<b>${esc(Q.kapitelText(z.kapitel || ''))}</b><span class="qm-sub">oben gewählt</span>`;
    if (z.art === 'offen') return '<b>offen</b><span class="qm-sub">bitte oben wählen, wohin der Ordner gehört</span>';
    const wert = z.art === 'kapitel' ? `kapitel:${z.kapitel}` : z.art, w = I.wahl[z.name] || {};
    const opt = [...(z.erkannt ? [['genau', `Kapitel ${z.erkannt} – Kapitelordner (Nummern)`], [`kapitel:${z.erkannt}`, `Kapitel ${z.erkannt} – nur Archiv`]] : []),
      ['eingang', 'Eingang'], ['aus', 'nicht übernehmen'],
      ...S.d.kapitel.filter((k) => k.id !== z.erkannt).map((k) => [`kapitel:${k.id}`, `${k.bereich ? 'Bereich' : 'Kapitel'} ${k.id} ${k.titel}`]),
      ...(Q.darf('verwalten') ? [['neu', 'Neuer Bereich …']] : [])];
    const sub = z.art === 'genau' ? 'an der Kapitelnummer erkannt' : z.imPfad ? 'nur Archiv – der Ordnername bleibt erhalten' : '';
    return `<select class="qm-eingabe" data-im-wahl="${esc(z.name)}" aria-label="Zuordnung für ${esc(z.name)}"${gesperrt()}>${opt.map(([k, t]) => option(k, t, wert)).join('')}</select>`
      + (z.art === 'neu' ? bereichFelder(w, 'data-im', z.name) : '') + (sub ? `<span class="qm-sub">${esc(sub)}</span>` : '');
  }
  function zahlen(liste) {
    const z = { n: liste.length, b: 0, neu: 0, vorhanden: 0, weg: 0, fertig: 0, fehler: 0 };
    for (const e of liste) {
      const s = status(e);
      z.b += e.groesse;
      if (s.hoch) z.neu++;
      if (s.gruppe in z) z[s.gruppe]++;
    }
    return z;
  }
  /* Freigaben je oberstem Ordner: Nachtragen in gültige Versionen (Vorgabe aus), Entwürfe (Vorgabe an); Dateien je Dokument gruppiert, einzeln abwählbar */
  function freigabenHtml(P) {
    const je = P.oberste.map(() => []);
    for (const e of I.liste) if (e.plan && e.plan.kandidat && e.plan.oben !== undefined) je[e.plan.oben].push(e);
    const entwuerfe = new Set(I.liste.filter((e) => e.status === 'dokument').map((e) => e.plan.ver)).size;
    const teil = P.oberste.map((z, i) => {
      if (!je[i].length) return '';
      const art = (k) => je[i].filter((e) => e.plan.kandidat === k && !I.ohne.has(schluessel(e))).length;
      const box = (k, n, text) => (n ? `<label class="qm-check"><input type="checkbox" data-im-frei="${esc(z.name)}" data-im-art="${k}"${z[k] ? ' checked' : ''}${gesperrt()}> ${esc(text)}</label>` : '');
      const gruppen = new Map();
      for (const e of je[i]) { if (!gruppen.has(e.plan.dok)) gruppen.set(e.plan.dok, []); gruppen.get(e.plan.dok).push(e); }
      const liste = [...gruppen].map(([dok, l]) => `<li><b>${esc(dokText(dok))}</b> → ${l[0].plan.kandidat === 'nachtragen' ? 'gültige Version' : 'Entwurf'}${l.length > 1 ? ` · ${Q.zahl(l.length)} Dateien zu dieser Nummer` : ''}`
        + `<ul>${l.map((e) => `<li><label class="qm-check"><input type="checkbox" data-im-ohne="${esc(schluessel(e))}"${I.ohne.has(schluessel(e)) ? '' : ' checked'}${gesperrt()}> ${esc(e.name)}</label></li>`).join('')}</ul></li>`).join('');
      return `<fieldset class="qm-im-frei"><legend>${esc(z.name)}</legend>`
        + box('nachtragen', art('nachtragen'), `${dateienText(art('nachtragen'))} als aktuelle Fassung in gültige Versionen nachtragen`)
        + box('entwurf', art('dokument'), `${dateienText(art('dokument'))} in Entwürfe ablegen`)
        + `<details class="qm-details"><summary>Dateien je Dokument ansehen und einzeln abwählen</summary><ul class="qm-verlauf qm-im-gruppen">${liste}</ul></details></fieldset>`;
    }).join('');
    return teil && teil + (entwuerfe ? `<p class="qm-hilfe"><b>Sie werden Bearbeiter ${entwuerfe === 1 ? 'dieses Entwurfs' : `dieser ${Q.zahl(entwuerfe)} Entwürfe`}</b> (4-Augen-Prinzip: Sie können ${entwuerfe === 1 ? 'ihn' : 'sie'} danach nicht selbst prüfen).</p>` : '')
      + '<p class="qm-hilfe">Nachtragen lässt sich nicht rückgängig machen. Ohne Häkchen kommen diese Dateien in den Eingang, abgewählte ins Archiv.</p>';
  }
  function zeichnen() {
    const P = I.plan, L = I.lauf;
    $('#im-ergebnis').hidden = !P;
    if (!P) return;
    const erkannt = [...new Set(P.oberste.filter((z) => z.erkannt).map((z) => z.erkannt))].sort(Q.natCmp);   // Reihenfolge des Dateisystems ist zufällig
    $('#im-wurzel').innerHTML = `Gewählter Ordner: <b>${esc(P.wurzel.name || '—')}</b> · ${dateienText(I.liste.length)} · ${gb(I.liste.reduce((s, e) => s + e.groesse, 0))}`
      + ` · erkannte Kapitel: <b>${erkannt.length ? esc(erkannt.join(', ')) : 'keine'}</b>`;
    $('#im-frage').hidden = !P.wurzel.frage; $('#im-frage').classList.toggle('offen', P.offen);
    if (P.wurzel.frage) $('#im-frage').innerHTML = wurzelHtml(P);
    $('#im-warnung').hidden = !erkannt.length;
    const je = P.oberste.map(() => []), lose = [];
    for (const e of I.liste) (e.plan && e.plan.oben !== undefined ? je[e.plan.oben] : lose).push(e);
    const zeile = (name, z, l) => { const c = zahlen(l); return `<tr><td class="qm-voll" data-label="Ordner"><span class="qm-name">${esc(name)}</span></td><td data-label="Zuordnung" class="qm-im-wahl">${z}</td>`
      + `<td class="qm-zahl" data-label="Dateien">${Q.zahl(c.n)}<span class="qm-sub">${gb(c.b)}</span></td><td class="qm-zahl" data-label="neu">${Q.zahl(c.neu)}</td><td class="qm-zahl" data-label="schon da">${Q.zahl(c.vorhanden)}</td><td class="qm-zahl" data-label="übersprungen">${Q.zahl(c.weg)}</td></tr>`; };
    $('#im-oberste').innerHTML = `<table class="qm-tabelle qm-karten qm-im-tabelle"><thead><tr><th>Oberster Ordner</th><th>Zuordnung</th><th class="qm-zahl">Dateien</th><th class="qm-zahl">neu</th><th class="qm-zahl">schon da</th><th class="qm-zahl">übersprungen</th></tr></thead><tbody>`
      + P.oberste.map((z, i) => zeile(z.name, wahlHtml(z), je[i])).join('') + (lose.length ? zeile('lose Dateien', '<b>Eingang</b>', lose) : '') + '</tbody></table>';
    const frei = freigabenHtml(P);
    $('#im-freigaben').hidden = !frei; $('#im-freigaben').innerHTML = frei;
    const c = zahlen(I.liste);
    $('#im-zahlen').innerHTML = [['Dateien', c.n], ['neu', c.neu], ['schon abgelegt', c.vorhanden], ['übersprungen', c.weg], ['neue Ordner', P.neu.length], ['neue Bereiche', Object.keys(P.bereiche || {}).length]]
      .concat(L ? [['fertig', c.fertig], ['Fehler', c.fehler]] : []).map(([n, w]) => `<div><b>${Q.zahl(w)}</b><span>${esc(n)}</span></div>`).join('');
    const gruppe = (g) => I.liste.filter((e) => status(e).gruppe === g).length;
    $('#im-filter').innerHTML = FILTER.map(([k, n]) => { const z = k ? gruppe(k) : I.liste.length; return k && !z && I.filter !== k ? '' : `<button type="button" data-im-filter="${k}" aria-pressed="${I.filter === k}">${esc(n)} <b>${Q.zahl(z)}</b></button>`; }).join('');
    listeZeichnen();
    const offen = I.liste.filter((e) => status(e).hoch).length;
    $('#im-los').hidden = !!L; $('#im-los').disabled = !offen || P.offen;
    $('#im-los').textContent = offen === 1 ? '1 Datei importieren' : `${Q.zahl(offen)} Dateien importieren`;
    $('#im-stopp').hidden = !L || L.ende; $('#im-csv').hidden = !L || !L.ende;
    $('#im-fortschritt').hidden = !L; $('#im-stand').hidden = !L;
  }
  function dateiZeile(e) {
    const s = status(e);
    return `<tr><td class="qm-voll" data-label="Datei"><span class="qm-name">${esc(e.name)}</span><span class="qm-sub">${esc(e.pfad || '—')} · ${esc(Q.groesseText(e.groesse))}</span></td>`
      + `<td data-label="Ziel">${esc(zielText(e) || '—')}${e.plan && e.plan.pfad && e.plan.ziel !== 'eingang' ? `<span class="qm-sub">${esc(e.plan.pfad.split('/').join(' / '))}</span>` : ''}</td>`
      + `<td data-label="Status" class="qm-sa-status">${chip(s.text + (e.grund ? ` · ${e.grund}` : '') + (e.status === 'laeuft' && e.empfangen ? ` ${Math.round(100 * e.empfangen / e.groesse)} %` : ''), s.farbe)}</td></tr>`;
  }
  function listeZeichnen() {
    const l = I.liste.filter((e) => !I.filter || status(e).gruppe === I.filter);
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
  /* So viele fertige Uploads passen in ein Bündel: Zahl, Bytes und Word/Excel-Nachträge (Lenkung unter der Sperre) – Grenzen vom Server */
  function buendelZahl(l) {
    const a = S.d.ablage;
    let n = 0, b = 0, lk = 0;
    for (const e of l) {
      const o = e.plan.status === 'nachtragen' && a.office.includes((e.name.split('.').pop() || '').toLowerCase()) ? e.groesse : 0;
      if (n && (n >= a.buendel || b + e.groesse > a.buendelBytes || (o && lk + o > a.lenkungBytes))) break;
      n++; b += e.groesse; lk += o;
    }
    return n;
  }
  async function eintragenJetzt(alle) {
    const L = I.lauf;
    while (L.fertig.length && (alle || buendelZahl(L.fertig) < L.fertig.length || L.fertig.length >= S.d.ablage.buendel)) {
      const teil = L.fertig.splice(0, buendelZahl(L.fertig));
      const r = await api('qs_import_eintragen', { ...angaben(), export: I.plan.export,
        uploads: teil.map((e) => ({ upload: e.upload, status: e.plan.status, ver: e.plan.ver || '', ohne: I.ohne.has(schluessel(e)) })) });
      if (r.status === 401) { L.abbrechen = true; L.anmelden = true; return; }
      for (const e of teil) {
        const x = r.status === 200 && r.data.ok ? r.data.uploads[e.upload] : { status: 'fehler', grund: fehlerText(r, 'Eintragen fehlgeschlagen') };
        e.status = { abgelegt: 'abgelegt', eingang: 'imEingang', vorhanden: 'vorhanden', verworfen: 'verworfen' }[x && x.status] || 'fehler';
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
      const r = await Q.dateiSenden(f, '', '', (pos) => { L.gesendet += pos - vorher.gesendet; vorher.gesendet = pos; e.empfangen = pos; }, { sammeln: true, herkunft: e.pfad });
      if (r.anmelden) { L.abbrechen = true; L.anmelden = true; return; }
      if (r.fehler) { e.status = 'fehler'; e.grund = r.fehler; L.erledigt++; continue; }
      e.status = 'hochgeladen'; e.upload = r.upload; L.fertig.push(e);
      await eintragen();
    }
  }
  async function starten() {
    if (I.lauf || !I.plan || I.plan.offen) return;
    $('#im-los').disabled = true;
    meldung('Neue Ordner und Bereiche werden angelegt …', true);
    if (!(await planen(true))) { $('#im-los').disabled = false; return; }
    wahlMerken();
    await Q.neuLaden();
    const warte = I.liste.filter((e) => status(e).hoch);
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
    const zeilen = [['Ordner', 'Datei', 'Größe (Bytes)', 'Ergebnis', 'Ziel', 'Grund'], ...I.liste.map((e) => [e.pfad, e.name, e.groesse, status(e).text, zielText(e), e.grund])];
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
  async function neuPlanen() {
    meldung('Plan wird erstellt …', true);
    if (await planen()) { wahlMerken(); meldung('', true); zeichnen(); }
  }
  const wahlAus = (wert, vorschlag) => (wert.startsWith('kapitel:') ? { art: 'kapitel', kapitel: wert.slice(8) } : wert === 'neu' ? { art: 'neu', ...vorschlag } : { art: wert });
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
  $('#im-frage').addEventListener('change', (ev) => {
    const el = ev.target;
    if (el.id === 'im-wurzel-wahl') I.wurzel = el.value ? wahlAus(el.value, I.plan.wurzel.bereichVorschlag) : {};
    else if (el.dataset.imWurzelNr !== undefined || el.dataset.imWurzelTitel !== undefined) I.wurzel = { ...I.wurzel, [el.dataset.imWurzelNr !== undefined ? 'kapitel' : 'titel']: el.value.trim() };
    else return;
    neuPlanen();
  });
  $('#im-oberste').addEventListener('change', (ev) => {
    const el = ev.target, name = el.dataset.imWahl ?? el.dataset.imNr ?? el.dataset.imTitel;
    if (name === undefined) return;
    const z = I.plan.oberste.find((x) => x.name === name);
    if (el.dataset.imWahl !== undefined) I.wahl[name] = wahlAus(el.value, z.bereichVorschlag);
    else I.wahl[name] = { ...I.wahl[name], [el.dataset.imNr !== undefined ? 'kapitel' : 'titel']: el.value.trim() };
    neuPlanen();
  });
  $('#im-freigaben').addEventListener('change', (ev) => {
    const el = ev.target;
    if (el.dataset.imFrei !== undefined) {
      const z = I.plan.oberste.find((x) => x.name === el.dataset.imFrei);
      I.freigaben[z.name] = { nachtragen: z.nachtragen, entwurf: z.entwurf, [el.dataset.imArt]: el.checked };
    } else if (el.dataset.imOhne !== undefined) { if (el.checked) I.ohne.delete(el.dataset.imOhne); else I.ohne.add(el.dataset.imOhne); }
    else return;
    neuPlanen();
  });
  $('#im-filter').addEventListener('click', (ev) => { const b = ev.target.closest('[data-im-filter]'); if (b) { I.filter = b.dataset.imFilter; zeichnen(); } });
  $('#im-form').addEventListener('submit', (ev) => { ev.preventDefault(); starten(); });
  $('#im-stopp').addEventListener('click', () => { if (I.lauf) { I.lauf.abbrechen = true; $('#im-stopp').disabled = true; meldung('Wird nach den laufenden Dateien angehalten …', true); } });
  $('#im-csv').addEventListener('click', berichtCsv);
  const laeuft = () => I.lauf && !I.lauf.ende;
  $$('#dlg-import [data-im-zu]').forEach((b) => b.addEventListener('click', () => { if (laeuft()) toast('Der Import läuft noch – „Abbrechen“ hält nach den laufenden Dateien an.', true); else $('#dlg-import').close(); }));
  $('#dlg-import').addEventListener('cancel', (ev) => { if (laeuft()) { ev.preventDefault(); toast('Der Import läuft noch – „Abbrechen“ hält nach den laufenden Dateien an.', true); } });

})();
