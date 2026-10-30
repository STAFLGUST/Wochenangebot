<?php
declare(strict_types=1);
/* Qualitätssicherung · QM-System (IFS Wholesale): Daten und Regeln des Moduls „qs“ (Oberfläche qs.intern, Aktionen in
   app/api/aktionen/qs.php). Löst die Excel „QM-System“ ab: Blatt „Inhaltsverzeichnis“ = Dokumentenlenkung,
   „Managementsystem“ = QM-Handbuch, „Prüfungen“ = Prüfplan; dazu Nachweise der Prüfungen und Maßnahmen im Aufbau des
   IFS-Maßnahmenplans (Anforderung, Bewertung, Korrektur, Ursache, Korrekturmaßnahme, Freigabe, Wirksamkeit).

   Dokumentenlenkung nach Handbuch 1.1 (2.0.9–2.0.17):
     - gelenkte Dokumente (Arbeitsanweisung, Formblatt, Liste, Excel, Vorlage) haben Versionen; Ordner und externe Dokumente
       stehen nur im Register (ohne Versionen)
     - Ablauf einer Version: Entwurf → in Prüfung → geprüft → freigegeben; die Versionsnummer zählt erst bei der Freigabe um
       1 hoch, Datum = Freigabedatum; die vorige gültige Version wird „ersetzt“ (bleibt einsehbar)
     - 4-Augen-Prinzip: wer den Entwurf erstellt oder geändert hat, prüft ihn nicht (auch kein Administrator); Prüfen und
       Freigeben nur mit „qs.freigeben“; ein Entwurf nach dem anderen je Dokument
     - Überprüfung: nach N Monaten (Einstellung, Standard 36) seit der letzten Freigabe bzw. „ohne Änderung überprüft“ ist
       das Dokument zur Überprüfung fällig
   Prüfplan: tägliche, wöchentliche und monatliche Prüfungen folgen dem Kalender (jeder Arbeitstag Mo–Fr ohne Hamburger
   Feiertage, jede Kalenderwoche, jeder Monat): eine Periode ohne Nachweis ist versäumt und wird gezählt. Längere Intervalle
   rechnen ab dem letzten Nachweis (bzw. der ersten Fälligkeit). „Bei Bedarf“ hat keine Fälligkeit. Prüfungen sind
   Mitarbeitern zugewiesen (ausführende); wer nur „qs.nachweis“ hat, weist nur seine Prüfungen nach.
   Eigene Dokumente (alle Schreibvorgänge unter der Sperre „qs-dokumente“):
     qs-stamm       Kapitel, Personen (Kürzel, Name, Funktion, verknüpfter Mitarbeiter), Einstellungen
     qs-dokumente   gelenkte Dokumente mit Versionen und Verlauf
     qs-handbuch    Abschnitte des QM-Handbuchs je Kapitel mit Änderungsliste (Datum, was, Grund, von)
     qs-pruefplan   Prüfungen mit Intervall, ab wann, Sollwert, Maßnahme bei Abweichung, Zuständig, ausführende Mitarbeiter
     qs-nachweise   Durchführungen der Prüfungen; nie geändert oder gelöscht, nur storniert
     qs-massnahmen  Maßnahmen mit Nummer je Jahr, IFS-Feldern, Status und Wirksamkeitsprüfung
   Gelesen (Eigentümer Plattform, über users_load): Mitarbeiter für die Verknüpfung mit Kürzeln und die Zuweisung von
   Prüfungen (nur Kennung, Name, Zugang). Feiertage über hr_feiertag() des Moduls HR.
   Dokumentenablage (Dateien, lib/dateiablage.php, Bereich „qs“): gelenkte Dokumente tragen Dateien je Version
   (versionen[].dateien), Ordner und externe Dokumente am Dokument (dateien). Im Entwurf legt ab und entfernt, wer bearbeiten
   darf (er gilt damit als Bearbeiter – 4-Augen-Prinzip); in Prüfung und verworfen ist nichts änderbar; zu einer
   freigegebenen oder ersetzten Version trägt nur „qs.freigeben“ Dateien nach (z. B. die bisherige Datei aus dem Ordner
   „QM-System“). Außerhalb des Entwurfs wird nie gelöscht, nur „entfernt“ vermerkt (mit Grund; die Datei bleibt erhalten).
   Nummernstruktur (Anlegen und Ändern in der Oberfläche): Arbeitsanweisungen, Formblätter, Listen und Excel-Dokumente heißen
   „<Kapitel>-<Art><laufende Nr.>“ (z. B. 1.4-F08); leer = nächste freie Nummer (nie wiederverwendet, auch nicht von eingezogenen).
   Vorlagen und Lenkungsangaben (module/qs/vorlagen.php): neue Dokumente aus einer Vorlage (Art V), Platzhalter in Word/Excel,
   Lenkungsangaben bei der Freigabe, Übernahme der Dateien in eine Überarbeitung.
   Audit-Bericht (module/qs/bericht.php): Auswertung eines Zeitraums aus denselben Dokumenten, nur lesen.
   Zuständig/Vertreter sind Kürzel (Schnappschuss, GR-106). Gespeicherte Felder, die diese Fassung nicht kennt, bleiben beim
   Speichern erhalten (GR-006). Rechte (GR-103): qs.sehen, qs.nachweis, qs.bearbeiten, qs.freigeben, qs.verwalten. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const QS_ARTEN = ['A' => 'Arbeitsanweisung', 'F' => 'Formblatt', 'L' => 'Liste', 'E' => 'Excel', 'V' => 'Vorlage', 'X' => 'Externes Dokument', 'O' => 'Ordner'];
const QS_GELENKT = ['A', 'F', 'L', 'E', 'V'];
const QS_VER_STATUS = ['entwurf' => 'Entwurf', 'pruefung' => 'In Prüfung', 'geprueft' => 'Geprüft', 'freigegeben' => 'Freigegeben', 'ersetzt' => 'Ersetzt', 'verworfen' => 'Verworfen'];
const QS_VER_OFFEN = ['entwurf', 'pruefung', 'geprueft'];
const QS_INTERVALLE = ['arbeitstaeglich' => 'täglich (Arbeitstage Mo–Fr)', 'taeglich' => 'täglich (auch am Wochenende)', 'woechentlich' => 'wöchentlich',
                       'monatlich' => 'monatlich', 'quartal' => 'vierteljährlich', 'halbjahr' => 'halbjährlich', 'jaehrlich' => 'jährlich',
                       'zweijaehrlich' => 'alle 2 Jahre', 'dreijaehrlich' => 'alle 3 Jahre', 'anlass' => 'bei Bedarf (ohne Fälligkeit)'];
/* Kalender-Intervalle: Periode ohne Nachweis = versäumt; Fenster für Quote und Versäumnisse */
const QS_KALENDER = ['arbeitstaeglich' => 'tag', 'taeglich' => 'tag', 'woechentlich' => 'woche', 'monatlich' => 'monat'];
const QS_KALENDER_FENSTER = ['tag' => 30, 'woche' => 84, 'monat' => 365];   // Tage zurück für die Quote
const QS_ROLLEND = ['quartal' => 3, 'halbjahr' => 6, 'jaehrlich' => 12, 'zweijaehrlich' => 24, 'dreijaehrlich' => 36];   // Monate
const QS_VORLAUF = ['quartal' => 14];
const QS_VORLAUF_STANDARD = 30;
const QS_MAX_VERSAEUMT = 400;
const QS_ERGEBNIS = ['io' => 'In Ordnung', 'abweichung' => 'Abweichung'];
const QS_QUELLEN = ['intern' => 'Internes Audit', 'extern' => 'Externes Audit (IFS)', 'kunde' => 'Kundenaudit', 'behoerde' => 'Behörde / Veterinär',
                    'pruefung' => 'Prüfplan', 'reklamation' => 'Reklamation', 'review' => 'Management-Review', 'sonstige' => 'Sonstige'];
const QS_BEWERTUNG = ['', 'A', 'B', 'C', 'D', 'Major', 'KO'];
const QS_MASSN_STATUS = ['offen' => 'Offen', 'in_arbeit' => 'In Arbeit', 'umgesetzt' => 'Umgesetzt', 'wirksam' => 'Wirksam (abgeschlossen)', 'verworfen' => 'Verworfen'];
const QS_MASSN_ABGESCHLOSSEN = ['wirksam', 'verworfen'];
const QS_UEBERPRUEFUNG_STANDARD = 36;   // Monate seit der letzten Freigabe bzw. Überprüfung
const QS_MAX_KAPITEL = 100;
const QS_MAX_PERSONEN = 300;
const QS_MAX_DOKUMENTE = 5000;
const QS_MAX_VERSIONEN = 200;
const QS_MAX_ABSCHNITTE = 5000;
const QS_MAX_PRUEFUNGEN = 1000;
const QS_MAX_AUSFUEHRENDE = 50;
const QS_MAX_NACHWEISE = 100000;
const QS_MAX_MASSNAHMEN = 20000;
const QS_MAX_AENDERUNGEN = 200;
const QS_MAX_VERLAUF = 100;
const QS_MAX_VERWEISE = 20;
const QS_START_NACHWEISE = 5000;   // qs_start liefert die neuesten Nachweise (Fälligkeiten rechnet der Server aus allen)
const QS_MAX_DATEIEN = 50;         // aktive Dateien je Version bzw. je Ordner/externem Dokument
const QS_NR_STRUKTUR = ['A', 'F', 'L', 'E'];   // Nummer „<Kapitel>-<Art><laufende Nr.>“ (z. B. 1.4-F08); Vorlagen „V“ heißen frei (z. B. „Vorlage F“)

