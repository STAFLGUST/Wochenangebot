<?php
declare(strict_types=1);
/* Dateiprüfung (wie ein Datei-Scanner gegen Schadcode): vergleicht die Programmdateien mit der Prüfliste der
   freigegebenen Fassung (integritaet-liste.php, beim Einspielen aus dem freigegebenen Commit erzeugt von
   deploy/bereitstellen.py; Wert = SHA-256 oder bei HTML-Seiten [mit, ohne Versionsnummern]), meldet unbekannte Dateien,
   prüft den Datenordner (Sperrzeile, ausführbare Dateien, Schutz des Datenbankordners; Dateien der Dateiablage
   data/dateien/<bereich>/<xx>/<id>.bin sind erwartet) und sucht in unbekannten bzw.
   veränderten Dateien und in gespeicherten Daten nach typischen Mustern von Hintertüren, Schadcode und Link-Spam.
   Dazu eine Übersicht der Komponenten (PHP, SQLite, OpenSSL, eingebundene Bibliotheken). Nur lesend, keine Dienste
   im Internet; es werden nie Dateiinhalte ausgegeben. Ergebnis im Dokument „integritaet“ (letzter Lauf + Verlauf). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const INTEGRITAET_MAX_BYTES = 2097152;     // größere Dateien werden nur per Prüfsumme verglichen, nicht durchsucht
const INTEGRITAET_MAX_DATEIEN = 5000;
const INTEGRITAET_ZEIT = 20.0;             // Sekunden; danach wird abgebrochen (Ergebnis als unvollständig markiert)
const INTEGRITAET_MAX_EINTRAEGE = 500;     // gespeicherte/ausgelieferte Befunde je Lauf
const INTEGRITAET_VERLAUF = 20;
const INTEGRITAET_AUTO_STUNDEN = 24;       // älter → beim Öffnen der Sicherheitsansicht automatisch prüfen (höchstens 1× am Tag)
const INTEGRITAET_STUFEN = ['kritisch' => 3, 'warnung' => 2, 'hinweis' => 1];
/* Ende der Sicherheitsupdates je PHP-Version (php.net/supported-versions, Stand Oktober 2026) */
const PHP_SUPPORT_ENDE = ['7.4' => '2022-11-28', '8.0' => '2023-11-26', '8.1' => '2025-12-31', '8.2' => '2026-12-31', '8.3' => '2027-12-31', '8.4' => '2028-12-31', '8.5' => '2029-12-31'];
/* Vom Webserver oder der Shell ausführbare Dateien */
/* Nur sperrende Zugriffsregeln (.htaccess im Datenordner und im Datenbankordner): jede Zeile ist leer, Kommentar,
   „Require all denied“, „Deny from all“, „Order allow,deny“/„Order deny,allow“ oder ein <IfModule>-Rahmen; mindestens
   eine Sperrzeile. Alles andere (z. B. AddHandler, php_value, Rewrite, Allow) gilt als verändert. */
function integritaet_nur_sperre(string $t): bool
{
    $sperre = false;
    foreach (preg_split('/\R/', $t) ?: [] as $z) {
        $z = trim($z);
        if ($z === '' || $z[0] === '#') continue;
        if (preg_match('~^(?:Require\s+all\s+denied|Deny\s+from\s+all)$~i', $z)) { $sperre = true; continue; }
        if (preg_match('~^(?:Order\s+(?:allow,deny|deny,allow)|<IfModule\s+!?[A-Za-z0-9_.]+>|</IfModule>)$~i', $z)) continue;
        return false;
    }
    return $sperre;
}
/* Merkdatei der Proxy-Adressen (proxy_adressen_merken in lib/protokoll.php): nur eine JSON-Liste von IP-Adressen */
const INTEGRITAET_PROXY_DATEI = '~^wa-proxy-[46]-[0-9a-f]{64}\.json$~';
function integritaet_proxy_ok(?string $t): bool
{
    if ($t === null || strlen($t) > 4096) return false;
    $j = json_decode($t, true);
    if (!is_array($j) || !array_is_list($j) || count($j) > 64) return false;
    foreach ($j as $x) if (!is_string($x) || filter_var($x, FILTER_VALIDATE_IP) === false) return false;
    return true;
}
/* Dateiablage (lib/dateiablage.php): hochgeladene Dateien der Module unter data/dateien/<bereich>/<xx>/<id>.bin – erwartet;
   nie ausgeführt (data/ liefert der Webserver nicht aus), Inhalt beliebig (PDF, Word …), daher nicht nach Mustern durchsucht */
