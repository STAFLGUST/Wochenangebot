<?php
declare(strict_types=1);
/* Bestandsliste und Stammdaten */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Bestand ---------------- */

/* Nur lesend: exakte ISO-Wochen, keine Entwurfspreise und kein Rückgriff auf ältere Wochen.
   Historie hat Vorrang; alte Veröffentlichungen ergänzen nur noch nicht archivierte Wochen. */
function stock_week_prices(?DateTimeImmutable $today = null): array
{
    $today = ($today ?? new DateTimeImmutable('now', new DateTimeZone('Europe/Berlin')))->setTimezone(new DateTimeZone('Europe/Berlin'));
    $dates = [$today, $today->modify('-7 days')];
    $deleted = store_read('historie_geloescht') ?? [];
    $weeks = [];
    foreach ($dates as $date) {
        $week = (int)$date->format('W'); $year = (int)$date->format('o');
        $id = history_id($week, $year);
        $h = store_read('historie/' . $id);
        if (!$h && !in_array($id, $deleted, true)) {
            $sources = ['angebot'];
            foreach (store_names('versionen') as $f) $sources[] = 'versionen/' . basename($f);
            foreach ($sources as $source) {
                $m = store_read($source);
                if (!$m || ($m['meta']['week'] ?? null) !== $week || ($m['meta']['year'] ?? null) !== $year) continue;
                $candidate = history_from_model($m, 'Veröffentlichung', $m['publishedAt'] ?? null);
                if (!$h || strcmp((string)$candidate['savedAt'], (string)$h['savedAt']) > 0) $h = $candidate;
            }
        }
        // Keine Kundenpreise, Einkaufspreise oder sonstigen internen Angebotsfelder ergänzen.
        $items = [];
        foreach ($h['items'] ?? [] as $it) {
            if (empty($it['code'])) continue;
            $items[] = ['code' => $it['code'], 'price' => $it['price'] ?? ['status' => 'none']];
        }
        $weeks[] = ['week' => $week, 'year' => $year, 'available' => $h !== null,
                    'source' => $h['source'] ?? null, 'origin' => $h['origin'] ?? null, 'items' => $items];
    }
    return ['allowed' => true, 'current' => $weeks[0], 'previous' => $weeks[1]];
}

