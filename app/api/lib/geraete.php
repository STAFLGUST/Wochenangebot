<?php
declare(strict_types=1);
/* Vertraute Geräte: Nach einer erfolgreichen Anmeldung merkt sich der Browser eine zufällige Kennung (Cookie, nur für den
   Server lesbar); gespeichert wird beim Zugang nur deren Prüfsumme. Wird ein Zugang durch fremde Fehlversuche gesperrt,
   kommt der Inhaber auf einem solchen Gerät trotzdem mit seinem Passwort hinein – Fehlversuche zählen dann nur für dieses
   Gerät (nach GERAET_FEHLER ist es bis zur nächsten erfolgreichen Anmeldung nicht mehr vertraut). Ohne die Kennung bleibt
   die Sperre unverändert, deshalb ändert sich für Angreifer nichts. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const GERAET_COOKIE = 'WA_GERAET';
const GERAET_TAGE = 180;     // unbenutzte Geräte verfallen
const GERAET_MAX = 10;       // je Zugang (die zuletzt benutzten bleiben)
const GERAET_FEHLER = 5;     // falsche Passwörter/Codes je Gerät während einer Sperre

/* Kennung aus dem Cookie (nur das Format wird geprüft) */
function geraet_token(): string
{
    $t = (string)($_COOKIE[GERAET_COOKIE] ?? '');
    return preg_match('/^[A-Za-z0-9_-]{43}$/D', $t) ? $t : '';
}
function geraet_hash(string $t): string { return hash('sha256', 'wa-geraet|' . $t); }

/* Gültige (nicht verfallene) Geräte eines Zugangs */
function geraete_gueltig(array $acc): array
{
    $grenze = time() - GERAET_TAGE * 86400;
    return array_values(array_filter((array)($acc['geraete'] ?? []), fn($g) => is_array($g) && is_string($g['h'] ?? null) && (int)($g['zuletzt'] ?? 0) > $grenze));
}

/* Ist dieser Browser für den Zugang vertraut (und hat noch Versuche)? Liefert den Index in $acc['geraete'] oder null. */
function geraet_vertraut(array $acc): ?int
{
    if (function_exists('app_client') && app_client()) return null;   // die App nutzt keine Cookies
    $t = geraet_token();
    if ($t === '') return null;
    $h = geraet_hash($t);
    $grenze = time() - GERAET_TAGE * 86400;
    foreach ((array)($acc['geraete'] ?? []) as $i => $g) {
        if (is_array($g) && hash_equals((string)($g['h'] ?? ''), $h) && (int)($g['zuletzt'] ?? 0) > $grenze && (int)($g['f'] ?? 0) < GERAET_FEHLER) return $i;
    }
    return null;
}

/* Fehlversuch auf einem vertrauten Gerät während einer Sperre zählen */
function geraet_fehlversuch(array &$acc, int $i): void
{
    if (!isset($acc['geraete'][$i])) return;
    $acc['geraete'][$i]['f'] = (int)($acc['geraete'][$i]['f'] ?? 0) + 1;
}

/* Kurzer Gerätename für die Anzeige („Chrome · Windows“) */
function geraet_name(string $ua): string
{
    $b = preg_match('/Edg\//', $ua) ? 'Edge' : (preg_match('/OPR\/|Opera/', $ua) ? 'Opera' : (preg_match('/Firefox\//', $ua) ? 'Firefox'
        : (preg_match('/Chrome\/|CriOS\//', $ua) ? 'Chrome' : (preg_match('/Safari\//', $ua) ? 'Safari' : 'Browser'))));
    $o = preg_match('/iPhone|iPad|iPod/', $ua) ? 'iOS' : (preg_match('/Android/', $ua) ? 'Android' : (preg_match('/Windows/', $ua) ? 'Windows'
        : (preg_match('/Mac OS X|Macintosh/', $ua) ? 'macOS' : (preg_match('/Linux|X11/', $ua) ? 'Linux' : ''))));
    return $o !== '' ? "$b · $o" : $b;
}

/* Nach einer erfolgreichen Anmeldung: Gerät merken bzw. auffrischen und das Cookie (neu) setzen.
   $neu: true, wenn der Zugang schon Geräte hatte und dieses nicht dazugehörte (Grundlage für „Anmeldung von neuem Gerät“). */
function geraet_merken(array &$acc, ?bool &$neu = null): void
{
    $neu = false;
    if (function_exists('app_client') && app_client()) return;
    $list = geraete_gueltig($acc);
    $t = geraet_token();
    if ($t === '') $t = b64u_enc(random_bytes(32));   // vorhandene Kennung des Browsers weiterverwenden (mehrere Zugänge im selben Browser)
    $h = geraet_hash($t);
    $gefunden = false;
    foreach ($list as $k => $g) {
        if (hash_equals((string)$g['h'], $h)) { $list[$k]['zuletzt'] = time(); $list[$k]['f'] = 0; $gefunden = true; }
    }
    if (!$gefunden) {
        $neu = $list !== [];
        $list[] = ['h' => $h, 'name' => geraet_name((string)($_SERVER['HTTP_USER_AGENT'] ?? '')), 'seit' => now(), 'zuletzt' => time(), 'f' => 0];
    }
    usort($list, fn($a, $b) => (int)$b['zuletzt'] <=> (int)$a['zuletzt']);
    $acc['geraete'] = array_slice($list, 0, GERAET_MAX);
    if (!headers_sent()) {
        setcookie(GERAET_COOKIE, $t, ['expires' => time() + GERAET_TAGE * 86400, 'path' => '/', 'secure' => is_https(), 'httponly' => true, 'samesite' => 'Strict']);
    }
}

/* Nur das aktuelle Gerät behalten (eigener Passwortwechsel) bzw. alle entfernen ($alle) */
function geraete_zuruecksetzen(array &$acc, bool $alle = false): void
{
    $t = $alle ? '' : geraet_token();
    $h = $t !== '' ? geraet_hash($t) : '';
    $acc['geraete'] = $h === '' ? [] : array_values(array_filter(geraete_gueltig($acc), fn($g) => hash_equals((string)$g['h'], $h)));
    if (!$acc['geraete']) unset($acc['geraete']);
}

/* Anzeige in der Verwaltung (ohne Prüfsummen) */
function geraete_public(array $acc): array
{
    return array_map(fn($g) => ['name' => (string)($g['name'] ?? ''), 'seit' => (string)($g['seit'] ?? ''), 'zuletzt' => gmdate('Y-m-d\TH:i:s\Z', (int)$g['zuletzt'])], geraete_gueltig($acc));
}

/* Sicherheitsereignis, wenn sich ein Administrator von einem Gerät anmeldet, das für seinen Zugang noch nicht bekannt war
   (nicht beim allerersten gemerkten Gerät). Geht über das Protokoll an die Benachrichtigung „Sicherheitsereignisse“. */
function geraet_neu_melden(array $u, bool $neu): void
{
    if (!$neu || ($u['role'] ?? '') !== 'admin') return;
    $land = function_exists('geo_country') ? (string)geo_country(client_ip()) : '';
    audit('security', 'Administrator „' . $u['username'] . '“ hat sich von einem neuen Gerät angemeldet (' . geraet_name((string)($_SERVER['HTTP_USER_AGENT'] ?? ''))
        . ($land !== '' ? ', ' . $land : '') . ')');
}
