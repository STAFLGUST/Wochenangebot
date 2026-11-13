<?php
declare(strict_types=1);
/* Importvertrag des Moduls Angebot – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md).
   - Preisverlauf: frühere Angebotslisten (.xlsx) als Wochen im Preisverlauf. Gelesen werden sie vom Angebotsleser im
     Browser (offer-core.js, parseOfferWorkbook); hier prüft der Server die Wochen (clean_history_items), vergleicht sie mit
     den gespeicherten Wochen (Vorschau) und speichert sie (Übernahme, Protokoll je Woche). Die bisherige Aktion
     history_import nutzt preisverlauf_woche_speichern().
   - Artikelpreise (CSV der Warenwirtschaft, Auftrag des Inhabers 04.11.2026: nur noch hier, nicht mehr im Angebot): Preise
     ohne Kundengruppe ins Wochenangebot, mit Kundengruppe ins Angebot der Gruppe – in den Entwurf, veröffentlicht wird im
     Angebotseditor. Die Angebotswoche des Entwurfs wird auf die gewählte KW gesetzt (Standard: aktuelle KW). Kundengruppen
     ohne Angebot bekommen nur auf ausdrücklichen Wunsch je ein Angebot – einzeln ausgewählt (Option „gruppen“, Liste, Standard
     leer). Die Vorschau liefert zusätzlich „details“ für die Darstellung im Browser (admin-preisimport.js: Preise je Angebot
     mit bisher/neu, erhöht/gesenkt/neu, „Bitte prüfen“ ab 10 %, Gruppen ohne Angebot zum Anhaken). Gelesen wird die
     Datei im Browser (preiseAusCsv in admin.js); hier prüft der Server die Zeilen, ordnet sie den Angeboten zu (Vorschau)
     und schreibt Entwurf und ggf. neue Angebote unter Sperre mit Stand-Prüfung (409), Protokoll wie beim Speichern.
   Der frühere Excel-Import des Wochenangebots im Editor ist entfallen (Auftrag des Inhabers 04.11.2026).
   Wird von api/index.php geladen; schreibt nur eigene Dokumente (historie/*, historie_geloescht, entwurf, angebote). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

function import_arten_angebot(): array
{
    return [
        'preisverlauf' => ['name' => 'Preisverlauf (frühere Angebotslisten)', 'kurz' => 'Frühere Angebotslisten, je Datei eine Woche', 'beschreibung' => 'Excel-Angebotslisten früherer Wochen; jede Datei wird eine Woche im Preisverlauf. Das aktuelle Angebot bleibt unverändert.',
            'recht' => ['preisverlauf.bearbeiten'], 'aktion' => 'history_import', 'dateien' => ['xlsx', 'xlsm'], 'kodierung' => 'Excel-Arbeitsmappe (.xlsx)', 'mehrere' => true,
            'ansicht' => 'hist', 'vorschau' => 'preisverlauf_import_vorschau', 'uebernahme' => 'preisverlauf_import_uebernehmen'],
        'angebot_preise' => ['name' => 'Artikelpreise (CSV)', 'kurz' => 'Preise der Woche in den Entwurf, auch je Kundengruppe',
            'beschreibung' => 'Artikelpreise der Warenwirtschaft in den Entwurf: ohne Kundengruppe ins Wochenangebot, mit Kundengruppe ins Angebot der Gruppe. Die Angebotswoche wird auf die gewählte KW gesetzt (Standard: aktuelle KW). Veröffentlicht wird im Angebotseditor.',
            'recht' => ['angebot.bearbeiten', 'angebote.verwalten'], 'aktion' => 'save_draft', 'dateien' => ['csv'], 'kodierung' => 'CSV, UTF-8 oder Windows-1252, Semikolon getrennt', 'ansicht' => 'edit',
            'vorschau' => 'angebot_preise_vorschau', 'uebernahme' => 'angebot_preise_uebernehmen',
            'optionen' => [
                ['id' => 'woche', 'typ' => 'auswahl', 'label' => 'Angebotswoche', 'werte' => angebot_preise_wochen(), 'standard' => angebot_preise_aktuelle_woche()],
                ['id' => 'gruppen', 'typ' => 'liste', 'label' => 'Neue Angebote für Kundengruppen ohne Angebot', 'standard' => []],
            ]],
    ];
}

/* ---------------- Artikelpreise (CSV) ---------------- */

