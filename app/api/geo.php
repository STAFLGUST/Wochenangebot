<?php
/*
 * Länderzuordnung von IP-Adressen (für Ländersperren)
 * Datenquelle: ip-location-db „geo-whois-asn-country“ (CC0 / Public Domain)
 *
 * Binärformat laender.dat.php (beginnt mit einer PHP-Sperre, damit die Datei
 * im Browser nicht abrufbar ist):
 *   GEO_GUARD | "GEO2" | n4 (uint32) | n6 (uint32) | Stand (10 Byte, JJJJ-MM-TT)
 *   n4 × [start uint32 | ende uint32 | Land 2 Byte]          (IPv4)
 *   n6 × [start 8 Byte | ende 8 Byte | Land 2 Byte]           (IPv6, erste 64 Bit)
 */
declare(strict_types=1);
if (realpath((string)($_SERVER['SCRIPT_FILENAME'] ?? '')) === __FILE__) { http_response_code(404); exit; }

const GEO_GUARD = "<?php http_response_code(404); exit; __halt_compiler();";
const GEO_HEAD = 22;
const GEO_OFF = 55 + GEO_HEAD; // strlen(GEO_GUARD) + Kopf
const GEO_PKG = '@ip-location-db/geo-whois-asn-country';

/* aktuelle Datenbank: heruntergeladenes Update (Datenordner) vor mitgelieferter Fassung */
function geo_file(): ?string
{
    global $DATA;
    foreach ([($DATA ?? '') . '/geo/laender.dat.php', __DIR__ . '/geo/laender.dat.php'] as $f) if (is_file($f) && filesize($f) > GEO_OFF) return $f;
    return null;
}
function geo_info(): ?array
{
    $f = geo_file();
    if (!$f) return null;
    $h = substr((string)file_get_contents($f, false, null, 0, GEO_OFF), strlen(GEO_GUARD));
    if (substr($h, 0, 4) !== 'GEO2') return null;
    $n = unpack('N2', substr($h, 4, 8));
    return ['date' => substr($h, 12, 10), 'v4' => $n[1], 'v6' => $n[2], 'updated' => strpos($f, __DIR__) !== 0];
}
/* ISO-Ländercode einer IP-Adresse oder null (privat/unbekannt) */
function geo_country(string $ip): ?string
{
    static $cache = [];
    if (isset($cache[$ip])) return $cache[$ip];
    if (filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false) return $cache[$ip] = null;
    $f = geo_file();
    if (!$f) return null;
    $fh = fopen($f, 'rb');
    if (!$fh) return null;
    $h = substr((string)fread($fh, GEO_OFF), strlen(GEO_GUARD));
    if (substr($h, 0, 4) !== 'GEO2') { fclose($fh); return null; }
    $n = unpack('N2', substr($h, 4, 8)); $n4 = $n[1]; $n6 = $n[2];
    $bin = inet_pton($ip);
    if (strlen($bin) === 16 && substr($bin, 0, 12) === "\0\0\0\0\0\0\0\0\0\0\xff\xff") $bin = substr($bin, 12); // IPv4 in IPv6
    $res = null;
    if (strlen($bin) === 4) {
        $key = unpack('N', $bin)[1];
        $lo = 0; $hi = $n4 - 1;
        while ($lo <= $hi) {
            $mid = ($lo + $hi) >> 1;
            fseek($fh, GEO_OFF + $mid * 10);
            $r = fread($fh, 10);
            $s = unpack('N2', $r);
            if ($key < $s[1]) $hi = $mid - 1; elseif ($key > $s[2]) $lo = $mid + 1; else { $res = substr($r, 8, 2); break; }
        }
    } else {
        $key = substr($bin, 0, 8);
        $base = GEO_OFF + $n4 * 10;
        $lo = 0; $hi = $n6 - 1;
        while ($lo <= $hi) {
            $mid = ($lo + $hi) >> 1;
            fseek($fh, $base + $mid * 18);
            $r = fread($fh, 18);
            if (strcmp($key, substr($r, 0, 8)) < 0) $hi = $mid - 1; elseif (strcmp($key, substr($r, 8, 8)) > 0) $lo = $mid + 1; else { $res = substr($r, 16, 2); break; }
        }
    }
    fclose($fh);
    return $cache[$ip] = ($res !== null && preg_match('/^[A-Z]{2}$/', $res) ? $res : null);
}
/* 8-Byte-Wert + 1 (für zusammenhängende Bereiche) */
function geo_inc8(string $b): string
{
    for ($i = 7; $i >= 0; $i--) { $c = ord($b[$i]) + 1; $b[$i] = chr($c & 0xff); if ($c < 256) break; }
    return $b;
}
/* CSV (start,ende,Land) → Binärdatei; benachbarte Bereiche desselben Landes werden zusammengefasst */
function geo_build($in4, $in6, string $out, string $date): array
{
    $v4 = ''; $n4 = 0; $prev = null;
    while (($line = fgets($in4)) !== false) {
        $p = explode(',', trim($line));
        if (count($p) < 3 || !preg_match('/^[A-Z]{2}$/', $p[2])) continue;
        $a = @inet_pton($p[0]); $b = @inet_pton($p[1]);
        if ($a === false || $b === false || strlen($a) !== 4) continue;
        $s = unpack('N', $a)[1]; $e = unpack('N', $b)[1];
        if ($prev && $prev[2] === $p[2] && $s === $prev[1] + 1) { $prev[1] = $e; continue; }
        if ($prev) { $v4 .= pack('NN', $prev[0], $prev[1]) . $prev[2]; $n4++; }
        $prev = [$s, $e, $p[2]];
    }
    if ($prev) { $v4 .= pack('NN', $prev[0], $prev[1]) . $prev[2]; $n4++; }
    $v6 = ''; $n6 = 0; $prev = null;
    while (($line = fgets($in6)) !== false) {
        $p = explode(',', trim($line));
        if (count($p) < 3 || !preg_match('/^[A-Z]{2}$/', $p[2])) continue;
        $a = @inet_pton($p[0]); $b = @inet_pton($p[1]);
        if ($a === false || $b === false || strlen($a) !== 16) continue;
        $s = substr($a, 0, 8); $e = substr($b, 0, 8);
        if ($prev && $prev[2] === $p[2] && strcmp($s, geo_inc8($prev[1])) <= 0) { if (strcmp($e, $prev[1]) > 0) $prev[1] = $e; continue; }
        if ($prev && strcmp($s, $prev[1]) <= 0) $s = geo_inc8($prev[1]);           // Überlappung durch 64-Bit-Kürzung
        if ($prev && strcmp($s, $e) > 0) continue;
        if ($prev) { $v6 .= $prev[0] . $prev[1] . $prev[2]; $n6++; }
        $prev = [$s, $e, $p[2]];
    }
    if ($prev) { $v6 .= $prev[0] . $prev[1] . $prev[2]; $n6++; }
    if ($n4 < 10000 || $n6 < 1000) throw new RuntimeException('Die Länderdaten sind unvollständig.');
    $tmp = $out . '.' . bin2hex(random_bytes(4)) . '.tmp';
    if (!is_dir(dirname($out))) @mkdir(dirname($out), 0775, true);
    file_put_contents($tmp, GEO_GUARD . 'GEO2' . pack('NN', $n4, $n6) . substr(str_pad($date, 10), 0, 10) . $v4 . $v6);
    rename($tmp, $out);
    return ['v4' => $n4, 'v6' => $n6];
}

