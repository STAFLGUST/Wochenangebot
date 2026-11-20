<?php
declare(strict_types=1);
/* STAFL-Plattform · Modul Container-Import – Kalkulation je Container (Auftrag des Inhabers 20.11.2026): Einstandspreis
   frei Lager je Position aus Einkaufspreis, Seefracht, Versicherung, Einkaufsprovision, Zoll und Nebenkosten; je Teil der
   Partie (Abnehmer) Ist, Soll, VK, Rohertrag und Rohgewinn. Zollregime je Position: Hilton-Kontingent, Mercosur-Kontingent,
   Drittlandszoll, EU-Ursprung oder ein anderer Satz – „anteilig Hilton“ = derselbe Artikel in mehreren Positionen.
   Eine Regel, nur auf dem Server: ci_kalkulation_rechnen ist eine reine Funktion (Eingabe + Sätze → Ergebnis, kein
   Speicher, intern ungerundet, gerundet wird nur in der Anzeige) – Unit-Test tests/unit/test_ci_kalkulation.py.
   Rechenschritte (je eine Funktion):
     1 Sätze anwenden (ci_kalk_saetze_anwenden): überschriebene Sätze der Kalkulation – leeres Feld = Vorgabe des Satzes
     2 Prüfen (ci_kalk_pruefen): Datum, Kurs, Gewicht, je Position Ursprung ↔ Zollregime ↔ Datum ↔ KN-Code. Unmögliche
       Kombinationen (Hilton/Mercosur-Kontingent für ein anderes Land, Mercosur-Kontingent vor dem Start, „EU-Ursprung“
       für ein Nicht-EU-Land) sind Fehler: die Kalkulation ist dann unvollständig und lässt sich nicht festschreiben
     3 Kosten des Containers (ci_kalk_kosten), Seefracht und Preise in USD mit dem Kurs USD je € umgerechnet:
         Fracht/kg      = Seefracht € / Netto aller Positionen
         Nebenkosten/kg = (Nachlauf + Finanzierung + Zahlungskosten) / Netto aller Positionen + Zuschlag €/kg;
                          Finanzierung = Warenwert € × Zins % × Tage / 360; Zahlungskosten = Warenwert € × ‰ / 1000 + fix
     4 Position (ci_kalk_position):
         Vers./kg       = (Preis € + Fracht/kg) × (1 + imaginärer Gewinn %) × Versicherung % des Teils – die Prämie des
                          Teils verteilt sich nach Wert (Warenwert + Frachtanteil der Position), nicht nach kg
         Zollwert/kg    = Preis € + Fracht/kg + Vers./kg (+ Provision/kg nur, wenn sie keine Einkaufsprovision ist: Art. 71
                          Abs. 1 Buchst. a Ziff. i UZK nimmt Einkaufsprovisionen aus dem Zollwert)
         Zoll/kg        = Zollwert/kg × Wertzoll % + spezifischer Zoll €/100 kg / 100 (ci_kalk_zoll_kg)
         Einstand/kg    = Preis € + Fracht/kg + Vers./kg + Provision/kg + Zoll/kg + Nebenkosten/kg
     5 Auswertung (ci_kalk_auswertung) je Teil und gesamt:
         Vers.-Wert Teil = (Warenwert € des Teils + Fracht/kg × Netto des Teils) × (1 + imaginärer Gewinn %);
                          Prämie = Vers.-Wert × Satz % = Summe Vers./kg × Netto der Positionen des Teils
         Rohertrag = VK − Ist, Rohgewinn = Rohertrag − Rückvergütung (% vom VK) − WKZ; dazu Zoll je Regime,
         Schlachtkörperäquivalent, Vergleich mit/ohne Mercosur-Kontingent, anteilig Hilton (ci_kalk_kontingente, ci_kalk_anteilig)
   Sätze stehen nur in CI_KALK_SAETZE (mit Quelle) – je Kalkulation überschreibbar mit Pflicht-Vermerk. Ein Entwurf rechnet
   mit dem Stand dieser Tabelle; „endgültig festschreiben“ hält Eingabe und Ergebnis (darin die wirksamen Sätze) sowie den
   Container fest (GR-106). Danach ändert nur eine neue Fassung mit Grund etwas; Fassungen werden nie gelöscht (GoBD).
   Dokument: containerimport-kalkulationen (eigene Sperre). Aktionen: app/api/aktionen/containerimport_kalkulation.php. */
if (!defined('WA_API')) { http_response_code(404); exit; }

