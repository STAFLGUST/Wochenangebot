<?php
declare(strict_types=1);
/* Bestandsliste und Stammdaten */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Bestand ---------------- */

/* Nur lesend: exakte ISO-Wochen, keine Entwurfspreise und kein Rückgriff auf ältere Wochen.
   Historie hat Vorrang; alte Veröffentlichungen ergänzen nur noch nicht archivierte Wochen. */
function stock_week_prices(?DateTimeImmutable $today = null): array
{
    $today = ($today ?? new DateTimeImmutable('now', new DateTimeZone('Europe/Berlin')))->setTimezone(new DateTimeZone('Europe/Berlin'));
    $dates = [$today, $today->modify('-7 days')];
    $deleted = store_read('historie_geloescht') ?? [];
    $weeks = [];
    foreach ($dates as $date) {
        $week = (int)$date->format('W'); $year = (int)$date->format('o');
        $id = history_id($week, $year);
        $h = store_read('historie/' . $id);
        if (!$h && !in_array($id, $deleted, true)) {
            $sources = ['angebot'];
            foreach (store_names('versionen') as $f) $sources[] = 'versionen/' . basename($f);
            foreach ($sources as $source) {
                $m = store_read($source);
                if (!$m || ($m['meta']['week'] ?? null) !== $week || ($m['meta']['year'] ?? null) !== $year) continue;
                $candidate = history_from_model($m, 'Veröffentlichung', $m['publishedAt'] ?? null);
                if (!$h || strcmp((string)$candidate['savedAt'], (string)$h['savedAt']) > 0) $h = $candidate;
            }
        }
        // Keine Kundenpreise, Einkaufspreise oder sonstigen internen Angebotsfelder ergänzen.
        $items = [];
        foreach ($h['items'] ?? [] as $it) {
            if (empty($it['code'])) continue;
            $items[] = ['code' => $it['code'], 'price' => $it['price'] ?? ['status' => 'none']];
        }
        $weeks[] = ['week' => $week, 'year' => $year, 'available' => $h !== null,
                    'source' => $h['source'] ?? null, 'origin' => $h['origin'] ?? null, 'items' => $items];
    }
    return ['allowed' => true, 'current' => $weeks[0], 'previous' => $weeks[1]];
}

function clean_date($v): ?string
{
    if (!is_string($v) || !preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $m)) return null;
    return checkdate((int)$m[2], (int)$m[3], (int)$m[1]) && (int)$m[1] >= 2000 && (int)$m[1] <= 2100 ? $v : null;
}
function clean_kg($v, string $where): float
{
    if (!is_int($v) && !is_float($v)) throw new InvalidArgumentException("Menge fehlt ($where).");
    $v = (float)$v;
    if (!is_finite($v) || abs($v) > 10000000) throw new InvalidArgumentException("Menge außerhalb des gültigen Bereichs ($where).");
    return round($v, 3);
}
function clean_incoming($rows): array
{
    if (!is_array($rows) || !array_is_list($rows) || count($rows) > 20000) throw new InvalidArgumentException('Ungültige Liste erwarteter Zugänge (max. 20000).');
    $out = [];
    foreach ($rows as $row) {
        if (!is_array($row)) throw new InvalidArgumentException('Ungültiger erwarteter Zugang.');
        $code = s($row['code'] ?? null, 20, false);
        if ($code === null || !preg_match('#^[0-9A-Za-z./-]+$#', $code)) throw new InvalidArgumentException('Ungültige Artikelnummer im Zugang.');
        $kg = clean_kg($row['kg'] ?? null, $code);
        if ($kg <= 0) throw new InvalidArgumentException('Zugangsmenge muss größer als null sein.');
        $arrival = clean_date($row['arrival'] ?? null);
        if (isset($row['arrival']) && $arrival === null) throw new InvalidArgumentException('Ungültiges Ankunftsdatum im Zugang.');
        $out[] = ['code' => $code, 'name' => s($row['name'] ?? '', 200) ?: '(ohne Bezeichnung)',
                  'lot' => s($row['lot'] ?? '', 20) ?? '', 'marke' => s($row['marke'] ?? '', 40) ?? '', 'arrival' => $arrival, 'kg' => $kg];
    }
    return $out;
}
function clean_stock($b, bool $allowEmpty = false): array
{
    $src = is_array($b['articles'] ?? null) ? $b['articles'] : [];
    if (!$src && !$allowEmpty) throw new InvalidArgumentException('Die Bestandsliste enthält keine Artikel mit eingelagertem Bestand.');
    if (count($src) > 20000) throw new InvalidArgumentException('Zu viele Artikel in der Bestandsliste.');
    $out = [];
    $seen = [];
    foreach ($src as $a) {
        if (!is_array($a)) continue;
        $code = s($a['code'] ?? null, 20, false);
        if ($code === null || !preg_match('#^[0-9A-Za-z./-]+$#', $code)) throw new InvalidArgumentException('Ungültige Artikelnummer in der Bestandsliste.');
        $key = ctype_digit($code) ? (ltrim($code, '0') === '' ? '0' : ltrim($code, '0')) : strtoupper($code);
        if (isset($seen[$key])) throw new InvalidArgumentException("Artikelnummer $code kommt in der Bestandsliste doppelt vor.");
        $seen[$key] = true;
        $lots = [];
        foreach (array_slice(is_array($a['lots'] ?? null) ? $a['lots'] : [], 0, 500) as $l) {
            if (!is_array($l)) continue;
            $kolli = $l['kolli'] ?? null;
            $ek = $l['ek'] ?? null;   // Einkaufspreis € je kg – nur für Berechtigte ausgeliefert (stock_ohne_ek)
            $lots[] = ['lot' => s($l['lot'] ?? '', 20) ?? '', 'marke' => s($l['marke'] ?? '', 40) ?? '', 'arrival' => clean_date($l['arrival'] ?? null), 'mhd' => clean_date($l['mhd'] ?? null),
                       'kolli' => (is_int($kolli) || is_float($kolli)) && abs($kolli) < 1000000 ? round((float)$kolli, 2) : null, 'kg' => clean_kg($l['kg'] ?? null, $code),
                       'ek' => (is_int($ek) || is_float($ek)) && $ek >= 0 && $ek < 100000 ? round((float)$ek, 3) : null];
        }
        $kg = clean_kg($a['kg'] ?? null, $code);
        if ($kg <= 0) continue;
        $mhd = clean_date($a['mhd'] ?? null);
        $out[] = ['code' => $code, 'name' => s($a['name'] ?? '', 200) ?: '(ohne Bezeichnung)', 'kg' => $kg, 'mhd' => $mhd,
                  'mhdKg' => $mhd !== null && isset($a['mhdKg']) ? clean_kg($a['mhdKg'], $code) : null, 'lots' => $lots];
    }
    if (!$out && !$allowEmpty) throw new InvalidArgumentException('Die Bestandsliste enthält keine Artikel mit eingelagertem Bestand.');
    return $out;
}

