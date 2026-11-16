<?php
declare(strict_types=1);
/* QM-System · Organigramm als gelenktes Dokument (Entscheidung des Inhabers 16.11.2026 „Im QM-System zeichnen“; nur bei
   Bedarf geladen von app/api/aktionen/qs.php). Die Struktur liegt als optionales Feld „organigramm“ an einer Version in
   qs-dokumente. Ein Dokument ist ein Organigramm, sobald eine seiner Versionen das Feld trägt – keine Einstellung, keine feste Nummer.
     knoten  Stellen und Funktionen (1 bis 300): id, titel, personen (Kürzel der QM-Personen), vertretung (Kürzel), ueber
             (übergeordnete Stelle, '' = oberste Ebene), art ('linie' | 'stab' = Stabsstelle oder Beauftragte seitlich an der
             Linie, ohne eigene untergeordnete Stellen), hinweis. Die Reihenfolge der Liste ist die Reihenfolge unter einer Stelle.
     namen   erst ab der Freigabe: Namen zu den Kürzeln als Schnappschuss (GR-106) – spätere Änderungen der Personen ändern
             die freigegebene Fassung nicht.
   Lenkung wie bei Dateien: ändern nur im Entwurf mit „qs.bearbeiten“ (zählt als Bearbeiter, 4-Augen-Prinzip); Prüfung und
   Freigabe über qs_version_schritt. Die Freigabe legt die PDF-Fassung (A4 quer, Logo, Lenkungsangaben im Fuß) als Datei der
   Version ab (dateien[].organigramm = true). „Überarbeitung beginnen“ übernimmt die Struktur, nicht die PDF. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar
require_once __DIR__ . '/vorlagen.php';

const QS_OG_MAX_KNOTEN = 300;
const QS_OG_MAX_PERSONEN = 10;
const QS_OG_ARTEN = ['linie', 'stab'];
/* Maße der PDF-Fassung in pt, vor dem Einpassen auf die Seite: Kastenbreite, Innenrand, Abstand zwischen Nachbarn, zwischen den
   Ebenen und zwischen den Stabsstellen links und rechts der Linie */
const QS_OG_B = 124.0;
const QS_OG_RAND = 5.0;
const QS_OG_SPALT = 12.0;
const QS_OG_EBENE = 26.0;
const QS_OG_STAB = 30.0;

/* Eingabe → gültige Struktur ohne Namens-Schnappschuss. $alt = bisherige Struktur des Entwurfs: Felder, die diese Fassung
   nicht kennt, bleiben an Knoten mit gleicher Kennung erhalten (GR-006). */