/* ---------- Laden und Schreiben ---------- */
function qs_stamm(): array
{
    $d = store_read('qs-stamm');
    $d = is_array($d) ? $d : [];
    $out = ['rev' => (int)($d['rev'] ?? 0)];
    $out['kapitel'] = is_array($d['kapitel'] ?? null) ? array_values($d['kapitel']) : [];
    $out['personen'] = is_array($d['personen'] ?? null) ? array_values($d['personen']) : [];
    $e = is_array($d['einstellungen'] ?? null) ? $d['einstellungen'] : [];
    $out['einstellungen'] = ['ueberpruefungMonate' => (int)($e['ueberpruefungMonate'] ?? QS_UEBERPRUEFUNG_STANDARD)] + $e;
    return $out + $d;
}
function qs_doc(string $name): array
{
    $d = store_read($name);
    return ['rev' => (int)($d['rev'] ?? 0), 'liste' => is_array($d['liste'] ?? null) ? array_values($d['liste']) : []] + (is_array($d) ? $d : []);
}
function qs_schreiben(string $name, array $doc): void
{
    $doc['rev'] = (int)($doc['rev'] ?? 0) + 1;
    $doc['updatedAt'] = now();
    store_write($name, $doc);
}
function qs_id(string $praefix): string { return $praefix . bin2hex(random_bytes(6)); }
function qs_wer(array $me): array { return ['t' => now(), 'von' => (string)$me['name'], 'vonId' => (string)$me['id']]; }
function qs_verlauf(array &$e, array $me, string $was): void
{
    $e['verlauf'] = is_array($e['verlauf'] ?? null) ? $e['verlauf'] : [];
    $e['verlauf'][] = ['t' => now(), 'von' => (string)$me['name'], 'was' => $was];
    if (count($e['verlauf']) > QS_MAX_VERLAUF) $e['verlauf'] = array_slice($e['verlauf'], -QS_MAX_VERLAUF);
}
function qs_heute(): string { return date('Y-m-d'); }
/* Ist das Modul noch leer (für den Import ohne „ersetzen“)? */
function qs_leer(): bool
{
    $s = qs_stamm();
    if ($s['kapitel'] || $s['personen']) return false;
    foreach (['qs-dokumente', 'qs-handbuch', 'qs-pruefplan', 'qs-nachweise', 'qs-massnahmen'] as $n) if (qs_doc($n)['liste']) return false;
    return true;
}
/* Kapitel- und Abschnittsnummern natürlich sortieren („1.2“ vor „1.10“, „2.0.9“ vor „2.0.10“) */
function qs_nat_cmp(string $a, string $b): int
{
    $x = preg_split('/[.\s-]+/', trim($a)) ?: []; $y = preg_split('/[.\s-]+/', trim($b)) ?: [];
    for ($i = 0; $i < max(count($x), count($y)); $i++) {
        $p = $x[$i] ?? null; $q = $y[$i] ?? null;
        if ($p === null) return -1;
        if ($q === null) return 1;
        $c = (ctype_digit($p) && ctype_digit($q)) ? ((int)$p <=> (int)$q) : strnatcasecmp($p, $q);
        if ($c !== 0) return $c;
    }
    return 0;
}

/* ---------- Mitarbeiter (Plattformkern, nur lesen) ---------- */
/* Wählbare Mitarbeiter: aktive Zugänge und Mitarbeiter ohne Anmeldung (z. B. Lager); deaktivierte Zugänge nicht */
function qs_mitarbeiter(): array
{
    $out = [];
    foreach (users_load() as $u) {
        $ohne = ($u['zugang'] ?? true) === false;
        if (empty($u['active']) && !$ohne) continue;
        $out[] = ['id' => (string)$u['id'], 'name' => (string)($u['name'] ?? $u['username'] ?? ''), 'zugang' => !$ohne];
    }
    usort($out, function ($a, $b) { return strnatcasecmp($a['name'], $b['name']); });
    return $out;
}
/* Kürzel, die mit einem Mitarbeiter verknüpft sind */
function qs_kuerzel_von(array $stamm, string $userId): array
{
    $k = [];
    foreach ($stamm['personen'] as $p) if ($userId !== '' && (string)($p['mitarbeiter'] ?? '') === $userId) $k[] = (string)$p['id'];
    return $k;
}
/* Ist der Mitarbeiter für die Prüfung eingeteilt (ausführend oder über sein Kürzel zuständig/Vertreter)? */
function qs_pruefung_meine(array $p, array $stamm, string $userId): bool
{
    if (in_array($userId, array_map('strval', (array)($p['ausfuehrende'] ?? [])), true)) return true;
    $k = qs_kuerzel_von($stamm, $userId);
    return $k && (in_array((string)($p['zustaendig'] ?? ''), $k, true) || in_array((string)($p['vertreter'] ?? ''), $k, true));
}

/* ---------- Prüfen der Eingaben ---------- */
function qs_text($v, int $max, string $was): string
{
    if ($v !== null && !is_string($v) && !is_int($v) && !is_float($v)) throw new InvalidArgumentException("$was: ungültiger Wert.");
    $t = trim(str_replace("\r", '', (string)$v));
    $t = preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', $t) ?? '';
    if (mb_strlen($t) > $max) throw new InvalidArgumentException("$was: höchstens $max Zeichen.");
    return $t;
}
function qs_datum($v, string $was, bool $pflicht = true): string
{
    $v = is_string($v) ? trim($v) : '';
    if ($v === '') { if ($pflicht) throw new InvalidArgumentException("$was: bitte ein Datum angeben."); return ''; }
    if (!preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $m) || !checkdate((int)$m[2], (int)$m[3], (int)$m[1]) || (int)$m[1] < 1990 || (int)$m[1] > 2099)
        throw new InvalidArgumentException("$was: bitte ein gültiges Datum angeben.");
    return $v;
}
function qs_wahl($v, array $erlaubt, string $was): string
{
    $v = is_string($v) ? trim($v) : '';
    if (!in_array($v, $erlaubt, true)) throw new InvalidArgumentException("$was: ungültige Auswahl.");
    return $v;
}
/* Kürzel einer Person (Zuständig, Vertreter, erstellt …): kurz, ohne Zeilenumbruch; muss nicht in der Personenliste stehen
   (ältere Einträge nennen auch Dienstleister wie „H&M“ oder „TE / Maler“) */
function qs_kuerzel($v, string $was, int $max = 40): string
{
    $t = qs_text($v, $max, $was);
    if (strpos($t, "\n") !== false) throw new InvalidArgumentException("$was: bitte ohne Zeilenumbruch.");
    return $t;
}
function qs_kapitel_pruefen($v, array $stamm, string $was = 'Kapitel', bool $pflicht = true): string
{
    $k = is_string($v) ? rtrim(trim($v), '.') : '';
    if ($k === '') { if ($pflicht) throw new InvalidArgumentException("$was: bitte ein Kapitel wählen."); return ''; }
    foreach ($stamm['kapitel'] as $x) if ((string)$x['id'] === $k) return $k;
    throw new InvalidArgumentException("$was: unbekanntes Kapitel „" . mb_substr($k, 0, 20) . '“.');
}
function qs_ablage($v): string
{
    $t = qs_text($v, 500, 'Ablage');
    if (strpos($t, "\n") !== false) throw new InvalidArgumentException('Ablage: bitte ohne Zeilenumbruch.');
    // Verweise nur als Pfad oder http(s)-Adresse – nie „javascript:“ o. Ä. (die Oberfläche verlinkt nur http(s))
    if (preg_match('/^[a-z][a-z0-9+.-]*:/i', $t) && !preg_match('~^https?://~i', $t) && !preg_match('/^[a-z]:[\\\\\/]/i', $t))
        throw new InvalidArgumentException('Ablage: bitte einen Ordnerpfad oder eine http(s)-Adresse angeben.');
    return $t;
}
function qs_verweise($v): array
{
    if ($v === null || $v === '') return [];
    if (is_string($v)) $v = preg_split('/\n+/', $v) ?: [];
    if (!is_array($v)) throw new InvalidArgumentException('Wo? Womit?: ungültige Angaben.');
    $out = [];
    foreach ($v as $x) {
        $t = qs_text($x, 300, 'Wo? Womit?');
        $t = preg_replace('/\s+/u', ' ', $t) ?? $t;
        if ($t !== '' && !in_array($t, $out, true)) $out[] = $t;
    }
    if (count($out) > QS_MAX_VERWEISE) throw new InvalidArgumentException('Wo? Womit?: höchstens ' . QS_MAX_VERWEISE . ' Verweise.');
    return $out;
}
/* Liste von Mitarbeiter-Kennungen (nur bekannte, ohne doppelte) */
function qs_mitarbeiter_liste($v, array $erlaubt, string $was): array
{
    if ($v === null || $v === '') return [];
    if (!is_array($v)) throw new InvalidArgumentException("$was: ungültige Angaben.");
    $ids = array_column($erlaubt, 'id');
    $out = [];
    foreach ($v as $x) {
        $x = is_string($x) ? trim($x) : '';
        if (!in_array($x, $ids, true)) throw new InvalidArgumentException("$was: unbekannter Mitarbeiter.");
        if (!in_array($x, $out, true)) $out[] = $x;
    }
    if (count($out) > QS_MAX_AUSFUEHRENDE) throw new InvalidArgumentException("$was: höchstens " . QS_MAX_AUSFUEHRENDE . ' Mitarbeiter.');
    return $out;
}

