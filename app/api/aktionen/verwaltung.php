<?php
declare(strict_types=1);
/* Aktionen: Sicherheit, Länder-/IP-Sperre, Sitzungen, Nutzer, Protokoll
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'security_status': {
            $me = require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $users = users_load();
            $names = []; foreach ($users as $u) $names[$u['id']] = $u;
            $sess = [];
            foreach (sess_prune(store_read('sitzungen') ?? []) as $sid => $v) {
                $u = $names[$v['uid']] ?? null;
                $sess[] = ['sid' => $sid, 'uid' => $v['uid'], 'username' => $u['username'] ?? '?', 'name' => $u['name'] ?? '?', 'role' => $u['role'] ?? '',
                           'ip' => $v['ip'], 'ua' => $v['ua'], 'created' => $v['created'], 'seen' => gmdate('Y-m-d\TH:i:s\Z', (int)$v['seen']), 'current' => $sid === ($_SESSION['sid'] ?? '')];
            }
            usort($sess, function ($a, $b) { return strcmp($b['seen'], $a['seen']); });
            $ips = [];
            foreach (store_read('logins') ?? [] as $k => $v) {
                if ((int)($v['until'] ?? 0) <= time() && (int)($v['n'] ?? 0) === 0) continue;
                $ips[] = ['key' => $k, 'ip' => $v['ip'] ?? 'unbekannt', 'n' => (int)($v['n'] ?? 0), 'until' => (int)($v['until'] ?? 0) > time() ? gmdate('Y-m-d\TH:i:s\Z', (int)$v['until']) : null, 't' => gmdate('Y-m-d\TH:i:s\Z', (int)($v['t'] ?? time()))];
            }
            $fails = [];
            foreach ([gmdate('Y-m'), gmdate('Y-m', strtotime('first day of last month'))] as $m) {
                foreach (store_read('protokoll/' . $m) ?? [] as $e) if (in_array($e['a'], ['login_fail', 'kunde_login_fail'], true) && strtotime($e['t']) > time() - 7 * 86400) $fails[] = ['t' => $e['t'], 'u' => $e['u'], 'ip' => $e['ip'] ?? '', 's' => $e['s']];
            }
            usort($fails, function ($a, $b) { return strcmp($b['t'], $a['t']); });
            $f24 = count(array_filter($fails, function ($e) { return strtotime($e['t']) > time() - 86400; }));
            $gs = store_read('laendersperre') ?? [];
            $gcc = []; foreach ($gs['cc'] ?? [] as $k => $v) $gcc[] = ['cc' => $k, 'n' => $v['n'], 'last' => $v['last']];
            usort($gcc, function ($a, $b) { return $b['n'] <=> $a['n']; });
            $g7 = (($gs['day'] ?? '') === gmdate('Y-m-d') ? (int)($gs['today'] ?? 0) : 0);
            foreach ($gs['days'] ?? [] as $dd => $n) if ($dd > gmdate('Y-m-d', time() - 7 * 86400)) $g7 += (int)$n;
            $secLog = sec_log_entries(14);
            respond(['ok' => true, 'settings' => sec(), 'bestaetigung' => bestaetigung_katalog(), 'bestaetigungMinuten' => BESTAETIGUNG_MINUTEN, 'myIp' => client_ip(), 'https' => is_https(),
                     'timeline' => sec_timeline($secLog), 'topIps' => sec_top_ips($secLog), 'config' => sec_config_checks($users),
                     'backup' => store_read('sicherung'),
                     'wartung' => wartung(), 'storage' => store_stats(), 'php' => PHP_VERSION,
                     'disk' => ['free' => @disk_free_space($DATA) ?: null, 'total' => @disk_total_space($DATA) ?: null],
                     'mail' => (function () {
                         $l = array_filter(store_read('mailversand') ?? [], function ($x) { return strtotime($x['t']) > time() - 7 * 86400; });
                         return ['configured' => (bool)mail_cfg() && (bool)mail_base_url(), 'sent7' => count(array_filter($l, function ($x) { return $x['ok']; })), 'failed7' => count(array_filter($l, function ($x) { return !$x['ok']; }))];
                     })(),
                     'orders' => (function () {
                         $all = store_read('bestellungen') ?? [];
                         $l = array_filter($all, function ($x) { return strtotime($x['t']) > time() - 7 * 86400; });
                         $last = $all ? end($all) : null;
                         return ['enabled' => order_enabled(), 'n7' => count($l), 'failed7' => count(array_filter($l, function ($x) { return ($x['status'] ?? '') === 'fehler'; })), 'last' => $last['t'] ?? null, 'lastNr' => $last['nr'] ?? null];
                     })(),
                     'customers' => (function () {
                         $c = customers_load()['customers'];
                         $act = array_filter($c, function ($x) { return !empty($x['active']); });
                         return ['active' => count($act), 'withLogin' => count(array_filter($act, function ($x) { return !empty($x['login']['active']); })),
                                 'online' => count(array_unique(array_column(ksess_prune(store_read('kundensitzungen') ?? []), 'kid')))];
                     })(),
                     'deployment' => store_read('deployment'),
                     'myCountry' => geo_country(client_ip()), 'geo' => geo_info(), 'geoCountries' => GEO_COUNTRIES, 'geoStats' => array_slice($gcc, 0, 30), 'geoBlocked7' => $g7,
                     'users' => array_map('user_public', $users), 'sessions' => $sess, 'blockedIps' => $ips,
                     'fails' => array_slice($fails, 0, 30), 'fails24' => $f24]);
        }

        /* Nur lesende Diagnosen (keine Befehle auf dem Server) */
        case 'security_diag': {
            require_auth(true, 'admin');
            header('Cache-Control: no-store');
            respond(['ok' => true, 'result' => sec_diag((string)(body()['check'] ?? ''))]);
        }
        /* Sicherheitsprotokoll exportieren (enthält IP-Adressen und Namen → Passwortbestätigung) */
        case 'security_export': {
            $me = require_admin_confirmation('security_export');
            $days = (int)(body()['days'] ?? 90);
            if (!in_array($days, [7, 30, 90, 365], true)) fail('Ungültiger Zeitraum.', 422);
            $r = sec_export_csv($days);
            audit('security', "Sicherheitsprotokoll exportiert ({$days} Tage, {$r['count']} Einträge)");
            respond(['ok' => true, 'csv' => $r['csv'], 'count' => $r['count'], 'filename' => 'Sicherheitsprotokoll_' . gmdate('Y-m-d') . '_' . $days . 'T.csv']);
        }
        case 'security_save': {
            $me = require_admin_confirmation('security_save');
            $b = body();
            $old = sec();
            $twofa = in_array($b['twofa'] ?? '', ['off', 'admins', 'all'], true) ? $b['twofa'] : 'off';
            $ips = [];
            foreach (array_slice(is_array($b['adminIps'] ?? null) ? $b['adminIps'] : [], 0, 50) as $c) {
                $c = trim((string)$c);
                if ($c === '') continue;
                if (!valid_cidr($c)) throw new InvalidArgumentException("„{$c}“ ist keine gültige IP-Adresse oder kein gültiger Bereich (z. B. 80.147.24.150 oder 80.147.24.0/24).");
                $ips[] = $c;
            }
            $ipEnabled = !empty($b['ipEnabled']);
            if ($ipEnabled && !$ips) throw new InvalidArgumentException('Bitte mindestens eine freigegebene IP-Adresse eintragen.');
            if ($ipEnabled && !ip_allowed(client_ip(), $ips)) throw new InvalidArgumentException('Ihre aktuelle Adresse ' . client_ip() . ' ist nicht in der Liste – Sie würden sich selbst aussperren.');
            $geoEnabled = !empty($b['geoEnabled']);
            $geoMode = ($b['geoMode'] ?? '') === 'allow' ? 'allow' : 'block';
            $geoScope = ($b['geoScope'] ?? '') === 'all' ? 'all' : 'admin';
            $gc = [];
            foreach (array_slice(is_array($b['geoCountries'] ?? null) ? $b['geoCountries'] : [], 0, 300) as $c) {
                $c = strtoupper(trim((string)$c));
                if (in_array($c, GEO_COUNTRIES, true) && !in_array($c, $gc, true)) $gc[] = $c;
            }
            sort($gc);
            if ($geoEnabled && !$gc) throw new InvalidArgumentException($geoMode === 'allow' ? 'Bitte mindestens ein erlaubtes Land auswählen.' : 'Bitte mindestens ein Land zum Sperren auswählen.');
            if ($geoEnabled && !geo_info()) throw new InvalidArgumentException('Die Länderdatenbank fehlt – bitte zuerst „Länderdaten aktualisieren“.');
            $geoS = ['geoEnabled' => $geoEnabled, 'geoMode' => $geoMode, 'geoCountries' => $gc, 'adminIps' => $ips];
            if ($geoEnabled && ($mc = geo_blocked(client_ip(), $geoS)) !== null) throw new InvalidArgumentException("Sie greifen gerade aus einem Land zu, das damit gesperrt wäre ({$mc}) – Sie würden sich selbst aussperren.");
            if ($twofa !== 'off' && !has_second_factor($me) && ($twofa === 'all' || $me['role'] === 'admin')) throw new InvalidArgumentException('Bitte richten Sie zuerst für sich selbst die Zwei-Faktor-Anmeldung ein (Menü „…“ → „Zwei-Faktor-Anmeldung“).');
            $new = ['twofa' => $twofa, 'pwMin' => max(10, min(32, (int)($b['pwMin'] ?? 10))), 'pwComplex' => !empty($b['pwComplex']),
                    'idleMinutes' => in_array((int)($b['idleMinutes'] ?? 480), [15, 30, 60, 120, 240, 480, 720], true) ? (int)($b['idleMinutes'] ?? 480) : 480,
                    'ipEnabled' => $ipEnabled, 'adminIps' => $ips,
                    'lockAfter' => max(3, min(20, (int)($b['lockAfter'] ?? 10))), 'lockMinutes' => max(5, min(1440, (int)($b['lockMinutes'] ?? 15))),
                    'geoEnabled' => $geoEnabled, 'geoMode' => $geoMode, 'geoCountries' => $gc, 'geoScope' => $geoScope];
            // Passwortbestätigung: nur abschaltbare Aktionen; ohne Angabe (ältere Oberfläche) bleibt der bisherige Stand
            if (array_key_exists('bestaetigungAus', $b)) {
                $aus = [];
                foreach ((array)$b['bestaetigungAus'] as $k) {
                    $k = (string)$k;
                    if (!isset(BESTAETIGUNG[$k])) throw new InvalidArgumentException('Unbekannte Aktion bei der Passwortbestätigung.');
                    if (BESTAETIGUNG[$k][2]) throw new InvalidArgumentException('„' . BESTAETIGUNG[$k][1] . '“ verlangt immer eine Passwortbestätigung.');
                    if (!in_array($k, $aus, true)) $aus[] = $k;
                }
                $new['bestaetigungAus'] = array_values(array_filter(array_keys(BESTAETIGUNG), fn($k) => in_array($k, $aus, true)));
            } else $new['bestaetigungAus'] = array_values((array)($old['bestaetigungAus'] ?? []));
            $min = (int)($b['bestaetigungMinuten'] ?? ($old['bestaetigungMinuten'] ?? 5));
            if (!in_array($min, BESTAETIGUNG_MINUTEN, true)) throw new InvalidArgumentException('Ungültige Gültigkeitsdauer der Passwortbestätigung.');
            $new['bestaetigungMinuten'] = $min;
            store_write('sicherheit', $new);
            $GLOBALS['SEC'] = $new;
            $L = ['twofa' => 'Zwei-Faktor-Pflicht', 'pwMin' => 'Passwort-Mindestlänge', 'pwComplex' => 'Passwort-Komplexität', 'idleMinutes' => 'Abmeldung nach Inaktivität (Min.)',
                  'ipEnabled' => 'IP-Freigabe Eingabebereich', 'adminIps' => 'Freigegebene Adressen', 'lockAfter' => 'Kontosperre nach Fehlversuchen', 'lockMinutes' => 'Kontosperre (Min.)',
                  'geoEnabled' => 'Ländersperre', 'geoMode' => 'Ländersperre – Art', 'geoCountries' => 'Ländersperre – Länder', 'geoScope' => 'Ländersperre – gilt für',
                  'bestaetigungMinuten' => 'Passwortbestätigung gilt (Min.)'];
            $GV = ['block' => 'ausgewählte Länder sperren', 'allow' => 'nur ausgewählte Länder erlauben', 'admin' => 'nur Eingabebereich', 'all' => 'ganze Seite'];
            $fmt = function ($v) use ($GV) { return is_bool($v) ? ($v ? 'an' : 'aus') : (is_array($v) ? implode(', ', $v) : (string)($GV[$v] ?? $v)); };
            $d = [];
            foreach ($L as $k => $label) if ($fmt($old[$k] ?? null) !== $fmt($new[$k])) $d[] = ['k' => "sec|$k", 'code' => '', 'name' => 'Sicherheit', 'f' => $label, 'from' => $fmt($old[$k] ?? ''), 'to' => $fmt($new[$k])];
            $oldAus = (array)($old['bestaetigungAus'] ?? []);
            foreach (BESTAETIGUNG as $k => [, $label, $fest]) {
                $a = !in_array($k, $oldAus, true); $n = !in_array($k, $new['bestaetigungAus'], true);
                if (!$fest && $a !== $n) $d[] = ['k' => "sec|bst|$k", 'code' => '', 'name' => 'Sicherheit', 'f' => 'Passwortbestätigung: ' . $label, 'from' => $a ? 'verlangt' : 'nicht verlangt', 'to' => $n ? 'verlangt' : 'nicht verlangt'];
            }
            if ($d) audit('security', 'Sicherheitseinstellungen geändert', $d);
            respond(['ok' => true, 'settings' => $new]);
        }

        case 'geo_lookup': {
            require_auth(false, 'admin');
            $ip = trim((string)($_GET['ip'] ?? ''));
            if (filter_var($ip, FILTER_VALIDATE_IP) === false) fail('Keine gültige IP-Adresse.', 422);
            $priv = filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false;
            respond(['ok' => true, 'ip' => $ip, 'country' => geo_country($ip), 'private' => $priv]);
        }

        case 'geo_clear_stats': {
            require_admin_confirmation('geo_clear_stats');
            with_lock('laendersperre', function () { store_write('laendersperre', []); });
            respond(['ok' => true]);
        }

        case 'session_end': {
            $me = require_admin_confirmation('session_end');
            $b = body();
            $sid = (string)($b['sid'] ?? '');
            $uid = (string)($b['uid'] ?? '');
            $mine = (string)($_SESSION['sid'] ?? '');
            $who = '';
            $reg = store_read('sitzungen') ?? [];
            if ($sid !== '' && isset($reg[$sid])) $who = $reg[$sid]['uid'];
            $n = sess_remove(function ($k, $v) use ($sid, $uid, $mine) { return $k !== $mine && (($sid !== '' && $k === $sid) || ($uid !== '' && $v['uid'] === $uid)); });
            $users = users_load(); $un = ''; foreach ($users as $u) if ($u['id'] === ($uid ?: $who)) $un = $u['username'];
            if ($n) audit('security', $n === 1 ? "Sitzung von „{$un}“ beendet" : "{$n} Sitzungen von „{$un}“ beendet");
            respond(['ok' => true, 'ended' => $n]);
        }

        case 'ip_unblock': {
            require_admin_confirmation('ip_unblock');
            $key = (string)(body()['key'] ?? '');
            $ip = with_lock('logins', function () use ($key) {
                $a = store_read('logins') ?? [];
                $ip = $a[$key]['ip'] ?? null;
                unset($a[$key]);
                store_write('logins', $a);
                return $ip;
            });
            audit('security', 'IP-Sperre aufgehoben' . ($ip ? " ({$ip})" : ''));
            respond(['ok' => true]);
        }

        case 'geo_update': {
            require_admin_confirmation('geo_update');
            @set_time_limit(180);
            try { $r = geo_download($DATA . '/geo/laender.dat.php'); }
            catch (Throwable $e) { error_log('[wochenangebot] geo: ' . $e->getMessage()); fail('Die Länderdaten konnten nicht aktualisiert werden. Bitte später erneut versuchen.', 502); }
            audit('security', 'Länderdaten aktualisiert (Stand ' . $r['date'] . ')');
            respond(['ok' => true, 'geo' => geo_info()]);
        }

        case 'user_unlock': {
            require_admin_confirmation('user_unlock');
            $u = user_update((string)(body()['id'] ?? ''), function (&$x) { $x['lockedUntil'] = 0; $x['failCount'] = 0; });
            if (!$u) fail('Nutzer nicht gefunden.', 404);
            audit('security', "Zugang „{$u['username']}“ entsperrt");
            respond(['ok' => true]);
        }

        case 'users': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            respond(['ok' => true, 'users' => array_map('user_public', users_load())]);
        }

        /* Nutzerrechte: Rechte je Rolle und Übersicht je Nutzer (Administrator) */
        case 'rechte': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $roles = rights_roles();
            respond(['ok' => true, 'catalog' => rights_catalog(), 'roles' => $roles, 'adminOnly' => PERMS_ADMIN_ONLY, 'roleLabels' => ROLE_LABELS,
                     'custom' => store_read('rechte') !== null, 'updatedAt' => store_read('rechte')['updatedAt'] ?? null, 'updatedBy' => store_read('rechte')['updatedBy'] ?? '',
                     'users' => array_map(function ($u) use ($roles) { return ['id' => $u['id'], 'name' => $u['name'], 'username' => $u['username'], 'role' => $u['role'], 'active' => (bool)$u['active'],
                         'grant' => array_values((array)($u['grant'] ?? [])), 'deny' => array_values((array)($u['deny'] ?? [])), 'perms' => user_perms($u, $roles)]; }, users_load())]);
        }
        case 'rechte_save': {
            $me = require_admin_confirmation('rechte_save');
            $in = body()['roles'] ?? null;
            if (!is_array($in)) fail('Ungültige Anfrage.', 422);
            $old = rights_roles();
            $new = []; $d = [];
            foreach (PERM_ROLES as $r) {
                $new[$r] = is_array($in[$r] ?? null) ? rights_close(rights_clean($in[$r])) : $old[$r];
                $add = array_diff($new[$r], $old[$r]); $rem = array_diff($old[$r], $new[$r]);
                foreach ($add as $k) $d[] = ['k' => "r|$r|$k", 'code' => '', 'name' => ROLE_LABELS[$r], 'f' => PERMS[$k]['l'], 'from' => 'nein', 'to' => 'ja'];
                foreach ($rem as $k) $d[] = ['k' => "r|$r|$k", 'code' => '', 'name' => ROLE_LABELS[$r], 'f' => PERMS[$k]['l'], 'from' => 'ja', 'to' => 'nein'];
            }
            store_write('rechte', ['roles' => $new, 'updatedAt' => now(), 'updatedBy' => $me['name']]);
            if ($d) audit('user', 'Rechte der Rollen geändert', $d);
            respond(['ok' => true, 'roles' => $new]);
        }

        case 'user_save': {
            $me = require_admin_confirmation('user_save');
            $b = body();
            $res = with_lock('nutzer', function () use ($b, $me) {
                $users = users_load();
                $id = is_string($b['id'] ?? null) ? $b['id'] : '';
                $isNew = $id === '';
                $name = s($b['name'] ?? '', 80, false);
                if ($name === null) throw new InvalidArgumentException('Bitte einen Namen angeben.');
                $role = is_string($b['role'] ?? null) && isset(ROLES[$b['role']]) ? $b['role'] : null;
                if ($role === null) throw new InvalidArgumentException('Ungültige Rolle.');
                $active = !empty($b['active']);
                $pw = $b['password'] ?? '';
                $setPw = is_string($pw) && $pw !== '';
                // Abweichende Rechte (nur wenn mitgeschickt); verboten hat Vorrang
                $hasRights = array_key_exists('grant', $b) || array_key_exists('deny', $b);
                $deny = rights_clean(is_array($b['deny'] ?? null) ? $b['deny'] : []);
                $grant = array_values(array_diff(rights_clean(is_array($b['grant'] ?? null) ? $b['grant'] : []), $deny));
                $lbl = function (array $ks) { return implode(', ', array_map(function ($k) { return PERMS[$k]['l']; }, $ks)); };
                if ($isNew) {
                    $uname = clean_username($b['username'] ?? '');
                    foreach ($users as $u) if ($u['username'] === $uname) throw new InvalidArgumentException('Der Benutzername „' . $uname . '“ ist bereits vergeben.');
                    if (!$setPw) throw new InvalidArgumentException('Bitte ein Passwort für den neuen Nutzer festlegen.');
                    $u = ['id' => 'u' . bin2hex(random_bytes(6)), 'username' => $uname, 'name' => $name, 'role' => $role, 'active' => $active,
                          'hash' => password_hash(check_password($pw, $uname), PASSWORD_DEFAULT), 'mustChange' => !empty($b['mustChange']), 'sv' => 1,
                          'created' => now(), 'createdBy' => $me['username'], 'lastLogin' => null];
                    if ($hasRights && $role !== 'admin') { if ($grant) $u['grant'] = $grant; if ($deny) $u['deny'] = $deny; }
                    $users[] = $u;
                    users_save($users);
                    $d = [['k' => 'u|role', 'code' => '', 'name' => $uname, 'f' => 'Rolle', 'from' => '', 'to' => ROLE_LABELS[$role]]];
                    if (!$active) $d[] = ['k' => 'u|active', 'code' => '', 'name' => $uname, 'f' => 'Status', 'from' => '', 'to' => 'deaktiviert'];
                    if (!empty($u['grant'])) $d[] = ['k' => 'u|grant', 'code' => '', 'name' => $uname, 'f' => 'Zusätzlich erlaubt', 'from' => '', 'to' => $lbl($u['grant'])];
                    if (!empty($u['deny'])) $d[] = ['k' => 'u|deny', 'code' => '', 'name' => $uname, 'f' => 'Verboten', 'from' => '', 'to' => $lbl($u['deny'])];
                    return [$u, 'Nutzer „' . $uname . '“ (' . $name . ') angelegt', $d];
                }
                $i = user_find($users, $id);
                if ($i === null) fail('Nutzer nicht gefunden.', 404);
                $old = $users[$i];
                if ($id === $me['id'] && ($setPw || !empty($b['reset2fa']) || !empty($b['resetPasskeys']))) {
                    fail('Für den eigenen Zugang bitte „Passwort ändern“, „Zwei-Faktor-Anmeldung“ oder „Passkeys“ verwenden.', 403);
                }
                if ($id === $me['id'] && ($role !== $old['role'] || !$active)) throw new InvalidArgumentException('Die eigene Rolle und den eigenen Zugang können Sie nicht ändern.');
                $users[$i]['name'] = $name;
                $users[$i]['role'] = $role;
                $users[$i]['active'] = $active;
                if (active_admins($users) < 1) throw new InvalidArgumentException('Es muss mindestens ein aktiver Administrator bestehen bleiben.');
                $d = [];
                if ($old['name'] !== $name) $d[] = ['k' => 'u|name', 'code' => '', 'name' => $old['username'], 'f' => 'Name', 'from' => $old['name'], 'to' => $name];
                if ($old['role'] !== $role) $d[] = ['k' => 'u|role', 'code' => '', 'name' => $old['username'], 'f' => 'Rolle', 'from' => ROLE_LABELS[$old['role']], 'to' => ROLE_LABELS[$role]];
                if ($hasRights || $role === 'admin') {
                    $og = array_values((array)($old['grant'] ?? [])); $od = array_values((array)($old['deny'] ?? []));
                    if ($role === 'admin') { $grant = []; $deny = []; }
                    unset($users[$i]['grant'], $users[$i]['deny']);
                    if ($grant) $users[$i]['grant'] = $grant;
                    if ($deny) $users[$i]['deny'] = $deny;
                    if ($og != $grant) $d[] = ['k' => 'u|grant', 'code' => '', 'name' => $old['username'], 'f' => 'Zusätzlich erlaubt', 'from' => $lbl($og), 'to' => $lbl($grant)];
                    if ($od != $deny) $d[] = ['k' => 'u|deny', 'code' => '', 'name' => $old['username'], 'f' => 'Verboten', 'from' => $lbl($od), 'to' => $lbl($deny)];
                }
                if ((bool)$old['active'] !== $active) $d[] = ['k' => 'u|active', 'code' => '', 'name' => $old['username'], 'f' => 'Status', 'from' => $old['active'] ? 'aktiv' : 'deaktiviert', 'to' => $active ? 'aktiv' : 'deaktiviert'];
                if (!empty($b['reset2fa']) && !empty($old['totp'])) {
                    unset($users[$i]['totp'], $users[$i]['totpLast'], $users[$i]['recovery']);
                    $users[$i]['sv'] = (int)$users[$i]['sv'] + 1;
                    $d[] = ['k' => 'u|2fa', 'code' => '', 'name' => $old['username'], 'f' => 'Zwei-Faktor', 'from' => 'eingerichtet', 'to' => 'zurückgesetzt'];
                }
                if (!empty($b['resetPasskeys']) && has_passkeys($old)) {
                    unset($users[$i]['passkeys']);
                    $users[$i]['sv'] = (int)$users[$i]['sv'] + 1;
                    $n = count($old['passkeys']);
                    $d[] = ['k' => 'u|passkey', 'code' => '', 'name' => $old['username'], 'f' => 'Passkeys', 'from' => $n === 1 ? '1 Passkey' : "$n Passkeys", 'to' => 'alle entfernt'];
                }
                if ($setPw) {
                    $users[$i]['hash'] = password_hash(check_password($pw, $old['username']), PASSWORD_DEFAULT);
                    $users[$i]['mustChange'] = $id !== $me['id'] && !empty($b['mustChange']);
                    $users[$i]['sv'] = (int)$users[$i]['sv'] + 1;      // bestehende Sitzungen des Nutzers beenden
                    $d[] = ['k' => 'u|pw', 'code' => '', 'name' => $old['username'], 'f' => 'Passwort', 'from' => '', 'to' => 'neu gesetzt' . ($users[$i]['mustChange'] ? ' (muss beim Anmelden geändert werden)' : '')];
                }
                $users[$i]['changed'] = now();
                users_save($users);
                return [$users[$i], 'Nutzer „' . $old['username'] . '“ geändert', $d];
            });
            [$u, $msg, $d] = $res;
            if ($u['id'] === $me['id']) { $_SESSION['sv'] = (int)$u['sv']; }
            elseif ((int)$u['sv'] > 1 || empty($u['active'])) {
                $uid = $u['id']; $sv = (int)$u['sv'];
                if (empty($u['active']) || array_filter($d, function ($x) { return in_array($x['k'], ['u|pw', 'u|2fa', 'u|passkey'], true); })) sess_remove(function ($k, $v) use ($uid) { return $v['uid'] === $uid; });
            }
            if ($d) audit('user', $msg, $d);
            respond(['ok' => true, 'user' => user_public($u)]);
        }

        case 'user_delete': {
            $me = require_admin_confirmation('user_delete');
            $id = (string)(body()['id'] ?? '');
            $gone = with_lock('nutzer', function () use ($id, $me) {
                $users = users_load();
                $i = user_find($users, $id);
                if ($i === null) fail('Nutzer nicht gefunden.', 404);
                if ($id === $me['id']) throw new InvalidArgumentException('Den eigenen Zugang können Sie nicht löschen.');
                $u = $users[$i];
                array_splice($users, $i, 1);
                if (active_admins($users) < 1) throw new InvalidArgumentException('Es muss mindestens ein aktiver Administrator bestehen bleiben.');
                users_save($users);
                return $u;
            });
            sess_remove(function ($k, $v) use ($gone) { return $v['uid'] === $gone['id']; });
            audit('user', 'Nutzer „' . $gone['username'] . '“ (' . $gone['name'] . ') gelöscht');
            respond(['ok' => true]);
        }

        case 'log': {
            require_perm('protokoll.sehen');
            header('Cache-Control: no-store');
            $months = [];
            foreach (store_names('protokoll') as $f) {
                $m = basename($f);
                if (preg_match('/^\d{4}-\d{2}$/', $m)) $months[] = $m;
            }
            rsort($months);
            $month = (string)($_GET['month'] ?? '');
            if (!preg_match('/^\d{4}-\d{2}$/', $month)) $month = $months[0] ?? gmdate('Y-m');
            respond(['ok' => true, 'month' => $month, 'months' => $months, 'entries' => array_reverse(store_read('protokoll/' . $month) ?? [])]);
        }
}
