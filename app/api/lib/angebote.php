<?php
declare(strict_types=1);
/* Angebote, Kundenpreise, Sonderpreise, Datenmodell, gemeinsames Bearbeiten */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Mehrere Angebote ----------------
   Alle Angebote teilen sich eine Artikelliste im Entwurf; je Angebot steht fest, welche Artikel es enthält:
   – Wochenangebot: alle Artikel außer variants.std = {status: 'hidden'} (Preis in $item['price']).
   – Kundenangebot mit Regel 'hidden' („eigene Artikelliste“, Voreinstellung für neue Angebote): nur Artikel mit
     eigenem Eintrag $item['variants'][<Angebots-ID>] = {status: value|request, value?, carried?}. Jedes Angebot steht
     für sich – Artikel anderer Angebote (auch mit Sonderpreis) erscheinen dort nie.
   – Kundenangebot mit Regel 'standard' (bisheriges Verhalten, „folgt dem Wochenangebot“): alle Artikel, ohne eigenen
     Eintrag mit dem Standardpreis; variants[<id>] = {status: 'hidden'} blendet einen Artikel dort aus.
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
/* IDs nicht (mehr) vorhandener Angebote, unter denen noch Daten stehen: Kundenpreise/Sonderpreise im veröffentlichten
   Angebot oder Entwurf, direkte Freischaltungen bei Kunden. Eine neue Angebots-ID darf keine davon sein (offers_save). */
function angebot_ids_mit_resten(array $vorhanden): array
{
    $ids = [];
    foreach (['angebot', 'entwurf'] as $doc) {
        $d = store_read($doc) ?? [];
        foreach ($d['items'] ?? [] as $it) {
            foreach (array_keys(is_array($it['variants'] ?? null) ? $it['variants'] : []) as $k) $ids[(string)$k] = true;
            foreach (array_keys(is_array($it['sale']['offers'] ?? null) ? $it['sale']['offers'] : []) as $k) $ids[(string)$k] = true;
            foreach (array_keys(is_array($it['namen'] ?? null) ? $it['namen'] : []) as $k) $ids[(string)$k] = true;   // eigene Bezeichnungen
        }
        foreach (array_keys(is_array($d['meta']['werbung'] ?? null) ? $d['meta']['werbung'] : []) as $k) $ids[(string)$k] = true;   // Werbung
    }
    foreach (customers_load()['customers'] as $c) foreach (is_array($c['angebote'] ?? null) ? $c['angebote'] : [] as $k) $ids[(string)$k] = true;
    unset($ids[OFFER_STD]);
    return array_values(array_diff(array_keys($ids), $vorhanden));
}
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
/* Werbung je Angebot: $model['meta']['werbung'] = {<Angebots-ID>: {titel, text?, artikel: [{id, text?}], weitere?: [{titel,
   text?, artikel}]}} – Artikel, die im Angebot oben in einem farbigen Block stehen und in der Liste hervorgehoben sind.
   Höchstens zwei Blöcke je Angebot: der erste steht in den Feldern des Eintrags (ältere Fassungen lesen nur ihn), eine
   weitere Werbung in „weitere“ (Kundenseite: rechts daneben). Gilt nur für das eigene Angebot (keine Übernahme durch
   Angebote, die dem Wochenangebot folgen); ausgeliefert wird nur der eigene Eintrag (offer_resolve). */
