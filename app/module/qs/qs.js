/* STAFL-Plattform · Qualitätssicherung (QM-System) – Oberfläche nach dem Designvorschlag vom 30.10.2026. Anmeldung über
   den Status, alle Daten aus qs_start, Reiter über location.hash, Hell/Dunkel am Konto (theme.js).
   Ansichten: Übersicht (Kennzahlen; „Ihre Aufgaben“ = eigene Kontrollen, Dokumente zum Prüfen/Freigeben, eigene Entwürfe
   und Maßnahmen; fällige Prüfungen; Stand der Dokumente je Kapitel; offene Maßnahmen), Dokumente (Register je Kapitel mit
   Zustandsfilter, Seitenleiste mit Versionen, Ablauf Entwurf → Prüfung → Freigabe und Überprüfung), Handbuch (Kapitel mit
   Ziel, Abschnitte mit Verweisen, Suche, Drucken), Prüfplan (Jahresplan 6 Monate zurück, 5 voraus: erfüllte Tage/Wochen,
   Nachweise, Versäumnisse, geplante Fälligkeiten; Nachweis erfassen; Maßnahme aus einer Abweichung), Maßnahmen (Tafel
   offen → in Arbeit → umgesetzt → wirksam oder Liste; Eingabemaske im Aufbau des IFS-Maßnahmenplans), Einstellungen
   (Personen mit Kürzel und Mitarbeiter, Kapitel, Überprüfungsfrist, Datenpaket).
   Rechte und 4-Augen-Prinzip prüft der Server bei jeder Aktion (GR-103); ausgeblendete Knöpfe sind nur Anzeige.
   Kein Inline-Skript (CSP). */