function qs_organigramm_pruefen($v, ?array $alt, array $stamm): array
{
    $liste = is_array($v) ? ($v['knoten'] ?? null) : null;
    if (!is_array($liste) || !array_is_list($liste)) throw new InvalidArgumentException('Organigramm: ungültige Angaben.');
    if (!$liste) throw new InvalidArgumentException('Das Organigramm braucht mindestens eine Stelle.');
    if (count($liste) > QS_OG_MAX_KNOTEN) throw new InvalidArgumentException('Organigramm: höchstens ' . QS_OG_MAX_KNOTEN . ' Stellen.');
    $bekannt = array_map('strval', array_column($stamm['personen'], 'id'));
    $person = function ($x, string $was) use ($bekannt): string {
        $x = qs_kuerzel($x, $was);
        if ($x !== '' && !in_array($x, $bekannt, true)) throw new InvalidArgumentException("$was: „{$x}“ steht nicht in den Personen.");
        return $x;
    };
    $bisher = [];
    foreach ((array)($alt['knoten'] ?? []) as $k) if (is_array($k) && isset($k['id'])) $bisher[(string)$k['id']] = $k;
    $out = [];
    foreach ($liste as $i => $x) {
        $nr = 'Stelle ' . ($i + 1);
        $id = is_array($x) && is_string($x['id'] ?? null) ? $x['id'] : '';
        if (!preg_match('/^[a-z0-9]{1,24}$/D', $id)) throw new InvalidArgumentException("$nr: ungültige Kennung.");
        if (isset($out[$id])) throw new InvalidArgumentException("$nr: Kennung doppelt.");
        $k = ['id' => $id, 'titel' => qs_kuerzel($x['titel'] ?? '', $nr, 120)] + ($bisher[$id] ?? []);
        if ($k['titel'] === '') throw new InvalidArgumentException("$nr: bitte die Stelle bzw. Funktion benennen.");
        $was = "Stelle „{$k['titel']}“";
        $p = $x['personen'] ?? [];
        if (!is_array($p) || count($p) > QS_OG_MAX_PERSONEN) throw new InvalidArgumentException("$was: höchstens " . QS_OG_MAX_PERSONEN . ' Personen.');
        $k['personen'] = array_values(array_unique(array_filter(array_map(fn($y) => $person($y, "$was: Person"), $p), 'strlen')));
        $k['vertretung'] = $person($x['vertretung'] ?? '', "$was: Vertretung");
        $k['ueber'] = is_string($x['ueber'] ?? null) ? $x['ueber'] : '';
        $k['art'] = qs_wahl($x['art'] ?? 'linie', QS_OG_ARTEN, "$was: Art");
        $k['hinweis'] = qs_kuerzel($x['hinweis'] ?? '', "$was: Hinweis", 200);
        $out[$id] = $k;
    }
    foreach ($out as $k) {
        $was = "Stelle „{$k['titel']}“";
        if ($k['ueber'] !== '' && !isset($out[$k['ueber']])) throw new InvalidArgumentException("$was: die übergeordnete Stelle fehlt.");
        if ($k['ueber'] !== '' && $out[$k['ueber']]['art'] === 'stab') throw new InvalidArgumentException("$was: eine Stabsstelle hat keine untergeordneten Stellen.");
        if ($k['art'] === 'stab' && $k['ueber'] === '') throw new InvalidArgumentException("$was: eine Stabsstelle braucht eine übergeordnete Stelle.");
    }
    foreach ($out as $id => $k)
        for ($n = 0, $u = $k['ueber']; $u !== ''; $u = $out[$u]['ueber'])
            if ($u === $id || ++$n > count($out)) throw new InvalidArgumentException("Stelle „{$k['titel']}“: sie wäre sich selbst untergeordnet.");
    return ['knoten' => array_values($out)] + ($alt ?? []);
}

/* Aktion qs_organigramm_save: Struktur im offenen Entwurf speichern (Stand „rev“ des Dokuments wie bei qs_version_save) */
function qs_organigramm_speichern(): void
{
    $me = require_perm('qs.bearbeiten', true);
    $b = body();
    [$d, $was] = with_lock('qs-dokumente', function () use ($b, $me) {
        $doc = qs_doc('qs-dokumente');
        $i = qs_dokument_index($doc, $b['dokument'] ?? '');
        $d = $doc['liste'][$i];
        qs_rev_pruefen($b, $d, 'Das Dokument');
        if (!in_array($d['art'] ?? '', QS_GELENKT, true)) fail('Ordner und externe Dokumente haben keine Versionen.', 422);
        if (!empty($d['eingezogen'])) fail('Das Dokument ist eingezogen.', 409);
        $o = qs_ver_index($d, QS_VER_OFFEN);
        if ($o === null) fail('Das Organigramm lässt sich nur in einem Entwurf ändern – bitte zuerst „Überarbeitung beginnen“.', 409);
        $v = $d['versionen'][$o];
        if ($v['status'] !== 'entwurf') fail('Die Überarbeitung liegt zur Prüfung vor und kann nicht mehr geändert werden.', 409);
        $neu = qs_organigramm_pruefen($b['organigramm'] ?? null, $v['organigramm'] ?? null, qs_stamm());
        if (($v['organigramm'] ?? null) === $neu) return [$d, ''];
        $was = isset($v['organigramm']) ? 'geändert' : 'angelegt';
        $v['organigramm'] = $neu;
        if (!in_array((string)$me['id'], array_map('strval', (array)$v['bearbeiter']), true)) $v['bearbeiter'][] = (string)$me['id'];
        qs_verlauf($v, $me, "Organigramm $was (" . count($neu['knoten']) . ' Stellen)');
        $d['versionen'][$o] = $v;
        return [qs_dok_ablegen($doc, $i, $d, $me), $was];
    });
    if ($was !== '') audit('qs', 'QM-System: Organigramm in ' . qs_dok_name($d) . " $was");
    respond(['ok' => true, 'dokument' => qs_dok_antwort($d)]);
}

