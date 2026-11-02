<?php
declare(strict_types=1);
/* Controlling · Bereich Bestandsverlauf (Auftrag des Inhabers 02.11.2026): Auswertung der Tagesstände, die der Bestand bei
   jeder Übernahme der Bestandsliste speichert (module/bestand/verlauf.php, nur über bestand_verlauf_index()/_tag() gelesen,
   GR-101), zusammen mit dem Absatz aus den eigenen Umsatzdaten (module/controlling/umsatzdaten.php).

   Zeitraum: die letzten 30, 90 oder 365 Tage bis zur jüngsten Liste oder eigener Zeitraum (höchstens CTL_BESTAND_TAGE_MAX).
   Gliederung nach Artikel, Artikelgruppe (VK-Gruppe) oder Fleischart; Filter ag, fa, a (kommagetrennt, „_“ = ohne).
   Zuordnung zu Gruppe und Fleischart nach den heutigen Stammdaten der Verwaltung (wie die Umsatzauswertung).
   Kennzahlen je Zeile und gesamt:
   - Bestand heute = kg der jüngsten Liste im Zeitraum, Veränderung gegenüber der ersten Liste im Zeitraum.
   - Ø Bestand = Mittel der Tagesstände (Artikel, die an einem Tag fehlen, zählen dort mit 0 kg).
   - Absatz = berechnete Menge der Umsatzdaten (einschließlich Gutschriften) vom ersten Tag des Zeitraums bis zum letzten
     Tag mit Umsatzdaten – nur Artikel, die im Zeitraum in mindestens einer Liste stehen (Lagerartikel).
   - Reichweite (Tage) = Bestand heute ÷ (Absatz ÷ Kalendertage mit Umsatzdaten); ohne Absatz keine Reichweite.
   - Umschlag = Absatz ÷ Ø Bestand, hochgerechnet aufs Jahr × 365 ÷ Kalendertage.
   - Hinweis „lange am Lager“ ab CTL_BESTAND_LANGE Tagen Reichweite, „knapp“ unter CTL_BESTAND_KNAPP, „kein Absatz“ bei
     Bestand ohne Absatz.
   Lagerwert zum Einkaufspreis nur mit controlling.bestand_ek und bestand.einkaufspreise (GR-008) – ohne beide Rechte
   verlässt er den Server nicht (GR-103). Geladen von module/controlling/controlling.php. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const CTL_BESTAND_ZEITRAEUME = [30, 90, 365];   // Tage bis zur jüngsten Liste
const CTL_BESTAND_TAGE_MAX = 400;                // eigener Zeitraum höchstens
const CTL_BESTAND_LANGE = 45;                    // Reichweite ab … Tagen: „lange am Lager“
const CTL_BESTAND_KNAPP = 3;                     // Reichweite unter … Tagen: „knapp“
const CTL_BESTAND_SPARK = 40;                    // Punkte des Mini-Verlaufs je Zeile
const CTL_BESTAND_ZEILEN_MAX = 3000;
const CTL_BESTAND_NACH = ['artikel' => 'Artikel', 'vkgruppe' => 'Artikelgruppe', 'fleischart' => 'Fleischart'];
const CTL_BESTAND_FILTER = ['ag' => 'vkgruppe', 'fa' => 'fleischart', 'a' => 'artikel'];

function ctl_bestand_darf_ek(array $me): bool { return may($me, 'controlling.bestand_ek') && may($me, 'bestand.einkaufspreise'); }

function ctl_bestand_tagnr(string $d): int { return intdiv((int)gmmktime(12, 0, 0, (int)substr($d, 5, 2), (int)substr($d, 8, 2), (int)substr($d, 0, 4)), 86400); }
function ctl_bestand_datum(int $n): string { return gmdate('Y-m-d', $n * 86400 + 43200); }
function ctl_bestand_gueltig($v): bool
{
    return is_string($v) && preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $x) === 1 && checkdate((int)$x[2], (int)$x[3], (int)$x[1]) && (int)$x[1] >= 2000 && (int)$x[1] <= 2100;
}

/* Merkmal eines Artikels (Nummer wie in der Bestandsliste) für Filter und Gliederung */
function ctl_bestand_merkmal(string $dim, string $code): string
{
    if ($dim === 'artikel') return code_key($code);
    $a = umsatz_artikel($code);
    return umsatz_wert((string)($dim === 'vkgruppe' ? ($a['vk'] ?? '') : ($a['fa'] ?? '')));
}

