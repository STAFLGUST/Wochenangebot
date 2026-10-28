<?php
declare(strict_types=1);
/* Hilfsskript für tests/unit/test_adressen.py: Schreibweisen-Regeln und Nachschlagen aus app/api/lib/adressen.php.
   Eingabe (JSON auf stdin): {"norm": {"strasse": [...], "text": [...], "nr": [...]}, "teilen": [...], "punkte": [[strasse, plz, ort], ...]}
   Ausgabe (JSON): dieselbe Struktur mit Ergebnissen; Adressverzeichnis über WA_ADRESSEN. */
define('WA_API', true);
require __DIR__ . '/../../app/api/lib/adressen.php';
$in = json_decode((string)stream_get_contents(STDIN), true);
$out = ['norm' => [], 'teilen' => [], 'punkte' => [], 'stand' => adressen_stand()];
foreach (['strasse' => 'adressen_norm_strasse', 'text' => 'adressen_norm_text', 'nr' => 'adressen_norm_nr'] as $art => $f) {
    $out['norm'][$art] = array_map($f, $in['norm'][$art] ?? []);
}
$out['teilen'] = array_map('adressen_teilen', $in['teilen'] ?? []);
foreach ($in['punkte'] ?? [] as [$s, $p, $o]) $out['punkte'][] = adressen_punkt($s, $p, $o);
echo json_encode($out, JSON_UNESCAPED_UNICODE);