const ANGEBOT_PREISE_MAX = 50000;   // Zeilen einer Preisdatei
const ANGEBOT_PREISE_PRUEFEN = 10;  // Preisänderung ab diesem Prozentsatz: „Bitte prüfen“ (Tippfehler in der Warenwirtschaft)
const ANGEBOT_PREISE_DETAILS = 5000; // Preiszeilen in den Details der Vorschau (die Zahlen zählen immer alle)

/* Aktuelle Kalenderwoche (ISO 8601, Zeitzone der Anwendung) als „JJJJ-WW“ – Standard der Option „Angebotswoche“ */
function angebot_preise_aktuelle_woche(): string
{
    $d = new DateTimeImmutable('today');
    return sprintf('%04d-%02d', (int)$d->format('o'), (int)$d->format('W'));
}
/* Auswahl der Angebotswoche: vier Wochen zurück bis acht Wochen voraus, die aktuelle gekennzeichnet */
function angebot_preise_wochen(): array
{
    $heute = new DateTimeImmutable('today');
    $out = [];
    for ($i = -4; $i <= 8; $i++) {
        $d = $heute->modify(sprintf('%+d week', $i));
        $w = (int)$d->format('W'); $y = (int)$d->format('o');
        $mo = $heute->setISODate($y, $w, 1); $so = $mo->modify('+6 day');
        $out[] = ['wert' => sprintf('%04d-%02d', $y, $w), 'text' => "KW $w/$y · " . $mo->format('d.m.') . '–' . $so->format('d.m.Y') . ($i === 0 ? ' (aktuelle Woche)' : '')];
    }
    return $out;
}

/* Schlüssel einer Artikelnummer wie im Browser (StockCore.normCode): reine Zahlen ohne führende Nullen, sonst Großbuchstaben */
function angebot_code_key(string $c): string
{
    $c = trim($c);
    return ctype_digit($c) ? (ltrim($c, '0') ?: '0') : strtoupper($c);
}

/* Kennung eines neuen Angebots aus dem Namen (wie slug() im Eingabebereich) */
function angebot_slug(string $name): string
{
    $x = preg_replace('/^wochenangebot\s*/u', '', mb_strtolower($name));
    $x = strtr($x, ['ä' => 'ae', 'ö' => 'oe', 'ü' => 'ue', 'ß' => 'ss']);
    $x = trim(substr(trim((string)preg_replace('/[^a-z0-9]+/', '-', $x), '-'), 0, 32), '-');
    if ($x === '') $x = 'angebot';
    // „e-…“: Einzelangebote; „sonder-…“: Sonderangebote; Ziffern: JSON-Schlüssel
    return preg_match('/^(e|sonder)-/', $x) || ctype_digit($x) ? substr('angebot-' . $x, 0, 40) : $x;
}

/* Preise eintragen in 2 Nachkommastellen, mehr nur wenn vorhanden */
function angebot_preis_text(float $v): string
{
    $t = number_format($v, 4, ',', '.');
    return preg_replace('/(,\d\d)0{1,2}$/', '$1', $t) . ' €';
}

/* Zeilen des Lesers prüfen: {zeile, code, gruppe, preis}. Ungültige Zeilen werden Fehlerzeilen (nicht übernommen). */
function angebot_preise_zeilen(array $e): array
{
    $roh = is_array($e['preise'] ?? null) ? array_values($e['preise']) : [];
    if (!$roh) fail('Keine Preise in der Datei gefunden.', 422);
    if (count($roh) > ANGEBOT_PREISE_MAX) fail('Zu viele Zeilen (höchstens ' . number_format(ANGEBOT_PREISE_MAX, 0, ',', '.') . ').', 422);
    $ok = []; $fehler = [];
    foreach ($roh as $r) {
        if (!is_array($r)) continue;
        $zeile = is_int($r['zeile'] ?? null) ? $r['zeile'] : null;
        $code = is_string($r['code'] ?? null) || is_int($r['code'] ?? null) ? trim((string)$r['code']) : '';
        $gruppe = is_string($r['gruppe'] ?? null) || is_int($r['gruppe'] ?? null) ? trim((string)$r['gruppe']) : '';
        $p = $r['preis'] ?? null;
        $f = null;
        if ($code === '' || mb_strlen($code) > 20 || !preg_match('#^[0-9A-Za-z./-]+$#', $code)) $f = 'Artikelnummer ungültig';
        elseif ($gruppe !== '' && !preg_match('/^[0-9A-Za-z._-]{1,10}$/', $gruppe)) $f = 'Kundengruppe ungültig';
        elseif ((!is_int($p) && !is_float($p)) || !is_finite((float)$p) || $p < 0 || $p >= 100000) $f = 'Preis ungültig';
        if ($f !== null) { $fehler[] = ['art' => 'fehler', 'zeile' => $zeile, 'schluessel' => mb_substr($code, 0, 20), 'name' => '', 'text' => $f . ' – nicht übernommen']; continue; }
        $ok[] = ['zeile' => $zeile, 'code' => $code, 'gruppe' => $gruppe, 'preis' => round((float)$p, 4)];
    }
    if (!$ok && !$fehler) fail('Keine Preise in der Datei gefunden.', 422);
    return [$ok, $fehler];
}

