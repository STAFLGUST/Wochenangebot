<?php
declare(strict_types=1);
/* QM-System · Audit-Bericht (Aktionen qs_bericht, qs_bericht_excel): Auswertung eines Zeitraums (höchstens zwei Jahre, endet
   spätestens heute) für das IFS-Audit – nur lesen, nichts wird gespeichert. Nur bei Bedarf geladen (aktionen/qs.php).
   Inhalt:
     Prüfplan   Kalender-Intervalle (täglich, wöchentlich, monatlich): je Periode erfüllt oder versäumt wie in der Fälligkeit
                (qs_faelligkeit_kern), gezählt im Monat ihres Endes; eine Periode zählt, wenn sie zum Stichtag (= Bis) vorbei
                ist oder schon einen Nachweis hat; Nachweise nach dem Stichtag zählen nicht. Versäumte Perioden als
                zusammenhängende Bereiche. Längere Intervalle: Fristenkette (erste Fälligkeit bzw. letzter Nachweis +
                Intervall) mit eingehalten, verspätet (Tage), überfällig zum Stichtag, noch nie geprüft – im Zeitraum
                fällig oder in ihn hinein überfällig. „Bei Bedarf“ und inaktive Prüfungen: nur Nachweise.
     Abweichungen  Nachweise mit Ergebnis „Abweichung“ im Zeitraum mit der zugehörigen Maßnahme; stornierte Nachweise zählen nie
                (nur ihre Anzahl wird genannt).
     Maßnahmen  erfasst bis zum Stichtag und im Zeitraum noch offen oder abgeschlossen (Status: Stand heute).
     Dokumente  Freigaben, Überprüfungen ohne Änderung und Einziehungen im Zeitraum; Bestand und „Überprüfung fällig“ Stand heute.
     Handbuch   Änderungen der Abschnitte im Zeitraum.
   qs_bericht_daten() rechnet nur mit übergebenen Daten (prüfbar ohne Speicher); qs_bericht_xlsx() schreibt die Arbeitsmappe
   (Office Open XML ohne PHP-Erweiterung „zip“, ZIP aus qs_zip_bauen in vorlagen.php; Texte als Text, nie als Formel). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar
require_once __DIR__ . '/vorlagen.php';

const QS_BERICHT_MAX_TAGE = 730;   // Bis − Von höchstens 730 Tage (zwei Jahre; tägliche Perioden bleiben unter der Grenze von qs_perioden)
const QS_BERICHT_ART = ['tag' => 'Tag', 'woche' => 'Woche', 'monat' => 'Monat'];

/* Zeitraum prüfen: [von, bis] */
function qs_bericht_zeitraum($von, $bis, string $heute): array
{
    $von = qs_datum($von, 'Von'); $bis = qs_datum($bis, 'Bis');
    if ($bis > $heute) throw new InvalidArgumentException('Bis: der Zeitraum kann nicht in der Zukunft enden.');
    if ($von > $bis) throw new InvalidArgumentException('Von muss vor Bis liegen.');
    if (qs_tage_bis($von, $bis) > QS_BERICHT_MAX_TAGE) throw new InvalidArgumentException('Der Zeitraum darf höchstens zwei Jahre umfassen.');
    return [$von, $bis];
}
function qs_bericht_monate(string $von, string $bis): array
{
    $out = [];
    for ($m = substr($von, 0, 7) . '-01'; substr($m, 0, 7) <= substr($bis, 0, 7); $m = qs_plus_monate($m, 1)) $out[] = substr($m, 0, 7);
    return $out;
}

/* Kalender-Intervall: Perioden im Zeitraum, erfüllt/versäumt je Monat, versäumte Bereiche [erste, letzte, Anzahl] */
function qs_bericht_kalender(array $p, array $eigene, string $von, string $bis, string $heute): array
{
    $iv = (string)$p['intervall']; $art = QS_KALENDER[$iv];
    $out = ['faellig' => 0, 'erfuellt' => 0, 'versaeumt' => 0, 'bereiche' => [], 'monate' => []];
    $erledigt = [];
    foreach ($eigene as $n) if ($n['datum'] <= $bis) $erledigt[qs_periode($art, $n['datum'])] = true;
    $ab = (string)($p['start'] ?? '') ?: substr((string)($p['erstellt']['t'] ?? $heute), 0, 10);
    $vonAb = max($von, $ab);
    if ($vonAb > $bis) return $out;
    $lauf = null;
    foreach (qs_perioden($iv, $vonAb, $bis) as [$per, $ende]) {
        $ok = isset($erledigt[$per]);
        if (!$ok && !($ende <= $bis && $ende < $heute)) continue;   // laufende Periode ohne Nachweis zählt (noch) nicht
        $m = substr(min($ende, $bis), 0, 7);
        $out['monate'][$m] = ['f' => ($out['monate'][$m]['f'] ?? 0) + 1, 'e' => ($out['monate'][$m]['e'] ?? 0) + ($ok ? 1 : 0)];
        $out['faellig']++;
        if ($ok) { $out['erfuellt']++; $lauf = null; continue; }
        $out['versaeumt']++;
        if ($lauf === null) { $out['bereiche'][] = [$per, $per, 1]; $lauf = count($out['bereiche']) - 1; }
        else { $out['bereiche'][$lauf][1] = $per; $out['bereiche'][$lauf][2]++; }
    }
    return $out;
}

