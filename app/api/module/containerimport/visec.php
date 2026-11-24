<?php
declare(strict_types=1);
/* Container-Import · EUDR: Abfrage von VISEC Carne (https://carne.visec.com.ar) für Container aus Argentinien (Auftrag des
   Inhabers 24.11.2026). VISEC ist die Plattform der argentinischen Rindfleischkette zur EUDR: Jedes Tier (Caravana =
   Ohrmarke) wird dort gegen Entwaldung nach dem 31.12.2020, Schutzgebiete und Legalität geprüft. Über einen DTE
   (Documento de Tránsito Electrónico: Transport lebender Tiere zum Schlachthof, SENASA) liefert die Schnittstelle Tropa,
   Daten und den Stand jeder Caravana. VISEC zertifiziert nicht – das Ergebnis stützt die eigene Prüfung.
   Ablauf: Am Container stehen die DTE-Nummern aus den Papieren (visecDte, von Hand, gespeichert mit dem Container).
   „Bei VISEC abfragen“ schickt jede Nummer – nur sie, keine Namen – mit dem Token an VISEC. Abgelegt wird je Container und DTE
   die jüngste Antwort, verdichtet (Zahlen je Stand, höchstens CI_VISEC_LISTE ungültige bzw. offene Ohrmarken, Kopfdaten, Kennung
   der Anfrage) im Dokument CI_VISEC_DOKUMENT – nie in den Feldern des Containers. Die vollständige Liste bleibt bei VISEC.
   Daraus ergibt sich das Kriterium „Tiere laut VISEC“ des Risikoprofils (nur für Container mit DTE-Nummern); es liest die
   Antworten selbst (ci_visec_zu), damit kein Aufrufer von eudr_profil es vergessen kann.
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
const CI_VISEC_ZEITLIMIT = 15;          // Sekunden Gesamtfrist je Abfrage (Verbinden, Kopfzeilen, Antwort)
const CI_VISEC_BUDGET = 40;             // Sekunden für alle DTE eines Containers: eine Abfrage beginnt nur, wenn sie davor fertig sein kann
const CI_VISEC_MAX_BYTE = 4 * 1024 * 1024;
const CI_VISEC_LISTE = 100;             // so viele ungültige bzw. offene Ohrmarken werden je DTE mit Nummer abgelegt
/* Stände einer Caravana, die noch nicht entschieden sind („offen“); auch leer = VISEC kennt sie noch nicht */
const CI_VISEC_OFFEN = [
    'EN_PROCESO' => 'wartet auf Validierung', 'EN_ESPERA' => 'wartet auf den Erzeuger', 'EN_VALIDACION' => 'in Validierung',
    'ERROR_SIGSA' => 'Nummer bei SENASA unbekannt', '' => 'bei VISEC nicht erfasst',
];
/* Form jedes abgelegten Ergebnisses (auch eines Fehlers) – die Sicht ergänzt t, von und stand */
const CI_VISEC_LEER = ['fehler' => '', 'fehlerText' => '', 'anfrage' => '', 'observaciones' => '', 'registriert' => false, 'fechaDte' => '', 'fechaArribo' => '',
    'estado' => '', 'tropa' => '', 'tiere' => 0, 'zahlen' => ['VALIDA' => 0, 'INVALIDA' => 0, 'offen' => 0], 'ungueltig' => [], 'offen' => []];

/* VISEC nicht erreichbar oder fremde Antwort: beendet die Abfrage eines Containers, bisher Geholtes bleibt */
final class CiVisecFehler extends RuntimeException {}

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
/* Tag aus einem Zeitpunkt der Antwort („JJJJ-MM-TT…“), sonst leer */
function ci_visec_datum($v): string { return is_string($v) && preg_match('/^\d{4}-\d{2}-\d{2}/', $v, $m) ? $m[0] : ''; }

/* Eine DTE-Nummer bei VISEC abfragen → verdichtetes Ergebnis (Form CI_VISEC_LEER). Ein Fall, den VISEC nicht lösen kann
   (error), ist ein Ergebnis. Token abgelehnt: fail (die übrigen Nummern brauchen es nicht zu versuchen); nicht erreichbar,
   Serverfehler oder fremde Antwort: CiVisecFehler. */
