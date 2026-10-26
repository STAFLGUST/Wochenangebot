<?php
declare(strict_types=1);
/* Modul HR · Urlaubsverwaltung – Fachlogik (Daten, Feiertage, Urlaubskonto, Anträge, Monatsplan).
   Eigene Dokumente (regeln/datenverantwortung.toml): hr-personal, hr-abwesenheiten, hr-einstellungen.
   Mitarbeiterkonten liest das Modul nur über users_load() des Plattformkerns (Verknüpfung Person ↔ Anmeldung).

   Fachliche Regeln (mit dem Inhaber abgestimmt, Oktober 2026):
   - Genehmigung durch Personen mit dem zuweisbaren Recht hr.genehmigen (Inhaber 25.10.2026, eigene Rolle), nicht mehr
     automatisch durch die Personalstelle (hr.verwalten). Niemand entscheidet über den eigenen Antrag und niemand trägt
     sich selbst Abwesenheiten ein – auch Administratoren nicht (Vier-Augen-Prinzip, hr_eigen).
     Mitarbeiter beantragen nur Urlaub.
   - Krank (K), Gleittag (G) und freie Tage (X) trägt nur die Personalstelle ein.
   - Resturlaub wird ins Folgejahr übertragen und verfällt am Verfallstag (Standard 31.03., einstellbar in Verwaltung →
     Urlaub, hr_uebertrag_bis), soweit er bis dahin nicht genommen ist.
   - Kalender: alle sehen, wer abwesend ist – nie den Grund. Gründe, Notizen und Konten nur für die Person selbst
     und die Personalstelle.
   - Freie Tage einer verkürzten Woche (z. B. 4-Tage-Woche) ergeben sich aus den Arbeitstagen der Person (Excel: „x“). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const HR_ARTEN = ['U' => 'Urlaub', 'K' => 'Krank', 'G' => 'Gleittag', 'X' => 'Freier Tag'];
const HR_STATUS = ['beantragt', 'genehmigt', 'abgelehnt', 'zurueckgezogen', 'storniert'];
const HR_AKTIV = ['beantragt', 'genehmigt'];
const HR_UEBERTRAG_BIS = '03-31';            // Standard: Resturlaub aus dem Vorjahr verfällt nach diesem Tag (einstellbar: hr_uebertrag_bis)
const HR_WOCHENTAGE = [1 => 'Mo', 2 => 'Di', 3 => 'Mi', 4 => 'Do', 5 => 'Fr', 6 => 'Sa', 7 => 'So'];
const HR_MONATE = [1 => 'Januar', 2 => 'Februar', 3 => 'März', 4 => 'April', 5 => 'Mai', 6 => 'Juni', 7 => 'Juli', 8 => 'August',
    9 => 'September', 10 => 'Oktober', 11 => 'November', 12 => 'Dezember'];
const HR_MAX_PERSONEN = 500;
const HR_MAX_EINTRAEGE = 20000;

/* ---------------- Datum ---------------- */

function hr_heute(): string { return date('Y-m-d'); }
function hr_ts(string $d): int { return (int)gmmktime(0, 0, 0, (int)substr($d, 5, 2), (int)substr($d, 8, 2), (int)substr($d, 0, 4)); }
function hr_plus(string $d, int $n): string { return gmdate('Y-m-d', hr_ts($d) + $n * 86400); }
function hr_wochentag(string $d): int { return (int)gmdate('N', hr_ts($d)); }
function hr_datum($v): ?string
{
    if (!is_string($v) || !preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $m)) return null;
    return checkdate((int)$m[2], (int)$m[3], (int)$m[1]) && (int)$m[1] >= 2000 && (int)$m[1] <= 2100 ? $v : null;
}
function hr_de(string $d): string { return substr($d, 8, 2) . '.' . substr($d, 5, 2) . '.' . substr($d, 0, 4); }
function hr_zeitraum_text(string $von, string $bis): string { return $von === $bis ? hr_de($von) : hr_de($von) . '–' . hr_de($bis); }

/* Ostersonntag (gregorianisch, Verfahren nach Meeus/Jones/Butcher) – ohne PHP-Erweiterung „calendar“ */
function hr_ostern(int $j): string
{
    $a = $j % 19; $b = intdiv($j, 100); $c = $j % 100; $d = intdiv($b, 4); $e = $b % 4; $f = intdiv($b + 8, 25);
    $g = intdiv($b - $f + 1, 3); $h = (19 * $a + $b - $d - $g + 15) % 30; $i = intdiv($c, 4); $k = $c % 4;
    $l = (32 + 2 * $e + 2 * $i - $h - $k) % 7; $m = intdiv($a + 11 * $h + 22 * $l, 451);
    $mon = intdiv($h + $l - 7 * $m + 114, 31); $tag = (($h + $l - 7 * $m + 114) % 31) + 1;
    return sprintf('%04d-%02d-%02d', $j, $mon, $tag);
}

/* Gesetzliche Feiertage in Hamburg: Datum → Name */
function hr_feiertage(int $j): array
{
    static $cache = [];
    if (isset($cache[$j])) return $cache[$j];
    $o = hr_ostern($j);
    $f = [sprintf('%04d-01-01', $j) => 'Neujahr', hr_plus($o, -2) => 'Karfreitag', hr_plus($o, 1) => 'Ostermontag',
          sprintf('%04d-05-01', $j) => 'Tag der Arbeit', hr_plus($o, 39) => 'Christi Himmelfahrt', hr_plus($o, 50) => 'Pfingstmontag',
          sprintf('%04d-10-03', $j) => 'Tag der Deutschen Einheit', sprintf('%04d-10-31', $j) => 'Reformationstag',
          sprintf('%04d-12-25', $j) => '1. Weihnachtstag', sprintf('%04d-12-26', $j) => '2. Weihnachtstag'];
    ksort($f);
    return $cache[$j] = $f;
}
function hr_feiertag(string $d): ?string { return hr_feiertage((int)substr($d, 0, 4))[$d] ?? null; }

