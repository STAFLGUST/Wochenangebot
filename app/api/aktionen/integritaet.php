<?php
declare(strict_types=1);
/* Aktion: Dateiprüfung (lib/integritaet.php) – nur Administratoren.
   GET  ?action=security_integrity               letzter Lauf + Verlauf (älter als 24 h → einmal am Tag automatisch prüfen)
   POST ?action=security_integrity {run: true}   jetzt prüfen (CSRF, protokolliert)
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

if ($action === 'security_integrity') {
    if ($method === 'POST') {
        $me = require_auth(true, 'admin');
        if ((body()['run'] ?? null) !== true) fail('Ungültige Anfrage.', 422);
        $r = integritaet_lauf(false, $me);
        $c = $r['counts'];
        audit('security', "Dateiprüfung ausgeführt: {$c['critical']} kritisch, {$c['warnings']} Warnungen, {$c['checked']} geprüft");
        respond(['ok' => true] + integritaet_stand(false));
    }
    require_auth(false, 'admin');
    respond(['ok' => true] + integritaet_stand());
}
