<?php
/* Notfall: alle Wartungen beenden – Angebotsseite (Dokument „wartung“) und alle Bereiche (Dokument „module“).
   Für den Fall, dass eine Wartung die Arbeit blockiert und niemand mehr in die Verwaltung kommt. Auch mit SQLite.
   Aufruf auf dem Server über deploy/wartung-aus.sh; in Tests: DATA_DIR=<Testdaten> php deploy/wartung-aus.php */
$DATA = getenv('DATA_DIR') ?: '/var/www/html/data';
require is_file(__DIR__ . '/../app/api/storage.php') ? __DIR__ . '/../app/api/storage.php' : '/var/www/html/api/storage.php';
$jetzt = gmdate('Y-m-d\TH:i:s\Z');
$beendet = [];
with_lock('wartung', function () use (&$beendet, $jetzt) {
    $w = store_read('wartung');
    if (is_array($w) && !empty($w['active'])) {
        $w['active'] = false; $w['since'] = null; $w['by'] = 'Notfallwerkzeug'; $w['changed'] = $jetzt;
        store_write('wartung', $w);
        $beendet[] = 'angebot.kunden';
    }
});
with_lock('module', function () use (&$beendet, $jetzt) {
    $d = store_read('module') ?? [];
    $aktiv = array_keys(array_filter(is_array($d['wartung'] ?? null) ? $d['wartung'] : [], function ($w) { return !empty($w['active']); }));
    $v = is_array($d['verlauf'] ?? null) ? $d['verlauf'] : [];
    foreach (array_merge($beendet, $aktiv) as $b) array_unshift($v, ['t' => $jetzt, 'wer' => 'Notfallwerkzeug (Server)', 'bereich' => $b, 'alt' => 'wartung', 'neu' => 'normal', 'grund' => 'Notfall: alle Wartungen beendet', 'ab' => null, 'bis' => null]);
    $d['wartung'] = [];
    $d['verlauf'] = array_slice($v, 0, 100);
    store_write('module', $d);
    $beendet = array_merge($beendet, $aktiv);
});
echo $beendet ? 'Wartung beendet: ' . implode(', ', $beendet) . '.' : 'Keine Wartung aktiv.';
