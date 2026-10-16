<?php
/*
 * Einstellungen für die Wochenangebots-API.
 * Diese Datei wird vom Webserver ausgeführt, nicht ausgeliefert.
 */
return [
    // Firmenname – erscheint im Kopf der Website und auf dem Ausdruck
    'company'        => 'Standard-Fleisch',

    // Ordner für die gespeicherten Daten (muss für PHP beschreibbar sein)
    'data_dir'       => __DIR__ . '/../data',

    // Nach so vielen Stunden ohne Aktivität wird man im Eingabebereich abgemeldet
    'session_hours'  => 8,

    // Anzahl der aufbewahrten früheren Veröffentlichungen
    'keep_versions'  => 60,

    // Anmeldeschutz: nach X Fehlversuchen für Y Minuten sperren
    'max_attempts'   => 5,
    'lock_minutes'   => 10,
];
