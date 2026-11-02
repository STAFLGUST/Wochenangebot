<?php
declare(strict_types=1);
/* Controlling · Bereich Arbeitszeit (Auftrag des Inhabers 02.11.2026): Auswertung des Zeitberichts der Zeiterfassung
   (.xlsx-Export „Zeitbericht“, Importart „zeitbericht“ der Importzentrale, Leser app/module/controlling/arbeitszeit-import.js).

   Datei: eine Zeile je Mitarbeiter und Tag mit Vorname, Nachname, Datum, Hinein, Hinaus, Geplant, Gearbeitete Stunden,
   Abwesenheit, Pause, Saldo, Mitarbeiternummer, Department; weitere Stempel desselben Tages stehen in Folgezeilen ohne Namen
   und Datum. Gespeichert werden je Tag nur Soll, Ist, Abwesenheit (Stunden, ohne Grund wie Urlaub oder Krankheit),
   Pause, Saldo laut Zeiterfassung und die Stempel (Kommen/Gehen) – Personaldaten, Recht controlling.arbeitszeit_sehen.

   Stempelfehler werden nie geschätzt oder korrigiert, sondern erkannt, markiert und aus dem bereinigten Saldo herausgenommen:
   - „kommen“: Gehen ohne Kommen · „gehen“: Kommen ohne Gehen · „null“: Kommen = Gehen (Dauer 0)
   - „lang“: Ist oder ein einzelnes Kommen–Gehen länger als AZ_LANG (vergessenes Gehen, am Folgetag gestempelt)
   - „ohne“: Soll > 0, kein Stempel und keine Abwesenheit
   - „saldo“: Saldo der Zeiterfassung passt nicht zu Ist + Abwesenheit − Soll
   Der Tag des Imports und spätere Tage gelten als „laufend“ (noch nicht abgeschlossen): nicht gewertet, kein Fehler.
   Kennzahlen gibt es zweimal: „laut Zeiterfassung“ (alle Tage) und „bereinigt“ (nur Tage ohne Stempelfehler).

   Dokumente: ARBEITSZEIT (Verzeichnis: Mitarbeiter, Jahre, Importverlauf, Revision) und ARBEITSZEIT/JJJJ (Tage des Jahres).
   Ein Import ersetzt den Zeitraum seiner Datei (erster bis letzter Tag); Tage davor und danach bleiben. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const ARBEITSZEIT = 'controlling-arbeitszeit';
const AZ_LANG = 12 * 60;               // Minuten: länger gilt als Stempelfehler (Arbeitszeitgesetz: höchstens 10 Stunden)
const AZ_ZEILEN_MAX = 60000;           // Zeilen der Datei
const AZ_SPALTEN_MAX = 40;
const AZ_IMPORTE_MAX = 30;             // Einträge im Importverlauf
const AZ_FEHLERLISTE_MAX = 2000;       // Stempelfehler in einer Antwort
const AZ_FEHLER = ['kommen' => 'Kommen fehlt', 'gehen' => 'Gehen fehlt', 'null' => 'Kommen = Gehen', 'lang' => 'unplausibel lang',
                   'ohne' => 'kein Stempel, keine Abwesenheit', 'saldo' => 'Saldo passt nicht'];
/* Spalten des Zeitberichts (Überschrift klein geschrieben → Feld); Pflicht: AZ_PFLICHT */
const AZ_SPALTEN = ['vorname' => 'vorname', 'nachname' => 'nachname', 'datum' => 'datum', 'hinein' => 'kommen', 'hinaus' => 'gehen',
                    'geplant' => 'soll', 'gearbeitete stunden' => 'ist', 'abwesenheit' => 'abw', 'pause' => 'pause', 'saldo' => 'saldo',
                    'mitarbeiternummer' => 'nr', 'department' => 'abt', 'abteilung' => 'abt'];
const AZ_PFLICHT = ['vorname', 'nachname', 'datum', 'kommen', 'gehen', 'soll', 'ist', 'saldo'];

/* ---------- Werte lesen ---------- */

