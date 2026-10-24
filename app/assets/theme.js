/* Hell/Dunkel-Einstellung vor dem ersten Zeichnen anwenden (ohne Inline-Skript, wegen Content-Security-Policy) */
try { var t = localStorage.getItem('wochenangebot.theme'); if (t) { t = JSON.parse(t); if (t === 'dark' || t === 'light') document.documentElement.setAttribute('data-theme', t); } } catch (e) { /* ignorieren */ }

/* Hell/Dunkel gilt für das Mitarbeiterkonto auf jedem Host der Plattform (Dashboard, Angebot, Verwaltung, Bestand, HR, CRM).
   Jeder Host hat eigenen Browser-Speicher (eigene Subdomain, keine gemeinsamen Cookies – GR-108); deshalb steht die Wahl am
   Konto (Aktion theme_save) und jede Seite übernimmt sie nach der Anmeldung aus dem Status:
     STAFL_THEME.konto(user, csrf, api)   – nach dem Status-Abruf (user.theme: 'light' | 'dark' | '' = wie das Gerät)
   Danach speichert jeder Wechsel über den Knopf der Seite (setzt data-theme) die Wahl am Konto mit. Seiten ohne Anmeldung
   (Kundenseite, Anmeldeseite) bleiben bei der Einstellung des Geräts bzw. dieses Browsers. */
(function () {
  var root = document.documentElement, ziel = null, eigen = false;
  function lokal(wert) { try { if (wert) localStorage.setItem('wochenangebot.theme', JSON.stringify(wert)); else localStorage.removeItem('wochenangebot.theme'); } catch (e) { /* ohne Speicher */ } }
  function setzen(wert) {
    eigen = true;
    if (wert === 'dark' || wert === 'light') root.setAttribute('data-theme', wert); else root.removeAttribute('data-theme');
    lokal(wert);
    eigen = false;
    try { document.dispatchEvent(new CustomEvent('stafl-theme', { detail: wert || '' })); } catch (e) { /* alte Browser */ }
  }
  function merken(wert) {
    if (!ziel || !ziel.csrf) return;
    try {
      fetch(ziel.api + '?action=theme_save', { method: 'POST', credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': ziel.csrf }, body: JSON.stringify({ theme: wert || '' }) }).catch(function () { /* nächster Versuch beim nächsten Wechsel */ });
    } catch (e) { /* ignorieren */ }
  }
  try {
    new MutationObserver(function () {
      if (eigen || !ziel) return;
      var wert = root.getAttribute('data-theme') || '';
      if (wert === ziel.theme) return;
      ziel.theme = wert;
      merken(wert);
    }).observe(root, { attributes: true, attributeFilter: ['data-theme'] });
  } catch (e) { /* ohne Beobachter: Wahl bleibt nur in diesem Browser */ }
  window.STAFL_THEME = {
    konto: function (user, csrf, api) {
      if (!user) return;
      var wert = user.theme === 'dark' || user.theme === 'light' ? user.theme : '';
      ziel = { csrf: csrf || '', api: api || '../api/', theme: wert };
      // Konto ohne eigene Wahl: bisherige Wahl dieses Browsers übernehmen und am Konto speichern (einmalig)
      var hier = root.getAttribute('data-theme') || '';
      if (!wert && hier) { ziel.theme = hier; merken(hier); return; }
      if (wert !== hier) setzen(wert);
    },
    setzen: setzen,
  };
})();

/* Waagerecht scrollende Leisten (.stafl-streifen): Klassen mehr-l / mehr-r, solange links bzw. rechts noch Inhalt folgt –
   app.css blendet den Rand dann weich aus. Ohne Animation (Tests und Bewegungsreduktion unberührt). */
(function () {
  function pruefen(el) {
    var mehrL = el.scrollLeft > 2, mehrR = el.scrollLeft + el.clientWidth < el.scrollWidth - 2;
    el.classList.toggle('mehr-l', mehrL); el.classList.toggle('mehr-r', mehrR);
  }
  var beobachtet = typeof WeakSet === 'function' ? new WeakSet() : null;
  var ro = typeof ResizeObserver === 'function' ? new ResizeObserver(function (e) { e.forEach(function (x) { pruefen(x.target); }); }) : null;
  function anmelden() {
    var els = document.querySelectorAll('.stafl-streifen');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (beobachtet && beobachtet.has(el)) { pruefen(el); continue; }
      if (beobachtet) beobachtet.add(el);
      el.addEventListener('scroll', function () { pruefen(this); }, { passive: true });
      if (ro) ro.observe(el);
      pruefen(el);
    }
  }
  function start() {
    anmelden();
    // Inhalt der Leisten entsteht teils erst nach dem Laden (Schnellauswahl, sichtbare Reiter): Änderungen mitprüfen
    // – höchstens einmal je Bild (große Tabellen ändern sich oft), nur Leisten, keine ganze Seite
    var geplant = false;
    try { new MutationObserver(function () { if (geplant) return; geplant = true; requestAnimationFrame(function () { geplant = false; anmelden(); }); })
      .observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden'] }); } catch (e) { /* ohne Beobachter */ }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
