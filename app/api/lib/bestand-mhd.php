<?php
declare(strict_types=1);
/* Modul Bestand · MHD-Liste an den Verkauf: dieselbe Liste wie die Suche „MHD“ im Bestand (kürzestes MHD bis heute + 14 Tage,
   früheste zuerst), als Excel-Datei (ohne PHP-Erweiterung „zip“, unkomprimiertes ZIP) und E-Mail mit dem Bild der Liste.
   Mengen, MHD und Preise nimmt der Server aus dem gespeicherten Bestand und den Wochenpreisen – nie aus dem Browser.
   Versand über das Postfach für interne E-Mails an die Empfänger der Benachrichtigung „MHD-Liste an den Verkauf“. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const MHD_TAGE = 14;

/* MHD-Stufe wie in der Oberfläche (mhdClass in admin.js) */
function mhd_stufe(?string $mhd, string $heute): string
{
    if (!$mhd) return '';
    $tage = (int)round((strtotime($mhd . 'T12:00:00Z') - strtotime($heute . 'T12:00:00Z')) / 86400);
    return $tage < 0 ? 'abgelaufen' : ($tage <= 4 ? '0-4' : ($tage <= 7 ? '5-7' : ($tage <= MHD_TAGE ? '8-14' : '')));
}
/* Wochenpreis je Artikelnummer wie S.weekPriceMap: bei widersprüchlichen Angaben „mehrere Preisangaben“ */
function mhd_preise(array $woche): array
{
    $map = [];
    foreach ($woche['items'] ?? [] as $it) {
        $k = code_key((string)$it['code']); $p = is_array($it['price'] ?? null) ? $it['price'] : ['status' => 'none'];
        $sig = json_encode([$p['status'] ?? '', $p['value'] ?? null, $p['label'] ?? '']);
        if (!isset($map[$k])) $map[$k] = $p + ['_sig' => $sig];
        elseif ($map[$k]['_sig'] !== $sig) $map[$k] = ['status' => 'ambiguous', '_sig' => 'x'];
    }
    return $map;
}
function mhd_preis_text(?array $p): string
{
    $s = $p['status'] ?? 'none';
    if ($s === 'ambiguous') return 'mehrere Preisangaben';
    if ($s === 'request') return 'auf Anfrage';
    if ($s !== 'value' || !is_numeric($p['value'] ?? null)) return '—';
    $v = number_format((float)$p['value'], 4, ',', '.');   // wie Intl de-DE: 2 bis 4 Nachkommastellen
    while (substr($v, -1) === '0' && strlen($v) - strpos($v, ',') > 3) $v = substr($v, 0, -1);
    return $v . ' €' . (!empty($p['label']) ? ' · ' . $p['label'] : '/kg');
}
/* Die MHD-Liste: [heute, bis, zeilen[{code, name, kg, mhd, mhdKg, stufe, erfasst, gesamt, eta, preis, vorwoche}], preise(bool), wochen] */
function mhd_liste(array $st, bool $mitPreisen, ?DateTimeImmutable $jetzt = null): array
{
    $jetzt = ($jetzt ?? new DateTimeImmutable('now', new DateTimeZone('Europe/Berlin')))->setTimezone(new DateTimeZone('Europe/Berlin'));
    $heute = $jetzt->format('Y-m-d');
    $bis = $jetzt->modify('+' . MHD_TAGE . ' days')->format('Y-m-d');
    $zu = [];
    foreach ($st['incoming'] ?? [] as $z) $zu[code_key((string)$z['code'])][] = $z;
    $wp = $mitPreisen ? stock_week_prices($jetzt) : null;
    $akt = $wp ? mhd_preise($wp['current']) : []; $vor = $wp ? mhd_preise($wp['previous']) : [];
    $zeilen = [];
    foreach ($st['articles'] ?? [] as $a) {
        $mhd = $a['mhd'] ?? null;
        if (!$mhd || $mhd > $bis) continue;
        $k = code_key((string)$a['code']);
        $erfasst = 0;
        $etas = [];
        foreach ($zu[$k] ?? [] as $z) { $erfasst += (int)round((float)$z['kg'] * 1000); if (!empty($z['arrival'])) $etas[] = $z['arrival']; }
        sort($etas);
        $eta = null;
        foreach ($etas as $e) if ($e >= $heute) { $eta = $e; break; }
        if ($eta === null && $etas) $eta = end($etas);
        $zeilen[] = ['code' => (string)$a['code'], 'name' => (string)$a['name'], 'kg' => (float)$a['kg'], 'mhd' => $mhd, 'mhdKg' => (float)($a['mhdKg'] ?? 0),
                     'stufe' => mhd_stufe($mhd, $heute), 'erfasst' => $erfasst / 1000, 'gesamt' => ((int)round((float)$a['kg'] * 1000) + $erfasst) / 1000, 'eta' => $eta,
                     'preis' => $mitPreisen ? mhd_preis_text($akt[$k] ?? null) : null, 'vorwoche' => $mitPreisen ? mhd_preis_text($vor[$k] ?? null) : null];
    }
    usort($zeilen, function ($x, $y) { return strcmp($x['mhd'], $y['mhd']) ?: strnatcasecmp($x['code'], $y['code']); });
    return ['heute' => $heute, 'bis' => $bis, 'zeilen' => $zeilen, 'preise' => $mitPreisen,
            'wochen' => $wp ? ['KW ' . $wp['current']['week'] . '/' . $wp['current']['year'], 'KW ' . $wp['previous']['week'] . '/' . $wp['previous']['year']] : null];
}

