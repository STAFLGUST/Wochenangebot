<?php
declare(strict_types=1);
/* Angebote, Kundenpreise, Sonderpreise, Datenmodell, gemeinsames Bearbeiten */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Mehrere Angebote ----------------
   Das Standardangebot („Wochenangebot“) ist die Grundlage. Kundenangebote (z. B. Edeka) haben je Artikel optional
   einen eigenen Preis in $item['variants'][<Angebots-ID>] = {status: value|request|hidden, value?, carried?}.
   Ohne eigenen Preis gilt die Regel des Angebots: 'standard' = Standardpreis zeigen, 'hidden' = Artikel ausblenden.
   Kundenpreise verlassen den Server nur aufgelöst und nur für berechtigte Nutzer (offer_resolve). */
const OFFER_STD = 'std';
const OFFER_DEFAULTS = [
    ['id' => 'chefs-culinar', 'name' => 'Wochenangebot Chefs Culinar', 'fallback' => 'standard'],
    ['id' => 'handelshof-efs', 'name' => 'Wochenangebot Handelshof, EFS', 'fallback' => 'standard'],
    ['id' => 'edeka', 'name' => 'Wochenangebot Edeka', 'fallback' => 'standard'],
    ['id' => 'bela', 'name' => 'Wochenangebot Bela', 'fallback' => 'standard'],
];
const VARIANT_STATUS = ['value', 'request', 'hidden'];
const OFFER_MAX = 100;   // Kundenangebote (je Kundengruppe höchstens eines)
function offers_load(): array
{
    $d = store_read('angebote');
    return is_array($d) && isset($d['offers']) ? $d : ['rev' => 0, 'offers' => OFFER_DEFAULTS, 'updatedAt' => null];
}
function offer_ids(): array { return array_column(offers_load()['offers'], 'id'); }
/* Kundengruppen eines Angebots (Stammdaten → Angebote): Kunden dieser Gruppen sehen das Angebot ohne eigene Freischaltung */
function offer_gruppen_clean($v, string $name): array
{
    if (!is_array($v)) throw new InvalidArgumentException("Ungültige Kundengruppen ($name).");
    $out = [];
    foreach (array_slice($v, 0, 500) as $g) {
        $g = is_string($g) || is_int($g) ? trim((string)$g) : '';
        if (!preg_match('/^[0-9A-Za-z._-]{1,10}$/', $g)) throw new InvalidArgumentException("Ungültige Kundengruppe ($name).");
        $out[$g] = true;
    }
    $out = array_keys($out);
    $out = array_map('strval', $out);
    usort($out, 'strnatcasecmp');
    return $out;
}
/* Ist das Standard-Wochenangebot ohne Anmeldung sichtbar? (Voreinstellung: ja) */
function std_public(): bool { $d = offers_load(); return !array_key_exists('stdPublic', $d) || !empty($d['stdPublic']); }

function offer_def(string $id): ?array
{
    if ($id === OFFER_STD) return ['id' => OFFER_STD, 'name' => 'Wochenangebot', 'fallback' => 'standard'];
    foreach (offers_load()['offers'] as $o) if ($o['id'] === $id) return $o;
    return null;
}
function clean_variants($v, string $where, array $known): array
{
    $out = [];
    if (!is_array($v)) return $out;
    foreach ($v as $oid => $p) {
        $oid = (string)$oid;   // JSON-Schlüssel wie "24" kommen als Zahl an – sonst gingen Kundenpreise beim Speichern verloren
        if (!is_array($p)) continue;
        $st = $p['status'] ?? '';
        if ($oid === OFFER_STD) {                       // Wochenangebot: nur „ausgeblendet“ (Preis steht in price)
            if ($st === 'hidden') $out[$oid] = ['status' => 'hidden'];
            continue;
        }
        if (!in_array($oid, $known, true)) continue;   // gelöschte Angebote fallen weg
        if (!in_array($st, VARIANT_STATUS, true)) throw new InvalidArgumentException("Ungültiger Angebotspreis ($where).");
        $row = ['status' => $st];
        if ($st === 'value') {
            $x = $p['value'] ?? null;
            if (!is_int($x) && !is_float($x)) throw new InvalidArgumentException("Angebotspreis fehlt ($where).");
            $x = (float)$x;
            if ($x < 0 || $x >= 100000) throw new InvalidArgumentException("Angebotspreis außerhalb des gültigen Bereichs ($where).");
            $row['value'] = round($x, 4);
        }
        if (!empty($p['carried'])) $row['carried'] = true;
        $out[$oid] = $row;
    }
    return $out;
}
/* Sonderpreis „solange der Vorrat reicht“ (Artikel mit kurzem oder überschrittenem MHD):
   $item['sale'] = {value: Grundsonderpreis für alle Angebote, offers?: {<Angebots-ID>: {value} | {status: 'none'}}}.
   Ein Sonderposten ohne Bestand (laut letzter Bestandsliste) wird in allen Angeboten automatisch ausgeblendet. */
