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
        'kunden' => $csv + ['name' => 'Kunden', 'beschreibung' => 'Kundendaten-Export der Warenwirtschaft: Nummer, Name1, Adresse, Telefon, E-Mail, Kundengruppe, Vertreter und alle weiteren Spalten (Umsätze, Kreditlimit, letzte Rechnung …).',
            'recht' => ['kunden.bearbeiten'], 'aktion' => 'kunden_import', 'bestaetigung' => 'kunden_import', 'ansicht' => 'kunden',
            'vorschau' => 'kunden_import_vorschau', 'uebernahme' => 'kunden_import_uebernehmen',
            'optionen' => [['id' => 'ohneStern', 'typ' => 'schalter', 'label' => 'Mit „*“ markierte Kunden überspringen (in der Warenwirtschaft nicht mehr aktiv)', 'standard' => true],
                           ['id' => 'anlegen', 'typ' => 'schalter', 'label' => 'Neue Kunden anlegen (aus: nur bestehende Kunden aktualisieren)', 'standard' => true],
                           ['id' => 'aktivRegel', 'typ' => 'schalter', 'label' => 'Kunden ohne Rechnung seit ' . KUNDEN_AKTIV_MONATE . ' Monaten auf inaktiv setzen (mit neuer Rechnung wieder aktiv)', 'standard' => true]]],
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

/* Weitere Spalten des Kundendaten-Exports der Warenwirtschaft: gespeichert am Kunden unter „wawi“ (neues, optionales
   Feld – ältere Fassungen behalten es beim Speichern, GR-006), dazu „stand“ (Zeitpunkt der letzten Änderung durch einen
   Import). Der Leser (kAusCsv) liefert Datumswerte als JJJJ-MM-TT, Beträge als Zahl in Euro, Ja/Nein als true/false.
   Feld => [Art, Länge]. Nicht eigens gespeichert: Vertreter.Alpha (Kurzname des Vertreters, steht unter Stammdaten → Vertreter).
   Ausgeliefert werden die Werte nur an Nutzer mit „Kunden bearbeiten“ (customer_public), nie an CRM, Kunden oder ins Protokoll. */
const KUNDEN_WAWI_FELDER = [
    'alpha' => ['text', 40], 'konto' => ['text', 20], 'rgEmpf' => ['text', 30], 'kondition' => ['text', 10], 'angelegtVon' => ['text', 20], 'gln' => ['ziffern', 20],
    'letzteRechnung' => ['datum', 0], 'letzterLieferschein' => ['datum', 0], 'angelegtAm' => ['datum', 0], 'angelegtUm' => ['uhrzeit', 0],
    'kreditlimit' => ['betrag', 0], 'umsatzMonat' => ['betrag', 0], 'rohgewinnMonat' => ['betrag', 0], 'umsatzVorigerMonat' => ['betrag', 0], 'rohgewinnVorigerMonat' => ['betrag', 0],
    'umsatzJahr' => ['betrag', 0], 'rohgewinnJahr' => ['betrag', 0], 'umsatzVorigesJahr' => ['betrag', 0], 'rohgewinnVorigesJahr' => ['betrag', 0],
    'umsatzVorjahr' => ['betrag', 0], 'umsatzVorvorjahr' => ['betrag', 0],
    'mailAB' => ['mails', 400], 'mailLS' => ['mails', 400], 'mailERechnung' => ['mails', 400], 'weitereEmails' => ['mails', 400],
    'abgabeCitti' => ['janein', 0], 'dfb' => ['janein', 0], 'rgSperre' => ['janein', 0],
];
/* Aktiv-Regel des Imports: ohne Rechnung, Lieferschein und Neuanlage in diesem Zeitraum wird ein Kunde inaktiv */
const KUNDEN_AKTIV_MONATE = 18;

