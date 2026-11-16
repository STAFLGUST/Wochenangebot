<?php
declare(strict_types=1);
/* QM-System · Organigramm als gelenktes Dokument (Entscheidung des Inhabers 16.11.2026 „Im QM-System zeichnen“; nur bei
   Bedarf geladen von app/api/aktionen/qs.php). Die Struktur ist ein Feld an der Version statt eines eigenen Speicher-Dokuments,
   damit Lenkung, 4-Augen-Prinzip und Freigabe unverändert gelten. Datenform: docs/entwickler/05-daten.md.
   qs_organigramm_lage und app/module/qs/organigramm.css ordnen nach derselben Regel an – Änderungen immer an beiden. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const QS_OG_MAX_KNOTEN = 300;
const QS_OG_MAX_PERSONEN = 10;
const QS_OG_MAX_TITEL = 120;
const QS_OG_MAX_HINWEIS = 200;
const QS_OG_ARTEN = ['linie', 'stab'];
/* Maße der PDF-Fassung in pt, bevor das Diagramm auf die Seite eingepasst wird */
const QS_OG_KASTEN_BREITE = 88.0;
const QS_OG_INNENRAND = 4.0;
const QS_OG_ZEILENHOEHE = 1.3;   // je pt Schriftgröße
const QS_OG_NACHBAR_ABSTAND = 9.0;
const QS_OG_EBENEN_ABSTAND = 22.0;
const QS_OG_STAB_ABSTAND = 24.0;
const QS_OG_STAPEL_EINZUG = 18.0;
const QS_OG_STAPEL_ABSTAND = 6.0;
const QS_OG_WURZEL_ABSTAND = 30.0;
const QS_OG_MIN_SCHRIFT = 6.0;
const QS_OG_SCHRIFT_KLEIN = 7.0;   // Vertretung und Hinweis; bis hierhin wird ein zu langes Wort verkleinert, danach getrennt

/* Eingabe → gültige Struktur ohne Namens-Schnappschuss; null bei leerer Liste (Organigramm aus dem Entwurf nehmen).
   $alt = bisherige Struktur: Felder, die diese Fassung nicht kennt, bleiben an Knoten mit gleicher Kennung erhalten (GR-006). */
