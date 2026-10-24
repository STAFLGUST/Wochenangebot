<?php
declare(strict_types=1);
/* Modul HR · Excel-Export für den Steuerberater: ein Blatt je Monat in Aufbau und Gestaltung der bisherigen
   Planungsdatei „Urlaub 2026“ (Legende, Monatstitel, Wochentage, Tageszahlen, Abteilungen senkrecht, Kürzel U/K/G und
   „x“ für freie Tage, Summen je Person und Monat mit Excel-Formeln).
   Nur genehmigte Einträge; beantragter Urlaub erscheint nicht. Erzeugt die .xlsx-Datei ohne PHP-Erweiterung „zip“
   (das Produktions-Image hat sie nicht): Office-Open-XML-Teile werden unkomprimiert in ein ZIP-Archiv geschrieben. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- ZIP (Methode „stored“) ---------------- */

function hr_zip(array $dateien): string
{
    $daten = ''; $verz = ''; $n = 0;
    foreach ($dateien as $name => $inhalt) {
        $crc = crc32($inhalt); $len = strlen($inhalt); $off = strlen($daten);
        // Version 2.0, Flag 0x0800 = Dateinamen in UTF-8, Methode 0, Zeit 00:00, Datum 01.01.1980
        $kopf = pack('vvvvvVVVvv', 20, 0x0800, 0, 0, 0x21, $crc, $len, $len, strlen($name), 0);
        $daten .= "PK\x03\x04" . $kopf . $name . $inhalt;
        $verz .= "PK\x01\x02" . pack('vvvvvvVVVvvvvvVV', 20, 20, 0x0800, 0, 0, 0x21, $crc, $len, $len, strlen($name), 0, 0, 0, 0, 0, $off) . $name;
        $n++;
    }
    return $daten . $verz . "PK\x05\x06" . pack('vvvvVVv', 0, 0, $n, $n, strlen($verz), strlen($daten), 0);
}

/* ---------------- Formate ---------------- */

/* Formatkatalog: Schlüssel → Index in cellXfs (styles.xml wird daraus erzeugt) */
final class HrStile
{
    public array $fonts = []; public array $fills = []; public array $borders = []; public array $xfs = [];
    private array $idx = [];

    public function __construct()
    {
        $this->fills = ['<fill><patternFill patternType="none"/></fill>', '<fill><patternFill patternType="gray125"/></fill>'];
        $this->fonts = ['<font><sz val="11"/><name val="Calibri"/><family val="2"/></font>'];
        $this->borders = ['<border><left/><right/><top/><bottom/><diagonal/></border>'];
        $this->xfs = ['<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'];
    }
    private function liste(array &$l, string $xml): int { $i = array_search($xml, $l, true); if ($i !== false) return (int)$i; $l[] = $xml; return count($l) - 1; }

    /* $s: fett, gr (Schriftgröße), farbe (RGB der Schrift), fill (RGB), rand [links, rechts, oben, unten] (thin|medium|''),
       h (left|center), v (center), dreh (Grad) */
    public function id(array $s): int
    {
        $k = json_encode($s);
        if (isset($this->idx[$k])) return $this->idx[$k];
        $font = $this->liste($this->fonts, '<font>' . (!empty($s['fett']) ? '<b/>' : '') . '<sz val="' . ($s['gr'] ?? 11) . '"/>'
            . (!empty($s['farbe']) ? '<color rgb="FF' . $s['farbe'] . '"/>' : '<color theme="1"/>') . '<name val="Calibri"/><family val="2"/><scheme val="minor"/></font>');
        $fill = empty($s['fill']) ? 0 : $this->liste($this->fills, '<fill><patternFill patternType="solid"><fgColor rgb="FF' . $s['fill'] . '"/><bgColor indexed="64"/></patternFill></fill>');
        $r = $s['rand'] ?? ['', '', '', ''];
        $teil = function (string $n, string $st) { return $st === '' ? "<$n/>" : "<$n style=\"$st\"><color indexed=\"64\"/></$n>"; };
        $border = $this->liste($this->borders, '<border>' . $teil('left', $r[0]) . $teil('right', $r[1]) . $teil('top', $r[2]) . $teil('bottom', $r[3]) . '<diagonal/></border>');
        $al = '';
        if (!empty($s['h']) || !empty($s['v']) || !empty($s['dreh'])) {
            $al = '<alignment' . (!empty($s['h']) ? ' horizontal="' . $s['h'] . '"' : '') . (!empty($s['v']) ? ' vertical="' . $s['v'] . '"' : '')
                . (!empty($s['dreh']) ? ' textRotation="' . (int)$s['dreh'] . '"' : '') . '/>';
        }
        $xf = '<xf numFmtId="0" fontId="' . $font . '" fillId="' . $fill . '" borderId="' . $border . '" xfId="0" applyFont="1"'
            . ($fill ? ' applyFill="1"' : '') . ($border ? ' applyBorder="1"' : '') . ($al ? ' applyAlignment="1">' . $al . '</xf>' : '/>');
        return $this->idx[$k] = $this->liste($this->xfs, $xf);
    }

