<?php
declare(strict_types=1);
/* Modul HR · Jahresplanung des Urlaubs (Inhaber 03.11.2026, Vorplanung und Einzeltage 10.11.2026).
   Jeder Mitarbeiter plant bis zum Stichtag (Standard 31.12., bis 10.11.2026: 01.12.) mindestens einen Anteil (Standard 90 %) seines Urlaubsanspruchs
   des nächsten Jahres vor – mit normalen Urlaubsanträgen und einer Vertretung je Zeitraum. Ab dem Planungsbeginn (Standard
   01.10.) zeigt die Urlaubsseite den Stand; die Personalstelle erinnert per E-Mail an alle, die das Ziel noch nicht erreicht
   haben. Die Ansicht „Jahresplanung“ (nur Personalstelle – sie enthält alle Urlaubszeiträume; zusammen mit dem Kalender
   ließen sich sonst Krankheitstage ableiten, unabhängige Prüfung 03.11.2026) fasst alles zusammen: Stand je Mitarbeiter,
   Zeitleiste, Konflikte je Antrag (Vertretung fehlt oder ist selbst abwesend, Überschneidung in der Abteilung, Urlaubssperre,
   über dem Resturlaub). Konfliktfreie Anträge lassen sich gesammelt genehmigen (hr.genehmigen, nie die eigenen). Nach dem
   Abschluss bekommt jeder Mitarbeiter seine Jahresübersicht per E-Mail.
   Vorplanung (Inhaber 10.11.2026): mit dem Schalter „Vorplanung“ beantragt ein Mitarbeiter mehrere Zeiträume des nächsten
   Jahres auf einmal (hr_vorplanung – alle oder keiner); jeder Zeitraum wird wie ein einzelner Antrag geprüft, auch ob die
   Vertretung da ist (hr_antrag_zeitraum, Vorschau: hr_antrag_pruefen). In der Vorplanung höchstens einzeltageMax (Standard
   4) einzelne Urlaubstage, der übrige Urlaub möglichst zusammenhängend: darüber Hinweis an den Mitarbeiter und Konflikt
   „einzeltage“ in der Jahresplanung (die Personalstelle entscheidet einzeln). Vorplanung = bis zum Stichtag erfasst.
   Gespeichert im eigenen Dokument hr-einstellungen, Feld „planung“ (nur erweitert – GR-006): {start, stichtag (MM-TT),
   prozent, vertretungPflicht, einzeltageMax, abschluss: {"JJJJ": {t, by, byId}}}. Fehlende Felder: Standardwerte. Anträge selbst stehen
   wie immer in hr-abwesenheiten. Gründe anderer Abwesenheiten (z. B. Krankheit) erscheinen nie – nur „abwesend“.
   Eingebunden von module/hr/urlaub.php. */
if (!defined('WA_API')) { http_response_code(404); exit; }

const HR_PLANUNG_START = '10-01';
const HR_PLANUNG_STICHTAG = '12-31';   // Inhaber 10.11.2026 („bis zum 31.12. einreichen“; vorher 01.12.)
const HR_PLANUNG_PROZENT = 90;
const HR_PLANUNG_EINZELTAGE = 4;       // höchstens so viele einzelne Urlaubstage in der Vorplanung (0 = keine Prüfung)
const HR_VORPLANUNG_MAX = 20;          // Zeiträume je Vorplanung (ein Absenden)

/* Einstellungen der Jahresplanung (fehlende oder ungültige Felder: Standard) */
function hr_planung_einst(?array $d = null): array
{
    $d = $d ?? (store_read('hr-einstellungen') ?? []);
    $p = is_array($d['planung'] ?? null) ? $d['planung'] : [];
    $proz = $p['prozent'] ?? HR_PLANUNG_PROZENT;
    $abschluss = [];
    foreach ((array)($p['abschluss'] ?? []) as $j => $a) if (preg_match('/^\d{4}$/', (string)$j) && is_array($a)) $abschluss[(string)$j] = $a;
    return ['start' => hr_uebertrag_bis_norm($p['start'] ?? null) ?? HR_PLANUNG_START, 'stichtag' => hr_uebertrag_bis_norm($p['stichtag'] ?? null) ?? HR_PLANUNG_STICHTAG,
            'prozent' => is_int($proz) && $proz >= 10 && $proz <= 100 ? $proz : HR_PLANUNG_PROZENT,
            // Vertretung bei Urlaubsanträgen Pflicht (Regel 6 der Urlaubsregeln); nur ein ausdrückliches false schaltet sie ab
            'vertretungPflicht' => ($p['vertretungPflicht'] ?? true) !== false,
            'einzeltageMax' => is_int($p['einzeltageMax'] ?? null) && $p['einzeltageMax'] >= 0 && $p['einzeltageMax'] <= 50 ? $p['einzeltageMax'] : HR_PLANUNG_EINZELTAGE,
            'abschluss' => $abschluss];
}
/* Einstellungen aus der Verwaltung prüfen (hr_einstellungen_save, Feld „planung“): {start, stichtag, prozent, vertretungPflicht,
   einzeltageMax (optional – ohne Angabe bleibt der gespeicherte Wert)} */