function ci_visec_dte(string $nummer): array
{
    $a = abruf_http((getenv('WA_VISEC_URL') ?: CI_VISEC_URL) . '/dte',   // WA_VISEC_URL nur in den Tests
        ['User-Agent: STAFL-Plattform (Container-Import)', 'Authorization: Bearer ' . ci_visec_token(), 'Accept: application/json', 'Content-Type: application/json'],
        CI_VISEC_ZEITLIMIT, CI_VISEC_MAX_BYTE, 'POST', json_encode(['numero' => $nummer], JSON_THROW_ON_ERROR));
    if ($a['status'] === 401) fail('VISEC lehnt den Zugangstoken ab (fehlt, ungültig oder abgelaufen). Bitte bei VISEC im Profil einen neuen Token erzeugen und vom Administrator in .env eintragen lassen.', 503);
    if ($a['fehler'] !== '' || $a['status'] === 0) throw new CiVisecFehler('VISEC ist gerade nicht erreichbar.');
    if ($a['status'] !== 200) {
        error_log('[containerimport] VISEC antwortet mit ' . $a['status']);
        throw new CiVisecFehler('VISEC meldet einen Fehler (HTTP ' . $a['status'] . ').');
    }
    $j = json_decode($a['roh'], true);
    if (!is_array($j)) throw new CiVisecFehler('VISEC hat unerwartet geantwortet.');
    $e = ['anfrage' => preg_match('/^[0-9a-f-]{36}$/i', (string)($j['requestId'] ?? '')) ? strtolower($j['requestId']) : '',
        'observaciones' => ci_visec_text($j['observaciones'] ?? null, 500)] + CI_VISEC_LEER;
    if (is_array($j['error'] ?? null)) {
        $code = strtoupper(ci_visec_text($j['error']['code'] ?? null, 40));
        return ['fehler' => preg_match('/^[A-Z0-9_]{1,40}$/', $code) ? $code : 'FEHLER', 'fehlerText' => ci_visec_text($j['error']['description'] ?? null, 300)] + $e;
    }
    $d = $j['dte'] ?? null;
    if (!is_array($d)) throw new CiVisecFehler('VISEC hat unerwartet geantwortet.');
    foreach (is_array($d['caravanas'] ?? null) ? $d['caravanas'] : [] as $c) {
        if (!is_array($c)) continue;
        $nr = ci_visec_text($c['caravanaNumero'] ?? null, 40);
        $stand = strtoupper(ci_visec_text($c['estado'] ?? null, 30));
        $e['tiere']++;
        if ($stand === 'VALIDA') { $e['zahlen']['VALIDA']++; continue; }
        if ($stand === 'INVALIDA') { $e['zahlen']['INVALIDA']++; if (count($e['ungueltig']) < CI_VISEC_LISTE) $e['ungueltig'][] = $nr; continue; }
        $e['zahlen']['offen']++;
        if (count($e['offen']) < CI_VISEC_LISTE) $e['offen'][] = [$nr, CI_VISEC_OFFEN[$stand] ?? $stand];
    }
    return [
        'registriert' => is_int($d['dteId'] ?? null) && $d['dteId'] > 0,   // negativ: VISEC kennt den DTE noch nicht, Tiere von SENASA
        'fechaDte' => ci_visec_datum($d['fechaDte'] ?? null), 'fechaArribo' => ci_visec_datum($d['fechaArribo'] ?? null),
        'estado' => ci_visec_text($d['estado'] ?? null, 40), 'tropa' => ci_visec_text($d['tropa'] ?? null, 40),
    ] + $e;
}

/* Alle DTE eines Containers abfragen (außerhalb jeder Sperre – das dauert) → [Nummer → Ergebnis, Fehlermeldung oder '']. Nach
   dem Zeitbudget oder dem ersten CiVisecFehler bleiben die übrigen Nummern unabgefragt (ihr alter Stand bleibt). */
function ci_visec_abfragen(array $nummern): array
{
    $ende = microtime(true) + CI_VISEC_BUDGET;
    $aus = [];
    foreach ($nummern as $n) {
        if (microtime(true) + CI_VISEC_ZEITLIMIT > $ende) break;
        try { $aus[$n] = ci_visec_dte($n); } catch (CiVisecFehler $f) { return [$aus, $f->getMessage()]; }
    }
    return [$aus, ''];
}

/* Abgelegte Antworten: Container-Kennung → DTE-Nummer → Ergebnis mit t (Abfrage) und von. Einmal je Anfrage gelesen, unter
   einer Sperre immer frisch (store_read_gemerkt); klein, weil verdichtet. */
