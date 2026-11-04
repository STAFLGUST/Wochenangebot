<?php
declare(strict_types=1);
/* Importzentrale (Verwaltung → Import, Roadmap 10b) – ein Ablauf für alle Importe:
   Importart wählen → Datei wählen → Vorschau (neu / geändert / entfällt / Fehler je Zeile) → übernehmen → Ergebnis und Protokoll.

   Die Zentrale liest und prüft keine Dateiformate selbst. Jede Importart gehört dem Modul, dem die Daten gehören
   (regeln/datenverantwortung.toml), und ist in dessen Importvertrag registriert (app/api/module/<modul>/import.php,
   Funktion import_arten_<modul>()). Die Zentrale ruft nur dessen Vorschau- und Übernahmefunktion auf und prüft vorher
   einheitlich: Anmeldung, Recht der Importart (GR-103), Wartung der Oberfläche, zu der die Importaktion des Eigentümers
   gehört (GR-107), und – falls registriert – die Passwortbestätigung. Vertrag: docs/plattform/schnittstellen/import.md.
   Große Dateien (Registrierung „teile“): Der Leser liefert neben den Daten der Vorschau einzelne Teile; die Vorschau nennt,
   welche Teile der Eigentümer für die Übernahme braucht, der Browser schickt sie vorher einzeln (import_teil, je Anfrage
   höchstens 6 MB), der Eigentümer legt sie in seiner Zwischenablage ab und übernimmt erst mit import_uebernehmen.
   Eigene Darstellung: Der Eigentümer darf der Vorschau „details“ (beliebige Daten, nur für seine Darstellung im Browser,
   W.importDarstellung), „fuss“ (Zusammenfassung über dem Knopf) und „knopf“ (Beschriftung) mitgeben; die Zentrale reicht
   sie nur begrenzt durch und wertet sie nie aus.
   Aktionen: aktionen/importzentrale.php (import_arten, import_pruefen, import_teil, import_uebernehmen). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Module mit Importvertrag, in dieser Reihenfolge angezeigt. Neuer Eigentümer: Datei module/<id>/import.php mit
   import_arten_<id>(), in api/index.php laden und hier eintragen. */
const IMPORT_EIGENTUEMER = ['verwaltung', 'bestand', 'angebot', 'hr', 'controlling'];
const IMPORT_ZEILEN_MAX = 500;              // Zeilen der Vorschau, die an den Browser gehen (Zahlen zählen immer alle)
const IMPORT_DATEITYPEN = ['csv', 'xls', 'xlsx', 'xlsm'];
const IMPORT_ABLAEUFE = ['zentrale', 'editor'];
const IMPORT_OPTIONSTYPEN = ['schalter', 'datum', 'auswahl', 'liste'];   // auswahl: feste Werte des Eigentümers ({wert, text}), z. B. Angebotswoche;
                                                                          // liste: Kennungen, die die Darstellung des Eigentümers setzt (z. B. gewählte Kundengruppen)
const IMPORT_LISTE_MAX = 500;               // Einträge einer Option „liste“
const IMPORT_DETAILS_MAX = 3000000;         // Bytes der „details“ einer Vorschau (JSON)
const IMPORT_ZEILENARTEN = ['neu', 'geaendert', 'entfaellt', 'fehler'];
const IMPORT_MB = 30;                       // Größe einer Datei (Prüfung im Browser); Importarten mit Teilen dürfen mehr („maxMb“, bis 200)
const IMPORT_TEILE_MAX = 2000;              // Teile, die eine Vorschau für die Übernahme anfordern darf

/* Alle registrierten Importarten (id → Eintrag mit Standardwerten). Ungültige Registrierungen sind ein Programmfehler
   und fallen im Test „importzentrale“ auf; sie werden nie stillschweigend angeboten. */
