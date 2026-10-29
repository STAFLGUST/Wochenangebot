<?php
declare(strict_types=1);
/* Leergut · Leergutkonten und Abstimmung: Daten und Regeln des Moduls „leergut“ (Oberfläche leergut.intern, Aktionen in
   app/api/aktionen/leergut.php). Löst die Excel-Liste „Leergut Bilanz Allgemein“ ab: je Partner (Lieferant, Spedition,
   Kühlhaus, Kunde) ein Konto mit Bewegungen je Lademittel, Abstimmungen mit den Auszügen der Partner (Fristen), Dachser-
   Abschreibungen für nicht getauschtes Leergut unserer Kunden, Inventur des eigenen Bestands und Bilanz zum Stichtag.

   Vorzeichen wie in der Excel-Liste: + = der Partner schuldet uns Leergut, − = wir schulden dem Partner.
   Abgang = wir übergeben Leergut an den Partner (+), Zugang = der Partner übergibt uns Leergut (−).

   Eigene Dokumente (alle Schreibvorgänge unter der Sperre „leergut-bewegungen“):
     leergut-stamm          Lademittel (Name, Wert je Stück für die Bewertung) und Partner (Art, Firma/Mandant, Konto-Nr.
                            beim Partner, Frist für Widersprüche in Tagen, E-Mail für die Abstimmung, Lieferanten hinter einem
                            Sammelkonto, genutzte Lademittel, aktiv)
     leergut-bewegungen     Bewegungen je Partner: Datum, Art, Abgang/Zugang je Lademittel, Beleg, Text; nie geändert oder
                            gelöscht – Fehler werden storniert (Status statt Löschen) und neu gebucht
     leergut-abstimmungen   Auszüge der Partner zum Stichtag: Saldo laut Partner, unser Saldo zum Stichtag (Schnappschuss beim
                            Erfassen, GR-106), Eingang, Frist, Status offen/bestätigt/widersprochen/zur Info, Notiz, Verlauf
     leergut-abschreibungen Dachser-Abschreibungen „lt. Empfänger“: Kunde, Sendung, Mengen, Status offen/widersprochen/
                            berechnet/ausgeglichen/nicht zu beachten, WinAB-Auftrag, Notiz, Verlauf
     leergut-inventur       Eigener Bestand zum Stichtag (z. B. Lager gefüllt, Kisten unbenutzt, Abholer) für die Bilanz
   Kundenkonten aus WinAB: den Bericht „Lademittelbewegungen Kunden“ liest die Oberfläche im Browser und schickt nur die
   Belege, die den Saldo eines Kunden ändern; lg_winab_pruefen/lg_winab_abgleich gleichen sie je Beleg ab (Partner mit
   WinAB-Kundennummer „kundenNr“, Bewegungen mit Herkunft „winab“; geänderte und ausgeglichene Belege werden storniert).
   Erste/letzte Lieferung und letzte Rückgabe laut Bericht (auch aus reinem Tausch) stehen am Partner (Feld „winab“) und
   fließen in „Leergut bei Kunden“ und die Abholliste (lg_kunden_leergut, lg_csv_kunden) ein.
   Dachser-Liste „Unterkonto-Vorspediteur“ (Mail „Infos von Fa. DACHSER“): lg_mail_text, lg_dachser_lesen, lg_dachser_abgleich.
   Keine Daten anderer Module. Gespeicherte Felder, die diese Fassung nicht kennt, bleiben beim Speichern erhalten (GR-006).
   Rechte (GR-103): leergut.sehen, leergut.bearbeiten, leergut.verwalten. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const LG_MANDANTEN = ['standard' => 'Standard-Fleisch', 'matthies' => 'Matthies Fleischwaren'];
const LG_ARTEN = ['lieferant' => 'Lieferant', 'spedition' => 'Spedition', 'kuehlhaus' => 'Kühlhaus / Lager', 'kunde' => 'Kunde', 'sonstige' => 'Sonstige'];
const LG_TYPEN = ['bewegung' => 'Lieferung / Tausch', 'abholung' => 'Abholung / Rückgabe', 'umbuchung' => 'Umbuchung', 'korrektur' => 'Korrektur', 'anfang' => 'Anfangsbestand'];
const LG_ABST_STATUS = ['offen' => 'Offen', 'bestaetigt' => 'Bestätigt', 'widersprochen' => 'Widersprochen', 'info' => 'Zur Info'];
const LG_ABSCHR_STATUS = ['offen' => 'Offen', 'widersprochen' => 'Widersprochen', 'berechnet' => 'Berechnet', 'ausgeglichen' => 'Ausgeglichen', 'ignoriert' => 'Nicht zu beachten'];
const LG_DOKS = ['leergut-stamm', 'leergut-bewegungen', 'leergut-abstimmungen', 'leergut-abschreibungen', 'leergut-inventur'];
const LG_MAX_PARTNER = 2000;      // Lieferanten, Speditionen und Kundenkonten aus WinAB
const LG_MAX_LADEMITTEL = 30;
const LG_MAX_BEWEGUNGEN = 200000;
const LG_MAX_ABSTIMMUNGEN = 20000;
const LG_MAX_ABSCHREIBUNGEN = 50000;
const LG_MAX_INVENTUR = 2000;
const LG_MAX_MENGE = 1000000;     // Stück je Lademittel und Buchung
const LG_MAX_VERLAUF = 100;
const LG_FRIST_STANDARD = 14;
const LG_WINAB_ARTEN = ['Lieferschein', 'Gutschrift', 'Rechnung'];   // Sammelrechnungen wiederholen die Lieferscheine
const LG_MAX_WINAB_BELEGE = 50000;
const LG_MAX_WINAB_KUNDEN = 5000;

/* ---------- Grundwerte ---------- */
/* Lademittel der Excel-Liste; Werte je Stück laut Leitfaden (änderbar unter Einstellungen) */
function lg_grund_lademittel(): array
{
    return [['id' => 'e2', 'name' => 'E2-Kiste', 'wert' => 5.5, 'aktiv' => true], ['id' => 'h1', 'name' => 'H1-Palette', 'wert' => 36.0, 'aktiv' => true],
            ['id' => 'eu', 'name' => 'Europalette', 'wert' => null, 'aktiv' => true], ['id' => 'haken', 'name' => 'Eurohaken', 'wert' => null, 'aktiv' => true],
            ['id' => 'e1', 'name' => 'E1-Kiste', 'wert' => null, 'aktiv' => true], ['id' => 'be2', 'name' => 'Blaue E2 (Palettenpool)', 'wert' => null, 'aktiv' => true],
            ['id' => 'kuebel', 'name' => 'Kübel', 'wert' => null, 'aktiv' => true]];
}

/* ---------- Laden und Schreiben ---------- */
function lg_stamm(): array
{
    $d = store_read('leergut-stamm');
    $d = is_array($d) ? $d : [];
    $out = ['rev' => (int)($d['rev'] ?? 0)];
    $out['lademittel'] = is_array($d['lademittel'] ?? null) && $d['lademittel'] ? array_values($d['lademittel']) : lg_grund_lademittel();
    $out['partner'] = is_array($d['partner'] ?? null) ? array_values($d['partner']) : [];
    return $out + $d;
}
function lg_doc(string $name): array
{
    $d = store_read($name);
    return ['rev' => (int)($d['rev'] ?? 0), 'liste' => is_array($d['liste'] ?? null) ? array_values($d['liste']) : []] + (is_array($d) ? $d : []);
}
function lg_schreiben(string $name, array $doc): void
{
    $doc['rev'] = (int)($doc['rev'] ?? 0) + 1;
    $doc['updatedAt'] = now();
    store_write($name, $doc);
}
function lg_id(string $praefix): string { return $praefix . bin2hex(random_bytes(6)); }
function lg_ids(array $liste): array { return array_values(array_map(function ($x) { return (string)$x['id']; }, $liste)); }
function lg_wer(array $me): array { return ['t' => now(), 'von' => (string)$me['name'], 'vonId' => (string)$me['id']]; }
function lg_verlauf(array &$e, array $me, string $was): void
{
    $e['verlauf'] = is_array($e['verlauf'] ?? null) ? $e['verlauf'] : [];
    $e['verlauf'][] = ['t' => now(), 'von' => (string)$me['name'], 'was' => $was];
    if (count($e['verlauf']) > LG_MAX_VERLAUF) $e['verlauf'] = array_slice($e['verlauf'], -LG_MAX_VERLAUF);
}
/* Ist das Modul noch leer (für den Import ohne „ersetzen“)? Partner oder Buchungen zählen, die Grundwerte nicht. */
function lg_leer(): bool
{
    if (lg_stamm()['partner']) return false;
    foreach (['leergut-bewegungen', 'leergut-abstimmungen', 'leergut-abschreibungen', 'leergut-inventur'] as $n) if (lg_doc($n)['liste']) return false;
    return true;
}

