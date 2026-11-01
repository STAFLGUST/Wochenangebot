<?php
declare(strict_types=1);
/* Controlling · Kundenbild – Schnittstelle für das CRM (GR-101; Leser „crm“ in regeln/datenverantwortung.toml).
   Umsatz und Menge je Kunde aus den importierten Umsatzdaten (module/controlling/umsatzdaten.php) – nie EK-Werte, DB oder
   Spanne – und die Signale, mit denen ein Verkäufer handeln kann. Stichtag ist der letzte Tag mit Umsatzdaten (Stand).
   Kauf = berechnete Position mit Menge > 0; Umsatz und Menge zählen wie in der Auswertung alle berechneten Positionen
   (auch Gutschriften), Positionen ohne Berechnung (Leergut) nie.
     Bestellpause   dieselbe Regel wie die Umsatzstatistik (umsatz_pause_pruefen: Stammkunde der letzten 182 Tage, Pause
                    mindestens doppelt so lang wie üblich, länger als jede frühere, mindestens 7 Tage)
     kauft weniger  Menge der letzten 91 Tage mindestens 20 % unter denselben Tagen im Vorjahr; ohne Vorjahr (weniger als
                    3 Kauftage dort) unter den 91 Tagen davor – verglichen wird nur mit mindestens 3 Kauftagen
     Artikel weg    ein Artikel, den der Kunde in 365 Tagen an mindestens 3 Tagen gekauft hat, seit mindestens 6 Wochen und
                    dem Dreifachen seines üblichen Abstands nicht mehr – obwohl der Kunde mindestens 14 Tage danach noch
                    anderes gekauft hat (sonst ist es eine Bestellpause des ganzen Kunden)
     neu            erster Kauf in den letzten 91 Tagen, die 365 Tage davor nichts – nur, wenn die Daten so weit zurückreichen
                    (Kunden-Pop-up zusätzlich je Artikel: neu, kauft weniger ab −30 %, nicht mehr gekauft)
   Welche Werte ein Mitarbeiter sieht (€ bzw. kg), entscheidet das CRM (crm.umsatz_euro, crm.umsatz_kg); hier wird nur
   gerechnet. Je Anfrage eine Lesung der Monate (zwei Jahre bis zum Stand). Wird vom CRM bei Bedarf geladen (require_once). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const KUNDENBILD_TAGE = 730;               // gelesener Zeitraum: zwei Jahre bis zum Stand (12 Monate mit Vorjahr)
const KUNDENBILD_FENSTER = 91;             // „letzte 3 Monate“
const KUNDENBILD_WENIGER = 0.2;            // kauft weniger: mindestens 20 % weniger Menge
const KUNDENBILD_VERGLEICH_KAUFTAGE = 3;   // Vergleichszeitraum mit mindestens so vielen Kauftagen
const KUNDENBILD_ARTIKEL_KAUFTAGE = 3;     // Artikel weg: vorher an mindestens 3 Tagen gekauft …
const KUNDENBILD_ARTIKEL_PAUSE = 42;       // … seit mindestens 6 Wochen nicht mehr …
const KUNDENBILD_ARTIKEL_FAKTOR = 3;       // … und mindestens dreimal so lange wie sein üblicher Abstand …
const KUNDENBILD_ARTIKEL_DANACH = 14;      // … obwohl der Kunde mindestens 14 Tage später noch etwas gekauft hat
const KUNDENBILD_ARTIKEL_WENIGER = 0.3;    // Artikel kauft weniger: mindestens 30 % weniger Menge (Kunden-Pop-up)
const KUNDENBILD_NEU_RUHE = 365;           // neu: die 365 Tage vor dem ersten Kauf ohne Kauf
const KUNDENBILD_TOP_ARTIKEL = 8;          // Top-Artikel im Kunden-Pop-up
const KUNDENBILD_AUFFAELLIG = 5;           // je Gruppe „Auffällig bei Artikeln“ im Kunden-Pop-up

/* Tagnummer → Datum (JJJJ-MM-TT) */
function kundenbild_datum(int $t): string { return gmdate('Y-m-d', $t * 86400); }
/* Gleicher Tag ein Jahr früher (29.02. → 28.02.) */
function kundenbild_vorjahr(string $d): string
{
    $j = (int)substr($d, 0, 4) - 1; $m = (int)substr($d, 5, 2);
    return sprintf('%04d-%02d-%02d', $j, $m, min((int)substr($d, 8, 2), (int)gmdate('t', (int)gmmktime(12, 0, 0, $m, 1, $j))));
}

