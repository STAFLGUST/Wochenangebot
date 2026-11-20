<?php
declare(strict_types=1);
/* Angebot · Preisänderung zur Vorwoche (Inhaber 20.11.2026: Angebot zusätzlich „mit Preisänderung“ verschicken und drucken,
   ▼ günstiger, ▲ teurer, neu; jeder Kunde nur gegen sein eigenes Angebot der Vorwoche). Eingebunden von lib/angebote.php.
   Die Regel steht nur hier: angebot_vorwoche() liefert je Angebot die Liste der Änderungen, die Angebotsseite
   (assets/angebot-vorwoche.js) schlägt darin nur nach, die Wochen-Mail zählt und sortiert sie (angebot_vorwoche_mail).
   Schnappschuss beim Veröffentlichen (GR-106): Weil die Kundenseite nach der Datentrennung keine internen Dokumente lesen kann,
   legt angebot_vorwoche_stempeln() (angebot_veroeffentlichen, Mitarbeiterseite) die Preise der Vorwoche ins Modell:
   meta.vorwoche = {kw, jahr, angebote: [IDs der dabei aufgelösten Kundenangebote]} und je Artikel
   vorwoche = {Angebots-ID: Preis | null (ohne Preis) | false (nicht im Angebot)}. Der Eintrag „std“ gilt für jedes Angebot
   ohne eigenen Eintrag; ein Kundenangebot bekommt nur einen, wenn er abweicht. Fehlt der Eintrag ganz, war der Artikel neu.
   Ein Angebot, das beim Stempeln unbekannt war (später angelegt), hat keinen Vergleich – nie die Preise des Wochenangebots.
   Beide Felder liefert offer_resolve nie aus (Positivliste ARTIKEL_FELDER_AUSGELIEFERT, meta.vorwoche entfernt), clean_model
   verwirft sie (kein Weitertragen in den Entwurf).
   Vorwoche = die KW vor meta.week/year (angebot_woche_modell: Wochenablage, aktuelles Angebot, versionen/* – nie der
   Preisverlauf), je Angebot mit dessen damaliger Definition (sonst der heutigen). Zuordnung (Artikel-IDs aus dem Excel-Import
   sind Zellpositionen, nicht stabil) von genau nach grob: Art.-Nr.+Bezeichnung+Gruppe, Art.-Nr.+Bezeichnung, Art.-Nr.; ohne
   Art.-Nr. Bezeichnung+Gruppe, Bezeichnung. Ein Schlüssel zählt nur, wenn er in Vorwoche und aktuellem Angebot je genau einmal
   vorkommt (eine neue Variante mit vorhandener Art.-Nr. ist „neu“). Bezeichnung und Gruppe normalisiert wie keyPart in
   assets/offer-core.js (Kleinschreibung, nur a–z, 0–9, äöüß).
   Neigung des Pfeils (Darstellung „nur Pfeil“, ?vergleich=pfeil): je geänderter Artikel p = Veränderung in Prozent des
   Vorwochenpreises (1 Nachkommastelle, mit Vorzeichen) und stufe 1–3 nach ANGEBOT_VORWOCHE_STUFEN (gerechnet am gerundeten p).
   Nicht verglichen: Zusatzpreise (nur der Hauptpreis), Artikel ohne Preis oder „auf Anfrage“ in einer der Wochen (kein
   Hinweis), Einzelangebote; gibt es die direkte Vorwoche nicht (ausgelassene KW), gibt es keinen Vergleich. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Grenzen der Pfeil-Stufen in Prozent (Inhaber 20.11.2026, anpassbar): unter 2 % leicht (1), ab 2 % mittel (2), ab 5 % stark (3) */
const ANGEBOT_VORWOCHE_STUFEN = [2.0, 5.0];

/* KW vor der Woche des Modells als [kw, jahr] (auch über den Jahreswechsel, ISO-Wochen), sonst null */
function angebot_vorwoche_kw(array $m): ?array
{
    if (!angebot_woche_kw($m)) return null;
    $d = (new DateTimeImmutable())->setISODate($m['meta']['year'], $m['meta']['week'])->modify('-7 days');
    return [(int)$d->format('W'), (int)$d->format('o')];
}