/* Wert eines WaWi-Felds prüfen; null = leer bzw. ungültig (dann nicht gespeichert) */
function kunden_wawi_wert(array $typ, $v)
{
    [$art, $max] = $typ;
    if ($v === null || $v === '') return null;
    switch ($art) {
        case 'janein': return is_bool($v) ? $v : null;
        case 'betrag': return (is_int($v) || is_float($v)) && is_finite((float)$v) && abs((float)$v) < 1e12 ? round((float)$v, 2) : null;
        case 'datum': return is_string($v) && preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $m) && (int)$m[1] >= 1900 && (int)$m[1] <= 2100 && checkdate((int)$m[2], (int)$m[3], (int)$m[1]) ? $v : null;
        case 'uhrzeit': return is_string($v) && preg_match('/^([01]\d|2[0-3]):[0-5]\d$/', $v) ? $v : null;
        case 'ziffern': return is_string($v) && preg_match('/^\d{1,' . $max . '}$/', $v) ? $v : null;
        case 'mails':
            if (!is_string($v)) return null;
            $ok = [];
            foreach (preg_split('/[;,\s]+/', $v) ?: [] as $m) if ($m !== '' && mb_strlen($m) <= 160 && filter_var($m, FILTER_VALIDATE_EMAIL) !== false && !in_array($m, $ok, true) && mb_strlen(implode(', ', array_merge($ok, [$m]))) <= $max) $ok[] = $m;
            return $ok ? implode(', ', $ok) : null;
        default: $s = s($v, $max); return $s === null || $s === '' ? null : $s;
    }
}
/* WaWi-Daten nach einer Zeile der Datei: Felder, die die Datei enthält ($felder), werden übernommen bzw. geleert; die
   übrigen (ältere Exporte ohne die Spalte, Felder einer neueren Fassung) bleiben. Ohne „stand“. */
function kunden_wawi_neu(array $alt, $roh, array $felder): array
{
    $roh = is_array($roh) ? $roh : [];
    $neu = array_diff_key($alt, ['stand' => true]);
    foreach ($felder as $f) {
        $v = kunden_wawi_wert(KUNDEN_WAWI_FELDER[$f], $roh[$f] ?? null);
        if ($v === null) unset($neu[$f]); else $neu[$f] = $v;
    }
    return $neu;
}
/* Stichtag der Aktiv-Regel (JJJJ-MM-TT, Ortszeit): heute vor KUNDEN_AKTIV_MONATE Monaten */
function kunden_aktiv_stichtag(): string { return (new DateTimeImmutable('today'))->modify('-' . KUNDEN_AKTIV_MONATE . ' months')->format('Y-m-d'); }
/* Jüngstes Datum aus letzter Rechnung, letztem Lieferschein (Rechnung ggf. an einen Rechnungsempfänger) und Anlage; '' = keines */
function kunden_letztes_datum(array $w): string
{
    return max((string)($w['letzteRechnung'] ?? ''), (string)($w['letzterLieferschein'] ?? ''), (string)($w['angelegtAm'] ?? ''));
}
function kunden_dmy(string $iso): string { return preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $iso, $m) ? "{$m[3]}.{$m[2]}.{$m[1]}" : $iso; }

/* Kundenstammdaten aus der Warenwirtschaft (CSV im Browser gelesen): Abgleich über die Kundennummer, sonst über
   Firma + PLZ bei Kunden ohne Nummer. Übernommen werden Nummer, Firma, Adresse, Land, Telefon, E-Mail und
   Kundengruppe sowie Vertreter/Vertreter 2; bestehende Kunden behalten Firma, E-Mail, Zugang und Freischaltungen (leere Felder werden ergänzt).
   Alle weiteren Spalten landen unter „wawi“ (KUNDEN_WAWI_FELDER). Neue Kunden: ohne Zugang, ohne Wochenangebot per E-Mail
   (Einverständnis fehlt), Angebote über die Kundengruppe.
   Aktiv-Regel ($b['aktivRegel'], nur wenn die Datei die Spalte LetzteRechnung hat): Kunden ohne Rechnung, Lieferschein und
   Neuanlage in den letzten 18 Monaten (bzw. mit „*“) werden inaktiv und mit „autoInaktiv“ gekennzeichnet; kommt wieder eine
   Rechnung, werden nur so gekennzeichnete Kunden wieder aktiv – von Hand deaktivierte bleiben inaktiv, von Hand wieder
   aktivierte („aktivVonHand“, kunde_save) aktiv. Kunden, die sich in den 18 Monaten auf der Angebotsseite angemeldet haben, bleiben aktiv. Kunden, die nicht in der Datei stehen, bleiben unverändert.
   $b: rows, anlegen, aktivRegel, wawiFelder (Felder, die die Datei enthält), quelle, rev (nur Übernahme). $pruefen: nur Vorschau.
   $details: zusätzlich Ergebnis je Zeile („zeilen“). Die Rechte- und Bestätigungsprüfung macht der Aufrufer (Aktion kunden_import bzw. Importzentrale). */