/* ---------- Datum ---------- */
function qs_dt(string $d): DateTimeImmutable { return new DateTimeImmutable($d . ' 12:00:00', new DateTimeZone('UTC')); }
function qs_plus_tage(string $d, int $n): string { return qs_dt($d)->modify(($n >= 0 ? '+' : '') . $n . ' days')->format('Y-m-d'); }
function qs_monatstage(int $j, int $m): int { return (int)qs_dt(sprintf('%04d-%02d-01', $j, $m))->format('t'); }
/* Datum + Monate ohne Überlauf (31.01. + 1 Monat = 28./29.02.) */
function qs_plus_monate(string $d, int $monate): string
{
    $x = qs_dt($d);
    $i = (int)$x->format('Y') * 12 + (int)$x->format('n') - 1 + $monate;   // Monate seit Jahr 0 (auch rückwärts über den Jahreswechsel)
    $j = intdiv($i, 12); $m = $i % 12 + 1; $t = (int)$x->format('j');
    return sprintf('%04d-%02d-%02d', $j, $m, min($t, qs_monatstage($j, $m)));
}
function qs_tage_bis(string $von, string $bis): int { return (int)round((qs_dt($bis)->getTimestamp() - qs_dt($von)->getTimestamp()) / 86400); }
function qs_feiertag(string $d): bool { return function_exists('hr_feiertag') && hr_feiertag($d) !== null; }   // Hamburg (Modul HR)
function qs_arbeitstag(string $d): bool { return (int)qs_dt($d)->format('N') <= 5 && !qs_feiertag($d); }

/* ---------- Stammdaten: Kapitel, Personen, Einstellungen ---------- */
function qs_kapitel_liste_pruefen($v, array $alt, array $benutzt): array
{
    if (!is_array($v)) throw new InvalidArgumentException('Kapitel: ungültige Angaben.');
    if (count($v) > QS_MAX_KAPITEL) throw new InvalidArgumentException('Kapitel: höchstens ' . QS_MAX_KAPITEL . ' Einträge.');
    $altNach = []; foreach ($alt as $a) if (is_array($a) && isset($a['id'])) $altNach[(string)$a['id']] = $a;
    $out = []; $ids = [];
    foreach (array_values($v) as $i => $x) {
        if (!is_array($x)) throw new InvalidArgumentException('Kapitel: ungültige Angaben.');
        $id = rtrim(qs_text($x['id'] ?? '', 12, 'Kapitel ' . ($i + 1)), '.');
        if (!preg_match('/^\d{1,2}(\.\d{1,2}){0,2}$/', $id)) throw new InvalidArgumentException('Kapitel ' . ($i + 1) . ': Nummer wie „1.4“ angeben.');
        if (in_array($id, $ids, true)) throw new InvalidArgumentException("Kapitel $id ist doppelt.");
        $ids[] = $id;
        $row = $altNach[$id] ?? [];
        $row['id'] = $id;
        $row['titel'] = qs_text($x['titel'] ?? '', 120, "Kapitel $id");
        if ($row['titel'] === '') throw new InvalidArgumentException("Kapitel $id: bitte einen Titel angeben.");
        $row['zustaendig'] = qs_kuerzel($x['zustaendig'] ?? '', "Kapitel $id: Zuständig");
        $row['vertreter'] = qs_kuerzel($x['vertreter'] ?? '', "Kapitel $id: Vertreter");
        $row['aktiv'] = !array_key_exists('aktiv', $x) || !empty($x['aktiv']);
        $out[] = $row;
    }
    foreach ($altNach as $id => $a) if (!in_array((string)$id, $ids, true) && isset($benutzt[(string)$id]))
        throw new InvalidArgumentException("Kapitel $id wird verwendet und kann nicht entfernt werden – bitte deaktivieren.");
    usort($out, function ($a, $b) { return qs_nat_cmp($a['id'], $b['id']); });
    return $out;
}
/* Personen mit Kürzel; „mitarbeiter“ verknüpft das Kürzel mit einem Mitarbeiterkonto der Plattform (je Mitarbeiter höchstens
   ein Kürzel). $mitarbeiter = null: ohne Prüfung der Verknüpfung (Datenpaket, dort gibt es keine Verknüpfungen). */
function qs_personen_pruefen($v, array $alt, ?array $mitarbeiter): array
{
    if (!is_array($v)) throw new InvalidArgumentException('Personen: ungültige Angaben.');
    if (count($v) > QS_MAX_PERSONEN) throw new InvalidArgumentException('Personen: höchstens ' . QS_MAX_PERSONEN . ' Einträge.');
    $altNach = []; foreach ($alt as $a) if (is_array($a) && isset($a['id'])) $altNach[(string)$a['id']] = $a;
    $out = []; $ids = []; $verknuepft = [];
    $mIds = $mitarbeiter === null ? [] : array_column($mitarbeiter, 'id');
    foreach (array_values($v) as $i => $x) {
        if (!is_array($x)) throw new InvalidArgumentException('Personen: ungültige Angaben.');
        $id = qs_kuerzel($x['id'] ?? '', 'Person ' . ($i + 1) . ': Kürzel');
        if ($id === '' || mb_strlen($id) > 12) throw new InvalidArgumentException('Person ' . ($i + 1) . ': Kürzel mit 1 bis 12 Zeichen angeben.');
        foreach ($ids as $schon) if (mb_strtolower($schon) === mb_strtolower($id)) throw new InvalidArgumentException("Kürzel „{$id}“ ist doppelt.");
        $ids[] = $id;
        $row = $altNach[$id] ?? [];
        $row['id'] = $id;
        $row['name'] = qs_text($x['name'] ?? '', 100, "Person $id: Name");
        if ($row['name'] === '') throw new InvalidArgumentException("Person „{$id}“: bitte einen Namen angeben.");
        $row['funktion'] = qs_text($x['funktion'] ?? '', 100, "Person $id: Funktion");
        $m = $mitarbeiter === null ? '' : (is_string($x['mitarbeiter'] ?? null) ? trim($x['mitarbeiter']) : '');
        if ($m !== '' && !in_array($m, $mIds, true)) throw new InvalidArgumentException("Person „{$id}“: unbekannter Mitarbeiter.");
        if ($m !== '' && isset($verknuepft[$m])) throw new InvalidArgumentException("Ein Mitarbeiter kann nur mit einem Kürzel verknüpft sein („{$verknuepft[$m]}“ und „{$id}“).");
        if ($m !== '') $verknuepft[$m] = $id;
        $row['mitarbeiter'] = $m;
        $row['aktiv'] = !array_key_exists('aktiv', $x) || !empty($x['aktiv']);
        $out[] = $row;
    }
    return $out;
}
function qs_einstellungen_pruefen($v, array $alt): array
{
    if (!is_array($v)) throw new InvalidArgumentException('Einstellungen: ungültige Angaben.');
    $m = $v['ueberpruefungMonate'] ?? $alt['ueberpruefungMonate'] ?? QS_UEBERPRUEFUNG_STANDARD;
    if (is_string($m) && ctype_digit(trim($m))) $m = (int)trim($m);
    if (!is_int($m) || $m < 6 || $m > 120) throw new InvalidArgumentException('Überprüfung der Dokumente: bitte 6 bis 120 Monate angeben.');
    return ['ueberpruefungMonate' => $m] + $alt;
}
/* Welche Kapitel werden von Dokumenten, Abschnitten, Prüfungen oder Maßnahmen verwendet? */
function qs_kapitel_benutzt(): array
{
    $b = [];
    foreach (['qs-dokumente', 'qs-handbuch', 'qs-pruefplan', 'qs-massnahmen'] as $n) foreach (qs_doc($n)['liste'] as $e) if (($e['kapitel'] ?? '') !== '') $b[(string)$e['kapitel']] = true;
    return $b;
}

/* ---------- Dokumente und Versionen ---------- */
/* $struktur: Nummernstruktur durchsetzen (Anlegen und Ändern in der Oberfläche; nicht beim Datenpaket aus der Excel) –
   neue Dokumente der Arten A, F, L, E und geänderte Nummern, Kapitel oder Arten folgen „<Kapitel>-<Art><Nr.>“, leer = nächste freie */
