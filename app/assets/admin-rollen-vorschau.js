/* ==========================================================================
   Wochenangebot – Verwaltung → Rollen und Rechte: Bilder (nur Anzeige)
   Modulsymbole mit den Kachelfarben des Dashboards (dashboard/dashboard.css, .db-ico[data-symbol]) und die
   Vorschau-Bilder wichtiger Rechte: kleine, fest gezeichnete Ausschnitte aus dem Modul mit BEISPIELDATEN (nie echte
   Daten, GR-007), die rot markieren, was das Recht freischaltet. Welches Recht welches Bild zeigt, legt der Server fest
   (PERMS_VORSCHAU in lib/rechte.php, Feld „vorschau“ im Katalog). Genutzt von admin-rollen.js:
   WA.rollenSymbol(symbol) → { pfad, farbe }, WA.rollenVorschau(art, modul, symbol) → HTML (leer bei unbekannter Art).
   ========================================================================== */
(function () {
  'use strict';
  const W = window.WA;
  const esc = W.esc;

  /* Symbol des Modulregisters (Feld icon) → Pfad (24er Raster, Linie) und Kachelfarbe */
  const SYMBOLE = {
    tag: ['M12.6 2.6 21.4 11.4a2 2 0 0 1 0 2.8l-7.2 7.2a2 2 0 0 1-2.8 0L2.6 12.6A2 2 0 0 1 2 11.2V4a2 2 0 0 1 2-2h7.2a2 2 0 0 1 1.4.6Z M7.5 7.5h.01', '#b3263a'],
    boxes: ['M21 8 12 3 3 8v8l9 5 9-5V8Z M3 8l9 5 9-5 M12 13v8', '#3f7a5a'],
    crate: ['M3 6h18v14H3Z M3 11h18 M3 15.5h18 M8 6v14 M16 6v14', '#8a7560'],
    users: ['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2 M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8Z M22 21v-2a4 4 0 0 0-3-3.9 M16 3.1a4 4 0 0 1 0 7.8', '#3d6fa8'],
    store: ['M4 4h16l1 5H3Z M3 9a3 3 0 0 0 6 0a3 3 0 0 0 6 0a3 3 0 0 0 6 0 M5 12v8h14v-8 M10 20v-5h4v5', '#c2414f'],
    'shield-check': ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z M9 12l2 2 4-4', '#2f8a86'],
    truck: ['M2 5h12v11H2Z M14 9h4l4 4v3h-8 M6 19.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z M18 19.5a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z', '#c98a2b'],
    container: ['M2 7h20v11H2Z M6 7v11 M10 7v11 M14 7v11 M18 7v11', '#2a7f9e'],
    upload: ['M12 15V4 M7 9l5-5 5 5 M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4', '#6a5fa8'],
    calendar: ['M4 5h16v16H4Z M4 10h16 M8 3v4 M16 3v4', '#8e4fa0'],
    megaphone: ['M3 11v3a1 1 0 0 0 1 1h3l5 4V6L7 10H4a1 1 0 0 0-1 1Z M16 9a4 4 0 0 1 0 6 M19 6a8 8 0 0 1 0 12', '#e06a3a'],
    chart: ['M3 3v18h18 M7 15l4-4 3 3 6-6', '#6b8a3a'],
    settings: ['M4 6h9 M17 6h3 M15 4v4 M4 12h3 M11 12h9 M9 10v4 M4 18h11 M19 18h1 M17 16v4', '#5b5f68'],
    'shield-lock': ['M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z M9.5 11.5h5v4h-5Z M10.5 11.5V10a1.5 1.5 0 0 1 3 0v1.5', '#4a4f5a']
  };
  const RASTER = 'M4 4h7v7H4Z M13 4h7v7h-7Z M4 13h7v7H4Z M13 13h7v7h-7Z';
  W.rollenSymbol = (s) => { const x = SYMBOLE[s]; return { pfad: x ? x[0] : RASTER, farbe: x ? x[1] : '#7a7570' }; };
  const svg = (pfad, gr = 14, cls = '') => `<svg class="rv-i ${cls}" width="${gr}" height="${gr}" viewBox="0 0 24 24" aria-hidden="true"><path d="${pfad}"/></svg>`;

  /* Tabelle aus Spalten [Kopf, Werte, Klasse]; „extra“ = weitere, fertige Spalte (z. B. die markierte EK-Spalte) */
  const tab = (spalten, extra = '') => `<div class="rv-tab">${spalten.map(([kopf, werte, cls]) => `<div class="rv-sp ${cls || ''}"><span>${kopf}</span>${werte.map((w) => `<span>${w}</span>`).join('')}</div>`).join('')}${extra}</div>`;
  const ARTIKEL = ['Artikel', ['Schweinenacken o. K.', 'Rinderhüfte', 'Putenbrust'], 'breit'];
  const MENGE = ['Menge', ['312 kg', '88 kg', '540 kg'], 'r'];

  /* art → [Pfad im Kopf, Beschreibung für Screenreader, Inhalt] */
  const BILDER = {
    kachel: (m, sym) => {
      const s = W.rollenSymbol(sym);
      return ['Dashboard', 'Die Kachel des Moduls erscheint im Dashboard.',
        `<div class="rv-kacheln"><span class="rv-kachel an rv-mark"><span class="rv-ico" style="background:${s.farbe}">${svg(s.pfad, 15)}</span><b>${esc(m)}</b></span><span class="rv-kachel"></span><span class="rv-kachel"></span><span class="rv-kachel"></span></div>
        <span class="rv-sub">Die Kachel erscheint, das Modul lässt sich öffnen. Was darin geht, regeln die Rechte darunter.</span>`];
    },
    bestand: () => ['Bestand › Partien', 'Partienliste mit Artikel, Partie, Menge und MHD.',
      `<div class="rv-mark">${tab([ARTIKEL, ['Partie', ['P-2041', 'P-2057', 'P-2063']], MENGE, ['MHD', ['14.11.', '<i class="rv-chip warn">09.11.</i>', '22.11.']]])}</div>
      <span class="rv-sub">Mengen und MHD je Partie – Einkaufspreise bleiben ausgeblendet.</span>`],
    ek: () => ['Bestand › Partien', 'Partienliste mit zusätzlicher Spalte Einkaufspreis je kg.',
      `${tab([ARTIKEL, MENGE, ['MHD', ['14.11.', '09.11.', '22.11.']]], '<div class="rv-sp r ek rv-mark innen"><span>EK €/kg</span><span>4,85</span><span>11,20</span><span>6,10</span></div>')}
      <span class="rv-sub">Ohne dieses Recht fehlt die Spalte EK – auch in Exporten und im Controlling.</span>`],
    import: () => ['Verwaltung › Import', 'Ablagefeld zum Hochladen der Bestandsliste.',
      `<div class="rv-ablage rv-mark">${svg(SYMBOLE.upload[0], 20)}<b>Bestandsliste hierher ziehen</b><span class="rv-sub">CSV aus der Warenwirtschaft · ersetzt den Tagesstand</span></div>
      <span class="rv-ok">${svg('M5 12l5 5 9-10', 12)}Bestand_Montag.csv geprüft und übernommen</span>`],
    mhd: () => ['E-Mail an den Verkauf', 'E-Mail mit der MHD-Liste an den Verkauf.',
      `<div class="rv-karte"><span><span class="rv-sub">An:</span> Verkauf (Verteiler)</span><span><span class="rv-sub">Betreff:</span> <b>MHD-Liste – Ware bis 15.11.</b></span>
        <span class="rv-trenn">Rinderhüfte · P-2057 · 88 kg · MHD 09.11.</span><span>Schweinenacken o. K. · P-2041 · 312 kg · MHD 14.11.</span></div>
      <div class="rv-zeile ende"><span class="rv-sub">geht an den Verkaufsverteiler</span><span class="rv-knopf rv-mark">${svg('M22 2 11 13 M22 2l-7 20-4-9-9-4Z', 11)}Liste senden</span></div>`],
    veroeffentlichen: () => ['Angebot › Entwurf', 'Knopf Veröffentlichen macht den Entwurf für alle Kunden sichtbar.',
      `<div class="rv-zeile"><span class="rv-chip warn">Entwurf KW 46</span><span class="rv-sub rv-wachsen">geändert heute 14:20</span><span class="rv-knopf rv-mark">Veröffentlichen</span></div>
      <div class="rv-karte"><span class="rv-zeile"><b>Wochenangebot KW 46</b><span class="rv-chip ok">für alle Kunden sichtbar</span></span>
        <span class="rv-zeile rv-trenn"><span>Schweinenacken o. K.</span><b>5,49 €/kg</b></span><span class="rv-zeile"><span>Putenbrust</span><b>7,20 €/kg</b></span></div>`],
    umsatz: () => ['CRM › Cockpit', 'Umsatz in Euro im CRM-Cockpit.',
      `<div class="rv-zeile oben"><span class="rv-kpi"><span class="rv-sub">Kunden aktiv</span><b>48</b></span><span class="rv-kpi"><span class="rv-sub">Menge Okt.</span><b>12.400 kg</b></span><span class="rv-kpi ek rv-mark"><span>Umsatz Okt.</span><b>86.200,00 €</b></span></div>
      <div class="rv-karte rv-zeile"><span>Metzgerei Muster · Kunden-Pop-up</span><span><b>1.100 kg</b> · <b class="rv-rot">4.180,00 €</b></span></div>
      <span class="rv-sub">Ohne dieses Recht stehen hier nur Mengen in kg.</span>`],
    export: () => ['CRM › Liste', 'CSV-Datei mit Kontaktdaten herunterladen.',
      `<div class="rv-zeile oben"><span class="rv-sub">CRM-Liste · 214 Kunden</span><span class="rv-knopf hell rv-mark">${svg('M12 4v11 M7 10l5 5 5-5 M4 19h16', 11)}CSV herunterladen</span></div>
      ${tab([['Firma', ['Beispiel GmbH', 'Muster &amp; Sohn'], 'breit'], ['Kontakt', ['F. Muster', 'E. Probe']], ['Telefon', ['0123 45…', '0123 67…']]])}
      <span class="rv-warn">${svg('M12 3 2 21h20L12 3Z M12 10v4 M12 17h.01', 12)}Die Datei enthält Kontaktdaten und verlässt das System.</span>`],
    spanne: () => ['Controlling › Umsatzauswertung', 'Umsatzauswertung mit Einkaufswert, Deckungsbeitrag und Spanne.',
      `${tab([['Kunde', ['Metzgerei Muster', 'Beispiel GmbH', 'Hof Probe'], 'breit'], ['Umsatz', ['4.180,00 €', '2.940,00 €', '1.310,00 €'], 'r']], '<div class="rv-sp r ek rv-mark innen"><span>DB · Spanne</span><span>620,00 € · 15,0 %</span><span>380,00 € · 13,0 %</span><span>210,00 € · 16,0 %</span></div>')}
      <span class="rv-sub">Wirkt nur zusammen mit „Einkaufspreise (EK) sehen“ im Bestand.</span>`],
    lagerwert: () => ['Controlling › Bestandsverlauf', 'Bestandsverlauf mit zweiter Linie Lagerwert zum Einkaufspreis.',
      `<div class="rv-zeile oben anfang"><span class="rv-leg"><i class="gruen"></i>Bestand in kg</span><span class="rv-leg rot rv-mark"><i></i>Lagerwert zum EK</span></div>
      <div class="rv-karte rv-diag"><svg viewBox="0 0 320 80" preserveAspectRatio="none" aria-hidden="true"><path class="g" d="M0 20H320 M0 40H320 M0 60H320"/>
        <polyline class="kg" points="0,52 32,48 64,50 96,42 128,44 160,36 192,40 224,30 256,34 288,26 320,28"/><polyline class="ek" points="0,62 32,60 64,58 96,54 128,56 160,46 192,48 224,40 256,38 288,30 320,22"/></svg></div>`],
    genehmigen: () => ['HR › Offene Anträge', 'Urlaubsantrag genehmigen oder ablehnen.',
      `<div class="rv-karte"><span class="rv-zeile anfang"><span class="rv-av">TW</span><span class="rv-spalte"><b>T. Wagner · Urlaub</b><span class="rv-sub">12.–16.11. · 5 Tage · Rest danach 14 Tage</span></span></span>
        <span class="rv-zeile ende"><span class="rv-paar rv-mark"><span class="rv-knopf hell">Ablehnen</span><span class="rv-knopf gruen">Genehmigen</span></span></span></div>
      <span class="rv-sub">Entscheidet über Anträge anderer Mitarbeiter, nie über eigene.</span>`],
    kundenzugang: () => ['Verwaltung › Kunden', 'Einladung für einen Kundenzugang senden.',
      `<div class="rv-karte rv-dlg"><b>Zugang für Metzgerei Muster</b><span class="rv-sub">E-Mail des Kunden</span><span class="rv-feld">einkauf@example.com</span>
        <span class="rv-zeile ende"><span class="rv-knopf hell">Zugang sperren</span><span class="rv-knopf rv-mark">Einladung senden</span></span></div>
      <span class="rv-sub">Der Kunde sieht danach nur seine freigeschalteten Angebote.</span>`],
    notfall: () => ['Sicherheit › Lagebild', 'Knopf Notfallmodus auslösen im Lagebild.',
      `<div class="rv-karte rv-alarm rv-zeile anfang">${svg(SYMBOLE['shield-lock'][0], 24, 'rot')}<span class="rv-spalte"><b>Notfallmodus</b><span>Kunden sehen sofort eine Wartungsseite. Mitarbeiter ohne Administratorrolle werden abgemeldet.</span>
        <span class="rv-knopf rv-mark rv-links">Notfallmodus auslösen</span></span></div>
      <span class="rv-sub">Beenden können ihn nur Administratoren.</span>`]
  };

  /* Vorschau-Bild als <figure> (für Screenreader mit Beschreibung); leer, wenn es für die Art kein Bild gibt */
  W.rollenVorschau = (art, modul, symbol) => {
    const f = BILDER[art];
    if (!f) return '';
    const [pfad, alt, inhalt] = f(modul || '', symbol || '');
    return `<figure class="rv" role="img" aria-label="Vorschau: ${esc(alt)}" title="Vorschau: ${esc(alt)}" data-rv="${esc(art)}">
      <figcaption class="rv-kopf"><b>${esc(art === 'kachel' ? `${pfad} › ${modul}` : pfad)}</b><span>Beispieldaten</span></figcaption>
      <div class="rv-body">${inhalt}</div></figure>`;
  };
})();