function kunden_import_lauf(array $b, bool $pruefen, bool $details = false): array
{
    $rows = is_array($b['rows'] ?? null) ? $b['rows'] : [];
    if (!$rows) fail('Keine Kunden in der Datei gefunden.', 422);
    if (count($rows) > 10000) fail('Zu viele Zeilen (höchstens 10.000).', 422);
    $anlegen = !array_key_exists('anlegen', $b) || !empty($b['anlegen']);
    $quelle = s($b['quelle'] ?? '', 120) ?? '';
    $FELDER = ['nr', 'firma', 'strasse', 'plz', 'ort', 'land', 'telefon', 'email', 'gruppe', 'vertreter', 'vertreter2'];
    $wawiFelder = array_values(array_intersect(array_keys(KUNDEN_WAWI_FELDER), array_filter(is_array($b['wawiFelder'] ?? null) ? $b['wawiFelder'] : [], 'is_string')));
    $regelGewuenscht = !empty($b['aktivRegel']);
    $regel = $regelGewuenscht && in_array('letzteRechnung', $wawiFelder, true);
    $stichtag = kunden_aktiv_stichtag();
    $res = with_lock('kunden', function () use ($b, $rows, $anlegen, $pruefen, $details, $FELDER, $wawiFelder, $regel, $stichtag) {
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
        $st = ['neu' => 0, 'aktualisiert' => 0, 'unveraendert' => 0, 'ohneFirma' => 0, 'doppelt' => 0, 'mailUngueltig' => 0, 'nichtAngelegt' => 0,
               'wawi' => 0, 'inaktiv' => 0, 'inaktivZugang' => 0, 'inaktivMail' => 0, 'neuInaktiv' => 0, 'reaktiviert' => 0, 'bleibtAktivZugang' => 0, 'bleibtAktivHand' => 0, 'bleibtInaktiv' => 0];
        $fremd = []; $fremdV = []; $bspNeu = []; $bspAkt = []; $bspInaktiv = []; $ch = []; $seen = []; $zeilen = [];
        $zeile = function (string $art, $r, array $x, string $text) use (&$zeilen, $details) {
            if ($details) $zeilen[] = ['art' => $art, 'zeile' => import_zeilennr($r), 'schluessel' => $x['nr'], 'name' => $x['firma'], 'text' => $text];
        };
        // Meldet sich der Kunde in den 18 Monaten auf der Angebotsseite an, ist er aktiv – auch ohne Rechnung
        $nutztZugang = function (array $c) use ($stichtag): bool {
            $l = $c['login'] ?? null;
            return is_array($l) && !empty($l['active']) && substr((string)($l['lastLogin'] ?? ''), 0, 10) >= $stichtag;
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
            $wAlt = $idx !== null && is_array($d['customers'][$idx]['wawi'] ?? null) ? $d['customers'][$idx]['wawi'] : [];
            $w = kunden_wawi_neu($wAlt, $r['wawi'] ?? null, $wawiFelder);
            // Aktiv laut Warenwirtschaft (null = Regel nicht angewendet)
            $soll = null; $grund = '';
            if ($regel) {
                $stern = !empty($r['stern']);
                $soll = !$stern && kunden_letztes_datum($w) >= $stichtag;   // ohne Datum: '' liegt vor jedem Stichtag
                if (!$soll) $grund = $stern ? 'in der Warenwirtschaft mit „*“ markiert'
                    : 'keine Rechnung seit ' . KUNDEN_AKTIV_MONATE . ' Monaten' . (($w['letzteRechnung'] ?? '') !== '' ? ' (letzte ' . kunden_dmy($w['letzteRechnung']) . ')' : '');
            }
            if ($idx === null) {
                if (!$anlegen) { $st['nichtAngelegt']++; continue; }
                $aktiv = $soll ?? true;
                $row = ['id' => 'k' . bin2hex(random_bytes(6))];
                foreach (CUSTOMER_FIELDS as $f => $max) $row[$f] = $x[$f] ?? '';
                $row += ['angebote' => [], 'active' => $aktiv, 'mailAngebot' => false, 'login' => null, 'created' => now(), 'changed' => now()];
                if (!$aktiv) { $row['autoInaktiv'] = ['seit' => now(), 'grund' => $grund]; $st['neuInaktiv']++; }
                if ($w) $row['wawi'] = $w + ['stand' => now()];
                $d['customers'][] = $row;
                if ($x['nr'] !== '') $byNr[$x['nr']] = count($d['customers']) - 1;
                else $byName[mb_strtolower($x['firma']) . '|' . $x['plz']] = count($d['customers']) - 1;   // gleiche Zeile ohne Nummer nicht doppelt anlegen
                $st['neu']++;
                if (count($bspNeu) < 8) $bspNeu[] = ['nr' => $x['nr'], 'firma' => $x['firma'], 'ort' => $x['ort'], 'gruppe' => $x['gruppe'], 'aktiv' => $aktiv];
                if (count($ch) < 2000) $ch[] = ['k' => "c{$row['id']}|+", 'code' => $x['nr'], 'name' => $x['firma'], 'f' => 'Neuer Kunde (Import)', 'from' => '', 'to' => trim($x['plz'] . ' ' . $x['ort']) . ($aktiv ? '' : " – inaktiv: $grund")];
                $zeile('neu', $r, $x, implode(' · ', array_filter([trim($x['plz'] . ' ' . $x['ort']), $x['gruppe'] !== '' ? 'Kundengruppe ' . $x['gruppe'] : '', $aktiv ? '' : "inaktiv: $grund"])));
                continue;
            }
            $c = $d['customers'][$idx];
            $neu = $c; $diff = [];
            foreach (['nr', 'gruppe', 'vertreter', 'vertreter2', 'strasse', 'plz', 'ort', 'land', 'telefon'] as $f) if ($x[$f] !== '' && (string)($c[$f] ?? '') !== $x[$f]) $neu[$f] = $x[$f];   // Warenwirtschaft führt Adresse, Gruppe, Vertreter
            foreach (['firma', 'email'] as $f) if ($x[$f] !== '' && (string)($c[$f] ?? '') === '') $neu[$f] = $x[$f];                                     // nur ergänzen
            foreach (array_merge(['firma', 'email'], ['nr', 'gruppe', 'vertreter', 'vertreter2', 'strasse', 'plz', 'ort', 'land', 'telefon']) as $f) if ((string)($c[$f] ?? '') !== (string)($neu[$f] ?? '')) $diff[$f] = [(string)($c[$f] ?? ''), (string)$neu[$f]];
            // Daten der Warenwirtschaft: Vergleich ohne Stand (Typen je Feld fest, daher reicht ==)
            $wawiNeu = $w != array_diff_key($wAlt, ['stand' => true]);
            if ($wawiNeu) { if ($w) $neu['wawi'] = $w + ['stand' => now()]; else unset($neu['wawi']); }
            // Aktiv-Status
            $aktivAlt = !empty($c['active']);
            $warum = '';
            if ($soll === false && $aktivAlt) {
                if (!empty($c['aktivVonHand'])) $st['bleibtAktivHand']++;   // von Hand wieder aktiviert – bleibt so
                elseif ($nutztZugang($c)) $st['bleibtAktivZugang']++;
                else {
                    $neu['active'] = false;
                    $neu['autoInaktiv'] = ['seit' => now(), 'grund' => $grund];
                    $warum = $grund;
                    $zugang = !empty($c['login']['active']);
                    $mail = (!array_key_exists('mailAngebot', $c) || !empty($c['mailAngebot'])) && (string)($c['email'] ?? '') !== '';   // wie customer_public
                    $st['inaktiv']++;
                    if ($zugang) $st['inaktivZugang']++;
                    if ($mail) $st['inaktivMail']++;
                    $bspInaktiv[] = ['nr' => (string)($c['nr'] ?? ''), 'firma' => (string)$c['firma'], 'zugang' => $zugang, 'mail' => $mail, 'grund' => $grund];
                }
            } elseif ($soll === true && !$aktivAlt) {
                if (!empty($c['autoInaktiv'])) { $neu['active'] = true; unset($neu['autoInaktiv']); $warum = 'wieder Rechnung bzw. Lieferschein'; $st['reaktiviert']++; }
                else $st['bleibtInaktiv']++;   // von Hand deaktiviert – bleibt so
            }
            if ($aktivAlt !== !empty($neu['active'])) $diff['active'] = [$aktivAlt ? 'ja' : 'nein', !empty($neu['active']) ? 'ja' : 'nein'];
            if (!$diff && !$wawiNeu) { $st['unveraendert']++; continue; }
            $neu['changed'] = now();
            $d['customers'][$idx] = $neu;
            $st['aktualisiert']++;
            if ($wawiNeu) $st['wawi']++;
            $felder = array_merge(array_map(function ($f) { return CUSTOMER_LABELS[$f]; }, array_keys($diff)), $wawiNeu ? ['Daten der Warenwirtschaft'] : []);
            if (count($bspAkt) < 8) $bspAkt[] = ['nr' => $neu['nr'] ?? '', 'firma' => $neu['firma'], 'felder' => $felder];
            // Protokoll: Stammdaten und Aktiv-Status je Feld; Werte der Warenwirtschaft (Umsätze usw.) nur als Anzahl in der Zusammenfassung
            foreach ($diff as $f => [$from, $to]) if (count($ch) < 2000) $ch[] = ['k' => "c{$neu['id']}|$f", 'code' => $neu['nr'] ?? '', 'name' => $neu['firma'], 'f' => CUSTOMER_LABELS[$f], 'from' => $from, 'to' => $to . ($f === 'active' && $warum !== '' ? " ($warum)" : '')];
            $teile = array_map(function ($f, $v) use ($warum) { return CUSTOMER_LABELS[$f] . ': ' . ($v[0] === '' ? '–' : $v[0]) . ' → ' . $v[1] . ($f === 'active' && $warum !== '' ? " ($warum)" : ''); }, array_keys($diff), $diff);
            if ($wawiNeu) $teile[] = 'Daten der Warenwirtschaft aktualisiert';
            $zeile('geaendert', $r, ['nr' => (string)($neu['nr'] ?? ''), 'firma' => $neu['firma']], implode('; ', $teile));
        }
        if (count($d['customers']) > 20000) fail('Zu viele Kunden (höchstens 20.000).', 422);
        arsort($fremd); arsort($fremdV);
        usort($bspInaktiv, function ($a, $b) { return ((int)$b['zugang'] * 2 + (int)$b['mail']) - ((int)$a['zugang'] * 2 + (int)$a['mail']); });   // mit Zugang bzw. Wochenangebot zuerst
        $out = ['stat' => $st, 'gruppenUnbekannt' => (object)array_slice($fremd, 0, 20, true), 'vertreterUnbekannt' => (object)array_slice($fremdV, 0, 20, true),
                'beispiele' => ['neu' => $bspNeu, 'aktualisiert' => $bspAkt, 'inaktiv' => array_slice($bspInaktiv, 0, 8)]];
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
    $s = $out['stat'];
    $anz = function (int $z, string $eins, string $viele): string { return number_format($z, 0, ',', '.') . ' ' . ($z === 1 ? $eins : $viele); };
    if (!$pruefen && ($s['neu'] || $s['aktualisiert'])) {
        $zus = array_filter([$s['inaktiv'] ? "{$s['inaktiv']} inaktiv gesetzt" : '', $s['neuInaktiv'] ? "{$s['neuInaktiv']} neu als inaktiv" : '',
                             $s['reaktiviert'] ? "{$s['reaktiviert']} wieder aktiv" : '', $s['wawi'] ? "Daten der Warenwirtschaft bei {$s['wawi']} aktualisiert" : '']);
        audit('customers', 'Kunden ' . ($quelle !== '' ? "aus „{$quelle}“ " : '') . "importiert: {$s['neu']} neu, {$s['aktualisiert']} aktualisiert" . ($zus ? ' (' . implode(', ', $zus) . ')' : ''), $ch);
    }
    // Hinweise zu Aktiv-Regel und Daten der Warenwirtschaft (Dialog unter Stammdaten → Kunden und Importzentrale)
    $h = [];
    if ($regelGewuenscht && !$regel) $h[] = ['stufe' => 'warn', 'text' => 'Die Datei hat keine Spalte „LetzteRechnung“ – der Aktiv-Status der Kunden bleibt unverändert.'];
    if ($regel) {
        $h[] = ['stufe' => 'info', 'text' => 'Aktiv-Status nach der Warenwirtschaft: Kunden ohne Rechnung, Lieferschein und Neuanlage seit dem ' . kunden_dmy($stichtag) . ' (' . KUNDEN_AKTIV_MONATE . ' Monate) werden inaktiv'
            . ($s['inaktiv'] || $s['neuInaktiv'] ? ' – ' . implode(', ', array_filter([$s['inaktiv'] ? $anz($s['inaktiv'], 'bestehender Kunde', 'bestehende Kunden') : '', $s['neuInaktiv'] ? $anz($s['neuInaktiv'], 'neuer Kunde', 'neue Kunden') : ''])) : ' – keiner')
            . '. Kommt wieder eine Rechnung, wird ein so deaktivierter Kunde beim nächsten Import wieder aktiv.'];
        if ($s['inaktivZugang']) $h[] = ['stufe' => 'warn', 'text' => $anz($s['inaktivZugang'], 'Kunde hat', 'Kunden haben') . ' einen Zugang zur Angebotsseite und ' . ($s['inaktivZugang'] === 1 ? 'kann' : 'können') . ' sich danach nicht mehr anmelden (der Zugang bleibt gespeichert).'];
        if ($s['inaktivMail']) $h[] = ['stufe' => 'warn', 'text' => $anz($s['inaktivMail'], 'Kunde bekommt', 'Kunden bekommen') . ' das Wochenangebot per E-Mail und ' . ($s['inaktivMail'] === 1 ? 'erhält' : 'erhalten') . ' es als inaktive Kunden nicht mehr.'];
        if ($s['reaktiviert']) $h[] = ['stufe' => 'info', 'text' => $anz($s['reaktiviert'], 'automatisch deaktivierter Kunde wird', 'automatisch deaktivierte Kunden werden') . ' wieder aktiv.'];
        if ($s['bleibtAktivZugang']) $h[] = ['stufe' => 'info', 'text' => $anz($s['bleibtAktivZugang'], 'Kunde ohne Rechnung bleibt', 'Kunden ohne Rechnung bleiben') . ' aktiv – angemeldet auf der Angebotsseite in den letzten ' . KUNDEN_AKTIV_MONATE . ' Monaten.'];
        if ($s['bleibtAktivHand']) $h[] = ['stufe' => 'info', 'text' => $anz($s['bleibtAktivHand'], 'von Hand aktivierter Kunde ohne Rechnung bleibt', 'von Hand aktivierte Kunden ohne Rechnung bleiben') . ' aktiv.'];
        if ($s['bleibtInaktiv']) $h[] = ['stufe' => 'info', 'text' => $anz($s['bleibtInaktiv'], 'von Hand deaktivierter Kunde hat', 'von Hand deaktivierte Kunden haben') . ' wieder Rechnungen und ' . ($s['bleibtInaktiv'] === 1 ? 'bleibt' : 'bleiben') . ' trotzdem inaktiv (bei Bedarf im Kunden-Dialog aktivieren).'];
    }
    if ($wawiFelder) $h[] = ['stufe' => 'info', 'text' => 'Weitere Spalten (Konto, Rechnungsempfänger, Kreditlimit, Kondition, Umsätze und Rohgewinne, letzte Rechnung und Lieferschein, Anlage, GLN, E-Mail-Adressen für AB, Lieferschein und E-Rechnung, Rechnungssperre, CITTI, DFB) werden als Daten der Warenwirtschaft beim Kunden gespeichert'
        . ($s['wawi'] ? ' – bei ' . $anz($s['wawi'], 'bestehendem Kunden', 'bestehenden Kunden') . ' geändert' : '') . '. Sichtbar nur mit dem Recht „Kunden bearbeiten“.'];
    return ['rev' => $rev, 'regel' => $regel, 'stichtag' => $stichtag, 'hinweise' => $h] + $out;
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
    $r = kunden_import_lauf(['rows' => $rows, 'anlegen' => !empty($e['optionen']['anlegen']), 'aktivRegel' => !empty($e['optionen']['aktivRegel']),
                             'wawiFelder' => $e['wawiFelder'] ?? [], 'quelle' => $e['quelle'] ?? '', 'rev' => $e['stand'] ?? -1], $pruefen, true);
    $s = $r['stat'];
    $h = $r['hinweise'];
    $liste = function ($m) { $o = []; foreach ($m as $nr => $n) $o[] = "$nr ($n)"; return implode(', ', $o); };
    if ((array)$r['gruppenUnbekannt']) $h[] = ['stufe' => 'warn', 'text' => 'Kundengruppe nicht in der Liste (Stammdaten → Kundengruppen), Gruppe bleibt leer: ' . $liste($r['gruppenUnbekannt'])];
    if ((array)$r['vertreterUnbekannt']) $h[] = ['stufe' => 'warn', 'text' => 'Vertreter nicht in der Liste (Stammdaten → Vertreter), Feld bleibt leer: ' . $liste($r['vertreterUnbekannt'])];
    if ($s['mailUngueltig']) $h[] = ['stufe' => 'warn', 'text' => "{$s['mailUngueltig']}× ungültige E-Mail-Adresse – Feld bleibt leer."];
    $sternDatei = count(array_filter(is_array($e['rows'] ?? null) ? $e['rows'] : [], function ($r) { return is_array($r) && !empty($r['stern']); }));
    if ($stern) $h[] = ['stufe' => 'info', 'text' => "$stern mit „*“ markierte " . ($stern === 1 ? 'Kunde' : 'Kunden') . ' übersprungen (in der Warenwirtschaft nicht mehr aktiv).'];
    elseif ($sternDatei) $h[] = ['stufe' => 'info', 'text' => "$sternDatei mit „*“ markierte " . ($sternDatei === 1 ? 'Kunde wird' : 'Kunden werden') . ' mit übernommen (in der Warenwirtschaft nicht mehr aktiv).'];
    if ($s['nichtAngelegt']) $h[] = ['stufe' => 'info', 'text' => "{$s['nichtAngelegt']} neue Kunden nicht angelegt (nur bestehende aktualisieren)."];
    $h[] = ['stufe' => 'info', 'text' => 'Abgleich über die Kundennummer (ohne Nummer über Firma und PLZ). Bestehende Kunden: Kundengruppe, Vertreter, Adresse, Land und Telefon aus der Datei; Firma und E-Mail nur, wenn sie noch leer sind. Zugang, Freischaltungen und Notizen bleiben. Kunden, die nicht in der Datei stehen, bleiben unverändert. Neue Kunden bekommen keinen Zugang und kein Wochenangebot per E-Mail.'];
    // Warnungen zuerst (Reihenfolge der Anzeige)
    usort($h, function ($a, $b) { return ($a['stufe'] === 'warn' ? 0 : 1) - ($b['stufe'] === 'warn' ? 0 : 1); });
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
    $res = with_lock($liste, function () use ($rev, $groups, $me, $liste, $L) {
        $cur = gruppen_load($liste);
        if ($rev !== $cur['rev']) fail("Die {$L['viele']} wurden inzwischen an anderer Stelle geändert. Bitte neu laden.", 409);
        $alt = []; foreach ($cur['groups'] as $g) $alt[$g['nr']] = $g;
        $groups = gruppen_clean($liste, $groups, $alt);   // unter der Sperre: nicht gesendete und unbekannte Felder bleiben
        $neu = 0; $geaendert = 0;
        foreach ($groups as $g) { if (!isset($alt[$g['nr']])) $neu++; elseif ($alt[$g['nr']] != $g) $geaendert++; unset($alt[$g['nr']]); }
        $d = ['rev' => $cur['rev'] + 1, 'groups' => $groups, 'updatedAt' => now(), 'updatedBy' => $me['name']]
           + (is_array($roh = store_read($liste)) ? $roh : []);   // weitere Felder einer neueren Fassung bleiben (GR-006)
        store_write($liste, $d);
        return [$d, $neu, $geaendert, count($alt), $groups];
    });
    [$d, $neu, $geaendert, $weg, $groups] = $res;
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
    $cur = gruppen_load($liste);
    $alt = []; foreach ($cur['groups'] as $g) $alt[$g['nr']] = $g;
    $groups = gruppen_clean($liste, $roh, $alt);
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
