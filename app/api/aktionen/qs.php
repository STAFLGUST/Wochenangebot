<?php
declare(strict_types=1);
/* Aktionen: QM-System (Oberfläche qs.intern, Daten und Regeln in app/api/module/qs/qs.php)
   Rechte (GR-103): qs.sehen – Übersicht, Dokumente mit Versionen, Handbuch, Prüfplan mit Nachweisen, Maßnahmen, CSV,
                              Audit-Bericht (Ansicht und Excel);
                    qs.nachweis – Kontrollen durchführen: Nachweise für die eigenen (zugewiesenen) Prüfungen erfassen,
                                  eigene Nachweise stornieren;
                    qs.bearbeiten – Dokumente anlegen, Entwürfe schreiben, zur Prüfung geben, verwerfen; Nachweise aller
                                    Prüfungen erfassen und stornieren; Maßnahmen erfassen und bis „umgesetzt“ führen;
                    qs.freigeben – Entwürfe prüfen (nie eigene: 4-Augen-Prinzip, auch für Administratoren), freigeben,
                                   zurückgeben, Dokumente einziehen und „ohne Änderung überprüft“ vermerken; Handbuch und
                                   Prüfplan ändern (auch Zuweisung an Mitarbeiter); Maßnahmen als wirksam abschließen,
                                   verwerfen oder wieder öffnen;
                    qs.verwalten – Kapitel, Personen (Kürzel, Verknüpfung mit Mitarbeitern) und Einstellungen pflegen,
                                   Datenpaket übernehmen (enthält es Dokumentenversionen, zusätzlich qs.freigeben – es macht
                                   gelenkte Dokumente gültig).
                    qs.verfahren_sehen / _bearbeiten / _freigeben – Verfahrensdokumentation nach GoBD (eigene, sensible
                                   Rechte): ansehen und exportieren / Abschnitte und IT-Systeme pflegen / Fassung freigeben,
                                   „ohne Änderung überprüft“ vermerken.
   Dokumentenablage, Eingang und Ordner-Import: Regeln und Rechte je Stelle in module/qs/ablage.php, beschrieben in
   docs/entwickler/05-daten.md („QM-System: Dokumentenablage“).
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
switch ($action) {
        /* Start: Stammdaten, Dokumente, Handbuch, Prüfplan mit Fälligkeiten, neueste Nachweise, Maßnahmen, eigene Rechte */
        case 'qs_start': {
            $me = require_perm('qs.sehen');
            header('Cache-Control: no-store');
            $heute = qs_heute();
            $stamm = qs_stamm();
            ['dokumente' => $dokumente, 'handbuch' => $handbuch, 'pruefplan' => $plan, 'nachweise' => $nachweise, 'massnahmen' => $massnahmen]
                = qs_sichtbar($me, 'dokumente', 'handbuch', 'pruefplan', 'nachweise', 'massnahmen');
            qs_abschnitte_sortieren($handbuch);
            usort($nachweise, function ($a, $b) { return [$b['datum'], $b['erfasst']['t'] ?? ''] <=> [$a['datum'], $a['erfasst']['t'] ?? '']; });
            $monate = (int)$stamm['einstellungen']['ueberpruefungMonate'];
            respond(['ok' => true, 'heute' => $heute, 'ich' => ['id' => (string)$me['id'], 'name' => (string)$me['name'], 'kuerzel' => qs_kuerzel_von($stamm, (string)$me['id'])],
                     'rechte' => ['nachweis' => may($me, 'qs.nachweis'), 'bearbeiten' => may($me, 'qs.bearbeiten'), 'freigeben' => may($me, 'qs.freigeben'), 'verwalten' => may($me, 'qs.verwalten'),
                                  'verfahren' => may($me, 'qs.verfahren_sehen')],
                     'arten' => QS_ARTEN, 'gelenkt' => QS_GELENKT, 'verStatus' => QS_VER_STATUS, 'intervalle' => QS_INTERVALLE, 'ergebnisse' => QS_ERGEBNIS,
                     'quellen' => QS_QUELLEN, 'bewertungen' => QS_BEWERTUNG, 'massnStatus' => QS_MASSN_STATUS,
                     'kapitel' => $stamm['kapitel'], 'personen' => $stamm['personen'], 'einstellungen' => $stamm['einstellungen'], 'mitarbeiter' => qs_mitarbeiter(),
                     'dokumente' => array_map(function ($d) use ($monate, $heute) { return qs_dok_aus($d, $monate, $heute); }, $dokumente),
                     'ablageZahlen' => qs_ablage_uebersicht($dokumente), 'eingangZahl' => may($me, 'qs.bearbeiten') ? qs_ablage_belegt(null, qs_ablage_zahlen()) : 0,
                     'handbuch' => $handbuch,
                     'pruefungen' => qs_pruefungen_aus($plan, $nachweise, $heute),
                     'nachweise' => array_slice($nachweise, 0, QS_START_NACHWEISE), 'nachweiseGesamt' => count($nachweise),
                     'massnahmen' => array_map(function ($m) use ($heute) { return qs_massnahme_aus($m, $heute); }, $massnahmen),
                     'leer' => qs_leer(), 'ablage' => qs_ablage_einstellungen()]);
        }

        /* Dokumentenliste, Prüfplan oder Maßnahmen als CSV (Excel), im Protokoll vermerkt */
        case 'qs_export': {
            $me = require_perm('qs.sehen', true);
            $b = body();
            $liste = qs_wahl($b['liste'] ?? 'dokumente', ['dokumente', 'pruefplan', 'massnahmen'], 'Liste');
            $heute = qs_heute();
            if ($liste === 'dokumente') { $daten = qs_sichtbar($me, 'dokumente')['dokumente']; $csv = qs_csv_dokumente($daten, qs_stamm(), $heute); $name = 'QM-Dokumentenliste'; }
            elseif ($liste === 'pruefplan') {
                $l = qs_sichtbar($me, 'pruefplan', 'nachweise');
                $daten = qs_pruefungen_aus($l['pruefplan'], $l['nachweise'], $heute);
                $namen = []; foreach (qs_mitarbeiter() as $m) $namen[$m['id']] = $m['name'];
                $csv = qs_csv_pruefplan($daten, $namen); $name = 'QM-Pruefplan';
            }
            else { $daten = qs_sichtbar($me, 'massnahmen')['massnahmen']; $csv = qs_csv_massnahmen($daten); $name = 'QM-Massnahmen'; }
            audit('qs', 'QM-System: ' . ['dokumente' => 'Dokumentenliste', 'pruefplan' => 'Prüfplan', 'massnahmen' => 'Maßnahmen'][$liste] . ' als CSV heruntergeladen (' . count($daten) . ' Einträge)');
            header('Content-Type: text/csv; charset=utf-8');
            header('Content-Disposition: attachment; filename="' . $name . '_' . $heute . '.csv"');
            header('Cache-Control: private, no-store');
            header('X-Content-Type-Options: nosniff');
            echo $csv;
            exit;
        }

        /* Dokument anlegen (ohne id; gelenkte Arten bekommen gleich einen Entwurf) oder Angaben ändern (id + rev);
           Einziehen und wieder gültig machen nur mit „qs.freigeben“ (offene Entwürfe werden dabei verworfen).
           Nummernstruktur „<Kapitel>-<Art><Nr.>“ für A, F, L, E (leer = nächste freie). vorlage = Kennung einer Vorlage (Art V):
           ihre Word-/Excel-Dateien werden mit Nr., Titel usw. ausgefüllt und liegen im ersten Entwurf (module/qs/vorlagen.php). */
        case 'qs_dokument_save': {
            $me = require_perm('qs.bearbeiten', true);
            $b = body();
            $vorlage = is_string($b['vorlage'] ?? null) ? $b['vorlage'] : '';
            if ($vorlage !== '') require_once __DIR__ . '/../module/qs/vorlagen.php';
            $erzeugt = []; $fertig = false;
            if ($vorlage !== '') qs_erzeugte_aufraeumen($erzeugt, $fertig);
            [$d, $was] = with_lock('qs-dokumente', function () use ($b, $me, $vorlage, &$erzeugt) {
                $stamm = qs_stamm(); $doc = qs_doc('qs-dokumente');
                $id = (string)($b['id'] ?? ''); $alt = null; $i = null;
                if ($id !== '') { $i = qs_dokument_index($doc, $id); $alt = $doc['liste'][$i]; qs_rev_pruefen($b, $alt, 'Das Dokument'); }
                elseif (count($doc['liste']) >= QS_MAX_DOKUMENTE) fail('Zu viele Dokumente.', 422);
                if ($vorlage !== '' && $alt !== null) throw new InvalidArgumentException('Eine Vorlage gilt nur beim Anlegen.');
                $d = qs_dokument_pruefen($b, $alt, $stamm, $doc['liste'], true);
                $was = 'gespeichert';
                if ($alt === null) {
                    $d = ['id' => qs_id('d')] + $d + ['erstellt' => qs_wer($me), 'quelle' => 'hand', 'verlauf' => []];
                    qs_verlauf($d, $me, 'angelegt');
                    if (in_array($d['art'], QS_GELENKT, true)) $d['versionen'][] = qs_entwurf($me, qs_text($b['aenderungen'] ?? '', 2000, 'Änderungen') ?: 'Neu angelegt', qs_text($b['grund'] ?? '', 1000, 'Änderungsgrund'));
                    if ($vorlage !== '') {
                        if (!in_array($d['art'], QS_NR_STRUKTUR, true)) throw new InvalidArgumentException('Aus einer Vorlage entstehen Arbeitsanweisungen, Formblätter, Listen und Excel-Dokumente.');
                        $vi = null;
                        foreach ($doc['liste'] as $k => $x) if (($x['id'] ?? '') === $vorlage) $vi = $k;
                        if ($vi === null) throw new InvalidArgumentException('Die Vorlage gibt es nicht (mehr).');
                        $vd = $doc['liste'][$vi];
                        $d['versionen'][0]['dateien'] = qs_vorlage_anwenden($vd, $d, $stamm, $me, $erzeugt);
                        qs_verlauf($d['versionen'][0], $me, 'aus Vorlage „' . $vd['nr'] . '“ erzeugt');
                        qs_verlauf($d, $me, 'aus Vorlage „' . $vd['nr'] . '“ erzeugt');
                    }
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
            $fertig = true;
            audit('qs', 'QM-System: Dokument ' . qs_protokoll_name($d, qs_dok_name($d)) . ' ' . $was . ($erzeugt ? ' (aus Vorlage)' : ''));
            respond(['ok' => true, 'dokument' => qs_dok_antwort($d)]);
        }

        /* Entwurf einer neuen Version anlegen oder ändern (Änderungen und Änderungsgrund, Handbuch 2.0.11);
           dateien=true beim Beginn einer Überarbeitung: Dateien der gültigen Version (Rohfassung mit Platzhaltern) als Kopie übernehmen */
        case 'qs_version_save': {
            $me = require_perm('qs.bearbeiten', true);
            $b = body();
            $uebernehmen = !empty($b['dateien']);
            if ($uebernehmen) require_once __DIR__ . '/../module/qs/vorlagen.php';
            $erzeugt = []; $fertig = false;
            if ($uebernehmen) qs_erzeugte_aufraeumen($erzeugt, $fertig);
            $d = with_lock('qs-dokumente', function () use ($b, $me, $uebernehmen, &$erzeugt) {
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
                    $neu = qs_entwurf($me, $aend, $grund);
                    require_once __DIR__ . '/../module/qs/organigramm.php'; qs_organigramm_uebernehmen($gueltig === null ? null : $d['versionen'][$gueltig], $neu);
                    if ($uebernehmen && $gueltig !== null && ($f = qs_dateien_uebernehmen($d['versionen'][$gueltig], $me, $erzeugt))) {
                        $neu['dateien'] = $f;
                        qs_verlauf($neu, $me, 'Dateien aus Version ' . ($d['versionen'][$gueltig]['nr'] ?? '?') . ' übernommen (' . count($f) . ')');
                    }
                    $d['versionen'][] = $neu;
                    qs_verlauf($d, $me, 'Überarbeitung begonnen');
                }
                return qs_dok_ablegen($doc, $i, $d, $me);
            });
            $fertig = true;
            audit('qs', 'QM-System: Entwurf für ' . qs_protokoll_name($d, qs_dok_name($d)) . ' gespeichert');
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
            $erzeugt = []; $fertig = false;
            if (in_array($schritt, ['freigeben', 'pruefen_freigeben'], true)) { require_once __DIR__ . '/../module/qs/vorlagen.php'; qs_erzeugte_aufraeumen($erzeugt, $fertig); }
            [$d, $text] = with_lock('qs-dokumente', function () use ($b, $me, $schritt, &$erzeugt) {
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
                    qs_lenkung_eintragen($d, $v, qs_stamm(), $me, $erzeugt);   // Version, Datum, Kürzel in Word-/Excel-Dateien
                    qs_verlauf($v, $me, "freigegeben als Version $nr");
                    qs_verlauf($d, $me, "Version $nr freigegeben");
                    $text = "Version $nr freigegeben";
                }
                require_once __DIR__ . '/../module/qs/organigramm.php'; qs_organigramm_schritt($d, $v, $me, $erzeugt);   // Namen ab dem Einreichen, PDF-Fassung bei der Freigabe
                $d['versionen'][$o] = $v;
                return [qs_dok_ablegen($doc, $i, $d, $me), $text];
            });
            $fertig = true;
            audit('qs', 'QM-System: ' . qs_protokoll_name($d, qs_dok_name($d)) . ' – ' . $text);
            respond(['ok' => true, 'dokument' => qs_dok_antwort($d)]);
        }

        /* Datei ablegen – in Teilen (lib/dateiablage.php): dokument (Kennung oder „eingang“), version ('' bei Ordnern, externen
           Dokumenten und im Eingang), pfad (Unterordner), name, groesse, sha256, upload ('' beim ersten Teil), teil, daten (Base64).
           Regeln je Stelle: qs_ablage_regel(). sammeln=true (Ordner-Import): nur herkunft (Ordnerpfad wie gewählt) – der fertige Upload
           bleibt liegen, das Ziel berechnet qs_import_eintragen. Antwort: fertig=false mit upload, bis der letzte Teil da ist. */
        case 'qs_datei_hochladen': {
            $me = require_perm('qs.bearbeiten', true);
            require_once __DIR__ . '/../lib/dateiablage.php';
            require_once __DIR__ . '/../module/qs/vorlagen.php';
            $b = body();
            $dok = is_string($b['dokument'] ?? null) ? $b['dokument'] : ''; $ver = is_string($b['version'] ?? null) ? $b['version'] : '';
            $sammeln = !empty($b['sammeln']);
            if ($sammeln) { qs_import_teile($b['herkunft'] ?? null); $ziel = ['sammeln' => true, 'herkunft' => $b['herkunft']]; }
            else $ziel = ['dokument' => $dok, 'version' => $ver, 'pfad' => qs_pfad($b['pfad'] ?? '')];
            if (($b['upload'] ?? '') === '' && !$sammeln) {
                $doc = qs_doc('qs-dokumente'); $d = $dok === QS_EINGANG ? null : $doc['liste'][qs_dokument_index($doc, $dok)];
                qs_ablage_stelle($d, $ver, $me, 'hochladen', qs_ablage_belegt($d, qs_ablage_zahlen()));
            }
            $r = ablage_teil('qs', (string)$me['id'], $ziel, $b, !$sammeln);
            if (!$r['fertig']) respond(['ok' => true, 'fertig' => false, 'upload' => $r['upload'], 'empfangen' => $r['empfangen']]);
            if ($sammeln) respond(['ok' => true, 'fertig' => true, 'upload' => $r['upload']]);
            $datei = $r['datei'];
            $abgelegt = [(string)$datei['id']]; $erzeugt = []; $gespeichert = [];
            qs_ablage_aufraeumen($abgelegt, $erzeugt, $gespeichert);   // scheitert das Eintragen, bleibt keine verwaiste Datei zurück
            $platzhalter = $ver !== '' ? qs_platzhalter_vorab($datei) : null;
            [$aus, $liste] = with_lock('qs-dokumente', function () use ($datei, $dok, $ver, $ziel, $platzhalter, $me, &$erzeugt) {
                return qs_ablage_eintragen([['datei' => $datei, 'ziel' => $dok, 'version' => $ver, 'pfad' => $ziel['pfad'], 'platzhalter' => $platzhalter]], $me, 'abgelegt', $erzeugt);
            });
            if ($aus[0]['status'] === 'fehler') fail($aus[0]['grund'], $aus[0]['code']);
            $gespeichert = array_flip(array_merge($abgelegt, $erzeugt));
            $d = null; foreach ($liste as $x) if ((string)$x['id'] === $dok) $d = $x;
            audit('qs', 'QM-System: Datei für ' . ($d ? qs_protokoll_name($d, qs_dok_name($d)) : 'den Eingang') . ' abgelegt (' . round($datei['groesse'] / 1024) . ' KB)');
            respond(['ok' => true, 'fertig' => true, 'datei' => $aus[0]['datei']] + ($d ? ['dokument' => qs_dok_antwort($d)] : []));
        }

        /* Eingang (GET, nur mit qs.bearbeiten – dort liegen unsortierte, womöglich personenbezogene Unterlagen): Dateien ohne Ziel,
           erst beim Öffnen geladen (qs_start nennt nur die Zahl), und die Ziele, denen der Nutzer zuordnen darf */
        case 'qs_eingang': {
            $me = require_perm('qs.bearbeiten');
            header('Cache-Control: no-store');
            respond(['ok' => true, 'dateien' => qs_eingang_dateien(), 'ziele' => qs_eingang_ziele(qs_doc('qs-dokumente')['liste'], $me)]);
        }

        /* Dateien aus dem Eingang zuordnen (dateien = Kennungen) – einem Ordner oder externen Dokument (version '') oder dem Entwurf
           eines gelenkten Dokuments; Regeln in qs_eingang_zuordnen(). Alles oder nichts, die Datei behält Kennung und pfad. */
        case 'qs_datei_zuordnen': {
            $me = require_perm('qs.bearbeiten', true);
            require_once __DIR__ . '/../lib/dateiablage.php';
            require_once __DIR__ . '/../module/qs/vorlagen.php';
            $b = body();
            $ids = qs_ablage_auswahl($b['dateien'] ?? null);
            $dok = is_string($b['dokument'] ?? null) ? $b['dokument'] : ''; $ver = is_string($b['version'] ?? null) ? $b['version'] : '';
            $doc = qs_doc('qs-dokumente'); $d = $doc['liste'][qs_dokument_index($doc, $dok)];
            qs_ablage_stelle($d, $ver, $me, 'zuordnen', qs_ablage_belegt($d, qs_ablage_zahlen()), count($ids));   // Grenzen vor dem Lesen der Dateien
            $platzhalter = $ver !== '' ? qs_eingang_platzhalter($ids) : [];   // Word/Excel in einen Entwurf: vor der Sperre
            $erzeugt = [];
            [$d, $rest] = with_lock('qs-dokumente', function () use ($ids, $dok, $ver, $me, $platzhalter, &$erzeugt) { return qs_eingang_zuordnen($ids, $dok, $ver, $me, $platzhalter, $erzeugt); });
            audit('qs', 'QM-System: ' . qs_dateien_text(count($ids)) . ' aus dem Eingang ' . qs_protokoll_name($d, qs_dok_name($d)) . ' zugeordnet');
            respond(['ok' => true, 'dokument' => qs_dok_antwort($d), 'eingangZahl' => $rest]);
        }

        /* Dateien im Eingang endgültig löschen (dateien = Kennungen): Eintrag und Datei verschwinden, die Prüfsumme bleibt gemerkt.
           Alles oder nichts; die Dateien selbst erst nach dem Speichern (im Fehlerfall bleiben sie). */
        case 'qs_eingang_loeschen': {
            require_perm('qs.bearbeiten', true);
            require_once __DIR__ . '/../lib/dateiablage.php';
            $ids = qs_ablage_auswahl(body()['dateien'] ?? null);
            [$weg, $rest] = with_lock('qs-dokumente', function () use ($ids) { return qs_eingang_loeschen($ids); });
            foreach ($weg as $id) ablage_entfernen('qs', $id);
            audit('qs', 'QM-System: ' . qs_dateien_text(count($ids)) . ' im Eingang gelöscht');
            respond(['ok' => true, 'eingangZahl' => $rest]);
        }

        /* Datei entfernen: im Entwurf (qs.bearbeiten) endgültig gelöscht; an Ordnern/externen Dokumenten (qs.bearbeiten) und an
           freigegebenen Versionen (qs.freigeben) nur als „entfernt“ vermerkt (mit Grund), die Datei bleibt in der Ablage */
        case 'qs_datei_entfernen': {
            $me = require_perm('qs.bearbeiten', true);
            require_once __DIR__ . '/../lib/dateiablage.php';
            $b = body();
            [$d, $name, $loeschen, $frei] = with_lock('qs-dokumente', function () use ($b, $me) {
                $doc = qs_doc('qs-dokumente');
                $id = is_string($b['datei'] ?? null) ? $b['datei'] : '';
                $ort = qs_datei_suchen($doc['liste'], $id);
                if ($ort === null) fail('Datei nicht gefunden.', 404);
                [$f, $i, $vi, $k] = $ort;
                if ($i === null) return qs_archiv_entfernen($doc, $id, $b, $me);
                $d = $doc['liste'][$i];
                qs_rev_pruefen($b, $d, 'Das Dokument');
                qs_ablage_stelle($d, $vi === null ? '' : (string)$d['versionen'][$vi]['id'], $me, 'entfernen');
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
                $d = qs_dok_ablegen($doc, $i, $d, $me);
                // im Entwurf gelöscht – die Datei selbst nur, wenn sie nirgends mehr steht (nach einem Abbruch beim Zuordnen auch im Eingang)
                return [$d, (string)$f['name'], $entwurf ? $id : '', $entwurf && qs_datei_suchen($doc['liste'], $id) === null];
            });
            if ($frei) ablage_entfernen('qs', $loeschen);   // erst nach dem Speichern: im Fehlerfall bleibt die Datei
            audit('qs', 'QM-System: Datei aus ' . qs_protokoll_name($d, qs_dok_name($d)) . ($loeschen !== '' ? ' gelöscht (Entwurf)' : ' entfernt (vermerkt)'));
            respond(['ok' => true, 'dokument' => qs_dok_antwort($d)]);
        }

        /* Datei herunterladen (GET, id) – immer als Download; entfernte Dateien nicht, Dateien im Eingang nur mit qs.bearbeiten */
        case 'qs_datei': {
            $me = require_perm('qs.sehen');
            require_once __DIR__ . '/../lib/dateiablage.php';
            $id = is_string($_GET['id'] ?? null) ? $_GET['id'] : '';
            $liste = qs_doc('qs-dokumente')['liste'];
            $ort = qs_datei_suchen($liste, $id);
            if ($ort === null) fail('Datei nicht gefunden.', 404);
            $f = $ort[0];
            if (($f['ziel'] ?? '') === QS_EINGANG && !may($me, 'qs.bearbeiten')) fail('Dateien im Eingang sieht nur, wer bearbeiten darf.', 403);
            foreach ($liste as $i => $d) if ($i === $ort[1] || ($ort[1] === null && (string)$d['id'] === (string)($f['ziel'] ?? ''))) qs_dok_sichtbar($d, $me);
            if (!empty($f['entfernt'])) fail('Die Datei wurde entfernt.', 404);
            ablage_senden('qs', (string)$f['id'], (string)$f['name'], (string)($f['mime'] ?? ''));
        }

        /* Dateien eines Ordners/externen Dokuments (GET dok) für den Ordnerbaum – erst beim Öffnen geladen, nicht in qs_start */
        case 'qs_archiv': {
            $me = require_perm('qs.sehen');
            header('Cache-Control: no-store');
            $doc = qs_doc('qs-dokumente');
            $d = qs_dok_sichtbar($doc['liste'][qs_dokument_index($doc, $_GET['dok'] ?? '')], $me);
            respond(['ok' => true, 'dateien' => array_map('qs_archiv_antwort', qs_archiv_dateien($d))]);
        }

        /* Ordner bzw. Unterordner (GET dok, pfad) als ZIP „<Dokument>/<pfad>/<Datei>“; im Protokoll vermerkt (ohne Ordnernamen) */
        case 'qs_archiv_zip': {
            $me = require_perm('qs.sehen');
            require_once __DIR__ . '/../lib/dateiablage.php';
            $doc = qs_doc('qs-dokumente');
            $d = qs_dok_sichtbar($doc['liste'][qs_dokument_index($doc, $_GET['dok'] ?? '')], $me);
            $pfad = qs_pfad($_GET['pfad'] ?? '');
            $wurzel = ablage_zip_pfad(qs_dok_name($d));
            $e = [];
            foreach (qs_dateien_aktiv(qs_archiv_dateien($d)) as $f) {
                $p = (string)($f['pfad'] ?? '');
                if ($pfad === '' || $p === $pfad || str_starts_with($p, $pfad . '/')) $e[] = ['pfad' => $wurzel . '/' . qs_archiv_zip_pfad($f), 'bereich' => 'qs', 'id' => (string)$f['id']];
            }
            if (!$e) fail('In diesem Ordner liegen keine Dateien.', 404);
            audit('qs', 'QM-System: Ordner ' . qs_protokoll_name($d, qs_dok_name($d)) . ($pfad !== '' ? ' (Unterordner)' : '') . ' als ZIP heruntergeladen (' . qs_dateien_text(count($e)) . ')');
            ablage_zip_senden($wurzel . ($pfad !== '' ? ' - ' . ablage_zip_pfad(str_replace('/', ' - ', $pfad)) : '') . '.zip', $e);
        }

        /* Ablage als ZIP (GET): „QM-System/<Kapitel>/<Dokument>/<Datei>“ (Archivdateien mit ihren Unterordnern) und die Dokumentenliste;
           kapitel = nur ein Kapitel, alle=1 = auch ältere Versionen, Entwürfe und eingezogene Dokumente. Im Protokoll vermerkt. */
        case 'qs_ablage_export': {
            $me = require_perm('qs.sehen');
            require_once __DIR__ . '/../lib/dateiablage.php';
            $stamm = qs_stamm();
            $kapitel = is_string($_GET['kapitel'] ?? null) ? $_GET['kapitel'] : '';
            if ($kapitel !== '') qs_kapitel_pruefen($kapitel, $stamm);
            $alle = ($_GET['alle'] ?? '') === '1';
            $heute = qs_heute();
            $e = qs_ablage_eintraege(qs_sichtbar($me, 'dokumente')['dokumente'], $stamm, $kapitel, $alle, $heute);
            audit('qs', 'QM-System: Dokumentenablage als ZIP heruntergeladen (' . (count($e) - 1) . ' Dateien' . ($kapitel !== '' ? ', Kapitel ' . $kapitel : '') . ($alle ? ', mit älteren Versionen' : '') . ')');
            ablage_zip_senden('QM-System_' . ($kapitel !== '' ? ablage_zip_pfad($kapitel) . '_' : '') . $heute . '.zip', $e);
        }

        /* Ordner-Import, Schritt 1: Zuordnungsplan (qs_import_planen in module/qs/ablage.php) – ordner = [[Ordnerpfad, [[Name, Größe], …]], …],
           wurzel, wahl, freigaben, ohne; anlegen=true legt neue Bereiche (qs.verwalten) und Ordner-Dokumente an und liefert den Plan mit
           ihren Kennungen */
        case 'qs_sammel_plan': {
            $me = require_perm('qs.bearbeiten', true);
            require_once __DIR__ . '/../lib/dateiablage.php';
            [$plan, $neu, $bereiche] = qs_import_planen(body(), $me);
            if ($neu || $bereiche) audit('qs', "QM-System: Ordner-Import: $neu Ordner-Dokumente" . ($bereiche ? " und $bereiche Bereiche" : '') . ' angelegt');
            respond(['ok' => true] + $plan);
        }

        /* Ordner-Import, Schritt 2: bis QS_IMPORT_BUENDEL fertige Uploads (qs_datei_hochladen mit sammeln) in einem Schreibvorgang eintragen –
           uploads = [{upload, status, ver, ohne}] (erwartet laut Plan), dazu wurzel, wahl, freigaben, export wie beim Plan. Das Ziel
           berechnet der Server unter der Sperre neu (qs_import_eintragen). Antwort je Upload: status, datei, grund. */
        case 'qs_import_eintragen': {
            $me = require_perm('qs.bearbeiten', true);
            require_once __DIR__ . '/../lib/dateiablage.php';
            $b = body();
            $ergebnis = qs_import_eintragen(qs_import_uploads($b['uploads'] ?? null), qs_import_angaben($b), $me);
            $n = count(array_filter($ergebnis, function ($e) { return in_array($e['status'], ['abgelegt', 'eingang'], true); }));
            if ($n) audit('qs', 'QM-System: Ordner-Import: ' . qs_dateien_text($n) . ' abgelegt');
            respond(['ok' => true, 'uploads' => $ergebnis]);
        }

        /* Audit-Bericht (GET von, bis): Prüfplan je Monat, Versäumnisse und Fristen, Abweichungen, Maßnahmen, Dokumentenlenkung
           und Handbuch-Änderungen eines Zeitraums (module/qs/bericht.php); qs_bericht_excel liefert dasselbe als Excel und
           vermerkt es im Protokoll. Nur lesen. */
        case 'qs_bericht':
        case 'qs_bericht_excel': {
            $me = require_perm('qs.sehen');
            header('Cache-Control: no-store');
            require_once __DIR__ . '/../module/qs/bericht.php';
            $heute = qs_heute();
            [$von, $bis] = qs_bericht_zeitraum($_GET['von'] ?? '', $_GET['bis'] ?? '', $heute);
            $namen = []; foreach (qs_mitarbeiter() as $m) $namen[$m['id']] = $m['name'];
            $l = qs_sichtbar($me, 'dokumente', 'handbuch', 'pruefplan', 'nachweise', 'massnahmen');
            $b = qs_bericht_daten(qs_stamm(), $l['dokumente'], $l['handbuch'], $l['pruefplan'], $l['nachweise'], $l['massnahmen'], $namen, $von, $bis, $heute);
            if ($action === 'qs_bericht') respond(['ok' => true, 'erstellt' => ['t' => now(), 'von' => (string)$me['name']]] + $b);
            $xlsx = qs_bericht_xlsx($b, (string)$me['name']);
            audit('qs', 'QM-System: Audit-Bericht ' . qs_de($von) . ' – ' . qs_de($bis) . ' als Excel heruntergeladen');
            header('Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet');
            header('Content-Disposition: attachment; filename="QM-Audit-Bericht_' . $von . '_' . $bis . '.xlsx"');
            header('Content-Length: ' . strlen($xlsx));
            header('Cache-Control: private, no-store');
            header('X-Content-Type-Options: nosniff');
            echo $xlsx;
            exit;
        }

        /* Organigramm im offenen Entwurf speichern (dokument, rev, organigramm.knoten) bzw. als PDF-Vorschau (GET dokument) – module/qs/organigramm.php */
        case 'qs_organigramm_save': {
            require_once __DIR__ . '/../module/qs/organigramm.php';
            qs_organigramm_speichern();
        }
        case 'qs_organigramm_vorschau': {
            require_once __DIR__ . '/../module/qs/organigramm.php';
            qs_organigramm_vorschau();
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
            if ($was !== '') audit('qs', 'QM-System: Handbuch ' . qs_protokoll_name($a, $a['kapitel'] . ' ' . $a['nr'] . ' „' . $a['titel'] . '“') . ' ' . $was);
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
            audit('qs', 'QM-System: Prüfung ' . qs_protokoll_name($p, '„' . $p['titel'] . '“') . ' gespeichert' . (empty($p['aktiv']) ? ' (inaktiv)' : ''));
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
            audit('qs', 'QM-System: Nachweis ' . qs_protokoll_name($p, '„' . $p['titel'] . '“') . ' vom ' . qs_de($n['datum']) . ' erfasst (' . QS_ERGEBNIS[$n['ergebnis']] . ')' . ($m ? ', Maßnahme ' . $m['nr'] . ' angelegt' : ''));
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

        /* Datenpaket prüfen (vorschau) und übernehmen – nur in ein leeres Modul oder mit „ersetzen“.
           Enthält das Paket Dokumentenversionen, macht es gelenkte Dokumente gültig – derselbe Schritt wie „freigeben“
           in qs_version_schritt und darum nur mit „qs.freigeben“ (regeln/module.toml, Dokumentenlenkung). */
        case 'qs_import': {
            $me = require_perm('qs.verwalten', true);
            $b = body();
            $erg = qs_paket_pruefen($b['paket'] ?? null, $me);
            if ($erg['zahlen']['versionen'] > 0 && !may($me, 'qs.freigeben'))
                fail('Ein Datenpaket mit Dokumentenversionen macht gelenkte Dokumente gültig – das darf nur, wer prüfen und freigeben darf.', 403);
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

        /* ---------- Verfahrensdokumentation nach GoBD (module/qs/verfahren.php, Export module/qs/verfahren-export.php) ----------
           Eigene, sensible Rechte: qs.verfahren_sehen, qs.verfahren_bearbeiten, qs.verfahren_freigeben. */
        /* Alle Dokumentationen: Abschnitte, IT-Systeme, Fassungen (ohne Inhalt), Abweichung seit der letzten Fassung, eigene Rechte */
        case 'qs_verfahren': {
            $me = require_perm('qs.verfahren_sehen');
            header('Cache-Control: no-store');
            require_once __DIR__ . '/../module/qs/verfahren.php';
            $heute = qs_heute(); $stamm = qs_stamm(); $dokumente = qs_sichtbar($me, 'dokumente')['dokumente'];
            respond(['ok' => true, 'heute' => $heute, 'teile' => QS_VF_TEILE, 'systemArten' => QS_VF_SYSTEM_ART, 'betrieb' => QS_VF_BETRIEB,
                     'ueberpruefungMonate' => QS_VF_UEBERPRUEFUNG_MONATE,
                     'rechte' => ['bearbeiten' => may($me, 'qs.verfahren_bearbeiten'), 'freigeben' => may($me, 'qs.verfahren_freigeben')],
                     'dokus' => array_map(function ($d) use ($dokumente, $stamm, $heute) { return qs_vf_aus($d, $dokumente, $stamm, $heute); }, qs_doc(QS_VF_DOKUMENT)['liste'])]);
        }

        /* Dokumentation anlegen (muster: mit Mustergliederung), allgemeine Angaben ändern oder – nur ohne Fassung – löschen */
        case 'qs_verfahren_save': {
            $me = require_perm('qs.verfahren_bearbeiten', true);
            $b = body();
            require_once __DIR__ . '/../module/qs/verfahren.php';
            [$d, $was] = with_lock('qs-dokumente', function () use ($b, $me) {
                if ((string)($b['id'] ?? '') === '') {
                    $doc = qs_doc(QS_VF_DOKUMENT);
                    if (count($doc['liste']) >= QS_VF_MAX_DOKUS) fail('Zu viele Dokumentationen.', 422);
                    $d = ['id' => qs_id('v')] + qs_vf_kopf_felder($b) + ['kopfRev' => 1, 'erstellt' => qs_wer($me), 'abschnitte' => [], 'systeme' => [], 'fassungen' => [], 'pruefungen' => []];
                    $pos = [];
                    if (!empty($b['muster'])) foreach (qs_vf_muster() as [$teil, $titel, $hinweis]) {
                        $pos[$teil] = ($pos[$teil] ?? 0) + 1;
                        $d['abschnitte'][] = ['id' => qs_id('a'), 'teil' => $teil, 'pos' => $pos[$teil], 'titel' => $titel, 'text' => '', 'hinweis' => $hinweis,
                                              'systeme' => [], 'verweise' => [], 'zustaendig' => '', 'fertig' => false, 'rev' => 1];
                    }
                    $doc['liste'][] = $d;
                    return [qs_vf_ablegen($doc, count($doc['liste']) - 1, $d, $me), 'angelegt' . ($pos ? ' (mit Mustergliederung)' : '')];
                }
                [$doc, $i, $d] = qs_vf_laden($b['id']);
                if (array_key_exists('kopfRev', $b) && (int)$b['kopfRev'] !== (int)($d['kopfRev'] ?? 0))
                    respond(['ok' => false, 'code' => 'konflikt', 'error' => 'Die Angaben wurden inzwischen von ' . ($d['geaendert']['von'] ?? 'jemand anderem') . ' geändert. Bitte neu laden.'], 409);
                if (!empty($b['loeschen'])) {
                    if ($d['fassungen']) fail('Eine Dokumentation mit freigegebener Fassung wird aufbewahrt und kann nicht gelöscht werden.', 409);
                    array_splice($doc['liste'], $i, 1);
                    qs_schreiben(QS_VF_DOKUMENT, $doc);
                    return [$d, 'gelöscht'];
                }
                $d = qs_vf_kopf_felder($b) + $d;
                $d['kopfRev'] = (int)($d['kopfRev'] ?? 0) + 1;
                return [qs_vf_ablegen($doc, $i, $d, $me), 'allgemeine Angaben geändert'];
            });
            audit('qs', 'QM-System: Verfahrensdokumentation „' . $d['titel'] . '“ ' . $was);
            if ($was === 'gelöscht') respond(['ok' => true, 'geloescht' => true]);
            qs_vf_antworten($d, $me);
        }

        /* Abschnitt anlegen, ändern oder entfernen (der Arbeitsstand ist frei änderbar; Fassungen bleiben unberührt) */
        case 'qs_verfahren_abschnitt_save': {
            $me = require_perm('qs.verfahren_bearbeiten', true);
            $b = body();
            require_once __DIR__ . '/../module/qs/verfahren.php';
            [$d, $was] = with_lock('qs-dokumente', function () use ($b, $me) {
                [$doc, $i, $d] = qs_vf_laden($b['doku'] ?? '');
                $j = null; $alt = null;
                if ((string)($b['id'] ?? '') !== '') { $j = qs_vf_index($d['abschnitte'], $b['id'], 'Abschnitt'); $alt = $d['abschnitte'][$j]; qs_rev_pruefen($b, $alt, 'Der Abschnitt'); }
                elseif (count($d['abschnitte']) >= QS_VF_MAX_ABSCHNITTE) fail('Zu viele Abschnitte.', 422);
                if ($alt !== null && !empty($b['loeschen'])) {
                    array_splice($d['abschnitte'], $j, 1);
                    return [qs_vf_ablegen($doc, $i, $d, $me), 'Abschnitt „' . $alt['titel'] . '“ entfernt'];
                }
                $felder = qs_vf_abschnitt_felder($b, $d);
                if ($alt === null) $a = ['id' => qs_id('a')] + $felder + ['pos' => qs_vf_naechste_pos($d['abschnitte'], $felder['teil']), 'hinweis' => ''];
                else {
                    $a = $felder + $alt;
                    if ($alt['teil'] !== $a['teil']) $a['pos'] = qs_vf_naechste_pos($d['abschnitte'], $a['teil']);
                }
                $a['rev'] = (int)($a['rev'] ?? 0) + 1;
                $a['geaendert'] = qs_wer($me);
                if ($j === null) $d['abschnitte'][] = $a; else $d['abschnitte'][$j] = $a;
                return [qs_vf_ablegen($doc, $i, $d, $me), 'Abschnitt „' . $a['titel'] . '“ ' . ($alt === null ? 'angelegt' : 'geändert')];
            });
            audit('qs', 'QM-System: Verfahrensdokumentation „' . $d['titel'] . '“ – ' . $was);
            qs_vf_antworten($d, $me);
        }

        /* Abschnitt innerhalb seines Teils eine Stelle nach oben oder unten setzen (richtung: auf | ab) */
        case 'qs_verfahren_ordnen': {
            $me = require_perm('qs.verfahren_bearbeiten', true);
            $b = body();
            require_once __DIR__ . '/../module/qs/verfahren.php';
            $d = with_lock('qs-dokumente', function () use ($b, $me) {
                [$doc, $i, $d] = qs_vf_laden($b['doku'] ?? '');
                $j = qs_vf_index($d['abschnitte'], $b['id'] ?? '', 'Abschnitt');
                $richtung = qs_wahl($b['richtung'] ?? '', ['auf', 'ab'], 'Richtung');
                $teil = $d['abschnitte'][$j]['teil'];
                $reihe = [];
                foreach ($d['abschnitte'] as $k => $x) if ($x['teil'] === $teil) $reihe[] = $k;
                usort($reihe, function ($x, $y) use ($d) { return (int)($d['abschnitte'][$x]['pos'] ?? 0) <=> (int)($d['abschnitte'][$y]['pos'] ?? 0); });
                $p = (int)array_search($j, $reihe, true);
                $q = $p + ($richtung === 'auf' ? -1 : 1);
                if (!isset($reihe[$q])) return $d;   // steht schon am Rand
                [$reihe[$p], $reihe[$q]] = [$reihe[$q], $reihe[$p]];
                foreach ($reihe as $n => $k) $d['abschnitte'][$k]['pos'] = $n + 1;
                return qs_vf_ablegen($doc, $i, $d, $me);
            });
            qs_vf_antworten($d, $me);
        }

        /* IT-System anlegen, ändern oder entfernen; steht es in einer Fassung, wird es nur „außer Betrieb“ gesetzt */
        case 'qs_verfahren_system_save': {
            $me = require_perm('qs.verfahren_bearbeiten', true);
            $b = body();
            require_once __DIR__ . '/../module/qs/verfahren.php';
            [$d, $was] = with_lock('qs-dokumente', function () use ($b, $me) {
                [$doc, $i, $d] = qs_vf_laden($b['doku'] ?? '');
                $j = null; $alt = null;
                if ((string)($b['id'] ?? '') !== '') { $j = qs_vf_index($d['systeme'], $b['id'], 'IT-System'); $alt = $d['systeme'][$j]; qs_rev_pruefen($b, $alt, 'Das IT-System'); }
                elseif (count($d['systeme']) >= QS_VF_MAX_SYSTEME) fail('Zu viele IT-Systeme.', 422);
                if ($alt !== null && !empty($b['loeschen'])) {
                    if (qs_vf_system_in_fassung($d, (string)$alt['id'])) fail('Das System steht in einer freigegebenen Fassung und bleibt dokumentiert. Bitte „Außer Betrieb seit“ eintragen.', 409);
                    array_splice($d['systeme'], $j, 1);
                    foreach ($d['abschnitte'] as &$a) $a['systeme'] = array_values(array_diff($a['systeme'], [(string)$alt['id']]));
                    unset($a);
                    return [qs_vf_ablegen($doc, $i, $d, $me), 'IT-System „' . $alt['name'] . '“ entfernt'];
                }
                $s = qs_vf_system_felder($b) + ($alt ?? ['id' => qs_id('s')]);
                $s['rev'] = (int)($s['rev'] ?? 0) + 1;
                $s['geaendert'] = qs_wer($me);
                if ($j === null) $d['systeme'][] = $s; else $d['systeme'][$j] = $s;
                return [qs_vf_ablegen($doc, $i, $d, $me), 'IT-System „' . $s['name'] . '“ ' . ($alt === null ? 'angelegt' : 'geändert')];
            });
            audit('qs', 'QM-System: Verfahrensdokumentation „' . $d['titel'] . '“ – ' . $was);
            qs_vf_antworten($d, $me);
        }

        /* Neue Fassung freigeben (grund = Anlass, gueltigAb) oder – ohneAenderung – „ohne Änderung überprüft“ vermerken */
        case 'qs_verfahren_freigeben': {
            $me = require_perm('qs.verfahren_freigeben', true);
            $b = body();
            require_once __DIR__ . '/../module/qs/verfahren.php';
            [$d, $was] = with_lock('qs-dokumente', function () use ($b, $me) {
                [$doc, $i, $d] = qs_vf_laden($b['doku'] ?? '');
                qs_rev_pruefen($b, $d, 'Die Verfahrensdokumentation');
                $heute = qs_heute(); $stamm = qs_stamm(); $dokumente = qs_doc('qs-dokumente')['liste'];
                if (!empty($b['ohneAenderung'])) {
                    $letzte = $d['fassungen'] ? $d['fassungen'][count($d['fassungen']) - 1] : null;
                    if ($letzte === null) throw new InvalidArgumentException('Es gibt noch keine freigegebene Fassung.');
                    if (qs_vf_abweichung(qs_vf_inhalt($d, $dokumente, $stamm), is_array($letzte['inhalt'] ?? null) ? $letzte['inhalt'] : [])['offen'])
                        throw new InvalidArgumentException('Der Arbeitsstand weicht von der Fassung ' . (int)$letzte['nr'] . ' ab – bitte als neue Fassung freigeben.');
                    if (count($d['pruefungen']) >= QS_VF_MAX_PRUEFUNGEN) fail('Zu viele Vermerke.', 422);
                    $d['pruefungen'][] = ['datum' => $heute, 'fassung' => (int)$letzte['nr'], 'notiz' => qs_text($b['notiz'] ?? '', 500, 'Bemerkung')] + qs_wer($me);
                    return [qs_vf_ablegen($doc, $i, $d, $me), 'ohne Änderung überprüft (Fassung ' . (int)$letzte['nr'] . ')'];
                }
                $grund = qs_text($b['grund'] ?? '', 1000, 'Anlass');
                if ($grund === '') throw new InvalidArgumentException('Bitte den Anlass der Fassung angeben, z. B. „Erstfassung“ oder „Neues Archivsystem“.');
                $ab = qs_datum($b['gueltigAb'] ?? $heute, 'Gültig ab');
                $f = qs_vf_fassung_bilden($d, $dokumente, $stamm, $me, $grund, $ab, $heute);
                $d['fassungen'][] = $f;
                return [qs_vf_ablegen($doc, $i, $d, $me), 'Fassung ' . $f['nr'] . ' freigegeben (gültig ab ' . qs_de($ab) . ', Anlass: ' . mb_substr($grund, 0, 120) . ')'];
            });
            audit('qs', 'QM-System: Verfahrensdokumentation „' . $d['titel'] . '“ – ' . $was);
            qs_vf_antworten($d, $me);
        }

        /* Export (GET doku): fassung=N als PDF (0 = Arbeitsstand als Entwurf) oder Export für Prüfungen von/bis – als PDF,
           mit dokumente=1 als ZIP samt verknüpfter QM-Dokumente in der damaligen Version. Nur lesen, im Protokoll vermerkt. */
        case 'qs_verfahren_export': {
            $me = require_perm('qs.verfahren_sehen');
            header('Cache-Control: no-store');
            require_once __DIR__ . '/../lib/dateiablage.php';
            require_once __DIR__ . '/../module/qs/verfahren.php';
            require_once __DIR__ . '/../module/qs/verfahren-export.php';
            [, , $d] = qs_vf_laden($_GET['doku'] ?? '');
            qs_vf_export($d, $_GET, $me, qs_sichtbar($me, 'dokumente')['dokumente'], qs_stamm());
        }
}