/* Anfrage prüfen: Zeitraum (tage=30|90|365 oder von/bis), Gliederung, Filter */
function ctl_bestand_anfrage(array $q, array $tage): array
{
    $letzte = $tage ? (string)array_key_last($tage) : date('Y-m-d');
    $bis = isset($q['bis']) && $q['bis'] !== '' ? $q['bis'] : $letzte;
    if (!ctl_bestand_gueltig($bis)) throw new InvalidArgumentException('Bitte ein gültiges Datum angeben.');
    if (isset($q['von']) && $q['von'] !== '') {
        if (!ctl_bestand_gueltig($q['von'])) throw new InvalidArgumentException('Bitte ein gültiges Datum angeben.');
        $von = $q['von']; $art = 'eigen';
    } else {
        $n = (int)($q['tage'] ?? 30);
        if (!in_array($n, CTL_BESTAND_ZEITRAEUME, true)) throw new InvalidArgumentException('Unbekannter Zeitraum.');
        $von = ctl_bestand_datum(ctl_bestand_tagnr($bis) - $n + 1); $art = (string)$n;
    }
    $spanne = ctl_bestand_tagnr($bis) - ctl_bestand_tagnr($von) + 1;
    if ($spanne < 1) throw new InvalidArgumentException('Der Zeitraum endet vor seinem Beginn.');
    if ($spanne > CTL_BESTAND_TAGE_MAX) throw new InvalidArgumentException('Der Zeitraum darf höchstens ' . CTL_BESTAND_TAGE_MAX . ' Tage umfassen.');
    $nach = (string)($q['nach'] ?? 'artikel');
    if (!isset(CTL_BESTAND_NACH[$nach])) throw new InvalidArgumentException('Unbekannte Gliederung.');
    $filter = [];
    foreach (CTL_BESTAND_FILTER as $p => $dim) {
        $w = trim((string)($q[$p] ?? ''));
        if ($w === '') continue;
        $liste = array_slice(array_values(array_filter(array_map('trim', explode(',', $w)), fn($x) => $x !== '')), 0, 500);
        if ($dim === 'artikel') $liste = array_map(fn($x) => code_key($x), $liste);
        if ($liste) $filter[$dim] = array_fill_keys($liste, true);
    }
    return ['von' => $von, 'bis' => $bis, 'tage' => $spanne, 'zeitraum' => $art, 'nach' => $nach, 'filter' => $filter];
}

/* Letzter Tag mit Umsatzdaten (JJJJ-MM-TT) oder null */
function ctl_bestand_umsatz_bis(array $index): ?string
{
    if (!$index['monate']) return null;
    $m = (string)max(array_map('strval', array_keys($index['monate'])));
    return $m . '-' . sprintf('%02d', max(1, (int)($index['monate'][$m]['letzterTag'] ?? 1)));
}

