<?php
declare(strict_types=1);
/* REWE · Vordisposition Dry Aged: Daten und Regeln des Moduls „rewe“ (Oberfläche rewe.intern, Aktionen in
   app/api/aktionen/rewe.php, Excel für die Warenwirtschaft in app/api/module/rewe/export.php).
   Löst die Excel-Listen „Vordispo Rewe …“ ab: Jede Mitarbeiterin und jeder Mitarbeiter fragt die eigenen REWE-Märkte
   wöchentlich ab (Bestellt mit Mengen, Kein Bedarf, Nicht erreicht, Pause), gruppiert nach Lieferweg (REWE-Zentrallager
   oder Direktbelieferung). Jeder Markt hat eine Akte mit Wochenverlauf, Kaufbereitschaft, Dauerauftrag, Ansprechpartnern,
   Notizen und Wiedervorlagen. Die Leitung weist Märkte zu und ändert Lieferwege jeweils ab einer Kalenderwoche; zum
   Wochenende entsteht die Excel-Datei für die Erfassung in WinAB.

   Eigene Dokumente (alle Schreibvorgänge unter der Sperre „rewe-maerkte“):
     rewe-stamm        Lieferwege (Zentrallager/Direkt, Bestellschluss), Artikel (Name, Einheit, WinAB-Artikelnummer), Team
     rewe-maerkte      Märkte: Kd.-Nr. (WinAB), REWE-Marktnummer, Anschrift, Telefon, Kaufbereitschaft, Zuständigkeit und
                       Lieferweg je mit „ab KW“-Historie, Dauerauftrag (Rhythmus, Mengen, ab KW, Pause bis), Abfragetag,
                       Ansprechpartner, Hinweis
     rewe-wochen/JJJJ  je ISO-Jahr: Antworten je Markt und KW (Status, Mengen je Artikel, ohne Berechnung, Notiz) mit
                       Schnappschuss von Lieferweg und Zuständigkeit (GR-106), wer/wann; Wochenabschluss je KW (exportiert,
                       in WinAB erfasst)
     rewe-verlauf      Notizen, Telefonate, Wiedervorlagen und Änderungen (Kaufbereitschaft, Zuweisung, Dauerauftrag)
   Kalenderwochen als ISO-Woche „JJJJ-WW“ = Lieferwoche; Bestellschluss meist Freitag früh der Vorwoche (je Lieferweg
   hinterlegt). Die Abfrage startet deshalb mit der nächsten Lieferwoche (rw_kw_abfrage), der Wochenabschluss mit der
   Woche, deren Bestellschluss zuletzt war (rw_kw_abschluss).
   Fremde Daten nur lesend über die Schnittstellen der Verwaltung: Mitarbeiter (users_load) und Kundenstamm
   (customers_load) – REWE-Märkte sind WinAB-Kunden; Name, Anschrift und Telefon kommen über die Kd.-Nr. aus dem
   Kundenstamm, die eigenen Felder des Marktes gelten nur, solange die Nummer dort fehlt. Notizen und Ansprechpartner
   bleiben im REWE-Modul (nicht im CRM sichtbar, Entscheidung des Inhabers 30.10.2026).
   Team (rewe-stamm.team): je Mitarbeiter „alle Listen“ und „Wochenabschluss“ als eigene Zuweisung im Modul – wirkt
   zusätzlich zu den Rechten rewe.alle und rewe.exportieren (rw_alle, rw_export). Ruhende Märkte stehen nicht in der
   Wochenabfrage, sondern in einer eigenen Liste darunter (wieder aufnehmen = Kaufbereitschaft ändern).
   Gespeicherte Felder, die diese Fassung nicht kennt, bleiben erhalten (GR-006).
   Rechte (GR-103): rewe.sehen (eigene Märkte), rewe.bearbeiten (eigene Märkte abfragen und pflegen), rewe.alle (alle
   Listen), rewe.verwalten (Märkte, Zuweisung, Team, Lieferwege, Artikel, Datenpaket), rewe.exportieren (Wochenabschluss). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const RW_ANTWORTEN = ['bestellt' => 'Bestellt', 'kein' => 'Kein Bedarf', 'ne' => 'Nicht erreicht', 'pause' => 'Pause'];
const RW_KAUF = ['regelmaessig' => 'Kauft regelmäßig', 'gelegentlich' => 'Gelegentlich', 'interessiert' => 'Interessiert',
                 'kein_interesse' => 'Kein Interesse', 'ruhend' => 'Ruhend', 'ausgelistet' => 'Ausgelistet'];
const RW_KAUF_ABFRAGE = ['regelmaessig', 'gelegentlich', 'interessiert'];   // stehen in der Wochenabfrage
const RW_NOTIZ_ARTEN = ['notiz' => 'Notiz', 'telefonat' => 'Telefonat', 'besuch' => 'Besuch', 'reklamation' => 'Reklamation',
                        'ohne_berechnung' => 'Ware ohne Berechnung', 'system' => 'Änderung'];
const RW_LW_ARTEN = ['lager' => 'Zentrallager', 'direkt' => 'Direktbelieferung'];
const RW_TAGE = ['' => '–', 'mo' => 'Montag', 'di' => 'Dienstag', 'mi' => 'Mittwoch', 'do' => 'Donnerstag', 'fr' => 'Freitag'];
const RW_RHYTHMEN = [0 => 'kein Dauerauftrag', 1 => 'wöchentlich', 2 => '14-tägig', 3 => 'alle 3 Wochen', 4 => 'alle 4 Wochen'];
const RW_MAX_MAERKTE = 3000;
const RW_MAX_NOTIZEN = 60000;
const RW_MAX_MENGE = 999;
const RW_MAX_KONTAKTE = 12;
const RW_MAX_LIEFERWEGE = 40;
const RW_MAX_ARTIKEL = 20;
const RW_VERLAUF_WOCHEN = 8;          // Verlauf in der Wochenabfrage
const RW_ERSTES_JAHR = 2019;          // ältester Verlauf aus den Excel-Listen (KW 51/2020)
const RW_BESTELLSCHLUSS = 'Freitag früh der Vorwoche';   // Inhaber 30.10.2026: „eigentlich Freitag früh, manchmal variabel“

/* ---------- Grundwerte ---------- */
function rw_grund_lieferwege(): array
{
    return [['id' => 'direkt', 'name' => 'Direktbelieferung', 'art' => 'direkt', 'bestellschluss' => RW_BESTELLSCHLUSS, 'aktiv' => true]];
}
function rw_grund_artikel(): array
{
    return [['id' => 'rb', 'name' => 'Roastbeef Dry Aged', 'einheit' => 'Stück', 'nr' => '', 'aktiv' => true],   // 1 Stück = 1 Kolli (ganzes Roastbeef)
            ['id' => 'fk', 'name' => 'Filetkopf', 'einheit' => 'Stück', 'nr' => '', 'aktiv' => true],
            ['id' => 'set', 'name' => 'Vac. Set', 'einheit' => 'Stück', 'nr' => '', 'aktiv' => true]];
}