function clean_date($v): ?string
{
    if (!is_string($v) || !preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $m)) return null;
    return checkdate((int)$m[2], (int)$m[3], (int)$m[1]) && (int)$m[1] >= 2000 && (int)$m[1] <= 2100 ? $v : null;
}
function clean_kg($v, string $where): float
{
    if (!is_int($v) && !is_float($v)) throw new InvalidArgumentException("Menge fehlt ($where).");
    $v = (float)$v;
    if (!is_finite($v) || abs($v) > 10000000) throw new InvalidArgumentException("Menge außerhalb des gültigen Bereichs ($where).");
    return round($v, 3);
}
function clean_incoming($rows): array
{
    if (!is_array($rows) || !array_is_list($rows) || count($rows) > 20000) throw new InvalidArgumentException('Ungültige Liste erwarteter Zugänge (max. 20000).');
    $out = [];
    foreach ($rows as $row) {
        if (!is_array($row)) throw new InvalidArgumentException('Ungültiger erwarteter Zugang.');
        $code = s($row['code'] ?? null, 20, false);
        if ($code === null || !preg_match('#^[0-9A-Za-z./-]+$#', $code)) throw new InvalidArgumentException('Ungültige Artikelnummer im Zugang.');
        $kg = clean_kg($row['kg'] ?? null, $code);
        if ($kg <= 0) throw new InvalidArgumentException('Zugangsmenge muss größer als null sein.');
        $arrival = clean_date($row['arrival'] ?? null);
        if (isset($row['arrival']) && $arrival === null) throw new InvalidArgumentException('Ungültiges Ankunftsdatum im Zugang.');
        $z = ['code' => $code, 'name' => s($row['name'] ?? '', 200) ?: '(ohne Bezeichnung)',
              'lot' => s($row['lot'] ?? '', 20) ?? '', 'marke' => s($row['marke'] ?? '', 40) ?? '', 'arrival' => $arrival, 'kg' => $kg];
        /* Wie bei den eingelagerten Partien (optional, nur wenn in der Liste vorhanden): MHD, Kolli, EK-Preis € je kg
           (EK nur für Berechtigte ausgeliefert, stock_ohne_ek) */
        $mhd = clean_date($row['mhd'] ?? null);
        if ($mhd !== null) $z['mhd'] = $mhd;
        $kolli = $row['kolli'] ?? null;
        if ((is_int($kolli) || is_float($kolli)) && abs($kolli) < 1000000) $z['kolli'] = round((float)$kolli, 2);
        $ek = $row['ek'] ?? null;
        if ((is_int($ek) || is_float($ek)) && $ek >= 0 && $ek < 100000) $z['ek'] = round((float)$ek, 3);
        $out[] = $z;
    }
    return $out;
}
function clean_stock($b, bool $allowEmpty = false): array
{
    $src = is_array($b['articles'] ?? null) ? $b['articles'] : [];
    if (!$src && !$allowEmpty) throw new InvalidArgumentException('Die Bestandsliste enthält keine Artikel mit eingelagertem Bestand.');
    if (count($src) > 20000) throw new InvalidArgumentException('Zu viele Artikel in der Bestandsliste.');
    $out = [];
    $seen = [];
    foreach ($src as $a) {
        if (!is_array($a)) continue;
        $code = s($a['code'] ?? null, 20, false);
        if ($code === null || !preg_match('#^[0-9A-Za-z./-]+$#', $code)) throw new InvalidArgumentException('Ungültige Artikelnummer in der Bestandsliste.');
        $key = ctype_digit($code) ? (ltrim($code, '0') === '' ? '0' : ltrim($code, '0')) : strtoupper($code);
        if (isset($seen[$key])) throw new InvalidArgumentException("Artikelnummer $code kommt in der Bestandsliste doppelt vor.");
        $seen[$key] = true;
        $lots = [];
        foreach (array_slice(is_array($a['lots'] ?? null) ? $a['lots'] : [], 0, 500) as $l) {
            if (!is_array($l)) continue;
            $kolli = $l['kolli'] ?? null;
            $ek = $l['ek'] ?? null;   // Einkaufspreis € je kg – nur für Berechtigte ausgeliefert (stock_ohne_ek)
            $lots[] = ['lot' => s($l['lot'] ?? '', 20) ?? '', 'marke' => s($l['marke'] ?? '', 40) ?? '', 'arrival' => clean_date($l['arrival'] ?? null), 'mhd' => clean_date($l['mhd'] ?? null),
                       'kolli' => (is_int($kolli) || is_float($kolli)) && abs($kolli) < 1000000 ? round((float)$kolli, 2) : null, 'kg' => clean_kg($l['kg'] ?? null, $code),
                       'ek' => (is_int($ek) || is_float($ek)) && $ek >= 0 && $ek < 100000 ? round((float)$ek, 3) : null];
        }
        $kg = clean_kg($a['kg'] ?? null, $code);
        if ($kg <= 0) continue;
        $mhd = clean_date($a['mhd'] ?? null);
        $out[] = ['code' => $code, 'name' => s($a['name'] ?? '', 200) ?: '(ohne Bezeichnung)', 'kg' => $kg, 'mhd' => $mhd,
                  'mhdKg' => $mhd !== null && isset($a['mhdKg']) ? clean_kg($a['mhdKg'], $code) : null, 'lots' => $lots];
    }
    if (!$out && !$allowEmpty) throw new InvalidArgumentException('Die Bestandsliste enthält keine Artikel mit eingelagertem Bestand.');
    return $out;
}

/* Einkaufspreise aus einem Bestand entfernen (für Nutzer ohne Recht „bestand.einkaufspreise“) */
function stock_ohne_ek(?array $st): ?array
{
    if (!$st) return $st;
    foreach ($st['articles'] ?? [] as $i => $a) foreach ($a['lots'] ?? [] as $j => $l) unset($st['articles'][$i]['lots'][$j]['ek']);
    foreach ($st['incoming'] ?? [] as $i => $z) unset($st['incoming'][$i]['ek']);
    return $st;
}

