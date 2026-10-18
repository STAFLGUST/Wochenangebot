<?php
/* Wird von passwort-zuruecksetzen.sh im App-Container ausgeführt (nicht über das Web erreichbar). */
$DATA = getenv('DATA_DIR') ?: '/var/www/html/data';
require is_file(__DIR__ . '/../app/api/storage.php') ? __DIR__ . '/../app/api/storage.php' : '/var/www/html/api/storage.php';
[$name, $pw] = [strtolower((string)($argv[1] ?? '')), (string)($argv[2] ?? '')];
if (strlen($pw) < 10) { fwrite(STDERR, "Passwort zu kurz.\n"); exit(1); }
$neu = in_array('--neu', $argv, true);
if (!preg_match('/^[a-z0-9][a-z0-9._-]{1,31}$/', $name)) { fwrite(STDERR, "Ungültiger Benutzername.\n"); exit(1); }
with_lock('nutzer', function () use ($name, $pw, $neu) {
$data = store_read('nutzer');
if ($data === null && $neu) $data = ['users' => []];
if (!is_array($data) || !isset($data['users'])) throw new RuntimeException('Nutzerdaten fehlen oder sind beschädigt.');
$found = false;
foreach ($data['users'] as &$u) {
    if ($u['username'] !== $name) continue;
    $u['hash'] = password_hash($pw, PASSWORD_DEFAULT);
    $u['mustChange'] = true;
    $u['active'] = true;
    unset($u['totp'], $u['totpLast'], $u['recovery']);   // Zwei-Faktor neu einrichten
    $u['lockedUntil'] = 0; $u['failCount'] = 0;
    $u['sv'] = (int)($u['sv'] ?? 0) + 1;
    $u['changed'] = gmdate('Y-m-d\TH:i:s\Z');
    $found = true;
}
unset($u);
if (!$found && $neu) {
    $data['users'][] = ['id' => 'u' . bin2hex(random_bytes(6)), 'username' => $name, 'name' => 'Administrator', 'role' => 'admin', 'active' => true,
                        'hash' => password_hash($pw, PASSWORD_DEFAULT), 'mustChange' => true, 'sv' => 1, 'created' => gmdate('Y-m-d\TH:i:s\Z'),
                        'createdBy' => 'Server (passwort-zuruecksetzen.sh)', 'lastLogin' => null];
    $found = true;
}
if (!$found) {
    fwrite(STDERR, "Nutzer \"$name\" nicht gefunden (neu anlegen mit --neu). Vorhanden: " . implode(', ', array_map(function ($u) { return $u['username'] . ' (' . $u['role'] . ')'; }, $data['users'])) . "\n");
    exit(1);
}
store_write('nutzer', $data);
});
echo "Passwort für \"$name\" wurde zurückgesetzt, Zwei-Faktor-Anmeldung und Sperre aufgehoben.";
