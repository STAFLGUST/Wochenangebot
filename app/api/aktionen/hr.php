<?php
declare(strict_types=1);
/* Aktionen: HR · Urlaubsverwaltung (Oberfläche hr.intern, Logik in app/api/module/hr/)
   Rechte (GR-103): hr.antrag – eigener Urlaub und Gleittage, Anträge (nur wenn in Verwaltung → Urlaub eingeschaltet; Gleittage nur mit Rest
                    auf dem Gleittage-Konto), Abwesenheitskalender (nur „abwesend“);
                    hr.genehmigen – Urlaubsanträge genehmigen/ablehnen, nie die eigenen (zuweisbar, z. B. eigene Rolle);
                    hr.uebersicht – Urlaubsübersicht aller Mitarbeiter, nur Summen inkl. Krank-/Gleittage (hr.verwalten sieht sie auch);
                    hr.verwalten – Personalstelle: Einträge K/G/U/freie Tage (nicht für sich selbst), Mitarbeiter, Gleittage gewähren
                    (hr_gleittage_save, nicht für sich selbst), Export, Übernahme.
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
    return array_merge($p, ['name' => hr_name($p), 'konto' => hr_konto($p, $eintraege, $jahr), 'gleitKonto' => hr_gleit_konto($p, $eintraege, $jahr),
                            'gleittage' => hr_gleit_aus($p, true)]);
}

/* Einstellungen für Verwaltung → Urlaub: eingetragene Sperren (zum Bearbeiten), Sperren aus den Regeln (nur Anzeige, dieses
   und nächstes Jahr), Schalter, Ferien, Urlaubsregeln mit Vorlage */
function hr_einstellungen_aus(array $einst): array
{
    $j = (int)date('Y');
    return ['sperren' => $einst['sperrenEigene'], 'regelSperren' => $einst['regelSperren'], 'schliesstage' => $einst['schliesstage'],
            'sperrenAuto' => array_merge(hr_regel_sperren($j, $einst['schliesstage']), hr_regel_sperren($j + 1, $einst['schliesstage'])),
            'ferien' => $einst['ferien'], 'regeln' => $einst['regeln'], 'regelnStandard' => HR_REGELN_STANDARD, 'verfallAb' => $einst['verfallAb'],
            'planung' => array_diff_key(hr_planung_einst(), ['abschluss' => true]), 'ueberziehenMax' => $einst['ueberziehenMax'], 'amStueckMax' => $einst['amStueckMax']];
}

