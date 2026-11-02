<?php
declare(strict_types=1);
/* Modul HR · Importe für die Importzentrale (Verwaltung → Import, docs/plattform/schnittstellen/import.md):
   „Abwesenheiten aus der Zeiterfassung“ (Leser app/module/hr/verwaltung-hr.js, Vorschau/Übernahme module/hr/zeiterfassung.php)
   und gemeinsame Hilfen (Zeiträume aus Einzeltagen, Stand für die Vorschau).
   Die Übernahme der früheren Excel-Urlaubsplanung („Urlaub 2026.xlsx“) ist entfernt (Auftrag des Inhabers 02.11.2026: nicht mehr
   nötig); früher übernommene Einträge (quelle „import“) bleiben gespeichert und werden weiter angezeigt. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Kürzel zu Zeiträumen zusammenfassen: aufeinanderfolgende Arbeitstage (Mo–Fr ohne Feiertage) mit gleichem Kürzel */
function hr_import_zeitraeume(array $tage): array
{
    ksort($tage);
    $out = []; $lauf = null;
    foreach ($tage as $d => $code) {
        if ($lauf && $lauf['art'] === $code) {
            $dazwischen = true;
            for ($x = hr_plus($lauf['bis'], 1); $x < $d; $x = hr_plus($x, 1)) if (hr_wochentag($x) <= 5 && hr_feiertag($x) === null) { $dazwischen = false; break; }
            if ($dazwischen) { $lauf['bis'] = $d; continue; }
        }
        if ($lauf) $out[] = $lauf;
        $lauf = ['art' => $code, 'von' => $d, 'bis' => $d];
    }
    if ($lauf) $out[] = $lauf;
    return $out;
}

/* Importart für die Importzentrale (Verwaltung → Import). Leser im Browser: app/module/hr/verwaltung-hr.js
   (window.WA.importLeser.zeiterfassung). „aktion“: Oberfläche der HR-Verwaltung (Wartung, GR-107). */
function import_arten_hr(): array
{
    return [
        // Importvorlage für Urlaubs- und Krankheitstage (Entscheidung 23.10.2026): Abwesenheitsbericht der Zeiterfassung
        'zeiterfassung' => ['name' => 'Abwesenheiten aus der Zeiterfassung', 'kurz' => 'Urlaub, krank, Feiertag aus der Zeiterfassung', 'beschreibung' => 'Abwesenheitsbericht der Zeiterfassung (.xlsx, je Mitarbeiter eine Kopfzeile mit Mitarbeiternummer und darunter Urlaub/Krank/Feiertag). Zuordnung über die Personalnummer, sonst über den Namen; unbekannte Mitarbeiter werden ohne Anmeldung angelegt. Erneute Übernahme ersetzt die zuvor aus der Zeiterfassung übernommenen Einträge im Zeitraum des Berichts.',
            'recht' => ['hr.verwalten'], 'aktion' => 'hr_verwaltung', 'dateien' => ['xlsx'], 'kodierung' => 'Excel-Arbeitsmappe (.xlsx)',
            'optionen' => [['id' => 'abteilungen', 'typ' => 'schalter', 'label' => 'Abteilungen aus der Zeiterfassung übernehmen', 'standard' => false]],
            'vorschau' => 'hr_zeit_vorschau', 'uebernahme' => 'hr_zeit_uebernehmen'],
    ];
}

/* Stand der HR-Daten für Vorschau und Übernahme (veralteter Stand → 409) */
function hr_import_stand(array $personal, array $abw, int $mitarbeiter = 0): string { return $personal['rev'] . '-' . $abw['rev'] . '-' . $mitarbeiter; }