function hr_planung_einst_pruefen($b): array
{
    if (!is_array($b)) throw new InvalidArgumentException('Jahresplanung: Angaben fehlen.');
    $start = hr_uebertrag_bis_norm($b['start'] ?? null);
    $stich = hr_uebertrag_bis_norm($b['stichtag'] ?? null);
    if ($start === null || $stich === null) throw new InvalidArgumentException('Jahresplanung: bitte Beginn und Stichtag als gültiges Datum wählen (der 29.02. ist nicht möglich).');
    if ($start >= $stich) throw new InvalidArgumentException('Jahresplanung: der Beginn muss vor dem Stichtag liegen.');
    $proz = $b['prozent'] ?? null;
    if (!is_int($proz) || $proz < 10 || $proz > 100) throw new InvalidArgumentException('Jahresplanung: Anteil bitte als ganze Zahl zwischen 10 und 100 Prozent.');
    if (!is_bool($b['vertretungPflicht'] ?? null)) throw new InvalidArgumentException('Jahresplanung: Vertretung Pflicht bitte ja oder nein.');
    $out = ['start' => $start, 'stichtag' => $stich, 'prozent' => $proz, 'vertretungPflicht' => $b['vertretungPflicht']];
    if (array_key_exists('einzeltageMax', $b)) {
        $e = $b['einzeltageMax'];
        if (!is_int($e) || $e < 0 || $e > 50) throw new InvalidArgumentException('Jahresplanung: einzelne Urlaubstage bitte als ganze Zahl zwischen 0 (keine Prüfung) und 50.');
        $out['einzeltageMax'] = $e;
    }
    return $out;
}
/* Das Jahr, das geplant wird: das nächste Kalenderjahr */
function hr_planung_jahr(?string $heute = null): int { return (int)substr($heute ?? hr_heute(), 0, 4) + 1; }
/* Stichtag und Beginn als Datum (im Jahr vor dem Planungsjahr) */
function hr_planung_daten(array $pe, int $jahr): array { return ['start' => ($jahr - 1) . '-' . $pe['start'], 'stichtag' => ($jahr - 1) . '-' . $pe['stichtag']]; }

/* Stand einer Person: Anspruch, Ziel (Anteil des Anspruchs, auf halbe Tage aufgerundet), geplant = beantragt + genehmigt
   (Schließtage je ½), einzelne Urlaubstage der Vorplanung und noch nicht eingeplante Schließtage (24.12./31.12.).
   $zusatz: noch nicht gespeicherte Zeiträume ([{von, bis}], Vorschau der Vorplanung) – zählen wie beantragt. */
function hr_planung_person(array $p, array $eintraege, int $jahr, array $pe, array $zusatz = []): array
{
    $frei = hr_freie_tage($eintraege, $p['id']);
    $gen = 0.0; $bea = 0.0; $belegt = [];
    $jv = "$jahr-01-01"; $jb = "$jahr-12-31";
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id'] || !in_array($e['status'], HR_AKTIV, true) || $e['bis'] < $jv || $e['von'] > $jb) continue;
        foreach (HR_SCHLIESSTAGE as $md => $_) if ($e['von'] <= "$jahr-$md" && "$jahr-$md" <= $e['bis']) $belegt["$jahr-$md"] = true;
        if ($e['art'] !== 'U') continue;
        $n = hr_tage_summe(hr_tage($p, $e['von'], $e['bis'], $jv, $jb, $frei));
        if ($e['status'] === 'genehmigt') $gen += $n; else $bea += $n;
    }
    foreach ($zusatz as $z) {
        $bea += hr_tage_summe(hr_tage($p, $z['von'], $z['bis'], $jv, $jb, $frei));
        foreach (HR_SCHLIESSTAGE as $md => $_) if ($z['von'] <= "$jahr-$md" && "$jahr-$md" <= $z['bis']) $belegt["$jahr-$md"] = true;
    }
    $anspruch = hr_anspruch($p, $jahr);
    $ziel = ceil($anspruch * $pe['prozent'] / 100 * 2) / 2;
    $geplant = $gen + $bea;
    // Schließtage, an denen die Person arbeiten würde und noch nichts eingetragen ist (Urlaub, Gleittag, Krank, freier Tag)
    $offen = [];
    foreach (hr_schliesstage($jahr) as $d => $_) if (hr_arbeitstag($p, $d) && !isset($frei[$d]) && !isset($belegt[$d])) $offen[] = $d;
    return ['anspruch' => $anspruch, 'ziel' => $ziel, 'genehmigt' => $gen, 'beantragt' => $bea, 'geplant' => $geplant,
            'fehlt' => max(0.0, $ziel - $geplant), 'erreicht' => $geplant >= $ziel, 'anteil' => $anspruch > 0 ? (int)round($geplant / $anspruch * 100) : 100,
            'einzeltage' => hr_einzeltage($p, $eintraege, $jahr, $pe, $zusatz), 'einzeltageMax' => $pe['einzeltageMax'], 'schliesstageOffen' => $offen];
}

/* Entstand der Eintrag in der Vorplanung des Jahres? = bis zum Stichtag erfasst (UTC-Zeit, ohne Erfassungszeit: nein) */
function hr_vorplanung_eintrag(array $e, int $jahr, array $pe): bool
{
    $t = (string)($e['erfasst']['t'] ?? '');
    return $t !== '' && substr($t, 0, 10) <= hr_planung_daten($pe, $jahr)['stichtag'];
}

/* Hinweis beim einzelnen Antrag (hr_antrag): liegt er in der Vorplanung seines Jahres und sind es damit mehr einzelne
   Urlaubstage als vorgesehen? Der Antrag gilt trotzdem; die Jahresplanung zeigt ihn als Konflikt „einzeltage“. */
function hr_einzeltage_hinweis(array $p, array $eintraege, array $e): ?string
{
    if ($e['art'] !== 'U') return null;
    $pe = hr_planung_einst(); $jahr = (int)substr($e['von'], 0, 4);
    if ($pe['einzeltageMax'] <= 0 || !hr_vorplanung_eintrag($e, $jahr, $pe)) return null;
    $n = count(hr_einzeltage($p, $eintraege, $jahr, $pe));
    return $n > $pe['einzeltageMax'] ? "In der Vorplanung $jahr sind damit $n einzelne Urlaubstage geplant – vorgesehen sind höchstens {$pe['einzeltageMax']}, der übrige Urlaub möglichst zusammenhängend. Die Personalstelle prüft das." : null;
}

