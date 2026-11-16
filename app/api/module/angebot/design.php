<?php
declare(strict_types=1);
/* Angebot · Design je Angebot (Inhaber 16.11.2026): Aufbau und Raster des Angebots für Druck/PDF und Kundenseite.
   Dokument „angebot-designs“: { rev, vorlagen: [{ id, name, raster: {spalten 1–4, format quer|hoch}, abschnitte, angelegt, geaendert }] }.
   Abschnitt: { art: 'gruppen', titel, spalten?, inhalt: [{bereich: Name} | {gruppe: Name}] } (inhalt leer = alle übrigen Gruppen)
            | { art: 'text', titel, text }. Bereiche und Gruppen stehen mit Namen, nicht mit Kennung: die Kennungen der Gruppen
   vergibt der Excel-Import je Woche neu (g1, g2 …), die Namen bleiben.
   Am Angebot: design = { vorlage: Kennung ('' = Standard), anpassung?: { raster?: {spalten?, format?}, abschnitte? } } –
   Kunden- und Sonderangebote in ihrer Definition (Dokument „angebote“), das Wochenangebot dort als „stdDesign“, Einzelangebote
   am Eintrag in „einzelangebote“. Gespeichert wird nur, was von der Vorlage abweicht (Raster je Feld, Abschnitte als Ganzes).
   Ausgeliefert wird nur das wirksame Layout (design_wirksam in offer_resolve und einzel_model): Spalten, Format und Abschnitte mit
   Namen und Texten – nie weitere Felder. Welche Gruppe in welchen Abschnitt kommt, entscheidet die Angebotsseite für Bildschirm
   und Druck an einer Stelle (plAbschnitte in assets/frontend.js); Gruppen ohne Zuordnung stehen im ersten Abschnitt ohne Inhalt,
   sonst unter „Weitere Artikel“ (GR-010). Ohne Design gilt das bisherige Verhalten (Standard: drei Spalten, quer). */
if (!defined('WA_API')) { http_response_code(404); exit; }

const DESIGN_VORLAGEN_MAX = 30;
const DESIGN_ABSCHNITTE_MAX = 20;
const DESIGN_INHALT_MAX = 60;
const DESIGN_TEXT_MAX = 1000;
const DESIGN_FORMATE = ['quer', 'hoch'];
const DESIGN_STANDARD = ['raster' => ['spalten' => 3, 'format' => 'quer'], 'abschnitte' => []];

function design_load(): array
{
    $d = store_read('angebot-designs');
    $d = is_array($d) ? $d : [];
    return ['rev' => (int)($d['rev'] ?? 0), 'vorlagen' => array_values(is_array($d['vorlagen'] ?? null) ? $d['vorlagen'] : [])] + $d;
}
function design_vorlage(string $id): ?array
{
    foreach (design_load()['vorlagen'] as $v) if ((string)($v['id'] ?? '') === $id) return $v;
    return null;
}

