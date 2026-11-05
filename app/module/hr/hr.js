/* STAFL-Plattform · HR · Urlaub
   Gleittage-Konto (02.11.2026): Personalstelle gewährt Gleittage (Übersicht → „Gleittage gewähren“), Mitarbeiter sehen Rest und
   Gewährungen und beantragen Gleittage wie Urlaub (nur soweit der Rest reicht), Genehmiger sehen den Gleittage-Rest.
   Mitarbeiter: eigenes Urlaubskonto (nur Urlaub, nie Krankheit), Urlaubsantrag (ausblendbar: Verwaltung → Urlaub, Schalter
   „Urlaubsanträge über die Plattform“), Liste „Mein Urlaub und Anträge“ (nur Urlaub), Mini-Kalender „Mein Jahr“ mit allen
   eigenen Abwesenheiten und „Korrektur melden“ (geht an die Personalstelle), Abwesenheitskalender (Kollegen nur „abwesend“).
   Urlaubsübersicht (Recht hr.uebersicht, auch Personalstelle): alle Mitarbeiter mit Summen (Konto, Krank-, Gleittage).
   Urlaub genehmigen (Recht hr.genehmigen): offene Anträge genehmigen/ablehnen – nie den eigenen.
   Jahresplanung (03.11.2026): Mitarbeiter sehen in der Planungsphase den Stand ihrer Vorplanung des nächsten Jahres
   (Ziel: Anteil des Anspruchs bis zum Stichtag), Vertretung ist bei Urlaubsanträgen Pflicht (abschaltbar). Reiter
   „Jahresplanung“ (nur Personalstelle; gesammelt genehmigen mit „Urlaub genehmigen“): Stand je Mitarbeiter, Zeitleiste mit Konflikten, Anträge
   mit Konflikten genehmigen/ablehnen, konfliktfreie gesammelt genehmigen, Erinnerung, Abschluss mit Jahresübersicht.
   Personalstelle (Recht hr.verwalten): Korrekturmeldungen erledigen (mit Antwort, nie die eigene), Abwesenheiten eintragen (U, K, G, freier Tag; nicht für sich selbst),
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
  const ART = { U: 'Urlaub', K: 'Krank', G: 'Gleittag', X: 'Freier Tag', F: 'Unentschuldigt' };
  const STATUS = { beantragt: 'beantragt', genehmigt: 'genehmigt', abgelehnt: 'abgelehnt', zurueckgezogen: 'zurückgezogen', storniert: 'storniert' };
  let csrf = '';
  const S = { art: 'U', gleit: null, offen: [], ueb: null, ujahr: new Date().getFullYear(), start: null, jahr: new Date().getFullYear(), kal: { jahr: new Date().getFullYear(), monat: new Date().getMonth() + 1 }, verw: null, tab: 'mein', pjahr: null, jp: null, jpFilter: 'alle' };

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
  const zahl = (n) => window.STAFL_FORMAT.zahl(Math.round(n * 2) / 2, 0, 1);   // halbe Tage, echtes Minus wie überall
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
    if (tab === 'antraege') ladeAntraege();
    if (tab === 'export') zeigeExport();
    if (tab === 'uebersicht') ladeUebersicht();
    if (tab === 'planung') ladePlanung();
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
    for (const el of $$('[data-antraege]')) el.hidden = !(r.data.verwalten || r.data.genehmigen);
    for (const el of $$('[data-uebersicht]')) el.hidden = !r.data.uebersicht;
    for (const el of $$('[data-planung]')) el.hidden = !r.data.verwalten;   // Jahresplanung nur für die Personalstelle (Datenschutz)
    const offen = $('#hr-offen'), n = (r.data.offen || 0) + (r.data.korrekturenOffen || 0);   // Anträge und Korrekturmeldungen (Personalstelle)
    offen.hidden = !n; offen.textContent = n || '';
    zeigeMein();
    return true;
  }

  function wert(titel, n, cls = '', zusatz = '') {
    return `<div class="hr-wert hr-glas ${cls}"><span>${esc(titel)}</span><b>${esc(zahl(n))}</b>${zusatz ? `<small>${esc(zusatz)}</small>` : ''}</div>`;
  }
  function zeigeMein() {
    const d = S.start;
    $('#mein-titel').textContent = `Mein Urlaub ${d.jahr}`;
    $('#mein-ohne').hidden = !!d.ich;
    $('#mein-inhalt').hidden = !d.ich;
    if (!d.ich) return;
    const k = d.konto;
    $('#mein-konto').innerHTML =
      wert('Resturlaub', k.rest, 'haupt' + (k.rest < 0 ? ' minus' : ''), k.beantragt ? `davon ${tageText(k.beantragt)} beantragt` : '')
      + wert('Anspruch', k.anspruch)
      + wert('Übertrag Vorjahr', k.uebertrag, '', k.verfaellt > 0 ? `${tageText(k.verfaellt)} verfallen nach ${de(k.frist)}` : (k.verfallen > 0 ? `${tageText(k.verfallen)} verfallen` : (k.verfall === false && k.uebertrag > 0 ? 'verfällt nicht' : '')))
      + wert('Genommen', k.genommen)
      + wert('Geplant', k.geplant)
      + wert('Beantragt', k.beantragt);
    zeigeGleitMein();
    zeigePlanungMein();
    // Urlaubsanträge ausgeschaltet (Verwaltung → Urlaub): Formular ausblenden, Hinweis zeigen – der Server lehnt Anträge ohnehin ab
    const antraege = d.antraege !== false;
    $('#antrag').hidden = !antraege;
    $('#antrag-aus').hidden = antraege;
    zeigeRegeln(d.regeln);
    $('#mein-spalten').classList.toggle('ohne-antrag', !antraege);
    const sel = $('#antrag-vertretung'), alt = sel.value;
    sel.innerHTML = '<option value="">– keine –</option>' + d.kollegen.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    sel.value = alt;
    vertretungFeld();
    // Liste: Urlaub, Gleittage und Anträge – Krank und freie Tage stehen im Mini-Kalender „Mein Jahr“
    const liste = d.eintraege.filter((e) => (e.art === 'U' || e.art === 'G') && e.von <= `${d.jahr}-12-31` && e.bis >= `${d.jahr}-01-01`);
    $('#mein-liste').innerHTML = liste.length ? liste.map((e) => {
      const zurueck = (e.art === 'U' || e.art === 'G') && (e.status === 'beantragt' || (e.status === 'genehmigt' && e.von > d.heute));
      const ent = e.entscheidung && e.status !== 'genehmigt' && e.entscheidung.grund ? `Grund: ${e.entscheidung.grund}` : '';
      return `<li><span class="hr-art ${esc(e.art)}" title="${esc(e.artText)}">${esc(e.art === 'X' ? 'x' : e.art)}</span>
        <span class="zeitraum">${esc(zeitraum(e.von, e.bis))}</span><span>${esc(tageText(e.tage))}</span>
        <span class="hr-pille ${esc(e.status)}">${esc(STATUS[e.status] || e.status)}</span>
        ${zurueck ? `<button type="button" class="btn" data-zurueck="${esc(e.id)}">Zurückziehen</button>` : ''}
        ${e.notiz || ent ? `<span class="mehr">${esc([e.notiz, ent].filter(Boolean).join(' · '))}</span>` : ''}</li>`;
    }).join('') : `<li class="leer">Kein Urlaub in ${d.jahr}.</li>`;
    artSetzen(S.art);
    antragTage();
    zeigeMiniKalender();
    zeigeKorrekturen();
  }

  /* ---------- Gleittage-Konto des Mitarbeiters: Rest, gewährt, genommen und die Gewährungen ---------- */
  const vorzeichen = (n) => (n > 0 ? '+' : n < 0 ? '−' : '') + zahl(Math.abs(n));
  function zeigeGleitMein() {
    const d = S.start, g = d.gleitKonto, box = $('#mein-gleit');
    const aktiv = !!(g && g.aktiv);
    box.hidden = !aktiv;
    $('#antrag-art').hidden = !aktiv;
    if (!aktiv) { if (S.art === 'G') S.art = 'U'; return; }
    const gew = (d.gleittage || []).filter((x) => !x.storniert).slice(0, 5);
    box.innerHTML = `<div class="hr-gleit-kopf"><span>Gleittage ${esc(String(g.jahr))}</span><b class="${g.rest < 0 ? 'minus' : ''}">${esc(tageText(g.rest))} Rest</b>
      <small>${[g.uebertrag ? `${zahl(g.uebertrag)} aus dem Vorjahr` : '', `${zahl(g.gewaehrt)} gewährt`, `${zahl(g.genommen)} genommen`, g.geplant ? `${zahl(g.geplant)} geplant` : '', g.beantragt ? `${zahl(g.beantragt)} beantragt` : ''].filter(Boolean).map(esc).join(' · ')}</small></div>
      ${gew.length ? `<ul class="hr-gleit-gew">${gew.map((x) => `<li><b>${esc(vorzeichen(x.tage))}</b> am ${esc(de(x.am))}${x.grund ? ` – ${esc(x.grund)}` : ''}</li>`).join('')}</ul>` : ''}`;
  }
  function artSetzen(art) {
    const g = S.start && S.start.gleitKonto;
    S.art = art === 'G' && g && g.aktiv ? 'G' : 'U';
    $$('#antrag-art [data-art]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.art === S.art)));
    $('#antrag-titel').textContent = S.art === 'G' ? 'Gleittag beantragen' : 'Urlaub beantragen';
    $('[data-antrag-von]').textContent = S.art === 'G' ? 'Erster Gleittag' : 'Erster Urlaubstag';
    $('[data-antrag-bis]').textContent = S.art === 'G' ? 'Letzter Gleittag' : 'Letzter Urlaubstag';
    vertretungFeld();
  }
  /* Vertretung: bei Urlaub Pflicht, wenn die Personalstelle es so eingestellt hat (Verwaltung → Urlaub → Jahresplanung);
     bei Gleittagen freiwillig. Der Server prüft es ebenso (hr_antrag). */
  const vertretungPflicht = () => !!(S.start && S.start.vertretungPflicht) && S.art === 'U';
  function vertretungFeld() {
    const pflicht = vertretungPflicht(), sel = $('#antrag-vertretung');
    $('#antrag-vertretung-opt').textContent = pflicht ? '' : '(optional)';
    sel.required = pflicht;
    if (sel.options.length) sel.options[0].textContent = pflicht ? '– bitte wählen –' : '– keine –';
  }

  /* ---------- Jahresplanung: Stand der Vorplanung des nächsten Jahres (Mitarbeiter) ----------
     Nur in der Planungsphase (Server: hr_start.planung). Balken: genehmigt dunkel, beantragt heller, Strich beim Ziel. */
  function zeigePlanungMein() {
    const box = $('#mein-planung'), p = S.start && S.start.planung;
    box.hidden = !p;
    if (!p) { box.innerHTML = ''; return; }
    const proz = (n) => (p.anspruch > 0 ? Math.min(100, (n / p.anspruch) * 100) : 0);
    const zustand = p.erreicht ? 'erreicht' : p.vorbei ? 'vorbei' : '';
    const zielText = `${zahl(p.ziel)} von ${zahl(p.anspruch)} ${p.anspruch === 1 ? 'Tag' : 'Tagen'}`;
    const stand = p.erreicht ? `Ziel erreicht – ${tageText(p.geplant)} geplant`
      : `${zahl(p.geplant)} von ${zahl(p.ziel)} ${p.ziel === 1 ? 'Tag' : 'Tagen'} geplant · noch ${tageText(p.fehlt)}`;
    const satz = p.vorbei && !p.erreicht
      ? `Der Stichtag ${de(p.stichtag)} ist vorbei. Bitte planen Sie jetzt mindestens ${p.prozent} % Ihres Urlaubs ${p.jahr} – ${zielText}.`
      : `Bitte planen Sie bis zum ${de(p.stichtag)} mindestens ${p.prozent} % Ihres Urlaubs ${p.jahr} vor – ${zielText}.`;
    box.className = 'hr-mp hr-glas' + (zustand ? ' ' + zustand : '');
    box.innerHTML = `<div class="hr-mp-text"><h2 id="mp-titel">Urlaubsplanung ${esc(String(p.jahr))}</h2><p>${esc(satz)}
        ${S.start.vertretungPflicht ? ' Für jeden Zeitraum wählen Sie eine Vertretung aus.' : ''}</p></div>
      <div class="hr-mp-stand">
        <div class="hr-mp-balken" role="img" aria-label="${esc(`${zahl(p.geplant)} von ${zahl(p.anspruch)} Tagen geplant, Ziel ${zahl(p.ziel)}`)}">
          <i class="gen" style="width:${proz(p.genehmigt).toFixed(2)}%"></i><i class="bea" style="width:${proz(p.beantragt).toFixed(2)}%"></i>
          ${p.anspruch > 0 ? `<b class="ziel" style="left:${proz(p.ziel).toFixed(2)}%" title="Ziel: ${esc(tageText(p.ziel))}"></b>` : ''}
        </div>
        <p class="hr-mp-zahl" id="mp-stand">${esc(stand)}</p>
        <p class="hr-mp-legende"><span><i class="gen"></i>genehmigt ${esc(zahl(p.genehmigt))}</span><span><i class="bea"></i>beantragt ${esc(zahl(p.beantragt))}</span><span><i class="ziel"></i>Ziel ${esc(zahl(p.ziel))}</span></p>
      </div>
      ${S.start.antraege !== false ? `<button type="button" class="btn primary" id="mp-planen">Urlaub ${esc(String(p.jahr))} planen</button>` : ''}`;
  }
  $('#mein-planung').addEventListener('click', async (e) => {
    if (!e.target.closest('#mp-planen')) return;
    const p = S.start.planung;
    if (S.jahr !== p.jahr) { S.jahr = p.jahr; await ladeStart(); }
    zeigeTab('mein');
    artSetzen('U');
    $('#antrag').scrollIntoView({ behavior: 'smooth', block: 'center' });
    $('#antrag-von').focus();
  });
  $('#antrag-art').addEventListener('click', (e) => { const b = e.target.closest('[data-art]'); if (b) { artSetzen(b.dataset.art); antragTage(); } });

  /* ---------- Mein Jahr: Mini-Kalender aller eigenen Abwesenheiten ----------
     Tage wie im Urlaubskonto: U, K, G nur an Arbeitstagen der Person (ohne Feiertage und freie Tage), freie Tage (x)
     an jedem Tag des Zeitraums. Beantragt = umrandet. Tage mit Eintrag sind Knöpfe: Klick öffnet „Korrektur melden“. */
  const WT_JS = [7, 1, 2, 3, 4, 5, 6];   // Date.getDay() → ISO-Wochentag
  function zeigeMiniKalender() {
    const d = S.start, jahr = d.jahr, ft = d.feiertage || {}, arbeit = new Set((d.ich && d.ich.arbeitstage) || [1, 2, 3, 4, 5]);
    const tag = {};   // Datum → { art, offen, id }
    const aktiv = d.eintraege.filter((e) => e.status === 'genehmigt' || e.status === 'beantragt');
    const jeden = (e, f) => { for (let x = ausIso(e.von), ende = ausIso(e.bis); x <= ende; x.setDate(x.getDate() + 1)) { const s = iso(x); if (s.startsWith(String(jahr))) f(s, x); } };
    for (const e of aktiv.filter((x) => x.art === 'X')) jeden(e, (s) => { tag[s] = { art: 'X', offen: false, id: e.id }; });
    for (const e of aktiv.filter((x) => x.art !== 'X')) jeden(e, (s, x) => {
      if (!arbeit.has(WT_JS[x.getDay()]) || ft[s] || (tag[s] && tag[s].art === 'X')) return;
      tag[s] = { art: e.art, offen: e.status === 'beantragt', id: e.id };
    });
    const titel = ART;
    const leg = (stil, t) => `<span><i style="${stil}"></i>${t}</span>`;
    $('#mini-legende').innerHTML = leg('background:var(--hr-u-bg)', 'Urlaub') + leg('background:var(--hr-k-bg)', 'Krank') + leg('background:var(--hr-g-bg)', 'Gleittag')
      + leg('background:var(--hr-x-bg)', 'freier Tag') + (aktiv.some((e) => e.art === 'F') ? leg('background:var(--hr-f-bg)', 'unentschuldigt') : '')
      + leg('box-shadow:inset 0 0 0 1.5px var(--hr-u)', 'beantragt')
      + leg('background:var(--hr-feiertag)', 'Feiertag') + leg('background:var(--hr-wochenende)', 'Wochenende');
    $('#mini-kalender').innerHTML = MONATE.map((mn, m) => {
      const erster = new Date(jahr, m, 1), tage = new Date(jahr, m + 1, 0).getDate();
      let h = WT.map((w) => `<span class="wt" aria-hidden="true">${w[0]}</span>`).join('') + '<span></span>'.repeat(WT_JS[erster.getDay()] - 1);
      for (let t = 1; t <= tage; t++) {
        const dt = new Date(jahr, m, t), s = iso(dt), x = tag[s], we = WT_JS[dt.getDay()] > 5;
        const cls = ['t', we ? 'we' : '', ft[s] ? 'ft' : '', x ? x.art : '', x && x.offen ? 'offen' : '', s === d.heute ? 'heute' : ''].filter(Boolean).join(' ');
        const info = [de(s), ft[s] || '', x ? titel[x.art] + (x.offen ? ' (beantragt)' : '') : ''].filter(Boolean).join(' · ');
        h += x ? `<button type="button" class="${cls}" data-korr-tag="${s}" data-korr-eintrag="${esc(x.id)}" title="${esc(info)} – Korrektur melden" aria-label="${esc(info)}, Korrektur melden">${t}</button>`
          : `<span class="${cls}" title="${esc(info)}">${t}</span>`;
      }
      return `<div class="hr-mini-monat"><h3>${mn}</h3><div class="hr-mini-tage">${h}</div></div>`;
    }).join('');
  }
  $('#mini-kalender').addEventListener('click', (e) => {
    const b = e.target.closest('[data-korr-eintrag]');
    if (!b) return;
    const ein = S.start.eintraege.find((x) => x.id === b.dataset.korrEintrag);
    korrekturDialog(ein ? { von: ein.von, bis: ein.bis, eintrag: ein, tag: b.dataset.korrTag } : { von: b.dataset.korrTag, bis: b.dataset.korrTag });
  });

  /* ---------- Korrektur melden (an die Personalstelle) ---------- */
  function korrekturDialog(v = {}) {
    const dlg = $('#dlg-korrektur');
    dlg.dataset.eintrag = v.eintrag ? v.eintrag.id : '';
    $('#korrektur-von').value = v.von || ''; $('#korrektur-bis').value = v.bis || '';
    $('#korrektur-text').value = '';
    const bezug = $('#korrektur-bezug');
    bezug.hidden = !v.eintrag;
    bezug.textContent = v.eintrag ? `Eintrag: ${v.eintrag.artText} ${zeitraum(v.eintrag.von, v.eintrag.bis)} (${STATUS[v.eintrag.status] || v.eintrag.status})` : '';
    meldung($('#korrektur-meldung'), '');
    dlg.showModal();
    $('#korrektur-text').focus();
  }
  $('#korrektur-neu').addEventListener('click', () => korrekturDialog());
  $('#korrektur-text').addEventListener('input', () => meldung($('#korrektur-meldung'), ''));   // Hinweis gilt nach der Eingabe nicht mehr
  $('#korrektur-von').addEventListener('change', () => { if (!$('#korrektur-bis').value || $('#korrektur-bis').value < $('#korrektur-von').value) $('#korrektur-bis').value = $('#korrektur-von').value; });
  $('#korrektur-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const m = $('#korrektur-meldung');
    const b = { text: $('#korrektur-text').value.trim(), von: $('#korrektur-von').value, bis: $('#korrektur-bis').value, eintrag: $('#dlg-korrektur').dataset.eintrag || '' };
    if (b.text.length < 3) { meldung(m, 'Bitte kurz beschreiben, was nicht stimmt.'); $('#korrektur-text').focus(); return; }
    if (b.von && b.bis && b.bis < b.von) { meldung(m, 'Das Ende liegt vor dem Beginn.'); return; }
    $('#korrektur-senden').disabled = true;
    const r = await api('hr_korrektur', b);
    $('#korrektur-senden').disabled = false;
    if (r.status !== 200) { meldung(m, fehlerText(r, 'Die Meldung konnte nicht gesendet werden')); return; }
    $('#dlg-korrektur').close();
    await ladeStart();
    meldung($('#korrektur-info'), 'Danke – Ihre Meldung ist bei der Personalstelle.', 'ok');
  });
  function zeigeKorrekturen() {
    const l = S.start.korrekturen || [];
    $('#korrektur-eigene').hidden = !l.length;
    $('#korrektur-liste').innerHTML = l.map((k) => `<li><span class="hr-pille ${esc(k.status)}">${k.status === 'erledigt' ? 'erledigt' : 'offen'}</span>
      <span class="zeitraum">${k.von ? esc(zeitraum(k.von, k.bis)) : 'ohne Zeitraum'}</span>
      <span class="gedaempft">gemeldet am ${esc(k.erfasst ? window.STAFL_FORMAT.datum(k.erfasst.t) : '')}</span>
      <span class="text">${esc(k.text)}</span>
      ${k.erledigt ? `<span class="mehr">Personalstelle${k.erledigt.antwort ? ': ' + esc(k.erledigt.antwort) : ' hat die Meldung erledigt.'}</span>` : ''}</li>`).join('');
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
    const g = d.gleitKonto;
    if (n && S.art === 'G') {
      const frei = g ? g.verfuegbar : 0;
      out.textContent = `${n === 1 ? '1 Gleittag' : `${zahl(n)} Gleittage`}${n > frei ? ` – Ihr Gleittage-Konto reicht nur für ${tageText(Math.max(0, frei))}` : ` (noch ${tageText(frei)} frei)`}`;
      return;
    }
    out.textContent = n ? `${tageText(n)} Urlaub` : 'Im Zeitraum liegen keine Arbeitstage.';
  }
  $('#antrag-von').addEventListener('change', () => { if (!$('#antrag-bis').value || $('#antrag-bis').value < $('#antrag-von').value) $('#antrag-bis').value = $('#antrag-von').value; antragTage(); });
  $('#antrag-bis').addEventListener('change', antragTage);

  $('#antrag').addEventListener('submit', async (e) => {
    e.preventDefault();
    const m = $('#antrag-meldung');
    const b = { art: S.art, von: $('#antrag-von').value, bis: $('#antrag-bis').value, vertretung: $('#antrag-vertretung').value, notiz: $('#antrag-notiz').value };
    if (!b.von || !b.bis) { meldung(m, S.art === 'G' ? 'Bitte ersten und letzten Gleittag angeben.' : 'Bitte ersten und letzten Urlaubstag angeben.'); return; }
    if (b.bis < b.von) { meldung(m, ''); $('#antrag-bis').focus(); return; }   // der Hinweis unter den Daten sagt es schon
    if (vertretungPflicht() && !b.vertretung) { meldung(m, 'Bitte wählen Sie eine Vertretung für die Zeit Ihres Urlaubs aus.'); $('#antrag-vertretung').focus(); return; }
    $('#antrag-senden').disabled = true;
    const r = await api('hr_antrag', b);
    $('#antrag-senden').disabled = false;
    if (r.status !== 200) { meldung(m, fehlerText(r, 'Der Antrag konnte nicht gestellt werden')); return; }
    $('#antrag').reset();
    S.art = 'U';
    await ladeStart();
    meldung($('#antrag-meldung'), r.data.hinweis ? 'Antrag gestellt. ' + r.data.hinweis : 'Antrag gestellt – er wird jetzt geprüft.', r.data.hinweis ? 'warn' : 'ok');
  });

  /* Rückfrage im eigenen Fenster: Escape oder „Abbrechen“ = nein, der Fokus liegt auf „Abbrechen“ */
  function frage(titel, text, ja = 'Ja') {
    const d = $('#dlg-frage');
    $('#fr-titel').textContent = titel; $('#fr-text').textContent = text; $('#fr-ja').textContent = ja;
    return new Promise((ok) => {
      const fertig = (w) => { d.removeEventListener('click', klick); d.removeEventListener('close', zu); if (d.open) d.close(); ok(w); };
      const klick = (e) => { const k = e.target.closest('[data-antwort]'); if (k) fertig(k.dataset.antwort === 'ja'); };
      const zu = () => fertig(false);
      d.addEventListener('click', klick); d.addEventListener('close', zu);
      d.showModal(); $('#fr-nein').focus();
    });
  }

  $('#mein-liste').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-zurueck]');
    if (!b) return;
    if (!(await frage('Antrag zurückziehen?', 'Der Antrag wird zurückgenommen und nicht weiter geprüft. Bei Bedarf können Sie ihn neu stellen.', 'Zurückziehen'))) return;
    b.disabled = true;
    const ziel = () => ($('#antrag').hidden ? $('#mein-info') : $('#antrag-meldung'));   // ohne Antragsformular: Meldung über dem Konto
    const r = await api('hr_antrag_zurueckziehen', { id: b.dataset.zurueck });
    if (r.status !== 200) { b.disabled = false; meldung(ziel(), fehlerText(r, 'Zurückziehen fehlgeschlagen')); return; }
    await ladeStart();
    meldung(ziel(), 'Antrag zurückgezogen.', 'ok');
  });
  // Jahr wechseln (Mein Urlaub, Anträge, Mitarbeiter teilen das Jahr)
  $('#hr-app').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-jahr]');
    if (!b) return;
    S.jahr += Number(b.dataset.jahr);
    await ladeStart();
    if (S.tab === 'antraege') ladeAntraege();
  });

  /* ---------- Kalender / Monatsplan ---------- */
  function kalLegende(voll) {
    const f = (cls, text, stil) => `<span><i class="${cls}" style="${stil || ''}"></i>${esc(text)}</span>`;
    const art = (k, t) => `<span><b class="hr-art ${k}">${k === 'X' ? 'x' : k}</b>${esc(t)}</span>`;
    $('#kal-legende').innerHTML = (voll ? art('U', 'Urlaub') + art('K', 'Krank') + art('G', 'Gleittag') + art('X', 'freier Tag') + art('F', 'unentschuldigt')
      + '<span><b class="hr-art U offen">U?</b>beantragt</span>' : art('A', 'abwesend'))
      + f('', 'Wochenende', 'background:var(--hr-wochenende)') + f('', 'Feiertag', 'background:var(--hr-feiertag)')
      + f('', 'Ferien', 'background:var(--hr-ferien)') + f('', 'Urlaubssperre', 'background:var(--hr-sperre)')
      + f('', 'Heute', 'background:var(--hr-heute);box-shadow:inset 2px 0 0 var(--hr-akzent-ink),inset -2px 0 0 var(--hr-akzent-ink)');
  }
  /* Spalte „heute“ in den sichtbaren Bereich holen (am Handy scrollt die Tabelle waagerecht): nur wenn sie verdeckt ist,
     dann mittig rechts neben die festen Namen */
  function heuteSichtbar() {
    const th = $('#kal-plan thead th.heute'), box = $('#kal-plan').parentElement, name = $('#kal-plan thead th.name');
    if (!th || !box || box.scrollWidth <= box.clientWidth) return;
    const links = name ? name.offsetWidth : 0, sicht = box.clientWidth - links;
    if (th.offsetLeft - links >= box.scrollLeft && th.offsetLeft + th.offsetWidth <= box.scrollLeft + box.clientWidth) return;
    box.scrollLeft = Math.max(0, th.offsetLeft - links - (sicht - th.offsetWidth) / 2);
  }
  /* Ansicht „Monat“ oder „± 2 Wochen“ um einen Tag (Standard heute, Pfeile verschieben um eine Woche) und Filter nach
     Abteilungen. Beides merkt sich nur dieser Browser (Bequemlichkeit, keine Berechtigung – der Server liefert
     unverändert je Monat, hr_monat). Der Zeitraum entsteht aus den betroffenen Monaten (höchstens zwei). */
  const KAL_SPEICHER = 'hr.kalender';
  const plusTage = (d, n) => { const x = new Date(d + 'T12:00:00Z'); x.setUTCDate(x.getUTCDate() + n); return x.toISOString().slice(0, 10); };
  (() => {
    try {
      const v = JSON.parse(localStorage.getItem(KAL_SPEICHER) || '{}');
      S.kal.modus = v.modus === 'zeitraum' ? 'zeitraum' : 'monat';
      S.kal.abt = new Set(Array.isArray(v.abt) ? v.abt.filter((a) => typeof a === 'string') : []);
    } catch { S.kal.modus = 'monat'; S.kal.abt = new Set(); }
  })();
  const kalMerken = () => { try { localStorage.setItem(KAL_SPEICHER, JSON.stringify({ modus: S.kal.modus, abt: [...S.kal.abt] })); } catch { /* ohne Speicher */ } };
  const heuteIso = () => (S.start ? S.start.heute : iso(new Date()));
  /* Monatsdaten zu einem Plan zusammenführen: Tage im Zeitraum, Mitarbeiter je Abteilung in der Reihenfolge des Servers,
     Kürzel je Datum (der Server liefert je Monat Kürzel je Tag des Monats) */
  function kalZusammen(daten, von, bis) {
    const tage = daten.flatMap((d) => d.tage).filter((t) => !von || (t.datum >= von && t.datum <= bis));
    const gruppen = new Map(), personen = new Map();
    for (const d of daten) {
      const vor = `${d.jahr}-${String(d.monat).padStart(2, '0')}-`;
      for (const p of d.personen) {
        let x = personen.get(p.id);
        if (!x) {
          x = { ...p, tage: {} }; personen.set(p.id, x);
          if (!gruppen.has(p.abteilung)) gruppen.set(p.abteilung, []);
          gruppen.get(p.abteilung).push(x);
        }
        for (const [tag, k] of Object.entries(p.tage || {})) x.tage[vor + String(tag).padStart(2, '0')] = k;
      }
    }
    return { voll: !!daten[0].voll, tage, personen: [...gruppen.values()].flat() };
  }
  async function ladeKalender() {
    const k = S.kal, zeitraum = k.modus === 'zeitraum';
    let von = null, bis = null, monate = [[k.jahr, k.monat]];
    if (zeitraum) {
      if (!k.mitte) k.mitte = heuteIso();
      von = plusTage(k.mitte, -14); bis = plusTage(k.mitte, 14);
      k.jahr = Number(k.mitte.slice(0, 4)); k.monat = Number(k.mitte.slice(5, 7));
      monate = [];
      for (let j = Number(von.slice(0, 4)), m = Number(von.slice(5, 7)); `${j}-${String(m).padStart(2, '0')}` <= bis.slice(0, 7); m === 12 ? (m = 1, j++) : m++) monate.push([j, m]);
    }
    $('#kal-titel').textContent = zeitraum ? `${von.slice(0, 4) === bis.slice(0, 4) ? de(von).slice(0, 6) : de(von)} – ${de(bis)}` : `${MONATE[k.monat - 1]} ${k.jahr}`;
    for (const b of $$('#kal-modus button')) b.setAttribute('aria-pressed', String(b.dataset.modus === k.modus));
    $('[data-monat="-1"]').setAttribute('aria-label', zeitraum ? 'Eine Woche zurück' : 'Vorheriger Monat');
    $('[data-monat="1"]').setAttribute('aria-label', zeitraum ? 'Eine Woche vor' : 'Nächster Monat');
    const rs = await Promise.all(monate.map(([j, m]) => api('hr_monat', null, `&jahr=${j}&monat=${m}`)));
    const fehl = rs.find((r) => r.status !== 200);
    if (fehl) { $('#kal-filter').innerHTML = ''; $('#kal-plan').innerHTML = `<tbody><tr><td class="name">${esc(fehlerText(fehl, 'Kalender nicht verfügbar'))}</td></tr></tbody>`; return; }
    S.monat = kalZusammen(rs.map((r) => r.data), von, bis);
    if (S.monat.voll && (!S.verw || S.verw.jahr !== k.jahr)) await ladeVerwaltung(k.jahr);
    zeigeKalender();
  }
  /* Abteilung als durchgehender Balken über die ganze Breite; Name bleibt beim seitlichen Wischen links stehen (Kalender und Übersicht) */
  // Abteilungsbalken; im Kalender mit der Spalte „heute“ (Index ab 0 nach der Namensspalte) geteilt, damit die Heute-Säule durchläuft
  const abtZeile = (abt, n, spalten, heute = -1) => {
    const titel = `<span>${esc(abt || 'Ohne Abteilung')}<small>${n}</small></span>`;
    if (heute < 0) return `<tr class="abt"><th colspan="${spalten}" scope="rowgroup">${titel}</th></tr>`;
    const rest = spalten - heute - 2;
    return `<tr class="abt"><th colspan="${heute + 1}" scope="rowgroup">${titel}</th><td class="heute" aria-hidden="true"></td>${rest > 0 ? `<th class="rest" colspan="${rest}" aria-hidden="true"></th>` : ''}</tr>`;
  };
  function kalFilter(alle) {
    const aktiv = S.kal.abt;
    const knopf = (wert, text, an) => `<button type="button" class="hr-chip" data-abt="${esc(wert)}" aria-pressed="${an}">${esc(text)}</button>`;
    $('#kal-filter').innerHTML = alle.length < 2 ? '' : `<span class="hr-chip-titel">Abteilungen</span>${knopf('*', 'Alle', !aktiv.size)}`
      + alle.map((a) => knopf(a, a || 'Ohne Abteilung', aktiv.has(a))).join('');
  }
  function zeigeKalender() {
    const m = S.monat, heute = heuteIso(), zeitraum = S.kal.modus === 'zeitraum';
    kalLegende(m.voll);
    const alle = [...new Set(m.personen.map((p) => p.abteilung))];
    for (const a of [...S.kal.abt]) if (!alle.includes(a)) S.kal.abt.delete(a);   // entfallene Abteilungen vergessen
    kalFilter(alle);
    const personen = m.personen.filter((p) => !S.kal.abt.size || S.kal.abt.has(p.abteilung));
    const kl = (t) => (t.feiertag ? 'ft' : t.wochenende ? 'we' : t.ferien ? 'fe' : '');
    const neuerMonat = (t, i) => zeitraum && i > 0 && t.tag === 1;   // Monatswechsel im Zeitraum: Trennlinie und „1.11.“
    let html = '<thead><tr><th class="name" scope="col">Mitarbeiter</th>' + m.tage.map((t, i) =>
      `<th scope="col" class="${kl(t)}${t.sperre ? ' sp' : ''}${t.datum === heute ? ' heute' : ''}${neuerMonat(t, i) ? ' mstart' : ''}" title="${esc([de(t.datum), t.datum === heute ? 'heute' : '', t.feiertag, t.sperre ? 'Urlaubssperre' : ''].filter(Boolean).join(' · '))}"${t.datum === heute ? ' aria-current="date"' : ''}>`
      + (t.datum === heute ? `<small>Heute</small><span class="hr-heute-tag">${neuerMonat(t, i) ? `1.${t.datum.slice(5, 7)}.` : t.tag}</span>` : `<small>${t.wt}</small>${neuerMonat(t, i) ? `1.${t.datum.slice(5, 7)}.` : t.tag}`) + '</th>').join('') + '</tr></thead><tbody>';
    const heuteSpalte = m.tage.findIndex((t) => t.datum === heute);
    let abt = null;
    for (const p of personen) {
      if (p.abteilung !== abt) { abt = p.abteilung; html += abtZeile(abt, personen.filter((x) => x.abteilung === abt).length, m.tage.length + 1, heuteSpalte); }
      html += `<tr class="${p.ich ? 'ich' : ''}"><th class="name" scope="row" title="${esc(p.name)}">${esc(p.name)}</th>` + m.tage.map((t, i) => {
        const k = p.tage[t.datum] || '';
        const offen = k.endsWith('?'), code = offen ? k.slice(0, -1) : k;
        const titel = code === 'A' ? 'abwesend' : code === 'x' ? 'freier Tag' : (ART[code] || '') + (offen ? ' (beantragt)' : '');
        const inhalt = code ? `<span class="hr-art ${esc(code)}${offen ? ' offen' : ''}" title="${esc(titel)}">${esc(code === 'A' ? '•' : code)}</span>` : '';
        const klick = m.voll && !p.ich && !t.wochenende && !t.feiertag;   // eigene Abwesenheiten trägt eine andere Person ein
        return `<td class="${kl(t)}${t.datum === heute ? ' heute' : ''}${neuerMonat(t, i) ? ' mstart' : ''}${klick ? ' klick' : ''}"${klick ? ` data-person="${esc(p.id)}" data-datum="${t.datum}"` : ''}>${inhalt}</td>`;
      }).join('') + '</tr>';
    }
    if (!m.personen.length) html += `<tr><td class="name" colspan="${m.tage.length + 1}">Noch keine Mitarbeiter angelegt.</td></tr>`;
    $('#kal-plan').innerHTML = html + '</tbody>';
    heuteSichtbar();
  }
  $('#tab-kalender').addEventListener('click', async (e) => {
    const k = S.kal;
    const b = e.target.closest('[data-monat]');
    if (b) {
      if (k.modus === 'zeitraum') k.mitte = plusTage(k.mitte || heuteIso(), 7 * Number(b.dataset.monat));
      else {
        k.monat += Number(b.dataset.monat);
        if (k.monat < 1) { k.monat = 12; k.jahr--; } else if (k.monat > 12) { k.monat = 1; k.jahr++; }
      }
      ladeKalender();
      return;
    }
    if (e.target.closest('#kal-heute')) {
      const h = heuteIso();
      k.mitte = h; k.jahr = Number(h.slice(0, 4)); k.monat = Number(h.slice(5, 7));
      ladeKalender();
      return;
    }
    const mo = e.target.closest('#kal-modus button[data-modus]');
    if (mo) {
      if (mo.dataset.modus === k.modus) return;
      k.modus = mo.dataset.modus;
      if (k.modus === 'zeitraum') k.mitte = heuteIso();   // ± 2 Wochen beginnt immer bei heute
      kalMerken();
      ladeKalender();
      return;
    }
    const ch = e.target.closest('#kal-filter [data-abt]');
    if (ch) {
      const a = ch.dataset.abt;
      if (a === '*') k.abt.clear();
      else if (k.abt.has(a)) k.abt.delete(a);
      else k.abt.add(a);
      kalMerken();
      zeigeKalender();
      return;
    }
    const td = e.target.closest('td[data-person]');
    if (td && S.verw) {
      const j = Number(td.dataset.datum.slice(0, 4));
      if (S.verw.jahr !== j) await ladeVerwaltung(j);   // Zeitraum über den Jahreswechsel
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
    S.offen = r.data.offen;
    zahlOffen();
    if (S.tab === 'antraege') zeigeAntraege();
  }
  /* Offene Anträge: Personalstelle über hr_verwaltung, sonst (nur „Urlaub genehmigen“) über hr_offen */
  async function ladeAntraege() {
    if (S.start && S.start.verwalten) { await ladeVerwaltung(); return; }
    const r = await api('hr_offen');
    if (r.status !== 200) { fehlerVerwaltung(fehlerText(r, 'Anträge nicht verfügbar')); return; }
    S.offen = r.data.offen;
    zahlOffen();
    if (S.tab === 'antraege') zeigeAntraege();
  }
  // Zahl am Reiter: entscheidbare Anträge (ohne eigene); ohne Genehmigungsrecht alle offenen
  function zahlOffen() {
    const korr = S.verw && S.verw.korrekturen ? S.verw.korrekturen.filter((k) => k.status === 'offen' && !k.eigen).length : 0;
    const n = S.offen.filter((a) => !(S.start && S.start.genehmigen) || !a.eigen).length + korr;
    const offen = $('#hr-offen');
    offen.hidden = !n; offen.textContent = n || '';
  }
  function fehlerVerwaltung(text) { for (const id of ['#antraege-liste']) $(id).innerHTML = `<p class="hr-meldung fehler">${esc(text)}</p>`; }

  /* ---------- Anträge ---------- */
  function zeigeAntraege() {
    const darf = !!(S.start && S.start.genehmigen);
    $('#antraege-liste').innerHTML = S.offen.length ? S.offen.map((a) => {
      const gleit = a.art === 'G' && a.gleitKonto;
      const k = gleit ? a.gleitKonto : a.konto;
      const nach = k.rest - (a.tageImJahr ?? a.tage);   // Konto des Beginnjahres: nur die Tage in diesem Jahr
      return `<article class="hr-antrag hr-glas" data-id="${esc(a.id)}">
        <h3>${esc(a.name)}${a.art === 'G' ? ' <span class="hr-pille gleit">Gleittag</span>' : ''}</h3>
        <div class="zeitraum">${esc(zeitraum(a.von, a.bis))} · ${esc(tageText(a.tage))}</div>
        <dl><dt>${gleit ? 'Gleittage' : 'Resturlaub'} ${a.tageImJahr != null && a.tageImJahr < a.tage ? esc(String(k.jahr)) + ' ' : ''}danach</dt><dd${nach < 0 ? ' style="color:var(--hr-fehler);font-weight:700"' : ''}>${esc(tageText(nach))} (von ${esc(zahl(k.rest))})</dd>
        ${a.vertretungName ? `<dt>Vertretung</dt><dd>${esc(a.vertretungName)}</dd>` : ''}
        ${a.kollegen.length ? `<dt>Gleichzeitig weg</dt><dd>${esc(a.kollegen.join(', '))}</dd>` : ''}
        ${a.notiz ? `<dt>Notiz</dt><dd>${esc(a.notiz)}</dd>` : ''}
        <dt>Beantragt</dt><dd>${esc(a.erfasst ? window.STAFL_FORMAT.datum(a.erfasst.t) : '')}</dd></dl>
        ${darf && !a.eigen ? '<div class="knoepfe"><button type="button" class="btn primary" data-genehmigen>Genehmigen</button><button type="button" class="btn gefahr" data-ablehnen>Ablehnen</button></div>'
          : `<p class="hr-hinweis">${a.eigen ? 'Ihr eigener Antrag – darüber entscheidet eine andere Person mit dem Recht „Urlaub genehmigen“.' : 'Die Entscheidung trifft eine Person mit dem Recht „Urlaub genehmigen“.'}</p>`}
      </article>`;
    }).join('') : '<p class="hr-leer hr-glas">Keine offenen Anträge.</p>';
    if (!S.start || !S.start.verwalten || !S.verw) return;   // „Alle Einträge“ nur für die Personalstelle
    zeigeKorrekturenVerwaltung();
    const v = S.verw;
    $('#eintraege-titel').textContent = `Alle Einträge ${v.jahr}`;
    const sel = $('#eintraege-person'), alt = sel.value;
    sel.innerHTML = '<option value="">alle</option>' + v.personen.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}${p.ehemalig ? ' (ehemalig)' : ''}</option>`).join('');
    sel.value = alt;
    zeigeEintraege();
  }
  function zeigeEintraege() {
    const v = S.verw, f = $('#eintraege-person').value;
    const l = v.eintraege.filter((e) => !f || e.person === f);
    const ehemalig = new Set(v.personen.filter((p) => p.ehemalig).map((p) => p.id));   // ohne Mitarbeiter: Einträge bleiben, Person markiert
    $('#eintraege-tabelle').innerHTML = '<thead><tr><th>Mitarbeiter</th><th>Art</th><th>Zeitraum</th><th class="zahl">Tage</th><th>Status</th><th>Notiz / Entscheidung</th><th></th></tr></thead><tbody>'
      + (l.length ? l.map((e) => `<tr><td>${esc(e.name)}${ehemalig.has(e.person) ? ' <span class="gedaempft">(ehemalig)</span>' : ''}</td><td><span class="hr-art ${esc(e.art)}">${esc(e.art === 'X' ? 'x' : e.art)}</span> ${esc(e.artText)}</td>
        <td>${esc(zeitraum(e.von, e.bis))}</td><td class="zahl">${esc(zahl(e.tage))}</td><td><span class="hr-pille ${esc(e.status)}">${esc(STATUS[e.status] || e.status)}</span></td>
        <td class="gedaempft">${esc([e.notiz, e.entscheidung && e.entscheidung.grund, e.urlaubAbzug ? 'in der Zeiterfassung vom Urlaub abgezogen (zählt hier nicht)' : '', e.quelle === 'import' ? 'aus Excel übernommen' : '', e.quelle === 'zeiterfassung' ? 'aus der Zeiterfassung' : ''].filter(Boolean).join(' · '))}</td>
        <td>${e.status === 'genehmigt' && !e.eigen ? `<button type="button" class="btn" data-bearbeiten="${esc(e.id)}">Ändern</button>` : ''}</td></tr>`).join('')
        : '<tr><td colspan="7" class="gedaempft">Keine Einträge.</td></tr>') + '</tbody>';
  }
  $('#eintraege-person').addEventListener('change', zeigeEintraege);

  /* Korrekturmeldungen der Mitarbeiter (Personalstelle): offene mit Antwortfeld und „Erledigt“, zuletzt erledigte gedämpft */
  function zeigeKorrekturenVerwaltung() {
    const l = S.verw.korrekturen || [], offenL = l.filter((k) => k.status === 'offen'), erl = l.filter((k) => k.status !== 'offen').slice(0, 20);
    const offen = offenL.filter((k) => !k.eigen).length;
    $('#korr-zahl').hidden = !offen; $('#korr-zahl').textContent = offen || '';
    const gemeldet = (k) => `gemeldet am ${esc(k.erfasst ? window.STAFL_FORMAT.datum(k.erfasst.t) : '')}`;
    $('#korrekturen-liste').innerHTML = (offenL.length ? offenL.map((k) => `<article class="hr-korr hr-glas" data-korr="${esc(k.id)}">
        <h3>${esc(k.name)}</h3>
        <div class="zeitraum">${k.von ? esc(zeitraum(k.von, k.bis)) : 'ohne Zeitraum'}</div>
        <p class="text">${esc(k.text)}</p>
        <span class="gedaempft">${gemeldet(k)}</span>
        ${k.eigen ? '<p class="hr-korr-hinweis">Ihre eigene Meldung – sie erledigt eine andere Person der Personalstelle.</p>'
          : `<div class="antwort-zeile"><input type="text" maxlength="300" placeholder="Antwort (optional, sieht der Mitarbeiter)" aria-label="Antwort an ${esc(k.name)}"><button type="button" class="btn primary" data-korr-erledigt>Erledigt</button></div>`}
      </article>`).join('') : '<p class="hr-klein hr-voll" id="korr-leer">Keine offenen Korrekturmeldungen.</p>')
      // zuletzt erledigte (60 Tage, höchstens 20) zugeklappt und kompakt
      + (erl.length ? `<details class="hr-korr-erledigt hr-voll"><summary>Zuletzt erledigt (${erl.length})</summary><ul class="hr-liste">${erl.map((k) => `<li>
          <span class="hr-pille erledigt">erledigt</span><b>${esc(k.name)}</b><span class="zeitraum">${k.von ? esc(zeitraum(k.von, k.bis)) : 'ohne Zeitraum'}</span>
          <span class="gedaempft">${gemeldet(k)} · erledigt von ${esc(k.erledigt ? k.erledigt.by : '')}</span>
          <span class="mehr">${esc(k.text)}${k.erledigt && k.erledigt.antwort ? ' → ' + esc(k.erledigt.antwort) : ''}</span></li>`).join('')}</ul></details>` : '');
  }
  $('#korrekturen-liste').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-korr-erledigt]');
    if (!b) return;
    const karte = b.closest('[data-korr]');
    b.disabled = true;
    const r = await api('hr_korrektur_erledigt', { id: karte.dataset.korr, antwort: $('input', karte).value.trim() });
    if (r.status !== 200) { b.disabled = false; alertKarte(karte, fehlerText(r, 'Erledigen fehlgeschlagen')); return; }
    await ladeVerwaltung();
  });
  $('#eintraege-tabelle').addEventListener('click', (e) => {
    const b = e.target.closest('[data-bearbeiten]');
    if (b) eintragDialog(S.verw.eintraege.find((x) => x.id === b.dataset.bearbeiten));
  });
  $('#antraege-liste').addEventListener('click', async (e) => {
    const karte = e.target.closest('[data-id]');
    if (!karte) return;
    const a = S.offen.find((x) => x.id === karte.dataset.id);
    if (!a) return;
    if (e.target.closest('[data-genehmigen]')) {
      e.target.disabled = true;
      const r = await api('hr_entscheiden', { id: a.id, entscheidung: 'genehmigt' });
      if (r.status !== 200) { e.target.disabled = false; alertKarte(karte, fehlerText(r, 'Genehmigen fehlgeschlagen')); return; }
      await ladeAntraege();
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
    if (S.tab === 'planung') { await ladePlanung(); meldung($('#jp-meldung'), 'Antrag abgelehnt – der Mitarbeiter sieht den Grund.', 'ok'); }
    await ladeAntraege();
  });

  /* ---------- Abwesenheit eintragen / ändern ---------- */
  function eintragDialog(e) {
    // Personaldaten fehlen (z. B. Verbindung abgebrochen): Hinweis statt Skriptfehler
    if (!S.verw) { meldung($('#kal-meldung'), 'Personaldaten nicht verfügbar. Bitte die Seite neu laden.'); return; }
    meldung($('#kal-meldung'), '');
    const d = $('#dlg-eintrag');
    d.dataset.id = e.id || '';
    $('#dlg-eintrag-titel').textContent = e.id ? 'Abwesenheit ändern' : 'Abwesenheit eintragen';
    $('#eintrag-person').innerHTML = '<option value="">– bitte wählen –</option>' + S.verw.personen.filter((p) => (p.aktiv || p.id === e.person) && !(S.start && S.start.ich && p.id === S.start.ich.id))
      .map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    $('#eintrag-person').value = e.person || '';
    $('#eintrag-art').value = e.art || 'U';
    d.dataset.artVorher = e.id ? (e.art || '') : '';
    $('#eintrag-mail').checked = true; mailFeld();
    $('#eintrag-von').value = e.von || ''; $('#eintrag-bis').value = e.bis || '';
    $('#eintrag-notiz').value = e.notiz || '';
    $('#eintrag-storno').hidden = !e.id;
    meldung($('#eintrag-meldung'), '');
    d.showModal();
  }
  // Unentschuldigt (F): Haken „E-Mail an den Mitarbeiter“ (Standard an); beim Ändern eines F-Eintrags keine neue Mail
  function mailFeld() {
    const f = $('#eintrag-art').value === 'F', schon = $('#dlg-eintrag').dataset.artVorher === 'F';
    $('#eintrag-mail-feld').hidden = !f || schon;
  }
  $('#eintrag-art').addEventListener('change', mailFeld);
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
    if (b.art === 'F') b.mail = $('#eintrag-mail').checked;
    const r = await api('hr_eintrag_save', b);
    if (r.status !== 200) { meldung($('#eintrag-meldung'), fehlerText(r, 'Speichern fehlgeschlagen')); return; }
    await nachEintrag();
    meldung($('#eintraege-meldung'), r.data.hinweis || '', 'warn');   // z. B. Gleittag über das Gleittage-Konto hinaus
    // Unentschuldigt: Ergebnis der E-Mail an den Mitarbeiter (gesendet, keine Adresse, Versandfehler) dort, wo der Dialog geöffnet wurde
    const mm = r.data.mail;
    if (mm) meldung($(S.tab === 'kalender' ? '#kal-meldung' : '#eintraege-meldung'), mm.gesendet ? `Eingetragen – E-Mail mit der Bitte um Erklärung an ${mm.an} gesendet${mm.test ? ' (Testmodus)' : ''}.`
      : `Eingetragen – keine E-Mail gesendet: ${mm.grund}`, mm.gesendet ? 'ok' : 'warn');
  });
  $('#eintrag-storno').addEventListener('click', async () => {
    const r = await api('hr_eintrag_save', { id: $('#dlg-eintrag').dataset.id, stornieren: true });
    if (r.status !== 200) { meldung($('#eintrag-meldung'), fehlerText(r, 'Stornieren fehlgeschlagen')); return; }
    nachEintrag();
  });

  /* ---------- Urlaubsübersicht (hr.uebersicht oder Personalstelle): nur Summen ---------- */
  async function ladeUebersicht() {
    $('#ueb-titel').textContent = `Urlaubsübersicht ${S.ujahr}`;
    const r = await api('hr_uebersicht', null, '&jahr=' + S.ujahr);
    if (r.status !== 200) { $('#ueb-tabelle').innerHTML = `<tbody><tr><td class="gedaempft">${esc(fehlerText(r, 'Übersicht nicht verfügbar'))}</td></tr></tbody>`; return; }
    S.ueb = r.data;
    const sel = $('#ueb-abteilung'), alt = sel.value;
    const abt = [...new Set(r.data.zeilen.map((z) => z.abteilung))].sort((a, b) => a.localeCompare(b, 'de'));
    sel.innerHTML = '<option value="">alle</option>' + abt.map((a) => `<option value="${esc(a)}">${esc(a || 'Ohne Abteilung')}</option>`).join('');
    sel.value = abt.includes(alt) ? alt : '';
    zeigeUebersicht();
  }
  // Rest zuerst: die wichtigste Zahl ist auf dem Handy ohne Scrollen sichtbar
  const SP = [['rest', 'Rest'], ['anspruch', 'Anspruch'], ['uebertrag', 'Übertrag'], ['genommen', 'Genommen'], ['geplant', 'Geplant'], ['beantragt', 'Beantragt'], ['krank', 'Krank'], ['unentschuldigt', 'Unentschuldigt'], ['gleittage', 'Gleittage'], ['gleitRest', 'Gleittage-Rest']];
  function zeigeUebersicht() {
    const f = $('#ueb-abteilung').value;
    const zeilen = S.ueb.zeilen.filter((z) => !f || z.abteilung === f);
    const zelle = (z, k) => {
      const v = z[k];
      if (k === 'uebertrag' && (z.verfallen > 0 || z.verfaellt > 0)) {
        const t = z.verfallen > 0 ? `${tageText(z.verfallen)} verfallen` : `${tageText(z.verfaellt)} verfallen nach dem ${(S.ueb.uebertragBis || '03-31').split('-').reverse().join('.')}.`;
        return `<td class="zahl" title="${esc(t)}">${esc(zahl(v))}<small class="gedaempft"> (${esc(z.verfallen > 0 ? '−' + zahl(z.verfallen) : zahl(z.verfaellt) + '!')})</small></td>`;
      }
      if (k === 'gleitRest') {
        const t = v === null || v === undefined ? '<span class="gedaempft">—</span>' : `<span class="${v < 0 ? 'minus' : ''}">${esc(zahl(v))}</span>`;
        return `<td class="zahl gleit">${S.start && S.start.verwalten && !(S.start.ich && S.start.ich.id === z.id) ? `<button type="button" class="hr-gleit-zelle" data-gleit="${esc(z.id)}" aria-label="Gleittage von ${esc(z.name)}">${t}</button>` : t}</td>`;
      }
      return `<td class="zahl${k === 'rest' ? ' rest' + (v < 0 ? ' minus' : '') : ''}">${v ? esc(zahl(v)) : '<span class="gedaempft">0</span>'}</td>`;
    };
    let html = `<thead><tr><th scope="col">Mitarbeiter</th>${SP.map(([, t]) => `<th scope="col" class="zahl">${t}</th>`).join('')}</tr></thead><tbody>`;
    let abt = null;
    for (const z of zeilen) {
      if (z.abteilung !== abt) { abt = z.abteilung; html += abtZeile(abt, zeilen.filter((x) => x.abteilung === abt).length, SP.length + 1); }
      html += `<tr><th scope="row" class="name">${esc(z.name)}</th>${SP.map(([k]) => zelle(z, k)).join('')}</tr>`;
    }
    if (!zeilen.length) html += `<tr><td colspan="${SP.length + 1}" class="gedaempft">Keine Mitarbeiter im Urlaubsplan.</td></tr>`;
    html += '</tbody>';
    if (zeilen.length > 1) {
      const sum = (k) => zeilen.reduce((a, z) => a + Number(z[k] || 0), 0);
      html += `<tfoot><tr><th scope="row">Summe (${zeilen.length})</th>${SP.map(([k]) => `<td class="zahl">${k === 'gleitRest' && !zeilen.some((z) => z.gleitRest !== null) ? '—' : esc(zahl(sum(k)))}</td>`).join('')}</tr></tfoot>`;
    }
    $('#ueb-tabelle').innerHTML = html;
  }
  $('#ueb-abteilung').addEventListener('change', zeigeUebersicht);

  /* ---------- Gleittage gewähren (Personalstelle) ----------
     Daten der Personen (Konto, Gewährungen) aus hr_verwaltung des Übersichtsjahres; der Server prüft Recht und Vier-Augen-Prinzip. */
  async function gleitOeffnen(person) {
    const dlg = $('#dlg-gleit');
    meldung($('#gleit-meldung'), '');
    $('#gleit-konto').innerHTML = ''; $('#gleit-liste').innerHTML = '';
    if (!dlg.open) dlg.showModal();
    const r = await api('hr_verwaltung', null, '&jahr=' + S.ujahr);
    if (r.status !== 200) { meldung($('#gleit-meldung'), fehlerText(r, 'Mitarbeiter nicht verfügbar')); return; }
    const ich = S.start && S.start.ich ? S.start.ich.id : '';
    S.gleit = { jahr: r.data.jahr, personen: r.data.personen.filter((p) => p.aktiv && !p.altbestand && p.id !== ich) };
    const sel = $('#gleit-person');
    sel.innerHTML = '<option value="">– bitte wählen –</option>' + S.gleit.personen.map((p) => `<option value="${esc(p.id)}">${esc(p.name)}</option>`).join('');
    sel.value = person && S.gleit.personen.some((p) => p.id === person) ? person : '';
    $('#gleit-tage').value = '1'; $('#gleit-grund').value = '';
    gleitZeigen();
    (sel.value ? $('#gleit-tage') : sel).focus();
  }
  function gleitZeigen() {
    const p = S.gleit && S.gleit.personen.find((x) => x.id === $('#gleit-person').value);
    $('#gleit-speichern').disabled = !p;
    if (!p) { $('#gleit-konto').innerHTML = ''; $('#gleit-liste').innerHTML = '<li class="leer">Bitte einen Mitarbeiter wählen.</li>'; return; }
    const g = p.gleitKonto;
    $('#gleit-konto').innerHTML = g.aktiv
      ? wert(`Rest ${g.jahr}`, g.rest, 'haupt' + (g.rest < 0 ? ' minus' : '')) + wert('Aus dem Vorjahr', g.uebertrag) + wert('Gewährt', g.gewaehrt) + wert('Genommen', g.genommen + g.geplant, '', g.geplant ? `davon ${zahl(g.geplant)} geplant` : '')
      : '<p class="hr-klein">Noch keine Gleittage gewährt – das Konto beginnt mit der ersten Gewährung.</p>';
    const l = p.gleittage || [];
    $('#gleit-liste').innerHTML = l.length ? l.map((x) => `<li class="${x.storniert ? 'storniert' : ''}"><b>${esc(vorzeichen(x.tage))}</b><span>am ${esc(de(x.am))} · ${esc(x.von)}${x.grund ? ` – ${esc(x.grund)}` : ''}${x.storniert ? ` · storniert von ${esc(x.storniert.by)}` : ''}</span>
      ${x.storniert ? '' : `<button type="button" class="btn" data-gleit-storno="${esc(x.id)}">Stornieren</button>`}</li>`).join('') : '<li class="leer">Noch keine Gewährung.</li>';
  }
  async function gleitSpeichern(body) {
    const r = await api('hr_gleittage_save', { ...body, person: $('#gleit-person').value, jahr: S.gleit.jahr });
    if (r.status !== 200) { meldung($('#gleit-meldung'), fehlerText(r, 'Speichern fehlgeschlagen')); return false; }
    const p = S.gleit.personen.find((x) => x.id === r.data.person);
    if (p) { p.gleitKonto = r.data.gleitKonto; p.gleittage = r.data.gleittage; }
    gleitZeigen();
    if (S.ueb) ladeUebersicht();
    return true;
  }
  $('#ueb-gleit').addEventListener('click', () => gleitOeffnen(''));
  $('#gleit-person').addEventListener('change', () => { meldung($('#gleit-meldung'), ''); gleitZeigen(); });
  $('#gleit-form').addEventListener('submit', async (e) => {
    e.preventDefault();
    const tage = Number($('#gleit-tage').value), grund = $('#gleit-grund').value.trim();
    if (!tage || Math.round(tage * 2) !== tage * 2) { meldung($('#gleit-meldung'), 'Bitte die Anzahl in ganzen oder halben Tagen angeben.'); return; }
    if (tage < 0 && !grund) { meldung($('#gleit-meldung'), 'Bitte bei einer Korrektur einen Grund angeben.'); return; }
    $('#gleit-speichern').disabled = true;
    const ok = await gleitSpeichern({ tage, grund });
    $('#gleit-speichern').disabled = false;
    if (ok) { $('#gleit-grund').value = ''; meldung($('#gleit-meldung'), `${tageText(Math.abs(tage))} ${tage > 0 ? 'gewährt' : 'abgezogen'}.`, 'ok'); }
  });
  $('#gleit-liste').addEventListener('click', async (e) => {
    const b = e.target.closest('[data-gleit-storno]');
    if (!b) return;
    b.disabled = true;
    if (await gleitSpeichern({ id: b.dataset.gleitStorno, stornieren: true })) meldung($('#gleit-meldung'), 'Gewährung storniert.', 'ok');
    else b.disabled = false;
  });
  $('#ueb-tabelle').addEventListener('click', (e) => { const b = e.target.closest('[data-gleit]'); if (b) gleitOeffnen(b.dataset.gleit); });
  $('#tab-uebersicht').addEventListener('click', (e) => {
    const b = e.target.closest('[data-ujahr]');
    if (!b) return;
    S.ujahr += Number(b.dataset.ujahr);
    ladeUebersicht();
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

  /* ---------- Jahresplanung (nur Personalstelle; gesammelt genehmigen zusätzlich mit „Urlaub genehmigen“) ----------
     Server: hr_planung (Zusammenfassung), hr_entscheiden (einzeln), hr_planung_freigeben (konfliktfreie gesammelt),
     hr_planung_erinnern, hr_planung_abschluss, hr_planung_uebersicht_senden. Knöpfe nur als Anzeige – Rechte prüft der Server. */
  const KONFLIKT_ART = { vertretung: 'Vertretung', abteilung: 'Abteilung', sperre: 'Urlaubssperre', rest: 'Resturlaub' };
  async function ladePlanung() {
    const r = await api('hr_planung', null, S.pjahr ? '&jahr=' + S.pjahr : '');
    if (r.status !== 200) {
      S.jp = null; S.pjahr = null;   // nach einem Fehler wieder mit dem Planungsjahr des Servers beginnen
      $('#jp-titel').textContent = 'Jahresplanung';
      for (const id of ['#jp-info', '#jp-zahlen', '#jp-aktionen', '#jp-legende', '#jp-zeitleiste', '#jp-filter', '#jp-antraege']) $(id).innerHTML = '';
      meldung($('#jp-meldung'), fehlerText(r, 'Jahresplanung nicht verfügbar'));
      return;
    }
    S.jp = r.data; S.pjahr = r.data.jahr;
    zeigePlanung();
  }
  const jpFilter = { alle: () => true, konflikt: (a) => a.konflikte.length > 0, frei: (a) => a.frei, genehmigt: (a) => a.status === 'genehmigt' };
  function zeigePlanung() {
    const d = S.jp, z = d.zahlen, j = d.jahr;
    $('#jp-titel').textContent = `Jahresplanung ${j}`;
    $('#jp-info').textContent = [`Stichtag ${de(d.stichtag)}`, `Ziel: ${d.prozent} % des Anspruchs`, d.vertretungPflicht ? 'Vertretung Pflicht' : 'Vertretung freiwillig',
      d.abschluss ? `abgeschlossen am ${window.STAFL_FORMAT.datum(d.abschluss.t)}${d.abschluss.by ? ' von ' + d.abschluss.by : ''}` : `Hinweis für Mitarbeiter ab ${de(d.start)}`].join(' · ');
    const kachel = (titel, wert, cls = '', zusatz = '') => `<div class="hr-wert hr-glas ${cls}"><span>${esc(titel)}</span><b>${esc(wert)}</b>${zusatz ? `<small>${esc(zusatz)}</small>` : ''}</div>`;
    $('#jp-zahlen').innerHTML = kachel('Ziel erreicht', `${z.erreicht} / ${z.personen}`, 'haupt', z.personen - z.erreicht ? `${z.personen - z.erreicht} noch offen` : 'alle Mitarbeiter')
      + kachel('Offene Anträge', String(z.offen)) + kachel('Konfliktfrei', String(z.frei), 'ok') + kachel('Mit Konflikt', String(z.konflikte), z.konflikte ? 'konflikt' : '');
    const frei = d.antraege.filter((a) => a.frei).length;
    const k = [];
    if (d.verwalten && !d.abschluss) k.push(`<button type="button" class="btn" data-jp="erinnern"${z.erinnern ? '' : ' disabled'}>Erinnerung senden (${z.erinnern})</button>`);
    if (d.genehmigen) k.push(`<button type="button" class="btn" data-jp="freigeben"${frei ? '' : ' disabled'}>Konfliktfreie genehmigen (${frei})</button>`);
    if (d.verwalten && !d.abschluss) k.push('<button type="button" class="btn primary" data-jp="abschliessen">Planung abschließen und Jahresübersicht senden</button>');
    if (d.verwalten && d.abschluss) k.push('<button type="button" class="btn" data-jp="senden">Jahresübersicht erneut senden</button>', '<button type="button" class="btn" data-jp="oeffnen">Wieder öffnen</button>');
    $('#jp-aktionen').innerHTML = k.join('');
    zeigeZeitleiste();
    zeigePlanungListe();
  }
  /* Zeitleiste: je Mitarbeiter (nach Abteilung) eine Jahresleiste; Balken = Anträge, Sperren und Monate als Hintergrund */
  function zeigeZeitleiste() {
    const d = S.jp, j = d.jahr;
    const tag0 = Date.UTC(j, 0, 1), tage = (Date.UTC(j + 1, 0, 1) - tag0) / 86400000;
    const pos = (s) => Math.max(0, Math.min(tage, (Date.parse(s + 'T00:00:00Z') - tag0) / 86400000));
    const lage = (von, bis) => { const a = pos(von), b = pos(plusTage(bis, 1)); return `left:${(a / tage * 100).toFixed(3)}%;width:${(Math.max(0, b - a) / tage * 100).toFixed(3)}%`; };
    const raster = MONATE.map((m, i) => { const s = `${j}-${String(i + 1).padStart(2, '0')}-01`; return `<i style="left:${(pos(s) / tage * 100).toFixed(3)}%"></i>`; }).join('')
      + d.sperren.map((sp) => `<b class="sperre" style="${lage(sp.von < `${j}-01-01` ? `${j}-01-01` : sp.von, sp.bis > `${j}-12-31` ? `${j}-12-31` : sp.bis)}" title="${esc(`Urlaubssperre ${zeitraum(sp.von, sp.bis)}${sp.text ? ' – ' + sp.text : ''}`)}"></b>`).join('')
      + (d.heute.startsWith(String(j)) ? `<b class="heute" style="left:${(pos(d.heute) / tage * 100).toFixed(3)}%" title="Heute"></b>` : '');
    const kopf = `<div class="hr-jp-zeile hr-jp-kopf"><div class="hr-jp-name">Mitarbeiter</div><div class="hr-jp-spur">${MONATE.map((m, i) => {
      const s = `${j}-${String(i + 1).padStart(2, '0')}-01`, e = `${j}-${String(i + 1).padStart(2, '0')}-${String(new Date(Date.UTC(j, i + 1, 0)).getUTCDate()).padStart(2, '0')}`;
      return `<span style="${lage(s, e)}">${m.slice(0, 3)}</span>`; }).join('')}</div></div>`;
    let html = '', abt = null;
    for (const p of d.personen) {
      if (p.abteilung !== abt) { abt = p.abteilung; html += `<div class="hr-jp-abt"><span>${esc(abt || 'Ohne Abteilung')}<small>${d.personen.filter((x) => x.abteilung === abt).length}</small></span></div>`; }
      const balken = d.antraege.filter((a) => a.person === p.id).map((a) => {
        const titel = [`${a.name}: ${zeitraum(a.von, a.bis)}`, tageText(a.tage), STATUS[a.status] || a.status, `Vertretung: ${a.vertretung || '–'}`,
          ...a.konflikte.map((x) => x.text)].join(' · ');
        return `<button type="button" class="hr-jp-balken ${esc(a.status)}${a.konflikte.length ? ' konflikt' : ''}" style="${lage(a.von, a.bis)}" data-jp-antrag="${esc(a.id)}" title="${esc(titel)}" aria-label="${esc(titel)}"></button>`;
      }).join('');
      const ant = p.anspruch > 0 ? Math.min(100, p.geplant / p.anspruch * 100) : 0;
      // ohne Anspruch im Jahr (noch nicht gepflegt): kein Ziel, nur ein Hinweis statt „0/0“
      const stand = p.anspruch > 0
        ? `<span class="mini"><i style="width:${ant.toFixed(1)}%"></i><b style="left:${Math.min(100, p.ziel / p.anspruch * 100).toFixed(1)}%"></b></span><small>${esc(zahl(p.geplant))}/${esc(zahl(p.ziel))}</small>`
        : '<small class="ohne">kein Anspruch</small>';
      html += `<div class="hr-jp-zeile${p.erreicht && p.anspruch > 0 ? ' erreicht' : ''}" data-jp-person="${esc(p.id)}">
        <div class="hr-jp-name" title="${esc(p.anspruch > 0 ? `${p.name}: ${zahl(p.geplant)} von ${zahl(p.ziel)} Tagen (Ziel), Anspruch ${zahl(p.anspruch)}` : `${p.name}: kein Urlaubsanspruch für ${j} eingetragen`)}"><span class="nm">${esc(p.name)}</span>
          <span class="stand">${stand}</span></div>
        <div class="hr-jp-spur">${balken}</div></div>`;
    }
    if (!d.personen.length) html = '<p class="hr-klein hr-jp-leer">Keine Mitarbeiter im Urlaubsplan.</p>';
    $('#jp-zeitleiste').innerHTML = d.personen.length ? `<div class="hr-jp-zl">${kopf}<div class="hr-jp-raster" aria-hidden="true">${raster}</div>${html}</div>` : html;
    const f = (cls, t) => `<span><i class="${cls}"></i>${esc(t)}</span>`;
    $('#jp-legende').innerHTML = f('hr-jp-l genehmigt', 'genehmigt') + f('hr-jp-l beantragt', 'beantragt') + f('hr-jp-l konflikt', 'mit Konflikt') + f('hr-jp-l sperre', 'Urlaubssperre');
  }
  function zeigePlanungListe() {
    const d = S.jp, darf = d.genehmigen;
    if (!jpFilter[S.jpFilter]) S.jpFilter = 'alle';
    const namen = { alle: 'Alle', konflikt: 'Mit Konflikt', frei: 'Konfliktfrei', genehmigt: 'Genehmigt' };
    $('#jp-filter').innerHTML = Object.keys(namen).map((k) => `<button type="button" class="hr-chip" data-jp-filter="${k}" aria-pressed="${S.jpFilter === k}">${namen[k]} <small>${d.antraege.filter(jpFilter[k]).length}</small></button>`).join('');
    const l = d.antraege.filter(jpFilter[S.jpFilter]);
    $('#jp-antraege').innerHTML = l.length ? l.map((a) => `<li class="hr-jp-antrag${a.konflikte.length ? ' konflikt' : ''}" id="jp-a-${esc(a.id)}" data-id="${esc(a.id)}">
        <div class="kopf"><b>${esc(a.name)}</b><span class="hr-pille ${esc(a.status)}">${esc(STATUS[a.status] || a.status)}</span>${a.abteilung ? `<span class="gedaempft">${esc(a.abteilung)}</span>` : ''}</div>
        <div class="zeit"><span class="zeitraum">${esc(zeitraum(a.von, a.bis))}</span><span>${esc(tageText(a.tage))}</span><span>Vertretung: ${a.vertretung ? esc(a.vertretung) : '<em>keine</em>'}</span></div>
        ${a.notiz ? `<p class="notiz">${esc(a.notiz)}</p>` : ''}
        ${a.konflikte.length ? `<ul class="hr-jp-konflikte">${a.konflikte.map((x) => `<li class="${esc(x.art)}"><span>${esc(KONFLIKT_ART[x.art] || x.art)}</span>${esc(x.text)}</li>`).join('')}</ul>`
          : `<p class="hr-jp-ok">Kein Konflikt</p>`}
        ${a.status === 'beantragt' ? (darf && !a.eigen ? '<div class="knoepfe"><button type="button" class="btn primary" data-jp-genehmigen>Genehmigen</button><button type="button" class="btn gefahr" data-jp-ablehnen>Ablehnen</button></div>'
          : `<p class="hr-jp-eigen">${a.eigen ? 'Ihr eigener Antrag – darüber entscheidet eine andere Person.' : 'Die Entscheidung trifft eine Person mit dem Recht „Urlaub genehmigen“.'}</p>`) : ''}
      </li>`).join('') : `<li class="hr-jp-leer">${d.antraege.length ? 'Keine Anträge in dieser Auswahl.' : `Noch keine Urlaubsanträge für ${d.jahr}.`}</li>`;
  }
  $('#tab-planung').addEventListener('click', async (e) => {
    const jb = e.target.closest('[data-pjahr]');
    if (jb) { S.pjahr = (S.pjahr || new Date().getFullYear() + 1) + Number(jb.dataset.pjahr); meldung($('#jp-meldung'), ''); ladePlanung(); return; }
    const fb = e.target.closest('[data-jp-filter]');
    if (fb) { S.jpFilter = fb.dataset.jpFilter; zeigePlanungListe(); return; }
    const balken = e.target.closest('[data-jp-antrag]');
    if (balken) {
      let li = document.getElementById('jp-a-' + balken.dataset.jpAntrag);
      if (!li) { S.jpFilter = 'alle'; zeigePlanungListe(); li = document.getElementById('jp-a-' + balken.dataset.jpAntrag); }
      if (li) {
        li.scrollIntoView({ behavior: 'smooth', block: 'center' });
        li.classList.remove('hervor'); void li.offsetWidth; li.classList.add('hervor');
      }
      return;
    }
    const karte = e.target.closest('.hr-jp-antrag');
    if (karte && S.jp) {
      const a = S.jp.antraege.find((x) => x.id === karte.dataset.id);
      if (!a) return;
      if (e.target.closest('[data-jp-genehmigen]')) {
        e.target.disabled = true;
        const r = await api('hr_entscheiden', { id: a.id, entscheidung: 'genehmigt' });
        if (r.status !== 200) { e.target.disabled = false; meldung($('#jp-meldung'), fehlerText(r, 'Genehmigen fehlgeschlagen')); return; }
        await ladePlanung();
        meldung($('#jp-meldung'), `Genehmigt: ${a.name}, ${zeitraum(a.von, a.bis)}.`, 'ok');
        ladeAntraege();
        return;
      }
      if (e.target.closest('[data-jp-ablehnen]')) {
        $('#ablehnen-text').textContent = `${a.name}: ${zeitraum(a.von, a.bis)} (${tageText(a.tage)})`;
        $('#ablehnen-grund').value = ''; meldung($('#ablehnen-meldung'), '');
        $('#dlg-ablehnen').dataset.id = a.id;
        $('#dlg-ablehnen').showModal();
      }
      return;
    }
    const ak = e.target.closest('[data-jp]');
    if (ak && S.jp) await planungAktion(ak.dataset.jp, ak);
  });
  async function planungAktion(was, knopf) {
    const d = S.jp, j = d.jahr, m = $('#jp-meldung');
    meldung(m, '');   // Meldung der vorigen Aktion gilt nicht mehr
    const test = (r) => (r && r.test ? ' (Testmodus: an die Testadresse)' : '');
    const gesendet = (r) => (r ? `${r.gesendet} ${r.gesendet === 1 ? 'E-Mail' : 'E-Mails'} gesendet${r.fehler ? `, ${r.fehler} nicht zugestellt` : ''}${r.ohneAdresse ? `, ${r.ohneAdresse} ohne E-Mail-Adresse` : ''}${test(r)}` : 'keine E-Mail gesendet');
    let r;
    if (was === 'erinnern') {
      if (!(await frage(`Erinnerung zur Urlaubsplanung ${j} senden?`, `${d.zahlen.erinnern} Mitarbeiter mit E-Mail-Adresse, die ihr Ziel (${d.prozent} % bis ${de(d.stichtag)}) noch nicht erreicht haben, bekommen eine E-Mail mit ihrem Stand.`, 'Erinnerung senden'))) return;
      knopf.disabled = true;
      r = await api('hr_planung_erinnern', { jahr: j });
      if (r.status !== 200) { knopf.disabled = false; meldung(m, fehlerText(r, 'Erinnerung nicht gesendet')); return; }
      await ladePlanung(); meldung(m, `Erinnerung: ${gesendet(r.data.ergebnis)}.`, 'ok');
    } else if (was === 'freigeben') {
      const ids = d.antraege.filter((a) => a.frei).map((a) => a.id);
      if (!ids.length) return;
      if (!(await frage(`${ids.length} konfliktfreie ${ids.length === 1 ? 'Antrag' : 'Anträge'} genehmigen?`, 'Genehmigt werden nur Anträge ohne Konflikt (Vertretung da, keine Überschneidung in der Abteilung, keine Urlaubssperre, im Resturlaub) – der Server prüft jeden Antrag noch einmal. Eigene Anträge bleiben offen.', 'Genehmigen'))) return;
      knopf.disabled = true;
      r = await api('hr_planung_freigeben', { jahr: j, ids });
      if (r.status !== 200) { knopf.disabled = false; meldung(m, fehlerText(r, 'Genehmigen fehlgeschlagen')); return; }
      await ladePlanung();
      const weg = r.data.uebersprungen || [];
      meldung(m, `${r.data.genehmigt.length} ${r.data.genehmigt.length === 1 ? 'Antrag' : 'Anträge'} genehmigt${weg.length ? `, ${weg.length} übersprungen (${[...new Set(weg.map((x) => x.grund))].join(', ')})` : ''}.`, weg.length ? 'warn' : 'ok');
      ladeAntraege();
    } else if (was === 'abschliessen') {
      const testHinweis = d.testmodus ? ' Achtung, Testmodus ist an: die E-Mails gehen nur an die Testadresse – der Abschluss gilt aber für alle Mitarbeiter.' : '';
      if (!(await frage(`Planung ${j} abschließen?`, `Jeder Mitarbeiter mit E-Mail-Adresse bekommt seine Jahresübersicht ${j} (Urlaubszeiträume mit Vertretung, Konto, Jahr auf einen Blick). Der Planungshinweis in der Urlaubsverwaltung verschwindet. Offene Anträge bleiben offen.${testHinweis}`, 'Abschließen und senden'))) return;
      knopf.disabled = true;
      r = await api('hr_planung_abschluss', { jahr: j, abgeschlossen: true });
      if (r.status !== 200) { knopf.disabled = false; meldung(m, fehlerText(r, 'Abschließen fehlgeschlagen')); return; }
      await ladePlanung(); meldung(m, `Planung ${j} abgeschlossen – Jahresübersicht: ${gesendet(r.data.ergebnis)}.`, r.data.ergebnis && r.data.ergebnis.fehlerText && r.data.ergebnis.fehlerText.length && !r.data.ergebnis.gesendet ? 'warn' : 'ok');
    } else if (was === 'oeffnen') {
      if (!(await frage(`Planung ${j} wieder öffnen?`, 'Die Mitarbeiter sehen den Planungshinweis wieder (in der Planungsphase). Bereits gesendete Jahresübersichten bleiben, wie sie sind.', 'Wieder öffnen'))) return;
      knopf.disabled = true;
      r = await api('hr_planung_abschluss', { jahr: j, abgeschlossen: false });
      if (r.status !== 200) { knopf.disabled = false; meldung(m, fehlerText(r, 'Öffnen fehlgeschlagen')); return; }
      await ladePlanung(); meldung(m, `Planung ${j} wieder geöffnet.`, 'ok');
    } else if (was === 'senden') {
      if (!(await frage(`Jahresübersicht ${j} erneut senden?`, `Jeder Mitarbeiter mit E-Mail-Adresse bekommt seine Jahresübersicht ${j} mit dem aktuellen Stand.`, 'Senden'))) return;
      knopf.disabled = true;
      r = await api('hr_planung_uebersicht_senden', { jahr: j });
      knopf.disabled = false;
      if (r.status !== 200) { meldung(m, fehlerText(r, 'Senden fehlgeschlagen')); return; }
      meldung(m, `Jahresübersicht: ${gesendet(r.data.ergebnis)}.`, 'ok');
    }
  }

  /* ---------- Urlaubsregeln (Text der Personalstelle, Verwaltung → Urlaub) ----------
     Absätze durch Leerzeilen; eine Zeile „1. Überschrift“ am Anfang eines Absatzes wird zur Überschrift mit der Nummer
     als kleinem Kreis (kompakt, Inhaber 03.11.2026). Nur Text (esc). */
  const REGELN_ZU = 'hr-regeln-zu';
  let regelnBereit = false;   // erst nach dem ersten Anzeigen merken (das „toggle“ beim Laden der Seite zählt nicht)
  function zeigeRegeln(text) {
    const t = String(text || '').trim(), box = $('#regeln');
    box.hidden = !t; $('#antrag-regeln').hidden = !t;
    if (!t) return;
    $('#regeln-text').innerHTML = t.split(/\n\s*\n/).map((abs) => {
      const z = abs.split('\n'), m = /^(\d+)\.\s+(\S.*)$/.exec(z[0]);
      if (m) z.shift();
      const kopf = m ? `<h3><span class="hr-regel-nr">${esc(m[1])}</span> ${esc(m[2].trim())}</h3>` : '';
      return `<div class="hr-regel${m ? ' mit-nr' : ''}">${kopf}${z.length ? `<p>${z.map(esc).join('<br>')}</p>` : ''}</div>`;
    }).join('');
    if (!regelnBereit) { try { if (localStorage.getItem(REGELN_ZU) === '1') box.open = false; } catch (e) { /* ohne Speicher: offen */ } }
    regelnBereit = true;
  }
  $('#regeln').addEventListener('toggle', () => { if (!regelnBereit) return; try { localStorage.setItem(REGELN_ZU, $('#regeln').open ? '0' : '1'); } catch (e) { /* egal */ } });
  $('#antrag-regeln').addEventListener('click', (e) => {
    if (!e.target.closest('[data-regeln-zeigen]')) return;
    e.preventDefault();
    $('#regeln').open = true; $('#regeln').scrollIntoView({ behavior: 'smooth', block: 'start' });
  });

  /* ---------- Hinweis „Resturlaub verfällt bald“ ----------
     Ab 8 Wochen vor dem Verfallstag, solange Übertrag verfallen würde (Konto „verfaellt“; ohne Verfall der Person nie),
     höchstens einmal am Tag je Browser. Nur im laufenden Jahr. */
  const VERFALL_VORLAUF = 56;   // Tage
  function verfallHinweis() {
    const d = S.start, k = d && d.konto;
    if (!k || !(k.verfaellt > 0) || !k.frist || !d.heute || String(d.jahr) !== d.heute.slice(0, 4)) return;
    const tage = Math.round((Date.parse(k.frist + 'T00:00:00Z') - Date.parse(d.heute + 'T00:00:00Z')) / 86400000);
    if (tage < 0 || tage > VERFALL_VORLAUF) return;
    const key = 'hr-verfall-' + d.heute;
    try { if (localStorage.getItem('hr-verfall-gesehen') === key) return; localStorage.setItem('hr-verfall-gesehen', key); } catch (e) { /* ohne Speicher: jedes Mal */ }
    $('#verfall-text').textContent = `${tageText(k.verfaellt)} Resturlaub aus dem Vorjahr ${k.verfaellt === 1 ? 'verfällt' : 'verfallen'} am ${de(k.frist)}, wenn Sie ${k.verfaellt === 1 ? 'ihn' : 'sie'} bis dahin nicht nehmen.`;
    $('#verfall-planen').hidden = d.antraege === false;
    $('#dlg-verfall').showModal();
  }
  $('#verfall-planen').addEventListener('click', () => {
    $('#dlg-verfall').close(); zeigeTab('mein');
    $('#antrag-von').focus(); $('#antrag').scrollIntoView({ behavior: 'smooth', block: 'center' });
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
    verfallHinweis();
  }
  themaKnopf();
  laden().catch(() => fehler('Keine Verbindung zum Server.'));
})();
