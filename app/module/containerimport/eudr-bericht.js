/* STAFL-Plattform · Container-Import · EUDR – Entwaldungsberichte der Lieferanten lesen (reine Funktionen, kein DOM).
   Eingabe: die Textstücke einer PDF-Datei mit ihrer Lage auf der Seite ([[{ s, x, y }, …] je Seite], aus pdf.js) – nichts
   wird hochgeladen, der Bericht wird im Browser gelesen. Ausgabe: ein Produktionsort in der Form, die der Server prüft
   (containerimport_eudr_pruefen): Name, Erzeuger, Land, Kennung, Region, Ort, angegebene Fläche, Angaben des Berichts und
   die Koordinatenliste mit Bezugssystem.
   Gelesen wird das Format „Report on compliance with the EU“ (Hendata & Global Canopy, Paraguay): Tabelle „Farm information
   summary“ (Spalten über ihre Lage zugeordnet, weil Werte umbrechen), die Tabellen zur Konformität, die Kennungen der
   Satellitenbilder (daraus UTM-Zone und Halbkugel) und „Coordinates of farm“ als p0 x y, p1 x y … in UTM.
   Was sich nicht lesen lässt, bleibt leer und wird im Fenster von Hand ergänzt; der Server prüft alles noch einmal.
   Landnutzungsplan und Umweltgenehmigung („National Compliance Table“) liest die Seite nicht: bisher stand dort nie eine
   Angabe – beides wird am Betrieb von Hand gepflegt und beim erneuten Einlesen nicht überschrieben.
   API: window.EUDR_BERICHT.lesen(seiten) → { ort, bezug, anbieter } | { fehler } | null · .punkte(text) → [[x, y], …] | null */
