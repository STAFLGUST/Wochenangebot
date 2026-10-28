#!/usr/bin/env node
/* Kartenstil der Detailkarte (app/assets/karte/stil-hell.json, stil-dunkel.json) aus den Protomaps-Basemaps erzeugen.
   Grundlage sind die Ebenen von @protomaps/basemaps (BSD-3) mit deutschen Ortsnamen; die Farben sind an das
   STAFL-Design angepasst (warmes Grau, gedecktes Blau, dezente Gebäude). Ergebnis wird eingecheckt.

   Aufruf (einmalig bzw. nach einer neuen Basemaps-Version):
     npm pack @protomaps/basemaps@5.7.2 && mkdir basemaps && tar xzf protomaps-basemaps-5.7.2.tgz -C basemaps
     node werkzeuge/karte_stil.mjs basemaps/package
*/
import { createRequire } from 'node:module';
import { writeFileSync } from 'node:fs';
import path from 'node:path';

const paket = process.argv[2];
if (!paket) { console.error('Aufruf: node werkzeuge/karte_stil.mjs <Pfad zu @protomaps/basemaps/package>'); process.exit(1); }
const require = createRequire(import.meta.url);
const b = require(path.resolve(paket, 'dist/cjs/index.cjs'));
const version = require(path.resolve(paket, 'package.json')).version;

const HELL = {
  background: '#ebe7e1', earth: '#f3f0eb', water: '#c7d7e2',
  park_a: '#dfe7d4', park_b: '#d7e1cb', wood_a: '#d9e3ce', wood_b: '#d0dbc4', scrub_a: '#e0e6d6', scrub_b: '#d8dfcd',
  sand: '#ede6d6', beach: '#efe8d6', hospital: '#f2e5e3', school: '#eee8de', industrial: '#e9e5df', pedestrian: '#ece8e2',
  aerodrome: '#e7e3dd', runway: '#dcd6ce', zoo: '#dfe7d4', military: '#eae5de',
  buildings: '#e1dad1',
  highway: '#fbf5ec', highway_casing_early: '#d8cbbb', highway_casing_late: '#d8cbbb',
  major: '#ffffff', major_casing_early: '#ddd5ca', major_casing_late: '#ddd5ca',
  minor_a: '#ffffff', minor_b: '#ffffff', minor_service: '#fbfaf8', minor_casing: '#e3dcd3', minor_service_casing: '#e6e0d8',
  link: '#ffffff', link_casing: '#ddd5ca', other: '#eeeae4', railway: '#c8bfb5', boundaries: '#b3a9a0', pier: '#e9e5df',
  city_label: '#36312d', city_label_halo: '#f3f0eb', subplace_label: '#746c66', subplace_label_halo: '#f3f0eb',
  state_label: '#9b928b', state_label_halo: '#f3f0eb', country_label: '#7d7570',
  roads_label_minor: '#7a726a', roads_label_minor_halo: '#ffffff', roads_label_major: '#5f5852', roads_label_major_halo: '#ffffff',
  ocean_label: '#6f8798', address_label: '#8c847c', address_label_halo: '#f3f0eb',
  landcover: { grassland: '#e7e8dc', barren: '#efebe2', urban_area: '#e9e5df', farmland: '#ebeadf', glacier: '#ffffff', scrub: '#e4e7da', forest: '#dbe3d2' },
};
const DUNKEL = {
  background: '#141213', earth: '#1c191a', water: '#1d2a33',
  park_a: '#1f2720', park_b: '#20291f', wood_a: '#1e261f', wood_b: '#1f281f', scrub_a: '#1f251f', scrub_b: '#20261f',
  sand: '#262320', beach: '#272420', hospital: '#2a2122', school: '#24201f', industrial: '#211e1e', pedestrian: '#221f20',
  aerodrome: '#221f1f', runway: '#2d2929', zoo: '#1f2720', military: '#231f1f',
  buildings: '#2a2627',
  highway: '#4a4041', highway_casing_early: '#141213', highway_casing_late: '#141213',
  major: '#3b3536', major_casing_early: '#141213', major_casing_late: '#141213',
  minor_a: '#302b2c', minor_b: '#302b2c', minor_service: '#2a2627', minor_casing: '#141213', minor_service_casing: '#141213',
  link: '#3b3536', link_casing: '#141213', other: '#262223', railway: '#3a3536', boundaries: '#5a5253', pier: '#221f20',
  city_label: '#e6ddd4', city_label_halo: '#141213', subplace_label: '#a39a92', subplace_label_halo: '#141213',
  state_label: '#7d756e', state_label_halo: '#141213', country_label: '#8c847c',
  roads_label_minor: '#a0978f', roads_label_minor_halo: '#141213', roads_label_major: '#c2b9b0', roads_label_major_halo: '#141213',
  ocean_label: '#6f8798', address_label: '#8c847c', address_label_halo: '#141213',
  landcover: { grassland: '#1e221d', barren: '#221f1e', urban_area: '#1e1b1c', farmland: '#1f221e', glacier: '#2b2b2b', scrub: '#20231e', forest: '#1c241f' },
};

function stil(name, basis, farben) {
  const flavor = { ...b.namedFlavor(basis) };
  for (const [k, v] of Object.entries(farben)) if (k in flavor) flavor[k] = v;
  const ebenen = b.layers('protomaps', flavor, { lang: 'de' });
  // Geschäftskarte: Orte von Interesse (Restaurants, Läden …) eine Zoomstufe später als im Original, damit die
  // Kundenpunkte im Vordergrund bleiben
  const poi = ebenen.find((l) => l.id === 'pois');
  if (poi) poi.filter = JSON.parse(JSON.stringify(poi.filter).replace('["+",["get","min_zoom"],0]', '["+",["get","min_zoom"],1]'));
  return { erzeugt: `werkzeuge/karte_stil.mjs aus @protomaps/basemaps ${version}`, sprite: basis, background: flavor.background, layers: ebenen };
}
const ziel = path.resolve(path.dirname(new URL(import.meta.url).pathname), '..', 'app', 'assets', 'karte');
writeFileSync(path.join(ziel, 'stil-hell.json'), JSON.stringify(stil('hell', 'light', HELL)));
writeFileSync(path.join(ziel, 'stil-dunkel.json'), JSON.stringify(stil('dunkel', 'dark', DUNKEL)));
console.error('geschrieben: app/assets/karte/stil-hell.json, stil-dunkel.json');
