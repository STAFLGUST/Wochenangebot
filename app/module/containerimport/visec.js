/* STAFL-Plattform · Modul Container-Import – Bereich „Tiere laut VISEC“ im Fenster eines Containers aus Argentinien
   (Auftrag des Inhabers 24.11.2026: bei Lieferungen aus Argentinien die Daten von carne.visec.com.ar abrufen).
   Am Container stehen die DTE-Nummern aus den Papieren (Feld visecDte, gespeichert mit dem Container). „Speichern und bei
   VISEC abfragen“ speichert das Fenster und lässt den Server jede Nummer bei VISEC nachsehen (containerimport_visec_abfragen);
   je DTE zeigt der Bereich Tropa, Daten, Zahl der Tiere nach ihrem Stand laut VISEC und die Nummern der ungültigen bzw. noch
   nicht entschiedenen Tiere. Die Einstufung je DTE (stand) und das Kriterium im Risikoprofil bildet der Server (visec.php);
   diese Datei zeigt nur an.
   Der Bereich erscheint bei einem gespeicherten Container, wenn das Herkunftsland im Fenster Argentinien ist oder
   DTE-Nummern gespeichert sind. Hilfen und Zustand kommen über die Brücke window.STAFL_CI (containerimport.js lädt zuerst);
   die Datei hängt sich an den Haken „fenster“ und an eigene Ereignisse. Fremde Texte nur maskiert. */