/* ---------------- Excel (Office Open XML, ein Blatt) ---------------- */

function mhd_zip(array $dateien): string
{
    $daten = ''; $verz = ''; $n = 0;
    foreach ($dateien as $name => $inhalt) {
        $crc = crc32($inhalt); $len = strlen($inhalt); $off = strlen($daten);
        $daten .= "PK\x03\x04" . pack('vvvvvVVVvv', 20, 0x0800, 0, 0, 0x21, $crc, $len, $len, strlen($name), 0) . $name . $inhalt;
        $verz .= "PK\x01\x02" . pack('vvvvvvVVVvvvvvVV', 20, 20, 0x0800, 0, 0, 0x21, $crc, $len, $len, strlen($name), 0, 0, 0, 0, 0, $off) . $name;
        $n++;
    }
    return $daten . $verz . "PK\x05\x06" . pack('vvvvVVv', 0, 0, $n, $n, strlen($verz), strlen($daten), 0);
}
function mhd_xml(string $t): string { return htmlspecialchars(preg_replace('/[\x00-\x08\x0b\x0c\x0e-\x1f]/', '', $t) ?? '', ENT_XML1 | ENT_QUOTES, 'UTF-8'); }
function mhd_spalte(int $n): string { $s = ''; for ($n++; $n > 0; $n = intdiv($n - 1, 26)) $s = chr(65 + ($n - 1) % 26) . $s; return $s; }

