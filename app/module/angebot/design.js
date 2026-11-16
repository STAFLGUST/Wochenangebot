/* STAFL-Plattform · Angebot · Fenster „Design“ (Inhaber 16.11.2026): Aufbau und Raster eines Angebots für Druck/PDF und
   Kundenseite. Geöffnet über den Knopf „Design“ in „Angebot bearbeiten“ (gewähltes Angebot, Recht angebot.bearbeiten) und im
   Einzelangebot (einzelangebote.bearbeiten). Zwei Reiter:
   – „Dieses Angebot“: Design wählen (Standard oder eine Vorlage), „Anpassen“ öffnet dieselbe Bearbeitung wie bei Vorlagen,
     „Auf Vorlage zurücksetzen“ verwirft die Anpassung; „Speichern“ → angebot_design_setzen (der Server behält nur Abweichungen).
   – „Vorlagen“ (ändern nur mit angebote.verwalten): Liste mit Nutzung, neu, bearbeiten/umbenennen, kopieren, löschen (genutzte
     Vorlagen lehnt der Server mit den Namen der Angebote ab) → angebot_design_save / angebot_design_loeschen.
   Bearbeitung: Format (quer/hoch), Spalten 1–4, Abschnitte als Liste (↑/↓, entfernen): Gruppen-Abschnitt mit Überschrift,
   Spalten und Bereichen/Gruppen des Angebots (leer = alle übrigen Gruppen), Text-Abschnitt mit Überschrift und Text.
   Daneben die Live-Vorschau: die Angebotsseite im Rahmen (?vorschau=1&eingebettet=1&designvorschau=druck|web, assets/frontend.js),
   das ungespeicherte Design per postMessage – Druckseiten oder Kundenansicht, gesetzt mit dem gewählten Angebot.
   Wird von admin/index.html nach admin.js geladen; Daten des Editors über WA.angebot.design (admin.js). */
