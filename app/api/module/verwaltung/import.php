<?php
declare(strict_types=1);
/* Importvertrag der Verwaltung – Schnittstelle zur Importzentrale (docs/plattform/schnittstellen/import.md).
   Daten der Verwaltung: Kunden, Kundengruppen, VK-Gruppen, Vertreter und Artikelstammdaten.

   Die Datei liest der Leser des Eigentümers im Browser (CSV: admin-verwaltung.js, Artikelstammdaten: admin.js) und
   schickt die gelesenen Zeilen. Hier prüft der Server sie, vergleicht sie mit dem gespeicherten Stand (Vorschau) und
   übernimmt sie (Übernahme, mit Protokoll). Die bisherigen Aktionen kunden_import, kundengruppen_save/vkgruppen_save/
   vertreter_save und master_save nutzen dieselben Funktionen – es gibt je Importart genau eine Prüf- und Speicherlogik.
   Wird von api/index.php geladen; Speicherzugriffe nur auf Dokumente der Verwaltung (regeln/datenverantwortung.toml). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Registrierung für die Importzentrale (Felder: docs/plattform/schnittstellen/import.md) */
function import_arten_verwaltung(): array
{
    $csv = ['dateien' => ['csv'], 'kodierung' => 'CSV, UTF-8 oder Windows-1252, Semikolon getrennt'];
    $liste = function (string $liste, string $name, string $beschreibung, string $ansicht) use ($csv): array {
        return $csv + ['name' => $name, 'beschreibung' => $beschreibung, 'recht' => ['stammdaten.bearbeiten'], 'aktion' => $liste . '_save',
                       'ansicht' => $ansicht, 'vorschau' => 'gruppen_import_vorschau', 'uebernahme' => 'gruppen_import_uebernehmen'];
    };
    return [
        'kunden' => $csv + ['name' => 'Kunden', 'beschreibung' => 'Kundendaten-Export der Warenwirtschaft: Nummer, Name1, Adresse, Telefon, E-Mail, Kundengruppe, Vertreter.',
            'recht' => ['kunden.bearbeiten'], 'aktion' => 'kunden_import', 'bestaetigung' => 'kunden_import', 'ansicht' => 'kunden',
            'vorschau' => 'kunden_import_vorschau', 'uebernahme' => 'kunden_import_uebernehmen',
            'optionen' => [['id' => 'ohneStern', 'typ' => 'schalter', 'label' => 'Mit „*“ markierte Kunden überspringen (in der Warenwirtschaft nicht mehr aktiv)', 'standard' => true],
                           ['id' => 'anlegen', 'typ' => 'schalter', 'label' => 'Neue Kunden anlegen (aus: nur bestehende Kunden aktualisieren)', 'standard' => true]]],
        'kundengruppen' => $liste('kundengruppen', 'Kundengruppen', 'Liste der Kundengruppen aus der Warenwirtschaft: Nummer, Bezeichnung, Klasse, Kategorie.', 'gruppen'),
        'vertreter' => $liste('vertreter', 'Vertreter', 'Vertreter-Export der Warenwirtschaft: Nummer, Alpha, Name1, Land, PLZ, Ort, Telefon.', 'vertreter'),
        'stammdaten' => $csv + ['name' => 'Artikelstammdaten', 'beschreibung' => 'Artikelstammdaten-Export der Warenwirtschaft: Nummer, Bezeichnung1, Bezeichnung2, VGrp, GTIN. Neue Artikel werden angelegt, bestehende um VK-Gruppe und GTIN ergänzt.',
            'recht' => ['stammdaten.bearbeiten'], 'aktion' => 'master_save', 'ansicht' => 'master',
            'vorschau' => 'stammdaten_import_vorschau', 'uebernahme' => 'stammdaten_import_uebernehmen'],
        'vkgruppen' => $liste('vkgruppen', 'VK-Gruppen', 'Liste der VK-Gruppen aus der Warenwirtschaft: Nummer, Bezeichnung, Klasse, Kategorie.', 'vkgruppen'),
    ];
}

/* Zeilennummer aus dem Leser (Zeile in der Datei, Kopfzeile = 1) – nur zur Anzeige */
function import_zeilennr($r): ?int
{
    return is_array($r) && is_int($r['zeile'] ?? null) && $r['zeile'] > 0 && $r['zeile'] < 10000000 ? $r['zeile'] : null;
}

