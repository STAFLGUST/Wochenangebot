<?php
declare(strict_types=1);
/* Auswertung: Anmeldeorte der Kunden (ungefährer Ort aus der IP-Adresse, ort.php).
   Gespeichert wird nur der ermittelte Ort, Zeitpunkt, Kunde, Gerätetyp und Art der Anmeldung – nicht die IP-Adresse.
   Einträge werden nach ANMELDEORT_TAGE Tagen automatisch gelöscht, beim Löschen eines Kunden sofort. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const ANMELDEORT_TAGE = 90;
const ANMELDEORT_MAX = 20000;

function anmeldeorte_prune(array $list): array
{
    $grenze = gmdate('Y-m-d\TH:i:s\Z', time() - ANMELDEORT_TAGE * 86400);
    $list = array_values(array_filter($list, function ($e) use ($grenze) { return is_array($e) && (string)($e['t'] ?? '') >= $grenze; }));
    return count($list) > ANMELDEORT_MAX ? array_slice($list, -ANMELDEORT_MAX) : $list;
}
function anmeldeorte_load(): array
{
    return anmeldeorte_prune((store_read('anmeldeorte') ?? [])['entries'] ?? []);
}
function geraet_typ(string $ua): string
{
    if (preg_match('/iPad|Tablet|Kindle|Silk|PlayBook|Android(?!.*Mobile)/i', $ua)) return 'tablet';
    if (preg_match('/Mobi|iPhone|iPod|Android|Windows Phone/i', $ua)) return 'mobil';
    return 'desktop';
}
/* Anmeldung eines Kunden festhalten; Fehler dürfen die Anmeldung nie verhindern */
function anmeldeort_record(array $c, string $via = 'passwort'): void
{
    try {
        $ip = client_ip();
        $o = ort_lookup($ip);
        $e = ['t' => now(), 'kid' => (string)$c['id'], 'via' => $via, 'dev' => geraet_typ((string)($_SERVER['HTTP_USER_AGENT'] ?? ''))];
        if ($o) $e += ['city' => $o['city'], 'region' => $o['region'], 'cc' => $o['cc'], 'lat' => $o['lat'], 'lon' => $o['lon']];
        elseif ($cc = geo_country($ip)) $e['cc'] = $cc;
        with_lock('anmeldeorte', function () use ($e) {
            $list = anmeldeorte_load();
            $list[] = $e;
            store_write('anmeldeorte', ['entries' => anmeldeorte_prune($list)]);
        });
    } catch (Throwable $ex) {
        error_log('[wochenangebot] anmeldeort: ' . $ex->getMessage());
    }
}
function anmeldeorte_remove_customer(string $kid): void
{
    with_lock('anmeldeorte', function () use ($kid) {
        $list = anmeldeorte_load();
        $n = count($list);
        $list = array_values(array_filter($list, function ($e) use ($kid) { return ($e['kid'] ?? '') !== $kid; }));
        if (count($list) !== $n) store_write('anmeldeorte', ['entries' => $list]);
    });
}
