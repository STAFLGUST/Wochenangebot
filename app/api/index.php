<?php
/*
 * Wochenangebot – API
 *
 * Öffentlich:
 *   GET  ?action=offer            veröffentlichtes Angebot
 * Eingabebereich (Anmeldung nötig, Schreibzugriffe zusätzlich mit CSRF-Token):
 *   Rollen: viewer (nur ansehen) < editor (bearbeiten/veröffentlichen) < admin (+ Nutzer, Protokoll)
 *   GET  ?action=status           Anmeldestatus / Ersteinrichtung nötig?
 *   POST ?action=setup            ersten Administrator anlegen (nur solange es keinen Nutzer gibt)
 *   POST ?action=login | logout   Anmeldung mit Benutzername + Passwort
 *   GET  ?action=draft            Entwurf + veröffentlichter Stand
 *   POST ?action=save_draft       Entwurf speichern
 *   POST ?action=discard_draft    Entwurf verwerfen
 *   POST ?action=publish          Entwurf veröffentlichen (vorheriger Stand wird archiviert)
 *   GET  ?action=versions         frühere Veröffentlichungen
 *   GET  ?action=version&id=…     eine frühere Veröffentlichung
 *   POST ?action=change_password
 *   GET  ?action=history_list | history_data   Preisverlauf (Wochen-Stände)
 *   GET  ?action=history_prev&week=&year=      Preise der Vorwoche (jüngste gespeicherte Woche davor)
 *   POST ?action=history_import | history_delete
 *   GET  ?action=stock            Bestand (Mengen, MHD) – nur angemeldet, nie öffentlich
 *   POST ?action=stock_import     Bestandsliste übernehmen (Bearbeiter)
 *   GET  ?action=master           Stammdaten je Artikelnummer (Bezeichnung, Fleischart, Herkunft, Zustand)
 *   POST ?action=master_save      Stammdaten speichern (Bearbeiter)
 *   GET  ?action=users | log      Nutzerliste / Protokoll (nur Administrator)
 *   GET  ?action=security_status  Sicherheitsübersicht (nur Administrator)
 *   POST ?action=security_save | session_end | ip_unblock | user_unlock | geo_update
 *   POST ?action=login_2fa        zweiter Anmeldeschritt (Code aus der Authenticator-App)
 *   POST ?action=twofa_begin | twofa_enable | twofa_disable   eigene Zwei-Faktor-Anmeldung
 *   POST ?action=user_save | user_delete
 *
 * Alle Daten liegen als .php-Dateien mit Zugriffssperre im Datenordner –
 * sie lassen sich auch ohne .htaccess nicht direkt im Browser abrufen.
 */
declare(strict_types=1);

$CFG = require __DIR__ . '/config.php';
require __DIR__ . '/geo.php';
$DATA = rtrim((string)$CFG['data_dir'], '/');
const GUARD = "<?php http_response_code(404); exit; ?>\n";
const CATEGORIES = ['Rind', 'Kalb', 'Schwein', 'Lamm & Schaf', 'Geflügel', 'Knochen', 'Sonstiges'];
const CONDITIONS = ['frisch', 'gefroren', 'frisch-gefroren', 'dry-aged', 'unbekannt'];
const PRICE_STATUS = ['value', 'request', 'none'];

if (!function_exists('mb_substr')) { function mb_substr($s, $start, $len = null) { return $len === null ? substr($s, $start) : substr($s, $start, $len); } }
if (!function_exists('mb_strlen')) { function mb_strlen($s) { return strlen(utf8_decode($s)); } }

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');

set_exception_handler(function (Throwable $e) {
    error_log('[wochenangebot] ' . $e->getMessage());
    respond(['ok' => false, 'error' => 'Interner Fehler auf dem Server.'], 500);
});

/* ---------------- Hilfsfunktionen ---------------- */

function respond(array $data, int $status = 200): void
{
    http_response_code($status);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}
function fail(string $msg, int $status = 400): void { respond(['ok' => false, 'error' => $msg], $status); }

function store_path(string $name): string
{
    global $DATA;
    return $DATA . '/' . $name . '.php';
}
function store_read(string $name)
{
    $p = store_path($name);
    if (!is_file($p)) return null;
    $raw = (string)file_get_contents($p);
    if (strncmp($raw, GUARD, strlen(GUARD)) === 0) $raw = substr($raw, strlen(GUARD));
    $data = json_decode($raw, true);
    return is_array($data) ? $data : null;
}
function store_write(string $name, array $data): void
{
    global $DATA;
    $dir = dirname(store_path($name));
    if (!is_dir($dir) && !@mkdir($dir, 0775, true)) fail('Datenordner kann nicht angelegt werden. Bitte Schreibrechte für „data/“ prüfen.', 500);
    $json = json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    if ($json === false) fail('Daten konnten nicht gespeichert werden.', 500);
    $tmp = store_path($name) . '.' . bin2hex(random_bytes(4)) . '.tmp';
    if (@file_put_contents($tmp, GUARD . $json, LOCK_EX) === false) fail('Speichern fehlgeschlagen. Bitte Schreibrechte für „data/“ prüfen.', 500);
    if (!@rename($tmp, store_path($name))) { @unlink($tmp); fail('Speichern fehlgeschlagen.', 500); }
    if (!is_file($DATA . '/index.php')) @file_put_contents($DATA . '/index.php', GUARD);
}
function store_delete(string $name): void { $p = store_path($name); if (is_file($p)) @unlink($p); }
function store_mtime(string $name): ?int { $p = store_path($name); return is_file($p) ? (int)filemtime($p) : null; }

function body(): array
{
    $raw = file_get_contents('php://input', false, null, 0, 6 * 1024 * 1024 + 1);
    if ($raw === false || strlen($raw) > 6 * 1024 * 1024) fail('Anfrage ist zu groß.', 413);
    $data = json_decode($raw ?: '{}', true);
    if (!is_array($data)) fail('Ungültige Anfrage.');
    return $data;
}
function now(): string { return gmdate('Y-m-d\TH:i:s\Z'); }

/* ---------------- Nutzer ---------------- */

const ROLES = ['viewer' => 1, 'editor' => 2, 'admin' => 3];
const ROLE_LABELS = ['viewer' => 'Nur ansehen', 'editor' => 'Bearbeiter', 'admin' => 'Administrator'];

/* Exklusive Sperre für Lese-Ändere-Schreibe-Vorgänge (Nutzerliste, Protokoll) */
function with_lock(string $name, callable $fn)
{
    global $DATA;
    if (!is_dir($DATA) && !@mkdir($DATA, 0775, true)) fail('Datenordner kann nicht angelegt werden.', 500);
    static $held = [];
    if (!empty($held[$name])) return $fn();             // bereits gesperrt (verschachtelter Aufruf)
    $fh = @fopen($DATA . '/.' . $name . '.lock', 'c');
    if ($fh) flock($fh, LOCK_EX);
    $held[$name] = true;
    try { return $fn(); } finally { $held[$name] = false; if ($fh) { flock($fh, LOCK_UN); fclose($fh); } }
}
/* Nutzerliste; bisherige Einzel-Passwort-Installation wird einmalig zum Nutzer „admin“ */
function users_load(): array
{
    $u = store_read('nutzer');
    if (is_array($u) && isset($u['users'])) return $u['users'];
    $old = store_read('admin');
    if ($old && !empty($old['hash'])) {
        return with_lock('nutzer', function () use ($old) {
            $u = store_read('nutzer');
            if (is_array($u) && isset($u['users'])) return $u['users'];
            $users = [[
                'id' => 'u' . bin2hex(random_bytes(6)), 'username' => 'admin', 'name' => 'Administrator', 'role' => 'admin',
                'active' => true, 'hash' => (string)$old['hash'], 'mustChange' => false, 'sv' => 1,
                'created' => $old['created'] ?? now(), 'createdBy' => 'Übernahme', 'lastLogin' => null,
            ]];
            store_write('nutzer', ['users' => $users]);
            store_delete('admin');
            return $users;
        });
    }
    return [];
}
function users_save(array $users): void { store_write('nutzer', ['users' => array_values($users)]); }
function user_find(array $users, string $id): ?int { foreach ($users as $i => $u) if ($u['id'] === $id) return $i; return null; }
function user_public(array $u): array
{
    return ['id' => $u['id'], 'username' => $u['username'], 'name' => $u['name'], 'role' => $u['role'], 'active' => (bool)$u['active'],
            'mustChange' => (bool)($u['mustChange'] ?? false), 'created' => $u['created'] ?? null, 'createdBy' => $u['createdBy'] ?? '',
            'lastLogin' => $u['lastLogin'] ?? null, 'changed' => $u['changed'] ?? null,
            'twofa' => !empty($u['totp']), 'lockedUntil' => (int)($u['lockedUntil'] ?? 0) > time() ? (int)$u['lockedUntil'] : null];
}
function active_admins(array $users): int { $n = 0; foreach ($users as $u) if ($u['role'] === 'admin' && $u['active']) $n++; return $n; }
function clean_username($v): string
{
    $v = is_string($v) ? strtolower(trim($v)) : '';
    if (!preg_match('/^[a-z0-9][a-z0-9._-]{1,31}$/', $v)) throw new InvalidArgumentException('Benutzername: 2–32 Zeichen, nur Buchstaben a–z, Ziffern, Punkt, Binde- und Unterstrich.');
    return $v;
}
const COMMON_PASSWORDS = ['passwort', 'password', 'passwort1', 'passwort123', 'password1', 'password123', '123456789', '1234567890', '12345678910',
    'qwertz123', 'qwertzuiop', 'qwertyuiop', 'hallo12345', 'hallohallo', 'sommer2026', 'winter2026', 'herbst2026', 'fruehling2026', 'frühling2026',
    'sommer2025', 'winter2025', 'willkommen', 'willkommen1', 'willkommen123', 'administrator', 'admin12345', 'adminadmin', 'standardfleisch',
    'standard-fleisch', 'fleischmeister', 'wochenangebot', 'geheim1234', 'iloveyou12', 'abc1234567', '0000000000', '1111111111', 'letmein123'];
function check_password($pw, string $username = ''): string
{
    $pw = is_string($pw) ? $pw : '';
    $S = sec();
    $min = max(10, (int)$S['pwMin']);
    if (mb_strlen($pw) < $min) throw new InvalidArgumentException("Das Passwort muss mindestens $min Zeichen lang sein.");
    if (strlen($pw) > 200) throw new InvalidArgumentException('Das Passwort ist zu lang.');
    $low = mb_strtolower($pw);
    if (in_array($low, COMMON_PASSWORDS, true) || preg_match('/^(.)\1+$/u', $pw)) throw new InvalidArgumentException('Dieses Passwort ist zu leicht zu erraten. Bitte ein anderes wählen.');
    if ($username !== '' && strlen($username) >= 3 && strpos($low, strtolower($username)) !== false) throw new InvalidArgumentException('Das Passwort darf den Benutzernamen nicht enthalten.');
    if (!empty($S['pwComplex'])) {
        $classes = (int)preg_match('/[a-zäöüß]/u', $pw) + (int)preg_match('/[A-ZÄÖÜ]/u', $pw) + (int)preg_match('/\d/', $pw) + (int)preg_match('/[^\p{L}\d]/u', $pw);
        if ($classes < 3) throw new InvalidArgumentException('Das Passwort braucht mindestens drei der vier Zeichenarten: Kleinbuchstaben, Großbuchstaben, Ziffern, Sonderzeichen.');
    }
    return $pw;
}

/* ---------------- Sicherheitseinstellungen ---------------- */

const SEC_DEFAULTS = ['twofa' => 'off', 'pwMin' => 10, 'pwComplex' => false, 'idleMinutes' => 480,
                      'ipEnabled' => false, 'adminIps' => [], 'lockAfter' => 10, 'lockMinutes' => 15,
                      'geoEnabled' => false, 'geoMode' => 'block', 'geoCountries' => [], 'geoScope' => 'admin'];
