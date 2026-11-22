<?php
/* Schutzzentrale (Verwaltung → Schutz, nur Administratoren): Firewall, Sperrliste, Bedrohungsliste, Live-Verkehr,
   Vorlagen und Export der Sicherheitseinstellungen. Dazu die öffentliche Falle „waf_probe“. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'waf_probe': {
            fw_falle();
        }

        case 'fw_status': {
            require_auth(false, 'admin');
            // Nur lesen: Ist die Bedrohungsliste eingeschaltet und älter als einen Tag, meldet „feedVeraltet“ das – die Ansicht
            // frischt sie danach mit fw_feed_auffrischen (POST) auf. Früher lud diese GET-Aktion selbst (bis zu 2 × 30 s
            // Netzabruf und ein Schreibvorgang), die Ansicht hing so lange.
            respond(['ok' => true, 'feedVeraltet' => fw_feed_veraltet()] + fw_status((string)($_GET['filter'] ?? '')));
        }

        /* Bedrohungsliste täglich auffrischen (beim Öffnen der Ansicht, eigener Aufruf; ohne Bestätigung, weil nur eine
           ohnehin eingeschaltete, veraltete Liste neu geladen wird – „Jetzt aktualisieren“ bleibt fw_feed_update) */
        case 'fw_feed_auffrischen': {
            require_auth(true, 'admin');
            if (!fw_feed_veraltet()) respond(['ok' => true, 'aufgefrischt' => false] + fw_status());
            @set_time_limit(90);
            try { fw_feed_laden(); } catch (Throwable $e) { error_log('[wochenangebot] bedrohungsliste: ' . $e->getMessage()); respond(['ok' => true, 'aufgefrischt' => false] + fw_status()); }
            respond(['ok' => true, 'aufgefrischt' => true] + fw_status());
        }

        case 'fw_verkehr': {
            require_auth(false, 'admin');
            respond(['ok' => true, 'verkehr' => fw_verkehr_liste((string)($_GET['filter'] ?? ''), (int)($_GET['seit'] ?? 0)), 'jetzt' => time()]);
        }

        case 'fw_save': {
            $me = require_admin_confirmation('fw_save');
            $b = body();
            fw_feed_vorladen((bool)($b['feed'] ?? fw()['feed']));   // Netzabruf vor die Sperre, nie in sie hinein
            // Lesen, Prüfen und Schreiben unter der Sperre: sonst überschreibt dieser Weg eine gleichzeitige Änderung still
            [$old, $new] = with_lock('firewall', function () use ($b) {
                $GLOBALS['FWS'] = null;   // Stand unter der Sperre frisch lesen, nicht aus dem Zwischenspeicher
                $old = fw();
                $new = fw_clean($b, $old);
                if ($new['feed'] && !fw_feed_info()) throw new InvalidArgumentException('Die Bedrohungsliste konnte nicht geladen werden – bitte später erneut versuchen oder ohne Bedrohungsliste speichern.');
                store_write('firewall', $new);
                return [$old, $new];
            });
            $GLOBALS['FWS'] = $new;
            $L = FW_FELD_LABEL;
            $fmt = fn($v) => is_bool($v) ? ($v ? 'an' : 'aus') : (is_array($v) ? implode(', ', $v) : (string)(FW_WAF_MODI[$v] ?? $v));
            $d = [];
            foreach ($L as $k => $label) if ($fmt($old[$k] ?? '') !== $fmt($new[$k])) $d[] = ['k' => "fw|$k", 'code' => '', 'name' => 'Schutz', 'f' => $label, 'from' => $fmt($old[$k] ?? ''), 'to' => $fmt($new[$k])];
            if ((int)$new['mitschnittBis'] !== (int)$old['mitschnittBis']) $d[] = ['k' => 'fw|mitschnitt', 'code' => '', 'name' => 'Schutz', 'f' => 'Mitschnitt aller Anfragen', 'from' => '', 'to' => $new['mitschnittBis'] ? 'bis ' . date('H:i', $new['mitschnittBis']) . ' Uhr' : 'aus'];
            if ($d) audit('security', 'Firewall-Einstellungen geändert', $d);
            respond(['ok' => true] + fw_status());
        }

        case 'fw_sperren': {
            $me = require_admin_confirmation('fw_sperren');
            $b = body();
            $ip = trim((string)($b['ip'] ?? ''));
            if (!valid_cidr($ip)) throw new InvalidArgumentException('Bitte eine gültige IP-Adresse oder einen Bereich angeben (z. B. 203.0.113.7 oder 203.0.113.0/24).');
            $parts = explode('/', $ip);
            if (isset($parts[1]) && (int)$parts[1] < (strpos($parts[0], ':') !== false ? 32 : 16)) throw new InvalidArgumentException('Der Bereich ist zu groß (höchstens /16 bei IPv4, /32 bei IPv6).');
            if (ip_in(client_ip(), $ip)) throw new InvalidArgumentException('Das ist Ihre eigene Adresse – Sie würden sich selbst aussperren.');
            foreach (array_merge((array)sec()['adminIps'], (array)fw()['erlaubt']) as $c) if (ip_in(explode('/', $c)[0], $ip) || ip_in($parts[0], $c)) throw new InvalidArgumentException("Die Adresse überschneidet sich mit der freigegebenen Adresse „{$c}“.");
            $min = (int)($b['minuten'] ?? 0);
            if ($min !== 0 && !in_array($min, FW_SPERR_MINUTEN, true)) throw new InvalidArgumentException('Ungültige Sperrdauer.');
            $grund = s($b['grund'] ?? '', 80) ?? '';
            with_lock('sperrliste', function () use ($ip, $min, $grund, $me) {
                $L = fw_sperrliste();
                $L['manuell'] = array_values(array_filter($L['manuell'], fn($e) => $e['ip'] !== $ip && (!(int)($e['bis'] ?? 0) || (int)$e['bis'] > time())));
                if (count($L['manuell']) >= 500) throw new InvalidArgumentException('Zu viele Einträge (höchstens 500).');
                $L['manuell'][] = ['ip' => $ip, 'grund' => $grund, 'bis' => $min ? time() + 60 * $min : 0, 'von' => $me['name'], 't' => now()];
                store_write('sperrliste', $L);
            });
            audit('security', "Adresse {$ip} von Hand gesperrt" . ($min ? ' (' . ($min >= 1440 ? intdiv($min, 1440) . ' Tag(e)' : $min . ' Minuten') . ')' : ' (dauerhaft)') . ($grund !== '' ? " – {$grund}" : ''));
            respond(['ok' => true] + fw_status());
        }

        case 'fw_freigeben': {
            require_admin_confirmation('fw_sperren');
            $ip = trim((string)(body()['ip'] ?? ''));
            $weg = with_lock('sperrliste', function () use ($ip) {
                $L = fw_sperrliste();
                $n = count($L['manuell']) + count($L['auto']);
                $L['manuell'] = array_values(array_filter($L['manuell'], fn($e) => $e['ip'] !== $ip));
                unset($L['auto'][$ip]);
                if ($n === count($L['manuell']) + count($L['auto'])) return false;
                store_write('sperrliste', $L);
                return true;
            });
            if (!$weg) fail('Diese Adresse ist nicht gesperrt.', 404);
            with_lock('fw_zaehler', function () use ($ip) { $z = store_read('fw_zaehler') ?? []; unset($z[$ip]); store_write('fw_zaehler', $z); });
            store_aussen_aendern('fw_zaehler', function (array $z) use ($ip) { unset($z[$ip]); return $z; });   // Zähler der Kundenseite (ab Trennstufe 5)
            audit('security', "Sperre der Adresse {$ip} aufgehoben");
            respond(['ok' => true] + fw_status());
        }

        case 'fw_feed_update': {
            require_admin_confirmation('fw_feed');
            @set_time_limit(90);
            try { $r = fw_feed_laden(); }
            catch (Throwable $e) { error_log('[wochenangebot] bedrohungsliste: ' . $e->getMessage()); fail('Die Bedrohungsliste konnte nicht aktualisiert werden. Bitte später erneut versuchen.', 502); }
            audit('security', 'Bedrohungsliste aktualisiert (' . $r['quelle'] . ', ' . $r['anzahl'] . ' Netze)');
            respond(['ok' => true] + fw_status());
        }

        /* Vorlage anwenden: Sicherheitseinstellungen (gleiche Prüfungen wie beim Speichern) + Firewall */
        case 'fw_vorlage': {
            $me = require_admin_confirmation('fw_save');
            $v = fw_vorlage_anwenden((string)(body()['vorlage'] ?? ''), $me);
            audit('security', 'Vorlage „' . $v['label'] . '“ für die Sicherheitseinstellungen angewendet' . $v['hinweis']);
            respond(['ok' => true, 'sec' => $v['sec']] + fw_status());
        }

        /* Export/Import der Einstellungen als JSON (ohne Listen von Nutzern, Sperren oder Geheimnissen) */
        case 'fw_export': {
            require_auth(false, 'admin');
            $S = sec();
            respond(['ok' => true, 'export' => ['art' => 'wochenangebot-sicherheit', 'version' => 1, 'stand' => now(),
                'sicherheit' => array_diff_key(array_intersect_key($S, SEC_DEFAULTS), FW_NICHT_UEBERTRAGEN), 'firewall' => array_diff_key(fw(), ['mitschnittBis' => 1, 'erlaubt' => 1])]]);
        }
        case 'fw_import': {
            $me = require_admin_confirmation('fw_save');
            $x = body()['export'] ?? null;
            if (!is_array($x) || ($x['art'] ?? '') !== 'wochenangebot-sicherheit' || (int)($x['version'] ?? 0) !== 1) throw new InvalidArgumentException('Das ist keine Datei mit Sicherheitseinstellungen dieses Portals.');
            // Adress- und Länderlisten und die abgeschaltete Passwortbestätigung bleiben wie sie sind (eine Datei von einem
            // anderen Server könnte sonst alle aussperren bzw. eine Sicherheitskontrolle absenken)
            $datS = array_diff_key(array_intersect_key((array)($x['sicherheit'] ?? []), SEC_DEFAULTS), FW_NICHT_UEBERTRAGEN);
            $datF = array_diff_key(array_intersect_key((array)($x['firewall'] ?? []), FW_DEFAULTS), ['erlaubt' => 1, 'mitschnittBis' => 1]);
            // Unvertraute Datei: jeden Wert gegen seinen Wertebereich prüfen und die Datei abweisen. sec_clean/fw_clean würden
            // einen unzulässigen Wert still auf den Standard setzen – und der ist bei diesen Feldern die schwächste Stufe.
            foreach ($datS + $datF as $k => $v) {
                $bereich = SEC_IMPORT_WERTE[$k] ?? null;
                $gut = $bereich === null ? true
                    : (is_array($bereich) ? in_array($v, $bereich, true)
                    : ($bereich === 'bool' ? is_bool($v) : is_int($v) && $v >= (int)explode(':', $bereich)[1] && $v <= (int)explode(':', $bereich)[2]));
                if (!$gut) throw new InvalidArgumentException("Die Datei enthält für „{$k}“ einen unzulässigen Wert – bitte nicht übernehmen.");
            }
            fw_feed_vorladen((bool)($datF['feed'] ?? fw()['feed']));   // Netzabruf vor die Sperre, nie in sie hinein
            // Lesen, Prüfen und Schreiben beider Dokumente unter ihrer Sperre, immer in derselben Reihenfolge (erst sicherheit,
            // dann firewall): sonst schreibt der Import eine gleichzeitige Härtung still wieder zurück
            [$oldS, $oldF, $newS, $newF] = with_lock('sicherheit', function () use ($datS, $datF, $me) {
                return with_lock('firewall', function () use ($datS, $datF, $me) {
                    $GLOBALS['SEC'] = null; $GLOBALS['FWS'] = null;   // Stand unter der Sperre frisch lesen
                    $oldS = sec(); $oldF = fw();
                    $newS = sec_clean(array_merge($oldS, $datS), $oldS, $me);
                    $newF = fw_clean($datF, $oldF);
                    if ($newF['feed'] && !fw_feed_info()) $newF['feed'] = false;
                    store_write('sicherheit', $newS); $GLOBALS['SEC'] = $newS;
                    store_write('firewall', $newF); $GLOBALS['FWS'] = $newF;
                    return [$oldS, $oldF, $newS, $newF];
                });
            });
            // Protokoll feldweise wie security_save und fw_save: jede übernommene Änderung mit alt und neu
            $fmt = fn($v) => is_bool($v) ? ($v ? 'an' : 'aus') : (is_array($v) ? implode(', ', $v) : (string)$v);
            $d = [];
            foreach (SEC_FELD_LABEL as $k => $label) if ($fmt($oldS[$k] ?? '') !== $fmt($newS[$k] ?? '')) $d[] = ['k' => "sec|$k", 'code' => '', 'name' => 'Sicherheit', 'f' => $label, 'from' => $fmt($oldS[$k] ?? ''), 'to' => $fmt($newS[$k] ?? '')];
            foreach (FW_FELD_LABEL as $k => $label) if ($fmt($oldF[$k] ?? '') !== $fmt($newF[$k] ?? '')) $d[] = ['k' => "fw|$k", 'code' => '', 'name' => 'Schutz', 'f' => $label, 'from' => $fmt($oldF[$k] ?? ''), 'to' => $fmt($newF[$k] ?? '')];
            audit('security', 'Sicherheitseinstellungen aus Datei übernommen (Stand ' . s($x['stand'] ?? '', 30) . ')', $d);
            respond(['ok' => true, 'sec' => $newS] + fw_status());
        }
}
