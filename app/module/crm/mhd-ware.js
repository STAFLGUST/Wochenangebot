/* STAFL-Plattform · CRM · Reiter „MHD-Ware“ (Auftrag des Inhabers 01.11.2026): links die Artikel kurz vor Ablauf aus der MHD-Liste
   des Bestands – in denselben Farben wie dort (abgelaufen, 0–4, 5–7, 8–14 Tage) –, rechts die Kunden, die den gewählten Artikel
   gekauft haben (Standard: letzte 3 Monate, umschaltbar auf 6 oder 12): Telefon, Vertreter, letzter Kauf, Käufe, Menge.
   Ein anderer Artikel lässt sich suchen. Aus der Liste: Kundenblatt öffnen, für ausgewählte Kunden eine Wiedervorlage anlegen
   („MHD-Ware anbieten: …“, Recht CRM bearbeiten). Keine Preise und keine Umsätze – Daten nur über die Aktionen crm_mhd und
   crm_mhd_kaeufer (Recht crm.mhd_ware, geprüft auf dem Server). Wird von crm.js aufgerufen (window.STAFL_CRM_MHD.zeichne). */
'use strict';
(() => {
  const F = window.STAFL_FORMAT;   // Zahlen und Einheiten wie auf allen Seiten (app/assets/format.js)
  const kg = (milli) => (milli === null || milli === undefined ? '—' : F.kg(milli / 1000));   // wie im Bestand: 12,50 kg
  const kgZahl = (v) => (v === null || v === undefined ? '—' : F.kg(v));
  const STUFE = { abgelaufen: ['vorbei', 'abgelaufen'], '0-4': ['rot', 'heute – 4 Tage'], '5-7': ['orange', '5 – 7 Tage'], '8-14': ['gelb', '8 – 14 Tage'] };
  const REGELMAESSIG = 3;   // ab so vielen Käufen im Zeitraum „kauft regelmäßig“
  const M = { d: null, monate: 3, wahl: '', k: null, vertreter: '', regel: false, auswahl: new Set(), suche: '', ladenListe: 0, ladenKaeufer: 0, fehler: '', host: null, c: null };

  const tageBis = (iso, heute) => Math.round((new Date(iso + 'T12:00:00') - new Date(heute + 'T12:00:00')) / 86400000);
  function mhdText(a, heute) {
    if (!a.mhd) return '';
    const t = tageBis(a.mhd, heute);
    return t < 0 ? `seit ${-t === 1 ? 'gestern' : -t + ' Tagen'} abgelaufen` : t === 0 ? 'läuft heute ab' : t === 1 ? 'noch 1 Tag' : `noch ${t} Tage`;
  }
  const marke = (a, c, lang = false) => (a.mhd ? `<span class="crm-mhd-marke ${STUFE[a.stufe] ? STUFE[a.stufe][0] : ''}">MHD ${c.de(a.mhd)}${lang ? ` · ${c.esc(mhdText(a, M.d.heute))}` : ''}</span>` : '');

  async function listeLaden() {
    const nr = ++M.ladenListe;
    const r = await M.c.api('crm_mhd', null, '&monate=' + M.monate);
    if (nr !== M.ladenListe) return;
    if (r.status !== 200 || !r.data.ok) { M.fehler = M.c.fehlerText(r, 'Die MHD-Liste konnte nicht geladen werden'); zeichneAlles(); return; }
    M.fehler = ''; M.d = r.data;
    if (!M.wahl && M.d.artikel.length) M.wahl = M.d.artikel[0].code;
    zeichneAlles();
    if (M.wahl) kaeuferLaden();
  }
  async function kaeuferLaden() {
    const nr = ++M.ladenKaeufer;
    M.k = null; M.auswahl.clear(); zeichneKaeufer();
    const r = await M.c.api('crm_mhd_kaeufer', null, '&artikel=' + encodeURIComponent(M.wahl) + '&monate=' + M.monate);
    if (nr !== M.ladenKaeufer) return;
    if (r.status !== 200 || !r.data.ok) { M.k = { fehler: M.c.fehlerText(r, 'Die Käufer konnten nicht geladen werden') }; zeichneKaeufer(); return; }
    M.k = r.data; zeichneKaeufer();
  }

  /* ---------- Links: MHD-Liste und Suche ---------- */
  function zeichneListe() {
    const c = M.c, box = M.host.querySelector('#mhd-liste');
    if (!box) return;
    const q = M.suche.trim().toLocaleLowerCase('de-DE');
    const treffer = q.length >= 2 || /^\d+$/.test(q) ? M.d.alle.filter((a) => a.name.toLocaleLowerCase('de-DE').includes(q) || a.nr.toLocaleLowerCase('de-DE').includes(q)).slice(0, 12) : [];
    box.innerHTML = (M.d.artikel.length ? M.d.artikel.map((a) => `<li><button type="button" class="crm-mhd-artikel ${STUFE[a.stufe] ? STUFE[a.stufe][0] : ''}" data-mhd-artikel="${c.esc(a.code)}" aria-pressed="${a.code === M.wahl}">
        <span class="crm-mhd-name"><b>${c.esc(a.name)}</b><small>${c.esc(a.code)} · ${c.esc(kgZahl(a.mhdKg))} mit kürzestem MHD</small></span>
        <span class="crm-mhd-rechts">${marke(a, c)}<small>${a.kaeufer === 1 ? '1 Käufer' : `${a.kaeufer} Käufer`}</small></span></button></li>`).join('')
      : '<li class="crm-leer">Kein Artikel mit MHD in den nächsten 14 Tagen.</li>')
      + `<li class="crm-mhd-suchzeile"><label class="crm-suche"><span class="sr-only">Anderen Artikel suchen</span>${c.icon('search')}<input type="search" id="mhd-suche" value="${c.esc(M.suche)}" placeholder="Anderen Artikel suchen (Name oder Nummer)" autocomplete="off"></label>
        ${treffer.length ? `<div class="crm-mhd-treffer">${treffer.map((a) => `<button type="button" data-mhd-artikel="${c.esc(a.nr)}" aria-pressed="${a.nr === M.wahl}"><b>${c.esc(a.name)}</b> <small>${c.esc(a.nr)}</small></button>`).join('')}</div>`
          : q.length >= 2 ? '<p class="crm-leer">Kein Artikel in den Umsatzdaten gefunden.</p>' : ''}</li>`;
  }

  /* ---------- Rechts: Käufer des gewählten Artikels ---------- */
  function kaeuferZeilen() {
    const c = M.c, kunden = c.daten().kunden;
    const je = new Map(kunden.map((k) => [k.key, k]));
    return M.k.kaeufer.map((x) => ({ x, k: x.key ? je.get(x.key) : null }))
      .filter(({ x, k }) => (!M.vertreter || (k && (k.vertreter === M.vertreter || k.vertreter2 === M.vertreter))) && (!M.regel || x.kaeufe >= REGELMAESSIG));
  }
  function zeichneKaeufer() {
    const c = M.c, box = M.host.querySelector('#mhd-kaeufer');
    if (!box) return;
    if (!M.wahl) { box.innerHTML = '<p class="crm-leer">Bitte links einen Artikel wählen.</p>'; return; }
    if (!M.k) { box.innerHTML = '<p class="crm-leer">Käufer werden gesucht …</p>'; return; }
    if (M.k.fehler) { box.innerHTML = `<p class="crm-meldung fehler" role="alert">${c.esc(M.k.fehler)}</p>`; return; }
    const a = M.k.artikel, zeilen = kaeuferZeilen(), alle = M.k.kaeufer, bearbeiten = c.daten().rechte.bearbeiten;
    const regel = alle.filter((x) => x.kaeufe >= REGELMAESSIG).length, menge = alle.reduce((s, x) => s + x.menge, 0), zuletzt = alle.reduce((s, x) => (x.zuletzt > s ? x.zuletzt : s), '');
    const gewaehlt = zeilen.filter(({ k }) => k && M.auswahl.has(k.key)).length;
    box.innerHTML = `<div class="crm-mhd-kopf"><div><h2>${c.esc(a.name)} <small>${c.esc(a.nr)}</small></h2>
        <p>${a.mhd ? `${marke(a, c, true)} · ${c.esc(kgZahl(a.mhdKg))} mit kürzestem MHD · ${c.esc(kgZahl(a.kg))} auf Lager` : 'Nicht in der MHD-Liste'}</p></div>
        <div class="crm-mhd-wahl"><div class="crm-seg" role="group" aria-label="Zeitraum">${[3, 6, 12].map((n) => `<button type="button" data-mhd-monate="${n}" aria-pressed="${n === M.monate}">${n} Monate</button>`).join('')}</div>
          <select id="mhd-vertreter" aria-label="Vertreter">${c.vOpts(M.vertreter)}</select>
          <label class="crm-mhd-check"><input type="checkbox" id="mhd-regel"${M.regel ? ' checked' : ''}> kauft regelmäßig (ab ${REGELMAESSIG} Käufen)</label></div></div>
      <div class="crm-mhd-werte">${[['Käufer', String(alle.length)], ['Davon regelmäßig', String(regel)], ['Menge gekauft', menge === null || menge === undefined ? '—' : F.kgSumme(menge / 1000)], ['Zuletzt gekauft', zuletzt ? c.de(zuletzt) : '—']]
        .map(([n, w]) => `<div><span>${c.esc(n)}</span><b>${c.esc(w)}</b></div>`).join('')}</div>
      <p class="crm-mhd-hinweis">Käufe vom ${c.de(M.k.von)} bis ${c.de(M.k.bis)} laut Umsatzdaten der Warenwirtschaft${M.k.umsatzBis ? ` (Stand ${c.de(M.k.umsatzBis)})` : ''} – ohne Preise.</p>
      ${zeilen.length ? `<div class="crm-tabelle-rahmen"><table class="crm-tabelle crm-mhd-tabelle${bearbeiten ? ' mit-wahl' : ''}" id="mhd-tabelle">
        <thead><tr>${bearbeiten ? `<th class="crm-mhd-wahlspalte"><input type="checkbox" id="mhd-alle" aria-label="Alle auswählen"${gewaehlt && gewaehlt === zeilen.filter(({ k }) => k).length ? ' checked' : ''}></th>` : ''}<th>Kunde</th><th>Telefon</th><th class="m-aus">Vertreter</th><th>Letzter Kauf</th><th class="crm-mhd-zahl">Käufe</th><th class="crm-mhd-zahl m-aus">Ø Menge</th><th class="crm-mhd-zahl">Menge</th></tr></thead>
        <tbody>${zeilen.map(({ x, k }) => `<tr${k && !k.aktiv ? ' class="aus"' : ''}>${bearbeiten ? `<td class="crm-mhd-wahlspalte">${k ? `<input type="checkbox" data-mhd-wahl="${c.esc(k.key)}" aria-label="${c.esc(k.firma)} auswählen"${M.auswahl.has(k.key) ? ' checked' : ''}>` : ''}</td>` : ''}
          <td class="crm-mhd-kunde">${k ? c.firmaKnopf(k) : `<b>Kunde ${c.esc(x.kunde)}</b>`}<div class="gedaempft">KN ${c.esc(x.kunde)}${k ? ' · ' + c.esc([k.plz, k.ort].filter(Boolean).join(' ') || 'Ort fehlt') : ' · nicht in den Kundenstammdaten'}</div>
            ${k && k.crm.naechsterSchritt ? `<div class="gedaempft crm-mhd-schritt">${c.esc(k.crm.naechsterSchritt)}${k.crm.wiedervorlage ? ' · ' + c.de(k.crm.wiedervorlage) : ''}</div>` : ''}</td>
          <td class="crm-mhd-tel" data-label="Telefon">${k ? c.zeilen(c.telefone(k), c.telLink) : '<span class="gedaempft">—</span>'}</td>
          <td class="nw m-aus" data-label="Vertreter">${k && c.vName(k.vertreter) ? c.esc(c.vName(k.vertreter)) : '<span class="gedaempft">—</span>'}</td>
          <td class="nw" data-label="Letzter Kauf">${c.de(x.zuletzt)}</td><td class="crm-mhd-zahl" data-label="Käufe">${x.kaeufe}</td><td class="crm-mhd-zahl nw m-aus" data-label="Ø Menge">${c.esc(kg(Math.round(x.menge / x.kaeufe)))}</td><td class="crm-mhd-zahl nw" data-label="Menge">${c.esc(kg(x.menge))}</td></tr>`).join('')}</tbody></table></div>`
        : `<p class="crm-leer">${alle.length ? 'Kein Käufer für diese Auswahl.' : `Diesen Artikel hat in den letzten ${M.monate} Monaten niemand gekauft.`}</p>`}
      ${bearbeiten && zeilen.length ? `<div class="crm-mhd-fuss"><span id="mhd-gewaehlt">${gewaehlt === 1 ? '1 Kunde ausgewählt' : `${gewaehlt} Kunden ausgewählt`}</span><span class="crm-platz"></span>
        <label class="crm-mhd-datum">Wiedervorlage am<input type="date" id="mhd-datum" value="${c.esc(c.daten().heute)}"></label>
        <button type="button" class="btn primary" id="mhd-wv"${gewaehlt ? '' : ' disabled'}>Wiedervorlage anlegen</button></div>` : ''}`;
  }
  function zeichneAlles() {
    const c = M.c;
    if (M.fehler) { M.host.innerHTML = `<div class="crm-titel"><h1>MHD-Ware</h1></div><p class="crm-meldung fehler" role="alert">${c.esc(M.fehler)}</p>`; return; }
    if (!M.d) { M.host.innerHTML = '<div class="crm-titel"><h1>MHD-Ware</h1></div><p class="crm-leer">MHD-Liste wird geladen …</p>'; return; }
    const legende = Object.entries(STUFE).map(([, [cls, t]]) => `<span class="crm-mhd-marke ${cls}">${c.esc(t)}</span>`).join('');
    M.host.innerHTML = `<div class="crm-titel"><h1>MHD-Ware</h1><p>Artikel kurz vor Ablauf aus der MHD-Liste des Bestands${M.d.bestand ? ` (Bestand vom ${c.de(M.d.bestand.slice(0, 10))})` : ''} und die Kunden, die sie gekauft haben.</p></div>
      <div class="crm-mhd">
        <section class="crm-mhd-links crm-glas" aria-label="Artikel"><div class="crm-mhd-legende" aria-label="Farben wie in der MHD-Liste">${legende}</div><ul class="crm-mhd-liste" id="mhd-liste"></ul></section>
        <section class="crm-mhd-rechts-teil crm-glas" id="mhd-kaeufer" aria-live="polite"></section>
      </div>`;
    zeichneListe(); zeichneKaeufer();
  }

  /* ---------- Bedienung ---------- */
  let verbunden = false;
  function verbinden() {
    if (verbunden) return;
    verbunden = true;
    document.addEventListener('click', async (e) => {
      if (!M.host || !M.host.contains(e.target)) return;
      const a = e.target.closest('[data-mhd-artikel]');
      if (a) { M.wahl = a.dataset.mhdArtikel; M.suche = ''; zeichneListe(); kaeuferLaden(); return; }
      const mo = e.target.closest('[data-mhd-monate]');
      if (mo) { M.monate = Number(mo.dataset.mhdMonate); listeLaden(); return; }
      if (e.target.closest('#mhd-wv')) {
        const keys = kaeuferZeilen().filter(({ k }) => k && M.auswahl.has(k.key)).map(({ k }) => k.key);
        if (!keys.length) return;
        const knopf = e.target.closest('#mhd-wv'); knopf.disabled = true;
        const r = await M.c.api('crm_mhd_wiedervorlage', { artikel: M.wahl, kunden: keys, datum: M.host.querySelector('#mhd-datum').value });
        if (r.status !== 200 || !r.data.ok) { M.c.toast(M.c.fehlerText(r, 'Wiedervorlage nicht angelegt'), true); knopf.disabled = false; return; }
        r.data.kunden.forEach((k) => M.c.ersetze(k));
        M.auswahl.clear();
        M.c.toast(r.data.anzahl === 1 ? 'Wiedervorlage für 1 Kunden angelegt.' : `Wiedervorlage für ${r.data.anzahl} Kunden angelegt.`);
        M.c.neuZeichnen();
      }
    });
    document.addEventListener('change', (e) => {
      if (!M.host || !M.host.contains(e.target)) return;
      if (e.target.id === 'mhd-vertreter') { M.vertreter = e.target.value; zeichneKaeufer(); return; }
      if (e.target.id === 'mhd-regel') { M.regel = e.target.checked; zeichneKaeufer(); return; }
      if (e.target.id === 'mhd-alle') { kaeuferZeilen().forEach(({ k }) => { if (k) { if (e.target.checked) M.auswahl.add(k.key); else M.auswahl.delete(k.key); } }); zeichneKaeufer(); return; }
      const w = e.target.closest('[data-mhd-wahl]');
      if (w) {
        if (w.checked) M.auswahl.add(w.dataset.mhdWahl); else M.auswahl.delete(w.dataset.mhdWahl);
        const n = kaeuferZeilen().filter(({ k }) => k && M.auswahl.has(k.key)).length;
        M.host.querySelector('#mhd-gewaehlt').textContent = n === 1 ? '1 Kunde ausgewählt' : `${n} Kunden ausgewählt`;
        M.host.querySelector('#mhd-wv').disabled = !n;
      }
    });
    document.addEventListener('input', (e) => {
      if (e.target.id !== 'mhd-suche') return;
      M.suche = e.target.value; const pos = e.target.selectionStart;
      zeichneListe();
      const f = M.host.querySelector('#mhd-suche'); f.focus(); f.setSelectionRange(pos, pos);
    });
  }

  /* Aufruf aus crm.js: host = Reiterfläche, c = Hilfsfunktionen des CRM */
  function zeichne(host, c) {
    M.host = host; M.c = c;
    verbinden();
    if (!M.d && !M.fehler) { zeichneAlles(); listeLaden(); return; }
    zeichneAlles();
  }
  window.STAFL_CRM_MHD = { zeichne };
})();