/* ---------------- Kunden ---------------- */

/* Kundenstammdaten aus der Warenwirtschaft (CSV im Browser gelesen): Abgleich über die Kundennummer, sonst über
   Firma + PLZ bei Kunden ohne Nummer. Übernommen werden Nummer, Firma, Adresse, Land, Telefon, E-Mail und
   Kundengruppe sowie Vertreter/Vertreter 2; bestehende Kunden behalten Firma, E-Mail, Zugang und Freischaltungen (leere Felder werden ergänzt).
   Neue Kunden: aktiv, ohne Zugang, ohne Wochenangebot per E-Mail (Einverständnis fehlt), Angebote über die Kundengruppe.
   $b: rows, anlegen, quelle, rev (nur Übernahme). $pruefen: nur Vorschau. $details: zusätzlich Ergebnis je Zeile („zeilen“).
   Die Rechte- und Bestätigungsprüfung macht der Aufrufer (Aktion kunden_import bzw. Importzentrale). */
function kunden_import_lauf(array $b, bool $pruefen, bool $details = false): array
{
    $rows = is_array($b['rows'] ?? null) ? $b['rows'] : [];
    if (!$rows) fail('Keine Kunden in der Datei gefunden.', 422);
    if (count($rows) > 10000) fail('Zu viele Zeilen (höchstens 10.000).', 422);
    $anlegen = !array_key_exists('anlegen', $b) || !empty($b['anlegen']);
    $quelle = s($b['quelle'] ?? '', 120) ?? '';
    $FELDER = ['nr', 'firma', 'strasse', 'plz', 'ort', 'land', 'telefon', 'email', 'gruppe', 'vertreter', 'vertreter2'];
    $res = with_lock('kunden', function () use ($b, $rows, $anlegen, $pruefen, $details, $FELDER) {
        $d = customers_load();
        if (!$pruefen && (int)($b['rev'] ?? -1) !== (int)$d['rev']) fail('Die Kundendaten wurden inzwischen an anderer Stelle geändert. Bitte die Vorschau neu laden.', 409);
        // Nummern wie in der Liste schreiben („7“ in der Datei passt zu „07“ in den Kundengruppen)
        $nk = function (string $nr): string { return ctype_digit($nr) ? (ltrim($nr, '0') === '' ? '0' : ltrim($nr, '0')) : strtoupper($nr); };
        $gruppen = []; foreach (kundengruppen_load()['groups'] as $g) $gruppen[$nk($g['nr'])] = $g['nr'];
        $vertreter = []; foreach (vertreter_load()['groups'] as $g) $vertreter[$nk($g['nr'])] = $g['nr'];
        $byNr = []; $byName = [];
        foreach ($d['customers'] as $i => $c) {
            if (($c['nr'] ?? '') !== '') $byNr[$c['nr']] = $i;
            else $byName[mb_strtolower(trim($c['firma'])) . '|' . ($c['plz'] ?? '')] = $i;
        }
        $st = ['neu' => 0, 'aktualisiert' => 0, 'unveraendert' => 0, 'ohneFirma' => 0, 'doppelt' => 0, 'mailUngueltig' => 0, 'nichtAngelegt' => 0];
        $fremd = []; $fremdV = []; $bspNeu = []; $bspAkt = []; $ch = []; $seen = []; $zeilen = [];
        $zeile = function (string $art, $r, array $x, string $text) use (&$zeilen, $details) {
            if ($details) $zeilen[] = ['art' => $art, 'zeile' => import_zeilennr($r), 'schluessel' => $x['nr'], 'name' => $x['firma'], 'text' => $text];
        };
        foreach ($rows as $r) {
            if (!is_array($r)) continue;
            $x = [];
            foreach ($FELDER as $f) $x[$f] = s(is_scalar($r[$f] ?? null) ? (string)$r[$f] : '', CUSTOMER_FIELDS[$f]) ?? '';
            if (mb_strlen($x['firma']) < 2) { $st['ohneFirma']++; $zeile('fehler', $r, $x, 'Firma fehlt (Spalte Name1) – übersprungen'); continue; }
            if ($x['nr'] !== '') { if (isset($seen[$x['nr']])) { $st['doppelt']++; $zeile('fehler', $r, $x, 'Kundennummer steht mehrfach in der Datei – nur die erste Zeile zählt'); continue; } $seen[$x['nr']] = true; }
            if ($x['email'] !== '' && filter_var($x['email'], FILTER_VALIDATE_EMAIL) === false) { $x['email'] = ''; $st['mailUngueltig']++; }
            if ($x['gruppe'] !== '') { if (isset($gruppen[$nk($x['gruppe'])])) $x['gruppe'] = $gruppen[$nk($x['gruppe'])]; else { $fremd[$x['gruppe']] = ($fremd[$x['gruppe']] ?? 0) + 1; $x['gruppe'] = ''; } }
            foreach (['vertreter', 'vertreter2'] as $f) if ($x[$f] !== '') { if (isset($vertreter[$nk($x[$f])])) $x[$f] = $vertreter[$nk($x[$f])]; else { $fremdV[$x[$f]] = ($fremdV[$x[$f]] ?? 0) + 1; $x[$f] = ''; } }
            $idx = $x['nr'] !== '' && isset($byNr[$x['nr']]) ? $byNr[$x['nr']] : ($byName[mb_strtolower($x['firma']) . '|' . $x['plz']] ?? null);
            if ($idx === null) {
                if (!$anlegen) { $st['nichtAngelegt']++; continue; }
                $row = ['id' => 'k' . bin2hex(random_bytes(6))];
                foreach (CUSTOMER_FIELDS as $f => $max) $row[$f] = $x[$f] ?? '';
                $row += ['angebote' => [], 'active' => true, 'mailAngebot' => false, 'login' => null, 'created' => now(), 'changed' => now()];
                $d['customers'][] = $row;
                if ($x['nr'] !== '') $byNr[$x['nr']] = count($d['customers']) - 1;
                else $byName[mb_strtolower($x['firma']) . '|' . $x['plz']] = count($d['customers']) - 1;   // gleiche Zeile ohne Nummer nicht doppelt anlegen
                $st['neu']++;
                if (count($bspNeu) < 8) $bspNeu[] = ['nr' => $x['nr'], 'firma' => $x['firma'], 'ort' => $x['ort'], 'gruppe' => $x['gruppe']];
                if (count($ch) < 2000) $ch[] = ['k' => "c{$row['id']}|+", 'code' => $x['nr'], 'name' => $x['firma'], 'f' => 'Neuer Kunde (Import)', 'from' => '', 'to' => trim($x['plz'] . ' ' . $x['ort'])];
                $zeile('neu', $r, $x, implode(' · ', array_filter([trim($x['plz'] . ' ' . $x['ort']), $x['gruppe'] !== '' ? 'Kundengruppe ' . $x['gruppe'] : ''])));
                continue;
            }
            $c = $d['customers'][$idx];
            $neu = $c; $diff = [];
            foreach (['nr', 'gruppe', 'vertreter', 'vertreter2', 'strasse', 'plz', 'ort', 'land', 'telefon'] as $f) if ($x[$f] !== '' && (string)($c[$f] ?? '') !== $x[$f]) $neu[$f] = $x[$f];   // Warenwirtschaft führt Adresse, Gruppe, Vertreter
            foreach (['firma', 'email'] as $f) if ($x[$f] !== '' && (string)($c[$f] ?? '') === '') $neu[$f] = $x[$f];                                     // nur ergänzen
            foreach (array_merge(['firma', 'email'], ['nr', 'gruppe', 'vertreter', 'vertreter2', 'strasse', 'plz', 'ort', 'land', 'telefon']) as $f) if ((string)($c[$f] ?? '') !== (string)($neu[$f] ?? '')) $diff[$f] = [(string)($c[$f] ?? ''), (string)$neu[$f]];
            if (!$diff) { $st['unveraendert']++; continue; }
            $neu['changed'] = now();
            $d['customers'][$idx] = $neu;
            $st['aktualisiert']++;
            if (count($bspAkt) < 8) $bspAkt[] = ['nr' => $neu['nr'] ?? '', 'firma' => $neu['firma'], 'felder' => array_map(function ($f) { return CUSTOMER_LABELS[$f]; }, array_keys($diff))];
            foreach ($diff as $f => [$from, $to]) if (count($ch) < 2000) $ch[] = ['k' => "c{$neu['id']}|$f", 'code' => $neu['nr'] ?? '', 'name' => $neu['firma'], 'f' => CUSTOMER_LABELS[$f], 'from' => $from, 'to' => $to];
            $zeile('geaendert', $r, ['nr' => (string)($neu['nr'] ?? ''), 'firma' => $neu['firma']],
                   implode('; ', array_map(function ($f, $v) { return CUSTOMER_LABELS[$f] . ': ' . ($v[0] === '' ? '–' : $v[0]) . ' → ' . $v[1]; }, array_keys($diff), $diff)));
        }
        if (count($d['customers']) > 20000) fail('Zu viele Kunden (höchstens 20.000).', 422);
        arsort($fremd); arsort($fremdV);
        $out = ['stat' => $st, 'gruppenUnbekannt' => (object)array_slice($fremd, 0, 20, true), 'vertreterUnbekannt' => (object)array_slice($fremdV, 0, 20, true), 'beispiele' => ['neu' => $bspNeu, 'aktualisiert' => $bspAkt]];
        if ($details) $out['zeilen'] = $zeilen;
        if (!$pruefen && ($st['neu'] || $st['aktualisiert'])) {
            usort($d['customers'], function ($x, $y) { return strcasecmp($x['firma'], $y['firma']); });
            $d['rev'] = (int)$d['rev'] + 1;
            $d['updatedAt'] = now();
            store_write('kunden', $d);
        }
        return [$out, $d['rev'], $ch];
    });
    [$out, $rev, $ch] = $res;
    if (!$pruefen && $ch) audit('customers', 'Kunden ' . ($quelle !== '' ? "aus „{$quelle}“ " : '') . "importiert: {$out['stat']['neu']} neu, {$out['stat']['aktualisiert']} aktualisiert", $ch);
    return ['rev' => $rev] + $out;
}