function qs_dokument_pruefen(array $b, ?array $alt, array $stamm, array $alle, bool $struktur = false): array
{
    $row = $alt ?? [];
    $row['art'] = qs_wahl($b['art'] ?? ($alt['art'] ?? 'F'), array_keys(QS_ARTEN), 'Art');
    if ($alt !== null && ($alt['art'] ?? '') !== $row['art'] && in_array($alt['art'] ?? '', QS_GELENKT, true) !== in_array($row['art'], QS_GELENKT, true) && !empty($alt['versionen']))
        throw new InvalidArgumentException('Ein Dokument mit Versionen kann nicht zu einem Ordner oder externen Dokument werden (und umgekehrt).');
    if ($alt !== null && in_array($alt['art'] ?? '', QS_GELENKT, true) !== in_array($row['art'], QS_GELENKT, true) && qs_dateien_aktiv($alt['dateien'] ?? []))
        throw new InvalidArgumentException('In der Ablage des Dokuments liegen Dateien – es kann nicht zu einem gelenkten Dokument werden.');
    $row['kapitel'] = qs_kapitel_pruefen($b['kapitel'] ?? '', $stamm);
    $row['nr'] = qs_text($b['nr'] ?? '', 40, 'Dokumenten-Nr.');
    if (strpos($row['nr'], "\n") !== false) throw new InvalidArgumentException('Dokumenten-Nr.: bitte ohne Zeilenumbruch.');
    $gelenkt = in_array($row['art'], QS_GELENKT, true);
    if ($struktur && in_array($row['art'], QS_NR_STRUKTUR, true) && ($alt === null || $row['nr'] !== (string)($alt['nr'] ?? '')
            || $row['kapitel'] !== (string)($alt['kapitel'] ?? '') || $row['art'] !== (string)($alt['art'] ?? '')))
        $row['nr'] = qs_nr_struktur($row['nr'], $row['kapitel'], $row['art'], $alle, $alt);
    if ($gelenkt && $row['nr'] === '') throw new InvalidArgumentException($row['art'] === 'V' ? 'Bitte eine Bezeichnung angeben (z. B. „Vorlage F“).' : 'Bitte eine Dokumenten-Nr. angeben (z. B. „1.4-F08“).');
    if ($row['nr'] !== '') foreach ($alle as $d) if (($alt === null || $d['id'] !== $alt['id']) && mb_strtolower((string)($d['nr'] ?? '')) === mb_strtolower($row['nr']))
        throw new InvalidArgumentException("Die Dokumenten-Nr. „{$row['nr']}“ gibt es schon.");
    $row['titel'] = qs_text($b['titel'] ?? '', 200, 'Titel');
    if ($row['titel'] === '') throw new InvalidArgumentException('Bitte einen Titel angeben.');
    $row['ablage'] = qs_ablage($b['ablage'] ?? '');
    $row['zustaendig'] = qs_kuerzel($b['zustaendig'] ?? '', 'Zuständig');
    $row['vertreter'] = qs_kuerzel($b['vertreter'] ?? '', 'Vertreter');
    $row['notiz'] = qs_text($b['notiz'] ?? '', 2000, 'Notiz');
    $row['versionen'] = is_array($row['versionen'] ?? null) ? array_values($row['versionen']) : [];
    if (!array_key_exists('eingezogen', $row)) $row['eingezogen'] = null;
    if (!array_key_exists('ueberprueft', $row)) $row['ueberprueft'] = null;
    return $row;
}
/* ---------- Nummernstruktur ---------- */
function qs_nr_naechste(array $alle, string $kap, string $art, ?array $ohne = null): string
{
    $re = '/^' . preg_quote($kap, '/') . '-' . $art . '(\d+)/i';
    $max = 0;
    foreach ($alle as $d) {
        if ($ohne !== null && ($d['id'] ?? '') === ($ohne['id'] ?? null)) continue;
        if (preg_match($re, (string)($d['nr'] ?? ''), $m)) $max = max($max, (int)$m[1]);
    }
    if ($max >= 999) throw new InvalidArgumentException("Im Kapitel $kap ist keine Nummer der Art $art mehr frei.");
    return $kap . '-' . $art . str_pad((string)($max + 1), 2, '0', STR_PAD_LEFT);
}
/* Nummer prüfen bzw. vergeben (leer = nächste freie); Art in Großbuchstaben */
function qs_nr_struktur(string $nr, string $kap, string $art, array $alle, ?array $alt): string
{
    if ($nr === '') return qs_nr_naechste($alle, $kap, $art, $alt);
    if (!preg_match('/^' . preg_quote($kap, '/') . '-' . $art . '(\d{2,3})$/iD', $nr, $m))
        throw new InvalidArgumentException('Die Dokumenten-Nr. folgt der Struktur Kapitel-Art-laufende Nummer – hier z. B. „' . qs_nr_naechste($alle, $kap, $art, $alt)
            . '“. Leer lassen: dann vergibt das System die nächste freie Nummer.');
    return $kap . '-' . $art . $m[1];
}
function qs_dokument_index(array $doc, $id): int
{
    $id = is_string($id) ? $id : '';
    foreach ($doc['liste'] as $i => $e) if (($e['id'] ?? '') === $id && $id !== '') return $i;
    fail('Dokument nicht gefunden.', 404);
    return -1;
}
/* Index der gültigen (freigegebenen) bzw. der offenen Version (Entwurf, in Prüfung, geprüft) oder null */
function qs_ver_index(array $d, array $status): ?int
{
    $treffer = null;
    foreach ((array)($d['versionen'] ?? []) as $i => $v) if (in_array($v['status'] ?? '', $status, true)) $treffer = $i;
    return $treffer;
}
function qs_naechste_nr(array $d): int
{
    $n = 0;
    foreach ((array)($d['versionen'] ?? []) as $v) if (is_int($v['nr'] ?? null) || ctype_digit((string)($v['nr'] ?? ''))) $n = max($n, (int)$v['nr']);
    return $n + 1;
}
/* Zustand eines Dokuments für Übersicht und Filter */
function qs_dok_status(array $d): string
{
    if (!empty($d['eingezogen'])) return 'eingezogen';
    if (!in_array($d['art'] ?? '', QS_GELENKT, true)) return 'register';
    $o = qs_ver_index($d, QS_VER_OFFEN);
    if ($o !== null) return $d['versionen'][$o]['status'] === 'entwurf' ? 'entwurf' : 'pruefung';
    return qs_ver_index($d, ['freigegeben']) !== null ? 'gueltig' : 'ohne';
}
/* Überprüfung: seit (letzte Freigabe oder „ohne Änderung überprüft“), fällig ab (+ N Monate), fällig ja/nein.
   Nur für gültige, nicht eingezogene gelenkte Dokumente; ohne Freigabedatum gilt die Überprüfung als fällig. */
function qs_ueberpruefung(array $d, int $monate, string $heute): ?array
{
    if (!empty($d['eingezogen']) || !in_array($d['art'] ?? '', QS_GELENKT, true)) return null;
    $g = qs_ver_index($d, ['freigegeben']);
    if ($g === null) return null;
    $seit = (string)($d['versionen'][$g]['datum'] ?? '');
    $u = substr((string)($d['ueberprueft']['t'] ?? ''), 0, 10);
    if ($u !== '' && $u > $seit) $seit = $u;
    if ($seit === '') return ['seit' => '', 'faelligAb' => '', 'faellig' => true];
    $ab = qs_plus_monate($seit, $monate);
    return ['seit' => $seit, 'faelligAb' => $ab, 'faellig' => $ab <= $heute];
}
function qs_dok_aus(array $d, int $monate, string $heute): array
{
    return $d + ['zustand' => qs_dok_status($d), 'ueberpruefung' => qs_ueberpruefung($d, $monate, $heute)];
}
/* Neuer Entwurf (Version ohne Nummer) */
function qs_entwurf(array $me, string $aenderungen, string $grund): array
{
    $v = ['id' => qs_id('v'), 'nr' => null, 'datum' => '', 'status' => 'entwurf', 'aenderungen' => $aenderungen, 'grund' => $grund,
          'erstellt' => qs_wer($me), 'bearbeiter' => [(string)$me['id']], 'geprueft' => null, 'freigegeben' => null, 'kuerzel' => null, 'quelle' => 'hand', 'verlauf' => []];
    qs_verlauf($v, $me, 'Entwurf erstellt');
    return $v;
}

/* ---------- Dokumentenablage ---------- */
function qs_dateien_aktiv($liste): array
{
    return array_values(array_filter(is_array($liste) ? $liste : [], function ($f) { return is_array($f) && empty($f['entfernt']); }));
}
/* Darf $me an dieser Stelle (Dokument, Version-ID oder '' für Ordner/externe Dokumente) Dateien ablegen bzw. entfernen?
   Rückgabe: Index der Version oder null (Ablage am Dokument); sonst fail(). */
function qs_ablage_stelle(array $d, string $ver, array $me, string $was): ?int
{
    if (!empty($d['eingezogen'])) fail('Das Dokument ist eingezogen – die Ablage ist geschlossen.', 409);
    if (!in_array($d['art'] ?? '', QS_GELENKT, true)) {
        if ($ver !== '') fail('Ordner und externe Dokumente haben keine Versionen.', 422);
        if ($was === 'hochladen' && count(qs_dateien_aktiv($d['dateien'] ?? [])) >= QS_MAX_DATEIEN) fail('Zu viele Dateien (höchstens ' . QS_MAX_DATEIEN . ').', 422);
        return null;
    }
    $vi = null;
    foreach ((array)($d['versionen'] ?? []) as $i => $v) if (($v['id'] ?? '') === $ver && $ver !== '') $vi = $i;
    if ($vi === null) fail('Version nicht gefunden.', 404);
    $st = (string)$d['versionen'][$vi]['status'];
    if (in_array($st, ['pruefung', 'geprueft'], true)) fail('Die Überarbeitung liegt zur Prüfung vor – Dateien lassen sich nur im Entwurf ändern (zurückgeben lassen).', 409);
    if ($st === 'verworfen') fail('Die Version ist verworfen.', 409);
    if (in_array($st, ['freigegeben', 'ersetzt'], true) && !may($me, 'qs.freigeben'))
        fail('Dateien einer freigegebenen Version trägt nur nach oder entfernt, wer prüfen und freigeben darf.', 403);
    if ($was === 'hochladen' && count(qs_dateien_aktiv($d['versionen'][$vi]['dateien'] ?? [])) >= QS_MAX_DATEIEN) fail('Zu viele Dateien (höchstens ' . QS_MAX_DATEIEN . ').', 422);
    return $vi;
}
/* Einstellungen für die Oberfläche: erlaubte Dateiendungen, Höchstgröße je Datei und je Teilstück, Dateien je Stelle */
function qs_ablage_einstellungen(): array
{
    require_once __DIR__ . '/vorlagen.php';
    return ['arten' => array_keys(ABLAGE_ARTEN), 'max' => ABLAGE_DATEI_MAX, 'teil' => ABLAGE_TEIL_MAX, 'dateien' => QS_MAX_DATEIEN,
            'office' => array_keys(QS_OFFICE), 'platzhalter' => QS_PLATZHALTER_TEXT, 'nrStruktur' => QS_NR_STRUKTUR];
}
/* Datei in allen Dokumenten suchen: [Dokument-Index, Version-Index oder null, Datei-Index] oder null */
function qs_datei_finden(array $liste, string $id): ?array
{
    if (!preg_match('/^[a-z0-9]{12,40}$/D', $id)) return null;
    foreach ($liste as $i => $d) {
        foreach ((array)($d['dateien'] ?? []) as $k => $f) if (($f['id'] ?? '') === $id) return [$i, null, $k];
        foreach ((array)($d['versionen'] ?? []) as $j => $v) foreach ((array)($v['dateien'] ?? []) as $k => $f) if (($f['id'] ?? '') === $id) return [$i, $j, $k];
    }
    return null;
}
/* Liegt an dieser Stelle (Version bzw. Dokument) schon eine aktive Datei mit diesem Inhalt (SHA-256, auch Rohfassung)? Kennung oder null */
function qs_datei_gleich(array $d, ?int $vi, string $sha): ?string
{
    if (!preg_match('/^[0-9a-f]{64}$/D', $sha)) return null;
    foreach (qs_dateien_aktiv($vi === null ? ($d['dateien'] ?? []) : ($d['versionen'][$vi]['dateien'] ?? [])) as $f)
        if (hash_equals($sha, (string)($f['sha256'] ?? '')) || hash_equals($sha, (string)($f['sha256Roh'] ?? ''))) return (string)$f['id'];
    return null;
}
function qs_dateien_zahl(array $liste): int
{
    $n = 0;
    foreach ($liste as $d) {
        $n += count(qs_dateien_aktiv($d['dateien'] ?? []));
        foreach ((array)($d['versionen'] ?? []) as $v) $n += count(qs_dateien_aktiv($v['dateien'] ?? []));
    }
    return $n;
}
/* Einträge für den ZIP-Export „QM-System/<Kapitel>/<Dokument>/<Datei>“: gültige Version (bzw. Dateien von Ordnern und
   externen Dokumenten); mit $alle zusätzlich ältere Versionen und offene Entwürfe in Unterordnern. Eingezogene Dokumente
   nur mit $alle (Ordner „_eingezogen“). Dazu die Dokumentenliste als CSV. */
