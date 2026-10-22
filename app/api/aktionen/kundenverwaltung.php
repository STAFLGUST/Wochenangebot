<?php
declare(strict_types=1);
/* Aktionen: Kundenstammdaten (Administrator)
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        /* ---------- Kundenstammdaten (Eingabebereich, nur Administrator) ---------- */
        case 'kunden': {
            require_perm('kunden.sehen');
            header('Cache-Control: no-store');
            $d = customers_load();
            $act = [];
            foreach (ksess_prune(store_read('kundensitzungen') ?? []) as $v) $act[$v['kid']] = ($act[$v['kid']] ?? 0) + 1;
            $list = array_map(function ($c) use ($act) { $p = customer_public($c); $p['sessions'] = $act[$c['id']] ?? 0; return $p; }, $d['customers']);
            respond(['ok' => true, 'rev' => $d['rev'], 'customers' => $list]);
        }

        case 'kunde_save': {
            $me = require_perm_confirmed('kunden.bearbeiten', 'kunde_save');
            $b = body();
            pw_datenleck_vorab(is_array($b['login'] ?? null) ? ($b['login']['password'] ?? null) : null);
            $res = with_lock('kunden', function () use ($b) {
                $d = customers_load();
                if ((int)($b['rev'] ?? -1) !== (int)$d['rev']) fail('Die Kundendaten wurden inzwischen an anderer Stelle geändert. Bitte neu laden.', 409);
                $id = is_string($b['id'] ?? null) ? $b['id'] : '';
                $idx = null;
                foreach ($d['customers'] as $i => $c) if ($c['id'] === $id) $idx = $i;
                if ($id !== '' && $idx === null) fail('Kunde nicht gefunden.', 404);
                $old = $idx !== null ? $d['customers'][$idx] : null;
                $row = ['id' => $old['id'] ?? ('k' . bin2hex(random_bytes(6)))];
                foreach (CUSTOMER_FIELDS as $f => $max) {
                    $v = s($b[$f] ?? '', $max) ?? '';
                    $row[$f] = $v;
                }
                if (mb_strlen($row['firma']) < 2) throw new InvalidArgumentException('Bitte den Namen der Firma angeben.');
                // Kundengruppe muss es geben – eine inzwischen entfernte Gruppe darf unverändert bleiben
                if ($row['gruppe'] !== '' && $row['gruppe'] !== (string)($old['gruppe'] ?? '') && !in_array($row['gruppe'], array_column(kundengruppen_load()['groups'], 'nr'), true)) throw new InvalidArgumentException('Diese Kundengruppe gibt es nicht. Bitte unter Stammdaten → Kundengruppen anlegen.');
                $vt = array_column(vertreter_load()['groups'], 'nr');
                foreach (['vertreter', 'vertreter2'] as $f) if ($row[$f] !== '' && $row[$f] !== (string)($old[$f] ?? '') && !in_array($row[$f], $vt, true)) throw new InvalidArgumentException('Diesen Vertreter gibt es nicht. Bitte unter Stammdaten → Vertreter anlegen.');
                if ($row['email'] !== '' && filter_var($row['email'], FILTER_VALIDATE_EMAIL) === false) throw new InvalidArgumentException('Die E-Mail-Adresse ist ungültig.');
                foreach ($d['customers'] as $c) if ($c['id'] !== $row['id'] && $row['nr'] !== '' && ($c['nr'] ?? '') === $row['nr']) throw new InvalidArgumentException("Die Kundennummer {$row['nr']} ist bereits vergeben.");
                $known = array_merge([OFFER_STD], offer_ids());
                $row['angebote'] = array_values(array_unique(array_filter(is_array($b['angebote'] ?? null) ? $b['angebote'] : [], function ($o) use ($known) { return is_string($o) && in_array($o, $known, true); })));
                $row['active'] = !empty($b['active']);
                $row['mailAngebot'] = !array_key_exists('mailAngebot', $b) || !empty($b['mailAngebot']);
                foreach (['weekly', 'mailLast', 'abgemeldet'] as $keep) if (isset($old[$keep])) $row[$keep] = $old[$keep];
                if ($row['mailAngebot']) unset($row['abgemeldet']);
                $row['created'] = $old['created'] ?? now();
                $row['changed'] = now();
                // Zugang
                $lg = is_array($b['login'] ?? null) ? $b['login'] : null;
                $ol = $old['login'] ?? null;
                $pwNew = false; $ended = false;
                if (!$lg || !empty($lg['remove'])) {
                    $row['login'] = null;
                    $ended = (bool)$ol;
                } else {
                    $uname = clean_username($lg['username'] ?? '');
                    foreach ($d['customers'] as $c) if ($c['id'] !== $row['id'] && (($c['login']['username'] ?? '') === $uname)) throw new InvalidArgumentException("Der Benutzername „{$uname}“ ist bereits vergeben.");
                    $l = $ol ?: ['sv' => 1, 'created' => now(), 'lastLogin' => null, 'failCount' => 0, 'lockedUntil' => 0];
                    $l['username'] = $uname;
                    $l['active'] = !empty($lg['active']);
                    $pw = (string)($lg['password'] ?? '');
                    if ($pw !== '') {
                        $l['hash'] = password_hash(check_password($pw, $uname), PASSWORD_DEFAULT);
                        $l['mustChange'] = !empty($lg['mustChange']);
                        unset($l['mustChangeGrund']);
                        $l['pwSet'] = now();
                        $l['sv'] = (int)($l['sv'] ?? 0) + 1;
                        unset($l['token']);
                        geraete_zuruecksetzen($l, true);   // neues Passwort: kein Gerät mehr vertraut
                        $pwNew = true;
                    } elseif (empty($l['hash']) && empty($lg['invite'])) {
                        throw new InvalidArgumentException('Bitte ein Startpasswort festlegen oder eine Einladung per E-Mail senden.');
                    } elseif (empty($l['hash'])) {
                        $l['hash'] = null;
                        $l['mustChange'] = false;
                        if (($row['email'] ?? '') === '') throw new InvalidArgumentException('Für eine Einladung per E-Mail bitte die E-Mail-Adresse angeben.');
                    }
                    if (!empty($lg['unlock'])) { $l['lockedUntil'] = 0; $l['failCount'] = 0; }
                    if (!empty($lg['geraeteEntfernen'])) geraete_zuruecksetzen($l, true);
                    if ($ol && $ol['username'] !== $uname) { $l['sv'] = (int)($l['sv'] ?? 0) + 1; $ended = true; unset($l['token']); geraete_zuruecksetzen($l, true); }
                    if ($ol && !empty($ol['active']) && !$l['active']) $ended = true;
                    $row['login'] = $l;
                }
                if (!$row['active']) $ended = $ended || ($old && !empty($old['active']));
                if ($idx === null) $d['customers'][] = $row; else $d['customers'][$idx] = $row;
                usort($d['customers'], function ($x, $y) { return strcasecmp($x['firma'], $y['firma']); });
                $d['rev'] = (int)$d['rev'] + 1;
                $d['updatedAt'] = now();
                store_write('kunden', $d);
                return [$d, $row, $old, $pwNew, $ended];
            });
            [$d, $row, $old, $pwNew, $ended] = $res;
            if ($ended || $pwNew) ksess_remove(function ($k, $v) use ($row) { return $v['kid'] === $row['id']; });
            // Protokoll ohne Passwörter
            $ch = [];
            $fmt = function ($f, $v) { if ($f === 'angebote') return implode(', ', array_map(function ($o) { $x = offer_def($o); return $x['name'] ?? $o; }, $v ?? [])); if ($f === 'active' || $f === 'mailAngebot') return $v === false ? 'nein' : 'ja'; return (string)$v; };
            foreach (array_merge(array_keys(CUSTOMER_FIELDS), ['angebote', 'active', 'mailAngebot']) as $f) {
                $from = $old ? $fmt($f, $old[$f] ?? '') : ''; $to = $fmt($f, $row[$f] ?? '');
                if ($from !== $to) $ch[] = ['k' => "c{$row['id']}|$f", 'code' => $row['nr'], 'name' => $row['firma'], 'f' => CUSTOMER_LABELS[$f], 'from' => $from, 'to' => $to];
            }
            $ou = $old['login']['username'] ?? ''; $nu = $row['login']['username'] ?? '';
            if ($ou !== $nu) $ch[] = ['k' => "c{$row['id']}|user", 'code' => $row['nr'], 'name' => $row['firma'], 'f' => 'Zugang (Benutzername)', 'from' => $ou, 'to' => $nu ?: 'entfernt'];
            if ((bool)($old['login']['active'] ?? false) !== (bool)($row['login']['active'] ?? false)) $ch[] = ['k' => "c{$row['id']}|lact", 'code' => $row['nr'], 'name' => $row['firma'], 'f' => 'Zugang aktiv', 'from' => !empty($old['login']['active']) ? 'ja' : 'nein', 'to' => !empty($row['login']['active']) ? 'ja' : 'nein'];
            if ($pwNew) $ch[] = ['k' => "c{$row['id']}|pw", 'code' => $row['nr'], 'name' => $row['firma'], 'f' => 'Passwort', 'from' => '', 'to' => 'neu gesetzt' . (!empty($row['login']['mustChange']) ? ' (muss bei der ersten Anmeldung geändert werden)' : '')];
            if ($ch) audit('customers', $old ? "Kunde „{$row['firma']}“ bearbeitet" : "Kunde „{$row['firma']}“ angelegt", $ch);
            respond(['ok' => true, 'rev' => $d['rev'], 'customer' => customer_public($row)]);
        }

        case 'kunde_delete': {
            require_perm_confirmed('kunden.bearbeiten', 'kunde_delete');
            $b = body();
            $id = (string)($b['id'] ?? '');
            $res = with_lock('kunden', function () use ($id, $b) {
                $d = customers_load();
                if ((int)($b['rev'] ?? -1) !== (int)$d['rev']) fail('Die Kundendaten wurden inzwischen an anderer Stelle geändert. Bitte neu laden.', 409);
                foreach ($d['customers'] as $i => $c) if ($c['id'] === $id) {
                    array_splice($d['customers'], $i, 1);
                    $d['rev'] = (int)$d['rev'] + 1;
                    $d['updatedAt'] = now();
                    store_write('kunden', $d);
                    return [$d, $c];
                }
                fail('Kunde nicht gefunden.', 404);
            });
            [$d, $c] = $res;
            ksess_remove(function ($k, $v) use ($id) { return $v['kid'] === $id; });
            with_lock('merklisten', function () use ($id) { $all = store_read('merklisten') ?? []; if (isset($all[$id])) { unset($all[$id]); store_write('merklisten', $all); } });
            anmeldeorte_remove_customer($id);
            audit('customers', "Kunde „{$c['firma']}“ gelöscht", [['k' => "c$id|-", 'code' => $c['nr'] ?? '', 'name' => $c['firma'], 'f' => 'Kunde gelöscht', 'from' => $c['firma'], 'to' => '']]);
            respond(['ok' => true, 'rev' => $d['rev']]);
        }

        case 'kunden_import': {
            /* Kundenstammdaten aus der Warenwirtschaft (CSV im Browser gelesen). Abgleich, Prüfung und Speichern:
               kunden_import_lauf() im Importvertrag der Verwaltung (module/verwaltung/import.php, auch für die Importzentrale).
               „pruefen“ liefert nur die Vorschau; Übernehmen braucht die Passwortbestätigung. */
            $b = body();
            $pruefen = !empty($b['pruefen']);
            $me = $pruefen ? require_perm('kunden.bearbeiten', true) : require_perm_confirmed('kunden.bearbeiten', 'kunden_import');
            respond(['ok' => true, 'pruefen' => $pruefen] + kunden_import_lauf($b, $pruefen));
        }
}
