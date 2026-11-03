/* Hell/Dunkel-Einstellung vor dem ersten Zeichnen anwenden (ohne Inline-Skript, wegen Content-Security-Policy) */

/* Einfache Darstellung (Auftrag des Inhabers 02.11.2026): für Remote-Desktop (RDP) und virtuelle Maschinen ohne Grafikkarte.
   Dort zeichnet der Browser mit dem Prozessor – Unschärfe (backdrop-filter, „Glas“), weiche Farbflächen und Bewegungen kosten
   bei jedem Scrollen ein Vielfaches und lassen sich über RDP schlecht übertragen. data-darstellung="einfach" an <html> schaltet
   sie für alle Seiten ab (app.css, admin.css). Vor dem ersten Zeichnen:
     - Wahl am Konto (STAFL_THEME.konto aus dem Status: user.darstellung 'einfach' | 'effekte' | '' = automatisch), je Host im
       Browser gemerkt, damit die Seite nicht erst mit Glas erscheint;
     - sonst automatisch: Systemeinstellung „Transparenz reduzieren“ oder der Browser zeichnet ohne Grafikkarte (WebGL nur in
       Software bzw. gar nicht). Die Erkennung läuft je Host höchstens einmal in 7 Tagen; unter Automatisierung
       (navigator.webdriver, z. B. die Tests) nicht – dort gilt die Wahl am Konto. */
(function () {
  var root = document.documentElement, K_WAHL = 'stafl.darstellung', K_GRAFIK = 'stafl.grafik', GUELTIG = 7 * 864e5;
  function lesen(k) { try { return JSON.parse(localStorage.getItem(k) || 'null'); } catch (e) { return null; } }
  function schreiben(k, v) { try { if (v === null || v === '') localStorage.removeItem(k); else localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* ohne Speicher */ } }
  /* Zeichnet der Browser ohne Grafikkarte? (WebGL nicht verfügbar, nur mit großem Leistungsverlust oder als Software-Renderer) */
  function softwareGrafik() {
    try {
      var c = document.createElement('canvas');
      var gl = c.getContext('webgl', { failIfMajorPerformanceCaveat: true }) || c.getContext('experimental-webgl', { failIfMajorPerformanceCaveat: true });
      if (!gl) return true;
      var info = gl.getExtension('WEBGL_debug_renderer_info');
      var name = info ? String(gl.getParameter(info.UNMASKED_RENDERER_WEBGL) || '') : '';
      var weg = gl.getExtension('WEBGL_lose_context');
      if (weg) weg.loseContext();
      return /swiftshader|llvmpipe|softpipe|software|basic render|microsoft basic/i.test(name);
    } catch (e) { return false; }
  }
  var auto = null;
  function automatisch() {
    if (auto !== null) return auto;
    try { if (window.matchMedia && matchMedia('(prefers-reduced-transparency: reduce)').matches) return (auto = true); } catch (e) { /* alte Browser */ }
    if (navigator.webdriver) return (auto = false);
    var g = lesen(K_GRAFIK);
    if (!g || typeof g.software !== 'boolean' || !(Date.now() - (g.t || 0) < GUELTIG)) { g = { software: softwareGrafik(), t: Date.now() }; schreiben(K_GRAFIK, g); }
    return (auto = g.software);
  }
  var wahl = lesen(K_WAHL);
  if (wahl !== 'einfach' && wahl !== 'effekte') wahl = '';
  function anwenden() {
    var einfach = wahl === 'einfach' || (wahl === '' && automatisch());
    if (einfach) root.setAttribute('data-darstellung', 'einfach'); else root.removeAttribute('data-darstellung');
    try { document.dispatchEvent(new CustomEvent('stafl-darstellung', { detail: { einfach: einfach, wahl: wahl } })); } catch (e) { /* alte Browser */ }
  }
  anwenden();
  window.STAFL_DARSTELLUNG = {
    einfach: function () { return root.getAttribute('data-darstellung') === 'einfach'; },
    automatisch: automatisch,
    wahl: function () { return wahl; },
    /* Wahl vom Konto übernehmen (ohne zu speichern) */
    konto: function (w) { w = w === 'einfach' || w === 'effekte' ? w : ''; if (w === wahl) return; wahl = w; schreiben(K_WAHL, wahl); anwenden(); },
    /* Umschalten auf diesem Gerät: entspricht die neue Darstellung der Erkennung, gilt wieder „automatisch“ (''). Gibt die Wahl zurück. */
    setzen: function (einfach) { wahl = !!einfach === automatisch() ? '' : (einfach ? 'einfach' : 'effekte'); schreiben(K_WAHL, wahl); anwenden(); return wahl; },
  };
})();
try { var t = localStorage.getItem('wochenangebot.theme'); if (t) { t = JSON.parse(t); if (t === 'dark' || t === 'light') document.documentElement.setAttribute('data-theme', t); } } catch (e) { /* ignorieren */ }