/* ---------- Laden und Schreiben ---------- */
function rw_stamm(): array
{
    $d = store_read('rewe-stamm');
    $d = is_array($d) ? $d : [];
    $out = ['rev' => (int)($d['rev'] ?? 0)];
    $out['lieferwege'] = is_array($d['lieferwege'] ?? null) && $d['lieferwege'] ? array_values($d['lieferwege']) : rw_grund_lieferwege();
    $out['artikel'] = is_array($d['artikel'] ?? null) && $d['artikel'] ? array_values($d['artikel']) : rw_grund_artikel();
    $out['team'] = is_array($d['team'] ?? null) ? $d['team'] : [];   // Nutzer-ID → {alle: bool, export: bool}
    return $out + $d;
}
function rw_maerkte_doc(): array
{
    $d = store_read('rewe-maerkte');
    return ['rev' => (int)($d['rev'] ?? 0), 'liste' => is_array($d['liste'] ?? null) ? array_values($d['liste']) : []] + (is_array($d) ? $d : []);
}
function rw_verlauf_doc(): array
{
    $d = store_read('rewe-verlauf');
    return ['rev' => (int)($d['rev'] ?? 0), 'liste' => is_array($d['liste'] ?? null) ? array_values($d['liste']) : []] + (is_array($d) ? $d : []);
}
/* Wochen eines ISO-Jahres: maerkte[<Markt-ID>][<WW>] = Antwort, abschluss[<WW>] = Wochenabschluss */
function rw_wochen_doc(int $jahr): array
{
    $d = store_read('rewe-wochen/' . $jahr);
    $d = is_array($d) ? $d : [];
    $out = ['rev' => (int)($d['rev'] ?? 0), 'maerkte' => is_array($d['maerkte'] ?? null) ? $d['maerkte'] : [], 'abschluss' => is_array($d['abschluss'] ?? null) ? $d['abschluss'] : []];
    return $out + $d;
}
function rw_wochen_schreiben(int $jahr, array $doc): void
{
    $doc['rev'] = (int)($doc['rev'] ?? 0) + 1;
    $doc['updatedAt'] = now();
    store_write('rewe-wochen/' . $jahr, $doc);
}
/* Jahre mit Wochendaten (für die Akte und die Leerprüfung) */
function rw_wochen_jahre(): array
{
    $j = [];
    foreach (store_names('rewe-wochen') as $n) if (preg_match('~/(\d{4})$~', $n, $m)) $j[] = (int)$m[1];
    sort($j);
    return $j;
}
function rw_schreiben(string $name, array $doc): void
{
    $doc['rev'] = (int)($doc['rev'] ?? 0) + 1;
    $doc['updatedAt'] = now();
    if ($name === 'rewe-stamm') store_write('rewe-stamm', $doc);
    elseif ($name === 'rewe-maerkte') store_write('rewe-maerkte', $doc);
    elseif ($name === 'rewe-verlauf') store_write('rewe-verlauf', $doc);
    else throw new RuntimeException('Unbekanntes Dokument');
}
function rw_id(string $praefix): string { return $praefix . bin2hex(random_bytes(6)); }
function rw_wer(array $me): array { return ['t' => now(), 'von' => (string)$me['name'], 'vonId' => (string)$me['id']]; }
/* Ist das Modul noch leer (für die Übernahme des Datenpakets ohne „ersetzen“)? */
function rw_leer(): bool
{
    return !rw_maerkte_doc()['liste'] && !rw_verlauf_doc()['liste'] && !rw_wochen_jahre();
}

/* ---------- Kalenderwochen (ISO, „JJJJ-WW“) ---------- */
function rw_kw_heute(): string { return date('o-W'); }
/* Woche, deren Bestellschluss (Freitag früh) zuletzt war bzw. gerade läuft: ab Freitag zählt schon die nächste Woche */
function rw_kw_abschluss(): string { return date('o-W', strtotime('+3 days')); }
/* Lieferwoche, für die gerade abgefragt wird (die Woche nach dem nächsten Bestellschluss) */
function rw_kw_abfrage(): string { return rw_kw_plus(rw_kw_abschluss(), 1); }
function rw_kw_montag(string $kw): DateTimeImmutable
{
    return (new DateTimeImmutable('today'))->setISODate((int)substr($kw, 0, 4), (int)substr($kw, 5, 2), 1);
}
function rw_kw($v, string $was = 'Kalenderwoche'): string
{
    $v = is_string($v) ? trim($v) : '';
    if (!preg_match('/^(\d{4})-(\d{2})$/', $v, $m)) throw new InvalidArgumentException("$was: bitte als JJJJ-WW angeben.");
    $j = (int)$m[1]; $w = (int)$m[2];
    $wochen = (int)(new DateTimeImmutable("$j-12-28"))->format('W');
    if ($j < RW_ERSTES_JAHR || $j > 2099 || $w < 1 || $w > $wochen) throw new InvalidArgumentException("$was: ungültige Kalenderwoche.");
    return sprintf('%04d-%02d', $j, $w);
}
function rw_kw_plus(string $kw, int $n): string { return rw_kw_montag($kw)->modify(($n >= 0 ? '+' : '') . $n . ' weeks')->format('o-W'); }
function rw_kw_abstand(string $von, string $bis): int { return (int)round((rw_kw_montag($bis)->getTimestamp() - rw_kw_montag($von)->getTimestamp()) / 604800); }
function rw_kw_text(string $kw): string { return 'KW ' . (int)substr($kw, 5, 2) . '/' . substr($kw, 0, 4); }
function rw_kw_zeitraum(string $kw): array
{
    $mo = rw_kw_montag($kw);
    return ['von' => $mo->format('Y-m-d'), 'bis' => $mo->modify('+6 days')->format('Y-m-d')];
}

/* ---------- Prüfen der Eingaben ---------- */
function rw_text($v, int $max, string $was, bool $mehrzeilig = false): string
{
    if ($v !== null && !is_string($v) && !is_int($v) && !is_float($v)) throw new InvalidArgumentException("$was: ungültiger Wert.");
    $t = trim(str_replace("\r", '', (string)$v));
    if (!$mehrzeilig) $t = str_replace("\n", ' ', $t);
    $t = preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', $t) ?? '';
    if (mb_strlen($t) > $max) throw new InvalidArgumentException("$was: höchstens $max Zeichen.");
    return $t;
}
function rw_wahl($v, array $erlaubt, string $was): string
{
    $v = is_string($v) ? trim($v) : (is_int($v) ? (string)$v : '');
    if (!in_array($v, array_map('strval', $erlaubt), true)) throw new InvalidArgumentException("$was: ungültige Auswahl.");
    return $v;
}
function rw_ziffern($v, int $max, string $was): string
{
    $t = is_int($v) ? (string)$v : rw_text($v, $max + 5, $was);
    $t = str_replace([' ', '.'], '', $t);
    if ($t !== '' && !preg_match('/^\d{1,' . $max . '}$/', $t)) throw new InvalidArgumentException("$was: nur Ziffern (höchstens $max).");
    return $t;
}
function rw_ganz($v, string $was, int $max = RW_MAX_MENGE): int
{
    if (is_string($v)) $v = trim($v) === '' ? 0 : trim($v);
    if (is_bool($v) || !is_numeric($v) || (float)$v != round((float)$v)) throw new InvalidArgumentException("$was: bitte eine ganze Zahl angeben.");
    $n = (int)round((float)$v);
    if ($n < 0 || $n > $max) throw new InvalidArgumentException("$was: Zahl von 0 bis $max.");
    return $n;
}
/* Mengen je Artikel { rb: 1, fk: 2 } – nur bekannte Artikel, 0 entfällt */
function rw_mengen($v, array $stamm, string $was = 'Menge'): array
{
    if ($v === null || $v === '' || $v === []) return [];
    if (!is_array($v)) throw new InvalidArgumentException("$was: ungültige Angaben.");
    $ids = array_column($stamm['artikel'], 'id');
    $out = [];
    foreach ($v as $k => $n) {
        $k = (string)$k;
        if (!in_array($k, $ids, true)) throw new InvalidArgumentException("$was: unbekannter Artikel „" . mb_substr($k, 0, 20) . '“.');
        $z = rw_ganz($n, "$was " . rw_artikel_name($stamm, $k));
        if ($z) $out[$k] = $z;
    }
    return $out;
}
function rw_artikel_name(array $stamm, string $id): string
{
    foreach ($stamm['artikel'] as $a) if ($a['id'] === $id) return (string)$a['name'];
    return $id;
}
function rw_lieferweg(array $stamm, string $id): ?array
{
    foreach ($stamm['lieferwege'] as $l) if ($l['id'] === $id) return $l;
    return null;
}

