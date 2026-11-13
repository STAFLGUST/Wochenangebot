/* STAFL-Plattform · Modul Versand – Wochenangebot und Kundenangebote veröffentlichen und per E-Mail an Kunden senden
   (Auftrag des Inhabers 13.11.2026; Gestaltung „C2“, Variante A: zwei Schritte oben, Angebote zur Kontrolle, Verlauf).
   Daten: versand_start (Stand, nur Zahlen), versand_aenderungen (Liste im Fenster „Veröffentlichen“, nur mit Modulzugang
   Angebot), versand_veroeffentlichen (gespeicherter Entwurf, mit Revision – 409, wenn inzwischen jemand gespeichert hat),
   versand_empfaenger / versand_vorschau / versand_senden (Wochenangebot bzw. Sonderposten eines Angebots, in Teilen zu zehn),
   versand_verlauf (aus dem Protokoll, ohne Kundennamen).
   Bestätigung beim Senden wie überall: unter der zentralen Anmeldung erneute Anmeldung (reauth_required, Rücksprung hierher –
   die Auswahl bleibt in sessionStorage), sonst Passwort im Fenster (confirmation_required → reauth).
   Vorschau und Drucken eines Angebots öffnen die Angebotsseite des Eingabebereichs (Entwurf, ?vorschau=1 bzw. zusätzlich
   &drucken=liste – die Druckfassung des Angebots, assets/angebot-druck.js); nur mit Modulzugang Angebot.
   Fenster schließen nur über ×, „Abbrechen“ oder Escape (theme.js). Rechte prüft der Server bei jeder Aktion (GR-103);
   ausgeblendete oder gesperrte Knöpfe sind nur Anzeige. Kein Inline-Skript (CSP); fremde Texte nur maskiert. */
