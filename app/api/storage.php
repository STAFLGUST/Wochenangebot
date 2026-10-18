<?php
/* Shared persistence for HTTP and maintenance tools. No automatic migration/fallback. */
const GUARD = "<?php http_response_code(404); exit; ?>\n";
const STORE_SIDECARS = ['mail-schluessel', 'sicherung', 'deployment'];

function store_path(string $name): string
{
    global $DATA;
    if (!preg_match('~^[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*$~D', $name)) throw new RuntimeException('Invalid storage key');
    return $DATA . '/' . $name . '.php';
}
function store_mode(): string
{
    global $DATA;
    static $lock = null, $mode = null;
    if ($mode !== null) return $mode;
    if (!is_dir($DATA) && !mkdir($DATA, 0775, true)) throw new RuntimeException('Cannot create data directory');
    $lock = fopen($DATA . '/.storage.lock', 'c');
    if (!$lock || !flock($lock, LOCK_SH)) throw new RuntimeException('Cannot lock storage');
    // Held until the end of the process: migration cannot switch a live request's backend.
    return $mode = is_file($DATA . '/.sqlite-active') ? 'sqlite' : 'files';
}
function store_db(): PDO
{
    global $DATA;
    static $db = null;
    if ($db !== null) return $db;
    $path = $DATA . '/.sqlite/store.sqlite';
    if (!is_file($path)) throw new RuntimeException('Active database missing; restore backup');
    $db = new PDO('sqlite:' . $path, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_TIMEOUT => 10]);
    $db->exec('PRAGMA busy_timeout=10000');
    $db->exec('PRAGMA synchronous=FULL');
    if ((int)$db->query('PRAGMA user_version')->fetchColumn() !== 1) throw new RuntimeException('Unsupported database schema');
    return $db;
}
function store_sql(string $name): bool
{
    store_path($name);
    return store_mode() === 'sqlite' && !in_array($name, STORE_SIDECARS, true);
}
function store_read(string $name)
{
    if (store_sql($name)) {
        $q = store_db()->prepare('SELECT payload FROM documents WHERE name = ?');
        $q->execute([$name]); $raw = $q->fetchColumn();
        return $raw === false ? null : json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
    }
    $p = store_path($name);
    if (!is_file($p)) return null;
    $raw = (string)file_get_contents($p);
    if (strncmp($raw, GUARD, strlen(GUARD)) === 0) $raw = substr($raw, strlen(GUARD));
    $data = json_decode($raw, true);
    return is_array($data) ? $data : null;
}
function store_write(string $name, array $data): void
{
    $json = json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
    if (store_sql($name)) {
        $q = store_db()->prepare('INSERT INTO documents(name,payload,mtime) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload,mtime=excluded.mtime');
        $q->execute([$name, $json, time()]); return;
    }
    $dir = dirname(store_path($name));
    if (!is_dir($dir) && !mkdir($dir, 0775, true)) throw new RuntimeException('Cannot create storage directory');
    $tmp = store_path($name) . '.' . bin2hex(random_bytes(4)) . '.tmp';
    if (file_put_contents($tmp, GUARD . $json, LOCK_EX) === false) throw new RuntimeException('Cannot write data');
    if (!rename($tmp, store_path($name))) { @unlink($tmp); throw new RuntimeException('Cannot replace data'); }
}
function store_delete(string $name): void
{
    if (store_sql($name)) { $q = store_db()->prepare('DELETE FROM documents WHERE name=?'); $q->execute([$name]); }
    else { $p = store_path($name); if (is_file($p) && !unlink($p)) throw new RuntimeException('Cannot delete data'); }
}
function store_mtime(string $name): ?int
{
    if (store_sql($name)) {
        $q = store_db()->prepare('SELECT mtime FROM documents WHERE name=?'); $q->execute([$name]); $t = $q->fetchColumn();
        return $t === false ? null : (int)$t;
    }
    return is_file(store_path($name)) ? (int)filemtime(store_path($name)) : null;
}
function store_names(string $prefix): array
{
    store_path($prefix);
    if (store_mode() === 'sqlite') {
        $q = store_db()->prepare('SELECT name FROM documents WHERE substr(name,1,?)=? ORDER BY name');
        $q->execute([strlen($prefix) + 1, $prefix . '/']);
        return $q->fetchAll(PDO::FETCH_COLUMN);
    }
    return array_map(fn($p) => $prefix . '/' . basename($p, '.php'), glob(dirname(store_path($prefix . '/x')) . '/*.php') ?: []);
}
function store_commit(): void
{
    if (!empty($GLOBALS['store_tx'])) { store_db()->exec('COMMIT'); $GLOBALS['store_tx'] = false; }
}
function store_rollback(): void
{
    if (!empty($GLOBALS['store_tx'])) { store_db()->exec('ROLLBACK'); $GLOBALS['store_tx'] = false; }
}
function with_lock(string $name, callable $fn)
{
    global $DATA;
    if (store_sql($name)) {
        if (!empty($GLOBALS['store_tx'])) return $fn();
        store_db()->exec('BEGIN IMMEDIATE'); $GLOBALS['store_tx'] = true;
        try { $result = $fn(); store_commit(); return $result; }
        catch (Throwable $e) { store_rollback(); throw $e; }
    }
    static $held = [];
    if (!empty($held[$name])) return $fn();
    $fh = fopen($DATA . '/.' . $name . '.lock', 'c');
    if (!$fh || !flock($fh, LOCK_EX)) throw new RuntimeException('Cannot lock data');
    $held[$name] = true;
    try { return $fn(); } finally { unset($held[$name]); flock($fh, LOCK_UN); fclose($fh); }
}
