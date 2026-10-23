<?php
declare(strict_types=1);
/* Modul HR · Übernahme der bisherigen Planungsdatei („Urlaub 2026.xlsx“, ein Blatt je Monat).
   Der Browser liest die Excel-Datei (OfferCore.xlsxReadWorkbook) und sendet die Zellen der Monatsblätter; hier prüft der
   Server, zeigt eine Vorschau und übernimmt Mitarbeiter (Name, Abteilung, Reihenfolge) und Einträge U/K/G sowie freie
   Tage („x“). Erneute Übernahme ersetzt die zuvor übernommenen Einträge desselben Jahres; Anträge und Eintragungen der
   Personalstelle bleiben unverändert (überschneidende Tage aus der Datei werden dann nicht übernommen).
   Form von Vorschau/Übernahme wie im Importvertrag der Plattform (docs/plattform/schnittstellen/import.md), damit die
   Importart später in die Importzentrale aufgenommen werden kann. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const HR_IMPORT_MONATE = ['jan' => 1, 'feb' => 2, 'mär' => 3, 'mrz' => 3, 'mar' => 3, 'apr' => 4, 'mai' => 5, 'jun' => 6, 'jul' => 7, 'aug' => 8,
    'sep' => 9, 'okt' => 10, 'nov' => 11, 'dez' => 12];

function hr_namekey(string $n): string { return mb_strtolower(trim(preg_replace('/\s+/u', ' ', $n) ?? '')); }

/* Monat und Jahr eines Blatts: Datum in K2 (Excel-Seriennummer), sonst aus dem Blattnamen („Okt. '26“, „Januar ´26“) */
function hr_import_monat(array $blatt): ?array
{
    $grid = $blatt['grid'];
    foreach ([[1, 10], [1, 9], [1, 11]] as [$r, $c]) {
        $v = $grid[$r][$c] ?? null;
        if (is_int($v) || is_float($v)) {
            if ($v > 36000 && $v < 80000) { $t = (int)round(($v - 25569) * 86400); return [(int)gmdate('Y', $t), (int)gmdate('n', $t)]; }
        }
    }
    $name = mb_strtolower((string)$blatt['name']);
    $mon = null;
    foreach (HR_IMPORT_MONATE as $k => $m) if (mb_strpos($name, $k) === 0) { $mon = $m; break; }
    if ($mon === null) return null;
    if (preg_match('/(20\d\d)/', $name, $x)) return [(int)$x[1], $mon];
    if (preg_match('/[\'´`’](\d\d)\b/u', $name, $x)) return [2000 + (int)$x[1], $mon];
    return [0, $mon];
}

