/* ==========================================================================
   Eingabebereich – Fenster „Werbung schalten“ (Angebot bearbeiten, Knopf „Werbung“ in der Werkzeugleiste)
   Überschrift, optionaler Werbetext und bis zu 12 Artikel des gewählten Angebots (Reihenfolge, je Artikel ein kurzer
   Hinweis). Artikel wählt das gemeinsame Fenster „Artikelauswahl“ (admin-artikelwahl.js, über den Rückruf „auswaehlen“
   des Aufrufers: Artikel dieses Angebots vorausgewählt, Bestand sichtbar). Die Artikel stehen auf der Angebotsseite oben
   in einem Werbeblock und sind in der Liste hervorgehoben. Daten und Übernahme liefert der Aufrufer
   (admin.js: model.meta.werbung[<Angebot>], Rückruf „uebernehmen“); für Kunden sichtbar erst nach „Veröffentlichen“,
   ausgeliefert nur das eigene Angebot (Server: offer_resolve).
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const { $, esc, icon } = W;
  const dlg = $('#dlg-werbung');
  const body = $('#werbung-body');
  const TITEL = 'Unsere Empfehlung der Woche';
  let cfg = null, sel = [];

  const byId = () => new Map(cfg.artikel.map((a) => [a.id, a]));
  const zeile = (a) => [a.code, a.merkmale, a.preis].filter(Boolean).join(' · ');

  function listeHTML() {
    const m = byId();
    const ro = cfg.ro;
    sel = sel.filter((s) => m.has(s.id));
    const rows = sel.map((s, i) => {
      const a = m.get(s.id);
      return `<li data-wid="${esc(s.id)}"><span class="wb-nr">${i + 1}</span>
        <div class="wb-a"><b>${esc(a.name)}</b><small>${esc(zeile(a))}</small></div>
        <input class="in wb-hin" data-wt="${esc(s.id)}" value="${esc(s.text || '')}" maxlength="40" placeholder="Hinweis (optional), z. B. Top-Preis" aria-label="Hinweis zu ${esc(a.name)}"${ro ? ' disabled' : ''}>
        ${ro ? '' : `<span class="wb-btns"><button type="button" class="ibtn" data-wm="up" aria-label="Nach oben"${i === 0 ? ' disabled' : ''}>${icon('up', 'sm')}</button><button type="button" class="ibtn" data-wm="down" aria-label="Nach unten"${i === sel.length - 1 ? ' disabled' : ''}>${icon('down', 'sm')}</button><button type="button" class="ibtn danger" data-wm="rm" aria-label="${esc(a.name)} aus der Werbung nehmen">${icon('x', 'sm')}</button></span>`}</li>`;
    }).join('');
    $('#wb-n').textContent = `${sel.length} von ${cfg.max}`;
    $('#wb-liste').innerHTML = rows || `<li class="wb-leer">${ro ? 'Keine Artikel in der Werbung.' : 'Noch keine Artikel – über „Artikel auswählen“ hinzufügen.'}</li>`;
  }

  /* Rückkehr aus der Artikelauswahl: ids = gewählte Artikel (Reihenfolge der Auswahl), artikel = aktuelle Liste des Angebots.
     Schon beworbene behalten Platz und Hinweis, neue kommen ans Ende. */
  function ausAuswahl(ids, artikel) {
    if (artikel) cfg.artikel = artikel;
    const alt = new Map(sel.map((s) => [s.id, s]));
    sel = sel.filter((s) => ids.includes(s.id)).concat(ids.filter((id) => !alt.has(id)).map((id) => ({ id, text: '' }))).slice(0, cfg.max);
    listeHTML();
    $('#wb-auswahl')?.focus();
  }

  /* cfg: { angebot, eintrag: {titel, text?, artikel: [{id, text?}]} | null, artikel: [{id, code, name, merkmale, preis}],
     max, ro, auswaehlen(ids, fertig(ids, artikel?)), uebernehmen(eintrag | null) } */
  function oeffnen(c) {
    cfg = c;
    const e = c.eintrag;
    const ids = new Set(c.artikel.map((a) => a.id));
    sel = e ? e.artikel.filter((a) => ids.has(a.id)).map((a) => ({ id: a.id, text: a.text || '' })) : [];
    const ro = c.ro;
    body.innerHTML = `<div class="dlg-head"><div><h2 id="wb-title">${icon('megaphone')}Werbung schalten</h2>
        <p>Angebot „${esc(c.angebot)}“: Diese Artikel stehen auf der Angebotsseite oben im Werbeblock und sind in der Liste hervorgehoben. Für Kunden sichtbar nach „Veröffentlichen“.</p></div>
        <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        <div class="wb-felder">
          <label class="fld"><span>Überschrift</span><input id="wb-titel" maxlength="80" value="${esc(e ? e.titel : TITEL)}" placeholder="${esc(TITEL)}"${ro ? ' disabled' : ''}></label>
          <label class="fld"><span>Werbetext (optional)</span><textarea id="wb-text" maxlength="240" rows="2" placeholder="z. B. Frisch eingetroffen – nur solange der Vorrat reicht."${ro ? ' disabled' : ''}>${esc(e && e.text ? e.text : '')}</textarea></label>
        </div>
        <h3 class="d-h"><span>Beworbene Artikel</span><span id="wb-n"></span></h3>
        <ol class="wb-liste" id="wb-liste"></ol>
        ${ro ? '' : `<button type="button" class="btn wb-auswahl" id="wb-auswahl" data-wa="auswahl">${icon('list')}Artikel auswählen …</button>`}
      </div>
      <div class="dlg-foot">${!ro && e ? `<button type="button" class="btn ghost wb-ende" data-wa="ende">${icon('trash')}Werbung beenden</button>` : ''}<span class="spacer"></span>
        <button type="button" class="btn" data-close>${ro ? 'Schließen' : 'Abbrechen'}</button>${ro ? '' : `<button type="button" class="btn primary" data-wa="ok">${icon('check')}Übernehmen</button>`}</div>`;
    listeHTML();
    dlg.showModal();
    if (!ro) (sel.length ? $('#wb-titel') : $('#wb-auswahl')).focus();
  }

  body.addEventListener('submit', (e) => e.preventDefault());
  body.addEventListener('input', (e) => {
    const id = e.target.dataset.wt;
    if (id) { const s = sel.find((x) => x.id === id); if (s) s.text = e.target.value; }
  });
  body.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.target.tagName === 'INPUT') e.preventDefault(); });
  body.addEventListener('click', (e) => {
    if (e.target.closest('[data-close]')) { dlg.close(); return; }
    const mv = e.target.closest('[data-wm]');
    if (mv) {
      const i = sel.findIndex((s) => s.id === mv.closest('[data-wid]').dataset.wid);
      if (i < 0) return;
      const k = mv.dataset.wm;
      if (k === 'rm') sel.splice(i, 1);
      else { const j = k === 'up' ? i - 1 : i + 1; if (j < 0 || j >= sel.length) return; [sel[i], sel[j]] = [sel[j], sel[i]]; }
      listeHTML();
      const li = k === 'rm' ? null : $(`#wb-liste [data-wid="${CSS.escape(sel[k === 'up' ? i - 1 : i + 1].id)}"] [data-wm="${k}"]`);
      (li && !li.disabled ? li : $('#wb-auswahl'))?.focus();
      return;
    }
    const a = e.target.closest('[data-wa]')?.dataset.wa;
    if (a === 'auswahl') { cfg.auswaehlen(sel.map((s) => s.id), ausAuswahl); return; }
    if (a === 'ende') { dlg.close(); cfg.uebernehmen(null); return; }
    if (a === 'ok') {
      const titel = $('#wb-titel').value.trim(), text = $('#wb-text').value.trim();
      const artikel = sel.map((s) => (s.text.trim() ? { id: s.id, text: s.text.trim() } : { id: s.id }));
      dlg.close();
      cfg.uebernehmen(artikel.length ? { titel, ...(text ? { text } : {}), artikel } : null);
    }
  });
  dlg.addEventListener('click', (e) => { if (e.target === dlg) dlg.close(); });

  W.werbung = { oeffnen, TITEL };
})();