/* Arbeitstag der Person (Wochentag laut Arbeitstagen, kein Feiertag) */
function hr_arbeitstag(array $p, string $d): bool { return in_array(hr_wochentag($d), $p['arbeitstage'], true) && hr_feiertag($d) === null; }

/* Arbeitstage einer Person im Zeitraum (optional nur innerhalb [$ab, $bis2]; ohne freie Tage aus $frei: Datum → true) */
function hr_tage(array $p, string $von, string $bis, ?string $ab = null, ?string $bis2 = null, array $frei = []): array
{
    $out = [];
    $d = $ab !== null && $ab > $von ? $ab : $von;
    $ende = $bis2 !== null && $bis2 < $bis ? $bis2 : $bis;
    for (; $d <= $ende; $d = hr_plus($d, 1)) if (hr_arbeitstag($p, $d) && !isset($frei[$d])) $out[] = $d;
    return $out;
}

/* Einzeln eingetragene freie Tage („x“) einer Person: Datum → true */
function hr_freie_tage(array $eintraege, string $person): array
{
    $out = [];
    foreach ($eintraege as $e) {
        if ($e['person'] !== $person || $e['art'] !== 'X' || !in_array($e['status'], HR_AKTIV, true)) continue;
        for ($d = $e['von']; $d <= $e['bis']; $d = hr_plus($d, 1)) $out[$d] = true;
    }
    return $out;
}

/* ---------------- Daten lesen und prüfen ---------------- */

function hr_person_norm(array $p): array
{
    $at = array_values(array_unique(array_filter(array_map('intval', (array)($p['arbeitstage'] ?? [1, 2, 3, 4, 5])), function ($w) { return $w >= 1 && $w <= 7; })));
    sort($at);
    $jahre = [];
    foreach ((array)($p['jahre'] ?? []) as $j => $v) {
        if (!preg_match('/^\d{4}$/', (string)$j) || !is_array($v)) continue;
        $jahre[(string)$j] = ['anspruch' => isset($v['anspruch']) && is_numeric($v['anspruch']) ? (float)$v['anspruch'] : null,
                              'uebertrag' => isset($v['uebertrag']) && is_numeric($v['uebertrag']) ? (float)$v['uebertrag'] : null];
    }
    ksort($jahre);
    return ['id' => (string)($p['id'] ?? ''), 'vorname' => (string)($p['vorname'] ?? ''), 'nachname' => (string)($p['nachname'] ?? ''),
            'abteilung' => (string)($p['abteilung'] ?? ''), 'pos' => (int)($p['pos'] ?? 0), 'nutzer' => isset($p['nutzer']) && $p['nutzer'] !== '' ? (string)$p['nutzer'] : null,
            'arbeitstage' => $at ?: [1, 2, 3, 4, 5], 'aktiv' => !array_key_exists('aktiv', $p) || (bool)$p['aktiv'], 'jahre' => $jahre,
            'personalnummer' => trim((string)($p['personalnummer'] ?? '')),
            'geaendert' => $p['geaendert'] ?? null] + array_diff_key($p, array_flip(['id', 'vorname', 'nachname', 'abteilung', 'pos', 'nutzer', 'arbeitstage', 'aktiv', 'jahre', 'personalnummer', 'geaendert']));
}
function hr_name(array $p): string { return trim($p['vorname'] . ' ' . $p['nachname']); }

/* ---------------- Mitarbeiter = Nutzer ----------------
   Die Mitarbeiter der Urlaubsverwaltung sind die Mitarbeiter der Plattform (Verwaltung → Mitarbeiter, Dokument „nutzer“
   des Plattformkerns, gelesen über users_load()). Auch Kollegen ohne Anmeldung (z. B. Lager) sind dort Mitarbeiter
   („ohne Anmeldung“). „hr-personal“ speichert nur die HR-Angaben je Mitarbeiter (Abteilung, Reihenfolge, Arbeitstage,
   im Urlaubsplan, Anspruch/Übertrag je Jahr), verknüpft über „nutzer“. Ohne gespeicherte Angaben gelten Standardwerte;
   die Kennung der Person ist dann die Mitarbeiter-Kennung (u…). Einträge ohne Mitarbeiter (Altbestand vor Oktober 2026,
   gelöschte Mitarbeiter) bleiben lesbar und lassen sich in der Verwaltung übernehmen (hr_personal_uebernehmen). */

/* Gespeicherte HR-Angaben (Rohdaten zum Schreiben) */
function hr_personal_roh(): array
{
    $d = store_read('hr-personal') ?? [];
    return ['rev' => (int)($d['rev'] ?? 0), 'personen' => array_map('hr_person_norm', array_values(array_filter((array)($d['personen'] ?? []), 'is_array')))];
}

/* Vor- und Nachname eines Mitarbeiters (ältere Konten haben nur „name“: letztes Wort = Nachname) */
function hr_nutzer_namen(array $u): array
{
    $vor = (string)($u['vorname'] ?? ''); $nach = (string)($u['nachname'] ?? '');
    if ($vor !== '' || $nach !== '') return [$vor, $nach];
    $t = preg_split('/\s+/u', trim((string)($u['name'] ?? ''))) ?: [];
    return count($t) > 1 ? [implode(' ', array_slice($t, 0, -1)), (string)end($t)] : [(string)($t[0] ?? ''), ''];
}

/* Alle Mitarbeiter mit ihren HR-Angaben, sortiert nach Position */
function hr_personal(): array
{
    $roh = hr_personal_roh();
    $nachNutzer = [];
    foreach ($roh['personen'] as $e) if ($e['nutzer'] !== null && !isset($nachNutzer[$e['nutzer']])) $nachNutzer[$e['nutzer']] = $e;
    $ps = []; $vergeben = [];
    foreach (users_load() as $u) {
        $uid = (string)$u['id'];
        [$vor, $nach] = hr_nutzer_namen($u);
        $zugang = nutzer_hat_zugang($u);
        $e = $nachNutzer[$uid] ?? null;
        $basis = $e ?? hr_person_norm(['id' => $uid, 'nutzer' => $uid, 'aktiv' => !$zugang || !empty($u['active'])]);
        $vergeben[$basis['id']] = true;
        $ps[] = array_merge($basis, ['vorname' => $vor, 'nachname' => $nach, 'nutzer' => $uid, 'gespeichert' => $e !== null,
                                     'zugang' => $zugang, 'kontoAktiv' => !empty($u['active']), 'username' => (string)$u['username'], 'altbestand' => false]);
    }
    foreach ($roh['personen'] as $e) {
        if (isset($vergeben[$e['id']])) continue;
        $ps[] = array_merge($e, ['nutzer' => null, 'gespeichert' => true, 'zugang' => false, 'kontoAktiv' => false, 'username' => '', 'altbestand' => true]);
    }
    usort($ps, function ($a, $b) { return [$a['pos'] ?: 9999, hr_name($a)] <=> [$b['pos'] ?: 9999, hr_name($b)]; });
    return ['rev' => $roh['rev'], 'personen' => $ps];
}

