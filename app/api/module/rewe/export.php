<?php
declare(strict_types=1);
/* REWE · Wochenabschluss und Excel für die Warenwirtschaft (Aktionen rewe_abschluss, rewe_export, rewe_erfasst).
   rw_abschluss: alle Bestellungen einer KW über alle Listen – Zeilen je Markt und Artikel, Summen je Lieferweg, je
   Mitarbeiter und je Artikel, offene Märkte (in der Abfrage ohne Antwort), Hinweise (fällige Daueraufträge ohne Antwort,
   Artikel ohne WinAB-Nummer, Nachträge nach dem Export) und den Stand des Abschlusses (exportiert, in WinAB erfasst).
   In WinAB wird von Hand erfasst, immer als Einzelauftrag je Markt (Inhaber 30.10.2026): jede Zeile trägt die Nummer ihres
   Auftrags (ein Auftrag = ein Markt der Woche, Positionen = Artikel).
   rw_xlsx: Arbeitsmappe mit den Blättern „WinAB-Erfassung“, „Je Lieferweg“, „Je Mitarbeiter“ – ohne PHP-Erweiterung „zip“
   (das Produktions-Image hat sie nicht): Office-Open-XML-Teile unkomprimiert in einem ZIP-Archiv, Werte statt Formeln.
   Lieferweg und Zuständigkeit stammen aus dem Schnappschuss der Antwort (GR-106), Name und Anschrift aus dem Markt. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

function rw_abschluss(string $kw): array
{
    $stamm = rw_stamm(); $namen = rw_namen();
    $jahr = (int)substr($kw, 0, 4); $ww = substr($kw, 5, 2);
    $w = rw_wochen_doc($jahr);
    $zeilen = []; $jeLw = []; $jePerson = []; $jeArtikel = []; $offen = []; $dauerOffen = []; $nachtraege = 0;
    $lwName = function ($id) use ($stamm) { $l = rw_lieferweg($stamm, $id); return $l ? $l['name'] : 'Ohne Lieferweg'; };
    foreach (rw_maerkte_doc()['liste'] as $m) {
        $e = rw_antwort($w, $m['id'], $kw);
        if (!$e) {
            $faellig = rw_dauer_faellig($m, $kw);
            $an = rw_anzeige($m);
            if ($faellig) $dauerOffen[] = ['id' => $m['id'], 'name' => $an['name'], 'ort' => $an['ort'], 'zustaendig' => $namen[rw_zustaendig($m, $kw)] ?? ''];
            // Dauerauftrag in dieser Woche nicht fällig: keine Lieferung vorgesehen, also nicht offen (wie in „Meine Woche“)
            elseif (in_array($m['kauf'] ?? 'regelmaessig', RW_KAUF_ABFRAGE, true) && rw_dauer_naechste($m, $kw) === '')
                $offen[] = ['id' => $m['id'], 'name' => $an['name'], 'ort' => $an['ort'], 'zustaendig' => $namen[rw_zustaendig($m, $kw)] ?? '', 'lieferweg' => $lwName(rw_lw($m, $kw))];
            continue;
        }
        if (($e['s'] ?? '') !== 'bestellt') continue;
        $lw = (string)($e['lw'] ?? rw_lw($m, $kw)); $person = (string)($e['zuName'] ?? '') ?: '(niemand)';
        if (!empty($e['nachtrag'])) $nachtraege++;
        $an = rw_anzeige($m);
        $jeLw[$lw]['maerkte'] = ($jeLw[$lw]['maerkte'] ?? 0) + 1;
        $jePerson[$person]['maerkte'] = ($jePerson[$person]['maerkte'] ?? 0) + 1;
        foreach ($stamm['artikel'] as $a) {
            $n = (int)($e['m'][$a['id']] ?? 0);
            if (!$n) continue;
            $zeilen[] = ['lieferweg' => $lwName($lw), 'lieferwegId' => $lw, 'kdNr' => (string)($m['kdNr'] ?? ''), 'reweNr' => (string)($m['reweNr'] ?? ''), 'markt' => $an['name'],
                         'plz' => $an['plz'], 'ort' => $an['ort'], 'strasse' => $an['strasse'], 'winab' => $an['winab'], 'artikel' => $a['name'], 'artikelId' => $a['id'],
                         'nr' => (string)$a['nr'], 'menge' => $n, 'einheit' => (string)$a['einheit'], 'ohneBerechnung' => !empty($e['ob']), 'zustaendig' => $person,
                         'notiz' => (string)($e['n'] ?? ''), 'quelle' => (string)($e['q'] ?? 'hand'), 'nachtrag' => !empty($e['nachtrag']), 'marktId' => $m['id']];
            $jeLw[$lw]['mengen'][$a['id']] = ($jeLw[$lw]['mengen'][$a['id']] ?? 0) + $n;
            $jePerson[$person]['mengen'][$a['id']] = ($jePerson[$person]['mengen'][$a['id']] ?? 0) + $n;
            $jeArtikel[$a['id']] = ($jeArtikel[$a['id']] ?? 0) + $n;
        }
    }
    $rang = function ($id) use ($stamm) { $l = rw_lieferweg($stamm, $id); return $l ? ($l['art'] === 'lager' ? 0 : 1) : 2; };
    $artRang = array_flip(array_column($stamm['artikel'], 'id'));
    usort($zeilen, function ($a, $b) use ($rang, $artRang) { return [$rang($a['lieferwegId']), $a['lieferweg'], $a['kdNr'], $a['markt'], $a['marktId'], $artRang[$a['artikelId']] ?? 99] <=> [$rang($b['lieferwegId']), $b['lieferweg'], $b['kdNr'], $b['markt'], $b['marktId'], $artRang[$b['artikelId']] ?? 99]; });
    // Einzelaufträge: ein Auftrag je Markt, fortlaufend in der Reihenfolge der Liste
    $nr = 0; $vorher = '';
    foreach ($zeilen as &$r) { if ($r['marktId'] !== $vorher) { $nr++; $vorher = $r['marktId']; } $r['auftrag'] = $nr; }
    unset($r);
    $lwListe = [];
    foreach ($jeLw as $id => $x) $lwListe[] = ['id' => $id, 'name' => $lwName($id), 'maerkte' => $x['maerkte'], 'mengen' => $x['mengen'] ?? []];
    usort($lwListe, function ($a, $b) use ($rang) { return [$rang($a['id']), $a['name']] <=> [$rang($b['id']), $b['name']]; });
    $pListe = [];
    foreach ($jePerson as $name => $x) $pListe[] = ['name' => (string)$name, 'maerkte' => $x['maerkte'], 'mengen' => $x['mengen'] ?? []];
    usort($pListe, function ($a, $b) { return strcasecmp($a['name'], $b['name']); });
    $ohneNr = array_values(array_map(function ($a) { return $a['name']; }, array_filter($stamm['artikel'], function ($a) use ($jeArtikel) { return !empty($jeArtikel[$a['id']]) && $a['nr'] === ''; })));
    $ab = $w['abschluss'][$ww] ?? [];
    return ['kw' => $kw, 'kwText' => rw_kw_text($kw), 'zeitraum' => rw_kw_zeitraum($kw), 'zeilen' => $zeilen, 'lieferwege' => $lwListe, 'personen' => $pListe,
            'artikel' => (object)$jeArtikel, 'maerkte' => count(array_unique(array_column($zeilen, 'marktId'))), 'offen' => $offen, 'dauerOffen' => $dauerOffen,
            'ohneStamm' => count(array_unique(array_column(array_filter($zeilen, function ($r) { return !$r['winab']; }), 'marktId'))),
            'ohneNr' => $ohneNr, 'nachtraege' => $nachtraege, 'exportiert' => $ab['exportiert'] ?? null, 'erfasst' => $ab['erfasst'] ?? null];
}

/* Wochenabschluss vermerken (unter der Sperre): exportiert bzw. in WinAB erfasst */
function rw_abschluss_setzen(string $kw, string $feld, ?array $wert): array
{
    $jahr = (int)substr($kw, 0, 4); $ww = substr($kw, 5, 2);
    $w = rw_wochen_doc($jahr);
    $ab = $w['abschluss'][$ww] ?? [];
    $ab[$feld] = $wert;
    if ($feld === 'exportiert' && $wert) {   // ab jetzt sind Änderungen Nachträge; frühere Nachträge sind mit exportiert
        foreach ($w['maerkte'] as $mid => $wochen) if (isset($wochen[$ww]['nachtrag'])) unset($w['maerkte'][$mid][$ww]['nachtrag']);
    }
    $w['abschluss'][$ww] = $ab;
    rw_wochen_schreiben($jahr, $w);
    return $ab;
}

