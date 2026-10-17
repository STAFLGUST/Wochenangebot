<?php
/* Wird von passwort-zuruecksetzen.sh im App-Container ausgeführt (nicht über das Web erreichbar). */
$guard = "<?php http_response_code(404); exit; ?>\n";
$dir = getenv('DATA_DIR') ?: '/var/www/html/data';
$file = $dir . '/nutzer.php';
[$name, $pw] = [strtolower((string)($argv[1] ?? '')), (string)($argv[2] ?? '')];
if (strlen($pw) < 10) { fwrite(STDERR, "Passwort zu kurz.\n"); exit(1); }
$neu = in_array('--neu', $argv, true);
if (!preg_match('/^[a-z0-9][a-z0-9._-]{1,31}$/', $name)) { fwrite(STDERR, "Ungültiger Benutzername.\n"); exit(1); }
if (is_file($file)) {
    $raw = (string)file_get_contents($file);
    if (strncmp($raw, $guard, strlen($guard)) === 0) $raw = substr($raw, strlen($guard));
    $data = json_decode($raw, true);
    if (!is_array($data) || !isset($data['users'])) { fwrite(STDERR, "Nutzerdatei ist nicht lesbar – bitte aus der Datensicherung wiederherstellen (siehe LIESMICH).\n"); exit(1); }
} elseif ($neu) {
    $data = ['users' => []];
} else {
    fwrite(STDERR, "Keine Nutzerdatei gefunden. Neuen Administrator anlegen mit:  sh deploy/passwort-zuruecksetzen.sh $name --neu\n"); exit(1);
}
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
$tmp = $file . '.' . bin2hex(random_bytes(4)) . '.tmp';
file_put_contents($tmp, $guard . json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), LOCK_EX);
@chown($tmp, 33); @chgrp($tmp, 33);
rename($tmp, $file);
echo "Passwort für \"$name\" wurde zurückgesetzt, Zwei-Faktor-Anmeldung und Sperre aufgehoben.";
