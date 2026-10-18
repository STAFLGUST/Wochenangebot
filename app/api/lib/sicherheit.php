<?php
declare(strict_types=1);
/* Sicherheitseinstellungen, Länder-/IP-Sperre, Zwei-Faktor, Sitzungsregister, Wartungsmodus */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

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

/* ---------- Wartungsmodus ---------- */
const WARTUNG_TEXT = 'Wir aktualisieren gerade unser Angebotsportal. In Kürze sind wir wieder für Sie da.';
function wartung(): ?array
{
    $w = store_read('wartung');
    if (!is_array($w) || empty($w['active'])) return null;
    return ['active' => true, 'message' => (string)($w['message'] ?? '') ?: WARTUNG_TEXT, 'until' => $w['until'] ?? null, 'since' => $w['since'] ?? null, 'by' => $w['by'] ?? ''];
}