/* Bezeichnung einer Zeile: Artikel nach den Stammdaten (sonst Name aus der Liste), Gruppen mit Namen */
function ctl_bestand_bezeichnung(string $nach, string $key, string $code, string $listenname): array
{
    if ($nach === 'artikel') {
        $a = umsatz_artikel($code);
        $name = $a && $a['name'] !== '' ? $a['name'] : ($listenname !== '' ? $listenname : "Artikel $code");
        $vk = (string)($a['vk'] ?? '');
        $g = $vk !== '' ? (string)(umsatz_stamm()['vkgruppen'][$vk]['name'] ?? $vk) : '';
        return ['name' => $name, 'sub' => trim($code . ($g !== '' ? ' · ' . $g : ''))];
    }
    if ($key === UMSATZ_OHNE) return ['name' => $nach === 'vkgruppe' ? 'ohne Artikelgruppe' : 'ohne Fleischart', 'sub' => ''];
    if ($nach === 'vkgruppe') {
        $g = umsatz_stamm()['vkgruppen'][$key] ?? null;
        return $g ? ['name' => (string)($g['name'] ?? $key), 'sub' => 'Gruppe ' . $key] : ['name' => "Artikelgruppe $key", 'sub' => 'nicht in den Stammdaten'];
    }
    return ['name' => $key, 'sub' => ''];
}

/* Kennzahlen aus den Summen einer Zeile (bzw. aller Zeilen) */
function ctl_bestand_kennzahlen(array $r, int $listen, ?float $absatz, int $absatzTage, bool $ek): array
{
    $o = $listen > 0 ? $r['summe'] / $listen : 0.0;
    $reichweite = $absatz !== null && $absatz > 0 && $absatzTage > 0 ? $r['kg'] / ($absatz / $absatzTage) : null;
    $umschlag = $absatz !== null && $o > 0 ? max(0.0, $absatz) / $o : null;
    $hinweis = null;
    if ($absatz !== null) {
        if ($absatz <= 0 && $r['kg'] > 0) $hinweis = 'ohne';
        elseif ($reichweite !== null && $reichweite >= CTL_BESTAND_LANGE) $hinweis = 'lange';
        elseif ($reichweite !== null && $reichweite < CTL_BESTAND_KNAPP) $hinweis = 'knapp';
    }
    $w = ['kg' => round($r['kg'], 1), 'kgStart' => round($r['start'], 1),
          'delta' => $r['start'] > 0 ? round(($r['kg'] - $r['start']) / $r['start'] * 100, 1) : null,
          'oKg' => round($o, 1), 'zugang' => round($r['zugang'], 1), 'partien' => $r['partien'],
          'absatz' => $absatz === null ? null : round($absatz, 1),
          'reichweite' => $reichweite === null ? null : round($reichweite, 1),
          'umschlag' => $umschlag === null ? null : round($umschlag, 2),
          'umschlagJahr' => $umschlag === null || $absatzTage < 1 ? null : round($umschlag * 365 / $absatzTage, 1),
          'hinweis' => $hinweis];
    if ($ek) $w += ['ekWert' => round($r['ekWert'], 2), 'ekKg' => round($r['ekKg'], 1)];
    return $w;
}

/* Mini-Verlauf: höchstens CTL_BESTAND_SPARK Punkte, gleichmäßig über die Listen */
function ctl_bestand_spark(array $kg, int $n): array
{
    if ($n <= CTL_BESTAND_SPARK) { $out = []; for ($i = 0; $i < $n; $i++) $out[] = round($kg[$i] ?? 0.0, 1); return $out; }
    $out = [];
    for ($j = 0; $j < CTL_BESTAND_SPARK; $j++) { $i = (int)round($j * ($n - 1) / (CTL_BESTAND_SPARK - 1)); $out[] = round($kg[$i] ?? 0.0, 1); }
    return $out;
}

