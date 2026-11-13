<?php
declare(strict_types=1);
/* Startseite des Dashboards (Gestaltung „C2“): „Heute für Sie“, Schnellaktionen, „Zuletzt bearbeitet“ und Favoriten.
   Nur für die Aktion start_heute auf dem Dashboard-Host (aktionen/module.php lädt diese Datei erst dort, GR-109).

   „Heute für Sie“: Jedes Fachmodul liefert über eine eigene Funktion <präfix>_startseite($me) die offenen Punkte, die
   dieser Mitarbeiter dort erledigen kann (STARTSEITE_ANBIETER). Die Funktion liegt beim Eigentümer der Daten und prüft
   ihre Rechte selbst (GR-101, GR-103) – hier werden nur Module gefragt, deren Kachel für den Mitarbeiter nutzbar ist
   (Modulzugang, Freigabe, Wartung wie im Dashboard). Ein Punkt: art (ueberfaellig | heute | demnaechst), titel, detail,
   datum (JJJJ-MM-TT oder leer), ziel (Reiter des Moduls, z. B. „antraege“ → …/#antraege), anzahl (Sammelpunkte, sonst 1).
   Fehler eines Moduls verhindern die Startseite nicht: das Modul fehlt dann und steht unter „fehler“.

   „Zuletzt bearbeitet“: die eigenen letzten Änderungen aus dem Protokoll (nur eigene Einträge, maskiert wie in der
   Protokollansicht, nur Module mit nutzbarer Kachel). Schnellaktionen: feste Sprünge in Module, die es dort schon gibt –
   nur mit Modulzugang und passendem Recht. Favoriten: Liste von Modul-IDs am eigenen Konto (Feld „favoriten“, neu und
   optional, GR-006); ohne Wahl zeigt das Dashboard die ersten nutzbaren Anwendungen. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const STARTSEITE_ANBIETER = ['angebot' => 'angebot_startseite', 'bestand' => 'bestand_startseite', 'hr' => 'hr_startseite', 'crm' => 'crm_startseite',
    'qs' => 'qs_startseite', 'leergut' => 'lg_startseite', 'rewe' => 'rw_startseite', 'marketing' => 'mkt_startseite', 'versand' => 'versand_startseite'];
const STARTSEITE_ARTEN = ['ueberfaellig' => 0, 'heute' => 1, 'demnaechst' => 2];
const STARTSEITE_JE_MODUL = 8;        // Punkte je Modul in der Liste (gezählt werden alle)
const STARTSEITE_VORLAUF = 3;         // „Demnächst“: Fälligkeit in höchstens so vielen Tagen (Module können eigene Fristen nutzen)
const STARTSEITE_ZULETZT = 6;
const STARTSEITE_FAVORITEN_MAX = 8;
/* Protokoll-Vorgang → Modul (nur Vorgänge, die in einer Anwendung bearbeitet werden; Anmeldung, Sicherheit u. Ä. fehlen bewusst) */
const STARTSEITE_PROTOKOLL_MODUL = ['draft' => 'angebot', 'publish' => 'angebot', 'discard' => 'angebot', 'offers' => 'angebot', 'import' => 'angebot',
    'bestellung' => 'angebot', 'history' => 'angebot', 'einzelangebot' => 'crm', 'stock' => 'bestand', 'master' => 'verwaltung', 'customers' => 'verwaltung',
    'hr' => 'hr', 'qs' => 'qs', 'leergut' => 'leergut', 'rewe' => 'rewe', 'marketing' => 'marketing', 'crm' => 'crm', 'controlling' => 'controlling'];
/* Schnellaktionen in fester Reihenfolge (die ersten vier wie im Entwurf „C2“): Modul, nötiges Recht ('' = Modulzugang genügt),
   Text, Ziel im Modul (Reiter bzw. „<reiter>/neu“ – das Modul öffnet dann gleich das Fenster zum Anlegen); neu = Plus-Symbol */