/* ---------- Mitarbeiter (Verwaltung, nur lesend) ---------- */
/* Alle Mitarbeiter: ID → Name (auch gesperrte, damit alte Zuweisungen lesbar bleiben) */
function rw_namen(): array
{
    $n = [];
    foreach (users_load() as $u) $n[(string)$u['id']] = (string)($u['name'] ?: $u['username']);
    return $n;
}
/* Mitarbeiter, denen Märkte zugewiesen werden können: aktiv, mit Zugang und „REWE ansehen“ */
function rw_personen(): array
{
    $out = [];
    foreach (users_load() as $u) {
        if (empty($u['active']) || !nutzer_hat_zugang($u) || !may($u, 'rewe.sehen')) continue;
        $t = rw_team($u);
        $out[] = ['id' => (string)$u['id'], 'name' => (string)($u['name'] ?: $u['username']), 'bearbeiten' => may($u, 'rewe.bearbeiten'),
                  'alle' => rw_alle($u), 'export' => rw_export($u), 'teamAlle' => $t['alle'], 'teamExport' => $t['export'],
                  'rechtAlle' => may($u, 'rewe.alle'), 'rechtExport' => may($u, 'rewe.exportieren')];
    }
    usort($out, function ($a, $b) { return strcasecmp($a['name'], $b['name']); });
    return $out;
}
/* Team speichern: {Nutzer-ID: {alle, export}} – nur Mitarbeiter mit „REWE ansehen“ */
function rw_team_pruefen($v): array
{
    if (!is_array($v)) throw new InvalidArgumentException('Team: ungültige Angaben.');
    $erlaubt = array_column(rw_personen(), 'name', 'id');
    $out = [];
    foreach ($v as $id => $t) {
        $id = (string)$id;
        if (!isset($erlaubt[$id])) throw new InvalidArgumentException('Team: unbekannter Mitarbeiter oder ohne „REWE ansehen“.');
        if (!is_array($t)) throw new InvalidArgumentException('Team: ungültige Angaben.');
        if (!empty($t['alle']) || !empty($t['export'])) $out[$id] = ['alle' => !empty($t['alle']), 'export' => !empty($t['export'])];
    }
    return $out;
}

/* ---------- Kundenstamm der Verwaltung (nur lesend, customers_load): WinAB-Kd.-Nr. → Kunde ---------- */
function rw_kunden(): array
{
    static $k = null;
    if ($k !== null) return $k;
    $k = [];
    foreach (customers_load()['customers'] as $c) {
        $nr = trim((string)($c['nr'] ?? ''));
        if ($nr === '' || !is_array($c)) continue;
        $k[$nr] = ['firma' => (string)($c['firma'] ?? ''), 'strasse' => (string)($c['strasse'] ?? ''), 'plz' => (string)($c['plz'] ?? ''),
                   'ort' => (string)($c['ort'] ?? ''), 'telefon' => (string)($c['telefon'] ?? ''), 'aktiv' => !array_key_exists('active', $c) || !empty($c['active'])];
    }
    return $k;
}
/* Anzeige eines Marktes: Kundenstamm vor eigenen Feldern (nur leere Stammfelder füllt der Markt auf) */
function rw_anzeige(array $m): array
{
    $k = rw_kunden()[(string)($m['kdNr'] ?? '')] ?? null;
    $f = function (string $kf, string $mf) use ($k, $m) { $v = $k ? trim($k[$kf]) : ''; return $v !== '' ? $v : (string)($m[$mf] ?? ''); };
    return ['name' => $f('firma', 'name'), 'strasse' => $f('strasse', 'strasse'), 'plz' => $f('plz', 'plz'), 'ort' => $f('ort', 'ort'),
            'telefon' => $f('telefon', 'telefon'), 'winab' => $k !== null, 'winabAktiv' => $k ? $k['aktiv'] : null];
}
function rw_person_pruefen($v): string
{
    $id = is_string($v) ? trim($v) : '';
    if ($id === '') return '';
    foreach (users_load() as $u) if ((string)$u['id'] === $id) {
        if (empty($u['active']) || !nutzer_hat_zugang($u)) throw new InvalidArgumentException('Zuständig: Der Mitarbeiter ist gesperrt.');
        return $id;
    }
    throw new InvalidArgumentException('Zuständig: unbekannter Mitarbeiter.');
}

/* ---------- Historie „ab KW“ (Zuständigkeit, Lieferweg) ---------- */
/* Wert zur KW: letzter Eintrag mit ab ≤ KW; vor dem ersten Eintrag gilt der erste */
function rw_ab(array $hist, string $kw, string $feld): string
{
    $wert = null;
    foreach ($hist as $h) { if (($h['ab'] ?? '') <= $kw) $wert = (string)($h[$feld] ?? ''); }
    if ($wert === null && $hist) $wert = (string)($hist[0][$feld] ?? '');
    return $wert ?? '';
}
/* Neuer Wert ab KW: spätere Einträge entfallen, gleicher Wert wie vorher → keine Änderung */
function rw_ab_setzen(array $hist, string $kw, string $feld, string $wert): array
{
    $alt = $hist ? rw_ab($hist, rw_kw_plus($kw, -1), $feld) : null;
    $hist = array_values(array_filter($hist, function ($h) use ($kw) { return ($h['ab'] ?? '') < $kw; }));
    if ($alt !== $wert || !$hist) $hist[] = ['ab' => $kw, $feld => $wert];
    return $hist;
}
function rw_zustaendig(array $m, string $kw): string { return rw_ab($m['zustaendig'] ?? [], $kw, 'nutzer'); }
function rw_lw(array $m, string $kw): string { return rw_ab($m['lieferweg'] ?? [], $kw, 'id'); }

/* ---------- Sichtbarkeit (GR-103, serverseitig je Markt) ---------- */
/* Alle Listen / Wochenabschluss: Recht der Plattform oder Zuweisung im Team des Moduls (nur mit „REWE ansehen“) */
function rw_team(array $me): array
{
    static $team = null;
    if ($team === null) $team = rw_stamm()['team'];
    $t = $team[(string)$me['id']] ?? [];
    return ['alle' => !empty($t['alle']), 'export' => !empty($t['export'])];
}
function rw_alle(array $me): bool { return may($me, 'rewe.alle') || (may($me, 'rewe.sehen') && rw_team($me)['alle']); }
function rw_export(array $me): bool { return may($me, 'rewe.exportieren') || (may($me, 'rewe.sehen') && rw_team($me)['export']); }
function rw_eigen(array $m, array $me, string $kw): bool { return rw_zustaendig($m, $kw) === (string)$me['id']; }
function rw_darf_sehen(array $m, array $me, string $kw = ''): bool
{
    return rw_alle($me) || rw_eigen($m, $me, rw_kw_heute()) || rw_eigen($m, $me, rw_kw_abfrage()) || ($kw !== '' && rw_eigen($m, $me, $kw));
}
function rw_darf_pflegen(array $m, array $me, string $kw = ''): bool
{
    return may($me, 'rewe.bearbeiten') && rw_darf_sehen($m, $me, $kw);
}
function rw_markt_index(array $doc, $id): int
{
    $id = is_string($id) ? $id : '';
    foreach ($doc['liste'] as $i => $m) if ($id !== '' && ($m['id'] ?? '') === $id) return $i;
    fail('Markt nicht gefunden.', 404);
    return -1;
}
function rw_markt_finden(array $doc, $id, array $me, string $kw = ''): array
{
    $m = $doc['liste'][rw_markt_index($doc, $id)];
    if (!rw_darf_sehen($m, $me, $kw)) fail('Markt nicht gefunden.', 404);   // fremde Märkte ohne „alle Listen“ wie nicht vorhanden
    return $m;
}

/* ---------- Dauerauftrag ---------- */
function rw_dauer(array $m): array
{
    $d = is_array($m['dauer'] ?? null) ? $m['dauer'] : [];
    return ['rhythmus' => (int)($d['rhythmus'] ?? 0), 'mengen' => is_array($d['mengen'] ?? null) ? $d['mengen'] : [],
            'ab' => (string)($d['ab'] ?? ''), 'pauseBis' => (string)($d['pauseBis'] ?? '')];
}
/* Ist der Dauerauftrag in der KW fällig? Liefert die nächste fällige KW (≥ $kw) oder '' */
function rw_dauer_naechste(array $m, string $kw): string
{
    $d = rw_dauer($m);
    if ($d['rhythmus'] < 1 || !$d['mengen'] || $d['ab'] === '') return '';
    $start = $kw < $d['ab'] ? $d['ab'] : $kw;
    if ($d['pauseBis'] !== '' && $start <= $d['pauseBis']) $start = rw_kw_plus($d['pauseBis'], 1);
    $diff = rw_kw_abstand($d['ab'], $start);
    $rest = (($diff % $d['rhythmus']) + $d['rhythmus']) % $d['rhythmus'];
    return $rest === 0 ? $start : rw_kw_plus($start, $d['rhythmus'] - $rest);
}
function rw_dauer_faellig(array $m, string $kw): bool { return rw_dauer_naechste($m, $kw) === $kw; }
function rw_dauer_text(array $m, array $stamm): string
{
    $d = rw_dauer($m);
    if ($d['rhythmus'] < 1 || !$d['mengen']) return '';
    return 'Dauerauftrag ' . (RW_RHYTHMEN[$d['rhythmus']] ?? '') . ' · ' . rw_mengen_text($d['mengen'], $stamm);
}
function rw_mengen_text(array $mengen, array $stamm): string
{
    $t = [];
    foreach ($stamm['artikel'] as $a) if (!empty($mengen[$a['id']])) $t[] = $mengen[$a['id']] . ' ' . $a['name'];
    return implode(' + ', $t);
}