const CI_KALK_DOKUMENT = 'containerimport-kalkulationen';
const CI_KALK_MAX_POSITIONEN = 300;
const CI_KALK_MAX_TEILE = 12;
const CI_KALK_MAX_FASSUNGEN = 100;
const CI_KALK_IMAG_TOLERANZ = 0.10;   // Imag. EK weicht ab hier vom Einstand ab → Hinweis
const CI_KALK_SKE_OHNE_KNOCHEN = 1.3; // Schlachtkörperäquivalent je kg Fleisch ohne Knochen (Anrechnung auf das Mercosur-Kontingent)
const CI_KALK_MAX_KURS = 10.0;        // USD je €
const CI_KALK_MAX_PREIS = 1000.0;     // € bzw. USD je kg (Preis, Imag. EK, VK)

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
/* KN-Codes (Rindfleisch ohne Knochen) mit hinterlegtem Drittlandszoll → Satz in CI_KALK_SAETZE */
const CI_KALK_KN = [
    '02013000' => ['text' => '0201 30 00', 'name' => 'frisch oder gekühlt, ohne Knochen', 'satz' => 'drittland_frisch'],
    '02023090' => ['text' => '0202 30 90', 'name' => 'gefroren, ohne Knochen', 'satz' => 'drittland_gefroren'],
];
const CI_KALK_TARIC = 'vor Verwendung in TARIC prüfen';
/* Zollsätze an einer Stelle: Wertzoll in %, spezifischer Zoll in € je 100 kg, Quelle, gültig ab (leer = ohne Datum), Ursprung
   (Länder, für die der Satz gilt; Prüfung in ci_kalk_position_pruefen). Vorgaben des Inhabers vom 20.11.2026 – jeder Satz ist
   vor Verwendung in TARIC zu prüfen (CI_KALK_TARIC). Ändert sich ein Satz, hier ändern: Entwürfe rechnen sofort damit,
   festgeschriebene Fassungen behalten ihren Schnappschuss. */
const CI_KALK_SAETZE = [
    'hilton' => ['name' => 'Hilton-Kontingent', 'wert' => 20.0, 'spez' => 0.0, 'ab' => '', 'laender' => CI_KALK_HILTON_LAENDER,
        'quelle' => 'Zollkontingent für hochwertiges Rindfleisch („Hilton“), Kontingentszollsatz 20 %'],
    'hilton_mercosur' => ['name' => 'Hilton-Kontingent, Ursprung Mercosur', 'wert' => 0.0, 'spez' => 0.0, 'ab' => '2026-05-01', 'laender' => CI_KALK_MERCOSUR,
        'quelle' => 'Vorläufige Anwendung des Interimsabkommens EU-Mercosur ab 01.05.2026: Hilton-Kontingent für Ursprung Mercosur zollfrei (https://commission.europa.eu/topics/trade/eu-mercosur-trade-agreement_en)'],
    'mercosur' => ['name' => 'Mercosur-Kontingent Rindfleisch', 'wert' => 7.5, 'spez' => 0.0, 'ab' => '2026-05-01', 'laender' => CI_KALK_MERCOSUR,
        'quelle' => 'Interimsabkommen EU-Mercosur: Kontingent 99.000 t Schlachtkörperäquivalent, Kontingentszollsatz 7,5 %; nur mit Ursprungsnachweis und Kontingentszertifikat (https://commission.europa.eu/topics/trade/eu-mercosur-trade-agreement_en)'],
    'drittland_frisch' => ['name' => 'Drittlandszoll KN 0201 30 00 (frisch oder gekühlt, ohne Knochen)', 'wert' => 12.8, 'spez' => 303.4, 'ab' => '',
        'quelle' => 'Gemeinsamer Zolltarif, VO (EWG) Nr. 2658/87 Anhang I (Kombinierte Nomenklatur): 12,8 % + 303,4 €/100 kg'],
    'drittland_gefroren' => ['name' => 'Drittlandszoll KN 0202 30 90 (gefroren, ohne Knochen)', 'wert' => 12.8, 'spez' => 304.1, 'ab' => '',
        'quelle' => 'Gemeinsamer Zolltarif, VO (EWG) Nr. 2658/87 Anhang I (Kombinierte Nomenklatur): 12,8 % + 304,1 €/100 kg'],
    'eu' => ['name' => 'EU-Ursprung', 'wert' => 0.0, 'spez' => 0.0, 'ab' => '', 'laender' => CI_KALK_EU, 'quelle' => 'Ware mit Ursprung in der EU: kein Zoll'],
];

/* Eingabe einer neuen Kalkulation */
const CI_KALK_VORGABE_KOPF = ['kurs' => null, 'datum' => '', 'seefracht' => 0.0, 'seefrachtWaehrung' => 'USD', 'provisionT' => 0.0, 'provisionEinkauf' => true,
    'nachlauf' => 0.0, 'nachlaufKg' => 0.0, 'zins' => 0.0, 'tage' => 70, 'zahlPromille' => 1.5, 'zahlFix' => 50.0, 'imagGewinn' => 10.0];

