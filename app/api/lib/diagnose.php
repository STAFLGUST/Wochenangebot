<?php
declare(strict_types=1);
/* Sicherheit für IT-Administratoren: Lagebild (Verlauf, auffällige Adressen), Konfigurationsprüfung,
   nur lesende Diagnosen und Export des Sicherheitsprotokolls. Es werden keine Befehle auf dem Server ausgeführt. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Sicherheitsrelevante Vorgänge im Protokoll (Export, Verlauf) */
const SEC_LOG_TYPES = ['login', 'login_fail', 'logout', 'reauth', 'reauth_fail', 'twofa', 'password', 'security', 'user', 'setup', 'wartung', 'kunde_login', 'kunde_login_fail', 'kunde_password', 'mail', 'notfall', 'oidc_stufe'];

/* Protokolleinträge der letzten $days Tage (Monatsdateien) */
function sec_log_entries(int $days): array
{
    $since = time() - $days * 86400;
    $out = [];
    for ($i = 0; $i <= 24; $i++) {   // Monatsdateien (UTC) vom Startmonat bis heute; höchstens 2 Jahre
        $m = utc_monat($i, $since);
        foreach (store_read('protokoll/' . $m) ?? [] as $e) if (strtotime((string)$e['t']) >= $since) $out[] = $e;
        if ($m >= utc_monat()) break;
    }
    return $out;
}

/* Verlauf der letzten 14 Tage je Tag: fehlgeschlagene Anmeldungen (Mitarbeiter/Kunden), Passwortbestätigung, Ländersperre */
function sec_timeline(array $entries): array
{
    $days = [];
    for ($i = 13; $i >= 0; $i--) $days[gmdate('Y-m-d', time() - $i * 86400)] = ['staff' => 0, 'kunde' => 0, 'reauth' => 0, 'geo' => 0, 'ok' => 0];
    foreach ($entries as $e) {
        $d = substr((string)$e['t'], 0, 10);
        if (!isset($days[$d])) continue;
        if ($e['a'] === 'login_fail') $days[$d]['staff']++;
        elseif ($e['a'] === 'kunde_login_fail') $days[$d]['kunde']++;
        elseif ($e['a'] === 'reauth_fail') $days[$d]['reauth']++;
        elseif ($e['a'] === 'login') $days[$d]['ok']++;
    }
    $gs = store_read('laendersperre') ?? [];
    foreach ($gs['days'] ?? [] as $d => $n) if (isset($days[$d])) $days[$d]['geo'] += (int)$n;
    if (($gs['day'] ?? '') === gmdate('Y-m-d') && isset($days[gmdate('Y-m-d')])) $days[gmdate('Y-m-d')]['geo'] += (int)($gs['today'] ?? 0);
    $out = [];
    foreach ($days as $d => $v) $out[] = ['d' => $d] + $v;
    return $out;
}

/* Auffällige Adressen (7 Tage): fehlgeschlagene Anmeldungen je IP mit Land und versuchten Benutzernamen */
function sec_top_ips(array $entries): array
{
    $by = [];
    foreach ($entries as $e) {
        if (!in_array($e['a'], ['login_fail', 'kunde_login_fail', 'reauth_fail'], true) || strtotime((string)$e['t']) < time() - 7 * 86400) continue;
        $ip = (string)($e['ip'] ?? '');
        if ($ip === '') continue;
        $b = $by[$ip] ?? ['ip' => $ip, 'n' => 0, 'last' => '', 'users' => [], 'kunde' => 0];
        $b['n']++;
        if (strcmp((string)$e['t'], $b['last']) > 0) $b['last'] = (string)$e['t'];
        if (($e['u'] ?? '') !== '' && count($b['users']) < 5 && !in_array($e['u'], $b['users'], true)) $b['users'][] = (string)$e['u'];
        if ($e['a'] === 'kunde_login_fail') $b['kunde']++;
        $by[$ip] = $b;
    }
    usort($by, function ($a, $b) { return $b['n'] <=> $a['n'] ?: strcmp($b['last'], $a['last']); });
    $blocked = [];
    foreach (store_read('logins') ?? [] as $v) if ((int)($v['until'] ?? 0) > time()) $blocked[(string)($v['ip'] ?? '')] = true;
    return array_map(function ($b) use ($blocked) { return $b + ['cc' => geo_country($b['ip']), 'blocked' => isset($blocked[$b['ip']])]; }, array_slice(array_values($by), 0, 10));
}

