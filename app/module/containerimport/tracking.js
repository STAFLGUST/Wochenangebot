/* STAFL-Plattform · Modul Container-Import – Reiter „Tracking“: wo ist der Container, wann kommt er an (Auftrag des
   Inhabers 19.11.2026). Liste der Container mit Schiff, Reederei, Route, geplanter Abfahrt und Ankunft („in 12 Tagen“,
   „überfällig“), Suche, Fenster zum Pflegen und ein Verweis zur Sendungsverfolgung der Reederei.
   Die Angaben am Container werden von Hand gepflegt. Dazu stellt der Server die Meldung von Hafen Hamburg (öffentliche
   Liste „Expected vessels“, die nächsten Ankünfte): bestätigte Ankunft, Liegeplatz und Terminal eines Schiffs, das bei einem
   Container mit Zielhafen Hamburg eingetragen ist (S.d.hafen, hafen.php). Die Seite stößt das Auffrischen einmal je Besuch
   des Reiters im Hintergrund an (containerimport_tracking_hafen liefert nur die Meldungen); der Server entscheidet, ob er
   wirklich abruft. Die Meldung ist ein Hinweis – sie ändert weder Stand noch geplante Ankunft. Die Reederei wird
   aus dem Kürzel der Containernummer nur vorgeschlagen (Hinweis am Feld) – gespeichert wird, was gewählt ist. Der Verweis öffnet
   die Seite der Reederei in einem neuen Fenster und legt die Containernummer in die Zwischenablage.
   Hilfen und Zustand kommen über die Brücke window.STAFL_CI (containerimport.js lädt zuerst); die Datei trägt ihren Reiter
   dort ein und hängt ihre eigenen Ereignisse an. Regeln (Datum, Auswahl der Reederei) prüft der Server:
   app/api/module/containerimport/tracking.php. Daten: containerimport_tracking_save (die Antwort bringt den neuen Stand
   mit). Fremde Texte nur maskiert. */
