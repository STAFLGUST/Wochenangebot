<?php
/* Shared persistence for HTTP and maintenance tools. No automatic migration/fallback. */
const GUARD = "<?php http_response_code(404); exit; ?>\n";
const STORE_SIDECARS = ['mail-schluessel', 'sicherung', 'deployment'];
require_once __DIR__ . '/lib/datenbereiche-liste.php';   // Speicherbereiche (erzeugt aus regeln/datenverantwortung.toml)

/* ---------------- Speicherbereiche (ADR-007 Stufe 2) ----------------
   Nach deploy/daten-trennen.sh (Kennzeichen daten/.daten-getrennt) liegen interne Dokumente im eigenen Ordner WA_DATEN_INTERN
   (Kennzeichen .daten-intern) – nur Mitarbeiterseite und Postausgang binden ihn ein. Welche Dokumente die Kundenseite braucht,
   steht in regeln/datenverantwortung.toml (Feld bereich → lib/datenbereiche-liste.php). Ohne Trennung: alles wie bisher in $DATA.
   Jeder Bereich hat eigene Sperren und (im SQLite-Modus) eine eigene Datenbank. Die Kundenseite (ohne WA_DATEN_INTERN) sieht
   interne Dokumente nicht: Lesen liefert null, Schreiben bricht ab. */
final class StoreKeinZugang extends RuntimeException {}
function store_getrennt(): bool
{
    global $DATA;
    static $g = null;
    return $g ??= is_file($DATA . '/.daten-getrennt');
}
function store_bereich(string $name): string
{
    if (!store_getrennt() || in_array($name, STORE_SIDECARS, true) || in_array($name, DATEN_KUNDENSEITE, true)) return 'haupt';
    // Muster „name/*“: auch die Sperre unter dem Namen der Gruppe (z. B. with_lock('protokoll') für protokoll/<Monat>)
    foreach (DATEN_KUNDENSEITE_PRAEFIX as $p) if (strncmp($name, $p, strlen($p)) === 0 || $name . '/' === $p) return 'haupt';
    return 'intern';
}
/* Ordner eines Bereichs; Kundenseite (kein WA_DATEN_INTERN) → StoreKeinZugang für „intern“ */
function store_ordner(string $bereich): string
{
    global $DATA;
    static $intern = false;
    if ($bereich === 'haupt') return $DATA;
    if ($intern === false) {
        $e = rtrim(trim((string)(getenv('WA_DATEN_INTERN') ?: ($_SERVER['WA_DATEN_INTERN'] ?? ''))), '/');
        if ($e !== '' && !is_file($e . '/.daten-intern')) throw new RuntimeException('Interner Datenordner nicht eingerichtet (WA_DATEN_INTERN ohne .daten-intern)');
        $intern = $e === '' ? null : $e;
    }
    if ($intern === null) throw new StoreKeinZugang('Dieses Dokument gehört nicht zur Kundenseite.');
    return $intern;
}
/* Prüfhilfe (nur Tests, WA_SPUR_INTERN=1): Kundenseite fragt ein internes Dokument an – ins Serverprotokoll. Im Betrieb geschieht
   das nicht; die Testgruppe datentrennung stellt sicher, dass Kundenaktionen keine internen Dokumente brauchen. */