const WERBUNG_MAX = 12;       // Artikel je Werbung
const WERBUNG_BLOECKE = 2;    // Werbungen je Angebot
/* Blöcke eines Eintrags in Reihenfolge: erster Block, danach „weitere“ (ungeprüft) */
function werbung_bloecke($e): array
{
    if (!is_array($e)) return [];
    $l = [$e];
    foreach (is_array($e['weitere'] ?? null) ? array_values($e['weitere']) : [] as $b) if (is_array($b)) $l[] = $b;
    return $l;
}
/* Blöcke wieder zu einem Eintrag zusammensetzen (leere fallen weg, ein späterer rückt nach vorn); null = keine Werbung */
function werbung_eintrag(array $bloecke): ?array
{
    $bloecke = array_slice(array_values(array_filter($bloecke)), 0, WERBUNG_BLOECKE);
    if (!$bloecke) return null;
    $row = $bloecke[0];
    if (count($bloecke) > 1) $row['weitere'] = array_slice($bloecke, 1);
    return $row;
}
function werbung_block_clean(array $e, array $iids): ?array
{
    $art = [];
    foreach (array_slice(is_array($e['artikel'] ?? null) ? $e['artikel'] : [], 0, 200) as $a) {
        if (!is_array($a)) continue;
        $id = s($a['id'] ?? null, 40, false);
        if ($id === null || !isset($iids[$id]) || isset($art[$id])) continue;   // gelöschte Artikel fallen weg
        $art[$id] = ['id' => $id];
        $t = s($a['text'] ?? null, 40);
        if ($t !== null && $t !== '') $art[$id]['text'] = $t;
        if (count($art) >= WERBUNG_MAX) break;
    }
    if (!$art) return null;
    $row = ['titel' => s($e['titel'] ?? '', 80) ?? '', 'artikel' => array_values($art)];
    $t = s($e['text'] ?? null, 240);
    if ($t !== null && $t !== '') $row['text'] = $t;
    return $row;
}
function clean_werbung($w, array $known, array $iids): array
{
    $out = [];
    if (!is_array($w)) return $out;
    foreach ($w as $oid => $e) {
        $oid = (string)$oid;   // numerische Angebots-IDs kommen als Zahl an
        if (!is_array($e) || ($oid !== OFFER_STD && !in_array($oid, $known, true))) continue;   // gelöschte Angebote fallen weg
        $row = werbung_eintrag(array_map(function ($b) use ($iids) { return werbung_block_clean($b, $iids); }, array_slice(werbung_bloecke($e), 0, 10)));
        if ($row) $out[$oid] = $row;
    }
    return $out;
}
/* Empfehlung (bis 11/2026 „Sonderpreis“) je Artikel und Angebot:
   $item['sale'] = {value: Empfehlungspreis für alle Angebote | mark: true (ohne Preisänderung),
                    offers?: {<Angebots-ID>: {value} | {status: 'mark'} | {status: 'none'}}, since?}.
   Ohne Eintrag in offers gilt der Grundwert. Mit Preis: Sonderposten „solange der Vorrat reicht“ – Kunden sehen den
   bisherigen Preis durchgestrichen, ohne Bestand (laut letzter Bestandsliste) wird der Artikel in allen Angeboten
   ausgeblendet. Ohne Preis (mark): der Artikel wird nur hervorgehoben, Preis und Sichtbarkeit bleiben unverändert.
   Ältere Fassungen kennen nur Einträge mit Preis und verwerfen die übrigen (GR-006: nur erweitert). */