function qs_ablage_eintraege(array $dokumente, array $stamm, string $kapitel, bool $alle, string $heute): array
{
    $kt = []; foreach ($stamm['kapitel'] as $k) $kt[(string)$k['id']] = (string)$k['titel'];
    $wurzel = 'QM-System';
    $e = [];
    $gewaehlt = array_values(array_filter($dokumente, function ($d) use ($kapitel) { return $kapitel === '' || (string)$d['kapitel'] === $kapitel; }));
    usort($gewaehlt, function ($a, $b) { return qs_nat_cmp((string)$a['kapitel'], (string)$b['kapitel']) ?: strnatcasecmp((string)$a['nr'], (string)$b['nr']); });
    foreach ($gewaehlt as $d) {
        $eingezogen = !empty($d['eingezogen']);
        if ($eingezogen && !$alle) continue;
        $kap = ablage_zip_pfad(trim($d['kapitel'] . ' ' . ($kt[$d['kapitel']] ?? '')));
        $ordner = $wurzel . '/' . ($eingezogen ? '_eingezogen/' : '') . $kap . '/' . ablage_zip_pfad(trim(($d['nr'] !== '' ? $d['nr'] . ' ' : '') . $d['titel']));
        foreach (qs_dateien_aktiv($d['dateien'] ?? []) as $f) $e[] = ['pfad' => $ordner . '/' . ablage_zip_pfad((string)$f['name']), 'bereich' => 'qs', 'id' => (string)$f['id']];
        foreach ((array)($d['versionen'] ?? []) as $v) {
            $st = (string)($v['status'] ?? '');
            if ($st === 'freigegeben') $unter = '';
            elseif (!$alle || $st === 'verworfen') continue;
            elseif ($st === 'ersetzt') $unter = '/_ältere Versionen/Version ' . ($v['nr'] ?? '?');
            else $unter = '/_Entwurf';
            foreach (qs_dateien_aktiv($v['dateien'] ?? []) as $f) $e[] = ['pfad' => $ordner . $unter . '/' . ablage_zip_pfad((string)$f['name']), 'bereich' => 'qs', 'id' => (string)$f['id']];
        }
    }
    array_unshift($e, ['pfad' => $wurzel . '/Dokumentenliste.csv', 'inhalt' => qs_csv_dokumente($gewaehlt, $stamm, $heute)]);
    return $e;
}

/* ---------- Handbuch ---------- */
function qs_abschnitt_felder(array $b, array $stamm): array
{
    $row = ['kapitel' => qs_kapitel_pruefen($b['kapitel'] ?? '', $stamm), 'nr' => qs_text($b['nr'] ?? '', 20, 'Nummer'),
            'titel' => qs_text($b['titel'] ?? '', 200, 'Prozessschritt'), 'text' => qs_text($b['text'] ?? '', 20000, 'Worauf kommt es an'),
            'verweise' => qs_verweise($b['verweise'] ?? []), 'ifs' => qs_text($b['ifs'] ?? '', 60, 'IFS-Bezug'),
            'zustaendig' => qs_kuerzel($b['zustaendig'] ?? '', 'Zuständig'), 'vertreter' => qs_kuerzel($b['vertreter'] ?? '', 'Vertreter')];
    if ($row['titel'] === '') throw new InvalidArgumentException('Bitte den Prozessschritt (Titel) angeben.');
    if (strpos($row['nr'], "\n") !== false) throw new InvalidArgumentException('Nummer: bitte ohne Zeilenumbruch.');
    return $row;
}
const QS_ABSCHNITT_INHALT = ['kapitel', 'nr', 'titel', 'text', 'verweise', 'ifs', 'zustaendig', 'vertreter'];
function qs_abschnitte_sortieren(array &$liste): void
{
    usort($liste, function ($a, $b) { return qs_nat_cmp((string)$a['kapitel'], (string)$b['kapitel']) ?: (((int)($a['pos'] ?? 0)) <=> ((int)($b['pos'] ?? 0))); });
}

/* ---------- Prüfplan, Nachweise und Fälligkeit ---------- */
function qs_pruefung_felder(array $b, array $stamm, array $mitarbeiter): array
{
    $row = ['kapitel' => qs_kapitel_pruefen($b['kapitel'] ?? '', $stamm), 'titel' => qs_text($b['titel'] ?? '', 200, 'Prüfung'),
            'beschreibung' => qs_text($b['beschreibung'] ?? '', 4000, 'Frequenz / Durchführung'),
            'intervall' => qs_wahl($b['intervall'] ?? 'jaehrlich', array_keys(QS_INTERVALLE), 'Intervall'),
            'start' => qs_datum($b['start'] ?? '', 'Ab wann', false),
            'sollwert' => qs_text($b['sollwert'] ?? '', 2000, 'Sollwert'), 'massnahme' => qs_text($b['massnahme'] ?? '', 2000, 'Maßnahme bei Abweichung'),
            'womit' => qs_text($b['womit'] ?? '', 500, 'Wo? Womit?'),
            'zustaendig' => qs_kuerzel($b['zustaendig'] ?? '', 'Zuständig'), 'vertreter' => qs_kuerzel($b['vertreter'] ?? '', 'Vertreter'),
            'ausfuehrende' => qs_mitarbeiter_liste($b['ausfuehrende'] ?? [], $mitarbeiter, 'Durchführung'),
            'aktiv' => !array_key_exists('aktiv', $b) || !empty($b['aktiv'])];
    if ($row['titel'] === '') throw new InvalidArgumentException('Bitte die Prüfung benennen.');
    return $row;
}
/* Nachweise je Prüfung (ohne stornierte), neueste zuerst */
function qs_nachweise_nach_pruefung(array $nachweise): array
{
    $np = [];
    foreach ($nachweise as $n) if (empty($n['storno'])) $np[(string)$n['pruefung']][] = $n;
    foreach ($np as &$l) usort($l, function ($a, $b) { return [$b['datum'], $b['erfasst']['t'] ?? ''] <=> [$a['datum'], $a['erfasst']['t'] ?? '']; });
    return $np;
}
/* Kalender-Periode eines Datums: Tag „2026-10-30“, Woche „2026-W44“, Monat „2026-10“ */
function qs_periode(string $art, string $d): string
{
    if ($art === 'tag') return $d;
    if ($art === 'woche') return qs_dt($d)->format('o-\WW');
    return substr($d, 0, 7);
}
/* Letzter Tag der Periode (Fälligkeit) */
function qs_periode_ende(string $art, string $d): string
{
    if ($art === 'tag') return $d;
    if ($art === 'woche') return qs_plus_tage($d, 7 - (int)qs_dt($d)->format('N'));
    return substr($d, 0, 8) . sprintf('%02d', qs_monatstage((int)substr($d, 0, 4), (int)substr($d, 5, 2)));
}
/* Fällige Perioden von $ab bis $bis (einschließlich): Liste [Periode, Ende]; bei „Arbeitstage“ ohne Wochenende/Feiertage */
function qs_perioden(string $intervall, string $ab, string $bis): array
{
    $art = QS_KALENDER[$intervall];
    $out = [];
    if ($ab > $bis) return $out;
    if ($art === 'tag') {
        for ($d = $ab; $d <= $bis && count($out) < 1000; $d = qs_plus_tage($d, 1))
            if ($intervall !== 'arbeitstaeglich' || qs_arbeitstag($d)) $out[] = [$d, $d];
        return $out;
    }
    for ($d = $ab; $d <= $bis && count($out) < 1000; $d = qs_plus_tage(qs_periode_ende($art, $d), 1)) $out[] = [qs_periode($art, $d), qs_periode_ende($art, $d)];
    return $out;
}
/* Fälligkeit einer Prüfung.
   Kalender (täglich, wöchentlich, monatlich): offen = aktuelle Periode ohne Nachweis; versäumt = vergangene Perioden seit
   „ab“ (erste Fälligkeit, sonst Anlage der Prüfung) ohne Nachweis; Quote über das Fenster (30 Tage, 12 Wochen, 12 Monate).
   Rollend (vierteljährlich und länger): nächste = letzter Nachweis + Intervall, ohne Nachweis die erste Fälligkeit (sonst sofort).
   „bei Bedarf“ und inaktive Prüfungen haben keine Fälligkeit. Ampel: rot = überfällig bzw. letzte Periode versäumt,
   gelb = jetzt fällig bzw. bald fällig, grün = erledigt bzw. später fällig. */