/* Einzelne Urlaubstage der Vorplanung eines Jahres (Inhaber 10.11.2026: höchstens einzeltageMax, der übrige Urlaub möglichst
   zusammenhängend). Urlaub der Vorplanung (beantragt, genehmigt, bis zum Stichtag erfasst) und $zusatz werden zu Blöcken
   zusammengefasst: aufeinanderfolgende Urlaubstage – auch über Tage ohne Arbeit (Wochenende, Feiertag, freier Tag),
   Gleittage und Schließtage hinweg (Fr + Mo ist ein Block). Ein Block mit genau einem Urlaubstag ist ein Einzeltag;
   Schließtage (24.12./31.12.) zählen dabei nicht mit. Rückgabe: Daten der Einzeltage. */
function hr_einzeltage(array $p, array $eintraege, int $jahr, array $pe, array $zusatz = []): array
{
    $jv = "$jahr-01-01"; $jb = "$jahr-12-31";
    $frei = hr_freie_tage($eintraege, $p['id']);
    $liste = $zusatz; $bruecke = [];
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id'] || !in_array($e['status'], HR_AKTIV, true) || $e['bis'] < $jv || $e['von'] > $jb) continue;
        if ($e['art'] === 'U' && hr_vorplanung_eintrag($e, $jahr, $pe)) $liste[] = $e;
        elseif ($e['art'] === 'G') for ($d = max($e['von'], $jv), $ende = min($e['bis'], $jb); $d <= $ende; $d = hr_plus($d, 1)) $bruecke[$d] = true;
    }
    $urlaub = [];
    foreach ($liste as $e) foreach (hr_tage($p, $e['von'], $e['bis'], $jv, $jb, $frei) as $d) $urlaub[$d] = true;
    ksort($urlaub);
    $einzel = []; $block = []; $vorher = null;
    $abschluss = function (array $b) use (&$einzel) {
        $z = array_values(array_filter($b, function ($d) { return hr_schliesstag($d) === null; }));
        if (count($z) === 1) $einzel[] = $z[0];
    };
    foreach (array_keys($urlaub) as $d) {
        if ($vorher !== null) {
            for ($x = hr_plus($vorher, 1); $x < $d; $x = hr_plus($x, 1)) {
                if (hr_arbeitstag($p, $x) && !isset($frei[$x]) && !isset($bruecke[$x]) && hr_schliesstag($x) === null) { $abschluss($block); $block = []; break; }
            }
        }
        $block[] = $d; $vorher = $d;
    }
    if ($block) $abschluss($block);
    return $einzel;
}

/* Hinweis auf der Urlaubsseite des Mitarbeiters: nur in der Planungsphase (ab Beginn, bis die Planung abgeschlossen ist) */
function hr_planung_ich(?array $ich, array $eintraege, ?string $heute = null): ?array
{
    if (!$ich || !$ich['aktiv']) return null;
    $heute = $heute ?? hr_heute();
    $pe = hr_planung_einst(); $j = hr_planung_jahr($heute); $dt = hr_planung_daten($pe, $j);
    if ($heute < $dt['start'] || isset($pe['abschluss'][(string)$j]) || hr_anspruch($ich, $j) <= 0) return null;   // ohne Anspruch nichts zu planen
    return ['jahr' => $j, 'stichtag' => $dt['stichtag'], 'prozent' => $pe['prozent'], 'vorbei' => $heute > $dt['stichtag']] + hr_planung_person($ich, $eintraege, $j, $pe);
}

/* Überschneidung zweier Zeiträume */
function hr_planung_schnitt(array $a, array $b): bool { return $a['von'] <= $b['bis'] && $b['von'] <= $a['bis']; }

/* Wann ist die Vertretung im Zeitraum eines Antrags nicht da? Arbeitstage des Antragstellers, an denen die Vertretung abwesend
   ist (jede Abwesenheit außer freien Tagen) oder nicht arbeitet (eigene Arbeitstage, freie Tage, z. B. Teilzeit).
   $nurGenehmigt: nur genehmigte Abwesenheiten – für den Hinweis an den Mitarbeiter (wie im Kalender, nie offene Anträge anderer).
   Rückgabe ['abwesend' => [Daten], 'frei' => [Daten]] */
function hr_vertretung_luecken(array $e, array $p, array $vp, array $eintraege, bool $nurGenehmigt = false): array
{
    // an Schließtagen (24.12./31.12.) ist der Betrieb zu – dort braucht niemand eine Vertretung
    $tage = array_values(array_filter(hr_tage($p, $e['von'], $e['bis'], null, null, hr_freie_tage($eintraege, $p['id'])), function ($d) { return hr_schliesstag($d) === null; }));
    $arbeit = array_flip(hr_tage($vp, $e['von'], $e['bis'], null, null, hr_freie_tage($eintraege, $vp['id'])));
    $weg = [];
    foreach ($eintraege as $o) {
        if ($o['person'] !== $vp['id'] || $o['art'] === 'X' || !hr_planung_schnitt($o, $e)) continue;
        if ($nurGenehmigt ? $o['status'] !== 'genehmigt' : !in_array($o['status'], HR_AKTIV, true)) continue;
        for ($d = max($o['von'], $e['von']), $ende = min($o['bis'], $e['bis']); $d <= $ende; $d = hr_plus($d, 1)) $weg[$d] = true;
    }
    $ab = []; $fr = [];
    foreach ($tage as $d) { if (isset($weg[$d])) $ab[] = $d; elseif (!isset($arbeit[$d])) $fr[] = $d; }
    return ['abwesend' => $ab, 'frei' => $fr];
}
/* Prüfung eines Zeitraums für einen eigenen Antrag – gemeinsam für hr_antrag, hr_vorplanung und die Vorschau
   hr_antrag_pruefen. Dieselben Regeln wie bisher im Antrag (vergangen, keine Arbeitstage, Gleittage-Konto, Sperre,
   Überschneidung, Vertretung Pflicht), dazu die Vertretungsprüfung (Inhaber 10.11.2026): ist die Vertretung im Zeitraum
   nachweislich abwesend – genehmigt, wie im Kalender; nie offene Anträge oder Gründe anderer –, wird abgelehnt (Regel
   „Ihr Urlaub darf sich nicht mit dem Ihrer Vertretung überschneiden“); arbeitet sie an einzelnen Tagen nur nicht (z. B.
   Teilzeit), bleibt es ein Hinweis. Schließtage (24.12./31.12.) brauchen keine Vertretung; ein Zeitraum nur aus
   Schließtagen auch ohne Vertretung. $andere: weitere Zeiträume derselben Vorplanung (keine Überschneidung untereinander).
   Rückgabe: {von, bis, tage (Schließtage je ½), fehler (erster Grund zur Ablehnung) und code, hinweise[],
   vertretung: null|{id, name, status da|abwesend|frei, text}} */