function clean_money($x, string $what): float
{
    if (!is_int($x) && !is_float($x)) throw new InvalidArgumentException("$what fehlt.");
    $x = (float)$x;
    if ($x < 0 || $x >= 100000) throw new InvalidArgumentException("$what außerhalb des gültigen Bereichs.");
    return round($x, 4);
}
function clean_sale($v, string $where, array $known): ?array
{
    if (!is_array($v) || !array_key_exists('value', $v)) return null;
    $out = ['value' => clean_money($v['value'], "Sonderpreis ($where)")];
    $offers = [];
    foreach (is_array($v['offers'] ?? null) ? $v['offers'] : [] as $oid => $o) {
        $oid = (string)$oid;
        if (!is_array($o) || ($oid !== OFFER_STD && !in_array($oid, $known, true))) continue;
        if (($o['status'] ?? '') === 'none') $offers[$oid] = ['status' => 'none'];
        elseif (array_key_exists('value', $o)) $offers[$oid] = ['value' => clean_money($o['value'], "Sonderpreis ($where)")];
    }
    if ($offers) $out['offers'] = $offers;
    $since = s($v['since'] ?? null, 30);
    if ($since) $out['since'] = $since;
    return $out;
}
function sale_for(array $it, string $oid): ?float
{
    $s = $it['sale'] ?? null;
    if (!is_array($s) || !isset($s['value'])) return null;
    $o = $s['offers'][$oid] ?? null;
    if (is_array($o)) return ($o['status'] ?? '') === 'none' ? null : (float)$o['value'];
    return (float)$s['value'];
}
/* Artikelnummern mit eingelagertem Bestand (null = keine Bestandsliste vorhanden) */
function stock_codes(): ?array
{
    static $codes = false;
    if ($codes !== false) return $codes;
    $st = store_read('bestand');
    if (!is_array($st) || empty($st['articles'])) return $codes = null;
    $codes = [];
    foreach ($st['articles'] as $a) if ((float)($a['kg'] ?? 0) > 0) $codes[code_key((string)$a['code'])] = true;
    return $codes;
}
function sold_out(array $it): bool
{
    $codes = stock_codes();
    $c = (string)($it['code'] ?? '');
    return $codes !== null && $c !== '' && !isset($codes[code_key($c)]);
}
/* Angebot für die Auslieferung: nur Preise dieses Angebots, keine Kundenpreise anderer Angebote,
   keine ausgeblendeten Artikel, Sonderpreise aufgelöst (ohne Angaben zu anderen Angeboten) */