switch ($action) {
        /* Startseite: eigene Person, Urlaubskonto, eigene Einträge, Feiertage, Sperren */
        case 'hr_start': {
            $me = require_perm('hr.antrag');
            hr_mail_anstossen();   // automatische HR-Mails (Monatsübersicht, Steuerberater), versendet nach der Antwort
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
                     'gleitKonto' => $ich ? hr_gleit_konto($ich, $abw['eintraege'], $jahr) : null, 'gleittage' => $ich ? hr_gleit_aus($ich) : [],
                     'feiertage' => hr_feiertage($jahr), 'schliesstage' => (object)(hr_schliesstage($jahr) + hr_schliesstage($jahr + 1)),
                     'sperren' => $einst['sperren'], 'uebertragBis' => $einst['uebertragBis'],
                     'antraege' => $einst['antraege'], 'regeln' => $einst['regeln'],
                     // Jahresplanung: Stand des Mitarbeiters nur in der Planungsphase; Vertretung Pflicht bei Urlaubsanträgen
                     'planung' => hr_planung_ich($ich, $abw['eintraege']), 'vertretungPflicht' => hr_planung_einst()['vertretungPflicht'],
                     // feste Vertretung aus den Stammdaten (im Antrag gesperrt) und wen der Mitarbeiter vertritt („Sie vertreten“)
                     'festeVertretung' => $ich && ($fv = hr_feste_vertretung($ich, $personal)) ? ['id' => $fv['id'], 'name' => hr_name($fv)] : null,
                     'vertretungen' => $ich ? hr_meine_vertretungen($ich, $personal, $abw['eintraege']) : [],
                     // Vorplanung (Schalter bei „Urlaub beantragen“): Jahr, Stichtag, höchstens unverplante Tage, Grenze der einzelnen
                     // Urlaubstage; Urlaub am Stück höchstens (gilt für jeden Urlaubsantrag)
                     'amStueckMax' => $einst['amStueckMax'],
                     'vorplanung' => (function () { $pe = hr_planung_einst(); $j = hr_planung_jahr(null, $pe);
                         return ['jahr' => $j, 'stichtag' => hr_planung_daten($pe, $j)['stichtag'], 'unverplantMax' => $pe['unverplantMax'], 'einzeltageMax' => $pe['einzeltageMax'], 'max' => HR_VORPLANUNG_MAX]; })()]);
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
            hr_mail_anstossen();
            header('Cache-Control: no-store');
            $jahr = hr_jahr_param($_GET['jahr'] ?? null);
            $monat = (int)($_GET['monat'] ?? date('n'));
            if ($monat < 1 || $monat > 12) fail('Ungültiger Monat.', 422);
            respond(['ok' => true, 'voll' => may($me, 'hr.verwalten')] + hr_monat($jahr, $monat, $me, may($me, 'hr.verwalten')));
        }

        /* Antrag stellen (eigene Person): Urlaub (art U, Standard) oder Gleittag (art G, nur soweit das Gleittage-Konto reicht) */
        case 'hr_antrag': {
            $me = require_perm('hr.antrag', true);
            $b = body();
            [$von, $bis] = hr_zeitraum_pruefen($b);
            $art = (string)($b['art'] ?? 'U');
            if (!in_array($art, ['U', 'G'], true)) fail('Beantragen lassen sich Urlaub und Gleittage.', 422);
            if ($art === 'G' && substr($von, 0, 4) !== substr($bis, 0, 4)) fail('Gleittage bitte je Kalenderjahr beantragen.', 422);
            $notiz = s($b['notiz'] ?? '', 300) ?? '';
            $res = with_lock('hr-abwesenheiten', function () use ($me, $von, $bis, $notiz, $b, $art) {
                $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
                // ausgeschaltet in Verwaltung → Urlaub: der Server lehnt ab, auch wenn eine Seite den Antrag noch zeigt (GR-103)
                if (!$einst['antraege']) fail('Urlaubsanträge werden derzeit nicht über die Plattform gestellt. Bitte an die Personalstelle wenden.', 409);
                $ich = hr_ich($personal, $me);
                if (!$ich) fail('Ihr Konto ist noch keinem Mitarbeiter zugeordnet. Bitte an die Personalstelle wenden.', 409);
                // gemeinsame Prüfung mit Vorplanung und Vorschau – auch ob die Vertretung da ist (Inhaber 10.11.2026)
                // feste Vertretung (Stammdaten) und optionale zusätzliche – beide müssen da sein (Inhaber 10.11.2026)
                $z = hr_antrag_zeitraum($ich, $personal, $abw['eintraege'], $einst, $art, $von, $bis, $b['vertretung'] ?? null, [], $b['vertretung2'] ?? null);
                if ($z['fehler'] !== null) fail($z['fehler'], $z['code']);
                // genug Urlaubstage? Über der Grenze der Personalstelle: abgelehnt; darunter nur mit Bestätigung (Inhaber 10.11.2026)
                $ue = $art === 'U' ? hr_ueberzug($ich, $abw['eintraege'], [['art' => 'U', 'von' => $von, 'bis' => $bis]]) : ['tage' => 0.0];
                if ($ue['tage'] > $einst['ueberziehenMax']) fail(hr_ueberzug_text($ue, $einst['ueberziehenMax']), 409);
                if ($ue['tage'] > 0 && ($b['ueberziehen'] ?? false) !== true) return ['bestaetigen' => $ue + ['max' => $einst['ueberziehenMax'], 'text' => hr_ueberzug_text($ue, $einst['ueberziehenMax'])]];
                $e = ['id' => hr_neue_id('a'), 'person' => $ich['id'], 'art' => $art, 'von' => $von, 'bis' => $bis, 'status' => 'beantragt', 'notiz' => $notiz,
                      'vertretung' => $z['vertretung']['id'] ?? null, 'quelle' => 'antrag', 'erfasst' => ['t' => now(), 'by' => $me['name'], 'byId' => $me['id']]]
                    + (isset($z['vertretung2']['id']) ? ['vertretung2' => $z['vertretung2']['id']] : []);
                $abw['eintraege'][] = $e;
                hr_abwesenheiten_schreiben($abw);
                $jahr = (int)substr($von, 0, 4);
                return [$e, $ich, $z, hr_konto($ich, $abw['eintraege'], $jahr), hr_freie_tage($abw['eintraege'], $ich['id']), hr_gleit_konto($ich, $abw['eintraege'], $jahr),
                        hr_einzeltage_hinweis($ich, $abw['eintraege'], $e), $personal, $abw['eintraege'], $ue];
            });
            if (isset($res['bestaetigen'])) respond(['ok' => false, 'error' => $res['bestaetigen']['text'], 'bestaetigen' => $res['bestaetigen']], 409);
            [$e, $ich, $z, $konto, $frei, $gleit, $einzelHinweis, $personal, $alle, $ue] = $res;
            $vertHinweis = hr_vertretung_benachrichtigen($ich, [$e], $personal, $alle, $me);   // E-Mail an die Vertretung(en) nach der Antwort
            audit('hr', 'HR: ' . ($e['art'] === 'G' ? 'Gleittag' : 'Urlaub') . ' beantragt ' . hr_zeitraum_text($e['von'], $e['bis']) . ' (' . hr_zahl_text($z['tage']) . ' Arbeitstage'
                . ($ue['tage'] > 0 ? ', ' . hr_zahl_text($ue['tage']) . ' über den verfügbaren Tagen – bestätigt' : '') . ')');
            // Hinweise (der Antrag gilt trotzdem): über dem Resturlaub; Vertretung arbeitet an Tagen nicht; mehr Einzeltage als vorgesehen
            $hinweise = [];
            if ($e['art'] === 'U' && $konto['verfuegbar'] < 0) $hinweise[] = 'Der Antrag übersteigt Ihren Resturlaub um ' . hr_zahl_text(-$konto['verfuegbar']) . ' Tage – die Personalstelle entscheidet.';
            $hinweise = array_merge($hinweise, $z['hinweise'], $einzelHinweis ? [$einzelHinweis] : [], $vertHinweis ? [$vertHinweis] : []);
            respond(['ok' => true, 'eintrag' => hr_eintrag_aus($e, $ich, $frei), 'konto' => $konto, 'gleitKonto' => $gleit, 'hinweis' => $hinweise ? implode(' ', $hinweise) : null]);
        }

        /* Eigenen Antrag zurückziehen (offen oder genehmigt, solange er noch nicht begonnen hat) */
        /* Vorschau eines Antrags oder einer Vorplanung (speichert nichts): je Zeitraum Tage, Ablehnungsgrund, Hinweise und ob die
           Vertretung da ist; bei der Vorplanung dazu der Stand des Jahres mit diesen Zeiträumen (Ziel, Einzeltage, 24./31.12.).
           Nur Genehmigtes anderer (wie im Kalender) – nie offene Anträge oder Gründe. */
        case 'hr_antrag_pruefen': {
            $me = require_perm('hr.antrag', true);
            $b = body();
            $art = (string)($b['art'] ?? 'U');
            if (!in_array($art, ['U', 'G'], true)) fail('Beantragen lassen sich Urlaub und Gleittage.', 422);
            $vor = ($b['vorplanung'] ?? false) === true;
            // Vorplanung ohne Zeitraum: nur der Stand des Jahres (leere Zeilen beim Öffnen)
            try { $zr = $vor && ($b['zeitraeume'] ?? null) === [] ? [] : hr_zeitraeume_anfrage($b['zeitraeume'] ?? null); } catch (InvalidArgumentException $ex) { fail($ex->getMessage(), 422); }
            $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
            $ich = hr_ich($personal, $me);
            if (!$ich) fail('Ihr Konto ist noch keinem Mitarbeiter zugeordnet. Bitte an die Personalstelle wenden.', 409);
            if ($vor) {
                if ($art !== 'U') fail('Die Vorplanung gilt für Urlaub.', 422);
                $pe = hr_planung_einst(); $jahr = hr_planung_jahr(null, $pe);
                [$erg, $gut] = hr_vorplanung_pruefen($ich, $personal, $abw['eintraege'], $einst, $zr, $jahr);
                $stand = hr_planung_person($ich, $abw['eintraege'], $jahr, $pe, $gut);
                $konto = hr_konto($ich, $abw['eintraege'], $jahr);
                $neu = array_sum(array_map(function ($e) { return $e['fehler'] === null ? $e['tage'] : 0; }, $erg));
                $ue = hr_ueberzug($ich, $abw['eintraege'], array_map(function ($z) { return ['art' => 'U', 'von' => $z['von'], 'bis' => $z['bis']]; }, $gut));
                respond(['ok' => true, 'jahr' => $jahr, 'zeitraeume' => $erg, 'stand' => $stand + ['jahr' => $jahr, 'stichtag' => hr_planung_daten($pe, $jahr)['stichtag']],
                         'verfuegbarDanach' => $konto['verfuegbar'] - $neu, 'ueberzug' => $ue['tage'], 'ueberziehenMax' => $einst['ueberziehenMax'],
                         'ueberzugText' => $ue['tage'] > 0 ? hr_ueberzug_text($ue, $einst['ueberziehenMax']) : null]);
            }
            if (count($zr) !== 1) fail('Bitte einen Zeitraum angeben.', 422);
            $z = hr_antrag_zeitraum($ich, $personal, $abw['eintraege'], $einst, $art, $zr[0]['von'], $zr[0]['bis'], $zr[0]['vertretung'], [], $zr[0]['vertretung2']);
            // genug Urlaubstage? über der Grenze: Ablehnungsgrund; darunter: Rückfrage beim Absenden (Inhaber 10.11.2026)
            $ue = $art === 'U' ? hr_ueberzug($ich, $abw['eintraege'], [['art' => 'U', 'von' => $zr[0]['von'], 'bis' => $zr[0]['bis']]]) : ['tage' => 0.0];
            $z['ueberzug'] = $ue['tage']; $z['ueberziehenMax'] = $einst['ueberziehenMax'];
            if ($ue['tage'] > 0) {
                $z['ueberzugText'] = hr_ueberzug_text($ue, $einst['ueberziehenMax']);
                if ($ue['tage'] > $einst['ueberziehenMax'] && $z['fehler'] === null) { $z['fehler'] = $z['ueberzugText']; $z['code'] = 409; }
            }
            respond(['ok' => true, 'zeitraeume' => [$z]]);
        }

        /* Vorplanung (Inhaber 10.11.2026): mehrere Urlaubszeiträume des nächsten Jahres auf einmal beantragen – jeder geprüft wie
           ein einzelner Antrag; ist einer nicht in Ordnung, wird nichts gespeichert (Antwort mit dem Ergebnis je Zeitraum). */
        case 'hr_vorplanung': {
            $me = require_perm('hr.antrag', true);
            $b = body();
            try { $zr = hr_zeitraeume_anfrage($b['zeitraeume'] ?? null); } catch (InvalidArgumentException $ex) { fail($ex->getMessage(), 422); }
            $notiz = s($b['notiz'] ?? '', 300) ?? '';
            $bestaetigt = ($b['ueberziehen'] ?? false) === true;
            $res = with_lock('hr-abwesenheiten', function () use ($me, $zr, $notiz, $bestaetigt) {
                $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
                if (!$einst['antraege']) fail('Urlaubsanträge werden derzeit nicht über die Plattform gestellt. Bitte an die Personalstelle wenden.', 409);
                $ich = hr_ich($personal, $me);
                if (!$ich) fail('Ihr Konto ist noch keinem Mitarbeiter zugeordnet. Bitte an die Personalstelle wenden.', 409);
                $jahr = hr_planung_jahr();
                [$erg, $gut] = hr_vorplanung_pruefen($ich, $personal, $abw['eintraege'], $einst, $zr, $jahr);
                if (count($gut) !== count($zr)) return ['fehler' => true, 'zeitraeume' => $erg];
                // genug Urlaubstage für alle Zeilen zusammen? (wie beim einzelnen Antrag, Inhaber 10.11.2026)
                $ue = hr_ueberzug($ich, $abw['eintraege'], array_map(function ($z) { return ['art' => 'U', 'von' => $z['von'], 'bis' => $z['bis']]; }, $zr));
                if ($ue['tage'] > $einst['ueberziehenMax']) return ['fehler' => true, 'zeitraeume' => $erg, 'ueberzug' => hr_ueberzug_text($ue, $einst['ueberziehenMax']) . ' Es wurde nichts beantragt.'];
                if ($ue['tage'] > 0 && $bestaetigt !== true) return ['bestaetigen' => $ue + ['max' => $einst['ueberziehenMax'], 'text' => hr_ueberzug_text($ue, $einst['ueberziehenMax'])]];
                $neu = [];
                foreach ($zr as $i => $z) {
                    $neu[] = $abw['eintraege'][] = ['id' => hr_neue_id('a'), 'person' => $ich['id'], 'art' => 'U', 'von' => $z['von'], 'bis' => $z['bis'], 'status' => 'beantragt',
                        'notiz' => $notiz, 'vertretung' => $erg[$i]['vertretung']['id'] ?? null, 'quelle' => 'vorplanung', 'erfasst' => ['t' => now(), 'by' => $me['name'], 'byId' => $me['id']]]
                        + (isset($erg[$i]['vertretung2']['id']) ? ['vertretung2' => $erg[$i]['vertretung2']['id']] : []);
                }
                hr_abwesenheiten_schreiben($abw);
                $pe = hr_planung_einst();
                return ['fehler' => false, 'zeitraeume' => $erg, 'neu' => $neu, 'jahr' => $jahr, 'ich' => $ich, 'personal' => $personal, 'alle' => $abw['eintraege'],
                        'stand' => hr_planung_person($ich, $abw['eintraege'], $jahr, $pe) + ['jahr' => $jahr, 'stichtag' => hr_planung_daten($pe, $jahr)['stichtag']],
                        'konto' => hr_konto($ich, $abw['eintraege'], $jahr)];
            });
            if (isset($res['bestaetigen'])) respond(['ok' => false, 'error' => $res['bestaetigen']['text'], 'bestaetigen' => $res['bestaetigen']], 409);
            if ($res['fehler'] && isset($res['ueberzug'])) respond(['ok' => false, 'error' => $res['ueberzug'], 'zeitraeume' => $res['zeitraeume']], 409);
            if ($res['fehler']) {
                $n = count(array_filter($res['zeitraeume'], function ($e) { return $e['fehler'] !== null; }));
                respond(['ok' => false, 'error' => $n === 1 ? 'Ein Zeitraum ist nicht in Ordnung – es wurde nichts beantragt.' : "$n Zeiträume sind nicht in Ordnung – es wurde nichts beantragt.",
                         'zeitraeume' => $res['zeitraeume']], 422);
            }
            $summe = array_sum(array_column($res['zeitraeume'], 'tage'));
            audit('hr', 'HR: Vorplanung ' . $res['jahr'] . ' beantragt – ' . count($res['neu']) . ' Zeiträume (' . hr_zahl_text($summe) . ' Arbeitstage): '
                . implode(', ', array_map(function ($e) { return hr_zeitraum_text($e['von'], $e['bis']); }, $res['neu'])));
            $hinweise = [];
            foreach ($res['zeitraeume'] as $e) foreach ($e['hinweise'] as $h) $hinweise[] = hr_zeitraum_text($e['von'], $e['bis']) . ': ' . $h;
            $st = $res['stand'];
            if ($st['einzeltageMax'] > 0 && count($st['einzeltage']) > $st['einzeltageMax'])
                $hinweise[] = 'Sie haben ' . count($st['einzeltage']) . ' einzelne Urlaubstage geplant – vorgesehen sind höchstens ' . $st['einzeltageMax'] . '. Die Personalstelle prüft sie einzeln.';
            if ($res['konto']['verfuegbar'] < 0) $hinweise[] = 'Die Planung übersteigt Ihre verfügbaren Urlaubstage um ' . hr_zahl_text(-$res['konto']['verfuegbar']) . ' – die Personalstelle entscheidet.';
            if ($vh = hr_vertretung_benachrichtigen($res['ich'], $res['neu'], $res['personal'], $res['alle'], $me)) $hinweise[] = $vh;   // E-Mail an die Vertretungen
            respond(['ok' => true, 'eintraege' => array_map(function ($e) use ($res) { return hr_eintrag_aus($e, $res['ich']); }, $res['neu']), 'zeitraeume' => $res['zeitraeume'],
                     'stand' => $st, 'hinweis' => $hinweise ? implode(' ', $hinweise) : null]);
        }

        case 'hr_antrag_zurueckziehen': {
            $me = require_perm('hr.antrag', true);
            $id = s(body()['id'] ?? '', 40) ?? '';
            $e = with_lock('hr-abwesenheiten', function () use ($me, $id) {
                $personal = hr_personal(); $abw = hr_abwesenheiten();
                $ich = hr_ich($personal, $me);
                foreach ($abw['eintraege'] as &$e) {
                    if ($e['id'] !== $id) continue;
                    if (!$ich || $e['person'] !== $ich['id'] || !in_array($e['art'], ['U', 'G'], true)) break;
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
            audit('hr', 'HR: ' . ($e['art'] === 'G' ? 'Gleittag-Antrag' : 'Urlaubsantrag') . ' zurückgezogen ' . hr_zeitraum_text($e['von'], $e['bis']));
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
            hr_mail_anstossen();
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
            audit('hr', 'HR: ' . (($e['art'] ?? 'U') === 'G' ? 'Gleittag-Antrag ' : 'Urlaubsantrag ') . ($p ? hr_name($p) : '') . ' ' . hr_zeitraum_text($e['von'], $e['bis']) . ' ' . $ent);
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
                    $artVorher = $e['art'];
                    if (!in_array($e['status'], HR_AKTIV, true)) fail('Erledigte Einträge lassen sich nicht mehr ändern.', 409);
                    if ($e['status'] === 'beantragt') fail('Offene Anträge bitte genehmigen oder ablehnen.', 409);
                    $e = array_merge($e, ['person' => $p['id'], 'art' => $art, 'von' => $von, 'bis' => $bis, 'notiz' => s($b['notiz'] ?? '', 300) ?? '', 'geaendert' => $jetzt]);
                    if ($art !== 'K') unset($e['urlaubAbzug']);   // „vom Urlaub abgezogen“ gilt nur für Krankheit aus der Zeiterfassung
                    $abw['eintraege'][$i] = $e;
                }
                hr_abwesenheiten_schreiben($abw);
                return [$e, $p, $i === null ? 'eingetragen' : 'geändert', hr_freie_tage($abw['eintraege'], $p['id']), $abw['eintraege'], $artVorher ?? null];
            });
            [$e, $p, $was, $frei] = $res;
            $alle = $res[4] ?? []; $artVorher = $res[5] ?? null;
            // Protokoll ohne Art der Abwesenheit (Krankheit ist ein Gesundheitsdatum)
            audit('hr', 'HR: Abwesenheit ' . ($p ? hr_name($p) : '') . ' ' . hr_zeitraum_text($e['von'], $e['bis']) . ' ' . $was);
            // Gleittag über das Gleittage-Konto hinaus: erlaubt (Personalstelle), aber mit Hinweis
            $hinweis = null;
            if ($p && $e['art'] === 'G' && $e['status'] !== 'storniert') {
                $gk = hr_gleit_konto($p, $alle, (int)substr($e['von'], 0, 4));
                if (!$gk['aktiv']) $hinweis = hr_name($p) . ' hat noch kein Gleittage-Konto – der Gleittag zählt erst, wenn Gleittage gewährt sind.';
                elseif ($gk['rest'] < 0) $hinweis = 'Das Gleittage-Konto von ' . hr_name($p) . ' steht damit bei ' . str_replace('.', ',', (string)$gk['rest']) . ' Tagen.';
            }
            // Unentschuldigtes Fehlen (neu eingetragen oder geändert zu F): E-Mail an den Mitarbeiter, außer ausdrücklich abgewählt
            $mail = null;
            if ($p && $e['art'] === 'F' && $e['status'] === 'genehmigt' && $was !== 'storniert' && ($b['mail'] ?? true) !== false
                && ($was === 'eingetragen' || $artVorher !== 'F')) $mail = hr_fehlen_mail($p, $e, $alle, $me);
            respond(['ok' => true, 'eintrag' => $p ? hr_eintrag_aus($e, $p, $frei) : null, 'hinweis' => $hinweis, 'mail' => $mail]);
        }

        /* Gleittage gewähren ({person, tage, grund}; negative Anzahl = Korrektur mit Grund) oder eine Gewährung stornieren
           ({person, id, stornieren: true, grund}) – Personalstelle, nie für sich selbst. Antwort: Konto und Gewährungen der Person. */
        case 'hr_gleittage_save': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $jahr = hr_jahr_param($b['jahr'] ?? null);
            [$roh, $was] = hr_gleittage_setzen($b, $me);
            $personal = hr_personal(); $abw = hr_abwesenheiten();
            $p = null;
            foreach ($personal['personen'] as $x) if ($x['nutzer'] === $roh['nutzer']) $p = $x;
            if (!$p) fail('Mitarbeiter nicht gefunden.', 404);
            $tage = $was === 'gewährt' ? end($roh['gleittage'])['tage'] : null;
            audit('hr', 'HR: Gleittage ' . hr_name($p) . ' ' . ($was === 'gewährt' ? ($tage > 0 ? '+' : '') . str_replace('.', ',', (string)$tage) . ' gewährt' : 'Gewährung storniert'));   // ohne Grund
            respond(['ok' => true, 'rev' => $personal['rev'], 'person' => $p['id'], 'neu' => $was === 'gewährt' ? end($roh['gleittage'])['id'] : null,
                     'gleitKonto' => hr_gleit_konto($p, $abw['eintraege'], $jahr), 'gleittage' => hr_gleit_aus($p, true)]);
        }

        /* Verwaltung → Mitarbeiter: HR-Angaben aller Mitarbeiter mit Urlaubskonto, Urlaubssperren, Ferien (Personalstelle).
           Oberfläche wie die Mitarbeiterverwaltung (Eingabebereich der Verwaltung). */
        case 'mitarbeiter_hr': {
            $me = require_perm('hr.verwalten');
            hr_mail_anstossen();
            header('Cache-Control: no-store');
            $jahr = hr_jahr_param($_GET['jahr'] ?? null);
            $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
            respond(['ok' => true, 'jahr' => $jahr, 'rev' => $personal['rev'], 'uebertragBis' => $einst['uebertragBis'], 'antraege' => $einst['antraege'],
                     'personen' => array_map(function ($p) use ($abw, $jahr) { return hr_person_aus($p, $abw['eintraege'], $jahr); }, $personal['personen']),
                     // Auswahl im Dialog (Stammdaten → Abteilungen); leer = freier Text wie bisher
                     'abteilungen' => array_map(function ($a) { return ['nr' => $a['nr'], 'name' => $a['name']]; }, hr_abteilungen()),
                     'mail' => hr_mail_aus()] + hr_einstellungen_aus($einst));
        }

        /* HR-Angaben eines Mitarbeiters: Abteilung, Position, Arbeitstage, im Urlaubsplan, Verfall des Resturlaubs (ja/nein),
           Anspruch und Übertrag eines Jahres. Abteilung: „abteilungNr“ aus den Stammdaten (Stammdaten → Abteilungen, '' = keine);
           „abteilung“ als Text (ältere Oberfläche, ohne Stammdaten) – mit Stammdaten wird ein bekannter Name zur Nummer. */
        case 'mitarbeiter_hr_save': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $uid = (string)($b['nutzer'] ?? '');
            $users = users_load();
            $ui = user_find($users, $uid);
            if ($ui === null) fail('Mitarbeiter nicht gefunden.', 404);
            $werte = [];
            $abtListe = hr_abteilungen();
            if (array_key_exists('abteilungNr', $b)) {
                if (!$abtListe) fail('Abteilung: Es sind noch keine Abteilungen angelegt (Stammdaten → Abteilungen).', 422);
                if ($b['abteilungNr'] !== null && !is_scalar($b['abteilungNr'])) fail('Abteilung: bitte eine Abteilung aus den Stammdaten wählen.', 422);
                $werte += hr_abteilung_werte((string)($b['abteilungNr'] ?? ''), $abtListe);
            } elseif (array_key_exists('abteilung', $b)) {
                $t = s($b['abteilung'], 40) ?? '';
                $a = $abtListe ? abteilung_nach_name($abtListe, $t) : null;
                $werte += $a ? ['abteilung' => $a['name'], 'abteilungNr' => $a['nr']] : ['abteilung' => $t, 'abteilungNr' => null];
            }
            if (array_key_exists('pos', $b)) $werte['pos'] = max(0, min(9999, (int)$b['pos']));
            if (array_key_exists('aktiv', $b)) $werte['aktiv'] = (bool)$b['aktiv'];
            if (array_key_exists('verfall', $b)) {
                // Resturlaub aus dem Vorjahr verfällt am Verfallstag (Standard) oder bleibt erhalten (Inhaber 03.11.2026)
                if (!is_bool($b['verfall'])) fail('Resturlaub verfällt: bitte ja oder nein angeben.', 422);
                $werte['verfall'] = $b['verfall'];
            }
            if (array_key_exists('personalnummer', $b)) {
                // Mitarbeiternummer der Zeiterfassung (Zuordnung beim Import), eindeutig
                $nr = trim((string)(s($b['personalnummer'], 20) ?? ''));
                if ($nr !== '' && !preg_match('/^[A-Za-z0-9._\/-]{1,20}$/', $nr)) fail('Personalnummer: bitte nur Ziffern, Buchstaben, Punkt, Bindestrich oder Schrägstrich.', 422);
                $werte['personalnummer'] = $nr;
            }
            if (array_key_exists('vertretung', $b)) {
                // feste Vertretung (Inhaber 10.11.2026): steht in jedem Antrag des Mitarbeiters fest und muss da sein; leer = frei wählbar
                $v = $b['vertretung'];
                if ($v !== null && !is_string($v)) fail('Vertretung: bitte einen Mitarbeiter wählen oder leer lassen.', 422);
                $werte['vertretung'] = $v === null || $v === '' ? null : $v;
            }
            if (array_key_exists('eintritt', $b)) {
                // Eintritt (Inhaber 11.11.2026): im Eintrittsjahr anteiliger Urlaubsanspruch; leer = kein Datum (voller Anspruch)
                $e = $b['eintritt'];
                if ($e === null || $e === '') $werte['eintritt'] = null;
                elseif (($d = hr_eintritt_datum($e)) === null || $d > hr_plus(hr_heute(), 3 * 366)) fail('Eintritt: bitte ein gültiges Datum wählen oder leer lassen.', 422);
                else $werte['eintritt'] = $d;
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
            $verfallVorher = null; $vertretungVorher = null; $eintrittVorher = null;
            $p = with_lock('hr-personal', function () use ($b, $uid, $users, $ui, &$werte, &$jahr, &$jv, $me, &$verfallVorher, &$vertretungVorher, &$eintrittVorher) {
                $roh = hr_personal_roh();
                $verfallVorher = true;
                foreach ($roh['personen'] as $e) if ($e['nutzer'] === $uid) { $verfallVorher = $e['verfall']; $vertretungVorher = $e['vertretung']; $eintrittVorher = $e['eintritt'] ?? null; }
                if ((int)($b['rev'] ?? -1) !== $roh['rev']) fail('Die Mitarbeiterliste wurde inzwischen geändert. Bitte neu laden.', 409);
                // Vier-Augen-Prinzip: die eigenen Urlaubsangaben (Anspruch, Übertrag, Verfall, Arbeitstage, im Urlaubsplan, Personalnummer –
                // sie bestimmt die Zuordnung beim Import) ändert eine andere Person der Personalstelle. Abteilung und Position
                // (Reihenfolge im Plan) sind ohne Einfluss auf das Urlaubskonto und bleiben erlaubt. Unveränderte Werte (der
                // Dialog schickt immer alle Felder) werden still übergangen, damit z. B. der eigene Name änderbar bleibt.
                if ($uid === (string)$me['id']) hr_eigene_angaben_pruefen($werte, $jahr, $jv, $uid, $users[$ui]);
                if (($werte['vertretung'] ?? null) !== null) {
                    $idx = hr_personen_index(hr_personal());
                    $vp = $idx[$werte['vertretung']] ?? null;
                    $selbst = null;
                    foreach (hr_personal()['personen'] as $x) if ($x['nutzer'] === $uid) $selbst = $x['id'];
                    if (!$vp || !$vp['aktiv'] || !empty($vp['altbestand'])) fail('Vertretung: bitte einen Mitarbeiter im Urlaubsplan wählen.', 422);
                    if ($vp['id'] === ($selbst ?? $uid)) fail('Vertretung: ein Mitarbeiter kann sich nicht selbst vertreten.', 422);
                }
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
            $vtIdx = hr_personen_index(hr_personal());
            audit('hr', 'HR: Angaben von ' . $users[$ui]['name'] . ' geändert'
                . ($p['verfall'] !== $verfallVorher ? ($p['verfall'] ? ' (Resturlaub verfällt wieder am Verfallstag)' : ' (Resturlaub verfällt nicht mehr)') : '')
                . ($p['vertretung'] !== $vertretungVorher ? ($p['vertretung'] ? ' (feste Vertretung: ' . (isset($vtIdx[$p['vertretung']]) ? hr_name($vtIdx[$p['vertretung']]) : $p['vertretung']) . ')' : ' (keine feste Vertretung mehr)') : '')
                . (($p['eintritt'] ?? null) !== $eintrittVorher ? (($p['eintritt'] ?? null) ? ' (Eintritt ' . hr_de($p['eintritt']) . ')' : ' (kein Eintrittsdatum mehr)') : ''));
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
            // optional (ohne Angabe bleibt der gespeicherte Wert): Sperren aus den Urlaubsregeln, Text der Urlaubsregeln
            $zusatz = [];
            if (array_key_exists('regelSperren', $b)) {
                if (!is_bool($b['regelSperren'])) fail('Sperren aus den Urlaubsregeln: bitte ja oder nein angeben.', 422);
                $zusatz['regelSperren'] = $b['regelSperren'];
            }
            if (array_key_exists('schliesstage', $b)) {
                if (!is_bool($b['schliesstage'])) fail('Sonderregelung Dezember: bitte ja oder nein angeben.', 422);
                $zusatz['schliesstage'] = $b['schliesstage'];
            }
            if (array_key_exists('regeln', $b)) $zusatz['regeln'] = hr_regeln_pruefen($b['regeln']);
            if (array_key_exists('ueberziehenMax', $b)) {
                // Resturlaub überziehen: höchstens so viele Tage (mit Bestätigung), darüber immer abgelehnt
                $u = hr_ueberziehen_norm($b['ueberziehenMax']);
                if ($u === null) fail('Resturlaub überziehen: bitte 0 bis 30 Tage in ganzen oder halben Tagen angeben (0 = nie).', 422);
                $zusatz['ueberziehenMax'] = $u;
            }
            // Urlaub am Stück höchstens (Arbeitstage, 0 = keine Prüfung; optional – ohne Angabe bleibt der gespeicherte Wert)
            if (array_key_exists('amStueckMax', $b)) {
                $am = hr_am_stueck_norm($b['amStueckMax']);
                if ($am === null) fail('Urlaub am Stück: bitte eine ganze Zahl von 0 bis ' . HR_AM_STUECK_GRENZE . ' Arbeitstagen angeben (0 = keine Prüfung).', 422);
                $zusatz['amStueckMax'] = $am;
            }
            // Jahresplanung (optional): Beginn, Stichtag, höchstens unverplante Tage, Vertretung Pflicht, Einzeltage – der Abschluss bleibt
            $planung = null;
            if (array_key_exists('planung', $b)) { try { $planung = hr_planung_einst_pruefen($b['planung']); } catch (InvalidArgumentException $ex) { fail($ex->getMessage(), 422); } }
            // Übergangsregel: erstes Jahr mit Verfall (Jahreszahl) oder null = jedes Jahr
            if (array_key_exists('verfallAb', $b)) {
                if ($b['verfallAb'] !== null && hr_verfall_ab_norm($b['verfallAb']) === null) fail('Erster Verfall: bitte ein Jahr zwischen ' . HR_VERFALL_AB_MIN . ' und ' . HR_VERFALL_AB_MAX . ' wählen oder „jedes Jahr“.', 422);
                $zusatz['verfallAb'] = $b['verfallAb'];
            }
            // Verfallstag des Resturlaubs (optional; ohne Angabe bleibt der gespeicherte Wert)
            $bis = null;
            if (array_key_exists('uebertragBis', $b)) {
                $bis = hr_uebertrag_bis_norm($b['uebertragBis']);
                if ($bis === null) fail('Verfallstag des Resturlaubs: bitte ein gültiges Datum wählen (der 29.02. ist nicht möglich, weil es ihn nicht jedes Jahr gibt).', 422);
            }
            $alt = hr_einstellungen(); $vorher = $alt['uebertragBis'];
            $planungVorher = hr_planung_einst();
            with_lock('hr-einstellungen', function () use ($sperren, $ferien, $bis, $zusatz, $planung) {
                $d = store_read('hr-einstellungen') ?? [];
                if ($planung !== null) $zusatz['planung'] = array_merge(is_array($d['planung'] ?? null) ? $d['planung'] : [], $planung);
                store_write('hr-einstellungen', array_merge($d, ['rev' => (int)($d['rev'] ?? 0) + 1, 'sperren' => $sperren, 'ferien' => $ferien],
                                                            $bis !== null ? ['uebertragBis' => $bis] : [], $zusatz));
            });
            if ($planung !== null && array_diff_assoc($planung, array_intersect_key($planungVorher, $planung))) {
                $tm = function ($v) { return substr($v, 3, 2) . '.' . substr($v, 0, 2) . '.'; };
                $pn = hr_planung_einst();   // gespeicherter Stand (auch Werte ohne Angabe)
                audit('hr', 'HR: Jahresplanung eingestellt (ab ' . $tm($pn['start']) . ', Stichtag ' . $tm($pn['stichtag']) . (hr_stichtag_im_jahr($pn) ? ' im geplanten Jahr' : '')
                    . ', höchstens ' . hr_tage_text((float)$pn['unverplantMax']) . ' unverplant, Vertretung ' . ($pn['vertretungPflicht'] ? 'Pflicht' : 'freiwillig')
                    . ', höchstens ' . $pn['einzeltageMax'] . ' einzelne Urlaubstage)');
            }
            audit('hr', 'HR: Urlaubssperren und Ferien gespeichert (' . count($sperren) . ' Sperren, ' . count($ferien) . ' Ferienzeiträume)');
            if ($bis !== null && $bis !== $vorher) audit('hr', 'HR: Verfallstag Resturlaub auf ' . substr($bis, 3, 2) . '.' . substr($bis, 0, 2) . '. geändert (vorher ' . substr($vorher, 3, 2) . '.' . substr($vorher, 0, 2) . '.)');
            if (isset($zusatz['regelSperren']) && $zusatz['regelSperren'] !== $alt['regelSperren']) audit('hr', 'HR: Sperren aus den Urlaubsregeln ' . ($zusatz['regelSperren'] ? 'eingeschaltet' : 'ausgeschaltet'));
            if (isset($zusatz['schliesstage']) && $zusatz['schliesstage'] !== $alt['schliesstage']) audit('hr', 'HR: Sonderregelung Dezember (24.12./31.12. je ½ Urlaubstag) ' . ($zusatz['schliesstage'] ? 'eingeschaltet' : 'ausgeschaltet'));
            if (isset($zusatz['regeln']) && hr_regeln_text($zusatz['regeln']) !== $alt['regeln']) audit('hr', 'HR: Urlaubsregeln geändert');
            if (isset($zusatz['amStueckMax']) && $zusatz['amStueckMax'] !== $alt['amStueckMax'])
                audit('hr', 'HR: Urlaub am Stück höchstens ' . ($zusatz['amStueckMax'] ? $zusatz['amStueckMax'] . ' Arbeitstage' : 'ohne Grenze') . ' (vorher ' . ($alt['amStueckMax'] ? $alt['amStueckMax'] . ' Arbeitstage' : 'ohne Grenze') . ')');
            if (isset($zusatz['ueberziehenMax']) && $zusatz['ueberziehenMax'] !== $alt['ueberziehenMax'])
                audit('hr', 'HR: Resturlaub überziehen höchstens ' . hr_tage_text($zusatz['ueberziehenMax']) . ' (vorher ' . hr_tage_text($alt['ueberziehenMax']) . ')');   // verglichen wird, was Mitarbeiter sehen
            if (array_key_exists('verfallAb', $zusatz) && $zusatz['verfallAb'] !== $alt['verfallAb']) {
                $tag = substr(hr_einstellungen()['uebertragBis'], 3, 2) . '.' . substr(hr_einstellungen()['uebertragBis'], 0, 2) . '.';
                audit('hr', $zusatz['verfallAb'] === null ? 'HR: Resturlaub verfällt jedes Jahr (keine Übergangsregel mehr)'
                    : 'HR: Resturlaub verfällt erstmals am ' . $tag . $zusatz['verfallAb'] . ' (vorher kein Verfall)');
            }
            hr_verfall_ab(true); hr_schliesstage_an(true);
            $neu = hr_einstellungen();
            respond(['ok' => true, 'ferien' => $neu['ferien'], 'uebertragBis' => hr_uebertrag_bis(true)] + hr_einstellungen_aus($neu));
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
        /* ---------- E-Mails der Urlaubsverwaltung (Verwaltung → Urlaub, module/hr/mail.php) ---------- */
        /* Einstellungen: Monatsübersicht automatisch, Testmodus mit Testadresse, Steuerberater (Adresse, Tag, automatisch) */
        case 'hr_mail_save': {
            $me = require_perm('hr.verwalten', true);
            [$alt, $neu] = hr_mail_speichern(body());
            $an = function (bool $x) { return $x ? 'an' : 'aus'; };
            $teile = [];
            if ($alt['monat']['an'] !== $neu['monat']['an']) $teile[] = 'Monatsübersicht automatisch ' . $an($neu['monat']['an']);
            if ($alt['test'] !== $neu['test']) $teile[] = 'Testmodus ' . $an($neu['test']['an']) . ($neu['test']['adresse'] !== '' ? ' (' . $neu['test']['adresse'] . ')' : '');
            $sa = $alt['steuerberater']; $sn = $neu['steuerberater'];
            if ([$sa['an'], $sa['adresse'], $sa['tag']] !== [$sn['an'], $sn['adresse'], $sn['tag']]) $teile[] = 'Steuerberater automatisch ' . $an($sn['an']) . ', am ' . $sn['tag'] . '.' . ($sn['adresse'] !== '' ? ' an ' . $sn['adresse'] : '');
            if ($teile) audit('hr', 'HR: E-Mail-Einstellungen geändert: ' . implode('; ', $teile));
            respond(['ok' => true, 'mail' => hr_mail_aus()]);
        }
        /* Erinnerung „Resturlaub verfällt“ an alle, bei denen Übertrag verfallen würde */
        case 'hr_erinnerung_senden': {
            $me = require_perm('hr.verwalten', true);
            if (!hr_erinnerung_kandidaten()[0]) fail('Bei niemandem mit E-Mail-Adresse verfällt gerade Resturlaub – es gibt nichts zu senden.', 409);
            try { $r = hr_erinnerung_senden($me); } catch (RuntimeException $e) { fail($e->getMessage(), 409); }
            if (!$r['gesendet']) fail('Erinnerung nicht zugestellt: ' . ($r['fehlerText'][0] ?? 'Versandfehler'), 502);
            respond(['ok' => true, 'ergebnis' => $r, 'mail' => hr_mail_aus()]);
        }
        /* Monatsübersicht auf Knopfdruck: optional „monat“ (JJJJ-MM, höchstens 12 Monate zurück, nicht in der Zukunft), sonst Vormonat */
        case 'hr_monatsuebersicht_senden': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            [$vor, $dies] = hr_mail_monate();
            $ym = $b['monat'] ?? $vor;
            $grenze = (new DateTimeImmutable('first day of this month'))->modify('-12 months')->format('Y-m');
            if (!is_string($ym) || !preg_match('/^\d{4}-(0[1-9]|1[0-2])$/', $ym) || $ym > $dies || $ym < $grenze) fail('Monat: bitte einen Monat der letzten zwölf Monate wählen (JJJJ-MM).', 422);
            if (!hr_mail_empfaenger()[0]) fail('Kein Mitarbeiter im Urlaubsplan hat eine E-Mail-Adresse – es gibt nichts zu senden.', 409);
            try { $r = hr_monat_senden($ym, 'manuell', $me); } catch (RuntimeException $e) { fail($e->getMessage(), 409); }
            if (!$r['gesendet']) fail('Monatsübersicht nicht zugestellt: ' . ($r['fehlerText'][0] ?? 'Versandfehler'), 502);
            respond(['ok' => true, 'ergebnis' => $r, 'mail' => hr_mail_aus()]);
        }
        /* Übersicht an den Steuerberater auf Knopfdruck (Vormonat und laufender Monat) */
        case 'hr_steuerberater_senden': {
            $me = require_perm('hr.verwalten', true);
            try { $r = hr_stb_senden('manuell', $me); } catch (RuntimeException $e) { fail($e->getMessage(), 409); }
            if (!$r['gesendet']) fail('Übersicht nicht zugestellt: ' . ($r['fehlerText'][0] ?? 'Versandfehler'), 502);
            respond(['ok' => true, 'ergebnis' => $r, 'mail' => hr_mail_aus()]);
        }

        /* Jahresplanung: Zusammenfassung eines Jahres (Standard: das nächste) – nur Personalstelle. Sie enthält alle
           Urlaubszeiträume; zusammen mit dem Kalender („abwesend“) ließen sich daraus sonst Krankheitstage ableiten.
           Genehmiger ohne Personalstelle entscheiden wie bisher unter „Anträge“ (hr_offen). */
        case 'hr_planung': {
            $me = require_perm('hr.verwalten');
            header('Cache-Control: no-store');
            $jahr = isset($_GET['jahr']) ? hr_jahr_param($_GET['jahr']) : hr_planung_jahr();
            respond(['ok' => true, 'verwalten' => may($me, 'hr.verwalten'), 'genehmigen' => may($me, 'hr.genehmigen')] + hr_planung($jahr, $me));
        }
        /* Konfliktfreie Anträge gesammelt genehmigen: {jahr, ids[]} – Recht hr.genehmigen, nie die eigenen; jeder Antrag wird neu geprüft */
        case 'hr_planung_freigeben': {
            $me = require_perm('hr.genehmigen', true);
            $b = body();
            $jahr = isset($b['jahr']) ? hr_jahr_param($b['jahr']) : hr_planung_jahr();
            $ids = $b['ids'] ?? null;
            if (!is_array($ids) || !$ids || count($ids) > 500 || array_filter($ids, function ($x) { return !is_string($x) || !preg_match('/^[a-z0-9]{1,40}$/i', $x); })) fail('Bitte die Anträge angeben.', 422);
            [$ok, $weg] = hr_planung_freigeben($jahr, array_values(array_unique($ids)), $me);
            if ($ok) audit('hr', "HR: Jahresplanung $jahr: " . count($ok) . ' Urlaubsanträge gesammelt genehmigt');
            respond(['ok' => true, 'genehmigt' => $ok, 'uebersprungen' => $weg]);
        }
        /* Erinnerung „Bitte planen Sie Ihren Urlaub“ an alle Mitarbeiter mit Adresse, die das Ziel noch nicht erreicht haben */
        case 'hr_planung_erinnern': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $jahr = isset($b['jahr']) ? hr_jahr_param($b['jahr']) : hr_planung_jahr();
            if ($jahr < (int)substr(hr_heute(), 0, 4)) fail("Die Planung $jahr liegt in der Vergangenheit.", 409);
            if (isset(hr_planung_einst()['abschluss'][(string)$jahr])) fail("Die Planung $jahr ist abgeschlossen – erst wieder öffnen.", 409);
            try { $r = hr_planung_senden('planung', $jahr, $me); } catch (RuntimeException $e) { fail($e->getMessage(), 409); }
            if (!$r['gesendet']) fail('Erinnerung nicht zugestellt: ' . ($r['fehlerText'][0] ?? 'Versandfehler'), 502);
            respond(['ok' => true, 'ergebnis' => $r]);
        }
        /* Planung abschließen (mit Jahresübersicht an alle mit Adresse, Standard) oder wieder öffnen: {jahr, abgeschlossen, senden} */
        case 'hr_planung_abschluss': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $jahr = isset($b['jahr']) ? hr_jahr_param($b['jahr']) : hr_planung_jahr();
            if (!is_bool($b['abgeschlossen'] ?? null)) fail('Bitte abschließen oder wieder öffnen.', 422);
            $zu = $b['abgeschlossen'];
            if (!hr_planung_abschluss_setzen($jahr, $zu, $me)) fail($zu ? "Die Planung $jahr ist bereits abgeschlossen." : "Die Planung $jahr ist nicht abgeschlossen.", 409);
            audit('hr', "HR: Jahresplanung $jahr " . ($zu ? 'abgeschlossen' : 'wieder geöffnet'));
            $r = null;
            if ($zu && ($b['senden'] ?? true) !== false && hr_planung_empfaenger($jahr, false)[0]) {
                try { $r = hr_planung_senden('jahresuebersicht', $jahr, $me); } catch (RuntimeException $e) { $r = ['gesendet' => 0, 'fehler' => 0, 'fehlerText' => [$e->getMessage()]]; }
            }
            respond(['ok' => true, 'ergebnis' => $r]);
        }
        /* Jahresübersicht (erneut) senden: {jahr, person?} – an alle mit Adresse oder eine Person */
        case 'hr_planung_uebersicht_senden': {
            $me = require_perm('hr.verwalten', true);
            $b = body();
            $jahr = isset($b['jahr']) ? hr_jahr_param($b['jahr']) : hr_planung_jahr();
            $person = isset($b['person']) && $b['person'] !== '' ? (string)$b['person'] : null;
            try { $r = hr_planung_senden('jahresuebersicht', $jahr, $me, $person); } catch (RuntimeException $e) { fail($e->getMessage(), 409); }
            if (!$r['gesendet']) fail('Jahresübersicht nicht zugestellt: ' . ($r['fehlerText'][0] ?? 'Versandfehler'), 502);
            respond(['ok' => true, 'ergebnis' => $r]);
        }

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

}
