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
/* Trennstufe (Inhalt von daten/.daten-getrennt): 0 = nicht getrennt, 1 = interne Dokumente getrennt (Stufe 2a), 2 = zusätzlich
   Kundendokument geteilt, Bestand/Stammdaten, Postfächer, Vorlagen und Empfänger innen (Stufe 2b), 3 = Veröffentlichtes maßgeblich
   innen, außen nur eine Kopie (2c), 4 = Protokoll getrennt (2d), 5 = Zähler, Anmeldeversuche und Live-Verkehr je Seite (2e).
   Dokumente aus DATEN_AB_STUFE(_PRAEFIX) bleiben bis zu ihrer Stufe im gemeinsamen Ordner – ein Release allein ändert nichts;
   umgestellt wird mit deploy/daten-trennen.sh trennen (ADR-007). */
function store_stufe(): int
{
    global $DATA;
    static $s = null;
    if ($s !== null) return $s;
    $p = $DATA . '/.daten-getrennt';
    if (!is_file($p)) return $s = 0;
    $v = max(1, (int)trim((string)@file_get_contents($p)));
    // Daten weiter getrennt, als dieser Stand kennt (Rückfall ohne „zusammenfuehren“): nie still falsch lesen
    if ($v > DATEN_TRENNSTUFE) throw new RuntimeException('Daten sind weiter getrennt (Stufe ' . $v . '), als dieser Stand kennt – erst deploy/daten-trennen.sh zusammenfuehren');
    return $s = $v;
}
function store_getrennt(): bool { return store_stufe() > 0; }
function store_bereich(string $name): string
{
    if (!store_getrennt() || in_array($name, STORE_SIDECARS, true) || in_array($name, DATEN_KUNDENSEITE, true)) return 'haupt';
    if (isset(DATEN_AB_STUFE[$name]) && store_stufe() < DATEN_AB_STUFE[$name]) return 'haupt';   // zieht erst mit späterer Stufe um
    foreach (DATEN_AB_STUFE_PRAEFIX as $p => $st) {   // Muster „name/*“ (auch die Sperre unter dem Namen der Gruppe)
        if ((strncmp($name, $p, strlen($p)) === 0 || $name . '/' === $p) && store_stufe() < $st) return 'haupt';
    }
    if (in_array($name, DATEN_VEROEFFENTLICHT, true)) return store_innen() ? 'intern' : 'haupt';   // Kundenseite: nur die Kopie
    if (in_array($name, DATEN_JE_SEITE, true)) return store_innen() ? 'intern' : 'haupt';          // jede Seite ihr eigenes
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
/* Sieht dieser Server die internen Dokumente? (nicht getrennt: ja; getrennt: nur mit WA_DATEN_INTERN – Mitarbeiterseite und
   Postausgang). Die Kundenseite (getrennt, ohne WA_DATEN_INTERN) nutzt stattdessen Auszüge, z. B. den artikelauszug. */
function store_innen(): bool
{
    if (!store_getrennt()) return true;
    try { store_ordner('intern'); return true; } catch (StoreKeinZugang $e) { return false; }
}
/* ---------------- Veröffentlichte Dokumente (ADR-007 Stufe 2c, ab Trennstufe 3) ----------------
   Angebote, Einstellungen der Sicherheit, Firewall, Wartung, Fracht, Bestellfunktion …: Die Mitarbeiterseite schreibt und liest sie
   im internen Ordner und legt nach jedem Speichern eine Kopie in den gemeinsamen Ordner (store_kopie). Die Kundenseite liest nur die
   Kopie und kann sie nicht schreiben (StoreKeinZugang). Verändert sie die Kopie trotzdem (übernommene Kundenseite), merkt das der
   Postausgang beim nächsten Durchgang, stellt sie aus dem internen Stand wieder her und meldet es (store_kopien_abgleichen).
   Was die Mitarbeiterseite liest, kann die Kundenseite damit nie verändern. */
function store_veroeffentlicht(string $name): bool
{
    return store_getrennt() && in_array($name, DATEN_VEROEFFENTLICHT, true) && store_stufe() >= (DATEN_AB_STUFE[$name] ?? 1);
}
function store_schreibschutz(string $name): void
{
    if (store_veroeffentlicht($name) && !store_innen()) throw new StoreKeinZugang('Veröffentlichte Dokumente schreibt nur die Mitarbeiterseite: ' . $name);
}
/* Kopie im gemeinsamen Ordner auf den internen Stand bringen – in einer laufenden Transaktion erst nach deren Abschluss (dann
   mit dem Stand nach dem Abschluss, so gewinnt bei gleichzeitigen Änderungen immer der neueste) */
function store_kopie(string $name): void
{
    if (!empty($GLOBALS['store_tx']['intern'])) { $GLOBALS['store_kopien'][$name] = true; return; }
    $roh = store_roh($name, 'intern');
    store_roh_schreiben($name, 'haupt', $roh[0]);
}
function store_kopien_schreiben(): void
{
    $offen = array_keys($GLOBALS['store_kopien'] ?? []);
    $GLOBALS['store_kopien'] = [];
    foreach ($offen as $n) store_kopie($n);
}
/* Gespeicherter Inhalt (JSON-Text) und Zeitstempel eines Dokuments in einem bestimmten Bereich – ohne Einteilung nach Seite */
function store_roh(string $name, string $bereich): array
{
    $dir = store_ordner($bereich);
    if (store_mode($bereich) === 'sqlite') {
        $q = store_db($bereich)->prepare('SELECT payload, mtime FROM documents WHERE name = ?'); $q->execute([$name]);
        $r = $q->fetch(PDO::FETCH_NUM);
        return $r === false ? [null, null] : [(string)$r[0], (int)$r[1]];
    }
    $p = $dir . '/' . $name . '.php';
    if (!is_file($p)) return [null, null];
    $raw = (string)file_get_contents($p);
    return [strncmp($raw, GUARD, strlen(GUARD)) === 0 ? substr($raw, strlen(GUARD)) : $raw, (int)filemtime($p)];
}
function store_roh_schreiben(string $name, string $bereich, ?string $json): void
{
    $dir = store_ordner($bereich);
    if (store_mode($bereich) === 'sqlite') {
        if ($json === null) { store_db($bereich)->prepare('DELETE FROM documents WHERE name=?')->execute([$name]); return; }
        store_db($bereich)->prepare('INSERT INTO documents(name,payload,mtime) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload,mtime=excluded.mtime')->execute([$name, $json, time()]);
        return;
    }
    $p = $dir . '/' . $name . '.php';
    if ($json === null) { if (is_file($p)) @unlink($p); return; }
    $tmp = $p . '.' . bin2hex(random_bytes(4)) . '.tmp';
    if (file_put_contents($tmp, GUARD . $json, LOCK_EX) === false) throw new RuntimeException('Cannot write data');
    if (!rename($tmp, $p)) { @unlink($tmp); throw new RuntimeException('Cannot replace data'); }
}
/* Postausgang (und Mitarbeiterseite): alle Kopien mit dem internen Stand vergleichen und abweichende wiederherstellen. Rückgabe:
   wiederhergestellte Dokumente [Name => verändert durch jemand anderen?] – nachträglich geändert (Zeitstempel der Kopie deutlich
   nach dem internen Stand) heißt: nicht von der Mitarbeiterseite geschrieben. */
function store_kopien_abgleichen(): array
{
    $out = [];
    if (!store_innen() || store_stufe() < 1) return $out;
    foreach (DATEN_VEROEFFENTLICHT as $n) {
        if (!store_veroeffentlicht($n)) continue;
        $x = with_lock($n, function () use ($n) {
            [$innen, $ti] = store_roh($n, 'intern');
            [$aussen, $ta] = store_roh($n, 'haupt');
            if ($innen === $aussen || ($innen !== null && $aussen !== null && json_decode($innen, true) === json_decode($aussen, true))) return null;
            store_roh_schreiben($n, 'haupt', $innen);
            return $aussen !== null && ($innen === null || (int)$ta > (int)$ti + 5);
        });
        if ($x !== null) $out[$n] = $x;
    }
    return $out;
}
/* ---------------- Je Seite getrennte Dokumente (ADR-007 Stufe 2e, ab Trennstufe 5) ----------------
   Zähler, Anmeldeversuche, Live-Verkehr: Jede Seite schreibt ihr eigenes Dokument gleichen Namens (Kundenseite im gemeinsamen
   Ordner, Mitarbeiterseite und Postausgang innen) – store_read/store_write/with_lock wählen es selbst. Die Mitarbeiterseite liest
   das der Kundenseite zusätzlich (store_aussen_lesen, z. B. für die Übersichten der Sicherheit) und ändert es nur für das Aufheben
   einer Sperre (store_aussen_aendern). Die Kundenseite sieht die Dokumente der Mitarbeiterseite nie. */
function store_je_seite(string $name): bool
{
    return store_getrennt() && in_array($name, DATEN_JE_SEITE, true) && store_stufe() >= (DATEN_AB_STUFE[$name] ?? 1) && store_innen();
}
/* Mitarbeiterseite: Dokument der Kundenseite (null bis Trennstufe 5 – dann gibt es nur eines, das store_read schon liefert) */
function store_aussen_lesen(string $name): ?array
{
    if (!store_je_seite($name)) return null;
    $roh = store_roh($name, 'haupt')[0];
    $d = $roh === null ? null : json_decode($roh, true);
    return is_array($d) ? $d : null;
}
/* Mitarbeiterseite: Dokument der Kundenseite unter deren Sperre ändern ($fn bekommt den Inhalt und liefert den neuen) */
function store_aussen_aendern(string $name, callable $fn): void
{
    if (!store_je_seite($name)) return;
    with_lock_in('haupt', $name, function () use ($name, $fn) {
        $roh = store_roh($name, 'haupt')[0];
        $alt = $roh === null ? [] : (json_decode($roh, true) ?: []);
        $neu = $fn($alt);
        if ($neu !== $alt) store_roh_schreiben($name, 'haupt', json_encode($neu, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
    });
}
/* Kann dieser Server das Dokument lesen? (Kundenseite: nur Dokumente im gemeinsamen Ordner – je nach Trennstufe) */
function store_sichtbar(string $name): bool { return store_bereich($name) === 'haupt' || store_innen(); }
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
    store_schreibschutz($name);
    if (store_sql($name)) {
        $q = store_db(store_bereich($name))->prepare('INSERT INTO documents(name,payload,mtime) VALUES(?,?,?) ON CONFLICT(name) DO UPDATE SET payload=excluded.payload,mtime=excluded.mtime');
        $q->execute([$name, $json, time()]);
        if (store_veroeffentlicht($name)) store_kopie($name);
        return;
    }
    $dir = dirname(store_path($name));
    if (!is_dir($dir) && !mkdir($dir, 0775, true)) throw new RuntimeException('Cannot create storage directory');
    $tmp = store_path($name) . '.' . bin2hex(random_bytes(4)) . '.tmp';
    if (file_put_contents($tmp, GUARD . $json, LOCK_EX) === false) throw new RuntimeException('Cannot write data');
    if (!rename($tmp, store_path($name))) { @unlink($tmp); throw new RuntimeException('Cannot replace data'); }
    if (store_veroeffentlicht($name)) store_kopie($name);
}
function store_delete(string $name): void
{
    store_schreibschutz($name);
    if (store_sql($name)) { $q = store_db(store_bereich($name))->prepare('DELETE FROM documents WHERE name=?'); $q->execute([$name]); }
    else { $p = store_path($name); if (is_file($p) && !unlink($p)) throw new RuntimeException('Cannot delete data'); }
    if (store_veroeffentlicht($name)) store_kopie($name);
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
        if ($b === 'intern' && !empty($GLOBALS['store_kopien'])) store_kopien_schreiben();   // Kopien veröffentlichter Dokumente
    }
}
function store_rollback(?string $bereich = null): void
{
    foreach (array_keys($GLOBALS['store_tx'] ?? []) as $b) {
        if ($bereich !== null && $b !== $bereich) continue;
        store_db($b)->exec('ROLLBACK'); unset($GLOBALS['store_tx'][$b]);
        if ($b === 'intern') $GLOBALS['store_kopien'] = [];
    }
    $GLOBALS['notify_queue'] = [];   // vorgemerkte Benachrichtigungen gehören zu verworfenen Änderungen
}
function with_lock(string $name, callable $fn)
{
    store_schreibschutz($name);   // Kundenseite sperrt (und schreibt) veröffentlichte Dokumente nie
    store_path($name);            // Name prüfen (und Prüfhilfe)
    return with_lock_in(store_bereich($name), $name, $fn);
}
/* Sperre bzw. Transaktion eines Dokuments in einem bestimmten Bereich (with_lock wählt den Bereich nach der Einteilung) */
function with_lock_in(string $b, string $name, callable $fn)
{
    if (!in_array($name, STORE_SIDECARS, true) && store_mode($b) === 'sqlite') {
        if (!empty($GLOBALS['store_tx'][$b])) return $fn();
        store_db($b)->exec('BEGIN IMMEDIATE'); $GLOBALS['store_tx'][$b] = true;
        try { $result = $fn(); store_commit($b); return $result; }
        catch (Throwable $e) { store_rollback($b); throw $e; }
    }
    static $held = [];
    if (!empty($held[$b . '|' . $name])) return $fn();
    $lp = store_ordner($b) . '/.' . $name . '.lock';
    $fh = @fopen($lp, 'c') ?: (is_file($lp) ? @fopen($lp, 'r') : false);   // nur echte Sperrdatei, nie z. B. ein Verzeichnis
    if (!$fh || !flock($fh, LOCK_EX)) throw new RuntimeException('Cannot lock data');
    $held[$b . '|' . $name] = true;
    try { return $fn(); } finally { unset($held[$b . '|' . $name]); flock($fh, LOCK_UN); fclose($fh); }
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
    return ['mode' => store_mode('haupt'), 'documents' => $n, 'bytes' => $bytes, 'getrennt' => store_getrennt(), 'trennstufe' => store_stufe()];
}