/* ---------- Antworten ---------- */
function rw_antwort(array $wochen, string $markt, string $kw): ?array
{
    $e = $wochen['maerkte'][$markt][substr($kw, 5, 2)] ?? null;
    return is_array($e) ? $e : null;
}
/* Antwort für die Oberfläche (Kurzform im Speicher → lesbare Felder) */
function rw_antwort_aus(?array $e): ?array
{
    if (!$e) return null;
    return ['status' => (string)($e['s'] ?? ''), 'mengen' => is_array($e['m'] ?? null) ? $e['m'] : [], 'ohneBerechnung' => !empty($e['ob']),
            'notiz' => (string)($e['n'] ?? ''), 'r' => (int)($e['r'] ?? 0), 'quelle' => (string)($e['q'] ?? 'hand'), 'nachtrag' => !empty($e['nachtrag']),
            'lieferweg' => (string)($e['lw'] ?? ''), 'zustaendig' => (string)($e['zuName'] ?? ''), 't' => (string)($e['t'] ?? ''), 'von' => (string)($e['von'] ?? '')];
}
/* Wochen mehrerer Jahre auf einmal (Verlauf über den Jahreswechsel) */
function rw_wochen_cache(array &$cache, int $jahr): array
{
    if (!isset($cache[$jahr])) $cache[$jahr] = rw_wochen_doc($jahr);
    return $cache[$jahr];
}
function rw_antwort_kw(array &$cache, string $markt, string $kw): ?array
{
    return rw_antwort(rw_wochen_cache($cache, (int)substr($kw, 0, 4)), $markt, $kw);
}
/* Antwort setzen (Aufruf unter der Sperre). $b: {markt, kw, status ('' = zurück auf offen), mengen, ohneBerechnung, notiz, r} */
function rw_antwort_setzen(array $b, array $me, array $stamm, string $quelle = 'hand'): array
{
    $kw = rw_kw($b['kw'] ?? '');
    if (rw_kw_abstand(rw_kw_heute(), $kw) > 12) throw new InvalidArgumentException('Kalenderwoche: höchstens zwölf Wochen im Voraus.');
    $doc = rw_maerkte_doc();
    $m = rw_markt_finden($doc, $b['markt'] ?? '', $me, $kw);
    if (!may($me, 'rewe.bearbeiten') || (!rw_alle($me) && !rw_eigen($m, $me, $kw))) fail('Dieser Markt gehört in der Woche nicht zu Ihrer Liste.', 403);
    $status = is_string($b['status'] ?? null) ? trim($b['status']) : '';
    if ($status !== '') rw_wahl($status, array_keys(RW_ANTWORTEN), 'Antwort');
    $mengen = $status === 'bestellt' ? rw_mengen($b['mengen'] ?? [], $stamm) : [];
    if ($status === 'bestellt' && !$mengen) throw new InvalidArgumentException('Bestellt: bitte eine Menge angeben.');
    $notiz = rw_text($b['notiz'] ?? '', 300, 'Notiz');
    $jahr = (int)substr($kw, 0, 4); $ww = substr($kw, 5, 2);
    $w = rw_wochen_doc($jahr);
    $alt = rw_antwort($w, $m['id'], $kw);
    if (array_key_exists('r', $b) && (int)$b['r'] !== (int)($alt['r'] ?? 0))
        respond(['ok' => false, 'code' => 'konflikt', 'error' => 'Die Antwort wurde inzwischen von ' . ($alt['von'] ?? 'jemand anderem') . ' geändert. Bitte neu laden.',
                 'antwort' => rw_antwort_aus($alt)], 409);
    $abschluss = $w['abschluss'][$ww] ?? [];
    if ($status === '') {
        unset($w['maerkte'][$m['id']][$ww]);
        if (empty($w['maerkte'][$m['id']])) unset($w['maerkte'][$m['id']]);
        $neu = null;
    } else {
        $namen = rw_namen(); $zu = rw_zustaendig($m, $kw);
        $neu = ['s' => $status] + ($mengen ? ['m' => $mengen] : []) + (!empty($b['ohneBerechnung']) && $status === 'bestellt' ? ['ob' => true] : [])
             + ($notiz !== '' ? ['n' => $notiz] : [])
             + ['lw' => rw_lw($m, $kw), 'zu' => $zu, 'zuName' => $namen[$zu] ?? '', 'q' => $quelle, 'r' => (int)($alt['r'] ?? 0) + 1] + rw_wer($me);
        if (!empty($abschluss['exportiert'])) $neu['nachtrag'] = true;
        $w['maerkte'][$m['id']][$ww] = $neu;
    }
    if ($alt === null && $neu === null) return ['markt' => $m, 'antwort' => null];
    rw_wochen_schreiben($jahr, $w);
    return ['markt' => $m, 'antwort' => $neu];
}

/* ---------- Verlauf (Notizen und Änderungen) ---------- */
function rw_notiz_neu(array $doc, string $markt, string $art, string $text, array $me, string $wv = '', string $quelle = 'hand'): array
{
    if (count($doc['liste']) >= RW_MAX_NOTIZEN) $doc['liste'] = array_slice($doc['liste'], -RW_MAX_NOTIZEN + 1);
    $doc['liste'][] = ['id' => rw_id('n'), 'markt' => $markt, 'art' => $art, 'text' => $text, 'wv' => $wv, 'erledigt' => null, 'q' => $quelle] + rw_wer($me);
    return $doc;
}
function rw_system_notiz(string $markt, string $text, array $me): void
{
    rw_schreiben('rewe-verlauf', rw_notiz_neu(rw_verlauf_doc(), $markt, 'system', $text, $me));
}
/* Offene Wiedervorlagen je Markt (fällig bis heute) */
function rw_wiedervorlagen(array $verlauf, string $heute): array
{
    $out = [];
    foreach ($verlauf['liste'] as $n) {
        if (($n['wv'] ?? '') === '' || !empty($n['erledigt']) || $n['wv'] > $heute) continue;
        $out[$n['markt']][] = ['id' => $n['id'], 'wv' => $n['wv'], 'text' => (string)$n['text']];
    }
    return $out;
}

