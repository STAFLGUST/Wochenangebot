<?php
declare(strict_types=1);
/* Aktionen: QM-System (Oberfläche qs.intern, Daten und Regeln in app/api/module/qs/qs.php)
   Rechte (GR-103): qs.sehen – Übersicht, Dokumente mit Versionen, Handbuch, Prüfplan mit Nachweisen, Maßnahmen, CSV;
                    qs.nachweis – Kontrollen durchführen: Nachweise für die eigenen (zugewiesenen) Prüfungen erfassen,
                                  eigene Nachweise stornieren;
                    qs.bearbeiten – Dokumente anlegen, Entwürfe schreiben, zur Prüfung geben, verwerfen; Nachweise aller
                                    Prüfungen erfassen und stornieren; Maßnahmen erfassen und bis „umgesetzt“ führen;
                    qs.freigeben – Entwürfe prüfen (nie eigene: 4-Augen-Prinzip, auch für Administratoren), freigeben,
                                   zurückgeben, Dokumente einziehen und „ohne Änderung überprüft“ vermerken; Handbuch und
                                   Prüfplan ändern (auch Zuweisung an Mitarbeiter); Maßnahmen als wirksam abschließen,
                                   verwerfen oder wieder öffnen;
                    qs.verwalten – Kapitel, Personen (Kürzel, Verknüpfung mit Mitarbeitern) und Einstellungen pflegen,
                                   Datenpaket übernehmen.
   Dokumentenablage (lib/dateiablage.php): Dateien herunterladen und als ZIP exportieren mit qs.sehen; im Entwurf und an
   Ordnern/externen Dokumenten ablegen und entfernen mit qs.bearbeiten; zu freigegebenen Versionen nachtragen und entfernen
   (nur vermerkt, mit Grund) mit qs.freigeben – Regeln in qs_ablage_stelle().
   Gleichzeitiges Bearbeiten: Dokumente, Abschnitte, Prüfungen und Maßnahmen tragen „rev“; ein veralteter Stand bekommt 409.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Index eines Eintrags einer Liste oder 404 */
function qs_index(array $doc, $id, string $was): int
{
    $id = is_string($id) ? $id : '';
    foreach ($doc['liste'] as $i => $e) if (($e['id'] ?? '') === $id && $id !== '') return $i;
    fail("$was nicht gefunden.", 404);
    return -1;
}
/* Veralteter Stand eines Eintrags → 409 mit dem aktuellen Eintrag */
function qs_rev_pruefen(array $b, array $alt, string $was): void
{
    if (array_key_exists('rev', $b) && (int)$b['rev'] !== (int)($alt['rev'] ?? 0))
        respond(['ok' => false, 'code' => 'konflikt', 'error' => "$was wurde inzwischen von " . ($alt['geaendert']['von'] ?? 'jemand anderem') . ' geändert. Bitte neu laden.', 'eintrag' => $alt], 409);
}
function qs_dok_name(array $d): string { return trim(($d['nr'] !== '' ? $d['nr'] . ' ' : '') . $d['titel']); }
function qs_dok_antwort(array $d): array { return qs_dok_aus($d, (int)qs_stamm()['einstellungen']['ueberpruefungMonate'], qs_heute()); }
/* Dokument speichern: Stand hochzählen, „geändert“ setzen */
function qs_dok_ablegen(array &$doc, int $i, array $d, array $me): array
{
    $d['rev'] = (int)($d['rev'] ?? 0) + 1;
    $d['geaendert'] = qs_wer($me);
    $doc['liste'][$i] = $d;
    qs_schreiben('qs-dokumente', $doc);
    return $d;
}