/* Auswertung (Aktion controlling_bestand): Stand, Zeitraum, Summen, Tagesreihen und Zeilen der Gliederung */
function ctl_bestand_auswertung(array $q, array $me): array
{
    $index = bestand_verlauf_index();
    $a = ctl_bestand_anfrage($q, $index);
    $ek = ctl_bestand_darf_ek($me);
    $umsatzIndex = umsatzdaten_index();
    $umsatzBis = ctl_bestand_umsatz_bis($umsatzIndex);

    /* Tagesstände im Zeitraum (aufsteigend); fehlt ein Tagesdokument, zählt der Tag nicht */
    $listen = [];
    foreach (array_keys($index) as $d) {
        $d = (string)$d;
        if ($d < $a['von'] || $d > $a['bis']) continue;
        $t = bestand_verlauf_tag($d);
        if ($t !== null) $listen[$d] = $t;
    }
    $n = count($listen);
    $leer = fn() => ['kg' => 0.0, 'start' => 0.0, 'summe' => 0.0, 'zugang' => 0.0, 'ekWert' => 0.0, 'ekKg' => 0.0, 'partien' => 0, 'tage' => []];
    $art = []; $codes = []; $namen = []; $ok = []; $reihe = [];
    $i = 0;
    foreach ($listen as $d => $t) {
        $tag = ['d' => $d, 'kg' => 0.0, 'zugang' => 0.0, 'partien' => 0, 'artikel' => 0, 'ekWert' => 0.0];
        foreach ($t['artikel'] as $code => $w) {
            $code = (string)$code; $key = code_key($code);
            if (!isset($ok[$key])) {
                $ok[$key] = true;
                foreach ($a['filter'] as $dim => $erlaubt) if (!isset($erlaubt[ctl_bestand_merkmal($dim, $code)])) { $ok[$key] = false; break; }
            }
            if (!$ok[$key] || !is_array($w)) continue;
            $kg = (float)($w[0] ?? 0); $zu = (float)($w[1] ?? 0); $ekw = (float)($w[2] ?? 0); $ekk = (float)($w[3] ?? 0); $pa = (int)($w[4] ?? 0);
            $r = $art[$key] ?? $leer();
            $r['summe'] += $kg; $r['tage'][$i] = $kg;
            if ($i === 0) $r['start'] = $kg;
            if ($i === $n - 1) { $r['kg'] = $kg; $r['zugang'] = $zu; $r['ekWert'] = $ekw; $r['ekKg'] = $ekk; $r['partien'] = $pa; }
            $art[$key] = $r;
            $codes[$key] = $code; $namen[$key] = (string)($t['namen'][$code] ?? ($namen[$key] ?? ''));
            $tag['kg'] += $kg; $tag['zugang'] += $zu; $tag['partien'] += $pa; $tag['ekWert'] += $ekw; if ($kg > 0) $tag['artikel']++;
        }
        $tag['kg'] = round($tag['kg'], 1); $tag['zugang'] = round($tag['zugang'], 1);
        if ($ek) $tag['ekWert'] = round($tag['ekWert'], 2); else unset($tag['ekWert']);
        $reihe[] = $tag; $i++;
    }

    /* Absatz der Lagerartikel aus den Umsatzdaten (berechnete Menge, Tausendstel → kg) */
    $absatzBis = $umsatzBis !== null && $umsatzBis < $a['bis'] ? $umsatzBis : $a['bis'];
    $mitAbsatz = $umsatzBis !== null && $absatzBis >= $a['von'] && $n > 0;
    $absatzTage = $mitAbsatz ? ctl_bestand_tagnr($absatzBis) - ctl_bestand_tagnr($a['von']) + 1 : 0;
    $absatz = []; $absatzTag = [];
    if ($mitAbsatz) {
        $vonTag = (int)substr($a['von'], 8, 2); $bisTag = (int)substr($absatzBis, 8, 2);
        $vonM = substr($a['von'], 0, 7); $bisM = substr($absatzBis, 0, 7);
        foreach (umsatzdaten_monatsfolge($vonM, $bisM) as $m) {
            if (!isset($umsatzIndex['monate'][$m])) continue;
            foreach (umsatzdaten_monat($m) as $z) {
                if ($z[9] !== 1 || ($m === $vonM && $z[0] < $vonTag) || ($m === $bisM && $z[0] > $bisTag)) continue;
                $key = code_key((string)$z[2]);
                if (!isset($art[$key])) continue;   // nur Artikel, die im Zeitraum im Bestand waren (Filter schon angewandt)
                $absatz[$key] = ($absatz[$key] ?? 0) + $z[4];
                $d = $m . '-' . sprintf('%02d', $z[0]);
                $absatzTag[$d] = ($absatzTag[$d] ?? 0) + $z[4];
            }
        }
    }

    /* Zeilen der Gliederung und Gesamtsumme */
    $gesamt = $leer(); $gesamtAbsatz = 0; $grp = []; $grpAbsatz = []; $grpInfo = []; $grpCode = []; $lange = 0; $knapp = 0;
    foreach ($art as $key => $r) {
        $abs = $mitAbsatz ? ($absatz[$key] ?? 0) / 1000 : null;
        $hinweis = ctl_bestand_kennzahlen($r, $n, $abs, $absatzTage, false)['hinweis'];
        if ($hinweis === 'lange') $lange++; elseif ($hinweis === 'knapp') $knapp++;
        foreach (['kg', 'start', 'summe', 'zugang', 'ekWert', 'ekKg'] as $f) $gesamt[$f] += $r[$f];
        $gesamt['partien'] += $r['partien']; $gesamtAbsatz += $absatz[$key] ?? 0;
        $g = $a['nach'] === 'artikel' ? $key : ctl_bestand_merkmal($a['nach'], $codes[$key]);
        $z = $grp[$g] ?? $leer();
        foreach (['kg', 'start', 'summe', 'zugang', 'ekWert', 'ekKg'] as $f) $z[$f] += $r[$f];
        $z['partien'] += $r['partien'];
        foreach ($r['tage'] as $j => $kg) $z['tage'][$j] = ($z['tage'][$j] ?? 0) + $kg;
        $grp[$g] = $z; $grpAbsatz[$g] = ($grpAbsatz[$g] ?? 0) + ($absatz[$key] ?? 0);
        $grpInfo[$g] = ($grpInfo[$g] ?? 0) + 1;
        if (!isset($grpCode[$g])) $grpCode[$g] = $codes[$key];
    }
    $zeilen = [];
    foreach ($grp as $g => $z) {
        $b = ctl_bestand_bezeichnung($a['nach'], (string)$g, $grpCode[$g], $namen[$g] ?? '');
        $zeilen[] = ['key' => $a['nach'] === 'artikel' ? $grpCode[$g] : (string)$g] + $b
            + ctl_bestand_kennzahlen($z, $n, $mitAbsatz ? $grpAbsatz[$g] / 1000 : null, $absatzTage, $ek)
            + ['artikel' => $grpInfo[$g], 'spark' => ctl_bestand_spark($z['tage'], $n)];
    }
    usort($zeilen, fn($x, $y) => $y['kg'] <=> $x['kg'] ?: $y['oKg'] <=> $x['oKg'] ?: strnatcasecmp($x['name'], $y['name']));
    $summen = ctl_bestand_kennzahlen($gesamt, $n, $mitAbsatz ? $gesamtAbsatz / 1000 : null, $absatzTage, $ek);
    unset($summen['hinweis']);
    $summen += ['artikel' => count(array_filter($art, fn($r) => $r['kg'] > 0)), 'lange' => $lange, 'knapp' => $knapp,
                'absatzJeTag' => $mitAbsatz && $absatzTage > 0 ? round($gesamtAbsatz / 1000 / $absatzTage, 1) : null];
    ksort($absatzTag);
    $absatzReihe = [];
    foreach ($absatzTag as $d => $v) $absatzReihe[] = ['d' => $d, 'kg' => round($v / 1000, 1)];

    $tageListe = array_keys($index);
    return ['ok' => true,
            'stand' => ['listen' => count($tageListe), 'erste' => $tageListe[0] ?? null, 'letzte' => $tageListe ? end($tageListe) : null, 'umsatzBis' => $umsatzBis],
            'zeitraum' => ['von' => $a['von'], 'bis' => $a['bis'], 'tage' => $a['tage'], 'art' => $a['zeitraum'], 'listen' => $n,
                           'erste' => $n ? array_key_first($listen) : null, 'letzte' => $n ? array_key_last($listen) : null,
                           'absatzBis' => $mitAbsatz ? $absatzBis : null, 'absatzTage' => $absatzTage],
            'nach' => $a['nach'], 'rechte' => ['ek' => $ek], 'grenzen' => ['lange' => CTL_BESTAND_LANGE, 'knapp' => CTL_BESTAND_KNAPP],
            'summen' => $summen, 'reihe' => $reihe, 'absatzReihe' => $absatzReihe,
            'zeilen' => array_slice($zeilen, 0, CTL_BESTAND_ZEILEN_MAX), 'gesamt' => count($zeilen)];
}

