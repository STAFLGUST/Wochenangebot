<?php
declare(strict_types=1);
/* Aktionen: Preisverlauf
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'history_list': {
            require_perm('preisverlauf.sehen');
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
            require_perm('preisverlauf.sehen');
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
            $me = require_auth();
            if (!may($me, 'preisverlauf.sehen') && !may($me, 'angebot.bearbeiten')) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
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
            require_perm('preisverlauf.bearbeiten', true);
            $b = body();
            $week = $b['week'] ?? null;
            $year = $b['year'] ?? null;
            if (!is_int($week) || $week < 1 || $week > 53 || !is_int($year) || $year < 2000 || $year > 2100) fail('Kalenderwoche oder Jahr ungültig.', 422);
            // Prüfen, Speichern und Protokoll: preisverlauf_woche_speichern() (module/angebot/import.php, auch für die Importzentrale)
            $r = preisverlauf_woche_speichern($week, $year, $b['items'] ?? null, s($b['source'] ?? '', 200) ?? '');
            respond(['ok' => true, 'id' => $r['id'], 'replaced' => $r['replaced']]);
        }

        case 'history_delete': {
            require_perm('preisverlauf.bearbeiten', true);
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