/* Betriebszustand (Modul Sicherheit: Reiter System und Lagebild): Wartung, Sicherung, Bereitstellung, Datenablage,
   Speicher, E-Mail-Versand, Bestellwünsche, Kunden – nur lesend, für Administratoren */
function betrieb_daten(array $me): array
{
    global $DATA;
    $mail = array_filter(store_read('mailversand') ?? [], function ($x) { return strtotime((string)$x['t']) > time() - 7 * 86400; });
    $alle = store_read('bestellungen') ?? [];
    $woche = array_filter($alle, function ($x) { return strtotime((string)$x['t']) > time() - 7 * 86400; });
    $letzte = $alle ? end($alle) : null;
    $kunden = array_filter(customers_load()['customers'], function ($x) { return !empty($x['active']); });
    return ['backup' => store_read('sicherung'),
            'wartung' => wartung(), 'wartungEingabe' => modul_wartung_anzeige('angebot', 'eingabe', $me),
            'wartungVerlauf' => array_slice(modul_laufzeit()['verlauf'], 0, 20), 'storage' => store_stats(), 'php' => PHP_VERSION,
            'disk' => ['free' => @disk_free_space($DATA) ?: null, 'total' => @disk_total_space($DATA) ?: null],
            'mail' => ['configured' => (bool)mail_cfg() && (bool)mail_base_url(), 'sent7' => count(array_filter($mail, function ($x) { return $x['ok']; })),
                       'failed7' => count(array_filter($mail, function ($x) { return !$x['ok']; }))],
            'orders' => ['enabled' => order_enabled(), 'n7' => count($woche), 'failed7' => count(array_filter($woche, function ($x) { return ($x['status'] ?? '') === 'fehler'; })),
                         'last' => $letzte['t'] ?? null, 'lastNr' => $letzte['nr'] ?? null],
            'customers' => ['active' => count($kunden), 'withLogin' => count(array_filter($kunden, function ($x) { return !empty($x['login']['active']); })),
                            'online' => count(array_unique(array_column(ksess_prune(store_read('kundensitzungen') ?? []), 'kid')))],
            'deployment' => store_read('deployment'),
            'notfall' => notfall_anzeige($me)];
}

