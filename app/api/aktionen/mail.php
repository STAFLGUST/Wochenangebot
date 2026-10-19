<?php
declare(strict_types=1);
/* Aktionen: E-Mail-Versand (Administrator)
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        /* ---------- E-Mail-Versand (nur Administrator) ---------- */
        case 'mail_status': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $m = mail_cfg();
            $last = array_slice(store_read('mailversand') ?? [], -200);
            respond(['ok' => true, 'configured' => (bool)$m && (bool)mail_base_url(), 'baseUrl' => mail_base_url(),
                     'smtp' => $m ? ['host' => $m['host'], 'port' => $m['port'], 'secure' => $m['secure'], 'user' => $m['user'], 'from' => $m['from'], 'fromName' => $m['fromName'], 'replyTo' => $m['replyTo'], 'password' => $m['pass'] !== '', 'passError' => $m['passError'], 'source' => $m['source']] : null,
                     'account' => ($a = mail_account()) ? ['host' => $a['host'], 'port' => (int)$a['port'], 'secure' => $a['secure'], 'user' => $a['user'] ?? '', 'from' => $a['from'], 'fromName' => $a['fromName'] ?? '', 'replyTo' => $a['replyTo'] ?? '', 'password' => !empty($a['passEnc']), 'updatedAt' => $a['updatedAt'] ?? null, 'updatedBy' => $a['updatedBy'] ?? ''] : null,
                     'envConfigured' => env_str('MAIL_SMTP_HOST') !== '' && env_str('MAIL_FROM') !== '', 'orders' => order_settings(), 'notify' => notify_view(), 'sodium' => function_exists('sodium_crypto_secretbox'),
                     'signature' => mail_settings()['signature'], 'week' => mail_week(), 'log' => array_reverse($last), 'testumgebung' => testumgebung()]);
        }

        /* Benachrichtigungen an Mitarbeiter: je Ereignis an/aus und Empfänger (Administrator, mit Passwortbestätigung) */
        case 'benachrichtigung_save': {
            $me = require_admin_confirmation();
            $in = body()['events'] ?? null;
            if (!is_array($in)) fail('Ungültige Anfrage.', 422);
            $old = notify_settings()['events'];
            $new = []; $ch = [];
            foreach (NOTIFY_EVENTS as $k => $def) {
                $e = $in[$k] ?? null;
                if (!is_array($e)) { $new[$k] = $old[$k]; continue; }
                $to = notify_parse_to($e['to'] ?? '', $def['label']);
                $on = $def['fest'] ? $old[$k]['on'] : (!empty($def['manuell']) || !empty($e['on']));
                if ($def['fest'] && $on && !$to) fail('Die Bestellfunktion ist eingeschaltet – für neue Bestellwünsche wird mindestens eine Adresse gebraucht.', 422);
                if (!$def['fest'] && empty($def['ersatz']) && empty($def['manuell']) && $on && !$to) fail("„{$def['label']}“: Bitte mindestens eine Adresse angeben oder die Benachrichtigung ausschalten.", 422);
                $new[$k] = ['on' => $on, 'to' => $to];
                if ($old[$k]['on'] !== $on) $ch[] = ['k' => "notify|{$k}|on", 'code' => '', 'name' => $def['label'], 'f' => 'Benachrichtigung', 'from' => $old[$k]['on'] ? 'an' : 'aus', 'to' => $on ? 'an' : 'aus'];
                if (implode(', ', $old[$k]['to']) !== implode(', ', $to)) $ch[] = ['k' => "notify|{$k}|to", 'code' => '', 'name' => $def['label'], 'f' => 'Empfänger', 'from' => implode(', ', $old[$k]['to']), 'to' => implode(', ', $to)];
            }
            if ($new['bestellung']['to'] !== $old['bestellung']['to']) {   // Empfänger der Bestellwünsche liegen bei der Bestellfunktion
                $o = store_read('bestellung');
                $o = is_array($o) ? $o : [];
                $o['to'] = $new['bestellung']['to']; $o['updatedAt'] = now(); $o['updatedBy'] = $me['name'];
                store_write('bestellung', $o);
            }
            $ev = [];
            foreach ($new as $k => $e) if (!NOTIFY_EVENTS[$k]['fest']) $ev[$k] = $e;
            store_write('benachrichtigungen', ['events' => $ev, 'updatedAt' => now(), 'updatedBy' => $me['name']]);
            if ($ch) audit('mail', 'Benachrichtigungen geändert', $ch);
            respond(['ok' => true, 'notify' => notify_view(), 'orders' => order_settings(), 'active' => order_enabled()]);
        }
        case 'benachrichtigung_test': {
            $me = require_auth(true, 'admin');
            $ev = (string)(body()['event'] ?? '');
            if (!isset(NOTIFY_EVENTS[$ev])) fail('Unbekanntes Ereignis.', 422);
            require_mail();
            $to = notify_targets($ev, true);
            if (!$to) fail('Für dieses Ereignis sind noch keine Empfänger gespeichert.', 422);
            $items = [['ev' => $ev, 'title' => 'Test: ' . NOTIFY_EVENTS[$ev]['label'], 'facts' => [['Ausgelöst von', $me['name']]], 't' => now()]];
            respond(['ok' => true, 'results' => notify_send($ev, $to, $items, 0, true, $me['name'])]);
        }

        /* Testumgebung: abgelegte E-Mails ansehen (Administrator) */
        case 'testpostfach': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            if (!testumgebung()) fail('Nur in der Testumgebung verfügbar.', 404);
            $l = array_reverse(store_read('testpostfach') ?? []);
            if (isset($_GET['i'])) { $m = $l[(int)$_GET['i']] ?? null; if (!$m) fail('Nachricht nicht gefunden.', 404); respond(['ok' => true, 'mail' => $m]); }
            respond(['ok' => true, 'mails' => array_map(function ($m) { return ['t' => $m['t'], 'to' => $m['to'], 'subject' => $m['subject']]; }, $l)]);
        }

        case 'mail_konto_save': {
            $me = require_admin_confirmation();
            $b = body();
            $old = mail_account();
            if (!empty($b['remove'])) {
                if ($old) { store_write('mailkonto', ['removed' => now()]); audit('mail', 'Postfach-Einstellungen entfernt', [['k' => 'mail|konto', 'code' => '', 'name' => 'E-Mail', 'f' => 'Postfach', 'from' => $old['user'] . ' @ ' . $old['host'], 'to' => 'entfernt']]); }
                respond(['ok' => true]);
            }
            $host = strtolower(trim((string)($b['host'] ?? '')));
            if (!preg_match('/^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$/', $host)) fail('Bitte einen gültigen Mailserver angeben (z. B. smtp.hostinger.com).', 422);
            $secure = in_array($b['secure'] ?? '', ['ssl', 'starttls', 'none'], true) ? $b['secure'] : 'ssl';
            if ($secure === 'none' && !in_array($host, ['127.0.0.1', 'localhost'], true)) fail('Unverschlüsselter Versand ist nur an einen Server auf demselben Rechner erlaubt. Bitte SSL oder STARTTLS wählen.', 422);
            $port = (int)($b['port'] ?? 0);
            if ($port < 1 || $port > 65535) fail('Bitte einen gültigen Port angeben (meist 465 für SSL oder 587 für STARTTLS).', 422);
            $user = mail_clean_header(mb_substr((string)($b['user'] ?? ''), 0, 160));
            $from = trim((string)($b['from'] ?? ''));
            if (filter_var($from, FILTER_VALIDATE_EMAIL) === false) fail('Bitte eine gültige Absenderadresse angeben.', 422);
            $reply = trim((string)($b['replyTo'] ?? ''));
            if ($reply !== '' && filter_var($reply, FILTER_VALIDATE_EMAIL) === false) fail('Die Antwortadresse ist ungültig.', 422);
            $name = mb_substr(mail_clean_header((string)($b['fromName'] ?? '')), 0, 80);
            $pw = (string)($b['password'] ?? '');
            if (strlen($pw) > 500) fail('Das Passwort ist zu lang.', 422);
            $same = $old && $old['host'] === $host && (int)$old['port'] === $port && ($old['user'] ?? '') === $user && $old['secure'] === $secure;
            if ($pw === '') {
                // Das gespeicherte Passwort wird nur an denselben Server/Benutzer weiterverwendet – nie an einen geänderten Server
                if (!$same && $user !== '') fail('Bei neuem oder geändertem Server, Port, Verschlüsselung oder Benutzer bitte das Passwort des Postfachs (erneut) eingeben.', 422);
                $enc = $same ? (string)($old['passEnc'] ?? '') : '';
            } else {
                try { $enc = mail_encrypt($pw); } catch (RuntimeException $e) { fail($e->getMessage(), 500); }
            }
            $new = ['host' => $host, 'port' => $port, 'secure' => $secure, 'user' => $user, 'passEnc' => $enc, 'from' => $from, 'fromName' => $name, 'replyTo' => $reply, 'updatedAt' => now(), 'updatedBy' => $me['name']];
            store_write('mailkonto', $new);
            $ch = [];
            foreach (['host' => 'Mailserver', 'port' => 'Port', 'secure' => 'Verschlüsselung', 'user' => 'Benutzer', 'from' => 'Absenderadresse', 'fromName' => 'Absendername', 'replyTo' => 'Antwortadresse'] as $f => $lab) {
                $from0 = $old ? (string)($old[$f] ?? '') : ''; $to0 = (string)$new[$f];
                if ($from0 !== $to0) $ch[] = ['k' => "mail|$f", 'code' => '', 'name' => 'E-Mail', 'f' => $lab, 'from' => $from0, 'to' => $to0];
            }
            if ($pw !== '') $ch[] = ['k' => 'mail|pw', 'code' => '', 'name' => 'E-Mail', 'f' => 'Passwort', 'from' => '', 'to' => 'neu gesetzt'];
            if ($ch) audit('mail', $old ? 'Postfach-Einstellungen geändert' : 'Postfach für den E-Mail-Versand eingerichtet', $ch);
            // Verbindung und Anmeldung gleich prüfen (ohne E-Mail zu senden)
            $conn = ['ok' => true];
            try { $t = new Smtp(mail_cfg()); $t->open(); $t->close(); } catch (RuntimeException $e) { $conn = ['ok' => false, 'error' => $e->getMessage()]; }
            respond(['ok' => true, 'connection' => $conn]);
        }

        case 'mail_save': {
            require_admin_confirmation();
            $sig = (string)(body()['signature'] ?? '');
            $sig = mb_substr(trim(str_replace("\r", '', preg_replace('/[\x00-\x08\x0b-\x1f]/u', '', $sig) ?? '')), 0, 600);
            $old = mail_settings()['signature'];
            store_write('mailvorlage', ['signature' => $sig, 'updatedAt' => now()]);
            if ($old !== $sig) audit('mail', 'E-Mail-Signatur geändert', [['k' => 'mail|sig', 'code' => '', 'name' => 'E-Mail', 'f' => 'Signatur', 'from' => $old, 'to' => $sig]]);
            respond(['ok' => true, 'signature' => $sig]);
        }

        case 'mail_test': {
            $me = require_admin_confirmation();
            $cfg = require_mail();
            $to = trim((string)(body()['to'] ?? ''));
            if (filter_var($to, FILTER_VALIDATE_EMAIL) === false) fail('Bitte eine gültige E-Mail-Adresse angeben.', 422);
            $sub = 'Testnachricht aus dem Angebotsportal';
            $txt = "Diese Testnachricht bestätigt, dass der E-Mail-Versand des Angebotsportals funktioniert.

Ausgelöst von: {$me['name']}
";
            $html = mail_layout($sub, '<p style="margin:0 0 14px;">Diese Testnachricht bestätigt, dass der E-Mail-Versand des Angebotsportals funktioniert.</p><p style="margin:0;color:#857c72;font-size:13px;">Ausgelöst von: ' . mail_h($me['name']) . '</p>', mail_settings()['signature'], '');
            $r = mail_send_many($cfg, [['to' => $to, 'name' => '', 'subject' => $sub, 'text' => $txt, 'html' => $html]])[0];
            with_lock('mailversand', function () use ($to, $r, $me) {
                $l = store_read('mailversand') ?? [];
                $l[] = ['t' => now(), 'typ' => 'test', 'kid' => '', 'firma' => '', 'to' => $to, 'ok' => $r['ok'], 'error' => $r['error'] ?? '', 'by' => $me['name']];
                store_write('mailversand', array_slice($l, -3000));
            });
            if (!$r['ok']) fail('Testmail nicht versendet: ' . $r['error'], 502);
            respond(['ok' => true]);
        }

        case 'kunden_mail_vorschau': {
            require_auth(true, 'admin');
            $b = body();
            $typ = in_array($b['type'] ?? '', ['woche', 'angebot', 'invite', 'reset', 'restposten'], true) ? $b['type'] : 'woche';
            $c = null;
            foreach (customers_load()['customers'] as $x) if ($x['id'] === ($b['id'] ?? '')) $c = $x;
            if (!$c) $c = ['firma' => 'Musterkunde GmbH', 'ansprechpartner' => 'Frau Muster', 'email' => 'kunde@example.org', 'angebote' => [OFFER_STD], 'login' => ['username' => 'musterkunde']];
            if (!mail_base_url()) fail('Die Adresse der Angebotsseite für Links fehlt (DOMAIN bzw. WA_URL in .env).', 409);
            if ($typ === 'restposten') {
                $def = offer_def((string)($b['offer'] ?? ''));
                if (!$def) fail('Angebot nicht gefunden.', 404);
                [$sub, , $html] = mail_tpl_restposten($c, $def, restposten_items($def), mb_substr(trim((string)($b['note'] ?? '')), 0, 1000));
            } elseif ($typ === 'invite' || $typ === 'reset') [$sub, , $html] = mail_tpl_zugang($c, mail_base_url() . '/#zugang=BEISPIEL', $typ, time() + 86400 * TOKEN_DAYS[$typ]);
            else [$sub, , $html] = mail_tpl_angebot($c, mb_substr(trim((string)($b['note'] ?? '')), 0, 1000), mail_week());
            respond(['ok' => true, 'subject' => $sub, 'html' => $html, 'to' => $c['email'] ?? '']);
        }

        case 'kunde_mail': {
            require_admin_confirmation();
            $cfg = require_mail();
            $b = body();
            $c = null;
            foreach (customers_load()['customers'] as $x) if ($x['id'] === ($b['id'] ?? '')) $c = $x;
            if (!$c) fail('Kunde nicht gefunden.', 404);
            if (empty($c['email'])) fail("Für „{$c['firma']}“ ist keine E-Mail-Adresse hinterlegt.", 422);
            if (empty($c['active'])) fail('Der Kunde ist inaktiv.', 422);
            $type = $b['type'] ?? '';
            if ($type === 'zugang') {
                if (empty($c['login'])) fail('Für diesen Kunden ist kein Zugang eingerichtet.', 422);
                if (empty($c['login']['active'])) fail('Der Zugang ist deaktiviert.', 422);
                $purpose = empty($c['login']['hash']) ? 'invite' : 'reset';
                [$tok, $exp, $c] = kunde_token_new($c['id'], $purpose);
                [$sub, $txt, $html] = mail_tpl_zugang($c, mail_base_url() . '/#zugang=' . $tok, $purpose, $exp);
                $job = ['to' => $c['email'], 'name' => $c['ansprechpartner'] ?: $c['firma'], 'subject' => $sub, 'text' => $txt, 'html' => $html];
                $typ = $purpose;
            } elseif ($type === 'angebot') {
                if (!customer_offers($c)) fail('Für diesen Kunden ist kein Angebot freigeschaltet.', 422);
                if (array_key_exists('mailAngebot', $c) && empty($c['mailAngebot'])) fail(!empty($c['abgemeldet']) ? "„{$c['firma']}“ hat sich vom Wochenangebot per E-Mail abgemeldet – es werden keine Angebotsmails mehr gesendet." : "Für „{$c['firma']}“ ist das Wochenangebot per E-Mail ausgeschaltet.", 422);
                $job = mail_job_for($c, 'angebot', mb_substr(trim((string)($b['note'] ?? '')), 0, 1000), mail_week());
                $typ = 'angebot';
            } else fail('Unbekannte E-Mail-Art.', 422);
            $r = mail_send_many($cfg, [$job])[0];
            if (!$r['ok'] && isset($tok)) with_lock('kunden', function () use ($c) {   // Link nicht zugestellt → ungültig machen
                $d = customers_load();
                foreach ($d['customers'] as $i => $x) if ($x['id'] === $c['id']) unset($d['customers'][$i]['login']['token']);
                store_write('kunden', $d);
            });
            mail_record([['kid' => $c['id'], 'firma' => $c['firma'], 'to' => $c['email'], 'typ' => $typ, 'ok' => $r['ok'], 'error' => $r['error'] ?? '']]);
            audit('mail', MAIL_TYP[$typ] . " an „{$c['firma']}“ " . ($r['ok'] ? 'gesendet' : 'nicht zugestellt'), [['k' => "c{$c['id']}|mail", 'code' => $c['nr'] ?? '', 'name' => $c['firma'], 'f' => MAIL_TYP[$typ], 'from' => '', 'to' => $c['email'] . ($r['ok'] ? '' : ' – Fehler: ' . $r['error'])]]);
            if (!$r['ok']) fail('E-Mail nicht versendet: ' . $r['error'], 502);
            respond(['ok' => true, 'typ' => $typ, 'customer' => customer_public(array_values(array_filter(customers_load()['customers'], function ($x) use ($c) { return $x['id'] === $c['id']; }))[0])]);
        }

        case 'kunden_rundmail': {
            require_admin_confirmation();
            $cfg = require_mail();
            $b = body();
            $wk = mail_week();
            if (!$wk) fail('Es ist noch kein Angebot veröffentlicht.', 409);
            if ((int)($b['week'] ?? 0) !== $wk['week'] || (int)($b['year'] ?? 0) !== $wk['year']) fail('Inzwischen wurde ein anderes Angebot veröffentlicht. Bitte den Versand neu öffnen.', 409);
            $ids = array_slice(array_values(array_filter(is_array($b['ids'] ?? null) ? $b['ids'] : [], 'is_string')), 0, 20);
            $note = mb_substr(trim((string)($b['note'] ?? '')), 0, 1000);
            $jobs = []; $res = []; $map = [];
            foreach (customers_load()['customers'] as $c) {
                if (!in_array($c['id'], $ids, true)) continue;
                $map[$c['id']] = $c;
                $why = empty($c['active']) ? 'Kunde inaktiv' : (empty($c['email']) ? 'keine E-Mail-Adresse' : (empty($c['login']['active']) ? 'kein aktiver Zugang' : (!customer_offers($c) ? 'kein Angebot freigeschaltet' : (array_key_exists('mailAngebot', $c) && empty($c['mailAngebot']) ? (!empty($c['abgemeldet']) ? 'hat sich vom Wochenangebot abgemeldet' : 'Wochenangebot per E-Mail nicht gewünscht') : ''))));
                if ($why !== '') { $res[$c['id']] = ['ok' => false, 'error' => $why, 'skipped' => true]; continue; }
                $jobs[$c['id']] = mail_job_for($c, 'woche', $note, $wk);
            }
            @set_time_limit(180);
            ignore_user_abort(true);
            $res = $res + ($jobs ? mail_send_many($cfg, $jobs) : []);
            $entries = [];
            foreach ($res as $id => $r) if (empty($r['skipped'])) $entries[] = ['kid' => $id, 'firma' => $map[$id]['firma'], 'to' => $map[$id]['email'], 'typ' => 'woche', 'ok' => $r['ok'], 'error' => $r['error'] ?? ''];
            if ($entries) mail_record($entries, $wk);
            $okN = count(array_filter($res, function ($r) { return $r['ok']; }));
            $bad = array_filter($res, function ($r) { return !$r['ok']; });
            if ($res) audit('mail', "Wochenangebot KW {$wk['week']}/{$wk['year']} an $okN Kunden versendet" . ($bad ? ' (' . count($bad) . ' nicht zugestellt)' : ''),
                array_map(function ($id) use ($res, $map) { $r = $res[$id]; return ['k' => "c$id|woche", 'code' => $map[$id]['nr'] ?? '', 'name' => $map[$id]['firma'], 'f' => 'Wochenangebot', 'from' => '', 'to' => ($map[$id]['email'] ?? '') . ($r['ok'] ? '' : ' – ' . $r['error'])]; }, array_keys($res)));
            $out = [];
            foreach ($ids as $id) $out[] = ['id' => $id] + ($res[$id] ?? ['ok' => false, 'error' => 'Kunde nicht gefunden']);
            respond(['ok' => true, 'results' => $out]);
        }

        /* ---------- Sonderposten eines Angebots per E-Mail (nur an die Kunden dieses Angebots) ---------- */
        case 'restposten_info': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $def = offer_def((string)($_GET['offer'] ?? ''));
            if (!$def) fail('Angebot nicht gefunden.', 404);
            $pub = store_read('angebot');
            $items = array_map(function ($it) { return ['id' => $it['id'], 'code' => $it['code'] ?? '', 'name' => $it['name'], 'price' => (float)$it['price']['value'], 'regular' => $it['regular'] ?? null]; }, restposten_items($def));
            $rec = [];
            foreach (customers_load()['customers'] as $c) {
                if (!in_array($def['id'], customer_offers($c), true)) continue;
                $rec[] = ['id' => $c['id'], 'firma' => $c['firma'], 'nr' => $c['nr'] ?? '', 'email' => $c['email'] ?? '', 'reason' => restposten_reason($c, $def['id'])];
            }
            usort($rec, function ($a, $b) { return strcasecmp($a['firma'], $b['firma']); });
            respond(['ok' => true, 'offer' => ['id' => $def['id'], 'name' => $def['name']], 'publishedAt' => $pub['publishedAt'] ?? null, 'items' => $items, 'recipients' => $rec, 'mailReady' => (bool)mail_cfg() && (bool)mail_base_url()]);
        }

        case 'kunden_restposten': {
            require_admin_confirmation();
            $cfg = require_mail();
            $b = body();
            $def = offer_def((string)($b['offer'] ?? ''));
            if (!$def) fail('Angebot nicht gefunden.', 404);
            $pub = store_read('angebot');
            if (!$pub || (string)($b['publishedAt'] ?? '') !== (string)($pub['publishedAt'] ?? '')) fail('Inzwischen wurde neu veröffentlicht. Bitte den Versand neu öffnen und die Sonderposten prüfen.', 409);
            $items = restposten_items($def);
            if (!$items) fail('In diesem Angebot sind keine Sonderposten veröffentlicht (oder alle ohne Bestand).', 409);
            $ids = array_slice(array_values(array_filter(is_array($b['ids'] ?? null) ? $b['ids'] : [], 'is_string')), 0, 200);
            $note = mb_substr(trim((string)($b['note'] ?? '')), 0, 1000);
            $jobs = []; $res = []; $map = [];
            foreach (customers_load()['customers'] as $c) {
                if (!in_array($c['id'], $ids, true)) continue;
                $map[$c['id']] = $c;
                $why = restposten_reason($c, $def['id']);
                if ($why !== '') { $res[$c['id']] = ['ok' => false, 'error' => $why, 'skipped' => true]; continue; }
                [$sub, $txt, $html] = mail_tpl_restposten($c, $def, $items, $note);
                $one = mail_base_url() . '/api/?action=abmelden1&t=' . rawurlencode(abmelde_token($c['id']));
                $jobs[$c['id']] = ['to' => $c['email'], 'name' => ($c['ansprechpartner'] ?? '') ?: $c['firma'], 'subject' => $sub, 'text' => $txt, 'html' => $html,
                                   'headers' => ['List-Unsubscribe' => '<' . $one . '>', 'List-Unsubscribe-Post' => 'List-Unsubscribe=One-Click']];
            }
            @set_time_limit(300);
            ignore_user_abort(true);
            $res = $res + ($jobs ? mail_send_many($cfg, $jobs) : []);
            $entries = [];
            foreach ($res as $id => $r) if (empty($r['skipped'])) $entries[] = ['kid' => $id, 'firma' => $map[$id]['firma'], 'to' => $map[$id]['email'], 'typ' => 'restposten', 'ok' => $r['ok'], 'error' => $r['error'] ?? ''];
            if ($entries) mail_record($entries);
            $okN = count(array_filter($res, function ($r) { return $r['ok']; }));
            $bad = array_filter($res, function ($r) { return !$r['ok'] && empty($r['skipped']); });
            if ($res) audit('mail', "Sonderposten {$def['name']} (" . count($items) . " Artikel) an $okN Kunden versendet" . ($bad ? ' (' . count($bad) . ' nicht zugestellt)' : ''),
                array_map(function ($id) use ($res, $map) { $r = $res[$id]; return ['k' => "c$id|restposten", 'code' => $map[$id]['nr'] ?? '', 'name' => $map[$id]['firma'], 'f' => 'Sonderposten', 'from' => '', 'to' => ($map[$id]['email'] ?? '') . ($r['ok'] ? '' : ' – ' . $r['error'])]; }, array_keys($res)));
            $out = [];
            foreach ($ids as $id) $out[] = ['id' => $id] + ($res[$id] ?? ['ok' => false, 'error' => 'Kunde nicht gefunden']);
            respond(['ok' => true, 'results' => $out]);
        }
}
