/* ==========================================================================
   Verwaltung → Angebotskategorien (Stammdaten, Inhaber 05.11.2026)
   Angebotskategorien sind die Abschnitte des Angebots (z. B. „Eigene Zerlegung, Marke „Fleischmeister““). Jeder Kategorie
   werden VK-Gruppen der Warenwirtschaft zugeordnet, jede VK-Gruppe höchstens einer. Die Reihenfolge der Kategorien und darin
   der VK-Gruppen bestimmt den Aufbau aller Angebote (Editor: OfferCore.nachKategorien, wirksam nach dem Veröffentlichen).
   Daten: Aktionen angebotskategorien / angebotskategorien_save (app/api/module/verwaltung/angebotskategorien.php).
   Vorschlag aus dem Wochenangebot über die Schnittstelle des Angebots (W.angebot.kategorienVorschlag, admin.js).
   Ansehen: stammdaten.sehen, ändern: stammdaten.bearbeiten (prüft der Server).
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  if (!W) return;
  const { $, api, esc, icon, toast, confirmBox, dateTime, plural, fold, SU, may } = W;
  let daten = null;          // Stand des Servers: { rev, kategorien, vk, updatedAt, updatedBy }
  let entwurf = null;        // bearbeitete Kopie: [{ id, name, vk: [] }]
  let geaendert = false;
  let anzahl = {};           // Artikel je VK-Gruppe (nur zur Anzeige, falls lesbar)
  let q = '';
  const host = () => $('#view-kategorien');
  const kopie = (l) => l.map((k) => ({ id: k.id || '', name: k.name, vk: (k.vk || []).map(String) }));
  const vkName = (nr) => { const g = daten && daten.vk.find((x) => x.nr === nr); return g ? g.name : ''; };
  const zugeordnet = () => new Set(entwurf.flatMap((k) => k.vk));
  const frei = () => { const z = zugeordnet(); return daten.vk.filter((g) => !z.has(g.nr)).sort((a, b) => a.nr.localeCompare(b.nr, 'de', { numeric: true })); };
  const artikelText = (nr) => (anzahl[nr] ? plural(anzahl[nr], 'Artikel', 'Artikel') : '');

  async function laden() {
    const r = await api('angebotskategorien');
    daten = { rev: r.rev, kategorien: r.kategorien || [], vk: (r.vk || []).map((g) => ({ nr: String(g.nr), name: g.name || '' })), updatedAt: r.updatedAt, updatedBy: r.updatedBy };
    entwurf = kopie(daten.kategorien);
    geaendert = false;
    try { anzahl = (await api('vkgruppen')).artikel || {}; } catch { anzahl = {}; }
  }
  function markieren() { geaendert = true; render(); }

  function render() {
    const el = host();
    if (!el) return;
    const edit = may('stammdaten.bearbeiten');
    const f = frei(), n = daten.vk.length - f.length;
    const vorschlagDa = !!(W.angebot && W.angebot.kategorienVorschlag);
    const stand = `${plural(entwurf.length, 'Kategorie', 'Kategorien')} · ${n} von ${plural(daten.vk.length, 'VK-Gruppe', 'VK-Gruppen')} zugeordnet${geaendert ? ' · <strong class="ak-offen">nicht gespeichert</strong>' : ''}`;
    el.innerHTML = `
      ${edit ? `<div class="ed-toolbar ak-leiste">
        <span class="ak-stand" id="ak-stand">${stand}</span>
        ${vorschlagDa ? `<button type="button" class="btn" id="ak-vorschlag">${icon('history')}Vorschlag aus dem Wochenangebot</button>` : ''}
        <button type="button" class="btn" id="ak-neu">${icon('plus')}Kategorie anlegen</button>
        <button type="button" class="btn ghost" id="ak-verwerfen"${geaendert ? '' : ' disabled'}>Verwerfen</button>
        <button type="button" class="btn primary" id="ak-speichern"${geaendert ? '' : ' disabled'}>${icon('check')}Speichern</button>
      </div>` : `<p class="ak-stand ak-stand-ro" id="ak-stand">${stand}</p>`}
      <p class="hint ak-hinweis">Die Reihenfolge der Kategorien und darin der VK-Gruppen bestimmt den Aufbau aller Angebote (Wochenangebot und Kundenangebote):
        jede Angebotsgruppe steht in der Kategorie ihrer VK-Gruppe. Im Angebot wirksam nach dem nächsten Veröffentlichen. Ohne Kategorien bleibt die Reihenfolge von Hand.
        ${daten.updatedAt ? `Zuletzt gespeichert ${esc(dateTime(daten.updatedAt))}${daten.updatedBy ? ' von ' + esc(daten.updatedBy) : ''}.` : ''}</p>
      <div class="ak-layout">
        <div class="ak-kats" id="ak-kats">${entwurf.length ? entwurf.map((k, i) => katHTML(k, i, edit, f)).join('') : `<div class="ed-empty"><h3>Noch keine Angebotskategorien</h3><p>${edit ? 'Legen Sie Kategorien an oder übernehmen Sie den Vorschlag aus dem Wochenangebot (heutige Abschnitte und VK-Gruppen).' : 'Es sind noch keine Kategorien angelegt.'}</p></div>`}</div>
        <aside class="gcard ak-frei" aria-labelledby="ak-frei-t">
          <h3 id="ak-frei-t">Ohne Kategorie <span class="g-count">${f.length}</span></h3>
          ${daten.vk.length ? `<div class="search ak-suche">${icon('search')}<input id="ak-q" type="search" autocomplete="off" placeholder="VK-Gruppe finden" aria-label="VK-Gruppen ohne Kategorie durchsuchen" value="${esc(q)}"></div>` : ''}
          <ul class="ak-freiliste" id="ak-freiliste">${freiHTML(f, edit)}</ul>
        </aside>
      </div>`;
  }
  function katHTML(k, i, edit, f) {
    const opts = f.map((g) => `<option value="${esc(g.nr)}">${esc(g.nr)} · ${esc(g.name)}</option>`).join('');
    return `<section class="gcard ak-kat" data-k="${i}">
      <div class="ak-kopf"><span class="ak-pos" aria-hidden="true">${i + 1}</span>
        ${edit ? `<input class="in ak-name" data-ak="name" value="${esc(k.name)}" maxlength="200" aria-label="Bezeichnung der Kategorie ${i + 1}">` : `<h3 class="ak-name">${esc(k.name)}</h3>`}
        <span class="g-count">${plural(k.vk.length, 'VK-Gruppe', 'VK-Gruppen')}</span>
        ${edit ? `<span class="ak-akt">
          <button type="button" class="ibtn" data-ak="k-hoch" aria-label="Kategorie nach oben"${i === 0 ? ' disabled' : ''}>${icon('up')}</button>
          <button type="button" class="ibtn" data-ak="k-runter" aria-label="Kategorie nach unten"${i === entwurf.length - 1 ? ' disabled' : ''}>${icon('down')}</button>
          <button type="button" class="ibtn danger" data-ak="k-weg" aria-label="Kategorie löschen">${icon('trash')}</button></span>` : ''}
      </div>
      <ol class="ak-vks">${k.vk.map((v, j) => `<li data-v="${esc(v)}"><span class="ak-vnr">${esc(v)}</span><span class="ak-vname">${esc(vkName(v) || 'nicht in der VK-Gruppen-Liste')}</span><span class="ak-anz">${esc(artikelText(v))}</span>
        ${edit ? `<span class="ak-akt"><button type="button" class="ibtn" data-ak="v-hoch" aria-label="VK-Gruppe ${esc(v)} nach oben"${j === 0 ? ' disabled' : ''}>${icon('up')}</button><button type="button" class="ibtn" data-ak="v-runter" aria-label="VK-Gruppe ${esc(v)} nach unten"${j === k.vk.length - 1 ? ' disabled' : ''}>${icon('down')}</button><button type="button" class="ibtn" data-ak="v-weg" aria-label="VK-Gruppe ${esc(v)} aus der Kategorie nehmen">${icon('x')}</button></span>` : ''}</li>`).join('')
        || '<li class="ak-leer">Noch keine VK-Gruppe zugeordnet.</li>'}</ol>
      ${edit && f.length ? `<div class="ak-add"><select class="in" data-ak="v-dazu" aria-label="VK-Gruppe zu „${esc(k.name)}“ hinzufügen"><option value="">VK-Gruppe hinzufügen …</option>${opts}</select></div>` : ''}
    </section>`;
  }
  function freiHTML(f, edit) {
    const toks = SU.woerter(q);
    const liste = f.filter((g) => SU.passt(toks, SU.heu(g.nr, g.name)));
    if (!daten.vk.length) return '<li class="ak-leer">Die VK-Gruppen-Liste ist leer – zuerst unter Stammdaten → VK-Gruppen importieren.</li>';
    if (!f.length) return '<li class="ak-leer">Alle VK-Gruppen sind einer Kategorie zugeordnet.</li>';
    if (!liste.length) return '<li class="ak-leer">Keine Treffer.</li>';
    const kOpts = entwurf.map((k, i) => `<option value="${i}">${esc(k.name)}</option>`).join('');
    return liste.map((g) => `<li data-v="${esc(g.nr)}"><span class="ak-vnr">${esc(g.nr)}</span><span class="ak-vname">${esc(g.name)}</span><span class="ak-anz">${esc(artikelText(g.nr))}</span>
      ${edit && entwurf.length ? `<select class="in ak-zu" data-ak="zu" aria-label="VK-Gruppe ${esc(g.nr)} einer Kategorie zuordnen"><option value="">zuordnen …</option>${kOpts}</select>` : ''}</li>`).join('');
  }

  function neuerName() {
    const namen = new Set(entwurf.map((k) => fold(k.name)));
    let n = 1, name = 'Neue Kategorie';
    while (namen.has(fold(name))) name = `Neue Kategorie ${++n}`;
    return name;
  }
  async function speichern() {
    const leer = entwurf.find((k) => !k.name.trim());
    if (leer) { toast('Jede Kategorie braucht eine Bezeichnung.'); return; }
    const btn = $('#ak-speichern');
    if (btn) btn.disabled = true;
    try {
      const r = await api('angebotskategorien_save', { body: { rev: daten.rev, kategorien: entwurf } });
      daten.rev = r.rev; daten.kategorien = r.kategorien; daten.updatedAt = r.updatedAt; daten.updatedBy = r.updatedBy;
      entwurf = kopie(daten.kategorien); geaendert = false;
      render();
      const neu = W.angebot && W.angebot.kategorienGeaendert ? await W.angebot.kategorienGeaendert() : false;
      toast(`Angebotskategorien gespeichert.${neu ? ' Der Entwurf des Angebots ist danach geordnet –' : ' Das Angebot wird danach aufgebaut –'} wirksam nach dem nächsten Veröffentlichen.`, 7000);
    } catch (e) {
      if (btn) btn.disabled = false;
      if (e.status === 409 && await confirmBox('Inzwischen geändert', `${esc(e.message)} Ihre Änderungen hier gehen dabei verloren.`, 'Neu laden')) { await laden(); render(); return; }
      toast(e.message, 7000);
    }
  }

  host() && host().addEventListener('click', async (e) => {
    const t = e.target.closest('button');
    if (!t || !may('stammdaten.bearbeiten')) return;
    if (t.id === 'ak-speichern') { speichern(); return; }
    if (t.id === 'ak-verwerfen') { entwurf = kopie(daten.kategorien); geaendert = false; render(); return; }
    if (t.id === 'ak-neu') {
      entwurf.push({ id: '', name: neuerName(), vk: [] }); markieren();
      const inp = host().querySelector(`.ak-kat[data-k="${entwurf.length - 1}"] [data-ak="name"]`);
      if (inp) { inp.focus(); inp.select(); }
      return;
    }
    if (t.id === 'ak-vorschlag') {
      const v = W.angebot.kategorienVorschlag();
      if (!v || !v.length) { toast('Kein Vorschlag möglich: Das Wochenangebot ist hier nicht geladen oder hat keine Abschnitte.', 6000); return; }
      if (entwurf.length && !(await confirmBox('Vorschlag übernehmen?', `Die ${plural(entwurf.length, 'Kategorie', 'Kategorien')} hier werden durch den Vorschlag aus dem Wochenangebot ersetzt (${plural(v.length, 'Kategorie', 'Kategorien')}). Gespeichert wird erst mit „Speichern“.`, 'Ersetzen'))) return;
      const bekannt = new Map(entwurf.map((k) => [fold(k.name), k.id]));
      entwurf = v.map((k) => ({ id: bekannt.get(fold(k.name)) || '', name: k.name, vk: k.vk.map(String) }));
      markieren();
      toast(`Vorschlag übernommen: ${plural(entwurf.length, 'Kategorie', 'Kategorien')} – bitte prüfen und speichern.`, 6000);
      return;
    }
    const kat = t.closest('.ak-kat'), i = kat ? Number(kat.dataset.k) : -1, a = t.dataset.ak;
    if (i < 0 || !a) return;
    const k = entwurf[i];
    if (a === 'k-hoch' || a === 'k-runter') { const j = a === 'k-hoch' ? i - 1 : i + 1; [entwurf[i], entwurf[j]] = [entwurf[j], entwurf[i]]; markieren(); return; }
    if (a === 'k-weg') {
      if (k.vk.length && !(await confirmBox('Kategorie löschen?', `„${esc(k.name)}“ wird gelöscht; ${plural(k.vk.length, 'VK-Gruppe', 'VK-Gruppen')} ${k.vk.length === 1 ? 'ist' : 'sind'} danach ohne Kategorie.`, 'Löschen', true))) return;
      entwurf.splice(i, 1); markieren(); return;
    }
    const li = t.closest('li[data-v]'), v = li && li.dataset.v, j = v ? k.vk.indexOf(v) : -1;
    if (j < 0) return;
    if (a === 'v-hoch' || a === 'v-runter') { const m = a === 'v-hoch' ? j - 1 : j + 1; [k.vk[j], k.vk[m]] = [k.vk[m], k.vk[j]]; markieren(); return; }
    if (a === 'v-weg') { k.vk.splice(j, 1); markieren(); }
  });
  host() && host().addEventListener('change', (e) => {
    const t = e.target;
    if (!may('stammdaten.bearbeiten')) return;
    if (t.dataset.ak === 'name') {
      const i = Number(t.closest('.ak-kat').dataset.k), name = t.value.replace(/\s+/g, ' ').trim();
      if (!name) { t.value = entwurf[i].name; toast('Die Kategorie braucht eine Bezeichnung.'); return; }
      if (entwurf.some((k, x) => x !== i && fold(k.name) === fold(name))) { t.value = entwurf[i].name; toast(`Die Kategorie „${name}“ gibt es schon.`); return; }
      entwurf[i].name = name; markieren(); return;
    }
    if (t.dataset.ak === 'v-dazu' && t.value) { entwurf[Number(t.closest('.ak-kat').dataset.k)].vk.push(t.value); markieren(); return; }
    if (t.dataset.ak === 'zu' && t.value !== '') { entwurf[Number(t.value)].vk.push(t.closest('li[data-v]').dataset.v); markieren(); }
  });
  host() && host().addEventListener('input', (e) => {
    if (e.target.id !== 'ak-q') return;
    q = e.target.value;
    const l = $('#ak-freiliste');
    if (l) l.innerHTML = freiHTML(frei(), may('stammdaten.bearbeiten'));
  });

  W.views.kategorien = async function () {
    const el = host();
    if (!daten) el.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Angebotskategorien werden geladen …</div>';
    try { if (!daten || !geaendert) await laden(); } catch (e) { el.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    render();
  };
})();
