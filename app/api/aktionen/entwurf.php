<?php
declare(strict_types=1);
/* Aktionen: Entwurf, gemeinsames Bearbeiten, Veröffentlichen, Versionen
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        /* Entwurf und veröffentlichtes Angebot mit Kundenpreisen: nur mit Modulzugang Angebot (auch über andere Hosts) */
        case 'draft': {
            require_modulzugang('angebot');
            header('Cache-Control: no-store');
            $pub = store_read('angebot');
            $draft = store_read('entwurf');
            respond([
                'ok' => true,
                'published' => $pub,
                'publishedAt' => $pub['publishedAt'] ?? null,
                'draft' => $draft,
                'draftSavedAt' => $draft['savedAt'] ?? null,
                'draftSavedBy' => $draft['savedBy'] ?? null,
                'revision' => draft_rev($draft),
            ]);
        }

        /* Abgleich: Stand des Entwurfs und wer gerade im Eingabebereich ist (alle paar Sekunden) */
        case 'draft_ping': {
            $me = require_auth(true);
            $now = time();
            $pres = store_read('anwesenheit') ?? [];
            $mine = $pres[$me['id']] ?? null;
            if (!is_array($mine) || (int)($mine['at'] ?? 0) < $now - 20 || ($mine['name'] ?? '') !== $me['name']) {
                $pres = with_lock('anwesenheit', function () use ($me, $now) {
                    $l = store_read('anwesenheit') ?? [];
                    foreach ($l as $k => $v) if (!is_array($v) || (int)($v['at'] ?? 0) < $now - 90) unset($l[$k]);
                    $l[$me['id']] = ['name' => $me['name'], 'role' => $me['role'], 'at' => $now];
                    store_write('anwesenheit', $l);
                    return $l;
                });
            }
            $others = [];
            foreach ($pres as $id => $v) if ($id !== $me['id'] && is_array($v) && (int)($v['at'] ?? 0) >= $now - 45) $others[] = ['name' => (string)($v['name'] ?? ''), 'role' => (string)($v['role'] ?? '')];
            usort($others, fn($a, $b) => strcmp($a['name'], $b['name']));
            $draft = store_read('entwurf');
            $pub = store_read('angebot');
            respond(['ok' => true, 'revision' => draft_rev($draft), 'savedBy' => $draft['savedBy'] ?? null, 'savedAt' => $draft['savedAt'] ?? null,
                     'publishedAt' => $pub['publishedAt'] ?? null, 'offersRev' => (int)offers_load()['rev'], 'editors' => $others]);
        }

        case 'save_draft': {
            require_perm('angebot.bearbeiten', true);
            with_lock('entwurf', function () use ($CFG) {
                $b = body();
                $prev = store_read('entwurf');
                $cur = draft_rev($prev);
                if ((int)($b['revision'] ?? -1) !== $cur) draft_conflict($prev);
                $model = clean_model($b['model'] ?? null, false);
                $model['savedAt'] = now();
                $model['savedBy'] = current_user()['name'];
                $model['rev'] = $cur + 1;
                store_write('entwurf', $model);
                $before = $prev ?? store_read('angebot');
                $note = is_array($b['note'] ?? null) ? $b['note'] : null;
                if ($note && ($note['type'] ?? '') === 'import') {
                    $d = changes_between(store_read('angebot'), $model);
                    audit('import', 'Excel importiert: ' . (s($note['file'] ?? '', 120) ?: 'Datei') . ' – KW ' . ($model['meta']['week'] ?? '?') . '/' . ($model['meta']['year'] ?? '?') . ', ' . count($model['items']) . ' Artikel (gegenüber veröffentlicht: ' . changes_summary($d) . ')', array_slice($d, 0, 2000));
                } elseif ($note && ($note['type'] ?? '') === 'cleanup') {
                    $d = changes_between($before, $model);
                    if ($d) audit('draft', 'Merkmale vereinheitlicht (' . count($d) . ' Änderungen: Herkunft als Kürzel, Zustand „frisch“)', array_slice($d, 0, 2000));
                } elseif ($note && ($note['type'] ?? '') === 'kategorien') {
                    $d = changes_between($before, $model);
                    audit('draft', 'Angebot nach den Angebotskategorien geordnet (Stammdaten)' . ($d ? ': ' . changes_summary($d) : ''), array_slice($d, 0, 2000));
                } elseif ($note && ($note['type'] ?? '') === 'master') {
                    $d = changes_between($before, $model);
                    if ($d) audit('draft', 'Stammdaten auf den Entwurf angewendet', array_slice($d, 0, 2000));
                } elseif ($note && ($note['type'] ?? '') === 'aufbau') {
                    // Knopf „Editor“ im Angebot: Reihenfolge der Gruppen und Artikel (gilt für alle Angebote), dabei ggf. Bereich
                    // einer Gruppe oder Gruppe eines Artikels geändert
                    $d = changes_between($before, $model);
                    $nb = count(array_filter($d, function ($c) { return str_ends_with((string)$c['k'], '|section'); }));
                    $ng = count(array_filter($d, function ($c) { return str_ends_with((string)$c['k'], '|groupId'); }));
                    audit('draft', 'Aufbau des Angebots geändert (Reihenfolge der Bereiche, Gruppen und Artikel'
                        . ($nb ? ', Bereich bei ' . $nb . ($nb === 1 ? ' Gruppe' : ' Gruppen') . ' neu' : '')
                        . ($ng ? ', Gruppe bei ' . $ng . ($ng === 1 ? ' Artikel' : ' Artikeln') . ' neu' : '') . ')', array_slice($d, 0, 2000));
                } elseif ($note && ($note['type'] ?? '') === 'version') {
                    audit('import', 'Frühere Veröffentlichung als Entwurf geladen (KW ' . ($model['meta']['week'] ?? '?') . '/' . ($model['meta']['year'] ?? '?') . ')', array_slice(changes_between($before, $model), 0, 2000));
                } else {
                    $d = changes_between($before, $model);
                    if ($d) audit('draft', 'Entwurf bearbeitet', $d, null, true);
                }
                respond(['ok' => true, 'savedAt' => $model['savedAt'], 'revision' => $model['rev']]);
            });
        }

        case 'discard_draft': {
            require_perm('angebot.bearbeiten', true);
            with_lock('entwurf', function () use ($CFG) {
                $dr = store_read('entwurf');
                if (array_key_exists('revision', body()) && (int)body()['revision'] !== draft_rev($dr)) draft_conflict($dr);
                $rev = draft_end($dr, 'verworfen');
                if ($dr) { $d = changes_between($dr, store_read('angebot') ?? $dr); audit('discard', 'Entwurf verworfen' . ($d ? ' (' . changes_summary($d) . ' zurückgenommen)' : ''), array_slice($d, 0, 2000)); }
                respond(['ok' => true, 'revision' => $rev]);
            });
        }

        /* Veröffentlichen (bisherige Stelle: ältere offene Fenster, Tests). Seit 13.11.2026 liegt das Veröffentlichen im Modul
           Versand (versand_veroeffentlichen) – deshalb zusätzlich zum bestehenden Recht der Modulzugang „Versand“ (GR-103).
           Die Arbeit macht angebot_veroeffentlichen() (lib/angebote.php), wie im Modul Versand. */
        case 'publish': {
            require_perm('angebot.veroeffentlichen', true);
            require_modulzugang('versand', true);
            $b = body();
            $r = angebot_veroeffentlichen(is_array($b['model'] ?? null) ? $b['model'] : null, array_key_exists('revision', $b) ? $b['revision'] : null);
            respond(['ok' => true, 'publishedAt' => $r['publishedAt'], 'revision' => $r['revision']]);
        }

        /* Export für WinAB: veröffentlichtes Wochenangebot als CSV (Artikelnummer;Preis, höchster Preis je Nummer) –
           nur mit eigenem Recht, im Protokoll vermerkt (module/angebot/winab-export.php) */
        case 'angebot_winab_export': {
            $me = require_perm('angebot.winab_export', true);
            require_once dirname(__DIR__) . '/module/angebot/winab-export.php';
            $r = winab_export();
            audit('offers', 'Wochenangebot ' . ($r['woche'] !== '' ? $r['woche'] . ' ' : '') . 'für WinAB exportiert – ' . $r['anzahl'] . ' Artikel'
                . ($r['ohnePreis'] ? ', ' . $r['ohnePreis'] . ' ohne Preis ausgelassen' : '') . ($r['doppelt'] ? ', ' . $r['doppelt'] . '× doppelt (höchster Preis)' : ''));
            header('Cache-Control: private, no-store');
            respond(['ok' => true] + $r);
        }

        case 'versions': {
            require_modulzugang('angebot');
            $list = store_names('versionen');
            rsort($list);
            $out = [];
            foreach ($list as $f) {
                $id = basename($f);
                if (!preg_match('/^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$/', $id)) continue;
                $d = store_read('versionen/' . $id);
                if (!$d) continue;
                $out[] = ['id' => $id, 'week' => $d['meta']['week'] ?? null, 'year' => $d['meta']['year'] ?? null,
                          'items' => count($d['items'] ?? []), 'publishedAt' => $d['publishedAt'] ?? null, 'source' => $d['meta']['source'] ?? ''];
            }
            respond(['ok' => true, 'versions' => $out]);
        }

        case 'version': {
            require_modulzugang('angebot');
            $id = (string)($_GET['id'] ?? '');
            if (!preg_match('/^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$/', $id)) fail('Ungültige Version.');
            $d = store_read('versionen/' . $id);
            if (!$d) fail('Version nicht gefunden.', 404);
            respond(['ok' => true, 'model' => $d]);
        }
}
