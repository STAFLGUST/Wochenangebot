<?php
declare(strict_types=1);
/* Dateiablage der Plattform (neben der Speicherschicht): hochgeladene Dateien eines Moduls (z. B. QM-Dokumente) liegen in
   beiden Speicherarten im Dateisystem unter data/dateien/<bereich>/<xx>/<id>.bin – die SQLite-Datenbank enthält nur
   JSON-Dokumente, die Metadaten (Name, Größe, Prüfsumme, wer, wann) führt das Modul in seinem eigenen Dokument.
   Schutz: data/ liefert der Webserver nie aus (Caddy @private, app/.htaccess); ausgeliefert wird nur über Aktionen mit
   Rechteprüfung (ablage_senden), immer als Download (attachment, nosniff, sandbox). Sicherung: Teil des Datenarchivs
   (deploy/sichern.sh, alles unter data/); unvollständige Uploads (*.tmp) nicht. Die Dateien heißen bewusst nicht *.php:
   Sicherungsprüfung und Datenbank-Umschaltung behandeln nur *.php als JSON-Dokumente.
   Hochladen in Teilen: der API-Einstieg nimmt nur JSON bis 6 MB an – ablage_teil() sammelt Teile (Base64, je höchstens
   ABLAGE_TEIL_MAX Bytes) eines Uploads unter data/dateien/.teile/, prüft beim letzten Teil Größe, SHA-256 und Dateiart
   (Endung und Dateikopf passen zusammen) und legt die Datei ab. Ein Upload gehört dem Nutzer, der ihn begonnen hat.
   Vom Server erzeugte Dateien (z. B. aus einer Vorlage ausgefüllt) legt ablage_ablegen() ab, ablage_kopieren() kopiert eine Datei
   unter neuer Kennung (z. B. in eine neue Version), ablage_lesen() liefert den Inhalt.
   ZIP-Export: ablage_zip_senden() schreibt ein ZIP (Methode „stored“, UTF-8-Namen) direkt in die Antwort – ohne die
   PHP-Erweiterung „zip“ und ohne das ganze Archiv im Speicher zu halten. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const ABLAGE_TEIL_MAX = 3 * 1024 * 1024;        // Bytes je Teil (Base64 ≈ 4 MB, unter der Grenze des API-Einstiegs)
const ABLAGE_DATEI_MAX = 25 * 1024 * 1024;      // Bytes je Datei
const ABLAGE_UPLOAD_STUNDEN = 24;               // unvollständige Uploads werden danach entfernt
const ABLAGE_ZIP_MAX = 3500 * 1024 * 1024;      // ZIP ohne Zip64: unter 4 GB bleiben
/* Erlaubte Dateiarten: Endung → [MIME-Typ, erwarteter Dateikopf] (ole = Office 97–2003/Outlook, zip = Office Open XML/ODF) */
const ABLAGE_ARTEN = [
    'pdf' => ['application/pdf', 'pdf'],
    'doc' => ['application/msword', 'ole'], 'dot' => ['application/msword', 'ole'],
    'docx' => ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'zip'],
    'dotx' => ['application/vnd.openxmlformats-officedocument.wordprocessingml.template', 'zip'],
    'xls' => ['application/vnd.ms-excel', 'ole'], 'xlt' => ['application/vnd.ms-excel', 'ole'],
    'xlsx' => ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'zip'],
    'xlsm' => ['application/vnd.ms-excel.sheet.macroEnabled.12', 'zip'],
    'xltx' => ['application/vnd.openxmlformats-officedocument.spreadsheetml.template', 'zip'],
    'ppt' => ['application/vnd.ms-powerpoint', 'ole'],
    'pptx' => ['application/vnd.openxmlformats-officedocument.presentationml.presentation', 'zip'],
    'odt' => ['application/vnd.oasis.opendocument.text', 'zip'], 'ods' => ['application/vnd.oasis.opendocument.spreadsheet', 'zip'],
    'odp' => ['application/vnd.oasis.opendocument.presentation', 'zip'],
    'vsdx' => ['application/vnd.ms-visio.drawing', 'zip'],
    'msg' => ['application/vnd.ms-outlook', 'ole'], 'eml' => ['message/rfc822', 'text'],
    'rtf' => ['application/rtf', 'rtf'], 'txt' => ['text/plain', 'text'], 'csv' => ['text/csv', 'text'],
    'png' => ['image/png', 'png'], 'jpg' => ['image/jpeg', 'jpg'], 'jpeg' => ['image/jpeg', 'jpg'], 'gif' => ['image/gif', 'gif'],
];