/* „HH:MM“ bzw. „-HH:MM“ (auch über 24 Stunden) oder Excel-Bruchteil eines Tages → Minuten; leer → null; ungültig → false */
function az_minuten($v)
{
    if ($v === null || $v === '') return null;
    if (is_int($v) || is_float($v)) return is_finite((float)$v) && abs((float)$v) < 10 ? (int)round((float)$v * 1440) : false;
    if (!is_string($v)) return false;
    $v = trim($v);
    if ($v === '') return null;
    if (preg_match('/^(-?)(\d{1,3}):([0-5]\d)(?::[0-5]\d)?$/', $v, $m) !== 1) return false;
    $n = (int)$m[2] * 60 + (int)$m[3];
    return $m[1] === '-' ? -$n : $n;
}
/* Uhrzeit eines Stempels „HH:MM“ (00:00–23:59) bzw. Excel-Bruchteil → „HH:MM“; leer → null; ungültig → false */
function az_uhrzeit($v)
{
    $n = az_minuten($v);
    if ($n === null || $n === false) return $n;
    if ($n < 0 || $n >= 1440) return false;
    return sprintf('%02d:%02d', intdiv($n, 60), $n % 60);
}
/* Datum „TT-MM-JJJJ“, „TT.MM.JJJJ“, „JJJJ-MM-TT“ oder Excel-Seriennummer → „JJJJ-MM-TT“; ungültig → null */
function az_datum($v): ?string
{
    if (is_int($v) || is_float($v)) {
        $n = (int)floor((float)$v);
        if ($n < 36526 || $n > 73051) return null;   // 2000–2099
        return gmdate('Y-m-d', ($n - 25569) * 86400);
    }
    if (!is_string($v)) return null;
    $v = trim($v);
    if (preg_match('/^(\d{1,2})[-.\/](\d{1,2})[-.\/](\d{4})$/', $v, $m) === 1) [$t, $mo, $j] = [(int)$m[1], (int)$m[2], (int)$m[3]];
    elseif (preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $m) === 1) [$j, $mo, $t] = [(int)$m[1], (int)$m[2], (int)$m[3]];
    else return null;
    if ($j < 2000 || $j > 2099 || !checkdate($mo, $t, $j)) return null;
    return sprintf('%04d-%02d-%02d', $j, $mo, $t);
}
function az_text($v, int $max): string
{
    if (!is_string($v) && !is_int($v) && !is_float($v)) return '';
    return s(is_string($v) ? $v : (string)$v, $max) ?? '';
}
/* Schlüssel eines Mitarbeiters: Personalnummer, sonst Name (klein) – als kurze, unveränderliche Kennung */
function az_person_id(string $nr, string $name): string
{
    $quelle = $nr !== '' ? 'n:' . $nr : 'm:' . mb_strtolower(preg_replace('/\s+/u', ' ', trim($name)) ?? '', 'UTF-8');
    return 'p' . substr(hash('sha256', $quelle), 0, 12);
}

/* Stempelfehler eines Tages (ohne „laufend“) */
function az_fehler(array $t): array
{
    $f = [];
    $hatStempel = false;
    foreach ($t['stempel'] as [$k, $g]) {
        if ($k !== null || $g !== null) $hatStempel = true;
        if ($k === null && $g !== null) $f['kommen'] = true;
        elseif ($k !== null && $g === null) $f['gehen'] = true;
        elseif ($k !== null && $k === $g) $f['null'] = true;
        elseif ($k !== null) {
            $a = (int)substr($k, 0, 2) * 60 + (int)substr($k, 3, 2);
            $b = (int)substr($g, 0, 2) * 60 + (int)substr($g, 3, 2);
            if (($b < $a ? $b + 1440 - $a : $b - $a) > AZ_LANG) $f['lang'] = true;
        }
    }
    if ($t['ist'] > AZ_LANG) $f['lang'] = true;
    if (!$hatStempel && $t['soll'] > 0 && $t['abw'] === 0 && $t['ist'] === 0) $f['ohne'] = true;
    if (abs($t['ist'] + $t['abw'] - $t['soll'] - $t['saldo']) > 1) $f['saldo'] = true;
    return array_values(array_filter(array_keys(AZ_FEHLER), fn($k) => isset($f[$k])));
}

/* ---------- Zeitbericht lesen (Importzentrale: daten = { blaetter: [{ name, grid }] }) ---------- */