/* Detail (Aktion controlling_bestand_detail): ein Artikel, eine Artikelgruppe oder Fleischart (?dim=…&wert=…) im Zeitraum der
   Seite – Kennzahlen und je Liste Bestand, erwartete Zugänge, Partien (Lagerwert nur mit EK-Recht), Absatz je Tag */
function ctl_bestand_detail(array $q, array $me): array
{
    $dim = (string)($q['dim'] ?? '');
    $wert = trim((string)($q['wert'] ?? ''));
    if (!isset(CTL_BESTAND_NACH[$dim]) || $wert === '' || strlen($wert) > 80) throw new InvalidArgumentException('Unbekannte Auswahl.');
    $p = array_search($dim, CTL_BESTAND_FILTER, true);
    $q[$p] = $wert; $q['nach'] = $dim;
    $r = ctl_bestand_auswertung($q, $me);
    $zeile = $r['zeilen'][0] ?? null;
    if ($zeile === null) {
        $b = ctl_bestand_bezeichnung($dim, $dim === 'artikel' ? code_key($wert) : $wert, $wert, '');
        $zeile = ['key' => $wert] + $b;
    }
    return ['ok' => true, 'dim' => $dim, 'zeile' => $zeile, 'stand' => $r['stand'], 'zeitraum' => $r['zeitraum'], 'rechte' => $r['rechte'],
            'grenzen' => $r['grenzen'], 'reihe' => $r['reihe'], 'absatzReihe' => $r['absatzReihe']];
}