/* Längere Intervalle: Fristenkette; Ereignis [faellig, erledigt, status, tage] */
function qs_bericht_fristen(array $p, array $eigene, string $von, string $bis): array
{
    $monate = QS_ROLLEND[(string)$p['intervall']];
    $auf = array_reverse(array_values(array_filter($eigene, function ($n) use ($bis) { return $n['datum'] <= $bis; })));   // älteste zuerst
    $ketten = [];
    $faellig = (string)($p['start'] ?? '');
    foreach ($auf as $n) {
        if ($faellig !== '') $ketten[] = [$faellig, (string)$n['datum']];
        $faellig = qs_plus_monate((string)$n['datum'], $monate);
    }
    if ($faellig !== '' && $faellig <= $bis) $ketten[] = [$faellig, ''];
    $out = [];
    if (!$auf && (string)($p['start'] ?? '') === '') $out[] = ['faellig' => '', 'erledigt' => '', 'status' => 'nie', 'tage' => null];
    foreach ($ketten as [$f, $e]) {
        if ($f > $bis || ($f < $von && $e !== '' && $e < $von)) continue;   // nach dem Stichtag fällig bzw. vor dem Zeitraum erledigt
        if ($e !== '') $out[] = $e <= $f ? ['faellig' => $f, 'erledigt' => $e, 'status' => 'eingehalten', 'tage' => null]
                                         : ['faellig' => $f, 'erledigt' => $e, 'status' => 'verspaetet', 'tage' => qs_tage_bis($f, $e)];
        else $out[] = $f < $bis ? ['faellig' => $f, 'erledigt' => '', 'status' => 'ueberfaellig', 'tage' => qs_tage_bis($f, $bis)]
                                : ['faellig' => $f, 'erledigt' => '', 'status' => 'offen', 'tage' => null];
    }
    return $out;
}

/* Abschluss einer Maßnahme (Datum) – wirksam: Wirksamkeitsprüfung, verworfen: letzte Änderung */
function qs_bericht_abschluss(array $m): string
{
    if (($m['status'] ?? '') === 'wirksam') return substr((string)($m['wirksamkeit']['t'] ?? ''), 0, 10);
    if (($m['status'] ?? '') === 'verworfen') return substr((string)($m['geaendert']['t'] ?? ''), 0, 10);
    return '';
}

