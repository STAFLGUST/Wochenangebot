/* STAFL-Plattform · Angebot · „Export für WinAB“ im Bereich Import (Auftrag des Inhabers 05.11.2026; seit 19.11.2026 dort
   statt in der Werkzeugleiste des Wochenangebots, Datei immer „ImportPreise.csv“).
   Lädt das veröffentlichte Wochenangebot als CSV für WinAB herunter (Artikelnummer;Preis, je Nummer der höchste Preis).
   Datei, Dateiname und Zahlen erzeugt der Server (Aktion angebot_winab_export, module/angebot/winab-export.php) – nur mit
   dem Recht „angebot.winab_export“ und dem Modulzugang Angebot (GR-103). Angezeigt wird der Eintrag von der Importzentrale
   (admin-import.js, Gruppe „Export“, window.WA.importExporte) nur mit beidem. Unveröffentlichte Änderungen im Entwurf sind nicht enthalten –
   das sagt die Rückmeldung. Wird von admin/index.html nach admin.js geladen. */
(function () {
  'use strict';
  const W = window.WA;
  if (!W) return;
  (W.importExporte = W.importExporte || {}).winab = {
    name: 'Export für WinAB', format: 'CSV', recht: ['angebot.winab_export', 'angebot.zugang'],   // wie der Server: Recht und Modulzugang
    kurz: 'Preise des veröffentlichten Wochenangebots als Datei „ImportPreise.csv“',
    beschreibung: 'Veröffentlichtes Wochenangebot als CSV für WinAB herunterladen: Artikelnummer;Preis – steht ein Artikel mehrfach im Angebot, der höhere Preis',
    async start() {
      try {
        const r = await W.api('angebot_winab_export', { body: {} });
        const url = URL.createObjectURL(new Blob([r.csv], { type: 'text/csv' }));
        const a = Object.assign(document.createElement('a'), { href: url, download: r.datei });
        document.body.append(a); a.click(); a.remove();
        setTimeout(() => URL.revokeObjectURL(url), 10000);
        const extra = [r.doppelt ? `${W.fmtInt.format(r.doppelt)}× doppelt – höherer Preis genommen` : '', r.ohnePreis ? `${W.plural(r.ohnePreis, 'Artikel', 'Artikel')} ohne Preis ausgelassen` : '',
          W.pendingCount && W.pendingCount() ? 'unveröffentlichte Änderungen im Entwurf sind nicht enthalten' : ''].filter(Boolean);
        W.toast(`${r.datei} heruntergeladen: ${W.plural(r.anzahl, 'Artikel', 'Artikel')} aus dem veröffentlichten Wochenangebot${r.woche ? ' ' + r.woche : ''}${extra.length ? ' (' + extra.join('; ') + ')' : ''}.`, 7000);
      } catch (ex) {
        if (!ex.wartung && ex.status !== 401) W.toast(ex.message || String(ex), 7000);
      }
    },
  };
})();
