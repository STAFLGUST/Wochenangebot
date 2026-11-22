<?php
/*
 * Abrufe nach außen: gemeinsamer Standard für jeden Abruf fremder Dienste (Länderdaten geo.php, Ortsdaten ort.php,
 * Bedrohungsliste lib/firewall.php, Datenleck-Prüfung lib/nutzer.php, Hafen Hamburg und Whisp im Modul Container-Import).
 *
 *   abruf_frist_strom()  Strom mit Gesamtfrist und Mengengrenze unter einem Leser (fgets, fgetcsv, zlib-Filter)
 *   abruf_text()         ganze Antwort eines Stromkontexts holen – statt file_get_contents
 *   abruf_http()         ganze Antwort mit Status holen, Gesamtfrist über Verbinden, Kopf- und Rumpfphase
 *   abruf_vollstaendig() darf eine heruntergeladene Liste den bisherigen Bestand ersetzen?
 *
 * Wann welcher: abruf_text für einen vorbereiteten Stromkontext (Weiterleitungen, eigene Kopfzeilen des Wrappers) ohne
 * Bedarf am HTTP-Status; abruf_http, wenn der Status zählt, POST nötig ist oder die Gegenstelle schon in der Kopfphase
 * tröpfeln kann – nur dort liegt die Frist auch über Verbindungsaufbau und Kopfzeilen (fopen tut das nicht, nachgestellt).
 * Diese Datei lädt geo.php als erste (require_once), und geo.php lädt lib/laden.php als erste – deshalb stehen die Helfer
 * jeder Aktion und jedem Modul zur Verfügung, ohne eigenen Einbindeweg.
 */
declare(strict_types=1);
if (realpath((string)($_SERVER['SCRIPT_FILENAME'] ?? '')) === __FILE__) { http_response_code(404); exit; }

/* Strom mit Gesamtfrist und Mengengrenze. Nötig, weil „timeout“ eines Stroms nur je Lesevorgang gilt: eine tröpfelnde
   Gegenstelle (ein Byte je Sekunde) sendet immer wieder etwas, und fgets/fgetcsv warten dann beliebig lange auf das Ende
   einer Zeile – Arbeitsprozess und Sperre des Aufrufers bleiben so lange gehalten (nachgestellt: 150 s trotz
   set_time_limit(2), weil PHP Wartezeit in Stream-Aufrufen nicht auf max_execution_time zählt). Dieser Strom legt sich
   unter den Leser und gibt jedem Lesevorgang nur die restliche Frist; sind Frist oder Menge verbraucht, bricht der Abruf mit
   einer Ausnahme ab – sie trägt durch fgets, fgetcsv und einen zlib-Filter hindurch. Nicht selbst öffnen: abruf_frist_strom. */
class AbrufFrist
{
    public $context;
    public static array $warten = [];
    private $fh;
    private float $ende;
    private int $max;
    private int $gelesen = 0;
    private string $was;
    public function stream_open($pfad, $modus, $opt, &$ge): bool
    {
        $k = substr((string)$pfad, strpos((string)$pfad, '://') + 3);
        if (!isset(self::$warten[$k])) return false;
        [$this->fh, $this->ende, $this->max, $this->was] = self::$warten[$k];
        unset(self::$warten[$k]);   // jeder Strom wird genau einmal geöffnet
        return true;
    }
    public function stream_read($n)
    {
        $rest = $this->ende - microtime(true);
        if ($rest <= 0) throw new RuntimeException('Der Abruf der ' . $this->was . ' hat zu lange gedauert.');
        if ($this->gelesen > $this->max) throw new RuntimeException('Der Abruf der ' . $this->was . ' liefert unerwartet viele Daten.');
        @stream_set_timeout($this->fh, (int)ceil($rest));   // so endet auch eine ganz stumme Gegenstelle mit der Frist
        $teil = fread($this->fh, $n);
        $this->gelesen += strlen((string)$teil);
        return $teil;
    }
    public function stream_eof(): bool { return feof($this->fh); }
    public function stream_stat() { return []; }
    public function stream_set_option($o, $a, $b): bool { return false; }
}
if (!in_array('wafrist', stream_get_wrappers(), true)) stream_wrapper_register('wafrist', 'AbrufFrist');

/* Offenen Strom hinter Gesamtfrist ($ende: Zeitpunkt aus microtime) und Mengengrenze legen: gelesen wird aus dem
   Rückgabewert, der ursprüngliche Strom bleibt dem Aufrufer zum Schließen. */
function abruf_frist_strom($fh, float $ende, int $max, string $was)
{
    static $n = 0;
    $k = (string)++$n;
    AbrufFrist::$warten[$k] = [$fh, $ende, $max, $was];
    $neu = @fopen('wafrist://' . $k, 'rb');
    if (!$neu) { unset(AbrufFrist::$warten[$k]); throw new RuntimeException('Der Abruf der ' . $was . ' ließ sich nicht beginnen.'); }
    return $neu;
}