/* Gewählte Angebotswoche „JJJJ-WW“ → [Woche, Jahr] (nur gültige ISO-Wochen; sonst die aktuelle) */
function angebot_preise_woche($v): array
{
    $v = is_string($v) ? $v : '';
    if (!preg_match('/^(\d{4})-(\d{2})$/', $v, $m) || !kw_gueltig((int)$m[2], (int)$m[1])) {
        preg_match('/^(\d{4})-(\d{2})$/', angebot_preise_aktuelle_woche(), $m);
    }
    return [(int)$m[2], (int)$m[1]];
}

/* Ausgangsstand: Entwurf, sonst veröffentlichtes Angebot; Stand = Revision des Entwurfs und der Angebotsliste */
function angebot_preise_basis(): array
{
    $draft = store_read('entwurf');
    $basis = $draft ?? store_read('angebot');
    if (!is_array($basis) || !is_array($basis['items'] ?? null)) fail('Es gibt noch kein Angebot. Bitte zuerst im Angebotseditor Artikel anlegen.', 422);
    $offers = offers_load();
    return [$draft, $basis, $offers, draft_rev($draft) . '.' . (int)$offers['rev']];
}

/* Zuordnung der Preise zu Angeboten und Artikeln (ohne zu schreiben). Ziel: OFFER_STD (ohne Kundengruppe), Angebots-ID
   (Angebot der Kundengruppe) oder „neu:<Gruppe>“ (Gruppe ohne Angebot, nur wenn in $gewaehlt). Alle Artikel mit derselben
   Artikelnummer bekommen den Preis; derselbe Artikel im selben Angebot zweimal mit anderem Preis: der erste gilt. */
