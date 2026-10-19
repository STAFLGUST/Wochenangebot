/* Web-App: Offline-Speicher (sw.js) anmelden und Hinweis „Als App auf den Home-Bildschirm“.
   Der Hinweis erscheint nur auf Handy/Tablet, nicht in der bereits installierten Web-App und nach „Schließen“ nie wieder. */
(function () {
  'use strict';
  if ('serviceWorker' in navigator && window.isSecureContext) {
    window.addEventListener('load', function () { navigator.serviceWorker.register('sw.js').catch(function () { /* ohne Offline-Speicher weiter */ }); });
  }
  var installiert = (window.matchMedia && window.matchMedia('(display-mode: standalone)').matches) || window.navigator.standalone === true;
  if (installiert) { document.documentElement.classList.add('is-webapp'); return; }

  var KEY = 'wochenangebot.webappHinweis';
  try { if (localStorage.getItem(KEY) === 'aus') return; } catch (e) { /* Speicher gesperrt: Hinweis trotzdem zeigen */ }
  var box = document.getElementById('webapp-hint');
  if (!box) return;
  var touch = window.matchMedia && window.matchMedia('(pointer: coarse)').matches;
  var ua = navigator.userAgent;
  var ios = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  var SYMBOL = '<svg class="i sm" viewBox="0 0 24 24" aria-hidden="true" style="vertical-align:-3px"><path d="M12 3v12M8 7l4-4 4 4" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/><path d="M6 11H5a1 1 0 0 0-1 1v8a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-8a1 1 0 0 0-1-1h-1" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>';

  function zeigen(inhalt) {
    box.innerHTML = '<img src="assets/icons/apple-touch-icon.png" width="36" height="36" alt="">'
      + '<div class="wh-text">' + inhalt + '</div>'
      + '<button type="button" class="btn icon ghost sm" data-wh="aus" aria-label="Hinweis schließen" title="Nicht mehr anzeigen"><svg class="i sm" aria-hidden="true"><use href="#i-x"/></svg></button>';
    box.hidden = false;
  }
  box.addEventListener('click', function (e) {
    var b = e.target.closest('[data-wh]');
    if (!b) return;
    if (b.dataset.wh === 'installieren' && aufforderung) {
      aufforderung.prompt();
      aufforderung.userChoice.then(function () { aufforderung = null; box.hidden = true; });
      return;
    }
    try { localStorage.setItem(KEY, 'aus'); } catch (e2) { /* nur für diesen Besuch */ }
    box.hidden = true;
  });

  var aufforderung = null;
  if (ios && touch) {
    zeigen('<strong>Als App aufs ' + (/iPad/.test(ua) || navigator.platform === 'MacIntel' ? 'iPad' : 'iPhone') + ':</strong> auf ' + SYMBOL + ' „Teilen“ tippen und „Zum Home-Bildschirm“ wählen.');
  }
  // Android/Chrome: eigene Installationsabfrage des Browsers
  window.addEventListener('beforeinstallprompt', function (e) {
    if (!touch) return;
    e.preventDefault();
    aufforderung = e;
    zeigen('<strong>Wochenangebot als App:</strong> mit Symbol auf dem Startbildschirm, auch offline lesbar. '
      + '<button type="button" class="btn sm primary" data-wh="installieren">Installieren</button>');
  });
  window.addEventListener('appinstalled', function () { box.hidden = true; });
})();
