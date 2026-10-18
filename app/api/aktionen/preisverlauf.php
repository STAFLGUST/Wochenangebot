<?php
declare(strict_types=1);
/* Aktionen: Preisverlauf
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'history_list': {
            require_auth();
            header('Cache-Control: no-store');
            history_backfill();
            $out = [];
            foreach (history_ids() as $id) {
                $h = store_read('historie/' . $id);
                if (!$h) continue;
                $out[] = ['id' => $id, 'week' => $h['week'], 'year' => $h['year'], 'origin' => $h['origin'] ?? '', 'source' => $h['source'] ?? '',
                          'savedAt' => $h['savedAt'] ?? null, 'items' => count($h['items'] ?? [])];
            }
            respond(['ok' => true, 'weeks' => $out]);
        }

        case 'history_data': {
            require_auth();
            header('Cache-Control: no-store');
            history_backfill();
            $weeks = [];
            foreach (history_ids() as $id) {
                $h = store_read('historie/' . $id);
                if ($h) { $h['id'] = $id; $weeks[] = $h; }
            }
            respond(['ok' => true, 'weeks' => $weeks]);
        }

        case 'history_prev': {
            require_auth();
            header('Cache-Control: no-store');
            history_backfill();
            $w = (int)($_GET['week'] ?? 0);
            $y = (int)($_GET['year'] ?? 0);
            if ($w < 1 || $w > 53 || $y < 2000 || $y > 2100) respond(['ok' => true, 'week' => null]);
            $cur = history_id($w, $y);
            $prev = null;
            foreach (history_ids() as $id) if (strcmp($id, $cur) < 0) $prev = $id;   // jüngste Woche vor der Angebotswoche
            $h = $prev ? store_read('historie/' . $prev) : null;
            if ($h) {
                $items = [];
                foreach (($h['items'] ?? []) as $it) {
                    $row = ['code' => $it['code'] ?? null, 'name' => $it['name'] ?? '', 'price' => $it['price'] ?? ['status' => 'none']];
                    if (!empty($it['variants'])) $row['variants'] = $it['variants'];
                    $items[] = $row;
                }
                $h = ['id' => $prev, 'week' => $h['week'], 'year' => $h['year'], 'items' => $items];
            }
            respond(['ok' => true, 'week' => $h]);
        }

        case 'history_import': {
            require_auth(true, 'editor');
            $b = body();
            $week = $b['week'] ?? null;
            $year = $b['year'] ?? null;
            if (!is_int($week) || $week < 1 || $week > 53 || !is_int($year) || $year < 2000 || $year > 2100) fail('Kalenderwoche oder Jahr ungültig.', 422);
            $items = clean_history_items($b['items'] ?? null);
            $id = history_id($week, $year);
            $replaced = store_read('historie/' . $id) !== null;
            store_write('historie/' . $id, ['week' => $week, 'year' => $year, 'origin' => 'Import', 'source' => s($b['source'] ?? '', 200) ?? '', 'savedAt' => now(), 'items' => $items]);
            history_undelete($id);
            audit('history', 'Preisverlauf: KW ' . $week . '/' . $year . ($replaced ? ' ersetzt' : ' hochgeladen') . ' – ' . (s($b['source'] ?? '', 120) ?: 'ohne Dateiname') . ', ' . count($items) . ' Artikel');
            respond(['ok' => true, 'id' => $id, 'replaced' => $replaced]);
        }

        case 'history_delete': {
            require_auth(true, 'editor');
            $id = (string)(body()['id'] ?? '');
            if (!preg_match('/^\d{4}-\d{2}$/', $id)) fail('Ungültige Woche.');
            [$hy, $hw] = array_map('intval', explode('-', $id));
            audit('history', 'Preisverlauf: KW ' . $hw . '/' . $hy . ' entfernt');
            store_delete('historie/' . $id);
            $del = store_read('historie_geloescht') ?? [];
            if (!in_array($id, $del, true)) { $del[] = $id; store_write('historie_geloescht', $del); }
            respond(['ok' => true]);
        }
}
