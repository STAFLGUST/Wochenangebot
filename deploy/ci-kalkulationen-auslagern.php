<?php
/* Container-Import: Kalkulationen auslagern, wenn das Dokument containerimport-kalkulationen seine Gesamtgrenze erreicht
   (CI_KALK_MAX_POSITIONEN_GESAMT in app/api/module/containerimport/kalkulation.php). Das Dokument wird bei jedem Zugriff
   ganz gelesen und ganz geschrieben; ohne diesen Weg wäre die Grenze eine Einbahnstraße, denn die Anwendung löscht nie
   eine Fassung (GoBD).
   Entfernt wird nur, was zuvor vollständig exportiert und aus der Exportdatei wieder eingelesen und verglichen wurde –
   die Exportdatei ist das Archiv dieser Vorgänge und gehört in die Sicherung (nur für den Besitzer lesbar). Auch mit SQLite.
   Das Skript läuft bei laufender Anwendung: Hat sich ein genannter Eintrag seit dem Export geändert (neue Fassung), wird
   nichts entfernt – erneut exportieren.

     php deploy/ci-kalkulationen-auslagern.php                                  # nur ansehen: Größe je Container
     php deploy/ci-kalkulationen-auslagern.php --export /pfad/archiv.json       # alles exportieren, nichts ändern
     php deploy/ci-kalkulationen-auslagern.php --export /pfad/archiv.json --entfernen s1,s2

   In Tests: DATA_DIR=<Testdaten> php deploy/ci-kalkulationen-auslagern.php … */
$DATA = getenv('DATA_DIR') ?: '/var/www/html/data';
require is_file(__DIR__ . '/../app/api/storage.php') ? __DIR__ . '/../app/api/storage.php' : '/var/www/html/api/storage.php';
const DOKUMENT = 'containerimport-kalkulationen';

$argumente = array_slice($argv, 1);
$wert = function (string $name) use ($argumente): string {
    $i = array_search($name, $argumente, true);
    return $i === false || !isset($argumente[$i + 1]) ? '' : (string)$argumente[$i + 1];
};
$export = $wert('--export');
$entfernen = array_values(array_filter(array_map('trim', explode(',', $wert('--entfernen')))));
if ($entfernen && $export === '') { fwrite(STDERR, "--entfernen geht nur mit --export: ohne Archiv wird nichts entfernt.\n"); exit(2); }

$positionen = function (array $k): int {
    $n = 0;
    foreach ($k['fassungen'] ?? [] as $f) $n += count($f['eingabe']['positionen'] ?? []);
    return $n;
};
$doc = store_read(DOKUMENT);
if (!is_array($doc) || !is_array($doc['liste'] ?? null)) { echo "Kein Dokument " . DOKUMENT . " vorhanden.\n"; exit(0); }

$gesamt = 0;
echo "Container (sendung) · Fassungen · Positionen\n";
foreach ($doc['liste'] as $k) {
    $p = $positionen($k);
    $gesamt += $p;
    printf("  %-24s %4d %8d\n", (string)($k['sendung'] ?? '?'), count($k['fassungen'] ?? []), $p);
}
printf("Einträge: %d · Positionen zusammen: %d\n", count($doc['liste']), $gesamt);
if ($export === '') exit(0);

$json = json_encode($doc, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT | JSON_THROW_ON_ERROR);
$umask = umask(0077);   // Geschäftsdaten: neue Exportdatei nur für den Besitzer (z. B. unter /tmp)
$ok = file_put_contents($export, $json, LOCK_EX);
umask($umask);
if ($ok === false) { fwrite(STDERR, "Export nach $export nicht möglich.\n"); exit(1); }
$probe = json_decode((string)file_get_contents($export), true);   // Gegenprobe: das Archiv muss lesbar und gleich sein
if ($probe !== $doc) { fwrite(STDERR, "Der Export stimmt nicht mit dem Dokument überein – es wird nichts entfernt.\n"); exit(1); }
printf("Export geprüft: %s (%d Byte)\n", $export, strlen($json));
if (!$entfernen) exit(0);

$weg = [];
with_lock(DOKUMENT, function () use ($entfernen, &$weg, $positionen, $doc) {
    $d = store_read(DOKUMENT);
    if (!is_array($d) || !is_array($d['liste'] ?? null)) { fwrite(STDERR, "Dokument ist verschwunden.\n"); exit(1); }
    $bleibt = [];
    foreach ($d['liste'] as $k) {
        if (!in_array((string)($k['sendung'] ?? ''), $entfernen, true)) { $bleibt[] = $k; continue; }
        // nur genau so entfernen, wie er im Export steht – eine seither gespeicherte Fassung stünde in keinem Archiv
        if (!in_array($k, $doc['liste'], true)) {
            fwrite(STDERR, 'Kalkulation zu ' . (string)$k['sendung'] . " hat sich seit dem Export geändert – nichts entfernt, bitte erneut exportieren.\n");
            exit(1);
        }
        $weg[] = (string)$k['sendung'] . ' (' . $positionen($k) . ' Positionen)';
    }
    if (!$weg) return;
    $d['liste'] = $bleibt;
    $d['rev'] = (int)($d['rev'] ?? 0) + 1;
    $d['updatedAt'] = gmdate('Y-m-d\TH:i:s\Z');
    store_write(DOKUMENT, $d);
});
echo $weg ? "Ausgelagert (nur noch im Export): " . implode(', ', $weg) . "\n" : "Keiner der genannten Container hat eine Kalkulation.\n";