/* ---------- Märkte prüfen ---------- */
function rw_kontakte($v): array
{
    if ($v === null || $v === '') return [];
    if (!is_array($v)) throw new InvalidArgumentException('Ansprechpartner: ungültige Angaben.');
    if (count($v) > RW_MAX_KONTAKTE) throw new InvalidArgumentException('Höchstens ' . RW_MAX_KONTAKTE . ' Ansprechpartner.');
    $out = [];
    foreach (array_values($v) as $i => $k) {
        if (!is_array($k)) throw new InvalidArgumentException('Ansprechpartner: ungültige Angaben.');
        $name = rw_text($k['name'] ?? '', 80, 'Ansprechpartner ' . ($i + 1) . ': Name');
        $rolle = rw_text($k['rolle'] ?? '', 80, 'Ansprechpartner ' . ($i + 1) . ': Rolle');
        $tel = rw_text($k['telefon'] ?? '', 60, 'Ansprechpartner ' . ($i + 1) . ': Telefon');
        $mail = rw_text($k['email'] ?? '', 120, 'Ansprechpartner ' . ($i + 1) . ': E-Mail');
        if ($mail !== '' && !filter_var($mail, FILTER_VALIDATE_EMAIL)) throw new InvalidArgumentException('Ansprechpartner ' . ($i + 1) . ': ungültige E-Mail.');
        if ($name === '' && $rolle === '' && $tel === '' && $mail === '') continue;
        if ($name === '') throw new InvalidArgumentException('Ansprechpartner ' . ($i + 1) . ': bitte einen Namen angeben.');
        $out[] = ['name' => $name, 'rolle' => $rolle, 'telefon' => $tel, 'email' => $mail];
    }
    return $out;
}
function rw_dauer_pruefen($v, array $stamm): array
{
    if ($v === null || $v === '' || $v === []) return ['rhythmus' => 0, 'mengen' => [], 'ab' => '', 'pauseBis' => ''];
    if (!is_array($v)) throw new InvalidArgumentException('Dauerauftrag: ungültige Angaben.');
    $r = (int)rw_wahl((string)($v['rhythmus'] ?? '0'), array_keys(RW_RHYTHMEN), 'Dauerauftrag: Rhythmus');
    if ($r === 0) return ['rhythmus' => 0, 'mengen' => [], 'ab' => '', 'pauseBis' => ''];
    $mengen = rw_mengen($v['mengen'] ?? [], $stamm, 'Dauerauftrag');
    if (!$mengen) throw new InvalidArgumentException('Dauerauftrag: bitte eine Menge angeben.');
    $ab = rw_kw($v['ab'] ?? '', 'Dauerauftrag ab');
    $pause = trim((string)($v['pauseBis'] ?? '')) === '' ? '' : rw_kw($v['pauseBis'], 'Dauerauftrag: Pause bis');
    return ['rhythmus' => $r, 'mengen' => $mengen, 'ab' => $ab, 'pauseBis' => $pause];
}
/* Felder, die jeder mit „bearbeiten“ an eigenen Märkten pflegt */
const RW_FELDER_PFLEGE = ['kauf', 'dauer', 'abfragetag', 'ansprechpartner', 'hinweis', 'telefon'];
/* Stammfelder, nur mit „verwalten“ */
const RW_FELDER_STAMM = ['kdNr', 'reweNr', 'name', 'strasse', 'plz', 'ort', 'region'];
function rw_markt_felder(array $b, array $stamm, array $alt): array
{
    $m = [];
    if (array_key_exists('kdNr', $b)) $m['kdNr'] = rw_ziffern($b['kdNr'], 10, 'Kd.-Nr.');
    if (array_key_exists('reweNr', $b)) $m['reweNr'] = rw_ziffern($b['reweNr'], 10, 'REWE-Marktnummer');
    if (array_key_exists('name', $b)) $m['name'] = rw_text($b['name'], 100, 'Name');
    if (array_key_exists('strasse', $b)) $m['strasse'] = rw_text($b['strasse'], 100, 'Straße');
    if (array_key_exists('plz', $b)) $m['plz'] = rw_ziffern($b['plz'], 5, 'PLZ');
    if (array_key_exists('ort', $b)) $m['ort'] = rw_text($b['ort'], 80, 'Ort');
    if (array_key_exists('region', $b)) $m['region'] = rw_text($b['region'], 40, 'Region');
    if (array_key_exists('telefon', $b)) $m['telefon'] = rw_text($b['telefon'], 120, 'Telefon');
    if (array_key_exists('kauf', $b)) $m['kauf'] = rw_wahl($b['kauf'], array_keys(RW_KAUF), 'Kaufbereitschaft');
    if (array_key_exists('dauer', $b)) $m['dauer'] = rw_dauer_pruefen($b['dauer'], $stamm);
    if (array_key_exists('abfragetag', $b)) $m['abfragetag'] = rw_wahl($b['abfragetag'] ?? '', array_keys(RW_TAGE), 'Abfragetag');
    if (array_key_exists('ansprechpartner', $b)) $m['ansprechpartner'] = rw_kontakte($b['ansprechpartner']);
    if (array_key_exists('hinweis', $b)) $m['hinweis'] = rw_text($b['hinweis'], 1000, 'Hinweis', true);
    $neu = $m + $alt;
    $a = rw_anzeige($neu);
    if (trim($a['ort']) === '') throw new InvalidArgumentException('Ort: bitte angeben (oder eine Kd.-Nr. aus dem Kundenstamm).');
    if (trim($a['name']) === '') throw new InvalidArgumentException('Name: bitte angeben (oder eine Kd.-Nr. aus dem Kundenstamm).');
    return $m;
}
function rw_kdnr_frei(array $doc, string $kdNr, string $id): void
{
    if ($kdNr === '') return;
    foreach ($doc['liste'] as $m) if (($m['kdNr'] ?? '') === $kdNr && $m['id'] !== $id)
        throw new InvalidArgumentException('Kd.-Nr. ' . $kdNr . ' gehört schon zu ' . $m['name'] . '.');
}
/* Markt für die Oberfläche */
function rw_markt_aus(array $m, array $stamm, array $namen, string $kw): array
{
    $lw = rw_lieferweg($stamm, rw_lw($m, $kw));
    $zu = rw_zustaendig($m, $kw);
    $a = rw_anzeige($m);
    return ['id' => $m['id'], 'rev' => (int)($m['rev'] ?? 0), 'kdNr' => (string)($m['kdNr'] ?? ''), 'reweNr' => (string)($m['reweNr'] ?? ''),
            'name' => $a['name'], 'strasse' => $a['strasse'], 'plz' => $a['plz'], 'ort' => $a['ort'], 'telefon' => $a['telefon'], 'winab' => $a['winab'],
            'eigen' => ['name' => (string)($m['name'] ?? ''), 'strasse' => (string)($m['strasse'] ?? ''), 'plz' => (string)($m['plz'] ?? ''), 'ort' => (string)($m['ort'] ?? ''), 'telefon' => (string)($m['telefon'] ?? '')],
            'region' => (string)($m['region'] ?? ''), 'kauf' => (string)($m['kauf'] ?? 'regelmaessig'),
            'dauer' => rw_dauer($m), 'abfragetag' => (string)($m['abfragetag'] ?? ''), 'ansprechpartner' => is_array($m['ansprechpartner'] ?? null) ? $m['ansprechpartner'] : [],
            'hinweis' => (string)($m['hinweis'] ?? ''), 'lieferweg' => $lw ? $lw['id'] : '', 'lieferwegName' => $lw ? $lw['name'] : '', 'lieferwegArt' => $lw ? $lw['art'] : '',
            'zustaendig' => $zu, 'zustaendigName' => $namen[$zu] ?? '',
            'zustaendigHist' => array_map(function ($h) use ($namen) { return ['ab' => $h['ab'], 'nutzer' => $h['nutzer'], 'name' => $namen[$h['nutzer']] ?? ($h['nutzer'] === '' ? 'niemand' : '(unbekannt)')]; }, $m['zustaendig'] ?? []),
            'lieferwegHist' => array_map(function ($h) use ($stamm) { $l = rw_lieferweg($stamm, $h['id']); return ['ab' => $h['ab'], 'id' => $h['id'], 'name' => $l ? $l['name'] : $h['id']]; }, $m['lieferweg'] ?? [])];
}