/* Ergebnis: tage (Schlüssel „pid|JJJJ-MM-TT“ → Tag), personen (pid → name, nr, abt), von, bis, fehler (Zeilen), zeilen (gelesen) */
function az_zeitbericht(array $e): array
{
    $grid = $e['blaetter'][0]['grid'] ?? null;
    if (!is_array($grid) || !$grid) throw new InvalidArgumentException('Die Datei enthält keine Zeilen.');
    if (count($grid) > AZ_ZEILEN_MAX) throw new InvalidArgumentException('Die Datei hat mehr als ' . number_format(AZ_ZEILEN_MAX, 0, ',', '.') . ' Zeilen – bitte einen kürzeren Zeitraum exportieren.');
    /* Überschrift: erste Zeile (unter den ersten 10) mit allen Pflichtspalten */
    $spalte = null; $kopf = -1;
    foreach (array_slice($grid, 0, 10, true) as $i => $z) {
        if (!is_array($z)) continue;
        $map = [];
        foreach (array_slice($z, 0, AZ_SPALTEN_MAX, true) as $j => $v) {
            $n = mb_strtolower(trim(az_text($v, 60)), 'UTF-8');
            if (isset(AZ_SPALTEN[$n]) && !isset($map[AZ_SPALTEN[$n]])) $map[AZ_SPALTEN[$n]] = (int)$j;
        }
        if (!array_diff(AZ_PFLICHT, array_keys($map))) { $spalte = $map; $kopf = (int)$i; break; }
    }
    if ($spalte === null) throw new InvalidArgumentException('Das ist kein Zeitbericht der Zeiterfassung: Es fehlen Spalten (nötig: Vorname, Nachname, Datum, Hinein, Hinaus, Geplant, Gearbeitete Stunden, Saldo).');
    $wert = fn(array $z, string $f) => isset($spalte[$f]) ? ($z[$spalte[$f]] ?? null) : null;

    $tage = []; $personen = []; $fehler = []; $akt = null; $zeilen = 0;
    $fehlerZeile = function (int $zeile, string $text, string $schluessel = '') use (&$fehler) {
        $fehler[] = ['zeile' => $zeile, 'schluessel' => $schluessel, 'text' => $text];
    };
    foreach ($grid as $i => $z) {
        if ($i <= $kopf || !is_array($z)) continue;
        $nrZeile = (int)$i + 1;
        $leer = true;
        foreach (array_slice($z, 0, AZ_SPALTEN_MAX) as $v) if ($v !== null && $v !== '') { $leer = false; break; }
        if ($leer) continue;
        $zeilen++;
        $vor = az_text($wert($z, 'vorname'), 60); $nach = az_text($wert($z, 'nachname'), 60); $dRoh = $wert($z, 'datum');
        $k = az_uhrzeit($wert($z, 'kommen')); $g = az_uhrzeit($wert($z, 'gehen'));
        if ($k === false || $g === false) { $fehlerZeile($nrZeile, 'Uhrzeit von Hinein oder Hinaus nicht lesbar.'); continue; }
        if ($vor === '' && $nach === '' && ($dRoh === null || $dRoh === '')) {
            /* Folgezeile: weiterer Stempel des vorigen Tages */
            if ($akt === null) { $fehlerZeile($nrZeile, 'Stempel ohne Mitarbeiter und Tag (vor der ersten Tageszeile).'); continue; }
            if ($k !== null || $g !== null) $tage[$akt]['stempel'][] = [$k, $g];
            continue;
        }
        $akt = null;
        $d = az_datum($dRoh);
        $name = trim($vor . ' ' . $nach);
        if ($name === '') { $fehlerZeile($nrZeile, 'Zeile ohne Namen.'); continue; }
        if ($d === null) { $fehlerZeile($nrZeile, 'Datum nicht lesbar.', $name); continue; }
        $w = [];
        foreach (['soll', 'ist', 'abw', 'pause', 'saldo'] as $f) {
            $m = az_minuten($wert($z, $f));
            if ($m === false || ($m !== null && abs($m) > 48 * 60)) { $fehlerZeile($nrZeile, 'Stunden nicht lesbar (' . $f . ').', $name); continue 2; }
            $w[$f] = $m ?? 0;
        }
        if ($w['soll'] < 0 || $w['ist'] < 0 || $w['abw'] < 0 || $w['pause'] < 0) { $fehlerZeile($nrZeile, 'Negative Stunden bei Geplant, Gearbeitet, Abwesenheit oder Pause.', $name); continue; }
        $nr = az_text($wert($z, 'nr'), 20);
        if ($nr !== '' && preg_match('/^[0-9A-Za-z._-]{1,20}$/', $nr) !== 1) { $fehlerZeile($nrZeile, 'Mitarbeiternummer ungültig.', $name); continue; }
        $pid = az_person_id($nr, $name);
        $key = $pid . '|' . $d;
        if (isset($tage[$key])) { $fehlerZeile($nrZeile, 'Tag steht doppelt in der Datei.', $name . ' ' . az_tag($d)); continue; }
        $abt = az_text($wert($z, 'abt'), 40);
        $p = $personen[$pid] ?? ['name' => $name, 'nr' => $nr, 'abt' => '', 'abtTag' => ''];
        if ($abt !== '' && $d >= $p['abtTag']) { $p['abt'] = $abt; $p['abtTag'] = $d; }   // Abteilung des jüngsten Tages mit Angabe
        $personen[$pid] = $p;
        $tage[$key] = $w + ['stempel' => ($k !== null || $g !== null) ? [[$k, $g]] : []];
        $akt = $key;
    }
    if (!$tage) throw new InvalidArgumentException('Die Datei enthält keine lesbaren Tage.');
    ksort($tage);
    $daten = array_map(fn($k) => substr($k, -10), array_keys($tage));
    $von = min($daten); $bis = max($daten);
    $heute = date('Y-m-d');   // heute und später: Tag noch nicht abgeschlossen (laufend)
    foreach ($tage as $key => &$t) $t = az_tag_speichern($t, substr($key, -10) >= $heute);
    unset($t);
    foreach ($personen as &$p) unset($p['abtTag']);
    unset($p);
    return ['tage' => $tage, 'personen' => $personen, 'von' => $von, 'bis' => $bis, 'fehler' => $fehler, 'zeilen' => $zeilen];
}
/* Gespeicherte Form eines Tages: [Soll, Ist, Abwesenheit, Pause, Saldo, Stempel, Fehler, laufend] (Minuten) */
function az_tag_speichern(array $t, bool $laufend): array
{
    return [$t['soll'], $t['ist'], $t['abw'], $t['pause'], $t['saldo'], $t['stempel'], $laufend ? [] : az_fehler($t), $laufend ? 1 : 0];
}

