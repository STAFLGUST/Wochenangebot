<?php
/* ==========================================================================
   Schutzzentrale: Firewall (Angriffsmuster), Sperrliste (von Hand, automatisch, Bedrohungsliste), Fallen für
   Angriffswerkzeuge, Fehlerbremse und Live-Verkehr. Läuft vor jeder API-Aktion (fw_guard in api/index.php).

   Dokumente: „firewall“ (Einstellungen), „sperrliste“ ({manuell: [...], auto: {schlüssel: {...}}}),
   „bedrohungsliste“ (Netze aus der Spamhaus-DROP-Liste), „fw_zaehler“ (Treffer/Fehler je Adresse, kurzlebig),
   „verkehr“ (letzte Anfragen, Ringpuffer). Geschrieben wird nur bei Auffälligkeiten (Treffer, Sperre, Fehler,
   Anmeldung) oder während eines vom Administrator gestarteten Mitschnitts – normale Anfragen kosten nur Lesezugriffe.
   ========================================================================== */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const FW_DEFAULTS = ['waf' => 'sperren', 'autoSperre' => true, 'treffer' => 5, 'sperrMinuten' => 60, 'fehlerLimit' => 30,
                     'feed' => false, 'mitschnittBis' => 0, 'erlaubt' => []];
/* Nicht exportiert/importiert: Listen und Schalter, die vom einzelnen Server abhängen (Adressen, Länder) */
const FW_NICHT_UEBERTRAGEN = ['ipEnabled' => 1, 'adminIps' => 1, 'geoEnabled' => 1, 'geoMode' => 1, 'geoCountries' => 1, 'geoScope' => 1];
const FW_WAF_MODI = ['aus' => 'aus', 'protokoll' => 'nur protokollieren', 'sperren' => 'Anfrage abweisen'];
const FW_SPERR_MINUTEN = [10, 60, 360, 1440, 10080];
const FW_VERKEHR_MAX = 500;
const FW_FENSTER = 600;          // Treffer zählen 10 Minuten
const FW_FEHLER_FENSTER = 300;   // Fehlerbremse: 5 Minuten
/* Bedrohungsliste: Spamhaus DROP – von Kriminellen übernommene bzw. betriebene Netze („Don't Route Or Peer“) */
const FW_FEED_QUELLEN = ['https://www.spamhaus.org/drop/drop.txt', 'https://www.spamhaus.org/drop/dropv6.txt'];

/* Angriffsmuster: [Gruppe, Muster]. Geprüft werden Abfrageparameter und – ohne Mitarbeiter-Anmeldung – die Werte im
   JSON-Inhalt. Bewusst eindeutige Muster, damit normale Eingaben (Bemerkungen, Firmennamen) nicht abgewiesen werden. */
const FW_MUSTER = [
    ['SQL-Einschleusung', '/\bunion\b[\s\/*()]+(?:all[\s\/*]+)?select\b/i'],
    ['SQL-Einschleusung', '/\b(?:sleep|benchmark|pg_sleep|waitfor\s+delay)\s*\(\s*[\'"\d]/i'],
    ['SQL-Einschleusung', '/[\'"]\s*(?:or|and)\s+[\'"]?\d+[\'"]?\s*=\s*[\'"]?\d+/i'],
    ['SQL-Einschleusung', '/\binformation_schema\b|\bload_file\s*\(|\binto\s+(?:out|dump)file\b/i'],
    ['SQL-Einschleusung', '/;\s*(?:drop|truncate|alter)\s+table\b/i'],
    ['Skript-Einschleusung', '/<\s*script\b|<\s*iframe\b|<\s*object\b|<\s*embed\b/i'],
    ['Skript-Einschleusung', '/\bjavascript\s*:|\bvbscript\s*:/i'],
    ['Skript-Einschleusung', '/<[^>]+\bon(?:error|load|mouseover|focus|toggle|animationstart)\s*=/i'],
    ['Pfadmanipulation', '/(?:\.\.[\/\\\\]){2,}|\/etc\/(?:passwd|shadow|hosts)\b|\bproc\/self\/environ\b|\bwin\.ini\b/i'],
    ['Code-Ausführung', '/\$\{\s*jndi\s*:|\$\{\s*(?:env|sys|lower|upper)\s*:/i'],
    ['Code-Ausführung', '/\b(?:php|phar|expect|zip|glob):\/\//i'],
    ['Code-Ausführung', '/<\?php|\b(?:system|exec|passthru|shell_exec|popen|proc_open|assert)\s*\(\s*[\'"$]/i'],
    ['Code-Ausführung', '/\b(?:base64_decode|gzinflate|str_rot13)\s*\(|\beval\s*\(\s*(?:\$|base64|gz)/i'],
    ['Kopfzeilen-Einschleusung', '/[\r\n]\s*(?:set-cookie|location|content-type)\s*:/i'],
];
/* Bekannte Angriffs- und Scan-Werkzeuge (User-Agent) */
const FW_WERKZEUGE = '/\b(?:sqlmap|nikto|nmap|masscan|acunetix|nessus|openvas|wpscan|dirbuster|gobuster|feroxbuster|ffuf|zgrab|nuclei|havij|w3af|whatweb|jaeles|xsstrike|commix)\b/i';

