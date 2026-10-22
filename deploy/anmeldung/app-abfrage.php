<?php
/* Wird von deploy/anmeldung/konten.sh im App-Container ausgeführt (über die Standardeingabe, nicht über das Web).
 *   php -- postfach        → Zugangsdaten des Postfachs der Anwendung als JSON (Eingabebereich oder .env), nur für die
 *                            Einrichtung des Mailversands von Keycloak; das Passwort geht nur in die Datei des Keycloak-Tresors
 *   php -- nutzer <name>   → „aktiv“, „gesperrt“ oder „fehlt“: gibt es das Mitarbeiterkonto im Eingabebereich?
 * Ausgabe nur auf die Standardausgabe; nichts wird geschrieben.
 */
declare(strict_types=1);
$APP = rtrim(getenv('WA_APP_DIR') ?: '/var/www/html', '/');
$DATA = getenv('DATA_DIR') ?: $APP . '/data';
$CFG = require $APP . '/api/config.php';
require $APP . '/api/storage.php';
require $APP . '/api/mail.php';

$was = (string)($argv[1] ?? '');
if ($was === 'postfach') {
    $c = mail_cfg();
    if ($c === null || ($c['source'] ?? '') === 'test') { fwrite(STDERR, "Im Eingabebereich ist kein E-Mail-Versand eingerichtet (Verwaltung → E-Mail).\n"); exit(2); }
    if (!empty($c['passError'])) { fwrite(STDERR, "Das gespeicherte Postfach-Passwort lässt sich nicht entschlüsseln – im Eingabebereich neu eingeben.\n"); exit(3); }
    echo json_encode(['host' => $c['host'], 'port' => (int)$c['port'], 'secure' => $c['secure'], 'user' => $c['user'], 'pass' => $c['pass'],
                      'from' => $c['from'], 'fromName' => $c['fromName'], 'replyTo' => $c['replyTo'], 'quelle' => $c['source']],
                     JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), "\n";
    exit(0);
}
if ($was === 'nutzer') {
    $name = strtolower((string)($argv[2] ?? ''));
    $data = store_read('nutzer');
    foreach ((is_array($data) ? ($data['users'] ?? []) : []) as $u) {
        if (strcasecmp((string)($u['username'] ?? ''), $name) === 0) { echo !empty($u['active']) ? "aktiv\n" : "gesperrt\n"; exit(0); }
    }
    echo "fehlt\n";
    exit(0);
}
fwrite(STDERR, "Aufruf: postfach | nutzer <name>\n");
exit(1);