function kunden_import_vorschau(array $e, array $me): array { return kunden_import_zentrale($e, true); }
function kunden_import_uebernehmen(array $e, array $me): array { return kunden_import_zentrale($e, false); }
function kunden_import_zentrale(array $e, bool $pruefen): array
{
    $rows = is_array($e['rows'] ?? null) ? array_values($e['rows']) : [];
    $stern = 0;
    if (!empty($e['optionen']['ohneStern'])) {
        $rows = array_values(array_filter($rows, function ($r) use (&$stern) { if (is_array($r) && !empty($r['stern'])) { $stern++; return false; } return true; }));
        if (!$rows && $stern) fail('Alle Kunden der Datei sind mit „*“ markiert und werden übersprungen.', 422);
    }
    $r = kunden_import_lauf(['rows' => $rows, 'anlegen' => !empty($e['optionen']['anlegen']), 'quelle' => $e['quelle'] ?? '', 'rev' => $e['stand'] ?? -1], $pruefen, true);
    $s = $r['stat'];
    $h = [];
    $liste = function ($m) { $o = []; foreach ($m as $nr => $n) $o[] = "$nr ($n)"; return implode(', ', $o); };
    if ((array)$r['gruppenUnbekannt']) $h[] = ['stufe' => 'warn', 'text' => 'Kundengruppe nicht in der Liste (Stammdaten → Kundengruppen), Gruppe bleibt leer: ' . $liste($r['gruppenUnbekannt'])];
    if ((array)$r['vertreterUnbekannt']) $h[] = ['stufe' => 'warn', 'text' => 'Vertreter nicht in der Liste (Stammdaten → Vertreter), Feld bleibt leer: ' . $liste($r['vertreterUnbekannt'])];
    if ($s['mailUngueltig']) $h[] = ['stufe' => 'warn', 'text' => "{$s['mailUngueltig']}× ungültige E-Mail-Adresse – Feld bleibt leer."];
    $sternDatei = count(array_filter(is_array($e['rows'] ?? null) ? $e['rows'] : [], function ($r) { return is_array($r) && !empty($r['stern']); }));
    if ($stern) $h[] = ['stufe' => 'info', 'text' => "$stern mit „*“ markierte " . ($stern === 1 ? 'Kunde' : 'Kunden') . ' übersprungen (in der Warenwirtschaft nicht mehr aktiv).'];
    elseif ($sternDatei) $h[] = ['stufe' => 'info', 'text' => "$sternDatei mit „*“ markierte " . ($sternDatei === 1 ? 'Kunde wird' : 'Kunden werden') . ' mit übernommen (in der Warenwirtschaft nicht mehr aktiv).'];
    if ($s['nichtAngelegt']) $h[] = ['stufe' => 'info', 'text' => "{$s['nichtAngelegt']} neue Kunden nicht angelegt (nur bestehende aktualisieren)."];
    $h[] = ['stufe' => 'info', 'text' => 'Abgleich über die Kundennummer (ohne Nummer über Firma und PLZ). Bestehende Kunden: Kundengruppe, Vertreter, Adresse, Land und Telefon aus der Datei; Firma und E-Mail nur, wenn sie noch leer sind. Zugang, Freischaltungen und Notizen bleiben. Kunden, die nicht in der Datei stehen, bleiben unverändert. Neue Kunden bekommen keinen Zugang und kein Wochenangebot per E-Mail.'];
    return ['zahlen' => ['neu' => $s['neu'], 'geaendert' => $s['aktualisiert'], 'entfaellt' => 0, 'unveraendert' => $s['unveraendert'], 'fehler' => $s['ohneFirma'] + $s['doppelt']],
            'zeilen' => $r['zeilen'], 'hinweise' => $h, 'stand' => $r['rev']];
}