/* Der Bericht. $namen = Mitarbeiter-Kennung → Name (ausführende). Alle Daten werden nur gelesen. */
function qs_bericht_daten(array $stamm, array $dokumente, array $handbuch, array $plan, array $nachweise, array $massnahmen, array $namen,
                          string $von, string $bis, string $heute): array
{
    $imZeitraum = function (string $d) use ($von, $bis) { return $d !== '' && $d >= $von && $d <= $bis; };
    $monate = qs_bericht_monate($von, $bis);
    $np = qs_nachweise_nach_pruefung($nachweise);
    $kz = ['faellig' => 0, 'erfuellt' => 0, 'versaeumt' => 0, 'fristen' => 0, 'eingehalten' => 0, 'verspaetet' => 0, 'ueberfaellig' => 0, 'offen' => 0, 'nie' => 0,
           'nachweise' => 0, 'abweichungen' => 0, 'storniert' => 0, 'pruefungen' => 0];
    foreach ($nachweise as $n) if (!empty($n['storno']) && $imZeitraum((string)$n['datum'])) $kz['storniert']++;

    /* Prüfplan */
    usort($plan, function ($a, $b) { return qs_nat_cmp((string)$a['kapitel'], (string)$b['kapitel']) ?: strnatcasecmp((string)$a['titel'], (string)$b['titel']); });
    $pruefungen = [];
    foreach ($plan as $p) {
        $eigene = $np[$p['id']] ?? [];
        $imZ = array_values(array_filter($eigene, function ($n) use ($imZeitraum) { return $imZeitraum((string)$n['datum']); }));
        $iv = (string)($p['intervall'] ?? '');
        $art = empty($p['aktiv']) ? 'inaktiv' : (isset(QS_KALENDER[$iv]) ? 'kalender' : (isset(QS_ROLLEND[$iv]) ? 'rollend' : 'anlass'));
        if ($art === 'inaktiv' && !$imZ) continue;
        $row = ['id' => $p['id'], 'kapitel' => (string)$p['kapitel'], 'titel' => (string)$p['titel'], 'intervall' => $iv, 'intervallText' => QS_INTERVALLE[$iv] ?? $iv,
                'art' => $art, 'zustaendig' => (string)($p['zustaendig'] ?? ''),
                'ausfuehrende' => array_values(array_filter(array_map(function ($i) use ($namen) { return $namen[$i] ?? ''; }, (array)($p['ausfuehrende'] ?? [])))),
                'nachweise' => count($imZ), 'abweichungen' => count(array_filter($imZ, function ($n) { return $n['ergebnis'] === 'abweichung'; })),
                'monate' => [], 'faellig' => null, 'erfuellt' => null, 'versaeumt' => null, 'bereiche' => [], 'fristen' => []];
        foreach ($imZ as $n) { $m = substr((string)$n['datum'], 0, 7); $row['monate'][$m]['n'] = ($row['monate'][$m]['n'] ?? 0) + 1; }
        if ($art === 'kalender') {
            $k = qs_bericht_kalender($p, $eigene, $von, $bis, $heute);
            foreach ($k['monate'] as $m => $x) $row['monate'][$m] = ($row['monate'][$m] ?? []) + $x;
            $row['faellig'] = $k['faellig']; $row['erfuellt'] = $k['erfuellt']; $row['versaeumt'] = $k['versaeumt']; $row['bereiche'] = $k['bereiche'];
            $kz['faellig'] += $k['faellig']; $kz['erfuellt'] += $k['erfuellt']; $kz['versaeumt'] += $k['versaeumt'];
        } elseif ($art === 'rollend') {
            $row['fristen'] = qs_bericht_fristen($p, $eigene, $von, $bis);
            foreach ($row['fristen'] as $f) { $kz['fristen']++; $kz[$f['status']]++; }
        }
        if ($art !== 'inaktiv') $kz['pruefungen']++;
        $kz['nachweise'] += $row['nachweise']; $kz['abweichungen'] += $row['abweichungen'];
        $pruefungen[] = $row;
    }
    $kz['quote'] = $kz['faellig'] ? round($kz['erfuellt'] / $kz['faellig'], 4) : null;

    /* Abweichungen mit Maßnahme */
    $mIndex = []; foreach ($massnahmen as $m) $mIndex[(string)$m['id']] = $m;
    $pIndex = []; foreach ($plan as $p) $pIndex[(string)$p['id']] = $p;
    $abweichungen = [];
    foreach ($nachweise as $n) {
        if (!empty($n['storno']) || $n['ergebnis'] !== 'abweichung' || !$imZeitraum((string)$n['datum'])) continue;
        $p = $pIndex[(string)$n['pruefung']] ?? ['kapitel' => '', 'titel' => '(Prüfung entfernt)'];
        $m = $mIndex[(string)($n['massnahme'] ?? '')] ?? null;
        $abweichungen[] = ['datum' => (string)$n['datum'], 'kapitel' => (string)$p['kapitel'], 'pruefung' => (string)$p['titel'], 'bemerkung' => (string)$n['bemerkung'],
                           'durch' => (string)($n['durch'] ?? ''), 'massnahme' => $m ? ['nr' => (string)$m['nr'], 'status' => (string)$m['status']] : null];
    }
    usort($abweichungen, function ($a, $b) { return [$a['datum'], $a['kapitel'], $a['pruefung']] <=> [$b['datum'], $b['kapitel'], $b['pruefung']]; });

    /* Maßnahmen */
    $mz = ['erfasst' => 0, 'abgeschlossen' => 0, 'offen' => 0, 'ueberfaellig' => 0];
    $mListe = [];
    foreach ($massnahmen as $m) {
        $erf = substr((string)($m['erfasst']['t'] ?? ''), 0, 10);
        $abg = qs_bericht_abschluss($m);
        $offen = !in_array($m['status'] ?? 'offen', QS_MASSN_ABGESCHLOSSEN, true);
        if ($erf > $bis || (!$offen && $abg !== '' && $abg < $von)) continue;
        $x = qs_massnahme_aus($m, $heute);
        if ($imZeitraum($erf)) $mz['erfasst']++;
        if (!$offen && $imZeitraum($abg) && $m['status'] === 'wirksam') $mz['abgeschlossen']++;
        if ($offen) $mz['offen']++;
        if (!empty($x['ueberfaellig'])) $mz['ueberfaellig']++;
        $mListe[] = ['nr' => (string)$m['nr'], 'quelle' => (string)$m['quelle'], 'kapitel' => (string)$m['kapitel'], 'bewertung' => (string)($m['bewertung'] ?? ''),
                     'feststellung' => (string)$m['feststellung'], 'massnahme' => (string)$m['massnahme'], 'zustaendig' => (string)$m['zustaendig'],
                     'frist' => (string)$m['frist'], 'status' => (string)$m['status'], 'ueberfaellig' => !empty($x['ueberfaellig']), 'erfasst' => $erf, 'abgeschlossen' => $abg,
                     'wirksamkeit' => (string)($m['wirksamkeit']['notiz'] ?? '')];
    }
    usort($mListe, function ($a, $b) { return strnatcasecmp($a['nr'], $b['nr']); });

    /* Dokumentenlenkung */
    $monateU = (int)$stamm['einstellungen']['ueberpruefungMonate'];
    $dz = ['gueltig' => 0, 'inArbeit' => 0, 'ohneFreigabe' => 0, 'faellig' => 0, 'freigaben' => 0, 'ueberprueft' => 0, 'eingezogen' => 0];
    $vorgaenge = []; $faellig = [];
    foreach ($dokumente as $d) {
        $z = qs_dok_status($d);
        if ($z === 'gueltig') $dz['gueltig']++;
        elseif ($z === 'entwurf' || $z === 'pruefung') { $dz['inArbeit']++; if (qs_ver_index($d, ['freigegeben']) !== null) $dz['gueltig']++; }
        elseif ($z === 'ohne') $dz['ohneFreigabe']++;
        $basis = ['kapitel' => (string)$d['kapitel'], 'nr' => (string)$d['nr'], 'titel' => (string)$d['titel'], 'art' => (string)$d['art']];
        foreach ((array)($d['versionen'] ?? []) as $v) {
            if (!in_array($v['status'] ?? '', ['freigegeben', 'ersetzt'], true) || !$imZeitraum((string)($v['datum'] ?? ''))) continue;
            $k = is_array($v['kuerzel'] ?? null) ? $v['kuerzel'] : [];
            $vorgaenge[] = $basis + ['vorgang' => 'freigabe', 'datum' => (string)$v['datum'], 'version' => (string)$v['nr'], 'aenderungen' => (string)($v['aenderungen'] ?? ''),
                                     'grund' => (string)($v['grund'] ?? ''), 'erstellt' => (string)($k['erstellt'] ?? ($v['erstellt']['von'] ?? '')),
                                     'geprueft' => (string)($k['geprueft'] ?? ($v['geprueft']['von'] ?? '')), 'freigegeben' => (string)($k['freigegeben'] ?? ($v['freigegeben']['von'] ?? ''))];
            $dz['freigaben']++;
        }
        $u = substr((string)($d['ueberprueft']['t'] ?? ''), 0, 10);
        if ($imZeitraum($u)) { $vorgaenge[] = $basis + ['vorgang' => 'ueberprueft', 'datum' => $u, 'von' => (string)($d['ueberprueft']['von'] ?? ''), 'notiz' => (string)($d['ueberprueft']['notiz'] ?? '')]; $dz['ueberprueft']++; }
        $e = substr((string)($d['eingezogen']['t'] ?? ''), 0, 10);
        if ($imZeitraum($e)) { $vorgaenge[] = $basis + ['vorgang' => 'eingezogen', 'datum' => $e, 'von' => (string)($d['eingezogen']['von'] ?? ''), 'notiz' => (string)($d['eingezogen']['grund'] ?? '')]; $dz['eingezogen']++; }
        $ue = qs_ueberpruefung($d, $monateU, $heute);
        if ($ue && $ue['faellig']) { $faellig[] = $basis + ['seit' => $ue['seit'], 'faelligAb' => $ue['faelligAb']]; $dz['faellig']++; }
    }
    $nachNr = function ($a, $b) { return qs_nat_cmp($a['kapitel'], $b['kapitel']) ?: strnatcasecmp($a['nr'], $b['nr']); };
    usort($vorgaenge, function ($a, $b) use ($nachNr) { return strcmp($a['datum'], $b['datum']) ?: $nachNr($a, $b); });
    usort($faellig, function ($a, $b) use ($nachNr) { return strcmp($a['seit'], $b['seit']) ?: $nachNr($a, $b); });

    /* Handbuch */
    $hb = [];
    foreach ($handbuch as $a) foreach ((array)($a['aenderungen'] ?? []) as $c) {
        if (!$imZeitraum((string)($c['datum'] ?? ''))) continue;
        $hb[] = ['datum' => (string)$c['datum'], 'kapitel' => (string)$a['kapitel'], 'nr' => (string)($a['nr'] ?? ''), 'titel' => (string)$a['titel'],
                 'was' => (string)($c['was'] ?? ''), 'grund' => (string)($c['grund'] ?? ''), 'von' => (string)($c['von'] ?? '')];
    }
    usort($hb, function ($a, $b) { return strcmp($a['datum'], $b['datum']) ?: (qs_nat_cmp($a['kapitel'], $b['kapitel']) ?: qs_nat_cmp($a['nr'], $b['nr'])); });

    $kt = []; foreach ($stamm['kapitel'] as $k) $kt[(string)$k['id']] = (string)$k['titel'];
    return ['von' => $von, 'bis' => $bis, 'heute' => $heute, 'monate' => $monate, 'kapitel' => $kt,
            'kennzahlen' => ['pruefplan' => $kz, 'massnahmen' => $mz, 'dokumente' => $dz, 'handbuch' => count($hb)],
            'pruefungen' => $pruefungen, 'abweichungen' => $abweichungen, 'massnahmen' => $mListe,
            'dokumente' => ['vorgaenge' => $vorgaenge, 'faellig' => $faellig], 'handbuch' => $hb];
}

