<?php
declare(strict_types=1);
/* Sicherheitseinstellungen, Länder-/IP-Sperre, Zwei-Faktor, Sitzungsregister, Wartungsmodus */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Sicherheitseinstellungen ---------------- */

const SEC_DEFAULTS = ['twofa' => 'off', 'pwMin' => 10, 'pwComplex' => false, 'pwLeak' => false, 'idleMinutes' => 480,
                      'ipEnabled' => false, 'adminIps' => [], 'lockAfter' => 10, 'lockMinutes' => 15,
                      'geoEnabled' => false, 'geoMode' => 'block', 'geoCountries' => [], 'geoScope' => 'admin',
                      'bestaetigungAus' => [], 'bestaetigungMinuten' => 5];
/* Passwortbestätigung je Aktion (Sicherheit → Passwortbestätigung). Schlüssel = Aktion; [Bereich, Bezeichnung, fest].
   „fest“ = immer Pflicht (Zugänge, Rechte, Sitzungen, Sperren, Sicherheit, Postfach-Zugangsdaten) – nicht abschaltbar.
   Gespeichert werden nur die abgeschalteten Schlüssel (`bestaetigungAus`); unbekannte Schlüssel verlangen immer die Bestätigung. */
const BESTAETIGUNG = [
    'einzel_senden'         => ['Kunden', 'Einzelangebot per E-Mail senden', false],
    'kunden_rundmail'       => ['Kunden', 'Wochenangebot an Kunden senden', false],
    'kunden_restposten'     => ['Kunden', 'Sonderposten an Kunden senden', false],
    'kunde_mail'            => ['Kunden', 'E-Mail an einen Kunden (Einladung, Passwort-Link, Angebotslink)', false],
    'kunde_save'            => ['Kunden', 'Kunde anlegen oder ändern (auch Portal-Zugang)', false],
    'kunde_delete'          => ['Kunden', 'Kunde löschen', false],
    'kunden_import'         => ['Kunden', 'Kundenimport übernehmen', false],
    'angebote_loeschen'     => ['Angebote', 'Kundenangebot löschen', false],
    'bestell_settings_save' => ['Einstellungen', 'Bestellwünsche: Empfänger und Einstellungen ändern', false],
    'fracht_save'           => ['Einstellungen', 'Frachtregel ändern', false],
    'mail_save'             => ['Einstellungen', 'E-Mail-Signatur ändern', false],
    'mail_test'             => ['Einstellungen', 'Testmail senden', false],
    'benachrichtigung_save' => ['Einstellungen', 'Benachrichtigungen ändern', false],
    'wartung_save'          => ['Einstellungen', 'Wartungsmodus ein- oder ausschalten', false],
    'ort_update'            => ['Einstellungen', 'Ortsdatenbank (Auswertung) aktualisieren', false],
    'geo_update'            => ['Einstellungen', 'Länderdaten aktualisieren', false],
    'geo_clear_stats'       => ['Einstellungen', 'Statistik abgewiesener Zugriffe zurücksetzen', false],
    'fw_feed'               => ['Einstellungen', 'Bedrohungsliste (Spamhaus) aktualisieren', false],
    'user_save'             => ['Immer mit Bestätigung', 'Nutzer anlegen oder ändern', true],
    'user_delete'           => ['Immer mit Bestätigung', 'Nutzer löschen', true],
    'user_unlock'           => ['Immer mit Bestätigung', 'Gesperrten Zugang entsperren', true],
    'user_mail'             => ['Immer mit Bestätigung', 'Zugangsdaten per E-Mail an einen Nutzer senden', true],
    'rechte_save'           => ['Immer mit Bestätigung', 'Rechte der Rollen ändern', true],
    'session_end'           => ['Immer mit Bestätigung', 'Sitzung beenden', true],
    'ip_unblock'            => ['Immer mit Bestätigung', 'IP-Sperre aufheben', true],
    'security_save'         => ['Immer mit Bestätigung', 'Sicherheitseinstellungen ändern (auch diese Liste)', true],
    'security_export'       => ['Immer mit Bestätigung', 'Sicherheitsprotokoll exportieren', true],
    'fw_save'               => ['Immer mit Bestätigung', 'Firewall-Einstellungen und Vorlagen anwenden', true],
    'fw_sperren'            => ['Immer mit Bestätigung', 'Adresse sperren oder freigeben (Schutz)', true],
    'mail_konto_save'       => ['Immer mit Bestätigung', 'Postfach für den E-Mail-Versand (Zugangsdaten) ändern', true],
];
const BESTAETIGUNG_MINUTEN = [5, 15, 30, 60];
function bestaetigung_noetig(string $key): bool
{
    $b = BESTAETIGUNG[$key] ?? null;
    if (!$b || $b[2]) return true;
    return !in_array($key, (array)(sec()['bestaetigungAus'] ?? []), true);
}
/* Wie lange eine Passwortbestätigung gilt (Sekunden) */
function bestaetigung_sekunden(): int
{
    $m = (int)(sec()['bestaetigungMinuten'] ?? 5);
    return 60 * (in_array($m, BESTAETIGUNG_MINUTEN, true) ? $m : 5);
}
function bestaetigung_katalog(): array
{
    $out = [];
    foreach (BESTAETIGUNG as $k => [$g, $l, $fest]) $out[] = ['key' => $k, 'group' => $g, 'label' => $l, 'fest' => $fest, 'noetig' => bestaetigung_noetig($k)];
    return $out;
}
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