/* Umsatzzeilen der zwei Jahre bis zum Stand zusammenfassen – je Kunde und (auf Wunsch) je Kunde und Artikel.
   $nur: Kundennummern (beliebige Schreibweise) oder null = alle. Umsatz und Menge je Artikel über alle Kunden der letzten
   365 Tage zählen immer mit (Ø Preis aller Kunden für das Preisniveau). Ergebnis je Anfrage zwischengespeichert.
   Zeitfenster als Tagnummern (e = Stand): j365 [e−364, e], v365 [e−729, e−365], j91 [e−90, e], v91 [e−455, e−365],
   p91 [e−181, e−91], p182 [e−181, e] (Bestellpause); monat/jahr bis zum Stand und dieselben Tage im Vorjahr. */
function kundenbild_lesen(?array $nur, bool $mitArtikeln): ?array
{
    static $cache = [];
    $schluessel = json_encode([$nur, $mitArtikeln]);
    if (array_key_exists($schluessel, $cache)) return $cache[$schluessel];
    $index = umsatzdaten_index();
    $stand = umsatzdaten_stand($index);
    if (!$stand['bis']) return $cache[$schluessel] = null;
    $d = (string)$stand['bis'];
    $e = umsatz_tagnummer($d);
    $vjD = kundenbild_vorjahr($d);
    $vjE = umsatz_tagnummer($vjD);
    $grenzen = [
        'j365' => [$e - 364, $e], 'v365' => [$e - 729, $e - 365], 'j91' => [$e - 90, $e], 'v91' => [$e - 455, $e - 365], 'p91' => [$e - 181, $e - 91],
        'p182' => [$e - UMSATZ_PAUSE_TAGE + 1, $e],
        'monat' => [umsatz_tagnummer(substr($d, 0, 8) . '01'), $e], 'vjMonat' => [umsatz_tagnummer(substr($vjD, 0, 8) . '01'), $vjE],
        'jahr' => [umsatz_tagnummer(substr($d, 0, 4) . '-01-01'), $e], 'vjJahr' => [umsatz_tagnummer(substr($vjD, 0, 4) . '-01-01'), $vjE],
    ];
    $beginn = min($e - KUNDENBILD_TAGE + 1, $grenzen['vjJahr'][0]);
    $soll = null;
    if ($nur !== null) { $soll = []; foreach ($nur as $n) $soll[code_key((string)$n)] = true; }
    $leer = fn() => array_fill_keys(array_keys($grenzen), [0, 0]);
    // je Artikel: im Kunden-Pop-up (ein Kunde) zwei Jahre (mit Vorjahr der 365 Tage), sonst die letzten 455 Tage (Vorjahr der 91 Tage)
    $einer = $soll !== null && count($soll) === 1;
    $artVon = $einer ? $grenzen['v365'][0] : $grenzen['v91'][0];
    $artFenster = ['j365', 'v365', 'j91', 'v91', 'p91'];
    $kunden = []; $artikelAlle = []; $ck = [];
    foreach (umsatzdaten_monatsfolge(substr(kundenbild_datum($beginn), 0, 7), substr($d, 0, 7)) as $m) {
        if (!isset($index['monate'][$m])) continue;
        $basis = umsatz_tagnummer($m . '-01') - 1;
        foreach (umsatzdaten_monat($m) as $z) {
            if ($z[9] !== 1) continue;   // ohne Berechnung (Leergut) zählt nie
            $t = $basis + $z[0];
            if ($t < $beginn || $t > $e) continue;
            if ($t >= $grenzen['j365'][0]) { $aa = &$artikelAlle[(string)$z[2]]; $aa[0] = ($aa[0] ?? 0) + $z[5]; $aa[1] = ($aa[1] ?? 0) + $z[4]; unset($aa); }
            $kk = $ck[$z[1]] ??= code_key((string)$z[1]);
            if ($soll !== null && !isset($soll[$kk])) continue;
            $k = &$kunden[$kk];
            if ($k === null) $k = ['nr' => (string)$z[1], 'mon' => [], 'w' => $leer(), 'tage' => [], 'art' => []];
            $k['mon'][$m][0] = ($k['mon'][$m][0] ?? 0) + $z[5];
            $k['mon'][$m][1] = ($k['mon'][$m][1] ?? 0) + $z[4];
            foreach ($grenzen as $w => [$von, $bis]) if ($t >= $von && $t <= $bis) { $k['w'][$w][0] += $z[5]; $k['w'][$w][1] += $z[4]; }
            if ($z[4] > 0) $k['tage'][$t] = true;
            if ($mitArtikeln && $t >= $artVon) {
                $a = &$k['art'][(string)$z[2]];
                if ($a === null) $a = ['tage' => [], 'w' => array_fill_keys($artFenster, [0, 0])];
                foreach ($artFenster as $w) if ($t >= $grenzen[$w][0] && $t <= $grenzen[$w][1]) { $a['w'][$w][0] += $z[5]; $a['w'][$w][1] += $z[4]; }
                if ($z[4] > 0) $a['tage'][$t] = true;
                unset($a);
            }
            unset($k);
        }
    }
    return $cache[$schluessel] = ['stand' => $d, 'ende' => $e, 'von' => $stand['von'], 'grenzen' => $grenzen, 'kunden' => $kunden, 'artikelAlle' => $artikelAlle];
}