/* Bezeichnung und VK-Gruppe aus den Artikelstammdaten (Eigentümer Verwaltung, hier nur lesen – regeln/datenverantwortung.toml).
   Gilt für Ansicht, Druck, PDF, CSV und MHD-Mail; gespeichert bleibt der Bestand unverändert (Name aus der Importdatei).
   Ohne Stammdatensatz oder mit leerer Bezeichnung bleibt der Name der Importdatei. „nameImport“ nur, wenn er abweicht
   (Suche findet beide). „nameOrig“: Originalbezeichnung der Warenwirtschaft für die MHD-Liste (bestand_originalname()). „merkmale“: Fleischart · Herkunft · Zustand aus dem Stammsatz (bestand_merkmale(), nur wenn
   etwas bekannt ist) – die Ansicht zeigt sie unter der Bezeichnung, PDF, CSV und MHD-Mail daneben (Entscheidung Inhaber
   30.10.2026: „Nacken schier“ und „Lachs“ allein sind nicht eindeutig). Rückgabe zusätzlich „vkgruppen“: Nummer →
   Bezeichnung der verwendeten VK-Gruppen. */
const BESTAND_ZUSTAND = ['frisch' => 'frisch', 'gefroren' => 'gefroren', 'frisch-gefroren' => 'frisch/gefroren', 'dry-aged' => 'Dry Aged'];
function bestand_merkmale(array $s): string
{
    $kat = trim((string)($s['category'] ?? ''));
    $teile = [$kat === 'Sonstiges' ? '' : $kat, trim((string)($s['origin'] ?? '')), BESTAND_ZUSTAND[(string)($s['condition'] ?? '')] ?? ''];
    return implode(' · ', array_values(array_filter($teile, fn($t) => $t !== '')));
}
/* Bezeichnung mit Merkmalen in einer Zeile (Excel und Text der MHD-Mail; die CSV der Ansicht setzt sie genauso zusammen):
   „Lachs · Schwein · DE · frisch“ */
function bestand_bezeichnung(array $a): string
{
    $m = trim((string)($a['merkmale'] ?? ''));
    return (string)($a['name'] ?? '') . ($m !== '' ? ' · ' . $m : '');
}
/* Originalbezeichnung eines Bestandsartikels (MHD-Liste, Auftrag des Inhabers 03.11.2026): Bezeichnung1 aus dem
   Artikelstammdaten-Import der Warenwirtschaft, sonst der Name der Bestandsliste – nie die Angebotsbezeichnung.
   Erwartet einen Artikel nach bestand_mit_stammdaten(); wie im Browser (stockOrigName in admin.js). */
function bestand_originalname(array $a): string
{
    return (string)($a['nameOrig'] ?? $a['name'] ?? '');
}
function bestand_mit_stammdaten(?array $st): ?array
{
    if (!$st) return $st;
    $m = [];
    foreach ((store_read('stammdaten')['articles'] ?? []) as $a) if (is_array($a) && isset($a['code'])) $m[code_key((string)$a['code'])] = $a;
    $genutzt = [];
    $setze = function ($x) use ($m, &$genutzt) {
        if (!is_array($x)) return $x;
        $s = $m[code_key((string)($x['code'] ?? ''))] ?? null;
        if (!$s) return $x;
        $name = trim((string)($s['name'] ?? ''));
        if ($name !== '' && $name !== (string)($x['name'] ?? '')) { $x['nameImport'] = (string)($x['name'] ?? ''); $x['name'] = $name; }
        // Originalbezeichnung (MHD-Liste): Bezeichnung1 aus dem Artikelstammdaten-Import, sonst der Name der Bestandsliste;
        // „nameOrig“ nur, wenn sie von der angezeigten Bezeichnung abweicht
        $orig = trim((string)($s['nameWawi'] ?? '')) ?: (string)($x['nameImport'] ?? $x['name'] ?? '');
        if ($orig !== (string)$x['name']) $x['nameOrig'] = $orig;
        $merk = bestand_merkmale($s);
        if ($merk !== '') $x['merkmale'] = $merk;
        $vk = trim((string)($s['vkGruppe'] ?? ''));
        if ($vk !== '') { $x['vk'] = $vk; $genutzt[$vk] = true; }
        return $x;
    };
    $st['articles'] = array_map($setze, $st['articles'] ?? []);
    $st['incoming'] = array_map($setze, $st['incoming'] ?? []);
    $namen = [];
    if ($genutzt) foreach (gruppen_load('vkgruppen')['groups'] as $g) if (isset($genutzt[(string)($g['nr'] ?? '')])) $namen[(string)$g['nr']] = (string)($g['name'] ?? '');
    $st['vkgruppen'] = (object)$namen;
    return $st;
}

