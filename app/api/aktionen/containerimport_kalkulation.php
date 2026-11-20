<?php
declare(strict_types=1);
/* Aktionen: Modul Container-Import – Kalkulation je Container (Auftrag des Inhabers 20.11.2026; Rechenkern und Fassungen in
   app/api/module/containerimport/kalkulation.php). Eingebunden am Ende von aktionen/containerimport.php, dessen Helfer
   eudr_leser/eudr_bearbeiter hier gelten.
   Rechte (GR-103): ansehen und rechnen mit containerimport.eudr_sehen, speichern und festschreiben mit
   containerimport.eudr_bearbeiten. Das Ergebnis rechnet immer der Server – vom Browser gesendete Ergebnisse gibt es nicht.
   Fassungen werden nie gelöscht; eine endgültige Fassung ist unveränderlich (GR-106), Änderungen nur als neue Fassung mit Grund. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar
require_once __DIR__ . '/../module/containerimport/kalkulation.php';

/* Container (404) mit dem Schnappschuss, den eine endgültige Fassung festhält */
function ci_kalk_container($id): array
{
    [, $s] = eudr_sendung_holen(eudr_sendungen(), $id);
    return array_intersect_key($s, ['id' => 1, 'partie' => 1, 'akte' => 1, 'container' => 1, 'lieferant' => 1, 'lieferantNr' => 1, 'land' => 1, 'ware' => 1]);
}

switch ($action) {
        /* Reiter Kalkulation: Stand je Container, Sätze mit Quelle, Auswahllisten, eigene Rechte */
        case 'containerimport_kalkulation_start': {
            $me = eudr_leser();
            header('Cache-Control: no-store');
            respond(['ok' => true, 'uebersicht' => ci_kalk_uebersicht(ci_kalk_dokument()), 'saetze' => CI_KALK_SAETZE, 'regime' => CI_KALK_REGIME,
                'kn' => CI_KALK_KN, 'taric' => CI_KALK_TARIC, 'staende' => CI_KALK_STAENDE, 'vorgabe' => CI_KALK_VORGABE_KOPF,
                'rechte' => ['bearbeiten' => may($me, 'containerimport.eudr_bearbeiten')]]);
        }

        /* Kalkulation eines Containers mit allen Fassungen (Entwurf frisch gerechnet, endgültige als Schnappschuss) */
        case 'containerimport_kalkulation_laden': {
            eudr_leser();
            header('Cache-Control: no-store');
            $c = ci_kalk_container($_GET['sendung'] ?? '');
            [, $k] = ci_kalk_holen(ci_kalk_dokument(), $c['id']);
            respond(['ok' => true, 'container' => $c, 'kalkulation' => $k ? ci_kalk_sicht($k) : null]);
        }

        /* Rechnen ohne zu speichern (Vorschau beim Bearbeiten; POST wegen Inhalt) */
        case 'containerimport_kalkulation_rechnen': {
            eudr_leser(true);
            $eingabe = ci_kalkulation_eingabe(is_array(body()['eingabe'] ?? null) ? body()['eingabe'] : []);
            respond(['ok' => true, 'eingabe' => $eingabe, 'ergebnis' => ci_kalkulation_rechnen($eingabe, CI_KALK_SAETZE)]);
        }

        /* Entwurf speichern; ist die letzte Fassung endgültig, entsteht mit Grund eine neue Fassung */
        case 'containerimport_kalkulation_speichern': {
            $me = eudr_bearbeiter();
            $b = body();
            $c = ci_kalk_container($b['sendung'] ?? '');
            $eingabe = ci_kalkulation_eingabe(is_array($b['eingabe'] ?? null) ? $b['eingabe'] : []);
            $grund = eudr_text($b['grund'] ?? '', 500, 'Grund');
            [$k, $art] = with_lock(CI_KALK_DOKUMENT, function () use ($c, $eingabe, $b, $grund, $me) {
                [$doc, $k, $art] = ci_kalk_speichern(ci_kalk_dokument(), $c['id'], $eingabe, (int)($b['rev'] ?? 0), $grund, $me);
                store_write(CI_KALK_DOKUMENT, eudr_fortschreiben($doc));
                return [$k, $art];
            });
            $nr = count($k['fassungen']);
            if ($art !== 'entwurf') audit('containerimport', 'Kalkulation des Containers „' . eudr_container_name($c + ['nummer' => '']) . '“: ' . ($art === 'neu' ? 'angelegt' : "Fassung $nr angelegt (Grund: $grund)"));
            respond(['ok' => true, 'container' => $c, 'kalkulation' => ci_kalk_sicht($k), 'uebersicht' => ci_kalk_uebersicht(ci_kalk_dokument())]);
        }

        /* Letzte Fassung endgültig festschreiben (nur vollständig gerechnet; danach unveränderlich) */
        case 'containerimport_kalkulation_festschreiben': {
            $me = eudr_bearbeiter();
            $b = body();
            $c = ci_kalk_container($b['sendung'] ?? '');
            $k = with_lock(CI_KALK_DOKUMENT, function () use ($c, $b, $me) {
                [$doc, $k] = ci_kalk_festschreiben(ci_kalk_dokument(), $c['id'], (int)($b['rev'] ?? 0), $c, $me);
                store_write(CI_KALK_DOKUMENT, eudr_fortschreiben($doc));
                return $k;
            });
            audit('containerimport', 'Kalkulation des Containers „' . eudr_container_name($c + ['nummer' => '']) . '“: Fassung ' . count($k['fassungen']) . ' endgültig festgeschrieben');
            respond(['ok' => true, 'container' => $c, 'kalkulation' => ci_kalk_sicht($k), 'uebersicht' => ci_kalk_uebersicht(ci_kalk_dokument())]);
        }
}
