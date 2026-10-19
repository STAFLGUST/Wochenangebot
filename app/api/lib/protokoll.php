<?php
declare(strict_types=1);
/* Protokoll, Änderungstexte, Anmeldeversuche */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Protokoll ---------------- */

/* Ein Eintrag je Vorgang; fortlaufendes Bearbeiten des Entwurfs durch dieselbe Person wird zusammengefasst */
function audit(string $a, string $s, array $d = [], ?array $who = null, bool $merge = false): void
{
    global $ME;
    try {
        $who = $who ?? $ME;
        $month = gmdate('Y-m');
        with_lock('protokoll', function () use ($a, $s, $d, $who, $merge, $month) {
            $log = store_read('protokoll/' . $month) ?? [];
            $last = $log ? $log[count($log) - 1] : null;
            $u = $who['username'] ?? '';
            if ($merge && $last && $last['a'] === $a && $last['u'] === $u && strtotime($last['t']) > time() - 1800) {
                $last['d'] = changes_merge($last['d'] ?? [], $d);
                $last['t'] = now();
                $last['s'] = $s;
                if (!$last['d']) array_pop($log); else $log[count($log) - 1] = $last;
            } else {
                if ($merge && !$d) return;
                $e = ['t' => now(), 'u' => $u, 'n' => $who['name'] ?? '', 'r' => $who['role'] ?? '', 'ip' => client_ip(), 'a' => $a, 's' => $s];
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
function client_ip(): string
{
    $ip = (string)($_SERVER['REMOTE_ADDR'] ?? '');
    // Hinter dem eigenen Proxy (Caddy im Docker-Netz) die weitergereichte Besucher-IP verwenden
    $private = filter_var($ip, FILTER_VALIDATE_IP, FILTER_FLAG_NO_PRIV_RANGE | FILTER_FLAG_NO_RES_RANGE) === false;
    $fwd = (string)($_SERVER['HTTP_X_FORWARDED_FOR'] ?? '');
    if ($private && $fwd !== '') {
        $parts = array_map('trim', explode(',', $fwd));
        $last = end($parts);
        if (filter_var($last, FILTER_VALIDATE_IP)) return $last;
    }
    return $ip;
}
function client_key(): string { return hash('sha256', client_ip()); }
function attempts_check(): void
{
    $a = store_read('logins') ?? [];
    $k = client_key();
    if (!empty($a[$k]['until']) && $a[$k]['until'] > time()) {
        fail('Zu viele Fehlversuche. Bitte in ' . (int)ceil(($a[$k]['until'] - time()) / 60) . ' Minuten erneut versuchen.', 429);
    }
}
function attempts_record(bool $ok): void
{
    with_lock('logins', function () use ($ok) {
        global $CFG;
        $a = store_read('logins') ?? [];
        $k = client_key();
        foreach ($a as $kk => $v) if (($v['until'] ?? 0) < time() && ($v['t'] ?? 0) < time() - 86400) unset($a[$kk]);
        if ($ok) unset($a[$k]);
        else {
            $n = (int)($a[$k]['n'] ?? 0) + 1;
            $a[$k] = ['n' => $n, 't' => time(), 'ip' => client_ip(), 'until' => $n >= (int)$CFG['max_attempts'] ? time() + 60 * (int)$CFG['lock_minutes'] : 0];
            if ($n >= (int)$CFG['max_attempts']) {
                $a[$k]['n'] = 0;
                if (function_exists('notify')) notify('sicherheit', 'Anmeldesperre nach ' . $n . ' Fehlversuchen', [['IP-Adresse', client_ip()], ['Gesperrt für', (int)$CFG['lock_minutes'] . ' Minuten']]);
            }
        }
        store_write('logins', $a);
    });
}