/* ---------- Pfade und Namen ---------- */
function ablage_wurzel(): string
{
    global $DATA;
    return rtrim((string)$DATA, '/') . '/dateien';
}
function ablage_bereich(string $bereich): string
{
    if (!preg_match('/^[a-z][a-z0-9-]{1,30}$/D', $bereich)) throw new RuntimeException('Ungültiger Ablagebereich');
    return $bereich;
}
function ablage_pfad(string $bereich, string $id): string
{
    if (!preg_match('/^[a-z0-9]{12,40}$/D', $id)) throw new RuntimeException('Ungültige Datei-Kennung');
    return ablage_wurzel() . '/' . ablage_bereich($bereich) . '/' . substr($id, 0, 2) . '/' . $id . '.bin';
}
function ablage_neue_id(): string { return bin2hex(random_bytes(10)); }
/* Dateiname für Anzeige und Download: ohne Pfad, Steuer- und unter Windows verbotene Zeichen, höchstens 150 Zeichen,
   Endung bleibt erhalten. Leer → InvalidArgumentException. */
function ablage_dateiname($v): string
{
    $n = is_string($v) ? $v : '';
    $n = str_replace('\\', '/', $n);
    $p = strrpos($n, '/');
    if ($p !== false) $n = substr($n, $p + 1);   // ohne Pfad (nicht basename(): hängt vom Gebietsschema ab)
    $n = preg_replace('/[\x00-\x1f\x7f<>:"\/\\\\|?*]+/u', '-', $n) ?? '';
    $n = trim(preg_replace('/\s+/u', ' ', $n) ?? '', " .\t");
    if ($n === '' || $n === '-') throw new InvalidArgumentException('Bitte eine Datei mit Namen wählen.');
    if (mb_strlen($n) > 150) {
        $e = pathinfo($n, PATHINFO_EXTENSION);
        $n = rtrim(mb_substr($n, 0, 150 - mb_strlen($e) - 1)) . '.' . $e;
    }
    return $n;
}
/* Endung → Art (Schlüssel in ABLAGE_ARTEN) oder Ausnahme */
function ablage_art(string $name): string
{
    $e = strtolower(pathinfo($name, PATHINFO_EXTENSION));
    if (!isset(ABLAGE_ARTEN[$e])) throw new InvalidArgumentException('Diese Dateiart ist nicht erlaubt. Erlaubt sind ' . implode(', ', array_keys(ABLAGE_ARTEN)) . '.');
    return $e;
}
/* Passt der Dateikopf zur Endung? (verhindert z. B. ein Programm mit Endung .pdf) */
function ablage_inhalt_passt(string $pfad, string $art): bool
{
    $fh = @fopen($pfad, 'rb');
    if (!$fh) return false;
    $kopf = (string)fread($fh, 8192);
    fclose($fh);
    $soll = ABLAGE_ARTEN[$art][1] ?? '';
    if ($soll === 'pdf') return strncmp($kopf, '%PDF-', 5) === 0;
    if ($soll === 'zip') return strncmp($kopf, "PK\x03\x04", 4) === 0;
    if ($soll === 'ole') return strncmp($kopf, "\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1", 8) === 0;
    if ($soll === 'png') return strncmp($kopf, "\x89PNG\r\n\x1a\n", 8) === 0;
    if ($soll === 'jpg') return strncmp($kopf, "\xFF\xD8\xFF", 3) === 0;
    if ($soll === 'gif') return strncmp($kopf, 'GIF87a', 6) === 0 || strncmp($kopf, 'GIF89a', 6) === 0;
    if ($soll === 'rtf') return strncmp($kopf, '{\\rtf', 5) === 0;
    if ($soll === 'text') return strpos($kopf, "\0") === false && strncmp($kopf, 'MZ', 2) !== 0 && stripos(ltrim($kopf), '<') !== 0;
    return false;
}

