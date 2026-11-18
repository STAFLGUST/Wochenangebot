/* STAFL-Plattform · Container-Import · EUDR – Karte der Herkunftsbetriebe als SVG, ohne fremde Kartendienste.
   Hintergrund: Umrisse der Länder aus ../../assets/karte.json (Natural Earth, Mercator, 100 Einheiten je Grad); die
   Detailkarte des Servers (assets/detailkarte.js) deckt nur Deutschland ab und hilft für Herkunftsländer nicht.
   Zwei Formen: Übersicht (alle Betriebe als Fläche mit Marke im Mittelpunkt; Rad und Knöpfe zoomen, Ziehen verschiebt,
   Klick auf einen Betrieb ruft beiKlick) und Einzelfläche (Umriss groß mit Eckpunkten, Maßstab und Lage im Land).
   Farbe je Betrieb nach seiner Ampel vom Server (gruen | gelb | rot).
   API: window.EUDR_KARTE.zeichnen(element, { betriebe, einzeln, beiKlick }) → Promise */
(function () {
  'use strict';
  const NS = 'http://www.w3.org/2000/svg';
  const QUELLE = new URL('../../assets/karte.json', document.currentScript.src).href;
  const px = (lon) => (lon + 180) * 100;
  const py = (lat) => { const l = Math.max(-85, Math.min(85, lat)) * Math.PI / 180; return (180 - Math.log(Math.tan(Math.PI / 4 + l / 2)) * 180 / Math.PI) * 100; };
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  let laender = null;
  const ladeLaender = () => (laender = laender || fetch(QUELLE).then((r) => (r.ok ? r.json() : { laender: [] })).catch(() => ({ laender: [] })));

  /* Polygone einer Geometrie (Point: keine) */
  const polygone = (g) => (g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : []);
  const pfad = (g) => polygone(g).map((p) => p.map((ring) => 'M' + ring.map(([x, y]) => `${px(x).toFixed(2)} ${py(y).toFixed(2)}`).join('L') + 'Z').join('')).join('');
  /* Rahmen [x, y, Breite, Höhe] in Karteneinheiten um die Betriebe: Rand anteilig, Mindestbreite in Grad */
  function ausschnitt(betriebe, rand, minGrad, seite) {
    const xs = betriebe.flatMap((b) => [px(b.rahmen[0]), px(b.rahmen[2])]), ys = betriebe.flatMap((b) => [py(b.rahmen[1]), py(b.rahmen[3])]);
    let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
    let w = Math.max((x1 - x0) * (1 + 2 * rand), minGrad * 100), h = Math.max((y1 - y0) * (1 + 2 * rand), minGrad * 100 / seite);
    if (w / h > seite) h = w / seite; else w = h * seite;
    return [(x0 + x1) / 2 - w / 2, (y0 + y1) / 2 - h / 2, w, h];
  }
  /* „Runde“ Strecke für den Maßstab: 1, 2 oder 5 mal Zehnerpotenz, höchstens grenze Meter */
  function rund(grenze) {
    const p = 10 ** Math.floor(Math.log10(grenze));
    return [5, 2, 1].map((f) => f * p).find((v) => v <= grenze) || p;
  }
  const strecke = (m) => (m >= 1000 ? `${(m / 1000).toLocaleString('de-DE')} km` : `${m} m`);

  function svg(box, inhalt, klasse) {
    return `<svg xmlns="${NS}" class="${klasse}" viewBox="${box.map((v) => v.toFixed(2)).join(' ')}" preserveAspectRatio="xMidYMid meet" role="img">${inhalt}</svg>`;
  }
  const land = (k) => `<path class="ci-k-land" d="${k.laender.join('')}"/>`;
  const flaeche = (b, einzeln) => {
    const g = b.geometrie;
    if (g.type === 'Point') return '';
    return `<path class="ci-k-flaeche ${b.ampel}" data-id="${esc(b.id || '')}" d="${pfad(g)}"><title>${esc(b.name)}</title></path>`
      + (einzeln ? polygone(g).map((p) => p[0].slice(0, -1).map(([x, y]) => `<circle class="ci-k-ecke" cx="${px(x).toFixed(2)}" cy="${py(y).toFixed(2)}" r="0"/>`).join('')).join('') : '');
  };
  const marke = (b) => `<circle class="ci-k-marke ${b.ampel}" data-id="${esc(b.id || '')}" cx="${px(b.mitte[0]).toFixed(2)}" cy="${py(b.mitte[1]).toFixed(2)}" r="0"><title>${esc(b.name)}</title></circle>`;

  /* Größen, die mit dem Zoom mitgehen müssen (Marken, Eckpunkte), aus der aktuellen Breite des Ausschnitts setzen */
  function groessen(el) {
    const s = el.querySelector('svg.ci-k-haupt');
    const w = s.viewBox.baseVal.width, jePixel = w / (s.clientWidth || 600);   // Karteneinheiten je Bildschirmpunkt
    s.querySelectorAll('.ci-k-marke').forEach((c) => c.setAttribute('r', (6 * jePixel).toFixed(3)));
    s.querySelectorAll('.ci-k-ecke').forEach((c) => c.setAttribute('r', (2.5 * jePixel).toFixed(3)));
    const m = el.querySelector('.ci-k-massstab');
    if (m) {   // Maßstab: runde Strecke, höchstens 30 % der Breite – geht mit dem Zoom mit
      const meterJeEinheit = Number(m.dataset.meter), laenge = rund(w * meterJeEinheit * 0.3);
      m.firstElementChild.style.width = (laenge / meterJeEinheit / w * 100).toFixed(2) + '%';
      m.lastElementChild.textContent = strecke(laenge);
    }
  }
  /* Zoomen (Rad, Knöpfe) und Verschieben (Ziehen) über die viewBox; ein Antippen ohne Ziehen auf einem Betrieb ruft
     beiKlick – das Ziel wird beim Drücken gemerkt, weil der Zeiger danach an der Karte hängt (setPointerCapture) */
  function bedienung(el, start, beiKlick) {
    const s = el.querySelector('svg.ci-k-haupt');
    const setze = (b) => { s.setAttribute('viewBox', b.map((v) => v.toFixed(2)).join(' ')); groessen(el); };
    const jetzt = () => { const v = s.viewBox.baseVal; return [v.x, v.y, v.width, v.height]; };
    const zoom = (f, mx = 0.5, my = 0.5) => {
      const [x, y, w, h] = jetzt(), nw = Math.min(Math.max(w * f, 0.5), 36000), nh = nw * h / w;
      setze([x + (w - nw) * mx, y + (h - nh) * my, nw, nh]);
    };
    s.addEventListener('wheel', (e) => { e.preventDefault(); const r = s.getBoundingClientRect(); zoom(e.deltaY < 0 ? 0.8 : 1.25, (e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height); }, { passive: false });
    let zieh = null;
    s.addEventListener('pointerdown', (e) => {
      const ziel = e.target.closest('[data-id]');
      zieh = { x: e.clientX, y: e.clientY, box: jetzt(), bewegt: false, id: ziel ? ziel.dataset.id : '' };
      s.setPointerCapture(e.pointerId);
    });
    s.addEventListener('pointermove', (e) => {
      if (!zieh) return;
      const r = s.getBoundingClientRect(), dx = e.clientX - zieh.x, dy = e.clientY - zieh.y;
      if (Math.abs(dx) + Math.abs(dy) > 4) zieh.bewegt = true;
      if (zieh.bewegt) setze([zieh.box[0] - dx * zieh.box[2] / r.width, zieh.box[1] - dy * zieh.box[3] / r.height, zieh.box[2], zieh.box[3]]);
    });
    s.addEventListener('pointerup', (e) => {
      s.releasePointerCapture(e.pointerId);
      if (zieh && !zieh.bewegt && zieh.id && beiKlick) beiKlick(zieh.id);
      zieh = null;
    });
    s.addEventListener('pointercancel', () => { zieh = null; });
    el.querySelector('[data-zoom="+"]').addEventListener('click', () => zoom(0.6));
    el.querySelector('[data-zoom="-"]').addEventListener('click', () => zoom(1.6));
    el.querySelector('[data-zoom="0"]').addEventListener('click', () => setze(start));
  }

  async function zeichnen(el, opt) {
    const betriebe = (opt.betriebe || []).filter((b) => b.rahmen.every(Number.isFinite) && Math.abs(b.mitte[1]) <= 85);
    el.classList.add('ci-karte');
    el.dataset.karte = 'laedt';
    if (!betriebe.length) { el.innerHTML = '<p class="ci-leer">Keine Fläche zum Anzeigen.</p>'; el.dataset.karte = 'leer'; return; }
    const k = await ladeLaender();
    const seite = opt.einzeln ? 1.5 : 1.9;
    const start = ausschnitt(betriebe, opt.einzeln ? 0.18 : 0.5, opt.einzeln ? 0.002 : 11, seite);
    const knoepfe = '<div class="ci-k-zoom"><button type="button" data-zoom="+" aria-label="Vergrößern">+</button><button type="button" data-zoom="-" aria-label="Verkleinern">−</button><button type="button" data-zoom="0" aria-label="Ganze Ansicht" title="Ganze Ansicht">⌂</button></div>';
    let zusatz = '';
    if (opt.einzeln) {
      const b = betriebe[0], lat = b.mitte[1] * Math.PI / 180;
      const lage = ausschnitt(betriebe, 0, 14, 1.2);
      zusatz = `<div class="ci-k-massstab" data-meter="${(111320 * Math.cos(lat) / 100).toFixed(4)}"><span></span><b></b></div>`
        + `<div class="ci-k-lage">${svg(lage, land(k) + `<circle class="ci-k-marke ${b.ampel}" cx="${px(b.mitte[0]).toFixed(2)}" cy="${py(b.mitte[1]).toFixed(2)}" r="${(lage[2] / 28).toFixed(2)}"/>`, 'ci-k-klein')}</div>`;
    }
    el.innerHTML = svg(start, land(k) + betriebe.map((b) => flaeche(b, opt.einzeln)).join('') + (opt.einzeln ? '' : betriebe.map(marke).join('')), 'ci-k-haupt') + knoepfe + zusatz;
    groessen(el);
    bedienung(el, start, opt.beiKlick);
    el.dataset.karte = 'bereit';
  }

  window.EUDR_KARTE = { zeichnen };
})();
