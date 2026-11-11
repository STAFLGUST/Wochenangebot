<?php
declare(strict_types=1);
/* Modul HR · Urlaubsverwaltung – Fachlogik (Daten, Feiertage, Urlaubskonto, Anträge, Korrekturmeldungen, Monatsplan).
   Eigene Dokumente (regeln/datenverantwortung.toml): hr-personal, hr-abwesenheiten, hr-einstellungen, hr-korrekturen.
   Mitarbeiterkonten liest das Modul nur über users_load() des Plattformkerns (Verknüpfung Person ↔ Anmeldung).

   Fachliche Regeln (mit dem Inhaber abgestimmt, Oktober 2026):
   - Genehmigung durch Personen mit dem zuweisbaren Recht hr.genehmigen (Inhaber 25.10.2026, eigene Rolle), nicht mehr
     automatisch durch die Personalstelle (hr.verwalten). Niemand entscheidet über den eigenen Antrag und niemand trägt
     sich selbst Abwesenheiten ein – auch Administratoren nicht (Vier-Augen-Prinzip, hr_eigen).
     Mitarbeiter beantragen Urlaub und – soweit ihr Gleittage-Konto reicht – Gleittage (Inhaber 02.11.2026).
   - Krank (K) und freie Tage (X) trägt nur die Personalstelle ein, Gleittage (G) auch sie.
   - Unentschuldigtes Fehlen (F, Inhaber 03.11.2026) trägt nur die Personalstelle ein; dabei geht (abwählbar) eine E-Mail an
     den Mitarbeiter mit seiner Urlaubsübersicht und der Bitte um eine unverzügliche Erklärung (hr_fehlen_mail in mail.php).
     Zählt nicht gegen den Urlaub; Kollegen sehen nur „abwesend“; im Export und in der Übersicht als eigene Spalte.
   - Gleittage-Konto (Inhaber 02.11.2026): die Personalstelle gewährt Mitarbeitern Gleittage als Zusatztage (Anzahl, Grund;
     gespeichert je Person in hr-personal „gleittage“, Rücknahme als Storno). Konto je Jahr: Übertrag + gewährt − genommen −
     geplant = Rest; der Rest geht unbegrenzt ins Folgejahr (kein Verfall). Das Konto beginnt mit der ersten Gewährung –
     Gleittage davor zählen nicht. Ein Gleittag-Antrag braucht genug verfügbaren Rest; die Personalstelle trägt auch darüber
     hinaus ein (dann Hinweis).
   - Resturlaub wird ins Folgejahr übertragen und verfällt am Verfallstag (Standard 31.03., einstellbar in Verwaltung →
     Urlaub, hr_uebertrag_bis), soweit er bis dahin nicht genommen ist. Je Mitarbeiter abschaltbar (Inhaber 03.11.2026,
     Verwaltung → Mitarbeiter, hr-personal „verfall“, Standard an): ohne Verfall bleibt der Übertrag ganz erhalten und geht
     mit dem Rest ins Folgejahr. Gilt wie der Verfallstag für alle Jahre (das Konto wird berechnet, nicht gespeichert).
   - Kalender: alle sehen, wer abwesend ist – nie den Grund. Gründe, Notizen und Konten nur für die Person selbst
     und die Personalstelle. Mit dem Recht hr.kalender (Inhaber 11.11.2026, sensibel, einzeln vergeben) zusätzlich
     genehmigten Urlaub und Gleittage der Kollegen der eigenen Abteilung – nie Krankheit, Notizen, offene Anträge, Tage
     oder Konten (hr_zeile 'urlaub', hr_gleiche_abteilung).
   - Freie Tage einer verkürzten Woche (z. B. 4-Tage-Woche) ergeben sich aus den Arbeitstagen der Person (Excel: „x“).
   - Urlaubsanträge über die Plattform lassen sich ein- und ausschalten (Inhaber 30.10.2026, Verwaltung → Urlaub,
     hr-einstellungen.antraege, Standard an). Ausgeschaltet lehnt der Server neue Anträge ab; Kalender, Urlaubskonto,
     Eintragen durch die Personalstelle, Entscheiden und Zurückziehen offener Anträge bleiben.
   - Urlaubsregeln (Inhaber 03.11.2026): Text der Personalstelle (hr-einstellungen „regeln“, Vorlage HR_REGELN_STANDARD),
     den jeder Mitarbeiter beim Urlaubsantrag sieht; änderbar in Verwaltung → Urlaub. Eine unverändert gespeicherte frühere
     Vorlage (HR_REGELN_FRUEHER) zeigt die aktuelle – kompakte – Vorlage.
   - Urlaubssperren aus den Regeln jedes Jahr automatisch (Inhaber 03.11.2026, hr-einstellungen „regelSperren“, Standard an):
     Ostergeschäft (die zwei Wochen vor Karfreitag) und Weihnachtsgeschäft (30.11. bis 24.12.; bis 11.11.2026 ab dem Montag der
     letzten Novemberwoche).
     Sie gelten wie eingetragene Sperren (hr_einstellungen „sperren“ enthält beide; „sperrenEigene“ nur die eingetragenen).
   - Sonderregelung Dezember (Inhaber 10.11.2026): am 24.12. und 31.12. ist der Betrieb geschlossen. Verpflichtend für alle,
     nicht je Mitarbeiter wählbar: jeder Mitarbeiter im Urlaubsplan bekommt an beiden Tagen automatisch je ½ Urlaubstag
     angerechnet – zusammen 1 Tag (Betriebsurlaub, hr_betriebsurlaub; nichts gespeichert, immer gerechnet), an seinen
     Arbeitstagen und nicht, wenn er krank, unentschuldigt oder frei eingetragen ist. Eingetragener Urlaub bzw. Gleittage
     zählen dort nicht noch einmal (hr_tag_wert = 0); ein Antrag nur für diese Tage ist nicht nötig. Ab 2026; abschaltbar in
     Verwaltung → Urlaub (hr-einstellungen „schliesstage“, Standard an). Die Weihnachtssperre endet deshalb am 23.12.
     An Schließtagen braucht niemand eine Vertretung, und gleichzeitig weg ist dort jeder (keine Konflikte).
   - Krankheit zählt nie gegen den Urlaub (Inhaber 30.10.2026) – auch nicht „Krank ohne AU“, das die Zeiterfassung vom
     Urlaub abzieht (urlaubAbzug bleibt gespeichert und ist für die Personalstelle nur ein Hinweis). Das Urlaubskonto
     zählt nur Urlaub (U).
   - Korrektur melden (Inhaber 30.10.2026): Mitarbeiter melden einen Fehler in ihren Einträgen mit Text und optional
     Zeitraum; die Personalstelle sieht die Meldungen unter „Anträge“ und erledigt sie (mit Antwort, nie die eigene).
     Gespeichert im eigenen Dokument hr-korrekturen (nur die Person selbst und hr.verwalten). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const HR_ARTEN = ['U' => 'Urlaub', 'K' => 'Krank', 'G' => 'Gleittag', 'X' => 'Freier Tag', 'F' => 'Unentschuldigt'];
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

/* ---------------- Sonderregelung Dezember: Schließtage (Inhaber 10.11.2026) ----------------
   24.12. und 31.12.: Betrieb geschlossen, Urlaub zählt je einen halben Tag (beide zusammen 1 Urlaubstag). Erst ab 2026 –
   frühere Jahre bleiben unverändert (das Konto wird berechnet; ein anderer Rest 2025 änderte sonst den Übertrag nach 2026).
   Gleiches Gewicht für Gleittage (ebenfalls ein Tag weniger Arbeit); Krank, freie Tage und Fehlen zählen ganze Tage. */
const HR_SCHLIESSTAGE = ['12-24' => 'Heiligabend – Betrieb geschlossen', '12-31' => 'Silvester – Betrieb geschlossen'];
const HR_SCHLIESSTAGE_AB = 2026;
function hr_schliesstage_an(bool $neu = false): bool
{
    static $an = null;
    if ($an === null || $neu) $an = hr_einstellungen()['schliesstage'];
    return $an;
}
/* Schließtag? Text oder null */
function hr_schliesstag(string $d): ?string
{
    if ((int)substr($d, 0, 4) < HR_SCHLIESSTAGE_AB || !isset(HR_SCHLIESSTAGE[substr($d, 5)]) || !hr_schliesstage_an()) return null;
    return HR_SCHLIESSTAGE[substr($d, 5)];
}
/* Schließtage eines Jahres: Datum → Text (für Kalender und Vorplanung) */
function hr_schliesstage(int $j): array
{
    $o = [];
    foreach (HR_SCHLIESSTAGE as $md => $txt) if (hr_schliesstag("$j-$md") !== null) $o["$j-$md"] = $txt;
    return $o;
}
/* Gewicht eines Tages in einem Eintrag: Urlaub und Gleittag zählen an einem Schließtag nicht – dort gilt der Betriebsurlaub */
function hr_tag_wert(string $d, string $art = 'U'): float { return ($art === 'U' || $art === 'G') && hr_schliesstag($d) !== null ? 0.0 : 1.0; }
const HR_BETRIEBSURLAUB_WERT = 0.5;   // je Schließtag (24.12./31.12.) – zusammen 1 Urlaubstag
/* Betriebsurlaub einer Person in einem Jahr (verpflichtend, Inhaber 10.11.2026): Schließtage, die für sie Arbeitstage sind
   (kein Feiertag), ohne freie Tage und ohne Krankheit bzw. unentschuldigtes Fehlen. Nur Mitarbeiter im Urlaubsplan. */