function offer_resolve(array $m, array $def): array
{
    $std = $def['id'] === OFFER_STD;
    $items = [];
    foreach ($m['items'] ?? [] as $it) {
        $v = $it['variants'][$def['id']] ?? null;
        $sale = sale_for($it, $def['id']);
        unset($it['variants'], $it['sale']);
        if ($v && $v['status'] === 'hidden') continue;
        if ($sale !== null && sold_out($it)) continue;   // Sonderposten ausverkauft
        $regular = $it['price'];
        if ($std) {
            // Wochenangebot: Grundpreis und Zusatzpreise bleiben
        } elseif ($v) {
            $regular = $v['status'] === 'value' ? ['status' => 'value', 'value' => $v['value']] : ['status' => 'request'];
            $it['price'] = $regular;
            $it['altPrices'] = [];
        } elseif (($def['fallback'] ?? 'standard') === 'hidden') {
            if ($sale === null) continue;
            $regular = null;
        }
        if ($sale !== null) {
            $it['price'] = ['status' => 'value', 'value' => $sale];
            $it['altPrices'] = [];
            $it['sale'] = true;
            if ($regular && ($regular['status'] ?? '') === 'value' && (float)$regular['value'] > $sale) $it['regular'] = (float)$regular['value'];
        }
        $items[] = $it;
    }
    $used = [];
    foreach ($items as $it) $used[$it['groupId']] = true;
    $m['groups'] = array_values(array_filter($m['groups'] ?? [], function ($g) use ($used) { return isset($used[$g['id']]); }));
    $secs = [];
    foreach ($m['groups'] as $g) if (($g['section'] ?? '') !== '' && !in_array($g['section'], $secs, true)) $secs[] = $g['section'];
    $m['sections'] = $secs;
    $m['items'] = $items;
    $m['meta']['offerId'] = $def['id'];
    $m['meta']['offerName'] = $def['name'];
    return $m;
}

/* Übernimmt nur bekannte Felder in bekannten Formaten */
function clean_model($m, bool $strict): array
{
    if (!is_array($m)) throw new InvalidArgumentException('Daten fehlen.');
    $meta = is_array($m['meta'] ?? null) ? $m['meta'] : [];
    $week = $meta['week'] ?? null;
    $year = $meta['year'] ?? null;
    $week = is_int($week) && $week >= 1 && $week <= 53 ? $week : null;
    $year = is_int($year) && $year >= 2000 && $year <= 2100 ? $year : null;
    if ($strict && ($week === null || $year === null)) throw new InvalidArgumentException('Kalenderwoche und Jahr müssen angegeben sein.');
    $outMeta = ['week' => $week, 'year' => $year, 'notice' => s($meta['notice'] ?? '', 120) ?? ''];
    foreach (['title' => 200, 'source' => 200, 'sheetName' => 100] as $f => $max) {
        $v = s($meta[$f] ?? null, $max);
        if ($v !== null && $v !== '') $outMeta[$f] = $v;
    }

    $groups = [];
    $gids = [];
    foreach (array_slice(is_array($m['groups'] ?? null) ? $m['groups'] : [], 0, 1000) as $g) {
        if (!is_array($g)) continue;
        $id = s($g['id'] ?? null, 40, false);
        if ($id === null || !preg_match('/^[A-Za-z0-9_-]+$/', $id) || isset($gids[$id])) throw new InvalidArgumentException('Ungültige Gruppen-ID.');
        $name = s($g['name'] ?? null, 200, false);
        if ($name === null) throw new InvalidArgumentException('Eine Angebotsgruppe hat keinen Namen.');
        $gids[$id] = true;
        $groups[] = ['id' => $id, 'name' => $name, 'section' => s($g['section'] ?? '', 200) ?? ''];
    }

    $items = [];
    $iids = [];
    $known = offer_ids();
    $src = is_array($m['items'] ?? null) ? $m['items'] : [];
    if (count($src) > 5000) throw new InvalidArgumentException('Zu viele Artikel (max. 5000).');
    foreach ($src as $it) {
        if (!is_array($it)) continue;
        $id = s($it['id'] ?? null, 40, false);
        if ($id === null || !preg_match('/^[A-Za-z0-9_-]+$/', $id) || isset($iids[$id])) throw new InvalidArgumentException('Ungültige Artikel-ID.');
        $iids[$id] = true;
        $name = s($it['name'] ?? null, 200, false);
        if ($name === null) throw new InvalidArgumentException('Ein Artikel hat keine Bezeichnung.');
        $code = s($it['code'] ?? null, 20);
        if ($code === '') $code = null;
        if ($code !== null && !preg_match('#^[0-9A-Za-z./-]+$#', $code)) throw new InvalidArgumentException("Artikelnummer „{$code}“ ist ungültig.");
        $gid = s($it['groupId'] ?? null, 40);
        if ($gid === null || !isset($gids[$gid])) throw new InvalidArgumentException("Artikel „{$name}“ ist keiner gültigen Gruppe zugeordnet.");
        $cat = $it['category'] ?? '';
        if (!in_array($cat, CATEGORIES, true)) $cat = 'Sonstiges';
        $cond = $it['condition'] ?? '';
        if (!in_array($cond, CONDITIONS, true)) $cond = 'unbekannt';
        $origin = s($it['origin'] ?? null, 60);
        $alts = [];
        foreach (array_slice(is_array($it['altPrices'] ?? null) ? $it['altPrices'] : [], 0, 5) as $ap) $alts[] = clean_price($ap, $name);
        $row = [
            'id' => $id, 'code' => $code, 'name' => $name,
            'category' => $cat, 'origin' => ($origin === '' ? null : $origin), 'condition' => $cond,
            'groupId' => $gid, 'price' => clean_price($it['price'] ?? null, $name), 'altPrices' => $alts,
        ];
        $nr = s($it['nameRaw'] ?? null, 300);
        if ($nr !== null && $nr !== '' && $nr !== $name) $row['nameRaw'] = $nr;
        $cell = s($it['cell'] ?? null, 20);
        if ($cell !== null && $cell !== '') $row['cell'] = $cell;
        $vars = clean_variants($it['variants'] ?? null, $name, $known);
        if ($vars) $row['variants'] = $vars;
        $sale = clean_sale($it['sale'] ?? null, $name, $known);
        if ($sale) $row['sale'] = $sale;
        $items[] = $row;
    }
    if ($strict && !$items) throw new InvalidArgumentException('Das Angebot enthält keine Artikel.');
    $used = [];
    foreach ($items as $it) $used[$it['groupId']] = true;
    if ($strict) $groups = array_values(array_filter($groups, function ($g) use ($used) { return isset($used[$g['id']]); }));
    $sections = [];
    foreach ($groups as $g) if ($g['section'] !== '' && !in_array($g['section'], $sections, true)) $sections[] = $g['section'];
    return ['meta' => $outMeta, 'sections' => $sections, 'groups' => $groups, 'items' => $items];
}

