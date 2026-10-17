<?php
/* Prüft eine entpackte Datensicherung (Ersatz für sicherung-pruefen.py, falls kein Python vorhanden ist):
   jede Datendatei muss gültiges JSON enthalten. Gibt die Anzahl fehlerhafter Dateien aus. */
$guard = "<?php http_response_code(404); exit; ?>\n";
$bad = 0;
$it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($argv[1] ?? '.', FilesystemIterator::SKIP_DOTS));
foreach ($it as $f) {
    $p = (string)$f;
    if (substr($p, -4) !== '.php' || basename($p) === 'index.php') continue;
    $t = (string)file_get_contents($p);
    if (strncmp($t, $guard, strlen($guard)) === 0) $t = substr($t, strlen($guard));
    json_decode($t);
    if (json_last_error() !== JSON_ERROR_NONE) $bad++;
}
echo $bad;