/* „Überarbeitung beginnen“: Struktur der gültigen Version in den neuen Entwurf – ohne Namens-Schnappschuss (im Entwurf gelten die heutigen Namen) */
function qs_organigramm_uebernehmen(?array $gueltig, array &$neu): void
{
    if (isset($gueltig['organigramm']['knoten'])) $neu['organigramm'] = array_diff_key($gueltig['organigramm'], ['namen' => true]);
}

/* Freigabe (nach Nummer, Datum und Freigabe-Vermerk): Namen festhalten und die PDF-Fassung als Datei der Version ablegen */
function qs_organigramm_freigeben(array $d, array &$v, array $stamm, array $me, array &$erzeugt): void
{
    if (!isset($v['organigramm']['knoten'])) return;
    $name = array_column($stamm['personen'], 'name', 'id');
    $namen = [];
    foreach ($v['organigramm']['knoten'] as $k) foreach ([...$k['personen'], $k['vertretung']] as $kz) if ($kz !== '') $namen[$kz] = (string)($name[$kz] ?? $kz);
    $v['organigramm']['namen'] = $namen;
    $abl = ablage_ablegen('qs', qs_organigramm_pdf($d, $v, $stamm));
    $erzeugt[] = $abl['id'];
    $v['dateien'][] = ['id' => $abl['id'], 'name' => ablage_dateiname("{$d['nr']} {$d['titel']} - Version {$v['nr']}.pdf"), 'art' => 'pdf', 'mime' => 'application/pdf',
                       'groesse' => $abl['groesse'], 'sha256' => $abl['sha256'], 'hochgeladen' => qs_wer($me), 'organigramm' => true];
    qs_verlauf($v, $me, 'PDF-Fassung des Organigramms abgelegt');
}

/* Lage aller Kästen und Linien (pt, Ursprung oben links) aus der Struktur und der Höhe je Kasten: untergeordnete Stellen
   nebeneinander unter ihrer Stelle, Stabsstellen paarweise links und rechts an der Linie darunter, oberste Stellen nebeneinander.
   Dieselbe Anordnung zeichnet die Oberfläche mit CSS (app/module/qs/organigramm.css).
   Rückgabe ['b' => Breite, 'h' => Höhe, 'kaesten' => [id => [x, y]], 'linien' => [[x1, y1, x2, y2], …]] */