/* Datei lesen: Mitarbeiter (in Reihenfolge) und Kürzel je Datum */
function hr_import_lesen(array $e): array
{
    $sheets = $e['daten']['blaetter'] ?? null;
    if (!is_array($sheets) || !array_is_list($sheets) || !$sheets || count($sheets) > 24) throw new InvalidArgumentException('Die Datei enthält keine lesbaren Monatsblätter.');
    $jahrOpt = (int)($e['optionen']['jahr'] ?? 0);
    $personen = []; $marken = []; $fehler = []; $jahre = []; $monate = []; $unbekannt = [];
    foreach ($sheets as $b) {
        if (!is_array($b) || !is_string($b['name'] ?? null) || !is_array($b['grid'] ?? null) || count($b['grid']) > 300) throw new InvalidArgumentException('Ungültige Datei.');
        $b['name'] = mb_substr($b['name'], 0, 40);
        $mj = hr_import_monat($b);
        if ($mj === null) { $fehler[] = ['schluessel' => $b['name'], 'text' => 'Blatt übersprungen: Monat nicht erkannt.']; continue; }
        [$jahr, $mon] = $mj;
        if ($jahr === 0) $jahr = $jahrOpt;
        if ($jahr < 2000 || $jahr > 2100) { $fehler[] = ['schluessel' => $b['name'], 'text' => 'Blatt übersprungen: Jahr nicht erkannt.']; continue; }
        // Kopfzeile mit „Pos.“ in Spalte A, Tageszahlen ab Spalte D
        $kopf = null;
        foreach ($b['grid'] as $r => $zeile) if (is_array($zeile) && mb_strtolower(trim((string)($zeile[0] ?? ''))) === 'pos.') { $kopf = $r; break; }
        if ($kopf === null) { $fehler[] = ['schluessel' => $b['name'], 'text' => 'Blatt übersprungen: Kopfzeile „Pos.“ fehlt.']; continue; }
        $tagSp = [];
        $tmax = (int)gmdate('t', (int)gmmktime(0, 0, 0, $mon, 1, $jahr));
        foreach ((array)$b['grid'][$kopf] as $c => $v) if ($c >= 3 && (is_int($v) || is_float($v)) && (int)$v >= 1 && (int)$v <= $tmax && (int)$v == $v) $tagSp[$c] = (int)$v;
        if (!$tagSp) { $fehler[] = ['schluessel' => $b['name'], 'text' => 'Blatt übersprungen: keine Tageszahlen gefunden.']; continue; }
        $jahre[$jahr] = true; $monate[] = $mon;
        $abt = '';
        for ($r = $kopf + 1; $r < count($b['grid']); $r++) {
            $zeile = (array)($b['grid'][$r] ?? []);
            $name = s($zeile[2] ?? '', 80) ?? '';
            if (trim((string)($zeile[1] ?? '')) !== '') $abt = s($zeile[1], 40) ?? '';
            if ($name === '' || mb_strtolower($name) === 'summe') { if (mb_strtolower($name) === 'summe') break; continue; }
            $k = hr_namekey($name);
            $pos = is_numeric($zeile[0] ?? null) ? (int)$zeile[0] : count($personen) + 1;
            // Abteilung und Reihenfolge aus dem jüngsten Monat der Datei
            if (!isset($personen[$k]) || $personen[$k]['monat'] <= $jahr * 100 + $mon) $personen[$k] = ['name' => $name, 'abteilung' => $abt, 'pos' => $pos, 'monat' => $jahr * 100 + $mon];
            foreach ($tagSp as $c => $t) {
                $v = trim((string)($zeile[$c] ?? ''));
                if ($v === '' || is_float($zeile[$c] ?? null) || is_int($zeile[$c] ?? null)) continue;
                $d = sprintf('%04d-%02d-%02d', $jahr, $mon, $t);
                $code = $v === 'x' || $v === 'X' ? 'X' : (strtoupper($v) === 'GT' ? 'G' : strtoupper($v));   // „GT“ = Gleittag
                if (!in_array($code, ['U', 'K', 'G', 'X'], true)) { $unbekannt[$v] = ($unbekannt[$v] ?? 0) + 1; continue; }
                $marken[$k][$d] = $code;
            }
        }
    }
    if (count($jahre) > 1) throw new InvalidArgumentException('Die Datei enthält Monate aus mehreren Jahren (' . implode(', ', array_keys($jahre)) . '). Bitte je Jahr eine Datei übernehmen.');
    if (!$jahre) throw new InvalidArgumentException('In der Datei wurde kein Monatsblatt im Aufbau der Urlaubsplanung gefunden (Kopfzeile „Pos.“, Tageszahlen ab Spalte D).');
    return ['jahr' => (int)array_key_first($jahre), 'monate' => array_values(array_unique($monate)), 'personen' => $personen, 'marken' => $marken,
            'fehler' => $fehler, 'unbekannt' => $unbekannt];
}

/* Kürzel zu Zeiträumen zusammenfassen: aufeinanderfolgende Arbeitstage (Mo–Fr ohne Feiertage) mit gleichem Kürzel */
function hr_import_zeitraeume(array $tage): array
{
    ksort($tage);
    $out = []; $lauf = null;
    foreach ($tage as $d => $code) {
        if ($lauf && $lauf['art'] === $code) {
            $dazwischen = true;
            for ($x = hr_plus($lauf['bis'], 1); $x < $d; $x = hr_plus($x, 1)) if (hr_wochentag($x) <= 5 && hr_feiertag($x) === null) { $dazwischen = false; break; }
            if ($dazwischen) { $lauf['bis'] = $d; continue; }
        }
        if ($lauf) $out[] = $lauf;
        $lauf = ['art' => $code, 'von' => $d, 'bis' => $d];
    }
    if ($lauf) $out[] = $lauf;
    return $out;
}