function hr_betriebsurlaub(array $p, array $eintraege, int $jahr): array
{
    if (empty($p['aktiv']) || !empty($p['altbestand'])) return [];
    $tage = array_values(array_filter(array_keys(hr_schliesstage($jahr)), function ($d) use ($p) { return hr_arbeitstag($p, $d); }));
    if (!$tage) return [];
    $weg = hr_freie_tage($eintraege, $p['id']);
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id'] || !in_array($e['art'], ['K', 'F'], true) || !in_array($e['status'], HR_AKTIV, true)) continue;
        foreach ($tage as $d) if ($e['von'] <= $d && $d <= $e['bis']) $weg[$d] = true;
    }
    return array_values(array_filter($tage, function ($d) use ($weg) { return !isset($weg[$d]); }));
}
/* Summe der Gewichte einer Liste von Tagen (hr_tage) */
function hr_tage_summe(array $tage, string $art = 'U'): float { $n = 0.0; foreach ($tage as $d) $n += hr_tag_wert($d, $art); return $n; }
/* Tage im Schnitt zweier Zeiträume ohne Schließtage (Kalendertage) – an Schließtagen ist ohnehin jeder weg */
function hr_schnitt_ohne_schliesstage(array $a, array $b): array
{
    $o = [];
    for ($d = max($a['von'], $b['von']), $ende = min($a['bis'], $b['bis']); $d <= $ende; $d = hr_plus($d, 1)) if (hr_schliesstag($d) === null) $o[] = $d;
    return $o;
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
            // Nummer der Abteilung in den Stammdaten der Verwaltung (Inhaber 10.11.2026); „abteilung“ bleibt als Name gespeichert (GR-006)
            'abteilungNr' => isset($p['abteilungNr']) && is_scalar($p['abteilungNr']) && (string)$p['abteilungNr'] !== '' ? (string)$p['abteilungNr'] : null,
            'arbeitstage' => $at ?: [1, 2, 3, 4, 5], 'aktiv' => !array_key_exists('aktiv', $p) || (bool)$p['aktiv'], 'jahre' => $jahre,
            'personalnummer' => trim((string)($p['personalnummer'] ?? '')), 'gleittage' => hr_gleit_norm($p['gleittage'] ?? []),
            // Resturlaub verfällt am Verfallstag – nur ein ausdrückliches false schaltet das ab (fehlt das Feld: verfällt, GR-006)
            'verfall' => ($p['verfall'] ?? true) !== false,
            // feste Vertretung (Personenkennung, Inhaber 10.11.2026) – fehlt das Feld: keine, der Mitarbeiter wählt selbst
            'vertretung' => isset($p['vertretung']) && is_string($p['vertretung']) && $p['vertretung'] !== '' ? $p['vertretung'] : null,
            'geaendert' => $p['geaendert'] ?? null] + array_diff_key($p, array_flip(['id', 'vorname', 'nachname', 'abteilung', 'abteilungNr', 'pos', 'nutzer', 'arbeitstage', 'aktiv', 'jahre', 'personalnummer', 'gleittage', 'verfall', 'vertretung', 'geaendert']));
}
function hr_name(array $p): string { return trim($p['vorname'] . ' ' . $p['nachname']); }

/* ---------------- Abteilungen ----------------
   Die Abteilungen sind Stammdaten der Verwaltung (Stammdaten → Abteilungen, gelesen über abteilungen_liste). Die HR-Angaben
   verweisen über „abteilungNr“ darauf und tragen den Namen zusätzlich in „abteilung“ (Vorversion und Rückfall lesen ihn).
   Beim Lesen gilt der Name aus den Stammdaten – ein Umbenennen wirkt so überall. Angaben ohne Nummer (vor den Stammdaten
   gespeichert) finden ihre Abteilung über den Namen bzw. einen früheren Namen. Ohne Stammdaten bleibt der freie Text. */
function hr_abteilungen(): array
{
    try { return function_exists('abteilungen_liste') ? abteilungen_liste() : []; } catch (Throwable $e) { return []; }
}
function hr_abteilung_aufloesen(array $p, array $liste): array
{
    if (!$liste) return $p;
    $a = null;
    if (($p['abteilungNr'] ?? null) !== null) foreach ($liste as $x) if ($x['nr'] === $p['abteilungNr']) { $a = $x; break; }
    if (!$a) $a = abteilung_nach_name($liste, (string)$p['abteilung']);
    return $a ? array_merge($p, ['abteilung' => $a['name'], 'abteilungNr' => $a['nr']]) : $p;
}
/* Werte zum Speichern aus einer Nummer der Stammdaten ('' = keine Abteilung); unbekannte Nummer → Fehler */
function hr_abteilung_werte(string $nr, array $liste): array
{
    if ($nr === '') return ['abteilung' => '', 'abteilungNr' => null];
    foreach ($liste as $a) if ($a['nr'] === $nr) return ['abteilung' => $a['name'], 'abteilungNr' => $a['nr']];
    throw new InvalidArgumentException('Abteilung: bitte eine Abteilung aus den Stammdaten wählen.');
}

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
        // Ohne (gültigen) Mitarbeiter = ehemaliger Mitarbeiter (Inhaber 26.10.2026): zählt nicht mehr im Urlaubsplan (Kalender,
        // Übersicht, Vertretung; Export nur in Monaten mit eigenen Einträgen), Einträge bleiben erhalten. Nur Anzeige –
        // gespeichert bleibt „aktiv“ unverändert, damit eine spätere Zuordnung den bisherigen Stand übernimmt.
        $ps[] = array_merge($e, ['nutzer' => null, 'gespeichert' => true, 'zugang' => false, 'kontoAktiv' => false, 'username' => '', 'altbestand' => true,
                                 'ehemalig' => true, 'aktiv' => false]);
    }
    $abt = hr_abteilungen();
    if ($abt) foreach ($ps as &$p) $p = hr_abteilung_aufloesen($p, $abt);
    unset($p);
    usort($ps, function ($a, $b) { return [$a['pos'] ?: 9999, hr_name($a)] <=> [$b['pos'] ?: 9999, hr_name($b)]; });
    return ['rev' => $roh['rev'], 'personen' => $ps];
}

/* HR-Angaben eines Mitarbeiters speichern (anlegen oder ändern; unter der Sperre „hr-personal“ aufrufen).
   $werte: abteilung (mit abteilungNr), pos, arbeitstage, aktiv, jahre – nur die übergebenen Felder ändern sich. */
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
            if (($e['vertretung2'] ?? null) === $von) $e['vertretung2'] = $nach;
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
    $eigene = $z($d['sperren'] ?? []);
    // Sperren aus den Urlaubsregeln: nur ein ausdrückliches false schaltet sie aus (fehlt das Feld: an – GR-006)
    $regelSperren = ($d['regelSperren'] ?? true) !== false;
    $schliess = ($d['schliesstage'] ?? true) !== false;
    $alle = $eigene;
    if ($regelSperren) { $j = (int)date('Y'); for ($y = $j - 1; $y <= $j + 3; $y++) $alle = array_merge($alle, hr_regel_sperren($y, $schliess)); }
    usort($alle, function ($a, $b) { return [$a['von'], $a['bis']] <=> [$b['von'], $b['bis']]; });
    return ['rev' => (int)($d['rev'] ?? 0), 'sperren' => $alle, 'sperrenEigene' => $eigene, 'regelSperren' => $regelSperren, 'ferien' => $z($d['ferien'] ?? []),
            'uebertragBis' => hr_uebertrag_bis_norm($d['uebertragBis'] ?? null) ?? HR_UEBERTRAG_BIS,
            // Übergangsregel: Resturlaub verfällt erstmals am Verfallstag dieses Jahres (fehlt: jedes Jahr – GR-006)
            'verfallAb' => hr_verfall_ab_norm($d['verfallAb'] ?? null),
            // Urlaubsanträge über die Plattform: nur ein ausdrückliches false schaltet sie aus (fehlt das Feld: an – GR-006)
            'antraege' => ($d['antraege'] ?? true) !== false,
            // Sonderregelung Dezember (24.12./31.12. je ½ Urlaubstag): nur ein ausdrückliches false schaltet sie aus (GR-006)
            'schliesstage' => ($d['schliesstage'] ?? true) !== false,
            // Resturlaub überziehen (Inhaber 10.11.2026): so viele Tage darf ein Antrag über die verfügbaren Tage gehen – mit
            // Bestätigung „Trotzdem absenden“; darüber lehnt der Server immer ab. Fehlt das Feld: Standard (GR-006)
            'ueberziehenMax' => hr_ueberziehen_norm($d['ueberziehenMax'] ?? null) ?? HR_UEBERZIEHEN_STANDARD,
            // Urlaub am Stück (Inhaber 11.11.2026): höchstens so viele Arbeitstage in einem Block, 0 = keine Prüfung (fehlt: Standard)
            'amStueckMax' => hr_am_stueck_norm($d['amStueckMax'] ?? null) ?? HR_AM_STUECK_STANDARD,
            // Urlaubsregeln: gespeicherter Text (auch leer = keine Regeln anzeigen), ohne Feld die Vorlage
            'regeln' => hr_regeln_text($d['regeln'] ?? null)];
}