function clean_money($x, string $what): float
{
    if (!is_int($x) && !is_float($x)) throw new InvalidArgumentException("$what fehlt.");
    $x = (float)$x;
    if ($x < 0 || $x >= 100000) throw new InvalidArgumentException("$what außerhalb des gültigen Bereichs.");
    return round($x, 4);
}
function clean_sale($v, string $where, array $known): ?array
{
    if (!is_array($v)) return null;
    if (array_key_exists('value', $v) && $v['value'] !== null) $out = ['value' => clean_money($v['value'], "Empfehlungspreis ($where)")];
    elseif (!empty($v['mark'])) $out = ['mark' => true];
    else return null;
    $offers = [];
    foreach (is_array($v['offers'] ?? null) ? $v['offers'] : [] as $oid => $o) {
        $oid = (string)$oid;
        if (!is_array($o) || ($oid !== OFFER_STD && !in_array($oid, $known, true))) continue;
        $st = $o['status'] ?? '';
        if ($st === 'none' || $st === 'mark') $offers[$oid] = ['status' => $st];
        elseif (array_key_exists('value', $o)) $offers[$oid] = ['value' => clean_money($o['value'], "Empfehlungspreis ($where)")];
    }
    if ($offers) $out['offers'] = $offers;
    $since = s($v['since'] ?? null, 30);
    if ($since) $out['since'] = $since;
    return $out;
}
/* Empfehlung eines Artikels in einem Angebot: null = keine, sonst ['preis' => Empfehlungspreis | null (nur hervorheben)] */
function empfehlung_fuer(array $it, string $oid): ?array
{
    $s = $it['sale'] ?? null;
    if (!is_array($s) || (!isset($s['value']) && empty($s['mark']))) return null;
    $o = $s['offers'][$oid] ?? null;
    if (is_array($o)) {
        $st = $o['status'] ?? '';
        if ($st === 'none') return null;
        if ($st === 'mark') return ['preis' => null];
        if (isset($o['value'])) return ['preis' => (float)$o['value']];
    }
    return ['preis' => isset($s['value']) ? (float)$s['value'] : null];
}
/* Empfehlungspreis (Sonderposten „solange der Vorrat reicht“) eines Artikels in einem Angebot, sonst null */
function sale_for(array $it, string $oid): ?float
{
    $e = empfehlung_fuer($it, $oid);
    return $e ? $e['preis'] : null;
}
/* Artikelnummern mit eingelagertem Bestand (null = keine Bestandsliste vorhanden) */
function stock_codes(): ?array
{
    static $codes = false;
    if ($codes !== false) return $codes;
    if (!store_sichtbar('bestand')) {   // Kundenseite ab Trennstufe 2: nur der Auszug ohne Mengen (lib/bestand.php)
        $l = artikelauszug()['lager'] ?? null;
        return $codes = is_array($l) ? array_fill_keys(array_map('strval', $l), true) : null;
    }
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
        $emp = empfehlung_fuer($it, $def['id']);
        $sale = $emp ? $emp['preis'] : null;
        $eigenerName = !$std && is_array($it['namen'] ?? null) ? trim((string)($it['namen'][$def['id']] ?? '')) : '';
        unset($it['variants'], $it['sale'], $it['cell'], $it['namen']);   // Zelladresse der Excel-Datei ist intern; Bezeichnungen anderer Angebote nie
        if ($eigenerName !== '') $it['name'] = $eigenerName;   // eigene Bezeichnung in diesem Angebot, sonst der Basiswert
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
            continue;   // eigene Artikelliste: ohne eigenen Eintrag nicht im Angebot – auch nicht mit Sonderpreis
        }
        if ($sale !== null) {
            $it['price'] = ['status' => 'value', 'value' => $sale];
            $it['altPrices'] = [];
            $it['sale'] = true;
            if ($regular && ($regular['status'] ?? '') === 'value' && (float)$regular['value'] > $sale) $it['regular'] = (float)$regular['value'];
        } elseif ($emp !== null) {
            $it['empfehlung'] = true;   // Empfehlung ohne Preisänderung: nur hervorheben (Preis und Sichtbarkeit unverändert)
        }
        $items[] = $it;
    }
    $used = [];
    foreach ($items as $it) $used[$it['groupId']] = true;
    $m['groups'] = array_values(array_filter($m['groups'] ?? [], function ($g) use ($used) { return isset($used[$g['id']]); }));
    foreach ($m['groups'] as $i => $g) unset($m['groups'][$i]['vk']);   // VK-Gruppe der Angebotsgruppe ist intern
    $secs = [];
    foreach ($m['groups'] as $g) if (($g['section'] ?? '') !== '' && !in_array($g['section'], $secs, true)) $secs[] = $g['section'];
    $m['sections'] = $secs;
    $m['items'] = $items;
    unset($m['meta']['source'], $m['meta']['sheetName']);   // Dateiname/Blatt der Excel-Datei sind intern
    // Werbung: nur der Eintrag dieses Angebots und nur Artikel, die ausgeliefert werden – nie die anderer Angebote.
    // Bis zu zwei Blöcke (erster im Eintrag, zweiter in „weitere“); ein leerer erster Block rückt den zweiten nach vorn.
    $w = is_array($m['meta']['werbung'] ?? null) ? ($m['meta']['werbung'][$def['id']] ?? null) : null;
    unset($m['meta']['werbung']);
    if (is_array($w)) {
        $da = [];
        foreach ($items as $it) $da[(string)$it['id']] = true;
        $bl = [];
        foreach (werbung_bloecke($w) as $b) {
            $art = [];
            foreach (is_array($b['artikel'] ?? null) ? $b['artikel'] : [] as $a) {
                $id = (string)($a['id'] ?? '');
                if (!isset($da[$id])) continue;
                $art[] = array_filter(['id' => $id, 'text' => (string)($a['text'] ?? '')], function ($x) { return $x !== ''; });
            }
            $bl[] = $art ? array_filter(['titel' => (string)($b['titel'] ?? ''), 'text' => (string)($b['text'] ?? ''), 'artikel' => $art], function ($x) { return $x !== ''; }) : null;
        }
        $e = werbung_eintrag($bl);
        if ($e) $m['meta']['werbung'] = $e;
    }
    $m['meta']['offerId'] = $def['id'];
    $m['meta']['offerName'] = $def['name'];
    return $m;
}

