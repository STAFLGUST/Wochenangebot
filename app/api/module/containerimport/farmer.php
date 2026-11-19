<?php
declare(strict_types=1);
/* STAFL-Plattform · Modul Container-Import – Farmer-Nummern am Container (Auftrag des Inhabers 19.11.2026).
   Jeder Farmer hat zwei Nummern: die eigene („nr“, angezeigt F-0001) und die aus den Papieren des Lieferanten („kennung“,
   z. B. SIGOR-Nummer), je Herkunftsland eindeutig und verglichen ohne Rücksicht auf Schreibweise (ci_nummer_schluessel).
   Die eigene Nummer ist die Stelle in der Liste der Farmer + 1: abgeleitet beim Lesen (eudr_betriebe), nie gespeichert.
   Das gilt, weil die Liste nur am Ende wächst und nie gelöscht oder umsortiert wird (archivieren statt löschen).
   Ein Container nennt seine Farmer; Nummern aus den Papieren, zu denen noch kein Farmer angelegt ist, stehen am Container
   in „offeneNummern“ und werden zugeordnet, sobald ein Farmer mit dieser Nummer gespeichert wird (ci_offene_nummern_zuordnen,
   nur offene Bewertung, GR-106). Daraus die Gesamtprüfung je Container (ci_farmer_pruefung, nur abgeleitet).
   Speicher- und Prüfhelfer (eudr_text, eudr_betriebe …) stehen in eudr.php, das diese Datei einbindet. */
if (!defined('WA_API')) { http_response_code(404); exit; }

const CI_MAX_NUMMERN = 500;   // Farmer-Nummern je Container bzw. je Einfügen

/* Eigene Farmer-Nummer zum Anzeigen: „F-“ unterscheidet sie von den Nummern aus den Papieren (meist nur Ziffern) */
function ci_farmer_nr(int $nr): string { return sprintf('F-%04d', $nr); }

/* Nummer zum Vergleichen: ohne Rücksicht auf Groß- und Kleinschreibung, Leerzeichen, Punkte und Striche – „P-100“ und
   „p 100“, „12.345“ und „12 345“ sind jeweils dieselbe Nummer (Partienummern, Nummern aus den Papieren) */
function ci_nummer_norm(string $nummer): string
{
    return mb_strtolower((string)preg_replace('/[\s\x{00A0}\x{2010}-\x{2015}_.\/-]+/u', '', $nummer));
}
/* Schlüssel einer Nummer aus den Papieren: im Herkunftsland eindeutig ('' = keine Nummer, auch bei „-“ oder „.“) */
function ci_nummer_schluessel(string $land, string $nummer): string
{
    $n = ci_nummer_norm($nummer);
    return $n === '' ? '' : $land . ' ' . $n;
}
/* Nummern aus den Papieren der Farmer $liste: Schlüssel → Stelle des ersten Farmers damit (einmal je Anfrage bauen).
   Leere Schlüssel fehlen – sonst fielen alle Farmer mit „-“ als Nummer zu einem zusammen. */
function ci_nummern_index(array $liste): array
{
    $index = [];
    foreach ($liste as $i => $b) {
        $k = ci_nummer_schluessel($b['land'], $b['kennung']);
        if ($k !== '') $index[$k] ??= $i;
    }
    return $index;
}
/* Stelle eines anderen Farmers mit dieser Nummer aus den Papieren (archivierte zählen mit; null = keiner oder keine Nummer).
   $ausser = Stelle des Farmers selbst. */
function ci_nummer_vergeben(array $index, string $schluessel, ?int $ausser): ?int
{
    $i = $schluessel === '' ? null : $index[$schluessel] ?? null;
    return $i === $ausser ? null : $i;
}

/* Farmer-Nummern aus der Eingabe: Text (je Zeile, durch Komma, Semikolon oder Tabulator getrennt – so kommen sie aus einer
   Liste oder Tabelle) oder Liste. Leerzeichen innerhalb einer Nummer bleiben; Nummern ohne Inhalt („-“) fallen weg.
   Wirft InvalidArgumentException (422). */
