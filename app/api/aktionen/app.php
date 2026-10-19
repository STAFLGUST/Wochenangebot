<?php
declare(strict_types=1);
/* Aktionen: Grunddaten für die App (iOS/Android, Ordner mobile/). Beschreibung: docs/app-api.md
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Älteste App-Version, die noch mit dieser Schnittstelle arbeiten darf. Ältere Apps zeigen „Bitte aktualisieren“.
   Nur erhöhen, wenn die Schnittstelle unverträglich geändert wurde (Release wie jede andere Änderung). */
const APP_MIN_VERSION = '1.0.0';
const APP_API_VERSION = 1;

switch ($action) {
        case 'app_info': {
            header('Cache-Control: no-store');
            $W = wartung();
            respond(['ok' => true, 'apiVersion' => APP_API_VERSION, 'minAppVersion' => APP_MIN_VERSION, 'company' => $CFG['company'],
                     'stdPublic' => std_public(), 'bestellfunktion' => order_enabled(), 'testumgebung' => testumgebung(),
                     'wartung' => $W ? ['message' => $W['message'], 'until' => $W['until']] : null,
                     'links' => ['kontakt' => '/kontakt/', 'impressum' => '/impressum/', 'datenschutz' => '/datenschutz/']]);
        }
}
