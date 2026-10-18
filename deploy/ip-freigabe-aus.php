<?php
/* Offline emergency tool, also supports SQLite. */
$DATA = getenv('DATA_DIR') ?: '/var/www/html/data';
require is_file(__DIR__ . '/../app/api/storage.php') ? __DIR__ . '/../app/api/storage.php' : '/var/www/html/api/storage.php';
with_lock('sicherheit', function () {
    $s = store_read('sicherheit') ?? [];
    $s['ipEnabled'] = false;
    $s['geoEnabled'] = false;
    store_write('sicherheit', $s);
});
echo "IP-Freigabe und Ländersperre ausgeschaltet.";
