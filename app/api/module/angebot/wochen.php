<?php
declare(strict_types=1);
/* Angebot · Frühere Wochen ansehen (Wunsch des Inhabers 13.11.2026): das veröffentlichte Angebot einer Kalenderwoche –
   Wochenangebot oder ein Kundenangebot – nur für Mitarbeiter mit Modulzugang Angebot und nur lesend (Aktion angebot_woche in
   aktionen/entwurf.php; das Fenster app/module/angebot/fruehere-wochen.js zeigt es in der Angebotsseite, ?vorschau=1&woche=…).
   Quelle je KW (angebot_wochen_verzeichnis): das aktuell veröffentlichte Angebot, wenn es diese KW hat; sonst unter
   versionen/* (vor jeder Veröffentlichung das ganze bisherige Angebot, höchstens keep_versions) der zuletzt veröffentlichte
   Stand dieser KW (spätestes publishedAt); sonst der Preisstand im Preisverlauf (historie/<JJJJ-WW>, ohne Grenze, nur Artikel
   und Preise mit Kundenpreisen – ohne Werbung, Bereiche, eigene Bezeichnungen, Empfehlungen), als einfache Liste nach
   Angebotsgruppen. Aufgelöst wird immer auf dem Server mit offer_resolve (GR-002/GR-005): nur die Preise des gewählten
   Angebots, nie Kundenpreise oder Werbung anderer Angebote. Sonderposten bleiben sichtbar, auch wenn sie heute ausverkauft
   sind (der Bestand von damals ist nicht bekannt). Die Regel eines Kundenangebots (eigene Artikelliste / folgt dem
   Wochenangebot) gilt nach heutigem Stand – frühere Einstellungen sind nicht gespeichert.
   Wird von der Aktion bei Bedarf geladen; liest nur eigene Dokumente (angebot, angebote, versionen/*, historie/*), schreibt nichts. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* KW eines gespeicherten Angebots als „JJJJ-WW“ (nur gültige ISO-Wochen), sonst null */
function angebot_woche_kw($m): ?string
{
    $w = is_array($m) ? ($m['meta']['week'] ?? null) : null;
    $y = is_array($m) ? ($m['meta']['year'] ?? null) : null;
    return is_int($w) && is_int($y) && $y >= 2000 && $y <= 2100 && kw_gueltig($w, $y) ? history_id($w, $y) : null;
}

/* Gespeicherte Wochen: 'JJJJ-WW' => ['art' => veroeffentlicht|version|historie, 'id' => Versions-ID, 'stand' => publishedAt] –
   je KW der zuletzt veröffentlichte Stand, aufsteigend sortiert */
function angebot_wochen_verzeichnis(): array
{
    $v = [];
    $pub = store_read('angebot');
    if ($k = angebot_woche_kw($pub)) $v[$k] = ['art' => 'veroeffentlicht', 'id' => null, 'stand' => (string)($pub['publishedAt'] ?? '')];
    foreach (store_names('versionen') as $f) {
        $id = basename($f);
        if (!preg_match('/^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$/', $id)) continue;
        $d = store_read('versionen/' . $id);
        if (!($k = angebot_woche_kw($d))) continue;
        $stand = is_string($d['publishedAt'] ?? null) ? $d['publishedAt'] : '';
        $alt = $v[$k] ?? null;
        // das aktuelle Angebot ist immer der neueste Stand; unter den Versionen gewinnt das späteste publishedAt (dann die ID)
        if ($alt && ($alt['art'] === 'veroeffentlicht' || strcmp($alt['stand'] . '|' . $alt['id'], $stand . '|' . $id) >= 0)) continue;
        $v[$k] = ['art' => 'version', 'id' => $id, 'stand' => $stand];
    }
    foreach (history_ids() as $h) if (!isset($v[$h])) $v[$h] = ['art' => 'historie', 'id' => null, 'stand' => ''];
    ksort($v);
    return $v;
}

