<?php
declare(strict_types=1);
/* Aktionen: Listen der Stammdaten – Kundengruppen, VK-Gruppen, Vertreter, Versandarten, Lieferanten, Abteilungen
   (Beschreibung: lib/kunden.php) und Angebotskategorien (module/verwaltung/angebotskategorien.php).
   Kundengruppen, Vertreter und Versandarten ansehen mit „stammdaten.sehen“ oder „kunden.sehen“, VK-Gruppen, Lieferanten
   und Abteilungen mit „stammdaten.sehen“ (Umsätze der Lieferanten nur mit „stammdaten.bearbeiten“); Ändern und CSV-Import
   mit „stammdaten.bearbeiten“. Kunden verweisen über „gruppe“, „vertreter“/„vertreter2“ und „versandart“, Artikel über
   „vkGruppe“, Lieferanten über „versandart“, die HR-Angaben der Mitarbeiter über „abteilungNr“ auf die Nummer.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        /* Angebotskategorien (module/verwaltung/angebotskategorien.php): Abschnitte des Angebots mit zugeordneten VK-Gruppen.
           Lesen auch mit „angebot.bearbeiten“ (der Editor ordnet das Angebot danach), ändern mit „stammdaten.bearbeiten“. */
        case 'angebotskategorien': {
            $me = require_auth();
            if (!may($me, 'stammdaten.sehen') && !may($me, 'angebot.bearbeiten')) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
            require_once dirname(__DIR__) . '/module/verwaltung/angebotskategorien.php';
            header('Cache-Control: no-store');
            respond(['ok' => true] + kategorien_load() + ['vk' => kategorien_vk_namen()]);
        }

        case 'angebotskategorien_save': {
            $me = require_perm('stammdaten.bearbeiten', true);
            require_once dirname(__DIR__) . '/module/verwaltung/angebotskategorien.php';
            $b = body();
            respond(['ok' => true] + kategorien_speichern($b['kategorien'] ?? null, (int)($b['rev'] ?? -1), $me));
        }

        case 'kundengruppen':
        case 'vkgruppen':
        case 'vertreter':
        case 'versandarten':
        case 'lieferanten':
        case 'abteilungen': {
            $me = require_auth();
            $nurStamm = in_array($action, ['vkgruppen', 'lieferanten', 'abteilungen'], true);
            if (!may($me, 'stammdaten.sehen') && ($nurStamm || !may($me, 'kunden.sehen'))) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
            header('Cache-Control: no-store');
            $d = gruppen_load($action);
            $groups = $d['groups'];
            // Umsätze der Lieferanten (Einkaufsvolumen) nur für Bearbeiter der Stammdaten
            if ($action === 'lieferanten' && !may($me, 'stammdaten.bearbeiten'))
                $groups = array_map(function ($g) { return is_array($g) ? array_diff_key($g, array_flip(LIEFERANTEN_UMSATZ)) : $g; }, $groups);
            $out = ['ok' => true, 'rev' => $d['rev'], 'groups' => $groups, 'updatedAt' => $d['updatedAt'], 'updatedBy' => $d['updatedBy']];
            // Anzahl zugeordneter Artikel (VK-Gruppen) bzw. Kunden (nur für Berechtigte) – gruppen_zuordnungen() in module/verwaltung/import.php
            if ($action === 'vkgruppen') $out['artikel'] = (object)gruppen_zuordnungen($action);
            elseif ($action === 'versandarten') { if (may($me, 'kunden.sehen')) $out['zuordnung'] = (object)gruppen_zuordnungen($action); }
            elseif ($action !== 'lieferanten' && $action !== 'abteilungen' && may($me, 'kunden.sehen')) $out['kunden'] = (object)gruppen_zuordnungen($action);
            respond($out);
        }

        case 'kundengruppen_save':
        case 'vkgruppen_save':
        case 'vertreter_save':
        case 'versandarten_save':
        case 'lieferanten_save':
        case 'abteilungen_save': {
            $me = require_perm('stammdaten.bearbeiten', true);
            $b = body();
            // Prüfen, Revision, Speichern und Protokoll: gruppen_speichern() (module/verwaltung/import.php, auch für die Importzentrale)
            respond(['ok' => true] + gruppen_speichern(substr($action, 0, -5), $b['groups'] ?? null, (int)($b['rev'] ?? -1), $me, s($b['quelle'] ?? '', 120) ?? ''));
        }
}