/* ---------- Speicher ---------- */

function az_index(): array
{
    $d = store_read(ARBEITSZEIT);
    return is_array($d) ? $d + ['rev' => 0, 'personen' => [], 'jahre' => [], 'importe' => []] : ['rev' => 0, 'personen' => [], 'jahre' => [], 'importe' => []];
}
function az_jahr_lesen(string $jahr): array
{
    if (preg_match('/^\d{4}$/', $jahr) !== 1) return [];
    $d = store_read(ARBEITSZEIT . '/' . $jahr);
    return is_array($d['tage'] ?? null) ? $d['tage'] : [];
}
function az_tag(string $d): string { return substr($d, 8, 2) . '.' . substr($d, 5, 2) . '.' . substr($d, 0, 4); }
function az_anzahl(int $n): string { return number_format($n, 0, ',', '.'); }
function az_stunden(int $min): string { return ($min < 0 ? '−' : '') . sprintf('%d:%02d', intdiv(abs($min), 60), abs($min) % 60) . ' Std.'; }

/* Vergleich Datei ↔ gespeichert im Zeitraum der Datei: je Tag neu/geaendert/unveraendert, gespeicherte Tage ohne Gegenstück entfallen */
function az_vergleich(array $in): array
{
    $alt = [];
    for ($j = (int)substr($in['von'], 0, 4); $j <= (int)substr($in['bis'], 0, 4); $j++) {
        foreach (az_jahr_lesen((string)$j) as $k => $t) {
            $d = substr($k, -10);
            if ($d >= $in['von'] && $d <= $in['bis']) $alt[$k] = $t;
        }
    }
    $v = ['neu' => [], 'geaendert' => [], 'unveraendert' => [], 'entfaellt' => []];
    foreach ($in['tage'] as $k => $t) {
        if (!isset($alt[$k])) $v['neu'][] = $k;
        elseif ($alt[$k] !== $t) $v['geaendert'][] = $k;
        else $v['unveraendert'][] = $k;
    }
    foreach ($alt as $k => $_) if (!isset($in['tage'][$k])) $v['entfaellt'][] = $k;
    return $v;
}