/* ---------- Hochladen in Teilen ---------- */
function ablage_teile_ordner(): string
{
    $o = ablage_wurzel() . '/.teile';
    if (!is_dir($o) && !@mkdir($o, 0775, true) && !is_dir($o)) throw new RuntimeException('Ablage nicht beschreibbar');
    return $o;
}
/* Unvollständige Uploads nach ABLAGE_UPLOAD_STUNDEN entfernen */
function ablage_aufraeumen(): void
{
    $grenze = time() - ABLAGE_UPLOAD_STUNDEN * 3600;
    foreach (glob(ablage_teile_ordner() . '/*.tmp') ?: [] as $f) if ((int)@filemtime($f) < $grenze) @unlink($f);
}
/* Einen Teil annehmen. $b: upload ('' beim ersten Teil), teil (0, 1, …), daten (Base64), name, groesse, sha256 (Hex, optional).
   $ziel: Angaben des Moduls (z. B. Dokument und Version), werden mit dem Upload gemerkt und beim letzten Teil zurückgegeben.
   Rückgabe: ['fertig' => false, 'upload' => …, 'empfangen' => n] oder beim letzten Teil
   ['fertig' => true, 'ziel' => …, 'datei' => ['id', 'name', 'art', 'mime', 'groesse', 'sha256']] – die Datei liegt dann
   bereits in der Ablage; scheitert danach das Eintragen beim Modul, entfernt es sie mit ablage_entfernen(). */
