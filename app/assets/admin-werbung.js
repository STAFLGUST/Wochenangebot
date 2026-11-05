/* ==========================================================================
   Eingabebereich – Fenster „Werbung schalten“ (Angebot bearbeiten, Knopf „Werbung“ in der Werkzeugleiste)
   Bis zu zwei Werbungen je Angebot (Reiter „Werbung 1“/„Werbung 2“, „Weitere Werbung“ legt die zweite an): je Werbung
   Überschrift, optionaler Werbetext und bis zu 12 Artikel des gewählten Angebots (Reihenfolge, je Artikel ein kurzer
   Hinweis). Auf der Angebotsseite steht die erste Werbung oben, die zweite rechts daneben (schmal: darunter); beworbene
   Artikel sind in der Liste hervorgehoben. Artikel wählt das gemeinsame Fenster „Artikelauswahl“ (admin-artikelwahl.js,
   über den Rückruf „auswaehlen“ des Aufrufers: Artikel dieses Angebots vorausgewählt, Bestand sichtbar). Daten und
   Übernahme liefert der Aufrufer (admin.js: model.meta.werbung[<Angebot>] = erste Werbung mit „weitere“: [zweite],
   Rückruf „uebernehmen“); für Kunden sichtbar erst nach „Veröffentlichen“, ausgeliefert nur das eigene Angebot
   (Server: offer_resolve).
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const { $, esc, icon } = W;
  const dlg = $('#dlg-werbung');
  const body = $('#werbung-body');
  const TITEL = 'Unsere Empfehlung der Woche';
  const TITEL2 = 'Aktion der Woche';   // Vorschlag für die zweite Werbung
  const BLOECKE = 2;
  let cfg = null, bl = [], akt = 0;   // bl: [{titel, text, sel: [{id, text}]}], akt: angezeigte Werbung

  const byId = () => new Map(cfg.artikel.map((a) => [a.id, a]));
  const zeile = (a) => [a.code, a.merkmale, a.preis].filter(Boolean).join(' · ');
  const b = () => bl[akt];

  function listeHTML() {
    const m = byId();
    const ro = cfg.ro;
    b().sel = b().sel.filter((s) => m.has(s.id));
    const sel = b().sel;
    const rows = sel.map((s, i) => {
      const a = m.get(s.id);
      return `<li data-wid="${esc(s.id)}"><span class="wb-nr">${i + 1}</span>
        <div class="wb-a"><b>${esc(a.name)}</b><small>${esc(zeile(a))}</small></div>
        <input class="in wb-hin" data-wt="${esc(s.id)}" value="${esc(s.text || '')}" maxlength="40" placeholder="Hinweis (optional), z. B. Top-Preis" aria-label="Hinweis zu ${esc(a.name)}"${ro ? ' disabled' : ''}>
        ${ro ? '' : `<span class="wb-btns"><button type="button" class="ibtn" data-wm="up" aria-label="Nach oben"${i === 0 ? ' disabled' : ''}>${icon('up', 'sm')}</button><button type="button" class="ibtn" data-wm="down" aria-label="Nach unten"${i === sel.length - 1 ? ' disabled' : ''}>${icon('down', 'sm')}</button><button type="button" class="ibtn danger" data-wm="rm" aria-label="${esc(a.name)} aus der Werbung nehmen">${icon('x', 'sm')}</button></span>`}</li>`;
    }).join('');
    $('#wb-n').textContent = `${sel.length} von ${cfg.max}`;
    $('#wb-liste').innerHTML = rows || `<li class="wb-leer">${ro ? 'Keine Artikel in der Werbung.' : 'Noch keine Artikel – über „Artikel auswählen“ hinzufügen.'}</li>`;
    reiterHTML();
  }

  /* Reiter der Werbungen (nur ab zwei Werbungen) und Knopf „Weitere Werbung“ */
  function reiterHTML() {
    const host = $('#wb-reiter');
    if (!host) return;
    const plus = !cfg.ro && bl.length < BLOECKE;
    if (bl.length < 2) {
      host.innerHTML = plus ? `<button type="button" class="btn sm wb-plus" data-wa="neu">${icon('plus', 'sm')}Weitere Werbung</button><span class="wb-rh">erscheint auf der Angebotsseite rechts daneben</span>` : '';
      return;
    }
    host.innerHTML = `<div class="wb-tabs" role="tablist" aria-label="Werbungen">${bl.map((x, i) => `<button type="button" role="tab" class="wb-tab" data-wr="${i}" aria-selected="${i === akt}">
        <span>Werbung ${i + 1}<small>${i === 0 ? 'oben links' : 'rechts daneben'}</small></span><span class="wb-tz">${x.sel.length}</span></button>`).join('')}</div>`;
  }

  /* Felder und Liste der angezeigten Werbung */
  function blockHTML() {
    const ro = cfg.ro, x = b();
    $('#wb-block').innerHTML = `<div class="wb-felder">
        <label class="fld"><span>Überschrift</span><input id="wb-titel" maxlength="80" value="${esc(x.titel)}" placeholder="${esc(akt === 0 ? TITEL : TITEL2)}"${ro ? ' disabled' : ''}></label>
        <label class="fld"><span>Werbetext (optional)</span><textarea id="wb-text" maxlength="240" rows="2" placeholder="z. B. Frisch eingetroffen – nur solange der Vorrat reicht."${ro ? ' disabled' : ''}>${esc(x.text)}</textarea></label>
      </div>
      <h3 class="d-h"><span>Beworbene Artikel${bl.length > 1 ? ` · Werbung ${akt + 1}` : ''}</span><span id="wb-n"></span></h3>
      <ol class="wb-liste" id="wb-liste"></ol>
      ${ro ? '' : `<button type="button" class="btn wb-auswahl" id="wb-auswahl" data-wa="auswahl">${icon('list')}Artikel auswählen …</button>`}`;
    const ende = $('#wb-ende');
    if (ende) ende.querySelector('span').textContent = bl.length > 1 ? `Werbung ${akt + 1} entfernen` : 'Werbung beenden';
    if (ende) ende.hidden = bl.length < 2 && !cfg.eintrag;
    listeHTML();
  }
  function zeigen(i) {
    akt = Math.max(0, Math.min(bl.length - 1, i));
    blockHTML();
  }

  /* Rückkehr aus der Artikelauswahl: ids = gewählte Artikel (Reihenfolge der Auswahl), artikel = aktuelle Liste des Angebots.
     Schon beworbene behalten Platz und Hinweis, neue kommen ans Ende. */
  function ausAuswahl(ids, artikel) {
    if (artikel) cfg.artikel = artikel;
    const alt = new Map(b().sel.map((s) => [s.id, s]));
    b().sel = b().sel.filter((s) => ids.includes(s.id)).concat(ids.filter((id) => !alt.has(id)).map((id) => ({ id, text: '' }))).slice(0, cfg.max);
    listeHTML();
    $('#wb-auswahl')?.focus();
  }

  /* cfg: { angebot, eintrag: {titel, text?, artikel: [{id, text?}], weitere?: [{titel, text?, artikel}]} | null,
     artikel: [{id, code, name, merkmale, preis}], max, ro, auswaehlen(ids, fertig(ids, artikel?)),
     uebernehmen(eintrag | null) } */
  function oeffnen(c) {
    cfg = c;
    const e = c.eintrag;
    const ids = new Set(c.artikel.map((a) => a.id));
    const blk = (x) => ({ titel: x.titel || '', text: x.text || '', sel: (x.artikel || []).filter((a) => ids.has(a.id)).map((a) => ({ id: a.id, text: a.text || '' })) });
    bl = e ? [e, ...(Array.isArray(e.weitere) ? e.weitere : [])].slice(0, BLOECKE).map(blk) : [];
    if (!bl.length) bl = [{ titel: TITEL, text: '', sel: [] }];
    akt = 0;
    const ro = c.ro;
    body.innerHTML = `<div class="dlg-head"><div><h2 id="wb-title">${icon('megaphone')}Werbung schalten</h2>
        <p>Angebot „${esc(c.angebot)}“: Diese Artikel stehen auf der Angebotsseite oben im Werbeblock und sind in der Liste hervorgehoben. Eine weitere Werbung erscheint rechts daneben. Für Kunden sichtbar nach „Veröffentlichen“.</p></div>
        <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">
        <div class="wb-reiter" id="wb-reiter"></div>
        <div id="wb-block"></div>
        <p class="form-err" id="wb-err" role="alert"></p>
      </div>
      <div class="dlg-foot">${ro ? '' : `<button type="button" class="btn ghost wb-ende" id="wb-ende" data-wa="ende">${icon('trash')}<span>Werbung beenden</span></button>`}<span class="spacer"></span>
        <button type="button" class="btn" data-close>${ro ? 'Schließen' : 'Abbrechen'}</button>${ro ? '' : `<button type="button" class="btn primary" data-wa="ok">${icon('check')}Übernehmen</button>`}</div>`;
    blockHTML();
    dlg.showModal();
    if (!ro) (b().sel.length ? $('#wb-titel') : $('#wb-auswahl')).focus();
  }

  body.addEventListener('submit', (e) => e.preventDefault());
  body.addEventListener('input', (e) => {
    if (!cfg || !b()) return;
    if (e.target.id === 'wb-titel') { b().titel = e.target.value; return; }
    if (e.target.id === 'wb-text') { b().text = e.target.value; return; }
    const id = e.target.dataset.wt;
    if (id) { const s = b().sel.find((x) => x.id === id); if (s) s.text = e.target.value; }
  });
  body.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.tagName === 'INPUT') e.preventDefault();
    const t = e.target.closest('[data-wr]');   // Reiter mit Pfeiltasten wechseln
    if (t && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) { e.preventDefault(); zeigen(akt + (e.key === 'ArrowRight' ? 1 : -1)); $(`[data-wr="${akt}"]`)?.focus(); }
  });
  body.addEventListener('click', (e) => {
    if (e.target.closest('[data-close]')) { dlg.close(); return; }
    const r = e.target.closest('[data-wr]');
    if (r) { $('#wb-err').textContent = ''; zeigen(+r.dataset.wr); return; }
    const mv = e.target.closest('[data-wm]');
    if (mv) {
      const sel = b().sel;
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
    if (a === 'neu') {
      if (bl.length >= BLOECKE) return;
      bl.push({ titel: TITEL2, text: '', sel: [] });
      zeigen(bl.length - 1);
      $('#wb-auswahl')?.focus();
      return;
    }
    if (a === 'auswahl') { cfg.auswaehlen(b().sel.map((s) => s.id), ausAuswahl); return; }
    if (a === 'ende') {
      if (bl.length > 1) { bl.splice(akt, 1); zeigen(0); return; }   // nur diese Werbung entfernen (wirksam mit „Übernehmen“)
      dlg.close(); cfg.uebernehmen(null); return;
    }
    if (a === 'ok') {
      const leer = bl.findIndex((x) => !x.sel.length);
      if (bl.length > 1 && leer >= 0) {   // eine zweite Werbung ohne Artikel ginge sonst unbemerkt verloren
        zeigen(leer);
        $('#wb-err').textContent = `Werbung ${leer + 1} hat noch keine Artikel – Artikel auswählen oder „Werbung ${leer + 1} entfernen“.`;
        return;
      }
      const l = bl.filter((x) => x.sel.length).map((x) => {
        const titel = x.titel.trim(), text = x.text.trim();
        return { titel, ...(text ? { text } : {}), artikel: x.sel.map((s) => (s.text.trim() ? { id: s.id, text: s.text.trim() } : { id: s.id })) };
      });
      dlg.close();
      cfg.uebernehmen(!l.length ? null : l.length > 1 ? { ...l[0], weitere: l.slice(1) } : l[0]);
    }
  });

  W.werbung = { oeffnen, TITEL, TITEL2 };
})();