/* ---------- Prüfen der Eingaben ---------- */
function lg_text($v, int $max, string $was): string
{
    if ($v !== null && !is_string($v) && !is_int($v) && !is_float($v)) throw new InvalidArgumentException("$was: ungültiger Wert.");
    $t = trim(str_replace("\r", '', (string)$v));
    $t = preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', $t) ?? '';
    if (mb_strlen($t) > $max) throw new InvalidArgumentException("$was: höchstens $max Zeichen.");
    return $t;
}
function lg_datum($v, string $was, bool $pflicht = true): string
{
    $v = is_string($v) ? trim($v) : '';
    if ($v === '') { if ($pflicht) throw new InvalidArgumentException("$was: bitte ein Datum angeben."); return ''; }
    if (!preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $m) || !checkdate((int)$m[2], (int)$m[3], (int)$m[1]) || (int)$m[1] < 2000 || (int)$m[1] > 2099)
        throw new InvalidArgumentException("$was: bitte ein gültiges Datum angeben.");
    return $v;
}
function lg_wahl($v, array $erlaubt, string $was): string
{
    $v = is_string($v) ? trim($v) : '';
    if (!in_array($v, $erlaubt, true)) throw new InvalidArgumentException("$was: ungültige Auswahl.");
    return $v;
}
/* Ganze Zahl (Stück). Erlaubt auch Texte mit deutscher Schreibweise („1.234“). */
function lg_ganz($v, string $was, bool $negativ): int
{
    if (is_string($v)) { $v = str_replace(['.', ' ', "\u{a0}"], '', trim($v)); $v = str_replace(',', '.', $v); }
    if (is_bool($v) || !is_numeric($v) || (float)$v != round((float)$v)) throw new InvalidArgumentException("$was: bitte eine ganze Zahl angeben.");
    $n = (int)round((float)$v);
    if (!$negativ && $n < 0) throw new InvalidArgumentException("$was: bitte eine Zahl ab 0 angeben.");
    if (abs($n) > LG_MAX_MENGE) throw new InvalidArgumentException("$was: Zahl zu groß.");
    return $n;
}
/* Mengen je Lademittel: { e2: 12, h1: 1 } – nur bekannte Lademittel, leere und 0 entfallen */
function lg_mengen($v, array $lmIds, string $was, bool $negativ): array
{
    if ($v === null || $v === '' || $v === []) return [];
    if (!is_array($v)) throw new InvalidArgumentException("$was: ungültige Angaben.");
    $out = [];
    foreach ($v as $k => $n) {
        $k = (string)$k;
        if (!in_array($k, $lmIds, true)) throw new InvalidArgumentException("$was: unbekanntes Lademittel „" . mb_substr($k, 0, 30) . '“.');
        if ($n === null || $n === '') continue;
        $z = lg_ganz($n, "$was ($k)", $negativ);
        if ($z !== 0) $out[$k] = $z;
    }
    return $out;
}
function lg_betrag($v, string $was): ?float
{
    if ($v === null || $v === '') return null;
    if (is_string($v)) { $v = str_replace(['.', ' ', '€', "\u{a0}"], '', trim($v)); $v = str_replace(',', '.', $v); }
    if (is_bool($v) || !is_numeric($v) || (float)$v < 0 || (float)$v > 100000) throw new InvalidArgumentException("$was: bitte einen Betrag ab 0 angeben.");
    return round((float)$v, 2);
}
function lg_email($v, string $was): string
{
    $t = lg_text($v, 300, $was);
    if ($t === '') return '';
    $ok = [];
    foreach (preg_split('/[;,\s]+/', $t) ?: [] as $m) {
        if ($m === '') continue;
        if (filter_var($m, FILTER_VALIDATE_EMAIL) === false) throw new InvalidArgumentException("$was: „" . mb_substr($m, 0, 60) . '“ ist keine gültige E-Mail-Adresse.');
        if (!in_array($m, $ok, true)) $ok[] = $m;
    }
    return implode(', ', $ok);
}
/* Frist: Eingang + Tage (Kalendertage) */
function lg_frist(string $eingang, int $tage): string
{
    if ($eingang === '' || $tage <= 0) return '';
    return (new DateTimeImmutable($eingang . ' 12:00:00', new DateTimeZone('UTC')))->modify('+' . $tage . ' days')->format('Y-m-d');
}

/* ---------- Stammdaten: Lademittel und Partner ---------- */
function lg_lademittel_pruefen($v, array $alt): array
{
    if (!is_array($v) || !$v) throw new InvalidArgumentException('Lademittel: mindestens ein Eintrag.');
    if (count($v) > LG_MAX_LADEMITTEL) throw new InvalidArgumentException('Lademittel: höchstens ' . LG_MAX_LADEMITTEL . ' Einträge.');
    $altNach = []; foreach ($alt as $a) if (is_array($a) && isset($a['id'])) $altNach[(string)$a['id']] = $a;
    $out = []; $ids = [];
    foreach (array_values($v) as $i => $x) {
        if (!is_array($x)) throw new InvalidArgumentException('Lademittel: ungültige Angaben.');
        $name = lg_text($x['name'] ?? '', 40, 'Lademittel ' . ($i + 1));
        if ($name === '') throw new InvalidArgumentException('Lademittel ' . ($i + 1) . ': bitte einen Namen angeben.');
        $id = is_string($x['id'] ?? null) ? trim($x['id']) : '';
        if ($id === '' || !preg_match('/^[a-z0-9]{1,16}$/', $id)) {
            $basis = substr(preg_replace('/[^a-z0-9]+/', '', strtr(mb_strtolower($name), ['ä' => 'ae', 'ö' => 'oe', 'ü' => 'ue', 'ß' => 'ss'])) ?: 'lm', 0, 12); $id = $basis; $n = 2;
            while (in_array($id, $ids, true) || isset($altNach[$id])) $id = $basis . $n++;
        }
        if (in_array($id, $ids, true)) throw new InvalidArgumentException("Lademittel „{$name}“ ist doppelt.");
        $ids[] = $id;
        $row = $altNach[$id] ?? [];
        $row['id'] = $id; $row['name'] = $name; $row['wert'] = lg_betrag($x['wert'] ?? null, "Wert „{$name}“");
        $row['aktiv'] = !array_key_exists('aktiv', $x) || !empty($x['aktiv']);
        $out[] = $row;
    }
    // Entfernen würde Buchungen unlesbar machen: nicht mehr genutzte Lademittel werden deaktiviert, nicht gelöscht
    foreach ($altNach as $id => $a) if (!in_array($id, $ids, true)) throw new InvalidArgumentException('Lademittel „' . ($a['name'] ?? $id) . '“ kann nicht entfernt werden – bitte deaktivieren.');
    return $out;
}
function lg_partner_pruefen(array $b, ?array $alt, array $stamm): array
{
    $row = $alt ?? [];
    $row['name'] = lg_text($b['name'] ?? '', 100, 'Name');
    if ($row['name'] === '') throw new InvalidArgumentException('Bitte einen Namen für den Partner angeben.');
    foreach ($stamm['partner'] as $p) if (($alt === null || $p['id'] !== $alt['id']) && mb_strtolower((string)$p['name']) === mb_strtolower($row['name']))
        throw new InvalidArgumentException("Einen Partner „{$row['name']}“ gibt es schon.");
    $row['art'] = lg_wahl($b['art'] ?? 'lieferant', array_keys(LG_ARTEN), 'Art');
    $row['mandant'] = lg_wahl($b['mandant'] ?? 'standard', array_keys(LG_MANDANTEN), 'Firma');
    $row['kontoNr'] = lg_text($b['kontoNr'] ?? '', 40, 'Konto-Nr. beim Partner');
    if (array_key_exists('kundenNr', $b) || !isset($row['kundenNr'])) {   // ohne Angabe bleibt die gespeicherte Nummer
        $nr = lg_text($b['kundenNr'] ?? '', 12, 'WinAB-Kundennummer');
        if ($nr !== '' && !preg_match('/^\d{1,12}$/', $nr)) throw new InvalidArgumentException('WinAB-Kundennummer: bitte nur Ziffern.');
        foreach ($stamm['partner'] as $p) if ($nr !== '' && ($alt === null || $p['id'] !== $alt['id']) && (string)($p['kundenNr'] ?? '') === $nr)
            throw new InvalidArgumentException("Die WinAB-Kundennummer $nr gehört schon zu „{$p['name']}“.");
        $row['kundenNr'] = $nr;
    }
    $frist = $b['fristTage'] ?? LG_FRIST_STANDARD;
    $row['fristTage'] = ($frist === '' || $frist === null) ? 0 : lg_ganz($frist, 'Frist', false);
    if ($row['fristTage'] > 90) throw new InvalidArgumentException('Frist: höchstens 90 Tage.');
    $row['email'] = lg_email($b['email'] ?? '', 'E-Mail für die Abstimmung');
    $row['ansprechpartner'] = lg_text($b['ansprechpartner'] ?? '', 200, 'Ansprechpartner');
    $row['lieferanten'] = lg_text($b['lieferanten'] ?? '', 300, 'Lieferanten über dieses Konto');
    $row['notiz'] = lg_text($b['notiz'] ?? '', 2000, 'Notiz');
    $lm = lg_ids($stamm['lademittel']);
    $row['lademittel'] = [];
    foreach ((array)($b['lademittel'] ?? ['e2', 'h1']) as $x) { $x = lg_wahl($x, $lm, 'Lademittel'); if (!in_array($x, $row['lademittel'], true)) $row['lademittel'][] = $x; }
    if (!$row['lademittel']) throw new InvalidArgumentException('Bitte mindestens ein Lademittel wählen.');
    $row['aktiv'] = !array_key_exists('aktiv', $b) || !empty($b['aktiv']);
    return $row;
}
function lg_partner_finden(array $stamm, $id): array
{
    $id = is_string($id) ? $id : '';
    foreach ($stamm['partner'] as $p) if (($p['id'] ?? '') === $id && $id !== '') return $p;
    fail('Partner nicht gefunden.', 404);
    return [];
}

