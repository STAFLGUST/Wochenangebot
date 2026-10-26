<?php
declare(strict_types=1);
/* Aktionen des Moduls Sicherheit (Oberfläche sicherheit.intern, sicherheit.dashboard-stafl.de; docs/plattform/modul-sicherheit.md):
   GET  sicherheit_lage          Lagebild und Notfall-Zustand – Administrator und sicherheit.sehen; sicherheit.notfall: nur Zustand
   GET  sicherheit_ereignisse    Sicherheitsprotokoll (?tage=1|7|30|90, &art=, &q=) – Administrator und sicherheit.sehen
   GET  sicherheit_konten        privilegierte Konten – nur Administrator
   POST sicherheit_notfall_an    Notfallmodus auslösen – sicherheit.notfall (Administratoren immer), Bestätigungswort, Bestätigung
   POST sicherheit_notfall_aus   Notfallmodus beenden – nur Administrator, immer mit Bestätigung
   Die Daten liefern Funktionen des Plattformkerns (lib/diagnose.php, lib/notfall.php); dieses Modul liest keine Dokumente selbst.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Rechte im Modul für die Oberfläche (Anzeige; geprüft wird je Aktion) */
function sicherheit_rechte(array $u): array
{
    $admin = ($u['role'] ?? '') === 'admin';
    return ['admin' => $admin, 'sehen' => $admin || may($u, 'sicherheit.sehen'), 'notfall' => $admin || may($u, 'sicherheit.notfall'), 'beenden' => $admin];
}

switch ($action) {
    case 'sicherheit_lage': {
        $me = require_auth(false);
        $r = sicherheit_rechte($me);
        if (!$r['sehen'] && !$r['notfall']) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
        header('Cache-Control: no-store');
        $out = ['ok' => true, 'rechte' => $r, 'notfall' => notfall_anzeige($me), 'wirkungen' => notfall_wirkungen(),
                'verlauf' => $r['sehen'] ? notfall_verlauf() : [], 'ich' => ['name' => (string)$me['name'], 'ip' => client_ip()],
                'zeit' => now()];
        if ($r['sehen']) $out['lage'] = sec_lagebild($me);
        respond($out);
    }

    case 'sicherheit_ereignisse': {
        $me = require_auth(false);
        if (!sicherheit_rechte($me)['sehen']) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
        header('Cache-Control: no-store');
        $tage = (int)($_GET['tage'] ?? 7);
        if (!in_array($tage, [1, 7, 30, 90], true)) fail('Ungültiger Zeitraum.', 422);
        $art = (string)($_GET['art'] ?? '');
        if ($art !== '' && !isset(SEC_EREIGNIS_ARTEN[$art])) fail('Unbekannte Art.', 422);
        respond(['ok' => true] + sec_ereignisse($tage, $art, mb_substr((string)($_GET['q'] ?? ''), 0, 80)));
    }

    case 'sicherheit_konten': {
        require_auth(false, 'admin');
        header('Cache-Control: no-store');
        respond(['ok' => true] + sec_konten());
    }

    case 'sicherheit_notfall_an': {
        // Recht und Bestätigung („notfall_ausloesen“, abschaltbar): Keycloak-Host → erneute Anmeldung, sonst Passwort
        $me = require_perm_confirmed('sicherheit.notfall', 'notfall_ausloesen');
        $n = notfall_ausloesen($me, body());
        respond(['ok' => true, 'notfall' => $n, 'wirkungen' => notfall_wirkungen()]);
    }

    case 'sicherheit_notfall_aus': {
        $me = require_admin_confirmation('notfall_beenden');
        $r = notfall_beenden($me, body());
        respond(['ok' => true, 'notfall' => null, 'ende' => $r, 'verlauf' => notfall_verlauf()]);
    }
}