/* ---------- Importzentrale ---------- */

function arbeitszeit_import_vorschau(array $e, array $me): array
{
    $in = az_zeitbericht($e);
    $index = az_index();
    $v = az_vergleich($in);
    $personen = $in['personen'] + $index['personen'];
    $n = ['neu' => count($v['neu']), 'geaendert' => count($v['geaendert']), 'entfaellt' => count($v['entfaellt']), 'unveraendert' => count($v['unveraendert']), 'fehler' => count($in['fehler'])];
    $zeilen = [];
    foreach ($in['fehler'] as $f) $zeilen[] = ['art' => 'fehler', 'zeile' => $f['zeile'], 'schluessel' => $f['schluessel'], 'name' => $f['schluessel'], 'text' => $f['text']];
    foreach (['geaendert', 'entfaellt', 'neu'] as $art) {
        foreach ($v[$art] as $k) {
            if (count($zeilen) >= 500) break 2;
            [$pid, $d] = explode('|', $k);
            $zeilen[] = ['art' => $art, 'schluessel' => $d, 'name' => ($personen[$pid]['name'] ?? '?') . ' · ' . az_tag($d),
                         'text' => $art === 'entfaellt' ? 'nicht mehr in der Datei – gespeicherter Tag wird gelöscht' : ($art === 'neu' ? 'neuer Tag' : 'Werte oder Stempel geändert')];
        }
    }
    $fehlerTage = 0; $codes = [];
    foreach ($in['tage'] as $t) if ($t[6]) { $fehlerTage++; foreach ($t[6] as $c) $codes[$c] = ($codes[$c] ?? 0) + 1; }
    $h = [];
    $h[] = ['stufe' => 'info', 'text' => 'Zeitraum der Datei: ' . az_tag($in['von']) . ' – ' . az_tag($in['bis']) . ', ' . az_anzahl(count($in['personen'])) . ' Mitarbeiter, '
        . az_anzahl(count($in['tage'])) . ' Tage. Gespeicherte Tage dieses Zeitraums werden ersetzt, Tage davor und danach bleiben.'];
    if ($fehlerTage) {
        arsort($codes);
        $h[] = ['stufe' => 'warn', 'text' => az_anzahl($fehlerTage) . ' Tage mit Stempelfehlern (' . implode(', ', array_map(fn($c) => AZ_FEHLER[$c] . ' ' . az_anzahl($codes[$c]), array_keys($codes)))
            . '). Sie werden übernommen, in der Auswertung markiert und nicht in den bereinigten Saldo gerechnet – nichts wird geschätzt.'];
    }
    $laufend = count(array_filter($in['tage'], fn($t) => $t[7] === 1));
    $h[] = ['stufe' => 'info', 'text' => ($laufend === 1 ? '1 Tag ab heute gilt als noch nicht abgeschlossen und wird erst mit dem nächsten Import gewertet. '
            : ($laufend ? az_anzahl($laufend) . ' Tage ab heute gelten als noch nicht abgeschlossen und werden erst mit dem nächsten Import gewertet. ' : ''))
        . 'Gründe von Abwesenheiten (z. B. Urlaub, Krankheit) werden nicht gespeichert, nur die Stunden.'];
    $ohneNr = count(array_filter($in['personen'], fn($p) => $p['nr'] === ''));
    if ($ohneNr) $h[] = ['stufe' => 'info', 'text' => az_anzahl($ohneNr) . ' Mitarbeiter ohne Mitarbeiternummer – sie werden über den Namen zugeordnet. Ändert sich der Name, entsteht ein neuer Eintrag.'];
    if ($n['entfaellt']) $h[] = ['stufe' => 'warn', 'text' => az_anzahl($n['entfaellt']) . ' gespeicherte Tage im Zeitraum stehen nicht mehr in der Datei und werden gelöscht.'];
    if ($in['fehler']) $h[] = ['stufe' => 'warn', 'text' => az_anzahl(count($in['fehler'])) . ' Zeilen sind nicht lesbar und werden übersprungen.'];
    usort($h, fn($a, $b) => ($a['stufe'] === 'warn' ? 0 : 1) <=> ($b['stufe'] === 'warn' ? 0 : 1));
    return ['zahlen' => $n, 'zeilen' => $zeilen, 'hinweise' => $h, 'stand' => $index['rev']];
}