function import_registry(): array
{
    static $reg = null;
    if ($reg !== null) return $reg;
    $reg = [];
    foreach (IMPORT_EIGENTUEMER as $m) {
        foreach (('import_arten_' . $m)() as $id => $a) {
            $a += ['beschreibung' => '', 'kurz' => '', 'ablauf' => 'zentrale', 'optionen' => [], 'mehrere' => false, 'bestaetigung' => '', 'ansicht' => '', 'kodierung' => '',
                   'teile' => '', 'maxMb' => IMPORT_MB];
            $a['eigentuemer'] = $m;
            $a['recht'] = (array)$a['recht'];
            if (isset($reg[$id]) || !preg_match('/^[a-z][a-z0-9_]{1,30}$/', (string)$id) || !$a['recht'] || !isset(AKTIONEN[$a['aktion'] ?? ''])
                || !in_array($a['ablauf'], IMPORT_ABLAEUFE, true) || array_diff($a['dateien'] ?? [], IMPORT_DATEITYPEN) || empty($a['dateien'])
                || ($a['ablauf'] === 'zentrale' && (!is_callable($a['vorschau'] ?? null) || !is_callable($a['uebernahme'] ?? null)))
                || ($a['teile'] !== '' && ($a['ablauf'] !== 'zentrale' || !is_callable($a['teile'])))
                || !is_int($a['maxMb']) || $a['maxMb'] < 1 || $a['maxMb'] > ($a['teile'] !== '' ? 200 : IMPORT_MB)) {
                throw new LogicException("Importart „{$id}“ ist ungültig registriert.");
            }
            foreach ($a['optionen'] as $o) {
                if (!in_array($o['typ'] ?? '', IMPORT_OPTIONSTYPEN, true)) throw new LogicException("Importart „{$id}“: unbekannte Option.");
                if ($o['typ'] === 'auswahl' && (empty($o['werte']) || array_filter($o['werte'], fn($w) => !is_string($w['wert'] ?? null) || !is_string($w['text'] ?? null))
                    || !in_array($o['standard'] ?? null, array_column($o['werte'], 'wert'), true))) throw new LogicException("Importart „{$id}“: Auswahl „{$o['id']}“ ohne gültige Werte.");
                if ($o['typ'] === 'liste' && (!is_array($o['standard'] ?? null) || import_liste($o['standard']) !== array_values($o['standard']))) throw new LogicException("Importart „{$id}“: Liste „{$o['id']}“ ohne gültigen Standard.");
            }
            $reg[$id] = $a;
        }
    }
    return $reg;
}

/* Recht der Importart: alle eingetragenen Rechte (Administrator: alle) */
function import_darf(array $me, array $a): bool
{
    foreach ($a['recht'] as $p) if (!may($me, $p)) return false;
    return true;
}

/* Angaben für die Oberfläche (keine Funktionsnamen) */
function import_art_anzeige(string $id, array $a, array $me): array
{
    [$modul, $ob] = array_pad(explode('.', (string)AKTIONEN[$a['aktion']]['oberflaeche'], 2), 2, '');
    $z = modul_zustand($modul, $ob, $me);
    return ['id' => $id, 'name' => $a['name'], 'kurz' => (string)$a['kurz'], 'beschreibung' => $a['beschreibung'], 'eigentuemer' => $a['eigentuemer'],
            'eigentuemerName' => MODULE[$a['eigentuemer']]['name'] ?? $a['eigentuemer'], 'dateien' => array_values($a['dateien']),
            'kodierung' => $a['kodierung'], 'mehrere' => (bool)$a['mehrere'], 'ablauf' => $a['ablauf'], 'ansicht' => $a['ansicht'],
            'bestaetigung' => $a['bestaetigung'] !== '', 'optionen' => array_values($a['optionen']), 'maxMb' => $a['maxMb'], 'inTeilen' => $a['teile'] !== '',
            'verfuegbar' => $z === null || $z['zugang'], 'wartung' => $z !== null && $z['betrieb'] === 'wartung'];
}

/* Wert einer Option „liste“: nur Kennungen (Buchstaben, Ziffern, . _ -), ohne Doppelte, höchstens IMPORT_LISTE_MAX */
function import_liste($v): array
{
    $out = [];
    foreach (is_array($v) ? $v : [] as $x) {
        if (is_int($x)) $x = (string)$x;
        if (is_string($x) && preg_match('/^[A-Za-z0-9._-]{1,40}$/', $x)) $out[$x] = true;
    }
    return array_slice(array_keys($out), 0, IMPORT_LISTE_MAX);
}

