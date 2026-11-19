/* STAFL-Plattform · Angebot · „Export für WinAB“ im Bereich Import (Auftrag des Inhabers 05.11.2026; seit 19.11.2026 dort
   statt in der Werkzeugleiste des Wochenangebots, Datei immer „ImportPreise.csv“).
   Zwei Einträge, jeder mit seiner Woche: der Entwurf (Preise der neuen Woche, bevor sie veröffentlicht sind) und der
   veröffentlichte Stand. Lädt das Wochenangebot als CSV für WinAB herunter (Artikelnummer;Preis, je Nummer der höchste Preis).
   Datei, Dateiname und Zahlen erzeugt der Server (Aktion angebot_winab_export, module/angebot/winab-export.php) – nur mit
   dem Recht „angebot.winab_export“ und dem Modulzugang Angebot (GR-103). Angezeigt werden die Einträge von der Importzentrale
   (admin-import.js, Gruppe „Export“, window.WA.importExporte) nur mit beidem. Die Rückmeldung nennt Stand und Woche der Datei.
   Wird von admin/index.html nach admin.js geladen. */
(function () {
  'use strict';
  const W = window.WA;
  if (!W) return;
  async function laden(entwurf) {
    try {
      if (entwurf) await W.angebot.druck.bereit();   // wie vor dem Drucken: letzte Eingabe erst speichern – exportiert wird der gespeicherte Entwurf
      const r = await W.api('angebot_winab_export', { body: { entwurf } });
      const url = URL.createObjectURL(new Blob([r.csv], { type: 'text/csv' }));
      const a = Object.assign(document.createElement('a'), { href: url, download: r.datei });
      document.body.append(a); a.click(); a.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      const extra = [r.doppelt ? `${W.fmtInt.format(r.doppelt)}× doppelt – höherer Preis genommen` : '', r.ohnePreis ? `${W.plural(r.ohnePreis, 'Artikel', 'Artikel')} ohne Preis ausgelassen` : '',
        r.entwurf ? 'noch nicht veröffentlicht' : W.pendingCount() ? 'unveröffentlichte Änderungen im Entwurf sind nicht enthalten' : ''].filter(Boolean);
      W.toast(`${r.datei} heruntergeladen: ${W.plural(r.anzahl, 'Artikel', 'Artikel')} aus dem ${r.entwurf ? 'Entwurf' : 'veröffentlichten Wochenangebot'}${r.woche ? ' ' + r.woche : ''}${extra.length ? ' (' + extra.join('; ') + ')' : ''}.`, 7000);
    } catch (ex) {
      if (!ex.wartung && ex.status !== 401) W.toast(ex.message || String(ex), 7000);
    }
  }
  /* Name und Kurztext liest die Importzentrale bei jedem Zeichnen der Liste – daher immer mit der aktuellen Woche */
  const eintrag = (entwurf) => ({
    format: 'CSV', recht: ['angebot.winab_export', 'angebot.zugang'],   // wie der Server: Recht und Modulzugang
    get name() { const w = W.angebot.wochen()[entwurf ? 'entwurf' : 'veroeffentlicht']; return `Export für WinAB – ${entwurf ? 'Entwurf' : 'Veröffentlicht'}${w ? ` (${w})` : ''}`; },
    get kurz() {
      if (!entwurf) return 'Datei „ImportPreise.csv“ mit den Preisen, die die Kunden sehen';
      const n = W.pendingCount();
      return `Datei „ImportPreise.csv“ mit den Preisen des Entwurfs – ${n ? W.plural(n, 'Änderung', 'Änderungen') + ' noch nicht veröffentlicht' : 'entspricht dem veröffentlichten Stand'}`;
    },
    beschreibung: `${entwurf ? 'Gespeicherter Entwurf des Wochenangebots' : 'Veröffentlichtes Wochenangebot'} als CSV für WinAB herunterladen: Artikelnummer;Preis – steht ein Artikel mehrfach im Angebot, der höhere Preis`,
    start: () => laden(entwurf),
  });
  W.importExporte = W.importExporte || {};
  W.importExporte.winab_entwurf = eintrag(true);
  W.importExporte.winab = eintrag(false);
})();