/* ---------- Bewegungen ---------- */
function lg_bewegung_pruefen(array $b, array $stamm): array
{
    $p = lg_partner_finden($stamm, $b['partner'] ?? '');
    $lm = lg_ids($stamm['lademittel']);
    $row = ['partner' => $p['id'], 'datum' => lg_datum($b['datum'] ?? '', 'Datum'), 'typ' => lg_wahl($b['typ'] ?? 'bewegung', array_keys(LG_TYPEN), 'Art der Buchung'),
            'abgang' => lg_mengen($b['abgang'] ?? [], $lm, 'Abgang', false), 'zugang' => lg_mengen($b['zugang'] ?? [], $lm, 'Zugang', false),
            'beleg' => lg_text($b['beleg'] ?? '', 80, 'Beleg-Nr.'), 'text' => lg_text($b['text'] ?? '', 500, 'Text')];
    if (!$row['abgang'] && !$row['zugang']) throw new InvalidArgumentException('Bitte mindestens eine Menge bei Abgang oder Zugang eintragen.');
    return $row;
}
/* Saldo einer Bewegung je Lademittel (+ Abgang, − Zugang) */
function lg_delta(array $b): array
{
    $d = [];
    foreach ((array)($b['abgang'] ?? []) as $k => $n) $d[$k] = ($d[$k] ?? 0) + (int)$n;
    foreach ((array)($b['zugang'] ?? []) as $k => $n) $d[$k] = ($d[$k] ?? 0) - (int)$n;
    return $d;
}
function lg_addiere(array &$s, array $d): void { foreach ($d as $k => $n) $s[$k] = ($s[$k] ?? 0) + $n; }
function lg_ohne_null(array $s): array { return array_filter($s, function ($n) { return $n !== 0; }); }
/* Bewegungen je Partner nach Datum (ohne stornierte) */
function lg_nach_partner(array $bewegungen): array
{
    $p = [];
    foreach ($bewegungen as $b) if (empty($b['storno'])) $p[(string)$b['partner']][] = $b;
    foreach ($p as &$l) usort($l, function ($a, $b) { return strcmp($a['datum'], $b['datum']); });
    return $p;
}
/* Saldo eines Partners bis einschließlich Stichtag ('' = alle) */
function lg_saldo_bis(array $liste, string $stichtag): array
{
    $s = [];
    foreach ($liste as $b) { if ($stichtag !== '' && $b['datum'] > $stichtag) break; lg_addiere($s, lg_delta($b)); }
    return lg_ohne_null($s);
}
function lg_minus(array $a, array $b): array
{
    $d = $a;
    foreach ($b as $k => $n) $d[$k] = ($d[$k] ?? 0) - $n;
    return lg_ohne_null($d);
}

/* ---------- Abstimmungen ---------- */
function lg_abstimmung_pruefen(array $b, ?array $alt, array $stamm): array
{
    $row = $alt ?? [];
    $p = lg_partner_finden($stamm, $b['partner'] ?? ($alt['partner'] ?? ''));
    $row['partner'] = $p['id'];
    $row['stichtag'] = lg_datum($b['stichtag'] ?? '', 'Stichtag');
    $row['eingang'] = lg_datum($b['eingang'] ?? '', 'Eingang', false);
    if ($row['eingang'] !== '' && $row['eingang'] < $row['stichtag']) throw new InvalidArgumentException('Der Eingang liegt vor dem Stichtag.');
    $row['fristBis'] = array_key_exists('fristBis', $b) && $b['fristBis'] !== '' && $b['fristBis'] !== null
        ? lg_datum($b['fristBis'], 'Frist bis') : lg_frist($row['eingang'], (int)($p['fristTage'] ?? 0));
    $row['saldo'] = lg_mengen($b['saldo'] ?? [], lg_ids($stamm['lademittel']), 'Saldo laut Partner', true);
    $row['status'] = lg_wahl($b['status'] ?? 'offen', array_keys(LG_ABST_STATUS), 'Status');
    $row['quelle'] = lg_text($b['quelle'] ?? '', 200, 'Quelle');
    $row['notiz'] = lg_text($b['notiz'] ?? '', 4000, 'Notiz');
    return $row;
}
/* Abstimmung für die Oberfläche: unser Saldo zum Stichtag (heute gerechnet), Differenz, Fristampel */
function lg_abstimmung_aus(array $a, array $nachPartner, string $heute): array
{
    $a += ['eingang' => '', 'fristBis' => '', 'saldo' => [], 'status' => 'offen', 'quelle' => '', 'notiz' => '', 'verlauf' => [], 'rev' => 0];
    $eigen = lg_saldo_bis($nachPartner[$a['partner']] ?? [], $a['stichtag']);
    $a['eigenJetzt'] = $eigen;
    $a['differenz'] = lg_minus((array)$a['saldo'], $eigen);
    $a['ampel'] = '';
    if ($a['status'] === 'offen' && $a['fristBis'] !== '') {
        $tage = (int)floor((strtotime($a['fristBis'] . ' 12:00:00 UTC') - strtotime($heute . ' 12:00:00 UTC')) / 86400);
        $a['restTage'] = $tage;
        $a['ampel'] = $tage < 0 ? 'rot' : ($tage <= 3 ? 'gelb' : 'gruen');
    }
    return $a;
}

/* ---------- Konten (Übersicht je Partner) ---------- */
function lg_konten(array $stamm, array $bewegungen, array $abstimmungen, string $heute): array
{
    $np = lg_nach_partner($bewegungen);
    $abstNach = [];
    foreach ($abstimmungen as $a) $abstNach[(string)$a['partner']][] = $a;
    $out = [];
    foreach ($stamm['partner'] as $p) {
        $l = $np[$p['id']] ?? [];
        $gesamt = lg_saldo_bis($l, '');
        $abst = $abstNach[$p['id']] ?? [];
        usort($abst, function ($a, $b) { return strcmp($a['stichtag'], $b['stichtag']); });
        $bestaetigt = null; $letzte = null; $offen = 0; $ueberfaellig = 0;
        foreach ($abst as $a) {
            $letzte = $a;
            if (($a['status'] ?? '') === 'bestaetigt') $bestaetigt = $a;
            if (($a['status'] ?? '') === 'offen') { $offen++; if (($a['fristBis'] ?? '') !== '' && $a['fristBis'] < $heute) $ueberfaellig++; }
        }
        $bestSaldo = $bestaetigt ? lg_saldo_bis($l, $bestaetigt['stichtag']) : [];
        $partnerSaldo = $letzte ? (array)($letzte['saldo'] ?? []) : null;
        // Lieferung und Rückgabe (ohne Anfangsbestand und Korrektur): erste/letzte Abgabe, letzte Rückgabe
        $ersteAbgabe = ''; $letzteAbgabe = ''; $letzteRueckgabe = '';
        foreach ($l as $b) {
            if (in_array($b['typ'] ?? 'bewegung', ['anfang', 'korrektur'], true)) continue;
            if (!empty($b['abgang'])) { if ($ersteAbgabe === '') $ersteAbgabe = $b['datum']; $letzteAbgabe = $b['datum']; }
            if (!empty($b['zugang'])) $letzteRueckgabe = $b['datum'];
        }
        $wb = is_array($p['winab'] ?? null) ? $p['winab'] : [];   // laut WinAB-Bericht, auch aus reinem Tausch
        // WinAB-Buchungen ohne diese Angaben (übernommen vor 30.10.2026): reiner Tausch fehlt, die letzte Rückgabe ist unbekannt
        $rueckgabeUnbekannt = ($wb['bis'] ?? '') === '' && (bool)array_filter($l, function ($b) { return ($b['quelle'] ?? '') === 'winab'; });
        if (($wb['ersteLieferung'] ?? '') !== '' && ($ersteAbgabe === '' || $wb['ersteLieferung'] < $ersteAbgabe)) $ersteAbgabe = $wb['ersteLieferung'];
        if (($wb['letzteLieferung'] ?? '') > $letzteAbgabe) $letzteAbgabe = $wb['letzteLieferung'];
        if (($wb['letzteRueckgabe'] ?? '') > $letzteRueckgabe) $letzteRueckgabe = $wb['letzteRueckgabe'];
        $out[] = ['id' => $p['id'], 'saldo' => $gesamt, 'bestaetigt' => $bestaetigt ? ['stichtag' => $bestaetigt['stichtag'], 'saldo' => $bestSaldo] : null,
                  'offenSeitBestaetigung' => lg_minus($gesamt, $bestSaldo),
                  'letzteBewegung' => $l ? end($l)['datum'] : '', 'bewegungen' => count($l),
                  'letzteAbstimmung' => $letzte ? ['id' => $letzte['id'], 'stichtag' => $letzte['stichtag'], 'status' => $letzte['status'] ?? 'offen', 'saldo' => $partnerSaldo,
                                                   'differenz' => lg_minus((array)$partnerSaldo, lg_saldo_bis($l, $letzte['stichtag']))] : null,
                  'abstimmungenOffen' => $offen, 'ueberfaellig' => $ueberfaellig,
                  'ersteAbgabe' => $ersteAbgabe, 'letzteAbgabe' => $letzteAbgabe, 'letzteRueckgabe' => $letzteRueckgabe, 'rueckgabeUnbekannt' => $rueckgabeUnbekannt];
    }
    return $out;
}

