<?php
declare(strict_types=1);
/* STAFL-Plattform · Modul Container-Import – Tracking, zweite Stufe: bestätigte Ankunft in Hamburg aus der öffentlichen
   Liste „Expected vessels“ von Hafen Hamburg (Quelle dort: HVCC, täglich nach den Fahrplänen der Terminals; Blick rund zwei
   Tage voraus). Zustimmung des Inhabers 19.11.2026. Der Server ruft die Seite ohne Anmeldung ab, liest Schiff, Ankunft,
   Liegeplatz und Terminal und stellt sie den Containern über den Schiffsnamen zur Seite.
   Sparsam: höchstens alle zwei Stunden (nach einem Fehlschlag frühestens nach 15 Minuten) und nur, wenn ein Container mit
   Schiffsname und Zielhafen Hamburg noch nicht angekommen ist. Gelesen wird nur die erste Seite der Liste (die nächsten
   24 Ankünfte). Hinaus geht nichts von uns – keine Containernummer, kein Schiffsname.
   Abgerufenes steht nie in den Feldern des Containers (tracking.php), sondern mit Abrufzeit im Dokument
   containerimport-hafenmeldungen und wird beim Lesen dazugestellt (ci_hafen_sicht). Es ist ein Hinweis: Stand und geplante
   Ankunft ändert weiter nur ein Mensch. Ändert die Seite ihren Aufbau, liest ci_hafen_lesen nichts mehr – die Oberfläche
   meldet das, sonst passiert nichts. */
if (!defined('WA_API')) { http_response_code(404); exit; }

const CI_HAFEN_URL = 'https://www.hafen-hamburg.de/en/all-vessels/expected-vessels/';
const CI_HAFEN_FRIST = 2 * 3600;        // Sekunden zwischen zwei Abrufen
const CI_HAFEN_FRIST_FEHLER = 15 * 60;  // nach einem Fehlschlag
const CI_HAFEN_MAX = 200;               // gelesene Einträge höchstens

/* Schiffsname für den Vergleich: nur Buchstaben und Ziffern, groß – „MSC San-Francisco“ = „msc san francisco“ */
function ci_schiff_schluessel(string $name): string
{
    return (string)preg_replace('/[^A-Z0-9]+/u', '', mb_strtoupper($name));
}

/* Einträge aus dem HTML der Liste: je Schiff eine Überschrift „November 19, 2026, 3:00 pm | Liegeplatz, Terminal“ und
   darunter der Name. Zeiten sind Ortszeit Hamburg. Ein „-“ heißt keine Angabe. Unlesbares wird übersprungen. */
function ci_hafen_lesen(string $html): array
{
    $text = fn(string $t) => trim(preg_replace('/\s+/u', ' ', html_entity_decode($t, ENT_QUOTES | ENT_HTML5, 'UTF-8')) ?? '');
    $aus = [];
    preg_match_all('#<h3>([^<|]+)\|([^<]*)</h3>\s*<h2>([^<]+)</h2>#u', $html, $treffer, PREG_SET_ORDER);
    foreach (array_slice($treffer, 0, CI_HAFEN_MAX) as [, $zeit, $ort, $name]) {
        $wann = DateTime::createFromFormat('!F j, Y, g:i a', $text($zeit), new DateTimeZone('Europe/Berlin'));
        $name = mb_substr($text($name), 0, 80);
        if (!$wann || ci_schiff_schluessel($name) === '') continue;
        $teile = array_map(fn($t) => $t === '-' ? '' : mb_substr($t, 0, 60), array_map('trim', explode(',', $text($ort), 2))) + ['', ''];
        $aus[] = ['schiff' => $name, 'ankunft' => $wann->format('Y-m-d H:i'), 'liegeplatz' => $teile[0], 'terminal' => $teile[1]];
    }
    return $aus;
}

