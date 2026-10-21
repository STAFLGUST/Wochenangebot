<?php
declare(strict_types=1);
/* Modulübersicht (Plattformkern): GET ?action=module_status – Module, Oberflächen, Entwicklungsstand, Freigabe,
   Betrieb und Zugang aus Sicht des angemeldeten Mitarbeiters (lib/module.php). Nur lesend; Grundlage für das Dashboard. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

if ($action === 'module_status') {
    $me = require_auth();
    respond(['ok' => true, 'module' => modul_uebersicht($me)]);
}
