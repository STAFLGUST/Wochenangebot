<?php
declare(strict_types=1);
/* Aktionen des Moduls Sicherheit (Oberfläche sicherheit.intern, sicherheit.dashboard-stafl.de; docs/plattform/modul-sicherheit.md):
   GET  sicherheit_lage          Lagebild und Notfall-Zustand – Administrator und sicherheit.sehen; sicherheit.notfall: nur Zustand
   GET  sicherheit_ereignisse    Sicherheitsprotokoll (?tage=1|7|30|90, &art=, &q=) – Administrator und sicherheit.sehen
   GET  sicherheit_konten        privilegierte Konten – nur Administrator
   POST sicherheit_notfall_an    Notfallmodus auslösen – sicherheit.notfall (Administratoren immer), Bestätigungswort, Bestätigung
   POST sicherheit_notfall_aus   Notfallmodus beenden – nur Administrator, immer mit Bestätigung
   POST sicherheit_probealarm    Probealarm (Übung ohne Wirkung) – wie Auslösen: sicherheit.notfall bzw. Administrator
   POST sicherheit_probe_gesehen „Probealarm gesehen“ – alle mit Zugang zum Modul (sehen, notfall, Administrator)
   POST sicherheit_leitfaden     Leitfaden für den Ernstfall speichern – nur Administrator
   POST sicherheit_leitfaden_haken  Schritt im laufenden Notfall abhaken – sicherheit.notfall bzw. Administrator
   GET  sicherheit_bericht       Wochenbericht ansehen (Inhalt wie die E-Mail) – Administrator und sicherheit.sehen
   POST sicherheit_bericht_senden   Wochenbericht jetzt senden – nur Administrator
   POST sicherheit_bericht_einstellen  Wochenbericht an/aus, Wochentag – nur Administrator
   POST sicherheit_konto_deaktivieren  ungenutzten Zugang deaktivieren – nur Administrator mit Bestätigung (wie Verwaltung)
   Die Daten liefern Funktionen des Plattformkerns (lib/diagnose.php, lib/notfall.php, lib/bereitschaft.php, lib/nutzer.php);
   dieses Modul liest keine Dokumente selbst.
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
        $n = notfall();
        $verlauf = $r['sehen'] ? array_map(function ($v) { return $v + ['haken' => leitfaden_haken_fuer((string)($v['seit'] ?? ''))]; }, notfall_verlauf()) : [];
        $out = ['ok' => true, 'rechte' => $r, 'notfall' => notfall_anzeige($me), 'wirkungen' => notfall_wirkungen(),
                'verlauf' => $verlauf, 'ich' => ['name' => (string)$me['name'], 'ip' => client_ip()],
                // Bereitschaft (lib/bereitschaft.php): Leitfaden mit Ansprechpartnern, im Notfall abgehakte Schritte, Übungen
                'leitfaden' => leitfaden() + ['haken' => $n ? leitfaden_haken_fuer((string)($n['seit'] ?? '')) : []],
                'proben' => $r['sehen'] || $r['notfall'] ? array_slice(bereit_proben(), 0, 10) : [], 'probeOffen' => probe_offen($me),
                'zeit' => now()];
        if ($r['sehen']) $out['lage'] = sec_lagebild($me);
        if ($r['sehen']) $out['bericht'] = bericht_anzeige();
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
        $tage = (int)($_GET['tage'] ?? SEC_UNGENUTZT_TAGE);
        if (!in_array($tage, SEC_UNGENUTZT_WAHL, true)) fail('Ungültiger Zeitraum.', 422);
        respond(['ok' => true] + sec_konten() + ['ungenutzt' => sec_ungenutzt($tage)]);
    }

    case 'sicherheit_konto_deaktivieren': {
        // wie „aktiv“ abwählen in Verwaltung → Mitarbeiter: Administrator mit derselben Bestätigung (Schlüssel user_save)
        $me = require_admin_confirmation('user_save');
        $u = nutzer_deaktivieren($me, (string)(body()['id'] ?? ''), 'Sicherheit: ungenutzter Zugang');
        respond(['ok' => true, 'user' => ['id' => $u['id'], 'username' => $u['username'], 'active' => false]]);
    }

    case 'sicherheit_probealarm': {
        $me = require_perm('sicherheit.notfall', true);
        respond(['ok' => true, 'probe' => probe_ausloesen($me), 'proben' => array_slice(bereit_proben(), 0, 10)]);
    }

    case 'sicherheit_probe_gesehen': {
        $me = require_auth(true);
        $r = sicherheit_rechte($me);
        if (!$r['sehen'] && !$r['notfall']) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
        respond(['ok' => true, 'probe' => probe_quittieren($me, (string)(body()['id'] ?? ''))]);
    }

    case 'sicherheit_leitfaden': {
        $me = require_auth(true, 'admin');
        respond(['ok' => true, 'leitfaden' => leitfaden_speichern($me, body())]);
    }

    case 'sicherheit_leitfaden_haken': {
        $me = require_perm('sicherheit.notfall', true);
        respond(['ok' => true, 'haken' => leitfaden_haken($me, body())]);
    }

    case 'sicherheit_bericht': {
        $me = require_auth(false);
        if (!sicherheit_rechte($me)['sehen']) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
        header('Cache-Control: no-store');
        respond(['ok' => true, 'bericht' => bericht_daten(), 'einstellungen' => bericht_anzeige()]);
    }

    case 'sicherheit_bericht_senden': {
        $me = require_auth(true, 'admin');
        $e = bericht_senden($me, false);
        respond(['ok' => true, 'versand' => $e, 'einstellungen' => bericht_anzeige()]);
    }

    case 'sicherheit_bericht_einstellen': {
        $me = require_auth(true, 'admin');
        respond(['ok' => true, 'einstellungen' => bericht_speichern($me, body())]);
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
