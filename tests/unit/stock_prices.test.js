/* Unit-Test: Preisvergleich, Wochenpreise und Summenzeile der Bestandsliste (StockCore aus app/assets/stock-core.js). */
const assert = require('node:assert/strict');
require('../../app/assets/stock-core.js');
const S = globalThis.StockCore;
let n = 0;
const ok = (fn) => { fn(); n++; };
const value = (v, label) => ({status:'value', value:v, ...(label ? {label} : {})});
ok(() => assert.equal(S.priceComparison(value(12),value(10)).kind,'up'));
ok(() => assert.equal(S.priceComparison(value(8),value(10)).delta,-2));
ok(() => assert.equal(S.priceComparison(value(10),value(10)).kind,'same'));
ok(() => assert.equal(S.priceComparison(value(10),null).text,'keine Vergleichsdaten'));
ok(() => assert.equal(S.priceComparison(value(0),value(0)).kind,'same'));
ok(() => assert.equal(S.priceComparison(value(1.0001),value(1)).delta,.0001));
ok(() => assert.equal(S.priceComparison({status:'request'},value(10)).kind,'missing'));
ok(() => assert.equal(S.priceComparison(value(10,'Stück'),value(10)).text,'abweichende Preisbasis'));
ok(() => assert.equal(S.weekPriceMap({items:[{code:'001',price:value(10)},{code:'1',price:value(12)}]}).get('1').status,'ambiguous'));
ok(() => assert.equal(S.weekPriceMap({items:[{code:'001',price:value(10)},{code:'1',price:value(10)}]}).get('1').value,10));

/* ---------- Summenzeile: Zeilen wie admin.js stockZeile (kg, mhd, mhdKg, cls, lots, incoming) ---------- */
const zeilen = [
  { kg: 100, mhd: '2026-10-22', mhdKg: 40, cls: 'mhd-past', lots: [{ kg: 40, mhd: '2026-10-22', ek: 10 }, { kg: 60, mhd: '2026-11-20', ek: 12 }],
    incoming: [{ kg: 30, ek: 11 }] },
  { kg: 50, mhd: '2026-10-26', mhdKg: 20, cls: 'mhd-0-4', lots: [{ kg: 20, mhd: '2026-10-26', ek: 8.5 }, { kg: 30, mhd: '2026-10-30', ek: null }], incoming: [] },
  { kg: 25.4, mhd: '2026-10-28', mhdKg: 25.4, cls: 'mhd-5-7', lots: [{ kg: 25.4, mhd: '2026-10-28', ek: 4 }], incoming: [] },   // 5 Tage: nicht in „MHD bis 4 Tage“
  { kg: 10, mhd: null, mhdKg: null, cls: '', lots: [{ kg: 10, mhd: null, ek: 0 }], incoming: [] },                          // EK 0 = kein Preis
  { kg: null, mhd: null, mhdKg: null, cls: '', lots: [], incoming: [{ kg: 15 }, { kg: 0.004, ek: 2 }] },                      // nur Zugänge
];
const s = S.bestandSummen(zeilen);
ok(() => assert.deepEqual([s.eingelagert.kg, s.erfasst.kg, s.gesamt.kg, s.mhd.kg], [185.4, 45.004, 230.404, 60]));
ok(() => assert.deepEqual([s.eingelagert.ek, s.erfasst.ek, s.gesamt.ek, s.mhd.ek], [1391.6, 330.01, 1721.61, 570]));          // 400+720+170+101,6 · 330+0,008
ok(() => assert.deepEqual([s.eingelagert.ekKg, s.erfasst.ekKg, s.mhd.ekKg], [145.4, 30.004, 60]));
ok(() => assert.equal(s.mhd.anteil, 1));
ok(() => assert.ok(Math.abs(s.gesamt.anteil - 175.404 / 230.404) < 1e-12));
// Gramm statt Gleitkomma: 0,1 + 0,2 kg ergibt genau 0,3 kg
ok(() => assert.equal(S.bestandSummen([{ kg: 0.1, lots: [], incoming: [] }, { kg: 0.2, lots: [], incoming: [] }]).eingelagert.kg, 0.3));
// leere Auswahl: alles 0, kein Anteil
ok(() => { const z = S.bestandSummen([]); assert.deepEqual([z.gesamt.kg, z.gesamt.ek, z.gesamt.anteil], [0, 0, null]); });

// Ohne EK-Recht: nur kg, weder € noch „EK“ noch „Einkauf“
const ohne = S.summenZeileHTML(s, false);
ok(() => assert.ok(!/€|EK|Einkauf/.test(ohne), ohne));
ok(() => assert.match(ohne, /Gesamt verfügbar <b class="st-s-kg">230 kg<\/b><\/span>/));
ok(() => assert.match(ohne, /eingelagert <span class="st-s-kg">185 kg<\/span><\/span>/));
ok(() => assert.match(ohne, /erfasst <span class="st-s-kg">45 kg<\/span><\/span>/));
ok(() => assert.match(ohne, /MHD bis 4 Tage <span class="st-s-kg">60 kg<\/span><\/span>/));
// Mit EK-Recht: €-Werte, „€ EK“ vorn fett, Anteil im Hinweis, wenn nicht die ganze Menge einen EK-Preis hat
const mit = S.summenZeileHTML(s, true);
ok(() => assert.match(mit, /<b class="st-s-eur teil" title="Einkaufswert der Partien mit EK-Preis \(76 % der Menge\)">1\.722 € EK<\/b>/));
ok(() => assert.match(mit, /eingelagert <span class="st-s-kg">185 kg<\/span> · <span class="st-s-eur teil" title="[^"]*\(78 % der Menge\)">1\.392 €<\/span>/));
ok(() => assert.match(mit, /MHD bis 4 Tage <span class="st-s-kg">60 kg<\/span> · <span class="st-s-eur" title="Einkaufswert der Partien \(EK-Preis × Menge\)">570 €<\/span>/));
// ganz ohne EK-Preis: „– €“ statt 0 €; ohne Menge: 0 € ohne Hinweis auf einen Anteil
const leer = S.summenZeileHTML(S.bestandSummen([{ kg: 5, lots: [{ kg: 5 }], incoming: [] }]), true);
ok(() => assert.match(leer, /eingelagert <span class="st-s-kg">5 kg<\/span> · <span class="st-s-eur st-s-ohne"[^>]*>– €<\/span>/));
ok(() => assert.match(leer, /erfasst <span class="st-s-kg">0 kg<\/span> · <span class="st-s-eur" title="Einkaufswert der Partien \(EK-Preis × Menge\)">0 €<\/span>/));
// sehr kleiner Anteil: „unter 1 %“ statt „0 %“
ok(() => assert.match(S.summenZeileHTML(S.bestandSummen([{ kg: 1000, lots: [{ kg: 1, ek: 5 }, { kg: 999 }], incoming: [] }]), true), /unter 1 % der Menge/));
console.log(`${n}/${n} passed`);
