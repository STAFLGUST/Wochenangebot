<?php
declare(strict_types=1);
/* Angebot · Frühere Wochen ansehen und Wochenablage (Wünsche des Inhabers 13.11.2026): das veröffentlichte Angebot einer
   Kalenderwoche – Wochenangebot oder ein Kundenangebot – nur für Mitarbeiter mit Modulzugang Angebot und nur lesend (Aktion
   angebot_woche in aktionen/entwurf.php; das Fenster app/module/angebot/fruehere-wochen.js zeigt es in der Angebotsseite,
   ?vorschau=1&woche=…).
   Wochenablage angebot-woche/<JJJJ-WW> („je KW dauerhaft“): angebot_veroeffentlichen() (lib/angebote.php) legt bei jeder
   Veröffentlichung den neuen Stand mit den damaligen Angebotsdefinitionen (ID, Name, Regel der Artikelliste je Angebot, bei
   Sonderangeboten Art und Gültigkeit – nie Kundengruppen) ab
   und ersetzt damit den Stand derselben KW – im selben Sperr- und Transaktionsrahmen. Ohne Grenze, nie automatisch gelöscht.
   Wird eine alte Version (versionen/*, höchstens keep_versions) gelöscht, rettet angebot_woche_retten() sie vorher in die
   Ablage, wenn diese KW dort noch keinen neueren Stand hat (Definitionen dann unbekannt) – so geht ab jetzt kein vollständiger
   Wochenstand mehr verloren, auch nicht aus der Zeit vor der Ablage; ein Nachfüllen beim Lesen gibt es nicht.
   Quelle je KW (angebot_woche): der Stand mit dem spätesten publishedAt aus Ablage, aktuellem Angebot und versionen/*
   (gleich alt: die Ablage, sie kennt die Definitionen); sonst der Preisstand im Preisverlauf (historie/<JJJJ-WW>, nur Artikel
   und Preise – ohne Werbung, Bereiche, eigene Bezeichnungen, Empfehlungen) als einfache Liste nach Angebotsgruppen.
   Aufgelöst wird immer auf dem Server mit offer_resolve (GR-002/GR-005): nur das gewählte Angebot, mit seiner damaligen
   Definition, wenn die Ablage sie kennt, sonst mit der heutigen. Sonderposten bleiben sichtbar, auch wenn sie heute
   ausverkauft sind (der Bestand von damals ist nicht bekannt).
   Die Ablage ist intern (regeln/datenverantwortung.toml): die Kundenseite liest sie nie. Ältere Fassungen ignorieren sie.
   Schreibt nur eigene Dokumente (angebot-woche/*), liest angebot, angebote, versionen/*, historie/*. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar


/* KW eines gespeicherten Angebots als „JJJJ-WW“ (nur gültige ISO-Wochen), sonst null */
function angebot_woche_kw($m): ?string
{
    $w = is_array($m) ? ($m['meta']['week'] ?? null) : null;
    $y = is_array($m) ? ($m['meta']['year'] ?? null) : null;
    return is_int($w) && is_int($y) && $y >= 2000 && $y <= 2100 && kw_gueltig($w, $y) ? history_id($w, $y) : null;
}

/* Eine Angebotsdefinition so, wie offer_resolve sie braucht: ID, Name, Regel der Artikelliste, bei Sonderangeboten Art und
   Gültigkeit (Kopf „gültig von … bis …“, module/angebot/sonderangebote.php) – nie Kundengruppen (gruppen, sonderGruppen) */
function angebot_woche_definition(array $o): array
{
    $d = ['id' => (string)$o['id'], 'name' => (string)($o['name'] ?? $o['id']), 'fallback' => ($o['fallback'] ?? 'standard') === 'hidden' ? 'hidden' : 'standard'];
    if (is_string($o['art'] ?? null) && $o['art'] !== '') $d['art'] = $o['art'];
    if (is_array($o['gueltig'] ?? null)) $d['gueltig'] = $o['gueltig'];
    return $d;
}
/* Angebotsdefinitionen als Schnappschuss (GR-106) */
function angebot_woche_definitionen(): array
{
    $out = [];
    foreach (offers_load()['offers'] as $o) if (is_array($o) && isset($o['id'])) $out[] = angebot_woche_definition($o);
    return $out;
}

/* Beim Veröffentlichen (angebot_veroeffentlichen, unter der Sperre „entwurf“): neuen Stand je KW ablegen, ersetzt dieselbe KW */
function angebot_woche_ablegen(array $model): void
{
    $k = angebot_woche_kw($model);
    if (!$k) return;
    store_write('angebot-woche/' . $k, ['format' => 1, 'woche' => $k, 'stand' => (string)($model['publishedAt'] ?? ''), 'abgelegt' => now(),
                                    'quelle' => 'veroeffentlichung', 'angebote' => angebot_woche_definitionen(), 'modell' => $model]);
}

/* Vor dem Löschen einer alten Version (keep_versions): in die Ablage retten, wenn diese KW dort keinen neueren Stand hat */
function angebot_woche_retten($v): void
{
    $k = angebot_woche_kw($v);
    if (!$k) return;
    $stand = is_string($v['publishedAt'] ?? null) ? $v['publishedAt'] : '';
    $alt = store_read('angebot-woche/' . $k);
    if (is_array($alt) && strcmp((string)($alt['stand'] ?? ''), $stand) >= 0) return;
    store_write('angebot-woche/' . $k, ['format' => 1, 'woche' => $k, 'stand' => $stand, 'abgelegt' => now(), 'quelle' => 'version', 'angebote' => null, 'modell' => $v]);
}

