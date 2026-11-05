<?php
declare(strict_types=1);
/* Export des Wochenangebots für WinAB (Auftrag des Inhabers 05.11.2026): CSV mit Artikelnummer und Preis.
   - Stand: das veröffentlichte Wochenangebot, aufgelöst wie für Kunden (offer_resolve): ausgeblendete Artikel fehlen,
     Sonderposten mit ihrem Sonderpreis, ausverkaufte Sonderposten fehlen wie auf der Angebotsseite.
   - Je Artikelnummer eine Zeile; steht ein Artikel mehrfach im Angebot (auch mit Zusatzpreisen), gilt der höchste Preis.
     Gleich ist eine Nummer wie überall im Eingabebereich (code_key: Ziffern ohne führende Nullen, sonst Großbuchstaben).
   - Ohne Preis („auf Anfrage“) oder ohne Artikelnummer: nicht in der Datei (gezählt für die Rückmeldung).
   - Format: Kopfzeile „Artikelnummer;Preis“, Semikolon, Preis mit Dezimalkomma ohne Tausenderpunkt (mindestens 2, höchstens
     4 Nachkommastellen), Zeilenende CRLF, ohne BOM (nur ASCII), sortiert nach Artikelnummer.
   Recht angebot.winab_export (ohne Standardrollen), Aktion angebot_winab_export in aktionen/entwurf.php (Protokoll). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Preis für WinAB: 26,1 → „26,10“, 12.345 → „12,345“ */
function winab_preis(float $v): string
{
    $t = number_format($v, 4, ',', '');
    return (string)preg_replace('/(,\d\d)0{1,2}$/', '$1', $t);
}

/* Zeilen [Artikelnummer, Preis] aus einem veröffentlichten Angebotsmodell (höchster Preis je Nummer) und Zählung */
function winab_zeilen(array $pub): array
{
    $beste = [];   // code_key → [Nummer, Preis]
    $ohnePreis = 0; $ohneNummer = 0; $doppelt = 0;
    foreach (offer_resolve($pub, offer_def(OFFER_STD))['items'] as $it) {
        $code = trim((string)($it['code'] ?? ''));
        $preise = [];
        foreach (array_merge([$it['price'] ?? null], is_array($it['altPrices'] ?? null) ? $it['altPrices'] : []) as $p) {
            if (is_array($p) && ($p['status'] ?? '') === 'value' && is_numeric($p['value'] ?? null)) $preise[] = (float)$p['value'];
        }
        if ($code === '') { $ohneNummer++; continue; }
        if (!$preise) { $ohnePreis++; continue; }
        $k = code_key($code);
        $p = max($preise);
        if (isset($beste[$k])) { $doppelt++; if ($p > $beste[$k][1]) $beste[$k][1] = $p; }
        else $beste[$k] = [$code, $p];
    }
    $zeilen = array_values($beste);
    usort($zeilen, function ($a, $b) { return strnatcasecmp($a[0], $b[0]); });
    return ['zeilen' => $zeilen, 'ohnePreis' => $ohnePreis, 'ohneNummer' => $ohneNummer, 'doppelt' => $doppelt];
}

/* Datei für den Download: Name, Inhalt und Zahlen; 422 ohne veröffentlichtes Angebot oder ohne Preise */
function winab_export(): array
{
    $pub = store_read('angebot');
    if (!is_array($pub) || !is_array($pub['items'] ?? null)) fail('Es ist noch kein Wochenangebot veröffentlicht.', 422);
    $r = winab_zeilen($pub);
    if (!$r['zeilen']) fail('Im veröffentlichten Wochenangebot steht kein Artikel mit Preis.', 422);
    $w = (int)($pub['meta']['week'] ?? 0); $y = (int)($pub['meta']['year'] ?? 0);
    $csv = "Artikelnummer;Preis\r\n";
    foreach ($r['zeilen'] as [$code, $preis]) $csv .= $code . ';' . winab_preis($preis) . "\r\n";
    return ['datei' => 'WinAB_Wochenangebot' . ($w && $y ? sprintf('_KW%02d-%04d', $w, $y) : '') . '.csv', 'csv' => $csv,
            'anzahl' => count($r['zeilen']), 'ohnePreis' => $r['ohnePreis'], 'ohneNummer' => $r['ohneNummer'], 'doppelt' => $r['doppelt'],
            'woche' => $w && $y ? "KW $w/$y" : '', 'veroeffentlicht' => $pub['publishedAt'] ?? null];
}
