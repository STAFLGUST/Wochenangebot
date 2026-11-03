/* STAFL-Plattform · Controlling · Leser der Importart „umsatzdaten“ (Verwaltung → Import, window.WA.importLeser).
   Liest die Kundenumsatztabelle der Warenwirtschaft (CSV, Semikolon, Spalten Kunde, Datum, Artikel, Kolli, Menge, Preis,
   Gesamtbetrag, EKPreis – Reihenfolge egal) und fasst sie je Kunde, Artikel und Tag zusammen, getrennt nach berechnet
   (mit Gesamtbetrag) und ohne Berechnung (z. B. Leergut). Zeilen ohne Artikel (Belegköpfe) zählen nur für den Zeitraum.
   Ergebnis: Zusammenfassung je Monat mit Prüfsumme (daten) und je Monat ein Teil mit den Zeilen (teile) – die
   Importzentrale schickt nur die Teile, die der Server für die Übernahme verlangt (geänderte Monate).
   Zeile: [Tag, Kunde, Artikel, Kolli, Menge (Tausendstel), Umsatz (Cent), EK-Wert (Cent), Umsatz mit EK (Cent), Positionen,
   berechnet 1/0], sortiert nach Tag, Kunde, Artikel, berechnet. Prüfsumme = SHA-256 von JSON.stringify(Zeilen) – der Server
   rechnet sie genauso (module/controlling/umsatzdaten.php) und prüft jede Zeile erneut. Wird von admin/index.html geladen. */