/* Grunddaten (Aktion controlling_bestand_daten): Stand des Verlaufs, Rechte, Auswahllisten für die Filter (nur Nummern und Namen) */
function ctl_bestand_grunddaten(array $me): array
{
    $index = bestand_verlauf_index();
    $tage = array_keys($index);
    $artikel = [];
    if ($tage) {
        $t = bestand_verlauf_tag((string)end($tage));
        foreach (($t['artikel'] ?? []) as $code => $w) {
            $code = (string)$code; $x = umsatz_artikel($code);
            $artikel[] = ['nr' => $code, 'name' => $x && $x['name'] !== '' ? $x['name'] : (string)($t['namen'][$code] ?? "Artikel $code")];
        }
    }
    $vk = array_values(array_map(fn($g) => ['nr' => (string)$g['nr'], 'name' => (string)($g['name'] ?? '')], umsatz_stamm()['vkgruppen']));
    return ['ok' => true, 'stand' => ['listen' => count($tage), 'erste' => $tage[0] ?? null, 'letzte' => $tage ? end($tage) : null,
                                      'umsatzBis' => ctl_bestand_umsatz_bis(umsatzdaten_index())],
            'rechte' => ['ek' => ctl_bestand_darf_ek($me)], 'zeitraeume' => CTL_BESTAND_ZEITRAEUME,
            'gliederungen' => array_map(fn($id, $name) => ['id' => $id, 'name' => $name], array_keys(CTL_BESTAND_NACH), CTL_BESTAND_NACH),
            'grenzen' => ['lange' => CTL_BESTAND_LANGE, 'knapp' => CTL_BESTAND_KNAPP],
            'optionen' => ['vkgruppen' => $vk, 'fleischarten' => CATEGORIES, 'artikel' => $artikel]];
}