/* ---------------- Gemeinsames Bearbeiten des Entwurfs ----------------
   Jede Speicherung erhöht die Revision. Nach Veröffentlichen/Verwerfen bleibt die Revision in
   „entwurf-stand“ erhalten, damit veraltete Fenster den Entwurf nicht mit altem Stand neu anlegen. */
function draft_rev(?array $draft): int
{
    if ($draft !== null) return (int)($draft['rev'] ?? 0);
    $st = store_read('entwurf-stand');
    return is_array($st) ? (int)($st['rev'] ?? 0) : 0;
}
function draft_end(?array $draft, string $why): int
{
    $rev = draft_rev($draft) + 1;
    store_write('entwurf-stand', ['rev' => $rev, 'reason' => $why, 'by' => current_user()['name'] ?? '', 'at' => now()]);
    store_delete('entwurf');
    return $rev;
}
function draft_conflict(?array $draft): void
{
    $st = $draft === null ? store_read('entwurf-stand') : null;
    $by = (string)($draft['savedBy'] ?? ($st['by'] ?? ''));
    $what = $draft === null && is_array($st) ? 'den Entwurf ' . ($st['reason'] ?? 'geändert') : 'den Entwurf geändert';
    respond(['ok' => false, 'conflict' => true, 'revision' => draft_rev($draft), 'by' => $by,
             'error' => ($by !== '' ? $by : 'Jemand anderes') . ' hat inzwischen ' . $what . '.'], 409);
}
