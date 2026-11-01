<?php
declare(strict_types=1);
/* Controlling · Umsatzauswertung aus den importierten Umsatzdaten (module/controlling/umsatzdaten.php).
   Filter: Zeitraum (Monate), Vertreter, Kundengruppe, Kunde, Artikelgruppe (VK-Gruppe), Fleischart, Artikel.
   Gliederung nach Monat, Quartal, Jahr, Kalenderwoche, Vertreter, Kundengruppe, Kunde, Artikelgruppe, Fleischart oder Artikel,
   jeweils mit Vorjahr (gleicher Zeitraum ein Jahr früher; reicht der Zeitraum bis zum letzten Tag mit Daten, endet auch das
   Vorjahr an diesem Tag). Kennzahlen: Umsatz, Menge, Kolli, Positionen, Kunden; mit controlling.umsatz_ek und
   bestand.einkaufspreise (beide – GR-008: Einkaufspreise nur mit dem EK-Recht; dazu ein eigenes Recht für Margen) zusätzlich
   EK-Wert und Umsatz mit EK (Deckungsbeitrag = Umsatz mit EK − EK-Wert, Spanne = DB ÷ Umsatz mit EK) – ohne das Recht
   verlassen diese Werte den Server nicht (GR-103).
   Zuordnung zu Vertreter (Hauptvertreter des Kunden), Kundengruppe, Artikelgruppe und Fleischart nach den heutigen
   Stammdaten der Verwaltung (nur lesend: customers_load, gruppen_load, Artikelstammdaten); die Umsatzzeilen selbst bleiben
   so, wie sie importiert wurden. Nummern ohne Stammsatz erscheinen mit ihrer Nummer, „ohne …“ steht als Wert „_“.
   Rangliste (nicht bei Zeit): Kennzahl und Richtung, ABC-Analyse der Kennzahl und mit Vorjahr „neu“ (Kauf jetzt, nicht im
   Vorjahr) bzw. „verloren“ (Kauf im Vorjahr, jetzt nicht) je Zeile – auf Wunsch nur diese Zeilen (nur=neu|verloren).
   Kauf = berechnete Position mit Menge > 0 (eine Gutschrift allein ist kein Kauf). Bestellpausen: Stammkunden, die ungewöhnlich
   lange nichts gekauft haben (umsatz_pausen, Aktion controlling_umsatz_pausen). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const UMSATZ_GLIEDERUNG = ['monat' => 'Monat', 'quartal' => 'Quartal', 'jahr' => 'Jahr', 'kw' => 'Kalenderwoche', 'vertreter' => 'Vertreter',
                           'kundengruppe' => 'Kundengruppe', 'kunde' => 'Kunde', 'vkgruppe' => 'Artikelgruppe', 'fleischart' => 'Fleischart', 'artikel' => 'Artikel'];
const UMSATZ_ZEITLICH = ['monat', 'quartal', 'jahr', 'kw'];
const UMSATZ_FILTER = ['v' => 'vertreter', 'kg' => 'kundengruppe', 'k' => 'kunde', 'ag' => 'vkgruppe', 'fa' => 'fleischart', 'a' => 'artikel'];
const UMSATZ_ZEILEN_MAX = 2000;
const UMSATZ_MONATE_MAX = 120;
const UMSATZ_OHNE = '_';   // Filter- und Gliederungswert für „ohne Vertreter“, „ohne Kundengruppe“ …
/* Kennzahl der Rangliste: Umsatz, Menge, DB (€ = Umsatz mit EK − EK-Wert) oder Spanne (÷ Umsatz mit EK); DB und Spanne
   nur mit EK-Recht (GR-008 – auch die Reihenfolge allein verriete sie). Für Spanne kommen Zeilen mit wenig Umsatz
   mit EK (unter 0,1 % der Summe, mindestens 100 €) ans Ende, sonst stünden Einzelpositionen mit Zufallsspannen oben. */
const UMSATZ_RANG = ['umsatz', 'menge', 'db', 'spanne'];
const UMSATZ_RANG_ANTEIL_MIN = 0.001;
const UMSATZ_RANG_CENT_MIN = 10000;
/* ABC-Analyse: die größten Zeilen, die zusammen 80 % der Kennzahl bringen, sind A, bis 95 % B, der Rest C (die Zeile, mit der die
   Grenze überschritten wird, gehört noch zur oberen Klasse). Grundlage ist die Summe der positiven Werte; Zeilen mit Wert ≤ 0
   sind C. Nur für Summen (Umsatz, Menge, DB) – Spanne ist kein Anteil. */
const UMSATZ_ABC = ['A' => 0.8, 'B' => 0.95];
const UMSATZ_ABC_RANG = ['umsatz', 'menge', 'db'];
const UMSATZ_NUR = ['', 'neu', 'verloren'];

/* Stammdaten für Zuordnung und Namen (nur lesend, Eigentümer Verwaltung) */
function umsatz_stamm(): array
{
    static $s = null;
    if ($s !== null) return $s;
    $kunden = [];
    foreach (customers_load()['customers'] as $c) {
        $nr = trim((string)($c['nr'] ?? ''));
        if ($nr === '') continue;
        $kunden[code_key($nr)] = ['name' => (string)($c['firma'] ?? ''), 'ort' => trim((string)($c['plz'] ?? '') . ' ' . (string)($c['ort'] ?? '')),
                                  'vertreter' => (string)($c['vertreter'] ?? ''), 'gruppe' => (string)($c['gruppe'] ?? '')];
    }
    $artikel = [];
    foreach ((store_read('stammdaten')['articles'] ?? []) as $a) {
        if (!is_array($a) || !isset($a['code'])) continue;
        $artikel[code_key((string)$a['code'])] = ['name' => (string)($a['name'] ?? ''), 'vk' => (string)($a['vkGruppe'] ?? ''), 'fa' => (string)($a['category'] ?? '')];
    }
    $liste = function (string $l): array { $o = []; foreach (gruppen_load($l)['groups'] as $g) if (is_array($g) && isset($g['nr'])) $o[(string)$g['nr']] = $g; return $o; };
    return $s = ['kunden' => $kunden, 'artikel' => $artikel, 'vertreter' => $liste('vertreter'), 'kundengruppen' => $liste('kundengruppen'), 'vkgruppen' => $liste('vkgruppen')];
}
function umsatz_kunde(string $nr): ?array { return umsatz_stamm()['kunden'][code_key($nr)] ?? null; }
function umsatz_artikel(string $nr): ?array { return umsatz_stamm()['artikel'][code_key($nr)] ?? null; }
function umsatz_wert(string $v): string { return $v === '' ? UMSATZ_OHNE : $v; }