function ablage_teil(string $bereich, string $nutzerId, array $ziel, array $b): array
{
    ablage_bereich($bereich);
    $upload = is_string($b['upload'] ?? null) ? $b['upload'] : '';
    $teil = $b['teil'] ?? null;
    if (!is_int($teil) || $teil < 0 || $teil > 100000) throw new InvalidArgumentException('Ungültiger Teil.');
    $roh = is_string($b['daten'] ?? null) ? base64_decode($b['daten'], true) : false;
    if ($roh === false) throw new InvalidArgumentException('Die Datei kam nicht vollständig an. Bitte erneut hochladen.');
    if (strlen($roh) > ABLAGE_TEIL_MAX) throw new InvalidArgumentException('Teil zu groß.');
    $ordner = ablage_teile_ordner();
    if ($upload === '') {
        if ($teil !== 0) throw new InvalidArgumentException('Ein Upload beginnt mit dem ersten Teil.');
        ablage_aufraeumen();
        $name = ablage_dateiname($b['name'] ?? '');
        $art = ablage_art($name);
        $groesse = $b['groesse'] ?? null;
        if (!is_int($groesse) || $groesse < 1) throw new InvalidArgumentException('Die Datei ist leer.');
        if ($groesse > ABLAGE_DATEI_MAX) throw new InvalidArgumentException('Die Datei ist zu groß (höchstens ' . (int)(ABLAGE_DATEI_MAX / 1048576) . ' MB).');
        $sha = is_string($b['sha256'] ?? null) ? strtolower($b['sha256']) : '';
        if ($sha !== '' && !preg_match('/^[0-9a-f]{64}$/D', $sha)) throw new InvalidArgumentException('Ungültige Prüfsumme.');
        $upload = bin2hex(random_bytes(12));
        $meta = ['bereich' => $bereich, 'nutzer' => $nutzerId, 'ziel' => $ziel, 'name' => $name, 'art' => $art, 'groesse' => $groesse,
                 'sha256' => $sha, 'naechster' => 0, 'empfangen' => 0, 't' => time()];
    } else {
        if (!preg_match('/^[0-9a-f]{24}$/D', $upload) || !is_file("$ordner/$upload-meta.tmp")) throw new InvalidArgumentException('Der Upload ist abgelaufen. Bitte die Datei erneut hochladen.');
        $meta = json_decode((string)file_get_contents("$ordner/$upload-meta.tmp"), true);
        if (!is_array($meta) || ($meta['nutzer'] ?? '') !== $nutzerId || ($meta['bereich'] ?? '') !== $bereich || ($meta['ziel'] ?? null) !== $ziel)
            throw new InvalidArgumentException('Der Upload gehört zu einer anderen Datei. Bitte erneut hochladen.');
        if ($teil !== (int)$meta['naechster']) throw new InvalidArgumentException('Teile in falscher Reihenfolge. Bitte die Datei erneut hochladen.');
    }
    if ($meta['empfangen'] + strlen($roh) > $meta['groesse']) { ablage_upload_verwerfen($upload); throw new InvalidArgumentException('Die Datei ist größer als angegeben.'); }
    $teilPfad = "$ordner/$upload.tmp";
    if (file_put_contents($teilPfad, $roh, FILE_APPEND | LOCK_EX) === false) throw new RuntimeException('Ablage nicht beschreibbar');
    $meta['empfangen'] += strlen($roh);
    $meta['naechster'] = $teil + 1;
    if ($meta['empfangen'] < $meta['groesse']) {
        file_put_contents("$ordner/$upload-meta.tmp", json_encode($meta), LOCK_EX);
        return ['fertig' => false, 'upload' => $upload, 'empfangen' => $meta['empfangen']];
    }
    // Letzter Teil: Größe, Prüfsumme und Dateikopf prüfen, dann in die Ablage
    try {
        clearstatcache(true, $teilPfad);
        if ((int)filesize($teilPfad) !== (int)$meta['groesse']) throw new InvalidArgumentException('Die Datei kam nicht vollständig an. Bitte erneut hochladen.');
        $sha = (string)hash_file('sha256', $teilPfad);
        if ($meta['sha256'] !== '' && !hash_equals($meta['sha256'], $sha)) throw new InvalidArgumentException('Die Datei kam beschädigt an (Prüfsumme). Bitte erneut hochladen.');
        if (!ablage_inhalt_passt($teilPfad, $meta['art'])) throw new InvalidArgumentException('Der Inhalt passt nicht zur Dateiendung „.' . $meta['art'] . '“.');
        $id = ablage_neue_id();
        $ziel = ablage_pfad($bereich, $id);
        if (!is_dir(dirname($ziel)) && !@mkdir(dirname($ziel), 0775, true) && !is_dir(dirname($ziel))) throw new RuntimeException('Ablage nicht beschreibbar');
        if (!@rename($teilPfad, $ziel)) throw new RuntimeException('Ablage nicht beschreibbar');
    } finally {
        ablage_upload_verwerfen($upload);
    }
    return ['fertig' => true, 'ziel' => $meta['ziel'], 'datei' => ['id' => $id, 'name' => $meta['name'], 'art' => $meta['art'],
            'mime' => ABLAGE_ARTEN[$meta['art']][0], 'groesse' => (int)$meta['groesse'], 'sha256' => $sha]];
}
function ablage_upload_verwerfen(string $upload): void
{
    if (!preg_match('/^[0-9a-f]{24}$/D', $upload)) return;
    $o = ablage_teile_ordner();
    @unlink("$o/$upload.tmp"); @unlink("$o/$upload-meta.tmp");
}

