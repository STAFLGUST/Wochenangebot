<?php
declare(strict_types=1);
/* Importvertrag des Moduls Angebot – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md).
   - Preisverlauf: frühere Angebotslisten (.xlsx) als Wochen im Preisverlauf. Gelesen werden sie vom Angebotsleser im
     Browser (offer-core.js, parseOfferWorkbook); hier prüft der Server die Wochen (clean_history_items), vergleicht sie mit
     den gespeicherten Wochen (Vorschau) und speichert sie (Übernahme, Protokoll je Woche). Die bisherige Aktion
     history_import nutzt preisverlauf_woche_speichern().
   - Wochenangebot (Excel) und Artikelpreise (CSV) ändern den Entwurf: Vorschau, Prüfung und „Rückgängig“ gibt es nur im
     Angebotseditor, veröffentlicht wird von dort. Die Importzentrale führt sie deshalb nur auf und öffnet den Editor
     (Ablauf „editor“) – kein zweiter Weg, der den Entwurf ersetzt.
   Wird von api/index.php geladen; schreibt nur eigene Dokumente (historie/*, historie_geloescht). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

function import_arten_angebot(): array
{
    return [
        'preisverlauf' => ['name' => 'Preisverlauf (frühere Angebotslisten)', 'beschreibung' => 'Excel-Angebotslisten früherer Wochen; jede Datei wird eine Woche im Preisverlauf. Das aktuelle Angebot bleibt unverändert.',
            'recht' => ['preisverlauf.bearbeiten'], 'aktion' => 'history_import', 'dateien' => ['xlsx', 'xlsm'], 'kodierung' => 'Excel-Arbeitsmappe (.xlsx)', 'mehrere' => true,
            'ansicht' => 'hist', 'vorschau' => 'preisverlauf_import_vorschau', 'uebernahme' => 'preisverlauf_import_uebernehmen'],
        'angebot_excel' => ['name' => 'Wochenangebot (Excel)', 'beschreibung' => 'Excel-Angebotsliste der Woche. Ersetzt den Entwurf; prüfen, anpassen und veröffentlichen im Angebotseditor.',
            'recht' => ['angebot.bearbeiten'], 'aktion' => 'save_draft', 'dateien' => ['xlsx', 'xlsm'], 'kodierung' => 'Excel-Arbeitsmappe (.xlsx)', 'ablauf' => 'editor', 'ansicht' => 'edit'],
        'angebot_preise' => ['name' => 'Artikelpreise (CSV)', 'beschreibung' => 'Artikelpreise der Warenwirtschaft in den Entwurf: ohne Kundengruppe ins Wochenangebot, mit Kundengruppe ins Angebot der Gruppe. Unter Stammdaten → Angebote.',
            'recht' => ['angebot.bearbeiten', 'angebote.verwalten'], 'aktion' => 'save_draft', 'dateien' => ['csv'], 'kodierung' => 'CSV, UTF-8 oder Windows-1252, Semikolon getrennt', 'ablauf' => 'editor', 'ansicht' => 'angebote'],
    ];
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
        if (!is_int($week) || $week < 1 || $week > 53 || !is_int($year) || $year < 2000 || $year > 2100) {
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
