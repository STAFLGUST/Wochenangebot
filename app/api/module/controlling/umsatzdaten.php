<?php
declare(strict_types=1);
/* Controlling · Umsatzdaten aus der Warenwirtschaft (Kundenumsatztabelle: Kunde, Datum, Artikel, Kolli, Menge, Preis,
   Gesamtbetrag, EKPreis) – Speicherung und Import über die Importzentrale (Importart „umsatzdaten“, in Teilen).

   Dokumente (vertraulich, Einkaufswerte): „controlling-umsatzdaten“ = Verzeichnis { rev, monate: { "JJJJ-MM": Kennzahlen,
   hash }, kunden, artikel, importe, geaendert }; je Monat „controlling-umsatzdaten/JJJJ-MM“ = { monat, hash, zeilen };
   Zwischenablage eines Imports „controlling-umsatzteile/<Kennung>-JJJJ-MM“ (bis zur Übernahme, höchstens einen Tag).
   Zeile = Summe aller Positionen eines Kunden mit einem Artikel an einem Tag, getrennt nach berechnet/ohne Berechnung:
   [Tag, Kunde, Artikel, Kolli, Menge (Tausendstel), Umsatz (Cent), EK-Wert (Cent), Umsatz mit EK (Cent), Positionen, berechnet].
   EK-Wert = Menge × EKPreis der Positionen mit EK; „Umsatz mit EK“ ist deren Umsatz (Deckungsbeitrag nur über diese).
   Positionen ohne Gesamtbetrag (z. B. Leergut) heißen „ohne Berechnung“: Menge und Positionen bleiben erhalten, zählen
   aber nicht zu Menge und Umsatz der Auswertung.

   Import: Der Zeitraum der Datei (erster bis letzter Tag) ersetzt die gespeicherten Umsätze dieses Zeitraums; Monate davor
   und danach bleiben. Verglichen wird je Monat über die Prüfsumme (SHA-256 der Zeilen als JSON, im Browser gleich
   berechnet) – nur geänderte Monate werden übertragen; dieselbe Datei erneut ändert nichts. Der Leser im Browser
   (app/module/controlling/umsatz-import.js) liest die CSV und fasst zusammen; hier prüft der Server jede Zeile erneut.
   Wird von api/index.php geladen; Speicherzugriffe nur auf Dokumente des Controllings (regeln/datenverantwortung.toml). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const UMSATZDATEN = 'controlling-umsatzdaten';
const UMSATZDATEN_TEILE = 'controlling-umsatzteile';
const UMSATZDATEN_ZEILEN_MAX = 60000;      // Zeilen je Monat (heute rund 7 000)
const UMSATZDATEN_MONATE_MAX = 600;        // Monate in einer Datei (50 Jahre)
const UMSATZDATEN_LISTE_MAX = 50000;       // Kunden- bzw. Artikelnummern in einer Datei
const UMSATZDATEN_IMPORTE_MAX = 50;        // Einträge im Importverlauf
const UMSATZDATEN_TEIL_STUNDEN = 24;       // Zwischenablage eines nicht übernommenen Imports
const UMSATZDATEN_RUECKGANG = 0.8;         // Warnung, wenn ein Monat weniger als 80 % der bisherigen Positionen hat

/* Verzeichnis mit Standardwerten; unbekannte (neuere) Felder bleiben erhalten (GR-006) */
function umsatzdaten_index(): array
{
    $d = store_read(UMSATZDATEN) ?? [];
    return ['rev' => (int)($d['rev'] ?? 0), 'monate' => is_array($d['monate'] ?? null) ? $d['monate'] : [],
            'kunden' => is_array($d['kunden'] ?? null) ? $d['kunden'] : [], 'artikel' => is_array($d['artikel'] ?? null) ? $d['artikel'] : [],
            'importe' => is_array($d['importe'] ?? null) ? $d['importe'] : [], 'geaendert' => $d['geaendert'] ?? null] + $d;
}

