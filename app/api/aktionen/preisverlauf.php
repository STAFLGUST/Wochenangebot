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
                // history_week: ohne Kundenpreise – die Ansicht nutzt nur price (GR-002)
                $h = history_week($id);
                if ($h) { $h['id'] = $id; $weeks[] = $h; }
            }
            respond(['ok' => true, 'weeks' => $weeks]);
        }

        /* Vorwochenspalte des Editors. Die Preise je Kundenangebot stehen nicht im Preisverlauf (der führt keine
           Kundenpreise), sondern im vollständigen Wochenstand (Wochenablage, aktuelles Angebot, versionen/*) – und gehen
           nur an Aufrufer mit Modulzugang Angebot heraus, also hinter demselben Tor wie die Aktionen draft und version
           (GR-002, GR-103). Ohne diesen Zugang bleibt es beim Wochenpreis. */
        case 'history_prev': {
            $me = require_auth();
            if (!may($me, 'preisverlauf.sehen') && !may($me, 'angebot.bearbeiten')) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
            header('Cache-Control: no-store');
            history_backfill();
            $w = (int)($_GET['week'] ?? 0);
            $y = (int)($_GET['year'] ?? 0);
            if ($y < 2000 || $y > 2100 || !kw_gueltig($w, $y)) respond(['ok' => true, 'week' => null]);
            $cur = history_id($w, $y);
            $prev = null;
            foreach (history_ids() as $id) if (strcmp($id, $cur) < 0) $prev = $id;   // jüngste Woche vor der Angebotswoche
            $h = $prev ? history_week($prev) : null;
            if ($h) {
                $var = [];
                if (modul_zugang_frei($me, 'angebot')) {
                    require_once dirname(__DIR__) . '/module/angebot/wochen.php';
                    [$voll] = angebot_woche_modell($prev);
                    // Zuordnung über die Artikelnummer (der Preisverlauf führt keine Artikel-IDs); Artikel ohne Nummer
                    // behalten den Wochenpreis
                    foreach (is_array($voll['items'] ?? null) ? $voll['items'] : [] as $it)
                        if (!empty($it['variants']) && !empty($it['code'])) $var[(string)$it['code']] = $it['variants'];
                }
                $items = [];
                foreach (($h['items'] ?? []) as $it) {
                    $row = ['code' => $it['code'] ?? null, 'name' => $it['name'] ?? '', 'price' => $it['price'] ?? ['status' => 'none']];
                    if (isset($var[(string)($it['code'] ?? '')])) $row['variants'] = $var[(string)$it['code']];
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
            if (!is_int($week) || !is_int($year) || $year < 2000 || $year > 2100 || !kw_gueltig($week, $year)) fail('Kalenderwoche oder Jahr ungültig.', 422);
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
            with_lock('historie_geloescht', function () use ($id) {
                $del = store_read('historie_geloescht') ?? [];
                if (!in_array($id, $del, true)) { $del[] = $id; store_write('historie_geloescht', $del); }
            });
            respond(['ok' => true]);
        }
}
