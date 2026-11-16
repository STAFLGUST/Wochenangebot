<?php
declare(strict_types=1);
/* Angebot · Design je Angebot (Inhaber 16.11.2026): Aufbau und Raster des Angebots für Druck/PDF und Kundenseite.
   Datenform (ausführlich in docs/entwickler/05-daten.md):
   – Vorlagen im Dokument „angebot-designs“ (intern): { rev, vorlagen: [{ id, name, raster: {spalten, format}, abschnitte, angelegt, geaendert }] }.
     Abschnitt nach Art (DESIGN_ARTEN): { art: 'gruppen', titel, spalten?, inhalt: [{bereich: Name} | {gruppe: Name}] } (leer = alle
     übrigen Gruppen) | { art: 'text', titel, text }. Namen statt Kennungen: der Excel-Import vergibt die Gruppen-Kennungen je Woche neu.
   – Wahl am Angebot: design = { vorlage ('' = Standard), anpassung?: { raster?, abschnitte? } } – Kunden- und Sonderangebote in
     „angebote“, das Wochenangebot dort als „stdDesign“, Einzelangebote am Eintrag. Gespeichert wird nur die Abweichung von der Vorlage.
   – Veröffentlicht (GR-106): das wirksame Layout als Schnappschuss, nur mit den Namen, die im Angebot vorkommen, und nur mit bekannten
     Arten (design_fuer). Wochen-, Kunden- und Sonderangebote: beim Veröffentlichen im Modell als meta.design = {Angebots-ID: Layout}
     (design_staende in angebot_veroeffentlichen); Einzelangebote: am Eintrag als designFreigegeben (Freigabe und Speichern eines
     freigegebenen Einzelangebots). Kunden bekommen nur den Schnappschuss (offer_resolve, einzel_model); die Vorschau im Eingabebereich
     zeigt die gespeicherte Wahl. Eine geänderte Wahl oder Vorlage wirkt erst mit der nächsten Veröffentlichung.
   Welche Gruppe in welchen Abschnitt kommt, entscheidet die Angebotsseite für Bildschirm und Druck an einer Stelle (plAbschnitte in
   assets/frontend.js, GR-010). Ohne Design gilt das bisherige Verhalten (drei Spalten, quer). */
if (!defined('WA_API')) { http_response_code(404); exit; }

const DESIGN_VORLAGEN_MAX = 30;
const DESIGN_ABSCHNITTE_MAX = 20;
const DESIGN_INHALT_MAX = 60;
const DESIGN_TEXT_MAX = 1000;
const DESIGN_NAME_MAX = 120;     // Name eines Bereichs oder einer Gruppe in einem Abschnitt
const DESIGN_JSON_MAX = 32768;   // Bytes je Vorlage bzw. Anpassung (sonst wüchse jede Angebotsantwort mit)
const DESIGN_SPALTEN_MAX = ['quer' => 4, 'hoch' => 3];   // im Hochformat werden vier Spalten unlesbar schmal
const DESIGN_STANDARD = ['raster' => ['spalten' => 3, 'format' => 'quer'], 'abschnitte' => []];
const DESIGN_ARTEN = ['gruppen' => 'design_ab_gruppen', 'text' => 'design_ab_text'];   // Art → Prüfung; andere Arten stammen aus einer neueren Fassung

function design_load(): array
{
    $d = store_read('angebot-designs');
    $d = is_array($d) ? $d : [];
    return ['rev' => (int)($d['rev'] ?? 0), 'vorlagen' => array_values(is_array($d['vorlagen'] ?? null) ? $d['vorlagen'] : [])] + $d;
}
function design_index(array $d, string $id): ?int
{
    foreach ($d['vorlagen'] as $i => $v) if ((string)($v['id'] ?? '') === $id) return $i;
    return null;
}
// shortcut: liest „angebot-designs“ bei jedem Aufruf (je Angebot mit Design 2–3-mal beim Veröffentlichen und in der Änderungsliste);
// wird das bei vielen Angeboten und großen Vorlagen spürbar, die Vorlagen einmal je Anfrage laden und durchreichen
function design_vorlage(string $id): ?array
{
    $d = design_load();
    $i = design_index($d, $id);
    return $i === null ? null : $d['vorlagen'][$i];
}

