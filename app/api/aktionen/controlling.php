<?php
declare(strict_types=1);
/* Aktionen: Controlling (Oberfläche controlling.intern, Fachlogik in app/api/module/controlling/)
   Rechte (GR-103): controlling.zugang – Modul öffnen (Register, standardmäßig niemand);
                    controlling.umsatz_sehen – Umsatzstatistik (Monatsmeldung und Auswertung) ansehen; controlling.umsatz_ek – Einkaufswerte und Deckungsbeitrag der Auswertung (nur zusammen mit bestand.einkaufspreise, GR-008); controlling.umsatz_importieren –
                    Umsatzdaten über die Importzentrale (Verwaltung → Import, module/controlling/import.php);
                    controlling.bestand_sehen – Bestandsverlauf; controlling.bestand_ek – dessen Lagerwert (nur mit bestand.einkaufspreise);
                    controlling.arbeitszeit_sehen – Arbeitszeit aus dem Zeitbericht (Personaldaten); controlling.arbeitszeit_importieren – Import.
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

        /* Pop-up der Umsatzstatistik: ?dim=vertreter|kundengruppe|kunde|vkgruppe|fleischart|artikel&wert=… mit Zeitraum, Vorjahr und
           den Filtern der Seite – Kennzahlen, Monate, Kunden und Artikel mit letztem Kauf, beim Kunden die Liefertage */
        case 'controlling_umsatz_detail': {
            $me = require_perm('controlling.umsatz_sehen');
            header('Cache-Control: no-store');
            respond(umsatz_detail($_GET, $me));
        }
        case 'controlling_umsatz_pausen': {
            require_perm('controlling.umsatz_sehen');
            header('Cache-Control: no-store');
            respond(umsatz_pausen($_GET));
        }

        /* Bestandsverlauf (module/controlling/bestand.php): Grunddaten (Stand, Rechte, Auswahllisten), Auswertung
           (?tage=30|90|365 oder von/bis, nach=artikel|vkgruppe|fleischart, Filter ag, fa, a) und Detail (?dim=…&wert=…) –
           Lagerwert nur mit controlling.bestand_ek und bestand.einkaufspreise (GR-008) */
        case 'controlling_bestand_daten': {
            $me = require_perm('controlling.bestand_sehen');
            header('Cache-Control: no-store');
            respond(ctl_bestand_grunddaten($me));
        }
        case 'controlling_bestand': {
            $me = require_perm('controlling.bestand_sehen');
            header('Cache-Control: no-store');
            respond(ctl_bestand_auswertung($_GET, $me));
        }
        case 'controlling_bestand_detail': {
            $me = require_perm('controlling.bestand_sehen');
            header('Cache-Control: no-store');
            respond(ctl_bestand_detail($_GET, $me));
        }

        /* Arbeitszeit (module/controlling/arbeitszeit.php): Grunddaten (Stand, Abteilungen, Mitarbeiter), Auswertung
           (?von=JJJJ-MM&bis=JJJJ-MM, Filter abt, p) und Tage eines Mitarbeiters (?p=…) – Personaldaten, eigenes Recht */
        case 'controlling_arbeitszeit_daten': {
            $me = require_perm('controlling.arbeitszeit_sehen');
            header('Cache-Control: no-store');
            respond(az_grunddaten($me));
        }
        case 'controlling_arbeitszeit': {
            $me = require_perm('controlling.arbeitszeit_sehen');
            header('Cache-Control: no-store');
            respond(az_auswertung($_GET, $me));
        }
        case 'controlling_arbeitszeit_detail': {
            $me = require_perm('controlling.arbeitszeit_sehen');
            header('Cache-Control: no-store');
            respond(az_detail($_GET, $me));
        }
}
