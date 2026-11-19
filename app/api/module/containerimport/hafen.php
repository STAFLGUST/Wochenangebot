<?php
declare(strict_types=1);
/* STAFL-Plattform · Modul Container-Import – Tracking, zweite Stufe: bestätigte Ankunft in Hamburg aus der öffentlichen
   Liste „Expected vessels“ von Hafen Hamburg (Quelle dort: HVCC, täglich nach den Fahrplänen der Terminals). Zustimmung des
   Inhabers 19.11.2026. Der Server ruft die Seite ohne Anmeldung ab, liest Schiff, Ankunft, Liegeplatz und Terminal und stellt
   sie den Containern mit Zielhafen Hamburg über den Schiffsnamen zur Seite.
   Sparsam: höchstens alle zwei Stunden (nach einem Fehlschlag frühestens nach 15 Minuten) und nur, wenn ein Container mit
   Schiffsname und Zielhafen Hamburg noch nicht angekommen ist. Gelesen wird nur die erste Seite der Liste (die nächsten
   24 Ankünfte – ein Schiff erscheint also erst kurz vor der Ankunft). Hinaus geht nichts von uns – keine Containernummer,
   kein Schiffsname.
   Abgerufenes steht nie in den Feldern des Containers (tracking.php), sondern mit Abrufzeit im Dokument
   containerimport-hafenmeldungen und wird beim Lesen dazugestellt (ci_hafen_sicht). Es ist ein Hinweis: Stand und geplante
   Ankunft ändert weiter nur ein Mensch. Ändert die Seite ihren Aufbau, liest ci_hafen_hh_lesen nichts mehr – die Oberfläche
   meldet das, sonst passiert nichts.
   Zuschnitt: Hamburg ist die erste Quelle (ci_hafen_hh_…: Adresse, Lesen, Abrufen). Zwischenspeicher, Frist, Zuordnung und
   Sicht sind davon unabhängig; das Dokument ist ein Zwischenspeicher und darf mit einer zweiten Quelle neu geschnitten werden. */
if (!defined('WA_API')) { http_response_code(404); exit; }

const CI_HAFEN_DOKUMENT = 'containerimport-hafenmeldungen';
const CI_HAFEN_HH_URL = 'https://www.hafen-hamburg.de/en/all-vessels/expected-vessels/';
const CI_HAFEN_FRIST = 2 * 3600;        // Sekunden zwischen zwei Abrufen
const CI_HAFEN_FRIST_FEHLER = 15 * 60;  // nach einem Fehlschlag
const CI_HAFEN_MAX = 200;               // gelesene Einträge höchstens
const CI_HAFEN_ZEIT = 20;               // Sekunden für den ganzen Abruf
const CI_HAFEN_NACHLAUF = 12 * 3600;    // so lange nach der gemeldeten Ankunft gilt eine Meldung noch

/* Schiffsname für den Vergleich: nur Buchstaben und Ziffern, groß – „MSC San-Francisco“ = „msc san francisco“ */
function ci_schiff_schluessel(string $name): string
{
    return (string)preg_replace('/[^A-Z0-9]+/u', '', mb_strtoupper($name));
}

/* Einträge aus dem HTML der Liste: je Schiff eine Überschrift „November 19, 2026, 3:00 pm | Liegeplatz, Terminal“ und
   darunter der Name. Zeiten sind Ortszeit Hamburg und werden mit Zeitzone abgelegt (2026-11-19T15:00:00+01:00). Ein „-“ heißt
   keine Angabe. Unlesbares wird übersprungen – auch ein Eintrag mit ungültigen Zeichen; das Muster selbst arbeitet auf Bytes,
   damit ein einzelnes falsches Byte irgendwo auf der Seite nicht die ganze Liste unlesbar macht. Steuerzeichen fallen weg. */