/* Gruppen-ID → Name eines Modells oder aufgelösten Angebots */
function angebot_gruppen_namen(array $m): array
{
    $out = [];
    foreach ($m['groups'] ?? [] as $g) $out[$g['id']] = (string)$g['name'];
    return $out;
}

/* Vergleichsschlüssel eines Artikels, vom genauesten zum gröbsten */
function angebot_vorwoche_schluessel(array $it, array $gname): array
{
    $norm = fn($s) => preg_replace('/[^a-z0-9äöüß]+/u', '', mb_strtolower((string)$s));
    $n = $norm($it['name'] ?? '');
    $g = $norm($gname[$it['groupId'] ?? ''] ?? '');
    $c = trim((string)($it['code'] ?? ''));
    return $c !== '' ? ["cng:$c|$n|$g", "cn:$c|$n", "c:$c"] : ["ng:$n|$g", "n:$n"];
}

/* Artikel von $jetzt den Artikeln von $vorher zuordnen: [Artikel-ID => Preis der Vorwoche | null (ohne Preis)];
   ohne Treffer fehlt die ID. Ein Schlüssel zählt nur, wenn er auf beiden Seiten genau einmal vorkommt. */
function angebot_vorwoche_zuordnen(array $vorher, array $jetzt): array
{
    $gv = angebot_gruppen_namen($vorher);
    $vN = []; $vP = [];
    foreach ($vorher['items'] as $it) {
        $p = $it['price'] ?? null;
        $wert = is_array($p) && ($p['status'] ?? '') === 'value' ? (float)$p['value'] : null;
        foreach (angebot_vorwoche_schluessel($it, $gv) as $k) { $vN[$k] = ($vN[$k] ?? 0) + 1; $vP[$k] = $wert; }
    }
    $gj = angebot_gruppen_namen($jetzt);
    $jN = []; $schl = [];
    foreach ($jetzt['items'] as $it) {
        $schl[(string)$it['id']] = $s = angebot_vorwoche_schluessel($it, $gj);
        foreach ($s as $k) $jN[$k] = ($jN[$k] ?? 0) + 1;
    }
    $out = [];
    foreach ($schl as $id => $s) foreach ($s as $k) if (($vN[$k] ?? 0) === 1 && $jN[$k] === 1) { $out[$id] = $vP[$k]; break; }
    return $out;
}

/* Beim Veröffentlichen (unter der Sperre „entwurf“, vor dem Schreiben): Schnappschuss der Vorwoche ins Modell. Alte Einträge
   werden immer entfernt; gibt es die Vorwoche nicht, bleibt das Modell ohne Vergleich. */
function angebot_vorwoche_stempeln(array $model): array
{
    require_once __DIR__ . '/wochen.php';   // Wochenablage angebot-woche/<JJJJ-WW>
    unset($model['meta']['vorwoche']);
    foreach ($model['items'] ?? [] as $i => $it) unset($model['items'][$i]['vorwoche']);
    $vk = angebot_vorwoche_kw($model);
    [$alt, , $defs] = $vk ? angebot_woche_modell(history_id($vk[0], $vk[1])) : [null, null, null];
    if (!is_array($alt) || !is_array($alt['items'] ?? null)) return $model;
    $damals = angebot_woche_damals($defs);
    $pos = [];
    foreach ($model['items'] as $i => $it) $pos[(string)$it['id']] = $i;
    // Wochenangebot: jeder Artikel des Modells (auch die dort ausgeblendeten – Grundlage für die Angebote ohne eigenen Eintrag)
    foreach (angebot_vorwoche_zuordnen(offer_resolve($alt, offer_def(OFFER_STD), false), $model) as $id => $v) $model['items'][$pos[$id]]['vorwoche'] = [OFFER_STD => $v];
    $ids = [];
    foreach (offers_load()['offers'] as $o) {
        if (!is_array($o) || !isset($o['id'])) continue;
        $def = angebot_woche_definition($o);
        $ids[] = $def['id'];
        $jetzt = offer_resolve($model, $def, false);
        $treffer = angebot_vorwoche_zuordnen(offer_resolve($alt, $damals[$def['id']] ?? $def, false), $jetzt);
        foreach ($jetzt['items'] as $it) {
            $i = $pos[(string)$it['id']] ?? null;
            if ($i === null) continue;
            $v = array_key_exists((string)$it['id'], $treffer) ? $treffer[(string)$it['id']] : false;
            $m = $model['items'][$i]['vorwoche'] ?? [];
            $basis = array_key_exists(OFFER_STD, $m) ? $m[OFFER_STD] : false;   // null = damals ohne Preis (nicht „??“: null ≠ fehlt)
            if ($v !== $basis) $model['items'][$i]['vorwoche'][$def['id']] = $v;
        }
    }
    $model['meta']['vorwoche'] = ['kw' => $vk[0], 'jahr' => $vk[1], 'angebote' => $ids];
    return $model;
}

