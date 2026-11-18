/* STAFL-Plattform · Container-Import · EUDR – Karte der Herkunftsbetriebe.
   Auftrag des Inhabers (18.11.2026): Satellitenbild und Waldflächen wie in Global Nature Watch und Whisp. Gezeichnet von der
   gemeinsamen Detailkarte (assets/detailkarte.js) mit Rasterebenen dreier fremder Dienste, die der Browser direkt abruft:
     Satellitenbild   Sentinel-2 cloudless 2016 von EOX (CC BY 4.0; spätere Jahrgänge sind für Unternehmen kostenpflichtig)
     Wald Ende 2020   Global Forest Cover 2020 der EU-Kommission (JRC) – der Stichtag der EUDR; Hinweis, kein Nachweis
     Waldverlust      Tree cover loss ab 2021 (Hansen/UMD über Global Forest Watch, CC BY 4.0, 30 m)
   Zugelassen sind diese drei Adressen nur in der Content-Security-Policy des Hosts container-import (Caddyfile); die Dienste
   sehen die Adresse des Betrachters und den Kartenausschnitt, sonst nichts (keine Cookies, kein Referer).
   Ist die Herkunftskarte des Servers geladen (/karte/herkunft.pmtiles), liegen Straßen, Gewässer und Orte darüber.
   Sind die Dienste nicht erreichbar, zeichnet die Detailkarte nur die Herkunftskarte; fehlt auch sie oder kann der Browser
   kein WebGL, zeichnet diese Datei selbst als SVG:
   Hintergrund: Umrisse der Länder aus ../../assets/karte.json (Natural Earth, Mercator, 100 Einheiten je Grad).
   Zwei Formen: Übersicht (alle Betriebe als Fläche mit Marke im Mittelpunkt; Rad und Knöpfe zoomen, Ziehen verschiebt,
   Klick auf einen Betrieb ruft beiKlick) und Einzelfläche (Umriss groß mit Eckpunkten, Maßstab und Lage im Land).
   Farbe je Betrieb nach seiner Ampel vom Server (gruen | gelb | rot).
   API: window.EUDR_KARTE.zeichnen(element, { betriebe, einzeln, beiKlick }) → Promise
        window.EUDR_KARTE.auswerten(geometrie) → Promise<Ergebnis der Bildauswertung (eudr-auswertung.js) | null ohne Dienste> */
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

  const FARBE = { gruen: '#3f7a5a', gelb: '#b07d12', rot: '#9b2335' };
  const FARBE_BILD = { gruen: '#6ee7a0', gelb: '#ffd166', rot: '#ff6b81' };   // auf dem Satellitenbild: heller, sonst verschwindet der Umriss

  /* Ebenen fremder Dienste in Zeichenreihenfolge. Jede Adresse muss in der Content-Security-Policy des Hosts stehen
     (Caddyfile, Zuordnung csp_karten) – sonst meldet pruefeDienste „nicht erreichbar“ und die Karte kommt ohne Bilder. */
  const SATELLIT = 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg';
  const WALD_WMS = 'https://ies-ows.jrc.ec.europa.eu/iforce/gfc2020/wms.py?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=gfc2020_v3&STYLES=&CRS=EPSG:3857&FORMAT=image/png&TRANSPARENT=TRUE';
  const WALD = WALD_WMS + '&BBOX={bbox-epsg-3857}&WIDTH=256&HEIGHT=256';
  const VERLUST = 'https://tiles.globalforestwatch.org/umd_tree_cover_loss/latest/dynamic/';   // ohne Zusatz: unverarbeitet (Jahr im Blaukanal)
  const verlust = (bis) => `${VERLUST}{z}/{x}/{y}.png?start_year=2021&end_year=${bis}&render_type=true_color`;
  const ebenen = (bis) => [
    { id: 'satellit', name: 'Satellitenbild (2016)', kacheln: [SATELLIT], maxzoom: 14,
      quelle: '<a href="https://s2maps.eu" target="_blank" rel="noopener">Sentinel-2 cloudless – https://s2maps.eu</a> by <a href="https://eox.at" target="_blank" rel="noopener">EOX IT Services GmbH</a> (Contains modified Copernicus Sentinel data 2016 &amp; 2017)' },
    { id: 'wald2020', name: 'Wald Ende 2020 (EU)', farbe: '#4d9221', kacheln: [WALD], maxzoom: 15, deckkraft: 0.4,
      quelle: '<a href="https://forest-observatory.ec.europa.eu/forest/" target="_blank" rel="noopener">Wald 2020: © Europäische Union, JRC (GFC 2020 v3)</a>' },
    ...(bis ? [{ id: 'verlust', name: `Waldverlust 2021–${bis}`, farbe: '#e45796', kacheln: [verlust(bis)], maxzoom: 12,
      quelle: '<a href="https://www.globalforestwatch.org" target="_blank" rel="noopener">Waldverlust: Hansen/UMD/Google/USGS/NASA über Global Forest Watch (CC BY 4.0)</a>' }] : []),
  ];
  const an = { satellit: true, wald2020: true, verlust: true, grund: true };   // Auswahl der Ebenen, gilt für alle Karten der Seite
  let dienste = null;
  /* Einmal je Seite: Lässt sich das Satellitenbild abrufen (Netz, Content-Security-Policy)? Bis zu welchem Jahr reicht der
     Waldverlust? Der Dienst lehnt ein Endjahr ohne Daten ab (422) – so findet die Karte ohne Pflege das jüngste Jahr. */
  function pruefeDienste() {
    const ok = (adresse) => fetch(adresse, { credentials: 'omit' }).then((r) => r.ok, () => false);
    dienste = dienste || (async () => {
      if (!await ok(SATELLIT.replace('{z}/{y}/{x}', '0/0/0'))) return { bild: false, bis: null };
      for (let jahr = new Date().getFullYear(); jahr >= 2021; jahr--) if (await ok(verlust(jahr).replace('{z}/{x}/{y}', '0/0/0'))) return { bild: true, bis: jahr };
      return { bild: true, bis: null };
    })();
    return dienste;
  }

  /* Bildauswertung einer Fläche (eudr-auswertung.js) aus denselben Diensten – null, wenn sie nicht erreichbar sind */
  async function auswerten(geometrie) {
    const dienst = await pruefeDienste();
    if (!dienst.bild || !dienst.bis) return null;
    return window.EUDR_AUSWERTUNG.rechnen(geometrie, dienst.bis, {
      wald: (rahmen, punkte) => `${WALD_WMS}&BBOX=${rahmen.join(',')}&WIDTH=${punkte}&HEIGHT=${punkte}`,
      verlustRoh: (z, x, y) => `${VERLUST}${z}/${x}/${y}.png`,
    });
  }

  /* Detailkarte: Bilder (wenn erreichbar), Straßen und Orte (wenn die Herkunftskarte geladen ist), darüber die Flächen in
     der Farbe ihrer Ampel; in der Übersicht zusätzlich eine Marke je Betrieb (zusammengefasste Marken grau – eine Gruppe
     hat keine eigene Ampel). Schalter für die Ebenen und Zoomknöpfe liegen über der Karte. */
  async function detail(el, opt, betriebe, dienst, vektor) {
    const xs = betriebe.flatMap((b) => [b.rahmen[0], b.rahmen[2]]), ys = betriebe.flatMap((b) => [b.rahmen[1], b.rahmen[3]]);
    const rand = opt.einzeln ? 0.01 : 0.5;
    const rahmen = [Math.min(...xs) - rand, Math.min(...ys) - rand, Math.max(...xs) + rand, Math.max(...ys) + rand];
    const bilder = dienst.bild ? ebenen(dienst.bis) : [], farbe = dienst.bild ? FARBE_BILD : FARBE;
    el.innerHTML = '';
    const k = await window.STAFLKarte.erstellen(el, { karte: vektor ? 'herkunft' : null, raster: bilder.map((e) => ({ ...e, sichtbar: an[e.id] })),
      farbe: 'grau', beiKlick: opt.beiKlick, rahmen,
      punkte: opt.einzeln ? [] : betriebe.map((b) => ({ id: b.id, lon: b.mitte[0], lat: b.mitte[1], titel: b.name, farbe: farbe[b.ampel] })) });
    k.setzeGebiete({ type: 'FeatureCollection', features: betriebe.filter((b) => b.geometrie.type !== 'Point')
      .map((b) => ({ type: 'Feature', geometry: b.geometrie, properties: { farbe: farbe[b.ampel], hervor: !dienst.bild } })) });
    const schalter = [...bilder, ...(vektor && bilder.length ? [{ id: 'grund', name: 'Straßen und Orte' }] : [])];
    if (!an.grund) k.zeige('grund', false);
    el.insertAdjacentHTML('beforeend', (schalter.length ? `<details class="ci-k-ebenen"${el.clientWidth >= 520 ? ' open' : ''}><summary>Ebenen</summary>${schalter.map((e) =>
      `<label><input type="checkbox" value="${e.id}"${an[e.id] ? ' checked' : ''}>${e.farbe ? `<i style="background:${e.farbe}"></i>` : ''}${esc(e.name)}</label>`).join('')}</details>` : '')
      + '<div class="ci-k-zoom"><button type="button" data-zoom="+" aria-label="Vergrößern">+</button><button type="button" data-zoom="-" aria-label="Verkleinern">−</button><button type="button" data-zoom="0" aria-label="Ganze Ansicht" title="Ganze Ansicht">⌂</button>'
      + (el.requestFullscreen ? '<button type="button" data-zoom="v" aria-label="Karte groß zeigen" title="Karte groß zeigen">⛶</button>' : '') + '</div>');
    el.querySelector('.ci-k-zoom').addEventListener('click', (e) => {
      const z = (e.target.closest('button') || {}).dataset;
      if (!z) return;
      if (z.zoom === 'v') (document.fullscreenElement === el ? document.exitFullscreen() : el.requestFullscreen()).catch(() => {});   // Browser kann ablehnen
      else if (z.zoom === '0') k.map.fitBounds([[rahmen[0], rahmen[1]], [rahmen[2], rahmen[3]]], { padding: 24, duration: 300 });   // genau die Ansicht vom Anfang
      else k.zoom(z.zoom === '+' ? 1 : -1);
    });
    const wahl = el.querySelector('.ci-k-ebenen');
    if (wahl) wahl.addEventListener('change', (e) => { an[e.target.value] = e.target.checked; k.zeige(e.target.value, e.target.checked); });
  }

  async function zeichnen(el, opt) {
    const betriebe = (opt.betriebe || []).filter((b) => b.rahmen.every(Number.isFinite) && Math.abs(b.mitte[1]) <= 85);
    el.classList.add('ci-karte');
    el.dataset.karte = 'laedt';
    if (el.staflKarte) { el.staflKarte.entfernen(); delete el.staflKarte; el.classList.remove('detailkarte'); }   // vorige Detailkarte dieses Elements
    if (!betriebe.length) { el.innerHTML = '<p class="ci-leer">Keine Fläche zum Anzeigen.</p>'; el.dataset.karte = 'leer'; return; }
    if (window.STAFLKarte && window.STAFLKarte.webgl()) {
      const [dienst, vektor] = await Promise.all([pruefeDienste(), window.STAFLKarte.verfuegbar('herkunft')]);
      if (dienst.bild || vektor) { try { await detail(el, opt, betriebe, dienst, vektor); return; } catch (e) { console.warn('Karte der Herkunftsbetriebe:', e); el.classList.remove('detailkarte'); el.dataset.karte = 'laedt'; } }
    }
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

  window.EUDR_KARTE = { zeichnen, auswerten };
})();