/* Resturlaub überziehen: ganze oder halbe Tage 0–30 (0 = nie über die verfügbaren Tage), sonst null */
const HR_UEBERZIEHEN_STANDARD = 4.0;
function hr_ueberziehen_norm($v): ?float
{
    if (!is_int($v) && !is_float($v)) return null;
    $v = (float)$v;
    return $v >= 0 && $v <= 30 && fmod($v * 2, 1.0) == 0.0 ? $v : null;
}

/* ---------------- Urlaub am Stück (Inhaber 11.11.2026: „15 Tage ist das Maximum“) ----------------
   Ein Mitarbeiter kann höchstens amStueckMax Arbeitstage Urlaub am Stück beantragen (hr-einstellungen, Standard 15, 0 = keine
   Prüfung). Ein Block sind Urlaubstage, die nur durch Tage ohne Arbeit (Wochenende, Feiertag, eigener freier Tag, Schließtag
   24.12./31.12.) oder durch Gleittage getrennt sind: Freitag plus ab dem Montag danach 15 Tage sind 16 am Stück. Gezählt werden
   Arbeitstage mit Urlaub (Schließtage und Gleittage verbinden nur). Krankheit und andere Arbeitstage trennen. Geprüft wird beim
   Antrag und in der Vorplanung (hr_antrag_zeitraum, mit den übrigen Zeilen); die Personalstelle trägt weiter frei ein, die
   Jahresplanung zeigt längere Blöcke als Konflikt „dauer“. */
const HR_AM_STUECK_STANDARD = 15;
const HR_AM_STUECK_GRENZE = 60;   // höchster einstellbarer Wert
function hr_am_stueck_norm($v): ?int { return is_int($v) && $v >= 0 && $v <= HR_AM_STUECK_GRENZE ? $v : null; }
/* Längster Urlaubsblock, der einen der Zeiträume $neu ([{von, bis}], noch nicht gespeichert oder schon eingetragen) berührt –
   mit den beantragten und genehmigten Einträgen der Person. Rückgabe ['tage' => Arbeitstage, 'von' => erster, 'bis' => letzter
   Urlaubstag] oder null (kein Urlaubstag). */
function hr_am_stueck_block(array $p, array $eintraege, array $neu): ?array
{
    if (!$neu) return null;
    $min = min(array_column($neu, 'von')); $max = max(array_column($neu, 'bis'));
    $u = []; $g = []; $liste = $neu;
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id'] || !in_array($e['status'], HR_AKTIV, true) || $e['bis'] < hr_plus($min, -400) || $e['von'] > hr_plus($max, 400)) continue;
        if ($e['art'] === 'U') $liste[] = $e;
        elseif ($e['art'] === 'G') for ($d = $e['von']; $d <= $e['bis']; $d = hr_plus($d, 1)) $g[$d] = true;
    }
    foreach ($liste as $e) for ($d = $e['von']; $d <= $e['bis']; $d = hr_plus($d, 1)) $u[$d] = true;
    $frei = hr_freie_tage($eintraege, $p['id']);
    // 1 = Urlaubstag (zählt), 0 = verbindet (kein Arbeitstag, freier Tag, Schließtag, Gleittag), -1 = trennt
    $art = function (string $d) use ($p, $u, $g, $frei): int {
        if (!hr_arbeitstag($p, $d) || isset($frei[$d]) || hr_schliesstag($d) !== null) return 0;
        return isset($u[$d]) ? 1 : (isset($g[$d]) ? 0 : -1);
    };
    $best = null;
    foreach ($neu as $z) {
        $a = $z['von']; $b = $z['bis'];
        for ($d = hr_plus($a, -1), $i = 0; $i < 370 && ($t = $art($d)) >= 0; $d = hr_plus($d, -1), $i++) if ($t > 0) $a = $d;
        for ($d = hr_plus($b, 1), $i = 0; $i < 370 && ($t = $art($d)) >= 0; $d = hr_plus($d, 1), $i++) if ($t > 0) $b = $d;
        $n = 0; $erst = null; $letzt = null;
        for ($d = $a; $d <= $b; $d = hr_plus($d, 1)) if ($art($d) > 0) { $n++; $erst = $erst ?? $d; $letzt = $d; }
        if ($n > 0 && (!$best || $n > $best['tage'])) $best = ['tage' => $n, 'von' => $erst, 'bis' => $letzt];
    }
    return $best;
}
/* Text, wenn ein Block zu lang wäre; $allein: der Zeitraum ist schon allein zu lang */
function hr_am_stueck_text(array $blk, int $max, bool $allein): string
{
    return "Am Stück sind höchstens $max Arbeitstage Urlaub möglich – " . ($allein
        ? 'dieser Zeitraum hat ' . $blk['tage'] . ' Arbeitstage.'
        : 'zusammen mit Ihrem Urlaub direkt davor oder danach wären es ' . $blk['tage'] . ' Arbeitstage am Stück (' . hr_zeitraum_text($blk['von'], $blk['bis'])
          . '). Wochenenden, Feiertage und Gleittage dazwischen unterbrechen den Urlaub nicht.');
}

/* Überzug eines Urlaubsantrags (Inhaber 10.11.2026): um wie viele Tage gehen die verfügbaren Tage (Rest − offene Anträge)
   mit den neuen Einträgen ins Minus? Je berührtem Jahr gerechnet, der größte Wert zählt. $neu: [{art, von, bis}] (noch nicht
   gespeichert). Rückgabe {tage, jahr, verfuegbar (vorher, im Jahr des größten Überzugs)} – tage 0: reicht. */
function hr_ueberzug(array $p, array $eintraege, array $neu): array
{
    $jahre = [];
    foreach ($neu as $e) for ($j = (int)substr($e['von'], 0, 4); $j <= (int)substr($e['bis'], 0, 4); $j++) $jahre[$j] = true;
    $mit = $eintraege;
    foreach ($neu as $i => $e) $mit[] = ['id' => '_neu' . $i, 'person' => $p['id'], 'art' => $e['art'] ?? 'U', 'von' => $e['von'], 'bis' => $e['bis'], 'status' => 'beantragt'];
    $r = ['tage' => 0.0, 'jahr' => null, 'verfuegbar' => null];
    foreach (array_keys($jahre) as $j) {
        $nach = (float)hr_konto($p, $mit, $j)['verfuegbar'];
        if (-$nach > $r['tage']) $r = ['tage' => -$nach, 'jahr' => $j, 'verfuegbar' => (float)hr_konto($p, $eintraege, $j)['verfuegbar']];
    }
    return $r;
}
/* Text zum Überzug für Antragsteller: über der Grenze (abgelehnt) oder darunter (Rückfrage „Trotzdem absenden“) */
function hr_ueberzug_text(array $u, float $max): string
{
    $v = 'Dafür reichen Ihre Urlaubstage ' . $u['jahr'] . ' nicht: verfügbar ' . hr_tage_text(max(0.0, (float)$u['verfuegbar'])) . ', damit ' . hr_tage_text($u['tage']) . ' im Minus.';
    return $u['tage'] > $max
        ? $v . ($max > 0 ? ' Mehr als ' . hr_tage_text($max) . ' über die verfügbaren Tage ist nicht möglich' : ' Über die verfügbaren Tage hinaus ist kein Antrag möglich') . ' – bitte an die Personalstelle wenden.'
        : $v . ' Möglich sind bis zu ' . hr_tage_text($max) . ' – die Personalstelle entscheidet.';
}

/* ---------------- Urlaubsregeln und Sperren aus den Regeln (Inhaber 03.11.2026) ---------------- */
const HR_REGELN_MAX = 6000;   // Zeichen
/* Vorlage (Inhaber 03.11.2026: kompakt und einfach; Wortlaut 11.11.2026 wie „Urlaubsregeln kompakt“ der Mitarbeiter-Mail, dazu
   „Urlaubsdauer“ – höchstens 15 Arbeitstage am Stück, Inhaber 11.11.2026) – eine
   Zeile „1. Überschrift“, darunter der Text, Absätze durch Leerzeilen */
const HR_REGELN_STANDARD = "1. Urlaubsanspruch\n"
    . "Wie viele Urlaubstage Sie haben, steht in Ihrem Arbeitsvertrag.\n\n"
    . "2. Planung\n"
    . "Urlaub ist grundsätzlich im laufenden Kalenderjahr zu nehmen.\n\n"
    . "3. Vorplanung\n"
    . "Planen Sie Ihren Jahresurlaub bis zum 31.01. vor (Schalter „Vorplanung“ bei „Urlaub beantragen“). Höchstens 5 Urlaubstage dürfen unverplant bleiben. Liegt keine Planung vor, plant die Personalstelle Ihren Urlaub.\n\n"
    . "4. Einzelne Urlaubstage\n"
    . "In der Vorplanung höchstens 4 einzelne Urlaubstage. Den übrigen Urlaub planen Sie bitte zusammenhängend.\n\n"
    . "5. Urlaubsdauer\n"
    . "Am Stück höchstens 15 Arbeitstage Urlaub. Wochenenden, Feiertage und Gleittage dazwischen zählen durch: Freitag plus ab Montag 15 Tage wären 16.\n\n"
    . "6. Urlaubssperre\n"
    . "Grundsätzlich kein Urlaub im Ostergeschäft (2 Wochen vor Ostern) und im Weihnachtsgeschäft (30.11.–24.12.).\n\n"
    . "7. Resturlaub\n"
    . "Resturlaub ist grundsätzlich bis zum 31.03. des Folgejahres zu nehmen, sonst verfällt er.\n\n"
    . "8. Vertretung\n"
    . "Stimmen Sie Ihren Urlaub mit Ihrer Urlaubsvertretung ab. Sie muss während Ihres ganzen Urlaubs anwesend sein – Überschneidungen sind nicht erlaubt.\n\n"
    . "9. Sonderregelung Dezember\n"
    . "Am 24.12. und 31.12. bleibt der Betrieb geschlossen. Für beide Tage zusammen wird 1 Urlaubstag angerechnet – automatisch, ein Antrag ist nicht nötig.";