'use strict';
(() => {
  const API = '../../api/';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const TABS = ['uebersicht', 'dokumente', 'handbuch', 'pruefplan', 'massnahmen', 'einstellungen'];
  const MONATE = ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'];
  const S = { csrf: '', d: null, tab: 'uebersicht', kap: '', zustand: '', ansicht: 'tafel', toast: 0, paket: null, dok: '', pruefung: '', edit: {}, grund: null, laden: null, wahl: null };

  /* ---------- Aufruf der API: wirft nie, liefert { status, data, json } ---------- */
  async function api(action, body, query = '') {
    let res;
    try {
      res = await fetch(API + '?action=' + action + query, {
        method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
        headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': S.csrf } : {}, body: body ? JSON.stringify(body) : undefined,
      });
    } catch { return { status: 0, data: {}, json: false }; }
    let data = null;
    try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
    return { status: res.status, data: data || {}, json: data !== null };
  }
  const fehlerText = (r, fallback) => (r.data && r.data.error) || (r.status === 0 ? 'Keine Verbindung zum Server.' : `${fallback} (${r.status}).`);
  function toast(text, fehlerhaft = false) {
    const t = $('#qm-toast');
    t.textContent = text; t.className = 'qm-toast zeigen' + (fehlerhaft ? ' fehler' : '');
    clearTimeout(S.toast); S.toast = setTimeout(() => { t.className = 'qm-toast'; }, fehlerhaft ? 4500 : 2400);
  }
  function fehler(text) { $('#qm-login').hidden = true; $('#qm-app').hidden = true; $('#qm-err').hidden = false; $('#qm-err').textContent = text; }
  function zeigeAnmeldung() { $$('dialog[open]').forEach((d) => d.close()); $('#qm-login').hidden = false; $('#qm-app').hidden = true; $('#qm-user').hidden = true; }
  const initialen = (name) => { const t = String(name || '').trim().split(/[\s.\-_]+/).filter(Boolean); return (t.length > 1 ? t[0][0] + t[1][0] : (t[0] || '?').slice(0, 2)).toLocaleUpperCase('de-DE'); };

  /* ---------- Formate und Hilfen ---------- */
  const datum = (iso) => (iso ? `${iso.slice(8, 10)}.${iso.slice(5, 7)}.${iso.slice(0, 4)}` : '');
  const zeitpunkt = (t) => { const d = new Date(t); return isNaN(d) ? '' : d.toLocaleString('de-DE', { dateStyle: 'short', timeStyle: 'short' }); };
  const zahl = (n) => Number(n).toLocaleString('de-DE');
  const darf = (r) => !!(S.d && S.d.rechte && S.d.rechte[r]);
  const natCmp = (a, b) => String(a).localeCompare(String(b), 'de', { numeric: true, sensitivity: 'base' });
  const person = (k) => S.d.personen.find((p) => p.id === k) || null;
  const mitarbeiterName = (id) => (S.d.mitarbeiter.find((m) => m.id === id) || { name: '' }).name;
  const meineKuerzel = () => S.d.ich.kuerzel || [];
  /* Kürzel mit Name als Hinweis */
  const wer = (k) => { if (!k) return '<span class="qm-null">—</span>'; const p = person(k); return p ? `<abbr title="${esc(p.name + (p.funktion ? ' · ' + p.funktion : ''))}">${esc(k)}</abbr>` : esc(k); };
  const werName = (k) => { const p = person(k); return p ? `${k} (${p.name})` : k; };
  const kapitelTitel = (id) => { const k = S.d.kapitel.find((x) => x.id === id); return k ? k.titel : ''; };
  const kapitelText = (id) => (id ? `${id} ${kapitelTitel(id)}`.trim() : '—');
  const chip = (text, farbe = '') => `<span class="qm-chip ${esc(farbe)}">${esc(text)}</span>`;
  const optionen = (liste, wahl) => Object.entries(liste).map(([k, v]) => `<option value="${esc(k)}"${k === wahl ? ' selected' : ''}>${esc(v)}</option>`).join('');
  const kapitelOptionen = (wahl, leer = '') => (leer ? `<option value="">${esc(leer)}</option>` : '')
    + S.d.kapitel.filter((k) => k.aktiv !== false || k.id === wahl).map((k) => `<option value="${esc(k.id)}"${k.id === wahl ? ' selected' : ''}>${esc(k.id + ' ' + k.titel)}${k.aktiv === false ? ' (inaktiv)' : ''}</option>`).join('');
  const link = (ablage) => (/^https?:\/\//i.test(ablage) ? `<a href="${esc(ablage)}" target="_blank" rel="noopener noreferrer">${esc(ablage)}</a>` : esc(ablage));
  const leerzeile = (spalten, text) => `<tr><td class="qm-leerzeile" colspan="${spalten}">${esc(text)}</td></tr>`;
  const icon = (n) => `<svg class="i" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const monatName = (m) => MONATE[Number(m.slice(5, 7)) - 1] + (m.slice(5, 7) === '01' ? ' ' + m.slice(2, 4) : '');
  const plusMonate = (m, n) => { const x = Number(m.slice(0, 4)) * 12 + Number(m.slice(5, 7)) - 1 + n; return `${Math.floor(x / 12)}-${String(x % 12 + 1).padStart(2, '0')}`; };

  /* Rückweg zum Dashboard auf der echten Adresse */
  if (/(^|\.)dashboard-stafl\.de$/.test(location.hostname)) $('#qm-zurueck').href = 'https://dashboard-stafl.de/';

  /* ---------- Hell/Dunkel ---------- */
  const dunkel = () => document.documentElement.getAttribute('data-theme') === 'dark'
    || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  function themaKnopf() {
    const d = dunkel(), b = $('#qm-theme');
    b.innerHTML = icon(d ? 'sun' : 'moon');
    b.setAttribute('aria-label', d ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }
  $('#qm-theme').addEventListener('click', () => { document.documentElement.setAttribute('data-theme', dunkel() ? 'light' : 'dark'); themaKnopf(); });
  document.addEventListener('stafl-theme', themaKnopf);

  /* ---------- Reiter ---------- */
  function zeigeTab(tab) {
    if (!TABS.includes(tab) || (tab === 'einstellungen' && !darf('verwalten'))) tab = 'uebersicht';
    S.tab = tab;
    $$('#qm-tabs [role="tab"]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.tab === tab)));
    $$('.qm-tab').forEach((x) => { x.hidden = x.dataset.tab !== tab; });
    history.replaceState(null, '', '#' + tab);
  }
  $('#qm-tabs').addEventListener('click', (ev) => { const b = ev.target.closest('[role="tab"]'); if (b) zeigeTab(b.dataset.tab); });
  window.addEventListener('hashchange', () => { if (S.d) { const t = location.hash.slice(1).split('/')[0]; if (t !== S.tab) zeigeTab(t || 'uebersicht'); } });

  /* ---------- Daten ---------- */
  function setzeDaten(d) {
    S.d = d;
    $('#qm-kuerzel').innerHTML = d.personen.filter((p) => p.aktiv !== false).map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    $('#qm-tabs [data-tab="einstellungen"]').hidden = !darf('verwalten');
    $('#qm-d-neu').hidden = !darf('bearbeiten');
    $('#qm-m-neu').hidden = !darf('bearbeiten');
    $('#qm-h-neu').hidden = !darf('freigeben');
    $('#qm-p-neu').hidden = !darf('freigeben');
    $('#qm-datei-wahl').accept = (d.ablage ? d.ablage.arten : []).map((e) => '.' + e).join(',');
    const gel = d.dokumente.filter((x) => istGelenkt(x) && x.zustand !== 'eingezogen').length;
    $('#qm-unterzeile').textContent = `IFS Wholesale · ${zahl(d.kapitel.length)} Kapitel · ${zahl(gel)} gelenkte Dokumente · ${zahl(d.handbuch.filter((a) => !a.entfallen).length)} Handbuch-Abschnitte · ${zahl(d.pruefungen.filter((p) => p.aktiv).length)} Prüfungen`;
  }
  async function neuLaden() {
    const r = await api('qs_start');
    if (r.status === 401) { zeigeAnmeldung(); return false; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Aktualisieren fehlgeschlagen'), true); return false; }
    setzeDaten(r.data);
    renderAlles();
    if ($('#dlg-pruefung').open) renderPruefung();
    return true;
  }
  function renderAlles() {
    filterOptionen();
    renderUebersicht(); renderDokumente(); renderDok(); renderHandbuch(); renderPruefplan(); renderMassnahmen();
    if (darf('verwalten')) renderEinstellungen();
  }
  function filterOptionen() {
    for (const sel of ['#qm-d-kapitel', '#qm-p-kapitel']) { const w = $(sel).value; $(sel).innerHTML = kapitelOptionen(w, 'alle Kapitel'); $(sel).value = w; }
    const art = $('#qm-d-art').value; $('#qm-d-art').innerHTML = '<option value="">alle Arten</option>' + optionen(S.d.arten, art);
    const st = $('#qm-m-status').value || 'nicht';
    $('#qm-m-status').innerHTML = '<option value="nicht">nicht abgeschlossen</option><option value="">alle</option>' + optionen(S.d.massnStatus, st); $('#qm-m-status').value = st;
    const bz = $('#qm-m-bezug').value;
    const bezuege = [...new Set(S.d.massnahmen.map((m) => m.bezug).filter(Boolean))].sort(natCmp);
    $('#qm-m-bezug').innerHTML = '<option value="">alle Audits / Bezüge</option>' + bezuege.map((b) => `<option${b === bz ? ' selected' : ''}>${esc(b)}</option>`).join('');
  }

  /* ---------- Dokumente: Zustand ---------- */
  const gueltige = (d) => { const v = (d.versionen || []).filter((x) => x.status === 'freigegeben'); return v.length ? v[v.length - 1] : null; };
  const offene = (d) => (d.versionen || []).find((x) => ['entwurf', 'pruefung', 'geprueft'].includes(x.status)) || null;
  const istGelenkt = (d) => S.d.gelenkt.includes(d.art);
  const eigen = (v) => !!v && (v.bearbeiter || []).map(String).includes(String(S.d.ich.id));
  const ueberFaellig = (d) => !!(d.ueberpruefung && d.ueberpruefung.faellig);
  const naechsteVersion = (d) => (d.versionen || []).reduce((n, v) => Math.max(n, Number(v.nr) || 0), 0) + 1;
  function zustandChip(d) {
    const o = offene(d), g = gueltige(d);
    if (d.zustand === 'eingezogen') return chip('eingezogen', 'rot');
    if (d.zustand === 'register') return chip(d.art === 'O' ? 'Ordner' : 'extern');
    if (o && o.status === 'pruefung') return chip(`Version ${naechsteVersion(d)} in Prüfung`, 'blau');
    if (o && o.status === 'geprueft') return chip('Freigabe offen', 'blau');
    if (o) return chip(g ? 'in Überarbeitung' : 'Entwurf', 'gelb');
    if (!g) return chip('nicht freigegeben');
    return ueberFaellig(d) ? chip('Überprüfung fällig', 'gelb') : chip('gültig', 'gruen');
  }
  /* erstellt · geprüft · freigegeben: Kürzel aus der Excel oder Initialen der Plattform-Namen */
  function beteiligte(v) {
    if (!v) return '<span class="qm-null">—</span>';
    const k = v.kuerzel || {};
    if (!k.erstellt && !k.geprueft && !k.freigegeben && !v.erstellt && !v.geprueft && !v.freigegeben) return '<span class="qm-null">—</span>';
    const teil = (kz, w, was) => (kz ? wer(kz) : w && w.von ? `<abbr title="${esc(was + ' von ' + w.von + ', ' + zeitpunkt(w.t))}">${esc(initialen(w.von))}</abbr>` : '–');
    return `<span class="qm-wer" title="erstellt · geprüft · freigegeben">${teil(k.erstellt, v.erstellt, 'erstellt')}${teil(k.geprueft, v.geprueft, 'geprüft')}${teil(k.freigegeben, v.freigegeben, 'freigegeben')}</span>`;
  }

  /* ---------- Prüfungen: Fälligkeit ---------- */
  const istMeine = (p) => (p.ausfuehrende || []).includes(S.d.ich.id) || meineKuerzel().includes(p.zustaendig) || meineKuerzel().includes(p.vertreter);
  const darfNachweis = (p) => !!p.aktiv && (darf('bearbeiten') || (darf('nachweis') && istMeine(p)));
  const istFaellig = (p) => !!p.aktiv && ['rot', 'gelb'].includes((p.faellig || {}).ampel);
  const quoteText = (f) => (f.quote ? `${f.quote.erfuellt}/${f.quote.faellig}` : '');
  const IV_KURZ = { arbeitstaeglich: 'arbeitstäglich', taeglich: 'täglich', anlass: 'bei Bedarf' };
  const ivKurz = (iv) => IV_KURZ[iv] || S.d.intervalle[iv] || iv;
  function faelligChip(p) {
    const f = p.faellig || {};
    if (!p.aktiv) return chip('inaktiv');
    if (p.intervall === 'anlass') return chip('bei Bedarf');
    if (f.art === 'kalender') {
      if (f.offen) return chip(f.restTage === 0 ? 'heute fällig' : `bis ${datum(f.naechste)}`, f.ampel);   // rot = zuletzt versäumt (Anzahl darunter)
      if (f.ampel === 'rot') return chip('zuletzt versäumt', 'rot');
      if (!f.anzahl && f.naechste > S.d.heute) return chip(`ab ${datum(f.naechste)}`);
      return chip(f.naechste ? `erledigt · nächste ${datum(f.naechste)}` : 'erledigt', 'gruen');
    }
    if (!f.naechste) return chip(f.anzahl ? 'fällig' : 'noch kein Nachweis', 'rot');
    if (f.restTage < 0) return chip(`${-f.restTage} ${f.restTage === -1 ? 'Tag' : 'Tage'} überfällig`, 'rot');
    if (f.ampel === 'gelb') return chip(f.restTage === 0 ? 'heute fällig' : `fällig in ${f.restTage} ${f.restTage === 1 ? 'Tag' : 'Tagen'}`, 'gelb');
    return chip(datum(f.naechste), 'gruen');
  }

  /* ---------- Übersicht ---------- */
  const massnStatusChip = (m) => chip(S.d.massnStatus[m.status] || m.status, { offen: 'gelb', in_arbeit: 'blau', umgesetzt: 'gruen', wirksam: 'gruen' }[m.status] || '');
  const offeneMassn = () => S.d.massnahmen.filter((m) => !['wirksam', 'verworfen'].includes(m.status));
  const sortFrist = (a, b) => (a.frist || '9999').localeCompare(b.frist || '9999') || natCmp(a.nr, b.nr);
  const meineMassn = (m) => meineKuerzel().some((k) => String(m.zustaendig || '').split(/[\s/,;]+/).includes(k));
  const kpi = (titel, wert, sub, farbe, ziel) => `<button type="button" class="qm-kpi ${farbe}" data-kpi="${esc(ziel)}"><span>${esc(titel)}</span><b>${esc(wert)}</b><small>${esc(sub)}</small></button>`;
  const aufgabeDok = (x, farbe, ic, text, knopf) => `<button class="qm-aufgabe" type="button" data-dok="${esc(x.id)}"><span class="qm-symbol ${farbe}">${icon(ic)}</span><span><b>${esc(x.nr)} ${esc(x.titel)}</b><span class="qm-sub">${esc(text)}</span></span>${chip(knopf, farbe)}</button>`;
  function renderUebersicht() {
    const d = S.d;
    $('#qm-u-leer').hidden = !d.leer;
    const gelenkt = d.dokumente.filter((x) => istGelenkt(x) && x.zustand !== 'eingezogen');
    const gueltig = gelenkt.filter((x) => gueltige(x));
    const ueber = gueltig.filter(ueberFaellig);
    const faellig = d.pruefungen.filter(istFaellig);
    const rot = faellig.filter((p) => p.faellig.ampel === 'rot');
    const heuteOffen = d.pruefungen.filter((p) => p.aktiv && p.faellig && p.faellig.art === 'kalender' && p.faellig.offen && p.faellig.restTage === 0).length;
    const massn = offeneMassn(), massnUeber = massn.filter((m) => m.ueberfaellig), wirk = massn.filter((m) => m.status === 'umgesetzt');
    const jahre = String(Math.round((d.einstellungen.ueberpruefungMonate || 36) / 12 * 10) / 10).replace('.', ',');
    $('#qm-u-kpis').innerHTML = kpi('Gültige Dokumente', zahl(gueltig.length), `gelenkt, in ${zahl(new Set(gueltig.map((x) => x.kapitel)).size)} Kapiteln`, '', 'dokumente')
      + kpi('Überprüfung fällig', zahl(ueber.length), `letzte Freigabe vor über ${jahre} Jahren`, ueber.length ? 'gelb' : '', 'ueberpruefung')
      + kpi('Prüfungen fällig', zahl(faellig.length), `${zahl(rot.length)} überfällig oder versäumt · ${zahl(heuteOffen)} heute offen`, rot.length ? 'warn' : '', 'pruefplan')
      + kpi('Offene Maßnahmen', zahl(massn.length), `${zahl(massnUeber.length)} über der Frist · ${zahl(wirk.length)} Wirksamkeit prüfen`, massnUeber.length ? 'warn' : '', 'massnahmen');
    // Ihre Aufgaben: eigene Kontrollen, Dokumente im Ablauf, eigene Maßnahmen
    const auf = [];
    for (const p of d.pruefungen.filter((x) => x.aktiv && x.intervall !== 'anlass' && x.faellig && x.faellig.offen && istMeine(x))) {
      auf.push({ rang: p.faellig.ampel === 'rot' ? 0 : 1, html: `<button class="qm-aufgabe" type="button" data-nachweis="${esc(p.id)}"><span class="qm-symbol ${p.faellig.ampel === 'rot' ? 'rot' : 'gelb'}">${icon('klemmbrett')}</span><span><b>${esc(p.titel)}</b><span class="qm-sub">Ihre Kontrolle · ${esc(ivKurz(p.intervall))}${p.faellig.quote ? ` · ${quoteText(p.faellig)} erfüllt` : ''}</span></span>${faelligChip(p)}</button>` });
    }
    for (const x of gelenkt) {
      const v = offene(x); if (!v) continue;
      if (darf('freigeben') && v.status === 'pruefung' && !eigen(v)) auf.push({ rang: 2, html: aufgabeDok(x, 'blau', 'lupe', `Prüfung · Entwurf von ${v.erstellt ? v.erstellt.von : '–'}: „${v.aenderungen}“`, 'Prüfen') });
      else if (darf('freigeben') && v.status === 'geprueft') auf.push({ rang: 2, html: aufgabeDok(x, 'gruen', 'schild', `Freigabe offen · geprüft von ${v.geprueft ? v.geprueft.von : '–'}`, 'Freigeben') });
      else if (eigen(v) && v.status === 'entwurf') auf.push({ rang: 3, html: aufgabeDok(x, 'gelb', 'stift', `Ihr Entwurf${(v.verlauf || []).some((l) => /zurückgegeben/i.test(l.was)) ? ' · zurückgegeben' : ''}: „${v.aenderungen}“`, 'Überarbeiten') });
    }
    if (darf('freigeben')) for (const x of ueber.filter((y) => !offene(y) && (meineKuerzel().includes(y.zustaendig)))) auf.push({ rang: 4, html: aufgabeDok(x, 'gelb', 'dokument', `Überprüfung fällig${x.ueberpruefung.faelligAb ? ' seit ' + datum(x.ueberpruefung.faelligAb) : ''}`, 'Überprüfen') });
    for (const m of massn.filter((y) => meineMassn(y) || (darf('freigeben') && y.status === 'umgesetzt'))) {
      auf.push({ rang: 5, html: `<button class="qm-aufgabe" type="button" data-massn="${esc(m.id)}"><span class="qm-symbol ${m.ueberfaellig ? 'rot' : 'blau'}">${icon('blitz')}</span><span><b>${esc(m.nr)} · ${esc(m.feststellung)}</b><span class="qm-sub">${m.status === 'umgesetzt' ? 'Wirksamkeit prüfen' : 'Ihre Maßnahme'}${m.frist ? ' · Frist ' + esc(datum(m.frist)) : ''}</span></span>${massnStatusChip(m)}</button>` });
    }
    auf.sort((a, b) => a.rang - b.rang);
    $('#qm-u-aufgaben').innerHTML = auf.length ? `<ul class="qm-aufgaben">${auf.slice(0, 12).map((a) => `<li>${a.html}</li>`).join('')}</ul>${auf.length > 12 ? `<p class="qm-hilfe">und ${zahl(auf.length - 12)} weitere</p>` : ''}`
      : `<p class="qm-leerzeile">${meineKuerzel().length || darf('freigeben') ? 'Keine offenen Aufgaben für Sie.' : 'Keine offenen Aufgaben. Ist Ihr Kürzel unter Einstellungen mit Ihnen verknüpft, erscheinen hier Ihre Kontrollen und Maßnahmen.'}</p>`;
    // Fällige Prüfungen
    const fl = [...faellig].sort((a, b) => (a.faellig.ampel === b.faellig.ampel ? 0 : a.faellig.ampel === 'rot' ? -1 : 1) || ((a.faellig.restTage ?? -9999) - (b.faellig.restTage ?? -9999)) || natCmp(a.titel, b.titel)).slice(0, 10);
    $('#qm-u-faellig').innerHTML = fl.length ? `<ul class="qm-aufgaben">${fl.map((p) => `<li><button class="qm-aufgabe" type="button" data-pruefung="${esc(p.id)}"><span class="qm-symbol ${p.faellig.ampel}">${icon('klemmbrett')}</span><span><b>${esc(p.titel)}</b><span class="qm-sub">${esc(p.kapitel)} · ${esc(ivKurz(p.intervall))}${p.faellig.versaeumtAnzahl ? ` · ${zahl(p.faellig.versaeumtAnzahl)} versäumt` : ''}</span></span>${faelligChip(p)}</button></li>`).join('')}</ul>${faellig.length > 10 ? `<p class="qm-hilfe">und ${zahl(faellig.length - 10)} weitere im Prüfplan</p>` : ''}`
      : '<p class="qm-leerzeile">Keine Prüfung fällig.</p>';
    // Stand der Dokumente je Kapitel
    $('#qm-u-kapitel').innerHTML = d.kapitel.filter((k) => k.aktiv !== false).map((k) => {
      const ds = gueltig.filter((x) => x.kapitel === k.id), alt = ds.filter(ueberFaellig).length, n = ds.length;
      const a = n ? Math.round((n - alt) / n * 100) : 0;
      return `<button type="button" data-kap-dok="${esc(k.id)}"><span class="qm-kapnr">${esc(k.id)}</span><span class="qm-name">${esc(k.titel)}</span><small>${n ? `${zahl(n)} Dok.${alt ? ' · ' + zahl(alt) + ' fällig' : ''}` : 'keine Dokumente'}</small><span class="qm-balken"><i class="gruen" style="width:${a}%"></i><i class="gelb" style="width:${n ? 100 - a : 0}%"></i></span></button>`;
    }).join('') || '<p class="qm-leerzeile">Noch keine Kapitel.</p>';
    const ml = [...massn].sort(sortFrist).slice(0, 8);
    $('#qm-u-massn').innerHTML = ml.length ? massnTabelle(ml) : '<p class="qm-leerzeile">Keine offenen Maßnahmen.</p>';
  }
  $('#qm-u-kpis').addEventListener('click', (ev) => {
    const b = ev.target.closest('[data-kpi]'); if (!b) return;
    if (b.dataset.kpi === 'ueberpruefung' || b.dataset.kpi === 'dokumente') { S.zustand = b.dataset.kpi === 'dokumente' ? 'aktuell' : 'ueberpruefung'; $('#qm-d-kapitel').value = ''; renderDokumente(); zeigeTab('dokumente'); }
    else if (b.dataset.kpi === 'pruefplan') { $('#qm-p-faellig').checked = true; renderPruefplan(); zeigeTab('pruefplan'); }
    else zeigeTab(b.dataset.kpi);
  });
  $('#qm-u-kapitel').addEventListener('click', (ev) => { const b = ev.target.closest('[data-kap-dok]'); if (b) { $('#qm-d-kapitel').value = b.dataset.kapDok; S.zustand = ''; renderDokumente(); zeigeTab('dokumente'); } });
  /* Klicks auf Einträge überall auf der Seite (nicht in Eingabemasken) */
  document.addEventListener('click', (ev) => {
    if (!S.d || ev.target.closest('dialog')) return;
    const g = ev.target.closest('[data-gehe]'); if (g) { zeigeTab(g.dataset.gehe); return; }
    const nw = ev.target.closest('[data-nachweis]'); if (nw) { oeffneNachweis(nw.dataset.nachweis); return; }
    const d = ev.target.closest('[data-dok]'); if (d) { oeffneDok(d.dataset.dok); return; }
    const p = ev.target.closest('[data-pruefung]'); if (p) { oeffnePruefung(p.dataset.pruefung); return; }
    const m = ev.target.closest('[data-massn]'); if (m) oeffneMassnahme(m.dataset.massn);
  });

  /* ---------- Dokumente ---------- */
  const ZUSTAENDE = [['', 'Alle'], ['aktuell', 'Aktuell'], ['ueberpruefung', 'Überprüfung fällig', 'gelb'], ['arbeit', 'In Arbeit'], ['ohne', 'Ohne Freigabe'], ['eingezogen', 'Eingezogen'], ['register', 'Ordner & extern']];
  function passtZustand(x, z) {
    if (!z) return true;
    if (z === 'aktuell') return x.zustand === 'gueltig' && !ueberFaellig(x);
    if (z === 'ueberpruefung') return ueberFaellig(x);
    if (z === 'arbeit') return x.zustand === 'entwurf' || x.zustand === 'pruefung';
    return x.zustand === z;
  }
  function renderDokumente() {
    const q = $('#qm-d-suche').value.trim().toLocaleLowerCase('de-DE'), kap = $('#qm-d-kapitel').value, art = $('#qm-d-art').value;
    const basis = S.d.dokumente.filter((x) => (!kap || x.kapitel === kap) && (!art || x.art === art) && (!q || `${x.nr} ${x.titel}`.toLocaleLowerCase('de-DE').includes(q)));
    $('#qm-d-zustand').innerHTML = ZUSTAENDE.map(([z, n, f]) => { const c = basis.filter((x) => passtZustand(x, z)).length; return (z && !c && S.zustand !== z) ? '' : `<button type="button" data-zustand="${z}" aria-pressed="${S.zustand === z}" class="${f || ''}">${esc(n)} <b>${zahl(c)}</b></button>`; }).join('');
    const liste = basis.filter((x) => passtZustand(x, S.zustand))
      .sort((a, b) => natCmp(a.kapitel, b.kapitel) || (istGelenkt(a) === istGelenkt(b) ? 0 : istGelenkt(a) ? -1 : 1) || natCmp(a.nr, b.nr) || natCmp(a.titel, b.titel));
    let html = '', kapAlt = null;
    for (const x of liste) {
      if (x.kapitel !== kapAlt) {
        kapAlt = x.kapitel; const k = S.d.kapitel.find((y) => y.id === x.kapitel) || {};
        html += `<tr class="qm-gruppe"><td colspan="6"><b>${esc(kapitelText(x.kapitel))}</b>${k.zustaendig ? ` <span class="qm-sub">Zuständig ${esc(k.zustaendig)}${k.vertreter ? ' · Vertreter ' + esc(k.vertreter) : ''}</span>` : ''}</td></tr>`;
      }
      const g = gueltige(x), nd = aktiv(istGelenkt(x) ? (g ? g.dateien : []) : x.dateien).length;
      html += `<tr class="qm-klick${x.zustand === 'eingezogen' ? ' qm-aus' : ''}${x.id === S.dok ? ' qm-gewaehlt' : ''}" data-dok="${esc(x.id)}">
        <td class="qm-nr qm-mobil-weg" data-label="Nr.">${esc(x.nr) || '<span class="qm-null">—</span>'}</td>
        <td class="qm-voll" data-label="Titel"><span class="qm-name">${x.nr ? `<span class="qm-nur-mobil">${esc(x.nr)} · </span>` : ''}${esc(x.titel)}</span><span class="qm-sub">${esc(S.d.arten[x.art] || x.art)}${x.ablage && !istGelenkt(x) ? ' · ' + esc(x.ablage) : ''}${nd ? ` · <span class="qm-anz" title="${nd === 1 ? '1 Datei' : nd + ' Dateien'} in der Ablage">${icon('klammer')}${zahl(nd)}</span>` : ''}</span></td>
        <td class="qm-zahl" data-label="Version">${g ? esc(g.nr) : '—'}</td>
        <td data-label="Freigabe">${g && g.datum ? esc(datum(g.datum)) : '—'}</td>
        <td data-label="Status">${zustandChip(x)}</td>
        <td data-label="erstellt · geprüft · frei">${istGelenkt(x) ? beteiligte(g) : ''}</td></tr>`;
    }
    $('#qm-d-liste').innerHTML = `<table class="qm-tabelle qm-karten"><thead><tr><th>Nr.</th><th>Titel</th><th class="qm-zahl">Vers.</th><th>Freigabe</th><th>Status</th><th>erstellt · geprüft · frei</th></tr></thead><tbody>${html || leerzeile(6, S.d.dokumente.length ? 'Keine passenden Dokumente.' : 'Noch keine Dokumente.')}</tbody></table>`;
  }
  ['#qm-d-suche', '#qm-d-kapitel', '#qm-d-art'].forEach((s) => $(s).addEventListener('input', renderDokumente));
  $('#qm-d-zustand').addEventListener('click', (ev) => { const b = ev.target.closest('[data-zustand]'); if (b) { S.zustand = b.dataset.zustand; renderDokumente(); } });
  $('#qm-d-csv').addEventListener('click', () => ladeCsv('dokumente', `QM-Dokumentenliste_${S.d.heute}.csv`));
  $('#qm-d-zip').addEventListener('click', oeffneExport);
  $('#qm-d-neu').addEventListener('click', () => oeffneDokForm(''));

  /* Dokument in der Seitenleiste (unter 1100 px als Blatt von unten) */
  function oeffneDok(id) {
    if (!S.d.dokumente.some((x) => x.id === id)) return;
    if (S.laden && S.laden.fertig && S.laden.dok !== id) S.laden = null;
    S.dok = id;
    if (S.tab !== 'dokumente') zeigeTab('dokumente');
    renderDokumente(); renderDok();
    $('#qm-dk').scrollTop = 0;
  }
  function schliesseDok() { S.dok = ''; if (S.laden && S.laden.fertig) S.laden = null; renderDok(); renderDokumente(); }

  /* ---------- Dokumentenablage (Server: qs_datei_hochladen, qs_datei, qs_datei_entfernen, qs_ablage_export) ----------
     Gelenkte Dokumente tragen Dateien je Version, Ordner und externe Dokumente am Dokument. Ablegen und Entfernen im
     Entwurf mit „bearbeiten“ (zählt für das 4-Augen-Prinzip), an freigegebenen Versionen nur mit „freigeben“ (nachtragen,
     entfernen mit Grund); in der Prüfung nur ansehen. Die Regeln prüft der Server – hier nur, was angeboten wird. */
  const aktiv = (l) => (l || []).filter((f) => !f.entfernt);
  const groesseText = (n) => (n >= 1048576 ? `${(n / 1048576).toLocaleString('de-DE', { maximumFractionDigits: 1 })} MB` : `${zahl(Math.max(1, Math.round(n / 1024)))} KB`);
  function ablageOffen(x, v) {
    if (x.eingezogen || !darf('bearbeiten')) return false;
    if (!istGelenkt(x)) return !v;
    if (!v) return false;
    if (v.status === 'entwurf') return true;
    return ['freigegeben', 'ersetzt'].includes(v.status) && darf('freigeben');
  }
  /* Herkunft und Platzhalter einer Datei (Bauabschnitt 3: Vorlagen, Lenkungsangaben bei der Freigabe) */
  const platzhalterText = (l) => (l || []).map((k) => ((S.d.ablage || {}).platzhalter || {})[k] || k).join(', ');
  function dateiHerkunft(f, v) {
    const t = [];
    if (f.vorlage) t.push(`aus ${esc(f.vorlage.nr)}`);
    if (f.uebernommen) t.push(`aus Version ${esc(f.uebernommen)}`);
    if (f.ausgefuellt) t.push('Lenkungsangaben eingetragen');
    else if ((f.platzhalter || []).length && (!v || ['entwurf', 'pruefung', 'geprueft'].includes(v.status)))
      t.push(`<span class="qm-platzhalter" title="Platzhalter in der Datei">{{…}} ${esc(platzhalterText(f.platzhalter))}</span>`);
    return t.length ? ' · ' + t.join(' · ') : '';
  }
  function dateiListe(x, v, leer) {
    const alle = (v ? v.dateien : x.dateien) || [], da = aktiv(alle), weg = alle.filter((f) => f.entfernt), offen = ablageOffen(x, v);
    let h = da.length ? `<ul class="qm-dateien">${da.map((f) => `<li class="qm-datei"><button class="qm-datei-name" type="button" data-datei="${esc(f.id)}" title="${esc(f.name)} herunterladen">${icon('dokument')}<span>${esc(f.name)}</span></button>`
      + `<span class="qm-sub">${esc(groesseText(f.groesse))}${f.hochgeladen ? ` · ${esc(f.hochgeladen.von)} · ${esc(datum(String(f.hochgeladen.t).slice(0, 10)))}` : ''}${f.nachgetragen ? ' · nachgetragen' : ''}${dateiHerkunft(f, v)}</span>`
      + `${offen ? `<button class="qm-datei-weg" type="button" data-datei-weg="${esc(f.id)}" aria-label="${esc(f.name)} entfernen" title="Entfernen">×</button>` : ''}</li>`).join('')}</ul>`
      : (leer ? `<p class="qm-hilfe">${esc(leer)}</p>` : '');
    if (weg.length) h += `<details class="qm-details qm-entfernt"><summary>${weg.length === 1 ? '1 Datei entfernt' : zahl(weg.length) + ' Dateien entfernt'}</summary><ul class="qm-verlauf">${weg.map((f) => `<li><s>${esc(f.name)}</s> · ${esc(zeitpunkt(f.entfernt.t))} · ${esc(f.entfernt.von)}: ${esc(f.entfernt.grund)}</li>`).join('')}</ul></details>`;
    return h;
  }
  function ablageZone(x, v, text, klein = false) {
    if (!ablageOffen(x, v)) return '';
    const a = S.d.ablage || { arten: [], max: 0 }, mb = zahl(Math.round(a.max / 1048576));
    return `<div class="qm-drop${klein ? ' klein' : ''}" role="button" tabindex="0" data-drop="${esc(v ? v.id : '')}" aria-label="${esc(text)}: Dateien hierher ziehen oder auswählen"`
      + ` title="Erlaubt: ${esc(a.arten.join(', '))} – bis ${mb} MB je Datei">${icon(klein ? 'plus' : 'upload')}`
      + `<span><b>${esc(text)}</b><span>hierher ziehen oder <u>auswählen</u><small> · bis ${mb} MB je Datei</small></span></span></div>`;
  }
  const ladenText = (e) => e.fehler || (e.fertig ? 'abgelegt' : e.empfangen ? `${Math.round(100 * e.empfangen / e.groesse)} %` : 'wartet');
  function ladenHtml(x, vid) {
    const L = S.laden;
    if (!L || L.dok !== x.id || L.version !== vid) return '';
    return `<ul class="qm-laden" aria-live="polite">${L.liste.map((e, i) => `<li data-laden="${i}" class="${e.fehler ? 'fehler' : e.fertig ? 'fertig' : ''}"><span title="${esc(e.name)}">${esc(e.name)}</span><progress max="${e.groesse}" value="${e.empfangen}"></progress><small>${esc(ladenText(e))}</small></li>`).join('')}</ul>`;
  }
  function ladenAktualisieren(i) {
    const e = S.laden && S.laden.liste[i], li = $(`#qm-dk [data-laden="${i}"]`);
    if (!e || !li) return;
    li.className = e.fehler ? 'fehler' : e.fertig ? 'fertig' : '';
    $('progress', li).value = e.empfangen; $('small', li).textContent = ladenText(e);
  }
  const alsBase64 = (blob) => new Promise((ok, nein) => {
    const r = new FileReader();
    r.onload = () => { const t = String(r.result); ok(t.slice(t.indexOf(',') + 1)); };
    r.onerror = () => nein(r.error);
    r.readAsDataURL(blob);
  });
  async function pruefsumme(f) {   // SHA-256 (nur in sicheren Kontexten verfügbar; sonst prüft der Server nur die Größe)
    try {
      if (!window.crypto || !crypto.subtle) return '';
      return [...new Uint8Array(await crypto.subtle.digest('SHA-256', await f.arrayBuffer()))].map((b) => b.toString(16).padStart(2, '0')).join('');
    } catch { return ''; }
  }
  /* Dateien nacheinander in Teilen hochladen (der API-Einstieg nimmt nur JSON bis 6 MB an) */
  async function hochladen(dateien, vid) {
    const x = S.d.dokumente.find((y) => y.id === S.dok), a = S.d.ablage;
    if (!x || !a || !dateien || !dateien.length) return;
    if (S.laden && !S.laden.fertig) { toast('Bitte warten, bis die laufenden Dateien abgelegt sind.', true); return; }
    const liste = [...dateien].map((f) => {
      const ext = f.name.includes('.') ? f.name.split('.').pop().toLowerCase() : '';
      const fehler = !a.arten.includes(ext) ? (ext ? `Dateiart „.${ext}“ nicht erlaubt.` : 'Dateiart nicht erlaubt (ohne Endung).') : !f.size ? 'Die Datei ist leer.' : f.size > a.max ? `Zu groß (höchstens ${zahl(Math.round(a.max / 1048576))} MB).` : '';
      return { datei: f, name: f.name, groesse: f.size || 1, empfangen: 0, fehler, fertig: false };
    });
    S.laden = { dok: x.id, version: vid, liste, fertig: false };
    renderDok();
    let ok = 0;
    for (let i = 0; i < liste.length; i++) {
      const e = liste[i];
      if (e.fehler) continue;
      const f = e.datei, sha = await pruefsumme(f);
      let upload = '', teil = 0, pos = 0;
      for (;;) {
        const stueck = f.slice(pos, pos + a.teil);
        let daten;
        try { daten = await alsBase64(stueck); } catch { e.fehler = 'Die Datei ist nicht lesbar.'; break; }
        const r = await api('qs_datei_hochladen', { dokument: x.id, version: vid, name: f.name, groesse: f.size, sha256: sha, upload, teil, daten });
        if (r.status === 401) { S.laden = null; zeigeAnmeldung(); return; }
        if (r.status !== 200 || !r.data.ok) { e.fehler = fehlerText(r, 'Hochladen fehlgeschlagen'); break; }
        pos += stueck.size; teil++; e.empfangen = pos;
        if (r.data.fertig) { e.fertig = true; ok++; break; }
        upload = r.data.upload;
        ladenAktualisieren(i);
      }
      ladenAktualisieren(i);
    }
    S.laden.fertig = true;
    const fehl = liste.filter((e) => e.fehler);
    if (!fehl.length) S.laden = null;
    if (ok) await neuLaden(); else renderDok();
    if (!fehl.length) toast(ok === 1 ? 'Datei abgelegt' : `${zahl(ok)} Dateien abgelegt`);
    else toast(fehl.length === 1 ? `${fehl[0].name}: ${fehl[0].fehler}` : `${zahl(fehl.length)} Dateien nicht abgelegt – Gründe in der Liste.`, true);
  }
  function waehleDateien(vid) { S.wahl = vid; const i = $('#qm-datei-wahl'); i.value = ''; i.click(); }
  $('#qm-datei-wahl').addEventListener('change', (ev) => { const f = [...ev.target.files]; ev.target.value = ''; if (f.length && S.wahl !== null) hochladen(f, S.wahl); });
  function dateiOrt(x, id) {
    for (const f of x.dateien || []) if (f.id === id) return { f, v: null };
    for (const v of x.versionen || []) for (const f of v.dateien || []) if (f.id === id) return { f, v };
    return null;
  }
  function speichereDatei(blob, name) {
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob); a.download = name;
    document.body.append(a); a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1500);
  }
  async function herunterladen(id) {
    const x = S.d.dokumente.find((y) => y.id === S.dok), ort = x ? dateiOrt(x, id) : null;
    let res;
    try { res = await fetch(API + '?action=qs_datei&id=' + encodeURIComponent(id), { credentials: 'same-origin', cache: 'no-store' }); } catch { toast('Keine Verbindung zum Server.', true); return; }
    if (res.status === 401) { zeigeAnmeldung(); return; }
    if (!res.ok) { let d = {}; try { d = await res.json(); } catch { /* keine JSON-Antwort */ } toast(d.error || `Herunterladen fehlgeschlagen (${res.status}).`, true); return; }
    speichereDatei(await res.blob(), ort ? ort.f.name : 'Datei');
  }
  async function entferneDatei(id) {
    const x = S.d.dokumente.find((y) => y.id === S.dok), ort = x ? dateiOrt(x, id) : null;
    if (!ort) return;
    const entwurf = !!ort.v && ort.v.status === 'entwurf';
    const g = await frageGrund('Datei entfernen', entwurf ? `„${ort.f.name}“ wird aus dem Entwurf gelöscht.`
      : `„${ort.f.name}“ wird nicht mehr angeboten und nicht mehr exportiert. Sie bleibt mit Grund als „entfernt“ vermerkt.`, entwurf ? 'Grund (optional)' : 'Grund', !entwurf);
    if (g === null) return;
    const r = await api('qs_datei_entfernen', { datei: id, rev: x.rev, grund: g });
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Entfernen fehlgeschlagen'), true); if (r.status === 409) await neuLaden(); return; }
    if (S.laden && S.laden.fertig) S.laden = null;
    toast('Datei entfernt'); await neuLaden();
  }
  /* Ziehen und Ablegen: Felder hervorheben, sobald Dateien über die Seite gezogen werden; daneben nichts im Browser öffnen */
  const hatDateien = (ev) => !!ev.dataTransfer && [...(ev.dataTransfer.types || [])].includes('Files');
  const imFeld = (ev) => (ev.target && ev.target.closest ? ev.target.closest('.qm-drop') : null);
  let ziehen = 0;
  window.addEventListener('dragenter', (ev) => { if (hatDateien(ev)) { ziehen++; document.body.classList.add('qm-zieht'); } });
  window.addEventListener('dragleave', (ev) => { if (hatDateien(ev) && --ziehen <= 0) { ziehen = 0; document.body.classList.remove('qm-zieht'); } });
  window.addEventListener('dragover', (ev) => {
    if (!hatDateien(ev)) return;
    ev.preventDefault();
    const z = imFeld(ev);
    ev.dataTransfer.dropEffect = z ? 'copy' : 'none';
    $$('.qm-drop.drueber').forEach((d) => { if (d !== z) d.classList.remove('drueber'); });
    if (z) z.classList.add('drueber');
  });
  window.addEventListener('drop', (ev) => {
    if (!hatDateien(ev)) return;
    ev.preventDefault();
    ziehen = 0; document.body.classList.remove('qm-zieht');
    const z = imFeld(ev);
    $$('.qm-drop.drueber').forEach((d) => d.classList.remove('drueber'));
    if (z && $('#qm-dk').contains(z)) hochladen(ev.dataTransfer.files, z.dataset.drop);
  });
  $('#qm-dk').addEventListener('keydown', (ev) => { const z = imFeld(ev); if (z && (ev.key === 'Enter' || ev.key === ' ')) { ev.preventDefault(); waehleDateien(z.dataset.drop); } });

  /* Export der Ablage als ZIP: der Server erstellt das Archiv erst beim Herunterladen (direkt in die Antwort) */
  function exportUmfang(kap, alle) {
    let n = 0, b = 0;
    const dazu = (l) => aktiv(l).forEach((f) => { n++; b += f.groesse || 0; });
    for (const x of S.d.dokumente) {
      if ((kap && x.kapitel !== kap) || (x.eingezogen && !alle)) continue;
      dazu(x.dateien);
      for (const v of x.versionen || []) if (v.status === 'freigegeben' || (alle && v.status !== 'verworfen')) dazu(v.dateien);
    }
    return { n, b };
  }
  function exportHinweis() {
    const { n, b } = exportUmfang($('#az-kapitel').value, $('#az-alle').checked);
    $('#az-umfang').textContent = n ? `${n === 1 ? '1 Datei' : zahl(n) + ' Dateien'} · ${groesseText(b)} und die Dokumentenliste` : 'Noch keine Dateien – das Archiv enthält nur die Dokumentenliste.';
  }
  function oeffneExport() {
    $('#az-kapitel').innerHTML = kapitelOptionen($('#qm-d-kapitel').value, 'Alle Kapitel');
    exportHinweis();
    oeffne($('#dlg-ablage'));
  }
  $('#az-kapitel').addEventListener('change', exportHinweis);
  $('#az-alle').addEventListener('change', exportHinweis);
  $('#az-form').addEventListener('submit', (ev) => {
    ev.preventDefault();
    const kap = $('#az-kapitel').value, q = (kap ? '&kapitel=' + encodeURIComponent(kap) : '') + ($('#az-alle').checked ? '&alle=1' : '');
    const a = document.createElement('a');
    a.href = API + '?action=qs_ablage_export' + q; a.download = '';
    document.body.append(a); a.click(); a.remove();
    $('#dlg-ablage').close();
    toast('Das ZIP wird erstellt und heruntergeladen …');
  });

  function renderDok() {
    const p = $('#qm-dk'), x = S.d.dokumente.find((y) => y.id === S.dok);
    // Ungespeicherte Stichworte des Entwurfs über ein Neuzeichnen retten (z. B. nach dem Ablegen einer Datei)
    const ae = $('#dk-aend', p), ag = $('#dk-grund', p);
    const merk = x && ae && ag && !ae.readOnly && p.dataset.dok === x.id ? { ver: p.dataset.ver, a: ae.value, a0: ae.defaultValue, g: ag.value, g0: ag.defaultValue } : null;
    $('#qm-d-raster').classList.toggle('mit-panel', !!x);
    p.hidden = !x;
    if (!x) { S.dok = ''; p.innerHTML = ''; p.dataset.dok = ''; return; }
    const o = offene(x), g = gueltige(x), gelenkt = istGelenkt(x), u = x.ueberpruefung;
    const chips = [];
    if (g) chips.push(chip(`Version ${g.nr} gültig${g.datum ? ' seit ' + datum(g.datum) : ''}`, 'gruen'));
    if (o) chips.push(chip(o.status === 'entwurf' ? `Version ${naechsteVersion(x)} im Entwurf` : o.status === 'pruefung' ? `Version ${naechsteVersion(x)} in Prüfung` : 'Freigabe offen', o.status === 'entwurf' ? 'gelb' : 'blau'));
    if (u) chips.push(u.faellig ? chip(`Überprüfung fällig${u.faelligAb ? ' seit ' + datum(u.faelligAb) : ''}`, 'gelb') : chip(`nächste Überprüfung ${datum(u.faelligAb)}`));
    if (x.zustand === 'eingezogen') chips.push(chip('eingezogen', 'rot'));
    if (!gelenkt) chips.push(chip(x.art === 'O' ? 'Ordner' : 'externes Dokument'));
    const zp = person(x.zustaendig);
    const zust = x.zustaendig ? `${wer(x.zustaendig)}${zp ? ' ' + esc(zp.name) : ''}${x.vertreter ? ' · Vertreter ' + wer(x.vertreter) : ''}` : '—';
    let karte = '';
    if (o) {
      const kannEdit = o.status === 'entwurf' && darf('bearbeiten');
      const schritt = (klasse, titel, text) => `<li class="${klasse}"><b>${klasse === 'fertig' ? icon('haken') : ''}${esc(titel)}</b><span>${esc(text)}</span></li>`;
      const entwurfTxt = o.erstellt ? `${o.erstellt.von} · ${datum(o.erstellt.t.slice(0, 10))}` : '';
      const pruefTxt = o.geprueft ? `${o.geprueft.von} · ${datum(o.geprueft.t.slice(0, 10))}` : (darf('freigeben') && !eigen(o) ? 'durch Sie möglich' : 'nicht durch den Ersteller');
      karte = `<section class="qm-karte"><h3>Überarbeitung zu Version ${naechsteVersion(x)}</h3>
        <ol class="qm-schritte">${schritt(o.status === 'entwurf' ? 'jetzt' : 'fertig', 'Entwurf', entwurfTxt)}${schritt(o.status === 'pruefung' ? 'jetzt' : o.status === 'geprueft' ? 'fertig' : 'offen', 'Prüfung', pruefTxt)}${schritt(o.status === 'geprueft' ? 'jetzt' : 'offen', 'Freigabe', 'Datum = Freigabetag')}</ol>
        <div class="qm-formraster">
          <label class="qm-breit">Änderungen<input class="qm-eingabe" id="dk-aend" maxlength="2000" value="${esc(o.aenderungen)}"${kannEdit ? '' : ' readonly'}></label>
          <label class="qm-breit">Änderungsgrund<input class="qm-eingabe" id="dk-grund" maxlength="1000" value="${esc(o.grund)}"${kannEdit ? '' : ' readonly'}></label>
        </div>
        <div class="qm-ablage"><b class="qm-ablage-titel">${icon('klammer')}Dateien zu Version ${naechsteVersion(x)}</b>${dateiListe(x, o, 'Noch keine Dateien.')}${ablageZone(x, o, 'Dateien ablegen')}${ladenHtml(x, o.id)}
          ${aktiv(o.dateien).some((f) => (f.platzhalter || []).length) && nrStruktur(x.art) ? '<p class="qm-hilfe qm-lenkung">Bei der Freigabe trägt das System Version, Freigabedatum und Kürzel in die Platzhalter der Word-/Excel-Dateien ein.</p>' : ''}
          ${o.status === 'entwurf' && darf('freigeben') && !eigen(o) && ablageOffen(x, o) ? '<p class="qm-hilfe">Wer im Entwurf Dateien ablegt oder entfernt, zählt als Bearbeiter und kann ihn danach nicht mehr prüfen (4-Augen-Prinzip).</p>' : ''}</div>
        ${o.status === 'pruefung' && darf('freigeben') && eigen(o) ? '<p class="qm-hilfe">Sie haben diesen Entwurf erstellt oder geändert – prüfen muss eine andere Person (4-Augen-Prinzip).</p>' : ''}
        ${o.status !== 'entwurf' && !darf('freigeben') ? '<p class="qm-hilfe">Wartet auf Prüfung und Freigabe durch QMB oder Geschäftsführung.</p>' : ''}
        <div class="qm-knopfreihe">${kannEdit ? '<button class="btn" type="button" data-schritt="verwerfen">Verwerfen</button><button class="btn" type="button" data-schritt="speichern">Entwurf speichern</button><button class="btn primary" type="button" data-schritt="einreichen">Zur Prüfung geben</button>' : ''}${darf('freigeben') && o.status !== 'entwurf' ? '<button class="btn" type="button" data-schritt="zurueck">Zurückgeben</button>' : ''}${darf('freigeben') && o.status === 'pruefung' && !eigen(o) ? '<button class="btn" type="button" data-schritt="pruefen">Nur prüfen</button><button class="btn primary" type="button" data-schritt="pruefen_freigeben">Prüfen und freigeben</button>' : ''}${darf('freigeben') && o.status === 'geprueft' ? '<button class="btn primary" type="button" data-schritt="freigeben">Freigeben</button>' : ''}</div>
        ${(o.verlauf || []).length ? `<ul class="qm-verlauf">${o.verlauf.map((l) => `<li>${esc(zeitpunkt(l.t))} · ${esc(l.von)}: ${esc(l.was)}</li>`).join('')}</ul>` : ''}</section>`;
    } else if (gelenkt && !x.eingezogen && darf('bearbeiten')) {
      karte = `<section class="qm-karte"><h3>Überarbeiten</h3><p class="qm-hilfe">Änderungen und Grund in Stichworten (Handbuch 2.0.11). Die Versionsnummer zählt erst mit der Freigabe hoch.</p>
        <div class="qm-formraster"><label class="qm-breit">Änderungen<input class="qm-eingabe" id="dk-aend" maxlength="2000" placeholder="z. B. Ablauf ergänzt"></label>
        <label class="qm-breit">Änderungsgrund<input class="qm-eingabe" id="dk-grund" maxlength="1000" placeholder="z. B. Internes Audit"></label></div>
        ${g && aktiv(g.dateien).length ? `<label class="qm-check"><input type="checkbox" id="dk-dateien" checked> Dateien der Version ${esc(g.nr)} übernehmen (${zahl(aktiv(g.dateien).length)}) – mit ihren Platzhaltern</label>` : ''}
        <div class="qm-knopfreihe">${darf('freigeben') && g ? '<button class="btn" type="button" data-schritt="ueberprueft">Ohne Änderung überprüft</button>' : ''}<button class="btn primary" type="button" data-schritt="neu">Überarbeitung beginnen</button></div></section>`;
    }
    const vers = [...(x.versionen || [])].reverse();
    const versHtml = !gelenkt ? '<p class="qm-hilfe">Ordner und externe Dokumente stehen nur im Register – ohne Versionen.</p>'
      : vers.length ? `<div class="qm-versionen">${vers.map((v) => `<div class="qm-version${['ersetzt', 'verworfen'].includes(v.status) ? ' qm-aus' : ''}"><b>${esc(v.nr || naechsteVersion(x))}</b><span>${esc(datum(v.datum)) || '—'}</span><span>${beteiligte(v)}</span>${chip(S.d.verStatus[v.status] || v.status, { freigegeben: 'gruen', entwurf: 'gelb', pruefung: 'blau', geprueft: 'blau' }[v.status] || '')}${v.aenderungen || v.grund ? `<span class="qm-sub">${esc(v.aenderungen)}${v.grund ? ' – ' + esc(v.grund) : ''}</span>` : ''}${['ersetzt', 'verworfen'].includes(v.status) && ((v.dateien || []).length || ablageOffen(x, v)) ? `<div class="qm-version-dateien">${dateiListe(x, v, '')}${ablageZone(x, v, 'Datei nachtragen', true)}${ladenHtml(x, v.id)}</div>` : ''}</div>`).join('')}</div>`
        : '<p class="qm-hilfe">Noch keine Version.</p>';
    const vorlageKarte = x.art === 'V' && !x.eingezogen ? `<section class="qm-karte qm-vorlagenkarte"><h3>${icon('dokument')}Vorlage für neue Dokumente</h3>
      <p class="qm-hilfe">„Dokument anlegen“ mit dieser Vorlage kopiert die Word-/Excel-Datei der gültigen Version und füllt die Platzhalter {{Nr}}, {{Titel}}, {{Kapitel}}, {{Art}}, {{Zuständig}}, {{Vertreter}} aus.
      {{Version}}, {{Datum}}, {{Erstellt}}, {{Geprüft}}, {{Freigegeben}}, {{Änderungen}} und {{Grund}} trägt die Freigabe des neuen Dokuments ein. Platzhalter wie {{Nr}} einfach als Text in Kopf- oder Fußzeile bzw. Zelle schreiben.</p>
      ${vorlageNutzbar(x) ? '' : '<p class="qm-meldung">Noch nicht nutzbar: Es braucht eine freigegebene Version mit einer Word- oder Excel-Datei (.docx, .dotx, .xlsx, .xltx, .xlsm).</p>'}</section>` : '';
    const ablage = !gelenkt ? `<section class="qm-ablage"><h3 class="qm-zwischen">${icon('klammer')}Dateien</h3>${dateiListe(x, null, 'Noch keine Dateien.')}${ablageZone(x, null, 'Dateien ablegen')}${ladenHtml(x, '')}</section>`
      : g ? `<section class="qm-ablage"><h3 class="qm-zwischen">${icon('klammer')}Dateien · Version ${esc(g.nr)}</h3>${dateiListe(x, g, 'Zur gültigen Version liegen keine Dateien.')}${ablageZone(x, g, 'Datei nachtragen')}${ladenHtml(x, g.id)}</section>` : '';
    p.innerHTML = `<div class="qm-dp-kopf"><div><span class="qm-sub">${esc(S.d.arten[x.art] || x.art)}${x.nr ? ' · ' + esc(x.nr) : ''}</span><h2>${esc(x.titel)}</h2></div><button class="qm-dialog-schliessen" type="button" data-dk="schliessen" aria-label="Dokument schließen">×</button></div>
      <div class="qm-chips">${chips.join('')}</div>
      <dl class="qm-dl"><dt>Kapitel</dt><dd>${esc(kapitelText(x.kapitel))}</dd><dt>Zuständig</dt><dd>${zust}</dd>${x.ablage ? `<dt>Ablage</dt><dd>${link(x.ablage)}</dd>` : ''}${x.notiz ? `<dt>Notiz</dt><dd>${esc(x.notiz)}</dd>` : ''}${x.ueberprueft ? `<dt>Überprüft</dt><dd>${esc(datum(x.ueberprueft.t.slice(0, 10)))} · ${esc(x.ueberprueft.von)}${x.ueberprueft.notiz ? ' – ' + esc(x.ueberprueft.notiz) : ''}</dd>` : ''}${x.eingezogen ? `<dt>Eingezogen</dt><dd>${esc(zeitpunkt(x.eingezogen.t))} · ${esc(x.eingezogen.von)}: ${esc(x.eingezogen.grund)}</dd>` : ''}</dl>
      ${ablage}
      ${vorlageKarte}
      ${karte}
      <section><h3 class="qm-zwischen">Versionen</h3>${versHtml}</section>
      ${(x.verlauf || []).length ? `<details class="qm-details"><summary>Verlauf</summary><ul class="qm-verlauf">${x.verlauf.slice().reverse().map((l) => `<li>${esc(zeitpunkt(l.t))} · ${esc(l.von)}: ${esc(l.was)}</li>`).join('')}</ul></details>` : ''}
      <p class="qm-meldung" id="dk-meldung" role="alert"></p>
      <div class="qm-dp-fuss">${darf('bearbeiten') ? `<button class="btn" type="button" data-schritt="angaben">${icon('stift')}Angaben ändern</button>` : ''}${darf('freigeben') && (vers.length || !gelenkt) ? (x.eingezogen ? '<button class="btn" type="button" data-schritt="wieder">Wieder gültig machen</button>' : '<button class="btn" type="button" data-schritt="einziehen">Einziehen</button>') : ''}</div>`;
    p.dataset.dok = x.id; p.dataset.ver = o ? o.id : '';
    const ne = $('#dk-aend', p), ng = $('#dk-grund', p);
    if (merk && ne && ng && !ne.readOnly && merk.ver === p.dataset.ver) { if (merk.a !== merk.a0) ne.value = merk.a; if (merk.g !== merk.g0) ng.value = merk.g; }
  }
  const dokBody = (x) => ({ kapitel: x.kapitel, art: x.art, nr: x.nr, titel: x.titel, ablage: x.ablage, zustaendig: x.zustaendig, vertreter: x.vertreter, notiz: x.notiz });
  $('#qm-dk').addEventListener('click', async (ev) => {
    if (ev.target.closest('[data-dk="schliessen"]')) { schliesseDok(); return; }
    const dl = ev.target.closest('[data-datei]'); if (dl) { herunterladen(dl.dataset.datei); return; }
    const weg = ev.target.closest('[data-datei-weg]'); if (weg) { entferneDatei(weg.dataset.dateiWeg); return; }
    const z = imFeld(ev); if (z) { waehleDateien(z.dataset.drop); return; }
    const b = ev.target.closest('[data-schritt]'); if (!b) return;
    const x = S.d.dokumente.find((y) => y.id === S.dok); if (!x) return;
    const s = b.dataset.schritt;
    $('#dk-meldung').textContent = '';
    if (s === 'angaben') { oeffneDokForm(x.id); return; }
    let action = 'qs_version_schritt', body = { dokument: x.id, rev: x.rev, schritt: s }, ok = '';
    if (s === 'speichern' || s === 'neu') {
      action = 'qs_version_save'; body = { dokument: x.id, rev: x.rev, aenderungen: $('#dk-aend').value, grund: $('#dk-grund').value }; ok = s === 'neu' ? 'Überarbeitung begonnen' : 'Entwurf gespeichert';
      if (s === 'neu' && $('#dk-dateien') && $('#dk-dateien').checked) body.dateien = true;
    }
    else if (s === 'einziehen' || s === 'wieder') {
      let grund = '';
      if (s === 'einziehen') { grund = await frageGrund('Dokument einziehen', `„${x.nr} ${x.titel}“ wird ungültig. Offene Entwürfe werden verworfen; alle Versionen bleiben einsehbar.`, 'Grund', true); if (grund === null) return; }
      action = 'qs_dokument_save'; body = { ...dokBody(x), id: x.id, rev: x.rev, eingezogen: s === 'einziehen', einzugGrund: grund }; ok = s === 'einziehen' ? 'Dokument eingezogen' : 'Dokument wieder gültig';
    } else if (s === 'ueberprueft') {
      const g = await frageGrund('Ohne Änderung überprüft', 'Das Dokument ist weiter aktuell – die Frist bis zur nächsten Überprüfung beginnt heute neu.', 'Notiz (optional)', false);
      if (g === null) return;
      body.grund = g; ok = 'Als überprüft vermerkt';
    } else if (s === 'zurueck' || s === 'verwerfen') {
      const g = await frageGrund(s === 'zurueck' ? 'Zur Überarbeitung zurückgeben' : 'Entwurf verwerfen', s === 'zurueck' ? 'Der Entwurf geht an den Ersteller zurück.' : 'Der Entwurf bleibt in den Versionen als „verworfen“ sichtbar.', s === 'zurueck' ? 'Was ist zu ändern?' : 'Grund (optional)', s === 'zurueck');
      if (g === null) return;
      body.grund = g; ok = s === 'zurueck' ? 'Zurückgegeben' : 'Entwurf verworfen';
    } else if (s === 'einreichen') {
      const o = offene(x);   // geänderte Stichworte vorher mitspeichern
      if (o && ($('#dk-aend').value !== o.aenderungen || $('#dk-grund').value !== o.grund)) {
        const r0 = await api('qs_version_save', { dokument: x.id, rev: x.rev, aenderungen: $('#dk-aend').value, grund: $('#dk-grund').value });
        if (r0.status !== 200 || !r0.data.ok) { $('#dk-meldung').textContent = fehlerText(r0, 'Speichern fehlgeschlagen'); return; }
        body.rev = r0.data.dokument.rev;
      }
      ok = 'Zur Prüfung gegeben';
    } else ok = { pruefen: 'Als geprüft vermerkt', freigeben: 'Freigegeben', pruefen_freigeben: 'Geprüft und freigegeben' }[s] || 'Gespeichert';
    $$('#qm-dk button').forEach((k) => { k.disabled = true; });
    const r = await api(action, body);
    $$('#qm-dk button').forEach((k) => { k.disabled = false; });
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { const t = fehlerText(r, 'Speichern fehlgeschlagen'); if (r.status === 409) await neuLaden(); const m2 = $('#dk-meldung'); if (m2) m2.textContent = t; return; }
    const neu = r.data.dokument;
    if (neu && /freigegeben/i.test(ok) && gueltige(neu)) ok = `Version ${gueltige(neu).nr} freigegeben`;
    toast(ok); await neuLaden();
  });
  document.addEventListener('keydown', (ev) => { if (ev.key === 'Escape' && S.dok && !$('dialog[open]')) schliesseDok(); });

  /* Dokument anlegen / Angaben ändern – Nummer nach der Struktur „<Kapitel>-<Art><laufende Nr.>“ (z. B. 1.4-F08); der Server
     prüft sie und vergibt die nächste freie, wenn das Feld leer bleibt (oder noch den Vorschlag enthält). Neue Dokumente der
     Arten A, F, L, E können aus einer Vorlage (Art V mit freigegebener Word-/Excel-Datei) entstehen. */
  const nrStruktur = (art) => ((S.d.ablage || {}).nrStruktur || []).includes(art);
  const officeDateien = (v) => aktiv(v && v.dateien).filter((f) => ((S.d.ablage || {}).office || []).includes(f.art));
  const vorlageNutzbar = (x) => x.art === 'V' && !x.eingezogen && officeDateien(gueltige(x)).length > 0;
  function vorlagePasst(x, art) {   // „Vorlage F“ bzw. Titel mit „Formblatt“ passt zur Art F
    const name = (S.d.arten[art] || '').toLocaleLowerCase('de-DE');
    return new RegExp(`(^|\\s)${art}$`, 'i').test(x.nr || '') || (name && `${x.titel}`.toLocaleLowerCase('de-DE').includes(name));
  }
  function dfVorlagen() {
    const art = $('#df-art').value, neu = !S.edit.dok, liste = S.d.dokumente.filter(vorlageNutzbar);
    const z = $('#df-vorlage-z'), sel = $('#df-vorlage');
    z.hidden = !neu || !nrStruktur(art) || !liste.length;
    if (z.hidden) { sel.innerHTML = ''; return; }
    const alt = sel.dataset.art === art ? sel.value : null, passend = liste.find((x) => vorlagePasst(x, art));
    sel.innerHTML = '<option value="">— ohne Vorlage —</option>' + liste.sort((a, b) => natCmp(a.nr, b.nr)).map((x) => `<option value="${esc(x.id)}">${esc(x.nr)} · ${esc(x.titel)}</option>`).join('');
    sel.value = alt !== null ? alt : (passend ? passend.id : '');
    sel.dataset.art = art;
  }
  function naechsteNr(kap, art) {
    if (!kap || !S.d.gelenkt.includes(art)) return '';
    const re = new RegExp('^' + kap.replace(/\./g, '\\.') + '-' + art + '(\\d+)', 'i');
    let n = 0; for (const x of S.d.dokumente) { const m = re.exec(x.nr || ''); if (m) n = Math.max(n, parseInt(m[1], 10)); }
    return `${kap}-${art}${String(n + 1).padStart(2, '0')}`;
  }
  function oeffneDokForm(id) {
    const x = id ? S.d.dokumente.find((y) => y.id === id) : null;
    S.edit.dok = x;
    $('#df-titel').textContent = x ? 'Angaben ändern' : 'Dokument anlegen';
    $('#df-kapitel').innerHTML = kapitelOptionen(x ? x.kapitel : ($('#qm-d-kapitel').value || ''), x ? '' : 'Kapitel wählen');
    $('#df-art').innerHTML = optionen(S.d.arten, x ? x.art : 'F');
    $('#df-nr').value = x ? x.nr : ''; $('#df-nr').dataset.vorschlag = '';
    $('#df-titel-in').value = x ? x.titel : ''; $('#df-ablage').value = x ? x.ablage : '';
    $('#df-zust').value = x ? x.zustaendig : ''; $('#df-vertr').value = x ? x.vertreter : ''; $('#df-notiz').value = x ? x.notiz : ''; $('#df-aend').value = '';
    $('#df-aend-z').hidden = !!x;
    $('#df-vorlage').dataset.art = '';
    dfHilfe();
    oeffne($('#dlg-dokform'));
    $('#df-titel-in').focus();
  }
  function dfHilfe() {
    const art = $('#df-art').value, x = S.edit.dok, kap = $('#df-kapitel').value, nr = $('#df-nr');
    dfVorlagen();
    const mitVorlage = !$('#df-vorlage-z').hidden && $('#df-vorlage').value;
    $('#df-hilfe').textContent = S.d.gelenkt.includes(art)
      ? (x ? 'Inhaltliche Änderungen laufen über „Überarbeiten“ (neue Version mit Prüfung und Freigabe).'
        : 'Ein neues gelenktes Dokument startet als Entwurf; gültig wird es erst mit Prüfung und Freigabe.'
          + (nrStruktur(art) ? ' Die Nummer folgt der Struktur Kapitel-Art-laufende Nummer; leer gelassen vergibt das System die nächste freie.' : '')
          + (mitVorlage ? ' Die Datei der Vorlage liegt danach mit Nr., Titel und Kapitel im Entwurf; Version, Freigabedatum und Kürzel trägt die Freigabe ein.' : ''))
      : 'Ordner und externe Dokumente stehen nur im Register (ohne Versionen und Freigabe).';
    nr.placeholder = art === 'V' ? 'z. B. Vorlage F' : nrStruktur(art) && kap ? `automatisch (${naechsteNr(kap, art)})` : '';
    if (!x) {
      const v = nrStruktur(art) ? naechsteNr(kap, art) : '';
      if (!nr.value || nr.value === nr.dataset.vorschlag) { nr.value = v; nr.dataset.vorschlag = v; }
    } else if (nrStruktur(art)) {   // Kapitel oder Art geändert: neue Nummer nach der Struktur, zurück: alte Nummer
      const v = kap === x.kapitel && art === x.art ? x.nr : naechsteNr(kap, art);
      if (!nr.value || nr.value === nr.dataset.vorschlag || nr.value === x.nr) { nr.value = v; nr.dataset.vorschlag = v === x.nr ? '' : v; }
    }
  }
  ['#df-art', '#df-kapitel'].forEach((s) => $(s).addEventListener('input', dfHilfe));
  $('#df-vorlage').addEventListener('change', dfHilfe);
  $('#df-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const x = S.edit.dok;
    const nr = $('#df-nr'), nrWert = nr.value.trim();
    // unveränderter Vorschlag: leer schicken – der Server vergibt die nächste freie Nummer (auch wenn jemand gleichzeitig anlegt)
    const body = { kapitel: $('#df-kapitel').value, art: $('#df-art').value, nr: nrStruktur($('#df-art').value) && nr.dataset.vorschlag && nrWert === nr.dataset.vorschlag ? '' : nrWert,
      titel: $('#df-titel-in').value, ablage: $('#df-ablage').value, zustaendig: $('#df-zust').value, vertreter: $('#df-vertr').value, notiz: $('#df-notiz').value };
    if (x) { body.id = x.id; body.rev = x.rev; } else body.aenderungen = $('#df-aend').value;
    if (!x && !$('#df-vorlage-z').hidden && $('#df-vorlage').value) body.vorlage = $('#df-vorlage').value;
    const d = await senden(ev.target, 'qs_dokument_save', body);
    if (!d) return;
    $('#dlg-dokform').close();
    toast(x ? 'Angaben gespeichert' : body.vorlage ? `${d.dokument.nr} aus Vorlage angelegt` : `${d.dokument.nr || 'Dokument'} angelegt`);
    await neuLaden();
    oeffneDok(d.dokument.id);
  });

  /* ---------- Handbuch ---------- */
  function abschnitteSichtbar() {
    const q = $('#qm-h-suche').value.trim().toLocaleLowerCase('de-DE'), alle = $('#qm-h-entfallen').checked;
    return S.d.handbuch.filter((a) => (alle || !a.entfallen) && (!q || [a.nr, a.titel, a.text, ...(a.verweise || []), a.ifs].join(' ').toLocaleLowerCase('de-DE').includes(q)));
  }
  const markiere = (text, q) => { const t = esc(text); if (!q) return t; const e = esc(q).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); return t.replace(new RegExp(e, 'gi'), (m) => `<mark>${m}</mark>`); };
  /* Verweis „1.3-L02 HACCP-Analyse“ → Dokument, wenn die Dokumenten-Nr. vorne steht */
  function verweisDok(text) {
    const t = text.toLocaleLowerCase('de-DE').replace(/\s+/g, ' ');
    let best = null;
    for (const x of S.d.dokumente) { const nr = (x.nr || '').toLocaleLowerCase('de-DE'); if (nr && (t === nr || t.startsWith(nr + ' ') || t.startsWith(nr + '_')) && (!best || nr.length > best.nr.length)) best = x; }
    return best;
  }
  const istZiel = (a) => /^ziel\b/i.test(a.titel || '');
  function renderHandbuch() {
    const q = $('#qm-h-suche').value.trim();
    const sicht = abschnitteSichtbar();
    const zahlJe = {}; sicht.forEach((a) => { zahlJe[a.kapitel] = (zahlJe[a.kapitel] || 0) + 1; });
    if (S.kap && !S.d.kapitel.some((k) => k.id === S.kap)) S.kap = '';
    $('#qm-h-kapitel').innerHTML = `<li><button type="button" data-kap=""${S.kap === '' ? ' aria-current="true"' : ''}><span class="qm-kapnr">∑</span><span class="qm-name">Alle Kapitel</span><span class="qm-anzahl">${zahl(sicht.length)}</span></button></li>`
      + S.d.kapitel.map((k) => `<li><button type="button" data-kap="${esc(k.id)}"${S.kap === k.id ? ' aria-current="true"' : ''}><span class="qm-kapnr">${esc(k.id)}</span><span class="qm-name">${esc(k.titel)}</span><span class="qm-anzahl">${zahl(zahlJe[k.id] || 0)}</span></button></li>`).join('');
    let liste = sicht.filter((a) => !S.kap || a.kapitel === S.kap);
    const k = S.d.kapitel.find((x) => x.id === S.kap);
    const ziel = k && !q ? liste.find(istZiel) : null;
    if (ziel) liste = liste.filter((a) => a !== ziel);
    $('#qm-h-ueber').textContent = k ? `Kapitel ${k.id}` : 'QM-Handbuch';
    $('#qm-h-titel').textContent = k ? k.titel : 'Alle Kapitel';
    const letzte = (k ? sicht.filter((a) => a.kapitel === k.id) : sicht).flatMap((a) => (a.aenderungen || []).map((c) => c.datum)).filter(Boolean).sort().pop();
    $('#qm-h-meta').textContent = (k ? [k.zustaendig ? 'Zuständig ' + werName(k.zustaendig) : '', k.vertreter ? 'Vertreter ' + werName(k.vertreter) : '', `${zahl(liste.length + (ziel ? 1 : 0))} Abschnitte`]
      : [`${zahl(sicht.length)} Abschnitte in ${zahl(new Set(sicht.map((a) => a.kapitel)).size)} Kapiteln`, q ? `Suche „${q}“` : '']).concat(letzte ? [`letzte Änderung ${datum(letzte)}`] : []).filter(Boolean).join(' · ');
    $('#qm-h-ziel').hidden = !ziel;
    $('#qm-h-ziel').innerHTML = ziel ? `<b>Ziel.</b> ${esc(ziel.text)}${darf('freigeben') ? ` <button class="btn sm ghost" type="button" data-abschnitt="${esc(ziel.id)}">Ändern</button>` : ''}` : '';
    let html = '', kapAlt = null;
    for (const a of liste) {
      if (!S.kap && a.kapitel !== kapAlt) { kapAlt = a.kapitel; html += `<h2 class="qm-kapitelkopf">${esc(kapitelText(a.kapitel))}</h2>`; }
      const l = (a.aenderungen || []).filter((c) => c.was || c.grund).slice(-1)[0];
      html += `<article class="qm-abschnitt qm-glas${a.entfallen ? ' qm-entfallen' : ''}">
        <header><h3>${a.nr ? `<span class="qm-nr">${markiere(a.nr, q)}</span>` : ''}${markiere(a.titel, q)}</h3>${darf('freigeben') ? `<button class="btn sm ghost" type="button" data-abschnitt="${esc(a.id)}">${icon('stift')}Ändern</button>` : ''}</header>
        ${a.text ? `<p class="qm-text">${markiere(a.text, q)}</p>` : ''}
        ${(a.verweise || []).length ? `<div class="qm-verweise">${a.verweise.map((v) => { const dk = verweisDok(v); return dk ? `<button class="qm-verweis" type="button" data-dok="${esc(dk.id)}" title="Dokument öffnen">${icon('dokument')}${markiere(v, q)}${gueltige(dk) ? ' · V' + esc(gueltige(dk).nr) : ''}</button>` : `<span class="qm-verweis">${markiere(v, q)}</span>`; }).join('')}</div>` : ''}
        <footer>${a.ifs ? `<span>IFS ${esc(a.ifs)}</span>` : ''}${a.zustaendig ? `<span>Zuständig ${wer(a.zustaendig)}</span>` : ''}${a.vertreter ? `<span>Vertreter ${wer(a.vertreter)}</span>` : ''}${l ? `<span>Letzte Änderung${l.datum ? ' ' + esc(datum(l.datum)) : ''}: ${esc(l.was)}${l.grund ? ' – ' + esc(l.grund) : ''}</span>` : ''}${a.entfallen ? '<span>entfallen</span>' : ''}</footer>
      </article>`;
    }
    $('#qm-h-abschnitte').innerHTML = html || (ziel ? '' : `<p class="qm-leer-text qm-glas">${S.d.handbuch.length ? 'Keine passenden Abschnitte.' : 'Das Handbuch ist noch leer.'}</p>`);
  }
  $('#qm-h-kapitel').addEventListener('click', (ev) => { const b = ev.target.closest('[data-kap]'); if (b) { S.kap = b.dataset.kap; renderHandbuch(); } });
  ['#qm-h-suche', '#qm-h-entfallen'].forEach((s) => $(s).addEventListener('input', renderHandbuch));
  $('#qm-h-druck').addEventListener('click', () => window.print());
  $('#qm-h-neu').addEventListener('click', () => oeffneAbschnitt(''));
  $('#qm-t-handbuch').addEventListener('click', (ev) => { const b = ev.target.closest('[data-abschnitt]'); if (b) oeffneAbschnitt(b.dataset.abschnitt); });
  function oeffneAbschnitt(id) {
    const a = id ? S.d.handbuch.find((x) => x.id === id) : null;
    S.edit.abschnitt = a;
    $('#ab-titel').textContent = a ? (a.nr ? `Abschnitt ${a.nr} ändern` : 'Abschnitt ändern') : 'Abschnitt hinzufügen';
    $('#ab-kapitel').innerHTML = kapitelOptionen(a ? a.kapitel : S.kap, a || S.kap ? '' : 'Kapitel wählen');
    $('#ab-nr').value = a ? a.nr : ''; $('#ab-titel-in').value = a ? a.titel : ''; $('#ab-text').value = a ? a.text : '';
    $('#ab-verweise').value = a ? (a.verweise || []).join('\n') : ''; $('#ab-ifs').value = a ? a.ifs : '';
    $('#ab-zust').value = a ? a.zustaendig : ''; $('#ab-vertr').value = a ? a.vertreter : '';
    $('#ab-entfallen').checked = !!(a && a.entfallen); $('#ab-entfallen-z').hidden = !a;
    $('#ab-aend').value = a ? '' : 'Neu angelegt'; $('#ab-grund').value = '';
    $('#ab-aenderungen').innerHTML = a ? (a.aenderungen || []).slice().reverse().map((c) => `<li>${esc(datum(c.datum)) || '–'}${c.von ? ' · ' + esc(c.von) : ''}: ${esc(c.was)}${c.grund ? ' – ' + esc(c.grund) : ''}</li>`).join('') : '';
    $('#ab-aenderungen-z').hidden = !(a && (a.aenderungen || []).length);
    oeffne($('#dlg-abschnitt'));
    $('#ab-titel-in').focus();
  }
  $('#ab-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const a = S.edit.abschnitt;
    const body = { kapitel: $('#ab-kapitel').value, nr: $('#ab-nr').value, titel: $('#ab-titel-in').value, text: $('#ab-text').value, verweise: $('#ab-verweise').value,
      ifs: $('#ab-ifs').value, zustaendig: $('#ab-zust').value, vertreter: $('#ab-vertr').value, entfallen: $('#ab-entfallen').checked, aenderung: $('#ab-aend').value, grund: $('#ab-grund').value };
    if (a) { body.id = a.id; body.rev = a.rev; }
    const d = await senden(ev.target, 'qs_abschnitt_save', body);
    if (!d) return;
    $('#dlg-abschnitt').close();
    toast(d.unveraendert ? 'Keine Änderung' : 'Abschnitt gespeichert');
    if (!a) S.kap = d.abschnitt.kapitel;
    await neuLaden();
  });

  /* ---------- Prüfplan: Jahresplan (6 Monate zurück, aktueller Monat, 5 voraus) ---------- */
  function planZellen(p) {
    const f = p.faellig || {}, heute = S.d.heute.slice(0, 7), monate = f.monate || [], aktuell = monate.length - 1;
    const nm = f.naechste ? f.naechste.slice(0, 7) : '';
    const zellen = monate.map((m, i) => {
      let inhalt = '';
      if (f.art === 'kalender' && m.faellig) {
        const fehlt = m.faellig - m.erfuellt, farbe = fehlt === 0 ? 'gruen' : fehlt <= Math.max(1, Math.floor(m.faellig / 10)) ? 'gelb' : 'rot';
        inhalt = p.intervall === 'monatlich'
          ? (m.erfuellt ? `<i class="qm-pm ${m.abweichung ? 'abw' : 'ok'}" title="Nachweis ${esc(monatName(m.m))}">${m.abweichung ? '!' : '✓'}</i>` : '<i class="qm-pm ueber" title="versäumt">!</i>')
          : `<i class="qm-quote ${farbe}" title="${m.erfuellt} von ${m.faellig} erfüllt${m.abweichung ? ', mit Abweichung' : ''}">${m.erfuellt}/${m.faellig}</i>`;
      } else if (f.art === 'kalender' && i === aktuell && f.offen) inhalt = '<i class="qm-pm plan" title="offen"></i>';
      else if (f.art !== 'kalender' && m.erfuellt) inhalt = `<i class="qm-pm ${m.abweichung ? 'abw' : 'ok'}" title="${m.erfuellt} Nachweis(e)">${m.abweichung ? '!' : '✓'}</i>`;
      else if (f.art === 'rollend' && i === aktuell && f.ampel === 'rot') inhalt = '<i class="qm-pm ueber" title="überfällig">!</i>';
      else if (f.art === 'rollend' && m.m === nm) inhalt = `<i class="qm-pm plan" title="fällig ${esc(datum(f.naechste))}"></i>`;
      return `<span class="qm-zelle${m.m === heute ? ' heute' : ''}">${inhalt}</span>`;
    });
    while (zellen.length < 7) zellen.unshift('<span class="qm-zelle"></span>');
    for (let i = 1; i <= 5; i++) {
      const m = plusMonate(heute, i);
      let inhalt = '';
      if (f.art === 'kalender' && m >= (p.start || '').slice(0, 7)) inhalt = p.intervall === 'monatlich' ? '<i class="qm-pm plan"></i>' : '<i class="qm-quote">·</i>';
      else if (f.art === 'rollend' && m === nm) inhalt = `<i class="qm-pm plan" title="fällig ${esc(datum(f.naechste))}"></i>`;
      zellen.push(`<span class="qm-zelle">${inhalt}</span>`);
    }
    return zellen.join('');
  }
  function renderPruefplan() {
    const kap = $('#qm-p-kapitel').value, nurFaellig = $('#qm-p-faellig').checked, inaktiv = $('#qm-p-inaktiv').checked, meine = $('#qm-p-meine').checked;
    const liste = S.d.pruefungen.filter((p) => (!kap || p.kapitel === kap) && (inaktiv || p.aktiv) && (!nurFaellig || istFaellig(p)) && (!meine || istMeine(p)))
      .sort((a, b) => (a.intervall === 'anlass') - (b.intervall === 'anlass') || natCmp(a.kapitel, b.kapitel) || natCmp(a.titel, b.titel));
    const heute = S.d.heute.slice(0, 7);
    const monate = Array.from({ length: 12 }, (_, i) => plusMonate(heute, i - 6));
    $('#qm-p-unter').textContent = `${zahl(S.d.pruefungen.filter((p) => p.aktiv).length)} aktive Prüfungen · ${monatName(monate[0])} bis ${monatName(monate[11])} · täglich = jeder Arbeitstag (Mo–Fr ohne Feiertage)`;
    const kopf = `<div class="qm-plan-zeile kopf"><span>Prüfung</span>${monate.map((m) => `<span class="${m === heute ? 'heute' : ''}">${esc(monatName(m))}</span>`).join('')}<span>Fällig</span><span></span></div>`;
    const zeilen = liste.map((p) => {
      const f = p.faellig || {};
      const ausf = (p.ausfuehrende || []).map(mitarbeiterName).filter(Boolean);
      const sub = [p.kapitel, ivKurz(p.intervall), p.zustaendig ? 'Zuständig ' + p.zustaendig : '', ausf.length ? ausf.slice(0, 2).join(', ') + (ausf.length > 2 ? ` +${ausf.length - 2}` : '') : ''].filter(Boolean).join(' · ');
      const mitte = p.intervall === 'anlass' || !p.aktiv ? `<span class="qm-bedarf">${p.aktiv ? 'bei Bedarf' : 'inaktiv'} · ${zahl(f.anzahl || 0)} Nachweise${f.letzter ? ', zuletzt ' + esc(datum(f.letzter)) : ''}</span>` : planZellen(p);
      return `<div class="qm-plan-zeile qm-klick${p.aktiv ? '' : ' qm-aus'}${istMeine(p) ? ' qm-meine' : ''}" data-pruefung="${esc(p.id)}"><span class="qm-plan-titel"><b>${esc(p.titel)}</b><span>${esc(sub)}</span></span>${mitte}<span>${faelligChip(p)}${f.art === 'kalender' && f.versaeumtAnzahl ? `<span class="qm-sub">${zahl(f.versaeumtAnzahl)} versäumt</span>` : ''}</span><span>${darfNachweis(p) ? `<button class="btn sm" type="button" data-nachweis="${esc(p.id)}">Nachweis</button>` : ''}</span></div>`;
    }).join('');
    $('#qm-p-liste').innerHTML = `<div class="qm-plan">${kopf}${zeilen || `<p class="qm-leerzeile">${S.d.pruefungen.length ? 'Keine passenden Prüfungen.' : 'Der Prüfplan ist noch leer.'}</p>`}</div>`;
  }
  ['#qm-p-kapitel', '#qm-p-faellig', '#qm-p-inaktiv', '#qm-p-meine'].forEach((s) => $(s).addEventListener('input', renderPruefplan));
  $('#qm-p-csv').addEventListener('click', () => ladeCsv('pruefplan', `QM-Pruefplan_${S.d.heute}.csv`));
  $('#qm-p-neu').addEventListener('click', () => oeffnePruefForm(''));
  function oeffnePruefung(id) { if (!S.d.pruefungen.some((p) => p.id === id)) return; S.pruefung = id; renderPruefung(); oeffne($('#dlg-pruefung')); }
  const periodeText = (k) => (k.length === 10 ? datum(k) : k.includes('-W') ? `KW ${Number(k.split('-W')[1])}/${k.slice(0, 4)}` : `${monatName(k)} ${k.slice(0, 4)}`);
  function renderPruefung() {
    const p = S.d.pruefungen.find((x) => x.id === S.pruefung);
    if (!p) { $('#dlg-pruefung').close(); return; }
    const f = p.faellig || {};
    $('#pr-kapitel').textContent = kapitelText(p.kapitel); $('#pr-titel').textContent = p.titel;
    const fenster = p.intervall === 'woechentlich' ? '12 Wochen' : p.intervall === 'monatlich' ? '12 Monate' : '30 Tage';
    $('#pr-meta').innerHTML = `<span>${faelligChip(p)}</span><span>${esc(S.d.intervalle[p.intervall] || p.intervall)}</span>${f.letzter ? `<span>letzter Nachweis ${esc(datum(f.letzter))}</span>` : ''}${f.naechste ? `<span>nächste Fälligkeit <b>${esc(datum(f.naechste))}</b></span>` : ''}${f.quote ? `<span>erfüllt <b>${esc(quoteText(f))}</b> (letzte ${fenster})</span>` : ''}`;
    const feld = (t, w) => (w ? `<dt>${esc(t)}</dt><dd>${w}</dd>` : '');
    const ausf = (p.ausfuehrende || []).map(mitarbeiterName).filter(Boolean);
    $('#pr-felder').innerHTML = feld('Durchführung', esc(p.beschreibung)) + feld('Sollwert', esc(p.sollwert)) + feld('Maßnahme bei Abweichung', esc(p.massnahme)) + feld('Wo? Womit?', esc(p.womit))
      + feld('Ab wann', esc(datum(p.start))) + feld('Zuständig', p.zustaendig ? wer(p.zustaendig) + (p.vertreter ? ' · Vertreter ' + wer(p.vertreter) : '') : '') + feld('Durchführung durch', esc(ausf.join(', ')));
    const art = p.intervall === 'woechentlich' ? 'Wochen' : p.intervall === 'monatlich' ? 'Monate' : 'Tage';
    $('#pr-versaeumt').innerHTML = f.art === 'kalender' && f.versaeumtAnzahl
      ? `<section class="qm-karte qm-versaeumt"><h3>${chip(`${zahl(f.versaeumtAnzahl)} versäumt`, 'rot')} ${art} ohne Nachweis seit Beginn</h3><p class="qm-hilfe">${(f.versaeumt || []).slice(0, 40).map(periodeText).map(esc).join(' · ')}${(f.versaeumt || []).length > 40 ? ' …' : ''}</p>${darfNachweis(p) ? '<p class="qm-hilfe">Wurde die Kontrolle doch durchgeführt: Nachweis mit dem richtigen Datum nachtragen – er erscheint als „nachgetragen“.</p>' : ''}</section>` : '';
    const nw = S.d.nachweise.filter((n) => n.pruefung === p.id);
    $('#pr-nachweise').innerHTML = nw.length ? `<table class="qm-tabelle qm-karten"><thead><tr><th>Datum</th><th>Ergebnis</th><th>Bemerkung</th><th>Durchgeführt</th><th>Maßnahme</th><th></th></tr></thead><tbody>${nw.map((n) => {
      const m = n.massnahme ? S.d.massnahmen.find((x) => x.id === n.massnahme) : null;
      const nach = n.erfasst && n.erfasst.t.slice(0, 10) > n.datum;
      const eigenN = n.erfasst && String(n.erfasst.vonId) === String(S.d.ich.id);
      return `<tr${n.storno ? ' class="qm-storniert"' : ''}><td data-label="Datum">${esc(datum(n.datum))}${nach ? ' ' + chip('nachgetragen') : ''}</td>
        <td data-label="Ergebnis">${chip(S.d.ergebnisse[n.ergebnis] || n.ergebnis, n.ergebnis === 'io' ? 'gruen' : 'rot')}</td>
        <td data-label="Bemerkung">${esc(n.bemerkung) || '—'}${n.storno ? `<span class="qm-sub">storniert von ${esc(n.storno.von)}: ${esc(n.storno.grund)}</span>` : ''}</td>
        <td data-label="Durchgeführt">${esc(n.durch)}<span class="qm-sub">erfasst ${esc(zeitpunkt(n.erfasst.t))} · ${esc(n.erfasst.von)}</span></td>
        <td data-label="Maßnahme">${m ? `<button class="qm-verweis" type="button" data-massn-auf="${esc(m.id)}">${esc(m.nr)}</button>` : '—'}</td>
        <td class="qm-ohne-strich" data-label="">${!n.storno && (darf('bearbeiten') || (darf('nachweis') && eigenN)) ? `<button class="btn sm ghost" type="button" data-storno="${esc(n.id)}">Stornieren</button>` : ''}</td></tr>`;
    }).join('')}</tbody></table>${S.d.nachweiseGesamt > S.d.nachweise.length ? '<p class="qm-hilfe">Ältere Nachweise sind hier nicht aufgeführt.</p>' : ''}` : '<p class="qm-hilfe">Noch keine Nachweise.</p>';
    $('#pr-knoepfe').innerHTML = `${darf('freigeben') ? `<button class="btn" type="button" data-pr="aendern">${icon('stift')}Ändern</button>` : ''}${darfNachweis(p) ? '<button class="btn primary" type="button" data-pr="nachweis">Nachweis erfassen</button>' : ''}<button class="btn" type="button" data-schliessen>Schließen</button>`;
  }
  $('#dlg-pruefung').addEventListener('click', async (ev) => {
    const b = ev.target.closest('[data-pr]');
    if (b) { if (b.dataset.pr === 'aendern') oeffnePruefForm(S.pruefung); else oeffneNachweis(S.pruefung); return; }
    const m = ev.target.closest('[data-massn-auf]'); if (m) { oeffneMassnahme(m.dataset.massnAuf); return; }
    const s = ev.target.closest('[data-storno]');
    if (s) {
      const g = await frageGrund('Nachweis stornieren', 'Der Nachweis bleibt sichtbar, zählt aber nicht mehr für die Fälligkeit. Den richtigen Nachweis danach neu erfassen.', 'Grund', true);
      if (g === null) return;
      const r = await api('qs_nachweis_storno', { id: s.dataset.storno, grund: g });
      if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Stornieren fehlgeschlagen'), true); return; }
      toast('Nachweis storniert'); await neuLaden();
    }
  });
  function maWahl(gewaehlt) {
    const q = $('#pf-ma-suche').value.trim().toLocaleLowerCase('de-DE');
    $('#pf-ausfuehrende').innerHTML = S.d.mitarbeiter.filter((m) => gewaehlt.has(m.id) || !q || m.name.toLocaleLowerCase('de-DE').includes(q))
      .map((m) => `<label class="qm-check"><input type="checkbox" value="${esc(m.id)}"${gewaehlt.has(m.id) ? ' checked' : ''}> ${esc(m.name)}${m.zugang ? '' : ' <small>(ohne Anmeldung)</small>'}</label>`).join('') || '<span class="qm-hilfe">Keine Mitarbeiter gefunden.</span>';
  }
  $('#pf-ma-suche').addEventListener('input', () => maWahl(new Set($$('#pf-ausfuehrende input:checked').map((x) => x.value))));
  function oeffnePruefForm(id) {
    const p = id ? S.d.pruefungen.find((x) => x.id === id) : null;
    S.edit.pruefung = p;
    $('#pf-titel').textContent = p ? 'Prüfung ändern' : 'Prüfung anlegen';
    $('#pf-kapitel').innerHTML = kapitelOptionen(p ? p.kapitel : $('#qm-p-kapitel').value, p ? '' : 'Kapitel wählen');
    $('#pf-intervall').innerHTML = optionen(S.d.intervalle, p ? p.intervall : 'jaehrlich');
    $('#pf-titel-in').value = p ? p.titel : ''; $('#pf-beschr').value = p ? p.beschreibung : ''; $('#pf-start').value = p ? p.start : '';
    $('#pf-womit').value = p ? p.womit : ''; $('#pf-soll').value = p ? p.sollwert : ''; $('#pf-massn').value = p ? p.massnahme : '';
    $('#pf-zust').value = p ? p.zustaendig : ''; $('#pf-vertr').value = p ? p.vertreter : ''; $('#pf-aktiv').checked = p ? !!p.aktiv : true;
    $('#pf-ma-suche').value = ''; maWahl(new Set(p ? p.ausfuehrende || [] : []));
    oeffne($('#dlg-pruefform'));
    $('#pf-titel-in').focus();
  }
  $('#pf-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const p = S.edit.pruefung;
    const body = { kapitel: $('#pf-kapitel').value, titel: $('#pf-titel-in').value, beschreibung: $('#pf-beschr').value, intervall: $('#pf-intervall').value, start: $('#pf-start').value,
      womit: $('#pf-womit').value, sollwert: $('#pf-soll').value, massnahme: $('#pf-massn').value, zustaendig: $('#pf-zust').value, vertreter: $('#pf-vertr').value,
      ausfuehrende: $$('#pf-ausfuehrende input:checked').map((x) => x.value), aktiv: $('#pf-aktiv').checked };
    if (p) { body.id = p.id; body.rev = p.rev; }
    const d = await senden(ev.target, 'qs_pruefung_save', body);
    if (!d) return;
    $('#dlg-pruefform').close();
    toast('Prüfung gespeichert');
    await neuLaden();
  });

  /* Nachweis erfassen (wer die Kontrolle zugewiesen hat oder „bearbeiten“ darf) */
  function oeffneNachweis(id) {
    const p = S.d.pruefungen.find((x) => x.id === id); if (!p) return;
    S.edit.nachweis = p;
    $('#nw-titel').textContent = p.titel;
    $('#nw-unter').textContent = `Nachweis erfassen · ${kapitelText(p.kapitel)}`;
    $('#nw-soll').textContent = [p.beschreibung, p.sollwert ? `Sollwert: ${p.sollwert}` : ''].filter(Boolean).join(' · ');
    $('#nw-datum').value = S.d.heute; $('#nw-datum').max = S.d.heute;
    $('#nw-durch').value = S.d.ich.name; $('#nw-bem').value = '';
    $('#nw-massn').checked = darf('bearbeiten'); $('#nw-massn').disabled = !darf('bearbeiten');
    $('#nw-massn-l').hidden = !darf('bearbeiten'); $('#nw-massn-hinweis').hidden = darf('bearbeiten');
    $('#nw-korr').value = ''; $('#nw-km').value = p.massnahme || ''; $('#nw-mzust').value = p.zustaendig || ''; $('#nw-frist').value = '';
    setzeErgebnis('io');
    oeffne($('#dlg-nachweis'));
  }
  const ergebnis = () => { const b = $('#dlg-nachweis [data-ergebnis][aria-pressed="true"]'); return b ? b.dataset.ergebnis : 'io'; };
  function nwAbweichung() { $('#nw-massn-z').hidden = ergebnis() !== 'abweichung'; $('#nw-massn-felder').hidden = !$('#nw-massn').checked; }
  function setzeErgebnis(e) { $$('#dlg-nachweis [data-ergebnis]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.ergebnis === e))); nwAbweichung(); }
  $('#dlg-nachweis').addEventListener('click', (ev) => { const b = ev.target.closest('[data-ergebnis]'); if (b) setzeErgebnis(b.dataset.ergebnis); });
  $('#nw-massn').addEventListener('change', nwAbweichung);
  $('#nw-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const p = S.edit.nachweis, e = ergebnis();
    const body = { pruefung: p.id, datum: $('#nw-datum').value, ergebnis: e, bemerkung: $('#nw-bem').value, durch: $('#nw-durch').value };
    if (e === 'abweichung' && $('#nw-massn').checked && darf('bearbeiten')) body.massnahme = { korrektur: $('#nw-korr').value, massnahme: $('#nw-km').value, zustaendig: $('#nw-mzust').value, frist: $('#nw-frist').value };
    const d = await senden(ev.target, 'qs_nachweis_save', body);
    if (!d) return;
    $('#dlg-nachweis').close();
    toast(d.massnahme ? `Nachweis gespeichert, Maßnahme ${d.massnahme.nr} angelegt` : 'Nachweis gespeichert');
    await neuLaden();
  });

  /* ---------- Maßnahmen ---------- */
  function massnTabelle(liste) {
    return `<table class="qm-tabelle qm-karten"><thead><tr><th>Nr.</th><th>Feststellung</th><th>Quelle</th><th>IFS</th><th>Zuständig</th><th>Frist</th><th>Status</th></tr></thead><tbody>${liste.map((m) => `<tr class="qm-klick" data-massn="${esc(m.id)}">
      <td class="qm-nr" data-label="Nr.">${esc(m.nr)}</td>
      <td class="qm-voll" data-label="Feststellung"><span class="qm-kurz">${esc(m.feststellung)}</span><span class="qm-sub">${esc([m.bezug, m.kapitel ? 'Kapitel ' + m.kapitel : ''].filter(Boolean).join(' · '))}</span></td>
      <td data-label="Quelle">${esc(S.d.quellen[m.quelle] || m.quelle)}</td>
      <td data-label="IFS">${esc(m.anforderung) || '—'}${m.bewertung ? ' ' + chip(m.bewertung) : ''}</td>
      <td data-label="Zuständig">${wer(m.zustaendig)}</td>
      <td data-label="Frist">${m.frist ? (m.ueberfaellig ? chip(datum(m.frist), 'rot') : esc(datum(m.frist))) : '<span class="qm-null">—</span>'}</td>
      <td data-label="Status">${massnStatusChip(m)}</td></tr>`).join('')}</tbody></table>`;
  }
  const SPALTEN = [['offen', 'Offen', 'var(--qm-gelb)'], ['in_arbeit', 'In Arbeit', 'var(--qm-blau)'], ['umgesetzt', 'Umgesetzt · Wirksamkeit prüfen', 'var(--qm-green)'], ['wirksam', 'Wirksam', '#8d857f']];
  function renderMassnahmen() {
    const st = $('#qm-m-status').value, bz = $('#qm-m-bezug').value, q = $('#qm-m-suche').value.trim().toLocaleLowerCase('de-DE');
    const basis = S.d.massnahmen.filter((m) => (!bz || m.bezug === bz) && (!q || [m.nr, m.feststellung, m.bezug, m.massnahme, m.korrektur, m.ursache, m.zustaendig, m.anforderung].join(' ').toLocaleLowerCase('de-DE').includes(q)));
    $$('.qm-segment[aria-label="Ansicht"] [data-ansicht]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.ansicht === S.ansicht)));
    $('#qm-m-status').hidden = S.ansicht === 'tafel';
    if (!basis.length) { $('#qm-m-liste').innerHTML = `<p class="qm-leer-text qm-glas">${S.d.massnahmen.length ? 'Keine passenden Maßnahmen.' : 'Noch keine Maßnahmen.'}</p>`; return; }
    if (S.ansicht === 'tafel') {
      $('#qm-m-liste').innerHTML = `<div class="qm-tafel">${SPALTEN.map(([s, n, farbe]) => {
        const k = basis.filter((m) => m.status === s).sort(s === 'wirksam' ? (a, b) => natCmp(b.nr, a.nr) : sortFrist);
        const max = s === 'wirksam' ? 8 : 60;
        return `<section class="qm-spalte${s === 'wirksam' ? ' blass' : ''}" data-spalte="${s}"><div class="qm-spaltenkopf"><h2><i style="background:${farbe}"></i>${esc(n)}</h2><small>${zahl(k.length)}</small></div>
          ${k.slice(0, max).map((m) => `<button type="button" class="qm-mkarte" data-massn="${esc(m.id)}"><span class="qm-mk-kopf"><span>${esc(m.nr)}${m.anforderung ? ' · IFS ' + esc(m.anforderung) : m.kapitel ? ' · Kapitel ' + esc(m.kapitel) : ''}</span><span>${esc(m.bezug || S.d.quellen[m.quelle] || '')}</span></span>
            <b>${esc(m.feststellung)}</b>${m.ursache ? `<span class="qm-sub qm-kurz">Ursache: ${esc(m.ursache)}</span>` : ''}
            <span class="qm-mk-fuss"><span class="qm-avatar" title="${esc(werName(m.zustaendig))}">${esc(m.zustaendig || '–')}</span>${(s === 'wirksam' || s === 'umgesetzt') && m.erledigtAm ? chip('umgesetzt ' + datum(m.erledigtAm)) : m.frist ? chip('bis ' + datum(m.frist), m.ueberfaellig ? 'rot' : '') : ''}</span></button>`).join('') || '<p class="qm-leer-spalte">—</p>'}
          ${k.length > max ? `<p class="qm-leer-spalte">und ${zahl(k.length - max)} weitere – Ansicht „Liste“</p>` : ''}</section>`;
      }).join('')}</div>`;
      return;
    }
    const liste = basis.filter((m) => st === '' || (st === 'nicht' ? !['wirksam', 'verworfen'].includes(m.status) : m.status === st)).sort((a, b) => (st === 'nicht' ? sortFrist(a, b) : natCmp(b.nr, a.nr)));
    $('#qm-m-liste').innerHTML = `<section class="qm-panel qm-glas"><div class="qm-tabelle-wrap">${liste.length ? massnTabelle(liste) : '<p class="qm-leerzeile">Keine passenden Maßnahmen.</p>'}</div></section>`;
  }
  $('.qm-segment[aria-label="Ansicht"]').addEventListener('click', (ev) => { const b = ev.target.closest('[data-ansicht]'); if (b) { S.ansicht = b.dataset.ansicht; renderMassnahmen(); } });
  ['#qm-m-status', '#qm-m-bezug', '#qm-m-suche'].forEach((s) => $(s).addEventListener('input', renderMassnahmen));
  $('#qm-m-csv').addEventListener('click', () => ladeCsv('massnahmen', `QM-Massnahmen_${S.d.heute}.csv`));
  $('#qm-m-neu').addEventListener('click', () => oeffneMassnahme(''));
  const MS_FELDER = { quelle: 'ms-quelle', bezug: 'ms-bezug', kapitel: 'ms-kapitel', anforderung: 'ms-anf', bewertung: 'ms-bewertung', anforderungText: 'ms-anftext', feststellung: 'ms-fest',
    korrektur: 'ms-korr', korrekturVerantwortlich: 'ms-kverant', korrekturFrist: 'ms-kfrist', korrekturErledigt: 'ms-kerl', nachweisDoku: 'ms-nachweis',
    ursache: 'ms-ursache', massnahme: 'ms-km', zustaendig: 'ms-zust', frist: 'ms-frist', erledigtAm: 'ms-erl', status: 'ms-status', freigabeVon: 'ms-fvon', freigabeDatum: 'ms-fdatum', freigabeNotiz: 'ms-fnotiz' };
  const MS_AUSWAHL = ['quelle', 'kapitel', 'bewertung', 'status'];
  function oeffneMassnahme(id) {
    const m = id ? S.d.massnahmen.find((x) => x.id === id) : null;
    if (id && !m) return;
    S.edit.massn = m;
    const abgeschlossen = !!m && ['wirksam', 'verworfen'].includes(m.status);
    const kannAendern = darf('bearbeiten') && (!abgeschlossen || darf('freigeben'));
    $('#ms-nr').textContent = m ? `Maßnahme ${m.nr}` : '';
    $('#ms-titel').textContent = m ? (m.bezug || S.d.quellen[m.quelle] || 'Maßnahme') : 'Maßnahme erfassen';
    $('#ms-quelle').innerHTML = optionen(S.d.quellen, m ? m.quelle : 'intern');
    $('#ms-kapitel').innerHTML = kapitelOptionen(m ? m.kapitel : '', 'ohne Kapitel');
    $('#ms-bewertung').innerHTML = S.d.bewertungen.map((b) => `<option value="${esc(b)}"${m && m.bewertung === b ? ' selected' : ''}>${b ? esc(b) : '—'}</option>`).join('');
    const erlaubt = Object.fromEntries(Object.entries(S.d.massnStatus).filter(([k]) => darf('freigeben') || !['wirksam', 'verworfen'].includes(k) || (m && m.status === k)));
    $('#ms-status').innerHTML = optionen(erlaubt, m ? m.status : 'offen');
    for (const [f, el] of Object.entries(MS_FELDER)) if (!MS_AUSWAHL.includes(f)) $('#' + el).value = m ? (m[f] || '') : '';
    $('#ms-notiz').value = '';
    $('#ms-wirksam').textContent = m && m.wirksamkeit ? `Wirksam bestätigt am ${zeitpunkt(m.wirksamkeit.t)} von ${m.wirksamkeit.von}: ${m.wirksamkeit.notiz}`
      : abgeschlossen && !darf('freigeben') ? 'Abgeschlossen – ändern kann nur, wer prüfen und freigeben darf.' : '';
    $('#ms-verlauf').innerHTML = m ? (m.verlauf || []).slice().reverse().map((l) => `<li>${esc(zeitpunkt(l.t))} · ${esc(l.von)}: ${esc(l.was)}</li>`).join('') : '';
    $$('#ms-form .qm-eingabe').forEach((e) => { e.disabled = !kannAendern; });
    $('#ms-speichern').hidden = !kannAendern;
    msNotiz();
    oeffne($('#dlg-massnahme'));
  }
  function msNotiz() {
    const m = S.edit.massn, st = $('#ms-status').value;
    $('#ms-notiz-z').hidden = !(['wirksam', 'verworfen'].includes(st) && (!m || m.status !== st));
    $('#ms-notiz-l').textContent = st === 'verworfen' ? 'Grund für das Verwerfen' : 'Wirksamkeitsprüfung: wie geprüft, Ergebnis';
    if (st === 'umgesetzt' && !$('#ms-erl').value && !$('#ms-erl').disabled) $('#ms-erl').value = S.d.heute;
  }
  $('#ms-status').addEventListener('change', msNotiz);
  $('#ms-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const m = S.edit.massn;
    const body = { wirksamkeitNotiz: $('#ms-notiz').value };
    for (const [f, el] of Object.entries(MS_FELDER)) body[f] = $('#' + el).value;
    if (m) { body.id = m.id; body.rev = m.rev; }
    const d = await senden(ev.target, 'qs_massnahme_save', body);
    if (!d) return;
    $('#dlg-massnahme').close();
    toast(m ? `Maßnahme ${d.massnahme.nr} gespeichert` : `Maßnahme ${d.massnahme.nr} erfasst`);
    await neuLaden();
  });

  /* ---------- Einstellungen: Personen, Kapitel, Überprüfung, Datenpaket ---------- */
  const maOptionen = (wahl) => '<option value="">— nicht verknüpft —</option>' + S.d.mitarbeiter.map((m) => `<option value="${esc(m.id)}"${m.id === wahl ? ' selected' : ''}>${esc(m.name)}${m.zugang ? '' : ' (ohne Anmeldung)'}</option>`).join('');
  const kapitelZeile = (k = {}) => `<tr><td class="qm-eng" data-label="Nr."><input class="qm-eingabe" data-f="id" maxlength="12" value="${esc(k.id)}" placeholder="1.4" aria-label="Kapitelnummer"></td>
    <td class="qm-voll" data-label="Titel"><input class="qm-eingabe" data-f="titel" maxlength="120" value="${esc(k.titel)}" aria-label="Titel"></td>
    <td class="qm-eng" data-label="Zuständig"><input class="qm-eingabe" data-f="zustaendig" maxlength="40" list="qm-kuerzel" value="${esc(k.zustaendig)}" aria-label="Zuständig"></td>
    <td class="qm-eng" data-label="Vertreter"><input class="qm-eingabe" data-f="vertreter" maxlength="40" list="qm-kuerzel" value="${esc(k.vertreter)}" aria-label="Vertreter"></td>
    <td data-label="aktiv"><input type="checkbox" data-f="aktiv"${k.aktiv === false ? '' : ' checked'} aria-label="aktiv"></td></tr>`;
  const personZeile = (p = {}) => `<tr><td class="qm-eng" data-label="Kürzel"><input class="qm-eingabe" data-f="id" maxlength="12" value="${esc(p.id)}" aria-label="Kürzel"></td>
    <td data-label="Name"><input class="qm-eingabe" data-f="name" maxlength="100" value="${esc(p.name)}" aria-label="Name"></td>
    <td data-label="Funktion"><input class="qm-eingabe" data-f="funktion" maxlength="100" value="${esc(p.funktion)}" aria-label="Funktion"></td>
    <td data-label="Mitarbeiter"><select class="qm-eingabe" data-f="mitarbeiter" aria-label="Mitarbeiter">${maOptionen(p.mitarbeiter || '')}</select></td>
    <td data-label="aktiv"><input type="checkbox" data-f="aktiv"${p.aktiv === false ? '' : ' checked'} aria-label="aktiv"></td></tr>`;
  function renderEinstellungen() {
    $('#qm-e-kapitel').innerHTML = S.d.kapitel.map(kapitelZeile).join('');
    $('#qm-e-personen').innerHTML = S.d.personen.map(personZeile).join('');
    $('#qm-e-monate').value = S.d.einstellungen.ueberpruefungMonate;
  }
  $('#qm-e-kapitel-plus').addEventListener('click', () => { $('#qm-e-kapitel').insertAdjacentHTML('beforeend', kapitelZeile()); $('#qm-e-kapitel tr:last-child input').focus(); });
  $('#qm-e-person-plus').addEventListener('click', () => { $('#qm-e-personen').insertAdjacentHTML('beforeend', personZeile()); $('#qm-e-personen tr:last-child input').focus(); });
  const zeilen = (tbody) => $$('tr', tbody).map((tr) => Object.fromEntries($$('[data-f]', tr).map((e) => [e.dataset.f, e.type === 'checkbox' ? e.checked : e.value.trim()])))
    .filter((r) => Object.entries(r).some(([k, v]) => !['aktiv', 'mitarbeiter'].includes(k) && v));
  $('#qm-e-kapitel-form').addEventListener('submit', async (ev) => { ev.preventDefault(); const d = await senden(ev.target, 'qs_stamm_save', { kapitel: zeilen($('#qm-e-kapitel')) }); if (d) { toast('Kapitel gespeichert'); await neuLaden(); } });
  $('#qm-e-person-form').addEventListener('submit', async (ev) => { ev.preventDefault(); const d = await senden(ev.target, 'qs_stamm_save', { personen: zeilen($('#qm-e-personen')) }); if (d) { toast('Personen gespeichert'); await neuLaden(); } });
  $('#qm-e-einst-form').addEventListener('submit', async (ev) => { ev.preventDefault(); const d = await senden(ev.target, 'qs_stamm_save', { einstellungen: { ueberpruefungMonate: $('#qm-e-monate').value.trim() } }); if (d) { toast('Einstellung gespeichert'); await neuLaden(); } });
  $('#qm-e-datei').addEventListener('change', async () => {
    const f = $('#qm-e-datei').files[0]; S.paket = null; $('#qm-e-uebernehmen').disabled = true; $('#qm-e-meldung').textContent = ''; $('#qm-e-vorschau').innerHTML = '';
    if (!f) return;
    $('#qm-e-dateiname').textContent = f.name;
    let paket;
    try { paket = JSON.parse(await f.text()); } catch { $('#qm-e-meldung').textContent = 'Die Datei ist kein gültiges Datenpaket (JSON).'; return; }
    const r = await api('qs_import', { paket, vorschau: true });
    if (r.status !== 200 || !r.data.ok) { $('#qm-e-meldung').textContent = fehlerText(r, 'Prüfen fehlgeschlagen'); return; }
    const z = r.data.zahlen, namen = { kapitel: 'Kapitel', personen: 'Personen', dokumente: 'Dokumente', versionen: 'Versionen', handbuch: 'Handbuch-Abschnitte', pruefungen: 'Prüfungen', massnahmen: 'Maßnahmen' };
    $('#qm-e-vorschau').innerHTML = `<div class="qm-vorschau">${Object.entries(namen).map(([k, n]) => `<div><b>${zahl(z[k] || 0)}</b><span>${esc(n)}</span></div>`).join('')}</div>`
      + (r.data.fehler.length ? `<p class="qm-meldung">${zahl(r.data.fehler.length)} Fehler – so wird nichts übernommen:</p><ul class="qm-fehlerliste">${r.data.fehler.map((x) => `<li>${esc(x.teil)} ${esc(x.zeile)}: ${esc(x.text)}</li>`).join('')}</ul>`
        : r.data.dateien ? `<p class="qm-meldung">In der Dokumentenablage liegen schon ${zahl(r.data.dateien)} Dateien – ein Datenpaket kann die Dokumente nicht mehr ersetzen.</p>` : '<p class="qm-meldung ok">Keine Fehler gefunden.</p>');
    $('#qm-e-ersetzen-z').hidden = r.data.leer; $('#qm-e-ersetzen').checked = false;
    if (!r.data.fehler.length && !r.data.dateien) { S.paket = paket; $('#qm-e-uebernehmen').disabled = false; }
  });
  $('#qm-e-uebernehmen').addEventListener('click', async () => {
    if (!S.paket) return;
    const k = $('#qm-e-uebernehmen'); k.disabled = true;
    const r = await api('qs_import', { paket: S.paket, ersetzen: $('#qm-e-ersetzen').checked });
    k.disabled = false;
    if (r.status !== 200 || !r.data.ok) { $('#qm-e-meldung').className = 'qm-meldung'; $('#qm-e-meldung').textContent = fehlerText(r, 'Übernehmen fehlgeschlagen'); return; }
    S.paket = null; k.disabled = true; $('#qm-e-datei').value = ''; $('#qm-e-dateiname').textContent = ''; $('#qm-e-vorschau').innerHTML = ''; $('#qm-e-ersetzen-z').hidden = true;
    toast(`Datenpaket übernommen – ${zahl(r.data.zahlen.dokumente)} Dokumente, ${zahl(r.data.zahlen.handbuch)} Abschnitte, ${zahl(r.data.zahlen.pruefungen)} Prüfungen, ${zahl(r.data.zahlen.massnahmen || 0)} Maßnahmen`);
    await neuLaden();
  });

  /* ---------- Eingabemasken: gemeinsame Hilfen ---------- */
  $$('.qm-dialog').forEach((dlg) => dlg.addEventListener('click', (ev) => { if (ev.target.closest('[data-schliessen]')) dlg.close(); }));
  function oeffne(dlg) { $$('.qm-meldung', dlg).forEach((m) => { m.textContent = ''; }); $$('[aria-invalid]', dlg).forEach((x) => x.removeAttribute('aria-invalid')); if (!dlg.open) dlg.showModal(); }
  async function senden(form, action, body) {
    const knopf = form.querySelector('[type="submit"]'), m = form.querySelector('.qm-meldung');
    m.textContent = ''; m.className = 'qm-meldung';
    knopf.disabled = true;
    const r = await api(action, body);
    knopf.disabled = false;
    if (r.status === 200 && r.data.ok) return r.data;
    if (r.status === 401) { zeigeAnmeldung(); return null; }
    m.textContent = fehlerText(r, 'Speichern fehlgeschlagen');
    if (r.status === 409 && r.data.code === 'konflikt') await neuLaden();
    return null;
  }
  /* Grund abfragen → Text oder null (abgebrochen) */
  function frageGrund(titel, text, label, pflicht) {
    return new Promise((resolve) => {
      $('#gr-titel').textContent = titel; $('#gr-text').textContent = text; $('#gr-label').textContent = label; $('#gr-grund').value = '';
      S.grund = { resolve, pflicht };
      oeffne($('#dlg-grund')); $('#gr-grund').focus();
    });
  }
  $('#gr-form').addEventListener('submit', (ev) => {
    ev.preventDefault();
    const g = $('#gr-grund').value.trim();
    if (S.grund.pflicht && !g) { $('#gr-meldung').textContent = 'Bitte einen Grund angeben.'; $('#gr-grund').setAttribute('aria-invalid', 'true'); return; }
    const r = S.grund.resolve; S.grund = null; $('#dlg-grund').close(); r(g);
  });
  $('#dlg-grund').addEventListener('close', () => { if (S.grund) { const r = S.grund.resolve; S.grund = null; r(null); } });
  /* CSV vom Server herunterladen – der Server vermerkt es im Protokoll */
  async function ladeCsv(liste, dateiname) {
    let res;
    try {
      res = await fetch(API + '?action=qs_export', { method: 'POST', credentials: 'same-origin', cache: 'no-store', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': S.csrf }, body: JSON.stringify({ liste }) });
    } catch { toast('Keine Verbindung zum Server.', true); return; }
    if (res.status === 401) { zeigeAnmeldung(); return; }
    if (!res.ok) { let d = {}; try { d = await res.json(); } catch { /* keine JSON-Antwort */ } toast(d.error || `CSV konnte nicht erstellt werden (${res.status}).`, true); return; }
    speichereDatei(await res.blob(), dateiname);
  }

  /* ---------- Start ---------- */
  async function laden() {
    const st = await api('status');
    if (st.status === 401 && !st.json) { zeigeAnmeldung(); return; }   // zentrale Sitzung abgelaufen (Webserver)
    if (st.status === 403 && st.data.code === 'reauth_required' && typeof st.data.anmelden === 'string' && st.data.anmelden.startsWith('/oidc/')) {
      location.assign(st.data.anmelden + encodeURIComponent(location.href)); return;
    }
    if (st.status === 403 && st.data.error) { fehler(st.data.error); return; }
    if (st.status !== 200 || !st.data.loggedIn) { zeigeAnmeldung(); return; }
    S.csrf = st.data.csrf || '';
    if (window.STAFL_THEME) { window.STAFL_THEME.konto(st.data.user, S.csrf, API); themaKnopf(); }
    const name = st.data.user ? (st.data.user.name || st.data.user.username || '') : '';
    $('#qm-user').hidden = false; $('#qm-user-name').textContent = name; $('#qm-initialen').textContent = initialen(name);
    const r = await api('qs_start');
    if (r.status === 404) { fehler('Die Qualitätssicherung ist für Sie noch nicht freigegeben.'); return; }
    if (r.status === 503) { fehler(r.data.error || 'Die Qualitätssicherung wird gerade gewartet.'); return; }
    if (r.status === 403) { fehler(r.data.error || 'Dafür fehlt Ihnen die Berechtigung.'); return; }
    if (r.status === 401) { zeigeAnmeldung(); return; }
    if (r.status !== 200 || !r.data.ok) { fehler(fehlerText(r, 'Die Qualitätssicherung konnte nicht geladen werden')); return; }
    setzeDaten(r.data);
    $('#qm-login').hidden = true; $('#qm-app').hidden = false;
    renderAlles();
    zeigeTab(location.hash.slice(1).split('/')[0] || 'uebersicht');
  }
  themaKnopf();
  document.addEventListener('DOMContentLoaded', () => { laden().catch(() => fehler('Keine Verbindung zum Server.')); });
})();