/* Merkmal eines Kunden bzw. Artikels für Filter und Gliederung */
function umsatz_merkmal(string $dim, string $kunde, string $artikel): string
{
    switch ($dim) {
        case 'kunde': return $kunde;
        case 'artikel': return $artikel;
        case 'vertreter': return umsatz_wert((string)(umsatz_kunde($kunde)['vertreter'] ?? ''));
        case 'kundengruppe': return umsatz_wert((string)(umsatz_kunde($kunde)['gruppe'] ?? ''));
        case 'vkgruppe': return umsatz_wert((string)(umsatz_artikel($artikel)['vk'] ?? ''));
        case 'fleischart': return umsatz_wert((string)(umsatz_artikel($artikel)['fa'] ?? ''));
    }
    throw new LogicException('Unbekanntes Merkmal.');
}

/* Anfrage prüfen: Zeitraum, Gliederung, Vorjahr, Filter (kommagetrennt) */
function umsatz_anfrage(array $q, array $stand): array
{
    $bisStd = $stand['bis'] ? substr($stand['bis'], 0, 7) : date('Y-m');
    $von = (string)($q['von'] ?? substr($bisStd, 0, 4) . '-01');
    $bis = (string)($q['bis'] ?? $bisStd);
    if (!umsatzdaten_monat_gueltig($von) || !umsatzdaten_monat_gueltig($bis) || $von > $bis) throw new InvalidArgumentException('Bitte einen gültigen Zeitraum wählen (von … bis).');
    if (count(umsatzdaten_monatsfolge($von, $bis)) > UMSATZ_MONATE_MAX) throw new InvalidArgumentException('Der Zeitraum darf höchstens ' . UMSATZ_MONATE_MAX / 12 . ' Jahre umfassen.');
    $nach = (string)($q['nach'] ?? 'monat');
    if (!isset(UMSATZ_GLIEDERUNG[$nach])) throw new InvalidArgumentException('Unbekannte Gliederung.');
    $filter = [];
    foreach (UMSATZ_FILTER as $p => $dim) {
        $roh = (string)($q[$p] ?? '');
        if ($roh === '') continue;
        $werte = array_values(array_unique(explode(',', $roh)));
        if (count($werte) > 2000) throw new InvalidArgumentException('Zu viele Werte in einem Filter.');
        foreach ($werte as $w) if ($w !== UMSATZ_OHNE && !preg_match('#^[0-9A-Za-z._/-]{1,20}$#u', $w) && !($dim === 'fleischart' && in_array($w, CATEGORIES, true)))
            throw new InvalidArgumentException('Ungültiger Wert im Filter.');
        $filter[$dim] = array_fill_keys($werte, true);
    }
    $rang = (string)($q['rang'] ?? 'umsatz');
    if (!in_array($rang, UMSATZ_RANG, true)) throw new InvalidArgumentException('Unbekannte Kennzahl der Rangliste.');
    $vj = ($q['vj'] ?? '1') !== '0';
    $nur = (string)($q['nur'] ?? '');
    if (!in_array($nur, UMSATZ_NUR, true)) throw new InvalidArgumentException('Unbekannte Auswahl der Rangliste (neu oder verloren).');
    if ($nur !== '' && (!$vj || in_array($nach, UMSATZ_ZEITLICH, true))) throw new InvalidArgumentException('Neu und verloren gibt es nur mit Vorjahr und nicht bei einer Gliederung nach Zeit.');
    return ['von' => $von, 'bis' => $bis, 'nach' => $nach, 'vj' => $vj, 'filter' => $filter, 'rang' => $rang, 'auf' => ($q['auf'] ?? '0') === '1', 'nur' => $nur];
}

function umsatz_monat_plus(string $m, int $n): string
{
    $j = (int)substr($m, 0, 4); $mo = (int)substr($m, 5, 2) + $n;
    while ($mo < 1) { $mo += 12; $j--; }
    while ($mo > 12) { $mo -= 12; $j++; }
    return sprintf('%04d-%02d', $j, $mo);
}

/* Schlüssel einer zeitlichen Gliederung; $verschieben: Vorjahreswert dem Schlüssel des laufenden Jahres zuordnen */
function umsatz_zeitschluessel(string $nach, string $m, int $tag, int $verschieben): string
{
    $j = (int)substr($m, 0, 4) + $verschieben;
    switch ($nach) {
        case 'monat': return sprintf('%04d', $j) . substr($m, 4);
        case 'quartal': return sprintf('%04d-Q%d', $j, intdiv((int)substr($m, 5, 2) - 1, 3) + 1);
        case 'jahr': return sprintf('%04d', $j);
        case 'kw':
            $t = (int)mktime(12, 0, 0, (int)substr($m, 5, 2), $tag, (int)substr($m, 0, 4));
            return sprintf('%04d-W%02d', (int)date('o', $t) + $verschieben, (int)date('W', $t));
    }
    throw new LogicException('Keine zeitliche Gliederung.');
}

function umsatz_leer(): array { return ['umsatz' => 0, 'menge' => 0, 'kolli' => 0, 'pos' => 0, 'ek' => 0, 'umsatzEk' => 0, 'posOhne' => 0, 'mengeOhne' => 0]; }