/* Optionen der Importart aus der Anfrage: nur registrierte, mit Standardwert */
function import_optionen(array $a, $roh): array
{
    $roh = is_array($roh) ? $roh : [];
    $out = [];
    foreach ($a['optionen'] as $o) {
        $v = $roh[$o['id']] ?? ($o['standard'] ?? null);
        if ($o['typ'] === 'auswahl') $out[$o['id']] = in_array($v, array_column($o['werte'], 'wert'), true) ? $v : $o['standard'];   // nur angebotene Werte
        elseif ($o['typ'] === 'liste') $out[$o['id']] = import_liste($v);   // ob die Kennungen passen, prüft der Eigentümer
        else $out[$o['id']] = $o['typ'] === 'schalter' ? (bool)$v : (is_string($v) ? mb_substr($v, 0, 20) : null);
        if (!empty($o['pflicht']) && ($out[$o['id']] === null || $out[$o['id']] === '' || $out[$o['id']] === [])) throw new InvalidArgumentException("Bitte „{$o['label']}“ angeben.");
    }
    return $out;
}

/* Antwort des Eigentümers vereinheitlichen: Zahlen, höchstens IMPORT_ZEILEN_MAX Zeilen (Fehler zuerst), Hinweise;
   „details“, „fuss“ und „knopf“ des Eigentümers nur begrenzt durchgereicht (zu große Details entfallen – dann zeigt der
   Browser die einheitliche Vorschau) */
function import_ergebnis(array $r): array
{
    $n = [];
    foreach (['neu', 'geaendert', 'entfaellt', 'unveraendert', 'fehler'] as $k) $n[$k] = max(0, (int)($r['zahlen'][$k] ?? 0));
    $zeilen = [];
    foreach ((is_array($r['zeilen'] ?? null) ? $r['zeilen'] : []) as $z) {
        if (!is_array($z) || !in_array($z['art'] ?? '', IMPORT_ZEILENARTEN, true)) continue;
        $zeilen[] = ['art' => $z['art'], 'zeile' => is_int($z['zeile'] ?? null) ? $z['zeile'] : null, 'schluessel' => mb_substr((string)($z['schluessel'] ?? ''), 0, 40),
                     'name' => mb_substr((string)($z['name'] ?? ''), 0, 200), 'text' => mb_substr((string)($z['text'] ?? ''), 0, 600)];
    }
    $rang = array_flip(['fehler', 'entfaellt', 'geaendert', 'neu']);
    usort($zeilen, function ($x, $y) use ($rang) { return [$rang[$x['art']], $x['zeile'] ?? PHP_INT_MAX] <=> [$rang[$y['art']], $y['zeile'] ?? PHP_INT_MAX]; });
    $h = [];
    foreach ((is_array($r['hinweise'] ?? null) ? $r['hinweise'] : []) as $x) if (is_array($x) && is_string($x['text'] ?? null)) $h[] = ['stufe' => ($x['stufe'] ?? '') === 'warn' ? 'warn' : 'info', 'text' => $x['text']];
    $teile = [];   // Teile, die der Browser vor der Übernahme schicken soll (nur Kennungen, Reihenfolge des Eigentümers)
    foreach ((is_array($r['teile'] ?? null) ? $r['teile'] : []) as $k) if (is_string($k) && preg_match('/^[A-Za-z0-9_-]{1,40}$/', $k)) $teile[$k] = true;
    if (count($teile) > IMPORT_TEILE_MAX) throw new LogicException('Zu viele Teile für eine Übernahme.');
    $details = is_array($r['details'] ?? null) ? $r['details'] : null;
    if ($details !== null) { $j = json_encode($details, JSON_UNESCAPED_UNICODE); if ($j === false || strlen($j) > IMPORT_DETAILS_MAX) $details = null; }
    return ['zahlen' => $n, 'zeilen' => array_slice($zeilen, 0, IMPORT_ZEILEN_MAX), 'zeilenGesamt' => count($zeilen), 'hinweise' => $h,
            'stand' => is_int($r['stand'] ?? null) || is_string($r['stand'] ?? null) ? $r['stand'] : null, 'teile' => array_keys($teile),
            'details' => $details, 'fuss' => is_string($r['fuss'] ?? null) ? mb_substr($r['fuss'], 0, 300) : '', 'knopf' => is_string($r['knopf'] ?? null) ? mb_substr($r['knopf'], 0, 60) : ''];
}

