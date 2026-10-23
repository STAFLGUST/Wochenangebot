<?php
declare(strict_types=1);
/* Modul HR · Import „Abwesenheiten aus der Zeiterfassung“ (Abwesenheitsbericht, .xlsx) – Importvorlage für die
   Urlaubstage (Entscheidung des Inhabers, 23.10.2026). Der Bericht enthält je Mitarbeiter eine Kopfzeile (Vorname,
   Nachname, Mitarbeiternummer, Abteilung) und darunter die Abwesenheiten (Name der Abwesenheit, Abwesenheitsvergütung,
   Start-/Enddatum, Dauer). Übernommen werden Urlaub (U) und Krankheit (K); Feiertage berechnet die Plattform selbst.
   „Krank ohne AU“ mit „Abgezogen vom Urlaub“ zählt wie in der Zeiterfassung gegen den Urlaubsanspruch (urlaubAbzug).

   Zuordnung: zuerst über die Personalnummer (HR-Angabe „personalnummer“), sonst über den Namen; unbekannte Namen werden
   Mitarbeiter ohne Anmeldung (mit Personalnummer und Abteilung). Erneute Übernahme ersetzt die zuvor aus der
   Zeiterfassung übernommenen Einträge im Zeitraum des Berichts. Tage, für die im System schon ein Eintrag steht
   (Antrag, Personalstelle, Excel-Planung), bleiben unverändert; abweichende Arten erscheinen in der Vorschau.
   Form von Vorschau/Übernahme wie im Importvertrag (docs/plattform/schnittstellen/import.md). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const HR_ZEIT_SPALTEN = ['vorname' => 'vorname', 'nachname' => 'nachname', 'name (abwesenheit)' => 'art', 'abwesenheitsvergütung' => 'verguetung',
    'startdatum' => 'von', 'enddatum' => 'bis', 'dauer' => 'dauer', 'mitarbeiternummer' => 'nr', 'abteilung' => 'abteilung'];

/* Datum aus einer Zelle: Excel-Seriennummer (mit Uhrzeit als Bruchteil) oder Text „TT-MM-JJJJ“, „TT.MM.JJJJ“, „JJJJ-MM-TT“ */
function hr_zeit_datum($v): ?string
{
    if (is_int($v) || is_float($v)) {
        if ($v < 36000 || $v > 80000) return null;
        return gmdate('Y-m-d', ((int)floor($v) - 25569) * 86400);
    }
    $v = trim((string)$v);
    if (preg_match('/^(\d{1,2})[.\-\/](\d{1,2})[.\-\/](\d{4})/', $v, $m)) return hr_datum(sprintf('%04d-%02d-%02d', $m[3], $m[2], $m[1]));
    if (preg_match('/^(\d{4})-(\d{2})-(\d{2})/', $v, $m)) return hr_datum("{$m[1]}-{$m[2]}-{$m[3]}");
    return null;
}

/* Art der Abwesenheit → Kürzel (null = nicht übernehmen, z. B. Feiertag; false = unbekannt) */
function hr_zeit_art(string $art)
{
    $a = mb_strtolower(trim($art));
    if ($a === 'feiertag') return null;
    if (str_starts_with($a, 'urlaub')) return 'U';
    if (str_starts_with($a, 'krank')) return 'K';
    if (str_contains($a, 'gleit')) return 'G';
    return false;
}

