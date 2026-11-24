/* STAFL-Plattform · Container-Import · EUDR – Geodaten-Katalog: die offene Metadatenbank GEOS-EUDR des Thünen-Instituts
   (MIT-Lizenz, https://github.com/GEOS-EUDR-RepoHub/Metadatabase-Geodata-EUDR) beschreibt veröffentlichte Geodatensätze zu
   Wald: Hersteller, Walddefinition, ob sie zur Walddefinition der EUDR passt, Auflösung, Jahre, Validierung, Genauigkeit,
   bekannte Grenzen. Ansicht „Geodaten-Katalog“ (Liste mit Suche, je Eintrag aufklappbar) und kleine Verweise wie „FNF01“
   an Karte, Bildauswertung und Whisp-Ergebnis, die den Eintrag in einem Fenster öffnen – so ist bei jeder Gegenprüfung
   sichtbar, auf welcher Datengrundlage sie steht und wie genau diese ist.
   Daten: containerimport_eudr_geodaten (nur lesen, einmal je Seite geladen; Datei schreibt werkzeuge/eudr_geodatenkatalog.py).
   „NR“ = nicht berichtet, „NA“ = nicht zutreffend. Alles sind Fremdtexte: nur maskiert, Verweise nur mit http(s).
   Hilfen und Zustand über die Brücke window.STAFL_CI (containerimport.js lädt zuerst).
   API: window.EUDR_GEODATEN.verweis(id) → HTML eines Knopfs, der den Eintrag öffnet
        window.EUDR_GEODATEN.beleg(ids) → Promise<Text für die Dokumentation einer Prüfung: Katalog, Thema, Version, IDs> */
