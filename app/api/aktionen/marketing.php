<?php
declare(strict_types=1);
/* Aktionen: Marketing · Redaktionsplan (Oberfläche marketing.intern, Daten und Regeln in app/api/module/marketing/marketing.php)
   Rechte (GR-103): marketing.sehen – Übersicht, Kalender, Board, Liste, Kampagnen ansehen, CSV;
                    marketing.bearbeiten – Beiträge und Kampagnen anlegen und ändern, kommentieren, Status bis „Zur Freigabe“;
                    marketing.freigeben – Beiträge freigeben (Status „geplant“), zurückstufen;
                    marketing.verwalten – Einstellungen (Marken, Kanäle, Formate, Säulen), Beiträge löschen.
   Gleichzeitiges Bearbeiten: jeder Beitrag trägt „rev“; wer einen veralteten Stand speichert, bekommt 409 mit dem
   aktuellen Beitrag (nichts wird still überschrieben).
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Index eines Beitrags in der Liste oder 404 */
function mkt_index(array $doc, $id): int
{
    $id = is_string($id) ? $id : '';
    foreach ($doc['liste'] as $i => $e) if (($e['id'] ?? '') === $id && $id !== '') return $i;
    fail('Beitrag nicht gefunden.', 404);
    return -1;
}

switch ($action) {
        /* Start: Beiträge, Kampagnen, Einstellungen, wählbare Verantwortliche, eigene Rechte */
        case 'marketing_start': {
            $me = require_perm('marketing.sehen');
            header('Cache-Control: no-store');
            $namen = mkt_team_namen();
            respond(['ok' => true, 'heute' => date('Y-m-d'), 'jetzt' => date('Y-m-d\TH:i'), 'name' => $me['name'], 'ich' => (string)$me['id'],
                     'rechte' => ['bearbeiten' => may($me, 'marketing.bearbeiten'), 'freigeben' => may($me, 'marketing.freigeben'), 'verwalten' => may($me, 'marketing.verwalten')],
                     'status' => MKT_STATUS, 'einstellungen' => mkt_einstellungen(), 'kampagnen' => mkt_kampagnen_doc()['liste'], 'team' => mkt_team(),
                     'beitraege' => array_map(function ($e) use ($namen) { return mkt_beitrag_aus($e, $namen); }, mkt_beitraege_doc()['liste'])]);
        }

        /* Beitrag anlegen (ohne id) oder ändern (id + rev, nur mitgeschickte Felder) */
        case 'marketing_beitrag_save': {
            $me = require_perm('marketing.bearbeiten', true);
            $b = body();
            if (!is_array($b['felder'] ?? null)) fail('Keine Angaben übermittelt.', 422);
            $neuerStatus = array_key_exists('status', $b) ? (string)$b['status'] : null;
            $e = with_lock('marketing-beitraege', function () use ($b, $me, $neuerStatus) {
                $doc = mkt_beitraege_doc(); $einst = mkt_einstellungen(); $kamp = mkt_kampagnen_doc()['liste']; $team = mkt_team();
                $id = (string)($b['id'] ?? '');
                $roh = $b['felder'];
                if ($id !== '') {
                    // unveränderte Felder nicht neu prüfen: eine inzwischen entfernte Marke, ein ausgeschiedener Verantwortlicher
                    // o. Ä. bleibt stehen, solange niemand das Feld ändert
                    $vorher = $doc['liste'][mkt_index($doc, $id)] + mkt_beitrag_leer();
                    foreach ($roh as $k => $v) if (array_key_exists($k, $vorher) && $v === $vorher[$k]) unset($roh[$k]);
                }
                $f = mkt_felder_pruefen($roh, $einst, $kamp, $team);
                if ($id === '') {
                    if (count($doc['liste']) >= MKT_MAX_BEITRAEGE) fail('Zu viele Beiträge (höchstens ' . MKT_MAX_BEITRAEGE . ').', 422);
                    if (($f['titel'] ?? '') === '') throw new InvalidArgumentException('Bitte einen Titel angeben.');
                    $e = array_merge(mkt_beitrag_leer(), $f, ['id' => mkt_id('b'), 'erstellt' => ['t' => now(), 'von' => (string)$me['name'], 'vonId' => (string)$me['id']]]);
                    mkt_verlauf($e, $me, 'angelegt');
                    if ($neuerStatus !== null && $neuerStatus !== 'idee') { $t = mkt_status_setzen($e, $neuerStatus, $me); if ($t !== '') mkt_verlauf($e, $me, $t); }
                    $i = count($doc['liste']); $doc['liste'][] = $e;
                } else {
                    $i = mkt_index($doc, $id);
                    $alt = $doc['liste'][$i] + mkt_beitrag_leer();
                    if (array_key_exists('rev', $b) && (int)$b['rev'] !== (int)$alt['rev'])
                        respond(['ok' => false, 'code' => 'konflikt', 'error' => 'Der Beitrag wurde inzwischen von ' . ($alt['geaendert']['von'] ?? 'jemand anderem') . ' geändert. Bitte die neue Fassung prüfen.',
                                 'beitrag' => mkt_beitrag_aus($alt, mkt_team_namen())], 409);
                    $e = $f + $alt;   // nur mitgeschickte Felder ändern, alle übrigen (auch unbekannte) bleiben
                    $geaendert = array_keys(array_filter($f, function ($v, $k) use ($alt) { return $v !== ($alt[$k] ?? null); }, ARRAY_FILTER_USE_BOTH));
                    if ($neuerStatus === null && !$geaendert) return mkt_beitrag_aus($alt, mkt_team_namen());
                    if ($geaendert) mkt_verlauf($e, $me, 'geändert: ' . implode(', ', $geaendert));
                    // Inhalt eines freigegebenen Beitrags geändert, ohne selbst freigeben zu dürfen → zurück in die Freigabe
                    if ($neuerStatus === null && $alt['status'] === 'geplant' && array_intersect($geaendert, MKT_FREIGABE_FELDER) && !may($me, 'marketing.freigeben')) {
                        $e['status'] = 'freigabe'; $e['freigabe'] = null;
                        mkt_verlauf($e, $me, 'Freigabe zurückgenommen (Inhalt oder Termin geändert) → Zur Freigabe');
                    }
                    if ($neuerStatus !== null) { $t = mkt_status_setzen($e, $neuerStatus, $me); if ($t !== '') mkt_verlauf($e, $me, $t); }
                    if ($e['status'] === 'geplant' && ($e['veroeffentlichung'] === '' || !$e['kanaele'])) throw new InvalidArgumentException('Ein freigegebener Beitrag braucht Kanal und Veröffentlichungstermin.');
                    $doc['liste'][$i] = $e;
                }
                if (($e['verantwortlich'] ?? '') !== '') foreach ($team as $t) if ($t['id'] === $e['verantwortlich']) $e['verantwortlichSchnappschuss'] = $t['name'];
                $e['rev'] = (int)($e['rev'] ?? 0) + 1;
                $e['geaendert'] = ['t' => now(), 'von' => (string)$me['name']];
                $doc['liste'][$i] = $e;
                mkt_schreiben('marketing-beitraege', $doc);
                return mkt_beitrag_aus($e, mkt_team_namen());
            });
            audit('marketing', 'Marketing: Beitrag „' . $e['titel'] . '“ gespeichert (' . (MKT_STATUS[$e['status']] ?? $e['status']) . ')');
            respond(['ok' => true, 'beitrag' => $e]);
        }

        /* Kommentar zu einem Beitrag */
        case 'marketing_kommentar': {
            $me = require_perm('marketing.bearbeiten', true);
            $b = body();
            $text = mkt_text($b['text'] ?? '', 2000, 'Kommentar');
            if ($text === '') fail('Bitte einen Kommentar eingeben.', 422);
            $e = with_lock('marketing-beitraege', function () use ($b, $me, $text) {
                $doc = mkt_beitraege_doc();
                $i = mkt_index($doc, $b['id'] ?? '');
                $e = $doc['liste'][$i] + mkt_beitrag_leer();
                $e['kommentare'][] = ['id' => mkt_id('c'), 't' => now(), 'von' => (string)$me['name'], 'vonId' => (string)$me['id'], 'text' => $text];
                if (count($e['kommentare']) > MKT_MAX_KOMMENTARE) $e['kommentare'] = array_slice($e['kommentare'], -MKT_MAX_KOMMENTARE);
                $e['rev'] = (int)$e['rev'] + 1;
                $doc['liste'][$i] = $e;
                mkt_schreiben('marketing-beitraege', $doc);
                return mkt_beitrag_aus($e, mkt_team_namen());
            });
            respond(['ok' => true, 'beitrag' => $e]);
        }

        /* Beitrag endgültig löschen (sonst: Status „Verworfen“) */
        case 'marketing_beitrag_loeschen': {
            $me = require_perm('marketing.verwalten', true);
            $b = body();
            $titel = with_lock('marketing-beitraege', function () use ($b) {
                $doc = mkt_beitraege_doc();
                $i = mkt_index($doc, $b['id'] ?? '');
                $t = (string)$doc['liste'][$i]['titel'];
                array_splice($doc['liste'], $i, 1);
                mkt_schreiben('marketing-beitraege', $doc);
                return $t;
            });
            audit('marketing', 'Marketing: Beitrag „' . $titel . '“ gelöscht');
            respond(['ok' => true]);
        }

        /* Kampagne anlegen oder ändern (Archivieren statt Löschen: Beiträge behalten ihre Kampagne) */
        case 'marketing_kampagne_save': {
            $me = require_perm('marketing.bearbeiten', true);
            $b = body();
            $k = with_lock('marketing-beitraege', function () use ($b, $me) {
                $doc = mkt_kampagnen_doc(); $einst = mkt_einstellungen();
                $id = (string)($b['id'] ?? ''); $idx = null;
                foreach ($doc['liste'] as $i => $x) if (($x['id'] ?? '') === $id && $id !== '') $idx = $i;
                if ($id !== '' && $idx === null) fail('Kampagne nicht gefunden.', 404);
                if ($idx === null && count($doc['liste']) >= MKT_MAX_KAMPAGNEN) fail('Zu viele Kampagnen.', 422);
                $row = mkt_kampagne_pruefen($b, $idx !== null ? $doc['liste'][$idx] : null, $einst);
                $row = ['id' => $idx !== null ? $doc['liste'][$idx]['id'] : mkt_id('k')] + $row + ['erstellt' => ['t' => now(), 'von' => (string)$me['name']]];
                if ($idx === null) $doc['liste'][] = $row; else $doc['liste'][$idx] = $row;
                mkt_schreiben('marketing-kampagnen', $doc);
                return $row;
            });
            audit('marketing', 'Marketing: Kampagne „' . $k['name'] . '“ gespeichert');
            respond(['ok' => true, 'kampagne' => $k, 'kampagnen' => mkt_kampagnen_doc()['liste']]);
        }

        /* Einstellungen: Marken, Kanäle, Formate, Content-Säulen */
        case 'marketing_einstellungen_save': {
            $me = require_perm('marketing.verwalten', true);
            $b = body();
            $einst = with_lock('marketing-beitraege', function () use ($b) {
                $alt = mkt_einstellungen();
                $neu = $alt;
                $neu['marken'] = mkt_liste_pruefen($b['marken'] ?? $alt['marken'], 'Marken', true, false, $alt['marken']);
                $neu['kanaele'] = mkt_liste_pruefen($b['kanaele'] ?? $alt['kanaele'], 'Kanäle', false, true, $alt['kanaele']);
                $neu['formate'] = mkt_liste_pruefen($b['formate'] ?? $alt['formate'], 'Formate', false, false, $alt['formate']);
                $neu['saeulen'] = mkt_liste_pruefen($b['saeulen'] ?? $alt['saeulen'], 'Content-Säulen', true, false, $alt['saeulen']);
                mkt_schreiben('marketing-einstellungen', $neu);
                return mkt_einstellungen();
            });
            audit('marketing', 'Marketing: Einstellungen gespeichert');
            respond(['ok' => true, 'einstellungen' => $einst]);
        }

        /* Liste als CSV (Excel), im Protokoll vermerkt */
        case 'marketing_export': {
            $me = require_perm('marketing.sehen', true);
            $namen = mkt_team_namen();
            $liste = array_map(function ($e) use ($namen) { return mkt_beitrag_aus($e, $namen); }, mkt_beitraege_doc()['liste']);
            usort($liste, function ($a, $b) { return [$a['veroeffentlichung'] === '' ? 1 : 0, $a['veroeffentlichung'], $a['titel']] <=> [$b['veroeffentlichung'] === '' ? 1 : 0, $b['veroeffentlichung'], $b['titel']]; });
            audit('marketing', 'Marketing: Redaktionsplan als CSV heruntergeladen (' . count($liste) . ' Beiträge)');
            header('Content-Type: text/csv; charset=utf-8');
            header('Content-Disposition: attachment; filename="Redaktionsplan_' . date('Y-m-d') . '.csv"');
            header('Cache-Control: private, no-store');
            header('X-Content-Type-Options: nosniff');
            echo mkt_csv($liste, mkt_einstellungen(), mkt_kampagnen_doc()['liste']);
            exit;
        }
}