/* Die Liste abrufen: [Einträge, Fehlertext]. Kurzes Zeitlimit, keine Weiterleitungen, höchstens 2 MB. */
function ci_hafen_abrufen(): array
{
    $ctx = stream_context_create(['http' => ['method' => 'GET', 'header' => "Accept: text/html\r\nAccept-Language: en", 'timeout' => 12, 'ignore_errors' => true,
        'follow_location' => 0, 'max_redirects' => 0, 'user_agent' => 'STAFL-Plattform (Standard-Fleisch, Container-Import; Abruf höchstens alle zwei Stunden)']]);
    $http_response_header = [];
    $roh = @file_get_contents(getenv('WA_HAFEN_HH_URL') ?: CI_HAFEN_URL, false, $ctx, 0, 2 * 1024 * 1024);   // WA_HAFEN_HH_URL nur in den Tests
    $status = preg_match('#^HTTP/\S+\s+(\d{3})#', (string)($http_response_header[0] ?? ''), $m) ? (int)$m[1] : 0;
    if ($status !== 200 || !is_string($roh)) return [[], $status === 0 ? 'Hafen Hamburg ist gerade nicht erreichbar.' : 'Hafen Hamburg antwortet mit einem Fehler (' . $status . ').'];
    $liste = ci_hafen_lesen($roh);
    return [$liste, $liste ? '' : 'Die Liste von Hafen Hamburg ließ sich nicht lesen – vermutlich hat die Seite ihren Aufbau geändert.'];
}

/* Gespeicherte Meldungen: ['abgerufen' => Zeit des letzten Versuchs|'', 'gelesen' => Zeit des letzten gelungenen Abrufs|'',
   'fehler' => Text|'', 'schiffe' => Einträge des letzten gelungenen Abrufs] */
function ci_hafen_meldungen(): array
{
    $d = store_read('containerimport-hafenmeldungen');
    return ['abgerufen' => (string)($d['abgerufen'] ?? ''), 'gelesen' => (string)($d['gelesen'] ?? ''), 'fehler' => (string)($d['fehler'] ?? ''),
        'schiffe' => is_array($d['schiffe'] ?? null) ? $d['schiffe'] : []];
}

/* Braucht gerade ein Container die Liste? Aktiv, nicht angekommen, mit Schiffsname und Zielhafen Hamburg. */
function ci_hafen_gefragt(array $sendungen): bool
{
    foreach ($sendungen as $s) {
        if ($s['aktiv'] && $s['stand'] !== 'angekommen' && $s['schiff'] !== '' && mb_stripos($s['zielhafen'], 'hamburg') !== false) return true;
    }
    return false;
}

/* Liste auffrischen, wenn sie gebraucht wird und die Frist um ist. Bei einem Fehlschlag bleiben die zuletzt gelesenen
   Einträge stehen (mit ihrer Zeit). Gibt zurück, ob abgerufen wurde. */
function ci_hafen_auffrischen(array $sendungen): bool
{
    $alt = ci_hafen_meldungen();
    $frist = $alt['fehler'] !== '' ? CI_HAFEN_FRIST_FEHLER : CI_HAFEN_FRIST;
    if (!ci_hafen_gefragt($sendungen) || ($alt['abgerufen'] !== '' && time() - (int)strtotime($alt['abgerufen']) < $frist)) return false;
    [$liste, $fehler] = ci_hafen_abrufen();
    $jetzt = now();
    store_write('containerimport-hafenmeldungen', ['abgerufen' => $jetzt, 'fehler' => $fehler]
        + ($fehler === '' ? ['gelesen' => $jetzt, 'schiffe' => $liste] : ['gelesen' => $alt['gelesen'], 'schiffe' => $alt['schiffe']]) + ['updatedAt' => $jetzt]);
    return true;
}

/* Meldungen für die Oberfläche: nur was zu unseren Containern gehört (Kennung des Containers → Ankunft, Liegeplatz,
   Terminal), dazu Zeit und Ergebnis des letzten Abrufs. Die fremde Liste selbst wird nicht ausgeliefert. */
function ci_hafen_sicht(array $sendungen): array
{
    $m = ci_hafen_meldungen();
    $nach = [];
    foreach ($m['schiffe'] as $x) $nach[ci_schiff_schluessel((string)($x['schiff'] ?? ''))] ??= $x;   // steht ein Schiff zweimal in der Liste, zählt die frühere Ankunft
    $meldungen = [];
    foreach ($sendungen as $s) {
        $x = $s['schiff'] !== '' ? ($nach[ci_schiff_schluessel($s['schiff'])] ?? null) : null;
        if ($x) $meldungen[$s['id']] = ['schiff' => (string)$x['schiff'], 'ankunft' => (string)$x['ankunft'], 'liegeplatz' => (string)$x['liegeplatz'], 'terminal' => (string)$x['terminal']];
    }
    return ['abgerufen' => $m['abgerufen'], 'gelesen' => $m['gelesen'], 'fehler' => $m['fehler'], 'anzahl' => count($m['schiffe']), 'meldungen' => (object)$meldungen];
}
