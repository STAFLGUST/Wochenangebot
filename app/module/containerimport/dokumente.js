/* STAFL-Plattform · Modul Container-Import – Bereich „Dokumente“ im Fenster eines Containers (Auftrag des Inhabers
   20.11.2026): alle Unterlagen des Containerordners ablegen – PDF, Word, Excel (auch .xls) und E-Mail (.eml, .msg), mehrere
   auf einmal per Auswahl oder Ziehen und Ablegen, mit Fortschritt. Je Datei eine oder mehrere Dokumentarten (Sammel-PDF);
   die Arten schlägt der Dateiname vor (Regeln vom Server, S.d.dokRegeln.vorschlaege – nur ein Vorschlag, immer änderbar).
   Checkliste der Platzhalter je Container („fehlt“, Anzahl, „nicht nötig“), Kacheln mit Mini-Vorschau (PDF: erste Seite mit
   pdf.js aus assets/vendor/pdfjs, nur sichtbare und nacheinander, aus dem über die Aktion geladenen Inhalt; sonst Symbol mit
   Endung), Arten ändern und Entfernen (Grund Pflicht) als Vermerk, „Entfernte anzeigen“, Verlauf, ZIP des Containers.
   In der Liste der Container ein kurzer Zähler. Regeln, Rechte und GoBD liegen auf dem Server
   (app/api/module/containerimport/dokumente.php); ausgeblendete Knöpfe sind nur Anzeige.
   Hilfen und Zustand kommen über die Brücke window.STAFL_CI (containerimport.js lädt zuerst); die Datei hängt sich an deren
   Haken (zeile, fenster) und an eigene Ereignisse. Der Bereich liegt im Formular des Containers: keine Felder mit name,
   nur Knöpfe vom Typ „button“. Fremde Texte nur maskiert. */
