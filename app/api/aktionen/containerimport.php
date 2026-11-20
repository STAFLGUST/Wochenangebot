<?php
declare(strict_types=1);
/* Aktionen: Modul Container-Import – Container (im Code „sendung“) mit Lieferant, Partie-, Akten- und Containernummer und
   Stand; Reiter EUDR – Farmer (im Code „betrieb“) mit Geolokalisierung, Risikoprofil und
   GeoJSON-Datei für das EU-Informationssystem (Oberfläche containerimport.intern; Funktionen in
   app/api/module/containerimport/eudr.php und geometrie.php), Abfrage von Whisp für die Gegenprüfung (whisp.php).
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

switch ($action) {
        /* Stand der Seite: Betriebe und Sendungen mit Befunden und Risikoprofil, Länder, Portale, eigene Rechte */
        case 'containerimport_start': {
            $me = eudr_leser();
            require_once __DIR__ . '/../module/containerimport/whisp.php';
            header('Cache-Control: no-store');
            $darf = may($me, 'containerimport.eudr_bearbeiten');
            respond(['ok' => true, 'name' => $me['name'], 'rechte' => ['bearbeiten' => $darf, 'whisp' => $darf && whisp_eingerichtet()],
                'lieferanten' => $darf ? eudr_lieferanten() : []] + eudr_stand());   // Stammdaten nur zum Auswählen und nur hier, nicht in jeder Antwort
        }

        /* Geodaten-Katalog GEOS-EUDR (Thünen-Institut, MIT-Lizenz): öffentliche Metadaten offener Geodatensätze zu Wald, nur
           lesen, Recht wie die übrige EUDR-Ansicht. Die Datei schreibt nur werkzeuge/eudr_geodatenkatalog.py. */
        case 'containerimport_eudr_geodaten': {
            eudr_leser();
            $katalog = json_decode((string)@file_get_contents(__DIR__ . '/../module/containerimport/geodatenkatalog.json'), true);
            if (!is_array($katalog)) fail('Der Geodaten-Katalog ist nicht lesbar.', 500);
            respond(['ok' => true] + $katalog);
        }

        /* Dateien prüfen, ohne zu speichern: Lieferanten-GeoJSON, gelesene Berichte, eingefügte Koordinaten (POST wegen Inhalt).
           Steht eine Nummer aus den Papieren in diesem Durchgang bei zwei neuen Farmern, ist das zweite Vorkommen ein Fehler. */
        case 'containerimport_eudr_pruefen': {
            eudr_leser(true);
            $dateien = body()['dateien'] ?? null;
            if (!is_array($dateien) || !$dateien || !array_is_list($dateien) || count($dateien) > 50) fail('Bitte 1 bis 50 Dateien auswählen.', 422);
            $bekannt = eudr_bekannt_tabelle(eudr_betriebe()['liste']);
            $ergebnis = ci_doppelte_nummern_melden(array_map(fn($d) => eudr_datei_pruefen(is_array($d) ? $d : [], $bekannt), $dateien));
            $punkte = 0;
            foreach ($ergebnis as $datei) foreach ($datei['orte'] as $ort) $punkte += $ort['punkte'];
            if ($punkte > EUDR_MAX_PUNKTE_ANFRAGE) fail('Zu viele Punkte in einem Durchgang – bitte die Dateien einzeln einlesen.', 422);
            respond(['ok' => true, 'dateien' => $ergebnis]);
        }

        /* Betriebe anlegen oder ändern (einzeln aus dem Fenster oder mehrere nach dem Einlesen); „sendung“ ordnet sie zu.
           Ein neuer Farmer bekommt die nächste eigene Nummer (seine Stelle); die Nummer aus den Papieren ist je Land eindeutig (422). Container
           mit offener Bewertung, die eine gespeicherte Nummer vermerkt haben, bekommen den Farmer zugeordnet. */
        case 'containerimport_eudr_betriebe_save': {
            $me = eudr_bearbeiter();
            $b = body();
            $eingaben = $b['betriebe'] ?? null;
            if (!is_array($eingaben) || !$eingaben || !array_is_list($eingaben) || count($eingaben) > EUDR_MAX_ORTE_JE_DATEI) fail('Keine Farmer zum Speichern.', 422);
            [$gespeichert, $zugeordnet] = with_lock(EUDR_SPERRE, function () use ($b, $eingaben, $me) {
                $doc = eudr_betriebe();
                $sendungen = eudr_sendungen();
                $ziel = null;
                if (($b['sendung'] ?? '') !== '') {
                    [$ziel, $s] = eudr_holen($sendungen, $b['sendung']);
                    if (!empty($s['abschluss'])) fail('Die Bewertung dieses Containers ist abgeschlossen. Bitte zuerst wieder öffnen.', 409);
                }
                $gespeichert = [];
                $vorher = count($doc['liste']);   // Farmer ab dieser Stelle legt erst dieser Durchgang an
                $index = ci_nummern_index($doc['liste']);
                foreach ($eingaben as $e) {
                    if (!is_array($e)) throw new InvalidArgumentException('Ungültiger Farmer.');
                    $i = ($e['id'] ?? '') !== '' ? eudr_stelle($doc['liste'], (string)$e['id']) : null;
                    if (($e['id'] ?? '') !== '' && $i === null) fail('Farmer nicht gefunden.', 404);
                    $alt = $i !== null ? $doc['liste'][$i] : null;
                    if ($alt) eudr_rev_pruefen($e, $alt, 'Der Farmer „' . $alt['name'] . '“');
                    elseif (count($doc['liste']) >= EUDR_MAX_BETRIEBE) fail('Zu viele Farmer.', 422);
                    $neu = ['id' => $alt['id'] ?? eudr_id('b')] + eudr_betrieb_pruefen($e, $alt)
                        + ['pruefungen' => $alt['pruefungen'] ?? [], 'erstellt' => $alt['erstellt'] ?? eudr_wer($me), 'rev' => (int)($alt['rev'] ?? 0) + 1, 'geaendert' => eudr_wer($me)];
                    // nur eine neue oder geänderte Nummer prüfen: Doppelte aus der Zeit vor dieser Regel blockieren keine andere Änderung
                    $k = ci_nummer_schluessel($neu['land'], $neu['kennung']);
                    $geaendert = !$alt || ci_nummer_schluessel($alt['land'], $alt['kennung']) !== $k;
                    $j = $geaendert ? ci_nummer_vergeben($index, $k, $i) : null;
                    if ($j !== null) fail('Die Nummer „' . $neu['kennung'] . '“ aus den Papieren ' . ($j >= $vorher
                        ? 'steht in dieser Auswahl zweimal (auch bei „' . $doc['liste'][$j]['name'] . '“). Bitte nur einmal übernehmen.'
                        : 'hat in ' . (EUDR_LAENDER[$neu['land']]['name'] ?? $neu['land']) . ' schon der Farmer „' . $doc['liste'][$j]['name'] . '“ (' . ci_farmer_nr($j + 1) . ').'), 422);
                    $i ??= count($doc['liste']);
                    $doc['liste'][$i] = ['nr' => $i + 1] + $neu;   // nr nur für Meldungen und Zuordnung, gespeichert wird sie nie
                    $gespeichert[] = $doc['liste'][$i];
                    if (!$alt) { if ($k !== '') $index[$k] ??= $i; }
                    elseif ($geaendert) $index = ci_nummern_index($doc['liste']);   // selten: Nummer eines Farmers geändert
                }
                if (array_sum(array_map(fn($x) => geo_punktzahl($x['geometrie']), $doc['liste'])) > EUDR_MAX_PUNKTE) fail('Die Umrisse aller Farmer zusammen sind zu umfangreich. Bitte den Umriss vereinfachen lassen oder an den Administrator wenden.', 422);
                eudr_betriebe_schreiben($doc);
                if ($ziel !== null) {
                    $s = $sendungen['liste'][$ziel];
                    $s['betriebe'] = array_values(array_unique(array_merge($s['betriebe'], array_column($gespeichert, 'id'))));
                    $s['rev']++; $s['geaendert'] = eudr_wer($me);
                    $sendungen['liste'][$ziel] = $s;
                }
                [$sendungen['liste'], $zugeordnet] = ci_offene_nummern_zuordnen($sendungen['liste'], $gespeichert, $me);
                if ($ziel !== null || $zugeordnet) eudr_sendungen_schreiben($sendungen);
                return [$gespeichert, $zugeordnet];
            });
            audit('containerimport', 'EUDR: ' . (count($gespeichert) === 1 ? 'Farmer „' . $gespeichert[0]['name'] . '“' : count($gespeichert) . ' Farmer') . ' gespeichert'
                . ($zugeordnet ? '; vermerkte Farmer-Nummern an ' . $zugeordnet . ' Container' . ($zugeordnet === 1 ? '' : 'n') . ' zugeordnet' : ''));
            respond(['ok' => true] + eudr_stand());
        }

        /* Original einer eingelesenen Datei (Bericht, GeoJSON) in Teilen hochladen und im Eingang des QM-Systems ablegen
           (Entscheidung des Inhabers 18.11.2026; Schnittstelle des QM-Systems qs_eingang_hochladen, GR-101). „lieferant“ wird
           zum Unterordner. Nach dem letzten Teil steht an den Betrieben aus dieser Datei, wo das Original liegt. */
        case 'containerimport_eudr_original': {
            $me = eudr_bearbeiter();
            require_once __DIR__ . '/../lib/dateiablage.php';
            require_once __DIR__ . '/../module/qs/ablage.php';
            $b = body();
            $lieferant = str_replace(['/', '\\'], ' ', eudr_text($b['lieferant'] ?? '', 120, 'Lieferant'));
            $ablage = qs_eingang_hochladen($me, $b, EUDR_QM_ORDNER . ($lieferant !== '' ? '/' . $lieferant : ''));
            if (!$ablage['fertig']) respond(['ok' => true, 'fertig' => false, 'upload' => $ablage['upload'], 'empfangen' => $ablage['empfangen']]);
            if ($ablage['status'] === 'fehler') fail($ablage['grund'], $ablage['code']);
            $n = with_lock(EUDR_SPERRE, function () use ($ablage, $me) {
                $doc = eudr_betriebe();
                [$doc['liste'], $n] = eudr_original_vermerken($doc['liste'], $ablage, $me);
                if ($n) eudr_betriebe_schreiben($doc);
                return $n;
            });
            audit('containerimport', 'EUDR: Original „' . $ablage['name'] . '“ im Eingang des QM-Systems ' . ($ablage['status'] === 'eingang' ? 'abgelegt' : 'schon vorhanden'));
            respond(['ok' => true, 'fertig' => true, 'status' => $ablage['status'], 'vermerkt' => $n] + eudr_stand());
        }

        /* Eigene Gegenprüfung (Global Nature Watch, Whisp …) an einem Betrieb ergänzen – wird nie geändert oder gelöscht */
        case 'containerimport_eudr_gegenpruefung': {
            $me = eudr_bearbeiter();
            $b = body();
            $name = with_lock(EUDR_SPERRE, function () use ($b, $me) {
                $doc = eudr_betriebe();
                $i = eudr_stelle($doc['liste'], is_string($b['id'] ?? null) ? $b['id'] : '');
                if ($i === null) fail('Farmer nicht gefunden.', 404);
                if (count($doc['liste'][$i]['pruefungen'] ?? []) >= EUDR_MAX_PRUEFUNGEN) fail('Zu viele Gegenprüfungen an diesem Farmer.', 422);
                $doc['liste'][$i]['pruefungen'][] = eudr_pruefung_pruefen($b, $me);
                $doc['liste'][$i]['rev']++; $doc['liste'][$i]['geaendert'] = eudr_wer($me);
                eudr_betriebe_schreiben($doc);
                return $doc['liste'][$i]['name'];
            });
            audit('containerimport', 'EUDR: Gegenprüfung für „' . $name . '“ eingetragen');
            respond(['ok' => true] + eudr_stand());
        }

        /* Whisp (FAO) für einen Betrieb abfragen: mit „id“ starten (nur der Umriss geht an Whisp), mit „token“ den Stand holen.
           Antwort: fertig + ergebnis (Eigenschaften der Fläche) oder token + prozent. Speichert nichts – die Oberfläche zeigt
           das Ergebnis als Vorschlag für die Gegenprüfung. Ohne WHISP_API_KEY in .env ist die Abfrage aus (503). */
        case 'containerimport_eudr_whisp': {
            eudr_bearbeiter();
            require_once __DIR__ . '/../module/containerimport/whisp.php';
            if (!whisp_eingerichtet()) fail('Die Abfrage von Whisp ist nicht eingerichtet.', 503);
            $b = body();
            if (session_status() === PHP_SESSION_ACTIVE) session_write_close();   // sonst wartet jede weitere Anfrage der Sitzung, solange Whisp nicht antwortet
            if (isset($b['token'])) respond(['ok' => true] + whisp_stand(is_string($b['token']) ? $b['token'] : ''));
            $liste = eudr_betriebe()['liste'];
            $i = eudr_stelle($liste, is_string($b['id'] ?? null) ? $b['id'] : '');
            if ($i === null) fail('Farmer nicht gefunden.', 404);
            if ($liste[$i]['geometrie']['type'] === 'Point') fail('Whisp braucht einen Umriss – für einen einzelnen Punkt wäre das Ergebnis nicht die Fläche des Farmers.', 422);
            audit('containerimport', 'EUDR: Umriss von „' . $liste[$i]['name'] . '“ zur Prüfung an Whisp gesendet');   // vor dem Versand: auch ein abgelehnter Umriss hat das Haus verlassen
            respond(['ok' => true] + whisp_starten($liste[$i]['geometrie']));
        }

        /* Farmer-Nummern aus den Papieren für das Fenster „Container“ auflösen, ohne zu speichern (Vorschau vor dem Übernehmen):
           je Nummer der bekannte Farmer im Land des Containers oder „neu“. „betriebe“ und „offeneNummern“ = Stand des Fensters
           (auch eines noch nicht gespeicherten Containers). Gespeichert wird mit dem Container (eudr_sendung_pruefen). */
        case 'containerimport_eudr_nummern': {
            eudr_leser(true);
            $b = body();
            $ids = is_array($b['betriebe'] ?? null) ? array_values(array_filter($b['betriebe'], 'is_string')) : [];
            $liste = eudr_betriebe()['liste'];
            respond(['ok' => true, 'zeilen' => ci_nummern_aufloesen(ci_nummern_lesen($b['nummern'] ?? ''), eudr_land($b['land'] ?? ''), $ids, ci_nummern_lesen($b['offeneNummern'] ?? []), $liste, ci_nummern_index($liste))]);
        }

        /* Container anlegen oder ändern. Die Partienummer ist Pflicht und je Container eindeutig. Nach dem Abschluss der
           Bewertung lassen sich noch Stand, Container- und Aktennummer, Sorgfaltserklärung und Notiz ändern – der Container
           reist weiter, die Bewertung selbst bleibt, wie sie abgeschlossen wurde. */
        case 'containerimport_eudr_sendung_save': {
            $me = eudr_bearbeiter();
            $b = body();
            $s = with_lock(EUDR_SPERRE, function () use ($b, $me) {
                $doc = eudr_sendungen();
                $alt = null; $i = null;
                if (($b['id'] ?? '') !== '') {
                    [$i, $alt] = eudr_holen($doc, $b['id']);
                    eudr_rev_pruefen($b, $alt, 'Der Container');
                } elseif (count($doc['liste']) >= EUDR_MAX_SENDUNGEN) fail('Zu viele Container.', 422);
                if ($alt && !empty($alt['abschluss'])) {
                    $neu = eudr_sendung_laufend($b, $alt) + eudr_sendung_nachtrag($b, $alt) + $alt;
                } else {
                    // „+ $alt“ am Ende: Felder, die dieser Stand nicht kennt (nach einem Rückfall von einer neueren Version), bleiben erhalten
                    $neu = ['id' => $alt['id'] ?? eudr_id('s')] + eudr_sendung_pruefen($b, eudr_betriebe()['liste'], $alt)
                        + ['abschluss' => null, 'fruehere' => $alt['fruehere'] ?? [], 'erstellt' => $alt['erstellt'] ?? eudr_wer($me)] + ($alt ?? []);
                }
                if (eudr_partie_vergeben($doc['liste'], $neu['partie'], $i)) fail('Die Partienummer „' . $neu['partie'] . '“ ist schon bei einem anderen Container vergeben (archivierte zählen mit).', 422);
                $neu['rev'] = (int)($alt['rev'] ?? 0) + 1; $neu['geaendert'] = eudr_wer($me);
                if ($i === null) $doc['liste'][] = $neu; else $doc['liste'][$i] = $neu;
                eudr_sendungen_schreiben($doc);
                return $neu;
            });
            audit('containerimport', 'Container „' . eudr_container_name($s) . '“ gespeichert');
            respond(['ok' => true, 'id' => $s['id']] + eudr_stand());
        }

        /* Tracking eines Containers pflegen: Schiff, Reederei, Konnossement, Häfen, Abfahrt, Ankunft, dazu Stand und
           Containernummer. Geht auch nach dem Abschluss der Bewertung und ändert nichts an ihr. */
        case 'containerimport_tracking_save': {
            $me = eudr_bearbeiter();
            $b = body();
            $s = with_lock(EUDR_SPERRE, function () use ($b, $me) {
                $doc = eudr_sendungen();
                [$i, $alt] = eudr_holen($doc, $b['id'] ?? '');
                eudr_rev_pruefen($b, $alt, 'Der Container');
                $doc['liste'][$i] = ['rev' => $alt['rev'] + 1, 'geaendert' => eudr_wer($me)] + ci_reise($b, $alt) + ci_tracking_pruefen($b, $alt) + $alt;
                eudr_sendungen_schreiben($doc);
                return $doc['liste'][$i];
            });
            audit('containerimport', 'Tracking des Containers „' . eudr_container_name($s) . '“ gespeichert');
            respond(['ok' => true, 'id' => $s['id']] + eudr_stand());
        }

        /* Tracking: Liste „Expected vessels“ von Hafen Hamburg auffrischen, wenn ein Container sie braucht und die Frist um
           ist (hafen.php). Ändert keinen Container – auch wer nur ansehen darf, stößt das an (POST wegen CSRF). Läuft im
           Hintergrund der Seite und liefert deshalb nur die Meldungen, nicht den ganzen Stand. */
        case 'containerimport_tracking_hafen': {
            eudr_leser(true);
            if (session_status() === PHP_SESSION_ACTIVE) session_write_close();   // sonst wartet jede weitere Anfrage der Sitzung auf den Abruf
            $geholt = ci_hafen_auffrischen(eudr_sendungen()['liste']);
            respond(['ok' => true, 'geholt' => $geholt, 'hafen' => ci_hafen_sicht(eudr_sendungen()['liste'])]);   // Container nach dem Abruf neu lesen: Er kann lange dauern
        }

        /* Schlachthof anlegen oder ändern (Stammdaten unter dem Lieferanten; archivieren statt löschen) */
        case 'containerimport_schlachthof_save': {
            $me = eudr_bearbeiter();
            $b = body();
            $h = with_lock(EUDR_SPERRE, fn() => ci_schlachthof_speichern($b, $me));
            audit('containerimport', 'Schlachthof „' . $h['name'] . '“ gespeichert');
            respond(['ok' => true, 'id' => $h['id']] + eudr_stand());
        }

        /* Bewertung abschließen (Ergebnis, Begründung, Schnappschuss von Profil und Betrieben) oder wieder öffnen (mit Grund).
           „Vernachlässigbar“ geht nie mit einem kritischen Kriterium, mit offenen Kriterien nur mit Begründung. */
        case 'containerimport_eudr_sendung_abschluss': {
            $me = eudr_bearbeiter();
            $b = body();
            $s = with_lock(EUDR_SPERRE, function () use ($b, $me) {
                $doc = eudr_sendungen();
                [$i, $s] = eudr_holen($doc, $b['id'] ?? '');
                eudr_rev_pruefen($b, $s, 'Der Container');
                if (!empty($b['oeffnen'])) {
                    if (empty($s['abschluss'])) fail('Die Bewertung ist nicht abgeschlossen.', 409);
                    $grund = eudr_text($b['grund'] ?? '', 500, 'Grund', true);
                    $s['fruehere'][] = $s['abschluss'] + ['geoeffnet' => eudr_wer($me), 'grund' => $grund];   // samt Schnappschuss (GR-106)
                    foreach (array_slice(array_keys($s['fruehere']), 0, -EUDR_MAX_FRUEHERE) as $k) unset($s['fruehere'][$k]['betriebe']);   // ältere: Profil bleibt, Umrisse nicht
                    $s['abschluss'] = null;
                } else {
                    if (!empty($s['abschluss'])) fail('Die Bewertung ist bereits abgeschlossen.', 409);
                    $s['abschluss'] = eudr_abschluss($s, $b, array_map('eudr_betrieb_sicht', eudr_betriebe()['liste']), $me);
                    $s['schlachthofName'] = ci_schlachthof_namen()[$s['schlachthof']] ?? $s['schlachthofName'];   // ab jetzt der Name von heute (GR-106)
                }
                $s['rev']++; $s['geaendert'] = eudr_wer($me);
                $doc['liste'][$i] = $s;
                eudr_sendungen_schreiben($doc);
                return $s;
            });
            audit('containerimport', 'EUDR: Bewertung des Containers „' . eudr_container_name($s) . '“ ' . ($s['abschluss'] ? 'abgeschlossen (' . ($s['abschluss']['ergebnis'] === 'vernachlaessigbar' ? 'Risiko vernachlässigbar' : 'Risiko nicht vernachlässigbar') . ')' : 'wieder geöffnet'));
            respond(['ok' => true] + eudr_stand());
        }

        /* GeoJSON-Datei für das EU-Informationssystem: Betriebe einer Sendung (abgeschlossen: der Schnappschuss) oder ein Betrieb */
        case 'containerimport_eudr_export': {
            eudr_leser();
            header('Cache-Control: no-store');
            $betriebe = array_map('eudr_betrieb_sicht', eudr_betriebe()['liste']);
            if (isset($_GET['betrieb'])) {
                $bs = array_values(array_filter($betriebe, fn($x) => $x['id'] === $_GET['betrieb']));
                if (!$bs) fail('Farmer nicht gefunden.', 404);
                $name = $bs[0]['kennung'] !== '' ? $bs[0]['kennung'] : $bs[0]['name'];
            } else {
                [, $s] = eudr_holen(eudr_sendungen(), $_GET['sendung'] ?? '');
                $bs = eudr_sendung_betriebe($s, $betriebe);
                $name = eudr_container_name($s);
            }
            $datei = 'EUDR_' . trim((string)preg_replace('/[^A-Za-z0-9_-]+/', '_', $name), '_') . '.geojson';
            respond(['ok' => true, 'datei' => $datei] + eudr_geojson($bs));
        }

        /* Dokumente je Container (module/containerimport/dokumente.php, GoBD): Dateien eines Containers (GET sendung), auch
           entfernte, und die Vermerke seiner Checkliste. Protokoll ohne Dateinamen und Gründe (wie im QM-System). */
        case 'containerimport_dokumente': {
            eudr_leser();
            header('Cache-Control: no-store');
            [, $s] = eudr_holen(eudr_sendungen(), $_GET['sendung'] ?? '');
            respond(ci_dokumente_antwort(ci_dokumente(), $s['id']));
        }

        /* Datei in Teilen hochladen (sendung, arten und die Felder von ablage_teil). Überschreibt nie – jede Datei bekommt eine neue Kennung. */
        case 'containerimport_dokument_hochladen': {
            $me = eudr_bearbeiter();
            $r = ci_dokument_hochladen($me, body());
            if (!$r['fertig']) respond(['ok' => true, 'fertig' => false, 'upload' => $r['upload'], 'empfangen' => $r['empfangen']]);
            $e = $r['eintrag'];
            audit('containerimport', 'Dokument (' . ci_dok_artnamen($e['arten']) . ', ' . round($e['groesse'] / 1024) . ' KB) am Container „' . eudr_container_name($r['container']) . '“ abgelegt');
            respond(['fertig' => true, 'id' => $e['id']] + ci_dokumente_antwort($r['doc'], $e['sendung']));
        }

        /* Dokumentarten einer Datei ändern – Vermerk im Verlauf, nie stilles Überschreiben */
        case 'containerimport_dokument_arten': {
            $me = eudr_bearbeiter();
            [$f, $doc, $v] = ci_dokument_arten_aendern(body(), $me);
            audit('containerimport', 'Dokument am Container „' . eudr_container_name($f['schnappschuss']) . '“: Arten von ' . ci_dok_artnamen($v['alt']) . ' zu ' . ci_dok_artnamen($v['neu']) . ' geändert');
            respond(ci_dokumente_antwort($doc, $f['sendung']));
        }

        /* Datei als entfernt vermerken (Grund Pflicht) – sie bleibt in der Ablage und abrufbar */
        case 'containerimport_dokument_entfernen': {
            $me = eudr_bearbeiter();
            [$f, $doc] = ci_dokument_entfernen(body(), $me);
            audit('containerimport', 'Dokument (' . ci_dok_artnamen($f['arten']) . ') am Container „' . eudr_container_name($f['schnappschuss']) . '“ als entfernt vermerkt');
            respond(ci_dokumente_antwort($doc, $f['sendung']));
        }

        /* Punkt der Checkliste als „nicht nötig“ vermerken oder wieder als nötig (sendung, art, noetig) */
        case 'containerimport_dokument_checkliste': {
            $me = eudr_bearbeiter();
            [$s, $doc, $v] = ci_dokument_checkliste(body(), $me);
            audit('containerimport', 'Checkliste der Dokumente am Container „' . eudr_container_name($s) . '“: ' . ci_dok_artname($v['art']) . ($v['noetig'] ? ' wieder nötig' : ' nicht nötig'));
            respond(ci_dokumente_antwort($doc, $s['id']));
        }

        /* Eine Datei herunterladen (GET id), auch eine entfernte; die Vorschau der PDF lädt sie ebenso */
        case 'containerimport_dokument': {
            eudr_leser();
            [, $f] = ci_dok_holen(ci_dokumente(), $_GET['id'] ?? '');
            ablage_senden(CI_DOK_BEREICH, $f['id'], $f['name'], $f['mime']);
        }

        /* Alle Dateien eines Containers als ZIP (GET sendung): Ordner je erster Dokumentart, entfernte unter _entfernt, index.csv, checkliste.csv */
        case 'containerimport_dokumente_zip': {
            eudr_leser();
            [, $s] = eudr_holen(eudr_sendungen(), $_GET['sendung'] ?? '');
            $doc = ci_dokumente();
            $dateien = ci_dok_von($doc['liste'], $s['id']);
            audit('containerimport', 'Dokumente des Containers „' . eudr_container_name($s) . '“ als ZIP exportiert (' . count($dateien) . ' Dateien)');
            ablage_zip_senden(ablage_zip_pfad('Dokumente ' . eudr_container_name($s)) . '.zip', ci_dokumente_zip_eintraege($s, $dateien, ci_dok_von($doc['checkliste'], $s['id'])));
        }
}