/* Konfigurationsprüfung (serverseitig sichtbar): [bereich, stufe ok|warn|bad|info, titel, befund, empfehlung] */
function sec_config_checks(array $users): array
{
    $c = [];
    $add = function (string $area, string $lvl, string $title, string $text, string $hint = '') use (&$c) { $c[] = ['area' => $area, 'level' => $lvl, 'title' => $title, 'text' => $text, 'hint' => $hint]; };
    $on = function (string $k): bool { $v = strtolower((string)ini_get($k)); return in_array($v, ['1', 'on', 'yes', 'true'], true); };
    // Zugänge
    $act = array_filter($users, function ($u) { return !empty($u['active']); });
    $admins = array_filter($act, function ($u) { return $u['role'] === 'admin'; });
    $add('Zugänge', count($admins) <= 3 ? 'ok' : 'warn', 'Administratoren', (count($admins) === 1 ? '1 aktiver Administrator-Zugang' : count($admins) . ' aktive Administrator-Zugänge'), count($admins) <= 3 ? '' : 'Nur so viele Administratoren wie nötig – übrige als Bearbeiter führen.');
    $stale = sec_ungenutzt(SEC_UNGENUTZT_TAGE, $users)['konten'];
    $add('Zugänge', $stale ? 'warn' : 'ok', 'Unbenutzte Zugänge', $stale ? count($stale) . ' aktive Zugänge seit über ' . SEC_UNGENUTZT_TAGE . ' Tagen nicht angemeldet: ' . implode(', ', array_slice(array_map(function ($u) { return $u['username']; }, $stale), 0, 6)) : 'keine', $stale ? 'Nicht mehr benötigte Zugänge deaktivieren (Sicherheit → Konten).' : '');
    $must = array_filter($act, function ($u) { return !empty($u['mustChange']); });
    $add('Zugänge', $must ? 'warn' : 'ok', 'Startpasswörter', $must ? count($must) . ' Zugänge mit noch nicht geändertem Startpasswort' : 'alle Passwörter selbst gesetzt', $must ? 'Startpasswörter nur kurz gültig halten bzw. Zugang deaktivieren, bis er gebraucht wird.' : '');
    // Sitzung und PHP
    $cp = session_get_cookie_params();
    $https = is_https();
    $cookieOk = !empty($cp['httponly']) && (!$https || !empty($cp['secure'])) && in_array(strtolower((string)($cp['samesite'] ?? '')), ['lax', 'strict'], true);
    $add('Server', $cookieOk ? 'ok' : 'bad', 'Sitzungs-Cookies', 'HttpOnly ' . (!empty($cp['httponly']) ? 'ja' : 'nein') . ' · Secure ' . (!empty($cp['secure']) ? 'ja' : 'nein') . ' · SameSite ' . ((string)($cp['samesite'] ?? '') ?: 'nicht gesetzt'), $cookieOk ? '' : 'Cookies müssen HttpOnly, über HTTPS Secure und SameSite=Lax/Strict sein.');
    $add('Server', !$on('display_errors') ? 'ok' : 'bad', 'Fehlermeldungen', $on('display_errors') ? 'werden im Browser angezeigt' : 'nicht öffentlich (nur im Server-Protokoll)', $on('display_errors') ? 'display_errors ausschalten – Fehlermeldungen verraten Interna.' : '');
    $sent = in_array('x-powered-by', array_map(function ($h) { return strtolower(trim(explode(':', $h, 2)[0])); }, headers_list()), true);
    $add('Server', !$sent ? 'ok' : 'warn', 'PHP-Version im Header', $sent ? 'wird mitgesendet (X-Powered-By)' : ($on('expose_php') ? 'nicht sichtbar (von der Anwendung entfernt)' : 'nicht sichtbar'), $sent ? 'expose_php ausschalten.' : '');
    $add('Server', !$on('allow_url_include') ? 'ok' : 'bad', 'Fremde Dateien einbinden', $on('allow_url_include') ? 'erlaubt (allow_url_include)' : 'gesperrt');
    $ver = PHP_VERSION;
    $add('Server', version_compare($ver, '8.2.0', '>=') ? 'ok' : 'warn', 'PHP-Version', $ver . ' (' . PHP_SAPI . ')', version_compare($ver, '8.2.0', '>=') ? '' : 'Auf eine unterstützte PHP-Version aktualisieren.');
    $need = ['sodium' => 'Passwort des Postfachs verschlüsseln', 'openssl' => 'verschlüsselte Verbindung zum Mailserver', 'pdo_sqlite' => 'Datenbank-Speicher'];
    $miss = array_filter($need, function ($k) { return !extension_loaded($k); }, ARRAY_FILTER_USE_KEY);
    $add('Server', $miss ? 'warn' : 'ok', 'PHP-Erweiterungen', $miss ? 'fehlt: ' . implode(', ', array_keys($miss)) : implode(', ', array_keys($need)) . ' vorhanden', $miss ? 'Benötigt für: ' . implode('; ', $miss) . '.' : '');
    // Dienste
    $m = mail_cfg();
    if (testumgebung()) $add('Dienste', 'info', 'E-Mail-Verbindung', 'Testumgebung – es wird kein Mailserver verwendet');
    elseif (!$m) $add('Dienste', 'warn', 'E-Mail-Verbindung', 'nicht eingerichtet', 'Ohne E-Mail keine Benachrichtigungen bei Sicherheitsereignissen.');
    else $add('Dienste', ($m['secure'] ?? '') === 'none' ? 'bad' : 'ok', 'E-Mail-Verbindung', ($m['secure'] ?? '') === 'none' ? 'unverschlüsselt' : 'verschlüsselt (' . strtoupper((string)$m['secure']) . ')', ($m['secure'] ?? '') === 'none' ? 'SSL oder STARTTLS verwenden.' : '');
    $ns = notify_settings()['events']['sicherheit'] ?? ['on' => false, 'to' => []];
    $add('Dienste', $ns['on'] && $ns['to'] ? 'ok' : 'warn', 'Alarm bei Sicherheitsereignissen', $ns['on'] && $ns['to'] ? 'per E-Mail an ' . implode(', ', $ns['to']) : 'ausgeschaltet', $ns['on'] && $ns['to'] ? '' : 'Verwaltung → E-Mail → Benachrichtigungen → Sicherheitsereignisse.');
    $g = geo_info();
    $gAge = $g ? (int)floor((time() - strtotime($g['date'] . 'T00:00:00Z')) / 86400) : null;
    if (!empty(sec()['pwLeak'])) {
        $dl = store_read('datenleck');
        $add('Dienste', !$dl ? 'info' : ($dl['ok'] ? 'ok' : 'warn'), 'Datenleck-Prüfung der Passwörter', !$dl ? 'eingeschaltet, noch nicht benutzt'
            : ($dl['ok'] ? 'Dienst erreichbar (' . date('d.m.Y, H:i', (int)$dl['t']) . ' Uhr)' : 'Dienst zuletzt nicht erreichbar (' . date('d.m.Y, H:i', (int)$dl['t']) . ' Uhr)'),
            $dl && !$dl['ok'] ? 'Ohne Verbindung werden Passwörter nicht gegen Datenlecks geprüft (aber auch nicht blockiert). Ausgehende Verbindung zu api.pwnedpasswords.com prüfen.' : '');
    }
    $add('Dienste', !$g ? 'warn' : ($gAge > 120 ? 'warn' : 'ok'), 'Länderdaten', $g ? 'Stand ' . date('d.m.Y', strtotime($g['date'])) . " ({$gAge} Tage)" : 'fehlen', !$g || $gAge > 120 ? 'Unter Einstellungen „Länderdaten aktualisieren“.' : '');
    return $c;
}

