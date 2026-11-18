<?php
declare(strict_types=1);
/* Aktionen: Modul Container-Import, Reiter EUDR – Herkunftsbetriebe mit Geolokalisierung, Sendungen, Risikoprofil und
   GeoJSON-Datei für das EU-Informationssystem (Oberfläche containerimport.intern; Funktionen in
   app/api/module/containerimport/eudr.php und geometrie.php).
   Rechte (GR-103): Modulzugang containerimport.zugang für jede Aktion; Inhalte (ansehen, Dateien prüfen, exportieren) mit
   containerimport.eudr_sehen, alles, was speichert, mit containerimport.eudr_bearbeiten. Nichts wird gelöscht (archivieren, Gegenprüfungen nur ergänzen);
   eine abgeschlossene Bewertung hält Profil und Betriebe als Schnappschuss fest (GR-106).
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Mitarbeiter mit Modulzugang und dem Recht anzusehen (lesende Aktionen; $post = Aktion kommt als POST mit CSRF) */
function eudr_leser(bool $post = false): array
{
    $me = require_perm('containerimport.eudr_sehen', $post);
    require_modulzugang('containerimport', $post);
    return $me;
}
/* Mitarbeiter mit Modulzugang und dem Recht zu bearbeiten (schreibende Aktionen) */
function eudr_bearbeiter(): array
{
    $me = require_perm('containerimport.eudr_bearbeiten', true);
    require_modulzugang('containerimport', true);
    return $me;
}
/* Gespeicherte Sendung nach id (404) samt ihrer Stelle im Dokument */
function eudr_sendung_holen(array $doc, $id): array
{
    $i = eudr_stelle($doc['liste'], is_string($id) ? $id : '');
    if ($i === null) fail('Sendung nicht gefunden.', 404);
    return [$i, $doc['liste'][$i]];
}