/* ---------- Excel ---------- */
function qs_bericht_periode(string $art, string $per): string
{
    if ($art === 'tag') return qs_de($per);
    if ($art === 'woche') return 'KW ' . (int)substr($per, 6) . '/' . substr($per, 0, 4);
    return substr($per, 5, 2) . '/' . substr($per, 0, 4);
}
function qs_bericht_monat(string $m): string { return ['Jan', 'Feb', 'Mär', 'Apr', 'Mai', 'Jun', 'Jul', 'Aug', 'Sep', 'Okt', 'Nov', 'Dez'][(int)substr($m, 5, 2) - 1] . ' ' . substr($m, 2, 2); }
function qs_xl_spalte(int $n): string { $s = ''; for ($n++; $n > 0; $n = intdiv($n - 1, 26)) $s = chr(65 + ($n - 1) % 26) . $s; return $s; }
function qs_xl_text(string $t): string { return htmlspecialchars(preg_replace('/[\x00-\x08\x0b\x0c\x0e-\x1f]/', '', $t) ?? '', ENT_XML1 | ENT_QUOTES, 'UTF-8'); }
/* Stile: 0 Standard, 1 Kopfzeile, 2 Titel, 3 Hinweis, 4 fett, 5 Prozent, 6 Text mit Umbruch */
function qs_xl_stile(): string
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
        . '<cellXfs count="7"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top"/></xf>'
        . '<xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>'
        . '<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        . '<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        . '<xf numFmtId="0" fontId="4" fillId="0" borderId="0" xfId="0" applyFont="1"/>'
        . '<xf numFmtId="9" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment vertical="top"/></xf>'
        . '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment vertical="top" wrapText="1"/></xf></cellXfs>'
        . '<cellStyles count="1"><cellStyle name="Standard" xfId="0" builtinId="0"/></cellStyles></styleSheet>';
}
/* Blatt: Zeilen aus Zellen (Wert oder [Wert, Stil]); $kopf = Zeile der Kopfzeile (1-basiert, 0 = keine); $umbruch = Spalten mit Umbruch */
function qs_xl_blatt(array $zeilen, array $breiten, int $kopf, array $umbruch = []): string
{
    $xml = '';
    foreach ($zeilen as $zi => $zeile) {
        $r = $zi + 1;
        $xml .= '<row r="' . $r . '"' . ($r === $kopf ? ' ht="30" customHeight="1"' : '') . '>';
        foreach ($zeile as $si => $zelle) {
            [$wert, $stil] = is_array($zelle) ? $zelle : [$zelle, $r === $kopf ? 1 : (in_array($si, $umbruch, true) ? 6 : 0)];
            $ref = qs_xl_spalte($si) . $r;
            if ($wert === null || $wert === '') continue;
            if (is_int($wert) || is_float($wert)) $xml .= '<c r="' . $ref . '" s="' . $stil . '"><v>' . $wert . '</v></c>';
            else $xml .= '<c r="' . $ref . '" s="' . $stil . '" t="inlineStr"><is><t xml:space="preserve">' . qs_xl_text((string)$wert) . '</t></is></c>';
        }
        $xml .= '</row>';
    }
    $cols = '';
    foreach ($breiten as $i => $b) $cols .= '<col min="' . ($i + 1) . '" max="' . ($i + 1) . '" width="' . $b . '" customWidth="1"/>';
    $letzte = max(1, count($zeilen));
    $filter = $kopf > 0 && $letzte > $kopf ? '<autoFilter ref="A' . $kopf . ':' . qs_xl_spalte(count($breiten) - 1) . $letzte . '"/>' : '';
    return '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n"
        . '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        . '<sheetPr><pageSetUpPr fitToPage="1"/></sheetPr>'
        . '<sheetViews><sheetView workbookViewId="0">' . ($kopf > 0 ? '<pane ySplit="' . $kopf . '" topLeftCell="A' . ($kopf + 1) . '" activePane="bottomLeft" state="frozen"/>' : '') . '</sheetView></sheetViews>'
        . '<cols>' . $cols . '</cols><sheetData>' . $xml . '</sheetData>' . $filter
        . '<pageMargins left="0.4" right="0.4" top="0.5" bottom="0.5" header="0.3" footer="0.3"/><pageSetup paperSize="9" orientation="landscape" fitToWidth="1" fitToHeight="0"/></worksheet>';
}
function qs_xl_mappe(array $blaetter, string $titel): string
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
        $sheets .= '<sheet name="' . qs_xl_text(mb_substr($name, 0, 31)) . '" sheetId="' . $n . '" r:id="rId' . $n . '"/>';
        $dateien['xl/worksheets/sheet' . $n . '.xml'] = ['neu' => $xml];
    }
    $k = count($blaetter) + 1;
    $rels .= '<Relationship Id="rId' . $k . '" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>';
    $ct .= '</Types>';
    $jetzt = gmdate('Y-m-d\TH:i:s\Z');
    $teile = [
        '[Content_Types].xml' => $ct,
        '_rels/.rels' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            . '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            . '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
            . '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>',
        'docProps/core.xml' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
            . '<dc:title>' . qs_xl_text($titel) . '</dc:title><dc:creator>STAFL-Plattform · QM-System</dc:creator><dcterms:created xsi:type="dcterms:W3CDTF">' . $jetzt . '</dcterms:created></cp:coreProperties>',
        'docProps/app.xml' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties"><Application>STAFL-Plattform</Application></Properties>',
        'xl/workbook.xml' => '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' . "\n" . '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            . '<bookViews><workbookView/></bookViews><sheets>' . $sheets . '</sheets></workbook>',
        'xl/_rels/workbook.xml.rels' => $rels,
        'xl/styles.xml' => qs_xl_stile(),
    ];
    return qs_zip_bauen(array_map(function ($x) { return ['neu' => $x]; }, $teile) + $dateien, '');
}