function hr_antrag_zeitraum(array $ich, array $personal, array $eintraege, array $einst, string $art, string $von, string $bis, $vertretung, array $andere = []): array
{
    $r = ['von' => $von, 'bis' => $bis, 'tage' => 0.0, 'fehler' => null, 'code' => 200, 'hinweise' => [], 'vertretung' => null];
    $f = function (string $text, int $code) use (&$r) { if ($r['fehler'] === null) { $r['fehler'] = $text; $r['code'] = $code; } };
    if ($von < hr_heute()) $f('Urlaub kann nur für heute oder später beantragt werden. Vergangene Tage trägt die Personalstelle ein.', 422);
    $tage = hr_tage($ich, $von, $bis, null, null, hr_freie_tage($eintraege, $ich['id']));
    $r['tage'] = hr_tage_summe($tage, $art);
    if (!$tage) $f('Im gewählten Zeitraum liegen keine Arbeitstage (Wochenende, Feiertag oder freier Tag).', 422);
    if ($art === 'G' && $tage) {
        $gk = hr_gleit_konto($ich, $eintraege, (int)substr($von, 0, 4));
        if (!$gk['aktiv']) $f('Sie haben noch keine Gleittage. Gleittage gewährt die Personalstelle.', 409);
        elseif ($r['tage'] > $gk['verfuegbar']) $f('Dafür reicht Ihr Gleittage-Konto nicht: verfügbar ' . hr_zahl_text(max(0.0, (float)$gk['verfuegbar'])) . ' Tage, beantragt ' . hr_zahl_text($r['tage']) . '.', 409);
    }
    if ($s = hr_ueberschneidung($einst['sperren'], $von, $bis)) $f('Im Zeitraum ' . hr_zeitraum_text($s['von'], $s['bis']) . ' gilt eine Urlaubssperre' . ($s['text'] !== '' ? ' (' . $s['text'] . ')' : '') . '.', 422);
    if ($k = hr_kollision($eintraege, $ich['id'], $von, $bis, null, 'U')) $f('Für ' . hr_zeitraum_text($k['von'], $k['bis']) . ' gibt es bereits einen Eintrag.', 409);
    foreach ($andere as $o) if ($o['von'] <= $bis && $von <= $o['bis']) { $f('Überschneidet sich mit ' . hr_zeitraum_text($o['von'], $o['bis']) . ' in dieser Vorplanung.', 422); break; }
    $nurSchliess = $tage && !array_filter($tage, function ($d) { return hr_schliesstag($d) === null; });
    if ($vertretung !== null && $vertretung !== '') {
        $vp = hr_personen_index($personal)[(string)$vertretung] ?? null;
        if (!$vp || !$vp['aktiv'] || $vp['id'] === $ich['id']) { $f('Bitte eine gültige Vertretung wählen.', 422); return $r; }
        $l = hr_vertretung_luecken(['von' => $von, 'bis' => $bis], $ich, $vp, $eintraege, true);
        $n = hr_name($vp);
        if ($l['abwesend']) {
            $text = "Ihre Vertretung $n ist in dieser Zeit selbst abwesend (" . hr_daten_text($l['abwesend']) . ') – bitte wählen Sie eine andere Vertretung.';
            $r['vertretung'] = ['id' => $vp['id'], 'name' => $n, 'status' => 'abwesend', 'text' => $text];
            $f($text, 409);
        } elseif ($l['frei']) {
            $text = "Ihre Vertretung $n arbeitet an diesen Tagen nicht (" . hr_daten_text($l['frei']) . ') – bitte mit der Personalstelle klären.';
            $r['vertretung'] = ['id' => $vp['id'], 'name' => $n, 'status' => 'frei', 'text' => $text];
            $r['hinweise'][] = $text;
        } else $r['vertretung'] = ['id' => $vp['id'], 'name' => $n, 'status' => 'da', 'text' => "$n ist in dieser Zeit da."];
    } elseif ($art === 'U' && !$nurSchliess && hr_planung_einst()['vertretungPflicht']) $f('Bitte wählen Sie eine Vertretung für die Zeit Ihres Urlaubs aus.', 422);
    return $r;
}

/* Zeiträume aus der Anfrage (Vorplanung und Vorschau): [{von, bis, vertretung}] – höchstens HR_VORPLANUNG_MAX */
function hr_zeitraeume_anfrage($l): array
{
    if (!is_array($l) || !array_is_list($l) || !$l) throw new InvalidArgumentException('Bitte mindestens einen Zeitraum angeben.');
    if (count($l) > HR_VORPLANUNG_MAX) throw new InvalidArgumentException('Höchstens ' . HR_VORPLANUNG_MAX . ' Zeiträume auf einmal.');
    $out = [];
    foreach ($l as $i => $x) {
        if (!is_array($x)) throw new InvalidArgumentException('Zeitraum ' . ($i + 1) . ': ungültige Angaben.');
        try { [$von, $bis] = hr_zeitraum_pruefen($x); } catch (InvalidArgumentException $ex) { throw new InvalidArgumentException('Zeitraum ' . ($i + 1) . ': ' . $ex->getMessage()); }
        $v = $x['vertretung'] ?? null;
        $out[] = ['von' => $von, 'bis' => $bis, 'vertretung' => is_string($v) && $v !== '' ? $v : null];
    }
    return $out;
}

