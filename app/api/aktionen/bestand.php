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

        /* MHD-Liste an den Verkauf (Knopf im Bestand): Liste und Excel vom Server, Bild der Liste aus dem Browser (nur Darstellung);
           an die Empfänger der Benachrichtigung „MHD-Liste an den Verkauf“ über das Postfach für interne E-Mails */
        case 'stock_mhd_senden': {
            $me = require_perm('bestand.mhd_senden', true);
            $b = body();
            $st = store_read('bestand');
            if (!$st) fail('Es ist noch kein Bestand übernommen.', 404);
            require_once __DIR__ . '/../lib/bestand-mhd.php';
            $l = mhd_liste($st, may($me, 'preisverlauf.sehen'));
            if (!$l['zeilen']) fail('Kein Artikel mit MHD in den nächsten 14 Tagen oder bereits abgelaufen – es gibt nichts zu senden.', 422);
            // Das Bild zeigt genau diese Liste: Abgleich mit den Artikelnummern aus dem Browser (sonst neu laden)
            $codes = $b['codes'] ?? null;
            $soll = array_column($l['zeilen'], 'code'); sort($soll, SORT_STRING);
            $ist = is_array($codes) && array_is_list($codes) && count($codes) <= 5000 ? array_map('strval', $codes) : null;
            if ($ist !== null) sort($ist, SORT_STRING);
            if ($ist !== $soll) fail('Die MHD-Liste hat sich inzwischen geändert (neuer Bestand oder neuer Tag). Bitte die Seite neu laden und erneut senden.', 409);
            $to = notify_targets('mhd');
            if (!$to) fail('Für „MHD-Liste an den Verkauf“ sind noch keine Empfänger eingetragen. Ein Administrator legt sie unter Verwaltung → E-Mail → Benachrichtigungen fest.', 409);
            $png = mhd_bild_pruefen($b['bild'] ?? null);
            $notiz = mb_substr(trim(str_replace("\r", '', preg_replace('/[\x00-\x08\x0b-\x1f]/u', '', (string)($b['notiz'] ?? '')) ?? '')), 0, 1000);
            $cfg = require_mail(true);   // nur an Mitarbeiter: Postfach für interne E-Mails
            [$subject, $text, $html, $anhaenge] = mhd_mail($l, $png, $notiz, $me, $st);
            @set_time_limit(60);
            $jobs = array_map(function ($a) use ($subject, $text, $html, $anhaenge) { return ['to' => $a, 'name' => '', 'subject' => $subject, 'text' => $text, 'html' => $html, 'anhaenge' => $anhaenge]; }, $to);
            $res = mail_send_many($cfg, $jobs);
            $ergebnis = [];
            foreach ($jobs as $k => $j) $ergebnis[] = ['to' => $j['to'], 'ok' => !empty($res[$k]['ok']), 'error' => $res[$k]['error'] ?? ''];
            with_lock('mailversand', function () use ($ergebnis, $me) {
                $log = store_read('mailversand') ?? [];
                foreach ($ergebnis as $e) $log[] = ['t' => now(), 'typ' => 'mhd', 'kid' => '', 'firma' => 'MHD-Liste', 'to' => $e['to'], 'ok' => $e['ok'], 'error' => $e['error'], 'by' => $me['name']];
                store_write('mailversand', array_slice($log, -3000));
            });
            $ok = array_values(array_filter($ergebnis, function ($e) { return $e['ok']; }));
            audit('stock', 'MHD-Liste (' . count($l['zeilen']) . ' Artikel) an den Verkauf ' . ($ok ? 'gesendet an ' . implode(', ', array_column($ok, 'to')) : 'nicht zugestellt'));
            if (!$ok) fail('MHD-Liste nicht versendet: ' . ($ergebnis[0]['error'] ?: 'Versandfehler'), 502);
            respond(['ok' => true, 'artikel' => count($l['zeilen']), 'results' => $ergebnis]);
        }

        case 'stock_import': {
            $me = require_perm('bestand.importieren', true);
            $b = body();
            $incoming = clean_incoming($b['incoming'] ?? []);
            $articles = clean_stock($b, count($incoming) > 0);
            // Speichern und Protokoll: bestand_speichern() im Importvertrag des Moduls (module/bestand/import.php, auch für die Importzentrale)
            $st = bestand_speichern(clean_date($b['date'] ?? null), s($b['source'] ?? '', 200) ?? '', $articles, $incoming, $me);
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
            // Prüfen, Revision, Speichern: stammdaten_speichern() beim Daten-Eigentümer (module/verwaltung/import.php)
            [$m, $d] = stammdaten_speichern($b['articles'] ?? null, (int)($b['rev'] ?? -1), $me);
            if ($d) audit('master', 'Stammdaten bearbeitet', array_slice($d, 0, 2000), null, true);
            respond(['ok' => true, 'rev' => $m['rev'], 'updatedAt' => $m['updatedAt']]);
        }
}