const INTEGRITAET_ABLAGE = '~^dateien/[a-z][a-z0-9-]{1,30}/[a-z0-9]{2}/[a-z0-9]{12,40}\\.bin$~';
const INTEGRITAET_AUSFUEHRBAR = '~\.(?:php\d?|phtml|phar|pht|phps|inc|cgi|pl|py|sh|bash|shtml)$|(?:^|/)\.(?:htaccess|htpasswd|user\.ini)$~i';
/* Muster: [Bezeichnung, regulärer Ausdruck, Stufe, Dateiarten (php = PHP-Dateien, web = JS/HTML/SVG, conf = .htaccess/.user.ini,
   daten = gespeicherte Dokumente)]. Die Ausdrücke sind so geschrieben, dass sie nicht auf diese Datei selbst passen. */
const INTEGRITAET_MUSTER = [
    ['eval mit verschleiertem Code', '~\b(?:eval|assert)\s*\(\s*@?\s*(?:base64_decode|gzinflate|gzuncompress|gzdecode|str_rot13|hex2bin|convert_uudecode)\s*\(~i', 'kritisch', 'php daten'],
    ['Entpacken und Ausführen (gzinflate/base64)', '~\b(?:gzinflate|gzuncompress|gzdecode|str_rot13)\s*\(\s*base64_decode\s*\(~i', 'kritisch', 'php daten'],
    ['Ausführung von Eingaben (eval/assert)', '~\b(?:eval|assert|create_function)\s*\(\s*@?\s*\$_(?:GET|POST|REQUEST|COOKIE|SERVER|FILES)\b~i', 'kritisch', 'php daten'],
    ['Systembefehl mit Eingabe', '~\b(?:system|exec|shell_exec|passthru|popen|proc_open|pcntl_exec)\s*\(\s*@?\s*\$_(?:GET|POST|REQUEST|COOKIE|SERVER)\b~i', 'kritisch', 'php daten'],
    ['Eingabe als Funktion aufgerufen', '~\$_(?:GET|POST|REQUEST|COOKIE)\s*\[[^\]]{0,40}\]\s*\(~i', 'kritisch', 'php daten'],
    ['preg_replace mit /e (Codeausführung)', '~preg_replace\s*\(\s*([\'"])([^\w\s\\\\]).{0,300}?\2[imsxuADSUXJ]*e[imsxuADSUXJ]*\1~s', 'kritisch', 'php daten'],
    ['Systembefehle (shell_exec, passthru …)', '~\b(?:shell_exec|passthru|proc_open|popen|pcntl_exec)\s*\(~i', 'warnung', 'php'],
    ['create_function', '~\bcreate_function\s*\(~i', 'warnung', 'php'],
    ['Lange Base64-Nutzlast', '~base64_decode\s*\(\s*[\'"][A-Za-z0-9+/=\s]{300,}~', 'warnung', 'php daten'],
    ['Bekannte Web-Shell', '~\b(?:Files[M]an|b37[4]k|c9[9]shell|r5[7]shell|WSOset[c]ookie|wso_ver[s]ion|IndoX[p]loit|AnonymousF[o]x)\b~i', 'kritisch', 'php web daten'],
    ['document.write mit unescape', '~document\.write\s*\(\s*unescape\s*\(~i', 'kritisch', 'php web daten'],
    ['Krypto-Miner', '~\b(?:coin-?[h]ive|cryptono[i]ght|crypto-?lo[o]t|webmine[p]ool|jseco[i]n|deepmi[n]er|miner[o]\.cc|coin[i]mp)\b~i', 'kritisch', 'php web daten'],
    ['Fremdes Skript in gespeicherten Daten', '~<script\b[^>]*\bsrc\s*=\s*[\'"]?\s*(?:https?:)?//~i', 'kritisch', 'daten'],
    ['Fremdes Skript eingebunden', '~<script\b[^>]*\bsrc\s*=\s*[\'"]?\s*(?:https?:)?//~i', 'warnung', 'php web'],
    ['Eingebettete fremde Seite (iframe)', '~<iframe\b[^>]*\bsrc\s*=\s*[\'"]?\s*(?:https?:)?//~i', 'warnung', 'php web daten'],
    ['Skript in gespeicherten Daten', '~<script\b|\bjavascript\s*:|\bon(?:error|load|mouseover)\s*=~i', 'warnung', 'daten'],
    ['PHP-Code in gespeicherten Daten', '~<\?(?:php|=)~i', 'warnung', 'daten'],
    ['Verschleierter Code (fromCharCode-Kette)', '~fromCharCode\s*\(\s*\d+(?:\s*,\s*\d+){15,}|(?:fromCharCode\s*\([^()]{1,20}\)\s*\+\s*){4,}~i', 'warnung', 'php web daten'],
    ['PHP-Ausführung umgeleitet (.htaccess)', '~\b(?:auto_(?:prepend|append)_file|(?:AddType|AddHandler|SetHandler)\s+application/x-httpd-php)~i', 'kritisch', 'conf'],
];