/* Sicherheitseinstellungen prüfen und vollständig zurückgeben (Speichern, Vorlagen, Import) – $me = handelnder Administrator */
function sec_clean(array $b, array $old, array $me): array
{
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
    if ($twofa !== 'off' && !has_second_factor($me) && ($twofa === 'all' || $me['role'] === 'admin')) throw new InvalidArgumentException('Bitte richten Sie zuerst für sich selbst die Zwei-Faktor-Anmeldung ein (Menü „…“ → „Zwei-Faktor-Anmeldung“).');
    $new = ['twofa' => $twofa, 'pwMin' => max(10, min(32, (int)($b['pwMin'] ?? 10))), 'pwComplex' => !empty($b['pwComplex']),
            'pwLeak' => array_key_exists('pwLeak', $b) ? !empty($b['pwLeak']) : !empty($old['pwLeak']),   // ältere Oberfläche ohne Feld: unverändert
            'idleMinutes' => in_array((int)($b['idleMinutes'] ?? 480), [15, 30, 60, 120, 240, 480, 720], true) ? (int)($b['idleMinutes'] ?? 480) : 480,
            'ipEnabled' => $ipEnabled, 'adminIps' => $ips,
            'lockAfter' => max(3, min(20, (int)($b['lockAfter'] ?? 10))), 'lockMinutes' => max(5, min(1440, (int)($b['lockMinutes'] ?? 15))),
            'geoEnabled' => $geoEnabled, 'geoMode' => $geoMode, 'geoCountries' => $gc, 'geoScope' => $geoScope];
    // Passwortbestätigung: nur abschaltbare Aktionen; ohne Angabe (ältere Oberfläche) bleibt der bisherige Stand
    if (array_key_exists('bestaetigungAus', $b)) {
        $aus = [];
        foreach ((array)$b['bestaetigungAus'] as $k) {
            $k = (string)$k;
            if (!isset(BESTAETIGUNG[$k])) throw new InvalidArgumentException('Unbekannte Aktion bei der Passwortbestätigung.');
            if (BESTAETIGUNG[$k][2]) throw new InvalidArgumentException('„' . BESTAETIGUNG[$k][1] . '“ verlangt immer eine Passwortbestätigung.');
            if (!in_array($k, $aus, true)) $aus[] = $k;
        }
        $new['bestaetigungAus'] = array_values(array_filter(array_keys(BESTAETIGUNG), fn($k) => in_array($k, $aus, true)));
    } else $new['bestaetigungAus'] = array_values((array)($old['bestaetigungAus'] ?? []));
    $min = (int)($b['bestaetigungMinuten'] ?? ($old['bestaetigungMinuten'] ?? 5));
    if (!in_array($min, BESTAETIGUNG_MINUTEN, true)) throw new InvalidArgumentException('Ungültige Gültigkeitsdauer der Passwortbestätigung.');
    $new['bestaetigungMinuten'] = $min;
    return $new;
}