function arbeitszeit_import_uebernehmen(array $e, array $me): array
{
    $in = az_zeitbericht($e);
    $erg = with_lock(ARBEITSZEIT, function () use ($e, $in, $me) {
        $index = az_index();
        if ((int)($e['stand'] ?? -1) !== (int)$index['rev']) fail('Die Arbeitszeitdaten wurden inzwischen geändert. Die Vorschau wird neu geladen.', 409);
        $v = az_vergleich($in);
        for ($j = (int)substr($in['von'], 0, 4); $j <= (int)substr($in['bis'], 0, 4); $j++) {
            $jahr = (string)$j;
            $tage = array_filter(az_jahr_lesen($jahr), fn($k) => substr($k, -10) < $in['von'] || substr($k, -10) > $in['bis'], ARRAY_FILTER_USE_KEY);
            foreach ($in['tage'] as $k => $t) if (substr($k, -10, 4) === $jahr) $tage[$k] = $t;
            ksort($tage);
            if ($tage) {
                store_write(ARBEITSZEIT . '/' . $jahr, ['tage' => $tage]);
                $daten = array_map(fn($k) => substr($k, -10), array_keys($tage));
                $index['jahre'][$jahr] = ['von' => min($daten), 'bis' => max($daten), 'tage' => count($tage)];
            } else {
                store_delete(ARBEITSZEIT . '/' . $jahr);
                unset($index['jahre'][$jahr]);
            }
        }
        ksort($index['jahre']);
        foreach ($in['personen'] as $pid => $p) $index['personen'][$pid] = $p;
        $zahlen = ['neu' => count($v['neu']), 'geaendert' => count($v['geaendert']), 'entfaellt' => count($v['entfaellt']), 'unveraendert' => count($v['unveraendert'])];
        array_unshift($index['importe'], ['t' => now(), 'von' => $in['von'], 'bis' => $in['bis'], 'quelle' => s($e['quelle'] ?? '', 120) ?? '', 'wer' => $me['name'] ?? $me['username'] ?? '',
                                          'personen' => count($in['personen']), 'tage' => count($in['tage'])] + $zahlen);
        $index['importe'] = array_slice($index['importe'], 0, AZ_IMPORTE_MAX);
        $index['rev'] = (int)$index['rev'] + 1;
        store_write(ARBEITSZEIT, $index);
        return ['zahlen' => $zahlen + ['fehler' => count($in['fehler'])], 'stand' => $index['rev']];
    });
    // Protokoll ohne Namen und Stunden (Personaldaten): nur Zeitraum und Anzahl
    audit('controlling', 'Zeitbericht der Zeiterfassung übernommen: ' . az_tag($in['von']) . ' – ' . az_tag($in['bis']) . ', ' . az_anzahl(count($in['personen'])) . ' Mitarbeiter, '
        . az_anzahl($erg['zahlen']['neu']) . ' Tage neu, ' . az_anzahl($erg['zahlen']['geaendert']) . ' geändert, ' . az_anzahl($erg['zahlen']['entfaellt']) . ' entfallen');
    return ['zahlen' => $erg['zahlen'], 'zeilen' => [], 'hinweise' => [], 'stand' => $erg['stand']];
}

/* ---------- Auswertung ---------- */

/* Grunddaten: Stand, Jahre, Abteilungen, Mitarbeiter (für Filter und Suche), Fehlerarten */
function az_grunddaten(array $me): array
{
    $index = az_index();
    $abt = array_values(array_unique(array_filter(array_column($index['personen'], 'abt'), fn($a) => $a !== '')));
    sort($abt, SORT_LOCALE_STRING);
    $personen = [];
    foreach ($index['personen'] as $pid => $p) $personen[] = ['id' => $pid, 'name' => $p['name'], 'nr' => $p['nr'], 'abt' => $p['abt']];
    usort($personen, fn($a, $b) => strcoll($a['name'], $b['name']));
    $jahre = $index['jahre'];
    return ['ok' => true, 'stand' => ['rev' => $index['rev'], 'jahre' => $jahre, 'von' => $jahre ? reset($jahre)['von'] : null, 'bis' => $jahre ? end($jahre)['bis'] : null,
            'importe' => array_slice($index['importe'], 0, 5)], 'abteilungen' => $abt, 'personen' => $personen, 'fehlerarten' => AZ_FEHLER,
            'grenzen' => ['lang' => AZ_LANG], 'rechte' => ['importieren' => may($me, 'controlling.arbeitszeit_importieren')]];
}

