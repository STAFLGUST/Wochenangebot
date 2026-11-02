<?php
declare(strict_types=1);
/* Importvertrag des Controllings – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md).
   Importart „umsatzdaten“: Kundenumsatztabelle der Warenwirtschaft (CSV) für die Umsatzauswertung. Große Datei: Der Leser
   (app/module/controlling/umsatz-import.js, im Eingabebereich geladen) fasst je Monat zusammen; die Vorschau nennt die
   geänderten Monate, die der Browser vor der Übernahme einzeln schickt (Registrierung „teile“). Prüfung und Speicherung:
   module/controlling/umsatzdaten.php. Recht controlling.umsatz_importieren; Wartung über die Oberfläche des Controllings.
   Importart „zeitbericht“: Zeitbericht der Zeiterfassung (.xlsx) für den Bereich Arbeitszeit. Der Leser
   (app/module/controlling/arbeitszeit-import.js) schickt das erste Tabellenblatt; Prüfung, Stempelfehler und Speicherung:
   module/controlling/arbeitszeit.php. Recht controlling.arbeitszeit_importieren. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

function import_arten_controlling(): array
{
    return [
        'umsatzdaten' => ['name' => 'Umsätze je Kunde und Artikel', 'kurz' => 'Kundenumsatztabelle der Warenwirtschaft', 'dateien' => ['csv'], 'kodierung' => 'CSV, Semikolon getrennt (Kundenumsatztabelle der Warenwirtschaft)',
            'beschreibung' => 'Kundenumsatztabelle der Warenwirtschaft: Kunde, Datum, Artikel, Kolli, Menge, Preis, Gesamtbetrag, EKPreis – für die Umsatzauswertung im Controlling. '
                . 'Der Zeitraum der Datei ersetzt die gespeicherten Umsätze dieses Zeitraums, frühere Monate bleiben erhalten. Dieselbe Datei erneut ändert nichts.',
            'recht' => ['controlling.umsatz_importieren'], 'aktion' => 'controlling_umsatz_daten', 'maxMb' => 200,
            'vorschau' => 'umsatzdaten_import_vorschau', 'teile' => 'umsatzdaten_import_teil', 'uebernahme' => 'umsatzdaten_import_uebernehmen'],
        'zeitbericht' => ['name' => 'Arbeitszeit (Zeitbericht)', 'kurz' => 'Zeitbericht der Zeiterfassung (Excel)', 'dateien' => ['xlsx'], 'kodierung' => 'Excel (.xlsx), Export „Zeitbericht“ der Zeiterfassung',
            'beschreibung' => 'Zeitbericht der Zeiterfassung: je Mitarbeiter und Tag Geplant, Gearbeitete Stunden, Abwesenheit, Pause, Saldo und die Stempel – für den Bereich Arbeitszeit im Controlling. '
                . 'Der Zeitraum der Datei ersetzt die gespeicherten Tage dieses Zeitraums. Stempelfehler werden markiert, nicht korrigiert. Gründe von Abwesenheiten werden nicht gespeichert.',
            'recht' => ['controlling.arbeitszeit_importieren'], 'aktion' => 'controlling_arbeitszeit_daten', 'maxMb' => 30,
            'vorschau' => 'arbeitszeit_import_vorschau', 'uebernahme' => 'arbeitszeit_import_uebernehmen'],
    ];
}