function ci_nummern_lesen($v): array
{
    if (is_string($v)) $v = preg_split('/[\r\n,;\t]+/', $v);
    if (!is_array($v) || !array_is_list($v)) throw new InvalidArgumentException('Farmer-Nummern: ungültige Liste.');
    $aus = array_values(array_filter(array_map(fn($t) => eudr_text($t, 40, 'Farmer-Nummer'), $v), fn($t) => ci_nummer_norm($t) !== ''));
    if (count($aus) > CI_MAX_NUMMERN) throw new InvalidArgumentException('Höchstens ' . CI_MAX_NUMMERN . ' Farmer-Nummern auf einmal.');
    return $aus;
}
/* Farmer-Nummern eines Containers im Land $land auflösen – dieselbe Regel für die Vorschau und das Speichern. $ids = schon
   zugeordnete Farmer, $offen = schon vermerkte Nummern, $betriebe = gespeicherte Farmer, $index = ci_nummern_index($betriebe).
   Je Nummer der Farmer und ein Stand: bekannt (wird zugeordnet) · zugeordnet (ist es schon) · neu (unbekannt – wird vermerkt)
   · offen (ist schon vermerkt) · doppelt (steht weiter oben schon). */
function ci_nummern_aufloesen(array $nummern, string $land, array $ids, array $offen, array $betriebe, array $index): array
{
    $vermerkt = array_flip(array_map(fn($n) => ci_nummer_schluessel($land, $n), $offen));
    $gesehen = []; $zeilen = [];
    foreach ($nummern as $n) {
        $k = ci_nummer_schluessel($land, $n);
        $b = isset($index[$k]) ? $betriebe[$index[$k]] : null;
        $stand = isset($gesehen[$k]) ? 'doppelt' : ($b ? (in_array($b['id'], $ids, true) ? 'zugeordnet' : 'bekannt') : (isset($vermerkt[$k]) ? 'offen' : 'neu'));
        $gesehen[$k] = true;
        $zeilen[] = ['nummer' => $n, 'status' => $stand, 'betrieb' => $b['id'] ?? '', 'name' => $b['name'] ?? '', 'farmerNr' => $b ? ci_farmer_nr($b['nr']) : '', 'aktiv' => $b['aktiv'] ?? true];
    }
    return $zeilen;
}
/* Aufgelöste Nummern ($zeilen) an einem Container mit den Farmern $ids übernehmen: gefundene Farmer kommen dazu, vermerkt
   bleiben nur die unbekannten Nummern → ['betriebe', 'offeneNummern'] */
function ci_nummern_anwenden(array $ids, array $zeilen): array
{
    return ['betriebe' => array_values(array_unique([...$ids, ...array_filter(array_column($zeilen, 'betrieb'))])),
        'offeneNummern' => array_column(array_filter($zeilen, fn($z) => $z['status'] === 'neu'), 'nummer')];
}
/* Gespeicherte Farmer ($betriebe) den Containern zuordnen, die ihre Nummer aus den Papieren vermerkt haben – nur Container
   mit offener Bewertung, die nicht archiviert sind (abgeschlossene bleiben, wie sie sind, GR-106). Liefert die geänderte
   Liste und die Zahl der Container. */