/* Zeilen eines Zeitraums zusammenzählen. $ziel: Zeilen der Gliederung (mit Kunden je Zeile), $reihe: Werte je Monat;
   $verschieben = 1 für das Vorjahr (Schlüssel und Monate dem laufenden Zeitraum zugeordnet). $bisTag: letzter Tag im
   letzten Monat (Vorjahr bis zum gleichen Tag). $kunden/$artikel: Nummern mit berechnetem Umsatz (Anzahl in der Summe). */
function umsatz_zaehlen(array $a, array $index, string $von, string $bis, int $verschieben, ?int $bisTag, array &$ziel, array &$reihe, array &$kunden, array &$artikel): void
{
    $zeitlich = in_array($a['nach'], UMSATZ_ZEITLICH, true);
    $ok = []; $gk = [];   // Filterergebnis und Gliederungsschlüssel je Kunde/Artikel (zwischengespeichert)
    foreach (umsatzdaten_monatsfolge($von, $bis) as $m) {
        if (!isset($index['monate'][$m])) continue;
        $mZiel = umsatz_monat_plus($m, 12 * $verschieben);
        $grenze = $m === $bis && $bisTag !== null ? $bisTag : 31;
        $gMonat = $zeitlich && $a['nach'] !== 'kw' ? umsatz_zeitschluessel($a['nach'], $m, 1, $verschieben) : null;
        $gTag = [];
        $zr = $reihe[$mZiel] ?? umsatz_leer();
        foreach (umsatzdaten_monat($m) as $z) {
            if ($z[0] > $grenze) continue;
            $ka = $z[1] . "\0" . $z[2];
            if ($a['filter']) {
                if (!isset($ok[$ka])) {
                    $ok[$ka] = true;
                    foreach ($a['filter'] as $dim => $erlaubt) if (!isset($erlaubt[umsatz_merkmal($dim, $z[1], $z[2])])) { $ok[$ka] = false; break; }
                }
                if (!$ok[$ka]) continue;
            }
            $g = $gMonat ?? ($zeitlich ? ($gTag[$z[0]] ??= umsatz_zeitschluessel('kw', $m, $z[0], $verschieben)) : ($gk[$ka] ??= umsatz_merkmal($a['nach'], $z[1], $z[2])));
            if (!isset($ziel[$g])) $ziel[$g] = umsatz_leer() + ['kunden' => [], 'kauf' => false];
            $r = &$ziel[$g];   // Verweis: die Kundenliste der Zeile wird nicht je Zeile kopiert
            if ($z[9] === 1) {
                $r['umsatz'] += $z[5]; $r['menge'] += $z[4]; $r['kolli'] += $z[3]; $r['pos'] += $z[8]; $r['ek'] += $z[6]; $r['umsatzEk'] += $z[7];
                $zr['umsatz'] += $z[5]; $zr['menge'] += $z[4]; $zr['kolli'] += $z[3]; $zr['pos'] += $z[8]; $zr['ek'] += $z[6]; $zr['umsatzEk'] += $z[7];
                $r['kunden'][$z[1]] = true; $kunden[$z[1]] = true; $artikel[$z[2]] = true;
                if ($z[4] > 0) $r['kauf'] = true;   // Kauf (keine Gutschrift) – für „neu“ und „verloren“
            } else {
                $r['posOhne'] += $z[8]; $r['mengeOhne'] += $z[4]; $zr['posOhne'] += $z[8]; $zr['mengeOhne'] += $z[4];
            }
            unset($r);
        }
        $reihe[$mZiel] = $zr;
    }
}

/* Summe über alle Monate der Reihe */
function umsatz_summe(array $reihe): array
{
    $s = umsatz_leer();
    foreach ($reihe as $r) foreach ($s as $k => $_) $s[$k] += $r[$k];
    return $s;
}

/* Name und Zusatz einer Zeile der Gliederung */
function umsatz_bezeichnung(string $nach, string $k): array
{
    $s = umsatz_stamm();
    $ohne = ['vertreter' => 'ohne Vertreter', 'kundengruppe' => 'ohne Kundengruppe', 'vkgruppe' => 'ohne Artikelgruppe', 'fleischart' => 'ohne Fleischart (Artikel ohne Stammsatz)'];
    if ($k === UMSATZ_OHNE && isset($ohne[$nach])) return [$ohne[$nach], ''];
    switch ($nach) {
        case 'monat': return [umsatzdaten_monatsname($k), ''];
        case 'quartal': return [substr($k, 5) . ' ' . substr($k, 0, 4), ''];
        case 'jahr': return [$k, ''];
        case 'kw': return ['KW ' . (int)substr($k, 6) . '/' . substr($k, 0, 4), ''];
        case 'vertreter':
            $v = $s['vertreter'][$k] ?? null;
            return $v ? [$k . ' – ' . ((string)($v['name'] ?? '') ?: $k), (string)($v['kurz'] ?? '')] : ["Vertreter $k", 'nicht in den Stammdaten'];
        case 'kundengruppe':
        case 'vkgruppe':
            $g = $s[$nach === 'kundengruppe' ? 'kundengruppen' : 'vkgruppen'][$k] ?? null;
            return $g ? [$k . ' – ' . (string)($g['name'] ?? ''), trim(implode(' · ', array_filter([(string)($g['klasse'] ?? ''), (string)($g['kategorie'] ?? '')], 'strlen')))]
                      : [($nach === 'kundengruppe' ? 'Kundengruppe ' : 'Artikelgruppe ') . $k, 'nicht in den Stammdaten'];
        case 'fleischart': return [$k, ''];
        case 'kunde':
            $c = umsatz_kunde($k);
            if (!$c) return ["Kunde $k", 'nicht in den Kundenstammdaten'];
            $v = $c['vertreter'] !== '' ? ($s['vertreter'][$c['vertreter']]['name'] ?? $c['vertreter']) : '';
            return [($c['name'] !== '' ? $c['name'] : "Kunde $k"), trim(implode(' · ', array_filter([$k, $c['ort'], $v !== '' ? 'Vertreter ' . $v : ''], 'strlen')))];
        case 'artikel':
            $x = umsatz_artikel($k);
            if (!$x) return ["Artikel $k", 'nicht in den Artikelstammdaten'];
            $vk = $x['vk'] !== '' ? ($s['vkgruppen'][$x['vk']]['name'] ?? $x['vk']) : '';
            return [$x['name'] !== '' ? $x['name'] : "Artikel $k", trim(implode(' · ', array_filter([$k, $vk, $x['fa']], 'strlen')))];
    }
    return [$k, ''];
}