/* ---------- Lesen, Ablegen, Kopieren, Entfernen, Ausliefern ---------- */
function ablage_vorhanden(string $bereich, string $id): bool { return is_file(ablage_pfad($bereich, $id)); }
/* Inhalt lesen (z. B. eine Vorlage zum Ausfüllen) oder null, wenn die Datei fehlt */
function ablage_lesen(string $bereich, string $id): ?string
{
    $p = ablage_pfad($bereich, $id);
    if (!is_file($p) || filesize($p) > ABLAGE_DATEI_MAX) return null;
    $t = file_get_contents($p);
    return $t === false ? null : $t;
}
/* Vom Server erzeugten Inhalt (z. B. eine ausgefüllte Vorlage) als neue Datei ablegen: ['id', 'groesse', 'sha256'] */
function ablage_ablegen(string $bereich, string $inhalt): array
{
    if ($inhalt === '' || strlen($inhalt) > ABLAGE_DATEI_MAX) throw new InvalidArgumentException('Die erzeugte Datei ist leer oder zu groß (höchstens ' . (int)(ABLAGE_DATEI_MAX / 1048576) . ' MB).');
    $id = ablage_neue_id();
    $ziel = ablage_pfad($bereich, $id);
    if (!is_dir(dirname($ziel)) && !@mkdir(dirname($ziel), 0775, true) && !is_dir(dirname($ziel))) throw new RuntimeException('Ablage nicht beschreibbar');
    if (file_put_contents("$ziel.tmp", $inhalt, LOCK_EX) !== strlen($inhalt) || !@rename("$ziel.tmp", $ziel)) { @unlink("$ziel.tmp"); throw new RuntimeException('Ablage nicht beschreibbar'); }
    return ['id' => $id, 'groesse' => strlen($inhalt), 'sha256' => hash('sha256', $inhalt)];
}
/* Datei unter neuer Kennung kopieren (z. B. in eine neue Version): ['id', 'groesse', 'sha256'] oder null, wenn sie fehlt */
function ablage_kopieren(string $bereich, string $id): ?array
{
    $q = ablage_pfad($bereich, $id);
    if (!is_file($q)) return null;
    $neu = ablage_neue_id();
    $ziel = ablage_pfad($bereich, $neu);
    if (!is_dir(dirname($ziel)) && !@mkdir(dirname($ziel), 0775, true) && !is_dir(dirname($ziel))) throw new RuntimeException('Ablage nicht beschreibbar');
    if (!@copy($q, "$ziel.tmp") || !@rename("$ziel.tmp", $ziel)) { @unlink("$ziel.tmp"); throw new RuntimeException('Ablage nicht beschreibbar'); }
    return ['id' => $neu, 'groesse' => (int)filesize($ziel), 'sha256' => (string)hash_file('sha256', $ziel)];
}
function ablage_entfernen(string $bereich, string $id): void
{
    $p = ablage_pfad($bereich, $id);
    if (is_file($p) && !@unlink($p)) throw new RuntimeException('Datei konnte nicht entfernt werden');
}
/* Content-Disposition mit ASCII-Ersatz und UTF-8-Namen (RFC 6266/5987) */
function ablage_disposition(string $name): string
{
    $ascii = preg_replace('/[^A-Za-z0-9._ -]+/', '_', strtr($name, ['ä' => 'ae', 'ö' => 'oe', 'ü' => 'ue', 'Ä' => 'Ae', 'Ö' => 'Oe', 'Ü' => 'Ue', 'ß' => 'ss'])) ?: 'datei';
    return 'attachment; filename="' . $ascii . '"; filename*=UTF-8\'\'' . rawurlencode($name);
}
/* Datei als Download senden und beenden; fehlt sie, 404 (JSON) */
function ablage_senden(string $bereich, string $id, string $name, string $mime): void
{
    $p = ablage_pfad($bereich, $id);
    if (!is_file($p)) fail('Die Datei fehlt in der Ablage.', 404);
    @set_time_limit(300);
    header('Content-Type: ' . ($mime !== '' ? $mime : 'application/octet-stream'));
    header('Content-Disposition: ' . ablage_disposition($name));
    header('Content-Length: ' . filesize($p));
    header('Cache-Control: private, no-store');
    header('X-Content-Type-Options: nosniff');
    header("Content-Security-Policy: sandbox; default-src 'none'");
    while (ob_get_level() > 0) ob_end_clean();
    readfile($p);
    exit;
}

/* ---------- ZIP-Export (Methode „stored“, ohne Zip64) ----------
   $eintraege: Liste von ['pfad' => 'Ordner/Datei.pdf', 'bereich' => …, 'id' => …] (Datei aus der Ablage) oder
   ['pfad' => …, 'inhalt' => string] (z. B. eine CSV). Pfade mit „/“, UTF-8; doppelte Pfade bekommen „ (2)“ usw.
   Fehlende Dateien werden übersprungen und in „Hinweise.txt“ vermerkt. */