/* ---------- Wochenabfrage ---------- */
/* $wer: '' = eigene Liste, Nutzer-ID = Liste dieser Person (nur mit „alle“), '*' = alle Listen (nur mit „alle“) */
function rw_woche(string $kw, array $me, string $wer): array
{
    $stamm = rw_stamm(); $namen = rw_namen(); $heute = date('Y-m-d');
    $alle = rw_alle($me);
    $person = $wer === '' || !$alle ? (string)$me['id'] : $wer;
    $cache = [];
    $wv = rw_wiedervorlagen(rw_verlauf_doc(), $heute);
    $gruppen = []; $ruhend = []; $z = ['gesamt' => 0, 'beantwortet' => 0, 'bestellt' => 0, 'mengen' => [], 'dauerOffen' => 0, 'wiedervorlagen' => 0];
    foreach (rw_maerkte_doc()['liste'] as $m) {
        if ($person !== '*' && rw_zustaendig($m, $kw) !== $person) continue;
        $antwort = rw_antwort_kw($cache, $m['id'], $kw);
        $faellig = rw_dauer_faellig($m, $kw);
        if (!$antwort && !$faellig && !in_array($m['kauf'] ?? 'regelmaessig', RW_KAUF_ABFRAGE, true)) {
            if (($m['kauf'] ?? '') === 'ruhend') $ruhend[] = $m;
            continue;
        }
        $lwId = rw_lw($m, $kw);
        $verlauf = [];
        for ($i = RW_VERLAUF_WOCHEN; $i >= 1; $i--) {
            $k = rw_kw_plus($kw, -$i); $e = rw_antwort_kw($cache, $m['id'], $k);
            $verlauf[] = ['kw' => $k, 'status' => $e ? $e['s'] : '', 'menge' => $e && !empty($e['m']) ? array_sum($e['m']) : 0];
        }
        $naechste = rw_dauer_naechste($m, $kw);
        $eintrag = rw_markt_aus($m, $stamm, $namen, $kw) + ['antwort' => rw_antwort_aus($antwort), 'verlauf' => $verlauf,
            'dauerFaellig' => $faellig, 'dauerNaechste' => $naechste, 'dauerText' => rw_dauer_text($m, $stamm),
            'wiedervorlagen' => $wv[$m['id']] ?? [], 'darfAntworten' => may($me, 'rewe.bearbeiten') && ($alle || rw_eigen($m, $me, $kw))];
        $gruppen[$lwId === '' ? '_' : $lwId][] = $eintrag;
        $z['gesamt']++;
        if ($antwort) $z['beantwortet']++;
        if ($antwort && $antwort['s'] === 'bestellt') { $z['bestellt']++; foreach ($antwort['m'] ?? [] as $a => $n) $z['mengen'][$a] = ($z['mengen'][$a] ?? 0) + $n; }
        if (!$antwort && $faellig) $z['dauerOffen']++;
        if (!empty($wv[$m['id']])) $z['wiedervorlagen']++;
    }
    $aus = [];
    foreach ($gruppen as $id => $liste) {
        usort($liste, function ($a, $b) { return [$a['ort'], $a['name']] <=> [$b['ort'], $b['name']]; });
        $l = $id === '_' ? null : rw_lieferweg($stamm, $id);
        $aus[] = ['id' => $id === '_' ? '' : $id, 'name' => $l ? $l['name'] : 'Ohne Lieferweg', 'art' => $l ? $l['art'] : '', 'bestellschluss' => $l ? (string)($l['bestellschluss'] ?? '') : '',
                  'maerkte' => $liste];
    }
    // Zentrallager nach Name, Direktbelieferung danach, ohne Lieferweg zuletzt
    usort($aus, function ($a, $b) {
        $r = function ($g) { return $g['art'] === 'lager' ? 0 : ($g['art'] === 'direkt' ? 1 : 2); };
        return [$r($a), $a['name']] <=> [$r($b), $b['name']];
    });
    $ww = substr($kw, 5, 2);
    $abschluss = rw_wochen_cache($cache, (int)substr($kw, 0, 4))['abschluss'][$ww] ?? null;
    $ruhendAus = [];
    if ($ruhend) {
        $letzte = rw_letzte_bestellungen();
        foreach ($ruhend as $m) {
            $x = rw_markt_aus($m, $stamm, $namen, $kw);
            $ruhendAus[] = ['id' => $x['id'], 'name' => $x['name'], 'ort' => $x['ort'], 'strasse' => $x['strasse'], 'kdNr' => $x['kdNr'], 'lieferwegName' => $x['lieferwegName'],
                            'zustaendigName' => $x['zustaendigName'], 'letzte' => $letzte[$m['id']] ?? '', 'hinweis' => $x['hinweis'],
                            'darfPflegen' => rw_darf_pflegen($m, $me, $kw)];
        }
        usort($ruhendAus, function ($a, $b) { return [$a['ort'], $a['name']] <=> [$b['ort'], $b['name']]; });
    }
    return ['kw' => $kw, 'kwText' => rw_kw_text($kw), 'zeitraum' => rw_kw_zeitraum($kw), 'heute' => rw_kw_heute(), 'abfrage' => rw_kw_abfrage(), 'wer' => $person === (string)$me['id'] ? '' : $person,
            'werName' => $person === '*' ? 'Alle Listen' : ($namen[$person] ?? ''), 'gruppen' => $aus, 'ruhend' => $ruhendAus, 'zahlen' => $z,
            'abschluss' => $abschluss ? ['exportiert' => $abschluss['exportiert'] ?? null, 'erfasst' => $abschluss['erfasst'] ?? null] : null];
}
/* Fällige Daueraufträge einer KW als Bestellung übernehmen (eigene Märkte bzw. mit „alle“ die gewählte Liste) */
function rw_dauer_uebernehmen(string $kw, array $me, string $wer, array $nurIds): array
{
    $stamm = rw_stamm(); $n = 0;
    $alle = rw_alle($me);
    $person = $wer === '' || !$alle ? (string)$me['id'] : $wer;
    $w = rw_wochen_doc((int)substr($kw, 0, 4));
    foreach (rw_maerkte_doc()['liste'] as $m) {
        if ($person !== '*' && rw_zustaendig($m, $kw) !== $person) continue;
        if ($nurIds && !in_array($m['id'], $nurIds, true)) continue;
        if (!rw_dauer_faellig($m, $kw) || rw_antwort($w, $m['id'], $kw)) continue;
        $mengen = array_intersect_key(rw_dauer($m)['mengen'], array_flip(array_column($stamm['artikel'], 'id')));
        if (!$mengen) continue;
        rw_antwort_setzen(['markt' => $m['id'], 'kw' => $kw, 'status' => 'bestellt', 'mengen' => $mengen], $me, $stamm, 'dauer');
        $w = rw_wochen_doc((int)substr($kw, 0, 4));
        $n++;
    }
    return ['uebernommen' => $n];
}

/* Letzte Bestellung je Markt über alle Jahre (Märkteübersicht, ruhende Märkte) */
function rw_letzte_bestellungen(): array
{
    $out = [];
    foreach (rw_wochen_jahre() as $j) {
        foreach (rw_wochen_doc($j)['maerkte'] as $mid => $wochen) foreach ($wochen as $ww => $e) {
            if (($e['s'] ?? '') !== 'bestellt') continue;
            $k = sprintf('%04d-%s', $j, $ww);
            if ($k > ($out[$mid] ?? '')) $out[$mid] = $k;
        }
    }
    return $out;
}

/* ---------- Marktakte ---------- */
function rw_akte(array $m, array $me): array
{
    $stamm = rw_stamm(); $namen = rw_namen(); $kw = rw_kw_abfrage();
    $wochen = []; $jahre = [];
    foreach (rw_wochen_jahre() as $j) {
        $d = rw_wochen_doc($j);
        foreach ($d['maerkte'][$m['id']] ?? [] as $ww => $e) {
            $wochen[sprintf('%04d-%s', $j, $ww)] = ['status' => (string)($e['s'] ?? ''), 'mengen' => is_array($e['m'] ?? null) ? $e['m'] : [],
                'notiz' => (string)($e['n'] ?? ''), 'ohneBerechnung' => !empty($e['ob']), 'von' => (string)($e['von'] ?? ''), 'quelle' => (string)($e['q'] ?? 'hand')];
            $jahre[$j] = true;
        }
    }
    ksort($wochen);
    $notizen = array_values(array_filter(rw_verlauf_doc()['liste'], function ($n) use ($m) { return $n['markt'] === $m['id']; }));
    usort($notizen, function ($a, $b) { return strcmp($b['t'], $a['t']); });
    $zahlen = [];
    foreach ($wochen as $k => $e) {
        if ($e['status'] !== 'bestellt') continue;
        $j = substr($k, 0, 4);
        $zahlen[$j]['lieferungen'] = ($zahlen[$j]['lieferungen'] ?? 0) + 1;
        foreach ($e['mengen'] as $a => $n) $zahlen[$j]['mengen'][$a] = ($zahlen[$j]['mengen'][$a] ?? 0) + $n;
        $zahlen['letzte'] = $k;
    }
    return ['markt' => rw_markt_aus($m, $stamm, $namen, $kw), 'wochen' => (object)$wochen, 'notizen' => $notizen, 'zahlen' => (object)$zahlen,
            'darfPflegen' => rw_darf_pflegen($m, $me), 'naechsteDauer' => rw_dauer_naechste($m, $kw)];
}

