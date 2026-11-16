<?php
/* Reine Funktionen und Tabellen der Dateiablage (app/api/lib/dateiablage.php) ohne Server: Ende des ZIP-Verzeichnisses genau an
   den Zip64-Grenzen (Versatz 0xFFFFFFFE/0xFFFFFFFF, 65534/65535 Einträge), Platzreserve nach einem Upload, jede Kopfprüfung der
   Dateiarten ist bekannt und keine erlaubte Art steht auf der Sperrliste; Word, Excel und PowerPoint mit Kennwort (OLE-Container) werden
   angenommen, als OpenDocument, ZIP oder PDF nicht. */
declare(strict_types=1);
const WA_API = true;
require __DIR__ . '/../../app/api/lib/dateiablage.php';
function check(string $name, bool $ok): void
{
    if (!$ok) { fwrite(STDERR, "FAIL $name\n"); exit(1); }
    echo "PASS $name\n";
}
function eocd(string $ende): array { return unpack('x4/vdisk/vcddisk/vhier/vanzahl/Vlaenge/Vstart', substr($ende, -22)); }

$e = ablage_zip_ende(3, 183, 0xFFFFFFFE);
check('Verzeichnis beginnt bei 0xFFFFFFFE: klassisches Ende mit echtem Versatz', strlen($e) === 22 && eocd($e)['start'] === 0xFFFFFFFE && eocd($e)['anzahl'] === 3);
$e = ablage_zip_ende(3, 183, 0xFFFFFFFF);
$z = unpack('a4sig/Pgroesse/vmade/vneed/Vdisk/Vcddisk/Phier/Panzahl/Plaenge/Pstart', $e);
$v = unpack('a4sig/Vdisk/Pende64/Vdisks', $e, 56);
check('Verzeichnis beginnt bei 0xFFFFFFFF: Zip64-Ende mit echtem Versatz, Verweis darauf, im klassischen Ende 0xFFFFFFFF',
    strlen($e) === 56 + 20 + 22 && $z['sig'] === "PK\x06\x06" && $z['groesse'] === 44 && $z['anzahl'] === 3 && $z['laenge'] === 183 && $z['start'] === 0xFFFFFFFF
    && $v['sig'] === "PK\x06\x07" && $v['ende64'] === 0xFFFFFFFF + 183 && eocd($e)['start'] === 0xFFFFFFFF && eocd($e)['anzahl'] === 3);
check('65534 Einträge: klassisches Ende', strlen(ablage_zip_ende(0xFFFE, 100, 10)) === 22 && eocd(ablage_zip_ende(0xFFFE, 100, 10))['anzahl'] === 0xFFFE);
$e = ablage_zip_ende(70000, 100, 10);
check('ab 65535 Einträgen: Zip64-Ende mit der echten Anzahl, im klassischen Ende 0xFFFF', unpack('P', $e, 32)[1] === 70000 && eocd($e)['anzahl'] === 0xFFFF
    && strlen(ablage_zip_ende(0xFFFF, 100, 10)) === 98);

check('Platz reicht, wenn danach genau die Reserve frei bleibt', ablage_platz_reicht(ABLAGE_RESERVE + 100.0, 100));
check('Platz reicht nicht, wenn ein Byte der Reserve fehlt', !ablage_platz_reicht(ABLAGE_RESERVE + 100.0, 101) && !ablage_platz_reicht(0.0, 1));

// Kopf einer OLE-/CFB-Datei (MS-CFB 2.2), wie Microsoft Office eine Datei mit Kennwort speichert
$cfb = pack('a8a16vvvvva6VVVVVVVVV', "\xD0\xCF\x11\xE0\xA1\xB1\x1A\xE1", '', 0x3E, 3, 0xFFFE, 9, 6, '', 0, 1, 1, 0, 0x1000, 0xFFFFFFFE, 0, 0xFFFFFFFE, 0)
     . pack('V', 0) . str_repeat(pack('V', 0xFFFFFFFF), 108);
$tmp = tempnam(sys_get_temp_dir(), 'cfb');
file_put_contents($tmp, $cfb . str_repeat("\0", 1024));
check('Office-Datei mit Kennwort (OLE-Container) als docx, xlsx, xlsm, pptx angenommen', strlen($cfb) === 512
    && ablage_inhalt_passt($tmp, 'docx') && ablage_inhalt_passt($tmp, 'xlsx') && ablage_inhalt_passt($tmp, 'xlsm') && ablage_inhalt_passt($tmp, 'pptx'));
check('OLE-Container nicht als OpenDocument, ZIP oder PDF', !ablage_inhalt_passt($tmp, 'odt') && !ablage_inhalt_passt($tmp, 'zip') && !ablage_inhalt_passt($tmp, 'pdf'));
file_put_contents($tmp, "PK\x05\x06" . str_repeat("\0", 18));
check('leeres ZIP bleibt als docx abgelehnt', !ablage_inhalt_passt($tmp, 'docx'));
unlink($tmp);

$unbekannt = array_keys(array_filter(ABLAGE_ARTEN, fn($a) => !in_array($a[1], ['text', 'binaer'], true) && !isset(ABLAGE_KOEPFE[$a[1]])));
check('jede Art hat eine bekannte Kopfprüfung', $unbekannt === []);
check('keine erlaubte Art steht auf der Sperrliste', array_intersect(array_keys(ABLAGE_ARTEN), ABLAGE_GESPERRT) === []);