/* ---------- Eingabe prüfen (Grenze: alles, was vom Browser kommt) ---------- */
/* Zahl von 0 bis $max oder null (leer); Text auch deutsch („1.234,5“, eudr_zahl_text). Ein einzelner Punkt vor genau drei
   Ziffern („9.875“) gilt dort als Tausendertrenner – liegt die Zahl damit über $max, war wohl ein Dezimalpunkt gemeint:
   abgelehnt mit eigener Meldung statt still falsch gelesen. Nicht gerundet. */
function ci_kalk_zahl($v, string $was, float $max): ?float
{
    $z = eudr_zahl_text($v);
    if ($z === null) return null;
    if (!is_bool($z) && is_numeric($z) && (float)$z >= 0 && (float)$z <= $max) return (float)$z;
    if (is_string($v) && preg_match('/^\d{1,3}\.\d{3}$/', trim($v)))
        throw new InvalidArgumentException("$was: „" . trim($v) . '“ – Punkt als Tausendertrenner mehrdeutig, bitte Komma als Dezimalzeichen verwenden (' . str_replace('.', ',', trim($v)) . ').');
    throw new InvalidArgumentException("$was: bitte eine Zahl von 0 bis " . number_format($max, 0, ',', '.') . ' angeben.');
}
/* Zinstage: ganze Zahl (ein Komma würde sonst still abgeschnitten) */
function ci_kalk_tage($v): int
{
    $tage = ci_kalk_zahl($v, 'Zinstage', 3650) ?? 0.0;
    if (floor($tage) !== $tage) throw new InvalidArgumentException('Zinstage: bitte ganze Tage angeben.');
    return (int)$tage;
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
        'kurs' => ci_kalk_zahl($k['kurs'] ?? null, 'Kurs USD/€', CI_KALK_MAX_KURS),
        'datum' => eudr_datum($k['datum'] ?? '', 'Datum der Zollanmeldung'),
        'seefracht' => ci_kalk_zahl($k['seefracht'] ?? null, 'Seefracht', 1e7) ?? 0.0,
        'seefrachtWaehrung' => eudr_wahl($k['seefrachtWaehrung'] ?? '', ['USD', 'EUR'], 'Währung der Seefracht', 'USD'),
        'provisionT' => ci_kalk_zahl($k['provisionT'] ?? null, 'Provision €/t', 1e5) ?? 0.0,
        'provisionEinkauf' => !array_key_exists('provisionEinkauf', $k) || (bool)$k['provisionEinkauf'],
        'nachlauf' => ci_kalk_zahl($k['nachlauf'] ?? null, 'Nachlauf €', 1e7) ?? 0.0,
        'nachlaufKg' => ci_kalk_zahl($k['nachlaufKg'] ?? null, 'Zuschlag Nachlauf €/kg', 100) ?? 0.0,
        'zins' => ci_kalk_zahl($k['zins'] ?? null, 'Zinssatz %', 100) ?? 0.0,
        'tage' => ci_kalk_tage($k['tage'] ?? null),
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
            'preis' => ci_kalk_zahl($p['preis'] ?? null, "$was: Preis", CI_KALK_MAX_PREIS) ?? 0.0,
            'waehrung' => eudr_wahl($p['waehrung'] ?? '', ['USD', 'EUR'], "$was: Währung", 'USD'),
            'imagEk' => ci_kalk_zahl($p['imagEk'] ?? null, "$was: Imag. EK", CI_KALK_MAX_PREIS),
            'vk' => ci_kalk_zahl($p['vk'] ?? null, "$was: VK", CI_KALK_MAX_PREIS),
            // nur für „anderer Satz“
            'wertzoll' => $regime === 'anderer' ? ci_kalk_zahl($p['wertzoll'] ?? null, "$was: Wertzoll %", 1000) ?? 0.0 : 0.0,
            'spezifisch' => $regime === 'anderer' ? ci_kalk_zahl($p['spezifisch'] ?? null, "$was: spezifischer Zoll €/100 kg", 1e5) ?? 0.0 : 0.0,
            'vermerk' => $regime === 'anderer' ? eudr_text($p['vermerk'] ?? '', 300, "$was: Vermerk zum Satz") : ''];
    }
    // Überschriebene Sätze: leeres Feld (null) = Vorgabe des Satzes
    $ueber = [];
    foreach (is_array($b['ueberschrieben'] ?? null) ? $b['ueberschrieben'] : [] as $key => $u) {
        if (!isset(CI_KALK_SAETZE[$key]) || !is_array($u)) throw new InvalidArgumentException('Unbekannter Zollsatz.');
        $name = CI_KALK_SAETZE[$key]['name'];
        $ueber[$key] = ['wert' => ci_kalk_zahl($u['wert'] ?? null, "$name: Wertzoll %", 1000), 'spez' => ci_kalk_zahl($u['spez'] ?? null, "$name: €/100 kg", 1e5),
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

/* ---------- Rechnen (reine Funktionen) ---------- */
/* Kalkulation rechnen: geprüfte Eingabe (ci_kalkulation_eingabe) + Sätze (CI_KALK_SAETZE oder Schnappschuss) → Ergebnis.
   Mit einem Fehler in den Hinweisen ist das Ergebnis „unvollständig“ und enthält keine Zahlen. */
function ci_kalkulation_rechnen(array $e, array $saetze): array
{
    [$tab, $hinweise] = ci_kalk_saetze_anwenden($saetze, $e['ueberschrieben']);
    $hinweise = [...$hinweise, ...ci_kalk_pruefen($e, $tab)];
    if (in_array('fehler', array_column($hinweise, 'stufe'), true)) return ['vollstaendig' => false, 'hinweise' => $hinweise, 'saetze' => $tab];
    $kosten = ci_kalk_kosten($e);
    $teile = array_column($e['teile'], null, 'id');
    $kgTeil = [];
    foreach ($e['positionen'] as $p) $kgTeil[$p['teil']] = ($kgTeil[$p['teil']] ?? 0.0) + $p['netto'];
    $pos = [];
    foreach ($e['positionen'] as $p)
        $pos[] = ci_kalk_position($p, $e['kopf'], $kosten, $teile[$p['teil']], ci_kalk_satz($p, $e['kopf']['datum'], $tab)) + ['anteilTeil' => ci_kalk_teilen($p['netto'], $kgTeil[$p['teil']])];
    [$teilErgebnisse, $gesamt] = ci_kalk_auswertung($e, $pos, $kosten);
    return ['vollstaendig' => true, 'hinweise' => [...$hinweise, ...ci_kalk_ergebnis_pruefen($e, $pos, $teilErgebnisse)], 'saetze' => $tab,
        'positionen' => $pos, 'teile' => $teilErgebnisse, 'gesamt' => $gesamt] + ci_kalk_kontingente($e, $pos, $tab) + ['anteilig' => ci_kalk_anteilig($e['positionen'])];
}
/* Prüfhinweis: stufe fehler (Kalkulation unvollständig) | warnung | hinweis; pos = Stelle der Position oder null */
function ci_kalk_hinweis(string $stufe, string $text, ?int $pos = null): array { return ['stufe' => $stufe, 'text' => $text, 'pos' => $pos]; }

/* Schritt 1 – Sätze anwenden: überschriebene Sätze der Kalkulation über die Tabelle legen. Leeres Feld = Vorgabe des Satzes;
   ein Vermerk ohne Werte überschreibt nichts (bleibt als Hinweis sichtbar). Werte ohne Vermerk = Fehler.
   Liefert [wirksame Sätze, Hinweise]; ein überschriebener Satz trägt seine Vorgabe und den Vermerk mit. */
function ci_kalk_saetze_anwenden(array $saetze, array $ueberschrieben): array
{
    $hinweise = [];
    foreach ($ueberschrieben as $key => $u) {
        if (!isset($saetze[$key])) continue;
        $vorgabe = $saetze[$key];
        if ($u['wert'] === null && $u['spez'] === null) {
            if ($u['vermerk'] !== '') $hinweise[] = ci_kalk_hinweis('hinweis', "{$vorgabe['name']}: Vorgabe " . ci_kalk_satz_text($vorgabe) . " beibehalten – {$u['vermerk']}");
            continue;
        }
        $satz = ['wert' => $u['wert'] ?? $vorgabe['wert'], 'spez' => $u['spez'] ?? $vorgabe['spez']];
        $hinweise[] = $u['vermerk'] === '' ? ci_kalk_hinweis('fehler', "{$vorgabe['name']}: überschriebener Satz ohne Vermerk.")
            : ci_kalk_hinweis('warnung', "{$vorgabe['name']}: Satz überschrieben – " . ci_kalk_satz_text($satz) . ' statt ' . ci_kalk_satz_text($vorgabe) . " ({$u['vermerk']}).");
        $saetze[$key] = $satz + ['vermerk' => $u['vermerk'], 'vorgabe' => ['wert' => $vorgabe['wert'], 'spez' => $vorgabe['spez']]] + $vorgabe;
    }
    return [$saetze, $hinweise];
}

/* Schritt 2 – Prüfen: was fehlt oder nicht zusammenpasst, bevor gerechnet wird */
function ci_kalk_pruefen(array $e, array $tab): array
{
    $k = $e['kopf'];
    $h = [];
    if ($k['datum'] === '') $h[] = ci_kalk_hinweis('fehler', 'Datum der Zollanmeldung fehlt – es bestimmt Satz und Stichtag (Art. 85 UZK).');
    $usd = $k['seefrachtWaehrung'] === 'USD' || in_array('USD', array_column($e['positionen'], 'waehrung'), true);
    if ($usd && (float)$k['kurs'] <= 0) $h[] = ci_kalk_hinweis('fehler', 'Kurs USD/€ fehlt.');
    if (!$e['positionen']) $h[] = ci_kalk_hinweis('fehler', 'Noch keine Position.');
    elseif (array_sum(array_column($e['positionen'], 'netto')) <= 0) $h[] = ci_kalk_hinweis('fehler', 'Summe Netto ist 0 kg – Fracht und Nebenkosten lassen sich nicht je kg verteilen.');
    foreach ($e['positionen'] as $i => $p) array_push($h, ...ci_kalk_position_pruefen($p, $i, $k['datum'], $tab));
    return $h;
}
/* Ursprung ↔ Zollregime ↔ Datum ↔ KN-Code einer Position */
function ci_kalk_position_pruefen(array $p, int $i, string $datum, array $tab): array
{
    $land = $p['land'];
    $x = fn(string $stufe, string $text) => ci_kalk_hinweis($stufe, $text, $i);
    if ($land === '') return [$x('fehler', 'Ursprungsland fehlt.')];
    $eu = in_array($land, CI_KALK_EU, true);
    $mercosur = in_array($land, CI_KALK_MERCOSUR, true);
    $h = [];
    if ($p['regime'] !== 'eu' && $eu) $h[] = $x('warnung', "Ursprung $land liegt in der EU – dann fällt kein Zoll an (Zollregime „EU-Ursprung“).");
    if ($p['netto'] <= 0) $h[] = $x('warnung', 'Position ohne Nettogewicht.');
    switch ($p['regime']) {
        case 'hilton':
            if (!in_array($land, CI_KALK_HILTON_LAENDER, true)) $h[] = $x('fehler', "Das Hilton-Kontingent gibt es nicht für Ursprung $land (nur " . implode(', ', CI_KALK_HILTON_LAENDER) . ').');
            elseif ($mercosur && $datum !== '' && $datum < $tab['hilton_mercosur']['ab'])
                $h[] = $x('hinweis', 'Vor dem ' . ci_kalk_tag($tab['hilton_mercosur']['ab']) . " gilt im Hilton-Kontingent auch für Ursprung $land der Satz von " . ci_kalk_satz_text($tab['hilton']) . '.');
            break;
        case 'mercosur':
            if (!$mercosur) $h[] = $x('fehler', 'Das Mercosur-Kontingent gilt nur für Ursprung ' . implode(', ', CI_KALK_MERCOSUR) . " – nicht für $land.");
            if ($datum !== '' && $datum < $tab['mercosur']['ab']) $h[] = $x('fehler', 'Das Mercosur-Kontingent gilt erst ab dem ' . ci_kalk_tag($tab['mercosur']['ab']) . '.');
            if (!isset(CI_KALK_KN[$p['kn']])) $h[] = $x('hinweis', 'Schlachtkörperäquivalent (Faktor ' . str_replace('.', ',', (string)CI_KALK_SKE_OHNE_KNOCHEN) . ') nur für KN '
                . ci_kalk_kn_text() . ' hinterlegt – Anrechnung auf das Kontingent für diesen KN-Code bitte selbst ermitteln.');
            break;
        case 'drittland':
            if (!isset(CI_KALK_KN[$p['kn']])) $h[] = $x('fehler', 'Drittlandszoll ist nur für KN ' . ci_kalk_kn_text() . ' hinterlegt – bitte KN-Code prüfen oder „anderer Satz“ wählen.');
            elseif ($mercosur) $h[] = $x('hinweis', "Ursprung $land: mit Kontingentszertifikat wäre das Mercosur-Kontingent möglich (Vergleich unten).");
            break;
        case 'eu':
            if (!$eu) $h[] = $x('fehler', "Ursprung $land liegt nicht in der EU – bitte das passende Zollregime wählen.");
            break;
        default:   // anderer
            $h[] = $p['vermerk'] === '' ? $x('fehler', 'Anderer Satz: bitte einen Vermerk eintragen (woher der Satz stammt).')
                : $x('hinweis', 'Anderer Satz: ' . ci_kalk_satz_text(['wert' => $p['wertzoll'], 'spez' => $p['spezifisch']]) . ' – ' . $p['vermerk']);
    }
    return $h;
}
/* Wirksamer Satz einer Position mit Schlüssel; null, wenn keiner wählbar ist (ci_kalk_position_pruefen meldet den Grund) */
function ci_kalk_satz(array $p, string $datum, array $tab): ?array
{
    switch ($p['regime']) {
        case 'drittland': return ci_kalk_drittland_satz($p['kn'], $tab);
        case 'anderer': return ['key' => 'anderer', 'name' => 'Anderer Satz', 'wert' => $p['wertzoll'], 'spez' => $p['spezifisch'], 'ab' => '', 'quelle' => $p['vermerk']];
        case 'hilton':
            $key = in_array($p['land'], CI_KALK_MERCOSUR, true) && $datum >= $tab['hilton_mercosur']['ab'] ? 'hilton_mercosur' : 'hilton';
            return ['key' => $key] + $tab[$key];
        default: return ['key' => $p['regime']] + $tab[$p['regime']];   // mercosur, eu
    }
}
/* Drittlandszoll nach KN-Code (auch für den Vergleich mit dem Mercosur-Kontingent); null für einen nicht hinterlegten Code */
function ci_kalk_drittland_satz(string $kn, array $tab): ?array
{
    $key = CI_KALK_KN[$kn]['satz'] ?? null;
    return $key === null ? null : ['key' => $key] + $tab[$key];
}
/* Zoll je kg: Wertzoll % vom Zollwert + spezifischer Zoll €/100 kg */
function ci_kalk_zoll_kg(float $zollwertKg, array $satz): float { return $zollwertKg * $satz['wert'] / 100 + $satz['spez'] / 100; }
function ci_kalk_satz_text(array $s): string
{
    $z = fn(float $v) => rtrim(rtrim(number_format($v, 3, ',', '.'), '0'), ',');
    return $z($s['wert']) . ' %' . ($s['spez'] > 0 ? ' + ' . $z($s['spez']) . ' €/100 kg' : '');
}
function ci_kalk_kn_text(): string { return implode(' und ', array_column(CI_KALK_KN, 'text')); }
function ci_kalk_tag(string $d): string { return $d === '' ? '' : substr($d, 8, 2) . '.' . substr($d, 5, 2) . '.' . substr($d, 0, 4); }
/* Quotient, 0 bei Nenner 0 (nur wo 0 die richtige Anzeige ist und ein Hinweis den Grund nennt) */
function ci_kalk_teilen(float $a, float $b): float { return $b > 0 ? $a / $b : 0.0; }
function ci_kalk_eur(float $betrag, string $waehrung, float $kurs): float { return $waehrung === 'USD' ? $betrag / $kurs : $betrag; }

/* Schritt 3 – Kosten des Containers: Seefracht, Provision und Nebenkosten je kg (für alle Positionen gleich) */
function ci_kalk_kosten(array $e): array
{
    $k = $e['kopf'];
    $kurs = (float)$k['kurs'];
    $gesamtKg = array_sum(array_column($e['positionen'], 'netto'));
    $seefracht = ci_kalk_eur($k['seefracht'], $k['seefrachtWaehrung'], $kurs);
    $warenwert = array_sum(array_map(fn($p) => ci_kalk_eur($p['preis'], $p['waehrung'], $kurs) * $p['netto'], $e['positionen']));
    $finanzierung = $warenwert * $k['zins'] / 100 * $k['tage'] / 360;
    $zahlung = $warenwert * $k['zahlPromille'] / 1000 + $k['zahlFix'];
    return ['seefracht' => $seefracht, 'frachtKg' => $seefracht / $gesamtKg, 'provisionKg' => $k['provisionT'] / 1000, 'finanzierung' => $finanzierung,
        'zahlungskosten' => $zahlung, 'nachlauf' => $k['nachlauf'], 'nebenkostenKg' => ($k['nachlauf'] + $finanzierung + $zahlung) / $gesamtKg + $k['nachlaufKg']];
}

/* Schritt 4 – Position: Einstand je kg und Werte ($teil = Teil der Eingabe, $satz = ci_kalk_satz) */
function ci_kalk_position(array $p, array $kopf, array $kosten, array $teil, array $satz): array
{
    $preisEur = ci_kalk_eur($p['preis'], $p['waehrung'], (float)$kopf['kurs']);
    $versKg = ($preisEur + $kosten['frachtKg']) * (1 + $kopf['imagGewinn'] / 100) * $teil['versicherung'] / 100;
    $zollwertKg = $preisEur + $kosten['frachtKg'] + $versKg + ($kopf['provisionEinkauf'] ? 0.0 : $kosten['provisionKg']);
    $zollKg = ci_kalk_zoll_kg($zollwertKg, $satz);
    $vorNk = $preisEur + $kosten['frachtKg'] + $versKg + $kosten['provisionKg'] + $zollKg;
    $einstand = $vorNk + $kosten['nebenkostenKg'];
    return ['satz' => $satz['key'], 'satzName' => $satz['name'], 'wertzoll' => $satz['wert'], 'spezifisch' => $satz['spez'],
        'preisEur' => $preisEur, 'betragUsd' => $p['waehrung'] === 'USD' ? $p['preis'] * $p['netto'] : null, 'warenwert' => $preisEur * $p['netto'],
        'frachtKg' => $kosten['frachtKg'], 'versKg' => $versKg, 'provisionKg' => $kosten['provisionKg'], 'zollwertKg' => $zollwertKg, 'zollKg' => $zollKg,
        'zoll' => $zollKg * $p['netto'], 'einstandVorNkKg' => $vorNk, 'nebenkostenKg' => $kosten['nebenkostenKg'], 'einstandKg' => $einstand,
        'ist' => $einstand * $p['netto'], 'soll' => $p['imagEk'] === null ? null : $p['imagEk'] * $p['netto'], 'vkWert' => $p['vk'] === null ? null : $p['vk'] * $p['netto'],
        // Schlachtkörperäquivalent nur für Fleisch ohne Knochen (bekannte KN-Codes), sonst unbekannt
        'ske' => $p['regime'] === 'mercosur' && isset(CI_KALK_KN[$p['kn']]) ? $p['netto'] * CI_KALK_SKE_OHNE_KNOCHEN : null];
}

/* Schritt 5 – Auswertung je Teil und gesamt: Summen, Versicherungswert und Prämie, Ertrag. Liefert [Teile, Gesamt];
   ein Teil ohne Positionen verhindert keinen Gesamtertrag. */
function ci_kalk_auswertung(array $e, array $pos, array $kosten): array
{
    $teile = [];
    foreach ($e['teile'] as $t) {
        $ids = array_keys(array_filter($e['positionen'], fn($p) => $p['teil'] === $t['id']));
        $summe = ci_kalk_summe($e['positionen'], $pos, $ids);
        $frachtanteil = $kosten['frachtKg'] * $summe['netto'];
        $versWert = ($summe['warenwert'] + $frachtanteil) * (1 + $e['kopf']['imagGewinn'] / 100);
        $teile[] = ['id' => $t['id'], 'positionen' => count($ids), 'frachtanteil' => $frachtanteil, 'versWert' => $versWert, 'praemie' => $versWert * $t['versicherung'] / 100]
            + ci_kalk_ertrag($summe, $t['rueckverguetung'] * ($summe['vkWert'] ?? 0) / 100, $t['wkz']);
    }
    $mitPositionen = array_filter($teile, fn($t) => $t['positionen'] > 0);
    $gesamt = ci_kalk_summe($e['positionen'], $pos, array_keys($pos));
    if (in_array(null, array_column($mitPositionen, 'rohertrag'), true)) $gesamt['vkWert'] = null;
    $gesamt = ci_kalk_ertrag($gesamt, array_sum(array_column($mitPositionen, 'rueckverguetung')), array_sum(array_column($mitPositionen, 'wkz'))) + $kosten;
    return [$teile, $gesamt];
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
/* Prüfhinweise zum Ergebnis: Imag. EK weicht vom Einstand ab, Teil ohne Gewicht, Teil ohne vollständigen VK */
function ci_kalk_ergebnis_pruefen(array $e, array $pos, array $teile): array
{
    $h = [];
    foreach ($e['positionen'] as $i => $p) {
        $einstand = $pos[$i]['einstandKg'];
        if ($p['imagEk'] !== null && abs($p['imagEk'] - $einstand) > CI_KALK_IMAG_TOLERANZ * $einstand)
            $h[] = ci_kalk_hinweis('warnung', 'Imag. EK ' . number_format($p['imagEk'], 2, ',', '.') . ' €/kg weicht mehr als ' . round(CI_KALK_IMAG_TOLERANZ * 100) . ' % vom Einstand '
                . number_format($einstand, 2, ',', '.') . ' €/kg ab.', $i);
    }
    foreach ($e['teile'] as $n => $t) {
        if ($teile[$n]['netto'] <= 0) $h[] = ci_kalk_hinweis('warnung', 'Teil „' . $t['name'] . '“ hat kein Nettogewicht.');
        if ($teile[$n]['positionen'] && $teile[$n]['vkWert'] === null) $h[] = ci_kalk_hinweis('hinweis', 'Teil „' . $t['name'] . '“: VK fehlt – kein Rohertrag.');
    }
    return $h;
}
/* Zoll und Netto je Zollregime, Schlachtkörperäquivalent im Mercosur-Kontingent (null, wenn es für eine Position nicht
   bekannt ist) und Vergleich mit/ohne Mercosur-Kontingent für Ursprung Mercosur außerhalb von Hilton */
function ci_kalk_kontingente(array $e, array $pos, array $tab): array
{
    $zoll = $kg = $ske = [];
    $vergleich = ['kg' => 0.0, 'mitQuote' => 0.0, 'ohneQuote' => 0.0, 'positionen' => 0];
    foreach ($e['positionen'] as $i => $p) {
        $regime = $p['regime'];
        $zoll[$regime] = ($zoll[$regime] ?? 0.0) + $pos[$i]['zoll'];
        $kg[$regime] = ($kg[$regime] ?? 0.0) + $p['netto'];
        if ($regime === 'mercosur') $ske[] = $pos[$i]['ske'];
        $drittland = ci_kalk_drittland_satz($p['kn'], $tab);
        if (!in_array($regime, ['mercosur', 'drittland'], true) || !in_array($p['land'], CI_KALK_MERCOSUR, true) || $drittland === null) continue;
        $vergleich['kg'] += $p['netto'];
        $vergleich['positionen']++;
        $vergleich['mitQuote'] += ci_kalk_zoll_kg($pos[$i]['zollwertKg'], $tab['mercosur']) * $p['netto'];
        $vergleich['ohneQuote'] += ci_kalk_zoll_kg($pos[$i]['zollwertKg'], $drittland) * $p['netto'];
    }
    $vergleich['ersparnis'] = $vergleich['ohneQuote'] - $vergleich['mitQuote'];
    return ['zollJeRegime' => $zoll, 'kgJeRegime' => $kg, 'mercosurSke' => in_array(null, $ske, true) ? null : array_sum($ske),
        'vergleich' => $vergleich['positionen'] ? $vergleich : null];
}
/* Anteilig Hilton: Artikel (Schreibweise egal) in mehr als einem Zollregime, mit kg je Regime und Anteil im Hilton-Kontingent */
function ci_kalk_anteilig(array $positionen): array
{
    $artikel = [];
    foreach ($positionen as $p) {
        $a = mb_strtolower(trim($p['artikel']));
        $artikel[$a]['artikel'] ??= $p['artikel'];
        $artikel[$a]['regime'][$p['regime']] = ($artikel[$a]['regime'][$p['regime']] ?? 0.0) + $p['netto'];
    }
    $mehrere = array_filter($artikel, fn($a) => count($a['regime']) > 1);
    return array_values(array_map(fn($a) => $a + ['anteilHilton' => ci_kalk_teilen($a['regime']['hilton'] ?? 0.0, array_sum($a['regime']))], $mehrere));
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
    eudr_rev_pruefen(['rev' => $rev], $alt ?? [], 'Die Kalkulation');
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

/* Letzte Fassung endgültig festschreiben (GR-106): die Fassung hält dann ihre geprüfte Eingabe (Felder späterer Versionen
   mit ihrer Vorgabe), ihr Ergebnis (darin die wirksamen Sätze, ergebnis.saetze) und unter endgueltig wer, wann und den
   Container. Nur ein vollständiges Ergebnis lässt sich festschreiben. Liefert [Dokument, Kalkulation]. */
function ci_kalk_festschreiben(array $doc, string $sendung, int $rev, array $container, array $me): array
{
    [$i, $k] = ci_kalk_holen($doc, $sendung);
    if (!$k) fail('Für diesen Container gibt es noch keine Kalkulation.', 404);
    eudr_rev_pruefen(['rev' => $rev], $k, 'Die Kalkulation');
    $n = count($k['fassungen']) - 1;
    $f = $k['fassungen'][$n];
    if ($f['stand'] !== 'entwurf') fail('Diese Fassung ist bereits endgültig.', 409);
    $eingabe = ci_kalkulation_eingabe($f['eingabe']);
    $ergebnis = ci_kalkulation_rechnen($eingabe, CI_KALK_SAETZE);
    if (!$ergebnis['vollstaendig']) throw new InvalidArgumentException('Die Kalkulation ist unvollständig: ' . implode(' ', array_column(array_filter($ergebnis['hinweise'], fn($h) => $h['stufe'] === 'fehler'), 'text')));
    $k['fassungen'][$n] = ['stand' => 'endgueltig', 'eingabe' => $eingabe, 'ergebnis' => $ergebnis, 'endgueltig' => ['wer' => eudr_wer($me), 'container' => $container]] + $f;
    $k['rev']++;
    $doc['liste'][$i] = $k;
    return [$doc, $k];
}

/* Kalkulation für die Seite: je Fassung Eingabe und Ergebnis (mit den wirksamen Sätzen) – ein Entwurf frisch gerechnet mit
   den aktuellen Sätzen, eine endgültige Fassung genau so, wie sie festgeschrieben wurde. */
function ci_kalk_sicht(array $k): array
{
    $k['fassungen'] = array_map(function (array $f) {
        if ($f['stand'] === 'endgueltig') return $f + ['ergebnis' => $f['endgueltig']['ergebnis'] ?? null];   // ?? : Probestände vor dem Merge hielten es unter endgueltig
        try {
            $f['eingabe'] = ci_kalkulation_eingabe($f['eingabe']);   // ältere Einträge bekommen neue Felder mit ihrer Vorgabe (GR-006)
            return ['ergebnis' => ci_kalkulation_rechnen($f['eingabe'], CI_KALK_SAETZE)] + $f;
        } catch (InvalidArgumentException $e) {
            return ['ergebnis' => ['vollstaendig' => false, 'hinweise' => [ci_kalk_hinweis('fehler', $e->getMessage())], 'saetze' => CI_KALK_SAETZE]] + $f;
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