/* Bericht lesen (Zellen vom Leser im Browser): Mitarbeiter und Abwesenheiten */
function hr_zeit_lesen(array $e): array
{
    $blaetter = $e['blaetter'] ?? null;
    if (!is_array($blaetter) || !array_is_list($blaetter) || !$blaetter || count($blaetter) > 10) throw new InvalidArgumentException('Die Datei enthält kein lesbares Tabellenblatt.');
    $grid = null; $kopf = null; $sp = [];
    foreach ($blaetter as $b) {
        if (!is_array($b) || !is_array($b['grid'] ?? null) || count($b['grid']) > 20000) throw new InvalidArgumentException('Ungültige Datei.');
        foreach (array_slice($b['grid'], 0, 20, true) as $r => $zeile) {
            $m = [];
            foreach ((array)$zeile as $c => $v) { $k = mb_strtolower(trim((string)$v)); if (isset(HR_ZEIT_SPALTEN[$k])) $m[HR_ZEIT_SPALTEN[$k]] = $c; }
            if (isset($m['vorname'], $m['nachname'], $m['art'], $m['von'], $m['bis'])) { $grid = $b['grid']; $kopf = $r; $sp = $m; break 2; }
        }
    }
    if ($grid === null) throw new InvalidArgumentException('Das ist kein Abwesenheitsbericht der Zeiterfassung: Spalten „Vorname“, „Nachname“, „Name (Abwesenheit)“, „Startdatum“ und „Enddatum“ fehlen.');
    $zelle = function (array $z, string $f) use ($sp) { return isset($sp[$f]) ? ($z[$sp[$f]] ?? null) : null; };
    $personen = []; $eintraege = []; $fehler = []; $unbekannt = []; $von = null; $bis = null; $wer = null;
    for ($r = $kopf + 1; $r < count($grid); $r++) {
        $z = (array)($grid[$r] ?? []);
        $vor = s($zelle($z, 'vorname') ?? '', 40) ?? ''; $nach = s($zelle($z, 'nachname') ?? '', 40) ?? '';
        if ($vor !== '' || $nach !== '') {
            $nr = s((string)($zelle($z, 'nr') ?? ''), 20) ?? '';
            $wer = $nr !== '' ? 'nr:' . $nr : 'name:' . hr_namekey(trim("$vor $nach"));
            $personen[$wer] = ['vorname' => $vor, 'nachname' => $nach, 'name' => trim("$vor $nach"), 'nr' => $nr, 'abteilung' => s($zelle($z, 'abteilung') ?? '', 40) ?? '', 'zeile' => $r + 1];
            continue;
        }
        $art = trim((string)($zelle($z, 'art') ?? ''));
        if ($art === '') continue;
        if ($wer === null) { $fehler[] = ['zeile' => $r + 1, 'schluessel' => $art, 'text' => 'Abwesenheit ohne Mitarbeiter darüber – übersprungen.']; continue; }
        $a = hr_zeit_datum($zelle($z, 'von')); $b = hr_zeit_datum($zelle($z, 'bis'));
        if (!$a || !$b || $b < $a) { $fehler[] = ['zeile' => $r + 1, 'schluessel' => $art, 'text' => $personen[$wer]['name'] . ': Start- oder Enddatum fehlt bzw. ungültig – übersprungen.']; continue; }
        $von = $von === null || $a < $von ? $a : $von; $bis = $bis === null || $b > $bis ? $b : $bis;
        $k = hr_zeit_art($art);
        if ($k === null) continue;
        if ($k === false) { $unbekannt[$art] = ($unbekannt[$art] ?? 0) + 1; continue; }
        $abzug = $k === 'K' && str_contains(mb_strtolower((string)($zelle($z, 'verguetung') ?? '')), 'urlaub');
        $eintraege[] = ['wer' => $wer, 'art' => $k, 'abzug' => $abzug, 'von' => $a, 'bis' => $b, 'zeile' => $r + 1];
    }
    if (!$personen) throw new InvalidArgumentException('Im Bericht wurde kein Mitarbeiter gefunden.');
    return ['personen' => $personen, 'eintraege' => $eintraege, 'fehler' => $fehler, 'unbekannt' => $unbekannt, 'von' => $von, 'bis' => $bis];
}

/* Mitarbeiter zuordnen: Personalnummer, sonst Name (Anzeigename, Vor-/Nachname, Benutzername) */
function hr_zeit_zuordnen(array $l, array $personal, array $users): array
{
    $nachNr = []; $nachName = [];
    foreach ($personal['personen'] as $p) {
        if (($p['personalnummer'] ?? '') !== '') $nachNr[(string)$p['personalnummer']][$p['id']] = $p;
        $namen = [hr_namekey(hr_name($p))];
        if ($p['nutzer'] !== null && isset($users[$p['nutzer']])) $namen = array_merge($namen, hr_konto_namen($users[$p['nutzer']]));
        foreach (array_unique($namen) as $k) if ($k !== '') $nachName[$k][$p['id']] = $p;
    }
    $zu = []; $neu = []; $mehrdeutig = []; $aehnlich = [];
    foreach ($l['personen'] as $wer => $x) {
        $treffer = $x['nr'] !== '' ? array_values($nachNr[$x['nr']] ?? []) : [];
        if (!$treffer) $treffer = array_values($nachName[hr_namekey($x['name'])] ?? []);
        if (count($treffer) > 1) { $mehrdeutig[$wer] = $x['name']; continue; }
        if ($treffer) { $zu[$wer] = $treffer[0]; continue; }
        $neu[$wer] = $x;
        // ähnliche Namen (Schreibweise, z. B. Ulrich ↔ Ullrich) als Hinweis – nie automatisch zuordnen
        foreach ($personal['personen'] as $p) {
            if ($p['altbestand']) continue;
            if (levenshtein(hr_namekey($x['name']), hr_namekey(hr_name($p))) <= 2) $aehnlich[$wer][] = hr_name($p);
        }
    }
    return [$zu, $neu, $mehrdeutig, $aehnlich];
}