function angebot_preise_plan(array $model, array $offers, array $rows, array $gewaehlt): array
{
    $bei = []; $oname = [OFFER_STD => 'Wochenangebot'];
    foreach ($offers as $o) { $oname[$o['id']] = $o['name']; foreach ($o['gruppen'] ?? [] as $g) if (!isset($bei[(string)$g])) $bei[(string)$g] = $o['id']; }
    $kg = []; foreach (kundengruppen_load()['groups'] as $g) $kg[(string)$g['nr']] = (string)($g['name'] ?? '');
    $frei = OFFER_MAX - count(sonder_ohne($offers));   // Sonderangebote zählen nicht mit
    $items = [];
    foreach ($model['items'] as $i => $it) if (($it['code'] ?? '') !== '' && $it['code'] !== null) $items[angebot_code_key((string)$it['code'])][] = $i;
    // Kundengruppen ohne Angebot: bekannte (anlegbar) und unbekannte (nie)
    $fehlt = []; $unbekannt = [];
    foreach ($rows as $r) {
        if ($r['gruppe'] === '' || isset($bei[$r['gruppe']])) continue;
        if (isset($kg[$r['gruppe']])) $fehlt[$r['gruppe']] = ($fehlt[$r['gruppe']] ?? 0) + 1;
        else $unbekannt[$r['gruppe']] = ($unbekannt[$r['gruppe']] ?? 0) + 1;
    }
    // Name des Angebots je fehlender Gruppe (für die Auswahl, auch wenn nicht gewählt); angelegt nur die gewählten
    $vorschlag = []; $namen = ['wochenangebot' => true];
    foreach ($offers as $o) $namen[mb_strtolower($o['name'])] = true;
    foreach (array_keys($fehlt) as $nr) {
        $nr = (string)$nr;
        $n = mb_substr('Wochenangebot ' . ($kg[$nr] !== '' ? $kg[$nr] : 'Kundengruppe ' . $nr), 0, 80);
        if (isset($namen[mb_strtolower($n)])) $n = mb_substr($n, 0, 70) . " ($nr)";
        $namen[mb_strtolower($n)] = true;
        $vorschlag[$nr] = $n;
    }
    $wahl = array_flip(array_map('strval', $gewaehlt));
    $neuName = array_filter($vorschlag, function ($nr) use ($wahl) { return isset($wahl[(string)$nr]); }, ARRAY_FILTER_USE_KEY);
    $zuViele = count($neuName) > $frei;
    if ($zuViele) $neuName = [];
    $ziele = []; $nichtIm = []; $gesetzt = []; $konflikt = 0; $unveraendert = 0;
    foreach ($rows as $r) {
        $ziel = OFFER_STD;
        if ($r['gruppe'] !== '') {
            $ziel = $bei[$r['gruppe']] ?? (isset($neuName[$r['gruppe']]) ? 'neu:' . $r['gruppe'] : null);
            if ($ziel === null) continue;
        }
        $k = angebot_code_key($r['code']);
        if (!isset($items[$k])) { $nichtIm[$r['code']] = true; continue; }
        if (isset($gesetzt[$ziel . '|' . $k])) { if ($gesetzt[$ziel . '|' . $k] !== $r['preis']) $konflikt++; continue; }
        $gesetzt[$ziel . '|' . $k] = $r['preis'];
        $z = $ziele[$ziel] ?? ['preise' => 0, 'geaendert' => 0, 'neu' => 0, 'aend' => []];
        foreach ($items[$k] as $i) {
            $it = $model['items'][$i];
            $alt = $ziel === OFFER_STD ? ($it['price'] ?? null) : (strpos($ziel, 'neu:') === 0 ? null : ($it['variants'][$ziel] ?? null));
            $altWert = is_array($alt) && ($alt['status'] ?? '') === 'value' ? (float)$alt['value'] : null;
            if ($altWert !== null && abs($altWert - $r['preis']) < 0.00005) { $unveraendert++; continue; }
            $altWert !== null ? $z['geaendert']++ : $z['neu']++;
            $z['aend'][] = ['i' => $i, 'wert' => $r['preis'], 'alt' => $altWert, 'zeile' => $r['zeile']];
        }
        $z['preise']++;
        $ziele[$ziel] = $z;
    }
    $name = function (string $z) use ($oname, $neuName) { return strpos($z, 'neu:') === 0 ? $neuName[substr($z, 4)] . ' (neu)' : ($oname[$z] ?? $z); };
    $gruppenText = [OFFER_STD => 'ohne Kundengruppe'];
    foreach ($offers as $o) { $g = array_map('strval', $o['gruppen'] ?? []); $gruppenText[$o['id']] = $g ? (count($g) === 1 ? 'Gruppe ' : 'Gruppen ') . implode(', ', $g) : 'ohne Kundengruppe'; }
    return ['ziele' => $ziele, 'fehlt' => $fehlt, 'unbekannt' => $unbekannt, 'kg' => $kg, 'neuName' => $neuName, 'vorschlag' => $vorschlag, 'zuViele' => $zuViele, 'frei' => $frei,
            'nichtIm' => array_keys($nichtIm), 'konflikt' => $konflikt, 'unveraendert' => $unveraendert, 'name' => $name, 'gruppenText' => $gruppenText];
}

