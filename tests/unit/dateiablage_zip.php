<?php
declare(strict_types=1);
/* Hilfsskript für tests/unit/test_dateiablage_zip.py: ZIP-Export ablage_zip_senden() aus app/api/lib/dateiablage.php.
   Eingabe (JSON auf stdin): {"wurzel": Datenordner mit dateien/<bereich>/<xx>/<id>.bin, "eintraege": [...] wie im Modul}.
   Ausgabe: das ZIP auf stdout. */
define('WA_API', true);
$in = json_decode((string)stream_get_contents(STDIN), true);
function store_ordner(string $bereich): string { global $in; return $in['wurzel']; }
function store_getrennt(): bool { return false; }
require __DIR__ . '/../../app/api/lib/dateiablage.php';
ablage_zip_senden('test.zip', $in['eintraege']);