/* Plan der Übernahme (ohne zu speichern) */
function hr_zeit_planen(array $e): array
{
    $l = hr_zeit_lesen($e);
    $personal = hr_personal(); $abw = hr_abwesenheiten();
    $users = []; foreach (users_load() as $u) $users[(string)$u['id']] = $u;
    [$zu, $neu, $mehrdeutig, $aehnlich] = hr_zeit_zuordnen($l, $personal, $users);
    $abteilungen = !empty($e['optionen']['abteilungen']);
    $aend = [];
    foreach ($zu as $wer => $p) {
        $x = $l['personen'][$wer]; $w = [];
        if ($x['nr'] !== '' && ($p['personalnummer'] ?? '') !== $x['nr']) $w['personalnummer'] = $x['nr'];
        if ($abteilungen && $x['abteilung'] !== '' && $p['abteilung'] !== $x['abteilung']) $w['abteilung'] = $x['abteilung'];
        if ($w) $aend[$p['id']] = $w;
    }
    // zuvor aus der Zeiterfassung übernommene Einträge im Zeitraum des Berichts werden ersetzt
    $rv = $l['von']; $rb = $l['bis'];
    $alt = $rv === null ? [] : array_values(array_filter($abw['eintraege'], function ($x) use ($rv, $rb) {
        return ($x['quelle'] ?? '') === 'zeiterfassung' && $x['von'] >= $rv && $x['bis'] <= $rb;   // nur ganz im Zeitraum (Rest bleibt)
    }));
    $altIds = array_column($alt, 'id');
    $bleibt = array_values(array_filter($abw['eintraege'], function ($x) use ($altIds) { return !in_array($x['id'], $altIds, true); }));
    // belegte Tage je Person (aktive Einträge, die bleiben)
    $belegt = [];
    foreach ($bleibt as $x) {
        if (!in_array($x['status'], HR_AKTIV, true)) continue;
        for ($d = $x['von']; $d <= $x['bis']; $d = hr_plus($d, 1)) $belegt[$x['person']][$d] = $x['art'];
    }
    $tage = []; $gleich = 0; $abweichend = [];
    foreach ($l['eintraege'] as $x) {
        if (isset($mehrdeutig[$x['wer']])) continue;
        $pid = isset($zu[$x['wer']]) ? $zu[$x['wer']]['id'] : 'neu:' . $x['wer'];
        $code = $x['art'] . ($x['abzug'] ? '!' : '');
        for ($d = $x['von']; $d <= $x['bis']; $d = hr_plus($d, 1)) {
            if (hr_wochentag($d) > 5 || hr_feiertag($d) !== null) continue;
            if (isset($belegt[$pid][$d])) {
                if ($belegt[$pid][$d] === $x['art']) $gleich++;
                else $abweichend[] = [$l['personen'][$x['wer']]['name'], $d, $belegt[$pid][$d], $x['art']];
                continue;
            }
            $tage[$pid][$d] = $code;
        }
    }
    $neuE = [];
    foreach ($tage as $pid => $t) {
        foreach (hr_import_zeitraeume($t) as $z) {
            $neuE[] = ['id' => hr_neue_id('a'), 'person' => $pid, 'art' => rtrim($z['art'], '!'), 'von' => $z['von'], 'bis' => $z['bis'], 'status' => 'genehmigt',
                       'notiz' => '', 'quelle' => 'zeiterfassung'] + (str_ends_with($z['art'], '!') ? ['urlaubAbzug' => true] : []);
        }
    }
    return ['lesen' => $l, 'zu' => $zu, 'neu' => $neu, 'mehrdeutig' => $mehrdeutig, 'aehnlich' => $aehnlich, 'aend' => $aend, 'alt' => $alt, 'bleibt' => $bleibt,
            'neuE' => $neuE, 'gleich' => $gleich, 'abweichend' => $abweichend, 'personen' => hr_personen_index($personal),
            'stand' => hr_import_stand($personal, $abw, count($users))];
}