/* Anfrage: von/bis „JJJJ-MM“ (Standard: Jahr des jüngsten Tages), abt (kommagetrennt, „_“ = ohne Abteilung), p (Mitarbeiter) */
function az_anfrage(array $q, array $index): array
{
    $letzter = $index['jahre'] ? end($index['jahre'])['bis'] : date('Y-m-d');
    $monat = fn($v) => is_string($v) && preg_match('/^(\d{4})-(0[1-9]|1[0-2])$/', $v, $m) === 1 && (int)$m[1] >= 2000 && (int)$m[1] <= 2099;
    $bis = isset($q['bis']) && $q['bis'] !== '' ? $q['bis'] : substr($letzter, 0, 7);
    $von = isset($q['von']) && $q['von'] !== '' ? $q['von'] : substr($letzter, 0, 4) . '-01';
    if (!$monat($von) || !$monat($bis)) throw new InvalidArgumentException('Bitte einen Monat im Format JJJJ-MM angeben.');
    if ($von > $bis) throw new InvalidArgumentException('Der Zeitraum beginnt nach seinem Ende.');
    if (((int)substr($bis, 0, 4) - (int)substr($von, 0, 4)) * 12 + (int)substr($bis, 5) - (int)substr($von, 5) >= 36) throw new InvalidArgumentException('Höchstens 36 Monate auf einmal.');
    $liste = fn($v, $max, $muster) => array_values(array_unique(array_filter(array_map('trim', explode(',', is_string($v) ? $v : '')), fn($x) => $x !== '' && preg_match($muster, $x) === 1)));
    $abt = $liste($q['abt'] ?? '', 40, '/^.{1,40}$/u');
    $p = $liste($q['p'] ?? '', 40, '/^p[0-9a-f]{12}$/');
    return ['von' => $von, 'bis' => $bis, 'abt' => $abt, 'p' => $p];
}

/* Tage des Zeitraums mit Filter: liefert [pid, datum, tag] */
function az_tage(array $a, array $index): array
{
    $out = [];
    for ($j = (int)substr($a['von'], 0, 4); $j <= (int)substr($a['bis'], 0, 4); $j++) {
        foreach (az_jahr_lesen((string)$j) as $k => $t) {
            [$pid, $d] = explode('|', $k);
            $m = substr($d, 0, 7);
            if ($m < $a['von'] || $m > $a['bis']) continue;
            if ($a['p'] && !in_array($pid, $a['p'], true)) continue;
            if ($a['abt']) {
                $ab = $index['personen'][$pid]['abt'] ?? '';
                if (!in_array($ab === '' ? '_' : $ab, $a['abt'], true)) continue;
            }
            $out[] = [$pid, $d, $t];
        }
    }
    return $out;
}

function az_leer(): array
{
    return ['soll' => 0, 'ist' => 0, 'abw' => 0, 'saldo' => 0, 'sollOk' => 0, 'istOk' => 0, 'abwOk' => 0, 'saldoOk' => 0,
            'tage' => 0, 'tageOk' => 0, 'fehlerTage' => 0, 'saldoFehler' => 0, 'laufend' => 0, 'ohne' => 0, 'arbeitstage' => 0];
}
function az_addieren(array &$s, array $t): void
{
    [$soll, $ist, $abw, , $saldo, , $fehler, $laufend] = $t;
    if ($laufend) { $s['laufend']++; return; }
    $s['tage']++;
    $s['soll'] += $soll; $s['ist'] += $ist; $s['abw'] += $abw; $s['saldo'] += $saldo;
    if ($soll > 0) $s['arbeitstage']++;
    if ($fehler) {
        $s['fehlerTage']++; $s['saldoFehler'] += $saldo;
        if (in_array('ohne', $fehler, true)) $s['ohne']++;
        return;
    }
    $s['tageOk']++;
    $s['sollOk'] += $soll; $s['istOk'] += $ist; $s['abwOk'] += $abw; $s['saldoOk'] += $saldo;
}