/* Einkaufswerte und Deckungsbeitrag: eigenes Recht des Controllings UND das EK-Recht (GR-008) */
function umsatz_darf_ek(array $me): bool { return may($me, 'controlling.umsatz_ek') && may($me, 'bestand.einkaufspreise'); }

/* Kennzahlen für die Antwort: ohne EK-Recht ohne EK-Wert und Umsatz mit EK */
function umsatz_werte(array $r, bool $ek): array
{
    $o = ['umsatz' => $r['umsatz'], 'menge' => $r['menge'], 'kolli' => $r['kolli'], 'pos' => $r['pos'], 'posOhne' => $r['posOhne'], 'mengeOhne' => $r['mengeOhne']];
    if (isset($r['kunden'])) $o['kunden'] = is_array($r['kunden']) ? count($r['kunden']) : (int)$r['kunden'];
    if ($ek) { $o['ek'] = $r['ek']; $o['umsatzEk'] = $r['umsatzEk']; }
    return $o;
}

/* Wert einer Zeile für die Rangliste (null: keine Spanne, weil kein Umsatz mit EK) */
function umsatz_rang_wert(array $w, string $rang): int|float|null
{
    switch ($rang) {
        case 'menge': return $w['menge'];
        case 'db': return $w['umsatzEk'] - $w['ek'];
        case 'spanne': return $w['umsatzEk'] > 0 ? ($w['umsatzEk'] - $w['ek']) / $w['umsatzEk'] : null;
    }
    return $w['umsatz'];
}
/* Zeilen nach der Kennzahl ordnen (höchste zuerst, $auf: niedrigste zuerst); Spanne: Zeilen unter der Schwelle (Umsatz mit EK)
   und ohne Umsatz mit EK am Ende (Merkmal „klein“). Gleichstand: Umsatz, dann Name. $basis = 'vj': nach den Vorjahreswerten
   (verlorene Zeilen haben jetzt keine). */
function umsatz_rang_sortieren(array &$zeilen, string $rang, bool $auf, ?int $schwelle, string $basis = 'werte'): void
{
    foreach ($zeilen as &$z) {
        $w = $z[$basis] ?? $z['werte'];
        $z['rangWert'] = umsatz_rang_wert($w, $rang); $z['rangUmsatz'] = $w['umsatz'];
        if ($rang === 'spanne') $z['klein'] = $z['rangWert'] === null || $w['umsatzEk'] < $schwelle;
    }
    unset($z);
    usort($zeilen, function ($x, $y) use ($auf) {
        $k = (int)($x['klein'] ?? false) <=> (int)($y['klein'] ?? false);
        if ($k) return $k;
        $a = $x['rangWert'] ?? PHP_INT_MIN; $b = $y['rangWert'] ?? PHP_INT_MIN;
        $c = $auf ? $a <=> $b : $b <=> $a;
        return $c ?: $y['rangUmsatz'] <=> $x['rangUmsatz'] ?: strnatcasecmp($x['name'], $y['name']);
    });
    foreach ($zeilen as &$z) unset($z['rangWert'], $z['rangUmsatz']);
    unset($z);
}

/* ABC-Klasse je Zeile (Feld „abc“) und Zusammenfassung [A|B|C => [anzahl, anteil]]; null, wenn die Kennzahl keine Summe ist */
function umsatz_abc(array &$zeilen, string $rang): ?array
{
    if (!in_array($rang, UMSATZ_ABC_RANG, true) || !$zeilen) return null;
    $reihe = $zeilen;
    umsatz_rang_sortieren($reihe, $rang, false, null);
    $gesamt = 0;
    foreach ($reihe as $z) $gesamt += max(0, umsatz_rang_wert($z['werte'], $rang));
    $o = ['A' => ['anzahl' => 0, 'wert' => 0], 'B' => ['anzahl' => 0, 'wert' => 0], 'C' => ['anzahl' => 0, 'wert' => 0]];
    $klasse = []; $kum = 0;
    foreach ($reihe as $z) {
        $v = umsatz_rang_wert($z['werte'], $rang);
        $vorher = $gesamt > 0 ? $kum / $gesamt : 1.0;
        $k = $v <= 0 ? 'C' : ($vorher < UMSATZ_ABC['A'] ? 'A' : ($vorher < UMSATZ_ABC['B'] ? 'B' : 'C'));
        $kum += max(0, $v);
        $klasse[$z['schluessel']] = $k; $o[$k]['anzahl']++; $o[$k]['wert'] += max(0, $v);
    }
    foreach ($zeilen as &$z) $z['abc'] = $klasse[$z['schluessel']];
    unset($z);
    foreach ($o as &$x) { $x['anteil'] = $gesamt > 0 ? $x['wert'] / $gesamt : 0.0; unset($x['wert']); }
    unset($x);
    return $o;
}

