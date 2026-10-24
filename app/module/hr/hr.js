/* STAFL-Plattform · HR · Urlaub
   Mitarbeiter: eigenes Urlaubskonto, Urlaubsantrag, eigene Einträge, Abwesenheitskalender (Kollegen nur „abwesend“).
   Personalstelle (Recht hr.verwalten): offene Anträge genehmigen/ablehnen, Abwesenheiten eintragen (U, K, G, freier Tag),
   Mitarbeiter mit Anspruch und Übertrag, Excel-Export für den Steuerberater, Übernahme der bisherigen Excel-Planung,
   Urlaubssperren und Ferien. Alle Rechte prüft der Server bei jeder Aktion (GR-103) – ausgeblendete Bereiche sind nur
   Anzeige. Kein Inline-Skript (Content-Security-Policy). */
'use strict';
(() => {
  const API = '../../api/';
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (n) => `<svg class="i" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const MONATE = ['Januar', 'Februar', 'März', 'April', 'Mai', 'Juni', 'Juli', 'August', 'September', 'Oktober', 'November', 'Dezember'];
  const WT = ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'];
  const ART = { U: 'Urlaub', K: 'Krank', G: 'Gleittag', X: 'Freier Tag' };
  const STATUS = { beantragt: 'beantragt', genehmigt: 'genehmigt', abgelehnt: 'abgelehnt', zurueckgezogen: 'zurückgezogen', storniert: 'storniert' };
  let csrf = '';
  const S = { start: null, jahr: new Date().getFullYear(), kal: { jahr: new Date().getFullYear(), monat: new Date().getMonth() + 1 }, verw: null, tab: 'mein' };

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

  /* ---------- Datum und Zahlen ---------- */
  const iso = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  const ausIso = (s) => { const [y, m, d] = s.split('-').map(Number); return new Date(y, m - 1, d); };
  const de = (s) => s ? `${s.slice(8, 10)}.${s.slice(5, 7)}.${s.slice(0, 4)}` : '';
  const zeitraum = (a, b) => a === b ? de(a) : `${de(a)} – ${de(b)}`;
  const zahl = (n) => (Math.round(n * 2) / 2).toLocaleString('de-DE', { maximumFractionDigits: 1 });
  const tageText = (n) => `${zahl(n)} ${Math.abs(n) === 1 ? 'Tag' : 'Tage'}`;
  function meldung(el, text, art = 'fehler') { el.textContent = text || ''; el.className = 'hr-meldung' + (text ? ' ' + art : ''); }

  /* ---------- Kopf, Anmeldung ---------- */
  function initialen(name) {
    const t = String(name || '').trim().split(/[\s.\-_]+/).filter(Boolean);
    return (t.length > 1 ? t[0][0] + t[1][0] : (t[0] || '?').slice(0, 2)).toLocaleUpperCase('de-DE');
  }
  function fehler(text) { $('#hr-login').hidden = true; $('#hr-app').hidden = true; $('#hr-err').hidden = false; $('#hr-err').textContent = text; }
  function zeigeAnmeldung(ziel) {
    if (ziel) $('#hr-login a').setAttribute('href', ziel);
    $('#hr-login').hidden = false; $('#hr-app').hidden = true; $('#hr-user').hidden = true;
  }
  // Im Echtbetrieb führt das Logo zum Dashboard unter der zentralen Anmeldung, sonst zum Dashboard dieses Servers;
  // Mitarbeiter und Urlaubseinstellungen pflegt die Personalstelle in der Verwaltung (Mitarbeiter = Nutzer der Plattform)
  const ECHT = /(^|\.)dashboard-stafl\.de$/.test(location.hostname);
  if (ECHT) $('#hr-zurueck').href = 'https://dashboard-stafl.de/';
  for (const a of $$('[data-verwaltung-link]')) a.href = (ECHT ? 'https://verwaltung.dashboard-stafl.de/admin/' : '../../admin/') + '#' + a.dataset.verwaltungLink;

  const dunkel = () => document.documentElement.getAttribute('data-theme') === 'dark'
    || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  function themaKnopf() {
    const d = dunkel();
    $('#hr-theme').innerHTML = icon(d ? 'sun' : 'moon');
    $('#hr-theme').setAttribute('aria-label', d ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }
  $('#hr-theme').addEventListener('click', () => {
    const neu = dunkel() ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', neu);
    try { localStorage.setItem('wochenangebot.theme', JSON.stringify(neu)); } catch { /* ohne Speicher */ }
    themaKnopf();
  });

  /* ---------- Reiter ---------- */
  function zeigeTab(tab) {
    S.tab = tab;
    for (const b of $$('#hr-tabs button')) b.setAttribute('aria-selected', String(b.dataset.tab === tab));
    for (const p of $$('.hr-tab')) p.hidden = p.id !== 'tab-' + tab;
    try { history.replaceState(null, '', '#' + tab); } catch { /* egal */ }
    if (tab === 'kalender') ladeKalender();
    if (tab === 'antraege') ladeVerwaltung();
    if (tab === 'export') zeigeExport();
  }
  $('#hr-tabs').addEventListener('click', (e) => { const b = e.target.closest('button[data-tab]'); if (b) zeigeTab(b.dataset.tab); });

  /* ---------- Mein Urlaub ---------- */
  async function ladeStart() {
    const r = await api('hr_start', null, '&jahr=' + S.jahr);
    if (r.status === 404) { fehler('Die Urlaubsverwaltung ist für Sie noch nicht freigegeben.'); return false; }
    if (r.status === 503) { fehler(r.data.error || 'Die Urlaubsverwaltung wird gerade gewartet.'); return false; }
    if (r.status === 403) { fehler(r.data.error || 'Dafür fehlt Ihnen die Berechtigung.'); return false; }
    if (r.status === 401) { zeigeAnmeldung(r.json ? '' : './'); return false; }
    if (r.status !== 200 || !r.data.ok) { fehler(fehlerText(r, 'Die Urlaubsverwaltung konnte nicht geladen werden')); return false; }
    S.start = r.data;
    for (const el of $$('[data-verwalten]')) el.hidden = !r.data.verwalten;
    const offen = $('#hr-offen');
    offen.hidden = !r.data.offen; offen.textContent = r.data.offen || '';
    zeigeMein();
    return true;
  }

  function wert(titel, n, cls = '', zusatz = '') {
    return `<div class="hr-wert hr-glas ${cls}"><span>${esc(titel)}</span><b>${esc(zahl(n))}</b>${zusatz ? `<small>${esc(zusatz)}</small>` : ''}</div>`;
  }
  function zeigeMein() {
    const d = S.start;
    $('#mein-titel').textContent = `Mein Urlaub ${d.jahr}`;
    if (d.neuVerknuepft && d.ich) meldung($('#mein-info'), `Willkommen! Ihr Konto ist jetzt mit Ihrem Eintrag in der Urlaubsverwaltung verknüpft (${d.ich.name}).`, 'ok');
    $('#mein-ohne').hidden = !!d.ich;
    $('#mein-inhalt').hidden = !d.ich;
    if (!d.ich) return;
    const k = d.konto;
    $('#mein-konto').innerHTML =
      wert('Resturlaub', k.rest, 'haupt' + (k.rest < 0 ? ' minus' : ''), k.beantragt ? `davon ${tageText(k.beantragt)} beantragt` : '')
      + wert('Anspruch', k.anspruch)
      + wert('Übertrag Vorjahr', k.uebertrag, '', k.verfaellt > 0 ? `${tageText(k.verfaellt)} verfallen nach ${de(k.frist)}` : (k.verfallen > 0 ? `${tageText(k.verfallen)} verfallen` : ''))
      + wert('Genommen', k.genommen)
      + wert('Geplant', k.geplant)
      + wert('Beantragt', k.beantragt);
    const sel = $('#antrag-vertretung'), alt = sel.value;
    sel.innerHTML = '<option value="">– keine –</option>' + d.kollegen.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    sel.value = alt;
    const liste = d.eintraege.filter((e) => (e.art === 'U' || e.status === 'genehmigt') && e.von <= `${d.jahr}-12-31` && e.bis >= `${d.jahr}-01-01`);
    $('#mein-liste').innerHTML = liste.length ? liste.map((e) => {
      const zurueck = e.art === 'U' && (e.status === 'beantragt' || (e.status === 'genehmigt' && e.von > d.heute));
      const ent = e.entscheidung && e.status !== 'genehmigt' && e.entscheidung.grund ? `Grund: ${e.entscheidung.grund}` : '';
      return `<li><span class="hr-art ${esc(e.art)}" title="${esc(e.artText)}">${esc(e.art === 'X' ? 'x' : e.art)}</span>
        <span class="zeitraum">${esc(zeitraum(e.von, e.bis))}</span><span>${esc(tageText(e.tage))}</span>
        <span class="hr-pille ${esc(e.status)}">${esc(STATUS[e.status] || e.status)}</span>
        ${zurueck ? `<button type="button" class="btn" data-zurueck="${esc(e.id)}">Zurückziehen</button>` : ''}
        ${e.notiz || ent || e.urlaubAbzug ? `<span class="mehr">${esc([e.urlaubAbzug ? 'vom Urlaub abgezogen' : '', e.notiz, ent].filter(Boolean).join(' · '))}</span>` : ''}</li>`;
    }).join('') : `<li class="leer">Keine Einträge in ${d.jahr}.</li>`;
    antragTage();
  }

  /* Arbeitstage des Antrags (Vorschau im Browser; verbindlich rechnet der Server) */
  function antragTage() {
    const von = $('#antrag-von').value, bis = $('#antrag-bis').value, d = S.start;
    const out = $('#antrag-tage');
    meldung($('#antrag-meldung'), '');   // eine Meldung zum vorigen Absenden gilt nach einer Änderung der Daten nicht mehr
    if (!von || !bis || !d || !d.ich) { out.textContent = ''; return; }
    if (bis < von) { out.textContent = 'Das Ende liegt vor dem Beginn.'; return; }
    let n = 0;
    for (let t = ausIso(von); iso(t) <= bis && n < 400; t.setDate(t.getDate() + 1)) {
      const w = ((t.getDay() + 6) % 7) + 1;
      if (d.ich.arbeitstage.includes(w) && !(d.feiertage || {})[iso(t)]) n++;
    }
    out.textContent = n ? `${tageText(n)} Urlaub` : 'Im Zeitraum liegen keine Arbeitstage.';
  }
  $('#antrag-von').addEventListener('change', () => { if (!$('#antrag-bis').value || $('#antrag-bis').value < $('#antrag-von').value) $('#antrag-bis').value = $('#antrag-von').value; antragTage(); });
  $('#antrag-bis').addEventListener('change', antragTage);

  $('#antrag').addEventListener('submit', async (e) => {
    e.preventDefault();
    const m = $('#antrag-meldung');
    const b = { von: $('#antrag-von').value, bis: $('#antrag-bis').value, vertretung: $('#antrag-vertretung').value, notiz: $('#antrag-notiz').value };
    if (!b.von || !b.bis) { meldung(m, 'Bitte ersten und letzten Urlaubstag angeben.'); return; }
    if (b.bis < b.von) { meldung(m, ''); $('#antrag-bis').focus(); return; }   // der Hinweis unter den Daten sagt es schon
    $('#antrag-senden').disabled = true;
    const r = await api('hr_antrag', b);
    $('#antrag-senden').disabled = false;
    if (r.status !== 200) { meldung(m, fehlerText(r, 'Der Antrag konnte nicht gestellt werden')); return; }
    $('#antrag').reset();
    await ladeStart();
    meldung($('#antrag-meldung'), r.data.hinweis ? 'Antrag gestellt. ' + r.data.hinweis : 'Antrag gestellt – die Personalstelle entscheidet.', r.data.hinweis ? 'warn' : 'ok');
  });

  $('#mein-liste').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-zurueck]');
    if (!b) return;
    b.disabled = true;
    const r = await api('hr_antrag_zurueckziehen', { id: b.dataset.zurueck });
    if (r.status !== 200) { b.disabled = false; meldung($('#antrag-meldung'), fehlerText(r, 'Zurückziehen fehlgeschlagen')); return; }
    await ladeStart();
    meldung($('#antrag-meldung'), 'Antrag zurückgezogen.', 'ok');
  });
  // Jahr wechseln (Mein Urlaub, Anträge, Mitarbeiter teilen das Jahr)
  $('#hr-app').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-jahr]');
    if (!b) return;
    S.jahr += Number(b.dataset.jahr);
    await ladeStart();
    if (S.tab === 'antraege') ladeVerwaltung();
  });

  /* ---------- Kalender / Monatsplan ---------- */
  function kalLegende(voll) {
    const f = (cls, text, stil) => `<span><i class="${cls}" style="${stil || ''}"></i>${esc(text)}</span>`;
    const art = (k, t) => `<span><b class="hr-art ${k}">${k === 'X' ? 'x' : k}</b>${esc(t)}</span>`;
    $('#kal-legende').innerHTML = (voll ? art('U', 'Urlaub') + art('K', 'Krank') + art('G', 'Gleittag') + art('X', 'freier Tag')
      + '<span><b class="hr-art U offen">U?</b>beantragt</span>' : art('A', 'abwesend'))
      + f('', 'Wochenende', 'background:var(--hr-wochenende)') + f('', 'Feiertag', 'background:var(--hr-feiertag)')
      + f('', 'Ferien', 'background:var(--hr-ferien)') + f('', 'Urlaubssperre', 'background:var(--hr-sperre)');
  }
  async function ladeKalender() {
    const { jahr, monat } = S.kal;
    $('#kal-titel').textContent = `${MONATE[monat - 1]} ${jahr}`;
    const r = await api('hr_monat', null, `&jahr=${jahr}&monat=${monat}`);
    if (r.status !== 200) { $('#kal-plan').innerHTML = `<tbody><tr><td class="name">${esc(fehlerText(r, 'Kalender nicht verfügbar'))}</td></tr></tbody>`; return; }
    S.monat = r.data;
    if (r.data.voll && (!S.verw || S.verw.jahr !== jahr)) await ladeVerwaltung(jahr);
    zeigeKalender();
  }
  function zeigeKalender() {
    const m = S.monat, heute = S.start ? S.start.heute : iso(new Date());
    kalLegende(m.voll);
    const kl = (t) => (t.feiertag ? 'ft' : t.wochenende ? 'we' : t.ferien ? 'fe' : '');
    let html = '<thead><tr><th class="name" scope="col">Mitarbeiter</th>' + m.tage.map((t) =>
      `<th scope="col" class="${kl(t)}${t.sperre ? ' sp' : ''}${t.datum === heute ? ' heute' : ''}" title="${esc([de(t.datum), t.feiertag, t.sperre ? 'Urlaubssperre' : ''].filter(Boolean).join(' · '))}"><small>${t.wt}</small>${t.tag}</th>`).join('') + '</tr></thead><tbody>';
    let abt = null;
    for (const p of m.personen) {
      if (p.abteilung !== abt) { abt = p.abteilung; html += `<tr class="abt"><th colspan="${m.tage.length + 1}">${esc(abt || 'Ohne Abteilung')}</th></tr>`; }
      html += `<tr class="${p.ich ? 'ich' : ''}"><th class="name" scope="row" title="${esc(p.name)}">${esc(p.name)}</th>` + m.tage.map((t) => {
        const k = p.tage[t.tag] || '';
        const offen = k.endsWith('?'), code = offen ? k.slice(0, -1) : k;
        const titel = code === 'A' ? 'abwesend' : code === 'x' ? 'freier Tag' : (ART[code] || '') + (offen ? ' (beantragt)' : '');
        const inhalt = code ? `<span class="hr-art ${esc(code)}${offen ? ' offen' : ''}" title="${esc(titel)}">${esc(code === 'A' ? '•' : code)}</span>` : '';
        const klick = m.voll && !t.wochenende && !t.feiertag;
        return `<td class="${kl(t)}${klick ? ' klick' : ''}"${klick ? ` data-person="${esc(p.id)}" data-datum="${t.datum}"` : ''}>${inhalt}</td>`;
      }).join('') + '</tr>';
    }
    if (!m.personen.length) html += `<tr><td class="name" colspan="${m.tage.length + 1}">Noch keine Mitarbeiter angelegt.</td></tr>`;
    $('#kal-plan').innerHTML = html + '</tbody>';
  }
  $('#tab-kalender').addEventListener('click', (e) => {
    const b = e.target.closest('[data-monat]');
    if (b) {
      let { jahr, monat } = S.kal;
      monat += Number(b.dataset.monat);
      if (monat < 1) { monat = 12; jahr--; } else if (monat > 12) { monat = 1; jahr++; }
      S.kal = { jahr, monat };
      ladeKalender();
      return;
    }
    const td = e.target.closest('td[data-person]');
    if (td && S.verw) {
      const ein = S.verw.eintraege.find((x) => x.person === td.dataset.person && x.von <= td.dataset.datum && td.dataset.datum <= x.bis && ['genehmigt', 'beantragt'].includes(x.status));
      if (ein && ein.status === 'beantragt') { zeigeTab('antraege'); return; }
      eintragDialog(ein || { person: td.dataset.person, von: td.dataset.datum, bis: td.dataset.datum, art: 'U' });
    }
  });
  $('#kal-eintragen').addEventListener('click', async () => { if (!S.verw) await ladeVerwaltung(); eintragDialog({ art: 'K' }); });

  /* ---------- Personalstelle: Daten ---------- */
  async function ladeVerwaltung(jahr) {
    const j = jahr || S.jahr;
    const r = await api('hr_verwaltung', null, '&jahr=' + j);
    if (r.status !== 200) { fehlerVerwaltung(fehlerText(r, 'Personaldaten nicht verfügbar')); return; }
    S.verw = r.data;
    const offen = $('#hr-offen');
    offen.hidden = !r.data.offen.length; offen.textContent = r.data.offen.length || '';
    if (S.tab === 'antraege') zeigeAntraege();
  }
  function fehlerVerwaltung(text) { for (const id of ['#antraege-liste']) $(id).innerHTML = `<p class="hr-meldung fehler">${esc(text)}</p>`; }

  /* ---------- Anträge ---------- */
  function zeigeAntraege() {
    const v = S.verw;
    $('#antraege-liste').innerHTML = v.offen.length ? v.offen.map((a) => {
      const nach = a.konto.rest - (a.tageImJahr ?? a.tage);   // Konto des Beginnjahres: nur die Tage in diesem Jahr
      return `<article class="hr-antrag hr-glas" data-id="${esc(a.id)}">
        <h3>${esc(a.name)}</h3>
        <div class="zeitraum">${esc(zeitraum(a.von, a.bis))} · ${esc(tageText(a.tage))}</div>
        <dl><dt>Resturlaub ${a.tageImJahr != null && a.tageImJahr < a.tage ? esc(String(a.konto.jahr)) + ' ' : ''}danach</dt><dd${nach < 0 ? ' style="color:var(--hr-fehler);font-weight:700"' : ''}>${esc(tageText(nach))} (von ${esc(zahl(a.konto.rest))})</dd>
        ${a.vertretungName ? `<dt>Vertretung</dt><dd>${esc(a.vertretungName)}</dd>` : ''}
        ${a.kollegen.length ? `<dt>Gleichzeitig weg</dt><dd>${esc(a.kollegen.join(', '))}</dd>` : ''}
        ${a.notiz ? `<dt>Notiz</dt><dd>${esc(a.notiz)}</dd>` : ''}
        <dt>Beantragt</dt><dd>${esc(a.erfasst ? new Date(a.erfasst.t).toLocaleDateString('de-DE') : '')}</dd></dl>
        <div class="knoepfe"><button type="button" class="btn primary" data-genehmigen>Genehmigen</button><button type="button" class="btn gefahr" data-ablehnen>Ablehnen</button></div>
      </article>`;
    }).join('') : '<p class="hr-leer hr-glas">Keine offenen Anträge.</p>';
    $('#eintraege-titel').textContent = `Alle Einträge ${v.jahr}`;
    const sel = $('#eintraege-person'), alt = sel.value;
    sel.innerHTML = '<option value="">alle</option>' + v.personen.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    sel.value = alt;
    zeigeEintraege();
  }
  function zeigeEintraege() {
    const v = S.verw, f = $('#eintraege-person').value;
    const l = v.eintraege.filter((e) => !f || e.person === f);
    $('#eintraege-tabelle').innerHTML = '<thead><tr><th>Mitarbeiter</th><th>Art</th><th>Zeitraum</th><th class="zahl">Tage</th><th>Status</th><th>Notiz / Entscheidung</th><th></th></tr></thead><tbody>'
      + (l.length ? l.map((e) => `<tr><td>${esc(e.name)}</td><td><span class="hr-art ${esc(e.art)}">${esc(e.art === 'X' ? 'x' : e.art)}</span> ${esc(e.artText)}</td>
        <td>${esc(zeitraum(e.von, e.bis))}</td><td class="zahl">${esc(zahl(e.tage))}</td><td><span class="hr-pille ${esc(e.status)}">${esc(STATUS[e.status] || e.status)}</span></td>
        <td class="gedaempft">${esc([e.notiz, e.entscheidung && e.entscheidung.grund, e.urlaubAbzug ? 'vom Urlaub abgezogen' : '', e.quelle === 'import' ? 'aus Excel übernommen' : '', e.quelle === 'zeiterfassung' ? 'aus der Zeiterfassung' : ''].filter(Boolean).join(' · '))}</td>
        <td>${e.status === 'genehmigt' ? `<button type="button" class="btn" data-bearbeiten="${esc(e.id)}">Ändern</button>` : ''}</td></tr>`).join('')
        : '<tr><td colspan="7" class="gedaempft">Keine Einträge.</td></tr>') + '</tbody>';
  }
  $('#eintraege-person').addEventListener('change', zeigeEintraege);
  $('#eintraege-tabelle').addEventListener('click', (e) => {
    const b = e.target.closest('[data-bearbeiten]');
    if (b) eintragDialog(S.verw.eintraege.find((x) => x.id === b.dataset.bearbeiten));
  });
  $('#antraege-liste').addEventListener('click', async (e) => {
    const karte = e.target.closest('[data-id]');
    if (!karte) return;
    const a = S.verw.offen.find((x) => x.id === karte.dataset.id);
    if (e.target.closest('[data-genehmigen]')) {
      e.target.disabled = true;
      const r = await api('hr_entscheiden', { id: a.id, entscheidung: 'genehmigt' });
      if (r.status !== 200) { e.target.disabled = false; alertKarte(karte, fehlerText(r, 'Genehmigen fehlgeschlagen')); return; }
      await ladeVerwaltung();
      return;
    }
    if (e.target.closest('[data-ablehnen]')) {
      $('#ablehnen-text').textContent = `${a.name}: ${zeitraum(a.von, a.bis)} (${tageText(a.tage)})`;
      $('#ablehnen-grund').value = ''; meldung($('#ablehnen-meldung'), '');
      $('#dlg-ablehnen').dataset.id = a.id;
      $('#dlg-ablehnen').showModal();
    }
  });
  function alertKarte(karte, text) {
    let p = $('.hr-meldung', karte);
    if (!p) { p = document.createElement('p'); karte.append(p); }
    meldung(p, text);
  }
  $('#ablehnen-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const grund = $('#ablehnen-grund').value.trim();
    if (!grund) { meldung($('#ablehnen-meldung'), 'Bitte einen Grund angeben.'); return; }
    const r = await api('hr_entscheiden', { id: $('#dlg-ablehnen').dataset.id, entscheidung: 'abgelehnt', grund });
    if (r.status !== 200) { meldung($('#ablehnen-meldung'), fehlerText(r, 'Ablehnen fehlgeschlagen')); return; }
    $('#dlg-ablehnen').close();
    await ladeVerwaltung();
  });

  /* ---------- Abwesenheit eintragen / ändern ---------- */
  function eintragDialog(e) {
    // Personaldaten fehlen (z. B. Verbindung abgebrochen): Hinweis statt Skriptfehler
    if (!S.verw) { meldung($('#kal-meldung'), 'Personaldaten nicht verfügbar. Bitte die Seite neu laden.'); return; }
    meldung($('#kal-meldung'), '');
    const d = $('#dlg-eintrag');
    d.dataset.id = e.id || '';
    $('#dlg-eintrag-titel').textContent = e.id ? 'Abwesenheit ändern' : 'Abwesenheit eintragen';
    $('#eintrag-person').innerHTML = '<option value="">– bitte wählen –</option>' + S.verw.personen.filter((p) => p.aktiv || p.id === e.person)
      .map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    $('#eintrag-person').value = e.person || '';
    $('#eintrag-art').value = e.art || 'U';
    $('#eintrag-von').value = e.von || ''; $('#eintrag-bis').value = e.bis || '';
    $('#eintrag-notiz').value = e.notiz || '';
    $('#eintrag-storno').hidden = !e.id;
    meldung($('#eintrag-meldung'), '');
    d.showModal();
  }
  $('#eintrag-von').addEventListener('change', () => { if (!$('#eintrag-bis').value || $('#eintrag-bis').value < $('#eintrag-von').value) $('#eintrag-bis').value = $('#eintrag-von').value; });
  async function nachEintrag() {
    $('#dlg-eintrag').close();
    await ladeVerwaltung(S.tab === 'kalender' ? S.kal.jahr : undefined);
    if (S.tab === 'kalender') await ladeKalender();
    ladeStart();
  }
  $('#eintrag-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const b = { id: $('#dlg-eintrag').dataset.id, person: $('#eintrag-person').value, art: $('#eintrag-art').value,
      von: $('#eintrag-von').value, bis: $('#eintrag-bis').value, notiz: $('#eintrag-notiz').value };
    const r = await api('hr_eintrag_save', b);
    if (r.status !== 200) { meldung($('#eintrag-meldung'), fehlerText(r, 'Speichern fehlgeschlagen')); return; }
    nachEintrag();
  });
  $('#eintrag-storno').addEventListener('click', async () => {
    const r = await api('hr_eintrag_save', { id: $('#dlg-eintrag').dataset.id, stornieren: true });
    if (r.status !== 200) { meldung($('#eintrag-meldung'), fehlerText(r, 'Stornieren fehlgeschlagen')); return; }
    nachEintrag();
  });

  /* ---------- Export ---------- */
  function zeigeExport() {
    const j = $('#export-jahr'), m = $('#export-monat');
    if (!j.options.length) {
      const jetzt = new Date();
      for (let y = jetzt.getFullYear() + 1; y >= jetzt.getFullYear() - 3; y--) j.add(new Option(String(y), String(y), false, y === jetzt.getFullYear()));
      MONATE.forEach((n, i) => m.add(new Option(n, String(i + 1), false, i === (jetzt.getMonth() + 11) % 12)));   // Standard: Vormonat
      if (jetzt.getMonth() === 0) j.value = String(jetzt.getFullYear() - 1);
    }
  }
  $('#export-jahrganz').addEventListener('change', () => { $('#export-monat').disabled = $('#export-jahrganz').checked; });
  $('#export').addEventListener('submit', async (e) => {
    e.preventDefault();
    const jahr = Number($('#export-jahr').value);
    const monate = $('#export-jahrganz').checked ? [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12] : [Number($('#export-monat').value)];
    const m = $('#export-meldung');
    meldung(m, 'Datei wird erstellt …', 'warn');
    try {
      const res = await fetch(API + '?action=hr_export', { method: 'POST', credentials: 'same-origin', cache: 'no-store',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf }, body: JSON.stringify({ jahr, monate }) });
      if (!res.ok) { let t = ''; try { t = (await res.json()).error; } catch { /* kein JSON */ } throw new Error(t || `Export fehlgeschlagen (${res.status}).`); }
      const name = ((res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/) || [])[1] || 'Urlaub.xlsx';
      const url = URL.createObjectURL(await res.blob());
      const a = Object.assign(document.createElement('a'), { href: url, download: name });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      meldung(m, `${name} wurde heruntergeladen.`, 'ok');
    } catch (err) { meldung(m, err.message || String(err)); }
  });

  /* Dialoge: „Abbrechen“/„Schließen“ */
  for (const b of $$('[data-schliessen]')) b.addEventListener('click', () => b.closest('dialog').close());

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
    $('#hr-user').hidden = false; $('#hr-user-name').textContent = name; $('#hr-initialen').textContent = initialen(name);
    if (!(await ladeStart())) return;
    $('#hr-login').hidden = true; $('#hr-app').hidden = false;
    const tab = location.hash.slice(1);
    const knopf = $(`#hr-tabs button[data-tab="${CSS.escape(tab)}"]`);
    zeigeTab(knopf && !knopf.hidden ? tab : 'mein');
  }
  themaKnopf();
  laden().catch(() => fehler('Keine Verbindung zum Server.'));
})();
