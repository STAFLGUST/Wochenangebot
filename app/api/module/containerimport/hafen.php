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
   Zuschnitt: Hamburg ist die erste Quelle (ci_hafen_hh_…: Adresse, Lesen, Abrufen, Betrifft). Frist und Sperrablauf sind
   davon unabhängig; Dokument und Sicht tragen heute genau eine Quelle. Das Dokument ist ein Zwischenspeicher und darf mit
   einer zweiten Quelle neu geschnitten werden – ci_hafen_meldungen liest deshalb nur Einträge, die es kennt. */
if (!defined('WA_API')) { http_response_code(404); exit; }

const CI_HAFEN_DOKUMENT = 'containerimport-hafenmeldungen';
const CI_HAFEN_HH_URL = 'https://www.hafen-hamburg.de/en/all-vessels/expected-vessels/';
const CI_HAFEN_FRIST = 2 * 3600;        // Sekunden zwischen zwei Abrufen
const CI_HAFEN_FRIST_FEHLER = 15 * 60;  // nach einem Fehlschlag
const CI_HAFEN_MAX = 200;               // gelesene Einträge höchstens
const CI_HAFEN_MAX_BYTE = 2 * 1024 * 1024;
const CI_HAFEN_ZEITLIMIT = 20;          // Sekunden für das Lesen der Antwort
const CI_HAFEN_WARTEN = 12;             // Sekunden je Schritt beim Verbinden und für die Kopfzeilen – der Test mit hängender Gegenstelle bleibt darunter
const CI_HAFEN_VERSUCH = 120;           // so lange gilt ein begonnener Abruf als laufend; danach ist er abgebrochen (Neustart mitten im Abruf)
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

/* Die Liste abrufen: [Einträge, Fehlertext]. Keine Weiterleitungen, höchstens 2 MB. Das Zeitlimit des Stroms gilt nur je
   Schritt – eine tröpfelnde Gegenstelle hielte das Lesen sonst beliebig lange offen; jeder Leseschritt bekommt deshalb nur
   die Zeit, die vom Zeitlimit noch bleibt (Verbinden und Kopfzeilen begrenzt allein CI_HAFEN_WARTEN je Schritt).
   Vollständig ist die Antwort mit der angekündigten Länge – eine abgeschnittene wäre sonst still der neue Stand; ohne
   angekündigte Länge mit dem Ende der Verbindung. */
function ci_hafen_hh_abrufen(): array
{
    $ctx = stream_context_create(['http' => ['method' => 'GET', 'header' => "Accept: text/html\r\nAccept-Language: en", 'timeout' => CI_HAFEN_WARTEN, 'ignore_errors' => true,
        'follow_location' => 0, 'max_redirects' => 0, 'user_agent' => 'STAFL-Plattform (Standard-Fleisch, Container-Import)']]);
    $http_response_header = [];
    $fh = @fopen(getenv('WA_HAFEN_HH_URL') ?: CI_HAFEN_HH_URL, 'r', false, $ctx);   // WA_HAFEN_HH_URL nur in den Tests
    $status = preg_match('#^HTTP/\S+\s+(\d{3})#', (string)($http_response_header[0] ?? ''), $m) ? (int)$m[1] : 0;
    if (!$fh || $status !== 200) {
        if ($fh) fclose($fh);
        return [[], $status === 0 ? 'Hafen Hamburg ist gerade nicht erreichbar.' : 'Hafen Hamburg antwortet mit einem Fehler (' . $status . ').'];
    }
    $kopf = implode("\n", $http_response_header);
    $laenge = !preg_match('/^Transfer-Encoding:/mi', $kopf) && preg_match('/^Content-Length:\s*(\d+)\s*$/mi', $kopf, $m) ? (int)$m[1] : null;   // stückweise Antworten entpackt PHP – dort zählt das Ende der Verbindung
    $ende = microtime(true) + CI_HAFEN_ZEITLIMIT;
    $ziel = min($laenge ?? CI_HAFEN_MAX_BYTE, CI_HAFEN_MAX_BYTE);
    $roh = '';
    while (!feof($fh) && strlen($roh) < $ziel && ($rest = $ende - microtime(true)) > 0) {
        stream_set_timeout($fh, (int)ceil($rest));
        $teil = fread($fh, 65536);
        if ($teil === false || stream_get_meta_data($fh)['timed_out']) break;
        $roh .= $teil;
    }
    $ganz = strlen($roh) >= $ziel || ($laenge === null && feof($fh));
    fclose($fh);
    if (!$ganz) return [[], 'Die Antwort von Hafen Hamburg kam nicht vollständig an.'];
    $liste = ci_hafen_hh_lesen($roh);
    return [$liste, $liste ? '' : 'Die Liste von Hafen Hamburg ließ sich nicht lesen – vermutlich hat die Seite ihren Aufbau geändert.'];
}

/* Gespeicherte Meldungen: ['abgerufen' => Zeit des letzten beendeten Abrufs|'', 'gelesen' => Zeit des letzten gelungenen|'',
   'fehler' => Text|'', 'versuch' => Beginn eines laufenden Abrufs|'', 'schiffe' => Einträge des letzten gelungenen Abrufs].
   Die einzige Lesestelle: Einträge, die nicht
   aussehen wie von ci_hafen_hh_lesen geschrieben (vier Texte), fallen weg – ein später anders geschnittenes Dokument darf
   nach einem Rückfall auf diese Version nicht den Start des Moduls kosten. */