/* ---------- Prüfen ---------- */
function design_spalten($s): int
{
    if (!is_int($s) || $s < 1 || $s > 4) throw new InvalidArgumentException('Die Spaltenzahl muss zwischen 1 und 4 liegen.');
    return $s;
}
/* Raster einer Vorlage (alle Felder, Vorgabe Standard) bzw. einer Anpassung ($teil: nur die übergebenen Felder) */
function design_raster_clean($v, bool $teil): array
{
    if ($v === null && $teil) return [];
    if (!is_array($v)) throw new InvalidArgumentException('Ungültiges Raster.');
    $out = [];
    if (!$teil || array_key_exists('spalten', $v)) $out['spalten'] = design_spalten($v['spalten'] ?? DESIGN_STANDARD['raster']['spalten']);
    if (!$teil || array_key_exists('format', $v)) {
        $f = $v['format'] ?? DESIGN_STANDARD['raster']['format'];
        if (!is_string($f) || !isset(DESIGN_SPALTEN_MAX[$f])) throw new InvalidArgumentException('Das Format ist „quer“ oder „hoch“.');
        $out['format'] = $f;
    }
    return $out;
}
/* Freier Text mit Zeilen: ohne Steuerzeichen, höchstens 30 Zeilen und $max Zeichen */
function design_text($v, int $max): string
{
    if ($v !== null && !is_string($v)) throw new InvalidArgumentException('Der Text eines Abschnitts muss Text sein.');
    $t = preg_replace('/[\x00-\x09\x0b-\x1f\x7f]/u', '', str_replace("\r", '', (string)$v)) ?? '';
    return mb_substr(trim(implode("\n", array_slice(array_map('trim', explode("\n", $t)), 0, 30))), 0, $max);
}
function design_ab_text(array $a, string $titel): array
{
    $text = design_text($a['text'] ?? null, DESIGN_TEXT_MAX);
    if ($titel === '' && $text === '') throw new InvalidArgumentException('Ein Text-Abschnitt braucht eine Überschrift oder einen Text.');
    return ['art' => 'text', 'titel' => $titel, 'text' => $text];
}
function design_ab_gruppen(array $a, string $titel): array
{
    $in = $a['inhalt'] ?? [];
    if (!is_array($in) || !array_is_list($in)) throw new InvalidArgumentException('Ungültiger Inhalt eines Abschnitts.');
    if (count($in) > DESIGN_INHALT_MAX) throw new InvalidArgumentException('Höchstens ' . DESIGN_INHALT_MAX . ' Bereiche und Gruppen je Abschnitt.');
    $inhalt = []; $da = [];
    foreach ($in as $r) {
        $typ = is_array($r) && array_key_exists('bereich', $r) ? 'bereich' : 'gruppe';
        $name = is_array($r) && is_string($r[$typ] ?? null) ? s($r[$typ], DESIGN_NAME_MAX + 1, false) : null;
        if ($name === null || mb_strlen($name) > DESIGN_NAME_MAX) throw new InvalidArgumentException('Ungültiger Bereich oder ungültige Gruppe in einem Abschnitt (Name mit höchstens ' . DESIGN_NAME_MAX . ' Zeichen).');
        if (isset($da[$typ . "\x01" . mb_strtolower($name)])) continue;
        $da[$typ . "\x01" . mb_strtolower($name)] = true;
        $inhalt[] = [$typ => $name];
    }
    $row = ['art' => 'gruppen', 'titel' => $titel, 'inhalt' => $inhalt];
    if (($a['spalten'] ?? null) !== null) $row['spalten'] = design_spalten($a['spalten']);
    return $row;
}
function design_abschnitte_clean($v): array
{
    if (!is_array($v) || !array_is_list($v)) throw new InvalidArgumentException('Ungültige Abschnitte.');
    if (count($v) > DESIGN_ABSCHNITTE_MAX) throw new InvalidArgumentException('Höchstens ' . DESIGN_ABSCHNITTE_MAX . ' Abschnitte je Design.');
    $out = [];
    foreach ($v as $a) {
        $art = is_array($a) ? ($a['art'] ?? null) : null;
        if (!is_string($art) || !preg_match('/^[a-z]{1,20}$/', $art)) throw new InvalidArgumentException('Ungültiger Abschnitt.');
        if (!isset(DESIGN_ARTEN[$art])) { $out[] = $a; continue; }   // Art einer neueren Fassung: unverändert behalten (GR-006), ausgeliefert nie (design_fuer)
        if (($a['titel'] ?? null) !== null && !is_string($a['titel'])) throw new InvalidArgumentException('Die Überschrift eines Abschnitts muss Text sein.');
        $out[] = (DESIGN_ARTEN[$art])($a, s($a['titel'] ?? '', 80) ?? '');
    }
    return $out;
}
/* Ganzes Layout: im Hochformat höchstens drei Spalten – im Raster und in jedem Gruppen-Abschnitt */
function design_layout_pruefen(array $l): void
{
    $max = DESIGN_SPALTEN_MAX[$l['raster']['format']] ?? 4;
    $spalten = [(int)$l['raster']['spalten']];
    foreach ($l['abschnitte'] as $a) if (($a['art'] ?? '') === 'gruppen') $spalten[] = (int)($a['spalten'] ?? 0);
    if (max($spalten) > $max) throw new InvalidArgumentException("Im Hochformat sind höchstens $max Spalten möglich – bitte weniger Spalten oder das Querformat wählen.");
}
function design_groesse_pruefen(array $x): void
{
    if (strlen((string)json_encode($x, JSON_UNESCAPED_UNICODE)) > DESIGN_JSON_MAX) throw new InvalidArgumentException('Das Design ist zu umfangreich – bitte Texte oder Abschnitte kürzen.');
}