/* HR-Angaben eines Mitarbeiters speichern (anlegen oder ändern; unter der Sperre „hr-personal“ aufrufen).
   $werte: abteilung, pos, arbeitstage, aktiv, jahre – nur die übergebenen Felder ändern sich. */
function hr_angaben_setzen(array &$roh, string $uid, array $werte, array $u): array
{
    [$vor, $nach] = hr_nutzer_namen($u);
    foreach ($roh['personen'] as &$e) {
        if ($e['nutzer'] !== $uid) continue;
        $e = hr_person_norm(array_merge($e, $werte, ['vorname' => $vor, 'nachname' => $nach, 'geaendert' => now()]));
        return $e;
    }
    unset($e);
    $neu = hr_person_norm(array_merge(['id' => $uid, 'nutzer' => $uid, 'aktiv' => !nutzer_hat_zugang($u) || !empty($u['active'])], $werte,
                                      ['vorname' => $vor, 'nachname' => $nach, 'geaendert' => now()]));
    $roh['personen'][] = $neu;
    return $neu;
}

/* Abwesenheiten von einer Personenkennung auf eine andere umhängen (Übernahme eines Altbestands-Eintrags) */
function hr_abwesenheiten_umhaengen(string $von, string $nach): int
{
    if ($von === $nach) return 0;
    return with_lock('hr-abwesenheiten', function () use ($von, $nach) {
        $abw = hr_abwesenheiten(); $n = 0;
        foreach ($abw['eintraege'] as &$e) {
            if ($e['person'] === $von) { $e['person'] = $nach; $n++; }
            if (($e['vertretung'] ?? null) === $von) $e['vertretung'] = $nach;
        }
        unset($e);
        if ($n) hr_abwesenheiten_schreiben($abw);
        return $n;
    });
}

function hr_abwesenheiten(): array
{
    $d = store_read('hr-abwesenheiten') ?? [];
    return ['rev' => (int)($d['rev'] ?? 0), 'eintraege' => array_values(array_filter((array)($d['eintraege'] ?? []), function ($e) {
        return is_array($e) && isset($e['id'], $e['person'], $e['art'], $e['von'], $e['bis'], $e['status']);
    }))];
}
function hr_einstellungen(): array
{
    $d = store_read('hr-einstellungen') ?? [];
    $z = function ($l) { return array_values(array_filter((array)$l, function ($x) { return is_array($x) && hr_datum($x['von'] ?? null) && hr_datum($x['bis'] ?? null); })); };
    return ['rev' => (int)($d['rev'] ?? 0), 'sperren' => $z($d['sperren'] ?? []), 'ferien' => $z($d['ferien'] ?? []),
            'uebertragBis' => hr_uebertrag_bis_norm($d['uebertragBis'] ?? null) ?? HR_UEBERTRAG_BIS];
}

/* ---------------- Verfallstag des Resturlaubs aus dem Vorjahr ----------------
   Gespeichert als „MM-TT“ im Dokument hr-einstellungen (Feld uebertragBis, nur erweitert – GR-006); fehlt oder ungültig:
   HR_UEBERTRAG_BIS (31.03.). Gilt für alle Mitarbeiter und alle Jahre. */
function hr_uebertrag_bis_norm($v): ?string
{
    if (!is_string($v)) return null;
    if (preg_match('/^\d{4}-(\d{2})-(\d{2})$/', $v, $m)) $v = $m[1] . '-' . $m[2];   // aus einem Datumsfeld: nur Monat und Tag
    if (!preg_match('/^(\d{2})-(\d{2})$/', $v, $m)) return null;
    // Prüfung an einem Nicht-Schaltjahr: der 29.02. gibt es nicht jedes Jahr und ist deshalb nicht erlaubt
    return checkdate((int)$m[1], (int)$m[2], 2001) ? $v : null;
}
function hr_uebertrag_bis(bool $neu = false): string
{
    static $wert = null;
    if ($wert === null || $neu) $wert = hr_einstellungen()['uebertragBis'];
    return $wert;
}
/* Reihenfolge für Kalender und Export: Abteilungen nach der kleinsten Position ihrer Mitarbeiter, darin nach Position
   (wie in der Planungsdatei: jede Abteilung ein Block, auch wenn Positionen später ergänzt wurden) */
function hr_nach_abteilung(array $personen): array
{
    $erste = [];
    foreach ($personen as $p) { $k = mb_strtolower($p['abteilung']); $erste[$k] = min($erste[$k] ?? PHP_INT_MAX, $p['pos'] ?: 9999); }
    usort($personen, function ($a, $b) use ($erste) {
        $ka = mb_strtolower($a['abteilung']); $kb = mb_strtolower($b['abteilung']);
        return [$erste[$ka], $ka, $a['pos'] ?: 9999, hr_name($a)] <=> [$erste[$kb], $kb, $b['pos'] ?: 9999, hr_name($b)];
    });
    return $personen;
}
function hr_personen_index(array $personal): array { $o = []; foreach ($personal['personen'] as $p) $o[$p['id']] = $p; return $o; }

function hr_namekey(string $n): string { return mb_strtolower(trim(preg_replace('/\s+/u', ' ', $n) ?? '')); }