/* Vorplanung prüfen (ohne zu speichern): jeder Zeitraum wie ein Antrag (hr_antrag_zeitraum), nur im Vorplanungsjahr.
   Rückgabe [zeiträume[], gültige Zeiträume[]] */
function hr_vorplanung_pruefen(array $ich, array $personal, array $eintraege, array $einst, array $zr, int $jahr): array
{
    $erg = []; $gut = [];
    foreach ($zr as $i => $z) {
        $andere = array_slice($zr, 0, $i);   // nur frühere Zeilen: die erste bleibt gültig, die überschneidende wird markiert
        $e = hr_antrag_zeitraum($ich, $personal, $eintraege, $einst, 'U', $z['von'], $z['bis'], $z['vertretung'], $andere);
        if (substr($z['von'], 0, 4) !== (string)$jahr || substr($z['bis'], 0, 4) !== (string)$jahr) { $e['fehler'] = "Die Vorplanung gilt für $jahr – bitte nur Tage in $jahr."; $e['code'] = 422; }
        $erg[] = $e;
        if ($e['fehler'] === null) $gut[] = $z;
    }
    return [$erg, $gut];
}

/* Daten als kurze Zeiträume (aufeinanderfolgende Kalendertage zusammengefasst, höchstens vier, dann „…“) */
function hr_daten_text(array $daten): string
{
    $r = [];
    foreach ($daten as $d) { $n = count($r); if ($n && hr_plus($r[$n - 1][1], 1) === $d) $r[$n - 1][1] = $d; else $r[] = [$d, $d]; }
    return implode(', ', array_map(function ($x) { return hr_zeitraum_text($x[0], $x[1]); }, array_slice($r, 0, 4))) . (count($r) > 4 ? ', …' : '');
}

/* Konflikte eines Urlaubsantrags in der Jahresplanung. Nur Namen und Zeiträume, nie Gründe anderer Abwesenheiten.
   Arten: vertretung (fehlt, nicht im Urlaubsplan, selbst abwesend), abteilung (gleichzeitig weg – nicht an Schließtagen),
   sperre, rest, einzeltage ($einzel: Einzeltage der Vorplanung der Person, hr_einzeltage – mehr als einzeltageMax) */
function hr_planung_konflikte(array $e, array $p, array $idx, array $eintraege, array $sperren, array $pe, float $verfuegbar, array $einzel = []): array
{
    $k = [];
    $v = $e['vertretung'] ?? null;
    if (!$v) {
        // fehlende Vertretung zählt nur bei offenen Anträgen (Einträge der Personalstelle haben keine Vertretung) und nicht,
        // wenn der Antrag nur Schließtage (24.12./31.12.) enthält – der Betrieb ist dann geschlossen
        $tg = hr_tage($p, $e['von'], $e['bis']);
        $nurSchliess = $tg && !array_filter($tg, function ($d) { return hr_schliesstag($d) === null; });
        if ($pe['vertretungPflicht'] && $e['status'] === 'beantragt' && !$nurSchliess) $k[] = ['art' => 'vertretung', 'text' => 'Keine Vertretung angegeben'];
    } else {
        $vp = $idx[$v] ?? null;
        if (!$vp || !$vp['aktiv']) $k[] = ['art' => 'vertretung', 'text' => 'Vertretung nicht mehr im Urlaubsplan'];
        else {
            $l = hr_vertretung_luecken($e, $p, $vp, $eintraege);
            if ($l['abwesend']) $k[] = ['art' => 'vertretung', 'text' => 'Vertretung ' . hr_name($vp) . ' ist selbst abwesend (' . hr_daten_text($l['abwesend']) . ')'];
            if ($l['frei']) $k[] = ['art' => 'vertretung', 'text' => 'Vertretung ' . hr_name($vp) . ' arbeitet an diesen Tagen nicht (' . hr_daten_text($l['frei']) . ')'];
        }
    }
    if (trim((string)$p['abteilung']) !== '') foreach ($eintraege as $o) {
        if ($o['id'] === $e['id'] || $o['person'] === $e['person'] || $o['person'] === $v || $o['art'] === 'X' || !in_array($o['status'], HR_AKTIV, true) || !hr_planung_schnitt($o, $e)) continue;
        $op = $idx[$o['person']] ?? null;
        $gem = hr_schnitt_ohne_schliesstage($o, $e);   // nur am 24.12./31.12. zusammen weg: Betrieb ohnehin geschlossen
        if ($op && $op['aktiv'] && $op['abteilung'] === $p['abteilung'] && $gem) $k[] = ['art' => 'abteilung', 'text' => 'Gleichzeitig weg: ' . hr_name($op) . ' (' . hr_zeitraum_text($gem[0], $gem[count($gem) - 1]) . ')'];
    }
    if ($s = hr_ueberschneidung($sperren, $e['von'], $e['bis'])) $k[] = ['art' => 'sperre', 'text' => 'Urlaubssperre ' . hr_zeitraum_text($s['von'], $s['bis']) . ($s['text'] !== '' ? ' (' . $s['text'] . ')' : '')];
    if ($e['status'] === 'beantragt' && $verfuegbar < 0) $k[] = ['art' => 'rest', 'text' => 'Mehr als der Resturlaub (um ' . hr_tage_text(-$verfuegbar) . ')'];
    $max = $pe['einzeltageMax'];
    if ($max > 0 && count($einzel) > $max && array_intersect($einzel, hr_tage($p, $e['von'], $e['bis'])))
        $k[] = ['art' => 'einzeltage', 'text' => 'Einzelner Urlaubstag – in der Vorplanung ' . count($einzel) . ' einzelne Tage (höchstens ' . $max . ', übriger Urlaub möglichst zusammenhängend)'];
    return $k;
}

/* Zusammenfassung eines Jahres für die Personalstelle und „Urlaub genehmigen“: Mitarbeiter im Urlaubsplan mit Stand,
   alle Urlaubsanträge des Jahres (beantragt, genehmigt) mit Vertretung und Konflikten, Sperren, Zahlen, Abschluss.
   „frei“ = beantragt, ohne Konflikt und nicht der eigene – gesammelt genehmigbar (hr_planung_freigeben). */
