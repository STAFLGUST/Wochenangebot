<?php
declare(strict_types=1);
/* CRM · Einzelangebot beim Kunden (Auftrag des Inhabers 01.11.2026): im Kunden-Pop-up Einzelangebote des Kunden ansehen, anlegen,
   bearbeiten, im Portal freigeben, als PDF ansehen und per E-Mail senden – wie in der Angebotsübersicht des Eingabebereichs.
   Daten und Regeln gehören dem Angebot (Dokument „einzelangebote“, lib/einzelangebote.php); das CRM ruft nur dessen Funktionen
   auf (regeln/datenverantwortung.toml). Rechte wie im Eingabebereich: einzelangebote.sehen bzw. .bearbeiten, dazu crm.sehen
   (GR-103). Der Kunde kommt immer aus dem Schlüssel des Pop-ups (nie aus dem Browser); fremde Einzelangebote gibt es hier nicht. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Recht prüfen: einzelangebote.<sehen|bearbeiten> und CRM ansehen */
function crm_einzel_recht(string $art, bool $write = false): array
{
    $me = require_perm($art === 'bearbeiten' ? 'einzelangebote.bearbeiten' : 'einzelangebote.sehen', $write);
    if (!may($me, 'crm.sehen')) fail('Dafür fehlt Ihnen die Berechtigung „CRM ansehen“.', 403);
    return $me;
}
/* Kunde der Verwaltung zum Schlüssel (Interessenten haben keine Einzelangebote) */
function crm_einzel_kunde($key): array
{
    $k = crm_key_param($key);
    $c = crm_stammkunden()[$k] ?? null;
    if (!$c) fail('Einzelangebote gibt es nur für Kunden aus den Stammdaten.', 404);
    return $c;
}
/* Einzelangebot dieses Kunden (sonst 404 – auch wenn es einem anderen Kunden gehört) */
function crm_einzel_von(array $c, $id): array
{
    $e = is_string($id) && $id !== '' ? einzel_holen($id) : null;
    if ($e === null || ($e['kid'] ?? '') !== (string)$c['id']) fail('Einzelangebot nicht gefunden.', 404);
    return $e;
}
/* Artikel für die Suche: Nummer, Name, Fleischart, Wochenpreis, im Angebot, Bestand (nur mit bestand.sehen) – ohne Partien und EK */
function crm_einzel_artikel(array $me): array
{
    $a = einzel_artikel(may($me, 'bestand.sehen'), false);
    unset($a['ek']);
    $a['articles'] = array_map(fn($x) => array_intersect_key($x, array_flip(['code', 'name', 'category', 'vk', 'stdPrice', 'inOffer', 'kg', 'totalKg', 'mhd'])), $a['articles']);
    return $a;
}