/* Kennung eines Importlaufs (vom Browser zufällig gewählt, 32 Hex-Zeichen) – nur bei Importarten mit Teilen nötig */
function import_upload($v, bool $pflicht): string
{
    $u = is_string($v) ? $v : '';
    if ($u === '' && !$pflicht) return '';
    if (!preg_match('/^[a-f0-9]{32}$/', $u)) fail('Ungültige Kennung des Imports. Bitte die Datei erneut wählen.', 422);
    return $u;
}

/* Gemeinsame Prüfung vor Vorschau, Teil und Übernahme: Anmeldung (mit CSRF), Importart, Recht, Ablauf, Wartung */
function import_vorbereiten(array $b): array
{
    $me = require_auth(true);
    $id = (string)($b['art'] ?? '');
    $a = import_registry()[$id] ?? null;
    if (!$a) fail('Unbekannte Importart.', 404);
    if (!import_darf($me, $a)) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
    if ($a['ablauf'] !== 'zentrale') fail('Dieser Import läuft im Angebotseditor (Vorschau und Rückgängig dort).', 422);
    // Wartung der Oberfläche, zu der die Importaktion des Eigentümers gehört (GR-107): wie bei der Aktion selbst (503)
    modul_durchsetzen(AKTIONEN[$a['aktion']]);
    return [$me, $id, $a];
}

/* Ein Teil einer großen Datei an den Eigentümer (Zwischenablage). Anfrage: art, upload, schluessel, daten, quelle. */
function import_teil_ausfuehren(): array
{
    $b = body();
    [$me, $id, $a] = import_vorbereiten($b);
    if ($a['teile'] === '') fail('Diese Importart wird nicht in Teilen übertragen.', 422);
    $k = is_string($b['schluessel'] ?? null) ? $b['schluessel'] : '';
    if (!preg_match('/^[A-Za-z0-9_-]{1,40}$/', $k)) fail('Ungültiger Teil.', 422);
    $e = ['art' => $id, 'upload' => import_upload($b['upload'] ?? null, true), 'schluessel' => $k,
          'daten' => is_array($b['daten'] ?? null) ? $b['daten'] : [], 'quelle' => s($b['quelle'] ?? '', 200) ?? ''];
    ($a['teile'])($e, $me);
    return ['art' => $id, 'schluessel' => $k];
}

/* Vorschau oder Übernahme einer Importart. Anfrage: art, daten (vom Leser des Eigentümers), quelle (Dateiname), optionen,
   stand (Übernahme: Stand aus der Vorschau – der Eigentümer weist mit 409 ab, wenn sich die Daten inzwischen geändert haben). */
function import_ausfuehren(bool $uebernehmen): array
{
    $b = body();
    [$me, $id, $a] = import_vorbereiten($b);
    if ($uebernehmen && !array_key_exists('stand', $b)) fail('Bitte zuerst die Vorschau laden.', 422);
    if ($uebernehmen && $a['bestaetigung'] !== '') $me = require_perm_confirmed($a['recht'][0], $a['bestaetigung']);
    $e = is_array($b['daten'] ?? null) ? $b['daten'] : [];
    $e['art'] = $id;
    $e['quelle'] = s($b['quelle'] ?? '', 200) ?? '';
    $e['optionen'] = import_optionen($a, $b['optionen'] ?? null);
    $e['stand'] = $b['stand'] ?? null;
    $e['upload'] = import_upload($b['upload'] ?? null, $a['teile'] !== '');   // Importlauf, zu dem die geschickten Teile gehören
    $r = import_ergebnis(($a[$uebernehmen ? 'uebernahme' : 'vorschau'])($e, $me));
    return ['art' => $id, 'pruefen' => !$uebernehmen] + $r;
}
