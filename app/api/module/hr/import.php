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
    $sheets = $e['blaetter'] ?? ($e['daten']['blaetter'] ?? null);   // Importzentrale: Daten des Lesers direkt; HR-Aktion: unter „daten“
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

/* Importart für die Importzentrale (Verwaltung → Import, docs/plattform/schnittstellen/import.md). Leser im Browser:
   app/module/hr/verwaltung-hr.js (window.WA.importLeser.urlaubsplanung). */
function import_arten_hr(): array
{
    return [
        'urlaubsplanung' => ['name' => 'Urlaubsplanung (Excel)', 'beschreibung' => 'Bisherige Planung „Urlaub 2026.xlsx“: ein Blatt je Monat, Namen in Spalte C, U/K/G/x je Tag. Unbekannte Namen werden Mitarbeiter ohne Anmeldung; erneute Übernahme ersetzt die zuvor übernommenen Einträge desselben Jahres.',
            'recht' => ['hr.verwalten'], 'aktion' => 'hr_import_uebernehmen', 'dateien' => ['xlsx'], 'kodierung' => 'Excel-Arbeitsmappe (.xlsx)',
            'vorschau' => 'hr_import_vorschau', 'uebernahme' => 'hr_import_uebernehmen'],
        // Importvorlage für Urlaubs- und Krankheitstage (Entscheidung 23.10.2026): Abwesenheitsbericht der Zeiterfassung
        'zeiterfassung' => ['name' => 'Abwesenheiten aus der Zeiterfassung', 'beschreibung' => 'Abwesenheitsbericht der Zeiterfassung (.xlsx, je Mitarbeiter eine Kopfzeile mit Mitarbeiternummer und darunter Urlaub/Krank/Feiertag). Zuordnung über die Personalnummer, sonst über den Namen; unbekannte Mitarbeiter werden ohne Anmeldung angelegt. Erneute Übernahme ersetzt die zuvor aus der Zeiterfassung übernommenen Einträge im Zeitraum des Berichts.',
            'recht' => ['hr.verwalten'], 'aktion' => 'hr_import_uebernehmen', 'dateien' => ['xlsx'], 'kodierung' => 'Excel-Arbeitsmappe (.xlsx)',
            'optionen' => [['id' => 'abteilungen', 'typ' => 'schalter', 'label' => 'Abteilungen aus der Zeiterfassung übernehmen', 'standard' => false]],
            'vorschau' => 'hr_zeit_vorschau', 'uebernahme' => 'hr_zeit_uebernehmen'],
    ];
}

/* Plan der Übernahme (ohne zu speichern). Namen werden den Mitarbeitern zugeordnet (Anzeigename, Vor- + Nachname,
   Benutzername „vorname-nachname“); unbekannte Namen werden bei der Übernahme Mitarbeiter ohne Anmeldung. */
/* $me: wer übernimmt – Zeilen der eigenen Person werden nicht übernommen und ihre früheren Einträge nicht ersetzt
   (Vier-Augen-Prinzip: eigene Abwesenheiten trägt eine andere Person der Personalstelle ein) */
