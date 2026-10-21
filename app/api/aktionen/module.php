<?php
declare(strict_types=1);
/* Modulübersicht (Plattformkern): GET ?action=module_status – Module, Oberflächen, Entwicklungsstand, Freigabe,
   Betrieb und Zugang aus Sicht des angemeldeten Mitarbeiters (lib/module.php). Nur lesend; Grundlage für das Dashboard. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

if ($action === 'module_status') {
    $me = require_auth();
    $out = ['ok' => true, 'module' => modul_uebersicht($me)];
    if ($me['role'] === 'admin') $out['verlauf'] = array_slice(modul_laufzeit()['verlauf'], 0, 30);
    respond($out);
}

/* POST ?action=modul_wartung_save {bereich: "<modul>.<oberfläche>", active, grund, message, until, ab}
   Nur Administratoren, immer mit Passwortbestätigung; protokolliert (Protokoll und Verlauf im Dokument „module“). */
if ($action === 'modul_wartung_save') {
    $me = require_admin_confirmation('modul_wartung_save');
    $b = body();
    $ziel = (string)($b['bereich'] ?? '');
    $w = modul_wartung_setzen($ziel, $b, $me);
    [$m, $o] = array_pad(explode('.', $ziel, 2), 2, '');
    respond(['ok' => true, 'bereich' => $ziel, 'wartung' => modul_wartung_anzeige($m, $o, $me), 'zustand' => modul_zustand($m, $o, $me), 'aktiv' => $w !== null]);
}

/* POST ?action=modul_freigabe_save {bereich, freigabe: keine|test|produktiv|deaktiviert, grund}
   Nur Administratoren, immer mit Bestätigung; nur Werte, die der Entwicklungsstand im Code zulässt (lib/module.php). */
if ($action === 'modul_freigabe_save') {
    $me = require_admin_confirmation('modul_freigabe_save');
    $b = body();
    $ziel = (string)($b['bereich'] ?? '');
    $r = modul_freigabe_setzen($ziel, $b, $me);
    [$m, $o] = array_pad(explode('.', $ziel, 2), 2, '');
    respond(['ok' => true, 'bereich' => $ziel, 'freigabe' => $r, 'zustand' => modul_zustand($m, $o, $me)]);
}

/* POST ?action=modul_tester_save {bereich, tester: [Nutzer-IDs], grund} – wer eine Testfreigabe nutzen darf */
if ($action === 'modul_tester_save') {
    $me = require_admin_confirmation('modul_tester_save');
    $b = body();
    $ziel = (string)($b['bereich'] ?? '');
    $ids = modul_tester_setzen($ziel, $b, $me);
    [$m, $o] = array_pad(explode('.', $ziel, 2), 2, '');
    respond(['ok' => true, 'bereich' => $ziel, 'tester' => $ids, 'zustand' => modul_zustand($m, $o, $me)]);
}