/* Zeilen eines gespeicherten Monats (leer, wenn es ihn nicht gibt) */
function umsatzdaten_monat(string $m): array
{
    $d = store_read(UMSATZDATEN . '/' . $m);
    return is_array($d['zeilen'] ?? null) ? $d['zeilen'] : [];
}

/* Prüfsumme der Zeilen – identisch mit JSON.stringify im Browser (nur Ganzzahlen und ASCII-Nummern) */
function umsatzdaten_hash(array $zeilen): string
{
    return hash('sha256', json_encode($zeilen, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
}

function umsatzdaten_monat_gueltig($m): bool
{
    return is_string($m) && preg_match('/^(\d{4})-(0[1-9]|1[0-2])$/', $m, $x) === 1 && (int)$x[1] >= 2000 && (int)$x[1] <= 2100;
}
function umsatzdaten_tage(string $m): int { return (int)date('t', (int)mktime(0, 0, 0, (int)substr($m, 5, 2), 1, (int)substr($m, 0, 4))); }
function umsatzdaten_datum($v): string
{
    if (!is_string($v) || !preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $x) || !checkdate((int)$x[2], (int)$x[3], (int)$x[1]) || (int)$x[1] < 2000 || (int)$x[1] > 2100)
        throw new InvalidArgumentException('Ungültiger Zeitraum der Datei.');
    return $v;
}
/* Monate von … bis (je „JJJJ-MM“, einschließlich) */
function umsatzdaten_monatsfolge(string $von, string $bis): array
{
    $out = [];
    [$j, $m] = [(int)substr($von, 0, 4), (int)substr($von, 5, 2)];
    while (sprintf('%04d-%02d', $j, $m) <= $bis) { $out[] = sprintf('%04d-%02d', $j, $m); if (++$m > 12) { $m = 1; $j++; } }
    return $out;
}

/* Reihenfolge der Zeilen: Tag, Kunde, Artikel, berechnet (0 vor 1) – streng steigend, also ohne Doppelte */
function umsatzdaten_schluessel_kleiner(array $a, array $b): bool
{
    if ($a[0] !== $b[0]) return $a[0] < $b[0];
    if (($c = strcmp($a[1], $b[1])) !== 0) return $c < 0;
    if (($c = strcmp($a[2], $b[2])) !== 0) return $c < 0;
    return $a[9] < $b[9];
}
function umsatzdaten_sortieren(array &$z): void
{
    usort($z, fn($a, $b) => $a[0] <=> $b[0] ?: strcmp($a[1], $b[1]) ?: strcmp($a[2], $b[2]) ?: $a[9] <=> $b[9]);
}

/* Zeilen eines Monats aus dem Browser prüfen (jede Zahl ganzzahlig, Nummern wie in der Warenwirtschaft) */
function umsatzdaten_zeilen_pruefen(string $m, $zeilen): array
{
    if (!is_array($zeilen) || !array_is_list($zeilen) || count($zeilen) > UMSATZDATEN_ZEILEN_MAX) throw new InvalidArgumentException("$m: ungültige oder zu viele Zeilen.");
    $tage = umsatzdaten_tage($m);
    $int = fn($v, int $max) => is_int($v) && $v >= -$max && $v <= $max;
    $out = []; $vorher = null;
    foreach ($zeilen as $i => $z) {
        if (!is_array($z) || !array_is_list($z) || count($z) !== 10) throw new InvalidArgumentException("$m: Zeile " . ($i + 1) . ' ist ungültig.');
        [$tag, $kunde, $artikel, $kolli, $menge, $umsatz, $ek, $umsatzEk, $pos, $ber] = $z;
        if (!is_int($tag) || $tag < 1 || $tag > $tage || !is_string($kunde) || !preg_match('/^[0-9A-Za-z._-]{1,20}$/', $kunde)
            || !is_string($artikel) || !preg_match('#^[0-9A-Za-z._/-]{1,20}$#', $artikel)
            || !$int($kolli, 1000000000) || !$int($menge, 1000000000000) || !$int($umsatz, 1000000000000) || !$int($ek, 1000000000000)
            || !$int($umsatzEk, 1000000000000) || !is_int($pos) || $pos < 1 || $pos > 1000000 || ($ber !== 0 && $ber !== 1)
            || ($ber === 0 && ($umsatz !== 0 || $ek !== 0 || $umsatzEk !== 0)))
            throw new InvalidArgumentException("$m: Zeile " . ($i + 1) . ' enthält ungültige Werte.');
        if ($vorher !== null && !umsatzdaten_schluessel_kleiner($vorher, $z)) throw new InvalidArgumentException("$m: Zeilen nicht sortiert oder doppelt.");
        $out[] = $vorher = $z;
    }
    return $out;
}

/* Kennzahlen eines Monats (für Verzeichnis und Vorschau) */
function umsatzdaten_summen(array $zeilen): array
{
    $s = ['zeilen' => count($zeilen), 'pos' => 0, 'umsatz' => 0, 'menge' => 0, 'posOhne' => 0, 'kunden' => 0, 'artikel' => 0, 'ersterTag' => null, 'letzterTag' => null];
    $k = []; $a = [];
    foreach ($zeilen as $z) {
        if ($z[9] === 1) { $s['pos'] += $z[8]; $s['umsatz'] += $z[5]; $s['menge'] += $z[4]; } else $s['posOhne'] += $z[8];
        $k[$z[1]] = true; $a[$z[2]] = true;
        $s['ersterTag'] ??= $z[0]; $s['letzterTag'] = $z[0];
    }
    $s['kunden'] = count($k); $s['artikel'] = count($a);
    return $s;
}

/* Zeilen eines Monats im Tagesbereich [von, bis] bzw. außerhalb */
function umsatzdaten_tagesbereich(array $zeilen, int $von, int $bis, bool $innen): array
{
    return array_values(array_filter($zeilen, fn($z) => ($z[0] >= $von && $z[0] <= $bis) === $innen));
}

/* Zusammenfassung des Lesers (daten der Vorschau und Übernahme) prüfen */
function umsatzdaten_eingabe(array $e): array
{
    if ((int)($e['version'] ?? 0) !== 1) throw new InvalidArgumentException('Unbekanntes Format der Umsatzdaten. Bitte die Seite neu laden.');
    $von = umsatzdaten_datum($e['zeitraum']['von'] ?? null);
    $bis = umsatzdaten_datum($e['zeitraum']['bis'] ?? null);
    if ($von > $bis) throw new InvalidArgumentException('Ungültiger Zeitraum der Datei.');
    $monate = is_array($e['monate'] ?? null) ? $e['monate'] : [];
    if (!$monate) throw new InvalidArgumentException('Die Datei enthält keine Umsätze.');
    if (count($monate) > UMSATZDATEN_MONATE_MAX) throw new InvalidArgumentException('Die Datei umfasst zu viele Monate.');
    $out = [];
    foreach ($monate as $m => $x) {
        $m = (string)$m;
        if (!umsatzdaten_monat_gueltig($m) || $m < substr($von, 0, 7) || $m > substr($bis, 0, 7) || !is_array($x) || !is_string($x['hash'] ?? null) || !preg_match('/^[a-f0-9]{64}$/', $x['hash']))
            throw new InvalidArgumentException("Ungültige Angaben zum Monat $m.");
        $z = [];
        foreach (['zeilen', 'pos', 'umsatz', 'menge', 'posOhne'] as $f) { $v = $x[$f] ?? 0; if (!is_int($v) || abs($v) > 1e15) throw new InvalidArgumentException("Ungültige Angaben zum Monat $m."); $z[$f] = $v; }
        $out[$m] = ['hash' => $x['hash']] + $z;
    }
    ksort($out, SORT_STRING);
    $liste = function ($l) {
        if (!is_array($l) || count($l) > UMSATZDATEN_LISTE_MAX) throw new InvalidArgumentException('Ungültige Liste der Nummern.');
        return array_values(array_filter($l, fn($v) => is_string($v) && preg_match('#^[0-9A-Za-z._/-]{1,20}$#', $v)));
    };
    $datei = is_array($e['datei'] ?? null) ? $e['datei'] : [];
    $zahl = fn($v) => is_int($v) && $v >= 0 ? $v : 0;
    return ['von' => $von, 'bis' => $bis, 'monate' => $out, 'kunden' => $liste($e['kunden'] ?? []), 'artikel' => $liste($e['artikel'] ?? []),
            'datei' => ['zeilen' => $zahl($datei['zeilen'] ?? 0), 'ohneArtikel' => $zahl($datei['ohneArtikel'] ?? 0), 'leer' => $zahl($datei['leer'] ?? 0)]];
}

/* Vergleich der Datei mit dem gespeicherten Stand je Monat im Zeitraum der Datei:
   neu (bisher keine Umsätze), geaendert (andere Prüfsumme), unveraendert, entfaellt (gespeichert, aber nicht in der Datei).
   Randmonate, die die Datei nur teilweise abdeckt, vergleichen nur die Tage im Zeitraum (übrige Tage bleiben). */
function umsatzdaten_vergleich(array $in, array $index): array
{
    $vonM = substr($in['von'], 0, 7); $bisM = substr($in['bis'], 0, 7);
    $out = [];
    foreach (umsatzdaten_monatsfolge($vonM, $bisM) as $m) {
        $t1 = $m === $vonM ? (int)substr($in['von'], 8, 2) : 1;
        $t2 = $m === $bisM ? (int)substr($in['bis'], 8, 2) : umsatzdaten_tage($m);
        $teilweise = $t1 > 1 || $t2 < umsatzdaten_tage($m);
        $neu = $in['monate'][$m] ?? null;
        $alt = is_array($index['monate'][$m] ?? null) ? $index['monate'][$m] : null;
        if ($alt && $teilweise) {   // nur die Tage im Zeitraum vergleichen
            $innen = umsatzdaten_tagesbereich(umsatzdaten_monat($m), $t1, $t2, true);
            $alt = $innen ? umsatzdaten_summen($innen) + ['hash' => umsatzdaten_hash($innen)] : null;
        }
        if (!$neu && !$alt) continue;
        $art = !$alt ? 'neu' : (!$neu ? 'entfaellt' : ($neu['hash'] === $alt['hash'] ? 'unveraendert' : 'geaendert'));
        $out[$m] = ['art' => $art, 'neu' => $neu, 'alt' => $alt, 'von' => $t1, 'bis' => $t2, 'teilweise' => $teilweise];
    }
    return $out;
}

function umsatzdaten_monatsname(string $m): string { return CONTROLLING_MONATE[substr($m, 5, 2)] . ' ' . substr($m, 0, 4); }
function umsatzdaten_euro(int $cent): string { return number_format($cent / 100, 2, ',', '.') . ' €'; }
function umsatzdaten_anzahl(int $n): string { return number_format($n, 0, ',', '.'); }
function umsatzdaten_zahlwort(int $n, string $eins, string $viele): string { return umsatzdaten_anzahl($n) . ' ' . ($n === 1 ? $eins : $viele); }
function umsatzdaten_tag(string $d): string { return substr($d, 8, 2) . '.' . substr($d, 5, 2) . '.' . substr($d, 0, 4); }

/* Nummern ohne Stammsatz (Hinweis in der Vorschau): Kunden der Verwaltung, Artikelstammdaten */
function umsatzdaten_unbekannt(array $in): array
{
    $kunden = []; foreach (customers_load()['customers'] as $c) if (($c['nr'] ?? '') !== '') $kunden[code_key((string)$c['nr'])] = true;
    $artikel = []; foreach ((store_read('stammdaten')['articles'] ?? []) as $a) if (is_array($a) && isset($a['code'])) $artikel[code_key((string)$a['code'])] = true;
    return [array_values(array_filter($in['kunden'], fn($k) => !isset($kunden[code_key($k)]))),
            array_values(array_filter($in['artikel'], fn($a) => !isset($artikel[code_key($a)])))];
}

/* Vorschau für die Importzentrale (Vertrag: docs/plattform/schnittstellen/import.md) */
function umsatzdaten_import_vorschau(array $e, array $me): array
{
    $in = umsatzdaten_eingabe($e);
    $index = umsatzdaten_index();
    $v = umsatzdaten_vergleich($in, $index);
    $n = ['neu' => 0, 'geaendert' => 0, 'entfaellt' => 0, 'unveraendert' => 0, 'fehler' => 0];
    $zeilen = []; $teile = []; $h = []; $rueckgang = [];
    $kurz = fn(?array $x) => $x ? umsatzdaten_anzahl($x['pos']) . ' Positionen · Umsatz ' . umsatzdaten_euro($x['umsatz']) : 'keine Umsätze';
    foreach ($v as $m => $x) {
        $n[$x['art']]++;
        if ($x['art'] === 'unveraendert') continue;
        if ($x['art'] === 'neu' || $x['art'] === 'geaendert') $teile[] = $m;
        $text = $x['art'] === 'entfaellt' ? 'nicht in der Datei – gespeicherte Umsätze (' . $kurz($x['alt']) . ') werden gelöscht'
              : ($x['art'] === 'neu' ? $kurz($x['neu']) : $kurz($x['neu']) . ' (bisher ' . $kurz($x['alt']) . ')');
        if ($x['teilweise']) $text .= sprintf(' · nur %02d.–%02d. (übrige Tage bleiben)', $x['von'], $x['bis']);
        $zeilen[] = ['art' => $x['art'], 'schluessel' => $m, 'name' => umsatzdaten_monatsname($m), 'text' => $text];
        if ($x['art'] === 'geaendert' && $x['alt']['pos'] > 0 && $x['neu']['pos'] < UMSATZDATEN_RUECKGANG * $x['alt']['pos']) $rueckgang[] = umsatzdaten_monatsname($m);
    }
    $ausserhalb = count(array_filter(array_keys($index['monate']), fn($m) => !isset($v[$m]) && ($m < substr($in['von'], 0, 7) || $m > substr($in['bis'], 0, 7))));
    $pos = array_sum(array_column($in['monate'], 'pos')); $posOhne = array_sum(array_column($in['monate'], 'posOhne'));
    $h[] = ['stufe' => 'info', 'text' => 'Zeitraum der Datei: ' . umsatzdaten_tag($in['von']) . ' – ' . umsatzdaten_tag($in['bis'])
        . '. Die gespeicherten Umsätze dieses Zeitraums werden durch die Datei ersetzt' . ($ausserhalb ? '; ' . umsatzdaten_zahlwort($ausserhalb, 'Monat davor bzw. danach bleibt', 'Monate davor bzw. danach bleiben') . ' unverändert.' : '.')];
    $h[] = ['stufe' => 'info', 'text' => umsatzdaten_zahlwort($pos, 'berechnete Position', 'berechnete Positionen') . ' in ' . umsatzdaten_zahlwort(count($in['monate']), 'Monat', 'Monaten') . ', '
        . umsatzdaten_zahlwort(count($in['kunden']), 'Kunde', 'Kunden') . ', ' . umsatzdaten_anzahl(count($in['artikel'])) . ' Artikel. Gezählt wird je Monat; nur neue und geänderte Monate werden übertragen.'];
    if ($in['datei']['ohneArtikel']) $h[] = ['stufe' => 'info', 'text' => umsatzdaten_anzahl($in['datei']['ohneArtikel']) . ' Zeilen ohne Artikel (Belegköpfe) übersprungen.'];
    if ($posOhne) $h[] = ['stufe' => 'info', 'text' => umsatzdaten_anzahl($posOhne) . ' Positionen ohne Gesamtbetrag (z. B. Leergut) werden als „ohne Berechnung“ gespeichert und zählen nicht zu Menge und Umsatz.'];
    [$uk, $ua] = umsatzdaten_unbekannt($in);
    if ($uk) $h[] = ['stufe' => 'warn', 'text' => umsatzdaten_zahlwort(count($uk), 'Kundennummer steht', 'Kundennummern stehen') . ' nicht in den Kundenstammdaten (z. B. ' . implode(', ', array_slice($uk, 0, 5)) . ') – sie erscheinen in der Auswertung nur mit Nummer, ohne Vertreter und Kundengruppe.'];
    if ($ua) $h[] = ['stufe' => 'warn', 'text' => umsatzdaten_zahlwort(count($ua), 'Artikelnummer steht', 'Artikelnummern stehen') . ' nicht in den Artikelstammdaten (z. B. ' . implode(', ', array_slice($ua, 0, 5)) . ') – sie erscheinen nur mit Nummer, ohne Artikelgruppe und Fleischart.'];
    if ($rueckgang) $h[] = ['stufe' => 'warn', 'text' => 'Deutlich weniger Positionen als bisher in ' . implode(', ', array_slice($rueckgang, 0, 6)) . (count($rueckgang) > 6 ? ' …' : '') . ' – ist die Datei vollständig (alle Kunden, ganzer Zeitraum)?'];
    if ($n['entfaellt']) $h[] = ['stufe' => 'warn', 'text' => umsatzdaten_zahlwort($n['entfaellt'], 'Monat mit gespeicherten Umsätzen fehlt in der Datei und wird', 'Monate mit gespeicherten Umsätzen fehlen in der Datei und werden') . ' gelöscht.'];
    usort($h, fn($a, $b) => ($a['stufe'] === 'warn' ? 0 : 1) <=> ($b['stufe'] === 'warn' ? 0 : 1));
    return ['zahlen' => $n, 'zeilen' => $zeilen, 'hinweise' => $h, 'stand' => $index['rev'], 'teile' => $teile];
}

/* Ein Monat in die Zwischenablage (Importzentrale: import_teil). Schlüssel = Monat. */
function umsatzdaten_import_teil(array $e, array $me): void
{
    $m = (string)$e['schluessel'];
    $d = $e['daten'];
    if (!umsatzdaten_monat_gueltig($m) || ($d['monat'] ?? null) !== $m) throw new InvalidArgumentException('Ungültiger Monat.');
    $zeilen = umsatzdaten_zeilen_pruefen($m, $d['zeilen'] ?? null);
    $hash = umsatzdaten_hash($zeilen);
    if (($d['hash'] ?? '') !== $hash) throw new InvalidArgumentException(umsatzdaten_monatsname($m) . ': Prüfsumme stimmt nicht. Bitte die Datei erneut wählen.');
    store_write(UMSATZDATEN_TEILE . '/' . $e['upload'] . '-' . $m, ['von' => $me['id'], 't' => time(), 'monat' => $m, 'hash' => $hash, 'zeilen' => $zeilen]);
}

/* Zwischenablage aufräumen: Teile dieses Imports bzw. alle, die älter als UMSATZDATEN_TEIL_STUNDEN sind */
function umsatzdaten_teile_aufraeumen(string $upload = ''): void
{
    foreach (store_names(UMSATZDATEN_TEILE) as $name) {
        $teil = basename($name);
        if ($upload !== '' && str_starts_with($teil, $upload . '-')) { store_delete($name); continue; }
        $t = store_mtime($name);
        if ($t !== null && $t < time() - UMSATZDATEN_TEIL_STUNDEN * 3600) store_delete($name);
    }
}

/* Übernahme: neue und geänderte Monate aus der Zwischenablage schreiben, entfallene löschen, Verzeichnis neu, Protokoll */
function umsatzdaten_import_uebernehmen(array $e, array $me): array
{
    $in = umsatzdaten_eingabe($e);
    $upload = (string)$e['upload'];
    $erg = with_lock(UMSATZDATEN, function () use ($e, $in, $me, $upload) {
        $index = umsatzdaten_index();
        if ((int)($e['stand'] ?? -1) !== $index['rev']) fail('Die Umsatzdaten wurden inzwischen geändert. Die Vorschau wird neu geladen.', 409);
        $vorschau = umsatzdaten_import_vorschau($e, $me);
        $v = umsatzdaten_vergleich($in, $index);
        // Teil eines Monats aus der Zwischenablage (nur vom selben Mitarbeiter, gleiche Prüfsumme wie in der Vorschau)
        $teil = function (string $m, array $x) use ($upload, $me): ?array {
            $t = store_read(UMSATZDATEN_TEILE . '/' . $upload . '-' . $m);
            return is_array($t) && ($t['von'] ?? null) === $me['id'] && ($t['hash'] ?? '') === $x['neu']['hash'] && is_array($t['zeilen'] ?? null) ? $t['zeilen'] : null;
        };
        // zuerst alle Teile prüfen – fehlt einer, wird nichts geschrieben. Je Monat nur einmal im Speicher (Speichergrenze 128 MB)
        foreach ($v as $m => $x) {
            if (($x['art'] === 'neu' || $x['art'] === 'geaendert') && $teil($m, $x) === null)
                fail(umsatzdaten_monatsname($m) . ' wurde nicht vollständig übertragen. Bitte erneut übernehmen.', 422);
        }
        foreach ($v as $m => $x) {
            if ($x['art'] === 'unveraendert') continue;
            $zeilen = $x['art'] === 'entfaellt' ? [] : $teil($m, $x);
            if ($x['teilweise']) {   // Tage außerhalb des Zeitraums der Datei bleiben
                $zeilen = array_merge(umsatzdaten_tagesbereich(umsatzdaten_monat($m), $x['von'], $x['bis'], false), $zeilen);
                umsatzdaten_sortieren($zeilen);
            }
            if (!$zeilen) { store_delete(UMSATZDATEN . '/' . $m); unset($index['monate'][$m]); continue; }
            $hash = umsatzdaten_hash($zeilen);
            store_write(UMSATZDATEN . '/' . $m, ['monat' => $m, 'hash' => $hash, 'zeilen' => $zeilen]);
            $index['monate'][$m] = ['hash' => $hash] + umsatzdaten_summen($zeilen);
        }
        ksort($index['monate'], SORT_STRING);
        // Kunden und Artikel aller gespeicherten Monate (Auswahllisten der Auswertung)
        $k = []; $a = [];
        foreach (array_keys($index['monate']) as $m) foreach (umsatzdaten_monat($m) as $z) { $k[$z[1]] = true; $a[$z[2]] = true; }
        $index['kunden'] = array_map('strval', array_keys($k)); sort($index['kunden'], SORT_NATURAL);
        $index['artikel'] = array_map('strval', array_keys($a)); sort($index['artikel'], SORT_NATURAL);
        $z = $vorschau['zahlen'];
        array_unshift($index['importe'], ['t' => now(), 'von' => $me['id'], 'vonName' => $me['name'], 'quelle' => (string)($e['quelle'] ?? ''),
            'zeitraum' => [$in['von'], $in['bis']], 'neu' => $z['neu'], 'geaendert' => $z['geaendert'], 'entfallen' => $z['entfaellt'], 'unveraendert' => $z['unveraendert']]);
        $index['importe'] = array_slice($index['importe'], 0, UMSATZDATEN_IMPORTE_MAX);
        $index['rev']++;
        $index['geaendert'] = ['t' => now(), 'von' => $me['id'], 'vonName' => $me['name']];
        store_write(UMSATZDATEN, $index);
        umsatzdaten_teile_aufraeumen($upload);
        return $vorschau;
    });
    $z = $erg['zahlen'];
    audit('controlling', 'Umsatzdaten' . (($e['quelle'] ?? '') !== '' ? ' aus „' . s($e['quelle'], 120) . '“' : '') . ' übernommen: Zeitraum ' . umsatzdaten_tag($in['von']) . ' – ' . umsatzdaten_tag($in['bis'])
        . ", Monate {$z['neu']} neu, {$z['geaendert']} geändert, {$z['entfaellt']} entfallen, {$z['unveraendert']} unverändert");   // ohne Beträge
    return $erg;
}

/* Stand der Umsatzdaten für die Oberfläche (ohne Beträge): Monate, erster und letzter Tag, letzte Importe */
function umsatzdaten_stand(array $index): array
{
    $monate = array_keys($index['monate']);
    $erster = $monate ? $monate[0] . '-' . sprintf('%02d', (int)($index['monate'][$monate[0]]['ersterTag'] ?? 1)) : null;
    $letzter = $monate ? end($monate) . '-' . sprintf('%02d', (int)($index['monate'][end($monate)]['letzterTag'] ?? 1)) : null;
    $importe = array_map(fn($i) => ['t' => $i['t'] ?? null, 'vonName' => $i['vonName'] ?? '', 'quelle' => $i['quelle'] ?? '', 'zeitraum' => $i['zeitraum'] ?? null,
        'neu' => (int)($i['neu'] ?? 0), 'geaendert' => (int)($i['geaendert'] ?? 0), 'entfallen' => (int)($i['entfallen'] ?? 0)], array_slice($index['importe'], 0, 10));
    return ['rev' => $index['rev'], 'monate' => $monate, 'von' => $erster, 'bis' => $letzter, 'importe' => $importe];
}

/* ---------- Schnittstelle für andere Module (GR-101; Leser „crm“ in regeln/datenverantwortung.toml) ----------
   Nur Mengen, Liefertage und letzter Kauf – nie Beträge oder Einkaufswerte. Zuordnung über Kunden- und Artikelnummern. */

/* Käufer von Artikeln vom Tag $von bis $bis (JJJJ-MM-TT): je Artikel und Kunde Menge (Tausendstel, berechnete Positionen
   einschließlich Gutschriften), Käufe (Liefertage mit Menge > 0) und letzter Kauf; dazu der letzte Tag mit Umsatzdaten. */
function umsatzdaten_kaeufer(array $artikel, string $von, string $bis): array
{
    $soll = [];   // Artikelnummer (wie code_key: ohne führende Nullen) => angefragte Schreibweise
    foreach ($artikel as $a) $soll[code_key((string)$a)] = (string)$a;
    $index = umsatzdaten_index();
    $je = []; $ck = [];
    if ($soll && umsatzdaten_datum($von) === $von && umsatzdaten_datum($bis) === $bis && $von <= $bis) {
        foreach (umsatzdaten_monatsfolge(substr($von, 0, 7), substr($bis, 0, 7)) as $m) {
            if (!isset($index['monate'][$m])) continue;
            foreach (umsatzdaten_monat($m) as $z) {
                if ($z[9] !== 1) continue;
                $a = $ck[$z[2]] ??= code_key((string)$z[2]);
                if (!isset($soll[$a])) continue;
                $tag = $m . '-' . str_pad((string)$z[0], 2, '0', STR_PAD_LEFT);
                if ($tag < $von || $tag > $bis) continue;
                $k = $je[$a][$z[1]] ?? ['menge' => 0, 'kaeufe' => 0, 'zuletzt' => null];
                $k['menge'] += $z[4];
                if ($z[4] > 0) { $k['kaeufe']++; if ($k['zuletzt'] === null || $tag > $k['zuletzt']) $k['zuletzt'] = $tag; }
                $je[$a][$z[1]] = $k;
            }
        }
    }
    $out = [];
    foreach ($soll as $a => $wie) {
        $l = [];
        foreach ($je[$a] ?? [] as $kunde => $w) if ($w['kaeufe'] > 0) $l[] = ['kunde' => (string)$kunde] + $w;
        $out[$wie] = $l;
    }
    return ['stand' => umsatzdaten_stand($index)['bis'], 'artikel' => $out];
}

/* Artikel in den Umsatzdaten mit Namen aus den Artikelstammdaten (Nummer => Name; ohne Stammsatz „Artikel <Nr>“) */
function umsatzdaten_artikelliste(): array
{
    $out = [];
    foreach (umsatzdaten_index()['artikel'] as $nr) {
        $x = umsatz_artikel((string)$nr);
        $out[(string)$nr] = $x && $x['name'] !== '' ? $x['name'] : 'Artikel ' . $nr;
    }
    return $out;
}