/* ---------------- Excel ---------------- */
function rw_zip(array $dateien): string
{
    $daten = ''; $verz = ''; $n = 0;
    foreach ($dateien as $name => $inhalt) {
        $crc = crc32($inhalt); $len = strlen($inhalt); $off = strlen($daten);
        $kopf = pack('vvvvvVVVvv', 20, 0x0800, 0, 0, 0x21, $crc, $len, $len, strlen($name), 0);
        $daten .= "PK\x03\x04" . $kopf . $name . $inhalt;
        $verz .= "PK\x01\x02" . pack('vvvvvvVVVvvvvvVV', 20, 20, 0x0800, 0, 0, 0x21, $crc, $len, $len, strlen($name), 0, 0, 0, 0, 0, $off) . $name;
        $n++;
    }
    return $daten . $verz . "PK\x05\x06" . pack('vvvvVVv', 0, 0, $n, $n, strlen($verz), strlen($daten), 0);
}
function rw_xl_spalte(int $n): string { $s = ''; for ($n++; $n > 0; $n = intdiv($n - 1, 26)) $s = chr(65 + ($n - 1) % 26) . $s; return $s; }
function rw_xl_text(string $t): string
{
    $t = preg_replace('/[\x00-\x08\x0b\x0c\x0e-\x1f]/', '', $t) ?? '';
    return htmlspecialchars($t, ENT_XML1 | ENT_QUOTES, 'UTF-8');
}
/* Stile: 0 Standard, 1 Kopfzeile (fett, weiß auf Bordeaux), 2 Titel (fett, groß), 3 Hinweis (kursiv grau), 4 fett */
function rw_xl_stile(): string
{
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n"
        . '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        . '<fonts count="5"><font><sz val="10"/><name val="Arial"/><family val="2"/></font>'
        . '<font><b/><sz val="10"/><color rgb="FFFFFFFF"/><name val="Arial"/><family val="2"/></font>'
        . '<font><b/><sz val="14"/><name val="Arial"/><family val="2"/></font>'
        . '<font><i/><sz val="10"/><color rgb="FF5F5955"/><name val="Arial"/><family val="2"/></font>'
        . '<font><b/><sz val="10"/><name val="Arial"/><family val="2"/></font></fonts>'
        . '<fills count="3"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill>'
        . '<fill><patternFill patternType="solid"><fgColor rgb="FF8C1D2C"/><bgColor indexed="64"/></patternFill></fill></fills>'
        . '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        . '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        . '<cellXfs count="5"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        . '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
        . '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        . '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        . '<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1"/></cellXfs>'
        . '<cellStyles count="1"><cellStyle name="Standard" xfId="0" builtinId="0"/></cellStyles></styleSheet>';
}
/* Ein Blatt: $zeilen = Liste von Zeilen, Zelle = Wert oder [Wert, Stil]; $kopf = Zeilennummer (1-basiert) der Kopfzeile */
function rw_xl_blatt(array $zeilen, array $breiten, int $kopf): string
{
    $xml = '';
    foreach ($zeilen as $zi => $zeile) {
        $r = $zi + 1;
        $xml .= '<row r="' . $r . '"' . ($r === $kopf ? ' ht="28" customHeight="1"' : '') . '>';
        foreach ($zeile as $si => $zelle) {
            [$wert, $stil] = is_array($zelle) ? $zelle : [$zelle, $r === $kopf ? 1 : 0];
            $ref = rw_xl_spalte($si) . $r;
            if ($wert === null || $wert === '') $xml .= $stil ? '<c r="' . $ref . '" s="' . $stil . '"/>' : '';
            elseif (is_int($wert) || is_float($wert)) $xml .= '<c r="' . $ref . '" s="' . $stil . '"><v>' . $wert . '</v></c>';
            else $xml .= '<c r="' . $ref . '" s="' . $stil . '" t="inlineStr"><is><t xml:space="preserve">' . rw_xl_text((string)$wert) . '</t></is></c>';
        }
        $xml .= '</row>';
    }
    $cols = '';
    foreach ($breiten as $i => $b) $cols .= '<col min="' . ($i + 1) . '" max="' . ($i + 1) . '" width="' . $b . '" customWidth="1"/>';
    $letzte = max(1, count($zeilen));
    $filter = $kopf > 0 && $letzte > $kopf ? '<autoFilter ref="A' . $kopf . ':' . rw_xl_spalte(count($breiten) - 1) . $letzte . '"/>' : '';
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n"
        . '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        . '<sheetViews><sheetView workbookViewId="0">' . ($kopf > 0 ? '<pane ySplit="' . $kopf . '" topLeftCell="A' . ($kopf + 1) . '" activePane="bottomLeft" state="frozen"/>' : '') . '</sheetView></sheetViews>'
        . '<cols>' . $cols . '</cols><sheetData>' . $xml . '</sheetData>' . $filter
        . '<pageMargins left="0.4" right="0.4" top="0.5" bottom="0.5" header="0.3" footer="0.3"/><pageSetup paperSize="9" orientation="landscape" fitToHeight="0"/></worksheet>';
}
function rw_xlsx(array $blaetter, string $titel): string
{
    $ct = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        . '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
        . '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        . '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        . '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        . '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>';
    $rels = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">';
    $sheets = ''; $dateien = [];
    foreach (array_values($blaetter) as $i => [$name, $xml]) {
        $n = $i + 1;
        $ct .= '<Override PartName="/xl/worksheets/sheet' . $n . '.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>';
        $rels .= '<Relationship Id="rId' . $n . '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet' . $n . '.xml"/>';
        $sheets .= '<sheet name="' . rw_xl_text(mb_substr($name, 0, 31)) . '" sheetId="' . $n . '" r:id="rId' . $n . '"/>';
        $dateien['xl/worksheets/sheet' . $n . '.xml'] = $xml;
    }
    $k = count($blaetter) + 1;
    $rels .= '<Relationship Id="rId' . $k . '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>';
    $ct .= '</Types>';
    $jetzt = gmdate('Y-m-d\TH:i:s\Z');
    return rw_zip([
        '[Content_Types].xml' => $ct,
        '_rels/.rels' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            . '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            . '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            . '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>',
        'docProps/core.xml' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            . '<dc:title>' . rw_xl_text($titel) . '</dc:title><dc:creator>STAFL-Plattform · REWE</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">' . $jetzt . '</dcterms:created></cp:coreProperties>',
        'docProps/app.xml' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>STAFL-Plattform</Application></Properties>',
        'xl/workbook.xml' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            . '<bookViews><workbookView/></bookViews><sheets>' . $sheets . '</sheets></workbook>',
        'xl/_rels/workbook.xml.rels' => $rels,
        'xl/styles.xml' => rw_xl_stile(),
    ] + $dateien);
}
/* Arbeitsmappe des Wochenabschlusses; Texte, die mit = + - @ beginnen, bleiben Text (inlineStr, keine Formeln) */
function rw_export_xlsx(array $a, array $stamm, string $wer): string
{
    $zeitraum = date('d.m.Y', strtotime($a['zeitraum']['von'])) . '–' . date('d.m.Y', strtotime($a['zeitraum']['bis']));
    $titel = 'REWE Dry Aged – Erfassung in WinAB · ' . $a['kwText'];
    $kopf = ['Auftrag', 'Lieferweg', 'Liefer-KW', 'Kd.-Nr. (WinAB)', 'REWE-Markt-Nr.', 'Markt', 'PLZ', 'Ort', 'Straße', 'WinAB-Art.-Nr.', 'Artikel', 'Menge', 'Einheit',
             'Ohne Berechnung', 'Erfasst von', 'Notiz', 'Nachtrag'];
    $z = [[[$titel, 2]], [['Lieferwoche ' . $zeitraum . ' · erstellt ' . date('d.m.Y H:i') . ' von ' . $wer . ' · ' . $a['maerkte'] . ' Einzelaufträge (je Markt einer), ' . count($a['zeilen']) . ' Positionen', 3]], [], $kopf];
    foreach ($a['zeilen'] as $r) {
        $z[] = [$r['auftrag'], $r['lieferweg'], $a['kwText'], ctype_digit($r['kdNr']) && $r['kdNr'] !== '' ? (int)$r['kdNr'] : $r['kdNr'], ctype_digit($r['reweNr']) && $r['reweNr'] !== '' ? (int)$r['reweNr'] : $r['reweNr'],
                $r['markt'], $r['plz'], $r['ort'], $r['strasse'], $r['nr'], $r['artikel'], $r['menge'], $r['einheit'], $r['ohneBerechnung'] ? 'ja' : 'nein',
                $r['zustaendig'], $r['notiz'], $r['nachtrag'] ? 'ja' : ''];
    }
    $summe = array_sum(array_column($a['zeilen'], 'menge'));
    $z[] = [];
    $z[] = ['', '', '', '', '', ['Summe', 4], '', '', '', '', '', [$summe, 4]];
    $blaetter = [['WinAB-Erfassung', rw_xl_blatt($z, [9, 20, 12, 15, 15, 26, 8, 22, 28, 14, 20, 8, 9, 13, 16, 30, 10], 4)]];
    foreach ([['Je Lieferweg', 'Lieferweg', $a['lieferwege']], ['Je Mitarbeiter', 'Mitarbeiter', $a['personen']]] as [$blatt, $spalte, $liste]) {
        $art = array_values(array_filter($stamm['artikel'], function ($x) use ($a) { return !empty(((array)$a['artikel'])[$x['id']]); }));
        $s = [[[$a['kwText'] . ' · ' . $blatt, 2]], [], array_merge([$spalte, 'Märkte'], array_column($art, 'name'))];
        foreach ($liste as $x) {
            $s[] = array_merge([$x['name'], $x['maerkte']], array_map(function ($ar) use ($x) { return (int)($x['mengen'][$ar['id']] ?? 0); }, $art));
        }
        $s[] = array_merge([['Summe', 4], [array_sum(array_column($liste, 'maerkte')), 4]],
                           array_map(function ($ar) use ($a) { return [(int)(((array)$a['artikel'])[$ar['id']] ?? 0), 4]; }, $art));
        $blaetter[] = [$blatt, rw_xl_blatt($s, array_merge([24, 10], array_fill(0, count($art), 16)), 3)];
    }
    return rw_xlsx($blaetter, $titel);
}
