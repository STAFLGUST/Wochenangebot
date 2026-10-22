<?php
declare(strict_types=1);
/* Aktionen: Importzentrale (Verwaltung → Import; Ablauf und Prüfungen: module/verwaltung/importzentrale.php)
   GET  import_arten        Importarten, für die der angemeldete Nutzer das Recht hat (Anzeige ist keine Berechtigung)
   POST import_pruefen      Vorschau: { art, daten, quelle, optionen } → Zahlen, Zeilen, Hinweise, stand
   POST import_uebernehmen  Übernahme: wie Vorschau plus stand aus der Vorschau; Protokoll schreibt der Eigentümer
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'import_arten': {
            $me = require_auth();
            header('Cache-Control: no-store');
            $out = [];
            foreach (import_registry() as $id => $a) if (import_darf($me, $a)) $out[] = import_art_anzeige($id, $a, $me);
            respond(['ok' => true, 'arten' => $out, 'zeilenMax' => IMPORT_ZEILEN_MAX]);
        }

        case 'import_pruefen':
        case 'import_uebernehmen': {
            respond(['ok' => true] + import_ausfuehren($action === 'import_uebernehmen'));
        }
}