function mhd_xlsx(array $l, string $titel): string
{
    /* Formate (cellXfs): 0 Standard · 1 Kopf · 2 Titel · 3 kg · 4 Datum · 5–8 MHD-Stufen Datum · 9–12 MHD-Stufen kg · 13 Summe Text · 14 Summe kg · 15 Hinweis */
    $stufen = ['abgelaufen' => 'D9D6D2', '0-4' => 'FBE0DD', '5-7' => 'FDE7D3', '8-14' => 'FBF0C9'];
    $fills = '<fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill><fill><patternFill patternType="solid"><fgColor rgb="FFF3F1EE"/><bgColor indexed="64"/></patternFill></fill>';
    foreach ($stufen as $rgb) $fills .= '<fill><patternFill patternType="solid"><fgColor rgb="FF' . $rgb . '"/><bgColor indexed="64"/></patternFill></fill>';
    $xf = function (int $num, int $font, int $fill, int $border, string $al = '') {
        return '<xf numFmtId="' . $num . '" fontId="' . $font . '" fillId="' . $fill . '" borderId="' . $border . '" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"'
            . ($al ? ' applyAlignment="1"><alignment ' . $al . '/></xf>' : '/>');
    };
    $xfs = [$xf(0, 0, 0, 0), $xf(0, 1, 2, 1, 'vertical="center" wrapText="1"'), $xf(0, 2, 0, 0), $xf(164, 0, 0, 0), $xf(165, 0, 0, 0, 'horizontal="center"')];
    $i = 3; foreach ($stufen as $_) $xfs[] = $xf(165, 1, $i++, 0, 'horizontal="center"');
    $i = 3; foreach ($stufen as $_) $xfs[] = $xf(164, 1, $i++, 0);
    $xfs[] = $xf(0, 1, 2, 3); $xfs[] = $xf(164, 1, 2, 3); $xfs[] = $xf(0, 3, 0, 0);
    $styles = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        . '<numFmts count="2"><numFmt numFmtId="164" formatCode="#,##0.00&quot; kg&quot;"/><numFmt numFmtId="165" formatCode="dd.mm.yyyy"/></numFmts>'
        . '<fonts count="4"><font><sz val="11"/><name val="Calibri"/><family val="2"/></font><font><b/><sz val="11"/><name val="Calibri"/><family val="2"/></font>'
        . '<font><b/><sz val="14"/><name val="Calibri"/><family val="2"/></font><font><i/><sz val="10"/><color rgb="FF666666"/><name val="Calibri"/><family val="2"/></font></fonts>'
        . '<fills count="' . (3 + count($stufen)) . '">' . $fills . '</fills>'
        . '<borders count="4"><border><left/><right/><top/><bottom/><diagonal/></border><border><left/><right/><top/><bottom style="medium"><color indexed="64"/></bottom><diagonal/></border>'
        . '<border><left/><right/><top/><bottom style="thin"><color rgb="FFDDDDDD"/></bottom><diagonal/></border><border><left/><right/><top style="medium"><color indexed="64"/></top><bottom/><diagonal/></border></borders>'
        . '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        . '<cellXfs count="' . count($xfs) . '">' . implode('', $xfs) . '</cellXfs><cellStyles count="1"><cellStyle name="Standard" xfId="0" builtinId="0"/></cellStyles></styleSheet>';
    $stufeIdx = array_flip(array_keys($stufen));
    $kopf = ['Art.-Nr.', 'Bezeichnung'];
    if ($l['preise']) { $kopf[] = 'Aktueller Preis ' . $l['wochen'][0]; $kopf[] = 'Preis Vorwoche ' . $l['wochen'][1]; }
    array_push($kopf, 'Eingelagerter Bestand', 'Kürz. MHD', 'Kg kürz. MHD', 'Erfasster Bestand', 'Nächste ETA', 'Gesamt verfügbar');
    $breiten = [10, 42]; if ($l['preise']) array_push($breiten, 22, 22); array_push($breiten, 16, 12, 15, 15, 12, 16);
    $rows = [];
    $zelle = function (int $z, int $sp, $wert, int $s) {
        $r = mhd_spalte($sp) . $z;
        if ($wert === null || $wert === '') return '<c r="' . $r . '" s="' . $s . '"/>';
        if (is_float($wert) || is_int($wert)) return '<c r="' . $r . '" s="' . $s . '"><v>' . $wert . '</v></c>';
        return '<c r="' . $r . '" s="' . $s . '" t="inlineStr"><is><t xml:space="preserve">' . mhd_xml((string)$wert) . '</t></is></c>';
    };
    $datum = function (?string $iso) { return $iso ? (float)(strtotime($iso . 'T00:00:00Z') / 86400 + 25569) : null; };
    $rows[] = '<row r="1" ht="22" customHeight="1">' . $zelle(1, 0, $titel, 2) . '</row>';
    $rows[] = '<row r="2">' . $zelle(2, 0, count($l['zeilen']) . ' Artikel mit MHD bis ' . date('d.m.Y', strtotime($l['bis'])) . ' (früheste zuerst) · erstellt ' . date('d.m.Y, H:i') . ' Uhr · intern – nicht zur Weitergabe', 15) . '</row>';
    $c = '<row r="4" ht="32" customHeight="1">';
    foreach ($kopf as $sp => $t) $c .= $zelle(4, $sp, $t, 1);
    $rows[] = $c . '</row>';
    $z = 5;
    foreach ($l['zeilen'] as $a) {
        $si = $stufeIdx[$a['stufe']] ?? null;
        $w = [$a['code'], $a['name']];
        $s = [0, 0];
        if ($l['preise']) { array_push($w, $a['preis'], $a['vorwoche']); array_push($s, 0, 0); }
        array_push($w, $a['kg'], $datum($a['mhd']), $a['mhdKg'], $a['erfasst'], $datum($a['eta']), $a['gesamt']);
        array_push($s, 3, $si === null ? 4 : 5 + $si, $si === null ? 3 : 9 + $si, 3, 4, 3);
        $c = '<row r="' . $z . '">';
        foreach ($w as $sp => $v) $c .= $zelle($z, $sp, $v, $s[$sp]);
        $rows[] = $c . '</row>';
        $z++;
    }
    $off = $l['preise'] ? 2 : 0;
    $c = '<row r="' . $z . '">' . $zelle($z, 0, 'Gesamtsumme', 13) . $zelle($z, 1, '', 13);
    if ($l['preise']) $c .= $zelle($z, 2, '', 13) . $zelle($z, 3, '', 13);
    $erste = 5; $letzte = $z - 1;
    $f = function (int $sp) use ($z, $erste, $letzte) {
        $sp0 = mhd_spalte($sp);
        return '<c r="' . $sp0 . $z . '" s="14"><f>SUM(' . $sp0 . $erste . ':' . $sp0 . $letzte . ')</f></c>';
    };
    $c .= $f(2 + $off) . $zelle($z, 3 + $off, '', 13) . $f(4 + $off) . $f(5 + $off) . $zelle($z, 6 + $off, '', 13) . $f(7 + $off) . '</row>';
    $rows[] = $c;
    $cols = '<cols>';
    foreach ($breiten as $i => $b) $cols .= '<col min="' . ($i + 1) . '" max="' . ($i + 1) . '" width="' . $b . '" customWidth="1"/>';
    $cols .= '</cols>';
    $letzteSp = mhd_spalte(count($kopf) - 1);
    $blatt = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        . '<sheetViews><sheetView workbookViewId="0"><pane ySplit="4" topLeftCell="A5" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        . $cols . '<sheetData>' . implode('', $rows) . '</sheetData>'
        . ($l['zeilen'] ? '<autoFilter ref="A4:' . $letzteSp . $letzte . '"/>' : '')
        . '<pageMargins left="0.4" right="0.4" top="0.5" bottom="0.5" header="0.3" footer="0.3"/><pageSetup paperSize="9" orientation="landscape" fitToHeight="0"/></worksheet>';
    $mappe = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        . '<sheets><sheet name="MHD-Liste" sheetId="1" r:id="rId1"/></sheets>'
        . ($l['zeilen'] ? '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">\'MHD-Liste\'!$A$4:$' . $letzteSp . '$' . $letzte . '</definedName></definedNames>' : '')
        . '</workbook>';
    return mhd_zip([
        '[Content_Types].xml' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            . '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
            . '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            . '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            . '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>',
        '_rels/.rels' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            . '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        'xl/workbook.xml' => $mappe,
        'xl/_rels/workbook.xml.rels' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            . '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            . '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>',
        'xl/worksheets/sheet1.xml' => $blatt,
        'xl/styles.xml' => $styles,
    ]);
}