/* Fenster (<dialog>) auf allen Seiten gleich (Vorgabe des Inhabers 02.11.2026): Ein Klick neben das Fenster schließt es nie –
   geschlossen wird mit Escape, dem Schließen-Knopf oder den Knöpfen des Fensters. Läuft als Erstes (Erfassungsphase am
   window, dieses Skript lädt vor allen anderen) und gilt damit auch für Fenster, die ein Skript erst später erzeugt. Ein
   Klick mit dem Ziel <dialog> selbst ist immer einer daneben (Hintergrund) oder auf den leeren Rand, nie auf Inhalt. */
window.addEventListener('click', function (e) {
  var d = e.target;
  if (d && d.nodeName === 'DIALOG' && d.open) e.stopImmediatePropagation();
}, true);

/* Getippte, noch nicht gespeicherte Eingaben gehen nicht mit einem Escape verloren (Vorgabe des Inhabers 02.11.2026: Escape
   schließt jedes Fenster – aber einheitlich): Wurde in einem Formular eines offenen Fensters getippt, zeigt das erste
   Escape einen Hinweis, erst das zweite schließt; nach erfolgreichem Speichern wieder sofort. „Abbrechen“ und ×
   schließen weiter sofort. Nicht für Anmelde- und
   Passwortformulare, Suchfelder und Fenster mit data-ohne-warnung (speichern sofort selbst, z. B. „Artikel bearbeiten“,
   oder haben eine eigene Rückfrage). Gemeinsam für alle Seiten; Attribute data-geaendert/data-warnung wie im Eingabebereich. */
(function () {
  var HINWEIS = 'Die Eingaben sind noch nicht gespeichert – erneut Escape verwirft sie.';
  var FELD = 'textarea, select, input:not([type=checkbox]):not([type=radio]):not([type=search]):not([type=file]):not([type=hidden]):not([type=button]):not([type=submit])';
  function zaehlt(d, t) {
    if (!d || !d.open || d.hasAttribute('data-ohne-warnung') || t.closest('[data-ohne-warnung]')) return false;
    var f = t.closest('form');
    if (f && d.contains(f)) return !f.querySelector('input[type=password]');
    return t.nodeName === 'TEXTAREA' || !!t.closest('[data-mit-warnung]');   // ohne <form>: Notizen, Bemerkungen, markierte Felder
  }
  var el = null, uhr = 0;
  function zeigen() {
    if (!el) {
      el = document.createElement('div');
      el.id = 'stafl-hinweis'; el.className = 'stafl-toast'; el.setAttribute('role', 'status'); el.setAttribute('aria-live', 'polite');
      document.body.appendChild(el);
    }
    el.textContent = HINWEIS;
    try {   // über dem offenen Fenster (oberste Ebene), wie die übrigen Hinweise
      if (typeof el.showPopover === 'function') {
        if (!el.hasAttribute('popover')) { el.setAttribute('popover', 'manual'); el.setAttribute('data-stafl-oben', ''); }
        if (el.matches(':popover-open')) el.hidePopover();
        el.showPopover();
      }
    } catch (x) { /* ohne Popover: wie ein normaler Hinweis */ }
    el.classList.add('zeigen');
    clearTimeout(uhr); uhr = setTimeout(function () { el.classList.remove('zeigen'); }, 4000);
  }
  window.addEventListener('input', function (e) {
    var t = e.target;
    if (!t || !t.matches || !t.matches(FELD)) return;
    var d = t.closest('dialog');
    if (!zaehlt(d, t)) return;
    d.setAttribute('data-geaendert', '1');
    (d.__staflFelder = d.__staflFelder || []).indexOf(t) < 0 && d.__staflFelder.push(t);
  }, true);
  window.addEventListener('close', function (e) {
    var d = e.target;
    if (d && d.nodeName === 'DIALOG') { d.removeAttribute('data-geaendert'); d.removeAttribute('data-warnung'); d.__staflFelder = null; if (el) el.classList.remove('zeigen'); }
  }, true);
  // Gespeichert: Seiten, deren Fenster nach erfolgreichem Speichern offen bleibt, melden das (STAFL_FENSTER.gespeichert);
  // Abschicken allein zählt nicht – schlägt das Speichern fehl, bleiben die Eingaben geschützt. Zurücksetzen des Formulars
  // (reset) und neuer Inhalt (die getippten Felder sind fort) heben den Schutz ebenfalls auf.
  function frei(d) { if (d) { d.removeAttribute('data-geaendert'); d.removeAttribute('data-warnung'); d.__staflFelder = null; } }
  window.STAFL_FENSTER = { gespeichert: frei };
  window.addEventListener('reset', function (e) { frei(e.target && e.target.closest ? e.target.closest('dialog') : null); }, true);
  window.addEventListener('cancel', function (e) {
    var d = e.target;
    if (!d || d.nodeName !== 'DIALOG' || !d.hasAttribute('data-geaendert') || d.hasAttribute('data-warnung') || d.hasAttribute('data-busy')) return;
    // Hat die Seite den Inhalt inzwischen ersetzt (nächster Schritt, „Gespeichert“), stehen die getippten Felder nicht mehr da
    var felder = (d.__staflFelder || []).filter(function (f) { return f.isConnected && d.contains(f); });
    if (d.__staflFelder && !felder.length) { d.removeAttribute('data-geaendert'); d.__staflFelder = null; return; }
    e.preventDefault(); e.stopImmediatePropagation();
    d.setAttribute('data-warnung', '1');
    zeigen();
  }, true);
})();

