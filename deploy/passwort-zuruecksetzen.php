<?php
/* Wird von passwort-zuruecksetzen.sh im App-Container ausgeführt (nicht über das Web erreichbar). */
$guard = "<?php http_response_code(404); exit; ?>\n";
$dir = getenv('DATA_DIR') ?: '/var/www/html/data';
$file = $dir . '/nutzer.php';
[$name, $pw] = [strtolower((string)($argv[1] ?? '')), (string)($argv[2] ?? '')];
if (strlen($pw) < 10) { fwrite(STDERR, "Passwort zu kurz.\n"); exit(1); }
if (!is_file($file)) { fwrite(STDERR, "Keine Nutzerdatei gefunden – im Browser /admin/ öffnen (Ersteinrichtung bzw. erste Anmeldung).\n"); exit(1); }
$raw = (string)file_get_contents($file);
if (strncmp($raw, $guard, strlen($guard)) === 0) $raw = substr($raw, strlen($guard));
$data = json_decode($raw, true);
if (!is_array($data) || !isset($data['users'])) { fwrite(STDERR, "Nutzerdatei ist nicht lesbar.\n"); exit(1); }
$found = false;
foreach ($data['users'] as &$u) {
    if ($u['username'] !== $name) continue;
    $u['hash'] = password_hash($pw, PASSWORD_DEFAULT);
    $u['mustChange'] = true;
    $u['active'] = true;
    $u['sv'] = (int)($u['sv'] ?? 0) + 1;
    $u['changed'] = gmdate('Y-m-d\TH:i:s\Z');
    $found = true;
}
unset($u);
if (!$found) {
    fwrite(STDERR, "Nutzer \"$name\" nicht gefunden. Vorhanden: " . implode(', ', array_map(function ($u) { return $u['username'] . ' (' . $u['role'] . ')'; }, $data['users'])) . "\n");
    exit(1);
}
$tmp = $file . '.' . bin2hex(random_bytes(4)) . '.tmp';
file_put_contents($tmp, $guard . json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), LOCK_EX);
@chown($tmp, 33); @chgrp($tmp, 33);
rename($tmp, $file);
echo "Passwort für \"$name\" wurde zurückgesetzt.";