/* ---------------- Altbestand: Einträge ohne Mitarbeiter übernehmen ----------------
   Einträge aus der Zeit vor „Mitarbeiter = Nutzer“ (oder nach dem Löschen eines Mitarbeiters) gehören zu keinem
   Mitarbeiter. Beim ersten Aufruf von HR übernimmt ein Mitarbeiter ohne eigene HR-Angaben automatisch den einzigen
   gleichnamigen Eintrag (Anzeigename, Vor- + Nachname oder Benutzername „vorname-nachname“); in der Verwaltung lassen
   sich alle übrigen übernehmen (gleichnamiger Mitarbeiter oder neuer Mitarbeiter ohne Anmeldung). */
function hr_konto_namen(array $u): array
{
    $n = [hr_namekey((string)($u['name'] ?? '')), hr_namekey(trim(($u['vorname'] ?? '') . ' ' . ($u['nachname'] ?? ''))),
          hr_namekey(str_replace(['-', '.', '_'], ' ', (string)($u['username'] ?? '')))];
    return array_values(array_unique(array_filter($n, function ($x) { return $x !== '' && str_contains($x, ' '); })));
}
/* Kennungen der Einträge ohne gültigen Mitarbeiter (genau die, die hr_personal() als „altbestand“ zeigt): kein „nutzer“,
   der verknüpfte Mitarbeiter wurde gelöscht (z. B. ein beim Import angelegter Mitarbeiter ohne Anmeldung, später durch ein
   anderes Konto ersetzt) oder ein zweiter Eintrag für denselben Mitarbeiter (es zählt der erste). Ergebnis: [id => true] */
function hr_altbestand_ids(array $roh, ?array $users = null): array
{
    $nachNutzer = [];
    foreach ($roh['personen'] as $e) if ($e['nutzer'] !== null && !isset($nachNutzer[$e['nutzer']])) $nachNutzer[$e['nutzer']] = $e['id'];
    $vergeben = [];
    foreach ($users ?? users_load() as $u) $vergeben[$nachNutzer[(string)$u['id']] ?? (string)$u['id']] = true;
    $alt = [];
    foreach ($roh['personen'] as $e) if (!isset($vergeben[$e['id']])) $alt[$e['id']] = true;
    return $alt;
}
/* Erster gespeicherter Eintrag eines Mitarbeiters (seine HR-Angaben) – Index in $roh['personen'] oder null */
function hr_eintrag_des_nutzers(array $roh, string $uid): ?int
{
    foreach ($roh['personen'] as $k => $x) if ($x['nutzer'] === $uid) return $k;
    return null;
}

/* Vorschlag: genau ein Altbestands-Eintrag mit passendem Namen – sonst null */
function hr_vorschlag(array $roh, array $u): ?array
{
    $namen = hr_konto_namen($u);
    if (!$namen) return null;
    $alt = hr_altbestand_ids($roh);
    $treffer = array_values(array_filter($roh['personen'], function ($p) use ($namen, $alt) {
        return isset($alt[$p['id']]) && in_array(hr_namekey(hr_name($p)), $namen, true);
    }));
    return count($treffer) === 1 ? $treffer[0] : null;
}
/* Altbestands-Eintrag einem Mitarbeiter zuordnen (unter der Sperre „hr-personal“): Abwesenheiten, die schon unter der
   Mitarbeiter-Kennung stehen, wandern zum Eintrag */
function hr_altbestand_zuordnen(array &$roh, string $eintragId, array $u): array
{
    foreach ($roh['personen'] as $x) if ($x['nutzer'] === (string)$u['id'] && $x['id'] !== $eintragId) throw new InvalidArgumentException(hr_name($x) . ' hat bereits HR-Angaben.');
    [$vor, $nach] = hr_nutzer_namen($u);
    foreach ($roh['personen'] as &$e) {
        if ($e['id'] !== $eintragId) continue;
        $e['nutzer'] = (string)$u['id']; $e['vorname'] = $vor; $e['nachname'] = $nach; $e['geaendert'] = now();
        $kopie = $e;
        unset($e);
        hr_abwesenheiten_umhaengen((string)$u['id'], $eintragId);
        return $kopie;
    }
    unset($e);
    throw new InvalidArgumentException('Eintrag nicht gefunden.');
}
/* Altbestands-Eintrag von Hand einem Mitarbeiter zuordnen – auch bei abweichendem Namen und auch dann, wenn der
   Mitarbeiter schon HR-Angaben hat (z. B. „Lennert Gust“ aus der Zeiterfassung ↔ Konto „Administrator Gust“).
   Unter der Sperre „hr-personal“ aufrufen. Ohne HR-Angaben: wie hr_altbestand_zuordnen (der Eintrag wird die Person).
   Mit HR-Angaben: zusammenführen – die Angaben des Mitarbeiters gelten, leere Felder (Abteilung, Personalnummer,
   Anspruch/Übertrag je Jahr) kommen aus dem Eintrag; Abwesenheiten wandern zum Mitarbeiter, exakt doppelte
   (gleiche Art, Zeitraum, Status) werden beim Eintrag storniert (mit Grund), andere Überschneidungen brechen ab.
   Unterschiedliche Personalnummern brechen ab. Der Eintrag selbst verschwindet aus der Urlaubsliste; Abwesenheiten
   bleiben vollständig erhalten (nie gelöscht). Rückgabe: [Person, umgehängt, storniert]. */