const STARTSEITE_AKTIONEN = [
    ['modul' => 'angebot', 'recht' => 'einzelangebote.bearbeiten', 'titel' => 'Kundenangebot erstellen', 'ziel' => 'einzel', 'neu' => true],
    ['modul' => 'hr', 'recht' => 'hr.antrag', 'titel' => 'Urlaub beantragen', 'ziel' => 'mein', 'neu' => true],
    ['modul' => 'crm', 'recht' => 'crm.bearbeiten', 'titel' => 'Interessent anlegen', 'ziel' => 'kunden/neu', 'neu' => true],
    ['modul' => 'import', 'recht' => '', 'titel' => 'Daten importieren', 'ziel' => '', 'neu' => true],
    ['modul' => 'angebot', 'recht' => 'angebot.bearbeiten', 'titel' => 'Wochenangebot bearbeiten', 'ziel' => '', 'neu' => false],
    ['modul' => 'versand', 'recht' => 'angebot.veroeffentlichen', 'titel' => 'Angebot veröffentlichen', 'ziel' => '', 'neu' => false],
    ['modul' => 'marketing', 'recht' => 'marketing.bearbeiten', 'titel' => 'Beitrag anlegen', 'ziel' => 'kalender/neu', 'neu' => true],
    ['modul' => 'qs', 'recht' => 'qs.nachweis', 'titel' => 'Prüfnachweis erfassen', 'ziel' => 'pruefplan', 'neu' => true],
    ['modul' => 'crm', 'recht' => 'crm.sehen', 'titel' => 'Wiedervorlagen ansehen', 'ziel' => 'wiedervorlagen', 'neu' => false],
    ['modul' => 'rewe', 'recht' => 'rewe.bearbeiten', 'titel' => 'REWE-Wochenabfrage', 'ziel' => 'woche', 'neu' => false],
    ['modul' => 'leergut', 'recht' => 'leergut.bearbeiten', 'titel' => 'Leergut abstimmen', 'ziel' => 'abstimmungen', 'neu' => false],
];

/* Hilfen für die Anbieter der Module: Tage von heute bis zu einem Datum und die Gruppe eines Punkts */
function startseite_tage(string $datum, ?string $heute = null): int
{
    $heute ??= date('Y-m-d');
    return (int)round((strtotime($datum . ' 12:00:00 UTC') - strtotime($heute . ' 12:00:00 UTC')) / 86400);
}
/* '' = (noch) kein Punkt für die Startseite */
function startseite_art(int $tage, int $vorlauf = STARTSEITE_VORLAUF): string
{
    return $tage < 0 ? 'ueberfaellig' : ($tage === 0 ? 'heute' : ($tage <= $vorlauf ? 'demnaechst' : ''));
}
/* Kurzform eines Datums für Texte: „06.11.“ */
function startseite_de(string $datum): string
{
    return preg_match('/^\d{4}-(\d{2})-(\d{2})/', $datum, $m) ? $m[2] . '.' . $m[1] . '.' : '';
}

/* Module mit nutzbarer Kachel (wie die Kacheln des Dashboards: Modulzugang, Freigabe, Wartung) */
function startseite_module(array $me): array
{
    $out = [];
    foreach (modul_uebersicht($me) as $m) if (!empty($m['kachel']['zugang'])) $out[$m['id']] = (int)($m['reihenfolge'] ?? 999);
    return $out;
}

function startseite_punkt($p, string $modul): ?array
{
    if (!is_array($p) || !isset(STARTSEITE_ARTEN[$p['art'] ?? ''])) return null;
    $titel = mb_substr(trim((string)($p['titel'] ?? '')), 0, 160);
    if ($titel === '') return null;
    $datum = (string)($p['datum'] ?? '');
    $ziel = (string)($p['ziel'] ?? '');
    return ['modul' => $modul, 'art' => $p['art'], 'titel' => $titel, 'detail' => mb_substr(trim((string)($p['detail'] ?? '')), 0, 200),
            'datum' => preg_match('/^\d{4}-\d{2}-\d{2}$/', $datum) ? $datum : '', 'ziel' => preg_match('/^[a-z0-9_\/-]{0,60}$/', $ziel) ? $ziel : '',
            'anzahl' => max(1, (int)($p['anzahl'] ?? 1))];
}

