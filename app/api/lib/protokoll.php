<?php
declare(strict_types=1);
/* Protokoll, Änderungstexte, Anmeldeversuche */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Protokoll ---------------- */

/* Aufbewahrung (Inhaber 25.10.2026): das Protokoll umfasst den laufenden Monat und die sechs Monate davor. Ältere
   Monatsdokumente „protokoll/JJJJ-MM“ löscht audit() beim Schreiben (gleiche Sperre, beide Speicherarten).
   Sicherungen enthalten ältere Stände weiter, bis sie selbst ablaufen. */
const PROTOKOLL_MONATE = 6;

/* Ältester aufbewahrter Monat (JJJJ-MM): laufender Monat minus PROTOKOLL_MONATE */
function protokoll_grenze(?int $jetzt = null): string { return utc_monat(-PROTOKOLL_MONATE, $jetzt); }
/* Monate des Protokolls, die aufbewahrt werden (neueste zuerst) – Protokollansicht bietet nur diese an */
function protokoll_monate(): array
{
    $grenze = protokoll_grenze(); $out = [];
    foreach (store_names('protokoll') as $f) { $m = basename($f); if (preg_match('/^\d{4}-\d{2}$/', $m) && $m >= $grenze) $out[] = $m; }
    rsort($out);
    return $out;
}
/* Monatsdokumente vor der Grenze löschen; liefert die entfernten Monate (aufsteigend). Nur innerhalb von with_lock('protokoll'). */
function protokoll_aufraeumen(): array
{
    $grenze = protokoll_grenze(); $weg = [];
    foreach (store_names('protokoll') as $f) {
        $m = basename($f);
        if (preg_match('/^\d{4}-\d{2}$/', $m) && $m < $grenze) { store_delete('protokoll/' . $m); $weg[] = $m; }
    }
    sort($weg);
    return $weg;
}

/* Ein Eintrag je Vorgang; fortlaufendes Bearbeiten des Entwurfs durch dieselbe Person wird zusammengefasst */
/* Vorgänge mit Kundendaten (Adressen, E-Mails, Bestellungen) – im Protokoll nur mit Recht „Kunden ansehen“ vollständig */
const LOG_KUNDENDATEN = ['customers', 'kunde_login', 'kunde_login_fail', 'kunde_password', 'kunde_abmeldung', 'einzelangebot', 'bestellung', 'mail', 'einkauf'];
const LOG_KUNDENDATEN_TEXT = ['customers' => 'Kundendaten geändert', 'kunde_login' => 'Kunde angemeldet', 'kunde_login_fail' => 'Kunden-Anmeldung fehlgeschlagen',
    'kunde_password' => 'Kunde hat Passwort festgelegt', 'kunde_abmeldung' => 'Kunde hat E-Mails ab- oder angemeldet', 'einzelangebot' => 'Einzelangebot bearbeitet',
    'bestellung' => 'Bestellwunsch bearbeitet', 'mail' => 'E-Mail-Versand', 'einkauf' => 'Einkauf benachrichtigt'];
