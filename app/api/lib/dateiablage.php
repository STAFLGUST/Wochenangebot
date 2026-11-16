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
   Ein Upload beginnt nur, wenn danach noch ABLAGE_RESERVE auf der Platte frei bleibt. Ein ZIP-Archiv darf keine Einträge
   gesperrter Arten enthalten (ohne Entpacken: Verzeichnis, lokale Köpfe, Unicode-Pfad; höchstens ABLAGE_ZIP_EINTRAEGE_MAX).
   Vom Server erzeugte Dateien (z. B. aus einer Vorlage ausgefüllt) legt ablage_ablegen() ab, ablage_kopieren() legt eine Datei
   unter neuer Kennung ab (z. B. in eine neue Version; fester Verweis, da Ablage-Dateien sich nie ändern), ablage_lesen()
   liefert den Inhalt (nur bis ABLAGE_LESEN_MAX). Downloads geben die Sitzung vor dem Senden frei.
   Große Dateien: Zusammensetzen, Prüfsumme und Kopfprüfung arbeiten auf der Datei, nie auf dem ganzen Inhalt im Speicher.
   ZIP-Export: ablage_zip_senden() schreibt ein ZIP (Methode „stored“, UTF-8-Namen) direkt in die Antwort – ohne die
   PHP-Erweiterung „zip“ und ohne das ganze Archiv im Speicher zu halten; ab 4 GB bzw. 65535 Einträgen mit Zip64-Feldern. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const ABLAGE_TEIL_MAX = 3 * 1024 * 1024;        // Bytes je Teil (Base64 ≈ 4 MB, unter der Grenze des API-Einstiegs)
const ABLAGE_DATEI_MAX = 250 * 1024 * 1024;     // Bytes je Datei (Inhaber 16.11.2026: ganzes QM-System mit Videos und ZIP)
const ABLAGE_LESEN_MAX = 25 * 1024 * 1024;      // ablage_lesen() hält die ganze Datei im Speicher
/* Frei nach einem Upload: die Schwelle, ab der Sicherheit → System „Freier Speicher“ warnt (lib/diagnose.php), und die Reserve
   der Sicherung (deploy/sichern.sh) – Datenbank, Protokolle und Sicherung brauchen den Platz auch bei voller Ablage */
const ABLAGE_RESERVE = 5 * 1024 * 1024 * 1024;
const ABLAGE_UPLOAD_STUNDEN = 24;               // unvollständige Uploads werden danach entfernt
/* Nie erlaubt, auch nicht als Eintrag eines ZIP-Archivs: Arten, die beim Öffnen Code ausführen – im Browser bzw. unter Windows */
const ABLAGE_GESPERRT = ['html', 'htm', 'xhtml', 'svg', 'js', 'exe', 'com', 'scr', 'msi', 'bat', 'cmd', 'ps1', 'vbs', 'jar', 'hta', 'lnk', 'reg'];
/* Erlaubte Dateiarten: Endung → [MIME-Typ, Kopfprüfung aus ABLAGE_KOEPFE bzw. „text“/„binaer“]. Unbekannte Endungen bleiben
   abgelehnt. Ein ZIP-Archiv wird nicht entpackt; geprüft werden die Namen seiner Einträge (ablage_zip_pruefen). */