function hr_import_planen(array $e, ?array $me = null): array
{
    $l = hr_import_lesen($e);
    $personal = hr_personal(); $abw = hr_abwesenheiten();
    $eigen = $me ? hr_eigene_ids($personal, $me) : [];
    $users = []; foreach (users_load() as $u) $users[(string)$u['id']] = $u;
    $nachName = [];
    foreach ($personal['personen'] as $p) {
        $namen = [hr_namekey(hr_name($p))];
        if ($p['nutzer'] !== null && isset($users[$p['nutzer']])) $namen = array_merge($namen, hr_konto_namen($users[$p['nutzer']]));
        foreach (array_unique($namen) as $k) if ($k !== '') $nachName[$k][$p['id']] = $p;
    }
    $neuP = []; $aendP = []; $zuordnung = []; $mehrdeutig = []; $eigeneZeilen = [];
    foreach ($l['personen'] as $k => $x) {
        $treffer = array_values($nachName[$k] ?? []);
        if (count($treffer) > 1) { $mehrdeutig[$k] = $x['name']; continue; }
        if ($treffer) {
            $p = $treffer[0];
            if (isset($eigen[$p['id']])) { $eigeneZeilen[$k] = $x['name']; continue; }
            if ($p['abteilung'] !== $x['abteilung'] || $p['pos'] !== $x['pos']) $aendP[$p['id']] = ['abteilung' => $x['abteilung'], 'pos' => $x['pos']];
            $zuordnung[$k] = $p['id'];
            continue;
        }
        $teile = explode(' ', $x['name']);
        $nach = count($teile) > 1 ? array_pop($teile) : '';
        $neuP['neu:' . $k] = ['id' => 'neu:' . $k, 'vorname' => implode(' ', $teile), 'nachname' => $nach, 'abteilung' => $x['abteilung'], 'pos' => $x['pos']];
        $zuordnung[$k] = 'neu:' . $k;
    }
    $jahr = $l['jahr'];
    // bisher übernommene Einträge dieses Jahres werden ersetzt
    $alt = array_values(array_filter($abw['eintraege'], function ($x) use ($jahr, $eigen) { return ($x['quelle'] ?? '') === 'import' && (int)substr($x['von'], 0, 4) === $jahr && !isset($eigen[$x['person']]); }));
    $altIds = array_column($alt, 'id');
    $bleibt = array_values(array_filter($abw['eintraege'], function ($x) use ($altIds) { return !in_array($x['id'], $altIds, true); }));
    $neuE = []; $konflikte = [];
    foreach ($l['marken'] as $k => $tage) {
        if (!isset($zuordnung[$k])) continue;
        $pid = $zuordnung[$k];
        foreach (hr_import_zeitraeume($tage) as $z) {
            $kol = hr_kollision($bleibt, $pid, $z['von'], $z['bis'], null, $z['art']);
            if ($kol) { $konflikte[] = [$l['personen'][$k]['name'], $z, $kol]; continue; }
            $neuE[] = ['id' => hr_neue_id('a'), 'person' => $pid, 'art' => $z['art'], 'von' => $z['von'], 'bis' => $z['bis'], 'status' => 'genehmigt',
                       'notiz' => '', 'quelle' => 'import'];
        }
    }
    return ['lesen' => $l, 'neuP' => $neuP, 'aendP' => $aendP, 'mehrdeutig' => $mehrdeutig, 'eigen' => $eigeneZeilen, 'alt' => $alt, 'bleibt' => $bleibt, 'neuE' => $neuE,
            'konflikte' => $konflikte, 'personen' => hr_personen_index($personal), 'stand' => hr_import_stand($personal, $abw, count($users))];
}
function hr_import_stand(array $personal, array $abw, int $mitarbeiter = 0): string { return $personal['rev'] . '-' . $abw['rev'] . '-' . $mitarbeiter; }

