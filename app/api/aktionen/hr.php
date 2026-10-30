<?php
declare(strict_types=1);
/* Aktionen: HR · Urlaubsverwaltung (Oberfläche hr.intern, Logik in app/api/module/hr/)
   Rechte (GR-103): hr.antrag – eigener Urlaub, Anträge (nur wenn in Verwaltung → Urlaub eingeschaltet), Abwesenheitskalender (nur „abwesend“);
                    hr.genehmigen – Urlaubsanträge genehmigen/ablehnen, nie die eigenen (zuweisbar, z. B. eigene Rolle);
                    hr.uebersicht – Urlaubsübersicht aller Mitarbeiter, nur Summen inkl. Krank-/Gleittage (hr.verwalten sieht sie auch);
                    hr.verwalten – Personalstelle: Einträge K/G/U/freie Tage (nicht für sich selbst), Mitarbeiter, Export, Übernahme.
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
function hr_person_aus(array $p, array $eintraege, int $jahr): array
{
    return $p + ['name' => hr_name($p), 'konto' => hr_konto($p, $eintraege, $jahr)];
}

switch ($action) {
        /* Startseite: eigene Person, Urlaubskonto, eigene Einträge, Feiertage, Sperren */
        case 'hr_start': {
            $me = require_perm('hr.antrag');
            header('Cache-Control: no-store');
            $jahr = hr_jahr_param($_GET['jahr'] ?? null);
            $neuVerknuepft = false;   // früher automatische Verknüpfung beim ersten Aufruf – entfällt (nur noch die Personalstelle ordnet zu); Feld bleibt für ältere Oberflächen
            $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
            $ich = hr_ich($personal, $me);
            $verwalten = may($me, 'hr.verwalten');
            $genehmigen = may($me, 'hr.genehmigen');
            $uebersicht = $verwalten || may($me, 'hr.uebersicht');
            $eigene = [];
            if ($ich) { $frei = hr_freie_tage($abw['eintraege'], $ich['id']); foreach ($abw['eintraege'] as $e) if ($e['person'] === $ich['id']) $eigene[] = hr_eintrag_aus($e, $ich, $frei); }
            usort($eigene, function ($a, $b) { return $b['von'] <=> $a['von']; });
            $kollegen = [];
            foreach ($personal['personen'] as $p) if ($p['aktiv'] && (!$ich || $p['id'] !== $ich['id'])) $kollegen[] = ['id' => $p['id'], 'name' => hr_name($p)];
            // Zahl am Reiter „Anträge“: was der Mitarbeiter entscheiden kann (ohne eigene); Personalstelle ohne Genehmigungsrecht: alle offenen
            $offen = null;
            if ($genehmigen || $verwalten) $offen = count(array_filter($abw['eintraege'], function ($e) use ($genehmigen, $personal, $me) {
                return $e['status'] === 'beantragt' && (!$genehmigen || !hr_eigen($personal, $me, $e));
            }));
            // Korrekturmeldungen: eigene (neueste zuerst); Personalstelle zusätzlich die Zahl offener, die sie erledigen kann (ohne eigene)
            $korr = hr_korrekturen()['meldungen'];
            $eigeneIds = hr_eigene_ids($personal, $me);
            $meine = array_reverse(array_values(array_filter($korr, function ($m) use ($eigeneIds) { return isset($eigeneIds[$m['person']]); })));   // umgekehrt + stabile Sortierung: gleiche Sekunde → neueste zuerst
            usort($meine, function ($a, $b) { return strcmp($b['erfasst']['t'] ?? '', $a['erfasst']['t'] ?? ''); });
            $korrOffen = $verwalten ? count(array_filter($korr, function ($m) use ($eigeneIds) { return $m['status'] === 'offen' && !isset($eigeneIds[$m['person']]); })) : null;
            respond(['ok' => true, 'jahr' => $jahr, 'heute' => hr_heute(), 'name' => $me['name'], 'verwalten' => $verwalten, 'genehmigen' => $genehmigen, 'uebersicht' => $uebersicht, 'neuVerknuepft' => $neuVerknuepft,
                     'offen' => $offen, 'korrekturenOffen' => $korrOffen,
                     'korrekturen' => array_map(function ($m) use ($ich) { return hr_korrektur_aus($m, $ich); }, array_slice($meine, 0, 30)),
                     'ich' => $ich ? ['id' => $ich['id'], 'name' => hr_name($ich), 'abteilung' => $ich['abteilung'], 'arbeitstage' => $ich['arbeitstage']] : null,
                     'konto' => $ich ? hr_konto($ich, $abw['eintraege'], $jahr) : null, 'eintraege' => $eigene, 'kollegen' => $kollegen,
                     'feiertage' => hr_feiertage($jahr), 'sperren' => $einst['sperren'], 'uebertragBis' => $einst['uebertragBis'],
                     'antraege' => $einst['antraege']]);
        }

        /* Urlaubsübersicht: alle Mitarbeiter im Urlaubsplan mit Summen eines Jahres (Recht hr.uebersicht oder hr.verwalten).
           Nur Anzahlen – keine Zeiträume, Notizen oder Gründe (Krankheitstage sind Gesundheitsdaten). */
        case 'hr_uebersicht': {
            $me = require_auth();
            if (!may($me, 'hr.uebersicht') && !may($me, 'hr.verwalten')) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
            header('Cache-Control: no-store');
            $jahr = hr_jahr_param($_GET['jahr'] ?? null);
            // Verfallstag nur einmal als Monat-Tag (keine Datumsangaben je Mitarbeiter in der Antwort)
            respond(['ok' => true, 'jahr' => $jahr, 'heute' => hr_heute(), 'uebertragBis' => hr_uebertrag_bis(), 'zeilen' => hr_uebersicht($jahr)]);
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
                // ausgeschaltet in Verwaltung → Urlaub: der Server lehnt ab, auch wenn eine Seite den Antrag noch zeigt (GR-103)
                if (!$einst['antraege']) fail('Urlaubsanträge werden derzeit nicht über die Plattform gestellt. Bitte an die Personalstelle wenden.', 409);
                $ich = hr_ich($personal, $me);
                if (!$ich) fail('Ihr Konto ist noch keinem Mitarbeiter zugeordnet. Bitte an die Personalstelle wenden.', 409);
                if ($von < hr_heute()) fail('Urlaub kann nur für heute oder später beantragt werden. Vergangene Tage trägt die Personalstelle ein.', 422);
                $tage = hr_tage($ich, $von, $bis, null, null, hr_freie_tage($abw['eintraege'], $ich['id']));
                if (!$tage) fail('Im gewählten Zeitraum liegen keine Arbeitstage (Wochenende, Feiertag oder freier Tag).', 422);
                if ($s = hr_ueberschneidung($einst['sperren'], $von, $bis)) fail('Im Zeitraum ' . hr_zeitraum_text($s['von'], $s['bis']) . ' gilt eine Urlaubssperre' . ($s['text'] !== '' ? ' (' . $s['text'] . ')' : '') . '.', 422);
                if ($k = hr_kollision($abw['eintraege'], $ich['id'], $von, $bis, null, 'U')) fail('Für ' . hr_zeitraum_text($k['von'], $k['bis']) . ' gibt es bereits einen Eintrag.', 409);
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
                return [$e, $ich, count($tage), hr_konto($ich, $abw['eintraege'], $jahr), hr_freie_tage($abw['eintraege'], $ich['id'])];
            });
            [$e, $ich, $n, $konto, $frei] = $res;
            audit('hr', 'HR: Urlaub beantragt ' . hr_zeitraum_text($e['von'], $e['bis']) . " ($n Arbeitstage)");
            respond(['ok' => true, 'eintrag' => hr_eintrag_aus($e, $ich, $frei), 'konto' => $konto,
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

        /* Korrektur melden: Fehler in den eigenen Einträgen oder im Urlaubskonto an die Personalstelle melden.
           Text Pflicht, Zeitraum und Bezug auf einen eigenen Eintrag optional. Das Protokoll enthält den Text nicht. */
        case 'hr_korrektur': {
            $me = require_perm('hr.antrag', true);
            $b = body();
            $text = s($b['text'] ?? '', 500) ?? '';
            if (mb_strlen($text) < 3) fail('Bitte kurz beschreiben, was nicht stimmt.', 422);
            $von = null; $bis = null;
            if (($b['von'] ?? '') !== '' || ($b['bis'] ?? '') !== '') {
                $von = hr_datum($b['von'] ?? null); $bis = hr_datum(($b['bis'] ?? '') !== '' ? $b['bis'] : ($b['von'] ?? null));
                if (!$von || !$bis) fail('Bitte ein gültiges Datum wählen oder den Zeitraum leer lassen.', 422);
                if ($bis < $von) fail('Das Ende liegt vor dem Beginn.', 422);
            }
            $eintragId = s($b['eintrag'] ?? '', 40) ?? '';
            $m = with_lock('hr-korrekturen', function () use ($me, $text, $von, $bis, $eintragId) {
                $personal = hr_personal();
                $ich = hr_ich($personal, $me);
                if (!$ich) fail('Ihr Konto ist noch keinem Mitarbeiter zugeordnet. Bitte an die Personalstelle wenden.', 409);
                if ($eintragId !== '') {
                    $gef = null;
                    foreach (hr_abwesenheiten()['eintraege'] as $e) if ($e['id'] === $eintragId) { $gef = $e; break; }
                    if (!$gef || $gef['person'] !== $ich['id']) fail('Eintrag nicht gefunden.', 404);
                }
                $k = hr_korrekturen();
                $offen = count(array_filter($k['meldungen'], function ($x) use ($ich) { return $x['person'] === $ich['id'] && $x['status'] === 'offen'; }));
                if ($offen >= HR_MAX_KORREKTUREN_OFFEN) fail('Sie haben schon ' . $offen . ' offene Meldungen. Bitte warten, bis die Personalstelle sie bearbeitet hat.', 429);
                $m = ['id' => hr_neue_id('k'), 'person' => $ich['id'], 'text' => $text, 'status' => 'offen',
                      'erfasst' => ['t' => now(), 'by' => $me['name'], 'byId' => $me['id']]]
                     + ($von !== null ? ['von' => $von, 'bis' => $bis] : []) + ($eintragId !== '' ? ['eintrag' => $eintragId] : []);
                $k['meldungen'][] = $m;
                hr_korrekturen_schreiben($k);
                return hr_korrektur_aus($m, $ich);
            });
            audit('hr', 'HR: Korrektur gemeldet' . ($m['von'] ? ' (' . hr_zeitraum_text($m['von'], $m['bis']) . ')' : ''));
            respond(['ok' => true, 'meldung' => $m]);
        }

        /* Korrekturmeldung erledigen (Personalstelle) – mit optionaler Antwort für den Mitarbeiter; nie die eigene Meldung */
        case 'hr_korrektur_erledigt': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $id = s($b['id'] ?? '', 40) ?? '';
            $antwort = s($b['antwort'] ?? '', 300) ?? '';
            $m = with_lock('hr-korrekturen', function () use ($me, $id, $antwort) {
                $personal = hr_personal(); $k = hr_korrekturen();
                foreach ($k['meldungen'] as &$m) {
                    if ($m['id'] !== $id) continue;
                    if (hr_eigene_person($personal, $me, $m['person'])) fail('Ihre eigene Meldung erledigt eine andere Person der Personalstelle.', 403);
                    if ($m['status'] !== 'offen') fail('Diese Meldung ist bereits erledigt.', 409);
                    $m['status'] = 'erledigt';
                    $m['erledigt'] = ['t' => now(), 'by' => $me['name'], 'byId' => $me['id'], 'antwort' => $antwort];
                    $kopie = $m;
                    unset($m);
                    hr_korrekturen_schreiben($k);
                    return $kopie;
                }
                fail('Meldung nicht gefunden.', 404);
            });
            $p = hr_personen_index(hr_personal())[$m['person']] ?? null;
            audit('hr', 'HR: Korrekturmeldung erledigt (' . ($p ? hr_name($p) : 'ehemaliger Mitarbeiter') . ')');
            respond(['ok' => true, 'meldung' => hr_korrektur_aus($m, $p)]);
        }

        /* Personalstelle: Mitarbeiter mit Konten, offene Anträge, alle Einträge des Jahres, Einstellungen */
        case 'hr_verwaltung': {
            $me = require_perm('hr.verwalten');
            header('Cache-Control: no-store');
            $jahr = hr_jahr_param($_GET['jahr'] ?? null);
            $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
            $idx = hr_personen_index($personal);
            $eintraege = []; $freiJe = [];
            foreach ($abw['eintraege'] as $e) {
                $p = $idx[$e['person']] ?? null;
                if (!$p) continue;
                if ($e['von'] <= "$jahr-12-31" && $e['bis'] >= "$jahr-01-01") $eintraege[] = hr_eintrag_aus($e, $p, $freiJe[$e['person']] ??= hr_freie_tage($abw['eintraege'], $e['person'])) + ['eigen' => hr_eigen($personal, $me, $e)];
            }
            $offen = hr_offene_antraege($personal, $abw, $me);
            usort($eintraege, function ($a, $b) { return [$a['von'], $a['name']] <=> [$b['von'], $b['name']]; });
            // Korrekturmeldungen: alle offenen und die in den letzten 60 Tagen erledigten (offene zuerst, dann neueste)
            $grenze = gmdate('Y-m-d', time() - 60 * 86400);
            $korr = array_reverse(array_values(array_filter(hr_korrekturen()['meldungen'], function ($m) use ($grenze) {
                return $m['status'] === 'offen' || substr((string)($m['erledigt']['t'] ?? ''), 0, 10) >= $grenze;
            })));
            usort($korr, function ($a, $b) { return [$a['status'] === 'offen' ? 0 : 1, $b['erfasst']['t'] ?? ''] <=> [$b['status'] === 'offen' ? 0 : 1, $a['erfasst']['t'] ?? '']; });
            $eigeneIds = hr_eigene_ids($personal, $me);
            $korrAus = array_map(function ($m) use ($idx, $eigeneIds) { return hr_korrektur_aus($m, $idx[$m['person']] ?? null) + ['eigen' => isset($eigeneIds[$m['person']])]; }, $korr);
            respond(['ok' => true, 'jahr' => $jahr, 'rev' => $personal['rev'], 'heute' => hr_heute(), 'korrekturen' => $korrAus,
                     'personen' => array_map(function ($p) use ($abw, $jahr) { return hr_person_aus($p, $abw['eintraege'], $jahr); }, $personal['personen']),
                     'offen' => $offen, 'eintraege' => $eintraege, 'sperren' => $einst['sperren'], 'ferien' => $einst['ferien'], 'arten' => HR_ARTEN]);
        }

        /* Offene Urlaubsanträge für Mitarbeiter mit dem Recht „Urlaub genehmigen“ (ohne Personalstelle):
           nur Urlaubsanträge, keine Krankheiten oder anderen Abwesenheitsgründe, eigene Anträge als „eigen“ markiert */
        case 'hr_offen': {
            $me = require_perm('hr.genehmigen');
            header('Cache-Control: no-store');
            respond(['ok' => true, 'heute' => hr_heute(), 'offen' => hr_offene_antraege(hr_personal(), hr_abwesenheiten(), $me)]);
        }

        /* Antrag genehmigen oder ablehnen – Recht hr.genehmigen, nie der eigene Antrag (auch nicht als Administrator) */
        case 'hr_entscheiden': {
            $me = require_perm('hr.genehmigen', true);
            $b = body();
            $id = s($b['id'] ?? '', 40) ?? '';
            $ent = (string)($b['entscheidung'] ?? '');
            if (!in_array($ent, ['genehmigt', 'abgelehnt'], true)) fail('Bitte genehmigen oder ablehnen.', 422);
            $grund = s($b['grund'] ?? '', 300) ?? '';
            if ($ent === 'abgelehnt' && $grund === '') fail('Bitte einen Grund für die Ablehnung angeben.', 422);
            [$e, $p] = with_lock('hr-abwesenheiten', function () use ($me, $id, $ent, $grund) {
                $abw = hr_abwesenheiten(); $personal = hr_personal(); $idx = hr_personen_index($personal);
                foreach ($abw['eintraege'] as &$e) {
                    if ($e['id'] !== $id) continue;
                    if (hr_eigen($personal, $me, $e)) fail('Über den eigenen Antrag entscheidet eine andere Person mit dem Recht „Urlaub genehmigen“.', 403);
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

        /* Eintrag der Personalstelle anlegen, ändern oder stornieren (U, K, G, freier Tag) – gilt als genehmigt.
           Nie für sich selbst (Vier-Augen-Prinzip): sonst könnte sich die Personalstelle Urlaub ohne Genehmigung eintragen. */
        case 'hr_eintrag_save': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $id = s($b['id'] ?? '', 40) ?? '';
            $storno = !empty($b['stornieren']);
            $res = with_lock('hr-abwesenheiten', function () use ($me, $b, $id, $storno) {
                $abw = hr_abwesenheiten(); $personal = hr_personal(); $idx = hr_personen_index($personal);
                $i = null;
                foreach ($abw['eintraege'] as $k => $e) if ($e['id'] === $id) { $i = $k; break; }
                if ($id !== '' && $i === null) fail('Eintrag nicht gefunden.', 404);
                $selbst = 'Eigene Abwesenheiten trägt eine andere Person der Personalstelle ein; Urlaub bitte beantragen.';
                if ($i !== null && hr_eigene_person($personal, $me, $abw['eintraege'][$i]['person'])) fail($selbst, 403);
                if (!$storno && hr_eigene_person($personal, $me, (string)($b['person'] ?? ''))) fail($selbst, 403);
                if ($storno) {
                    if ($i === null || !in_array($abw['eintraege'][$i]['status'], HR_AKTIV, true)) fail('Nur offene oder genehmigte Einträge lassen sich stornieren.', 409);
                    $abw['eintraege'][$i]['status'] = 'storniert';
                    $abw['eintraege'][$i]['entscheidung'] = ['t' => now(), 'by' => $me['name'], 'grund' => s($b['grund'] ?? '', 300) ?? ''];
                    hr_abwesenheiten_schreiben($abw);
                    return [$abw['eintraege'][$i], $idx[$abw['eintraege'][$i]['person']] ?? null, 'storniert', hr_freie_tage($abw['eintraege'], $abw['eintraege'][$i]['person'])];
                }
                $p = $idx[(string)($b['person'] ?? '')] ?? null;
                if (!$p) fail('Bitte einen Mitarbeiter wählen.', 422);
                $art = (string)($b['art'] ?? '');
                if (!isset(HR_ARTEN[$art])) fail('Unbekannte Art der Abwesenheit.', 422);
                [$von, $bis] = hr_zeitraum_pruefen($b);
                if ($art !== 'X' && !hr_tage($p, $von, $bis)) fail('Im gewählten Zeitraum liegen keine Arbeitstage.', 422);
                if ($k = hr_kollision($abw['eintraege'], $p['id'], $von, $bis, $i !== null ? $id : null, $art)) fail('Für ' . hr_name($p) . ' gibt es im Zeitraum ' . hr_zeitraum_text($k['von'], $k['bis']) . ' bereits einen Eintrag.', 409);
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
                    if ($art !== 'K') unset($e['urlaubAbzug']);   // „vom Urlaub abgezogen“ gilt nur für Krankheit aus der Zeiterfassung
                    $abw['eintraege'][$i] = $e;
                }
                hr_abwesenheiten_schreiben($abw);
                return [$e, $p, $i === null ? 'eingetragen' : 'geändert', hr_freie_tage($abw['eintraege'], $p['id'])];
            });
            [$e, $p, $was, $frei] = $res;
            // Protokoll ohne Art der Abwesenheit (Krankheit ist ein Gesundheitsdatum)
            audit('hr', 'HR: Abwesenheit ' . ($p ? hr_name($p) : '') . ' ' . hr_zeitraum_text($e['von'], $e['bis']) . ' ' . $was);
            respond(['ok' => true, 'eintrag' => $p ? hr_eintrag_aus($e, $p, $frei) : null]);
        }

        /* Verwaltung → Mitarbeiter: HR-Angaben aller Mitarbeiter mit Urlaubskonto, Urlaubssperren, Ferien (Personalstelle).
           Oberfläche wie die Mitarbeiterverwaltung (Eingabebereich der Verwaltung). */
        case 'mitarbeiter_hr': {
            $me = require_perm('hr.verwalten');
            header('Cache-Control: no-store');
            $jahr = hr_jahr_param($_GET['jahr'] ?? null);
            $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
            respond(['ok' => true, 'jahr' => $jahr, 'rev' => $personal['rev'], 'uebertragBis' => $einst['uebertragBis'], 'antraege' => $einst['antraege'],
                     'personen' => array_map(function ($p) use ($abw, $jahr) { return hr_person_aus($p, $abw['eintraege'], $jahr); }, $personal['personen']),
                     'sperren' => $einst['sperren'], 'ferien' => $einst['ferien']]);
        }

        /* HR-Angaben eines Mitarbeiters: Abteilung, Position, Arbeitstage, im Urlaubsplan, Anspruch und Übertrag eines Jahres */
        case 'mitarbeiter_hr_save': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $uid = (string)($b['nutzer'] ?? '');
            $users = users_load();
            $ui = user_find($users, $uid);
            if ($ui === null) fail('Mitarbeiter nicht gefunden.', 404);
            $werte = [];
            if (array_key_exists('abteilung', $b)) $werte['abteilung'] = s($b['abteilung'], 40) ?? '';
            if (array_key_exists('pos', $b)) $werte['pos'] = max(0, min(9999, (int)$b['pos']));
            if (array_key_exists('aktiv', $b)) $werte['aktiv'] = (bool)$b['aktiv'];
            if (array_key_exists('personalnummer', $b)) {
                // Mitarbeiternummer der Zeiterfassung (Zuordnung beim Import), eindeutig
                $nr = trim((string)(s($b['personalnummer'], 20) ?? ''));
                if ($nr !== '' && !preg_match('/^[A-Za-z0-9._\/-]{1,20}$/', $nr)) fail('Personalnummer: bitte nur Ziffern, Buchstaben, Punkt, Bindestrich oder Schrägstrich.', 422);
                $werte['personalnummer'] = $nr;
            }
            if (array_key_exists('arbeitstage', $b)) {
                $at = is_array($b['arbeitstage']) ? array_values(array_unique(array_map('intval', $b['arbeitstage']))) : [];
                if (!$at || array_filter($at, function ($w) { return $w < 1 || $w > 7; })) fail('Bitte mindestens einen Arbeitstag wählen.', 422);
                sort($at);
                $werte['arbeitstage'] = $at;
            }
            $jahr = null; $jv = null;
            if (array_key_exists('jahr', $b)) {
                $jahr = hr_jahr_param($b['jahr']);
                $zahl = function ($z, string $was, float $min) use ($jahr) {
                    if ($z === null || $z === '') return null;
                    if (!is_numeric($z) || (float)$z < $min || (float)$z > 100 || fmod((float)$z * 2, 1.0) != 0.0) fail("$was $jahr: bitte eine Zahl in ganzen oder halben Tagen angeben.", 422);
                    return (float)$z;
                };
                $jv = ['anspruch' => $zahl($b['anspruch'] ?? null, 'Urlaubsanspruch', 0), 'uebertrag' => $zahl($b['uebertrag'] ?? null, 'Übertrag', -100)];
            }
            $p = with_lock('hr-personal', function () use ($b, $uid, $users, $ui, &$werte, &$jahr, &$jv, $me) {
                $roh = hr_personal_roh();
                if ((int)($b['rev'] ?? -1) !== $roh['rev']) fail('Die Mitarbeiterliste wurde inzwischen geändert. Bitte neu laden.', 409);
                // Vier-Augen-Prinzip: die eigenen Urlaubsangaben (Anspruch, Übertrag, Arbeitstage, im Urlaubsplan, Personalnummer –
                // sie bestimmt die Zuordnung beim Import) ändert eine andere Person der Personalstelle. Abteilung und Position
                // (Reihenfolge im Plan) sind ohne Einfluss auf das Urlaubskonto und bleiben erlaubt. Unveränderte Werte (der
                // Dialog schickt immer alle Felder) werden still übergangen, damit z. B. der eigene Name änderbar bleibt.
                if ($uid === (string)$me['id']) hr_eigene_angaben_pruefen($werte, $jahr, $jv, $uid, $users[$ui]);
                if (($werte['personalnummer'] ?? '') !== '') {
                    foreach (hr_personal()['personen'] as $x) {
                        if ($x['nutzer'] !== $uid && ($x['personalnummer'] ?? '') === $werte['personalnummer']) fail('Die Personalnummer ' . $werte['personalnummer'] . ' hat schon ' . hr_name($x)
                            . (!empty($x['altbestand']) ? ' (Urlaubsliste ohne Mitarbeiter). Diesen Eintrag bitte über „Einzeln zuordnen“ mit dem Mitarbeiter zusammenführen – die Personalnummer kommt dann mit.' : '.'), 409);
                    }
                }
                if ($jahr !== null) {
                    $jahre = [];
                    foreach ($roh['personen'] as $e) if ($e['nutzer'] === $uid) $jahre = $e['jahre'];
                    $jahre[(string)$jahr] = $jv;
                    $werte['jahre'] = $jahre;
                }
                $p = hr_angaben_setzen($roh, $uid, $werte, $users[$ui]);
                hr_personal_schreiben($roh);
                return $p;
            });
            audit('hr', 'HR: Angaben von ' . $users[$ui]['name'] . ' geändert');
            $personal = hr_personal(); $abw = hr_abwesenheiten();
            foreach ($personal['personen'] as $x) if ($x['nutzer'] === $uid) respond(['ok' => true, 'rev' => $personal['rev'], 'person' => hr_person_aus($x, $abw['eintraege'], $jahr ?? (int)date('Y'))]);
            respond(['ok' => true, 'rev' => $personal['rev']]);
        }

        /* Einträge der Urlaubsliste ohne Mitarbeiter (Altbestand) in die Mitarbeiter übernehmen */
        /* Einen Eintrag der Urlaubsliste ohne Mitarbeiter von Hand einem Mitarbeiter zuordnen (auch bei anderem Namen
           und wenn der Mitarbeiter schon HR-Angaben hat: zusammenführen, hr_altbestand_zusammenfuehren) */
        case 'hr_altbestand_zuordnen': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $eintrag = s($b['eintrag'] ?? '', 60) ?? '';
            $users = users_load();
            $ui = user_find($users, (string)($b['nutzer'] ?? ''));
            if ($ui === null) fail('Bitte einen Mitarbeiter wählen.', 422);
            $u = $users[$ui];
            // Vier-Augen-Prinzip: Einträge (mit Urlaub und Abwesenheiten) sich selbst zuordnen darf nur eine andere Person
            if ((string)$u['id'] === (string)$me['id']) fail('Einträge der Urlaubsliste ordnet Ihnen eine andere Person der Personalstelle zu.', 403);
            [$p, $n, $doppelt, $name] = with_lock('hr-personal', function () use ($b, $eintrag, $u) {
                $roh = hr_personal_roh();
                if ((int)($b['rev'] ?? -1) !== $roh['rev']) fail('Die Mitarbeiterliste wurde inzwischen geändert. Bitte neu laden.', 409);
                $name = '';
                foreach ($roh['personen'] as $x) if ($x['id'] === $eintrag) $name = hr_name($x);
                try { [$p, $n, $doppelt] = hr_altbestand_zusammenfuehren($roh, $eintrag, $u); }
                catch (InvalidArgumentException $ex) { fail($ex->getMessage(), 404); }
                catch (HrZuordnungFehler $ex) { fail($ex->getMessage(), 409); }
                hr_personal_schreiben($roh);
                return [$p, $n, $doppelt, $name];
            });
            audit('hr', 'HR: Eintrag der Urlaubsliste „' . $name . '“ dem Mitarbeiter ' . $u['name'] . ' zugeordnet (' . $n . ' Abwesenheiten' . ($doppelt ? ", $doppelt doppelte storniert" : '') . ')');
            $personal = hr_personal();
            respond(['ok' => true, 'rev' => $personal['rev'], 'abwesenheiten' => $n, 'doppelt' => $doppelt]);
        }

        case 'hr_personal_uebernehmen': {
            $me = require_perm('hr.verwalten', true);
            $text = hr_personal_uebernehmen($me);
            respond(['ok' => true, 'anzahl' => count($text), 'text' => $text]);
        }

        /* Urlaubssperren und Ferien */
        case 'hr_einstellungen_save': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $sperren = hr_zeitraeume_pruefen($b['sperren'] ?? [], 'Urlaubssperren');
            $ferien = hr_zeitraeume_pruefen($b['ferien'] ?? [], 'Ferien');
            // Verfallstag des Resturlaubs (optional; ohne Angabe bleibt der gespeicherte Wert)
            $bis = null;
            if (array_key_exists('uebertragBis', $b)) {
                $bis = hr_uebertrag_bis_norm($b['uebertragBis']);
                if ($bis === null) fail('Verfallstag des Resturlaubs: bitte ein gültiges Datum wählen (der 29.02. ist nicht möglich, weil es ihn nicht jedes Jahr gibt).', 422);
            }
            $vorher = hr_einstellungen()['uebertragBis'];
            with_lock('hr-einstellungen', function () use ($sperren, $ferien, $bis) {
                $d = store_read('hr-einstellungen') ?? [];
                store_write('hr-einstellungen', array_merge($d, ['rev' => (int)($d['rev'] ?? 0) + 1, 'sperren' => $sperren, 'ferien' => $ferien],
                                                            $bis !== null ? ['uebertragBis' => $bis] : []));
            });
            audit('hr', 'HR: Urlaubssperren und Ferien gespeichert (' . count($sperren) . ' Sperren, ' . count($ferien) . ' Ferienzeiträume)');
            if ($bis !== null && $bis !== $vorher) audit('hr', 'HR: Verfallstag Resturlaub auf ' . substr($bis, 3, 2) . '.' . substr($bis, 0, 2) . '. geändert (vorher ' . substr($vorher, 3, 2) . '.' . substr($vorher, 0, 2) . '.)');
            respond(['ok' => true, 'sperren' => $sperren, 'ferien' => $ferien, 'uebertragBis' => hr_uebertrag_bis(true)]);
        }

        /* Urlaubsanträge über die Plattform ein- oder ausschalten (Schalter in Verwaltung → Urlaub, sofort wirksam).
           Ändert nur das Feld antraege in hr-einstellungen; Sperren, Ferien und Verfallstag bleiben. */
        case 'hr_antraege_save': {
            $me = require_perm('hr.verwalten', true);
            $an = body()['an'] ?? null;
            if (!is_bool($an)) fail('Bitte „an“ (ja/nein) angeben.', 422);
            $vorher = with_lock('hr-einstellungen', function () use ($an) {
                $d = store_read('hr-einstellungen') ?? [];
                $alt = ($d['antraege'] ?? true) !== false;
                if ($alt !== $an) store_write('hr-einstellungen', array_merge($d, ['rev' => (int)($d['rev'] ?? 0) + 1, 'antraege' => $an]));
                return $alt;
            });
            if ($vorher !== $an) audit('hr', 'HR: Urlaubsanträge über die Plattform ' . ($an ? 'eingeschaltet' : 'ausgeschaltet'));
            respond(['ok' => true, 'antraege' => $an]);
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