    public function xml(): string
    {
        return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n"
            . '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            . '<fonts count="' . count($this->fonts) . '">' . implode('', $this->fonts) . '</fonts>'
            . '<fills count="' . count($this->fills) . '">' . implode('', $this->fills) . '</fills>'
            . '<borders count="' . count($this->borders) . '">' . implode('', $this->borders) . '</borders>'
            . '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
            . '<cellXfs count="' . count($this->xfs) . '">' . implode('', $this->xfs) . '</cellXfs>'
            . '<cellStyles count="1"><cellStyle name="Standard" xfId="0" builtinId="0"/></cellStyles></styleSheet>';
    }
}

/* Farben wie in „Urlaub 2026“ */
const HR_XL_WOCHENENDE = 'BFBFBF';
const HR_XL_FEIERTAG = 'FFC000';
const HR_XL_FERIEN = 'E2EFDA';
const HR_XL_SPERRE = 'FF0000';
const HR_XL_SUMME = 'EDEDED';
const HR_XL_TITEL = 'F2F2F2';
const HR_XL_ROT = 'FF0000';

function hr_xl_spalte(int $n): string { $s = ''; for ($n++; $n > 0; $n = intdiv($n - 1, 26)) $s = chr(65 + ($n - 1) % 26) . $s; return $s; }
function hr_xl_text(string $t): string { return htmlspecialchars(preg_replace('/[\x00-\x08\x0b\x0c\x0e-\x1f]/', '', $t) ?? '', ENT_XML1 | ENT_QUOTES, 'UTF-8'); }

