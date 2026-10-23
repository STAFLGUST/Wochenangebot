/* STAFL-Plattform – Einmalcode-Felder der Anmeldeseite (Felder mit data-stafl-otp: Anmeldung und Einrichtung) und Schutz
   gegen doppelt abgeschickte Anmeldeformulare (einmalAbsenden, unten).
   Keycloak vergleicht den Code genau so, wie er ankommt: „123 456“ (so zeigen viele Apps den Code an) oder ein Code mit
   Zeilenumbruch aus der Zwischenablage gilt dort als falsch und zählt als Fehlversuch. Das Skript entfernt deshalb beim
   Tippen, Einfügen und automatischen Ausfüllen alles außer Ziffern. Nur Darstellung/Eingabe – die Prüfung des Codes, die
   Sperre nach Fehlversuchen und die Einmalcode-Richtlinie bleiben unverändert bei Keycloak. Ohne Skript verhindert das
   Muster im Feld (pattern) das Absenden eines Codes mit Leerzeichen. */
(function () {
  'use strict';

  function nurZiffern(wert) {
    // auch Ziffern anderer Schreibweisen (z. B. Vollbreite aus manchen Tastaturen) als 0–9
    return String(wert || '').normalize('NFKC').replace(/\D+/g, '');
  }

  function bereinigen(feld) {
    var neu = nurZiffern(feld.value);
    if (neu !== feld.value) {
      feld.value = neu;
    }
  }

  function einrichten(feld) {
    if (feld.dataset.staflOtpBereit) {
      return;
    }
    feld.dataset.staflOtpBereit = '1';
    feld.addEventListener('input', function () { bereinigen(feld); });
    feld.addEventListener('change', function () { bereinigen(feld); });
    feld.addEventListener('blur', function () { bereinigen(feld); });
    feld.addEventListener('paste', function (e) {
      var daten = e.clipboardData && e.clipboardData.getData('text');
      if (typeof daten !== 'string') {
        return;   // Browser ohne Zugriff: das input-Ereignis danach bereinigt
      }
      e.preventDefault();
      var start = feld.selectionStart == null ? feld.value.length : feld.selectionStart;
      var ende = feld.selectionEnd == null ? feld.value.length : feld.selectionEnd;
      var wert = feld.value.slice(0, start) + nurZiffern(daten) + feld.value.slice(ende);
      feld.value = nurZiffern(wert);
      feld.dispatchEvent(new Event('input', { bubbles: true }));
    });
    // Vor dem Absenden noch einmal (Ausfüllen durch Passwortmanager ohne Ereignis); Prüfung des Musters erst danach
    if (feld.form) {
      feld.form.addEventListener('submit', function () { bereinigen(feld); }, true);
      var knopf = feld.form.querySelector('[type=submit]');
      if (knopf) {
        knopf.addEventListener('click', function () { bereinigen(feld); }, true);
      }
    }
    bereinigen(feld);
  }

  /* Jedes Anmeldeformular nur einmal absenden. Keycloak sperrt ein Konto 60 Sekunden, wenn zwei Fehlversuche weniger als
     eine Sekunde auseinanderliegen (quickLoginCheckMilliSeconds) – ein doppelt abgeschicktes Formular (Eingabetaste und
     Klick, zweimal Eingabe, Passwortmanager plus Klick) löste das aus; danach galt auch der richtige Code als falsch.
     Zurück-Taste (Seite aus dem Zwischenspeicher) und ein abgebrochener Seitenwechsel geben das Formular wieder frei. */
  function einmalAbsenden(form) {
    if (form.dataset.staflEinmal) {
      return;
    }
    form.dataset.staflEinmal = '1';
    form.addEventListener('submit', function (e) {
      if (form.dataset.staflGesendet) {
        e.preventDefault();
        e.stopImmediatePropagation();
        return;
      }
      form.dataset.staflGesendet = '1';
      setTimeout(function () { delete form.dataset.staflGesendet; }, 8000);
    });
  }

  function freigeben() {
    Array.prototype.forEach.call(document.querySelectorAll('form[data-stafl-gesendet]'), function (f) {
      delete f.dataset.staflGesendet;
      Array.prototype.forEach.call(f.querySelectorAll('[type=submit]'), function (k) { k.disabled = false; });
    });
  }

  function start() {
    Array.prototype.forEach.call(document.querySelectorAll('input[data-stafl-otp]'), einrichten);
    Array.prototype.forEach.call(document.querySelectorAll('form[method=post], form[method=POST]'), einmalAbsenden);
  }

  window.addEventListener('pageshow', function (e) {
    if (e.persisted) {
      freigeben();
    }
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
