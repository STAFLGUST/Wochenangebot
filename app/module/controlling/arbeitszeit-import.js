/* STAFL-Plattform · Controlling · Leser der Importart „zeitbericht“ (Verwaltung → Import, window.WA.importLeser).
   Liest das erste Tabellenblatt des Zeitberichts der Zeiterfassung (.xlsx) mit OfferCore.xlsxReadWorkbook und schickt es
   unverändert als Raster (höchstens 60 000 Zeilen, 25 Spalten) an den Server. Spalten erkennen, Zeiten lesen, Folgezeilen
   mit weiteren Stempeln zuordnen und Stempelfehler markieren macht nur der Server (module/controlling/arbeitszeit.php) –
   es gibt genau eine Prüflogik. Wird von admin/index.html geladen. */
(function () {
  'use strict';
  const W = window.WA;
  if (!W) return;
  const ZEILEN = 60000, SPALTEN = 25;

  W.importLeser = W.importLeser || {};
  W.importLeser.zeitbericht = {
    async lesen(files) {
      const f = files[0];
      const blaetter = await window.OfferCore.xlsxReadWorkbook(await f.arrayBuffer());
      const b = blaetter[0];
      if (!b || !b.grid.length) return { daten: { blaetter: [] }, zeilen: 0, fehler: [{ datei: f.name, text: 'Die Datei enthält kein Tabellenblatt mit Zeilen.' }], hinweise: [] };
      if (b.grid.length > ZEILEN) throw new Error(`Die Datei hat mehr als ${ZEILEN.toLocaleString('de-DE')} Zeilen – bitte einen kürzeren Zeitraum exportieren.`);
      const grid = b.grid.map((z) => Array.from({ length: Math.min(z.length, SPALTEN) }, (_, i) => z[i] ?? null));
      const hinweise = blaetter.length > 1 ? [{ stufe: 'info', text: `Gelesen wird nur das erste Tabellenblatt („${b.name}“).` }] : [];
      return { daten: { blaetter: [{ name: b.name, grid }] }, zeilen: Math.max(0, grid.length - 1), fehler: [], hinweise };
    },
    nachher() {},
  };
})();
