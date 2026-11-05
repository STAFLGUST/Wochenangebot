/* STAFL-Plattform · Angebot · Knopf „Export für WinAB“ in der Werkzeugleiste des Wochenangebots (Auftrag des Inhabers 05.11.2026).
   Lädt das veröffentlichte Wochenangebot als CSV für WinAB herunter (Artikelnummer;Preis, je Nummer der höchste Preis).
   Datei und Zahlen erzeugt der Server (Aktion angebot_winab_export, module/angebot/winab-export.php) – nur mit dem Recht
   „angebot.winab_export“ (GR-103); sichtbar ist der Knopf nur mit diesem Recht und nur beim Wochenangebot (admin.js,
   renderWerbungBtn). Unveröffentlichte Änderungen im Entwurf sind nicht enthalten – das sagt die Rückmeldung.
   Wird von admin/index.html nach admin.js geladen. */
(function () {
  'use strict';
  const W = window.WA;
  const btn = document.getElementById('btn-winab');
  if (!W || !btn) return;
  btn.addEventListener('click', async () => {
    if (btn.disabled) return;
    btn.disabled = true;
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
    } finally {
      btn.disabled = false;
    }
  });
})();