/* Frühere Vorlagen: wurde eine davon unverändert gespeichert (Verwaltung → Urlaub speichert den Text immer mit), gilt die
   aktuelle Vorlage – eigene Texte der Personalstelle bleiben unberührt; gespeichert wird dabei nichts (GR-006). */
const HR_REGELN_FRUEHER = [
    // 11.11.2026 (PR #332): acht Punkte wie die Mitarbeiter-Mail, noch ohne Urlaubsdauer
    "1. Urlaubsanspruch\n"
    . "Wie viele Urlaubstage Sie haben, steht in Ihrem Arbeitsvertrag.\n\n"
    . "2. Planung\n"
    . "Urlaub ist grundsätzlich im laufenden Kalenderjahr zu nehmen.\n\n"
    . "3. Vorplanung\n"
    . "Planen Sie Ihren Jahresurlaub bis zum 31.01. vor (Schalter „Vorplanung“ bei „Urlaub beantragen“). Höchstens 5 Urlaubstage dürfen unverplant bleiben. Liegt keine Planung vor, plant die Personalstelle Ihren Urlaub.\n\n"
    . "4. Einzelne Urlaubstage\n"
    . "In der Vorplanung höchstens 4 einzelne Urlaubstage. Den übrigen Urlaub planen Sie bitte zusammenhängend.\n\n"
    . "5. Urlaubssperre\n"
    . "Grundsätzlich kein Urlaub im Ostergeschäft (2 Wochen vor Ostern) und im Weihnachtsgeschäft (30.11.–24.12.).\n\n"
    . "6. Resturlaub\n"
    . "Resturlaub ist grundsätzlich bis zum 31.03. des Folgejahres zu nehmen, sonst verfällt er.\n\n"
    . "7. Vertretung\n"
    . "Stimmen Sie Ihren Urlaub mit Ihrer Urlaubsvertretung ab. Sie muss während Ihres ganzen Urlaubs anwesend sein – Überschneidungen sind nicht erlaubt.\n\n"
    . "8. Sonderregelung Dezember\n"
    . "Am 24.12. und 31.12. bleibt der Betrieb geschlossen. Für beide Tage zusammen wird 1 Urlaubstag angerechnet – automatisch, ein Antrag ist nicht nötig.",
    // 10.11.–11.11.2026 (PR #325): Vorplanung bis 31.12. mit 90 %, Urlaubsdauer 15 Tage, Weihnachtsgeschäft ab der letzten Novemberwoche
    "1. Urlaubsanspruch\n"
    . "Wie viele Urlaubstage Sie haben, steht in Ihrem Arbeitsvertrag.\n\n"
    . "2. Vorplanung\n"
    . "Bitte planen Sie bis zum 31.12. mindestens 90 % Ihres Urlaubs für das nächste Jahr vor (Schalter „Vorplanung“ bei „Urlaub beantragen“) – so können alle fair planen.\n\n"
    . "3. Einzelne Urlaubstage\n"
    . "In der Vorplanung höchstens 4 einzelne Urlaubstage. Den übrigen Urlaub planen Sie bitte möglichst zusammenhängend.\n\n"
    . "4. Urlaubsdauer\n"
    . "Am Stück sind bis zu 15 Arbeitstage Urlaub möglich (gesetzlich zugesichert: 10).\n\n"
    . "5. Urlaubssperre\n"
    . "Kein Urlaub im Ostergeschäft (zwei Wochen vor den Osterfeiertagen) und im Weihnachtsgeschäft (letzte Novemberwoche bis 23.12.).\n\n"
    . "6. Sonderregelung Dezember\n"
    . "Am 24.12. und 31.12. bleibt der Betrieb geschlossen. Dafür wird jedem automatisch 1 Urlaubstag angerechnet (je ½ Tag) – ein Antrag ist nicht nötig.\n\n"
    . "7. Resturlaub\n"
    . "Urlaub muss im laufenden Jahr genommen werden. Ging das wegen Urlaubssperre, viel Arbeit oder Krankheit nicht, haben Sie bis zum 31.03. des Folgejahres Zeit – danach verfällt der Rest in der Regel (§ 7 Abs. 3 BUrlG).\n\n"
    . "8. Vertretung\n"
    . "Ihr Urlaub darf sich nicht mit dem Ihrer Vertretung überschneiden. Wer Sie vertritt, steht im Vertretungsplan.",
    // 10.11.2026 (PR #324): acht Punkte, Sonderregelung Dezember noch zum Selbst-Einplanen
    "1. Urlaubsanspruch\n"
    . "Wie viele Urlaubstage Sie haben, steht in Ihrem Arbeitsvertrag.\n\n"
    . "2. Vorplanung\n"
    . "Bitte planen Sie bis zum 31.12. mindestens 90 % Ihres Urlaubs für das nächste Jahr vor (Schalter „Vorplanung“ bei „Urlaub beantragen“) – so können alle fair planen.\n\n"
    . "3. Einzelne Urlaubstage\n"
    . "In der Vorplanung höchstens 4 einzelne Urlaubstage. Den übrigen Urlaub planen Sie bitte möglichst zusammenhängend.\n\n"
    . "4. Urlaubsdauer\n"
    . "Am Stück sind bis zu 15 Arbeitstage Urlaub möglich (gesetzlich zugesichert: 10).\n\n"
    . "5. Urlaubssperre\n"
    . "Kein Urlaub im Ostergeschäft (zwei Wochen vor den Osterfeiertagen) und im Weihnachtsgeschäft (letzte Novemberwoche bis 23.12.).\n\n"
    . "6. Sonderregelung Dezember\n"
    . "Am 24.12. und 31.12. bleibt der Betrieb geschlossen. Für beide Tage zusammen ist nur 1 Urlaubstag einzusetzen.\n\n"
    . "7. Resturlaub\n"
    . "Urlaub muss im laufenden Jahr genommen werden. Ging das wegen Urlaubssperre, viel Arbeit oder Krankheit nicht, haben Sie bis zum 31.03. des Folgejahres Zeit – danach verfällt der Rest in der Regel (§ 7 Abs. 3 BUrlG).\n\n"
    . "8. Vertretung\n"
    . "Ihr Urlaub darf sich nicht mit dem Ihrer Vertretung überschneiden. Wer Sie vertritt, steht im Vertretungsplan.",
    // 03.11.–10.11.2026: kompakte Vorlage ohne Vorplanung, Einzeltage und Sonderregelung Dezember
    "1. Urlaubsanspruch\n"
    . "Wie viele Urlaubstage Sie haben, steht in Ihrem Arbeitsvertrag.\n\n"
    . "2. Planung\n"
    . "Bitte reichen Sie Ihre Urlaubsplanung für das ganze Jahr bis zum 31.03. ein – so können alle fair planen.\n\n"
    . "3. Urlaubsdauer\n"
    . "Am Stück sind bis zu 15 Arbeitstage Urlaub möglich (gesetzlich zugesichert: 10).\n\n"
    . "4. Urlaubssperre\n"
    . "Kein Urlaub im Ostergeschäft (zwei Wochen vor den Osterfeiertagen) und im Weihnachtsgeschäft (letzte Novemberwoche bis 24.12.).\n\n"
    . "5. Resturlaub\n"
    . "Urlaub muss im laufenden Jahr genommen werden. Ging das wegen Urlaubssperre, viel Arbeit oder Krankheit nicht, haben Sie bis zum 31.03. des Folgejahres Zeit – danach verfällt der Rest in der Regel (§ 7 Abs. 3 BUrlG).\n\n"
    . "6. Vertretung\n"
    . "Ihr Urlaub darf sich nicht mit dem Ihrer Vertretung überschneiden. Wer Sie vertritt, steht im Vertretungsplan.",
    // bis 03.11.2026: ausführlicher Wortlaut
    "1. Urlaubsanspruch\n"
        . "Der Urlaubsanspruch jedes Arbeitnehmers ist individuell über den Arbeitsvertrag geregelt.\n\n"
        . "2. Planung\n"
        . "Gemäß § 7 Abs. 3 Satz 1 BUrlG muss der Urlaub im Kalenderjahr vollständig genommen werden. Um eine Planung sinnvoll und für alle Beteiligten gerecht zu gestalten, sollte die jeweilige individuelle Jahresurlaubsplanung bis zum 31.03. eines jeden Kalenderjahres vom Arbeitnehmer eingereicht werden.\n\n"
        . "3. Urlaubsdauer\n"
        . "Das BUrlG gesteht dem Arbeitnehmer das Anrecht auf Urlaub an 10 aufeinander folgenden Arbeitstagen zu. Die innerbetriebliche Regelung gewährt den Arbeitnehmern aktuell einen Urlaub an 15 aufeinander folgenden Arbeitstagen.\n\n"
        . "4. Urlaubssperre\n"
        . "Aus betrieblichen Gründen wird zu folgenden Zeiten kein Urlaub gewährt:\n"
        . "Ostergeschäft: Zwei Wochen vor den Osterfeiertagen eines jeden Kalenderjahres.\n"
        . "Weihnachtsgeschäft: Ab der letzten Novemberwoche bis einschließlich dem 24.12. eines jeden Kalenderjahres.\n\n"
        . "5. Resturlaub\n"
        . "Gemäß § 7 Abs. 3 Satz 1 BUrlG muss der Urlaub im Kalenderjahr vollständig genommen werden. Konnte der Arbeitnehmer seinen Resturlaub wegen Urlaubssperre, Übermaß an Arbeit oder wegen Krankheit nicht nehmen, so muss der Resturlaub gemäß § 7 Abs. 3 Satz 3 BUrlG in den ersten drei Monaten des folgenden Kalenderjahres, d. h. bis zum 31. März, genommen werden. Andernfalls verfällt er grundsätzlich.\n\n"
        . "6. Urlaubsvertretung\n"
        . "Der Urlaub muss so geplant werden, dass es keine Überschneidung mit dem jeweiligen Vertreter (Vollvertretung) gibt. Die Urlaubsvertretung ist im Vertretungsplan festgelegt.",
];

