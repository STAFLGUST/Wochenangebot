/* STAFL-Plattform · Angebot · Fenster „Aufbau des Angebots“ (Knopf „Editor“ in der Werkzeugleiste von „Angebot bearbeiten“,
   Wunsch des Inhabers 11.11.2026, Artikel 12.11.2026). Zeigt die Bereiche des gewählten Angebots in Angebotsreihenfolge,
   darunter eingerückt ihre Gruppen mit Artikelzahl; Gruppen ohne Bereich bilden an ihrer Stelle einen Block „ohne Bereich“.
   Jede Gruppe lässt sich aufklappen und zeigt ihre Artikel (Art.-Nr., Bezeichnung in diesem Angebot).
   Reihenfolge ändern: Pfeile ↑/↓ (Tastatur, Handy) oder Ziehen am Griff (Maus und Touch über Pointer Events) – ein Bereich
   als Ganzes mit seinen Gruppen, eine Gruppe innerhalb ihres Bereichs oder in einen anderen (bekommt dessen Bereich,
   „Bereich neu“), ein Artikel innerhalb seiner Gruppe oder in eine andere (Ziehen auf eine aufgeklappte Gruppe an die Stelle,
   auf eine zugeklappte ans Ende; dazu die Auswahl „In Gruppe …“ für Handy und Tastatur, „verschoben“).
   Gespeichert wird erst mit „Übernehmen“ – alles in einem Schritt über den Entwurf (admin.js: WA.angebot.aufbau.uebernehmen →
   save_draft mit Revision, Recht angebot.bearbeiten auf dem Server); hat jemand anderes den Aufbau inzwischen geändert,
   übernimmt das Fenster nichts und zeigt den neuen Stand. „Abbrechen“, × und Escape verwerfen (mit Änderungen schließt
   Escape erst beim zweiten Mal, theme.js). Kundenangebot „folgt dem Wochenangebot“: nur ansehen; mit Angebotskategorien
   (Stammdaten) bleiben Bereiche und Gruppen fest, Artikel lassen sich verschieben.
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
  let d = null;          // Daten beim Öffnen (admin.js aufbauDaten): { angebot, std, sperre, gruppen: [{id, name, bereich, n, artikel}], stand }
  let bl = [];           // Blöcke in Angebotsreihenfolge: [{ bereich, ids: [Gruppen-ID …] }]
  let art = new Map();   // Gruppen-ID → [Artikel-ID …] in Reihenfolge
  let info = new Map();  // Gruppen-ID → { name, bereich (beim Öffnen) }
  let ainfo = new Map(); // Artikel-ID → { code, name, gruppe (beim Öffnen) }
  let offen = new Set(); // aufgeklappte Gruppen
  let start = '';        // Zustand beim Öffnen (Vergleich: geändert?)
  let busy = false;
  let zug = null;        // laufendes Ziehen

  const nurAnsehen = () => !d || (d.sperre && d.sperre.art === 'folgt') || !d.gruppen.length;   // nichts änderbar
  const gruppenFest = () => nurAnsehen() || !!d.sperre;                                            // Bereiche und Gruppen fest
  const zustand = () => JSON.stringify([bl.map((b) => [b.bereich, b.ids]), [...art].sort(([a], [b]) => (a < b ? -1 : 1))]);
  const liste = () => body.querySelector('#abf-liste');
  const gname = (gid) => (info.get(gid) || {}).name || '';

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
  const gruppeVon = (aid) => { for (const [g, ids] of art) if (ids.includes(aid)) return g; return null; };

  const pfeil = (ab, k, aus, lbl) => `<button type="button" class="ibtn" data-ab="${ab}" aria-label="${lbl}"${aus ? ' disabled' : ''}>${icon(k)}</button>`;
  const griff = (typ, lbl) => `<span class="abf-griff" data-griff="${typ}" title="${lbl}">${icon('griff')}</span>`;
  /* Auswahl „In Gruppe …“: alle anderen Gruppen des Angebots, nach Bereich gegliedert */
  function zuHTML(aid, gid) {
    const a = ainfo.get(aid);
    const opt = bl.map((b) => `<optgroup label="${esc(b.bereich || OHNE)}">${b.ids.filter((g) => g !== gid).map((g) => `<option value="${esc(g)}">${esc(gname(g))}</option>`).join('')}</optgroup>`).join('');
    return `<select class="abf-zu" data-zu aria-label="„${esc(a.name)}“ in eine andere Gruppe verschieben"><option value="">In Gruppe …</option>${opt}</select>`;
  }
  function artikelHTML(gid) {
    const ids = art.get(gid) || [], fest = nurAnsehen();
    if (!ids.length) return '<li class="abf-a abf-leer">Keine Artikel – die Gruppe entfällt in diesem Angebot.</li>';
    return ids.map((aid, i) => {
      const a = ainfo.get(aid);
      return `<li class="abf-a" data-aid="${esc(aid)}">${fest ? '' : griff('a', 'Artikel ziehen')}
        <span class="abf-an">${a.code ? `<span class="abf-nr">${esc(a.code)}</span>` : ''}<span class="abf-ab">${esc(a.name)}</span>${a.gruppe !== gid ? '<span class="abf-neu">verschoben</span>' : ''}</span>
        ${fest ? '' : `${zuHTML(aid, gid)}<span class="abf-btns">${pfeil('a-hoch', 'up', i === 0, `Artikel „${esc(a.name)}“ nach oben`)}${pfeil('a-runter', 'down', i === ids.length - 1, `Artikel „${esc(a.name)}“ nach unten`)}</span>`}</li>`;
    }).join('');
  }
  function listeHTML() {
    const gf = gruppenFest();
    return bl.map((b, bi) => {
      const titel = b.bereich || OHNE;
      const n = b.ids.reduce((s, id) => s + (art.get(id) || []).length, 0);
      const gruppen = b.ids.map((id, gi) => {
        const g = info.get(id), auf = offen.has(id), na = (art.get(id) || []).length;
        return `<li class="abf-g${auf ? ' offen' : ''}" data-gid="${esc(id)}"><div class="abf-gk">${gf ? '' : griff('g', 'Gruppe ziehen')}
          <button type="button" class="abf-auf" data-ab="g-auf" aria-expanded="${auf}" aria-controls="abf-a-${esc(id)}" title="${auf ? 'Artikel ausblenden' : 'Artikel zeigen'}">${icon('chev', 'sm abf-chev')}<span class="abf-gt"><span class="abf-gn">${esc(g.name)}${g.bereich !== b.bereich ? '<span class="abf-neu">Bereich neu</span>' : ''}</span><small class="abf-z">${plural(na, 'Artikel', 'Artikel')}</small></span></button>
          ${gf ? '' : `<span class="abf-btns">${pfeil('g-hoch', 'up', gi === 0, `Gruppe „${esc(g.name)}“ nach oben`)}${pfeil('g-runter', 'down', gi === b.ids.length - 1, `Gruppe „${esc(g.name)}“ nach unten`)}</span>`}</div>
          <ol class="abf-art" id="abf-a-${esc(id)}" aria-label="Artikel der Gruppe ${esc(g.name)}"${auf ? '' : ' hidden'}>${auf ? artikelHTML(id) : ''}</ol></li>`;
      }).join('');
      return `<li class="abf-ber${b.bereich ? '' : ' ohne'}" data-bi="${bi}" data-bereich="${esc(b.bereich)}">
        <div class="abf-bk">${gf ? '' : griff('b', 'Bereich mit allen Gruppen ziehen')}
          <div class="abf-bt"><b>${esc(titel)}</b><small>${plural(b.ids.length, 'Gruppe', 'Gruppen')} · ${plural(n, 'Artikel', 'Artikel')}</small></div>
          ${gf ? '' : `<span class="abf-btns">${pfeil('b-hoch', 'up', bi === 0, `Bereich „${esc(titel)}“ nach oben`)}${pfeil('b-runter', 'down', bi === bl.length - 1, `Bereich „${esc(titel)}“ nach unten`)}</span>`}</div>
        <ol class="abf-gr">${gruppen}</ol></li>`;
    }).join('');
  }

  /* Stand unten links; mit Änderungen schützt data-geaendert vor versehentlichem Escape (theme.js) */
  function standZeigen(meldung) {
    const geaendert = !nurAnsehen() && zustand() !== start;
    if (geaendert) dlg.dataset.geaendert = '1'; else { delete dlg.dataset.geaendert; delete dlg.dataset.warnung; }
    const el = body.querySelector('#abf-stand');
    if (el) {
      el.textContent = meldung || (geaendert ? 'Geändert – noch nicht übernommen' : 'Unverändert');
      el.classList.toggle('geaendert', geaendert);
    }
    const alle = body.querySelector('#abf-alle');
    if (alle) alle.textContent = offen.size >= info.size ? 'Artikel ausblenden' : 'Alle Artikel zeigen';
  }

  /* Fokus nach einer Aktion: derselbe Knopf an der neuen Stelle, am Rand der andere Pfeil */
  function fokussieren(f) {
    if (!f) return;
    const L = liste();
    const el = f.aid ? L.querySelector(`.abf-a[data-aid="${CSS.escape(f.aid)}"]`) : L.querySelector(`.abf-g[data-gid="${CSS.escape(f.gid)}"]`);
    if (!el) return;
    const ort = f.block ? el.closest('.abf-ber').querySelector('.abf-bk') : f.aid ? el : el.querySelector('.abf-gk');
    const gegen = f.ab.includes('hoch') ? f.ab.replace('hoch', 'runter') : f.ab.replace('runter', 'hoch');
    const b = [ort.querySelector(`[data-ab="${f.ab}"]`), ort.querySelector(`[data-ab="${gegen}"]`)].find((x) => x && !x.disabled);
    (b || ort.querySelector('[data-ab]:not(:disabled), select'))?.focus();
  }
  function zeichnen(fokus, meldung) {
    const sc = body.querySelector('.dlg-body'), y = sc ? sc.scrollTop : 0;
    liste().innerHTML = listeHTML();
    if (sc) sc.scrollTop = y;
    standZeigen(meldung);
    fokussieren(fokus);
  }
  function fehler(t) { const e = body.querySelector('#abf-err'); if (e) e.textContent = t || ''; }
  function aufleuchten(sel) {
    const el = liste().querySelector(sel);
    if (el) { el.classList.add('abf-gezogen'); setTimeout(() => el.classList.remove('abf-gezogen'), 1500); }
  }

  function laden(daten) {
    d = daten;
    info = new Map(d.gruppen.map((g) => [g.id, { name: g.name, bereich: g.bereich }]));
    ainfo = new Map(d.gruppen.flatMap((g) => g.artikel.map((a) => [a.id, { code: a.code, name: a.name, gruppe: g.id }])));
    art = new Map(d.gruppen.map((g) => [g.id, g.artikel.map((a) => a.id)]));
    offen = new Set([...offen].filter((g) => info.has(g)));
    bl = bloecke(d.gruppen);
    start = zustand();
    const ro = nurAnsehen();
    const hinweis = d.sperre ? `<p class="abf-hinweis sperre">${icon('lock', 'sm')}<span>${esc(d.sperre.text)}</span></p>` : '';
    const info2 = !d.gruppen.length ? `<p class="abf-hinweis">${icon('info', 'sm')}<span>Dieses Angebot enthält noch keine Artikel – es gibt nichts zu ordnen.</span></p>`
      : ro ? '' : `<p class="abf-hinweis">${icon('info', 'sm')}<span>Gilt für alle Angebote: Gruppen und Artikel stehen in jedem Angebot, das sie enthält, an dieser Stelle; ein verschobener Artikel wechselt die Gruppe in allen Angeboten. Zieht man eine Gruppe in einen anderen Bereich, bekommt sie dessen Bereich. Preise bleiben unverändert.</span></p>`;
    body.innerHTML = `<div class="dlg-head"><div><h2 id="abf-titel">${icon('aufbau')}Aufbau des Angebots</h2>
        <p>„${esc(d.angebot)}“: Reihenfolge der Bereiche, Gruppen und Artikel.${ro ? '' : ' Gruppe anklicken zeigt ihre Artikel. Am Griff ziehen oder die Pfeile nutzen – gespeichert wird erst mit „Übernehmen“.'}</p></div>
        <button type="button" class="btn icon ghost" data-close aria-label="Schließen">${icon('x')}</button></div>
      <div class="dlg-body">${hinweis}${info2}<p class="form-err" id="abf-err" role="alert"></p>
        ${d.gruppen.length ? '<div class="abf-werkzeug"><button type="button" class="btn sm ghost" id="abf-alle" data-ab="alle"></button></div>' : ''}
        <ol class="abf-liste${gruppenFest() ? ' nur-ansehen' : ''}${ro ? ' artikel-fest' : ''}" id="abf-liste" aria-label="Bereiche, Gruppen und Artikel in Angebotsreihenfolge"></ol></div>
      <div class="dlg-foot">${ro ? '' : '<span class="abf-stand" id="abf-stand" aria-live="polite"></span>'}<span class="spacer"></span>
        <button type="button" class="btn" data-close>${ro ? 'Schließen' : 'Abbrechen'}</button>${ro ? '' : `<button type="button" class="btn primary" id="abf-ok" data-ab="ok">${icon('check')}Übernehmen</button>`}</div>`;
    zeichnen();
  }

  function oeffnen() {
    const daten = A.daten();
    if (!daten || dlg.open) return;
    offen = new Set();
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
      r = await A.uebernehmen(bl.flatMap((b) => b.ids.map((id) => ({ id, bereich: b.bereich, artikel: (art.get(id) || []).slice() }))), d.stand);
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
      fehler(r.grund === 'folgt' ? 'Dieses Angebot folgt inzwischen dem Wochenangebot – nichts übernommen.'
        : r.grund === 'kategorien' ? 'Bereiche und Gruppen ordnen inzwischen die Angebotskategorien – nichts übernommen. Artikel lassen sich weiter verschieben.'
          : `${r.wer || 'Jemand anderes'} hat den Aufbau inzwischen geändert. Das Fenster zeigt jetzt den aktuellen Stand – Ihre Verschiebungen wurden nicht übernommen. Bitte erneut ordnen und übernehmen.`);
      return;
    }
    fehler((r && r.fehler) || 'Nicht übernommen.');
    ok.disabled = false;
    ok.innerHTML = `${icon('check')}Übernehmen`;
  }

  /* Artikel ans Ende einer anderen Gruppe (Auswahl „In Gruppe …“, Ziehen auf eine zugeklappte Gruppe) */
  function artikelNach(aid, ziel) {
    const von = gruppeVon(aid);
    if (!von || !art.has(ziel) || von === ziel) return null;
    const ids = art.get(von), i = ids.indexOf(aid);
    ids.splice(i, 1);
    art.get(ziel).push(aid);
    return { von, rest: ids[i] || ids[i - 1] || null };
  }

  /* ---------- Pfeile, Aufklappen, Auswahl ---------- */
  body.addEventListener('click', (e) => {
    const b = e.target.closest('[data-ab]');
    if (!b || busy || zug) return;
    const a = b.dataset.ab;
    if (a === 'ok') { uebernehmen(); return; }
    if (a === 'g-auf') {
      const gid = b.closest('[data-gid]').dataset.gid;
      if (offen.has(gid)) offen.delete(gid); else offen.add(gid);
      zeichnen({ gid, ab: 'g-auf' });
      return;
    }
    if (a === 'alle') {
      offen = offen.size >= info.size ? new Set() : new Set(info.keys());
      zeichnen();
      body.querySelector('#abf-alle')?.focus();
      return;
    }
    if (nurAnsehen()) return;
    fehler('');
    if ((a === 'b-hoch' || a === 'b-runter') && !gruppenFest()) {
      const i = +b.closest('[data-bi]').dataset.bi, j = a === 'b-hoch' ? i - 1 : i + 1;
      if (j < 0 || j >= bl.length) return;
      [bl[i], bl[j]] = [bl[j], bl[i]];
      const gid = bl[j].ids[0];
      normalisieren();
      zeichnen({ gid, block: true, ab: a });
    } else if ((a === 'g-hoch' || a === 'g-runter') && !gruppenFest()) {
      const li = b.closest('[data-gid]'), ids = bl[+li.closest('[data-bi]').dataset.bi].ids;
      const i = ids.indexOf(li.dataset.gid), j = a === 'g-hoch' ? i - 1 : i + 1;
      if (i < 0 || j < 0 || j >= ids.length) return;
      [ids[i], ids[j]] = [ids[j], ids[i]];
      zeichnen({ gid: li.dataset.gid, ab: a });
    } else if (a === 'a-hoch' || a === 'a-runter') {
      const aid = b.closest('[data-aid]').dataset.aid, ids = art.get(gruppeVon(aid));
      const i = ids.indexOf(aid), j = a === 'a-hoch' ? i - 1 : i + 1;
      if (i < 0 || j < 0 || j >= ids.length) return;
      [ids[i], ids[j]] = [ids[j], ids[i]];
      zeichnen({ aid, ab: a });
    }
  });
  body.addEventListener('change', (e) => {
    const s = e.target.closest('[data-zu]');
    if (!s || !s.value || busy || nurAnsehen()) return;
    const aid = s.closest('[data-aid]').dataset.aid, ziel = s.value;
    const r = artikelNach(aid, ziel);
    if (!r) return;
    fehler('');
    const name = ainfo.get(aid).name;
    zeichnen(r.rest ? { aid: r.rest, ab: 'zu' } : { gid: r.von, ab: 'g-auf' }, `„${name}“ → ans Ende von „${gname(ziel)}“`);
    aufleuchten(`.abf-g[data-gid="${CSS.escape(ziel)}"] > .abf-gk`);
  });

  /* ---------- Ziehen (Maus und Touch) ----------
     Das gezogene Element wandert während des Ziehens in der Liste mit (Mitte der Nachbarn als Grenze); Gruppen auch in andere
     Bereiche, Artikel in andere aufgeklappte Gruppen – über einer zugeklappten Gruppe wird diese markiert und der Artikel beim
     Loslassen an ihr Ende gesetzt. Beim Loslassen wird der Zustand aus der Liste gelesen; „pointercancel“ verwirft. Die
     Ereignisse laufen über window, weil das Verschieben im Dokument die Zeigererfassung des Griffs aufheben kann. Am Rand
     rollt die Liste. */
  function rollbar(el) {
    for (let x = el.parentElement; x && x !== document.body; x = x.parentElement) {
      const o = getComputedStyle(x).overflowY;
      if ((o === 'auto' || o === 'scroll') && x.scrollHeight > x.clientHeight) return x;
    }
    return null;
  }
  const mitte = (x, y) => { const r = x.getBoundingClientRect(); return y < r.top + r.height / 2; };
  function einfuegen(ol, y) {
    const vor = [...ol.children].find((x) => x !== zug.el && !x.classList.contains('abf-leer') && mitte(x, y)) || null;
    if (zug.el.parentNode !== ol || zug.el.nextElementSibling !== vor) ol.insertBefore(zug.el, vor);
  }
  function platzieren() {
    const y = zug.y, L = zug.liste;
    if (zug.art === 'b') {
      const vor = [...L.children].find((x) => x !== zug.el && mitte(x, y)) || null;
      if (zug.el.nextElementSibling !== vor) L.insertBefore(zug.el, vor);
      return;
    }
    if (zug.art === 'g') {
      const bs = [...L.children];
      const ziel = bs.find((x) => y < x.getBoundingClientRect().bottom) || bs[bs.length - 1];
      einfuegen(ziel.querySelector('.abf-gr'), y);
      return;
    }
    const gs = [...L.querySelectorAll('.abf-g')];
    const ziel = gs.find((x) => y < x.getBoundingClientRect().bottom) || gs[gs.length - 1];
    if (zug.zu && zug.zu !== ziel) zug.zu.classList.remove('abf-ziel');
    zug.zu = null;
    if (ziel.classList.contains('offen')) einfuegen(ziel.querySelector('.abf-art'), y);   // an die Stelle
    else { zug.zu = ziel; ziel.classList.add('abf-ziel'); }                                // zugeklappt: ans Ende
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
    if (z.zu) z.zu.classList.remove('abf-ziel');
    if (e.type === 'pointercancel' || !z.liste.isConnected) { if (z.liste.isConnected) zeichnen(); return; }
    if (z.art === 'a') {
      const aid = z.el.dataset.aid;
      for (const g of z.liste.querySelectorAll('.abf-g.offen')) {
        const ids = [...g.querySelectorAll('.abf-a[data-aid]')].map((x) => x.dataset.aid);
        art.set(g.dataset.gid, z.zu ? ids.filter((x) => x !== aid) : ids);
      }
      if (z.zu) art.get(z.zu.dataset.gid).push(aid);
      zeichnen(null, z.zu ? `„${ainfo.get(aid).name}“ → ans Ende von „${gname(z.zu.dataset.gid)}“` : '');
      if (z.zu) aufleuchten(`.abf-g[data-gid="${CSS.escape(z.zu.dataset.gid)}"] > .abf-gk`);
      else aufleuchten(`.abf-a[data-aid="${CSS.escape(aid)}"]`);
      return;
    }
    bl = [...z.liste.children].map((b) => ({ bereich: b.dataset.bereich, ids: [...b.querySelectorAll(':scope > .abf-gr > .abf-g')].map((g) => g.dataset.gid) }));
    normalisieren();
    const gid = z.art === 'g' ? z.el.dataset.gid : (z.el.querySelector('.abf-g') || {}).dataset?.gid;
    zeichnen();
    if (gid) aufleuchten(z.art === 'g' ? `.abf-g[data-gid="${CSS.escape(gid)}"] > .abf-gk` : `.abf-ber:has(.abf-g[data-gid="${CSS.escape(gid)}"]) > .abf-bk`);
  }
  body.addEventListener('pointerdown', (e) => {
    const h = e.target.closest('[data-griff]');
    if (!h || busy || zug || nurAnsehen() || (e.pointerType === 'mouse' && e.button !== 0)) return;
    if (h.dataset.griff !== 'a' && gruppenFest()) return;
    e.preventDefault();
    fehler('');
    const L = liste();
    const el = h.closest(h.dataset.griff === 'b' ? '.abf-ber' : h.dataset.griff === 'g' ? '.abf-g' : '.abf-a');
    zug = { art: h.dataset.griff, el, liste: L, pid: e.pointerId, y: e.clientY, sc: rollbar(L), zu: null };
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