/* ---------- Abschreibungen (Dachser „lt. Empfänger“) ---------- */
function lg_abschreibung_pruefen(array $b, ?array $alt, array $stamm): array
{
    $row = $alt ?? [];
    $row['zugestellt'] = lg_datum($b['zugestellt'] ?? '', 'Zustelldatum');
    $row['auftrag'] = lg_datum($b['auftrag'] ?? '', 'Auftragsdatum', false);
    $row['empfaenger'] = lg_text($b['empfaenger'] ?? '', 120, 'Empfänger');
    if ($row['empfaenger'] === '') throw new InvalidArgumentException('Bitte den Empfänger (Kunden) angeben.');
    $row['empfaengerNr'] = lg_text($b['empfaengerNr'] ?? '', 30, 'Empfänger-Nr.');
    $row['ort'] = lg_text($b['ort'] ?? '', 80, 'Ort');
    $row['sendung'] = lg_text($b['sendung'] ?? '', 40, 'Sendungsnummer');
    $row['menge'] = lg_mengen($b['menge'] ?? [], lg_ids($stamm['lademittel']), 'Menge', false);
    if (!$row['menge']) throw new InvalidArgumentException('Bitte mindestens eine Menge eintragen.');
    $row['grund'] = lg_text($b['grund'] ?? '', 120, 'Grund');
    $row['status'] = lg_wahl($b['status'] ?? 'offen', array_keys(LG_ABSCHR_STATUS), 'Status');
    $row['rechnung'] = lg_text($b['rechnung'] ?? '', 60, 'WinAB-Auftrag / Rechnung');
    $row['notiz'] = lg_text($b['notiz'] ?? '', 2000, 'Notiz');
    return $row;
}

/* ---------- Inventur ---------- */
function lg_inventur_pruefen(array $b, ?array $alt, array $stamm): array
{
    $row = $alt ?? [];
    $row['stichtag'] = lg_datum($b['stichtag'] ?? '', 'Stichtag');
    $lm = lg_ids($stamm['lademittel']);
    if (!is_array($b['positionen'] ?? null) || !$b['positionen'] || count($b['positionen']) > 12) throw new InvalidArgumentException('Inventur: 1 bis 12 Positionen.');
    $row['positionen'] = [];
    foreach (array_values($b['positionen']) as $i => $x) {
        if (!is_array($x)) throw new InvalidArgumentException('Inventur: ungültige Angaben.');
        $name = lg_text($x['name'] ?? '', 60, 'Position ' . ($i + 1));
        if ($name === '') throw new InvalidArgumentException('Position ' . ($i + 1) . ': bitte eine Bezeichnung angeben.');
        $row['positionen'][] = ['name' => $name, 'werte' => lg_mengen($x['werte'] ?? [], $lm, $name, false)];
    }
    $row['notiz'] = lg_text($b['notiz'] ?? '', 2000, 'Notiz');
    return $row;
}

/* ---------- Bilanz zum Stichtag ---------- */
function lg_bilanz(string $stichtag, array $stamm, array $bewegungen, array $abstimmungen, array $inventur): array
{
    $np = lg_nach_partner($bewegungen);
    $zeilen = []; $summe = []; $jeMandant = [];
    foreach ($stamm['partner'] as $p) {
        $s = lg_saldo_bis($np[$p['id']] ?? [], $stichtag);
        $letzte = null;
        foreach ($abstimmungen as $a) if ($a['partner'] === $p['id'] && $a['stichtag'] <= $stichtag && (!$letzte || $a['stichtag'] >= $letzte['stichtag'])) $letzte = $a;
        if (!$s && !$letzte && empty($p['aktiv'])) continue;
        $zeilen[] = ['partner' => $p['id'], 'name' => $p['name'], 'art' => $p['art'], 'mandant' => $p['mandant'], 'saldo' => $s,
                     'abstimmung' => $letzte ? ['stichtag' => $letzte['stichtag'], 'status' => $letzte['status'] ?? 'offen'] : null];
        lg_addiere($summe, $s);
        $jeMandant[$p['mandant']] = $jeMandant[$p['mandant']] ?? [];
        lg_addiere($jeMandant[$p['mandant']], $s);
    }
    $inv = null;
    foreach ($inventur as $i) if ($i['stichtag'] <= $stichtag && (!$inv || $i['stichtag'] >= $inv['stichtag'])) $inv = $i;
    $bestand = [];
    if ($inv) foreach ($inv['positionen'] as $pos) lg_addiere($bestand, (array)$pos['werte']);
    $werte = []; foreach ($stamm['lademittel'] as $l) $werte[$l['id']] = $l['wert'] ?? null;
    $euro = function (array $s) use ($werte) { $e = 0.0; $voll = true; foreach ($s as $k => $n) { if ($werte[$k] === null) { $voll = false; continue; } $e += $n * $werte[$k]; } return ['betrag' => round($e, 2), 'vollstaendig' => $voll]; };
    foreach ($zeilen as &$z) $z['euro'] = $euro($z['saldo']);
    unset($z);
    $gesamt = $summe; lg_addiere($gesamt, $bestand);
    return ['stichtag' => $stichtag, 'zeilen' => $zeilen, 'summe' => lg_ohne_null($summe), 'jeMandant' => array_map('lg_ohne_null', $jeMandant), 'inventur' => $inv,
            'bestand' => lg_ohne_null($bestand), 'gesamt' => lg_ohne_null($gesamt), 'euro' => ['konten' => $euro($summe), 'bestand' => $euro($bestand), 'gesamt' => $euro($gesamt)]];
}

/* ---------- CSV (Excel) ---------- */
function lg_csv_zelle($v): string
{
    $s = (string)$v;
    if ($s !== '' && strpbrk($s[0], '=+-@') !== false && !preg_match('/^-?\d+([.,]\d+)?$/', $s)) $s = "'" . $s;   // keine Formeln (CSV-Injection), Zahlen bleiben Zahlen
    return '"' . str_replace('"', '""', str_replace(["\r", "\n"], ' ', $s)) . '"';
}
function lg_csv_bilanz(array $bil, array $stamm): string
{
    $lm = $stamm['lademittel'];
    $kopf = array_merge(['Firma', 'Partner', 'Art'], array_map(function ($l) { return $l['name']; }, $lm), ['Wert €', 'Letzte Abstimmung', 'Status']);
    $z = [implode(';', array_map('lg_csv_zelle', $kopf))];
    $zahl = function ($n) { return $n === null ? '' : (string)$n; };
    foreach ($bil['zeilen'] as $r) {
        $row = [LG_MANDANTEN[$r['mandant']] ?? $r['mandant'], $r['name'], LG_ARTEN[$r['art']] ?? $r['art']];
        foreach ($lm as $l) $row[] = $zahl($r['saldo'][$l['id']] ?? null);
        $row[] = number_format($r['euro']['betrag'], 2, ',', '');
        $row[] = $r['abstimmung'] ? $r['abstimmung']['stichtag'] : '';
        $row[] = $r['abstimmung'] ? (LG_ABST_STATUS[$r['abstimmung']['status']] ?? '') : '';
        $z[] = implode(';', array_map('lg_csv_zelle', $row));
    }
    $sum = function (string $name, array $s, array $e) use ($lm, $zahl) {
        $row = ['', $name, ''];
        foreach ($lm as $l) $row[] = $zahl($s[$l['id']] ?? null);
        $row[] = number_format($e['betrag'], 2, ',', ''); $row[] = ''; $row[] = '';
        return implode(';', array_map('lg_csv_zelle', $row));
    };
    $z[] = $sum('Summe Konten', $bil['summe'], $bil['euro']['konten']);
    if ($bil['inventur']) $z[] = $sum('Eigener Bestand (Inventur ' . $bil['inventur']['stichtag'] . ')', $bil['bestand'], $bil['euro']['bestand']);
    $z[] = $sum('Gesamt', $bil['gesamt'], $bil['euro']['gesamt']);
    return "\xEF\xBB\xBF" . implode("\r\n", $z) . "\r\n";
}

/* „Leergut bei Kunden“ (Abholliste): Konten der Art Kunde mit Saldo, nach Wert absteigend. „Ohne Rückgabe seit“ zählt
   nur, wenn der Kunde uns etwas schuldet: Tage seit der letzten Rückgabe, ohne Rückgabe seit der ersten Lieferung;
   leer, wenn die letzte Rückgabe unbekannt ist (WinAB-Buchungen ohne Angaben aus dem Bericht). */