(() => {
  'use strict';
  const C = window.STAFL_CI, F = window.STAFL_FORMAT;
  const { S, $, esc, SU, kopf, marke, api, oeffnen, suchfeld } = C;
  S.suche.geodaten = '';
  const KONFORM = { ja: ['ja', 'ok'], teilweise: ['teilweise', 'warn'], nein: ['nein', 'rot'], nein_unklar: ['nein/unklar', 'warn'], unklar: ['unklar', 'warn'],
    nicht_berichtet: ['nicht berichtet', ''], nicht_zutreffend: ['nicht zutreffend', ''] };
  const offen = new Set();   // aufgeklappte Einträge der Liste, damit Neuzeichnen (Suche, Abgleich) sie nicht zuklappt – Stand aus dem DOM vor jedem Neuzeichnen
  let daten = null, laden = null;
  /* Katalog einmal je Seite; nach einem Fehler beim nächsten Aufruf neu versuchen → Katalog | null */
  const katalog = () => (laden = laden || api('containerimport_eudr_geodaten').then((r) => {
    if (r.status === 200 && r.data.ok) return (daten = r.data);
    laden = null;
    return null;
  }));
  const eintrag = (id) => daten && daten.eintraege.find((e) => e.id === id);
  const thema = (e) => daten.themen.find((t) => t.id === e.thema) || {};

  /* Zellwert als Text: NR/NA ausgeschrieben, leer als Strich */
  const wert = (v) => (v === null || v === undefined ? '—' : v === 'NR' ? 'nicht berichtet' : v === 'NA' ? 'nicht zutreffend' : v);
  const zeile = (titel, v) => (v === null || v === undefined ? '' : `<dt>${titel}</dt><dd>${esc(wert(v))}</dd>`);
  const jahre = (e) => (e.vonJahr === e.bisJahr ? wert(e.vonJahr) : `${wert(e.vonJahr)} – ${wert(e.bisJahr)}`);
  const aufloesung = (e) => (e.aufloesungM === null ? '—' : /^~?\d+(\.\d+)?$/.test(e.aufloesungM) ? `${e.aufloesungM} m` : wert(e.aufloesungM));
  const konform = (e) => marke(...(KONFORM[e.eudrKonform] || [e.eudrKonform, '']));
  function links(liste) {
    return liste.map((l) => {
      const ziel = /^https?:\/\//i.test(l.url) ? l.url : '';
      const text = l.text || ziel.replace(/^https?:\/\/(www\.)?/i, '').split(/[/?#]/)[0] || l.url;
      return ziel ? `<a href="${esc(ziel)}" target="_blank" rel="noopener noreferrer">${esc(text)}</a>` : esc(text);
    }).join(' · ');
  }
  /* Kurzangaben (Liste und Fenster) und alles Weitere (aufgeklappt) */
  const kurz = (e) => `<span class="ci-gd-kurz"><span>Auflösung ${esc(aufloesung(e))}</span><span>Jahre ${esc(jahre(e))}</span><span>EUDR-konform ${konform(e)}</span>
    <span class="ci-gd-oa">Gesamtgenauigkeit ${esc(wert(e.genauigkeit.oa))}</span></span>`;
  const verweisZeile = (titel, liste) => (liste.length ? `<dt>${titel}</dt><dd>${links(liste)}</dd>` : '');
  const mehr = (e) => `<dl class="ci-gd-dl">
      ${zeile('Hinweis des Katalogs', e.hinweis)}${zeile('Walddefinition', e.walddefinition)}${zeile('Klassen', e.klassen)}${zeile('Ausdehnung', e.ausdehnung)}
      ${zeile('Zeitliche Auflösung', e.zeitlich)}${zeile('Sensor, Grunddaten', e.sensor)}${zeile('Methode', [e.methode, e.kategorie].filter((x) => x && x !== 'NR').join(' · ') || e.methode)}
      ${zeile('Validierung', e.validierung.ansatz)}${zeile('Referenz der Validierung', e.validierung.referenz)}${zeile('Stichproben', e.validierung.stichproben)}
      ${zeile('Gesamtgenauigkeit (OA)', e.genauigkeit.oa)}${zeile('Hersteller- und Nutzergenauigkeit', e.genauigkeit.paUa)}${zeile('Weitere Maße', e.genauigkeit.weitere)}
      ${zeile('Mehr zur Genauigkeit', e.genauigkeit.zusatz)}${zeile('Bekannte Grenzen', e.grenzen)}${zeile('Veröffentlichung', e.zitat)}
      ${verweisZeile('Bericht', e.links.veroeffentlichung)}${verweisZeile('Google Earth Engine', e.links.gee)}${verweisZeile('Weitere Quellen', e.links.andere)}</dl>`;
  /* Quelle, Fassung und Zitiervorschlag des Katalogs (Lizenz MIT verlangt die Nennung der Urheber) */
  const quelle = () => `<p><strong>Quelle:</strong> <a href="${esc(daten.quelle.url)}" target="_blank" rel="noopener noreferrer">GEOS-EUDR Metadatenbank</a> · ${esc(daten.quelle.urheber)} · Lizenz ${esc(daten.quelle.lizenz)}</p>
    ${daten.themen.map((t) => `<p>${esc(t.name)}: Fassung v${esc(t.version)}${t.quelleCommit ? ` (Commit ${esc(t.quelleCommit)})` : ''}, übernommen am ${esc(F.datum(t.abgerufen))} · ${t.eintraege} Einträge</p>
      <p class="ci-leise">Zitiervorschlag: ${esc(t.zitiervorschlag)}</p>`).join('')}
    <p class="ci-leise">Beschreibt die Datensätze, nicht einzelne Flächen. „Nicht berichtet“: die Hersteller nennen es nicht.</p>`;

  function sicht() {
    if (!daten) {
      $('#ci-inhalt').innerHTML = '<div class="r-karte"><p class="ci-leer" role="status">Geodaten-Katalog wird geladen …</p></div>';
      katalog().then((d) => {
        if (S.reiter !== 'eudr' || S.sicht !== 'geodaten') return;
        if (d) sicht(); else $('#ci-inhalt').innerHTML = '<div class="r-karte"><p class="ci-leer">Der Geodaten-Katalog ist gerade nicht erreichbar. Bitte später erneut versuchen.</p></div>';
      });
      return;
    }
    // Auf- und Zuklappen der gezeigten Einträge übernehmen, bevor sie ersetzt werden. Nicht über das Ereignis „toggle“: es kommt
    // später als der Klick und für ein inzwischen entferntes Element unter Umständen gar nicht (CI, Chromium 141: Eintrag zu).
    for (const d of document.querySelectorAll('#ci-geodaten details[data-gd]')) offen[d.open ? 'add' : 'delete'](d.dataset.gd);
    const liste = daten.eintraege.filter((e) => SU.findet(S.suche.geodaten, e.id, e.name, e.hinweis, e.hersteller, e.sensor, e.methode, e.kategorie, e.walddefinition, e.klassen, e.zitat, KONFORM[e.eudrKonform] && KONFORM[e.eudrKonform][0]));
    $('#ci-inhalt').innerHTML = `<div class="ci-suchzeile">${suchfeld('Name, Kennung (FNF01), Hersteller, Sensor, Methode', 'Geodaten-Katalog')}</div>
      <div class="r-karte ci-hilfe ci-gd-quelle">${quelle()}</div>
      ${liste.length ? `<div class="ci-gd-liste" id="ci-geodaten">${liste.map((e) => `<details class="r-karte ci-gd" data-gd="${esc(e.id)}"${offen.has(e.id) ? ' open' : ''}>
        <summary><span class="ci-gd-titel"><b class="ci-zahlen">${esc(e.id)}</b> <strong>${esc(e.name)}</strong></span><span class="ci-unter">${esc(wert(e.hersteller))}</span>${kurz(e)}</summary>${mehr(e)}</details>`).join('')}</div>`
        : '<div class="r-karte"><p class="ci-leer">Kein Eintrag passt zur Suche.</p></div>'}`;
  }

  /* Fenster mit einem Eintrag (aus einem Verweis, auch über dem Fenster „Farmer“) */
  async function fenster(id) {
    const d = await katalog(), e = d && eintrag(id), form = $('#geodaten-inhalt');
    form.dataset.id = id;
    form.innerHTML = (e ? kopf('geodaten-titel', `${e.id} · ${e.name}`, esc(wert(e.hersteller))) + `<div class="dlg-body">${kurz(e)}${mehr(e)}
        <p class="ci-klein ci-leise">Geodaten-Katalog GEOS-EUDR (Thünen-Institut, Lizenz MIT), ${esc(thema(e).name)} v${esc(thema(e).version)}. Der Eintrag beschreibt das Produkt; ein Dienst kann eine neuere Fassung zeigen.</p></div>`
      : kopf('geodaten-titel', 'Geodaten-Katalog') + `<div class="dlg-body"><p>${d ? `Kein Eintrag ${esc(id)} im Katalog.` : 'Der Geodaten-Katalog ist gerade nicht erreichbar. Bitte später erneut versuchen.'}</p></div>`)
      + '<div class="dlg-foot"><span class="spacer"></span><button class="ci-knopf" type="button" data-zu>Schließen</button></div>';
    oeffnen($('#dlg-geodaten'));
  }

  const verweis = (id) => `<button class="ci-gd-verweis" type="button" data-geodaten="${esc(id)}" title="Eintrag ${esc(id)} im Geodaten-Katalog GEOS-EUDR: Auflösung, Genauigkeit, Grenzen">${esc(id)}</button>`;
  /* „GEOS-EUDR-Katalog (Thünen-Institut) ForestCover_TreeExtent v1.0: FNF01, FNF17“ – je Thema mit seiner Fassung */
  async function beleg(ids) {
    await katalog();
    const gruppen = new Map();
    for (const id of ids) {
      const e = eintrag(id), k = e ? `${e.thema} v${thema(e).version}` : 'Fassung nicht geladen';
      gruppen.set(k, [...(gruppen.get(k) || []), id]);
    }
    return 'GEOS-EUDR-Katalog (Thünen-Institut) ' + [...gruppen].map(([k, l]) => `${k}: ${l.join(', ')}`).join('; ');
  }

  C.sichten.geodaten = sicht;
  document.addEventListener('click', (e) => {
    const v = e.target.closest('[data-geodaten]');
    if (v) fenster(v.dataset.geodaten);
  });
  $('#geodaten-inhalt').addEventListener('submit', (e) => e.preventDefault());

  window.EUDR_GEODATEN = { verweis, beleg };
})();
