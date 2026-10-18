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
                     'user' => $u ? me_payload($u) : null, 'company' => $CFG['company'], 'wartung' => $u ? wartung() : null]);
        }

        case 'wartung_save': {
            $me = require_admin_confirmation();
            $b = body();
            $on = !empty($b['active']);
            $msg = mb_substr(trim(str_replace("\r", '', preg_replace('/[\x00-\x08\x0b-\x1f]/u', '', (string)($b['message'] ?? '')) ?? '')), 0, 500);
            $until = (string)($b['until'] ?? '');
            if ($until !== '' && !preg_match('/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/', $until)) fail('Bitte eine gültige Uhrzeit für das voraussichtliche Ende angeben.', 422);
            $old = wartung();
            $new = ['active' => $on, 'message' => $msg, 'until' => $until !== '' ? $until : null, 'since' => $on ? ($old['since'] ?? now()) : null, 'by' => $me['name'], 'changed' => now()];
            store_write('wartung', $new);
            if ((bool)$old !== $on) audit('wartung', $on ? 'Wartungsmodus eingeschaltet – Angebotsseite für Kunden pausiert' : 'Wartungsmodus ausgeschaltet – Angebotsseite wieder erreichbar',
                [['k' => 'wartung', 'code' => '', 'name' => 'Wartungsmodus', 'f' => 'Status', 'from' => $old ? 'an' : 'aus', 'to' => $on ? 'an' : 'aus']]);
            elseif ($on) audit('wartung', 'Hinweis zum Wartungsmodus geändert');
            respond(['ok' => true, 'wartung' => wartung()]);
        }

        case 'reauth': {
            $me = require_auth(true, 'admin');
            $u = confirm_password($me, (string)(body()['password'] ?? ''));
            mark_admin_confirmed($u);
            audit('reauth', 'Sensible Verwaltungsaktionen für fünf Minuten bestätigt');
            respond(['ok' => true, 'confirmedUntil' => time() + ADMIN_CONFIRM_SECONDS]);
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
                    if ((int)($u['lockedUntil'] ?? 0) > time()) { password_verify($pw, (string)$u['hash']); return ['locked', $u]; }
                    if (!password_verify($pw, (string)$u['hash'])) {
                        $lockedNow = login_failure($users[$i]);
                        users_save($users);
                        return [$lockedNow ? 'lockednow' : 'bad', $users[$i]];
                    }
                    if (!$u['active']) return ['inactive', $u];
                    if (password_needs_rehash((string)$u['hash'], PASSWORD_DEFAULT)) $users[$i]['hash'] = password_hash($pw, PASSWORD_DEFAULT);
                    // Bei 2FA ist das Passwort allein noch keine erfolgreiche Anmeldung.
                    if (empty($u['totp'])) {
                        $users[$i]['failCount'] = 0;
                        $users[$i]['lockedUntil'] = 0;
                        $users[$i]['lastLogin'] = now();
                    }
                    users_save($users);
                    return ['ok', $users[$i]];
                }
                password_verify($pw, '$2y$10$y80WR5wtxxV9G3NpBGQXmeL3EYKIGKm4gaElkDTK2cWFQtjyZdoPa'); // gleiche Laufzeit wie bei vorhandenem Nutzer
                return ['bad', null];
            });
            [$st, $u] = $res;
            $who = ['username' => mb_substr($name, 0, 40), 'name' => $u['name'] ?? '', 'role' => $u['role'] ?? ''];
            if ($st !== 'ok') {
                attempts_record(false);
                $why = ['inactive' => ' – Zugang deaktiviert', 'locked' => ' – Zugang gesperrt', 'lockednow' => ' – Zugang nach zu vielen Fehlversuchen gesperrt', 'bad' => ''][$st];
                audit('login_fail', 'Anmeldung fehlgeschlagen' . ($name !== '' ? ' (Benutzername „' . mb_substr($name, 0, 40) . '“)' : '') . $why, [], $who);
                usleep(400000);
                if ($st === 'inactive') fail('Dieser Zugang ist deaktiviert.', 401);
                if ($st === 'locked' || $st === 'lockednow') fail('Dieser Zugang ist wegen zu vieler Fehlversuche bis ' . (new DateTime('@' . (int)$u['lockedUntil']))->setTimezone(new DateTimeZone('Europe/Berlin'))->format('H:i') . ' Uhr gesperrt. Ein Administrator kann ihn vorher entsperren.', 429);
                fail('Benutzername oder Passwort ist nicht korrekt.', 401);
            }
            if (!empty($u['totp'])) {
                // zweiter Schritt: Code aus der Authenticator-App
                session_regenerate_id(true);
                $_SESSION = ['pend' => ['uid' => $u['id'], 'sv' => (int)$u['sv'], 't' => time(), 'n' => 0]];
                respond(['ok' => true, 'need2fa' => true]);
            }
            attempts_record(true);
            $tok = sign_in($u);
            audit('login', 'Angemeldet');
            respond(['ok' => true, 'csrf' => $tok, 'user' => me_payload($u)]);
        }

        case 'login_2fa': {
            start_session();
            attempts_check();
            $p = $_SESSION['pend'] ?? null;
            if (!$p || (int)$p['t'] < time() - 300) { $_SESSION = []; fail('Die Anmeldung ist abgelaufen. Bitte erneut mit Benutzername und Passwort anmelden.', 401); }
            $code = trim((string)(body()['code'] ?? ''));
            $res = with_lock('nutzer', function () use ($p, $code) {
                $users = users_load();
                $i = user_find($users, (string)$p['uid']);
                if ($i === null || !$users[$i]['active'] || (int)$users[$i]['sv'] !== (int)$p['sv'] || empty($users[$i]['totp'])) return ['gone', null];
                $u = &$users[$i];
                if ((int)($u['lockedUntil'] ?? 0) > time()) return ['locked', $u];
                $how = null;
                $step = totp_check((string)$u['totp'], $code, (int)($u['totpLast'] ?? 0));
                if ($step !== null) { $u['totpLast'] = $step; $how = 'app'; }
                elseif (preg_match('/^[a-z0-9]{5}-?[a-z0-9]{5}$/i', $code)) {
                    $h = rc_hash($code);
                    $k = array_search($h, $u['recovery'] ?? [], true);
                    if ($k !== false) { array_splice($u['recovery'], $k, 1); $how = 'recovery'; }
                }
                if (!$how) {
                    $locked = login_failure($u);
                    users_save($users);
                    return [$locked ? 'locked' : 'bad', $u];
                }
                $u['failCount'] = 0;
                $u['lockedUntil'] = 0;
                $u['lastLogin'] = now();
                $out = $u;
                unset($u);
                users_save($users);
                return [$how, $out];
            });
            [$st, $u] = $res;
            if ($st === 'gone') { $_SESSION = []; fail('Die Anmeldung ist abgelaufen. Bitte erneut anmelden.', 401); }
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
            respond(['ok' => true, 'csrf' => $tok, 'user' => me_payload($u), 'recoveryLeft' => $st === 'recovery' ? count($u['recovery'] ?? []) : null]);
        }

        case 'twofa_begin': {
            $me = current_user();
            if (!$me) fail('Bitte erneut anmelden.', 401);
            require_csrf();
            // Auch der Austausch eines vorhandenen Faktors braucht einen erneuten Passwortnachweis.
            if (!empty($me['totp'])) {
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
            if (twofa_required($me)) fail('Für Ihre Rolle ist die Zwei-Faktor-Anmeldung vorgeschrieben und kann nicht ausgeschaltet werden.', 422);
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
            if ($u) { audit('logout', 'Abgemeldet'); $sid = (string)($_SESSION['sid'] ?? ''); sess_remove(function ($k) use ($sid) { return $k === $sid; }); }
            $_SESSION = [];
            session_destroy();
            respond(['ok' => true]);
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
                $users[$i]['sv'] = (int)$users[$i]['sv'] + 1;   // andere Sitzungen dieses Nutzers abmelden
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
