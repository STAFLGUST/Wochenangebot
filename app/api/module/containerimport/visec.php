<?php
declare(strict_types=1);
/* Container-Import · EUDR: Abfrage von VISEC Carne (https://carne.visec.com.ar) für Container aus Argentinien (Auftrag des
   Inhabers 24.11.2026). VISEC ist die Plattform der argentinischen Rindfleischkette zur EUDR: Jedes Tier (Caravana =
   Ohrmarke) wird dort gegen Entwaldung nach dem 31.12.2020, Schutzgebiete und Legalität geprüft. Über einen DTE
   (Documento de Tránsito Electrónico: Transport lebender Tiere zum Schlachthof, SENASA) liefert die Schnittstelle Tropa,
   Daten und den Stand jeder Caravana. VISEC zertifiziert nicht – das Ergebnis stützt die eigene Prüfung.
   Ablauf: Am Container stehen die DTE-Nummern aus den Papieren (visecDte, von Hand, gespeichert mit dem Container).
   „Bei VISEC abfragen“ schickt jede Nummer – nur sie, keine Namen – mit dem Token an VISEC; die Antworten liegen mit
   Abfragezeit im Dokument CI_VISEC_DOKUMENT (je Container und DTE die jüngste) und werden beim Lesen dazugestellt
   (ci_visec_zu). Daraus ergibt sich das Kriterium „Tiere laut VISEC“ des Risikoprofils (nur für Container mit DTE-Nummern).
   Token: VISEC_API_TOKEN in .env (Profil bei VISEC → „Token de acceso a la API“ → „Generar token“; ersetzt den alten),
   nur im Mitarbeiter-Container; ohne ihn ist die Abfrage aus. Er verlässt den Server nur in der Kopfzeile an VISEC.
   Schnittstelle (Stand 24.11.2026, /api/Visec/swagger/v1/swagger.json): POST /dte {numero} → {error, requestId, dte:
   {dteId, numero, fechaDte, fechaEstado, fechaArribo, estado, tropa, caravanas: [{caravanaNumero, caravanaTipo, estado}]},
   observaciones}; ein nicht lösbarer Fall kommt mit HTTP 200 und error {code, description} (z. B. NOT_FOUND), HTTP 401 nur
   bei fehlendem, ungültigem oder abgelaufenem Token. Die Abfrage einer einzelnen Caravana (POST /caravana) nutzt das Modul nicht. */
if (!defined('WA_API')) { http_response_code(404); exit; }

const CI_VISEC_DOKUMENT = 'containerimport-visec';
const CI_VISEC_URL = 'https://carne.visec.com.ar/api/Visec';
const CI_VISEC_MAX_DTE = 30;            // DTE-Nummern je Container
const CI_VISEC_MAX_TIERE = 3000;        // gespeicherte Caravanas je DTE
const CI_VISEC_ZEITLIMIT = 15;          // Sekunden Gesamtfrist je Abfrage (Verbinden, Kopfzeilen, Antwort)
const CI_VISEC_BUDGET = 40;             // Sekunden für alle DTE eines Containers; was danach übrig ist, bleibt beim alten Stand
const CI_VISEC_MAX_BYTE = 4 * 1024 * 1024;
const CI_VISEC_LISTE = 100;             // so viele ungültige bzw. offene Caravanas zeigt die Sicht je DTE mit Nummer
/* Stände einer Caravana laut VISEC; alles außer VALIDA und INVALIDA (auch leer = VISEC kennt sie noch nicht) ist „offen“ */
const CI_VISEC_STAENDE = [
    'VALIDA' => 'gültig', 'INVALIDA' => 'ungültig', 'EN_PROCESO' => 'wartet auf Validierung', 'EN_ESPERA' => 'wartet auf den Erzeuger',
    'EN_VALIDACION' => 'in Validierung', 'ERROR_SIGSA' => 'Nummer bei SENASA unbekannt', '' => 'bei VISEC nicht erfasst',
];