function ci_visec_ergebnisse(): array
{
    $d = store_read_gemerkt(CI_VISEC_DOKUMENT);
    return is_array($d['ergebnisse'] ?? null) ? $d['ergebnisse'] : [];
}
/* Antworten einer Abfrage ablegen (unter der Sperre EUDR_SPERRE): je DTE ersetzt die jüngste die vorige */
function ci_visec_ablegen(string $sendung, array $ergebnisse, array $me): void
{
    $doc = store_read(CI_VISEC_DOKUMENT);
    $alle = is_array($doc['ergebnisse'] ?? null) ? $doc['ergebnisse'] : [];
    foreach ($ergebnisse as $n => $e) $alle[$sendung][(string)$n] = ['t' => now(), 'von' => (string)$me['name']] + $e;
    store_write(CI_VISEC_DOKUMENT, ['ergebnisse' => $alle]);
}

/* Container mit seinen DTE (Feld „visec“, in der Reihenfolge der Nummern), je DTE mit „stand“:
   nie (nicht abgefragt) | fehler (VISEC kennt den DTE nicht oder nennt keine Tiere) | kritisch (ungültige Tiere) | offen
   (Tiere noch nicht entschieden) | ok – die eine Einstufung für Kriterium und Oberfläche */
function ci_visec_zu(array $s): array
{
    $je = ci_visec_ergebnisse()[$s['id'] ?? ''] ?? [];
    $s['visec'] = array_map(function (string $n) use ($je): array {
        $e = is_array($je[$n] ?? null) ? $je[$n] + ['t' => '', 'von' => ''] + CI_VISEC_LEER : ['t' => '', 'von' => ''] + CI_VISEC_LEER;
        $stand = match (true) {
            $e['t'] === '' => 'nie',
            $e['fehler'] !== '' || $e['tiere'] === 0 => 'fehler',
            $e['zahlen']['INVALIDA'] > 0 => 'kritisch',
            $e['zahlen']['offen'] > 0 => 'offen',
            default => 'ok',
        };
        return ['nummer' => $n, 'stand' => $stand] + $e;
    }, $s['visecDte'] ?? []);
    return $s;
}

/* Kriterium „Tiere laut VISEC“ des Risikoprofils; null = der Container nennt keine DTE (kein Kriterium) */
function ci_visec_kriterium(array $s): ?array
{
    $dte = ci_visec_zu($s)['visec'];
    if (!$dte) return null;
    $titel = 'Tiere laut VISEC (Argentinien)';
    $je = fn(string ...$staende) => array_values(array_filter($dte, fn($d) => in_array($d['stand'], $staende, true)));
    $namen = fn(array $liste) => array_map(fn($d) => 'DTE ' . $d['nummer'], $liste);
    if ($kritisch = $je('kritisch')) {
        $n = array_sum(array_map(fn($d) => $d['zahlen']['INVALIDA'], $kritisch));
        return eudr_kriterium('visec', $titel, 'kritisch', "VISEC weist $n " . ($n === 1 ? 'Tier' : 'Tiere') . ' als ungültig aus – diese Tiere dürfen nicht in der Ware sein; mit dem Lieferanten klären.', $namen($kritisch));
    }
    if ($betroffen = $je('nie', 'fehler', 'offen')) {
        $tiere = array_sum(array_map(fn($d) => $d['zahlen']['offen'], $je('offen')));
        return eudr_kriterium('visec', $titel, 'offen', implode(' ', array_filter([
            $je('nie') ? 'Noch nicht bei VISEC abgefragt.' : '',
            $je('fehler') ? 'VISEC kennt einen DTE nicht oder nennt keine Tiere – Nummer prüfen.' : '',
            $tiere ? "$tiere " . ($tiere === 1 ? 'Tier ist' : 'Tiere sind') . ' bei VISEC noch nicht abschließend geprüft – später erneut abfragen.' : '',
        ])), $namen($betroffen));
    }
    $aelteste = min(array_column($dte, 't'));
    return eudr_kriterium('visec', $titel, 'ok', count($dte) . ' DTE mit ' . array_sum(array_column($dte, 'tiere')) . ' Tieren, alle gültig laut VISEC (Abfrage vom ' . date('d.m.Y', strtotime($aelteste)) . '). VISEC zertifiziert nicht – das Ergebnis stützt die eigene Prüfung.');
}