switch ($action) {
        /* Stand der Seite: Betriebe und Sendungen mit Befunden und Risikoprofil, Länder, Portale, eigene Rechte */
        case 'containerimport_start': {
            $me = eudr_leser();
            header('Cache-Control: no-store');
            respond(['ok' => true, 'name' => $me['name'], 'rechte' => ['bearbeiten' => may($me, 'containerimport.eudr_bearbeiten')]] + eudr_stand());
        }

        /* Dateien prüfen, ohne zu speichern: Lieferanten-GeoJSON, gelesene Berichte, eingefügte Koordinaten (POST wegen Inhalt) */
        case 'containerimport_eudr_pruefen': {
            eudr_leser(true);
            $dateien = body()['dateien'] ?? null;
            if (!is_array($dateien) || !$dateien || !array_is_list($dateien) || count($dateien) > 50) fail('Bitte 1 bis 50 Dateien auswählen.', 422);
            $bekannt = eudr_bekannt_tabelle(eudr_betriebe()['liste']);
            $ergebnis = array_map(fn($d) => eudr_datei_pruefen(is_array($d) ? $d : [], $bekannt), $dateien);
            $punkte = 0;
            foreach ($ergebnis as $datei) foreach ($datei['orte'] as $ort) $punkte += $ort['punkte'];
            if ($punkte > EUDR_MAX_PUNKTE_ANFRAGE) fail('Zu viele Punkte in einem Durchgang – bitte die Dateien einzeln einlesen.', 422);
            respond(['ok' => true, 'dateien' => $ergebnis]);
        }

        /* Betriebe anlegen oder ändern (einzeln aus dem Fenster oder mehrere nach dem Einlesen); „sendung“ ordnet sie zu */
        case 'containerimport_eudr_betriebe_save': {
            $me = eudr_bearbeiter();
            $b = body();
            $eingaben = $b['betriebe'] ?? null;
            if (!is_array($eingaben) || !$eingaben || !array_is_list($eingaben) || count($eingaben) > EUDR_MAX_ORTE_JE_DATEI) fail('Keine Betriebe zum Speichern.', 422);
            $gespeichert = with_lock(EUDR_SPERRE, function () use ($b, $eingaben, $me) {
                $doc = eudr_betriebe();
                $sendungen = eudr_sendungen();
                $ziel = null;
                if (($b['sendung'] ?? '') !== '') {
                    [$ziel, $s] = eudr_sendung_holen($sendungen, $b['sendung']);
                    if (!empty($s['abschluss'])) fail('Die Bewertung dieser Sendung ist abgeschlossen. Bitte zuerst wieder öffnen.', 409);
                }
                $gespeichert = [];
                foreach ($eingaben as $e) {
                    if (!is_array($e)) throw new InvalidArgumentException('Ungültiger Betrieb.');
                    $i = ($e['id'] ?? '') !== '' ? eudr_stelle($doc['liste'], (string)$e['id']) : null;
                    if (($e['id'] ?? '') !== '' && $i === null) fail('Betrieb nicht gefunden.', 404);
                    $alt = $i !== null ? $doc['liste'][$i] : null;
                    if ($alt) eudr_rev_pruefen($e, $alt, 'Der Betrieb „' . $alt['name'] . '“');
                    elseif (count($doc['liste']) >= EUDR_MAX_BETRIEBE) fail('Zu viele Betriebe.', 422);
                    $neu = ['id' => $alt['id'] ?? eudr_id('b')] + eudr_betrieb_pruefen($e, $alt)
                        + ['pruefungen' => $alt['pruefungen'] ?? [], 'erstellt' => $alt['erstellt'] ?? eudr_wer($me), 'rev' => (int)($alt['rev'] ?? 0) + 1, 'geaendert' => eudr_wer($me)];
                    if ($i === null) $doc['liste'][] = $neu; else $doc['liste'][$i] = $neu;
                    $gespeichert[] = $neu;
                }
                if (array_sum(array_map(fn($x) => geo_punktzahl($x['geometrie']), $doc['liste'])) > EUDR_MAX_PUNKTE) fail('Die Umrisse aller Betriebe zusammen sind zu umfangreich. Bitte den Umriss vereinfachen lassen oder an den Administrator wenden.', 422);
                eudr_betriebe_schreiben($doc);
                if ($ziel !== null) {
                    $s = $sendungen['liste'][$ziel];
                    $s['betriebe'] = array_values(array_unique(array_merge($s['betriebe'], array_column($gespeichert, 'id'))));
                    $s['rev']++; $s['geaendert'] = eudr_wer($me);
                    $sendungen['liste'][$ziel] = $s;
                    eudr_sendungen_schreiben($sendungen);
                }
                return $gespeichert;
            });
            audit('containerimport', 'EUDR: ' . (count($gespeichert) === 1 ? 'Herkunftsbetrieb „' . $gespeichert[0]['name'] . '“' : count($gespeichert) . ' Herkunftsbetriebe') . ' gespeichert');
            respond(['ok' => true] + eudr_stand());
        }

        /* Eigene Gegenprüfung (Global Nature Watch, Whisp …) an einem Betrieb ergänzen – wird nie geändert oder gelöscht */
        case 'containerimport_eudr_gegenpruefung': {
            $me = eudr_bearbeiter();
            $b = body();
            $name = with_lock(EUDR_SPERRE, function () use ($b, $me) {
                $doc = eudr_betriebe();
                $i = eudr_stelle($doc['liste'], is_string($b['id'] ?? null) ? $b['id'] : '');
                if ($i === null) fail('Betrieb nicht gefunden.', 404);
                if (count($doc['liste'][$i]['pruefungen'] ?? []) >= EUDR_MAX_PRUEFUNGEN) fail('Zu viele Gegenprüfungen an diesem Betrieb.', 422);
                $doc['liste'][$i]['pruefungen'][] = eudr_pruefung_pruefen($b, $me);
                $doc['liste'][$i]['rev']++; $doc['liste'][$i]['geaendert'] = eudr_wer($me);
                eudr_betriebe_schreiben($doc);
                return $doc['liste'][$i]['name'];
            });
            audit('containerimport', 'EUDR: Gegenprüfung für „' . $name . '“ eingetragen');
            respond(['ok' => true] + eudr_stand());
        }

        /* Sendung anlegen oder ändern. Nach dem Abschluss lassen sich nur noch Sorgfaltserklärung und Notiz ergänzen. */
        case 'containerimport_eudr_sendung_save': {
            $me = eudr_bearbeiter();
            $b = body();
            $s = with_lock(EUDR_SPERRE, function () use ($b, $me) {
                $doc = eudr_sendungen();
                $alt = null; $i = null;
                if (($b['id'] ?? '') !== '') {
                    [$i, $alt] = eudr_sendung_holen($doc, $b['id']);
                    eudr_rev_pruefen($b, $alt, 'Die Sendung');
                } elseif (count($doc['liste']) >= EUDR_MAX_SENDUNGEN) fail('Zu viele Sendungen.', 422);
                if ($alt && !empty($alt['abschluss'])) {
                    $neu = ['dds' => eudr_dds_pruefen(is_array($b['dds'] ?? null) ? $b['dds'] : []), 'notiz' => eudr_text($b['notiz'] ?? '', 2000, 'Notiz')] + $alt;
                } else {
                    $ids = array_column(eudr_betriebe()['liste'], 'id');
                    $neu = ['id' => $alt['id'] ?? eudr_id('s')] + eudr_sendung_pruefen($b, $ids)
                        + ['abschluss' => null, 'fruehere' => $alt['fruehere'] ?? [], 'erstellt' => $alt['erstellt'] ?? eudr_wer($me)];
                }
                $neu['rev'] = (int)($alt['rev'] ?? 0) + 1; $neu['geaendert'] = eudr_wer($me);
                if ($i === null) $doc['liste'][] = $neu; else $doc['liste'][$i] = $neu;
                eudr_sendungen_schreiben($doc);
                return $neu;
            });
            audit('containerimport', 'EUDR: Sendung „' . $s['nummer'] . '“ gespeichert');
            respond(['ok' => true, 'id' => $s['id']] + eudr_stand());
        }

        /* Bewertung abschließen (Ergebnis, Begründung, Schnappschuss von Profil und Betrieben) oder wieder öffnen (mit Grund).
           „Vernachlässigbar“ geht nie mit einem kritischen Kriterium, mit offenen Kriterien nur mit Begründung. */
        case 'containerimport_eudr_sendung_abschluss': {
            $me = eudr_bearbeiter();
            $b = body();
            $s = with_lock(EUDR_SPERRE, function () use ($b, $me) {
                $doc = eudr_sendungen();
                [$i, $s] = eudr_sendung_holen($doc, $b['id'] ?? '');
                eudr_rev_pruefen($b, $s, 'Die Sendung');
                if (!empty($b['oeffnen'])) {
                    if (empty($s['abschluss'])) fail('Die Bewertung ist nicht abgeschlossen.', 409);
                    $grund = eudr_text($b['grund'] ?? '', 500, 'Grund', true);
                    $s['fruehere'][] = $s['abschluss'] + ['geoeffnet' => eudr_wer($me), 'grund' => $grund];   // samt Schnappschuss (GR-106)
                    foreach (array_slice(array_keys($s['fruehere']), 0, -EUDR_MAX_FRUEHERE) as $k) unset($s['fruehere'][$k]['betriebe']);   // ältere: Profil bleibt, Umrisse nicht
                    $s['abschluss'] = null;
                } else {
                    if (!empty($s['abschluss'])) fail('Die Bewertung ist bereits abgeschlossen.', 409);
                    $s['abschluss'] = eudr_abschluss($s, $b, array_map('eudr_betrieb_sicht', eudr_betriebe()['liste']), $me);
                }
                $s['rev']++; $s['geaendert'] = eudr_wer($me);
                $doc['liste'][$i] = $s;
                eudr_sendungen_schreiben($doc);
                return $s;
            });
            audit('containerimport', 'EUDR: Bewertung der Sendung „' . $s['nummer'] . '“ ' . ($s['abschluss'] ? 'abgeschlossen (' . ($s['abschluss']['ergebnis'] === 'vernachlaessigbar' ? 'Risiko vernachlässigbar' : 'Risiko nicht vernachlässigbar') . ')' : 'wieder geöffnet'));
            respond(['ok' => true] + eudr_stand());
        }

        /* GeoJSON-Datei für das EU-Informationssystem: Betriebe einer Sendung (abgeschlossen: der Schnappschuss) oder ein Betrieb */
        case 'containerimport_eudr_export': {
            eudr_leser();
            header('Cache-Control: no-store');
            $betriebe = array_map('eudr_betrieb_sicht', eudr_betriebe()['liste']);
            if (isset($_GET['betrieb'])) {
                $bs = array_values(array_filter($betriebe, fn($x) => $x['id'] === $_GET['betrieb']));
                if (!$bs) fail('Betrieb nicht gefunden.', 404);
                $name = $bs[0]['kennung'] !== '' ? $bs[0]['kennung'] : $bs[0]['name'];
            } else {
                [, $s] = eudr_sendung_holen(eudr_sendungen(), $_GET['sendung'] ?? '');
                $bs = eudr_sendung_betriebe($s, $betriebe);
                $name = $s['nummer'];
            }
            $datei = 'EUDR_' . trim((string)preg_replace('/[^A-Za-z0-9_-]+/', '_', $name), '_') . '.geojson';
            respond(['ok' => true, 'datei' => $datei] + eudr_geojson($bs));
        }
}
