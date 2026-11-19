/* Container-Import · EUDR: Ergebnis einer Whisp-Abfrage (FAO, whisp.openforis.org) deuten – reine Rechnung ohne Seite und
   ohne Abrufe. Whisp liefert je Fläche viele Eigenschaften; für die Gegenprüfung zählen:
     Ind_01_treecover               Baumbestand Ende 2020 (ja ab rund 10 % der Fläche)
     Ind_03_disturbance_before_2020 Störung vor dem Stichtag
     Ind_04_disturbance_after_2020  Störung nach dem Stichtag (ja ab rund 10 % der Fläche)
     …_after_2020                   Fläche je Datensatz mit Störung nach 2020 (Einheit in „Unit“)
     risk_pcrop, risk_acrop, risk_timber   Risiko für Dauerkulturen, Ackerkulturen, Holz
   Für Rinder gibt Whisp noch kein eigenes Risiko aus (Stand 11/2026, „risk_cattle“ angekündigt) – kommt die Spalte,
   gilt sie. Bis dahin der Vorschlag nach der Regel, die Whisp für Ackerkulturen nutzt: Baumbestand 2020 und Störung danach
   = Befund. „Ohne Befund“ schlägt die Seite nur vor, wenn auch kein Datensatz eine Störung nach 2020 ab „abHa“ Hektar zeigt:
   die Schwellen von Whisp (10 % der Fläche) sind auf großen Betrieben viele Hektar. Sonst – und bei jedem Ergebnis, das
   nicht wie erwartet aussieht (Indikatoren fehlen, Einheit nicht Hektar) – gibt es keinen Vorschlag: der Bearbeiter beurteilt selbst.
   API: window.EUDR_WHISP.deuten({ felder, version }, abHa) →
        { vorschlag: 'befund' | 'ohne_befund' | null, verlustHa: Zahl | null (nur mit Befund), wald, vorher, nachher: true | false | null,
          stoerungen: [[Name, Wert]], risiken: [[Name, Wert]], rind: Whisp liefert ein Risiko für Rinder, flaeche, land, einheit,
          text: Bemerkung für die Gegenprüfung (höchstens 500 Zeichen, eudr_pruefung_pruefen) } */
(function () {
  'use strict';
  const RISIKO = { low: 'niedrig', high: 'hoch', more_info_needed: 'weitere Angaben nötig' };
  const NAME = { risk_pcrop: 'Dauerkulturen', risk_acrop: 'Ackerkulturen', risk_timber: 'Holz', risk_cattle: 'Rinder', risk_livestock: 'Rinder' };

  const jaNein = (v) => (v === true || /^yes$/i.test(String(v)) ? true : v === false || /^no$/i.test(String(v)) ? false : null);

  const zahlwert = (v) => (typeof v === 'number' ? v : typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN);   // Zahlen kommen notfalls auch als Text

  function deuten({ felder, version }, abHa) {
    const wald = jaNein(felder.Ind_01_treecover), vorher = jaNein(felder.Ind_03_disturbance_before_2020), nachher = jaNein(felder.Ind_04_disturbance_after_2020);
    const einheit = typeof felder.Unit === 'string' ? felder.Unit : '', hektar = /^ha$/i.test(einheit);
    const stoerungen = Object.entries(felder).filter(([k]) => /_after_2020$/i.test(k) && !/^Ind_/i.test(k)).map(([k, v]) => [k, zahlwert(v)]).filter(([, v]) => v > 0).sort((a, b) => b[1] - a[1]);
    const risiken = Object.entries(felder).filter(([k, v]) => /^risk_/i.test(k) && typeof v === 'string').map(([k, v]) => [NAME[k] || k, RISIKO[v] || v]);
    const rind = felder.risk_cattle ?? felder.risk_livestock;
    const merklich = stoerungen.length > 0 && (!hektar || stoerungen[0][1] >= (abHa || 0));   // ohne Hektar zählt jede Störung
    let vorschlag = null;
    if (rind === 'high' || rind === 'low') vorschlag = rind === 'high' ? 'befund' : 'ohne_befund';
    else if (rind === undefined && wald !== null && nachher !== null) {
      if (wald && nachher) vorschlag = 'befund';
      else if (!merklich) vorschlag = 'ohne_befund';
    }
    const verlust = felder.GFC_loss_after_2020;
    const wort = (v) => (v === null ? 'unbekannt' : v ? 'ja' : 'nein');
    const text = [`Whisp (FAO${version ? ', Version ' + version : ''}): Baumbestand 2020 ${wort(wald)}, Störung vor 2020 ${wort(vorher)}, Störung nach 2020 ${wort(nachher)}`,
      stoerungen.length ? `Datensätze mit Störung nach 2020: ${stoerungen.slice(0, 4).map(([k, v]) => `${k} ${window.STAFL_FORMAT.zahl(v, 1, 1)} ${einheit}`.trim()).join(', ')}` : 'kein Datensatz mit Störung nach 2020',
      risiken.length ? `Risiko ${risiken.map(([k, v]) => `${k}: ${v}`).join(', ')}` : ''].filter(Boolean).join('; ').slice(0, 499) + '.';
    return {
      vorschlag, verlustHa: vorschlag === 'befund' && hektar && zahlwert(verlust) > 0 ? zahlwert(verlust) : null,
      wald, vorher, nachher, stoerungen, risiken, rind: rind !== undefined, einheit, text,
      flaeche: hektar && zahlwert(felder.Area) > 0 ? zahlwert(felder.Area) : null, land: typeof felder.Country === 'string' ? felder.Country : '',
    };
  }

  window.EUDR_WHISP = { deuten };
})();