/* Gespeicherte Wochen (aufsteigend) und je KW der späteste Stand aus aktuellem Angebot und versionen/*:
   [Wochen => true, 'JJJJ-WW' => ['art' => veroeffentlicht|version, 'id' => Versions-ID, 'stand' => publishedAt]] */
function angebot_wochen_verzeichnis(): array
{
    $v = []; $wochen = [];
    $pub = store_read('angebot');
    if ($k = angebot_woche_kw($pub)) { $v[$k] = ['art' => 'veroeffentlicht', 'id' => null, 'stand' => (string)($pub['publishedAt'] ?? '')]; $wochen[$k] = true; }
    foreach (store_names('versionen') as $f) {
        $id = basename($f);
        if (!preg_match('/^[0-9]{8}-[0-9]{6}-[0-9a-f]{6}$/', $id)) continue;
        $d = store_read('versionen/' . $id);
        if (!($k = angebot_woche_kw($d))) continue;
        $wochen[$k] = true;
        $stand = is_string($d['publishedAt'] ?? null) ? $d['publishedAt'] : '';
        $alt = $v[$k] ?? null;
        // späteres publishedAt gewinnt (gleich: das aktuelle Angebot, dann die größere ID)
        if ($alt && strcmp($alt['stand'] . '|' . ($alt['art'] === 'veroeffentlicht' ? '~' : $alt['id']), $stand . '|' . $id) >= 0) continue;
        $v[$k] = ['art' => 'version', 'id' => $id, 'stand' => $stand];
    }
    foreach (store_names('angebot-woche') as $f) { $k = basename($f); if (preg_match('/^\d{4}-\d{2}$/', $k)) $wochen[$k] = true; }
    foreach (history_ids() as $h) $wochen[$h] = true;
    ksort($wochen);
    return ['wochen' => array_keys($wochen), 'je' => $v];
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
    $verz = angebot_wochen_verzeichnis();
    // Quelle: spätester Stand aus Ablage, aktuellem Angebot und Versionen; sonst Preisverlauf
    $kandidat = $verz['je'][$woche] ?? null;
    $ablage = store_read('angebot-woche/' . $woche);
    $modell = null; $quelle = null; $defs = null;
    if (is_array($ablage) && is_array($ablage['modell'] ?? null) && (!$kandidat || strcmp((string)($ablage['stand'] ?? ''), $kandidat['stand']) >= 0)) {
        $modell = $ablage['modell']; $quelle = 'ablage'; $defs = is_array($ablage['angebote'] ?? null) ? $ablage['angebote'] : null;
    } elseif ($kandidat && $kandidat['art'] === 'veroeffentlicht') { $modell = store_read('angebot'); $quelle = 'veroeffentlicht'; }
    elseif ($kandidat) { $modell = store_read('versionen/' . $kandidat['id']); $quelle = 'version'; }
    elseif (in_array($woche, $verz['wochen'], true)) { $h = store_read('historie/' . $woche); $modell = is_array($h) ? angebot_woche_aus_historie($h) : null; $quelle = 'historie'; }
    if (!is_array($modell)) { $modell = null; $quelle = null; }
    // Definition des Angebots: damals (Ablage), sonst heute; gab es das Angebot in dieser Woche nicht, kein Angebot (fehlt)
    $damals = [];
    foreach (is_array($defs) ? $defs : [] as $d) if (is_array($d) && isset($d['id'])) $damals[(string)$d['id']] = angebot_woche_definition($d);
    $heute = offer_def($oid);
    $fehlt = false; $einstellung = 'heute';
    if ($oid === OFFER_STD) $def = $heute;
    elseif (isset($damals[$oid])) { $def = $damals[$oid]; $einstellung = 'damals'; }
    elseif ($heute) { $def = $heute; $fehlt = is_array($defs) && $quelle === 'ablage'; }
    else fail('Unbekanntes Angebot.', 404);
    $offer = $modell && !$fehlt ? offer_resolve($modell, $def, false) : null;
    $vorige = null; $naechste = null;
    foreach ($verz['wochen'] as $k) { if ($k < $woche) $vorige = $k; elseif ($k > $woche && $naechste === null) $naechste = $k; }
    // Auswahl: Wochenangebot, die Angebote dieser Woche (damalige Namen), dazu die heutigen, die es damals nicht gab
    $angebote = [['id' => OFFER_STD, 'name' => 'Wochenangebot']]; $drin = [OFFER_STD => true];
    foreach ($damals as $d) { $angebote[] = ['id' => $d['id'], 'name' => $d['name']]; $drin[$d['id']] = true; }
    foreach (offers_load()['offers'] as $o) if (!isset($drin[(string)$o['id']])) $angebote[] = ['id' => (string)$o['id'], 'name' => (string)$o['name']];
    return ['woche' => $woche, 'kw' => (int)$m[2], 'jahr' => (int)$m[1], 'angebot' => ['id' => (string)$def['id'], 'name' => (string)$def['name']],
            'quelle' => $offer ? $quelle : null, 'stand' => $offer ? ($offer['publishedAt'] ?? null) : null, 'artikel' => $offer ? count($offer['items']) : 0,
            'einstellung' => $einstellung, 'fehlt' => $fehlt, 'offer' => $offer, 'vorige' => $vorige, 'naechste' => $naechste, 'erste' => $verz['wochen'][0] ?? null,
            'angebote' => $angebote];
}
