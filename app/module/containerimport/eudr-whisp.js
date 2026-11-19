/* Container-Import · EUDR: Ergebnis einer Whisp-Abfrage (FAO, whisp.openforis.org) deuten – reine Rechnung ohne Seite und
   ohne Abrufe. Whisp liefert je Fläche viele Eigenschaften; für die Gegenprüfung zählen:
     Ind_01_treecover               Baumbestand Ende 2020 (ja ab rund 10 % der Fläche)
     Ind_03_disturbance_before_2020 Störung vor dem Stichtag
     Ind_04_disturbance_after_2020  Störung nach dem Stichtag (ja ab rund 10 % der Fläche)
     …_after_2020                   Fläche je Datensatz mit Störung nach 2020 (Einheit in „Unit“)
     risk_pcrop, risk_acrop, risk_timber   Risiko für Dauerkulturen, Ackerkulturen, Holz
   Für Rinder gibt Whisp noch kein eigenes Risiko aus (Stand 11/2026, „risk_cattle“ angekündigt) – kommt die Spalte,
   gilt sie. Bis dahin der Vorschlag nach der Regel, die Whisp für Ackerkulturen nutzt: Baumbestand 2020 und Störung danach
   = Befund; kein Baumbestand 2020 = ohne Befund. Weil die Schwelle von 10 % auf großen Betrieben viel Fläche ist, gibt es
   bei Baumbestand und einer Störung ab AB_HA in einem Datensatz keinen Vorschlag – der Bearbeiter beurteilt selbst.
   API: window.EUDR_WHISP.deuten({ felder, version }) →
        { vorschlag: 'befund' | 'ohne_befund' | null, verlustHa: Zahl | null, wald, vorher, nachher: true | false | null,
          stoerungen: [[Name, Wert]], risiken: [[Name, Wert]], flaeche, land, einheit, text } */
(function () {
  'use strict';
  const AB_HA = 0.5;   // Mindestgröße eines Waldes nach der EUDR – wie bei der Bildauswertung
  const RISIKO = { low: 'niedrig', high: 'hoch', more_info_needed: 'weitere Angaben nötig' };
  const NAME = { risk_pcrop: 'Dauerkulturen', risk_acrop: 'Ackerkulturen', risk_timber: 'Holz', risk_cattle: 'Rinder', risk_livestock: 'Rinder' };

  const jaNein = (v) => (v === true || /^yes$/i.test(String(v)) ? true : v === false || /^no$/i.test(String(v)) ? false : null);
  const zahl = (v) => String(Math.round(v * 10) / 10).replace('.', ',');

  function deuten({ felder, version }) {
    const wald = jaNein(felder.Ind_01_treecover), vorher = jaNein(felder.Ind_03_disturbance_before_2020), nachher = jaNein(felder.Ind_04_disturbance_after_2020);
    const einheit = typeof felder.Unit === 'string' ? felder.Unit : '';
    const stoerungen = Object.entries(felder).filter(([k, v]) => /_after_2020$/i.test(k) && !/^Ind_/i.test(k) && typeof v === 'number' && v > 0).sort((a, b) => b[1] - a[1]);
    const risiken = Object.entries(felder).filter(([k, v]) => /^risk_/i.test(k) && typeof v === 'string').map(([k, v]) => [NAME[k] || k, RISIKO[v] || v]);
    const rind = felder.risk_cattle ?? felder.risk_livestock;
    const merklich = einheit === 'ha' && stoerungen.length > 0 && stoerungen[0][1] >= AB_HA;
    let vorschlag = null;
    if (rind === 'high' || rind === 'low') vorschlag = rind === 'high' ? 'befund' : 'ohne_befund';
    else if (rind === undefined && wald !== null && nachher !== null) {
      if (!wald) vorschlag = 'ohne_befund';
      else if (nachher) vorschlag = 'befund';
      else if (!merklich) vorschlag = 'ohne_befund';
    }
    const verlust = felder.GFC_loss_after_2020;
    const wort = (v) => (v === null ? 'unbekannt' : v ? 'ja' : 'nein');
    const text = [`Whisp (FAO${version ? ', Version ' + version : ''}): Baumbestand 2020 ${wort(wald)}, Störung vor 2020 ${wort(vorher)}, Störung nach 2020 ${wort(nachher)}`,
      stoerungen.length ? `Datensätze mit Störung nach 2020: ${stoerungen.slice(0, 4).map(([k, v]) => `${k} ${zahl(v)} ${einheit}`.trim()).join(', ')}` : 'kein Datensatz mit Störung nach 2020',
      risiken.length ? `Risiko ${risiken.map(([k, v]) => `${k}: ${v}`).join(', ')}` : ''].filter(Boolean).join('; ').slice(0, 499) + '.';
    return {
      vorschlag, verlustHa: vorschlag === 'befund' && einheit === 'ha' && typeof verlust === 'number' && verlust > 0 ? verlust : null,
      wald, vorher, nachher, stoerungen, risiken, einheit, text,
      flaeche: typeof felder.Area === 'number' ? felder.Area : null, land: typeof felder.Country === 'string' ? felder.Country : '',
    };
  }

  window.EUDR_WHISP = { deuten };
})();