'use strict';
(() => {
  const API = '../../api/';
  const ECHT = /(^|\.)dashboard-stafl\.de$/.test(location.hostname);
  const ANGEBOT = ECHT ? 'https://angebot.dashboard-stafl.de/' : '../../';   // Eingabebereich und Angebotsseite (Vorschau, Drucken)
  const MERK = 'stafl-versand-senden';   // Auswahl über die erneute Anmeldung hinweg
  const TEIL = 10;                       // Kunden je Aufruf von versand_senden
  const $ = (s, el = document) => el.querySelector(s);
  const $$ = (s, el = document) => [...el.querySelectorAll(s)];
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (n) => `<svg class="r-i" aria-hidden="true"><use href="#i-${n}"/></svg>`;
  const plural = (n, ein, viele) => `${n} ${n === 1 ? ein : viele}`;
  const S = { csrf: '', d: null, toast: 0, aend: null, send: null, monate: 2 };

  /* ---------- Aufruf der API: wirft nie, liefert { status, data } ---------- */
  async function api(action, body, query = '') {
    let res;
    try {
      res = await fetch(API + '?action=' + action + query, {
        method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
        headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': S.csrf } : {}, body: body ? JSON.stringify(body) : undefined,
      });
    } catch { return { status: 0, data: {} }; }
    let data = null;
    try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
    return { status: res.status, data: data || {} };
  }
  const fehlerText = (r, fallback) => (r.data && r.data.error) || (r.status === 0 ? 'Keine Verbindung zum Server.' : `${fallback} (${r.status}).`);
  function toast(text, fehlerhaft = false) {
    const t = $('#vs-toast');
    t.textContent = text; t.className = 'vs-toast zeigen' + (fehlerhaft ? ' fehler' : '');
    clearTimeout(S.toast); S.toast = setTimeout(() => { t.className = 'vs-toast'; }, fehlerhaft ? 5000 : 2800);
  }
  function fehler(text) { $('#vs-login').hidden = true; $('#vs-app').hidden = true; $('#vs-err').hidden = false; $('#vs-err').textContent = text; }
  function zeigeAnmeldung() { $$('dialog[open]').forEach((d) => d.close()); $('#vs-login').hidden = false; $('#vs-app').hidden = true; }

  /* ---------- Formate ---------- */
  const TAGE = ['So', 'Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa'];
  const zwei = (n) => String(n).padStart(2, '0');
  /* „heute, 10:42 Uhr“ bzw. „Do 05.11.2026, 14:10 Uhr“ */
  function zeit(t) {
    const d = new Date(t);
    if (!t || isNaN(d)) return '';
    const uhr = `${zwei(d.getHours())}:${zwei(d.getMinutes())} Uhr`;
    return (d.toDateString() === new Date().toDateString() ? 'heute' : `${TAGE[d.getDay()]} ${zwei(d.getDate())}.${zwei(d.getMonth() + 1)}.${d.getFullYear()}`) + ', ' + uhr;
  }
  const tag = (t) => { const d = new Date(t); return !t || isNaN(d) ? '' : `${zwei(d.getDate())}.${zwei(d.getMonth() + 1)}.${d.getFullYear()}`; };
  const kw = (w) => (w && w.week ? `KW ${w.week}/${w.year}` : '');
  function wochenText(w) {   // „Angebotswoche Mo 16.11. – So 22.11.2026“
    if (!w || !w.woche) return '';
    const v = w.woche.von, b = w.woche.bis;
    return `Angebotswoche Mo ${v.slice(8, 10)}.${v.slice(5, 7)}. – So ${b.slice(8, 10)}.${b.slice(5, 7)}.${b.slice(0, 4)}`;
  }
  const ART_TEXT = { preis: 'Preisänderungen', neu: 'Neu', entfernt: 'Entfernt', bearbeitet: 'Bearbeitet', angebotspreis: 'Angebotspreise',
    sichtbar: 'Im Wochenangebot ein- oder ausgeblendet', empfehlung: 'Empfehlungen', werbung: 'Werbung', kopf: 'Kopfdaten', aufbau: 'Aufbau' };
  const ART_REIHE = ['kopf', 'preis', 'neu', 'entfernt', 'bearbeitet', 'angebotspreis', 'sichtbar', 'empfehlung', 'werbung', 'aufbau'];
  const ART_KURZ = { preis: ['Preis', 'Preise'], neu: ['neu', 'neu'], entfernt: ['entfernt', 'entfernt'], bearbeitet: ['bearbeitet', 'bearbeitet'], angebotspreis: ['Angebotspreis', 'Angebotspreise'],
    sichtbar: ['ein-/ausgeblendet', 'ein-/ausgeblendet'], empfehlung: ['Empfehlung', 'Empfehlungen'], werbung: ['Werbung', 'Werbung'], kopf: ['Kopfdaten', 'Kopfdaten'], aufbau: ['Aufbau', 'Aufbau'] };

  /* ---------- Darstellung ---------- */
  const dunkel = () => document.documentElement.getAttribute('data-theme') === 'dark'
    || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  function themaKnopf() {
    const d = dunkel(), b = $('#vs-theme');
    b.innerHTML = icon(d ? 'sun' : 'moon');
    b.setAttribute('aria-label', d ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }

  /* ---------- Seite ---------- */
  function schritt(o) {
    const fakten = o.fakten.filter((f) => f[1]).map(([k, v]) => `<dt>${esc(k)}</dt><dd>${v}</dd>`).join('');
    return `<article class="r-karte vs-schritt ${o.klasse}" id="${o.id}">
      <div class="vs-schritt-kopf"><span class="vs-nr">${o.klasse === 'erledigt' ? icon('haken') : o.nr}</span><h3>${esc(o.titel)}</h3>${o.marke ? `<span class="vs-marke ${o.marke[1]}">${esc(o.marke[0])}</span>` : ''}</div>
      <p class="vs-stand">${esc(o.stand)}<small>${o.klein}</small></p>
      ${fakten ? `<dl class="vs-fakten">${fakten}</dl>` : ''}
      ${(o.hinweise || []).map((h) => `<p class="vs-hinweis${h[1] ? ' neutral' : ''}">${icon('info')}<span>${h[0]}</span></p>`).join('')}
      <div class="vs-schritt-fuss">${o.fuss}</div></article>`;
  }
  function zeichnen() {
    const d = S.d, r = d.rechte, v = d.veroeffentlicht, e = d.entwurf, ae = d.aenderungen, n = ae.anzahl, vs = d.versand;
    const woche = e || v;
    $('#vs-unterzeile').textContent = woche ? `Wochenangebot ${kw(woche)} · ${wochenText(woche)}` : 'Noch kein Angebot angelegt';
    document.title = `STAFL-Plattform · Versand${woche ? ' · ' + kw(woche) : ''}`;

    /* Schritt 1: Veröffentlichen */
    const offen = !!e && (n > 0 || ae.erste);
    const online = v ? `${esc(kw(v))} · veröffentlicht ${esc(zeit(v.publishedAt))}<span id="vs-pub-von"></span>` : '';
    const nAng = d.angebote.length;
    const s1 = { id: 'vs-s1', nr: 1, titel: 'Veröffentlichen', hinweise: [], fakten: [] };
    if (!e) Object.assign(s1, { klasse: 'erledigt', marke: v ? ['aktuell', 'ok'] : null, stand: v ? `${kw(v)} ist online` : 'Noch nichts veröffentlicht',
      klein: v ? `veröffentlicht ${esc(zeit(v.publishedAt))}<span id="vs-pub-von"></span> · keine offenen Änderungen` : 'Es gibt noch keinen Entwurf. Das Angebot entsteht in „Angebot bearbeiten“.',
      fakten: [['Gilt für', v ? `alle ${plural(nAng, 'Angebot', 'Angebote')}` : '']] });
    else Object.assign(s1, { klasse: offen ? 'offen' : '', marke: offen ? ['offen', 'warn'] : ['keine Änderungen erkannt', ''],
      stand: ae.erste ? 'Noch nichts veröffentlicht' : n > 0 ? `${plural(n, 'Änderung', 'Änderungen')} nicht veröffentlicht` : 'Entwurf ohne erkennbare Änderungen',
      klein: `Entwurf ${esc(kw(e))}${ae.erste ? ` · ${plural(e.artikel, 'Artikel', 'Artikel')}` : ''} · zuletzt bearbeitet ${esc(zeit(e.savedAt))}${e.savedBy ? ' von ' + esc(e.savedBy) : ''}`,
      fakten: [['Online ist', online], ['Gilt für', `alle ${plural(nAng, 'Angebot', 'Angebote')} (Wochenangebot und Kundenangebote)`]] });
    if (d.anwesend.length) s1.hinweise.push([`Gerade im Angebot: <strong>${esc(d.anwesend.join(', '))}</strong>. Veröffentlicht wird der zuletzt gespeicherte Stand.`, true]);
    const darfPub = r.veroeffentlichen && !!e;
    s1.fuss = `<button class="vs-knopf${offen && r.veroeffentlichen ? ' primaer' : ''}" type="button" id="vs-pub"${darfPub ? '' : ' disabled'} title="${esc(!e ? 'Nichts zu veröffentlichen – es gibt keine offenen Änderungen' : !r.veroeffentlichen ? 'Dafür fehlt Ihnen das Recht „Angebot veröffentlichen“' : 'Änderungen prüfen und veröffentlichen')}">${icon('send')}Veröffentlichen${e && n > 0 && !ae.erste ? `<span class="vs-zahl">${n}</span>` : ''}</button>`
      + (!e ? '<span class="vs-leise vs-klein">Nichts zu veröffentlichen</span>' : !r.veroeffentlichen ? '<span class="vs-leise vs-klein">Ihnen fehlt das Recht zum Veröffentlichen</span>' : '')
      + (r.angebot ? `<a class="vs-link" href="${esc(ANGEBOT)}admin/">Im Angebot ansehen</a>` : '');

    /* Schritt 2: An Kunden senden */
    const sp = d.angebote.filter((a) => a.sonderposten > 0);
    const rest = vs.empfaenger - vs.gesendet;
    const s2 = { id: 'vs-s2', nr: 2, titel: 'An Kunden senden', hinweise: [], klasse: '', marke: null,
      fakten: [['Letzter Versand', vs.zuletzt ? `${esc(kw(vs.zuletzt))} · ${esc(zeit(vs.zuletzt.t))}` : ''],
        ['Sonderposten', sp.length > 2 ? `in ${sp.length} Angeboten – Versand je Angebot in der Liste unten` : sp.map((a) => `${plural(a.sonderposten, 'Artikel', 'Artikel')} im ${esc(a.name)}`).join(' · ')]] };
    if (!v) Object.assign(s2, { stand: 'Noch nichts zu senden', klein: 'Kunden bekommen das Wochenangebot, sobald es veröffentlicht ist.' });
    else if (!vs.empfaenger) Object.assign(s2, { stand: 'Keine Empfänger', klein: 'Kein Kunde hat E-Mail-Adresse, aktiven Zugang und ein freigeschaltetes Angebot.' });
    else if (!vs.gesendet) Object.assign(s2, { stand: `KW ${v.week} noch nicht versendet`, klein: `${plural(vs.empfaenger, 'Kunde bekommt', 'Kunden bekommen')} das Wochenangebot per E-Mail` });
    else if (rest > 0) Object.assign(s2, { stand: `KW ${v.week}: an ${vs.gesendet} von ${vs.empfaenger} Kunden gesendet`, klein: `${plural(rest, 'Kunde', 'Kunden')} noch offen` });
    else Object.assign(s2, { klasse: 'erledigt', marke: ['erledigt', 'ok'], stand: `KW ${v.week} an alle ${plural(vs.empfaenger, 'Kunden', 'Kunden')} gesendet`, klein: 'Erneut senden ist möglich – bereits beschickte Kunden sind dann nicht vorausgewählt.' });
    if (v && offen && !ae.erste) { s2.marke = ['wartet auf Schritt 1', '']; s2.hinweise.push([`Kunden sehen immer den veröffentlichten Stand – heute noch ${esc(kw(v))}. Bitte zuerst veröffentlichen.`, false]); }
    else if (v && vs.empfaenger && rest > 0) { s2.klasse = 'offen'; s2.marke = ['offen', 'warn']; }
    if (v && !vs.postfach) s2.hinweise.push(['Das Postfach für den E-Mail-Versand ist noch nicht eingerichtet (Verwaltung → E-Mail).', false]);
    const darfSend = r.woche && !!v && vs.empfaenger > 0 && vs.postfach;
    s2.fuss = `<button class="vs-knopf${s2.klasse === 'offen' && darfSend ? ' primaer' : ''}" type="button" id="vs-send"${darfSend ? '' : ' disabled'} title="${esc(!r.woche ? 'Dafür fehlt Ihnen das Recht „Wochenangebot per E-Mail an Kunden senden“' : !v ? 'Erst veröffentlichen' : !vs.postfach ? 'Das Postfach ist noch nicht eingerichtet' : 'Empfänger wählen und senden')}">${icon('mail')}${s2.klasse === 'offen' && darfSend ? `An ${plural(rest, 'Kunden', 'Kunden')} senden …` : 'Senden …'}</button>`
      + (!r.woche ? '<span class="vs-leise vs-klein">Ihnen fehlt das Recht zum Senden</span>' : '');
    $('#vs-schritte').innerHTML = schritt(s1) + schritt(s2);

    /* Angebote dieser Woche */
    $('#vs-angebote').innerHTML = d.angebote.map((a) => {
      const arten = a.std ? ae.arten : null;   // Aufstellung nur beim Wochenangebot (Artikel und Kopfdaten gelten für alle)
      const detail = arten && a.aenderungen ? ART_REIHE.filter((k) => arten[k] && k !== 'angebotspreis' && k !== 'werbung').map((k) => (k === 'kopf' || k === 'aufbau' ? ART_KURZ[k][0] : `${arten[k]} ${ART_KURZ[k][arten[k] === 1 ? 0 : 1]}`)).join(' · ') : '';
      const aend = ae.erste && e ? '<span class="vs-marke warn">noch nicht veröffentlicht</span>'
        : a.aenderungen ? `<span class="vs-marke warn">${plural(a.aenderungen, 'Änderung', 'Änderungen')}</span>${detail ? `<span class="vs-unter vs-detail">${esc(detail)}</span>` : ''}` : '<span class="vs-marke ok">aktuell</span>';
      const q = a.std ? '' : '&angebot=' + encodeURIComponent(a.id);
      const knoepfe = (a.sonderposten > 0 && r.sonderposten ? `<button class="vs-knopf klein" type="button" data-sonderposten="${esc(a.id)}" title="Sonderposten dieses Angebots per E-Mail an seine Kunden senden">${icon('mail')}Sonderposten</button>` : '')
        + (r.angebot ? `<a class="vs-knopf klein nur-symbol" href="${esc(ANGEBOT)}index.html?vorschau=1${q}" target="_blank" rel="noopener" title="Vorschau: so sehen Kunden das Angebot nach dem Veröffentlichen" aria-label="Vorschau ${esc(a.name)}">${icon('auge')}</a>`
          + `<a class="vs-knopf klein nur-symbol" href="${esc(ANGEBOT)}index.html?vorschau=1&amp;drucken=liste${q}" target="_blank" rel="noopener" title="Drucken oder als PDF speichern (Angebotsansicht)" aria-label="Drucken ${esc(a.name)}">${icon('druck')}</a>` : '');
      return `<tr data-angebot="${esc(a.id)}"><td><span class="vs-name">${esc(a.name)}</span><span class="vs-unter">${a.std ? (a.oeffentlich ? 'öffentlich' : 'nur für Kunden') : 'Kundenangebot'} · ${plural(a.artikel, 'Artikel', 'Artikel')}${a.sonderposten ? ` · ${plural(a.sonderposten, 'Sonderposten', 'Sonderposten')}` : ''}</span></td>
        <td data-t="Änderungen">${aend}</td><td class="vs-r vs-zahlen" data-t="Kunden">${a.kunden}</td>
        <td class="vs-fest" data-t="Letzter Versand">${a.zuletzt ? `KW ${a.zuletzt.week} · ${esc(tag(a.zuletzt.t))}` : '<span class="vs-leise">noch nicht versendet</span>'}</td>
        <td><div class="vs-zeilenknoepfe">${knoepfe}</div></td></tr>`;
    }).join('');
    verlaufZeichnen();
  }
  function verlaufZeichnen() {
    const host = $('#vs-verlauf'), l = S.verlauf;
    if (!l) return;
    host.removeAttribute('aria-busy');
    host.innerHTML = l.length ? `<ul class="vs-liste">${l.map((x) => {
      const mail = x.art !== 'veroeffentlicht';
      const titel = mail ? `${x.titel} gesendet` : x.titel.split(' – ')[0];
      const meta = (mail ? `an ${plural(x.ok, 'Kunden', 'Kunden')}${x.fehler ? ` · ${x.fehler} nicht zugestellt` : ''}` : (x.titel.split(' – ')[1] || '')) + (x.von ? ' · ' + x.von : '');
      return `<li><div class="vs-zeile"><span class="vs-ico" data-symbol="${mail ? 'users' : 'tag'}">${icon(mail ? 'mail' : 'send')}</span><span class="vs-zeile-text"><span class="vs-zeile-titel">${esc(titel)}</span><span class="vs-zeile-meta">${esc(meta)}</span></span><span class="vs-zeile-datum">${esc(zeit(x.t).replace(' Uhr', ''))}</span></div></li>`;
    }).join('')}</ul>` : '<p class="vs-leer">Noch keine Veröffentlichung und kein Versand im Protokoll.</p>';
    // wer hat den Stand veröffentlicht, der online ist? (aus dem Verlauf, wenn der Zeitpunkt passt)
    const v = S.d.veroeffentlicht, von = $('#vs-pub-von');
    const p = v && l.find((x) => x.art === 'veroeffentlicht' && Math.abs(new Date(x.t) - new Date(v.publishedAt)) < 60000);
    if (von && p && p.von) von.textContent = ' von ' + p.von;
    $('#vs-verlauf-alle').hidden = S.monate > 2 || !S.verlaufMehr;
  }
  async function verlaufLaden() {
    const r = await api('versand_verlauf', null, '&monate=' + S.monate);
    if (r.status !== 200 || !r.data.ok) { $('#vs-verlauf').innerHTML = `<p class="vs-leer">${esc(fehlerText(r, 'Verlauf nicht geladen'))}</p>`; return; }
    S.verlauf = r.data.verlauf; S.verlaufMehr = r.data.monateMax > 2;
    verlaufZeichnen();
  }
  async function laden(still) {
    const r = await api('versand_start');
    if (r.status === 401) { zeigeAnmeldung(); return false; }
    if (r.status !== 200 || !r.data.ok) { if (still) toast(fehlerText(r, 'Stand nicht geladen'), true); else fehler(fehlerText(r, 'Der Versand ist gerade nicht erreichbar')); return false; }
    S.d = r.data;
    $('#vs-err').hidden = true; $('#vs-login').hidden = true; $('#vs-app').hidden = false;
    zeichnen();
    verlaufLaden();
    return true;
  }

  /* ---------- Fenster „Veröffentlichen“ ---------- */
  const zu = (titelId, titel, text) => `<div class="dlg-head"><div><h2 id="${titelId}">${esc(titel)}</h2>${text ? `<p>${text}</p>` : ''}</div><button class="vs-zu" type="button" data-close aria-label="Schließen">${icon('x')}</button></div>`;
  function pubZeichnen(filter) {
    const d = S.d, a = S.aend, e = d.entwurf, v = d.veroeffentlicht;
    const namen = a.angebote || {};
    const kurz = (oid) => (namen[oid] || oid).replace(/^(Wochen)?[Aa]ngebot\s+/, '') || namen[oid] || oid;
    const passt = (z) => filter === '*' || (filter === '' ? z.angebot === '' || z.angebot === 'std' : z.angebot === filter);
    const chips = [['*', 'Alle', a.anzahl]].concat(Object.keys(a.jeAngebot).filter((k) => k !== '' && k !== 'std').map((k) => [k, kurz(k), a.jeAngebot[k]]));
    const basis = (a.jeAngebot[''] || 0) + (a.jeAngebot.std || 0);
    if (basis && chips.length > 1) chips.splice(1, 0, ['', 'Wochenangebot', basis]);
    let body = '';
    if (a.erste) body = `<p class="vs-hinweis neutral">${icon('info')}<span>Erste Veröffentlichung: ${plural(e.artikel, 'Artikel', 'Artikel')}.</span></p>`;
    else if (!a.anzahl) body = `<p class="vs-hinweis neutral">${icon('info')}<span>Keine Änderungen gegenüber der veröffentlichten Fassung erkannt.</span></p>`;
    else {
      if (chips.length > 2) body += `<div class="vs-filter" role="group" aria-label="Änderungen nach Angebot">${chips.map(([k, t, n]) => `<button class="vs-chip" type="button" data-filter="${esc(k)}" aria-pressed="${k === filter}">${esc(t)} <b>${n}</b></button>`).join('')}</div>`;
      for (const art of ART_REIHE) {
        const z = a.zeilen.filter((x) => x.art === art && passt(x));
        if (!z.length) continue;
        body += `<p class="vs-h"><span>${esc(ART_TEXT[art])}${art === 'kopf' || art === 'aufbau' ? '' : ` (${z.length})`}</span></p><ul class="vs-aend">${z.slice(0, 200).map((x) => {
          const links = (x.angebot && x.angebot !== 'std' ? `<span class="vs-marke">${esc(kurz(x.angebot))}</span>` : '') + esc((x.code ? x.code + ' · ' : '') + x.name);
          const rechts = art === 'neu' ? `<strong>${esc(x.nach)}</strong>` : art === 'entfernt' ? esc(x.von) : x.von || x.nach ? `${esc(x.von || '—')} → <strong>${esc(x.nach || '—')}</strong>` : '';
          return `<li><span>${links}</span><span>${rechts}</span>${x.zusatz ? `<small>${esc(x.zusatz)}</small>` : ''}</li>`;
        }).join('')}${z.length > 200 ? `<li><span>… und ${z.length - 200} weitere</span><span></span></li>` : ''}</ul>`;
      }
    }
    $('#pub-inhalt').innerHTML = zu('pub-titel', `${kw(e)} veröffentlichen`, `Danach sehen Kunden diesen Stand.${v ? ` Der bisherige Stand (${esc(kw(v))}) wird als Version gesichert.` : ''}`)
      + `<div class="dlg-body"><p class="vs-meldung" id="pub-meldung" role="alert" hidden></p>${body}</div>
      <div class="dlg-foot">${d.rechte.angebot ? `<span class="vs-fuss-links">Etwas stimmt nicht? <a class="vs-link" href="${esc(ANGEBOT)}admin/">Im Angebot ändern</a></span>` : ''}
        <button class="vs-knopf" type="button" data-close>Abbrechen</button><button class="vs-knopf primaer" type="button" id="pub-jetzt">${icon('send')}Jetzt veröffentlichen</button></div>`;
  }
  async function pubOeffnen() {
    const d = S.d;
    if (!d.entwurf) return;
    if (d.rechte.angebot) {
      const r = await api('versand_aenderungen');
      if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Änderungen nicht geladen'), true); return; }
      S.aend = r.data;
    } else S.aend = { ...d.aenderungen, zeilen: [], angebote: {}, ohneListe: true };   // ohne Modulzugang Angebot: nur die Zahl
    pubZeichnen('*');
    if (S.aend.ohneListe && S.aend.anzahl) $('#pub-inhalt .dlg-body').insertAdjacentHTML('beforeend', `<p class="vs-hinweis neutral">${icon('info')}<span>${plural(S.aend.anzahl, 'Änderung', 'Änderungen')} im Entwurf. Die Liste mit Preisen sehen Sie nur mit Zugang zum Angebot.</span></p>`);
    $('#dlg-pub').showModal();
  }
  async function veroeffentlichen(knopf) {
    knopf.disabled = true; knopf.setAttribute('aria-busy', 'true');
    $('#dlg-pub').dataset.busy = '1';
    const r = await api('versand_veroeffentlichen', { revision: S.aend.revision });
    delete $('#dlg-pub').dataset.busy;
    knopf.disabled = false; knopf.removeAttribute('aria-busy');
    const m = $('#pub-meldung');
    if (r.status === 409 && r.data.conflict) {   // inzwischen hat jemand gespeichert: Liste neu holen, erst dann erneut bestätigen
      await laden(true);
      const neu = await api('versand_aenderungen');
      if (neu.status === 200 && neu.data.ok) { S.aend = neu.data; pubZeichnen('*'); }
      const m2 = $('#pub-meldung');
      m2.hidden = false; m2.textContent = (r.data.error || 'Der Entwurf wurde inzwischen geändert.') + ' Die Liste ist jetzt aktuell – bitte prüfen und erneut veröffentlichen.';
      return;
    }
    if (r.status !== 200 || !r.data.ok) { m.hidden = false; m.textContent = fehlerText(r, 'Nicht veröffentlicht'); if (r.status === 409) laden(true); return; }
    $('#dlg-pub').close();
    await laden(true);
    const vs = S.d.versand, darf = S.d.rechte.woche && vs.empfaenger > 0 && vs.postfach;
    $('#fertig-inhalt').innerHTML = zu('fertig-titel', 'Veröffentlicht', '')
      + `<div class="dlg-body"><div class="vs-erfolg"><span class="vs-haken">${icon('haken')}</span><h3>KW ${esc(r.data.week)}/${esc(r.data.year)} ist online</h3>
        <p>Veröffentlicht ${esc(zeit(r.data.publishedAt))}.${darf ? ` Jetzt das Wochenangebot per E-Mail an ${plural(vs.empfaenger, 'Kunden', 'Kunden')} senden?` : ''}</p></div></div>
      <div class="dlg-foot"><button class="vs-knopf" type="button" data-close>${darf ? 'Später' : 'Schließen'}</button>${darf ? `<button class="vs-knopf primaer" type="button" id="fertig-senden">${icon('mail')}Senden …</button>` : ''}</div>`;
    $('#dlg-fertig').showModal();
  }

  /* ---------- Fenster „Senden“ (Wochenangebot bzw. Sonderposten eines Angebots) ---------- */
  function sendZeichnen() {
    const s = S.send, w = s.art === 'woche', d = s.daten;
    const liste = w ? d.empfaenger : d.recipients.filter((c) => !c.reason);
    const aus = w ? d.ausgeschlossen.map((c) => [c.firma, c.grund]) : d.recipients.filter((c) => c.reason).map((c) => [c.firma, c.reason]);
    const namen = w ? d.angebote : {};
    const kurz = (oid) => (namen[oid] || oid).replace(/^(Wochen)?[Aa]ngebot\s+/, '') || namen[oid] || oid;
    const chips = w ? [['*', 'Alle', liste.length]].concat(Object.keys(namen).map((k) => [k, k === 'std' ? 'Wochenangebot' : kurz(k), liste.filter((c) => c.angebote.includes(k)).length]).filter((x) => x[2])) : [];
    const sicht = liste.filter((c) => s.filter === '*' || c.angebote.includes(s.filter));
    const titel = w ? `Wochenangebot ${kw(d.woche)} senden` : `Sonderposten „${d.offer.name}“ senden`;
    const text = w ? 'Jeder Kunde bekommt eine eigene E-Mail mit den Links zu seinen Angeboten – ohne Preise in der E-Mail.'
      : `Nur an Kunden, denen dieses Angebot freigeschaltet ist. Die E-Mail nennt die ${plural(d.items.length, 'Sonderposten', 'Sonderposten')} mit Preis.`;
    const zeile = (c) => {
      const erg = s.ergebnis[c.id];
      const stand = erg ? (erg.ok ? `<span class="vs-erg ok">gesendet</span>` : `<span class="vs-erg bad">${esc(erg.error || 'nicht gesendet')}</span>`)
        : w && c.gesendet ? `<span class="vs-erg warn">KW ${d.woche.week} bereits gesendet ${esc(tag(c.gesendet))}</span>` : w && !c.passwort ? '<span class="vs-erg warn">noch kein Passwort festgelegt</span>' : '';
      return `<li data-kunde="${esc(c.id)}"><input type="checkbox" data-wahl="${esc(c.id)}"${s.wahl.has(c.id) ? ' checked' : ''}${s.laeuft ? ' disabled' : ''} aria-label="${esc(c.firma)} auswählen"><div class="vs-wer">${esc(c.firma)}<span>${esc(c.email)}</span></div>
        <div class="vs-rechts">${stand}${w ? c.angebote.map((o) => `<span class="vs-marke">${esc(o === 'std' ? 'Wochenangebot' : kurz(o))}</span>`).join('') : ''}</div></li>`;
    };
    const n = s.wahl.size;
    $('#send-inhalt').innerHTML = zu('send-titel', titel, esc(text))
      + `<div class="dlg-body"><p class="vs-meldung${s.meldung && s.meldung[1] ? ' ok' : ''}" id="send-meldung" role="alert"${s.meldung ? '' : ' hidden'}>${s.meldung ? esc(s.meldung[0]) : ''}</p>
        ${!w && d.items.length ? `<ul class="vs-aend vs-artikel">${d.items.map((it) => `<li><span>${esc((it.code ? it.code + ' · ' : '') + it.name)}</span><span><strong>${esc(window.STAFL_FORMAT.euroKg(it.price))}</strong>${it.regular != null ? ` statt ${esc(window.STAFL_FORMAT.euroKg(it.regular))}` : ''}</span></li>`).join('')}</ul>` : ''}
        ${chips.length > 2 ? `<div class="vs-filter" role="group" aria-label="Empfänger nach Angebot">${chips.map(([k, t, z]) => `<button class="vs-chip" type="button" data-filter="${esc(k)}" aria-pressed="${k === s.filter}">${esc(t)} <b>${z}</b></button>`).join('')}</div>` : ''}
        ${liste.length ? `<div class="vs-empf"><div class="vs-empf-kopf"><label class="vs-check"><input type="checkbox" id="send-alle"${s.laeuft ? ' disabled' : ''}> <span id="send-zahl"></span></label>${aus.length ? `<span class="vs-leise">${aus.length} nicht berücksichtigt</span>` : ''}</div>
          <ul>${sicht.map(zeile).join('')}</ul></div>` : '<p class="vs-hinweis neutral">' + icon('info') + '<span>Kein Kunde mit E-Mail-Adresse, aktivem Zugang und freigeschaltetem Angebot.</span></p>'}
        ${aus.length ? `<details class="vs-aus"><summary>${plural(aus.length, 'Kunde', 'Kunden')} nicht berücksichtigt</summary><ul>${aus.map(([f, g]) => `<li>${esc(f)} – ${esc(g)}</li>`).join('')}</ul></details>` : ''}
        <label class="vs-feld">Zusatztext <small>optional, erscheint in jeder E-Mail</small><textarea id="send-note" maxlength="1000" placeholder="z. B. Diese Woche besonders günstig: Roastbeef."${s.laeuft ? ' disabled' : ''}>${esc(s.note)}</textarea></label>
        ${s.pw ? '<label class="vs-feld">Passwort zur Bestätigung<input type="password" id="send-pw" autocomplete="current-password"></label>' : ''}
        <div class="vs-mail" id="send-vorschau" hidden><dl><dt>Betreff</dt><dd id="send-betreff"></dd><dt>Vorschau für</dt><dd id="send-fuer"></dd></dl><iframe id="send-frame" sandbox="" title="Vorschau der E-Mail"></iframe></div>
      </div>
      <div class="dlg-foot"><span class="vs-fuss-links"><button class="vs-knopf klein" type="button" id="send-prev"${liste.length ? '' : ' disabled'}>${icon('auge')}Vorschau der E-Mail</button></span>
        <button class="vs-knopf" type="button" data-close>${s.fertig ? 'Schließen' : 'Abbrechen'}</button><button class="vs-knopf primaer" type="submit" id="send-jetzt">${icon('mail')}<span id="send-knopf"></span></button></div>`;
    sendZahl();
  }
  function sendZahl() {
    const s = S.send, n = s.wahl.size;
    const alle = $('#send-alle'), boxen = $$('#send-inhalt [data-wahl]');
    if (alle) { alle.checked = boxen.length > 0 && boxen.every((b) => b.checked); alle.indeterminate = !alle.checked && boxen.some((b) => b.checked); }
    const z = $('#send-zahl'); if (z) z.textContent = `${plural(n, 'Kunde', 'Kunden')} ausgewählt`;
    $('#send-knopf').textContent = s.laeuft ? `Wird gesendet … ${s.stand}` : n ? `An ${plural(n, 'Kunden', 'Kunden')} senden` : 'Kunden auswählen';
    $('#send-jetzt').disabled = !n || s.laeuft;
  }
  async function sendOeffnen(art, angebot, merk) {
    const r = await api('versand_empfaenger', null, '&art=' + art + (art === 'sonderposten' ? '&angebot=' + encodeURIComponent(angebot) : ''));
    if (r.status !== 200 || !r.data.ok) { toast(fehlerText(r, 'Empfänger nicht geladen'), true); return; }
    const d = r.data, w = art === 'woche';
    if (!d.postfach) { toast('Das Postfach für den E-Mail-Versand ist noch nicht eingerichtet (Verwaltung → E-Mail).', true); return; }
    if (w && !d.woche) { toast('Es ist noch kein Angebot veröffentlicht.', true); return; }
    if (!w && !d.items.length) { toast('In diesem Angebot sind keine Sonderposten veröffentlicht (oder alle ohne Bestand).', true); return; }
    const liste = w ? d.empfaenger : d.recipients.filter((c) => !c.reason);
    const vor = merk ? liste.filter((c) => merk.ids.includes(c.id)) : w ? liste.filter((c) => c.passwort && !c.gesendet) : liste;
    S.send = { art, angebot: angebot || '', daten: d, wahl: new Set(vor.map((c) => c.id)), filter: '*', note: merk ? merk.note : '', ergebnis: {}, laeuft: false, stand: '', pw: false, fertig: false,
      meldung: merk ? ['Bestätigt. Bitte den Versand jetzt mit „Senden“ auslösen.', true] : null };
    sendZeichnen();
    $('#dlg-send').showModal();
  }
  async function vorschau() {
    const s = S.send, id = [...s.wahl][0] || ((s.art === 'woche' ? s.daten.empfaenger : s.daten.recipients)[0] || {}).id;
    const r = await api('versand_vorschau', { art: s.art, angebot: s.angebot, id, note: $('#send-note').value });
    if (r.status !== 200 || !r.data.ok) { const m = $('#send-meldung'); m.hidden = false; m.className = 'vs-meldung'; m.textContent = fehlerText(r, 'Vorschau nicht geladen'); return; }
    $('#send-vorschau').hidden = false;
    $('#send-betreff').textContent = r.data.subject; $('#send-fuer').textContent = `${r.data.firma} · ${r.data.to}`;
    $('#send-frame').srcdoc = r.data.html;
    $('#send-vorschau').scrollIntoView({ block: 'nearest' });
  }
  async function senden() {
    const s = S.send, d = s.daten, w = s.art === 'woche';
    const ids = [...s.wahl];
    if (!ids.length || s.laeuft) return;
    s.note = $('#send-note').value;
    if (s.pw) {   // Bestätigung mit Passwort (ohne zentrale Anmeldung)
      const pw = $('#send-pw').value;
      const pr = await api('reauth', { password: pw });
      if (pr.status !== 200) { s.meldung = [fehlerText(pr, 'Passwort nicht bestätigt'), false]; sendZeichnen(); $('#send-pw').focus(); return; }
      s.pw = false;
    }
    s.laeuft = true; s.meldung = null; s.stand = `0/${ids.length}`;
    $('#dlg-send').dataset.busy = '1';
    sendZeichnen();
    let ok = 0, bad = 0, abbruch = '';
    for (let i = 0; i < ids.length && !abbruch; i += TEIL) {
      const teil = ids.slice(i, i + TEIL);
      const body = w ? { art: 'woche', ids: teil, note: s.note, week: d.woche.week, year: d.woche.year } : { art: 'sonderposten', angebot: s.angebot, ids: teil, note: s.note, publishedAt: d.publishedAt };
      const r = await api('versand_senden', body);
      if (r.status === 403 && r.data.code === 'reauth_required' && typeof r.data.anmelden === 'string' && r.data.anmelden.startsWith('/oidc/')) {
        try { sessionStorage.setItem(MERK, JSON.stringify({ art: s.art, angebot: s.angebot, ids: ids.slice(i), note: s.note })); } catch { /* ohne Speicher: Auswahl erneut treffen */ }
        location.assign(r.data.anmelden + encodeURIComponent(location.href));
        return;
      }
      if (r.status === 403 && r.data.code === 'confirmation_required') { s.pw = true; abbruch = 'Bitte bestätigen Sie den Versand mit Ihrem Passwort.'; s.okHinweis = true; break; }
      if (r.status !== 200 || !r.data.ok) {
        for (const id of teil) s.ergebnis[id] = { ok: false, error: fehlerText(r, 'nicht gesendet') };
        bad += teil.length;
        if ([401, 403, 409].includes(r.status)) abbruch = fehlerText(r, 'Versand abgebrochen');
      } else for (const x of r.data.results) {
        s.ergebnis[x.id] = x;
        if (x.ok) { ok++; s.wahl.delete(x.id); } else bad++;
      }
      s.stand = `${Math.min(i + TEIL, ids.length)}/${ids.length}`;
      sendZeichnen();
    }
    s.laeuft = false; delete $('#dlg-send').dataset.busy;
    s.fertig = ok > 0;
    s.meldung = abbruch ? [abbruch, !!s.okHinweis] : [`${plural(ok, 'E-Mail', 'E-Mails')} gesendet${bad ? `, ${bad} nicht zugestellt – Grund steht in der Zeile` : ''}.`, !bad];
    s.okHinweis = false;
    sendZeichnen();
    if (s.pw) $('#send-pw').focus();
    if (ok) laden(true);
  }

  /* ---------- Bedienung ---------- */
  document.addEventListener('click', (e) => {
    const zuKnopf = e.target.closest('dialog [data-close]');
    if (zuKnopf) { const dlg = zuKnopf.closest('dialog'); if (!dlg.dataset.busy) dlg.close(); return; }
    if (e.target.closest('#vs-pub')) { pubOeffnen(); return; }
    if (e.target.closest('#vs-send')) { sendOeffnen('woche'); return; }
    const sp = e.target.closest('[data-sonderposten]');
    if (sp) { sendOeffnen('sonderposten', sp.dataset.sonderposten); return; }
    if (e.target.closest('#vs-neu')) { laden(true).then((ok) => { if (ok) toast('Stand aktualisiert.'); }); return; }
    if (e.target.closest('#vs-verlauf-alle')) { S.monate = 6; verlaufLaden(); return; }
    if (e.target.closest('#fertig-senden')) { $('#dlg-fertig').close(); sendOeffnen('woche'); return; }
    const pj = e.target.closest('#pub-jetzt');
    if (pj) { veroeffentlichen(pj); return; }
    const chip = e.target.closest('.vs-chip');
    if (chip && chip.closest('#dlg-pub')) { pubZeichnen(chip.dataset.filter); return; }
    if (chip && chip.closest('#dlg-send')) { S.send.note = $('#send-note').value; S.send.filter = chip.dataset.filter; sendZeichnen(); return; }
    if (e.target.closest('#send-prev')) { vorschau(); return; }
  });
  $('#dlg-send').addEventListener('change', (e) => {
    const s = S.send;
    if (e.target.id === 'send-alle') for (const b of $$('#send-inhalt [data-wahl]')) { b.checked = e.target.checked; if (b.checked) s.wahl.add(b.dataset.wahl); else s.wahl.delete(b.dataset.wahl); }
    if (e.target.dataset.wahl) { if (e.target.checked) s.wahl.add(e.target.dataset.wahl); else s.wahl.delete(e.target.dataset.wahl); }
    sendZahl();
  });
  $('#send-inhalt').addEventListener('submit', (e) => { e.preventDefault(); senden(); });
  for (const dlg of $$('dialog')) dlg.addEventListener('cancel', (e) => { if (dlg.dataset.busy) e.preventDefault(); });   // Escape nicht, solange gesendet wird
  $('#vs-theme').addEventListener('click', () => { document.documentElement.setAttribute('data-theme', dunkel() ? 'light' : 'dark'); themaKnopf(); });
  document.addEventListener('stafl-theme', themaKnopf);
  document.addEventListener('visibilitychange', () => { if (!document.hidden && S.d && !$$('dialog[open]').length) laden(true); });   // zurück im Fenster: Stand auffrischen

  /* ---------- Start ---------- */
  (async () => {
    themaKnopf();
    const st = await api('status');
    if (st.status !== 200) { fehler(fehlerText(st, 'Der Versand ist gerade nicht erreichbar')); return; }
    if (!st.data.loggedIn) { zeigeAnmeldung(); return; }
    S.csrf = st.data.csrf || '';
    if (window.STAFL_THEME) { window.STAFL_THEME.konto(st.data.user, S.csrf, API); themaKnopf(); }
    if (!(await laden(false))) return;
    let merk = null;
    try { merk = JSON.parse(sessionStorage.getItem(MERK) || 'null'); sessionStorage.removeItem(MERK); } catch { merk = null; }
    if (merk && (merk.art === 'woche' || merk.art === 'sonderposten') && Array.isArray(merk.ids)) sendOeffnen(merk.art, merk.angebot, { ids: merk.ids.filter((x) => typeof x === 'string'), note: String(merk.note || '') });
  })();
})();