const ABLAGE_ARTEN = [
    'pdf' => ['application/pdf', 'pdf'],
    'doc' => ['application/msword', 'ole'], 'dot' => ['application/msword', 'ole'],
    'docx' => ['application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'ooxml'],
    'dotx' => ['application/vnd.openxmlformats-officedocument.wordprocessingml.template', 'ooxml'],
    'xls' => ['application/vnd.ms-excel', 'ole'], 'xlt' => ['application/vnd.ms-excel', 'ole'],
    'xlsx' => ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'ooxml'],
    'xlsm' => ['application/vnd.ms-excel.sheet.macroEnabled.12', 'ooxml'],
    'xltx' => ['application/vnd.openxmlformats-officedocument.spreadsheetml.template', 'ooxml'],
    'ppt' => ['application/vnd.ms-powerpoint', 'ole'],
    'pptx' => ['application/vnd.openxmlformats-officedocument.presentationml.presentation', 'ooxml'],
    'odt' => ['application/vnd.oasis.opendocument.text', 'office'], 'ods' => ['application/vnd.oasis.opendocument.spreadsheet', 'office'],
    'odp' => ['application/vnd.oasis.opendocument.presentation', 'office'],
    'vsdx' => ['application/vnd.ms-visio.drawing', 'ooxml'],
    'msg' => ['application/vnd.ms-outlook', 'ole'], 'eml' => ['message/rfc822', 'text'],
    'rtf' => ['application/rtf', 'rtf'], 'txt' => ['text/plain', 'text'], 'csv' => ['text/csv', 'text'],
    'png' => ['image/png', 'png'], 'jpg' => ['image/jpeg', 'jpg'], 'jpeg' => ['image/jpeg', 'jpg'], 'gif' => ['image/gif', 'gif'],
    'heic' => ['image/heic', 'heic'], 'heif' => ['image/heif', 'heic'], 'tif' => ['image/tiff', 'tif'], 'tiff' => ['image/tiff', 'tif'],
    'bmp' => ['image/bmp', 'bmp'],
    'mov' => ['video/quicktime', 'video'], 'mp4' => ['video/mp4', 'video'], 'm4v' => ['video/x-m4v', 'video'],
    'opus' => ['audio/ogg', 'ogg'], 'ogg' => ['audio/ogg', 'ogg'],
    'zip' => ['application/zip', 'zip'], 'xlsb' => ['application/vnd.ms-excel.sheet.binary.macroEnabled.12', 'ooxml'],
    'json' => ['application/json', 'text'], 'ics' => ['text/calendar', 'text'],
    'ttv' => ['application/octet-stream', 'binaer'],   // Trendview-Datenschreiber: Binärformat ohne festen Kopf
];
/* Erwartete Dateiköpfe: Liste von [Versatz, Bytes], einer muss passen */
const ABLAGE_KOEPFE = [
    'pdf' => [[0, '%PDF-']],
    'zip' => [[0, "PK\x03\x04"], [0, "PK\x05\x06"]],   // PK\5\6: leeres ZIP
    'office' => [[0, "PK\x03\x04"]],                     // OpenDocument: ZIP-Archiv, nie leer, auch mit Kennwort
    // Microsoft Office speichert eine Datei mit Kennwort als OLE-Container; ein OLE-Container ist als .doc/.xls ohnehin erlaubt
    'ooxml' => [[0, "PK\x03\x04"], [0, "\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"]],
    'ole' => [[0, "\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1"]],
    'png' => [[0, "\x89PNG\r\n\x1a\n"]],
    'jpg' => [[0, "\xFF\xD8\xFF"]],
    'gif' => [[0, 'GIF87a'], [0, 'GIF89a']],
    'rtf' => [[0, '{\\rtf']],
    'tif' => [[0, "II*\0"], [0, "MM\0*"]],
    'bmp' => [[0, 'BM']],
    'ogg' => [[0, 'OggS']],
    // ISO-BMFF (MP4, neuere MOV): „ftyp“ an Byte 4; ältere QuickTime-Dateien beginnen mit einem anderen Block der obersten Ebene
    'video' => [[4, 'ftyp'], [4, 'moov'], [4, 'mdat'], [4, 'wide'], [4, 'free'], [4, 'skip'], [4, 'pnot']],
    'heic' => [[4, 'ftypheic'], [4, 'ftypheix'], [4, 'ftyphevc'], [4, 'ftyphevx'], [4, 'ftypmif1'], [4, 'ftypmsf1']],
];