/* Kauftage (Tagnummern, aufsteigend) eines Bereichs */
function kundenbild_tage(array $set, int $von, int $bis): array
{
    $l = [];
    foreach ($set as $t => $_) if ($t >= $von && $t <= $bis) $l[] = (int)$t;
    sort($l);
    return $l;
}

/* Signale eines Kunden (Liste): pause, weniger, weg (Artikel), neu – mit Zahlen (Cent bzw. Tausendstel kg); das CRM blendet aus,
   was der Mitarbeiter nicht sehen darf. Für „weg“ braucht es die Artikel (kundenbild_lesen mit Artikeln). */
function kundenbild_signale(array $k, array $L): array
{
    $e = $L['ende']; $g = $L['grenzen'];
    $out = [];
    // Bestellpause: dieselbe Regel wie die Umsatzstatistik (Kauftage der letzten 182 Tage)
    $p = umsatz_pause_pruefen(kundenbild_tage($k['tage'], $g['p182'][0], $e), $e);
    if ($p && $p['auffaellig'])
        $out[] = ['art' => 'pause', 'letzter' => kundenbild_datum($p['letzter']), 'pause' => $p['pause'], 'abstand' => round($p['mittel'], 1), 'kauftage' => $p['kauftage'],
                  'umsatzMonat' => (int)round($k['w']['p182'][0] / $p['kauftage'] * 30.4375 / $p['mittel']),
                  'mengeMonat' => (int)round($k['w']['p182'][1] / $p['kauftage'] * 30.4375 / $p['mittel'])];
    // kauft weniger: letzte 91 Tage gegen Vorjahr, ohne Vorjahr gegen die 91 Tage davor
    $basis = count(kundenbild_tage($k['tage'], $g['v91'][0], $g['v91'][1])) >= KUNDENBILD_VERGLEICH_KAUFTAGE ? 'v91'
        : (count(kundenbild_tage($k['tage'], $g['p91'][0], $g['p91'][1])) >= KUNDENBILD_VERGLEICH_KAUFTAGE ? 'p91' : null);
    if ($basis !== null && $k['w'][$basis][1] > 0) {
        $anteil = ($k['w']['j91'][1] - $k['w'][$basis][1]) / $k['w'][$basis][1];
        if ($anteil <= -KUNDENBILD_WENIGER) {
            $s = ['art' => 'weniger', 'basis' => $basis === 'v91' ? 'vorjahr' : 'davor', 'anteil' => round($anteil, 3),
                  'menge' => $k['w']['j91'][1], 'mengeBasis' => $k['w'][$basis][1], 'umsatz' => $k['w']['j91'][0], 'umsatzBasis' => $k['w'][$basis][0]];
            // vor allem: der Artikel mit dem größten Mengenrückgang
            $best = null;
            foreach ($k['art'] as $nr => $a) {
                $minus = $a['w'][$basis][1] - $a['w']['j91'][1];
                if ($minus > 0 && ($best === null || $minus > $best[1])) $best = [(string)$nr, $minus];
            }
            if ($best) $s['vorAllem'] = kundenbild_artikel_name($best[0]) + ['nr' => $best[0]];
            $out[] = $s;
        }
    }
    // Artikel nicht mehr gekauft
    $weg = kundenbild_artikel_weg($k, $L);
    if ($weg) $out[] = ['art' => 'weg', 'anzahl' => count($weg), 'artikel' => array_slice($weg, 0, 3)];
    // neu dabei
    $erster = kundenbild_erster($k['tage'], $L);
    if ($erster !== null)
        $out[] = ['art' => 'neu', 'erster' => kundenbild_datum($erster), 'kauftage' => count(kundenbild_tage($k['tage'], $erster, $e)), 'umsatz' => $k['w']['j91'][0], 'menge' => $k['w']['j91'][1]];
    return $out;
}