/* Fachlicher Abbruch beim Zusammenführen (Antwort 409); eigene Klasse, damit Speicherfehler (PDOException) nicht als Meldung erscheinen */
final class HrZuordnungFehler extends RuntimeException {}
function hr_altbestand_zusammenfuehren(array &$roh, string $eintragId, array $u): array
{
    $uid = (string)$u['id'];
    $alt = hr_altbestand_ids($roh);
    $ei = null;
    foreach ($roh['personen'] as $k => $x) if ($x['id'] === $eintragId && isset($alt[$x['id']])) $ei = $k;
    $zi = hr_eintrag_des_nutzers($roh, $uid);
    if ($zi === $ei) $zi = null;   // der Eintrag selbst ist (verwaist) mit diesem Mitarbeiter verknüpft
    if ($ei === null) throw new InvalidArgumentException('Dieser Eintrag der Urlaubsliste ist schon einem Mitarbeiter zugeordnet. Bitte neu laden.');
    if ($zi === null) {
        $n = 0;
        foreach (hr_abwesenheiten()['eintraege'] as $a) if ($a['person'] === $eintragId) $n++;
        return [hr_altbestand_zuordnen($roh, $eintragId, $u), $n, 0];
    }
    $e = $roh['personen'][$ei]; $z = $roh['personen'][$zi];
    if ($e['personalnummer'] !== '' && $z['personalnummer'] !== '' && $e['personalnummer'] !== $z['personalnummer']) {
        throw new HrZuordnungFehler('Unterschiedliche Personalnummern: ' . hr_name($e) . ' hat ' . $e['personalnummer'] . ', ' . ($u['name'] ?? '') . ' hat ' . $z['personalnummer'] . '. Bitte zuerst eine der beiden Nummern korrigieren.');
    }
    [$umgehaengt, $storniert] = with_lock('hr-abwesenheiten', function () use ($e, $z) {
        $abw = hr_abwesenheiten();
        $ziel = array_values(array_filter($abw['eintraege'], function ($a) use ($z) { return $a['person'] === $z['id'] && in_array($a['status'], HR_AKTIV, true); }));
        $konflikte = []; $doppelt = [];
        foreach ($abw['eintraege'] as $i => $a) {
            if ($a['person'] !== $e['id'] || !in_array($a['status'], HR_AKTIV, true)) continue;
            foreach ($ziel as $b) {
                if (($a['art'] === 'X') !== ($b['art'] === 'X') || $a['bis'] < $b['von'] || $a['von'] > $b['bis']) continue;
                if ($a['art'] === $b['art'] && $a['von'] === $b['von'] && $a['bis'] === $b['bis'] && $a['status'] === $b['status']) { $doppelt[$i] = true; continue 2; }
                $konflikte[] = hr_zeitraum_text($a['von'], $a['bis']) . ' (Urlaubsliste) ↔ ' . hr_zeitraum_text($b['von'], $b['bis']);
            }
        }
        if ($konflikte) throw new HrZuordnungFehler('Überschneidende Abwesenheiten – bitte zuerst im HR-Bereich bereinigen: ' . implode('; ', array_slice($konflikte, 0, 5)) . (count($konflikte) > 5 ? ' …' : '') . '.');
        $n = 0;
        foreach ($abw['eintraege'] as $i => &$a) {
            if (isset($doppelt[$i])) {
                $a['status'] = 'storniert';
                $a['entscheidung'] = ['t' => now(), 'by' => 'System', 'grund' => 'doppelt beim Zusammenführen mit dem Mitarbeiter'];
            }
            if ($a['person'] === $e['id']) { $a['person'] = $z['id']; $n++; }
            if (($a['vertretung'] ?? null) === $e['id']) $a['vertretung'] = $z['id'];
        }
        unset($a);
        if ($n || $doppelt) hr_abwesenheiten_schreiben($abw);
        return [$n - count($doppelt), count($doppelt)];
    });
    // Angaben: Mitarbeiter gilt, leere Felder aus dem Eintrag
    $jahre = $z['jahre'];
    foreach ($e['jahre'] as $j => $v) {
        $alt = $jahre[$j] ?? ['anspruch' => null, 'uebertrag' => null];
        $jahre[$j] = ['anspruch' => $alt['anspruch'] ?? $v['anspruch'], 'uebertrag' => $alt['uebertrag'] ?? $v['uebertrag']];
    }
    [$vor, $nach] = hr_nutzer_namen($u);
    $roh['personen'][$zi] = hr_person_norm(array_merge($z, ['jahre' => $jahre, 'vorname' => $vor, 'nachname' => $nach, 'geaendert' => now(),
        'personalnummer' => $z['personalnummer'] !== '' ? $z['personalnummer'] : $e['personalnummer'],
        'abteilung' => $z['abteilung'] !== '' ? $z['abteilung'] : $e['abteilung']]));
    array_splice($roh['personen'], $ei, 1);
    return [$roh['personen'][$ei < $zi ? $zi - 1 : $zi], $umgehaengt, $storniert];
}

/* Beim ersten Aufruf automatisch übernehmen (nur eindeutige Namen; protokolliert) */
function hr_auto_verknuepfen(array $me): ?array
{
    return with_lock('hr-personal', function () use ($me) {
        $roh = hr_personal_roh();
        foreach ($roh['personen'] as $p) if ($p['nutzer'] === (string)$me['id']) return null;
        $v = hr_vorschlag($roh, $me);
        if (!$v) return null;
        $v = hr_altbestand_zuordnen($roh, $v['id'], $me);
        hr_personal_schreiben($roh);
        audit('hr', 'HR: Eintrag der Urlaubsliste „' . hr_name($v) . '“ automatisch dem Mitarbeiter ' . $me['name'] . ' zugeordnet (gleicher Name)');
        return $v;
    });
}
/* Alle Altbestands-Einträge übernehmen: gleichnamiger Mitarbeiter ohne HR-Angaben, sonst neuer Mitarbeiter ohne Anmeldung */
function hr_personal_uebernehmen(array $me): array
{
    return with_lock('hr-personal', function () use ($me) {
        $roh = hr_personal_roh();
        $users = users_load();
        $text = [];
        foreach ($roh['personen'] as $e) {
            $alt = hr_altbestand_ids($roh, $users);   // nach jeder Übernahme neu: zugeordnete Einträge zählen dann als vergeben
            if (!isset($alt[$e['id']])) continue;
            $mit = array_column(array_filter($roh['personen'], function ($x) use ($alt) { return $x['nutzer'] !== null && !isset($alt[$x['id']]); }), 'nutzer');
            $treffer = array_values(array_filter($users, function ($u) use ($e, $mit) {
                return !in_array((string)$u['id'], $mit, true) && in_array(hr_namekey(hr_name($e)), hr_konto_namen($u), true);
            }));
            if (count($treffer) === 1) { hr_altbestand_zuordnen($roh, $e['id'], $treffer[0]); $text[] = hr_name($e) . ' → ' . $treffer[0]['name']; continue; }
            $u = mitarbeiter_ohne_zugang_anlegen($e['vorname'], $e['nachname'] !== '' ? $e['nachname'] : '', $me);
            $users[] = $u;
            hr_altbestand_zuordnen($roh, $e['id'], $u);
            $text[] = hr_name($e) . ' als Mitarbeiter ohne Anmeldung angelegt';
        }
        if ($text) {
            hr_personal_schreiben($roh);
            audit('hr', 'HR: Urlaubsliste in die Mitarbeiter übernommen – ' . implode('; ', array_slice($text, 0, 30)) . (count($text) > 30 ? ' …' : ''));
        }
        return $text;
    });
}