function ci_hafen_meldungen(): array
{
    $d = store_read(CI_HAFEN_DOKUMENT);
    $eintrag = fn($x) => is_array($x) && is_string($x['schiff'] ?? null) && is_string($x['ankunft'] ?? null)
        && is_string($x['liegeplatz'] ?? null) && is_string($x['terminal'] ?? null);
    return ['abgerufen' => (string)($d['abgerufen'] ?? ''), 'gelesen' => (string)($d['gelesen'] ?? ''), 'fehler' => (string)($d['fehler'] ?? ''),
        'versuch' => (string)($d['versuch'] ?? ''), 'schiffe' => array_values(array_filter(is_array($d['schiffe'] ?? null) ? $d['schiffe'] : [], $eintrag))];
}

/* Felder des Dokuments ändern, der Rest bleibt stehen (unter Sperre gelesen und geschrieben) */
function ci_hafen_ablegen(array $neu): void
{
    with_lock(CI_HAFEN_DOKUMENT, fn() => store_write(CI_HAFEN_DOKUMENT, $neu + ['updatedAt' => now()] + ci_hafen_meldungen()));
}

/* Gehört die Hamburger Liste zu diesem Container? Nur mit Schiffsname und Zielhafen Hamburg: Ein Schiff läuft meist mehrere
   Häfen an – ein Container nach Rotterdam bekäme sonst eine Hamburger Ankunft gezeigt. */
function ci_hafen_hh_betrifft(array $s): bool
{
    return $s['schiff'] !== '' && mb_stripos($s['zielhafen'], 'hamburg') !== false;
}

/* Braucht gerade ein Container die Liste? Aktiv, noch nicht angekommen, und die Liste betrifft ihn. */
function ci_hafen_noetig(array $sendungen): bool
{
    foreach ($sendungen as $s) {
        if ($s['aktiv'] && $s['stand'] !== 'angekommen' && ci_hafen_hh_betrifft($s)) return true;
    }
    return false;
}

/* Sekunden seit einem Zeitstempel aus now(); '' oder Unlesbares zählt als sehr lange her */
function ci_hafen_alter(string $t): int
{
    $s = $t === '' ? false : strtotime($t);
    return $s === false ? PHP_INT_MAX : time() - $s;
}

/* Liste auffrischen, wenn sie gebraucht wird und die Frist um ist. Gibt zurück, ob abgerufen wurde.
   Die Sperre gilt nur dem Dokument, nie dem Abruf: Der kann bis zum Zeitlimit hängen, und im SQLite-Betrieb hielte die Sperre
   so lange jedes Speichern im Bereich auf. Deshalb drei Schritte – unter Sperre prüfen und den Versuch vormerken (wer
   gleichzeitig kommt, ruft nicht auch ab), ohne Sperre abrufen, unter Sperre das Ergebnis ablegen. Der Versuch steht in
   einem eigenen Feld: Bricht der Prozess mitten im Abruf ab, gilt er nach CI_HAFEN_VERSUCH als gescheitert und der nächste
   Aufruf ruft ab – die Frist zählt nur ab einem beendeten Abruf. */
function ci_hafen_auffrischen(array $sendungen): bool
{
    if (!ci_hafen_noetig($sendungen)) return false;
    $faellig = with_lock(CI_HAFEN_DOKUMENT, function () {
        $alt = ci_hafen_meldungen();
        if (ci_hafen_alter($alt['versuch']) < CI_HAFEN_VERSUCH) return false;   // ein anderer Aufruf ruft gerade ab
        if (ci_hafen_alter($alt['abgerufen']) < ($alt['fehler'] !== '' ? CI_HAFEN_FRIST_FEHLER : CI_HAFEN_FRIST)) return false;
        ci_hafen_ablegen(['versuch' => now()]);
        return true;
    });
    if (!$faellig) return false;
    [$liste, $fehler] = ci_hafen_hh_abrufen();
    $neu = ['abgerufen' => now(), 'fehler' => $fehler, 'versuch' => ''];
    if ($fehler === '') $neu += ['gelesen' => $neu['abgerufen'], 'schiffe' => $liste];   // bei einem Fehlschlag bleibt der letzte lesbare Stand mit seiner Zeit
    ci_hafen_ablegen($neu);
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
        $nach[ci_schiff_schluessel($x['schiff'])] ??= $x;   // steht ein Schiff zweimal in der Liste, zählt der erste nicht verfallene Eintrag (die Liste ist nach Ankunft geordnet)
    }
    $meldungen = [];
    foreach ($sendungen as $s) {
        $x = ci_hafen_hh_betrifft($s) ? ($nach[ci_schiff_schluessel($s['schiff'])] ?? null) : null;
        if ($x) $meldungen[$s['id']] = $x;
    }
    return ['abgerufen' => $m['abgerufen'], 'gelesen' => $m['gelesen'], 'fehler' => $m['fehler'], 'anzahl' => count($m['schiffe']), 'meldungen' => (object)$meldungen];
}