/* Raster einer Vorlage (alle Felder, Vorgabe Standard) bzw. einer Anpassung ($teil: nur die übergebenen Felder) */
function design_raster_clean($v, bool $teil): array
{
    if ($v === null && $teil) return [];
    if (!is_array($v)) throw new InvalidArgumentException('Ungültiges Raster.');
    $out = [];
    if (!$teil || array_key_exists('spalten', $v)) {
        $s = $v['spalten'] ?? DESIGN_STANDARD['raster']['spalten'];
        if (!is_int($s) || $s < 1 || $s > 4) throw new InvalidArgumentException('Die Spaltenzahl muss zwischen 1 und 4 liegen.');
        $out['spalten'] = $s;
    }
    if (!$teil || array_key_exists('format', $v)) {
        $f = $v['format'] ?? DESIGN_STANDARD['raster']['format'];
        if (!in_array($f, DESIGN_FORMATE, true)) throw new InvalidArgumentException('Das Format ist „quer“ oder „hoch“.');
        $out['format'] = $f;
    }
    return $out;
}
/* Freier Text mit Zeilen: ohne Steuerzeichen, höchstens 30 Zeilen und $max Zeichen */
function design_text($v, int $max): string
{
    $t = preg_replace('/[\x00-\x09\x0b-\x1f\x7f]/u', '', str_replace("\r", '', is_string($v) ? $v : '')) ?? '';
    return mb_substr(trim(implode("\n", array_slice(array_map('trim', explode("\n", $t)), 0, 30))), 0, $max);
}
function design_abschnitte_clean($v): array
{
    if (!is_array($v) || !array_is_list($v)) throw new InvalidArgumentException('Ungültige Abschnitte.');
    if (count($v) > DESIGN_ABSCHNITTE_MAX) throw new InvalidArgumentException('Höchstens ' . DESIGN_ABSCHNITTE_MAX . ' Abschnitte je Design.');
    $out = [];
    foreach ($v as $a) {
        if (!is_array($a)) throw new InvalidArgumentException('Ungültiger Abschnitt.');
        $titel = s($a['titel'] ?? '', 80) ?? '';
        if (($a['art'] ?? '') === 'text') {
            $text = design_text($a['text'] ?? '', DESIGN_TEXT_MAX);
            if ($titel === '' && $text === '') throw new InvalidArgumentException('Ein Text-Abschnitt braucht eine Überschrift oder einen Text.');
            $out[] = ['art' => 'text', 'titel' => $titel, 'text' => $text];
            continue;
        }
        if (($a['art'] ?? '') !== 'gruppen') throw new InvalidArgumentException('Unbekannte Art eines Abschnitts.');
        $in = $a['inhalt'] ?? [];
        if (!is_array($in) || count($in) > DESIGN_INHALT_MAX) throw new InvalidArgumentException('Höchstens ' . DESIGN_INHALT_MAX . ' Bereiche und Gruppen je Abschnitt.');
        $inhalt = []; $da = [];
        foreach ($in as $r) {
            $typ = is_array($r) && array_key_exists('bereich', $r) ? 'bereich' : 'gruppe';
            $name = is_array($r) ? s($r[$typ] ?? null, 200, false) : null;
            if ($name === null) throw new InvalidArgumentException('Ungültiger Bereich oder ungültige Gruppe in einem Abschnitt.');
            if (isset($da[$typ . "\x01" . mb_strtolower($name)])) continue;
            $da[$typ . "\x01" . mb_strtolower($name)] = true;
            $inhalt[] = [$typ => $name];
        }
        $row = ['art' => 'gruppen', 'titel' => $titel, 'inhalt' => $inhalt];
        if (($a['spalten'] ?? null) !== null) $row['spalten'] = design_raster_clean(['spalten' => $a['spalten']], true)['spalten'];
        $out[] = $row;
    }
    return $out;
}
function design_basis(string $vorlage): array
{
    $v = $vorlage === '' ? null : design_vorlage($vorlage);
    return $v ? ['raster' => $v['raster'], 'abschnitte' => $v['abschnitte']] : DESIGN_STANDARD;
}
/* Design am Angebot prüfen: null = Standard ohne Anpassung. Die Anpassung behält nur, was von der Vorlage abweicht. */
function design_wahl_clean($v): ?array
{
    if ($v === null) return null;
    if (!is_array($v)) throw new InvalidArgumentException('Ungültiges Design.');
    $vid = is_string($v['vorlage'] ?? null) ? $v['vorlage'] : '';
    if ($vid !== '' && !design_vorlage($vid)) throw new InvalidArgumentException('Diese Vorlage gibt es nicht (mehr). Bitte neu laden.');
    $basis = design_basis($vid);
    $an = is_array($v['anpassung'] ?? null) ? $v['anpassung'] : [];
    $anpassung = [];
    $raster = array_filter(design_raster_clean($an['raster'] ?? null, true), fn($x, $k) => $basis['raster'][$k] !== $x, ARRAY_FILTER_USE_BOTH);
    if ($raster) $anpassung['raster'] = $raster;
    if (($an['abschnitte'] ?? null) !== null) {
        $ab = design_abschnitte_clean($an['abschnitte']);
        if ($ab !== $basis['abschnitte']) $anpassung['abschnitte'] = $ab;
    }
    if ($vid === '' && !$anpassung) return null;
    return ['vorlage' => $vid] + ($anpassung ? ['anpassung' => $anpassung] : []);
}
/* Wirksames Layout eines Designs – null: Standard (bisheriges Verhalten, nichts ausgeliefert). Eine gelöschte Vorlage gilt als Standard. */
function design_wirksam($wahl): ?array
{
    if (!is_array($wahl)) return null;
    $basis = design_basis((string)($wahl['vorlage'] ?? ''));
    $an = is_array($wahl['anpassung'] ?? null) ? $wahl['anpassung'] : [];
    $out = ['raster' => (is_array($an['raster'] ?? null) ? $an['raster'] : []) + $basis['raster'],
            'abschnitte' => is_array($an['abschnitte'] ?? null) ? $an['abschnitte'] : $basis['abschnitte']];
    return $out == DESIGN_STANDARD ? null : $out;
}
/* Vorlage-Kennung → Namen der Angebote, die sie nutzen */
function design_nutzung(): array
{
    $o = offers_load();
    $n = [];
    $zu = function ($w, string $name) use (&$n) { $v = is_array($w) ? (string)($w['vorlage'] ?? '') : ''; if ($v !== '') $n[$v][] = $name; };
    $zu($o['stdDesign'] ?? null, 'Wochenangebot');
    foreach ($o['offers'] as $x) $zu($x['design'] ?? null, (string)$x['name']);
    foreach (einzel_load()['list'] as $e) $zu($e['design'] ?? null, 'Einzelangebot ' . $e['nr']);
    return $n;
}
function design_text_wahl(?array $wahl): string
{
    $v = $wahl && $wahl['vorlage'] !== '' ? design_vorlage($wahl['vorlage']) : null;
    return ($v ? 'Vorlage „' . $v['name'] . '“' : 'Standard') . (!empty($wahl['anpassung']) ? ', angepasst' : '');
}