function qs_organigramm_pruefen($v, ?array $alt, array $stamm): ?array
{
    $liste = is_array($v) ? ($v['knoten'] ?? null) : null;
    if (!is_array($liste) || !array_is_list($liste)) throw new InvalidArgumentException('Organigramm: ungültige Angaben.');
    if (!$liste) return null;
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
        $k = ['id' => $id, 'titel' => qs_kuerzel($x['titel'] ?? '', $nr, QS_OG_MAX_TITEL)] + ($bisher[$id] ?? []);
        if ($k['titel'] === '') throw new InvalidArgumentException("$nr: bitte die Stelle bzw. Funktion benennen.");
        $was = "Stelle „{$k['titel']}“";
        $p = $x['personen'] ?? [];
        if (!is_array($p) || count($p) > QS_OG_MAX_PERSONEN) throw new InvalidArgumentException("$was: höchstens " . QS_OG_MAX_PERSONEN . ' Personen.');
        $k['personen'] = array_values(array_unique(array_filter(array_map(fn($y) => $person($y, "$was: Person"), $p), 'strlen')));
        $k['vertretung'] = $person($x['vertretung'] ?? '', "$was: Vertretung");
        $k['ueber'] = $x['ueber'] ?? '';
        if (!is_string($k['ueber'])) throw new InvalidArgumentException("$was: ungültige übergeordnete Stelle.");
        $k['art'] = qs_wahl($x['art'] ?? 'linie', QS_OG_ARTEN, "$was: Art");
        $k['hinweis'] = qs_kuerzel($x['hinweis'] ?? '', "$was: Hinweis", QS_OG_MAX_HINWEIS);
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

/* Aktion qs_organigramm_save: Struktur im offenen Entwurf speichern, mit leerer Liste entfernen (Stand „rev“ wie bei qs_version_save).
   Optional „version“ (Kennung des Entwurfs beim Öffnen): eine Zeichnung landet nie in einem später begonnenen Entwurf. */
function qs_organigramm_speichern(): never
{
    $me = require_perm('qs.bearbeiten', true);
    $b = body();
    [$d, $was] = with_lock('qs-dokumente', function () use ($b, $me) {
        $doc = qs_doc('qs-dokumente');
        $i = qs_dokument_index($doc, $b['dokument'] ?? '');
        $d = $doc['liste'][$i];
        $o = qs_ver_index($d, QS_VER_OFFEN);
        if (isset($b['version']) && ($o === null || ($d['versionen'][$o]['id'] ?? '') !== $b['version']))   // vor „rev“: sonst böte die Oberfläche „trotzdem speichern“ an
            fail('Der Entwurf, zu dem diese Zeichnung gehört, wurde inzwischen verworfen oder freigegeben – sie wird nicht gespeichert.', 409);
        qs_rev_pruefen($b, $d, 'Das Dokument');
        if (!in_array($d['art'] ?? '', QS_GELENKT, true)) fail('Ordner und externe Dokumente haben keine Versionen.', 422);
        if (!empty($d['eingezogen'])) fail('Das Dokument ist eingezogen.', 409);
        if ($o === null) fail('Das Organigramm lässt sich nur in einem Entwurf ändern – bitte zuerst „Überarbeitung beginnen“.', 409);
        $v = $d['versionen'][$o];
        if ($v['status'] !== 'entwurf') fail('Die Überarbeitung liegt zur Prüfung vor und kann nicht mehr geändert werden.', 409);
        $neu = qs_organigramm_pruefen($b['organigramm'] ?? null, $v['organigramm'] ?? null, qs_stamm());
        if (($v['organigramm'] ?? null) === $neu) return [$d, ''];
        $was = $neu === null ? 'entfernt' : (isset($v['organigramm']) ? 'geändert' : 'angelegt');
        if ($neu === null) unset($v['organigramm']); else $v['organigramm'] = $neu;
        if (!in_array((string)$me['id'], array_map('strval', (array)$v['bearbeiter']), true)) $v['bearbeiter'][] = (string)$me['id'];
        qs_verlauf($v, $me, "Organigramm $was" . ($neu === null ? '' : ' (' . count($neu['knoten']) . ' Stellen)'));
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

/* Nach jedem Schritt in qs_version_schritt: ab dem Einreichen hält die Version die Namen fest – der Prüfer prüft genau diese,
   die Freigabe übernimmt sie unverändert (GR-106, 4-Augen-Prinzip); zurück im Entwurf gelten wieder die heutigen Namen. */
function qs_organigramm_schritt(array $d, array &$v, array $me, array &$erzeugt): void
{
    if (!isset($v['organigramm']['knoten'])) return;
    if ($v['status'] === 'entwurf') { unset($v['organigramm']['namen']); return; }
    if (!in_array($v['status'], ['pruefung', 'geprueft', 'freigegeben'], true)) return;   // jeder Stand nach dem Entwurf außer „verworfen“
    $stamm = qs_stamm();
    $v['organigramm']['namen'] ??= qs_organigramm_namen($v['organigramm'], $stamm);   // fehlt nur, wenn eine Vorversion der Anwendung eingereicht hat
    if ($v['status'] !== 'freigegeben') return;
    $abl = ablage_ablegen('qs', qs_organigramm_pdf($d, $v, $stamm));
    $erzeugt[] = $abl['id'];
    $v['dateien'][] = ['id' => $abl['id'], 'name' => ablage_dateiname("{$d['nr']} {$d['titel']} - Version {$v['nr']}.pdf"), 'art' => 'pdf', 'mime' => 'application/pdf',
                       'groesse' => $abl['groesse'], 'sha256' => $abl['sha256'], 'hochgeladen' => qs_wer($me), 'organigramm' => true];
    qs_verlauf($v, $me, 'PDF-Fassung des Organigramms abgelegt');
}

function qs_organigramm_namen(array $og, array $stamm): array
{
    $name = array_column($stamm['personen'], 'name', 'id');
    $namen = [];
    foreach ($og['knoten'] as $k) foreach ([...$k['personen'], $k['vertretung']] as $kz) if ($kz !== '') $namen[$kz] = (string)($name[$kz] ?? $kz);
    return $namen;
}

/* Aktion qs_organigramm_vorschau (GET): dieselbe PDF wie bei der Freigabe für die offene Version, als ENTWURF gekennzeichnet –
   der Prüfer sieht vorher, was festgeschrieben wird */
function qs_organigramm_vorschau(): never
{
    require_perm('qs.sehen');
    $doc = qs_doc('qs-dokumente');
    $d = $doc['liste'][qs_dokument_index($doc, $_GET['dokument'] ?? '')];
    $o = qs_ver_index($d, QS_VER_OFFEN);
    if ($o === null || !isset($d['versionen'][$o]['organigramm']['knoten'])) fail('Zu diesem Dokument gibt es keinen Entwurf mit Organigramm.', 404);
    $v = $d['versionen'][$o];
    $v['nr'] = qs_naechste_nr($d);
    $pdf = qs_organigramm_pdf($d, $v, qs_stamm(), 'ENTWURF – nicht freigegeben');
    header('Content-Type: application/pdf');
    header('Content-Disposition: ' . ablage_disposition(ablage_dateiname("{$d['nr']} {$d['titel']} - Entwurf Version {$v['nr']}.pdf")));
    header('Cache-Control: private, no-store');
    header('X-Content-Type-Options: nosniff');
    header('Content-Length: ' . strlen($pdf));
    echo $pdf;
    exit;
}

/* Lage aller Kästen und Linien in pt, Ursprung oben links: ['b', 'h', 'kaesten' => [id => ['x', 'y']], 'linien' => [[x1, y1, x2, y2]]].
   Oberste Stellen stehen nebeneinander; die Regel darunter steht bei qs_og_teilbaum. */
function qs_organigramm_lage(array $knoten, array $hoehe): array
{
    $unter = ['' => ['linie' => [], 'stab' => []]];
    foreach ($knoten as $k) $unter[$k['id']] = ['linie' => [], 'stab' => []];
    foreach ($knoten as $k) $unter[$k['ueber']][$k['art']][] = $k['id'];
    $lage = ['kaesten' => [], 'linien' => []];
    $x = 0.0; $h = 0.0;
    foreach ($unter['']['linie'] as $id) {
        $t = qs_og_teilbaum($id, $unter, $hoehe);
        qs_og_verschieben($lage, $t, $x, 0.0);
        $x += $t['b'] + QS_OG_WURZEL_ABSTAND; $h = max($h, $t['h']);
    }
    return ['b' => $x - QS_OG_WURZEL_ABSTAND, 'h' => $h] + $lage;
}

/* Teilbaum ab $id mit Ursprung oben links: Stabsstellen paarweise links und rechts der Linie unter der Stelle; Unterstellen
   nebeneinander – oder senkrecht gestapelt, wenn die Stelle keine Stabsstellen hat und keine Unterstelle eigene Unterstellen.
   Jeder Teil steht mittig unter der Stelle, die Stelle also mittig im Teilbaum. */
function qs_og_teilbaum(string $id, array $unter, array $hoehe): array
{
    $B = QS_OG_KASTEN_BREITE;
    $t = ['kaesten' => [$id => ['x' => -$B / 2, 'y' => 0.0]], 'linien' => []];   // x zunächst ab der Mitte der Stelle
    $halb = $B / 2;
    $y = $stamm = $hoehe[$id];
    foreach (array_chunk($unter[$id]['stab'], 2) as $paar) {
        $halb = $B + QS_OG_STAB_ABSTAND / 2;
        $y += QS_OG_EBENEN_ABSTAND / 2;
        foreach ($paar as $i => $c) {
            $x = $i === 0 ? -$halb : QS_OG_STAB_ABSTAND / 2;
            $t['kaesten'][$c] = ['x' => $x, 'y' => $y];
            $ym = $y + $hoehe[$c] / 2;
            $t['linien'][] = [0.0, $ym, $i === 0 ? $x + $B : $x, $ym];
            $stamm = max($stamm, $ym);
        }
        $y += max(array_map(fn($c) => $hoehe[$c], $paar));
    }
    $linie = $unter[$id]['linie'];
    $blatt = fn($c) => !$unter[$c]['linie'] && !$unter[$c]['stab'];
    if ($linie && !$unter[$id]['stab'] && count(array_filter($linie, $blatt)) === count($linie)) {
        $halb = ($B + QS_OG_STAPEL_EINZUG) / 2;
        $x = -$B / 2 + QS_OG_STAPEL_EINZUG / 2;
        $schiene = -$B / 2 + QS_OG_STAPEL_EINZUG / 4;
        foreach ($linie as $c) {
            $y += QS_OG_STAPEL_ABSTAND;
            $t['kaesten'][$c] = ['x' => $x, 'y' => $y];
            $ym = $y + $hoehe[$c] / 2;
            $t['linien'][] = [$schiene, $ym, $x, $ym];
            $y += $hoehe[$c];
        }
        $t['linien'][] = [$schiene, $hoehe[$id], $schiene, $ym];
    } elseif ($linie) {
        $kinder = array_map(fn($c) => qs_og_teilbaum($c, $unter, $hoehe), $linie);
        $reihe = array_sum(array_column($kinder, 'b')) + QS_OG_NACHBAR_ABSTAND * (count($kinder) - 1);
        $halb = max($halb, $reihe / 2);
        $stamm = $y + QS_OG_EBENEN_ABSTAND / 2;
        $y += QS_OG_EBENEN_ABSTAND;
        $x = -$reihe / 2; $mitten = [];
        foreach ($kinder as $k) {
            qs_og_verschieben($t, $k, $x, $y);
            $mitten[] = $m = $x + $k['b'] / 2;
            $t['linien'][] = [$m, $stamm, $m, $y];
            $x += $k['b'] + QS_OG_NACHBAR_ABSTAND;
        }
        if (count($mitten) > 1) $t['linien'][] = [$mitten[0], $stamm, end($mitten), $stamm];
        $y += max(array_column($kinder, 'h'));
    }
    if ($stamm > $hoehe[$id]) $t['linien'][] = [0.0, $hoehe[$id], 0.0, $stamm];
    $aus = ['b' => 2 * $halb, 'h' => $y, 'kaesten' => [], 'linien' => []];
    qs_og_verschieben($aus, $t, $halb, 0.0);
    return $aus;
}

function qs_og_verschieben(array &$ziel, array $teil, float $dx, float $dy): void
{
    foreach ($teil['kaesten'] as $id => $p) $ziel['kaesten'][$id] = ['x' => $p['x'] + $dx, 'y' => $p['y'] + $dy];
    foreach ($teil['linien'] as [$x1, $y1, $x2, $y2]) $ziel['linien'][] = [$x1 + $dx, $y1 + $dy, $x2 + $dx, $y2 + $dy];
}

/* Kasten einer Stelle: Textzeilen mit Grundlinie y (pt ab Oberkante) und Höhe h – Stelle, Person(en) oder „unbesetzt“, Vertretung, Hinweis */
function qs_organigramm_kasten(array $k, array $namen): array
{
    $innen = QS_OG_KASTEN_BREITE - 2 * QS_OG_INNENRAND;
    $zeilen = []; $y = QS_OG_INNENRAND;
    $dazu = function (string $text, float $g, bool $fett, string $farbe) use (&$zeilen, &$y, $innen): void {
        $woerter = preg_split('/\s+/u', trim($text)) ?: [$text];
        $breit = max(array_map(fn($w) => Pdf::width($w, $g, $fett), $woerter));
        if ($breit > $innen) $g = max(min($g, QS_OG_SCHRIFT_KLEIN), $g * $innen / $breit);
        foreach (Pdf::wrap(implode(' ', array_map(fn($w) => qs_og_trennen($w, $g, $innen, $fett), $woerter)), $g, $innen, $fett) as $z) {
            $y += $g * QS_OG_ZEILENHOEHE;
            $zeilen[] = ['text' => $z, 'g' => $g, 'fett' => $fett, 'farbe' => $farbe, 'y' => $y - $g * .3];
        }
    };
    $dazu($k['titel'], 8.0, true, '#1b1a18');
    if (!$k['personen']) $dazu('unbesetzt', 7.4, false, '#8a857e');
    foreach ($k['personen'] as $p) $dazu($namen[$p] ?? $p, 7.4, false, '#1b1a18');
    if ($k['vertretung'] !== '') $dazu('Vertretung: ' . ($namen[$k['vertretung']] ?? $k['vertretung']), QS_OG_SCHRIFT_KLEIN, false, '#5f5b55');
    if ($k['hinweis'] !== '') $dazu($k['hinweis'], QS_OG_SCHRIFT_KLEIN, false, '#5f5b55');
    return ['zeilen' => $zeilen, 'h' => $y + QS_OG_INNENRAND];
}

/* Wort, das auch verkleinert nicht in die Zeile passt, mit Trennstrich zerlegen (Teile mit Leerzeichen für Pdf::wrap) */
function qs_og_trennen(string $wort, float $g, float $innen, bool $fett): string
{
    $teile = [];
    while (Pdf::width($wort, $g, $fett) > $innen && mb_strlen($wort) > 2) {
        $n = mb_strlen($wort) - 1;
        while ($n > 1 && Pdf::width(mb_substr($wort, 0, $n) . '-', $g, $fett) > $innen) $n--;
        for ($m = $n; $m > $n / 2; $m--) if (preg_match('/^[^aeiouäöüy-][aeiouäöüy]/iu', mb_substr($wort, $m))) { $n = $m; break; }   // vor Konsonant + Vokal: „management-beauftragte“
        $teile[] = mb_substr($wort, 0, $n) . '-';
        $wort = mb_substr($wort, $n);
    }
    return implode(' ', [...$teile, $wort]);
}

/* Text auf $max pt Breite: erst verkleinern (bis QS_OG_MIN_SCHRIFT), dann mit „…“ kürzen → [Text, Größe] */
function qs_og_einpassen(string $t, float $g, float $max, bool $fett): array
{
    $breit = Pdf::width($t, $g, $fett);
    if ($breit > $max) $g = max(QS_OG_MIN_SCHRIFT, $g * $max / $breit);
    while (Pdf::width($t, $g, $fett) > $max && mb_strlen($t) > 1) $t = mb_substr($t, 0, -2) . '…';
    return [$t, $g];
}

/* Eine Seite A4 quer: Logo, Titel und Firma im Kopf, Lenkungsangaben im Fuß (wie die Platzhalter in Word-/Excel-Dateien).
   Namen aus dem Schnappschuss der Version, im Entwurf die heutigen; $marke kennzeichnet die Vorschau.
   shortcut: immer eine Seite – ab etwa 9 Stellen mit eigenen Unterstellen in einer Reihe fällt die Schrift unter 6 pt und die PDF
   sagt das; kommt das bei echten Organigrammen vor, auf mehrere Seiten verteilen. */
function qs_organigramm_pdf(array $d, array $v, array $stamm, string $marke = ''): string
{
    global $CFG;
    require_once __DIR__ . '/../../lib/pdf.php';
    require_once __DIR__ . '/vorlagen.php';
    $og = $v['organigramm'];
    $namen = $og['namen'] ?? qs_organigramm_namen($og, $stamm);
    $kaesten = [];
    foreach ($og['knoten'] as $k) $kaesten[$k['id']] = qs_organigramm_kasten($k, $namen);
    $lage = qs_organigramm_lage($og['knoten'], array_map(fn($x) => $x['h'], $kaesten));
    $pdf = new Pdf();
    $L = 28.0; $R = $pdf->w - 28.0; $oben = 86.0; $unten = 530.0; $logo = 110.0;
    $s = min(1.0, ($R - $L) / $lage['b'], ($unten - $oben) / $lage['h']);
    $ox = $L + ($R - $L - $lage['b'] * $s) / 2;
    $lw = max(.35, .9 * $s);

    $pdf->jpeg(__DIR__ . '/../../lib/druck-logo.jpg', $L, 22, $logo);
    if ($marke !== '') $pdf->text($R, 18, $marke, 9, true, '#b3261e', 'r');
    [$t, $g] = qs_og_einpassen((string)$d['titel'], 15, $R - $L - $logo - 20, true);
    $pdf->text($R, 40, $t, $g, true, '#1b1a18', 'r');
    [$t, $g] = qs_og_einpassen(implode(' · ', array_filter([(string)$d['nr'], (string)($CFG['company'] ?? '')])), 8, $R - $L - $logo - 20, false);
    $pdf->text($R, 54, $t, $g, false, '#5f5b55', 'r');
    $pdf->line($L, 70, $R, 70, .6, '#b9b4ac');
    $klein = $s * min(array_column(array_merge(...array_column($kaesten, 'zeilen')), 'g'));
    if ($klein < QS_OG_MIN_SCHRIFT)
        $pdf->text($L, 81, 'Hinweis: Für eine Seite zu groß – verkleinert auf ' . number_format($klein, 1, ',', '') . ' pt Schrift. Große Bereiche besser als eigene Organigramme führen.', 7.5, false, '#b3261e');

    foreach ($lage['linien'] as [$x1, $y1, $x2, $y2]) $pdf->line($ox + $x1 * $s, $oben + $y1 * $s, $ox + $x2 * $s, $oben + $y2 * $s, $lw, '#6f6a64');
    foreach ($og['knoten'] as $k) {
        $p = $lage['kaesten'][$k['id']];
        $x = $ox + $p['x'] * $s; $y = $oben + $p['y'] * $s; $w = QS_OG_KASTEN_BREITE * $s; $h = $kaesten[$k['id']]['h'] * $s;
        $stab = $k['art'] === 'stab';
        $pdf->rect($x, $y, $w, $h, $stab ? '#eef3f8' : '#ffffff');
        foreach ([[0, 0, 1, 0], [1, 0, 1, 1], [1, 1, 0, 1], [0, 1, 0, 0]] as [$a, $b, $c, $e]) $pdf->line($x + $a * $w, $y + $b * $h, $x + $c * $w, $y + $e * $h, $lw, $stab ? '#6d8fb5' : '#8a857e');
        foreach ($kaesten[$k['id']]['zeilen'] as $z) $pdf->text($x + QS_OG_INNENRAND * $s, $y + $z['y'] * $s, $z['text'], $z['g'] * $s, $z['fett'], $z['farbe']);
    }

    $l = qs_werte_lenkung($d, $v, $stamm);
    $pdf->line($L, 544, $R, 544, .6, '#b9b4ac');
    $spalte = 108.0; $x = $L;
    foreach (['Dokument-Nr.' => $l['nr'], 'Version' => $l['version'], 'Datum' => $l['datum'], 'Erstellt' => $l['erstellt'], 'Geprüft' => $l['geprueft'], 'Freigegeben' => $l['freigegeben']] as $was => $wert) {
        $pdf->text($x, 557, $was, 6.5, false, '#5f5b55');
        [$t, $g] = qs_og_einpassen($wert !== '' ? $wert : '—', 8.5, $spalte - 8, true);
        $pdf->text($x, 569, $t, $g, true, '#1b1a18');
        $x += $spalte;
    }
    $pdf->text($R, 569, 'Seite 1 von 1', 7.5, false, '#5f5b55', 'r');
    return $pdf->output(trim($d['nr'] . ' ' . $d['titel']));
}
