<?php
declare(strict_types=1);
/* Aktionen: Bestand und Stammdaten
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'stock': {
            $me = require_perm('bestand.sehen');
            header('Cache-Control: no-store');
            $st = store_read('bestand');
            respond(['ok' => true, 'stock' => may($me, 'bestand.einkaufspreise') ? $st : stock_ohne_ek($st),
                     'prices' => may($me, 'preisverlauf.sehen') ? stock_week_prices() : ['allowed' => false]]);
        }

        /* Bestand als PDF (ohne Preise, erfassten Bestand, Gesamt verfügbar und Zugänge): Reihenfolge/Gruppen aus der Ansicht,
           Zahlen aus dem gespeicherten Bestand (lib/bestand-pdf.php) */
        case 'stock_pdf': {
            require_perm('bestand.sehen', true);
            $b = body();
            $st = store_read('bestand');
            if (!$st) fail('Es ist noch kein Bestand übernommen.', 404);
            $src = $b['rows'] ?? [];
            if (!is_array($src) || !array_is_list($src) || count($src) > 25000) fail('Ungültige Auswahl.', 422);
            $zeilen = [];
            foreach ($src as $z) {
                if (is_array($z) && is_string($z['g'] ?? null)) { $zeilen[] = ['g' => s($z['g'], 80) ?? '']; continue; }
                if (is_array($z) && is_string($z['c'] ?? null) && preg_match('#^[0-9A-Za-z./-]{1,20}$#', $z['c'])) { $zeilen[] = ['c' => $z['c']]; continue; }
                fail('Ungültige Auswahl.', 422);
            }
            $mhd = !empty($b['mhd']);
            $q = s($b['q'] ?? '', 60) ?? '';
            $zusatz = $mhd ? ' – MHD bis ' . date('d.m.Y', strtotime('+14 days')) : ($q !== '' ? ' – Suche „' . $q . '“' : '');
            require_once __DIR__ . '/../lib/bestand-pdf.php';
            $pdf = stock_pdf($st, $zeilen, $zusatz);
            header('Content-Type: application/pdf');
            header('Content-Disposition: attachment; filename="' . stock_pdf_name($st, $mhd ? 'MHD' : ($q !== '' ? 'Auswahl' : '')) . '"');
            header('Cache-Control: private, no-store');
            header('Content-Length: ' . strlen($pdf));
            echo $pdf;
            exit;
        }

        case 'stock_import': {
            $me = require_perm('bestand.importieren', true);
            $b = body();
            $incoming = clean_incoming($b['incoming'] ?? []);
            $articles = clean_stock($b, count($incoming) > 0);
            $date = clean_date($b['date'] ?? null);
            $total = 0.0;
            foreach ($articles as $a) $total += $a['kg'];
            $st = ['date' => $date, 'source' => s($b['source'] ?? '', 200) ?? '', 'importedAt' => now(), 'importedBy' => $me['name'], 'articles' => $articles, 'incoming' => $incoming];
            store_write('bestand', $st);
            audit('stock', 'Bestand übernommen: ' . ($st['source'] ?: 'Datei') . ($date ? ' – Stand ' . date('d.m.Y', strtotime($date)) : '') . ', ' . count($articles) . ' Artikel, ' . number_format($total, 2, ',', '.') . ' kg eingelagert, ' . count($incoming) . ' erwartete Zugänge');
            respond(['ok' => true, 'stock' => may($me, 'bestand.einkaufspreise') ? $st : stock_ohne_ek($st)]);
        }

        case 'master': {
            require_perm('stammdaten.sehen');
            header('Cache-Control: no-store');
            $m = store_read('stammdaten');
            respond(['ok' => true, 'master' => $m ?: ['rev' => 0, 'articles' => [], 'updatedAt' => null]]);
        }

        case 'master_save': {
            $me = require_perm('stammdaten.bearbeiten', true);
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