function fw(): array
{
    global $FWS;
    if ($FWS === null) $FWS = array_merge(FW_DEFAULTS, store_read('firewall') ?? []);
    return $FWS;
}

/* Nie sperren: interne Adressen, freigegebene Adressen des Eingabebereichs und die Liste „nie sperren“ */
function fw_erlaubt(string $ip): bool
{
    if ($ip === '' || filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false) return true;
    $F = fw();
    if ($F['erlaubt'] && ip_allowed($ip, $F['erlaubt'])) return true;
    $S = sec();
    return !empty($S['adminIps']) && ip_allowed($ip, $S['adminIps']);
}
/* Angemeldeter Mitarbeiter? Nur nachsehen, wenn eine Sitzung mitkommt – sonst würde für jeden anonymen Besucher eine
   Sitzung (Cookie, Datei) angelegt */
function fw_mitarbeiter(): bool
{
    global $ME;
    if ($ME) return true;
    if (empty($_COOKIE[sitzung_cookie_name()]) && empty($_SERVER['HTTP_X_WA_SITZUNG'])) return false;
    return (bool)current_user();
}
/* Von einer fremden Seite ausgelöst (z. B. <img src="…/wp-login.php"> oder ein Link)? Browser senden Sec-Fetch-Site;
   solche Anfragen werden abgewiesen, zählen aber nicht als Treffer – sonst könnte jede Webseite die Adresse ihrer
   Besucher (z. B. das Büro) sperren lassen. Angriffswerkzeuge senden diese Kopfzeile nicht. */
function fw_fremd(): bool
{
    $site = strtolower((string)($_SERVER['HTTP_SEC_FETCH_SITE'] ?? ''));
    return $site !== '' && $site !== 'same-origin' && $site !== 'none';
}
/* Schlüssel einer Adresse: IPv4 einzeln, IPv6 je /64 (wie bei den Anmeldeversuchen) */
function fw_key(string $ip): string
{
    $bin = @inet_pton($ip);
    if ($bin !== false && strlen($bin) === 16) return inet_ntop(substr($bin, 0, 8) . str_repeat("\0", 8)) . '/64';
    return $ip;
}
function fw_sperrliste(): array
{
    $d = store_read('sperrliste') ?? [];
    return ['manuell' => array_values((array)($d['manuell'] ?? [])), 'auto' => (array)($d['auto'] ?? []), 'meldung' => (array)($d['meldung'] ?? [])];
}
/* Gesperrt? Liefert den Grund oder null */
function fw_gesperrt(string $ip): ?string
{
    $now = time();
    $L = fw_sperrliste();
    foreach ($L['manuell'] as $e) if ((!(int)($e['bis'] ?? 0) || (int)$e['bis'] > $now) && ip_in($ip, (string)$e['ip'])) return 'von Hand gesperrt' . (($e['grund'] ?? '') !== '' ? ' (' . $e['grund'] . ')' : '');
    $a = $L['auto'][fw_key($ip)] ?? null;
    if ($a && (int)($a['bis'] ?? 0) > $now) return 'automatisch gesperrt (' . ($a['grund'] ?? 'Angriff') . ')';
    if (fw()['feed'] && fw_feed_trifft($ip)) return 'Bedrohungsliste (Spamhaus DROP)';
    return null;
}