function store_spur(string $name): void
{
    if (getenv('WA_SPUR_INTERN') === '1') error_log('[speicher] Kundenseite fragt internes Dokument an: ' . $name . ' (Aktion ' . ($GLOBALS['action'] ?? '?') . ')');
}
function store_path(string $name): string
{
    if (!preg_match('~^[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*$~D', $name)) throw new RuntimeException('Invalid storage key');
    $b = store_bereich($name);
    // Prüfhilfe (nur Tests): öffentliche Aktion (Kundenseite) mit internem Dokument – auch wenn dieser Server es lesen darf
    if ($b === 'intern' && getenv('WA_SPUR_INTERN') === '1' && !empty($GLOBALS['AKTION']['oeffentlich'])) {
        error_log('[speicher] öffentliche Aktion ' . ($GLOBALS['action'] ?? '?') . ' greift auf internes Dokument zu: ' . $name);
    }
    return store_ordner($b) . '/' . $name . '.php';
}
function store_mode(string $bereich = 'haupt'): string
{
    static $lock = [], $mode = [];
    if (isset($mode[$bereich])) return $mode[$bereich];
    $dir = store_ordner($bereich);
    if (!is_dir($dir) && !mkdir($dir, 0775, true)) throw new RuntimeException('Cannot create data directory');
    // Lesend öffnen genügt für flock – so stört auch eine von root (Wartungsskript) angelegte Sperrdatei nicht.
    $lock[$bereich] = @fopen($dir . '/.storage.lock', 'c') ?: (is_file($dir . '/.storage.lock') ? @fopen($dir . '/.storage.lock', 'r') : false);
    if (!$lock[$bereich] || !flock($lock[$bereich], LOCK_SH)) throw new RuntimeException('Cannot lock storage');
    // Held until the end of the process: migration cannot switch a live request's backend.
    return $mode[$bereich] = is_file($dir . '/.sqlite-active') ? 'sqlite' : 'files';
}
function store_db(string $bereich = 'haupt'): PDO
{
    static $db = [];
    if (isset($db[$bereich])) return $db[$bereich];
    $path = store_ordner($bereich) . '/.sqlite/store.sqlite';
    if (!is_file($path)) throw new RuntimeException('Active database missing; restore backup');
    $d = new PDO('sqlite:' . $path, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::ATTR_TIMEOUT => 10]);
    $d->exec('PRAGMA busy_timeout=10000');
    $d->exec('PRAGMA synchronous=FULL');
    if ((int)$d->query('PRAGMA user_version')->fetchColumn() !== 1) throw new RuntimeException('Unsupported database schema');
    return $db[$bereich] = $d;
}
function store_sql(string $name): bool
{
    store_path($name);
    return !in_array($name, STORE_SIDECARS, true) && store_mode(store_bereich($name)) === 'sqlite';
}
function store_read(string $name)
{
    try {
        if (store_sql($name)) {
            $q = store_db(store_bereich($name))->prepare('SELECT payload FROM documents WHERE name = ?');
            $q->execute([$name]); $raw = $q->fetchColumn();
            return $raw === false ? null : json_decode($raw, true, 512, JSON_THROW_ON_ERROR);
        }
        $p = store_path($name);
    } catch (StoreKeinZugang $e) { store_spur($name); return null; }   // Kundenseite: interne Dokumente gibt es hier nicht
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
        $q = store_db(store_bereich($name))->prepare('INSERT INTO documents(name,payload,mtime) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload,mtime=excluded.mtime');
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
    if (store_sql($name)) { $q = store_db(store_bereich($name))->prepare('DELETE FROM documents WHERE name=?'); $q->execute([$name]); }
    else { $p = store_path($name); if (is_file($p) && !unlink($p)) throw new RuntimeException('Cannot delete data'); }
}
function store_mtime(string $name): ?int
{
    try {
        if (store_sql($name)) {
            $q = store_db(store_bereich($name))->prepare('SELECT mtime FROM documents WHERE name=?'); $q->execute([$name]); $t = $q->fetchColumn();
            return $t === false ? null : (int)$t;
        }
        return is_file(store_path($name)) ? (int)filemtime(store_path($name)) : null;
    } catch (StoreKeinZugang $e) { store_spur($name); return null; }
}
function store_names(string $prefix): array
{
    if (!preg_match('~^[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_-]+)*$~D', $prefix)) throw new RuntimeException('Invalid storage key');
    try {
        $b = store_bereich($prefix . '/x');   // Bereich der Dokumente unter dem Präfix (z. B. protokoll/2026-11)
        if (store_mode($b) === 'sqlite') {
            $q = store_db($b)->prepare('SELECT name FROM documents WHERE substr(name,1,?)=? ORDER BY name');
            $q->execute([strlen($prefix) + 1, $prefix . '/']);
            return $q->fetchAll(PDO::FETCH_COLUMN);
        }
        return array_map(fn($p) => $prefix . '/' . basename($p, '.php'), glob(dirname(store_path($prefix . '/x')) . '/*.php') ?: []);
    } catch (StoreKeinZugang $e) { store_spur($prefix . '/*'); return []; }
}
/* Offene Transaktionen je Bereich ($GLOBALS['store_tx'] = ['haupt' => true, …]; leer = keine) */
function store_commit(?string $bereich = null): void
{
    foreach (array_keys($GLOBALS['store_tx'] ?? []) as $b) {
        if ($bereich !== null && $b !== $bereich) continue;
        store_db($b)->exec('COMMIT'); unset($GLOBALS['store_tx'][$b]);
    }
}
function store_rollback(?string $bereich = null): void
{
    foreach (array_keys($GLOBALS['store_tx'] ?? []) as $b) {
        if ($bereich !== null && $b !== $bereich) continue;
        store_db($b)->exec('ROLLBACK'); unset($GLOBALS['store_tx'][$b]);
    }
    $GLOBALS['notify_queue'] = [];   // vorgemerkte Benachrichtigungen gehören zu verworfenen Änderungen
}
function with_lock(string $name, callable $fn)
{
    if (store_sql($name)) {
        $b = store_bereich($name);
        if (!empty($GLOBALS['store_tx'][$b])) return $fn();
        store_db($b)->exec('BEGIN IMMEDIATE'); $GLOBALS['store_tx'][$b] = true;
        try { $result = $fn(); store_commit($b); return $result; }
        catch (Throwable $e) { store_rollback($b); throw $e; }
    }
    static $held = [];
    if (!empty($held[$name])) return $fn();
    $lp = store_ordner(store_bereich($name)) . '/.' . $name . '.lock';
    $fh = @fopen($lp, 'c') ?: (is_file($lp) ? @fopen($lp, 'r') : false);   // nur echte Sperrdatei, nie z. B. ein Verzeichnis
    if (!$fh || !flock($fh, LOCK_EX)) throw new RuntimeException('Cannot lock data');
    $held[$name] = true;
    try { return $fn(); } finally { unset($held[$name]); flock($fh, LOCK_UN); fclose($fh); }
}