/* Vorschau/Ergebnis im Format der Importzentrale aus Plan, Fehlerzeilen und Angebotswoche */
function angebot_preise_ergebnis(array $plan, array $model, array $fehler, array $woche, array $opt, string $stand): array
{
    [$w, $y] = $woche;
    $zeilen = $fehler;
    $n = ['neu' => 0, 'geaendert' => 0, 'entfaellt' => 0, 'unveraendert' => $plan['unveraendert'], 'fehler' => count($fehler)];
    $altW = $model['meta']['week'] ?? null; $altY = $model['meta']['year'] ?? null;
    if ($altW !== $w || $altY !== $y) {
        $n['geaendert']++;
        $zeilen[] = ['art' => 'geaendert', 'zeile' => null, 'schluessel' => 'KW', 'name' => 'Angebotswoche', 'text' => ($altW ? "KW $altW/$altY" : 'ohne Angabe') . " → KW $w/$y"];
    }
    foreach ($plan['neuName'] as $nr => $nm) {
        $n['neu']++;
        $zeilen[] = ['art' => 'neu', 'zeile' => null, 'schluessel' => 'Angebot', 'name' => $nm, 'text' => "Neues Angebot mit eigener Artikelliste für Kundengruppe $nr" . ($plan['kg'][$nr] !== '' ? ' ' . $plan['kg'][$nr] : '')];
    }
    $je = [];
    // Details für die Darstellung im Browser: je Angebot die Preise mit bisher/neu (höchstens ANGEBOT_PREISE_DETAILS Zeilen)
    $kpi = ['hoch' => 0, 'runter' => 0, 'neu' => 0, 'pruefen' => 0, 'unveraendert' => $plan['unveraendert']];
    $dAngebote = []; $platz = ANGEBOT_PREISE_DETAILS; $gekuerzt = 0; $preise = 0;
    foreach ($plan['ziele'] as $ziel => $z) {
        $ziel = (string)$ziel;
        $nm = ($plan['name'])($ziel);
        $je[] = $nm . ': ' . ($z['preise'] === 1 ? '1 Preis' : number_format($z['preise'], 0, ',', '.') . ' Preise') . ' (' . $z['geaendert'] . ' geändert, ' . $z['neu'] . ' neu)';
        $da = ['id' => $ziel, 'name' => $nm, 'gruppen' => strpos($ziel, 'neu:') === 0 ? 'Gruppe ' . substr($ziel, 4) . ' · neues Angebot' : ($plan['gruppenText'][$ziel] ?? ''),
               'hoch' => 0, 'runter' => 0, 'neu' => 0, 'zeilen' => []];
        foreach ($z['aend'] as $a) {
            $art = $a['alt'] === null ? 'neu' : 'geaendert';
            $n[$art]++; $preise++;
            $zeilen[] = ['art' => $art, 'zeile' => $a['zeile'], 'schluessel' => (string)$model['items'][$a['i']]['code'], 'name' => $model['items'][$a['i']]['name'] . ' · ' . $nm,
                         'text' => ($a['alt'] === null ? 'Preis ' : angebot_preis_text($a['alt']) . ' → ') . angebot_preis_text($a['wert'])];
            $k = $a['alt'] === null ? 'neu' : ($a['wert'] > $a['alt'] ? 'hoch' : 'runter');
            $pruefen = $a['alt'] !== null && $a['alt'] > 0 && abs($a['wert'] - $a['alt']) / $a['alt'] * 100 >= ANGEBOT_PREISE_PRUEFEN;
            $kpi[$k]++; $da[$k]++; if ($pruefen) $kpi['pruefen']++;
            if ($platz-- > 0) $da['zeilen'][] = [(string)$model['items'][$a['i']]['code'], (string)$model['items'][$a['i']]['name'], $a['alt'], $a['wert'], $a['zeile'], $pruefen ? 1 : 0];
            else $gekuerzt++;
        }
        $dAngebote[] = $da;
    }
    $ohne = [];
    foreach ($plan['fehlt'] as $nr => $c) {
        $nr = (string)$nr;
        $ohne[] = ['nr' => $nr, 'name' => $plan['kg'][$nr] ?? '', 'preise' => $c, 'angebot' => $plan['vorschlag'][$nr] ?? '', 'an' => isset($plan['neuName'][$nr])];
    }
    $nAngebote = count($dAngebote);
    $neuA = count($plan['neuName']);
    $wTxt = "KW $w/$y";
    $pt = $preise === 1 ? '1 Preis' : number_format($preise, 0, ',', '.') . ' Preise';
    $fuss = $pt . ' in ' . ($nAngebote === 1 ? '1 Angebot' : $nAngebote . ' Angeboten') . ' · ' . ($neuA ? ($neuA === 1 ? '1 neues Angebot' : $neuA . ' neue Angebote') : 'keine neuen Angebote') . ' · Angebotswoche ' . $wTxt;
    $knopf = $preise ? $pt . ' übernehmen' : 'Übernehmen';
    $h = [['stufe' => 'info', 'text' => "Angebotswoche: KW $w/$y" . (($altW !== $w || $altY !== $y) && $altW ? " (bisher KW $altW/$altY)" : '') . '. Eingetragen wird in den Entwurf – die Kunden sehen die Preise erst nach „Veröffentlichen“ im Angebotseditor. Preise, die nicht in der Datei stehen, bleiben unverändert.']];
    if ($je) $h[] = ['stufe' => 'info', 'text' => 'Je Angebot: ' . implode(' · ', $je) . '.'];
    $liste = function (array $g) use ($plan) {
        $t = [];
        foreach (array_slice($g, 0, 12, true) as $nr => $c) { $kn = $plan['kg'][(string)$nr] ?? ''; $t[] = $nr . ($kn !== '' ? ' ' . $kn : '') . " ($c)"; }
        return implode(', ', $t) . (count($g) > 12 ? ' …' : '');
    };
    $nichtGew = array_diff_key($plan['fehlt'], $plan['neuName']);
    if ($nichtGew) {
        $h[] = ['stufe' => 'warn', 'text' => (count($nichtGew) === 1 ? '1 Kundengruppe hat' : count($nichtGew) . ' Kundengruppen haben') . ' noch kein Angebot und ' . (count($nichtGew) === 1 ? 'ist' : 'sind') . ' nicht ausgewählt: ' . $liste($nichtGew) . ' – ihre Preise werden nicht übernommen.'];
    }
    $zuViele = 'Es sind höchstens ' . OFFER_MAX . ' Angebote möglich – noch ' . $plan['frei'] . ' frei. Bitte weniger Kundengruppen auswählen; so wird kein Angebot angelegt.';
    if ($plan['zuViele']) $h[] = ['stufe' => 'warn', 'text' => $zuViele];
    // Weitere Hinweise: auch in der eigenen Darstellung (Woche, Angebote und Kundengruppen zeigt sie selbst)
    $weitere = [];
    if ($plan['unbekannt']) $weitere[] = ['stufe' => 'warn', 'text' => 'Nicht unter Stammdaten → Kundengruppen: ' . $liste($plan['unbekannt']) . ' – Preise nicht übernommen.'];
    if ($plan['nichtIm']) $weitere[] = ['stufe' => 'info', 'text' => (count($plan['nichtIm']) === 1 ? '1 Artikelnummer steht' : number_format(count($plan['nichtIm']), 0, ',', '.') . ' Artikelnummern stehen') . ' nicht im Angebot und ' . (count($plan['nichtIm']) === 1 ? 'wird' : 'werden') . ' übersprungen.'];
    if ($plan['konflikt']) $weitere[] = ['stufe' => 'warn', 'text' => $plan['konflikt'] . '× unterschiedliche Preise für denselben Artikel im selben Angebot (mehrere Kundengruppen) – der erste gilt.'];
    $h = array_merge($h, $weitere);
    $details = ['woche' => ['alt' => $altW ? "KW $altW/$altY" : null, 'neu' => $wTxt], 'kpi' => $kpi, 'angebote' => $dAngebote, 'ohne' => $ohne,
                'gekuerzt' => $gekuerzt, 'grenze' => ANGEBOT_PREISE_PRUEFEN, 'zuViele' => $plan['zuViele'] ? $zuViele : '', 'hinweise' => $weitere];
    return ['zahlen' => $n, 'zeilen' => $zeilen, 'hinweise' => $h, 'stand' => $stand, 'details' => $details, 'fuss' => $fuss, 'knopf' => $knopf];
}

