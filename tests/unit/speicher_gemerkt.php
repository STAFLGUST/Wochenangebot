<?php
/* Gemerktes Lesen der Speicherschicht (store_read_gemerkt in app/api/storage.php), ohne Server, in der Speicherart des
   Datenordners (Dateien oder SQLite – tests/unit/test_speicher_gemerkt.py prüft beide): innerhalb einer Anfrage wird das
   Dokument einmal gelesen; eigenes Schreiben und Löschen, jede Sperre (Beginn und Ende, auch nach einem Fehler) vergessen das
   Gemerkte; innerhalb einer Sperre gilt immer der aktuelle Stand – auch wenn ein anderer Prozess inzwischen geschrieben hat.
   Aufruf: DATA_DIR=<leerer Testordner> php tests/unit/speicher_gemerkt.php */
declare(strict_types=1);
$DATA = (string)getenv('DATA_DIR');
if ($DATA === '' || !is_dir($DATA)) { fwrite(STDERR, "DATA_DIR fehlt\n"); exit(2); }
require __DIR__ . '/../../app/api/storage.php';
function check(string $name, bool $ok, $wert = null): void
{
    if (!$ok) { fwrite(STDERR, "FAIL $name " . json_encode($wert, JSON_UNESCAPED_UNICODE) . "\n"); exit(1); }
    echo "PASS $name\n";
}
/* Ein anderer Prozess (wie eine zweite Anfrage) schreibt das Dokument */
function fremd_schreiben(array $d): void
{
    $code = '$DATA = getenv("DATA_DIR"); require ' . var_export(__DIR__ . '/../../app/api/storage.php', true) . ';'
          . ' with_lock("angebote", function () { store_write("angebote", json_decode(getenv("DOK"), true)); });';
    $cmd = 'DATA_DIR=' . escapeshellarg($GLOBALS['DATA']) . ' DOK=' . escapeshellarg(json_encode($d)) . ' ' . escapeshellarg(PHP_BINARY) . ' -r ' . escapeshellarg($code);
    exec($cmd, $aus, $rc);
    if ($rc !== 0) { fwrite(STDERR, "FAIL fremder Prozess: " . implode("\n", $aus) . "\n"); exit(1); }
}
$a = ['offers' => [['id' => 'a']]]; $b = ['offers' => [['id' => 'b']]]; $c = ['offers' => [['id' => 'c']]];
echo 'Speicherart: ' . store_mode() . "\n";

store_write('angebote', $a);
check('gelesen wie gespeichert', store_read_gemerkt('angebote') === $a);
fremd_schreiben($b);
check('innerhalb der Anfrage gemerkt: die fremde Änderung erscheint ohne Sperre nicht (ein Stand je Anfrage)', store_read_gemerkt('angebote') === $a);
check('store_read liest weiter frisch', store_read('angebote') === $b);
$innen = with_lock('angebote', function () { return store_read_gemerkt('angebote'); });
check('innerhalb einer Sperre der aktuelle Stand (sonst gingen fremde Änderungen beim Schreiben verloren)', $innen === $b, $innen);
check('nach der Sperre neu gelesen', store_read_gemerkt('angebote') === $b);

fremd_schreiben($c);
$innen = with_lock('andere-sperre', function () { return store_read_gemerkt('angebote'); });
check('auch unter einer anderen Sperre der aktuelle Stand', $innen === $c, $innen);
$innen = with_lock('a1', function () use ($c) {
    with_lock('a2', function () { return 1; });
    return [store_read_gemerkt('angebote') === $c, $GLOBALS['store_gemerkt'] ?? []];
});
check('verschachtelte Sperren: nach der inneren gilt die äußere weiter (aktueller Stand, nichts gemerkt)', $innen === [true, []], $innen);

store_read_gemerkt('angebote');
store_write('angebote', $a);
check('eigenes Schreiben vergisst das Gemerkte', store_read_gemerkt('angebote') === $a);
store_delete('angebote');
check('eigenes Löschen vergisst das Gemerkte', store_read_gemerkt('angebote') === null);

store_write('angebote', $a);
try { with_lock('angebote', function () { throw new RuntimeException('Abbruch'); }); } catch (RuntimeException $e) {}
check('nach einem Fehler in der Sperre wird wieder gemerkt (Zähler zurückgesetzt)', empty($GLOBALS['store_sperren']) && store_read_gemerkt('angebote') === $a);
fremd_schreiben($b);
check('… und die Anfrage behält ihren Stand', store_read_gemerkt('angebote') === $a);
