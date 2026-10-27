/* Rücksprungseite der Bestätigung im eigenen Fenster (admin/bestaetigt.html): meldet dem Eingabebereich, dass die
   erneute Anmeldung bei der STAFL-Anmeldung abgeschlossen ist, und schließt das Fenster. Drei Wege, alle nur innerhalb
   desselben Ursprungs: BroadcastChannel, postMessage an das öffnende Fenster und ein localStorage-Ereignis. Die Meldung
   löst nur eine Wiederholung der Anfrage aus – ob die Aktion bestätigt ist, entscheidet allein der Server. */
(function () {
  'use strict';
  var nachricht = { typ: 'stafl-bestaetigt', t: Date.now() };
  try { var k = new BroadcastChannel('stafl-bestaetigung'); k.postMessage(nachricht); k.close(); } catch (e) { /* älterer Browser */ }
  try { if (window.opener && window.opener !== window) window.opener.postMessage(nachricht, location.origin); } catch (e) { /* kein Zugriff */ }
  try { localStorage.setItem('stafl-bestaetigung', String(nachricht.t)); localStorage.removeItem('stafl-bestaetigung'); } catch (e) { /* Speicher gesperrt */ }
  setTimeout(function () {
    try { window.close(); } catch (e) { /* nicht per Skript geöffnet */ }
    // Bleibt das Fenster offen (z. B. als Tab geöffnet): Hinweis anpassen
    setTimeout(function () {
      var t = document.getElementById('bst-text');
      if (t) t.textContent = 'Bestätigt. Sie können dieses Fenster schließen und im ursprünglichen Fenster weiterarbeiten.';
    }, 600);
  }, 400);
})();