/* Dateiart für die Musterprüfung (null = nicht durchsuchen, z. B. Bilder) */
function integritaet_art(string $pfad): ?string
{
    if (preg_match('~\.(?:php\d?|phtml|phar|pht|inc)$~i', $pfad)) return 'php';
    if (preg_match('~\.(?:js|mjs|html?|svg|xml|json|css|txt)$~i', $pfad)) return 'web';
    if (preg_match('~(?:^|/)\.(?:htaccess|user\.ini)$~i', $pfad)) return 'conf';
    return null;
}
/* Muster in einem Text: [Bezeichnungen, höchste Stufe] */
function integritaet_muster(string $text, string $art): array
{
    $treffer = []; $stufe = '';
    foreach (INTEGRITAET_MUSTER as [$label, $re, $lvl, $arten]) {
        if (!in_array($art, explode(' ', $arten), true) || isset($treffer[$label])) continue;
        if (preg_match($re, $text) === 1) { $treffer[$label] = true; if (INTEGRITAET_STUFEN[$lvl] > (INTEGRITAET_STUFEN[$stufe] ?? 0)) $stufe = $lvl; }
    }
    // Versteckte Linksammlung (SEO-Spam): unsichtbarer Bereich mit mindestens fünf Links auf fremde Seiten
    if ($art !== 'conf' && preg_match_all('~display\s*:\s*none|visibility\s*:\s*hidden~i', $text, $m, PREG_OFFSET_CAPTURE)) {
        foreach (array_slice($m[0], 0, 50) as [, $pos]) {
            if (preg_match_all('~<a\s[^>]*href\s*=\s*[\'"]?\s*https?://~i', substr($text, (int)$pos, 3000)) >= 5) {
                $treffer['Versteckte Links (SEO-Spam)'] = true;
                if (INTEGRITAET_STUFEN['warnung'] > (INTEGRITAET_STUFEN[$stufe] ?? 0)) $stufe = 'warnung';
                break;
            }
        }
    }
    return [array_keys($treffer), $stufe];
}
function integritaet_liste(): ?array
{
    $f = __DIR__ . '/integritaet-liste.php';
    if (!is_file($f)) return null;
    $l = require $f;
    return is_array($l) ? $l : null;
}

