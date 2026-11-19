/* ==========================================================================
   STAFL-Plattform – Detailkarte (Straßen, Gebäude, Ortsnamen) vom eigenen Server
   Gemeinsame Kartenkomponente für die CRM-Karte und die Auswertung der Verwaltung. Kartendaten: OpenStreetMap
   (ODbL) als eine PMTiles-Datei unter /karte/karte.pmtiles auf demselben Host (deploy/karte-laden.sh, nur mit
   Anmeldung erreichbar). Darstellung: MapLibre GL (BSD-3) und pmtiles (BSD-3) aus app/assets/vendor/, Stil
   app/assets/karte/stil-*.json (werkzeuge/karte_stil.mjs), Schriften und Symbole aus app/assets/karte/.
   Ohne die Angabe „raster“ keine fremden Kartendienste: alle Anfragen gehen an den eigenen Host (Content-Security-Policy 'self').
   Fehlt die Kartendatei, beantwortet der Server (bzw. ein vorgeschaltetes CDN) keine Range-Anfragen oder kann der
   Browser kein WebGL, meldet verfuegbar() false – die Seiten zeichnen dann ihre bisherige Übersichtskarte.

   Zweite Kartendatei „herkunft“ (/karte/herkunft.pmtiles: Südamerika und Neuseeland) für
   die Herkunftsbetriebe im Container-Import – gewählt über den Namen der Karte, Standard ist „karte“ (Deutschland).

   Rasterebenen fremder Dienste (optionen.raster – Satellitenbild, Waldkarten): nur für Seiten, deren Host sie in seiner
   Content-Security-Policy zulässt (Caddyfile: nur der Container-Import). Mit Rasterebenen zeichnet die Kartendatei nur noch
   Linien und Beschriftung (Straßen, Gewässer, Orte) darüber; mit karte: null entfällt sie ganz.

   API (global window.STAFLKarte):
     verfuegbar(karte = 'karte')       → Promise<boolean>
     webgl()                           → boolean (kann der Browser die Karte überhaupt zeichnen?)
     erstellen(element, optionen)      → Promise<Karte>
       optionen: { karte: 'karte'|'herkunft'|null (keine Kartendatei, nur mit raster),
                   raster: [{ id, kacheln: [Adresse mit {z}/{x}/{y} oder {bbox-epsg-3857}], maxzoom, deckkraft, quelle (HTML), sichtbar }] in Zeichenreihenfolge,
                   punkte, farbe: 'gruen'|'rot'|'grau', beiKlick(id, punkt), beiBewegung(), beiLeerklick(lon, lat), rahmen: [lon1, lat1, lon2, lat2] }
       punkt:    { id, lon, lat, n (Anzahl), aus (inaktiv), titel, farbe (eigene Farbe als #rrggbb, sonst die der Karte) }
     Karte: setzePunkte(punkte), passend(), zoom(+1|-1), zentriere(lon, lat, zoom), position(lon, lat) → [x, y],
            markiere(id), anzahl(), groesse(), entfernen(); map (MapLibre). Am Element: element.staflKarte und
            data-karte="laedt" | "bereit" (fertig gezeichnet)
            setzeGebiete(sammlung | null): Flächen unter den Punkten (z. B. Nielsen-Gebiete) – GeoJSON-Features mit
              properties { farbe, hervor (true = betont), text (Beschriftung, \n erlaubt), beschriftung: [lon, lat] };
            gebiete() → Anzahl gezeigter Flächen; rahmen([lon1, lat1, lon2, lat2]) zeigt einen Ausschnitt
            zeige(id, an) blendet eine Rasterebene ein oder aus, mit id 'grund' Linien und Beschriftung der Kartendatei;
              sichtbar(id) → boolean
   ========================================================================== */
