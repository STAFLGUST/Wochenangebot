<?php
/* Notfallmodus beenden (Server-Werkzeug zu deploy/notfall-aus.sh) – gleicher Ablauf wie notfall_ende() in
   app/api/lib/notfall.php, aber ohne Anmeldung: Zustand „aus“, Verlauf ergänzen, gesicherte Sicherheits- und
   Firewall-Einstellungen zurückschreiben (außer NOTFALL_AUS=streng), Vermerk im Protokoll und im Wartungsverlauf.
   Auch mit SQLite. In Tests: DATA_DIR=<Testdaten> php deploy/notfall-aus.php */
$DATA = getenv('DATA_DIR') ?: '/var/www/html/data';
require is_file(__DIR__ . '/../app/api/storage.php') ? __DIR__ . '/../app/api/storage.php' : '/var/www/html/api/storage.php';
$jetzt = gmdate('Y-m-d\TH:i:s\Z');
$streng = getenv('NOTFALL_AUS') === 'streng';
$r = with_lock('sicherheit-notfall', function () use ($jetzt, $streng) {
    $d = store_read('sicherheit-notfall') ?? [];
    if (empty($d['aktiv'])) return null;
    $text = 'unverändert (streng)';
    if (!$streng && is_array($d['vorher'] ?? null) && !empty($d['optionen']['firewall'])) {
        store_write('sicherheit', (array)($d['vorher']['sicherheit'] ?? []));
        store_write('firewall', (array)($d['vorher']['firewall'] ?? []));
        $text = 'wie vor dem Notfall wiederhergestellt';
    } elseif (empty($d['optionen']['firewall'])) $text = 'nicht geändert (Firewall war abgewählt)';
    $v = is_array($d['verlauf'] ?? null) ? $d['verlauf'] : [];
    array_unshift($v, ['seit' => $d['seit'] ?? null, 'bis' => $jetzt, 'von' => (string)($d['vonName'] ?? ''), 'beendetVon' => 'Notfallwerkzeug (Server)',
                       'grund' => (string)($d['grund'] ?? ''), 'notiz' => '', 'wirkung' => (array)($d['wirkung'] ?? []), 'einstellungen' => $text]);
    store_write('sicherheit-notfall', ['aktiv' => false, 'verlauf' => array_slice($v, 0, 20), 'geaendert' => $jetzt]);
    return $text;
});
if ($r === null) { echo 'Der Notfallmodus ist nicht aktiv.'; exit(0); }
with_lock('module', function () use ($jetzt) {
    $d = store_read('module') ?? [];
    $v = is_array($d['verlauf'] ?? null) ? $d['verlauf'] : [];
    array_unshift($v, ['t' => $jetzt, 'wer' => 'Notfallwerkzeug (Server)', 'bereich' => 'alle', 'alt' => 'wartung', 'neu' => 'normal', 'grund' => 'Notfallmodus beendet (Server)', 'ab' => null, 'bis' => null]);
    $d['verlauf'] = array_slice($v, 0, 100);
    if (!is_array($d['wartung'] ?? null)) $d['wartung'] = [];
    store_write('module', $d);
});
$monat = gmdate('Y-m');
with_lock('protokoll', function () use ($jetzt, $monat, $r) {
    $log = store_read('protokoll/' . $monat) ?? [];
    $log[] = ['t' => $jetzt, 'u' => 'system', 'n' => 'Notfallwerkzeug (Server)', 'r' => '', 'ip' => '', 'a' => 'notfall', 's' => 'Notfallmodus auf dem Server beendet',
              'd' => [['k' => 'notfall|fw', 'code' => '', 'name' => 'Notfallmodus', 'f' => 'Einstellungen', 'from' => '', 'to' => $r]]];
    store_write('protokoll/' . $monat, $log);
});
echo 'Notfallmodus beendet. Sicherheits- und Firewall-Einstellungen: ' . $r . '.';
