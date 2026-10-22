/* ==========================================================================
   Wochenangebot – Eingabebereich, Importzentrale (Verwaltung → Import, Roadmap 10b)
   Ein Ablauf für alle Importe: Importart wählen → Datei wählen → Vorschau → übernehmen → Ergebnis.
   Welche Importarten es gibt und wer sie nutzen darf, sagt der Server (Aktion import_arten, Registrierung beim
   Daten-Eigentümer). Die Datei liest der Leser des Eigentümers (window.WA.importLeser – aus admin.js bzw.
   admin-verwaltung.js, dieselben Leser wie beim Import an Ort und Stelle); hier wird nur einheitlich geprüft, ob Dateityp,
   Kodierung und Inhalt überhaupt passen. Vorschau und Übernahme macht der Server (import_pruefen, import_uebernehmen).
   Vertrag: docs/plattform/schnittstellen/import.md
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const { $, api, esc, icon, toast, plural, fmtInt, may, setView } = W;

  /* Nur für die Anzeige des Menüpunkts (die Rechte prüft der Server je Importart, GR-103): Rechte der registrierten
     Importarten. Der Test „importzentrale“ prüft, dass die Liste zu import_arten passt. */
  const RECHTE = ['kunden.bearbeiten', 'stammdaten.bearbeiten', 'bestand.importieren', 'preisverlauf.bearbeiten', 'angebot.bearbeiten'];
  W.importSichtbar = () => RECHTE.some((p) => may(p));

  const MAX_BYTES = 30 * 1024 * 1024;
  const ART_LABEL = { neu: 'Neu', geaendert: 'Geändert', entfaellt: 'Entfällt', fehler: 'Fehler' };
  const SCHRITTE = ['Importart', 'Datei', 'Vorschau', 'Ergebnis'];
  let arten = null;        // Importarten des Nutzers (Server)
  let lauf = null;         // { art, dateien, quelle, gelesen, optionen, vorschau, ergebnis, schritt, fehler, filter, busy }
  const view = () => $('#view-importe');

  /* ---------- Einheitliche Vorprüfung der Datei (Dateityp, Kodierung, leer) – vor dem Leser des Eigentümers ---------- */
  const endung = (name) => ((/\.([a-z0-9]+)$/i.exec(name) || [])[1] || '').toLowerCase();
  const istZip = (b) => b[0] === 0x50 && b[1] === 0x4b;
  const istOle = (b) => b[0] === 0xd0 && b[1] === 0xcf && b[2] === 0x11 && b[3] === 0xe0;
  const istBiff = (b) => b.length > 2 && [0x09, 0x0209, 0x0409, 0x0809].includes(b[0] | (b[1] << 8));
  function utf16(b) {
    if ((b[0] === 0xff && b[1] === 0xfe) || (b[0] === 0xfe && b[1] === 0xff)) return true;
    let nul = 0;
    for (let i = 0; i < b.length; i++) if (b[i] === 0) nul++;
    return b.length > 16 && nul / b.length > 0.2;
  }
  const typText = (art) => art.dateien.map((d) => '.' + d).join(', ');
  async function dateiPruefen(art, file) {
    const ext = endung(file.name);
    if (!art.dateien.includes(ext)) throw new Error(`Falsche Datei: „${file.name}“ – erwartet wird ${art.kodierung || typText(art)}.`);
    if (file.size === 0) throw new Error(`Die Datei „${file.name}“ ist leer.`);
    if (file.size > MAX_BYTES) throw new Error(`Die Datei „${file.name}“ ist größer als 30 MB.`);
    const kopf = new Uint8Array(await file.slice(0, 4096).arrayBuffer());
    if (ext === 'csv') {
      if (istZip(kopf) || istOle(kopf)) throw new Error(`Falsche Datei: „${file.name}“ ist eine Excel-Datei, erwartet wird CSV (${art.kodierung}). In Excel „Speichern unter → CSV (Trennzeichen-getrennt)“ wählen.`);
      if (utf16(kopf)) throw new Error(`Falsche Kodierung: „${file.name}“ ist als UTF-16 („Unicode-Text“) gespeichert. Erwartet: ${art.kodierung}. Bitte als „CSV (Trennzeichen-getrennt)“ oder „CSV UTF-8“ speichern.`);
      if (kopf.includes(0)) throw new Error(`Falsche Datei: „${file.name}“ ist keine Textdatei (CSV).`);
      const text = new TextDecoder('windows-1252').decode(await file.arrayBuffer());
      if (!/[^\s﻿ï»¿;"]/.test(text)) throw new Error(`Die Datei „${file.name}“ ist leer.`);
    } else if (ext === 'xls') {
      if (!istOle(kopf) && !istBiff(kopf) && !istZip(kopf)) throw new Error(`Falsche Datei: „${file.name}“ ist keine Excel-Datei (${art.kodierung}).`);
    } else if (!istZip(kopf)) {
      throw new Error(`Falsche Datei: „${file.name}“ ist keine Excel-Arbeitsmappe (${art.kodierung}). Ältere .xls-Dateien bitte in Excel als „Excel-Arbeitsmappe (.xlsx)“ speichern.`);
    }
  }

  /* ---------- Darstellung ---------- */
  function schritte(n) {
    return `<ol class="imp-schritte" aria-label="Ablauf">${SCHRITTE.map((s, i) => `<li${i === n ? ' aria-current="step"' : i < n ? ' class="fertig"' : ''}>${s}</li>`).join('')}</ol>`;
  }
  function renderListe() {
    const h = view();
    if (!arten.length) { h.innerHTML = '<div class="ed-empty"><h3>Keine Importe verfügbar</h3><p>Für Importe fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.</p></div>'; return; }
    h.innerHTML = `${schritte(0)}
      <p class="imp-intro">Alle Importe an einer Stelle. Gelesen und geprüft wird jede Datei vom Bereich, dem die Daten gehören – vor dem Übernehmen sehen Sie, was neu ist, was sich ändert, was entfällt und welche Zeilen fehlerhaft sind. Jede Übernahme steht im Protokoll.</p>
      <div class="imp-liste">${arten.map((a) => `
        <article class="imp-art" data-art="${esc(a.id)}">
          <h3><span>${esc(a.name)}</span><span class="imp-eig" title="Die Daten gehören zum Bereich ${esc(a.eigentuemerName)}">${esc(a.eigentuemerName)}</span></h3>
          <p>${esc(a.beschreibung)}</p>
          <p class="imp-typ">${esc(a.kodierung || typText(a))}${a.mehrere ? ' · mehrere Dateien möglich' : ''}${a.bestaetigung ? ' · Übernahme mit Passwortbestätigung' : ''}</p>
          <div class="imp-aktion">${!a.verfuegbar ? `<span class="st-warn">${a.wartung ? 'Pausiert: Wartungsarbeiten' : 'Nicht verfügbar'}</span>`
            : a.ablauf === 'editor' ? `<button type="button" class="btn sm" data-imp-editor="${esc(a.id)}">${icon('link', 'sm')}Im Angebotseditor öffnen</button>`
            : `<button type="button" class="btn sm primary" data-imp-waehlen="${esc(a.id)}">${icon('upload', 'sm')}${a.mehrere ? 'Dateien wählen' : 'Datei wählen'}</button>
               <input type="file" hidden data-imp-datei="${esc(a.id)}" accept="${esc(a.dateien.map((d) => '.' + d).join(','))}"${a.mehrere ? ' multiple' : ''}>`}</div>
        </article>`).join('')}</div>`;
  }

  function kopf(titel) {
    const l = lauf;
    const datei = l.dateien.length === 1 ? l.dateien[0].name : plural(l.dateien.length, 'Datei', 'Dateien');
    return `<div class="imp-kopf"><div><h2 id="imp-titel">${esc(l.art.name)} importieren</h2><p>${esc(datei)}${l.gelesen ? ` · ${plural(l.gelesen.zeilen, 'Eintrag', 'Einträge')} gelesen` : ''}${titel ? ' · ' + esc(titel) : ''}</p></div>
      <button type="button" class="btn sm ghost" data-imp="liste">${icon('undo', 'sm')}Alle Importe</button></div>`;
  }
  function optionenHTML() {
    const ops = lauf.art.optionen;
    if (!ops.length) return '';
    return `<div class="imp-optionen">${ops.map((o) => o.typ === 'datum'
      ? `<label class="fld sm"><span>${esc(o.label)}</span><input type="date" data-imp-opt="${esc(o.id)}" value="${esc(lauf.optionen[o.id] || '')}"${o.pflicht ? ' required' : ''}></label>`
      : `<label class="check"><input type="checkbox" data-imp-opt="${esc(o.id)}"${lauf.optionen[o.id] ? ' checked' : ''}> ${esc(o.label)}</label>`).join('')}</div>`;
  }
  /* Zeilen der Vorschau: Fehler aus dem Leser (Datei) + Ergebnis des Servers */
  function alleZeilen() {
    const lf = (lauf.gelesen.fehler || []).map((f) => ({ art: 'fehler', zeile: f.zeile ?? null, schluessel: f.schluessel || '', name: f.datei || '', text: f.text }));
    return lf.concat(lauf.vorschau.zeilen).sort((a, b) => (a.art === 'fehler' && b.art === 'fehler' ? (a.zeile ?? 1e9) - (b.zeile ?? 1e9) : 0));
  }
  function zahlen() {
    const z = { ...lauf.vorschau.zahlen };
    z.fehler += (lauf.gelesen.fehler || []).length;
    return z;
  }
  function zahlenHTML(z, ids) {
    return `<div class="imp-zahlen">${['neu', 'geaendert', 'entfaellt', 'fehler'].map((k) => `<div class="${k}${z[k] ? ' hat' : ''}"><span>${ART_LABEL[k]}</span><strong${ids ? ` id="imp-${k}"` : ''}>${fmtInt.format(z[k])}</strong></div>`).join('')}</div>
      <p class="imp-gleich">${fmtInt.format(z.unveraendert)} unverändert</p>`;
  }
  function zeilenHTML() {
    const alle = alleZeilen();
    const f = lauf.filter;
    const list = f === 'alle' ? alle : alle.filter((x) => x.art === f);
    const gekuerzt = lauf.vorschau.zeilenGesamt > lauf.vorschau.zeilen.length;
    const zaehl = (k) => alle.filter((x) => x.art === k).length;
    const seg = `<div class="seg txt imp-filter" role="group" aria-label="Zeilen filtern">${['alle', 'neu', 'geaendert', 'entfaellt', 'fehler'].map((k) => `<button type="button" data-imp-filter="${k}" aria-pressed="${f === k}">${k === 'alle' ? 'Alle' : ART_LABEL[k]}${k === 'alle' ? '' : ` ${zaehl(k)}`}</button>`).join('')}</div>`;
    if (!alle.length) return '';
    return `${seg}<div class="gcard"><table class="etab imp-tab"><thead><tr><th class="imp-z">Zeile</th><th class="imp-a">Änderung</th><th>Eintrag</th></tr></thead><tbody id="imp-zeilen">${list.length ? list.map((x) => `
        <tr data-imp-art="${x.art}"><td class="imp-z">${x.zeile != null ? fmtInt.format(x.zeile) : '–'}</td><td class="imp-a"><span class="imp-badge ${x.art}">${ART_LABEL[x.art]}</span></td>
        <td>${x.schluessel ? `<span class="imp-k">${esc(x.schluessel)}</span>` : ''}${esc(x.name)}${x.text ? `<div class="sub">${esc(x.text)}</div>` : ''}</td></tr>`).join('')
      : '<tr><td colspan="3" class="imp-leer">Keine Zeilen in dieser Auswahl.</td></tr>'}</tbody></table></div>
      ${gekuerzt ? `<p class="hint">Angezeigt werden die ersten ${fmtInt.format(lauf.vorschau.zeilen.length)} von ${fmtInt.format(lauf.vorschau.zeilenGesamt)} geänderten oder fehlerhaften Zeilen; die Zahlen oben zählen alle.</p>` : ''}`;
  }
  function hinweiseHTML(list) {
    return list.length ? `<ul class="issues imp-hinweise">${list.map((x) => `<li class="${x.stufe === 'warn' ? 'warn' : 'info'}"><span class="lvl">${x.stufe === 'warn' ? 'Prüfen' : 'Info'}</span><span>${esc(x.text)}</span></li>`).join('')}</ul>` : '';
  }
  function renderLauf() {
    const l = lauf, h = view();
    if (l.schritt === 'lesen' || (l.schritt === 'vorschau' && !l.vorschau)) {
      h.innerHTML = `${schritte(l.schritt === 'lesen' ? 1 : 2)}${kopf()}<div class="loading" role="status"><div class="spinner"></div>${l.schritt === 'lesen' ? 'Datei wird gelesen …' : 'Abgleich mit den gespeicherten Daten …'}</div>`;
      return;
    }
    if (l.schritt === 'fehler') {
      h.innerHTML = `${schritte(l.gelesen ? 2 : 1)}${kopf()}${l.gelesen ? optionenHTML() : ''}<div class="err-box" id="imp-fehler" role="alert">${esc(l.fehler)}</div>
        <p class="hint">Es wurde nichts übernommen.</p>
        <div class="imp-fuss"><button type="button" class="btn" data-imp="liste">Abbrechen</button><button type="button" class="btn primary" data-imp="andere">${icon('upload')}Andere Datei wählen</button></div>`;
      return;
    }
    if (l.schritt === 'fertig') {
      const z = { ...l.ergebnis.zahlen };
      z.fehler += (l.gelesen.fehler || []).length;
      const ziel = l.art.ansicht && l.art.ansicht !== 'importe' ? $('#vt-' + l.art.ansicht) : null;
      h.innerHTML = `${schritte(3)}${kopf()}
        <div class="imp-ergebnis" id="imp-ergebnis" role="status">
          <div class="sec-card ok"><span class="sec-dot"></span><div><strong>Import übernommen</strong><span>${esc([`${fmtInt.format(z.neu)} neu`, `${fmtInt.format(z.geaendert)} geändert`, `${fmtInt.format(z.entfaellt)} entfallen`, z.fehler ? `${fmtInt.format(z.fehler)} fehlerhafte Zeilen nicht übernommen` : ''].filter(Boolean).join(' · '))}</span>
            <em>Im Protokoll eingetragen${may('protokoll.sehen') ? ' (Verwaltung → Protokoll)' : ''}.</em></div></div>
          ${zahlenHTML(z, false)}
          <div class="imp-fuss">${ziel && !ziel.hidden ? `<button type="button" class="btn" data-imp="ansicht">${esc(ziel.textContent.trim())} öffnen</button>` : ''}<span class="sp"></span><button type="button" class="btn primary" data-imp="liste">Weiteren Import</button></div>
        </div>`;
      return;
    }
    // Vorschau
    const z = zahlen();
    const nix = !z.neu && !z.geaendert && !z.entfaellt;
    h.innerHTML = `${schritte(2)}${kopf()}${optionenHTML()}
      ${zahlenHTML(z, true)}
      ${hinweiseHTML((l.gelesen.hinweise || []).concat(l.vorschau.hinweise))}
      ${zeilenHTML()}
      <div class="imp-fuss">
        <p class="hint">${nix ? 'Keine Änderungen – die Daten sind bereits aktuell.' : `Übernommen werden die neuen, geänderten und entfallenden Einträge${z.fehler ? '; Zeilen mit Fehler werden übersprungen' : ''}.${l.art.bestaetigung ? ' Zum Übernehmen fragt der Eingabebereich nach Ihrem Passwort.' : ''}`}</p>
        <p class="kerr" id="imp-err" role="alert"></p>
        <button type="button" class="btn" data-imp="liste">Abbrechen</button><button type="button" class="btn" data-imp="andere">Andere Datei</button><span class="sp"></span>
        <button type="button" class="btn primary" id="imp-ok" data-imp="ok"${nix || l.busy ? ' disabled' : ''}>${icon('check')}Übernehmen</button>
      </div>`;
  }

  /* ---------- Ablauf ---------- */
  function datenAnfrage() {
    return { art: lauf.art.id, daten: lauf.gelesen.daten, quelle: lauf.quelle, optionen: lauf.optionen };
  }
  async function lesen() {
    const l = lauf;
    l.schritt = 'lesen'; l.gelesen = null; l.vorschau = null; renderLauf();
    try {
      for (const f of l.dateien) await dateiPruefen(l.art, f);
      const leser = W.importLeser && W.importLeser[l.art.id];
      if (!leser) throw new Error('Für diese Importart ist im Eingabebereich kein Leser geladen. Bitte die Seite neu laden.');
      l.gelesen = await leser.lesen(l.dateien);
      for (const o of l.art.optionen) if (!(o.id in l.optionen)) l.optionen[o.id] = l.gelesen.optionen && o.id in l.gelesen.optionen ? l.gelesen.optionen[o.id] : (o.standard ?? (o.typ === 'schalter' ? false : ''));
    } catch (ex) {
      if (lauf !== l) return;
      l.schritt = 'fehler'; l.fehler = ex.message || String(ex); renderLauf(); return;
    }
    if (lauf === l) await pruefen();
  }
  async function pruefen(nochmal = true) {
    const l = lauf;
    const fehlt = l.art.optionen.find((o) => o.pflicht && !l.optionen[o.id]);
    l.schritt = 'vorschau'; l.vorschau = null;
    if (fehlt) { l.schritt = 'fehler'; l.fehler = `Bitte „${fehlt.label}“ angeben.`; renderLauf(); return; }
    renderLauf();
    try {
      const r = await api('import_pruefen', { body: datenAnfrage() });
      if (lauf !== l) return;
      l.vorschau = r; l.filter = 'alle';
    } catch (ex) {
      if (lauf !== l) return;
      if (ex.status === 409 && nochmal) { await lesen(); return; }   // Stand hat sich geändert (z. B. Stammdaten): neu lesen
      l.schritt = 'fehler'; l.fehler = ex.message; renderLauf(); return;
    }
    renderLauf();
    view().scrollIntoView({ block: 'start' });
  }
  async function uebernehmen(btn) {
    const l = lauf;
    l.busy = true; btn.disabled = true;
    try {
      const r = await api('import_uebernehmen', { body: { ...datenAnfrage(), stand: l.vorschau.stand } });
      if (lauf !== l) return;
      l.ergebnis = r; l.schritt = 'fertig';
      const z = r.zahlen;
      toast(`${l.art.name}: ${fmtInt.format(z.neu)} neu, ${fmtInt.format(z.geaendert)} geändert, ${fmtInt.format(z.entfaellt)} entfallen.`, 5000);
      try { await W.importLeser[l.art.id].nachher?.(); } catch { /* Ansicht lädt beim nächsten Öffnen neu */ }
      renderLauf();
    } catch (ex) {
      l.busy = false;
      if (lauf !== l) return;
      if (ex.status === 409) { toast(ex.message + ' Die Vorschau wurde neu geladen.', 7000); await lesen(); return; }
      if (ex.wartung || ex.status === 401) return;
      btn.disabled = false;
      const e = $('#imp-err'); if (e) e.textContent = ex.message;
    }
  }
  function starten(art, files) {
    if (!files.length) return;
    lauf = { art, dateien: art.mehrere ? files : files.slice(0, 1), quelle: files.length === 1 ? files[0].name : files.map((f) => f.name).join(', ').slice(0, 200),
      optionen: {}, gelesen: null, vorschau: null, ergebnis: null, schritt: 'lesen', filter: 'alle', busy: false };
    lesen();
  }
  function zurListe() { lauf = null; render(); }

  async function render() {
    const h = view();
    if (lauf) { renderLauf(); return; }
    if (!arten) h.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Importe werden geladen …</div>';
    try { arten = (await api('import_arten')).arten; } catch (e) { if (!e.wartung) h.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    if (!lauf) renderListe();
  }

  const host = view();
  host.addEventListener('click', (e) => {
    const w = e.target.closest('[data-imp-waehlen]');
    if (w) { host.querySelector(`input[data-imp-datei="${w.dataset.impWaehlen}"]`).click(); return; }
    const ed = e.target.closest('[data-imp-editor]');
    if (ed) {
      const a = arten.find((x) => x.id === ed.dataset.impEditor);
      setView(a.ansicht);
      if (a.id === 'angebot_excel') { const b = $('#btn-import'); if (b && !b.hidden) b.click(); }
      else toast('Preise importieren: Knopf „Preise importieren“ unter den Angeboten.', 5000);
      return;
    }
    const fb = e.target.closest('[data-imp-filter]');
    if (fb && lauf) { lauf.filter = fb.dataset.impFilter; renderLauf(); return; }
    const b = e.target.closest('[data-imp]');
    if (!b) return;
    const act = b.dataset.imp;
    if (act === 'liste') { zurListe(); return; }
    if (act === 'andere' && lauf) { const art = lauf.art; lauf = null; renderListe(); host.querySelector(`input[data-imp-datei="${art.id}"]`)?.click(); return; }
    if (act === 'ok' && lauf && lauf.vorschau) { uebernehmen(b); return; }
    if (act === 'ansicht' && lauf) { const v = lauf.art.ansicht; lauf = null; setView(v); }
  });
  host.addEventListener('change', (e) => {
    const inp = e.target.closest('input[data-imp-datei]');
    if (inp) {
      const files = [...inp.files]; inp.value = '';
      const art = arten.find((x) => x.id === inp.dataset.impDatei);
      if (art && files.length) starten(art, files);
      return;
    }
    const o = e.target.closest('[data-imp-opt]');
    if (o && lauf && lauf.gelesen) {
      lauf.optionen[o.dataset.impOpt] = o.type === 'checkbox' ? o.checked : o.value;
      pruefen();
    }
  });

  W.views.importe = render;   // Ansicht „importe“ (nicht „import“: #vt-import ist der Importknopf der Vertreter)
})();