/* ---------- Pfade und Namen ---------- */
function ablage_wurzel(): string
{
    // Dateien sind intern (Dokumentenablage QS u. a.): nach der Datentrennung im Ordner daten-intern, den die Kundenseite
    // nicht sieht (app/api/storage.php, ADR-007 Stufe 2); vorher wie bisher im Datenordner
    return rtrim(store_ordner(store_getrennt() ? 'intern' : 'haupt'), '/') . '/dateien';
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
function ablage_mb(int $bytes): string { return intdiv($bytes, 1048576) . ' MB'; }
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
    if (!isset(ABLAGE_ARTEN[$e]) || in_array($e, ABLAGE_GESPERRT, true)) throw new InvalidArgumentException('Diese Dateiart ist nicht erlaubt. Erlaubt sind ' . implode(', ', array_keys(ABLAGE_ARTEN)) . '.');
    return $e;
}
/* Passt der Dateikopf zur Endung? (verhindert z. B. ein Programm mit Endung .pdf) */
function ablage_inhalt_passt(string $pfad, string $art): bool
{
    $fh = @fopen($pfad, 'rb');
    if (!$fh) return false;
    $kopf = (string)fread($fh, 8192);
    fclose($fh);
    if (strncmp($kopf, 'MZ', 2) === 0) return false;   // Windows-Programm, gleich mit welcher Endung
    $soll = ABLAGE_ARTEN[$art][1];
    // „<“ nur bei Arten ohne festen Kopf: ein MP4 mit 60 Byte langem ftyp-Block beginnt mit \0\0\0<
    if ($soll === 'text') return strpos($kopf, "\0") === false && strncmp(ltrim($kopf), '<', 1) !== 0;
    if ($soll === 'binaer') return strncmp(ltrim($kopf, " \t\r\n"), '<', 1) !== 0;
    foreach (ABLAGE_KOEPFE[$soll] as [$pos, $bytes]) if (substr($kopf, $pos, strlen($bytes)) === $bytes) return true;
    return false;
}
/* ZIP-Aufbau (PKWARE APPNOTE 4.3): Signatur und feste Länge der Sätze. Der Höchstwert eines 16-/32-Bit-Feldes heißt „siehe Zip64“. */
const ABLAGE_ZIP_SAETZE = [
    'lokal' => ["PK\x03\x04", 30],       // Kopf vor jedem Inhalt
    'eintrag' => ["PK\x01\x02", 46],     // Eintrag im zentralen Verzeichnis
    'ende64' => ["PK\x06\x06", 56],      // Zip64-Ende (ohne erweiterbaren Teil, den nur verschlüsselte Verzeichnisse nutzen)
    'verweis64' => ["PK\x06\x07", 20],   // Verweis auf das Zip64-Ende, direkt vor dem Ende
    'ende' => ["PK\x05\x06", 22],        // Ende des Verzeichnisses, danach der Kommentar
];
const ABLAGE_ZIP_VOLL16 = 0xFFFF;
const ABLAGE_ZIP_VOLL32 = 0xFFFFFFFF;
const ABLAGE_ZIP_FELD_ZIP64 = 0x0001;
const ABLAGE_ZIP_FELD_UNICODE = 0x7075;   // Unicode-Pfad (Info-ZIP): Version, Prüfsumme des Namens, Name in UTF-8
/* Zusatzfelder je Kopf: Packer schreiben bis zu fünf (Zeiten, Unix-Kennung, Zip64, Unicode-Pfad, Verschlüsselung). Mehr hält
   nur die Prüfung auf (65535 Bytes leerer Felder sind 16383 Felder). */
const ABLAGE_ZIP_FELDER_MAX = 16;
/* Höchstzahl der Einträge je ZIP: ein QM-Archiv hat höchstens einige Zehntausend (das ganze QM-System rund 15.000 Dateien).
   Bis zur Grenze dauert die Prüfung höchstens rund 3 s; 250 MB voller kleinster Einträge (3,4 Mio.) bräuchten 20 bis 30 s. */