/* Bild der Liste aus dem Browser prüfen (nur PNG, Größe begrenzt). Rückgabe: PNG-Daten. */
function mhd_bild_pruefen($b64): string
{
    if (!is_string($b64) || $b64 === '') fail('Das Bild der MHD-Liste fehlt.', 422);
    $b64 = preg_replace('#^data:image/png;base64,#', '', $b64) ?? '';
    if (strlen($b64) > 8 * 1024 * 1024) fail('Das Bild der MHD-Liste ist zu groß.', 413);
    $png = base64_decode($b64, true);
    if ($png === false || strncmp($png, "\x89PNG\r\n\x1a\n", 8) !== 0) fail('Das Bild der MHD-Liste ist ungültig.', 422);
    $info = @getimagesizefromstring($png);
    if (!$info || $info[2] !== IMAGETYPE_PNG || $info[0] < 100 || $info[0] > 4000 || $info[1] < 50 || $info[1] > 30000) fail('Das Bild der MHD-Liste ist ungültig.', 422);
    return $png;
}

/* E-Mail an den Verkauf: Text, HTML mit eingebettetem Bild (cid), Excel im Anhang. Rückgabe [Betreff, Text, HTML, Anhänge, Dateiname] */
function mhd_mail(array $l, string $png, string $notiz, array $me, array $st): array
{
    global $CFG;
    $datum = date('d.m.Y', strtotime($l['heute']));
    $bis = date('d.m.Y', strtotime($l['bis']));
    $n = count($l['zeilen']);
    $kg = array_sum(array_map(function ($a) { return (int)round($a['mhdKg'] * 1000); }, $l['zeilen'])) / 1000;
    $abgl = count(array_filter($l['zeilen'], function ($a) { return $a['stufe'] === 'abgelaufen'; }));
    $subject = "MHD-Liste vom $datum: $n Artikel mit MHD bis $bis";
    $datei = 'MHD-Liste_' . $l['heute'] . '.xlsx';
    $kgT = number_format($kg, 2, ',', '.') . ' kg';
    $bestand = !empty($st['date']) ? date('d.m.Y', strtotime((string)$st['date'])) : '–';
    $text = "Hallo,\n\nanbei die MHD-Liste vom $datum (Bestand vom $bestand): $n Artikel mit MHD bis $bis, davon $abgl bereits abgelaufen; $kgT mit dem kürzesten MHD.\n"
        . ($notiz !== '' ? "\nHinweis von {$me['name']}:\n$notiz\n" : '')
        . "\nDie vollständige Liste steht als Excel-Datei im Anhang ($datei).\n\n";
    foreach (array_slice($l['zeilen'], 0, 200) as $a) {
        $text .= str_pad($a['code'], 8) . ' ' . date('d.m.y', strtotime($a['mhd'])) . '  ' . str_pad(number_format($a['mhdKg'], 2, ',', '.') . ' kg', 12, ' ', STR_PAD_LEFT) . '  ' . $a['name'] . "\n";
    }
    $text .= "\nGesendet von {$me['name']} über die STAFL-Plattform (Bestand). Intern – nicht an Kunden weitergeben.\n";
    $kopf = '<p style="margin:0 0 6px;">Hallo,</p><p style="margin:0 0 14px;">anbei die MHD-Liste vom <strong>' . mail_h($datum) . '</strong> (Bestand vom ' . mail_h($bestand) . '): <strong>' . $n . ' Artikel</strong> mit MHD bis ' . mail_h($bis)
        . ($abgl ? ', davon <strong style="color:#8f1d14;">' . $abgl . ' bereits abgelaufen</strong>' : '') . '; ' . mail_h($kgT) . ' mit dem kürzesten MHD.</p>'
        . ($notiz !== '' ? '<p style="margin:0 0 14px;padding:10px 12px;background:#f4f1ec;border-radius:8px;"><strong>Hinweis von ' . mail_h($me['name']) . ':</strong><br>' . nl2br(mail_h($notiz)) . '</p>' : '');
    $bildHtml = '<img src="cid:mhd-liste" alt="MHD-Liste vom ' . mail_h($datum) . '" width="100%" style="display:block;width:100%;max-width:1100px;height:auto;border:1px solid #e6e0d8;border-radius:6px;">';
    $fuss = '<p style="margin:14px 0 0;color:#857c72;font-size:13px;">Die vollständige Liste steht als Excel-Datei im Anhang (' . mail_h($datei) . ').<br>Gesendet von ' . mail_h($me['name']) . ' über die STAFL-Plattform (Bestand). Intern – nicht an Kunden weitergeben.</p>';
    /* Eigene, breite Hülle: das Bild braucht mehr Platz als die 560 px der Standardvorlage */
    $html = '<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' . mail_h($subject) . '</title></head>'
        . '<body style="margin:0;padding:0;background:#f4f1ec;font-family:Arial,Helvetica,sans-serif;color:#1d1a17;">'
        . '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1ec;padding:20px 8px;"><tr><td align="center">'
        . '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:1140px;background:#ffffff;border-radius:12px;border:1px solid #e6e0d8;">'
        . '<tr><td style="padding:20px 20px 0;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7b1e2b;font-weight:bold;">' . mail_h((string)($CFG['company'] ?? '')) . ' · MHD-Liste</td></tr>'
        . '<tr><td style="padding:10px 20px 20px;font-size:15px;line-height:1.55;">' . $kopf . $bildHtml . $fuss . '</td></tr></table></td></tr></table></body></html>';
    $anhaenge = [
        ['name' => 'MHD-Liste_' . $l['heute'] . '.png', 'type' => 'image/png', 'data' => $png, 'cid' => 'mhd-liste'],
        ['name' => $datei, 'type' => 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'data' => mhd_xlsx($l, ($CFG['company'] ?? '') . ' · MHD-Liste vom ' . $datum . ' (Bestand vom ' . $bestand . ')')],
    ];
    return [$subject, $text, $html, $anhaenge, $datei];
}
