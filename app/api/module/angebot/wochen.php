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
   (gleich alt: die Ablage, sie kennt die Definitionen); sonst – nur mit dem Recht des Preisverlaufs (preisverlauf_lesbar,
   wie die Aktion history_prev) – der Preisstand im Preisverlauf (historie/<JJJJ-WW>, nur Artikel und Preise, ohne
   Kundenpreise, Werbung, Bereiche, eigene Bezeichnungen, Empfehlungen) als einfache Liste nach Angebotsgruppen. Ohne
   dieses Recht gilt eine nur im Preisverlauf vorhandene Woche als Woche ohne Daten und erscheint auch nicht in der
   Wochenliste (vorige/naechste/erste).
   Aufgelöst wird immer auf dem Server mit offer_resolve (GR-002/GR-005): nur das gewählte Angebot, mit seiner damaligen
   Definition, wenn die Ablage sie kennt, sonst mit der heutigen. Sonderposten bleiben sichtbar, auch wenn sie heute
   ausverkauft sind (der Bestand von damals ist nicht bekannt).
   Die Ablage ist intern (regeln/datenverantwortung.toml): die Kundenseite liest sie nie. Ältere Fassungen ignorieren sie.
   Preisänderung zur Vorwoche (Inhaber 20.11.2026, Abschnitt unten): angebot_vorwoche_stempeln() legt beim Veröffentlichen
   die Preise der Vorwoche je Angebot als Schnappschuss ins Modell (meta.vorwoche, Artikelfeld vorwoche), angebot_vorwoche()
   liefert daraus nur die Preise des angefragten Angebots (Aktion offer mit vergleich=vorwoche, auch auf der Kundenseite),
   angebot_vorwoche_uebersicht() die Zähler und größten Veränderungen für die Wochen-Mail.
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
    if (preisverlauf_lesbar()) foreach (history_ids() as $h) $wochen[$h] = true;   // nur mit dem Recht des Preisverlaufs (GR-103)
    ksort($wochen);
    return ['wochen' => array_keys($wochen), 'je' => $v];
}

/* Preisstand des Preisverlaufs als Angebotsmodell für offer_resolve: Angebotsgruppen aus den gespeicherten Gruppennamen
   (Reihenfolge wie gespeichert), ohne Bereiche, Werbung, eigene Bezeichnungen und Empfehlungen. Ohne Kundenpreise – der
   Preisverlauf führt keine (history_week, GR-002): Kundenangebote zeigen aus dieser Quelle den Wochenpreis, Angebote mit
   eigener Artikelliste bleiben leer. Vollständige Wochenstände liefert die Wochenablage (angebot_woche_modell). */
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
        $items[] = $row;
    }
    return ['meta' => ['week' => (int)($h['week'] ?? 0), 'year' => (int)($h['year'] ?? 0), 'notice' => ''], 'sections' => [], 'groups' => $groups, 'items' => $items,
            'publishedAt' => is_string($h['savedAt'] ?? null) ? $h['savedAt'] : null];
}

/* Vollständiger Stand einer KW (mit Kundenpreisen und Werbung) aus Wochenablage, aktuellem Angebot und versionen/* –
   ohne den Preisverlauf. Rückgabe [Modell|null, Quelle|null, damalige Angebotsdefinitionen|null]; Quelle ≠ null bei
   einem gefundenen, aber leeren Dokument. Auch die Vorwochenspalte des Editors nutzt das (Aktion history_prev). */
function angebot_woche_modell(string $woche, ?array $verz = null): array
{
    $kandidat = ($verz ?? angebot_wochen_verzeichnis())['je'][$woche] ?? null;
    $ablage = store_read('angebot-woche/' . $woche);
    if (is_array($ablage) && is_array($ablage['modell'] ?? null) && (!$kandidat || strcmp((string)($ablage['stand'] ?? ''), $kandidat['stand']) >= 0))
        return [$ablage['modell'], 'ablage', is_array($ablage['angebote'] ?? null) ? $ablage['angebote'] : null];
    if (!$kandidat) return [null, null, null];
    $m = $kandidat['art'] === 'veroeffentlicht' ? store_read('angebot') : store_read('versionen/' . $kandidat['id']);
    return [is_array($m) ? $m : null, $kandidat['art'] === 'veroeffentlicht' ? 'veroeffentlicht' : 'version', null];
}