(() => {
  'use strict';
  const C = window.STAFL_CI;
  const { S, $, esc, marke, tag, api, uebernehmen, toast } = C;
  const zahl = (n, ein, viele) => `${n} ${n === 1 ? ein : viele}`;
  /* Marke je Einstufung des Servers */
  const MARKE = {
    nie: () => ['nicht abgefragt', 'warn'],
    fehler: (d) => [d.fehler === 'NOT_FOUND' ? 'bei VISEC nicht gefunden' : d.fehler ? 'Fehler bei VISEC' : 'keine Tiere genannt', 'warn'],
    kritisch: (d) => [`${d.zahlen.INVALIDA} ungültig`, 'rot'],
    offen: (d) => [`${d.zahlen.offen} offen`, 'warn'],
    ok: () => ['alle gültig', 'ok'],
  };
  const sichtbar = (land, s) => land === 'AR' || s.visecDte.length > 0;

  function dteZeile(d) {
    const angaben = [d.tropa && `Tropa ${esc(d.tropa)}`, d.fechaDte && `DTE vom ${tag(d.fechaDte)}`, d.fechaArribo && `Ankunft ${tag(d.fechaArribo)}`, d.estado && `Stand ${esc(d.estado)}`].filter(Boolean);
    const tiere = d.tiere ? `<p class="ci-klein">${zahl(d.tiere, 'Tier', 'Tiere')}: ${d.zahlen.VALIDA} gültig · ${d.zahlen.INVALIDA} ungültig · ${d.zahlen.offen} offen${d.registriert ? '' : ' · <span class="ci-leise">VISEC hat diesen DTE noch nicht erfasst (Tiere von SENASA)</span>'}</p>` : '';
    const liste = (titelText, eintraege) => (eintraege.length ? `<details class="ci-visec-tiere"><summary>${titelText}</summary><p class="ci-klein">${eintraege.join(', ')}</p></details>` : '');
    return `<li class="ci-visec-dte"><div class="ci-visec-kopf"><strong>DTE ${esc(d.nummer)}</strong>${marke(...MARKE[d.stand](d))}</div>
      ${angaben.length ? `<p class="ci-klein ci-leise">${angaben.join(' · ')}</p>` : ''}${tiere}
      ${d.fehler ? `<p class="ci-klein">${esc(d.fehler)}${d.fehlerText ? ` – ${esc(d.fehlerText)}` : ''}</p>` : ''}
      ${d.observaciones ? `<p class="ci-klein ci-leise">${esc(d.observaciones)}</p>` : ''}
      ${liste(`Ungültige Tiere (${d.zahlen.INVALIDA})`, d.ungueltig.map(esc))}${liste(`Offene Tiere (${d.zahlen.offen})`, d.offen.map(([nr, stand]) => `${esc(nr)} <span class="ci-leise">(${esc(stand)})</span>`))}
      ${d.t ? `<p class="ci-klein ci-leise">Abgefragt am ${tag(d.t)} von ${esc(d.von)}${d.anfrage ? ` · Anfrage ${esc(d.anfrage)}` : ''}</p>` : ''}</li>`;
  }

  function zeichnen(s) {
    const el = $('#sendung-visec');
    if (!el) return;
    const darf = S.d.rechte.bearbeiten && !s.abschluss;
    el.innerHTML = `<h3 class="ci-h">Tiere laut VISEC <span class="ci-leise">· Argentinien</span></h3>
      ${darf ? `<label class="ci-feld breit"><span>DTE-Nummern aus den Papieren</span><textarea name="visecDte" rows="3" placeholder="je Zeile eine Nummer (Documento de Tránsito Electrónico)">${esc(s.visecDte.join('\n'))}</textarea>
        <small>Gespeichert wird mit dem Container. Bei VISEC geht nur die Nummer hin.</small></label>` : ''}
      ${s.visec.length ? `<ul class="ci-visec-liste">${s.visec.map(dteZeile).join('')}</ul>` : (darf ? '' : '<p class="ci-leer">Keine DTE-Nummern eingetragen.</p>')}
      ${darf && S.d.rechte.visec ? '<p class="ci-visec-knopf"><button class="ci-knopf" type="button" id="visec-abfragen">Speichern und bei VISEC abfragen</button><span id="visec-laeuft" class="ci-klein ci-leise" aria-live="polite"></span></p>'
        : darf ? '<p class="ci-klein ci-leise">Die Abfrage bei VISEC ist auf dem Server nicht eingerichtet (Token fehlt).</p>' : ''}
      <p class="ci-klein ci-leise">VISEC prüft jedes Tier gegen Entwaldung nach dem 31.12.2020, Schutzgebiete und Legalität. VISEC zertifiziert nicht – das Ergebnis stützt die eigene Prüfung.</p>`;
    el.hidden = !sichtbar($('#sendung-inhalt [name=land]').value, s);
  }

  /* Fenster speichern (auch die eben eingetragenen Nummern; sendungSpeichern öffnet das Fenster neu), dann abfragen und das
     Fenster mit dem neuen Profil noch einmal öffnen – es wird also zweimal aufgebaut */
  async function abfragen() {
    const id = $('#sendung-inhalt').dataset.id;
    if (!await C.sendungSpeichern()) return;
    const laeuft = $('#visec-laeuft');
    if (laeuft) laeuft.textContent = 'VISEC wird abgefragt …';
    const r = await api('containerimport_visec_abfragen', { id });
    if (!uebernehmen(r, 'VISEC konnte nicht abgefragt werden')) { const l = $('#visec-laeuft'); if (l) l.textContent = ''; return; }
    const offen = r.data.offen.length;
    toast(offen ? `${r.data.hinweis ? r.data.hinweis + ' ' : ''}${zahl(offen, 'DTE wurde', 'DTE wurden')} nicht abgefragt – bitte später erneut abfragen.` : 'VISEC abgefragt.', offen > 0);
    if ($('#dlg-sendung').open && $('#sendung-inhalt').dataset.id === id) C.sendungOeffnen(id);
  }

  C.haken.fenster.push(zeichnen);
  document.addEventListener('click', (e) => { if (e.target.closest('#visec-abfragen')) abfragen(); });
  document.addEventListener('change', (e) => {
    if (e.target.name !== 'land' || e.target.form !== $('#sendung-inhalt')) return;
    const el = $('#sendung-visec'), s = C.sendung($('#sendung-inhalt').dataset.id);
    if (el && s) el.hidden = !sichtbar(e.target.value, s);
  });
})();