/* Prüftext einer Anfrage: Abfrage (dekodiert) und – ohne Mitarbeiter-Anmeldung – alle Zeichenketten im JSON-Inhalt */
const FW_GEHEIM = ['password', 'current', 'password2', 'pw', 'code', 'token'];   // Passwörter/Codes nie prüfen (beliebige Zeichen erlaubt)
function fw_werte($v, array &$out, int $tiefe = 0): void
{
    if ($tiefe > 8 || count($out) > 2000) return;
    if (is_string($v)) { $out[] = $v; return; }
    if (is_array($v)) foreach ($v as $k => $x) {
        if (is_string($k)) { if (in_array(strtolower($k), FW_GEHEIM, true)) continue; $out[] = $k; }
        fw_werte($x, $out, $tiefe + 1);
    }
}
function fw_pruefen(string $text): ?string
{
    if ($text === '') return null;
    foreach (FW_MUSTER as [$gruppe, $re]) {
        $r = preg_match($re, $text);
        if ($r === 1) return $gruppe;
        if ($r === false) return $gruppe . ' (Prüfung überlastet)';   // nicht prüfbar (z. B. extrem verschachtelt) = verdächtig
    }
    return null;
}
function fw_angriff(): ?string
{
    $ua = (string)($_SERVER['HTTP_USER_AGENT'] ?? '');
    if ($ua !== '' && preg_match(FW_WERKZEUGE, $ua)) return 'Angriffswerkzeug';
    $q = (string)($_SERVER['QUERY_STRING'] ?? '');
    $teile = [$q, rawurldecode($q), rawurldecode(rawurldecode($q))];
    if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'POST' && !fw_mitarbeiter()) {
        $raw = (string)file_get_contents('php://input', false, null, 0, 262144);
        $j = json_decode($raw, true);
        if (is_array($j)) { $w = []; fw_werte($j, $w); $teile[] = implode("\n", $w); }
        else $teile[] = $raw;
    }
    return fw_pruefen(implode("\n", $teile));
}

/* Zähler (Treffer / Fehler) je Adresse – liefert die Anzahl im Zeitfenster */
function fw_zaehlen(string $ip, string $art, int $fenster): int
{
    return (int)with_lock('fw_zaehler', function () use ($ip, $art, $fenster) {
        $now = time();
        $z = store_read('fw_zaehler') ?? [];
        foreach ($z as $k => $v) if ((int)($v['t'] ?? 0) < $now - 3600) unset($z[$k]);
        if (count($z) > 5000) { uasort($z, fn($a, $b) => (int)($b['t'] ?? 0) <=> (int)($a['t'] ?? 0)); $z = array_slice($z, 0, 4000, true); }   // älteste zuerst weg
        $k = fw_key($ip);
        $e = $z[$k] ?? ['t' => $now];
        $l = array_values(array_filter((array)($e[$art] ?? []), fn($t) => (int)$t > $now - $fenster));
        $l[] = $now;
        $F = fw();
        $e[$art] = array_slice($l, -(max((int)$F['treffer'], (int)$F['fehlerLimit']) + 5));
        $e['t'] = $now;
        $z[$k] = $e;
        store_write('fw_zaehler', $z);
        return count($l);
    });
}
/* Automatisch sperren (Protokoll → Benachrichtigung „Sicherheitsereignisse“) */
function fw_auto_sperren(string $ip, string $grund): void
{
    $F = fw();
    if (!$F['autoSperre'] || fw_erlaubt($ip)) return;
    $min = (int)$F['sperrMinuten'];
    $melden = with_lock('sperrliste', function () use ($ip, $grund, $min) {
        $L = fw_sperrliste();
        $now = time();
        $k = fw_key($ip);
        if (isset($L['auto'][$k]) && (int)$L['auto'][$k]['bis'] > $now) return null;   // schon gesperrt: nichts schreiben
        foreach ($L['auto'] as $kk => $a) if ((int)($a['bis'] ?? 0) < $now - 86400) unset($L['auto'][$kk]);
        $L['auto'][$k] = ['ip' => $k, 'grund' => mb_substr($grund, 0, 80), 'bis' => $now + 60 * $min, 'n' => (int)($L['auto'][$k]['n'] ?? 0) + 1, 't' => now()];
        if (count($L['auto']) > 5000) $L['auto'] = array_slice($L['auto'], -5000, null, true);
        // Protokoll/Benachrichtigung höchstens einmal je Minute (bei vielen Adressen gesammelt)
        $m = $L['meldung'];
        $mehr = (int)($m['n'] ?? 0);
        if ((int)($m['t'] ?? 0) > $now - 60) { $L['meldung'] = ['t' => (int)$m['t'], 'n' => $mehr + 1]; $mehr = -1; }
        else $L['meldung'] = ['t' => $now, 'n' => 0];
        store_write('sperrliste', $L);
        return $mehr;
    });
    if ($melden !== null && $melden >= 0) audit('security', 'Adresse ' . fw_key($ip) . ' automatisch gesperrt (' . $grund . ', ' . ($min >= 1440 ? intdiv($min, 1440) . ' Tag(e)' : $min . ' Minuten') . ')'
        . ($melden ? " – seit der letzten Meldung {$melden} weitere Adresse(n) gesperrt" : ''), [], ['username' => 'firewall', 'name' => 'Firewall', 'role' => '']);
}
function fw_treffer(string $ip, string $grund): void
{
    $F = fw();
    if (fw_erlaubt($ip) || fw_fremd() || fw_mitarbeiter()) return;   // fremde Seite oder angemeldeter Mitarbeiter: nicht zählen
    if (fw_zaehlen($ip, 'h', FW_FENSTER) >= max(1, (int)$F['treffer'])) fw_auto_sperren($ip, $grund);
}