function audit(string $a, string $s, array $d = [], ?array $who = null, bool $merge = false): void
{
    global $ME;
    try {
        $who = $who ?? $ME;
        $month = gmdate('Y-m');
        with_lock('protokoll', function () use ($a, $s, $d, $who, $merge, $month) {
            $log = store_read('protokoll/' . $month) ?? [];
            // Aufbewahrung: ältere Monate entfernen und das im laufenden Monat vermerken (nur Monate, keine Inhalte)
            if ($weg = protokoll_aufraeumen()) {
                $log[] = ['t' => now(), 'u' => 'system', 'n' => 'System', 'r' => '', 'ip' => '', 'a' => 'protokoll_aufbewahrung',
                          's' => 'Protokoll: ' . count($weg) . (count($weg) === 1 ? ' Monat' : ' Monate') . ' älter als ' . PROTOKOLL_MONATE . ' Monate entfernt ('
                               . ($weg[0] === end($weg) ? $weg[0] : $weg[0] . ' bis ' . end($weg)) . ')'];
            }
            $last = $log ? $log[count($log) - 1] : null;
            $u = $who['username'] ?? '';
            if ($merge && $last && $last['a'] === $a && $last['u'] === $u && strtotime($last['t']) > time() - 1800) {
                $last['d'] = changes_merge($last['d'] ?? [], $d);
                $last['t'] = now();
                $last['s'] = $s;
                if (!$last['d']) array_pop($log); else $log[count($log) - 1] = $last;
            } else {
                if ($merge && !$d) { if ($weg) store_write('protokoll/' . $month, $log); return; }
                // Kunden: IP nur bei fehlgeschlagener Anmeldung (Sicherheit), sonst nicht speichern (wie bei der Auswertung zugesagt)
                $ip = ($who['role'] ?? '') === 'kunde' && $a !== 'kunde_login_fail' ? '' : client_ip();
                $e = ['t' => now(), 'u' => $u, 'n' => $who['name'] ?? '', 'r' => $who['role'] ?? '', 'ip' => $ip, 'a' => $a, 's' => $s];
                if ($d) $e['d'] = $d;
                $log[] = $e;
            }
            store_write('protokoll/' . $month, $log);
        });
        if (function_exists('notify_from_audit')) notify_from_audit($a, $s, $d, $who);
    } catch (Throwable $e) {
        if (!empty($GLOBALS['store_tx'])) throw $e;
        error_log('[wochenangebot] Protokoll: ' . $e->getMessage());
    }
}
function price_text($p): string
{
    if (!is_array($p)) return '';
    $st = $p['status'] ?? 'none';
    if ($st === 'value') {
        $v = (float)$p['value'];
        $t = number_format($v, abs($v * 100 - round($v * 100)) > 1e-6 ? 3 : 2, ',', '.') . ' €/kg';
    } elseif ($st === 'request') $t = 'auf Anfrage';
    else $t = 'ohne Preis';
    return $t;
}
function sale_text($sale): string
{
    if (!is_array($sale) || !isset($sale['value'])) return '';
    $t = 'Sonderpreis ' . price_text(['status' => 'value', 'value' => $sale['value']]);
    foreach ($sale['offers'] ?? [] as $oid => $o) {
        $def = offer_def((string)$oid);
        $t .= '; ' . ($def['name'] ?? $oid) . ': ' . (($o['status'] ?? '') === 'none' ? 'kein Sonderpreis' : price_text(['status' => 'value', 'value' => $o['value']]));
    }
    return $t;
}
function variant_text($v, string $oid = ''): string
{
    if ($oid === OFFER_STD) return is_array($v) && ($v['status'] ?? '') === 'hidden' ? 'ausgeblendet' : 'sichtbar';
    if (!is_array($v)) return 'ohne eigenen Preis';
    if (($v['status'] ?? '') === 'hidden') return 'ausgeblendet';
    return price_text($v);
}
function alts_text($alts): string
{
    $out = [];
    foreach ((array)$alts as $p) $out[] = trim(($p['label'] ?? '') . ': ' . price_text($p));
    return implode(' · ', $out);
}
/* Änderungen zwischen zwei Ständen als Liste {k, code, name, f, from, to} */
function changes_between(?array $a, array $b): array
{
    $out = [];
    $am = $a['meta'] ?? [];
    $bm = $b['meta'] ?? [];
    $wa = isset($am['week']) ? ($am['week'] . '/' . ($am['year'] ?? '')) : '';
    $wb = isset($bm['week']) ? ($bm['week'] . '/' . ($bm['year'] ?? '')) : '';
    if ($a && $wa !== $wb) $out[] = ['k' => 'm|week', 'code' => '', 'name' => 'Kopfdaten', 'f' => 'Kalenderwoche', 'from' => $wa, 'to' => $wb];
    if ($a && (string)($am['notice'] ?? '') !== (string)($bm['notice'] ?? '')) $out[] = ['k' => 'm|notice', 'code' => '', 'name' => 'Kopfdaten', 'f' => 'Hinweis', 'from' => (string)($am['notice'] ?? ''), 'to' => (string)($bm['notice'] ?? '')];
    // Werbung je Angebot (Überschrift und beworbene Artikel)
    if ($a) {
        $wA = is_array($am['werbung'] ?? null) ? $am['werbung'] : [];
        $wB = is_array($bm['werbung'] ?? null) ? $bm['werbung'] : [];
        $names = [];
        foreach (array_merge($a['items'] ?? [], $b['items'] ?? []) as $it) $names[(string)($it['id'] ?? '')] = (string)($it['name'] ?? '');
        $wtext = function ($e) use ($names) {
            if (!is_array($e) || empty($e['artikel'])) return '';
            $n = array_map(function ($x) use ($names) { return $names[(string)($x['id'] ?? '')] ?? '?'; }, $e['artikel']);
            return trim((string)($e['titel'] ?? '') . ': ' . implode(' · ', $n), ': ');
        };
        foreach (array_unique(array_merge(array_map('strval', array_keys($wA)), array_map('strval', array_keys($wB)))) as $oid) {
            $wf = $wtext($wA[$oid] ?? null); $wt = $wtext($wB[$oid] ?? null);
            $same = json_encode($wA[$oid] ?? null) === json_encode($wB[$oid] ?? null);
            if (!$same) { $def = offer_def($oid); $out[] = ['k' => "m|w:$oid", 'code' => '', 'name' => 'Werbung', 'f' => 'Werbung ' . ($def['name'] ?? $oid), 'from' => $wf ?: 'keine', 'to' => $wt ?: 'keine']; }
        }
    }
    $ga = []; foreach (($a['groups'] ?? []) as $g) $ga[$g['id']] = $g;
    $gb = []; foreach (($b['groups'] ?? []) as $g) $gb[$g['id']] = $g;
    foreach ($gb as $id => $g) {
        if (!isset($ga[$id])) continue;
        if ($ga[$id]['name'] !== $g['name']) $out[] = ['k' => "g$id|name", 'code' => '', 'name' => 'Gruppe', 'f' => 'Gruppenname', 'from' => $ga[$id]['name'], 'to' => $g['name']];
        if (($ga[$id]['section'] ?? '') !== ($g['section'] ?? '')) $out[] = ['k' => "g$id|section", 'code' => '', 'name' => $g['name'], 'f' => 'Bereich', 'from' => $ga[$id]['section'] ?? '', 'to' => $g['section'] ?? ''];
    }
    $gname = function ($id) use ($ga, $gb) { return $gb[$id]['name'] ?? $ga[$id]['name'] ?? ''; };
    $ia = []; foreach (($a['items'] ?? []) as $it) $ia[$it['id']] = $it;
    $ib = []; foreach (($b['items'] ?? []) as $it) $ib[$it['id']] = $it;
    $fields = ['code' => 'Art.-Nr.', 'name' => 'Bezeichnung', 'category' => 'Fleischart', 'origin' => 'Herkunft', 'condition' => 'Zustand'];
    foreach ($ib as $id => $it) {
        $code = (string)($it['code'] ?? '');
        if (!isset($ia[$id])) {
            if ($a) $out[] = ['k' => "$id|+", 'code' => $code, 'name' => $it['name'], 'f' => 'Neuer Artikel', 'from' => '', 'to' => price_text($it['price']) . ' · ' . $gname($it['groupId'])];
            continue;
        }
        $o = $ia[$id];
        foreach ($fields as $f => $label) {
            if ((string)($o[$f] ?? '') !== (string)($it[$f] ?? '')) $out[] = ['k' => "$id|$f", 'code' => $code, 'name' => $it['name'], 'f' => $label, 'from' => (string)($o[$f] ?? ''), 'to' => (string)($it[$f] ?? '')];
        }
        if (($o['groupId'] ?? '') !== ($it['groupId'] ?? '')) $out[] = ['k' => "$id|groupId", 'code' => $code, 'name' => $it['name'], 'f' => 'Gruppe', 'from' => $gname($o['groupId']), 'to' => $gname($it['groupId'])];
        if (price_text($o['price'] ?? null) !== price_text($it['price'] ?? null)) $out[] = ['k' => "$id|price", 'code' => $code, 'name' => $it['name'], 'f' => 'Preis', 'from' => price_text($o['price'] ?? null), 'to' => price_text($it['price'] ?? null)];
        if ((string)($o['price']['label'] ?? '') !== (string)($it['price']['label'] ?? '')) $out[] = ['k' => "$id|plabel", 'code' => $code, 'name' => $it['name'], 'f' => 'Preisbezeichnung', 'from' => (string)($o['price']['label'] ?? ''), 'to' => (string)($it['price']['label'] ?? '')];
        if (alts_text($o['altPrices'] ?? []) !== alts_text($it['altPrices'] ?? [])) $out[] = ['k' => "$id|alts", 'code' => $code, 'name' => $it['name'], 'f' => 'Zusatzpreise', 'from' => alts_text($o['altPrices'] ?? []), 'to' => alts_text($it['altPrices'] ?? [])];
        foreach (array_unique(array_merge(array_keys($o['variants'] ?? []), array_keys($it['variants'] ?? []))) as $oid) {
            $vf = variant_text($o['variants'][$oid] ?? null, (string)$oid); $vt = variant_text($it['variants'][$oid] ?? null, (string)$oid);
            if ($vf !== $vt) { $def = offer_def((string)$oid); $out[] = ['k' => "$id|v:$oid", 'code' => $code, 'name' => $it['name'], 'f' => ($oid === OFFER_STD ? 'Sichtbar im ' : 'Preis ') . ($def['name'] ?? $oid), 'from' => $vf, 'to' => $vt]; }
        }
        if (sale_text($o['sale'] ?? null) !== sale_text($it['sale'] ?? null)) $out[] = ['k' => "$id|sale", 'code' => $code, 'name' => $it['name'], 'f' => 'Sonderpreis (solange der Vorrat reicht)', 'from' => sale_text($o['sale'] ?? null) ?: 'kein Sonderpreis', 'to' => sale_text($it['sale'] ?? null) ?: 'kein Sonderpreis'];
    }
    foreach ($ia as $id => $it) {
        if (!isset($ib[$id])) $out[] = ['k' => "$id|-", 'code' => (string)($it['code'] ?? ''), 'name' => $it['name'], 'f' => 'Artikel entfernt', 'from' => price_text($it['price']), 'to' => ''];
    }
    return $out;
}
/* Neue Änderungen in einen bestehenden Eintrag einarbeiten: Ausgangswert bleibt, Endwert wird aktualisiert */
function changes_merge(array $old, array $new): array
{
    $idx = [];
    foreach ($old as $i => $c) $idx[$c['k']] = $i;
    foreach ($new as $c) {
        [$id, $f] = explode('|', $c['k'], 2) + [1 => ''];
        if ($f === '-' && isset($idx["$id|+"])) {           // neu angelegt und wieder entfernt → nichts übrig
            foreach ($old as $i => $o) if (strpos($o['k'], "$id|") === 0) unset($old[$i]);
            $old = array_values($old);
            $idx = []; foreach ($old as $i => $o) $idx[$o['k']] = $i;
            continue;
        }
        if ($f !== '+' && $f !== '-' && isset($idx["$id|+"])) { // Bearbeitung eines neuen Artikels → Eintrag „neu“ aktualisieren
            $o = &$old[$idx["$id|+"]];
            $o['code'] = $c['code']; $o['name'] = $c['name'];
            if ($f === 'price') $o['to'] = preg_replace('/^[^·]*/u', $c['to'] . ' ', $o['to'], 1);
            unset($o);
            continue;
        }
        if (isset($idx[$c['k']])) {
            $o = &$old[$idx[$c['k']]];
            $o['to'] = $c['to']; $o['code'] = $c['code']; $o['name'] = $c['name'];
            $same = $o['from'] === $o['to'];
            unset($o);
            if ($same) {
                unset($old[$idx[$c['k']]]);
                $old = array_values($old);
                $idx = []; foreach ($old as $i => $o2) $idx[$o2['k']] = $i;
            }
        } else {
            $old[] = $c;
            $idx[$c['k']] = count($old) - 1;
        }
    }
    return array_slice(array_values($old), 0, 2000);
}
function changes_summary(array $d): string
{
    $p = $n = $r = $e = 0;
    foreach ($d as $c) {
        $f = explode('|', $c['k'], 2)[1] ?? '';
        if ($f === 'price' || strpos($f, 'v:') === 0) $p++; elseif ($f === '+') $n++; elseif ($f === '-') $r++; else $e++;
    }
    $parts = [];
    if ($p) $parts[] = $p . ($p === 1 ? ' Preis' : ' Preise') . ' geändert';
    if ($n) $parts[] = $n . ' Artikel neu';
    if ($r) $parts[] = $r . ' Artikel entfernt';
    if ($e) $parts[] = $e . ($e === 1 ? ' weitere Änderung' : ' weitere Änderungen');
    return $parts ? implode(', ', $parts) : 'keine Änderungen';
}