function ci_hafen_hh_lesen(string $html): array
{
    $text = fn(string $t) => trim(preg_replace('/[\s\p{C}]+/u', ' ', html_entity_decode($t, ENT_QUOTES | ENT_HTML5, 'UTF-8')) ?? '');
    $aus = [];
    preg_match_all('#<h3>([^<|]+)\|([^<]*)</h3>\s*<h2>([^<]+)</h2>#', $html, $treffer, PREG_SET_ORDER);
    foreach (array_slice($treffer, 0, CI_HAFEN_MAX) as [, $zeit, $ort, $name]) {
        $wann = DateTime::createFromFormat('!F j, Y, g:i a', $text($zeit), new DateTimeZone('Europe/Berlin'));
        $name = mb_substr($text($name), 0, 80);
        if (!$wann || ci_schiff_schluessel($name) === '') continue;
        $teile = array_map(fn($t) => $t === '-' ? '' : mb_substr($t, 0, 60), array_map('trim', explode(',', $text($ort), 2))) + ['', ''];
        $aus[] = ['schiff' => $name, 'ankunft' => $wann->format(DATE_ATOM), 'liegeplatz' => $teile[0], 'terminal' => $teile[1]];
    }
    return $aus;
}

/* Die Liste abrufen: [Einträge, Fehlertext]. Keine Weiterleitungen, höchstens 2 MB, und eine Frist für den ganzen Abruf
   (das Zeitlimit des Stroms gilt nur je Leseschritt – eine tröpfelnde Gegenstelle hielte ihn sonst beliebig lange offen). */
function ci_hafen_hh_abrufen(): array
{
    $ende = microtime(true) + CI_HAFEN_ZEIT;
    $ctx = stream_context_create(['http' => ['method' => 'GET', 'header' => "Accept: text/html\r\nAccept-Language: en", 'timeout' => 12, 'ignore_errors' => true,
        'follow_location' => 0, 'max_redirects' => 0, 'user_agent' => 'STAFL-Plattform (Standard-Fleisch, Container-Import)']]);
    $http_response_header = [];
    $fh = @fopen(getenv('WA_HAFEN_HH_URL') ?: CI_HAFEN_HH_URL, 'r', false, $ctx);   // WA_HAFEN_HH_URL nur in den Tests
    $status = preg_match('#^HTTP/\S+\s+(\d{3})#', (string)($http_response_header[0] ?? ''), $m) ? (int)$m[1] : 0;
    if (!$fh || $status !== 200) return [[], $status === 0 ? 'Hafen Hamburg ist gerade nicht erreichbar.' : 'Hafen Hamburg antwortet mit einem Fehler (' . $status . ').'];
    $roh = '';
    while (!feof($fh) && strlen($roh) < 2 * 1024 * 1024 && microtime(true) < $ende) {
        $teil = fread($fh, 65536);
        if ($teil === false || stream_get_meta_data($fh)['timed_out']) break;
        $roh .= $teil;
    }
    $ganz = feof($fh) || strlen($roh) >= 2 * 1024 * 1024;
    fclose($fh);
    if (!$ganz) return [[], 'Hafen Hamburg antwortet zu langsam.'];
    $liste = ci_hafen_hh_lesen($roh);
    return [$liste, $liste ? '' : 'Die Liste von Hafen Hamburg ließ sich nicht lesen – vermutlich hat die Seite ihren Aufbau geändert.'];
}

/* Gespeicherte Meldungen: ['abgerufen' => Zeit des letzten Versuchs|'', 'gelesen' => Zeit des letzten gelungenen Abrufs|'',
   'fehler' => Text|'', 'schiffe' => Einträge des letzten gelungenen Abrufs] */
function ci_hafen_meldungen(): array
{
    $d = store_read(CI_HAFEN_DOKUMENT);
    return ['abgerufen' => (string)($d['abgerufen'] ?? ''), 'gelesen' => (string)($d['gelesen'] ?? ''), 'fehler' => (string)($d['fehler'] ?? ''),
        'schiffe' => is_array($d['schiffe'] ?? null) ? $d['schiffe'] : []];
}

/* Gehört die Hamburger Liste zu diesem Container? Nur mit Schiffsname und Zielhafen Hamburg: Ein Schiff läuft meist mehrere
   Häfen an – ein Container nach Rotterdam bekäme sonst eine Hamburger Ankunft gezeigt. */
