/* Textsuche – EINE Regel für alle Suchfelder der Plattform (Prüfung der Suchfunktionen, Auftrag des Inhabers 10.11.2026).
   Jede Seite lädt diese Datei vor ihren eigenen Skripten und nutzt window.STAFL_SUCHE statt eigener Vergleiche.

   Regeln (docs/entwickler/10-konventionen.md, geprüft in der Testgruppe „einheit“):
   - Groß-/Kleinschreibung und Akzente zählen nicht: „muller“ findet „Müller“, „cafe“ findet „Café“.
   - Umlaute und ß auch ausgeschrieben: „Mueller“, „Faerse“, „Strasse“ finden „Müller“, „Färse“, „Straße“ – und umgekehrt.
   - Mehrere Wörter: jedes Wort muss vorkommen, Reihenfolge und Feld egal („filet rind“ findet „Rinderfilet“ ebenso wie
     Bezeichnung „Filet“ mit Herkunft „Rind …“; „eiche hamburg“ findet Firma und Ort).
   - Nummern: eine reine Ziffernfolge ab vier Stellen findet auch gegliedert geschriebene Nummern
     („0401234567“ findet „040 1234567“ oder „040/12 34-567“) – nie über Feldgrenzen hinweg.
   - Leerzeichen am Rand und mehrfache Leerzeichen zählen nicht; eine leere Suche passt auf alles.

   norm(text)            Text für den Vergleich (klein, ohne Akzente, ä/ae → a, ö/oe → o, ü/ue → u, ß/ss → s)
   woerter(eingabe)      Suchwörter der Eingabe (schon mit norm)
   heu(...felder)        durchsuchbarer Text aus mehreren Feldern (leere Felder entfallen; Felder bleiben getrennt)
   passt(suche, text)    true, wenn jedes Suchwort im Text vorkommt; suche = Eingabe oder woerter(…), text = heu(…) bzw.
                         norm(…) – fertig vorbereitete Texte je Zeile sparen bei langen Listen das wiederholte Umformen
   findet(eingabe, ...felder)   Kurzform: passt(eingabe, heu(...felder)) */
(function (root) {
  'use strict';
  const TRENNER = ' │ ';   // zwischen Feldern: verhindert Treffer über Feldgrenzen (auch bei der Nummernsuche)
  const norm = (s) => String(s ?? '').toLocaleLowerCase('de-DE').normalize('NFD').replace(/[̀-ͯ]/g, '')
    .replace(/ß/g, 'ss').replace(/œ/g, 'oe').replace(/æ/g, 'ae').replace(/ø/g, 'o')
    .replace(/ae/g, 'a').replace(/oe/g, 'o').replace(/ue/g, 'u').replace(/ss/g, 's');
  const woerter = (q) => (Array.isArray(q) ? q : norm(q).split(/\s+/).filter(Boolean));
  const heu = (...felder) => norm(felder.flat().filter((f) => f !== null && f !== undefined && f !== '').join(TRENNER));
  const kompakt = (h) => h.replace(/(\d)[\s./()\-]+(?=\d)/g, '$1');   // Gliederung zwischen Ziffern entfernen (innerhalb eines Feldes)
  function passt(suche, text) {
    const w = woerter(suche);
    if (!w.length) return true;
    const h = String(text ?? '');
    let k = null;
    return w.every((t) => {
      if (h.includes(t)) return true;
      const z = t.replace(/[./()\-]/g, '');   // „040/1234567“ wie „0401234567“
      return /^\d{4,}$/.test(z) && (k ??= kompakt(h)).includes(z);
    });
  }
  const findet = (eingabe, ...felder) => passt(eingabe, heu(...felder));

  root.STAFL_SUCHE = { norm, woerter, heu, passt, findet };
})(typeof window !== 'undefined' ? window : globalThis);