/* Person des angemeldeten Mitarbeiters (im Urlaubsplan) */
function hr_ich(array $personal, array $me): ?array
{
    foreach ($personal['personen'] as $p) if ($p['nutzer'] !== null && $p['nutzer'] === (string)$me['id'] && $p['aktiv']) return $p;
    return null;
}

/* Gehört der Eintrag dem angemeldeten Mitarbeiter? Über die verknüpfte Person (auch inaktive) oder den Antragsteller.
   Grundlage des Vier-Augen-Prinzips: eigene Anträge entscheidet und eigene Abwesenheiten trägt eine andere Person ein. */
function hr_eigen(array $personal, array $me, array $e): bool
{
    if ((string)($e['erfasst']['byId'] ?? '') !== '' && ($e['quelle'] ?? '') === 'antrag' && (string)$e['erfasst']['byId'] === (string)$me['id']) return true;
    return hr_eigene_person($personal, $me, (string)($e['person'] ?? ''));
}
function hr_eigene_person(array $personal, array $me, string $person): bool
{
    foreach ($personal['personen'] as $p) if ($p['id'] === $person && $p['nutzer'] !== null && $p['nutzer'] === (string)$me['id']) return true;
    return false;
}

/* Offene Urlaubsanträge für die Entscheidung (hr_verwaltung, hr_offen): Konto, Vertretung, wer aus derselben Abteilung
   gleichzeitig weg ist (ohne Grund), „eigen“ = Antrag des angemeldeten Mitarbeiters (nicht entscheidbar). */
function hr_offene_antraege(array $personal, array $abw, array $me): array
{
    $idx = hr_personen_index($personal);
    $offen = []; $freiJe = [];
    foreach ($abw['eintraege'] as $e) {
        if ($e['status'] !== 'beantragt') continue;
        $p = $idx[$e['person']] ?? null;
        if (!$p) continue;
        $aus = hr_eintrag_aus($e, $p, $freiJe[$e['person']] ??= hr_freie_tage($abw['eintraege'], $e['person']));
        $kj = (int)substr($e['von'], 0, 4);
        $aus['konto'] = hr_konto($p, $abw['eintraege'], $kj);
        // Tage des Antrags im Jahr des Kontos (über den Jahreswechsel zählt der Rest im Folgejahr)
        $aus['tageImJahr'] = count(hr_tage($p, $e['von'], $e['bis'], "$kj-01-01", "$kj-12-31", $freiJe[$e['person']]));
        $aus['vertretungName'] = $e['vertretung'] && isset($idx[$e['vertretung']]) ? hr_name($idx[$e['vertretung']]) : null;
        $aus['eigen'] = hr_eigen($personal, $me, $e);
        $aus['kollegen'] = [];
        foreach ($abw['eintraege'] as $o) {
            if ($o['id'] === $e['id'] || $o['person'] === $e['person'] || !in_array($o['status'], HR_AKTIV, true) || $o['bis'] < $e['von'] || $o['von'] > $e['bis']) continue;
            $op = $idx[$o['person']] ?? null;
            if ($op && $op['abteilung'] === $p['abteilung']) $aus['kollegen'][] = hr_name($op) . ' (' . hr_zeitraum_text(max($o['von'], $e['von']), min($o['bis'], $e['bis'])) . ')';
        }
        $offen[] = $aus;
    }
    usort($offen, function ($a, $b) { return $a['von'] <=> $b['von']; });
    return $offen;
}

/* Zeiträume (Urlaubssperren, Ferien) prüfen: [{von, bis, text}] */
function hr_zeitraeume_pruefen($l, string $was): array
{
    if (!is_array($l) || !array_is_list($l) || count($l) > 200) throw new InvalidArgumentException("Ungültige Angaben ($was).");
    $out = [];
    foreach ($l as $i => $x) {
        $von = hr_datum($x['von'] ?? null); $bis = hr_datum($x['bis'] ?? null);
        if (!$von || !$bis) throw new InvalidArgumentException("$was, Zeile " . ($i + 1) . ': bitte Beginn und Ende angeben.');
        if ($bis < $von) throw new InvalidArgumentException("$was, Zeile " . ($i + 1) . ': das Ende liegt vor dem Beginn.');
        $out[] = ['von' => $von, 'bis' => $bis, 'text' => s($x['text'] ?? '', 80) ?? ''];
    }
    usort($out, function ($a, $b) { return $a['von'] <=> $b['von']; });
    return $out;
}
function hr_in_zeitraum(array $liste, string $d): ?array { foreach ($liste as $z) if ($z['von'] <= $d && $d <= $z['bis']) return $z; return null; }
function hr_ueberschneidung(array $liste, string $von, string $bis): ?array { foreach ($liste as $z) if ($z['von'] <= $bis && $von <= $z['bis']) return $z; return null; }

/* ---------------- Urlaubskonto ---------------- */

/* Anspruch eines Jahres: Eintrag des Jahres, sonst der letzte frühere Eintrag (gleichbleibender Anspruch) */
function hr_anspruch(array $p, int $jahr): float
{
    $wert = 0.0;
    foreach ($p['jahre'] as $j => $v) if ((int)$j <= $jahr && $v['anspruch'] !== null) $wert = $v['anspruch'];
    return $wert;
}

/* Urlaubskonto einer Person für ein Jahr. Übertrag: von Hand gesetzt (z. B. erstes Jahr im System) oder Rest des
   Vorjahres. Der Übertrag wird zuerst verbraucht; was davon bis zum Verfallstag (hr_uebertrag_bis, Standard 31.03.)
   nicht genommen (genehmigt) ist, verfällt. */
