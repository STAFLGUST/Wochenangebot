<?php
/*
 * Ungefährer Ort (Stadt) einer IP-Adresse – für die Karte der Kunden-Anmeldungen (Auswertung)
 * Datenquelle: DB-IP „IP to City Lite“ (CC BY 4.0, https://db-ip.com), monatlich aktualisiert.
 * Namensnennung: „IP Geolocation by DB-IP“ (wird in der Auswertung angezeigt).
 *
 * Binärformat orte.dat.php (im Datenordner; beginnt mit einer PHP-Sperre, damit die Datei im Browser nicht abrufbar ist):
 *   ORT_GUARD | "ORT1" | n4 (uint32) | n6 (uint32) | nOrte (uint32) | Stand (10 Byte, JJJJ-MM-TT)
 *   n4 × [start uint32 | ende uint32 | Ort uint32]                 (IPv4)
 *   n6 × [start 8 Byte | ende 8 Byte | Ort uint32]                 (IPv6, erste 64 Bit)
 *   nOrte × [Breite int32 ×10⁴ | Länge int32 ×10⁴ | Land 2 Byte | Name 54 Byte „Stadt|Region“, mit \0 aufgefüllt]
 */
declare(strict_types=1);
if (realpath((string)($_SERVER['SCRIPT_FILENAME'] ?? '')) === __FILE__) { http_response_code(404); exit; }

const ORT_GUARD = "<?php http_response_code(404); exit; __halt_compiler();";
const ORT_HEAD = 26;
const ORT_OFF = 55 + ORT_HEAD;           // strlen(ORT_GUARD) + Kopf
const ORT_REC = 64;                      // Länge eines Ort-Eintrags
const ORT_URL = 'https://download.db-ip.com/free/dbip-city-lite-%s.csv.gz';