/* Ein Monatsblatt (sheet-XML) */
function hr_xl_blatt(array $m, HrStile $st): string
{
    $zellen = [];   // [zeile][spalte] = XML der Zelle
    $setz = function (int $z, int $sp, $wert, int $stil, ?string $formel = null) use (&$zellen) {
        $r = hr_xl_spalte($sp) . $z;
        if ($formel !== null) $x = '<c r="' . $r . '" s="' . $stil . '"><f>' . hr_xl_text($formel) . '</f><v>' . (int)$wert . '</v></c>';
        elseif ($wert === null || $wert === '') $x = '<c r="' . $r . '" s="' . $stil . '"/>';
        elseif (is_int($wert) || is_float($wert)) $x = '<c r="' . $r . '" s="' . $stil . '"><v>' . $wert . '</v></c>';
        else $x = '<c r="' . $r . '" s="' . $stil . '" t="inlineStr"><is><t xml:space="preserve">' . hr_xl_text((string)$wert) . '</t></is></c>';
        $zellen[$z][$sp] = $x;
    };
    $merge = [];
    $T = ['', '', '', '']; $D = ['thin', 'thin', 'thin', 'thin'];
    $fett = ['fett' => true];

    // Legende (Zeilen 2–5) wie in der Planungsdatei
    $leg = ['fett' => true, 'rand' => ['medium', '', 'medium', 'medium']];
    $box = ['fett' => true, 'h' => 'center', 'v' => 'center', 'rand' => $D];
    foreach ([[2, 'Urlaub', 'U'], [3, 'Krank', 'K'], [4, 'Gleittag', 'G']] as [$z, $t, $k]) { $setz($z, 2, $t, $st->id($leg)); $setz($z, 3, $k, $st->id($box)); }
    $setz(5, 2, 'Urlaubssperre', $st->id($leg)); $setz(5, 3, '', $st->id($box + ['fill' => HR_XL_SPERRE]));
    $setz(2, 5, 'x', $st->id($box)); $setz(2, 6, 'Freier Tag', $st->id($fett));
    $setz(4, 5, '', $st->id($box + ['fill' => HR_XL_FERIEN])); $setz(4, 6, 'Ferien', $st->id($fett));
    $setz(5, 5, '', $st->id($box + ['fill' => HR_XL_FEIERTAG])); $setz(5, 6, 'Feiertag', $st->id([]));
    // Monatstitel K2:U3
    $setz(2, 10, $m['name'] . ' ' . $m['jahr'], $st->id(['fett' => true, 'gr' => 22, 'h' => 'center', 'v' => 'center', 'fill' => HR_XL_TITEL]));
    for ($z = 2; $z <= 3; $z++) for ($sp = 10; $sp <= 20; $sp++) if ($z !== 2 || $sp !== 10) $setz($z, $sp, '', $st->id(['fill' => HR_XL_TITEL]));
    $merge[] = 'K2:U3';

    // Kopf: Zeile 7 Wochentage, Zeile 8 Pos./Monat/Tageszahlen; Spalten A Pos., B Abteilung, C Name, ab D die Tage
    $tage = $m['tage']; $n = count($tage); $erste = 3; $letzte = $erste + $n - 1;
    $sU = $letzte + 1; $sK = $letzte + 2; $sG = $letzte + 3;
    $farbe = function (array $t): ?string {
        if ($t['feiertag'] !== null) return HR_XL_FEIERTAG;
        if ($t['wochenende']) return HR_XL_WOCHENENDE;
        if ($t['ferien']) return HR_XL_FERIEN;
        return null;
    };
    $setz(8, 0, 'Pos.', $st->id(['fett' => true, 'h' => 'center', 'rand' => $D]));
    $setz(8, 1, ' ', $st->id(['fett' => true, 'h' => 'center', 'rand' => ['thin', '', 'thin', '']]));
    $setz(8, 2, $m['name'], $st->id(['fett' => true, 'gr' => 12, 'v' => 'center', 'rand' => ['medium', 'thin', 'thin', 'medium']]));
    foreach ($tage as $i => $t) {
        $f = $farbe($t);
        $kopf = ['fett' => true, 'h' => 'center'] + ($t['sperre'] ? ['fill' => HR_XL_SPERRE] : ($f ? ['fill' => $f] : []));
        $setz(7, $erste + $i, $t['wt'], $st->id($kopf + ['rand' => [$i === 0 ? 'medium' : 'thin', 'thin', 'medium', 'medium']]));
        $setz(8, $erste + $i, $t['tag'], $st->id($kopf + ['rand' => ['thin', 'thin', '', 'medium']]));
    }
    $rot = ['fett' => true, 'farbe' => HR_XL_ROT, 'h' => 'center'];
    foreach ([[$sU, 'U'], [$sK, 'K'], [$sG, 'G']] as $j => [$sp, $k]) {
        $setz(7, $sp, $k, $st->id($rot + ['rand' => [$j === 0 ? 'medium' : 'thin', 'thin', 'medium', 'thin']]));
        $setz(8, $sp, '', $st->id($rot + ['rand' => [$j === 0 ? 'medium' : 'thin', 'thin', 'thin', 'medium']]));
    }

    // Mitarbeiterzeilen ab Zeile 9
    $z = 9; $start = 9; $abtStart = 9; $abt = null; $pos = 0;
    $abtStil = $st->id(['fett' => true, 'gr' => 12, 'h' => 'center', 'v' => 'center', 'dreh' => 90, 'rand' => ['medium', 'thin', 'medium', 'thin']]);
    $abschluss = function (int $bis) use (&$abtStart, &$merge, $setz, $abtStil) {
        if ($bis > $abtStart) { $merge[] = 'B' . $abtStart . ':B' . $bis; for ($r = $abtStart + 1; $r <= $bis; $r++) $setz($r, 1, '', $abtStil); }
    };
    $L = hr_xl_spalte($erste); $R = hr_xl_spalte($letzte);
    foreach ($m['personen'] as $p) {
        if ($p['abteilung'] !== $abt) {
            if ($abt !== null) $abschluss($z - 1);
            $abt = $p['abteilung']; $abtStart = $z;
            $setz($z, 1, $abt, $abtStil);
        }
        $pos++;
        $setz($z, 0, $pos, $st->id(['fett' => true, 'h' => 'center', 'rand' => ['thin', '', 'thin', 'thin']]));
        $setz($z, 2, $p['name'], $st->id(['fett' => true, 'rand' => $D]));
        $anz = ['U' => 0, 'K' => 0, 'G' => 0];
        foreach ($tage as $i => $t) {
            $k = (string)(((array)$p['tage'])[$t['tag']] ?? '');
            if (isset($anz[$k])) $anz[$k]++;
            $f = $farbe($t);
            $setz($z, $erste + $i, $k, $st->id(['fett' => true, 'h' => 'center', 'v' => 'center', 'rand' => $D] + ($f ? ['fill' => $f] : [])));
        }
        foreach ([[$sU, 'U'], [$sK, 'K'], [$sG, 'G']] as [$sp, $k]) {
            $setz($z, $sp, $anz[$k], $st->id($rot + ['rand' => ['thin', 'thin', '', 'thin']]), 'COUNTIF(' . $L . $z . ':' . $R . $z . ',"' . $k . '")');
        }
        $z++;
    }
    if ($abt !== null) $abschluss($z - 1);
    $ende = $z - 1;
    // Summenzeile
    $sz = $z + 1;
    $setz($sz, 2, 'Summe', $st->id($fett));
    $setz($sz, $letzte - 2, 'Summe', $st->id(['fett' => true, 'h' => 'center']));
    for ($sp = $letzte - 1; $sp <= $letzte; $sp++) $setz($sz, $sp, '', $st->id(['fett' => true, 'h' => 'center']));
    $merge[] = hr_xl_spalte($letzte - 2) . $sz . ':' . hr_xl_spalte($letzte) . $sz;
    foreach ([$sU, $sK, $sG] as $j => $sp) {
        $c = hr_xl_spalte($sp);
        $summe = 0;
        foreach ($m['personen'] as $p) foreach ((array)$p['tage'] as $k) if ($k === ['U', 'K', 'G'][$j]) $summe++;
        $setz($sz, $sp, $summe, $st->id($rot + ['fill' => HR_XL_SUMME, 'rand' => $D]), $ende >= $start ? "SUM({$c}{$start}:{$c}{$ende})" : '0');
    }

    // XML
    $breiten = '<col min="1" max="1" width="5.89" customWidth="1"/><col min="2" max="2" width="7.44" customWidth="1"/>'
        . '<col min="3" max="3" width="22.33" customWidth="1"/><col min="4" max="' . ($letzte + 1) . '" width="5" customWidth="1"/>'
        . '<col min="' . ($sU + 1) . '" max="' . ($sG + 1) . '" width="6.44" customWidth="1"/>';
    ksort($zellen);
    $rows = '';
    foreach ($zellen as $r => $cs) {
        ksort($cs);
        $h = $r >= 7 && $r <= $ende ? ' ht="18" customHeight="1"' : ($r === 2 || $r === 3 ? ' ht="15.75" customHeight="1"' : '');
        $rows .= '<row r="' . $r . '"' . $h . '>' . implode('', $cs) . '</row>';
    }
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n"
        . '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        . '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'
        . '<sheetViews><sheetView workbookViewId="0"><pane xSplit="3" ySplit="8" topLeftCell="D9" activePane="bottomRight" state="frozen"/>'
        . '<selection pane="bottomRight" activeCell="D9" sqref="D9"/></sheetView></sheetViews>'
        . '<sheetFormatPr defaultRowHeight="15"/><cols>' . $breiten . '</cols><sheetData>' . $rows . '</sheetData>'
        . '<mergeCells count="' . count($merge) . '">' . implode('', array_map(function ($x) { return '<mergeCell ref="' . $x . '"/>'; }, $merge)) . '</mergeCells>'
        . '<pageMargins left="0.25" right="0.25" top="0.5" bottom="0.5" header="0.3" footer="0.3"/>'
        . '<pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="1"/></worksheet>';
}

