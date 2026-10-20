<?php
declare(strict_types=1);
/* Aktionen: Passkeys (WebAuthn) – eigene Passkeys verwalten, Anmeldung mit Passkey
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const PASSKEY_APP_FEHLER = 'In der App ist die Anmeldung mit Passkey nicht möglich – bitte den Code aus der Authenticator-App verwenden.';

switch ($action) {
        case 'passkey_list': {
            $me = require_auth();
            header('Cache-Control: no-store');
            respond(['ok' => true, 'passkeys' => passkey_public($me), 'max' => PASSKEY_MAX]);
        }

        /* Einrichtung starten – wie bei der Authenticator-App nur mit Passwort, außer direkt nach der Anmeldung ohne zweiten Faktor */
        case 'passkey_begin': {
            $me = current_user();
            if (!$me) fail('Bitte erneut anmelden.', 401);
            require_csrf();
            if (app_client()) fail(PASSKEY_APP_FEHLER, 403);
            unset($_SESSION['pkReg']);
            // ein mitgesendetes Passwort wird immer geprüft (Dialog im Menü)
            $pw = (string)(body()['password'] ?? '');
            if ($pw !== '' || has_second_factor($me) || (int)($_SESSION['authAt'] ?? 0) < time() - 300) $me = confirm_password($me, $pw);
            if (count((array)($me['passkeys'] ?? [])) >= PASSKEY_MAX) fail('Es sind höchstens ' . PASSKEY_MAX . ' Passkeys je Zugang möglich. Bitte zuerst einen entfernen.', 422);
            $c = passkey_challenge('pkReg', ['uid' => $me['id'], 'sv' => (int)$me['sv']]);
            respond(['ok' => true, 'options' => passkey_create_options($me, $c)]);
        }

        case 'passkey_register': {
            $me = current_user();
            if (!$me) fail('Bitte erneut anmelden.', 401);
            require_csrf();
            if (app_client()) fail(PASSKEY_APP_FEHLER, 403);
            $p = passkey_take('pkReg');
            if (!$p || ($p['uid'] ?? '') !== $me['id'] || (int)($p['sv'] ?? -1) !== (int)$me['sv']) fail('Bitte die Einrichtung neu starten.', 409);
            $b = body();
            $e = passkey_verify_registration($b, (string)$p['c']);
            $u = with_lock('nutzer', function () use ($me, &$e, $b) {
                $users = users_load();
                foreach ($users as $x) foreach ((array)($x['passkeys'] ?? []) as $pk) if (hash_equals((string)$pk['id'], $e['id'])) fail('Dieser Passkey ist bereits eingerichtet.', 409);
                $i = user_find($users, $me['id']);
                if ($i === null || !$users[$i]['active'] || (int)$users[$i]['sv'] !== (int)$me['sv']) fail('Bitte erneut anmelden.', 401);
                if (count((array)($users[$i]['passkeys'] ?? [])) >= PASSKEY_MAX) fail('Es sind höchstens ' . PASSKEY_MAX . ' Passkeys je Zugang möglich.', 422);
                $e['name'] = passkey_name($b['name'] ?? '', $users[$i]);
                $users[$i]['passkeys'] = array_values(array_merge((array)($users[$i]['passkeys'] ?? []), [$e]));
                $users[$i]['sv'] = (int)$users[$i]['sv'] + 1;   // andere Sitzungen beenden (wie beim Einrichten der Authenticator-App)
                $users[$i]['changed'] = now();
                users_save($users);
                return $users[$i];
            });
            keep_current_session($u);
            audit('twofa', 'Passkey „' . $e['name'] . '“ hinzugefügt');
            respond(['ok' => true, 'user' => me_payload($u), 'passkeys' => passkey_public($u)]);
        }

        case 'passkey_rename': {
            $me = require_auth(true);
            $b = body();
            $ref = (string)($b['ref'] ?? '');
            $name = s($b['name'] ?? '', 60, false);
            if ($name === null) throw new InvalidArgumentException('Bitte einen Namen angeben.');
            $found = false;
            $u = user_update($me['id'], function (&$x) use ($ref, $name, &$found) {
                foreach ($x['passkeys'] ?? [] as $k => $pk) if (passkey_ref($pk) === $ref) { $x['passkeys'][$k]['name'] = preg_replace('/[\x00-\x1f\x7f]/u', '', $name); $found = true; }
            });
            if (!$u || !$found) fail('Passkey nicht gefunden.', 404);
            respond(['ok' => true, 'passkeys' => passkey_public($u)]);
        }

        case 'passkey_delete': {
            $me = require_auth(true);
            $b = body();
            $ref = (string)($b['ref'] ?? '');
            $pk = null;
            foreach ((array)($me['passkeys'] ?? []) as $x) if (passkey_ref($x) === $ref) $pk = $x;
            if (!$pk) fail('Passkey nicht gefunden.', 404);
            if (twofa_required($me) && empty($me['totp']) && count($me['passkeys']) === 1) fail('Für Ihre Rolle ist ein zweiter Faktor vorgeschrieben. Bitte zuerst die Authenticator-App einrichten oder einen weiteren Passkey hinzufügen.', 422);
            $me = confirm_password($me, (string)($b['password'] ?? ''));
            $u = user_update($me['id'], function (&$x) use ($me, $ref) {
                if ((int)$x['sv'] !== (int)$me['sv'] || !$x['active']) fail('Bitte erneut anmelden.', 401);
                $x['passkeys'] = array_values(array_filter((array)($x['passkeys'] ?? []), fn($p) => passkey_ref($p) !== $ref));
                if (!$x['passkeys']) unset($x['passkeys']);
                $x['sv'] = (int)$x['sv'] + 1;
                $x['changed'] = now();
            });
            if (!$u) fail('Bitte erneut anmelden.', 401);
            keep_current_session($u);
            audit('twofa', 'Passkey „' . $pk['name'] . '“ entfernt');
            respond(['ok' => true, 'user' => me_payload($u), 'passkeys' => passkey_public($u)]);
        }

        /* Anmeldung: ohne Benutzername (auffindbare Passkeys) oder mit second = zweiter Schritt nach dem Passwort */
        case 'passkey_login_begin': {
            start_session();
            attempts_check();
            if (app_client()) fail(PASSKEY_APP_FEHLER, 403);
            $second = !empty(body()['second']);
            $u = null;
            if ($second) {
                $p = $_SESSION['pend'] ?? null;
                if (!is_array($p) || (int)$p['t'] < time() - 300) { $_SESSION = []; fail('Die Anmeldung ist abgelaufen. Bitte erneut mit Benutzername und Passwort anmelden.', 401); }
                $users = users_load();
                $i = user_find($users, (string)$p['uid']);
                if ($i === null || !$users[$i]['active'] || (int)$users[$i]['sv'] !== (int)$p['sv'] || !has_passkeys($users[$i])) { $_SESSION = []; fail('Die Anmeldung ist abgelaufen. Bitte erneut anmelden.', 401); }
                $u = $users[$i];
            }
            $c = passkey_challenge('pkAuth', ['second' => $second]);
            respond(['ok' => true, 'options' => passkey_get_options($c, $u)]);
        }

        case 'passkey_login': {
            start_session();
            attempts_check();
            if (app_client()) fail(PASSKEY_APP_FEHLER, 403);
            $ch = passkey_take('pkAuth');
            if (!$ch) fail('Die Anfrage ist abgelaufen. Bitte erneut versuchen.', 401);
            $second = !empty($ch['second']);
            $pend = $second ? ($_SESSION['pend'] ?? null) : null;
            if ($second && (!is_array($pend) || (int)$pend['t'] < time() - 300)) { $_SESSION = []; fail('Die Anmeldung ist abgelaufen. Bitte erneut mit Benutzername und Passwort anmelden.', 401); }
            $b = body();
            $denied = function (string $why, ?array $u, string $msg, int $code = 401) use ($second, $pend) {
                attempts_record(false);
                $who = $u ? ['username' => $u['username'], 'name' => $u['name'], 'role' => $u['role']] : ['username' => '', 'name' => '', 'role' => ''];
                audit('login_fail', $why, [], $who);
                if ($second) {
                    $_SESSION['pend']['n'] = (int)$pend['n'] + 1;
                    if ($code === 429 || $_SESSION['pend']['n'] >= 5) $_SESSION = [];
                }
                usleep(300000);
                fail($msg, $code);
            };
            $cdRaw = b64u_dec($b['clientDataJSON'] ?? null);
            $ad = b64u_dec($b['authenticatorData'] ?? null);
            $sig = b64u_dec($b['signature'] ?? null);
            $id = is_string($b['id'] ?? null) && strlen($b['id']) <= 1400 ? $b['id'] : '';
            $uh = isset($b['userHandle']) && $b['userHandle'] !== '' && $b['userHandle'] !== null ? b64u_dec($b['userHandle']) : null;
            if ($cdRaw === null || $ad === null || $sig === null || $id === '') $denied('Anmeldung mit Passkey fehlgeschlagen (ungültige Antwort)', null, 'Die Antwort des Passkeys ist ungültig.');
            try {
                passkey_client_data($cdRaw, 'webauthn.get', (string)$ch['c']);
                $info = passkey_auth_data($ad, false);
            } catch (InvalidArgumentException $ex) {
                $denied('Anmeldung mit Passkey fehlgeschlagen (' . $ex->getMessage() . ')', null, $ex->getMessage());
            }
            $res = with_lock('nutzer', function () use ($id, $uh, $pend, $ad, $cdRaw, $sig, $info) {
                $users = users_load();
                $i = $k = null;
                foreach ($users as $ui => $x) foreach ((array)($x['passkeys'] ?? []) as $pi => $pk) if (hash_equals((string)$pk['id'], $id)) { $i = $ui; $k = $pi; }
                if ($i === null) return ['unknown', null, ''];
                $u = &$users[$i];
                $pk = $u['passkeys'][$k];
                $name = (string)($pk['name'] ?? '');
                if ($uh !== null && !hash_equals((string)$u['id'], $uh)) return ['unknown', null, ''];
                if ($pend && ((string)$pend['uid'] !== $u['id'] || (int)$pend['sv'] !== (int)$u['sv'])) return ['wrong', $u, $name];
                if ((int)($u['lockedUntil'] ?? 0) > time()) return ['locked', $u, $name];
                if (!passkey_signature_ok($pk, $ad, $cdRaw, $sig)) {
                    $lockedNow = login_failure($u);
                    $out = $u; unset($u);
                    users_save($users);
                    return [$lockedNow ? 'lockednow' : 'bad', $out, $name];
                }
                // Signaturzähler: kleiner oder gleich dem gespeicherten → möglicherweise kopierter Schlüssel
                $old = (int)($pk['signCount'] ?? 0); $new = (int)$info['signCount'];
                if ($new > 0 && $old > 0 && $new <= $old) return ['clone', $u, $name];
                if (!$u['active']) return ['inactive', $u, $name];
                $u['passkeys'][$k]['signCount'] = max($old, $new);   // Zähler nie zurücksetzen (manche Geräte melden immer 0)
                $u['passkeys'][$k]['lastUsed'] = now();
                if (!empty($u['mustChange'])) { $out = $u; unset($u); users_save($users); return ['mustchange', $out, $name]; }
                $u['failCount'] = 0;
                $u['lockedUntil'] = 0;
                $u['lastLogin'] = now();
                $out = $u; unset($u);
                users_save($users);
                return ['ok', $out, $name];
            });
            [$st, $u, $name] = $res;
            $nm = $name !== '' ? ' „' . $name . '“' : '';
            if ($st === 'unknown') $denied('Anmeldung mit unbekanntem Passkey', null, 'Dieser Passkey ist hier nicht bekannt. Bitte mit Benutzername und Passwort anmelden.');
            if ($st === 'wrong') $denied('Passkey' . $nm . ' gehört zu einem anderen Zugang (zweiter Anmeldeschritt)', $u, 'Dieser Passkey gehört nicht zu diesem Zugang.');
            if ($st === 'locked' || $st === 'lockednow') $denied('Anmeldung mit Passkey' . $nm . ' fehlgeschlagen – Zugang gesperrt', $u, 'Dieser Zugang ist wegen zu vieler Fehlversuche bis ' . (new DateTime('@' . (int)$u['lockedUntil']))->setTimezone(new DateTimeZone('Europe/Berlin'))->format('H:i') . ' Uhr gesperrt. Ein Administrator kann ihn vorher entsperren.', 429);
            if ($st === 'bad') $denied('Anmeldung mit Passkey' . $nm . ' fehlgeschlagen (Signatur ungültig)', $u, 'Der Passkey konnte nicht bestätigt werden.');
            if ($st === 'clone') $denied('Passkey' . $nm . ' abgewiesen: Signaturzähler zu niedrig (möglicherweise kopiert)', $u, 'Der Passkey wurde abgewiesen, weil sein Zähler nicht passt (möglicherweise kopiert). Bitte einen Administrator informieren.');
            if ($st === 'inactive') $denied('Anmeldung mit Passkey' . $nm . ' fehlgeschlagen – Zugang deaktiviert', $u, 'Dieser Zugang ist deaktiviert.');
            if ($st === 'mustchange') fail('Bitte zuerst mit Benutzername und Passwort anmelden und ein neues Passwort festlegen.', 403);
            attempts_record(true);
            $tok = sign_in($u);
            audit('login', $second ? 'Angemeldet (mit Passwort und Passkey)' : 'Angemeldet (mit Passkey)');
            respond(['ok' => true, 'csrf' => $tok, 'user' => me_payload($u)]);
        }
}