$SEC = null;
function sec(): array
{
    global $SEC;
    if ($SEC === null) $SEC = array_merge(SEC_DEFAULTS, store_read('sicherheit') ?? []);
    return $SEC;
}
/* Ländersperre: true, wenn diese Adresse nach den Einstellungen $S gesperrt ist.
   Nie gesperrt: freigegebene Adressen, interne Adressen und Adressen ohne bekanntes Land. */
function geo_blocked(string $ip, array $S): ?string
{
    if (empty($S['geoEnabled']) || !$S['geoCountries']) return null;
    if ($S['adminIps'] && ip_allowed($ip, $S['adminIps'])) return null;
    $cc = geo_country($ip);
    if ($cc === null) return null;
    $listed = in_array($cc, $S['geoCountries'], true);
    return ($S['geoMode'] === 'allow' ? !$listed : $listed) ? $cc : null;
}
function geo_count(string $cc): void
{
    try {
        with_lock('laendersperre', function () use ($cc) {
            $a = store_read('laendersperre') ?? [];
            $day = gmdate('Y-m-d');
            if (($a['day'] ?? '') !== $day) { $a['days'][$a['day'] ?? $day] = $a['today'] ?? 0; $a['day'] = $day; $a['today'] = 0; }
            $a['days'] = array_slice($a['days'] ?? [], -30, null, true);
            $a['today'] = ($a['today'] ?? 0) + 1;
            $c = $a['cc'][$cc] ?? ['n' => 0];
            $a['cc'][$cc] = ['n' => $c['n'] + 1, 'last' => now()];
            store_write('laendersperre', $a);
        });
    } catch (Throwable $e) { /* Zählung ist nicht kritisch */ }
}
function ip_in(string $ip, string $cidr): bool
{
    $parts = explode('/', trim($cidr), 2);
    $net = @inet_pton($parts[0]);
    $adr = @inet_pton($ip);
    if ($net === false || $adr === false || strlen($net) !== strlen($adr)) return false;
    $bits = isset($parts[1]) ? (int)$parts[1] : strlen($net) * 8;
    $bytes = intdiv($bits, 8);
    if (substr($net, 0, $bytes) !== substr($adr, 0, $bytes)) return false;
    $rest = $bits % 8;
    if (!$rest) return true;
    $mask = chr((0xff << (8 - $rest)) & 0xff);
    return (($net[$bytes] & $mask) === ($adr[$bytes] & $mask));
}
function ip_allowed(string $ip, array $list): bool { foreach ($list as $c) if (ip_in($ip, $c)) return true; return false; }
function valid_cidr(string $c): bool
{
    $p = explode('/', trim($c), 2);
    if (!filter_var($p[0], FILTER_VALIDATE_IP)) return false;
    if (!isset($p[1])) return true;
    $max = strpos($p[0], ':') !== false ? 128 : 32;
    return ctype_digit($p[1]) && (int)$p[1] >= 8 && (int)$p[1] <= $max;
}
function twofa_required(array $u): bool { $m = sec()['twofa']; return $m === 'all' || ($m === 'admins' && $u['role'] === 'admin'); }
function is_https(): bool { return (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https'); }

/* ---------------- Zwei-Faktor (TOTP, RFC 6238) ---------------- */

const B32 = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ234567';
function b32_encode(string $bin): string
{
    $bits = ''; foreach (str_split($bin) as $c) $bits .= str_pad(decbin(ord($c)), 8, '0', STR_PAD_LEFT);
    $out = ''; foreach (str_split($bits, 5) as $chunk) $out .= B32[bindec(str_pad($chunk, 5, '0'))];
    return $out;
}
function b32_decode(string $s): string
{
    $s = strtoupper(preg_replace('/[^A-Za-z2-7]/', '', $s));
    $bits = ''; foreach (str_split($s) as $c) { $v = strpos(B32, $c); if ($v === false) return ''; $bits .= str_pad(decbin($v), 5, '0', STR_PAD_LEFT); }
    $out = ''; foreach (str_split($bits, 8) as $b) if (strlen($b) === 8) $out .= chr(bindec($b));
    return $out;
}
function totp_at(string $secret, int $step): string
{
    $h = hash_hmac('sha1', pack('N*', 0, $step), b32_decode($secret), true);
    $o = ord($h[19]) & 0x0f;
    $n = ((ord($h[$o]) & 0x7f) << 24) | (ord($h[$o + 1]) << 16) | (ord($h[$o + 2]) << 8) | ord($h[$o + 3]);
    return str_pad((string)($n % 1000000), 6, '0', STR_PAD_LEFT);
}
/* Liefert den verwendeten Zeitschritt oder null; jeder Code gilt nur einmal */
function totp_check(string $secret, string $code, int $last = 0): ?int
{
    $code = preg_replace('/\s+/', '', $code);
    if (!preg_match('/^\d{6}$/', $code)) return null;
    $now = intdiv(time(), 30);
    for ($d = -1; $d <= 1; $d++) { $st = $now + $d; if ($st > $last && hash_equals(totp_at($secret, $st), $code)) return $st; }
    return null;
}
function recovery_codes(): array
{
    $abc = 'abcdefghjkmnpqrstuvwxyz23456789';
    $out = [];
    for ($i = 0; $i < 10; $i++) { $c = ''; for ($j = 0; $j < 10; $j++) $c .= $abc[random_int(0, strlen($abc) - 1)]; $out[] = substr($c, 0, 5) . '-' . substr($c, 5); }
    return $out;
}
function rc_hash(string $c): string { return hash('sha256', strtolower(preg_replace('/[^A-Za-z0-9]/', '', $c))); }

/* ---------------- Sitzungsregister ---------------- */

function sess_prune(array $list): array
{
    $max = (int)sec()['idleMinutes'] * 60;
    foreach ($list as $k => $v) if ((int)($v['seen'] ?? 0) < time() - $max) unset($list[$k]);
    return $list;
}
function sess_register(array $u): void
{
    with_lock('sitzungen', function () use ($u) {
        $list = sess_prune(store_read('sitzungen') ?? []);
        $sid = bin2hex(random_bytes(12));
        $list[$sid] = ['uid' => $u['id'], 'ip' => client_ip(), 'ua' => mb_substr((string)($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 240), 'created' => now(), 'seen' => time()];
        store_write('sitzungen', $list);
        $_SESSION['sid'] = $sid;
    });
}
function sess_remove(callable $match): int
{
    return with_lock('sitzungen', function () use ($match) {
        $list = store_read('sitzungen') ?? [];
        $n = 0;
        foreach ($list as $k => $v) if ($match($k, $v)) { unset($list[$k]); $n++; }
        if ($n) store_write('sitzungen', $list);
        return $n;
    });
}

/* ---------------- Sitzung ---------------- */

function start_session(): void
{
    global $CFG;
    if (session_status() === PHP_SESSION_ACTIVE) return;
    $https = is_https();
    ini_set('session.use_strict_mode', '1');
    ini_set('session.use_only_cookies', '1');
    session_name('WA_ADMIN');
    session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'secure' => $https, 'httponly' => true, 'samesite' => 'Strict']);
    session_start();
    $max = (int)sec()['idleMinutes'] * 60;
    if (!empty($_SESSION['uid']) && (time() - (int)($_SESSION['seen'] ?? 0)) > $max) { $_SESSION = []; session_regenerate_id(true); }
    if (!empty($_SESSION['uid'])) $_SESSION['seen'] = time();
}
/* Angemeldeter Nutzer – Rolle und Status werden bei jeder Anfrage frisch gelesen */
$ME = null;
function current_user(): ?array
{
    global $ME;
    if ($ME !== null) return $ME;
    start_session();
    if (empty($_SESSION['uid'])) return null;
    $users = users_load();
    $i = user_find($users, (string)$_SESSION['uid']);
    if ($i === null || !$users[$i]['active'] || (int)$users[$i]['sv'] !== (int)($_SESSION['sv'] ?? -1)) { $_SESSION = []; return null; }
    // Sitzung muss im Register stehen (Administrator kann sie beenden)
    $sid = (string)($_SESSION['sid'] ?? '');
    $reg = store_read('sitzungen') ?? [];
    if ($sid === '' || !isset($reg[$sid]) || $reg[$sid]['uid'] !== $users[$i]['id']) { $_SESSION = []; return null; }
    if ((int)$reg[$sid]['seen'] < time() - 60 || $reg[$sid]['ip'] !== client_ip()) {
        with_lock('sitzungen', function () use ($sid) {
            $l = store_read('sitzungen') ?? [];
            if (isset($l[$sid])) { $l[$sid]['seen'] = time(); $l[$sid]['ip'] = client_ip(); store_write('sitzungen', sess_prune($l)); }
        });
    }
    return $ME = $users[$i];
}
function require_auth(bool $write = false, string $role = 'viewer'): array
{
    $u = current_user();
    if (!$u) fail('Bitte erneut anmelden.', 401);
    if ($write) {
        $tok = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
        if (!is_string($tok) || !hash_equals((string)($_SESSION['csrf'] ?? ''), $tok)) fail('Sicherheitsprüfung fehlgeschlagen – bitte Seite neu laden.', 403);
    }
    if (!empty($u['mustChange'])) fail('Bitte zuerst ein neues Passwort festlegen.', 403);
    if (twofa_required($u) && empty($u['totp'])) fail('Bitte zuerst die Zwei-Faktor-Anmeldung einrichten.', 403);
    if (ROLES[$u['role']] < ROLES[$role]) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
    return $u;
}
function sign_in(array $u): string
{
    global $ME;
    session_regenerate_id(true);
    $_SESSION['uid'] = $u['id'];
    $_SESSION['sv'] = (int)$u['sv'];
    $_SESSION['seen'] = time();
    $_SESSION['csrf'] = bin2hex(random_bytes(32));
    unset($_SESSION['pend'], $_SESSION['totpPending']);
    sess_register($u);
    $ME = $u;
    return $_SESSION['csrf'];
}
function me_payload(array $u): array
{
    return ['id' => $u['id'], 'username' => $u['username'], 'name' => $u['name'], 'role' => $u['role'], 'mustChange' => (bool)($u['mustChange'] ?? false),
            'twofa' => !empty($u['totp']), 'needTwofa' => twofa_required($u) && empty($u['totp']), 'twofaRequired' => twofa_required($u)];
}
/* Nutzer innerhalb der Sperre ändern und speichern */
function user_update(string $id, callable $fn): ?array
{
    return with_lock('nutzer', function () use ($id, $fn) {
        $users = users_load();
        $i = user_find($users, $id);
        if ($i === null) return null;
        $fn($users[$i]);
        users_save($users);
        return $users[$i];
    });
}
function require_csrf(): void
{
    $tok = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
    if (!is_string($tok) || !hash_equals((string)($_SESSION['csrf'] ?? ''), $tok)) fail('Sicherheitsprüfung fehlgeschlagen – bitte Seite neu laden.', 403);
}

/* ---------------- Protokoll ---------------- */

/* Ein Eintrag je Vorgang; fortlaufendes Bearbeiten des Entwurfs durch dieselbe Person wird zusammengefasst */
function audit(string $a, string $s, array $d = [], ?array $who = null, bool $merge = false): void
{
    global $ME;
    try {
        $who = $who ?? $ME;
        $month = gmdate('Y-m');
        with_lock('protokoll', function () use ($a, $s, $d, $who, $merge, $month) {
            $log = store_read('protokoll/' . $month) ?? [];
            $last = $log ? $log[count($log) - 1] : null;
            $u = $who['username'] ?? '';
            if ($merge && $last && $last['a'] === $a && $last['u'] === $u && strtotime($last['t']) > time() - 1800) {
                $last['d'] = changes_merge($last['d'] ?? [], $d);
                $last['t'] = now();
                $last['s'] = $s;
                if (!$last['d']) array_pop($log); else $log[count($log) - 1] = $last;
            } else {
                if ($merge && !$d) return;
                $e = ['t' => now(), 'u' => $u, 'n' => $who['name'] ?? '', 'r' => $who['role'] ?? '', 'ip' => client_ip(), 'a' => $a, 's' => $s];
                if ($d) $e['d'] = $d;
                $log[] = $e;
            }
            store_write('protokoll/' . $month, $log);
        });
    } catch (Throwable $e) {
        error_log('[wochenangebot] Protokoll: ' . $e->getMessage());
    }
}
function price_text($p): string
{
    if (!is_array($p)) return '';
    $st = $p['status'] ?? 'none';
    if ($st === 'value') {
        $v = (float)$p['value'];
        $t = number_format($v, abs($v * 100 - round($v * 100)) > 1e-6 ? 3 : 2, ',', '.') . ' €/kg';
    } elseif ($st === 'request') $t = 'auf Anfrage';
    else $t = 'ohne Preis';
    return $t;
}
function alts_text($alts): string
{
    $out = [];
    foreach ((array)$alts as $p) $out[] = trim(($p['label'] ?? '') . ': ' . price_text($p));
    return implode(' · ', $out);
}
/* Änderungen zwischen zwei Ständen als Liste {k, code, name, f, from, to} */
function changes_between(?array $a, array $b): array
{
    $out = [];
    $am = $a['meta'] ?? [];
    $bm = $b['meta'] ?? [];
    $wa = isset($am['week']) ? ($am['week'] . '/' . ($am['year'] ?? '')) : '';
    $wb = isset($bm['week']) ? ($bm['week'] . '/' . ($bm['year'] ?? '')) : '';
    if ($a && $wa !== $wb) $out[] = ['k' => 'm|week', 'code' => '', 'name' => 'Kopfdaten', 'f' => 'Kalenderwoche', 'from' => $wa, 'to' => $wb];
    if ($a && (string)($am['notice'] ?? '') !== (string)($bm['notice'] ?? '')) $out[] = ['k' => 'm|notice', 'code' => '', 'name' => 'Kopfdaten', 'f' => 'Hinweis', 'from' => (string)($am['notice'] ?? ''), 'to' => (string)($bm['notice'] ?? '')];
    $ga = []; foreach (($a['groups'] ?? []) as $g) $ga[$g['id']] = $g;
    $gb = []; foreach (($b['groups'] ?? []) as $g) $gb[$g['id']] = $g;
    foreach ($gb as $id => $g) {
        if (!isset($ga[$id])) continue;
        if ($ga[$id]['name'] !== $g['name']) $out[] = ['k' => "g$id|name", 'code' => '', 'name' => 'Gruppe', 'f' => 'Gruppenname', 'from' => $ga[$id]['name'], 'to' => $g['name']];
        if (($ga[$id]['section'] ?? '') !== ($g['section'] ?? '')) $out[] = ['k' => "g$id|section", 'code' => '', 'name' => $g['name'], 'f' => 'Bereich', 'from' => $ga[$id]['section'] ?? '', 'to' => $g['section'] ?? ''];
    }
    $gname = function ($id) use ($ga, $gb) { return $gb[$id]['name'] ?? $ga[$id]['name'] ?? ''; };
    $ia = []; foreach (($a['items'] ?? []) as $it) $ia[$it['id']] = $it;
    $ib = []; foreach (($b['items'] ?? []) as $it) $ib[$it['id']] = $it;
    $fields = ['code' => 'Art.-Nr.', 'name' => 'Bezeichnung', 'category' => 'Fleischart', 'origin' => 'Herkunft', 'condition' => 'Zustand'];
    foreach ($ib as $id => $it) {
        $code = (string)($it['code'] ?? '');
        if (!isset($ia[$id])) {
            if ($a) $out[] = ['k' => "$id|+", 'code' => $code, 'name' => $it['name'], 'f' => 'Neuer Artikel', 'from' => '', 'to' => price_text($it['price']) . ' · ' . $gname($it['groupId'])];
            continue;
        }
        $o = $ia[$id];
        foreach ($fields as $f => $label) {
            if ((string)($o[$f] ?? '') !== (string)($it[$f] ?? '')) $out[] = ['k' => "$id|$f", 'code' => $code, 'name' => $it['name'], 'f' => $label, 'from' => (string)($o[$f] ?? ''), 'to' => (string)($it[$f] ?? '')];
        }
        if (($o['groupId'] ?? '') !== ($it['groupId'] ?? '')) $out[] = ['k' => "$id|groupId", 'code' => $code, 'name' => $it['name'], 'f' => 'Gruppe', 'from' => $gname($o['groupId']), 'to' => $gname($it['groupId'])];
        if (price_text($o['price'] ?? null) !== price_text($it['price'] ?? null)) $out[] = ['k' => "$id|price", 'code' => $code, 'name' => $it['name'], 'f' => 'Preis', 'from' => price_text($o['price'] ?? null), 'to' => price_text($it['price'] ?? null)];
        if ((string)($o['price']['label'] ?? '') !== (string)($it['price']['label'] ?? '')) $out[] = ['k' => "$id|plabel", 'code' => $code, 'name' => $it['name'], 'f' => 'Preisbezeichnung', 'from' => (string)($o['price']['label'] ?? ''), 'to' => (string)($it['price']['label'] ?? '')];
        if (alts_text($o['altPrices'] ?? []) !== alts_text($it['altPrices'] ?? [])) $out[] = ['k' => "$id|alts", 'code' => $code, 'name' => $it['name'], 'f' => 'Zusatzpreise', 'from' => alts_text($o['altPrices'] ?? []), 'to' => alts_text($it['altPrices'] ?? [])];
    }
    foreach ($ia as $id => $it) {
        if (!isset($ib[$id])) $out[] = ['k' => "$id|-", 'code' => (string)($it['code'] ?? ''), 'name' => $it['name'], 'f' => 'Artikel entfernt', 'from' => price_text($it['price']), 'to' => ''];
    }
    return $out;
}
/* Neue Änderungen in einen bestehenden Eintrag einarbeiten: Ausgangswert bleibt, Endwert wird aktualisiert */
function changes_merge(array $old, array $new): array
{
    $idx = [];
    foreach ($old as $i => $c) $idx[$c['k']] = $i;
    foreach ($new as $c) {
        [$id, $f] = explode('|', $c['k'], 2) + [1 => ''];
        if ($f === '-' && isset($idx["$id|+"])) {           // neu angelegt und wieder entfernt → nichts übrig
            foreach ($old as $i => $o) if (strpos($o['k'], "$id|") === 0) unset($old[$i]);
            $old = array_values($old);
            $idx = []; foreach ($old as $i => $o) $idx[$o['k']] = $i;
            continue;
        }
        if ($f !== '+' && $f !== '-' && isset($idx["$id|+"])) { // Bearbeitung eines neuen Artikels → Eintrag „neu“ aktualisieren
            $o = &$old[$idx["$id|+"]];
            $o['code'] = $c['code']; $o['name'] = $c['name'];
            if ($f === 'price') $o['to'] = preg_replace('/^[^·]*/u', $c['to'] . ' ', $o['to'], 1);
            unset($o);
            continue;
        }
        if (isset($idx[$c['k']])) {
            $o = &$old[$idx[$c['k']]];
            $o['to'] = $c['to']; $o['code'] = $c['code']; $o['name'] = $c['name'];
            $same = $o['from'] === $o['to'];
            unset($o);
            if ($same) {
                unset($old[$idx[$c['k']]]);
                $old = array_values($old);
                $idx = []; foreach ($old as $i => $o2) $idx[$o2['k']] = $i;
            }
        } else {
            $old[] = $c;
            $idx[$c['k']] = count($old) - 1;
        }
    }
    return array_slice(array_values($old), 0, 2000);
}
function changes_summary(array $d): string
{
    $p = $n = $r = $e = 0;
    foreach ($d as $c) {
        $f = explode('|', $c['k'], 2)[1] ?? '';
        if ($f === 'price') $p++; elseif ($f === '+') $n++; elseif ($f === '-') $r++; else $e++;
    }
    $parts = [];
    if ($p) $parts[] = $p . ($p === 1 ? ' Preis' : ' Preise') . ' geändert';
    if ($n) $parts[] = $n . ' Artikel neu';
    if ($r) $parts[] = $r . ' Artikel entfernt';
    if ($e) $parts[] = $e . ($e === 1 ? ' weitere Änderung' : ' weitere Änderungen');
    return $parts ? implode(', ', $parts) : 'keine Änderungen';
}

/* Anmeldeversuche begrenzen */
function client_ip(): string
{
    $ip = (string)($_SERVER['REMOTE_ADDR'] ?? '');
    // Hinter dem eigenen Proxy (Caddy im Docker-Netz) die weitergereichte Besucher-IP verwenden
    $private = filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false;
    $fwd = (string)($_SERVER['HTTP_X_FORWARDED_FOR'] ?? '');
    if ($private && $fwd !== '') {
        $parts = array_map('trim', explode(',', $fwd));
        $last = end($parts);
        if (filter_var($last, FILTER_VALIDATE_IP)) return $last;
    }
    return $ip;
}
function client_key(): string { return hash('sha256', client_ip()); }
function attempts_check(): void
{
    $a = store_read('logins') ?? [];
    $k = client_key();
    if (!empty($a[$k]['until']) && $a[$k]['until'] > time()) {
        fail('Zu viele Fehlversuche. Bitte in ' . (int)ceil(($a[$k]['until'] - time()) / 60) . ' Minuten erneut versuchen.', 429);
    }
}
function attempts_record(bool $ok): void
{
    global $CFG;
    $a = store_read('logins') ?? [];
    $k = client_key();
    foreach ($a as $kk => $v) if (($v['until'] ?? 0) < time() && ($v['t'] ?? 0) < time() - 86400) unset($a[$kk]);
    if ($ok) unset($a[$k]);
    else {
        $n = (int)($a[$k]['n'] ?? 0) + 1;
        $a[$k] = ['n' => $n, 't' => time(), 'ip' => client_ip(), 'until' => $n >= (int)$CFG['max_attempts'] ? time() + 60 * (int)$CFG['lock_minutes'] : 0];
        if ($n >= (int)$CFG['max_attempts']) $a[$k]['n'] = 0;
    }
    store_write('logins', $a);
}

/* ---------------- Datenprüfung ---------------- */

function s($v, int $max, bool $allowEmpty = true): ?string
{
    if ($v === null) return null;
    if (!is_string($v) && !is_int($v) && !is_float($v)) return null;
    $v = trim(preg_replace('/\s+/u', ' ', (string)$v) ?? '');
    if (!$allowEmpty && $v === '') return null;
    return mb_substr($v, 0, $max);
}
function clean_price($p, string $where): array
{
    if (!is_array($p)) throw new InvalidArgumentException("Preisangabe fehlt ($where).");
    $st = $p['status'] ?? '';
    if (!in_array($st, PRICE_STATUS, true)) throw new InvalidArgumentException("Ungültiger Preisstatus ($where).");
    $out = ['status' => $st];
    if ($st === 'value') {
        $v = $p['value'] ?? null;
        if (!is_int($v) && !is_float($v)) throw new InvalidArgumentException("Preis fehlt ($where).");
        $v = (float)$v;
        if ($v < 0 || $v >= 100000) throw new InvalidArgumentException("Preis außerhalb des gültigen Bereichs ($where).");
        $out['value'] = round($v, 4);
    }
    $raw = s($p['raw'] ?? null, 60);
    if ($raw !== null && $raw !== '') $out['raw'] = $raw;
    $label = s($p['label'] ?? null, 40);
    if ($label !== null && $label !== '') $out['label'] = $label;
    return $out;
}
/* Übernimmt nur bekannte Felder in bekannten Formaten */
function clean_model($m, bool $strict): array
{
    if (!is_array($m)) throw new InvalidArgumentException('Daten fehlen.');
    $meta = is_array($m['meta'] ?? null) ? $m['meta'] : [];
    $week = $meta['week'] ?? null;
    $year = $meta['year'] ?? null;
    $week = is_int($week) && $week >= 1 && $week <= 53 ? $week : null;
    $year = is_int($year) && $year >= 2000 && $year <= 2100 ? $year : null;
    if ($strict && ($week === null || $year === null)) throw new InvalidArgumentException('Kalenderwoche und Jahr müssen angegeben sein.');
    $outMeta = ['week' => $week, 'year' => $year, 'notice' => s($meta['notice'] ?? '', 120) ?? ''];
    foreach (['title' => 200, 'source' => 200, 'sheetName' => 100] as $f => $max) {
        $v = s($meta[$f] ?? null, $max);
        if ($v !== null && $v !== '') $outMeta[$f] = $v;
    }

    $groups = [];
    $gids = [];
    foreach (array_slice(is_array($m['groups'] ?? null) ? $m['groups'] : [], 0, 1000) as $g) {
        if (!is_array($g)) continue;
        $id = s($g['id'] ?? null, 40, false);
        if ($id === null || !preg_match('/^[A-Za-z0-9_-]+$/', $id) || isset($gids[$id])) throw new InvalidArgumentException('Ungültige Gruppen-ID.');
        $name = s($g['name'] ?? null, 200, false);
        if ($name === null) throw new InvalidArgumentException('Eine Angebotsgruppe hat keinen Namen.');
        $gids[$id] = true;
        $groups[] = ['id' => $id, 'name' => $name, 'section' => s($g['section'] ?? '', 200) ?? ''];
    }

    $items = [];
    $iids = [];
    $src = is_array($m['items'] ?? null) ? $m['items'] : [];
    if (count($src) > 5000) throw new InvalidArgumentException('Zu viele Artikel (max. 5000).');
    foreach ($src as $it) {
        if (!is_array($it)) continue;
        $id = s($it['id'] ?? null, 40, false);
        if ($id === null || !preg_match('/^[A-Za-z0-9_-]+$/', $id) || isset($iids[$id])) throw new InvalidArgumentException('Ungültige Artikel-ID.');
        $iids[$id] = true;
        $name = s($it['name'] ?? null, 200, false);
        if ($name === null) throw new InvalidArgumentException('Ein Artikel hat keine Bezeichnung.');
        $code = s($it['code'] ?? null, 20);
        if ($code === '') $code = null;
        if ($code !== null && !preg_match('#^[0-9A-Za-z./-]+$#', $code)) throw new InvalidArgumentException("Artikelnummer „{$code}“ ist ungültig.");
        $gid = s($it['groupId'] ?? null, 40);
        if ($gid === null || !isset($gids[$gid])) throw new InvalidArgumentException("Artikel „{$name}“ ist keiner gültigen Gruppe zugeordnet.");
        $cat = $it['category'] ?? '';
        if (!in_array($cat, CATEGORIES, true)) $cat = 'Sonstiges';
        $cond = $it['condition'] ?? '';
        if (!in_array($cond, CONDITIONS, true)) $cond = 'unbekannt';
        $origin = s($it['origin'] ?? null, 60);
        $alts = [];
        foreach (array_slice(is_array($it['altPrices'] ?? null) ? $it['altPrices'] : [], 0, 5) as $ap) $alts[] = clean_price($ap, $name);
        $row = [
            'id' => $id, 'code' => $code, 'name' => $name,
            'category' => $cat, 'origin' => ($origin === '' ? null : $origin), 'condition' => $cond,
            'groupId' => $gid, 'price' => clean_price($it['price'] ?? null, $name), 'altPrices' => $alts,
        ];
        $nr = s($it['nameRaw'] ?? null, 300);
        if ($nr !== null && $nr !== '' && $nr !== $name) $row['nameRaw'] = $nr;
        $cell = s($it['cell'] ?? null, 20);
        if ($cell !== null && $cell !== '') $row['cell'] = $cell;
        $items[] = $row;
    }
    if ($strict && !$items) throw new InvalidArgumentException('Das Angebot enthält keine Artikel.');
    $used = [];
    foreach ($items as $it) $used[$it['groupId']] = true;
    if ($strict) $groups = array_values(array_filter($groups, function ($g) use ($used) { return isset($used[$g['id']]); }));
    $sections = [];
    foreach ($groups as $g) if ($g['section'] !== '' && !in_array($g['section'], $sections, true)) $sections[] = $g['section'];
    return ['meta' => $outMeta, 'sections' => $sections, 'groups' => $groups, 'items' => $items];
}

/* ---------------- Preisverlauf ---------------- */

function history_id(int $week, int $year): string { return sprintf('%04d-%02d', $year, $week); }
function history_ids(): array
{
    $ids = [];
    foreach (glob(dirname(store_path('historie/x')) . '/*.php') ?: [] as $f) {
        $id = basename($f, '.php');
        if (preg_match('/^\d{4}-\d{2}$/', $id)) $ids[] = $id;
    }
    sort($ids);
    return $ids;
}
/* Preis-Stand einer Woche aus einem veröffentlichten Angebot */
function history_from_model(array $m, string $origin, ?string $at): ?array
{
    $w = $m['meta']['week'] ?? null;
    $y = $m['meta']['year'] ?? null;
    if (!is_int($w) || !is_int($y)) return null;
    $gn = [];
    foreach (($m['groups'] ?? []) as $g) $gn[$g['id']] = $g['name'];
    $items = [];
    foreach (($m['items'] ?? []) as $it) {
        $row = ['code' => $it['code'] ?? null, 'name' => (string)($it['name'] ?? ''), 'group' => $gn[$it['groupId'] ?? ''] ?? '',
                'category' => $it['category'] ?? 'Sonstiges', 'price' => $it['price'] ?? ['status' => 'none']];
        if (!empty($it['altPrices'])) $row['altPrices'] = $it['altPrices'];
        $items[] = $row;
    }
    return ['week' => $w, 'year' => $y, 'origin' => $origin, 'source' => (string)($m['meta']['source'] ?? ''), 'savedAt' => $at ?: now(), 'items' => $items];
}
/* Bisherige Veröffentlichungen einmalig in den Preisverlauf übernehmen (gelöschte Wochen ausgenommen) */
function history_backfill(): void
{
    $have = array_flip(history_ids());
    $deleted = array_flip(store_read('historie_geloescht') ?? []);
    $sources = [];
    foreach (glob(dirname(store_path('versionen/x')) . '/*.php') ?: [] as $f) $sources[] = store_read('versionen/' . basename($f, '.php'));
    $sources[] = store_read('angebot');
    $cand = [];
    foreach ($sources as $m) {
        if (!$m) continue;
        $h = history_from_model($m, 'Veröffentlichung', $m['publishedAt'] ?? null);
        if (!$h) continue;
        $id = history_id($h['week'], $h['year']);
        if (isset($have[$id]) || isset($deleted[$id])) continue;
        if (!isset($cand[$id]) || strcmp((string)$h['savedAt'], (string)$cand[$id]['savedAt']) > 0) $cand[$id] = $h;
    }
    foreach ($cand as $id => $h) store_write('historie/' . $id, $h);
}
function history_undelete(string $id): void
{
    $del = store_read('historie_geloescht') ?? [];
    if (in_array($id, $del, true)) store_write('historie_geloescht', array_values(array_diff($del, [$id])));
}
function clean_history_items($items): array
{
    if (!is_array($items) || !$items) throw new InvalidArgumentException('Die Woche enthält keine Artikel.');
    if (count($items) > 5000) throw new InvalidArgumentException('Zu viele Artikel (max. 5000).');
    $out = [];
    foreach ($items as $it) {
        if (!is_array($it)) continue;
        $name = s($it['name'] ?? null, 200, false);
        if ($name === null) continue;
        $code = s($it['code'] ?? null, 20);
        if ($code === '' || ($code !== null && !preg_match('#^[0-9A-Za-z./-]+$#', $code))) $code = null;
        $cat = in_array($it['category'] ?? '', CATEGORIES, true) ? $it['category'] : 'Sonstiges';
        $row = ['code' => $code, 'name' => $name, 'group' => s($it['group'] ?? '', 200) ?? '', 'category' => $cat, 'price' => clean_price($it['price'] ?? null, $name)];
        $alts = [];
        foreach (array_slice(is_array($it['altPrices'] ?? null) ? $it['altPrices'] : [], 0, 5) as $ap) $alts[] = clean_price($ap, $name);
        if ($alts) $row['altPrices'] = $alts;
        $out[] = $row;
    }
    if (!$out) throw new InvalidArgumentException('Die Woche enthält keine gültigen Artikel.');
    return $out;
}

/* ---------------- Bestand ---------------- */

function clean_date($v): ?string
{
    if (!is_string($v) || !preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $m)) return null;
    return checkdate((int)$m[2], (int)$m[3], (int)$m[1]) && (int)$m[1] >= 2000 && (int)$m[1] <= 2100 ? $v : null;
}
function clean_kg($v, string $where): float
{
    if (!is_int($v) && !is_float($v)) throw new InvalidArgumentException("Menge fehlt ($where).");
    $v = (float)$v;
    if (!is_finite($v) || abs($v) > 10000000) throw new InvalidArgumentException("Menge außerhalb des gültigen Bereichs ($where).");
    return round($v, 3);
}
function clean_stock($b): array
{
    $src = is_array($b['articles'] ?? null) ? $b['articles'] : [];
    if (!$src) throw new InvalidArgumentException('Die Bestandsliste enthält keine Artikel mit eingelagertem Bestand.');
    if (count($src) > 20000) throw new InvalidArgumentException('Zu viele Artikel in der Bestandsliste.');
    $out = [];
    $seen = [];
    foreach ($src as $a) {
        if (!is_array($a)) continue;
        $code = s($a['code'] ?? null, 20, false);
        if ($code === null || !preg_match('#^[0-9A-Za-z./-]+$#', $code)) throw new InvalidArgumentException('Ungültige Artikelnummer in der Bestandsliste.');
        $key = ctype_digit($code) ? (ltrim($code, '0') === '' ? '0' : ltrim($code, '0')) : strtoupper($code);
        if (isset($seen[$key])) throw new InvalidArgumentException("Artikelnummer $code kommt in der Bestandsliste doppelt vor.");
        $seen[$key] = true;
        $lots = [];
        foreach (array_slice(is_array($a['lots'] ?? null) ? $a['lots'] : [], 0, 500) as $l) {
            if (!is_array($l)) continue;
            $kolli = $l['kolli'] ?? null;
            $lots[] = ['lot' => s($l['lot'] ?? '', 20) ?? '', 'arrival' => clean_date($l['arrival'] ?? null), 'mhd' => clean_date($l['mhd'] ?? null),
                       'kolli' => (is_int($kolli) || is_float($kolli)) && abs($kolli) < 1000000 ? round((float)$kolli, 2) : null, 'kg' => clean_kg($l['kg'] ?? null, $code)];
        }
        $kg = clean_kg($a['kg'] ?? null, $code);
        if ($kg <= 0) continue;
        $mhd = clean_date($a['mhd'] ?? null);
        $out[] = ['code' => $code, 'name' => s($a['name'] ?? '', 200) ?: '(ohne Bezeichnung)', 'kg' => $kg, 'mhd' => $mhd,
                  'mhdKg' => $mhd !== null && isset($a['mhdKg']) ? clean_kg($a['mhdKg'], $code) : null, 'lots' => $lots];
    }
    if (!$out) throw new InvalidArgumentException('Die Bestandsliste enthält keine Artikel mit eingelagertem Bestand.');
    return $out;
}

