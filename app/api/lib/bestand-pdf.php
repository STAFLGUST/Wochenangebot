<?php
declare(strict_types=1);
/* Bestand als PDF (Verwaltung → Bestand → „PDF“): A4 hoch, nur Art.-Nr., Bezeichnung (Merkmale aus den Stammdaten grau
   dahinter), eingelagerter Bestand, kürzestes MHD
   und Kg kürz. MHD – ohne Preise, erfassten Bestand, Gesamt verfügbar und erwartete Zugänge (zum Weitergeben, z. B. an den
   Verkauf). Reihenfolge und Warengruppen kommen aus der Ansicht (Suche/Sortierung wie am Bildschirm), die Zahlen immer aus dem
   gespeicherten Bestand. Nur bei Bedarf geladen (require_once aus aktionen/bestand.php). */
if (!defined('WA_API')) { http_response_code(404); exit; }
require_once __DIR__ . '/pdf.php';

/* MHD-Stufe relativ zu heute (deutsche Zeit) – wie mhdClass() im Eingabebereich */
function stock_pdf_stufe(?string $mhd): string
{
    if (!$mhd) return '';
    $tage = (int)round((strtotime($mhd . ' 12:00:00') - strtotime(date('Y-m-d') . ' 12:00:00')) / 86400);
    return $tage < 0 ? 'past' : ($tage <= 4 ? '0-4' : ($tage <= 7 ? '5-7' : ($tage <= 14 ? '8-14' : '')));
}
/* Farben wie in der Ansicht (helle Töne): [Hintergrund, Schrift] */
const STOCK_PDF_FARBEN = ['past' => ['#d9d6d2', '#1f1d1a'], '0-4' => ['#fbe0dd', '#8f1d14'], '5-7' => ['#fde7d3', '#7a3209'], '8-14' => ['#fbf0c9', '#6b4a05']];
const STOCK_PDF_STUFEN = ['past' => 'abgelaufen', '0-4' => 'heute – 4 Tage', '5-7' => '5 – 7 Tage', '8-14' => '8 – 14 Tage'];