/* Erster Kauf, wenn er „neu“ ist: in den letzten 91 Tagen, die 365 Tage davor kein Kauf – und die Daten reichen so weit zurück
   (sonst wäre jeder Kunde am Anfang der Daten „neu“). null = nicht neu. */
function kundenbild_erster(array $tage, array $L): ?int
{
    $g = $L['grenzen'];
    $l = kundenbild_tage($tage, $g['j91'][0] - KUNDENBILD_NEU_RUHE, $L['ende']);
    if (!$l || $l[0] < $g['j91'][0]) return null;
    return $L['von'] !== null && umsatz_tagnummer((string)$L['von']) <= $l[0] - KUNDENBILD_NEU_RUHE ? $l[0] : null;
}

/* Name und Fleischart eines Artikels aus den Artikelstammdaten (ohne Stammsatz „Artikel <Nr>“) */
function kundenbild_artikel_name(string $nr): array
{
    $x = umsatz_artikel($nr);
    return ['name' => $x && $x['name'] !== '' ? $x['name'] : 'Artikel ' . $nr, 'fleischart' => $x ? (string)$x['fa'] : ''];
}

/* Artikel, die der Kunde nicht mehr kauft (Regel oben), meistgekaufte (Umsatz der 365 Tage) zuerst */
function kundenbild_artikel_weg(array $k, array $L): array
{
    if (!$k['tage']) return [];
    $e = $L['ende']; $von = $L['grenzen']['j365'][0];
    $letzterKauf = (int)max(array_keys($k['tage']));
    $out = [];
    foreach ($k['art'] as $nr => $a) {
        $l = kundenbild_tage($a['tage'], $von, $e);
        $n = count($l);
        if ($n < KUNDENBILD_ARTIKEL_KAUFTAGE) continue;
        $mittel = ($l[$n - 1] - $l[0]) / ($n - 1);
        $pause = $e - $l[$n - 1];
        if ($pause < KUNDENBILD_ARTIKEL_PAUSE || $pause < KUNDENBILD_ARTIKEL_FAKTOR * $mittel || $letzterKauf < $l[$n - 1] + KUNDENBILD_ARTIKEL_DANACH) continue;
        $out[] = ['nr' => (string)$nr] + kundenbild_artikel_name((string)$nr) + ['zuletzt' => kundenbild_datum($l[$n - 1]), 'pause' => $pause, 'abstand' => round($mittel, 1),
                  'kauftage' => $n, 'umsatz' => $a['w']['j365'][0], 'menge' => $a['w']['j365'][1]];
    }
    usort($out, fn($x, $y) => $y['umsatz'] <=> $x['umsatz'] ?: $y['menge'] <=> $x['menge'] ?: strcmp($x['nr'], $y['nr']));
    return $out;
}

/* Monate (JJJJ-MM) der letzten 12 Monate bis zum Monat des Stands */
function kundenbild_monate(string $stand): array
{
    $bis = substr($stand, 0, 7);
    return umsatzdaten_monatsfolge(umsatz_monat_plus($bis, -11), $bis);
}