/* ---------------- Stammdaten ---------------- */

function code_key(string $c): string { return ctype_digit($c) ? (ltrim($c, '0') === '' ? '0' : ltrim($c, '0')) : strtoupper($c); }
function clean_master($list): array
{
    if (!is_array($list)) throw new InvalidArgumentException('Stammdaten fehlen.');
    if (count($list) > 20000) throw new InvalidArgumentException('Zu viele Stammdatensätze.');
    $out = [];
    $seen = [];
    foreach ($list as $a) {
        if (!is_array($a)) continue;
        $code = s($a['code'] ?? null, 20, false);
        if ($code === null || !preg_match('#^[0-9A-Za-z./-]+$#', $code)) throw new InvalidArgumentException('Ungültige Artikelnummer in den Stammdaten.');
        $k = code_key($code);
        if (isset($seen[$k])) throw new InvalidArgumentException("Artikelnummer $code ist in den Stammdaten doppelt.");
        $seen[$k] = true;
        $name = s($a['name'] ?? null, 200, false);
        if ($name === null) throw new InvalidArgumentException("Artikel $code hat keine Bezeichnung.");
        $cat = in_array($a['category'] ?? '', CATEGORIES, true) ? $a['category'] : 'Sonstiges';
        $cond = in_array($a['condition'] ?? '', CONDITIONS, true) ? $a['condition'] : 'unbekannt';
        $origin = s($a['origin'] ?? null, 60);
        $out[] = ['code' => $code, 'name' => $name, 'category' => $cat, 'origin' => ($origin === '' ? null : $origin), 'condition' => $cond];
    }
    usort($out, function ($x, $y) { return strnatcmp($x['code'], $y['code']); });
    return $out;
}
function master_changes(array $old, array $new): array
{
    $o = []; foreach ($old as $a) $o[code_key($a['code'])] = $a;
    $n = []; foreach ($new as $a) $n[code_key($a['code'])] = $a;
    $L = ['name' => 'Bezeichnung', 'category' => 'Fleischart', 'origin' => 'Herkunft', 'condition' => 'Zustand'];
    $d = [];
    foreach ($n as $k => $a) {
        if (!isset($o[$k])) { $d[] = ['k' => "s$k|+", 'code' => $a['code'], 'name' => $a['name'], 'f' => 'Neuer Stammsatz', 'from' => '', 'to' => $a['category'] . ' · ' . $a['condition']]; continue; }
        foreach ($L as $f => $label) if ((string)($o[$k][$f] ?? '') !== (string)($a[$f] ?? '')) $d[] = ['k' => "s$k|$f", 'code' => $a['code'], 'name' => $a['name'], 'f' => $label, 'from' => (string)($o[$k][$f] ?? ''), 'to' => (string)($a[$f] ?? '')];
    }
    foreach ($o as $k => $a) if (!isset($n[$k])) $d[] = ['k' => "s$k|-", 'code' => $a['code'], 'name' => $a['name'], 'f' => 'Stammsatz gelöscht', 'from' => $a['name'], 'to' => ''];
    return $d;
}