function hr_planung(int $jahr, array $me): array
{
    $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen(); $pe = hr_planung_einst();
    $idx = hr_personen_index($personal);
    $eintraege = $abw['eintraege'];
    $jv = "$jahr-01-01"; $jb = "$jahr-12-31";
    $sperren = array_values(array_filter($einst['sperren'], function ($s) use ($jv, $jb) { return $s['bis'] >= $jv && $s['von'] <= $jb; }));
    $nutzer = [];
    foreach (users_load() as $u) $nutzer[(string)$u['id']] = hr_mail_adresse($u['email'] ?? '') !== '';
    $personen = []; $verf = [];
    foreach (hr_nach_abteilung(array_values(array_filter($personal['personen'], function ($p) { return $p['aktiv']; }))) as $p) {
        $verf[$p['id']] = (float)hr_konto($p, $eintraege, $jahr)['verfuegbar'];
        $personen[$p['id']] = ['id' => $p['id'], 'name' => hr_name($p), 'abteilung' => $p['abteilung'], 'adresse' => $p['nutzer'] !== null && ($nutzer[$p['nutzer']] ?? false),
                               'konflikte' => 0] + hr_planung_person($p, $eintraege, $jahr, $pe);
    }
    $antraege = []; $freiJe = [];
    foreach ($eintraege as $e) {
        if ($e['art'] !== 'U' || !in_array($e['status'], HR_AKTIV, true) || $e['bis'] < $jv || $e['von'] > $jb || !isset($personen[$e['person']])) continue;
        $p = $idx[$e['person']];
        $kon = hr_planung_konflikte($e, $p, $idx, $eintraege, $einst['sperren'], $pe, $verf[$p['id']], $personen[$p['id']]['einzeltage']);
        $eigen = hr_eigen($personal, $me, $e);
        if ($kon) $personen[$p['id']]['konflikte']++;
        $vp = ($e['vertretung'] ?? null) ? ($idx[$e['vertretung']] ?? null) : null;
        $antraege[] = ['id' => $e['id'], 'person' => $p['id'], 'name' => hr_name($p), 'abteilung' => $p['abteilung'], 'von' => $e['von'], 'bis' => $e['bis'],
                       'tage' => hr_tage_summe(hr_tage($p, $e['von'], $e['bis'], $jv, $jb, $freiJe[$p['id']] ??= hr_freie_tage($eintraege, $p['id']))),
                       'status' => $e['status'], 'vertretung' => $vp ? hr_name($vp) : null, 'notiz' => (string)($e['notiz'] ?? ''),
                       'eigen' => $eigen, 'konflikte' => $kon, 'frei' => $e['status'] === 'beantragt' && !$kon && !$eigen];
    }
    usort($antraege, function ($a, $b) { return [$a['von'], $a['name']] <=> [$b['von'], $b['name']]; });
    $dt = hr_planung_daten($pe, $jahr);
    $pl = array_values($personen);
    $abschluss = $pe['abschluss'][(string)$jahr] ?? null;
    $mail = hr_mail_einst();
    return ['jahr' => $jahr, 'heute' => hr_heute(), 'start' => $dt['start'], 'stichtag' => $dt['stichtag'], 'prozent' => $pe['prozent'],
            'testmodus' => $mail['test']['an'], 'postfach' => (bool)mail_cfg_intern(),
            'vertretungPflicht' => $pe['vertretungPflicht'], 'einzeltageMax' => $pe['einzeltageMax'], 'schliesstage' => (object)hr_schliesstage($jahr),
            'abschluss' => $abschluss ? ['t' => $abschluss['t'] ?? null, 'by' => (string)($abschluss['by'] ?? '')] : null,
            'personen' => $pl, 'antraege' => $antraege, 'sperren' => $sperren,
            // „Ziel erreicht x von y“ zählt nur Mitarbeiter mit Anspruch im Jahr (ohne Anspruch gibt es nichts zu planen)
            'zahlen' => ['personen' => count(array_filter($pl, function ($p) { return $p['anspruch'] > 0; })),
                         'erreicht' => count(array_filter($pl, function ($p) { return $p['erreicht'] && $p['anspruch'] > 0; })),
                         'erinnern' => count(array_filter($pl, function ($p) { return !$p['erreicht'] && $p['adresse']; })),
                         'offen' => count(array_filter($antraege, function ($a) { return $a['status'] === 'beantragt'; })),
                         'frei' => count(array_filter($antraege, function ($a) { return $a['frei']; })),
                         'konflikte' => count(array_filter($antraege, function ($a) { return (bool)$a['konflikte']; }))]];
}

/* Konfliktfreie Anträge gesammelt genehmigen (unter der Sperre hr-abwesenheiten): jeder Antrag wird neu geprüft; eigene,
   bereits entschiedene und solche mit Konflikt bleiben offen. Rückgabe [genehmigt[], übersprungen[{id, grund}]] */