(() => {
  'use strict';
  const C = window.STAFL_CI, F = window.STAFL_FORMAT;
  const { S, $, esc, icon, marke, api, uebernehmen, toast, base64 } = C;
  const API = '../../api/';
  const PDFJS = new URL('../../assets/vendor/pdfjs/', document.currentScript.src).href;
  const TEIL = 2 * 1024 * 1024;   // Bytes je Teil (Base64 bleibt unter der Grenze des Servers)
  /* Zustand des offenen Containers: Dateien und Vermerke vom Server, Warteschlange der gewählten Dateien, offene Bearbeitung */
  const D = { sendung: '', dateien: null, vermerke: [], fehler: '', warte: [], laedt: false, entfernte: false, arten: '', entfernen: '' };
  const vorschauen = new Map();   // Kennung → gezeichnete erste Seite (canvas) oder null (nicht lesbar)
  const R = () => S.d.dokRegeln;
  const artName = (a) => (R().arten[a] || { name: a }).name;
  const pflicht = () => Object.keys(R().arten).filter((a) => R().arten[a].checkliste);
  const zahlen = (sid) => ({ anzahl: 0, arten: {}, nichtNoetig: [], ...(S.d.dokumente[sid] || {}) });
  const fehlen = (sid) => { const z = zahlen(sid); return pflicht().filter((a) => !z.arten[a] && !z.nichtNoetig.includes(a)); };
  const groesse = (b) => (b < 1048576 ? `${F.zahl(Math.max(1, Math.round(b / 1024)), 0, 0)} KB` : `${F.zahl(b / 1048576, 1, 1)} MB`);
  const endung = (name) => (/\.([a-z0-9]+)$/i.exec(name) || ['', ''])[1].toLowerCase();
  const fehlerText = (r, fallback) => (r.data && r.data.error) || (r.status === 0 ? 'Keine Verbindung zum Server.' : `${fallback} (${r.status}).`);
  const hex = (puffer) => [...new Uint8Array(puffer)].map((b) => b.toString(16).padStart(2, '0')).join('');

  /* Arten aus dem Dateinamen: die erste passende Regel, sonst keine (der Nutzer wählt) */
  function vorschlag(name) {
    const n = name.toLowerCase(), r = R().vorschlaege.find(([muster]) => new RegExp(muster).test(n));
    return r ? [...r[1]] : [];
  }
  C.dokVorschlag = vorschlag;   // für Tests der Zuordnungstabelle

  /* ---------- Zähler in der Liste der Container ---------- */
  C.haken.zeile = (s) => {
    const n = zahlen(s.id).anzahl, f = fehlen(s.id).length;
    return `<span class="ci-unter ci-dok-zahl">${icon('dok')}${n === 1 ? '1 Dokument' : `${n} Dokumente`}${f ? ` · ${f} ${f === 1 ? 'fehlt' : 'fehlen'}` : ' · vollständig'}</span>`;
  };

  /* ---------- Fenster „Container“ ---------- */
  C.haken.fenster = async (s) => {
    if (D.sendung !== s.id) Object.assign(D, { sendung: s.id, warte: [], arten: '', entfernen: '', entfernte: false });
    D.dateien = null; D.fehler = '';
    zeichnen();
    const r = await api('containerimport_dokumente', null, '&sendung=' + encodeURIComponent(s.id));
    if (D.sendung !== s.id) return;
    if (r.status !== 200 || !r.data.ok) D.fehler = fehlerText(r, 'Die Dokumente konnten nicht geladen werden');
    else annehmen(r.data);
    zeichnen();
  };
  function annehmen(d) { D.dateien = d.dokDateien; D.vermerke = d.dokVermerke; S.d.dokumente = d.dokumente; }

  /* Auswahl der Arten als Kästchen (data-art; kein name, damit das Formular des Containers sie nicht mitnimmt) */
  const artenWahl = (gewaehlt, kennung) => `<div class="ci-dok-arten" data-wahl="${esc(kennung)}">${Object.keys(R().arten).map((a) =>
    `<label class="ci-check"><input type="checkbox" data-art="${a}"${gewaehlt.includes(a) ? ' checked' : ''}>${esc(artName(a))}</label>`).join('')}</div>`;
  const gewaehlt = (kennung) => [...document.querySelectorAll(`[data-wahl="${kennung}"] input:checked`)].map((el) => el.dataset.art);

  function checkliste(darf) {
    const z = zahlen(D.sendung);
    return `<ul class="ci-dok-check">${pflicht().map((a) => {
      const n = z.arten[a] || 0, nicht = z.nichtNoetig.includes(a);
      const stand = n ? marke(n === 1 ? 'vorhanden' : `${n} Dateien`, 'ok') : nicht ? marke('nicht nötig') : marke('fehlt', 'warn');
      const knopf = darf && !n ? `<button class="ci-dok-link" type="button" data-noetig="${a}" data-wert="${nicht}">${nicht ? 'wieder nötig' : 'nicht nötig'}</button>` : '';
      return `<li><span>${esc(artName(a))}</span><span class="ci-rechts">${stand}${knopf}</span></li>`;
    }).join('')}</ul>`;
  }

  function warteZeile(w, i) {
    const stand = { wartet: '', laedt: `<progress max="${w.datei.size}" value="${w.empfangen}"></progress> ${Math.floor((100 * w.empfangen) / w.datei.size)} %`,
      fehler: `<span class="ci-dok-fehler">${esc(w.fehler)}</span>`, fertig: marke('abgelegt', 'ok') }[w.stand];
    return `<li class="ci-dok-warte"><div class="ci-dok-zeile"><span class="ci-dok-name">${esc(w.datei.name)}<small>${groesse(w.datei.size)}${w.arten.length ? ` · ${esc(w.arten.map(artName).join(', '))}` : ''}</small></span>
        ${D.laedt || w.stand === 'fertig' ? '' : `<button class="ci-zu" type="button" data-warte-weg="${i}" aria-label="${esc(w.datei.name)} nicht hochladen">${icon('x')}</button>`}</div>
      ${w.gesperrt ? `<p class="ci-dok-fehler">${esc(w.gesperrt)}</p>` : `<details${w.arten.length && !w.offen ? '' : ' open'}><summary>${w.arten.length ? 'Arten ändern' : 'Bitte die Dokumentart wählen'}</summary>${artenWahl(w.arten, 'w' + i)}</details>`}
      ${stand ? `<div class="ci-dok-stand">${stand}</div>` : ''}</li>`;
  }

  function kachel(f, darf) {
    const weg = f.entfernt, pdf = f.endung === 'pdf' && f.groesse <= R().vorschauMax;
    const url = `${API}?action=containerimport_dokument&id=${encodeURIComponent(f.id)}`;
    const bild = pdf ? `<div class="ci-dok-bild" data-pdf="${esc(f.id)}"><span class="ci-dok-endung">PDF</span></div>`
      : `<div class="ci-dok-bild"><span class="ci-dok-endung">${esc(f.endung.toUpperCase())}</span>${icon('dok')}</div>`;
    const bearbeiten = D.arten === f.id ? `<div class="ci-dok-panel">${artenWahl(f.arten, 'k' + f.id)}<div class="ci-dok-knoepfe"><button class="ci-knopf klein" type="button" data-arten-zu>Abbrechen</button><button class="ci-knopf klein primaer" type="button" data-arten-speichern="${esc(f.id)}">Arten speichern</button></div></div>`
      : D.entfernen === f.id ? `<div class="ci-dok-panel"><label class="ci-feld breit"><span>Grund für das Entfernen</span><input type="text" id="dok-grund" maxlength="500" placeholder="z. B. falscher Container, doppelt"><small>Die Datei bleibt abrufbar und erscheint unter „Entfernte anzeigen“.</small></label>
          <div class="ci-dok-knoepfe"><button class="ci-knopf klein" type="button" data-arten-zu>Abbrechen</button><button class="ci-knopf klein primaer" type="button" data-entfernen-ok="${esc(f.id)}">Entfernen</button></div></div>`
      : darf && !weg ? `<div class="ci-dok-knoepfe"><button class="ci-dok-link" type="button" data-arten="${esc(f.id)}">Arten ändern</button><button class="ci-dok-link" type="button" data-entfernen="${esc(f.id)}">Entfernen</button></div>` : '';
    return `<li class="ci-dok-kachel${weg ? ' weg' : ''}" data-dok="${esc(f.id)}">
      <a class="ci-dok-vorschau" href="${url}" download title="${esc(f.name)} herunterladen">${bild}</a>
      <div class="ci-dok-text"><a class="ci-dok-name" href="${url}" download>${esc(f.name)}</a>
        <span class="ci-dok-chips">${f.arten.map((a) => `<span class="ci-marke">${esc(artName(a))}</span>`).join('')}</span>
        <small>${groesse(f.groesse)} · ${F.datumZeit(f.hochgeladen.t)} · ${esc(f.hochgeladen.von)}</small>
        ${weg ? `<small class="ci-dok-fehler">Entfernt am ${F.datumZeit(weg.t)} von ${esc(weg.von)}: ${esc(weg.grund)}</small>` : ''}
        ${bearbeiten}</div></li>`;
  }

  /* Verlauf: Hochladen, Arten geändert, Entfernt, Checkliste – neueste zuerst */
  function verlauf() {
    const e = [];
    for (const f of D.dateien) {
      e.push([f.hochgeladen, `„${f.name}“ abgelegt`]);
      for (const v of f.verlauf || []) e.push([v, `„${f.name}“: Arten ${(v.alt || []).map(artName).join(', ')} → ${(v.neu || []).map(artName).join(', ')}`]);
      if (f.entfernt) e.push([f.entfernt, `„${f.name}“ entfernt: ${f.entfernt.grund}`]);
    }
    for (const v of D.vermerke) e.push([v, `Checkliste: ${artName(v.art)} ${v.noetig ? 'wieder nötig' : 'nicht nötig'}`]);
    e.sort((a, b) => b[0].t.localeCompare(a[0].t));
    return e.length ? `<details class="ci-dok-verlauf"><summary>Verlauf (${e.length})</summary><ul>${e.map(([w, text]) => `<li><span class="ci-leise">${F.datumZeit(w.t)} · ${esc(w.von)}</span> ${esc(text)}</li>`).join('')}</ul></details>` : '';
  }

  function zeichnen() {
    const el = $('#sendung-dokumente');
    if (!el || $('#sendung-inhalt').dataset.id !== D.sendung) return;
    const darf = S.d.rechte.bearbeiten, alle = D.dateien || [], weg = alle.filter((f) => f.entfernt).length;
    const gezeigt = alle.filter((f) => D.entfernte || !f.entfernt), offen = D.warte.filter((w) => w.stand !== 'fertig' && !w.gesperrt);
    const zip = `${API}?action=containerimport_dokumente_zip&sendung=${encodeURIComponent(D.sendung)}`;
    el.innerHTML = `<div class="ci-dok-kopf"><h3 class="ci-h" id="dok-titel">Dokumente${D.dateien ? ` <span class="ci-leise">· ${alle.length - weg}</span>` : ''}</h3>
        ${alle.length ? `<a class="ci-knopf klein" href="${zip}" download id="dok-zip">${icon('runter')}ZIP herunterladen</a>` : ''}</div>`
      + (D.fehler ? `<p class="ci-meldung">${icon('warn')} ${esc(D.fehler)}</p>` : !D.dateien ? '<p class="ci-leise ci-klein">Dokumente werden geladen …</p>' : checkliste(darf)
        + (darf ? `<label class="ci-ablage ci-dok-ablage" for="dok-dateien">${icon('hoch')}<span><strong>Dateien hierher ziehen oder auswählen</strong><small>PDF, Word, Excel (auch .xls) und E-Mails (.eml, .msg), mehrere auf einmal. Die Art schlägt der Dateiname vor; eine Sammel-PDF kann mehrere Arten tragen. Nichts wird überschrieben.</small></span>
            <input type="file" id="dok-dateien" multiple accept="${R().endungen.map((e) => '.' + e).join(',')}"></label>` : '')
        + (D.warte.length ? `<ul class="ci-dok-warteliste">${D.warte.map(warteZeile).join('')}</ul>
            <div class="ci-dok-knoepfe">${offen.length ? `<button class="ci-knopf primaer" type="button" id="dok-hochladen"${D.laedt || offen.some((w) => !w.arten.length) ? ' disabled' : ''}>${icon('hoch')}${offen.length === 1 ? 'Datei hochladen' : `${offen.length} Dateien hochladen`}</button>` : ''}${D.laedt ? '' : '<button class="ci-knopf klein" type="button" id="dok-warte-leeren">Liste leeren</button>'}</div>` : '')
        + (gezeigt.length ? `<ul class="ci-dok-kacheln">${gezeigt.map((f) => kachel(f, darf)).join('')}</ul>` : `<p class="ci-leise ci-klein">${alle.length ? 'Alle Dateien sind entfernt.' : 'Noch keine Dokumente an diesem Container.'}</p>`)
        + (weg ? `<label class="ci-check"><input type="checkbox" id="dok-entfernte"${D.entfernte ? ' checked' : ''}>Entfernte anzeigen (${weg})</label>` : '')
        + verlauf());
    vorschauBeobachten(el);
  }

  /* ---------- Mini-Vorschau der PDF: erste Seite, nur sichtbare, nacheinander ---------- */
  const schlange = [];
  let laeuft = false;
  const beobachter = 'IntersectionObserver' in window ? new IntersectionObserver((eintraege) => {
    for (const e of eintraege) if (e.isIntersecting) { beobachter.unobserve(e.target); schlange.push(e.target.dataset.pdf); }
    abarbeiten();
  }) : null;
  function vorschauBeobachten(el) {
    for (const b of el.querySelectorAll('[data-pdf]')) {
      if (vorschauen.has(b.dataset.pdf)) einsetzen(b.dataset.pdf);
      else if (beobachter) beobachter.observe(b);
    }
  }
  function einsetzen(id) {
    const c = vorschauen.get(id), b = document.querySelector(`.ci-dok-bild[data-pdf="${CSS.escape(id)}"]`);
    if (!b) return;
    if (c) { b.replaceChildren(c); b.classList.add('gezeichnet'); } else b.classList.add('ohne');
  }
  async function abarbeiten() {
    if (laeuft) return;
    laeuft = true;
    while (schlange.length) {
      const id = schlange.shift();
      if (!vorschauen.has(id)) vorschauen.set(id, await ersteSeite(id));
      einsetzen(id);
    }
    laeuft = false;
  }
  async function ersteSeite(id) {
    try {
      const res = await fetch(`${API}?action=containerimport_dokument&id=${encodeURIComponent(id)}`, { credentials: 'same-origin', cache: 'no-store' });
      if (!res.ok) return null;
      const pdfjs = await import(PDFJS + 'pdf.min.js');
      pdfjs.GlobalWorkerOptions.workerSrc = PDFJS + 'pdf.worker.min.js';
      const aufgabe = pdfjs.getDocument({ data: new Uint8Array(await res.arrayBuffer()), isEvalSupported: false });
      const seite = await (await aufgabe.promise).getPage(1);
      const vp = seite.getViewport({ scale: 2 * 120 / seite.getViewport({ scale: 1 }).width });   // doppelte Auflösung für scharfe Anzeige
      const c = document.createElement('canvas');
      c.width = Math.ceil(vp.width); c.height = Math.ceil(vp.height);
      await seite.render({ canvasContext: c.getContext('2d'), viewport: vp }).promise;
      await aufgabe.destroy();
      return c;
    } catch (e) { console.warn('Vorschau nicht möglich:', id, e); return null; }
  }

  /* ---------- Warteschlange und Hochladen ---------- */
  async function aufnehmen(dateien) {
    const vorhanden = new Map((D.dateien || []).filter((f) => !f.entfernt).map((f) => [f.sha256, f.name]));
    for (const datei of dateien) {
      const w = { datei, sendung: D.sendung, arten: vorschlag(datei.name), offen: false, stand: 'wartet', empfangen: 0, fehler: '', gesperrt: '', sha: '' };
      if (!R().endungen.includes(endung(datei.name))) w.gesperrt = 'Diese Dateiart kann nicht abgelegt werden (erlaubt: PDF, Word, Excel, E-Mail).';
      else if (!datei.size) w.gesperrt = 'Die Datei ist leer.';
      else {
        w.sha = hex(await crypto.subtle.digest('SHA-256', await datei.arrayBuffer()));
        if (vorhanden.has(w.sha) || D.warte.some((x) => x.sha === w.sha)) w.gesperrt = `Liegt schon an diesem Container${vorhanden.has(w.sha) ? ` („${vorhanden.get(w.sha)}“)` : ''}.`;
      }
      D.warte.push(w);
    }
    zeichnen();
  }
  async function eineDatei(w) {
    let upload = '';
    for (let teil = 0; teil * TEIL < w.datei.size; teil++) {
      const daten = base64(new Uint8Array(await w.datei.slice(teil * TEIL, (teil + 1) * TEIL).arrayBuffer()));
      const r = await api('containerimport_dokument_hochladen', { sendung: w.sendung, arten: w.arten, upload, teil, daten, name: w.datei.name, groesse: w.datei.size, sha256: w.sha }, '', false);
      if (r.status !== 200 || !r.data.ok) return fehlerText(r, 'Das Hochladen ist fehlgeschlagen');
      if (r.data.fertig) { if (D.sendung === w.sendung) annehmen(r.data); else S.d.dokumente = r.data.dokumente; return ''; }
      upload = r.data.upload; w.empfangen = r.data.empfangen;
      zeichnen();
    }
    return 'Die Datei kam nicht vollständig an.';
  }
  async function hochladen() {
    if (D.laedt) return;
    D.laedt = true;
    const liste = D.warte.filter((w) => w.stand !== 'fertig' && !w.gesperrt);
    let ok = 0;
    for (const w of liste) {
      w.stand = 'laedt'; w.empfangen = 0; zeichnen();
      w.fehler = await eineDatei(w);
      w.stand = w.fehler ? 'fehler' : 'fertig';
      if (!w.fehler) ok++;
    }
    D.laedt = false;
    D.warte = D.warte.filter((w) => w.stand !== 'fertig');
    C.reiter[S.reiter]();   // Zähler in der Liste der Container
    zeichnen();
    const falsch = liste.length - ok;
    toast(falsch ? `${ok} von ${liste.length} Dateien abgelegt – ${falsch} mit Fehler (siehe Liste).` : ok === 1 ? 'Datei abgelegt.' : `${ok} Dateien abgelegt.`, falsch > 0);
  }

  /* ---------- Arten ändern, Entfernen, Checkliste ---------- */
  async function senden(action, body, erfolg) {
    const r = await api(action, body);
    if (!uebernehmen(r, 'Das konnte nicht gespeichert werden')) return;
    annehmen(r.data);
    D.arten = ''; D.entfernen = '';
    zeichnen();
    toast(erfolg);
  }

  /* ---------- Ereignisse (nur im Bereich „Dokumente“) ---------- */
  document.addEventListener('click', (e) => {
    const t = e.target;
    if (!t.closest('#sendung-dokumente')) return;
    const b = (sel) => t.closest(sel);
    if (b('#dok-hochladen')) { hochladen(); return; }
    if (b('#dok-warte-leeren')) { D.warte = []; zeichnen(); return; }
    const weg = b('[data-warte-weg]');
    if (weg) { D.warte.splice(Number(weg.dataset.warteWeg), 1); zeichnen(); return; }
    const noetig = b('[data-noetig]');
    if (noetig) { senden('containerimport_dokument_checkliste', { sendung: D.sendung, art: noetig.dataset.noetig, noetig: noetig.dataset.wert === 'true' }, 'Checkliste gespeichert.'); return; }
    const arten = b('[data-arten]');
    if (arten) { D.arten = arten.dataset.arten; D.entfernen = ''; zeichnen(); return; }
    const entf = b('[data-entfernen]');
    if (entf) { D.entfernen = entf.dataset.entfernen; D.arten = ''; zeichnen(); $('#dok-grund').focus(); return; }
    if (b('[data-arten-zu]')) { D.arten = ''; D.entfernen = ''; zeichnen(); return; }
    const speichern = b('[data-arten-speichern]');
    if (speichern) {
      const neu = gewaehlt('k' + speichern.dataset.artenSpeichern);
      if (!neu.length) { toast('Bitte mindestens eine Dokumentart wählen.', true); return; }
      senden('containerimport_dokument_arten', { id: speichern.dataset.artenSpeichern, arten: neu }, 'Arten geändert.');
      return;
    }
    const ok = b('[data-entfernen-ok]');
    if (ok) {
      const grund = $('#dok-grund').value.trim();
      if (!grund) { toast('Bitte einen Grund angeben.', true); $('#dok-grund').focus(); return; }
      senden('containerimport_dokument_entfernen', { id: ok.dataset.entfernenOk, grund }, 'Datei als entfernt vermerkt.');
    }
  });
  document.addEventListener('change', (e) => {
    const t = e.target;
    if (!t.closest('#sendung-dokumente')) return;
    if (t.id === 'dok-dateien') { aufnehmen([...t.files]); return; }
    if (t.id === 'dok-entfernte') { D.entfernte = t.checked; zeichnen(); return; }
    const wahl = t.closest('[data-wahl^="w"]');   // Arten einer wartenden Datei
    if (wahl) { Object.assign(D.warte[Number(wahl.dataset.wahl.slice(1))], { arten: gewaehlt(wahl.dataset.wahl), offen: true }); zeichnen(); }
  });
  /* Eingabetaste im Feld „Grund“ entfernt, statt den Container zu speichern */
  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Enter' || e.target.id !== 'dok-grund') return;
    e.preventDefault();
    document.querySelector('[data-entfernen-ok]').click();
  });
  /* Ziehen und Ablegen auf die Ablagefläche */
  for (const art of ['dragenter', 'dragover']) document.addEventListener(art, (e) => {
    const z = e.target.closest && e.target.closest('.ci-dok-ablage');
    if (!z) return;
    e.preventDefault(); z.classList.add('ziel');
  });
  document.addEventListener('dragleave', (e) => { const z = e.target.closest && e.target.closest('.ci-dok-ablage'); if (z) z.classList.remove('ziel'); });
  document.addEventListener('drop', (e) => {
    const z = e.target.closest && e.target.closest('.ci-dok-ablage');
    if (!z) return;
    e.preventDefault(); z.classList.remove('ziel');
    if (!D.laedt && e.dataTransfer.files.length) aufnehmen([...e.dataTransfer.files]);
  });
})();