/* Nur lesende Diagnosen; Ergebnis: ['ok' => bool, 'items' => [[label, wert, stufe]], 'ms' => int] */
function sec_diag(string $check): array
{
    global $DATA;
    $t0 = microtime(true);
    $items = []; $ok = true;
    $it = function (string $l, string $v, string $lvl = 'ok') use (&$items, &$ok) { $items[] = ['label' => $l, 'value' => $v, 'level' => $lvl]; if ($lvl === 'bad') $ok = false; };
    if ($check === 'storage') {
        $st = store_stats();
        $it('Speicherart', $st['mode'] === 'sqlite' ? 'SQLite-Datenbank' : 'Dateien', 'info');
        $it('Datensätze', (string)$st['documents'], 'info');
        $bad = [];
        if ($st['mode'] === 'sqlite') {
            $qc = (string)store_db()->query('PRAGMA quick_check')->fetchColumn();
            $it('Datenbank-Prüfung (quick_check)', $qc, $qc === 'ok' ? 'ok' : 'bad');
            try { foreach (store_db()->query('SELECT name FROM documents WHERE json_valid(payload) = 0 LIMIT 20') as $r) $bad[] = $r['name']; }
            catch (Throwable $e) { $it('Inhaltsprüfung', 'nicht möglich (' . $e->getMessage() . ')', 'warn'); }
        } else {
            $files = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($DATA, FilesystemIterator::SKIP_DOTS));
            foreach ($files as $f) {
                $rel = substr($f->getPathname(), strlen($DATA) + 1);
                if (!$f->isFile() || substr($rel, -4) !== '.php' || $rel === 'index.php' || strpos($rel, 'geo/') === 0 || $rel[0] === '.') continue;
                $raw = (string)@file_get_contents($f->getPathname());
                if (strncmp($raw, GUARD, strlen(GUARD)) !== 0) { $bad[] = $rel . ' (ohne Zugriffssperre)'; continue; }
                json_decode(substr($raw, strlen(GUARD)));
                if (json_last_error() !== JSON_ERROR_NONE) $bad[] = $rel;
                if (count($bad) >= 20) break;
            }
        }
        $it('Fehlerhafte Datensätze', $bad ? implode(', ', $bad) : 'keine', $bad ? 'bad' : 'ok');
    } elseif ($check === 'mail') {
        $m = mail_cfg();
        if (testumgebung()) $it('Mailserver', 'Testumgebung – kein Mailserver (E-Mails im Testpostfach)', 'info');
        elseif (!$m) $it('Mailserver', 'nicht eingerichtet', 'warn');
        else {
            $it('Server', $m['host'] . ':' . $m['port'] . ' (' . strtoupper((string)$m['secure']) . ')', 'info');
            try { $s = new Smtp($m); $s->open(); $s->close(); $it('Verbindung und Anmeldung', 'erfolgreich (keine E-Mail versendet)'); }
            catch (RuntimeException $e) { $it('Verbindung und Anmeldung', $e->getMessage(), 'bad'); }
        }
    } elseif ($check === 'files') {
        $it('Datenordner beschreibbar', is_writable($DATA) ? 'ja' : 'nein', is_writable($DATA) ? 'ok' : 'bad');
        $tmp = sys_get_temp_dir();
        $it('Temporärer Ordner beschreibbar', is_writable($tmp) ? 'ja' : 'nein', is_writable($tmp) ? 'ok' : 'warn');
        $app = dirname(__DIR__, 2);
        $it('Programmordner schreibgeschützt', is_writable($app) ? 'nein (beschreibbar)' : 'ja', is_writable($app) ? 'warn' : 'ok');
        $free = @disk_free_space($DATA); $total = @disk_total_space($DATA);
        $it('Freier Speicher', $free && $total ? round($free / 1073741824, 1) . ' GB von ' . round($total / 1073741824, 1) . ' GB' : 'unbekannt', $free && $free < 1073741824 ? 'bad' : ($free && $free < 5 * 1073741824 ? 'warn' : 'ok'));
        $locks = glob($DATA . '/.*.lock') ?: [];
        $it('Sperrdateien', (string)count($locks), count($locks) > 200 ? 'warn' : 'info');
    } elseif ($check === 'php') {
        $it('PHP', PHP_VERSION . ' · ' . PHP_SAPI . ' · ' . PHP_OS_FAMILY, 'info');
        foreach (['sodium', 'openssl', 'pdo_sqlite', 'mbstring', 'intl', 'opcache' => 'Zend OPcache'] as $k => $ext) {
            $name = is_int($k) ? $ext : $k;
            $it('Erweiterung ' . $name, extension_loaded($ext) ? 'vorhanden' : 'fehlt', extension_loaded($ext) ? 'ok' : (in_array($name, ['sodium', 'openssl', 'pdo_sqlite'], true) ? 'warn' : 'info'));
        }
        foreach (['memory_limit', 'max_execution_time', 'post_max_size', 'upload_max_filesize', 'session.gc_maxlifetime', 'date.timezone'] as $k) $it($k, (string)ini_get($k) ?: '–', 'info');
        $it('Serverzeit', date('d.m.Y H:i:s') . ' (' . date_default_timezone_get() . ')', 'info');
        $it('Serverzeit UTC', gmdate('Y-m-d\TH:i:s\Z'), 'info');
    } else {
        fail('Unbekannte Prüfung.', 422);
    }
    return ['ok' => $ok, 'check' => $check, 'items' => $items, 'ms' => (int)round((microtime(true) - $t0) * 1000), 'serverTime' => gmdate('Y-m-d\TH:i:s\Z')];
}