/* Daten für das Fenster „Design“: Vorlagen mit Nutzung und – mit $oid – das Design dieses Angebots */
function design_liste(array $me, string $oid): array
{
    $nutzung = design_nutzung();
    $d = design_load();
    $out = ['rev' => $d['rev'], 'standard' => DESIGN_STANDARD, 'darfVorlagen' => may($me, 'angebote.verwalten'),
            'vorlagen' => array_map(fn($v) => ['id' => $v['id'], 'name' => $v['name'], 'raster' => $v['raster'], 'abschnitte' => $v['abschnitte'],
                                              'genutzt' => $nutzung[$v['id']] ?? []], $d['vorlagen'])];
    if ($oid === '') return $out;
    if (strncmp($oid, 'e-', 2) === 0) {
        if (!may($me, 'einzelangebote.sehen')) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
        $e = einzel_von_kennung($oid);
        if (!$e) fail('Einzelangebot nicht gefunden.', 404);
        return $out + ['wahl' => $e['design'] ?? null, 'darfWahl' => may($me, 'einzelangebote.bearbeiten')];
    }
    $def = offer_def($oid);
    if (!$def) fail('Unbekanntes Angebot.', 404);
    return $out + ['wahl' => $def['design'] ?? null, 'darfWahl' => may($me, 'angebot.bearbeiten')];
}

/* Vorlage anlegen ($b ohne id) oder ändern: {rev, id?, name, raster, abschnitte}; Recht prüft die Aktion */
function design_vorlage_speichern(array $me, array $b): array
{
    $name = s($b['name'] ?? null, 60, false);
    if ($name === null || mb_strlen($name) < 2) throw new InvalidArgumentException('Bitte einen Namen für die Vorlage angeben (mindestens 2 Zeichen).');
    if (mb_strtolower($name) === 'standard') throw new InvalidArgumentException('„Standard“ ist das eingebaute Design – bitte einen anderen Namen wählen.');
    $raster = design_raster_clean($b['raster'] ?? null, false);
    $abschnitte = design_abschnitte_clean($b['abschnitte'] ?? []);
    $id = is_string($b['id'] ?? null) ? $b['id'] : '';
    [$row, $d, $neu] = with_lock('angebot-designs', function () use ($me, $b, $name, $raster, $abschnitte, $id) {
        $d = design_load();
        if ((int)($b['rev'] ?? -1) !== $d['rev']) fail('Die Vorlagen wurden inzwischen geändert. Bitte neu laden.', 409);
        $idx = null;
        foreach ($d['vorlagen'] as $i => $v) if ((string)$v['id'] === $id) $idx = $i;
        if ($id !== '' && $idx === null) fail('Diese Vorlage gibt es nicht (mehr).', 404);
        foreach ($d['vorlagen'] as $i => $v) if ($i !== $idx && mb_strtolower((string)$v['name']) === mb_strtolower($name)) throw new InvalidArgumentException("Der Name „{$name}“ ist bereits vergeben.");
        $wer = ['t' => now(), 'von' => (string)$me['name']];
        if ($idx === null) {
            if (count($d['vorlagen']) >= DESIGN_VORLAGEN_MAX) throw new InvalidArgumentException('Höchstens ' . DESIGN_VORLAGEN_MAX . ' Vorlagen – bitte eine nicht mehr benötigte löschen.');
            $row = ['id' => bin2hex(random_bytes(5)), 'name' => $name, 'raster' => $raster, 'abschnitte' => $abschnitte, 'angelegt' => $wer];
            $d['vorlagen'][] = $row;
        } else {
            // Felder, die dieser Stand nicht kennt (neuere Fassung), bleiben erhalten (GR-006)
            $row = ['id' => $id, 'name' => $name, 'raster' => $raster, 'abschnitte' => $abschnitte, 'geaendert' => $wer]
                 + array_diff_key($d['vorlagen'][$idx], array_flip(['id', 'name', 'raster', 'abschnitte', 'geaendert']));
            $d['vorlagen'][$idx] = $row;
        }
        $d['rev']++;
        store_write('angebot-designs', $d);
        return [$row, $d, $idx === null];
    });
    audit('offers', 'Design-Vorlage „' . $name . '“ ' . ($neu ? 'angelegt' : 'gespeichert') . ' (' . $raster['spalten'] . ' Spalten, ' . $raster['format'] . ', '
        . count($abschnitte) . ' Abschnitte)');
    return ['rev' => $d['rev'], 'id' => $row['id']];
}
/* Vorlage löschen: {rev, id} – nicht, solange ein Angebot sie nutzt (409 mit den Namen). Unter den Sperren der Angebote und
   Einzelangebote, damit niemand die Vorlage gleichzeitig wählt (design_setzen prüft unter derselben Sperre). */