function lg_kunden_leergut(array $stamm, array $bewegungen, string $heute): array
{
    $werte = []; foreach ($stamm['lademittel'] as $l) $werte[$l['id']] = $l['wert'] ?? null;
    $konten = []; foreach (lg_konten($stamm, $bewegungen, [], $heute) as $k) $konten[$k['id']] = $k;
    $zeilen = [];
    foreach ($stamm['partner'] as $p) {
        $k = $konten[$p['id']];
        if ($p['art'] !== 'kunde' || !$k['saldo']) continue;
        $e = 0.0; $voll = true; $stueck = 0;
        foreach ($k['saldo'] as $id => $n) { if ($n > 0) $stueck += $n; if (($werte[$id] ?? null) === null) { $voll = false; continue; } $e += $n * $werte[$id]; }
        $seit = $stueck > 0 && !$k['rueckgabeUnbekannt'] ? ($k['letzteRueckgabe'] !== '' ? $k['letzteRueckgabe'] : $k['ersteAbgabe']) : '';
        $tage = $seit !== '' ? max(0, (int)round((strtotime($heute . ' 12:00:00 UTC') - strtotime($seit . ' 12:00:00 UTC')) / 86400)) : null;
        $zeilen[] = ['partner' => $p['id'], 'name' => $p['name'], 'kundenNr' => (string)($p['kundenNr'] ?? ''), 'mandant' => $p['mandant'], 'saldo' => $k['saldo'],
                     'euro' => ['betrag' => round($e, 2), 'vollstaendig' => $voll], 'stueck' => $stueck, 'letzteAbgabe' => $k['letzteAbgabe'],
                     'letzteRueckgabe' => $k['rueckgabeUnbekannt'] ? '' : $k['letzteRueckgabe'], 'ohneRueckgabeSeit' => $seit, 'tage' => $tage];
    }
    usort($zeilen, function ($a, $b) { return [$b['euro']['betrag'], $b['stueck']] <=> [$a['euro']['betrag'], $a['stueck']] ?: strcmp(mb_strtolower($a['name']), mb_strtolower($b['name'])); });
    return $zeilen;
}
function lg_csv_kunden(array $zeilen, array $stamm): string
{
    $lm = array_values(array_filter($stamm['lademittel'], function ($l) use ($zeilen) { foreach ($zeilen as $z) if (!empty($z['saldo'][$l['id']])) return true; return false; }));
    $kopf = array_merge(['Kunde', 'WinAB-Kd.-Nr.', 'Firma'], array_map(function ($l) { return $l['name']; }, $lm), ['Wert €', 'Letzte Lieferung', 'Letzte Rückgabe', 'Ohne Rückgabe seit (Tage)']);
    $z = [implode(';', array_map('lg_csv_zelle', $kopf))];
    $tag = function (string $d) { return $d === '' ? '' : date('d.m.Y', strtotime($d . ' 12:00:00')); };
    foreach ($zeilen as $r) {
        $row = [$r['name'], $r['kundenNr'], LG_MANDANTEN[$r['mandant']] ?? $r['mandant']];
        foreach ($lm as $l) $row[] = isset($r['saldo'][$l['id']]) ? (string)$r['saldo'][$l['id']] : '';
        $row[] = number_format($r['euro']['betrag'], 2, ',', '');   // nur bewertete Lademittel (wie in der Bilanz)
        $row[] = $tag($r['letzteAbgabe']); $row[] = $tag($r['letzteRueckgabe']); $row[] = $r['tage'] === null ? '' : (string)$r['tage'];
        $z[] = implode(';', array_map('lg_csv_zelle', $row));
    }
    return "\xEF\xBB\xBF" . implode("\r\n", $z) . "\r\n";
}

/* ---------- Datenpaket (Übernahme der bisherigen Excel-Liste und der Partnerauszüge) ----------
   Format: { format: "stafl-leergut", version: 1, lademittel: [...], partner: [{ schluessel, name, … }],
             bewegungen: [{ partner: <schluessel>, datum, typ, abgang, zugang, beleg, text }], abstimmungen: [...],
             abschreibungen: [...], inventur: [...] }
   Prüft alles mit denselben Regeln wie die Eingabemasken; Fehler je Abschnitt und Zeile. */
function lg_paket_pruefen($p, array $me): array
{
    if (!is_array($p) || ($p['format'] ?? '') !== 'stafl-leergut' || (int)($p['version'] ?? 0) !== 1)
        throw new InvalidArgumentException('Das ist kein Leergut-Datenpaket (Format „stafl-leergut“, Version 1).');
    $fehler = [];
    $merke = function (string $teil, int $i, Throwable $e) use (&$fehler) { if (count($fehler) < 200) $fehler[] = ['teil' => $teil, 'zeile' => $i + 1, 'text' => $e->getMessage()]; };
    $stamm = ['rev' => 0, 'lademittel' => [], 'partner' => []];
    try { $stamm['lademittel'] = lg_lademittel_pruefen($p['lademittel'] ?? lg_grund_lademittel(), []); }
    catch (InvalidArgumentException $e) { $merke('lademittel', 0, $e); $stamm['lademittel'] = lg_grund_lademittel(); }
    $schl = [];
    foreach (array_values((array)($p['partner'] ?? [])) as $i => $x) {
        try {
            if (!is_array($x)) throw new InvalidArgumentException('ungültige Angaben');
            $k = lg_text($x['schluessel'] ?? '', 60, 'Schlüssel');
            if ($k === '' || isset($schl[$k])) throw new InvalidArgumentException('Schlüssel fehlt oder ist doppelt.');
            if (count($stamm['partner']) >= LG_MAX_PARTNER) throw new InvalidArgumentException('Zu viele Partner.');
            $row = lg_partner_pruefen($x, null, $stamm);
            $row = ['id' => lg_id('p')] + $row + ['erstellt' => lg_wer($me), 'quelle' => 'import'];
            $stamm['partner'][] = $row; $schl[$k] = $row['id'];
        } catch (InvalidArgumentException $e) { $merke('partner', $i, $e); }
    }
    $mitPartner = function ($x) use ($schl) { if (!is_array($x)) throw new InvalidArgumentException('ungültige Angaben'); $k = (string)($x['partner'] ?? ''); if (!isset($schl[$k])) throw new InvalidArgumentException("unbekannter Partner „" . mb_substr($k, 0, 40) . '“'); $x['partner'] = $schl[$k]; return $x; };
    $docs = ['bewegungen' => [], 'abstimmungen' => [], 'abschreibungen' => [], 'inventur' => []];
    $grenzen = ['bewegungen' => LG_MAX_BEWEGUNGEN, 'abstimmungen' => LG_MAX_ABSTIMMUNGEN, 'abschreibungen' => LG_MAX_ABSCHREIBUNGEN, 'inventur' => LG_MAX_INVENTUR];
    foreach ($grenzen as $teil => $max) if (count((array)($p[$teil] ?? [])) > $max) throw new InvalidArgumentException("Zu viele Einträge in „{$teil}“ (höchstens $max).");
    foreach (array_values((array)($p['bewegungen'] ?? [])) as $i => $x) {
        try {
            $x = $mitPartner($x);
            $row = lg_bewegung_pruefen($x, $stamm);
            $docs['bewegungen'][] = ['id' => lg_id('b')] + $row + ['quelle' => 'import', 'erfasst' => lg_wer($me), 'storno' => null];
        } catch (InvalidArgumentException $e) { $merke('bewegungen', $i, $e); }
    }
    foreach (array_values((array)($p['abstimmungen'] ?? [])) as $i => $x) {
        try {
            $x = $mitPartner($x);
            $row = lg_abstimmung_pruefen($x, null, $stamm);
            $row = ['id' => lg_id('a')] + $row + ['eigen' => null, 'erfasst' => lg_wer($me), 'herkunft' => 'import', 'verlauf' => [], 'rev' => 1];
            $docs['abstimmungen'][] = $row;
        } catch (InvalidArgumentException $e) { $merke('abstimmungen', $i, $e); }
    }
    foreach (array_values((array)($p['abschreibungen'] ?? [])) as $i => $x) {
        try {
            if (!is_array($x)) throw new InvalidArgumentException('ungültige Angaben');
            $row = lg_abschreibung_pruefen($x, null, $stamm);
            $docs['abschreibungen'][] = ['id' => lg_id('d')] + $row + ['erfasst' => lg_wer($me), 'verlauf' => [], 'rev' => 1];
        } catch (InvalidArgumentException $e) { $merke('abschreibungen', $i, $e); }
    }
    foreach (array_values((array)($p['inventur'] ?? [])) as $i => $x) {
        try {
            if (!is_array($x)) throw new InvalidArgumentException('ungültige Angaben');
            $docs['inventur'][] = ['id' => lg_id('i')] + lg_inventur_pruefen($x, null, $stamm) + ['erfasst' => lg_wer($me), 'rev' => 1];
        } catch (InvalidArgumentException $e) { $merke('inventur', $i, $e); }
    }
    // Schnappschuss unseres Saldos zum Stichtag jeder Abstimmung (wie beim Erfassen von Hand)
    $np = lg_nach_partner($docs['bewegungen']);
    foreach ($docs['abstimmungen'] as &$a) $a['eigen'] = lg_saldo_bis($np[$a['partner']] ?? [], $a['stichtag']);
    unset($a);
    $zahlen = ['lademittel' => count($stamm['lademittel']), 'partner' => count($stamm['partner'])];
    foreach ($docs as $k => $l) $zahlen[$k] = count($l);
    return ['stamm' => $stamm, 'docs' => $docs, 'zahlen' => $zahlen, 'fehler' => $fehler];
}

