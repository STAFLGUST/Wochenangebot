/* STAFL-Plattform · Dashboard (Startseite, Gestaltung „C2“)
   Aufbau: Begrüßung mit Zahl der offenen Punkte, Hinweise zu Wartungen, Favoriten (kompakte Kacheln, „Bearbeiten“),
   „Heute für Sie“ (Überfällig / Heute / Demnächst), Schnellaktionen und „Zuletzt bearbeitet“. Seitenleiste mit Suche (Strg K)
   und Zahlen je Anwendung zeichnet der gemeinsame Rahmen (../assets/rahmen.js).
   Daten: module_status (Modulregister – keine fest programmierte Liste) und start_heute (nur Dashboard-Host, GR-109: offene
   Punkte liefern die Module nach ihren Rechten, Schnellaktionen, eigene letzte Änderungen, Favoriten am Konto). Was eine Kachel
   oder ein Punkt zeigt, ist nur Anzeige; ob eine Anwendung nutzbar ist und welche Rechte gelten, entscheidet der Server bei
   jeder Aktion (GR-102, GR-103). Kein Inline-Skript (Content-Security-Policy); fremde Texte nur maskiert.
   Knöpfe oben rechts: Schnellzugriff (Blitz, öffnet die Suche), einfache Darstellung für Remote-Desktop (Bildschirm; Wahl am
   Konto, sonst automatisch erkannt, theme.js), Hell/Dunkel. */