/* Kalenderwoche nach ISO 8601: KW 53 gibt es nur in Jahren mit 53 Wochen (der 28.12. liegt immer in der letzten) */
function kw_gueltig(int $woche, int $jahr): bool
{
    return $woche >= 1 && $woche <= (int)(new DateTimeImmutable(sprintf('%04d-12-28', $jahr)))->format('W');
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
    // Entwurf behält die Angabe (nichts geht verloren), veröffentlicht wird nur eine Woche, die es gibt
    if ($strict && !kw_gueltig($week, $year)) throw new InvalidArgumentException("Die KW $week/$year gibt es nicht – das Jahr hat nur 52 Kalenderwochen.");
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
        $row = ['id' => $id, 'name' => $name, 'section' => s($g['section'] ?? '', 200) ?? ''];
        // optional: VK-Gruppe (Stammdaten), aus der „Artikel hinzufügen“ die Angebotsgruppe wählt (ältere Fassungen verwerfen das Feld)
        $vk = is_string($g['vk'] ?? null) || is_int($g['vk'] ?? null) ? trim((string)$g['vk']) : '';
        if ($vk !== '' && preg_match('/^[0-9A-Za-z._-]{1,10}$/', $vk)) $row['vk'] = $vk;
        $groups[] = $row;
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
        // optional: eigene Bezeichnung je Kundenangebot (ältere Fassungen verwerfen das Feld; dann gilt wieder „name“)
        $namen = angebotsnamen_clean($it['namen'] ?? null, $name, $known);
        if ($namen) $row['namen'] = $namen;
        $sale = clean_sale($it['sale'] ?? null, $name, $known);
        if ($sale) $row['sale'] = $sale;
        $items[] = $row;
    }
    if ($strict && !$items) throw new InvalidArgumentException('Das Angebot enthält keine Artikel.');
    $werbung = clean_werbung($meta['werbung'] ?? null, $known, $iids);   // optional (ältere Fassungen verwerfen das Feld)
    if ($werbung) $outMeta['werbung'] = $werbung;
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

/* ---------------- Veröffentlichen und Änderungsliste (Schnittstelle des Angebots) ----------------
   Eine Stelle für die Aktion publish (Eingabebereich, ältere Fenster, Tests) und das Modul Versand (versand_veroeffentlichen):
   $modell = null veröffentlicht den gespeicherten Entwurf – das Modul Versand hat das Modell des Editors nicht. $revision
   (null = ungeprüft) muss zur Revision des Entwurfs passen, sonst 409 (draft_conflict). Rechte prüft der Aufrufer (GR-103). */