/* ---------- Zuweisung ---------- */
/* Zuständigkeit und/oder Lieferweg mehrerer Märkte ab KW ändern; Änderung im Verlauf mit Namen */
function rw_zuweisen(array $ids, string $kw, ?string $nutzer, ?string $lieferweg, array $me): int
{
    $doc = rw_maerkte_doc(); $stamm = rw_stamm(); $namen = rw_namen();
    $verlauf = rw_verlauf_doc(); $n = 0;
    foreach ($ids as $id) {
        $i = rw_markt_index($doc, $id); $m = $doc['liste'][$i]; $text = [];
        if ($nutzer !== null) {
            $alt = rw_zustaendig($m, $kw);
            $m['zustaendig'] = rw_ab_setzen($m['zustaendig'] ?? [], $kw, 'nutzer', $nutzer);
            if ($alt !== $nutzer) $text[] = 'Zuständig ' . ($namen[$alt] ?? 'niemand') . ' → ' . ($nutzer === '' ? 'niemand' : ($namen[$nutzer] ?? $nutzer));
        }
        if ($lieferweg !== null) {
            $alt = rw_lw($m, $kw);
            $m['lieferweg'] = rw_ab_setzen($m['lieferweg'] ?? [], $kw, 'id', $lieferweg);
            if ($alt !== $lieferweg) $text[] = 'Lieferweg ' . (rw_lieferweg($stamm, $alt)['name'] ?? 'ohne') . ' → ' . rw_lieferweg($stamm, $lieferweg)['name'];
        }
        if (!$text) continue;
        $m['rev'] = (int)($m['rev'] ?? 0) + 1; $m['geaendert'] = rw_wer($me);
        $doc['liste'][$i] = $m;
        $verlauf = rw_notiz_neu($verlauf, $m['id'], 'system', implode(', ', $text) . ' ab ' . rw_kw_text($kw), $me);
        $n++;
    }
    if ($n) { rw_schreiben('rewe-maerkte', $doc); rw_schreiben('rewe-verlauf', $verlauf); }
    return $n;
}

/* ---------- Stammdaten (Lieferwege, Artikel) ---------- */
function rw_stamm_pruefen(array $b, array $alt): array
{
    $neu = $alt;
    if (array_key_exists('lieferwege', $b)) {
        if (!is_array($b['lieferwege']) || !$b['lieferwege']) throw new InvalidArgumentException('Lieferwege: mindestens einer.');
        if (count($b['lieferwege']) > RW_MAX_LIEFERWEGE) throw new InvalidArgumentException('Zu viele Lieferwege.');
        $neu['lieferwege'] = rw_stamm_liste($b['lieferwege'], $alt['lieferwege'], 'Lieferweg', function ($x, $w) {
            return ['art' => rw_wahl($x['art'] ?? '', array_keys(RW_LW_ARTEN), "$w: Art"), 'bestellschluss' => rw_text($x['bestellschluss'] ?? RW_BESTELLSCHLUSS, 40, "$w: Bestellschluss")];
        }, 'l');
    }
    if (array_key_exists('artikel', $b)) {
        if (!is_array($b['artikel']) || !$b['artikel']) throw new InvalidArgumentException('Artikel: mindestens einer.');
        if (count($b['artikel']) > RW_MAX_ARTIKEL) throw new InvalidArgumentException('Zu viele Artikel.');
        $neu['artikel'] = rw_stamm_liste($b['artikel'], $alt['artikel'], 'Artikel', function ($x, $w) {
            $nr = rw_text($x['nr'] ?? '', 20, "$w: WinAB-Artikelnummer");
            if ($nr !== '' && !preg_match('/^[A-Za-z0-9.\-\/]+$/', $nr)) throw new InvalidArgumentException("$w: WinAB-Artikelnummer nur aus Ziffern, Buchstaben, . - /");
            return ['einheit' => rw_text($x['einheit'] ?? '', 15, "$w: Einheit") ?: 'Stück', 'nr' => $nr];
        }, 'a');
        if (!array_filter($neu['artikel'], function ($a) { return $a['aktiv']; })) throw new InvalidArgumentException('Artikel: mindestens einer muss aktiv sein.');
    }
    return $neu;
}
/* Gemeinsame Prüfung für Lieferwege und Artikel: Kennung bleibt, nichts wird entfernt (nur deaktiviert), Namen eindeutig */
function rw_stamm_liste(array $liste, array $alt, string $was, callable $extra, string $praefix): array
{
    $out = []; $namen = [];
    $altIds = array_column($alt, 'id');
    foreach (array_values($liste) as $i => $x) {
        if (!is_array($x)) throw new InvalidArgumentException("$was: ungültige Angaben.");
        $w = $was . ' ' . ($i + 1);
        $name = rw_text($x['name'] ?? '', 60, "$w: Name");
        if ($name === '') throw new InvalidArgumentException("$w: bitte einen Namen angeben.");
        $k = mb_strtolower($name);
        if (isset($namen[$k])) throw new InvalidArgumentException("$was „{$name}“ gibt es zweimal.");
        $namen[$k] = true;
        $id = is_string($x['id'] ?? null) && $x['id'] !== '' ? $x['id'] : '';
        if ($id !== '' && !in_array($id, $altIds, true)) throw new InvalidArgumentException("$w: unbekannte Kennung.");
        $vorher = $id !== '' ? $alt[array_search($id, $altIds, true)] : [];
        $out[] = ['id' => $id !== '' ? $id : rw_id($praefix), 'name' => $name] + $extra($x, $w) + ['aktiv' => !array_key_exists('aktiv', $x) || !empty($x['aktiv'])] + $vorher;
    }
    $neuIds = array_column($out, 'id');
    foreach ($alt as $a) if (!in_array($a['id'], $neuIds, true)) throw new InvalidArgumentException("$was „{$a['name']}“ lässt sich nicht entfernen – bitte deaktivieren.");
    return $out;
}

/* ---------- Datenpaket (Übernahme der Excel-Listen) ---------- */
/* Paket prüfen: { format: "stafl-rewe", version: 1, lieferwege: [{id, name, art}], artikel?: [...],
   maerkte: [{kdNr, reweNr, name, strasse, plz, ort, region, telefon, kauf, hinweis, ansprechpartner, dauer,
              zustaendig: [{ab, liste}], lieferweg: [{ab, id}], wochen: {"JJJJ-WW": {s, m, n}}, notizen: [{art, text}]}] }
   $zuordnung: Listenname → Nutzer-ID (leer = niemand). Liefert Dokumente, Zahlen und Fehler je Markt. */
