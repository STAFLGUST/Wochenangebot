// Unit-Test: Drei-Wege-Abgleich beim gemeinsamen Bearbeiten des Entwurfs (OfferCore.mergeModels).
const path = require('path');
const C = require(path.resolve(__dirname, '..', '..', 'app/assets/offer-core.js'));
let failed = 0, total = 0;
const check = (name, ok, info = '') => { total++; console.log((ok ? 'PASS ' : 'FAIL ') + name + (info ? '  ' + info : '')); if (!ok) failed++; };
const J = (v) => JSON.parse(JSON.stringify(v));
const P = (v) => ({ status: 'value', value: v });
const base = {
  meta: { week: 42, year: 2026, notice: 'Freibleibendes Angebot' },
  sections: ['Rind'],
  groups: [{ id: 'g1', name: 'Rind frisch', section: 'Rind' }, { id: 'g2', name: 'Schwein', section: '' }],
  items: [
    { id: 'a', code: '100', name: 'Hüfte', groupId: 'g1', price: P(10), altPrices: [] },
    { id: 'b', code: '200', name: 'Rücken', groupId: 'g1', price: P(20), altPrices: [], variants: { bela: { status: 'value', value: 19 } } },
    { id: 'c', code: '300', name: 'Nacken', groupId: 'g2', price: P(5), altPrices: [] },
  ],
};
const item = (m, id) => m.items.find((x) => x.id === id);

{ // verschiedene Artikel geändert → beide Änderungen bleiben
  const mine = J(base), theirs = J(base);
  item(mine, 'a').price = P(11);
  item(theirs, 'b').price = P(21);
  const r = C.mergeModels(base, mine, theirs);
  check('eigener Preis bleibt', item(r.model, 'a').price.value === 11);
  check('fremder Preis übernommen', item(r.model, 'b').price.value === 21);
  check('keine Konflikte', r.conflicts.length === 0, JSON.stringify(r.conflicts));
  check('geänderte Zeile gemeldet', r.remoteItems.length === 1 && r.remoteItems[0] === 'b', r.remoteItems.join());
}
{ // gleicher Artikel, verschiedene Felder
  const mine = J(base), theirs = J(base);
  item(mine, 'a').price = P(12);
  item(theirs, 'a').name = 'Hüfte ohne Deckel';
  const r = C.mergeModels(base, mine, theirs);
  check('Feldweise: Preis und Bezeichnung', item(r.model, 'a').price.value === 12 && item(r.model, 'a').name === 'Hüfte ohne Deckel');
}
{ // gleiches Feld → eigene Eingabe gilt, Konflikt gemeldet
  const mine = J(base), theirs = J(base);
  item(mine, 'a').price = P(13);
  item(theirs, 'a').price = P(14);
  const r = C.mergeModels(base, mine, theirs);
  check('Konflikt: eigene Eingabe gilt', item(r.model, 'a').price.value === 13);
  check('Konflikt gemeldet', r.conflicts.length === 1 && r.conflicts[0].field === 'price');
}
{ // Kundenangebotspreise je Angebot
  const mine = J(base), theirs = J(base);
  item(mine, 'b').variants.bela = { status: 'value', value: 18 };
  item(theirs, 'b').variants.mueller = { status: 'request' };
  const r = C.mergeModels(base, mine, theirs);
  const v = item(r.model, 'b').variants;
  check('Kundenpreise beider Angebote', v.bela.value === 18 && v.mueller.status === 'request', JSON.stringify(v));
  const t2 = J(base); delete item(t2, 'b').variants;
  const r2 = C.mergeModels(base, J(base), t2);
  check('fremd entfernter Kundenpreis entfernt', !item(r2.model, 'b').variants);
}
{ // neue Artikel von beiden, Reihenfolge
  const mine = J(base), theirs = J(base);
  mine.items.splice(1, 0, { id: 'm1', code: '110', name: 'Mein Neuer', groupId: 'g1', price: P(1), altPrices: [] });
  theirs.items.push({ id: 't1', code: '310', name: 'Ihr Neuer', groupId: 'g2', price: P(2), altPrices: [] });
  const r = C.mergeModels(base, mine, theirs);
  check('beide neuen Artikel vorhanden', r.model.items.map((x) => x.id).join() === 'a,m1,b,c,t1', r.model.items.map((x) => x.id).join());
}
{ // Löschen bleibt gelöscht, auch wenn der andere geändert hat
  const mine = J(base), theirs = J(base);
  mine.items = mine.items.filter((x) => x.id !== 'c');
  item(theirs, 'c').price = P(6);
  item(theirs, 'a').price = P(9);
  const r = C.mergeModels(base, mine, theirs);
  check('eigene Löschung bleibt', !item(r.model, 'c'));
  check('fremde Änderung übernommen', item(r.model, 'a').price.value === 9);
  check('Löschung trotz Änderung gemeldet', r.conflicts.some((c) => c.field === 'deleted' && c.id === 'c'));
  const t3 = J(base); t3.items = t3.items.filter((x) => x.id !== 'a');
  const r3 = C.mergeModels(base, J(base), t3);
  check('fremde Löschung übernommen', !item(r3.model, 'a') && r3.removed.includes('a'));
}
{ // Kopfdaten
  const mine = J(base), theirs = J(base);
  mine.meta.notice = 'Neu';
  theirs.meta.week = 43;
  const r = C.mergeModels(base, mine, theirs);
  check('Kopfdaten feldweise', r.model.meta.notice === 'Neu' && r.model.meta.week === 43);
}
{ // Gruppe gelöscht, Artikel vom anderen hineingelegt → Gruppe bleibt
  const mine = J(base), theirs = J(base);
  mine.groups = mine.groups.filter((g) => g.id !== 'g2'); mine.items = mine.items.filter((x) => x.groupId !== 'g2');
  theirs.items.push({ id: 't2', code: '320', name: 'Bauch', groupId: 'g2', price: P(4), altPrices: [] });
  const r = C.mergeModels(base, mine, theirs);
  check('Gruppe bleibt für neuen Artikel', r.model.groups.some((g) => g.id === 'g2') && !!item(r.model, 't2'));
}
{ // ohne gemeinsame Basis (erster Entwurf) und unverändert
  const r = C.mergeModels(J(base), J(base), J(base));
  check('nichts geändert → changed=false', r.changed === false && r.conflicts.length === 0);
  const theirs = J(base); theirs.publishedAt = 'x';
  const r2 = C.mergeModels(null, J(base), J(base));
  check('fehlende Basis: gleiche Stände bleiben', r2.model.items.length === 3 && r2.conflicts.length === 0);
}
console.log(`${total - failed}/${total} passed`);
process.exit(failed ? 1 : 0);