function ci_offene_nummern_zuordnen(array $liste, array $betriebe, array $me): array
{
    $index = ci_nummern_index($betriebe);
    $n = 0;
    foreach ($liste as $i => $s) {
        if (!empty($s['abschluss']) || ($s['aktiv'] ?? true) === false || !$s['offeneNummern']) continue;
        $zeilen = ci_nummern_aufloesen($s['offeneNummern'], $s['land'], $s['betriebe'], [], $betriebe, $index);
        if (!array_filter(array_column($zeilen, 'betrieb'))) continue;
        $liste[$i] = ci_nummern_anwenden($s['betriebe'], $zeilen) + ['rev' => $s['rev'] + 1, 'geaendert' => eudr_wer($me)] + $s;
        $n++;
    }
    return [$liste, $n];
}
/* Neue Farmer eines Einlese-Durchgangs (alle Dateien, $dateien = Ergebnisse von eudr_datei_pruefen) mit derselben Nummer aus
   den Papieren: das zweite Vorkommen wird als Fehler seiner Datei gemeldet und nicht übernommen – beim Speichern scheiterte
   sonst der ganze Durchgang. Bekannte Farmer zählen nicht (sie werden zusammengeführt). */
function ci_doppelte_nummern_melden(array $dateien): array
{
    $gesehen = [];
    foreach ($dateien as $d => $datei) {
        foreach ($datei['orte'] as $o => $ort) {
            $k = $ort['bekannt'] === '' ? ci_nummer_schluessel($ort['land'], $ort['kennung']) : '';
            if ($k === '') continue;
            if (!isset($gesehen[$k])) { $gesehen[$k] = $ort['name']; continue; }
            $dateien[$d]['fehler'][] = $ort['name'] . ': gleiche Nummer „' . $ort['kennung'] . '“ aus den Papieren wie „' . $gesehen[$k] . '“ in dieser Auswahl – nicht übernommen.';
            unset($dateien[$d]['orte'][$o]);
        }
        $dateien[$d]['orte'] = array_values($dateien[$d]['orte']);
    }
    return $dateien;
}
/* Gesamtprüfung der Farmer eines Containers ($bs = Sichten, nach dem Abschluss der Schnappschuss): wie viele in Ordnung
   (Ampel grün), wie viele Nummern ohne Unterlagen, je Thema der Bewertung die Zahl der Farmer je Stufe (kritisch, offen;
   nur Stufen mit Farmern). Ampel: rot ohne Farmer, mit fehlenden Unterlagen oder einem roten Farmer; gelb, wenn einer gelb ist. */
function ci_farmer_pruefung(array $bs, array $offen): array
{
    $zahl = [];
    foreach ($bs as $b) foreach ($b['bewertung'] as $thema => $stufe) if ($stufe !== 'ok') $zahl[$thema][$stufe] = ($zahl[$thema][$stufe] ?? 0) + 1;
    $themen = array_map(fn($z) => array_filter(['kritisch' => $z['kritisch'] ?? 0, 'offen' => $z['offen'] ?? 0]), $zahl);
    $ampeln = array_count_values(array_column($bs, 'ampel'));
    $gesamt = count($bs) + count($offen);
    return ['gesamt' => $gesamt, 'inOrdnung' => $ampeln['gruen'] ?? 0, 'ohneUnterlagen' => count($offen), 'themen' => $themen,
        'ampel' => !$gesamt || $offen || isset($ampeln['rot']) ? 'rot' : (isset($ampeln['gelb']) ? 'gelb' : 'gruen')];
}
/* Vermerkte Nummern aller Container für die Gesamtübersicht: je Nummer (im Land) einmal, mit den Containern, die sie nennen.
   Nummern, zu denen es inzwischen einen Farmer gibt ($index = ci_nummern_index), fehlen – auch wenn ein abgeschlossener
   Container sie weiter vermerkt hat (sein Vermerk bleibt, GR-106). */
function ci_offene_nummern(array $sendungen, array $index): array
{
    $aus = [];
    foreach ($sendungen as $s) foreach ($s['offeneNummern'] as $n) {
        $k = ci_nummer_schluessel($s['land'], $n);
        if (isset($index[$k])) continue;
        $aus[$k] ??= ['nummer' => $n, 'land' => $s['land'], 'sendungen' => []];
        $aus[$k]['sendungen'][] = $s['id'];
    }
    return array_values($aus);
}