/* Eine vollständige Prüfung; Ergebnis ohne Dateiinhalte */
function integritaet_pruefen(): array
{
    global $DATA;
    $t0 = microtime(true);
    $root = dirname(__DIR__, 2);
    $dataReal = realpath($DATA) ?: $DATA;
    $items = []; $n = 0; $abbruch = '';
    $c = ['checked' => 0, 'modified' => 0, 'missing' => 0, 'unknown' => 0, 'suspicious' => 0, 'data' => 0, 'critical' => 0, 'warnings' => 0, 'hints' => 0];
    $add = function (string $path, string $art, string $stufe, string $text, array $sig = [], string $sigStufe = '') use (&$items) {
        if ($sigStufe !== '' && INTEGRITAET_STUFEN[$sigStufe] > INTEGRITAET_STUFEN[$stufe]) $stufe = $sigStufe;
        $it = ['path' => $path, 'art' => $art, 'stufe' => $stufe, 'text' => $text];
        if ($sig) $it['signatur'] = implode(', ', $sig);
        $items[] = $it;
    };
    $grenze = function () use (&$n, &$abbruch, $t0): bool {
        if ($abbruch !== '') return true;
        if ($n >= INTEGRITAET_MAX_DATEIEN) $abbruch = 'Höchstzahl von ' . INTEGRITAET_MAX_DATEIEN . ' Dateien erreicht';
        elseif (microtime(true) - $t0 > INTEGRITAET_ZEIT) $abbruch = 'Zeitgrenze von ' . (int)INTEGRITAET_ZEIT . ' Sekunden erreicht';
        return $abbruch !== '';
    };
    $lesen = function (string $abs): ?string { $sz = @filesize($abs); return $sz !== false && $sz <= INTEGRITAET_MAX_BYTES ? (string)@file_get_contents($abs) : null; };

    /* 1. Freigegebene Dateien: fehlt / verändert */
    $liste = integritaet_liste();
    if ($liste === null) {
        $add('api/lib/integritaet-liste.php', 'fehlt', 'kritisch', 'Prüfliste fehlt – Programmdateien können nicht verglichen werden');
        $liste = [];
    }
    foreach ($liste as $rel => $hash) {
        if ($grenze()) break;
        $n++; $c['checked']++;
        $abs = $root . '/' . $rel;
        if (!is_file($abs)) { $c['missing']++; $add($rel, 'fehlt', 'warnung', 'Datei der freigegebenen Fassung fehlt'); continue; }
        $ist = (string)hash_file('sha256', $abs);   // HTML-Seiten: zwei zulässige Fassungen (mit/ohne Versionsnummern)
        if (!array_filter((array)$hash, function ($h) use ($ist) { return is_string($h) && hash_equals($h, $ist); })) {
            $c['modified']++;
            $art = integritaet_art($rel); $txt = $art ? $lesen($abs) : null;
            [$sig, $ss] = $txt !== null ? integritaet_muster($txt, $art) : [[], ''];
            $add($rel, 'geaendert', preg_match(INTEGRITAET_AUSFUEHRBAR, $rel) ? 'kritisch' : 'warnung', 'Inhalt weicht von der freigegebenen Fassung ab', $sig, $ss);
        }
    }

    /* 2. Unbekannte Dateien im Programmordner (ohne Datenordner) */
    $dirs = new RecursiveCallbackFilterIterator(new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS),
        function (SplFileInfo $f) use ($root, $dataReal) {
            if (!$f->isDir()) return true;
            $p = $f->getPathname();
            return $p !== $root . '/data' && (realpath($p) ?: $p) !== $dataReal;
        });
    foreach (new RecursiveIteratorIterator($dirs) as $f) {
        if ($grenze()) break;
        if ($f->isDir()) continue;
        $rel = str_replace('\\', '/', substr($f->getPathname(), strlen($root) + 1));
        if (isset($liste[$rel]) || $rel === 'api/lib/integritaet-liste.php') continue;
        $n++; $c['checked']++; $c['unknown']++;
        $exe = preg_match(INTEGRITAET_AUSFUEHRBAR, $rel) === 1;
        $art = integritaet_art($rel); $txt = $art && !$f->isLink() ? $lesen($f->getPathname()) : null;
        [$sig, $ss] = $txt !== null ? integritaet_muster($txt, $art) : [[], ''];
        $add($rel, 'unbekannt', $exe ? 'kritisch' : 'warnung', $exe ? 'Unbekannte ausführbare Datei – nicht Teil der freigegebenen Fassung' : 'Unbekannte Datei – nicht Teil der freigegebenen Fassung', $sig, $ss);
    }

    /* 3. Datenordner: nur Datensätze mit Sperrzeile, keine ausführbaren Dateien, Schutz des Datenbankordners */
    $sqlite = is_file($DATA . '/.sqlite-active');
    if (is_dir($DATA)) {
        $dd = new RecursiveCallbackFilterIterator(new RecursiveDirectoryIterator($DATA, FilesystemIterator::SKIP_DOTS),
            function (SplFileInfo $f) use ($DATA) {
                if (!$f->isDir()) return true;
                $b = $f->getFilename();
                return substr($f->getPathname(), strlen($DATA) + 1) !== '.sqlite' && strpos($b, '.sqlite-stage-') !== 0 && strpos($b, '.export-') !== 0;
            });
        foreach (new RecursiveIteratorIterator($dd) as $f) {
            if ($grenze()) break;
            if ($f->isDir()) continue;
            $rel = str_replace('\\', '/', substr($f->getPathname(), strlen($DATA) + 1));
            $base = $f->getFilename();
            $path = 'data/' . $rel;
            if (substr($base, -4) === '.tmp' || ($base[0] === '.' && substr($base, -5) === '.lock') || $rel === '.sqlite-active') continue;   // Zwischendateien, Sperren, Schalter
            $n++; $c['checked']++;
            if (preg_match(INTEGRITAET_ABLAGE, $rel)) continue;   // Dateiablage der Module
            if (substr($base, -4) === '.php') {
                $fh = @fopen($f->getPathname(), 'rb'); $head = $fh ? (string)fread($fh, 128) : ''; if ($fh) fclose($fh);
                if ($rel === 'index.php') {
                    $ok = strncmp($head, GUARD, strlen(GUARD)) === 0 || trim($head) === '<?php http_response_code(404); exit;';
                    if (!$ok) { $c['data']++; $add($path, 'daten', 'kritisch', 'Sperrdatei des Datenordners enthält anderen PHP-Code'); }
                    continue;
                }
                if (strpos($rel, 'geo/') === 0 && substr($base, -8) === '.dat.php') {
                    if (strncmp($head, GEO_GUARD, strlen(GEO_GUARD)) !== 0) { $c['data']++; $add($path, 'daten', 'kritisch', 'Länder-/Ortsdaten ohne Zugriffssperre (anderer PHP-Code)'); }
                    continue;
                }
                if (strncmp($head, GUARD, strlen(GUARD)) !== 0) { $c['data']++; $add($path, 'daten', 'kritisch', 'Datensatz ohne Zugriffssperre – enthält ausführbaren PHP-Code'); continue; }
                $raw = $lesen($f->getPathname());
                if ($raw === null) continue;
                [$sig, $ss] = integritaet_muster(str_replace(['\\"', '\\/'], ['"', '/'], substr($raw, strlen(GUARD))), 'daten');
                if ($sig) { $c['suspicious']++; $add($path, 'verdaechtig', $ss, 'Auffälliges Muster in gespeicherten Daten', $sig); }
                continue;
            }
            // Zugriffssperre im Datenordner (z. B. aus der Zeit vor Docker): erlaubt, solange sie nur sperrt
            if ($rel === '.htaccess') {
                if (integritaet_nur_sperre((string)$lesen($f->getPathname()))) continue;
                $c['data']++; $add($path, 'daten', 'kritisch', 'Zugriffsregeln im Datenordner (.htaccess) enthalten mehr als eine Sperre');
                continue;
            }
            // Proxy-Merkdatei der Anwendung: erwartet, solange sie nur IP-Adressen enthält
            if (preg_match(INTEGRITAET_PROXY_DATEI, $rel)) {
                if (integritaet_proxy_ok($lesen($f->getPathname()))) continue;
                $c['data']++; $add($path, 'daten', 'warnung', 'Merkdatei der Proxy-Adressen mit unerwartetem Inhalt');
                continue;
            }
            $c['data']++;
            if (preg_match(INTEGRITAET_AUSFUEHRBAR, $rel)) $add($path, 'daten', 'kritisch', 'Ausführbare Datei im Datenordner');
            else $add($path, 'daten', 'hinweis', 'Unerwartete Datei im Datenordner');
        }
        // Datenbankordner: nur die Datenbank selbst und eine sperrende .htaccess
        if (is_dir($DATA . '/.sqlite')) {
            foreach (scandir($DATA . '/.sqlite') ?: [] as $b) {
                if ($b === '.' || $b === '..' || preg_match('~^store\.sqlite(?:-wal|-shm|-journal)?$~', $b) || $b === '.htaccess') continue;
                $n++; $c['checked']++; $c['data']++;
                $add('data/.sqlite/' . $b, 'daten', preg_match(INTEGRITAET_AUSFUEHRBAR, $b) || is_dir($DATA . '/.sqlite/' . $b) ? 'kritisch' : 'hinweis', 'Unerwartete Datei im Datenbankordner');
            }
            $ht = $DATA . '/.sqlite/.htaccess';
            if (is_file($ht)) {
                $n++; $c['checked']++;
                $t = (string)@file_get_contents($ht, false, null, 0, 4096);
                if (!integritaet_nur_sperre($t)) {
                    $c['data']++; $add('data/.sqlite/.htaccess', 'daten', 'kritisch', 'Zugriffssperre des Datenbankordners verändert');
                }
            } elseif ($sqlite) { $c['data']++; $add('data/.sqlite/.htaccess', 'daten', 'warnung', 'Zugriffssperre des Datenbankordners (.htaccess) fehlt'); }
        }
    }
    /* 4. Datensätze in der Datenbank durchsuchen */
    if ($sqlite && $abbruch === '') {
        try {
            $q = store_db()->query('SELECT name, length(payload) AS n FROM documents ORDER BY name');
            $one = store_db()->prepare('SELECT payload FROM documents WHERE name = ?');
            foreach ($q->fetchAll(PDO::FETCH_ASSOC) as $r) {
                if ($grenze()) break;
                $n++; $c['checked']++;
                if ((int)$r['n'] > INTEGRITAET_MAX_BYTES) continue;
                $one->execute([$r['name']]);
                [$sig, $ss] = integritaet_muster(str_replace(['\\"', '\\/'], ['"', '/'], (string)$one->fetchColumn()), 'daten');
                if ($sig) { $c['suspicious']++; $add('datenbank/' . $r['name'], 'verdaechtig', $ss, 'Auffälliges Muster in gespeicherten Daten', $sig); }
            }
        } catch (Throwable $e) {
            error_log('[wochenangebot] Dateiprüfung: ' . $e->getMessage());
            $add('data/.sqlite/store.sqlite', 'daten', 'warnung', 'Datenbank konnte nicht durchsucht werden');
        }
    }

    usort($items, function ($a, $b) { return INTEGRITAET_STUFEN[$b['stufe']] <=> INTEGRITAET_STUFEN[$a['stufe']] ?: strcmp($a['path'], $b['path']); });
    foreach ($items as $it) $c[['kritisch' => 'critical', 'warnung' => 'warnings', 'hinweis' => 'hints'][$it['stufe']]]++;
    $comp = integritaet_komponenten($root);
    return ['ok' => $c['critical'] === 0 && $c['warnings'] === 0, 'ranAt' => now(), 'ms' => (int)round((microtime(true) - $t0) * 1000),
            'counts' => $c, 'items' => array_slice($items, 0, INTEGRITAET_MAX_EINTRAEGE), 'truncated' => max(0, count($items) - INTEGRITAET_MAX_EINTRAEGE),
            'partial' => $abbruch !== '', 'partialText' => $abbruch, 'manifest' => count($liste), 'storage' => $sqlite ? 'sqlite' : 'files', 'components' => $comp];
}