function hr_zeit_vorschau(array $e, array $me): array
{
    $pl = hr_zeit_planen($e);
    $l = $pl['lesen'];
    $n = ['neu' => 0, 'geaendert' => 0, 'entfaellt' => 0, 'unveraendert' => $pl['gleich'], 'fehler' => 0];
    $z = [];
    foreach ($pl['neu'] as $wer => $x) {
        $n['neu']++;
        $hinweis = isset($pl['aehnlich'][$wer]) ? ' – ähnlich: ' . implode(', ', $pl['aehnlich'][$wer]) . ' (gleiche Person? Dort die Personalnummer ' . ($x['nr'] ?: '–') . ' eintragen und erneut prüfen)' : '';
        $z[] = ['art' => 'neu', 'zeile' => $x['zeile'], 'schluessel' => $x['nr'] !== '' ? 'Nr. ' . $x['nr'] : 'Mitarbeiter', 'name' => $x['name'],
                'text' => 'neuer Mitarbeiter ohne Anmeldung' . ($x['abteilung'] !== '' ? ' (' . $x['abteilung'] . ')' : '') . $hinweis];
    }
    foreach ($pl['mehrdeutig'] as $wer => $name) { $n['fehler']++; $z[] = ['art' => 'fehler', 'zeile' => $l['personen'][$wer]['zeile'], 'schluessel' => 'Mitarbeiter', 'name' => $name, 'text' => 'nicht übernommen: Name/Personalnummer gibt es mehrfach unter den Mitarbeitern']; }
    foreach ($pl['aend'] as $pid => $w) {
        $n['geaendert']++;
        $t = [];
        if (isset($w['personalnummer'])) $t[] = 'Personalnummer ' . $w['personalnummer'];
        if (isset($w['abteilung'])) $t[] = 'Abteilung ' . $w['abteilung'];
        $z[] = ['art' => 'geaendert', 'schluessel' => 'Mitarbeiter', 'name' => hr_name($pl['personen'][$pid]), 'text' => implode(', ', $t)];
    }
    $namen = [];
    foreach ($pl['personen'] as $id => $p) $namen[$id] = hr_name($p);
    foreach ($pl['neu'] as $wer => $x) $namen['neu:' . $wer] = $x['name'];
    $proPerson = [];
    foreach ($pl['neuE'] as $x) {
        $k = $x['art'] . (!empty($x['urlaubAbzug']) ? '!' : '');
        $proPerson[$x['person']][$k] = ($proPerson[$x['person']][$k] ?? 0) + count(hr_tage(['arbeitstage' => [1, 2, 3, 4, 5]], $x['von'], $x['bis']));
    }
    foreach ($proPerson as $pid => $arten) {
        $n['neu']++;
        $t = [];
        foreach (['U' => 'Urlaub', 'K' => 'Krank', 'K!' => 'Krank (vom Urlaub abgezogen)', 'G' => 'Gleittag'] as $k => $txt) if (!empty($arten[$k])) $t[] = "$txt {$arten[$k]} " . ($arten[$k] === 1 ? 'Tag' : 'Tage');
        $z[] = ['art' => 'neu', 'schluessel' => 'Abwesenheiten', 'name' => $namen[$pid] ?? $pid, 'text' => implode(' · ', $t)];
    }
    if ($pl['alt']) { $n['entfaellt'] += count($pl['alt']); $z[] = ['art' => 'entfaellt', 'schluessel' => 'Abwesenheiten', 'name' => 'frühere Übernahme', 'text' => count($pl['alt']) . ' Einträge der letzten Übernahme aus der Zeiterfassung werden ersetzt']; }
    $abw = [];
    foreach ($pl['abweichend'] as [$name, $d, $ist, $neu]) $abw[$name][] = hr_de($d) . " ($ist statt $neu)";
    foreach ($abw as $name => $tage) { $n['fehler']++; $z[] = ['art' => 'fehler', 'schluessel' => 'abweichend', 'name' => $name, 'text' => 'im System anders eingetragen, bleibt unverändert: ' . implode(', ', array_slice($tage, 0, 10)) . (count($tage) > 10 ? ' …' : '')]; }
    foreach ($l['fehler'] as $f) { $n['fehler']++; $z[] = ['art' => 'fehler', 'zeile' => $f['zeile'], 'schluessel' => $f['schluessel'], 'name' => '', 'text' => $f['text']]; }
    $h = [['stufe' => 'info', 'text' => 'Abwesenheitsbericht ' . ($l['von'] ? hr_de($l['von']) . '–' . hr_de($l['bis']) : '') . ': ' . count($l['personen']) . ' Mitarbeiter, ' . count($l['eintraege']) . ' Abwesenheiten (ohne Feiertage).']];
    if ($pl['gleich']) $h[] = ['stufe' => 'info', 'text' => $pl['gleich'] . ' Tage sind schon gleich eingetragen (Antrag, Personalstelle oder Excel-Planung) und bleiben, wie sie sind.'];
    if ($l['unbekannt']) $h[] = ['stufe' => 'warn', 'text' => 'Nicht übernommen (unbekannte Arten): ' . implode(', ', array_map(function ($k, $v) { return "„{$k}“ ({$v}×)"; }, array_keys($l['unbekannt']), $l['unbekannt'])) . '.'];
    $h[] = ['stufe' => 'info', 'text' => 'Übernommene Einträge gelten als genehmigt. „Krank ohne AU“ mit „Abgezogen vom Urlaub“ zählt wie in der Zeiterfassung gegen den Urlaubsanspruch.'];
    return ['zahlen' => $n, 'zeilen' => array_slice($z, 0, 500), 'hinweise' => $h, 'stand' => $pl['stand']];
}