const ABLAGE_ZIP_EINTRAEGE_MAX = 200000;
const ABLAGE_ZIP_MELDUNG_MAX = 5;          // so viele gesperrte Einträge nennt die Meldung
/* Namen eines ZIP-Archivs gegen ABLAGE_GESPERRT prüfen, ohne zu entpacken (auch Zip64); wirft bei gesperrter Endung, mehr als
   ABLAGE_ZIP_EINTRAEGE_MAX Einträgen oder unklarem Aufbau. Geprüft wird jeder Name, den ein Entpacker zeigen könnte: im
   Verzeichnis, im lokalen Kopf (muss gleich sein) und im Unicode-Pfad beider. Das Verzeichnis muss lückenlos direkt vor dem Ende
   stehen und genau die angegebene Zahl Einträge haben – sonst lesen Python, Go, Java oder unzip womöglich andere Einträge.
   Ein ZIP im ZIP wird nicht geöffnet. */
function ablage_zip_pruefen(string $pfad): void
{
    $kaputt = new InvalidArgumentException('Das ZIP-Archiv ist beschädigt (Inhaltsverzeichnis nicht lesbar).');
    $groesse = (int)filesize($pfad);
    $fh = fopen($pfad, 'rb');
    if ($fh === false) throw new RuntimeException('Ablage nicht lesbar');
    try {
        $lesen = function (int $pos, int $n) use ($fh): string { if ($n < 1 || $pos < 0) return ''; fseek($fh, $pos); return (string)fread($fh, $n); };
        $satz = function (int $pos, string $art) use ($lesen, $kaputt): string {
            [$sig, $n] = ABLAGE_ZIP_SAETZE[$art];
            $s = $lesen($pos, $n);
            return strlen($s) === $n && str_starts_with($s, $sig) ? $s : throw $kaputt;
        };
        // Ende: der letzte Satz, der ganz in die Datei passt (so suchen Go und Java), mit Kommentar genau bis zum Dateiende
        [$endeSig, $endeLaenge] = ABLAGE_ZIP_SAETZE['ende'];
        $endeAb = max(0, $groesse - $endeLaenge - ABLAGE_ZIP_VOLL16);
        $ende = $lesen($endeAb, $groesse - $endeAb);
        $p = strlen($ende) < $endeLaenge ? false : strrpos($ende, $endeSig, -$endeLaenge);
        if ($p === false) throw $kaputt;
        $e = unpack('x10/vanzahl/Vlaenge/Vstart/vkommentar', $ende, $p);
        if ($p + $endeLaenge + $e['kommentar'] !== strlen($ende)) throw $kaputt;
        $verzEnde = $endeAb + $p;
        $verweisPos = $verzEnde - ABLAGE_ZIP_SAETZE['verweis64'][1];
        $zip64 = str_starts_with($lesen($verweisPos, 4), ABLAGE_ZIP_SAETZE['verweis64'][0]);
        if ($zip64) {   // wie bei Python, sobald der Verweis da ist; klassische Felder: Höchstwert oder gleicher Wert (wie bei Java)
            $verzEnde = unpack('x8/Pende64', $satz($verweisPos, 'verweis64'))['ende64'];
            $z = unpack('x32/Panzahl/Plaenge/Pstart', $satz($verzEnde, 'ende64'));
            if ($verzEnde + ABLAGE_ZIP_SAETZE['ende64'][1] !== $verweisPos) throw $kaputt;   // ohne erweiterbaren Teil
            foreach (['anzahl' => ABLAGE_ZIP_VOLL16, 'laenge' => ABLAGE_ZIP_VOLL32, 'start' => ABLAGE_ZIP_VOLL32] as $k => $voll)
                if ($e[$k] !== $voll && $e[$k] !== $z[$k]) throw $kaputt;
            $e = $z;
        }
        if ($e['start'] + $e['laenge'] !== $verzEnde) throw $kaputt;
        $muster = '/\.(?:' . implode('|', ABLAGE_GESPERRT) . ')[ .]*(?::|$)/iD';   // Windows: „a.exe. “ = „a.exe“, „a.exe:x“ = Datenstrom von a.exe
        for ($pos = $e['start'], $gelesen = 0, $vorher = -1, $gesperrt = [], $zahlGesperrt = 0; $pos < $verzEnde; $gelesen++) {
            if ($gelesen === ABLAGE_ZIP_EINTRAEGE_MAX) throw new InvalidArgumentException('Das ZIP-Archiv hat mehr als ' . number_format(ABLAGE_ZIP_EINTRAEGE_MAX, 0, ',', '.') . ' Einträge. Bitte in kleinere Archive teilen.');
            $c = unpack('x20/Vgepackt/Vgroesse/vname/vextra/vkommentar/x8/Vversatz', $satz($pos, 'eintrag'));
            $pos += ABLAGE_ZIP_SAETZE['eintrag'][1];
            $name = $lesen($pos, $c['name']);
            $felder = ablage_zip_felder($lesen($pos + $c['name'], $c['extra'])) ?? throw $kaputt;
            $pos += $c['name'] + $c['extra'] + $c['kommentar'];
            if ($pos > $verzEnde) throw $kaputt;
            if ($c['versatz'] === ABLAGE_ZIP_VOLL32) {   // Zip64-Feld enthält nur die Werte, die hier Höchstwert sind, in dieser Reihenfolge
                $vor = 8 * (($c['groesse'] === ABLAGE_ZIP_VOLL32) + ($c['gepackt'] === ABLAGE_ZIP_VOLL32));
                $z64 = $felder[ABLAGE_ZIP_FELD_ZIP64][0] ?? '';
                $c['versatz'] = strlen($z64) >= $vor + 8 ? unpack('P', $z64, $vor)[1] : throw $kaputt;
            }
            // je Eintrag ein eigener lokaler Kopf, aufsteigend vor dem Verzeichnis (geteilte Köpfe würden je Eintrag neu gelesen), gleicher Name
            $l = unpack('x26/vname/vextra', $satz($c['versatz'], 'lokal'));
            $lokal = $c['versatz'] + ABLAGE_ZIP_SAETZE['lokal'][1];
            if ($c['versatz'] <= $vorher || $lokal > $e['start'] || $lesen($lokal, $l['name']) !== $name) throw $kaputt;
            $vorher = $c['versatz'];
            $namen = [$name];
            foreach ([$felder, ablage_zip_felder($lesen($lokal + $l['name'], $l['extra'])) ?? throw $kaputt] as $f)
                foreach ($f[ABLAGE_ZIP_FELD_UNICODE] ?? [] as $u) $namen[] = substr($u, 5);   // nach Version (1) und Prüfsumme (4)
            foreach ($namen as $n) {
                if (str_contains($n, "\0")) throw $kaputt;   // Python und Go schneiden dort ab: „a.exe\0.txt“ wird zu „a.exe“
                if (preg_match($muster, $n) === 0) continue;   // ein Fehler der Suche (false) sperrt
                if (++$zahlGesperrt <= ABLAGE_ZIP_MELDUNG_MAX) $gesperrt[] = '„' . mb_substr(mb_scrub($n), 0, 150) . '“';
                break;
            }
        }
        // 16-Bit-Zahl ohne Zip64 modulo 65536 (so zählen Go und unzip; 65535 Einträge schreibt Python ohne Zip64)
        if ($pos !== $verzEnde || ($zip64 ? $gelesen : $gelesen & ABLAGE_ZIP_VOLL16) !== $e['anzahl']) throw $kaputt;
        if ($gesperrt) throw new InvalidArgumentException('Das ZIP-Archiv enthält gesperrte Dateiarten: ' . implode(', ', $gesperrt)
            . ($zahlGesperrt > count($gesperrt) ? ' und ' . ($zahlGesperrt - count($gesperrt)) . ' weitere' : '') . '.');
    } finally {
        fclose($fh);
    }
}
/* Zusatzfelder eines ZIP-Kopfes → [Kennung => [Inhalt, …]]; null, wenn ein Feld abgeschnitten ist (wie bei Python) oder es mehr
   als ABLAGE_ZIP_FELDER_MAX sind */
