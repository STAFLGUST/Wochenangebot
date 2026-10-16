<?php
/*
 * Wochenangebot – API
 *
 * Öffentlich:
 *   GET  ?action=offer            veröffentlichtes Angebot
 * Eingabebereich (Anmeldung nötig, Schreibzugriffe zusätzlich mit CSRF-Token):
 *   GET  ?action=status           Anmeldestatus / Ersteinrichtung nötig?
 *   POST ?action=setup            erstes Passwort festlegen (nur solange keins existiert)
 *   POST ?action=login | logout
 *   GET  ?action=draft            Entwurf + veröffentlichter Stand
 *   POST ?action=save_draft       Entwurf speichern
 *   POST ?action=discard_draft    Entwurf verwerfen
 *   POST ?action=publish          Entwurf veröffentlichen (vorheriger Stand wird archiviert)
 *   GET  ?action=versions         frühere Veröffentlichungen
 *   GET  ?action=version&id=…     eine frühere Veröffentlichung
 *   POST ?action=change_password
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
    if (!empty($_SESSION['auth']) && (time() - (int)($_SESSION['seen'] ?? 0)) > $max) { $_SESSION = []; session_regenerate_id(true); }
    if (!empty($_SESSION['auth'])) $_SESSION['seen'] = time();
}
function logged_in(): bool { start_session(); return !empty($_SESSION['auth']); }
function require_auth(bool $write = false): void
{
    if (!logged_in()) fail('Bitte erneut anmelden.', 401);
    if ($write) {
        $tok = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
        if (!is_string($tok) || !hash_equals((string)($_SESSION['csrf'] ?? ''), $tok)) fail('Sicherheitsprüfung fehlgeschlagen – bitte Seite neu laden.', 403);
    }
}
function sign_in(): string
{
    session_regenerate_id(true);
    $_SESSION['auth'] = true;
    $_SESSION['seen'] = time();
    $_SESSION['csrf'] = bin2hex(random_bytes(32));
    return $_SESSION['csrf'];
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

/* ---------------- Aktionen ---------------- */

$action = (string)($_GET['action'] ?? '');
$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$writeActions = ['setup', 'login', 'logout', 'save_draft', 'discard_draft', 'publish', 'change_password'];
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
            $in = logged_in();
            respond(['ok' => true, 'setupRequired' => store_read('admin') === null, 'loggedIn' => $in, 'csrf' => $in ? $_SESSION['csrf'] : null, 'company' => $CFG['company']]);
        }

        case 'setup': {
            if (store_read('admin') !== null) fail('Das Passwort ist bereits eingerichtet.', 409);
            $pw = (string)(body()['password'] ?? '');
            if (mb_strlen($pw) < 10) fail('Das Passwort muss mindestens 10 Zeichen lang sein.');
            store_write('admin', ['hash' => password_hash($pw, PASSWORD_DEFAULT), 'created' => now()]);
            start_session();
            respond(['ok' => true, 'csrf' => sign_in()]);
        }

        case 'login': {
            start_session();
            attempts_check();
            $adm = store_read('admin');
            if ($adm === null) fail('Bitte zuerst ein Passwort einrichten.', 409);
            $pw = (string)(body()['password'] ?? '');
            if (!password_verify($pw, (string)$adm['hash'])) { attempts_record(false); usleep(400000); fail('Passwort ist nicht korrekt.', 401); }
            attempts_record(true);
            if (password_needs_rehash((string)$adm['hash'], PASSWORD_DEFAULT)) { $adm['hash'] = password_hash($pw, PASSWORD_DEFAULT); store_write('admin', $adm); }
            respond(['ok' => true, 'csrf' => sign_in()]);
        }

        case 'logout': {
            start_session();
            $_SESSION = [];
            session_destroy();
            respond(['ok' => true]);
        }

        case 'change_password': {
            require_auth(true);
            $b = body();
            $adm = store_read('admin');
            if (!$adm || !password_verify((string)($b['current'] ?? ''), (string)$adm['hash'])) fail('Das bisherige Passwort ist nicht korrekt.', 401);
            $new = (string)($b['password'] ?? '');
            if (mb_strlen($new) < 10) fail('Das neue Passwort muss mindestens 10 Zeichen lang sein.');
            store_write('admin', ['hash' => password_hash($new, PASSWORD_DEFAULT), 'created' => $adm['created'] ?? now(), 'changed' => now()]);
            respond(['ok' => true]);
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
            require_auth(true);
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
            respond(['ok' => true, 'savedAt' => $model['savedAt'], 'revision' => $model['rev']]);
        }

        case 'discard_draft': {
            require_auth(true);
            store_delete('entwurf');
            respond(['ok' => true]);
        }

        case 'publish': {
            require_auth(true);
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

        default:
            fail('Unbekannte Aktion.', 404);
    }
} catch (InvalidArgumentException $e) {
    fail($e->getMessage(), 422);
}
