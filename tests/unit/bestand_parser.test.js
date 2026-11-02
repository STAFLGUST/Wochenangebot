// Unit-Test: Der Bestands-Parser der App (stock-core.js) liefert für die Test-Bestandsliste exakt
// dieselben Summen wie die unabhängige Referenzauswertung (tests/fixtures/bestand/master_stock.json).
// Regeln: BE-R001 (nur eingelagerte Partien zählen), BE-R002 (frühestes MHD und Menge daran).
// Dazu die CSV-Ausgabe der Bestandsliste (tests/fixtures/bestand/bestand.csv, synthetisch, Windows-1252, Semikolon).
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..', '..');
globalThis.window = globalThis;
globalThis.OfferCore = require(path.join(root, 'app/assets/offer-core.js'));
eval(fs.readFileSync(path.join(root, 'app/assets/stock-core.js'), 'utf8'));
const fix = path.join(root, 'tests/fixtures/bestand');
const master = JSON.parse(fs.readFileSync(path.join(fix, 'master_stock.json'), 'utf8'));
let failed = 0, n = 0;
const check = (name, ok, info = '') => { n++; console.log((ok ? 'PASS ' : 'FAIL ') + name + (info ? '  ' + info : '')); if (!ok) failed++; };
(async () => {
  const buf = fs.readFileSync(path.join(fix, 'bestand.xls'));
  const sheets = await StockCore.readStockWorkbook(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
  const r = StockCore.parseStockWorkbook(sheets, 'Bestand_16.10.26.XLS');
  const expected = sheets[0].grid.filter(row => row[9] === 'erfasst' && Number.isFinite(row[21]) && row[21] > 0 && /^[0-9]+$/.test(String(row[1])));
  check('erfasst: jede Lieferung separat, keine eingelagerten Partien', r.incoming.length === expected.length);
  check('erfasst: Artikel, kg und Ankunft aus J/M unverändert', r.incoming.every((d, i) => d.code === String(expected[i][1]) && Math.abs(d.kg - expected[i][21]) < .00001 && d.arrival === StockCore.toDate(expected[i][12], true)));
  check('erfasst: MHD, Kolli und EK-Preis wie bei den Partien übernommen', r.incoming.every((d, i) => d.kolli === expected[i][18] && (expected[i][22] == null ? d.ek === null : Math.abs(d.ek - expected[i][22]) < 1e-6)
    && d.mhd === (StockCore.toDate(expected[i][16], true) || null)) && r.incoming.some((d) => d.mhd) && r.incoming.some((d) => !d.mhd));
  check('mehrere Lieferungen pro Artikel bleiben einzeln', new Set(r.incoming.map(d => d.code)).size < r.incoming.length);
  const onlyIncoming = sheets.map(s => ({...s, grid: s.grid.filter(row => !row.includes('eingelagert'))}));
  const only = StockCore.parseStockWorkbook(onlyIncoming, 'nur-zugaenge.xls');
  check('Datei nur mit erfasst importierbar, Bestand leer', only.articles.length === 0 && only.incoming.length === expected.length);
  const by = new Map(r.articles.map((a) => [StockCore.normCode(a.code), a]));
  let bad = 0;
  for (const [code, name, kg, mhd, mhdKg] of master) {
    const a = by.get(StockCore.normCode(code));
    if (!a || a.name !== name || Math.abs(a.kg - kg) > 1e-6 || (a.mhd || null) !== (mhd || null) || Math.abs((a.mhdKg ?? 0) - (mhdKg ?? 0)) > 1e-6) {
      bad++; if (bad < 4) console.log('  Abweichung', code, name, kg, mhd, mhdKg, '→', a && [a.name, a.kg, a.mhd, a.mhdKg]);
    }
  }
  check('Bestandsdatum aus Dateiinhalt', r.date === '2026-10-16', r.date);
  check('alle Referenzartikel mit gleicher Menge und MHD', bad === 0, `${bad} Abweichungen bei ${master.length} Artikeln`);
  const extra = r.articles.filter((a) => a.kg > 0 && !master.some((m) => StockCore.normCode(m[0]) === StockCore.normCode(a.code)) && /^\d+$/.test(a.code));
  check('keine zusätzlichen Artikel mit Bestand', extra.length === 0, extra.slice(0, 3).map((a) => a.code).join(', '));
  // ---------- CSV-Ausgabe der Bestandsliste ----------
  const cb = fs.readFileSync(path.join(fix, 'bestand.csv'));
  const ab = cb.buffer.slice(cb.byteOffset, cb.byteOffset + cb.byteLength);
  const c = StockCore.parseStockWorkbook(await StockCore.readStockWorkbook(ab, 'Bestand.csv'), 'Bestand.csv');
  check('CSV: Spalten nach Überschrift (Art. Nr., Bezeichnung, Marke, Status, Ankunft, Partie, MHD, Kolli, netto, EK Preis)',
    JSON.stringify(c.columns) === JSON.stringify({ status: 6, code: 0, name: 1, arrival: 7, lot: 8, mhd: 9, kolli: 10, kg: 11, ek: 12, marke: 3 }), JSON.stringify(c.columns));
  check('CSV: eingelagert, erfasst, anderer Status, übersprungene Zeilen (Etiketten, ohne netto)',
    JSON.stringify(c.stats) === JSON.stringify({ rows: 10, stored: 5, expected: 2, other: { verkauft: 1 }, skipped: 2, noMhd: 1 }), JSON.stringify(c.stats));
  const ca = new Map(c.articles.map((a) => [a.code, a]));
  check('CSV: Artikel mit Menge, frühestem MHD und Menge daran (Tausenderpunkt, Dezimalkomma)', c.articles.length === 4
    && ca.get('10601').kg === 1782.5 && ca.get('10601').mhd === '2026-11-18' && ca.get('10601').mhdKg === 1541
    && ca.get('60100').kg === 800.25 && ca.get('60100').mhd === '2027-09-01' && ca.get('10823').kg === 41.6, JSON.stringify(c.articles.map((a) => [a.code, a.kg, a.mhd, a.mhdKg])));
  check('CSV: führende Nullen der Artikelnummer bleiben, Partie ohne MHD zählt zur Menge', ca.has('00001') && ca.get('00001').kg === 27.95 && ca.get('00001').mhd === null);
  const lot = ca.get('10601').lots[0];
  check('CSV: Partie mit Marke, Ankunft, Kolli, EK-Preis; Anführungszeichen und Umlaute in der Bezeichnung',
    lot.lot === '900002' && lot.marke === 'Weide Nord' && lot.arrival === '2026-10-12' && lot.kolli === 29 && lot.ek === 10.75
    && ca.get('10601').name === 'Testhüfte "Premium", frisch' && ca.get('00001').lots[0].marke === 'Hof Süd', JSON.stringify(lot));
  check('CSV: erwartete Zugänge (erfasst) einzeln, auch ohne Ankunft', c.incoming.length === 2
    && c.incoming[0].code === '10823' && c.incoming[0].kg === 120 && c.incoming[0].arrival === '2026-11-20' && c.incoming[1].arrival === null && c.incoming[1].kg === 500,
    JSON.stringify(c.incoming.map((x) => [x.code, x.kg, x.arrival])));
  check('CSV: kein Datum in der Datei → leer (wird im Dialog gesetzt)', c.date === null);
  const ohneName = StockCore.parseStockWorkbook(await StockCore.readStockWorkbook(ab, 'export'), 'export');
  check('CSV auch ohne Endung erkannt (Text mit Semikolon)', ohneName.articles.length === 4);
  const utf8 = Buffer.from(cb.toString('latin1'), 'utf8');
  const u = StockCore.parseStockWorkbook(await StockCore.readStockWorkbook(utf8.buffer.slice(utf8.byteOffset, utf8.byteOffset + utf8.byteLength), 'b.csv'), 'b.csv');
  check('CSV in UTF-8 gespeichert: gleiche Werte, Umlaute richtig', u.articles.length === 4 && u.articles.find((a) => a.code === '10601').name === 'Testhüfte "Premium", frisch');
  let fehler = '';
  try { await StockCore.readStockWorkbook(new TextEncoder().encode('kein Bestand\nnur Text ohne Trennzeichen').buffer, 'x.txt'); } catch (e) { fehler = e.message; }
  check('weder CSV noch Excel: verständlicher Fehler', /weder eine CSV-Datei noch eine Excel-Datei/.test(fehler), fehler);
  console.log(`${n - failed}/${n} passed`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