/* ---------- Zusammenführen (nur hier; der Editor übernimmt das Ergebnis „wirksam“) ---------- */
function design_basis(string $vorlage): array
{
    $v = $vorlage === '' ? null : design_vorlage($vorlage);
    return $v ? ['raster' => $v['raster'], 'abschnitte' => $v['abschnitte']] : DESIGN_STANDARD;
}
/* Vorlage und Anpassung zusammen; eine gelöschte Vorlage gilt als Standard, die Anpassung bleibt */
function design_zusammen($wahl): array
{
    if (!is_array($wahl)) return DESIGN_STANDARD;
    $basis = design_basis(is_string($wahl['vorlage'] ?? null) ? $wahl['vorlage'] : '');
    $an = is_array($wahl['anpassung'] ?? null) ? $wahl['anpassung'] : [];
    return ['raster' => (is_array($an['raster'] ?? null) ? $an['raster'] : []) + $basis['raster'],
            'abschnitte' => is_array($an['abschnitte'] ?? null) ? $an['abschnitte'] : $basis['abschnitte']];
}
/* Wirksames Layout – null: Standard. Im Hochformat höchstens drei Spalten, auch wenn eine spätere Änderung der Vorlage das Format
   wechselt, während eine Anpassung vier Spalten festhält. */
function design_wirksam($wahl): ?array
{
    $l = design_zusammen($wahl);
    $max = DESIGN_SPALTEN_MAX[$l['raster']['format']] ?? 4;
    $l['raster']['spalten'] = min((int)$l['raster']['spalten'], $max);
    foreach ($l['abschnitte'] as $i => $a) if (($a['art'] ?? '') === 'gruppen' && isset($a['spalten'])) $l['abschnitte'][$i]['spalten'] = min((int)$a['spalten'], $max);
    return $l == DESIGN_STANDARD ? null : $l;
}
/* Design am Angebot prüfen: null = Standard ohne Anpassung. Die Anpassung behält nur, was von der Vorlage abweicht. */
function design_wahl_clean($v): ?array
{
    if ($v === null) return null;
    if (!is_array($v)) throw new InvalidArgumentException('Ungültiges Design.');
    $vid = $v['vorlage'] ?? '';
    if (!is_string($vid)) throw new InvalidArgumentException('Ungültige Vorlage.');
    if ($vid !== '' && !design_vorlage($vid)) throw new InvalidArgumentException('Diese Vorlage gibt es nicht (mehr). Bitte neu laden.');
    $an = $v['anpassung'] ?? null;
    if ($an !== null && !is_array($an)) throw new InvalidArgumentException('Ungültige Anpassung.');
    $basis = design_basis($vid);
    $anpassung = [];
    $raster = array_filter(design_raster_clean($an['raster'] ?? null, true), fn($x, $k) => $basis['raster'][$k] !== $x, ARRAY_FILTER_USE_BOTH);
    if ($raster) $anpassung['raster'] = $raster;
    if (($an['abschnitte'] ?? null) !== null) {
        $ab = design_abschnitte_clean($an['abschnitte']);
        if ($ab !== $basis['abschnitte']) $anpassung['abschnitte'] = $ab;
    }
    design_groesse_pruefen($anpassung);
    if ($vid === '' && !$anpassung) return null;
    $wahl = ['vorlage' => $vid] + ($anpassung ? ['anpassung' => $anpassung] : []);
    design_layout_pruefen(design_zusammen($wahl));
    return $wahl;
}