/* Sicherheitsprotokoll als CSV (Semikolon, UTF-8 mit BOM) */
function sec_export_csv(int $days): array
{
    $rows = array_filter(sec_log_entries($days), function ($e) { return in_array($e['a'], SEC_LOG_TYPES, true); });
    $cell = function ($v) { $v = (string)$v; if ($v !== '' && strpbrk($v[0], "=+-@\t\r") !== false) $v = "'" . $v; return '"' . str_replace('"', '""', $v) . '"'; };
    $out = ["\xEF\xBB\xBF" . 'Zeit (UTC);Vorgang;Benutzer;Name;Rolle;IP-Adresse;Beschreibung;Details'];
    foreach ($rows as $e) {
        $det = implode(' | ', array_map(function ($c) { return trim(($c['name'] ?? '') . ' ' . ($c['f'] ?? '') . ': ' . ($c['from'] ?? '') . ' → ' . ($c['to'] ?? '')); }, array_slice((array)($e['d'] ?? []), 0, 20)));
        $out[] = implode(';', array_map($cell, [$e['t'], $e['a'], $e['u'] ?? '', $e['n'] ?? '', $e['r'] ?? '', $e['ip'] ?? '', $e['s'] ?? '', $det]));
    }
    return ['csv' => implode("\r\n", $out) . "\r\n", 'count' => count($rows)];
}