/* Aktion angebot_woche: KW „JJJJ-WW“ und Angebot (leer = Wochenangebot) → aufgelöstes Angebot dieser Woche oder null */
function angebot_woche(string $woche, string $oid): array
{
    if (!preg_match('/^(\d{4})-(\d{2})$/', $woche, $m) || (int)$m[1] < 2000 || (int)$m[1] > 2100 || !kw_gueltig((int)$m[2], (int)$m[1])) fail('Ungültige Kalenderwoche.', 422);
    if (!preg_match('/^[a-z0-9-]{1,40}$/', $oid) || strncmp($oid, 'e-', 2) === 0) fail('Unbekanntes Angebot.', 404);
    $verz = angebot_wochen_verzeichnis();
    // Quelle: spätester Stand aus Ablage, aktuellem Angebot und Versionen; sonst Preisverlauf (nur mit dessen Recht,
    // preisverlauf_lesbar – die Wochenliste enthält ihn dann ohnehin nicht)
    [$modell, $quelle, $defs] = angebot_woche_modell($woche, $verz);
    if ($quelle === null && preisverlauf_lesbar() && in_array($woche, $verz['wochen'], true)) {
        $h = history_week($woche); $modell = is_array($h) ? angebot_woche_aus_historie($h) : null; $quelle = 'historie';
    }
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

/* ---------- Preisänderung zur Vorwoche (Inhaber 20.11.2026: Angebot „mit Preisänderung“ verschicken und drucken) ----------
   Vorwoche = die KW vor meta.week/year des Angebots, Stand aus angebot_woche_modell (Wochenablage, aktuelles Angebot,
   versionen/* – nie der Preisverlauf). Weil die Kundenseite nach der Datentrennung keine internen Dokumente lesen kann, wird der
   Vergleich beim Veröffentlichen (angebot_veroeffentlichen, Mitarbeiterseite) als Schnappschuss ins Modell geschrieben (GR-106):
   meta.vorwoche = {kw, jahr} und je Artikel vorwoche = {Angebots-ID: Preis | null (ohne Preis) | false (nicht im Angebot)}.
   Der Eintrag „std“ gilt für jedes Angebot ohne eigenen Eintrag; ein Kundenangebot bekommt nur einen, wenn er abweicht (klein).
   Fehlt der Eintrag ganz, war der Artikel neu. Beide Felder liefert offer_resolve nie aus (Artikel nur über die Positivliste
   ARTIKEL_FELDER_AUSGELIEFERT – auch in älteren Fassungen –, meta.vorwoche entfernt), clean_model verwirft sie (kein Weitertragen
   in den Entwurf). Aufgelöst wird je Angebot mit dessen damaliger Definition (sonst der heutigen), zugeordnet über Art.-Nr.,
   Bezeichnung und Gruppe wie diffOffers im Editor (Artikel-IDs aus dem Excel-Import sind Zellpositionen, nicht stabil). */

/* KW vor der Woche des Modells als [kw, jahr], sonst null */
function angebot_vorwoche_kw(array $m): ?array
{
    if (!angebot_woche_kw($m)) return null;
    $d = (new DateTimeImmutable())->setISODate($m['meta']['year'], $m['meta']['week'])->modify('-7 days');
    return [(int)$d->format('W'), (int)$d->format('o')];
}

/* Vergleichsschlüssel eines aufgelösten Artikels, vom genauesten zum gröbsten (null = trifft nicht zu) */
function angebot_vorwoche_schluessel(array $it, array $gname): array
{
    $n = mb_strtolower(preg_replace('/\s+/u', ' ', trim((string)($it['name'] ?? ''))));
    $c = trim((string)($it['code'] ?? ''));
    $g = mb_strtolower(trim((string)($gname[$it['groupId'] ?? ''] ?? '')));
    return $c !== '' ? ["cng:$c|$n|$g", "cn:$c|$n", "c:$c", null] : [null, null, null, "n:$n"];
}
/* Index der Vorwoche eines Angebots: je Stufe Schlüssel → Preis|null; mehrdeutige Schlüssel → 'mehrdeutig' */
function angebot_vorwoche_index(array $offer): array
{
    $gname = []; foreach ($offer['groups'] ?? [] as $g) $gname[$g['id']] = $g['name'];
    $idx = [[], [], [], []];
    foreach ($offer['items'] as $it) {
        $p = $it['price'] ?? null;
        $wert = is_array($p) && ($p['status'] ?? '') === 'value' ? (float)$p['value'] : null;
        foreach (angebot_vorwoche_schluessel($it, $gname) as $i => $k) if ($k !== null) $idx[$i][$k] = array_key_exists($k, $idx[$i]) ? 'mehrdeutig' : $wert;
    }
    return $idx;
}
/* Preis der Vorwoche eines Artikels: Zahl, null (damals ohne Preis) oder false (damals nicht im Angebot) */
function angebot_vorwoche_finden(array $idx, array $it, array $gname)
{
    foreach (angebot_vorwoche_schluessel($it, $gname) as $i => $k)
        if ($k !== null && array_key_exists($k, $idx[$i]) && $idx[$i][$k] !== 'mehrdeutig') return $idx[$i][$k];
    return false;
}

/* Beim Veröffentlichen (unter der Sperre „entwurf“, vor dem Schreiben): Schnappschuss der Vorwoche ins Modell. Alte Einträge
   werden immer entfernt; gibt es die Vorwoche nicht, bleibt das Modell ohne Vergleich. */
function angebot_vorwoche_stempeln(array $model): array
{
    unset($model['meta']['vorwoche']);
    foreach ($model['items'] ?? [] as $i => $it) unset($model['items'][$i]['vorwoche']);
    $vk = angebot_vorwoche_kw($model);
    [$alt, , $defs] = $vk ? angebot_woche_modell(history_id($vk[0], $vk[1])) : [null, null, null];
    if (!is_array($alt) || !is_array($alt['items'] ?? null)) return $model;
    $damals = [];
    foreach (is_array($defs) ? $defs : [] as $d) if (is_array($d) && isset($d['id'])) $damals[(string)$d['id']] = angebot_woche_definition($d);
    $pos = []; foreach ($model['items'] as $i => $it) $pos[(string)$it['id']] = $i;
    $gname = []; foreach ($model['groups'] ?? [] as $g) $gname[$g['id']] = $g['name'];
    // Wochenangebot: jeder Artikel des Modells (auch die dort ausgeblendeten – Grundlage für die Angebote ohne eigenen Eintrag)
    $std = angebot_vorwoche_index(offer_resolve($alt, offer_def(OFFER_STD), false));
    foreach ($model['items'] as $i => $it) { $v = angebot_vorwoche_finden($std, $it, $gname); if ($v !== false) $model['items'][$i]['vorwoche'] = [OFFER_STD => $v]; }
    foreach (offers_load()['offers'] as $o) {
        if (!is_array($o) || !isset($o['id'])) continue;
        $def = angebot_woche_definition($o);
        $idx = angebot_vorwoche_index(offer_resolve($alt, $damals[$def['id']] ?? $def, false));
        $jetzt = offer_resolve($model, $def, false);
        $jg = []; foreach ($jetzt['groups'] as $g) $jg[$g['id']] = $g['name'];
        foreach ($jetzt['items'] as $it) {
            $i = $pos[(string)$it['id']] ?? null;
            if ($i === null) continue;
            $v = angebot_vorwoche_finden($idx, $it, $jg);
            $m = $model['items'][$i]['vorwoche'] ?? [];
            $basis = array_key_exists(OFFER_STD, $m) ? $m[OFFER_STD] : false;   // null = damals ohne Preis (nicht „??“: null ≠ fehlt)
            if ($v !== $basis) $model['items'][$i]['vorwoche'][$def['id']] = $v;
        }
    }
    $model['meta']['vorwoche'] = ['kw' => $vk[0], 'jahr' => $vk[1]];
    return $model;
}

/* Vergleich für ein aufgelöstes Angebot ($offer = offer_resolve($model, $def)): {kw, jahr, preise: {Artikel-ID: Preis|null}}
   – nur Artikel dieses Angebots, nur Preise dieses Angebots (GR-002); fehlt eine ID, ist der Artikel neu. Ohne Vorwoche
   oder bei Einzelangeboten null. Liest nur das Modell (auch auf der Kundenseite nutzbar). */
function angebot_vorwoche(array $model, array $def, array $offer): ?array
{
    $vw = $model['meta']['vorwoche'] ?? null;
    if (!is_array($vw) || !is_int($vw['kw'] ?? null) || !is_int($vw['jahr'] ?? null) || strncmp((string)$def['id'], 'e-', 2) === 0) return null;
    $da = []; foreach ($offer['items'] as $it) $da[(string)$it['id']] = true;
    $preise = [];
    foreach ($model['items'] ?? [] as $it) {
        $id = (string)($it['id'] ?? '');
        if (!isset($da[$id])) continue;
        $m = is_array($it['vorwoche'] ?? null) ? $it['vorwoche'] : [];
        $v = array_key_exists($def['id'], $m) ? $m[$def['id']] : (array_key_exists(OFFER_STD, $m) ? $m[OFFER_STD] : false);
        if ($v !== false) $preise[$id] = is_int($v) || is_float($v) ? (float)$v : null;
    }
    return ['kw' => $vw['kw'], 'jahr' => $vw['jahr'], 'preise' => (object)$preise];
}

/* Veränderungen eines aufgelösten Angebots gegen die Vorwoche (E-Mail „mit Preisänderung“): Zähler und die größten
   Veränderungen [{code, name, alt, neu, diff}] nach Betrag – dieselbe Regel wie preisVergleich() in assets/frontend.js */
function angebot_vorwoche_uebersicht(array $offer, array $vw, int $top = 5): array
{
    $n = ['guenstiger' => 0, 'teurer' => 0, 'neu' => 0];
    $liste = [];
    $preise = (array)$vw['preise'];
    foreach ($offer['items'] as $it) {
        $id = (string)$it['id'];
        if (!array_key_exists($id, $preise)) { $n['neu']++; continue; }
        $neu = ($it['price']['status'] ?? '') === 'value' ? (float)$it['price']['value'] : null;
        if ($neu === null || $preise[$id] === null) continue;
        $d = round($neu - $preise[$id], 2);
        if ($d == 0) continue;
        $n[$d < 0 ? 'guenstiger' : 'teurer']++;
        $liste[] = ['code' => (string)($it['code'] ?? ''), 'name' => (string)$it['name'], 'alt' => $preise[$id], 'neu' => $neu, 'diff' => $d];
    }
    usort($liste, fn($a, $b) => abs($b['diff']) <=> abs($a['diff']));
    return $n + ['top' => array_slice($liste, 0, $top)];
}