/* Anmeldeversuche begrenzen */
/* Darf diese Gegenstelle die Besucher-IP weiterreichen (X-Forwarded-For)?
   WA_TRUSTED_PROXIES (Docker: „caddy“) = Liste aus Namen, IP-Adressen oder Netzen; nur diese gelten als eigener Proxy.
   Ohne Angabe (Hostinger, lokale Tests) wie bisher: jede private Adresse. */
/* Zuletzt aufgelöste Adressen eines Proxy-Namens (im Datenordner, sonst im Temp-Ordner; nur vom Server selbst geschrieben,
   getrennt nach IPv4/IPv6). Aufgelöst: merken, wenn neu; nicht aufgelöst: die gemerkten zurückgeben (leer = nie aufgelöst). */
function proxy_adressen_merken(string $name, array $adr, string $familie = '4'): array
{
    $dir = !empty($GLOBALS['DATA']) && is_dir($GLOBALS['DATA']) && is_writable($GLOBALS['DATA']) ? $GLOBALS['DATA'] : sys_get_temp_dir();
    $f = rtrim($dir, '/') . '/wa-proxy-' . $familie . '-' . hash('sha256', $name) . '.json';
    $alt = is_file($f) ? json_decode((string)@file_get_contents($f), true) : null;
    $alt = is_array($alt) ? array_values(array_filter($alt, fn($x) => is_string($x) && filter_var($x, FILTER_VALIDATE_IP))) : [];
    if (!$adr) return $alt;
    sort($adr);
    if ($adr !== $alt) { $tmp = $f . '.' . bin2hex(random_bytes(4)); if (@file_put_contents($tmp, json_encode($adr)) !== false) @rename($tmp, $f); }
    return $adr;
}
function trusted_proxy(string $ip): bool
{
    static $cache = [];
    if (isset($cache[$ip])) return $cache[$ip];
    $cfg = trim((string)(getenv('WA_TRUSTED_PROXIES') ?: ($_SERVER['WA_TRUSTED_PROXIES'] ?? '')));
    if ($cfg === '') return $cache[$ip] = filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false;
    $aufgeloest = false;
    foreach (preg_split('/[\s,]+/', $cfg) as $t) {
        if ($t === '') continue;
        if (strpos($t, '/') !== false) { $aufgeloest = true; if (function_exists('ip_in') && ip_in($ip, $t)) return $cache[$ip] = true; continue; }
        if (filter_var($t, FILTER_VALIDATE_IP)) { $aufgeloest = true; if (@inet_pton($t) === @inet_pton($ip)) return $cache[$ip] = true; continue; }
        if (!preg_match('/^[a-z0-9.-]{1,253}$/i', $t) || !preg_match('/[a-z]/i', $t)) continue;   // Name mit Buchstaben (sonst würde „10.1“ als 10.0.0.1 aufgelöst)
        $adr = gethostbynamel($t) ?: [];   // Docker-Dienstname (IPv4)
        if (strpos($ip, ':') !== false && function_exists('dns_get_record')) $adr = array_merge($adr, array_column(@dns_get_record($t, DNS_AAAA) ?: [], 'ipv6'));   // IPv6-Netz
        $adr = proxy_adressen_merken($t, $adr, strpos($ip, ':') !== false ? '6' : '4');   // kurze DNS-Störung: zuletzt aufgelöste Adressen weiterverwenden
        if ($adr) $aufgeloest = true;
        $bin = @inet_pton($ip);
        foreach ($adr as $a) if ($bin !== false && @inet_pton($a) === $bin) return $cache[$ip] = true;   // binär vergleichen (IPv6-Schreibweisen)
    }
    // Kein Name auflösbar und noch nie aufgelöst (z. B. DNS-Störung direkt nach dem Start): wie ohne Angabe, sonst hätten alle
    // Besucher die Adresse des Proxys (Sperren und Grenzen träfen alle gemeinsam). Im Produktivnetz sind nur Caddy und die App.
    if (!$aufgeloest) return $cache[$ip] = filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false;
    return $cache[$ip] = false;
}
function client_ip(): string
{
    $ip = (string)($_SERVER['REMOTE_ADDR'] ?? '');
    // Hinter dem eigenen Proxy (Caddy) die weitergereichte Besucher-IP verwenden – nur von diesem, nie von anderen Containern
    $fwd = (string)($_SERVER['HTTP_X_FORWARDED_FOR'] ?? '');
    if ($fwd !== '' && trusted_proxy($ip)) {
        $parts = array_map('trim', explode(',', $fwd));
        $last = end($parts);
        if (filter_var($last, FILTER_VALIDATE_IP)) return $last;
    }
    return $ip;
}
/* Schlüssel für Fehlversuche: IPv4 je Adresse, IPv6 je /64-Netz (ein Anschluss hat meist ein ganzes /64 –
   sonst könnte man durch Wechseln der Adresse beliebig oft raten) */