function design_vorlage_loeschen(array $me, array $b): array
{
    $id = is_string($b['id'] ?? null) ? $b['id'] : '';
    [$name, $d] = with_lock('angebote', fn() => with_lock('einzelangebote', fn() => with_lock('angebot-designs', function () use ($b, $id) {
        $d = design_load();
        if ((int)($b['rev'] ?? -1) !== $d['rev']) fail('Die Vorlagen wurden inzwischen geändert. Bitte neu laden.', 409);
        $idx = null;
        foreach ($d['vorlagen'] as $i => $v) if ((string)$v['id'] === $id) $idx = $i;
        if ($idx === null) fail('Diese Vorlage gibt es nicht (mehr).', 404);
        $name = (string)$d['vorlagen'][$idx]['name'];
        $wer = design_nutzung()[$id] ?? [];
        if ($wer) fail("Die Vorlage „{$name}“ wird noch genutzt: " . implode(', ', array_slice($wer, 0, 6)) . (count($wer) > 6 ? ' und ' . (count($wer) - 6) . ' weitere' : '')
            . '. Bitte dort zuerst ein anderes Design wählen.', 409);
        array_splice($d['vorlagen'], $idx, 1);
        $d['rev']++;
        store_write('angebot-designs', $d);
        return [$name, $d];
    })));
    audit('offers', 'Design-Vorlage „' . $name . '“ gelöscht', [], $me);
    return ['rev' => $d['rev']];
}
/* Design eines Angebots setzen ($design null = Standard): Kunden- und Sonderangebote, Wochenangebot („std“), Einzelangebote („e-…“).
   Wirkt sofort auf Kundenseite und Druck. Recht prüft die Aktion (angebot.bearbeiten bzw. einzelangebote.bearbeiten). */
function design_setzen(array $me, string $oid, $design): array
{
    $wahl = null;
    if (strncmp($oid, 'e-', 2) === 0) {
        $e = with_lock('einzelangebote', function () use ($oid, $design, &$wahl) {
            $wahl = design_wahl_clean($design);   // unter der Sperre: die Vorlage kann nicht gerade gelöscht werden
            $d = einzel_load();
            $i = preg_match('/^e-([a-f0-9]{10})$/', $oid, $m) ? einzel_find($d, $m[1]) : null;
            if ($i === null) fail('Einzelangebot nicht gefunden.', 404);
            if ($wahl === null) unset($d['list'][$i]['design']); else $d['list'][$i]['design'] = $wahl;
            store_write('einzelangebote', $d);
            return $d['list'][$i];
        });
        $name = 'Einzelangebot ' . $e['nr'];
    } else {
        $def = offer_def($oid);
        if (!$def) fail('Unbekanntes Angebot.', 404);
        with_lock('angebote', function () use ($oid, $design, &$wahl) {
            $wahl = design_wahl_clean($design);
            $cur = offers_load();
            if ($oid === OFFER_STD) {
                if ($wahl === null) unset($cur['stdDesign']); else $cur['stdDesign'] = $wahl;
            } else {
                $i = array_search($oid, array_map('strval', array_column($cur['offers'], 'id')), true);
                if ($i === false) fail('Unbekanntes Angebot.', 404);
                if ($wahl === null) unset($cur['offers'][$i]['design']); else $cur['offers'][$i]['design'] = $wahl;
            }
            store_write('angebote', $cur);
        });
        $name = (string)$def['name'];
    }
    audit('offers', 'Design von „' . $name . '“: ' . design_text_wahl($wahl), [], $me);
    return ['wahl' => $wahl, 'wirksam' => design_wirksam($wahl)];
}