/* ---------- WinAB-Bericht „Lademittelbewegungen Kunden“ ----------
   Die Oberfläche liest den Bericht im Browser und schickt { bericht: {datei, von, bis, datum}, kunden: [{nr, name}],
   belege: [{kd, art, beleg, datum, abgang, zugang}] } – nur Lieferscheine, Gutschriften und Einzelrechnungen
   (Sammelrechnungen wiederholen die Lieferscheine), nur Lademittel des Moduls (Karton ist kein Leergut) und nur Belege,
   die den Saldo ändern (Abgang ≠ Zugang). Vorzeichen wie im Modul: Abgang = an den Kunden, Zugang = vom Kunden zurück.
   „bis“ ist das Berichtsdatum (der Bericht nennt sonst „bis 31.12.2078“). */
function lg_winab_pruefen($b, array $stamm): array
{
    $ber = is_array($b['bericht'] ?? null) ? $b['bericht'] : [];
    $von = lg_datum($ber['von'] ?? '', 'Zeitraum von');
    $bis = lg_datum($ber['bis'] ?? '', 'Zeitraum bis');
    if ($bis < $von) throw new InvalidArgumentException('Zeitraum: „bis“ liegt vor „von“.');
    $bericht = ['datei' => lg_text($ber['datei'] ?? '', 120, 'Datei'), 'von' => $von, 'bis' => $bis];
    $kunden = []; $daten = [];
    $kl = $b['kunden'] ?? [];
    if (!is_array($kl) || count($kl) > LG_MAX_WINAB_KUNDEN) throw new InvalidArgumentException('Kundenliste fehlt oder ist zu lang.');
    foreach (array_values($kl) as $i => $k) {
        $nr = is_array($k) ? (string)($k['nr'] ?? '') : '';
        if (!preg_match('/^\d{1,12}$/', $nr)) throw new InvalidArgumentException('Kunde ' . ($i + 1) . ': ungültige Kundennummer.');
        $name = lg_text($k['name'] ?? '', 100, 'Kundenname');
        $kunden[$nr] = $name !== '' ? $name : 'Kunde';
        $dt = [];   // Lieferung und Rückgabe laut Bericht (auch aus Belegen ohne Wirkung auf den Saldo)
        foreach (['ersteLieferung' => 'erste Lieferung', 'letzteLieferung' => 'letzte Lieferung', 'letzteRueckgabe' => 'letzte Rückgabe'] as $f => $was) {
            $d = lg_datum($k[$f] ?? '', "Kunde $nr: $was", false);
            if ($d !== '' && ($d < $von || $d > $bis)) throw new InvalidArgumentException("Kunde $nr: $was liegt außerhalb des Berichtszeitraums.");
            $dt[$f] = $d;
        }
        if (array_intersect_key($k, $dt)) $daten[$nr] = $dt;   // ältere Oberflächen schicken keine Angaben: dann nichts ändern
    }
    $bl = $b['belege'] ?? [];
    if (!is_array($bl) || count($bl) > LG_MAX_WINAB_BELEGE) throw new InvalidArgumentException('Belegliste fehlt oder ist zu lang (höchstens ' . LG_MAX_WINAB_BELEGE . ').');
    $lm = lg_ids($stamm['lademittel']);
    $belege = []; $fehler = []; $ohneWirkung = 0;
    foreach (array_values($bl) as $i => $x) {
        try {
            if (!is_array($x)) throw new InvalidArgumentException('ungültige Angaben');
            $kd = (string)($x['kd'] ?? '');
            if (!isset($kunden[$kd])) throw new InvalidArgumentException('Kundennummer „' . mb_substr($kd, 0, 20) . '“ fehlt in der Kundenliste');
            $art = lg_wahl($x['art'] ?? '', LG_WINAB_ARTEN, 'Belegart');
            $nr = lg_text(is_scalar($x['beleg'] ?? null) ? (string)$x['beleg'] : '', 30, 'Belegnr.');
            if ($nr === '') throw new InvalidArgumentException('Belegnr. fehlt');
            $datum = lg_datum($x['datum'] ?? '', 'Datum');
            if ($datum < $von || $datum > $bis) throw new InvalidArgumentException("Datum $datum liegt außerhalb des Berichtszeitraums");
            $ab = lg_mengen($x['abgang'] ?? [], $lm, 'Abgang', false);
            $zu = lg_mengen($x['zugang'] ?? [], $lm, 'Zugang', false);
            if (!lg_ohne_null(lg_delta(['abgang' => $ab, 'zugang' => $zu]))) { $ohneWirkung++; continue; }
            $key = "$kd|$art|$nr";
            if (isset($belege[$key])) throw new InvalidArgumentException("$art $nr ist doppelt");
            $belege[$key] = ['kd' => $kd, 'art' => $art, 'beleg' => $nr, 'datum' => $datum, 'abgang' => $ab, 'zugang' => $zu];
        } catch (InvalidArgumentException $e) { if (count($fehler) < 200) $fehler[] = ['zeile' => $i + 1, 'text' => $e->getMessage()]; }
    }
    return ['bericht' => $bericht, 'kunden' => $kunden, 'daten' => $daten, 'belege' => $belege, 'fehler' => $fehler, 'ohneWirkung' => $ohneWirkung];
}
/* Abgleich je Beleg (Kunde, Belegart, Belegnr.) im Berichtszeitraum: neu → buchen, gleich → nichts, geändert → alten
   stornieren und neu buchen, nicht mehr im Bericht (ausgeglichen) → stornieren. Bewegungen außerhalb des Zeitraums, von
   Kunden, die der Bericht nicht nennt, und von Hand gebuchte bleiben unberührt. Die Kundenliste enthält alle Kunden
   des Berichts, auch solche ohne saldowirksamen Beleg. Kunden ohne Konto bekommen eins (Art Kunde, Name mit Kundennummer). */
function lg_winab_abgleich(array $w, array $stamm, array $bew, array $me): array
{
    $heute = date('d.m.Y');
    $nachNr = [];
    foreach ($stamm['partner'] as $i => $p) if ((string)($p['kundenNr'] ?? '') !== '') $nachNr[(string)$p['kundenNr']] = $i;
    $namen = [];
    foreach ($stamm['partner'] as $p) $namen[mb_strtolower((string)$p['name'])] = true;
    $genutzt = [];
    foreach ($w['belege'] as $b) foreach (array_merge(array_keys($b['abgang']), array_keys($b['zugang'])) as $l) $genutzt[$b['kd']][$l] = true;
    $neuKunden = [];
    foreach (array_keys($genutzt) as $kd) {
        $kd = (string)$kd;
        if (isset($nachNr[$kd])) continue;
        $name = rtrim(mb_substr($w['kunden'][$kd], 0, 84)) . ' (' . $kd . ')';
        $basis = $name; $n = 2;
        while (isset($namen[mb_strtolower($name)])) $name = $basis . ' ' . $n++;
        $namen[mb_strtolower($name)] = true;
        $lms = array_values(array_filter(lg_ids($stamm['lademittel']), function ($l) use ($genutzt, $kd) { return isset($genutzt[$kd][$l]) || in_array($l, ['e2', 'h1'], true); }));
        $stamm['partner'][] = ['id' => lg_id('p'), 'name' => $name, 'art' => 'kunde', 'mandant' => 'standard', 'kontoNr' => '', 'kundenNr' => $kd,
            'fristTage' => 0, 'email' => '', 'ansprechpartner' => '', 'lieferanten' => '', 'lademittel' => $lms, 'aktiv' => true, 'quelle' => 'winab',
            'notiz' => 'Aus dem WinAB-Bericht „Lademittelbewegungen Kunden“ angelegt. Salden ab ' . date('d.m.Y', strtotime($w['bericht']['von'])) . ' – ältere Stände liegen in WinAB nicht vor.',
            'erstellt' => lg_wer($me), 'rev' => 1, 'geaendert' => lg_wer($me)];
        $nachNr[$kd] = count($stamm['partner']) - 1;
        $neuKunden[] = $name;
    }
    if (count($stamm['partner']) > LG_MAX_PARTNER) throw new InvalidArgumentException('Zu viele Partner (höchstens ' . LG_MAX_PARTNER . ').');
    $alt = [];
    foreach ($bew as $i => $b) {
        $k = $b['winab'] ?? null;
        if (($b['quelle'] ?? '') !== 'winab' || !empty($b['storno']) || !is_array($k)) continue;
        if ($b['datum'] < $w['bericht']['von'] || $b['datum'] > $w['bericht']['bis']) continue;
        if (!isset($w['kunden'][(string)$k['kd']])) continue;   // Kunde nicht im Bericht (z. B. auf einzelne Kunden gefiltert): nicht anfassen
        $alt[$k['kd'] . '|' . $k['art'] . '|' . $k['beleg']] = $i;
    }
    $z = ['kunden' => count($neuKunden), 'neu' => 0, 'gleich' => 0, 'geaendert' => 0, 'ausgeglichen' => 0, 'ohneWirkung' => $w['ohneWirkung']];
    $offenAb = date('Y-m-d', strtotime($w['bericht']['bis'] . ' 12:00:00 UTC') - 3 * 86400);
    foreach ($w['belege'] as $key => $b) {
        $pid = $stamm['partner'][$nachNr[$b['kd']]]['id'];
        if (isset($alt[$key])) {
            $i = $alt[$key]; unset($alt[$key]);
            $a = $bew[$i];
            if ($a['partner'] === $pid && $a['datum'] === $b['datum'] && (array)$a['abgang'] == $b['abgang'] && (array)$a['zugang'] == $b['zugang']) { $z['gleich']++; continue; }
            $bew[$i]['storno'] = lg_wer($me) + ['grund' => "WinAB-Abgleich vom $heute: Beleg geändert"];
            $z['geaendert']++;
        } else $z['neu']++;
        $text = 'Aus WinAB („Lademittelbewegungen Kunden“' . ($w['bericht']['datei'] !== '' ? ', ' . $w['bericht']['datei'] : '') . ')';
        if ($b['datum'] >= $offenAb && !$b['zugang']) $text .= ' – zum Berichtsdatum noch nicht zurück';
        $bew[] = ['id' => lg_id('b'), 'partner' => $pid, 'datum' => $b['datum'], 'typ' => $b['art'] === 'Gutschrift' ? 'abholung' : 'bewegung',
                  'abgang' => $b['abgang'], 'zugang' => $b['zugang'], 'beleg' => $b['art'] . ' ' . $b['beleg'], 'text' => $text,
                  'quelle' => 'winab', 'winab' => ['kd' => $b['kd'], 'art' => $b['art'], 'beleg' => $b['beleg']], 'erfasst' => lg_wer($me), 'storno' => null];
    }
    foreach ($alt as $i) { $bew[$i]['storno'] = lg_wer($me) + ['grund' => "WinAB-Abgleich vom $heute: Beleg ausgeglichen oder nicht mehr im Bericht"]; $z['ausgeglichen']++; }
    // Lieferung und Rückgabe laut Bericht am Kundenkonto (Feld winab). Frühere Berichte bleiben gültig: erste = früheste,
    // letzte = späteste Angabe. „daten“ zählt die Konten, deren Angaben sich ändern.
    $z['daten'] = 0;
    foreach ($w['daten'] ?? [] as $kd => $dt) {
        $kd = (string)$kd;
        if (!isset($nachNr[$kd])) continue;
        $i = $nachNr[$kd];
        $vorher = is_array($stamm['partner'][$i]['winab'] ?? null) ? $stamm['partner'][$i]['winab'] : [];
        $felder = [];
        foreach (['ersteLieferung', 'letzteLieferung', 'letzteRueckgabe'] as $f) {
            $a = (string)($vorher[$f] ?? ''); $n = (string)($dt[$f] ?? '');
            $felder[$f] = $n === '' ? $a : ($a === '' ? $n : ($f === 'ersteLieferung' ? min($a, $n) : max($a, $n)));
        }
        $alteFelder = array_map(function ($f) use ($vorher) { return (string)($vorher[$f] ?? ''); }, ['ersteLieferung' => 'ersteLieferung', 'letzteLieferung' => 'letzteLieferung', 'letzteRueckgabe' => 'letzteRueckgabe']);
        if ($felder !== $alteFelder) $z['daten']++;
        $nachher = $felder + ['bis' => max((string)($vorher['bis'] ?? ''), $w['bericht']['bis'])];
        if ($nachher !== $vorher) $stamm['partner'][$i]['winab'] = $nachher;
    }
    // Saldo aller Kundenkonten mit WinAB-Nummer nach dem Abgleich
    $kundenIds = [];
    foreach ($stamm['partner'] as $p) if ((string)($p['kundenNr'] ?? '') !== '') $kundenIds[$p['id']] = true;
    $summe = []; $mitSaldo = 0;
    foreach (lg_nach_partner($bew) as $pid => $l) {
        if (!isset($kundenIds[$pid])) continue;
        $s = lg_saldo_bis($l, '');
        if ($s) { $mitSaldo++; lg_addiere($summe, $s); }
    }
    $z['konten'] = $mitSaldo;
    return [$stamm, $bew, $z, $neuKunden, lg_ohne_null($summe)];
}