/* Arbeitsmappe aus Monatsplänen (hr_monat mit voller Sicht, aber nur genehmigte Einträge) */
function hr_xlsx(array $monate): string
{
    $st = new HrStile();
    $blaetter = [];
    foreach ($monate as $m) $blaetter[] = [$m['name'] . ' ' . $m['jahr'], hr_xl_blatt($m, $st)];
    $ct = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n"
        . '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        . '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        . '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        . '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        . '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        . '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>';
    $wbRels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">';
    $sheets = ''; $dateien = [];
    foreach ($blaetter as $i => [$name, $xml]) {
        $n = $i + 1;
        $ct .= '<Override PartName="/xl/worksheets/sheet' . $n . '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>';
        $wbRels .= '<Relationship Id="rId' . $n . '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet' . $n . '.xml"/>';
        $sheets .= '<sheet name="' . hr_xl_text(mb_substr($name, 0, 31)) . '" sheetId="' . $n . '" r:id="rId' . $n . '"/>';
        $dateien['xl/worksheets/sheet' . $n . '.xml'] = $xml;
    }
    $k = count($blaetter) + 1;
    $wbRels .= '<Relationship Id="rId' . $k . '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>';
    $ct .= '</Types>';
    $jetzt = gmdate('Y-m-d\TH:i:s\Z');
    return hr_zip([
        '[Content_Types].xml' => $ct,
        '_rels/.rels' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            . '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            . '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            . '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>',
        'docProps/core.xml' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            . '<dc:title>Urlaub</dc:title><dc:creator>STAFL-Plattform · HR</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">' . $jetzt . '</dcterms:created></cp:coreProperties>',
        'docProps/app.xml' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>STAFL-Plattform</Application></Properties>',
        'xl/workbook.xml' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            . '<bookViews><workbookView/></bookViews><sheets>' . $sheets . '</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>',
        'xl/_rels/workbook.xml.rels' => $wbRels,
        'xl/styles.xml' => $st->xml(),
    ] + $dateien);
}

