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
            /* Kundenstammdaten aus der Warenwirtschaft (CSV im Browser gelesen): Abgleich über die Kundennummer, sonst über
               Firma + PLZ bei Kunden ohne Nummer. Übernommen werden Nummer, Firma, Adresse, Land, Telefon, E-Mail und
               Kundengruppe sowie Vertreter/Vertreter 2; bestehende Kunden behalten Firma, E-Mail, Zugang und Freischaltungen (leere Felder werden ergänzt).
               Neue Kunden: aktiv, ohne Zugang, ohne Wochenangebot per E-Mail (Einverständnis fehlt), Angebote über die Kundengruppe.
               „pruefen“ liefert nur die Vorschau; Übernehmen braucht die Passwortbestätigung. */
            $b = body();
            $pruefen = !empty($b['pruefen']);
            $me = $pruefen ? require_perm('kunden.bearbeiten', true) : require_perm_confirmed('kunden.bearbeiten', 'kunden_import');
            $rows = is_array($b['rows'] ?? null) ? $b['rows'] : [];
            if (!$rows) fail('Keine Kunden in der Datei gefunden.', 422);
            if (count($rows) > 10000) fail('Zu viele Zeilen (höchstens 10.000).', 422);
            $anlegen = !array_key_exists('anlegen', $b) || !empty($b['anlegen']);
            $quelle = s($b['quelle'] ?? '', 120) ?? '';
            $FELDER = ['nr', 'firma', 'strasse', 'plz', 'ort', 'land', 'telefon', 'email', 'gruppe', 'vertreter', 'vertreter2'];
            $res = with_lock('kunden', function () use ($b, $rows, $anlegen, $pruefen, $FELDER) {
                $d = customers_load();
                if (!$pruefen && (int)($b['rev'] ?? -1) !== (int)$d['rev']) fail('Die Kundendaten wurden inzwischen an anderer Stelle geändert. Bitte die Vorschau neu laden.', 409);
                // Nummern wie in der Liste schreiben („7“ in der Datei passt zu „07“ in den Kundengruppen)
                $nk = function (string $nr): string { return ctype_digit($nr) ? (ltrim($nr, '0') === '' ? '0' : ltrim($nr, '0')) : strtoupper($nr); };
                $gruppen = []; foreach (kundengruppen_load()['groups'] as $g) $gruppen[$nk($g['nr'])] = $g['nr'];
                $vertreter = []; foreach (vertreter_load()['groups'] as $g) $vertreter[$nk($g['nr'])] = $g['nr'];
                $byNr = []; $byName = [];
                foreach ($d['customers'] as $i => $c) {
                    if (($c['nr'] ?? '') !== '') $byNr[$c['nr']] = $i;
                    else $byName[mb_strtolower(trim($c['firma'])) . '|' . ($c['plz'] ?? '')] = $i;
                }
                $st = ['neu' => 0, 'aktualisiert' => 0, 'unveraendert' => 0, 'ohneFirma' => 0, 'doppelt' => 0, 'mailUngueltig' => 0, 'nichtAngelegt' => 0];
                $fremd = []; $fremdV = []; $bspNeu = []; $bspAkt = []; $ch = []; $seen = [];
                foreach ($rows as $r) {
                    if (!is_array($r)) continue;
                    $x = [];
                    foreach ($FELDER as $f) $x[$f] = s(is_scalar($r[$f] ?? null) ? (string)$r[$f] : '', CUSTOMER_FIELDS[$f]) ?? '';
                    if (mb_strlen($x['firma']) < 2) { $st['ohneFirma']++; continue; }
                    if ($x['nr'] !== '') { if (isset($seen[$x['nr']])) { $st['doppelt']++; continue; } $seen[$x['nr']] = true; }
                    if ($x['email'] !== '' && filter_var($x['email'], FILTER_VALIDATE_EMAIL) === false) { $x['email'] = ''; $st['mailUngueltig']++; }
                    if ($x['gruppe'] !== '') { if (isset($gruppen[$nk($x['gruppe'])])) $x['gruppe'] = $gruppen[$nk($x['gruppe'])]; else { $fremd[$x['gruppe']] = ($fremd[$x['gruppe']] ?? 0) + 1; $x['gruppe'] = ''; } }
                    foreach (['vertreter', 'vertreter2'] as $f) if ($x[$f] !== '') { if (isset($vertreter[$nk($x[$f])])) $x[$f] = $vertreter[$nk($x[$f])]; else { $fremdV[$x[$f]] = ($fremdV[$x[$f]] ?? 0) + 1; $x[$f] = ''; } }
                    $idx = $x['nr'] !== '' && isset($byNr[$x['nr']]) ? $byNr[$x['nr']] : ($byName[mb_strtolower($x['firma']) . '|' . $x['plz']] ?? null);
                    if ($idx === null) {
                        if (!$anlegen) { $st['nichtAngelegt']++; continue; }
                        $row = ['id' => 'k' . bin2hex(random_bytes(6))];
                        foreach (CUSTOMER_FIELDS as $f => $max) $row[$f] = $x[$f] ?? '';
                        $row += ['angebote' => [], 'active' => true, 'mailAngebot' => false, 'login' => null, 'created' => now(), 'changed' => now()];
                        $d['customers'][] = $row;
                        if ($x['nr'] !== '') $byNr[$x['nr']] = count($d['customers']) - 1;
                        else $byName[mb_strtolower($x['firma']) . '|' . $x['plz']] = count($d['customers']) - 1;   // gleiche Zeile ohne Nummer nicht doppelt anlegen
                        $st['neu']++;
                        if (count($bspNeu) < 8) $bspNeu[] = ['nr' => $x['nr'], 'firma' => $x['firma'], 'ort' => $x['ort'], 'gruppe' => $x['gruppe']];
                        if (count($ch) < 2000) $ch[] = ['k' => "c{$row['id']}|+", 'code' => $x['nr'], 'name' => $x['firma'], 'f' => 'Neuer Kunde (Import)', 'from' => '', 'to' => trim($x['plz'] . ' ' . $x['ort'])];
                        continue;
                    }
                    $c = $d['customers'][$idx];
                    $neu = $c; $diff = [];
                    foreach (['nr', 'gruppe', 'vertreter', 'vertreter2', 'strasse', 'plz', 'ort', 'land', 'telefon'] as $f) if ($x[$f] !== '' && (string)($c[$f] ?? '') !== $x[$f]) $neu[$f] = $x[$f];   // Warenwirtschaft führt Adresse, Gruppe, Vertreter
                    foreach (['firma', 'email'] as $f) if ($x[$f] !== '' && (string)($c[$f] ?? '') === '') $neu[$f] = $x[$f];                                     // nur ergänzen
                    foreach (array_merge(['firma', 'email'], ['nr', 'gruppe', 'vertreter', 'vertreter2', 'strasse', 'plz', 'ort', 'land', 'telefon']) as $f) if ((string)($c[$f] ?? '') !== (string)($neu[$f] ?? '')) $diff[$f] = [(string)($c[$f] ?? ''), (string)$neu[$f]];
                    if (!$diff) { $st['unveraendert']++; continue; }
                    $neu['changed'] = now();
                    $d['customers'][$idx] = $neu;
                    $st['aktualisiert']++;
                    if (count($bspAkt) < 8) $bspAkt[] = ['nr' => $neu['nr'] ?? '', 'firma' => $neu['firma'], 'felder' => array_map(function ($f) { return CUSTOMER_LABELS[$f]; }, array_keys($diff))];
                    foreach ($diff as $f => [$from, $to]) if (count($ch) < 2000) $ch[] = ['k' => "c{$neu['id']}|$f", 'code' => $neu['nr'] ?? '', 'name' => $neu['firma'], 'f' => CUSTOMER_LABELS[$f], 'from' => $from, 'to' => $to];
                }
                if (count($d['customers']) > 20000) fail('Zu viele Kunden (höchstens 20.000).', 422);
                arsort($fremd); arsort($fremdV);
                $out = ['stat' => $st, 'gruppenUnbekannt' => (object)array_slice($fremd, 0, 20, true), 'vertreterUnbekannt' => (object)array_slice($fremdV, 0, 20, true), 'beispiele' => ['neu' => $bspNeu, 'aktualisiert' => $bspAkt]];
                if (!$pruefen && ($st['neu'] || $st['aktualisiert'])) {
                    usort($d['customers'], function ($x, $y) { return strcasecmp($x['firma'], $y['firma']); });
                    $d['rev'] = (int)$d['rev'] + 1;
                    $d['updatedAt'] = now();
                    store_write('kunden', $d);
                }
                return [$out, $d['rev'], $ch];
            });
            [$out, $rev, $ch] = $res;
            if (!$pruefen && $ch) audit('customers', 'Kunden ' . ($quelle !== '' ? "aus „{$quelle}“ " : '') . "importiert: {$out['stat']['neu']} neu, {$out['stat']['aktualisiert']} aktualisiert", $ch);
            respond(['ok' => true, 'rev' => $rev, 'pruefen' => $pruefen] + $out);
        }
}