/* Gespeicherter Text der Urlaubsregeln für die Anzeige: ohne Feld oder als unveränderte frühere Vorlage die aktuelle Vorlage */
function hr_regeln_text($t): string
{
    if (!is_string($t)) return HR_REGELN_STANDARD;
    return in_array(trim($t), HR_REGELN_FRUEHER, true) ? HR_REGELN_STANDARD : $t;
}

/* Text der Urlaubsregeln prüfen: Zeichenkette, höchstens HR_REGELN_MAX Zeichen, ohne Steuerzeichen (Zeilenumbrüche bleiben) */
function hr_regeln_pruefen($t): string
{
    if (!is_string($t)) throw new InvalidArgumentException('Urlaubsregeln: bitte Text angeben.');
    $t = trim(preg_replace('/[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x{feff}\x{200b}]/u', '', str_replace("\r", '', $t)) ?? '');
    if (mb_strlen($t) > HR_REGELN_MAX) throw new InvalidArgumentException('Urlaubsregeln: höchstens ' . HR_REGELN_MAX . ' Zeichen.');
    return $t;
}

/* Sperren aus den Urlaubsregeln für ein Jahr: Ostergeschäft = die zwei Wochen vor Karfreitag (Karfreitag − 14 bis
   Gründonnerstag), Weihnachtsgeschäft = 30.11. bis 23.12. (Inhaber 11.11.2026, „30.11.–24.12.“; vorher ab dem Montag der
   letzten Novemberwoche) – am 24.12. ist der Betrieb geschlossen (Sonderregelung Dezember ab 2026, $schliess); ohne sie bis
   einschließlich 24.12. */
function hr_regel_sperren(int $j, bool $schliess = true): array
{
    $karfreitag = hr_plus(hr_ostern($j), -2);
    $ende = $schliess && $j >= HR_SCHLIESSTAGE_AB ? '12-23' : '12-24';
    return [['von' => hr_plus($karfreitag, -14), 'bis' => hr_plus($karfreitag, -1), 'text' => 'Ostergeschäft', 'auto' => true],
            ['von' => sprintf('%04d-11-30', $j), 'bis' => sprintf('%04d-%s', $j, $ende), 'text' => 'Weihnachtsgeschäft', 'auto' => true]];
}

/* ---------------- Verfallstag des Resturlaubs aus dem Vorjahr ----------------
   Gespeichert als „MM-TT“ im Dokument hr-einstellungen (Feld uebertragBis, nur erweitert – GR-006); fehlt oder ungültig:
   HR_UEBERTRAG_BIS (31.03.). Gilt für alle Jahre und alle Mitarbeiter mit Verfall (hr-personal „verfall“, Standard an). */
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
/* Übergangsregel (Inhaber 03.11.2026: „im ersten Jahr streichen wir noch keine Urlaubstage, erst nächstes Jahr“):
   Resturlaub verfällt erstmals am Verfallstag des Jahres „verfallAb“ (hr-einstellungen, Jahreszahl, nur erweitert – GR-006).
   In Jahren davor verfällt bei niemandem etwas; der ganze Rest geht ins Folgejahr. Fehlt das Feld: Verfall in jedem Jahr. */
const HR_VERFALL_AB_MIN = 2000, HR_VERFALL_AB_MAX = 2100;
function hr_verfall_ab_norm($v): ?int
{
    return is_int($v) && $v >= HR_VERFALL_AB_MIN && $v <= HR_VERFALL_AB_MAX ? $v : null;
}
/* Erstes Jahr mit Verfall (0 = jedes Jahr) */
function hr_verfall_ab(bool $neu = false): int
{
    static $wert = null;
    if ($wert === null || $neu) $wert = hr_einstellungen()['verfallAb'] ?? 0;
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
   Mitarbeiter (ehemalige Mitarbeiter). Zugeordnet werden sie nur durch die Personalstelle (Verwaltung → Mitarbeiter:
   „Einzeln zuordnen“ mit Vorschlag, „Gleichnamige zuordnen“) – nie automatisch beim Aufruf von HR (Sicherheitsdurchsicht
   26.10.2026: sonst sähe ein neuer gleichnamiger Mitarbeiter Abwesenheiten seines Vorgängers) und nie durch die eigene Person. */
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
            if (($a['vertretung2'] ?? null) === $e['id']) $a['vertretung2'] = $z['id'];
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

/* Altbestands-Einträge dem gleichnamigen Mitarbeiter ohne HR-Angaben zuordnen (eindeutiger Name). Einträge ohne passenden
   Mitarbeiter bleiben ehemalige Mitarbeiter – es entstehen keine neuen Mitarbeiter mehr (Inhaber 26.10.2026). */
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
            // nie der eigenen Person zuordnen (Vier-Augen-Prinzip) – das macht eine andere Person der Personalstelle
            if (count($treffer) === 1 && (string)$treffer[0]['id'] !== (string)$me['id']) { hr_altbestand_zuordnen($roh, $e['id'], $treffer[0]); $text[] = hr_name($e) . ' → ' . $treffer[0]['name']; }
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
    if ((string)($e['erfasst']['byId'] ?? '') !== '' && in_array($e['quelle'] ?? '', ['antrag', 'vorplanung'], true) && (string)$e['erfasst']['byId'] === (string)$me['id']) return true;
    return hr_eigene_person($personal, $me, (string)($e['person'] ?? ''));
}
/* Eigene HR-Angaben (mitarbeiter_hr_save für sich selbst): Felder mit Einfluss auf das Urlaubskonto dürfen sich nicht
   ändern – unveränderte Werte werden entfernt, geänderte abgelehnt (403). $werte/$jahr/$jv werden angepasst. */
function hr_eigene_angaben_pruefen(array &$werte, ?int &$jahr, ?array &$jv, string $uid, array $u): void
{
    $ist = null;
    foreach (hr_personal()['personen'] as $x) if ($x['nutzer'] === $uid) { $ist = $x; break; }
    $ist = $ist ?? hr_person_norm(['id' => $uid, 'nutzer' => $uid, 'aktiv' => !nutzer_hat_zugang($u) || !empty($u['active'])]);
    $nein = 'Ihre eigenen Urlaubsangaben (Anspruch, Übertrag, Verfall, Arbeitstage, Urlaubsplan, Personalnummer, Vertretung) ändert eine andere Person der Personalstelle.';
    foreach (['aktiv', 'arbeitstage', 'personalnummer', 'verfall', 'vertretung'] as $f) {
        if (!array_key_exists($f, $werte)) continue;
        if ($werte[$f] !== $ist[$f]) fail($nein, 403);
        unset($werte[$f]);
    }
    if ($jahr !== null) {
        $alt = $ist['jahre'][(string)$jahr] ?? ['anspruch' => null, 'uebertrag' => null];
        // Anspruch: gespeicherter Wert des Jahres oder (Dialog-Vorbelegung) der geltende aus einem früheren Jahr
        $anspruchGleich = $jv['anspruch'] === null ? $alt['anspruch'] === null : ((float)$jv['anspruch'] === (float)($alt['anspruch'] ?? hr_anspruch($ist, $jahr)));
        $uebertragGleich = $jv['uebertrag'] === null ? $alt['uebertrag'] === null : ($alt['uebertrag'] !== null && (float)$jv['uebertrag'] === (float)$alt['uebertrag']);
        if (!$anspruchGleich || !$uebertragGleich) fail($nein, 403);
        $jahr = null; $jv = null;
    }
}
/* Kennungen der eigenen Person(en) des angemeldeten Mitarbeiters (verknüpft, auch nicht im Urlaubsplan) – für das
   Vier-Augen-Prinzip bei Angaben, Zuordnung und Importen: eigene Daten ändert immer eine andere Person der Personalstelle */