'use strict';
(() => {
  const API = '../api/';
  const R = window.STAFL_RAHMEN;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (n) => `<svg class="r-i" aria-hidden="true"><use href="#i-${n}"/></svg>`;   // Symbole dieser Seite (Hell/Dunkel …)
  const ENTWICKLUNG = { geplant: 'Geplant', in_entwicklung: 'In Entwicklung', in_pruefung: 'In Prüfung', fertig: 'Nicht freigegeben' };
  const FAV_MAX = 8, FAV_STANDARD = 4, JE_GRUPPE = 3;   // „Heute für Sie“: je Gruppe drei Punkte, alle auf Wunsch
  const S = { module: [], alle: {}, heute: null, favoriten: null, alleZeigen: false, wahl: null };
  let csrf = '';

  async function api(action, body) {
    const res = await fetch(API + '?action=' + action, {
      method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf } : {}, body: body ? JSON.stringify(body) : undefined,
    });
    let data = null;
    try { data = await res.json(); } catch { /* keine JSON-Antwort */ }
    return { status: res.status, data: data || {}, json: data !== null };
  }

  window.STAFL_KACHEL_ZIEL = R.ziel;   // für die Tests (reine Funktion, keine Daten; liegt im gemeinsamen Rahmen)

  /* Ziel eines Moduls auf diesem Host, optional mit Reiter („antraege“ → …/#antraege) */
  function modulZiel(id, reiter) {
    const m = S.alle[id];
    if (!m || !m.kachel) return '';
    const z = R.ziel(m.kachel, S.alle, location.hostname);
    return z === '#' ? '' : z + (reiter ? '#' + reiter : '');
  }

  function status(m) {
    const k = m.kachel || {};
    const [zm, zo] = String(k.ziel || '').split('.');
    const ob = ((S.alle[zm] || {}).oberflaechen || []).find((o) => o.id === zo) || {};
    switch (k.status) {
      case 'verfuegbar': return { text: 'Verfügbar', cls: 'ok' };
      case 'wartung': return { text: k.zugang ? 'Wartung – Zugang für Administratoren' : 'Wartung', cls: 'warn', hinweis: ob.wartung && ob.wartung.message };
      case 'testbetrieb': return { text: 'Testbetrieb', cls: 'warn' };
      case 'in_pruefung': return { text: 'Nur für Tester', cls: '' };
      case 'deaktiviert': return { text: 'Deaktiviert', cls: '' };
      case 'entwicklungsstand': return { text: ENTWICKLUNG[ob.entwicklung] || 'In Vorbereitung', cls: '' };
      default: return { text: 'Nicht verfügbar', cls: '' };
    }
  }

  /* Eine kompakte Kachel: Symbol und Name, keine Unterzeile. Eine zweite Zeile nur bei besonderem Stand (Wartung mit
     Hinweis, Testbetrieb …); „Verfügbar“ bleibt für Screenreader im Text. Zahl offener Punkte rechts oben. */
  function kachel(m) {
    const s = status(m);
    const bald = R.art(m) === 'bald';
    const z = S.heute && S.heute.zahlen ? S.heute.zahlen[m.id] : null;
    const zahl = z && z.offen ? `<span class="db-zahl${z.ueberfaellig ? ' rot' : ''}" title="${z.offen} offen">${z.offen > 99 ? '99+' : z.offen}<span class="sr-only"> offen</span></span>` : '';
    const inhalt = `<span class="db-ico" data-symbol="${esc(m.icon)}">${R.symbol(m.icon)}</span>
      <span class="db-text"><span class="db-name">${esc(m.name)}</span><span class="db-badge ${s.cls}${s.cls === 'ok' ? ' sr-only' : ''}">${esc(s.text)}</span>
      ${s.hinweis ? `<span class="db-hint">${esc(s.hinweis)}</span>` : ''}</span>${zahl}
      ${bald ? '<span class="r-bald" aria-hidden="true">Bald</span>' : ''}`;
    return m.kachel.zugang
      ? `<a class="db-tile" role="listitem" data-modul="${esc(m.id)}" href="${esc(R.ziel(m.kachel, S.alle, location.hostname))}">${inhalt}</a>`
      : `<div class="db-tile off${bald ? ' gesperrt' : ''}" role="listitem" data-modul="${esc(m.id)}" aria-disabled="true">${inhalt}</div>`;
  }

  /* ── Favoriten: Wahl am Konto (start_heute.favoriten); ohne Wahl die ersten Anwendungen in der Reihenfolge des Registers ── */
  // wie die Seitenleiste: Anwendungen, danach „Verwaltung & Daten“ – jeweils in der Reihenfolge des Registers
  const waehlbar = () => { const l = R.sichtbar(S.module).filter((m) => R.art(m) !== 'bald'); return [...l.filter((m) => m.gruppe !== 'verwaltung'), ...l.filter((m) => m.gruppe === 'verwaltung')]; };
  function favoritenListe() {
    const w = waehlbar();
    if (Array.isArray(S.favoriten)) return S.favoriten.map((id) => w.find((m) => m.id === id)).filter(Boolean);
    return w.filter((m) => m.gruppe !== 'verwaltung').slice(0, FAV_STANDARD);
  }
  function favoritenZeigen() {
    const liste = favoritenListe();
    $('#db-grid').innerHTML = liste.map(kachel).join('') || (waehlbar().length
      ? '<p class="db-leer" role="listitem">Keine Favoriten gewählt – über „Bearbeiten“ Anwendungen hinzufügen.</p>'
      : '<p class="db-leer" role="listitem">Für Ihre Rolle ist noch keine Anwendung freigegeben. Bitte an einen Administrator wenden.</p>');
    $('#db-fav-bearbeiten').hidden = !waehlbar().length;
    einpassen();
  }
  function wahlZeigen() {
    const w = waehlbar();
    $('#db-fav-auswahl').innerHTML = w.map((m) => `<button class="db-fav-chip" type="button" data-modul="${esc(m.id)}" aria-pressed="${S.wahl.includes(m.id)}">`
      + `<span class="db-ico klein" data-symbol="${esc(m.icon)}">${R.symbol(m.icon)}</span>${esc(m.name)}</button>`).join('');
    const voll = S.wahl.length >= FAV_MAX;
    for (const b of document.querySelectorAll('.db-fav-chip')) b.disabled = voll && b.getAttribute('aria-pressed') !== 'true';
    $('#db-fav-text').textContent = `Wählen Sie bis zu acht Anwendungen für den schnellen Zugriff (${S.wahl.length} von ${FAV_MAX}).`;
  }
  function wahlOeffnen(auf) {
    S.wahl = auf ? favoritenListe().map((m) => m.id) : null;
    $('#db-fav-wahl').hidden = !auf; $('#db-grid').hidden = auf;
    $('#db-fav-bearbeiten').setAttribute('aria-expanded', String(auf));
    $('#db-fav-bearbeiten').hidden = auf;   // beim Bearbeiten nur „Abbrechen“ und „Speichern“
    $('#db-fav-fehler').hidden = true;
    if (auf) { wahlZeigen(); const b = document.querySelector('.db-fav-chip'); if (b) b.focus(); } else $('#db-fav-bearbeiten').focus();
  }
  $('#db-fav-bearbeiten').addEventListener('click', () => wahlOeffnen(true));
  $('#db-fav-abbrechen').addEventListener('click', () => wahlOeffnen(false));
  $('#db-fav-speichern').addEventListener('click', () => speichern());
  $('#db-fav-auswahl').addEventListener('click', (e) => {
    const b = e.target.closest('.db-fav-chip');
    if (!b || b.disabled) return;
    const id = b.dataset.modul;
    // Reihenfolge des Registers beibehalten (wie in der Seitenleiste)
    const neu = S.wahl.includes(id) ? S.wahl.filter((x) => x !== id) : [...S.wahl, id];
    S.wahl = waehlbar().map((m) => m.id).filter((x) => neu.includes(x));
    wahlZeigen();
    const gleich = document.querySelector(`.db-fav-chip[data-modul="${CSS.escape(id)}"]`);
    if (gleich) gleich.focus();
  });
  async function speichern() {
    const knopf = $('#db-fav-speichern');
    knopf.disabled = true;
    const r = await api('start_favoriten_save', { favoriten: S.wahl }).catch(() => ({ status: 0, data: {} }));
    knopf.disabled = false;
    if (r.status !== 200 || !r.data.ok) {
      $('#db-fav-fehler').hidden = false;
      $('#db-fav-fehler').textContent = r.data.error || 'Die Favoriten konnten nicht gespeichert werden.';
      return;
    }
    S.favoriten = r.data.favoriten;
    wahlOeffnen(false);
    favoritenZeigen();
  }

  /* ── Heute für Sie ── */
  const GRUPPEN = [['ueberfaellig', 'Überfällig'], ['heute', 'Heute'], ['demnaechst', 'Demnächst']];
  const tag = (iso) => new Date(iso + 'T12:00:00');
  function datumText(iso, heute) {
    if (!iso) return '';
    const t = Math.round((tag(iso) - tag(heute)) / 864e5);
    if (t === 0) return 'Heute';
    if (t === 1) return 'Morgen';
    if (t === -1) return 'Gestern';
    const d = tag(iso);
    const kurz = `${d.getDate()}.${d.getMonth() + 1}.`;
    return t > 1 && t < 7 ? d.toLocaleDateString('de-DE', { weekday: 'short' }).replace('.', '') + ', ' + kurz : kurz;
  }
  function punktZeile(p, heute) {
    const m = S.alle[p.modul] || {}, href = modulZiel(p.modul, p.ziel);
    const meta = [m.name, p.detail].filter(Boolean).join(' · ');
    const inhalt = `<span class="db-ico klein" data-symbol="${esc(m.icon)}">${R.symbol(m.icon)}</span>`
      + `<span class="db-zeile-text"><span class="db-zeile-titel">${esc(p.titel)}</span><span class="db-zeile-meta">${esc(meta)}</span></span>`
      + `<span class="db-zeile-datum ${esc(p.art)}">${esc(datumText(p.datum, heute))}</span>`;
    return `<li>${href ? `<a class="db-zeile" href="${esc(href)}" data-modul="${esc(p.modul)}">${inhalt}</a>` : `<span class="db-zeile">${inhalt}</span>`}</li>`;
  }
  function heuteZeigen() {
    const h = S.heute, liste = $('#db-heute-liste');
    liste.setAttribute('aria-busy', 'false');
    if (!h) {
      liste.innerHTML = '<p class="db-leer-zeile">Die offenen Punkte konnten nicht geladen werden. Bitte die Seite später neu laden.</p>';
      $('#db-heute-alle').hidden = true; $('#db-heute-zahl').hidden = true;
      return;
    }
    const p = h.punkte || [], g = h.gesamt || { offen: 0, ueberfaellig: 0 };
    const zeigen = S.alleZeigen ? p : GRUPPEN.flatMap(([art]) => p.filter((x) => x.art === art).slice(0, JE_GRUPPE));
    $('#db-heute-zahl').hidden = !g.offen; $('#db-heute-zahl').textContent = String(g.offen);
    $('#db-heute-zahl').classList.toggle('rot', g.ueberfaellig > 0);
    if (!p.length) {
      liste.innerHTML = `<p class="db-leer-zeile db-erledigt">${icon('check')}<span>Alles erledigt – heute steht für Sie nichts an.</span></p>`;
    } else {
      liste.innerHTML = GRUPPEN.map(([art, titel]) => {
        const teil = zeigen.filter((x) => x.art === art);
        return teil.length ? `<div class="db-gruppe ${art}"><h3 class="db-gruppe-titel">${titel}</h3><ul>${teil.map((x) => punktZeile(x, h.heute)).join('')}</ul></div>` : '';
      }).join('');
    }
    if (h.fehler && h.fehler.length) {
      const namen = h.fehler.map((id) => (S.alle[id] || {}).name || id).join(', ');
      liste.insertAdjacentHTML('beforeend', `<p class="db-leer-zeile db-teilfehler">${esc(namen)}: offene Punkte gerade nicht abrufbar.</p>`);
    }
    const mehr = p.length > zeigen.length || S.alleZeigen;
    $('#db-heute-alle').hidden = !mehr;
    $('#db-heute-alle').setAttribute('aria-expanded', String(S.alleZeigen));
    $('#db-heute-alle').textContent = S.alleZeigen ? 'Weniger anzeigen' : 'Alle offenen Punkte';
  }
  $('#db-heute-alle').addEventListener('click', () => { S.alleZeigen = !S.alleZeigen; heuteZeigen(); });

  /* Unterzeile: „6 offene Punkte, einer davon überfällig“ */
  function unterzeile() {
    const g = S.heute && S.heute.gesamt;
    $('#db-sub-trenner').hidden = !g;
    if (!g) { $('#db-sub').textContent = ''; return; }
    const ueber = g.ueberfaellig === 1 ? 'einer davon überfällig' : `${g.ueberfaellig} davon überfällig`;
    $('#db-sub').textContent = !g.offen ? 'keine offenen Punkte'
      : `${g.offen === 1 ? 'ein offener Punkt' : g.offen + ' offene Punkte'}${g.ueberfaellig ? (g.offen === 1 ? ', überfällig' : ', ' + ueber) : ''}`;
  }

  /* ── Schnellaktionen und Zuletzt bearbeitet ── */
  function aktionenZeigen() {
    const a = ((S.heute && S.heute.aktionen) || []).map((x) => ({ ...x, href: modulZiel(x.modul, x.ziel) })).filter((x) => x.href);
    $('#db-aktionen').hidden = !a.length;
    $('#db-aktionen-liste').innerHTML = a.slice(0, 4).map((x) => {
      const m = S.alle[x.modul] || {};
      return `<li><a class="db-zeile" href="${esc(x.href)}" data-modul="${esc(x.modul)}"><span class="db-ico klein" data-symbol="${esc(m.icon)}">${R.symbol(m.icon)}</span>`
        + `<span class="db-zeile-text"><span class="db-zeile-titel">${esc(x.titel)}</span></span>${R.symbol(x.neu ? 'plus' : 'pfeil', 'r-i db-plus')}</a></li>`;
    }).join('');
    // Suche (Strg K): alle Schnellaktionen zusätzlich zu den Anwendungen
    R.suche(a.map((x) => ({ titel: x.titel, href: x.href, symbol: (S.alle[x.modul] || {}).icon, gruppe: 'Schnellaktionen' })));
  }
  function zeitText(iso) {
    const t = new Date(iso);
    if (isNaN(t)) return '';
    const min = Math.round((Date.now() - t) / 6e4);
    if (min < 1) return 'gerade eben';
    if (min < 60) return `vor ${min} Min.`;
    if (min < 60 * 24 && t.getDate() === new Date().getDate()) return 'heute, ' + t.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) + ' Uhr';
    return t.toLocaleDateString('de-DE', { day: 'numeric', month: 'numeric' }) + ', ' + t.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' }) + ' Uhr';
  }
  function zuletztZeigen() {
    const z = (S.heute && S.heute.zuletzt) || [];
    $('#db-zuletzt').hidden = !z.length;
    $('#db-zuletzt-liste').innerHTML = z.map((x) => {
      const m = S.alle[x.modul] || {}, href = modulZiel(x.modul, '');
      const inhalt = `<span class="db-ico klein" data-symbol="${esc(m.icon)}">${R.symbol(m.icon)}</span>`
        + `<span class="db-zeile-text"><span class="db-zeile-titel db-zweizeilig">${esc(x.text)}</span><span class="db-zeile-meta">${esc([m.name, zeitText(x.zeit)].filter(Boolean).join(' · '))}</span></span>`;
      return `<li>${href ? `<a class="db-zeile" href="${esc(href)}" data-modul="${esc(x.modul)}">${inhalt}</a>` : `<span class="db-zeile">${inhalt}</span>`}</li>`;
    }).join('');
  }

  /* ── Hinweise: geplante und laufende Wartungen der eigenen Anwendungen (aus module_status), schließbar ── */
  const WEG = 'stafl.dashboard.hinweise';
  function weggeklickt() { try { return JSON.parse(localStorage.getItem(WEG) || '[]'); } catch { return []; } }
  function wartungen() {
    const gruppen = new Map();
    for (const m of R.sichtbar(S.module)) {
      if (R.art(m) === 'bald') continue;
      const [zm, zo] = String(m.kachel.ziel || '').split('.');
      const w = (((S.alle[zm] || {}).oberflaechen || []).find((o) => o.id === zo) || {}).wartung;
      if (!w) continue;
      const schluessel = [w.geplant ? 'geplant' : 'aktiv', w.ab || w.since || '', w.until || '', w.message || ''].join('|');
      if (!gruppen.has(schluessel)) gruppen.set(schluessel, { w, namen: [] });
      gruppen.get(schluessel).namen.push(m.name);
    }
    return [...gruppen].map(([schluessel, g]) => ({ schluessel, ...g }));
  }
  const uhr = (iso) => new Date(iso).toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
  const tagLang = (iso) => new Date(iso).toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });
  function hinweiseZeigen() {
    const weg = weggeklickt();
    const liste = wartungen().filter((x) => !weg.includes(x.schluessel));
    $('#db-hinweise').innerHTML = liste.map((x) => {
      const w = x.w, namen = x.namen.length > 3 ? x.namen.slice(0, 3).join(', ') + ` und ${x.namen.length - 3} weitere` : x.namen.join(', ');
      const bis = w.until ? (new Date(w.until).toDateString() === new Date(w.ab || Date.now()).toDateString() ? uhr(w.until) + ' Uhr' : tagLang(w.until) + ', ' + uhr(w.until) + ' Uhr') : '';
      const wann = w.geplant
        ? `Wartung am ${tagLang(w.ab)}, ${uhr(w.ab)}${bis ? '–' + bis : ' Uhr'}`
        : `Wartung läuft${bis ? ' bis ' + bis : ''}`;
      const text = w.message ? w.message : (w.geplant ? 'In dieser Zeit ist die Anwendung kurz nicht erreichbar.' : 'Die Anwendung ist gerade nicht erreichbar.');
      return `<div class="db-hinweis" role="status" data-schluessel="${esc(x.schluessel)}">${icon('warn')}<p><strong>${esc(wann)}</strong> · ${esc(namen)}. ${esc(text)}</p>`
        + `<button class="db-hinweis-zu" type="button" aria-label="Hinweis ausblenden">${icon('x')}</button></div>`;
    }).join('');
  }
  $('#db-hinweise').addEventListener('click', (e) => {
    const b = e.target.closest('.db-hinweis-zu');
    if (!b) return;
    const s = b.closest('.db-hinweis').dataset.schluessel;
    try { localStorage.setItem(WEG, JSON.stringify([...weggeklickt(), s].slice(-20))); } catch { /* ohne Speicher nur bis zum Neuladen */ }
    b.closest('.db-hinweis').remove();
  });

  /* Lange Kachelnamen (Registernamen wie „Qualitätssicherung“, „Container-Import“) nicht mitten im Wort trennen: Schrift in halben Pixeln
     verkleinern, bis das längste Wort in die Kachel passt – höchstens auf drei Viertel der Grundgröße. Reicht das
     nicht, darf das Wort als Notlösung umbrechen (Klasse db-name-umbruch), statt über die Kachel hinauszuragen. */
  /* true, wenn ein Wort über zwei Zeilen läuft – auch am Bindestrich („Container-Import“), den der Browser sonst trennt */
  function wortGebrochen(el) {
    const t = el.firstChild;
    if (!t || t.nodeType !== 3) return false;
    for (const m of t.textContent.matchAll(/\S+/g)) {
      const r = document.createRange(); r.setStart(t, m.index); r.setEnd(t, m.index + m[0].length);
      if (new Set([...r.getClientRects()].map((q) => Math.round(q.top))).size > 1) return true;
    }
    return false;
  }
  function namenEinpassen() {
    for (const el of document.querySelectorAll('#db-bereich .db-name')) {
      el.style.fontSize = ''; el.classList.remove('db-name-umbruch');
      const basis = parseFloat(getComputedStyle(el).fontSize), min = Math.max(12, basis * .75);
      const zuBreit = () => el.scrollWidth > el.clientWidth + 1 || wortGebrochen(el);
      let g = basis;
      while (zuBreit() && g > min) { g = Math.max(min, g - .5); el.style.fontSize = g + 'px'; }
      if (zuBreit()) el.classList.add('db-name-umbruch');
    }
  }

  let breite = 0;
  function einpassen() { breite = $('#db-grid').clientWidth; namenEinpassen(); }
  // Neu einpassen, wenn sich die Breite ändert (Fenster, Drehen) und sobald die Schrift geladen ist
  new ResizeObserver(() => { if ($('#db-grid').clientWidth !== breite && $('#db-grid .db-tile')) einpassen(); }).observe($('#db-grid'));
  if (document.fonts) document.fonts.ready.then(() => { if ($('#db-grid .db-tile')) einpassen(); });

  /* Begrüßung nach Tageszeit (Uhr des Geräts) mit Vornamen und Datum, z. B. „Guten Tag, Erika“ · „Donnerstag, 22. Oktober“ */
  function gruss(stunde) {
    if (stunde >= 5 && stunde < 11) return 'Guten Morgen';
    if (stunde >= 11 && stunde < 18) return 'Guten Tag';
    return 'Guten Abend';
  }
  window.STAFL_GRUSS = gruss;   // für die Tests (reine Funktion)
  /* Vorname = erster Namensteil ohne Titel („Dr. Erika Editor“ → „Erika“); ohne Namen nur der Gruß */
  function vorname(name) {
    return String(name || '').trim().split(/\s+/).find((t) => t && !t.endsWith('.')) || '';
  }
  function begruessung(name) {
    const jetzt = new Date(), v = vorname(name);
    $('#db-datum').textContent = jetzt.toLocaleDateString('de-DE', { weekday: 'long', day: 'numeric', month: 'long' });
    $('#db-titel').textContent = gruss(jetzt.getHours()) + (v ? `, ${v}` : '');
  }

  function fehler(text) {
    R.entfernen();
    $('#db-login').hidden = true; $('#db-bereich').hidden = true;
    $('#db-err').hidden = false; $('#db-err').textContent = text;
  }

  function zeigeAnmeldung(ziel) {
    R.entfernen();
    if (ziel) $('#db-login a').setAttribute('href', ziel);
    $('#db-login').hidden = false; $('#db-bereich').hidden = true;
  }

  async function abmelden() {
    const r = await api('logout', {});
    // Zentrale Anmeldung (Keycloak-Host): auch bei Keycloak abmelden – beendet die Anmeldung für alle Anwendungen
    if (typeof r.data.abmelden === 'string' && r.data.abmelden.startsWith('/oidc/')) { location.replace(r.data.abmelden); return; }
    zeigeAnmeldung();
  }

  async function laden() {
    const st = await api('status');
    // Keycloak-Host: zentrale Sitzung abgelaufen (401 vom Webserver, kein JSON) → Anmelden = Seite neu laden
    if (st.status === 401 && !st.json) { zeigeAnmeldung('./'); return; }
    // Zweiter Faktor für dieses Konto vorgeschrieben: zweite Stufe bei Keycloak, danach zurück auf diese Seite
    if (st.status === 403 && st.data.code === 'reauth_required' && typeof st.data.anmelden === 'string' && st.data.anmelden.startsWith('/oidc/')) {
      location.assign(st.data.anmelden + encodeURIComponent(location.href)); return;
    }
    // Angemeldet bei Keycloak, aber hier kein (aktives) Mitarbeiterkonto: Hinweis statt Anmeldemaske
    if (st.status === 403 && st.data.error) { fehler(st.data.error); return; }
    if (st.status !== 200 || !st.data.loggedIn) { zeigeAnmeldung(); return; }
    csrf = st.data.csrf || '';
    if (window.STAFL_THEME) { window.STAFL_THEME.konto(st.data.user, csrf, API); themaKnopf(); }   // Hell/Dunkel am Konto (theme.js)
    const nutzer = st.data.user || {};
    const heute = api('start_heute').catch(() => ({ status: 0, data: {} }));   // parallel zur Modulübersicht
    const r = await api('module_status');
    if (r.status === 401) { zeigeAnmeldung(r.json ? '' : './'); return; }
    if (r.status !== 200 || !r.data.ok) { fehler(r.data.error || `Die Anwendungen konnten nicht geladen werden (${r.status}).`); return; }
    S.module = r.data.module || [];
    S.alle = Object.fromEntries(S.module.map((m) => [m.id, m]));
    $('#db-login').hidden = true; $('#db-bereich').hidden = false;
    R.zeichnen({ module: S.module, aktiv: 'start', nutzer, start: './', abmelden });
    begruessung(nutzer.name || nutzer.username || '');
    notfallHinweis(r.data.notfall);
    hinweiseZeigen();
    // Platzhalter, bis die Favoriten am Konto bekannt sind (kein Springen von der Standardauswahl zur eigenen)
    $('#db-grid').innerHTML = '<div class="db-tile db-platzhalter" aria-hidden="true"></div>'.repeat(FAV_STANDARD);
    const h = await heute;
    S.heute = h.status === 200 && h.data.ok ? h.data : null;
    if (S.heute) S.favoriten = S.heute.favoriten;
    R.zahlen(S.heute ? S.heute.zahlen : null);
    unterzeile();
    favoritenZeigen();
    heuteZeigen();
    aktionenZeigen();
    zuletztZeigen();
  }

  /* Notfallmodus (Modul Sicherheit): Hinweis über den Kacheln – Einzelheiten nur für Administratoren und Berechtigte */
  function notfallHinweis(n) {
    const el = $('#db-notfall');
    el.hidden = !n;
    if (!n) return;
    const seit = new Date(n.seit).toLocaleString('de-DE', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
    el.innerHTML = n.grund !== undefined
      ? `<strong>Notfallmodus aktiv</strong> seit ${esc(seit)} Uhr${n.von ? ` · ausgelöst von ${esc(n.von)}` : ''}. Kunden sehen Wartung, Mitarbeiter ohne Administratorrolle sind gesperrt.`
      : '<strong>Anwendungen vorübergehend gesperrt.</strong> Wegen einer Sicherheitsmaßnahme ist der Zugriff gerade nicht möglich. Bitte wenden Sie sich an einen Administrator.';
  }

  /* Schnellzugriff (Blitz): öffnet die Suche des Rahmens – Anwendungen und Schnellaktionen */
  $('#db-schnell').addEventListener('click', () => R.sucheOeffnen());

  /* Hell/Dunkel wie auf der Angebotsseite (gleicher Speicherschlüssel, theme.js setzt es vor dem ersten Zeichnen) */
  const dunkel = () => document.documentElement.getAttribute('data-theme') === 'dark'
    || (!document.documentElement.getAttribute('data-theme') && matchMedia('(prefers-color-scheme: dark)').matches);
  function themaKnopf() {
    const b = $('#db-theme'), d = dunkel();
    b.innerHTML = icon(d ? 'sun' : 'moon');
    b.setAttribute('aria-label', d ? 'Helles Design einschalten' : 'Dunkles Design einschalten');
  }
  $('#db-theme').addEventListener('click', () => {
    const neu = dunkel() ? 'light' : 'dark';
    document.documentElement.setAttribute('data-theme', neu);
    try { localStorage.setItem('wochenangebot.theme', JSON.stringify(neu)); } catch { /* ohne Speicher */ }
    themaKnopf();
  });
  /* Einfache Darstellung (theme.js): an/aus, gespeichert am Konto; Hinweis unter der Begrüßung, solange sie an ist */
  function darstellungKnopf() {
    const D = window.STAFL_DARSTELLUNG, b = $('#db-darstellung');
    if (!D) { b.hidden = true; return; }
    const an = D.einfach();
    b.setAttribute('aria-pressed', String(an));
    b.setAttribute('aria-label', an ? 'Einfache Darstellung ausschalten' : 'Einfache Darstellung einschalten (für Remote-Desktop)');
    b.title = an ? 'Einfache Darstellung ist an – Effekte wieder einschalten' : 'Einfache Darstellung für Remote-Desktop einschalten';
    const h = $('#db-darstellung-hinweis');
    h.hidden = !an;
    h.textContent = !an ? '' : D.wahl() === 'einfach' ? 'Einfache Darstellung ist an (Ihre Wahl) – ruhiger und flüssiger, z. B. über Remote-Desktop.'
      : 'Einfache Darstellung ist an – automatisch, weil dieser Computer ohne Grafikkarte zeichnet (z. B. Remote-Desktop).';
  }
  $('#db-darstellung').addEventListener('click', () => {
    const neu = !window.STAFL_DARSTELLUNG.einfach();
    if (window.STAFL_THEME) window.STAFL_THEME.darstellung(neu); else window.STAFL_DARSTELLUNG.setzen(neu);
    darstellungKnopf();
  });
  document.addEventListener('stafl-darstellung', darstellungKnopf);

  themaKnopf();
  darstellungKnopf();
  laden().catch(() => fehler('Keine Verbindung zum Server.'));
})();