/* Aufklappmenüs aus <details data-menue> (Filter „Monate“, „Vertreter“, „Wann“) bedienen sich wie jedes Menü: Escape
   schließt (Fokus zurück auf den Titel), ein Klick außerhalb ebenso. Ein Klick auf ein Element, das die Seite inzwischen
   neu gezeichnet hat (nicht mehr im Dokument), zählt nicht als „außerhalb“. */
document.addEventListener('keydown', function (e) {
  if (e.key !== 'Escape') return;
  var m = document.querySelector('details[data-menue][open]');
  if (!m) return;
  m.open = false;
  var s = m.querySelector('summary');
  if (s) s.focus();
  e.preventDefault();
});
document.addEventListener('click', function (e) {
  var t = e.target;
  if (!t || !t.isConnected) return;
  var offen = document.querySelectorAll('details[data-menue][open]');
  for (var i = 0; i < offen.length; i++) if (!offen[i].contains(t)) offen[i].open = false;
});
/* Aufgeklappte Liste ganz im Bild halten (am Handy ragte sie sonst rechts hinaus); „toggle“ steigt nicht auf, daher Erfassung */
document.addEventListener('toggle', function (e) {
  var d = e.target;
  if (!d || !d.matches || !d.matches('details[data-menue]') || !d.open) return;
  var p = d.querySelector(':scope > :not(summary)');
  if (!p) return;
  p.style.left = ''; p.style.maxWidth = '';
  var W = document.documentElement.clientWidth, r = p.getBoundingClientRect();
  if (r.width > W - 16) { p.style.maxWidth = (W - 16) + 'px'; r = p.getBoundingClientRect(); }
  var schieben = r.right > W - 8 ? r.right - (W - 8) : 0;
  if (r.left - schieben < 8) schieben = r.left - 8;
  if (schieben) p.style.left = ((parseFloat(getComputedStyle(p).left) || 0) - schieben) + 'px';
}, true);

/* Fokus im Fenster: Manche Fenster setzen ihren Inhalt erst nach showModal() – dann stünde der Fokus außerhalb (Tastatur und
   Bildschirmleser fänden das Fenster nicht). Steht er nach dem Öffnen nicht im Fenster, geht er auf das erste bedienbare
   Element darin (sonst auf das Fenster selbst). Einen Fokus, den die Seite selbst setzt, lässt das unberührt. */
