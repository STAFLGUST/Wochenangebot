<?php
declare(strict_types=1);
/* Preisverlauf (Wochenstände) */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Preisverlauf ---------------- */

function history_id(int $week, int $year): string { return sprintf('%04d-%02d', $year, $week); }
function history_ids(): array
{
    $ids = [];
    foreach (store_names('historie') as $f) {
        $id = basename($f);
        if (preg_match('/^\d{4}-\d{2}$/', $id)) $ids[] = $id;
    }
    sort($ids);
    return $ids;
}
/* Preis-Stand einer Woche aus einem veröffentlichten Angebot */
function history_from_model(array $m, string $origin, ?string $at): ?array
{
    $w = $m['meta']['week'] ?? null;
    $y = $m['meta']['year'] ?? null;
    if (!is_int($w) || !is_int($y)) return null;
    $gn = [];
    foreach (($m['groups'] ?? []) as $g) $gn[$g['id']] = $g['name'];
    $items = [];
    foreach (($m['items'] ?? []) as $it) {
        $row = ['code' => $it['code'] ?? null, 'name' => (string)($it['name'] ?? ''), 'group' => $gn[$it['groupId'] ?? ''] ?? '',
                'category' => $it['category'] ?? 'Sonstiges', 'price' => $it['price'] ?? ['status' => 'none']];
        if (!empty($it['altPrices'])) $row['altPrices'] = $it['altPrices'];
        if (!empty($it['variants'])) $row['variants'] = $it['variants'];
        $items[] = $row;
    }
    return ['week' => $w, 'year' => $y, 'origin' => $origin, 'source' => (string)($m['meta']['source'] ?? ''), 'savedAt' => $at ?: now(), 'items' => $items];
}
/* Bisherige Veröffentlichungen einmalig in den Preisverlauf übernehmen (gelöschte Wochen ausgenommen) */
function history_backfill(): void
{
    $have = array_flip(history_ids());
    $deleted = array_flip(store_read('historie_geloescht') ?? []);
    $sources = [];
    foreach (store_names('versionen') as $f) $sources[] = store_read('versionen/' . basename($f));
    $sources[] = store_read('angebot');
    $cand = [];
    foreach ($sources as $m) {
        if (!$m) continue;
        $h = history_from_model($m, 'Veröffentlichung', $m['publishedAt'] ?? null);
        if (!$h) continue;
        $id = history_id($h['week'], $h['year']);
        if (isset($have[$id]) || isset($deleted[$id])) continue;
        if (!isset($cand[$id]) || strcmp((string)$h['savedAt'], (string)$cand[$id]['savedAt']) > 0) $cand[$id] = $h;
    }
    foreach ($cand as $id => $h) store_write('historie/' . $id, $h);
}
function history_undelete(string $id): void
{
    $del = store_read('historie_geloescht') ?? [];
    if (in_array($id, $del, true)) store_write('historie_geloescht', array_values(array_diff($del, [$id])));
}
function clean_history_items($items): array
{
    if (!is_array($items) || !$items) throw new InvalidArgumentException('Die Woche enthält keine Artikel.');
    if (count($items) > 5000) throw new InvalidArgumentException('Zu viele Artikel (max. 5000).');
    $out = [];
    foreach ($items as $it) {
        if (!is_array($it)) continue;
        $name = s($it['name'] ?? null, 200, false);
        if ($name === null) continue;
        $code = s($it['code'] ?? null, 20);
        if ($code === '' || ($code !== null && !preg_match('#^[0-9A-Za-z./-]+$#', $code))) $code = null;
        $cat = in_array($it['category'] ?? '', CATEGORIES, true) ? $it['category'] : 'Sonstiges';
        $row = ['code' => $code, 'name' => $name, 'group' => s($it['group'] ?? '', 200) ?? '', 'category' => $cat, 'price' => clean_price($it['price'] ?? null, $name)];
        $alts = [];
        foreach (array_slice(is_array($it['altPrices'] ?? null) ? $it['altPrices'] : [], 0, 5) as $ap) $alts[] = clean_price($ap, $name);
        if ($alts) $row['altPrices'] = $alts;
        $out[] = $row;
    }
    if (!$out) throw new InvalidArgumentException('Die Woche enthält keine gültigen Artikel.');
    return $out;
}