/* ---------------- Listen der Stammdaten: Kundengruppen, VK-Gruppen, Vertreter ---------------- */

/* Anzahl zugeordneter Kunden (Kundengruppen, Vertreter) bzw. Artikel (VK-Gruppen) je Nummer */
function gruppen_zuordnungen(string $liste): array
{
    $n = [];
    if ($liste === 'vkgruppen') {
        foreach ((store_read('stammdaten')['articles'] ?? []) as $a) if (($a['vkGruppe'] ?? '') !== '') $n[$a['vkGruppe']] = ($n[$a['vkGruppe']] ?? 0) + 1;
        return $n;
    }
    foreach (customers_load()['customers'] as $c) {
        $nrs = $liste === 'vertreter' ? array_unique(array_filter([(string)($c['vertreter'] ?? ''), (string)($c['vertreter2'] ?? '')], 'strlen')) : array_filter([(string)($c['gruppe'] ?? '')], 'strlen');
        foreach ($nrs as $x) $n[$x] = ($n[$x] ?? 0) + 1;
    }
    return $n;
}

/* Ganze Liste speichern (Revision, Protokoll) – Aktionen kundengruppen_save/vkgruppen_save/vertreter_save und Importzentrale */
function gruppen_speichern(string $liste, $groups, int $rev, array $me, string $quelle = ''): array
{
    $L = GRUPPEN_LISTEN[$liste];
    $groups = gruppen_clean($liste, $groups);
    $res = with_lock($liste, function () use ($rev, $groups, $me, $liste, $L) {
        $cur = gruppen_load($liste);
        if ($rev !== $cur['rev']) fail("Die {$L['viele']} wurden inzwischen an anderer Stelle geändert. Bitte neu laden.", 409);
        $alt = []; foreach ($cur['groups'] as $g) $alt[$g['nr']] = $g;
        $neu = 0; $geaendert = 0;
        foreach ($groups as $g) { if (!isset($alt[$g['nr']])) $neu++; elseif ($alt[$g['nr']] != $g) $geaendert++; unset($alt[$g['nr']]); }
        $d = ['rev' => $cur['rev'] + 1, 'groups' => $groups, 'updatedAt' => now(), 'updatedBy' => $me['name']];
        store_write($liste, $d);
        return [$d, $neu, $geaendert, count($alt)];
    });
    [$d, $neu, $geaendert, $weg] = $res;
    if ($neu || $geaendert || $weg) audit('master', $L['viele'] . ' ' . ($quelle !== '' ? "aus „{$quelle}“ übernommen" : 'gespeichert') . ": $neu neu, $geaendert geändert, $weg entfernt (" . count($groups) . ' insgesamt)');
    return ['rev' => $d['rev'], 'groups' => $d['groups'], 'neu' => $neu, 'geaendert' => $geaendert, 'entfernt' => $weg];
}

