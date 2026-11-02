/* Zahlen, Beträge, Mengen, Prozente und Datum – EIN Format für alle Seiten der Plattform (Auftrag des Inhabers 02.11.2026:
   „überall Euros, wo Euros hingehören, Kilos, wo Kilos hingehören, Prozente, wo Prozente hingehören – und überall gleich“).
   Jede Seite lädt diese Datei vor ihren eigenen Skripten und nutzt window.STAFL_FORMAT statt eigener Formatierer.

   Regeln (docs/entwickler/10-konventionen.md, geprüft in der Testgruppe „einheit“):
   - Beträge immer mit 2 Nachkommastellen und „€“: 1.234,50 €. In Kennzahl-Kacheln erst ab 100 Mio. kurz (123,46 Mio. €,
     voller Wert im Tooltip).
   - Preise je kg: 12,35 €/kg – immer 2 Nachkommastellen, wie Bestellwunsch, E-Mail und Abrechnung (4,125 → 4,13).
   - Mengen immer in kg (nie t) mit 2 Nachkommastellen (1.782,50 kg – wie Bestand, Lieferschein und PDF, untereinander
     bündig); Summen in Auswertungen und Kennzahlen (Controlling, CRM) ab 100 kg ganz (1.783 kg).
   - Prozent mit 1 Nachkommastelle: 12,3 %; Veränderungen mit Vorzeichen +12,3 % / −12,3 % / ±0,0 %; Prozentpunkte „Pp“.
   - Minus als echtes Minuszeichen (−), zwischen Zahl und Einheit ein Leerzeichen (wie bisher auf den meisten Seiten).
   - Fehlender Wert: „—“. Null ist ein Wert (0,00 €, 0 kg).
   - Datum 02.11.2026, mit Uhrzeit 02.11.2026, 14:05; Kalenderwoche KW 45/2026.
   CSV-Dateien bleiben maschinenlesbar (ohne Tausenderpunkt und Einheit) und nutzen diese Datei nicht. */
(function () {
  var NB = ' ', MINUS = '−', LEER = '—';
  var cache = {};
  function nf(min, max) {
    var k = min + ':' + max;
    if (!cache[k]) cache[k] = new Intl.NumberFormat('de-DE', { minimumFractionDigits: min, maximumFractionDigits: max });
    return cache[k];
  }
  function wert(v) {
    if (v === null || v === undefined || v === '') return null;
    var s = String(v).trim();   // Zahl aus der API; Text mit Komma wie in einer Eingabe („1.234,5“)
    var n = typeof v === 'number' ? v : s.indexOf(',') >= 0 ? Number(s.replace(/\./g, '').replace(',', '.')) : Number(s);
    return Number.isFinite(n) ? n : null;
  }
  /* Kaufmännisch runden wie der Server (PHP round): 12,345 → 12,35, auch wenn die Binärzahl knapp darunter liegt */
  function runden(n, stellen) {
    var r = Number(Math.round(Number(n + 'e' + stellen)) + 'e-' + stellen);
    return Number.isFinite(r) ? r : n;
  }
  /* Zahl mit min…max Nachkommastellen, echtes Minus; -0 wird 0 */
  function zahl(v, min, max) {
    var n = wert(v);
    if (n === null) return LEER;
    if (min === undefined) min = 0;
    if (max === undefined) max = Math.max(min, 2);
    var s = nf(min, max).format(runden(Math.abs(n), max));
    return (n < 0 && s.replace(/[0,.]/g, '') !== '' ? MINUS : '') + s;
  }
  function mitEinheit(s, einheit) { return s === LEER ? LEER : s + NB + einheit; }
  function euro(v) { return mitEinheit(zahl(v, 2, 2), '€'); }
  function euroKachel(v) {
    var n = wert(v);
    if (n !== null && Math.abs(n) >= 1e8) return mitEinheit(zahl(n / 1e6, 2, 2) + NB + 'Mio.', '€');
    return euro(v);
  }
  function euroKg(v) { return mitEinheit(zahl(v, 2, 2), '€/kg'); }
  function kg(v) { return mitEinheit(zahl(v, 2, 2), 'kg'); }
  function kgSumme(v) { var n = wert(v); return n === null ? LEER : mitEinheit(zahl(n, 0, Math.abs(n) >= 100 ? 0 : 1), 'kg'); }
  /* Anteil als Bruch (0,123 → 12,3 %) */
  function prozent(anteil) { var n = wert(anteil); return n === null ? LEER : mitEinheit(zahl(n * 100, 1, 1), '%'); }
  function vorzeichen(n, s) { return (n > 0 && s.replace(/[0,.]/g, '') !== '' ? '+' : s.replace(/[0,.]/g, '') === '' ? '±' : '') + s; }
  /* Veränderung als Bruch (0,123 → +12,3 %) */
  function veraenderung(anteil) { var n = wert(anteil); if (n === null) return LEER; return mitEinheit(vorzeichen(n, zahl(n * 100, 1, 1)), '%'); }
  /* Differenz zweier Anteile in Prozentpunkten (0,012 → +1,2 Pp) */
  function pp(anteil) { var n = wert(anteil); if (n === null) return LEER; return mitEinheit(vorzeichen(n, zahl(n * 100, 1, 1)), 'Pp'); }
  /* Differenz mit Vorzeichen in einer Einheit (z. B. Preisänderung: +0,50 €/kg) */
  function differenz(v, einheit, min, max) {
    var n = wert(v); if (n === null) return LEER;
    var s = vorzeichen(n, zahl(n, min === undefined ? 2 : min, max === undefined ? 2 : max));
    return einheit ? mitEinheit(s, einheit) : s;
  }
  function alsDatum(d) {
    if (d === null || d === undefined || d === '') return null;
    if (d instanceof Date) return isNaN(d) ? null : d;
    if (typeof d === 'number') { var z = new Date(d < 1e11 ? d * 1000 : d); return isNaN(z) ? null : z; }
    var s = String(d);
    if (/^\d{4}-\d{2}-\d{2}$/.test(s)) { var p = s.split('-'); return new Date(+p[0], +p[1] - 1, +p[2]); }   // reines Datum: Ortszeit
    var t = new Date(s); return isNaN(t) ? null : t;
  }
  var DF = null, DZF = null;
  function datum(d) {
    var m = typeof d === 'string' && /^(\d{4})-(\d{2})-(\d{2})/.exec(d);
    if (m && d.length === 10) return m[3] + '.' + m[2] + '.' + m[1];   // reines Datum: ohne Umrechnung der Zeitzone
    var t = alsDatum(d); if (!t) return LEER;
    if (!DF) DF = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', timeZone: 'Europe/Berlin' });
    return DF.format(t);
  }
  function datumZeit(d) {
    var t = alsDatum(d); if (!t) return LEER;
    if (!DZF) DZF = new Intl.DateTimeFormat('de-DE', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Berlin' });
    return DZF.format(t);
  }
  function kw(woche, jahr) { return woche ? 'KW' + NB + woche + (jahr ? '/' + jahr : '') : LEER; }
  window.STAFL_FORMAT = { LEER: LEER, zahl: zahl, euro: euro, euroKachel: euroKachel, euroKg: euroKg, kg: kg, kgSumme: kgSumme,
    prozent: prozent, veraenderung: veraenderung, pp: pp, differenz: differenz, datum: datum, datumZeit: datumZeit, kw: kw };
})();
