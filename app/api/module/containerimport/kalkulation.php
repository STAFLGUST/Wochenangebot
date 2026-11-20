<?php
declare(strict_types=1);
/* STAFL-Plattform · Modul Container-Import – Kalkulation je Container (Auftrag des Inhabers 20.11.2026): Einstandspreis
   frei Lager je Position aus Einkaufspreis, Seefracht, Versicherung, Einkaufsprovision, Zoll und Nebenkosten; je Teil der
   Partie (Abnehmer) Ist, Soll, VK, Rohertrag und Rohgewinn. Zollregime je Position: Hilton-Kontingent, Mercosur-Kontingent,
   Drittlandszoll, EU-Ursprung oder ein anderer Satz – „anteilig Hilton“ = derselbe Artikel in mehreren Positionen.
   Eine Regel, nur auf dem Server: ci_kalkulation_rechnen ist eine reine Funktion (Eingabe + Sätze → Ergebnis, kein
   Speicher, intern ungerundet, gerundet wird nur in der Anzeige) – Unit-Test tests/unit/test_ci_kalkulation.py.
   Formeln (Seefracht und Preise in USD werden mit dem Kurs USD je € umgerechnet):
     Fracht/kg      = Seefracht € / Netto aller Positionen
     Vers.-Wert Teil = (Warenwert € des Teils + Seefracht € × kg-Anteil des Teils) × (1 + imaginärer Gewinn %)
     Vers./kg       = Prämie des Teils (Vers.-Wert × Satz %) / Netto des Teils
     Zollwert/kg    = Preis € + Fracht/kg + Vers./kg (+ Provision/kg nur, wenn sie keine Einkaufsprovision ist: Art. 71
                      Abs. 1 Buchst. a Ziff. i UZK nimmt Einkaufsprovisionen aus dem Zollwert)
     Zoll/kg        = Zollwert/kg × Wertzoll % + spezifischer Zoll €/100 kg / 100
     Einstand/kg    = Preis € + Fracht/kg + Vers./kg + Provision/kg + Zoll/kg + Nebenkosten/kg
     Nebenkosten/kg = (Nachlauf + Finanzierung + Zahlungskosten) / Netto aller Positionen + Zuschlag €/kg;
                      Finanzierung = Warenwert € × Zins % × Tage / 360; Zahlungskosten = Warenwert € × ‰ / 1000 + fix
   Sätze stehen nur in CI_KALK_SAETZE (mit Quelle) – je Kalkulation überschreibbar mit Pflicht-Vermerk. Ein Entwurf rechnet
   mit dem Stand dieser Tabelle; „endgültig festschreiben“ hält Eingabe, Sätze, Ergebnis und Container fest (GR-106).
   Danach ändert nur eine neue Fassung mit Grund etwas; Fassungen werden nie gelöscht (GoBD).
   Dokument: containerimport-kalkulationen (eigene Sperre). Aktionen: app/api/aktionen/containerimport_kalkulation.php. */
if (!defined('WA_API')) { http_response_code(404); exit; }

const CI_KALK_DOKUMENT = 'containerimport-kalkulationen';
const CI_KALK_MAX_POSITIONEN = 300;
const CI_KALK_MAX_TEILE = 12;
const CI_KALK_MAX_FASSUNGEN = 100;
const CI_KALK_IMAG_TOLERANZ = 0.10;   // Imag. EK weicht ab hier vom Einstand ab → Hinweis
const CI_KALK_SKE_OHNE_KNOCHEN = 1.3; // Schlachtkörperäquivalent je kg Fleisch ohne Knochen (Anrechnung auf das Mercosur-Kontingent)