function hr_eigene_ids(array $personal, array $me): array
{
    $o = [];
    foreach ($personal['personen'] as $p) if ($p['nutzer'] !== null && $p['nutzer'] === (string)$me['id']) $o[$p['id']] = true;
    return $o;
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
        if ($e['art'] === 'G') $aus['gleitKonto'] = hr_gleit_konto($p, $abw['eintraege'], $kj);   // Gleittag-Antrag: Rest des Gleittage-Kontos
        // Tage des Antrags im Jahr des Kontos (über den Jahreswechsel zählt der Rest im Folgejahr)
        $aus['tageImJahr'] = hr_tage_summe(hr_tage($p, $e['von'], $e['bis'], "$kj-01-01", "$kj-12-31", $freiJe[$e['person']]), $e['art']);
        $aus['vertretungName'] = $e['vertretung'] && isset($idx[$e['vertretung']]) ? hr_name($idx[$e['vertretung']]) : null;
        $aus['vertretung2Name'] = ($e['vertretung2'] ?? null) && isset($idx[$e['vertretung2']]) ? hr_name($idx[$e['vertretung2']]) : null;
        $aus['eigen'] = hr_eigen($personal, $me, $e);
        $aus['kollegen'] = [];
        foreach ($abw['eintraege'] as $o) {
            if ($o['id'] === $e['id'] || $o['person'] === $e['person'] || !in_array($o['status'], HR_AKTIV, true) || $o['bis'] < $e['von'] || $o['von'] > $e['bis']) continue;
            $op = $idx[$o['person']] ?? null;
            $gem = hr_schnitt_ohne_schliesstage($o, $e);   // nur am 24.12./31.12. zusammen weg: Betrieb ohnehin geschlossen
            if ($op && $op['abteilung'] === $p['abteilung'] && $gem) $aus['kollegen'][] = hr_name($op) . ' (' . hr_zeitraum_text($gem[0], $gem[count($gem) - 1]) . ')';
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
   nicht genommen (genehmigt) ist, verfällt – außer der Verfall ist für die Person abgeschaltet („verfall“ = false, dann
   bleibt der Übertrag ganz erhalten). „verfall“ steht auch in der Rückgabe. */
function hr_konto(array $p, array $eintraege, int $jahr, ?string $heute = null, int $tiefe = 0): array
{
    $heute = $heute ?? hr_heute();
    $u = ['genommen' => 0, 'geplant' => 0, 'beantragt' => 0, 'bis_frist' => 0];
    $frist = sprintf('%04d-%s', $jahr, hr_uebertrag_bis());
    $frei = hr_freie_tage($eintraege, $p['id']);
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id']) continue;
        // nur Urlaub – Krankheit nie, auch nicht mit urlaubAbzug aus der Zeiterfassung (Inhaber 30.10.2026)
        if ($e['art'] !== 'U' || !in_array($e['status'], HR_AKTIV, true)) continue;
        foreach (hr_tage($p, $e['von'], $e['bis'], "$jahr-01-01", "$jahr-12-31", $frei) as $d) {
            $w = hr_tag_wert($d);   // Schließtage zählen hier nicht – dort gilt der Betriebsurlaub (unten)
            if ($e['status'] === 'beantragt') { $u['beantragt'] += $w; continue; }
            $u[$d <= $heute ? 'genommen' : 'geplant'] += $w;
            if ($d <= $frist) $u['bis_frist'] += $w;
        }
    }
    // Betriebsurlaub 24.12./31.12.: automatisch je ½ Tag, wie genehmigter Urlaub (verpflichtend, Inhaber 10.11.2026)
    $betrieb = 0.0;
    foreach (hr_betriebsurlaub($p, $eintraege, $jahr) as $d) {
        $u[$d <= $heute ? 'genommen' : 'geplant'] += HR_BETRIEBSURLAUB_WERT;
        if ($d <= $frist) $u['bis_frist'] += HR_BETRIEBSURLAUB_WERT;
        $betrieb += HR_BETRIEBSURLAUB_WERT;
    }
    $anspruch = hr_anspruch($p, $jahr);
    $manuell = $p['jahre'][(string)$jahr]['uebertrag'] ?? null;
    if ($manuell !== null) $uebertrag = $manuell;
    else {
        // automatisch nur, wenn für das Vorjahr ein Anspruch bekannt ist (sonst z. B. nach einer Übernahme negative Reste)
        $vorjahrDaten = (bool)array_filter($p['jahre'], function ($v, $j) use ($jahr) { return (int)$j < $jahr && $v['anspruch'] !== null; }, ARRAY_FILTER_USE_BOTH);
        $uebertrag = $vorjahrDaten && $tiefe < 30 ? hr_konto($p, $eintraege, $jahr - 1, $heute, $tiefe + 1)['rest_jahresende'] : 0.0;
    }
    // Verfall: je Mitarbeiter abschaltbar (hr-personal „verfall“) und erst ab dem Jahr der Übergangsregel (hr_verfall_ab)
    $verfall = ($p['verfall'] ?? true) !== false && $jahr >= hr_verfall_ab();
    $offen = $verfall ? max(0.0, $uebertrag - $u['bis_frist']) : 0.0;   // bis zur Frist noch nicht verplanter Übertrag (ohne Verfall: nichts)
    $verfallen = $heute > $frist ? $offen : 0.0;
    $rest = $anspruch + $uebertrag - $verfallen - $u['genommen'] - $u['geplant'];
    // Rest zum Jahresende (für den Übertrag ins Folgejahr): Verfall gilt dann in jedem Fall
    $restEnde = $anspruch + $uebertrag - $offen - $u['genommen'] - $u['geplant'];
    return ['jahr' => $jahr, 'anspruch' => $anspruch, 'uebertrag' => $uebertrag, 'uebertrag_manuell' => $manuell !== null,
            'frist' => $frist, 'verfall' => $verfall, 'verfaellt' => $heute <= $frist ? $offen : 0.0, 'verfallen' => $verfallen,
            'genommen' => $u['genommen'], 'geplant' => $u['geplant'], 'beantragt' => $u['beantragt'], 'betriebsurlaub' => $betrieb,
            'rest' => $rest, 'verfuegbar' => $rest - $u['beantragt'], 'rest_jahresende' => $restEnde];
}

/* ---------------- Gleittage-Konto (Inhaber 02.11.2026) ----------------
   Gewährung: {id, tage (halbe Tage, −50 … 50, nicht 0), grund, am (JJJJ-MM-TT), t, von, vonId, storniert: null|{t, by, grund}}.
   Negative Gewährungen sind Korrekturen. Stornierte zählen nicht, bleiben aber sichtbar. */
const HR_GLEIT_MAX = 50;            // höchstens so viele Tage je Gewährung (auch als Korrektur)
const HR_GLEIT_GEWAEHRUNGEN = 500;  // je Person

function hr_gleit_norm($l): array
{
    $out = [];
    foreach (is_array($l) ? $l : [] as $g) {
        if (!is_array($g) || !is_numeric($g['tage'] ?? null) || !hr_datum($g['am'] ?? null)) continue;
        $out[] = ['id' => (string)($g['id'] ?? ''), 'tage' => (float)$g['tage'], 'grund' => (string)($g['grund'] ?? ''), 'am' => (string)$g['am'],
                  't' => $g['t'] ?? null, 'von' => (string)($g['von'] ?? ''), 'vonId' => (string)($g['vonId'] ?? ''),
                  'storniert' => is_array($g['storniert'] ?? null) ? $g['storniert'] : null] + $g;
    }
    return $out;
}

/* Wirksame Gewährungen und Beginn des Kontos (Tag der ersten wirksamen Gewährung) */
function hr_gleit_wirksam(array $p): array { return array_values(array_filter($p['gleittage'] ?? [], function ($g) { return $g['storniert'] === null; })); }
function hr_gleit_beginn(array $p): ?string
{
    $b = null;
    foreach (hr_gleit_wirksam($p) as $g) if ($b === null || $g['am'] < $b) $b = $g['am'];
    return $b;
}

/* Gleittage-Konto einer Person für ein Jahr: Übertrag (Rest des Vorjahres, ohne Verfall) + gewährt − genommen − geplant = Rest;
   verfügbar = Rest − beantragt. Gezählt werden genehmigte bzw. beantragte Gleittage (G) an Arbeitstagen ab Beginn des Kontos. */
function hr_gleit_konto(array $p, array $eintraege, int $jahr, ?string $heute = null): array
{
    $heute = $heute ?? hr_heute();
    $beginn = hr_gleit_beginn($p);
    $leer = ['jahr' => $jahr, 'aktiv' => false, 'beginn' => $beginn, 'uebertrag' => 0.0, 'gewaehrt' => 0.0, 'genommen' => 0, 'geplant' => 0, 'beantragt' => 0,
             'rest' => 0.0, 'verfuegbar' => 0.0];
    if ($beginn === null || $jahr < (int)substr($beginn, 0, 4)) return $leer;
    $wirksam = hr_gleit_wirksam($p);
    $frei = hr_freie_tage($eintraege, $p['id']);
    $rest = 0.0; $k = $leer;
    for ($j = (int)substr($beginn, 0, 4); $j <= $jahr; $j++) {
        $k = ['jahr' => $j, 'aktiv' => true, 'beginn' => $beginn, 'uebertrag' => $rest, 'gewaehrt' => 0.0, 'genommen' => 0, 'geplant' => 0, 'beantragt' => 0];
        foreach ($wirksam as $g) if ((int)substr($g['am'], 0, 4) === $j) $k['gewaehrt'] += $g['tage'];
        $ab = max($beginn, "$j-01-01");
        foreach ($eintraege as $e) {
            if ($e['person'] !== $p['id'] || ($e['art'] ?? '') !== 'G' || !in_array($e['status'], HR_AKTIV, true)) continue;
            foreach (hr_tage($p, $e['von'], $e['bis'], $ab, "$j-12-31", $frei) as $d) {
                $w = hr_tag_wert($d, 'G');   // Schließtage je ½
                if ($e['status'] === 'beantragt') $k['beantragt'] += $w;
                else $k[$d <= $heute ? 'genommen' : 'geplant'] += $w;
            }
        }
        $rest = $k['uebertrag'] + $k['gewaehrt'] - $k['genommen'] - $k['geplant'];
        $k['rest'] = $rest; $k['verfuegbar'] = $rest - $k['beantragt'];
    }
    return $k;
}

/* Gewährungen für die Ausgabe (neueste zuerst); $voll: mit Kennung der gewährenden Person (nur Personalstelle) */
function hr_gleit_aus(array $p, bool $voll = false): array
{
    $l = array_map(function ($g) use ($voll) {
        $o = ['id' => $g['id'], 'tage' => $g['tage'], 'grund' => $g['grund'], 'am' => $g['am'], 'von' => $g['von'],
              'storniert' => $g['storniert'] ? ['t' => $g['storniert']['t'] ?? null, 'by' => (string)($g['storniert']['by'] ?? ''), 'grund' => (string)($g['storniert']['grund'] ?? '')] : null];
        return $voll ? $o + ['t' => $g['t']] : $o;
    }, array_reverse($p['gleittage'] ?? []));   // gespeichert in der Reihenfolge der Gewährung: neueste zuerst
    usort($l, function ($a, $b) { return $b['am'] <=> $a['am']; });     // stabil: am selben Tag bleibt die neueste vorn
    return $l;
}

/* Gleittage gewähren oder eine Gewährung stornieren (Personalstelle, nie für sich selbst). $b: person, tage, grund – oder
   person, id, stornieren, grund. Gibt die geänderte Person (Rohdaten) zurück. */
function hr_gleittage_setzen(array $b, array $me): array
{
    return with_lock('hr-personal', function () use ($b, $me) {
        $personal = hr_personal();
        $p = hr_personen_index($personal)[(string)($b['person'] ?? '')] ?? null;
        if (!$p) fail('Bitte einen Mitarbeiter wählen.', 422);
        if (hr_eigene_person($personal, $me, $p['id'])) fail('Eigene Gleittage gewährt eine andere Person der Personalstelle.', 403);
        if (!empty($p['altbestand']) || $p['nutzer'] === null) fail('Gleittage lassen sich nur Mitarbeitern im Urlaubsplan gewähren.', 422);
        $roh = hr_personal_roh();
        $i = null;
        foreach ($roh['personen'] as $k => $e) if ($e['nutzer'] === $p['nutzer']) { $i = $k; break; }
        $jetzt = now();
        if (!empty($b['stornieren'])) {
            if ($i === null) fail('Gewährung nicht gefunden.', 404);
            $id = (string)($b['id'] ?? '');
            foreach ($roh['personen'][$i]['gleittage'] as &$g) {
                if ($g['id'] !== $id) continue;
                if ($g['storniert'] !== null) fail('Diese Gewährung ist bereits storniert.', 409);
                $g['storniert'] = ['t' => $jetzt, 'by' => $me['name'], 'byId' => $me['id'], 'grund' => s($b['grund'] ?? '', 200) ?? ''];
                unset($g);
                hr_personal_schreiben($roh);
                return [$roh['personen'][$i], 'storniert'];
            }
            fail('Gewährung nicht gefunden.', 404);
        }
        if (!$p['aktiv']) fail('Gleittage lassen sich nur Mitarbeitern im Urlaubsplan gewähren.', 422);
        $t = $b['tage'] ?? null;
        if (!is_numeric($t) || (float)$t == 0.0 || abs((float)$t) > HR_GLEIT_MAX || fmod((float)$t * 2, 1.0) != 0.0)
            fail('Bitte die Anzahl in ganzen oder halben Tagen angeben (höchstens ' . HR_GLEIT_MAX . ', negativ zum Korrigieren).', 422);
        $grund = trim(s($b['grund'] ?? '', 200) ?? '');
        if ((float)$t < 0 && $grund === '') fail('Bitte bei einer Korrektur (negative Anzahl) einen Grund angeben.', 422);
        if ($i === null) {
            $users = users_load();
            $ui = user_find($users, (string)$p['nutzer']);
            if ($ui === null) fail('Mitarbeiter nicht gefunden.', 404);
            hr_angaben_setzen($roh, (string)$p['nutzer'], [], $users[$ui]);
            $i = array_key_last($roh['personen']);
        }
        if (count($roh['personen'][$i]['gleittage']) >= HR_GLEIT_GEWAEHRUNGEN) fail('Zu viele Gewährungen für diesen Mitarbeiter.', 422);
        $roh['personen'][$i]['gleittage'][] = ['id' => hr_neue_id('g'), 'tage' => (float)$t, 'grund' => $grund, 'am' => hr_heute(), 't' => $jetzt,
                                               'von' => $me['name'], 'vonId' => $me['id'], 'storniert' => null];
        hr_personal_schreiben($roh);
        return [$roh['personen'][$i], 'gewährt'];   // die neue Gewährung ist die letzte der Liste
    });
}

/* ---------------- Urlaubsübersicht (Recht hr.uebersicht oder hr.verwalten) ----------------
   Je Mitarbeiter im Urlaubsplan nur Summen eines Jahres: Urlaubskonto (hr_konto) und genehmigte Arbeitstage je Art
   (Krank, Gleittag). Keine Zeiträume, Notizen, Gründe oder Entscheidungen – Krankheitstage sind Gesundheitsdaten und
   erscheinen nur hier als Anzahl. */
function hr_tage_je_art(array $p, array $eintraege, int $jahr): array
{
    $n = ['K' => 0, 'G' => 0, 'F' => 0];
    $frei = hr_freie_tage($eintraege, $p['id']);
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id'] || $e['status'] !== 'genehmigt' || !isset($n[$e['art']])) continue;
        $n[$e['art']] += hr_tage_summe(hr_tage($p, $e['von'], $e['bis'], "$jahr-01-01", "$jahr-12-31", $frei), $e['art']);   // Gleittag am Schließtag: zählt nicht (Betriebsurlaub)
    }
    return $n;
}
/* Gleittage-Konto in der Übersicht: gewährt (mit Übertrag) und Rest – ohne Konto beides leer */
function hr_gleit_summen(array $k): array
{
    return ['gleitGewaehrt' => $k['aktiv'] ? $k['uebertrag'] + $k['gewaehrt'] : null, 'gleitRest' => $k['aktiv'] ? $k['rest'] : null];
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
                     'krank' => $t['K'], 'gleittage' => $t['G'], 'unentschuldigt' => $t['F']] + hr_gleit_summen(hr_gleit_konto($p, $abw, $jahr));
    }
    return $zeilen;
}