function client_key(): string
{
    $ip = client_ip();
    $bin = @inet_pton($ip);
    if ($bin !== false && strlen($bin) === 16 && substr($bin, 0, 12) !== str_repeat("\0", 10) . "\xff\xff") $ip = inet_ntop(substr($bin, 0, 8) . str_repeat("\0", 8)) . '/64';
    return hash('sha256', $ip);
}
/* Fehlversuchsbremse je Adresse (Dokument „logins“: Schlüssel → {n, t, ip, until, bereich, wer}).
   - Eine erfolgreiche Anmeldung nimmt nur die Fehlversuche **für denselben Benutzernamen** zurück (wer sich vertippt und
     dann anmeldet, wird wie bisher nicht gesperrt). Fehlversuche für andere Namen bleiben stehen: Sonst könnte jemand mit
     einem eigenen gültigen Zugang zwischen je vier Versuchen an fremden Konten kurz sich selbst anmelden und unbegrenzt
     weiterraten (Passwort-Spraying). „wer“: Name → Zahl der Fehlversuche (nur Prüfsummen der Namen).
   - Fehlversuche verfallen ATTEMPTS_FENSTER Sekunden nach dem letzten Fehlversuch.
   - Mitarbeiter- und Kundenanmeldung zählen getrennt ($bereich): Ein Kundenzugang entsperrt nie die Mitarbeiteranmeldung
     und umgekehrt. Mitarbeiter behalten den bisherigen Schlüssel (Rückfall auf die Vorversion liest ihn weiter, GR-006).
   - Eine laufende Sperre (until) hebt keine Anmeldung auf – nur ein Administrator (ip_unblock) oder der Zeitablauf. */