/* ---------- Modul Sicherheit: Lagebild, Ereignisse, privilegierte Konten (nur lesend; Aufrufer prüfen die Rechte) ---------- */

/* Ereignisarten für Filter und Anzeige (Protokoll-Vorgang → Art) */
const SEC_EREIGNIS_ARTEN = [
    'anmeldung' => ['Anmeldung', ['login', 'login_fail', 'logout', 'reauth', 'reauth_fail', 'twofa', 'password', 'oidc_stufe']],
    'kunden' => ['Kunden-Anmeldung', ['kunde_login', 'kunde_login_fail', 'kunde_password']],
    'konten' => ['Zugänge und Rollen', ['user', 'setup']],
    'einstellungen' => ['Einstellungen und Schutz', ['security', 'wartung', 'mail']],
    'notfall' => ['Notfallmodus', ['notfall']],
];
function sec_ereignis_art(string $a): string
{
    foreach (SEC_EREIGNIS_ARTEN as $k => [, $liste]) if (in_array($a, $liste, true)) return $k;
    return 'einstellungen';
}
/* Sicherheitsereignisse der letzten $tage Tage, neueste zuerst; Filter Art und Suchtext (Beschreibung, Benutzer, Name, IP) */
function sec_ereignisse(int $tage, string $art = '', string $q = '', int $max = 300): array
{
    $q = mb_strtolower(trim($q));
    $alle = array_reverse(array_values(array_filter(sec_log_entries($tage), function ($e) { return in_array($e['a'] ?? '', SEC_LOG_TYPES, true); })));
    $zahlen = array_fill_keys(array_keys(SEC_EREIGNIS_ARTEN), 0);
    $out = [];
    foreach ($alle as $e) {
        $k = sec_ereignis_art((string)$e['a']);
        $zahlen[$k]++;
        if ($art !== '' && $k !== $art) continue;
        if ($q !== '' && strpos(mb_strtolower(implode(' ', [$e['s'] ?? '', $e['u'] ?? '', $e['n'] ?? '', $e['ip'] ?? ''])), $q) === false) continue;
        if (count($out) >= $max) continue;
        $stufe = in_array($e['a'], ['login_fail', 'kunde_login_fail', 'reauth_fail', 'oidc_stufe'], true) ? 'warn' : ($e['a'] === 'notfall' ? 'bad' : 'info');
        $out[] = ['t' => $e['t'], 'a' => $e['a'], 'art' => $k, 'stufe' => $stufe, 'u' => (string)($e['u'] ?? ''), 'n' => (string)($e['n'] ?? ''), 'r' => (string)($e['r'] ?? ''),
                  'ip' => (string)($e['ip'] ?? ''), 's' => (string)($e['s'] ?? ''), 'd' => array_slice(array_values(array_filter((array)($e['d'] ?? []), 'is_array')), 0, 20)];
    }
    $arten = [];
    foreach (SEC_EREIGNIS_ARTEN as $k => [$label]) $arten[] = ['key' => $k, 'label' => $label, 'n' => $zahlen[$k]];
    return ['ereignisse' => $out, 'arten' => $arten, 'gesamt' => count($alle), 'tage' => $tage];
}