function qs_organigramm_lage(array $knoten, array $hoehe): array
{
    $linie = ['' => []]; $stab = [];
    foreach ($knoten as $k) { $linie[$k['id']] = []; $stab[$k['id']] = []; }
    foreach ($knoten as $k) if ($k['art'] === 'stab') $stab[$k['ueber']][] = $k['id']; else $linie[$k['ueber']][] = $k['id'];
    $zeile = fn(array $s, int $i): float => max($hoehe[$s[$i]], $hoehe[$s[$i + 1] ?? $s[$i]]);
    $mass = [];
    $messen = function (string $id) use (&$messen, &$mass, $linie, $stab, $hoehe, $zeile): array {
        foreach ($linie[$id] as $c) $messen($c);
        $band = 0.0;
        for ($i = 0; $i < count($stab[$id]); $i += 2) $band += QS_OG_EBENE / 2 + $zeile($stab[$id], $i);
        $reihe = array_sum(array_map(fn($c) => $mass[$c][0], $linie[$id])) + QS_OG_SPALT * max(0, count($linie[$id]) - 1);
        $hKinder = $linie[$id] ? QS_OG_EBENE + max(array_map(fn($c) => $mass[$c][1], $linie[$id])) : 0;
        return $mass[$id] = [max(QS_OG_B, $stab[$id] ? 2 * QS_OG_B + QS_OG_STAB : 0, $reihe), $hoehe[$id] + $band + $hKinder, $reihe];
    };
    $kaesten = []; $linien = [];
    $setzen = function (string $id, float $x, float $y) use (&$setzen, &$kaesten, &$linien, &$mass, $linie, $stab, $hoehe, $zeile): void {
        [$b, , $reihe] = $mass[$id];
        $cx = $x + $b / 2;
        $kaesten[$id] = [$cx - QS_OG_B / 2, $y];
        $unten = $y + $hoehe[$id];
        $yy = $unten; $ende = $unten;
        for ($i = 0, $s = $stab[$id]; $i < count($s); $i += 2) {
            $yy += QS_OG_EBENE / 2;
            foreach ([[$s[$i], true], [$s[$i + 1] ?? null, false]] as [$c, $links]) {
                if ($c === null) continue;
                $kx = $links ? $cx - QS_OG_STAB / 2 - QS_OG_B : $cx + QS_OG_STAB / 2;
                $kaesten[$c] = [$kx, $yy];
                $ende = max($ende, $ym = $yy + $hoehe[$c] / 2);
                $linien[] = [$cx, $ym, $links ? $kx + QS_OG_B : $kx, $ym];
            }
            $yy += $zeile($s, $i);
        }
        if ($linie[$id]) {
            $ende = $yy + QS_OG_EBENE / 2;
            $cx0 = $cx - $reihe / 2; $mitten = [];
            foreach ($linie[$id] as $c) {
                $setzen($c, $cx0, $yy + QS_OG_EBENE);
                $mitten[] = $m = $cx0 + $mass[$c][0] / 2;
                $linien[] = [$m, $ende, $m, $yy + QS_OG_EBENE];
                $cx0 += $mass[$c][0] + QS_OG_SPALT;
            }
            if (count($mitten) > 1) $linien[] = [$mitten[0], $ende, end($mitten), $ende];
        }
        if ($ende > $unten) $linien[] = [$cx, $unten, $cx, $ende];
    };
    $x = 0.0; $h = 0.0;
    foreach ($linie[''] as $id) {
        [$b, $hh] = $messen($id);
        $setzen($id, $x, 0.0);
        $x += $b + 3 * QS_OG_SPALT; $h = max($h, $hh);
    }
    return ['b' => $x - 3 * QS_OG_SPALT, 'h' => $h, 'kaesten' => $kaesten, 'linien' => $linien];
}

/* Textzeilen eines Kastens [Text, Größe, fett, Farbe]: Stelle, Person(en) oder „unbesetzt“, Vertretung, Hinweis. Ein Wort, das
   nicht in eine Zeile passt (z. B. „Qualitätsmanagementbeauftragte“), verkleinert die Schrift statt getrennt zu werden. */
function qs_organigramm_zeilen(array $k, array $namen): array
{
    $w = QS_OG_B - 2 * QS_OG_RAND; $z = [];
    $dazu = function (string $t, float $g, bool $fett, string $farbe) use (&$z, $w): void {
        $breit = max(array_map(fn($x) => Pdf::width($x, $g, $fett), preg_split('/\s+/u', $t) ?: [$t]));
        if ($breit > $w) $g = max(5.0, $g * $w / $breit);
        foreach (Pdf::wrap($t, $g, $w, $fett) as $x) $z[] = [$x, $g, $fett, $farbe];
    };
    $dazu($k['titel'], 7.6, true, '#1b1a18');
    if (!$k['personen']) $dazu('unbesetzt', 7, false, '#8a857e');
    foreach ($k['personen'] as $p) $dazu($namen[$p] ?? $p, 7, false, '#1b1a18');
    if ($k['vertretung'] !== '') $dazu('Vertretung: ' . ($namen[$k['vertretung']] ?? $k['vertretung']), 6.3, false, '#5f5b55');
    if ($k['hinweis'] !== '') $dazu($k['hinweis'], 6.3, false, '#5f5b55');
    return $z;
}