function hr_zeit_uebernehmen(array $e, array $me): array
{
    return with_lock('hr-personal', function () use ($e, $me) {
        return with_lock('hr-abwesenheiten', function () use ($e, $me) {
            $v = hr_zeit_vorschau($e, $me);
            if ((string)($e['stand'] ?? '') !== $v['stand']) fail('Die HR-Daten wurden inzwischen geändert. Bitte die Vorschau neu laden.', 409);
            $pl = hr_zeit_planen($e);
            $neuNutzer = [];
            foreach ($pl['neu'] as $wer => $x) $neuNutzer[$wer] = mitarbeiter_ohne_zugang_anlegen($x['vorname'], $x['nachname'], $me);
            $users = []; foreach (users_load() as $u) $users[(string)$u['id']] = $u;
            $roh = hr_personal_roh();
            foreach ($pl['aend'] as $pid => $w) {
                $p = $pl['personen'][$pid];
                if ($p['nutzer'] !== null && isset($users[$p['nutzer']])) { hr_angaben_setzen($roh, $p['nutzer'], $w, $users[$p['nutzer']]); continue; }
                foreach ($roh['personen'] as &$x) if ($x['id'] === $pid) $x = hr_person_norm(array_merge($x, $w, ['geaendert' => now()]));
                unset($x);
            }
            $personId = [];
            foreach ($pl['neu'] as $wer => $x) {
                $u = $neuNutzer[$wer];
                $personId['neu:' . $wer] = hr_angaben_setzen($roh, (string)$u['id'], ['abteilung' => $x['abteilung'], 'personalnummer' => $x['nr'], 'aktiv' => true], $u)['id'];
            }
            hr_personal_schreiben($roh);
            $jetzt = ['t' => now(), 'by' => $me['name'], 'byId' => $me['id']];
            $abw = hr_abwesenheiten();
            $abw['eintraege'] = array_merge($pl['bleibt'], array_map(function ($x) use ($jetzt, $personId) {
                return array_merge($x, ['person' => $personId[$x['person']] ?? $x['person'], 'erfasst' => $jetzt]);
            }, $pl['neuE']));
            hr_abwesenheiten_schreiben($abw);
            $q = s($e['quelle'] ?? '', 120) ?? '';
            audit('hr', 'HR: Abwesenheiten aus der Zeiterfassung übernommen' . ($q !== '' ? " ($q)" : '') . ': ' . count($pl['neu']) . ' neue Mitarbeiter ohne Anmeldung, '
                . count($pl['neuE']) . ' Einträge' . ($pl['alt'] ? ', ' . count($pl['alt']) . ' frühere ersetzt' : ''));
            return $v;
        });
    });
}