(function () {
  'use strict';
  const W = window.WA;
  if (!W) return;
  const SPALTEN = { kunde: 'kunde', datum: 'datum', artikel: 'artikel', kolli: 'kolli', menge: 'menge', preis: 'preis', gesamtbetrag: 'betrag', ekpreis: 'ek' };
  const PFLICHT = ['kunde', 'datum', 'artikel', 'menge', 'betrag'];
  const NUMMER = /^[0-9A-Za-z._-]{1,20}$/;
  const ARTIKELNR = /^[0-9A-Za-z._/-]{1,20}$/;

  /* Felder einer CSV-Zeile (Semikolon, Anführungszeichen mit "" als Maskierung) */
  function felder(z) {
    const out = [];
    let i = 0;
    const n = z.length;
    for (;;) {
      if (z.charCodeAt(i) === 34) {   // "
        let s = '', j = i + 1;
        for (;;) {
          const k = z.indexOf('"', j);
          if (k < 0) { s += z.slice(j); i = n; break; }
          if (z.charCodeAt(k + 1) === 34) { s += z.slice(j, k) + '"'; j = k + 2; continue; }
          s += z.slice(j, k); i = k + 1; break;
        }
        const k = z.indexOf(';', i);
        out.push(s);
        if (k < 0) return out;
        i = k + 1;
      } else {
        const k = z.indexOf(';', i);
        if (k < 0) { out.push(z.slice(i).trim()); return out; }
        out.push(z.slice(i, k).trim());
        i = k + 1;
      }
    }
  }
  /* Deutsche Zahl („1.347,25“, „-12“, „317,000“) als Ganzzahl in 10^-stellen; leer → null; ungültig → NaN */
  function festkomma(s, stellen) {
    s = (s || '').trim();
    if (s === '') return null;
    const m = /^(-?)([0-9.]*)(?:,([0-9]*))?$/.exec(s);
    if (!m || (m[2].replace(/\./g, '') === '' && !m[3])) return NaN;
    const ganz = m[2].replace(/\./g, '') || '0';
    let teil = (m[3] || '');
    let auf = 0;
    if (teil.length > stellen) { auf = Number(teil[stellen]) >= 5 ? 1 : 0; teil = teil.slice(0, stellen); }
    const v = Number(ganz + teil.padEnd(stellen, '0')) + auf;
    return m[1] ? -v : v;
  }
  /* „TT.MM.JJJJ“ → [JJJJ-MM, Tag] oder null */
  function datum(s) {
    const m = /^(\d{1,2})\.(\d{1,2})\.(\d{4})$/.exec((s || '').trim());
    if (!m) return null;
    const t = Number(m[1]), mo = Number(m[2]), j = Number(m[3]);
    if (j < 2000 || j > 2100 || mo < 1 || mo > 12 || t < 1 || t > new Date(j, mo, 0).getDate()) return null;
    return [`${j}-${String(mo).padStart(2, '0')}`, t];
  }
  const vgl = (a, b) => (a < b ? -1 : a > b ? 1 : 0);
  async function sha256(text) {
    const h = new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(text)));
    return [...h].map((x) => x.toString(16).padStart(2, '0')).join('');
  }
  function dekodieren(buf) {
    const b = new Uint8Array(buf);
    if (b[0] === 0xef && b[1] === 0xbb && b[2] === 0xbf) return new TextDecoder('utf-8').decode(b.subarray(3));
    try { return new TextDecoder('utf-8', { fatal: true }).decode(b); } catch { return new TextDecoder('windows-1252').decode(b); }
  }

  async function lesen(dateien) {
    const text = dekodieren(await dateien[0].arrayBuffer());
    let pos = 0, nr = 0, kopf = null;
    const fehler = [], summen = new Map(), kunden = new Set(), artikel = new Set();
    let von = null, bis = null, zeilen = 0, ohneArtikel = 0, leer = 0, mitEk = false;
    const fehlerhaft = (zeile, schluessel, t) => { fehler.push({ zeile, schluessel, text: t }); };
    while (pos < text.length) {
      let ende = text.indexOf('\n', pos);
      if (ende < 0) ende = text.length;
      let z = text.slice(pos, ende);
      pos = ende + 1; nr++;
      if (z.endsWith('\r')) z = z.slice(0, -1);
      if (!z.replace(/[;"\s\uFEFF]/g, '')) continue;
      const f = felder(z.replace(/^\uFEFF/, ''));
      if (!kopf) {
        kopf = {};
        f.forEach((name, i) => { const k = SPALTEN[name.toLowerCase().replace(/[\s._-]/g, '')]; if (k && !(k in kopf)) kopf[k] = i; });
        const fehlt = PFLICHT.filter((k) => !(k in kopf));
        if (fehlt.length) throw new Error(`Falsche Datei: Die Kundenumsatztabelle braucht die Spalten Kunde, Datum, Artikel, Menge und Gesamtbetrag (gefunden: ${f.slice(0, 10).join(', ') || 'keine Kopfzeile'}).`);
        mitEk = 'ek' in kopf;
        continue;
      }
      const wert = (k) => (k in kopf ? (f[kopf[k]] || '') : '');
      const kunde = wert('kunde'), art = wert('artikel'), d = datum(wert('datum'));
      if (!d) { fehlerhaft(nr, kunde, `Ungültiges Datum „${wert('datum')}“ (erwartet TT.MM.JJJJ).`); continue; }
      if (!NUMMER.test(kunde)) { fehlerhaft(nr, kunde, `Ungültige Kundennummer „${kunde}“.`); continue; }
      const tagText = `${d[0]}-${String(d[1]).padStart(2, '0')}`;
      if (von === null || tagText < von) von = tagText;
      if (bis === null || tagText > bis) bis = tagText;
      if (!art) { ohneArtikel++; continue; }
      if (!ARTIKELNR.test(art)) { fehlerhaft(nr, kunde, `Ungültige Artikelnummer „${art}“.`); continue; }
      const menge = festkomma(wert('menge'), 3), betrag = festkomma(wert('betrag'), 2), kolli = festkomma(wert('kolli'), 0), ek = festkomma(wert('ek'), 4);
      if ([menge, betrag, kolli, ek].some((v) => Number.isNaN(v))) { fehlerhaft(nr, kunde, `Artikel ${art}: Menge, Kolli, Gesamtbetrag oder EKPreis ist keine Zahl.`); continue; }
      if (menge === null && betrag === null) { leer++; continue; }
      const ber = betrag !== null ? 1 : 0;
      const schl = `${d[0]}|${d[1]}|${kunde}|${art}|${ber}`;
      let s = summen.get(schl);
      if (!s) { s = [0, 0, 0, 0, 0, 0]; summen.set(schl, s); }   // Kolli, Menge, Umsatz, EK-Wert, Umsatz mit EK, Positionen
      s[0] += kolli || 0; s[1] += menge || 0; s[5]++;
      if (ber) {
        s[2] += betrag;
        if (ek !== null) { s[3] += Math.round(((menge || 0) * ek) / 100000); s[4] += betrag; }   // Menge (10^-3) × EK (10^-4) → Cent
      }
      zeilen++; kunden.add(kunde); artikel.add(art);
    }
    if (!kopf) throw new Error('Die Datei ist leer.');
    if (!zeilen) throw new Error('Die Datei enthält keine Umsatzpositionen (Zeilen mit Artikel).');
    if (fehler.length > Math.max(50, zeilen / 100)) throw new Error(`Die Datei passt nicht: ${fehler.length} fehlerhafte Zeilen (z. B. Zeile ${fehler[0].zeile}: ${fehler[0].text}).`);
    // je Monat sortierte Zeilen, Prüfsumme und Kennzahlen
    const monate = new Map();
    for (const [k, s] of summen) {
      const [m, tag, kunde, art, ber] = k.split('|');
      if (!monate.has(m)) monate.set(m, []);
      monate.get(m).push([Number(tag), kunde, art, s[0], s[1], s[2], s[3], s[4], s[5], Number(ber)]);
    }
    const daten = { version: 1, zeitraum: { von, bis }, monate: {}, kunden: [...kunden].sort(), artikel: [...artikel].sort(), datei: { zeilen, ohneArtikel, leer } };
    const teile = {};
    for (const m of [...monate.keys()].sort()) {
      const z = monate.get(m).sort((a, b) => a[0] - b[0] || vgl(a[1], b[1]) || vgl(a[2], b[2]) || a[9] - b[9]);
      const hash = await sha256(JSON.stringify(z));
      let pos1 = 0, umsatz = 0, menge = 0, posOhne = 0;
      for (const r of z) { if (r[9]) { pos1 += r[8]; umsatz += r[5]; menge += r[4]; } else posOhne += r[8]; }
      daten.monate[m] = { hash, zeilen: z.length, pos: pos1, umsatz, menge, posOhne };
      teile[m] = { monat: m, hash, zeilen: z };
    }
    const hinweise = mitEk ? [] : [{ stufe: 'warn', text: 'Die Datei hat keine Spalte EKPreis – Deckungsbeitrag, Spanne und DB-Anteil bleiben für diesen Zeitraum leer.' }];
    return { daten, teile, zeilen, fehler, hinweise };
  }

  W.importLeser = W.importLeser || {};
  W.importLeser.umsatzdaten = { lesen, nachher() {} };
  W.umsatzLeser = { felder, festkomma, datum };   // für Tests (Node/Browser)
})();