function hr_konto(array $p, array $eintraege, int $jahr, ?string $heute = null, int $tiefe = 0): array
{
    $heute = $heute ?? hr_heute();
    $u = ['genommen' => 0, 'geplant' => 0, 'beantragt' => 0, 'bis_frist' => 0];
    $frist = sprintf('%04d-%s', $jahr, hr_uebertrag_bis());
    $frei = hr_freie_tage($eintraege, $p['id']);
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id']) continue;
        // Urlaub; dazu Abwesenheiten, die laut Zeiterfassung vom Urlaub abgezogen werden („Krank ohne AU“)
        if (($e['art'] !== 'U' && empty($e['urlaubAbzug'])) || !in_array($e['status'], HR_AKTIV, true)) continue;
        foreach (hr_tage($p, $e['von'], $e['bis'], "$jahr-01-01", "$jahr-12-31", $frei) as $d) {
            if ($e['status'] === 'beantragt') { $u['beantragt']++; continue; }
            $u[$d <= $heute ? 'genommen' : 'geplant']++;
            if ($d <= $frist) $u['bis_frist']++;
        }
    }
    $anspruch = hr_anspruch($p, $jahr);
    $manuell = $p['jahre'][(string)$jahr]['uebertrag'] ?? null;
    if ($manuell !== null) $uebertrag = $manuell;
    else {
        // automatisch nur, wenn für das Vorjahr ein Anspruch bekannt ist (sonst z. B. nach einer Übernahme negative Reste)
        $vorjahrDaten = (bool)array_filter($p['jahre'], function ($v, $j) use ($jahr) { return (int)$j < $jahr && $v['anspruch'] !== null; }, ARRAY_FILTER_USE_BOTH);
        $uebertrag = $vorjahrDaten && $tiefe < 30 ? hr_konto($p, $eintraege, $jahr - 1, $heute, $tiefe + 1)['rest_jahresende'] : 0.0;
    }
    $offen = max(0.0, $uebertrag - $u['bis_frist']);          // bis zur Frist noch nicht verplanter Übertrag
    $verfallen = $heute > $frist ? $offen : 0.0;
    $rest = $anspruch + $uebertrag - $verfallen - $u['genommen'] - $u['geplant'];
    // Rest zum Jahresende (für den Übertrag ins Folgejahr): Verfall gilt dann in jedem Fall
    $restEnde = $anspruch + $uebertrag - $offen - $u['genommen'] - $u['geplant'];
    return ['jahr' => $jahr, 'anspruch' => $anspruch, 'uebertrag' => $uebertrag, 'uebertrag_manuell' => $manuell !== null,
            'frist' => $frist, 'verfaellt' => $heute <= $frist ? $offen : 0.0, 'verfallen' => $verfallen,
            'genommen' => $u['genommen'], 'geplant' => $u['geplant'], 'beantragt' => $u['beantragt'],
            'rest' => $rest, 'verfuegbar' => $rest - $u['beantragt'], 'rest_jahresende' => $restEnde];
}

/* ---------------- Urlaubsübersicht (Recht hr.uebersicht oder hr.verwalten) ----------------
   Je Mitarbeiter im Urlaubsplan nur Summen eines Jahres: Urlaubskonto (hr_konto) und genehmigte Arbeitstage je Art
   (Krank, Gleittag). Keine Zeiträume, Notizen, Gründe oder Entscheidungen – Krankheitstage sind Gesundheitsdaten und
   erscheinen nur hier als Anzahl. */
function hr_tage_je_art(array $p, array $eintraege, int $jahr): array
{
    $n = ['K' => 0, 'G' => 0];
    $frei = hr_freie_tage($eintraege, $p['id']);
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id'] || $e['status'] !== 'genehmigt' || !isset($n[$e['art']])) continue;
        $n[$e['art']] += count(hr_tage($p, $e['von'], $e['bis'], "$jahr-01-01", "$jahr-12-31", $frei));
    }
    return $n;
}
function hr_uebersicht(int $jahr): array
{
    $abw = hr_abwesenheiten()['eintraege'];
    $zeilen = [];
    foreach (hr_nach_abteilung(array_values(array_filter(hr_personal()['personen'], function ($p) { return $p['aktiv']; }))) as $p) {
        $k = hr_konto($p, $abw, $jahr);
        $t = hr_tage_je_art($p, $abw, $jahr);
        $zeilen[] = ['id' => $p['id'], 'name' => hr_name($p), 'abteilung' => $p['abteilung'],
                     'anspruch' => $k['anspruch'], 'uebertrag' => $k['uebertrag'], 'verfallen' => $k['verfallen'], 'verfaellt' => $k['verfaellt'],
                     'genommen' => $k['genommen'], 'geplant' => $k['geplant'], 'beantragt' => $k['beantragt'], 'rest' => $k['rest'],
                     'krank' => $t['K'], 'gleittage' => $t['G']];
    }
    return $zeilen;
}

/* ---------------- Einträge (Anträge und Eintragungen der Personalstelle) ---------------- */

/* Eintrag für die Ausgabe. $voll: Personalstelle oder die Person selbst (Art, Notiz, Entscheidung) */
function hr_eintrag_aus(array $e, array $p, array $frei = []): array
{
    return ['id' => $e['id'], 'person' => $e['person'], 'name' => hr_name($p), 'art' => $e['art'], 'artText' => HR_ARTEN[$e['art']] ?? $e['art'],
            'von' => $e['von'], 'bis' => $e['bis'], 'tage' => $e['art'] === 'X' ? count(hr_tage($p, $e['von'], $e['bis'])) : count(hr_tage($p, $e['von'], $e['bis'], null, null, $frei)), 'status' => $e['status'],
            'notiz' => (string)($e['notiz'] ?? ''), 'vertretung' => $e['vertretung'] ?? null, 'quelle' => (string)($e['quelle'] ?? ''),
            'urlaubAbzug' => !empty($e['urlaubAbzug']), 'erfasst' => $e['erfasst'] ?? null, 'entscheidung' => $e['entscheidung'] ?? null];
}