function hr_import_vorschau(array $e, array $me): array
{
    $pl = hr_import_planen($e, $me);
    $l = $pl['lesen'];
    $n = ['neu' => 0, 'geaendert' => 0, 'entfaellt' => 0, 'unveraendert' => 0, 'fehler' => 0];
    $z = [];
    foreach ($pl['eigen'] as $name) { $n['fehler']++; $z[] = ['art' => 'fehler', 'schluessel' => 'Mitarbeiter', 'name' => $name, 'text' => 'nicht übernommen – eigene Person: bitte durch eine andere Person der Personalstelle übernehmen lassen']; }
    foreach ($pl['neuP'] as $p) { $n['neu']++; $z[] = ['art' => 'neu', 'schluessel' => 'Mitarbeiter', 'name' => hr_name($p), 'text' => 'neuer Mitarbeiter ohne Anmeldung' . ($p['abteilung'] !== '' ? ' (' . $p['abteilung'] . ')' : '')]; }
    foreach ($pl['mehrdeutig'] as $name) { $n['fehler']++; $z[] = ['art' => 'fehler', 'schluessel' => 'Mitarbeiter', 'name' => $name, 'text' => 'nicht übernommen: Name gibt es mehrfach unter den Mitarbeitern – bitte Namen eindeutig machen']; }
    $alle = $pl['personen'] + $pl['neuP'];
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
    $h[] = ['stufe' => 'info', 'text' => 'Übernommene Einträge gelten als genehmigt. Urlaubsanspruch und Übertrag aus dem Vorjahr stehen nicht in der Datei – bitte danach unter Verwaltung → Mitarbeiter eintragen.'];
    $xFreitag = [];
    foreach ($l['marken'] as $k => $tage) {
        $wt = array_count_values(array_map('hr_wochentag', array_keys(array_filter($tage, function ($c) { return $c === 'X'; }))));
        arsort($wt);
        if ($wt && reset($wt) >= 4) $xFreitag[] = $l['personen'][$k]['name'] . ' (meist ' . HR_WOCHENTAGE[array_key_first($wt)] . ')';
    }
    if ($xFreitag) $h[] = ['stufe' => 'info', 'text' => 'Regelmäßige freie Tage („x“): ' . implode(', ', $xFreitag) . '. Sie werden als freie Tage übernommen; für künftige Monate unter Verwaltung → Mitarbeiter die Arbeitstage einstellen.'];
    return ['zahlen' => $n, 'zeilen' => array_slice($z, 0, 500), 'hinweise' => $h, 'stand' => $pl['stand']];
}

function hr_import_uebernehmen(array $e, array $me): array
{
    return with_lock('hr-personal', function () use ($e, $me) {
        return with_lock('hr-abwesenheiten', function () use ($e, $me) {
            $v = hr_import_vorschau($e, $me);
            if ((string)($e['stand'] ?? '') !== $v['stand']) fail('Die HR-Daten wurden inzwischen geändert. Bitte die Vorschau neu laden.', 409);
            $pl = hr_import_planen($e, $me);
            // neue Mitarbeiter ohne Anmeldung anlegen (Plattformkern), dann HR-Angaben setzen
            $ids = [];
            foreach ($pl['neuP'] as $platz => $p) $ids[$platz] = mitarbeiter_ohne_zugang_anlegen($p['vorname'], $p['nachname'], $me);
            $users = []; foreach (users_load() as $u) $users[(string)$u['id']] = $u;
            $roh = hr_personal_roh();
            foreach ($pl['aendP'] as $pid => $werte) {
                $p = $pl['personen'][$pid];
                if ($p['nutzer'] !== null && isset($users[$p['nutzer']])) { hr_angaben_setzen($roh, $p['nutzer'], $werte, $users[$p['nutzer']]); continue; }
                foreach ($roh['personen'] as &$x) if ($x['id'] === $pid) $x = hr_person_norm(array_merge($x, $werte, ['geaendert' => now()]));
                unset($x);
            }
            $personId = [];
            foreach ($pl['neuP'] as $platz => $p) {
                $u = $ids[$platz];
                $personId[$platz] = hr_angaben_setzen($roh, (string)$u['id'], ['abteilung' => $p['abteilung'], 'pos' => $p['pos'], 'aktiv' => true], $u)['id'];
            }
            hr_personal_schreiben($roh);
            $jetzt = ['t' => now(), 'by' => $me['name'], 'byId' => $me['id']];
            $abw = hr_abwesenheiten();
            $abw['eintraege'] = array_merge($pl['bleibt'], array_map(function ($x) use ($jetzt, $personId) {
                return array_merge($x, ['person' => $personId[$x['person']] ?? $x['person'], 'erfasst' => $jetzt]);
            }, $pl['neuE']));
            hr_abwesenheiten_schreiben($abw);
            $q = s($e['quelle'] ?? '', 120) ?? '';
            audit('hr', 'HR: Urlaubsplanung ' . $pl['lesen']['jahr'] . ' übernommen' . ($q !== '' ? " ($q)" : '') . ': ' . count($pl['neuP']) . ' neue Mitarbeiter ohne Anmeldung, '
                . count($pl['neuE']) . ' Einträge' . ($pl['alt'] ? ', ' . count($pl['alt']) . ' frühere ersetzt' : ''));
            return $v;
        });
    });
}
