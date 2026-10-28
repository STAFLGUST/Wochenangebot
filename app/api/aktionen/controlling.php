<?php
declare(strict_types=1);
/* Aktionen: Controlling (Oberfläche controlling.intern, Fachlogik in app/api/module/controlling/)
   Rechte (GR-103): controlling.zugang – Modul öffnen (Register, standardmäßig niemand);
                    controlling.umsatz_sehen – Umsatzstatistik ansehen; controlling.umsatz_bearbeiten – Monatswerte erfassen.
   Neue Bereiche (OP-Konten, Liquidität …) bekommen eigene Aktionen controlling_<bereich>_… mit eigenen Rechten.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        /* Start: Bereiche, die dieser Mitarbeiter sehen darf (ohne Fachdaten) */
        case 'controlling_start': {
            $me = require_modulzugang('controlling');
            header('Cache-Control: no-store');
            respond(['ok' => true, 'bereiche' => controlling_bereiche($me)]);
        }

        /* Umsatzstatistik: alle Monatswerte, Vertreter (aktuelle und ausgeschiedene mit Werten) */
        case 'controlling_umsatz': {
            $me = require_perm('controlling.umsatz_sehen');
            header('Cache-Control: no-store');
            respond(controlling_umsatz_antwort($me));
        }

        /* Monatswerte speichern: nur mitgeschickte (aktuelle) Vertreter ändern sich, die übrigen Werte des Monats bleiben */
        case 'controlling_umsatz_monat_save': {
            $me = require_perm('controlling.umsatz_bearbeiten', true);
            $b = body();
            $e = controlling_umsatz_eingabe($b);
            with_lock('controlling-umsatz', function () use ($b, $e, $me) {
                $d = controlling_umsatz_doc();
                if ((int)($b['rev'] ?? -1) !== $d['rev']) fail('Die Umsatzstatistik wurde inzwischen geändert. Bitte neu laden.', 409);
                $monat = is_array($d['jahre'][$e['jahr']][$e['monat']] ?? null) ? $d['jahre'][$e['jahr']][$e['monat']] : [];
                foreach ($e['werte'] as $nr => $w) {
                    if ($w['kg'] === null && $w['umsatz'] === null && $w['db'] === null) unset($monat[$nr]);
                    else $monat[$nr] = $w;
                    $d['vertreter'][$nr] = $e['stamm'][$nr];   // Schnappschuss des Namens (GR-106)
                }
                if ($monat) {
                    ksort($monat, SORT_NATURAL);
                    $d['jahre'][$e['jahr']][$e['monat']] = $monat;
                    ksort($d['jahre'][$e['jahr']], SORT_STRING);   // „10“–„12“ sind in PHP Zahlenschlüssel
                } else {
                    unset($d['jahre'][$e['jahr']][$e['monat']]);
                    if (empty($d['jahre'][$e['jahr']])) unset($d['jahre'][$e['jahr']]);
                }
                $d['rev']++;
                $d['geaendert'] = ['t' => now(), 'von' => $me['id'], 'vonName' => $me['name']];
                store_write('controlling-umsatz', $d);
            });
            audit('controlling', 'Umsatzstatistik: Monatswerte ' . CONTROLLING_MONATE[$e['monat']] . ' ' . $e['jahr'] . ' gespeichert');   // ohne Beträge
            respond(controlling_umsatz_antwort($me));
        }
}