(function () {
  if (typeof HTMLDialogElement === 'undefined' || !HTMLDialogElement.prototype.showModal) return;
  var orig = HTMLDialogElement.prototype.showModal;
  var ZIEL = '[autofocus], input:not([type=hidden]):not([disabled]), select:not([disabled]), textarea:not([disabled]), button:not([disabled]), [href], [tabindex]:not([tabindex="-1"])';
  HTMLDialogElement.prototype.showModal = function () {
    var d = this, r = orig.apply(this, arguments);
    var pruefen = function () {
      if (!d.open || d.contains(document.activeElement)) return;
      var z = d.querySelector(ZIEL);
      if (z) z.focus(); else { if (!d.hasAttribute('tabindex')) d.setAttribute('tabindex', '-1'); d.focus(); }
    };
    if (typeof requestAnimationFrame === 'function') requestAnimationFrame(pruefen); else setTimeout(pruefen, 0);
    // Inhalt, der erst nach dem Laden kommt, ersetzt oft das fokussierte Element (Fokus fiele auf die Seite zurück):
    // solange das Fenster offen ist, nach jeder Änderung prüfen – nur wenn der Fokus verloren ist, nie während der Eingabe
    if (typeof MutationObserver === 'function' && !d.__staflFokus) {
      var mo = new MutationObserver(function () {
        var a = document.activeElement;
        if (d.open && (!a || a === document.body || !a.isConnected)) pruefen();
        // neue Fehlermeldung ([role=alert]) ins Bild holen – sonst stünde sie in langen Fenstern unten außer Sicht
        var meld = d.querySelectorAll('[role="alert"]');
        for (var i = 0; i < meld.length; i++) {
          var m = meld[i], t = (m.textContent || '').trim();
          if (t && t !== m.__staflText && m.offsetParent) { m.scrollIntoView({ block: 'nearest' }); }
          m.__staflText = t;
        }
      });
      mo.observe(d, { childList: true, subtree: true, characterData: true });
      d.__staflFokus = mo;
      d.addEventListener('close', function () { mo.disconnect(); d.__staflFokus = null; }, { once: true });
    }
    return r;
  };
})();

/* Hinweise (Toasts) über offenen Fenstern lesbar: Ein Fenster aus showModal() liegt in der obersten Ebene, alles andere
   darunter hinter dem abgedunkelten, unscharfen Hintergrund – ein Hinweis wie „Gespeichert“ wäre dort kaum lesbar. Deshalb
   liegt jeder Toast der Seite ([role=status] mit Klasse „toast“ bzw. „…-toast“) als Popover (manual: kein Schließen per
   Escape oder Klick) ebenfalls in der obersten Ebene und wird beim Öffnen eines Fensters erneut nach oben geholt. Sichtbar
   oder unsichtbar bleibt er wie bisher über die Klassen der Seite (opacity, pointer-events: none); app.css setzt die
   Popover-Vorgaben des Browsers zurück. Ohne Popover-Unterstützung bleibt alles wie bisher. */
(function () {
  if (typeof HTMLElement === 'undefined' || typeof HTMLElement.prototype.showPopover !== 'function') return;
  var SEL = '[role="status"].toast, [role="status"][class*="-toast"]';
  function oben() {
    var t = document.querySelectorAll(SEL);
    for (var i = 0; i < t.length; i++) {
      var el = t[i];
      try {
        if (!el.hasAttribute('popover')) { el.setAttribute('popover', 'manual'); el.setAttribute('data-stafl-oben', ''); }
        if (el.matches(':popover-open')) el.hidePopover();
        el.showPopover();
      } catch (e) { /* älterer Browser: Toast bleibt, wo er war */ }
    }
  }
  function start() {
    oben();
    try {
      new MutationObserver(function (m) {
        for (var i = 0; i < m.length; i++) { var d = m[i].target; if (d.nodeName === 'DIALOG' && d.open) { oben(); return; } }
      }).observe(document.body, { subtree: true, attributes: true, attributeFilter: ['open'] });
    } catch (e) { /* ohne Beobachter */ }
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();

/* Hell/Dunkel (und die einfache Darstellung) gilt für das Mitarbeiterkonto auf jedem Host der Plattform (Dashboard, Angebot, Verwaltung, Bestand, HR, CRM).
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
      if (window.STAFL_DARSTELLUNG) window.STAFL_DARSTELLUNG.konto(user.darstellung);   // einfache Darstellung am Konto
      // Konto ohne eigene Wahl: bisherige Wahl dieses Browsers übernehmen und am Konto speichern (einmalig)
      var hier = root.getAttribute('data-theme') || '';
      if (!wert && hier) { ziel.theme = hier; merken(hier); return; }
      if (wert !== hier) setzen(wert);
    },
    setzen: setzen,
    /* Einfache Darstellung umschalten und am Konto speichern (gilt dann auf jedem Host); gibt die Wahl zurück */
    darstellung: function (einfach) {
      if (!window.STAFL_DARSTELLUNG) return '';
      var w = window.STAFL_DARSTELLUNG.setzen(einfach);
      if (ziel && ziel.csrf) {
        try {
          fetch(ziel.api + '?action=theme_save', { method: 'POST', credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': ziel.csrf }, body: JSON.stringify({ darstellung: w }) }).catch(function () { /* bleibt in diesem Browser */ });
        } catch (e) { /* ignorieren */ }
      }
      return w;
    },
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
