<?php
declare(strict_types=1);
/* Aktionen: Listen der Stammdaten – Kundengruppen, VK-Gruppen und Vertreter (Beschreibung: lib/kunden.php).
   Kundengruppen und Vertreter ansehen mit „stammdaten.sehen“ oder „kunden.sehen“, VK-Gruppen mit „stammdaten.sehen“;
   Ändern und CSV-Import mit „stammdaten.bearbeiten“. Kunden verweisen über „gruppe“ und „vertreter“/„vertreter2“,
   Artikel über „vkGruppe“ auf die Nummer.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'kundengruppen':
        case 'vkgruppen':
        case 'vertreter': {
            $me = require_auth();
            $vk = $action === 'vkgruppen';
            if (!may($me, 'stammdaten.sehen') && ($vk || !may($me, 'kunden.sehen'))) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
            header('Cache-Control: no-store');
            $d = gruppen_load($action);
            $out = ['ok' => true, 'rev' => $d['rev'], 'groups' => $d['groups'], 'updatedAt' => $d['updatedAt'], 'updatedBy' => $d['updatedBy']];
            // Anzahl zugeordneter Artikel (VK-Gruppen) bzw. Kunden (nur für Berechtigte) – gruppen_zuordnungen() in module/verwaltung/import.php
            if ($vk) $out['artikel'] = (object)gruppen_zuordnungen($action);
            elseif (may($me, 'kunden.sehen')) $out['kunden'] = (object)gruppen_zuordnungen($action);
            respond($out);
        }

        case 'kundengruppen_save':
        case 'vkgruppen_save':
        case 'vertreter_save': {
            $me = require_perm('stammdaten.bearbeiten', true);
            $b = body();
            // Prüfen, Revision, Speichern und Protokoll: gruppen_speichern() (module/verwaltung/import.php, auch für die Importzentrale)
            respond(['ok' => true] + gruppen_speichern(substr($action, 0, -5), $b['groups'] ?? null, (int)($b['rev'] ?? -1), $me, s($b['quelle'] ?? '', 120) ?? ''));
        }
}