function hr_planung_freigeben(int $jahr, array $ids, array $me): array
{
    return with_lock('hr-abwesenheiten', function () use ($jahr, $ids, $me) {
        $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen(); $pe = hr_planung_einst();
        $idx = hr_personen_index($personal);
        $sperren = $einst['sperren'];
        $ok = []; $weg = [];
        $gewuenscht = array_flip($ids);
        foreach ($abw['eintraege'] as $i => $e) {
            if (!isset($gewuenscht[$e['id']])) continue;
            unset($gewuenscht[$e['id']]);
            $p = $idx[$e['person']] ?? null;
            if ($e['art'] !== 'U' || $e['status'] !== 'beantragt' || $e['bis'] < "$jahr-01-01" || $e['von'] > "$jahr-12-31" || !$p || !$p['aktiv']) { $weg[] = ['id' => $e['id'], 'grund' => 'nicht offen']; continue; }
            if (hr_eigen($personal, $me, $e)) { $weg[] = ['id' => $e['id'], 'grund' => 'eigener Antrag']; continue; }
            $verf = (float)hr_konto($p, $abw['eintraege'], $jahr)['verfuegbar'];   // wie in der Ansicht (hr_planung): Konto des Planungsjahres
            $einzel = hr_einzeltage($p, $abw['eintraege'], $jahr, $pe);
            if (hr_planung_konflikte($e, $p, $idx, $abw['eintraege'], $sperren, $pe, $verf, $einzel)) { $weg[] = ['id' => $e['id'], 'grund' => 'Konflikt']; continue; }
            $abw['eintraege'][$i]['status'] = 'genehmigt';
            $abw['eintraege'][$i]['entscheidung'] = ['t' => now(), 'by' => $me['name'], 'grund' => 'Jahresplanung ' . $jahr];
            $ok[] = $e['id'];
        }
        foreach (array_keys($gewuenscht) as $id) $weg[] = ['id' => $id, 'grund' => 'nicht gefunden'];
        if ($ok) hr_abwesenheiten_schreiben($abw);
        return [$ok, $weg];
    });
}

/* ---------------- E-Mails der Jahresplanung (Aufbau wie die übrigen HR-Mails, module/hr/mail.php) ---------------- */

/* Zeilen [Zeitraum (+ beantragt), Tage, –, Vertretung] eines Jahres für hr_mail_tabelle */
function hr_planung_mail_zeilen(array $p, array $eintraege, int $jahr, array $idx): array
{
    $frei = hr_freie_tage($eintraege, $p['id']);
    $z = [];
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id'] || $e['art'] !== 'U' || !in_array($e['status'], HR_AKTIV, true) || $e['bis'] < "$jahr-01-01" || $e['von'] > "$jahr-12-31") continue;
        $n = hr_tage_summe(hr_tage($p, $e['von'], $e['bis'], "$jahr-01-01", "$jahr-12-31", $frei));
        if (!$n) continue;
        $vp = ($e['vertretung'] ?? null) ? ($idx[$e['vertretung']] ?? null) : null;
        $z[] = [$e['von'], hr_zeitraum_text($e['von'], $e['bis']) . ($e['status'] === 'beantragt' ? ' (beantragt)' : ''), hr_tage_text((float)$n), false,
                'Vertretung: ' . ($vp ? hr_name($vp) : '–')];
    }
    usort($z, function ($a, $b) { return $a[0] <=> $b[0]; });
    return array_map(function ($x) { return array_slice($x, 1); }, $z);
}

/* Erinnerung „Bitte planen Sie Ihren Urlaub“ */
function hr_planung_erinnerung_inhalt(array $p, array $eintraege, int $jahr, array $pe, array $idx): array
{
    $st = hr_planung_person($p, $eintraege, $jahr, $pe);
    $dt = hr_planung_daten($pe, $jahr);
    $vor = hr_mail_vorname($p);
    $betreff = hr_heute() > $dt['stichtag'] ? "Bitte planen Sie Ihren Urlaub $jahr jetzt" : "Bitte planen Sie Ihren Urlaub $jahr bis zum " . hr_de($dt['stichtag']);
    $vorbei = hr_heute() > $dt['stichtag'];
    $satz = ($vorbei ? 'der Stichtag ' . hr_de($dt['stichtag']) . " ist vorbei – bitte planen Sie jetzt mindestens {$pe['prozent']} % Ihres Urlaubs $jahr"
                     : 'bitte planen Sie bis zum ' . hr_de($dt['stichtag']) . " mindestens {$pe['prozent']} % Ihres Urlaubs $jahr")
        . ' – das sind ' . hr_tage_text($st['ziel']) . ' von ' . hr_tage_text($st['anspruch']) . '.';
    $box = 'Bisher geplant: ' . hr_tage_text($st['geplant']) . ' – es fehlen noch ' . hr_tage_text($st['fehlt']) . '.';
    $wie = 'Stellen Sie dazu im Urlaubsportal Urlaubsanträge für ' . $jahr . ($pe['vertretungPflicht'] ? ' und wählen Sie für jeden Zeitraum eine Vertretung aus' : '')
        . '. Die Personalstelle prüft die Planung und gibt sie frei.';
    $zeilen = hr_planung_mail_zeilen($p, $eintraege, $jahr, $idx);
    [$lt, $lh] = hr_mail_knopf();
    $text = "Hallo $vor,\n\n$satz\n$box\n$wie" . ($zeilen ? "\n\nIhr Urlaub $jahr bisher\n" . hr_mail_tabelle_text(array_map(function ($z) { return [$z[0] . ' – ' . $z[3], $z[1]]; }, $zeilen)) : '') . $lt;
    $html = '<p style="margin:0 0 6px;">Hallo ' . mail_h($vor) . ',</p><p style="margin:0;">' . mail_h($satz) . '</p>' . hr_mail_box($box)
        . '<p style="margin:12px 0 0;">' . mail_h($wie) . '</p>'
        . ($zeilen ? hr_mail_h2("Ihr Urlaub $jahr bisher") . hr_mail_tabelle($zeilen) : '') . $lh;
    return hr_mail_rahmen($betreff, $text, $html, "Ihre Urlaubsplanung $jahr");
}

