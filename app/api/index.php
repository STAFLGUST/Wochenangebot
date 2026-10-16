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
 *   POST ?action=user_save | user_delete
 *
 * Alle Daten liegen als .php-Dateien mit Zugriffssperre im Datenordner –
 * sie lassen sich auch ohne .htaccess nicht direkt im Browser abrufen.
 */
declare(strict_types=1);

$CFG = require __DIR__ . '/config.php';
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
            'lastLogin' => $u['lastLogin'] ?? null, 'changed' => $u['changed'] ?? null];
}
function active_admins(array $users): int { $n = 0; foreach ($users as $u) if ($u['role'] === 'admin' && $u['active']) $n++; return $n; }
function clean_username($v): string
{
    $v = is_string($v) ? strtolower(trim($v)) : '';
    if (!preg_match('/^[a-z0-9][a-z0-9._-]{1,31}$/', $v)) throw new InvalidArgumentException('Benutzername: 2–32 Zeichen, nur Buchstaben a–z, Ziffern, Punkt, Binde- und Unterstrich.');
    return $v;
}
function check_password($pw): string
{
    $pw = is_string($pw) ? $pw : '';
    if (mb_strlen($pw) < 10) throw new InvalidArgumentException('Das Passwort muss mindestens 10 Zeichen lang sein.');
    if (strlen($pw) > 200) throw new InvalidArgumentException('Das Passwort ist zu lang.');
    return $pw;
}

/* ---------------- Sitzung ---------------- */

function start_session(): void
{
    global $CFG;
    if (session_status() === PHP_SESSION_ACTIVE) return;
    $https = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
    ini_set('session.use_strict_mode', '1');
    ini_set('session.use_only_cookies', '1');
    session_name('WA_ADMIN');
    session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'secure' => $https, 'httponly' => true, 'samesite' => 'Strict']);
    session_start();
    $max = (int)$CFG['session_hours'] * 3600;
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
    $ME = $u;
    return $_SESSION['csrf'];
}
function me_payload(array $u): array { return ['id' => $u['id'], 'username' => $u['username'], 'name' => $u['name'], 'role' => $u['role'], 'mustChange' => (bool)($u['mustChange'] ?? false)]; }

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
        $a[$k] = ['n' => $n, 't' => time(), 'until' => $n >= (int)$CFG['max_attempts'] ? time() + 60 * (int)$CFG['lock_minutes'] : 0];
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
$writeActions = ['setup', 'login', 'logout', 'save_draft', 'discard_draft', 'publish', 'change_password', 'history_import', 'history_delete', 'user_save', 'user_delete', 'stock_import', 'master_save'];
if (in_array($action, $writeActions, true)) {
    if ($method !== 'POST') fail('Methode nicht erlaubt.', 405);
    if (stripos((string)($_SERVER['CONTENT_TYPE'] ?? ''), 'application/json') !== 0) fail('Ungültige Anfrage.', 415);
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
                $u = ['id' => 'u' . bin2hex(random_bytes(6)), 'username' => clean_username($b['username'] ?? ''), 'name' => $name, 'role' => 'admin',
                      'active' => true, 'hash' => password_hash(check_password($b['password'] ?? ''), PASSWORD_DEFAULT), 'mustChange' => false,
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
            $res = with_lock('nutzer', function () use ($name, $pw) {
                $users = users_load();
                foreach ($users as $i => $u) {
                    if ($u['username'] !== $name) continue;
                    if (!password_verify($pw, (string)$u['hash'])) return null;
                    if (!$u['active']) return 'inactive';
                    if (password_needs_rehash((string)$u['hash'], PASSWORD_DEFAULT)) $users[$i]['hash'] = password_hash($pw, PASSWORD_DEFAULT);
                    $users[$i]['lastLogin'] = now();
                    users_save($users);
                    return $users[$i];
                }
                password_verify($pw, '$2y$10$y80WR5wtxxV9G3NpBGQXmeL3EYKIGKm4gaElkDTK2cWFQtjyZdoPa'); // gleiche Laufzeit wie bei vorhandenem Nutzer
                return null;
            });
            if (!is_array($res)) {
                attempts_record(false);
                audit('login_fail', 'Anmeldung fehlgeschlagen' . ($name !== '' ? ' (Benutzername „' . mb_substr($name, 0, 40) . '“)' : '') . ($res === 'inactive' ? ' – Zugang deaktiviert' : ''), [], ['username' => mb_substr($name, 0, 40), 'name' => '', 'role' => '']);
                usleep(400000);
                fail($res === 'inactive' ? 'Dieser Zugang ist deaktiviert.' : 'Benutzername oder Passwort ist nicht korrekt.', 401);
            }
            attempts_record(true);
            $tok = sign_in($res);
            audit('login', 'Angemeldet');
            respond(['ok' => true, 'csrf' => $tok, 'user' => me_payload($res)]);
        }

        case 'logout': {
            $u = current_user();
            if ($u) audit('logout', 'Abgemeldet');
            $_SESSION = [];
            session_destroy();
            respond(['ok' => true]);
        }

        case 'change_password': {
            $me = current_user();
            if (!$me) fail('Bitte erneut anmelden.', 401);
            $tok = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
            if (!is_string($tok) || !hash_equals((string)($_SESSION['csrf'] ?? ''), $tok)) fail('Sicherheitsprüfung fehlgeschlagen – bitte Seite neu laden.', 403);
            $b = body();
            if (!password_verify((string)($b['current'] ?? ''), (string)$me['hash'])) fail('Das bisherige Passwort ist nicht korrekt.', 401);
            $new = check_password($b['password'] ?? '');
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
                          'hash' => password_hash(check_password($pw), PASSWORD_DEFAULT), 'mustChange' => !empty($b['mustChange']), 'sv' => 1,
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
                if ($setPw) {
                    $users[$i]['hash'] = password_hash(check_password($pw), PASSWORD_DEFAULT);
                    $users[$i]['mustChange'] = $id !== $me['id'] && !empty($b['mustChange']);
                    $users[$i]['sv'] = (int)$old['sv'] + 1;      // bestehende Sitzungen des Nutzers beenden
                    $d[] = ['k' => 'u|pw', 'code' => '', 'name' => $old['username'], 'f' => 'Passwort', 'from' => '', 'to' => 'neu gesetzt' . ($users[$i]['mustChange'] ? ' (muss beim Anmelden geändert werden)' : '')];
                }
                $users[$i]['changed'] = now();
                users_save($users);
                return [$users[$i], 'Nutzer „' . $old['username'] . '“ geändert', $d];
            });
            [$u, $msg, $d] = $res;
            if ($u['id'] === $me['id']) { $_SESSION['sv'] = (int)$u['sv']; }
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
                if ($d) audit('draft', '„frisch“ aus ' . count($d) . ' Bezeichnungen entfernt (steht im Zustand)', array_slice($d, 0, 2000));
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
