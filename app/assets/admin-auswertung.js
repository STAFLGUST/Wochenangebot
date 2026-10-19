/* ==========================================================================
   Wochenangebot – Eingabebereich, Auswertung
   Karte der Kunden-Anmeldungen: ungefährer Ort (aus der IP-Adresse) je Anmeldung, Liste, Filter nach Zeitraum und Kunde.
   Die Landkarte (app/assets/karte.json, Natural Earth) zeichnet die Seite selbst – keine fremden Kartendienste.
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const { $, $$, api, esc, icon, toast, dateTime, plural } = W;

  const RANGES = [[1, 'Heute'], [7, '7 Tage'], [30, '30 Tage'], [90, '90 Tage']];
  const DEV = { mobil: 'Handy', tablet: 'Tablet', desktop: 'Computer' };
  const VIA = { passwort: 'Anmeldung', link: 'Link aus E-Mail' };
  /* Orientierung auf der Karte (nur bei näherer Ansicht) */
  const STAEDTE = [['Hamburg', 53.55, 10.0], ['Berlin', 52.52, 13.405], ['München', 48.137, 11.575], ['Köln', 50.937, 6.96], ['Frankfurt', 50.11, 8.682],
    ['Hannover', 52.375, 9.732], ['Leipzig', 51.34, 12.375], ['Stuttgart', 48.776, 9.18], ['Bremen', 53.08, 8.8], ['Dresden', 51.05, 13.738], ['Nürnberg', 49.452, 11.077], ['Kiel', 54.323, 10.123]];
  const regionName = (() => { try { const d = new Intl.DisplayNames(['de'], { type: 'region' }); return (c) => { try { return d.of(c); } catch (e) { return c; } }; } catch (e) { return (c) => c; } })();

  let tage = 30, kunde = '', data = null, karte = null, karteLaden = null, sel = null;
  let vb = null, full = null;   // aktueller und gesamter Kartenausschnitt [x, y, w, h]

  /* Web-Mercator wie werkzeuge/karte_bauen.py: 1 Einheit = 0,01 Längengrad */
  const px = (lon) => (lon + 180) * 100;
  const py = (lat) => { const l = Math.max(-85, Math.min(85, lat)) * Math.PI / 180; return (180 - Math.log(Math.tan(Math.PI / 4 + l / 2)) * 180 / Math.PI) * 100; };

  const ortName = (e) => (e.city ? e.city + (e.region && e.region !== e.city ? ', ' + e.region : '') : (e.cc ? regionName(e.cc) + ' (Ort unbekannt)' : 'Ort unbekannt'));
  const ortKurz = (e) => (e.city || (e.cc ? regionName(e.cc) : 'unbekannt'));

  function loadKarte() {
    if (karte) return Promise.resolve(karte);
    if (!karteLaden) karteLaden = fetch('../assets/karte.json').then((r) => { if (!r.ok) throw new Error('Karte nicht geladen'); return r.json(); }).then((j) => { karte = j; return j; }).finally(() => { karteLaden = null; });
    return karteLaden;
  }

  /* Anmeldungen am selben Ort zu einem Punkt zusammenfassen */
  function gruppen(list) {
    const m = new Map();
    for (const e of list) {
      if (typeof e.lat !== 'number' || typeof e.lon !== 'number') continue;
      const k = e.lat.toFixed(3) + ',' + e.lon.toFixed(3);
      if (!m.has(k)) m.set(k, { key: k, lat: e.lat, lon: e.lon, x: px(e.lon), y: py(e.lat), items: [], kids: new Set() });
      const g = m.get(k); g.items.push(e); g.kids.add(e.kid);
    }
    return [...m.values()].sort((a, b) => b.items.length - a.items.length);
  }

  function filtered() {
    if (!data) return [];
    return kunde ? data.entries.filter((e) => e.kid === kunde) : data.entries;
  }

  function fitBox(gs) {
    let box;
    if (gs.length) {
      const xs = gs.map((g) => g.x), ys = gs.map((g) => g.y);
      let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      const minW = 700;   // etwa 7 Längengrade: mindestens ein Bundesland-Umfeld
      if (x1 - x0 < minW) { const c = (x0 + x1) / 2; x0 = c - minW / 2; x1 = c + minW / 2; }
      if (y1 - y0 < minW * 0.6) { const c = (y0 + y1) / 2; y0 = c - minW * 0.3; y1 = c + minW * 0.3; }
      const pw = (x1 - x0) * 0.18, ph = (y1 - y0) * 0.18;
      box = [x0 - pw, y0 - ph, x1 - x0 + 2 * pw, y1 - y0 + 2 * ph];
    } else {
      box = [px(5.2), py(55.4), px(15.8) - px(5.2), py(47) - py(55.4)];   // Deutschland
    }
    return aspect(box);
  }
  /* Ausschnitt an das Seitenverhältnis der Kartenfläche anpassen */
  function aspect(b) {
    const svg = $('#aw-svg');
    const r = svg ? svg.clientWidth / Math.max(1, svg.clientHeight) : 1.6;
    let [x, y, w, h] = b;
    if (w / h < r) { const nw = h * r; x -= (nw - w) / 2; w = nw; } else { const nh = w / r; y -= (nh - h) / 2; h = nh; }
    return [x, y, w, h];
  }

  async function render() {
    const host = $('#view-auswertung');
    if (!data) host.innerHTML = '<div class="loading" style="justify-content:center;padding:48px 0"><div class="spinner"></div>Auswertung wird geladen …</div>';
    try {
      [data] = await Promise.all([api('auswertung', { query: '&tage=' + tage }), loadKarte()]);
    } catch (e) { host.innerHTML = `<div class="err-box">${esc(e.message)}</div>`; return; }
    if (kunde && !data.kunden.some((k) => k.id === kunde)) kunde = '';
    sel = null;
    const list = filtered();
    const gs = gruppen(list);
    const kunden = [...data.kunden].sort((a, b) => a.firma.localeCompare(b.firma, 'de'));
    const nK = new Set(list.map((e) => e.kid)).size;
    const od = data.ortsdaten;
    host.innerHTML = `
      <div class="ed-toolbar aw-bar">
        <div class="seg txt" role="group" aria-label="Zeitraum">${RANGES.map(([k, l]) => `<button type="button" data-aw-tage="${k}" aria-pressed="${tage === k}">${l}</button>`).join('')}</div>
        <label class="select"><span class="sr-only">Kunde</span><select id="aw-kunde"><option value="">Alle Kunden</option>${kunden.map((k) => `<option value="${esc(k.id)}"${k.id === kunde ? ' selected' : ''}>${esc(k.firma)}</option>`).join('')}</select>${icon('chev', 'sm')}</label>
        <span class="aw-sum" id="aw-sum">${plural(list.length, 'Anmeldung', 'Anmeldungen')} · ${plural(nK, 'Kunde', 'Kunden')} · ${plural(gs.length, 'Ort', 'Orte')}</span>
      </div>
      ${!od ? `<div class="notice aw-note">${icon('info')}<p><strong>Ortsdaten fehlen.</strong> Ohne sie wird nur das Land erkannt. ${data.kannAktualisieren ? 'Bitte einmal „Ortsdaten laden“ wählen (dauert 1–3 Minuten).' : 'Bitte einen Administrator bitten, die Ortsdaten zu laden.'}</p>${data.kannAktualisieren ? `<button type="button" class="btn primary" data-aw="ort">${icon('download')}Ortsdaten laden</button>` : ''}</div>` : ''}
      <section class="gcard aw-map" aria-label="Karte der Anmeldeorte">
        <svg id="aw-svg" role="img" aria-label="Karte: ${esc(plural(gs.length, 'Ort', 'Orte'))} mit Kunden-Anmeldungen">
          <g id="aw-land">${karte.laender.map((d) => `<path d="${d}"/>`).join('')}</g>
          <g id="aw-ref"></g><g id="aw-pts"></g>
        </svg>
        <div class="aw-zoom" role="group" aria-label="Kartenausschnitt">
          <button type="button" class="btn icon" data-aw="in" aria-label="Vergrößern">${icon('plus')}</button>
          <button type="button" class="btn icon" data-aw="out" aria-label="Verkleinern"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M6 12h12"/></svg></button>
          <button type="button" class="btn icon" data-aw="fit" aria-label="Alle Anmeldungen zeigen" title="Alle Anmeldungen zeigen"><svg class="i" viewBox="0 0 24 24" aria-hidden="true"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button>
        </div>
        <div class="aw-pop" id="aw-pop" role="dialog" aria-live="polite" hidden></div>
        ${!gs.length ? `<div class="aw-empty">${list.length ? 'Für diese Anmeldungen ist kein Ort bekannt.' : 'Im gewählten Zeitraum hat sich kein Kunde angemeldet.'}</div>` : ''}
      </section>
      ${list.length ? `<section class="gcard aw-list"><h3 class="sec-h">Anmeldungen</h3><div class="aw-tw"><table class="etab aw-tab"><thead><tr><th>Zeit</th><th>Kunde</th><th>Ort</th><th class="aw-dev">Gerät</th><th class="aw-via">Art</th></tr></thead><tbody>
        ${list.slice(0, 500).map((e) => `<tr${typeof e.lat === 'number' ? ` data-aw-pt="${e.lat.toFixed(3)},${e.lon.toFixed(3)}" tabindex="0"` : ''}><td class="aw-t">${esc(dateTime(e.t))}</td><td><span class="nm">${esc(firma(e.kid))}</span></td><td>${esc(ortName(e))}${e.cc && e.cc !== 'DE' && e.city ? ` <span class="sub">${esc(regionName(e.cc))}</span>` : ''}</td><td class="aw-dev">${esc(DEV[e.dev] || '–')}</td><td class="aw-via">${esc(VIA[e.via] || '–')}</td></tr>`).join('')}
      </tbody></table></div>${list.length > 500 ? '<p class="hint">Es werden die letzten 500 Anmeldungen angezeigt.</p>' : ''}</section>` : ''}
      <p class="hint aw-foot">Der Ort wird aus der Internetadresse ermittelt und ist ungefähr: meist die Stadt oder Region des Internetanbieters, nicht die Adresse des Kunden (im Mobilfunk oft ein Knotenpunkt wie Frankfurt, mit VPN ganz woanders). Gespeichert werden Ort, Zeit, Gerätetyp und Kunde – keine IP-Adresse –, nach ${data.aufbewahrung} Tagen automatisch gelöscht.
        ${od ? `Ortsdaten: <a href="https://db-ip.com" target="_blank" rel="noopener">IP Geolocation by DB-IP</a> (CC BY 4.0), Stand ${esc(od.date.slice(5, 7) + '/' + od.date.slice(0, 4))}.` : ''} Karte: Natural Earth.
        ${od && data.kannAktualisieren ? `<button type="button" class="link-btn" data-aw="ort">Ortsdaten aktualisieren</button>` : ''}</p>`;
    vb = fitBox(gs); full = aspect([karte.box[0], karte.box[1] + karte.box[3] * 0.08, karte.box[2], karte.box[3] * 0.8]);
    drawPoints(gs);
    applyVb();
  }
  const firma = (kid) => { const k = data && data.kunden.find((x) => x.id === kid); return k ? k.firma : 'Kunde'; };

  function scale() { const svg = $('#aw-svg'); return vb[2] / Math.max(1, svg.clientWidth); }   // Karten-Einheiten je Bildschirmpunkt

  function drawPoints(gs) {
    $('#aw-pts').innerHTML = gs.map((g) => {
      const n = g.items.length, firmen = [...g.kids].map(firma);
      return `<g class="aw-pt${n > 1 ? ' multi' : ''}" data-aw-key="${g.key}" tabindex="0" role="button" aria-label="${esc(ortKurz(g.items[0]))}: ${esc(plural(n, 'Anmeldung', 'Anmeldungen'))}"><title>${esc(ortName(g.items[0]))} – ${esc(firmen.slice(0, 4).join(', '))}${firmen.length > 4 ? ' …' : ''} (${n})</title><circle cx="${g.x.toFixed(1)}" cy="${g.y.toFixed(1)}" data-n="${n}"/><text class="aw-lbl" data-x="${g.x.toFixed(1)}" data-y="${g.y.toFixed(1)}" data-n="${n}">${esc(ortKurz(g.items[0]))}</text>${n > 1 ? `<text x="${g.x.toFixed(1)}" y="${g.y.toFixed(1)}">${n > 99 ? '99+' : n}</text>` : ''}</g>`;
    }).join('');
    $('#aw-pts')._gs = gs;
  }

  /* Ausschnitt anwenden: Punktgröße, Schrift und Orientierungsstädte an den Zoom anpassen */
  function applyVb() {
    const svg = $('#aw-svg');
    if (!svg) return;
    vb = clamp(vb);
    svg.setAttribute('viewBox', vb.map((v) => v.toFixed(1)).join(' '));
    const s = scale();
    for (const c of $$('#aw-pts circle')) { const n = +c.dataset.n; c.setAttribute('r', ((n > 1 ? 9 : 7) + Math.min(10, Math.sqrt(n) * 1.6)) * s); }
    for (const t of $$('#aw-pts text:not(.aw-lbl)')) t.setAttribute('font-size', 10.5 * s);
    const lbl = $$('#aw-pts .aw-lbl'), zeigen = lbl.length <= 25 || vb[2] < 1500;   // Ortsnamen an den Punkten, bei sehr vielen erst beim Hineinzoomen
    for (const t of lbl) {
      const n = +t.dataset.n, r = (n > 1 ? 9 : 7) + Math.min(10, Math.sqrt(n) * 1.6);
      t.setAttribute('x', +t.dataset.x + (r + 4) * s); t.setAttribute('y', +t.dataset.y + 4 * s); t.setAttribute('font-size', 12 * s);
      t.style.display = zeigen ? '' : 'none';
    }
    const ref = $('#aw-ref');
    const pts = ($('#aw-pts')._gs || []);
    const frei = (x, y) => !pts.some((g) => Math.abs(g.x - x) < 70 * s && Math.abs(g.y - y) < 16 * s);   // keine Beschriftung unter einem Punkt
    ref.innerHTML = vb[2] < 2600 ? STAEDTE.filter(([, lat, lon]) => frei(px(lon) + 30 * s, py(lat))).map(([n, lat, lon]) => `<circle cx="${px(lon)}" cy="${py(lat)}" r="${2.2 * s}"/><text x="${px(lon) + 5 * s}" y="${py(lat) + 3.5 * s}" font-size="${11 * s}">${n}</text>`).join('') : '';
    placePop();
  }
  function clamp(b) {
    let [x, y, w, h] = b;
    const maxW = full ? full[2] : 36000, minW = 120;
    if (w > maxW) { h = h * maxW / w; w = maxW; }
    if (w < minW) { h = h * minW / w; w = minW; }
    if (full) { x = Math.max(full[0] - w * 0.5, Math.min(full[0] + full[2] - w * 0.5, x)); y = Math.max(full[1] - h * 0.5, Math.min(full[1] + full[3] - h * 0.5, y)); }
    return [x, y, w, h];
  }
  function zoom(f, cx, cy) {
    const [x, y, w, h] = vb;
    if (cx === undefined) { cx = x + w / 2; cy = y + h / 2; }
    vb = [cx - (cx - x) * f, cy - (cy - y) * f, w * f, h * f];
    applyVb();
  }
  function toMap(ev) {
    const svg = $('#aw-svg'), r = svg.getBoundingClientRect();
    return [vb[0] + (ev.clientX - r.left) / r.width * vb[2], vb[1] + (ev.clientY - r.top) / r.height * vb[3]];
  }

  /* Hinweisfeld zu einem Ort */
  function openPop(key) {
    const gs = $('#aw-pts')._gs || [];
    const g = gs.find((x) => x.key === key);
    if (!g) return;
    sel = g;
    for (const el of $$('#aw-pts .aw-pt')) el.classList.toggle('sel', el.dataset.awKey === key);
    const pop = $('#aw-pop');
    const byK = new Map();
    for (const e of g.items) { if (!byK.has(e.kid)) byK.set(e.kid, []); byK.get(e.kid).push(e); }
    pop.innerHTML = `<div class="aw-pop-h"><strong>${esc(ortName(g.items[0]))}</strong>${g.items[0].cc && g.items[0].cc !== 'DE' ? `<span class="sub">${esc(regionName(g.items[0].cc))}</span>` : ''}<button type="button" class="btn icon ghost sm" data-aw="close" aria-label="Schließen">${icon('x')}</button></div>
      <ul>${[...byK.entries()].map(([kid, es]) => `<li><span class="nm">${esc(firma(kid))}</span><span class="sub">${esc(plural(es.length, 'Anmeldung', 'Anmeldungen'))}, zuletzt ${esc(dateTime(es[0].t))} · ${esc(DEV[es[0].dev] || '')}</span></li>`).join('')}</ul>`;
    pop.hidden = false;
    placePop();
  }
  function closePop() { sel = null; const p = $('#aw-pop'); if (p) p.hidden = true; for (const el of $$('#aw-pts .aw-pt.sel')) el.classList.remove('sel'); }
  function placePop() {
    const pop = $('#aw-pop');
    if (!pop || pop.hidden || !sel) return;
    const svg = $('#aw-svg'), wrap = svg.parentElement;
    const sr = svg.getBoundingClientRect(), wr = wrap.getBoundingClientRect();   // SVG-Elemente haben kein offsetLeft
    const sx = (sel.x - vb[0]) / vb[2] * sr.width + sr.left - wr.left, sy = (sel.y - vb[1]) / vb[3] * sr.height + sr.top - wr.top;
    const pw = pop.offsetWidth, ph = pop.offsetHeight;
    let left = sx - pw / 2, top = sy - ph - 16;
    if (top < 8) top = sy + 16;
    left = Math.max(8, Math.min(wrap.clientWidth - pw - 8, left));
    top = Math.max(8, Math.min(wrap.clientHeight - ph - 8, top));
    pop.style.left = left + 'px'; pop.style.top = top + 'px';
  }

  /* Bedienung: Ziehen, Mausrad, zwei Finger, Knöpfe */
  const view = $('#view-auswertung');
  const ptrs = new Map(); let drag = null, pinch = null, moved = false;
  view.addEventListener('pointerdown', (e) => {
    if (!e.target.closest('#aw-svg')) return;
    ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    e.target.closest('#aw-svg').setPointerCapture(e.pointerId);
    moved = false;
    if (ptrs.size === 1) drag = { x: e.clientX, y: e.clientY, vb: vb.slice() };
    else if (ptrs.size === 2) { const [a, b] = [...ptrs.values()]; pinch = { d: Math.hypot(a[0] - b[0], a[1] - b[1]), vb: vb.slice(), c: toMap({ clientX: (a[0] + b[0]) / 2, clientY: (a[1] + b[1]) / 2 }) }; drag = null; }
  });
  view.addEventListener('pointermove', (e) => {
    if (!ptrs.has(e.pointerId)) return;
    ptrs.set(e.pointerId, [e.clientX, e.clientY]);
    const svg = $('#aw-svg');
    if (drag) {
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
      const s = drag.vb[2] / svg.clientWidth;
      vb = [drag.vb[0] - dx * s, drag.vb[1] - dy * s, drag.vb[2], drag.vb[3]];
      applyVb();
    } else if (pinch && ptrs.size === 2) {
      const [a, b] = [...ptrs.values()];
      const f = pinch.d / Math.max(1, Math.hypot(a[0] - b[0], a[1] - b[1]));
      moved = true;
      const [x, y, w, h] = pinch.vb, [cx, cy] = pinch.c;
      vb = [cx - (cx - x) * f, cy - (cy - y) * f, w * f, h * f];
      applyVb();
    }
  });
  const up = (e) => { ptrs.delete(e.pointerId); if (ptrs.size < 2) pinch = null; if (!ptrs.size) drag = null; };
  view.addEventListener('pointerup', up); view.addEventListener('pointercancel', up);
  view.addEventListener('wheel', (e) => {
    if (!e.target.closest('#aw-svg')) return;
    e.preventDefault();
    const [cx, cy] = toMap(e);
    zoom(Math.exp(Math.max(-0.5, Math.min(0.5, e.deltaY * (e.deltaMode ? 0.05 : 0.0022)))), cx, cy);
  }, { passive: false });
  view.addEventListener('click', async (e) => {
    const r = e.target.closest('[data-aw-tage]');
    if (r) { tage = +r.dataset.awTage; render(); return; }
    const pt = e.target.closest('[data-aw-key]');
    if (pt && !moved) { openPop(pt.dataset.awKey); return; }
    const row = e.target.closest('[data-aw-pt]');
    if (row) { focusPt(row.dataset.awPt); return; }
    const a = e.target.closest('[data-aw]')?.dataset.aw;
    if (a === 'in') zoom(0.6);
    else if (a === 'out') zoom(1 / 0.6);
    else if (a === 'fit') { closePop(); vb = fitBox($('#aw-pts')._gs || []); applyVb(); }
    else if (a === 'close') closePop();
    else if (a === 'ort') updateOrt(e.target.closest('button'));
    else if (e.target.closest('#aw-svg') && !moved) closePop();
  });
  view.addEventListener('keydown', (e) => {
    if ((e.key === 'Enter' || e.key === ' ') && e.target.closest('[data-aw-key]')) { e.preventDefault(); openPop(e.target.closest('[data-aw-key]').dataset.awKey); }
    else if (e.key === 'Enter' && e.target.closest('[data-aw-pt]')) focusPt(e.target.closest('[data-aw-pt]').dataset.awPt);
    else if (e.key === 'Escape') closePop();
  });
  view.addEventListener('change', (e) => { if (e.target.id === 'aw-kunde') { kunde = e.target.value; render(); } });
  window.addEventListener('resize', () => { if (vb && $('#aw-svg') && !$('#view-auswertung').hidden) { vb = aspect(vb); applyVb(); } });

  function focusPt(key) {
    const g = ($('#aw-pts')._gs || []).find((x) => x.key === key);
    if (!g) return;
    const w = Math.min(vb[2], 900), h = w * vb[3] / vb[2];
    vb = [g.x - w / 2, g.y - h / 2, w, h];
    applyVb();
    openPop(key);
    $('#aw-svg').scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  async function updateOrt(btn) {
    if (btn) { btn.disabled = true; btn.dataset.lbl = btn.innerHTML; btn.innerHTML = '<span class="spinner sm"></span>Ortsdaten werden geladen …'; }
    try {
      const r = await api('ort_update', { body: {} });
      toast(`Ortsdaten geladen (Stand ${r.ortsdaten.date.slice(5, 7)}/${r.ortsdaten.date.slice(0, 4)}). Neue Anmeldungen erhalten ab jetzt einen Ort.`);
      render();
    } catch (ex) {
      toast(ex.message, 6000);
      if (btn) { btn.disabled = false; btn.innerHTML = btn.dataset.lbl; }
    }
  }

  W.views.auswertung = render;
})();