function ci_visec_token(): string
{
    $t = trim((string)(getenv('VISEC_API_TOKEN') ?: ''));
    return preg_match('#^[A-Za-z0-9._~+/=-]{10,4096}$#', $t) ? $t : '';   // nur Zeichen eines Tokens: kein Zeilenumbruch in die Kopfzeile
}
function ci_visec_eingerichtet(): bool { return ci_visec_token() !== ''; }

/* DTE-Nummern aus der Eingabe (Text mit einer Nummer je Zeile oder Liste): ohne Leerzeichen, groß, ohne Doppelte, in der
   Reihenfolge der Eingabe. Erlaubt sind Ziffern, Buchstaben und die Trennzeichen - / . (VISEC sucht auch Varianten) */
function ci_visec_nummern($v): array
{
    $teile = is_array($v) ? $v : preg_split('/[\r\n,;]+/', is_string($v) ? $v : '');
    $aus = [];
    foreach ($teile as $t) {
        if (!is_string($t)) throw new InvalidArgumentException('DTE-Nummern: bitte je Zeile eine Nummer.');
        $n = strtoupper((string)preg_replace('/\s+/u', '', $t));
        if ($n === '') continue;
        if (!preg_match('#^[0-9A-Z][0-9A-Z./-]{2,29}$#', $n)) throw new InvalidArgumentException('DTE-Nummer „' . mb_substr($n, 0, 40) . '“ ist ungültig (Ziffern, Buchstaben, - / . – höchstens 30 Zeichen).');
        $aus[$n] = true;
    }
    if (count($aus) > CI_VISEC_MAX_DTE) throw new InvalidArgumentException('Höchstens ' . CI_VISEC_MAX_DTE . ' DTE-Nummern je Container.');
    return array_map('strval', array_keys($aus));   // reine Ziffern würden sonst als Schlüssel zu Zahlen
}

/* Fremder Text: ohne Steuerzeichen, gekürzt */
function ci_visec_text($v, int $max): string
{
    return is_string($v) ? mb_substr(trim((string)preg_replace('/[\x00-\x1F\x7F]+/u', ' ', $v)), 0, $max) : '';
}
/* Zeitpunkt aus der Antwort als „JJJJ-MM-TT“ bzw. „JJJJ-MM-TTTHH:MM“ ($zeit); alles andere leer */
function ci_visec_datum($v, bool $zeit = false): string
{
    return is_string($v) && preg_match('/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2})?/', $v, $m) ? substr($m[0], 0, $zeit ? 16 : 10) : '';
}

/* Eine DTE-Nummer bei VISEC abfragen: Ergebnis zum Speichern. Token abgelehnt, nicht erreichbar oder fremde Antwort enden
   mit fail – dann wird nichts gespeichert. Ein Fall, den VISEC nicht lösen kann (error), ist ein Ergebnis. */