/* $zeilen: [['g' => Warengruppe] | ['c' => Artikelnummer], …] in der Reihenfolge der Ansicht; $zusatz: Suche/MHD-Auswahl für den Titel */
function stock_pdf(array $st, array $zeilen, string $zusatz = ''): string
{
    global $CFG;
    $norm = fn(string $c) => ctype_digit($c) ? (ltrim($c, '0') === '' ? '0' : ltrim($c, '0')) : strtoupper($c);
    $art = [];
    foreach ($st['articles'] ?? [] as $a) $art[$norm((string)$a['code'])] = $a;

    // Bausteine: Gruppenkopf, Artikel, Gruppensumme; Summen nur über Artikel mit eingelagertem Bestand
    $teile = []; $gruppe = null; $gKg = $gMkg = 0; $gesKg = $gesMkg = 0; $anzahl = 0; $inGruppe = 0;
    $schliessen = function () use (&$teile, &$gruppe, &$gKg, &$gMkg, &$inGruppe) {
        if ($gruppe !== null && $inGruppe) $teile[] = ['t' => 'sum', 'label' => 'Summe ' . $gruppe, 'kg' => $gKg / 1000, 'mkg' => $gMkg / 1000];
        elseif ($gruppe !== null && $teile && end($teile)['t'] === 'g') array_pop($teile);   // leere Gruppe weglassen
        $gKg = $gMkg = 0; $inGruppe = 0;
    };
    foreach ($zeilen as $z) {
        if (isset($z['g'])) { $schliessen(); $gruppe = (string)$z['g']; $teile[] = ['t' => 'g', 'label' => $gruppe]; continue; }
        $a = $art[$norm((string)($z['c'] ?? ''))] ?? null;
        if (!$a || !((float)($a['kg'] ?? 0) > 0)) continue;   // nur eingelagerter Bestand
        $kg = (int)round((float)$a['kg'] * 1000); $mkg = $a['mhdKg'] !== null ? (int)round((float)$a['mhdKg'] * 1000) : 0;
        $gKg += $kg; $gMkg += $mkg; $gesKg += $kg; $gesMkg += $mkg; $anzahl++; $inGruppe++;
        $teile[] = ['t' => 'a', 'a' => $a, 'stufe' => stock_pdf_stufe($a['mhd'] ?? null)];
    }
    $schliessen();
    if ($anzahl) $teile[] = ['t' => 'total', 'label' => 'Gesamtsumme', 'kg' => $gesKg / 1000, 'mkg' => $gesMkg / 1000];

    $pdf = new Pdf(595.28, 841.89);   // A4 hoch
    $W = $pdf->w; $H = $pdf->h;
    $ML = 34; $MR = 34; $MT = 30; $MB = 38;
    $x0 = $ML; $x1 = $W - $MR;
    // Spalten: Art.-Nr. | Bezeichnung | Eingelagerter Bestand | Kürz. MHD | Kg kürz. MHD
    $cCode = $x0 + 4; $cName = $x0 + 52; $cKg = $x1 - 172; $cMhd = $x1 - 136; $cMkg = $x1 - 4;
    $wName = $cKg - 78 - $cName;
    $FS = 8.6; $RH = 15.2;
    $kg = fn(float $v) => number_format($v, 2, ',', '.') . ' kg';
    $fit = function (string $t, float $size, float $max, bool $bold = false): string {
        if (Pdf::width($t, $size, $bold) <= $max) return $t;
        while ($t !== '' && Pdf::width($t . '…', $size, $bold) > $max) $t = mb_substr($t, 0, -1);
        return rtrim($t) . '…';
    };
    $titel = 'Bestand vom ' . (!empty($st['date']) ? date('d.m.Y', strtotime($st['date'])) : '?') . $zusatz;
    $firma = (string)($CFG['company'] ?? '');
    $meta = $anzahl . ' Artikel' . ' · eingelagerter Bestand ohne Preise und Zugänge · erstellt ' . date('d.m.Y, H:i') . ' Uhr';

    // Seiten vorab einteilen (für „Seite x von y“): Kopf auf Seite 1 höher (Logo, Legende)
    $kopf1 = 92; $kopfN = 50; $tabKopf = 22;
    $seiten = [[]]; $y = $MT + $kopf1 + $tabKopf;
    foreach ($teile as $i => $t) {
        $h = $t['t'] === 'g' ? $RH + 4 : $RH;
        $naechste = $teile[$i + 1] ?? null;
        $mit = $t['t'] === 'g' && $naechste && $naechste['t'] === 'a' ? $RH : 0;   // Gruppenkopf nie allein am Seitenende
        if ($y + $h + $mit > $H - $MB) { $seiten[] = []; $y = $MT + $kopfN + $tabKopf; }
        $seiten[count($seiten) - 1][] = $t; $y += $h;
    }
    $n = count($seiten);

    foreach ($seiten as $p => $liste) {
        if ($p) $pdf->addPage();
        $y = $MT;
        if ($p === 0) {
            $lh = $pdf->jpeg(__DIR__ . '/druck-logo.jpg', $x0, $y, 120);
            $pdf->text($x1, $y + 14, $titel, 14, true, '#1b1a18', 'r');
            $pdf->text($x1, $y + 28, $meta, 7.8, false, '#5f5b55', 'r');
            $pdf->text($x1, $y + 39, 'Intern – nur für den Verkauf; Mengen ohne Gewähr (Stand der Bestandsliste).', 7.8, false, '#5f5b55', 'r');
            // Legende
            $ly = $y + max($lh, 40) + 12; $lx = $x0;
            $pdf->text($lx, $ly + 8, 'MHD:', 8, true, '#1b1a18'); $lx += 26;
            foreach (STOCK_PDF_STUFEN as $k => $l) {
                $w = Pdf::width($l, 7.8, true) + 12;
                $pdf->rect($lx, $ly, $w, 11, STOCK_PDF_FARBEN[$k][0]);
                $pdf->text($lx + 6, $ly + 8, $l, 7.8, true, STOCK_PDF_FARBEN[$k][1]);
                $lx += $w + 6;
            }
            $y += $kopf1;
        } else {
            $pdf->text($x0, $y + 12, ($firma !== '' ? $firma . ' · ' : '') . $titel, 10.5, true, '#1b1a18');
            $pdf->text($x0, $y + 25, 'Fortsetzung', 7.8, false, '#5f5b55');
            $y += $kopfN;
        }
        // Tabellenkopf
        $pdf->text($cCode, $y + 12, 'Art.-Nr.', 7.8, true, '#1b1a18');
        $pdf->text($cName, $y + 12, 'Art. Bezeichnung', 7.8, true, '#1b1a18');
        $pdf->text($cKg, $y + 12, 'Eingelagerter Bestand', 7.8, true, '#1b1a18', 'r');
        $pdf->text($cMhd + 4, $y + 12, 'Kürz. MHD', 7.8, true, '#1b1a18');
        $pdf->text($cMkg, $y + 12, 'Kg kürz. MHD', 7.8, true, '#1b1a18', 'r');
        $pdf->line($x0, $y + 17, $x1, $y + 17, 1, '#8a857e');
        $y += $tabKopf;
        if (!$teile) $pdf->text($x0, $y + 14, 'Keine Artikel mit eingelagertem Bestand in dieser Auswahl.', 9, false, '#5f5b55');
        foreach ($liste as $t) {
            if ($t['t'] === 'g') {
                $pdf->rect($x0, $y + 2, $x1 - $x0, $RH, '#efece8');
                $pdf->text($cCode, $y + 13, $fit($t['label'], 9, $x1 - $x0 - 10, true), 9, true, '#1b1a18');
                $y += $RH + 4; continue;
            }
            if ($t['t'] === 'sum' || $t['t'] === 'total') {
                $pdf->rect($x0, $y, $x1 - $x0, $RH, $t['t'] === 'total' ? '#e4e0da' : '#f5f3f0');
                if ($t['t'] === 'total') $pdf->line($x0, $y, $x1, $y, 1.2, '#3a3733');
                $pdf->text($cCode, $y + 10.6, $fit($t['label'], $FS, $cKg - 80 - $cCode, true), $FS, true, '#1b1a18');
                $pdf->text($cKg, $y + 10.6, $kg($t['kg']), $FS, true, '#1b1a18', 'r');
                $pdf->text($cMkg, $y + 10.6, $kg($t['mkg']), $FS, true, '#1b1a18', 'r');
                $y += $RH + ($t['t'] === 'sum' ? 3 : 0); continue;
            }
            $a = $t['a']; $f = STOCK_PDF_FARBEN[$t['stufe']] ?? null;
            if ($f) $pdf->rect($cMhd, $y + .6, $x1 - $cMhd, $RH - 1.2, $f[0]);
            $pdf->text($cCode, $y + 10.6, $fit((string)$a['code'], $FS, 44), $FS, false, '#3d3a36');
            $name = $fit((string)$a['name'], $FS, $wName);
            $pdf->text($cName, $y + 10.6, $name, $FS, false, '#1b1a18');
            // Merkmale aus den Stammdaten (Fleischart · Herkunft · Zustand) grau dahinter, soweit Platz ist
            $merk = trim((string)($a['merkmale'] ?? '')); $nb = Pdf::width($name, $FS);
            if ($merk !== '' && $wName - $nb - 6 > 24) $pdf->text($cName + $nb + 6, $y + 10.6, $fit($merk, 7.4, $wName - $nb - 6), 7.4, false, '#6f6a63');
            $pdf->text($cKg, $y + 10.6, $kg((float)$a['kg']), $FS, false, '#1b1a18', 'r');
            $pdf->text($cMhd + 4, $y + 10.6, !empty($a['mhd']) ? date('d.m.y', strtotime($a['mhd'])) : '—', $FS, (bool)$f, $f[1] ?? '#1b1a18');
            $pdf->text($cMkg, $y + 10.6, $a['mhdKg'] !== null ? $kg((float)$a['mhdKg']) : '—', $FS, true, $f[1] ?? '#1b1a18', 'r');
            $pdf->line($x0, $y + $RH, $x1, $y + $RH, .3, '#e2ded8');
            $y += $RH;
        }
        // Fußzeile
        $pdf->line($x0, $H - $MB + 10, $x1, $H - $MB + 10, .4, '#c9c4bd');
        $pdf->text($x0, $H - $MB + 22, ($firma !== '' ? $firma . ' · ' : '') . $titel, 7.5, false, '#5f5b55');
        $pdf->text($x1, $H - $MB + 22, 'Seite ' . ($p + 1) . ' von ' . $n, 7.5, false, '#5f5b55', 'r');
    }
    return $pdf->output($titel);
}
function stock_pdf_name(array $st, string $art = ''): string
{
    return 'Bestand_' . (!empty($st['date']) ? $st['date'] : date('Y-m-d')) . ($art !== '' ? '_' . $art : '') . '.pdf';
}