/* Änderungen eines aufgelösten Angebots ($offer = offer_resolve($model, $def)) gegen die Vorwoche:
   {kw, jahr, stufen, aenderungen: {Artikel-ID: {art: 'neu'} | {art: 'guenstiger'|'teurer', d, alt, p, stufe}}} – nur Artikel dieses Angebots,
   nur Preise dieses Angebots (GR-002); unveränderte und preislose Artikel fehlen. Ohne Vorwoche, bei Einzelangeboten und für
   Angebote, die beim Stempeln unbekannt waren, null. Liest nur das Modell (auch auf der Kundenseite nutzbar). */
function angebot_vorwoche(array $model, array $def, array $offer): ?array
{
    $vw = $model['meta']['vorwoche'] ?? null;
    $oid = (string)$def['id'];
    if (!is_array($vw) || !is_int($vw['kw'] ?? null) || !is_int($vw['jahr'] ?? null) || strncmp($oid, 'e-', 2) === 0) return null;
    if ($oid !== OFFER_STD && is_array($vw['angebote'] ?? null) && !in_array($oid, $vw['angebote'], true)) return null;
    $stempel = [];
    foreach ($model['items'] ?? [] as $it) if (is_array($it['vorwoche'] ?? null)) $stempel[(string)($it['id'] ?? '')] = $it['vorwoche'];
    $aend = [];
    foreach ($offer['items'] as $it) {
        $id = (string)$it['id'];
        $m = $stempel[$id] ?? [];
        $alt = array_key_exists($oid, $m) ? $m[$oid] : (array_key_exists(OFFER_STD, $m) ? $m[OFFER_STD] : false);
        if ($alt === false) { $aend[$id] = ['art' => 'neu']; continue; }
        if ((!is_int($alt) && !is_float($alt)) || ($it['price']['status'] ?? '') !== 'value') continue;
        $d = round((float)$it['price']['value'] - $alt, 2);
        if ($d == 0) continue;
        $p = $alt > 0 ? round($d / $alt * 100, 1) : null;   // Vorwochenpreis 0: keine Prozentangabe, stärkste Stufe
        $stufe = $p === null ? 3 : 1 + count(array_filter(ANGEBOT_VORWOCHE_STUFEN, fn($g) => abs($p) >= $g));
        $aend[$id] = ['art' => $d < 0 ? 'guenstiger' : 'teurer', 'd' => $d, 'alt' => (float)$alt, 'p' => $p, 'stufe' => $stufe];
    }
    return ['kw' => $vw['kw'], 'jahr' => $vw['jahr'], 'stufen' => ANGEBOT_VORWOCHE_STUFEN, 'aenderungen' => (object)$aend];
}

/* Übersicht der Änderungen eines Angebots für die Wochen-Mail als [Text, HTML] (E-Mail-taugliches HTML mit Inline-Styles,
   Farben wie auf der Angebotsseite), aus dem veröffentlichten Stand (Server, nie aus dem Browser); null ohne Vorwoche.
   Je Angebot einmal je Aufruf berechnet (ein Versand rechnet für viele Kunden dieselben Angebote). */