/* Antwort eines Abrufs vollständig lesen – statt file_get_contents, dessen „timeout“ ebenfalls nur je Lesevorgang gilt.
   Nach der Gesamtfrist $ende oder über $max Byte gilt der Abruf als fehlgeschlagen: Rückgabe false wie bei einem nicht
   erreichbaren Dienst, nie ein abgeschnittener Text (der wäre sonst still der neue Stand). */
function abruf_text(string $url, $ctx, float $ende, int $max): string|false
{
    $fh = @fopen($url, 'rb', false, $ctx);
    if (!$fh) return false;
    try {
        $roh = '';
        while (strlen($roh) < $max && !feof($fh)) {
            $rest = $ende - microtime(true);
            if ($rest <= 0) return false;
            @stream_set_timeout($fh, (int)ceil($rest));
            $teil = fread($fh, 65536);
            if ($teil === false || $teil === '' || stream_get_meta_data($fh)['timed_out']) break;
            $roh .= $teil;
        }
        return strlen($roh) >= $max || feof($fh) ? substr($roh, 0, $max) : false;
    } finally {
        fclose($fh);
    }
}

/* Ist eine heruntergeladene Liste plausibel vollständig und darf den bisherigen Bestand ersetzen?
   Eine abgebrochene Übertragung – Verbindungsabbruch, abgeschnittener TLS-Strom, abgelaufenes Lesezeitlimit – sieht für
   fgets/fgetcsv aus wie das Ende der Datei. Die absolute Mindestzahl $min erkennt nur den völligen Ausfall: ein Rest von
   3 Prozent liegt weit darüber und würde die Sperrdatenbank still durch einen Bruchteil ersetzen. Deshalb zusätzlich gegen
   den bisherigen Bestand $alt (null = es gibt keinen): weniger als die Hälfte ist kein neuer Stand, sondern ein Rest.
   Die Hälfte und nicht etwa 0,8: die Quellen schwanken von Monat zu Monat um wenige Prozent, eine enge Schranke würde eine
   echte Schrumpfung der Oberquelle dauerhaft abweisen – sicher (der alte Bestand bleibt aktiv), aber eben dauerhaft und
   ohne jede Aktualisierung. Eine Halbierung hat keine der Quellen je gezeigt; träte sie ein, meldet die Oberfläche den
   Fehlschlag, und der Weg zurück ist, die Datei im Datenordner zu entfernen (dann gilt wieder die mitgelieferte Fassung
   bzw. gar kein Bestand) oder die Schranke bewusst zu senken. */
function abruf_vollstaendig(int $neu, int $min, ?int $alt): bool
{
    return $neu >= $min && ($alt === null || $neu * 2 >= $alt);
}

/* Eine ganze HTTP-Antwort holen, mit einer Gesamtfrist über Verbindungsaufbau, Kopfzeilen und Rumpf.
   Warum nicht fopen('http://…'): dessen „timeout“ gilt nur je Lesevorgang, und die Kopfzeilen liest fopen selbst – eine
   Gegenstelle, die den Kopf Byte für Byte tröpfelt, hält fopen beliebig lange fest (nachgestellt: 42 s trotz timeout 3).
   Deshalb eigene Verbindung, eigene Anfrage, und der Rest durch abruf_frist_strom: dort hat jeder Lesevorgang nur die
   restliche Frist, eine stumme wie eine tröpfelnde Gegenstelle endet also mit ihr.
   Rückgabe ['status' => HTTP-Status (0 = gar keine Antwort), 'roh' => Inhalt, 'fehler' => Kennung]: '' in Ordnung ·
   'netz' nicht erreichbar oder Frist um, bevor ein Status kam · 'halb' Antwort brach ab oder die Frist war um ·
   'gross' mehr als $maxByte Inhalt. Bei jedem Fehler ist 'roh' leer – ein halber Inhalt wird nie ausgewertet, eine
   abgeschnittene Antwort kann so nicht still der neue Stand werden (mit angekündigter Länge und bei „chunked“).
   Hinaus geht nur, was der Aufrufer mitgibt: keine Weiterleitungen, keine Cookies, nur die übergebenen Kopfzeilen. */
const ABRUF_VERBINDEN = 8;    // Sekunden für den Verbindungsaufbau – Teil der Gesamtfrist, nie länger als sie
const ABRUF_KOPF_MAX = 200;   // höchstens so viele Kopfzeilen je Antwort

