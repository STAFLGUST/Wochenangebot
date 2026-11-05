<?php
/* Notfallmodus beenden (Server-Werkzeug zu deploy/notfall-aus.sh) – ohne Anmeldung, aber mit genau derselben Funktion wie die
   Oberfläche: notfall_ende() in app/api/lib/notfall.php (Zustand „aus“, Verlauf ergänzen und den Rückweg feldbezogen gehen –
   nur Felder der Vorlage „Notfall“, die noch den vom Notfall geschriebenen Wert haben; außer NOTFALL_AUS=streng). Dazu hier der
   Vermerk im Protokoll und im Wartungsverlauf. Auch mit SQLite. In Tests: DATA_DIR=<Testdaten> php deploy/notfall-aus.php */
$DATA = getenv('DATA_DIR') ?: '/var/www/html/data';
require is_file(__DIR__ . '/../app/api/storage.php') ? __DIR__ . '/../app/api/storage.php' : '/var/www/html/api/storage.php';
/* Nichts zu tun, wenn gar kein Notfall vermerkt ist (dann auch keine Funktionen laden) */
if (!is_array(store_read('sicherheit-notfall') ?? null)) { echo 'Der Notfallmodus ist nicht aktiv.'; exit(0); }
/* Funktionen des Notfallmodus laden (nur Konstanten und Funktionen; keine Anfrage, keine Anmeldung) – wie
   deploy/anmeldung/app-abfrage.php die Sicherheitseinstellungen über lib/sicherheit.php liest: eine Quelle statt
   einer zweiten Umsetzung desselben Ablaufs. */
if (!defined('WA_API')) define('WA_API', true);
if (!function_exists('now')) { function now(): string { return gmdate('Y-m-d\TH:i:s\Z'); } }   // sonst aus app/api/lib/kern.php
$LIB = is_file(__DIR__ . '/../app/api/lib/notfall.php') ? __DIR__ . '/../app/api/lib/' : '/var/www/html/api/lib/';
require $LIB . 'firewall.php';   // FW_VORLAGEN und FW_NICHT_UEBERTRAGEN: welche Felder der Rückweg anfassen darf
require $LIB . 'notfall.php';
$jetzt = gmdate('Y-m-d\TH:i:s\Z');
$streng = getenv('NOTFALL_AUS') === 'streng';
$e = notfall_ende('Notfallwerkzeug (Server)', !$streng);
if ($e === null) { echo 'Der Notfallmodus ist nicht aktiv.'; exit(0); }
$r = (string)$e['einstellungen'];
$jetzt = (string)($e['eintrag']['bis'] ?? $jetzt);
with_lock('module', function () use ($jetzt) {
    $d = store_read('module') ?? [];
    $v = is_array($d['verlauf'] ?? null) ? $d['verlauf'] : [];
    array_unshift($v, ['t' => $jetzt, 'wer' => 'Notfallwerkzeug (Server)', 'bereich' => 'alle', 'alt' => 'wartung', 'neu' => 'normal', 'grund' => 'Notfallmodus beendet (Server)', 'ab' => null, 'bis' => null]);
    $d['verlauf'] = array_slice($v, 0, 100);
    if (!is_array($d['wartung'] ?? null)) $d['wartung'] = [];
    store_write('module', $d);
});
$monat = gmdate('Y-m');
$felder = (array)($e['felder'] ?? []);   // zurückgenommene Felder einzeln ins Protokoll (wie in der Oberfläche)
with_lock('protokoll', function () use ($jetzt, $monat, $r, $felder) {
    $log = store_read('protokoll/' . $monat) ?? [];
    $log[] = ['t' => $jetzt, 'u' => 'system', 'n' => 'Notfallwerkzeug (Server)', 'r' => '', 'ip' => '', 'a' => 'notfall', 's' => 'Notfallmodus auf dem Server beendet',
              'd' => array_merge([['k' => 'notfall|fw', 'code' => '', 'name' => 'Notfallmodus', 'f' => 'Einstellungen', 'from' => '', 'to' => $r]], $felder)];
    store_write('protokoll/' . $monat, $log);
});
echo 'Notfallmodus beendet. Sicherheits- und Firewall-Einstellungen: ' . $r . '.';
