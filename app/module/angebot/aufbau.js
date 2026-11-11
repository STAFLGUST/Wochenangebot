/* STAFL-Plattform · Angebot · Fenster „Aufbau des Angebots“ (Knopf „Editor“ in der Werkzeugleiste von „Angebot bearbeiten“,
   Wunsch des Inhabers 11.11.2026). Zeigt die Bereiche des gewählten Angebots in Angebotsreihenfolge, darunter eingerückt
   ihre Gruppen mit Artikelzahl; Gruppen ohne Bereich bilden an ihrer Stelle einen eigenen Block „ohne Bereich“.
   Reihenfolge ändern: Pfeile ↑/↓ (Tastatur, Handy) oder Ziehen am Griff (Maus und Touch über Pointer Events) – ein Bereich
   als Ganzes mit seinen Gruppen, eine Gruppe innerhalb ihres Bereichs; zieht man eine Gruppe in einen anderen Bereich,
   bekommt sie dessen Bereich (Kennzeichen „Bereich neu“). Gespeichert wird erst mit „Übernehmen“ über den Entwurf
   (admin.js: WA.angebot.aufbau.uebernehmen → save_draft mit Revision, Recht angebot.bearbeiten auf dem Server); hat jemand
   anderes den Aufbau inzwischen geändert, übernimmt das Fenster nichts und zeigt den neuen Stand. „Abbrechen“, × und
   Escape verwerfen (mit Änderungen schließt Escape erst beim zweiten Mal, theme.js). Ohne eigenen Aufbau (Kundenangebot
   „folgt dem Wochenangebot“, Angebotskategorien der Stammdaten) zeigt das Fenster den Aufbau nur an.
   Wird von admin/index.html nach admin.js geladen. */