/* ---------------- Auszug für die Kundenseite (ADR-007 Stufe 2b) ----------------
   Ab Trennstufe 2 liegen Bestand und Stammdaten innen. Die Kundenseite braucht davon nur, welche Artikel Lagerbestand haben
   (ausverkaufte Sonderposten, stock_codes) und Fleischart, Herkunft und Zustand je Artikel (Einzelangebote, einzel_model) – nie
   Mengen, Partien, MHD oder Einkaufspreise (GR-001, GR-008). Neu geschrieben nach jeder Änderung von Bestand oder Stammdaten
   (bestand_speichern, stammdaten_speichern); der Postausgang prüft zusätzlich bei jedem Durchgang, ob er zum Stand passt. */
function artikelauszug_erzeugen(?array $bestand, ?array $stamm): array
{
    $lager = null;   // null: keine Bestandsliste vorhanden (dann gilt nichts als ausverkauft)
    if (is_array($bestand) && !empty($bestand['articles'])) {
        $lager = [];
        foreach ($bestand['articles'] as $a) if (is_array($a) && (float)($a['kg'] ?? 0) > 0) $lager[code_key((string)($a['code'] ?? ''))] = true;
        $lager = array_map('strval', array_keys($lager)); sort($lager, SORT_STRING);
    }
    $merkmale = [];
    foreach ((is_array($stamm['articles'] ?? null) ? $stamm['articles'] : []) as $a) {
        if (!is_array($a) || (string)($a['code'] ?? '') === '') continue;
        $merkmale[code_key((string)$a['code'])] = ['category' => $a['category'] ?? null, 'origin' => $a['origin'] ?? null, 'condition' => $a['condition'] ?? null];
    }
    ksort($merkmale, SORT_STRING);
    return ['lager' => $lager, 'merkmale' => (object)$merkmale];
}
/* Auszug neu schreiben, wenn er nicht zum Stand von Bestand und Stammdaten passt (nur ab Trennstufe 2, nur mit Sicht auf die
   internen Daten). $immer: ohne Vergleich der Zeitstempel (Durchsicht des Postausgangs). Rückgabe: geschrieben? */
function artikelauszug_aktualisieren(bool $immer = true): bool
{
    if (store_stufe() < 2 || !store_innen()) return false;
    $quelle = ['bestand' => store_mtime('bestand'), 'stammdaten' => store_mtime('stammdaten')];
    $alt = store_read('artikelauszug');
    if (!$immer && is_array($alt) && ($alt['quelle'] ?? null) == $quelle) return false;
    $neu = artikelauszug_erzeugen(store_read('bestand'), store_read('stammdaten'));
    if (is_array($alt) && json_encode([$alt['lager'] ?? null, (object)($alt['merkmale'] ?? [])]) === json_encode([$neu['lager'], $neu['merkmale']]) && ($alt['quelle'] ?? null) == $quelle) return false;
    with_lock('artikelauszug', function () use ($neu, $quelle) { store_write('artikelauszug', $neu + ['quelle' => $quelle, 'erzeugt' => now()]); });
    return true;
}
/* Kundenseite: Auszug lesen (null, wenn es noch keinen gibt) */
function artikelauszug(): ?array
{
    $a = store_read('artikelauszug');
    return is_array($a) ? $a : null;
}

/* ---------------- Stammdaten ---------------- */

/* Startseite des Dashboards („Heute für Sie“, lib/startseite.php): Artikel der MHD-Liste (dieselbe Liste wie die Suche „MHD“
   und die MHD-Mail, mhd_liste_ohne_preise) für Mitarbeiter, die die MHD-Liste verantworten (bestand.mhd_senden): abgelaufen =
   überfällig, MHD in höchstens 4 Tagen = heute (rot in der Liste), in 5–7 Tagen = demnächst. Nur Anzahlen, keine Mengen. */