/* Plan der Übernahme (ohne zu speichern) */
function hr_import_planen(array $e): array
{
    $l = hr_import_lesen($e);
    $personal = hr_personal(); $abw = hr_abwesenheiten();
    $nachName = [];
    foreach ($personal['personen'] as $p) $nachName[hr_namekey(hr_name($p))] = $p;
    $neuP = []; $aendP = []; $zuordnung = [];
    foreach ($l['personen'] as $k => $x) {
        if (isset($nachName[$k])) {
            $p = $nachName[$k];
            if ($p['abteilung'] !== $x['abteilung'] || $p['pos'] !== $x['pos']) $aendP[$p['id']] = ['abteilung' => $x['abteilung'], 'pos' => $x['pos']];
            $zuordnung[$k] = $p['id'];
            continue;
        }
        $teile = explode(' ', $x['name']);
        $nach = count($teile) > 1 ? array_pop($teile) : '';
        $p = hr_person_norm(['id' => hr_neue_id('p'), 'vorname' => implode(' ', $teile), 'nachname' => $nach, 'abteilung' => $x['abteilung'], 'pos' => $x['pos'],
                             'arbeitstage' => [1, 2, 3, 4, 5], 'aktiv' => true, 'jahre' => []]);
        $neuP[$p['id']] = $p; $zuordnung[$k] = $p['id'];
    }
    $jahr = $l['jahr'];
    // bisher übernommene Einträge dieses Jahres werden ersetzt
    $alt = array_values(array_filter($abw['eintraege'], function ($x) use ($jahr) { return ($x['quelle'] ?? '') === 'import' && (int)substr($x['von'], 0, 4) === $jahr; }));
    $altIds = array_column($alt, 'id');
    $bleibt = array_values(array_filter($abw['eintraege'], function ($x) use ($altIds) { return !in_array($x['id'], $altIds, true); }));
    $neuE = []; $konflikte = [];
    foreach ($l['marken'] as $k => $tage) {
        $pid = $zuordnung[$k];
        foreach (hr_import_zeitraeume($tage) as $z) {
            $kol = hr_kollision($bleibt, $pid, $z['von'], $z['bis']);
            if ($kol) { $konflikte[] = [$l['personen'][$k]['name'], $z, $kol]; continue; }
            $neuE[] = ['id' => hr_neue_id('a'), 'person' => $pid, 'art' => $z['art'], 'von' => $z['von'], 'bis' => $z['bis'], 'status' => 'genehmigt',
                       'notiz' => '', 'quelle' => 'import'];
        }
    }
    return ['lesen' => $l, 'neuP' => $neuP, 'aendP' => $aendP, 'alt' => $alt, 'bleibt' => $bleibt, 'neuE' => $neuE, 'konflikte' => $konflikte,
            'stand' => hr_import_stand($personal, $abw)];
}
function hr_import_stand(array $personal, array $abw): string { return $personal['rev'] . '-' . $abw['rev']; }

