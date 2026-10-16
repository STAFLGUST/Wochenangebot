<?php
/* Wird von ip-freigabe-aus.sh im App-Container ausgeführt (nicht über das Web erreichbar). */
$guard = "<?php http_response_code(404); exit; ?>\n";
$file = (getenv('DATA_DIR') ?: '/var/www/html/data') . '/sicherheit.php';
if (!is_file($file)) { echo "Keine Sicherheitseinstellungen vorhanden – IP-Freigabe ist aus."; exit(0); }
$raw = (string)file_get_contents($file);
if (strncmp($raw, $guard, strlen($guard)) === 0) $raw = substr($raw, strlen($guard));
$s = json_decode($raw, true) ?: [];
$s['ipEnabled'] = false;
$tmp = $file . '.' . bin2hex(random_bytes(4)) . '.tmp';
file_put_contents($tmp, $guard . json_encode($s, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), LOCK_EX);
@chown($tmp, 33); @chgrp($tmp, 33);
rename($tmp, $file);
echo "IP-Freigabe ausgeschaltet – der Eingabebereich ist wieder von überall erreichbar.";