/* Auswertung: Gliederung mit Vorjahr, Monatsreihe, Summen */
function umsatz_auswertung(array $q, array $me): array
{
    $index = umsatzdaten_index();
    $stand = umsatzdaten_stand($index);
    $a = umsatz_anfrage($q, $stand);
    $ek = umsatz_darf_ek($me);
    if (in_array($a['rang'], ['db', 'spanne'], true) && !$ek) fail('Die Rangliste nach DB oder Spanne sehen nur Mitarbeiter, die auch die Einkaufswerte sehen dürfen.', 403);
    // Endet der Zeitraum im Monat des letzten Datentags, endet das Vorjahr am gleichen Tag (gleicher Stand)
    $letzter = $stand['bis'];
    $bisTag = $letzter && substr($letzter, 0, 7) === $a['bis'] && (int)substr($letzter, 8, 2) < umsatzdaten_tage($a['bis']) ? (int)substr($letzter, 8, 2) : null;
    $zeilen = []; $reihe = []; $kunden = []; $artikel = [];
    umsatz_zaehlen($a, $index, $a['von'], $a['bis'], 0, null, $zeilen, $reihe, $kunden, $artikel);
    $zeilenVj = []; $reiheVj = []; $kundenVj = []; $artikelVj = [];
    $vjVon = umsatz_monat_plus($a['von'], -12); $vjBis = umsatz_monat_plus($a['bis'], -12);
    if ($a['vj']) umsatz_zaehlen($a, $index, $vjVon, $vjBis, 1, $bisTag, $zeilenVj, $reiheVj, $kundenVj, $artikelVj);
    $summe = umsatz_summe($reihe); $summeVj = umsatz_summe($reiheVj);

    $zeitlich = in_array($a['nach'], UMSATZ_ZEITLICH, true);
    $schluessel = array_keys($zeilen + ($zeitlich ? [] : $zeilenVj));   // Zeitliche Gliederung: nur Zeitabschnitte des laufenden Zeitraums
    // Merkmale nur mit Positionen ohne Berechnung (z. B. Leergut) erscheinen nicht als eigene Zeile – sie stehen in der Summe
    if (!$zeitlich) $schluessel = array_values(array_filter($schluessel, fn($k) => ($zeilen[$k]['pos'] ?? 0) > 0 || ($zeilenVj[$k]['pos'] ?? 0) > 0));
    $out = [];
    $vergleich = $a['vj'] && !$zeitlich;   // „neu“ und „verloren“ nur mit Vorjahr und nicht bei Zeit
    $wechsel = $vergleich ? ['neu' => ['anzahl' => 0, 'umsatz' => 0], 'verloren' => ['anzahl' => 0, 'umsatzVj' => 0]] : null;
    foreach ($schluessel as $k) {
        $k = (string)$k;
        [$name, $sub] = umsatz_bezeichnung($a['nach'], $k);
        $z = ['schluessel' => $k, 'name' => $name, 'sub' => $sub, 'werte' => umsatz_werte($zeilen[$k] ?? umsatz_leer() + ['kunden' => []], $ek),
              'vj' => $a['vj'] && isset($zeilenVj[$k]) ? umsatz_werte($zeilenVj[$k], $ek) : null];
        if ($vergleich) {
            $kauf = !empty($zeilen[$k]['kauf']); $kaufVj = !empty($zeilenVj[$k]['kauf']);
            if ($kauf && !$kaufVj) { $z['wechsel'] = 'neu'; $wechsel['neu']['anzahl']++; $wechsel['neu']['umsatz'] += $z['werte']['umsatz']; }
            elseif ($kaufVj && !$kauf) { $z['wechsel'] = 'verloren'; $wechsel['verloren']['anzahl']++; $wechsel['verloren']['umsatzVj'] += $z['vj']['umsatz']; }
        }
        $out[] = $z;
    }
    $schwelle = null; $abc = null;
    if ($zeitlich) usort($out, fn($x, $y) => strcmp($x['schluessel'], $y['schluessel']));
    else {
        $abc = umsatz_abc($out, $a['rang']);   // über alle Zeilen der Auswahl, vor „nur neu/verloren“ und vor dem Kürzen
        if ($a['nur'] !== '') $out = array_values(array_filter($out, fn($z) => ($z['wechsel'] ?? '') === $a['nur']));
        $basis = $a['nur'] === 'verloren' ? 'vj' : 'werte';
        if ($a['rang'] === 'spanne') $schwelle = max(UMSATZ_RANG_CENT_MIN, (int)round(($basis === 'vj' ? $summeVj : $summe)['umsatzEk'] * UMSATZ_RANG_ANTEIL_MIN));
        umsatz_rang_sortieren($out, $a['rang'], $a['auf'], $schwelle, $basis);
    }
    $monate = [];
    foreach (umsatzdaten_monatsfolge($a['von'], $a['bis']) as $m)
        $monate[] = ['monat' => $m, 'werte' => umsatz_werte($reihe[$m] ?? umsatz_leer(), $ek), 'vj' => $a['vj'] && isset($reiheVj[$m]) ? umsatz_werte($reiheVj[$m], $ek) : null];
    return ['ok' => true, 'anfrage' => ['von' => $a['von'], 'bis' => $a['bis'], 'nach' => $a['nach'], 'vj' => $a['vj'], 'rang' => $a['rang'], 'auf' => $a['auf'], 'nur' => $a['nur']],
            'rangSchwelle' => $schwelle, 'abc' => $abc, 'wechsel' => $wechsel,
            'vorjahr' => $a['vj'] ? ['von' => $vjVon, 'bis' => $vjBis, 'bisTag' => $bisTag] : null, 'ek' => $ek,
            'summe' => umsatz_werte($summe + ['kunden' => count($kunden)], $ek) + ['artikel' => count($artikel)],
            'summeVj' => $a['vj'] ? umsatz_werte($summeVj + ['kunden' => count($kundenVj)], $ek) + ['artikel' => count($artikelVj)] : null,
            'monate' => $monate, 'zeilen' => array_slice($out, 0, UMSATZ_ZEILEN_MAX), 'zeilenGesamt' => count($out), 'rev' => $index['rev']];
}