const QS_BERICHT_STATUS = ['eingehalten' => 'eingehalten', 'verspaetet' => 'verspätet', 'ueberfaellig' => 'überfällig', 'offen' => 'fällig am Stichtag', 'nie' => 'noch nie geprüft'];
const QS_BERICHT_VORGANG = ['freigabe' => 'Freigabe', 'ueberprueft' => 'Überprüft ohne Änderung', 'eingezogen' => 'Eingezogen'];

/* Arbeitsmappe: Zusammenfassung, Prüfplan (je Monat), Versäumnisse und Fristen, Abweichungen, Maßnahmen, Dokumente,
   Überprüfung fällig, Handbuch */
function qs_bericht_xlsx(array $b, string $wer): string
{
    $kz = $b['kennzahlen']; $p = $kz['pruefplan']; $m = $kz['massnahmen']; $d = $kz['dokumente'];
    $zeitraum = qs_de($b['von']) . ' – ' . qs_de($b['bis']);
    $kap = function (string $id) use ($b) { return trim($id . ' ' . ($b['kapitel'][$id] ?? '')); };

    $z = [[['QM-System · Audit-Bericht', 2]], ['Zeitraum: ' . $zeitraum], ['Erstellt am ' . qs_de($b['heute']) . ($wer !== '' ? ' von ' . $wer : '')],
          [['Status von Dokumenten und Maßnahmen: Stand ' . qs_de($b['heute']) . '. Nachweise nach dem Stichtag zählen nicht.', 3]], [],
          ['Bereich', 'Kennzahl', 'Wert']];
    $z[] = ['Prüfplan', 'Fällige Perioden (täglich, wöchentlich, monatlich)', $p['faellig']];
    $z[] = ['Prüfplan', 'davon erfüllt', $p['erfuellt']];
    $z[] = ['Prüfplan', 'Erfüllungsquote', $p['quote'] === null ? '' : [(float)$p['quote'], 5]];
    $z[] = ['Prüfplan', 'Versäumte Perioden', $p['versaeumt']];
    $z[] = ['Prüfplan', 'Fristen längerer Intervalle', $p['fristen']];
    $z[] = ['Prüfplan', 'davon eingehalten', $p['eingehalten']];
    $z[] = ['Prüfplan', 'davon verspätet', $p['verspaetet']];
    $z[] = ['Prüfplan', 'davon überfällig bzw. noch nie geprüft', $p['ueberfaellig'] + $p['nie']];
    $z[] = ['Prüfplan', 'Nachweise im Zeitraum', $p['nachweise']];
    $z[] = ['Prüfplan', 'davon Abweichungen', $p['abweichungen']];
    $z[] = ['Prüfplan', 'Stornierte Nachweise im Zeitraum', $p['storniert']];
    $z[] = ['Maßnahmen', 'Erfasst im Zeitraum', $m['erfasst']];
    $z[] = ['Maßnahmen', 'Wirksam abgeschlossen im Zeitraum', $m['abgeschlossen']];
    $z[] = ['Maßnahmen', 'Offen (Stand heute)', $m['offen']];
    $z[] = ['Maßnahmen', 'davon überfällig', $m['ueberfaellig']];
    $z[] = ['Dokumente', 'Gültige gelenkte Dokumente (Stand heute)', $d['gueltig']];
    $z[] = ['Dokumente', 'In Überarbeitung oder Prüfung', $d['inArbeit']];
    $z[] = ['Dokumente', 'Noch nie freigegeben', $d['ohneFreigabe']];
    $z[] = ['Dokumente', 'Überprüfung fällig', $d['faellig']];
    $z[] = ['Dokumente', 'Freigaben im Zeitraum', $d['freigaben']];
    $z[] = ['Dokumente', 'Ohne Änderung überprüft im Zeitraum', $d['ueberprueft']];
    $z[] = ['Dokumente', 'Eingezogen im Zeitraum', $d['eingezogen']];
    $z[] = ['Handbuch', 'Änderungen im Zeitraum', $kz['handbuch']];
    $blaetter = [['Zusammenfassung', qs_xl_blatt($z, [14, 48, 12], 6)]];

    $kopf = ['Kapitel', 'Prüfung', 'Intervall', 'Zuständig', 'Durchführung', 'Fällig', 'Erfüllt', 'Quote', 'Versäumt', 'Fristen eingehalten', 'verspätet', 'überfällig', 'Nachweise', 'Abweichungen'];
    foreach ($b['monate'] as $mo) $kopf[] = qs_bericht_monat($mo);
    $z = [$kopf];
    foreach ($b['pruefungen'] as $x) {
        $fr = ['eingehalten' => 0, 'verspaetet' => 0, 'ueberfaellig' => 0];
        foreach ($x['fristen'] as $f) {
            if ($f['status'] === 'eingehalten' || $f['status'] === 'verspaetet') $fr[$f['status']]++;
            elseif ($f['status'] === 'ueberfaellig' || $f['status'] === 'nie') $fr['ueberfaellig']++;
        }
        $roll = $x['art'] === 'rollend';
        $r = [$kap($x['kapitel']), $x['titel'], $x['intervallText'] . ($x['art'] === 'inaktiv' ? ' (inaktiv)' : ''), $x['zustaendig'], implode(', ', $x['ausfuehrende']),
              $x['faellig'], $x['erfuellt'], $x['faellig'] ? [round($x['erfuellt'] / $x['faellig'], 4), 5] : '', $x['versaeumt'],
              $roll ? $fr['eingehalten'] : '', $roll ? $fr['verspaetet'] : '', $roll ? $fr['ueberfaellig'] : '', $x['nachweise'], $x['abweichungen']];
        foreach ($b['monate'] as $mo) {
            $c = $x['monate'][$mo] ?? [];
            $r[] = $x['art'] === 'kalender' ? (isset($c['f']) ? $c['e'] . '/' . $c['f'] : '') : ($c['n'] ?? '');
        }
        $z[] = $r;
    }
    $z[] = []; $z[] = [['Monatsspalten: täglich/wöchentlich/monatlich erfüllt/fällig (Perioden, gezählt im Monat ihres Endes); sonst Anzahl der Nachweise.', 3]];
    $blaetter[] = ['Prüfplan', qs_xl_blatt($z, array_merge([22, 34, 20, 10, 22, 8, 8, 8, 9, 11, 9, 9, 10, 12], array_fill(0, count($b['monate']), 8)), 1, [1, 4])];

    $z = [['Kapitel', 'Prüfung', 'Intervall', 'Art', 'Von / fällig am', 'Bis / erledigt am', 'Anzahl / Tage']];
    foreach ($b['pruefungen'] as $x) {
        $art = QS_KALENDER[$x['intervall']] ?? '';
        foreach ($x['bereiche'] as [$a, $e, $n]) $z[] = [$kap($x['kapitel']), $x['titel'], $x['intervallText'], 'versäumt', qs_bericht_periode($art, $a), qs_bericht_periode($art, $e), $n];
        foreach ($x['fristen'] as $f) if ($f['status'] !== 'eingehalten')
            $z[] = [$kap($x['kapitel']), $x['titel'], $x['intervallText'], QS_BERICHT_STATUS[$f['status']], qs_de($f['faellig']), qs_de($f['erledigt']), $f['tage'] ?? ''];
    }
    $blaetter[] = ['Versäumnisse', qs_xl_blatt($z, [22, 34, 20, 18, 16, 16, 13], 1, [1])];

    $z = [['Datum', 'Kapitel', 'Prüfung', 'Feststellung', 'Durchgeführt von', 'Maßnahme', 'Status der Maßnahme']];
    foreach ($b['abweichungen'] as $x) $z[] = [qs_de($x['datum']), $kap($x['kapitel']), $x['pruefung'], $x['bemerkung'], $x['durch'], $x['massnahme']['nr'] ?? '', isset($x['massnahme']) ? (QS_MASSN_STATUS[$x['massnahme']['status']] ?? '') : ''];
    $blaetter[] = ['Abweichungen', qs_xl_blatt($z, [11, 22, 30, 50, 18, 11, 20], 1, [2, 3])];

    $z = [['Nr.', 'Quelle', 'Kapitel', 'Bewertung', 'Feststellung', 'Korrekturmaßnahme', 'Zuständig', 'Frist', 'Status', 'Überfällig', 'Erfasst', 'Abgeschlossen', 'Wirksamkeit']];
    foreach ($b['massnahmen'] as $x) $z[] = [$x['nr'], QS_QUELLEN[$x['quelle']] ?? $x['quelle'], $x['kapitel'], $x['bewertung'], $x['feststellung'], $x['massnahme'], $x['zustaendig'],
                                              qs_de($x['frist']), QS_MASSN_STATUS[$x['status']] ?? $x['status'], $x['ueberfaellig'] ? 'ja' : '', qs_de($x['erfasst']), qs_de($x['abgeschlossen']), $x['wirksamkeit']];
    $blaetter[] = ['Maßnahmen', qs_xl_blatt($z, [10, 18, 9, 10, 46, 46, 11, 11, 18, 10, 11, 13, 36], 1, [4, 5, 12])];

    $z = [['Datum', 'Vorgang', 'Kapitel', 'Nr.', 'Titel', 'Version', 'Änderungen / Notiz', 'Grund', 'erstellt', 'geprüft', 'freigegeben / durch']];
    foreach ($b['dokumente']['vorgaenge'] as $x) {
        $frei = $x['vorgang'] === 'freigabe';
        $z[] = [qs_de($x['datum']), QS_BERICHT_VORGANG[$x['vorgang']], $kap($x['kapitel']), $x['nr'], $x['titel'], $frei ? $x['version'] : '', $frei ? $x['aenderungen'] : $x['notiz'],
                $frei ? $x['grund'] : '', $frei ? $x['erstellt'] : '', $frei ? $x['geprueft'] : '', $frei ? $x['freigegeben'] : $x['von']];
    }
    $blaetter[] = ['Dokumente', qs_xl_blatt($z, [11, 22, 22, 11, 36, 8, 40, 30, 10, 10, 14], 1, [4, 6, 7])];

    $z = [['Kapitel', 'Nr.', 'Titel', 'Art', 'Freigegeben bzw. überprüft am', 'Überprüfung fällig seit']];
    foreach ($b['dokumente']['faellig'] as $x) $z[] = [$kap($x['kapitel']), $x['nr'], $x['titel'], QS_ARTEN[$x['art']] ?? $x['art'], qs_de($x['seit']), qs_de($x['faelligAb'])];
    $blaetter[] = ['Überprüfung fällig', qs_xl_blatt($z, [22, 11, 44, 16, 16, 16], 1, [2])];

    $z = [['Datum', 'Kapitel', 'Abschnitt', 'Prozessschritt', 'Änderung', 'Grund', 'von']];
    foreach ($b['handbuch'] as $x) $z[] = [qs_de($x['datum']), $kap($x['kapitel']), $x['nr'], $x['titel'], $x['was'], $x['grund'], $x['von']];
    $blaetter[] = ['Handbuch', qs_xl_blatt($z, [11, 22, 10, 32, 44, 32, 18], 1, [3, 4, 5])];

    return qs_xl_mappe($blaetter, 'QM-System · Audit-Bericht ' . $zeitraum);
}