/* Kennzahlen eines Kunden für Cockpit und Liste: Fenster als [Umsatz, Menge], 12 Monate, letzter Kauf, Kauftage, Signale */
function kundenbild_zusammenfassung(array $k, array $L, bool $mitSignalen): array
{
    $monate = kundenbild_monate($L['stand']);
    $kauf = kundenbild_tage($k['tage'], $L['grenzen']['j365'][0], $L['ende']);
    return ['nr' => $k['nr'], 'w' => $k['w'], 'reihe' => array_map(fn($m) => $k['mon'][$m] ?? [0, 0], $monate),
            'zuletzt' => $k['tage'] ? kundenbild_datum((int)max(array_keys($k['tage']))) : null, 'kauftage' => count($kauf),
            'signale' => $mitSignalen ? kundenbild_signale($k, $L) : []];
}

/* Cockpit: alle Kunden bzw. nur $nur (Kundennummern) mit Kennzahlen und Signalen. Schlüssel = Kundennummer ohne führende Nullen
   (code_key). Ohne Umsatzdaten: stand null. */
function kundenbild_kunden(?array $nur = null): array
{
    $L = kundenbild_lesen($nur, true);
    if ($L === null) return ['stand' => null, 'von' => null, 'monat' => null, 'monate' => [], 'vorjahr' => null, 'kunden' => []];
    $out = [];
    foreach ($L['kunden'] as $kk => $k) $out[(string)$kk] = kundenbild_zusammenfassung($k, $L, true);
    return ['stand' => $L['stand'], 'von' => $L['von'], 'monat' => substr($L['stand'], 0, 7), 'monate' => kundenbild_monate($L['stand']),
            'vorjahr' => kundenbild_vorjahr($L['stand']), 'kunden' => $out];
}

/* Kunden-Pop-up: ein Kunde mit Kennzahlen (365 Tage mit Vorjahr), Monaten mit Vorjahr, Rhythmus, Preisniveau, Top-Artikeln
   und „Auffällig bei Artikeln“ (nicht mehr gekauft, kauft weniger, neu). null = keine Umsatzdaten zu dieser Nummer. */