/* ---------------- Aktionen ---------------- */

$action = (string)($_GET['action'] ?? '');
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$writeActions = ['setup', 'login', 'logout', 'save_draft', 'discard_draft', 'publish', 'change_password', 'history_import', 'history_delete', 'user_save', 'user_delete', 'stock_import', 'master_save',
                 'login_2fa', 'twofa_begin', 'twofa_enable', 'twofa_disable', 'security_save', 'session_end', 'ip_unblock', 'user_unlock', 'geo_update', 'geo_clear_stats'];
if (in_array($action, $writeActions, true)) {
    if ($method !== 'POST') fail('Methode nicht erlaubt.', 405);
    if (stripos((string)($_SERVER['CONTENT_TYPE'] ?? ''), 'application/json') !== 0) fail('Ungültige Anfrage.', 415);
}

/* Ländersperre (ganze Seite oder nur Eingabebereich) */
$isPublic = $action === 'offer' && empty($_GET['draft']);
$S = sec();
if (!empty($S['geoEnabled']) && (!$isPublic || $S['geoScope'] === 'all')) {
    $cc = geo_blocked(client_ip(), $S);
    if ($cc !== null) {
        geo_count($cc);
        fail('Der Zugriff aus Ihrem Land ist leider nicht möglich.', 403);
    }
}