/* neueste Länderdaten herunterladen und in den Datenordner schreiben */
function geo_download(string $out): array
{
    $ctx = stream_context_create(['http' => ['timeout' => 60, 'user_agent' => 'Wochenangebot', 'follow_location' => 1], 'ssl' => ['verify_peer' => true]]);
    $ver = '2';
    $meta = @file_get_contents('https://data.jsdelivr.com/v1/packages/npm/' . GEO_PKG . '/resolved?specifier=2', false, $ctx);
    $j = $meta ? json_decode($meta, true) : null;
    if (is_array($j) && preg_match('/^\d+\.\d+\.\d+$/', (string)($j['version'] ?? ''))) $ver = $j['version'];
    $date = preg_match('/\.(\d{4})(\d{2})(\d{2})\d*$/', $ver, $m) ? "$m[1]-$m[2]-$m[3]" : gmdate('Y-m-d');
    $base = 'https://cdn.jsdelivr.net/npm/' . GEO_PKG . '@' . $ver . '/geo-whois-asn-country-';
    $in4 = @fopen($base . 'ipv4.csv', 'rb', false, $ctx);
    $in6 = $in4 ? @fopen($base . 'ipv6.csv', 'rb', false, $ctx) : false;
    if (!$in4 || !$in6) throw new RuntimeException('Die Länderdaten konnten nicht heruntergeladen werden.');
    try { $r = geo_build($in4, $in6, $out, $date); } finally { fclose($in4); fclose($in6); }
    return $r + ['date' => $date, 'version' => $ver];
}

/* ISO-Ländercodes für die Auswahl (Namen liefert der Browser auf Deutsch) */
const GEO_COUNTRIES = ['AD','AE','AF','AG','AI','AL','AM','AO','AQ','AR','AS','AT','AU','AW','AX','AZ','BA','BB','BD','BE','BF','BG','BH','BI','BJ','BL','BM','BN','BO','BQ','BR','BS','BT','BV','BW','BY','BZ','CA','CC','CD','CF','CG','CH','CI','CK','CL','CM','CN','CO','CR','CU','CV','CW','CX','CY','CZ','DE','DJ','DK','DM','DO','DZ','EC','EE','EG','EH','ER','ES','ET','FI','FJ','FK','FM','FO','FR','GA','GB','GD','GE','GF','GG','GH','GI','GL','GM','GN','GP','GQ','GR','GS','GT','GU','GW','GY','HK','HM','HN','HR','HT','HU','ID','IE','IL','IM','IN','IO','IQ','IR','IS','IT','JE','JM','JO','JP','KE','KG','KH','KI','KM','KN','KP','KR','KW','KY','KZ','LA','LB','LC','LI','LK','LR','LS','LT','LU','LV','LY','MA','MC','MD','ME','MF','MG','MH','MK','ML','MM','MN','MO','MP','MQ','MR','MS','MT','MU','MV','MW','MX','MY','MZ','NA','NC','NE','NF','NG','NI','NL','NO','NP','NR','NU','NZ','OM','PA','PE','PF','PG','PH','PK','PL','PM','PN','PR','PS','PT','PW','PY','QA','RE','RO','RS','RU','RW','SA','SB','SC','SD','SE','SG','SH','SI','SJ','SK','SL','SM','SN','SO','SR','SS','ST','SV','SX','SY','SZ','TC','TD','TF','TG','TH','TJ','TK','TL','TM','TN','TO','TR','TT','TV','TW','TZ','UA','UG','UM','US','UY','UZ','VA','VC','VE','VG','VI','VN','VU','WF','WS','XK','YE','YT','ZA','ZM','ZW'];