/* Verlauf der letzten 6 Monate und des laufenden Monats für den Jahresplan: je Monat fällige Perioden (nur Kalender-
   Intervalle; die laufende, noch offene Periode zählt nicht), davon erfüllt (bzw. Anzahl Nachweise), Abweichung ja/nein */
function qs_monatsverlauf(array $eigene, string $heute, ?string $iv, string $ab, array $erledigt): array
{
    $out = [];
    $start = qs_plus_monate(substr($heute, 0, 8) . '01', -6);
    for ($m = $start; $m <= $heute; $m = qs_plus_monate($m, 1)) {
        $key = substr($m, 0, 7);
        $ende = min(qs_periode_ende('monat', $m), $heute);
        $row = ['m' => $key, 'faellig' => null, 'erfuellt' => 0, 'abweichung' => false];
        foreach ($eigene as $n) if (substr((string)$n['datum'], 0, 7) === $key) {
            if ($n['ergebnis'] === 'abweichung') $row['abweichung'] = true;
            if ($iv === null) $row['erfuellt']++;
        }
        if ($iv !== null) {
            $von = max($m, $ab);
            $per = $von <= $ende ? array_filter(qs_perioden($iv, $von, $ende), function ($x) use ($m, $ende, $heute, $erledigt) {
                return $x[1] >= $m && $x[1] <= $ende && ($x[1] < $heute || isset($erledigt[$x[0]]));
            }) : [];
            $row['faellig'] = count($per);
            $row['erfuellt'] = count(array_filter($per, function ($x) use ($erledigt) { return isset($erledigt[$x[0]]); }));
        }
        $out[] = $row;
    }
    return $out;
}
function qs_faelligkeit(array $p, array $eigene, string $heute): array
{
    $f = qs_faelligkeit_kern($p, $eigene, $heute);
    $iv = (string)($p['intervall'] ?? '');
    $kal = isset(QS_KALENDER[$iv]) && !empty($p['aktiv']);
    $erledigt = [];
    if ($kal) foreach ($eigene as $n) if ($n['datum'] <= $heute) $erledigt[qs_periode(QS_KALENDER[$iv], $n['datum'])] = true;
    $ab = (string)($p['start'] ?? '') ?: substr((string)($p['erstellt']['t'] ?? $heute), 0, 10);
    $f['monate'] = qs_monatsverlauf($eigene, $heute, $kal ? $iv : null, $ab, $erledigt);
    return $f;
}
function qs_faelligkeit_kern(array $p, array $eigene, string $heute): array
{
    $letzter = $eigene[0] ?? null;
    $out = ['letzter' => $letzter ? $letzter['datum'] : '', 'letztesErgebnis' => $letzter ? $letzter['ergebnis'] : '', 'anzahl' => count($eigene),
            'art' => '', 'naechste' => '', 'restTage' => null, 'ampel' => '', 'offen' => false, 'versaeumt' => [], 'versaeumtAnzahl' => 0, 'quote' => null];
    $iv = (string)($p['intervall'] ?? '');
    if (empty($p['aktiv']) || $iv === 'anlass' || (!isset(QS_KALENDER[$iv]) && !isset(QS_ROLLEND[$iv]))) return $out;
    if (isset(QS_KALENDER[$iv])) {
        $art = QS_KALENDER[$iv];
        $out['art'] = 'kalender';
        $erledigt = [];
        foreach ($eigene as $n) if ($n['datum'] <= $heute) $erledigt[qs_periode($art, $n['datum'])] = true;
        $ab = (string)($p['start'] ?? '');
        if ($ab === '') $ab = substr((string)($p['erstellt']['t'] ?? $heute), 0, 10);
        if ($ab > $heute) {   // beginnt erst später
            $erste = qs_perioden($iv, $ab, qs_plus_tage($ab, 40))[0] ?? null;
            $out['naechste'] = $erste ? $erste[1] : $ab; $out['restTage'] = qs_tage_bis($heute, $out['naechste']); $out['ampel'] = 'gruen';
            return $out;
        }
        $alle = qs_perioden($iv, $ab, $heute);
        $aktuell = null;
        if ($alle && $alle[count($alle) - 1][1] >= $heute) $aktuell = array_pop($alle);   // laufende Periode (heute bzw. diese Woche/dieser Monat)
        $vers = [];
        foreach ($alle as [$per, $ende]) if (!isset($erledigt[$per])) $vers[] = $per;
        $out['versaeumtAnzahl'] = count($vers);
        $out['versaeumt'] = array_slice(array_reverse($vers), 0, QS_MAX_VERSAEUMT);
        $fenster = qs_plus_tage($heute, -QS_KALENDER_FENSTER[$art]);
        $imFenster = array_values(array_filter($alle, function ($x) use ($fenster) { return $x[1] > $fenster; }));
        if ($imFenster) {
            $ok = count(array_filter($imFenster, function ($x) use ($erledigt) { return isset($erledigt[$x[0]]); }));
            $out['quote'] = ['erfuellt' => $ok, 'faellig' => count($imFenster)];
        }
        $zuletztVersaeumt = $alle && !isset($erledigt[$alle[count($alle) - 1][0]]);
        if ($aktuell !== null && !isset($erledigt[$aktuell[0]])) {
            $out['offen'] = true; $out['naechste'] = $aktuell[1]; $out['restTage'] = qs_tage_bis($heute, $aktuell[1]);
            $out['ampel'] = $zuletztVersaeumt ? 'rot' : ($out['restTage'] <= 7 ? 'gelb' : 'gruen');
        } else {
            $naechste = qs_perioden($iv, qs_plus_tage($aktuell ? $aktuell[1] : $heute, 1), qs_plus_tage($heute, 40))[0] ?? null;
            $out['naechste'] = $naechste ? $naechste[1] : ''; $out['restTage'] = $out['naechste'] !== '' ? qs_tage_bis($heute, $out['naechste']) : null;
            $out['ampel'] = ($aktuell === null && $zuletztVersaeumt) ? 'rot' : 'gruen';   // z. B. Wochenende nach versäumtem Freitag
        }
        return $out;
    }
    $out['art'] = 'rollend';
    $naechste = $letzter ? qs_plus_monate($letzter['datum'], QS_ROLLEND[$iv]) : (string)($p['start'] ?? '');
    if ($naechste === '') { $out['ampel'] = 'rot'; $out['restTage'] = 0; $out['offen'] = true; return $out; }   // noch nie geprüft, ohne erste Fälligkeit
    $rest = qs_tage_bis($heute, $naechste);
    $vorlauf = QS_VORLAUF[$iv] ?? QS_VORLAUF_STANDARD;
    $out['naechste'] = $naechste; $out['restTage'] = $rest; $out['offen'] = $rest <= $vorlauf;
    $out['ampel'] = $rest < 0 ? 'rot' : ($rest <= $vorlauf ? 'gelb' : 'gruen');
    return $out;
}
function qs_nachweis_felder(array $b, array $p, string $heute): array
{
    if (empty($p['aktiv'])) fail('Diese Prüfung ist nicht aktiv.', 409);
    $row = ['pruefung' => $p['id'], 'datum' => qs_datum($b['datum'] ?? '', 'Datum'), 'ergebnis' => qs_wahl($b['ergebnis'] ?? '', array_keys(QS_ERGEBNIS), 'Ergebnis'),
            'bemerkung' => qs_text($b['bemerkung'] ?? '', 4000, 'Bemerkung'), 'durch' => qs_text($b['durch'] ?? '', 100, 'Durchgeführt von')];
    if ($row['datum'] > $heute) throw new InvalidArgumentException('Datum: ein Nachweis kann nicht in der Zukunft liegen.');
    if ($row['ergebnis'] === 'abweichung' && $row['bemerkung'] === '') throw new InvalidArgumentException('Bei einer Abweichung bitte festhalten, was festgestellt wurde.');
    return $row;
}
function qs_pruefung_finden(array $plan, $id): array
{
    $id = is_string($id) ? $id : '';
    foreach ($plan as $x) if (($x['id'] ?? '') === $id && $id !== '') return $x;
    fail('Prüfung nicht gefunden.', 404);
    return [];
}