function ablage_zip_felder(string $z): ?array
{
    for ($felder = [], $i = 0, $k = 0; $i + 4 <= strlen($z); $i += 4 + $f['n']) {
        $f = unpack('vid/vn', $z, $i);
        if ($i + 4 + $f['n'] > strlen($z) || ++$k > ABLAGE_ZIP_FELDER_MAX) return null;
        $felder[$f['id']][] = substr($z, $i + 4, $f['n']);
    }
    return $felder;
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
        if ($groesse > ABLAGE_DATEI_MAX) throw new InvalidArgumentException('Die Datei ist zu groß (höchstens ' . ablage_mb(ABLAGE_DATEI_MAX) . ').');
        $frei = @disk_free_space($ordner);   // false (nicht ermittelbar): wie bisher annehmen
        if ($frei !== false && !ablage_platz_reicht($frei, $groesse))
            throw new InvalidArgumentException('Auf dem Server ist nicht genug Speicherplatz für diese Datei frei. Bitte den Administrator informieren.');
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
        if ($meta['art'] === 'zip') ablage_zip_pruefen($teilPfad);
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
function ablage_platz_reicht(float $frei, int $groesse): bool { return $frei - $groesse >= ABLAGE_RESERVE; }
function ablage_upload_verwerfen(string $upload): void
{
    if (!preg_match('/^[0-9a-f]{24}$/D', $upload)) return;
    $o = ablage_teile_ordner();
    @unlink("$o/$upload.tmp"); @unlink("$o/$upload-meta.tmp");
}

/* ---------- Lesen, Ablegen, Kopieren, Entfernen, Ausliefern ---------- */
function ablage_vorhanden(string $bereich, string $id): bool { return is_file(ablage_pfad($bereich, $id)); }
/* Inhalt lesen (z. B. eine Vorlage zum Ausfüllen) oder null, wenn die Datei fehlt oder größer als ABLAGE_LESEN_MAX ist */
function ablage_lesen(string $bereich, string $id): ?string
{
    $p = ablage_pfad($bereich, $id);
    if (!is_file($p) || filesize($p) > ABLAGE_LESEN_MAX) return null;
    $t = file_get_contents($p);
    return $t === false ? null : $t;
}
/* Vom Server erzeugten Inhalt (z. B. eine ausgefüllte Vorlage) als neue Datei ablegen: ['id', 'groesse', 'sha256'] */
function ablage_ablegen(string $bereich, string $inhalt): array
{
    if ($inhalt === '' || strlen($inhalt) > ABLAGE_DATEI_MAX) throw new InvalidArgumentException('Die erzeugte Datei ist leer oder zu groß (höchstens ' . ablage_mb(ABLAGE_DATEI_MAX) . ').');
    $id = ablage_neue_id();
    $ziel = ablage_pfad($bereich, $id);
    if (!is_dir(dirname($ziel)) && !@mkdir(dirname($ziel), 0775, true) && !is_dir(dirname($ziel))) throw new RuntimeException('Ablage nicht beschreibbar');
    if (file_put_contents("$ziel.tmp", $inhalt, LOCK_EX) !== strlen($inhalt) || !@rename("$ziel.tmp", $ziel)) { @unlink("$ziel.tmp"); throw new RuntimeException('Ablage nicht beschreibbar'); }
    return ['id' => $id, 'groesse' => strlen($inhalt), 'sha256' => hash('sha256', $inhalt)];
}
/* Datei unter neuer Kennung ablegen (z. B. in eine neue Version): ['id', 'groesse', 'sha256'] oder null, wenn sie fehlt.
   Ablage-Dateien ändern sich nie: fester Verweis (Hardlink, kostet weder Platz noch Zeit), Kopie nur, wo das Dateisystem keinen
   kennt; ablage_entfernen() löscht nur den eigenen Namen. $sha256: Prüfsumme aus den Metadaten des Moduls, sonst gerechnet. */
function ablage_kopieren(string $bereich, string $id, string $sha256 = ''): ?array
{
    $q = ablage_pfad($bereich, $id);
    if (!is_file($q)) return null;
    $neu = ablage_neue_id();
    $ziel = ablage_pfad($bereich, $neu);
    if (!is_dir(dirname($ziel)) && !@mkdir(dirname($ziel), 0775, true) && !is_dir(dirname($ziel))) throw new RuntimeException('Ablage nicht beschreibbar');
    if (!@link($q, $ziel) && (!@copy($q, "$ziel.tmp") || !@rename("$ziel.tmp", $ziel))) { @unlink("$ziel.tmp"); throw new RuntimeException('Ablage nicht beschreibbar'); }
    return ['id' => $neu, 'groesse' => (int)filesize($ziel), 'sha256' => $sha256 !== '' ? $sha256 : (string)hash_file('sha256', $ziel)];
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
    if (session_status() === PHP_SESSION_ACTIVE) session_write_close();   // sonst wartet jede weitere Anfrage der Sitzung auf das Ende des Downloads
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

/* ---------- ZIP-Export (Methode „stored“) ----------
   $eintraege: Liste von ['pfad' => 'Ordner/Datei.pdf', 'bereich' => …, 'id' => …] (Datei aus der Ablage) oder
   ['pfad' => …, 'inhalt' => string] (z. B. eine CSV). Pfade mit „/“, UTF-8; doppelte Pfade bekommen „ (2)“ usw.
   Fehlende Dateien werden übersprungen und in „Hinweise.txt“ vermerkt; verschwindet eine Datei erst während des Exports, fehlt
   sie im Archiv und steht im Fehlerprotokoll des Servers. Jeder Eintrag bleibt unter 4 GB; Zip64 braucht es nur für den
   Versatz ab 4 GB und ab 65535 Einträgen. */
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
    $fehlend = []; $liste = []; $gesehen = [];
    foreach ($eintraege as $e) {
        $pfad = (string)$e['pfad'];
        if (isset($e['id'])) {
            $p = ablage_pfad((string)$e['bereich'], (string)$e['id']);
            if (!is_file($p)) { $fehlend[] = $pfad; continue; }
            if (filesize($p) >= 0xFFFFFFFF) throw new RuntimeException('ZIP-Export: Eintrag ab 4 GB nicht vorgesehen (' . $pfad . ')');
            $e['datei'] = $p;
        }
        // gleiche Pfade unterscheiden (Windows: ohne Groß-/Kleinschreibung)
        $basis = $pfad; $n = 1;
        while (isset($gesehen[mb_strtolower($pfad)])) {
            $n++;
            $punkt = strrpos($basis, '.'); $schnitt = strrpos($basis, '/');
            $pfad = ($punkt !== false && $punkt > (int)$schnitt) ? substr($basis, 0, $punkt) . " ($n)" . substr($basis, $punkt) : "$basis ($n)";
        }
        $gesehen[mb_strtolower($pfad)] = true;
        $e['pfad'] = $pfad;
        $liste[] = $e;
    }
    if ($fehlend) {
        $wurzel = strpos((string)($liste[0]['pfad'] ?? ''), '/') !== false ? explode('/', (string)$liste[0]['pfad'])[0] . '/' : '';
        $liste[] = ['pfad' => $wurzel . 'Hinweise.txt', 'inhalt' => "Folgende Dateien fehlen in der Ablage und sind nicht enthalten:\r\n" . implode("\r\n", $fehlend) . "\r\n"];
    }
    if (session_status() === PHP_SESSION_ACTIVE) session_write_close();   // sonst wartet jede weitere Anfrage der Sitzung auf das Ende des Exports
    header('Content-Type: application/zip');
    header('Content-Disposition: ' . ablage_disposition($dateiname));
    header('Cache-Control: private, no-store');
    header('X-Content-Type-Options: nosniff');
    while (ob_get_level() > 0) ob_end_clean();
    $t = getdate();
    $zeit = ($t['hours'] << 11) | ($t['minutes'] << 5) | intdiv($t['seconds'], 2);
    $datum = (max(0, $t['year'] - 1980) << 9) | ($t['mon'] << 5) | $t['mday'];
    $off = 0; $verz = ''; $anzahl = 0;
    foreach ($liste as $e) {
        $name = (string)$e['pfad'];
        if (isset($e['datei'])) {
            // Erst öffnen, dann Kopf schreiben: ein geöffneter Inhalt bleibt lesbar, auch wenn die Datei danach entfernt wird
            $fh = @fopen($e['datei'], 'rb');
            if ($fh === false) { error_log('ZIP-Export: ' . $name . ' während des Exports entfernt, nicht im Archiv'); continue; }
            $len = (int)fstat($fh)['size'];
            $h = hash_init('crc32b'); hash_update_stream($h, $fh); rewind($fh);
            $crc = (int)hexdec(hash_final($h));
        } else { $inhalt = (string)$e['inhalt']; $crc = crc32($inhalt); $len = strlen($inhalt); }
        $zip64 = $off >= 0xFFFFFFFF;   // Versatz passt nicht in 32 Bit
        $version = $zip64 ? 45 : 20;
        // Zip64-Feld auch im lokalen Kopf: Info-ZIP unzip wertet das UTF-8-Kennzeichen nur bei vorhandenem Zusatzfeld aus und
        // läse den Namen sonst lokal anders als im Verzeichnis („mismatching local filename“)
        $extraLokal = $zip64 ? pack('vvPP', 1, 16, $len, $len) : '';
        $extraVerz = $zip64 ? pack('vvP', 1, 8, $off) : '';
        $groesseLokal = $zip64 ? 0xFFFFFFFF : $len;
        $kopf = "PK\x03\x04" . pack('vvvvvVVVvv', $version, 0x0800, 0, $zeit, $datum, $crc, $groesseLokal, $groesseLokal, strlen($name), strlen($extraLokal)) . $name . $extraLokal;
        echo $kopf;
        if (isset($e['datei'])) { while (!feof($fh)) { echo fread($fh, 1048576); flush(); } fclose($fh); }
        else echo $inhalt;
        $verz .= "PK\x01\x02" . pack('vvvvvvVVVvvvvvVV', $version, $version, 0x0800, 0, $zeit, $datum, $crc, $len, $len, strlen($name), strlen($extraVerz), 0, 0, 0, 0, min($off, 0xFFFFFFFF))
              . $name . $extraVerz;
        $off += strlen($kopf) + $len;
        $anzahl++;
    }
    echo $verz . ablage_zip_ende($anzahl, strlen($verz), $off);
    exit;
}
/* Ende des Verzeichnisses; ab 65535 Einträgen bzw. 4 GB (Länge oder Beginn des Verzeichnisses) davor das Zip64-Ende und der
   Verweis darauf. In den 16-/32-Bit-Feldern steht dann der Höchstwert als Zeichen „siehe Zip64“. */
function ablage_zip_ende(int $anzahl, int $verzLaenge, int $verzStart): string
{
    $ende = "PK\x05\x06" . pack('vvvvVVv', 0, 0, min($anzahl, 0xFFFF), min($anzahl, 0xFFFF), min($verzLaenge, 0xFFFFFFFF), min($verzStart, 0xFFFFFFFF), 0);
    if ($anzahl < 0xFFFF && $verzLaenge < 0xFFFFFFFF && $verzStart < 0xFFFFFFFF) return $ende;
    return "PK\x06\x06" . pack('PvvVVPPPP', 44, 45, 45, 0, 0, $anzahl, $anzahl, $verzLaenge, $verzStart)
         . "PK\x06\x07" . pack('VPV', 0, $verzStart + $verzLaenge, 1) . $ende;
}