/* Monatsplan für den Export: alle aktiven Mitarbeiter, nur genehmigte Einträge, Kürzel U/K/G/x.
   Nicht mehr im Urlaubsplan (z. B. ausgeschieden): nur in Monaten, in denen sie genehmigte Abwesenheiten haben – die
   Abrechnung eines vergangenen Monats braucht sie weiter. */
function hr_export_monat(int $jahr, int $monat): array
{
    $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
    $tage = hr_monatstage($jahr, $monat, $einst);
    $genehmigt = array_values(array_filter($abw['eintraege'], function ($e) { return $e['status'] === 'genehmigt'; }));
    $mv = sprintf('%04d-%02d-01', $jahr, $monat); $mb = sprintf('%04d-%02d-31', $jahr, $monat);
    $imMonat = [];
    foreach ($genehmigt as $e) if ($e['art'] !== 'X' && $e['von'] <= $mb && $e['bis'] >= $mv) $imMonat[$e['person']] = true;
    $zeilen = [];
    foreach (hr_nach_abteilung($personal['personen']) as $p) {
        if (!$p['aktiv'] && !isset($imMonat[$p['id']])) continue;
        $zeilen[] = ['id' => $p['id'], 'name' => hr_name($p), 'abteilung' => $p['abteilung'], 'tage' => hr_zeile($p, $genehmigt, $tage, 'voll')];
    }
    return ['jahr' => $jahr, 'monat' => $monat, 'name' => HR_MONATE[$monat], 'tage' => $tage, 'personen' => $zeilen];
}

function hr_export_dateiname(int $jahr, array $monate): string
{
    if (count($monate) === 12) return "Urlaub_{$jahr}.xlsx";
    if (count($monate) === 1) return sprintf('Urlaub_%04d-%02d_%s.xlsx', $jahr, $monate[0], str_replace('ä', 'ae', HR_MONATE[$monate[0]]));
    return sprintf('Urlaub_%04d-%02d_bis_%02d.xlsx', $jahr, $monate[0], $monate[count($monate) - 1]);
}