/* ---------------- Einträge (Anträge und Eintragungen der Personalstelle) ---------------- */

/* Eintrag für die Ausgabe. $voll: Personalstelle oder die Person selbst (Art, Notiz, Entscheidung) */
function hr_eintrag_aus(array $e, array $p, array $frei = []): array
{
    return ['id' => $e['id'], 'person' => $e['person'], 'name' => hr_name($p), 'art' => $e['art'], 'artText' => HR_ARTEN[$e['art']] ?? $e['art'],
            'von' => $e['von'], 'bis' => $e['bis'], 'tage' => $e['art'] === 'X' ? count(hr_tage($p, $e['von'], $e['bis'])) : hr_tage_summe(hr_tage($p, $e['von'], $e['bis'], null, null, $frei), $e['art']), 'status' => $e['status'],
            'notiz' => (string)($e['notiz'] ?? ''), 'vertretung' => $e['vertretung'] ?? null, 'vertretung2' => $e['vertretung2'] ?? null, 'quelle' => (string)($e['quelle'] ?? ''),
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
/* ---------------- Korrekturmeldungen (Dokument hr-korrekturen) ----------------
   {rev, meldungen: [{id, person, von?, bis?, eintrag?, text, status: offen|erledigt, erfasst: {t, by, byId},
   erledigt?: {t, by, antwort}}]} – nie gelöscht; sichtbar nur für die Person selbst und die Personalstelle. */
const HR_MAX_KORREKTUREN = 5000;
const HR_MAX_KORREKTUREN_OFFEN = 20;          // je Person gleichzeitig offen
function hr_korrekturen(): array
{
    $d = store_read('hr-korrekturen') ?? [];
    return ['rev' => (int)($d['rev'] ?? 0), 'meldungen' => array_values(array_filter((array)($d['meldungen'] ?? []), function ($m) {
        return is_array($m) && isset($m['id'], $m['person'], $m['text'], $m['status']);
    }))];
}
function hr_korrekturen_schreiben(array $d): void
{
    if (count($d['meldungen']) > HR_MAX_KORREKTUREN) throw new InvalidArgumentException('Zu viele Korrekturmeldungen.');
    store_write('hr-korrekturen', ['rev' => $d['rev'] + 1, 'meldungen' => array_values($d['meldungen'])]);
}
/* Meldung für die Ausgabe (Person selbst oder Personalstelle); $p: Person der Meldung (für den Namen), sonst „ehemalig“ */
function hr_korrektur_aus(array $m, ?array $p): array
{
    return ['id' => $m['id'], 'person' => $m['person'], 'name' => $p ? hr_name($p) : 'ehemaliger Mitarbeiter',
            'von' => $m['von'] ?? null, 'bis' => $m['bis'] ?? null, 'eintrag' => $m['eintrag'] ?? null, 'text' => (string)$m['text'],
            'status' => $m['status'] === 'erledigt' ? 'erledigt' : 'offen', 'erfasst' => $m['erfasst'] ?? null,
            'erledigt' => isset($m['erledigt']) ? ['t' => $m['erledigt']['t'] ?? null, 'by' => $m['erledigt']['by'] ?? '', 'antwort' => (string)($m['erledigt']['antwort'] ?? '')] : null];
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
        $out[] = ['tag' => $t, 'datum' => $d, 'wt' => HR_WOCHENTAGE[$w], 'wochenende' => $w >= 6, 'feiertag' => hr_feiertag($d), 'schliesstag' => hr_schliesstag($d),
                  'ferien' => (hr_in_zeitraum($einst['ferien'], $d)['text'] ?? null) !== null, 'sperre' => hr_in_zeitraum($einst['sperren'], $d) !== null];
    }
    return $out;
}

/* Arten, die die Sicht 'urlaub' (Recht hr.kalender) bei Kollegen mit ihrem Kürzel zeigt – alles andere bleibt „A“ */
const HR_KALENDER_ARTEN = ['U', 'G'];

/* Gleiche Abteilung (Sicht 'urlaub' nur für Kollegen der eigenen Abteilung, Inhaber 11.11.2026): über die Nummer der
   Stammdaten (abteilungNr, nach hr_personal auch für Angaben, die nur den – auch früheren – Namen tragen), sonst über den
   Namen ohne Groß-/Kleinschreibung und doppelte Leerzeichen. Ohne Abteilung nie gleich (auch nicht zwei leere). */
function hr_gleiche_abteilung(array $a, array $b): bool
{
    if (($a['abteilungNr'] ?? null) !== null && ($b['abteilungNr'] ?? null) !== null) return (string)$a['abteilungNr'] === (string)$b['abteilungNr'];
    $na = hr_namekey((string)($a['abteilung'] ?? ''));
    return $na !== '' && $na === hr_namekey((string)($b['abteilung'] ?? ''));
}

/* Kürzel je Person und Tag eines Monats.
   $sicht: 'voll' (Personalstelle: Art, auch beantragt mit „?“), 'eigen' (eigene Zeile wie voll), 'kollege' (nur „A“ =
   abwesend, nur genehmigt, nie der Grund; freie Tage einer verkürzten Woche ebenfalls „A“), 'urlaub' (Recht hr.kalender,
   Inhaber 11.11.2026, nur für Kollegen der eigenen Abteilung – hr_monat: wie 'kollege', aber genehmigter Urlaub „U“ und
   Gleittag „G“ mit Kürzel – Krank, Unentschuldigt und freie Tage bleiben „A“, offene Anträge unsichtbar). */
function hr_zeile(array $p, array $eintraege, array $tage, string $sicht): array
{
    $kollege = $sicht === 'kollege' || $sicht === 'urlaub';   // fremde Zeile: nur genehmigt, freie Tage nur „A“
    $out = [];
    foreach ($tage as $t) {
        if ($t['wochenende'] || $t['feiertag'] !== null) continue;
        if (!in_array(hr_wochentag($t['datum']), $p['arbeitstage'], true)) $out[$t['tag']] = $kollege ? 'A' : 'x';
    }
    $erster = $tage[0]['datum']; $letzter = $tage[count($tage) - 1]['datum'];
    foreach ($eintraege as $e) {
        if ($e['person'] !== $p['id'] || !in_array($e['status'], HR_AKTIV, true) || $e['bis'] < $erster || $e['von'] > $letzter) continue;
        if ($kollege && $e['status'] !== 'genehmigt') continue;
        foreach ($tage as $t) {
            $d = $t['datum'];
            if ($d < $e['von'] || $d > $e['bis'] || $t['wochenende'] || $t['feiertag'] !== null) continue;
            if ($e['art'] === 'X') { $out[$t['tag']] = $kollege ? 'A' : 'x'; continue; }
            if (!in_array(hr_wochentag($d), $p['arbeitstage'], true)) continue;
            $out[$t['tag']] = $sicht === 'urlaub' ? (in_array($e['art'], HR_KALENDER_ARTEN, true) ? $e['art'] : 'A')
                : ($kollege ? 'A' : $e['art'] . ($e['status'] === 'beantragt' ? '?' : ''));
        }
    }
    return $out;
}

/* Monatsplan: alle aktiven Mitarbeiter, gruppiert nach Abteilung (Reihenfolge laut Position).
   $kollegen: Sicht auf fremde Zeilen ohne $voll – 'kollege' (Standard, nur „A“) oder 'urlaub' (Recht hr.kalender). 'urlaub'
   gilt je Zeile nur für Kollegen der eigenen Abteilung (Inhaber 11.11.2026); andere Abteilungen wie 'kollege'. Ohne eigene
   Person im Urlaubsplan oder ohne Abteilung bei niemandem. Antwort: „sicht“ (voll | urlaub | kollege – wirksame Sicht) und
   „urlaubAbteilung“ (Name der eigenen Abteilung bei 'urlaub', sonst null). */
function hr_monat(int $jahr, int $monat, array $me, bool $voll, string $kollegen = 'kollege'): array
{
    if (!in_array($kollegen, ['kollege', 'urlaub'], true)) $kollegen = 'kollege';
    $personal = hr_personal(); $abw = hr_abwesenheiten(); $einst = hr_einstellungen();
    $tage = hr_monatstage($jahr, $monat, $einst);
    $ich = hr_ich($personal, $me);
    $urlaub = !$voll && $kollegen === 'urlaub' && $ich !== null && hr_gleiche_abteilung($ich, $ich);   // hat eine Abteilung
    $zeilen = [];
    foreach (hr_nach_abteilung($personal['personen']) as $p) {
        if (!$p['aktiv']) continue;
        $eigen = $ich !== null && $ich['id'] === $p['id'];
        $sicht = $voll || $eigen ? 'voll' : ($urlaub && hr_gleiche_abteilung($ich, $p) ? 'urlaub' : 'kollege');
        $zeilen[] = ['id' => $p['id'], 'name' => hr_name($p), 'abteilung' => $p['abteilung'], 'ich' => $eigen,
                     'tage' => (object)hr_zeile($p, $abw['eintraege'], $tage, $sicht)];
    }
    return ['jahr' => $jahr, 'monat' => $monat, 'name' => HR_MONATE[$monat], 'tage' => $tage, 'personen' => $zeilen,
            'sperren' => $einst['sperren'], 'ferien' => $einst['ferien'],
            'sicht' => $voll ? 'voll' : ($urlaub ? 'urlaub' : 'kollege'), 'urlaubAbteilung' => $urlaub ? $ich['abteilung'] : null];
}

/* Startseite des Dashboards („Heute für Sie“, lib/startseite.php): was dieser Mitarbeiter in HR entscheiden kann – dieselben
   Zahlen wie am Reiter „Anträge“ (hr_start: offene Anträge ohne eigene, Korrekturmeldungen der Personalstelle). Bewusst nur
   Anzahlen und das früheste Datum, keine Namen oder Arten (Abwesenheiten sind Personaldaten, Krankheit Gesundheitsdaten). */
function hr_startseite(array $me): array
{
    $genehmigen = may($me, 'hr.genehmigen'); $verwalten = may($me, 'hr.verwalten');
    if (!$genehmigen && !$verwalten) return [];
    $heute = hr_heute(); $personal = hr_personal(); $out = [];
    $offen = array_filter(hr_abwesenheiten()['eintraege'], function ($e) use ($genehmigen, $personal, $me) {
        return $e['status'] === 'beantragt' && (!$genehmigen || !hr_eigen($personal, $me, $e));
    });
    if ($offen) {
        $n = count($offen); $ab = min(array_column($offen, 'von'));
        $out[] = ['art' => $ab < $heute ? 'ueberfaellig' : 'heute', 'titel' => $n === 1 ? 'Antrag entscheiden' : "$n Anträge entscheiden",
                  'detail' => ($ab < $heute ? 'Beginn schon vorbei: ' : 'frühester Beginn ') . startseite_de($ab), 'datum' => $ab < $heute ? $ab : '', 'ziel' => 'antraege', 'anzahl' => $n];
    }
    if ($verwalten) {
        $eigene = hr_eigene_ids($personal, $me);
        $n = count(array_filter(hr_korrekturen()['meldungen'], function ($m) use ($eigene) { return $m['status'] === 'offen' && !isset($eigene[$m['person']]); }));
        if ($n) $out[] = ['art' => 'heute', 'titel' => $n === 1 ? 'Korrekturmeldung bearbeiten' : "$n Korrekturmeldungen bearbeiten", 'detail' => 'Personalstelle',
                          'ziel' => 'antraege', 'anzahl' => $n];
    }
    return $out;
}

require_once __DIR__ . '/mail.php';   // E-Mails der Urlaubsverwaltung (Erinnerung, Monatsübersicht, Steuerberater)
require_once __DIR__ . '/planung.php';   // Jahresplanung (Vorplanung des nächsten Jahres, Konflikte, Jahresübersicht)