/* ---------- Detail für die Pop-ups der Umsatzstatistik ----------
   Ein Vertreter, eine Kundengruppe, ein Kunde, eine Artikelgruppe, eine Fleischart oder ein Artikel: Kennzahlen mit Vorjahr,
   Monatsreihe, Kunden und Artikel (je mit letztem Kauf im Zeitraum oder Vorjahr), beim Kunden auch seine Liefertage.
   Kauf = berechnete Position mit Menge > 0: Gutschriften zählen in Umsatz und Menge, aber nicht als Kauf oder Liefertag.
   Die Filter der Seite gelten weiter; das gewählte Merkmal ersetzt einen Filter desselben Merkmals. Je Zeitraum eine Lesung
   je Monat (Summen für Kunden, Artikel und Tage in einem Durchgang). */
const UMSATZ_DETAIL = ['vertreter', 'kundengruppe', 'kunde', 'vkgruppe', 'fleischart', 'artikel'];

function umsatz_detail_addieren(array &$r, array $z, ?string $datum): void
{
    if ($z[9] === 1) {
        $r['umsatz'] += $z[5]; $r['menge'] += $z[4]; $r['kolli'] += $z[3]; $r['pos'] += $z[8]; $r['ek'] += $z[6]; $r['umsatzEk'] += $z[7];
        if ($datum !== null && $z[4] > 0) {   // Kauf (keine Gutschrift): Tage mit Kauf und letzter Kauf
            if ($r['zuletzt'] === null || $datum > $r['zuletzt']) $r['zuletzt'] = $datum;
            if (($r['_tag'] ?? null) !== $datum) { $r['kaeufe']++; $r['_tag'] = $datum; }
        }
    } else {
        $r['posOhne'] += $z[8]; $r['mengeOhne'] += $z[4];
    }
}

/* Summen eines Zeitraums je Monat, Kunde, Artikel und (auf Wunsch) Liefertag; $verschieben/$bisTag wie umsatz_zaehlen() */
function umsatz_detail_zaehlen(array $a, array $index, string $von, string $bis, int $verschieben, ?int $bisTag, bool $mitTagen): array
{
    $o = ['reihe' => [], 'kunden' => [], 'artikel' => [], 'tage' => []];
    $ok = [];
    foreach (umsatzdaten_monatsfolge($von, $bis) as $m) {
        if (!isset($index['monate'][$m])) continue;
        $mZiel = umsatz_monat_plus($m, 12 * $verschieben);
        $grenze = $m === $bis && $bisTag !== null ? $bisTag : 31;
        $zr = $o['reihe'][$mZiel] ?? umsatz_leer();
        foreach (umsatzdaten_monat($m) as $z) {
            if ($z[0] > $grenze) continue;
            $ka = $z[1] . "\0" . $z[2];
            if (!isset($ok[$ka])) {
                $ok[$ka] = true;
                foreach ($a['filter'] as $dim => $erlaubt) if (!isset($erlaubt[umsatz_merkmal($dim, $z[1], $z[2])])) { $ok[$ka] = false; break; }
            }
            if (!$ok[$ka]) continue;
            $datum = $m . '-' . str_pad((string)$z[0], 2, '0', STR_PAD_LEFT);
            umsatz_detail_addieren($zr, $z, null);
            $o['kunden'][$z[1]] ??= umsatz_leer() + ['zuletzt' => null, 'kaeufe' => 0];
            umsatz_detail_addieren($o['kunden'][$z[1]], $z, $datum);
            $o['artikel'][$z[2]] ??= umsatz_leer() + ['zuletzt' => null, 'kaeufe' => 0];
            umsatz_detail_addieren($o['artikel'][$z[2]], $z, $datum);
            if ($mitTagen && $z[9] === 1) {
                $o['tage'][$datum] ??= umsatz_leer() + ['zuletzt' => null, 'kaeufe' => 0];
                umsatz_detail_addieren($o['tage'][$datum], $z, $datum);
            }
        }
        $o['reihe'][$mZiel] = $zr;
    }
    return $o;
}

/* Liste der Kunden bzw. Artikel des Details: umsatzstärkste zuerst, nur mit berechneten Positionen (sonst nur Leergut) */
function umsatz_detail_liste(string $nach, array $jetzt, ?array $vj, bool $ek): array
{
    $out = [];
    foreach (array_keys($jetzt + ($vj ?? [])) as $nr) {
        $nr = (string)$nr;
        $w = $jetzt[$nr] ?? null; $wv = $vj[$nr] ?? null;
        if (($w['pos'] ?? 0) === 0 && ($wv['pos'] ?? 0) === 0) continue;
        [$name, $sub] = umsatz_bezeichnung($nach, $nr);
        $zuletzt = max((string)($w['zuletzt'] ?? ''), (string)($wv['zuletzt'] ?? ''));
        $out[] = ['nr' => $nr, 'name' => $name, 'sub' => $sub, 'werte' => umsatz_werte($w ?? umsatz_leer(), $ek),
                  'vj' => $vj !== null && $wv ? umsatz_werte($wv, $ek) : null, 'zuletzt' => $zuletzt !== '' ? $zuletzt : null, 'kaeufe' => (int)($w['kaeufe'] ?? 0)];
    }
    usort($out, fn($x, $y) => $y['werte']['umsatz'] <=> $x['werte']['umsatz'] ?: ($y['vj']['umsatz'] ?? 0) <=> ($x['vj']['umsatz'] ?? 0) ?: strnatcasecmp($x['name'], $y['name']));
    return $out;
}