/* Live-Verkehr: Ringpuffer der letzten Anfragen. Parameter mit Schlüsseln/Tokens werden unkenntlich gemacht. */
function fw_verkehr(array $e): void
{
    try {
        $q = (string)($_SERVER['QUERY_STRING'] ?? '');
        $q = preg_replace('/(^|&)(t|token|k|key|code|sig|z)=[^&]*/i', '$1$2=…', $q);
        $ip = client_ip();
        $u = fw_mitarbeiter() ? current_user() : null;
        $row = ['t' => time(), 'ip' => $ip, 'm' => substr((string)($_SERVER['REQUEST_METHOD'] ?? ''), 0, 7), 'q' => mb_substr((string)$q, 0, 160),
                'st' => (int)($e['st'] ?? http_response_code()), 'why' => mb_substr((string)($e['why'] ?? ''), 0, 120),
                'ua' => mb_substr((string)($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 120), 'u' => $u ? $u['username'] : ''];
        if (function_exists('geo_country') && ($cc = @geo_country($ip))) $row['cc'] = $cc;
        with_lock('verkehr', function () use ($row) {
            $v = store_read('verkehr') ?? [];
            // gleiche gesperrte Adresse innerhalb einer Minute: nur zählen statt jede Anfrage einzeln speichern
            $hit = null;
            if ($row['why'] !== '') for ($i = count($v) - 1; $i >= max(0, count($v) - 30); $i--) {
                if ($v[$i]['t'] < $row['t'] - 60) break;
                if ($v[$i]['ip'] === $row['ip'] && $v[$i]['why'] === $row['why']) { $hit = $i; break; }
            }
            if ($hit !== null) { $v[$hit]['n'] = (int)($v[$hit]['n'] ?? 1) + 1; $v[$hit]['t'] = $row['t']; }
            else $v[] = $row;
            if (count($v) > FW_VERKEHR_MAX) $v = array_slice($v, -FW_VERKEHR_MAX);
            store_write('verkehr', $v);
        });
    } catch (Throwable $ex) { error_log('[wochenangebot] verkehr: ' . $ex->getMessage()); }
}

/* Vor jeder Aktion */
function fw_guard(string $action): void
{
    $ip = client_ip();
    if ($action === 'waf_probe') return;   // Falle: eigene Aktion
    // Angemeldete Mitarbeiter kommen trotz Sperre der Adresse durch (z. B. Büro über eine fremde Seite gesperrt) – sie können
    // die Sperre so selbst aufheben; ihre Anmeldung prüft Passwort, Zwei-Faktor und ggf. die IP-Freigabe weiterhin
    if (!fw_erlaubt($ip) && !fw_mitarbeiter() && ($grund = fw_gesperrt($ip)) !== null) {
        fw_verkehr(['st' => 403, 'why' => 'Gesperrt: ' . $grund]);
        header('Retry-After: 600');
        fail('Der Zugriff von Ihrer Internetadresse ist vorübergehend gesperrt.', 403);
    }
    $F = fw();
    if ($F['waf'] !== 'aus' && !fw_erlaubt($ip) && ($gruppe = fw_angriff()) !== null) {
        $block = $F['waf'] === 'sperren';
        fw_verkehr(['st' => $block ? 403 : 0, 'why' => 'Firewall: ' . $gruppe . ($block ? '' : ' (nur protokolliert)')]);
        fw_treffer($ip, $gruppe);
        if ($block) fail('Die Anfrage wurde von der Firewall abgewiesen.', 403);
    }
    register_shutdown_function('fw_nachher', $action);
}
/* Nach jeder Aktion: Fehlerbremse, Anmeldungen und Mitschnitt im Live-Verkehr */
const FW_ANMELDUNG = ['login', 'login_2fa', 'kunde_login', 'passkey_login'];
function fw_nachher(string $action): void
{
    try {
        $st = (int)http_response_code();
        $F = fw();
        $ip = client_ip();
        $fehler = in_array($st, [400, 404, 405, 415], true) && !fw_mitarbeiter();
        if ($fehler && (int)$F['fehlerLimit'] > 0 && !fw_erlaubt($ip) && !fw_fremd() && fw_zaehlen($ip, 'e', FW_FEHLER_FENSTER) >= (int)$F['fehlerLimit']) {
            fw_auto_sperren($ip, 'zu viele fehlerhafte Anfragen');
        }
        if (in_array($action, FW_ANMELDUNG, true)) fw_verkehr(['st' => $st, 'why' => $st === 200 ? 'Anmeldung' : 'Anmeldung fehlgeschlagen']);
        elseif ((int)$F['mitschnittBis'] > time() || $fehler) fw_verkehr(['st' => $st, 'why' => $fehler ? 'Fehlerhafte Anfrage' : '']);
    } catch (Throwable $ex) { error_log('[wochenangebot] firewall: ' . $ex->getMessage()); }
}

/* Falle: typische Pfade von Angriffswerkzeugen (wp-login.php, .env, phpMyAdmin …) leitet Caddy hierher */
function fw_falle(): void
{
    $ip = client_ip();
    $p = mb_substr(preg_replace('/[^\x20-\x7e]/', '', (string)($_GET['p'] ?? '')), 0, 80);
    if (!fw_erlaubt($ip) && fw_gesperrt($ip) === null) {   // schon gesperrt: nur antworten, nichts schreiben
        fw_verkehr(['st' => 404, 'why' => 'Falle: ' . ($p !== '' ? $p : 'unbekannter Pfad')]);
        fw_treffer($ip, 'Suche nach Schwachstellen (' . ($p !== '' ? $p : 'Pfad') . ')');
    }
    http_response_code(404);
    header('Content-Type: text/plain; charset=utf-8');
    header('Cache-Control: no-store');
    echo 'Nicht gefunden.';
    exit;
}

/* Bedrohungsliste herunterladen und prüfen (nur öffentliche Netze, keine eigenen/freigegebenen Adressen) */
function fw_feed_laden(): array
{
    $ctx = stream_context_create(['http' => ['timeout' => 30, 'user_agent' => 'Wochenangebot', 'follow_location' => 1], 'ssl' => ['verify_peer' => true]]);
    $netze = [];
    $ok = 0;
    foreach (FW_FEED_QUELLEN as $url) {
        $t = @file_get_contents($url, false, $ctx, 0, 2000000);
        if ($t === false) continue;
        $ok++;
        foreach (preg_split('/\R/', $t) as $z) {
            $c = trim(explode(';', $z, 2)[0]);
            if ($c === '' || !valid_cidr($c) || strpos($c, '/') === false) continue;
            [$net, $bits] = explode('/', $c);
            if ((int)$bits < (strpos($net, ':') !== false ? 19 : 8)) continue;   // unplausibel große Netze nie übernehmen
            if (filter_var($net, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false) continue;
            $netze[] = $c;
        }
    }
    if (!$ok) throw new RuntimeException('Die Bedrohungsliste konnte nicht geladen werden.');
    if (count($netze) < 50) throw new RuntimeException('Die Bedrohungsliste ist unvollständig.');
    return fw_feed_speichern($netze, 'Spamhaus DROP');
}
function fw_feed_speichern(array $netze, string $quelle): array
{
    $S = sec();
    $eigen = array_merge((array)$S['adminIps'], (array)fw()['erlaubt'], [client_ip()]);
    $netze = array_values(array_unique(array_filter($netze, function ($c) use ($eigen) {
        $net = explode('/', $c)[0];
        foreach ($eigen as $e) if ($e !== '' && (ip_in(explode('/', $e)[0], $c) || ip_in($net, $e))) return false;   // nie sich selbst sperren
        return true;
    })));
    $d = ['quelle' => $quelle, 'stand' => now(), 'anzahl' => count($netze), 'netze' => array_slice($netze, 0, 50000)];
    store_write('bedrohungsliste', $d + fw_feed_index($d['netze']));
    return ['quelle' => $quelle, 'stand' => $d['stand'], 'anzahl' => $d['anzahl']];
}
/* Schneller Index der Bedrohungsliste für die Prüfung vor jeder Anfrage: IPv4 als sortierte, zusammengefasste Bereiche
   (gepackt: Anfang/Ende je 4 Byte, base64) für eine binäre Suche; IPv6 (wenige Netze) als Liste. Steht im selben Dokument
   wie die Liste (zusätzliche Felder v4/v6/n4): Schreibt eine ältere Version die Liste neu, fehlt der Index und wird neu
   gebaut – er kann nie zu einer anderen Liste gehören. Ältere Versionen ignorieren die Felder. */
function fw_feed_index(array $netze): array
{
    $r = []; $v6 = [];
    foreach ($netze as $c) {
        $p = explode('/', (string)$c, 2);
        if (strpos($p[0], ':') !== false) { $v6[] = $c; continue; }
        $a = ip2long($p[0]);
        if ($a === false) continue;
        $bits = isset($p[1]) ? max(0, min(32, (int)$p[1])) : 32;
        $mask = $bits === 0 ? 0 : ((0xFFFFFFFF << (32 - $bits)) & 0xFFFFFFFF);
        $start = $a & $mask;
        $r[] = [$start, $start | (~$mask & 0xFFFFFFFF)];
    }
    usort($r, fn($x, $y) => $x[0] <=> $y[0]);
    $m = [];
    foreach ($r as [$a, $b]) {
        $k = count($m) - 1;
        if ($k >= 0 && $a <= $m[$k][1] + 1) $m[$k][1] = max($m[$k][1], $b); else $m[] = [$a, $b];
    }
    $bin = '';
    foreach ($m as [$a, $b]) $bin .= pack('NN', $a, $b);
    return ['v4' => base64_encode($bin), 'v6' => $v6, 'n4' => count($m)];
}
/* Steht die Adresse auf der Bedrohungsliste? Mit Index binäre Suche; ohne Index (Liste einer älteren Version) wie bisher */
function fw_feed_trifft(string $ip): bool
{
    $x = store_read('bedrohungsliste');
    if (!is_array($x) || empty($x['netze'])) return false;
    if (!isset($x['v4'])) {
        // Liste ohne Index (von einer älteren Version geladen): einmal nachbauen, bis dahin wie bisher prüfen
        // (scheitert das Speichern, höchstens einmal je Minute erneut versuchen)
        $merk = rtrim(sys_get_temp_dir(), '/') . '/wa-bl-index-' . substr(hash('sha256', (string)($GLOBALS['DATA'] ?? '')), 0, 12);
        if (@filemtime($merk) > time() - 60) return ip_allowed($ip, (array)$x['netze']);
        try {
            with_lock('bedrohungsliste', function () {
                $f = store_read('bedrohungsliste');
                if (is_array($f) && !empty($f['netze']) && !isset($f['v4'])) store_write('bedrohungsliste', $f + fw_feed_index((array)$f['netze']));
            });
        } catch (Throwable $e) { @touch($merk); error_log('[wochenangebot] bedrohungsliste-index: ' . $e->getMessage()); }
        return ip_allowed($ip, (array)$x['netze']);
    }
    if (strpos($ip, ':') !== false) return !empty($x['v6']) && ip_allowed($ip, (array)$x['v6']);
    $a = ip2long($ip);
    $bin = base64_decode((string)$x['v4'], true);
    if ($a === false || !is_string($bin) || $bin === '') return false;
    $lo = 0; $hi = intdiv(strlen($bin), 8) - 1;
    while ($lo <= $hi) {
        $mid = ($lo + $hi) >> 1;
        $s = unpack('N', $bin, $mid * 8)[1]; $e = unpack('N', $bin, $mid * 8 + 4)[1];
        if ($a < $s) $hi = $mid - 1; elseif ($a > $e) $lo = $mid + 1; else return true;
    }
    return false;
}
function fw_feed_info(): ?array
{
    $f = store_read('bedrohungsliste');
    return $f ? ['quelle' => $f['quelle'] ?? '', 'stand' => $f['stand'] ?? null, 'anzahl' => (int)($f['anzahl'] ?? 0)] : null;
}

/* Einstellungen prüfen (Firewall) */
function fw_clean(array $b, array $old): array
{
    $waf = (string)($b['waf'] ?? $old['waf']);
    if (!isset(FW_WAF_MODI[$waf])) throw new InvalidArgumentException('Unbekannte Firewall-Einstellung.');
    $min = (int)($b['sperrMinuten'] ?? $old['sperrMinuten']);
    if (!in_array($min, FW_SPERR_MINUTEN, true)) throw new InvalidArgumentException('Ungültige Sperrdauer.');
    $erlaubt = [];
    foreach (array_slice(is_array($b['erlaubt'] ?? null) ? $b['erlaubt'] : (array)$old['erlaubt'], 0, 50) as $c) {
        $c = trim((string)$c);
        if ($c === '') continue;
        if (!valid_cidr($c)) throw new InvalidArgumentException("„{$c}“ ist keine gültige IP-Adresse oder kein gültiger Bereich.");
        $erlaubt[] = $c;
    }
    $mit = array_key_exists('mitschnittMinuten', $b) ? (int)$b['mitschnittMinuten'] : null;
    if ($mit !== null && !in_array($mit, [0, 15, 60], true)) throw new InvalidArgumentException('Ungültige Dauer für den Mitschnitt.');
    return ['waf' => $waf, 'autoSperre' => (bool)($b['autoSperre'] ?? $old['autoSperre']),
            'treffer' => max(1, min(50, (int)($b['treffer'] ?? $old['treffer']))), 'sperrMinuten' => $min,
            'fehlerLimit' => max(0, min(500, (int)($b['fehlerLimit'] ?? $old['fehlerLimit']))),
            'feed' => (bool)($b['feed'] ?? $old['feed']),
            'mitschnittBis' => $mit === null ? (int)$old['mitschnittBis'] : ($mit ? time() + 60 * $mit : 0),
            'erlaubt' => $erlaubt];
}

/* Vorlagen für die Sicherheitseinstellungen (Sicherheit + Firewall). Nicht enthalten: Listen (Adressen, Länder). */
const FW_VORLAGEN = [
    'standard' => ['label' => 'Standard', 'text' => 'Ausgewogen für den Alltag: Firewall weist Angriffe ab, automatische Sperre nach 5 Treffern für 1 Stunde, Zwei-Faktor für Administratoren.',
        'sec' => ['twofa' => 'admins', 'pwMin' => 10, 'pwComplex' => false, 'idleMinutes' => 480, 'lockAfter' => 10, 'lockMinutes' => 15],
        'fw' => ['waf' => 'sperren', 'autoSperre' => true, 'treffer' => 5, 'sperrMinuten' => 60, 'fehlerLimit' => 30]],
    'streng' => ['label' => 'Streng', 'text' => 'Mehr Schutz: Zwei-Faktor für alle, längere Passwörter mit Datenleck-Prüfung, kürzere Sitzungen, Sperre nach 3 Treffern für einen Tag, Bedrohungsliste an.',
        'sec' => ['twofa' => 'all', 'pwMin' => 12, 'pwComplex' => true, 'pwLeak' => true, 'idleMinutes' => 60, 'lockAfter' => 5, 'lockMinutes' => 60],
        'fw' => ['waf' => 'sperren', 'autoSperre' => true, 'treffer' => 3, 'sperrMinuten' => 1440, 'fehlerLimit' => 20, 'feed' => true]],
    'notfall' => ['label' => 'Notfall (laufender Angriff)', 'text' => 'Für akute Angriffe: Sperre schon nach dem ersten Treffer für 7 Tage, sehr kurze Sitzungen, Mitschnitt aller Anfragen für 60 Minuten. Tipp: vorher die Büro-Adresse unter „nie sperren“ eintragen.',
        'sec' => ['twofa' => 'all', 'pwMin' => 12, 'pwComplex' => true, 'pwLeak' => true, 'idleMinutes' => 30, 'lockAfter' => 3, 'lockMinutes' => 240],
        'fw' => ['waf' => 'sperren', 'autoSperre' => true, 'treffer' => 1, 'sperrMinuten' => 10080, 'fehlerLimit' => 10, 'feed' => true, 'mitschnittMinuten' => 60]],
];

/* Übersicht für die Ansicht „Schutz“ */
function fw_status(string $filter = ''): array
{
    $now = time();
    $L = fw_sperrliste();
    $auto = array_values(array_filter($L['auto'], fn($a) => (int)($a['bis'] ?? 0) > $now));
    usort($auto, fn($a, $b) => strcmp((string)$b['t'], (string)$a['t']));
    $manuell = array_values(array_filter($L['manuell'], fn($e) => !(int)($e['bis'] ?? 0) || (int)$e['bis'] > $now));
    $v = store_read('verkehr') ?? [];
    $tag = array_filter($v, fn($e) => (int)$e['t'] > $now - 86400);
    $angriffe = 0; $gesperrt = 0; $fehlAnm = 0;
    foreach ($tag as $e) {
        $w = (string)($e['why'] ?? ''); $n = (int)($e['n'] ?? 1);
        if (strpos($w, 'Firewall:') === 0 || strpos($w, 'Falle:') === 0) $angriffe += $n;
        if (strpos($w, 'Gesperrt:') === 0) $gesperrt += $n;
        if ($w === 'Anmeldung fehlgeschlagen') $fehlAnm += $n;
    }
    $F = fw();
    return ['fw' => $F, 'modi' => FW_WAF_MODI, 'sperrMinuten' => FW_SPERR_MINUTEN, 'vorlagen' => array_map(fn($x) => ['label' => $x['label'], 'text' => $x['text']], FW_VORLAGEN),
            'zahlen' => ['angriffe' => $angriffe, 'abgewiesen' => $gesperrt, 'anmeldungFehl' => $fehlAnm, 'gesperrteAdressen' => count($auto) + count($manuell)],
            'manuell' => $manuell, 'auto' => array_slice($auto, 0, 300), 'autoGesamt' => count($auto), 'feed' => fw_feed_info(),
            'meineIp' => client_ip(), 'mitschnitt' => (int)$F['mitschnittBis'] > $now ? (int)$F['mitschnittBis'] : 0,
            'verkehr' => fw_verkehr_liste($filter, 0)];
}
function fw_verkehr_liste(string $filter, int $seit): array
{
    $v = array_reverse(store_read('verkehr') ?? []);
    $out = [];
    foreach ($v as $e) {
        if ($seit && (int)$e['t'] <= $seit) break;
        $w = (string)($e['why'] ?? '');
        if ($filter === 'gesperrt' && strpos($w, 'Gesperrt:') !== 0 && strpos($w, 'Firewall:') !== 0 && strpos($w, 'Falle:') !== 0) continue;
        if ($filter === 'anmeldung' && strpos($w, 'Anmeldung') !== 0) continue;
        if ($filter === 'fehler' && (int)$e['st'] < 400) continue;
        $out[] = $e;
        if (count($out) >= 200) break;
    }
    return $out;
}