/* ---------- Maßnahmen (Aufbau des IFS-Maßnahmenplans) ---------- */
function qs_massnahme_felder(array $b, array $stamm): array
{
    $row = ['quelle' => qs_wahl($b['quelle'] ?? 'sonstige', array_keys(QS_QUELLEN), 'Quelle'), 'bezug' => qs_text($b['bezug'] ?? '', 200, 'Bezug'),
            'kapitel' => qs_kapitel_pruefen($b['kapitel'] ?? '', $stamm, 'Kapitel', false),
            'anforderung' => qs_kuerzel($b['anforderung'] ?? '', 'IFS-Anforderung', 20), 'anforderungText' => qs_text($b['anforderungText'] ?? '', 4000, 'Anforderung'),
            'bewertung' => qs_wahl($b['bewertung'] ?? '', QS_BEWERTUNG, 'Bewertung'),
            'feststellung' => qs_text($b['feststellung'] ?? '', 6000, 'Feststellung'),
            'korrektur' => qs_text($b['korrektur'] ?? '', 4000, 'Korrektur (Sofortmaßnahme)'),
            'korrekturVerantwortlich' => qs_kuerzel($b['korrekturVerantwortlich'] ?? '', 'Korrektur: verantwortlich', 100),
            'korrekturFrist' => qs_datum($b['korrekturFrist'] ?? '', 'Korrektur: Frist', false), 'korrekturErledigt' => qs_datum($b['korrekturErledigt'] ?? '', 'Korrektur: erledigt am', false),
            'nachweisDoku' => qs_text($b['nachweisDoku'] ?? '', 2000, 'Nachweisart / Dokumente'),
            'ursache' => qs_text($b['ursache'] ?? '', 4000, 'Ursache'), 'massnahme' => qs_text($b['massnahme'] ?? '', 6000, 'Korrekturmaßnahme'),
            'zustaendig' => qs_kuerzel($b['zustaendig'] ?? '', 'Zuständig', 100), 'frist' => qs_datum($b['frist'] ?? '', 'Frist', false),
            'erledigtAm' => qs_datum($b['erledigtAm'] ?? '', 'Umgesetzt am', false),
            'freigabeVon' => qs_kuerzel($b['freigabeVon'] ?? '', 'Freigabe durch', 100), 'freigabeDatum' => qs_datum($b['freigabeDatum'] ?? '', 'Freigabedatum', false),
            'freigabeNotiz' => qs_text($b['freigabeNotiz'] ?? '', 2000, 'Freigabe: Notiz'),
            'status' => qs_wahl($b['status'] ?? 'offen', array_keys(QS_MASSN_STATUS), 'Status')];
    if ($row['feststellung'] === '') throw new InvalidArgumentException('Bitte die Feststellung (Abweichung) beschreiben.');
    return $row;
}
/* Nächste Nummer „JJJJ-NNN“ je Jahr */
function qs_massnahme_nr(array $liste, string $jahr): string
{
    $n = 0;
    foreach ($liste as $m) if (preg_match('/^' . preg_quote($jahr, '/') . '-(\d+)$/', (string)($m['nr'] ?? ''), $x)) $n = max($n, (int)$x[1]);
    return sprintf('%s-%03d', $jahr, $n + 1);
}
function qs_massnahme_aus(array $m, string $heute): array
{
    $offen = in_array($m['status'] ?? 'offen', ['offen', 'in_arbeit'], true);
    $m['ueberfaellig'] = $offen && ($m['frist'] ?? '') !== '' && $m['frist'] < $heute;
    return $m;
}

/* ---------- Übersicht für die Oberfläche ---------- */
function qs_pruefungen_aus(array $plan, array $nachweise, string $heute): array
{
    $np = qs_nachweise_nach_pruefung($nachweise);
    return array_map(function ($p) use ($np, $heute) { return $p + ['faellig' => qs_faelligkeit($p, $np[$p['id']] ?? [], $heute)]; }, $plan);
}

/* ---------- CSV (Excel) ---------- */
function qs_csv_zelle($v): string
{
    $s = (string)$v;
    if ($s !== '' && strpbrk($s[0], "=+-@\t") !== false && !preg_match('/^-?\d+([.,]\d+)?$/', $s)) $s = "'" . $s;   // keine Formeln (CSV-Injection), Zahlen bleiben Zahlen
    return '"' . str_replace('"', '""', str_replace(["\r", "\n"], ' ', $s)) . '"';
}
function qs_csv(array $kopf, array $zeilen): string
{
    $z = [implode(';', array_map('qs_csv_zelle', $kopf))];
    foreach ($zeilen as $r) $z[] = implode(';', array_map('qs_csv_zelle', $r));
    return "\xEF\xBB\xBF" . implode("\r\n", $z) . "\r\n";
}
function qs_de(string $iso): string { return $iso === '' ? '' : substr($iso, 8, 2) . '.' . substr($iso, 5, 2) . '.' . substr($iso, 0, 4); }
function qs_csv_dokumente(array $dokumente, array $stamm, string $heute): string
{
    $kt = []; foreach ($stamm['kapitel'] as $k) $kt[$k['id']] = $k['titel'];
    $status = ['gueltig' => 'gültig', 'entwurf' => 'in Überarbeitung', 'pruefung' => 'in Prüfung', 'ohne' => 'noch nicht freigegeben', 'eingezogen' => 'eingezogen', 'register' => 'nicht gelenkt'];
    usort($dokumente, function ($a, $b) { return qs_nat_cmp((string)$a['kapitel'], (string)$b['kapitel']) ?: strnatcasecmp((string)$a['nr'], (string)$b['nr']); });
    $z = [];
    foreach ($dokumente as $d) {
        $g = qs_ver_index($d, ['freigegeben']); $v = $g !== null ? $d['versionen'][$g] : null;
        $k = is_array($v['kuerzel'] ?? null) ? $v['kuerzel'] : [];
        $u = qs_ueberpruefung($d, (int)$stamm['einstellungen']['ueberpruefungMonate'], $heute);
        $z[] = [$d['kapitel'], $kt[$d['kapitel']] ?? '', $d['nr'], QS_ARTEN[$d['art']] ?? $d['art'], $d['titel'], $v ? (string)$v['nr'] : '', $v ? qs_de((string)$v['datum']) : '',
                $status[qs_dok_status($d)] ?? '', $u ? ($u['faellig'] ? 'fällig' : qs_de($u['faelligAb'])) : '',
                $k['erstellt'] ?? ($v['erstellt']['von'] ?? ''), $k['geprueft'] ?? ($v['geprueft']['von'] ?? ''), $k['freigegeben'] ?? ($v['freigegeben']['von'] ?? ''),
                $d['zustaendig'], $d['vertreter'], $v['aenderungen'] ?? '', $v['grund'] ?? '', $d['ablage']];
    }
    return qs_csv(['Kapitel', 'Kapiteltitel', 'Dokumenten-Nr.', 'Art', 'Titel', 'Version', 'Datum', 'Status', 'Überprüfung', 'erstellt', 'geprüft', 'freigegeben', 'Zuständig', 'Vertreter', 'Änderungen', 'Änderungsgrund', 'Ablage'], $z);
}
function qs_csv_pruefplan(array $pruefungen, array $namen): string
{
    usort($pruefungen, function ($a, $b) { return qs_nat_cmp((string)$a['kapitel'], (string)$b['kapitel']) ?: strnatcasecmp((string)$a['titel'], (string)$b['titel']); });
    $z = [];
    foreach ($pruefungen as $p) {
        $f = $p['faellig'];
        $z[] = [$p['kapitel'], $p['titel'], QS_INTERVALLE[$p['intervall']] ?? $p['intervall'], $p['beschreibung'], $p['sollwert'], $p['massnahme'], $p['womit'], $p['zustaendig'], $p['vertreter'],
                implode(', ', array_map(function ($i) use ($namen) { return $namen[$i] ?? ''; }, (array)($p['ausfuehrende'] ?? []))),
                qs_de($f['letzter']), $f['letztesErgebnis'] !== '' ? (QS_ERGEBNIS[$f['letztesErgebnis']] ?? '') : '', qs_de($f['naechste']),
                $f['quote'] ? $f['quote']['erfuellt'] . ' von ' . $f['quote']['faellig'] : '', $f['art'] === 'kalender' ? (string)$f['versaeumtAnzahl'] : '', empty($p['aktiv']) ? 'inaktiv' : 'aktiv'];
    }
    return qs_csv(['Kapitel', 'Prüfung', 'Intervall', 'Frequenz / Durchführung', 'Sollwert', 'Maßnahme bei Abweichung', 'Wo? Womit?', 'Zuständig', 'Vertreter', 'Durchführung',
                   'Letzter Nachweis', 'Ergebnis', 'Nächste Fälligkeit', 'Erfüllt (Zeitraum)', 'Versäumt seit Beginn', 'Status'], $z);
}
function qs_csv_massnahmen(array $liste): string
{
    usort($liste, function ($a, $b) { return strnatcasecmp((string)$a['nr'], (string)$b['nr']); });
    $z = [];
    foreach ($liste as $m) {
        $w = is_array($m['wirksamkeit'] ?? null) ? $m['wirksamkeit'] : [];
        $z[] = [$m['nr'], QS_QUELLEN[$m['quelle']] ?? $m['quelle'], $m['bezug'], $m['kapitel'], $m['anforderung'] ?? '', $m['bewertung'] ?? '', $m['feststellung'],
                $m['korrektur'], $m['korrekturVerantwortlich'] ?? '', qs_de((string)($m['korrekturFrist'] ?? '')), qs_de((string)($m['korrekturErledigt'] ?? '')), $m['nachweisDoku'] ?? '',
                $m['ursache'], $m['massnahme'], $m['zustaendig'], qs_de((string)$m['frist']), qs_de((string)($m['erledigtAm'] ?? '')), QS_MASSN_STATUS[$m['status']] ?? $m['status'],
                $m['freigabeVon'] ?? '', qs_de((string)($m['freigabeDatum'] ?? '')), qs_de(substr((string)($w['t'] ?? ''), 0, 10)), $w['von'] ?? '', $w['notiz'] ?? ''];
    }
    return qs_csv(['Nr.', 'Quelle', 'Bezug', 'Kapitel', 'IFS-Anforderung', 'Bewertung', 'Feststellung', 'Korrektur', 'Korrektur verantwortlich', 'Korrektur bis', 'Korrektur erledigt',
                   'Nachweis', 'Ursache', 'Korrekturmaßnahme', 'Zuständig', 'Frist', 'Umgesetzt am', 'Status', 'Freigabe durch', 'Freigabedatum', 'Wirksam am', 'Wirksamkeit geprüft von', 'Wirksamkeit'], $z);
}