/* ---------- Dachser-Liste „Unterkonto-Vorspediteur“ (Mail „Infos von Fa. DACHSER“) ----------
   Dachser schickt monatlich die Abschreibungen „lt. Empfänger“ als Text: je Fall Auftragsdatum, Empfänger-Nr., Empfänger
   (20 Zeichen), Ort, Zustelldatum, Anzahl, Packmittel, Kennzeichen, Grund und Sendungsnummer; am Ende den Saldo je
   Packmittel „zu Gunsten DA“. Eingefügt wird der Text der Mail oder die gespeicherte Mail (.eml). */
const LG_MAX_DACHSER_TEXT = 2000000;

/* Text einer gespeicherten Mail (.eml): erster text/plain-Teil (sonst text/html ohne Auszeichnung), Transfer-Kodierung
   und Zeichensatz aufgelöst. Ohne Mailkopf (eingefügter Text) bleibt der Text unverändert. */
function lg_mail_text(string $roh, int $tiefe = 0): string
{
    $roh = str_replace("\r\n", "\n", $roh);
    $teile = explode("\n\n", $roh, 2);
    if ($tiefe > 6 || count($teile) < 2 || !preg_match('/^(mime-version|content-type)\s*:/im', $teile[0])) return $roh;
    $kopf = preg_replace("/\n[ \t]+/", ' ', $teile[0]);
    $feld = function (string $n) use ($kopf) { return preg_match('/^' . $n . '\s*:\s*(.*)$/im', $kopf, $m) ? trim($m[1]) : ''; };
    $typ = $feld('content-type');
    $rumpf = $teile[1];
    if (preg_match('/^multipart\//i', $typ) && preg_match('/boundary\s*=\s*"?([^";\s]+)"?/i', $typ, $b)) {
        $html = '';
        foreach (array_slice(explode('--' . $b[1], $rumpf), 1) as $teil) {
            if (strncmp($teil, '--', 2) === 0) break;
            $teil = ltrim($teil, "\n");
            $t = lg_mail_text(preg_match('/^(mime-version|content-type)\s*:/im', explode("\n\n", $teil, 2)[0]) ? $teil : "Content-Type: text/plain\n\n" . $teil, $tiefe + 1);
            if (preg_match('/^content-type\s*:\s*text\/html/im', explode("\n\n", $teil, 2)[0])) { if ($html === '') $html = $t; continue; }
            if (trim($t) !== '' && !preg_match('/^content-type\s*:\s*(image|application)\//im', explode("\n\n", $teil, 2)[0])) return $t;
        }
        return $html;
    }
    $kod = strtolower($feld('content-transfer-encoding'));
    if ($kod === 'quoted-printable') $rumpf = quoted_printable_decode(str_replace("\n", "\r\n", $rumpf));
    elseif ($kod === 'base64') $rumpf = (string)base64_decode(preg_replace('/\s+/', '', $rumpf));
    $rumpf = str_replace("\r\n", "\n", $rumpf);
    $cs = preg_match('/charset\s*=\s*"?([A-Za-z0-9_\-:.]+)"?/i', $typ, $c) ? strtoupper($c[1]) : '';
    if ($cs !== '' && $cs !== 'UTF-8' && $cs !== 'US-ASCII') {
        try { $rumpf = mb_convert_encoding($rumpf, 'UTF-8', $cs === 'ISO-8859-1' ? 'Windows-1252' : $cs); } catch (Throwable $e) { /* unbekannter Zeichensatz: wie geliefert */ }
    }
    if (!mb_check_encoding($rumpf, 'UTF-8')) $rumpf = mb_convert_encoding($rumpf, 'UTF-8', 'Windows-1252');
    if (preg_match('/^text\/html/i', $typ)) $rumpf = html_entity_decode(strip_tags(preg_replace('/<br\s*\/?>|<\/(p|div|tr)>/i', "\n", $rumpf)), ENT_QUOTES | ENT_HTML5, 'UTF-8');
    return $rumpf;
}

/* Datum „1.09.26“ / „30.09.2026“ → ISO */
function lg_dachser_datum(string $d): string
{
    if (!preg_match('/^(\d{1,2})\.(\d{1,2})\.(\d{2}|\d{4})$/', $d, $m)) return '';
    $j = strlen($m[3]) === 2 ? 2000 + (int)$m[3] : (int)$m[3];
    return checkdate((int)$m[2], (int)$m[1], $j) ? sprintf('%04d-%02d-%02d', $j, $m[2], $m[1]) : '';
}

/* Liest die Liste: Fälle je Zeile, Stichtag(e), Saldo laut Dachser; Zeilen, die wie ein Fall aussehen, aber nicht lesbar
   sind, kommen als Fehler zurück. Packmittel ohne Lademittel im Modul (z. B. Gitterbox) werden gezählt, nicht übernommen. */
