<?php
declare(strict_types=1);
/* Aktionen: Einzelangebote (Angebot bearbeiten → Einzelangebote). Beschreibung und Logik: lib/einzelangebote.php (dieselben
   Funktionen nutzt das CRM im Kunden-Pop-up, Aktionen crm_einzel_*)
   Rechte: einzelangebote.sehen (setzt kunden.sehen voraus), einzelangebote.bearbeiten; E-Mail an den Kunden mit Passwortbestätigung.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'einzel_liste': {
            require_perm('einzelangebote.sehen');
            header('Cache-Control: no-store');
            respond(['ok' => true, 'list' => einzel_liste()]);
        }

        case 'einzel_detail': {
            require_perm('einzelangebote.sehen');
            header('Cache-Control: no-store');
            $e = einzel_holen((string)($_GET['id'] ?? ''));
            if ($e === null) fail('Einzelangebot nicht gefunden.', 404);
            respond(['ok' => true, 'angebot' => einzel_view($e, einzel_kunden_map()), 'fracht' => fracht_hinweis()]);
        }

        case 'einzel_pdf': {   // PDF im Design der Angebotsansicht (Vorschau des E-Mail-Anhangs)
            require_perm('einzelangebote.sehen');
            $e = einzel_holen((string)($_GET['id'] ?? ''));
            if ($e === null) fail('Einzelangebot nicht gefunden.', 404);
            einzel_pdf_senden($e);
        }

        case 'einzel_artikel': {
            $me = require_perm('einzelangebote.bearbeiten');
            header('Cache-Control: no-store');
            respond(['ok' => true] + einzel_artikel(may($me, 'bestand.sehen'), may($me, 'bestand.einkaufspreise')));
        }

        case 'einzel_save': {
            $me = require_perm('einzelangebote.bearbeiten', true);
            respond(['ok' => true, 'angebot' => einzel_speichern(body(), $me)]);
        }

        case 'einzel_status': {
            $me = require_perm('einzelangebote.bearbeiten', true);
            respond(['ok' => true, 'angebot' => einzel_status_setzen(body(), $me)]);
        }

        case 'einzel_loeschen': {
            require_perm('einzelangebote.bearbeiten', true);
            einzel_entfernen((string)(body()['id'] ?? ''));
            respond(['ok' => true]);
        }

        case 'einzel_senden': {
            $me = require_perm_confirmed('einzelangebote.bearbeiten', 'einzel_senden');
            $cfg = require_mail();
            respond(['ok' => true, 'angebot' => einzel_mail(body(), $me, $cfg)]);
        }
}
