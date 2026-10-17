// Unit-Test: Der Bestands-Parser der App (stock-core.js) liefert für die Test-Bestandsliste exakt
// dieselben Summen wie die unabhängige Referenzauswertung (tests/fixtures/bestand/master_stock.json).
// Regeln: BE-R001 (nur eingelagerte Partien zählen), BE-R002 (frühestes MHD und Menge daran).
const fs = require('fs');
const path = require('path');
const root = path.resolve(__dirname, '..', '..');
globalThis.window = globalThis;
globalThis.OfferCore = require(path.join(root, 'app/assets/offer-core.js'));
eval(fs.readFileSync(path.join(root, 'app/assets/stock-core.js'), 'utf8'));
const fix = path.join(root, 'tests/fixtures/bestand');
const master = JSON.parse(fs.readFileSync(path.join(fix, 'master_stock.json'), 'utf8'));
let failed = 0;
const check = (name, ok, info = '') => { console.log((ok ? 'PASS ' : 'FAIL ') + name + (info ? '  ' + info : '')); if (!ok) failed++; };
(async () => {
  const buf = fs.readFileSync(path.join(fix, 'bestand.xls'));
  const sheets = await StockCore.readStockWorkbook(buf.buffer.slice(buf.byteOffset, buf.byteOffset + buf.byteLength));
  const r = StockCore.parseStockWorkbook(sheets, 'Bestand_16.10.26.XLS');
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
  console.log(`${3 - failed}/3 passed`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
