/* Angebot · Preisänderung zur Vorwoche auf der Angebotsseite (frontend.js, Inhaber 20.11.2026): nur mit ?vergleich=vorwoche,
   =pfeil bzw. =aenderungen. Rechnet nichts: der Server liefert je Angebot die Liste der Änderungen (Aktion offer mit
   vergleich=vorwoche, api/module/angebot/vorwoche.php) – {kw, jahr, stufen, aenderungen: {Artikel-ID: {art: 'neu'} |
   {art: 'guenstiger' | 'teurer', d, alt, p, stufe}}}; unveränderte Artikel fehlen dort. Hier wird nur nachgeschlagen und gezeichnet:
   je Artikel ein kleiner farbiger Hinweis „▼ 2,00“ / „▲ 1,00“ / „neu“ und die Legende; Darstellung „pfeil“ (Inhaber 20.11.2026,
   Zusatzversion) zeigt statt des Betrags nur einen Pfeil, je stufe 30°, 60° oder 90° gegen die Waagerechte geneigt. Ohne Vergleich
   liefern html() und legende() '' – die Seite bleibt wie bisher. Lage und Größe regeln app.css (Bildschirm) und angebot-druck.css (Druck).
   Schnittstelle: window.Vorwoche = { setzen(vorwoche, modus), aktiv(), geaendert(it), html(it, cls), legende(vor, nach) },
   modus = 'vorwoche' | 'aenderungen' | 'pfeil'. */
(function (root) {
  'use strict';
  const zahl = (v) => root.STAFL_FORMAT.zahl(v, 2, 2);
  const WINKEL = { 1: 30, 2: 60, 3: 90 };
  /* Pfeil nach rechts, gedreht: teurer nach oben (gegen den Uhrzeigersinn), günstiger nach unten */
  const pfeilSVG = (art, stufe) => `<svg class="vw-svg" viewBox="0 0 16 16" aria-hidden="true" style="transform:rotate(${(art === 'teurer' ? -1 : 1) * WINKEL[stufe]}deg)"><path d="M2 8h11.5M9 3.5 13.5 8 9 12.5" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
  let vw = null, nur = false, pfeil = false;
  const aenderung = (it) => (vw && Object.prototype.hasOwnProperty.call(vw.aenderungen, it.id) ? vw.aenderungen[it.id] : null);
  root.Vorwoche = {
    setzen(v, modus) { vw = v && v.aenderungen ? v : null; nur = modus === 'aenderungen'; pfeil = modus === 'pfeil'; },
    aktiv: () => !!vw,
    geaendert: (it) => !!aenderung(it),
    /* Hinweis je Artikel; cls „vw-pille“ (Karten, Tabelle) mit Fläche */
    html(it, cls = '') {
      const a = aenderung(it);
      if (!a) return '';
      const kw = 'KW ' + Number(vw.kw);
      const um = pfeil && a.p != null ? root.STAFL_FORMAT.zahl(Math.abs(a.p), 1, 1) + ' %' : zahl(Math.abs(a.d)) + ' €';
      const [zeichen, lang] = a.art === 'neu' ? ['neu', `neu, nicht im Angebot der ${kw}`]
        : [pfeil ? pfeilSVG(a.art, a.stufe) : `${a.d < 0 ? '▼' : '▲'} ${zahl(Math.abs(a.d))}`, `${a.d < 0 ? 'günstiger' : 'teurer'} um ${um} (${kw}: ${zahl(a.alt)} €/kg)`];
      return `<span class="vw vw-${a.art}${pfeil && a.art !== 'neu' ? ' vw-pfeil' : ''}${cls ? ' ' + cls : ''}" title="${lang}"><span aria-hidden="true">${zeichen}</span><span class="sr-only">${lang}</span></span>`;
    },
    /* Legende, von vor/nach umrahmt (z. B. Trenner); ohne Vergleich '' */
    legende(vor = '', nach = '') {
      if (!vw) return '';
      const kopf = `${nur ? 'Nur Änderungen' : 'Veränderung'} zur KW ${Number(vw.kw)}:`;
      const ab = (vw.stufen || []).map((g) => 'ab ' + root.STAFL_FORMAT.zahl(g, 0, 1) + ' %').join(' / ');
      return `${vor}<span class="vw-leg">${kopf} ${pfeil
        ? `<span class="vw vw-teurer vw-pfeil">${pfeilSVG('teurer', 3)} teurer</span> <span class="vw vw-guenstiger vw-pfeil">${pfeilSVG('guenstiger', 3)} günstiger</span> <span class="vw vw-neu">neu</span> · steiler = stärker${ab ? ` (${ab})` : ''}`
        : '<span class="vw vw-guenstiger">▼ günstiger</span> <span class="vw vw-teurer">▲ teurer</span> <span class="vw vw-neu">neu</span>'}</span>${nach}`;
    },
  };
})(window);