/* Lagebild: Kennzahlen, Verlauf, auffällige Adressen, Konfigurationsprüfung, Dateiprüfung, letzte Ereignisse */
function sec_lagebild(array $me): array
{
    $users = users_load();
    $log = sec_log_entries(14);
    $tag = time() - 86400;
    $n24 = function (array $arten) use ($log, $tag) { return count(array_filter($log, function ($e) use ($arten, $tag) { return in_array($e['a'], $arten, true) && strtotime((string)$e['t']) > $tag; })); };
    $aktiv = array_values(array_filter($users, function ($u) { return !empty($u['active']) && nutzer_hat_zugang($u); }));
    $admins = array_filter($aktiv, function ($u) { return $u['role'] === 'admin'; });
    $ohne2 = array_filter($aktiv, function ($u) { return !has_second_factor($u) && ($u['oidcSub'] ?? '') === ''; });
    $gesperrtIp = 0;
    foreach (store_read('logins') ?? [] as $v) if ((int)($v['until'] ?? 0) > time()) $gesperrtIp++;
    $fw = fw_status();
    $ip = integritaet_stand(false)['result'];
    $S = sec();
    $sitz = sess_prune(store_read('sitzungen') ?? []);
    return [
        'kennzahlen' => [
            'fehl24' => $n24(['login_fail', 'kunde_login_fail', 'reauth_fail']), 'anmeldungen24' => $n24(['login', 'kunde_login']),
            'angriffe24' => (int)($fw['zahlen']['angriffe'] ?? 0), 'abgewiesen24' => (int)($fw['zahlen']['abgewiesen'] ?? 0),
            'gesperrteAdressen' => (int)($fw['zahlen']['gesperrteAdressen'] ?? 0) + $gesperrtIp,
            'gesperrteKonten' => count(array_filter($users, function ($u) { return (int)($u['lockedUntil'] ?? 0) > time(); })),
            'sitzungen' => count($sitz), 'kundenOnline' => count(array_unique(array_column(ksess_prune(store_read('kundensitzungen') ?? []), 'kid'))),
            'zugaenge' => count($aktiv), 'admins' => count($admins), 'ohneZweiFaktor' => count($ohne2),
            'adminsOhneZweiFaktor' => count(array_filter($ohne2, function ($u) { return $u['role'] === 'admin'; })),
        ],
        'einstellungen' => ['twofa' => $S['twofa'], 'ipEnabled' => (bool)$S['ipEnabled'], 'geoEnabled' => (bool)$S['geoEnabled'], 'pwMin' => (int)$S['pwMin'],
                            'pwComplex' => (bool)$S['pwComplex'], 'pwLeak' => (bool)($S['pwLeak'] ?? false), 'idleMinutes' => (int)$S['idleMinutes'],
                            'waf' => (string)($fw['fw']['waf'] ?? ''), 'autoSperre' => !empty($fw['fw']['autoSperre']), 'feed' => !empty($fw['fw']['feed'])],
        'dateipruefung' => $ip ? ['ranAt' => $ip['ranAt'] ?? null, 'ok' => !empty($ip['ok']), 'counts' => $ip['counts'] ?? []] : null,
        'backup' => store_read('sicherung'), 'deployment' => store_read('deployment'), 'https' => is_https(),
        'timeline' => sec_timeline($log), 'topIps' => sec_top_ips($log), 'config' => sec_config_checks($users), 'stunden' => fw_stunden(),
        'ereignisse' => array_slice(sec_ereignisse(7)['ereignisse'], 0, 8),
    ];
}

/* Ungenutzte Zugänge: aktive Mitarbeiter mit Anmeldung, deren letzte Anmeldung (bzw. ohne Anmeldung: Anlage) länger als
   $tage Tage zurückliegt und die keine laufende Sitzung haben. Auf Keycloak-Hosts zählt die letzte Anmeldung bei Keycloak
   (oidc_anmeldung_merken). Neueste zuerst nach Inaktivität (älteste oben). Eine Quelle für Konfigurationsprüfung, Modul
   Sicherheit (Reiter Konten) und Wochenbericht. */
const SEC_UNGENUTZT_TAGE = 90;
const SEC_UNGENUTZT_WAHL = [30, 60, 90, 180, 365];
function sec_ungenutzt(int $tage, ?array $users = null): array
{
    $users ??= users_load();
    $aktiv = [];
    foreach (sess_prune(store_read('sitzungen') ?? []) as $v) {
        $uid = (string)($v['uid'] ?? '');
        $aktiv[$uid] = max($aktiv[$uid] ?? 0, (int)($v['seen'] ?? 0));
    }
    $grenze = time() - $tage * 86400;
    $out = [];
    foreach ($users as $u) {
        if (empty($u['active']) || !nutzer_hat_zugang($u) || isset($aktiv[(string)$u['id']])) continue;
        $letzte = ($u['lastLogin'] ?? null) ?: null;
        $ref = $letzte ?: ($u['created'] ?? null);
        $t = $ref ? strtotime((string)$ref) : false;
        if ($t === false || $t >= $grenze) continue;
        $out[] = ['id' => (string)$u['id'], 'name' => (string)$u['name'], 'username' => (string)$u['username'], 'admin' => ($u['role'] ?? '') === 'admin',
                  'rollen' => rollen_text($u), 'lastLogin' => $letzte, 'created' => $u['created'] ?? null, 'nie' => $letzte === null,
                  'tage' => (int)floor((time() - $t) / 86400), 'zentral' => (string)($u['oidcSub'] ?? '') !== ''];
    }
    usort($out, function ($a, $b) { return ($b['tage'] <=> $a['tage']) ?: strcasecmp($a['name'], $b['name']); });
    return ['konten' => $out, 'tage' => $tage, 'wahl' => SEC_UNGENUTZT_WAHL];
}