function umsatz_detail(array $q, array $me): array
{
    $index = umsatzdaten_index();
    $stand = umsatzdaten_stand($index);
    $a = umsatz_anfrage(['nach' => 'monat'] + array_diff_key($q, ['nur' => true]), $stand);   // „nur neu/verloren“ gilt nur für die Rangliste
    $dim = (string)($q['dim'] ?? '');
    if (!in_array($dim, UMSATZ_DETAIL, true)) throw new InvalidArgumentException('Unbekanntes Merkmal.');
    $wert = (string)($q['wert'] ?? '');
    if ($wert !== UMSATZ_OHNE && !preg_match('#^[0-9A-Za-z._/-]{1,20}$#u', $wert) && !($dim === 'fleischart' && in_array($wert, CATEGORIES, true)))
        throw new InvalidArgumentException('Ungültiger Wert.');
    $a['filter'][$dim] = [$wert => true];
    $ek = umsatz_darf_ek($me);
    $letzter = $stand['bis'];
    $bisTag = $letzter && substr($letzter, 0, 7) === $a['bis'] && (int)substr($letzter, 8, 2) < umsatzdaten_tage($a['bis']) ? (int)substr($letzter, 8, 2) : null;
    $vjVon = umsatz_monat_plus($a['von'], -12); $vjBis = umsatz_monat_plus($a['bis'], -12);
    $jetzt = umsatz_detail_zaehlen($a, $index, $a['von'], $a['bis'], 0, null, $dim === 'kunde');
    $vj = $a['vj'] ? umsatz_detail_zaehlen($a, $index, $vjVon, $vjBis, 1, $bisTag, false) : null;

    $zaehle = fn(array $l) => count(array_filter($l, fn($r) => $r['pos'] > 0));
    $zuletzt = null;
    foreach ([$jetzt['kunden'], $vj['kunden'] ?? []] as $l) foreach ($l as $r) if ($r['zuletzt'] !== null && ($zuletzt === null || $r['zuletzt'] > $zuletzt)) $zuletzt = $r['zuletzt'];
    $summe = umsatz_summe($jetzt['reihe']);
    $monate = [];
    foreach (umsatzdaten_monatsfolge($a['von'], $a['bis']) as $m)
        $monate[] = ['monat' => $m, 'werte' => umsatz_werte($jetzt['reihe'][$m] ?? umsatz_leer(), $ek), 'vj' => $vj !== null && isset($vj['reihe'][$m]) ? umsatz_werte($vj['reihe'][$m], $ek) : null];
    [$name, $sub] = umsatz_bezeichnung($dim, $wert);
    $o = ['ok' => true, 'dim' => $dim, 'wert' => $wert, 'name' => $name, 'sub' => $sub,
          'anfrage' => ['von' => $a['von'], 'bis' => $a['bis'], 'vj' => $a['vj']],
          'vorjahr' => $a['vj'] ? ['von' => $vjVon, 'bis' => $vjBis, 'bisTag' => $bisTag] : null, 'ek' => $ek,
          'summe' => umsatz_werte($summe, $ek) + ['kunden' => $zaehle($jetzt['kunden']), 'artikel' => $zaehle($jetzt['artikel']), 'zuletzt' => $zuletzt],
          'summeVj' => $vj !== null ? umsatz_werte(umsatz_summe($vj['reihe']), $ek) + ['kunden' => $zaehle($vj['kunden']), 'artikel' => $zaehle($vj['artikel'])] : null,
          'monate' => $monate, 'rev' => $index['rev']];
    if ($dim === 'kunde') {
        $c = umsatz_kunde($wert);
        $s = umsatz_stamm();
        $o['kunde'] = $c ? ['vertreter' => $c['vertreter'] !== '' ? (string)($s['vertreter'][$c['vertreter']]['name'] ?? $c['vertreter']) : '',
                            'gruppe' => $c['gruppe'] !== '' ? (string)($s['kundengruppen'][$c['gruppe']]['name'] ?? $c['gruppe']) : '', 'ort' => $c['ort']] : null;
        $tage = [];
        foreach ($jetzt['tage'] as $t => $r) if ($r['kaeufe'] > 0) $tage[] = ['tag' => (string)$t, 'werte' => umsatz_werte($r, $ek)];   // nur Tage mit Kauf
        usort($tage, fn($x, $y) => strcmp($y['tag'], $x['tag']));
        $o['tage'] = $tage;
    } else {
        $l = umsatz_detail_liste('kunde', $jetzt['kunden'], $vj['kunden'] ?? null, $ek);
        $o['kunden'] = array_slice($l, 0, UMSATZ_ZEILEN_MAX); $o['kundenGesamt'] = count($l);
    }
    if ($dim !== 'artikel') {
        $l = umsatz_detail_liste('artikel', $jetzt['artikel'], $vj['artikel'] ?? null, $ek);
        $o['artikel'] = array_slice($l, 0, UMSATZ_ZEILEN_MAX); $o['artikelGesamt'] = count($l);
    }
    return $o;
}

/* ---------- Bestellpausen (Frühwarnung) ----------
   Stammkunden = mindestens UMSATZ_PAUSE_KAUFTAGE Tage mit Kauf in den UMSATZ_PAUSE_TAGE Tagen bis zum Stichtag (Ende des gewählten
   Zeitraums, höchstens der letzte Tag mit Daten). Auffällig, wenn die Pause seit dem letzten Kauf mindestens UMSATZ_PAUSE_FAKTOR-mal
   so lang ist wie der übliche Abstand (Ø zwischen erstem und letztem Kauftag), länger als jede frühere Pause im Fenster (sonst
   wären Kunden, die in Schüben kaufen, ständig auffällig) und mindestens UMSATZ_PAUSE_MIN_TAGE Tage. Kauf = berechnete Position mit
   Menge > 0. Die Filter der Seite gelten (z. B. nur Rind: „kauft sonst alle 7 Tage Rind“). Reihenfolge nach dem üblichen
   Monatsumsatz (Umsatz je Kauftag × Kauftage im Monat), höchster zuerst. Keine Einkaufswerte (GR-008). */
const UMSATZ_PAUSE_TAGE = 182;
const UMSATZ_PAUSE_KAUFTAGE = 4;
const UMSATZ_PAUSE_FAKTOR = 2;
const UMSATZ_PAUSE_MIN_TAGE = 7;
const UMSATZ_PAUSE_MAX = 200;

/* Tageszahl eines Datums (für Abstände in Tagen) */
function umsatz_tagnummer(string $datum): int { return intdiv((int)gmmktime(12, 0, 0, (int)substr($datum, 5, 2), (int)substr($datum, 8, 2), (int)substr($datum, 0, 4)), 86400); }