/* ---------- Schnappschuss (Veröffentlichen) ---------- */
/* Layout der Wahl für ein Angebot mit diesen Gruppen ([{name, section}], aufgelöst): nur bekannte Arten, in Gruppen-Abschnitten nur
   Bereiche und Gruppen des Angebots (Schreibweise wie plAbschnitte: ohne Groß-/Kleinschreibung). Ein Abschnitt, von dem nichts im
   Angebot vorkommt, entfällt – ein leerer Inhalt hieße „alle übrigen Gruppen“. null: Standard. */
function design_fuer(array $gruppen, $wahl): ?array
{
    $w = design_wirksam($wahl);
    if (!$w) return null;
    $key = fn(string $typ, $name) => $typ . "\x01" . mb_strtolower(trim((string)$name));
    $da = [];
    foreach ($gruppen as $g) { $da[$key('gruppe', $g['name'] ?? '')] = true; if (($g['section'] ?? '') !== '') $da[$key('bereich', $g['section'])] = true; }
    $ab = [];
    foreach ($w['abschnitte'] as $a) {
        if (!isset(DESIGN_ARTEN[$a['art'] ?? ''])) continue;
        if ($a['art'] === 'gruppen' && $a['inhalt']) {
            $a['inhalt'] = array_values(array_filter($a['inhalt'], fn($r) => isset($da[isset($r['bereich']) ? $key('bereich', $r['bereich']) : $key('gruppe', $r['gruppe'] ?? '')])));
            if (!$a['inhalt']) continue;
        }
        $ab[] = $a;
    }
    $l = ['raster' => $w['raster'], 'abschnitte' => $ab];
    return $l == DESIGN_STANDARD ? null : $l;
}
/* Schnappschüsse aller Angebote für ein Modell, das gerade veröffentlicht wird: {Angebots-ID: Layout}, nur Angebote mit Design */
function design_staende(array $model): array
{
    $out = [];
    foreach (array_merge([offer_def(OFFER_STD)], offers_load()['offers']) as $def) {
        if (!design_wirksam($def['design'] ?? null)) continue;
        if ($l = design_fuer(offer_resolve($model, $def, false)['groups'], $def['design'])) $out[(string)$def['id']] = $l;
    }
    return $out;
}
/* Gespeichertes, noch nicht veröffentlichtes Design je Angebot – Zeilen der Änderungsliste vor dem Veröffentlichen
   (angebot_aenderungen, Modul Versand). Verglichen wird mit den Gruppen des veröffentlichten Stands. */
function design_aenderungen(array $pub): array
{
    $alt = is_array($pub['meta']['design'] ?? null) ? $pub['meta']['design'] : [];
    $z = [];
    foreach (array_merge([offer_def(OFFER_STD)], offers_load()['offers']) as $def) {
        $oid = (string)$def['id'];
        $war = is_array($alt[$oid] ?? null) ? $alt[$oid] : null;
        if (!$war && !design_wirksam($def['design'] ?? null)) continue;
        $neu = design_fuer(offer_resolve($pub, $def, false)['groups'], $def['design'] ?? null);
        if ($neu == $war) continue;
        $von = design_kurz($war); $nach = design_kurz($neu);
        $z[] = ['art' => 'design', 'angebot' => $oid, 'code' => '', 'name' => 'Design', 'von' => $von, 'nach' => $nach === $von ? $nach . ', Abschnitte geändert' : $nach,
                'zusatz' => design_text_wahl($def['design'] ?? null)];
    }
    return $z;
}
/* Namen der Angebote, deren Schnappschuss sich zwischen zwei veröffentlichten Ständen unterscheidet (Protokoll) */
function design_geaendert(?array $prev, array $model): array
{
    $alt = is_array($prev['meta']['design'] ?? null) ? $prev['meta']['design'] : [];
    $neu = is_array($model['meta']['design'] ?? null) ? $model['meta']['design'] : [];
    $n = [];
    foreach (array_unique(array_merge(array_keys($alt), array_keys($neu))) as $oid) {
        if (($alt[$oid] ?? null) != ($neu[$oid] ?? null)) $n[] = (string)(offer_def((string)$oid)['name'] ?? $oid);
    }
    return $n;
}
function design_kurz(?array $l): string
{
    if (!$l) return 'Standard';
    $s = (int)$l['raster']['spalten']; $n = count($l['abschnitte']);
    return $s . ($s === 1 ? ' Spalte' : ' Spalten') . ', ' . ($l['raster']['format'] === 'hoch' ? 'hoch' : 'quer') . ', ' . ($n === 1 ? '1 Abschnitt' : "$n Abschnitte");
}
/* Einzelangebot: Layout der Wahl mit den Namen dieses Angebots (eine Gruppe mit dem Titel, wie einzel_model) */
function design_einzel(array $e): ?array
{
    return design_fuer([['name' => einzel_titel($e), 'section' => '']], $e['design'] ?? null);
}
/* Freigabe bzw. Speichern eines freigegebenen Einzelangebots: Schnappschuss für den Kunden (einzel_status_setzen, einzel_speichern) */
function design_einzel_freigeben(array $e): array
{
    unset($e['designFreigegeben']);
    $l = design_einzel($e);
    return $l ? $e + ['designFreigegeben' => $l] : $e;
}