(function () {
  'use strict';
  const BASIS = new URL('.', document.currentScript ? document.currentScript.src : location.href).href;   // …/assets/
  const datei = (karte) => new URL('/karte/' + (karte === 'herkunft' ? 'herkunft' : 'karte') + '.pmtiles', location.href).href;
  const DEUTSCHLAND = [5.6, 47.2, 15.3, 55.1];
  const ATTRIBUTION = '<a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">© OpenStreetMap-Mitwirkende</a> · <a href="https://protomaps.com" target="_blank" rel="noopener">Protomaps</a>';
  const FARBEN = { gruen: ['#3f7a5a', '#2f6147'], rot: ['#9b2335', '#7b1e2b'], grau: ['#5f6368', '#3c4043'] };

  let bibliothek = null, protokoll = null;
  const pruefung = {};   // je Kartendatei
  const stile = {};

  function webgl() {
    try { const c = document.createElement('canvas'); return !!(c.getContext('webgl2') || c.getContext('webgl')); } catch (e) { return false; }
  }
  /* Kartendatei vorhanden? (eine kleine Range-Anfrage; nur einmal je Seite). Kommt statt des Abschnitts die ganze Datei
     (Status 200 – z. B. ein vorgeschaltetes CDN, das Range-Anfragen nicht weitergibt), wird der Abruf sofort abgebrochen:
     sonst liefe im Hintergrund ein Download der ganzen Kartendatei (mehrere GB) weiter. Die Karte braucht Abschnitte. */
  function verfuegbar(karte) {
    const DATEI = datei(karte);
    if (!pruefung[DATEI]) {
      pruefung[DATEI] = !webgl() ? Promise.resolve(false) : (async () => {
        const abbruch = new AbortController();
        try {
          const r = await fetch(DATEI, { headers: { Range: 'bytes=0-6' }, credentials: 'same-origin', cache: 'no-store', signal: abbruch.signal });
          if (r.status !== 206) {
            abbruch.abort();
            if (r.status === 200) console.warn('Detailkarte: Der Server liefert keine Abschnitte der Kartendatei (Status 200 statt 206) – Übersichtskarte wird gezeigt.');
            return false;
          }
          return (await r.text()).startsWith('PMTiles');
        } catch (e) {
          abbruch.abort();
          return false;
        }
      })();
    }
    return pruefung[DATEI];
  }
  function skript(src) {
    return new Promise((ok, fehler) => {
      const s = document.createElement('script'); s.src = src; s.onload = ok; s.onerror = () => fehler(new Error('Karte: ' + src + ' nicht geladen'));
      document.head.appendChild(s);
    });
  }
  function laden() {
    if (!bibliothek) {
      if (!document.querySelector('link[data-detailkarte]')) {
        const l = document.createElement('link'); l.rel = 'stylesheet'; l.href = BASIS + 'vendor/maplibre/maplibre-gl.css'; l.dataset.detailkarte = '1';
        document.head.appendChild(l);
      }
      // ES-Module mit Endung .js (Webserver liefern sie ohne eigene MIME-Einstellung als JavaScript aus); den Worker
      // nennt setWorkerUrl, weil MapLibre sonst „maplibre-gl-worker.mjs“ neben sich sucht
      bibliothek = Promise.all([import(BASIS + 'vendor/maplibre/maplibre-gl.js'), window.pmtiles ? null : skript(BASIS + 'vendor/pmtiles/pmtiles.js')])
        .then(([m]) => {
          const ml = m.default || m;
          ml.setWorkerUrl(BASIS + 'vendor/maplibre/maplibre-gl-worker.js');
          if (!protokoll) { protokoll = new window.pmtiles.Protocol(); ml.addProtocol('pmtiles', protokoll.tile); }
          return ml;
        });
      bibliothek.catch(() => { bibliothek = null; });
    }
    return bibliothek;
  }
  const dunkel = () => {
    const t = document.documentElement.dataset.theme;
    return t ? t === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches;
  };
  /* Ebenen der Kartendatei über einem Bild: Hintergrund, Linien und Beschriftung (Flächen würden das Bild verdecken);
     Straßen halb durchsichtig und ohne Rand, damit das Bild lesbar bleibt */
  const ueberBild = (layers) => layers.filter((l) => l.type === 'background' || l.type === 'symbol' || (l.type === 'line' && !l.id.includes('casing')))
    .map((l) => (l.type === 'line' ? { ...l, paint: { ...l.paint, 'line-opacity': 0.5 } } : l));
  /* Stil der Karte. Ohne Rasterebenen: die Kartendatei mit allen Ebenen. Mit Rasterebenen: Hintergrund, die Bilder in der
     gegebenen Reihenfolge, darüber – wenn eine Kartendatei gewählt ist – Linien und Beschriftung. */
  function stil(art, karte, raster) {
    if (!stile[art]) {
      stile[art] = fetch(BASIS + 'karte/stil-' + art + '.json').then((r) => { if (!r.ok) throw new Error('Kartenstil nicht geladen'); return r.json(); });
    }
    return stile[art].then((s) => {
      const [hintergrund, ...darueber] = ueberBild(s.layers);
      return {
        version: 8,
        glyphs: BASIS + 'karte/schrift/{fontstack}/{range}.pbf',
        sprite: BASIS + 'karte/sprite/' + s.sprite,
        sources: {
          ...(karte ? { protomaps: { type: 'vector', url: 'pmtiles://' + datei(karte), attribution: ATTRIBUTION } } : {}),
          ...Object.fromEntries(raster.map((r) => ['raster-' + r.id, { type: 'raster', tiles: r.kacheln, tileSize: 256, maxzoom: r.maxzoom || 14, attribution: r.quelle || '' }])),
        },
        layers: raster.length ? [
          hintergrund,
          ...raster.map((r) => ({ id: 'raster-' + r.id, type: 'raster', source: 'raster-' + r.id,
            layout: { visibility: r.sichtbar === false ? 'none' : 'visible' }, paint: { 'raster-opacity': r.deckkraft === undefined ? 1 : r.deckkraft } })),
          ...(karte ? darueber : []),
        ] : s.layers,
      };
    });
  }

  function geojson(punkte) {
    return {
      type: 'FeatureCollection',
      features: (punkte || []).filter((p) => isFinite(p.lon) && isFinite(p.lat)).map((p, i) => ({
        type: 'Feature', id: i + 1,
        geometry: { type: 'Point', coordinates: [p.lon, p.lat] },
        properties: { key: String(p.id), n: p.n || 1, aus: p.aus ? 1 : 0, titel: p.titel || '', ...(/^#[0-9a-f]{6}$/i.test(p.farbe || '') ? { farbe: p.farbe } : {}) },
      })),
    };
  }

  async function erstellen(el, opt) {
    const raster = opt.raster || [];
    const karte = opt.karte === null && raster.length ? null : (opt.karte || 'karte');
    const [ml, style] = await Promise.all([laden(), stil(dunkel() ? 'dunkel' : 'hell', karte, raster)]);
    const [farbe, rand] = FARBEN[opt.farbe] || FARBEN.gruen;
    const halo = dunkel() ? '#141213' : '#ffffff';
    const grund = karte && raster.length ? style.layers.filter((l) => l.source === 'protomaps').map((l) => l.id) : [];   // Linien und Beschriftung über den Bildern
    let punkte = opt.punkte || [];
    el.classList.add('detailkarte');
    const map = new ml.Map({
      container: el, style, bounds: opt.rahmen || DEUTSCHLAND, fitBoundsOptions: { padding: 24 },
      minZoom: 3, maxZoom: 19, attributionControl: { compact: true }, dragRotate: false, pitchWithRotate: false,
      cooperativeGestures: false, locale: {
        'NavigationControl.ZoomIn': 'Vergrößern', 'NavigationControl.ZoomOut': 'Verkleinern',
        'AttributionControl.ToggleAttribution': 'Kartenquellen', 'Map.Title': 'Karte',
      },
    });
    map.touchZoomRotate.disableRotation();
    // Ladezustand am Element: data-karte="laedt" | "bereit" (alles gezeichnet, keine Bewegung) – Tests warten darauf per
    // CSS-Selektor, weil die Content-Security-Policy der Seiten kein eval erlaubt
    el.dataset.karte = 'laedt';
    map.on('idle', () => { el.dataset.karte = 'bereit'; });
    map.on('movestart', () => { el.dataset.karte = 'laedt'; });
    map.on('dataloading', () => { el.dataset.karte = 'laedt'; });
    // Fehlende Schriftbereiche (seltene Schriftzeichen) und Symbole leise übergehen – die Karte bleibt nutzbar.
    // Neu zeichnen: nach einer nicht geladenen Kachel prüft die Karte sonst nicht mehr, ob sie fertig ist („load“, „idle“ blieben aus).
    map.on('error', (e) => { const m = String(e && e.error && e.error.message || ''); if (!/glyph|sprite|image/i.test(m) && window.console) console.warn('Karte:', m); map.triggerRepaint(); });
    map.on('styleimagemissing', () => {});
    await new Promise((ok) => map.once('load', ok));
    if (raster.length) {   // Bilder: Maßstab dazu; die langen Quellenangaben der Dienste eingeklappt (ⓘ öffnet sie)
      map.addControl(new ml.ScaleControl({ unit: 'metric', maxWidth: 110 }), 'bottom-left');
      const quellen = el.querySelector('.maplibregl-ctrl-attrib');
      if (quellen) { quellen.classList.remove('maplibregl-compact-show'); quellen.removeAttribute('open'); }
    }
    map.addSource('punkte', { type: 'geojson', data: geojson(punkte), cluster: true, clusterRadius: 34, clusterMaxZoom: 12,
      clusterProperties: { n: ['+', ['get', 'n']], aus: ['min', ['get', 'aus']] } });
    const groesse = ['interpolate', ['linear'], ['sqrt', ['get', 'n']], 1, 8, 4, 12, 20, 19, 60, 26];
    map.addLayer({ id: 'punkte-kreis', type: 'circle', source: 'punkte', paint: {
      'circle-radius': groesse,
      'circle-color': ['case', ['==', ['get', 'aus'], 1], '#9a938c', ['coalesce', ['get', 'farbe'], farbe]],
      'circle-stroke-color': ['case', ['boolean', ['feature-state', 'auswahl'], false], rand, halo],
      'circle-stroke-width': ['case', ['boolean', ['feature-state', 'auswahl'], false], 3, 1.6],
      'circle-opacity': 0.92,
    } });
    map.addLayer({ id: 'punkte-zahl', type: 'symbol', source: 'punkte', filter: ['>', ['get', 'n'], 1], layout: {
      'text-field': ['case', ['>', ['get', 'n'], 99], '99+', ['to-string', ['get', 'n']]],
      'text-font': ['Noto Sans Medium'], 'text-size': 11, 'text-allow-overlap': true, 'text-ignore-placement': true,
    }, paint: { 'text-color': '#ffffff' } });
    // Flächen (Gebiete) unter den Beschriftungen der Grundkarte – ohne Grundkarte unter den Punkten; ihre Namen unter den Punkten
    const ersteSchrift = ((map.getStyle().layers || []).find((l) => l.type === 'symbol' && l.source !== 'punkte') || { id: 'punkte-kreis' }).id;
    let gebieteDa = false, gebieteZahl = 0;
    function setzeGebiete(sammlung) {
      const fs = (sammlung && sammlung.features) || [];
      gebieteZahl = fs.length;
      const flaechen = { type: 'FeatureCollection', features: fs.map((f, i) => ({ type: 'Feature', id: i + 1, geometry: f.geometry,
        properties: { farbe: f.properties.farbe || '#5b7fa6', hervor: f.properties.hervor ? 1 : 0 } })) };
      const texte = { type: 'FeatureCollection', features: fs.filter((f) => f.properties.text && Array.isArray(f.properties.beschriftung)).map((f) => ({
        type: 'Feature', geometry: { type: 'Point', coordinates: f.properties.beschriftung }, properties: { text: f.properties.text, farbe: f.properties.farbe || '#5b7fa6' } })) };
      if (gebieteDa) { map.getSource('gebiete').setData(flaechen); map.getSource('gebiete-text').setData(texte); return; }
      map.addSource('gebiete', { type: 'geojson', data: flaechen });
      map.addSource('gebiete-text', { type: 'geojson', data: texte });
      map.addLayer({ id: 'gebiete-flaeche', type: 'fill', source: 'gebiete', paint: {
        'fill-color': ['get', 'farbe'], 'fill-opacity': ['case', ['==', ['get', 'hervor'], 1], 0.2, 0.12] } }, ersteSchrift);
      // Auf einem Bild braucht der Umriss einen hellen Rand, sonst verschwindet er im Wald
      if (raster.length) map.addLayer({ id: 'gebiete-rand', type: 'line', source: 'gebiete', paint: { 'line-color': '#ffffff', 'line-width': 5, 'line-opacity': 0.85 } }, ersteSchrift);
      map.addLayer({ id: 'gebiete-linie', type: 'line', source: 'gebiete', paint: {
        'line-color': ['get', 'farbe'], 'line-width': ['case', ['==', ['get', 'hervor'], 1], 2.6, 1.2], 'line-opacity': 0.9 } }, ersteSchrift);
      map.addLayer({ id: 'gebiete-text', type: 'symbol', source: 'gebiete-text', layout: {
        'text-field': ['get', 'text'], 'text-font': ['Noto Sans Medium'], 'text-size': 13, 'text-line-height': 1.25 },
        paint: { 'text-color': ['get', 'farbe'], 'text-halo-color': halo, 'text-halo-width': 1.8 } }, 'punkte-kreis');
      gebieteDa = true;
    }
    let markiert = null;
    const k = {
      map,
      setzePunkte(neu) { punkte = neu || []; markiert = null; map.getSource('punkte').setData(geojson(punkte)); },
      passend() {
        const ps = punkte.filter((p) => isFinite(p.lon) && isFinite(p.lat));
        if (!ps.length) { map.fitBounds(opt.rahmen || DEUTSCHLAND, { padding: 24, duration: 300 }); return; }
        const lo = ps.map((p) => p.lon), la = ps.map((p) => p.lat);
        map.fitBounds([[Math.min(...lo), Math.min(...la)], [Math.max(...lo), Math.max(...la)]], { padding: 48, maxZoom: 13, duration: 300 });
      },
      zoom(r) { if (r > 0) map.zoomIn(); else map.zoomOut(); },
      zentriere(lon, lat, z) { map.easeTo({ center: [lon, lat], zoom: Math.max(map.getZoom(), z || 11), duration: 400 }); },
      position(lon, lat) { const p = map.project([lon, lat]); return [p.x, p.y]; },
      markiere(id) {
        if (markiert !== null) map.setFeatureState({ source: 'punkte', id: markiert }, { auswahl: false });
        markiert = null;
        if (id === null || id === undefined) return;
        const i = punkte.findIndex((p) => String(p.id) === String(id));
        if (i >= 0) { markiert = i + 1; map.setFeatureState({ source: 'punkte', id: markiert }, { auswahl: true }); }
      },
      anzahl() { return punkte.length; },
      setzeGebiete,
      gebiete() { return gebieteZahl; },
      rahmen(b) { map.fitBounds([[b[0], b[1]], [b[2], b[3]]], { padding: 40, duration: 300 }); },
      zeige(id, an) { for (const l of id === 'grund' ? grund : ['raster-' + id]) if (map.getLayer(l)) map.setLayoutProperty(l, 'visibility', an ? 'visible' : 'none'); },
      sichtbar(id) { const l = id === 'grund' ? grund[0] : 'raster-' + id; return !!(l && map.getLayer(l)) && map.getLayoutProperty(l, 'visibility') !== 'none'; },
      groesse() { map.resize(); },
      entfernen() { try { map.remove(); } catch (e) { /* schon entfernt */ } },
    };
    map.on('click', 'punkte-kreis', async (e) => {
      const f = e.features && e.features[0]; if (!f) return;
      if (f.properties.cluster) {
        const z = await map.getSource('punkte').getClusterExpansionZoom(f.properties.cluster_id);
        map.easeTo({ center: f.geometry.coordinates, zoom: Math.min(z, 18), duration: 400 });
        return;
      }
      const p = punkte.find((x) => String(x.id) === f.properties.key);
      if (p && opt.beiKlick) opt.beiKlick(p.id, p);
    });
    el.staflKarte = k;   // für Tests und Fehlersuche (Zustand der Karte am Element)
    map.on('mouseenter', 'punkte-kreis', () => { map.getCanvas().style.cursor = 'pointer'; });
    map.on('mouseleave', 'punkte-kreis', () => { map.getCanvas().style.cursor = ''; });
    if (opt.beiBewegung) map.on('move', opt.beiBewegung);
    if (opt.beiLeerklick) map.on('click', (e) => { if (!map.queryRenderedFeatures(e.point, { layers: ['punkte-kreis'] }).length) opt.beiLeerklick(e.lngLat.lng, e.lngLat.lat); });
    return k;
  }

  window.STAFLKarte = { verfuegbar, webgl, erstellen };
})();