/* Preisstand des Preisverlaufs als Angebotsmodell für offer_resolve: Angebotsgruppen aus den gespeicherten Gruppennamen
   (Reihenfolge wie gespeichert), ohne Bereiche, Werbung, eigene Bezeichnungen und Empfehlungen; Kundenpreise (variants)
   nur, soweit sie bei der Veröffentlichung gespeichert wurden (eingelesene alte Listen haben keine) */
function angebot_woche_aus_historie(array $h): array
{
    $groups = []; $gid = []; $items = [];
    foreach (is_array($h['items'] ?? null) ? array_values($h['items']) : [] as $i => $it) {
        if (!is_array($it)) continue;
        $g = trim((string)($it['group'] ?? ''));
        if (!isset($gid[$g])) { $gid[$g] = 'h' . count($gid); $groups[] = ['id' => $gid[$g], 'name' => $g !== '' ? $g : 'Weitere Artikel', 'section' => '']; }
        $row = ['id' => 'h' . $i, 'code' => $it['code'] ?? null, 'name' => (string)($it['name'] ?? ''), 'category' => (string)($it['category'] ?? 'Sonstiges'),
                'origin' => null, 'condition' => 'unbekannt', 'groupId' => $gid[$g],
                'price' => is_array($it['price'] ?? null) ? $it['price'] : ['status' => 'none'],
                'altPrices' => is_array($it['altPrices'] ?? null) ? array_values($it['altPrices']) : []];
        if (is_array($it['variants'] ?? null)) $row['variants'] = $it['variants'];
        $items[] = $row;
    }
    return ['meta' => ['week' => (int)($h['week'] ?? 0), 'year' => (int)($h['year'] ?? 0), 'notice' => ''], 'sections' => [], 'groups' => $groups, 'items' => $items,
            'publishedAt' => is_string($h['savedAt'] ?? null) ? $h['savedAt'] : null];
}

/* Aktion angebot_woche: KW „JJJJ-WW“ und Angebot (leer = Wochenangebot) → aufgelöstes Angebot dieser Woche oder null */
function angebot_woche(string $woche, string $oid): array
{
    if (!preg_match('/^(\d{4})-(\d{2})$/', $woche, $m) || (int)$m[1] < 2000 || (int)$m[1] > 2100 || !kw_gueltig((int)$m[2], (int)$m[1])) fail('Ungültige Kalenderwoche.', 422);
    if (!preg_match('/^[a-z0-9-]{1,40}$/', $oid) || strncmp($oid, 'e-', 2) === 0) fail('Unbekanntes Angebot.', 404);
    $def = offer_def($oid);
    if (!$def) fail('Unbekanntes Angebot.', 404);
    $verz = angebot_wochen_verzeichnis();
    $e = $verz[$woche] ?? null;
    $modell = null;
    if ($e && $e['art'] === 'veroeffentlicht') $modell = store_read('angebot');
    elseif ($e && $e['art'] === 'version') $modell = store_read('versionen/' . $e['id']);
    elseif ($e) { $h = store_read('historie/' . $woche); $modell = is_array($h) ? angebot_woche_aus_historie($h) : null; }
    $offer = is_array($modell) ? offer_resolve($modell, $def, false) : null;
    $keys = array_keys($verz);
    $vorige = null; $naechste = null;
    foreach ($keys as $k) { if ($k < $woche) $vorige = $k; elseif ($k > $woche && $naechste === null) $naechste = $k; }
    $angebote = [['id' => OFFER_STD, 'name' => 'Wochenangebot']];
    foreach (offers_load()['offers'] as $o) $angebote[] = ['id' => (string)$o['id'], 'name' => (string)$o['name']];
    return ['woche' => $woche, 'kw' => (int)$m[2], 'jahr' => (int)$m[1], 'angebot' => ['id' => (string)$def['id'], 'name' => (string)$def['name']],
            'quelle' => $offer ? $e['art'] : null, 'stand' => $offer ? ($offer['publishedAt'] ?? null) : null, 'artikel' => $offer ? count($offer['items']) : 0,
            'offer' => $offer, 'vorige' => $vorige, 'naechste' => $naechste, 'erste' => $keys[0] ?? null, 'angebote' => $angebote];
}