function lg_dachser_lesen(string $text, array $stamm): array
{
    $lm = lg_ids($stamm['lademittel']);
    $pm = function (string $code) use ($lm, $stamm) {
        $c = strtolower($code);
        if (in_array($c, $lm, true)) return $c;
        foreach (['eu' => ['eu', 'ep', 'fp'], 'e2' => ['e2'], 'h1' => ['h1'], 'e1' => ['e1']] as $id => $codes) if (in_array($c, $codes, true) && in_array($id, $lm, true)) return $id;
        return '';
    };
    $zeilen = []; $fehler = []; $unbekannt = []; $saldo = []; $per = []; $konto = '';
    $auftrag = ''; $empf = null; $imSaldo = false; $erwarteEmpf = false;
    foreach (explode("\n", str_replace(["\r", "\f"], ['', ''], $text)) as $i => $z) {
        if (preg_match('/Unterkonto-Vorspediteur\s+(\S+)/u', $z, $m)) { $konto = $m[1]; $imSaldo = false; continue; }
        if (preg_match('/^\s*per\s+(\d{1,2}\.\d{2}\.\d{2,4})\b/u', $z, $m)) { $d = lg_dachser_datum($m[1]); if ($d !== '') $per[$d] = true; continue; }
        if (preg_match('/Unterkonto\s+Saldo\s+per\s+(\d{1,2}\.\d{2}\.\d{2,4})/u', $z, $m)) { $imSaldo = true; $d = lg_dachser_datum($m[1]); if ($d !== '') $per[$d] = true; continue; }
        if ($imSaldo && preg_match('/^\s*([A-Z0-9]{2,3})\s+(-?\d+)\s+zu\s+Gunsten\s+(\S+)/u', $z, $m)) {
            $id = $pm($m[1]); $n = (int)$m[2] * (stripos($m[3], 'DA') === 0 ? 1 : -1);
            if ($id !== '') $saldo[$id] = ($saldo[$id] ?? 0) + $n;   // Packmittel ohne Lademittel: schon bei den Fällen gezählt
            continue;
        }
        if (preg_match('/^\s*(\d{1,2}\.\d{2}\.\d{2})\s+(-?\d{1,5})\s+([A-Z0-9]{2,3})\s+([A-Z0-9])\s+(.+?)\s+(\d{8,14})\s*$/u', $z, $m)) {
            $zug = lg_dachser_datum($m[1]);
            if ($zug === '') { if (count($fehler) < 50) $fehler[] = ['zeile' => $i + 1, 'text' => 'Zustelldatum „' . $m[1] . '“ nicht lesbar']; continue; }
            if ($empf === null) { if (count($fehler) < 50) $fehler[] = ['zeile' => $i + 1, 'text' => 'Fall ohne Empfänger (Sendung ' . $m[6] . ')']; continue; }
            $id = $pm($m[3]);
            if ($id === '') { $unbekannt[$m[3]] = ($unbekannt[$m[3]] ?? 0) + 1; continue; }
            $zeilen[] = ['auftrag' => $auftrag, 'zugestellt' => $zug, 'empfaengerNr' => $empf['nr'], 'empfaenger' => $empf['name'], 'ort' => $empf['ort'],
                         'lm' => $id, 'menge' => (int)$m[2], 'kz' => $m[4], 'grund' => trim($m[5]), 'sendung' => $m[6]];
            continue;
        }
        if (preg_match('/^\s*(\d{1,2}\.\d{2}\.\d{2})\s+(\d{5,10})\s+\S/u', $z, $m)) { $auftrag = lg_dachser_datum($m[1]); $empf = null; $erwarteEmpf = true; continue; }
        if ($erwarteEmpf && preg_match('/^\s{4,}(\d{5,10})\s+(\S.*)$/u', $z, $m)) {   // Empfänger: die Zeile direkt nach dem Absender
            $erwarteEmpf = false;
            $t = preg_split('/\s{2,}/u', trim($m[2]));
            $schoen = function (string $s) { return preg_match('/\p{Ll}/u', $s) ? $s : mb_convert_case(mb_strtolower($s), MB_CASE_TITLE, 'UTF-8'); };
            $empf = ['nr' => $m[1], 'name' => $schoen(trim($t[0])), 'ort' => $schoen(trim(implode(' ', array_slice($t, 1))))];
        }
    }
    ksort($per);
    return ['konto' => $konto, 'per' => $per ? array_key_last($per) : '', 'zeilen' => $zeilen, 'saldo' => lg_ohne_null($saldo), 'unbekannt' => $unbekannt, 'fehler' => $fehler];
}

/* Abgleich mit den erfassten Abschreibungen über die Sendungsnummer: je Sendung ein Fall (Mengen je Lademittel addiert).
   Neu → anlegen (REWE nur mit H1: „Nicht zu beachten“ laut Leitfaden); Lademittel schon erfasst → nichts (abweichende
   Menge wird gemeldet, nicht geändert); fehlt einem offenen Fall ein Lademittel → ergänzen (mit Verlauf), sonst neuer Fall. */
function lg_dachser_abgleich(array $l, array $liste, array $me): array
{
    $gruppen = [];
    foreach ($l['zeilen'] as $z) {
        $g = &$gruppen[$z['sendung']];
        if (!$g) $g = ['zugestellt' => $z['zugestellt'], 'auftrag' => $z['auftrag'], 'empfaenger' => $z['empfaenger'], 'empfaengerNr' => $z['empfaengerNr'],
                       'ort' => $z['ort'], 'sendung' => $z['sendung'], 'menge' => [], 'kz' => [], 'grund' => $z['grund']];
        $g['menge'][$z['lm']] = ($g['menge'][$z['lm']] ?? 0) + $z['menge'];
        $g['kz'][$z['kz']] = true;
        if ($z['zugestellt'] < $g['zugestellt']) $g['zugestellt'] = $z['zugestellt'];
        unset($g);
    }
    $nachSendung = [];
    foreach ($liste as $i => $a) if (($a['sendung'] ?? '') !== '') $nachSendung[(string)$a['sendung']][] = $i;
    $z = ['zeilen' => count($l['zeilen']), 'sendungen' => count($gruppen), 'neu' => 0, 'ergaenzt' => 0, 'schon' => 0, 'abweichend' => 0, 'ignoriert' => 0];
    $abw = []; $quelle = 'Dachser-Liste' . ($l['per'] !== '' ? ' per ' . date('d.m.Y', strtotime($l['per'] . ' 12:00:00')) : '');
    foreach ($gruppen as $sendung => $g) {
        $sendung = (string)$sendung;
        $fehlt = []; $hatAbw = false;
        foreach ($g['menge'] as $id => $n) {
            $bei = null;
            foreach ($nachSendung[$sendung] ?? [] as $i) if (isset($liste[$i]['menge'][$id])) { $bei = $i; break; }
            if ($bei === null) { $fehlt[$id] = $n; continue; }
            if ((int)$liste[$bei]['menge'][$id] !== $n) {
                $hatAbw = true;
                if (count($abw) < 50) $abw[] = ['sendung' => $sendung, 'empfaenger' => $g['empfaenger'], 'lm' => $id, 'erfasst' => (int)$liste[$bei]['menge'][$id], 'dachser' => $n];
            }
        }
        if (!$fehlt) { $z[$hatAbw ? 'abweichend' : 'schon']++; continue; }   // je Sendung genau eine Zahl: neu, ergänzt, abweichend oder schon erfasst
        $offen = null;
        foreach ($nachSendung[$sendung] ?? [] as $i) if (($liste[$i]['status'] ?? 'offen') === 'offen') { $offen = $i; break; }
        if ($offen !== null) {
            foreach ($fehlt as $id => $n) $liste[$offen]['menge'][$id] = $n;
            lg_verlauf($liste[$offen], $me, 'Menge aus der ' . $quelle . ' ergänzt: ' . implode(', ', array_map(function ($id, $n) { return strtoupper($id) . ' ' . $n; }, array_keys($fehlt), $fehlt)));
            $liste[$offen]['rev'] = (int)($liste[$offen]['rev'] ?? 0) + 1;
            $liste[$offen]['geaendert'] = lg_wer($me);
            $z['ergaenzt']++;
            continue;
        }
        $rewe = stripos($g['empfaenger'], 'rewe') !== false && array_keys($fehlt) === ['h1'];
        $d = ['id' => lg_id('d'), 'zugestellt' => $g['zugestellt'], 'auftrag' => $g['auftrag'], 'empfaenger' => mb_substr($g['empfaenger'], 0, 120),
              'empfaengerNr' => mb_substr($g['empfaengerNr'], 0, 30), 'ort' => mb_substr($g['ort'], 0, 80), 'sendung' => $sendung, 'menge' => $fehlt,
              'grund' => mb_substr($g['grund'] . ' (Kz. ' . implode('/', array_keys($g['kz'])) . ')', 0, 120), 'status' => $rewe ? 'ignoriert' : 'offen',
              'rechnung' => '', 'notiz' => $rewe ? 'H1-Abschreibungen bei REWE laut Leitfaden nicht zu beachten.' : '', 'quelle' => 'dachser',
              'erfasst' => lg_wer($me), 'verlauf' => [], 'rev' => 1, 'geaendert' => lg_wer($me)];
        lg_verlauf($d, $me, 'erfasst aus der ' . $quelle . ($rewe ? ' (Nicht zu beachten)' : ''));
        $liste[] = $d;
        $nachSendung[$sendung][] = count($liste) - 1;
        $z['neu']++;
        if ($rewe) $z['ignoriert']++;
    }
    $summe = []; $anz = []; $doppelt = [];
    foreach ($l['zeilen'] as $r) {
        $summe[$r['lm']] = ($summe[$r['lm']] ?? 0) + $r['menge'];
        $k = $r['sendung'] . '|' . $r['lm'];
        if (($anz[$k] = ($anz[$k] ?? 0) + 1) === 2 && count($doppelt) < 50) $doppelt[] = ['sendung' => $r['sendung'], 'empfaenger' => $r['empfaenger'], 'lm' => $r['lm']];
    }
    $z['doppelt'] = count($doppelt);
    return [$liste, $z, $abw, lg_ohne_null($summe), $doppelt];
}
