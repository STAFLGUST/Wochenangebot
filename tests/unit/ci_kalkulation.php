<?php
declare(strict_types=1);
/* Hilfsskript für tests/unit/test_ci_kalkulation.py: Rechenkern der Kalkulation je Container
   (app/api/module/containerimport/kalkulation.php) ohne Server und ohne Speicher.
   Eingabe (JSON auf stdin): {"eingabe": {...}, "saetze": {...} (optional, sonst CI_KALK_SAETZE)}
   Ausgabe (JSON): {"eingabe": geprüfte Eingabe, "ergebnis": Ergebnis} oder {"fehler": Meldung der Eingabeprüfung}. */
define('WA_API', true);
function now(): string { return gmdate('Y-m-d\TH:i:s\Z'); }
require __DIR__ . '/../../app/api/module/containerimport/eudr.php';
require __DIR__ . '/../../app/api/module/containerimport/kalkulation.php';
$in = json_decode((string)stream_get_contents(STDIN), true);
try {
    $e = ci_kalkulation_eingabe($in['eingabe'] ?? []);
    $out = ['eingabe' => $e, 'ergebnis' => ci_kalkulation_rechnen($e, $in['saetze'] ?? CI_KALK_SAETZE), 'nochmal' => ci_kalkulation_eingabe($e) === $e];
} catch (InvalidArgumentException $x) {
    $out = ['fehler' => $x->getMessage()];
}
echo json_encode($out, JSON_UNESCAPED_UNICODE | JSON_PRESERVE_ZERO_FRACTION);
