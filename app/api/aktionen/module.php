<?php
declare(strict_types=1);
/* Modulübersicht (Plattformkern): GET ?action=module_status – Module, Oberflächen, Entwicklungsstand, Freigabe,
   Betrieb und Zugang aus Sicht des angemeldeten Mitarbeiters (lib/module.php). Nur lesend; Grundlage für das Dashboard.
   Dazu die Startseite des Dashboards (start_heute, start_favoriten_save – lib/startseite.php) und die Modulverwaltung. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

if ($action === 'module_status') {
    $me = require_auth();
    $out = ['ok' => true, 'module' => modul_uebersicht($me), 'notfall' => notfall_anzeige($me)];   // Notfallmodus: Hinweis im Dashboard
    if ($me['role'] === 'admin') $out['verlauf'] = array_slice(modul_laufzeit()['verlauf'], 0, 30);
    respond($out);
}

/* Startseite des Dashboards (Modul „dashboard“, nur auf dem Dashboard-Host, GR-109): GET ?action=start_heute – offene Punkte
   „Heute für Sie“ aus den Modulen mit nutzbarer Kachel, Zahlen je Modul (Seitenleiste), Schnellaktionen, eigene letzte
   Änderungen und Favoriten (lib/startseite.php). Nur lesend; jedes Modul prüft seine Rechte selbst (GR-103). */
if ($action === 'start_heute') {
    $me = require_auth();
    require_once __DIR__ . '/../lib/startseite.php';
    respond(['ok' => true] + startseite_heute($me));
}

/* POST ?action=start_favoriten_save {favoriten: [Modul-IDs] | null} – Favoriten der Startseite am eigenen Konto (neues
   optionales Feld „favoriten“; leere Liste = bewusst keine, null = Standard). Nur der eigene Datensatz, kein Protokoll nötig
   (wie theme_save). */
if ($action === 'start_favoriten_save') {
    $me = require_auth(true);
    require_once __DIR__ . '/../lib/startseite.php';
    $b = body();
    if (!array_key_exists('favoriten', $b)) fail('Keine Favoriten übermittelt.', 422);
    $fav = startseite_favoriten_pruefen($b['favoriten']);
    with_lock('nutzer', function () use ($me, $fav) {
        $users = users_load();
        $i = user_find($users, $me['id']);
        if ($i === null) fail('Bitte erneut anmelden.', 401);
        if (($users[$i]['favoriten'] ?? null) === $fav) return;
        if ($fav === null) unset($users[$i]['favoriten']); else $users[$i]['favoriten'] = $fav;
        users_save($users);
    });
    respond(['ok' => true, 'favoriten' => $fav]);
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