function angebot_preise_vorschau(array $e, array $me): array
{
    [$rows, $fehler] = angebot_preise_zeilen($e);
    [, $basis, $offers, $stand] = angebot_preise_basis();
    $plan = angebot_preise_plan($basis, $offers['offers'], $rows, (array)($e['optionen']['gruppen'] ?? []));
    return angebot_preise_ergebnis($plan, $basis, $fehler, angebot_preise_woche($e['optionen']['woche'] ?? null), $e['optionen'], $stand);
}

/* Neue Angebote für Kundengruppen ohne Angebot (eigene Artikelliste, Gruppe zugeordnet) – Regeln wie offers_save:
   eindeutige Namen, nie die ID eines gelöschten Angebots, höchstens OFFER_MAX. Gibt Gruppe → Angebots-ID zurück. */
function angebote_fuer_gruppen_anlegen(array $neuName, int $rev, array $me): array
{
    return with_lock('angebote', function () use ($neuName, $rev, $me) {
        $cur = offers_load();
        if ((int)$cur['rev'] !== $rev) fail('Die Angebote wurden inzwischen an anderer Stelle geändert. Die Vorschau wird neu geladen.', 409);
        $offers = $cur['offers'];
        if (count(sonder_ohne($offers)) + count($neuName) > OFFER_MAX) fail('Höchstens ' . OFFER_MAX . ' Kundenangebote.', 422);
        $gesperrt = array_values(array_unique(array_merge(array_values(array_filter(is_array($cur['geloescht'] ?? null) ? $cur['geloescht'] : [], 'is_string')),
            angebot_ids_mit_resten(array_column($offers, 'id')))));
        $belegt = array_flip(array_merge(array_column($offers, 'id'), $gesperrt, [OFFER_STD]));
        $ids = []; $d = [];
        foreach ($neuName as $nr => $name) {
            $basis = angebot_slug($name); $id = $basis; $k = 2;
            while (isset($belegt[$id])) $id = substr($basis, 0, 36) . '-' . $k++;
            $belegt[$id] = true;
            $offers[] = ['id' => $id, 'name' => $name, 'fallback' => 'hidden', 'gruppen' => [(string)$nr]];
            $ids[(string)$nr] = $id;
            $d[] = ['k' => "o$id|+", 'code' => '', 'name' => $name, 'f' => 'Neues Angebot', 'from' => '', 'to' => 'Artikelliste: eigene Artikelliste'];
            $d[] = ['k' => "o$id|grp", 'code' => '', 'name' => $name, 'f' => 'Kundengruppen', 'from' => '', 'to' => (string)$nr];
        }
        $out = ['rev' => (int)$cur['rev'] + 1, 'updatedAt' => now(), 'updatedBy' => $me['name'], 'offers' => array_values($offers)]
             + array_diff_key($cur, array_flip(['rev', 'updatedAt', 'updatedBy', 'offers']));   // weitere Felder bleiben (GR-006)
        store_write('angebote', $out);
        audit('offers', 'Angebote für Kundengruppen angelegt (Preisimport)', $d);
        return $ids;
    });
}