/* Auswertung: Summen, Monate, je Mitarbeiter, je Abteilung, Stempelfehler (alle Werte in Minuten) */
function az_auswertung(array $q, array $me): array
{
    $index = az_index();
    $a = az_anfrage($q, $index);
    $summe = az_leer(); $monate = []; $personen = []; $abt = []; $fehler = []; $fehlerGesamt = 0;
    foreach (az_tage($a, $index) as [$pid, $d, $t]) {
        $m = substr($d, 0, 7);
        $p = $index['personen'][$pid] ?? ['name' => '?', 'nr' => '', 'abt' => ''];
        $ab = $p['abt'] !== '' ? $p['abt'] : '_';
        $monate[$m] ??= az_leer(); $personen[$pid] ??= az_leer(); $abt[$ab] ??= az_leer() + ['personen' => []];
        az_addieren($summe, $t); az_addieren($monate[$m], $t); az_addieren($personen[$pid], $t); az_addieren($abt[$ab], $t);
        $abt[$ab]['personen'][$pid] = true;
        if ($t[6] && !$t[7]) {
            $fehlerGesamt++;
            $fehler[] = ['p' => $pid, 'd' => $d, 'fehler' => $t[6], 'stempel' => $t[5], 'soll' => $t[0], 'ist' => $t[1], 'abw' => $t[2], 'saldo' => $t[4]];
        }
    }
    ksort($monate);
    $pl = [];
    foreach ($personen as $pid => $s) {
        $p = $index['personen'][$pid] ?? ['name' => '?', 'nr' => '', 'abt' => ''];
        $pl[] = ['id' => $pid, 'name' => $p['name'], 'nr' => $p['nr'], 'abt' => $p['abt']] + $s;
    }
    usort($pl, fn($x, $y) => strcoll($x['name'], $y['name']));
    $al = [];
    foreach ($abt as $id => $s) { $s['personen'] = count($s['personen']); $al[] = ['id' => $id, 'name' => $id === '_' ? 'ohne Abteilung' : $id] + $s; }
    usort($al, fn($x, $y) => ($x['id'] === '_') <=> ($y['id'] === '_') ?: strcoll($x['name'], $y['name']));
    usort($fehler, fn($x, $y) => strcmp($y['d'], $x['d']) ?: strcoll($index['personen'][$x['p']]['name'] ?? '', $index['personen'][$y['p']]['name'] ?? ''));
    $fehler = array_slice($fehler, 0, AZ_FEHLERLISTE_MAX);   // die jüngsten zuerst
    return ['ok' => true, 'zeitraum' => ['von' => $a['von'], 'bis' => $a['bis']], 'summe' => $summe,
            'monate' => array_map(fn($m, $s) => ['m' => $m] + $s, array_keys($monate), $monate),
            'personen' => $pl, 'abteilungen' => $al, 'fehler' => $fehler, 'fehlerGesamt' => $fehlerGesamt];
}

/* Pop-up: alle Tage eines Mitarbeiters im Zeitraum (?p=…&von&bis) */
function az_detail(array $q, array $me): array
{
    $index = az_index();
    $pid = is_string($q['p'] ?? null) ? $q['p'] : '';
    if (preg_match('/^p[0-9a-f]{12}$/', $pid) !== 1 || !isset($index['personen'][$pid])) throw new InvalidArgumentException('Unbekannter Mitarbeiter.');
    $a = az_anfrage(['von' => $q['von'] ?? '', 'bis' => $q['bis'] ?? ''], $index);
    $a['p'] = [$pid]; $a['abt'] = [];
    $summe = az_leer(); $tage = [];
    foreach (az_tage($a, $index) as [, $d, $t]) {
        az_addieren($summe, $t);
        $tage[] = ['d' => $d, 'soll' => $t[0], 'ist' => $t[1], 'abw' => $t[2], 'pause' => $t[3], 'saldo' => $t[4], 'stempel' => $t[5], 'fehler' => $t[6], 'laufend' => (bool)$t[7]];
    }
    usort($tage, fn($x, $y) => strcmp($y['d'], $x['d']));
    $p = $index['personen'][$pid];
    return ['ok' => true, 'person' => ['id' => $pid, 'name' => $p['name'], 'nr' => $p['nr'], 'abt' => $p['abt']], 'zeitraum' => ['von' => $a['von'], 'bis' => $a['bis']], 'summe' => $summe, 'tage' => $tage];
}