function rw_paket_pruefen($paket, $zuordnung, array $me): array
{
    $fehler = [];
    if (!is_array($paket) || ($paket['format'] ?? '') !== 'stafl-rewe' || (int)($paket['version'] ?? 0) !== 1)
        return ['fehler' => ['Kein REWE-Datenpaket (format „stafl-rewe“, Version 1).'], 'zahlen' => [], 'listen' => []];
    $zuordnung = is_array($zuordnung) ? $zuordnung : [];
    $stamm = ['lieferwege' => rw_grund_lieferwege(), 'artikel' => rw_grund_artikel()];
    try {
        if (isset($paket['artikel'])) $stamm['artikel'] = rw_stamm_pruefen(['artikel' => $paket['artikel']], ['artikel' => []] + $stamm)['artikel'];
        $lw = [];
        foreach ((array)($paket['lieferwege'] ?? []) as $i => $l) {
            $id = is_string($l['id'] ?? null) ? $l['id'] : '';
            if (!preg_match('/^[a-z0-9_-]{1,30}$/', $id)) throw new InvalidArgumentException('Lieferweg ' . ($i + 1) . ': ungültige Kennung.');
            $lw[$id] = ['id' => $id, 'name' => rw_text($l['name'] ?? '', 60, 'Lieferweg ' . ($i + 1)), 'art' => rw_wahl($l['art'] ?? '', array_keys(RW_LW_ARTEN), 'Lieferweg ' . ($i + 1) . ': Art'),
                        'bestellschluss' => rw_text($l['bestellschluss'] ?? RW_BESTELLSCHLUSS, 40, 'Lieferweg ' . ($i + 1) . ': Bestellschluss'), 'aktiv' => true];
        }
        foreach (rw_grund_lieferwege() as $g) if (!isset($lw[$g['id']])) $lw[$g['id']] = $g;
        $stamm['lieferwege'] = array_values($lw);
    } catch (InvalidArgumentException $e) { return ['fehler' => [$e->getMessage()], 'zahlen' => [], 'listen' => []]; }
    $personen = array_column(rw_personen(), 'name', 'id');
    $listen = [];
    $maerkte = []; $wochen = []; $notizen = []; $kdNrn = [];
    $z = ['maerkte' => 0, 'antworten' => 0, 'bestellungen' => 0, 'stueck' => 0, 'notizen' => 0, 'dauerauftraege' => 0, 'lieferwege' => count($stamm['lieferwege'])];
    $roh = is_array($paket['maerkte'] ?? null) ? array_values($paket['maerkte']) : [];
    if (count($roh) > RW_MAX_MAERKTE) return ['fehler' => ['Zu viele Märkte.'], 'zahlen' => [], 'listen' => []];
    foreach ($roh as $i => $p) {
        $w = 'Markt ' . ($i + 1) . (is_array($p) && !empty($p['ort']) ? ' (' . mb_substr((string)$p['ort'], 0, 40) . ')' : '');
        try {
            if (!is_array($p)) throw new InvalidArgumentException('ungültige Angaben');
            $id = rw_id('m');
            $f = rw_markt_felder(['name' => ($p['name'] ?? '') !== '' ? $p['name'] : ('REWE ' . ($p['ort'] ?? ''))] + array_intersect_key($p, array_flip(array_merge(RW_FELDER_STAMM, RW_FELDER_PFLEGE))), $stamm, []);
            if (($f['kdNr'] ?? '') !== '') {
                if (isset($kdNrn[$f['kdNr']])) throw new InvalidArgumentException('Kd.-Nr. ' . $f['kdNr'] . ' doppelt');
                $kdNrn[$f['kdNr']] = true;
            }
            $zu = [];
            foreach ((array)($p['zustaendig'] ?? []) as $h) {
                $liste = rw_text($h['liste'] ?? '', 60, 'Liste');
                $listen[$liste] = ($listen[$liste] ?? 0) + 1;
                $nutzer = is_string($zuordnung[$liste] ?? null) ? $zuordnung[$liste] : '';
                if ($nutzer !== '' && !isset($personen[$nutzer])) throw new InvalidArgumentException('Liste „' . $liste . '“: Mitarbeiter ohne „REWE ansehen“ oder unbekannt');
                $zu[] = ['ab' => rw_kw($h['ab'] ?? '', 'Zuständig ab'), 'nutzer' => $nutzer];
            }
            $lwh = [];
            foreach ((array)($p['lieferweg'] ?? []) as $h) {
                $lid = is_string($h['id'] ?? null) ? $h['id'] : '';
                if (!rw_lieferweg($stamm, $lid)) throw new InvalidArgumentException('unbekannter Lieferweg „' . mb_substr($lid, 0, 30) . '“');
                $lwh[] = ['ab' => rw_kw($h['ab'] ?? '', 'Lieferweg ab'), 'id' => $lid];
            }
            if (!$lwh) throw new InvalidArgumentException('ohne Lieferweg');
            usort($zu, function ($a, $b) { return strcmp($a['ab'], $b['ab']); });
            usort($lwh, function ($a, $b) { return strcmp($a['ab'], $b['ab']); });
            $m = ['id' => $id, 'rev' => 1] + $f + ['kauf' => 'regelmaessig', 'zustaendig' => $zu, 'lieferweg' => $lwh, 'erstellt' => rw_wer($me) + ['quelle' => 'datenpaket']];
            if (rw_dauer($m)['rhythmus'] > 0) $z['dauerauftraege']++;
            foreach ((array)($p['wochen'] ?? []) as $kw => $e) {
                $kw = rw_kw((string)$kw, 'Woche');
                if (!is_array($e)) throw new InvalidArgumentException("Woche $kw: ungültig");
                $s = rw_wahl($e['s'] ?? '', array_keys(RW_ANTWORTEN), "Woche $kw: Antwort");
                $mengen = $s === 'bestellt' ? rw_mengen($e['m'] ?? [], $stamm, "Woche $kw") : [];
                if ($s === 'bestellt' && !$mengen) throw new InvalidArgumentException("Woche $kw: bestellt ohne Menge");
                $notiz = rw_text($e['n'] ?? '', 300, "Woche $kw: Notiz");
                $zuKw = rw_ab($zu, $kw, 'nutzer');
                $wochen[(int)substr($kw, 0, 4)][$id][substr($kw, 5, 2)] = ['s' => $s] + ($mengen ? ['m' => $mengen] : []) + ($notiz !== '' ? ['n' => $notiz] : [])
                    + ['lw' => rw_ab($lwh, $kw, 'id'), 'zu' => $zuKw, 'zuName' => $personen[$zuKw] ?? rw_ab_liste($p, $kw), 'q' => 'excel', 'r' => 1, 't' => now(), 'von' => 'Excel-Liste', 'vonId' => ''];
                $z['antworten']++;
                if ($s === 'bestellt') { $z['bestellungen']++; $z['stueck'] += array_sum($mengen); }
            }
            foreach ((array)($p['notizen'] ?? []) as $n) {
                $text = rw_text($n['text'] ?? '', 2000, 'Notiz', true);
                if ($text === '') continue;
                $notizen[] = ['id' => rw_id('n'), 'markt' => $id, 'art' => rw_wahl($n['art'] ?? 'notiz', array_keys(RW_NOTIZ_ARTEN), 'Notiz: Art'), 'text' => $text, 'wv' => '',
                              'erledigt' => null, 'q' => 'datenpaket'] + rw_wer($me);
                $z['notizen']++;
            }
            $maerkte[] = $m;
            $z['maerkte']++;
        } catch (InvalidArgumentException $e) {
            $fehler[] = "$w: " . $e->getMessage();
            if (count($fehler) >= 100) { $fehler[] = 'Weitere Fehler nicht angezeigt.'; break; }
        }
    }
    ksort($listen);
    return ['fehler' => $fehler, 'zahlen' => $z, 'listen' => $listen, 'stamm' => $stamm, 'maerkte' => $maerkte, 'wochen' => $wochen, 'notizen' => $notizen];
}
function rw_ab_liste(array $p, string $kw): string
{
    $wert = '';
    foreach ((array)($p['zustaendig'] ?? []) as $h) if (($h['ab'] ?? '') <= $kw || $wert === '') $wert = (string)($h['liste'] ?? '');
    return $wert;
}
function rw_paket_uebernehmen(array $erg, bool $ersetzen): void
{
    if (!rw_leer() && !$ersetzen) fail('Im Modul sind schon Daten. Zum Ersetzen „Vorhandene Daten ersetzen“ wählen.', 409);
    foreach (rw_wochen_jahre() as $j) store_delete('rewe-wochen/' . $j);
    $alt = rw_stamm();
    rw_schreiben('rewe-stamm', ['rev' => $alt['rev'], 'lieferwege' => $erg['stamm']['lieferwege'], 'artikel' => $erg['stamm']['artikel'], 'team' => $alt['team']]);
    rw_schreiben('rewe-maerkte', ['rev' => rw_maerkte_doc()['rev'], 'liste' => $erg['maerkte']]);
    rw_schreiben('rewe-verlauf', ['rev' => rw_verlauf_doc()['rev'], 'liste' => $erg['notizen']]);
    foreach ($erg['wochen'] as $j => $maerkte) rw_wochen_schreiben((int)$j, ['rev' => 0, 'maerkte' => $maerkte, 'abschluss' => []]);
}