function ablage_zip_pfad(string $teil): string
{
    $t = preg_replace('/[\x00-\x1f\x7f<>:"\/\\\\|?*]+/u', '-', $teil) ?? '';
    $t = trim(preg_replace('/\s+/u', ' ', $t) ?? '', " .");
    if (mb_strlen($t) > 100) $t = rtrim(mb_substr($t, 0, 100), " .");
    return $t === '' ? '_' : $t;
}
function ablage_zip_senden(string $dateiname, array $eintraege): void
{
    @set_time_limit(0);
    $fehlend = []; $liste = []; $gesehen = []; $summe = 0;
    foreach ($eintraege as $e) {
        $pfad = (string)$e['pfad'];
        if (isset($e['id'])) {
            $p = ablage_pfad((string)$e['bereich'], (string)$e['id']);
            if (!is_file($p)) { $fehlend[] = $pfad; continue; }
            $e['datei'] = $p; $e['groesse'] = (int)filesize($p);
        } else $e['groesse'] = strlen((string)$e['inhalt']);
        // gleiche Pfade unterscheiden (Windows: ohne Groß-/Kleinschreibung)
        $basis = $pfad; $n = 1;
        while (isset($gesehen[mb_strtolower($pfad)])) {
            $n++;
            $punkt = strrpos($basis, '.'); $schnitt = strrpos($basis, '/');
            $pfad = ($punkt !== false && $punkt > (int)$schnitt) ? substr($basis, 0, $punkt) . " ($n)" . substr($basis, $punkt) : "$basis ($n)";
        }
        $gesehen[mb_strtolower($pfad)] = true;
        $e['pfad'] = $pfad;
        $summe += $e['groesse'];
        $liste[] = $e;
    }
    if ($fehlend) {
        $wurzel = strpos((string)($liste[0]['pfad'] ?? ''), '/') !== false ? explode('/', (string)$liste[0]['pfad'])[0] . '/' : '';
        $liste[] = ['pfad' => $wurzel . 'Hinweise.txt', 'inhalt' => "Folgende Dateien fehlen in der Ablage und sind nicht enthalten:\r\n" . implode("\r\n", $fehlend) . "\r\n", 'groesse' => 0];
    }
    if ($summe > ABLAGE_ZIP_MAX) fail('Der Export ist zu groß für ein ZIP-Archiv. Bitte nach Kapitel exportieren.', 413);
    header('Content-Type: application/zip');
    header('Content-Disposition: ' . ablage_disposition($dateiname));
    header('Cache-Control: private, no-store');
    header('X-Content-Type-Options: nosniff');
    while (ob_get_level() > 0) ob_end_clean();
    $t = getdate();
    $zeit = ($t['hours'] << 11) | ($t['minutes'] << 5) | intdiv($t['seconds'], 2);
    $datum = (max(0, $t['year'] - 1980) << 9) | ($t['mon'] << 5) | $t['mday'];
    $off = 0; $verz = ''; $n = 0;
    foreach ($liste as $e) {
        $name = (string)$e['pfad'];
        if (isset($e['datei'])) { $crc = (int)hexdec((string)hash_file('crc32b', $e['datei'])); $len = (int)filesize($e['datei']); }
        else { $inhalt = (string)$e['inhalt']; $crc = crc32($inhalt); $len = strlen($inhalt); }
        $kopf = "PK\x03\x04" . pack('vvvvvVVVvv', 20, 0x0800, 0, $zeit, $datum, $crc, $len, $len, strlen($name), 0) . $name;
        echo $kopf;
        if (isset($e['datei'])) { $fh = fopen($e['datei'], 'rb'); while (!feof($fh)) { echo fread($fh, 1048576); flush(); } fclose($fh); }
        else echo $inhalt;
        $verz .= "PK\x01\x02" . pack('vvvvvvVVVvvvvvVV', 20, 20, 0x0800, 0, $zeit, $datum, $crc, $len, $len, strlen($name), 0, 0, 0, 0, 0, $off) . $name;
        $off += strlen($kopf) + $len;
        $n++;
    }
    echo $verz . "PK\x05\x06" . pack('vvvvVVv', 0, 0, $n, $n, strlen($verz), $off, 0);
    exit;
}