/* Liste der Importart (Registrierung: kundengruppen, vkgruppen, vertreter) */
function gruppen_import_liste(array $e): string
{
    $l = (string)($e['art'] ?? '');
    if (!isset(GRUPPEN_LISTEN[$l])) throw new InvalidArgumentException('Unbekannte Liste.');
    return $l;
}

/* Vorschau: neu / geändert / entfällt gegenüber der gespeicherten Liste (gespeichert wird immer die ganze Liste) */
function gruppen_import_vorschau(array $e, array $me): array
{
    $liste = gruppen_import_liste($e);
    $L = GRUPPEN_LISTEN[$liste];
    $roh = is_array($e['groups'] ?? null) ? $e['groups'] : [];
    if (!$roh) fail("Keine {$L['viele']} in der Datei gefunden.", 422);
    $zeileVon = [];
    foreach ($roh as $g) if (is_array($g) && is_scalar($g['nr'] ?? null)) $zeileVon[(string)$g['nr']] = import_zeilennr($g);
    $groups = gruppen_clean($liste, $roh);
    $cur = gruppen_load($liste);
    $alt = []; foreach ($cur['groups'] as $g) $alt[$g['nr']] = $g;
    $LABEL = ['name' => $liste === 'vertreter' ? 'Name' : 'Bezeichnung', 'kurz' => 'Kurzname', 'klasse' => 'Klasse', 'kategorie' => 'Kategorie',
              'telefon' => 'Telefon', 'plz' => 'PLZ', 'ort' => 'Ort', 'land' => 'Land'];
    $z = []; $n = ['neu' => 0, 'geaendert' => 0, 'entfaellt' => 0, 'unveraendert' => 0, 'fehler' => 0];
    foreach ($groups as $g) {
        $nr = $g['nr'];
        if (!isset($alt[$nr])) { $n['neu']++; $z[] = ['art' => 'neu', 'zeile' => $zeileVon[$nr] ?? null, 'schluessel' => $nr, 'name' => $g['name'], 'text' => '']; continue; }
        $a = $alt[$nr]; unset($alt[$nr]);
        $diff = [];
        foreach (array_keys($L['felder']) as $f) {
            $va = (string)($a[$f] ?? ''); $vg = (string)($g[$f] ?? '');
            if ($va !== $vg) $diff[] = ($LABEL[$f] ?? $f) . ': ' . ($va === '' ? '–' : $va) . ' → ' . ($vg === '' ? '–' : $vg);
        }
        if (!$diff) { $n['unveraendert']++; continue; }
        $n['geaendert']++;
        $z[] = ['art' => 'geaendert', 'zeile' => $zeileVon[$nr] ?? null, 'schluessel' => $nr, 'name' => $g['name'], 'text' => implode('; ', $diff)];
    }
    $h = [];
    $zahl = $alt ? gruppen_zuordnungen($liste) : [];
    $zaehlt = $liste === 'vkgruppen' || may($me, 'kunden.sehen');   // Kundenzahlen nur für Nutzer mit Kundenrecht
    $mit = 0;
    foreach ($alt as $nr => $a) {
        $n['entfaellt']++;
        $k = $zahl[$nr] ?? 0;
        if ($k) $mit++;
        $z[] = ['art' => 'entfaellt', 'zeile' => null, 'schluessel' => (string)$nr, 'name' => $a['name'], 'text' => 'nicht mehr in der Datei – wird entfernt' . ($k && $zaehlt ? " ($k " . ($liste === 'vkgruppen' ? 'Artikel' : ($k === 1 ? 'Kunde' : 'Kunden')) . ' zugeordnet)' : '')];
    }
    if ($mit) $h[] = ['stufe' => 'warn', 'text' => "$mit entfallende " . ($mit === 1 ? 'Eintrag hat' : 'Einträge haben') . ' zugeordnete ' . ($liste === 'vkgruppen' ? 'Artikel' : 'Kunden') . '; diese behalten die Nummer, bis eine andere gewählt wird.'];
    $h[] = ['stufe' => 'info', 'text' => "Gespeichert wird die ganze Liste: {$L['viele']}, die nicht in der Datei stehen, werden entfernt."];
    return ['zahlen' => $n, 'zeilen' => $z, 'hinweise' => $h, 'stand' => $cur['rev']];
}