function angebot_veroeffentlichen(?array $modell, $revision): array
{
    global $CFG;
    $keep = (int)$CFG['keep_versions'];
    return with_lock('entwurf', function () use ($modell, $revision, $keep) {
        $dr = store_read('entwurf');
        if ($revision !== null && (int)$revision !== draft_rev($dr)) draft_conflict($dr);
        if ($modell === null) {
            if (!$dr) respond(['ok' => false, 'code' => 'nichts_offen', 'revision' => draft_rev($dr),
                               'error' => 'Es gibt keine offenen Änderungen – veröffentlicht ist bereits der aktuelle Stand.'], 409);
            $modell = $dr;
        }
        $model = clean_model($modell, true);
        $prev = store_read('angebot');
        if ($prev) {
            $id = gmdate('Ymd-His') . '-' . bin2hex(random_bytes(3));
            store_write('versionen/' . $id, $prev);
            $list = store_names('versionen');
            rsort($list);
            foreach (array_slice($list, $keep) as $old) store_delete($old);
        }
        // streng steigend mit Millisekunden (wie einzel_stand): zwei Veröffentlichungen in derselben Sekunde bekommen
        // verschiedene Stände – ein Bestellwunsch auf der ersten Fassung wird dann nicht mit der zweiten gerechnet
        $model['publishedAt'] = einzel_stand(is_array($prev) && is_string($prev['publishedAt'] ?? null) ? $prev['publishedAt'] : null);
        store_write('angebot', $model);
        $rev = draft_end($dr, 'veröffentlicht');
        $h = history_from_model($model, 'Veröffentlichung', $model['publishedAt']);
        if ($h) { $hid = history_id($h['week'], $h['year']); store_write('historie/' . $hid, $h); history_undelete($hid); }
        $d = $prev ? changes_between($prev, $model) : [];
        audit('publish', 'KW ' . $model['meta']['week'] . '/' . $model['meta']['year'] . ' veröffentlicht – ' . count($model['items']) . ' Artikel' . ($prev ? ' (' . changes_summary($d) . ')' : ' (erste Veröffentlichung)'), array_slice($d, 0, 2000));
        return ['publishedAt' => $model['publishedAt'], 'revision' => $rev, 'week' => $model['meta']['week'], 'year' => $model['meta']['year'], 'artikel' => count($model['items'])];
    });
}
/* Weicht der Aufbau (Reihenfolge der Gruppen, Bereich je Gruppe, Gruppe und Reihenfolge der Artikel) vom veröffentlichten Stand
   ab? Gleiche Regel wie aufbauGeaendert() im Editor (admin.js): nur Gruppen und Artikel, die es in beiden Ständen gibt. */
function angebot_aufbau_geaendert(array $pub, array $neu): bool
{
    $pg = []; foreach ($pub['groups'] ?? [] as $g) $pg[(string)$g['id']] = (string)$g['name'];
    $used = []; foreach ($neu['items'] ?? [] as $it) $used[(string)$it['groupId']] = true;
    $neuG = array_values(array_filter($neu['groups'] ?? [], fn($g) => isset($used[(string)$g['id']])));
    $mg = []; foreach ($neuG as $g) $mg[(string)$g['id']] = (string)$g['name'];
    $sig = function (array $gs, array $other): string {
        $o = [];
        foreach ($gs as $g) if (($other[(string)$g['id']] ?? null) === (string)$g['name']) $o[] = $g['id'] . "\x01" . ($g['section'] ?? '');
        return implode("\x02", $o);
    };
    if ($sig($pub['groups'] ?? [], $mg) !== $sig($neuG, $pg)) return true;
    $reihe = function (array $m, array $other): string {
        $gi = []; foreach ($m['groups'] ?? [] as $i => $g) $gi[(string)$g['id']] = $i;
        $x = [];
        foreach ($m['items'] ?? [] as $i => $it) if (isset($other[(string)$it['id']])) $x[] = [$gi[(string)$it['groupId']] ?? PHP_INT_MAX, $i, $it['id'] . '@' . $it['groupId']];
        usort($x, fn($a, $b) => [$a[0], $a[1]] <=> [$b[0], $b[1]]);
        return implode("\x02", array_column($x, 2));
    };
    $idsN = []; foreach ($neu['items'] ?? [] as $it) $idsN[(string)$it['id']] = true;
    $idsP = []; foreach ($pub['items'] ?? [] as $it) $idsP[(string)$it['id']] = true;
    return $reihe($pub, $idsN) !== $reihe($neu, $idsP);
}
/* Unveröffentlichte Änderungen des Entwurfs als Zeilen für die Liste „Veröffentlichen“ (Modul Versand). Grundlage ist
   changes_between() – dieselbe Liste, die das Protokoll beim Veröffentlichen festhält. Gezählt wird wie am Knopf des Editors:
   Kopfdaten einmal, je Artikel eine Preisänderung oder eine Bearbeitung, je Angebot und Artikel ein Angebotspreis, je Artikel
   eine Empfehlung, je Angebot die Werbung, der Aufbau einmal. „angebot“ = Angebot, das die Zeile betrifft ('' = alle).
   Rückgabe: erste (noch nichts veröffentlicht), entwurf (bool), revision, anzahl, zeilen [{art, angebot, code, name, von, nach,
   zusatz}], jeAngebot {Angebots-ID bzw. '' → Anzahl}, arten {art → Anzahl}. Zeilen enthalten Preise – der Aufrufer liefert
   sie nur mit Modulzugang Angebot aus. */
