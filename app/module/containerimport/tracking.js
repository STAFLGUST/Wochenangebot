/* STAFL-Plattform · Modul Container-Import – Reiter „Tracking“: wo ist der Container, wann kommt er an (Auftrag des
   Inhabers 19.11.2026). Liste der Container mit Schiff, Reederei, Route, geplanter Abfahrt und Ankunft („in 12 Tagen“,
   „überfällig“), Suche, Fenster zum Pflegen und ein Verweis zur Sendungsverfolgung der Reederei.
   Erste Stufe ohne fremde Dienste: alle Angaben werden von Hand gepflegt; die Seite fragt nirgends ab. Der Verweis öffnet
   die Seite der Reederei in einem neuen Fenster und legt die Containernummer in die Zwischenablage.
   Hilfen und Zustand kommen über die Brücke window.STAFL_CI (containerimport.js lädt zuerst); die Datei trägt ihren Reiter
   dort ein und hängt ihre eigenen Ereignisse an. Regeln (Datum, Auswahl der Reederei) prüft der Server:
   app/api/module/containerimport/tracking.php. Daten: containerimport_tracking_save (die Antwort bringt den neuen Stand
   mit). Fremde Texte nur maskiert. */
(() => {
  'use strict';
  const C = window.STAFL_CI;
  const { S, $, esc, SU, feld, kopf, werte, marke, tag, api, uebernehmen, toast, oeffnen, sendung, HINWEIS_NUMMER } = C;
  const T = { suche: '', angekommene: false };
  const HAEFEN = ['Hamburg', 'Rotterdam', 'Bremerhaven', 'Antwerpen', 'Wilhelmshaven'];
  const nummer = (text) => text.replace(/[\s./-]+/g, '').toUpperCase();
  /* Reederei, die das Kürzel der Containernummer nahelegt (nur ein Vorschlag: gemietete Container tragen fremde Kürzel) */
  const vorschlag = (container) => Object.keys(S.d.reedereien).find((k) => S.d.reedereien[k].kuerzel.includes(nummer(container).slice(0, 4))) || '';
  const verweis = (s) => {
    const r = S.d.reedereien[s.reederei];
    return r && r.url && s.container ? r.url.replace('{nr}', encodeURIComponent(nummer(s.container))) : '';
  };
  /* Tage von heute (Datum des Servers) bis zu einem Datum JJJJ-MM-TT */
  const tageBis = (datum) => Math.round((Date.parse(datum + 'T00:00:00Z') - Date.parse(S.d.heute + 'T00:00:00Z')) / 86400000);
  /* Ankunft in Worten: [Text, Farbe der Marke] */
  function ankunft(s) {
    if (s.stand === 'angekommen') return ['angekommen', 'ok'];
    if (!s.eta) return ['Ankunft offen', ''];
    const n = tageBis(s.eta);
    if (n < 0) return [n === -1 ? 'seit gestern überfällig' : `seit ${-n} Tagen überfällig`, 'rot'];
    return [n === 0 ? 'heute' : n === 1 ? 'morgen' : `in ${n} Tagen`, n <= 3 ? 'warn' : ''];
  }

  function zeichnen() {
    const alle = S.d.sendungen.filter((s) => s.aktiv), unterwegs = alle.filter((s) => s.stand !== 'angekommen');
    const liste = (T.angekommene ? alle : unterwegs)
      .filter((s) => SU.findet(T.suche, s.partie, s.akte, s.container, s.nummer, s.schiff, s.bl, s.abgangshafen, s.zielhafen, s.lieferant, s.ware, (S.d.reedereien[s.reederei] || {}).name))
      .sort((a, b) => (a.stand === 'angekommen') - (b.stand === 'angekommen') || (a.eta || '9999').localeCompare(b.eta || '9999') || b.erstellt.t.localeCompare(a.erstellt.t));
    const zeiten = unterwegs.map((s) => s.eta).filter(Boolean).sort(), ueberfaellig = zeiten.filter((t) => t < S.d.heute).length, naechste = zeiten[ueberfaellig];
    const zeile = (s) => {
      const [text, farbe] = ankunft(s), r = S.d.reedereien[s.reederei];
      return `<tr data-tracking="${esc(s.id)}" tabindex="0">
        <td><span class="ci-name">${esc(s.name)}</span><span class="ci-unter">${s.container ? `<span class="ci-zahlen">${esc(s.container)}</span>` : 'Containernummer fehlt'}</span></td>
        <td data-t="Schiff"><span>${esc(s.schiff || '—')}</span><span class="ci-unter">${esc(r ? r.name : '')}</span></td>
        <td data-t="Route"><span>${esc(s.abgangshafen || '—')} → ${esc(s.zielhafen || '—')}</span><span class="ci-unter">${esc([s.lieferant, s.ware].filter(Boolean).join(' · '))}</span></td>
        <td data-t="Abfahrt" class="ci-fest">${tag(s.etd)}</td>
        <td data-t="Ankunft" class="ci-fest"><span>${tag(s.eta)}</span><span class="ci-unter">${marke(text, farbe)}</span></td>
        <td data-t="Stand">${marke(S.d.staende[s.stand], s.stand === 'angekommen' ? 'ok' : '')}</td></tr>`;
    };
    $('#ci-bereich-tracking').innerHTML = `<p class="ci-t-lage">${unterwegs.length === 1 ? '1 Container ist' : `${unterwegs.length} Container sind`} noch nicht angekommen${ueberfaellig ? ` · ${ueberfaellig} überfällig` : ''}${naechste ? ` · nächste Ankunft ${tag(naechste)}` : ''}.
        <span class="ci-leise">Alle Angaben werden von Hand gepflegt – die Seite fragt weder Reederei noch Hafen ab.</span></p>
      <div class="ci-suchzeile"><input type="search" id="ci-t-suche" value="${esc(T.suche)}" placeholder="Partie, Containernummer, Schiff, Hafen, Lieferant" aria-label="Tracking durchsuchen">
        <label class="ci-check"><input type="checkbox" id="ci-t-angekommene"${T.angekommene ? ' checked' : ''}>Angekommene anzeigen</label></div>`
      + (liste.length
        ? `<div class="r-karte"><table class="ci-tab" id="ci-tracking"><thead><tr><th scope="col">Container</th><th scope="col">Schiff</th><th scope="col">Route</th><th scope="col">Abfahrt</th><th scope="col">Ankunft</th><th scope="col">Stand</th></tr></thead><tbody>${liste.map(zeile).join('')}</tbody></table></div>`
        : `<div class="r-karte"><p class="ci-leer">${T.suche ? 'Kein Container passt zur Suche.' : alle.length ? 'Alle Container sind angekommen.' : 'Noch kein Container. Container legen Sie im Reiter „EUDR“ an.'}</p></div>`);
  }

  function fenster(id) {
    const s = sendung(id);
    if (!s) return;
    const aus = !S.d.rechte.bearbeiten, vor = s.reederei ? '' : vorschlag(s.container), url = verweis(s), r = S.d.reedereien[s.reederei];
    const reedereien = [['', '— bitte wählen —'], ...Object.entries(S.d.reedereien).map(([k, x]) => [k, x.name])];
    const form = $('#tracking-inhalt');
    form.dataset.id = s.id;
    form.innerHTML = kopf('tracking-titel', `Tracking ${s.name}`, esc([s.lieferant, s.ware].filter(Boolean).join(' · ')))
      + `<div class="dlg-body">
        <div class="ci-raster">
          ${feld('Containernummer', 'container', s.container, { aus, platz: 'z. B. MSKU 907032 3', hinweis: HINWEIS_NUMMER[s.containerPruefung] })}${feld('Stand', 'stand', s.stand, { wahl: Object.entries(S.d.staende), aus })}
          ${feld('Schiff', 'schiff', s.schiff, { aus, platz: 'Name des Schiffs' })}${feld('Reederei', 'reederei', s.reederei || vor, { wahl: reedereien, aus, hinweis: vor ? 'Vorschlag nach dem Kürzel der Containernummer – bitte prüfen.' : '' })}
          ${feld('Abgangshafen', 'abgangshafen', s.abgangshafen, { aus, platz: 'z. B. Santos' })}${feld('Zielhafen', 'zielhafen', s.zielhafen, { aus, liste: 'ci-t-haefen', platz: 'z. B. Hamburg' })}
          ${feld('Abfahrt (geplant)', 'etd', s.etd, { typ: 'date', aus })}${feld('Ankunft (geplant)', 'eta', s.eta, { typ: 'date', aus })}
          ${feld('Konnossement (B/L)', 'bl', s.bl, { aus, breit: true, platz: 'Nummer des Konnossements – viele Reedereien verfolgen auch darüber' })}
        </div>
        <datalist id="ci-t-haefen">${HAEFEN.map((h) => `<option value="${h}">`).join('')}</datalist>
        <p class="ci-klein ci-leise">${url ? `Die Sendungsverfolgung öffnet die Seite von ${esc(r.name)} in einem neuen Fenster; die Containernummer liegt dann in der Zwischenablage.`
          : 'Mit Containernummer und Reederei erscheint hier nach dem Speichern der Verweis zur Sendungsverfolgung der Reederei.'}</p>
      </div>
      <div class="dlg-foot">${url ? `<a class="ci-knopf" id="tracking-verweis" href="${esc(url)}" target="_blank" rel="noopener noreferrer" data-nummer="${esc(nummer(s.container))}">Sendungsverfolgung der Reederei</a>` : ''}
        <span class="spacer"></span>
        <button class="ci-knopf" type="button" data-zu>Schließen</button>${aus ? '' : '<button class="ci-knopf primaer" type="submit">Speichern</button>'}</div>`;
    oeffnen($('#dlg-tracking'));
  }

  async function speichern() {
    const form = $('#tracking-inhalt'), w = werte(form), alt = sendung(form.dataset.id);
    const r = await api('containerimport_tracking_save', { id: alt.id, rev: alt.rev, container: w.container, stand: w.stand, schiff: w.schiff, reederei: w.reederei, bl: w.bl, abgangshafen: w.abgangshafen, zielhafen: w.zielhafen, etd: w.etd, eta: w.eta });
    if (!uebernehmen(r, 'Das Tracking konnte nicht gespeichert werden')) return;
    toast('Tracking gespeichert.');
    fenster(r.data.id);
  }

  C.reiter.tracking = zeichnen;
  $('#tracking-inhalt').addEventListener('submit', (e) => { e.preventDefault(); speichern(); });
  document.addEventListener('click', (e) => {
    const zeile = e.target.closest('tr[data-tracking]'), link = e.target.closest('#tracking-verweis');
    if (zeile) fenster(zeile.dataset.tracking);
    if (link && navigator.clipboard) navigator.clipboard.writeText(link.dataset.nummer).then(() => toast('Containernummer kopiert.'), () => {});
  });
  document.addEventListener('input', (e) => {
    if (e.target.id !== 'ci-t-suche') return;
    T.suche = e.target.value;
    const stelle = e.target.selectionStart;
    zeichnen();
    $('#ci-t-suche').focus(); $('#ci-t-suche').setSelectionRange(stelle, stelle);
  });
  document.addEventListener('change', (e) => {
    if (e.target.id === 'ci-t-angekommene') { T.angekommene = e.target.checked; zeichnen(); }
  });
})();
