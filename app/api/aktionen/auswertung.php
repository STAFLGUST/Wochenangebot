<?php
declare(strict_types=1);
/* Aktionen: Auswertung (Karte der Kunden-Anmeldungen) und Aktualisieren der Ortsdaten
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'auswertung': {
            $me = require_perm('auswertung.sehen');
            header('Cache-Control: no-store');
            $tage = (int)($_GET['tage'] ?? 30);
            if (!in_array($tage, [1, 7, 30, 90], true)) $tage = 30;
            $grenze = gmdate('Y-m-d\TH:i:s\Z', time() - $tage * 86400);
            $kunden = [];
            foreach (customers_load()['customers'] as $c) $kunden[$c['id']] = ['id' => $c['id'], 'firma' => $c['firma'], 'nr' => $c['nr'] ?? '', 'ort' => $c['ort'] ?? '', 'active' => !empty($c['active'])];
            $list = array_values(array_filter(anmeldeorte_load(), function ($e) use ($grenze, $kunden) { return $e['t'] >= $grenze && isset($kunden[$e['kid']]); }));
            $used = array_flip(array_column($list, 'kid'));
            $info = ort_info();
            respond(['ok' => true, 'tage' => $tage, 'aufbewahrung' => ANMELDEORT_TAGE, 'entries' => array_reverse($list),
                     'kunden' => array_values(array_intersect_key($kunden, $used)),
                     'ortsdaten' => $info ? ['date' => $info['date'], 'orte' => $info['orte']] : null,
                     'kannAktualisieren' => $me['role'] === 'admin']);
        }

        case 'ort_update': {
            require_admin_confirmation();
            @set_time_limit(900);
            @ini_set('memory_limit', '256M');
            ignore_user_abort(true);
            // eigene Dateisperre (nicht with_lock: im SQLite-Betrieb würde das minutenlang alle Schreibzugriffe blockieren)
            if (!is_dir($DATA . '/geo')) @mkdir($DATA . '/geo', 0775, true);
            $lk = @fopen($DATA . '/geo/.orte.lock', 'c');
            if (!$lk || !flock($lk, LOCK_EX | LOCK_NB)) fail('Die Ortsdaten werden gerade schon aktualisiert. Bitte einige Minuten warten.', 409);
            try { $r = ort_download($DATA . '/geo/orte.dat.php'); }
            catch (Throwable $e) { error_log('[wochenangebot] ortsdaten: ' . $e->getMessage()); fail('Die Ortsdaten konnten nicht aktualisiert werden. Bitte später erneut versuchen.', 502); }
            finally { flock($lk, LOCK_UN); fclose($lk); }
            audit('security', 'Ortsdaten für die Auswertung aktualisiert (Stand ' . substr($r['date'], 0, 7) . ', ' . $r['orte'] . ' Orte)');
            $info = ort_info();
            respond(['ok' => true, 'ortsdaten' => ['date' => $info['date'], 'orte' => $info['orte']]]);
        }
}