(() => {
  'use strict';
  const C = window.STAFL_CI, F = window.STAFL_FORMAT;
  const { S, $, esc, SU, feld, kopf, werte, marke, tag, api, uebernehmen, toast, oeffnen, sendung, suchfeld, HINWEIS_NUMMER } = C;
  S.suche.tracking = '';
  let angekommene = false;   // auch angekommene Container zeigen
  let hafenAngestossen = false;  // Auffrischen der Hafenliste in diesem Besuch schon angestoßen
  const HAEFEN = ['Hamburg', 'Rotterdam', 'Bremerhaven', 'Antwerpen', 'Wilhelmshaven'];
  const nummer = (text) => text.replace(/[\s./-]+/g, '').toUpperCase();   // Containernummer ohne Gliederung, wie eudr_containernummer auf dem Server
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

  /* Meldung von Hafen Hamburg: „20.11.2026, 14:30 · Liegeplatz, Terminal“ */
  const meldungText = (m) => [F.datumZeit(m.ankunft), [m.liegeplatz, m.terminal].filter(Boolean).join(', ')].filter(Boolean).join(' · ');
  function hafenHinweis() {
    const h = S.d.hafen;
    if (h.fehler) return h.fehler + (h.gelesen ? ` Angezeigt wird der letzte lesbare Stand (${F.datumZeit(h.gelesen)}).` : '');
    if (h.gelesen) return `Ankünfte in Hamburg laut Hafen Hamburg (HVCC), Stand ${F.datumZeit(h.gelesen)}: ${h.anzahl === 1 ? 'das nächste Schiff' : `die nächsten ${h.anzahl} Schiffe`}.`;
    return 'Abfahrt und Ankunft werden von Hand gepflegt. Für Container mit Schiff und Zielhafen Hamburg zeigt die Seite zusätzlich die Meldung von Hafen Hamburg, sobald das Schiff dort unter den nächsten Ankünften steht.';
  }
  /* Einmal je Besuch: Server bitten, die Hafenliste aufzufrischen. Läuft im Hintergrund und fasst deshalb nur die eigenen
     Meldungen an – nie den übrigen Stand (eine inzwischen gespeicherte Änderung bliebe sonst auf der Strecke) und nur den
     eigenen Reiter. Fehler bleiben still: Die Liste ist ein Zusatz. */
  async function hafenAuffrischen() {
    if (hafenAngestossen) return;
    hafenAngestossen = true;
    const r = await api('containerimport_tracking_hafen', {}, '', false);
    if (!r.data.hafen || r.data.hafen.abgerufen === S.d.hafen.abgerufen) return;   // nichts Neues: nichts anfassen
    S.d.hafen = r.data.hafen;
    if (S.reiter !== 'tracking') return;
    /* neu zeichnen, ohne die Tastatur zu stören: wer gerade sucht, tippt weiter; wer auf einer Zeile steht, bleibt dort */
    const a = document.activeElement, zeile = a && a.dataset.tracking, suche = a && a.id === 'ci-t-suche' ? a.selectionStart : null;
    zeichnen();
    if (suche !== null) { $('#ci-t-suche').focus(); $('#ci-t-suche').setSelectionRange(suche, suche); }
    if (zeile) document.querySelectorAll('tr[data-tracking]').forEach((tr) => { if (tr.dataset.tracking === zeile) tr.focus(); });
  }

  function zeichnen() {
    hafenAuffrischen();
    const alle = S.d.sendungen.filter((s) => s.aktiv), unterwegs = alle.filter((s) => s.stand !== 'angekommen');
    const liste = (angekommene ? alle : unterwegs)
      .filter((s) => SU.findet(S.suche.tracking, s.partie, s.akte, s.container, s.nummer, s.schiff, s.bl, s.abgangshafen, s.zielhafen, s.lieferant, s.ware, (S.d.reedereien[s.reederei] || {}).name))
      .sort((a, b) => (a.stand === 'angekommen') - (b.stand === 'angekommen') || (a.eta || '9999').localeCompare(b.eta || '9999') || b.erstellt.t.localeCompare(a.erstellt.t));
    const zeiten = unterwegs.map((s) => s.eta).filter(Boolean).sort(), ueberfaellig = zeiten.filter((t) => t < S.d.heute).length, naechste = zeiten[ueberfaellig];
    const zeile = (s) => {
      const [text, farbe] = ankunft(s), r = S.d.reedereien[s.reederei], m = S.d.hafen.meldungen[s.id];
      return `<tr data-tracking="${esc(s.id)}" tabindex="0">
        <td><span class="ci-name">${esc(s.name)}</span><span class="ci-unter">${s.container ? `<span class="ci-zahlen">${esc(s.container)}</span>` : 'Containernummer fehlt'}</span></td>
        <td data-t="Schiff"><span>${esc(s.schiff || '—')}</span><span class="ci-unter">${esc(r ? r.name : '')}</span></td>
        <td data-t="Route"><span>${esc(s.abgangshafen || '—')} → ${esc(s.zielhafen || '—')}</span><span class="ci-unter">${esc([s.lieferant, s.ware].filter(Boolean).join(' · '))}</span></td>
        <td data-t="Abfahrt" class="ci-fest">${tag(s.etd)}</td>
        <td data-t="Ankunft" class="ci-fest"><span>${tag(s.eta)}</span><span class="ci-unter">${marke(text, farbe)}</span>${m ? `<span class="ci-unter ci-t-meldung">Hafen Hamburg: ${esc(meldungText(m))}</span>` : ''}</td>
        <td data-t="Stand">${marke(S.d.staende[s.stand], s.stand === 'angekommen' ? 'ok' : '')}</td></tr>`;
    };
    $('#ci-bereich-tracking').innerHTML = `<p class="ci-t-lage">${unterwegs.length === 1 ? '1 Container ist' : `${unterwegs.length} Container sind`} noch nicht angekommen${ueberfaellig ? ` · ${ueberfaellig} überfällig` : ''}${naechste ? ` · nächste Ankunft ${tag(naechste)}` : ''}.
        <span class="ci-leise" id="ci-t-hafen">${esc(hafenHinweis())}</span></p>
      <div class="ci-suchzeile">${suchfeld('Partie, Containernummer, Schiff, Hafen, Lieferant', 'Tracking', 'tracking', 'ci-t-suche')}
        <label class="ci-check"><input type="checkbox" id="ci-t-angekommene"${angekommene ? ' checked' : ''}>Angekommene anzeigen</label></div>`
      + (liste.length
        ? `<div class="r-karte"><table class="ci-tab" id="ci-tracking"><thead><tr><th scope="col">Container</th><th scope="col">Schiff</th><th scope="col">Route</th><th scope="col">Abfahrt</th><th scope="col">Ankunft</th><th scope="col">Stand</th></tr></thead><tbody>${liste.map(zeile).join('')}</tbody></table></div>`
        : `<div class="r-karte"><p class="ci-leer">${S.suche.tracking ? 'Kein Container passt zur Suche.' : alle.length ? 'Alle Container sind angekommen.' : 'Noch kein Container. Container legen Sie im Reiter „EUDR“ an.'}</p></div>`);
  }

  function fenster(id) {
    const s = sendung(id);
    if (!s) return;
    const aus = !S.d.rechte.bearbeiten, vor = s.reederei ? '' : vorschlag(s.container), url = verweis(s), r = S.d.reedereien[s.reederei], m = S.d.hafen.meldungen[s.id];
    const meldung = m ? `<div class="ci-abschluss"><span class="ci-marke ok">Hafen Hamburg</span><span>${esc(m.schiff)} wird erwartet: ${esc(meldungText(m))}<small>Öffentliche Liste des Hafens (Quelle HVCC), Stand ${esc(F.datumZeit(S.d.hafen.gelesen))}. Zeiten und Liegeplätze können sich kurzfristig ändern.</small></span></div>` : '';
    const reedereien = [['', '— bitte wählen —'], ...Object.entries(S.d.reedereien).map(([k, x]) => [k, x.name])];
    const form = $('#tracking-inhalt');
    form.dataset.id = s.id;
    form.innerHTML = kopf('tracking-titel', `Tracking ${s.name}`, esc([s.lieferant, s.ware].filter(Boolean).join(' · ')))
      + `<div class="dlg-body">
        ${meldung}
        <div class="ci-raster">
          ${feld('Containernummer', 'container', s.container, { aus, platz: 'z. B. MSKU 907032 3', hinweis: HINWEIS_NUMMER[s.containerPruefung] })}${feld('Stand', 'stand', s.stand, { wahl: Object.entries(S.d.staende), aus })}
          ${feld('Schiff', 'schiff', s.schiff, { aus, platz: 'Name des Schiffs' })}${feld('Reederei', 'reederei', s.reederei, { wahl: reedereien, aus, hinweis: vor ? `Nach dem Kürzel der Containernummer vermutlich ${S.d.reedereien[vor].name} – bitte wählen.` : '' })}
          ${feld('Abgangshafen', 'abgangshafen', s.abgangshafen, { aus, platz: 'z. B. Santos' })}${feld('Zielhafen', 'zielhafen', s.zielhafen, { aus, liste: 'ci-t-haefen', platz: 'z. B. Hamburg' })}
          ${feld('Abfahrt (geplant)', 'etd', s.etd, { typ: 'date', aus })}${feld('Ankunft (geplant)', 'eta', s.eta, { typ: 'date', aus })}
          ${feld('Konnossement (B/L)', 'bl', s.bl, { aus, breit: true, platz: 'Nummer des Konnossements – viele Reedereien verfolgen auch darüber' })}
        </div>
        <datalist id="ci-t-haefen">${HAEFEN.map((h) => `<option value="${h}">`).join('')}</datalist>
        <p class="ci-klein ci-leise">${url ? `Die Sendungsverfolgung öffnet die Seite von ${esc(r.name)} in einem neuen Fenster und legt die Containernummer zum Einfügen in die Zwischenablage, wenn der Browser das zulässt.`
          : r && !r.url ? 'Für diese Reederei ist keine Sendungsverfolgung hinterlegt.' : 'Mit Containernummer und Reederei erscheint hier nach dem Speichern der Verweis zur Sendungsverfolgung der Reederei.'}</p>
      </div>
      <div class="dlg-foot">${url ? `<a class="ci-knopf" id="tracking-verweis" href="${esc(url)}" target="_blank" rel="noopener noreferrer" data-nummer="${esc(nummer(s.container))}">Sendungsverfolgung der Reederei</a>` : ''}
        <span class="spacer"></span>
        <button class="ci-knopf" type="button" data-zu>Schließen</button>${aus ? '' : '<button class="ci-knopf primaer" type="submit">Speichern</button>'}</div>`;
    oeffnen($('#dlg-tracking'));
  }

  async function speichern() {
    const form = $('#tracking-inhalt'), w = werte(form), alt = sendung(form.dataset.id);
    const r = await api('containerimport_tracking_save', { id: alt.id, rev: alt.rev, ...w });   // die Felder des Fensters heißen wie die Angaben
    if (!uebernehmen(r, 'Das Tracking konnte nicht gespeichert werden')) return;
    toast('Tracking gespeichert.');
    fenster(r.data.id);
  }

  C.reiter.tracking = zeichnen;
  $('#tracking-inhalt').addEventListener('submit', (e) => { e.preventDefault(); speichern(); });
  document.addEventListener('click', (e) => {
    const zeile = e.target.closest('tr[data-tracking]'), link = e.target.closest('#tracking-verweis');
    if (e.target.closest('#ci-neu')) hafenAngestossen = false;   // „Stand neu laden“ fragt auch die Hafenliste wieder an
    if (zeile) fenster(zeile.dataset.tracking);
    if (link && navigator.clipboard) navigator.clipboard.writeText(link.dataset.nummer).then(() => toast('Containernummer kopiert.'), () => {});
  });
  document.addEventListener('change', (e) => {
    if (e.target.id === 'ci-t-angekommene') { angekommene = e.target.checked; zeichnen(); }
  });
})();
