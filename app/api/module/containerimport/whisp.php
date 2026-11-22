<?php
declare(strict_types=1);
/* Container-Import · EUDR: Abfrage von Whisp (FAO, https://whisp.openforis.org) für die eigene Gegenprüfung eines Betriebs.
   Der Server schickt nur den Umriss (keine Namen, keine Kennungen) und holt das Ergebnis später mit der Vorgangsnummer ab –
   die Auswertung dauert bei Whisp Sekunden bis Minuten. Der Zugangsschlüssel steht als WHISP_API_KEY in .env (ein Jahr
   gültig, Kontoseite von Whisp) und verlässt den Server nur in der Kopfzeile an Whisp; ohne ihn ist die Abfrage aus.
   Nichts wird gespeichert: die Oberfläche zeigt das Ergebnis als Vorschlag für das Formular der Gegenprüfung.
   Schnittstelle (Stand 19.11.2026, /api/openapi.json): POST /submit/geojson → 202 mit data.token oder 200 mit Ergebnis;
   GET /status/{token} → 202 in Arbeit, 200 Ergebnis (GeoJSON, Eigenschaften je Fläche in properties). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const WHISP_URL = 'https://whisp.openforis.org/api';
const WHISP_TOKEN = '/^[A-Za-z0-9_-]{6,128}$/';   // Vorgangsnummer – wird Teil der Adresse, deshalb streng geprüft
const WHISP_MAX_FELDER = 300;     // höchstens so viele Eigenschaften reicht der Server an die Oberfläche weiter
const WHISP_ZEITLIMIT = 20;       // Sekunden Gesamtfrist je Anfrage (Verbinden, Kopfzeilen, Antwort)
const WHISP_MAX_BYTE = 8 * 1024 * 1024;

function whisp_schluessel(): string { return trim((string)(getenv('WHISP_API_KEY') ?: '')); }
function whisp_eingerichtet(): bool { return whisp_schluessel() !== ''; }

/* Eine Anfrage an Whisp: [Status, JSON|null]; Status 0 = nicht erreichbar. Keine Weiterleitungen und eine Gesamtfrist
   über den ganzen Abruf (abruf_http in lib/abruf.php): eine tröpfelnde Gegenstelle hielte sonst einen Webserver-Prozess beliebig lange fest.
   Eine abgebrochene oder zu große Antwort zählt wie „nicht erreichbar“ – ein halbes JSON wird nie ausgewertet. */
function whisp_http(string $methode, string $pfad, ?array $inhalt = null): array
{
    $kopf = ['User-Agent: STAFL-Plattform', 'x-api-key: ' . whisp_schluessel(), 'Accept: application/json'];
    if ($inhalt !== null) $kopf[] = 'Content-Type: application/json';
    $a = abruf_http((getenv('WA_WHISP_URL') ?: WHISP_URL) . $pfad, $kopf, WHISP_ZEITLIMIT, WHISP_MAX_BYTE, $methode,   // WA_WHISP_URL nur in den Tests
        $inhalt === null ? null : json_encode($inhalt, JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
    if ($a['fehler'] !== '') return [0, null];
    $json = $a['roh'] !== '' ? json_decode($a['roh'], true) : null;
    return [$a['status'], is_array($json) ? $json : null];
}

/* Antwort von Whisp für die Oberfläche: ['fertig' => true, 'ergebnis' => …] oder ['fertig' => false, 'token', 'prozent'].
   Alles andere endet mit einer verständlichen Meldung (fail). */
function whisp_antwort(int $status, ?array $json): array
{
    $code = is_string($json['code'] ?? null) && preg_match('/^[a-z_]{1,60}$/', $json['code']) ? $json['code'] : '';   // fremder Text: nur das erwartete Muster
    if ($status === 200 && $code === 'analysis_completed') return ['fertig' => true, 'ergebnis' => whisp_ergebnis($json['data'] ?? null)];
    if ($status === 202) {
        $token = $json['data']['token'] ?? '';
        if (!is_string($token) || !preg_match(WHISP_TOKEN, $token)) fail('Whisp hat unerwartet geantwortet. Bitte später erneut versuchen.', 502);
        return ['fertig' => false, 'token' => $token, 'prozent' => is_numeric($json['data']['percent'] ?? null) ? (int)round((float)$json['data']['percent']) : null];
    }
    if ($status === 0) fail('Whisp ist gerade nicht erreichbar. Bitte später erneut versuchen.', 502);
    error_log('[containerimport] Whisp antwortet mit ' . $status . ' ' . $code);
    fail(match (true) {
        $status === 401 => 'Whisp lehnt den Zugangsschlüssel ab (abgelaufen oder ersetzt?). Bitte den Administrator den Schlüssel in .env erneuern lassen.',
        $status === 429 => 'Whisp nimmt gerade keine weiteren Abfragen an. Bitte in einigen Minuten erneut versuchen.',
        $status === 404 => 'Whisp kennt diese Abfrage nicht mehr. Bitte neu starten.',
        $status === 408 || $code === 'analysis_timeout' => 'Whisp hat die Auswertung nach Zeitüberschreitung abgebrochen. Bitte erneut versuchen.',
        $code === 'validation_plot_too_large' => 'Die Fläche ist für Whisp zu groß (Grenze von Whisp: 100.000 ha, Stand 11/2026).',
        str_starts_with($code, 'validation_') => 'Whisp nimmt diesen Umriss nicht an (' . $code . ').',
        default => 'Whisp meldet einen Fehler. Bitte später erneut versuchen.',
    }, $status === 401 ? 503 : 502);
}

/* Abfrage für einen Umriss starten – die Funktion bekommt nur die Geometrie, Namen kann sie nicht versenden */
function whisp_starten(array $geometrie): array
{
    return whisp_antwort(...whisp_http('POST', '/submit/geojson', [
        'type' => 'FeatureCollection',
        'features' => [['type' => 'Feature', 'properties' => new stdClass(), 'geometry' => $geometrie]],
        'analysisOptions' => ['async' => true, 'unitType' => 'ha'],
    ]));
}
/* Stand einer gestarteten Abfrage */
function whisp_stand(string $token): array
{
    if (!preg_match(WHISP_TOKEN, $token)) fail('Ungültige Abfrage.', 422);
    return whisp_antwort(...whisp_http('GET', '/status/' . $token));
}

/* Eigenschaften der ersten Fläche aus dem Ergebnis – nur einfache Werte mit harmlosen Namen (die Oberfläche maskiert sie
   zusätzlich); der zurückgelieferte Umriss wird nicht weitergereicht. */
function whisp_ergebnis($daten): array
{
    $roh = is_array($daten) ? ($daten['features'][0]['properties'] ?? null) : null;
    if (!is_array($roh)) fail('Whisp hat kein Ergebnis für diese Fläche geliefert.', 502);
    $felder = [];
    foreach ($roh as $name => $wert) {
        if (count($felder) >= WHISP_MAX_FELDER) break;
        if (!is_string($name) || !preg_match('/^[A-Za-z0-9_.-]{1,80}$/', $name)) continue;
        if (is_bool($wert) || is_int($wert) || is_float($wert)) $felder[$name] = $wert;
        elseif (is_string($wert) && strlen($wert) <= 200) $felder[$name] = $wert;
    }
    $meta = is_array($roh['whisp_processing_metadata'] ?? null) ? $roh['whisp_processing_metadata'] : [];
    $version = is_string($meta['whisp_version'] ?? null) && preg_match('/^[A-Za-z0-9._-]{1,40}$/', $meta['whisp_version']) ? $meta['whisp_version'] : '';
    return ['felder' => $felder, 'version' => $version];
}
