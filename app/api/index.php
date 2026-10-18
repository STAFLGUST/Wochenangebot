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
 *   GET  ?action=offers            Angebote (Standard + Kundenangebote), angemeldet
 *   POST ?action=offers_save       Angebote anlegen/umbenennen/Regel ändern (Bearbeiter), löschen (Administrator)
 *   GET  ?action=kunden            Kundenstammdaten (nur Administrator); POST kunde_save | kunde_delete
 *   GET  ?action=kunde_status      Kunden-Anmeldung auf der Angebotsseite; POST kunde_login | kunde_logout | kunde_passwort
 *   POST ?action=kunde_token_check | kunde_token_set   Passwort über Link aus der E-Mail festlegen (Einladung/Zurücksetzen)
 *   GET  ?action=mail_status       E-Mail-Versand (nur Administrator); POST mail_save | mail_test | kunde_mail | kunden_rundmail | kunden_mail_vorschau
 *   POST ?action=kunde_bestellung  Bestellwunsch eines Kunden (Preise serverseitig aus dem Angebot) → E-Mail an uns (+ Kopie)
 *   POST ?action=bestell_settings_save   Empfänger für Bestellwünsche (nur Administrator)
 *   POST ?action=wartung_save      Wartungsmodus ein/aus (Administrator, mit Passwortbestätigung)
 *   GET  ?action=kunde_merkliste   Merkliste des angemeldeten Kunden; POST kunde_merkliste_save (Kunden-CSRF)
 *   POST ?action=kunde_abmelden_info | kunde_abmelden   Abmeldelink aus der Angebotsmail (öffentlich, Code im Link)
 *   POST ?action=abmelden1&t=…     Ein-Klick-Abmeldung aus dem E-Mail-Programm (RFC 8058, Formular statt JSON)
 *   POST ?action=mail_konto_save   Postfach/Absender speichern (nur Administrator; Passwort verschlüsselt, nie zurückgegeben)
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
require __DIR__ . '/mail.php';
$DATA = rtrim((string)$CFG['data_dir'], '/');
require __DIR__ . '/storage.php';
require __DIR__ . '/orders.php';
require __DIR__ . '/order_outbox.php';
const CATEGORIES = ['Rind', 'Kalb', 'Schwein', 'Lamm & Schaf', 'Geflügel', 'Knochen', 'Sonstiges'];
const CONDITIONS = ['frisch', 'gefroren', 'frisch-gefroren', 'dry-aged', 'unbekannt'];
const PRICE_STATUS = ['value', 'request', 'none'];

if (!function_exists('mb_substr')) { function mb_substr($s, $start, $len = null) { return $len === null ? substr($s, $start) : substr($s, $start, $len); } }
if (!function_exists('mb_strlen')) { function mb_strlen($s) { return strlen(utf8_decode($s)); } }

header('Content-Type: application/json; charset=utf-8');
header('X-Content-Type-Options: nosniff');
header('Referrer-Policy: same-origin');

set_exception_handler(function (Throwable $e) {
    store_rollback();
    error_log('[wochenangebot] ' . $e->getMessage());
    respond(['ok' => false, 'error' => 'Interner Fehler auf dem Server.'], 500);
});

/* ---------------- Hilfsfunktionen ---------------- */

function respond(array $data, int $status = 200): void
{
    store_commit(); // Intentional API errors may persist login-attempt counters.
    http_response_code($status);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}
function fail(string $msg, int $status = 400): void { respond(['ok' => false, 'error' => $msg], $status); }

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
/* Ersteinrichtung im Browser nur auf einem wirklich leeren System – nie, wenn Nutzerdaten
   vorhanden, aber nicht lesbar sind, und nie auf dem Produktivserver (WA_INSTALLED=1). */
function setup_allowed(): bool
{
    if (getenv('WA_INSTALLED') === '1' || ($_SERVER['WA_INSTALLED'] ?? '') === '1') return false;
    return store_mtime('nutzer') === null && store_mtime('admin') === null;
}
/* Unter der Nutzersperre aufrufen: gilt für Passwort UND zweiten Anmeldeschritt. */
function login_failure(array &$u): bool
{
    $S = sec();
    $u['failCount'] = (int)($u['failCount'] ?? 0) + 1;
    if ($u['failCount'] < max(3, (int)$S['lockAfter'])) return false;
    $u['lockedUntil'] = time() + 60 * max(1, (int)$S['lockMinutes']);
    $u['failCount'] = 0;
    return true;
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
    if (!empty($_SESSION['uid']) && !bg_request()) $_SESSION['seen'] = time();
}
/* Automatische Abfragen im Hintergrund (Abgleich mit anderen Bearbeitern) zählen nicht als Aktivität –
   die Abmeldung nach Inaktivität bleibt wirksam. */