function angebot_aenderungen(?array $pub = null, ?array $dr = null): array
{
    $pub = $pub ?? store_read('angebot');
    $dr = $dr ?? store_read('entwurf');
    $out = ['erste' => !$pub, 'entwurf' => (bool)$dr, 'revision' => draft_rev($dr), 'anzahl' => 0, 'zeilen' => [], 'jeAngebot' => [], 'arten' => []];
    if (!$dr) return $out;
    if (!$pub) { $out['anzahl'] = count($dr['items'] ?? []); $out['arten'] = ['neu' => $out['anzahl']]; $out['jeAngebot'] = ['' => $out['anzahl']]; return $out; }
    $zeilen = []; $kopf = []; $jeArtikel = []; $aufbau = false;
    foreach (changes_between($pub, $dr) as $c) {
        [$id, $f] = explode('|', (string)$c['k'], 2) + [1 => ''];
        $z = ['art' => '', 'angebot' => '', 'code' => (string)$c['code'], 'name' => (string)$c['name'], 'von' => (string)$c['from'], 'nach' => (string)$c['to'], 'zusatz' => ''];
        if ($id === 'm' && strpos($f, 'w:') === 0) { $z['art'] = 'werbung'; $z['angebot'] = substr($f, 2); $z['name'] = 'Werbung'; $zeilen[] = $z; }
        elseif ($id === 'm') $kopf[] = $c;
        elseif ($f === 'groupId' || in_array($c['f'], ['Bereich', 'Gruppenname'], true)) $aufbau = true;   // Gruppe eines Artikels, Bereich oder Name einer Gruppe
        elseif ($f === '+') { $z['art'] = 'neu'; $zeilen[] = $z; }
        elseif ($f === '-') { $z['art'] = 'entfernt'; $zeilen[] = $z; }
        elseif (strpos($f, 'v:') === 0) { $oid = substr($f, 2); $z['art'] = $oid === OFFER_STD ? 'sichtbar' : 'angebotspreis'; $z['angebot'] = $oid; $zeilen[] = $z; }
        elseif ($f === 'sale') { $z['art'] = 'empfehlung'; $zeilen[] = $z; }
        else $jeArtikel[$id][] = $c;   // Preis, Preisbezeichnung, Zusatzpreise, Stammfelder, eigene Bezeichnung je Angebot
    }
    foreach ($jeArtikel as $liste) {
        $preis = null; $felder = [];
        foreach ($liste as $c) {
            $f = explode('|', (string)$c['k'], 2)[1] ?? '';
            if ($f === 'price') $preis = $c;
            else $felder[] = $c['f'] . ': ' . ($c['from'] !== '' ? $c['from'] : '—') . ' → ' . ($c['to'] !== '' ? $c['to'] : '—');
        }
        $erste = $preis ?? $liste[0];
        $zeilen[] = ['art' => $preis ? 'preis' : 'bearbeitet', 'angebot' => '', 'code' => (string)$erste['code'], 'name' => (string)$erste['name'],
                     'von' => $preis ? (string)$preis['from'] : '', 'nach' => $preis ? (string)$preis['to'] : '', 'zusatz' => mb_substr(implode(' · ', $felder), 0, 400)];
    }
    if ($kopf) array_unshift($zeilen, ['art' => 'kopf', 'angebot' => '', 'code' => '', 'name' => implode(' · ', array_map(fn($c) => (string)$c['f'], $kopf)),
        'von' => implode(' · ', array_map(fn($c) => $c['f'] === 'Kalenderwoche' ? 'KW ' . $c['from'] : (string)$c['from'], $kopf)),
        'nach' => implode(' · ', array_map(fn($c) => $c['f'] === 'Kalenderwoche' ? 'KW ' . $c['to'] : (string)$c['to'], $kopf)), 'zusatz' => '']);
    if ($aufbau || angebot_aufbau_geaendert($pub, $dr)) $zeilen[] = ['art' => 'aufbau', 'angebot' => '', 'code' => '', 'name' => 'Reihenfolge der Bereiche, Gruppen oder Artikel geändert', 'von' => '', 'nach' => '', 'zusatz' => 'gilt für alle Angebote'];
    foreach ($zeilen as $z) {
        $out['arten'][$z['art']] = ($out['arten'][$z['art']] ?? 0) + 1;
        $out['jeAngebot'][$z['angebot']] = ($out['jeAngebot'][$z['angebot']] ?? 0) + 1;
    }
    $out['anzahl'] = count($zeilen);
    $out['zeilen'] = array_slice($zeilen, 0, 2000);
    return $out;
}
/* Stand des Angebots für das Modul Versand – nur Zahlen und Namen, keine Preise: veröffentlichter Stand und Entwurf (Woche,
   Zeitpunkt, wer zuletzt gespeichert hat), wer gerade im Eingabebereich arbeitet, und je Angebot Name, Sichtbarkeit,
   Artikelzahl (Entwurf, sonst veröffentlicht – wie Kunden es nach dem Veröffentlichen sehen) und veröffentlichte Sonderposten. */
