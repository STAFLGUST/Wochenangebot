<?php
declare(strict_types=1);
/* Controlling · Bereich Umsatzstatistik, Reiter „Monatsmeldung“: Kg, Umsatz und Deckungsbeitrag je Vertreter und Monat eines
   Jahres – gerechnet aus den importierten Umsatzdaten der Warenwirtschaft (module/controlling/umsatzdaten.php), nicht mehr
   von Hand erfasst (Auftrag des Inhabers 01.11.2026: „nur durch die importierten Daten“). Die Oberfläche (umsatz.js) zeigt
   Kennzahlen, Anteile, Spanne = DB ÷ Umsatz und den Monatsvergleich.
   Vertreter = Hauptvertreter des Kunden nach den heutigen Stammdaten der Verwaltung (wie in der Auswertung); Kunden ohne
   Vertreter bzw. ohne Stammsatz stehen unter „ohne Vertreter“, Nummern, die nicht mehr in den Stammdaten stehen, mit Nummer.
   Kg = Menge der berechneten Positionen; DB nur mit controlling.umsatz_ek und bestand.einkaufspreise (GR-008), sonst leer.
   Das frühere Dokument „controlling-umsatz“ (Monatsmeldung von Hand) wird nicht mehr gelesen oder geschrieben. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Jahre mit importierten Umsätzen (neueste zuerst) */
function controlling_umsatz_jahre(array $index): array
{
    $j = array_values(array_unique(array_map(fn($m) => substr((string)$m, 0, 4), array_keys($index['monate']))));
    rsort($j, SORT_STRING);
    return $j;
}

/* Vertreter für die Oberfläche: aktuelle aus den Stammdaten, dazu Nummern mit Umsatz, die dort nicht (mehr) stehen,
   und „ohne Vertreter“ (Nummer „_“), wenn es Umsätze ohne Vertreter gibt */
function controlling_umsatz_vertreter(array $mitUmsatz): array
{
    $stamm = umsatz_stamm()['vertreter'];
    $out = [];
    foreach ($stamm as $nr => $v) {
        $name = trim((string)($v['name'] ?? '')); $kurz = trim((string)($v['kurz'] ?? ''));
        $out[] = ['nr' => (string)$nr, 'name' => $name, 'kurz' => $kurz, 'aktiv' => true, 'anzeige' => $nr . ' – ' . ($kurz !== '' ? $kurz : ($name !== '' ? $name : $nr))];
    }
    foreach (array_keys($mitUmsatz) as $nr) {
        $nr = (string)$nr;
        if (isset($stamm[$nr]) || $nr === UMSATZ_OHNE) continue;
        $out[] = ['nr' => $nr, 'name' => '', 'kurz' => '', 'aktiv' => false, 'anzeige' => "Vertreter $nr (nicht in den Stammdaten)"];
    }
    usort($out, fn($a, $b) => $a['aktiv'] === $b['aktiv'] ? strnatcasecmp($a['nr'], $b['nr']) : ($a['aktiv'] ? -1 : 1));   // aktuelle zuerst
    if (isset($mitUmsatz[UMSATZ_OHNE])) $out[] = ['nr' => UMSATZ_OHNE, 'name' => '', 'kurz' => '', 'aktiv' => false, 'anzeige' => 'ohne Vertreter'];
    return $out;
}

/* Kg, Umsatz und DB je Monat und Vertreter eines Jahres aus den Umsatzdaten: { "MM": { "<Vertreter>": { kg, umsatz, db } } } */
function controlling_umsatz_jahr(array $index, string $jahr, bool $ek): array
{
    $summe = [];   // Monat → Vertreter → [Menge, Umsatz, EK-Wert, Umsatz mit EK]
    $vertreter = [];   // Vertreter je Kunde (zwischengespeichert)
    foreach (array_keys($index['monate']) as $m) {
        $m = (string)$m;
        if (substr($m, 0, 4) !== $jahr) continue;
        $mm = substr($m, 5, 2);
        foreach (umsatzdaten_monat($m) as $z) {
            if ($z[9] !== 1) continue;   // ohne Berechnung (z. B. Leergut) zählt nicht
            $v = $vertreter[$z[1]] ??= umsatz_merkmal('vertreter', $z[1], $z[2]);
            $s = &$summe[$mm][$v];
            $s ??= [0, 0, 0, 0];
            $s[0] += $z[4]; $s[1] += $z[5]; $s[2] += $z[6]; $s[3] += $z[7];
            unset($s);
        }
    }
    $out = [];
    ksort($summe, SORT_STRING);
    foreach ($summe as $mm => $je) {
        ksort($je, SORT_NATURAL);
        foreach ($je as $v => $s) $out[(string)$mm][(string)$v] = ['kg' => round($s[0] / 1000, 3), 'umsatz' => round($s[1] / 100, 2), 'db' => $ek ? round(($s[3] - $s[2]) / 100, 2) : null];
    }
    return $out;
}

/* Antwort für die Oberfläche: ein Jahr (Anfrage ?jahr=JJJJ, sonst das jüngste mit Umsatzdaten) */
function controlling_umsatz_antwort(array $me, $jahrRoh = null): array
{
    $index = umsatzdaten_index();
    $jahre = controlling_umsatz_jahre($index);
    $jahr = $jahrRoh !== null && $jahrRoh !== '' ? controlling_jahr($jahrRoh) : ($jahre[0] ?? date('Y'));
    $ek = umsatz_darf_ek($me);
    $werte = controlling_umsatz_jahr($index, $jahr, $ek);
    $mitUmsatz = [];
    foreach ($werte as $je) foreach (array_keys($je) as $v) $mitUmsatz[(string)$v] = true;
    $monate = [];
    foreach (CONTROLLING_MONATE as $nr => $name) $monate[] = ['nr' => sprintf('%02d', $nr), 'name' => $name];   // „10“–„12“ sind in PHP Zahlenschlüssel
    $g = $index['importe'][0] ?? null;
    return ['ok' => true, 'rev' => $index['rev'], 'jahr' => $jahr, 'jahreListe' => $jahre, 'jahre' => (object)($werte ? [$jahr => $werte] : []), 'monate' => $monate,
            'vertreter' => controlling_umsatz_vertreter($mitUmsatz), 'geaendert' => $g ? ['t' => $g['t'] ?? null, 'vonName' => $g['vonName'] ?? ''] : null,
            'rechte' => ['ek' => $ek, 'importieren' => may($me, 'controlling.umsatz_importieren')], 'umsatzdaten' => ['vorhanden' => (bool)$index['monate']]];
}
