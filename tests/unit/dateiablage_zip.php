<?php
declare(strict_types=1);
/* Hilfsskript für tests/unit/test_dateiablage_zip.py zu app/api/lib/dateiablage.php.
   Ohne Argumente: ZIP-Export ablage_zip_senden(). Eingabe (JSON auf stdin): {"wurzel": Datenordner mit dateien/<bereich>/<xx>/<id>.bin,
   "eintraege": [...] wie im Modul}. Ausgabe: das ZIP auf stdout.
   Mit Dateipfaden als Argumenten: Prüfung beim Hochladen ablage_zip_pruefen(). Ausgabe: JSON-Liste, je Datei „ok“ oder die Meldung. */
define('WA_API', true);
function store_ordner(string $bereich): string { global $in; return $in['wurzel']; }
function store_getrennt(): bool { return false; }
require __DIR__ . '/../../app/api/lib/dateiablage.php';
if ($argc > 1) {
    echo json_encode(array_map(function (string $f): string {
        try { ablage_zip_pruefen($f); return 'ok'; } catch (InvalidArgumentException $e) { return $e->getMessage(); }
    }, array_slice($argv, 1)), JSON_UNESCAPED_UNICODE);
    exit;
}
$in = json_decode((string)stream_get_contents(STDIN), true);
ablage_zip_senden('test.zip', $in['eintraege']);
