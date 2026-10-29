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
   Keine Daten anderer Module. Gespeicherte Felder, die diese Fassung nicht kennt, bleiben beim Speichern erhalten (GR-006).
   Rechte (GR-103): leergut.sehen, leergut.bearbeiten, leergut.verwalten. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const LG_MANDANTEN = ['standard' => 'Standard-Fleisch', 'matthies' => 'Matthies Fleischwaren'];
const LG_ARTEN = ['lieferant' => 'Lieferant', 'spedition' => 'Spedition', 'kuehlhaus' => 'Kühlhaus / Lager', 'kunde' => 'Kunde', 'sonstige' => 'Sonstige'];
const LG_TYPEN = ['bewegung' => 'Lieferung / Tausch', 'abholung' => 'Abholung / Rückgabe', 'umbuchung' => 'Umbuchung', 'korrektur' => 'Korrektur', 'anfang' => 'Anfangsbestand'];
const LG_ABST_STATUS = ['offen' => 'Offen', 'bestaetigt' => 'Bestätigt', 'widersprochen' => 'Widersprochen', 'info' => 'Zur Info'];
const LG_ABSCHR_STATUS = ['offen' => 'Offen', 'widersprochen' => 'Widersprochen', 'berechnet' => 'Berechnet', 'ausgeglichen' => 'Ausgeglichen', 'ignoriert' => 'Nicht zu beachten'];
const LG_DOKS = ['leergut-stamm', 'leergut-bewegungen', 'leergut-abstimmungen', 'leergut-abschreibungen', 'leergut-inventur'];
const LG_MAX_PARTNER = 500;
const LG_MAX_LADEMITTEL = 30;
const LG_MAX_BEWEGUNGEN = 200000;
const LG_MAX_ABSTIMMUNGEN = 20000;
const LG_MAX_ABSCHREIBUNGEN = 50000;
const LG_MAX_INVENTUR = 2000;
const LG_MAX_MENGE = 1000000;     // Stück je Lademittel und Buchung
const LG_MAX_VERLAUF = 100;
const LG_FRIST_STANDARD = 14;

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
        $out[] = ['id' => $p['id'], 'saldo' => $gesamt, 'bestaetigt' => $bestaetigt ? ['stichtag' => $bestaetigt['stichtag'], 'saldo' => $bestSaldo] : null,
                  'offenSeitBestaetigung' => lg_minus($gesamt, $bestSaldo),
                  'letzteBewegung' => $l ? end($l)['datum'] : '', 'bewegungen' => count($l),
                  'letzteAbstimmung' => $letzte ? ['id' => $letzte['id'], 'stichtag' => $letzte['stichtag'], 'status' => $letzte['status'] ?? 'offen', 'saldo' => $partnerSaldo,
                                                   'differenz' => lg_minus((array)$partnerSaldo, lg_saldo_bis($l, $letzte['stichtag']))] : null,
                  'abstimmungenOffen' => $offen, 'ueberfaellig' => $ueberfaellig];
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
