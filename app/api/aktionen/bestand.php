<?php
declare(strict_types=1);
/* Aktionen: Bestand und Stammdaten
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'stock': {
            require_auth();
            header('Cache-Control: no-store');
            respond(['ok' => true, 'stock' => store_read('bestand')]);
        }

        case 'stock_import': {
            $me = require_auth(true, 'editor');
            $b = body();
            $articles = clean_stock($b);
            $date = clean_date($b['date'] ?? null);
            $total = 0.0;
            foreach ($articles as $a) $total += $a['kg'];
            $st = ['date' => $date, 'source' => s($b['source'] ?? '', 200) ?? '', 'importedAt' => now(), 'importedBy' => $me['name'], 'articles' => $articles];
            store_write('bestand', $st);
            audit('stock', 'Bestand übernommen: ' . ($st['source'] ?: 'Datei') . ($date ? ' – Stand ' . date('d.m.Y', strtotime($date)) : '') . ', ' . count($articles) . ' Artikel, ' . number_format($total, 2, ',', '.') . ' kg eingelagert');
            respond(['ok' => true, 'stock' => $st]);
        }

        case 'master': {
            require_auth();
            header('Cache-Control: no-store');
            $m = store_read('stammdaten');
            respond(['ok' => true, 'master' => $m ?: ['rev' => 0, 'articles' => [], 'updatedAt' => null]]);
        }

        case 'master_save': {
            $me = require_auth(true, 'editor');
            $b = body();
            $articles = clean_master($b['articles'] ?? null);
            $res = with_lock('stammdaten', function () use ($b, $articles, $me) {
                $cur = store_read('stammdaten') ?: ['rev' => 0, 'articles' => []];
                if ((int)($b['rev'] ?? -1) !== (int)$cur['rev']) fail('Die Stammdaten wurden inzwischen an anderer Stelle geändert. Bitte die Seite neu laden.', 409);
                $m = ['rev' => (int)$cur['rev'] + 1, 'updatedAt' => now(), 'updatedBy' => $me['name'], 'articles' => $articles];
                store_write('stammdaten', $m);
                return [$m, master_changes($cur['articles'], $articles)];
            });
            [$m, $d] = $res;
            if ($d) audit('master', 'Stammdaten bearbeitet', array_slice($d, 0, 2000), null, true);
            respond(['ok' => true, 'rev' => $m['rev'], 'updatedAt' => $m['updatedAt']]);
        }
}