/* ---------- Fenster „Design“ und Aktionen ---------- */
/* Vorlage-Kennung → Angebote, die sie nutzen. Einzelangebote mit Nummer nur mit einzelangebote.sehen, sonst nur ihre Anzahl. */
function design_nutzung(array $me): array
{
    $o = offers_load();
    $n = []; $einzel = [];
    $vid = fn($w) => is_array($w) && is_string($w['vorlage'] ?? null) ? $w['vorlage'] : '';
    if (($v = $vid($o['stdDesign'] ?? null)) !== '') $n[$v][] = 'Wochenangebot';
    foreach ($o['offers'] as $x) if (($v = $vid($x['design'] ?? null)) !== '') $n[$v][] = (string)$x['name'];
    $mitNr = may($me, 'einzelangebote.sehen');
    foreach (einzel_load()['list'] as $e) {
        if (($v = $vid($e['design'] ?? null)) === '') continue;
        if ($mitNr) $n[$v][] = 'Einzelangebot ' . $e['nr']; else $einzel[$v] = ($einzel[$v] ?? 0) + 1;
    }
    foreach ($einzel as $v => $k) $n[$v][] = $k === 1 ? '1 Einzelangebot' : "$k Einzelangebote";
    return $n;
}
function design_text_wahl(?array $wahl): string
{
    $v = $wahl && is_string($wahl['vorlage'] ?? null) && $wahl['vorlage'] !== '' ? design_vorlage($wahl['vorlage']) : null;
    return ($v ? 'Vorlage „' . $v['name'] . '“' : 'Standard') . (!empty($wahl['anpassung']) ? ', angepasst' : '');
}
/* Design eines Angebots für das Fenster: Wahl, wirksames Layout (der Editor rechnet nicht selbst) und ob Kunden es schon sehen –
   offen: die gespeicherte Wahl weicht vom veröffentlichten Schnappschuss ab; Einzelangebote zusätzlich freigegeben */
function design_angebot(string $oid): array
{
    if (strncmp($oid, 'e-', 2) === 0) {
        $e = einzel_von_kennung($oid);
        if (!$e) fail('Einzelangebot nicht gefunden.', 404);
        $wahl = $e['design'] ?? null;
        return ['wahl' => $wahl, 'wirksam' => design_wirksam($wahl) ?? DESIGN_STANDARD, 'freigegeben' => ($e['status'] ?? '') === 'freigegeben',
                'offen' => design_einzel($e) != (is_array($e['designFreigegeben'] ?? null) ? $e['designFreigegeben'] : null)];
    }
    $def = offer_def($oid);
    if (!$def) fail('Unbekanntes Angebot.', 404);
    $wahl = $def['design'] ?? null;
    $pub = store_read('angebot');
    $r = $pub ? offer_resolve($pub, $def, false) : null;
    return ['wahl' => $wahl, 'wirksam' => design_wirksam($wahl) ?? DESIGN_STANDARD,
            'offen' => $r ? design_fuer($r['groups'], $wahl) != ($r['meta']['design'] ?? null) : design_wirksam($wahl) !== null];
}
/* Daten für das Fenster „Design“: Vorlagen mit Nutzung und – mit $oid – das Design dieses Angebots */
function design_liste(array $me, string $oid): array
{
    $nutzung = design_nutzung($me);
    $d = design_load();
    $out = ['rev' => $d['rev'], 'standard' => DESIGN_STANDARD, 'darfVorlagen' => may($me, 'angebote.verwalten'),
            'vorlagen' => array_map(fn($v) => ['id' => $v['id'], 'name' => $v['name'], 'raster' => $v['raster'], 'abschnitte' => $v['abschnitte'],
                                              'genutzt' => $nutzung[$v['id']] ?? []], $d['vorlagen'])];
    if ($oid === '') return $out;
    $einzel = strncmp($oid, 'e-', 2) === 0;
    if ($einzel && !may($me, 'einzelangebote.sehen')) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
    return $out + design_angebot($oid) + ['darfWahl' => may($me, $einzel ? 'einzelangebote.bearbeiten' : 'angebot.bearbeiten')];
}

