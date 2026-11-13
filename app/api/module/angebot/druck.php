<?php
declare(strict_types=1);
/* Druck der Angebote: Fußzeile des Briefbogens unter jedem gedruckten Angebot (Wunsch des Inhabers 13.11.2026).
   Die Fußzeile besteht aus drei Textspalten (Firma/Anschrift · Telefon/Web · Bank/Steuer) und zwei Zeilen (Handelsregister);
   davor stehen die Siegel (assets/druck-siegel.jpg), darüber der Hinweis zu Mengen und Fracht (lib/fracht.php).
   Gespeichert als optionales Feld „druck“ im Dokument „fracht“ (Einstellungen des Angebots; ältere Fassungen ohne das Feld
   bleiben lesbar, fracht_save erhält es): {spalten: [3 Texte], zeilen: [2 Texte], modus: 'jede'|'letzte'}.
   Ohne eigene Angaben gilt die Vorgabe unten – nur was ohnehin öffentlich im Impressum der Angebotsseite steht; Bank-,
   Steuer- und weitere Registerangaben trägt ein Administrator ein (Angebot bearbeiten → ⋯ → „Fußzeile im Druck“), sie
   stehen nicht im Code (GR-007). Ausgeliefert wird die Fußzeile mit dem Angebot (fracht_public → „fuss“), weil jede
   Druckfassung sie zeigt – sie enthält nur Angaben des Geschäftsbriefs.
   modus: Fußzeile und Hinweis auf jeder Seite („jede“) oder nur am Fuß der letzten Seite („letzte“). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const DRUCK_FUSS_MODI = ['jede', 'letzte'];
const DRUCK_FUSS_MODUS = 'jede';   // Vorgabe, solange nichts gewählt ist (Entscheidung des Inhabers steht aus)
const DRUCK_FUSS_ZEILEN = 6;       // Zeilen je Spalte
const DRUCK_FUSS_LAENGE = 70;      // Zeichen je Zeile einer Spalte
const DRUCK_FUSS_LANG = 200;       // Zeichen je Registerzeile
/* Vorgabe: Angaben aus dem Impressum (app/impressum/) und dem Hinweis der Frachtregel – nichts darüber hinaus */
const DRUCK_FUSS_VORGABE = [
    'spalten' => [
        "Standard-Fleisch GmbH & Co. KG\nLagerstraße 17\n20357 Hamburg",
        "Telefon ( 040 ) 43 25 88-0\nTelefax ( 040 ) 43 25 88-88\nwww.standard-fleisch.de\ninfo@standard-fleisch.de",
        "Ust-IdNr. : DE 118949959",
    ],
    'zeilen' => [
        'Eingetragen Handelsregister Hamburg B 522 68 * Geschäftsführer : Jan Lawrence, Markus Nachtigall, Nils Dwenger, Tilman Paschen',
        'Eingetragen Handelsregister Hamburg A 828 28 * Persönlich haftende Gesellschafterin : Jan Lawrence Handelsgesellschaft mbH',
    ],
];