function bestand_startseite(array $me): array
{
    if (!may($me, 'bestand.sehen') || !may($me, 'bestand.mhd_senden')) return [];
    require_once __DIR__ . '/bestand-mhd.php';
    $l = mhd_liste_ohne_preise();
    $n = ['abgelaufen' => [], '0-4' => [], '5-7' => []];
    foreach ($l['zeilen'] as $z) if (isset($n[$z['stufe']])) $n[$z['stufe']][] = (string)$z['mhd'];
    $text = function (int $k, string $rest) { return ($k === 1 ? '1 Artikel' : "$k Artikel") . ' ' . $rest; };
    $out = [];
    if ($n['abgelaufen']) $out[] = ['art' => 'ueberfaellig', 'titel' => $text(count($n['abgelaufen']), 'mit abgelaufenem MHD'), 'detail' => 'noch im Bestand',
                                     'datum' => min($n['abgelaufen']), 'ziel' => 'stock', 'anzahl' => count($n['abgelaufen'])];
    if ($n['0-4']) $out[] = ['art' => 'heute', 'titel' => $text(count($n['0-4']), 'mit MHD in höchstens 4 Tagen'), 'detail' => 'frühestes MHD ' . startseite_de(min($n['0-4'])),
                             'ziel' => 'stock', 'anzahl' => count($n['0-4'])];
    if ($n['5-7']) $out[] = ['art' => 'demnaechst', 'titel' => $text(count($n['5-7']), 'mit MHD in 5–7 Tagen'), 'detail' => 'frühestes MHD ' . startseite_de(min($n['5-7'])),
                             'datum' => min($n['5-7']), 'ziel' => 'stock', 'anzahl' => count($n['5-7'])];
    return $out;
}

function code_key(string $c): string { return ctype_digit($c) ? (ltrim($c, '0') === '' ? '0' : ltrim($c, '0')) : strtoupper($c); }
function clean_master($list): array
{
    if (!is_array($list)) throw new InvalidArgumentException('Stammdaten fehlen.');
    if (count($list) > 20000) throw new InvalidArgumentException('Zu viele Stammdatensätze.');
    $out = [];
    $seen = [];
    foreach ($list as $a) {
        if (!is_array($a)) continue;
        $code = s($a['code'] ?? null, 20, false);
        if ($code === null || !preg_match('#^[0-9A-Za-z./-]+$#', $code)) throw new InvalidArgumentException('Ungültige Artikelnummer in den Stammdaten.');
        $k = code_key($code);
        if (isset($seen[$k])) throw new InvalidArgumentException("Artikelnummer $code ist in den Stammdaten doppelt.");
        $seen[$k] = true;
        $name = s($a['name'] ?? null, 200, false);
        if ($name === null) throw new InvalidArgumentException("Artikel $code hat keine Bezeichnung.");
        $cat = in_array($a['category'] ?? '', CATEGORIES, true) ? $a['category'] : 'Sonstiges';
        $cond = in_array($a['condition'] ?? '', CONDITIONS, true) ? $a['condition'] : 'unbekannt';
        $origin = s($a['origin'] ?? null, 60);
        $e = ['code' => $code, 'name' => $name, 'category' => $cat, 'origin' => ($origin === '' ? null : $origin), 'condition' => $cond];
        // Felder aus der Warenwirtschaft (Artikelstammdaten-Export): VK-Gruppe (Stammdaten → VK-Gruppen) und GTIN
        $vk = s($a['vkGruppe'] ?? '', 10) ?? '';
        if ($vk !== '' && !preg_match('/^[0-9A-Za-z._-]{1,10}$/', $vk)) throw new InvalidArgumentException("Artikel $code: ungültige VK-Gruppe.");
        $gtin = preg_replace('/\s+/', '', (string)($a['gtin'] ?? ''));
        if ($gtin !== '' && !preg_match('/^\d{8,14}$/', $gtin)) throw new InvalidArgumentException("Artikel $code: ungültige GTIN (8 bis 14 Ziffern).");
        if ($vk !== '') $e['vkGruppe'] = $vk;
        if ($gtin !== '') $e['gtin'] = $gtin;
        // Originalbezeichnung der Warenwirtschaft (Bezeichnung1 des Artikelstammdaten-Exports, nur lesen) und eigene
        // Bezeichnung je Kundenangebot (Angebots-ID → Text; fehlt = Basiswert „name“). Beide optional, GR-006.
        $wawi = s($a['nameWawi'] ?? null, 200);
        if ($wawi !== null && $wawi !== '') $e['nameWawi'] = $wawi;
        $namen = angebotsnamen_clean($a['namen'] ?? null, $code);
        if ($namen) $e['namen'] = $namen;
        $out[] = $e;
    }
    usort($out, function ($x, $y) { return strnatcmp($x['code'], $y['code']); });
    return $out;
}
/* Eigene Bezeichnungen je Angebot (Stammsatz und Artikel des Angebots): Angebots-ID → Text, höchstens OFFER_MAX Einträge.
   Leere Texte fallen weg (dann gilt die Bezeichnung des Artikels). Das Wochenangebot hat keinen Eintrag – seine
   Bezeichnung ist der Basiswert. $known: nur diese Angebote (Angebotsmodell); null = nur das Format prüfen (Stammdaten). */
