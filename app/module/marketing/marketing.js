/* STAFL-Plattform · Marketing · Redaktionsplan
   Social-Media-Inhalte planen, produzieren, freigeben und veröffentlichen: Übersicht, Kalender (Monat/Woche, Verschieben per
   Ziehen), Board (Spalten je Status), Liste mit Filtern, Kampagnen, Einstellungen (Marken, Kanäle, Formate, Content-Säulen)
   und der Beitrag mit Inhalt, Planung, Checkliste, Material, Ablauf, Kennzahlen und Kommentaren.
   Alle Rechte und Ablaufregeln prüft der Server bei jeder Aktion (GR-103) – ausgeblendete Knöpfe sind nur Anzeige.
   Kein Inline-Skript (Content-Security-Policy); Texte vom Server immer über esc(). */
'use strict';
(() => {
  const API = '../../api/';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (n) => `<svg class="i" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const ABLAUF = ['idee', 'planung', 'produktion', 'freigabe', 'geplant', 'veroeffentlicht'];
  const REIHE = [...ABLAUF, 'verworfen'];
  const STATUS_ART = { idee: '', planung: 'info', produktion: 'info', freigabe: 'warn', geplant: 'ok', veroeffentlicht: 'ok', verworfen: 'aus' };
  const NAECHSTER = { idee: ['planung', 'Planung starten'], planung: ['produktion', 'In Produktion'], produktion: ['freigabe', 'Zur Freigabe geben'],
    freigabe: ['geplant', 'Freigeben'], geplant: ['veroeffentlicht', 'Als veröffentlicht markieren'] };
  const WT = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  const MONATE = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  const FARBEN = ['#8c1d2c', '#2f7a52', '#2f6fb0', '#c27a1a', '#7a4fb0', '#1f8a8a', '#b0446c', '#5c6b7a'];
  const VORLAGEN = {
    reel: ['Hook und Skript final', 'Drehort und Termin abgestimmt', 'A-Roll gedreht', 'B-Roll gedreht', 'Schnitt und Untertitel', 'Musik/Ton lizenzfrei geprüft', 'Cover / Titelbild', 'Caption und Hashtags', 'Freigabe eingeholt'],
    karussell: ['Hook-Slide', 'Inhalt-Slides (4 Punkte)', 'CTA-Slide', 'Gestaltung in Canva', 'Produktangaben geprüft', 'Caption und Hashtags', 'Freigabe eingeholt'],
    foto: ['Motiv und Styling', 'Fotos aufgenommen', 'Bildbearbeitung', 'Caption und Hashtags', 'Freigabe eingeholt'],
  };
  let csrf = '';
  const S = { d: null, tab: 'uebersicht', f: { q: '', marke: '', kanal: '', verantwortlich: '', kampagne: '', status: '', meine: false, verworfen: false },
    kal: { modus: 'monat', tag: null, termine: false }, sort: 'termin', zeigeArchiv: false, offen: null, schnappschuss: '' };

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
    const t = $('#mkt-toast');
    t.textContent = text; t.className = 'mkt-toast zeigen' + (fehler ? ' fehler' : '');
    clearTimeout(toastZeit); toastZeit = setTimeout(() => { t.className = 'mkt-toast'; }, fehler ? 4200 : 2200);
  }
  /* Rückfrage im eigenen Dialog (kein Browser-Dialog) */
  function frage(titel, text, ja = 'Ja') {
    const d = $('#dlg-frage');
    $('#fr-titel').textContent = titel; $('#fr-text').textContent = text; $('#fr-ja').textContent = ja;
    return new Promise((ok) => {
      const fertig = (w) => { d.removeEventListener('click', klick); d.removeEventListener('cancel', abbruch); if (d.open) d.close(); ok(w); };
      const klick = (e) => { const b = e.target.closest('[data-antwort]'); if (b) fertig(b.dataset.antwort === 'ja'); };
      const abbruch = () => fertig(false);
      d.addEventListener('click', klick); d.addEventListener('cancel', abbruch);
      d.showModal();
    });
  }

  /* ---------- Datum ---------- */
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const ausIso = (s) => { const [y, m, d] = s.slice(0, 10).split('-').map(Number); return new Date(y, m - 1, d); };
  const heute = () => S.d.heute;
  const plusTage = (s, n) => { const d = ausIso(s); d.setDate(d.getDate() + n); return iso(d); };
  const montag = (s) => { const d = ausIso(s); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return iso(d); };
  const datumVon = (e) => (e.veroeffentlichung || '').slice(0, 10);
  const zeitVon = (e) => (e.veroeffentlichung || '').slice(11, 16);
  const de = (s) => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : '';
  const deKurz = (s) => s ? `${WT[(ausIso(s).getDay() + 6) % 7]} ${s.slice(8, 10)}.${s.slice(5, 7)}.` : '';
  const terminText = (e) => e.veroeffentlichung ? deKurz(datumVon(e)) + (zeitVon(e) ? ' ' + zeitVon(e) : '') : 'ohne Termin';
  const deZeit = (s) => { const d = new Date(s); return isNaN(d) ? '' : d.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' }); };
  const tageBis = (s) => Math.round((ausIso(s) - ausIso(heute())) / 86400000);

  /* ---------- Nachschlagen ---------- */
  const finde = (liste, id) => (liste || []).find((x) => x.id === id) || null;
  const marke = (id) => finde(S.d.einstellungen.marken, id);
  const kanal = (id) => finde(S.d.einstellungen.kanaele, id);
  const format = (id) => finde(S.d.einstellungen.formate, id);
  const saeule = (id) => finde(S.d.einstellungen.saeulen, id);
  const kampagne = (id) => finde(S.d.kampagnen, id);
  const nameVon = (o, id) => o ? o.name : (id ? id + ' (entfernt)' : '');
  const statusName = (s) => S.d.status[s] || s;
  const statusPille = (s) => `<span class="mkt-pille ${STATUS_ART[s] || ''}">${esc(statusName(s))}</span>`;
  const initialen = (n) => { const t = String(n || '').trim().split(/[\s.\-_]+/).filter(Boolean);   // wie HR und CRM: „Administrator“ → „AD“
    return (t.length > 1 ? t[0][0] + t[1][0] : (t[0] || '?').slice(0, 2)).toLocaleUpperCase('de-DE'); };
  const markenFarbe = (e) => (marke(e.marke) || {}).farbe || '#9a928b';
  const kanalKurz = (id) => { const k = kanal(id); return k ? k.name : id; };
  const darfBearbeiten = () => S.d.rechte.bearbeiten;
  const ueberfaellig = (e) => !['veroeffentlicht', 'verworfen'].includes(e.status)
    && ((e.veroeffentlichung && datumVon(e) < heute()) || (e.produktionBis && e.produktionBis < heute() && ['idee', 'planung', 'produktion'].includes(e.status)));
  const opts = (liste, wert, leer) => (leer !== null ? `<option value="">${esc(leer)}</option>` : '')
    + liste.filter((x) => x.aktiv !== false || x.id === wert).map((x) => `<option value="${esc(x.id)}"${x.id === wert ? ' selected' : ''}>${esc(x.name)}</option>`).join('')
    + (wert && !finde(liste, wert) ? `<option value="${esc(wert)}" selected>${esc(wert)} (entfernt)</option>` : '');

  /* ---------- Filter ---------- */
  function passt(e, ohneStatus = false) {
    const f = S.f;
    if (!f.verworfen && e.status === 'verworfen' && f.status !== 'verworfen') return false;
    if (f.marke && e.marke !== f.marke) return false;
    if (f.kanal && !e.kanaele.includes(f.kanal)) return false;
    if (f.verantwortlich && e.verantwortlich !== f.verantwortlich) return false;
    if (f.kampagne && e.kampagne !== f.kampagne) return false;
    if (f.meine && e.verantwortlich !== S.d.ich) return false;
    if (!ohneStatus && f.status && e.status !== f.status) return false;
    if (f.q) {
      const q = f.q.toLowerCase();
      if (![e.titel, e.hook, e.text, e.hashtags, e.notizen].some((t) => String(t || '').toLowerCase().includes(q))) return false;
    }
    return true;
  }
  function filterLeiste(mitStatus = false) {
    const f = S.f, E = S.d.einstellungen;
    return `<div class="mkt-leiste" data-filter>
      <label class="mkt-suche"><span class="sr-only">Suchen</span>${icon('search')}<input type="search" data-f="q" value="${esc(f.q)}" placeholder="Titel, Text, Hashtag …"></label>
      <select data-f="marke" aria-label="Marke">${opts(E.marken, f.marke, 'Alle Marken')}</select>
      <select data-f="kanal" aria-label="Kanal">${opts(E.kanaele, f.kanal, 'Alle Kanäle')}</select>
      ${mitStatus ? `<select data-f="status" aria-label="Status"><option value="">Alle Status</option>${Object.keys(S.d.status).map((s) => `<option value="${s}"${s === f.status ? ' selected' : ''}>${esc(statusName(s))}</option>`).join('')}</select>` : ''}
      <select data-f="verantwortlich" aria-label="Verantwortlich"><option value="">Alle Verantwortlichen</option>${S.d.team.map((t) => `<option value="${esc(t.id)}"${t.id === f.verantwortlich ? ' selected' : ''}>${esc(t.name)}</option>`).join('')}</select>
      <select data-f="kampagne" aria-label="Kampagne">${opts(S.d.kampagnen.filter((k) => !k.archiviert || k.id === f.kampagne), f.kampagne, 'Alle Kampagnen')}</select>
      <label class="mkt-check-z"><input type="checkbox" data-f="meine"${f.meine ? ' checked' : ''}> nur meine</label>
      ${Object.values(f).some((v) => v) ? '<button type="button" class="btn mkt-klein-btn" data-filter-leeren>Filter zurücksetzen</button>' : ''}
    </div>`;
  }
  document.addEventListener('input', (e) => {
    const el = e.target.closest('[data-filter] [data-f]');
    if (!el || el.type !== 'search') return;
    S.f.q = el.value; zeichne(true);
  });
  document.addEventListener('change', (e) => {
    const el = e.target.closest('[data-filter] [data-f]');
    if (!el || el.type === 'search') return;
    S.f[el.dataset.f] = el.type === 'checkbox' ? el.checked : el.value; zeichne();
  });

  /* ---------- Kopf, Anmeldung, Thema ---------- */
  function fehler(text) { $('#mkt-login').hidden = true; $('#mkt-app').hidden = true; $('#mkt-err').hidden = false; $('#mkt-err').textContent = text; }
  function zeigeAnmeldung(ziel) {
    if (ziel) $('#mkt-login a').setAttribute('href', ziel);
    $('#mkt-login').hidden = false; $('#mkt-app').hidden = true; $('#mkt-user').hidden = true;
  }
  const ECHT = /(^|\.)dashboard-stafl\.de$/.test(location.hostname);
  if (ECHT) $('#mkt-zurueck').href = 'https://dashboard-stafl.de/';
  const dunkel = () => document.documentElement.getAttribute('data-theme') === 'dark'
    || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  function themaKnopf() {
    const d = dunkel();
    $('#mkt-theme').innerHTML = icon(d ? 'sun' : 'moon');
    $('#mkt-theme').setAttribute('aria-label', d ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }
  $('#mkt-theme').addEventListener('click', () => {
    const neu = dunkel() ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', neu);
    try { localStorage.setItem('wochenangebot.theme', JSON.stringify(neu)); } catch { /* ohne Speicher */ }
    themaKnopf();
  });

  /* ---------- Reiter ---------- */
  function zeigeTab(tab) {
    S.tab = tab;
    for (const b of $$('#mkt-tabs button')) b.setAttribute('aria-selected', String(b.dataset.tab === tab));
    for (const p of $$('.mkt-tab')) p.hidden = p.id !== 'tab-' + tab;
    try { history.replaceState(null, '', '#' + tab); } catch { /* egal */ }
    zeichne();
  }
  $('#mkt-tabs').addEventListener('click', (e) => { const b = e.target.closest('button[data-tab]'); if (b) zeigeTab(b.dataset.tab); });
  /* nurInhalt: beim Tippen in der Suche nur die Ergebnisse neu zeichnen, damit das Suchfeld den Fokus behält */
  function zeichne(nurInhalt = false) {
    const n = S.d.beitraege.filter((e) => e.status === 'freigabe').length;
    $('#mkt-freigabe-zahl').hidden = !n; $('#mkt-freigabe-zahl').textContent = n || '';
    const ansicht = { uebersicht, kalender, board, liste, kampagnen, einstellungen }[S.tab];
    if (nurInhalt && $(`#tab-${S.tab} [data-ergebnis]`)) { $(`#tab-${S.tab} [data-ergebnis]`).innerHTML = ansicht(true); return; }
    $(`#tab-${S.tab}`).innerHTML = ansicht(false);
  }

  /* ---------- Daten ---------- */
  function setzeDaten(d) {
    S.d = d;
    $('#mkt-neu').hidden = !d.rechte.bearbeiten;
    $('#mkt-export').hidden = false;
    $('#mkt-tabs [data-tab="einstellungen"]').hidden = !d.rechte.verwalten;
  }
  function ersetze(e) {
    if (!e) return;
    const i = S.d.beitraege.findIndex((x) => x.id === e.id);
    if (i >= 0) S.d.beitraege[i] = e; else S.d.beitraege.push(e);
  }
  const beitrag = (id) => S.d.beitraege.find((e) => e.id === id) || null;
  /* Teiländerung ohne Dialog (Kalender, Board): Konflikt → neue Fassung übernehmen und melden */
  async function speichere(e, felder, status) {
    const body = { id: e.id, rev: e.rev, felder };
    if (status) body.status = status;
    const r = await api('marketing_beitrag_save', body);
    if (r.status === 409 && r.data.beitrag) { ersetze(r.data.beitrag); zeichne(); toast(r.data.error, true); return null; }
    if (r.status !== 200) { toast(fehlerText(r, 'Speichern fehlgeschlagen'), true); zeichne(); return null; }
    const vorher = e.status;
    ersetze(r.data.beitrag); zeichne();
    if (vorher === 'geplant' && r.data.beitrag.status === 'freigabe') toast('Termin geändert – der Beitrag muss erneut freigegeben werden.');
    else toast('Gespeichert.');
    return r.data.beitrag;
  }

  /* ---------- Bausteine ---------- */
  function kanalChips(e) { return e.kanaele.map((k) => `<span class="mkt-kanal">${esc(kanalKurz(k))}</span>`).join(''); }
  function karte(e, kompakt = false) {
    const ch = e.checkliste.length ? `${e.checkliste.filter((p) => p.erledigt).length}/${e.checkliste.length}` : '';
    const zieh = darfBearbeiten() ? ' draggable="true"' : '';
    return `<article class="mkt-kartei${ueberfaellig(e) ? ' ueber' : ''}" data-oeffnen="${esc(e.id)}" data-zieh="${esc(e.id)}"${zieh} tabindex="0" style="--marke:${esc(markenFarbe(e))}">
      <div class="kopf"><b>${esc(e.titel)}</b>${e.prioritaet === 'hoch' ? '<span class="mkt-pille fehler">hoch</span>' : ''}</div>
      <div class="meta"><span>${icon('uhr')}${esc(terminText(e))}</span>${e.format ? `<span>${esc(nameVon(format(e.format), e.format))}</span>` : ''}</div>
      ${kompakt ? '' : `<div class="kanaele">${kanalChips(e)}</div>`}
      <div class="fuss">${e.verantwortlich ? `<span class="mkt-avatar" title="${esc(e.verantwortlichName)}">${esc(initialen(e.verantwortlichName))}</span>` : ''}
        ${ch ? `<span title="Checkliste">${icon('check')}${ch}</span>` : ''}${e.kommentare.length ? `<span title="Kommentare">${icon('chat')}${e.kommentare.length}</span>` : ''}
        ${e.ki ? `<span class="mkt-ki" title="Mit KI erzeugt – Kennzeichnung prüfen">${icon('funke')}KI</span>` : ''}</div>
    </article>`;
  }
  function zeile(e, wann) {
    return `<li><span class="mkt-punkt" style="--marke:${esc(markenFarbe(e))}"></span><div class="was"><button type="button" class="mkt-titelknopf" data-oeffnen="${esc(e.id)}">${esc(e.titel)}</button>
      <small>${esc([nameVon(marke(e.marke), e.marke), e.kanaele.map(kanalKurz).join(', '), e.verantwortlichName].filter(Boolean).join(' · '))}</small></div>${wann}</li>`;
  }
  function kpi(titel, w, zusatz = '', cls = '', ziel = '') {
    return `<${ziel ? 'button type="button"' : 'div'} class="mkt-wert mkt-glas ${cls}"${ziel ? ` data-gehe="${ziel}"` : ''}><span>${esc(titel)}</span><b>${esc(w)}</b>${zusatz ? `<small>${esc(zusatz)}</small>` : ''}</${ziel ? 'button' : 'div'}>`;
  }
  function balken(paare) {
    const max = Math.max(1, ...paare.map((p) => p[1]));
    return paare.map(([n, v, farbe]) => `<div class="mkt-balken"><span>${esc(n)}</span><span class="spur"><i style="width:${Math.round(v / max * 100)}%;${farbe ? `background:${esc(farbe)}` : ''}"></i></span><b>${v}</b></div>`).join('');
  }

  /* ---------- Übersicht ---------- */
  function uebersicht() {
    const B = S.d.beitraege, h = heute(), mo = montag(h), so = plusTage(mo, 6), bis28 = plusTage(h, 27);
    const aktiv = B.filter((e) => e.status !== 'verworfen');
    const woche = aktiv.filter((e) => e.veroeffentlichung && datumVon(e) >= mo && datumVon(e) <= so);
    const naechste = aktiv.filter((e) => e.veroeffentlichung && datumVon(e) >= h && e.status !== 'veroeffentlicht').sort((a, b) => a.veroeffentlichung.localeCompare(b.veroeffentlichung)).slice(0, 8);
    const freigabe = B.filter((e) => e.status === 'freigabe').sort((a, b) => (a.veroeffentlichung || '9').localeCompare(b.veroeffentlichung || '9'));
    const ueber = B.filter(ueberfaellig).sort((a, b) => (a.veroeffentlichung || a.produktionBis).localeCompare(b.veroeffentlichung || b.produktionBis));
    const meine = aktiv.filter((e) => e.verantwortlich === S.d.ich && !['veroeffentlicht'].includes(e.status)).sort((a, b) => (a.veroeffentlichung || '9').localeCompare(b.veroeffentlichung || '9')).slice(0, 8);
    const seit30 = plusTage(h, -30);
    const veroeff30 = B.filter((e) => e.status === 'veroeffentlicht' && (e.veroeffentlichtAm ? e.veroeffentlichtAm.slice(0, 10) : datumVon(e)) >= seit30).length;
    const vier = aktiv.filter((e) => e.veroeffentlichung && datumVon(e) >= h && datumVon(e) <= bis28);
    const E = S.d.einstellungen;
    const kanalMix = E.kanaele.filter((k) => k.aktiv !== false).map((k) => [k.name, vier.filter((e) => e.kanaele.includes(k.id)).length]);
    const saeulenMix = E.saeulen.filter((s) => s.aktiv !== false).map((s) => [s.name, vier.filter((e) => e.saeule === s.id).length, s.farbe]);
    const ohneSaeule = vier.filter((e) => !e.saeule).length;
    if (ohneSaeule) saeulenMix.push(['ohne Säule', ohneSaeule, '#9a928b']);
    const wannText = (e) => { const t = tageBis(datumVon(e)); return `<span class="wann">${esc(terminText(e))}<small>${t === 0 ? 'heute' : t === 1 ? 'morgen' : 'in ' + t + ' Tagen'}</small></span>`; };
    const leer = (t) => `<p class="mkt-leer">${esc(t)}</p>`;
    return `<div class="mkt-titel"><div><h1>Redaktionsplan</h1><p>Was wir wann produzieren und veröffentlichen – von der Idee bis zum Beitrag.</p></div></div>
      <div class="mkt-kpis">
        ${kpi('Diese Woche', woche.length, `${deKurz(mo)} – ${deKurz(so)}`, '', 'kalender')}
        ${kpi('In Produktion', B.filter((e) => e.status === 'produktion').length, 'Beiträge', '', 'board')}
        ${kpi('Zur Freigabe', freigabe.length, S.d.rechte.freigeben ? 'warten auf Sie' : 'warten auf Freigabe', freigabe.length ? 'warn' : '', 'board')}
        ${kpi('Überfällig', ueber.length, 'Termin oder Produktion', ueber.length ? 'akzent' : '', 'liste')}
        ${kpi('Veröffentlicht', veroeff30, 'letzte 30 Tage')}
      </div>
      ${darfBearbeiten() ? `<form class="mkt-idee mkt-glas" id="idee-form"><span class="lbl">${icon('funke')}Idee festhalten</span><input type="text" id="idee-titel" maxlength="140" placeholder="z. B. Reel: Ein Tag in der Reifekammer" aria-label="Neue Idee"><button type="submit" class="btn primary">Speichern</button></form>` : ''}
      <div class="mkt-raster">
        <section class="mkt-karte mkt-glas"><div class="mkt-karte-kopf"><h3>Nächste Veröffentlichungen</h3><button type="button" class="btn" data-gehe="kalender">Kalender</button></div>
          ${naechste.length ? `<ul class="mkt-zeilen">${naechste.map((e) => zeile(e, wannText(e))).join('')}</ul>` : leer('Nichts geplant. Im Kalender auf einen Tag tippen, um einen Beitrag zu planen.')}</section>
        <section class="mkt-karte mkt-glas"><div class="mkt-karte-kopf"><h3>Wartet auf Freigabe</h3>${freigabe.length ? `<span class="mkt-pille warn">${freigabe.length}</span>` : ''}</div>
          ${freigabe.length ? `<ul class="mkt-zeilen">${freigabe.slice(0, 8).map((e) => zeile(e, `<span class="wann">${esc(terminText(e))}</span>`)).join('')}</ul>` : leer('Keine Beiträge in der Freigabe.')}</section>
        <section class="mkt-karte mkt-glas"><div class="mkt-karte-kopf"><h3>Überfällig</h3></div>
          ${ueber.length ? `<ul class="mkt-zeilen">${ueber.slice(0, 8).map((e) => zeile(e, `<span class="wann ueber">${esc(e.veroeffentlichung && datumVon(e) < h ? 'Termin ' + deKurz(datumVon(e)) : 'Produktion bis ' + deKurz(e.produktionBis))}</span>`)).join('')}</ul>` : leer('Alles im Plan.')}</section>
        <section class="mkt-karte mkt-glas"><div class="mkt-karte-kopf"><h3>Meine Beiträge</h3></div>
          ${meine.length ? `<ul class="mkt-zeilen">${meine.map((e) => zeile(e, `<span class="wann">${statusPille(e.status)}</span>`)).join('')}</ul>` : leer('Ihnen ist gerade kein offener Beitrag zugeordnet.')}</section>
        <section class="mkt-karte mkt-glas"><div class="mkt-karte-kopf"><h3>Kanäle – nächste 4 Wochen</h3></div>${vier.length ? balken(kanalMix) : leer('Noch nichts geplant.')}</section>
        <section class="mkt-karte mkt-glas"><div class="mkt-karte-kopf"><h3>Content-Säulen – nächste 4 Wochen</h3></div>${vier.length ? balken(saeulenMix) : leer('Noch nichts geplant.')}
          ${vier.length ? '<p class="mkt-klein">Ausgewogene Säulen halten den Kanal abwechslungsreich – fehlt eine länger, lohnt ein Beitrag dazu.</p>' : ''}</section>
      </div>`;
  }

  /* ---------- Kalender ---------- */
  const schmal = () => matchMedia('(max-width: 760px)').matches;
  function kalender(nurInhalt) {
    if (!S.kal.tag) S.kal.tag = heute();
    const inhalt = kalenderInhalt();
    if (nurInhalt) return inhalt;
    const ref = ausIso(S.kal.tag);
    const titel = S.kal.modus === 'monat' ? `${MONATE[ref.getMonth()]} ${ref.getFullYear()}` : `Woche ${deKurz(montag(S.kal.tag))} – ${deKurz(plusTage(montag(S.kal.tag), 6))}`;
    return `<div class="mkt-kalkopf">
        <div class="mkt-navi"><button type="button" class="mkt-rund klein" data-kal="zurueck" aria-label="Zurück">${icon('links')}</button><h1>${esc(titel)}</h1>
          <button type="button" class="mkt-rund klein" data-kal="vor" aria-label="Weiter">${icon('rechts')}</button><button type="button" class="btn" data-kal="heute">Heute</button></div>
        <div class="mkt-umschalter" role="group" aria-label="Ansicht"><button type="button" data-kal="monat" aria-pressed="${S.kal.modus === 'monat'}">Monat</button><button type="button" data-kal="woche" aria-pressed="${S.kal.modus === 'woche'}">Woche</button></div>
        <label class="mkt-check-z"><input type="checkbox" data-kal="termine"${S.kal.termine ? ' checked' : ''}> Dreh- und Produktionstermine</label>
      </div>
      ${filterLeiste()}
      <div data-ergebnis>${inhalt}</div>`;
  }
  function tagesEintraege(tag) {
    const B = S.d.beitraege.filter((e) => passt(e));
    const pub = B.filter((e) => datumVon(e) === tag).sort((a, b) => (zeitVon(a) || '99').localeCompare(zeitVon(b) || '99'));
    const ter = S.kal.termine ? [...B.filter((e) => e.drehtermin === tag).map((e) => [e, 'Dreh']), ...B.filter((e) => e.produktionBis === tag && !['geplant', 'veroeffentlicht'].includes(e.status)).map((e) => [e, 'Produktion bis'])] : [];
    return [pub, ter];
  }
  function chip(e) {
    const zieh = darfBearbeiten() && e.status !== 'veroeffentlicht' ? ' draggable="true"' : '';
    return `<button type="button" class="mkt-chip st-${esc(e.status)}${ueberfaellig(e) ? ' ueber' : ''}" data-oeffnen="${esc(e.id)}" data-zieh="${esc(e.id)}"${zieh} style="--marke:${esc(markenFarbe(e))}" title="${esc(e.titel + ' · ' + statusName(e.status))}">
      ${zeitVon(e) ? `<time>${esc(zeitVon(e))}</time>` : ''}<span class="t">${esc(e.titel)}</span><span class="k">${esc(e.kanaele.map((k) => kanalKurz(k).slice(0, 2)).join(' '))}</span></button>`;
  }
  function terminChip([e, art]) { return `<button type="button" class="mkt-chip termin" data-oeffnen="${esc(e.id)}" title="${esc(art + ': ' + e.titel)}">${icon(art === 'Dreh' ? 'kamera' : 'uhr')}<span class="t">${esc(art)}: ${esc(e.titel)}</span></button>`; }
  function kalenderInhalt() {
    const ohne = S.d.beitraege.filter((e) => passt(e) && !e.veroeffentlichung && !['veroeffentlicht', 'verworfen'].includes(e.status));
    const seite = `<aside class="mkt-ohne mkt-glas" data-ablage><h3>Ohne Termin <span class="mkt-klein">${ohne.length}</span></h3>
      ${darfBearbeiten() ? '<p class="mkt-klein mkt-zieh-hinweis">In den Kalender ziehen, um einen Termin zu setzen.</p>' : ''}
      <div class="mkt-ohne-liste">${ohne.map((e) => karte(e, true)).join('') || '<p class="mkt-leer">Alle Beiträge haben einen Termin.</p>'}</div></aside>`;
    if (schmal()) return `<div class="mkt-kal-rahmen">${agenda()}${seite}</div>`;
    const h = heute();
    if (S.kal.modus === 'woche') {
      const mo = montag(S.kal.tag);
      const tage = [...Array(7)].map((_, i) => plusTage(mo, i));
      return `<div class="mkt-kal-rahmen"><div class="mkt-woche mkt-glas">${tage.map((t) => { const [pub, ter] = tagesEintraege(t); return `<div class="mkt-tag${t === h ? ' heute' : ''}" data-tag="${t}">
        <div class="mkt-tagkopf"><span>${WT[(ausIso(t).getDay() + 6) % 7]}</span><b>${t.slice(8, 10)}.${t.slice(5, 7)}.</b>${darfBearbeiten() ? `<button type="button" class="mkt-plus" data-neu-am="${t}" aria-label="Beitrag am ${de(t)} planen">${icon('plus')}</button>` : ''}</div>
        <div class="mkt-tagliste">${pub.map(chip).join('')}${ter.map(terminChip).join('')}</div></div>`; }).join('')}</div>${seite}</div>`;
    }
    const ref = ausIso(S.kal.tag), erster = iso(new Date(ref.getFullYear(), ref.getMonth(), 1));
    const start = montag(erster), monat = ref.getMonth();
    const wochen = []; for (let w = 0; w < 6; w++) { const t0 = plusTage(start, w * 7); if (w > 3 && ausIso(t0).getMonth() !== monat) break; wochen.push(t0); }
    return `<div class="mkt-kal-rahmen"><div class="mkt-monat mkt-glas"><div class="mkt-wtage">${WT.map((w) => `<span>${w}</span>`).join('')}</div>
      ${wochen.map((w0) => `<div class="mkt-wzeile">${[...Array(7)].map((_, i) => { const t = plusTage(w0, i), [pub, ter] = tagesEintraege(t), anders = ausIso(t).getMonth() !== monat;
        const mehr = pub.length > 4 ? `<button type="button" class="mkt-mehr" data-woche-von="${t}">+ ${pub.length - 4} weitere</button>` : '';
        return `<div class="mkt-tag${t === h ? ' heute' : ''}${anders ? ' anders' : ''}" data-tag="${t}"><div class="mkt-tagkopf"><b>${Number(t.slice(8, 10))}</b>${darfBearbeiten() ? `<button type="button" class="mkt-plus" data-neu-am="${t}" aria-label="Beitrag am ${de(t)} planen">${icon('plus')}</button>` : ''}</div>
          <div class="mkt-tagliste">${pub.slice(0, 4).map(chip).join('')}${mehr}${ter.map(terminChip).join('')}</div></div>`; }).join('')}</div>`).join('')}</div>${seite}</div>`;
  }
  /* Handy: Tagesliste des Monats bzw. der Woche statt Raster */
  function agenda() {
    const ref = ausIso(S.kal.tag);
    let von, bis;
    if (S.kal.modus === 'woche') { von = montag(S.kal.tag); bis = plusTage(von, 6); } else { von = iso(new Date(ref.getFullYear(), ref.getMonth(), 1)); bis = iso(new Date(ref.getFullYear(), ref.getMonth() + 1, 0)); }
    const tage = [];
    for (let t = von; t <= bis; t = plusTage(t, 1)) { const [pub, ter] = tagesEintraege(t); if (pub.length || ter.length || t === heute()) tage.push([t, pub, ter]); }
    return `<div class="mkt-agenda mkt-glas">${tage.map(([t, pub, ter]) => `<div class="mkt-agenda-tag${t === heute() ? ' heute' : ''}" data-tag="${t}"><div class="mkt-tagkopf"><b>${esc(deKurz(t))}</b>${darfBearbeiten() ? `<button type="button" class="mkt-plus" data-neu-am="${t}" aria-label="Beitrag am ${de(t)} planen">${icon('plus')}</button>` : ''}</div>
      <div class="mkt-tagliste">${pub.map(chip).join('')}${ter.map(terminChip).join('')}${!pub.length && !ter.length ? '<span class="mkt-klein">nichts geplant</span>' : ''}</div></div>`).join('') || '<p class="mkt-leer">In diesem Zeitraum ist nichts geplant.</p>'}</div>`;
  }
  document.addEventListener('click', (e) => {
    const k = e.target.closest('[data-kal]');
    if (k && k.type !== 'checkbox') {
      const a = k.dataset.kal, ref = ausIso(S.kal.tag || heute());
      if (a === 'heute') S.kal.tag = heute();
      else if (a === 'monat' || a === 'woche') S.kal.modus = a;
      else if (S.kal.modus === 'monat') S.kal.tag = iso(new Date(ref.getFullYear(), ref.getMonth() + (a === 'vor' ? 1 : -1), 1));
      else S.kal.tag = plusTage(S.kal.tag, a === 'vor' ? 7 : -7);
      zeichne(); return;
    }
    const w = e.target.closest('[data-woche-von]');
    if (w) { S.kal.modus = 'woche'; S.kal.tag = w.dataset.wocheVon; zeichne(); }
  });
  document.addEventListener('change', (e) => { const k = e.target.closest('input[data-kal="termine"]'); if (k) { S.kal.termine = k.checked; zeichne(); } });
  addEventListener('resize', () => { if (S.d && S.tab === 'kalender') { const s = schmal(); if (s !== S.kal.warSchmal) { S.kal.warSchmal = s; zeichne(); } } });

  /* ---------- Ziehen und Ablegen (Kalender: Termin, Board: Status) ---------- */
  let gezogen = '';
  document.addEventListener('dragstart', (e) => { const el = e.target.closest('[data-zieh][draggable="true"]'); if (!el) return; gezogen = el.dataset.zieh; e.dataTransfer.effectAllowed = 'move'; try { e.dataTransfer.setData('text/plain', gezogen); } catch { /* egal */ } el.classList.add('zieht'); });
  document.addEventListener('dragend', (e) => { const el = e.target.closest && e.target.closest('[data-zieh]'); if (el) el.classList.remove('zieht'); $$('.ziel').forEach((x) => x.classList.remove('ziel')); });
  document.addEventListener('dragover', (e) => {
    if (!gezogen) return;
    const ziel = e.target.closest('[data-tag], [data-spalte], [data-ablage]');
    if (!ziel) return;
    e.preventDefault(); e.dataTransfer.dropEffect = 'move';
    $$('.ziel').forEach((x) => { if (x !== ziel) x.classList.remove('ziel'); }); ziel.classList.add('ziel');
  });
  document.addEventListener('drop', async (e) => {
    const ziel = e.target.closest('[data-tag], [data-spalte], [data-ablage]');
    const id = gezogen; gezogen = '';
    if (!ziel || !id) return;
    e.preventDefault(); ziel.classList.remove('ziel');
    const b = beitrag(id); if (!b) return;
    if ('ablage' in ziel.dataset) { if (b.veroeffentlichung) await speichere(b, { veroeffentlichung: '' }); }   // Termin entfernen
    else if (ziel.dataset.tag) {
      const neu = ziel.dataset.tag + (zeitVon(b) ? 'T' + zeitVon(b) : '');
      if (neu !== b.veroeffentlichung) await speichere(b, { veroeffentlichung: neu });
    } else if (ziel.dataset.spalte !== b.status) {
      if (ziel.dataset.spalte === 'geplant' && !S.d.rechte.freigeben) { toast('Freigeben darf nur, wer das Recht dazu hat.', true); return; }
      await speichere(b, {}, ziel.dataset.spalte);
    }
  });

  /* ---------- Board ---------- */
  function board(nurInhalt) {
    const inhalt = boardInhalt();
    if (nurInhalt) return inhalt;
    return `<div class="mkt-titel"><div><h1>Board</h1><p>${darfBearbeiten() ? 'Karten in die nächste Spalte ziehen oder öffnen, um den Status zu ändern.' : 'Stand aller Beiträge nach Status.'}</p></div>
      <label class="mkt-check-z"><input type="checkbox" data-f-verworfen${S.f.verworfen ? ' checked' : ''}> Verworfene zeigen</label></div>
      ${filterLeiste()}<div data-ergebnis>${inhalt}</div>`;
  }
  function boardInhalt() {
    const spalten = [...ABLAUF, ...(S.f.verworfen ? ['verworfen'] : [])];
    const B = S.d.beitraege.filter((e) => passt(e, true));
    return `<div class="mkt-board">${spalten.map((s) => {
      let liste = B.filter((e) => e.status === s).sort((a, b) => (a.veroeffentlichung || '9').localeCompare(b.veroeffentlichung || '9'));
      const gesamt = liste.length;
      if (s === 'veroeffentlicht') liste = liste.sort((a, b) => (b.veroeffentlichung || '').localeCompare(a.veroeffentlichung || '')).slice(0, 20);
      return `<section class="mkt-spalte mkt-glas st-${s}" data-spalte="${s}"><div class="mkt-spalte-kopf"><span>${esc(statusName(s))}</span><span class="mkt-pille">${gesamt}</span></div>
        ${liste.map((e) => karte(e)).join('') || '<p class="mkt-leer">—</p>'}${s === 'veroeffentlicht' && gesamt > 20 ? `<p class="mkt-klein">die letzten 20 von ${gesamt} – alle in der Liste</p>` : ''}</section>`;
    }).join('')}</div>`;
  }
  document.addEventListener('change', (e) => { if (e.target.matches('[data-f-verworfen]')) { S.f.verworfen = e.target.checked; zeichne(); } });

  /* ---------- Liste ---------- */
  function liste(nurInhalt) {
    const inhalt = listeInhalt();
    if (nurInhalt) return inhalt;
    return `<div class="mkt-titel"><div><h1>Alle Beiträge</h1><p>Suchen, filtern, sortieren – als CSV für Excel über den Knopf oben.</p></div>
      <label class="mkt-check-z"><input type="checkbox" data-f-verworfen${S.f.verworfen ? ' checked' : ''}> Verworfene zeigen</label></div>
      ${filterLeiste(true)}<div data-ergebnis>${inhalt}</div>`;
  }
  function listeInhalt() {
    const sorter = { termin: (a, b) => (a.veroeffentlichung || '9999').localeCompare(b.veroeffentlichung || '9999') || a.titel.localeCompare(b.titel),
      titel: (a, b) => a.titel.localeCompare(b.titel, 'de'), status: (a, b) => REIHE.indexOf(a.status) - REIHE.indexOf(b.status) || (a.veroeffentlichung || '9').localeCompare(b.veroeffentlichung || '9') };
    const L = S.d.beitraege.filter((e) => passt(e)).sort(sorter[S.sort] || sorter.termin);
    const th = (k, t) => `<th><button type="button" class="mkt-sort${S.sort === k ? ' an' : ''}" data-sort="${k}">${esc(t)}</button></th>`;
    return `<p class="mkt-klein mkt-anzahl">${L.length} ${L.length === 1 ? 'Beitrag' : 'Beiträge'}</p>
      <div class="mkt-tabelle-rahmen mkt-glas"><table class="mkt-tabelle"><thead><tr>${th('termin', 'Veröffentlichung')}${th('titel', 'Titel')}<th class="m-aus">Marke</th><th>Kanäle</th><th class="l-aus">Format</th>${th('status', 'Status')}<th class="m-aus">Verantwortlich</th><th class="l-aus">Kampagne</th></tr></thead>
      <tbody>${L.map((e) => `<tr class="${e.status === 'verworfen' ? 'aus' : ''}">
        <td class="nw${ueberfaellig(e) ? ' mkt-ueber' : ''}">${esc(terminText(e))}</td>
        <td><button type="button" class="mkt-titelknopf" data-oeffnen="${esc(e.id)}"><span class="mkt-punkt" style="--marke:${esc(markenFarbe(e))}"></span>${esc(e.titel)}</button>${e.ki ? ` <span class="mkt-ki">${icon('funke')}KI</span>` : ''}</td>
        <td class="m-aus nw">${esc(nameVon(marke(e.marke), e.marke))}</td><td>${kanalChips(e)}</td><td class="l-aus nw">${esc(nameVon(format(e.format), e.format))}</td>
        <td class="nw">${statusPille(e.status)}</td><td class="m-aus nw">${esc(e.verantwortlichName)}</td><td class="l-aus">${esc(nameVon(kampagne(e.kampagne), e.kampagne))}</td></tr>`).join('')
        || '<tr><td colspan="8" class="mkt-leer">Keine Beiträge zu diesem Filter.</td></tr>'}</tbody></table></div>`;
  }
  document.addEventListener('click', (e) => { const b = e.target.closest('[data-sort]'); if (b) { S.sort = b.dataset.sort; zeichne(); } });

  /* ---------- Kampagnen ---------- */
  function kampagnen() {
    const K = S.d.kampagnen.filter((k) => S.zeigeArchiv || !k.archiviert).sort((a, b) => (b.von || '').localeCompare(a.von || '') || a.name.localeCompare(b.name));
    return `<div class="mkt-titel"><div><h1>Kampagnen</h1><p>Beiträge zu einem Anlass bündeln – mit Zeitraum, Ziel und Fortschritt.</p></div>
      <label class="mkt-check-z"><input type="checkbox" id="kp-archiv"${S.zeigeArchiv ? ' checked' : ''}> archivierte zeigen</label>
      ${darfBearbeiten() ? `<button type="button" class="btn primary" data-kampagne-neu>${icon('plus')}Kampagne</button>` : ''}</div>
      <div class="mkt-kampagnen">${K.map((k) => {
        const B = S.d.beitraege.filter((e) => e.kampagne === k.id && e.status !== 'verworfen');
        const fertig = B.filter((e) => e.status === 'veroeffentlicht').length;
        const jeStatus = ABLAUF.map((s) => [s, B.filter((e) => e.status === s).length]).filter((x) => x[1]);
        return `<article class="mkt-karte mkt-glas mkt-kampagne${k.archiviert ? ' aus' : ''}" style="--marke:${esc(k.farbe)}">
          <div class="mkt-karte-kopf"><h3><span class="mkt-punkt"></span>${esc(k.name)}</h3>${darfBearbeiten() ? `<button type="button" class="btn" data-kampagne="${esc(k.id)}">Bearbeiten</button>` : ''}</div>
          <p class="mkt-klein">${esc([k.von || k.bis ? `${de(k.von) || '…'} – ${de(k.bis) || '…'}` : 'ohne Zeitraum', nameVon(marke(k.marke), k.marke), k.archiviert ? 'archiviert' : ''].filter(Boolean).join(' · '))}</p>
          ${k.ziel ? `<p class="mkt-ziel">${esc(k.ziel)}</p>` : ''}
          <div class="mkt-fortschritt" title="${fertig} von ${B.length} veröffentlicht"><i style="width:${B.length ? Math.round(fertig / B.length * 100) : 0}%"></i></div>
          <p class="mkt-klein">${B.length ? `${fertig} von ${B.length} veröffentlicht · ${jeStatus.map(([s, n]) => `${n} ${statusName(s)}`).join(' · ')}` : 'Noch keine Beiträge.'}</p>
          <button type="button" class="btn" data-kampagne-liste="${esc(k.id)}">Beiträge anzeigen</button></article>`;
      }).join('') || '<p class="mkt-leer">Noch keine Kampagnen.</p>'}</div>`;
  }
  function kampagneDialog(k) {
    const d = $('#dlg-kampagne');
    d.dataset.id = k ? k.id : '';
    $('#kp-titel').textContent = k ? 'Kampagne bearbeiten' : 'Neue Kampagne';
    $('#kp-name').value = k ? k.name : ''; $('#kp-ziel').value = k ? k.ziel : ''; $('#kp-von').value = k ? k.von : ''; $('#kp-bis').value = k ? k.bis : '';
    $('#kp-marke').innerHTML = opts(S.d.einstellungen.marken, k ? k.marke : '', 'alle Marken');
    $('#kp-farbe').innerHTML = FARBEN.map((f, i) => `<option value="${f}"${(k ? k.farbe : FARBEN[0]) === f ? ' selected' : ''}>${['Bordeaux', 'Grün', 'Blau', 'Orange', 'Violett', 'Petrol', 'Rosé', 'Schiefer'][i]}</option>`).join('');
    $('#kp-archiviert').checked = !!(k && k.archiviert);
    $('#kp-meldung').textContent = ''; $('#kp-meldung').className = 'mkt-meldung';
    d.showModal(); $('#kp-name').focus();
  }
  $('#kp-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const d = $('#dlg-kampagne');
    const body = { id: d.dataset.id || '', name: $('#kp-name').value, ziel: $('#kp-ziel').value, von: $('#kp-von').value, bis: $('#kp-bis').value,
      marke: $('#kp-marke').value, farbe: $('#kp-farbe').value, archiviert: $('#kp-archiviert').checked };
    $('#kp-speichern').disabled = true;
    const r = await api('marketing_kampagne_save', body);
    $('#kp-speichern').disabled = false;
    if (r.status !== 200) { $('#kp-meldung').className = 'mkt-meldung fehler'; $('#kp-meldung').textContent = fehlerText(r, 'Speichern fehlgeschlagen'); return; }
    S.d.kampagnen = r.data.kampagnen; d.close(); toast('Kampagne gespeichert.'); zeichne();
  });
  document.addEventListener('change', (e) => { if (e.target.id === 'kp-archiv') { S.zeigeArchiv = e.target.checked; zeichne(); } });

  /* ---------- Einstellungen ---------- */
  const LISTEN = [['marken', 'Marken', true, false], ['kanaele', 'Kanäle', false, true], ['formate', 'Formate', false, false], ['saeulen', 'Content-Säulen', true, false]];
  function einstellungen() {
    if (!S.d.rechte.verwalten) return '<p class="mkt-leer">Einstellungen ändern dürfen Administratoren bzw. wer „Marketing verwalten“ hat.</p>';
    const E = S.d.einstellungen;
    const nutzung = (art, id) => S.d.beitraege.filter((e) => art === 'kanaele' ? e.kanaele.includes(id) : e[{ marken: 'marke', formate: 'format', saeulen: 'saeule' }[art]] === id).length;
    return `<div class="mkt-titel"><div><h1>Einstellungen</h1><p>Auswahllisten des Redaktionsplans. Nicht mehr benötigte Einträge besser abschalten als löschen – bestehende Beiträge behalten sie.</p></div></div>
      <form id="einst-form" class="mkt-einst">${LISTEN.map(([art, titel, farbe, istKanal]) => `<section class="mkt-karte mkt-glas" data-liste="${art}">
        <div class="mkt-karte-kopf"><h3>${esc(titel)}</h3><button type="button" class="btn" data-zeile-neu="${art}">${icon('plus')}Hinzufügen</button></div>
        <div class="mkt-einst-kopf${istKanal ? ' kanal' : ''}"><span>Name</span>${farbe ? '<span>Farbe</span>' : ''}${istKanal ? '<span title="Zeichengrenze für den Text (0 = keine)">Zeichen</span><span title="empfohlene Höchstzahl Hashtags (0 = keine)">Hashtags</span>' : ''}<span>aktiv</span><span></span></div>
        ${E[art].map((x) => einstZeile(art, x, farbe, istKanal, nutzung(art, x.id))).join('')}</section>`).join('')}
        <p class="mkt-meldung" id="einst-meldung" role="status"></p>
        <div class="mkt-knoepfe"><span class="mkt-platz"></span><button type="submit" class="btn primary" id="einst-speichern">Einstellungen speichern</button></div></form>`;
  }
  function einstZeile(art, x, farbe, istKanal, n) {
    return `<div class="mkt-einst-zeile${istKanal ? ' kanal' : ''}" data-id="${esc(x.id || '')}">
      <input type="text" data-k="name" value="${esc(x.name || '')}" maxlength="60" aria-label="Name">
      ${farbe ? `<select data-k="farbe" aria-label="Farbe" style="--marke:${esc(x.farbe || FARBEN[0])}">${FARBEN.map((f, i) => `<option value="${f}"${x.farbe === f ? ' selected' : ''}>${['Bordeaux', 'Grün', 'Blau', 'Orange', 'Violett', 'Petrol', 'Rosé', 'Schiefer'][i]}</option>`).join('')}${x.farbe && !FARBEN.includes(x.farbe) ? `<option value="${esc(x.farbe)}" selected>eigene</option>` : ''}</select>` : ''}
      ${istKanal ? `<input type="number" data-k="limit" min="0" max="100000" value="${Number(x.limit || 0)}" aria-label="Zeichengrenze"><input type="number" data-k="hashtags" min="0" max="100" value="${Number(x.hashtags || 0)}" aria-label="Hashtags">` : ''}
      <label class="mkt-check-z"><input type="checkbox" data-k="aktiv"${x.aktiv !== false ? ' checked' : ''}><span class="sr-only">aktiv</span></label>
      <button type="button" class="mkt-rund klein" data-zeile-weg title="${n ? `Wird in ${n} Beiträgen verwendet` : 'Entfernen'}" aria-label="Entfernen">${icon('papierkorb')}</button></div>`;
  }
  document.addEventListener('click', (e) => {
    const neu = e.target.closest('[data-zeile-neu]');
    if (neu) { const art = neu.dataset.zeileNeu, [, , farbe, istKanal] = LISTEN.find((l) => l[0] === art); $(`[data-liste="${art}"]`).insertAdjacentHTML('beforeend', einstZeile(art, { name: '', farbe: FARBEN[$$(`[data-liste="${art}"] .mkt-einst-zeile`).length % FARBEN.length], aktiv: true }, farbe, istKanal, 0)); $(`[data-liste="${art}"] .mkt-einst-zeile:last-child input`).focus(); return; }
    const weg = e.target.closest('[data-zeile-weg]');
    if (weg) {
      const z = weg.closest('.mkt-einst-zeile');
      if (/verwendet/.test(weg.title)) frage('Eintrag entfernen?', `${weg.title}. Diese Beiträge zeigen ihn danach als „(entfernt)“. Besser: „aktiv“ ausschalten.`, 'Trotzdem entfernen').then((ja) => { if (ja) z.remove(); });
      else z.remove();
    }
  });
  document.addEventListener('change', (e) => { const s = e.target.closest('.mkt-einst-zeile select[data-k="farbe"]'); if (s) s.style.setProperty('--marke', s.value); });
  document.addEventListener('submit', async (e) => {
    if (e.target.id !== 'einst-form') return;
    e.preventDefault();
    const body = {};
    for (const [art] of LISTEN) body[art] = $$(`[data-liste="${art}"] .mkt-einst-zeile`).map((z) => {
      const o = { id: z.dataset.id, name: $('[data-k="name"]', z).value, aktiv: $('[data-k="aktiv"]', z).checked };
      if ($('[data-k="farbe"]', z)) o.farbe = $('[data-k="farbe"]', z).value;
      if ($('[data-k="limit"]', z)) { o.limit = $('[data-k="limit"]', z).value; o.hashtags = $('[data-k="hashtags"]', z).value; }
      return o;
    });
    $('#einst-speichern').disabled = true;
    const r = await api('marketing_einstellungen_save', body);
    $('#einst-speichern').disabled = false;
    const m = $('#einst-meldung');
    if (r.status !== 200) { m.className = 'mkt-meldung fehler'; m.textContent = fehlerText(r, 'Speichern fehlgeschlagen'); return; }
    S.d.einstellungen = r.data.einstellungen; zeichne(); toast('Einstellungen gespeichert.');
  });

  /* ---------- Beitrag (Dialog) ---------- */
  const dlg = $('#dlg-beitrag');
  let checkliste = [], links = [];
  function zeichneCheck() {
    const b = darfBearbeiten();
    $('#bt-check').innerHTML = checkliste.map((p, i) => `<li><label class="mkt-check-z"><input type="checkbox" data-check="${i}"${p.erledigt ? ' checked' : ''}${b ? '' : ' disabled'}><span class="${p.erledigt ? 'erledigt' : ''}">${esc(p.text)}</span></label>${b ? `<button type="button" class="mkt-rund klein" data-check-weg="${i}" aria-label="Punkt entfernen">${icon('x')}</button>` : ''}</li>`).join('') || '<li class="mkt-klein">Noch keine Punkte – z. B. eine Vorlage wählen.</li>';
    $('#bt-check-stand').textContent = checkliste.length ? `${checkliste.filter((p) => p.erledigt).length} von ${checkliste.length} erledigt` : '';
  }
  function zeichneLinks() {
    const b = darfBearbeiten();
    $('#bt-links').innerHTML = links.map((l, i) => `<li><a href="${esc(l.url)}" target="_blank" rel="noopener noreferrer">${icon('extern')}${esc(l.titel || l.url)}</a>${b ? `<button type="button" class="mkt-rund klein" data-link-weg="${i}" aria-label="Link entfernen">${icon('x')}</button>` : ''}</li>`).join('') || '<li class="mkt-klein">Noch kein Material verlinkt.</li>';
  }
  function zeichneZaehler() {
    const text = $('#bt-text').value, tags = $('#bt-hashtags').value, ganz = text + (tags.trim() ? '\n\n' + tags.trim() : '');
    const nTags = (tags.match(/#[\p{L}\p{N}_]+/gu) || []).length;
    const gewaehlt = $$('#bt-kanaele input:checked').map((x) => kanal(x.value)).filter(Boolean);
    const teile = gewaehlt.filter((k) => k.limit > 0 || k.hashtags > 0).map((k) => {
      const zu = k.limit > 0 && ganz.length > k.limit, tz = k.hashtags > 0 && nTags > k.hashtags;
      return `<span class="${zu || tz ? 'zuviel' : ''}">${esc(k.name)}: ${k.limit > 0 ? `${ganz.length.toLocaleString('de-DE')}/${k.limit.toLocaleString('de-DE')} Zeichen` : ''}${k.hashtags > 0 ? `${k.limit > 0 ? ', ' : ''}${nTags}/${k.hashtags} Hashtags` : ''}</span>`;
    });
    $('#bt-zaehler').innerHTML = teile.join('') || (gewaehlt.length ? '' : '<span>Kanäle wählen, um die Zeichengrenzen zu sehen.</span>');
  }
  function zeichneVeroeff(e) {
    const st = e ? e.status : 'idee';
    const zeigen = ['geplant', 'veroeffentlicht'].includes(st) || (e && (Object.keys(e.veroeffentlicht || {}).length || Object.keys(e.ergebnisse || {}).length));
    $('#bt-veroeff').hidden = !zeigen;
    if (!zeigen) return;
    const gewaehlt = $$('#bt-kanaele input:checked').map((x) => x.value);
    const ver = (e && e.veroeffentlicht) || {}, erg = (e && e.ergebnisse) || {}, dis = darfBearbeiten() ? '' : ' disabled';
    const vorhanden = $('#bt-veroeff-felder').dataset.fuer === (e ? e.id + ':' + e.rev : '') ? Object.fromEntries($$('#bt-veroeff-felder [data-vk]').map((z) => [z.dataset.vk, { url: $('[data-v="url"]', z).value, reichweite: $('[data-v="reichweite"]', z).value, interaktionen: $('[data-v="interaktionen"]', z).value, aufrufe: $('[data-v="aufrufe"]', z).value }])) : {};
    $('#bt-veroeff-felder').dataset.fuer = e ? e.id + ':' + e.rev : '';
    $('#bt-veroeff-felder').innerHTML = gewaehlt.map((k) => { const v = vorhanden[k] || { url: ver[k] || '', ...(erg[k] || {}) }; return `<div class="mkt-vk" data-vk="${esc(k)}"><b>${esc(kanalKurz(k))}</b>
      <input type="url" data-v="url" value="${esc(v.url || '')}" placeholder="Link zum Beitrag" aria-label="Link ${esc(kanalKurz(k))}"${dis}>
      <div class="mkt-felder drei"><label>Reichweite<input type="number" min="0" data-v="reichweite" value="${esc(v.reichweite ?? '')}"${dis}></label><label>Interaktionen<input type="number" min="0" data-v="interaktionen" value="${esc(v.interaktionen ?? '')}"${dis}></label><label>Aufrufe<input type="number" min="0" data-v="aufrufe" value="${esc(v.aufrufe ?? '')}"${dis}></label></div></div>`; }).join('')
      || '<p class="mkt-klein">Kanäle wählen, um Links und Kennzahlen einzutragen.</p>';
  }
  function zeichneAblauf(e) {
    const st = e ? e.status : 'idee', R = S.d.rechte;
    $('#bt-status').innerHTML = statusPille(st);
    const stufen = ABLAUF.map((s) => `<span class="mkt-stufe${s === st ? ' jetzt' : ''}${ABLAUF.indexOf(s) < ABLAUF.indexOf(st) ? ' fertig' : ''}">${esc(statusName(s))}</span>`).join('');
    const knoepfe = [];
    if (R.bearbeiten) {
      const n = NAECHSTER[st];
      if (n && (n[0] !== 'geplant' || R.freigeben)) knoepfe.push(`<button type="button" class="btn primary" data-status="${n[0]}">${esc(n[1])}</button>`);
      if (st === 'freigabe' && !R.freigeben) knoepfe.push('<span class="mkt-klein">Wartet auf Freigabe durch eine berechtigte Person.</span>');
      if (st === 'freigabe' && R.freigeben) knoepfe.push('<button type="button" class="btn" data-status="produktion">Änderungen nötig</button>');
      if (['geplant', 'veroeffentlicht'].includes(st) && R.freigeben) knoepfe.push('<button type="button" class="btn" data-status="freigabe">Freigabe zurücknehmen</button>');
      if (st !== 'verworfen' && st !== 'veroeffentlicht') knoepfe.push('<button type="button" class="btn gefahr" data-status="verworfen">Verwerfen</button>');
      if (st === 'verworfen') knoepfe.push('<button type="button" class="btn" data-status="idee">Wieder aufnehmen</button>');
    }
    $('#bt-schritte').innerHTML = `<div class="mkt-stufen">${stufen}</div><div class="mkt-knoepfe">${knoepfe.join('')}</div>`;
    const f = e && e.freigabe;
    $('#bt-freigabe-info').textContent = f ? `Freigegeben von ${f.von} am ${deZeit(f.t)}` : (st === 'freigabe' ? 'Nach dem Freigeben ist der Beitrag veröffentlichungsbereit; Änderungen danach brauchen eine neue Freigabe.' : '');
  }
  function zeichneKommentare(e) {
    $('#bt-kommentare').innerHTML = e && e.kommentare.length ? e.kommentare.slice().reverse().map((k) => `<li><span class="mkt-avatar">${esc(initialen(k.von))}</span><div><b>${esc(k.von)}</b> <time>${esc(deZeit(k.t))}</time><p>${esc(k.text)}</p></div></li>`).join('') : '<li class="mkt-klein">Noch keine Kommentare.</li>';
    $('#bt-verlauf').innerHTML = e ? e.verlauf.slice().reverse().map((v) => `<li><time>${esc(deZeit(v.t))}</time><div>${esc(v.was)}<small>${esc(v.von)}</small></div></li>`).join('') : '';
    $('#bt-kommentar').disabled = !e; $('#bt-kommentar-add').disabled = !e;
    $('#bt-kommentar').placeholder = e ? 'Kommentar, z. B. Feedback zur Freigabe' : 'Kommentare nach dem ersten Speichern';
  }
  function fuelle(e, vorgabe = {}) {
    const E = S.d.einstellungen, x = e || { ...vorgabeBeitrag(), ...vorgabe };
    S.offen = e ? e.id : null;
    $('#bt-titel').value = x.titel || '';
    $('#bt-sub').textContent = e ? `angelegt ${e.erstellt ? 'von ' + e.erstellt.von + ' · ' : ''}zuletzt geändert ${e.geaendert ? deZeit(e.geaendert.t) + ' von ' + e.geaendert.von : ''}` : 'neuer Beitrag';
    $('#bt-hook').value = x.hook || ''; $('#bt-text').value = x.text || ''; $('#bt-hashtags').value = x.hashtags || ''; $('#bt-cta').value = x.cta || ''; $('#bt-notizen').value = x.notizen || '';
    $('#bt-marke').innerHTML = opts(E.marken, x.marke, '– keine –');
    $('#bt-format').innerHTML = opts(E.formate, x.format, '– offen –');
    $('#bt-saeule').innerHTML = opts(E.saeulen, x.saeule, '– keine –');
    $('#bt-kampagne').innerHTML = opts(S.d.kampagnen.filter((k) => !k.archiviert || k.id === x.kampagne), x.kampagne, '– keine –');
    $('#bt-verantwortlich').innerHTML = '<option value="">– niemand –</option>' + S.d.team.map((t) => `<option value="${esc(t.id)}"${t.id === x.verantwortlich ? ' selected' : ''}>${esc(t.name)}</option>`).join('')
      + (x.verantwortlich && !S.d.team.some((t) => t.id === x.verantwortlich) ? `<option value="${esc(x.verantwortlich)}" selected>${esc(x.verantwortlichName || 'nicht mehr im Team')}</option>` : '');
    $('#bt-prioritaet').value = x.prioritaet || 'normal';
    $('#bt-kanaele').innerHTML = '<legend>Kanäle</legend>' + E.kanaele.filter((k) => k.aktiv !== false || (x.kanaele || []).includes(k.id)).map((k) => `<label class="mkt-kanalwahl"><input type="checkbox" value="${esc(k.id)}"${(x.kanaele || []).includes(k.id) ? ' checked' : ''}><span>${esc(k.name)}</span></label>`).join('');
    $('#bt-dreh').value = x.drehtermin || ''; $('#bt-produktion').value = x.produktionBis || '';
    $('#bt-datum').value = (x.veroeffentlichung || '').slice(0, 10); $('#bt-zeit').value = (x.veroeffentlichung || '').slice(11, 16);
    $('#bt-ki').checked = !!x.ki; $('#bt-ki-hinweis').hidden = !x.ki;
    checkliste = (x.checkliste || []).map((p) => ({ ...p })); links = (x.links || []).map((l) => ({ ...l }));
    zeichneCheck(); zeichneLinks(); zeichneZaehler(); zeichneAblauf(e); zeichneVeroeff(e); zeichneKommentare(e);
    const b = darfBearbeiten();
    for (const el of $$('input, select, textarea', dlg)) if (!el.closest('[data-schliessen]') && el.id !== 'bt-kommentar') el.disabled = !b;
    for (const el of $$('[data-nur-bearbeiten]', dlg)) el.hidden = !b;
    $('#bt-loeschen').hidden = !(e && S.d.rechte.verwalten);
    $('#bt-duplizieren').hidden = !(e && b);
    $('#bt-meldung').textContent = ''; $('#bt-meldung').className = 'mkt-meldung';
    $('#bt-konflikt').hidden = true; $('#bt-verwerfen').hidden = true;
    S.schnappschuss = JSON.stringify(sammle());
  }
  function vorgabeBeitrag() {
    const E = S.d.einstellungen, aktiv = (l) => l.filter((x) => x.aktiv !== false);
    return { marke: aktiv(E.marken).length === 1 ? aktiv(E.marken)[0].id : '', kanaele: [], verantwortlich: S.d.team.some((t) => t.id === S.d.ich) ? S.d.ich : '', prioritaet: 'normal',
      kampagne: S.f.kampagne || '' };
  }
  function sammle() {
    const datum = $('#bt-datum').value, zeit = $('#bt-zeit').value;
    const f = { titel: $('#bt-titel').value.trim(), prioritaet: $('#bt-prioritaet').value, marke: $('#bt-marke').value, kanaele: $$('#bt-kanaele input:checked').map((x) => x.value),
      format: $('#bt-format').value, saeule: $('#bt-saeule').value, kampagne: $('#bt-kampagne').value, verantwortlich: $('#bt-verantwortlich').value,
      drehtermin: $('#bt-dreh').value, produktionBis: $('#bt-produktion').value, veroeffentlichung: datum ? datum + (zeit ? 'T' + zeit : '') : '',
      hook: $('#bt-hook').value, text: $('#bt-text').value, hashtags: $('#bt-hashtags').value, cta: $('#bt-cta').value, notizen: $('#bt-notizen').value,
      ki: $('#bt-ki').checked, checkliste, links };
    if (!$('#bt-veroeff').hidden) {
      f.veroeffentlicht = {}; f.ergebnisse = {};
      for (const z of $$('#bt-veroeff-felder [data-vk]')) {
        const k = z.dataset.vk, url = $('[data-v="url"]', z).value.trim();
        if (url) f.veroeffentlicht[k] = url;
        const zahlen = { reichweite: $('[data-v="reichweite"]', z).value, interaktionen: $('[data-v="interaktionen"]', z).value, aufrufe: $('[data-v="aufrufe"]', z).value };
        if (Object.values(zahlen).some((v) => v !== '')) f.ergebnisse[k] = Object.fromEntries(Object.entries(zahlen).map(([n, v]) => [n, v === '' ? null : Number(v)]));
      }
    }
    return f;
  }
  const geaendert = () => darfBearbeiten() && JSON.stringify(sammle()) !== S.schnappschuss;
  function oeffne(id, vorgabe) {
    const e = id ? beitrag(id) : null;
    if (id && !e) return;
    fuelle(e, vorgabe);
    if (!dlg.open) dlg.showModal();
    if (!e) $('#bt-titel').focus();
  }
  async function speichern(status) {
    const e = S.offen ? beitrag(S.offen) : null;
    const f = sammle(), m = $('#bt-meldung');
    if (!f.titel) { m.className = 'mkt-meldung fehler'; m.textContent = 'Bitte einen Titel angeben.'; $('#bt-titel').focus(); return null; }
    const body = { felder: f };
    if (e) { body.id = e.id; body.rev = e.rev; }
    if (status) body.status = status;
    $('#bt-speichern').disabled = true;
    const r = await api('marketing_beitrag_save', body);
    $('#bt-speichern').disabled = false;
    if (r.status === 409 && r.data.beitrag) {
      $('#bt-konflikt').hidden = false;
      $('#bt-konflikt').innerHTML = `${esc(r.data.error)} <button type="button" class="btn" id="bt-neu-laden">Neue Fassung laden</button>`;
      ersetze(r.data.beitrag); return null;
    }
    if (r.status !== 200) { m.className = 'mkt-meldung fehler'; m.textContent = fehlerText(r, 'Speichern fehlgeschlagen'); return null; }
    const vorher = e ? e.status : '';
    ersetze(r.data.beitrag);
    fuelle(r.data.beitrag);
    const n = r.data.beitrag;
    m.className = 'mkt-meldung ok';
    m.textContent = vorher === 'geplant' && n.status === 'freigabe' ? 'Gespeichert – der Beitrag war freigegeben und muss nach der Änderung erneut freigegeben werden.' : (status ? `Gespeichert: ${statusName(n.status)}.` : 'Gespeichert.');
    zeichne();
    return n;
  }
  $('#bt-form').addEventListener('submit', (e) => { e.preventDefault(); speichern(); });
  dlg.addEventListener('click', async (e) => {
    const t = e.target;
    const st = t.closest('[data-status]');
    if (st) {
      if (st.dataset.status === 'verworfen' && !(await frage('Beitrag verwerfen?', 'Der Beitrag bleibt erhalten und lässt sich später wieder aufnehmen.', 'Verwerfen'))) return;
      speichern(st.dataset.status); return;
    }
    if (t.closest('#bt-neu-laden')) { fuelle(beitrag(S.offen)); return; }
    if (t.closest('[data-schliessen]')) { schliessen(); return; }
    if (t.closest('#bt-verwerfen-ja')) { $('#bt-verwerfen').hidden = true; dlg.close(); return; }
    if (t.closest('#bt-verwerfen-nein')) { $('#bt-verwerfen').hidden = true; return; }
    if (t.closest('#bt-check-add')) { const v = $('#bt-check-neu').value.trim(); if (v) { checkliste.push({ text: v, erledigt: false }); $('#bt-check-neu').value = ''; zeichneCheck(); } $('#bt-check-neu').focus(); return; }
    const cw = t.closest('[data-check-weg]'); if (cw) { checkliste.splice(Number(cw.dataset.checkWeg), 1); zeichneCheck(); return; }
    const vl = t.closest('[data-vorlage]');
    if (vl) { for (const p of VORLAGEN[vl.dataset.vorlage]) if (!checkliste.some((c) => c.text === p)) checkliste.push({ text: p, erledigt: false }); zeichneCheck(); return; }
    if (t.closest('#bt-link-add')) {
      const url = $('#bt-link-url').value.trim(), titel = $('#bt-link-titel').value.trim();
      if (!/^https?:\/\/\S+$/i.test(url)) { $('#bt-meldung').className = 'mkt-meldung fehler'; $('#bt-meldung').textContent = 'Bitte eine Webadresse mit https:// angeben.'; return; }
      links.push({ titel, url }); $('#bt-link-url').value = ''; $('#bt-link-titel').value = ''; zeichneLinks(); return;
    }
    const lw = t.closest('[data-link-weg]'); if (lw) { links.splice(Number(lw.dataset.linkWeg), 1); zeichneLinks(); return; }
    if (t.closest('#bt-kommentar-add')) kommentieren();
    if (t.closest('#bt-duplizieren')) {
      const e0 = beitrag(S.offen);
      if (geaendert() && !(await frage('Ungespeicherte Änderungen', 'Die Kopie entsteht aus dem gespeicherten Stand. Änderungen vorher speichern?', 'Ohne Speichern kopieren'))) return;
      fuelle(null, { ...e0, titel: e0.titel + ' (Kopie)', veroeffentlichung: '', veroeffentlicht: {}, ergebnisse: {}, checkliste: e0.checkliste.map((p) => ({ text: p.text, erledigt: false })) });
      $('#bt-titel').focus(); $('#bt-titel').select();
    }
    if (t.closest('#bt-loeschen')) {
      const e0 = beitrag(S.offen);
      if (!(await frage('Beitrag endgültig löschen?', `„${e0.titel}“ wird mit Kommentaren und Verlauf gelöscht. Zum Aufheben ohne Löschen: „Verwerfen“.`, 'Endgültig löschen'))) return;
      const r = await api('marketing_beitrag_loeschen', { id: e0.id });
      if (r.status !== 200) { toast(fehlerText(r, 'Löschen fehlgeschlagen'), true); return; }
      S.d.beitraege = S.d.beitraege.filter((x) => x.id !== e0.id); dlg.close(); zeichne(); toast('Beitrag gelöscht.');
    }
  });
  dlg.addEventListener('change', (e) => {
    const c = e.target.closest('[data-check]'); if (c) { checkliste[Number(c.dataset.check)].erledigt = c.checked; zeichneCheck(); return; }
    if (e.target.closest('#bt-kanaele')) { zeichneZaehler(); zeichneVeroeff(S.offen ? beitrag(S.offen) : null); }
    if (e.target.id === 'bt-ki') $('#bt-ki-hinweis').hidden = !e.target.checked;
  });
  dlg.addEventListener('input', (e) => { if (['bt-text', 'bt-hashtags'].includes(e.target.id)) zeichneZaehler(); });
  dlg.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && e.target.id === 'bt-check-neu') { e.preventDefault(); $('#bt-check-add').click(); }
    if (e.key === 'Enter' && e.target.id === 'bt-kommentar') { e.preventDefault(); kommentieren(); }
    if (e.key === 'Enter' && ['bt-link-url', 'bt-link-titel'].includes(e.target.id)) { e.preventDefault(); $('#bt-link-add').click(); }
  });
  dlg.addEventListener('cancel', (e) => { if (geaendert()) { e.preventDefault(); $('#bt-verwerfen').hidden = false; } });
  dlg.addEventListener('close', () => { S.offen = null; zeichne(); });
  function schliessen() { if (geaendert()) { $('#bt-verwerfen').hidden = false; $('#bt-verwerfen-nein').focus(); return; } dlg.close(); }
  async function kommentieren() {
    const text = $('#bt-kommentar').value.trim(), e = beitrag(S.offen);
    if (!text || !e) return;
    const r = await api('marketing_kommentar', { id: e.id, text });
    if (r.status !== 200) { toast(fehlerText(r, 'Kommentar nicht gespeichert'), true); return; }
    $('#bt-kommentar').value = '';
    ersetze(r.data.beitrag);   // ungespeicherte Eingaben im Dialog bleiben; nur der Stand (rev) folgt dem Server
    zeichneKommentare(r.data.beitrag);
  }
  /* Kampagnen-Dialog schließen */
  $('#dlg-kampagne').addEventListener('click', (e) => { if (e.target.closest('[data-schliessen]')) $('#dlg-kampagne').close(); });

  /* ---------- Klicks in den Ansichten ---------- */
  document.addEventListener('click', (e) => {
    if (e.target.closest('dialog')) return;
    const o = e.target.closest('[data-oeffnen]'); if (o) { oeffne(o.dataset.oeffnen); return; }
    const n = e.target.closest('[data-neu-am]'); if (n) { oeffne(null, { veroeffentlichung: n.dataset.neuAm }); return; }
    const g = e.target.closest('[data-gehe]'); if (g) { zeigeTab(g.dataset.gehe); return; }
    if (e.target.closest('#mkt-neu')) { oeffne(null, {}); return; }
    if (e.target.closest('#mkt-export')) { exportieren(); return; }
    if (e.target.closest('[data-filter-leeren]')) { S.f = { q: '', marke: '', kanal: '', verantwortlich: '', kampagne: '', status: '', meine: false, verworfen: false }; zeichne(); return; }
    if (e.target.closest('[data-kampagne-neu]')) { kampagneDialog(null); return; }
    const k = e.target.closest('[data-kampagne]'); if (k) { kampagneDialog(kampagne(k.dataset.kampagne)); return; }
    const kl = e.target.closest('[data-kampagne-liste]'); if (kl) { S.f.kampagne = kl.dataset.kampagneListe; S.f.verworfen = false; zeigeTab('liste'); }
  });
  document.addEventListener('keydown', (e) => {
    if (e.target.closest && e.target.closest('dialog')) return;
    const o = e.target.closest && e.target.closest('article[data-oeffnen]');
    if (o && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); oeffne(o.dataset.oeffnen); }
  });
  document.addEventListener('submit', async (e) => {
    if (e.target.id !== 'idee-form') return;
    e.preventDefault();
    const titel = $('#idee-titel').value.trim();
    if (!titel) { $('#idee-titel').focus(); return; }
    const r = await api('marketing_beitrag_save', { felder: { ...vorgabeBeitrag(), titel } });
    if (r.status !== 200) { toast(fehlerText(r, 'Idee nicht gespeichert'), true); return; }
    ersetze(r.data.beitrag); zeichne(); toast('Idee gespeichert – im Board unter „Idee“.');
    $('#idee-titel').focus();
  });

  async function exportieren() {
    try {
      const res = await fetch(API + '?action=marketing_export', { method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: '{}' });
      if (!res.ok) { let t = ''; try { t = (await res.json()).error; } catch { /* kein JSON */ } throw new Error(t || `Export fehlgeschlagen (${res.status}).`); }
      const name = ((res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/) || [])[1] || 'Redaktionsplan.csv';
      const url = URL.createObjectURL(await res.blob());
      const a = Object.assign(document.createElement('a'), { href: url, download: name });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      toast(`${name} heruntergeladen.`);
    } catch (err) { toast(err.message === 'Failed to fetch' ? 'Keine Verbindung zum Server.' : (err.message || String(err)), true); }
  }

  /* ---------- Start ---------- */
  async function laden() {
    const st = await api('status');
    if (st.status === 401 && !st.json) { zeigeAnmeldung('./'); return; }
    if (st.status === 403 && st.data.code === 'reauth_required' && typeof st.data.anmelden === 'string' && st.data.anmelden.startsWith('/oidc/')) {
      location.assign(st.data.anmelden + encodeURIComponent(location.href)); return;
    }
    if (st.status === 403 && st.data.error) { fehler(st.data.error); return; }
    if (st.status === 0) { fehler('Keine Verbindung zum Server.'); return; }
    if (st.status !== 200 || !st.data.loggedIn) { zeigeAnmeldung(); return; }
    csrf = st.data.csrf || '';
    if (window.STAFL_THEME) { window.STAFL_THEME.konto(st.data.user, csrf, API); themaKnopf(); }   // Hell/Dunkel am Konto (theme.js)
    const name = st.data.user ? (st.data.user.name || st.data.user.username || '') : '';
    $('#mkt-user').hidden = false; $('#mkt-user-name').textContent = name; $('#mkt-initialen').textContent = initialen(name);
    const r = await api('marketing_start');
    if (r.status === 404) { fehler('Der Redaktionsplan ist für Sie noch nicht freigegeben.'); return; }
    if (r.status === 503) { fehler(r.data.error || 'Der Redaktionsplan wird gerade gewartet.'); return; }
    if (r.status === 403) { fehler(r.data.error || 'Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.'); return; }
    if (r.status === 401) { zeigeAnmeldung(r.json ? '' : './'); return; }
    if (r.status !== 200 || !r.data.ok) { fehler(fehlerText(r, 'Der Redaktionsplan konnte nicht geladen werden')); return; }
    setzeDaten(r.data);
    S.kal.warSchmal = schmal();
    $('#mkt-login').hidden = true; $('#mkt-app').hidden = false;
    const tab = location.hash.slice(1);
    const knopf = $(`#mkt-tabs button[data-tab="${CSS.escape(tab)}"]`);
    zeigeTab(knopf && !knopf.hidden ? tab : 'uebersicht');
  }
  themaKnopf();
  laden().catch(() => fehler('Keine Verbindung zum Server.'));
})();