const ATTEMPTS_FENSTER = 3600;
function attempts_key(string $bereich = 'mitarbeiter'): string
{
    return $bereich === 'kunde' ? hash('sha256', 'kunde|' . client_key()) : client_key();
}
function attempts_wer(string $name): string
{
    return substr(hash('sha256', 'wer|' . mb_strtolower(trim($name))), 0, 16);
}
function attempts_check(string $bereich = 'mitarbeiter'): void
{
    $a = store_read('logins') ?? [];
    $k = attempts_key($bereich);
    if (!empty($a[$k]['until']) && $a[$k]['until'] > time()) {
        fail('Zu viele Fehlversuche. Bitte in ' . (int)ceil(($a[$k]['until'] - time()) / 60) . ' Minuten erneut versuchen.', 429);
    }
}
/* $name: Benutzername des Versuchs ('' = ohne Namen, z. B. Einmal-Links – wird nie durch eine Anmeldung zurückgenommen) */
function attempts_record(bool $ok, string $bereich = 'mitarbeiter', string $name = ''): void
{
    with_lock('logins', function () use ($ok, $bereich, $name) {
        global $CFG;
        $a = store_read('logins') ?? [];
        $k = attempts_key($bereich);
        $w = $name !== '' ? attempts_wer($name) : '';
        $vorher = $a;
        foreach ($a as $kk => $v) if (($v['until'] ?? 0) < time() && ($v['t'] ?? 0) < time() - 86400) unset($a[$kk]);
        $alt = $a[$k] ?? null;
        $frisch = $alt !== null && (int)($alt['t'] ?? 0) >= time() - ATTEMPTS_FENSTER;
        if ($ok) {
            if ($alt !== null && $frisch && $w !== '' && isset($alt['wer'][$w]) && (int)($alt['until'] ?? 0) <= time()) {
                $n = max(0, (int)$alt['n'] - (int)$alt['wer'][$w]);
                unset($alt['wer'][$w]);
                if ($n === 0 && !$alt['wer']) unset($a[$k]); else $a[$k] = ['n' => $n] + $alt;
            }
        } else {
            $wer = $frisch && is_array($alt['wer'] ?? null) ? $alt['wer'] : [];
            if ($w !== '') $wer[$w] = (int)($wer[$w] ?? 0) + 1;
            $n = ($frisch ? (int)($alt['n'] ?? 0) : 0) + 1;
            $a[$k] = ['n' => $n, 't' => time(), 'ip' => client_ip(), 'until' => $n >= (int)$CFG['max_attempts'] ? time() + 60 * (int)$CFG['lock_minutes'] : (int)($alt['until'] ?? 0),
                      'bereich' => $bereich, 'wer' => $wer];
            if ($n >= (int)$CFG['max_attempts']) {
                $a[$k]['n'] = 0; $a[$k]['wer'] = [];
                if (function_exists('notify')) notify('sicherheit', 'Anmeldesperre nach ' . $n . ' Fehlversuchen', [['IP-Adresse', client_ip()], ['Gesperrt für', (int)$CFG['lock_minutes'] . ' Minuten']]);
            }
        }
        if ($a !== $vorher) store_write('logins', $a);
    });
}