function ci_hafen_betrifft(array $s): bool
{
    return $s['schiff'] !== '' && mb_stripos($s['zielhafen'], 'hamburg') !== false;
}

/* Braucht gerade ein Container die Liste? Aktiv, noch nicht angekommen, und die Liste betrifft ihn. */
function ci_hafen_noetig(array $sendungen): bool
{
    foreach ($sendungen as $s) {
        if ($s['aktiv'] && $s['stand'] !== 'angekommen' && ci_hafen_betrifft($s)) return true;
    }
    return false;
}

/* Liste auffrischen, wenn sie gebraucht wird und die Frist um ist. Gibt zurück, ob abgerufen wurde.
   Die Sperre gilt nur dem Dokument, nie dem Abruf: Der kann bis zum Zeitlimit hängen, und im SQLite-Betrieb hielte die Sperre
   so lange jedes Speichern im Bereich auf. Deshalb drei Schritte – unter Sperre prüfen und den Versuch vormerken (wer
   gleichzeitig kommt, ruft nicht auch ab), ohne Sperre abrufen, unter Sperre das Ergebnis ablegen. Bei einem Fehlschlag
   bleiben die zuletzt gelesenen Einträge mit ihrer Zeit stehen. */
function ci_hafen_auffrischen(array $sendungen): bool
{
    if (!ci_hafen_noetig($sendungen)) return false;
    $faellig = with_lock(CI_HAFEN_DOKUMENT, function () {
        $alt = ci_hafen_meldungen();
        $frist = $alt['fehler'] !== '' ? CI_HAFEN_FRIST_FEHLER : CI_HAFEN_FRIST;
        if ($alt['abgerufen'] !== '' && time() - (int)strtotime($alt['abgerufen']) < $frist) return false;
        store_write(CI_HAFEN_DOKUMENT, ['abgerufen' => now(), 'updatedAt' => now()] + $alt);
        return true;
    });
    if (!$faellig) return false;
    [$liste, $fehler] = ci_hafen_hh_abrufen();
    $jetzt = now();
    with_lock(CI_HAFEN_DOKUMENT, fn() => store_write(CI_HAFEN_DOKUMENT, ['abgerufen' => $jetzt, 'fehler' => $fehler, 'updatedAt' => $jetzt]
        + ($fehler === '' ? ['gelesen' => $jetzt, 'schiffe' => $liste] : []) + ci_hafen_meldungen()));
    return true;
}

/* Meldungen für die Oberfläche: nur was zu unseren Containern gehört (Kennung des Containers → Schiff, Ankunft, Liegeplatz,
   Terminal), dazu Zeit und Ergebnis des letzten Abrufs. Die fremde Liste selbst wird nicht ausgeliefert. Eine Meldung
   verfällt CI_HAFEN_NACHLAUF nach ihrer Ankunft: Scheitert der Abruf länger oder fragt kein Container mehr, stünde sonst
   eine Wochen alte Ankunft als „wird erwartet“ da. */
function ci_hafen_sicht(array $sendungen): array
{
    $m = ci_hafen_meldungen();
    $nach = [];
    foreach ($m['schiffe'] as $x) {
        if ((int)strtotime($x['ankunft']) < time() - CI_HAFEN_NACHLAUF) continue;
        $nach[ci_schiff_schluessel($x['schiff'])] ??= $x;   // steht ein Schiff zweimal in der Liste, zählt der erste Eintrag (die Liste ist nach Ankunft geordnet)
    }
    $meldungen = [];
    foreach ($sendungen as $s) {
        $x = ci_hafen_betrifft($s) ? ($nach[ci_schiff_schluessel($s['schiff'])] ?? null) : null;
        if ($x) $meldungen[$s['id']] = $x;
    }
    return ['abgerufen' => $m['abgerufen'], 'gelesen' => $m['gelesen'], 'fehler' => $m['fehler'], 'anzahl' => count($m['schiffe']), 'meldungen' => (object)$meldungen];
}
