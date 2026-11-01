<?php
declare(strict_types=1);
/* Aktionen: Controlling (Oberfläche controlling.intern, Fachlogik in app/api/module/controlling/)
   Rechte (GR-103): controlling.zugang – Modul öffnen (Register, standardmäßig niemand);
                    controlling.umsatz_sehen – Umsatzstatistik (Monatsmeldung und Auswertung) ansehen; controlling.umsatz_ek – Einkaufswerte und Deckungsbeitrag der Auswertung (nur zusammen mit bestand.einkaufspreise, GR-008); controlling.umsatz_importieren –
                    Umsatzdaten über die Importzentrale (Verwaltung → Import, module/controlling/import.php).
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

        /* Umsatzstatistik, Monatsmeldung: Kg, Umsatz, DB je Vertreter und Monat eines Jahres (?jahr=JJJJ) aus den Umsatzdaten */
        case 'controlling_umsatz': {
            $me = require_perm('controlling.umsatz_sehen');
            header('Cache-Control: no-store');
            respond(controlling_umsatz_antwort($me, $_GET['jahr'] ?? null));
        }

        /* Umsatzauswertung: Stand der importierten Daten, Rechte, Auswahllisten (Vertreter, Gruppen, Kunden, Artikel) */
        case 'controlling_umsatz_daten': {
            $me = require_perm('controlling.umsatz_sehen');
            header('Cache-Control: no-store');
            respond(umsatz_grunddaten($me));
        }

        /* Umsatzauswertung: ?von=JJJJ-MM&bis=JJJJ-MM&nach=…&vj=1 und Filter v, kg, k, ag, fa, a (kommagetrennt, „_“ = ohne) */
        case 'controlling_umsatz_auswertung': {
            $me = require_perm('controlling.umsatz_sehen');
            header('Cache-Control: no-store');
            respond(umsatz_auswertung($_GET, $me));
        }
}