function ci_visec_dte(string $nummer): array
{
    $a = abruf_http((getenv('WA_VISEC_URL') ?: CI_VISEC_URL) . '/dte',   // WA_VISEC_URL nur in den Tests
        ['User-Agent: STAFL-Plattform (Container-Import)', 'Authorization: Bearer ' . ci_visec_token(), 'Accept: application/json', 'Content-Type: application/json'],
        CI_VISEC_ZEITLIMIT, CI_VISEC_MAX_BYTE, 'POST', json_encode(['numero' => $nummer], JSON_THROW_ON_ERROR));
    if ($a['status'] === 401) fail('VISEC lehnt den Zugangstoken ab (fehlt, ungültig oder abgelaufen). Bitte bei VISEC im Profil einen neuen Token erzeugen und vom Administrator in .env eintragen lassen.', 503);
    if ($a['fehler'] !== '' || $a['status'] === 0) fail('VISEC ist gerade nicht erreichbar. Bitte später erneut abfragen.', 502);
    if ($a['status'] !== 200) {
        error_log('[containerimport] VISEC antwortet mit ' . $a['status']);
        fail('VISEC meldet einen Fehler (HTTP ' . $a['status'] . '). Bitte später erneut abfragen.', 502);
    }
    $j = json_decode($a['roh'], true);
    if (!is_array($j)) fail('VISEC hat unerwartet geantwortet. Bitte später erneut abfragen.', 502);
    $r = ['fehler' => '', 'fehlerText' => '', 'anfrage' => preg_match('/^[0-9a-f-]{36}$/i', (string)($j['requestId'] ?? '')) ? strtolower($j['requestId']) : '',
        'observaciones' => ci_visec_text($j['observaciones'] ?? null, 500)];
    if (is_array($j['error'] ?? null)) {
        $code = strtoupper(ci_visec_text($j['error']['code'] ?? null, 40));
        return ['fehler' => preg_match('/^[A-Z0-9_]{1,40}$/', $code) ? $code : 'FEHLER', 'fehlerText' => ci_visec_text($j['error']['description'] ?? null, 300)] + $r;
    }
    $d = $j['dte'] ?? null;
    if (!is_array($d)) fail('VISEC hat unerwartet geantwortet. Bitte später erneut abfragen.', 502);
    $tiere = [];
    foreach (is_array($d['caravanas'] ?? null) ? $d['caravanas'] : [] as $c) {
        if (count($tiere) >= CI_VISEC_MAX_TIERE) break;
        if (!is_array($c)) continue;
        $tiere[] = [ci_visec_text($c['caravanaNumero'] ?? null, 40), ci_visec_text($c['caravanaTipo'] ?? null, 30), strtoupper(ci_visec_text($c['estado'] ?? null, 30))];
    }
    return [
        'registriert' => is_int($d['dteId'] ?? null) && $d['dteId'] > 0,   // negativ: VISEC kennt den DTE noch nicht, Daten von SENASA
        'fechaDte' => ci_visec_datum($d['fechaDte'] ?? null), 'fechaArribo' => ci_visec_datum($d['fechaArribo'] ?? null), 'fechaEstado' => ci_visec_datum($d['fechaEstado'] ?? null, true),
        'estado' => ci_visec_text($d['estado'] ?? null, 40), 'tropa' => ci_visec_text($d['tropa'] ?? null, 40),
        'caravanas' => $tiere,
    ] + $r;
}

/* Alle DTE eines Containers abfragen (außerhalb jeder Sperre – das dauert): Nummer → Ergebnis. Nach CI_VISEC_BUDGET Sekunden
   bleiben die übrigen Nummern unabgefragt (die Antwort nennt sie, ihr alter Stand bleibt). */
function ci_visec_abfragen(array $nummern): array
{
    $ende = microtime(true) + CI_VISEC_BUDGET;
    $aus = [];
    foreach ($nummern as $n) {
        if (microtime(true) > $ende) break;
        $aus[$n] = ci_visec_dte($n);
    }
    return $aus;
}

/* Gespeicherte Ergebnisse: Container-Kennung → DTE-Nummer → Ergebnis mit t (Abfrage) und von. Einmal je Anfrage gelesen,
   unter einer Sperre immer frisch (store_read_gemerkt). */
function ci_visec_ergebnisse(): array
{
    $d = store_read_gemerkt(CI_VISEC_DOKUMENT);
    return is_array($d['ergebnisse'] ?? null) ? $d['ergebnisse'] : [];
}
/* Ergebnisse einer Abfrage ablegen (unter der Sperre EUDR_SPERRE): je DTE die jüngste ersetzt die vorige */
function ci_visec_ablegen(string $sendung, array $ergebnisse, array $me): void
{
    $doc = store_read(CI_VISEC_DOKUMENT);
    $doc = is_array($doc) ? $doc : [];
    $alle = is_array($doc['ergebnisse'] ?? null) ? $doc['ergebnisse'] : [];
    foreach ($ergebnisse as $n => $e) $alle[$sendung][(string)$n] = ['t' => now(), 'von' => (string)$me['name']] + $e;
    store_write(CI_VISEC_DOKUMENT, ['rev' => (int)($doc['rev'] ?? 0) + 1, 'ergebnisse' => $alle]);
}

/* Sicht eines Ergebnisses für die Oberfläche: Zahlen je Stand statt der ganzen Liste, ungültige und offene Caravanas mit Nummer
   (höchstens CI_VISEC_LISTE). Ohne Abfrage nur die Nummer. */