/* Kennzahlen für die Übersicht im Eingabebereich (beide Bereiche, soweit diese Seite sie sieht) */
function store_stats(): array
{
    $bereiche = ['haupt'];
    if (store_getrennt()) { try { store_ordner('intern'); $bereiche[] = 'intern'; } catch (StoreKeinZugang $e) { } }
    $n = 0; $bytes = 0;
    foreach ($bereiche as $b) {
        $dir = store_ordner($b);
        if (store_mode($b) === 'sqlite') {
            $path = $dir . '/.sqlite/store.sqlite';
            $n += (int)store_db($b)->query('SELECT COUNT(*) FROM documents')->fetchColumn(); $bytes += is_file($path) ? (int)filesize($path) : 0;
            continue;
        }
        $it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($dir, FilesystemIterator::SKIP_DOTS));
        foreach ($it as $f) {
            $rel = substr($f->getPathname(), strlen($dir) + 1);
            if ($f->isFile() && substr($rel, -4) === '.php' && $rel !== 'index.php' && strpos($rel, 'geo/') !== 0 && $rel[0] !== '.') { $n++; $bytes += $f->getSize(); }
        }
    }
    return ['mode' => store_mode('haupt'), 'documents' => $n, 'bytes' => $bytes, 'getrennt' => store_getrennt()];
}