/* Stammkunden mit auffälliger Bestellpause zum Stichtag; Anfrage wie die Auswertung (von, bis, Filter) */
function umsatz_pausen(array $q): array
{
    $index = umsatzdaten_index();
    $stand = umsatzdaten_stand($index);
    $a = umsatz_anfrage(['nach' => 'kunde'] + array_diff_key($q, ['nur' => true]), $stand);
    $regel = ['tage' => UMSATZ_PAUSE_TAGE, 'kauftage' => UMSATZ_PAUSE_KAUFTAGE, 'faktor' => UMSATZ_PAUSE_FAKTOR, 'minTage' => UMSATZ_PAUSE_MIN_TAGE];
    if (!$stand['bis']) return ['ok' => true, 'stichtag' => null, 'von' => null, 'stammkunden' => 0, 'zeilen' => [], 'gesamt' => 0, 'regel' => $regel, 'rev' => $index['rev']];
    $stichtag = min($a['bis'] . '-' . sprintf('%02d', umsatzdaten_tage($a['bis'])), (string)$stand['bis']);
    $ende = umsatz_tagnummer($stichtag);
    $beginn = $ende - UMSATZ_PAUSE_TAGE + 1;
    $vonDatum = gmdate('Y-m-d', $beginn * 86400);
    $tage = []; $umsatz = []; $ok = [];
    foreach (umsatzdaten_monatsfolge(substr($vonDatum, 0, 7), substr($stichtag, 0, 7)) as $m) {
        if (!isset($index['monate'][$m])) continue;
        $basis = umsatz_tagnummer($m . '-01') - 1;
        foreach (umsatzdaten_monat($m) as $z) {
            if ($z[9] !== 1) continue;
            $t = $basis + $z[0];
            if ($t < $beginn || $t > $ende) continue;
            $ka = $z[1] . "\0" . $z[2];
            if ($a['filter']) {
                if (!isset($ok[$ka])) {
                    $ok[$ka] = true;
                    foreach ($a['filter'] as $dim => $erlaubt) if (!isset($erlaubt[umsatz_merkmal($dim, $z[1], $z[2])])) { $ok[$ka] = false; break; }
                }
                if (!$ok[$ka]) continue;
            }
            $umsatz[$z[1]] = ($umsatz[$z[1]] ?? 0) + $z[5];
            if ($z[4] > 0) $tage[$z[1]][$t] = true;
        }
    }
    $stamm = 0; $out = [];
    foreach ($tage as $nr => $set) {
        $nr = (string)$nr;
        $n = count($set);
        if ($n < UMSATZ_PAUSE_KAUFTAGE) continue;
        $stamm++;
        $liste = array_keys($set);
        sort($liste);
        $laengste = 0;
        for ($i = 1; $i < $n; $i++) $laengste = max($laengste, $liste[$i] - $liste[$i - 1]);
        $mittel = ($liste[$n - 1] - $liste[0]) / ($n - 1);
        $pause = $ende - $liste[$n - 1];
        if ($pause < UMSATZ_PAUSE_MIN_TAGE || $pause < UMSATZ_PAUSE_FAKTOR * $mittel || $pause <= $laengste) continue;
        [$name, $sub] = umsatz_bezeichnung('kunde', $nr);
        $out[] = ['nr' => $nr, 'name' => $name, 'sub' => $sub, 'letzter' => gmdate('Y-m-d', $liste[$n - 1] * 86400), 'pause' => $pause,
                  'abstand' => round($mittel, 1), 'laengste' => $laengste, 'kauftage' => $n, 'umsatzMonat' => (int)round(($umsatz[$nr] ?? 0) / $n * 30.4375 / $mittel)];
    }
    usort($out, fn($x, $y) => $y['umsatzMonat'] <=> $x['umsatzMonat'] ?: $y['pause'] <=> $x['pause'] ?: strcmp($x['nr'], $y['nr']));
    return ['ok' => true, 'stichtag' => $stichtag, 'von' => $vonDatum, 'stammkunden' => $stamm, 'zeilen' => array_slice($out, 0, UMSATZ_PAUSE_MAX),
            'gesamt' => count($out), 'regel' => $regel, 'rev' => $index['rev']];
}

/* Grunddaten der Auswertung: Stand der Daten, Rechte, Auswahllisten (nur Nummern und Namen) */
function umsatz_grunddaten(array $me): array
{
    $index = umsatzdaten_index();
    $s = umsatz_stamm();
    $gruppe = fn(array $l) => array_values(array_map(fn($g) => ['nr' => (string)$g['nr'], 'name' => (string)($g['name'] ?? '')], $l));
    $kunden = array_map(function ($nr) { $c = umsatz_kunde($nr); return ['nr' => $nr, 'name' => $c && $c['name'] !== '' ? $c['name'] : "Kunde $nr", 'bekannt' => $c !== null]; }, $index['kunden']);
    $artikel = array_map(function ($nr) { $x = umsatz_artikel($nr); return ['nr' => $nr, 'name' => $x && $x['name'] !== '' ? $x['name'] : "Artikel $nr", 'bekannt' => $x !== null]; }, $index['artikel']);
    return ['ok' => true, 'stand' => umsatzdaten_stand($index),
            'rechte' => ['ek' => umsatz_darf_ek($me), 'importieren' => may($me, 'controlling.umsatz_importieren')],
            'gliederungen' => array_map(fn($id, $name) => ['id' => $id, 'name' => $name], array_keys(UMSATZ_GLIEDERUNG), UMSATZ_GLIEDERUNG),
            'optionen' => ['vertreter' => $gruppe($s['vertreter']), 'kundengruppen' => $gruppe($s['kundengruppen']), 'vkgruppen' => $gruppe($s['vkgruppen']),
                           'fleischarten' => CATEGORIES, 'kunden' => $kunden, 'artikel' => $artikel]];
}
