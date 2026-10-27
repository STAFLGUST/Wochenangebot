<?php
declare(strict_types=1);
/* Aktionen: Sicherheit, Länder-/IP-Sperre, Sitzungen (Oberfläche Modul Sicherheit), Betriebszustand, Nutzer, Protokoll
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
                $ips[] = ['key' => $k, 'ip' => $v['ip'] ?? 'unbekannt', 'n' => (int)($v['n'] ?? 0), 'until' => (int)($v['until'] ?? 0) > time() ? gmdate('Y-m-d\TH:i:s\Z', (int)$v['until']) : null, 't' => gmdate('Y-m-d\TH:i:s\Z', (int)($v['t'] ?? time())), 'bereich' => (string)($v['bereich'] ?? 'mitarbeiter')];
            }
            $fails = [];
            foreach ([utc_monat(), utc_monat(-1)] as $m) {
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
            respond(betrieb_daten($me) + ['ok' => true, 'settings' => sec(), 'bestaetigung' => bestaetigung_katalog(), 'bestaetigungMinuten' => BESTAETIGUNG_MINUTEN, 'myIp' => client_ip(), 'https' => is_https(),
                     'timeline' => sec_timeline($secLog), 'topIps' => sec_top_ips($secLog), 'config' => sec_config_checks($users),
                     'myCountry' => geo_country(client_ip()), 'geo' => geo_info(), 'geoCountries' => GEO_COUNTRIES, 'geoStats' => array_slice($gcc, 0, 30), 'geoBlocked7' => $g7,
                     'users' => array_map('user_public', $users), 'sessions' => $sess, 'blockedIps' => $ips,
                     'fails' => array_slice($fails, 0, 30), 'fails24' => $f24]);
        }

        /* Sicherheit → System (bis 27.10.2026 Verwaltung → System): Betriebszustand (Wartung, Sicherung, Bereitstellung,
           Speicher, Versand) – nur lesend. „nutzer“: Auswahl der Tester (Module und Freigaben) – nur Name, Benutzername,
           aktiv; die Liste der Mitarbeiter (Aktion users) gehört zur Verwaltung und ist auf diesem Host nicht erreichbar. */
        case 'betrieb_status': {
            $me = require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $nutzer = array_map(function ($u) { return ['id' => (string)$u['id'], 'name' => (string)$u['name'], 'username' => (string)$u['username'], 'active' => !empty($u['active'])]; }, users_load());
            respond(['ok' => true] + betrieb_daten($me) + ['nutzer' => array_values($nutzer)]);
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
            $new = sec_clean($b, $old, $me);
            store_write('sicherheit', $new);
            $GLOBALS['SEC'] = $new;
            $L = ['twofa' => 'Zwei-Faktor-Pflicht', 'pwMin' => 'Passwort-Mindestlänge', 'pwComplex' => 'Passwort-Komplexität', 'pwLeak' => 'Passwörter gegen Datenlecks prüfen', 'idleMinutes' => 'Abmeldung nach Inaktivität (Min.)',
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
            $treffer = function ($k, $v) use ($sid, $uid, $mine) { return $k !== $mine && (($sid !== '' && $k === $sid) || ($uid !== '' && $v['uid'] === $uid)); };
            // Zentrale Anmeldung: beendete Sitzungen merken, sonst entstünden sie beim nächsten Aufruf neu (lib/oidc.php).
            // Mit bekannter Keycloak-Sitzung genau diese, sonst – und bei „alle Sitzungen“ – alle des Mitarbeiters (nie die eigene).
            $kc = []; $alle = [];
            foreach ($reg as $k => $v) if ($treffer($k, $v)) { if (!empty($v['oidcSid'])) $kc[] = $v['oidcSid']; else $alle[] = $v['uid']; }
            if ($uid !== '') $alle[] = $uid;
            oidc_abmeldung_merken($kc, array_unique(array_filter($alle, fn($x) => $x !== $me['id'])));
            $n = sess_remove($treffer);
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
            $u = user_update((string)(body()['id'] ?? ''), function (&$x) { $x['lockedUntil'] = 0; $x['failCount'] = 0; unset($x['lockTries']); });
            if (!$u) fail('Mitarbeiter nicht gefunden.', 404);
            audit('security', "Zugang „{$u['username']}“ entsperrt");
            respond(['ok' => true]);
        }

        case 'users': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            respond(['ok' => true, 'users' => array_map('user_public', users_load()), 'twofaModus' => sec()['twofa']]);
        }

        /* Nutzerrechte: Rollen, Rechte je Rolle und Übersicht je Nutzer (Administrator) */
        case 'rechte': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $roles = rights_roles();
            $users = users_load();
            $d = store_read('rechte') ?? [];
            $labels = ROLE_LABELS; foreach (array_keys($roles) as $r) $labels[$r] = rolle_name($r);
            respond(['ok' => true, 'catalog' => rights_catalog(), 'roles' => $roles, 'adminOnly' => PERMS_ADMIN_ONLY, 'roleLabels' => $labels,
                     'rollen' => rollen_liste($roles, $users), 'module' => rechte_module(),
                     'custom' => store_read('rechte') !== null, 'updatedAt' => $d['updatedAt'] ?? null, 'updatedBy' => $d['updatedBy'] ?? '',
                     'users' => array_map(function ($u) use ($roles) { return ['id' => $u['id'], 'name' => $u['name'], 'username' => $u['username'], 'role' => $u['role'], 'rollen' => user_rollen($u), 'active' => (bool)$u['active'],
                         'grant' => array_values((array)($u['grant'] ?? [])), 'deny' => array_values((array)($u['deny'] ?? [])), 'perms' => user_perms($u, $roles)]; }, $users)]);
        }
        /* Rechte der Standardrollen (bisherige Oberfläche; die Rollenverwaltung nutzt rolle_save) */
        case 'rechte_save': {
            $me = require_admin_confirmation('rechte_save');
            $in = body()['roles'] ?? null;
            if (!is_array($in)) fail('Ungültige Anfrage.', 422);
            $old = rights_roles();
            $new = []; $d = [];
            $kat = perms_katalog();
            foreach (PERM_ROLES as $r) {
                $new[$r] = is_array($in[$r] ?? null) ? rights_clean($in[$r]) : $old[$r];
                // Ältere Oberfläche (noch geöffnete Seite) kennt den Modulzugang nicht: bisherigen Wert behalten statt ihn zu entziehen
                $istZugang = fn($k) => ($kat[$k]['k'] ?? '') === 'zugang';
                if (!array_filter($new[$r], $istZugang)) $new[$r] = array_merge($new[$r], array_filter($old[$r], $istZugang));
                $new[$r] = rights_close(array_values(array_unique($new[$r])));
                $add = array_diff($new[$r], $old[$r]); $rem = array_diff($old[$r], $new[$r]);
                foreach ($add as $k) $d[] = ['k' => "r|$r|$k", 'code' => '', 'name' => rolle_name($r), 'f' => $kat[$k]['l'], 'from' => 'nein', 'to' => 'ja'];
                foreach ($rem as $k) $d[] = ['k' => "r|$r|$k", 'code' => '', 'name' => rolle_name($r), 'f' => $kat[$k]['l'], 'from' => 'ja', 'to' => 'nein'];
            }
            store_write('rechte', ['roles' => $new, 'bekannt' => array_keys($kat), 'updatedAt' => now(), 'updatedBy' => $me['name']]);
            if ($d) audit('user', 'Rechte der Rollen geändert', $d);
            respond(['ok' => true, 'roles' => $new]);
        }
        /* Rolle anlegen oder ändern: Name, Beschreibung, Rechte (inkl. Modulzugang). Standardrollen: Name und Rechte,
           Administrator: fest. Neue Rolle optional als Kopie einer bestehenden (kopieVon). */
        case 'rolle_save': {
            $me = require_admin_confirmation('rechte_save');
            $b = body();
            $id = is_string($b['id'] ?? null) ? $b['id'] : '';
            if ($id === 'admin') fail('Die Rolle „Administrator“ hat immer alle Rechte und kann nicht geändert werden.', 422);
            $res = with_lock('rollen', function () use ($b, $id, $me) {
                $dok = rollen_dok(true);
                $eigene = rollen_eigene();
                $alt = rights_roles();
                $kat = perms_katalog();
                $name = s($b['name'] ?? null, 40, false);
                if ($name === null || mb_strlen($name) < 2) throw new InvalidArgumentException('Bitte einen Namen für die Rolle angeben (mindestens 2 Zeichen).');
                $besch = s($b['beschreibung'] ?? '', 160) ?? '';
                $neu = $id === '';
                if (!$neu && !in_array($id, PERM_ROLES, true) && !isset($eigene[$id])) fail('Rolle nicht gefunden.', 404);
                foreach (array_merge(['admin'], PERM_ROLES, array_keys($eigene)) as $r) {
                    if ($r !== $id && mb_strtolower(rolle_name($r)) === mb_strtolower($name)) throw new InvalidArgumentException('Eine Rolle mit dem Namen „' . $name . '“ gibt es bereits.');
                }
                $quelle = is_string($b['kopieVon'] ?? null) ? $b['kopieVon'] : '';
                if (is_array($b['rechte'] ?? null)) $rechte = rights_close(rights_clean($b['rechte']));
                elseif ($neu && $quelle !== '' && rolle_existiert($quelle)) $rechte = $quelle === 'admin' ? array_keys($kat) : ($alt[$quelle] ?? []);
                elseif (!$neu) $rechte = $alt[$id];
                else $rechte = [];
                if ($neu) { do { $id = 'r' . bin2hex(random_bytes(4)); } while (isset($eigene[$id])); }
                $vorher = $neu ? [] : $alt[$id];
                $altName = $neu ? '' : rolle_name($id);
                $d = [];
                if ($altName !== $name) $d[] = ['k' => "rolle|$id|name", 'code' => '', 'name' => $name, 'f' => 'Name', 'from' => $altName, 'to' => $name];
                foreach (array_diff($rechte, $vorher) as $k) $d[] = ['k' => "r|$id|$k", 'code' => '', 'name' => $name, 'f' => $kat[$k]['l'], 'from' => 'nein', 'to' => 'ja'];
                foreach (array_diff($vorher, $rechte) as $k) $d[] = ['k' => "r|$id|$k", 'code' => '', 'name' => $name, 'f' => $kat[$k]['l'], 'from' => 'ja', 'to' => 'nein'];
                if (in_array($id, PERM_ROLES, true)) {
                    // Standardrolle: Rechte im Dokument „rechte“ (wie bisher, ältere Fassungen lesen sie weiter), Name im Dokument „rollen“
                    $roles = []; foreach (PERM_ROLES as $r) $roles[$r] = $r === $id ? $rechte : $alt[$r];
                    store_write('rechte', ['roles' => $roles, 'bekannt' => array_keys($kat), 'updatedAt' => now(), 'updatedBy' => $me['name']]);
                    $namen = is_array($dok['namen'] ?? null) ? $dok['namen'] : [];
                    if ($name === ROLE_LABELS[$id]) unset($namen[$id]); else $namen[$id] = $name;
                    $dok['namen'] = $namen;
                } else {
                    $e = is_array($dok['eigene'] ?? null) ? $dok['eigene'] : [];
                    $e[$id] = ['name' => $name, 'beschreibung' => $besch, 'rechte' => $rechte,
                               'erstellt' => $e[$id]['erstellt'] ?? now(), 'von' => $e[$id]['von'] ?? $me['name'], 'geaendert' => now(), 'geaendertVon' => $me['name']];
                    $dok['eigene'] = $e;
                }
                store_write('rollen', $dok);
                rollen_dok(true);
                return [$id, $name, $neu, $d];
            });
            [$id, $name, $neu, $d] = $res;
            audit('user', $neu ? "Rolle „{$name}“ angelegt" : "Rolle „{$name}“ geändert", $d);
            respond(['ok' => true, 'id' => $id, 'rollen' => rollen_liste()]);
        }
        /* Eigene Rolle löschen – nur, wenn kein Mitarbeiter sie mehr hat (sonst verlöre er stillschweigend Rechte) */
        case 'rolle_loeschen': {
            $me = require_admin_confirmation('rechte_save');
            $id = (string)(body()['id'] ?? '');
            if ($id === 'admin' || in_array($id, PERM_ROLES, true)) fail('Standardrollen können nicht gelöscht werden.', 422);
            $name = with_lock('rollen', function () use ($id) {
                $dok = rollen_dok(true);
                if (!isset(rollen_eigene()[$id])) fail('Rolle nicht gefunden.', 404);
                $mit = array_values(array_filter(users_load(), fn($u) => in_array($id, user_rollen($u), true)));
                if ($mit) throw new InvalidArgumentException('Die Rolle ist noch ' . (count($mit) === 1 ? '1 Mitarbeiter' : count($mit) . ' Mitarbeitern') . ' zugeordnet ('
                    . implode(', ', array_slice(array_column($mit, 'name'), 0, 5)) . (count($mit) > 5 ? ' …' : '') . '). Bitte zuerst dort eine andere Rolle wählen.');
                $name = rolle_name($id);
                unset($dok['eigene'][$id]);
                store_write('rollen', $dok);
                rollen_dok(true);
                return $name;
            });
            audit('user', "Rolle „{$name}“ gelöscht", [['k' => "rolle|$id|name", 'code' => '', 'name' => $name, 'f' => 'Rolle', 'from' => $name, 'to' => '']]);
            respond(['ok' => true, 'rollen' => rollen_liste()]);
        }

        case 'user_save': {
            $me = require_admin_confirmation('user_save');
            $b = body();
            pw_datenleck_vorab($b['password'] ?? null);
            $res = with_lock('nutzer', function () use ($b, $me) {
                $users = users_load();
                $id = is_string($b['id'] ?? null) ? $b['id'] : '';
                $isNew = $id === '';
                $id = is_string($b['id'] ?? null) ? $b['id'] : '';
                $person = nutzer_person($b, $id === '');
                $name = $person['name'];
                // Rollen: „rollen“ (Liste, neue Oberfläche) oder „role“ (eine Rolle, ältere Oberfläche). Administrator nur allein.
                $weitere = null;
                if (is_array($b['rollen'] ?? null)) {
                    $liste = array_values(array_unique(array_filter($b['rollen'], fn($x) => is_string($x) && $x !== '')));
                    foreach ($liste as $r) if (!rolle_existiert($r)) throw new InvalidArgumentException('Ungültige Rolle.');
                    if (!$liste) throw new InvalidArgumentException('Bitte mindestens eine Rolle wählen.');
                    if (in_array('admin', $liste, true)) { $role = 'admin'; $weitere = []; }
                    else {
                        // Hauptrolle bevorzugt eine Standardrolle: ältere Fassungen (Rückfall) kennen nur diese – nie mehr Rechte als hier
                        $std = array_values(array_intersect($liste, PERM_ROLES));
                        $role = $std[0] ?? $liste[0];
                        $weitere = array_values(array_diff($liste, [$role]));
                    }
                } else {
                    $role = is_string($b['role'] ?? null) && rolle_existiert($b['role']) ? $b['role'] : null;
                    if ($role === null) throw new InvalidArgumentException('Ungültige Rolle.');
                }
                // Mitarbeiter ohne Anmeldung (z. B. Lager, nur Urlaubsplanung): immer deaktiviert, kein Passwort nötig
                $zugang = !array_key_exists('zugang', $b) || !empty($b['zugang']);
                $active = $zugang && !empty($b['active']);
                if (!$zugang) { $role = 'viewer'; $weitere = []; }   // ohne Anmeldung keine Rechte; beim Einrichten der Anmeldung neu wählen
                $pw = $zugang ? ($b['password'] ?? '') : '';
                $setPw = is_string($pw) && $pw !== '';
                // Zentrale Anmeldung (Keycloak-Host): es gibt nur noch das Passwort von Keycloak – gesetzt über „Zentrale Anmeldung“
                // im Mitarbeiter (anmeldekonto_aendern). Das alte Passwort der Anwendung gilt nur noch im Notzugang (deploy/notzugang.sh).
                if ($setPw && oidc_modus()) throw new InvalidArgumentException('Passwörter setzt die zentrale Anmeldung: im Mitarbeiter unter „Zentrale Anmeldung“ → „Passwort setzen“.');
                // Abweichende Rechte (nur wenn mitgeschickt); verboten hat Vorrang
                $hasRights = array_key_exists('grant', $b) || array_key_exists('deny', $b);
                $deny = rights_clean(is_array($b['deny'] ?? null) ? $b['deny'] : []);
                $grant = array_values(array_diff(rights_clean(is_array($b['grant'] ?? null) ? $b['grant'] : []), $deny));
                $lbl = function (array $ks) { return implode(', ', array_map(function ($k) { return perms_katalog()[$k]['l'] ?? $k; }, $ks)); };
                // Zwei-Faktor-Pflicht je Nutzer (optional; ohne Angabe – ältere Oberfläche – bleibt sie unverändert)
                $hasPflicht = array_key_exists('twofaPflicht', $b);
                $pflicht = !empty($b['twofaPflicht']);
                if ($isNew) {
                    $wunsch = trim((string)($b['username'] ?? ''));
                    if ($wunsch === '' && $person['vorname'] !== '') $wunsch = benutzername_vorschlag($person['vorname'], $person['nachname'], array_column($users, 'username'));
                    $uname = clean_username($wunsch);
                    foreach ($users as $u) if ($u['username'] === $uname) throw new InvalidArgumentException('Der Benutzername „' . $uname . '“ ist bereits vergeben.');
                    if (!$setPw && $zugang && !oidc_modus()) throw new InvalidArgumentException('Bitte ein Passwort für den neuen Mitarbeiter festlegen.');
                    $u = ['id' => 'u' . bin2hex(random_bytes(6)), 'username' => $uname, 'name' => $name, 'role' => $role, 'active' => $active,
                          'hash' => password_hash($setPw ? check_password($pw, $uname) : bin2hex(random_bytes(24)), PASSWORD_DEFAULT), 'mustChange' => $setPw && !empty($b['mustChange']), 'sv' => 1,
                          'created' => now(), 'createdBy' => $me['username'], 'lastLogin' => null];
                    if (!$zugang) { $u['zugang'] = false; $pflicht = false; }
                    foreach (['vorname', 'nachname', 'email'] as $f) if ($person[$f] !== '') $u[$f] = $person[$f];
                    if ($pflicht) $u['twofaPflicht'] = true;
                    if ($hasRights && $role !== 'admin') { if ($grant) $u['grant'] = $grant; if ($deny) $u['deny'] = $deny; }
                    if ($weitere) $u['rollen'] = $weitere;
                    $users[] = $u;
                    users_save($users);
                    $d = [['k' => 'u|role', 'code' => '', 'name' => $uname, 'f' => 'Rolle', 'from' => '', 'to' => rollen_text($u)]];
                    if (!$active) $d[] = ['k' => 'u|active', 'code' => '', 'name' => $uname, 'f' => 'Status', 'from' => '', 'to' => 'deaktiviert'];
                    if ($person['email'] !== '') $d[] = ['k' => 'u|email', 'code' => '', 'name' => $uname, 'f' => 'E-Mail', 'from' => '', 'to' => $person['email']];
                    if (!empty($u['grant'])) $d[] = ['k' => 'u|grant', 'code' => '', 'name' => $uname, 'f' => 'Zusätzlich erlaubt', 'from' => '', 'to' => $lbl($u['grant'])];
                    if (!empty($u['deny'])) $d[] = ['k' => 'u|deny', 'code' => '', 'name' => $uname, 'f' => 'Verboten', 'from' => '', 'to' => $lbl($u['deny'])];
                    if ($pflicht) $d[] = ['k' => 'u|2fapflicht', 'code' => '', 'name' => $uname, 'f' => 'Zwei-Faktor-Pflicht', 'from' => '', 'to' => 'ja'];
                    return [$u, 'Mitarbeiter „' . $uname . '“ (' . $name . ') ' . ($zugang ? 'angelegt' : 'ohne Anmeldung angelegt'), $d];
                }
                $i = user_find($users, $id);
                if ($i === null) fail('Mitarbeiter nicht gefunden.', 404);
                $old = $users[$i];
                if ($id === $me['id'] && !$zugang) throw new InvalidArgumentException('Den eigenen Zugang können Sie nicht entfernen.');
                // Anmeldung neu einrichten: nur mit neuem Passwort (das bisherige ist unbrauchbar)
                if ($zugang && !nutzer_hat_zugang($old) && !$setPw && !oidc_modus()) throw new InvalidArgumentException('Für die Anmeldung bitte ein Passwort festlegen.');
                if ($id === $me['id'] && ($setPw || !empty($b['reset2fa']) || !empty($b['resetPasskeys']))) {
                    fail('Für den eigenen Zugang bitte „Passwort ändern“, „Zwei-Faktor-Anmeldung“ oder „Passkeys“ verwenden.', 403);
                }
                $vergleich = function (string $r, ?array $w, array $alt): array {
                    $l = $r === 'admin' ? ['admin'] : array_merge([$r], $w ?? array_map('strval', (array)($alt['rollen'] ?? [])));
                    $l = array_values(array_unique($l)); sort($l); return $l;
                };
                $altRollen = user_rollen($old); sort($altRollen);
                if ($id === $me['id'] && ($vergleich($role, $weitere, $old) != $altRollen || !$active)) throw new InvalidArgumentException('Die eigene Rolle und den eigenen Zugang können Sie nicht ändern.');
                if ($id === $me['id'] && $hasPflicht && $pflicht !== !empty($old['twofaPflicht'])) fail('Die Zwei-Faktor-Pflicht des eigenen Zugangs kann nur ein anderer Administrator ändern.', 403);
                $users[$i]['name'] = $name;
                foreach (['vorname', 'nachname', 'email'] as $f) {
                    if ($f !== 'email' && $person['vorname'] === '' && $person['nachname'] === '') continue;   // ältere Oberfläche: nur „name“
                    if (!array_key_exists($f, $b) && $f === 'email') continue;
                    if ($person[$f] !== '') $users[$i][$f] = $person[$f]; else unset($users[$i][$f]);
                }
                $users[$i]['role'] = $role;
                if ($weitere !== null || $role === 'admin') { if ($weitere && $role !== 'admin') $users[$i]['rollen'] = $weitere; else unset($users[$i]['rollen']); }
                $users[$i]['active'] = $active;
                if ($zugang) unset($users[$i]['zugang']); else { $users[$i]['zugang'] = false; $users[$i]['mustChange'] = false; }
                if (active_admins($users) < 1) throw new InvalidArgumentException('Es muss mindestens ein aktiver Administrator bestehen bleiben.');
                $d = [];
                if ($old['name'] !== $name) $d[] = ['k' => 'u|name', 'code' => '', 'name' => $old['username'], 'f' => 'Name', 'from' => $old['name'], 'to' => $name];
                if ((string)($old['email'] ?? '') !== (string)($users[$i]['email'] ?? '')) $d[] = ['k' => 'u|email', 'code' => '', 'name' => $old['username'], 'f' => 'E-Mail', 'from' => (string)($old['email'] ?? ''), 'to' => (string)($users[$i]['email'] ?? '')];
                if (rollen_text($old) !== rollen_text($users[$i])) $d[] = ['k' => 'u|role', 'code' => '', 'name' => $old['username'], 'f' => 'Rolle', 'from' => rollen_text($old), 'to' => rollen_text($users[$i])];
                if ($hasRights || $role === 'admin') {
                    $og = array_values((array)($old['grant'] ?? [])); $od = array_values((array)($old['deny'] ?? []));
                    if ($role === 'admin') { $grant = []; $deny = []; }
                    unset($users[$i]['grant'], $users[$i]['deny']);
                    if ($grant) $users[$i]['grant'] = $grant;
                    if ($deny) $users[$i]['deny'] = $deny;
                    if ($og != $grant) $d[] = ['k' => 'u|grant', 'code' => '', 'name' => $old['username'], 'f' => 'Zusätzlich erlaubt', 'from' => $lbl($og), 'to' => $lbl($grant)];
                    if ($od != $deny) $d[] = ['k' => 'u|deny', 'code' => '', 'name' => $old['username'], 'f' => 'Verboten', 'from' => $lbl($od), 'to' => $lbl($deny)];
                }
                if ($hasPflicht && $pflicht !== !empty($old['twofaPflicht'])) {
                    if ($pflicht) $users[$i]['twofaPflicht'] = true; else unset($users[$i]['twofaPflicht']);
                    $d[] = ['k' => 'u|2fapflicht', 'code' => '', 'name' => $old['username'], 'f' => 'Zwei-Faktor-Pflicht', 'from' => $pflicht ? 'nein' : 'ja', 'to' => $pflicht ? 'ja' : 'nein'];
                }
                if (nutzer_hat_zugang($old) !== $zugang) $d[] = ['k' => 'u|zugang', 'code' => '', 'name' => $old['username'], 'f' => 'Anmeldung', 'from' => $zugang ? 'ohne' : 'mit', 'to' => $zugang ? 'mit' : 'ohne'];
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
                if (!empty($b['resetGeraete']) && geraete_gueltig($old)) {
                    $n = count(geraete_gueltig($old));
                    geraete_zuruecksetzen($users[$i], true);
                    $d[] = ['k' => 'u|geraete', 'code' => '', 'name' => $old['username'], 'f' => 'Vertraute Geräte', 'from' => $n === 1 ? '1 Gerät' : "$n Geräte", 'to' => 'alle entfernt'];
                }
                if ($setPw) {
                    $users[$i]['hash'] = password_hash(check_password($pw, $old['username']), PASSWORD_DEFAULT);
                    $users[$i]['mustChange'] = $id !== $me['id'] && !empty($b['mustChange']);
                    unset($users[$i]['mustChangeGrund']);
                    $users[$i]['sv'] = (int)$users[$i]['sv'] + 1;      // bestehende Sitzungen des Nutzers beenden
                    geraete_zuruecksetzen($users[$i], true);            // neues Passwort: kein Gerät mehr vertraut
                    $d[] = ['k' => 'u|pw', 'code' => '', 'name' => $old['username'], 'f' => 'Passwort', 'from' => '', 'to' => 'neu gesetzt' . ($users[$i]['mustChange'] ? ' (muss beim Anmelden geändert werden)' : '')];
                }
                $users[$i]['changed'] = now();
                users_save($users);
                return [$users[$i], 'Mitarbeiter „' . $old['username'] . '“ geändert', $d];
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

        case 'user_mail': {   // Zugangsdaten per E-Mail an den Mitarbeiter (optional mit Startpasswort)
            $me = require_admin_confirmation('user_mail');
            $cfg = require_mail();
            $b = body();
            $users = users_load();
            $i = user_find($users, (string)($b['id'] ?? ''));
            if ($i === null) fail('Mitarbeiter nicht gefunden.', 404);
            $u = $users[$i];
            if (empty($u['email'])) fail('Für diesen Mitarbeiter ist keine E-Mail-Adresse hinterlegt.', 422);
            if (empty($u['active'])) fail('Der Zugang ist deaktiviert – bitte zuerst aktivieren.', 422);
            $pw = $b['password'] ?? null;
            $startPw = null;
            if (is_string($pw) && $pw !== '') {
                if (empty($u['mustChange'])) fail('Ein Startpasswort wird nur mitgesendet, wenn der Mitarbeiter es bei der ersten Anmeldung ändern muss.', 422);
                if (!password_verify($pw, (string)$u['hash'])) fail('Das Startpasswort passt nicht zum gespeicherten Passwort.', 422);
                $startPw = $pw;
            }
            $note = mb_substr(trim(str_replace("\r", '', (string)($b['note'] ?? ''))), 0, 1000);
            [$sub, $txt, $html] = mail_tpl_nutzer($u, $startPw, $note);
            @set_time_limit(60);
            $r = mail_send_many($cfg, ['x' => ['to' => $u['email'], 'name' => $u['name'], 'subject' => $sub, 'text' => $txt, 'html' => $html]])['x'];
            $info = ['t' => now(), 'to' => $u['email'], 'by' => $me['username'], 'ok' => $r['ok'], 'mitPasswort' => $startPw !== null];
            $u = with_lock('nutzer', function () use ($u, $info) {
                $users = users_load();
                $i = user_find($users, $u['id']);
                if ($i === null) return $u;
                $users[$i]['mailInfo'] = $info;
                users_save($users);
                return $users[$i];
            });
            mail_record([['kid' => '', 'firma' => $u['name'] . ' (Mitarbeiter)', 'to' => $info['to'], 'typ' => 'zugang', 'ok' => $r['ok'], 'error' => $r['error'] ?? '']]);
            audit('user', 'Zugangsdaten an „' . $u['username'] . '“ (' . $info['to'] . ') ' . ($startPw !== null ? 'mit Startpasswort ' : '') . ($r['ok'] ? 'per E-Mail versendet' : 'nicht zugestellt: ' . ($r['error'] ?? '')));
            if (!$r['ok']) fail('Die E-Mail konnte nicht zugestellt werden: ' . ($r['error'] ?? 'unbekannter Fehler'), 502);
            respond(['ok' => true, 'user' => user_public($u)]);
        }

        case 'user_delete': {
            $me = require_admin_confirmation('user_delete');
            $id = (string)(body()['id'] ?? '');
            $gone = with_lock('nutzer', function () use ($id, $me) {
                $users = users_load();
                $i = user_find($users, $id);
                if ($i === null) fail('Mitarbeiter nicht gefunden.', 404);
                if ($id === $me['id']) throw new InvalidArgumentException('Den eigenen Zugang können Sie nicht löschen.');
                $u = $users[$i];
                array_splice($users, $i, 1);
                if (active_admins($users) < 1) throw new InvalidArgumentException('Es muss mindestens ein aktiver Administrator bestehen bleiben.');
                users_save($users);
                return $u;
            });
            sess_remove(function ($k, $v) use ($gone) { return $v['uid'] === $gone['id']; });
            audit('user', 'Mitarbeiter „' . $gone['username'] . '“ (' . $gone['name'] . ') gelöscht');
            respond(['ok' => true]);
        }

        case 'log': {
            $me = require_perm('protokoll.sehen');
            header('Cache-Control: no-store');
            $months = protokoll_monate();   // nur aufbewahrte Monate (PROTOKOLL_MONATE)
            $month = (string)($_GET['month'] ?? '');
            if (!preg_match('/^\d{4}-\d{2}$/', $month) || $month < protokoll_grenze()) $month = $months[0] ?? gmdate('Y-m');
            $entries = array_reverse(store_read('protokoll/' . $month) ?? []);
            // Ohne Recht „Kunden ansehen“: Einträge mit Kundendaten (Adressen, E-Mails, Bestellungen, Kunden-IP) nur als Vorgang zeigen
            if (!may($me, 'kunden.sehen')) {
                foreach ($entries as &$e) {
                    if (($e['r'] ?? '') === 'kunde' || in_array($e['a'] ?? '', LOG_KUNDENDATEN, true)) {
                        $e['s'] = LOG_KUNDENDATEN_TEXT[$e['a']] ?? 'Vorgang mit Kundendaten';
                        unset($e['d']);
                        $e['ip'] = '';
                        if (($e['r'] ?? '') === 'kunde') { $e['u'] = 'kunde'; $e['n'] = 'Kunde'; }
                        $e['masked'] = true;
                    }
                }
                unset($e);
            }
            // Ohne Recht „HR verwalten“: Vorgänge der Urlaubsverwaltung (Namen, Zeiträume von Abwesenheiten) nur als Vorgang zeigen –
            // aus Name und Zeitraum ließe sich auf Krankheit schließen (Gesundheitsdaten)
            if (!may($me, 'hr.verwalten')) {
                foreach ($entries as &$e) {
                    if (($e['a'] ?? '') !== 'hr') continue;
                    $e['s'] = 'Vorgang der Urlaubsverwaltung';
                    unset($e['d']);
                    $e['masked'] = true;
                }
                unset($e);
            }
            respond(['ok' => true, 'month' => $month, 'months' => $months, 'aufbewahrung' => PROTOKOLL_MONATE, 'entries' => $entries]);
        }
}
