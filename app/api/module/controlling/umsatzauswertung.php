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
   so, wie sie importiert wurden. Nummern ohne Stammsatz erscheinen mit ihrer Nummer, „ohne …“ steht als Wert „_“. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const UMSATZ_GLIEDERUNG = ['monat' => 'Monat', 'quartal' => 'Quartal', 'jahr' => 'Jahr', 'kw' => 'Kalenderwoche', 'vertreter' => 'Vertreter',
                           'kundengruppe' => 'Kundengruppe', 'kunde' => 'Kunde', 'vkgruppe' => 'Artikelgruppe', 'fleischart' => 'Fleischart', 'artikel' => 'Artikel'];
const UMSATZ_ZEITLICH = ['monat', 'quartal', 'jahr', 'kw'];
const UMSATZ_FILTER = ['v' => 'vertreter', 'kg' => 'kundengruppe', 'k' => 'kunde', 'ag' => 'vkgruppe', 'fa' => 'fleischart', 'a' => 'artikel'];
const UMSATZ_ZEILEN_MAX = 2000;
const UMSATZ_MONATE_MAX = 120;
const UMSATZ_OHNE = '_';   // Filter- und Gliederungswert für „ohne Vertreter“, „ohne Kundengruppe“ …

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
    return ['von' => $von, 'bis' => $bis, 'nach' => $nach, 'vj' => ($q['vj'] ?? '1') !== '0', 'filter' => $filter];
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
            if (!isset($ziel[$g])) $ziel[$g] = umsatz_leer() + ['kunden' => []];
            $r = &$ziel[$g];   // Verweis: die Kundenliste der Zeile wird nicht je Zeile kopiert
            if ($z[9] === 1) {
                $r['umsatz'] += $z[5]; $r['menge'] += $z[4]; $r['kolli'] += $z[3]; $r['pos'] += $z[8]; $r['ek'] += $z[6]; $r['umsatzEk'] += $z[7];
                $zr['umsatz'] += $z[5]; $zr['menge'] += $z[4]; $zr['kolli'] += $z[3]; $zr['pos'] += $z[8]; $zr['ek'] += $z[6]; $zr['umsatzEk'] += $z[7];
                $r['kunden'][$z[1]] = true; $kunden[$z[1]] = true; $artikel[$z[2]] = true;
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

/* Auswertung: Gliederung mit Vorjahr, Monatsreihe, Summen */
function umsatz_auswertung(array $q, array $me): array
{
    $index = umsatzdaten_index();
    $stand = umsatzdaten_stand($index);
    $a = umsatz_anfrage($q, $stand);
    $ek = umsatz_darf_ek($me);
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
    foreach ($schluessel as $k) {
        $k = (string)$k;
        [$name, $sub] = umsatz_bezeichnung($a['nach'], $k);
        $out[] = ['schluessel' => $k, 'name' => $name, 'sub' => $sub, 'werte' => umsatz_werte($zeilen[$k] ?? umsatz_leer() + ['kunden' => []], $ek),
                  'vj' => $a['vj'] && isset($zeilenVj[$k]) ? umsatz_werte($zeilenVj[$k], $ek) : null];
    }
    if ($zeitlich) usort($out, fn($x, $y) => strcmp($x['schluessel'], $y['schluessel']));
    else usort($out, fn($x, $y) => $y['werte']['umsatz'] <=> $x['werte']['umsatz'] ?: ($y['vj']['umsatz'] ?? 0) <=> ($x['vj']['umsatz'] ?? 0) ?: strnatcasecmp($x['name'], $y['name']));
    $monate = [];
    foreach (umsatzdaten_monatsfolge($a['von'], $a['bis']) as $m)
        $monate[] = ['monat' => $m, 'werte' => umsatz_werte($reihe[$m] ?? umsatz_leer(), $ek), 'vj' => $a['vj'] && isset($reiheVj[$m]) ? umsatz_werte($reiheVj[$m], $ek) : null];
    return ['ok' => true, 'anfrage' => ['von' => $a['von'], 'bis' => $a['bis'], 'nach' => $a['nach'], 'vj' => $a['vj']],
            'vorjahr' => $a['vj'] ? ['von' => $vjVon, 'bis' => $vjBis, 'bisTag' => $bisTag] : null, 'ek' => $ek,
            'summe' => umsatz_werte($summe + ['kunden' => count($kunden)], $ek) + ['artikel' => count($artikel)],
            'summeVj' => $a['vj'] ? umsatz_werte($summeVj + ['kunden' => count($kundenVj)], $ek) + ['artikel' => count($artikelVj)] : null,
            'monate' => $monate, 'zeilen' => array_slice($out, 0, UMSATZ_ZEILEN_MAX), 'zeilenGesamt' => count($out), 'rev' => $index['rev']];
}

/* ---------- Detail für die Pop-ups der Umsatzstatistik ----------
   Ein Vertreter, eine Kundengruppe, ein Kunde, eine Artikelgruppe, eine Fleischart oder ein Artikel: Kennzahlen mit Vorjahr,
   Monatsreihe, Kunden und Artikel (je mit letztem Kauf im Zeitraum oder Vorjahr), beim Kunden auch seine Liefertage.
   Die Filter der Seite gelten weiter; das gewählte Merkmal ersetzt einen Filter desselben Merkmals. Je Zeitraum eine Lesung
   je Monat (Summen für Kunden, Artikel und Tage in einem Durchgang). */
const UMSATZ_DETAIL = ['vertreter', 'kundengruppe', 'kunde', 'vkgruppe', 'fleischart', 'artikel'];

function umsatz_detail_addieren(array &$r, array $z, ?string $datum): void
{
    if ($z[9] === 1) {
        $r['umsatz'] += $z[5]; $r['menge'] += $z[4]; $r['kolli'] += $z[3]; $r['pos'] += $z[8]; $r['ek'] += $z[6]; $r['umsatzEk'] += $z[7];
        if ($datum !== null && ($r['zuletzt'] === null || $datum > $r['zuletzt'])) $r['zuletzt'] = $datum;
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
            $o['kunden'][$z[1]] ??= umsatz_leer() + ['zuletzt' => null];
            umsatz_detail_addieren($o['kunden'][$z[1]], $z, $datum);
            $o['artikel'][$z[2]] ??= umsatz_leer() + ['zuletzt' => null];
            umsatz_detail_addieren($o['artikel'][$z[2]], $z, $datum);
            if ($mitTagen && $z[9] === 1) {
                $o['tage'][$datum] ??= umsatz_leer() + ['zuletzt' => null];
                umsatz_detail_addieren($o['tage'][$datum], $z, null);
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
                  'vj' => $vj !== null && $wv ? umsatz_werte($wv, $ek) : null, 'zuletzt' => $zuletzt !== '' ? $zuletzt : null];
    }
    usort($out, fn($x, $y) => $y['werte']['umsatz'] <=> $x['werte']['umsatz'] ?: ($y['vj']['umsatz'] ?? 0) <=> ($x['vj']['umsatz'] ?? 0) ?: strnatcasecmp($x['name'], $y['name']));
    return $out;
}

function umsatz_detail(array $q, array $me): array
{
    $index = umsatzdaten_index();
    $stand = umsatzdaten_stand($index);
    $a = umsatz_anfrage(['nach' => 'monat'] + $q, $stand);
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
        foreach ($jetzt['tage'] as $t => $r) $tage[] = ['tag' => (string)$t, 'werte' => umsatz_werte($r, $ek)];
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