function ci_visec_sicht(string $nummer, ?array $e): array
{
    if (!$e) return ['nummer' => $nummer, 't' => ''];
    $zahlen = ['VALIDA' => 0, 'INVALIDA' => 0, 'offen' => 0];
    $ungueltig = []; $offen = [];
    foreach ($e['caravanas'] ?? [] as [$nr, , $stand]) {
        if ($stand === 'VALIDA') { $zahlen['VALIDA']++; continue; }
        if ($stand === 'INVALIDA') { $zahlen['INVALIDA']++; if (count($ungueltig) < CI_VISEC_LISTE) $ungueltig[] = $nr; continue; }
        $zahlen['offen']++;
        if (count($offen) < CI_VISEC_LISTE) $offen[] = [$nr, CI_VISEC_STAENDE[$stand] ?? $stand];
    }
    return ['nummer' => $nummer, 'tiere' => count($e['caravanas'] ?? []), 'zahlen' => $zahlen, 'ungueltig' => $ungueltig, 'offen' => $offen]
        + array_diff_key($e, ['caravanas' => 1]);
}

/* Container mit den Ergebnissen seiner DTE-Nummern (Feld „visec“, in der Reihenfolge der Nummern) – für Sicht und Profil */
function ci_visec_zu(array $s): array
{
    $je = ci_visec_ergebnisse()[$s['id'] ?? ''] ?? [];
    $s['visec'] = array_map(fn($n) => ci_visec_sicht($n, is_array($je[$n] ?? null) ? $je[$n] : null), $s['visecDte'] ?? []);
    return $s;
}

/* Kriterium „Tiere laut VISEC“ des Risikoprofils; null = der Container nennt keine DTE (kein Kriterium) */
function ci_visec_kriterium(array $s): ?array
{
    $dte = $s['visec'] ?? [];
    if (!$dte) return null;
    $titel = 'Tiere laut VISEC (Argentinien)';
    $name = fn(array $d) => 'DTE ' . $d['nummer'];
    $ungueltig = array_filter($dte, fn($d) => ($d['zahlen']['INVALIDA'] ?? 0) > 0);
    if ($ungueltig) {
        $n = array_sum(array_map(fn($d) => $d['zahlen']['INVALIDA'], $ungueltig));
        return eudr_kriterium('visec', $titel, 'kritisch', "VISEC weist $n " . ($n === 1 ? 'Tier' : 'Tiere') . ' als ungültig aus – diese Tiere dürfen nicht in der Ware sein; mit dem Lieferanten klären.', array_values(array_map($name, $ungueltig)));
    }
    $nie = array_filter($dte, fn($d) => $d['t'] === '');
    $fehler = array_filter($dte, fn($d) => $d['t'] !== '' && ($d['fehler'] !== '' || $d['tiere'] === 0));
    $offen = array_filter($dte, fn($d) => ($d['zahlen']['offen'] ?? 0) > 0);
    if ($nie || $fehler || $offen) {
        $tiere = array_sum(array_map(fn($d) => $d['zahlen']['offen'], $offen));
        $betroffen = $nie + $fehler + $offen;   // gleiche Stellen wie in $dte: jede DTE einmal
        ksort($betroffen);
        return eudr_kriterium('visec', $titel, 'offen', implode(' ', array_filter([
            $nie ? 'Noch nicht bei VISEC abgefragt.' : '',
            $fehler ? 'VISEC kennt einen DTE nicht oder nennt keine Tiere – Nummer prüfen.' : '',
            $offen ? "$tiere " . ($tiere === 1 ? 'Tier ist' : 'Tiere sind') . ' bei VISEC noch nicht abschließend geprüft – später erneut abfragen.' : '',
        ])), array_values(array_map($name, $betroffen)));
    }
    $tiere = array_sum(array_column($dte, 'tiere'));
    $zuletzt = min(array_column($dte, 't'));
    return eudr_kriterium('visec', $titel, 'ok', count($dte) . ' DTE mit ' . $tiere . ' Tieren, alle gültig laut VISEC (Abfrage vom ' . date('d.m.Y', strtotime($zuletzt)) . '). VISEC zertifiziert nicht – das Ergebnis stützt die eigene Prüfung.');
}
