<?php
declare(strict_types=1);
/* Fracht: Mindestmenge für frachtfreie Lieferung, Frachtanteil je Staffel (unter X kg → Y € pro Sendung) und der
   Hinweis („Vermerk“) unter dem Angebot. Gespeichert im Dokument „fracht“ (Verwaltung → E-Mail → Fracht und Hinweis).
   Der Frachtanteil eines Bestellwunsches wird nur hier auf dem Server berechnet (Regel 10). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const FRACHT_DEFAULT = [
    'aktiv' => true,
    'staffeln' => [['unter' => 300, 'kosten' => 30.0], ['unter' => 200, 'kosten' => 35.0]],
    'zusatz' => "Telefon Büro Hamburg: 040 - 43 25 88 - 0 · Fax Büro Hamburg: 040 - 43 25 88 - 88\nTelefon Büro Köln: 040 - 43 25 88 - 55 + 57",
];
const FRACHT_MAX_STAFFELN = 5;

function fracht_clean_staffeln($in): array
{
    $out = []; $seen = [];
    foreach (is_array($in) ? $in : [] as $s) {
        if (!is_array($s) || !is_numeric($s['unter'] ?? null) || !is_numeric($s['kosten'] ?? null)) continue;
        $u = (int)round((float)$s['unter']); $k = round((float)$s['kosten'], 2);
        if ($u < 1 || $u > 100000 || $k < 0 || $k > 10000 || isset($seen[$u])) continue;
        $seen[$u] = true;
        $out[] = ['unter' => $u, 'kosten' => $k];
    }
    usort($out, function ($a, $b) { return $b['unter'] <=> $a['unter']; });   // größte Grenze zuerst
    return array_slice($out, 0, FRACHT_MAX_STAFFELN);
}
function fracht_settings(): array
{
    $d = store_read('fracht');
    if (!is_array($d)) return FRACHT_DEFAULT + ['updatedAt' => null, 'updatedBy' => ''];
    return ['aktiv' => !empty($d['aktiv']), 'staffeln' => fracht_clean_staffeln($d['staffeln'] ?? []), 'zusatz' => (string)($d['zusatz'] ?? ''),
            'updatedAt' => $d['updatedAt'] ?? null, 'updatedBy' => (string)($d['updatedBy'] ?? '')];
}
/* frachtfrei ab (kg) oder null */
function fracht_frei(array $s): ?int { return $s['aktiv'] && $s['staffeln'] ? (int)$s['staffeln'][0]['unter'] : null; }
/* Frachtanteil für eine Gesamtmenge: kleinste Grenze, die noch über der Menge liegt */
function fracht_kosten(float $kg, ?array $s = null): array
{
    $s = $s ?? fracht_settings();
    $frei = fracht_frei($s);
    $hit = null;
    if ($frei !== null && $kg > 0) foreach ($s['staffeln'] as $st) if ($kg < $st['unter']) $hit = $st;
    return ['kosten' => $hit ? (float)$hit['kosten'] : 0.0, 'unter' => $hit ? (int)$hit['unter'] : null, 'frei' => $frei];
}
function fracht_eur(float $v): string { return fmod($v, 1.0) == 0.0 ? number_format($v, 0, ',', '.') : number_format($v, 2, ',', '.'); }
/* Vermerk unter dem Angebot (Bildschirm und Druck), Zeile für Zeile */
function fracht_hinweis(?array $s = null): array
{
    $s = $s ?? fracht_settings();
    $frei = fracht_frei($s);
    $l = [$frei !== null
        ? "Die Preise verstehen sich per kg netto, ohne eventuelle Konditionen, frachtfrei geliefert bei einer Mindestbestellmenge von ca. " . number_format($frei, 0, ',', '.') . " kg."
        : 'Die Preise verstehen sich per kg netto, ohne eventuelle Konditionen.'];
    if ($frei !== null) foreach ($s['staffeln'] as $st) $l[] = 'Bei Mengen unter ' . number_format($st['unter'], 0, ',', '.') . ' kg berechnen wir einen Frachtanteil von ' . fracht_eur($st['kosten']) . ' € pro Sendung.';
    foreach (preg_split('/\R/', trim($s['zusatz'])) as $z) if (trim($z) !== '') $l[] = trim($z);
    return $l;
}
function fracht_public(): array
{
    $s = fracht_settings();
    return ['aktiv' => fracht_frei($s) !== null, 'frei' => fracht_frei($s), 'staffeln' => $s['aktiv'] ? $s['staffeln'] : [], 'hinweis' => fracht_hinweis($s)];
}