function ort_file(): ?string
{
    global $DATA;
    $f = ($DATA ?? '') . '/geo/orte.dat.php';
    return is_file($f) && filesize($f) > ORT_OFF ? $f : null;
}
function ort_head($fh): ?array
{
    $h = substr((string)fread($fh, ORT_OFF), strlen(ORT_GUARD));
    if (substr($h, 0, 4) !== 'ORT1') return null;
    $n = unpack('N3', substr($h, 4, 12));
    return ['v4' => $n[1], 'v6' => $n[2], 'orte' => $n[3], 'date' => rtrim(substr($h, 16, 10))];
}
function ort_info(): ?array
{
    $f = ort_file();
    if (!$f || !($fh = fopen($f, 'rb'))) return null;
    $h = ort_head($fh);
    fclose($fh);
    return $h ? $h + ['size' => filesize($f)] : null;
}
/* Ort einer IP-Adresse: ['city','region','cc','lat','lon'] oder null (privat/unbekannt) */
function ort_lookup(string $ip): ?array
{
    if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false) return null;
    $f = ort_file();
    if (!$f || !($fh = fopen($f, 'rb'))) return null;
    try {
        $h = ort_head($fh);
        if (!$h) return null;
        $bin = inet_pton($ip);
        if (strlen($bin) === 16 && substr($bin, 0, 12) === "\0\0\0\0\0\0\0\0\0\0\xff\xff") $bin = substr($bin, 12);
        $loc = null;
        if (strlen($bin) === 4) {
            $key = unpack('N', $bin)[1];
            $lo = 0; $hi = $h['v4'] - 1;
            while ($lo <= $hi) {
                $mid = ($lo + $hi) >> 1;
                fseek($fh, ORT_OFF + $mid * 12);
                $s = unpack('N3', (string)fread($fh, 12));
                if ($key < $s[1]) $hi = $mid - 1; elseif ($key > $s[2]) $lo = $mid + 1; else { $loc = $s[3]; break; }
            }
        } else {
            $key = substr($bin, 0, 8);
            $base = ORT_OFF + $h['v4'] * 12;
            $lo = 0; $hi = $h['v6'] - 1;
            while ($lo <= $hi) {
                $mid = ($lo + $hi) >> 1;
                fseek($fh, $base + $mid * 20);
                $r = (string)fread($fh, 20);
                if (strcmp($key, substr($r, 0, 8)) < 0) $hi = $mid - 1; elseif (strcmp($key, substr($r, 8, 8)) > 0) $lo = $mid + 1; else { $loc = unpack('N', substr($r, 16, 4))[1]; break; }
            }
        }
        if ($loc === null || $loc >= $h['orte']) return null;
        fseek($fh, ORT_OFF + $h['v4'] * 12 + $h['v6'] * 20 + $loc * ORT_REC);
        $r = (string)fread($fh, ORT_REC);
        if (strlen($r) !== ORT_REC) return null;
        $p = unpack('Nlat/Nlon', substr($r, 0, 8));
        $s32 = function (int $v): int { return $v >= 0x80000000 ? $v - 0x100000000 : $v; };
        $cc = substr($r, 8, 2);
        if (!preg_match('/^[A-Z]{2}$/', $cc) || $cc === 'ZZ') return null;
        [$city, $region] = array_pad(explode('|', rtrim(substr($r, 10), "\0"), 2), 2, '');
        return ['city' => $city, 'region' => $region, 'cc' => $cc, 'lat' => $s32($p['lat']) / 10000, 'lon' => $s32($p['lon']) / 10000];
    } finally {
        fclose($fh);
    }
}
/* gekürzt auf höchstens $n Byte, ohne ein UTF-8-Zeichen zu zerschneiden */
function ort_cut(string $s, int $n): string
{
    if (strlen($s) <= $n) return $s;
    return mb_strcut($s, 0, $n, 'UTF-8');
}
/* CSV (start,ende,Kontinent,Land,Region,Stadt,Breite,Länge) → Binärdatei; benachbarte Bereiche desselben Orts werden zusammengefasst */
function ort_build($in, string $out, string $date): array
{
    $tmp = $out . '.' . bin2hex(random_bytes(4)) . '.tmp';
    if (!is_dir(dirname($out))) @mkdir(dirname($out), 0775, true);
    $fo = fopen($tmp, 'wb');
    $fl = fopen('php://temp/maxmemory:' . (4 << 20), 'w+b');   // Orte: erst sammeln, am Ende anhängen
    if (!$fo || !$fl) throw new RuntimeException('Datei nicht beschreibbar');
    try {
        fwrite($fo, str_repeat("\0", ORT_OFF));
        $locs = []; $nl = 0; $n4 = 0; $n6 = 0; $prev = null; $v6 = false; $buf = '';
        $flush = function () use (&$prev, &$buf, &$n4, &$n6, &$v6) {
            if (!$prev) return;
            if ($v6) { $buf .= $prev[0] . $prev[1] . pack('N', $prev[2]); $n6++; }
            else { $buf .= pack('NNN', $prev[0], $prev[1], $prev[2]); $n4++; }
        };
        while (($row = fgetcsv($in, 0, ',', '"', '')) !== false) {
            if (count($row) < 8) continue;
            $cc = $row[3];
            if (!preg_match('/^[A-Z]{2}$/', $cc)) continue;
            $a = @inet_pton($row[0]); $b = @inet_pton($row[1]);
            if ($a === false || $b === false || strlen($a) !== strlen($b)) continue;
            $is6 = strlen($a) === 16;
            if ($is6 && !$v6) { $flush(); $prev = null; $v6 = true; }
            elseif (!$is6 && $v6) continue;   // IPv4 nach IPv6: Quelle unerwartet sortiert
            $lat = (int)round((float)$row[6] * 10000); $lon = (int)round((float)$row[7] * 10000);
            $key = $cc . '|' . $row[4] . '|' . $row[5] . '|' . $lat . '|' . $lon;
            if (!isset($locs[$key])) {
                $locs[$key] = $nl++;
                fwrite($fl, pack('NN', $lat & 0xffffffff, $lon & 0xffffffff) . $cc . str_pad(ort_cut($row[5] . '|' . $row[4], 54), 54, "\0"));
            }
            $loc = $locs[$key];
            if (!$is6) {
                $s = unpack('N', $a)[1]; $e = unpack('N', $b)[1];
                if ($prev && $prev[2] === $loc && $s === $prev[1] + 1) { $prev[1] = $e; continue; }
                $flush(); $prev = [$s, $e, $loc];
            } else {
                $s = substr($a, 0, 8); $e = substr($b, 0, 8);
                if ($prev && $prev[2] === $loc && strcmp($s, geo_inc8($prev[1])) <= 0) { if (strcmp($e, $prev[1]) > 0) $prev[1] = $e; continue; }
                if ($prev && strcmp($s, $prev[1]) <= 0) $s = geo_inc8($prev[1]);   // Überlappung durch 64-Bit-Kürzung
                if ($prev && strcmp($s, $e) > 0) continue;
                $flush(); $prev = [$s, $e, $loc];
            }
            if (strlen($buf) > 1 << 20) { fwrite($fo, $buf); $buf = ''; }
        }
        $flush();
        fwrite($fo, $buf); $buf = '';
        unset($locs);
        if ($n4 < 100000 || $n6 < 10000) throw new RuntimeException('Die Ortsdaten sind unvollständig.');
        rewind($fl);
        stream_copy_to_stream($fl, $fo);
        rewind($fo);
        fwrite($fo, ORT_GUARD . 'ORT1' . pack('NNN', $n4, $n6, $nl) . substr(str_pad($date, 10), 0, 10));
        fclose($fo); $fo = null;
        rename($tmp, $out);
        return ['v4' => $n4, 'v6' => $n6, 'orte' => $nl];
    } finally {
        if ($fo) fclose($fo);
        fclose($fl);
        if (is_file($tmp)) @unlink($tmp);
    }
}
/* aktuelle Ortsdaten herunterladen (dieser oder letzter Monat) und in den Datenordner schreiben */
function ort_download(string $out): array
{
    $ctx = stream_context_create(['http' => ['timeout' => 120, 'user_agent' => 'Wochenangebot', 'follow_location' => 1], 'ssl' => ['verify_peer' => true]]);
    foreach ([gmdate('Y-m'), gmdate('Y-m', strtotime('first day of last month'))] as $m) {
        $in = @fopen('compress.zlib://' . sprintf(getenv('WA_ORT_URL') ?: ORT_URL, $m), 'rb', false, $ctx);   // WA_ORT_URL nur in den Tests
        if (!$in) continue;
        try { return ort_build($in, $out, $m . '-01') + ['date' => $m . '-01']; } finally { fclose($in); }
    }
    throw new RuntimeException('Die Ortsdaten konnten nicht heruntergeladen werden.');
}