/* Privilegierte Konten: Administratoren und Inhaber sicherheitsrelevanter Rechte mit Anmeldeschutz, letzter Anmeldung, Sitzungen */
const SEC_KONTEN_RECHTE = ['sicherheit.notfall', 'sicherheit.sehen', 'kunden.bearbeiten', 'wochenangebot.senden', 'sonderposten.senden',
    'einzelangebote.bearbeiten', 'angebote.loeschen', 'hr.verwalten', 'hr.uebersicht', 'protokoll.sehen', 'auswertung.sehen'];
function sec_konten(): array
{
    $users = users_load();
    $roles = rights_roles();
    $kat = perms_katalog();
    $je = [];
    foreach (sess_prune(store_read('sitzungen') ?? []) as $sid => $v) {
        $je[(string)$v['uid']][] = ['sid' => (string)$sid, 'ip' => (string)($v['ip'] ?? ''), 'ua' => (string)($v['ua'] ?? ''), 'created' => $v['created'] ?? null,
                                    'seen' => gmdate('Y-m-d\TH:i:s\Z', (int)($v['seen'] ?? 0)), 'current' => $sid === ($_SESSION['sid'] ?? '')];
    }
    $out = [];
    foreach ($users as $u) {
        if (!nutzer_hat_zugang($u)) continue;
        $admin = ($u['role'] ?? '') === 'admin';
        $heikel = $admin ? [] : array_values(array_intersect(SEC_KONTEN_RECHTE, user_perms($u, $roles)));
        if (!$admin && !$heikel) continue;
        $out[] = ['id' => (string)$u['id'], 'name' => (string)$u['name'], 'username' => (string)$u['username'], 'admin' => $admin, 'aktiv' => !empty($u['active']),
                  'rollen' => rollen_text($u), 'rechte' => array_map(function ($k) use ($kat) { return ['key' => $k, 'label' => $kat[$k]['l'], 'gruppe' => $kat[$k]['g']]; }, $heikel),
                  'totp' => !empty($u['totp']), 'passkeys' => count((array)($u['passkeys'] ?? [])), 'zentral' => (string)($u['oidcSub'] ?? '') !== '',
                  'zweiFaktor' => has_second_factor($u), 'lastLogin' => $u['lastLogin'] ?? null, 'mustChange' => !empty($u['mustChange']),
                  'lockedUntil' => (int)($u['lockedUntil'] ?? 0) > time() ? (int)$u['lockedUntil'] : null,
                  'geraete' => count(geraete_public($u)), 'sitzungen' => $je[(string)$u['id']] ?? []];
    }
    usort($out, function ($a, $b) { return ($b['admin'] <=> $a['admin']) ?: ($b['aktiv'] <=> $a['aktiv']) ?: strcasecmp($a['name'], $b['name']); });
    $aktiv = array_filter($out, function ($k) { return $k['aktiv']; });
    return ['konten' => $out, 'zahlen' => ['admins' => count(array_filter($aktiv, function ($k) { return $k['admin']; })),
            'weitere' => count(array_filter($aktiv, function ($k) { return !$k['admin']; })),
            'ohneZweiFaktor' => count(array_filter($aktiv, function ($k) { return !$k['zweiFaktor'] && !$k['zentral']; })),
            'notfall' => count(array_filter($aktiv, function ($k) { return $k['admin'] || in_array('sicherheit.notfall', array_column($k['rechte'], 'key'), true); }))],
            'rechte' => array_map(function ($k) use ($kat) { return ['key' => $k, 'label' => $kat[$k]['l'] ?? $k]; }, SEC_KONTEN_RECHTE)];
}