function abruf_http(string $url, array $kopfzeilen, int $frist, int $maxByte, string $methode = 'GET', ?string $inhalt = null): array
{
    $ende = microtime(true) + $frist;
    $u = parse_url($url);
    $host = (string)($u['host'] ?? '');
    $tls = ($u['scheme'] ?? '') === 'https';
    $fehlschlag = fn(int $status, string $kennung) => ['status' => $status, 'roh' => '', 'fehler' => $kennung];
    if ($host === '' || (!$tls && ($u['scheme'] ?? '') !== 'http')) return $fehlschlag(0, 'netz');
    $port = (int)($u['port'] ?? ($tls ? 443 : 80));
    $ctx = stream_context_create(['ssl' => ['verify_peer' => true, 'verify_peer_name' => true, 'peer_name' => $host]]);
    $roh = @stream_socket_client(($tls ? 'tls' : 'tcp') . '://' . $host . ':' . $port, $nr, $txt,
        (float)max(1, min(ABRUF_VERBINDEN, $frist)), STREAM_CLIENT_CONNECT, $ctx);
    if (!$roh) return $fehlschlag(0, 'netz');
    $status = 0;
    try {
        $anfrage = $methode . ' ' . (($u['path'] ?? '') === '' ? '/' : $u['path']) . (isset($u['query']) ? '?' . $u['query'] : '')
            . " HTTP/1.1\r\nHost: " . $host . ($port === ($tls ? 443 : 80) ? '' : ':' . $port) . "\r\nConnection: close\r\n";
        foreach ($kopfzeilen as $z) if (!preg_match('/[\r\n]/', (string)$z)) $anfrage .= $z . "\r\n";   // keine eingeschmuggelte Zeile
        if ($inhalt !== null) $anfrage .= 'Content-Length: ' . strlen($inhalt) . "\r\n";
        $anfrage .= "\r\n" . ($inhalt ?? '');
        @stream_set_timeout($roh, max(1, (int)ceil($ende - microtime(true))));
        if (fwrite($roh, $anfrage) !== strlen($anfrage)) return $fehlschlag(0, 'netz');
        // Mengengrenze des Stroms nur als Rückhalt (Kopfzeilen und Stückrahmen kommen zur Nutzlast); genau prüft der Rumpf unten
        $s = abruf_frist_strom($roh, $ende, $maxByte + (1 << 20), 'Antwort');
        try {
            /* Kopf einer Antwort lesen: Kopfzeilen klein geschrieben, oder null (kein Status, Abbruch, zu viele Zeilen) */
            $kopf_lesen = function () use ($s, &$status): ?array {
                $zeile = fgets($s);
                if (!is_string($zeile) || !preg_match('#^HTTP/\d\.\d +(\d{3})#', $zeile, $m)) return null;
                $status = (int)$m[1];
                $kopf = [];
                for ($i = 0; $i < ABRUF_KOPF_MAX; $i++) {
                    $z = fgets($s);
                    if (!is_string($z)) return null;
                    $z = rtrim($z, "\r\n");
                    if ($z === '') return $kopf;
                    $p = strpos($z, ':');
                    if ($p > 0) $kopf[strtolower(trim(substr($z, 0, $p)))] = trim(substr($z, $p + 1));
                }
                return null;
            };
            do { $kopf = $kopf_lesen(); } while ($kopf !== null && $status < 200);   // 1xx-Zwischenantwort überspringen
            if ($kopf === null) return $fehlschlag($status, $status ? 'halb' : 'netz');
            $laenge = preg_match('/^\d{1,18}$/', (string)($kopf['content-length'] ?? '')) ? (int)$kopf['content-length'] : null;
            if (stripos((string)($kopf['transfer-encoding'] ?? ''), 'chunked') !== false) {
                // stückweise Antwort ohne angekündigte Länge: Stück für Stück bis zum Schlussstück 0 – fehlt es, war die Antwort halb
                $text = '';
                while (true) {
                    $z = fgets($s);
                    if (!is_string($z) || !preg_match('/^([0-9a-fA-F]{1,15})/', $z, $m)) return $fehlschlag($status, 'halb');
                    $n = (int)hexdec($m[1]);
                    if ($n === 0) break;
                    if (strlen($text) + $n > $maxByte) return $fehlschlag($status, 'gross');
                    $stueck = abruf_lesen($s, $n);
                    if (strlen($stueck) !== $n) return $fehlschlag($status, 'halb');
                    $text .= $stueck;
                    if (fgets($s) === false) return $fehlschlag($status, 'halb');   // Zeilenende nach dem Stück
                }
            } elseif ($laenge !== null) {
                // angekündigte Länge: genau so viele Byte – so wartet der Abruf auch nicht auf das Ende einer offen gehaltenen Verbindung
                if ($laenge > $maxByte) return $fehlschlag($status, 'gross');
                $text = abruf_lesen($s, $laenge);
                if (strlen($text) !== $laenge) return $fehlschlag($status, 'halb');
            } else {
                $text = abruf_lesen($s, $maxByte + 1);   // ohne Angabe endet der Rumpf mit der Verbindung
                if (strlen($text) > $maxByte) return $fehlschlag($status, 'gross');
            }
            return ['status' => $status, 'roh' => $text, 'fehler' => ''];
        } finally {
            fclose($s);
        }
    } catch (RuntimeException $e) {   // Gesamtfrist oder Rückhalt-Mengengrenze aus abruf_frist_strom
        return $fehlschlag($status, $status ? 'halb' : 'netz');
    } finally {
        fclose($roh);
    }
}

/* Höchstens $n Byte aus einem Strom lesen; weniger heißt: die Gegenstelle hat vorher aufgehört (oder die Frist lief ab) */
function abruf_lesen($s, int $n): string
{
    $aus = '';
    while (strlen($aus) < $n && !feof($s)) {
        $teil = fread($s, min(65536, $n - strlen($aus)));
        if (!is_string($teil) || $teil === '') break;
        $aus .= $teil;
    }
    return $aus;
}
