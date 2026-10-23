<?php
declare(strict_types=1);
/* Aktionen: HR · Urlaubsverwaltung (Oberfläche hr.intern, Logik in app/api/module/hr/)
   Rechte (GR-103): hr.antrag – eigener Urlaub, Anträge, Abwesenheitskalender (nur „abwesend“);
                    hr.verwalten – zentrale Stelle: genehmigen, Einträge K/G/U/freie Tage, Mitarbeiter, Export, Übernahme.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Jahr aus der Anfrage (Standard: aktuelles Jahr) */
function hr_jahr_param($v): int
{
    $j = is_numeric($v) ? (int)$v : (int)date('Y');
    if ($j < 2000 || $j > 2100) throw new InvalidArgumentException('Ungültiges Jahr.');
    return $j;
}

/* Angaben einer Person für die Personalstelle */
function hr_person_aus(array $p, array $eintraege, int $jahr, array $nutzerNamen): array
{
    return $p + ['name' => hr_name($p), 'nutzerName' => $p['nutzer'] !== null ? ($nutzerNamen[$p['nutzer']] ?? null) : null,
                 'konto' => hr_konto($p, $eintraege, $jahr)];
}

switch ($action) {
        /* Startseite: eigene Person, Urlaubskonto, eigene Einträge, Feiertage, Sperren */
        case 'hr_start': {
            $me = require_perm('hr.antrag');
            header('Cache-Control: no-store');
            $jahr = hr_jahr_param($_GET['jahr'] ?? null);
            $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
            $ich = hr_ich($personal, $me);
            $verwalten = may($me, 'hr.verwalten');
            $eigene = [];
            if ($ich) { $frei = hr_freie_tage($abw['eintraege'], $ich['id']); foreach ($abw['eintraege'] as $e) if ($e['person'] === $ich['id']) $eigene[] = hr_eintrag_aus($e, $ich, $frei); }
            usort($eigene, function ($a, $b) { return $b['von'] <=> $a['von']; });
            $kollegen = [];
            foreach ($personal['personen'] as $p) if ($p['aktiv'] && (!$ich || $p['id'] !== $ich['id'])) $kollegen[] = ['id' => $p['id'], 'name' => hr_name($p)];
            respond(['ok' => true, 'jahr' => $jahr, 'heute' => hr_heute(), 'name' => $me['name'], 'verwalten' => $verwalten,
                     'offen' => $verwalten ? count(array_filter($abw['eintraege'], function ($e) { return $e['status'] === 'beantragt'; })) : null,
                     'ich' => $ich ? ['id' => $ich['id'], 'name' => hr_name($ich), 'abteilung' => $ich['abteilung'], 'arbeitstage' => $ich['arbeitstage']] : null,
                     'konto' => $ich ? hr_konto($ich, $abw['eintraege'], $jahr) : null, 'eintraege' => $eigene, 'kollegen' => $kollegen,
                     'feiertage' => hr_feiertage($jahr), 'sperren' => $einst['sperren'], 'uebertragBis' => HR_UEBERTRAG_BIS]);
        }

        /* Monatsplan / Abwesenheitskalender: Kollegen nur „abwesend“, Personalstelle mit Kürzeln */
        case 'hr_monat': {
            $me = require_perm('hr.antrag');
            header('Cache-Control: no-store');
            $jahr = hr_jahr_param($_GET['jahr'] ?? null);
            $monat = (int)($_GET['monat'] ?? date('n'));
            if ($monat < 1 || $monat > 12) fail('Ungültiger Monat.', 422);
            respond(['ok' => true, 'voll' => may($me, 'hr.verwalten')] + hr_monat($jahr, $monat, $me, may($me, 'hr.verwalten')));
        }

        /* Urlaubsantrag stellen (eigene Person) */
        case 'hr_antrag': {
            $me = require_perm('hr.antrag', true);
            $b = body();
            [$von, $bis] = hr_zeitraum_pruefen($b);
            $notiz = s($b['notiz'] ?? '', 300) ?? '';
            $res = with_lock('hr-abwesenheiten', function () use ($me, $von, $bis, $notiz, $b) {
                $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
                $ich = hr_ich($personal, $me);
                if (!$ich) fail('Ihr Konto ist noch keinem Mitarbeiter zugeordnet. Bitte an die Personalstelle wenden.', 409);
                if ($von < hr_heute()) fail('Urlaub kann nur für heute oder später beantragt werden. Vergangene Tage trägt die Personalstelle ein.', 422);
                $tage = hr_tage($ich, $von, $bis, null, null, hr_freie_tage($abw['eintraege'], $ich['id']));
                if (!$tage) fail('Im gewählten Zeitraum liegen keine Arbeitstage (Wochenende, Feiertag oder freier Tag).', 422);
                if ($s = hr_ueberschneidung($einst['sperren'], $von, $bis)) fail('Im Zeitraum ' . hr_zeitraum_text($s['von'], $s['bis']) . ' gilt eine Urlaubssperre' . ($s['text'] !== '' ? ' (' . $s['text'] . ')' : '') . '.', 422);
                if ($k = hr_kollision($abw['eintraege'], $ich['id'], $von, $bis)) fail('Für ' . hr_zeitraum_text($k['von'], $k['bis']) . ' gibt es bereits einen Eintrag.', 409);
                $vert = null;
                if (($b['vertretung'] ?? '') !== '' && ($b['vertretung'] ?? null) !== null) {
                    $vp = hr_personen_index($personal)[(string)$b['vertretung']] ?? null;
                    if (!$vp || !$vp['aktiv'] || $vp['id'] === $ich['id']) fail('Bitte eine gültige Vertretung wählen.', 422);
                    $vert = $vp['id'];
                }
                $e = ['id' => hr_neue_id('a'), 'person' => $ich['id'], 'art' => 'U', 'von' => $von, 'bis' => $bis, 'status' => 'beantragt', 'notiz' => $notiz,
                      'vertretung' => $vert, 'quelle' => 'antrag', 'erfasst' => ['t' => now(), 'by' => $me['name'], 'byId' => $me['id']]];
                $abw['eintraege'][] = $e;
                hr_abwesenheiten_schreiben($abw);
                $jahr = (int)substr($von, 0, 4);
                return [$e, $ich, count($tage), hr_konto($ich, $abw['eintraege'], $jahr)];
            });
            [$e, $ich, $n, $konto] = $res;
            audit('hr', 'HR: Urlaub beantragt ' . hr_zeitraum_text($e['von'], $e['bis']) . " ($n Arbeitstage)");
            respond(['ok' => true, 'eintrag' => hr_eintrag_aus($e, $ich), 'konto' => $konto,
                     'hinweis' => $konto['verfuegbar'] < 0 ? 'Der Antrag übersteigt Ihren Resturlaub um ' . (-$konto['verfuegbar']) . ' Tage – die Personalstelle entscheidet.' : null]);
        }

        /* Eigenen Antrag zurückziehen (offen oder genehmigt, solange er noch nicht begonnen hat) */
        case 'hr_antrag_zurueckziehen': {
            $me = require_perm('hr.antrag', true);
            $id = s(body()['id'] ?? '', 40) ?? '';
            $e = with_lock('hr-abwesenheiten', function () use ($me, $id) {
                $personal = hr_personal(); $abw = hr_abwesenheiten();
                $ich = hr_ich($personal, $me);
                foreach ($abw['eintraege'] as &$e) {
                    if ($e['id'] !== $id) continue;
                    if (!$ich || $e['person'] !== $ich['id'] || $e['art'] !== 'U') break;
                    if (!in_array($e['status'], HR_AKTIV, true)) fail('Dieser Antrag ist bereits erledigt.', 409);
                    if ($e['status'] === 'genehmigt' && $e['von'] <= hr_heute()) fail('Begonnener Urlaub kann nur die Personalstelle ändern.', 409);
                    $e['status'] = 'zurueckgezogen';
                    $e['entscheidung'] = ['t' => now(), 'by' => $me['name'], 'grund' => 'vom Mitarbeiter zurückgezogen'];
                    $kopie = $e;
                    unset($e);
                    hr_abwesenheiten_schreiben($abw);
                    return $kopie;
                }
                fail('Antrag nicht gefunden.', 404);
            });
            audit('hr', 'HR: Urlaubsantrag zurückgezogen ' . hr_zeitraum_text($e['von'], $e['bis']));
            respond(['ok' => true]);
        }

        /* Personalstelle: Mitarbeiter mit Konten, offene Anträge, alle Einträge des Jahres, Einstellungen */
        case 'hr_verwaltung': {
            $me = require_perm('hr.verwalten');
            header('Cache-Control: no-store');
            $jahr = hr_jahr_param($_GET['jahr'] ?? null);
            $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
            $idx = hr_personen_index($personal);
            $nutzer = []; $nutzerNamen = [];
            foreach (users_load() as $u) {
                if (empty($u['active'])) continue;
                $nutzer[] = ['id' => $u['id'], 'name' => (string)$u['name'], 'vorname' => (string)($u['vorname'] ?? ''), 'nachname' => (string)($u['nachname'] ?? '')];
                $nutzerNamen[$u['id']] = (string)$u['name'];
            }
            $eintraege = []; $offen = []; $freiJe = [];
            foreach ($abw['eintraege'] as $e) {
                $p = $idx[$e['person']] ?? null;
                if (!$p) continue;
                $aus = hr_eintrag_aus($e, $p, $freiJe[$e['person']] ??= hr_freie_tage($abw['eintraege'], $e['person']));
                if ($e['status'] === 'beantragt') {
                    $aus['konto'] = hr_konto($p, $abw['eintraege'], (int)substr($e['von'], 0, 4));
                    $aus['vertretungName'] = $e['vertretung'] && isset($idx[$e['vertretung']]) ? hr_name($idx[$e['vertretung']]) : null;
                    $aus['kollegen'] = [];   // wer aus derselben Abteilung im Zeitraum ebenfalls abwesend ist
                    foreach ($abw['eintraege'] as $o) {
                        if ($o['id'] === $e['id'] || $o['person'] === $e['person'] || !in_array($o['status'], HR_AKTIV, true) || $o['bis'] < $e['von'] || $o['von'] > $e['bis']) continue;
                        $op = $idx[$o['person']] ?? null;
                        if ($op && $op['abteilung'] === $p['abteilung']) $aus['kollegen'][] = hr_name($op) . ' (' . hr_zeitraum_text(max($o['von'], $e['von']), min($o['bis'], $e['bis'])) . ')';
                    }
                    $offen[] = $aus;
                }
                if ($e['von'] <= "$jahr-12-31" && $e['bis'] >= "$jahr-01-01") $eintraege[] = $aus;
            }
            usort($offen, function ($a, $b) { return $a['von'] <=> $b['von']; });
            usort($eintraege, function ($a, $b) { return [$a['von'], $a['name']] <=> [$b['von'], $b['name']]; });
            respond(['ok' => true, 'jahr' => $jahr, 'rev' => $personal['rev'], 'heute' => hr_heute(),
                     'personen' => array_map(function ($p) use ($abw, $jahr, $nutzerNamen) { return hr_person_aus($p, $abw['eintraege'], $jahr, $nutzerNamen); }, $personal['personen']),
                     'nutzer' => $nutzer, 'offen' => $offen, 'eintraege' => $eintraege, 'sperren' => $einst['sperren'], 'ferien' => $einst['ferien'], 'arten' => HR_ARTEN]);
        }

        /* Antrag genehmigen oder ablehnen */
        case 'hr_entscheiden': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $id = s($b['id'] ?? '', 40) ?? '';
            $ent = (string)($b['entscheidung'] ?? '');
            if (!in_array($ent, ['genehmigt', 'abgelehnt'], true)) fail('Bitte genehmigen oder ablehnen.', 422);
            $grund = s($b['grund'] ?? '', 300) ?? '';
            if ($ent === 'abgelehnt' && $grund === '') fail('Bitte einen Grund für die Ablehnung angeben.', 422);
            [$e, $p] = with_lock('hr-abwesenheiten', function () use ($me, $id, $ent, $grund) {
                $abw = hr_abwesenheiten(); $idx = hr_personen_index(hr_personal());
                foreach ($abw['eintraege'] as &$e) {
                    if ($e['id'] !== $id) continue;
                    if ($e['status'] !== 'beantragt') fail('Dieser Antrag wurde bereits entschieden oder zurückgezogen.', 409);
                    $e['status'] = $ent;
                    $e['entscheidung'] = ['t' => now(), 'by' => $me['name'], 'grund' => $grund];
                    $kopie = $e;
                    unset($e);
                    hr_abwesenheiten_schreiben($abw);
                    return [$kopie, $idx[$kopie['person']] ?? null];
                }
                fail('Antrag nicht gefunden.', 404);
            });
            audit('hr', 'HR: Urlaubsantrag ' . ($p ? hr_name($p) : '') . ' ' . hr_zeitraum_text($e['von'], $e['bis']) . ' ' . $ent);
            respond(['ok' => true, 'status' => $e['status']]);
        }

        /* Eintrag der Personalstelle anlegen, ändern oder stornieren (U, K, G, freier Tag) – gilt als genehmigt */
        case 'hr_eintrag_save': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $id = s($b['id'] ?? '', 40) ?? '';
            $storno = !empty($b['stornieren']);
            $res = with_lock('hr-abwesenheiten', function () use ($me, $b, $id, $storno) {
                $abw = hr_abwesenheiten(); $idx = hr_personen_index(hr_personal());
                $i = null;
                foreach ($abw['eintraege'] as $k => $e) if ($e['id'] === $id) { $i = $k; break; }
                if ($id !== '' && $i === null) fail('Eintrag nicht gefunden.', 404);
                if ($storno) {
                    if ($i === null || !in_array($abw['eintraege'][$i]['status'], HR_AKTIV, true)) fail('Nur offene oder genehmigte Einträge lassen sich stornieren.', 409);
                    $abw['eintraege'][$i]['status'] = 'storniert';
                    $abw['eintraege'][$i]['entscheidung'] = ['t' => now(), 'by' => $me['name'], 'grund' => s($b['grund'] ?? '', 300) ?? ''];
                    hr_abwesenheiten_schreiben($abw);
                    return [$abw['eintraege'][$i], $idx[$abw['eintraege'][$i]['person']] ?? null, 'storniert'];
                }
                $p = $idx[(string)($b['person'] ?? '')] ?? null;
                if (!$p) fail('Bitte einen Mitarbeiter wählen.', 422);
                $art = (string)($b['art'] ?? '');
                if (!isset(HR_ARTEN[$art])) fail('Unbekannte Art der Abwesenheit.', 422);
                [$von, $bis] = hr_zeitraum_pruefen($b);
                if ($art !== 'X' && !hr_tage($p, $von, $bis)) fail('Im gewählten Zeitraum liegen keine Arbeitstage.', 422);
                if ($k = hr_kollision($abw['eintraege'], $p['id'], $von, $bis, $i !== null ? $id : null)) fail('Für ' . hr_name($p) . ' gibt es im Zeitraum ' . hr_zeitraum_text($k['von'], $k['bis']) . ' bereits einen Eintrag.', 409);
                $jetzt = ['t' => now(), 'by' => $me['name'], 'byId' => $me['id']];
                if ($i === null) {
                    $e = ['id' => hr_neue_id('a'), 'person' => $p['id'], 'art' => $art, 'von' => $von, 'bis' => $bis, 'status' => 'genehmigt',
                          'notiz' => s($b['notiz'] ?? '', 300) ?? '', 'vertretung' => null, 'quelle' => 'personalstelle', 'erfasst' => $jetzt];
                    $abw['eintraege'][] = $e;
                } else {
                    $e = $abw['eintraege'][$i];
                    if (!in_array($e['status'], HR_AKTIV, true)) fail('Erledigte Einträge lassen sich nicht mehr ändern.', 409);
                    if ($e['status'] === 'beantragt') fail('Offene Anträge bitte genehmigen oder ablehnen.', 409);
                    $e = array_merge($e, ['person' => $p['id'], 'art' => $art, 'von' => $von, 'bis' => $bis, 'notiz' => s($b['notiz'] ?? '', 300) ?? '', 'geaendert' => $jetzt]);
                    $abw['eintraege'][$i] = $e;
                }
                hr_abwesenheiten_schreiben($abw);
                return [$e, $p, $i === null ? 'eingetragen' : 'geändert'];
            });
            [$e, $p, $was] = $res;
            // Protokoll ohne Art der Abwesenheit (Krankheit ist ein Gesundheitsdatum)
            audit('hr', 'HR: Abwesenheit ' . ($p ? hr_name($p) : '') . ' ' . hr_zeitraum_text($e['von'], $e['bis']) . ' ' . $was);
            respond(['ok' => true, 'eintrag' => $p ? hr_eintrag_aus($e, $p) : null]);
        }

        /* Mitarbeiter anlegen oder ändern (Name, Abteilung, Reihenfolge, Konto, Arbeitstage, Anspruch und Übertrag je Jahr) */
        case 'hr_person_save': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $x = is_array($b['person'] ?? null) ? $b['person'] : fail('Ungültige Angaben.', 422);
            $vor = s($x['vorname'] ?? '', 60) ?? ''; $nach = s($x['nachname'] ?? '', 60) ?? '';
            if ($vor === '' && $nach === '') fail('Bitte einen Namen angeben.', 422);
            $at = is_array($x['arbeitstage'] ?? null) ? array_values(array_unique(array_map('intval', $x['arbeitstage']))) : [1, 2, 3, 4, 5];
            if (!$at || array_filter($at, function ($w) { return $w < 1 || $w > 7; })) fail('Bitte mindestens einen Arbeitstag wählen.', 422);
            sort($at);
            $jahre = [];
            foreach ((array)($x['jahre'] ?? []) as $j => $v) {
                if (!preg_match('/^\d{4}$/', (string)$j) || (int)$j < 2000 || (int)$j > 2100 || !is_array($v)) fail('Ungültiges Jahr beim Urlaubsanspruch.', 422);
                $zahl = function ($z, string $was, float $min) use ($j) {
                    if ($z === null || $z === '') return null;
                    if (!is_numeric($z) || (float)$z < $min || (float)$z > 100 || fmod((float)$z * 2, 1.0) != 0.0) fail("$was $j: bitte eine Zahl in ganzen oder halben Tagen angeben.", 422);
                    return (float)$z;
                };
                $jahre[(string)$j] = ['anspruch' => $zahl($v['anspruch'] ?? null, 'Urlaubsanspruch', 0), 'uebertrag' => $zahl($v['uebertrag'] ?? null, 'Übertrag', -100)];
            }
            $nutzer = ($x['nutzer'] ?? null) === null || $x['nutzer'] === '' ? null : (string)$x['nutzer'];
            if ($nutzer !== null && user_find(users_load(), $nutzer) === null) fail('Das gewählte Mitarbeiterkonto gibt es nicht.', 422);
            $id = s($x['id'] ?? '', 40) ?? '';
            $p = with_lock('hr-personal', function () use ($id, $vor, $nach, $at, $jahre, $nutzer, $x, $b) {
                $personal = hr_personal();
                if ((int)($b['rev'] ?? -1) !== $personal['rev']) fail('Die Mitarbeiterliste wurde inzwischen geändert. Bitte neu laden.', 409);
                if ($nutzer !== null) foreach ($personal['personen'] as $o) if ($o['nutzer'] === $nutzer && $o['id'] !== $id) fail('Dieses Mitarbeiterkonto ist bereits ' . hr_name($o) . ' zugeordnet.', 409);
                $neu = ['vorname' => $vor, 'nachname' => $nach, 'abteilung' => s($x['abteilung'] ?? '', 40) ?? '', 'pos' => max(0, min(9999, (int)($x['pos'] ?? 0))),
                        'nutzer' => $nutzer, 'arbeitstage' => $at, 'aktiv' => !array_key_exists('aktiv', $x) || (bool)$x['aktiv'], 'jahre' => $jahre, 'geaendert' => now()];
                if ($id === '') { $p = hr_person_norm(['id' => hr_neue_id('p')] + $neu); $personal['personen'][] = $p; }
                else {
                    $p = null;
                    foreach ($personal['personen'] as &$o) if ($o['id'] === $id) { $o = hr_person_norm(array_merge($o, $neu)); $p = $o; }
                    unset($o);
                    if (!$p) fail('Mitarbeiter nicht gefunden.', 404);
                }
                hr_personal_schreiben($personal);
                return $p;
            });
            audit('hr', 'HR: Mitarbeiter ' . hr_name($p) . ($id === '' ? ' angelegt' : ' geändert'));
            respond(['ok' => true, 'person' => $p]);
        }

        /* Urlaubssperren und Ferien */
        case 'hr_einstellungen_save': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $sperren = hr_zeitraeume_pruefen($b['sperren'] ?? [], 'Urlaubssperren');
            $ferien = hr_zeitraeume_pruefen($b['ferien'] ?? [], 'Ferien');
            with_lock('hr-einstellungen', function () use ($sperren, $ferien) {
                $d = store_read('hr-einstellungen') ?? [];
                store_write('hr-einstellungen', array_merge($d, ['rev' => (int)($d['rev'] ?? 0) + 1, 'sperren' => $sperren, 'ferien' => $ferien]));
            });
            audit('hr', 'HR: Urlaubssperren und Ferien gespeichert (' . count($sperren) . ' Sperren, ' . count($ferien) . ' Ferienzeiträume)');
            respond(['ok' => true, 'sperren' => $sperren, 'ferien' => $ferien]);
        }

        /* Excel für den Steuerberater: ausgewählte Monate eines Jahres im Aufbau der Urlaubsplanung */
        case 'hr_export': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $jahr = hr_jahr_param($b['jahr'] ?? null);
            $monate = is_array($b['monate'] ?? null) ? array_values(array_unique(array_map('intval', $b['monate']))) : [];
            sort($monate);
            if (!$monate || $monate[0] < 1 || $monate[count($monate) - 1] > 12) fail('Bitte mindestens einen Monat wählen.', 422);
            $datei = hr_xlsx(array_map(function ($m) use ($jahr) { return hr_export_monat($jahr, $m); }, $monate));
            audit('hr', 'HR: Excel-Export ' . hr_export_dateiname($jahr, $monate));
            header('Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
            header('Content-Disposition: attachment; filename="' . hr_export_dateiname($jahr, $monate) . '"');
            header('Cache-Control: private, no-store');
            header('Content-Length: ' . strlen($datei));
            echo $datei;
            exit;
        }

        /* Übernahme der bisherigen Excel-Urlaubsplanung: Vorschau und Übernahme */
        case 'hr_import_pruefen': {
            $me = require_perm('hr.verwalten', true);
            respond(['ok' => true] + hr_import_vorschau(body(), $me));
        }
        case 'hr_import_uebernehmen': {
            $me = require_perm('hr.verwalten', true);
            respond(['ok' => true] + hr_import_uebernehmen(body(), $me));
        }
}