function bg_request(): bool
{
    global $action;
    return ($action ?? '') === 'draft_ping' || (($action ?? '') === 'draft' && ($_GET['bg'] ?? '') === '1');
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
    if (!bg_request() && ((int)$reg[$sid]['seen'] < time() - 60 || $reg[$sid]['ip'] !== client_ip())) {
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
    mark_admin_confirmed($u);
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
/* Kurze, sitzungsgebundene Freigabe sensibler Verwaltungsaktionen. */
const ADMIN_CONFIRM_SECONDS = 300;
const CONFIRM_MAX_FAILURES = 5;
const CONFIRM_LOCK_SECONDS = 600;
function mark_admin_confirmed(array $u): void
{
    $_SESSION['adminConfirmedAt'] = time();
    $_SESSION['adminConfirmedSv'] = (int)$u['sv'];
}
function confirmation_locked(array $u): void
{
    $remaining = (int)($u['confirmUntil'] ?? 0) - time();
    if ($remaining > 0) {
        header('Retry-After: ' . $remaining);
        respond(['ok' => false, 'code' => 'confirmation_locked', 'error' => 'Zu viele falsche Passwortbestätigungen. Bitte in ' . (int)ceil($remaining / 60) . ' Minuten erneut versuchen.'], 429);
    }
}
function require_admin_confirmation(): array
{
    $u = require_auth(true, 'admin');
    confirmation_locked($u);
    $at = (int)($_SESSION['adminConfirmedAt'] ?? 0);
    if ($at <= time() && $at > time() - ADMIN_CONFIRM_SECONDS && (int)($_SESSION['adminConfirmedSv'] ?? -1) === (int)$u['sv']) return $u;
    respond(['ok' => false, 'code' => 'confirmation_required', 'error' => 'Bitte bestätigen Sie diese Verwaltungsaktion mit Ihrem aktuellen Passwort.'], 403);
}
/* Gemeinsame, kontoweite Bremse für Passwortbestätigungen; nie durch neue Sitzungen zurücksetzen. */
function confirm_password(array $me, string $password, int $invalidStatus = 422): array
{
    $result = with_lock('nutzer', function () use ($me, $password) {
        $users = users_load();
        $i = user_find($users, $me['id']);
        if ($i === null || !$users[$i]['active'] || (int)$users[$i]['sv'] !== (int)$me['sv']) fail('Bitte erneut anmelden.', 401);
        $u = &$users[$i];
        confirmation_locked($u);
        $ok = password_verify($password, (string)$u['hash']);
        if ($ok) {
            unset($u['confirmFailures'], $u['confirmSeen'], $u['confirmUntil']);
        } else {
            $n = (int)($u['confirmSeen'] ?? 0) <= time() - CONFIRM_LOCK_SECONDS || !empty($u['confirmUntil']) ? 0 : (int)($u['confirmFailures'] ?? 0);
            $u['confirmFailures'] = $n + 1;
            $u['confirmSeen'] = time();
            $u['confirmUntil'] = $n + 1 >= CONFIRM_MAX_FAILURES ? time() + CONFIRM_LOCK_SECONDS : 0;
        }
        users_save($users);
        return [$ok, $u];
    });
    [$ok, $u] = $result;
    $GLOBALS['ME'] = $u;
    if (!$ok) {
        audit('reauth_fail', 'Passwortbestätigung fehlgeschlagen', [], $u);
        confirmation_locked($u);
        respond(['ok' => false, 'code' => 'confirmation_invalid', 'error' => 'Das aktuelle Passwort ist nicht korrekt.'], $invalidStatus);
    }
    return $u;
}
/* Nach Änderungen am zweiten Faktor nur die bestätigende Sitzung behalten. */
function keep_current_session(array $u): void
{
    $_SESSION['sv'] = (int)$u['sv'];
    // Eine vorhandene Freigabe nicht verlängern, nur an die neue Sitzungsversion binden.
    $_SESSION['adminConfirmedSv'] = (int)$u['sv'];
    unset($_SESSION['totpPending']);
    $GLOBALS['ME'] = $u;
    $sid = (string)($_SESSION['sid'] ?? '');
    sess_remove(function ($k, $v) use ($u, $sid) { return $v['uid'] === $u['id'] && $k !== $sid; });
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
        if (!empty($GLOBALS['store_tx'])) throw $e;
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
function sale_text($sale): string
{
    if (!is_array($sale) || !isset($sale['value'])) return '';
    $t = 'Sonderpreis ' . price_text(['status' => 'value', 'value' => $sale['value']]);
    foreach ($sale['offers'] ?? [] as $oid => $o) {
        $def = offer_def((string)$oid);
        $t .= '; ' . ($def['name'] ?? $oid) . ': ' . (($o['status'] ?? '') === 'none' ? 'kein Sonderpreis' : price_text(['status' => 'value', 'value' => $o['value']]));
    }
    return $t;
}
function variant_text($v, string $oid = ''): string
{
    if ($oid === OFFER_STD) return is_array($v) && ($v['status'] ?? '') === 'hidden' ? 'ausgeblendet' : 'sichtbar';
    if (!is_array($v)) return 'ohne eigenen Preis';
    if (($v['status'] ?? '') === 'hidden') return 'ausgeblendet';
    return price_text($v);
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
        foreach (array_unique(array_merge(array_keys($o['variants'] ?? []), array_keys($it['variants'] ?? []))) as $oid) {
            $vf = variant_text($o['variants'][$oid] ?? null, (string)$oid); $vt = variant_text($it['variants'][$oid] ?? null, (string)$oid);
            if ($vf !== $vt) { $def = offer_def((string)$oid); $out[] = ['k' => "$id|v:$oid", 'code' => $code, 'name' => $it['name'], 'f' => ($oid === OFFER_STD ? 'Sichtbar im ' : 'Preis ') . ($def['name'] ?? $oid), 'from' => $vf, 'to' => $vt]; }
        }
        if (sale_text($o['sale'] ?? null) !== sale_text($it['sale'] ?? null)) $out[] = ['k' => "$id|sale", 'code' => $code, 'name' => $it['name'], 'f' => 'Sonderpreis (solange der Vorrat reicht)', 'from' => sale_text($o['sale'] ?? null) ?: 'kein Sonderpreis', 'to' => sale_text($it['sale'] ?? null) ?: 'kein Sonderpreis'];
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
        if ($f === 'price' || strpos($f, 'v:') === 0) $p++; elseif ($f === '+') $n++; elseif ($f === '-') $r++; else $e++;
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
    with_lock('logins', function () use ($ok) {
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
    });
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
/* ---------------- Mehrere Angebote ----------------
   Das Standardangebot („Wochenangebot“) ist die Grundlage. Kundenangebote (z. B. Edeka) haben je Artikel optional
   einen eigenen Preis in $item['variants'][<Angebots-ID>] = {status: value|request|hidden, value?, carried?}.
   Ohne eigenen Preis gilt die Regel des Angebots: 'standard' = Standardpreis zeigen, 'hidden' = Artikel ausblenden.
   Kundenpreise verlassen den Server nur aufgelöst und nur für berechtigte Nutzer (offer_resolve). */
const OFFER_STD = 'std';
const OFFER_DEFAULTS = [
    ['id' => 'chefs-culinar', 'name' => 'Wochenangebot Chefs Culinar', 'fallback' => 'standard'],
    ['id' => 'handelshof-efs', 'name' => 'Wochenangebot Handelshof, EFS', 'fallback' => 'standard'],
    ['id' => 'edeka', 'name' => 'Wochenangebot Edeka', 'fallback' => 'standard'],
    ['id' => 'bela', 'name' => 'Wochenangebot Bela', 'fallback' => 'standard'],
];
const VARIANT_STATUS = ['value', 'request', 'hidden'];
function offers_load(): array
{
    $d = store_read('angebote');
    return is_array($d) && isset($d['offers']) ? $d : ['rev' => 0, 'offers' => OFFER_DEFAULTS, 'updatedAt' => null];
}
function offer_ids(): array { return array_column(offers_load()['offers'], 'id'); }
/* Ist das Standard-Wochenangebot ohne Anmeldung sichtbar? (Voreinstellung: ja) */
function std_public(): bool { $d = offers_load(); return !array_key_exists('stdPublic', $d) || !empty($d['stdPublic']); }

/* ---------------- Kunden ----------------
   Kunden melden sich auf der Angebotsseite an (eigene Anmeldung, getrennt vom Eingabebereich) und sehen nur
   die Angebote, für die sie freigeschaltet sind. Kunden erhalten nie Zugriff auf Aktionen des Eingabebereichs:
   dort zählt nur die Mitarbeiter-Anmeldung ($_SESSION['uid']), Kunden haben $_SESSION['kid']. */
function customers_load(): array
{
    $d = store_read('kunden');
    return is_array($d) && isset($d['customers']) ? $d : ['rev' => 0, 'customers' => [], 'updatedAt' => null];
}
function customer_offers(array $c): array
{
    $known = array_merge([OFFER_STD], offer_ids());
    return array_values(array_filter($c['angebote'] ?? [], function ($o) use ($known) { return in_array($o, $known, true); }));
}
function customer_public(array $c): array
{
    $out = $c;
    $l = $c['login'] ?? null;
    $out['angebote'] = customer_offers($c);
    $out['login'] = $l ? ['username' => $l['username'], 'active' => !empty($l['active']), 'mustChange' => !empty($l['mustChange']),
                          'lastLogin' => $l['lastLogin'] ?? null, 'pwSet' => $l['pwSet'] ?? null,
                          'lockedUntil' => (int)($l['lockedUntil'] ?? 0) > time() ? (int)$l['lockedUntil'] : 0,
                          'hasPassword' => !empty($l['hash']),
                          'link' => !empty($l['token']) && (int)$l['token']['exp'] > time() ? ['p' => $l['token']['p'], 'exp' => (int)$l['token']['exp']] : null] : null;
    $out['mailAngebot'] = !array_key_exists('mailAngebot', $c) || !empty($c['mailAngebot']);
    return $out;
}
function kunde_clear(): void { foreach (['kid', 'ksv', 'kseen', 'kcsrf', 'ksid'] as $k) unset($_SESSION[$k]); }
function ksess_prune(array $list): array
{
    $max = (int)sec()['idleMinutes'] * 60;
    foreach ($list as $k => $v) if ((int)($v['seen'] ?? 0) < time() - $max) unset($list[$k]);
    return $list;
}
function ksess_remove(callable $match): int
{
    return with_lock('kundensitzungen', function () use ($match) {
        $list = store_read('kundensitzungen') ?? [];
        $n = 0;
        foreach ($list as $k => $v) if ($match($k, $v)) { unset($list[$k]); $n++; }
        if ($n) store_write('kundensitzungen', $list);
        return $n;
    });
}
/* Angemeldeter Kunde – Stammdaten, Freigabe und Zugang werden bei jeder Anfrage frisch gelesen */
$KUNDE = null;
function current_customer(): ?array
{
    global $KUNDE;
    if ($KUNDE !== null) return $KUNDE ?: null;
    start_session();
    $KUNDE = false;
    if (empty($_SESSION['kid'])) return null;
    if (time() - (int)($_SESSION['kseen'] ?? 0) > (int)sec()['idleMinutes'] * 60) { kunde_clear(); return null; }
    $c = null;
    foreach (customers_load()['customers'] as $x) if ($x['id'] === $_SESSION['kid']) { $c = $x; break; }
    $l = $c['login'] ?? null;
    if (!$c || empty($c['active']) || !$l || empty($l['active']) || (int)($l['sv'] ?? 0) !== (int)($_SESSION['ksv'] ?? -1)) { kunde_clear(); return null; }
    $sid = (string)($_SESSION['ksid'] ?? '');
    $reg = store_read('kundensitzungen') ?? [];
    if ($sid === '' || !isset($reg[$sid]) || $reg[$sid]['kid'] !== $c['id']) { kunde_clear(); return null; }
    if ((int)$reg[$sid]['seen'] < time() - 60) {
        with_lock('kundensitzungen', function () use ($sid) {
            $r = store_read('kundensitzungen') ?? [];
            if (isset($r[$sid])) { $r[$sid]['seen'] = time(); $r[$sid]['ip'] = client_ip(); store_write('kundensitzungen', ksess_prune($r)); }
        });
    }
    $_SESSION['kseen'] = time();
    return $KUNDE = $c;
}
function require_customer_csrf(): void
{
    $tok = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
    if (!is_string($tok) || !hash_equals((string)($_SESSION['kcsrf'] ?? ''), $tok)) fail('Sicherheitsprüfung fehlgeschlagen – bitte Seite neu laden.', 403);
}
function kunde_payload(array $c): array
{
    $names = [];
    foreach (customer_offers($c) as $id) { $d = offer_def($id); if ($d) $names[] = ['id' => $id, 'name' => $d['name']]; }
    return ['firma' => $c['firma'], 'ansprechpartner' => $c['ansprechpartner'] ?? '', 'username' => $c['login']['username'],
            'mustChange' => !empty($c['login']['mustChange']), 'angebote' => $names];
}
const CUSTOMER_FIELDS = ['nr' => 30, 'firma' => 120, 'ansprechpartner' => 120, 'strasse' => 120, 'plz' => 10, 'ort' => 80, 'land' => 60, 'email' => 160, 'telefon' => 40, 'notiz' => 500];
const CUSTOMER_LABELS = ['mailAngebot' => 'Wochenangebot per E-Mail', 'nr' => 'Kundennummer', 'firma' => 'Firma', 'ansprechpartner' => 'Ansprechpartner', 'strasse' => 'Straße', 'plz' => 'PLZ', 'ort' => 'Ort',
                         'land' => 'Land', 'email' => 'E-Mail', 'telefon' => 'Telefon', 'notiz' => 'Notiz', 'angebote' => 'Angebote', 'active' => 'Kunde aktiv'];

/* ---------------- E-Mail an Kunden ---------------- */
const TOKEN_DAYS = ['invite' => 7, 'reset' => 2];
function mail_settings(): array
{
    global $CFG;
    $d = store_read('mailvorlage');
    return is_array($d) ? $d + ['signature' => ''] : ['signature' => "Mit freundlichen Grüßen\n" . $CFG['company']];
}
function require_mail(): array
{
    $m = mail_cfg();
    if (!$m) fail('Der E-Mail-Versand ist noch nicht eingerichtet (Zugangsdaten des Postfachs in .env auf dem Server).', 409);
    if (!mail_base_url()) fail('Die Adresse der Angebotsseite für Links fehlt (DOMAIN bzw. WA_URL in .env).', 409);
    return $m;
}
function mail_week(): ?array
{
    $o = store_read('angebot');
    $w = (int)($o['meta']['week'] ?? 0); $y = (int)($o['meta']['year'] ?? 0);
    if (!$o || $w < 1 || $y < 2000) return null;
    $mo = (new DateTimeImmutable())->setISODate($y, $w);
    return ['week' => $w, 'year' => $y, 'from' => $mo->format('d.m.'), 'to' => $mo->modify('+6 days')->format('d.m.Y'), 'publishedAt' => $o['publishedAt'] ?? null];
}
function mail_offer_links(array $c): array
{
    $base = mail_base_url();
    $out = [];
    foreach (customer_offers($c) as $id) { $d = offer_def($id); if ($d) $out[] = [$d['name'], $base . '/' . ($id === OFFER_STD ? '' : '?angebot=' . rawurlencode($id))]; }
    return $out;
}
function mail_footer(string $kind): string
{
    global $CFG;
    return $kind === 'angebot'
        ? "Sie erhalten diese E-Mail als Kunde von {$CFG['company']}. Sie können das Wochenangebot per E-Mail jederzeit mit einem Klick abbestellen – Ihr Zugang zum Angebotsportal bleibt davon unberührt."
        : "Diese E-Mail wurde von {$CFG['company']} über das Angebotsportal versendet. Falls Sie keinen Zugang erwartet haben, können Sie sie ignorieren.";
}
/* ---------- Abmelden vom Wochenangebot ----------
   Fester Abmeldecode je Kunde: HMAC über die Kundennummer mit einem geheimen Schlüssel (wird mitgesichert,
   damit Links in alten E-Mails nach einer Wiederherstellung weiter funktionieren). Kein Login nötig. */
function abmelde_key(): string
{
    $k = store_read('abmelde-schluessel');
    $raw = is_array($k) ? base64_decode((string)($k['key'] ?? ''), true) : false;
    if (is_string($raw) && strlen($raw) === 32) return $raw;
    return with_lock('abmelde-schluessel', function () {
        $k = store_read('abmelde-schluessel');
        $raw = is_array($k) ? base64_decode((string)($k['key'] ?? ''), true) : false;
        if (is_string($raw) && strlen($raw) === 32) return $raw;
        $raw = random_bytes(32);
        store_write('abmelde-schluessel', ['key' => base64_encode($raw), 'created' => now()]);
        return $raw;
    });
}
function abmelde_token(string $kid): string
{
    return $kid . '.' . substr(rtrim(strtr(base64_encode(hash_hmac('sha256', 'abmelden|' . $kid, abmelde_key(), true)), '+/', '-_'), '='), 0, 32);
}
function abmelde_kunde(string $tok): ?array
{
    if (!preg_match('/^(k[a-f0-9]{12})\.[A-Za-z0-9_-]{32}$/', $tok, $m) || !hash_equals(abmelde_token($m[1]), $tok)) return null;
    foreach (customers_load()['customers'] as $c) if ($c['id'] === $m[1]) return $c;
    return null;
}
function abmelde_url(array $c): string { return mail_base_url() . '/#abmelden=' . (!empty($c['id']) ? abmelde_token($c['id']) : 'BEISPIEL'); }
/* Abmelden/Wiederanmelden speichern; true, wenn sich der Status geändert hat */
function abmelde_setzen(array $c, bool $ab, string $via): bool
{
    return with_lock('kunden', function () use ($c, $ab, $via) {
        $d = customers_load();
        foreach ($d['customers'] as $i => $x) if ($x['id'] === $c['id']) {
            $was = !array_key_exists('mailAngebot', $x) || !empty($x['mailAngebot']);
            if ($was === !$ab) return false;
            $d['customers'][$i]['mailAngebot'] = !$ab;
            if ($ab) $d['customers'][$i]['abgemeldet'] = ['t' => now(), 'via' => $via];
            else unset($d['customers'][$i]['abgemeldet']);
            $d['rev'] = (int)$d['rev'] + 1;
            store_write('kunden', $d);
            return true;
        }
        return false;
    });
}
function abmelde_melden(array $c, bool $ab, string $via): void
{
    global $CFG;
    $who = ['username' => 'kunde:' . ($c['login']['username'] ?? $c['id']), 'name' => $c['firma'], 'role' => 'kunde'];
    $txt = $ab ? 'Kunde hat sich vom Wochenangebot per E-Mail abgemeldet' . ($via === '1klick' ? ' (Ein-Klick im E-Mail-Programm)' : '') : 'Kunde hat sich wieder für das Wochenangebot per E-Mail angemeldet';
    audit('kunde_abmeldung', $txt, [['k' => "c{$c['id']}|mailAngebot", 'code' => $c['nr'] ?? '', 'name' => $c['firma'], 'f' => 'Wochenangebot per E-Mail', 'from' => $ab ? 'ja' : 'nein', 'to' => $ab ? 'nein' : 'ja']], $who);
    // Hinweis an uns (Antwortadresse, sonst Absender) – Fehler dabei stören den Kunden nicht
    $cfg = mail_cfg();
    if (!$cfg || !mail_base_url()) return;
    $to = $cfg['replyTo'] ?: $cfg['from'];
    $sub = ($ab ? 'Abmeldung' : 'Wiederanmeldung') . " Wochenangebot: {$c['firma']}";
    $body = ($ab ? "{$c['firma']} hat sich vom Wochenangebot per E-Mail abgemeldet und erhält es nicht mehr." : "{$c['firma']} möchte das Wochenangebot wieder per E-Mail erhalten.")
        . "

Kundennummer: " . (($c['nr'] ?? '') ?: '–') . "
E-Mail: {$c['email']}
Zeit: " . date('d.m.Y, H:i') . " Uhr

Die E-Mail-Adresse bleibt in den Stammdaten gespeichert. Einladungen und Passwort-Links können weiterhin gesendet werden.
";
    $r = mail_send_many($cfg, [['to' => $to, 'name' => '', 'subject' => $sub, 'text' => $body, 'html' => mail_layout($sub, '<p style="margin:0;">' . nl2br(mail_h($body)) . '</p>', '', '')]])[0];
    with_lock('mailversand', function () use ($to, $r, $c) {
        $l = store_read('mailversand') ?? [];
        $l[] = ['t' => now(), 'typ' => 'hinweis', 'kid' => $c['id'], 'firma' => $c['firma'], 'to' => $to, 'ok' => $r['ok'], 'error' => $r['error'] ?? '', 'by' => 'automatisch'];
        store_write('mailversand', array_slice($l, -3000));
    });
}

/* ---------- Wartungsmodus ---------- */
const WARTUNG_TEXT = 'Wir aktualisieren gerade unser Angebotsportal. In Kürze sind wir wieder für Sie da.';
function wartung(): ?array
{
    $w = store_read('wartung');
    if (!is_array($w) || empty($w['active'])) return null;
    return ['active' => true, 'message' => (string)($w['message'] ?? '') ?: WARTUNG_TEXT, 'until' => $w['until'] ?? null, 'since' => $w['since'] ?? null, 'by' => $w['by'] ?? ''];
}

/* ---------- Bestellwünsche ---------- */
function order_settings(): array
{
    $d = store_read('bestellung');
    return ['enabled' => !empty($d['enabled']), 'to' => array_values(array_filter((array)($d['to'] ?? []), 'is_string')), 'copy' => !is_array($d) || !array_key_exists('copy', $d) || !empty($d['copy']),
            'updatedAt' => $d['updatedAt'] ?? null, 'updatedBy' => $d['updatedBy'] ?? ''];
}
function order_enabled(): bool { $o = order_settings(); return $o['enabled'] && $o['to'] && mail_cfg() && mail_base_url(); }
function de_num(float $v, int $dec = 2): string { return number_format($v, $dec, ',', '.'); }
function de_qty(float $v): string { $s = number_format($v, 2, ',', '.'); return preg_replace('/,?0+$/', '', $s) ?: '0'; }
/* Mail an uns bzw. Kopie an den Kunden: [Betreff, Text, HTML] */
function mail_tpl_bestellung(array $o, bool $copy): array
{
    global $CFG;
    $c = $o['kunde'];
    $subject = $copy ? "Ihr Bestellwunsch {$o['nr']} – {$CFG['company']}" : "Bestellwunsch {$o['nr']} – {$c['firma']}" . ($o['week'] ? " (KW {$o['week']})" : '');
    $intro = $copy
        ? "vielen Dank für Ihren Bestellwunsch. Wir haben ihn erhalten und melden uns mit der Bestätigung bei Ihnen. Bitte beachten Sie: Erst mit unserer Bestätigung ist die Bestellung verbindlich."
        : "über das Angebotsportal ist ein neuer Bestellwunsch eingegangen.";
    $kopf = [['Bestellwunsch', $o['nr']], ['Eingang', date('d.m.Y, H:i', strtotime($o['t'])) . ' Uhr'], ['Angebot', $o['angebotName'] . ($o['week'] ? " · KW {$o['week']}/{$o['year']}" : '')]];
    if (!$copy) {
        $kopf[] = ['Kunde', $c['firma'] . ($c['nr'] ? " (Kd.-Nr. {$c['nr']})" : '')];
        if ($c['ansprechpartner']) $kopf[] = ['Ansprechpartner', $c['ansprechpartner']];
        $adr = trim(implode(', ', array_filter([$c['strasse'], trim($c['plz'] . ' ' . $c['ort'])])));
        if ($adr !== '') $kopf[] = ['Anschrift', $adr];
        if ($c['email']) $kopf[] = ['E-Mail', $c['email']];
        if ($c['telefon']) $kopf[] = ['Telefon', $c['telefon']];
        $kopf[] = ['Benutzerkennung', $c['username']];
    }
    if ($o['termin']) $kopf[] = ['Wunschtermin', date('d.m.Y', strtotime($o['termin']))];
    if ($o['referenz'] !== '') $kopf[] = ['Ihre Referenz', $o['referenz']];
    $pr = function ($p) { return $p['price'] !== null ? de_num($p['price']) . ' €/kg' : 'auf Anfrage'; };
    $sum = function ($p) { return $p['sum'] !== null ? de_num($p['sum']) . ' €' : '–'; };
    $t = ($copy ? mail_greeting($c) : 'Hallo,') . "\n\n" . $intro . "\n\n";
    foreach ($kopf as [$k, $v]) $t .= str_pad($k . ':', 18) . $v . "\n";
    $t .= "\nPositionen:\n";
    foreach ($o['positions'] as $i => $p) $t .= sprintf("%2d. %s%s – %s kg × %s = %s\n", $i + 1, $p['code'] ? $p['code'] . ' ' : '', $p['name'], de_qty($p['qty']), $pr($p), $sum($p));
    $t .= "\nGesamtmenge: " . de_qty($o['totalQty']) . " kg\nWarenwert (ca.): " . de_num($o['total']) . " €" . ($o['onRequest'] ? " zzgl. {$o['onRequest']} Position(en) mit Preis auf Anfrage" : '') . "\n";
    if ($o['bemerkung'] !== '') $t .= "\nBemerkung:\n{$o['bemerkung']}\n";
    $t .= "\nPreise laut Angebot (freibleibend, netto); abgerechnet wird nach tatsächlichem Gewicht.\n";
    if ($copy) $t .= "\n" . mail_settings()['signature'] . "\n";
    $row = function ($k, $v) { return '<tr><td style="padding:3px 12px 3px 0;color:#857c72;white-space:nowrap;vertical-align:top;">' . mail_h($k) . '</td><td style="padding:3px 0;">' . mail_h($v) . '</td></tr>'; };
    $h = '<p style="margin:0 0 14px;">' . mail_h($copy ? mail_greeting($c) : 'Hallo,') . '</p><p style="margin:0 0 14px;">' . mail_h($intro) . '</p>'
        . '<table role="presentation" cellpadding="0" cellspacing="0" style="font-size:14px;margin:0 0 16px;">' . implode('', array_map(function ($r) use ($row) { return $row($r[0], $r[1]); }, $kopf)) . '</table>';
    $th = 'style="text-align:left;padding:6px 6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;"';
    $thr = 'style="text-align:right;padding:6px 6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;"';
    $h .= '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:13.5px;border-collapse:collapse;"><tr><th ' . $th . '>Art.-Nr.</th><th ' . $th . '>Artikel</th><th ' . $thr . '>Menge</th><th ' . $thr . '>Preis</th><th ' . $thr . '>Summe</th></tr>';
    foreach ($o['positions'] as $p) {
        $td = 'style="padding:6px 6px;border-bottom:1px solid #eee8e1;vertical-align:top;"'; $tdr = 'style="padding:6px 6px;border-bottom:1px solid #eee8e1;text-align:right;white-space:nowrap;vertical-align:top;"';
        $h .= '<tr><td ' . $td . '>' . mail_h($p['code']) . '</td><td ' . $td . '>' . mail_h($p['name']) . ($p['group'] ? '<br><span style="font-size:11.5px;color:#857c72;">' . mail_h($p['group']) . '</span>' : '') . '</td><td ' . $tdr . '>' . de_qty($p['qty']) . ' kg</td><td ' . $tdr . '>' . mail_h($pr($p)) . '</td><td ' . $tdr . '>' . mail_h($sum($p)) . '</td></tr>';
    }
    $h .= '<tr><td colspan="2" style="padding:8px 6px;font-weight:bold;">Summe (ca.)</td><td style="padding:8px 6px;text-align:right;font-weight:bold;white-space:nowrap;">' . de_qty($o['totalQty']) . ' kg</td><td></td><td style="padding:8px 6px;text-align:right;font-weight:bold;white-space:nowrap;">' . de_num($o['total']) . ' €</td></tr></table>'
        . ($o['onRequest'] ? '<p style="margin:6px 0 0;font-size:12.5px;color:#857c72;">Zzgl. ' . $o['onRequest'] . ' Position(en) mit Preis auf Anfrage.</p>' : '')
        . ($o['bemerkung'] !== '' ? '<p style="margin:14px 0 0;padding:10px 12px;background:#f7efe9;border-radius:8px;"><strong>Bemerkung:</strong><br>' . nl2br(mail_h($o['bemerkung'])) . '</p>' : '')
        . '<p style="margin:14px 0 0;font-size:12.5px;color:#857c72;">Preise laut Angebot (freibleibend, netto); abgerechnet wird nach tatsächlichem Gewicht.</p>';
    return [$subject, $t, mail_layout($subject, $h, $copy ? mail_settings()['signature'] : '', $copy ? "Diese E-Mail bestätigt den Eingang Ihres Bestellwunsches bei {$CFG['company']}." : 'Automatisch erzeugt vom Angebotsportal. Antworten gehen direkt an den Kunden.')];
}

/* Wochenangebot / Angebotslink: [Betreff, Text, HTML] */
function mail_tpl_angebot(array $c, string $note, ?array $wk): array
{
    global $CFG;
    $links = mail_offer_links($c);
    $kw = $wk ? "KW {$wk['week']}/{$wk['year']}" : '';
    $subject = ($kw ? "Wochenangebot $kw" : 'Ihr Angebot') . ' – ' . $CFG['company'];
    $intro = $wk ? "unser Angebot für KW {$wk['week']} ({$wk['from']} – {$wk['to']}) ist online." : 'hier ist der Link zu Ihrem Angebot.';
    $user = $c['login']['username'] ?? '';
    $sig = mail_settings()['signature'];
    $t = mail_greeting($c) . "\n\n" . $intro . "\n\n" . ($note !== '' ? $note . "\n\n" : '');
    foreach ($links as [$n, $u]) $t .= "$n:\n$u\n\n";
    if ($user !== '') $t .= "Anmeldung mit Ihrer Benutzerkennung: $user\nPasswort vergessen? Antworten Sie einfach auf diese E-Mail.\n\n";
    $ab = abmelde_url($c);
    $t .= $sig . "\n\n-- \n" . mail_footer('angebot') . "\nVom Wochenangebot abmelden: $ab\n";
    $h = '<p style="margin:0 0 14px;">' . mail_h(mail_greeting($c)) . '</p><p style="margin:0 0 14px;">' . mail_h($intro) . '</p>'
        . ($note !== '' ? '<p style="margin:0 0 14px;padding:12px 14px;background:#f7efe9;border-radius:8px;">' . nl2br(mail_h($note)) . '</p>' : '');
    foreach ($links as [$n, $u]) $h .= mail_button($u, $n . ' ansehen');
    if ($user !== '') $h .= '<p style="margin:14px 0 0;font-size:13px;color:#4a443e;">Anmeldung mit Ihrer Benutzerkennung <strong>' . mail_h($user) . '</strong>. Passwort vergessen? Antworten Sie einfach auf diese E-Mail.</p>';
    $abBtn = '<p style="max-width:560px;margin:10px auto 0;text-align:center;"><a href="' . mail_h($ab) . '" style="display:inline-block;padding:7px 14px;border:1px solid #cfc6bb;border-radius:8px;color:#5f574f;font-size:12px;text-decoration:none;">Vom Wochenangebot abmelden</a></p>';
    return [$subject, $t, mail_layout($subject, $h, $sig, mail_footer('angebot'), $abBtn)];
}
/* Sonderposten eines Angebots – nur dessen Artikel und Preise: [Betreff, Text, HTML] */
function restposten_items(array $def): array
{
    $pub = store_read('angebot');
    if (!$pub) return [];
    $off = offer_resolve($pub, $def);
    return array_values(array_filter($off['items'], function ($it) { return !empty($it['sale']); }));
}
function mail_tpl_restposten(array $c, array $def, array $items, string $note): array
{
    global $CFG;
    $subject = 'Sonderposten – solange der Vorrat reicht – ' . $CFG['company'];
    $intro = 'folgende Artikel bieten wir Ihnen zum Sonderpreis an – nur solange der Vorrat reicht:';
    $url = mail_base_url() . '/' . ($def['id'] === OFFER_STD ? '' : '?angebot=' . rawurlencode($def['id']));
    $login = !empty($c['login']['active']) ? ($c['login']['username'] ?? '') : '';
    $sig = mail_settings()['signature'];
    $pr = function ($it) { return de_num((float)$it['price']['value']) . ' €/kg' . (isset($it['regular']) ? ' (statt ' . de_num((float)$it['regular']) . ' €/kg)' : ''); };
    $t = mail_greeting($c) . "\n\n" . $intro . "\n\n" . ($note !== '' ? $note . "\n\n" : '');
    foreach ($items as $it) $t .= '- ' . (($it['code'] ?? '') !== '' ? $it['code'] . ' ' : '') . $it['name'] . ': ' . $pr($it) . "\n";
    $t .= "\nPreise freibleibend, netto; abgerechnet wird nach tatsächlichem Gewicht.\n";
    if ($login !== '') $t .= "\nZum Angebot (Anmeldung mit Ihrer Benutzerkennung $login):\n$url\n";
    $ab = abmelde_url($c);
    $t .= "\n" . $sig . "\n\n-- \n" . mail_footer('angebot') . "\nVom Wochenangebot abmelden: $ab\n";
    $td = 'style="padding:7px 6px;border-bottom:1px solid #eee8e1;vertical-align:top;"';
    $tdr = 'style="padding:7px 6px;border-bottom:1px solid #eee8e1;text-align:right;white-space:nowrap;vertical-align:top;"';
    $th = 'style="text-align:left;padding:6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;"';
    $h = '<p style="margin:0 0 14px;">' . mail_h(mail_greeting($c)) . '</p><p style="margin:0 0 14px;">' . mail_h($intro) . '</p>'
        . ($note !== '' ? '<p style="margin:0 0 14px;padding:12px 14px;background:#f7efe9;border-radius:8px;">' . nl2br(mail_h($note)) . '</p>' : '')
        . '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;border-collapse:collapse;margin:0 0 12px;"><tr><th ' . $th . '>Art.-Nr.</th><th ' . $th . '>Artikel</th><th style="text-align:right;padding:6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;">Sonderpreis</th></tr>';
    foreach ($items as $it) {
        $h .= '<tr><td ' . $td . '>' . mail_h((string)($it['code'] ?? '')) . '</td><td ' . $td . '>' . mail_h($it['name']) . '</td><td ' . $tdr . '><strong style="color:#b42318;">' . de_num((float)$it['price']['value']) . ' €/kg</strong>'
            . (isset($it['regular']) ? '<br><span style="font-size:12px;color:#857c72;text-decoration:line-through;">' . de_num((float)$it['regular']) . ' €/kg</span>' : '') . '</td></tr>';
    }
    $h .= '</table><p style="margin:0 0 14px;font-size:12.5px;color:#857c72;">Solange der Vorrat reicht. Preise freibleibend, netto; abgerechnet wird nach tatsächlichem Gewicht.</p>';
    if ($login !== '') $h .= mail_button($url, 'Zum Angebot') . '<p style="margin:8px 0 0;font-size:13px;color:#4a443e;">Anmeldung mit Ihrer Benutzerkennung <strong>' . mail_h($login) . '</strong>.</p>';
    $abBtn = '<p style="max-width:560px;margin:10px auto 0;text-align:center;"><a href="' . mail_h($ab) . '" style="display:inline-block;padding:7px 14px;border:1px solid #cfc6bb;border-radius:8px;color:#5f574f;font-size:12px;text-decoration:none;">Vom Wochenangebot abmelden</a></p>';
    return [$subject, $t, mail_layout($subject, $h, $sig, mail_footer('angebot'), $abBtn)];
}
/* Wer bekommt die Sonderposten eines Angebots? Nur Kunden, denen genau dieses Angebot freigeschaltet ist. */
function restposten_reason(array $c, string $oid): string
{
    if (!in_array($oid, customer_offers($c), true)) return 'Angebot nicht freigeschaltet';
    if (empty($c['active'])) return 'Kunde inaktiv';
    if (empty($c['email'])) return 'keine E-Mail-Adresse';
    if (array_key_exists('mailAngebot', $c) && empty($c['mailAngebot'])) return !empty($c['abgemeldet']) ? 'hat sich vom Wochenangebot abgemeldet' : 'Angebote per E-Mail nicht gewünscht';
    return '';
}
/* Einladung / Passwort zurücksetzen */
function mail_tpl_zugang(array $c, string $url, string $purpose, int $exp): array
{
    global $CFG;
    $inv = $purpose === 'invite';
    $subject = $inv ? "Ihr Zugang zum Angebotsportal von {$CFG['company']}" : "Passwort für Ihren Zugang neu festlegen – {$CFG['company']}";
    $until = date('d.m.Y, H:i', $exp) . ' Uhr';
    $user = $c['login']['username'];
    $lines = $inv
        ? ["für Sie ist ein Zugang zu unserem Angebotsportal eingerichtet. Dort sehen Sie jederzeit Ihr aktuelles Angebot.", "Ihre Benutzerkennung: $user", "Bitte legen Sie über den folgenden Link Ihr persönliches Passwort fest. Der Link ist bis $until gültig und kann nur einmal verwendet werden."]
        : ["für Ihren Zugang zu unserem Angebotsportal (Benutzerkennung: $user) wurde ein neues Passwort angefordert.", "Bitte legen Sie über den folgenden Link ein neues Passwort fest. Der Link ist bis $until gültig und kann nur einmal verwendet werden."];
    $sig = mail_settings()['signature'];
    $t = mail_greeting($c) . "\n\n" . implode("\n\n", $lines) . "\n\n" . $url . "\n\n" . $sig . "\n\n-- \n" . mail_footer('zugang') . "\n";
    $h = '<p style="margin:0 0 14px;">' . mail_h(mail_greeting($c)) . '</p>';
    foreach ($lines as $l) $h .= '<p style="margin:0 0 14px;">' . mail_h($l) . '</p>';
    $h .= mail_button($url, $inv ? 'Passwort festlegen' : 'Neues Passwort festlegen')
        . '<p style="margin:12px 0 0;font-size:12px;color:#857c72;word-break:break-all;">Falls die Schaltfläche nicht funktioniert: ' . mail_h($url) . '</p>';
    return [$subject, $t, mail_layout($subject, $h, $sig, mail_footer('zugang'))];
}
/* Einmal-Link erzeugen (gespeichert wird nur der Hash) */
function kunde_token_new(string $kid, string $purpose): array
{
    $tok = rtrim(strtr(base64_encode(random_bytes(32)), '+/', '-_'), '=');
    $exp = time() + 86400 * TOKEN_DAYS[$purpose];
    $c = with_lock('kunden', function () use ($kid, $tok, $exp, $purpose) {
        $d = customers_load();
        foreach ($d['customers'] as $i => $x) if ($x['id'] === $kid && !empty($x['login'])) {
            $d['customers'][$i]['login']['token'] = ['h' => hash('sha256', $tok), 'exp' => $exp, 'p' => $purpose, 't' => now()];
            store_write('kunden', $d);
            return $d['customers'][$i];
        }
        return null;
    });
    if (!$c) fail('Kunde oder Zugang nicht gefunden.', 404);
    return [$tok, $exp, $c];
}
function kunde_by_token(string $tok): ?array
{
    if (!preg_match('/^[A-Za-z0-9_-]{40,64}$/', $tok)) return null;
    $h = hash('sha256', $tok);
    foreach (customers_load()['customers'] as $c) {
        $t = $c['login']['token'] ?? null;
        if ($t && hash_equals((string)$t['h'], $h) && (int)$t['exp'] > time() && !empty($c['active']) && !empty($c['login']['active'])) return $c;
    }
    return null;
}
/* Mehrere Nachrichten über eine Verbindung; Ergebnis je Auftrag */
function mail_send_many(array $cfg, array $jobs): array
{
    $smtp = new Smtp($cfg);
    $res = [];
    try {
        foreach ($jobs as $k => $j) {
            try {
                $smtp->send($j['to'], mail_build($cfg, $j['to'], $j['name'] ?? '', $j['subject'], $j['text'], $j['html'], $j['headers'] ?? []));
                $res[$k] = ['ok' => true];
            } catch (RuntimeException $e) {
                $res[$k] = ['ok' => false, 'error' => $e->getMessage()];
                if (preg_match('/Verbindung|Anmeldung|Verschlüssel|nicht bereit|Begrüßung|nur an einen Server|entschlüsselt/', $e->getMessage())) {
                    foreach ($jobs as $k2 => $x) if (!isset($res[$k2])) $res[$k2] = ['ok' => false, 'error' => $e->getMessage()];
                    break;
                }
            }
        }
    } finally { $smtp->close(); }
    return $res;
}
/* Versand an Kunden vermerken (letzte E-Mail, Wochenversand) und ins Versandprotokoll schreiben */
function mail_record(array $entries, ?array $wk = null): void
{
    global $ME;
    with_lock('kunden', function () use ($entries, $wk) {
        $d = customers_load();
        foreach ($d['customers'] as $i => $c) foreach ($entries as $e) if ($e['kid'] === $c['id']) {
            $d['customers'][$i]['mailLast'] = ['typ' => $e['typ'], 't' => now(), 'ok' => $e['ok'], 'to' => $e['to']];
            if ($e['ok'] && $e['typ'] === 'woche' && $wk) $d['customers'][$i]['weekly'] = ['week' => $wk['week'], 'year' => $wk['year'], 't' => now()];
        }
        store_write('kunden', $d);
    });
    with_lock('mailversand', function () use ($entries, $ME) {
        $l = store_read('mailversand') ?? [];
        foreach ($entries as $e) $l[] = ['t' => now(), 'typ' => $e['typ'], 'kid' => $e['kid'], 'firma' => $e['firma'], 'to' => $e['to'], 'ok' => $e['ok'], 'error' => $e['error'] ?? '', 'by' => $ME['name'] ?? ''];
        store_write('mailversand', array_slice($l, -3000));
    });
}
const MAIL_TYP = ['woche' => 'Wochenangebot', 'angebot' => 'Angebotslink', 'invite' => 'Einladung', 'reset' => 'Passwort-Link', 'test' => 'Testmail', 'hinweis' => 'Hinweis Abmeldung', 'bestellung' => 'Bestellwunsch', 'bestellkopie' => 'Kopie Bestellwunsch', 'restposten' => 'Sonderposten'];
function mail_job_for(array $c, string $typ, string $note = '', ?array $wk = null): array
{
    if (empty($c['email'])) throw new InvalidArgumentException("Für „{$c['firma']}“ ist keine E-Mail-Adresse hinterlegt.");
    [$sub, $txt, $html] = mail_tpl_angebot($c, $note, $wk);
    // Ein-Klick-Abmeldung im E-Mail-Programm (RFC 8058) – erwartet u. a. von Gmail/Yahoo bei regelmäßigen Sendungen
    $one = mail_base_url() . '/api/?action=abmelden1&t=' . rawurlencode(abmelde_token($c['id']));
    return ['to' => $c['email'], 'name' => $c['ansprechpartner'] ?: $c['firma'], 'subject' => $sub, 'text' => $txt, 'html' => $html,
            'headers' => ['List-Unsubscribe' => '<' . $one . '>', 'List-Unsubscribe-Post' => 'List-Unsubscribe=One-Click']];
}
/* Kunde anmelden (nach Passwortprüfung oder Einmal-Link) */
function kunde_sign_in(array $c): void
{
    session_regenerate_id(true);
    kunde_clear();
    $_SESSION['kid'] = $c['id'];
    $_SESSION['ksv'] = (int)($c['login']['sv'] ?? 0);
    $_SESSION['kseen'] = time();
    $_SESSION['kcsrf'] = bin2hex(random_bytes(32));
    with_lock('kundensitzungen', function () use ($c) {
        $r = ksess_prune(store_read('kundensitzungen') ?? []);
        $sid = bin2hex(random_bytes(12));
        $r[$sid] = ['kid' => $c['id'], 'ip' => client_ip(), 'ua' => mb_substr((string)($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 240), 'created' => now(), 'seen' => time()];
        store_write('kundensitzungen', $r);
        $_SESSION['ksid'] = $sid;
    });
    $GLOBALS['KUNDE'] = $c;
}
function offer_def(string $id): ?array
{
    if ($id === OFFER_STD) return ['id' => OFFER_STD, 'name' => 'Wochenangebot', 'fallback' => 'standard'];
    foreach (offers_load()['offers'] as $o) if ($o['id'] === $id) return $o;
    return null;
}
function clean_variants($v, string $where, array $known): array
{
    $out = [];
    if (!is_array($v)) return $out;
    foreach ($v as $oid => $p) {
        if (!is_string($oid) || !is_array($p)) continue;
        $st = $p['status'] ?? '';
        if ($oid === OFFER_STD) {                       // Wochenangebot: nur „ausgeblendet“ (Preis steht in price)
            if ($st === 'hidden') $out[$oid] = ['status' => 'hidden'];
            continue;
        }
        if (!in_array($oid, $known, true)) continue;   // gelöschte Angebote fallen weg
        if (!in_array($st, VARIANT_STATUS, true)) throw new InvalidArgumentException("Ungültiger Angebotspreis ($where).");
        $row = ['status' => $st];
        if ($st === 'value') {
            $x = $p['value'] ?? null;
            if (!is_int($x) && !is_float($x)) throw new InvalidArgumentException("Angebotspreis fehlt ($where).");
            $x = (float)$x;
            if ($x < 0 || $x >= 100000) throw new InvalidArgumentException("Angebotspreis außerhalb des gültigen Bereichs ($where).");
            $row['value'] = round($x, 4);
        }
        if (!empty($p['carried'])) $row['carried'] = true;
        $out[$oid] = $row;
    }
    return $out;
}
/* Sonderpreis „solange der Vorrat reicht“ (Artikel mit kurzem oder überschrittenem MHD):
   $item['sale'] = {value: Grundsonderpreis für alle Angebote, offers?: {<Angebots-ID>: {value} | {status: 'none'}}}.
   Ein Sonderposten ohne Bestand (laut letzter Bestandsliste) wird in allen Angeboten automatisch ausgeblendet. */
function clean_money($x, string $what): float
{
    if (!is_int($x) && !is_float($x)) throw new InvalidArgumentException("$what fehlt.");
    $x = (float)$x;
    if ($x < 0 || $x >= 100000) throw new InvalidArgumentException("$what außerhalb des gültigen Bereichs.");
    return round($x, 4);
}
function clean_sale($v, string $where, array $known): ?array
{
    if (!is_array($v) || !array_key_exists('value', $v)) return null;
    $out = ['value' => clean_money($v['value'], "Sonderpreis ($where)")];
    $offers = [];
    foreach (is_array($v['offers'] ?? null) ? $v['offers'] : [] as $oid => $o) {
        if (!is_string($oid) || !is_array($o) || ($oid !== OFFER_STD && !in_array($oid, $known, true))) continue;
        if (($o['status'] ?? '') === 'none') $offers[$oid] = ['status' => 'none'];
        elseif (array_key_exists('value', $o)) $offers[$oid] = ['value' => clean_money($o['value'], "Sonderpreis ($where)")];
    }
    if ($offers) $out['offers'] = $offers;
    $since = s($v['since'] ?? null, 30);
    if ($since) $out['since'] = $since;
    return $out;
}
function sale_for(array $it, string $oid): ?float
{
    $s = $it['sale'] ?? null;
    if (!is_array($s) || !isset($s['value'])) return null;
    $o = $s['offers'][$oid] ?? null;
    if (is_array($o)) return ($o['status'] ?? '') === 'none' ? null : (float)$o['value'];
    return (float)$s['value'];
}
/* Artikelnummern mit eingelagertem Bestand (null = keine Bestandsliste vorhanden) */
function stock_codes(): ?array
{
    static $codes = false;
    if ($codes !== false) return $codes;
    $st = store_read('bestand');
    if (!is_array($st) || empty($st['articles'])) return $codes = null;
    $codes = [];
    foreach ($st['articles'] as $a) if ((float)($a['kg'] ?? 0) > 0) $codes[code_key((string)$a['code'])] = true;
    return $codes;
}
function sold_out(array $it): bool
{
    $codes = stock_codes();
    $c = (string)($it['code'] ?? '');
    return $codes !== null && $c !== '' && !isset($codes[code_key($c)]);
}
/* Angebot für die Auslieferung: nur Preise dieses Angebots, keine Kundenpreise anderer Angebote,
   keine ausgeblendeten Artikel, Sonderpreise aufgelöst (ohne Angaben zu anderen Angeboten) */
function offer_resolve(array $m, array $def): array
{
    $std = $def['id'] === OFFER_STD;
    $items = [];
    foreach ($m['items'] ?? [] as $it) {
        $v = $it['variants'][$def['id']] ?? null;
        $sale = sale_for($it, $def['id']);
        unset($it['variants'], $it['sale']);
        if ($v && $v['status'] === 'hidden') continue;
        if ($sale !== null && sold_out($it)) continue;   // Sonderposten ausverkauft
        $regular = $it['price'];
        if ($std) {
            // Wochenangebot: Grundpreis und Zusatzpreise bleiben
        } elseif ($v) {
            $regular = $v['status'] === 'value' ? ['status' => 'value', 'value' => $v['value']] : ['status' => 'request'];
            $it['price'] = $regular;
            $it['altPrices'] = [];
        } elseif (($def['fallback'] ?? 'standard') === 'hidden') {
            if ($sale === null) continue;
            $regular = null;
        }
        if ($sale !== null) {
            $it['price'] = ['status' => 'value', 'value' => $sale];
            $it['altPrices'] = [];
            $it['sale'] = true;
            if ($regular && ($regular['status'] ?? '') === 'value' && (float)$regular['value'] > $sale) $it['regular'] = (float)$regular['value'];
        }
        $items[] = $it;
    }
    $used = [];
    foreach ($items as $it) $used[$it['groupId']] = true;
    $m['groups'] = array_values(array_filter($m['groups'] ?? [], function ($g) use ($used) { return isset($used[$g['id']]); }));
    $secs = [];
    foreach ($m['groups'] as $g) if (($g['section'] ?? '') !== '' && !in_array($g['section'], $secs, true)) $secs[] = $g['section'];
    $m['sections'] = $secs;
    $m['items'] = $items;
    $m['meta']['offerId'] = $def['id'];
    $m['meta']['offerName'] = $def['name'];
    return $m;
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
    $known = offer_ids();
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
        $vars = clean_variants($it['variants'] ?? null, $name, $known);
        if ($vars) $row['variants'] = $vars;
        $sale = clean_sale($it['sale'] ?? null, $name, $known);
        if ($sale) $row['sale'] = $sale;
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
    foreach (store_names('historie') as $f) {
        $id = basename($f);
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
        if (!empty($it['variants'])) $row['variants'] = $it['variants'];
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
    foreach (store_names('versionen') as $f) $sources[] = store_read('versionen/' . basename($f));
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

/* ---------------- Gemeinsames Bearbeiten des Entwurfs ----------------
   Jede Speicherung erhöht die Revision. Nach Veröffentlichen/Verwerfen bleibt die Revision in
   „entwurf-stand“ erhalten, damit veraltete Fenster den Entwurf nicht mit altem Stand neu anlegen. */
function draft_rev(?array $draft): int
{
    if ($draft !== null) return (int)($draft['rev'] ?? 0);
    $st = store_read('entwurf-stand');
    return is_array($st) ? (int)($st['rev'] ?? 0) : 0;
}
function draft_end(?array $draft, string $why): int
{
    $rev = draft_rev($draft) + 1;
    store_write('entwurf-stand', ['rev' => $rev, 'reason' => $why, 'by' => current_user()['name'] ?? '', 'at' => now()]);
    store_delete('entwurf');
    return $rev;
}
function draft_conflict(?array $draft): void
{
    $st = $draft === null ? store_read('entwurf-stand') : null;
    $by = (string)($draft['savedBy'] ?? ($st['by'] ?? ''));
    $what = $draft === null && is_array($st) ? 'den Entwurf ' . ($st['reason'] ?? 'geändert') : 'den Entwurf geändert';
    respond(['ok' => false, 'conflict' => true, 'revision' => draft_rev($draft), 'by' => $by,
             'error' => ($by !== '' ? $by : 'Jemand anderes') . ' hat inzwischen ' . $what . '.'], 409);
}

/* ---------------- Aktionen ---------------- */

$action = (string)($_GET['action'] ?? '');
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$writeActions = ['reauth', 'setup', 'login', 'logout', 'save_draft', 'discard_draft', 'publish', 'change_password', 'history_import', 'history_delete', 'user_save', 'user_delete', 'stock_import', 'master_save',
                 'login_2fa', 'twofa_begin', 'twofa_enable', 'twofa_disable', 'security_save', 'session_end', 'ip_unblock', 'user_unlock', 'geo_update', 'geo_clear_stats', 'offers_save',
                 'kunde_save', 'kunde_delete', 'kunde_login', 'kunde_logout', 'kunde_passwort', 'kunde_token_check', 'kunde_token_set',
                 'mail_save', 'mail_test', 'kunde_mail', 'kunden_rundmail', 'kunden_mail_vorschau', 'mail_konto_save', 'kunde_abmelden_info', 'kunde_abmelden', 'kunde_merkliste_save', 'kunde_bestellung', 'bestell_settings_save', 'wartung_save', 'draft_ping', 'bestellung_save', 'bestellung_mail_retry', 'kunden_restposten'];
if (in_array($action, $writeActions, true)) {
    if ($method !== 'POST') fail('Methode nicht erlaubt.', 405);
    if (stripos((string)($_SERVER['CONTENT_TYPE'] ?? ''), 'application/json') !== 0) fail('Ungültige Anfrage.', 415);
}

/* Ländersperre (ganze Seite oder nur Eingabebereich) */
/* Öffentlicher Bereich = Angebotsseite inkl. Kunden-Anmeldung (Kundenangebote verlangen dort selbst eine Anmeldung) */
$isPublic = ($action === 'offer' && empty($_GET['draft'])) || in_array($action, ['kunde_status', 'kunde_login', 'kunde_logout', 'kunde_passwort', 'kunde_token_check', 'kunde_token_set', 'kunde_abmelden_info', 'kunde_abmelden', 'abmelden1', 'kunde_merkliste', 'kunde_merkliste_save', 'kunde_bestellung', 'kunde_bestellungen', 'kunde_bestellung_detail'], true);
$S = sec();
if (!empty($S['geoEnabled']) && (!$isPublic || $S['geoScope'] === 'all')) {
    $cc = geo_blocked(client_ip(), $S);
    if ($cc !== null) {
        geo_count($cc);
        fail('Der Zugriff aus Ihrem Land ist leider nicht möglich.', 403);
    }
}

/* Wartungsmodus: Angebotsseite und Kundenfunktionen pausieren; Mitarbeiter arbeiten normal weiter.
   Abmelden vom Wochenangebot und Kunden-Abmelden bleiben immer möglich. */
const WARTUNG_GESPERRT = ['offer', 'kunde_login', 'kunde_passwort', 'kunde_token_check', 'kunde_token_set', 'kunde_merkliste', 'kunde_merkliste_save', 'kunde_bestellung', 'kunde_bestellungen', 'kunde_bestellung_detail'];
if (in_array($action, WARTUNG_GESPERRT, true) && ($W = wartung()) && !current_user()) {
    header('Retry-After: 600');
    respond(['ok' => false, 'wartung' => true, 'error' => $W['message'], 'until' => $W['until']], 503);
}

/* IP-Freigabe für den Eingabebereich (die öffentliche Angebotsseite bleibt frei) */
if (!$isPublic) {
    if (!empty($S['ipEnabled']) && $S['adminIps'] && !ip_allowed(client_ip(), $S['adminIps'])) {
        fail('Der Eingabebereich ist von dieser Internetadresse (' . client_ip() . ') aus nicht freigegeben.', 403);
    }
}

try {
    orders_action($action);
    switch ($action) {

        case 'offer': {
            header('Cache-Control: no-cache');
            $oid = (string)($_GET['angebot'] ?? OFFER_STD);
            if ($oid === '') $oid = OFFER_STD;
            if (!preg_match('/^[a-z0-9-]{1,40}$/', $oid)) fail('Unbekanntes Angebot.', 404);
            if ($oid !== OFFER_STD || !std_public()) {
                // Mitarbeiter sehen alle Angebote; Kunden nur freigeschaltete; sonst Anmeldung nötig
                if (current_user()) require_auth();
                elseif ($k = current_customer()) {
                    if (!empty($k['login']['mustChange'])) fail('Bitte zuerst ein eigenes Passwort festlegen.', 403);
                    if (!in_array($oid, customer_offers($k), true)) fail('Dieses Angebot ist für Ihren Zugang nicht freigeschaltet.', 403);
                } else fail('Bitte anmelden.', 401);
                header('Cache-Control: private, no-store');
            }
            $def = offer_def($oid);
            if (!$def) fail('Unbekanntes Angebot.', 404);
            if (!empty($_GET['draft'])) {
                require_auth();
                $d = store_read('entwurf') ?? store_read('angebot');
                if (!$d) fail('Kein Entwurf vorhanden.', 404);
                respond(['ok' => true, 'company' => $CFG['company'], 'preview' => true, 'offer' => offer_resolve($d, $def)]);
            }
            $published = store_read('angebot');
            if ($published === null) fail('Es ist noch kein Angebot veröffentlicht.', 404);
            if ($oid === OFFER_STD && std_public()) {
                $etag = '"' . hash('sha256', json_encode($published) . ':std') . '"';
                header('ETag: ' . $etag);
                if (trim((string)($_SERVER['HTTP_IF_NONE_MATCH'] ?? '')) === $etag) { http_response_code(304); exit; }
            }
            respond(['ok' => true, 'company' => $CFG['company'], 'offer' => offer_resolve($published, $def)]);
        }

        case 'offers': {
            require_auth();
            header('Cache-Control: no-store');
            $d = offers_load();
            respond(['ok' => true, 'rev' => $d['rev'], 'offers' => $d['offers'], 'std' => offer_def(OFFER_STD), 'stdPublic' => std_public()]);
        }

        case 'offers_save': {
            $me = require_auth(true, 'editor');
            $b = body();
            $list = [];
            $names = [];
            foreach (array_slice(is_array($b['offers'] ?? null) ? $b['offers'] : [], 0, 30) as $o) {
                if (!is_array($o)) continue;
                $name = s($o['name'] ?? null, 80, false);
                if ($name === null || mb_strlen($name) < 2) throw new InvalidArgumentException('Jedes Angebot braucht einen Namen (mindestens 2 Zeichen).');
                $key = mb_strtolower($name);
                if (isset($names[$key]) || $key === 'wochenangebot') throw new InvalidArgumentException("Der Name „{$name}“ ist bereits vergeben.");
                $names[$key] = true;
                $id = (string)($o['id'] ?? '');
                if ($id === '' || $id === OFFER_STD || !preg_match('/^[a-z0-9-]{1,40}$/', $id)) throw new InvalidArgumentException('Ungültige Angebots-ID.');
                $fb = ($o['fallback'] ?? '') === 'hidden' ? 'hidden' : 'standard';
                $list[] = ['id' => $id, 'name' => $name, 'fallback' => $fb];
            }
            if (count(array_unique(array_column($list, 'id'))) !== count($list)) throw new InvalidArgumentException('Angebots-IDs sind doppelt.');
            $res = with_lock('angebote', function () use ($b, $list, $me) {
                $cur = offers_load();
                if ((int)($b['rev'] ?? -1) !== (int)$cur['rev']) fail('Die Angebote wurden inzwischen an anderer Stelle geändert. Bitte die Seite neu laden.', 409);
                $old = []; foreach ($cur['offers'] as $o) $old[$o['id']] = $o;
                $new = []; foreach ($list as $o) $new[$o['id']] = $o;
                $removed = array_diff_key($old, $new);
                if ($removed) require_admin_confirmation();
                $d = [];
                $FB = ['standard' => 'Standardpreis zeigen', 'hidden' => 'Artikel ausblenden'];
                foreach ($new as $id => $o) {
                    if (!isset($old[$id])) { $d[] = ['k' => "o$id|+", 'code' => '', 'name' => $o['name'], 'f' => 'Neues Angebot', 'from' => '', 'to' => 'ohne eigenen Preis: ' . $FB[$o['fallback']]]; continue; }
                    if ($old[$id]['name'] !== $o['name']) $d[] = ['k' => "o$id|name", 'code' => '', 'name' => $o['name'], 'f' => 'Name', 'from' => $old[$id]['name'], 'to' => $o['name']];
                    if (($old[$id]['fallback'] ?? 'standard') !== $o['fallback']) $d[] = ['k' => "o$id|fb", 'code' => '', 'name' => $o['name'], 'f' => 'Ohne eigenen Preis', 'from' => $FB[$old[$id]['fallback'] ?? 'standard'], 'to' => $FB[$o['fallback']]];
                }
                foreach ($removed as $id => $o) $d[] = ['k' => "o$id|-", 'code' => '', 'name' => $o['name'], 'f' => 'Angebot gelöscht', 'from' => $o['name'], 'to' => ''];
                $oldPub = !array_key_exists('stdPublic', $cur) || !empty($cur['stdPublic']);
                $pub = array_key_exists('stdPublic', $b) ? !empty($b['stdPublic']) : $oldPub;
                if ($pub !== $oldPub) {
                    require_admin_confirmation();
                    $d[] = ['k' => 'ostd|pub', 'code' => '', 'name' => 'Wochenangebot', 'f' => 'Öffentlich ohne Anmeldung', 'from' => $oldPub ? 'ja' : 'nein', 'to' => $pub ? 'ja' : 'nein'];
                }
                $out = ['rev' => (int)$cur['rev'] + 1, 'updatedAt' => now(), 'updatedBy' => $me['name'], 'offers' => array_values($new), 'stdPublic' => $pub];
                store_write('angebote', $out);
                return [$out, $d];
            });
            [$out, $d] = $res;
            if ($d) audit('offers', 'Angebote geändert', $d);
            respond(['ok' => true, 'rev' => $out['rev'], 'offers' => $out['offers'], 'stdPublic' => $out['stdPublic']]);
        }

        /* ---------- Kunden-Anmeldung (Angebotsseite) ---------- */
        case 'kunde_status': {
            header('Cache-Control: no-store');
            start_session();
            $k = current_customer();
            $staff = current_user() !== null;
            respond(['ok' => true, 'stdPublic' => std_public(), 'staff' => $staff, 'kunde' => $k ? kunde_payload($k) : null, 'bestellung' => $k ? order_enabled() : false, 'wartung' => wartung(), 'csrf' => $k ? ($_SESSION['kcsrf'] ?? null) : null]);
        }

        case 'kunde_login': {
            start_session();
            attempts_check();
            $b = body();
            $name = is_string($b['username'] ?? null) ? strtolower(trim($b['username'])) : '';
            $pw = (string)($b['password'] ?? '');
            $res = with_lock('kunden', function () use ($name, $pw) {
                $d = customers_load();
                foreach ($d['customers'] as $i => $c) {
                    $l = $c['login'] ?? null;
                    if (!$l || $name === '' || $l['username'] !== $name) continue;
                    if ((int)($l['lockedUntil'] ?? 0) > time()) { password_verify($pw, (string)$l['hash']); return ['locked', $c]; }
                    if (!password_verify($pw, (string)$l['hash'])) {
                        $lockedNow = login_failure($d['customers'][$i]['login']);
                        store_write('kunden', $d);
                        return [$lockedNow ? 'lockednow' : 'bad', $d['customers'][$i]];
                    }
                    if (empty($c['active']) || empty($l['active'])) return ['inactive', $c];
                    if (password_needs_rehash((string)$l['hash'], PASSWORD_DEFAULT)) $d['customers'][$i]['login']['hash'] = password_hash($pw, PASSWORD_DEFAULT);
                    $d['customers'][$i]['login']['failCount'] = 0;
                    $d['customers'][$i]['login']['lockedUntil'] = 0;
                    $d['customers'][$i]['login']['lastLogin'] = now();
                    store_write('kunden', $d);
                    return ['ok', $d['customers'][$i]];
                }
                password_verify($pw, '$2y$10$y80WR5wtxxV9G3NpBGQXmeL3EYKIGKm4gaElkDTK2cWFQtjyZdoPa'); // gleiche Laufzeit
                return ['bad', null];
            });
            [$st, $c] = $res;
            $who = ['username' => 'kunde:' . mb_substr($name, 0, 40), 'name' => $c['firma'] ?? '', 'role' => 'kunde'];
            if ($st !== 'ok') {
                attempts_record(false);
                $why = ['inactive' => ' – Zugang deaktiviert', 'locked' => ' – Zugang gesperrt', 'lockednow' => ' – Zugang nach zu vielen Fehlversuchen gesperrt', 'bad' => ''][$st];
                audit('kunde_login_fail', 'Kunden-Anmeldung fehlgeschlagen' . ($name !== '' ? ' (Benutzername „' . mb_substr($name, 0, 40) . '“)' : '') . $why, [], $who);
                usleep(400000);
                if ($st === 'inactive') fail('Dieser Zugang ist deaktiviert. Bitte wenden Sie sich an Ihren Ansprechpartner.', 401);
                if ($st === 'locked' || $st === 'lockednow') fail('Dieser Zugang ist wegen zu vieler Fehlversuche vorübergehend gesperrt. Bitte später erneut versuchen.', 429);
                fail('Benutzername oder Passwort ist nicht korrekt.', 401);
            }
            attempts_record(true);
            kunde_sign_in($c);
            audit('kunde_login', 'Kunde angemeldet', [], $who);
            respond(['ok' => true, 'csrf' => $_SESSION['kcsrf'], 'kunde' => kunde_payload($c)]);
        }

        case 'kunde_logout': {
            start_session();
            if (current_customer()) {
                require_customer_csrf();
                $sid = (string)($_SESSION['ksid'] ?? '');
                ksess_remove(function ($k) use ($sid) { return $k === $sid; });
            }
            kunde_clear();
            respond(['ok' => true]);
        }

        case 'kunde_passwort': {
            $c = current_customer();
            if (!$c) fail('Bitte erneut anmelden.', 401);
            require_customer_csrf();
            $b = body();
            if (!password_verify((string)($b['current'] ?? ''), (string)$c['login']['hash'])) fail('Das bisherige Passwort ist nicht korrekt.', 422);
            $new = check_password($b['password'] ?? '', $c['login']['username']);
            if (password_verify($new, (string)$c['login']['hash'])) fail('Bitte ein anderes als das bisherige Passwort wählen.', 422);
            $c2 = with_lock('kunden', function () use ($c, $new) {
                $d = customers_load();
                foreach ($d['customers'] as $i => $x) if ($x['id'] === $c['id']) {
                    $d['customers'][$i]['login']['hash'] = password_hash($new, PASSWORD_DEFAULT);
                    $d['customers'][$i]['login']['mustChange'] = false;
                    $d['customers'][$i]['login']['pwSet'] = now();
                    $d['customers'][$i]['login']['sv'] = (int)($x['login']['sv'] ?? 0) + 1;
                    unset($d['customers'][$i]['login']['token']);
                    store_write('kunden', $d);
                    return $d['customers'][$i];
                }
                return null;
            });
            if (!$c2) fail('Zugang nicht gefunden.', 404);
            $_SESSION['ksv'] = (int)$c2['login']['sv'];
            $sid = (string)($_SESSION['ksid'] ?? '');
            ksess_remove(function ($k, $v) use ($c2, $sid) { return $v['kid'] === $c2['id'] && $k !== $sid; });   // andere Geräte abmelden
            $GLOBALS['KUNDE'] = $c2;
            audit('kunde_password', 'Kunde hat eigenes Passwort festgelegt', [], ['username' => 'kunde:' . $c2['login']['username'], 'name' => $c2['firma'], 'role' => 'kunde']);
            respond(['ok' => true, 'kunde' => kunde_payload($c2)]);
        }

        /* ---------- Passwort über Link aus der E-Mail (Einladung / Zurücksetzen) ---------- */
        case 'kunde_token_check': {
            attempts_check();
            $c = kunde_by_token((string)(body()['token'] ?? ''));
            if (!$c) { attempts_record(false); fail('Dieser Link ist abgelaufen oder wurde bereits verwendet. Bitte fordern Sie bei uns einen neuen an.', 410); }
            respond(['ok' => true, 'firma' => $c['firma'], 'username' => $c['login']['username'], 'purpose' => $c['login']['token']['p'], 'exp' => (int)$c['login']['token']['exp']]);
        }

        case 'kunde_token_set': {
            start_session();
            attempts_check();
            $b = body();
            $tok = (string)($b['token'] ?? '');
            $c = kunde_by_token($tok);
            if (!$c) { attempts_record(false); fail('Dieser Link ist abgelaufen oder wurde bereits verwendet. Bitte fordern Sie bei uns einen neuen an.', 410); }
            $new = check_password($b['password'] ?? '', $c['login']['username']);
            $c2 = with_lock('kunden', function () use ($c, $new, $tok) {
                $d = customers_load();
                foreach ($d['customers'] as $i => $x) if ($x['id'] === $c['id']) {
                    $t = $x['login']['token'] ?? null;
                    if (!$t || !hash_equals((string)$t['h'], hash('sha256', $tok)) || (int)$t['exp'] <= time()) return null;   // inzwischen verbraucht
                    $l = &$d['customers'][$i]['login'];
                    $l['hash'] = password_hash($new, PASSWORD_DEFAULT);
                    $l['mustChange'] = false; $l['pwSet'] = now(); $l['sv'] = (int)($l['sv'] ?? 0) + 1;
                    $l['failCount'] = 0; $l['lockedUntil'] = 0; $l['lastLogin'] = now();
                    unset($l['token']);
                    store_write('kunden', $d);
                    return $d['customers'][$i];
                }
                return null;
            });
            if (!$c2) fail('Dieser Link ist abgelaufen oder wurde bereits verwendet. Bitte fordern Sie bei uns einen neuen an.', 410);
            attempts_record(true);
            ksess_remove(function ($k, $v) use ($c2) { return $v['kid'] === $c2['id']; });
            kunde_sign_in($c2);
            audit('kunde_password', 'Kunde hat Passwort über den Link aus der E-Mail festgelegt', [], ['username' => 'kunde:' . $c2['login']['username'], 'name' => $c2['firma'], 'role' => 'kunde']);
            respond(['ok' => true, 'csrf' => $_SESSION['kcsrf'], 'kunde' => kunde_payload($c2)]);
        }

        /* ---------- Bestellwunsch aus dem Portal ---------- */
        case 'kunde_bestellung': {
            $c = current_customer();
            if (!$c) fail('Bitte erneut anmelden.', 401);
            require_customer_csrf();
            if (!empty($c['login']['mustChange'])) fail('Bitte zuerst ein eigenes Passwort festlegen.', 403);
            if (!order_enabled()) fail('Bestellungen über das Portal sind derzeit nicht möglich. Bitte wenden Sie sich direkt an uns.', 409);
            $b = body();
            $key = (string)($b['requestId'] ?? '');
            if ($key !== '' && !preg_match('/^[A-Za-z0-9_-]{16,80}$/D', $key)) fail('Ungültige Übermittlungskennung.', 422);
            $hash = order_request_hash($b);
            with_lock('bestellungen', function () use ($c, $key, $hash) { order_replay(store_read('bestellungen') ?? [], $c['id'], $key, $hash); });
            $oid = (string)($b['angebot'] ?? OFFER_STD);
            if ($oid === '') $oid = OFFER_STD;
            $def = offer_def($oid);
            if (!$def || !(in_array($oid, customer_offers($c), true) || ($oid === OFFER_STD && std_public()))) fail('Für dieses Angebot ist Ihr Zugang nicht freigeschaltet.', 403);
            $pub = store_read('angebot');
            if (!$pub) fail('Es ist kein Angebot veröffentlicht.', 409);
            if ((string)($b['publishedAt'] ?? '') !== (string)($pub['publishedAt'] ?? $pub['savedAt'] ?? '')) fail('Das Angebot wurde inzwischen aktualisiert. Bitte prüfen Sie Ihren Bestellwunsch mit den aktuellen Preisen und senden Sie ihn erneut.', 409);
            $off = offer_resolve($pub, $def);
            $byId = []; foreach ($off['items'] as $it) $byId[$it['id']] = $it;
            $gName = []; foreach ($off['groups'] ?? [] as $g) $gName[$g['id']] = $g['name'];
            $in = is_array($b['positions'] ?? null) ? $b['positions'] : [];
            if (!$in) fail('Bitte mindestens eine Menge eingeben.', 422);
            if (count($in) > 300) fail('Zu viele Positionen in einem Bestellwunsch (höchstens 300).', 422);
            $pos = []; $seen = []; $total = 0.0; $qtyT = 0.0; $req = 0;
            foreach ($in as $p) {
                $id = is_array($p) ? (string)($p['id'] ?? '') : '';
                $q = is_array($p) && is_numeric($p['qty'] ?? null) ? round((float)$p['qty'], 2) : 0.0;
                if ($id === '' || isset($seen[$id])) continue;
                if (!isset($byId[$id])) fail('Ein Artikel Ihres Bestellwunsches ist im aktuellen Angebot nicht mehr enthalten. Bitte Seite neu laden und prüfen.', 409);
                if ($q <= 0 || $q > 99999) fail('Bitte nur Mengen zwischen 0,01 und 99.999 kg eingeben.', 422);
                $seen[$id] = true;
                $it = $byId[$id];
                $price = ($it['price']['status'] ?? '') === 'value' ? (float)$it['price']['value'] : null;
                $sum = $price !== null ? round(round($price * 100) * $q) / 100 : null;   // in Cent rechnen (wie die Anzeige im Portal)
                if ($sum !== null) $total += $sum; else $req++;
                $qtyT += $q;
                $pos[] = ['id' => $id, 'code' => (string)($it['code'] ?? ''), 'name' => (string)$it['name'] . (!empty($it['sale']) ? ' (Sonderposten)' : ''), 'group' => $gName[$it['groupId'] ?? ''] ?? '', 'qty' => $q, 'price' => $price, 'sum' => $sum];
            }
            if (!$pos) fail('Bitte mindestens eine Menge eingeben.', 422);
            $termin = (string)($b['termin'] ?? '');
            if ($termin !== '') {
                $d = DateTimeImmutable::createFromFormat('!Y-m-d', $termin);
                if (!$d || $d->format('Y-m-d') !== $termin || $termin < date('Y-m-d') || $termin > date('Y-m-d', strtotime('+120 days'))) fail('Bitte ein gültiges Wunschdatum (heute bis in 4 Monaten) wählen.', 422);
            }
            $ref = s($b['referenz'] ?? '', 60) ?? '';
            $bem = mb_substr(trim(str_replace("\r", '', preg_replace('/[\x00-\x08\x0b-\x1f]/u', '', (string)($b['bemerkung'] ?? '')) ?? '')), 0, 1000);
            // Missbrauchsschutz: höchstens 30 Bestellwünsche je Kunde und Tag
            $recent = array_filter(store_read('bestellungen') ?? [], function ($x) use ($c) { return ($x['kid'] ?? '') === $c['id'] && strtotime($x['t']) > time() - 86400; });
            if (count($recent) >= 30) fail('Heute wurden bereits sehr viele Bestellwünsche gesendet. Bitte wenden Sie sich direkt an uns.', 429);
            $o = with_lock('bestellungen', function () use ($c, $def, $off, $pos, $total, $qtyT, $req, $termin, $ref, $bem, $key, $hash) {
                $all = store_read('bestellungen') ?? [];
                order_replay($all, $c['id'], $key, $hash);
                if (count(array_filter($all, fn($x) => ($x['kid'] ?? '') === $c['id'] && strtotime($x['t']) > time() - 86400)) >= 30) fail('Heute wurden bereits sehr viele Bestellwünsche gesendet.', 429);
                $y = date('Y'); $n = 0;
                foreach ($all as $x) if (strpos($x['nr'], "B-$y-") === 0) $n = max($n, (int)substr($x['nr'], 7));
                $o = ['nr' => sprintf('B-%s-%04d', $y, $n + 1), 't' => now(), 'kid' => $c['id'], 'firma' => $c['firma'], 'angebot' => $def['id'], 'angebotName' => $def['name'],
                      'week' => (int)($off['meta']['week'] ?? 0), 'year' => (int)($off['meta']['year'] ?? 0), 'positions' => $pos, 'total' => round($total, 2), 'totalQty' => round($qtyT, 2),
                      'onRequest' => $req, 'termin' => $termin, 'referenz' => $ref, 'bemerkung' => $bem, 'status' => 'neu', 'workflow' => 'neu', 'revision' => 1, 'requestId' => $key, 'requestHash' => $hash];
                $o['kunde'] = array_intersect_key($c, array_flip(['firma','nr','ansprechpartner','strasse','plz','ort','email','telefon']));
                $o['kunde']['username'] = $c['login']['username'];
                $o['outbox'] = order_outbox_create($o);
                $all[] = $o;
                store_write('bestellungen', $all);
                return $o;
            });
            try { $o = order_outbox_send($o['nr']); } catch (RuntimeException $e) { $o['status'] = 'fehler'; }   // Bestellung ist gespeichert; Versand bleibt als offener Auftrag sichtbar
            $okIn = ($o['status'] ?? '') === 'gesendet';
            $who = ['username' => 'kunde:' . $c['login']['username'], 'name' => $c['firma'], 'role' => 'kunde'];
            audit('bestellung', "Bestellwunsch {$o['nr']} ({$def['name']}, " . count($pos) . ' Positionen, ' . de_qty($o['totalQty']) . ' kg)' . ($okIn ? '' : ' – E-Mail nicht zugestellt'),
                array_map(function ($p) { return ['k' => 'b|' . $p['id'], 'code' => $p['code'], 'name' => $p['name'], 'f' => 'Menge', 'from' => '', 'to' => de_qty($p['qty']) . ' kg' . ($p['price'] !== null ? ' × ' . de_num($p['price']) . ' €' : ' (Preis auf Anfrage)')]; }, $pos), $who);
            if (!$okIn) fail('Ihr Bestellwunsch wurde gespeichert, die E-Mail konnte aber nicht bestätigt werden. Bitte nicht als neuen Bestellwunsch erneut eingeben. Unser Team kann den Versand prüfen.', 502);
            order_receipt($o);
        }

        case 'bestell_settings_save': {
            $me = require_admin_confirmation();
            $b = body();
            $raw = is_array($b['to'] ?? null) ? implode(',', $b['to']) : (string)($b['to'] ?? '');
            $to = [];
            foreach (preg_split('/[\s,;]+/', $raw) as $a) {
                if ($a === '') continue;
                if (filter_var($a, FILTER_VALIDATE_EMAIL) === false) fail("„" . mb_substr($a, 0, 80) . "“ ist keine gültige E-Mail-Adresse.", 422);
                $to[strtolower($a)] = $a;
            }
            $to = array_values($to);
            if (count($to) > 5) fail('Höchstens 5 Empfänger für Bestellwünsche.', 422);
            $en = !empty($b['enabled']);
            if ($en && !$to) fail('Bitte mindestens eine Adresse angeben, an die Bestellwünsche gehen.', 422);
            $old = order_settings();
            $new = ['enabled' => $en, 'to' => $to, 'copy' => !empty($b['copy']), 'updatedAt' => now(), 'updatedBy' => $me['name']];
            store_write('bestellung', $new);
            $ch = [];
            if ($old['enabled'] !== $en) $ch[] = ['k' => 'best|en', 'code' => '', 'name' => 'Bestellungen', 'f' => 'Bestellfunktion', 'from' => $old['enabled'] ? 'an' : 'aus', 'to' => $en ? 'an' : 'aus'];
            if (implode(', ', $old['to']) !== implode(', ', $to)) $ch[] = ['k' => 'best|to', 'code' => '', 'name' => 'Bestellungen', 'f' => 'Empfänger', 'from' => implode(', ', $old['to']), 'to' => implode(', ', $to)];
            if ($old['copy'] !== $new['copy']) $ch[] = ['k' => 'best|copy', 'code' => '', 'name' => 'Bestellungen', 'f' => 'Kopie an Kunden', 'from' => $old['copy'] ? 'ja' : 'nein', 'to' => $new['copy'] ? 'ja' : 'nein'];
            if ($ch) audit('mail', 'Einstellungen für Bestellwünsche geändert', $ch);
            respond(['ok' => true, 'orders' => order_settings(), 'active' => order_enabled()]);
        }

        /* ---------- Merkliste je Kunde (geräteübergreifend) ---------- */
        case 'kunde_merkliste': {
            header('Cache-Control: private, no-store');
            $c = current_customer();
            if (!$c) fail('Bitte anmelden.', 401);
            $m = (store_read('merklisten') ?? [])[$c['id']] ?? null;
            respond(['ok' => true, 'keys' => $m['keys'] ?? [], 'savedAt' => $m['t'] ?? null, 'exists' => $m !== null]);
        }

        case 'kunde_merkliste_save': {
            $c = current_customer();
            if (!$c) fail('Bitte erneut anmelden.', 401);
            require_customer_csrf();
            $in = body()['keys'] ?? null;
            if (!is_array($in)) fail('Ungültige Merkliste.', 422);
            $keys = [];
            foreach ($in as $k) {
                if (!is_string($k) || $k === '' || mb_strlen($k) > 200 || preg_match('/[\x00-\x1f]/', $k)) continue;
                $keys[$k] = true;
                if (count($keys) >= 1000) break;
            }
            $keys = array_keys($keys);
            with_lock('merklisten', function () use ($c, $keys) {
                $all = store_read('merklisten') ?? [];
                $all[$c['id']] = ['keys' => $keys, 't' => now()];
                store_write('merklisten', $all);
            });
            respond(['ok' => true, 'count' => count($keys)]);
        }

        /* ---------- Abmelden vom Wochenangebot (Link aus der E-Mail, ohne Anmeldung) ---------- */
        case 'kunde_abmelden_info': {
            attempts_check();
            $c = abmelde_kunde((string)(body()['token'] ?? ''));
            if (!$c) { attempts_record(false); fail('Dieser Abmeldelink ist ungültig. Bitte wenden Sie sich direkt an uns.', 404); }
            $e = (string)($c['email'] ?? '');
            $masked = $e !== '' ? preg_replace('/^(.).*?(@.*)$/u', '$1•••$2', $e) : '';
            respond(['ok' => true, 'firma' => $c['firma'], 'email' => $masked, 'subscribed' => !array_key_exists('mailAngebot', $c) || !empty($c['mailAngebot']), 'company' => $CFG['company']]);
        }

        case 'kunde_abmelden': {
            attempts_check();
            $b = body();
            $c = abmelde_kunde((string)($b['token'] ?? ''));
            if (!$c) { attempts_record(false); fail('Dieser Abmeldelink ist ungültig. Bitte wenden Sie sich direkt an uns.', 404); }
            $ab = empty($b['wieder']);
            if (abmelde_setzen($c, $ab, 'link')) abmelde_melden($c, $ab, 'link');
            respond(['ok' => true, 'subscribed' => !$ab]);
        }

        case 'abmelden1': {
            // Ein-Klick-Abmeldung (RFC 8058): das E-Mail-Programm sendet POST mit „List-Unsubscribe=One-Click“
            if ($method !== 'POST') fail('Bitte den Abmeldelink in der E-Mail verwenden.', 405);
            attempts_check();
            $c = abmelde_kunde((string)($_GET['t'] ?? ''));
            if (!$c) { attempts_record(false); fail('Ungültiger Abmeldelink.', 404); }
            if (abmelde_setzen($c, true, '1klick')) abmelde_melden($c, true, '1klick');
            respond(['ok' => true]);
        }

        /* ---------- E-Mail-Versand (nur Administrator) ---------- */
        case 'mail_status': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $m = mail_cfg();
            $last = array_slice(store_read('mailversand') ?? [], -200);
            respond(['ok' => true, 'configured' => (bool)$m && (bool)mail_base_url(), 'baseUrl' => mail_base_url(),
                     'smtp' => $m ? ['host' => $m['host'], 'port' => $m['port'], 'secure' => $m['secure'], 'user' => $m['user'], 'from' => $m['from'], 'fromName' => $m['fromName'], 'replyTo' => $m['replyTo'], 'password' => $m['pass'] !== '', 'passError' => $m['passError'], 'source' => $m['source']] : null,
                     'account' => ($a = mail_account()) ? ['host' => $a['host'], 'port' => (int)$a['port'], 'secure' => $a['secure'], 'user' => $a['user'] ?? '', 'from' => $a['from'], 'fromName' => $a['fromName'] ?? '', 'replyTo' => $a['replyTo'] ?? '', 'password' => !empty($a['passEnc']), 'updatedAt' => $a['updatedAt'] ?? null, 'updatedBy' => $a['updatedBy'] ?? ''] : null,
                     'envConfigured' => env_str('MAIL_SMTP_HOST') !== '' && env_str('MAIL_FROM') !== '', 'orders' => order_settings(), 'sodium' => function_exists('sodium_crypto_secretbox'),
                     'signature' => mail_settings()['signature'], 'week' => mail_week(), 'log' => array_reverse($last)]);
        }

        case 'mail_konto_save': {
            $me = require_admin_confirmation();
            $b = body();
            $old = mail_account();
            if (!empty($b['remove'])) {
                if ($old) { store_write('mailkonto', ['removed' => now()]); audit('mail', 'Postfach-Einstellungen entfernt', [['k' => 'mail|konto', 'code' => '', 'name' => 'E-Mail', 'f' => 'Postfach', 'from' => $old['user'] . ' @ ' . $old['host'], 'to' => 'entfernt']]); }
                respond(['ok' => true]);
            }
            $host = strtolower(trim((string)($b['host'] ?? '')));
            if (!preg_match('/^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$/', $host)) fail('Bitte einen gültigen Mailserver angeben (z. B. smtp.hostinger.com).', 422);
            $secure = in_array($b['secure'] ?? '', ['ssl', 'starttls', 'none'], true) ? $b['secure'] : 'ssl';
            if ($secure === 'none' && !in_array($host, ['127.0.0.1', 'localhost'], true)) fail('Unverschlüsselter Versand ist nur an einen Server auf demselben Rechner erlaubt. Bitte SSL oder STARTTLS wählen.', 422);
            $port = (int)($b['port'] ?? 0);
            if ($port < 1 || $port > 65535) fail('Bitte einen gültigen Port angeben (meist 465 für SSL oder 587 für STARTTLS).', 422);
            $user = mail_clean_header(mb_substr((string)($b['user'] ?? ''), 0, 160));
            $from = trim((string)($b['from'] ?? ''));
            if (filter_var($from, FILTER_VALIDATE_EMAIL) === false) fail('Bitte eine gültige Absenderadresse angeben.', 422);
            $reply = trim((string)($b['replyTo'] ?? ''));
            if ($reply !== '' && filter_var($reply, FILTER_VALIDATE_EMAIL) === false) fail('Die Antwortadresse ist ungültig.', 422);
            $name = mb_substr(mail_clean_header((string)($b['fromName'] ?? '')), 0, 80);
            $pw = (string)($b['password'] ?? '');
            if (strlen($pw) > 500) fail('Das Passwort ist zu lang.', 422);
            $same = $old && $old['host'] === $host && (int)$old['port'] === $port && ($old['user'] ?? '') === $user && $old['secure'] === $secure;
            if ($pw === '') {
                // Das gespeicherte Passwort wird nur an denselben Server/Benutzer weiterverwendet – nie an einen geänderten Server
                if (!$same && $user !== '') fail('Bei neuem oder geändertem Server, Port, Verschlüsselung oder Benutzer bitte das Passwort des Postfachs (erneut) eingeben.', 422);
                $enc = $same ? (string)($old['passEnc'] ?? '') : '';
            } else {
                try { $enc = mail_encrypt($pw); } catch (RuntimeException $e) { fail($e->getMessage(), 500); }
            }
            $new = ['host' => $host, 'port' => $port, 'secure' => $secure, 'user' => $user, 'passEnc' => $enc, 'from' => $from, 'fromName' => $name, 'replyTo' => $reply, 'updatedAt' => now(), 'updatedBy' => $me['name']];
            store_write('mailkonto', $new);
            $ch = [];
            foreach (['host' => 'Mailserver', 'port' => 'Port', 'secure' => 'Verschlüsselung', 'user' => 'Benutzer', 'from' => 'Absenderadresse', 'fromName' => 'Absendername', 'replyTo' => 'Antwortadresse'] as $f => $lab) {
                $from0 = $old ? (string)($old[$f] ?? '') : ''; $to0 = (string)$new[$f];
                if ($from0 !== $to0) $ch[] = ['k' => "mail|$f", 'code' => '', 'name' => 'E-Mail', 'f' => $lab, 'from' => $from0, 'to' => $to0];
            }
            if ($pw !== '') $ch[] = ['k' => 'mail|pw', 'code' => '', 'name' => 'E-Mail', 'f' => 'Passwort', 'from' => '', 'to' => 'neu gesetzt'];
            if ($ch) audit('mail', $old ? 'Postfach-Einstellungen geändert' : 'Postfach für den E-Mail-Versand eingerichtet', $ch);
            // Verbindung und Anmeldung gleich prüfen (ohne E-Mail zu senden)
            $conn = ['ok' => true];
            try { $t = new Smtp(mail_cfg()); $t->open(); $t->close(); } catch (RuntimeException $e) { $conn = ['ok' => false, 'error' => $e->getMessage()]; }
            respond(['ok' => true, 'connection' => $conn]);
        }

        case 'mail_save': {
            require_admin_confirmation();
            $sig = (string)(body()['signature'] ?? '');
            $sig = mb_substr(trim(str_replace("\r", '', preg_replace('/[\x00-\x08\x0b-\x1f]/u', '', $sig) ?? '')), 0, 600);
            $old = mail_settings()['signature'];
            store_write('mailvorlage', ['signature' => $sig, 'updatedAt' => now()]);
            if ($old !== $sig) audit('mail', 'E-Mail-Signatur geändert', [['k' => 'mail|sig', 'code' => '', 'name' => 'E-Mail', 'f' => 'Signatur', 'from' => $old, 'to' => $sig]]);
            respond(['ok' => true, 'signature' => $sig]);
        }

        case 'mail_test': {
            $me = require_admin_confirmation();
            $cfg = require_mail();
            $to = trim((string)(body()['to'] ?? ''));
            if (filter_var($to, FILTER_VALIDATE_EMAIL) === false) fail('Bitte eine gültige E-Mail-Adresse angeben.', 422);
            $sub = 'Testnachricht aus dem Angebotsportal';
            $txt = "Diese Testnachricht bestätigt, dass der E-Mail-Versand des Angebotsportals funktioniert.

Ausgelöst von: {$me['name']}
";
            $html = mail_layout($sub, '<p style="margin:0 0 14px;">Diese Testnachricht bestätigt, dass der E-Mail-Versand des Angebotsportals funktioniert.</p><p style="margin:0;color:#857c72;font-size:13px;">Ausgelöst von: ' . mail_h($me['name']) . '</p>', mail_settings()['signature'], '');
            $r = mail_send_many($cfg, [['to' => $to, 'name' => '', 'subject' => $sub, 'text' => $txt, 'html' => $html]])[0];
            with_lock('mailversand', function () use ($to, $r, $me) {
                $l = store_read('mailversand') ?? [];
                $l[] = ['t' => now(), 'typ' => 'test', 'kid' => '', 'firma' => '', 'to' => $to, 'ok' => $r['ok'], 'error' => $r['error'] ?? '', 'by' => $me['name']];
                store_write('mailversand', array_slice($l, -3000));
            });
            if (!$r['ok']) fail('Testmail nicht versendet: ' . $r['error'], 502);
            respond(['ok' => true]);
        }

        case 'kunden_mail_vorschau': {
            require_auth(true, 'admin');
            $b = body();
            $typ = in_array($b['type'] ?? '', ['woche', 'angebot', 'invite', 'reset', 'restposten'], true) ? $b['type'] : 'woche';
            $c = null;
            foreach (customers_load()['customers'] as $x) if ($x['id'] === ($b['id'] ?? '')) $c = $x;
            if (!$c) $c = ['firma' => 'Musterkunde GmbH', 'ansprechpartner' => 'Frau Muster', 'email' => 'kunde@example.org', 'angebote' => [OFFER_STD], 'login' => ['username' => 'musterkunde']];
            if (!mail_base_url()) fail('Die Adresse der Angebotsseite für Links fehlt (DOMAIN bzw. WA_URL in .env).', 409);
            if ($typ === 'restposten') {
                $def = offer_def((string)($b['offer'] ?? ''));
                if (!$def) fail('Angebot nicht gefunden.', 404);
                [$sub, , $html] = mail_tpl_restposten($c, $def, restposten_items($def), mb_substr(trim((string)($b['note'] ?? '')), 0, 1000));
            } elseif ($typ === 'invite' || $typ === 'reset') [$sub, , $html] = mail_tpl_zugang($c, mail_base_url() . '/#zugang=BEISPIEL', $typ, time() + 86400 * TOKEN_DAYS[$typ]);
            else [$sub, , $html] = mail_tpl_angebot($c, mb_substr(trim((string)($b['note'] ?? '')), 0, 1000), mail_week());
            respond(['ok' => true, 'subject' => $sub, 'html' => $html, 'to' => $c['email'] ?? '']);
        }

        case 'kunde_mail': {
            require_admin_confirmation();
            $cfg = require_mail();
            $b = body();
            $c = null;
            foreach (customers_load()['customers'] as $x) if ($x['id'] === ($b['id'] ?? '')) $c = $x;
            if (!$c) fail('Kunde nicht gefunden.', 404);
            if (empty($c['email'])) fail("Für „{$c['firma']}“ ist keine E-Mail-Adresse hinterlegt.", 422);
            if (empty($c['active'])) fail('Der Kunde ist inaktiv.', 422);
            $type = $b['type'] ?? '';
            if ($type === 'zugang') {
                if (empty($c['login'])) fail('Für diesen Kunden ist kein Zugang eingerichtet.', 422);
                if (empty($c['login']['active'])) fail('Der Zugang ist deaktiviert.', 422);
                $purpose = empty($c['login']['hash']) ? 'invite' : 'reset';
                [$tok, $exp, $c] = kunde_token_new($c['id'], $purpose);
                [$sub, $txt, $html] = mail_tpl_zugang($c, mail_base_url() . '/#zugang=' . $tok, $purpose, $exp);
                $job = ['to' => $c['email'], 'name' => $c['ansprechpartner'] ?: $c['firma'], 'subject' => $sub, 'text' => $txt, 'html' => $html];
                $typ = $purpose;
            } elseif ($type === 'angebot') {
                if (!customer_offers($c)) fail('Für diesen Kunden ist kein Angebot freigeschaltet.', 422);
                if (array_key_exists('mailAngebot', $c) && empty($c['mailAngebot'])) fail(!empty($c['abgemeldet']) ? "„{$c['firma']}“ hat sich vom Wochenangebot per E-Mail abgemeldet – es werden keine Angebotsmails mehr gesendet." : "Für „{$c['firma']}“ ist das Wochenangebot per E-Mail ausgeschaltet.", 422);
                $job = mail_job_for($c, 'angebot', mb_substr(trim((string)($b['note'] ?? '')), 0, 1000), mail_week());
                $typ = 'angebot';
            } else fail('Unbekannte E-Mail-Art.', 422);
            $r = mail_send_many($cfg, [$job])[0];
            if (!$r['ok'] && isset($tok)) with_lock('kunden', function () use ($c) {   // Link nicht zugestellt → ungültig machen
                $d = customers_load();
                foreach ($d['customers'] as $i => $x) if ($x['id'] === $c['id']) unset($d['customers'][$i]['login']['token']);
                store_write('kunden', $d);
            });
            mail_record([['kid' => $c['id'], 'firma' => $c['firma'], 'to' => $c['email'], 'typ' => $typ, 'ok' => $r['ok'], 'error' => $r['error'] ?? '']]);
            audit('mail', MAIL_TYP[$typ] . " an „{$c['firma']}“ " . ($r['ok'] ? 'gesendet' : 'nicht zugestellt'), [['k' => "c{$c['id']}|mail", 'code' => $c['nr'] ?? '', 'name' => $c['firma'], 'f' => MAIL_TYP[$typ], 'from' => '', 'to' => $c['email'] . ($r['ok'] ? '' : ' – Fehler: ' . $r['error'])]]);
            if (!$r['ok']) fail('E-Mail nicht versendet: ' . $r['error'], 502);
            respond(['ok' => true, 'typ' => $typ, 'customer' => customer_public(array_values(array_filter(customers_load()['customers'], function ($x) use ($c) { return $x['id'] === $c['id']; }))[0])]);
        }

        case 'kunden_rundmail': {
            require_admin_confirmation();
            $cfg = require_mail();
            $b = body();
            $wk = mail_week();
            if (!$wk) fail('Es ist noch kein Angebot veröffentlicht.', 409);
            if ((int)($b['week'] ?? 0) !== $wk['week'] || (int)($b['year'] ?? 0) !== $wk['year']) fail('Inzwischen wurde ein anderes Angebot veröffentlicht. Bitte den Versand neu öffnen.', 409);
            $ids = array_slice(array_values(array_filter(is_array($b['ids'] ?? null) ? $b['ids'] : [], 'is_string')), 0, 20);
            $note = mb_substr(trim((string)($b['note'] ?? '')), 0, 1000);
            $jobs = []; $res = []; $map = [];
            foreach (customers_load()['customers'] as $c) {
                if (!in_array($c['id'], $ids, true)) continue;
                $map[$c['id']] = $c;
                $why = empty($c['active']) ? 'Kunde inaktiv' : (empty($c['email']) ? 'keine E-Mail-Adresse' : (empty($c['login']['active']) ? 'kein aktiver Zugang' : (!customer_offers($c) ? 'kein Angebot freigeschaltet' : (array_key_exists('mailAngebot', $c) && empty($c['mailAngebot']) ? (!empty($c['abgemeldet']) ? 'hat sich vom Wochenangebot abgemeldet' : 'Wochenangebot per E-Mail nicht gewünscht') : ''))));
                if ($why !== '') { $res[$c['id']] = ['ok' => false, 'error' => $why, 'skipped' => true]; continue; }
                $jobs[$c['id']] = mail_job_for($c, 'woche', $note, $wk);
            }
            @set_time_limit(180);
            ignore_user_abort(true);
            $res = $res + ($jobs ? mail_send_many($cfg, $jobs) : []);
            $entries = [];
            foreach ($res as $id => $r) if (empty($r['skipped'])) $entries[] = ['kid' => $id, 'firma' => $map[$id]['firma'], 'to' => $map[$id]['email'], 'typ' => 'woche', 'ok' => $r['ok'], 'error' => $r['error'] ?? ''];
            if ($entries) mail_record($entries, $wk);
            $okN = count(array_filter($res, function ($r) { return $r['ok']; }));
            $bad = array_filter($res, function ($r) { return !$r['ok']; });
            if ($res) audit('mail', "Wochenangebot KW {$wk['week']}/{$wk['year']} an $okN Kunden versendet" . ($bad ? ' (' . count($bad) . ' nicht zugestellt)' : ''),
                array_map(function ($id) use ($res, $map) { $r = $res[$id]; return ['k' => "c$id|woche", 'code' => $map[$id]['nr'] ?? '', 'name' => $map[$id]['firma'], 'f' => 'Wochenangebot', 'from' => '', 'to' => ($map[$id]['email'] ?? '') . ($r['ok'] ? '' : ' – ' . $r['error'])]; }, array_keys($res)));
            $out = [];
            foreach ($ids as $id) $out[] = ['id' => $id] + ($res[$id] ?? ['ok' => false, 'error' => 'Kunde nicht gefunden']);
            respond(['ok' => true, 'results' => $out]);
        }

        /* ---------- Sonderposten eines Angebots per E-Mail (nur an die Kunden dieses Angebots) ---------- */
        case 'restposten_info': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $def = offer_def((string)($_GET['offer'] ?? ''));
            if (!$def) fail('Angebot nicht gefunden.', 404);
            $pub = store_read('angebot');
            $items = array_map(function ($it) { return ['id' => $it['id'], 'code' => $it['code'] ?? '', 'name' => $it['name'], 'price' => (float)$it['price']['value'], 'regular' => $it['regular'] ?? null]; }, restposten_items($def));
            $rec = [];
            foreach (customers_load()['customers'] as $c) {
                if (!in_array($def['id'], customer_offers($c), true)) continue;
                $rec[] = ['id' => $c['id'], 'firma' => $c['firma'], 'nr' => $c['nr'] ?? '', 'email' => $c['email'] ?? '', 'reason' => restposten_reason($c, $def['id'])];
            }
            usort($rec, function ($a, $b) { return strcasecmp($a['firma'], $b['firma']); });
            respond(['ok' => true, 'offer' => ['id' => $def['id'], 'name' => $def['name']], 'publishedAt' => $pub['publishedAt'] ?? null, 'items' => $items, 'recipients' => $rec, 'mailReady' => (bool)mail_cfg() && (bool)mail_base_url()]);
        }

        case 'kunden_restposten': {
            require_admin_confirmation();
            $cfg = require_mail();
            $b = body();
            $def = offer_def((string)($b['offer'] ?? ''));
            if (!$def) fail('Angebot nicht gefunden.', 404);
            $pub = store_read('angebot');
            if (!$pub || (string)($b['publishedAt'] ?? '') !== (string)($pub['publishedAt'] ?? '')) fail('Inzwischen wurde neu veröffentlicht. Bitte den Versand neu öffnen und die Sonderposten prüfen.', 409);
            $items = restposten_items($def);
            if (!$items) fail('In diesem Angebot sind keine Sonderposten veröffentlicht (oder alle ohne Bestand).', 409);
            $ids = array_slice(array_values(array_filter(is_array($b['ids'] ?? null) ? $b['ids'] : [], 'is_string')), 0, 200);
            $note = mb_substr(trim((string)($b['note'] ?? '')), 0, 1000);
            $jobs = []; $res = []; $map = [];
            foreach (customers_load()['customers'] as $c) {
                if (!in_array($c['id'], $ids, true)) continue;
                $map[$c['id']] = $c;
                $why = restposten_reason($c, $def['id']);
                if ($why !== '') { $res[$c['id']] = ['ok' => false, 'error' => $why, 'skipped' => true]; continue; }
                [$sub, $txt, $html] = mail_tpl_restposten($c, $def, $items, $note);
                $one = mail_base_url() . '/api/?action=abmelden1&t=' . rawurlencode(abmelde_token($c['id']));
                $jobs[$c['id']] = ['to' => $c['email'], 'name' => ($c['ansprechpartner'] ?? '') ?: $c['firma'], 'subject' => $sub, 'text' => $txt, 'html' => $html,
                                   'headers' => ['List-Unsubscribe' => '<' . $one . '>', 'List-Unsubscribe-Post' => 'List-Unsubscribe=One-Click']];
            }
            @set_time_limit(300);
            ignore_user_abort(true);
            $res = $res + ($jobs ? mail_send_many($cfg, $jobs) : []);
            $entries = [];
            foreach ($res as $id => $r) if (empty($r['skipped'])) $entries[] = ['kid' => $id, 'firma' => $map[$id]['firma'], 'to' => $map[$id]['email'], 'typ' => 'restposten', 'ok' => $r['ok'], 'error' => $r['error'] ?? ''];
            if ($entries) mail_record($entries);
            $okN = count(array_filter($res, function ($r) { return $r['ok']; }));
            $bad = array_filter($res, function ($r) { return !$r['ok'] && empty($r['skipped']); });
            if ($res) audit('mail', "Sonderposten {$def['name']} (" . count($items) . " Artikel) an $okN Kunden versendet" . ($bad ? ' (' . count($bad) . ' nicht zugestellt)' : ''),
                array_map(function ($id) use ($res, $map) { $r = $res[$id]; return ['k' => "c$id|restposten", 'code' => $map[$id]['nr'] ?? '', 'name' => $map[$id]['firma'], 'f' => 'Sonderposten', 'from' => '', 'to' => ($map[$id]['email'] ?? '') . ($r['ok'] ? '' : ' – ' . $r['error'])]; }, array_keys($res)));
            $out = [];
            foreach ($ids as $id) $out[] = ['id' => $id] + ($res[$id] ?? ['ok' => false, 'error' => 'Kunde nicht gefunden']);
            respond(['ok' => true, 'results' => $out]);
        }

        /* ---------- Kundenstammdaten (Eingabebereich, nur Administrator) ---------- */
        case 'kunden': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $d = customers_load();
            $act = [];
            foreach (ksess_prune(store_read('kundensitzungen') ?? []) as $v) $act[$v['kid']] = ($act[$v['kid']] ?? 0) + 1;
            $list = array_map(function ($c) use ($act) { $p = customer_public($c); $p['sessions'] = $act[$c['id']] ?? 0; return $p; }, $d['customers']);
            respond(['ok' => true, 'rev' => $d['rev'], 'customers' => $list]);
        }

        case 'kunde_save': {
            $me = require_admin_confirmation();
            $b = body();
            $res = with_lock('kunden', function () use ($b) {
                $d = customers_load();
                if ((int)($b['rev'] ?? -1) !== (int)$d['rev']) fail('Die Kundendaten wurden inzwischen an anderer Stelle geändert. Bitte neu laden.', 409);
                $id = is_string($b['id'] ?? null) ? $b['id'] : '';
                $idx = null;
                foreach ($d['customers'] as $i => $c) if ($c['id'] === $id) $idx = $i;
                if ($id !== '' && $idx === null) fail('Kunde nicht gefunden.', 404);
                $old = $idx !== null ? $d['customers'][$idx] : null;
                $row = ['id' => $old['id'] ?? ('k' . bin2hex(random_bytes(6)))];
                foreach (CUSTOMER_FIELDS as $f => $max) {
                    $v = s($b[$f] ?? '', $max) ?? '';
                    $row[$f] = $v;
                }
                if (mb_strlen($row['firma']) < 2) throw new InvalidArgumentException('Bitte den Namen der Firma angeben.');
                if ($row['email'] !== '' && filter_var($row['email'], FILTER_VALIDATE_EMAIL) === false) throw new InvalidArgumentException('Die E-Mail-Adresse ist ungültig.');
                foreach ($d['customers'] as $c) if ($c['id'] !== $row['id'] && $row['nr'] !== '' && ($c['nr'] ?? '') === $row['nr']) throw new InvalidArgumentException("Die Kundennummer {$row['nr']} ist bereits vergeben.");
                $known = array_merge([OFFER_STD], offer_ids());
                $row['angebote'] = array_values(array_unique(array_filter(is_array($b['angebote'] ?? null) ? $b['angebote'] : [], function ($o) use ($known) { return is_string($o) && in_array($o, $known, true); })));
                $row['active'] = !empty($b['active']);
                $row['mailAngebot'] = !array_key_exists('mailAngebot', $b) || !empty($b['mailAngebot']);
                foreach (['weekly', 'mailLast', 'abgemeldet'] as $keep) if (isset($old[$keep])) $row[$keep] = $old[$keep];
                if ($row['mailAngebot']) unset($row['abgemeldet']);
                $row['created'] = $old['created'] ?? now();
                $row['changed'] = now();
                // Zugang
                $lg = is_array($b['login'] ?? null) ? $b['login'] : null;
                $ol = $old['login'] ?? null;
                $pwNew = false; $ended = false;
                if (!$lg || !empty($lg['remove'])) {
                    $row['login'] = null;
                    $ended = (bool)$ol;
                } else {
                    $uname = clean_username($lg['username'] ?? '');
                    foreach ($d['customers'] as $c) if ($c['id'] !== $row['id'] && (($c['login']['username'] ?? '') === $uname)) throw new InvalidArgumentException("Der Benutzername „{$uname}“ ist bereits vergeben.");
                    $l = $ol ?: ['sv' => 1, 'created' => now(), 'lastLogin' => null, 'failCount' => 0, 'lockedUntil' => 0];
                    $l['username'] = $uname;
                    $l['active'] = !empty($lg['active']);
                    $pw = (string)($lg['password'] ?? '');
                    if ($pw !== '') {
                        $l['hash'] = password_hash(check_password($pw, $uname), PASSWORD_DEFAULT);
                        $l['mustChange'] = !empty($lg['mustChange']);
                        $l['pwSet'] = now();
                        $l['sv'] = (int)($l['sv'] ?? 0) + 1;
                        unset($l['token']);
                        $pwNew = true;
                    } elseif (empty($l['hash']) && empty($lg['invite'])) {
                        throw new InvalidArgumentException('Bitte ein Startpasswort festlegen oder eine Einladung per E-Mail senden.');
                    } elseif (empty($l['hash'])) {
                        $l['hash'] = null;
                        $l['mustChange'] = false;
                        if (($row['email'] ?? '') === '') throw new InvalidArgumentException('Für eine Einladung per E-Mail bitte die E-Mail-Adresse angeben.');
                    }
                    if (!empty($lg['unlock'])) { $l['lockedUntil'] = 0; $l['failCount'] = 0; }
                    if ($ol && $ol['username'] !== $uname) { $l['sv'] = (int)($l['sv'] ?? 0) + 1; $ended = true; unset($l['token']); }
                    if ($ol && !empty($ol['active']) && !$l['active']) $ended = true;
                    $row['login'] = $l;
                }
                if (!$row['active']) $ended = $ended || ($old && !empty($old['active']));
                if ($idx === null) $d['customers'][] = $row; else $d['customers'][$idx] = $row;
                usort($d['customers'], function ($x, $y) { return strcasecmp($x['firma'], $y['firma']); });
                $d['rev'] = (int)$d['rev'] + 1;
                $d['updatedAt'] = now();
                store_write('kunden', $d);
                return [$d, $row, $old, $pwNew, $ended];
            });
            [$d, $row, $old, $pwNew, $ended] = $res;
            if ($ended || $pwNew) ksess_remove(function ($k, $v) use ($row) { return $v['kid'] === $row['id']; });
            // Protokoll ohne Passwörter
            $ch = [];
            $fmt = function ($f, $v) { if ($f === 'angebote') return implode(', ', array_map(function ($o) { $x = offer_def($o); return $x['name'] ?? $o; }, $v ?? [])); if ($f === 'active' || $f === 'mailAngebot') return $v === false ? 'nein' : 'ja'; return (string)$v; };
            foreach (array_merge(array_keys(CUSTOMER_FIELDS), ['angebote', 'active', 'mailAngebot']) as $f) {
                $from = $old ? $fmt($f, $old[$f] ?? '') : ''; $to = $fmt($f, $row[$f] ?? '');
                if ($from !== $to) $ch[] = ['k' => "c{$row['id']}|$f", 'code' => $row['nr'], 'name' => $row['firma'], 'f' => CUSTOMER_LABELS[$f], 'from' => $from, 'to' => $to];
            }
            $ou = $old['login']['username'] ?? ''; $nu = $row['login']['username'] ?? '';
            if ($ou !== $nu) $ch[] = ['k' => "c{$row['id']}|user", 'code' => $row['nr'], 'name' => $row['firma'], 'f' => 'Zugang (Benutzername)', 'from' => $ou, 'to' => $nu ?: 'entfernt'];
            if ((bool)($old['login']['active'] ?? false) !== (bool)($row['login']['active'] ?? false)) $ch[] = ['k' => "c{$row['id']}|lact", 'code' => $row['nr'], 'name' => $row['firma'], 'f' => 'Zugang aktiv', 'from' => !empty($old['login']['active']) ? 'ja' : 'nein', 'to' => !empty($row['login']['active']) ? 'ja' : 'nein'];
            if ($pwNew) $ch[] = ['k' => "c{$row['id']}|pw", 'code' => $row['nr'], 'name' => $row['firma'], 'f' => 'Passwort', 'from' => '', 'to' => 'neu gesetzt' . (!empty($row['login']['mustChange']) ? ' (muss bei der ersten Anmeldung geändert werden)' : '')];
            if ($ch) audit('customers', $old ? "Kunde „{$row['firma']}“ bearbeitet" : "Kunde „{$row['firma']}“ angelegt", $ch);
            respond(['ok' => true, 'rev' => $d['rev'], 'customer' => customer_public($row)]);
        }

        case 'kunde_delete': {
            require_admin_confirmation();
            $b = body();
            $id = (string)($b['id'] ?? '');
            $res = with_lock('kunden', function () use ($id, $b) {
                $d = customers_load();
                if ((int)($b['rev'] ?? -1) !== (int)$d['rev']) fail('Die Kundendaten wurden inzwischen an anderer Stelle geändert. Bitte neu laden.', 409);
                foreach ($d['customers'] as $i => $c) if ($c['id'] === $id) {
                    array_splice($d['customers'], $i, 1);
                    $d['rev'] = (int)$d['rev'] + 1;
                    $d['updatedAt'] = now();
                    store_write('kunden', $d);
                    return [$d, $c];
                }
                fail('Kunde nicht gefunden.', 404);
            });
            [$d, $c] = $res;
            ksess_remove(function ($k, $v) use ($id) { return $v['kid'] === $id; });
            with_lock('merklisten', function () use ($id) { $all = store_read('merklisten') ?? []; if (isset($all[$id])) { unset($all[$id]); store_write('merklisten', $all); } });
            audit('customers', "Kunde „{$c['firma']}“ gelöscht", [['k' => "c$id|-", 'code' => $c['nr'] ?? '', 'name' => $c['firma'], 'f' => 'Kunde gelöscht', 'from' => $c['firma'], 'to' => '']]);
            respond(['ok' => true, 'rev' => $d['rev']]);
        }

        case 'status': {
            header('Cache-Control: no-store');
            $u = current_user();
            $noUsers = !users_load();
            respond(['ok' => true, 'setupRequired' => $noUsers && setup_allowed(), 'setupLocked' => $noUsers && !setup_allowed(), 'loggedIn' => (bool)$u, 'csrf' => $u ? $_SESSION['csrf'] : null,
                     'user' => $u ? me_payload($u) : null, 'company' => $CFG['company'], 'wartung' => $u ? wartung() : null]);
        }

        case 'wartung_save': {
            $me = require_admin_confirmation();
            $b = body();
            $on = !empty($b['active']);
            $msg = mb_substr(trim(str_replace("\r", '', preg_replace('/[\x00-\x08\x0b-\x1f]/u', '', (string)($b['message'] ?? '')) ?? '')), 0, 500);
            $until = (string)($b['until'] ?? '');
            if ($until !== '' && !preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/', $until)) fail('Bitte eine gültige Uhrzeit für das voraussichtliche Ende angeben.', 422);
            $old = wartung();
            $new = ['active' => $on, 'message' => $msg, 'until' => $until !== '' ? $until : null, 'since' => $on ? ($old['since'] ?? now()) : null, 'by' => $me['name'], 'changed' => now()];
            store_write('wartung', $new);
            if ((bool)$old !== $on) audit('wartung', $on ? 'Wartungsmodus eingeschaltet – Angebotsseite für Kunden pausiert' : 'Wartungsmodus ausgeschaltet – Angebotsseite wieder erreichbar',
                [['k' => 'wartung', 'code' => '', 'name' => 'Wartungsmodus', 'f' => 'Status', 'from' => $old ? 'an' : 'aus', 'to' => $on ? 'an' : 'aus']]);
            elseif ($on) audit('wartung', 'Hinweis zum Wartungsmodus geändert');
            respond(['ok' => true, 'wartung' => wartung()]);
        }

        case 'reauth': {
            $me = require_auth(true, 'admin');
            $u = confirm_password($me, (string)(body()['password'] ?? ''));
            mark_admin_confirmed($u);
            audit('reauth', 'Sensible Verwaltungsaktionen für fünf Minuten bestätigt');
            respond(['ok' => true, 'confirmedUntil' => time() + ADMIN_CONFIRM_SECONDS]);
        }

        case 'setup': {
            $b = body();
            $u = with_lock('nutzer', function () use ($b) {
                if (users_load()) fail('Die Ersteinrichtung ist bereits erfolgt.', 409);
                if (!setup_allowed()) fail('Die Ersteinrichtung im Browser ist auf diesem Server gesperrt. Zugang auf dem Server wiederherstellen (siehe LIESMICH).', 403);
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
            if (!users_load()) fail(setup_allowed() ? 'Bitte zuerst die Ersteinrichtung durchführen.' : 'Es ist kein Zugang vorhanden oder die Nutzerdaten sind nicht lesbar. Bitte den Zugang auf dem Server wiederherstellen (siehe LIESMICH).', 409);
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
                        $lockedNow = login_failure($users[$i]);
                        users_save($users);
                        return [$lockedNow ? 'lockednow' : 'bad', $users[$i]];
                    }
                    if (!$u['active']) return ['inactive', $u];
                    if (password_needs_rehash((string)$u['hash'], PASSWORD_DEFAULT)) $users[$i]['hash'] = password_hash($pw, PASSWORD_DEFAULT);
                    // Bei 2FA ist das Passwort allein noch keine erfolgreiche Anmeldung.
                    if (empty($u['totp'])) {
                        $users[$i]['failCount'] = 0;
                        $users[$i]['lockedUntil'] = 0;
                        $users[$i]['lastLogin'] = now();
                    }
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
                if ((int)($u['lockedUntil'] ?? 0) > time()) return ['locked', $u];
                $how = null;
                $step = totp_check((string)$u['totp'], $code, (int)($u['totpLast'] ?? 0));
                if ($step !== null) { $u['totpLast'] = $step; $how = 'app'; }
                elseif (preg_match('/^[a-z0-9]{5}-?[a-z0-9]{5}$/i', $code)) {
                    $h = rc_hash($code);
                    $k = array_search($h, $u['recovery'] ?? [], true);
                    if ($k !== false) { array_splice($u['recovery'], $k, 1); $how = 'recovery'; }
                }
                if (!$how) {
                    $locked = login_failure($u);
                    users_save($users);
                    return [$locked ? 'locked' : 'bad', $u];
                }
                $u['failCount'] = 0;
                $u['lockedUntil'] = 0;
                $u['lastLogin'] = now();
                $out = $u;
                unset($u);
                users_save($users);
                return [$how, $out];
            });
            [$st, $u] = $res;
            if ($st === 'gone') { $_SESSION = []; fail('Die Anmeldung ist abgelaufen. Bitte erneut anmelden.', 401); }
            if ($st === 'bad' || $st === 'locked') {
                attempts_record(false);
                $_SESSION['pend']['n'] = (int)$p['n'] + 1;
                audit('login_fail', 'Zwei-Faktor-Code falsch', [], ['username' => $u['username'], 'name' => $u['name'], 'role' => $u['role']]);
                if ($st === 'locked') { $_SESSION = []; fail('Dieser Zugang ist wegen zu vieler Fehlversuche gesperrt. Bitte später erneut versuchen oder einen Administrator kontaktieren.', 429); }
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
            // Auch der Austausch eines vorhandenen Faktors braucht einen erneuten Passwortnachweis.
            if (!empty($me['totp'])) {
                unset($_SESSION['totpPending']);
                $me = confirm_password($me, (string)(body()['password'] ?? ''));
            }
            $secret = b32_encode(random_bytes(20));
            $_SESSION['totpPending'] = ['secret' => $secret, 'sv' => (int)$me['sv'], 't' => time()];
            $issuer = rawurlencode(($CFG['company'] ?: 'Wochenangebot') . ' Wochenangebot');
            respond(['ok' => true, 'secret' => $secret, 'uri' => "otpauth://totp/{$issuer}:" . rawurlencode($me['username']) . "?secret={$secret}&issuer={$issuer}&algorithm=SHA1&digits=6&period=30"]);
        }

        case 'twofa_enable': {
            $me = current_user();
            if (!$me) fail('Bitte erneut anmelden.', 401);
            require_csrf();
            $pending = $_SESSION['totpPending'] ?? null;
            if (!is_array($pending) || (int)$pending['sv'] !== (int)$me['sv'] || (int)$pending['t'] < time() - 300) {
                unset($_SESSION['totpPending']);
                fail('Bitte die Einrichtung neu starten.', 409);
            }
            $secret = (string)$pending['secret'];
            $step = totp_check($secret, (string)(body()['code'] ?? ''));
            if ($step === null) fail('Der Code stimmt nicht. Bitte die Uhrzeit des Handys prüfen und den aktuellen Code eingeben.', 422);
            $codes = recovery_codes();
            $u = user_update($me['id'], function (&$x) use ($secret, $step, $codes, $me) {
                if ((int)$x['sv'] !== (int)$me['sv'] || !$x['active']) fail('Bitte erneut anmelden.', 401);
                $x['sv'] = (int)$x['sv'] + 1;
                $x['totp'] = $secret; $x['totpLast'] = $step; $x['recovery'] = array_map('rc_hash', $codes); $x['changed'] = now();
            });
            if (!$u) fail('Bitte erneut anmelden.', 401);
            keep_current_session($u);
            audit('twofa', 'Zwei-Faktor-Anmeldung eingerichtet');
            respond(['ok' => true, 'recovery' => $codes, 'user' => me_payload($u)]);
        }

        case 'twofa_disable': {
            $me = require_auth(true);
            if (empty($me['totp'])) fail('Die Zwei-Faktor-Anmeldung ist nicht eingerichtet.', 409);
            if (twofa_required($me)) fail('Für Ihre Rolle ist die Zwei-Faktor-Anmeldung vorgeschrieben und kann nicht ausgeschaltet werden.', 422);
            $me = confirm_password($me, (string)(body()['password'] ?? ''));
            $u = user_update($me['id'], function (&$x) use ($me) {
                if ((int)$x['sv'] !== (int)$me['sv'] || !$x['active']) fail('Bitte erneut anmelden.', 401);
                unset($x['totp'], $x['totpLast'], $x['recovery']);
                $x['sv'] = (int)$x['sv'] + 1;
                $x['changed'] = now();
            });
            if (!$u) fail('Bitte erneut anmelden.', 401);
            keep_current_session($u);
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
            $me = confirm_password($me, (string)($b['current'] ?? ''), 401);
            $new = check_password($b['password'] ?? '', $me['username']);
            if (password_verify($new, (string)$me['hash'])) fail('Bitte ein anderes als das bisherige Passwort wählen.');
            $u = with_lock('nutzer', function () use ($me, $new) {
                $users = users_load();
                $i = user_find($users, $me['id']);
                if ($i === null || !$users[$i]['active'] || (int)$users[$i]['sv'] !== (int)$me['sv']) fail('Bitte erneut anmelden.', 401);
                $users[$i]['hash'] = password_hash($new, PASSWORD_DEFAULT);
                $users[$i]['mustChange'] = false;
                $users[$i]['sv'] = (int)$users[$i]['sv'] + 1;   // andere Sitzungen dieses Nutzers abmelden
                $users[$i]['changed'] = now();
                users_save($users);
                return $users[$i];
            });
            $_SESSION['sv'] = (int)$u['sv'];
            mark_admin_confirmed($u);
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
                foreach (store_read('protokoll/' . $m) ?? [] as $e) if (in_array($e['a'], ['login_fail', 'kunde_login_fail'], true) && strtotime($e['t']) > time() - 7 * 86400) $fails[] = ['t' => $e['t'], 'u' => $e['u'], 'ip' => $e['ip'] ?? '', 's' => $e['s']];
            }
            usort($fails, function ($a, $b) { return strcmp($b['t'], $a['t']); });
            $f24 = count(array_filter($fails, function ($e) { return strtotime($e['t']) > time() - 86400; }));
            $gs = store_read('laendersperre') ?? [];
            $gcc = []; foreach ($gs['cc'] ?? [] as $k => $v) $gcc[] = ['cc' => $k, 'n' => $v['n'], 'last' => $v['last']];
            usort($gcc, function ($a, $b) { return $b['n'] <=> $a['n']; });
            $g7 = (($gs['day'] ?? '') === gmdate('Y-m-d') ? (int)($gs['today'] ?? 0) : 0);
            foreach ($gs['days'] ?? [] as $dd => $n) if ($dd > gmdate('Y-m-d', time() - 7 * 86400)) $g7 += (int)$n;
            respond(['ok' => true, 'settings' => sec(), 'myIp' => client_ip(), 'https' => is_https(),
                     'backup' => store_read('sicherung'),
                     'wartung' => wartung(), 'storage' => store_stats(), 'php' => PHP_VERSION,
                     'disk' => ['free' => @disk_free_space($DATA) ?: null, 'total' => @disk_total_space($DATA) ?: null],
                     'mail' => (function () {
                         $l = array_filter(store_read('mailversand') ?? [], function ($x) { return strtotime($x['t']) > time() - 7 * 86400; });
                         return ['configured' => (bool)mail_cfg() && (bool)mail_base_url(), 'sent7' => count(array_filter($l, function ($x) { return $x['ok']; })), 'failed7' => count(array_filter($l, function ($x) { return !$x['ok']; }))];
                     })(),
                     'orders' => (function () {
                         $all = store_read('bestellungen') ?? [];
                         $l = array_filter($all, function ($x) { return strtotime($x['t']) > time() - 7 * 86400; });
                         $last = $all ? end($all) : null;
                         return ['enabled' => order_enabled(), 'n7' => count($l), 'failed7' => count(array_filter($l, function ($x) { return ($x['status'] ?? '') === 'fehler'; })), 'last' => $last['t'] ?? null, 'lastNr' => $last['nr'] ?? null];
                     })(),
                     'customers' => (function () {
                         $c = customers_load()['customers'];
                         $act = array_filter($c, function ($x) { return !empty($x['active']); });
                         return ['active' => count($act), 'withLogin' => count(array_filter($act, function ($x) { return !empty($x['login']['active']); })),
                                 'online' => count(array_unique(array_column(ksess_prune(store_read('kundensitzungen') ?? []), 'kid')))];
                     })(),
                     'deployment' => store_read('deployment'),
                     'myCountry' => geo_country(client_ip()), 'geo' => geo_info(), 'geoCountries' => GEO_COUNTRIES, 'geoStats' => array_slice($gcc, 0, 30), 'geoBlocked7' => $g7,
                     'users' => array_map('user_public', $users), 'sessions' => $sess, 'blockedIps' => $ips,
                     'fails' => array_slice($fails, 0, 30), 'fails24' => $f24]);
        }

        case 'security_save': {
            $me = require_admin_confirmation();
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
                    'idleMinutes' => in_array((int)($b['idleMinutes'] ?? 480), [15, 30, 60, 120, 240, 480, 720], true) ? (int)($b['idleMinutes'] ?? 480) : 480,
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
            require_admin_confirmation();
            with_lock('laendersperre', function () { store_write('laendersperre', []); });
            respond(['ok' => true]);
        }

        case 'session_end': {
            $me = require_admin_confirmation();
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
            require_admin_confirmation();
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
            require_admin_confirmation();
            @set_time_limit(180);
            try { $r = geo_download($DATA . '/geo/laender.dat.php'); }
            catch (Throwable $e) { error_log('[wochenangebot] geo: ' . $e->getMessage()); fail('Die Länderdaten konnten nicht aktualisiert werden. Bitte später erneut versuchen.', 502); }
            audit('security', 'Länderdaten aktualisiert (Stand ' . $r['date'] . ')');
            respond(['ok' => true, 'geo' => geo_info()]);
        }

        case 'user_unlock': {
            require_admin_confirmation();
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
            $me = require_admin_confirmation();
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
                if ($id === $me['id'] && ($setPw || !empty($b['reset2fa']))) {
                    fail('Für den eigenen Zugang bitte „Passwort ändern“ oder „Zwei-Faktor-Anmeldung“ verwenden.', 403);
                }
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
            $me = require_admin_confirmation();
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
            foreach (store_names('protokoll') as $f) {
                $m = basename($f);
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
                'draftSavedBy' => $draft['savedBy'] ?? null,
                'revision' => draft_rev($draft),
            ]);
        }

        /* Abgleich: Stand des Entwurfs und wer gerade im Eingabebereich ist (alle paar Sekunden) */
        case 'draft_ping': {
            $me = require_auth(true);
            $now = time();
            $pres = store_read('anwesenheit') ?? [];
            $mine = $pres[$me['id']] ?? null;
            if (!is_array($mine) || (int)($mine['at'] ?? 0) < $now - 20 || ($mine['name'] ?? '') !== $me['name']) {
                $pres = with_lock('anwesenheit', function () use ($me, $now) {
                    $l = store_read('anwesenheit') ?? [];
                    foreach ($l as $k => $v) if (!is_array($v) || (int)($v['at'] ?? 0) < $now - 90) unset($l[$k]);
                    $l[$me['id']] = ['name' => $me['name'], 'role' => $me['role'], 'at' => $now];
                    store_write('anwesenheit', $l);
                    return $l;
                });
            }
            $others = [];
            foreach ($pres as $id => $v) if ($id !== $me['id'] && is_array($v) && (int)($v['at'] ?? 0) >= $now - 45) $others[] = ['name' => (string)($v['name'] ?? ''), 'role' => (string)($v['role'] ?? '')];
            usort($others, fn($a, $b) => strcmp($a['name'], $b['name']));
            $draft = store_read('entwurf');
            $pub = store_read('angebot');
            respond(['ok' => true, 'revision' => draft_rev($draft), 'savedBy' => $draft['savedBy'] ?? null, 'savedAt' => $draft['savedAt'] ?? null,
                     'publishedAt' => $pub['publishedAt'] ?? null, 'offersRev' => (int)offers_load()['rev'], 'editors' => $others]);
        }

        case 'save_draft': {
            require_auth(true, 'editor');
            with_lock('entwurf', function () use ($CFG) {
                $b = body();
                $prev = store_read('entwurf');
                $cur = draft_rev($prev);
                if ((int)($b['revision'] ?? -1) !== $cur) draft_conflict($prev);
                $model = clean_model($b['model'] ?? null, false);
                $model['savedAt'] = now();
                $model['savedBy'] = current_user()['name'];
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
            });
        }

        case 'discard_draft': {
            require_auth(true, 'editor');
            with_lock('entwurf', function () use ($CFG) {
                $dr = store_read('entwurf');
                if (array_key_exists('revision', body()) && (int)body()['revision'] !== draft_rev($dr)) draft_conflict($dr);
                $rev = draft_end($dr, 'verworfen');
                if ($dr) { $d = changes_between($dr, store_read('angebot') ?? $dr); audit('discard', 'Entwurf verworfen' . ($d ? ' (' . changes_summary($d) . ' zurückgenommen)' : ''), array_slice($d, 0, 2000)); }
                respond(['ok' => true, 'revision' => $rev]);
            });
        }

        case 'publish': {
            require_auth(true, 'editor');
            with_lock('entwurf', function () use ($CFG) {
                $dr = store_read('entwurf');
                if (array_key_exists('revision', body()) && (int)body()['revision'] !== draft_rev($dr)) draft_conflict($dr);
                $model = clean_model(body()['model'] ?? null, true);
                $prev = store_read('angebot');
                if ($prev) {
                    $id = gmdate('Ymd-His') . '-' . bin2hex(random_bytes(3));
                    store_write('versionen/' . $id, $prev);
                    $list = store_names('versionen');
                    rsort($list);
                    foreach (array_slice($list, (int)$CFG['keep_versions']) as $old) store_delete($old);
                }
                $model['publishedAt'] = now();
                store_write('angebot', $model);
                $rev = draft_end($dr, 'veröffentlicht');
                $h = history_from_model($model, 'Veröffentlichung', $model['publishedAt']);
                if ($h) { $hid = history_id($h['week'], $h['year']); store_write('historie/' . $hid, $h); history_undelete($hid); }
                $d = $prev ? changes_between($prev, $model) : [];
                audit('publish', 'KW ' . $model['meta']['week'] . '/' . $model['meta']['year'] . ' veröffentlicht – ' . count($model['items']) . ' Artikel' . ($prev ? ' (' . changes_summary($d) . ')' : ' (erste Veröffentlichung)'), array_slice($d, 0, 2000));
                respond(['ok' => true, 'publishedAt' => $model['publishedAt'], 'revision' => $rev]);
            });
        }

        case 'versions': {
            require_auth();
            $list = store_names('versionen');
            rsort($list);
            $out = [];
            foreach ($list as $f) {
                $id = basename($f);
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
                foreach (($h['items'] ?? []) as $it) {
                    $row = ['code' => $it['code'] ?? null, 'name' => $it['name'] ?? '', 'price' => $it['price'] ?? ['status' => 'none']];
                    if (!empty($it['variants'])) $row['variants'] = $it['variants'];
                    $items[] = $row;
                }
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
    store_rollback();
    fail($e->getMessage(), 422);
}