switch ($action) {
        /* Start: Stammdaten, Dokumente, Handbuch, Prüfplan mit Fälligkeiten, neueste Nachweise, Maßnahmen, eigene Rechte */
        case 'qs_start': {
            $me = require_perm('qs.sehen');
            header('Cache-Control: no-store');
            $heute = qs_heute();
            $stamm = qs_stamm();
            $nachweise = qs_doc('qs-nachweise')['liste'];
            $handbuch = qs_doc('qs-handbuch')['liste'];
            qs_abschnitte_sortieren($handbuch);
            usort($nachweise, function ($a, $b) { return [$b['datum'], $b['erfasst']['t'] ?? ''] <=> [$a['datum'], $a['erfasst']['t'] ?? '']; });
            $dokumente = qs_doc('qs-dokumente')['liste'];
            $monate = (int)$stamm['einstellungen']['ueberpruefungMonate'];
            respond(['ok' => true, 'heute' => $heute, 'ich' => ['id' => (string)$me['id'], 'name' => (string)$me['name'], 'kuerzel' => qs_kuerzel_von($stamm, (string)$me['id'])],
                     'rechte' => ['nachweis' => may($me, 'qs.nachweis'), 'bearbeiten' => may($me, 'qs.bearbeiten'), 'freigeben' => may($me, 'qs.freigeben'), 'verwalten' => may($me, 'qs.verwalten')],
                     'arten' => QS_ARTEN, 'gelenkt' => QS_GELENKT, 'verStatus' => QS_VER_STATUS, 'intervalle' => QS_INTERVALLE, 'ergebnisse' => QS_ERGEBNIS,
                     'quellen' => QS_QUELLEN, 'bewertungen' => QS_BEWERTUNG, 'massnStatus' => QS_MASSN_STATUS,
                     'kapitel' => $stamm['kapitel'], 'personen' => $stamm['personen'], 'einstellungen' => $stamm['einstellungen'], 'mitarbeiter' => qs_mitarbeiter(),
                     'dokumente' => array_map(function ($d) use ($monate, $heute) { return qs_dok_aus($d, $monate, $heute); }, $dokumente),
                     'handbuch' => $handbuch,
                     'pruefungen' => qs_pruefungen_aus(qs_doc('qs-pruefplan')['liste'], $nachweise, $heute),
                     'nachweise' => array_slice($nachweise, 0, QS_START_NACHWEISE), 'nachweiseGesamt' => count($nachweise),
                     'massnahmen' => array_map(function ($m) use ($heute) { return qs_massnahme_aus($m, $heute); }, qs_doc('qs-massnahmen')['liste']),
                     'leer' => qs_leer(), 'ablage' => qs_ablage_einstellungen()]);
        }

        /* Dokumentenliste, Prüfplan oder Maßnahmen als CSV (Excel), im Protokoll vermerkt */
        case 'qs_export': {
            require_perm('qs.sehen', true);
            $b = body();
            $liste = qs_wahl($b['liste'] ?? 'dokumente', ['dokumente', 'pruefplan', 'massnahmen'], 'Liste');
            $heute = qs_heute();
            if ($liste === 'dokumente') { $daten = qs_doc('qs-dokumente')['liste']; $csv = qs_csv_dokumente($daten, qs_stamm(), $heute); $name = 'QM-Dokumentenliste'; }
            elseif ($liste === 'pruefplan') {
                $daten = qs_pruefungen_aus(qs_doc('qs-pruefplan')['liste'], qs_doc('qs-nachweise')['liste'], $heute);
                $namen = []; foreach (qs_mitarbeiter() as $m) $namen[$m['id']] = $m['name'];
                $csv = qs_csv_pruefplan($daten, $namen); $name = 'QM-Pruefplan';
            }
            else { $daten = qs_doc('qs-massnahmen')['liste']; $csv = qs_csv_massnahmen($daten); $name = 'QM-Massnahmen'; }
            audit('qs', 'QM-System: ' . ['dokumente' => 'Dokumentenliste', 'pruefplan' => 'Prüfplan', 'massnahmen' => 'Maßnahmen'][$liste] . ' als CSV heruntergeladen (' . count($daten) . ' Einträge)');
            header('Content-Type: text/csv; charset=utf-8');
            header('Content-Disposition: attachment; filename="' . $name . '_' . $heute . '.csv"');
            header('Cache-Control: private, no-store');
            header('X-Content-Type-Options: nosniff');
            echo $csv;
            exit;
        }

        /* Dokument anlegen (ohne id; gelenkte Arten bekommen gleich einen Entwurf) oder Angaben ändern (id + rev);
           Einziehen und wieder gültig machen nur mit „qs.freigeben“ (offene Entwürfe werden dabei verworfen) */
        case 'qs_dokument_save': {
            $me = require_perm('qs.bearbeiten', true);
            $b = body();
            [$d, $was] = with_lock('qs-dokumente', function () use ($b, $me) {
                $stamm = qs_stamm(); $doc = qs_doc('qs-dokumente');
                $id = (string)($b['id'] ?? ''); $alt = null; $i = null;
                if ($id !== '') { $i = qs_dokument_index($doc, $id); $alt = $doc['liste'][$i]; qs_rev_pruefen($b, $alt, 'Das Dokument'); }
                elseif (count($doc['liste']) >= QS_MAX_DOKUMENTE) fail('Zu viele Dokumente.', 422);
                $d = qs_dokument_pruefen($b, $alt, $stamm, $doc['liste']);
                $was = 'gespeichert';
                if ($alt === null) {
                    $d = ['id' => qs_id('d')] + $d + ['erstellt' => qs_wer($me), 'quelle' => 'hand', 'verlauf' => []];
                    qs_verlauf($d, $me, 'angelegt');
                    if (in_array($d['art'], QS_GELENKT, true)) $d['versionen'][] = qs_entwurf($me, qs_text($b['aenderungen'] ?? '', 2000, 'Änderungen') ?: 'Neu angelegt', qs_text($b['grund'] ?? '', 1000, 'Änderungsgrund'));
                    $was = 'angelegt';
                } else {
                    foreach (['nr', 'titel', 'kapitel', 'art', 'ablage', 'zustaendig', 'vertreter'] as $f)
                        if ((string)($alt[$f] ?? '') !== (string)$d[$f]) qs_verlauf($d, $me, ['nr' => 'Dokumenten-Nr.', 'titel' => 'Titel', 'kapitel' => 'Kapitel', 'art' => 'Art', 'ablage' => 'Ablage', 'zustaendig' => 'Zuständig', 'vertreter' => 'Vertreter'][$f] . ' geändert');
                }
                if (array_key_exists('eingezogen', $b) && (bool)$b['eingezogen'] !== !empty($d['eingezogen'])) {
                    if (!may($me, 'qs.freigeben')) fail('Einziehen und wieder gültig machen darf nur, wer prüfen und freigeben darf.', 403);
                    if ($alt === null) fail('Ein neues Dokument kann nicht gleich eingezogen werden.', 422);
                    if (!empty($b['eingezogen'])) {
                        $grund = qs_text($b['einzugGrund'] ?? '', 500, 'Grund');
                        if ($grund === '') throw new InvalidArgumentException('Bitte einen Grund für das Einziehen angeben.');
                        foreach ($d['versionen'] as &$v) if (in_array($v['status'], QS_VER_OFFEN, true)) { $v['status'] = 'verworfen'; qs_verlauf($v, $me, 'verworfen (Dokument eingezogen)'); }
                        unset($v);
                        $d['eingezogen'] = qs_wer($me) + ['grund' => $grund];
                        qs_verlauf($d, $me, 'eingezogen: ' . $grund);
                        $was = 'eingezogen';
                    } else {
                        $d['eingezogen'] = null;
                        qs_verlauf($d, $me, 'wieder gültig');
                        $was = 'wieder gültig';
                    }
                }
                if ($i === null) { $doc['liste'][] = $d; $i = count($doc['liste']) - 1; }
                $d = qs_dok_ablegen($doc, $i, $d, $me);
                return [$d, $was];
            });
            audit('qs', 'QM-System: Dokument ' . qs_dok_name($d) . ' ' . $was);
            respond(['ok' => true, 'dokument' => qs_dok_antwort($d)]);
        }

        /* Entwurf einer neuen Version anlegen oder ändern (Änderungen und Änderungsgrund, Handbuch 2.0.11) */
        case 'qs_version_save': {
            $me = require_perm('qs.bearbeiten', true);
            $b = body();
            $d = with_lock('qs-dokumente', function () use ($b, $me) {
                $doc = qs_doc('qs-dokumente');
                $i = qs_dokument_index($doc, $b['dokument'] ?? '');
                $d = $doc['liste'][$i];
                qs_rev_pruefen($b, $d, 'Das Dokument');
                if (!in_array($d['art'], QS_GELENKT, true)) fail('Ordner und externe Dokumente haben keine Versionen.', 422);
                if (!empty($d['eingezogen'])) fail('Das Dokument ist eingezogen. Zuerst wieder gültig machen.', 409);
                $aend = qs_text($b['aenderungen'] ?? '', 2000, 'Änderungen');
                $grund = qs_text($b['grund'] ?? '', 1000, 'Änderungsgrund');
                $gueltig = qs_ver_index($d, ['freigegeben']);
                if ($gueltig !== null && ($aend === '' || $grund === '')) throw new InvalidArgumentException('Bitte Änderungen und Änderungsgrund in Stichworten angeben.');
                if ($aend === '') $aend = 'Neu angelegt';
                $o = qs_ver_index($d, QS_VER_OFFEN);
                if ($o !== null) {
                    $v = $d['versionen'][$o];
                    if ($v['status'] !== 'entwurf') fail('Die Überarbeitung liegt zur Prüfung vor und kann nicht mehr geändert werden.', 409);
                    if ($v['aenderungen'] === $aend && $v['grund'] === $grund) return $d;
                    $v['aenderungen'] = $aend; $v['grund'] = $grund;
                    if (!in_array((string)$me['id'], (array)$v['bearbeiter'], true)) $v['bearbeiter'][] = (string)$me['id'];
                    qs_verlauf($v, $me, 'Entwurf geändert');
                    $d['versionen'][$o] = $v;
                } else {
                    if (count($d['versionen']) >= QS_MAX_VERSIONEN) fail('Zu viele Versionen.', 422);
                    $d['versionen'][] = qs_entwurf($me, $aend, $grund);
                    qs_verlauf($d, $me, 'Überarbeitung begonnen');
                }
                return qs_dok_ablegen($doc, $i, $d, $me);
            });
            audit('qs', 'QM-System: Entwurf für ' . qs_dok_name($d) . ' gespeichert');
            respond(['ok' => true, 'dokument' => qs_dok_antwort($d)]);
        }

        /* Ablauf einer Version: einreichen (Entwurf → in Prüfung), zurueck (an den Ersteller, mit Grund), pruefen,
           freigeben, pruefen_freigeben (beides in einem Schritt), verwerfen (nur Entwürfe).
           4-Augen-Prinzip: wer den Entwurf erstellt oder geändert hat, prüft ihn nicht (Handbuch 2.0.14). */
        case 'qs_version_schritt': {
            $b = body();
            $schritt = is_string($b['schritt'] ?? null) ? $b['schritt'] : '';
            $rechte = ['einreichen' => 'qs.bearbeiten', 'verwerfen' => 'qs.bearbeiten', 'zurueck' => 'qs.freigeben', 'pruefen' => 'qs.freigeben', 'freigeben' => 'qs.freigeben',
                       'pruefen_freigeben' => 'qs.freigeben', 'ueberprueft' => 'qs.freigeben'];
            if (!isset($rechte[$schritt])) { require_perm('qs.bearbeiten', true); fail('Unbekannter Schritt.', 422); }
            $me = require_perm($rechte[$schritt], true);
            [$d, $text] = with_lock('qs-dokumente', function () use ($b, $me, $schritt) {
                $doc = qs_doc('qs-dokumente');
                $i = qs_dokument_index($doc, $b['dokument'] ?? '');
                $d = $doc['liste'][$i];
                qs_rev_pruefen($b, $d, 'Das Dokument');
                if ($schritt === 'ueberprueft') {   // Überprüfung ohne Änderung (Handbuch 2.0: regelmäßig überarbeiten) – setzt die Frist neu
                    if (!empty($d['eingezogen']) || qs_ver_index($d, ['freigegeben']) === null) fail('Überprüfen lässt sich nur ein gültiges Dokument.', 409);
                    $notiz = qs_text($b['grund'] ?? '', 500, 'Notiz');
                    $d['ueberprueft'] = qs_wer($me) + ['notiz' => $notiz];
                    qs_verlauf($d, $me, 'ohne Änderung überprüft' . ($notiz !== '' ? ': ' . $notiz : ''));
                    return [qs_dok_ablegen($doc, $i, $d, $me), 'ohne Änderung überprüft'];
                }
                $o = qs_ver_index($d, QS_VER_OFFEN);
                if ($o === null) fail('Für dieses Dokument liegt kein Entwurf vor.', 409);
                $v = $d['versionen'][$o];
                $braucht = ['einreichen' => ['entwurf'], 'verwerfen' => ['entwurf'], 'zurueck' => ['pruefung', 'geprueft'], 'pruefen' => ['pruefung'],
                            'freigeben' => ['geprueft'], 'pruefen_freigeben' => ['pruefung']][$schritt];
                if (!in_array($v['status'], $braucht, true)) fail('Dieser Schritt passt nicht zum Stand der Version (' . (QS_VER_STATUS[$v['status']] ?? $v['status']) . ').', 409);
                $eigen = in_array((string)$me['id'], array_map('strval', (array)($v['bearbeiter'] ?? [])), true);
                if (in_array($schritt, ['pruefen', 'pruefen_freigeben'], true) && $eigen)
                    fail('4-Augen-Prinzip: Erstellung/Überarbeitung und Prüfung müssen durch zwei verschiedene Personen erfolgen.', 403);
                // (bewusst if/elseif statt switch: „case '…'“ hält das Regelwerk für API-Aktionen)
                if ($schritt === 'einreichen') { $v['status'] = 'pruefung'; qs_verlauf($v, $me, 'zur Prüfung gegeben'); $text = 'zur Prüfung gegeben'; }
                elseif ($schritt === 'verwerfen') {
                    $v['status'] = 'verworfen'; $g = qs_text($b['grund'] ?? '', 500, 'Grund');
                    qs_verlauf($v, $me, 'verworfen' . ($g !== '' ? ': ' . $g : '')); $text = 'Entwurf verworfen';
                } elseif ($schritt === 'zurueck') {
                    $g = qs_text($b['grund'] ?? '', 500, 'Grund');
                    if ($g === '') throw new InvalidArgumentException('Bitte angeben, was am Entwurf zu ändern ist.');
                    $v['status'] = 'entwurf'; $v['geprueft'] = null; qs_verlauf($v, $me, 'zurückgegeben: ' . $g); $text = 'zur Überarbeitung zurückgegeben';
                } elseif ($schritt === 'pruefen') { $v['status'] = 'geprueft'; $v['geprueft'] = qs_wer($me); qs_verlauf($v, $me, 'geprüft'); $text = 'geprüft'; }
                else {   // freigeben, pruefen_freigeben
                    if (!empty($d['eingezogen'])) fail('Das Dokument ist eingezogen.', 409);
                    if ($schritt === 'pruefen_freigeben') { $v['geprueft'] = qs_wer($me); qs_verlauf($v, $me, 'geprüft'); }
                    $nr = qs_naechste_nr($d);
                    $g = qs_ver_index($d, ['freigegeben']);
                    if ($g !== null) { $d['versionen'][$g]['status'] = 'ersetzt'; qs_verlauf($d['versionen'][$g], $me, "ersetzt durch Version $nr"); }
                    $v['status'] = 'freigegeben'; $v['nr'] = $nr; $v['datum'] = qs_heute(); $v['freigegeben'] = qs_wer($me);
                    qs_verlauf($v, $me, "freigegeben als Version $nr");
                    qs_verlauf($d, $me, "Version $nr freigegeben");
                    $text = "Version $nr freigegeben";
                }
                $d['versionen'][$o] = $v;
                return [qs_dok_ablegen($doc, $i, $d, $me), $text];
            });
            audit('qs', 'QM-System: ' . qs_dok_name($d) . ' – ' . $text);
            respond(['ok' => true, 'dokument' => qs_dok_antwort($d)]);
        }

        /* Datei ablegen – in Teilen (lib/dateiablage.php): dokument, version ('' bei Ordnern/externen Dokumenten), name,
           groesse, sha256, upload ('' beim ersten Teil), teil, daten (Base64). Vor dem ersten Teil und beim Eintragen prüft
           qs_ablage_stelle(), ob hier abgelegt werden darf. Antwort: fertig=false mit upload, bis der letzte Teil da ist. */
        case 'qs_datei_hochladen': {
            $me = require_perm('qs.bearbeiten', true);
            require_once __DIR__ . '/../lib/dateiablage.php';
            $b = body();
            $dok = is_string($b['dokument'] ?? null) ? $b['dokument'] : ''; $ver = is_string($b['version'] ?? null) ? $b['version'] : '';
            if (($b['upload'] ?? '') === '') { $doc = qs_doc('qs-dokumente'); qs_ablage_stelle($doc['liste'][qs_dokument_index($doc, $dok)], $ver, $me, 'hochladen'); }
            $r = ablage_teil('qs', (string)$me['id'], ['dokument' => $dok, 'version' => $ver], $b);
            if (!$r['fertig']) respond(['ok' => true, 'fertig' => false, 'upload' => $r['upload'], 'empfangen' => $r['empfangen']]);
            $datei = $r['datei'];
            // Scheitert das Eintragen (fail/Ausnahme), bleibt keine verwaiste Datei zurück
            $eingetragen = false;
            register_shutdown_function(function () use (&$eingetragen, $datei) { if (!$eingetragen) { try { ablage_entfernen('qs', $datei['id']); } catch (Throwable $e) { /* bleibt liegen */ } } });
            $d = with_lock('qs-dokumente', function () use ($dok, $ver, $me, $datei) {
                $doc = qs_doc('qs-dokumente');
                $i = qs_dokument_index($doc, $dok);
                $d = $doc['liste'][$i];
                $vi = qs_ablage_stelle($d, $ver, $me, 'hochladen');
                $f = ['id' => $datei['id'], 'name' => $datei['name'], 'art' => $datei['art'], 'mime' => $datei['mime'], 'groesse' => $datei['groesse'],
                      'sha256' => $datei['sha256'], 'hochgeladen' => qs_wer($me)];
                if ($vi === null) {
                    $d['dateien'] = is_array($d['dateien'] ?? null) ? array_values($d['dateien']) : [];
                    $d['dateien'][] = $f;
                    qs_verlauf($d, $me, 'Datei abgelegt: ' . $datei['name']);
                } else {
                    $v = $d['versionen'][$vi];
                    $v['dateien'] = is_array($v['dateien'] ?? null) ? array_values($v['dateien']) : [];
                    if ($v['status'] === 'entwurf') {
                        if (!in_array((string)$me['id'], array_map('strval', (array)($v['bearbeiter'] ?? [])), true)) $v['bearbeiter'][] = (string)$me['id'];   // 4-Augen-Prinzip
                        qs_verlauf($v, $me, 'Datei abgelegt: ' . $datei['name']);
                    } else {
                        $f['nachgetragen'] = true;
                        qs_verlauf($v, $me, 'Datei nachgetragen: ' . $datei['name']);
                        qs_verlauf($d, $me, 'Datei zu Version ' . ($v['nr'] ?? '?') . ' nachgetragen: ' . $datei['name']);
                    }
                    $v['dateien'][] = $f;
                    $d['versionen'][$vi] = $v;
                }
                return qs_dok_ablegen($doc, $i, $d, $me);
            });
            $eingetragen = true;
            audit('qs', 'QM-System: Datei für ' . qs_dok_name($d) . ' abgelegt (' . round($datei['groesse'] / 1024) . ' KB)');
            respond(['ok' => true, 'fertig' => true, 'datei' => $datei['id'], 'dokument' => qs_dok_antwort($d)]);
        }

        /* Datei entfernen: im Entwurf und an Ordnern/externen Dokumenten (qs.bearbeiten) – im Entwurf endgültig gelöscht;
           bei Ordnern/externen Dokumenten und freigegebenen Versionen (qs.freigeben) nur als „entfernt“ vermerkt (mit Grund),
           die Datei bleibt in der Ablage */
        case 'qs_datei_entfernen': {
            $me = require_perm('qs.bearbeiten', true);
            require_once __DIR__ . '/../lib/dateiablage.php';
            $b = body();
            [$d, $name, $loeschen] = with_lock('qs-dokumente', function () use ($b, $me) {
                $doc = qs_doc('qs-dokumente');
                $ort = qs_datei_finden($doc['liste'], is_string($b['datei'] ?? null) ? $b['datei'] : '');
                if ($ort === null) fail('Datei nicht gefunden.', 404);
                [$i, $vi, $k] = $ort;
                $d = $doc['liste'][$i];
                qs_rev_pruefen($b, $d, 'Das Dokument');
                qs_ablage_stelle($d, $vi === null ? '' : (string)$d['versionen'][$vi]['id'], $me, 'entfernen');
                $f = $vi === null ? $d['dateien'][$k] : $d['versionen'][$vi]['dateien'][$k];
                if (!empty($f['entfernt'])) fail('Die Datei ist schon entfernt.', 409);
                $entwurf = $vi !== null && $d['versionen'][$vi]['status'] === 'entwurf';
                $grund = qs_text($b['grund'] ?? '', 500, 'Grund');
                if (!$entwurf && $grund === '') throw new InvalidArgumentException('Bitte einen Grund angeben – die Datei bleibt als „entfernt“ vermerkt.');
                if ($entwurf) {
                    $v = $d['versionen'][$vi];
                    array_splice($v['dateien'], $k, 1);
                    if (!in_array((string)$me['id'], array_map('strval', (array)($v['bearbeiter'] ?? [])), true)) $v['bearbeiter'][] = (string)$me['id'];
                    qs_verlauf($v, $me, 'Datei entfernt: ' . $f['name']);
                    $d['versionen'][$vi] = $v;
                } else {
                    $f['entfernt'] = qs_wer($me) + ['grund' => $grund];
                    if ($vi === null) { $d['dateien'][$k] = $f; qs_verlauf($d, $me, 'Datei entfernt: ' . $f['name'] . ' – ' . $grund); }
                    else {
                        $d['versionen'][$vi]['dateien'][$k] = $f;
                        qs_verlauf($d['versionen'][$vi], $me, 'Datei entfernt: ' . $f['name'] . ' – ' . $grund);
                        qs_verlauf($d, $me, 'Datei aus Version ' . ($d['versionen'][$vi]['nr'] ?? '?') . ' entfernt: ' . $f['name'] . ' – ' . $grund);
                    }
                }
                return [qs_dok_ablegen($doc, $i, $d, $me), (string)$f['name'], $entwurf ? (string)$f['id'] : ''];
            });
            if ($loeschen !== '') ablage_entfernen('qs', $loeschen);   // erst nach dem Speichern: im Fehlerfall bleibt die Datei
            audit('qs', 'QM-System: Datei aus ' . qs_dok_name($d) . ($loeschen !== '' ? ' gelöscht (Entwurf)' : ' entfernt (vermerkt)'));
            respond(['ok' => true, 'dokument' => qs_dok_antwort($d)]);
        }

        /* Datei herunterladen (GET, id) – immer als Download; entfernte Dateien nicht */
        case 'qs_datei': {
            require_perm('qs.sehen');
            require_once __DIR__ . '/../lib/dateiablage.php';
            $liste = qs_doc('qs-dokumente')['liste'];
            $ort = qs_datei_finden($liste, is_string($_GET['id'] ?? null) ? $_GET['id'] : '');
            if ($ort === null) fail('Datei nicht gefunden.', 404);
            [$i, $vi, $k] = $ort;
            $f = $vi === null ? $liste[$i]['dateien'][$k] : $liste[$i]['versionen'][$vi]['dateien'][$k];
            if (!empty($f['entfernt'])) fail('Die Datei wurde entfernt.', 404);
            ablage_senden('qs', (string)$f['id'], (string)$f['name'], (string)($f['mime'] ?? ''));
        }

        /* Ablage als ZIP (GET): „QM-System/<Kapitel>/<Dokument>/<Datei>“ mit der Dokumentenliste; kapitel = nur ein Kapitel,
           alle=1 = auch ältere Versionen, Entwürfe und eingezogene Dokumente. Im Protokoll vermerkt. */
        case 'qs_ablage_export': {
            require_perm('qs.sehen');
            require_once __DIR__ . '/../lib/dateiablage.php';
            $stamm = qs_stamm();
            $kapitel = is_string($_GET['kapitel'] ?? null) ? $_GET['kapitel'] : '';
            if ($kapitel !== '') qs_kapitel_pruefen($kapitel, $stamm);
            $alle = ($_GET['alle'] ?? '') === '1';
            $heute = qs_heute();
            $e = qs_ablage_eintraege(qs_doc('qs-dokumente')['liste'], $stamm, $kapitel, $alle, $heute);
            audit('qs', 'QM-System: Dokumentenablage als ZIP heruntergeladen (' . (count($e) - 1) . ' Dateien' . ($kapitel !== '' ? ', Kapitel ' . $kapitel : '') . ($alle ? ', mit älteren Versionen' : '') . ')');
            ablage_zip_senden('QM-System_' . ($kapitel !== '' ? ablage_zip_pfad($kapitel) . '_' : '') . $heute . '.zip', $e);
        }

        /* Abschnitt des QM-Handbuchs anlegen (ohne id) oder ändern (id + rev): jede inhaltliche Änderung mit Grund in der
           Änderungsliste; „entfallen“ statt löschen */
        case 'qs_abschnitt_save': {
            $me = require_perm('qs.freigeben', true);
            $b = body();
            [$a, $was] = with_lock('qs-dokumente', function () use ($b, $me) {
                $stamm = qs_stamm(); $doc = qs_doc('qs-handbuch');
                $id = (string)($b['id'] ?? ''); $alt = null; $i = null;
                if ($id !== '') { $i = qs_index($doc, $id, 'Abschnitt'); $alt = $doc['liste'][$i]; qs_rev_pruefen($b, $alt, 'Der Abschnitt'); }
                elseif (count($doc['liste']) >= QS_MAX_ABSCHNITTE) fail('Zu viele Abschnitte.', 422);
                $felder = qs_abschnitt_felder($b, $stamm);
                $aend = qs_text($b['aenderung'] ?? '', 1000, 'Änderung');
                $grund = qs_text($b['grund'] ?? '', 1000, 'Änderungsgrund');
                $entfallen = !empty($b['entfallen']);
                $eintrag = ['datum' => qs_heute(), 'was' => '', 'grund' => $grund, 'von' => (string)$me['name']];
                if ($alt === null) {
                    $pos = 0; foreach ($doc['liste'] as $x) if ($x['kapitel'] === $felder['kapitel']) $pos = max($pos, (int)($x['pos'] ?? 0));
                    $a = ['id' => qs_id('h')] + $felder + ['pos' => $pos + 1, 'entfallen' => null, 'aenderungen' => [array_merge($eintrag, ['was' => $aend !== '' ? $aend : 'Neu angelegt'])], 'quelle' => 'hand'];
                    $was = 'angelegt';
                } else {
                    $a = $alt;
                    $geaendert = false;
                    foreach (QS_ABSCHNITT_INHALT as $f) if (($alt[$f] ?? null) !== $felder[$f]) $geaendert = true;
                    $warEntfallen = !empty($alt['entfallen']);
                    if (!$geaendert && $warEntfallen === $entfallen) return [$alt, ''];
                    if ($aend === '' || $grund === '') throw new InvalidArgumentException('Bitte die Änderung und den Änderungsgrund in Stichworten angeben.');
                    $a = $felder + $a;
                    if ($warEntfallen !== $entfallen) $a['entfallen'] = $entfallen ? qs_wer($me) : null;
                    $a['aenderungen'] = array_values(array_merge(is_array($alt['aenderungen'] ?? null) ? $alt['aenderungen'] : [], [array_merge($eintrag, ['was' => $aend])]));
                    if (count($a['aenderungen']) > QS_MAX_AENDERUNGEN) $a['aenderungen'] = array_slice($a['aenderungen'], -QS_MAX_AENDERUNGEN);
                    if ($alt['kapitel'] !== $a['kapitel']) { $pos = 0; foreach ($doc['liste'] as $x) if ($x['kapitel'] === $a['kapitel']) $pos = max($pos, (int)($x['pos'] ?? 0)); $a['pos'] = $pos + 1; }
                    $was = $warEntfallen !== $entfallen ? ($entfallen ? 'als entfallen markiert' : 'wieder aufgenommen') : 'geändert';
                }
                $a['rev'] = (int)($a['rev'] ?? 0) + 1;
                $a['geaendert'] = qs_wer($me);
                if ($i === null) $doc['liste'][] = $a; else $doc['liste'][$i] = $a;
                qs_schreiben('qs-handbuch', $doc);
                return [$a, $was];
            });
            if ($was !== '') audit('qs', 'QM-System: Handbuch ' . $a['kapitel'] . ' ' . $a['nr'] . ' „' . $a['titel'] . '“ ' . $was);
            respond(['ok' => true, 'abschnitt' => $a, 'unveraendert' => $was === '']);
        }

        /* Prüfung des Prüfplans anlegen oder ändern (Intervall, erste Fälligkeit, Sollwert, Maßnahme, aktiv) */
        case 'qs_pruefung_save': {
            $me = require_perm('qs.freigeben', true);
            $b = body();
            $p = with_lock('qs-dokumente', function () use ($b, $me) {
                $stamm = qs_stamm(); $doc = qs_doc('qs-pruefplan');
                $id = (string)($b['id'] ?? ''); $alt = null; $i = null;
                if ($id !== '') { $i = qs_index($doc, $id, 'Prüfung'); $alt = $doc['liste'][$i]; qs_rev_pruefen($b, $alt, 'Die Prüfung'); }
                elseif (count($doc['liste']) >= QS_MAX_PRUEFUNGEN) fail('Zu viele Prüfungen.', 422);
                $felder = qs_pruefung_felder($b, $stamm, qs_mitarbeiter());
                if ($alt === null) { $p = ['id' => qs_id('p')] + $felder + ['erstellt' => qs_wer($me), 'quelle' => 'hand', 'verlauf' => []]; qs_verlauf($p, $me, 'angelegt'); }
                else {
                    $p = $felder + $alt;
                    $teile = [];
                    $namen = ['kapitel' => 'Kapitel', 'titel' => 'Bezeichnung', 'beschreibung' => 'Durchführung', 'intervall' => 'Intervall', 'start' => 'ab wann', 'sollwert' => 'Sollwert',
                              'massnahme' => 'Maßnahme', 'womit' => 'Wo? Womit?', 'zustaendig' => 'Zuständig', 'vertreter' => 'Vertreter', 'ausfuehrende' => 'Durchführung durch', 'aktiv' => 'aktiv'];
                    foreach ($felder as $f => $w) if (($alt[$f] ?? null) !== $w) $teile[] = $namen[$f] ?? $f;
                    if (!$teile) return $alt;
                    qs_verlauf($p, $me, 'geändert: ' . implode(', ', $teile));
                }
                $p['rev'] = (int)($p['rev'] ?? 0) + 1;
                $p['geaendert'] = qs_wer($me);
                if ($i === null) $doc['liste'][] = $p; else $doc['liste'][$i] = $p;
                qs_schreiben('qs-pruefplan', $doc);
                return $p;
            });
            audit('qs', 'QM-System: Prüfung „' . $p['titel'] . '“ gespeichert' . (empty($p['aktiv']) ? ' (inaktiv)' : ''));
            $eigene = qs_nachweise_nach_pruefung(qs_doc('qs-nachweise')['liste'])[$p['id']] ?? [];
            respond(['ok' => true, 'pruefung' => $p + ['faellig' => qs_faelligkeit($p, $eigene, qs_heute())]]);
        }

        /* Nachweis einer Prüfung erfassen; bei einer Abweichung auf Wunsch gleich eine Maßnahme anlegen */
        case 'qs_nachweis_save': {
            $me = require_perm('qs.nachweis', true);
            $b = body();
            [$n, $m, $p] = with_lock('qs-dokumente', function () use ($b, $me) {
                $heute = qs_heute(); $plan = qs_doc('qs-pruefplan')['liste'];
                $p = qs_pruefung_finden($plan, $b['pruefung'] ?? '');
                if (!may($me, 'qs.bearbeiten') && !qs_pruefung_meine($p, qs_stamm(), (string)$me['id']))
                    fail('Diese Prüfung ist Ihnen nicht zugewiesen. Nachweise für andere Prüfungen erfasst, wer „QM-System bearbeiten“ hat.', 403);
                $row = qs_nachweis_felder($b, $p, $heute);
                $doc = qs_doc('qs-nachweise');
                if (count($doc['liste']) >= QS_MAX_NACHWEISE) fail('Zu viele Nachweise.', 422);
                if ($row['durch'] === '') $row['durch'] = (string)$me['name'];
                $n = ['id' => qs_id('n')] + $row + ['massnahme' => '', 'erfasst' => qs_wer($me), 'storno' => null];
                $m = null;
                if ($row['ergebnis'] === 'abweichung' && is_array($b['massnahme'] ?? null)) {
                    if (!may($me, 'qs.bearbeiten')) fail('Eine Maßnahme legt an, wer „QM-System bearbeiten“ hat – die Abweichung ist im Nachweis festgehalten.', 403);
                    $md = qs_doc('qs-massnahmen');
                    if (count($md['liste']) >= QS_MAX_MASSNAHMEN) fail('Zu viele Maßnahmen.', 422);
                    $mb = $b['massnahme'];
                    $felder = qs_massnahme_felder(['quelle' => 'pruefung', 'bezug' => 'Prüfung „' . $p['titel'] . '“ am ' . qs_de($row['datum']), 'kapitel' => $p['kapitel'],
                                                   'feststellung' => $row['bemerkung'], 'korrektur' => $mb['korrektur'] ?? '', 'massnahme' => $mb['massnahme'] ?? '',
                                                   'zustaendig' => $mb['zustaendig'] ?? ($p['zustaendig'] ?? ''), 'frist' => $mb['frist'] ?? '', 'status' => 'offen'], qs_stamm());
                    $m = ['id' => qs_id('m'), 'nr' => qs_massnahme_nr($md['liste'], substr($heute, 0, 4))] + $felder
                         + ['wirksamkeit' => null, 'pruefung' => $p['id'], 'nachweisId' => $n['id'], 'rev' => 1, 'erfasst' => qs_wer($me), 'geaendert' => qs_wer($me), 'quelle' => 'hand', 'verlauf' => []];
                    qs_verlauf($m, $me, 'aus dem Nachweis angelegt');
                    $n['massnahme'] = $m['id'];
                    $md['liste'][] = $m;
                    qs_schreiben('qs-massnahmen', $md);
                }
                $doc['liste'][] = $n;
                qs_schreiben('qs-nachweise', $doc);
                return [$n, $m, $p];
            });
            audit('qs', 'QM-System: Nachweis „' . $p['titel'] . '“ vom ' . qs_de($n['datum']) . ' erfasst (' . QS_ERGEBNIS[$n['ergebnis']] . ')' . ($m ? ', Maßnahme ' . $m['nr'] . ' angelegt' : ''));
            $eigene = qs_nachweise_nach_pruefung(qs_doc('qs-nachweise')['liste'])[$p['id']] ?? [];
            respond(['ok' => true, 'nachweis' => $n, 'massnahme' => $m ? qs_massnahme_aus($m, qs_heute()) : null, 'pruefung' => $p + ['faellig' => qs_faelligkeit($p, $eigene, qs_heute())]]);
        }

        /* Nachweis stornieren (bleibt sichtbar, zählt nicht mehr für die Fälligkeit) */
        case 'qs_nachweis_storno': {
            $me = require_perm('qs.nachweis', true);
            $b = body();
            $grund = qs_text($b['grund'] ?? '', 300, 'Grund');
            if ($grund === '') fail('Bitte einen Grund für das Stornieren angeben.', 422);
            $n = with_lock('qs-dokumente', function () use ($b, $me, $grund) {
                $doc = qs_doc('qs-nachweise');
                $i = qs_index($doc, $b['id'] ?? '', 'Nachweis');
                if (!empty($doc['liste'][$i]['storno'])) fail('Dieser Nachweis ist schon storniert.', 409);
                if (!may($me, 'qs.bearbeiten') && (string)($doc['liste'][$i]['erfasst']['vonId'] ?? '') !== (string)$me['id'])
                    fail('Stornieren dürfen Sie nur eigene Nachweise.', 403);
                $doc['liste'][$i]['storno'] = qs_wer($me) + ['grund' => $grund];
                qs_schreiben('qs-nachweise', $doc);
                return $doc['liste'][$i];
            });
            audit('qs', 'QM-System: Nachweis vom ' . qs_de($n['datum']) . ' storniert');
            respond(['ok' => true, 'nachweis' => $n]);
        }

        /* Maßnahme erfassen (ohne id) oder ändern (id + rev). „Wirksam“ (Wirksamkeitsprüfung mit Notiz), „verworfen“ und
           jede Änderung einer abgeschlossenen Maßnahme nur mit „qs.freigeben“. */
        case 'qs_massnahme_save': {
            $me = require_perm('qs.bearbeiten', true);
            $b = body();
            $m = with_lock('qs-dokumente', function () use ($b, $me) {
                $stamm = qs_stamm(); $doc = qs_doc('qs-massnahmen');
                $id = (string)($b['id'] ?? ''); $alt = null; $i = null;
                if ($id !== '') { $i = qs_index($doc, $id, 'Maßnahme'); $alt = $doc['liste'][$i]; qs_rev_pruefen($b, $alt, 'Die Maßnahme'); }
                elseif (count($doc['liste']) >= QS_MAX_MASSNAHMEN) fail('Zu viele Maßnahmen.', 422);
                $felder = qs_massnahme_felder($b, $stamm);
                $altStatus = $alt['status'] ?? null;
                $darf = may($me, 'qs.freigeben');
                if (!$darf && (in_array($felder['status'], QS_MASSN_ABGESCHLOSSEN, true) || in_array((string)$altStatus, QS_MASSN_ABGESCHLOSSEN, true)) && $felder['status'] !== $altStatus)
                    fail('Als wirksam abschließen, verwerfen oder wieder öffnen darf nur, wer prüfen und freigeben darf.', 403);
                if (!$darf && in_array((string)$altStatus, QS_MASSN_ABGESCHLOSSEN, true)) fail('Abgeschlossene Maßnahmen ändert nur, wer prüfen und freigeben darf.', 403);
                $notiz = qs_text($b['wirksamkeitNotiz'] ?? '', 2000, 'Wirksamkeit');
                if ($felder['status'] === 'wirksam' && $altStatus !== 'wirksam' && $notiz === '') throw new InvalidArgumentException('Bitte festhalten, wie die Wirksamkeit geprüft wurde.');
                if ($felder['status'] === 'verworfen' && $altStatus !== 'verworfen' && $notiz === '') throw new InvalidArgumentException('Bitte den Grund für das Verwerfen angeben.');
                if ($alt === null) {
                    $m = ['id' => qs_id('m'), 'nr' => qs_massnahme_nr($doc['liste'], substr(qs_heute(), 0, 4))] + $felder
                         + ['wirksamkeit' => null, 'pruefung' => '', 'nachweisId' => '', 'erfasst' => qs_wer($me), 'quelle' => 'hand', 'verlauf' => []];
                    qs_verlauf($m, $me, 'erfasst (' . QS_MASSN_STATUS[$m['status']] . ')');
                } else {
                    $m = $felder + $alt;
                    if ($altStatus !== $m['status']) qs_verlauf($m, $me, 'Status: ' . (QS_MASSN_STATUS[$altStatus] ?? '') . ' → ' . QS_MASSN_STATUS[$m['status']]);
                    else { $gleich = true; foreach ($felder as $f => $w) if (($alt[$f] ?? null) !== $w) $gleich = false; if ($gleich) return $alt; qs_verlauf($m, $me, 'geändert'); }
                }
                if ($m['status'] === 'wirksam' && $altStatus !== 'wirksam') $m['wirksamkeit'] = qs_wer($me) + ['notiz' => $notiz];
                elseif (!in_array($m['status'], QS_MASSN_ABGESCHLOSSEN, true)) $m['wirksamkeit'] = null;
                if ($m['status'] === 'verworfen' && $altStatus !== 'verworfen') qs_verlauf($m, $me, 'Grund: ' . $notiz);
                $m['rev'] = (int)($m['rev'] ?? 0) + 1;
                $m['geaendert'] = qs_wer($me);
                if ($i === null) $doc['liste'][] = $m; else $doc['liste'][$i] = $m;
                qs_schreiben('qs-massnahmen', $doc);
                return $m;
            });
            audit('qs', 'QM-System: Maßnahme ' . $m['nr'] . ' gespeichert (' . QS_MASSN_STATUS[$m['status']] . ')');
            respond(['ok' => true, 'massnahme' => qs_massnahme_aus($m, qs_heute())]);
        }

        /* Kapitel und Personen (Kürzel) – verwendete Kapitel nur deaktivieren, nicht entfernen */
        case 'qs_stamm_save': {
            $me = require_perm('qs.verwalten', true);
            $b = body();
            $stamm = with_lock('qs-dokumente', function () use ($b) {
                $stamm = qs_stamm();
                if (array_key_exists('rev', $b) && (int)$b['rev'] !== $stamm['rev']) fail('Kapitel und Personen wurden inzwischen geändert. Bitte neu laden.', 409);
                if (array_key_exists('kapitel', $b)) $stamm['kapitel'] = qs_kapitel_liste_pruefen($b['kapitel'], $stamm['kapitel'], qs_kapitel_benutzt());
                if (array_key_exists('personen', $b)) $stamm['personen'] = qs_personen_pruefen($b['personen'], $stamm['personen'], qs_mitarbeiter());
                if (array_key_exists('einstellungen', $b)) $stamm['einstellungen'] = qs_einstellungen_pruefen($b['einstellungen'], $stamm['einstellungen']);
                qs_schreiben('qs-stamm', $stamm);
                return qs_stamm();
            });
            audit('qs', 'QM-System: Kapitel und Personen gespeichert (' . count($stamm['kapitel']) . ' Kapitel, ' . count($stamm['personen']) . ' Personen)');
            respond(['ok' => true, 'rev' => $stamm['rev'], 'kapitel' => $stamm['kapitel'], 'personen' => $stamm['personen'], 'einstellungen' => $stamm['einstellungen']]);
        }

        /* Datenpaket prüfen (vorschau) und übernehmen – nur in ein leeres Modul oder mit „ersetzen“ */
        case 'qs_import': {
            $me = require_perm('qs.verwalten', true);
            $b = body();
            $erg = qs_paket_pruefen($b['paket'] ?? null, $me);
            $leer = qs_leer();
            $dateien = qs_dateien_zahl(qs_doc('qs-dokumente')['liste']);
            if (!empty($b['vorschau'])) respond(['ok' => true, 'zahlen' => $erg['zahlen'], 'fehler' => $erg['fehler'], 'leer' => $leer, 'dateien' => $dateien]);
            if ($erg['fehler']) respond(['ok' => false, 'error' => 'Das Datenpaket enthält Fehler – nichts übernommen.', 'fehler' => $erg['fehler']], 422);
            with_lock('qs-dokumente', function () use ($erg, $b) {
                if (!qs_leer() && empty($b['ersetzen'])) fail('Im QM-System sind schon Daten. Zum Ersetzen „Vorhandene Daten ersetzen“ wählen.', 409);
                if ($n = qs_dateien_zahl(qs_doc('qs-dokumente')['liste'])) fail("In der Dokumentenablage liegen schon $n Dateien – ein Datenpaket kann die Dokumente dann nicht mehr ersetzen (die Dateien gingen verloren).", 409);
                $alt = qs_stamm();
                $stamm = $erg['stamm']; $stamm['rev'] = $alt['rev']; $stamm['einstellungen'] = $alt['einstellungen'];
                qs_schreiben('qs-stamm', $stamm);
                foreach (['dokumente', 'handbuch', 'pruefplan', 'massnahmen'] as $k) qs_schreiben('qs-' . $k, ['rev' => qs_doc('qs-' . $k)['rev'], 'liste' => $erg['docs'][$k]]);
                qs_schreiben('qs-nachweise', ['rev' => qs_doc('qs-nachweise')['rev'], 'liste' => []]);
            });
            $z = $erg['zahlen'];
            audit('qs', 'QM-System: Datenpaket übernommen' . ($leer ? '' : ' (vorhandene Daten ersetzt)') . ' – ' . $z['kapitel'] . ' Kapitel, ' . $z['dokumente'] . ' Dokumente mit '
                . $z['versionen'] . ' Versionen, ' . $z['handbuch'] . ' Handbuch-Abschnitte, ' . $z['pruefungen'] . ' Prüfungen, ' . $z['massnahmen'] . ' Maßnahmen');
            respond(['ok' => true, 'zahlen' => $z]);
        }
}