/* IP-Freigabe für den Eingabebereich (die öffentliche Angebotsseite bleibt frei) */
if (!$isPublic) {
    if (!empty($S['ipEnabled']) && $S['adminIps'] && !ip_allowed(client_ip(), $S['adminIps'])) {
        fail('Der Eingabebereich ist von dieser Internetadresse (' . client_ip() . ') aus nicht freigegeben.', 403);
    }
}

try {
    switch ($action) {

        case 'offer': {
            header('Cache-Control: no-cache');
            if (!empty($_GET['draft'])) {
                require_auth();
                $d = store_read('entwurf') ?? store_read('angebot');
                if (!$d) fail('Kein Entwurf vorhanden.', 404);
                respond(['ok' => true, 'company' => $CFG['company'], 'preview' => true, 'offer' => $d]);
            }
            $p = store_path('angebot');
            if (!is_file($p)) fail('Es ist noch kein Angebot veröffentlicht.', 404);
            $etag = '"' . md5((string)filemtime($p) . ':' . filesize($p)) . '"';
            header('ETag: ' . $etag);
            if (trim((string)($_SERVER['HTTP_IF_NONE_MATCH'] ?? '')) === $etag) { http_response_code(304); exit; }
            respond(['ok' => true, 'company' => $CFG['company'], 'offer' => store_read('angebot')]);
        }

        case 'status': {
            header('Cache-Control: no-store');
            $u = current_user();
            respond(['ok' => true, 'setupRequired' => !users_load(), 'loggedIn' => (bool)$u, 'csrf' => $u ? $_SESSION['csrf'] : null,
                     'user' => $u ? me_payload($u) : null, 'company' => $CFG['company']]);
        }

        case 'setup': {
            $b = body();
            $u = with_lock('nutzer', function () use ($b) {
                if (users_load()) fail('Die Ersteinrichtung ist bereits erfolgt.', 409);
                $name = s($b['name'] ?? '', 80) ?: 'Administrator';
                $uname = clean_username($b['username'] ?? '');
                $u = ['id' => 'u' . bin2hex(random_bytes(6)), 'username' => $uname, 'name' => $name, 'role' => 'admin',
                      'active' => true, 'hash' => password_hash(check_password($b['password'] ?? '', $uname), PASSWORD_DEFAULT), 'mustChange' => false,
                      'sv' => 1, 'created' => now(), 'createdBy' => 'Ersteinrichtung', 'lastLogin' => now()];
                users_save([$u]);
                return $u;
            });
            start_session();
            $tok = sign_in($u);
            audit('setup', 'Ersteinrichtung: Administrator „' . $u['username'] . '“ angelegt');
            respond(['ok' => true, 'csrf' => $tok, 'user' => me_payload($u)]);
        }

        case 'login': {
            start_session();
            attempts_check();
            if (!users_load()) fail('Bitte zuerst die Ersteinrichtung durchführen.', 409);
            $b = body();
            $name = is_string($b['username'] ?? null) ? strtolower(trim($b['username'])) : '';
            $pw = (string)($b['password'] ?? '');
            $S = sec();
            $res = with_lock('nutzer', function () use ($name, $pw, $S) {
                $users = users_load();
                foreach ($users as $i => $u) {
                    if ($u['username'] !== $name) continue;
                    if ((int)($u['lockedUntil'] ?? 0) > time()) { password_verify($pw, (string)$u['hash']); return ['locked', $u]; }
                    if (!password_verify($pw, (string)$u['hash'])) {
                        $n = (int)($u['failCount'] ?? 0) + 1;
                        $users[$i]['failCount'] = $n;
                        $lockedNow = $n >= max(3, (int)$S['lockAfter']);
                        if ($lockedNow) { $users[$i]['lockedUntil'] = time() + 60 * max(1, (int)$S['lockMinutes']); $users[$i]['failCount'] = 0; }
                        users_save($users);
                        return [$lockedNow ? 'lockednow' : 'bad', $users[$i]];
                    }
                    if (!$u['active']) return ['inactive', $u];
                    if (password_needs_rehash((string)$u['hash'], PASSWORD_DEFAULT)) $users[$i]['hash'] = password_hash($pw, PASSWORD_DEFAULT);
                    $users[$i]['failCount'] = 0;
                    $users[$i]['lockedUntil'] = 0;
                    if (empty($u['totp'])) $users[$i]['lastLogin'] = now();
                    users_save($users);
                    return ['ok', $users[$i]];
                }
                password_verify($pw, '$2y$10$y80WR5wtxxV9G3NpBGQXmeL3EYKIGKm4gaElkDTK2cWFQtjyZdoPa'); // gleiche Laufzeit wie bei vorhandenem Nutzer
                return ['bad', null];
            });
            [$st, $u] = $res;
            $who = ['username' => mb_substr($name, 0, 40), 'name' => $u['name'] ?? '', 'role' => $u['role'] ?? ''];
            if ($st !== 'ok') {
                attempts_record(false);
                $why = ['inactive' => ' – Zugang deaktiviert', 'locked' => ' – Zugang gesperrt', 'lockednow' => ' – Zugang nach zu vielen Fehlversuchen gesperrt', 'bad' => ''][$st];
                audit('login_fail', 'Anmeldung fehlgeschlagen' . ($name !== '' ? ' (Benutzername „' . mb_substr($name, 0, 40) . '“)' : '') . $why, [], $who);
                usleep(400000);
                if ($st === 'inactive') fail('Dieser Zugang ist deaktiviert.', 401);
                if ($st === 'locked' || $st === 'lockednow') fail('Dieser Zugang ist wegen zu vieler Fehlversuche bis ' . (new DateTime('@' . (int)$u['lockedUntil']))->setTimezone(new DateTimeZone('Europe/Berlin'))->format('H:i') . ' Uhr gesperrt. Ein Administrator kann ihn vorher entsperren.', 429);
                fail('Benutzername oder Passwort ist nicht korrekt.', 401);
            }
            if (!empty($u['totp'])) {
                // zweiter Schritt: Code aus der Authenticator-App
                session_regenerate_id(true);
                $_SESSION = ['pend' => ['uid' => $u['id'], 'sv' => (int)$u['sv'], 't' => time(), 'n' => 0]];
                respond(['ok' => true, 'need2fa' => true]);
            }
            attempts_record(true);
            $tok = sign_in($u);
            audit('login', 'Angemeldet');
            respond(['ok' => true, 'csrf' => $tok, 'user' => me_payload($u)]);
        }

        case 'login_2fa': {
            start_session();
            attempts_check();
            $p = $_SESSION['pend'] ?? null;
            if (!$p || (int)$p['t'] < time() - 300) { $_SESSION = []; fail('Die Anmeldung ist abgelaufen. Bitte erneut mit Benutzername und Passwort anmelden.', 401); }
            $code = trim((string)(body()['code'] ?? ''));
            $res = with_lock('nutzer', function () use ($p, $code) {
                $users = users_load();
                $i = user_find($users, (string)$p['uid']);
                if ($i === null || !$users[$i]['active'] || (int)$users[$i]['sv'] !== (int)$p['sv'] || empty($users[$i]['totp'])) return ['gone', null];
                $u = &$users[$i];
                $how = null;
                $step = totp_check((string)$u['totp'], $code, (int)($u['totpLast'] ?? 0));
                if ($step !== null) { $u['totpLast'] = $step; $how = 'app'; }
                elseif (preg_match('/^[a-z0-9]{5}-?[a-z0-9]{5}$/i', $code)) {
                    $h = rc_hash($code);
                    $k = array_search($h, $u['recovery'] ?? [], true);
                    if ($k !== false) { array_splice($u['recovery'], $k, 1); $how = 'recovery'; }
                }
                if (!$how) return ['bad', $u];
                $u['lastLogin'] = now();
                $out = $u;
                unset($u);
                users_save($users);
                return [$how, $out];
            });
            [$st, $u] = $res;
            if ($st === 'gone') { $_SESSION = []; fail('Die Anmeldung ist abgelaufen. Bitte erneut anmelden.', 401); }
            if ($st === 'bad') {
                attempts_record(false);
                $_SESSION['pend']['n'] = (int)$p['n'] + 1;
                audit('login_fail', 'Zwei-Faktor-Code falsch', [], ['username' => $u['username'], 'name' => $u['name'], 'role' => $u['role']]);
                if ($_SESSION['pend']['n'] >= 5) { $_SESSION = []; fail('Zu viele falsche Codes. Bitte erneut anmelden.', 401); }
                usleep(300000);
                fail('Der Code ist nicht korrekt oder abgelaufen.', 401);
            }
            attempts_record(true);
            $tok = sign_in($u);
            audit('login', $st === 'recovery' ? 'Angemeldet (mit Wiederherstellungscode – noch ' . count($u['recovery'] ?? []) . ' übrig)' : 'Angemeldet (mit Zwei-Faktor-Code)');
            respond(['ok' => true, 'csrf' => $tok, 'user' => me_payload($u), 'recoveryLeft' => $st === 'recovery' ? count($u['recovery'] ?? []) : null]);
        }

        case 'twofa_begin': {
            $me = current_user();
            if (!$me) fail('Bitte erneut anmelden.', 401);
            require_csrf();
            $secret = b32_encode(random_bytes(20));
            $_SESSION['totpPending'] = $secret;
            $issuer = rawurlencode(($CFG['company'] ?: 'Wochenangebot') . ' Wochenangebot');
            respond(['ok' => true, 'secret' => $secret, 'uri' => "otpauth://totp/{$issuer}:" . rawurlencode($me['username']) . "?secret={$secret}&issuer={$issuer}&algorithm=SHA1&digits=6&period=30"]);
        }

        case 'twofa_enable': {
            $me = current_user();
            if (!$me) fail('Bitte erneut anmelden.', 401);
            require_csrf();
            $secret = (string)($_SESSION['totpPending'] ?? '');
            if ($secret === '') fail('Bitte die Einrichtung neu starten.', 409);
            $step = totp_check($secret, (string)(body()['code'] ?? ''));
            if ($step === null) fail('Der Code stimmt nicht. Bitte die Uhrzeit des Handys prüfen und den aktuellen Code eingeben.', 422);
            $codes = recovery_codes();
            $u = user_update($me['id'], function (&$x) use ($secret, $step, $codes) {
                $x['totp'] = $secret; $x['totpLast'] = $step; $x['recovery'] = array_map('rc_hash', $codes); $x['changed'] = now();
            });
            unset($_SESSION['totpPending']);
            $GLOBALS['ME'] = $u;
            audit('twofa', 'Zwei-Faktor-Anmeldung eingerichtet');
            respond(['ok' => true, 'recovery' => $codes, 'user' => me_payload($u)]);
        }

        case 'twofa_disable': {
            $me = require_auth(true);
            if (empty($me['totp'])) fail('Die Zwei-Faktor-Anmeldung ist nicht eingerichtet.', 409);
            if (twofa_required($me)) fail('Für Ihre Rolle ist die Zwei-Faktor-Anmeldung vorgeschrieben und kann nicht ausgeschaltet werden.', 422);
            if (!password_verify((string)(body()['password'] ?? ''), (string)$me['hash'])) fail('Das Passwort ist nicht korrekt.', 422);
            $u = user_update($me['id'], function (&$x) { unset($x['totp'], $x['totpLast'], $x['recovery']); $x['changed'] = now(); });
            audit('twofa', 'Zwei-Faktor-Anmeldung ausgeschaltet');
            respond(['ok' => true, 'user' => me_payload($u)]);
        }

        case 'logout': {
            $u = current_user();
            if ($u) { audit('logout', 'Abgemeldet'); $sid = (string)($_SESSION['sid'] ?? ''); sess_remove(function ($k) use ($sid) { return $k === $sid; }); }
            $_SESSION = [];
            session_destroy();
            respond(['ok' => true]);
        }

        case 'change_password': {
            $me = current_user();
            if (!$me) fail('Bitte erneut anmelden.', 401);
            require_csrf();
            $b = body();
            if (!password_verify((string)($b['current'] ?? ''), (string)$me['hash'])) fail('Das bisherige Passwort ist nicht korrekt.', 401);
            $new = check_password($b['password'] ?? '', $me['username']);
            if (password_verify($new, (string)$me['hash'])) fail('Bitte ein anderes als das bisherige Passwort wählen.');
            $u = with_lock('nutzer', function () use ($me, $new) {
                $users = users_load();
                $i = user_find($users, $me['id']);
                if ($i === null) fail('Bitte erneut anmelden.', 401);
                $users[$i]['hash'] = password_hash($new, PASSWORD_DEFAULT);
                $users[$i]['mustChange'] = false;
                $users[$i]['sv'] = (int)$users[$i]['sv'] + 1;   // andere Sitzungen dieses Nutzers abmelden
                $users[$i]['changed'] = now();
                users_save($users);
                return $users[$i];
            });
            $_SESSION['sv'] = (int)$u['sv'];
            $GLOBALS['ME'] = $u;
            $sid = (string)($_SESSION['sid'] ?? '');
            sess_remove(function ($k, $v) use ($u, $sid) { return $v['uid'] === $u['id'] && $k !== $sid; });
            audit('password', 'Eigenes Passwort geändert');
            respond(['ok' => true, 'user' => me_payload($u)]);
        }

        case 'stock': {
            require_auth();
            header('Cache-Control: no-store');
            respond(['ok' => true, 'stock' => store_read('bestand')]);
        }

        case 'stock_import': {
            $me = require_auth(true, 'editor');
            $b = body();
            $articles = clean_stock($b);
            $date = clean_date($b['date'] ?? null);
            $total = 0.0;
            foreach ($articles as $a) $total += $a['kg'];
            $st = ['date' => $date, 'source' => s($b['source'] ?? '', 200) ?? '', 'importedAt' => now(), 'importedBy' => $me['name'], 'articles' => $articles];
            store_write('bestand', $st);
            audit('stock', 'Bestand übernommen: ' . ($st['source'] ?: 'Datei') . ($date ? ' – Stand ' . date('d.m.Y', strtotime($date)) : '') . ', ' . count($articles) . ' Artikel, ' . number_format($total, 2, ',', '.') . ' kg eingelagert');
            respond(['ok' => true, 'stock' => $st]);
        }

        case 'master': {
            require_auth();
            header('Cache-Control: no-store');
            $m = store_read('stammdaten');
            respond(['ok' => true, 'master' => $m ?: ['rev' => 0, 'articles' => [], 'updatedAt' => null]]);
        }

        case 'master_save': {
            $me = require_auth(true, 'editor');
            $b = body();
            $articles = clean_master($b['articles'] ?? null);
            $res = with_lock('stammdaten', function () use ($b, $articles, $me) {
                $cur = store_read('stammdaten') ?: ['rev' => 0, 'articles' => []];
                if ((int)($b['rev'] ?? -1) !== (int)$cur['rev']) fail('Die Stammdaten wurden inzwischen an anderer Stelle geändert. Bitte die Seite neu laden.', 409);
                $m = ['rev' => (int)$cur['rev'] + 1, 'updatedAt' => now(), 'updatedBy' => $me['name'], 'articles' => $articles];
                store_write('stammdaten', $m);
                return [$m, master_changes($cur['articles'], $articles)];
            });
            [$m, $d] = $res;
            if ($d) audit('master', 'Stammdaten bearbeitet', array_slice($d, 0, 2000), null, true);
            respond(['ok' => true, 'rev' => $m['rev'], 'updatedAt' => $m['updatedAt']]);
        }

        case 'security_status': {
            $me = require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $users = users_load();
            $names = []; foreach ($users as $u) $names[$u['id']] = $u;
            $sess = [];
            foreach (sess_prune(store_read('sitzungen') ?? []) as $sid => $v) {
                $u = $names[$v['uid']] ?? null;
                $sess[] = ['sid' => $sid, 'uid' => $v['uid'], 'username' => $u['username'] ?? '?', 'name' => $u['name'] ?? '?', 'role' => $u['role'] ?? '',
                           'ip' => $v['ip'], 'ua' => $v['ua'], 'created' => $v['created'], 'seen' => gmdate('Y-m-d\TH:i:s\Z', (int)$v['seen']), 'current' => $sid === ($_SESSION['sid'] ?? '')];
            }
            usort($sess, function ($a, $b) { return strcmp($b['seen'], $a['seen']); });
            $ips = [];
            foreach (store_read('logins') ?? [] as $k => $v) {
                if ((int)($v['until'] ?? 0) <= time() && (int)($v['n'] ?? 0) === 0) continue;
                $ips[] = ['key' => $k, 'ip' => $v['ip'] ?? 'unbekannt', 'n' => (int)($v['n'] ?? 0), 'until' => (int)($v['until'] ?? 0) > time() ? gmdate('Y-m-d\TH:i:s\Z', (int)$v['until']) : null, 't' => gmdate('Y-m-d\TH:i:s\Z', (int)($v['t'] ?? time()))];
            }
            $fails = [];
            foreach ([gmdate('Y-m'), gmdate('Y-m', strtotime('first day of last month'))] as $m) {
                foreach (store_read('protokoll/' . $m) ?? [] as $e) if ($e['a'] === 'login_fail' && strtotime($e['t']) > time() - 7 * 86400) $fails[] = ['t' => $e['t'], 'u' => $e['u'], 'ip' => $e['ip'] ?? '', 's' => $e['s']];
            }
            usort($fails, function ($a, $b) { return strcmp($b['t'], $a['t']); });
            $f24 = count(array_filter($fails, function ($e) { return strtotime($e['t']) > time() - 86400; }));
            $gs = store_read('laendersperre') ?? [];
            $gcc = []; foreach ($gs['cc'] ?? [] as $k => $v) $gcc[] = ['cc' => $k, 'n' => $v['n'], 'last' => $v['last']];
            usort($gcc, function ($a, $b) { return $b['n'] <=> $a['n']; });
            $g7 = (($gs['day'] ?? '') === gmdate('Y-m-d') ? (int)($gs['today'] ?? 0) : 0);
            foreach ($gs['days'] ?? [] as $dd => $n) if ($dd > gmdate('Y-m-d', time() - 7 * 86400)) $g7 += (int)$n;
            respond(['ok' => true, 'settings' => sec(), 'myIp' => client_ip(), 'https' => is_https(),
                     'myCountry' => geo_country(client_ip()), 'geo' => geo_info(), 'geoCountries' => GEO_COUNTRIES, 'geoStats' => array_slice($gcc, 0, 30), 'geoBlocked7' => $g7,
                     'users' => array_map('user_public', $users), 'sessions' => $sess, 'blockedIps' => $ips,
                     'fails' => array_slice($fails, 0, 30), 'fails24' => $f24]);
        }

        case 'security_save': {
            $me = require_auth(true, 'admin');
            $b = body();
            $old = sec();
            $twofa = in_array($b['twofa'] ?? '', ['off', 'admins', 'all'], true) ? $b['twofa'] : 'off';
            $ips = [];
            foreach (array_slice(is_array($b['adminIps'] ?? null) ? $b['adminIps'] : [], 0, 50) as $c) {
                $c = trim((string)$c);
                if ($c === '') continue;
                if (!valid_cidr($c)) throw new InvalidArgumentException("„{$c}“ ist keine gültige IP-Adresse oder kein gültiger Bereich (z. B. 80.147.24.150 oder 80.147.24.0/24).");
                $ips[] = $c;
            }
            $ipEnabled = !empty($b['ipEnabled']);
            if ($ipEnabled && !$ips) throw new InvalidArgumentException('Bitte mindestens eine freigegebene IP-Adresse eintragen.');
            if ($ipEnabled && !ip_allowed(client_ip(), $ips)) throw new InvalidArgumentException('Ihre aktuelle Adresse ' . client_ip() . ' ist nicht in der Liste – Sie würden sich selbst aussperren.');
            $geoEnabled = !empty($b['geoEnabled']);
            $geoMode = ($b['geoMode'] ?? '') === 'allow' ? 'allow' : 'block';
            $geoScope = ($b['geoScope'] ?? '') === 'all' ? 'all' : 'admin';
            $gc = [];
            foreach (array_slice(is_array($b['geoCountries'] ?? null) ? $b['geoCountries'] : [], 0, 300) as $c) {
                $c = strtoupper(trim((string)$c));
                if (in_array($c, GEO_COUNTRIES, true) && !in_array($c, $gc, true)) $gc[] = $c;
            }
            sort($gc);
            if ($geoEnabled && !$gc) throw new InvalidArgumentException($geoMode === 'allow' ? 'Bitte mindestens ein erlaubtes Land auswählen.' : 'Bitte mindestens ein Land zum Sperren auswählen.');
            if ($geoEnabled && !geo_info()) throw new InvalidArgumentException('Die Länderdatenbank fehlt – bitte zuerst „Länderdaten aktualisieren“.');
            $geoS = ['geoEnabled' => $geoEnabled, 'geoMode' => $geoMode, 'geoCountries' => $gc, 'adminIps' => $ips];
            if ($geoEnabled && ($mc = geo_blocked(client_ip(), $geoS)) !== null) throw new InvalidArgumentException("Sie greifen gerade aus einem Land zu, das damit gesperrt wäre ({$mc}) – Sie würden sich selbst aussperren.");
            if ($twofa !== 'off' && empty($me['totp']) && ($twofa === 'all' || $me['role'] === 'admin')) throw new InvalidArgumentException('Bitte richten Sie zuerst für sich selbst die Zwei-Faktor-Anmeldung ein (Menü „…“ → „Zwei-Faktor-Anmeldung“).');
            $new = ['twofa' => $twofa, 'pwMin' => max(10, min(32, (int)($b['pwMin'] ?? 10))), 'pwComplex' => !empty($b['pwComplex']),
                    'idleMinutes' => in_array((int)($b['idleMinutes'] ?? 480), [15, 30, 60, 120, 240, 480, 720], true) ? (int)$b['idleMinutes'] : 480,
                    'ipEnabled' => $ipEnabled, 'adminIps' => $ips,
                    'lockAfter' => max(3, min(20, (int)($b['lockAfter'] ?? 10))), 'lockMinutes' => max(5, min(1440, (int)($b['lockMinutes'] ?? 15))),
                    'geoEnabled' => $geoEnabled, 'geoMode' => $geoMode, 'geoCountries' => $gc, 'geoScope' => $geoScope];
            store_write('sicherheit', $new);
            $GLOBALS['SEC'] = $new;
            $L = ['twofa' => 'Zwei-Faktor-Pflicht', 'pwMin' => 'Passwort-Mindestlänge', 'pwComplex' => 'Passwort-Komplexität', 'idleMinutes' => 'Abmeldung nach Inaktivität (Min.)',
                  'ipEnabled' => 'IP-Freigabe Eingabebereich', 'adminIps' => 'Freigegebene Adressen', 'lockAfter' => 'Kontosperre nach Fehlversuchen', 'lockMinutes' => 'Kontosperre (Min.)',
                  'geoEnabled' => 'Ländersperre', 'geoMode' => 'Ländersperre – Art', 'geoCountries' => 'Ländersperre – Länder', 'geoScope' => 'Ländersperre – gilt für'];
            $GV = ['block' => 'ausgewählte Länder sperren', 'allow' => 'nur ausgewählte Länder erlauben', 'admin' => 'nur Eingabebereich', 'all' => 'ganze Seite'];
            $fmt = function ($v) use ($GV) { return is_bool($v) ? ($v ? 'an' : 'aus') : (is_array($v) ? implode(', ', $v) : (string)($GV[$v] ?? $v)); };
            $d = [];
            foreach ($L as $k => $label) if ($fmt($old[$k] ?? null) !== $fmt($new[$k])) $d[] = ['k' => "sec|$k", 'code' => '', 'name' => 'Sicherheit', 'f' => $label, 'from' => $fmt($old[$k] ?? ''), 'to' => $fmt($new[$k])];
            if ($d) audit('security', 'Sicherheitseinstellungen geändert', $d);
            respond(['ok' => true, 'settings' => $new]);
        }

        case 'geo_lookup': {
            require_auth(false, 'admin');
            $ip = trim((string)($_GET['ip'] ?? ''));
            if (filter_var($ip, FILTER_VALIDATE_IP) === false) fail('Keine gültige IP-Adresse.', 422);
            $priv = filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false;
            respond(['ok' => true, 'ip' => $ip, 'country' => geo_country($ip), 'private' => $priv]);
        }

        case 'geo_clear_stats': {
            require_auth(true, 'admin');
            with_lock('laendersperre', function () { store_write('laendersperre', []); });
            respond(['ok' => true]);
        }

        case 'session_end': {
            $me = require_auth(true, 'admin');
            $b = body();
            $sid = (string)($b['sid'] ?? '');
            $uid = (string)($b['uid'] ?? '');
            $mine = (string)($_SESSION['sid'] ?? '');
            $who = '';
            $reg = store_read('sitzungen') ?? [];
            if ($sid !== '' && isset($reg[$sid])) $who = $reg[$sid]['uid'];
            $n = sess_remove(function ($k, $v) use ($sid, $uid, $mine) { return $k !== $mine && (($sid !== '' && $k === $sid) || ($uid !== '' && $v['uid'] === $uid)); });
            $users = users_load(); $un = ''; foreach ($users as $u) if ($u['id'] === ($uid ?: $who)) $un = $u['username'];
            if ($n) audit('security', $n === 1 ? "Sitzung von „{$un}“ beendet" : "{$n} Sitzungen von „{$un}“ beendet");
            respond(['ok' => true, 'ended' => $n]);
        }

        case 'ip_unblock': {
            require_auth(true, 'admin');
            $key = (string)(body()['key'] ?? '');
            $ip = with_lock('logins', function () use ($key) {
                $a = store_read('logins') ?? [];
                $ip = $a[$key]['ip'] ?? null;
                unset($a[$key]);
                store_write('logins', $a);
                return $ip;
            });
            audit('security', 'IP-Sperre aufgehoben' . ($ip ? " ({$ip})" : ''));
            respond(['ok' => true]);
        }

        case 'geo_update': {
            require_auth(true, 'admin');
            @set_time_limit(180);
            try { $r = geo_download($DATA . '/geo/laender.dat.php'); }
            catch (Throwable $e) { error_log('[wochenangebot] geo: ' . $e->getMessage()); fail('Die Länderdaten konnten nicht aktualisiert werden. Bitte später erneut versuchen.', 502); }
            audit('security', 'Länderdaten aktualisiert (Stand ' . $r['date'] . ')');
            respond(['ok' => true, 'geo' => geo_info()]);
        }

        case 'user_unlock': {
            require_auth(true, 'admin');
            $u = user_update((string)(body()['id'] ?? ''), function (&$x) { $x['lockedUntil'] = 0; $x['failCount'] = 0; });
            if (!$u) fail('Nutzer nicht gefunden.', 404);
            audit('security', "Zugang „{$u['username']}“ entsperrt");
            respond(['ok' => true]);
        }

        case 'users': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            respond(['ok' => true, 'users' => array_map('user_public', users_load())]);
        }

        case 'user_save': {
            $me = require_auth(true, 'admin');
            $b = body();
            $res = with_lock('nutzer', function () use ($b, $me) {
                $users = users_load();
                $id = is_string($b['id'] ?? null) ? $b['id'] : '';
                $isNew = $id === '';
                $name = s($b['name'] ?? '', 80, false);
                if ($name === null) throw new InvalidArgumentException('Bitte einen Namen angeben.');
                $role = is_string($b['role'] ?? null) && isset(ROLES[$b['role']]) ? $b['role'] : null;
                if ($role === null) throw new InvalidArgumentException('Ungültige Rolle.');
                $active = !empty($b['active']);
                $pw = $b['password'] ?? '';
                $setPw = is_string($pw) && $pw !== '';
                if ($isNew) {
                    $uname = clean_username($b['username'] ?? '');
                    foreach ($users as $u) if ($u['username'] === $uname) throw new InvalidArgumentException('Der Benutzername „' . $uname . '“ ist bereits vergeben.');
                    if (!$setPw) throw new InvalidArgumentException('Bitte ein Passwort für den neuen Nutzer festlegen.');
                    $u = ['id' => 'u' . bin2hex(random_bytes(6)), 'username' => $uname, 'name' => $name, 'role' => $role, 'active' => $active,
                          'hash' => password_hash(check_password($pw, $uname), PASSWORD_DEFAULT), 'mustChange' => !empty($b['mustChange']), 'sv' => 1,
                          'created' => now(), 'createdBy' => $me['username'], 'lastLogin' => null];
                    $users[] = $u;
                    users_save($users);
                    $d = [['k' => 'u|role', 'code' => '', 'name' => $uname, 'f' => 'Rolle', 'from' => '', 'to' => ROLE_LABELS[$role]]];
                    if (!$active) $d[] = ['k' => 'u|active', 'code' => '', 'name' => $uname, 'f' => 'Status', 'from' => '', 'to' => 'deaktiviert'];
                    return [$u, 'Nutzer „' . $uname . '“ (' . $name . ') angelegt', $d];
                }
                $i = user_find($users, $id);
                if ($i === null) fail('Nutzer nicht gefunden.', 404);
                $old = $users[$i];
                if ($id === $me['id'] && ($role !== $old['role'] || !$active)) throw new InvalidArgumentException('Die eigene Rolle und den eigenen Zugang können Sie nicht ändern.');
                $users[$i]['name'] = $name;
                $users[$i]['role'] = $role;
                $users[$i]['active'] = $active;
                if (active_admins($users) < 1) throw new InvalidArgumentException('Es muss mindestens ein aktiver Administrator bestehen bleiben.');
                $d = [];
                if ($old['name'] !== $name) $d[] = ['k' => 'u|name', 'code' => '', 'name' => $old['username'], 'f' => 'Name', 'from' => $old['name'], 'to' => $name];
                if ($old['role'] !== $role) $d[] = ['k' => 'u|role', 'code' => '', 'name' => $old['username'], 'f' => 'Rolle', 'from' => ROLE_LABELS[$old['role']], 'to' => ROLE_LABELS[$role]];
                if ((bool)$old['active'] !== $active) $d[] = ['k' => 'u|active', 'code' => '', 'name' => $old['username'], 'f' => 'Status', 'from' => $old['active'] ? 'aktiv' : 'deaktiviert', 'to' => $active ? 'aktiv' : 'deaktiviert'];
                if (!empty($b['reset2fa']) && !empty($old['totp'])) {
                    unset($users[$i]['totp'], $users[$i]['totpLast'], $users[$i]['recovery']);
                    $users[$i]['sv'] = (int)$users[$i]['sv'] + 1;
                    $d[] = ['k' => 'u|2fa', 'code' => '', 'name' => $old['username'], 'f' => 'Zwei-Faktor', 'from' => 'eingerichtet', 'to' => 'zurückgesetzt'];
                }
                if ($setPw) {
                    $users[$i]['hash'] = password_hash(check_password($pw, $old['username']), PASSWORD_DEFAULT);
                    $users[$i]['mustChange'] = $id !== $me['id'] && !empty($b['mustChange']);
                    $users[$i]['sv'] = (int)$users[$i]['sv'] + 1;      // bestehende Sitzungen des Nutzers beenden
                    $d[] = ['k' => 'u|pw', 'code' => '', 'name' => $old['username'], 'f' => 'Passwort', 'from' => '', 'to' => 'neu gesetzt' . ($users[$i]['mustChange'] ? ' (muss beim Anmelden geändert werden)' : '')];
                }
                $users[$i]['changed'] = now();
                users_save($users);
                return [$users[$i], 'Nutzer „' . $old['username'] . '“ geändert', $d];
            });
            [$u, $msg, $d] = $res;
            if ($u['id'] === $me['id']) { $_SESSION['sv'] = (int)$u['sv']; }
            elseif ((int)$u['sv'] > 1 || empty($u['active'])) {
                $uid = $u['id']; $sv = (int)$u['sv'];
                if (empty($u['active']) || array_filter($d, function ($x) { return in_array($x['k'], ['u|pw', 'u|2fa'], true); })) sess_remove(function ($k, $v) use ($uid) { return $v['uid'] === $uid; });
            }
            if ($d) audit('user', $msg, $d);
            respond(['ok' => true, 'user' => user_public($u)]);
        }

        case 'user_delete': {
            $me = require_auth(true, 'admin');
            $id = (string)(body()['id'] ?? '');
            $gone = with_lock('nutzer', function () use ($id, $me) {
                $users = users_load();
                $i = user_find($users, $id);
                if ($i === null) fail('Nutzer nicht gefunden.', 404);
                if ($id === $me['id']) throw new InvalidArgumentException('Den eigenen Zugang können Sie nicht löschen.');
                $u = $users[$i];
                array_splice($users, $i, 1);
                if (active_admins($users) < 1) throw new InvalidArgumentException('Es muss mindestens ein aktiver Administrator bestehen bleiben.');
                users_save($users);
                return $u;
            });
            sess_remove(function ($k, $v) use ($gone) { return $v['uid'] === $gone['id']; });
            audit('user', 'Nutzer „' . $gone['username'] . '“ (' . $gone['name'] . ') gelöscht');
            respond(['ok' => true]);
        }

        case 'log': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $months = [];
            foreach (glob(dirname(store_path('protokoll/x')) . '/*.php') ?: [] as $f) {
                $m = basename($f, '.php');
                if (preg_match('/^\d{4}-\d{2}$/', $m)) $months[] = $m;
            }
            rsort($months);
            $month = (string)($_GET['month'] ?? '');
            if (!preg_match('/^\d{4}-\d{2}$/', $month)) $month = $months[0] ?? gmdate('Y-m');
            respond(['ok' => true, 'month' => $month, 'months' => $months, 'entries' => array_reverse(store_read('protokoll/' . $month) ?? [])]);
        }

        case 'draft': {
            require_auth();
            header('Cache-Control: no-store');
            $pub = store_read('angebot');
            $draft = store_read('entwurf');
            respond([
                'ok' => true,
                'published' => $pub,
                'publishedAt' => $pub['publishedAt'] ?? null,
                'draft' => $draft,
                'draftSavedAt' => $draft['savedAt'] ?? null,
                'revision' => (int)($draft['rev'] ?? 0),
            ]);
        }

        case 'save_draft': {
            require_auth(true, 'editor');
            $b = body();
            $prev = store_read('entwurf');
            $cur = (int)($prev['rev'] ?? 0);
            if ($prev !== null && (int)($b['revision'] ?? -1) !== $cur) {
                fail('Der Entwurf wurde inzwischen in einem anderen Fenster geändert. Bitte die Seite neu laden.', 409);
            }
            $model = clean_model($b['model'] ?? null, false);
            $model['savedAt'] = now();
            $model['rev'] = $cur + 1;
            store_write('entwurf', $model);
            $before = $prev ?? store_read('angebot');
            $note = is_array($b['note'] ?? null) ? $b['note'] : null;
            if ($note && ($note['type'] ?? '') === 'import') {
                $d = changes_between(store_read('angebot'), $model);
                audit('import', 'Excel importiert: ' . (s($note['file'] ?? '', 120) ?: 'Datei') . ' – KW ' . ($model['meta']['week'] ?? '?') . '/' . ($model['meta']['year'] ?? '?') . ', ' . count($model['items']) . ' Artikel (gegenüber veröffentlicht: ' . changes_summary($d) . ')', array_slice($d, 0, 2000));
            } elseif ($note && ($note['type'] ?? '') === 'cleanup') {
                $d = changes_between($before, $model);
                if ($d) audit('draft', 'Bezeichnungen und Herkunft vereinheitlicht (' . count($d) . ' Änderungen: ohne „frisch“, Marke Fleischmeister, Herkunft als Kürzel)', array_slice($d, 0, 2000));
            } elseif ($note && ($note['type'] ?? '') === 'master') {
                $d = changes_between($before, $model);
                if ($d) audit('draft', 'Stammdaten auf den Entwurf angewendet', array_slice($d, 0, 2000));
            } elseif ($note && ($note['type'] ?? '') === 'version') {
                audit('import', 'Frühere Veröffentlichung als Entwurf geladen (KW ' . ($model['meta']['week'] ?? '?') . '/' . ($model['meta']['year'] ?? '?') . ')', array_slice(changes_between($before, $model), 0, 2000));
            } else {
                $d = changes_between($before, $model);
                if ($d) audit('draft', 'Entwurf bearbeitet', $d, null, true);
            }
            respond(['ok' => true, 'savedAt' => $model['savedAt'], 'revision' => $model['rev']]);
        }

        case 'discard_draft': {
            require_auth(true, 'editor');
            $dr = store_read('entwurf');
            store_delete('entwurf');
            if ($dr) { $d = changes_between($dr, store_read('angebot') ?? $dr); audit('discard', 'Entwurf verworfen' . ($d ? ' (' . changes_summary($d) . ' zurückgenommen)' : ''), array_slice($d, 0, 2000)); }
            respond(['ok' => true]);
        }

        case 'publish': {
            require_auth(true, 'editor');
            $model = clean_model(body()['model'] ?? null, true);
            $prev = store_read('angebot');
            if ($prev) {
                $id = gmdate('Ymd-His') . '-' . bin2hex(random_bytes(3));
                store_write('versionen/' . $id, $prev);
                $list = glob(dirname(store_path('versionen/x')) . '/*.php') ?: [];
                rsort($list);
                foreach (array_slice($list, (int)$CFG['keep_versions']) as $old) @unlink($old);
            }
            $model['publishedAt'] = now();
            store_write('angebot', $model);
            store_delete('entwurf');
            $h = history_from_model($model, 'Veröffentlichung', $model['publishedAt']);
            if ($h) { $hid = history_id($h['week'], $h['year']); store_write('historie/' . $hid, $h); history_undelete($hid); }
            $d = $prev ? changes_between($prev, $model) : [];
            audit('publish', 'KW ' . $model['meta']['week'] . '/' . $model['meta']['year'] . ' veröffentlicht – ' . count($model['items']) . ' Artikel' . ($prev ? ' (' . changes_summary($d) . ')' : ' (erste Veröffentlichung)'), array_slice($d, 0, 2000));
            respond(['ok' => true, 'publishedAt' => $model['publishedAt']]);
        }

        case 'versions': {
            require_auth();
            $list = glob(dirname(store_path('versionen/x')) . '/*.php') ?: [];
            rsort($list);
            $out = [];
            foreach ($list as $f) {
                $id = basename($f, '.php');
                if (!preg_match('/^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$/', $id)) continue;
                $d = store_read('versionen/' . $id);
                if (!$d) continue;
                $out[] = ['id' => $id, 'week' => $d['meta']['week'] ?? null, 'year' => $d['meta']['year'] ?? null,
                          'items' => count($d['items'] ?? []), 'publishedAt' => $d['publishedAt'] ?? null, 'source' => $d['meta']['source'] ?? ''];
            }
            respond(['ok' => true, 'versions' => $out]);
        }

        case 'version': {
            require_auth();
            $id = (string)($_GET['id'] ?? '');
            if (!preg_match('/^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$/', $id)) fail('Ungültige Version.');
            $d = store_read('versionen/' . $id);
            if (!$d) fail('Version nicht gefunden.', 404);
            respond(['ok' => true, 'model' => $d]);
        }

        case 'history_list': {
            require_auth();
            header('Cache-Control: no-store');
            history_backfill();
            $out = [];
            foreach (history_ids() as $id) {
                $h = store_read('historie/' . $id);
                if (!$h) continue;
                $out[] = ['id' => $id, 'week' => $h['week'], 'year' => $h['year'], 'origin' => $h['origin'] ?? '', 'source' => $h['source'] ?? '',
                          'savedAt' => $h['savedAt'] ?? null, 'items' => count($h['items'] ?? [])];
            }
            respond(['ok' => true, 'weeks' => $out]);
        }

        case 'history_data': {
            require_auth();
            header('Cache-Control: no-store');
            history_backfill();
            $weeks = [];
            foreach (history_ids() as $id) {
                $h = store_read('historie/' . $id);
                if ($h) { $h['id'] = $id; $weeks[] = $h; }
            }
            respond(['ok' => true, 'weeks' => $weeks]);
        }

        case 'history_prev': {
            require_auth();
            header('Cache-Control: no-store');
            history_backfill();
            $w = (int)($_GET['week'] ?? 0);
            $y = (int)($_GET['year'] ?? 0);
            if ($w < 1 || $w > 53 || $y < 2000 || $y > 2100) respond(['ok' => true, 'week' => null]);
            $cur = history_id($w, $y);
            $prev = null;
            foreach (history_ids() as $id) if (strcmp($id, $cur) < 0) $prev = $id;   // jüngste Woche vor der Angebotswoche
            $h = $prev ? store_read('historie/' . $prev) : null;
            if ($h) {
                $items = [];
                foreach (($h['items'] ?? []) as $it) $items[] = ['code' => $it['code'] ?? null, 'name' => $it['name'] ?? '', 'price' => $it['price'] ?? ['status' => 'none']];
                $h = ['id' => $prev, 'week' => $h['week'], 'year' => $h['year'], 'items' => $items];
            }
            respond(['ok' => true, 'week' => $h]);
        }

        case 'history_import': {
            require_auth(true, 'editor');
            $b = body();
            $week = $b['week'] ?? null;
            $year = $b['year'] ?? null;
            if (!is_int($week) || $week < 1 || $week > 53 || !is_int($year) || $year < 2000 || $year > 2100) fail('Kalenderwoche oder Jahr ungültig.', 422);
            $items = clean_history_items($b['items'] ?? null);
            $id = history_id($week, $year);
            $replaced = store_read('historie/' . $id) !== null;
            store_write('historie/' . $id, ['week' => $week, 'year' => $year, 'origin' => 'Import', 'source' => s($b['source'] ?? '', 200) ?? '', 'savedAt' => now(), 'items' => $items]);
            history_undelete($id);
            audit('history', 'Preisverlauf: KW ' . $week . '/' . $year . ($replaced ? ' ersetzt' : ' hochgeladen') . ' – ' . (s($b['source'] ?? '', 120) ?: 'ohne Dateiname') . ', ' . count($items) . ' Artikel');
            respond(['ok' => true, 'id' => $id, 'replaced' => $replaced]);
        }

        case 'history_delete': {
            require_auth(true, 'editor');
            $id = (string)(body()['id'] ?? '');
            if (!preg_match('/^\d{4}-\d{2}$/', $id)) fail('Ungültige Woche.');
            [$hy, $hw] = array_map('intval', explode('-', $id));
            audit('history', 'Preisverlauf: KW ' . $hw . '/' . $hy . ' entfernt');
            store_delete('historie/' . $id);
            $del = store_read('historie_geloescht') ?? [];
            if (!in_array($id, $del, true)) { $del[] = $id; store_write('historie_geloescht', $del); }
            respond(['ok' => true]);
        }

        default:
            fail('Unbekannte Aktion.', 404);
    }
} catch (InvalidArgumentException $e) {
    fail($e->getMessage(), 422);
}
