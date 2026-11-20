/* Angebot · Preisänderung zur Vorwoche auf der Angebotsseite (frontend.js, Inhaber 20.11.2026): nur mit ?vergleich=vorwoche
   bzw. =aenderungen. Rechnet nichts: der Server liefert je Angebot die Liste der Änderungen (Aktion offer mit
   vergleich=vorwoche, api/module/angebot/vorwoche.php) – {kw, jahr, aenderungen: {Artikel-ID: {art: 'neu'} |
   {art: 'guenstiger' | 'teurer', d, alt}}}; unveränderte Artikel fehlen dort. Hier wird nur nachgeschlagen und gezeichnet:
   je Artikel ein kleiner farbiger Hinweis „▼ 2,00“ / „▲ 1,00“ / „neu“ und die Legende. Ohne Vergleich liefern html() und
   legende() '' – die Seite bleibt wie bisher. Lage und Größe regeln app.css (Bildschirm) und angebot-druck.css (Druck).
   Schnittstelle: window.Vorwoche = { setzen(vorwoche, nurAenderungen), aktiv(), geaendert(it), html(it, cls), legende(vor, nach) }. */
(function (root) {
  'use strict';
  const zahl = (v) => root.STAFL_FORMAT.zahl(v, 2, 2);
  let vw = null, nur = false;
  const aenderung = (it) => (vw && Object.prototype.hasOwnProperty.call(vw.aenderungen, it.id) ? vw.aenderungen[it.id] : null);
  root.Vorwoche = {
    setzen(v, nurAenderungen) { vw = v && v.aenderungen ? v : null; nur = nurAenderungen; },
    aktiv: () => !!vw,
    geaendert: (it) => !!aenderung(it),
    /* Hinweis je Artikel; cls „vw-pille“ (Karten, Tabelle) mit Fläche */
    html(it, cls = '') {
      const a = aenderung(it);
      if (!a) return '';
      const kw = 'KW ' + Number(vw.kw);
      const [zeichen, lang] = a.art === 'neu' ? ['neu', `neu, nicht im Angebot der ${kw}`]
        : [`${a.d < 0 ? '▼' : '▲'} ${zahl(Math.abs(a.d))}`, `${a.d < 0 ? 'günstiger' : 'teurer'} um ${zahl(Math.abs(a.d))} € (${kw}: ${zahl(a.alt)} €/kg)`];
      return `<span class="vw vw-${a.art}${cls ? ' ' + cls : ''}" title="${lang}"><span aria-hidden="true">${zeichen}</span><span class="sr-only">${lang}</span></span>`;
    },
    /* Legende, von vor/nach umrahmt (z. B. Trenner); ohne Vergleich '' */
    legende: (vor = '', nach = '') => (vw ? `${vor}<span class="vw-leg">${nur ? 'Nur Änderungen' : 'Veränderung'} zur KW ${Number(vw.kw)}: <span class="vw vw-guenstiger">▼ günstiger</span> <span class="vw vw-teurer">▲ teurer</span> <span class="vw vw-neu">neu</span></span>${nach}` : ''),
  };
})(window);