(function () {
  'use strict';
  const W = window.WA;
  const btn = document.getElementById('btn-design');
  const dlg = document.getElementById('dlg-design');
  const body = document.getElementById('design-body');
  if (!W || !btn || !dlg || !body || !W.angebot || !W.angebot.design) return;
  const { api, esc, icon, toast, confirmBox } = W;
  const D = W.angebot.design;
  const kopie = (x) => JSON.parse(JSON.stringify(x));
  let z = null;   // Zustand des Fensters (oeffnen)

  const basis = (vid) => { const v = z.daten.vorlagen.find((x) => x.id === vid); return kopie(v ? { raster: v.raster, abschnitte: v.abschnitte } : z.daten.standard); };
  const wirksam = (w) => { const b = basis(w ? w.vorlage : ''), a = (w && w.anpassung) || {}; return { raster: { ...b.raster, ...(a.raster || {}) }, abschnitte: a.abschnitte || b.abschnitte }; };
  const gleich = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  const rasterText = (d) => `${d.raster.spalten} ${d.raster.spalten === 1 ? 'Spalte' : 'Spalten'} · ${d.raster.format === 'hoch' ? 'Hochformat' : 'Querformat'} · ${d.abschnitte.length || 'ohne'} ${d.abschnitte.length === 1 ? 'Abschnitt' : 'Abschnitte'}`;
  /* das Design, das gerade bearbeitet bzw. angezeigt wird */
  const aktuell = () => (z.reiter === 'vorlagen' && z.vorlage ? z.vorlage : z.entwurf);

  /* ---------- Bearbeitung: Raster und Abschnitte (Angebot und Vorlage) ---------- */
  function refHTML(r, i, j) {
    const typ = 'bereich' in r ? 'bereich' : 'gruppe', name = r[typ];
    const da = typ === 'bereich' ? z.namen.bereiche.some((b) => b.toLowerCase() === name.toLowerCase()) : z.namen.gruppen.some((g) => g.name.toLowerCase() === name.toLowerCase());
    return `<li class="ds-ref${da ? '' : ' fehlt'}"><span><b>${typ === 'bereich' ? 'Bereich' : 'Gruppe'}</b> ${esc(name)}${da ? '' : ' <em>(nicht in diesem Angebot)</em>'}</span>
      <button type="button" class="ibtn" data-ds="ref-weg" data-i="${i}" data-j="${j}" aria-label="${typ === 'bereich' ? 'Bereich' : 'Gruppe'} „${esc(name)}“ entfernen">${icon('x', 'sm')}</button></li>`;
  }
  function abschnittHTML(a, i, n) {
    const pfeile = `<span class="ds-btns"><button type="button" class="ibtn" data-ds="hoch" data-i="${i}" aria-label="Abschnitt ${i + 1} nach oben"${i === 0 ? ' disabled' : ''}>${icon('up')}</button>
      <button type="button" class="ibtn" data-ds="runter" data-i="${i}" aria-label="Abschnitt ${i + 1} nach unten"${i === n - 1 ? ' disabled' : ''}>${icon('down')}</button>
      <button type="button" class="ibtn danger" data-ds="weg" data-i="${i}" aria-label="Abschnitt ${i + 1} entfernen">${icon('trash')}</button></span>`;
    const titel = `<input class="ds-titel" data-f="titel" data-i="${i}" maxlength="80" value="${esc(a.titel || '')}" placeholder="${a.art === 'text' ? 'Überschrift' : 'Überschrift (optional)'}" aria-label="Überschrift von Abschnitt ${i + 1}">`;
    if (a.art === 'text') {
      return `<li class="ds-ab text" data-i="${i}"><div class="ds-ab-kopf"><span class="ds-art">Text</span>${titel}${pfeile}</div>
        <textarea data-f="text" data-i="${i}" rows="3" maxlength="1000" placeholder="Text, z. B. Hinweis zur Lieferung" aria-label="Text von Abschnitt ${i + 1}">${esc(a.text || '')}</textarea></li>`;
    }
    const vergeben = new Set((a.inhalt || []).map((r) => ('bereich' in r ? 'b:' : 'g:') + Object.values(r)[0].toLowerCase()));
    const opt = (wert, txt) => `<option value="${esc(wert)}">${esc(txt)}</option>`;
    const neu = `<select class="ds-neu" data-f="neu" data-i="${i}" aria-label="Bereich oder Gruppe zu Abschnitt ${i + 1} hinzufügen"><option value="">+ Bereich oder Gruppe …</option>
      ${z.namen.bereiche.length ? `<optgroup label="Bereiche">${z.namen.bereiche.filter((b) => !vergeben.has('b:' + b.toLowerCase())).map((b) => opt('b:' + b, b)).join('')}</optgroup>` : ''}
      <optgroup label="Gruppen">${z.namen.gruppen.filter((g) => !vergeben.has('g:' + g.name.toLowerCase())).map((g) => opt('g:' + g.name, g.name + (g.bereich ? ' – ' + g.bereich : ''))).join('')}</optgroup></select>`;
    const sp = `<label class="ds-sp"><span>Spalten</span><select data-f="spalten" data-i="${i}" aria-label="Spalten von Abschnitt ${i + 1}"><option value="">wie Raster</option>${[1, 2, 3, 4].map((k) => `<option value="${k}"${a.spalten === k ? ' selected' : ''}>${k}</option>`).join('')}</select></label>`;
    return `<li class="ds-ab" data-i="${i}"><div class="ds-ab-kopf"><span class="ds-art">Gruppen</span>${titel}${pfeile}</div>
      <div class="ds-ab-zeile">${sp}${neu}</div>
      ${(a.inhalt || []).length ? `<ul class="ds-refs">${a.inhalt.map((r, j) => refHTML(r, i, j)).join('')}</ul>` : '<p class="ds-rest">Alle übrigen Gruppen des Angebots in Angebotsreihenfolge.</p>'}</li>`;
  }
  function editorHTML(d, ro) {
    if (ro) return `<p class="ds-zus">${esc(rasterText(d))}</p>`;
    return `<div class="ds-raster"><div class="fld"><span>Format</span><div class="ds-seg" role="radiogroup" aria-label="Format">${['quer', 'hoch'].map((f) => `<button type="button" role="radio" data-ds="format" data-wert="${f}" aria-checked="${d.raster.format === f}">${f === 'quer' ? 'Quer' : 'Hoch'}</button>`).join('')}</div></div>
        <div class="fld"><span>Spalten</span><div class="ds-seg" role="radiogroup" aria-label="Spalten">${[1, 2, 3, 4].map((k) => `<button type="button" role="radio" data-ds="spalten" data-wert="${k}" aria-checked="${d.raster.spalten === k}">${k}</button>`).join('')}</div></div></div>
      <h3 class="ds-h">Abschnitte</h3>
      ${d.abschnitte.length ? `<ol class="ds-liste">${d.abschnitte.map((a, i) => abschnittHTML(a, i, d.abschnitte.length)).join('')}</ol>`
        : '<p class="ds-rest">Keine Abschnitte: alle Gruppen in Angebotsreihenfolge, wie bisher.</p>'}
      <div class="ds-plus"><button type="button" class="btn" data-ds="neu-gruppen">${icon('plus', 'sm')}Gruppen-Abschnitt</button><button type="button" class="btn" data-ds="neu-text">${icon('plus', 'sm')}Text-Abschnitt</button></div>
      <p class="hint">Bereiche und Gruppen gelten über ihren Namen. Gruppen ohne Abschnitt stehen im ersten Abschnitt ohne Inhalt, sonst am Ende unter „Weitere Artikel“ – kein Artikel fehlt.</p>`;
  }

  /* ---------- Reiter ---------- */
  function angebotHTML() {
    const w = z.daten, ro = !w.darfWahl, angepasst = z.angepasst;
    return `<label class="fld"><span>Design</span><select id="ds-wahl"${ro ? ' disabled' : ''}><option value="">Standard (3 Spalten, quer)</option>${w.vorlagen.map((v) => `<option value="${esc(v.id)}"${v.id === z.wahl ? ' selected' : ''}>${esc(v.name)}</option>`).join('')}</select></label>
      <p class="ds-zus">${esc(rasterText(z.entwurf))}${angepasst && !gleich(z.entwurf, basis(z.wahl)) ? ' · <span class="ds-angepasst">angepasst</span>' : ''}</p>
      ${ro ? '<p class="hint">Sie dürfen das Design dieses Angebots nicht ändern.</p>' : `<div class="ds-knoepfe"><button type="button" class="btn" id="ds-anpassen" aria-expanded="${angepasst}"${angepasst ? ' disabled' : ''}>${icon('aufbau', 'sm')}Anpassen</button>
        <button type="button" class="btn ghost" id="ds-zuruecksetzen"${angepasst ? '' : ' disabled'}>${icon('undo', 'sm')}Auf Vorlage zurücksetzen</button></div>`}
      ${angepasst && !ro ? `<div class="ds-editor">${editorHTML(z.entwurf, false)}</div>` : ''}`;
  }
  function vorlagenHTML() {
    const w = z.daten, darf = w.darfVorlagen;
    if (z.vorlage) {
      return `<label class="fld"><span>Name der Vorlage</span><input id="ds-name" maxlength="60" value="${esc(z.vorlage.name)}" autocomplete="off"></label>
        <div class="ds-editor">${editorHTML(z.vorlage, false)}</div>`;
    }
    return `${darf ? `<div class="ds-knoepfe"><button type="button" class="btn" data-ds="v-neu">${icon('plus', 'sm')}Neue Vorlage</button></div>` : '<p class="hint">Vorlagen anlegen und ändern dürfen Mitarbeiter mit dem Recht „Kundenangebote anlegen“.</p>'}
      ${w.vorlagen.length ? `<ul class="ds-vorlagen">${w.vorlagen.map((v) => `<li class="ds-v" data-id="${esc(v.id)}"><div class="ds-v-t"><b>${esc(v.name)}</b><small>${esc(rasterText(v))}</small>
          <small>${v.genutzt.length ? 'genutzt: ' + esc(v.genutzt.join(', ')) : 'nicht genutzt'}</small></div>
          ${darf ? `<span class="ds-btns"><button type="button" class="ibtn" data-ds="v-bearbeiten" aria-label="„${esc(v.name)}“ bearbeiten oder umbenennen" title="Bearbeiten / umbenennen">${icon('aufbau')}</button>
          <button type="button" class="ibtn" data-ds="v-kopieren" aria-label="„${esc(v.name)}“ kopieren" title="Kopieren">${icon('copy')}</button>
          <button type="button" class="ibtn danger" data-ds="v-loeschen" aria-label="„${esc(v.name)}“ löschen" title="Löschen">${icon('trash')}</button></span>` : ''}</li>`).join('')}</ul>`
        : '<p class="ds-rest">Noch keine Vorlagen. Eine Vorlage legt Spalten, Format und Abschnitte fest und lässt sich für viele Angebote wählen.</p>'}`;
  }
  /* Gerüst einmal beim Öffnen (der Rahmen der Vorschau bleibt stehen – neu eingehängt würde er neu laden), danach nur die
     linke Seite und die Fußleiste neu */
  function geruest() {
    body.innerHTML = `<div class="dlg-head"><div><h2 id="ds-titel">${icon('design')}Design · ${esc(z.name)}</h2><p>Aufbau für Druck/PDF und Kundenseite. Wirkt sofort nach dem Speichern.</p></div>
        <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body ds-body"><div class="ds-links" id="ds-links"></div>
        <div class="ds-rechts"><div class="ds-vk"><div class="ds-seg" role="radiogroup" aria-label="Vorschau">${['druck', 'web'].map((a) => `<button type="button" role="radio" data-ds="ansicht" data-wert="${a}" aria-checked="${z.ansicht === a}">${a === 'druck' ? 'Druck' : 'Kundenseite'}</button>`).join('')}</div>
          <span class="ds-info" id="ds-info" aria-live="polite"></span></div></div></div>
      <div class="dlg-foot" id="ds-fuss"></div>`;
    body.querySelector('.ds-rechts').append(rahmen());
  }
  function zeichnen(fokus) {
    const links = body.querySelector('#ds-links'), y = links.scrollTop, vr = z.reiter === 'vorlagen';
    links.innerHTML = `<div class="ds-reiter" role="tablist"><button type="button" role="tab" id="ds-r-angebot" aria-selected="${!vr}" data-ds="reiter" data-wert="angebot">${z.einzel ? 'Dieses Einzelangebot' : 'Dieses Angebot'}</button>
        <button type="button" role="tab" id="ds-r-vorlagen" aria-selected="${vr}" data-ds="reiter" data-wert="vorlagen">Vorlagen</button></div>
      <div role="tabpanel" aria-labelledby="ds-r-${vr ? 'vorlagen' : 'angebot'}">${vr ? vorlagenHTML() : angebotHTML()}</div>
      <p class="form-err" id="ds-err" role="alert">${esc(z.fehler || '')}</p>`;
    body.querySelector('#ds-fuss').innerHTML = `<span class="ds-stand" id="ds-stand"></span>` + (vr ? (z.vorlage ? `<button type="button" class="btn" data-ds="v-zurueck">Zurück zur Liste</button><button type="button" class="btn primary" data-ds="v-speichern">${icon('check')}Vorlage speichern</button>`
      : '<button type="button" class="btn" data-close>Schließen</button>')
      : `<button type="button" class="btn" data-close>Abbrechen</button>${z.daten.darfWahl ? `<button type="button" class="btn primary" data-ds="speichern">${icon('check')}Speichern</button>` : ''}`);
    links.scrollTop = y;
    if (fokus) { const el = body.querySelector(fokus); if (el) el.focus(); }
    standZeigen();
  }
  function standZeigen() {
    const geaendert = z.reiter === 'vorlagen' ? !!z.vorlage && !gleich(z.vorlage, z.vorlageStart) : !gleich([z.wahl, z.angepasst ? z.entwurf : null], z.start);
    if (geaendert) dlg.dataset.geaendert = '1'; else { delete dlg.dataset.geaendert; delete dlg.dataset.warnung; }
    const el = body.querySelector('#ds-stand');
    if (el) { el.textContent = geaendert ? 'Geändert – noch nicht gespeichert' : ''; el.classList.toggle('geaendert', geaendert); }
  }

  /* ---------- Vorschau (Angebotsseite im Rahmen) ---------- */
  let frame = null, bereit = false, uhr = 0;
  function rahmen() {
    if (!frame) {
      frame = document.createElement('iframe');
      frame.className = 'ds-vorschau';
      frame.title = 'Vorschau des Designs';
      bereit = false;
      frame.src = D.adresse(z.angebot) + '&designvorschau=' + z.ansicht;
    }
    return frame;
  }
  function vorschau(sofort) {
    clearTimeout(uhr);
    const senden = () => { if (frame && bereit && frame.contentWindow) frame.contentWindow.postMessage({ wa: 'design', design: aktuell(), ansicht: z.ansicht }, location.origin); };
    if (sofort) senden(); else uhr = setTimeout(senden, 300);
    standZeigen();
  }
  window.addEventListener('message', (e) => {
    if (e.origin !== location.origin || !frame || e.source !== frame.contentWindow || !e.data || e.data.wa !== 'design') return;
    if (e.data.stand === 'bereit') { bereit = true; vorschau(true); return; }
    const info = body.querySelector('#ds-info'), m = e.data;
    if (info) info.textContent = m.ansicht === 'druck' && m.spalten ? `${m.spalten} ${m.spalten === 1 ? 'Spalte' : 'Spalten'} · ${m.format === 'hoch' ? 'hoch' : 'quer'} · ${m.seiten} ${m.seiten === 1 ? 'Seite' : 'Seiten'}` : m.ansicht === 'web' ? 'wie für Kunden' : '';
  });

  /* ---------- Öffnen, Laden, Speichern ---------- */
  const laden = (oid) => api('angebot_designs&angebot=' + encodeURIComponent(oid));
  async function oeffnen(opt) {
    const o = opt || D.angebot();
    if (!o) return;
    let daten;
    try { daten = await laden(o.angebot); } catch (e) { if (e.status !== 401) toast(e.message || 'Das Design konnte nicht geladen werden.', 6000); return; }
    if (frame) { frame.remove(); frame = null; }
    z = { angebot: o.angebot, name: o.name, einzel: !!o.einzel, daten, reiter: 'angebot', ansicht: z ? z.ansicht : 'druck', vorlage: null, fehler: '',
      namen: o.einzel ? { bereiche: [], gruppen: [] } : D.namen() };
    uebernehmen(daten.wahl);
    geruest();
    zeichnen();
    dlg.showModal();
    (body.querySelector('#ds-wahl:not(:disabled)') || body.querySelector('[data-close]')).focus();
  }
  /* gespeichertes Design des Angebots in den Zustand übernehmen */
  function uebernehmen(w) {
    z.wahl = w && z.daten.vorlagen.some((v) => v.id === w.vorlage) ? w.vorlage : '';
    z.angepasst = !!(w && w.anpassung);
    z.entwurf = wirksam(w && z.wahl === w.vorlage ? w : null);
    z.start = [z.wahl, z.angepasst ? kopie(z.entwurf) : null];
  }
  async function neuLaden(meldung) {
    z.daten = await laden(z.angebot);
    z.fehler = meldung || '';
  }
  async function speichern(knopf) {
    knopf.disabled = true;
    try {
      const r = await api('angebot_design_setzen', { body: { angebot: z.angebot, design: { vorlage: z.wahl, anpassung: z.angepasst ? { raster: z.entwurf.raster, abschnitte: z.entwurf.abschnitte } : null } } });
      uebernehmen(r.wahl);
      delete dlg.dataset.geaendert;
      dlg.close();
      toast(`Design von „${z.name}“ gespeichert: ${r.wahl ? (z.daten.vorlagen.find((v) => v.id === r.wahl.vorlage) || { name: 'Standard' }).name + (r.wahl.anpassung ? ' (angepasst)' : '') : 'Standard'}.`, 5000);
    } catch (e) {
      knopf.disabled = false;
      if (e.status !== 401) fehler(e.message || 'Nicht gespeichert.');
    }
  }
  async function vorlageSpeichern(knopf) {
    const v = z.vorlage;
    v.name = (body.querySelector('#ds-name') || {}).value || v.name;
    if (v.name.trim().length < 2) { fehler('Bitte einen Namen für die Vorlage angeben (mindestens 2 Zeichen).'); return; }
    knopf.disabled = true;
    try {
      await api('angebot_design_save', { body: { rev: z.daten.rev, id: v.id || '', name: v.name, raster: v.raster, abschnitte: v.abschnitte } });
      await neuLaden();
      z.vorlage = null;
      if (!z.angepasst) z.entwurf = basis(z.wahl);   // die gewählte Vorlage kann sich gerade geändert haben
      zeichnen();
      vorschau(true);
      toast(`Vorlage „${v.name.trim()}“ gespeichert.`, 4000);
    } catch (e) {
      knopf.disabled = false;
      if (e.status === 409) { await neuLaden(e.message); z.vorlage = null; zeichnen(); return; }
      if (e.status !== 401) fehler(e.message || 'Nicht gespeichert.');
    }
  }
  async function vorlageLoeschen(v) {
    if (!(await confirmBox('Vorlage löschen?', `„${esc(v.name)}“ wird gelöscht. Angebote nutzen sie nicht mehr – das prüft der Server.`, 'Löschen', true))) return;
    try {
      await api('angebot_design_loeschen', { body: { rev: z.daten.rev, id: v.id } });
      await neuLaden();
      toast(`Vorlage „${v.name}“ gelöscht.`, 4000);
    } catch (e) {
      if (e.status === 401) return;
      await neuLaden(e.message || 'Nicht gelöscht.');
    }
    zeichnen();
  }
  function fehler(t) { z.fehler = t; const el = body.querySelector('#ds-err'); if (el) el.textContent = t; }
  function freierName(basisName) {
    const belegt = (n) => z.daten.vorlagen.some((v) => v.name.toLowerCase() === n.toLowerCase());
    const b = ('Kopie von ' + basisName).slice(0, 60);
    if (!belegt(b)) return b;
    for (let k = 2; ; k++) { const n = `${b.slice(0, 54)} (${k})`; if (!belegt(n)) return n; }
  }

  /* ---------- Bedienung ---------- */
  body.addEventListener('click', async (e) => {
    const t = e.target.closest('[data-ds], [data-close], #ds-anpassen, #ds-zuruecksetzen');
    if (!t || !z) return;
    if (t.matches('[data-close]')) { dlg.close(); return; }
    if (t.id === 'ds-anpassen') { z.angepasst = true; zeichnen('.ds-editor [data-ds="format"][aria-checked="true"]'); vorschau(); return; }
    if (t.id === 'ds-zuruecksetzen') { z.angepasst = false; z.entwurf = basis(z.wahl); zeichnen('#ds-anpassen'); vorschau(); return; }
    const a = t.dataset.ds, i = +t.dataset.i, d = aktuell();
    if (a === 'reiter') { z.reiter = t.dataset.wert; z.vorlage = null; z.fehler = ''; zeichnen('#ds-r-' + z.reiter); vorschau(true); return; }
    if (a === 'ansicht') { z.ansicht = t.dataset.wert; for (const b of body.querySelectorAll('[data-ds="ansicht"]')) b.setAttribute('aria-checked', String(b === t)); vorschau(true); return; }
    if (a === 'speichern') { speichern(t); return; }
    if (a === 'v-neu') { z.vorlage = { id: '', name: '', ...kopie(z.daten.standard) }; z.vorlageStart = kopie(z.vorlage); zeichnen('#ds-name'); vorschau(); return; }
    if (a === 'v-zurueck') { z.vorlage = null; z.fehler = ''; zeichnen(); vorschau(true); return; }
    if (a === 'v-speichern') { vorlageSpeichern(t); return; }
    const vid = t.closest('.ds-v') && t.closest('.ds-v').dataset.id, v = vid && z.daten.vorlagen.find((x) => x.id === vid);
    if (a === 'v-bearbeiten' && v) { z.vorlage = kopie({ id: v.id, name: v.name, raster: v.raster, abschnitte: v.abschnitte }); z.vorlageStart = kopie(z.vorlage); zeichnen('#ds-name'); vorschau(); return; }
    if (a === 'v-kopieren' && v) { z.vorlage = kopie({ id: '', name: freierName(v.name), raster: v.raster, abschnitte: v.abschnitte }); z.vorlageStart = {}; zeichnen('#ds-name'); vorschau(); return; }
    if (a === 'v-loeschen' && v) { vorlageLoeschen(v); return; }
    if (!d) return;
    if (a === 'format') d.raster.format = t.dataset.wert;
    else if (a === 'spalten') d.raster.spalten = +t.dataset.wert;
    else if (a === 'neu-gruppen') d.abschnitte.push({ art: 'gruppen', titel: '', inhalt: [] });
    else if (a === 'neu-text') d.abschnitte.push({ art: 'text', titel: '', text: '' });
    else if (a === 'hoch' && i > 0) d.abschnitte.splice(i - 1, 0, ...d.abschnitte.splice(i, 1));
    else if (a === 'runter' && i < d.abschnitte.length - 1) d.abschnitte.splice(i + 1, 0, ...d.abschnitte.splice(i, 1));
    else if (a === 'weg') d.abschnitte.splice(i, 1);
    else if (a === 'ref-weg') d.abschnitte[i].inhalt.splice(+t.dataset.j, 1);
    else return;
    const ziel = a === 'neu-gruppen' || a === 'neu-text' ? `.ds-ab[data-i="${d.abschnitte.length - 1}"] .ds-titel`
      : a === 'hoch' || a === 'runter' ? `.ds-ab[data-i="${a === 'hoch' ? i - 1 : i + 1}"] [data-ds="${a}"]:not(:disabled)` : a === 'format' || a === 'spalten' ? `[data-ds="${a}"][data-wert="${t.dataset.wert}"]` : null;
    zeichnen(ziel);
    vorschau();
  });
  body.addEventListener('change', (e) => {
    const t = e.target;
    if (!z) return;
    if (t.id === 'ds-wahl') { z.wahl = t.value; z.angepasst = false; z.entwurf = basis(z.wahl); zeichnen('#ds-wahl'); vorschau(); return; }
    const d = aktuell(), i = +t.dataset.i;
    if (!d || !t.dataset.f) return;
    if (t.dataset.f === 'spalten') { if (t.value) d.abschnitte[i].spalten = +t.value; else delete d.abschnitte[i].spalten; vorschau(); return; }
    if (t.dataset.f === 'neu' && t.value) {
      const [typ, ...rest] = t.value.split(':'), name = rest.join(':');
      d.abschnitte[i].inhalt.push(typ === 'b' ? { bereich: name } : { gruppe: name });
      zeichnen(`.ds-ab[data-i="${i}"] [data-f="neu"]`);
      vorschau();
    }
  });
  body.addEventListener('input', (e) => {
    const t = e.target, d = z && aktuell();
    if (!d) return;
    if (t.id === 'ds-name' && z.vorlage) { z.vorlage.name = t.value; standZeigen(); return; }
    if (t.dataset.f === 'titel' || t.dataset.f === 'text') { d.abschnitte[+t.dataset.i][t.dataset.f] = t.value; vorschau(); }
  });
  dlg.addEventListener('close', () => { if (frame) { frame.remove(); frame = null; } clearTimeout(uhr); });
  btn.addEventListener('click', () => oeffnen());
  D.oeffnen = oeffnen;
})();