/* PDF-Fassung einer freigegebenen Version: eine Seite A4 quer, Diagramm eingepasst; Kopf mit Logo, Titel und Firma, Fuß mit
   den Lenkungsangaben (Nr., Version, Datum, erstellt, geprüft, freigegeben – wie die Platzhalter in Word-/Excel-Dateien).
   shortcut: immer eine Seite – sehr große Organigramme werden klein; bei Bedarf auf mehrere Seiten verteilen. */
function qs_organigramm_pdf(array $d, array $v, array $stamm): string
{
    global $CFG;
    require_once __DIR__ . '/../../lib/pdf.php';
    $og = $v['organigramm']; $namen = (array)($og['namen'] ?? []);
    $zeilen = []; $hoehe = [];
    foreach ($og['knoten'] as $k) {
        $zeilen[$k['id']] = qs_organigramm_zeilen($k, $namen);
        $hoehe[$k['id']] = 2 * QS_OG_RAND + array_sum(array_map(fn($z) => $z[1] * 1.3, $zeilen[$k['id']]));
    }
    $lage = qs_organigramm_lage($og['knoten'], $hoehe);
    $pdf = new Pdf();
    $L = 28.0; $R = $pdf->w - 28.0; $oben = 86.0; $unten = 530.0;
    $s = min(1.0, ($R - $L) / $lage['b'], ($unten - $oben) / $lage['h']);
    $ox = $L + ($R - $L - $lage['b'] * $s) / 2;
    $lw = max(.35, .9 * $s);

    $pdf->jpeg(__DIR__ . '/../../lib/druck-logo.jpg', $L, 22, 110);
    $pdf->text($R, 40, (string)$d['titel'], 15, true, '#1b1a18', 'r');
    $pdf->text($R, 54, implode(' · ', array_filter([(string)$d['nr'], (string)($CFG['company'] ?? '')])), 8, false, '#5f5b55', 'r');
    $pdf->line($L, 70, $R, 70, .6, '#b9b4ac');

    foreach ($lage['linien'] as [$x1, $y1, $x2, $y2]) $pdf->line($ox + $x1 * $s, $oben + $y1 * $s, $ox + $x2 * $s, $oben + $y2 * $s, $lw, '#6f6a64');
    foreach ($og['knoten'] as $k) {
        [$x, $y] = $lage['kaesten'][$k['id']];
        $x = $ox + $x * $s; $y = $oben + $y * $s; $w = QS_OG_B * $s; $h = $hoehe[$k['id']] * $s;
        $stab = $k['art'] === 'stab';
        $pdf->rect($x, $y, $w, $h, $stab ? '#eef3f8' : '#ffffff');
        foreach ([[0, 0, 1, 0], [1, 0, 1, 1], [1, 1, 0, 1], [0, 1, 0, 0]] as [$a, $b, $c, $e]) $pdf->line($x + $a * $w, $y + $b * $h, $x + $c * $w, $y + $e * $h, $lw, $stab ? '#6d8fb5' : '#8a857e');
        $ty = $y + QS_OG_RAND * $s;
        foreach ($zeilen[$k['id']] as [$t, $g, $fett, $farbe]) { $ty += $g * 1.3 * $s; $pdf->text($x + QS_OG_RAND * $s, $ty - $g * .3 * $s, $t, $g * $s, $fett, $farbe); }
    }

    $l = qs_werte_lenkung($d, $v, $stamm);
    $pdf->line($L, 544, $R, 544, .6, '#b9b4ac');
    $x = $L;
    foreach (['Dokument-Nr.' => $l['nr'], 'Version' => $l['version'], 'Datum' => $l['datum'], 'Erstellt' => $l['erstellt'], 'Geprüft' => $l['geprueft'], 'Freigegeben' => $l['freigegeben']] as $was => $wert) {
        $pdf->text($x, 557, $was, 6.5, false, '#5f5b55');
        $pdf->text($x, 569, $wert, 8.5, true, '#1b1a18');
        $x += 108;
    }
    $pdf->text($R, 569, 'Seite 1 von 1', 7.5, false, '#5f5b55', 'r');
    return $pdf->output(trim($d['nr'] . ' ' . $d['titel']));
}