function angebotsnamen_clean($v, string $wo, ?array $known = null): array
{
    $out = [];
    if (!is_array($v)) return $out;
    foreach ($v as $oid => $t) {
        $oid = (string)$oid;   // numerische Angebots-IDs kommen als Zahl an
        if ($oid === 'std' || !preg_match('/^[a-z0-9-]{1,40}$/', $oid)) continue;
        if ($known !== null && !in_array($oid, $known, true)) continue;   // gelöschte Angebote fallen weg
        if (!is_string($t)) continue;
        $t = s($t, 200);
        if ($t === null || $t === '') continue;
        $out[$oid] = $t;
        if (count($out) > 100) throw new InvalidArgumentException("Zu viele Bezeichnungen je Angebot ($wo).");
    }
    ksort($out, SORT_STRING);
    return $out;
}
/* Vergleichstext der Bezeichnungen je Angebot (Protokoll, Vorschau): „edeka: Rinderhüfte · bela: …“ */
function angebotsnamen_text($v): string
{
    if (!is_array($v) || !$v) return '';
    $t = [];
    foreach ($v as $oid => $n) $t[] = $oid . ': ' . $n;
    return implode(' · ', $t);
}
function master_changes(array $old, array $new): array
{
    $o = []; foreach ($old as $a) $o[code_key($a['code'])] = $a;
    $n = []; foreach ($new as $a) $n[code_key($a['code'])] = $a;
    $L = ['name' => 'Bezeichnung', 'nameWawi' => 'Originalbezeichnung', 'category' => 'Fleischart', 'origin' => 'Herkunft', 'condition' => 'Zustand', 'vkGruppe' => 'VK-Gruppe', 'gtin' => 'GTIN'];
    $d = [];
    foreach ($n as $k => $a) {
        if (!isset($o[$k])) { $d[] = ['k' => "s$k|+", 'code' => $a['code'], 'name' => $a['name'], 'f' => 'Neuer Stammsatz', 'from' => '', 'to' => $a['category'] . ' · ' . $a['condition']]; continue; }
        foreach ($L as $f => $label) if ((string)($o[$k][$f] ?? '') !== (string)($a[$f] ?? '')) $d[] = ['k' => "s$k|$f", 'code' => $a['code'], 'name' => $a['name'], 'f' => $label, 'from' => (string)($o[$k][$f] ?? ''), 'to' => (string)($a[$f] ?? '')];
        $na = angebotsnamen_text($o[$k]['namen'] ?? null); $nn = angebotsnamen_text($a['namen'] ?? null);
        if ($na !== $nn) $d[] = ['k' => "s$k|namen", 'code' => $a['code'], 'name' => $a['name'], 'f' => 'Bezeichnung je Angebot', 'from' => $na, 'to' => $nn];
    }
    foreach ($o as $k => $a) if (!isset($n[$k])) $d[] = ['k' => "s$k|-", 'code' => $a['code'], 'name' => $a['name'], 'f' => 'Stammsatz gelöscht', 'from' => $a['name'], 'to' => ''];
    return $d;
}