function hr_import_vorschau(array $e, array $me): array
{
    $pl = hr_import_planen($e);
    $l = $pl['lesen'];
    $n = ['neu' => 0, 'geaendert' => 0, 'entfaellt' => 0, 'unveraendert' => 0, 'fehler' => 0];
    $z = [];
    foreach ($pl['neuP'] as $p) { $n['neu']++; $z[] = ['art' => 'neu', 'schluessel' => 'Mitarbeiter', 'name' => hr_name($p), 'text' => 'neu angelegt' . ($p['abteilung'] !== '' ? ' (' . $p['abteilung'] . ')' : '')]; }
    $alle = hr_personen_index(hr_personal()) + $pl['neuP'];
    foreach ($pl['aendP'] as $id => $x) { $n['geaendert']++; $z[] = ['art' => 'geaendert', 'schluessel' => 'Mitarbeiter', 'name' => hr_name($alle[$id]), 'text' => 'Abteilung/Reihenfolge: ' . $x['abteilung'] . ', Position ' . $x['pos']]; }
    $proPerson = [];
    foreach ($pl['neuE'] as $x) { $proPerson[$x['person']][$x['art']] = ($proPerson[$x['person']][$x['art']] ?? 0) + count(hr_tage(['arbeitstage' => [1, 2, 3, 4, 5]], $x['von'], $x['bis'])); }
    foreach ($proPerson as $pid => $arten) {
        $n['neu']++;
        $teile = [];
        foreach (['U' => 'Urlaub', 'K' => 'Krank', 'G' => 'Gleittag', 'X' => 'freie Tage'] as $k => $t) if (!empty($arten[$k])) $teile[] = "$t {$arten[$k]}";
        $z[] = ['art' => 'neu', 'schluessel' => 'Einträge ' . $l['jahr'], 'name' => hr_name($alle[$pid]), 'text' => implode(' · ', $teile) . ' Tage'];
    }
    if ($pl['alt']) { $n['entfaellt'] += count($pl['alt']); $z[] = ['art' => 'entfaellt', 'schluessel' => 'Einträge ' . $l['jahr'], 'name' => 'frühere Übernahme', 'text' => count($pl['alt']) . ' Einträge der letzten Übernahme werden ersetzt']; }
    foreach ($pl['konflikte'] as [$name, $zr, $kol]) {
        $n['fehler']++;
        $z[] = ['art' => 'fehler', 'schluessel' => $zr['art'] . ' ' . hr_zeitraum_text($zr['von'], $zr['bis']), 'name' => $name,
                'text' => 'nicht übernommen: überschneidet sich mit einem Eintrag im System (' . hr_zeitraum_text($kol['von'], $kol['bis']) . ')'];
    }
    foreach ($l['fehler'] as $f) { $n['fehler']++; $z[] = ['art' => 'fehler', 'schluessel' => $f['schluessel'], 'name' => '', 'text' => $f['text']]; }
    $h = [['stufe' => 'info', 'text' => 'Jahr ' . $l['jahr'] . ', ' . count($l['monate']) . ' Monatsblätter, ' . count($l['personen']) . ' Mitarbeiter.']];
    if ($l['unbekannt']) $h[] = ['stufe' => 'warn', 'text' => 'Nicht übernommen (unbekannte Kürzel): ' . implode(', ', array_map(function ($k, $v) { return "„{$k}“ ({$v}×)"; }, array_keys($l['unbekannt']), $l['unbekannt'])) . '.'];
    $h[] = ['stufe' => 'info', 'text' => 'Übernommene Einträge gelten als genehmigt. Urlaubsanspruch und Übertrag aus dem Vorjahr stehen nicht in der Datei – bitte danach unter „Mitarbeiter“ eintragen.'];
    $xFreitag = [];
    foreach ($l['marken'] as $k => $tage) {
        $wt = array_count_values(array_map('hr_wochentag', array_keys(array_filter($tage, function ($c) { return $c === 'X'; }))));
        arsort($wt);
        if ($wt && reset($wt) >= 4) $xFreitag[] = $l['personen'][$k]['name'] . ' (meist ' . HR_WOCHENTAGE[array_key_first($wt)] . ')';
    }
    if ($xFreitag) $h[] = ['stufe' => 'info', 'text' => 'Regelmäßige freie Tage („x“): ' . implode(', ', $xFreitag) . '. Sie werden als freie Tage übernommen; für künftige Monate unter „Mitarbeiter“ die Arbeitstage einstellen.'];
    return ['zahlen' => $n, 'zeilen' => array_slice($z, 0, 500), 'hinweise' => $h, 'stand' => $pl['stand']];
}

function hr_import_uebernehmen(array $e, array $me): array
{
    return with_lock('hr-personal', function () use ($e, $me) {
        return with_lock('hr-abwesenheiten', function () use ($e, $me) {
            $v = hr_import_vorschau($e, $me);
            if ((string)($e['stand'] ?? '') !== $v['stand']) fail('Die HR-Daten wurden inzwischen geändert. Bitte die Vorschau neu laden.', 409);
            $pl = hr_import_planen($e);
            $personal = hr_personal();
            foreach ($personal['personen'] as &$p) {
                if (isset($pl['aendP'][$p['id']])) { $p = array_merge($p, $pl['aendP'][$p['id']]); $p['geaendert'] = now(); }
            }
            unset($p);
            foreach ($pl['neuP'] as $p) $personal['personen'][] = $p + ['geaendert' => now()];
            hr_personal_schreiben($personal);
            $jetzt = ['t' => now(), 'by' => $me['name'], 'byId' => $me['id']];
            $abw = hr_abwesenheiten();
            $abw['eintraege'] = array_merge($pl['bleibt'], array_map(function ($x) use ($jetzt) { return $x + ['erfasst' => $jetzt]; }, $pl['neuE']));
            hr_abwesenheiten_schreiben($abw);
            $q = s($e['quelle'] ?? '', 120) ?? '';
            audit('hr', 'HR: Urlaubsplanung ' . $pl['lesen']['jahr'] . ' übernommen' . ($q !== '' ? " ($q)" : '') . ': ' . count($pl['neuP']) . ' neue Mitarbeiter, '
                . count($pl['neuE']) . ' Einträge' . ($pl['alt'] ? ', ' . count($pl['alt']) . ' frühere ersetzt' : ''));
            return $v;
        });
    });
}