function angebot_vorwoche_mail(string $oid, string $name): ?array
{
    static $pub = false, $cache = [];
    if (array_key_exists($oid, $cache)) return $cache[$oid];
    if ($pub === false) $pub = store_read('angebot');
    $def = offer_def($oid);
    $off = is_array($pub) && $def ? offer_resolve($pub, $def) : null;
    $vw = $off ? angebot_vorwoche($pub, $def, $off) : null;
    return $cache[$oid] = $vw ? angebot_vorwoche_block($name, $vw['kw'], $off, (array)$vw['aenderungen']) : null;
}
function angebot_vorwoche_block(string $name, int $kw, array $off, array $aend, int $top = 5): array
{
    $n = ['guenstiger' => 0, 'teurer' => 0, 'neu' => 0];
    $liste = [];
    foreach ($off['items'] as $it) {
        $a = $aend[(string)$it['id']] ?? null;
        if (!$a) continue;
        $n[$a['art']]++;
        if ($a['art'] !== 'neu') $liste[] = ['code' => (string)($it['code'] ?? ''), 'name' => (string)$it['name'], 'alt' => $a['alt'], 'neu' => (float)$it['price']['value'], 'd' => $a['d']];
    }
    usort($liste, fn($a, $b) => abs($b['d']) <=> abs($a['d']));
    $liste = array_slice($liste, 0, $top);
    $e = fn($x) => number_format((float)$x, 2, ',', '.');
    $pfeil = fn($d) => ($d < 0 ? '▼ ' : '▲ ') . $e(abs($d));
    $farbe = ['guenstiger' => '#1f5a3c', 'teurer' => '#8c1d2c', 'neu' => '#7a5418'];
    $zahl = array_filter(['guenstiger' => $n['guenstiger'] ? "▼ {$n['guenstiger']} günstiger" : '', 'teurer' => $n['teurer'] ? "▲ {$n['teurer']} teurer" : '', 'neu' => $n['neu'] ? "{$n['neu']} neu" : '']);
    $t = "$name · Veränderung zur KW $kw: " . ($zahl ? implode(' · ', $zahl) : 'keine Preisänderung') . "\n";
    foreach ($liste as $r) $t .= '  ' . ($r['code'] !== '' ? $r['code'] . ' ' : '') . $r['name'] . ': ' . $e($r['alt']) . ' → ' . $e($r['neu']) . ' €/kg (' . $pfeil($r['d']) . ")\n";
    $zh = [];
    foreach ($zahl as $art => $txt) $zh[] = '<span style="color:' . $farbe[$art] . ';">' . $txt . '</span>';
    $td = 'padding:4px 6px;border-top:1px solid #ece6df;';
    $th = 'padding:0 6px 3px;font-weight:600;color:#857c72;';
    $rows = '';
    foreach ($liste as $r) $rows .= '<tr><td style="' . $td . 'color:#857c72;white-space:nowrap;">' . mail_h($r['code']) . '</td><td style="' . $td . '">' . mail_h($r['name']) . '</td>'
        . '<td style="' . $td . 'text-align:right;color:#857c72;white-space:nowrap;">' . $e($r['alt']) . '</td><td style="' . $td . 'text-align:right;font-weight:600;white-space:nowrap;">' . $e($r['neu']) . '</td>'
        . '<td style="' . $td . 'text-align:right;white-space:nowrap;color:' . $farbe[$r['d'] < 0 ? 'guenstiger' : 'teurer'] . ';">' . $pfeil($r['d']) . '</td></tr>';
    $h = '<div style="margin:0 0 10px;padding:12px 14px;border:1px solid #e6e1da;border-radius:8px;">'
        . '<p style="margin:0 0 4px;font-size:13px;color:#4a443e;"><strong>' . mail_h($name) . '</strong> · Veränderung zur KW ' . $kw . '</p>'
        . '<p style="margin:0;font-size:13px;">' . ($zh ? implode(' &middot; ', $zh) : '<span style="color:#857c72;">keine Preisänderung</span>') . '</p>'
        . ($rows ? '<table role="presentation" cellpadding="0" cellspacing="0" style="width:100%;margin-top:8px;border-collapse:collapse;font-size:12.5px;color:#2b2622;">'
            . '<tr><th style="' . $th . 'text-align:left;">Art.-Nr.</th><th style="' . $th . 'text-align:left;">Artikel</th><th style="' . $th . 'text-align:right;">bisher</th><th style="' . $th . 'text-align:right;">neu</th><th style="' . $th . 'text-align:right;">€/kg</th></tr>'
            . $rows . '</table>' : '')
        . '</div>';
    return [$t, $h];
}