function angebot_stand(): array
{
    $pub = store_read('angebot');
    $dr = store_read('entwurf');
    $kopf = function (?array $m): ?array {
        if (!$m) return null;
        return ['week' => (int)($m['meta']['week'] ?? 0), 'year' => (int)($m['meta']['year'] ?? 0), 'artikel' => count($m['items'] ?? [])];
    };
    $now = time();
    $da = [];
    foreach ((array)(store_read('anwesenheit') ?? []) as $v) if (is_array($v) && (int)($v['at'] ?? 0) >= $now - 45) $da[] = (string)($v['name'] ?? '');
    sort($da);
    $angebote = [];
    $modell = $dr ?: $pub;
    foreach (array_merge([offer_def(OFFER_STD)], offers_load()['offers']) as $def) {
        $n = 0; $sp = 0;
        try { if ($modell) $n = count(offer_resolve($modell, $def)['items']); } catch (Throwable $e) { $n = 0; }
        try { if ($pub) $sp = count(restposten_items($def)); } catch (Throwable $e) { $sp = 0; }
        $angebote[] = ['id' => (string)$def['id'], 'name' => (string)$def['name'], 'std' => $def['id'] === OFFER_STD,
                       'oeffentlich' => $def['id'] === OFFER_STD && std_public(), 'artikel' => $n, 'sonderposten' => $sp];
    }
    return ['veroeffentlicht' => $pub ? $kopf($pub) + ['publishedAt' => $pub['publishedAt'] ?? null] : null,
            'entwurf' => $dr ? $kopf($dr) + ['savedAt' => $dr['savedAt'] ?? null, 'savedBy' => (string)($dr['savedBy'] ?? '')] : null,
            'anwesend' => array_values(array_unique(array_filter($da, 'strlen'))), 'angebote' => $angebote];
}
