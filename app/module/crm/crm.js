/* STAFL-Plattform · CRM · Vertrieb
   Cockpit, Kunden, Wiedervorlagen (Anruf-Rhythmus), Pipeline, Karte und Auswertung – nach der Vertriebs-CRM-Musterdatei.
   Kunden kommen aus den Stammdaten der Verwaltung (nur lesend); das CRM ergänzt je Kunde ein Kundenblatt (Ansprechpartner,
   Segment, Phase, Wann/Erledigt, Potenzial, nächster Schritt, Notiz), Interessenten und den Aktivitätenverlauf.
   Alle Rechte prüft der Server bei jeder Aktion (GR-103) – ausgeblendete Knöpfe sind nur Anzeige.
   Kein Inline-Skript (Content-Security-Policy), keine fremden Kartendienste: die Karte zeichnet die Seite selbst
   (Umrisse ../../assets/karte.json, PLZ-Mittelpunkte plz.json). */
'use strict';
(() => {
  const API = '../../api/';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (n) => `<svg class="i" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const OFFEN_PHASEN = ['Interessent', 'Erstkontakt', 'Muster/Probe', 'Angebot', 'Verhandlung'];
  const TAGE = ['montag', 'dienstag', 'mittwoch', 'donnerstag', 'freitag', 'samstag', 'sonntag'];
  const SEITE = 200;   // Zeilen je Abschnitt in den Tabellen („Weitere anzeigen“)
  let csrf = '';
  const S = {
    d: null, tab: 'cockpit', byKey: new Map(),
    kunden: { q: '', segment: '', vertreter: '', phase: '', aktiv: 'ja', n: SEITE },
    wv: { q: '', vertreter: '', termin: 'alle', wann: [], n: SEITE, reihenfolge: null },
    karte: { ja: true, nein: false },
  };

  async function api(action, body, query = '') {
    let res;
    try {
      res = await fetch(API + '?action=' + action + query, {
        method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
        headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf } : {}, body: body ? JSON.stringify(body) : undefined,
      });
    } catch { return { status: 0, data: {}, json: false }; }   // keine Verbindung: Aufrufer zeigen „Keine Verbindung zum Server.“
    let data = null;
    try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
    return { status: res.status, data: data || {}, json: data !== null };
  }
  const fehlerText = (r, fallback) => (r.data && r.data.error) || (r.status === 0 ? 'Keine Verbindung zum Server.' : `${fallback} (${r.status}).`);
  let toastZeit = 0;
  function toast(text, fehler = false) {
    const t = $('#crm-toast');
    t.textContent = text; t.className = 'crm-toast zeigen' + (fehler ? ' fehler' : '');
    clearTimeout(toastZeit); toastZeit = setTimeout(() => { t.className = 'crm-toast'; }, fehler ? 4200 : 2200);
  }

  /* ---------- Datum, Zahlen, Namen ---------- */
  const de = (s) => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : '—';
  const deZeit = (s) => { const d = new Date(s); return isNaN(d) ? '' : d.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' }); };
  const geld = (n) => n ? new Intl.NumberFormat('de-DE', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 }).format(n) : '—';
  const zahl = (n) => (n ?? '') === '' || n === null ? '' : String(n).replace('.', ',');
  const heute = () => S.d.heute;
  const tageBis = (iso) => { if (!iso) return Infinity; const a = new Date(iso + 'T12:00:00'), b = new Date(heute() + 'T12:00:00'); return Math.round((a - b) / 86400000); };
  const vName = (nr) => { if (!nr) return ''; const v = S.d.vertreter.find((x) => x.nr === nr); return v ? v.name : nr; };
  const wert = (k) => (k.crm.potenzialKg || 0) * (k.crm.preisKg || 0);
  const db = (k) => (k.crm.potenzialKg || 0) * (k.crm.dbKg || 0);
  const initialen = (name) => { const t = String(name || '').trim().split(/[\s.\-_]+/).filter(Boolean); return (t.length > 1 ? t[0][0] + t[1][0] : (t[0] || '?').slice(0, 2)).toLocaleUpperCase('de-DE'); };
  const darf = () => !!(S.d && S.d.rechte.bearbeiten);
  /* Alle Ansprechpartner (Stammdaten + Kundenblatt) und Telefonnummern eines Kunden */
  function namen(k) {
    const n = [...String(k.ansprechpartner || '').split(/[,;\n]+/), ...k.crm.kontakte.map((p) => p.name + (p.funktion ? ` (${p.funktion})` : ''))].map((x) => x.trim()).filter(Boolean);
    return [...new Set(n)];
  }
  function telefone(k) { return [...new Set([k.telefon, ...k.crm.kontakte.map((p) => p.telefon)].map((x) => String(x || '').trim()).filter(Boolean))]; }
  const telLink = (n) => `<a href="tel:${esc(n.replace(/[^\d+]/g, ''))}">${esc(n)}</a>`;
  const zeilen = (liste, f = esc) => liste.length ? `<div class="zeilen">${liste.map((x) => `<div>${f(x)}</div>`).join('')}</div>` : '<span class="gedaempft">—</span>';
  const firmaKnopf = (k) => `<button type="button" class="crm-firma" data-oeffnen="${esc(k.key)}">${esc(k.firma || 'Ohne Firmenname')}</button>`;
  const opts = (liste, wert_, leer = '') => (leer !== null ? `<option value="">${esc(leer)}</option>` : '') + liste.map((v) => `<option value="${esc(v)}"${v === wert_ ? ' selected' : ''}>${esc(v)}</option>`).join('');
  const vOpts = (wert_, leer = 'Alle Vertreter') => `<option value="">${esc(leer)}</option>` + S.d.vertreter.map((v) => `<option value="${esc(v.nr)}"${v.nr === wert_ ? ' selected' : ''}>${esc(v.name)}</option>`).join('');

  /* Anruf-Rhythmus: in wie vielen Tagen ist der nächste Termin? (wöchentlich, 14-tägig gerade/ungerade KW; „Monatlich“ ohne Tag) */
  function kw(d) { const x = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate())); x.setUTCDate(x.getUTCDate() + 4 - (x.getUTCDay() || 7)); const y = new Date(Date.UTC(x.getUTCFullYear(), 0, 1)); return Math.ceil(((x - y) / 86400000 + 1) / 7); }
  function naechsterAnruf(r) {
    const v = String(r || '').toLowerCase(), tag = TAGE.findIndex((t) => v.includes(t));
    if (tag < 0) return Infinity;
    const h = new Date(heute() + 'T12:00:00'), delta = (tag - ((h.getDay() + 6) % 7) + 7) % 7;
    const gerade = v.includes('ungerade') ? 1 : (v.includes('gerade') ? 0 : -1);
    for (let o = delta; o <= delta + 14; o += 7) { const d = new Date(h); d.setDate(h.getDate() + o); if (gerade < 0 || kw(d) % 2 === gerade) return o; }
    return Infinity;
  }
  const heuteAnrufen = (k) => k.crm.anrufAktiv && (naechsterAnruf(k.crm.rhythmus1) === 0 || naechsterAnruf(k.crm.rhythmus2) === 0);
  const faellig = () => S.d.kunden.filter((k) => k.crm.naechsterSchritt && k.crm.wiedervorlage && tageBis(k.crm.wiedervorlage) <= 0);

  /* ---------- Kopf, Anmeldung, Thema ---------- */
  function fehler(text) { $('#crm-login').hidden = true; $('#crm-app').hidden = true; $('#crm-err').hidden = false; $('#crm-err').textContent = text; }
  function zeigeAnmeldung(ziel) {
    if (ziel) $('#crm-login a').setAttribute('href', ziel);
    $('#crm-login').hidden = false; $('#crm-app').hidden = true; $('#crm-user').hidden = true;
  }
  // Im Echtbetrieb führt das Logo zum Dashboard unter der zentralen Anmeldung, sonst zum Dashboard dieses Servers
  const ECHT = /(^|\.)dashboard-stafl\.de$/.test(location.hostname);
  if (ECHT) $('#crm-zurueck').href = 'https://dashboard-stafl.de/';
  const verwaltungKunden = () => (ECHT ? 'https://verwaltung.dashboard-stafl.de/admin/' : '../../admin/') + '#kunden';
  const dunkel = () => document.documentElement.getAttribute('data-theme') === 'dark'
    || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  function themaKnopf() {
    const d = dunkel();
    $('#crm-theme').innerHTML = icon(d ? 'sun' : 'moon');
    $('#crm-theme').setAttribute('aria-label', d ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }
  $('#crm-theme').addEventListener('click', () => {
    const neu = dunkel() ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', neu);
    try { localStorage.setItem('wochenangebot.theme', JSON.stringify(neu)); } catch { /* ohne Speicher */ }
    themaKnopf();
  });

  /* ---------- Reiter ---------- */
  function zeigeTab(tab) {
    S.tab = tab;
    for (const b of $$('#crm-tabs button')) b.setAttribute('aria-selected', String(b.dataset.tab === tab));
    for (const p of $$('.crm-tab')) p.hidden = p.id !== 'tab-' + tab;
    try { history.replaceState(null, '', '#' + tab); } catch { /* egal */ }
    zeichne();
  }
  $('#crm-tabs').addEventListener('click', (e) => { const b = e.target.closest('button[data-tab]'); if (b) zeigeTab(b.dataset.tab); });
  function zeichne() {
    const n = faellig().length;
    $('#crm-faellig').hidden = !n; $('#crm-faellig').textContent = n || '';
    ({ cockpit, kunden, wiedervorlagen, pipeline, karte, auswertung })[S.tab]();
  }

  /* ---------- Daten ---------- */
  function setzeDaten(d) {
    S.d = d;
    S.byKey = new Map(d.kunden.map((k) => [k.key, k]));
    $('#crm-export').hidden = !d.rechte.exportieren;
  }
  /* Eintrag nach dem Speichern ersetzen (Server liefert den ganzen Eintrag zurück) */
  function ersetze(k) {
    if (!k) return;
    const i = S.d.kunden.findIndex((x) => x.key === k.key);
    if (i >= 0) S.d.kunden[i] = k; else S.d.kunden.push(k);
    S.byKey.set(k.key, k);
  }
  async function speichereFelder(key, felder) {
    const r = await api('crm_kunde_save', { key, felder });
    if (r.status !== 200) { toast(fehlerText(r, 'Speichern fehlgeschlagen'), true); return null; }
    ersetze(r.data.kunde);
    return r.data.kunde;
  }

  /* ---------- Cockpit ---------- */
  function kpi(titel, w, zusatz = '', cls = '') { return `<div class="crm-wert crm-glas ${cls}"><span>${esc(titel)}</span><b>${esc(w)}</b>${zusatz ? `<small>${esc(zusatz)}</small>` : ''}</div>`; }
  function cockpit() {
    const K = S.d.kunden, aktiv = K.filter((k) => k.aktiv && k.art === 'kunde').length;
    const offen = K.filter((k) => OFFEN_PHASEN.includes(k.crm.phase) && k.aktiv);
    const wv = K.filter((k) => k.crm.naechsterSchritt && k.crm.wiedervorlage).sort((a, b) => a.crm.wiedervorlage.localeCompare(b.crm.wiedervorlage));
    const anrufe = K.filter((k) => heuteAnrufen(k) && k.crm.anrufStatus !== 'Erledigt');
    const nInt = K.filter((k) => k.art === 'interessent').length;
    const balken = S.d.phasen.slice(0, 6).map((p) => [p, K.filter((k) => k.crm.phase === p).length]);
    const max = Math.max(1, ...balken.map((b) => b[1]));
    $('#tab-cockpit').innerHTML = `
      <div class="crm-titel"><h1>Vertrieb im Überblick</h1><p>Kunden aus den Stammdaten, Wiedervorlagen, Aktivitäten und Verkaufschancen.</p></div>
      <div class="crm-kpis">
        ${kpi('Aktive Kunden', aktiv, `${K.length - nInt} Kunden in den Stammdaten${nInt ? ` · ${nInt} Interessenten` : ''}`)}
        ${kpi('Heute anrufen', anrufe.length, 'laut „Wann“, noch nicht erledigt', anrufe.length ? 'akzent' : '')}
        ${kpi('Wiedervorlagen fällig', faellig().length, `${wv.length} terminiert`, faellig().length ? 'warn' : '')}
        ${kpi('Offene Chancen', offen.length, 'Interessent bis Verhandlung')}
        ${kpi('DB-Potenzial', geld(offen.reduce((n, k) => n + db(k), 0)), 'kg × DB/kg der offenen Chancen')}
      </div>
      <div class="crm-raster">
        <section class="crm-karte crm-glas"><div class="crm-karte-kopf"><h3>Als Nächstes dran</h3><button type="button" class="btn" data-gehe="wiedervorlagen">Alle Wiedervorlagen</button></div>
          ${wv.length ? `<ul class="crm-zeilen">${wv.slice(0, 8).map((k) => `<li><div class="was"><b>${esc(k.crm.naechsterSchritt)}</b>${firmaKnopf(k)}<small>${esc(vName(k.vertreter) || 'ohne Vertreter')}</small></div><span class="wann${tageBis(k.crm.wiedervorlage) < 0 ? ' ueber' : ''}">${de(k.crm.wiedervorlage)}</span></li>`).join('')}</ul>`
            : '<p class="crm-leer">Noch keine Wiedervorlagen. Im Kundenblatt den nächsten Schritt mit Datum planen.</p>'}
        </section>
        <section class="crm-karte crm-glas"><div class="crm-karte-kopf"><h3>Heute anrufen</h3><button type="button" class="btn" data-gehe="wiedervorlagen" data-termin="heute">Liste öffnen</button></div>
          ${anrufe.length ? `<ul class="crm-zeilen">${anrufe.slice(0, 8).map((k) => `<li><div class="was">${firmaKnopf(k)}<small>${esc(namen(k).slice(0, 2).join(', ') || '—')}</small></div><span class="wann">${telefone(k)[0] ? telLink(telefone(k)[0]) : ''}</span></li>`).join('')}</ul>${anrufe.length > 8 ? `<p class="crm-klein">und ${anrufe.length - 8} weitere</p>` : ''}`
            : '<p class="crm-leer">Für heute stehen keine offenen Anrufe an.</p>'}
        </section>
        <section class="crm-karte crm-glas"><h3>Verkaufsprozess</h3>
          ${balken.map(([p, n]) => `<div class="crm-balken"><span>${esc(p)}</span><div class="spur"><i style="width:${n ? Math.max(3, n / max * 100) : 0}%"></i></div><b>${n}</b></div>`).join('')}
          <p class="crm-klein">Kunden aus den Stammdaten starten als Bestandskunden, neue Interessenten als Interessent. Die Phase lässt sich im Kundenblatt oder in der Pipeline ändern.</p>
        </section>
        <section class="crm-karte crm-glas"><h3>Letzte Aktivitäten</h3>
          ${S.d.letzte.length ? `<ul class="crm-zeilen">${S.d.letzte.slice(0, 6).map((a) => `<li><div class="was">${S.byKey.has(a.key) ? `<button type="button" class="crm-firma" data-oeffnen="${esc(a.key)}">${esc(a.art)} · ${esc(S.byKey.get(a.key).firma)}</button>` : `<b>${esc(a.art)} · ${esc(a.firma)}</b>`}<small>${esc(deZeit(a.at))} · ${esc(a.von)}${a.notiz ? ' · ' + esc(a.notiz) : ''}</small></div></li>`).join('')}</ul>`
            : '<p class="crm-leer">Der Verlauf beginnt mit dem ersten protokollierten Telefonat, Besuch oder Angebot.</p>'}
        </section>
      </div>`;
  }

  /* ---------- Kunden ---------- */
  function kundenListe() {
    const f = S.kunden, q = f.q.toLocaleLowerCase('de').trim();
    return S.d.kunden.filter((k) => {
      if (f.aktiv === 'ja' && !k.aktiv) return false;
      if (f.aktiv === 'nein' && k.aktiv) return false;
      if (f.segment && k.crm.segment !== f.segment) return false;
      if (f.phase && k.crm.phase !== f.phase) return false;
      if (f.vertreter && k.vertreter !== f.vertreter && k.vertreter2 !== f.vertreter) return false;
      if (!q) return true;
      if (!k._suche) k._suche = [k.firma, k.nr, k.ort, k.plz, k.email, k.telefon, k.ansprechpartner, vName(k.vertreter), vName(k.vertreter2),
        ...k.crm.kontakte.flatMap((p) => [p.name, p.funktion, p.telefon, p.email])].join(' ').toLocaleLowerCase('de');
      return k._suche.includes(q);
    });
  }
  function kunden() {
    const f = S.kunden, liste = kundenListe(), b = darf();
    const host = $('#tab-kunden');
    const fokus = document.activeElement && document.activeElement.id === 'k-suche' ? document.activeElement.selectionStart : null;
    host.innerHTML = `
      <div class="crm-titel"><h1>Kunden</h1><p>${liste.length} von ${S.d.kunden.length} · Stammdaten aus der Verwaltung, Kundenblatt im CRM</p>
        ${b ? `<button type="button" class="btn primary" data-neu-interessent>${icon('plus')}Interessent</button>` : ''}</div>
      <div class="crm-leiste">
        <label class="crm-suche"><span class="sr-only">Suchen</span>${icon('search')}<input type="search" id="k-suche" value="${esc(f.q)}" placeholder="Firma, Kundennummer, Ort, Ansprechpartner, Telefon …"></label>
        <select id="k-aktiv" aria-label="Aktiv"><option value="ja"${f.aktiv === 'ja' ? ' selected' : ''}>Nur aktive</option><option value=""${f.aktiv === '' ? ' selected' : ''}>Aktive und inaktive</option><option value="nein"${f.aktiv === 'nein' ? ' selected' : ''}>Nur inaktive</option></select>
        <select id="k-segment" aria-label="Segment">${opts(S.d.segmente, f.segment, 'Alle Segmente')}</select>
        <select id="k-phase" aria-label="Phase">${opts(S.d.phasen, f.phase, 'Alle Phasen')}</select>
        <select id="k-vertreter" aria-label="Vertreter">${vOpts(f.vertreter)}</select>
      </div>
      <div class="crm-tabelle-rahmen crm-glas"><table class="crm-tabelle" id="k-tabelle">
        <thead><tr><th>Kunde</th><th class="m-aus">Telefon</th><th class="m-aus">Ansprechpartner</th><th>Vertreter</th><th>Segment</th><th>Phase</th><th>Nächster Schritt</th></tr></thead>
        <tbody>${liste.slice(0, f.n).map((k) => `<tr class="${k.aktiv ? '' : 'aus'}">
          <td>${firmaKnopf(k)} ${k.art === 'interessent' ? '<span class="crm-pille info">Interessent</span>' : ''}<div class="gedaempft">${k.nr ? 'KN ' + esc(k.nr) + ' · ' : ''}${esc([k.plz, k.ort].filter(Boolean).join(' ') || 'Ort fehlt')}</div></td>
          <td class="m-aus">${zeilen(telefone(k), telLink)}</td>
          <td class="m-aus">${zeilen(namen(k))}</td>
          <td class="nw">${vName(k.vertreter) ? esc(vName(k.vertreter)) : '<span class="gedaempft">—</span>'}${k.vertreter2 ? `<div class="gedaempft">${esc(vName(k.vertreter2))}</div>` : ''}</td>
          <td>${b ? `<select data-feld="segment" data-key="${esc(k.key)}" aria-label="Segment ${esc(k.firma)}">${opts(S.d.segmente, k.crm.segment, null)}</select>` : esc(k.crm.segment)}</td>
          <td>${b ? `<select data-feld="phase" data-key="${esc(k.key)}" aria-label="Phase ${esc(k.firma)}">${opts(S.d.phasen, k.crm.phase, null)}</select>` : esc(k.crm.phase)}</td>
          <td>${k.crm.naechsterSchritt ? `<span class="${tageBis(k.crm.wiedervorlage) < 0 ? 'crm-ueber' : ''}">${esc(k.crm.naechsterSchritt)}</span><div class="gedaempft">${k.crm.wiedervorlage ? de(k.crm.wiedervorlage) : ''}</div>` : '<span class="gedaempft">—</span>'}</td>
        </tr>`).join('') || '<tr><td colspan="7" class="crm-leer">Keine Kunden gefunden.</td></tr>'}</tbody></table>
        ${liste.length > f.n ? `<div class="crm-mehr"><button type="button" class="btn" data-mehr="kunden">Weitere ${Math.min(SEITE, liste.length - f.n)} anzeigen (${liste.length - f.n} übrig)</button></div>` : ''}
      </div>`;
    if (fokus !== null) { const i = $('#k-suche'); i.focus(); i.setSelectionRange(fokus, fokus); }
  }
  let suchZeit = 0;
  document.addEventListener('input', (e) => {
    if (e.target.id === 'k-suche') { S.kunden.q = e.target.value; S.kunden.n = SEITE; clearTimeout(suchZeit); suchZeit = setTimeout(kunden, 150); }
    if (e.target.id === 'wv-suche') { S.wv.q = e.target.value; S.wv.n = SEITE; clearTimeout(suchZeit); suchZeit = setTimeout(() => wiedervorlagen(true), 150); }
  });

  /* ---------- Wiedervorlagen (Anrufliste) ---------- */
  function wvReihenfolge() {
    // Einmal je Aufruf festgelegt, damit Zeilen beim Bearbeiten nicht springen: aktiv vor inaktiv, offen vor erledigt, nächster Anruf zuerst
    const sort = S.d.kunden.slice().sort((a, b) => (a.crm.anrufAktiv === b.crm.anrufAktiv ? 0 : a.crm.anrufAktiv ? -1 : 1)
      || ((a.crm.anrufStatus === 'Erledigt') - (b.crm.anrufStatus === 'Erledigt'))
      || (naechsterAnruf(a.crm.rhythmus1) - naechsterAnruf(b.crm.rhythmus1)) || (naechsterAnruf(a.crm.rhythmus2) - naechsterAnruf(b.crm.rhythmus2))
      || a.firma.localeCompare(b.firma, 'de'));
    S.wv.reihenfolge = sort.map((k) => k.key);
  }
  function wvListe() {
    if (!S.wv.reihenfolge) wvReihenfolge();
    const bekannt = new Set(S.wv.reihenfolge);
    for (const k of S.d.kunden) if (!bekannt.has(k.key)) S.wv.reihenfolge.push(k.key);
    const f = S.wv, q = f.q.toLocaleLowerCase('de').trim();
    return S.wv.reihenfolge.map((key) => S.byKey.get(key)).filter((k) => {
      if (!k) return false;
      if (f.vertreter && k.vertreter !== f.vertreter && k.vertreter2 !== f.vertreter) return false;
      if (f.wann.length && !f.wann.includes(k.crm.rhythmus1 || '__ohne__')) return false;
      const t = tageBis(k.crm.wiedervorlage), hat = !!k.crm.wiedervorlage;
      if (f.termin === 'heute' && !heuteAnrufen(k)) return false;
      if (f.termin === 'offen' && !(k.crm.anrufAktiv && k.crm.anrufStatus !== 'Erledigt' && (k.crm.rhythmus1 || k.crm.rhythmus2))) return false;
      if (f.termin === 'ueber' && !(hat && t < 0)) return false;
      if (f.termin === 'wv-heute' && !(hat && t === 0)) return false;
      if (f.termin === 'kuenftig' && !(hat && t > 0)) return false;
      if (!q) return true;
      return [k.firma, k.nr, k.ort, ...namen(k), ...telefone(k)].join(' ').toLocaleLowerCase('de').includes(q);
    });
  }
  function wiedervorlagen(nurTabelle = false) {
    const f = S.wv, b = darf(), liste = wvListe();
    const rh = ['', ...S.d.rhythmen];
    const alleWann = [...new Set(S.d.kunden.map((k) => k.crm.rhythmus1 || '__ohne__'))].sort((x, y) => (x === '__ohne__' ? -1 : y === '__ohne__' ? 1 : x.localeCompare(y, 'de')));
    const sel = (k, feld, liste_, aria, cls = '') => b ? `<select data-feld="${feld}" data-key="${esc(k.key)}" class="${cls}" aria-label="${esc(aria)} ${esc(k.firma)}">${liste_}</select>` : '';
    const zeile = (k) => {
      const st = k.crm.anrufStatus, ak = k.crm.anrufAktiv ? 'Ja' : 'Nein';
      return `<tr class="${k.crm.anrufAktiv ? '' : 'aus'}">
        <td>${b ? sel(k, 'anrufAktiv', `<option value="Ja"${ak === 'Ja' ? ' selected' : ''}>Ja</option><option value="Nein"${ak === 'Nein' ? ' selected' : ''}>Nein</option>`, 'Aktiv', 'st-' + ak) : esc(ak)}</td>
        <td class="kunde">${firmaKnopf(k)}${k.art === 'interessent' ? ' <span class="crm-pille info">Interessent</span>' : ''}${k.nr ? `<div class="gedaempft">KN ${esc(k.nr)}</div>` : ''}${k.crm.naechsterSchritt ? `<div class="gedaempft${tageBis(k.crm.wiedervorlage) < 0 ? ' crm-ueber' : ''}">${esc(k.crm.naechsterSchritt)}${k.crm.wiedervorlage ? ' · ' + de(k.crm.wiedervorlage) : ''}</div>` : ''}</td>
        <td class="m-aus">${zeilen(namen(k))}</td>
        <td>${zeilen(telefone(k), telLink)}</td>
        <td class="m-aus l-aus">${esc(k.angebote.join(', ') || '—')}</td>
        <td class="nw m-aus">${esc(vName(k.vertreter) || '—')}${k.vertreter2 ? `<div class="gedaempft">${esc(vName(k.vertreter2))}</div>` : ''}</td>
        <td class="wann">${b ? sel(k, 'rhythmus1', opts(rh.slice(1), k.crm.rhythmus1, '— Wann —'), 'Wann') + sel(k, 'rhythmus2', opts(rh.slice(1), k.crm.rhythmus2, '— Wann 2 —'), 'Wann 2')
          : esc(k.crm.rhythmus1 || '—') + (k.crm.rhythmus2 ? `<div class="gedaempft">${esc(k.crm.rhythmus2)}</div>` : '')}</td>
        <td>${b ? sel(k, 'anrufStatus', opts(S.d.anruf, st, null), 'Erledigt', 'st-' + st) : `<span class="crm-pille ${st === 'Erledigt' ? 'ok' : st === 'Nochmal' ? 'warn' : 'fehler'}">${esc(st)}</span>`}</td>
      </tr>`;
    };
    const tabelle = `<table class="crm-tabelle" id="wv-tabelle"><thead><tr><th>Aktiv</th><th>Kunde</th><th class="m-aus">Ansprechpartner</th><th>Telefon</th><th class="m-aus l-aus">Angebot</th><th class="m-aus">Vertreter</th><th>Wann / Wann 2</th><th>Erledigt</th></tr></thead>
      <tbody>${liste.slice(0, f.n).map(zeile).join('') || '<tr><td colspan="8" class="crm-leer">Keine Kunden für diese Auswahl.</td></tr>'}</tbody></table>
      ${liste.length > f.n ? `<div class="crm-mehr"><button type="button" class="btn" data-mehr="wv">Weitere ${Math.min(SEITE, liste.length - f.n)} anzeigen (${liste.length - f.n} übrig)</button></div>` : ''}`;
    if (nurTabelle && $('#wv-rahmen')) { $('#wv-rahmen').innerHTML = tabelle; $('#wv-anzahl').textContent = `${liste.length} von ${S.d.kunden.length} Kunden`; return; }
    const offenDetails = $('#wv-wann') && $('#wv-wann').open;
    $('#tab-wiedervorlagen').innerHTML = `
      <div class="crm-titel"><h1>Wiedervorlagen</h1><p id="wv-anzahl">${liste.length} von ${S.d.kunden.length} Kunden</p></div>
      <div class="crm-leiste">
        <label class="crm-suche"><span class="sr-only">Suchen</span>${icon('search')}<input type="search" id="wv-suche" value="${esc(f.q)}" placeholder="Firma, Ansprechpartner, Telefon …"></label>
        <select id="wv-termin" aria-label="Termin">
          ${[['alle', 'Alle Kunden'], ['heute', 'Heute anrufen'], ['offen', 'Anruf offen (mit Rhythmus)'], ['ueber', 'Wiedervorlage überfällig'], ['wv-heute', 'Wiedervorlage heute'], ['kuenftig', 'Wiedervorlage künftig']]
            .map(([v, l]) => `<option value="${v}"${f.termin === v ? ' selected' : ''}>${l}</option>`).join('')}
        </select>
        <details class="crm-mehrfach" id="wv-wann"${offenDetails ? ' open' : ''}><summary>${f.wann.length ? `Wann: ${f.wann.length} gewählt` : 'Wann: alle'}</summary>
          <div class="optionen"><button type="button" class="btn" id="wv-wann-alle">Alle Wann-Werte zeigen</button>
          ${alleWann.map((w) => `<label><input type="checkbox" data-wann value="${esc(w)}"${f.wann.includes(w) ? ' checked' : ''}><span>${w === '__ohne__' ? '— nicht festgelegt —' : esc(w)}</span></label>`).join('')}</div></details>
        <select id="wv-vertreter" aria-label="Vertreter">${vOpts(f.vertreter)}</select>
        ${b ? '<button type="button" class="btn" id="wv-neu-sortieren" title="Liste neu nach dem nächsten Anruf ordnen">Neu ordnen</button>' : ''}
      </div>
      <div class="crm-tabelle-rahmen crm-glas" id="wv-rahmen">${tabelle}</div>
      <p class="crm-klein" style="margin-top:10px">Änderungen werden sofort gespeichert. Die Reihenfolge bleibt beim Bearbeiten stehen – „Neu ordnen“ sortiert nach dem nächsten Anruf.</p>`;
  }

  /* ---------- Pipeline ---------- */
  function pipeline() {
    const b = darf(), phasen = S.d.phasen.slice(0, 6);
    const spalten = phasen.map((p) => {
      const l = S.d.kunden.filter((k) => k.crm.phase === p && k.aktiv).sort((x, y) => db(y) - db(x) || x.firma.localeCompare(y.firma, 'de'));
      const summe = l.reduce((n, k) => n + db(k), 0);
      return `<section class="crm-spalte crm-glas" data-phase="${esc(p)}"><div class="crm-spalte-kopf"><span>${esc(p)}</span><span class="crm-pille">${l.length}</span></div>
        ${summe ? `<small class="crm-gedaempft">DB-Chance ${geld(summe)}</small>` : ''}
        ${l.slice(0, 30).map((k) => `<div class="crm-deal">${firmaKnopf(k)}<small>${esc(k.crm.segment)} · ${esc(vName(k.vertreter) || 'ohne Vertreter')}</small>
          ${wert(k) || db(k) ? `<small>Wert ${geld(wert(k))} · DB ${geld(db(k))}</small>` : ''}
          ${b ? `<select data-feld="phase" data-key="${esc(k.key)}" aria-label="Phase ${esc(k.firma)}">${opts(S.d.phasen, k.crm.phase, null)}</select>` : ''}</div>`).join('') || '<p class="crm-leer">Keine Einträge</p>'}
        ${l.length > 30 ? `<p class="crm-klein">und ${l.length - 30} weitere – in „Kunden“ nach Phase filtern</p>` : ''}</section>`;
    }).join('');
    $('#tab-pipeline').innerHTML = `<div class="crm-titel"><h1>Verkaufs-Pipeline</h1><p>Aktive Kunden und Interessenten nach Phase. Potenzial (kg, €/kg, DB/kg) im Kundenblatt eintragen.</p>
      ${b ? `<button type="button" class="btn primary" data-neu-interessent>${icon('plus')}Interessent</button>` : ''}</div><div class="crm-board">${spalten}</div>
      <p class="crm-klein" style="margin-top:12px">Bestandskunden werden nicht automatisch als Chance gezählt – nur die Phasen Interessent bis Verhandlung.</p>`;
  }

  /* ---------- Karte (eigene Zeichnung, Web-Mercator wie die Auswertung der Verwaltung) ---------- */
  const px = (lon) => (lon + 180) * 100;
  const py = (lat) => { const l = Math.max(-85, Math.min(85, lat)) * Math.PI / 180; return (180 - Math.log(Math.tan(Math.PI / 4 + l / 2)) * 180 / Math.PI) * 100; };
  const STAEDTE = [['Hamburg', 53.55, 10.0], ['Berlin', 52.52, 13.405], ['München', 48.137, 11.575], ['Köln', 50.937, 6.96], ['Frankfurt', 50.11, 8.682],
    ['Hannover', 52.375, 9.732], ['Bremen', 53.079, 8.802], ['Kiel', 54.323, 10.123], ['Leipzig', 51.34, 12.375], ['Stuttgart', 48.776, 9.177], ['Nürnberg', 49.452, 11.077], ['Dortmund', 51.514, 7.468]];
  let geo = null, geoLaden = null, vb = null, voll = null;
  function ladeGeo() {
    if (geo) return Promise.resolve(geo);
    if (!geoLaden) {
      geoLaden = Promise.all([fetch('../../assets/karte.json').then((r) => { if (!r.ok) throw new Error('Karte nicht geladen'); return r.json(); }),
        fetch('plz.json').then((r) => { if (!r.ok) throw new Error('Postleitzahlen nicht geladen'); return r.json(); })])
        .then(([k, p]) => { geo = { karte: k, plz: p.plz }; return geo; }).finally(() => { geoLaden = null; });
    }
    return geoLaden;
  }
  /* PLZ eines Kunden für die Karte: nur Deutschland (5-stellig; 4-stellig ohne Land = führende 0 fehlt) */
  function kartenPlz(k) {
    const land = String(k.land || '').trim().toLowerCase(), p = String(k.plz || '').replace(/\D/g, '');
    if (land && !['d', 'de', 'deu', 'deutschland', 'germany'].includes(land)) return '';
    if (p.length === 5) return p;
    if (p.length === 4 && !land) return '0' + p;
    return '';
  }
  function kartenPunkte() {
    const m = new Map(); let ohne = 0;
    for (const k of S.d.kunden) {
      if ((k.aktiv && !S.karte.ja) || (!k.aktiv && !S.karte.nein)) continue;
      const p = kartenPlz(k), c = p && geo.plz[p];
      if (!c) { ohne++; continue; }
      if (!m.has(p)) m.set(p, { plz: p, x: px(c[1] / 1000), y: py(c[0] / 1000), liste: [] });
      m.get(p).liste.push(k);
    }
    return { punkte: [...m.values()].sort((a, b) => b.liste.length - a.liste.length), ohne };
  }
  function seitenVerhaeltnis(b) {
    const svg = $('#km-svg'); const r = svg && svg.clientWidth > 0 && svg.clientHeight > 0 ? svg.clientWidth / svg.clientHeight : 1.4;
    let [x, y, w, h] = b;
    if (w / h < r) { const nw = h * r; x -= (nw - w) / 2; w = nw; } else { const nh = w / r; y -= (nh - h) / 2; h = nh; }
    return [x, y, w, h];
  }
  async function karte() {
    const host = $('#tab-karte');
    if (!geo) host.innerHTML = '<div class="crm-titel"><h1>Karte</h1><p>Karte wird geladen …</p></div>';
    try { await ladeGeo(); } catch (e) { host.innerHTML = `<p class="crm-fehler">${esc(e.message)}</p>`; return; }
    if (S.tab !== 'karte') return;
    const { punkte, ohne } = kartenPunkte();
    const n = punkte.reduce((s, p) => s + p.liste.length, 0);
    host.innerHTML = `
      <div class="crm-titel"><h1>Kunden auf der Karte</h1><p>${n} Kunden an ${punkte.length} Postleitzahlen${ohne ? ` · ${ohne} ohne Kartenpunkt (Ausland oder PLZ fehlt)` : ''}</p></div>
      <div class="crm-leiste"><label class="crm-check"><input type="checkbox" id="km-ja"${S.karte.ja ? ' checked' : ''}> aktive Kunden</label><label class="crm-check"><input type="checkbox" id="km-nein"${S.karte.nein ? ' checked' : ''}> inaktive Kunden</label></div>
      <section class="crm-karte-flaeche crm-glas" aria-label="Karte der Kunden">
        <svg id="km-svg" role="img" aria-label="Karte: ${punkte.length} Orte mit Kunden"><g id="km-land">${geo.karte.laender.map((d) => `<path d="${d}"/>`).join('')}</g><g id="km-ref"></g><g id="km-pts"></g></svg>
        <div class="crm-zoom" role="group" aria-label="Kartenausschnitt">
          <button type="button" class="crm-rund" data-km="in" aria-label="Vergrößern">${icon('plus')}</button>
          <button type="button" class="crm-rund" data-km="aus" aria-label="Verkleinern">${icon('minus')}</button>
          <button type="button" class="crm-rund" data-km="alle" aria-label="Alle Kunden zeigen">${icon('fit')}</button>
        </div>
        <div class="crm-pop" id="km-pop" hidden></div>
      </section>
      <p class="crm-klein" style="margin-top:10px">Punkte sind Mittelpunkte der Postleitzahl, keine Hausadressen. Karte: Natural Earth; Postleitzahlen: WZB plz_geocoord (Apache 2.0).</p>`;
    $('#km-pts').innerHTML = punkte.map((p) => {
      const aus = p.liste.every((k) => !k.aktiv);
      return `<g class="pt${aus ? ' aus' : ''}" data-plz="${p.plz}" tabindex="0" role="button" aria-label="${esc(p.plz)} ${esc(p.liste[0].ort)}: ${p.liste.length} Kunden"><title>${esc(p.plz)} ${esc(p.liste[0].ort)} – ${esc(p.liste.slice(0, 4).map((k) => k.firma).join(', '))}${p.liste.length > 4 ? ' …' : ''}</title><circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" data-n="${p.liste.length}"/>${p.liste.length > 1 ? `<text x="${p.x.toFixed(1)}" y="${p.y.toFixed(1)}">${p.liste.length > 99 ? '99+' : p.liste.length}</text>` : ''}</g>`;
    }).join('');
    $('#km-pts')._punkte = punkte;
    voll = seitenVerhaeltnis([px(5.2), py(55.4), px(15.8) - px(5.2), py(47) - py(55.4)]);
    vb = voll.slice();
    if (punkte.length) {
      const xs = punkte.map((p) => p.x), ys = punkte.map((p) => p.y);
      let x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys);
      const minW = 500; if (x1 - x0 < minW) { const c = (x0 + x1) / 2; x0 = c - minW / 2; x1 = c + minW / 2; } if (y1 - y0 < minW * .6) { const c = (y0 + y1) / 2; y0 = c - minW * .3; y1 = c + minW * .3; }
      const pw = (x1 - x0) * .18, ph = (y1 - y0) * .18; vb = seitenVerhaeltnis([x0 - pw, y0 - ph, x1 - x0 + 2 * pw, y1 - y0 + 2 * ph]);
    }
    kartenAusschnitt();
  }
  function kartenAusschnitt() {
    const svg = $('#km-svg'); if (!svg || !vb) return;
    const maxW = (voll ? voll[2] : 1100) * 2.2;
    if (vb[2] > maxW) { const f = maxW / vb[2]; vb = [vb[0] + vb[2] * (1 - f) / 2, vb[1] + vb[3] * (1 - f) / 2, vb[2] * f, vb[3] * f]; }
    if (vb[2] < 20) { const f = 20 / vb[2]; vb = [vb[0] - vb[2] * (f - 1) / 2, vb[1] - vb[3] * (f - 1) / 2, vb[2] * f, vb[3] * f]; }
    svg.setAttribute('viewBox', vb.map((v) => v.toFixed(2)).join(' '));
    const s = vb[2] / Math.max(1, svg.clientWidth);
    for (const c of $$('#km-pts circle')) { const n = +c.dataset.n; c.setAttribute('r', ((n > 1 ? 8 : 5.5) + Math.min(10, Math.sqrt(n) * 1.5)) * s); }
    for (const t of $$('#km-pts text')) t.setAttribute('font-size', 10 * s);
    const pts = $('#km-pts')._punkte || [];
    const frei = (x, y) => !pts.some((p) => Math.abs(p.x - x) < 60 * s && Math.abs(p.y - y) < 14 * s);
    $('#km-ref').innerHTML = STAEDTE.filter(([, lat, lon]) => frei(px(lon) + 26 * s, py(lat))).map(([n, lat, lon]) => `<circle cx="${px(lon)}" cy="${py(lat)}" r="${2 * s}"/><text x="${px(lon) + 5 * s}" y="${py(lat) + 3.5 * s}" font-size="${11 * s}">${n}</text>`).join('');
  }
  function kartenZoom(f, cx, cy) {
    const [x, y, w, h] = vb;
    if (cx === undefined) { cx = x + w / 2; cy = y + h / 2; }
    vb = [cx - (cx - x) * f, cy - (cy - y) * f, w * f, h * f];
    kartenAusschnitt();
  }
  function kartenPos(ev) { const svg = $('#km-svg'), r = svg.getBoundingClientRect(); return [vb[0] + (ev.clientX - r.left) / r.width * vb[2], vb[1] + (ev.clientY - r.top) / r.height * vb[3]]; }
  function kartenPop(plz) {
    const p = ($('#km-pts')._punkte || []).find((x) => x.plz === plz); if (!p) return;
    for (const g of $$('#km-pts .pt')) g.classList.toggle('sel', g.dataset.plz === plz);
    const pop = $('#km-pop');
    pop.innerHTML = `<h3><span>${esc(p.plz)} ${esc(p.liste[0].ort)}</span><button type="button" class="crm-rund klein" data-km="zu" aria-label="Schließen">${icon('x')}</button></h3>
      <ul>${p.liste.map((k) => `<li>${firmaKnopf(k)}<small>${k.nr ? 'KN ' + esc(k.nr) + ' · ' : ''}${esc(vName(k.vertreter) || 'ohne Vertreter')}${k.aktiv ? '' : ' · inaktiv'}</small></li>`).join('')}</ul>`;
    pop.hidden = false;
  }
  let ziehen = null;
  document.addEventListener('pointerdown', (e) => {
    const svg = e.target.closest('#km-svg'); if (!svg || e.button !== 0) return;
    if (e.target.closest('.pt')) return;
    ziehen = { x: e.clientX, y: e.clientY, vb: vb.slice(), bewegt: false, id: e.pointerId };
    svg.setPointerCapture(e.pointerId); svg.classList.add('ziehen');
  });
  document.addEventListener('pointermove', (e) => {
    if (!ziehen || e.pointerId !== ziehen.id) return;
    const svg = $('#km-svg'), r = svg.getBoundingClientRect();
    const dx = (e.clientX - ziehen.x) / r.width * ziehen.vb[2], dy = (e.clientY - ziehen.y) / r.height * ziehen.vb[3];
    if (Math.abs(e.clientX - ziehen.x) + Math.abs(e.clientY - ziehen.y) > 3) ziehen.bewegt = true;
    vb = [ziehen.vb[0] - dx, ziehen.vb[1] - dy, ziehen.vb[2], ziehen.vb[3]];
    $('#km-svg').setAttribute('viewBox', vb.map((v) => v.toFixed(2)).join(' '));
  });
  document.addEventListener('pointerup', (e) => { if (!ziehen || e.pointerId !== ziehen.id) return; const svg = $('#km-svg'); if (svg) svg.classList.remove('ziehen'); ziehen = null; kartenAusschnitt(); });
  document.addEventListener('wheel', (e) => { if (!e.target.closest('#km-svg')) return; e.preventDefault(); const [cx, cy] = kartenPos(e); kartenZoom(e.deltaY > 0 ? 1.2 : 1 / 1.2, cx, cy); }, { passive: false });

  /* ---------- Auswertung ---------- */
  function auswertung() {
    const K = S.d.kunden;
    const proV = S.d.vertreter.map((v) => {
      const l = K.filter((k) => k.vertreter === v.nr || k.vertreter2 === v.nr);
      return { name: v.name, kunden: l.length, aktiv: l.filter((k) => k.aktiv).length, akt: l.reduce((n, k) => n + k.aktivitaeten, 0), db: l.filter((k) => OFFEN_PHASEN.includes(k.crm.phase)).reduce((n, k) => n + db(k), 0) };
    });
    const ohne = K.filter((k) => !k.vertreter && !k.vertreter2);
    if (ohne.length) proV.push({ name: 'Ohne Vertreter', kunden: ohne.length, aktiv: ohne.filter((k) => k.aktiv).length, akt: ohne.reduce((n, k) => n + k.aktivitaeten, 0), db: ohne.filter((k) => OFFEN_PHASEN.includes(k.crm.phase)).reduce((n, k) => n + db(k), 0) });
    const seg = S.d.segmente.map((s) => [s, K.filter((k) => k.crm.segment === s).length]).filter((x) => x[1]);
    const segMax = Math.max(1, ...seg.map((x) => x[1]));
    const art = Object.entries(S.d.statistik.jeArt).filter((x) => x[1]);
    const artMax = Math.max(1, ...art.map((x) => x[1]));
    $('#tab-auswertung').innerHTML = `
      <div class="crm-titel"><h1>Auswertung</h1><p>Bestand, Aktivitäten und Chancen je Vertreter und Segment.</p></div>
      <div class="crm-kpis">
        ${kpi('Aktivitäten gesamt', S.d.statistik.gesamt)}
        ${kpi('Letzte 30 Tage', S.d.statistik.tage30)}
        ${kpi('Interessenten', K.filter((k) => k.art === 'interessent').length)}
        ${kpi('Ohne Segment', K.filter((k) => k.crm.segment === 'Nicht zugeordnet').length, 'Segment im Kundenblatt prüfen')}
        ${kpi('Ohne Wann', K.filter((k) => k.aktiv && !k.crm.rhythmus1 && !k.crm.rhythmus2).length, 'aktive Kunden ohne Anruf-Rhythmus')}
      </div>
      <div class="crm-raster">
        <section class="crm-karte crm-glas"><h3>Bestand nach Vertreter</h3>
          <div class="crm-tabelle-rahmen" style="max-height:none"><table class="crm-tabelle"><thead><tr><th>Vertreter</th><th>Kunden</th><th>davon aktiv</th><th>Aktivitäten</th><th>DB-Chance</th></tr></thead>
          <tbody>${proV.map((v) => `<tr><td>${esc(v.name)}</td><td>${v.kunden}</td><td>${v.aktiv}</td><td>${v.akt}</td><td class="nw">${geld(v.db)}</td></tr>`).join('') || '<tr><td colspan="5" class="crm-leer">Keine Vertreter in den Stammdaten.</td></tr>'}</tbody></table></div>
        </section>
        <section class="crm-karte crm-glas"><h3>Segmente</h3>
          ${seg.map(([s, n]) => `<div class="crm-balken"><span>${esc(s)}</span><div class="spur"><i style="width:${Math.max(3, n / segMax * 100)}%"></i></div><b>${n}</b></div>`).join('')}
          <p class="crm-klein">Kunden aus den Stammdaten sind zunächst „Nicht zugeordnet“.</p>
        </section>
        <section class="crm-karte crm-glas"><h3>Aktivitäten nach Art</h3>
          ${art.length ? art.map(([a, n]) => `<div class="crm-balken"><span>${esc(a)}</span><div class="spur"><i style="width:${Math.max(3, n / artMax * 100)}%"></i></div><b>${n}</b></div>`).join('') : '<p class="crm-leer">Noch keine Aktivitäten protokolliert.</p>'}
        </section>
        <section class="crm-karte crm-glas"><h3>Wirtschaftliche Auswertung</h3>
          <p class="crm-klein">Umsatz und kg je Kunde, DB je Auftrag, letzter Kauf und Wiederkaufrate folgen, sobald Auftragsdaten aus WinAB angebunden sind. Bis dahin werden keine Umsätze geschätzt – nur das im Kundenblatt eingetragene Potenzial zählt.</p>
        </section>
      </div>`;
  }

  /* ---------- Kundenblatt ---------- */
  let offenKey = '';
  function feld(label, name, k, typ = 'text', extra = '') {
    const v = k.crm[name];
    const wertText = typ === 'number' ? zahl(v) : (v ?? '');
    return `<label class="${extra}">${esc(label)}<input type="${typ === 'number' ? 'text' : typ}"${typ === 'number' ? ' inputmode="decimal"' : ''} data-blatt="${name}" value="${esc(wertText)}"${darf() ? '' : ' disabled'}></label>`;
  }
  function auswahl(label, name, k, liste, leer = null) {
    return `<label>${esc(label)}<select data-blatt="${name}"${darf() ? '' : ' disabled'}>${opts(liste, k.crm[name], leer)}</select></label>`;
  }
  function kontaktZeile(p = {}) {
    const d = darf() ? '' : ' disabled';
    return `<div class="crm-kontakt" data-kontakt>
      <input type="text" data-k="name" placeholder="Name" aria-label="Name" maxlength="80" value="${esc(p.name || '')}"${d}>
      <input type="text" data-k="funktion" placeholder="Funktion" aria-label="Funktion" maxlength="60" value="${esc(p.funktion || '')}"${d}>
      <input type="tel" data-k="telefon" placeholder="Telefon" aria-label="Telefon" maxlength="40" value="${esc(p.telefon || '')}"${d}>
      <input type="email" data-k="email" placeholder="E-Mail" aria-label="E-Mail" maxlength="160" value="${esc(p.email || '')}"${d}>
      ${darf() ? `<button type="button" class="crm-rund klein" data-kontakt-weg aria-label="Ansprechpartner entfernen">${icon('x')}</button>` : '<span></span>'}
    </div>`;
  }
  function stammdaten(k) {
    const dd = (t, v, weit = false) => `<div${weit ? ' class="weit"' : ''}><dt>${esc(t)}</dt><dd>${v || '<span class="crm-gedaempft">—</span>'}</dd></div>`;
    const adr = [k.strasse, [k.plz, k.ort].filter(Boolean).join(' '), k.land].filter(Boolean).map(esc).join('<br>');
    return `<dl class="crm-stamm">
      ${dd('Kundennummer', esc(k.nr))}${dd('Kundengruppe', esc(k.gruppe))}${dd('Status', k.aktiv ? 'aktiv' : 'inaktiv')}
      ${dd('Vertreter', esc(vName(k.vertreter)))}${dd('Vertreter 2', esc(vName(k.vertreter2)))}${dd('Angebote', esc(k.angebote.join(', ')))}
      ${dd('Anschrift', adr)}${dd('Telefon', k.telefon ? telLink(k.telefon) : '')}${dd('E-Mail', k.email ? `<a href="mailto:${esc(k.email)}">${esc(k.email)}</a>` : '', true)}
      ${dd('Ansprechpartner (Stammdaten)', esc(k.ansprechpartner), true)}
    </dl>`;
  }
  async function oeffne(key) {
    const k = S.byKey.get(key); if (!k) return;
    offenKey = key;
    const b = darf();
    $('#kunde-titel').textContent = k.firma || 'Kunde';
    $('#kunde-sub').textContent = [k.art === 'interessent' ? 'Interessent' : (k.nr ? 'KN ' + k.nr : 'Kunde'), vName(k.vertreter) || 'ohne Vertreter', k.crm.geaendert ? `zuletzt geändert ${deZeit(k.crm.geaendert)} von ${k.crm.geaendertVon}` : ''].filter(Boolean).join(' · ');
    const rh = S.d.rhythmen;
    $('#kunde-inhalt').innerHTML = `
      <section class="crm-abschnitt">
        <div class="crm-abschnitt-kopf"><h3>${k.art === 'interessent' ? 'Adresse des Interessenten' : 'Stammdaten'}</h3>
          ${k.art === 'interessent' ? (b ? '<button type="button" class="btn" data-interessent-bearbeiten>Adresse bearbeiten</button>' : '')
            : `<span class="crm-klein">Pflege in der Verwaltung${S.d.rechte.stammdaten ? ` · <a href="${esc(verwaltungKunden())}" target="_blank" rel="noopener">Kunden öffnen ${icon('extern')}</a>` : ''}</span>`}</div>
        ${stammdaten(k)}
      </section>
      <section class="crm-abschnitt">
        <div class="crm-abschnitt-kopf"><h3>Ansprechpartner</h3><span class="crm-klein">im CRM gepflegt</span></div>
        <div class="crm-kontakte-kopf"><span>Name</span><span>Funktion</span><span>Telefon</span><span>E-Mail</span><span></span></div>
        <div class="crm-kontakte" id="kontakte">${k.crm.kontakte.map(kontaktZeile).join('') || (b ? '' : '<p class="crm-leer">Keine weiteren Ansprechpartner.</p>')}</div>
        ${b ? `<div class="crm-knoepfe"><button type="button" class="btn" data-kontakt-neu>${icon('plus')}Ansprechpartner</button><span class="crm-platz"></span><button type="button" class="btn primary" data-kontakte-speichern>Ansprechpartner speichern</button></div>` : ''}
      </section>
      <section class="crm-abschnitt">
        <div class="crm-abschnitt-kopf"><h3>Vertrieb</h3><span class="crm-status" id="blatt-status">${b ? 'Änderungen werden beim Verlassen eines Feldes gespeichert.' : 'Nur ansehen – zum Bearbeiten fehlt das Recht „CRM bearbeiten“.'}</span></div>
        <div class="crm-felder vier">
          ${auswahl('Segment', 'segment', k, S.d.segmente)}${auswahl('Phase', 'phase', k, S.d.phasen)}
          ${auswahl('Wann', 'rhythmus1', k, rh, '— nicht festgelegt —')}${auswahl('Wann 2', 'rhythmus2', k, rh, '— nicht festgelegt —')}
          ${auswahl('Erledigt', 'anrufStatus', k, S.d.anruf)}
          <label>Aktiv in der Wiedervorlage<select data-blatt="anrufAktiv"${b ? '' : ' disabled'}><option value="Ja"${k.crm.anrufAktiv ? ' selected' : ''}>Ja</option><option value="Nein"${k.crm.anrufAktiv ? '' : ' selected'}>Nein</option></select></label>
          ${feld('Letzter Kontakt', 'letzterKontakt', k, 'date')}${feld('Letzter Auftrag', 'letzterAuftrag', k, 'date')}
          ${feld('Potenzial · kg', 'potenzialKg', k, 'number')}${feld('Nettoverkaufspreis · €/kg', 'preisKg', k, 'number')}${feld('DB · €/kg', 'dbKg', k, 'number')}${feld('Ø Bestellmenge · kg', 'bestellKg', k, 'number')}
          ${feld('Nächster Schritt', 'naechsterSchritt', k, 'text', 'breit')}
          ${feld('Wiedervorlage am', 'wiedervorlage', k, 'date')}${feld('Kontaktpräferenz', 'praeferenz', k, 'text')}
          <label class="breit">Gesprächsnotiz / Bedarf<textarea data-blatt="notiz" maxlength="2000"${b ? '' : ' disabled'}>${esc(k.crm.notiz)}</textarea></label>
        </div>
      </section>
      ${b ? `<section class="crm-abschnitt">
        <div class="crm-abschnitt-kopf"><h3>Aktivität protokollieren</h3></div>
        <form class="crm-felder vier" id="akt-form" novalidate>
          <label>Art<select id="akt-art">${opts(S.d.arten, 'Telefonat', null)}</select></label>
          <label class="crm-akt-notiz" style="grid-column: span 3">Ergebnis / Betreff<input type="text" id="akt-notiz" maxlength="500" placeholder="z. B. Bedarf für KW 44 besprochen"></label>
          <label style="grid-column: span 2">Nächster Schritt<input type="text" id="akt-naechster" maxlength="160" placeholder="z. B. Angebot nachfassen"></label>
          <label>Wiedervorlage am<input type="date" id="akt-faellig"></label>
          <div style="display:flex;align-items:flex-end"><button type="submit" class="btn primary" id="akt-speichern">Aktivität speichern</button></div>
        </form>
        <p class="crm-meldung" id="akt-meldung" role="status"></p>
      </section>` : ''}
      <section class="crm-abschnitt">
        <div class="crm-abschnitt-kopf"><h3>Verlauf</h3><span class="crm-klein" id="verlauf-zahl"></span></div>
        <ul class="crm-verlauf" id="verlauf"><li class="crm-leer">Verlauf wird geladen …</li></ul>
      </section>`;
    const dlg = $('#dlg-kunde');
    if (!dlg.open) dlg.showModal();
    ladeVerlauf(key);
  }
  async function ladeVerlauf(key) {
    const r = await api('crm_verlauf', null, '&key=' + encodeURIComponent(key));
    if (offenKey !== key || !$('#verlauf')) return;
    if (r.status !== 200) { $('#verlauf').innerHTML = `<li class="crm-leer">${esc(fehlerText(r, 'Verlauf nicht geladen'))}</li>`; return; }
    const l = r.data.aktivitaeten;
    $('#verlauf-zahl').textContent = l.length ? `${l.length} ${l.length === 1 ? 'Eintrag' : 'Einträge'}` : '';
    $('#verlauf').innerHTML = l.length ? l.map((a) => `<li><time>${esc(deZeit(a.at))}</time><div><b>${esc(a.art)}</b>${a.notiz ? ' · ' + esc(a.notiz) : ''}<small>${esc(a.von)}${a.naechster ? ` · Nächster Schritt: ${esc(a.naechster)}${a.faellig ? ' bis ' + de(a.faellig) : ''}` : ''}</small></div></li>`).join('')
      : '<li class="crm-leer">Noch keine Aktivitäten protokolliert.</li>';
  }
  function blattStatus(text, art = '') { const s = $('#blatt-status'); if (s) { s.textContent = text; s.className = 'crm-status ' + art; } }
  /* Änderung eines Feldes im Kundenblatt speichern */
  document.addEventListener('change', async (e) => {
    const el = e.target;
    if (el.matches('[data-blatt]') && offenKey) {
      const name = el.dataset.blatt;
      let v = el.value;
      if (name === 'anrufAktiv') v = v === 'Ja';
      if (['potenzialKg', 'preisKg', 'dbKg', 'bestellKg'].includes(name)) v = v.trim() === '' ? null : v.trim().replace(',', '.');
      blattStatus('Wird gespeichert …');
      const k = await speichereFelder(offenKey, { [name]: v });
      if (k) blattStatus('Gespeichert.', 'ok');
      else { blattStatus('Nicht gespeichert – bitte Eingabe prüfen.', 'fehler'); const alt = S.byKey.get(offenKey); if (alt) el.value = name === 'anrufAktiv' ? (alt.crm.anrufAktiv ? 'Ja' : 'Nein') : zahlOderText(alt.crm[name]); }
      return;
    }
    // Auswahl direkt in einer Tabelle (Kunden, Wiedervorlage, Pipeline)
    if (el.matches('select[data-feld][data-key]')) {
      const name = el.dataset.feld; let v = el.value;
      if (name === 'anrufAktiv') v = v === 'Ja';
      const k = await speichereFelder(el.dataset.key, { [name]: v });
      if (!k) { const alt = S.byKey.get(el.dataset.key); if (alt) el.value = name === 'anrufAktiv' ? (alt.crm.anrufAktiv ? 'Ja' : 'Nein') : alt.crm[name]; return; }
      if (el.className.startsWith('st-')) el.className = 'st-' + el.value;
      el.closest('tr') && name === 'anrufAktiv' && el.closest('tr').classList.toggle('aus', !k.crm.anrufAktiv);
      toast('Gespeichert.');
      if (S.tab === 'pipeline') pipeline();
      const n = faellig().length; $('#crm-faellig').hidden = !n; $('#crm-faellig').textContent = n || '';
      return;
    }
    // Filter
    const f = { 'k-aktiv': ['kunden', 'aktiv'], 'k-segment': ['kunden', 'segment'], 'k-phase': ['kunden', 'phase'], 'k-vertreter': ['kunden', 'vertreter'],
      'wv-termin': ['wv', 'termin'], 'wv-vertreter': ['wv', 'vertreter'] }[el.id];
    if (f) { S[f[0]][f[1]] = el.value; S[f[0]].n = SEITE; f[0] === 'kunden' ? kunden() : wiedervorlagen(true); return; }
    if (el.matches('[data-wann]')) { S.wv.wann = $$('[data-wann]:checked').map((x) => x.value); S.wv.n = SEITE; $('#wv-wann summary').textContent = S.wv.wann.length ? `Wann: ${S.wv.wann.length} gewählt` : 'Wann: alle'; wiedervorlagen(true); return; }
    if (el.id === 'km-ja' || el.id === 'km-nein') { S.karte[el.id === 'km-ja' ? 'ja' : 'nein'] = el.checked; karte(); }
  });
  const zahlOderText = (v) => (typeof v === 'number' ? zahl(v) : (v ?? ''));
  function kontakteAusFormular() {
    return $$('#kontakte [data-kontakt]').map((z) => Object.fromEntries($$('[data-k]', z).map((i) => [i.dataset.k, i.value.trim()]))).filter((p) => p.name || p.funktion || p.telefon || p.email);
  }

  /* Aktivität speichern */
  document.addEventListener('submit', async (e) => {
    if (e.target.id === 'akt-form') {
      e.preventDefault();
      const m = $('#akt-meldung'), key = offenKey;
      const b = { key, art: $('#akt-art').value, notiz: $('#akt-notiz').value, naechster: $('#akt-naechster').value, faellig: $('#akt-faellig').value };
      $('#akt-speichern').disabled = true;
      const r = await api('crm_aktivitaet', b);
      $('#akt-speichern').disabled = false;
      if (r.status !== 200) { m.className = 'crm-meldung fehler'; m.textContent = fehlerText(r, 'Speichern fehlgeschlagen'); return; }
      ersetze(r.data.kunde);
      S.d.letzte.unshift(r.data.aktivitaet); S.d.letzte = S.d.letzte.slice(0, 30);
      S.d.statistik.gesamt++; S.d.statistik.tage30++; S.d.statistik.jeArt[r.data.aktivitaet.art] = (S.d.statistik.jeArt[r.data.aktivitaet.art] || 0) + 1;
      toast('Aktivität protokolliert.');
      oeffne(key);
      return;
    }
    if (e.target.id === 'interessent-form') { e.preventDefault(); speichereInteressent(); }
  });

  /* ---------- Interessent ---------- */
  const INT_FELDER = ['firma', 'ansprechpartner', 'strasse', 'plz', 'ort', 'land', 'telefon', 'email', 'vertreter', 'vertreter2'];
  function interessentDialog(k = null) {
    const d = $('#dlg-interessent');
    d.dataset.id = k ? k.key : '';
    $('#interessent-titel').textContent = k ? 'Interessent bearbeiten' : 'Neuer Interessent';
    $('#int-vertreter').innerHTML = vOpts(k ? k.vertreter : '', '— kein Vertreter —');
    $('#int-vertreter2').innerHTML = vOpts(k ? k.vertreter2 : '', '— kein Vertreter —');
    for (const f of INT_FELDER) if (!f.startsWith('vertreter')) $('#int-' + f).value = k ? k[f] : '';
    $('#int-aktiv').checked = k ? k.aktiv : true;
    $('#interessent-meldung').textContent = ''; $('#interessent-meldung').className = 'crm-meldung';
    d.showModal();
    $('#int-firma').focus();
  }
  async function speichereInteressent() {
    const d = $('#dlg-interessent'), b = { id: d.dataset.id || '', aktiv: $('#int-aktiv').checked };
    for (const f of INT_FELDER) b[f] = $('#int-' + f).value;
    const r = await api('crm_interessent_save', b);
    if (r.status !== 200) { const m = $('#interessent-meldung'); m.className = 'crm-meldung fehler'; m.textContent = fehlerText(r, 'Speichern fehlgeschlagen'); return; }
    ersetze(r.data.kunde);
    S.d.kunden.sort((x, y) => x.firma.localeCompare(y.firma, 'de'));
    d.close();
    toast(b.id ? 'Interessent gespeichert.' : 'Interessent angelegt.');
    zeichne();
    oeffne(r.data.kunde.key);
  }

  /* ---------- Klicks ---------- */
  document.addEventListener('click', async (e) => {
    const t = e.target;
    const o = t.closest('[data-oeffnen]'); if (o) { oeffne(o.dataset.oeffnen); return; }
    const g = t.closest('[data-gehe]'); if (g) { if (g.dataset.termin) { S.wv.termin = g.dataset.termin; S.wv.n = SEITE; } zeigeTab(g.dataset.gehe); return; }
    if (t.closest('[data-neu-interessent]')) { interessentDialog(); return; }
    if (t.closest('[data-interessent-bearbeiten]')) { interessentDialog(S.byKey.get(offenKey)); return; }
    const mehr = t.closest('[data-mehr]'); if (mehr) { if (mehr.dataset.mehr === 'kunden') { S.kunden.n += SEITE; kunden(); } else { S.wv.n += SEITE; wiedervorlagen(true); } return; }
    if (t.closest('[data-schliessen]')) { t.closest('dialog').close(); return; }
    if (t.closest('[data-kontakt-neu]')) { $('#kontakte').insertAdjacentHTML('beforeend', kontaktZeile()); $('#kontakte [data-kontakt]:last-child input').focus(); return; }
    if (t.closest('[data-kontakt-weg]')) { t.closest('[data-kontakt]').remove(); return; }
    if (t.closest('[data-kontakte-speichern]')) {
      blattStatus('Ansprechpartner werden gespeichert …');
      const k = await speichereFelder(offenKey, { kontakte: kontakteAusFormular() });
      if (k) { blattStatus('Ansprechpartner gespeichert.', 'ok'); toast('Ansprechpartner gespeichert.'); $('#kontakte').innerHTML = k.crm.kontakte.map(kontaktZeile).join(''); }
      else blattStatus('Ansprechpartner nicht gespeichert – bitte Eingaben prüfen.', 'fehler');
      return;
    }
    if (t.id === 'wv-wann-alle') { for (const c of $$('[data-wann]')) c.checked = false; S.wv.wann = []; $('#wv-wann summary').textContent = 'Wann: alle'; wiedervorlagen(true); return; }
    if (t.closest('#wv-neu-sortieren')) { wvReihenfolge(); wiedervorlagen(true); toast('Nach dem nächsten Anruf geordnet.'); return; }
    const km = t.closest('[data-km]');
    if (km) { const a = km.dataset.km; if (a === 'in') kartenZoom(1 / 1.6); else if (a === 'aus') kartenZoom(1.6); else if (a === 'alle') { vb = voll.slice(); kartenAusschnitt(); } else if (a === 'zu') { $('#km-pop').hidden = true; for (const p of $$('#km-pts .pt')) p.classList.remove('sel'); } return; }
    const pt = t.closest('#km-pts .pt'); if (pt) { kartenPop(pt.dataset.plz); return; }
    if (t.closest('#crm-export')) { exportieren(); }
  });
  document.addEventListener('keydown', (e) => { const pt = e.target.closest && e.target.closest('#km-pts .pt'); if (pt && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); kartenPop(pt.dataset.plz); } });
  // Nach dem Schließen des Kundenblatts die aktuelle Ansicht mit den neuen Werten zeichnen
  $('#dlg-kunde').addEventListener('close', () => { offenKey = ''; zeichne(); });
  addEventListener('resize', () => { if (S.tab === 'karte' && vb) { vb = seitenVerhaeltnis(vb); kartenAusschnitt(); } });

  async function exportieren() {
    try {
      const res = await fetch(API + '?action=crm_export', { method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: '{}' });
      if (!res.ok) { let t = ''; try { t = (await res.json()).error; } catch { /* kein JSON */ } throw new Error(t || `Export fehlgeschlagen (${res.status}).`); }
      const name = ((res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/) || [])[1] || 'CRM.csv';
      const url = URL.createObjectURL(await res.blob());
      const a = Object.assign(document.createElement('a'), { href: url, download: name });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      toast(`${name} wurde heruntergeladen.`);
    } catch (err) { toast(err.message || String(err), true); }
  }

  /* ---------- Start ---------- */
  async function laden() {
    const st = await api('status');
    if (st.status === 401 && !st.json) { zeigeAnmeldung('./'); return; }
    if (st.status === 403 && st.data.code === 'reauth_required' && typeof st.data.anmelden === 'string' && st.data.anmelden.startsWith('/oidc/')) {
      location.assign(st.data.anmelden + encodeURIComponent(location.href)); return;
    }
    if (st.status === 403 && st.data.error) { fehler(st.data.error); return; }
    if (st.status !== 200 || !st.data.loggedIn) { zeigeAnmeldung(); return; }
    csrf = st.data.csrf || '';
    if (window.STAFL_THEME) { window.STAFL_THEME.konto(st.data.user, csrf, API); themaKnopf(); }   // Hell/Dunkel am Konto (theme.js)
    const name = st.data.user ? (st.data.user.name || st.data.user.username || '') : '';
    $('#crm-user').hidden = false; $('#crm-user-name').textContent = name; $('#crm-initialen').textContent = initialen(name);
    const r = await api('crm_start');
    if (r.status === 404) { fehler('Das CRM ist für Sie noch nicht freigegeben.'); return; }
    if (r.status === 503) { fehler(r.data.error || 'Das CRM wird gerade gewartet.'); return; }
    if (r.status === 403) { fehler(r.data.error || 'Dafür fehlt Ihnen die Berechtigung.'); return; }
    if (r.status === 401) { zeigeAnmeldung(r.json ? '' : './'); return; }
    if (r.status !== 200 || !r.data.ok) { fehler(fehlerText(r, 'Das CRM konnte nicht geladen werden')); return; }
    setzeDaten(r.data);
    $('#crm-login').hidden = true; $('#crm-app').hidden = false;
    const tab = location.hash.slice(1);
    zeigeTab($(`#crm-tabs button[data-tab="${CSS.escape(tab)}"]`) ? tab : 'cockpit');
  }
  themaKnopf();
  laden().catch(() => fehler('Keine Verbindung zum Server.'));
})();