/* Jahresübersicht nach dem Abschluss der Planung */
function hr_planung_uebersicht_inhalt(array $p, array $eintraege, int $jahr, array $idx): array
{
    $k = hr_konto($p, $eintraege, $jahr);
    $zeilen = hr_planung_mail_zeilen($p, $eintraege, $jahr, $idx);
    $jm = hr_mail_jahr_monate($p, $eintraege, $jahr, "$jahr-01-01");   // alles noch geplant
    $vor = hr_mail_vorname($p);
    $betreff = "Ihre Urlaubsplanung $jahr";
    $satz = "die Urlaubsplanung für $jahr ist abgeschlossen. Hier ist Ihre Jahresübersicht – bitte prüfen Sie sie und melden Sie sich bei der Personalstelle, wenn etwas nicht stimmt.";
    $konto = [['Anspruch ' . $jahr, hr_tage_text((float)$k['anspruch'])]];
    if ($k['uebertrag'] != 0) $konto[] = ['Übertrag aus ' . ($jahr - 1) . ' (voraussichtlich)', hr_tage_text((float)$k['uebertrag'])];
    $konto[] = ['Geplant (genehmigt)', hr_tage_text((float)$k['geplant'] + (float)$k['genommen'])];
    if ($k['beantragt']) $konto[] = ['Beantragt (noch nicht genehmigt)', hr_tage_text((float)$k['beantragt'])];
    $konto[] = ['Noch nicht verplant', hr_tage_text((float)$k['verfuegbar']), true];
    [$lt, $lh] = hr_mail_knopf();
    $text = "Hallo $vor,\n\n$satz\n\nIhr Urlaub $jahr\n" . ($zeilen ? hr_mail_tabelle_text(array_map(function ($z) { return [$z[0] . ' – ' . $z[3], $z[1]]; }, $zeilen)) : '  noch kein Urlaub eingetragen')
        . "\n\nUrlaubskonto $jahr\n" . hr_mail_tabelle_text($konto) . "\n\nIhr Jahr $jahr auf einen Blick\n" . hr_mail_jahr_text($jm) . $lt;
    $html = '<p style="margin:0 0 6px;">Hallo ' . mail_h($vor) . ',</p><p style="margin:0;">' . mail_h($satz) . '</p>'
        . hr_mail_h2("Ihr Urlaub $jahr") . ($zeilen ? hr_mail_tabelle($zeilen) : '<p style="margin:0;color:#4a443e;">Noch kein Urlaub eingetragen.</p>')
        . hr_mail_h2("Urlaubskonto $jahr") . hr_mail_tabelle($konto)
        . hr_mail_h2("Ihr Jahr $jahr auf einen Blick") . hr_mail_jahr_html($jm) . $lh;
    return hr_mail_rahmen($betreff, $text, $html, "Ihre Urlaubsplanung $jahr");
}

/* Empfänger: Mitarbeiter im Urlaubsplan mit E-Mail-Adresse; $nurOffen: nur wer das Ziel noch nicht erreicht hat;
   $person: nur diese Person. Rückgabe [[Person, Adresse]…, Anzahl ohne Adresse] */
function hr_planung_empfaenger(int $jahr, bool $nurOffen, ?string $person = null): array
{
    $abw = hr_abwesenheiten()['eintraege']; $pe = hr_planung_einst();
    $adr = [];
    foreach (users_load() as $u) $adr[(string)$u['id']] = hr_mail_adresse($u['email'] ?? '');
    $mit = []; $ohne = 0;
    foreach (hr_personal()['personen'] as $p) {
        if (!$p['aktiv'] || ($person !== null && $p['id'] !== $person) || hr_anspruch($p, $jahr) <= 0) continue;   // ohne Anspruch keine Planung
        if ($nurOffen && hr_planung_person($p, $abw, $jahr, $pe)['erreicht']) continue;
        $a = $p['nutzer'] !== null ? ($adr[$p['nutzer']] ?? '') : '';
        if ($a === '') $ohne++; else $mit[] = [$p, $a];
    }
    return [$mit, $ohne];
}
/* Versand: art „planung“ (Erinnerung) oder „jahresuebersicht“ */
function hr_planung_senden(string $art, int $jahr, array $me, ?string $person = null): array
{
    [$mit, $ohne] = hr_planung_empfaenger($jahr, $art === 'planung', $person);
    if (!$mit) throw new RuntimeException($art === 'planung' ? 'Alle Mitarbeiter mit E-Mail-Adresse haben ihr Ziel schon erreicht.' : 'Kein Mitarbeiter mit E-Mail-Adresse.');
    $abw = hr_abwesenheiten()['eintraege']; $idx = hr_personen_index(hr_personal()); $pe = hr_planung_einst(); $m = hr_mail_einst();
    $jobs = [];
    foreach ($mit as [$p, $an]) {
        [$betreff, $text, $html] = $art === 'planung' ? hr_planung_erinnerung_inhalt($p, $abw, $jahr, $pe, $idx) : hr_planung_uebersicht_inhalt($p, $abw, $jahr, $idx);
        [$to, $name, $betreff] = hr_mail_ziel($m, $an, hr_name($p), $betreff);
        $jobs[] = ['to' => $to, 'name' => $name, 'subject' => $betreff, 'text' => $text, 'html' => $html];
    }
    return hr_mail_versenden($jobs, $art, 'manuell', $me, ['jahr' => $jahr, 'ohneAdresse' => $ohne, 'test' => $m['test']['an']]);
}

/* Abschluss setzen oder aufheben – geprüft und geschrieben unter der Sperre hr-einstellungen (zwei gleichzeitige Klicks
   schließen nur einmal ab, die Jahresübersicht geht nur einmal). Rückgabe: false, wenn der Zustand schon so war. */
function hr_planung_abschluss_setzen(int $jahr, bool $zu, array $me): bool
{
    return with_lock('hr-einstellungen', function () use ($jahr, $zu, $me) {
        $d = store_read('hr-einstellungen') ?? [];
        $pl = is_array($d['planung'] ?? null) ? $d['planung'] : [];
        $ab = is_array($pl['abschluss'] ?? null) ? $pl['abschluss'] : [];
        if (isset($ab[(string)$jahr]) === $zu) return false;
        if ($zu) $ab[(string)$jahr] = ['t' => now(), 'by' => (string)$me['name'], 'byId' => (string)$me['id']];
        else unset($ab[(string)$jahr]);
        $pl['abschluss'] = (object)$ab;
        $d['planung'] = $pl;
        $d['rev'] = (int)($d['rev'] ?? 0) + 1;
        store_write('hr-einstellungen', $d);
        return true;
    });
}