/* Vorlage anlegen ($b ohne id) oder ändern: {rev, id?, name, raster, abschnitte}; Recht prüft die Aktion. Wirkt auf ein Angebot
   erst mit dessen nächster Veröffentlichung. */
function design_vorlage_speichern(array $me, array $b): array
{
    $name = s($b['name'] ?? null, 60, false);
    if ($name === null || mb_strlen($name) < 2) throw new InvalidArgumentException('Bitte einen Namen für die Vorlage angeben (mindestens 2 Zeichen).');
    if (mb_strtolower($name) === 'standard') throw new InvalidArgumentException('„Standard“ ist das eingebaute Design – bitte einen anderen Namen wählen.');
    $raster = design_raster_clean($b['raster'] ?? null, false);
    $abschnitte = design_abschnitte_clean($b['abschnitte'] ?? []);
    design_layout_pruefen(['raster' => $raster, 'abschnitte' => $abschnitte]);
    design_groesse_pruefen(['raster' => $raster, 'abschnitte' => $abschnitte]);
    $id = is_string($b['id'] ?? null) ? $b['id'] : '';
    [$row, $d, $neu] = with_lock('angebot-designs', function () use ($me, $b, $name, $raster, $abschnitte, $id) {
        $d = design_load();
        if ((int)($b['rev'] ?? -1) !== $d['rev']) fail('Die Vorlagen wurden inzwischen geändert. Bitte neu laden.', 409);
        $idx = $id === '' ? null : design_index($d, $id);
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
        . count($abschnitte) . ' Abschnitte; wirkt mit der nächsten Veröffentlichung)');
    return ['rev' => $d['rev'], 'id' => $row['id']];
}
/* Vorlage löschen: {rev, id} – nicht, solange ein Angebot sie nutzt (409 mit den Namen). Unter den Sperren der Angebote und
   Einzelangebote, damit niemand die Vorlage gleichzeitig wählt (design_setzen prüft unter derselben Sperre). Schnappschüsse
   veröffentlichter Stände bleiben unberührt. */
function design_vorlage_loeschen(array $me, array $b): array
{
    $id = is_string($b['id'] ?? null) ? $b['id'] : '';
    [$name, $d] = with_lock('angebote', fn() => with_lock('einzelangebote', fn() => with_lock('angebot-designs', function () use ($me, $b, $id) {
        $d = design_load();
        if ((int)($b['rev'] ?? -1) !== $d['rev']) fail('Die Vorlagen wurden inzwischen geändert. Bitte neu laden.', 409);
        $idx = design_index($d, $id);
        if ($idx === null) fail('Diese Vorlage gibt es nicht (mehr).', 404);
        $name = (string)$d['vorlagen'][$idx]['name'];
        $wer = design_nutzung($me)[$id] ?? [];
        if ($wer) fail("Die Vorlage „{$name}“ wird noch genutzt: " . implode(', ', array_slice($wer, 0, 6)) . (count($wer) > 6 ? ' und ' . (count($wer) - 6) . ' weitere' : '')
            . '. Bitte dort zuerst ein anderes Design wählen.', 409);
        array_splice($d['vorlagen'], $idx, 1);
        $d['rev']++;
        store_write('angebot-designs', $d);
        return [$name, $d];
    })));
    audit('offers', 'Design-Vorlage „' . $name . '“ gelöscht');
    return ['rev' => $d['rev']];
}
/* Design eines Angebots wählen ($design null = Standard): Kunden- und Sonderangebote, Wochenangebot („std“), Einzelangebote („e-…“).
   Speichert nur die Wahl – Kunden sehen sie erst nach dem Veröffentlichen (Einzelangebote: Freigabe bzw. Speichern des freigegebenen
   Einzelangebots). Recht prüft die Aktion (angebot.bearbeiten bzw. einzelangebote.bearbeiten). */
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
    audit('offers', 'Design von „' . $name . '“ gespeichert: ' . design_text_wahl($wahl) . ' (wirkt mit der nächsten Veröffentlichung)');
    return design_angebot($oid);
}