function startseite_heute(array $me): array
{
    $module = startseite_module($me);
    $punkte = []; $zahlen = []; $fehler = [];
    foreach (STARTSEITE_ANBIETER as $modul => $fn) {
        if (!isset($module[$modul]) || !function_exists($fn)) continue;
        try {
            $liste = $fn($me);
        } catch (Throwable $e) {
            error_log('Startseite: Modul ' . $modul . ': ' . $e->getMessage());
            $fehler[] = $modul;
            continue;
        }
        $eigene = [];
        foreach (is_array($liste) ? $liste : [] as $p) if ($x = startseite_punkt($p, $modul)) $eigene[] = $x;
        if (!$eigene) continue;
        usort($eigene, 'startseite_vergleich');
        $z = ['offen' => 0, 'ueberfaellig' => 0];
        foreach ($eigene as $x) { $z['offen'] += $x['anzahl']; if ($x['art'] === 'ueberfaellig') $z['ueberfaellig'] += $x['anzahl']; }
        $zahlen[$modul] = $z;
        foreach (array_slice($eigene, 0, STARTSEITE_JE_MODUL) as $x) $punkte[] = $x + ['reihe' => $module[$modul]];
    }
    usort($punkte, 'startseite_vergleich');
    $gesamt = ['offen' => array_sum(array_column($zahlen, 'offen')), 'ueberfaellig' => array_sum(array_column($zahlen, 'ueberfaellig'))];
    $fav = $me['favoriten'] ?? null;
    return ['heute' => date('Y-m-d'), 'punkte' => array_map(fn($p) => array_diff_key($p, ['reihe' => 1]), $punkte), 'zahlen' => (object)$zahlen, 'gesamt' => $gesamt,
            'zuletzt' => startseite_zuletzt($me, $module), 'aktionen' => startseite_aktionen($me, $module),
            'favoriten' => is_array($fav) ? array_values(array_filter($fav, 'is_string')) : null, 'fehler' => $fehler];
}
/* Überfällig vor heute vor demnächst; innerhalb nach Datum (ohne Datum zuletzt), dann Reihenfolge der Module */
function startseite_vergleich(array $a, array $b): int
{
    return [STARTSEITE_ARTEN[$a['art']], $a['datum'] === '' ? '9999' : $a['datum'], $a['reihe'] ?? 0, $a['titel']]
       <=> [STARTSEITE_ARTEN[$b['art']], $b['datum'] === '' ? '9999' : $b['datum'], $b['reihe'] ?? 0, $b['titel']];
}

/* Eigene letzte Änderungen aus dem Protokoll (laufender und vorheriger Monat), je Text nur die neueste */
function startseite_zuletzt(array $me, array $module): array
{
    $wer = (string)($me['username'] ?? '');
    if ($wer === '') return [];
    $out = []; $gesehen = [];
    foreach ([utc_monat(0), utc_monat(-1)] as $monat) {
        $eigene = [];
        foreach (protokoll_monat($monat) as $e) {
            if (($e['u'] ?? '') !== $wer || ($e['r'] ?? '') === 'kunde') continue;
            $modul = STARTSEITE_PROTOKOLL_MODUL[$e['a'] ?? ''] ?? null;
            if ($modul === null || !isset($module[$modul])) continue;
            $eigene[] = $e + ['modul' => $modul];
        }
        foreach (array_reverse(protokoll_maskieren($eigene, $me)) as $e) {
            $text = trim((string)($e['s'] ?? ''));
            if ($text === '' || isset($gesehen[$text]) || stripos($text, 'heruntergeladen') !== false) continue;
            $gesehen[$text] = true;
            // Vorsatz des Moduls („QM-System: …“, „REWE: …“) entfällt – das Modul steht in der Zeile darunter
            $kurz = preg_replace('/^(QM-System|Marketing|CRM|Leergut|REWE|HR|Controlling|Preisverlauf): /u', '', $text);
            $out[] = ['modul' => $e['modul'], 'text' => mb_substr($kurz, 0, 160), 'zeit' => (string)($e['t'] ?? '')];
            if (count($out) >= STARTSEITE_ZULETZT) return $out;
        }
    }
    return $out;
}

function startseite_aktionen(array $me, array $module): array
{
    $out = [];
    foreach (STARTSEITE_AKTIONEN as $a) {
        if (!isset($module[$a['modul']]) || ($a['recht'] !== '' && !may($me, $a['recht']))) continue;
        $out[] = ['modul' => $a['modul'], 'titel' => $a['titel'], 'ziel' => $a['ziel'], 'neu' => $a['neu']];
    }
    return $out;
}

/* Favoriten prüfen: nur Module mit Kachel, ohne Doppelte, höchstens STARTSEITE_FAVORITEN_MAX; null = zurück zum Standard */
function startseite_favoriten_pruefen($liste): ?array
{
    if ($liste === null) return null;
    if (!is_array($liste) || array_values($liste) !== $liste || count($liste) > STARTSEITE_FAVORITEN_MAX) throw new InvalidArgumentException('Bitte höchstens ' . STARTSEITE_FAVORITEN_MAX . ' Favoriten wählen.');
    $out = [];
    foreach ($liste as $id) {
        if (!is_string($id) || empty(MODULE[$id]['dashboard'])) throw new InvalidArgumentException('Unbekannte Anwendung.');
        if (!in_array($id, $out, true)) $out[] = $id;
    }
    return $out;
}
