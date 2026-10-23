/* ==========================================================================
   Wochenangebot – Eingabebereich, Verwaltung → Rollen und Rechte (nur Administratoren)
   Eigene Rollen anlegen, umbenennen, kopieren und löschen; je Rolle: welche Module sie öffnen darf (Modulzugang
   „<modul>.zugang“) und was sie darin sehen und bearbeiten darf. Gespeichert wird nur auf dem Server (rolle_save,
   rolle_loeschen); dort werden Rechte, Voraussetzungen und Modulzugang auch durchgesetzt (GR-103) – diese Seite zeigt
   und sammelt nur die Auswahl. Daten: Aktion „rechte“ (rollen, module, catalog).
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const { $, $$, api, esc, icon, toast, confirmBox, dateTime, plural } = W;

  let daten = null;          // Antwort von „rechte“
  let wahl = 'editor';       // gewählte Rolle (id) oder '' für eine neue
  let entwurf = null;        // { id, name, beschreibung, rechte:Set } – ungespeicherte Auswahl
  let geaendert = false;

  const kat = () => daten.catalog;
  const recht = (k) => kat().find((p) => p.key === k) || { requires: [] };
  const rolle = (id) => daten.rollen.find((r) => r.id === id);
  /* Voraussetzungen (bearbeiten setzt sehen voraus) – wie rights_close auf dem Server */
  const mitVoraussetzungen = (set) => { let neu = true; while (neu) { neu = false; for (const k of [...set]) for (const r of recht(k).requires) if (!set.has(r)) { set.add(r); neu = true; } } return set; };
  const abhaengige = (k) => kat().filter((p) => p.requires.includes(k)).map((p) => p.key);

  function neuerEntwurf(id, kopie) {
    const r = id ? rolle(id) : null;
    const q = kopie ? rolle(kopie) : null;
    entwurf = r ? { id: r.id, name: r.name, beschreibung: r.beschreibung || '', rechte: new Set(r.rechte), art: r.art }
      : { id: '', name: q ? `${q.name} (Kopie)` : '', beschreibung: q && q.art === 'eigen' ? q.beschreibung : '', rechte: new Set(q ? (q.art === 'fest' ? kat().map((p) => p.key) : q.rechte) : []), art: 'eigen' };
    geaendert = !r;
  }

  const modulRechte = (mid) => kat().filter((p) => p.modul === mid && p.kind !== 'zugang');
  const zugangKey = (mid) => (kat().some((p) => p.key === mid + '.zugang') ? mid + '.zugang' : '');
  const zaehleModule = (rechte) => daten.module.filter((m) => zugangKey(m.id) && rechte.includes(zugangKey(m.id))).length;

  function listeHTML() {
    return daten.rollen.map((r) => {
      const n = r.art === 'fest' ? 'alle' : zaehleModule(r.rechte);
      return `<button type="button" class="rl-item${r.id === wahl ? ' on' : ''}" data-rl-wahl="${esc(r.id)}" aria-pressed="${r.id === wahl}">
        <span class="rl-item-n">${esc(r.name)}${r.art === 'fest' ? ' <span class="rl-tag">fest</span>' : r.art === 'standard' ? ' <span class="rl-tag">Standard</span>' : ''}</span>
        <span class="rl-item-m">${plural(r.mitarbeiter, 'Mitarbeiter', 'Mitarbeiter')} · ${n === 'alle' ? 'alle Module' : plural(n, 'Modul', 'Module')}</span></button>`;
    }).join('') + (wahl === '' ? `<button type="button" class="rl-item on" aria-pressed="true"><span class="rl-item-n">${esc(entwurf.name || 'Neue Rolle')}</span><span class="rl-item-m">noch nicht gespeichert</span></button>` : '');
  }

  function rechtZeile(p, an, gesperrt) {
    const art = p.kind === 'sehen' ? '<span class="rm-k rm-sehen">sehen</span>' : '<span class="rm-k rm-machen">bearbeiten</span>';
    return `<label class="rl-recht"><input type="checkbox" data-rl-key="${esc(p.key)}"${an ? ' checked' : ''}${gesperrt ? ' disabled' : ''}>${art}<span>${esc(p.label)}</span></label>`;
  }

  function modulHTML(m, fest) {
    const zk = zugangKey(m.id);
    const rechte = modulRechte(m.id);
    if (!zk && !rechte.length) return '';
    const auf = fest || !zk || entwurf.rechte.has(zk);
    const status = m.kachel ? (m.freigegeben ? '' : '<span class="rl-tag rl-plan">in Vorbereitung</span>') : '';
    const teil = m.teil_von ? (daten.module.find((x) => x.id === m.teil_von) || {}).name : '';
    return `<section class="rl-mod${auf ? '' : ' zu'}" data-rl-modul="${esc(m.id)}">
      <div class="rl-mod-kopf">
        <div class="rl-mod-t"><h4>${esc(m.name)} ${status}</h4><p>${esc(m.beschreibung)}${teil ? ` <span class="muted">· öffnet die Importzentrale im Bereich „${esc(teil)}“</span>` : ''}</p></div>
        ${zk ? `<label class="rl-schalter"><input type="checkbox" role="switch" data-rl-key="${esc(zk)}"${auf ? ' checked' : ''}${fest ? ' disabled' : ''} aria-label="Modul „${esc(m.name)}“ öffnen"><span class="rl-schalter-t">${auf ? 'Zugang' : 'Kein Zugang'}</span></label>` : ''}
      </div>
      ${rechte.length ? `<div class="rl-rechte">${rechte.map((p) => rechtZeile(p, fest || entwurf.rechte.has(p.key), fest)).join('')}</div>
        ${zk && !auf ? '<p class="rl-mod-hinw">Ohne Zugang erscheint die Kachel nicht und die Oberfläche des Moduls ist gesperrt. Angehakte Rechte gelten nur dort, wo andere Module sie nutzen.</p>' : ''}`
        : (m.kachel && !m.freigegeben ? '<p class="rl-mod-hinw">Die Rechte innerhalb des Moduls kommen mit seiner Freigabe hinzu.</p>' : '')}
    </section>`;
  }

  function detailHTML() {
    const r = entwurf.id ? rolle(entwurf.id) : null;
    const fest = entwurf.art === 'fest';
    const eigen = entwurf.art === 'eigen';
    return `<div class="rl-det-kopf">
        <div class="rl-felder">
          <label class="fld"><span>Name der Rolle</span><input id="rl-name" maxlength="40" value="${esc(entwurf.name)}"${fest ? ' disabled' : ''} placeholder="z. B. Vertrieb, Lager, Personalstelle" autocomplete="off"></label>
          ${eigen ? `<label class="fld"><span>Beschreibung <small class="muted">(optional)</small></span><input id="rl-besch" maxlength="160" value="${esc(entwurf.beschreibung)}" placeholder="Wofür ist die Rolle gedacht?" autocomplete="off"></label>`
            : `<p class="hint rl-art">${fest ? 'Administratoren haben immer alle Rechte, dazu die Verwaltung von Mitarbeitern, Rollen, Sicherheit und E-Mail. Diese Rolle ist fest.' : 'Standardrolle: Name und Rechte sind änderbar, die Rolle selbst bleibt bestehen.'}</p>`}
        </div>
        ${r ? `<div class="rl-det-akt">
          <button type="button" class="btn sm" data-rl-akt="kopie">${icon('copy', 'sm')}Als neue Rolle kopieren</button>
          ${eigen ? `<button type="button" class="btn sm ghost rl-loeschen" data-rl-akt="loeschen">${icon('trash', 'sm')}Rolle löschen</button>` : ''}
          ${entwurf.art === 'standard' ? `<button type="button" class="btn sm ghost" data-rl-akt="standard">${icon('undo', 'sm')}Standard wiederherstellen</button>` : ''}
        </div>` : ''}
      </div>
      ${r ? `<p class="sub rl-meta">${plural(r.mitarbeiter, 'Mitarbeiter hat', 'Mitarbeiter haben')} diese Rolle${r.geaendert ? ` · geändert ${esc(dateTime(r.geaendert))}${r.geaendertVon ? ' von ' + esc(r.geaendertVon) : ''}` : ''}</p>` : ''}
      <h3 class="sec-h rl-h">Module und Rechte</h3>
      <p class="hint">Je Modul: ob die Rolle es öffnen darf und was sie darin sehen und bearbeiten darf. Wer etwas bearbeiten darf, darf es auch sehen. Einzelnen Mitarbeitern geben oder entziehen Sie Rechte zusätzlich unter „Mitarbeiter“ → „Bearbeiten“.</p>
      <div class="rl-module">${daten.module.map((m) => modulHTML(m, fest)).join('')}</div>
      <section class="rl-mod rl-admin"><div class="rl-mod-kopf"><div class="rl-mod-t"><h4>Nur Administratoren</h4><p>Fest vorbehalten, damit sich niemand selbst höhere Rechte geben kann.</p></div></div>
        <div class="rl-rechte">${daten.adminOnly.map((l) => `<span class="rl-recht fest"><span class="rl-fest-i" aria-hidden="true">${fest ? '✓' : '–'}</span><span class="rm-k rm-machen">bearbeiten</span><span>${esc(l)}</span></span>`).join('')}</div></section>
      <p class="form-err" id="rl-err" role="alert"></p>
      ${fest ? '' : `<div class="sec-foot rl-foot"><span class="rl-stand" id="rl-stand" role="status">${geaendert ? 'Ungespeicherte Änderungen' : ''}</span>
        ${entwurf.id ? `<button type="button" class="btn ghost" data-rl-akt="verwerfen"${geaendert ? '' : ' disabled'}>Verwerfen</button>` : '<button type="button" class="btn ghost" data-rl-akt="verwerfen">Abbrechen</button>'}
        <button type="button" class="btn primary" data-rl-akt="speichern">${icon('check', 'sm')}${entwurf.id ? 'Rolle speichern' : 'Rolle anlegen'}</button></div>`}`;
  }

  function zeichnen() {
    const host = $('#view-rollen');
    host.innerHTML = `<div class="ed-toolbar"><span class="ed-hint">${plural(daten.rollen.length, 'Rolle', 'Rollen')} · legen fest, welche Module ein Mitarbeiter öffnen und was er darin sehen und bearbeiten darf</span>
        <button type="button" class="btn primary" data-rl-akt="neu">${icon('plus')}Neue Rolle</button></div>
      <div class="rl-layout">
        <nav class="gcard rl-liste" aria-label="Rollen">${listeHTML()}</nav>
        <div class="gcard rl-detail" id="rl-detail">${detailHTML()}</div>
      </div>`;
  }

  function markieren() {
    geaendert = true;
    const st = $('#rl-stand'); if (st) st.textContent = 'Ungespeicherte Änderungen';
    const v = $('#view-rollen [data-rl-akt="verwerfen"]'); if (v) v.disabled = false;
  }
  async function weiterOhneSpeichern() {
    if (!geaendert) return true;
    return confirmBox('Änderungen verwerfen?', 'Die Änderungen an dieser Rolle sind noch nicht gespeichert.', 'Verwerfen', true);
  }

  async function laden(id) {
    const host = $('#view-rollen');
    if (!daten) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Rollen werden geladen …</div>';
    try { daten = await api('rechte'); } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    if (id !== undefined) wahl = id;
    if (wahl !== '' && !rolle(wahl)) wahl = 'editor';
    if (wahl !== '' || !entwurf) neuerEntwurf(wahl === '' ? null : wahl);
    zeichnen();
  }

  const host = $('#view-rollen');
  host.addEventListener('input', (e) => {
    if (e.target.id === 'rl-name') { entwurf.name = e.target.value; markieren(); }
    if (e.target.id === 'rl-besch') { entwurf.beschreibung = e.target.value; markieren(); }
  });
  host.addEventListener('change', (e) => {
    const k = e.target.dataset.rlKey;
    if (!k) return;
    const box = (key) => host.querySelector(`[data-rl-key="${CSS.escape(key)}"]`);
    if (e.target.checked) for (const q of mitVoraussetzungen(new Set([k]))) { entwurf.rechte.add(q); const b = box(q); if (b) b.checked = true; }
    else {
      entwurf.rechte.delete(k);
      const stapel = [k];
      while (stapel.length) for (const d of abhaengige(stapel.pop())) if (entwurf.rechte.has(d)) { entwurf.rechte.delete(d); const b = box(d); if (b) b.checked = false; stapel.push(d); }
    }
    // Modulzugang umgeschaltet: Abschnitt neu zeichnen (Hinweis, abgeblendete Rechte), Fokus auf dem Schalter behalten
    if (recht(k).kind === 'zugang') {
      const m = daten.module.find((x) => x.id === recht(k).modul);
      const alt = host.querySelector(`[data-rl-modul="${CSS.escape(m.id)}"]`);
      if (alt) { alt.outerHTML = modulHTML(m, false); const s = box(k); if (s) s.focus(); }
    }
    markieren();
  });
  host.addEventListener('click', async (e) => {
    const w = e.target.closest('[data-rl-wahl]');
    if (w) {
      if (w.dataset.rlWahl === wahl) return;
      if (!(await weiterOhneSpeichern())) return;
      wahl = w.dataset.rlWahl; neuerEntwurf(wahl); zeichnen();
      const d = $('#rl-detail'); if (d && window.matchMedia('(max-width: 900px)').matches) d.scrollIntoView({ block: 'start', behavior: 'smooth' });
      return;
    }
    const a = e.target.closest('[data-rl-akt]')?.dataset.rlAkt;
    if (!a) return;
    if (a === 'neu' || a === 'kopie') {
      if (!(await weiterOhneSpeichern())) return;
      const quelle = a === 'kopie' ? entwurf.id : null;
      wahl = ''; neuerEntwurf(null, quelle); zeichnen();
      const n = $('#rl-name'); if (n) { n.focus(); n.select(); }
      return;
    }
    if (a === 'standard') {   // Standardrechte laut Katalog (bisheriges Rollenmodell) – wirksam erst mit „Rolle speichern“
      entwurf.rechte = new Set(kat().filter((p) => p.default.includes(entwurf.id)).map((p) => p.key));
      const name = entwurf.name; zeichnen(); markieren(); const n = $('#rl-name'); if (n) n.value = name;
      toast('Standard eingetragen – zum Übernehmen „Rolle speichern“.');
      return;
    }
    if (a === 'verwerfen') {
      if (!entwurf.id) { wahl = 'editor'; neuerEntwurf('editor'); zeichnen(); return; }
      neuerEntwurf(entwurf.id); zeichnen(); return;
    }
    if (a === 'loeschen') {
      const r = rolle(entwurf.id);
      if (r.mitarbeiter) { $('#rl-err').textContent = `Die Rolle ist noch ${plural(r.mitarbeiter, 'Mitarbeiter', 'Mitarbeitern')} zugeordnet. Bitte dort zuerst eine andere Rolle wählen.`; return; }
      if (!(await confirmBox('Rolle löschen?', `Die Rolle „${esc(r.name)}“ wird gelöscht. Das lässt sich nicht rückgängig machen.`, 'Löschen', true))) return;
      try { await api('rolle_loeschen', { body: { id: r.id } }); geaendert = false; toast(`Rolle „${r.name}“ gelöscht.`); await laden('editor'); }
      catch (ex) { const f = $('#rl-err'); if (f) f.textContent = ex.message; }
      return;
    }
    if (a === 'speichern') {
      const f = $('#rl-err'); f.textContent = '';
      const name = entwurf.name.trim();
      if (name.length < 2) { f.textContent = 'Bitte einen Namen für die Rolle angeben (mindestens 2 Zeichen).'; $('#rl-name').focus(); return; }
      const btn = e.target.closest('button'); btn.disabled = true;
      try {
        const r = await api('rolle_save', { body: { id: entwurf.id, name, beschreibung: entwurf.beschreibung.trim(), rechte: [...entwurf.rechte] } });
        const neu = !entwurf.id;
        geaendert = false;
        toast(neu ? `Rolle „${name}“ angelegt – jetzt unter „Mitarbeiter“ zuordnen.` : `Rolle „${name}“ gespeichert. Die Rechte gelten ab der nächsten Aktion der Mitarbeiter.`);
        await laden(r.id);
      } catch (ex) { f.textContent = ex.message; btn.disabled = false; }
    }
  });

  W.views.rollen = () => laden();
})();