const CI_KALK_HILTON_LAENDER = ['AR', 'AU', 'BR', 'CA', 'NZ', 'PY', 'US', 'UY'];
const CI_KALK_MERCOSUR = ['AR', 'BR', 'PY', 'UY'];
const CI_KALK_EU = ['AT', 'BE', 'BG', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI', 'FR', 'GR', 'HR', 'HU', 'IE', 'IT', 'LT', 'LU', 'LV', 'MT', 'NL', 'PL', 'PT', 'RO', 'SE', 'SI', 'SK'];

/* Zollregime zur Auswahl je Position. Die Schlüssel stehen in gespeicherten Kalkulationen: nie umbenennen (GR-006). */
const CI_KALK_REGIME = [
    'hilton' => 'Hilton-Kontingent',
    'mercosur' => 'Mercosur-Kontingent',
    'drittland' => 'Drittlandszoll (ohne Kontingent)',
    'eu' => 'EU-Ursprung (kein Zoll)',
    'anderer' => 'Anderer Satz',
];
/* KN-Codes mit hinterlegtem Drittlandszoll → Satz in CI_KALK_SAETZE */
const CI_KALK_KN = [
    '02013000' => ['text' => '0201 30 00', 'name' => 'frisch oder gekühlt, ohne Knochen', 'satz' => 'drittland_frisch'],
    '02023090' => ['text' => '0202 30 90', 'name' => 'gefroren, ohne Knochen', 'satz' => 'drittland_gefroren'],
];
const CI_KALK_TARIC = 'vor Verwendung in TARIC prüfen';
/* Zollsätze an einer Stelle: Wertzoll in %, spezifischer Zoll in € je 100 kg, Quelle, gültig ab (leer = ohne Datum).
   Vorgaben des Inhabers vom 20.11.2026 – jeder Satz ist vor Verwendung in TARIC zu prüfen (CI_KALK_TARIC). Ändert sich ein
   Satz, hier ändern: Entwürfe rechnen sofort damit, festgeschriebene Fassungen behalten ihren Schnappschuss. */
const CI_KALK_SAETZE = [
    'hilton' => ['name' => 'Hilton-Kontingent', 'wert' => 20.0, 'spez' => 0.0, 'ab' => '',
        'quelle' => 'Zollkontingent für hochwertiges Rindfleisch („Hilton“), Kontingentszollsatz 20 %; Ursprung AR, AU, BR, CA, NZ, PY, US, UY'],
    'hilton_mercosur' => ['name' => 'Hilton-Kontingent, Ursprung Mercosur', 'wert' => 0.0, 'spez' => 0.0, 'ab' => '2026-05-01',
        'quelle' => 'Vorläufige Anwendung des Interimsabkommens EU-Mercosur ab 01.05.2026: Hilton-Kontingent für Ursprung AR, BR, PY, UY zollfrei (https://commission.europa.eu/topics/trade/eu-mercosur-trade-agreement_en)'],
    'mercosur' => ['name' => 'Mercosur-Kontingent Rindfleisch', 'wert' => 7.5, 'spez' => 0.0, 'ab' => '2026-05-01',
        'quelle' => 'Interimsabkommen EU-Mercosur: Kontingent 99.000 t Schlachtkörperäquivalent, Kontingentszollsatz 7,5 %; nur Ursprung AR, BR, PY, UY mit Ursprungsnachweis und Kontingentszertifikat (https://commission.europa.eu/topics/trade/eu-mercosur-trade-agreement_en)'],
    'drittland_frisch' => ['name' => 'Drittlandszoll KN 0201 30 00 (frisch oder gekühlt, ohne Knochen)', 'wert' => 12.8, 'spez' => 303.4, 'ab' => '',
        'quelle' => 'Gemeinsamer Zolltarif, VO (EWG) Nr. 2658/87 Anhang I (Kombinierte Nomenklatur): 12,8 % + 303,4 €/100 kg'],
    'drittland_gefroren' => ['name' => 'Drittlandszoll KN 0202 30 90 (gefroren, ohne Knochen)', 'wert' => 12.8, 'spez' => 304.1, 'ab' => '',
        'quelle' => 'Gemeinsamer Zolltarif, VO (EWG) Nr. 2658/87 Anhang I (Kombinierte Nomenklatur): 12,8 % + 304,1 €/100 kg'],
    'eu' => ['name' => 'EU-Ursprung', 'wert' => 0.0, 'spez' => 0.0, 'ab' => '', 'quelle' => 'Ware mit Ursprung in der EU: kein Zoll'],
];

/* Eingabe einer neuen Kalkulation */
const CI_KALK_VORGABE_KOPF = ['kurs' => null, 'datum' => '', 'seefracht' => 0.0, 'seefrachtWaehrung' => 'USD', 'provisionT' => 0.0, 'provisionEinkauf' => true,
    'nachlauf' => 0.0, 'nachlaufKg' => 0.0, 'zins' => 0.0, 'tage' => 70, 'zahlPromille' => 1.5, 'zahlFix' => 50.0, 'imagGewinn' => 10.0];

/* ---------- Eingabe prüfen (Grenze: alles, was vom Browser kommt) ---------- */
/* Zahl im Bereich [$min, $max] oder null (leer); Text auch in deutscher Schreibweise („1.234,5“). Nicht gerundet. */
function ci_kalk_zahl($v, string $was, float $max, float $min = 0.0): ?float
{
    if ($v === null || $v === '') return null;
    if (is_string($v)) {
        $v = str_replace([' ', "\u{a0}"], '', trim($v));
        if (preg_match('/^-?\d{1,3}(\.\d{3})+(,\d+)?$/', $v)) $v = str_replace('.', '', $v);
        $v = str_replace(',', '.', $v);
    }
    if (is_bool($v) || !is_numeric($v) || !is_finite((float)$v) || (float)$v < $min || (float)$v > $max)
        throw new InvalidArgumentException("$was: bitte eine Zahl von " . str_replace('.', ',', (string)$min) . ' bis ' . number_format($max, 0, ',', '.') . ' angeben.');
    return (float)$v;
}
/* KN-Code: acht Ziffern (Leerzeichen erlaubt) oder leer */
function ci_kalk_kn($v): string
{
    $kn = preg_replace('/\s+/', '', eudr_text($v, 20, 'KN-Code')) ?? '';
    if ($kn !== '' && !preg_match('/^\d{8}$/', $kn)) throw new InvalidArgumentException('KN-Code: bitte acht Ziffern angeben (z. B. 0201 30 00).');
    return $kn;
}
/* Rohe Eingabe → geprüfte Eingabe. Wirft InvalidArgumentException bei unlesbaren Werten (422). Was nur unvollständig ist
   (Kurs, Gewichte, KN-Code …), bleibt erlaubt – so lässt sich ein Entwurf speichern; ci_kalkulation_rechnen meldet es. */
function ci_kalkulation_eingabe(array $b): array
{
    $k = is_array($b['kopf'] ?? null) ? $b['kopf'] : [];
    $kopf = [
        'kurs' => ci_kalk_zahl($k['kurs'] ?? null, 'Kurs USD/€', 1000),
        'datum' => eudr_datum($k['datum'] ?? '', 'Datum'),
        'seefracht' => ci_kalk_zahl($k['seefracht'] ?? null, 'Seefracht', 1e7) ?? 0.0,
        'seefrachtWaehrung' => eudr_wahl($k['seefrachtWaehrung'] ?? '', ['USD', 'EUR'], 'Währung der Seefracht', 'USD'),
        'provisionT' => ci_kalk_zahl($k['provisionT'] ?? null, 'Provision €/t', 1e5) ?? 0.0,
        'provisionEinkauf' => !array_key_exists('provisionEinkauf', $k) || (bool)$k['provisionEinkauf'],
        'nachlauf' => ci_kalk_zahl($k['nachlauf'] ?? null, 'Nachlauf €', 1e7) ?? 0.0,
        'nachlaufKg' => ci_kalk_zahl($k['nachlaufKg'] ?? null, 'Zuschlag Nachlauf €/kg', 100) ?? 0.0,
        'zins' => ci_kalk_zahl($k['zins'] ?? null, 'Zinssatz %', 100) ?? 0.0,
        'tage' => (int)(ci_kalk_zahl($k['tage'] ?? null, 'Zinstage', 3650) ?? 0),
        'zahlPromille' => ci_kalk_zahl($k['zahlPromille'] ?? null, 'Zahlungskosten ‰', 1000) ?? 0.0,
        'zahlFix' => ci_kalk_zahl($k['zahlFix'] ?? null, 'Zahlungskosten fix €', 1e6) ?? 0.0,
        'imagGewinn' => ci_kalk_zahl($k['imagGewinn'] ?? null, 'Imaginärer Gewinn %', 100) ?? 0.0,
    ];
    $teile = [];
    foreach (ci_kalk_liste($b['teile'] ?? [], CI_KALK_MAX_TEILE, 'Teile') as $t) {
        $id = eudr_text($t['id'] ?? '', 12, 'Kennung des Teils', true);
        if (!preg_match('/^[a-z0-9]+$/', $id) || isset($teile[$id])) throw new InvalidArgumentException('Kennung des Teils ungültig oder doppelt.');
        $teile[$id] = ['id' => $id, 'name' => eudr_text($t['name'] ?? '', 80, 'Name des Teils', true), 'abnehmer' => eudr_text($t['abnehmer'] ?? '', 120, 'Abnehmer'),
            'versicherung' => ci_kalk_zahl($t['versicherung'] ?? null, 'Versicherung %', 100) ?? 0.0,
            'rueckverguetung' => ci_kalk_zahl($t['rueckverguetung'] ?? null, 'Rückvergütung %', 100) ?? 0.0,
            'wkz' => ci_kalk_zahl($t['wkz'] ?? null, 'WKZ €', 1e7) ?? 0.0];
    }
    $positionen = [];
    foreach (ci_kalk_liste($b['positionen'] ?? [], CI_KALK_MAX_POSITIONEN, 'Positionen') as $n => $p) {
        $was = 'Position ' . ($n + 1);
        $teil = is_string($p['teil'] ?? null) ? $p['teil'] : '';
        if (!isset($teile[$teil])) throw new InvalidArgumentException("$was: bitte einen Teil wählen.");
        $regime = eudr_wahl($p['regime'] ?? '', array_keys(CI_KALK_REGIME), "$was: Zollregime");
        $land = is_string($p['land'] ?? null) && trim($p['land']) !== '' ? eudr_land($p['land']) : '';
        $positionen[] = ['teil' => $teil, 'artikel' => eudr_text($p['artikel'] ?? '', 120, "$was: Artikel", true), 'rl' => (bool)($p['rl'] ?? false),
            'regime' => $regime, 'land' => $land, 'kn' => ci_kalk_kn($p['kn'] ?? ''),
            'kartons' => ci_kalk_zahl($p['kartons'] ?? null, "$was: Kartons", 1e6) ?? 0.0,
            'brutto' => ci_kalk_zahl($p['brutto'] ?? null, "$was: Brutto kg", 1e7) ?? 0.0,
            'netto' => ci_kalk_zahl($p['netto'] ?? null, "$was: Netto kg", 1e7) ?? 0.0,
            'preis' => ci_kalk_zahl($p['preis'] ?? null, "$was: Preis", 1e4) ?? 0.0,
            'waehrung' => eudr_wahl($p['waehrung'] ?? '', ['USD', 'EUR'], "$was: Währung", 'USD'),
            'imagEk' => ci_kalk_zahl($p['imagEk'] ?? null, "$was: Imag. EK", 1e4),
            'vk' => ci_kalk_zahl($p['vk'] ?? null, "$was: VK", 1e4),
            // nur für „anderer Satz“
            'wertzoll' => $regime === 'anderer' ? ci_kalk_zahl($p['wertzoll'] ?? null, "$was: Wertzoll %", 1000) ?? 0.0 : 0.0,
            'spezifisch' => $regime === 'anderer' ? ci_kalk_zahl($p['spezifisch'] ?? null, "$was: spezifischer Zoll €/100 kg", 1e5) ?? 0.0 : 0.0,
            'vermerk' => $regime === 'anderer' ? eudr_text($p['vermerk'] ?? '', 300, "$was: Vermerk zum Satz") : ''];
    }
    $ueber = [];
    foreach (is_array($b['ueberschrieben'] ?? null) ? $b['ueberschrieben'] : [] as $key => $u) {
        if (!isset(CI_KALK_SAETZE[$key]) || !is_array($u)) throw new InvalidArgumentException('Unbekannter Zollsatz.');
        $name = CI_KALK_SAETZE[$key]['name'];
        $ueber[$key] = ['wert' => ci_kalk_zahl($u['wert'] ?? null, "$name: Wertzoll %", 1000) ?? 0.0, 'spez' => ci_kalk_zahl($u['spez'] ?? null, "$name: €/100 kg", 1e5) ?? 0.0,
            'vermerk' => eudr_text($u['vermerk'] ?? '', 300, "$name: Vermerk")];
    }
    return ['kopf' => $kopf, 'teile' => array_values($teile), 'positionen' => $positionen, 'ueberschrieben' => $ueber, 'notiz' => eudr_text($b['notiz'] ?? '', 2000, 'Notiz')];
}
/* Liste aus der Eingabe (höchstens $max Einträge, jeder ein Objekt) */
function ci_kalk_liste($v, int $max, string $was): array
{
    if (!is_array($v) || !array_is_list($v) || count($v) > $max) throw new InvalidArgumentException("$was: höchstens $max Einträge.");
    foreach ($v as $x) if (!is_array($x)) throw new InvalidArgumentException("$was: ungültiger Eintrag.");
    return $v;
}

/* ---------- Rechnen (reine Funktion) ---------- */
/* Satz einer Position: [Schlüssel, Satz, Hinweise] – Schlüssel '' = keiner (Fehler in den Hinweisen) */
function ci_kalk_satz(array $p, string $datum, array $tab): array
{
    $land = $p['land'];
    $h = [];
    if ($land === '') return ['', null, [['fehler', 'Ursprungsland fehlt.']]];
    if ($p['regime'] !== 'eu' && in_array($land, CI_KALK_EU, true)) $h[] = ['warnung', "Ursprung $land liegt in der EU – dann fällt kein Zoll an (Zollregime „EU-Ursprung“)."];
    switch ($p['regime']) {
        case 'hilton':
            if (!in_array($land, CI_KALK_HILTON_LAENDER, true)) $h[] = ['warnung', "Das Hilton-Kontingent gibt es nicht für Ursprung $land (nur " . implode(', ', CI_KALK_HILTON_LAENDER) . ').'];
            $mercosur = in_array($land, CI_KALK_MERCOSUR, true);
            if ($mercosur && $datum !== '' && $datum < $tab['hilton_mercosur']['ab']) $h[] = ['hinweis', 'Vor dem ' . ci_kalk_tag($tab['hilton_mercosur']['ab']) . ' gilt im Hilton-Kontingent auch für Ursprung ' . $land . ' der Satz von ' . ci_kalk_satz_text($tab['hilton']) . '.'];
            $key = $mercosur && $datum >= $tab['hilton_mercosur']['ab'] ? 'hilton_mercosur' : 'hilton';
            return [$key, $tab[$key], $h];
        case 'mercosur':
            if (!in_array($land, CI_KALK_MERCOSUR, true)) $h[] = ['warnung', "Das Mercosur-Kontingent gilt nur für Ursprung AR, BR, PY, UY – nicht für $land."];
            if ($datum !== '' && $datum < $tab['mercosur']['ab']) $h[] = ['warnung', 'Das Mercosur-Kontingent gilt erst ab dem ' . ci_kalk_tag($tab['mercosur']['ab']) . '.'];
            if (!isset(CI_KALK_KN[$p['kn']])) $h[] = ['warnung', 'Anrechnung auf das Kontingent mit Faktor ' . str_replace('.', ',', (string)CI_KALK_SKE_OHNE_KNOCHEN) . ' (ohne Knochen) – für diesen KN-Code nicht hinterlegt, bitte prüfen.'];
            return ['mercosur', $tab['mercosur'], $h];
        case 'drittland':
            if (!isset(CI_KALK_KN[$p['kn']])) return ['', null, [['fehler', 'Drittlandszoll ist nur für KN 0201 30 00 und 0202 30 90 hinterlegt – bitte KN-Code prüfen oder „anderer Satz“ wählen.']]];
            if (in_array($land, CI_KALK_MERCOSUR, true)) $h[] = ['hinweis', "Ursprung $land: mit Kontingentszertifikat wäre das Mercosur-Kontingent möglich (Vergleich unten)."];
            $key = CI_KALK_KN[$p['kn']]['satz'];
            return [$key, $tab[$key], $h];
        case 'eu':
            if (!in_array($land, CI_KALK_EU, true)) $h[] = ['warnung', "Ursprung $land liegt nicht in der EU – Zoll fällt an."];
            return ['eu', $tab['eu'], $h];
        default:   // anderer
            if ($p['vermerk'] === '') return ['', null, [['fehler', 'Anderer Satz: bitte einen Vermerk eintragen (woher der Satz stammt).']]];
            $h[] = ['hinweis', 'Anderer Satz: ' . ci_kalk_satz_text(['wert' => $p['wertzoll'], 'spez' => $p['spezifisch']]) . ' – ' . $p['vermerk']];
            return ['anderer', ['name' => 'Anderer Satz', 'wert' => $p['wertzoll'], 'spez' => $p['spezifisch'], 'ab' => '', 'quelle' => $p['vermerk']], $h];
    }
}
function ci_kalk_satz_text(array $s): string
{
    $z = fn(float $v) => rtrim(rtrim(number_format($v, 3, ',', '.'), '0'), ',');
    return $z($s['wert']) . ' %' . ($s['spez'] > 0 ? ' + ' . $z($s['spez']) . ' €/100 kg' : '');
}
function ci_kalk_tag(string $d): string { return $d === '' ? '' : substr($d, 8, 2) . '.' . substr($d, 5, 2) . '.' . substr($d, 0, 4); }
/* Quotient, 0 bei Nenner 0 (nur wo 0 die richtige Anzeige ist und ein Hinweis den Grund nennt) */
function ci_kalk_teilen(float $a, float $b): float { return $b > 0 ? $a / $b : 0.0; }

/* Kalkulation rechnen: geprüfte Eingabe (ci_kalkulation_eingabe) + Sätze (CI_KALK_SAETZE oder Schnappschuss) → Ergebnis.
   Mit einem Fehler in den Hinweisen (Kurs, Gewicht, KN-Code …) ist das Ergebnis „unvollständig“ und enthält keine Zahlen. */
function ci_kalkulation_rechnen(array $e, array $saetze): array
{
    $k = $e['kopf'];
    $hinweise = [];
    $melde = function (string $stufe, string $text, ?int $pos = null) use (&$hinweise) { $hinweise[] = ['stufe' => $stufe, 'text' => $text, 'pos' => $pos]; };
    $tab = $saetze;
    foreach ($e['ueberschrieben'] as $key => $u) {
        if (!isset($tab[$key])) continue;
        $vorgabe = $tab[$key];
        if ($u['vermerk'] === '') $melde('fehler', $vorgabe['name'] . ': überschriebener Satz ohne Vermerk.');
        else $melde('warnung', $vorgabe['name'] . ': Satz überschrieben – ' . ci_kalk_satz_text($u) . ' statt ' . ci_kalk_satz_text($vorgabe) . ' (' . $u['vermerk'] . ').');
        $tab[$key] = ['wert' => $u['wert'], 'spez' => $u['spez'], 'vermerk' => $u['vermerk'], 'vorgabe' => ['wert' => $vorgabe['wert'], 'spez' => $vorgabe['spez']]] + $vorgabe;
    }
    if ($k['datum'] === '') $melde('fehler', 'Datum der Kalkulation fehlt (bestimmt u. a. den Satz im Hilton-Kontingent).');
    $usd = $k['seefrachtWaehrung'] === 'USD' || in_array('USD', array_column($e['positionen'], 'waehrung'), true);
    $kurs = (float)($k['kurs'] ?? 0);
    if ($usd && $kurs <= 0) $melde('fehler', 'Kurs USD/€ fehlt.');
    $gesamtKg = array_sum(array_column($e['positionen'], 'netto'));
    if (!$e['positionen']) $melde('fehler', 'Noch keine Position.');
    elseif ($gesamtKg <= 0) $melde('fehler', 'Summe Netto ist 0 kg – Fracht und Nebenkosten lassen sich nicht je kg verteilen.');
    $satz = [];
    foreach ($e['positionen'] as $i => $p) {
        [$key, $s, $h] = ci_kalk_satz($p, $k['datum'], $tab);
        $satz[$i] = $key === '' ? null : ['key' => $key] + $s;
        foreach ($h as [$stufe, $text]) $melde($stufe, $text, $i);
        if ($p['netto'] <= 0) $melde('warnung', 'Position ohne Nettogewicht.', $i);
    }
    if (in_array('fehler', array_column($hinweise, 'stufe'), true)) return ['vollstaendig' => false, 'hinweise' => $hinweise, 'saetze' => $tab];

    $eur = fn(float $betrag, string $waehrung) => $waehrung === 'USD' ? $betrag / $kurs : $betrag;
    $seefracht = $eur($k['seefracht'], $k['seefrachtWaehrung']);
    $frachtKg = $seefracht / $gesamtKg;
    $provKg = $k['provisionT'] / 1000;
    // Teile: Gewicht, Warenwert, Versicherung
    $T = [];
    foreach ($e['teile'] as $t) $T[$t['id']] = ['kg' => 0.0, 'ww' => 0.0];
    foreach ($e['positionen'] as $p) { $T[$p['teil']]['kg'] += $p['netto']; $T[$p['teil']]['ww'] += $eur($p['preis'], $p['waehrung']) * $p['netto']; }
    $warenwert = array_sum(array_column($T, 'ww'));
    foreach ($e['teile'] as $t) {
        $x = &$T[$t['id']];
        $x['frachtanteil'] = $seefracht * $x['kg'] / $gesamtKg;
        $x['versWert'] = ($x['ww'] + $x['frachtanteil']) * (1 + $k['imagGewinn'] / 100);
        $x['praemie'] = $x['versWert'] * $t['versicherung'] / 100;
        $x['versKg'] = ci_kalk_teilen($x['praemie'], $x['kg']);
        if ($x['kg'] <= 0) $melde('warnung', 'Teil „' . $t['name'] . '“ hat kein Nettogewicht.');
        unset($x);
    }
    $finanzierung = $warenwert * $k['zins'] / 100 * $k['tage'] / 360;
    $zahlung = $warenwert * $k['zahlPromille'] / 1000 + $k['zahlFix'];
    $nebenKg = ($k['nachlauf'] + $finanzierung + $zahlung) / $gesamtKg + $k['nachlaufKg'];

    $pos = [];
    foreach ($e['positionen'] as $i => $p) {
        $s = $satz[$i];
        $preisEur = $eur($p['preis'], $p['waehrung']);
        $versKg = $T[$p['teil']]['versKg'];
        $zollwertKg = $preisEur + $frachtKg + $versKg + ($k['provisionEinkauf'] ? 0.0 : $provKg);
        $zollKg = $zollwertKg * $s['wert'] / 100 + $s['spez'] / 100;
        $vorNk = $preisEur + $frachtKg + $versKg + $provKg + $zollKg;
        $einstand = $vorNk + $nebenKg;
        if ($p['imagEk'] !== null && abs($p['imagEk'] - $einstand) > CI_KALK_IMAG_TOLERANZ * $einstand)
            $melde('warnung', 'Imag. EK ' . number_format($p['imagEk'], 2, ',', '.') . ' €/kg weicht mehr als 10 % vom Einstand ' . number_format($einstand, 2, ',', '.') . ' €/kg ab.', $i);
        $pos[] = ['satz' => $s['key'], 'satzName' => $s['name'], 'wertzoll' => $s['wert'], 'spezifisch' => $s['spez'],
            'preisEur' => $preisEur, 'betragUsd' => $p['waehrung'] === 'USD' ? $p['preis'] * $p['netto'] : null, 'warenwert' => $preisEur * $p['netto'],
            'anteilTeil' => ci_kalk_teilen($p['netto'], $T[$p['teil']]['kg']),
            'frachtKg' => $frachtKg, 'versKg' => $versKg, 'provisionKg' => $provKg, 'zollwertKg' => $zollwertKg, 'zollKg' => $zollKg, 'zoll' => $zollKg * $p['netto'],
            'einstandVorNkKg' => $vorNk, 'nebenkostenKg' => $nebenKg, 'einstandKg' => $einstand, 'ist' => $einstand * $p['netto'],
            'soll' => $p['imagEk'] === null ? null : $p['imagEk'] * $p['netto'], 'vkWert' => $p['vk'] === null ? null : $p['vk'] * $p['netto'],
            'ske' => $s['key'] === 'mercosur' ? $p['netto'] * CI_KALK_SKE_OHNE_KNOCHEN : null];
    }
    $teile = [];
    foreach ($e['teile'] as $t) {
        $ids = array_keys(array_filter($e['positionen'], fn($p) => $p['teil'] === $t['id']));
        $x = ci_kalk_summe($e['positionen'], $pos, $ids) + array_intersect_key($T[$t['id']], ['frachtanteil' => 1, 'versWert' => 1, 'praemie' => 1, 'versKg' => 1]);
        if ($ids && $x['vkWert'] === null) $melde('hinweis', 'Teil „' . $t['name'] . '“: VK fehlt – kein Rohertrag.');
        $teile[] = ['id' => $t['id'], 'positionen' => count($ids)] + ci_kalk_ertrag($x, $t['rueckverguetung'] * ($x['vkWert'] ?? 0) / 100, $t['wkz']);
    }
    $gesamt = ci_kalk_summe($e['positionen'], $pos, array_keys($pos));
    $mitPositionen = array_filter($teile, fn($t) => $t['positionen'] > 0);   // ein leerer Teil verhindert keinen Gesamtertrag
    if (in_array(null, array_column($mitPositionen, 'rohertrag'), true)) $gesamt['vkWert'] = null;
    $gesamt = ci_kalk_ertrag($gesamt, array_sum(array_column($mitPositionen, 'rueckverguetung')), array_sum(array_column($mitPositionen, 'wkz')));
    $gesamt += ['seefracht' => $seefracht, 'frachtKg' => $frachtKg, 'provisionKg' => $provKg, 'finanzierung' => $finanzierung, 'zahlungskosten' => $zahlung,
        'nachlauf' => $k['nachlauf'], 'nebenkostenKg' => $nebenKg];

    // Kontingente, Zoll je Regime, Vergleich mit/ohne Mercosur-Kontingent, anteilig Hilton
    $zollRegime = $kg = [];
    foreach ($e['positionen'] as $i => $p) {
        $zollRegime[$p['regime']] = ($zollRegime[$p['regime']] ?? 0.0) + $pos[$i]['zoll'];
        $kg[$p['regime']] = ($kg[$p['regime']] ?? 0.0) + $p['netto'];
    }
    $vergleich = ['kg' => 0.0, 'mitQuote' => 0.0, 'ohneQuote' => 0.0, 'positionen' => 0];
    foreach ($e['positionen'] as $i => $p) {
        if (!in_array($p['regime'], ['mercosur', 'drittland'], true) || !in_array($p['land'], CI_KALK_MERCOSUR, true) || !isset(CI_KALK_KN[$p['kn']])) continue;
        $dl = $tab[CI_KALK_KN[$p['kn']]['satz']]; $mq = $tab['mercosur']; $zw = $pos[$i]['zollwertKg'];
        $vergleich['kg'] += $p['netto']; $vergleich['positionen']++;
        $vergleich['mitQuote'] += ($zw * $mq['wert'] / 100 + $mq['spez'] / 100) * $p['netto'];
        $vergleich['ohneQuote'] += ($zw * $dl['wert'] / 100 + $dl['spez'] / 100) * $p['netto'];
    }
    $vergleich['ersparnis'] = $vergleich['ohneQuote'] - $vergleich['mitQuote'];
    $artikel = [];
    foreach ($e['positionen'] as $p) {
        $a = mb_strtolower(trim($p['artikel']));
        $artikel[$a]['artikel'] ??= $p['artikel'];
        $artikel[$a]['regime'][$p['regime']] = ($artikel[$a]['regime'][$p['regime']] ?? 0.0) + $p['netto'];
    }
    $anteilig = array_values(array_filter($artikel, fn($a) => count($a['regime']) > 1));
    foreach ($anteilig as &$a) $a['anteilHilton'] = ci_kalk_teilen($a['regime']['hilton'] ?? 0.0, array_sum($a['regime']));
    unset($a);
    return ['vollstaendig' => true, 'hinweise' => $hinweise, 'saetze' => $tab, 'positionen' => $pos, 'teile' => $teile, 'gesamt' => $gesamt,
        'zollJeRegime' => $zollRegime, 'kgJeRegime' => $kg,
        'kontingente' => ['hilton' => $kg['hilton'] ?? 0.0, 'mercosur' => $kg['mercosur'] ?? 0.0, 'mercosurSke' => array_sum(array_filter(array_column($pos, 'ske')))],
        'vergleich' => $vergleich['positionen'] ? $vergleich : null, 'anteilig' => $anteilig];
}
/* Summen über Positionen ($ids = Stellen): Kartons, Gewichte, Beträge; Soll und VK nur, wenn jede Position sie hat */
function ci_kalk_summe(array $eingabe, array $pos, array $ids): array
{
    $s = ['kartons' => 0.0, 'brutto' => 0.0, 'netto' => 0.0, 'rl' => 0.0, 'betragUsd' => 0.0, 'warenwert' => 0.0, 'zoll' => 0.0, 'ist' => 0.0, 'soll' => 0.0, 'vkWert' => 0.0];
    foreach ($ids as $i) {
        $p = $eingabe[$i]; $r = $pos[$i];
        foreach (['kartons', 'brutto', 'netto'] as $f) $s[$f] += $p[$f];
        if ($p['rl']) $s['rl'] += $p['netto'];
        foreach (['betragUsd', 'warenwert', 'zoll', 'ist'] as $f) $s[$f] += $r[$f] ?? 0.0;
        foreach (['soll', 'vkWert'] as $f) $s[$f] = $s[$f] === null || $r[$f] === null ? null : $s[$f] + $r[$f];
    }
    if (!$ids) $s['soll'] = $s['vkWert'] = null;
    return $s;
}
/* Rohertrag (VK − Ist), Marge (vom VK), Aufschlag (vom Ist, wie „% Marge“ der bisherigen Excel), € je kg,
   Rückvergütung, WKZ und Rohgewinn – alles null ohne vollständigen VK */
function ci_kalk_ertrag(array $x, float $rueckverguetung, float $wkz): array
{
    $vk = $x['vkWert'];
    $roh = $vk === null ? null : $vk - $x['ist'];
    return ['rohertrag' => $roh, 'marge' => $roh === null || $vk <= 0 ? null : $roh / $vk, 'aufschlag' => $roh === null || $x['ist'] <= 0 ? null : $roh / $x['ist'],
        'eurKg' => $roh === null || $x['netto'] <= 0 ? null : $roh / $x['netto'],
        'rueckverguetung' => $roh === null ? null : $rueckverguetung, 'wkz' => $roh === null ? null : $wkz,
        'rohgewinn' => $roh === null ? null : $roh - $rueckverguetung - $wkz] + $x;
}

/* ---------- Fassungen (Dokument containerimport-kalkulationen) ---------- */
const CI_KALK_STAENDE = ['entwurf' => 'vorläufig', 'endgueltig' => 'endgültig'];

function ci_kalk_dokument(): array { return eudr_liste(store_read(CI_KALK_DOKUMENT)); }

/* Kalkulation eines Containers aus dem Dokument [Stelle, Eintrag] oder [null, null] */
function ci_kalk_holen(array $doc, string $sendung): array
{
    foreach ($doc['liste'] as $i => $k) if (($k['sendung'] ?? '') === $sendung) return [$i, $k];
    return [null, null];
}

/* Entwurf speichern. Ohne Kalkulation: Fassung 1 anlegen. Ist die letzte Fassung endgültig, entsteht eine neue Fassung –
   nur mit Grund. Liefert [Dokument, Kalkulation, Art: neu|entwurf|fassung]. */
function ci_kalk_speichern(array $doc, string $sendung, array $eingabe, int $rev, string $grund, array $me): array
{
    [$i, $alt] = ci_kalk_holen($doc, $sendung);
    if ($alt && (int)$alt['rev'] !== $rev) fail('Die Kalkulation wurde inzwischen von jemand anderem geändert. Bitte neu laden.', 409);
    if (!$alt && $rev !== 0) fail('Die Kalkulation wurde inzwischen von jemand anderem geändert. Bitte neu laden.', 409);
    $fassungen = $alt['fassungen'] ?? [];
    $letzte = $fassungen ? $fassungen[count($fassungen) - 1] : null;
    if ($letzte && $letzte['stand'] === 'entwurf') {
        $fassungen[count($fassungen) - 1] = ['eingabe' => $eingabe, 'geaendert' => eudr_wer($me)] + $letzte;
        $art = 'entwurf';
    } else {
        if ($letzte && $grund === '') throw new InvalidArgumentException('Die Kalkulation ist endgültig festgeschrieben. Für eine neue Fassung bitte den Grund angeben.');
        if (count($fassungen) >= CI_KALK_MAX_FASSUNGEN) fail('Zu viele Fassungen dieser Kalkulation.', 422);
        $fassungen[] = ['nr' => count($fassungen) + 1, 'stand' => 'entwurf', 'grund' => $letzte ? $grund : '', 'eingabe' => $eingabe,
            'erstellt' => eudr_wer($me), 'geaendert' => eudr_wer($me), 'endgueltig' => null];
        $art = $letzte ? 'fassung' : 'neu';
    }
    // „+ ($alt ?? [])“: Felder einer späteren Version bleiben nach einem Rückfall erhalten
    $neu = ['id' => $alt['id'] ?? eudr_id('k'), 'sendung' => $sendung, 'fassungen' => $fassungen, 'rev' => (int)($alt['rev'] ?? 0) + 1] + ($alt ?? []);
    if ($i === null) $doc['liste'][] = $neu; else $doc['liste'][$i] = $neu;
    return [$doc, $neu, $art];
}

/* Letzte Fassung endgültig festschreiben: Schnappschuss von Sätzen, Ergebnis und Container (GR-106). Nur ein vollständiges
   Ergebnis lässt sich festschreiben. Liefert [Dokument, Kalkulation]. */
function ci_kalk_festschreiben(array $doc, string $sendung, int $rev, array $container, array $me): array
{
    [$i, $k] = ci_kalk_holen($doc, $sendung);
    if (!$k) fail('Für diesen Container gibt es noch keine Kalkulation.', 404);
    if ((int)$k['rev'] !== $rev) fail('Die Kalkulation wurde inzwischen von jemand anderem geändert. Bitte neu laden.', 409);
    $n = count($k['fassungen']) - 1;
    $f = $k['fassungen'][$n];
    if ($f['stand'] !== 'entwurf') fail('Diese Fassung ist bereits endgültig.', 409);
    $ergebnis = ci_kalkulation_rechnen(ci_kalkulation_eingabe($f['eingabe']), CI_KALK_SAETZE);
    if (!$ergebnis['vollstaendig']) throw new InvalidArgumentException('Die Kalkulation ist unvollständig: ' . implode(' ', array_column(array_filter($ergebnis['hinweise'], fn($h) => $h['stufe'] === 'fehler'), 'text')));
    $f['stand'] = 'endgueltig';
    $f['endgueltig'] = ['wer' => eudr_wer($me), 'saetze' => CI_KALK_SAETZE, 'ergebnis' => $ergebnis, 'container' => $container];
    $k['fassungen'][$n] = $f;
    $k['rev']++;
    $doc['liste'][$i] = $k;
    return [$doc, $k];
}

/* Kalkulation für die Seite: je Fassung Eingabe, Sätze und Ergebnis – ein Entwurf frisch gerechnet mit den aktuellen
   Sätzen, eine endgültige Fassung genau so, wie sie festgeschrieben wurde. */
function ci_kalk_sicht(array $k): array
{
    $k['fassungen'] = array_map(function (array $f) {
        if ($f['stand'] === 'endgueltig') return $f + ['ergebnis' => $f['endgueltig']['ergebnis']];
        try {
            $f['eingabe'] = ci_kalkulation_eingabe($f['eingabe']);   // ältere Einträge bekommen neue Felder mit ihrer Vorgabe (GR-006)
            return $f + ['ergebnis' => ci_kalkulation_rechnen($f['eingabe'], CI_KALK_SAETZE)];
        } catch (InvalidArgumentException $e) {
            return $f + ['ergebnis' => ['vollstaendig' => false, 'hinweise' => [['stufe' => 'fehler', 'text' => $e->getMessage(), 'pos' => null]], 'saetze' => CI_KALK_SAETZE]];
        }
    }, $k['fassungen']);
    return $k;
}

/* Übersicht für den Reiter: je Container Stand und Nummer der letzten Fassung */
function ci_kalk_uebersicht(array $doc): array
{
    $u = [];
    foreach ($doc['liste'] as $k) {
        $f = $k['fassungen'][count($k['fassungen']) - 1];
        $u[$k['sendung']] = ['nr' => $f['nr'], 'stand' => $f['stand'], 'geaendert' => $f['endgueltig']['wer'] ?? $f['geaendert'],
            'fassungen' => count($k['fassungen']), 'endgueltige' => count(array_filter($k['fassungen'], fn($x) => $x['stand'] === 'endgueltig'))];
    }
    return $u;
}