function angebot_preise_uebernehmen(array $e, array $me): array
{
    [$rows, $fehler] = angebot_preise_zeilen($e);
    $woche = angebot_preise_woche($e['optionen']['woche'] ?? null);
    return with_lock('entwurf', function () use ($e, $me, $rows, $fehler, $woche) {
        [$draft, $basis, $offers, $stand] = angebot_preise_basis();
        if ((string)($e['stand'] ?? '') !== $stand) fail('Der Entwurf oder die Angebote wurden inzwischen geändert. Die Vorschau wird neu geladen.', 409);
        $plan = angebot_preise_plan($basis, $offers['offers'], $rows, (array)($e['optionen']['gruppen'] ?? []));
        $r = angebot_preise_ergebnis($plan, $basis, $fehler, $woche, $e['optionen'], $stand);
        $ids = $plan['neuName'] ? angebote_fuer_gruppen_anlegen($plan['neuName'], (int)$offers['rev'], $me) : [];
        $model = $basis;
        $preise = 0;
        foreach ($plan['ziele'] as $ziel => $z) {
            $ziel = (string)$ziel;
            $oid = strpos($ziel, 'neu:') === 0 ? ($ids[substr($ziel, 4)] ?? null) : $ziel;
            if ($oid === null) continue;
            foreach ($z['aend'] as $a) {
                if ($oid === OFFER_STD) {
                    $label = $model['items'][$a['i']]['price']['label'] ?? '';
                    $model['items'][$a['i']]['price'] = ['status' => 'value', 'value' => $a['wert']] + ($label !== '' ? ['label' => $label] : []);
                } else {
                    $model['items'][$a['i']]['variants'][$oid] = ['status' => 'value', 'value' => $a['wert']];
                }
                $preise++;
            }
        }
        $model['meta']['week'] = $woche[0];
        $model['meta']['year'] = $woche[1];
        $prev = $draft;
        $model = clean_model($model, false);
        $model['savedAt'] = now();
        $model['savedBy'] = $me['name'];
        $model['rev'] = draft_rev($prev) + 1;
        store_write('entwurf', $model);
        $dd = changes_between($basis, $model);
        audit('import', 'Preise importiert: ' . ($e['quelle'] ?: 'Datei') . ' – KW ' . $woche[0] . '/' . $woche[1] . ', ' . $preise . ' Preise' . ($ids ? ', ' . (count($ids) === 1 ? '1 Angebot' : count($ids) . ' Angebote') . ' angelegt' : '')
            . ' (' . ($dd ? changes_summary($dd) : 'keine Änderung') . ')', array_slice($dd, 0, 2000));
        $r['stand'] = $model['rev'] . '.' . (int)offers_load()['rev'];
        return $r;
    });
}