/* Text einer Spalte: höchstens DRUCK_FUSS_ZEILEN Zeilen, ohne Steuerzeichen, Leerzeichen bereinigt */
function druck_fuss_text($v, int $zeilen, int $laenge): string
{
    $t = is_string($v) ? $v : '';
    $t = str_replace("\r", '', preg_replace('/[\x00-\x09\x0b-\x1f\x7f]/u', ' ', $t) ?? '');
    $out = [];
    foreach (explode("\n", $t) as $l) {
        $l = trim(preg_replace('/\s+/u', ' ', $l) ?? '');
        if ($l !== '') $out[] = mb_substr($l, 0, $laenge);
    }
    return implode("\n", array_slice($out, 0, $zeilen));
}
/* Eingabe prüfen: drei Spalten, zwei Zeilen, Modus – unbekannte Felder fallen weg */
function druck_fuss_clean($in): array
{
    $in = is_array($in) ? $in : [];
    $sp = is_array($in['spalten'] ?? null) ? array_values($in['spalten']) : [];
    $ze = is_array($in['zeilen'] ?? null) ? array_values($in['zeilen']) : [];
    $spalten = []; $zeilen = [];
    for ($i = 0; $i < 3; $i++) $spalten[] = druck_fuss_text($sp[$i] ?? '', DRUCK_FUSS_ZEILEN, DRUCK_FUSS_LAENGE);
    for ($i = 0; $i < 2; $i++) $zeilen[] = druck_fuss_text($ze[$i] ?? '', 1, DRUCK_FUSS_LANG);
    $modus = in_array($in['modus'] ?? '', DRUCK_FUSS_MODI, true) ? $in['modus'] : DRUCK_FUSS_MODUS;
    return ['spalten' => $spalten, 'zeilen' => $zeilen, 'modus' => $modus];
}
/* Gespeicherte Einstellung (roh) oder null */
function druck_fuss_gespeichert(): ?array
{
    $d = store_read('fracht');
    return is_array($d) && is_array($d['druck'] ?? null) ? $d['druck'] : null;
}
/* Wirksame Fußzeile: eigene Texte, sonst die Vorgabe; „eigen“ sagt, ob Texte hinterlegt sind */
function druck_fuss(): array
{
    $g = druck_fuss_gespeichert();
    $c = druck_fuss_clean($g ?? []);
    $eigen = implode('', $c['spalten']) . implode('', $c['zeilen']) !== '';
    if (!$eigen) { $c['spalten'] = DRUCK_FUSS_VORGABE['spalten']; $c['zeilen'] = DRUCK_FUSS_VORGABE['zeilen']; }
    return $c + ['eigen' => $eigen, 'updatedAt' => $g['updatedAt'] ?? null, 'updatedBy' => (string)($g['updatedBy'] ?? '')];
}
/* Für die Angebotsseite (Druck): nur Texte und Modus */
function druck_fuss_public(): array
{
    $f = druck_fuss();
    return ['spalten' => $f['spalten'], 'zeilen' => $f['zeilen'], 'modus' => $f['modus']];
}
/* Speichern (nur das Feld „druck“; Fracht und Hinweis bleiben unverändert). Leere Texte = wieder die Vorgabe. */
function druck_fuss_speichern($in, array $me): array
{
    $alt = druck_fuss();
    $neu = druck_fuss_clean($in);
    with_lock('fracht', function () use ($neu, $me) {
        $d = store_read('fracht');
        if (!is_array($d)) $d = ['aktiv' => FRACHT_DEFAULT['aktiv'], 'staffeln' => FRACHT_DEFAULT['staffeln'], 'zusatz' => FRACHT_DEFAULT['zusatz']];
        $d['druck'] = $neu + ['updatedAt' => now(), 'updatedBy' => $me['name']];
        store_write('fracht', $d);
    });
    $jetzt = druck_fuss();
    $ch = [];
    foreach ([0 => 'Spalte 1', 1 => 'Spalte 2', 2 => 'Spalte 3'] as $i => $n) {
        if ($alt['spalten'][$i] !== $jetzt['spalten'][$i]) $ch[] = ['k' => "druck|s$i", 'code' => '', 'name' => 'Fußzeile im Druck', 'f' => $n, 'from' => str_replace("\n", ' / ', $alt['spalten'][$i]), 'to' => str_replace("\n", ' / ', $jetzt['spalten'][$i])];
    }
    foreach ([0 => 'Zeile 1', 1 => 'Zeile 2'] as $i => $n) {
        if ($alt['zeilen'][$i] !== $jetzt['zeilen'][$i]) $ch[] = ['k' => "druck|z$i", 'code' => '', 'name' => 'Fußzeile im Druck', 'f' => $n, 'from' => $alt['zeilen'][$i], 'to' => $jetzt['zeilen'][$i]];
    }
    $mt = ['jede' => 'auf jeder Seite', 'letzte' => 'nur auf der letzten Seite'];
    if ($alt['modus'] !== $jetzt['modus']) $ch[] = ['k' => 'druck|modus', 'code' => '', 'name' => 'Fußzeile im Druck', 'f' => 'Fußzeile und Hinweis', 'from' => $mt[$alt['modus']], 'to' => $mt[$jetzt['modus']]];
    if ($ch) audit('mail', 'Fußzeile im Druck der Angebote geändert', $ch);
    return $jetzt;
}