/* ---------- Datenpaket (bisherige Excel „QM-System“ und Maßnahmenpläne) ----------
   Format „stafl-qs“, Version 1: kapitel [{id, titel, zustaendig, vertreter}], personen [{id (Kürzel), name, funktion}],
   dokumente [{nr, kapitel, art, titel, ablage, zustaendig, vertreter, versionen [{nr, datum, aenderungen, grund, erstellt,
   geprueft, freigegeben (Kürzel)}]}], handbuch [{kapitel, nr, titel, text, verweise, ifs, zustaendig, vertreter,
   aenderungen [{datum, was, grund}]}], pruefungen [{kapitel, titel, beschreibung, intervall, start, sollwert, massnahme,
   womit, zustaendig, vertreter}], massnahmen [{nr, quelle, bezug, kapitel, anforderung, bewertung, feststellung, …, status}].
   Versionen aus der Excel: die höchste gilt (freigegeben), ältere sind „ersetzt“; Kürzel als Schnappschuss. Verknüpfungen
   mit Mitarbeitern und ausführende Mitarbeiter enthält das Paket nicht (sie hängen von der Plattform ab). */
function qs_paket_pruefen($p, array $me): array
{
    if (!is_array($p) || ($p['format'] ?? '') !== 'stafl-qs' || (int)($p['version'] ?? 0) !== 1)
        throw new InvalidArgumentException('Das ist kein Datenpaket des QM-Systems (Format „stafl-qs“, Version 1).');
    $grenzen = ['kapitel' => QS_MAX_KAPITEL, 'personen' => QS_MAX_PERSONEN, 'dokumente' => QS_MAX_DOKUMENTE, 'handbuch' => QS_MAX_ABSCHNITTE, 'pruefungen' => QS_MAX_PRUEFUNGEN, 'massnahmen' => QS_MAX_MASSNAHMEN];
    foreach ($grenzen as $teil => $max) {
        if (array_key_exists($teil, $p) && !is_array($p[$teil])) throw new InvalidArgumentException("„{$teil}“ muss eine Liste sein.");
        if (count((array)($p[$teil] ?? [])) > $max) throw new InvalidArgumentException("Zu viele Einträge in „{$teil}“ (höchstens $max).");
    }
    $fehler = [];
    $merke = function (string $teil, int $i, Throwable $e) use (&$fehler) { if (count($fehler) < 200) $fehler[] = ['teil' => $teil, 'zeile' => $i + 1, 'text' => $e->getMessage()]; };
    $stamm = ['rev' => 0, 'kapitel' => [], 'personen' => [], 'einstellungen' => ['ueberpruefungMonate' => QS_UEBERPRUEFUNG_STANDARD]];
    try { $stamm['kapitel'] = qs_kapitel_liste_pruefen($p['kapitel'] ?? [], [], []); } catch (InvalidArgumentException $e) { $merke('kapitel', 0, $e); }
    try { $stamm['personen'] = qs_personen_pruefen($p['personen'] ?? [], [], null); } catch (InvalidArgumentException $e) { $merke('personen', 0, $e); }
    $wer = qs_wer($me);
    $docs = ['dokumente' => [], 'handbuch' => [], 'pruefplan' => [], 'massnahmen' => []];
    foreach (array_values((array)($p['dokumente'] ?? [])) as $i => $x) {
        try {
            if (!is_array($x)) throw new InvalidArgumentException('ungültige Angaben');
            $d = qs_dokument_pruefen($x, null, $stamm, $docs['dokumente']);
            $vers = [];
            $vx = $x['versionen'] ?? [];
            if (!is_array($vx)) throw new InvalidArgumentException('Versionen: ungültige Angaben.');
            if ($vx && !in_array($d['art'], QS_GELENKT, true)) throw new InvalidArgumentException('Ordner und externe Dokumente haben keine Versionen.');
            if (count($vx) > QS_MAX_VERSIONEN) throw new InvalidArgumentException('Zu viele Versionen.');
            foreach (array_values($vx) as $j => $v) {
                if (!is_array($v)) throw new InvalidArgumentException('Version ' . ($j + 1) . ': ungültige Angaben.');
                $nr = $v['nr'] ?? null;
                if (is_string($nr) && ctype_digit(trim($nr))) $nr = (int)trim($nr);
                if (!is_int($nr) || $nr < 1 || $nr > 999) throw new InvalidArgumentException('Version ' . ($j + 1) . ': Versionsnummer ab 1 angeben.');
                foreach ($vers as $w) if ($w['nr'] === $nr) throw new InvalidArgumentException("Version $nr ist doppelt.");
                $vers[] = ['id' => qs_id('v'), 'nr' => $nr, 'datum' => qs_datum($v['datum'] ?? '', "Version $nr: Datum", false), 'status' => 'ersetzt',
                           'aenderungen' => qs_text($v['aenderungen'] ?? '', 2000, "Version $nr: Änderungen"), 'grund' => qs_text($v['grund'] ?? '', 1000, "Version $nr: Änderungsgrund"),
                           'erstellt' => null, 'bearbeiter' => [], 'geprueft' => null, 'freigegeben' => null,
                           'kuerzel' => ['erstellt' => qs_kuerzel($v['erstellt'] ?? '', "Version $nr: erstellt"), 'geprueft' => qs_kuerzel($v['geprueft'] ?? '', "Version $nr: geprüft"),
                                         'freigegeben' => qs_kuerzel($v['freigegeben'] ?? '', "Version $nr: freigegeben")],
                           'quelle' => 'paket', 'verlauf' => []];
            }
            usort($vers, function ($a, $b) { return $a['nr'] <=> $b['nr']; });
            if ($vers) $vers[count($vers) - 1]['status'] = 'freigegeben';
            $d['versionen'] = $vers;
            if (count($docs['dokumente']) >= QS_MAX_DOKUMENTE) throw new InvalidArgumentException('Zu viele Dokumente.');
            $docs['dokumente'][] = ['id' => qs_id('d')] + $d + ['rev' => 1, 'erstellt' => $wer, 'geaendert' => $wer, 'quelle' => 'paket', 'verlauf' => []];
        } catch (InvalidArgumentException $e) { $merke('dokumente', $i, $e); }
    }
    $pos = [];
    foreach (array_values((array)($p['handbuch'] ?? [])) as $i => $x) {
        try {
            if (!is_array($x)) throw new InvalidArgumentException('ungültige Angaben');
            $a = qs_abschnitt_felder($x, $stamm);
            $aend = [];
            foreach (array_values(is_array($x['aenderungen'] ?? null) ? $x['aenderungen'] : []) as $j => $c) {
                if (!is_array($c)) throw new InvalidArgumentException('Änderung ' . ($j + 1) . ': ungültige Angaben.');
                $aend[] = ['datum' => qs_datum($c['datum'] ?? '', 'Änderung ' . ($j + 1) . ': Datum', false), 'was' => qs_text($c['was'] ?? '', 1000, 'Änderung ' . ($j + 1)),
                           'grund' => qs_text($c['grund'] ?? '', 1000, 'Änderung ' . ($j + 1) . ': Grund'), 'von' => qs_text($c['von'] ?? '', 100, 'Änderung ' . ($j + 1) . ': von')];
            }
            $pos[$a['kapitel']] = ($pos[$a['kapitel']] ?? 0) + 1;
            $docs['handbuch'][] = ['id' => qs_id('h')] + $a + ['pos' => $pos[$a['kapitel']], 'entfallen' => null, 'aenderungen' => $aend, 'rev' => 1, 'geaendert' => $wer, 'quelle' => 'paket'];
        } catch (InvalidArgumentException $e) { $merke('handbuch', $i, $e); }
    }
    foreach (array_values((array)($p['pruefungen'] ?? [])) as $i => $x) {
        try {
            if (!is_array($x)) throw new InvalidArgumentException('ungültige Angaben');
            $docs['pruefplan'][] = ['id' => qs_id('p')] + qs_pruefung_felder(['ausfuehrende' => []] + $x, $stamm, []) + ['rev' => 1, 'erstellt' => $wer, 'geaendert' => $wer, 'quelle' => 'paket', 'verlauf' => []];
        } catch (InvalidArgumentException $e) { $merke('pruefungen', $i, $e); }
    }
    $nrs = [];
    foreach (array_values((array)($p['massnahmen'] ?? [])) as $i => $x) {
        try {
            if (!is_array($x)) throw new InvalidArgumentException('ungültige Angaben');
            $m = qs_massnahme_felder($x, $stamm);
            $nr = qs_text($x['nr'] ?? '', 20, 'Nr.');
            if ($nr === '') $nr = qs_massnahme_nr($docs['massnahmen'], substr(qs_heute(), 0, 4));
            if (isset($nrs[$nr])) throw new InvalidArgumentException("Maßnahme $nr ist doppelt.");
            $nrs[$nr] = true;
            $w = null;
            if ($m['status'] === 'wirksam') {
                $wn = qs_text($x['wirksamkeitNotiz'] ?? '', 2000, 'Wirksamkeit');
                if ($wn === '') throw new InvalidArgumentException('Wirksam: bitte die Wirksamkeitsprüfung beschreiben.');
                $w = $wer + ['notiz' => $wn];
            }
            $docs['massnahmen'][] = ['id' => qs_id('m'), 'nr' => $nr] + $m + ['wirksamkeit' => $w, 'pruefung' => '', 'nachweisId' => '', 'rev' => 1, 'erfasst' => $wer, 'geaendert' => $wer, 'quelle' => 'paket', 'verlauf' => []];
        } catch (InvalidArgumentException $e) { $merke('massnahmen', $i, $e); }
    }
    $zahlen = ['kapitel' => count($stamm['kapitel']), 'personen' => count($stamm['personen']), 'dokumente' => count($docs['dokumente']),
               'versionen' => array_sum(array_map(function ($d) { return count($d['versionen']); }, $docs['dokumente'])),
               'handbuch' => count($docs['handbuch']), 'pruefungen' => count($docs['pruefplan']), 'massnahmen' => count($docs['massnahmen'])];
    return ['stamm' => $stamm, 'docs' => $docs, 'zahlen' => $zahlen, 'fehler' => $fehler];
}