function gruppen_import_uebernehmen(array $e, array $me): array
{
    $liste = gruppen_import_liste($e);
    $v = gruppen_import_vorschau($e, $me);   // gleiche Prüfung wie in der Vorschau; die Revision schützt vor Zwischenänderungen
    gruppen_speichern($liste, $e['groups'], (int)($e['stand'] ?? -1), $me, (string)($e['quelle'] ?? ''));
    return $v;
}

/* ---------------- Artikelstammdaten ---------------- */

/* Ganze Stammdatenliste speichern (Revision) – Aktion master_save und Importzentrale. Liefert [Dokument, Änderungen]. */
function stammdaten_speichern($articles, int $rev, array $me): array
{
    $articles = clean_master($articles);
    return with_lock('stammdaten', function () use ($rev, $articles, $me) {
        $cur = store_read('stammdaten') ?: ['rev' => 0, 'articles' => []];
        if ($rev !== (int)$cur['rev']) fail('Die Stammdaten wurden inzwischen an anderer Stelle geändert. Bitte die Seite neu laden.', 409);
        $m = ['rev' => (int)$cur['rev'] + 1, 'updatedAt' => now(), 'updatedBy' => $me['name'], 'articles' => $articles];
        store_write('stammdaten', $m);
        return [$m, master_changes($cur['articles'], $articles)];
    });
}

