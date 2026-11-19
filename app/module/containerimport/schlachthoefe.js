/* STAFL-Plattform · Modul Container-Import – Schlachthöfe: Stammdaten unter dem Lieferanten (Entscheidung des Inhabers
   19.11.2026: dem Lieferanten gehören Schlachthöfe, an sie liefern die Farmer). Ansicht „Schlachthöfe“ mit Suche und das
   Fenster zum Anlegen und Ändern. Die Auswahl des Schlachthofs im Fenster „Container“ liegt in containerimport.js.
   Eigene Datei, damit containerimport.js nicht weiter wächst: Hilfen und Zustand kommen über die Brücke window.STAFL_CI
   (containerimport.js lädt zuerst); die Datei trägt ihre Ansicht dort ein und hängt ihre eigenen Ereignisse an.
   Regeln (Name je Lieferant eindeutig, Lieferant mit Containern bleibt) liegen auf dem Server:
   app/api/module/containerimport/schlachthoefe.php. Daten: containerimport_schlachthof_save (die Antwort bringt den neuen
   Stand mit). Fremde Texte nur maskiert. */
(() => {
  'use strict';
  const C = window.STAFL_CI;
  const { S, $, esc, icon, SU, feld, kopf, werte, api, uebernehmen, toast, oeffnen, landName, laenderWahl, lieferantFeld, lieferantAus, suchfeld, archivSchalter, titel } = C;
  S.suche.schlachthoefe = '';
  const hof = (id) => S.d.schlachthoefe.find((x) => x.id === id);
  const containerVon = (id) => S.d.sendungen.filter((s) => s.schlachthof === id);

  function sicht() {
    const darf = S.d.rechte.bearbeiten;
    const liste = S.d.schlachthoefe.filter((x) => (x.aktiv || S.archiv) && SU.findet(S.suche.schlachthoefe, x.name, x.zulassung, x.ort, landName(x.land), x.lieferant, x.lieferantNr))
      .sort((a, b) => a.lieferant.localeCompare(b.lieferant, 'de') || a.name.localeCompare(b.name, 'de'));
    const zeile = (x) => `<tr data-schlachthof="${esc(x.id)}" tabindex="0" class="${x.aktiv ? '' : 'ci-archiv'}">
      <td><span class="ci-name">${esc(x.name)}</span><span class="ci-unter">${x.zulassung ? `Zulassung <span class="ci-zahlen">${esc(x.zulassung)}</span>` : '—'}</span></td>
      <td data-t="Lieferant"><span>${esc(x.lieferant)}</span><span class="ci-unter">${x.lieferantNr ? `Nr. ${esc(x.lieferantNr)}` : 'nicht mit den Stammdaten verknüpft'}</span></td>
      <td data-t="Lage" class="ci-woerter"><span>${esc(landName(x.land))}</span><span class="ci-unter">${esc(x.ort)}</span></td>
      <td data-t="Container" class="ci-r">${containerVon(x.id).length}</td></tr>`;
    $('#ci-inhalt').innerHTML = `<div class="ci-suchzeile">${S.d.schlachthoefe.length ? suchfeld('Name, Zulassungsnummer, Ort, Lieferant', 'Schlachthöfe') : ''}
        ${darf ? `<button class="ci-knopf" type="button" id="ci-schlachthof-neu">${icon('plus')}Neuer Schlachthof</button>` : ''}</div>`
      + (liste.length
        ? `<div class="r-karte"><table class="ci-tab" id="ci-schlachthoefe"><thead><tr><th scope="col">Schlachthof</th><th scope="col">Lieferant</th><th scope="col">Lage</th><th scope="col" class="ci-r">Container</th></tr></thead><tbody>${liste.map(zeile).join('')}</tbody></table></div>`
        : `<div class="r-karte"><p class="ci-leer">${S.d.schlachthoefe.length ? 'Kein Schlachthof passt zur Suche.' : 'Noch kein Schlachthof. Legen Sie die Schlachthöfe Ihrer Lieferanten an – am Container wählen Sie dann den passenden aus.'}</p></div>`)
      + archivSchalter();
  }

  function fenster(id) {
    const neu = !id, darf = S.d.rechte.bearbeiten, aus = !darf;
    const x = neu ? { id: '', rev: 0, name: '', lieferant: '', lieferantNr: '', land: 'PY', ort: '', zulassung: '', notiz: '', aktiv: true } : hof(id);
    if (!x) return;
    const container = neu ? [] : containerVon(x.id).sort((a, b) => b.erstellt.t.localeCompare(a.erstellt.t));
    const form = $('#schlachthof-inhalt');
    form.dataset.id = x.id;
    form.innerHTML = kopf('schlachthof-titel', neu ? 'Neuer Schlachthof' : x.name, neu ? '' : `${esc(x.lieferant)} · ${esc(landName(x.land))}`)
      + `<div class="dlg-body">
        <div class="ci-raster">
          ${feld('Name', 'name', x.name, { aus, platz: 'z. B. Werk Asunción' })}${lieferantFeld(x, aus, neu, 'ci-lieferanten-hof')}
          ${feld('Land', 'land', x.land, { wahl: laenderWahl(x.land), aus })}${feld('Ort', 'ort', x.ort, { aus })}
          ${feld('Zulassungsnummer', 'zulassung', x.zulassung, { aus, platz: 'Betriebsnummer für die Einfuhr in die EU', hinweis: 'Steht im Genusstauglichkeitskennzeichen und in der Veterinärbescheinigung.' })}
          ${feld('Notiz', 'notiz', x.notiz, { lang: 2, aus })}
        </div>
        ${neu ? '' : `<h3 class="ci-h">Container dieses Schlachthofs</h3>${container.length
          ? `<ul class="ci-wahl">${container.map((s) => `<li><span><strong>${esc(titel(s))}</strong><small>${esc([S.d.staende[s.stand], s.ware, s.container && `Container ${s.container}`].filter(Boolean).join(' · '))}</small></span></li>`).join('')}</ul>`
          : '<p class="ci-leise ci-klein">Noch kein Container. Den Schlachthof wählen Sie im Fenster des Containers.</p>'}`}
      </div>
      <div class="dlg-foot"><span class="spacer"></span>
        ${darf && !neu ? `<button class="ci-knopf" type="button" id="schlachthof-archiv">${x.aktiv ? 'Archivieren' : 'Wiederherstellen'}</button>` : ''}
        <button class="ci-knopf" type="button" data-zu>Schließen</button>${darf ? '<button class="ci-knopf primaer" type="submit">Speichern</button>' : ''}</div>`;
    oeffnen($('#dlg-schlachthof'));
  }

  async function speichern(zusatz = {}) {
    const form = $('#schlachthof-inhalt'), w = werte(form), alt = hof(form.dataset.id);
    const r = await api('containerimport_schlachthof_save', { id: form.dataset.id, rev: alt ? alt.rev : 0, aktiv: alt ? alt.aktiv : true, name: w.name, ...lieferantAus(w.lieferant, alt), land: w.land, ort: w.ort, zulassung: w.zulassung, notiz: w.notiz, ...zusatz });
    if (!uebernehmen(r, 'Der Schlachthof konnte nicht gespeichert werden')) return;
    toast('Schlachthof gespeichert.');
    $('#dlg-schlachthof').close();
  }

  C.sichten.schlachthoefe = sicht;
  $('#schlachthof-inhalt').addEventListener('submit', (e) => { e.preventDefault(); speichern(); });
  document.addEventListener('click', (e) => {
    const t = e.target, zeile = t.closest('tr[data-schlachthof]');
    if (t.closest('#ci-schlachthof-neu')) fenster('');
    else if (t.closest('#schlachthof-archiv')) speichern({ aktiv: !hof($('#schlachthof-inhalt').dataset.id).aktiv });
    else if (zeile) fenster(zeile.dataset.schlachthof);
  });
})();
