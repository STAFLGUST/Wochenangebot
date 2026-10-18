<?php
declare(strict_types=1);
/* Aktionen: Kunden auf der Angebotsseite: Anmeldung, Passwort-Links, Bestellwunsch, Merkliste, Abmelden
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        /* ---------- Kunden-Anmeldung (Angebotsseite) ---------- */
        case 'kunde_status': {
            header('Cache-Control: no-store');
            start_session();
            $k = current_customer();
            $staff = current_user() !== null;
            respond(['ok' => true, 'stdPublic' => std_public(), 'staff' => $staff, 'kunde' => $k ? kunde_payload($k) : null, 'bestellung' => $k ? order_enabled() : false, 'wartung' => wartung(), 'csrf' => $k ? ($_SESSION['kcsrf'] ?? null) : null]);
        }

        case 'kunde_login': {
            start_session();
            attempts_check();
            $b = body();
            $name = is_string($b['username'] ?? null) ? strtolower(trim($b['username'])) : '';
            $pw = (string)($b['password'] ?? '');
            $res = with_lock('kunden', function () use ($name, $pw) {
                $d = customers_load();
                foreach ($d['customers'] as $i => $c) {
                    $l = $c['login'] ?? null;
                    if (!$l || $name === '' || $l['username'] !== $name) continue;
                    if ((int)($l['lockedUntil'] ?? 0) > time()) { password_verify($pw, (string)$l['hash']); return ['locked', $c]; }
                    if (!password_verify($pw, (string)$l['hash'])) {
                        $lockedNow = login_failure($d['customers'][$i]['login']);
                        store_write('kunden', $d);
                        return [$lockedNow ? 'lockednow' : 'bad', $d['customers'][$i]];
                    }
                    if (empty($c['active']) || empty($l['active'])) return ['inactive', $c];
                    if (password_needs_rehash((string)$l['hash'], PASSWORD_DEFAULT)) $d['customers'][$i]['login']['hash'] = password_hash($pw, PASSWORD_DEFAULT);
                    $d['customers'][$i]['login']['failCount'] = 0;
                    $d['customers'][$i]['login']['lockedUntil'] = 0;
                    $d['customers'][$i]['login']['lastLogin'] = now();
                    store_write('kunden', $d);
                    return ['ok', $d['customers'][$i]];
                }
                password_verify($pw, '$2y$10$y80WR5wtxxV9G3NpBGQXmeL3EYKIGKm4gaElkDTK2cWFQtjyZdoPa'); // gleiche Laufzeit
                return ['bad', null];
            });
            [$st, $c] = $res;
            $who = ['username' => 'kunde:' . mb_substr($name, 0, 40), 'name' => $c['firma'] ?? '', 'role' => 'kunde'];
            if ($st !== 'ok') {
                attempts_record(false);
                $why = ['inactive' => ' – Zugang deaktiviert', 'locked' => ' – Zugang gesperrt', 'lockednow' => ' – Zugang nach zu vielen Fehlversuchen gesperrt', 'bad' => ''][$st];
                audit('kunde_login_fail', 'Kunden-Anmeldung fehlgeschlagen' . ($name !== '' ? ' (Benutzername „' . mb_substr($name, 0, 40) . '“)' : '') . $why, [], $who);
                usleep(400000);
                if ($st === 'inactive') fail('Dieser Zugang ist deaktiviert. Bitte wenden Sie sich an Ihren Ansprechpartner.', 401);
                if ($st === 'locked' || $st === 'lockednow') fail('Dieser Zugang ist wegen zu vieler Fehlversuche vorübergehend gesperrt. Bitte später erneut versuchen.', 429);
                fail('Benutzername oder Passwort ist nicht korrekt.', 401);
            }
            attempts_record(true);
            kunde_sign_in($c);
            audit('kunde_login', 'Kunde angemeldet', [], $who);
            respond(['ok' => true, 'csrf' => $_SESSION['kcsrf'], 'kunde' => kunde_payload($c)]);
        }

        case 'kunde_logout': {
            start_session();
            if (current_customer()) {
                require_customer_csrf();
                $sid = (string)($_SESSION['ksid'] ?? '');
                ksess_remove(function ($k) use ($sid) { return $k === $sid; });
            }
            kunde_clear();
            respond(['ok' => true]);
        }

        case 'kunde_passwort': {
            $c = current_customer();
            if (!$c) fail('Bitte erneut anmelden.', 401);
            require_customer_csrf();
            $b = body();
            if (!password_verify((string)($b['current'] ?? ''), (string)$c['login']['hash'])) fail('Das bisherige Passwort ist nicht korrekt.', 422);
            $new = check_password($b['password'] ?? '', $c['login']['username']);
            if (password_verify($new, (string)$c['login']['hash'])) fail('Bitte ein anderes als das bisherige Passwort wählen.', 422);
            $c2 = with_lock('kunden', function () use ($c, $new) {
                $d = customers_load();
                foreach ($d['customers'] as $i => $x) if ($x['id'] === $c['id']) {
                    $d['customers'][$i]['login']['hash'] = password_hash($new, PASSWORD_DEFAULT);
                    $d['customers'][$i]['login']['mustChange'] = false;
                    $d['customers'][$i]['login']['pwSet'] = now();
                    $d['customers'][$i]['login']['sv'] = (int)($x['login']['sv'] ?? 0) + 1;
                    unset($d['customers'][$i]['login']['token']);
                    store_write('kunden', $d);
                    return $d['customers'][$i];
                }
                return null;
            });
            if (!$c2) fail('Zugang nicht gefunden.', 404);
            $_SESSION['ksv'] = (int)$c2['login']['sv'];
            $sid = (string)($_SESSION['ksid'] ?? '');
            ksess_remove(function ($k, $v) use ($c2, $sid) { return $v['kid'] === $c2['id'] && $k !== $sid; });   // andere Geräte abmelden
            $GLOBALS['KUNDE'] = $c2;
            audit('kunde_password', 'Kunde hat eigenes Passwort festgelegt', [], ['username' => 'kunde:' . $c2['login']['username'], 'name' => $c2['firma'], 'role' => 'kunde']);
            respond(['ok' => true, 'kunde' => kunde_payload($c2)]);
        }

        /* ---------- Passwort über Link aus der E-Mail (Einladung / Zurücksetzen) ---------- */
        case 'kunde_token_check': {
            attempts_check();
            $c = kunde_by_token((string)(body()['token'] ?? ''));
            if (!$c) { attempts_record(false); fail('Dieser Link ist abgelaufen oder wurde bereits verwendet. Bitte fordern Sie bei uns einen neuen an.', 410); }
            respond(['ok' => true, 'firma' => $c['firma'], 'username' => $c['login']['username'], 'purpose' => $c['login']['token']['p'], 'exp' => (int)$c['login']['token']['exp']]);
        }

        case 'kunde_token_set': {
            start_session();
            attempts_check();
            $b = body();
            $tok = (string)($b['token'] ?? '');
            $c = kunde_by_token($tok);
            if (!$c) { attempts_record(false); fail('Dieser Link ist abgelaufen oder wurde bereits verwendet. Bitte fordern Sie bei uns einen neuen an.', 410); }
            $new = check_password($b['password'] ?? '', $c['login']['username']);
            $c2 = with_lock('kunden', function () use ($c, $new, $tok) {
                $d = customers_load();
                foreach ($d['customers'] as $i => $x) if ($x['id'] === $c['id']) {
                    $t = $x['login']['token'] ?? null;
                    if (!$t || !hash_equals((string)$t['h'], hash('sha256', $tok)) || (int)$t['exp'] <= time()) return null;   // inzwischen verbraucht
                    $l = &$d['customers'][$i]['login'];
                    $l['hash'] = password_hash($new, PASSWORD_DEFAULT);
                    $l['mustChange'] = false; $l['pwSet'] = now(); $l['sv'] = (int)($l['sv'] ?? 0) + 1;
                    $l['failCount'] = 0; $l['lockedUntil'] = 0; $l['lastLogin'] = now();
                    unset($l['token']);
                    store_write('kunden', $d);
                    return $d['customers'][$i];
                }
                return null;
            });
            if (!$c2) fail('Dieser Link ist abgelaufen oder wurde bereits verwendet. Bitte fordern Sie bei uns einen neuen an.', 410);
            attempts_record(true);
            ksess_remove(function ($k, $v) use ($c2) { return $v['kid'] === $c2['id']; });
            kunde_sign_in($c2);
            audit('kunde_password', 'Kunde hat Passwort über den Link aus der E-Mail festgelegt', [], ['username' => 'kunde:' . $c2['login']['username'], 'name' => $c2['firma'], 'role' => 'kunde']);
            respond(['ok' => true, 'csrf' => $_SESSION['kcsrf'], 'kunde' => kunde_payload($c2)]);
        }

        /* ---------- Bestellwunsch aus dem Portal ---------- */
        case 'kunde_bestellung': {
            $c = current_customer();
            if (!$c) fail('Bitte erneut anmelden.', 401);
            require_customer_csrf();
            if (!empty($c['login']['mustChange'])) fail('Bitte zuerst ein eigenes Passwort festlegen.', 403);
            if (!order_enabled()) fail('Bestellungen über das Portal sind derzeit nicht möglich. Bitte wenden Sie sich direkt an uns.', 409);
            $b = body();
            $key = (string)($b['requestId'] ?? '');
            if ($key !== '' && !preg_match('/^[A-Za-z0-9_-]{16,80}$/D', $key)) fail('Ungültige Übermittlungskennung.', 422);
            $hash = order_request_hash($b);
            with_lock('bestellungen', function () use ($c, $key, $hash) { order_replay(store_read('bestellungen') ?? [], $c['id'], $key, $hash); });
            $oid = (string)($b['angebot'] ?? OFFER_STD);
            if ($oid === '') $oid = OFFER_STD;
            $def = offer_def($oid);
            if (!$def || !(in_array($oid, customer_offers($c), true) || ($oid === OFFER_STD && std_public()))) fail('Für dieses Angebot ist Ihr Zugang nicht freigeschaltet.', 403);
            $pub = store_read('angebot');
            if (!$pub) fail('Es ist kein Angebot veröffentlicht.', 409);
            if ((string)($b['publishedAt'] ?? '') !== (string)($pub['publishedAt'] ?? $pub['savedAt'] ?? '')) fail('Das Angebot wurde inzwischen aktualisiert. Bitte prüfen Sie Ihren Bestellwunsch mit den aktuellen Preisen und senden Sie ihn erneut.', 409);
            $off = offer_resolve($pub, $def);
            $byId = []; foreach ($off['items'] as $it) $byId[$it['id']] = $it;
            $gName = []; foreach ($off['groups'] ?? [] as $g) $gName[$g['id']] = $g['name'];
            $in = is_array($b['positions'] ?? null) ? $b['positions'] : [];
            if (!$in) fail('Bitte mindestens eine Menge eingeben.', 422);
            if (count($in) > 300) fail('Zu viele Positionen in einem Bestellwunsch (höchstens 300).', 422);
            $pos = []; $seen = []; $total = 0.0; $qtyT = 0.0; $req = 0;
            foreach ($in as $p) {
                $id = is_array($p) ? (string)($p['id'] ?? '') : '';
                $q = is_array($p) && is_numeric($p['qty'] ?? null) ? round((float)$p['qty'], 2) : 0.0;
                if ($id === '' || isset($seen[$id])) continue;
                if (!isset($byId[$id])) fail('Ein Artikel Ihres Bestellwunsches ist im aktuellen Angebot nicht mehr enthalten. Bitte Seite neu laden und prüfen.', 409);
                if ($q <= 0 || $q > 99999) fail('Bitte nur Mengen zwischen 0,01 und 99.999 kg eingeben.', 422);
                $seen[$id] = true;
                $it = $byId[$id];
                $price = ($it['price']['status'] ?? '') === 'value' ? (float)$it['price']['value'] : null;
                $sum = $price !== null ? round(round($price * 100) * $q) / 100 : null;   // in Cent rechnen (wie die Anzeige im Portal)
                if ($sum !== null) $total += $sum; else $req++;
                $qtyT += $q;
                $pos[] = ['id' => $id, 'code' => (string)($it['code'] ?? ''), 'name' => (string)$it['name'] . (!empty($it['sale']) ? ' (Sonderposten)' : ''), 'group' => $gName[$it['groupId'] ?? ''] ?? '', 'qty' => $q, 'price' => $price, 'sum' => $sum];
            }
            if (!$pos) fail('Bitte mindestens eine Menge eingeben.', 422);
            $termin = (string)($b['termin'] ?? '');
            if ($termin !== '') {
                $d = DateTimeImmutable::createFromFormat('!Y-m-d', $termin);
                if (!$d || $d->format('Y-m-d') !== $termin || $termin < date('Y-m-d') || $termin > date('Y-m-d', strtotime('+120 days'))) fail('Bitte ein gültiges Wunschdatum (heute bis in 4 Monaten) wählen.', 422);
            }
            $ref = s($b['referenz'] ?? '', 60) ?? '';
            $bem = mb_substr(trim(str_replace("\r", '', preg_replace('/[\x00-\x08\x0b-\x1f]/u', '', (string)($b['bemerkung'] ?? '')) ?? '')), 0, 1000);
            // Missbrauchsschutz: höchstens 30 Bestellwünsche je Kunde und Tag
            $recent = array_filter(store_read('bestellungen') ?? [], function ($x) use ($c) { return ($x['kid'] ?? '') === $c['id'] && strtotime($x['t']) > time() - 86400; });
            if (count($recent) >= 30) fail('Heute wurden bereits sehr viele Bestellwünsche gesendet. Bitte wenden Sie sich direkt an uns.', 429);
            $o = with_lock('bestellungen', function () use ($c, $def, $off, $pos, $total, $qtyT, $req, $termin, $ref, $bem, $key, $hash) {
                $all = store_read('bestellungen') ?? [];
                order_replay($all, $c['id'], $key, $hash);
                if (count(array_filter($all, fn($x) => ($x['kid'] ?? '') === $c['id'] && strtotime($x['t']) > time() - 86400)) >= 30) fail('Heute wurden bereits sehr viele Bestellwünsche gesendet.', 429);
                $y = date('Y'); $n = 0;
                foreach ($all as $x) if (strpos($x['nr'], "B-$y-") === 0) $n = max($n, (int)substr($x['nr'], 7));
                $o = ['nr' => sprintf('B-%s-%04d', $y, $n + 1), 't' => now(), 'kid' => $c['id'], 'firma' => $c['firma'], 'angebot' => $def['id'], 'angebotName' => $def['name'],
                      'week' => (int)($off['meta']['week'] ?? 0), 'year' => (int)($off['meta']['year'] ?? 0), 'positions' => $pos, 'total' => round($total, 2), 'totalQty' => round($qtyT, 2),
                      'onRequest' => $req, 'termin' => $termin, 'referenz' => $ref, 'bemerkung' => $bem, 'status' => 'neu', 'workflow' => 'neu', 'revision' => 1, 'requestId' => $key, 'requestHash' => $hash];
                $o['kunde'] = array_intersect_key($c, array_flip(['firma','nr','ansprechpartner','strasse','plz','ort','email','telefon']));
                $o['kunde']['username'] = $c['login']['username'];
                $o['outbox'] = order_outbox_create($o);
                $all[] = $o;
                store_write('bestellungen', $all);
                return $o;
            });
            try { $o = order_outbox_send($o['nr']); } catch (RuntimeException $e) { $o['status'] = 'fehler'; }   // Bestellung ist gespeichert; Versand bleibt als offener Auftrag sichtbar
            $okIn = ($o['status'] ?? '') === 'gesendet';
            $who = ['username' => 'kunde:' . $c['login']['username'], 'name' => $c['firma'], 'role' => 'kunde'];
            audit('bestellung', "Bestellwunsch {$o['nr']} ({$def['name']}, " . count($pos) . ' Positionen, ' . de_qty($o['totalQty']) . ' kg)' . ($okIn ? '' : ' – E-Mail nicht zugestellt'),
                array_map(function ($p) { return ['k' => 'b|' . $p['id'], 'code' => $p['code'], 'name' => $p['name'], 'f' => 'Menge', 'from' => '', 'to' => de_qty($p['qty']) . ' kg' . ($p['price'] !== null ? ' × ' . de_num($p['price']) . ' €' : ' (Preis auf Anfrage)')]; }, $pos), $who);
            if (!$okIn) fail('Ihr Bestellwunsch wurde gespeichert, die E-Mail konnte aber nicht bestätigt werden. Bitte nicht als neuen Bestellwunsch erneut eingeben. Unser Team kann den Versand prüfen.', 502);
            order_receipt($o);
        }

        case 'bestell_settings_save': {
            $me = require_admin_confirmation();
            $b = body();
            $raw = is_array($b['to'] ?? null) ? implode(',', $b['to']) : (string)($b['to'] ?? '');
            $to = [];
            foreach (preg_split('/[\s,;]+/', $raw) as $a) {
                if ($a === '') continue;
                if (filter_var($a, FILTER_VALIDATE_EMAIL) === false) fail("„" . mb_substr($a, 0, 80) . "“ ist keine gültige E-Mail-Adresse.", 422);
                $to[strtolower($a)] = $a;
            }
            $to = array_values($to);
            if (count($to) > 5) fail('Höchstens 5 Empfänger für Bestellwünsche.', 422);
            $en = !empty($b['enabled']);
            if ($en && !$to) fail('Bitte mindestens eine Adresse angeben, an die Bestellwünsche gehen.', 422);
            $old = order_settings();
            $new = ['enabled' => $en, 'to' => $to, 'copy' => !empty($b['copy']), 'updatedAt' => now(), 'updatedBy' => $me['name']];
            store_write('bestellung', $new);
            $ch = [];
            if ($old['enabled'] !== $en) $ch[] = ['k' => 'best|en', 'code' => '', 'name' => 'Bestellungen', 'f' => 'Bestellfunktion', 'from' => $old['enabled'] ? 'an' : 'aus', 'to' => $en ? 'an' : 'aus'];
            if (implode(', ', $old['to']) !== implode(', ', $to)) $ch[] = ['k' => 'best|to', 'code' => '', 'name' => 'Bestellungen', 'f' => 'Empfänger', 'from' => implode(', ', $old['to']), 'to' => implode(', ', $to)];
            if ($old['copy'] !== $new['copy']) $ch[] = ['k' => 'best|copy', 'code' => '', 'name' => 'Bestellungen', 'f' => 'Kopie an Kunden', 'from' => $old['copy'] ? 'ja' : 'nein', 'to' => $new['copy'] ? 'ja' : 'nein'];
            if ($ch) audit('mail', 'Einstellungen für Bestellwünsche geändert', $ch);
            respond(['ok' => true, 'orders' => order_settings(), 'active' => order_enabled()]);
        }

        /* ---------- Merkliste je Kunde (geräteübergreifend) ---------- */
        case 'kunde_merkliste': {
            header('Cache-Control: private, no-store');
            $c = current_customer();
            if (!$c) fail('Bitte anmelden.', 401);
            $m = (store_read('merklisten') ?? [])[$c['id']] ?? null;
            respond(['ok' => true, 'keys' => $m['keys'] ?? [], 'savedAt' => $m['t'] ?? null, 'exists' => $m !== null]);
        }

        case 'kunde_merkliste_save': {
            $c = current_customer();
            if (!$c) fail('Bitte erneut anmelden.', 401);
            require_customer_csrf();
            $in = body()['keys'] ?? null;
            if (!is_array($in)) fail('Ungültige Merkliste.', 422);
            $keys = [];
            foreach ($in as $k) {
                if (!is_string($k) || $k === '' || mb_strlen($k) > 200 || preg_match('/[\x00-\x1f]/', $k)) continue;
                $keys[$k] = true;
                if (count($keys) >= 1000) break;
            }
            $keys = array_keys($keys);
            with_lock('merklisten', function () use ($c, $keys) {
                $all = store_read('merklisten') ?? [];
                $all[$c['id']] = ['keys' => $keys, 't' => now()];
                store_write('merklisten', $all);
            });
            respond(['ok' => true, 'count' => count($keys)]);
        }

        /* ---------- Abmelden vom Wochenangebot (Link aus der E-Mail, ohne Anmeldung) ---------- */
        case 'kunde_abmelden_info': {
            attempts_check();
            $c = abmelde_kunde((string)(body()['token'] ?? ''));
            if (!$c) { attempts_record(false); fail('Dieser Abmeldelink ist ungültig. Bitte wenden Sie sich direkt an uns.', 404); }
            $e = (string)($c['email'] ?? '');
            $masked = $e !== '' ? preg_replace('/^(.).*?(@.*)$/u', '$1•••$2', $e) : '';
            respond(['ok' => true, 'firma' => $c['firma'], 'email' => $masked, 'subscribed' => !array_key_exists('mailAngebot', $c) || !empty($c['mailAngebot']), 'company' => $CFG['company']]);
        }

        case 'kunde_abmelden': {
            attempts_check();
            $b = body();
            $c = abmelde_kunde((string)($b['token'] ?? ''));
            if (!$c) { attempts_record(false); fail('Dieser Abmeldelink ist ungültig. Bitte wenden Sie sich direkt an uns.', 404); }
            $ab = empty($b['wieder']);
            if (abmelde_setzen($c, $ab, 'link')) abmelde_melden($c, $ab, 'link');
            respond(['ok' => true, 'subscribed' => !$ab]);
        }

        case 'abmelden1': {
            // Ein-Klick-Abmeldung (RFC 8058): das E-Mail-Programm sendet POST mit „List-Unsubscribe=One-Click“
            if ($method !== 'POST') fail('Bitte den Abmeldelink in der E-Mail verwenden.', 405);
            attempts_check();
            $c = abmelde_kunde((string)($_GET['t'] ?? ''));
            if (!$c) { attempts_record(false); fail('Ungültiger Abmeldelink.', 404); }
            if (abmelde_setzen($c, true, '1klick')) abmelde_melden($c, true, '1klick');
            respond(['ok' => true]);
        }
}