/* Komponenten mit Version und Stand der Sicherheitsupdates (ohne Abfrage im Internet) */
function integritaet_komponenten(string $root): array
{
    $out = [];
    $mm = PHP_MAJOR_VERSION . '.' . PHP_MINOR_VERSION;
    $ende = PHP_SUPPORT_ENDE[$mm] ?? null;
    if ($ende) {
        $tage = (int)floor((strtotime($ende . 'T23:59:59Z') - time()) / 86400);
        $datum = date('d.m.Y', strtotime($ende . 'T12:00:00Z'));
        if ($tage < 0) $out[] = ['name' => 'PHP', 'version' => PHP_VERSION, 'stufe' => 'kritisch', 'text' => "Keine Sicherheitsupdates mehr seit {$datum} – auf eine aktuelle PHP-Version umstellen (Container-Image)."];
        elseif ($tage < 180) $out[] = ['name' => 'PHP', 'version' => PHP_VERSION, 'stufe' => 'warnung', 'text' => "Sicherheitsupdates nur noch bis {$datum} ({$tage} Tage) – Umstieg planen."];
        else $out[] = ['name' => 'PHP', 'version' => PHP_VERSION, 'stufe' => 'ok', 'text' => "Sicherheitsupdates bis {$datum}."];
    } else {
        $alt = version_compare($mm, array_key_first(PHP_SUPPORT_ENDE), '<');
        $out[] = ['name' => 'PHP', 'version' => PHP_VERSION, 'stufe' => $alt ? 'kritisch' : 'hinweis', 'text' => $alt ? 'Veraltete Version ohne Sicherheitsupdates.' : 'Unterstützungsende nicht hinterlegt (neuere Version).'];
    }
    if (!empty($_SERVER['SERVER_SOFTWARE'])) $out[] = ['name' => 'Webserver', 'version' => mb_substr((string)$_SERVER['SERVER_SOFTWARE'], 0, 60), 'stufe' => 'ok', 'text' => PHP_SAPI];
    if (extension_loaded('pdo_sqlite')) {
        try { $v = (string)(new PDO('sqlite::memory:'))->query('SELECT sqlite_version()')->fetchColumn(); } catch (Throwable $e) { $v = '?'; }
        $out[] = ['name' => 'SQLite', 'version' => $v, 'stufe' => 'ok', 'text' => store_mode() === 'sqlite' ? 'Datenablage in der Datenbank' : 'verfügbar (Datenablage in Dateien)'];
    }
    if (defined('OPENSSL_VERSION_TEXT')) {
        $v = trim(preg_replace('~^OpenSSL\s+~i', '', OPENSSL_VERSION_TEXT) ?? '');
        $alt = preg_match('~^(\d+)\.~', $v, $m) && (int)$m[1] < 3;
        $out[] = ['name' => 'OpenSSL', 'version' => $v, 'stufe' => $alt ? 'warnung' : 'ok', 'text' => $alt ? 'Version 1.x erhält keine Sicherheitsupdates mehr.' : 'Updates kommen mit dem Container-Image.'];
    }
    foreach (glob($root . '/assets/vendor/*.{js,css}', GLOB_BRACE) ?: [] as $f) {
        $head = (string)@file_get_contents($f, false, null, 0, 4096);
        $name = basename($f);
        foreach (preg_split('~\R~', $head) ?: [] as $line) {
            $t = trim(preg_replace('~^\s*(?:/\*+!?|\*+|//+)~', '', $line) ?? '');
            if (preg_match('~[A-Za-z]{3}~', $t) && !preg_match('~^(?:copyright|licen[cs]ed|url|https?:|@license)~i', $t)) { $name = mb_substr(trim($t, " */"), 0, 60); break; }
        }
        $ver = preg_match('~(?:@version|\bversion\b)[\s:=\'"v]*(\d+\.\d+(?:\.\d+)?)|\bv(\d+\.\d+\.\d+)\b|@(\d+\.\d+\.\d+)~i', $head, $m) ? ($m[1] ?: ($m[2] ?? '') ?: ($m[3] ?? '')) : '';
        $out[] = ['name' => $name, 'version' => $ver !== '' ? $ver : '–', 'stufe' => $ver !== '' ? 'ok' : 'hinweis', 'file' => 'assets/vendor/' . basename($f),
                  'text' => ($ver !== '' ? '' : 'Version im Dateikopf nicht angegeben; ') . 'Prüfsumme ' . substr((string)hash_file('sha256', $f), 0, 12) . ' (über die Prüfliste überwacht).'];
    }
    return $out;
}

