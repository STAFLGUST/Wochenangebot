<?php
declare(strict_types=1);
/* Importvertrag des Moduls Bestand – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md).
   Die Bestandsliste aus WinAB (.xls/.xlsx) liest der Leser des Moduls im Browser (app/assets/stock-core.js). Hier prüft
   der Server die gelesenen Partien (clean_stock, clean_incoming in lib/bestand.php), vergleicht sie mit dem gespeicherten
   Bestand (Vorschau) und ersetzt ihn (Übernahme, mit Protokoll). Die bisherige Aktion stock_import nutzt bestand_speichern().
   Wird von api/index.php geladen; schreibt nur das eigene Dokument „bestand“. Einkaufspreise erscheinen nie in der Vorschau. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

function import_arten_bestand(): array
{
    return [
        'bestand' => ['name' => 'Bestand', 'beschreibung' => 'Bestandsliste aus WinAB („Partieliste … verfügbar“) mit Art.-Nr., Bezeichnung, Status, MHD und netto. Ersetzt den bisherigen Bestand.',
            'recht' => ['bestand.importieren'], 'aktion' => 'stock_import', 'dateien' => ['xls', 'xlsx'], 'kodierung' => 'Excel-Datei (.xls oder .xlsx)',
            'ansicht' => 'stock', 'vorschau' => 'bestand_import_vorschau', 'uebernahme' => 'bestand_import_uebernehmen',
            'optionen' => [['id' => 'datum', 'typ' => 'datum', 'label' => 'Bestandsdatum', 'pflicht' => true]]],
    ];
}

/* Bestand speichern und protokollieren (Aktion stock_import und Importzentrale) */
function bestand_speichern(?string $date, string $source, array $articles, array $incoming, array $me): array
{
    $total = 0.0;
    foreach ($articles as $a) $total += $a['kg'];
    $st = ['date' => $date, 'source' => $source, 'importedAt' => now(), 'importedBy' => $me['name'], 'articles' => $articles, 'incoming' => $incoming];
    store_write('bestand', $st);
    audit('stock', 'Bestand übernommen: ' . ($st['source'] ?: 'Datei') . ($date ? ' – Stand ' . date('d.m.Y', strtotime($date)) : '') . ', ' . count($articles) . ' Artikel, ' . number_format($total, 2, ',', '.') . ' kg eingelagert, ' . count($incoming) . ' erwartete Zugänge');
    return $st;
}

/* Gelesene Bestandsliste prüfen: Partien, erwartete Zugänge, Bestandsdatum (Pflicht in der Importzentrale) */
function bestand_import_pruefen(array $e): array
{
    $incoming = clean_incoming($e['incoming'] ?? []);
    $articles = clean_stock($e, count($incoming) > 0);
    $date = clean_date($e['optionen']['datum'] ?? null);
    if ($date === null) throw new InvalidArgumentException('Bitte ein gültiges Bestandsdatum angeben.');
    return [$date, $articles, $incoming];
}

function bestand_import_vorschau(array $e, array $me): array
{
    [$date, $articles, $incoming] = bestand_import_pruefen($e);
    $cur = store_read('bestand');
    $kg = function (float $v): string { return number_format($v, 2, ',', '.') . ' kg'; };
    $tag = function (?string $d): string { return $d ? date('d.m.Y', strtotime($d)) : 'ohne MHD'; };
    $alt = [];
    foreach (($cur['articles'] ?? []) as $a) $alt[code_key((string)$a['code'])] = $a;
    $z = []; $n = ['neu' => 0, 'geaendert' => 0, 'entfaellt' => 0, 'unveraendert' => 0, 'fehler' => 0];
    foreach ($articles as $a) {
        $k = code_key($a['code']);
        $o = $alt[$k] ?? null;
        unset($alt[$k]);
        if (!$o) { $n['neu']++; $z[] = ['art' => 'neu', 'zeile' => null, 'schluessel' => $a['code'], 'name' => $a['name'], 'text' => $kg($a['kg']) . ' · MHD ' . $tag($a['mhd'])]; continue; }
        $diff = [];
        if (abs((float)$o['kg'] - $a['kg']) >= 0.0005) $diff[] = 'Menge: ' . $kg((float)$o['kg']) . ' → ' . $kg($a['kg']);
        if (($o['mhd'] ?? null) !== $a['mhd']) $diff[] = 'Kürzestes MHD: ' . $tag($o['mhd'] ?? null) . ' → ' . $tag($a['mhd']);
        if (!$diff) { $n['unveraendert']++; continue; }
        $n['geaendert']++;
        $z[] = ['art' => 'geaendert', 'zeile' => null, 'schluessel' => $a['code'], 'name' => $a['name'], 'text' => implode('; ', $diff)];
    }
    foreach ($alt as $o) { $n['entfaellt']++; $z[] = ['art' => 'entfaellt', 'zeile' => null, 'schluessel' => (string)$o['code'], 'name' => (string)($o['name'] ?? ''), 'text' => 'nicht mehr im Bestand (bisher ' . $kg((float)$o['kg']) . ')']; }
    $total = 0.0; foreach ($articles as $a) $total += $a['kg'];
    $h = [['stufe' => 'info', 'text' => count($articles) . ' Artikel mit ' . $kg($total) . ' eingelagert, ' . count($incoming) . ' erwartete Zugänge (Status „erfasst“, separat, nicht im Bestand).']];
    if ($cur) $h[] = ['stufe' => 'info', 'text' => 'Ersetzt den bisherigen Bestand vom ' . ($cur['date'] ? date('d.m.Y', strtotime($cur['date'])) : '?') . ' (' . count($cur['articles'] ?? []) . ' Artikel).'];
    if ($date > date('Y-m-d')) $h[] = ['stufe' => 'warn', 'text' => 'Das Bestandsdatum liegt in der Zukunft.'];
    $h[] = ['stufe' => 'info', 'text' => 'Mengen und MHD sind nur im Eingabebereich sichtbar, nicht auf der öffentlichen Angebotsseite.'];
    return ['zahlen' => $n, 'zeilen' => $z, 'hinweise' => $h, 'stand' => bestand_stand($cur)];
}

/* Kennung des gespeicherten Bestands für die Übernahme (ändert sich mit jedem Speichern, auch innerhalb einer Sekunde) */
function bestand_stand(?array $st): string { return $st ? substr(hash('sha256', json_encode($st)), 0, 20) : ''; }

function bestand_import_uebernehmen(array $e, array $me): array
{
    $v = bestand_import_vorschau($e, $me);
    [$date, $articles, $incoming] = bestand_import_pruefen($e);
    $source = s($e['quelle'] ?? '', 200) ?? '';
    with_lock('bestand', function () use ($e, $date, $source, $articles, $incoming, $me) {
        if (bestand_stand(store_read('bestand')) !== (string)($e['stand'] ?? '')) fail('Der Bestand wurde inzwischen an anderer Stelle übernommen. Bitte die Vorschau neu laden.', 409);
        bestand_speichern($date, $source, $articles, $incoming, $me);
    });
    return $v;
}