/* Der Leser (admin.js) liefert die vollständige neue Liste: bestehende Artikel mit ergänzter VK-Gruppe/GTIN plus neue
   Artikel mit vorgeschlagenen Merkmalen – dieselbe Regel wie der Import unter Stammdaten → Artikelstammdaten. Hier: Prüfung
   (clean_master), Vergleich mit dem gespeicherten Stand und Revision (Grundlage des Lesers = gespeicherter Stand). */
function stammdaten_import_vorschau(array $e, array $me): array
{
    $cur = store_read('stammdaten') ?: ['rev' => 0, 'articles' => []];
    if ((int)($e['rev'] ?? -1) !== (int)$cur['rev']) fail('Die Artikelstammdaten wurden inzwischen an anderer Stelle geändert. Bitte die Datei erneut wählen.', 409);
    $neuListe = clean_master($e['articles'] ?? null);
    $zeileVon = [];
    foreach ((is_array($e['zeilen'] ?? null) ? $e['zeilen'] : []) as $code => $nr) if (is_int($nr)) $zeileVon[code_key((string)$code)] = $nr;
    $by = [];
    foreach (master_changes($cur['articles'], $neuListe) as $c) $by[code_key((string)$c['code'])][] = $c;
    $z = []; $n = ['neu' => 0, 'geaendert' => 0, 'entfaellt' => 0, 'unveraendert' => 0, 'fehler' => 0];
    foreach ($by as $k => $list) {
        $c0 = $list[0];
        $zl = $zeileVon[$k] ?? null;
        if ($c0['f'] === 'Neuer Stammsatz') { $n['neu']++; $z[] = ['art' => 'neu', 'zeile' => $zl, 'schluessel' => $c0['code'], 'name' => $c0['name'], 'text' => $c0['to']]; continue; }
        if ($c0['f'] === 'Stammsatz gelöscht') { $n['entfaellt']++; $z[] = ['art' => 'entfaellt', 'zeile' => null, 'schluessel' => $c0['code'], 'name' => $c0['name'], 'text' => 'wird entfernt']; continue; }
        $n['geaendert']++;
        $z[] = ['art' => 'geaendert', 'zeile' => $zl, 'schluessel' => $c0['code'], 'name' => $c0['name'],
                'text' => implode('; ', array_map(function ($c) { return $c['f'] . ': ' . ($c['from'] === '' ? '–' : $c['from']) . ' → ' . ($c['to'] === '' ? '–' : $c['to']); }, $list))];
    }
    $n['unveraendert'] = max(0, count(array_filter(array_keys($zeileVon), function ($k) use ($by) { return !isset($by[$k]); })));
    $h = [['stufe' => 'info', 'text' => 'Bezeichnung, Fleischart, Herkunft und Zustand bestehender Artikel bleiben unverändert; Artikel, die nicht in der Datei stehen, bleiben erhalten. EK, Bestand, Umsatz und Lieferant werden nicht übernommen.']];
    return ['zahlen' => $n, 'zeilen' => $z, 'hinweise' => $h, 'stand' => (int)$cur['rev']];
}

function stammdaten_import_uebernehmen(array $e, array $me): array
{
    $v = stammdaten_import_vorschau($e, $me);
    [$m, $d] = stammdaten_speichern($e['articles'], (int)($e['stand'] ?? -1), $me);
    $q = s($e['quelle'] ?? '', 120) ?? '';
    if ($d) audit('master', 'Artikelstammdaten ' . ($q !== '' ? "aus „{$q}“ " : '') . "importiert: {$v['zahlen']['neu']} neu, {$v['zahlen']['geaendert']} geändert", array_slice($d, 0, 2000));
    return $v;
}