/* Neue Befunde (kritisch/Warnung) gegenüber dem vorigen Lauf */
function integritaet_neu(?array $prev, array $r): array
{
    $key = function ($x) { return $x['path'] . '|' . $x['art'] . '|' . ($x['signatur'] ?? ''); };
    $alt = [];
    foreach ((array)($prev['items'] ?? []) as $x) if (is_array($x) && isset($x['path'], $x['art'])) $alt[$key($x)] = true;
    return array_values(array_filter($r['items'], function ($x) use ($alt, $key) { return $x['stufe'] !== 'hinweis' && !isset($alt[$key($x)]); }));
}

/* Prüfung ausführen, speichern (letzter Lauf + kurzer Verlauf) und bei neuen Befunden benachrichtigen */
function integritaet_lauf(bool $auto, ?array $me): array
{
    @set_time_limit(60);
    $r = integritaet_pruefen() + ['auto' => $auto, 'by' => $auto ? '' : (string)($me['username'] ?? '')];
    $prev = with_lock('integritaet', function () use ($r) {
        $d = store_read('integritaet') ?? [];
        $prev = is_array($d['last'] ?? null) ? $d['last'] : null;
        $h = is_array($d['history'] ?? null) ? $d['history'] : [];
        $h[] = ['ranAt' => $r['ranAt'], 'ms' => $r['ms'], 'auto' => $r['auto'], 'by' => $r['by'], 'ok' => $r['ok'], 'counts' => $r['counts']];
        $d['last'] = $r;
        $d['history'] = array_slice($h, -INTEGRITAET_VERLAUF);
        store_write('integritaet', $d);
        return $prev;
    });
    $neu = integritaet_neu($prev, $r);
    if ($neu) {
        $k = count(array_filter($neu, function ($x) { return $x['stufe'] === 'kritisch'; }));
        $facts = [['Neu kritisch', (string)$k], ['Neu Warnungen', (string)(count($neu) - $k)],
                  ['Insgesamt', "{$r['counts']['critical']} kritisch, {$r['counts']['warnings']} Warnungen, {$r['counts']['checked']} Dateien/Datensätze geprüft"],
                  ['Ausgelöst', $auto ? 'automatische Prüfung' : 'Prüfung durch ' . ($me['name'] ?? $me['username'] ?? '')]];
        foreach (array_slice($neu, 0, 5) as $x) $facts[] = [$x['stufe'] === 'kritisch' ? 'Kritisch' : 'Warnung', $x['path'] . ' – ' . $x['text'] . (isset($x['signatur']) ? ' (' . $x['signatur'] . ')' : '')];
        if (count($neu) > 5) $facts[] = ['…', (count($neu) - 5) . ' weitere (Sicherheit → Dateiprüfung)'];
        notify('sicherheit', 'Dateiprüfung: ' . count($neu) . ' neue ' . (count($neu) === 1 ? 'Auffälligkeit' : 'Auffälligkeiten'), $facts);
    }
    return $r;
}

/* Gespeicherter Stand; ist der letzte Lauf älter als 24 Stunden, wird höchstens einmal am Tag automatisch geprüft */
function integritaet_stand(bool $autoErlaubt = true): array
{
    $d = store_read('integritaet') ?? [];
    $last = is_array($d['last'] ?? null) ? $d['last'] : null;
    $alt = !$last || strtotime((string)($last['ranAt'] ?? '')) < time() - INTEGRITAET_AUTO_STUNDEN * 3600;
    $heute = gmdate('Y-m-d');
    if ($autoErlaubt && $alt && ($d['autoDay'] ?? '') !== $heute) {
        $los = with_lock('integritaet', function () use ($heute) {
            $d = store_read('integritaet') ?? [];
            if (($d['autoDay'] ?? '') === $heute) return false;
            $d['autoDay'] = $heute;
            store_write('integritaet', $d);
            return true;
        });
        if ($los) { integritaet_lauf(true, null); $d = store_read('integritaet') ?? []; }
    }
    return ['result' => is_array($d['last'] ?? null) ? $d['last'] : null, 'history' => array_reverse(is_array($d['history'] ?? null) ? $d['history'] : [])];
}
