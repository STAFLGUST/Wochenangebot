<?php
declare(strict_types=1);
/* Aktionen: Status, Wartungsmodus, Anmeldung, Zwei-Faktor, Passwort
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'status': {
            header('Cache-Control: no-store');
            $u = current_user();
            $noUsers = !users_load();
            respond(['ok' => true, 'setupRequired' => $noUsers && setup_allowed(), 'setupLocked' => $noUsers && !setup_allowed(), 'loggedIn' => (bool)$u, 'csrf' => $u ? $_SESSION['csrf'] : null,
                     'user' => $u ? me_payload($u) : null, 'company' => $CFG['company'], 'wartung' => $u ? wartung() : null, 'testumgebung' => testumgebung(),
                     // Wartung des Eingabebereichs (lib/module.php): Hinweis für Administratoren, Sperrbildschirm für alle anderen
                     'wartungEingabe' => $u ? modul_wartung_anzeige('angebot', 'eingabe', $u) : null,
                     'eingabeGesperrt' => $u ? !modul_zustand('angebot', 'eingabe', $u)['zugang'] : false,
                     // alter Eingabebereich stillgelegt (lib/oidc.php): neue Adresse für Hinweis und Weiterleitung
                     'umgezogen' => eigene_anmeldung_stillgelegt() ? eingabe_adresse() : null]);
        }

        case 'wartung_save': {
            $me = require_admin_confirmation('wartung_save');
            $b = body();
            $on = !empty($b['active']);
            $msg = mb_substr(trim(str_replace("\r", '', preg_replace('/[\x00-\x08\x0b-\x1f]/u', '', (string)($b['message'] ?? '')) ?? '')), 0, 500);
            $until = (string)($b['until'] ?? '');
            if ($until !== '' && !preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/', $until)) fail('Bitte eine gültige Uhrzeit für das voraussichtliche Ende angeben.', 422);
            $old = wartung();
            $new = ['active' => $on, 'message' => $msg, 'until' => $until !== '' ? $until : null, 'since' => $on ? ($old['since'] ?? now()) : null, 'by' => $me['name'], 'changed' => now()];
            store_write('wartung', $new);
            if ((bool)$old !== $on) modul_verlauf_eintragen(['t' => now(), 'wer' => $me['name'], 'bereich' => 'angebot.kunden', 'alt' => $old ? 'wartung' : 'normal',
                                                             'neu' => $on ? 'wartung' : 'normal', 'grund' => '', 'ab' => null, 'bis' => $on ? $new['until'] : null]);
            if ((bool)$old !== $on) audit('wartung', $on ? 'Wartungsmodus eingeschaltet – Angebotsseite für Kunden pausiert' : 'Wartungsmodus ausgeschaltet – Angebotsseite wieder erreichbar',
                [['k' => 'wartung', 'code' => '', 'name' => 'Wartungsmodus', 'f' => 'Status', 'from' => $old ? 'an' : 'aus', 'to' => $on ? 'an' : 'aus']]);
            elseif ($on) audit('wartung', 'Hinweis zum Wartungsmodus geändert');
            respond(['ok' => true, 'wartung' => wartung()]);
        }

        case 'reauth': {
            $me = require_auth(true);
            // Passwortbestätigung nur für Nutzer, die bestätigungspflichtige Aktionen ausführen dürfen
            if ($me['role'] !== 'admin' && !array_intersect(user_perms($me), ['kunden.bearbeiten', 'wochenangebot.senden', 'sonderposten.senden', 'angebote.loeschen', 'einzelangebote.bearbeiten'])) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
            $u = confirm_password($me, (string)(body()['password'] ?? ''));
            mark_admin_confirmed($u);
            audit('reauth', 'Sensible Verwaltungsaktionen für fünf Minuten bestätigt');
            respond(['ok' => true, 'confirmedUntil' => time() + bestaetigung_sekunden()]);
        }

        case 'setup': {
            $b = body();
            $u = with_lock('nutzer', function () use ($b) {
                if (users_load()) fail('Die Ersteinrichtung ist bereits erfolgt.', 409);
                if (!setup_allowed()) fail('Die Ersteinrichtung im Browser ist auf diesem Server gesperrt. Zugang auf dem Server wiederherstellen (siehe LIESMICH).', 403);
                $name = s($b['name'] ?? '', 80) ?: 'Administrator';
                $uname = clean_username($b['username'] ?? '');
                $u = ['id' => 'u' . bin2hex(random_bytes(6)), 'username' => $uname, 'name' => $name, 'role' => 'admin',
                      'active' => true, 'hash' => password_hash(check_password($b['password'] ?? '', $uname), PASSWORD_DEFAULT), 'mustChange' => false,
                      'sv' => 1, 'created' => now(), 'createdBy' => 'Ersteinrichtung', 'lastLogin' => now()];
                users_save([$u]);
                return $u;
            });
            start_session();
            $tok = sign_in($u);
            audit('setup', 'Ersteinrichtung: Administrator „' . $u['username'] . '“ angelegt');
            respond(['ok' => true, 'csrf' => $tok, 'user' => me_payload($u)]);
        }

        case 'login': {
            start_session();
            attempts_check();
            if (!users_load()) fail(setup_allowed() ? 'Bitte zuerst die Ersteinrichtung durchführen.' : 'Es ist kein Zugang vorhanden oder die Nutzerdaten sind nicht lesbar. Bitte den Zugang auf dem Server wiederherstellen (siehe LIESMICH).', 409);
            $b = body();
            $name = is_string($b['username'] ?? null) ? strtolower(trim($b['username'])) : '';
            $pw = (string)($b['password'] ?? '');
            $S = sec();
            $res = with_lock('nutzer', function () use ($name, $pw, $S) {
                $users = users_load();
                foreach ($users as $i => $u) {
                    if ($u['username'] !== $name) continue;
                    $gesperrt = (int)($u['lockedUntil'] ?? 0) > time();
                    $gi = $gesperrt ? geraet_vertraut($u) : null;   // vertrautes Gerät des Inhabers (lib/geraete.php)
                    if ($gesperrt && $gi === null) {
                        // Gesperrt: richtiges Passwort + zweiter Faktor kommt trotzdem durch (sonst könnte jeder durch Fehlversuche
                        // den Inhaber aussperren). Damit die Antwort nichts verrät, bekommt während der Sperre JEDES Passwort den
                        // Code-Schritt (auch bei Zugängen ohne zweiten Faktor und bei unbekannten Namen, siehe unten); wirksam ist er nur
                        // bei richtigem Passwort, aktivem Zugang mit Authenticator-App und solange von den 3 Code-Versuchen je Sperre
                        // (über alle Anmeldevorgänge, siehe login_2fa) noch welche übrig sind. Hier wird nichts gespeichert.
                        $ok = password_verify($pw, (string)$u['hash']);
                        if ($ok && $u['active'] && !empty($u['totp']) && (int)($u['lockTries'] ?? 0) < 3) return ['ok_locked', $u];
                        return ['locked_code', $u];
                    }
                    if ($gesperrt) {
                        // Gesperrt, aber vertrautes Gerät: normal prüfen; falsche Passwörter zählen nur für dieses Gerät
                        if (!password_verify($pw, (string)$u['hash'])) { geraet_fehlversuch($users[$i], $gi); users_save($users); return ['bad', $users[$i]]; }
                    } elseif (!empty($u['lockTries'])) { unset($users[$i]['lockTries']); $u = $users[$i]; users_save($users); }   // Sperre abgelaufen
                    if (!$gesperrt && !password_verify($pw, (string)$u['hash'])) {
                        $lockedNow = login_failure($users[$i]);
                        users_save($users);
                        return [$lockedNow ? 'lockednow' : 'bad', $users[$i]];
                    }
                    if (!$u['active']) return ['inactive', $u];
                    if (password_needs_rehash((string)$u['hash'], PASSWORD_DEFAULT)) $users[$i]['hash'] = password_hash($pw, PASSWORD_DEFAULT);
                    // Mit zweitem Faktor (Authenticator-App oder Passkey) ist das Passwort allein noch keine erfolgreiche Anmeldung.
                    $x = ['gh' => $gi !== null ? (string)$u['geraete'][$gi]['h'] : '', 'neu' => false];
                    if (!has_second_factor($u)) {
                        $users[$i]['failCount'] = 0;
                        $users[$i]['lockedUntil'] = 0;
                        unset($users[$i]['lockTries']);
                        $users[$i]['lastLogin'] = now();
                        geraet_merken($users[$i], $x['neu']);
                    }
                    users_save($users);
                    return ['ok', $users[$i], $x];
                }
                dummy_verify($pw, array_column($users, 'hash')); // gleiche Laufzeit wie bei vorhandenem Nutzer
                return ['bad', null];
            });
            [$st, $u, $x] = $res + [2 => ['gh' => '', 'neu' => false]];
            if ($st === 'bad' && $u === null && ($until = ghost_lock('u', $name, true, $neu))) {   // unbekannter Name: gleiche Sperre
                $st = $neu ? 'lockednow' : 'locked_code';
                $u = ['lockedUntil' => $until];
            }
            $who = ['username' => mb_substr($name, 0, 40), 'name' => $u['name'] ?? '', 'role' => $u['role'] ?? ''];
            if ($st === 'ok') {
                // Passwort in bekannten Datenlecks? (nur wenn eingeschaltet, einmal je Passwort) → muss sofort geändert werden
                $leak = pw_leak_bei_anmeldung($pw, $u, $merker);
                if ($merker !== null) {
                    $u = user_update($u['id'], function (&$y) use ($merker, $leak, $u) { if (!hash_equals((string)($y['hash'] ?? ''), (string)$u['hash'])) return;   // inzwischen geändert
                        $y['leakGeprueft'] = $merker; if ($leak) { $y['mustChange'] = true; $y['mustChangeGrund'] = 'datenleck'; } }) ?? $u;
                    if ($leak && ($u['mustChangeGrund'] ?? '') === 'datenleck') audit('security', 'Passwort von „' . $u['username'] . '“ in bekannten Datenlecks gefunden – muss bei der Anmeldung geändert werden', [], $who);
                }
            }
            if ($st === 'ok_locked' || $st === 'locked_code') {
                // Während einer Sperre: für jedes Passwort dieselbe Antwort (Code-Schritt mit Hinweis auf die Sperre)
                attempts_record(false);
                audit('login_fail', 'Anmeldung während der Sperre' . ($name !== '' ? ' (Benutzername „' . mb_substr($name, 0, 40) . '“)' : '')
                    . ($st === 'ok_locked' ? ' – Passwort richtig, Code-Schritt' : ''), [], $who);
                anmeldung_angleichen();
                session_regenerate_id(true);
                $_SESSION = ['pend' => $st === 'ok_locked'
                    ? ['uid' => $u['id'], 'sv' => (int)$u['sv'], 't' => time(), 'n' => 0, 'lk' => true, 'bis' => (int)$u['lockedUntil']]
                    : ['uid' => '', 'sv' => 0, 't' => time(), 'n' => 0, 'lk' => true, 'bis' => (int)$u['lockedUntil'], 'fake' => true, 'name' => mb_substr($name, 0, 40)]];
                respond(['ok' => true, 'need2fa' => true, 'methods' => ['totp'], 'gesperrtBis' => (new DateTime('@' . (int)$u['lockedUntil']))->setTimezone(new DateTimeZone('Europe/Berlin'))->format('H:i')]);
            }
            if ($st !== 'ok') {
                attempts_record(false);
                $why = ['inactive' => ' – Zugang deaktiviert', 'locked' => ' – Zugang gesperrt', 'lockednow' => ' – Zugang nach zu vielen Fehlversuchen gesperrt', 'bad' => ''][$st];
                audit('login_fail', 'Anmeldung fehlgeschlagen' . ($name !== '' ? ' (Benutzername „' . mb_substr($name, 0, 40) . '“)' : '') . $why, [], $who);
                anmeldung_angleichen();
                if ($st === 'inactive') fail('Dieser Zugang ist deaktiviert.', 401);
                if ($st === 'locked' || $st === 'lockednow') fail('Dieser Zugang ist wegen zu vieler Fehlversuche bis ' . (new DateTime('@' . (int)$u['lockedUntil']))->setTimezone(new DateTimeZone('Europe/Berlin'))->format('H:i') . ' Uhr gesperrt. Ein Administrator kann ihn vorher entsperren.', 429);
                fail('Benutzername oder Passwort ist nicht korrekt.', 401);
            }
            if (has_second_factor($u)) {
                // Die App kennt nur den Code aus der Authenticator-App (keine Passkeys)
                if (app_client() && empty($u['totp'])) {
                    audit('login_fail', 'Anmeldung in der App nicht möglich – nur Passkey eingerichtet', [], $who);
                    respond(['ok' => false, 'code' => 'app_totp_required', 'error' => 'Für die Anmeldung in der App ist die Authenticator-App nötig. Bitte im Eingabebereich im Browser unter „Zwei-Faktor-Anmeldung“ einrichten.'], 403);
                }
                // zweiter Schritt: Code aus der Authenticator-App oder Passkey (gesperrte Zugänge: siehe oben)
                session_regenerate_id(true);
                $_SESSION = ['pend' => ['uid' => $u['id'], 'sv' => (int)$u['sv'], 't' => time(), 'n' => 0, 'lk' => false, 'gh' => (string)$x['gh']]];
                $methods = array_values(array_filter([!empty($u['totp']) ? 'totp' : null, has_passkeys($u) && !app_client() ? 'passkey' : null]));
                respond(['ok' => true, 'need2fa' => true, 'methods' => $methods]);
            }
            attempts_record(true);
            $tok = sign_in($u);
            audit('login', 'Angemeldet');
            geraet_neu_melden($u, (bool)$x['neu']);
            respond(['ok' => true, 'csrf' => $tok, 'user' => me_payload($u)]);
        }

        case 'login_2fa': {
            start_session();
            attempts_check();
            $p = $_SESSION['pend'] ?? null;
            // Code-Schritt aus einer Sperre endet mit der Sperre – echte und wirkungslose Vorgänge gleich (sonst verriete das
            // Verhalten nach Ablauf, welcher Vorgang das richtige Passwort hatte)
            if (!$p || (int)$p['t'] < time() - 300 || (!empty($p['lk']) && time() >= (int)($p['bis'] ?? 0))) { $_SESSION = []; fail('Die Anmeldung ist abgelaufen. Bitte erneut mit Benutzername und Passwort anmelden.', 401); }
            $code = trim((string)(body()['code'] ?? ''));
            $res = with_lock('nutzer', function () use ($p, $code) {
                $users = users_load();
                // Code-Schritt ohne wirksame Anmeldung (während einer Sperre mit falschem Passwort, ohne App, unbekannter Name):
                // immer abweisen – mit derselben Antwort und demselben Aufwand wie ein falscher Code
                if (!empty($p['fake'])) { users_save($users); return ['bad', ['username' => (string)($p['name'] ?? ''), 'name' => '', 'role' => '']]; }
                $i = user_find($users, (string)$p['uid']);
                if ($i === null || !$users[$i]['active'] || (int)$users[$i]['sv'] !== (int)$p['sv'] || empty($users[$i]['totp'])) return ['gone', null];
                $u = &$users[$i];
                $gesperrt = (int)($u['lockedUntil'] ?? 0) > time();
                // Passwort-Schritt auf einem vertrauten Gerät während der Sperre (lib/geraete.php): Sperre gilt hier nicht,
                // falsche Codes zählen nur für dieses Gerät
                $gi = null;
                if (!empty($p['gh'])) foreach ((array)($u['geraete'] ?? []) as $k => $g) if (is_array($g) && hash_equals((string)($g['h'] ?? ''), (string)$p['gh']) && (int)($g['f'] ?? 0) < GERAET_FEHLER) $gi = $k;
                $frei = $gesperrt && $gi !== null;
                if (!empty($p['lk']) && !$gesperrt) return ['abgelaufen', null];   // Sperre vorzeitig aufgehoben (Administrator): neu anmelden
                if ($gesperrt && empty($p['lk']) && !$frei) return ['locked', $u];
                // höchstens 3 Code-Versuche je Sperre – über alle parallelen Anmeldevorgänge; danach wie ein falscher Code
                if ($gesperrt && !$frei && (int)($u['lockTries'] ?? 0) >= 3) { $out = $u; unset($u); users_save($users); return ['bad', $out]; }
                $how = null;
                $step = totp_check((string)$u['totp'], $code, (int)($u['totpLast'] ?? 0));
                if ($step !== null) { $u['totpLast'] = $step; $how = 'app'; }
                elseif (preg_match('/^[a-z0-9]{5}-?[a-z0-9]{5}$/i', $code)) {
                    $h = rc_hash($code);
                    $k = array_search($h, $u['recovery'] ?? [], true);
                    if ($k !== false) { array_splice($u['recovery'], $k, 1); $how = 'recovery'; }
                }
                if (!$how) {
                    if ($frei) { geraet_fehlversuch($u, $gi); $out = $u; unset($u); users_save($users); return ['bad', $out]; }
                    if ($gesperrt) {   // Code-Versuch während der Sperre: zählt nur gegen die 3 Versuche (Antwort wie sonst)
                        $u['lockTries'] = (int)($u['lockTries'] ?? 0) + 1;
                        users_save($users);
                        return ['bad', $u];
                    }
                    $locked = login_failure($u);
                    users_save($users);
                    return [$locked ? 'locked' : 'bad', $u];
                }
                $u['failCount'] = 0;
                $u['lockedUntil'] = 0;
                unset($u['lockTries']);
                $u['lastLogin'] = now();
                geraet_merken($u, $neu);
                $out = $u;
                unset($u);
                users_save($users);
                return [$how, $out, $neu];
            });
            [$st, $u, $neuGeraet] = $res + [2 => false];
            if ($st === 'gone') { $_SESSION = []; fail('Die Anmeldung ist abgelaufen. Bitte erneut anmelden.', 401); }
            if ($st === 'abgelaufen') { $_SESSION = []; fail('Die Anmeldung ist abgelaufen. Bitte erneut mit Benutzername und Passwort anmelden.', 401); }
            if ($st === 'bad' || $st === 'locked') {
                attempts_record(false);
                $_SESSION['pend']['n'] = (int)$p['n'] + 1;
                audit('login_fail', 'Zwei-Faktor-Code falsch', [], ['username' => $u['username'], 'name' => $u['name'], 'role' => $u['role']]);
                if ($st === 'locked') { $_SESSION = []; fail('Dieser Zugang ist wegen zu vieler Fehlversuche gesperrt. Bitte später erneut versuchen oder einen Administrator kontaktieren.', 429); }
                if ($_SESSION['pend']['n'] >= 5) { $_SESSION = []; fail('Zu viele falsche Codes. Bitte erneut anmelden.', 401); }
                usleep(300000);
                fail('Der Code ist nicht korrekt oder abgelaufen.', 401);
            }
            attempts_record(true);
            $tok = sign_in($u);
            audit('login', $st === 'recovery' ? 'Angemeldet (mit Wiederherstellungscode – noch ' . count($u['recovery'] ?? []) . ' übrig)' : 'Angemeldet (mit Zwei-Faktor-Code)');
            geraet_neu_melden($u, (bool)$neuGeraet);
            respond(['ok' => true, 'csrf' => $tok, 'user' => me_payload($u), 'recoveryLeft' => $st === 'recovery' ? count($u['recovery'] ?? []) : null]);
        }

        case 'twofa_begin': {
            $me = current_user();
            if (!$me) fail('Bitte erneut anmelden.', 401);
            require_csrf();
            // Austausch eines vorhandenen Faktors – und Ersteinrichtung später als 5 Minuten nach der Anmeldung – nur mit erneutem
            // Passwortnachweis (sonst könnte eine übernommene Sitzung einen eigenen Faktor hinterlegen und den Inhaber aussperren)
            if ((string)(body()['password'] ?? '') !== '' || has_second_factor($me) || (int)($_SESSION['authAt'] ?? 0) < time() - 300) {   // mitgesendetes Passwort immer prüfen
                unset($_SESSION['totpPending']);
                $me = confirm_password($me, (string)(body()['password'] ?? ''));
            }
            $secret = b32_encode(random_bytes(20));
            $_SESSION['totpPending'] = ['secret' => $secret, 'sv' => (int)$me['sv'], 't' => time()];
            $issuer = rawurlencode(($CFG['company'] ?: 'Wochenangebot') . ' Wochenangebot');
            respond(['ok' => true, 'secret' => $secret, 'uri' => "otpauth://totp/{$issuer}:" . rawurlencode($me['username']) . "?secret={$secret}&issuer={$issuer}&algorithm=SHA1&digits=6&period=30"]);
        }

        case 'twofa_enable': {
            $me = current_user();
            if (!$me) fail('Bitte erneut anmelden.', 401);
            require_csrf();
            $pending = $_SESSION['totpPending'] ?? null;
            if (!is_array($pending) || (int)$pending['sv'] !== (int)$me['sv'] || (int)$pending['t'] < time() - 300) {
                unset($_SESSION['totpPending']);
                fail('Bitte die Einrichtung neu starten.', 409);
            }
            $secret = (string)$pending['secret'];
            $step = totp_check($secret, (string)(body()['code'] ?? ''));
            if ($step === null) fail('Der Code stimmt nicht. Bitte die Uhrzeit des Handys prüfen und den aktuellen Code eingeben.', 422);
            $codes = recovery_codes();
            $u = user_update($me['id'], function (&$x) use ($secret, $step, $codes, $me) {
                if ((int)$x['sv'] !== (int)$me['sv'] || !$x['active']) fail('Bitte erneut anmelden.', 401);
                $x['sv'] = (int)$x['sv'] + 1;
                $x['totp'] = $secret; $x['totpLast'] = $step; $x['recovery'] = array_map('rc_hash', $codes); $x['changed'] = now();
            });
            if (!$u) fail('Bitte erneut anmelden.', 401);
            keep_current_session($u);
            audit('twofa', 'Zwei-Faktor-Anmeldung eingerichtet');
            respond(['ok' => true, 'recovery' => $codes, 'user' => me_payload($u)]);
        }

        case 'twofa_disable': {
            $me = require_auth(true);
            if (empty($me['totp'])) fail('Die Zwei-Faktor-Anmeldung ist nicht eingerichtet.', 409);
            if (twofa_required($me) && !has_passkeys($me)) fail('Für Ihren Zugang ist die Zwei-Faktor-Anmeldung vorgeschrieben und kann nicht ausgeschaltet werden.', 422);
            $me = confirm_password($me, (string)(body()['password'] ?? ''));
            $u = user_update($me['id'], function (&$x) use ($me) {
                if ((int)$x['sv'] !== (int)$me['sv'] || !$x['active']) fail('Bitte erneut anmelden.', 401);
                unset($x['totp'], $x['totpLast'], $x['recovery']);
                $x['sv'] = (int)$x['sv'] + 1;
                $x['changed'] = now();
            });
            if (!$u) fail('Bitte erneut anmelden.', 401);
            keep_current_session($u);
            audit('twofa', 'Zwei-Faktor-Anmeldung ausgeschaltet');
            respond(['ok' => true, 'user' => me_payload($u)]);
        }

        case 'logout': {
            $u = current_user();
            // Mit Sitzung nur mit CSRF-Token (wie kunde_logout): eine fremde Seite kann niemanden abmelden. Ohne Sitzung
            // (abgelaufen, schon abgemeldet) bleibt Abmelden ohne Token möglich, damit Oberflächen immer aufräumen können.
            if ($u) require_csrf();
            if ($u) { audit('logout', 'Abgemeldet'); $sid = (string)($_SESSION['sid'] ?? ''); sess_remove(function ($k) use ($sid) { return $k === $sid; }); }
            $_SESSION = [];
            session_destroy();
            // Keycloak-Host: danach über das Modul auch zentral abmelden (alle Anwendungen per Back-Channel-Logout)
            respond(oidc_modus() ? ['ok' => true, 'abmelden' => oidc_abmelde_adresse()] : ['ok' => true]);
        }

        /* Hell/Dunkel am eigenen Konto (Anzeige-Einstellung): gilt auf jedem Host der Plattform, weil jede Seite sie nach der
           Anmeldung aus dem Status übernimmt (theme.js). '' = wie das Gerät. Nur der eigene Datensatz, kein Protokoll nötig. */
        case 'theme_save': {
            $me = require_auth(true);
            $t = body()['theme'] ?? null;
            if (!is_string($t) || !in_array($t, ['light', 'dark', ''], true)) fail('Ungültige Darstellung.', 422);
            with_lock('nutzer', function () use ($me, $t) {
                $users = users_load();
                $i = user_find($users, $me['id']);
                if ($i === null) fail('Bitte erneut anmelden.', 401);
                if (($users[$i]['theme'] ?? '') === $t) return;
                if ($t === '') unset($users[$i]['theme']); else $users[$i]['theme'] = $t;
                users_save($users);
            });
            respond(['ok' => true, 'theme' => $t]);
        }
        case 'change_password': {
            $me = current_user();
            if (!$me) fail('Bitte erneut anmelden.', 401);
            require_csrf();
            $b = body();
            $me = confirm_password($me, (string)($b['current'] ?? ''), 401);
            $new = check_password($b['password'] ?? '', $me['username']);
            if (password_verify($new, (string)$me['hash'])) fail('Bitte ein anderes als das bisherige Passwort wählen.');
            $u = with_lock('nutzer', function () use ($me, $new) {
                $users = users_load();
                $i = user_find($users, $me['id']);
                if ($i === null || !$users[$i]['active'] || (int)$users[$i]['sv'] !== (int)$me['sv']) fail('Bitte erneut anmelden.', 401);
                $users[$i]['hash'] = password_hash($new, PASSWORD_DEFAULT);
                $users[$i]['mustChange'] = false;
                unset($users[$i]['mustChangeGrund']);
                $users[$i]['sv'] = (int)$users[$i]['sv'] + 1;   // andere Sitzungen dieses Nutzers abmelden
                geraete_zuruecksetzen($users[$i]);              // vertraut bleibt nur dieses Gerät
                $users[$i]['changed'] = now();
                users_save($users);
                return $users[$i];
            });
            $_SESSION['sv'] = (int)$u['sv'];
            mark_admin_confirmed($u);
            $GLOBALS['ME'] = $u;
            $sid = (string)($_SESSION['sid'] ?? '');
            sess_remove(function ($k, $v) use ($u, $sid) { return $v['uid'] === $u['id'] && $k !== $sid; });
            audit('password', 'Eigenes Passwort geändert');
            respond(['ok' => true, 'user' => me_payload($u)]);
        }
}