/* Eine Woche speichern (ersetzt eine vorhandene Woche) und protokollieren – Aktion history_import und Importzentrale */
function preisverlauf_woche_speichern(int $week, int $year, $items, string $source): array
{
    $items = clean_history_items($items);
    $id = history_id($week, $year);
    $replaced = store_read('historie/' . $id) !== null;
    store_write('historie/' . $id, ['week' => $week, 'year' => $year, 'origin' => 'Import', 'source' => mb_substr($source, 0, 200), 'savedAt' => now(), 'items' => $items]);
    history_undelete($id);
    audit('history', 'Preisverlauf: KW ' . $week . '/' . $year . ($replaced ? ' ersetzt' : ' hochgeladen') . ' – ' . (mb_substr($source, 0, 120) ?: 'ohne Dateiname') . ', ' . count($items) . ' Artikel');
    return ['id' => $id, 'replaced' => $replaced, 'items' => count($items)];
}

/* Wochen der Dateien prüfen: gültige Woche, Artikel; doppelte Woche → die spätere Datei zählt (wie im Preisverlauf) */
function preisverlauf_import_wochen(array $e): array
{
    $roh = is_array($e['wochen'] ?? null) ? array_values($e['wochen']) : [];
    if (!$roh) fail('Keine Angebotslisten gefunden.', 422);
    if (count($roh) > 60) fail('Zu viele Dateien auf einmal (höchstens 60).', 422);
    $ok = []; $fehler = [];
    foreach ($roh as $i => $w) {
        $datei = s(is_array($w) ? ($w['datei'] ?? '') : '', 200) ?? '';
        $week = is_array($w) ? ($w['week'] ?? null) : null; $year = is_array($w) ? ($w['year'] ?? null) : null;
        if (!is_int($week) || !is_int($year) || $year < 2000 || $year > 2100 || !kw_gueltig($week, $year)) {
            $fehler[] = ['datei' => $datei, 'text' => 'Kalenderwoche oder Jahr nicht erkannt – bitte unter Preisverlauf → „Alte Angebote hochladen“ eintragen'];
            continue;
        }
        try { $items = clean_history_items($w['items'] ?? null); }
        catch (InvalidArgumentException $ex) { $fehler[] = ['datei' => $datei, 'text' => $ex->getMessage()]; continue; }
        $id = history_id($week, $year);
        if (isset($ok[$id])) $fehler[] = ['datei' => $ok[$id]['datei'], 'text' => "KW $week/$year steht auch in „{$datei}“ – die spätere Datei zählt"];
        $ok[$id] = ['datei' => $datei, 'week' => $week, 'year' => $year, 'items' => $items, 'i' => $i];
    }
    return [$ok, $fehler];
}

function preisverlauf_import_vorschau(array $e, array $me): array
{
    [$ok, $fehler] = preisverlauf_import_wochen($e);
    $z = []; $n = ['neu' => 0, 'geaendert' => 0, 'entfaellt' => 0, 'unveraendert' => 0, 'fehler' => count($fehler)];
    foreach ($ok as $id => $w) {
        $alt = store_read('historie/' . $id);
        $art = $alt ? 'geaendert' : 'neu';
        $n[$art]++;
        $z[] = ['art' => $art, 'zeile' => null, 'schluessel' => "KW {$w['week']}/{$w['year']}", 'name' => $w['datei'], 'text' => count($w['items']) . ' Artikel' . ($alt ? ' – ersetzt die gespeicherte Woche (' . count($alt['items'] ?? []) . ' Artikel, ' . (($alt['origin'] ?? '') === 'Import' ? 'Import' : 'Veröffentlichung') . ')' : '')];
    }
    foreach ($fehler as $f) $z[] = ['art' => 'fehler', 'zeile' => null, 'schluessel' => '', 'name' => $f['datei'], 'text' => $f['text']];
    $h = [['stufe' => 'info', 'text' => 'Jede Datei wird eine Woche im Preisverlauf; eine schon gespeicherte Woche wird ersetzt. Das aktuelle Angebot bleibt unverändert.']];
    return ['zahlen' => $n, 'zeilen' => $z, 'hinweise' => $h, 'stand' => null];
}

function preisverlauf_import_uebernehmen(array $e, array $me): array
{
    $v = preisverlauf_import_vorschau($e, $me);
    [$ok] = preisverlauf_import_wochen($e);
    foreach ($ok as $w) preisverlauf_woche_speichern($w['week'], $w['year'], $w['items'], $w['datei']);
    return $v;
}