function kundenbild_kunde(string $nr): ?array
{
    $L = kundenbild_lesen([$nr], true);
    if ($L === null || !isset($L['kunden'][code_key($nr)])) return $L === null ? null : ['stand' => $L['stand'], 'von' => $L['von'], 'kunde' => null];
    $k = $L['kunden'][code_key($nr)];
    $g = $L['grenzen']; $e = $L['ende'];
    $o = kundenbild_zusammenfassung($k, $L, true);
    // Monate mit Vorjahr (12 Monate bis zum Monat des Stands; Vorjahr = derselbe Monat ein Jahr früher, voll)
    $o['monate'] = array_map(fn($m) => ['monat' => $m, 'jetzt' => $k['mon'][$m] ?? [0, 0], 'vj' => $k['mon'][umsatz_monat_plus($m, -12)] ?? [0, 0]], kundenbild_monate($L['stand']));
    // Rhythmus: Ø Abstand der Kauftage in 365 Tagen und die häufigsten Wochentage (je mindestens ein Viertel der Kauftage)
    $kauf = kundenbild_tage($k['tage'], $g['j365'][0], $e);
    $n = count($kauf);
    $wt = [];
    foreach ($kauf as $t) { $w = (int)gmdate('N', $t * 86400); $wt[$w] = ($wt[$w] ?? 0) + 1; }
    arsort($wt);
    $o['rhythmus'] = ['kauftage' => $n, 'abstand' => $n > 1 ? round(($kauf[$n - 1] - $kauf[0]) / ($n - 1), 1) : null,
                      'wochentage' => array_slice(array_keys(array_filter($wt, fn($c) => $n >= 4 && $c / $n >= 0.25)), 0, 3)];
    // Preisniveau: was er gezahlt hat gegenüber dem Ø Preis aller Kunden für dieselben Mengen (365 Tage, Artikel mit Menge)
    $eigen = 0; $alle = 0;
    foreach ($k['art'] as $anr => $a) {
        $aa = $L['artikelAlle'][(string)$anr] ?? null;
        if ($a['w']['j365'][1] <= 0 || !$aa || $aa[1] <= 0) continue;
        $eigen += $a['w']['j365'][0];
        $alle += $a['w']['j365'][1] * $aa[0] / $aa[1];
    }
    $o['preisniveau'] = $alle > 0 ? round($eigen / $alle - 1, 4) : null;
    // Top-Artikel (Umsatz der 365 Tage) mit Vorjahr (365 Tage davor) und Umsatz/Menge aller Kunden (für deren Ø Preis)
    $top = [];
    foreach ($k['art'] as $anr => $a) {
        if ($a['w']['j365'] === [0, 0]) continue;
        $tage = kundenbild_tage($a['tage'], $g['j365'][0], $e);
        $aa = $L['artikelAlle'][(string)$anr] ?? null;
        $top[] = ['nr' => (string)$anr] + kundenbild_artikel_name((string)$anr) + ['j365' => $a['w']['j365'], 'v365' => $a['w']['v365'],
                  'zuletzt' => $tage ? kundenbild_datum($tage[count($tage) - 1]) : null, 'alle' => $aa && $aa[1] > 0 ? $aa : null];
    }
    usort($top, fn($x, $y) => $y['j365'][0] <=> $x['j365'][0] ?: $y['j365'][1] <=> $x['j365'][1] ?: strcmp($x['nr'], $y['nr']));
    $o['artikel'] = array_slice($top, 0, KUNDENBILD_TOP_ARTIKEL);
    $o['artikelGesamt'] = count($top);
    // Auffällig bei Artikeln (ein Artikel, der nicht mehr gekauft wird, steht nicht zusätzlich unter „kauft weniger“)
    $weg = kundenbild_artikel_weg($k, $L);
    $istWeg = array_flip(array_column($weg, 'nr'));
    $weniger = []; $neu = [];
    foreach ($k['art'] as $anr => $a) {
        if (isset($istWeg[(string)$anr])) continue;
        $basis = count(kundenbild_tage($a['tage'], $g['v91'][0], $g['v91'][1])) >= 2 ? 'v91' : (count(kundenbild_tage($a['tage'], $g['p91'][0], $g['p91'][1])) >= 2 ? 'p91' : null);
        if ($basis !== null && $a['w'][$basis][1] > 0 && $a['w']['j91'][1] > 0 && $a['w']['j91'][1] <= (1 - KUNDENBILD_ARTIKEL_WENIGER) * $a['w'][$basis][1])
            $weniger[] = ['nr' => (string)$anr] + kundenbild_artikel_name((string)$anr) + ['basis' => $basis === 'v91' ? 'vorjahr' : 'davor',
                          'anteil' => round(($a['w']['j91'][1] - $a['w'][$basis][1]) / $a['w'][$basis][1], 3), 'menge' => $a['w']['j91'][1], 'mengeBasis' => $a['w'][$basis][1],
                          'umsatz' => $a['w']['j91'][0], 'umsatzBasis' => $a['w'][$basis][0]];
        $erster = kundenbild_erster($a['tage'], $L);
        if ($erster !== null)
            $neu[] = ['nr' => (string)$anr] + kundenbild_artikel_name((string)$anr) + ['erster' => kundenbild_datum($erster), 'kauftage' => count(kundenbild_tage($a['tage'], $erster, $e)),
                      'umsatz' => $a['w']['j91'][0], 'menge' => $a['w']['j91'][1]];
    }
    usort($weniger, fn($x, $y) => ($y['mengeBasis'] - $y['menge']) <=> ($x['mengeBasis'] - $x['menge']) ?: strcmp($x['nr'], $y['nr']));
    usort($neu, fn($x, $y) => $y['umsatz'] <=> $x['umsatz'] ?: $y['menge'] <=> $x['menge']);
    $o['auffaellig'] = ['weg' => array_slice($weg, 0, KUNDENBILD_AUFFAELLIG), 'weniger' => array_slice($weniger, 0, KUNDENBILD_AUFFAELLIG),
                        'neu' => array_slice($neu, 0, KUNDENBILD_AUFFAELLIG)];
    return ['stand' => $L['stand'], 'von' => $L['von'], 'vorjahr' => kundenbild_vorjahr($L['stand']), 'kunde' => $o];
}