/* Einkaufspreise aus einem Bestand entfernen (für Nutzer ohne Recht „bestand.einkaufspreise“) */
function stock_ohne_ek(?array $st): ?array
{
    if (!$st) return $st;
    foreach ($st['articles'] ?? [] as $i => $a) foreach ($a['lots'] ?? [] as $j => $l) unset($st['articles'][$i]['lots'][$j]['ek']);
    return $st;
}

/* ---------------- Stammdaten ---------------- */

function code_key(string $c): string { return ctype_digit($c) ? (ltrim($c, '0') === '' ? '0' : ltrim($c, '0')) : strtoupper($c); }
function clean_master($list): array
{
    if (!is_array($list)) throw new InvalidArgumentException('Stammdaten fehlen.');
    if (count($list) > 20000) throw new InvalidArgumentException('Zu viele Stammdatensätze.');
    $out = [];
    $seen = [];
    foreach ($list as $a) {
        if (!is_array($a)) continue;
        $code = s($a['code'] ?? null, 20, false);
        if ($code === null || !preg_match('#^[0-9A-Za-z./-]+$#', $code)) throw new InvalidArgumentException('Ungültige Artikelnummer in den Stammdaten.');
        $k = code_key($code);
        if (isset($seen[$k])) throw new InvalidArgumentException("Artikelnummer $code ist in den Stammdaten doppelt.");
        $seen[$k] = true;
        $name = s($a['name'] ?? null, 200, false);
        if ($name === null) throw new InvalidArgumentException("Artikel $code hat keine Bezeichnung.");
        $cat = in_array($a['category'] ?? '', CATEGORIES, true) ? $a['category'] : 'Sonstiges';
        $cond = in_array($a['condition'] ?? '', CONDITIONS, true) ? $a['condition'] : 'unbekannt';
        $origin = s($a['origin'] ?? null, 60);
        $e = ['code' => $code, 'name' => $name, 'category' => $cat, 'origin' => ($origin === '' ? null : $origin), 'condition' => $cond];
        // Felder aus der Warenwirtschaft (Artikelstammdaten-Export): VK-Gruppe (Stammdaten → VK-Gruppen) und GTIN
        $vk = s($a['vkGruppe'] ?? '', 10) ?? '';
        if ($vk !== '' && !preg_match('/^[0-9A-Za-z._-]{1,10}$/', $vk)) throw new InvalidArgumentException("Artikel $code: ungültige VK-Gruppe.");
        $gtin = preg_replace('/\s+/', '', (string)($a['gtin'] ?? ''));
        if ($gtin !== '' && !preg_match('/^\d{8,14}$/', $gtin)) throw new InvalidArgumentException("Artikel $code: ungültige GTIN (8 bis 14 Ziffern).");
        if ($vk !== '') $e['vkGruppe'] = $vk;
        if ($gtin !== '') $e['gtin'] = $gtin;
        $out[] = $e;
    }
    usort($out, function ($x, $y) { return strnatcmp($x['code'], $y['code']); });
    return $out;
}
function master_changes(array $old, array $new): array
{
    $o = []; foreach ($old as $a) $o[code_key($a['code'])] = $a;
    $n = []; foreach ($new as $a) $n[code_key($a['code'])] = $a;
    $L = ['name' => 'Bezeichnung', 'category' => 'Fleischart', 'origin' => 'Herkunft', 'condition' => 'Zustand', 'vkGruppe' => 'VK-Gruppe', 'gtin' => 'GTIN'];
    $d = [];
    foreach ($n as $k => $a) {
        if (!isset($o[$k])) { $d[] = ['k' => "s$k|+", 'code' => $a['code'], 'name' => $a['name'], 'f' => 'Neuer Stammsatz', 'from' => '', 'to' => $a['category'] . ' · ' . $a['condition']]; continue; }
        foreach ($L as $f => $label) if ((string)($o[$k][$f] ?? '') !== (string)($a[$f] ?? '')) $d[] = ['k' => "s$k|$f", 'code' => $a['code'], 'name' => $a['name'], 'f' => $label, 'from' => (string)($o[$k][$f] ?? ''), 'to' => (string)($a[$f] ?? '')];
    }
    foreach ($o as $k => $a) if (!isset($n[$k])) $d[] = ['k' => "s$k|-", 'code' => $a['code'], 'name' => $a['name'], 'f' => 'Stammsatz gelöscht', 'from' => $a['name'], 'to' => ''];
    return $d;
}
