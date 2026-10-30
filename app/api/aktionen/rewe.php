<?php
declare(strict_types=1);
/* Aktionen: REWE · Vordisposition Dry Aged (Oberfläche rewe.intern, Daten und Regeln in app/api/module/rewe/rewe.php,
   Wochenabschluss und Excel in app/api/module/rewe/export.php)
   Rechte (GR-103): rewe.sehen – eigene Liste und Akten der eigenen Märkte;
                    rewe.bearbeiten – eigene Märkte abfragen (Antworten), Notizen, Wiedervorlagen, Kaufbereitschaft,
                                      Dauerauftrag, Ansprechpartner;
                    rewe.alle – alle Listen sehen (mit „bearbeiten“ auch für andere abfragen, z. B. Vertretung);
                    rewe.verwalten – Märkte anlegen und Stammfelder ändern, Zuweisung und Lieferweg ab KW, Team, Lieferwege
                                     und Artikel, Datenpaket der Excel-Listen übernehmen;
                    rewe.exportieren – Wochenabschluss aller Listen, Excel für WinAB, „in WinAB erfasst“ abhaken.
   „Alle Listen“ und „Wochenabschluss“ lassen sich zusätzlich im Team des Moduls zuweisen (rw_alle, rw_export).
   „Eigene Märkte“ prüft der Server je Markt über die Zuständigkeit der Kalenderwoche; fremde Märkte ohne „alle“ → 404.
   Gleichzeitiges Bearbeiten: Märkte tragen „rev“, Antworten „r“; ein veralteter Stand bekommt 409.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

function rw_rechte(array $me): array
{
    return ['bearbeiten' => may($me, 'rewe.bearbeiten'), 'alle' => rw_alle($me), 'verwalten' => may($me, 'rewe.verwalten'), 'exportieren' => rw_export($me)];
}
function rw_kw_param(string $standard): string
{
    $v = $_GET['kw'] ?? '';
    return is_string($v) && $v !== '' ? rw_kw($v) : $standard;
}
function rw_export_pruefen(bool $schreibend = false): array
{
    $me = require_perm('rewe.sehen', $schreibend);
    if (!rw_export($me)) fail('Den Wochenabschluss sehen nur Mitarbeiter mit „REWE-Wochenabschluss“ (Recht oder Team).', 403);
    return $me;
}
function rw_xlsx_senden(string $inhalt, string $datei): void
{
    header('Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
    header('Content-Disposition: attachment; filename="' . $datei . '"');
    header('Content-Length: ' . strlen($inhalt));
    header('Cache-Control: private, no-store');
    header('X-Content-Type-Options: nosniff');
    echo $inhalt;
    exit;
}

switch ($action) {
        /* Start: Rechte, Stammdaten, Auswahllisten, Mitarbeiter (für „alle Listen“ und Verwaltung) */
        case 'rewe_start': {
            $me = require_perm('rewe.sehen');
            header('Cache-Control: no-store');
            $r = rw_rechte($me);
            $stamm = rw_stamm();
            respond(['ok' => true, 'name' => $me['name'], 'ich' => (string)$me['id'], 'heute' => rw_kw_heute(), 'abfrage' => rw_kw_abfrage(), 'abschlussKw' => rw_kw_abschluss(),
                     'datum' => date('Y-m-d'), 'rechte' => $r, 'stammRev' => $stamm['rev'], 'lieferwege' => $stamm['lieferwege'], 'artikel' => $stamm['artikel'], 'antworten' => RW_ANTWORTEN, 'kauf' => RW_KAUF, 'kaufAbfrage' => RW_KAUF_ABFRAGE,
                     'notizArten' => RW_NOTIZ_ARTEN, 'lwArten' => RW_LW_ARTEN, 'tage' => RW_TAGE, 'rhythmen' => RW_RHYTHMEN,
                     'personen' => $r['alle'] || $r['verwalten'] || $r['exportieren'] ? rw_personen() : [],
                     'leer' => $r['verwalten'] ? rw_leer() : null]);
        }

        /* Wochenabfrage einer KW: eigene Liste (mit „alle“: ?wer=<Nutzer-ID> oder * für alle Listen) */
        case 'rewe_woche': {
            $me = require_perm('rewe.sehen');
            header('Cache-Control: no-store');
            $kw = rw_kw_param(rw_kw_abfrage());
            $wer = is_string($_GET['wer'] ?? null) ? trim($_GET['wer']) : '';
            if ($wer !== '' && !rw_alle($me)) fail('Andere Listen sehen nur Mitarbeiter mit „Alle REWE-Listen“.', 403);
            respond(['ok' => true, 'woche' => rw_woche($kw, $me, $wer)]);
        }

        /* Märkte (Übersicht): sichtbare Märkte mit Lieferweg, Zuständigkeit, Kaufbereitschaft und letzter Bestellung */
        case 'rewe_maerkte': {
            $me = require_perm('rewe.sehen');
            header('Cache-Control: no-store');
            $kw = rw_kw_abfrage(); $stamm = rw_stamm(); $namen = rw_namen();
            $jahr = (int)substr(rw_kw_heute(), 0, 4);
            $dieses = rw_wochen_doc($jahr)['maerkte'];
            $letzteAlle = rw_letzte_bestellungen();
            $out = [];
            foreach (rw_maerkte_doc()['liste'] as $m) {
                if (!rw_darf_sehen($m, $me)) continue;
                $letzte = $letzteAlle[$m['id']] ?? '';
                $anzahl = count(array_filter($dieses[$m['id']] ?? [], function ($e) { return ($e['s'] ?? '') === 'bestellt'; }));
                $x = rw_markt_aus($m, $stamm, $namen, $kw);
                $out[] = ['id' => $x['id'], 'name' => $x['name'], 'ort' => $x['ort'], 'plz' => $x['plz'], 'strasse' => $x['strasse'], 'kdNr' => $x['kdNr'], 'reweNr' => $x['reweNr'], 'winab' => $x['winab'],
                          'lieferweg' => $x['lieferweg'], 'lieferwegName' => $x['lieferwegName'], 'zustaendig' => $x['zustaendig'], 'zustaendigName' => $x['zustaendigName'],
                          'kauf' => $x['kauf'], 'dauerText' => rw_dauer_text($m, $stamm), 'letzte' => $letzte, 'anzahlJahr' => $anzahl];
            }
            usort($out, function ($a, $b) { return [$a['ort'], $a['name']] <=> [$b['ort'], $b['name']]; });
            respond(['ok' => true, 'maerkte' => $out, 'jahr' => $jahr]);
        }

        /* Marktakte: Markt, alle Wochen, Notizen und Verlauf, Kennzahlen je Jahr */
        case 'rewe_markt': {
            $me = require_perm('rewe.sehen');
            header('Cache-Control: no-store');
            $m = rw_markt_finden(rw_maerkte_doc(), $_GET['id'] ?? '', $me);
            respond(['ok' => true] + rw_akte($m, $me));
        }

        /* Antwort einer KW setzen oder zurücknehmen (status leer) */
        case 'rewe_antwort': {
            $me = require_perm('rewe.bearbeiten', true);
            $b = body();
            $erg = with_lock('rewe-maerkte', function () use ($b, $me) { return rw_antwort_setzen($b, $me, rw_stamm()); });
            $a = $erg['antwort'];
            audit('rewe', 'REWE: ' . $erg['markt']['name'] . ', ' . rw_kw_text(rw_kw($b['kw'])) . ' – '
                . ($a ? (RW_ANTWORTEN[$a['s']] ?? $a['s']) . (!empty($a['m']) ? ' (' . rw_mengen_text($a['m'], rw_stamm()) . ')' : '') : 'Antwort zurückgenommen'));
            respond(['ok' => true, 'antwort' => rw_antwort_aus($a)]);
        }

        /* Fällige Daueraufträge der KW als Bestellung übernehmen (nur Märkte ohne Antwort) */
        case 'rewe_dauer_uebernehmen': {
            $me = require_perm('rewe.bearbeiten', true);
            $b = body();
            $kw = rw_kw($b['kw'] ?? '');
            $wer = is_string($b['wer'] ?? null) ? trim($b['wer']) : '';
            if ($wer !== '' && !rw_alle($me)) fail('Andere Listen bearbeiten nur Mitarbeiter mit „Alle REWE-Listen“.', 403);
            $ids = array_values(array_filter((array)($b['maerkte'] ?? []), 'is_string'));
            $erg = with_lock('rewe-maerkte', function () use ($kw, $me, $wer, $ids) { return rw_dauer_uebernehmen($kw, $me, $wer, $ids); });
            if ($erg['uebernommen']) audit('rewe', 'REWE: ' . $erg['uebernommen'] . ' Daueraufträge für ' . rw_kw_text($kw) . ' übernommen');
            respond(['ok' => true] + $erg);
        }

        /* Markt anlegen (verwalten) oder ändern: Pflegefelder an eigenen Märkten (bearbeiten), Stammfelder nur mit „verwalten“ */
        case 'rewe_markt_save': {
            $me = require_perm('rewe.bearbeiten', true);
            $b = body();
            $markt = with_lock('rewe-maerkte', function () use ($b, $me) {
                $stamm = rw_stamm(); $doc = rw_maerkte_doc(); $kw = rw_kw_abfrage();
                $id = is_string($b['id'] ?? null) ? $b['id'] : '';
                if ($id === '') {
                    if (!may($me, 'rewe.verwalten')) fail('Märkte anlegen dürfen nur Mitarbeiter mit „REWE verwalten“.', 403);
                    if (count($doc['liste']) >= RW_MAX_MAERKTE) fail('Zu viele Märkte.', 422);
                    $f = rw_markt_felder($b, $stamm, []);
                    rw_kdnr_frei($doc, $f['kdNr'] ?? '', '');
                    $lw = is_string($b['lieferweg'] ?? null) ? $b['lieferweg'] : '';
                    $l = rw_lieferweg($stamm, $lw);
                    if (!$l || empty($l['aktiv'])) throw new InvalidArgumentException('Lieferweg: bitte einen aktiven Lieferweg wählen.');
                    $ab = isset($b['ab']) && $b['ab'] !== '' ? rw_kw($b['ab'], 'Gültig ab') : $kw;
                    $m = ['id' => rw_id('m'), 'rev' => 1] + $f + ['kauf' => 'regelmaessig']
                       + ['zustaendig' => [['ab' => $ab, 'nutzer' => rw_person_pruefen($b['zustaendig'] ?? '')]], 'lieferweg' => [['ab' => $ab, 'id' => $lw]], 'erstellt' => rw_wer($me)];
                    $doc['liste'][] = $m;
                    rw_schreiben('rewe-maerkte', $doc);
                    rw_system_notiz($m['id'], 'Markt angelegt', $me);
                    return [$m, true];
                }
                $i = rw_markt_index($doc, $id); $alt = $doc['liste'][$i];
                if (!rw_darf_pflegen($alt, $me)) fail('Markt nicht gefunden.', 404);
                if (array_intersect(RW_FELDER_STAMM, array_keys($b)) && !may($me, 'rewe.verwalten')) fail('Stammdaten des Marktes ändern nur Mitarbeiter mit „REWE verwalten“.', 403);
                if (array_key_exists('rev', $b) && (int)$b['rev'] !== (int)($alt['rev'] ?? 0))
                    respond(['ok' => false, 'code' => 'konflikt', 'error' => 'Der Markt wurde inzwischen von ' . ($alt['geaendert']['von'] ?? 'jemand anderem') . ' geändert. Bitte neu laden.'], 409);
                $f = rw_markt_felder($b, $stamm, $alt);
                if (array_key_exists('kdNr', $f)) rw_kdnr_frei($doc, $f['kdNr'], $id);
                $neu = $f + $alt;
                $neu['rev'] = (int)($alt['rev'] ?? 0) + 1; $neu['geaendert'] = rw_wer($me);
                $doc['liste'][$i] = $neu;
                rw_schreiben('rewe-maerkte', $doc);
                $text = [];
                if (($alt['kauf'] ?? 'regelmaessig') !== ($neu['kauf'] ?? 'regelmaessig')) $text[] = 'Kaufbereitschaft: ' . (RW_KAUF[$alt['kauf'] ?? 'regelmaessig'] ?? '') . ' → ' . RW_KAUF[$neu['kauf']];
                if (array_key_exists('dauer', $f) && rw_dauer($alt) != rw_dauer($neu)) $text[] = rw_dauer_text($neu, $stamm) ?: 'Dauerauftrag beendet';
                if ($text) rw_system_notiz($id, implode(' · ', $text), $me);
                return [$neu, false];
            });
            [$m, $neu] = $markt;
            audit('rewe', 'REWE: Markt ' . ($neu ? 'angelegt' : 'geändert') . ' – ' . $m['name']);
            respond(['ok' => true, 'markt' => rw_markt_aus($m, rw_stamm(), rw_namen(), rw_kw_abfrage())]);
        }

        /* Notiz, Telefonat, Wiedervorlage anlegen ({markt, art, text, wiedervorlage}) oder Wiedervorlage erledigen ({id, erledigt}) */
        case 'rewe_notiz_save': {
            $me = require_perm('rewe.bearbeiten', true);
            $b = body();
            $n = with_lock('rewe-maerkte', function () use ($b, $me) {
                $doc = rw_verlauf_doc(); $maerkte = rw_maerkte_doc();
                if (!empty($b['id'])) {
                    foreach ($doc['liste'] as $i => $n) {
                        if ($n['id'] !== $b['id']) continue;
                        $m = $maerkte['liste'][rw_markt_index($maerkte, $n['markt'])];
                        if (!rw_darf_pflegen($m, $me)) fail('Notiz nicht gefunden.', 404);
                        if (($n['wv'] ?? '') === '') throw new InvalidArgumentException('Nur Wiedervorlagen lassen sich erledigen.');
                        $doc['liste'][$i]['erledigt'] = empty($b['erledigt']) ? null : rw_wer($me);
                        rw_schreiben('rewe-verlauf', $doc);
                        return $doc['liste'][$i];
                    }
                    fail('Notiz nicht gefunden.', 404);
                }
                $m = rw_markt_finden($maerkte, $b['markt'] ?? '', $me);
                if (!rw_darf_pflegen($m, $me)) fail('Markt nicht gefunden.', 404);
                $art = rw_wahl($b['art'] ?? 'notiz', array_diff(array_keys(RW_NOTIZ_ARTEN), ['system']), 'Art');
                $text = rw_text($b['text'] ?? '', 2000, 'Notiz', true);
                if ($text === '') throw new InvalidArgumentException('Notiz: bitte einen Text angeben.');
                $wv = trim((string)($b['wiedervorlage'] ?? ''));
                if ($wv !== '') {
                    if (!preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $wv, $t) || !checkdate((int)$t[2], (int)$t[3], (int)$t[1])) throw new InvalidArgumentException('Wiedervorlage: ungültiges Datum.');
                    if ($wv > date('Y-m-d', strtotime('+2 years'))) throw new InvalidArgumentException('Wiedervorlage: höchstens zwei Jahre im Voraus.');
                }
                $doc = rw_notiz_neu($doc, $m['id'], $art, $text, $me, $wv);
                rw_schreiben('rewe-verlauf', $doc);
                return end($doc['liste']);
            });
            respond(['ok' => true, 'notiz' => $n]);
        }

        /* Zuständigkeit und/oder Lieferweg mehrerer Märkte ab KW ändern */
        case 'rewe_zuweisen': {
            $me = require_perm('rewe.verwalten', true);
            $b = body();
            $ids = $b['maerkte'] ?? null;
            if (!is_array($ids) || !$ids || count($ids) > RW_MAX_MAERKTE || array_filter($ids, function ($x) { return !is_string($x); })) throw new InvalidArgumentException('Bitte Märkte auswählen.');
            $kw = rw_kw($b['ab'] ?? '', 'Gültig ab');
            $nutzer = array_key_exists('nutzer', $b) ? rw_person_pruefen($b['nutzer']) : null;
            $stamm = rw_stamm();
            $lw = null;
            if (array_key_exists('lieferweg', $b) && $b['lieferweg'] !== null && $b['lieferweg'] !== '') {
                $l = rw_lieferweg($stamm, (string)$b['lieferweg']);
                if (!$l || empty($l['aktiv'])) throw new InvalidArgumentException('Lieferweg: bitte einen aktiven Lieferweg wählen.');
                $lw = $l['id'];
            }
            if ($nutzer === null && $lw === null) throw new InvalidArgumentException('Bitte Zuständigkeit oder Lieferweg wählen.');
            $n = with_lock('rewe-maerkte', function () use ($ids, $kw, $nutzer, $lw, $me) { return rw_zuweisen(array_values(array_unique($ids)), $kw, $nutzer, $lw, $me); });
            audit('rewe', 'REWE: ' . $n . ' Märkte ab ' . rw_kw_text($kw) . ' neu zugewiesen');
            respond(['ok' => true, 'geaendert' => $n]);
        }

        /* Lieferwege und Artikel (Name, Einheit, WinAB-Artikelnummer) pflegen */
        case 'rewe_stamm_save': {
            $me = require_perm('rewe.verwalten', true);
            $b = body();
            $stamm = with_lock('rewe-maerkte', function () use ($b) {
                $alt = rw_stamm();
                if (array_key_exists('rev', $b) && (int)$b['rev'] !== $alt['rev']) fail('Die Einstellungen wurden inzwischen geändert. Bitte neu laden.', 409);
                $neu = rw_stamm_pruefen($b, $alt);
                rw_schreiben('rewe-stamm', $neu);
                return rw_stamm();
            });
            audit('rewe', 'REWE: Lieferwege und Artikel geändert');
            respond(['ok' => true, 'rev' => $stamm['rev'], 'lieferwege' => $stamm['lieferwege'], 'artikel' => $stamm['artikel']]);
        }

        /* Team: „alle Listen“ und „Wochenabschluss“ je Mitarbeiter (Zuweisung im Modul, zusätzlich zu den Rechten) */
        case 'rewe_team_save': {
            $me = require_perm('rewe.verwalten', true);
            $b = body();
            $team = rw_team_pruefen($b['team'] ?? null);
            with_lock('rewe-maerkte', function () use ($team) { $s = rw_stamm(); $s['team'] = $team; rw_schreiben('rewe-stamm', $s); });
            audit('rewe', 'REWE: Team geändert – ' . count(array_filter($team, function ($t) { return $t['alle']; })) . ' mit allen Listen, '
                . count(array_filter($team, function ($t) { return $t['export']; })) . ' mit Wochenabschluss');
            respond(['ok' => true]);
        }

        /* Wochenabschluss einer KW über alle Listen */
        case 'rewe_abschluss': {
            rw_export_pruefen();
            header('Cache-Control: no-store');
            respond(['ok' => true, 'abschluss' => rw_abschluss(rw_kw_param(rw_kw_abschluss()))]);
        }

        /* Excel für die Erfassung in WinAB; vermerkt „exportiert“ (spätere Änderungen sind Nachträge) */
        case 'rewe_export': {
            $me = rw_export_pruefen(true);
            $b = body();
            $kw = rw_kw($b['kw'] ?? '');
            $a = rw_abschluss($kw);
            if (!$a['zeilen']) fail('In dieser Woche gibt es keine Bestellungen.', 422);
            $datei = rw_export_xlsx($a, rw_stamm(), (string)$me['name']);
            with_lock('rewe-maerkte', function () use ($kw, $me, $a) {
                rw_abschluss_setzen($kw, 'exportiert', rw_wer($me) + ['zeilen' => count($a['zeilen']), 'stueck' => array_sum(array_column($a['zeilen'], 'menge'))]);
            });
            audit('rewe', 'REWE: Excel für WinAB erstellt – ' . rw_kw_text($kw) . ', ' . $a['maerkte'] . ' Einzelaufträge, ' . count($a['zeilen']) . ' Positionen');
            rw_xlsx_senden($datei, 'REWE_WinAB_' . str_replace('-', '_KW', $kw) . '.xlsx');
        }

        /* „In WinAB erfasst“ setzen oder zurücknehmen */
        case 'rewe_erfasst': {
            $me = rw_export_pruefen(true);
            $b = body();
            $kw = rw_kw($b['kw'] ?? '');
            $ja = !empty($b['erfasst']);
            $ab = with_lock('rewe-maerkte', function () use ($kw, $me, $ja) {
                if ($ja && empty(rw_wochen_doc((int)substr($kw, 0, 4))['abschluss'][substr($kw, 5, 2)]['exportiert'])) throw new InvalidArgumentException('Bitte zuerst die Excel-Datei erstellen.');
                return rw_abschluss_setzen($kw, 'erfasst', $ja ? rw_wer($me) : null);
            });
            audit('rewe', 'REWE: ' . rw_kw_text($kw) . ($ja ? ' als in WinAB erfasst markiert' : ' – Haken „in WinAB erfasst“ zurückgenommen'));
            respond(['ok' => true, 'erfasst' => $ab['erfasst'] ?? null]);
        }

        /* Datenpaket der bisherigen Excel-Listen prüfen (vorschau) und übernehmen; Listen → Mitarbeiter über „zuordnung“ */
        case 'rewe_import': {
            $me = require_perm('rewe.verwalten', true);
            $b = body();
            $erg = rw_paket_pruefen($b['paket'] ?? null, $b['zuordnung'] ?? [], $me);
            $leer = rw_leer();
            if (!empty($b['vorschau'])) respond(['ok' => true, 'zahlen' => $erg['zahlen'], 'listen' => (object)$erg['listen'], 'fehler' => $erg['fehler'], 'leer' => $leer]);
            if ($erg['fehler']) respond(['ok' => false, 'error' => 'Das Datenpaket enthält Fehler – nichts übernommen.', 'fehler' => $erg['fehler']], 422);
            with_lock('rewe-maerkte', function () use ($erg, $b) { rw_paket_uebernehmen($erg, !empty($b['ersetzen'])); });
            $z = $erg['zahlen'];
            audit('rewe', 'REWE: Datenpaket übernommen' . ($leer ? '' : ' (vorhandene Daten ersetzt)') . ' – ' . $z['maerkte'] . ' Märkte, ' . $z['antworten'] . ' Wochenantworten, '
                . $z['bestellungen'] . ' Bestellungen, ' . $z['notizen'] . ' Notizen');
            respond(['ok' => true, 'zahlen' => $z]);
        }
}
