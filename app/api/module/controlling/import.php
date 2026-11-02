<?php
declare(strict_types=1);
/* Importvertrag des Controllings – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md).
   Importart „umsatzdaten“: Kundenumsatztabelle der Warenwirtschaft (CSV) für die Umsatzauswertung. Große Datei: Der Leser
   (app/module/controlling/umsatz-import.js, im Eingabebereich geladen) fasst je Monat zusammen; die Vorschau nennt die
   geänderten Monate, die der Browser vor der Übernahme einzeln schickt (Registrierung „teile“). Prüfung und Speicherung:
   module/controlling/umsatzdaten.php. Recht controlling.umsatz_importieren; Wartung über die Oberfläche des Controllings. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

function import_arten_controlling(): array
{
    return [
        'umsatzdaten' => ['name' => 'Umsätze je Kunde und Artikel', 'kurz' => 'Kundenumsatztabelle der Warenwirtschaft', 'dateien' => ['csv'], 'kodierung' => 'CSV, Semikolon getrennt (Kundenumsatztabelle der Warenwirtschaft)',
            'beschreibung' => 'Kundenumsatztabelle der Warenwirtschaft: Kunde, Datum, Artikel, Kolli, Menge, Preis, Gesamtbetrag, EKPreis – für die Umsatzauswertung im Controlling. '
                . 'Der Zeitraum der Datei ersetzt die gespeicherten Umsätze dieses Zeitraums, frühere Monate bleiben erhalten. Dieselbe Datei erneut ändert nichts.',
            'recht' => ['controlling.umsatz_importieren'], 'aktion' => 'controlling_umsatz_daten', 'maxMb' => 200,
            'vorschau' => 'umsatzdaten_import_vorschau', 'teile' => 'umsatzdaten_import_teil', 'uebernahme' => 'umsatzdaten_import_uebernehmen'],
    ];
}