(function (root) {
  'use strict';
  const LAENDER = { paraguay: 'PY', argentina: 'AR', brazil: 'BR', brasil: 'BR', uruguay: 'UY', bolivia: 'BO', colombia: 'CO' };
  /* Spalten der Tabelle „Farm information summary“: Feld → Muster der Überschrift */
  const SPALTEN = [['kennung', /^SIGOR/i], ['name', /^Farm Name/i], ['erzeuger', /^Owner/i], ['land', /^Country/i], ['region', /^Department/i], ['ort', /^District/i], ['flaecheAngabe', /^Farm area/i]];
  /* Abschnitte des Berichts: Feld → Überschrift der Tabelle */
  const ABSCHNITTE = [['entwaldung', /Deforestation-free compliance table/i], ['schutzgebiet', /Overlap with Protected Areas Table/i], ['indigen', /Overlap with Indigenous Territories Table/i], ['ende', /National Compliance Table|Data used for/i]];
  const ZAHL = '-?\\d+(?:\\.\\d+)?';

  const LUECKE = 4;   // Punkt: bis zu diesem Abstand gehören zwei Textstücke einer Zeile zum selben Lauf (Wort, Zelle)

  /* Zeilen einer Seite, von oben nach unten: je Zeile die Läufe von links nach rechts. pdf.js liefert Text oft in Stücken
     („500000“, „.“, „00“) – Stücke ohne Lücke werden zusammengesetzt, damit Zahlen und Tabellenzellen ganz bleiben. */
  function zeilen(stuecke) {
    const sortiert = [...stuecke].sort((a, b) => b.y - a.y || a.x - b.x);
    const gruppen = [];
    for (const t of sortiert) {
      const letzte = gruppen[gruppen.length - 1];
      if (letzte && Math.abs(letzte.y - t.y) < 3) letzte.stuecke.push(t); else gruppen.push({ y: t.y, stuecke: [t] });
    }
    return gruppen.map((g) => {
      const laeufe = [];
      let leer = false;
      for (const t of g.stuecke.sort((a, b) => a.x - b.x)) {
        if (t.s.trim() === '') { leer = leer || t.s !== ''; continue; }
        const w = Number.isFinite(t.w) ? t.w : 0, l = laeufe[laeufe.length - 1];
        const abstand = l ? t.x - (l.x + l.w) : Infinity;
        if (abstand < LUECKE) { l.s += (leer || abstand >= 1 ? ' ' : '') + t.s; l.w = t.x + w - l.x; } else laeufe.push({ s: t.s, x: t.x, w });
        leer = false;
      }
      return { y: g.y, stuecke: laeufe };
    }).filter((z) => z.stuecke.length);
  }
  /* Zahl aus dem Bericht: Dezimalpunkt, Tausenderkommas („1,234.5“) entfernt */
  const zahl = (text) => Number(String(text).replace(/,(?=\d{3}(\D|$))/g, ''));
  /* Koordinatenpaare aus Text: „p0 500000.00 7400000.00, p1 …“, „p0,500000.00,7400000.00,p1,…“ oder je Zeile „x y“.
     Bei nummerierten Listen müssen die Nummern lückenlos ab 0 aufsteigen – fehlt eine (Zahl beim Umbruch zerrissen), ist das
     Ergebnis null statt eines Umrisses mit einer Ecke weniger. */
  function punkte(text) {
    const mitNummer = [...String(text).matchAll(new RegExp(`p(\\d+)[\\s,;]+(${ZAHL})[\\s,;]+(${ZAHL})`, 'gi'))];
    if (mitNummer.length) return mitNummer.every((m, i) => Number(m[1]) === i) ? mitNummer.map((m) => [Number(m[2]), Number(m[3])]) : null;
    return [...String(text).matchAll(new RegExp(`(${ZAHL})[\\s,;]+(${ZAHL})`, 'g'))].map((m) => [Number(m[1]), Number(m[2])]);
  }
  /* „Compliant“ / „Non-compliant“ und die Zahl danach aus dem Text eines Abschnitts. Die Verneinung zählt in jeder
     Schreibweise (Bindestrich, Umbruch, „not“); steht beides im Abschnitt, gilt die Verneinung. */
  function konform(text) {
    const nein = /\bnon\W*compliant|\bnot\W+compliant/i.exec(text), ja = /\bcompliant\b/i.exec(text);
    if (!nein && !ja) return { stand: 'unbekannt', ha: null };
    const danach = /^\W*(\d[\d,]*(?:\.\d+)?)/.exec(text.slice((nein || ja).index + (nein || ja)[0].length));
    return { stand: nein ? 'nicht_konform' : 'konform', ha: danach ? zahl(danach[1]) : null };
  }
  /* Werte der Tabelle „Farm information summary“: jedes Textstück unter den Überschriften gehört zur nächstgelegenen Spalte */
  function stammdaten(zeilenListe) {
    const kopf = zeilenListe.findIndex((z) => z.stuecke.some((t) => SPALTEN[0][1].test(t.s.trim())));
    if (kopf < 0) return {};
    const spalten = [];
    for (const [feld, muster] of SPALTEN) {
      const t = zeilenListe[kopf].stuecke.find((x) => muster.test(x.s.trim()));
      if (t) spalten.push({ feld, x: t.x + (t.w || 0) / 2, teile: [] });
    }
    for (let i = kopf + 1; i < zeilenListe.length; i++) {
      const text = zeilenListe[i].stuecke.map((t) => t.s).join(' ');
      if (ABSCHNITTE[0][1].test(text)) break;
      for (const t of zeilenListe[i].stuecke) {
        const mitte = t.x + (t.w || 0) / 2;
        spalten.reduce((a, b) => (Math.abs(b.x - mitte) < Math.abs(a.x - mitte) ? b : a)).teile.push(t.s.trim());
      }
    }
    return Object.fromEntries(spalten.map((s) => [s.feld, s.teile.join(' ').replace(/\s+/g, ' ').trim()]));
  }

  /* Plausible UTM-Werte (Rechtswert, Hochwert)? Fängt z. B. eine Seitenzahl ab, die zwischen zwei Zahlen geraten ist. */
  const utm = ([rechts, hoch]) => rechts >= 100000 && rechts <= 900000 && hoch >= 1000 && hoch <= 10000000;

  /* Bericht lesen. null, wenn die Datei keine Koordinatenliste enthält (dann ist es kein solcher Bericht);
     { fehler } wenn sie eine enthält, die sich nicht sicher lesen lässt. */
  function lesen(seiten) {
    const zeilenListe = seiten.flatMap(zeilen);
    const text = zeilenListe.map((z) => z.stuecke.map((t) => t.s).join(' ')).join('\n');
    const listen = text.split(/Coordinates of farm\s*\d*:?/i).slice(1);
    if (!listen.length) return null;
    if (listen.length > 1) return { fehler: 'Der Bericht enthält mehrere Flächen – bitte je Betrieb einen Bericht oder ein GeoJSON einlesen.' };
    const liste = punkte(listen[0]);
    if (!liste || liste.length < 3 || !liste.every(utm)) return { fehler: 'Die Koordinatenliste lässt sich nicht sicher lesen (Lücke in der Nummerierung oder unplausible Werte) – bitte die Koordinaten von Hand einfügen.' };
    const s = stammdaten(zeilenListe);
    const stellen = ABSCHNITTE.map(([feld, muster]) => [feld, text.search(muster)]).filter(([, i]) => i >= 0).sort((a, b) => a[1] - b[1]);
    const abschnitt = (feld) => { const i = stellen.findIndex(([f]) => f === feld); return i < 0 ? '' : text.slice(stellen[i][1], i + 1 < stellen.length ? stellen[i + 1][1] : undefined); };
    const [entwaldung, schutzgebiet, indigen] = ['entwaldung', 'schutzgebiet', 'indigen'].map((f) => konform(abschnitt(f)));
    const datum = /Analysis Date:\s*(\d{2})\/(\d{2})\/(\d{4})/i.exec(text);
    const landText = (s.land || (/Farm Country:\s*([A-Za-z ]+)/i.exec(text) || [])[1] || '').trim().toLowerCase();
    // Sentinel-2-Kacheln nennen Zone und Breitenband (vor N = Südhalbkugel). Nennt der Bericht verschiedene Zonen, bleibt
    // die Zone leer – der Server verlangt sie dann, statt die Fläche um hunderte Kilometer zu versetzen.
    const kacheln = [...text.matchAll(/_T(\d{2})([C-HJ-NP-X])[A-Z]{2}\b/g)];
    const kachel = kacheln.length && kacheln.every((k) => k[1] === kacheln[0][1] && (k[2] < 'N') === (kacheln[0][2] < 'N')) ? kacheln[0] : null;
    const jahre = [...text.matchAll(/S2_SR_HARMONIZED\/(\d{4})\d{4}T/g)].map((m) => Number(m[1]));
    const flaeche = zahl(s.flaecheAngabe || '');
    return {
      anbieter: /Hendata/i.test(text) ? 'Hendata & Global Canopy' : '',
      bezug: kachel ? `UTM ${Number(kachel[1])}${kachel[2] < 'N' ? 'S' : 'N'}` : '',
      ort: {
        name: s.name || '', erzeuger: s.erzeuger || '', land: LAENDER[landText] || '', kennung: s.kennung || '', region: s.region || '', ort: s.ort || '',
        flaecheAngabe: Number.isFinite(flaeche) && flaeche > 0 ? flaeche : null,
        bericht: {
          datum: datum ? `${datum[3]}-${datum[2]}-${datum[1]}` : '',
          entwaldung: entwaldung.stand, entwaldungHa: entwaldung.ha, schutzgebiet: schutzgebiet.stand, indigen: indigen.stand,
          bilderBis: jahre.length ? Math.max(...jahre) : null,
        },
        koordinaten: { system: 'utm', zone: kachel ? Number(kachel[1]) : null, sued: kachel ? kachel[2] < 'N' : true, punkte: liste },
      },
    };
  }

  root.EUDR_BERICHT = { lesen, punkte };
})(typeof window !== 'undefined' ? window : globalThis);