(function () {
  'use strict';
  const W = window.WA;
  const btn = document.getElementById('btn-aufbau');
  const dlg = document.getElementById('dlg-aufbau');
  if (!W || !btn || !dlg || !W.angebot || !W.angebot.aufbau) return;
  const { esc, icon, plural, toast } = W;
  const A = W.angebot.aufbau;
  const body = document.getElementById('aufbau-body');
  const OHNE = 'ohne Bereich';
  let d = null;          // Daten beim Öffnen (admin.js aufbauDaten): { angebot, std, sperre, gruppen: [{id, name, bereich, n}], stand }
  let bl = [];           // Blöcke in Angebotsreihenfolge: [{ bereich, ids: [Gruppen-ID …] }]
  let info = new Map();  // Gruppen-ID → { name, n, bereich (beim Öffnen) }
  let start = '';        // Zustand beim Öffnen (Vergleich: geändert?)
  let busy = false;
  let zug = null;        // laufendes Ziehen

  const nurAnsehen = () => !d || !!d.sperre || !d.gruppen.length;
  const zustand = () => JSON.stringify(bl.map((b) => [b.bereich, b.ids]));
  const liste = () => body.querySelector('#abf-liste');

  /* Aufeinanderfolgende Gruppen mit gleichem Bereich bilden einen Block (wie die Überschriften im Editor und auf der Seite) */
  function bloecke(gruppen) {
    const out = [];
    for (const g of gruppen) {
      const l = out[out.length - 1];
      if (l && l.bereich === g.bereich) l.ids.push(g.id); else out.push({ bereich: g.bereich, ids: [g.id] });
    }
    return out;
  }
  /* leere Blöcke entfernen, benachbarte mit gleichem Bereich zusammenfassen */
  function normalisieren() {
    bl = bl.filter((b) => b.ids.length);
    for (let i = bl.length - 1; i > 0; i--) if (bl[i].bereich === bl[i - 1].bereich) { bl[i - 1].ids.push(...bl[i].ids); bl.splice(i, 1); }
  }

  function listeHTML() {
    const ro = nurAnsehen();
    const pfeil = (art, k, aus, lbl) => `<button type="button" class="ibtn" data-ab="${art}" aria-label="${lbl}"${aus ? ' disabled' : ''}>${icon(k)}</button>`;
    const griff = (art, lbl) => (ro ? '' : `<span class="abf-griff" data-griff="${art}" title="${lbl}">${icon('griff')}</span>`);
    return bl.map((b, bi) => {
      const titel = b.bereich || OHNE;
      const n = b.ids.reduce((s, id) => s + info.get(id).n, 0);
      const gruppen = b.ids.map((id, gi) => {
        const g = info.get(id);
        return `<li class="abf-g" data-gid="${esc(id)}">${griff('g', 'Gruppe ziehen')}
          <span class="abf-gt"><span class="abf-gn">${esc(g.name)}${g.bereich !== b.bereich ? '<span class="abf-neu">Bereich neu</span>' : ''}</span><small class="abf-z">${plural(g.n, 'Artikel', 'Artikel')}</small></span>
          ${ro ? '' : `<span class="abf-btns">${pfeil('g-hoch', 'up', gi === 0, `Gruppe „${esc(g.name)}“ nach oben`)}${pfeil('g-runter', 'down', gi === b.ids.length - 1, `Gruppe „${esc(g.name)}“ nach unten`)}</span>`}</li>`;
      }).join('');
      return `<li class="abf-ber${b.bereich ? '' : ' ohne'}" data-bi="${bi}" data-bereich="${esc(b.bereich)}">
        <div class="abf-bk">${griff('b', 'Bereich mit allen Gruppen ziehen')}
          <div class="abf-bt"><b>${esc(titel)}</b><small>${plural(b.ids.length, 'Gruppe', 'Gruppen')} · ${plural(n, 'Artikel', 'Artikel')}</small></div>
          ${ro ? '' : `<span class="abf-btns">${pfeil('b-hoch', 'up', bi === 0, `Bereich „${esc(titel)}“ nach oben`)}${pfeil('b-runter', 'down', bi === bl.length - 1, `Bereich „${esc(titel)}“ nach unten`)}</span>`}</div>
        <ol class="abf-gr">${gruppen}</ol></li>`;
    }).join('');
  }

  /* Stand unten links; mit Änderungen schützt data-geaendert vor versehentlichem Escape (theme.js) */
  function standZeigen() {
    const geaendert = !nurAnsehen() && zustand() !== start;
    if (geaendert) dlg.dataset.geaendert = '1'; else { delete dlg.dataset.geaendert; delete dlg.dataset.warnung; }
    const el = body.querySelector('#abf-stand');
    if (!el) return;
    el.textContent = geaendert ? 'Geändert – noch nicht übernommen' : 'Unverändert';
    el.classList.toggle('geaendert', geaendert);
  }

  /* Fokus nach einem Pfeil: derselbe Knopf an der neuen Stelle, am Rand der andere Pfeil */
  function fokussieren(f) {
    if (!f) return;
    const g = liste().querySelector(`.abf-g[data-gid="${CSS.escape(f.gid)}"]`);
    if (!g) return;
    const ort = f.block ? g.closest('.abf-ber').querySelector('.abf-bk') : g;
    const b = ort.querySelector(`[data-ab="${f.ab}"]`);
    (b && !b.disabled ? b : ort.querySelector('[data-ab]:not(:disabled)'))?.focus();
  }
  function zeichnen(fokus) {
    liste().innerHTML = listeHTML();
    standZeigen();
    fokussieren(fokus);
  }
  function fehler(t) { const e = body.querySelector('#abf-err'); if (e) e.textContent = t || ''; }

  function laden(daten) {
    d = daten;
    info = new Map(d.gruppen.map((g) => [g.id, { name: g.name, n: g.n, bereich: g.bereich }]));
    bl = bloecke(d.gruppen);
    start = zustand();
    const ro = nurAnsehen();
    const hinweis = d.sperre ? `<p class="abf-hinweis sperre">${icon('lock', 'sm')}<span>${esc(d.sperre.text)}</span></p>`
      : !d.gruppen.length ? `<p class="abf-hinweis">${icon('info', 'sm')}<span>Dieses Angebot enthält noch keine Artikel – es gibt nichts zu ordnen.</span></p>`
        : `<p class="abf-hinweis">${icon('info', 'sm')}<span>Gilt für alle Angebote: Wochenangebot und Kundenangebote zeigen ihre Gruppen in dieser Reihenfolge. Zieht man eine Gruppe in einen anderen Bereich, bekommt sie dessen Bereich. Artikel und Preise bleiben unverändert.</span></p>`;
    body.innerHTML = `<div class="dlg-head"><div><h2 id="abf-titel">${icon('aufbau')}Aufbau des Angebots</h2>
        <p>„${esc(d.angebot)}“: Reihenfolge der Bereiche und ihrer Gruppen.${ro ? '' : ' Am Griff ziehen oder die Pfeile nutzen – gespeichert wird erst mit „Übernehmen“.'}</p></div>
        <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">${hinweis}<p class="form-err" id="abf-err" role="alert"></p>
        <ol class="abf-liste${ro ? ' nur-ansehen' : ''}" id="abf-liste" aria-label="Bereiche und Gruppen in Angebotsreihenfolge"></ol></div>
      <div class="dlg-foot">${ro ? '' : '<span class="abf-stand" id="abf-stand" aria-live="polite"></span>'}<span class="spacer"></span>
        <button type="button" class="btn" data-close>${ro ? 'Schließen' : 'Abbrechen'}</button>${ro ? '' : `<button type="button" class="btn primary" id="abf-ok" data-ab="ok">${icon('check')}Übernehmen</button>`}</div>`;
    zeichnen();
  }

  function oeffnen() {
    const daten = A.daten();
    if (!daten || dlg.open) return;
    laden(daten);
    dlg.showModal();
    (body.querySelector('#abf-liste [data-ab]:not(:disabled)') || body.querySelector('[data-close]')).focus();
  }

  async function uebernehmen() {
    if (nurAnsehen()) { dlg.close(); return; }
    if (zustand() === start) { dlg.close(); toast('Aufbau unverändert – nichts gespeichert.'); return; }
    const ok = body.querySelector('#abf-ok');
    busy = true; dlg.dataset.busy = '1'; fehler('');
    ok.disabled = true;
    ok.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px"></div>Wird übernommen …';
    let r;
    try {
      r = await A.uebernehmen(bl.flatMap((b) => b.ids.map((id) => ({ id, bereich: b.bereich }))), d.stand);
    } catch (e) {
      r = { fehler: e.message || String(e) };
    } finally {
      busy = false; delete dlg.dataset.busy;
    }
    if (r && r.ok) {
      delete dlg.dataset.geaendert;
      dlg.close();
      toast(r.unveraendert ? 'Aufbau unverändert – nichts gespeichert.' : r.gespeichert === false
        ? 'Aufbau übernommen – der Entwurf ist noch nicht gespeichert (Hinweis oben).'
        : 'Aufbau übernommen und im Entwurf gespeichert – gilt für alle Angebote, für Kunden sichtbar nach „Veröffentlichen“.', 6000);
      return;
    }
    if (r && r.konflikt) {
      laden(r.daten);
      fehler(r.daten.sperre ? 'Der Aufbau lässt sich hier inzwischen nicht mehr ändern – nichts übernommen.'
        : `${r.wer || 'Jemand anderes'} hat den Aufbau inzwischen geändert. Das Fenster zeigt jetzt den aktuellen Stand – Ihre Verschiebungen wurden nicht übernommen. Bitte erneut ordnen und übernehmen.`);
      return;
    }
    fehler((r && r.fehler) || 'Nicht übernommen.');
    ok.disabled = false;
    ok.innerHTML = `${icon('check')}Übernehmen`;
  }

  /* ---------- Pfeile ---------- */
  body.addEventListener('click', (e) => {
    const b = e.target.closest('[data-ab]');
    if (!b || busy || zug) return;
    const a = b.dataset.ab;
    if (a === 'ok') { uebernehmen(); return; }
    if (nurAnsehen()) return;
    fehler('');
    if (a === 'b-hoch' || a === 'b-runter') {
      const i = +b.closest('[data-bi]').dataset.bi, j = a === 'b-hoch' ? i - 1 : i + 1;
      if (j < 0 || j >= bl.length) return;
      [bl[i], bl[j]] = [bl[j], bl[i]];
      const gid = bl[j].ids[0];
      normalisieren();
      zeichnen({ gid, block: true, ab: a });
    } else if (a === 'g-hoch' || a === 'g-runter') {
      const li = b.closest('[data-gid]'), ids = bl[+li.closest('[data-bi]').dataset.bi].ids;
      const i = ids.indexOf(li.dataset.gid), j = a === 'g-hoch' ? i - 1 : i + 1;
      if (i < 0 || j < 0 || j >= ids.length) return;
      [ids[i], ids[j]] = [ids[j], ids[i]];
      zeichnen({ gid: li.dataset.gid, ab: a });
    }
  });

  /* ---------- Ziehen (Maus und Touch) ----------
     Das gezogene Element wandert während des Ziehens in der Liste mit (Mitte der Nachbarn als Grenze); Gruppen auch in
     andere Bereiche. Beim Loslassen wird der Zustand aus der Liste gelesen; „pointercancel“ verwirft. Die Ereignisse laufen
     über window, weil das Verschieben im Dokument die Zeigererfassung des Griffs aufheben kann. Am Rand rollt die Liste. */
  function rollbar(el) {
    for (let x = el.parentElement; x && x !== document.body; x = x.parentElement) {
      const o = getComputedStyle(x).overflowY;
      if ((o === 'auto' || o === 'scroll') && x.scrollHeight > x.clientHeight) return x;
    }
    return null;
  }
  function platzieren() {
    const y = zug.y, L = zug.liste;
    if (zug.art === 'b') {
      const vor = [...L.children].find((x) => x !== zug.el && y < x.getBoundingClientRect().top + x.getBoundingClientRect().height / 2) || null;
      if (zug.el.nextElementSibling !== vor) L.insertBefore(zug.el, vor);
      return;
    }
    const bs = [...L.children];
    const ziel = bs.find((x) => y < x.getBoundingClientRect().bottom) || bs[bs.length - 1];
    const ol = ziel.querySelector('.abf-gr');
    const vor = [...ol.children].find((x) => x !== zug.el && y < x.getBoundingClientRect().top + x.getBoundingClientRect().height / 2) || null;
    if (zug.el.parentNode !== ol || zug.el.nextElementSibling !== vor) ol.insertBefore(zug.el, vor);
  }
  function rollen() {
    if (!zug) return;
    if (zug.sc) {
      const r = zug.sc.getBoundingClientRect(), rand = 48;
      let dy = 0;
      if (zug.y < r.top + rand) dy = -Math.min(18, Math.ceil((r.top + rand - zug.y) / 3));
      else if (zug.y > r.bottom - rand) dy = Math.min(18, Math.ceil((zug.y - r.bottom + rand) / 3));
      if (dy) { const v = zug.sc.scrollTop; zug.sc.scrollTop += dy; if (zug.sc.scrollTop !== v) platzieren(); }
    }
    zug.raf = requestAnimationFrame(rollen);
  }
  function bewegen(e) {
    if (!zug || e.pointerId !== zug.pid) return;
    e.preventDefault();
    zug.y = e.clientY;
    platzieren();
  }
  function loslassen(e) {
    if (!zug || e.pointerId !== zug.pid) return;
    const z = zug;
    zug = null;
    cancelAnimationFrame(z.raf);
    window.removeEventListener('pointermove', bewegen);
    window.removeEventListener('pointerup', loslassen);
    window.removeEventListener('pointercancel', loslassen);
    z.liste.classList.remove('beim-ziehen');
    z.el.classList.remove('zieht');
    if (e.type === 'pointercancel' || !z.liste.isConnected) { if (z.liste.isConnected) zeichnen(); return; }
    bl = [...z.liste.children].map((b) => ({ bereich: b.dataset.bereich, ids: [...b.querySelectorAll('.abf-g')].map((g) => g.dataset.gid) }));
    normalisieren();
    const gid = z.art === 'g' ? z.el.dataset.gid : (z.el.querySelector('.abf-g') || {}).dataset?.gid;
    zeichnen();
    const neu = gid && liste().querySelector(`.abf-g[data-gid="${CSS.escape(gid)}"]`);
    const el = neu && (z.art === 'g' ? neu : neu.closest('.abf-ber'));
    if (el) { el.classList.add('abf-gezogen'); setTimeout(() => el.classList.remove('abf-gezogen'), 1500); }
  }
  body.addEventListener('pointerdown', (e) => {
    const h = e.target.closest('[data-griff]');
    if (!h || busy || zug || nurAnsehen() || (e.pointerType === 'mouse' && e.button !== 0)) return;
    e.preventDefault();
    fehler('');
    const L = liste();
    const el = h.closest(h.dataset.griff === 'b' ? '.abf-ber' : '.abf-g');
    zug = { art: h.dataset.griff, el, liste: L, pid: e.pointerId, y: e.clientY, sc: rollbar(L) };
    L.classList.add('beim-ziehen');
    el.classList.add('zieht');
    window.addEventListener('pointermove', bewegen, { passive: false });
    window.addEventListener('pointerup', loslassen);
    window.addEventListener('pointercancel', loslassen);
    zug.raf = requestAnimationFrame(rollen);
  });

  dlg.addEventListener('close', () => {
    if (zug) loslassen({ pointerId: zug.pid, type: 'pointercancel' });
    d = null;
  });
  btn.addEventListener('click', oeffnen);
})();
