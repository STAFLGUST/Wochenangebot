/* STAFL-Plattform · Container-Import · EUDR – Bildauswertung einer Fläche: Wald Ende 2020 und Waldverlust seit 2021 in Hektar.
   Eine Schätzung aus denselben Kartenbildern, die die Karte zeigt – ein Hinweis für die eigene Gegenprüfung, kein Nachweis:
     Wald Ende 2020   Global Forest Cover 2020 der EU-Kommission (JRC), 10 m – Bildpunkt gefärbt = Wald
     Waldverlust      Tree cover loss (Hansen/UMD über Global Forest Watch), 30 m – unverarbeitete Kachel: Rot 255 = Verlust,
                      Blau = Jahr − 2000 (am 18.11.2026 Bildpunkt für Bildpunkt gegen die eingefärbte Fassung des Dienstes geprüft)
   Gerechnet wird im Browser auf dem Raster der Kacheln von Zoomstufe 12 mit 512 Bildpunkten (rund 9 m je Punkt am Äquator,
   feiner als beide Quellen): Fläche als Maske zeichnen (Randpunkte anteilig), je Punkt zählen, je Zeile mit der wahren
   Punktfläche auf ihrer Breite gewichten (Web-Mercator auf dem Ellipsoid WGS84: cos² der Breite mal (1−e²)/(1−e² sin²)²). Zur Kontrolle liefert das Ergebnis die so gezählte Gesamtfläche – sie muss zur
   berechneten Fläche des Betriebs passen. Flächen über 16 Kacheln (grob 35 × 35 km) werden nicht ausgewertet statt gröber.
   API: window.EUDR_AUSWERTUNG.rechnen(geometrie, bis, quellen) → Promise<{ flaecheHa, waldHa, verlustHa, verlustAufWaldHa,
        vorherHa, jahre: { 2021: ha, … }, bis } | { zuGross: true } | null (keine Fläche)>
        quellen: { wald(bbox3857, punkte) → Adresse, verlustRoh(z, x, y) → Adresse } – aus eudr-karte.js */
(function () {
  'use strict';
  const Z = 12, PUNKTE = 512, MAX_KACHELN = 16, STICHJAHR = 20;   // Verlust zählt ab Jahr 21 (nach dem 31.12.2020)
  const ERDUMFANG = 40075016.686, HALB = ERDUMFANG / 2, E2 = 0.00669437999014;   // WGS84: Umfang am Äquator, erste Exzentrizität²
  const kx = (lon) => (lon + 180) / 360 * 2 ** Z;
  const ky = (lat) => (1 - Math.asinh(Math.tan(lat * Math.PI / 180)) / Math.PI) / 2 * 2 ** Z;
  const breite = (y) => Math.atan(Math.sinh(Math.PI * (1 - 2 * y / 2 ** Z)));   // Breite (Bogenmaß) zur Kachelzeile y, auch gebrochen
  const polygone = (g) => (g.type === 'Polygon' ? [g.coordinates] : g.type === 'MultiPolygon' ? g.coordinates : []);

  /* Bild ohne Farbanpassung laden – sonst könnte der Browser das Jahr im Blaukanal um eins verschieben */
  async function bild(adresse) {
    const r = await fetch(adresse, { credentials: 'omit' });
    if (!r.ok) throw new Error('Kartenbild nicht geladen (' + r.status + ')');
    return createImageBitmap(await r.blob(), { colorSpaceConversion: 'none', premultiplyAlpha: 'none' });
  }
  function leinwand(w, h) {
    const c = document.createElement('canvas'); c.width = w; c.height = h;
    const k = c.getContext('2d', { willReadFrequently: true }); k.imageSmoothingEnabled = false;
    return k;
  }

  async function rechnen(geometrie, bis, quellen) {
    const teile = polygone(geometrie);
    if (!teile.length) return null;
    const xs = teile.flatMap((p) => p[0].map(([lon]) => kx(lon))), ys = teile.flatMap((p) => p[0].map(([, lat]) => ky(lat)));
    const x0 = Math.floor(Math.min(...xs)), y0 = Math.floor(Math.min(...ys)), nx = Math.floor(Math.max(...xs)) - x0 + 1, ny = Math.floor(Math.max(...ys)) - y0 + 1;
    if (nx * ny > MAX_KACHELN) return { zuGross: true };
    const w = nx * PUNKTE, h = ny * PUNKTE;
    const maske = leinwand(w, h), wald = leinwand(w, h), verlust = leinwand(w, h);
    maske.beginPath();
    for (const p of teile) for (const ring of p) { ring.forEach(([lon, lat], i) => maske[i ? 'lineTo' : 'moveTo']((kx(lon) - x0) * PUNKTE, (ky(lat) - y0) * PUNKTE)); maske.closePath(); }
    maske.fill('evenodd');
    const breiteKachel = ERDUMFANG / 2 ** Z;
    await Promise.all(Array.from({ length: nx * ny }, async (_, i) => {
      const x = x0 + i % nx, y = y0 + Math.floor(i / nx), links = -HALB + x * breiteKachel, oben = HALB - y * breiteKachel;
      const [v, f] = await Promise.all([bild(quellen.verlustRoh(Z, x, y)), bild(quellen.wald([links, oben - breiteKachel, links + breiteKachel, oben], PUNKTE))]);
      verlust.drawImage(v, (x - x0) * PUNKTE, (y - y0) * PUNKTE, PUNKTE, PUNKTE);
      wald.drawImage(f, (x - x0) * PUNKTE, (y - y0) * PUNKTE, PUNKTE, PUNKTE);
    }));
    const M = maske.getImageData(0, 0, w, h).data, W = wald.getImageData(0, 0, w, h).data, V = verlust.getImageData(0, 0, w, h).data;
    const e = { flaecheHa: 0, waldHa: 0, verlustHa: 0, verlustAufWaldHa: 0, vorherHa: 0, jahre: {}, bis };
    for (let jahr = 2001 + STICHJAHR; jahr <= bis; jahr++) e.jahre[jahr] = 0;
    for (let zeile = 0; zeile < h; zeile++) {
      const phi = breite(y0 + (zeile + 0.5) / PUNKTE), seite = ERDUMFANG * Math.cos(phi) / (PUNKTE * 2 ** Z);
      const haJePunkt = seite * seite * (1 - E2) / (1 - E2 * Math.sin(phi) ** 2) ** 2 / 10000;
      for (let i = zeile * w * 4, ende = i + w * 4; i < ende; i += 4) {
        if (!M[i + 3]) continue;
        const anteil = M[i + 3] / 255 * haJePunkt, istWald = W[i + 3] > 127, jahr = V[i + 3] > 127 && V[i] > 127 ? V[i + 2] : 0;
        e.flaecheHa += anteil;
        if (istWald) e.waldHa += anteil;
        if (jahr > STICHJAHR && 2000 + jahr <= bis) { e.verlustHa += anteil; e.jahre[2000 + jahr] += anteil; if (istWald) e.verlustAufWaldHa += anteil; }
        else if (jahr > 0 && jahr <= STICHJAHR) e.vorherHa += anteil;
      }
    }
    return e;
  }

  window.EUDR_AUSWERTUNG = { rechnen };
})();