/* Überschneidung mit einem aktiven Eintrag derselben Person (außer $ohne).
   $art (Art des neuen Eintrags): freie Tage (X) und Abwesenheiten (U, K, G) schließen sich nicht aus – ein freier Tag
   zählt bei einer Abwesenheit einfach nicht mit (hr_tage mit $frei). Ohne $art zählt jede Überschneidung (bisheriges Verhalten). */
function hr_kollision(array $eintraege, string $person, string $von, string $bis, ?string $ohne = null, ?string $art = null): ?array
{
    foreach ($eintraege as $e) {
        if ($e['person'] !== $person || $e['id'] === $ohne || !in_array($e['status'], HR_AKTIV, true)) continue;
        if ($art !== null && ($art === 'X') !== (($e['art'] ?? '') === 'X')) continue;
        if ($e['von'] <= $bis && $von <= $e['bis']) return $e;
    }
    return null;
}

function hr_zeitraum_pruefen(array $b): array
{
    $von = hr_datum($b['von'] ?? null); $bis = hr_datum($b['bis'] ?? null);
    if (!$von || !$bis) throw new InvalidArgumentException('Bitte Beginn und Ende angeben.');
    if ($bis < $von) throw new InvalidArgumentException('Das Ende liegt vor dem Beginn.');
    if (hr_ts($bis) - hr_ts($von) > 366 * 86400) throw new InvalidArgumentException('Ein Eintrag umfasst höchstens ein Jahr.');
    return [$von, $bis];
}

function hr_neue_id(string $prefix): string { return $prefix . bin2hex(random_bytes(6)); }

/* Abwesenheiten speichern (unter Sperre aufrufen) */
function hr_abwesenheiten_schreiben(array $d): void
{
    if (count($d['eintraege']) > HR_MAX_EINTRAEGE) throw new InvalidArgumentException('Zu viele Einträge.');
    store_write('hr-abwesenheiten', ['rev' => $d['rev'] + 1, 'eintraege' => array_values($d['eintraege'])]);
}
function hr_personal_schreiben(array $d): void
{
    if (count($d['personen']) > HR_MAX_PERSONEN) throw new InvalidArgumentException('Zu viele Mitarbeiter.');
    store_write('hr-personal', ['rev' => $d['rev'] + 1, 'personen' => array_values($d['personen'])]);
}

/* ---------------- Monatsplan und Kalender ---------------- */

/* Tageskopf eines Monats: Wochentag, Wochenende, Feiertag, Ferien, Urlaubssperre */
function hr_monatstage(int $jahr, int $monat, array $einst): array
{
    $n = (int)gmdate('t', (int)gmmktime(0, 0, 0, $monat, 1, $jahr));
    $out = [];
    for ($t = 1; $t <= $n; $t++) {
        $d = sprintf('%04d-%02d-%02d', $jahr, $monat, $t);
        $w = hr_wochentag($d);
        $out[] = ['tag' => $t, 'datum' => $d, 'wt' => HR_WOCHENTAGE[$w], 'wochenende' => $w >= 6, 'feiertag' => hr_feiertag($d),
                  'ferien' => (hr_in_zeitraum($einst['ferien'], $d)['text'] ?? null) !== null, 'sperre' => hr_in_zeitraum($einst['sperren'], $d) !== null];
    }
    return $out;
}

/* Kürzel je Person und Tag eines Monats.
   $sicht: 'voll' (Personalstelle: Art, auch beantragt mit „?“), 'eigen' (eigene Zeile wie voll), 'kollege' (nur „A“ =
   abwesend, nur genehmigt, nie der Grund; freie Tage einer verkürzten Woche ebenfalls „A“). */
function hr_zeile(array $p, array $eintraege, array $tage, string $sicht): array
{
    $out = [];
    foreach ($tage as $t) {
        if ($t['wochenende'] || $t['feiertag'] !== null) continue;
        if (!in_array(hr_wochentag($t['datum']), $p['arbeitstage'], true)) $out[$t['tag']] = $sicht === 'kollege' ? 'A' : 'x';
    }
    $erster = $tage[0]['datum']; $letzter = $tage[count($tage) - 1]['datum'];
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id'] || !in_array($e['status'], HR_AKTIV, true) || $e['bis'] < $erster || $e['von'] > $letzter) continue;
        if ($sicht === 'kollege' && $e['status'] !== 'genehmigt') continue;
        foreach ($tage as $t) {
            $d = $t['datum'];
            if ($d < $e['von'] || $d > $e['bis'] || $t['wochenende'] || $t['feiertag'] !== null) continue;
            if ($e['art'] === 'X') { $out[$t['tag']] = $sicht === 'kollege' ? 'A' : 'x'; continue; }
            if (!in_array(hr_wochentag($d), $p['arbeitstage'], true)) continue;
            $out[$t['tag']] = $sicht === 'kollege' ? 'A' : $e['art'] . ($e['status'] === 'beantragt' ? '?' : '');
        }
    }
    return $out;
}

/* Monatsplan: alle aktiven Mitarbeiter, gruppiert nach Abteilung (Reihenfolge laut Position) */
function hr_monat(int $jahr, int $monat, array $me, bool $voll): array
{
    $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
    $tage = hr_monatstage($jahr, $monat, $einst);
    $ich = hr_ich($personal, $me);
    $zeilen = [];
    foreach (hr_nach_abteilung($personal['personen']) as $p) {
        if (!$p['aktiv']) continue;
        $eigen = $ich !== null && $ich['id'] === $p['id'];
        $zeilen[] = ['id' => $p['id'], 'name' => hr_name($p), 'abteilung' => $p['abteilung'], 'ich' => $eigen,
                     'tage' => (object)hr_zeile($p, $abw['eintraege'], $tage, $voll || $eigen ? 'voll' : 'kollege')];
    }
    return ['jahr' => $jahr, 'monat' => $monat, 'name' => HR_MONATE[$monat], 'tage' => $tage, 'personen' => $zeilen,
            'sperren' => $einst['sperren'], 'ferien' => $einst['ferien']];
}
