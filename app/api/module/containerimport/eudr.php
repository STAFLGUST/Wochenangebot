<?php
declare(strict_types=1);
/* Container-Import: Container (ein Einkauf bei einem Lieferanten, eine Partienummer) mit ihren Farmern und der Prüfung nach
   der EUDR (Verordnung (EU) 2023/1115, entwaldungsfreie Lieferketten): Geolokalisierung, Risikoprofil und GeoJSON-Datei für
   das EU-Informationssystem (TRACES).
   Begriffe (Entscheidung des Inhabers 19.11.2026): die Oberfläche sagt „Container“ und „Farmer“. Im Code, in den Namen der
   Aktionen und in den gespeicherten Daten heißen sie weiter „sendung“ und „betrieb“ – so bleiben bestehende Daten lesbar
   und ein Rückfall auf die Vorversion möglich (GR-006).
   Dokumente: containerimport-eudr-betriebe (Farmer: Produktionsorte, Umriss in WGS84), containerimport-eudr-sendungen
   (Container mit Lieferant aus den Stammdaten, Partie-, Akten- und Containernummer, Stand, ihren Farmern, Nachweisen und –
   nach dem Abschluss – einem Schnappschuss von Profil und Farmern, GR-106).
   Nichts wird gelöscht: Farmer und Container werden archiviert, Gegenprüfungen nur ergänzt.
   Farmer-Nummern (eigene Nummer, Nummer aus den Papieren, vermerkte Nummern am Container, Gesamtprüfung): farmer.php.
   Abgeleitete Werte (Fläche, Mittelpunkt, Befunde, Risikoprofil) werden bei jedem Lesen neu berechnet und nie gespeichert –
   ausgenommen der Schnappschuss einer abgeschlossenen Bewertung. Geometrie: geometrie.php. 
   Vorsilben: eudr_ tragen die Funktionen aus der Zeit, als das Modul nur den Reiter EUDR hatte (auch allgemeine Helfer wie
   eudr_text oder eudr_liste); neue Funktionen, die nicht zur EUDR gehören, heißen ci_ (Container-Import). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar
require __DIR__ . '/schlachthoefe.php';   // Schlachthöfe unter dem Lieferanten (eigene Datei, gleiche Helfer)
require __DIR__ . '/tracking.php';        // Reiter Tracking: Schiff, Reederei, Häfen, Abfahrt und Ankunft am Container
require __DIR__ . '/hafen.php';           // Tracking: Ankunft in Hamburg aus der öffentlichen Liste des Hafens
require __DIR__ . '/farmer.php';          // Farmer-Nummern am Container und Gesamtprüfung der Farmer
require __DIR__ . '/dokumente.php';       // Dokumente je Container (Dateiablage, GoBD)

const EUDR_SPERRE = 'containerimport-eudr-betriebe';   // eine Sperre für beide Dokumente (Sendungen verweisen auf Betriebe)
const EUDR_MAX_BETRIEBE = 2000;
const EUDR_MAX_PUNKTE = 150000;          // Punkte aller Betriebe zusammen: jede Antwort rechnet und liefert alle Umrisse (Speichergrenze 128 MB)
const EUDR_MAX_PUNKTE_ANFRAGE = 100000;  // Punkte aller Flächen einer Prüfung
/* Punkte aller Umrisse in den Schnappschüssen des Container-Dokuments (Abschlüsse und frühere Abschlüsse zusammen). Jede
   Aktion des Moduls liest das ganze Dokument, ohne Grenze brach store_read ab rund 400 000 Punkten mit einem Speicherfehler ab
   (HTTP 500 für das ganze Modul). Gemessen im Dateibetrieb mit memory_limit = 128M und allen Bibliotheken: 100 000 Punkte sind
   rund 2,8 MiB Dokument und 31 MiB Speicher; mit Farmern an EUDR_MAX_PUNKTE braucht eine Antwort (auch der Abschluss) 86 von 128 MiB. */
const EUDR_MAX_PUNKTE_SCHNAPPSCHUESSE = 100000;
const EUDR_MAX_FRUEHERE = 5;             // frühere Abschlüsse je Sendung, die ihren Schnappschuss behalten
const EUDR_MAX_SENDUNGEN = 5000;
const EUDR_MAX_ORTE_JE_DATEI = 1000;
const EUDR_MAX_PRUEFUNGEN = 50;          // Gegenprüfungen je Betrieb
const EUDR_BEFUNDE_FASSUNG = 1;          // Fassung von geo_pruefen; hochzählen, sobald die Prüfung andere Befunde liefert – dann rechnet der Zwischenspeicher neu
/* Stand eines Containers auf seinem Weg (Reihenfolge = Ablauf); wird von Hand gesetzt, auch nach dem Abschluss der Bewertung */
const EUDR_STAENDE = ['gekauft' => 'gekauft', 'unterwegs' => 'unterwegs', 'dokumente' => 'Dokumente da', 'angekommen' => 'angekommen'];
/* Felder, die älteren Einträgen fehlen (vor dem Container als Mittelpunkt, vor den Schlachthöfen) – eudr_sendungen ergänzt sie beim Lesen */
const EUDR_SENDUNG_VORGABEN = ['partie' => '', 'akte' => '', 'lieferantNr' => '', 'stand' => 'gekauft', 'schlachthof' => '', 'schlachthofName' => '', 'offeneNummern' => []];
const EUDR_NACHWEIS = ['konform', 'nicht_konform', 'unbekannt'];
const EUDR_DREI = ['ja', 'nein', 'offen'];
const EUDR_QUELLEN = ['bericht', 'geojson', 'koordinaten'];
const EUDR_QM_ORDNER = 'EUDR';              // Ordner im Eingang des QM-Systems für die Originale der Lieferantenunterlagen
const EUDR_FLAECHE_TOLERANZ = 0.05;      // Abweichung berechnete ↔ angegebene Fläche, ab der ein Hinweis erscheint
const EUDR_BERICHT_MONATE = 12;          // älter darf ein Entwaldungsbericht bei der Schlachtung nicht sein

/* Einstufung der Herkunftsländer (Art. 29; Durchführungsverordnung (EU) 2025/1093) und grober Rahmen [West, Süd, Ost, Nord]
   für die Lageprüfung. Eine Klasse steht nur dort, wo die Einstufung belegt ist; Länder ohne Klasse (null) sind wählbar, das Profil meldet sie wie
   alle nicht genannten als „nachsehen“. */
const EUDR_LAENDER_STAND = 'Durchführungsverordnung (EU) 2025/1093';
const EUDR_LAENDER = [
    'PY' => ['name' => 'Paraguay', 'klasse' => 'standard', 'rahmen' => [-62.7, -27.7, -54.2, -19.2]],
    'AR' => ['name' => 'Argentinien', 'klasse' => 'standard', 'rahmen' => [-73.6, -55.2, -53.6, -21.7]],
    'BR' => ['name' => 'Brasilien', 'klasse' => 'standard', 'rahmen' => [-74.0, -33.8, -34.7, 5.3]],
    'BO' => ['name' => 'Bolivien', 'klasse' => 'standard', 'rahmen' => [-69.7, -22.9, -57.4, -9.6]],
    'CO' => ['name' => 'Kolumbien', 'klasse' => 'standard'],
    'EC' => ['name' => 'Ecuador', 'klasse' => 'standard'],
    'PE' => ['name' => 'Peru', 'klasse' => 'standard'],
    'MX' => ['name' => 'Mexiko', 'klasse' => 'standard'],
    'UY' => ['name' => 'Uruguay', 'klasse' => null, 'rahmen' => [-58.5, -35.0, -53.0, -30.0]],
    'NZ' => ['name' => 'Neuseeland', 'klasse' => null],
    'BY' => ['name' => 'Belarus', 'klasse' => 'hoch'],
    'KP' => ['name' => 'Nordkorea', 'klasse' => 'hoch'],
    'MM' => ['name' => 'Myanmar', 'klasse' => 'hoch'],
    'RU' => ['name' => 'Russland', 'klasse' => 'hoch'],
];

/* Portale für die eigene Gegenprüfung der Entwaldung (unabhängig vom Bericht des Lieferanten) */
const EUDR_PORTALE = [
    'gnw' => ['name' => 'Global Nature Watch', 'url' => 'https://www.globalnaturewatch.org/', 'hinweis' => 'Fläche als GeoJSON hochladen; Baumverlust seit 2021 und Warnmeldungen ansehen.'],
    'whisp' => ['name' => 'Whisp (FAO)', 'url' => 'https://whisp.openforis.org/', 'hinweis' => 'GeoJSON hochladen; für Rinder gibt Whisp noch kein eigenes Risiko aus – Baumbestand 2020 und Störungen nach 2020 ansehen.'],
    'sonst' => ['name' => 'Andere Quelle', 'url' => '', 'hinweis' => ''],
];

/* ---------- Speicher ---------- */
/* Inhalt eines Dokuments als ['rev', 'liste'] (fehlt es, leer) */
function eudr_liste($d): array
{
    return ['rev' => (int)($d['rev'] ?? 0), 'liste' => is_array($d['liste'] ?? null) ? array_values($d['liste']) : []];
}
/* Dokument für das Schreiben fortschreiben: Revision erhöhen, Zeitstempel setzen */
function eudr_fortschreiben(array $doc): array
{
    return ['rev' => (int)($doc['rev'] ?? 0) + 1, 'updatedAt' => now()] + $doc;
}
/* Dokument der Herkunftsbetriebe mit der eigenen Farmer-Nummer „nr“ = Stelle + 1. Annahme: die Liste wächst nur am Ende,
   nichts wird gelöscht oder umsortiert (archivieren) – so bleibt die Nummer fest. Nie gespeichert (eudr_betriebe_schreiben). */
function eudr_betriebe(): array
{
    $doc = eudr_liste(store_read('containerimport-eudr-betriebe'));
    foreach ($doc['liste'] as $i => $b) $doc['liste'][$i]['nr'] = $i + 1;
    return $doc;
}
/* Dokument der Sendungen */
function eudr_sendungen(): array
{
    $doc = eudr_liste(store_read('containerimport-eudr-sendungen'));
    $doc['liste'] = array_map(fn($s) => $s + EUDR_SENDUNG_VORGABEN + CI_TRACKING_VORGABEN, $doc['liste']);
    return $doc;
}
/* Herkunftsbetriebe speichern. Dabei den Zwischenspeicher der Befunde auffrischen (eudr_geo_befunde): gerechnet wird beim
   Schreiben, nicht in jeder Antwort des Moduls. */
function eudr_betriebe_schreiben(array $doc): void
{
    $doc['liste'] = array_map(function (array $b): array {
        $b = array_diff_key($b, ['nr' => 1]);   // abgeleitet (eudr_betriebe)
        $kennung = eudr_geo_kennung($b['geometrie']);
        if (($b['geoBefunde']['kennung'] ?? '') !== $kennung || ($b['geoBefunde']['fassung'] ?? 0) !== EUDR_BEFUNDE_FASSUNG) {
            $b['geoBefunde'] = ['fassung' => EUDR_BEFUNDE_FASSUNG, 'kennung' => $kennung, 'befunde' => geo_pruefen($b['geometrie'])];
        }
        return $b;
    }, $doc['liste']);
    store_write('containerimport-eudr-betriebe', eudr_fortschreiben($doc));
}
/* Sendungen speichern */
function eudr_sendungen_schreiben(array $doc): void { store_write('containerimport-eudr-sendungen', eudr_fortschreiben($doc)); }
/* Neue Kennung mit Vorsilbe (b = Betrieb, s = Sendung) */
function eudr_id(string $praefix): string { return $praefix . bin2hex(random_bytes(6)); }
/* Stempel „wann und von wem“ */
function eudr_wer(array $me): array { return ['t' => now(), 'von' => (string)$me['name']]; }
/* Stelle eines Eintrags in einer Liste nach seiner id (null = nicht vorhanden) */
function eudr_stelle(array $liste, string $id): ?int
{
    foreach ($liste as $i => $e) if (($e['id'] ?? '') === $id) return $i;
    return null;
}
/* Eintrag eines Dokuments nach id samt seiner Stelle (404 mit $fehlt): Container, Dateien am Container */
function eudr_holen(array $doc, $id, string $fehlt = 'Container nicht gefunden.'): array
{
    $i = eudr_stelle($doc['liste'], is_string($id) ? $id : '');
    if ($i === null) fail($fehlt, 404);
    return [$i, $doc['liste'][$i]];
}
/* Stand, den der Bearbeiter gesehen hat, mit dem gespeicherten vergleichen (409, wenn inzwischen jemand gespeichert hat) */
function eudr_rev_pruefen(array $eingabe, array $alt, string $was): void
{
    if ((int)($eingabe['rev'] ?? 0) !== (int)($alt['rev'] ?? 0)) fail("$was wurde inzwischen von jemand anderem geändert. Bitte neu laden und erneut prüfen.", 409);
}

/* ---------- Prüfen der Eingaben ---------- */
/* Text ohne Steuerzeichen, höchstens $max Zeichen; $pflicht = darf nicht leer sein */
function eudr_text($v, int $max, string $was, bool $pflicht = false): string
{
    if ($v !== null && !is_string($v) && !is_int($v) && !is_float($v)) throw new InvalidArgumentException("$was: ungültiger Wert.");
    $t = trim(preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', str_replace("\r", '', (string)$v)) ?? '');
    if (mb_strlen($t) > $max) throw new InvalidArgumentException("$was: höchstens $max Zeichen.");
    if ($pflicht && $t === '') throw new InvalidArgumentException("$was: bitte ausfüllen.");
    return $t;
}
/* Datum JJJJ-MM-TT oder leer; $bisHeute = ein Datum in der Zukunft ist ein Eingabefehler */
function eudr_datum($v, string $was, bool $bisHeute = false): string
{
    $v = is_string($v) ? trim($v) : '';
    if ($v === '') return '';
    if (!preg_match('/^(\d{4})-(\d{2})-(\d{2})$/', $v, $m) || !checkdate((int)$m[2], (int)$m[3], (int)$m[1]) || (int)$m[1] < 2000 || (int)$m[1] > 2099)
        throw new InvalidArgumentException("$was: bitte ein gültiges Datum angeben.");
    if ($bisHeute && $v > date('Y-m-d')) throw new InvalidArgumentException("$was: liegt in der Zukunft.");
    return $v;
}
/* Einer der erlaubten Werte; leer ergibt den Standard, wenn einer genannt ist */
function eudr_wahl($v, array $erlaubt, string $was, ?string $standard = null): string
{
    if (($v === null || $v === '') && $standard !== null) return $standard;
    if (!is_string($v) || !in_array($v, $erlaubt, true)) throw new InvalidArgumentException("$was: ungültige Auswahl.");
    return $v;
}
/* Zahl ab 0 oder null (leer); Text auch in deutscher Schreibweise („1.234,5“) */
function eudr_zahl($v, string $was): ?float
{
    $v = eudr_zahl_text($v);
    if ($v === null) return null;
    if (is_bool($v) || !is_numeric($v) || (float)$v < 0 || (float)$v > 1e9) throw new InvalidArgumentException("$was: bitte eine Zahl ab 0 angeben.");
    return round((float)$v, 3);
}
/* Eingabe einer Zahl lesbar für is_numeric: deutscher Text „1.234,5“ → „1234.5“, „0,5“ → „0.5“; Punkte gelten nur in
   Dreiergruppen nach einer Ziffer 1–9 als Tausendertrenner („0.500“ bleibt 0,5). Leer → null, keine Zeichenkette → unverändert. */
function eudr_zahl_text($v)
{
    if (!is_string($v)) return $v;
    if ($v === '') return null;
    $v = str_replace([' ', "\u{a0}"], '', trim($v));
    if (preg_match('/^[1-9]\d{0,2}(\.\d{3})+(,\d+)?$/', $v)) $v = str_replace('.', '', $v);
    return str_replace(',', '.', $v);
}
/* Zweistelliger Ländercode in Großbuchstaben */
function eudr_land($v): string
{
    $v = is_string($v) ? strtoupper(trim($v)) : '';
    if (!preg_match('/^[A-Z]{2}$/', $v)) throw new InvalidArgumentException('Land: bitte den zweistelligen Ländercode angeben (z. B. PY).');
    return $v;
}

/* ---------- Betriebe (Produktionsorte) ---------- */
/* Geometrie eines Betriebs aus der Eingabe: fertige GeoJSON-Geometrie in WGS84 oder Punktliste mit Bezugssystem
   („utm“ mit Zone und Halbkugel bzw. „wgs84“). Liefert wie geo_lesen ['geometrie', 'korrekturen'] oder ['fehler']. */
function eudr_geometrie_aus(array $b): array
{
    if (isset($b['geometrie'])) return geo_lesen($b['geometrie']);
    $k = is_array($b['koordinaten'] ?? null) ? $b['koordinaten'] : [];
    $punkte = is_array($k['punkte'] ?? null) && array_is_list($k['punkte']) ? $k['punkte'] : [];
    if (count($punkte) > GEO_MAX_PUNKTE) return ['fehler' => 'Mehr als ' . GEO_MAX_PUNKTE . ' Punkte in einem Produktionsort.'];
    foreach ($punkte as $p) if (!geo_position($p)) return ['fehler' => 'Die Koordinatenliste enthält einen Punkt ohne zwei Zahlen.'];
    if (!$punkte) return ['fehler' => 'Keine Koordinaten gefunden.'];
    if (($k['system'] ?? '') === 'utm') {
        $zone = $k['zone'] ?? null;
        if (!is_int($zone) || $zone < 1 || $zone > 60) return ['fehler' => 'UTM-Zone fehlt oder ist ungültig (1–60).'];
        $sued = !empty($k['sued']);
        $punkte = array_map(fn($p) => geo_utm_nach_wgs84((float)$p[0], (float)$p[1], $zone, $sued), $punkte);
    } elseif (($k['system'] ?? '') !== 'wgs84') {
        return ['fehler' => 'Bezugssystem der Koordinaten fehlt (UTM oder WGS84).'];
    }
    return geo_lesen(count($punkte) === 1 ? ['type' => 'Point', 'coordinates' => $punkte[0]] : ['type' => 'Polygon', 'coordinates' => [$punkte]]);
}

/* Felder eines Betriebs aus der Eingabe prüfen (ohne id, rev, Zeitstempel und Gegenprüfungen). $alt = gespeicherter Stand
   beim Ändern – eine Regel für alle Felder: Was die Eingabe nicht nennt, bleibt, wie es gespeichert ist (auch einzelne
   Angaben des Berichts). So überschreibt erneutes Einlesen einer Datei nichts, was die Datei nicht kennt.
   Wirft InvalidArgumentException (422). */
function eudr_betrieb_pruefen(array $b, ?array $alt): array
{
    if (isset($b['geometrie']) || isset($b['koordinaten']) || !$alt) {
        $g = eudr_geometrie_aus($b);
        if (isset($g['fehler'])) throw new InvalidArgumentException('Geolokalisierung: ' . $g['fehler']);
    } else {
        $g = ['geometrie' => $alt['geometrie'], 'korrekturen' => []];
    }
    $n = (is_array($b['bericht'] ?? null) ? $b['bericht'] : []) + ($alt['bericht'] ?? []);
    $b += $alt ?? [];
    $q = is_array($b['quelle'] ?? null) ? $b['quelle'] : [];
    $sha = is_string($q['sha256'] ?? null) && preg_match('/^[0-9a-f]{64}$/', $q['sha256']) ? $q['sha256'] : '';
    $korrekturen = array_merge(array_intersect(array_keys(GEO_KORREKTUREN), is_array($q['korrekturen'] ?? null) ? $q['korrekturen'] : []), $g['korrekturen']);
    $nachweis = fn(string $feld, string $was): string => eudr_wahl($n[$feld] ?? null, EUDR_NACHWEIS, $was, 'unbekannt');
    $jahr = $n['bilderBis'] ?? null;
    return [
        'name' => eudr_text($b['name'] ?? '', 120, 'Name des Farmers', true),
        'erzeuger' => eudr_text($b['erzeuger'] ?? '', 120, 'Erzeuger'),
        'land' => eudr_land($b['land'] ?? ''),
        'kennung' => eudr_text($b['kennung'] ?? '', 40, 'Kennung'),
        'region' => eudr_text($b['region'] ?? '', 80, 'Region'),
        'ort' => eudr_text($b['ort'] ?? '', 80, 'Ort'),
        'flaecheAngabe' => eudr_zahl($b['flaecheAngabe'] ?? null, 'Angegebene Fläche'),
        'geometrie' => $g['geometrie'],
        'quelle' => [
            'art' => eudr_wahl($q['art'] ?? null, EUDR_QUELLEN, 'Quelle', 'koordinaten'),
            'datei' => eudr_text($q['datei'] ?? '', 200, 'Dateiname'),
            'sha256' => $sha,
            'lieferant' => eudr_text($q['lieferant'] ?? '', 120, 'Lieferant'),
            'anbieter' => eudr_text($q['anbieter'] ?? '', 120, 'Ersteller des Berichts'),
            'bezug' => eudr_text($q['bezug'] ?? '', 40, 'Bezugssystem'),
            'korrekturen' => array_values(array_unique($korrekturen)),
            // Ablage des Originals im QM-System: setzt nur der Server (eudr_original_vermerken), gilt für genau diese Datei
            'qm' => $sha !== '' && $sha === ($alt['quelle']['sha256'] ?? '') ? ($alt['quelle']['qm'] ?? null) : null,
        ],
        'bericht' => [
            'datum' => eudr_datum($n['datum'] ?? '', 'Datum der Analyse', true),
            'entwaldung' => $nachweis('entwaldung', 'Entwaldung'),
            'entwaldungHa' => eudr_zahl($n['entwaldungHa'] ?? null, 'Entwaldete Fläche'),
            'schutzgebiet' => $nachweis('schutzgebiet', 'Schutzgebiete'),
            'indigen' => $nachweis('indigen', 'Indigene Gebiete'),
            'landnutzung' => $nachweis('landnutzung', 'Landnutzungsplan'),
            'umwelt' => $nachweis('umwelt', 'Umweltgenehmigung'),
            'bilderBis' => is_int($jahr) && $jahr >= 2015 && $jahr <= 2099 ? $jahr : null,
        ],
        'notiz' => eudr_text($b['notiz'] ?? '', 2000, 'Notiz'),
        'aktiv' => (bool)($b['aktiv'] ?? true),
    ];
}

/* An allen Betrieben, die aus der Datei mit dieser Prüfsumme stammen, vermerken, wo ihr Original im QM-System liegt
   ($ablage = Antwort von qs_eingang_hochladen). Liefert die geänderte Liste und die Zahl der Betriebe. */
function eudr_original_vermerken(array $liste, array $ablage, array $me): array
{
    $n = 0;
    foreach ($liste as $i => $b) {
        if (($b['quelle']['sha256'] ?? '') !== $ablage['sha256']) continue;
        $liste[$i]['quelle']['qm'] = ['status' => $ablage['status'], 'datei' => (string)($ablage['datei'] ?? ''), 'name' => $ablage['name'], 'pfad' => $ablage['pfad']] + eudr_wer($me);
        $liste[$i]['rev']++;
        $n++;
    }
    return [$liste, $n];
}

/* Kennung der Geometrie zum Wiedererkennen derselben Fläche */
function eudr_geo_kennung(array $g): string { return sha1((string)json_encode($g['coordinates'])); }

/* Befunde des Umrisses eines Betriebs. Zwischengespeichert im additiven Feld „geoBefunde“ (Fassung der Prüfung, Kennung der
   Geometrie, Befunde) – ohne das Feld wird gerechnet, ältere Daten bleiben also lesbar (GR-006). Warum: eudr_stand() bildet
   eudr_betrieb_sicht über ALLE gespeicherten Farmer ab und läuft in jeder Antwort des Moduls; die Prüfung auf
   Selbstüberschneidung kostet je Umriss bis zu GEO_MAX_VERGLEICHE Kantenvergleiche. Geschrieben wird der Zwischenspeicher in
   eudr_betriebe_schreiben; er gilt nur für dieselbe Geometrie und dieselbe Fassung, anders Geschnittenes wird verworfen. */
function eudr_geo_befunde(array $b): array
{
    $c = $b['geoBefunde'] ?? null;
    $gut = fn($x): bool => is_array($x) && is_string($x['stufe'] ?? null) && is_string($x['code'] ?? null) && is_string($x['text'] ?? null);
    if (is_array($c) && ($c['fassung'] ?? 0) === EUDR_BEFUNDE_FASSUNG && ($c['kennung'] ?? '') === eudr_geo_kennung($b['geometrie'])
        && is_array($c['befunde'] ?? null) && array_is_list($c['befunde']) && count(array_filter($c['befunde'], $gut)) === count($c['befunde'])) {
        return $c['befunde'];
    }
    return geo_pruefen($b['geometrie']);
}

/* Nachschlagetabelle der gespeicherten Betriebe zum Wiedererkennen (einmal je Anfrage): Nummer aus den Papieren bzw. Umriss → Betrieb */
function eudr_bekannt_tabelle(array $liste): array
{
    $tabelle = [];
    foreach (ci_nummern_index($liste) as $k => $i) $tabelle['k ' . $k] = $liste[$i];
    foreach ($liste as $b) $tabelle['g ' . eudr_geo_kennung($b['geometrie'])] ??= $b;
    return $tabelle;
}
/* Gespeicherter Betrieb, der zu einem eingelesenen passt: gleiche Nummer aus den Papieren im selben Land, sonst dieselbe Geometrie */
function eudr_bekannt(array $neu, array $tabelle): ?array
{
    $k = ci_nummer_schluessel($neu['land'], $neu['kennung']);
    return ($k !== '' ? $tabelle['k ' . $k] ?? null : null) ?? $tabelle['g ' . eudr_geo_kennung($neu['geometrie'])] ?? null;
}

/* Jüngste Gegenprüfung je Portal (nur diese zählt im Risikoprofil) */
function eudr_pruefungen_aktuell(array $b): array
{
    $aus = [];
    foreach ($b['pruefungen'] ?? [] as $p) if (!isset($aus[$p['portal']]) || strcmp($p['datum'], $aus[$p['portal']]['datum']) >= 0) $aus[$p['portal']] = $p;
    return array_values($aus);
}

/* Betrieb für die Oberfläche: gespeicherte Felder plus abgeleitete Kennzahlen und Befunde.
   stand: „fehler“ (Geolokalisierung so nicht einreichbar), „hinweis“ oder „ok“. */
function eudr_betrieb_sicht(array $b): array
{
    $k = geo_kennzahlen($b['geometrie']);
    $befunde = eudr_geo_befunde($b);
    foreach ($b['quelle']['korrekturen'] ?? [] as $korrektur) $befunde[] = ['stufe' => 'hinweis', 'code' => 'korrektur', 'text' => 'Beim Einlesen korrigiert: ' . GEO_KORREKTUREN[$korrektur] . '.'];
    $land = EUDR_LAENDER[$b['land']] ?? null;
    if (isset($land['rahmen'])) {
        [$w, $s, $o, $n] = $land['rahmen'];
        if ($k['mitte'][0] < $w || $k['mitte'][0] > $o || $k['mitte'][1] < $s || $k['mitte'][1] > $n) {
            $befunde[] = ['stufe' => 'fehler', 'code' => 'lage', 'text' => 'Die Fläche liegt nicht in ' . $land['name'] . ' – Länge und Breite vertauscht oder falsches Bezugssystem?'];
        }
    }
    $angabe = $b['flaecheAngabe'];
    if ($k['flaeche'] !== null && $angabe && abs($k['flaeche'] - $angabe) / $angabe > EUDR_FLAECHE_TOLERANZ) {
        $befunde[] = ['stufe' => 'hinweis', 'code' => 'flaeche', 'text' => 'Die berechnete Fläche weicht um mehr als ' . (int)(EUDR_FLAECHE_TOLERANZ * 100) . ' % von der angegebenen ab.'];
    }
    $stufen = array_column($befunde, 'stufe');
    $stand = in_array('fehler', $stufen, true) ? 'fehler' : ($stufen ? 'hinweis' : 'ok');
    $bewertung = eudr_betrieb_bewertung($b, $stand);
    return array_diff_key($b, ['geoBefunde' => 1]) + [   // der Zwischenspeicher der Befunde bleibt auf dem Server
        'farmerNr' => isset($b['nr']) ? ci_farmer_nr($b['nr']) : '',   // ohne nr: beim Einlesen ein neuer Farmer, der seine Nummer erst beim Speichern bekommt
        'flaeche' => $k['flaeche'] ?? ($angabe ?: GEO_PUNKT_HA), 'mitte' => $k['mitte'], 'rahmen' => $k['rahmen'], 'punkte' => $k['punkte'],
        'befunde' => $befunde, 'stand' => $stand, 'bewertung' => $bewertung, 'pruefungenAktuell' => eudr_pruefungen_aktuell($b),
        'ampel' => in_array('kritisch', $bewertung, true) ? 'rot' : (in_array('offen', $bewertung, true) ? 'gelb' : 'gruen'),
    ];
}

/* Bewertung eines Betriebs je Thema (ok | offen | kritisch): das Risikoprofil der Sendung und die Farbe auf der Karte
   lesen sie hier ab. Was erst mit der Sendung zu beurteilen ist (Alter des Berichts und Ende der Satellitenbilder gegen den
   Schlachttag, weitere Nachweise zur Legalität), steht bei den Kriterien (eudr_kriterien).
   $geoStand = Stand der Geolokalisierung (eudr_betrieb_sicht). */
function eudr_betrieb_bewertung(array $b, string $geoStand): array
{
    $n = $b['bericht']; $pruefungen = eudr_pruefungen_aktuell($b); $gebiete = [$n['schutzgebiet'], $n['indigen']]; $recht = [$n['landnutzung'], $n['umwelt']];
    $stufe = fn(bool $kritisch, bool $offen): string => $kritisch ? 'kritisch' : ($offen ? 'offen' : 'ok');
    return [
        'geo' => $stufe($geoStand === 'fehler', false),
        'entwaldung' => $stufe($n['entwaldung'] === 'nicht_konform' || ($n['entwaldungHa'] ?? 0) > 0, $n['entwaldung'] === 'unbekannt'),
        'gegenpruefung' => $stufe((bool)array_filter($pruefungen, fn($p) => $p['ergebnis'] === 'befund' || ($p['verlustHa'] ?? 0) > 0), !$pruefungen),
        'gebiete' => $stufe(in_array('nicht_konform', $gebiete, true), in_array('unbekannt', $gebiete, true)),
        'legalitaet' => $stufe(in_array('nicht_konform', $recht, true), in_array('unbekannt', $recht, true)),
    ];
}

/* Eine Gegenprüfung aus der Eingabe prüfen */
function eudr_pruefung_pruefen(array $b, array $me): array
{
    $datum = eudr_datum($b['datum'] ?? '', 'Datum der Prüfung', true);
    if ($datum === '') throw new InvalidArgumentException('Datum der Prüfung: bitte angeben.');
    return [
        'portal' => eudr_wahl($b['portal'] ?? null, array_keys(EUDR_PORTALE), 'Portal'),
        'datum' => $datum,
        'ergebnis' => eudr_wahl($b['ergebnis'] ?? null, ['ohne_befund', 'befund'], 'Ergebnis'),
        'verlustHa' => eudr_zahl($b['verlustHa'] ?? null, 'Baumverlust seit 2021'),
        'bemerkung' => eudr_text($b['bemerkung'] ?? '', 500, 'Bemerkung'),
    ] + eudr_wer($me);
}

/* ---------- Dateien einlesen ---------- */
/* Eigenschaft eines GeoJSON-Features lesen. Das EU-Informationssystem unterscheidet Groß- und Kleinschreibung –
   abweichend geschriebene Namen werden gelesen und in $falsch gemeldet. */
function eudr_eigenschaft(array $eigenschaften, string $name, array &$falsch)
{
    if (array_key_exists($name, $eigenschaften)) return $eigenschaften[$name];
    foreach ($eigenschaften as $k => $v) if (strcasecmp((string)$k, $name) === 0 || strcasecmp(str_replace('_', '', (string)$k), $name) === 0) { $falsch[(string)$k] = $name; return $v; }
    return null;
}

/* Lieferanten-GeoJSON lesen: je Feature ein Produktionsort (MultiPoint wird in Punkte zerlegt).
   Liefert ['orte' => [Eingaben für eudr_betrieb_pruefen], 'fehler' => [...], 'hinweise' => [...]]. */
function eudr_geojson_lesen(string $text, string $datei): array
{
    $aus = ['orte' => [], 'fehler' => [], 'hinweise' => []];
    try { $d = json_decode($text, true, 64, JSON_THROW_ON_ERROR); } catch (JsonException $e) { $d = null; }
    if (!is_array($d)) { $aus['fehler'][] = 'Die Datei ist kein gültiges JSON (Syntaxfehler, z. B. fehlende Klammer).'; return $aus; }
    $art = $d['type'] ?? null;
    $features = $art === 'FeatureCollection' && is_array($d['features'] ?? null) ? array_values($d['features'])
        : ($art === 'Feature' ? [$d] : (isset($d['coordinates']) ? [['type' => 'Feature', 'properties' => [], 'geometry' => $d]] : null));
    if ($features === null) { $aus['fehler'][] = 'Kein GeoJSON: erwartet wird eine „FeatureCollection“ mit „features“.'; return $aus; }
    if (!$features) { $aus['fehler'][] = 'Die Datei enthält keine Flächen.'; return $aus; }
    if (count($features) > EUDR_MAX_ORTE_JE_DATEI) { $aus['fehler'][] = 'Mehr als ' . EUDR_MAX_ORTE_JE_DATEI . ' Flächen in einer Datei – bitte teilen.'; return $aus; }
    $falsch = [];
    foreach ($features as $i => $f) {
        $nr = $i + 1;
        $g = is_array($f) && is_array($f['geometry'] ?? null) ? $f['geometry'] : null;
        if (!$g) { $aus['fehler'][] = "Fläche $nr: ohne Geometrie."; continue; }
        $e = is_array($f['properties'] ?? null) ? $f['properties'] : [];
        $name = eudr_eigenschaft($e, 'ProductionPlace', $falsch);
        $erzeuger = eudr_eigenschaft($e, 'ProducerName', $falsch);
        $code = eudr_eigenschaft($e, 'ProducerCountry', $falsch);
        $ha = eudr_eigenschaft($e, 'Area', $falsch);
        if (is_string($ha)) { $aus['hinweise'][] = "Fläche $nr: „Area“ steht in Anführungszeichen – das EU-Informationssystem liest dann 0 Hektar. Beim Export wird eine Zahl geschrieben."; }
        $teile = ($g['type'] ?? '') === 'MultiPoint' && is_array($g['coordinates'] ?? null)
            ? array_map(fn($p) => ['type' => 'Point', 'coordinates' => $p], array_values($g['coordinates'])) : [$g];
        foreach ($teile as $t => $teil) {
            $aus['orte'][] = [
                'name' => is_string($name) ? mb_substr(trim($name), 0, 120) : '',
                'nameErsatz' => 'Fläche ' . $nr . (count($teile) > 1 ? '.' . ($t + 1) : '') . ' aus ' . mb_substr($datei, 0, 80),
                'erzeuger' => is_string($erzeuger) ? mb_substr(trim($erzeuger), 0, 120) : '',
                'land' => is_string($code) && preg_match('/^[A-Za-z]{2}$/', trim($code)) ? strtoupper(trim($code)) : '',
                'flaecheAngabe' => is_numeric($ha) && (float)$ha > 0 ? (float)$ha : null,
                'geometrie' => $teil,
            ];
        }
    }
    foreach ($falsch as $ist => $soll) $aus['hinweise'][] = "Eigenschaft „{$ist}“ ist anders geschrieben als vorgeschrieben („{$soll}“) – das EU-Informationssystem würde sie übergehen. Beim Export wird sie richtig geschrieben.";
    return $aus;
}

/* Eine hochgeladene Datei prüfen, ohne zu speichern: Lieferanten-GeoJSON („text“) oder ein vom Browser gelesener
   Produktionsort („ort“: Bericht oder eingefügte Koordinaten). Liefert die Orte so, wie sie gespeichert würden, mit
   Kennzahlen und Befunden ($bekannt = eudr_bekannt_tabelle der gespeicherten Betriebe), ob es den Betrieb schon gibt („bekannt“ = id – dann zusammengeführt mit dem gespeicherten Stand)
   und als „eingabe“ genau das, was beim Übernehmen an containerimport_eudr_betriebe_save geht.
   $punkte zählt die Punkte aller Orte des ganzen Durchgangs (über alle Dateien) mit und bricht mit 422 ab, sobald
   EUDR_MAX_PUNKTE_ANFRAGE überschritten ist – geprüft wird je Ort vor der Prüfung seines Umrisses, nicht erst, wenn alle
   Dateien durch sind. */
function eudr_datei_pruefen(array $d, array $bekannt, int &$punkte): array
{
    $datei = eudr_text($d['datei'] ?? '', 200, 'Dateiname');
    $land = isset($d['land']) && $d['land'] !== '' ? eudr_land($d['land']) : '';
    $quelle = ['art' => eudr_wahl($d['art'] ?? null, EUDR_QUELLEN, 'Art der Datei'), 'datei' => $datei, 'sha256' => $d['sha256'] ?? '',
        'lieferant' => $d['lieferant'] ?? '', 'anbieter' => $d['anbieter'] ?? '', 'bezug' => $d['bezug'] ?? ''];
    if ($quelle['art'] === 'geojson') {
        if (!is_string($d['text'] ?? null)) throw new InvalidArgumentException('GeoJSON: Inhalt der Datei fehlt.');
        $gelesen = eudr_geojson_lesen($d['text'], $datei);
        $quelle['bezug'] = 'WGS84';
    } else {
        $gelesen = ['orte' => [is_array($d['ort'] ?? null) ? $d['ort'] : []], 'fehler' => [], 'hinweise' => []];
    }
    $aus = ['datei' => $datei, 'art' => $quelle['art'], 'orte' => [], 'fehler' => $gelesen['fehler'], 'hinweise' => $gelesen['hinweise']];
    $leer = fn($v): bool => $v === '' || $v === null;
    foreach ($gelesen['orte'] as $ort) {
        // Nur was die Datei wirklich nennt, geht in die Eingabe – der Rest bleibt bei einem bekannten Betrieb, wie er ist
        $ersatz = $ort['nameErsatz'] ?? 'Betrieb aus ' . ($datei !== '' ? $datei : 'der Koordinatenliste');
        if (is_array($ort['bericht'] ?? null)) $ort['bericht'] = array_filter($ort['bericht'], fn($v) => !$leer($v));
        $ort = array_filter(array_diff_key($ort, ['nameErsatz' => 1]), fn($v) => !$leer($v)) + ['land' => $land, 'quelle' => $quelle];
        try {
            if ($ort['land'] === '') throw new InvalidArgumentException('Das Land fehlt – bitte das Herkunftsland wählen.');
            $b = eudr_betrieb_pruefen($ort + ['name' => $ersatz], null);
            $alt = eudr_bekannt($b, $bekannt);
            $eingabe = ['geometrie' => $b['geometrie'], 'quelle' => $b['quelle']] + array_diff_key($ort, ['koordinaten' => 1]) + ($alt ? [] : ['name' => $ersatz]);
            if ($alt) $b = ['nr' => $alt['nr']] + eudr_betrieb_pruefen($eingabe, $alt);
        } catch (InvalidArgumentException $e) {
            $aus['fehler'][] = (is_string($ort['name'] ?? null) ? $ort['name'] . ': ' : '') . $e->getMessage();
            continue;
        }
        // Budget des Durchgangs halten, bevor die teure Prüfung des Umrisses läuft (eudr_betrieb_sicht → geo_pruefen)
        $punkte += geo_punktzahl($b['geometrie']);
        if ($punkte > EUDR_MAX_PUNKTE_ANFRAGE) fail('Zu viele Punkte in einem Durchgang – bitte die Dateien einzeln einlesen.', 422);
        $aus['orte'][] = eudr_betrieb_sicht($b) + ['bekannt' => $alt['id'] ?? '', 'bekanntRev' => $alt['rev'] ?? 0, 'eingabe' => $eingabe];
    }
    return $aus;
}

/* ---------- Sendungen ---------- */
/* Felder einer Sendung aus der Eingabe prüfen (ohne id, rev, Zeitstempel und Abschluss); $betriebe = gespeicherte Farmer.
   Vermerkte Farmer-Nummern („offeneNummern“, ohne Eingabe die gespeicherten) werden jedes Mal neu aufgelöst: Gibt es den
   Farmer inzwischen, wird er zugeordnet und der Vermerk entfällt. */
function eudr_sendung_pruefen(array $b, array $betriebe, ?array $alt): array
{
    $ids = is_array($b['betriebe'] ?? null) ? array_values(array_unique(array_filter($b['betriebe'], 'is_string'))) : [];
    $betriebIds = array_column($betriebe, 'id');
    foreach ($ids as $id) if (!in_array($id, $betriebIds, true)) throw new InvalidArgumentException('Ein gewählter Farmer ist nicht (mehr) vorhanden. Bitte neu laden.');
    $land = eudr_land($b['land'] ?? '');
    $zeilen = ci_nummern_aufloesen(ci_nummern_lesen(array_key_exists('offeneNummern', $b) ? $b['offeneNummern'] : $alt['offeneNummern'] ?? []), $land, $ids, [], $betriebe, ci_nummern_index($betriebe));
    ['betriebe' => $ids, 'offeneNummern' => $offen] = ci_nummern_anwenden($ids, $zeilen);
    $von = eudr_datum($b['schlachtVon'] ?? '', 'Schlachtung von'); $bis = eudr_datum($b['schlachtBis'] ?? '', 'Schlachtung bis');
    if ($von !== '' && $bis !== '' && $bis < $von) throw new InvalidArgumentException('Schlachtung: „bis“ liegt vor „von“.');
    $n = is_array($b['nachweis'] ?? null) ? $b['nachweis'] : [];
    $lieferant = eudr_lieferant($b, $alt);
    $aktiv = !array_key_exists('aktiv', $b) || (bool)$b['aktiv'];
    return [
        // Pflicht – nur ein Eintrag von vorher darf ohne Partienummer ins Archiv
        'partie' => eudr_text($b['partie'] ?? '', 20, 'Partienummer', $aktiv || !$alt || $alt['partie'] !== ''),
        'nummer' => eudr_text($b['nummer'] ?? '', 60, 'Auftragsnummer des Lieferanten'),
        ...$lieferant,
        ...ci_schlachthof_am_container($b, $lieferant, $alt['schlachthof'] ?? ''),
        ...eudr_sendung_laufend($b, $alt),
        'land' => $land,
        'ware' => eudr_text($b['ware'] ?? '', 160, 'Ware'),
        'hs' => eudr_text($b['hs'] ?? '', 12, 'Zolltarifnummer'),
        'mengeKg' => eudr_zahl($b['mengeKg'] ?? null, 'Menge'),
        'schlachtVon' => $von, 'schlachtBis' => $bis,
        'lose' => eudr_text($b['lose'] ?? '', 200, 'Lose'),
        'betriebe' => $ids,
        'offeneNummern' => $offen,
        'nachweis' => [
            'erklaerung' => eudr_datum($n['erklaerung'] ?? '', 'Lieferantenerklärung vom', true),
            'rueckverfolgung' => eudr_wahl($n['rueckverfolgung'] ?? null, EUDR_DREI, 'Rückverfolgung', 'offen'),
            'haltung' => eudr_wahl($n['haltung'] ?? null, EUDR_DREI, 'Haltungsbetriebe', 'offen'),
            'legalitaet' => eudr_wahl($n['legalitaet'] ?? null, EUDR_DREI, 'Legalität', 'offen'),
        ],
        'aktiv' => $aktiv,
    ];
}
/* Angaben, die sich mit der Reise des Containers ändern – sie bleiben auch nach dem Abschluss der Bewertung pflegbar.
   Stand, Container- und Aktennummer behalten ohne Eingabe ihren Wert. */
function eudr_sendung_laufend(array $b, ?array $alt): array
{
    $alt = ($alt ?? []) + EUDR_SENDUNG_VORGABEN + ['container' => ''];
    return [
        ...ci_reise($b, $alt),
        'akte' => eudr_text($b['akte'] ?? $alt['akte'], 40, 'Aktennummer'),
        'dds' => eudr_dds_pruefen(is_array($b['dds'] ?? null) ? $b['dds'] : []),
        'notiz' => eudr_text($b['notiz'] ?? '', 2000, 'Notiz'),
    ];
}
/* Stand und Containernummer aus der Eingabe (ohne Eingabe bleibt der gespeicherte Wert) – die eine Stelle für alle, die sie
   pflegen: das Fenster „Container“ (eudr_sendung_laufend) und das Fenster „Tracking“ (containerimport_tracking_save). */
function ci_reise(array $b, array $alt): array
{
    return [
        'stand' => eudr_wahl($b['stand'] ?? null, array_keys(EUDR_STAENDE), 'Stand', $alt['stand']),
        'container' => eudr_text($b['container'] ?? $alt['container'], 40, 'Containernummer'),
    ];
}
/* Was einem älteren Eintrag noch fehlt, lässt sich auch nach dem Abschluss der Bewertung nachtragen – einmal, solange das
   Feld leer ist: die Partienummer (Einträge von vor dem Container als Mittelpunkt) und der Schlachthof. */
function eudr_sendung_nachtrag(array $b, array $alt): array
{
    return ($alt['partie'] === '' ? ['partie' => eudr_text($b['partie'] ?? '', 20, 'Partienummer')] : [])
        + ($alt['schlachthof'] === '' ? ci_schlachthof_am_container($b, $alt, '') : []);
}
/* Schlüssel des Lieferanten eines Eintrags (Container, Schlachthof): mit Nummer der Stammdaten die Nummer, sonst der Name
   ohne Rücksicht auf Groß- und Kleinschreibung. Gleicher Schlüssel = gleicher Lieferant; dieselbe Regel filtert in
   containerimport.js (lieferantSchluessel) die Auswahl der Schlachthöfe. */
function ci_lieferant_schluessel(array $x): string
{
    return $x['lieferantNr'] !== '' ? 'nr:' . $x['lieferantNr'] : 'name:' . mb_strtolower($x['lieferant']);
}
/* Lieferant eines Containers: mit „lieferantNr“ aus den Stammdaten der Verwaltung (Schnittstelle lieferanten_kurz, GR-101).
   Der Name wird mitgespeichert und bei jedem Speichern vor dem Abschluss aus den Stammdaten aufgefrischt – so bleibt der
   Container auch für ältere Stände lesbar. Fehlt der Lieferant dort inzwischen, bleibt die gespeicherte Verknüpfung mit
   ihrem Namen gültig. Ohne Nummer ist der Name freier Text (Lieferant steht noch nicht in den Stammdaten). */
function eudr_lieferant(array $b, ?array $alt): array
{
    $nr = eudr_text($b['lieferantNr'] ?? '', 20, 'Lieferant');
    if ($nr === '') return ['lieferantNr' => '', 'lieferant' => eudr_text($b['lieferant'] ?? '', 120, 'Lieferant', true)];
    $stamm = lieferanten_kurz()[$nr] ?? null;
    if ($stamm) return ['lieferantNr' => $nr, 'lieferant' => eudr_lieferant_name($stamm)];
    if ($alt && $alt['lieferantNr'] === $nr) return ['lieferantNr' => $nr, 'lieferant' => $alt['lieferant']];
    throw new InvalidArgumentException('Der gewählte Lieferant steht nicht (mehr) in den Stammdaten. Bitte neu laden.');
}
/* Name eines Lieferanten der Stammdaten; ohne Namen der Kurzname, ohne beides „Lieferant <Nummer>“ */
function eudr_lieferant_name(array $stamm): string
{
    return $stamm['name'] !== '' ? $stamm['name'] : ($stamm['kurz'] !== '' ? $stamm['kurz'] : 'Lieferant ' . $stamm['nr']);
}
/* Lieferanten zur Auswahl am Container: nur Nummer und Name, nach Name sortiert */
function eudr_lieferanten(): array
{
    $liste = array_map(fn($l) => ['nr' => $l['nr'], 'name' => eudr_lieferant_name($l)], array_values(lieferanten_kurz()));
    usort($liste, fn($a, $b) => strcasecmp($a['name'], $b['name']) ?: strcmp($a['nr'], $b['nr']));
    return $liste;
}
/* Ist die Partienummer schon bei einem anderen Container vergeben (auch bei einem archivierten)? Verglichen wird wie alle
   Nummern (ci_nummer_norm) – „P-100“, „p 100“ und „P–100“ sind dieselbe Partie. */
function eudr_partie_vergeben(array $liste, string $partie, ?int $ausser): bool
{
    $k = ci_nummer_norm($partie);
    if ($k === '') return false;
    foreach ($liste as $i => $x) if ($i !== $ausser && ci_nummer_norm($x['partie']) === $k) return true;
    return false;
}

/* Wie ein Container heißt: seine Partienummer; ältere Einträge ohne Partienummer nach der Auftragsnummer */
function eudr_container_name(array $s): string { return $s['partie'] !== '' ? $s['partie'] : $s['nummer']; }
/* Containernummer nach ISO 6346 (vier Buchstaben, sechs Ziffern, Prüfziffer) einordnen: '' leer, 'ok', 'pruefziffer' (Tippfehler?)
   oder 'format'. Nur ein Hinweis – gespeichert wird, was eingegeben wurde. */
function eudr_containernummer(string $text): string
{
    $n = strtoupper((string)preg_replace('/[\s.\/-]+/', '', $text));
    if ($n === '') return '';
    if (!preg_match('/^[A-Z]{4}[0-9]{7}$/', $n)) return 'format';
    $summe = 0;
    for ($i = 0; $i < 10; $i++) {
        $z = $n[$i];
        if ($z >= 'A') { $k = ord($z) - 65; $wert = 10 + $k + intdiv($k + 9, 10); }   // A=10, B=12 … K=21, L=23 … U=32, V=34 … (Vielfache von 11 ausgelassen)
        else $wert = (int)$z;
        $summe += $wert << $i;
    }
    return $summe % 11 % 10 === (int)$n[10] ? 'ok' : 'pruefziffer';
}
/* Angaben zur Sorgfaltserklärung im EU-Informationssystem (auch nach dem Abschluss änderbar) */
function eudr_dds_pruefen(array $dds): array
{
    return ['referenz' => eudr_text($dds['referenz'] ?? '', 60, 'Referenznummer der Sorgfaltserklärung'), 'datum' => eudr_datum($dds['datum'] ?? '', 'Datum der Sorgfaltserklärung', true)];
}

/* ---------- Risikoprofil ---------- */
/* Namen der Betriebe, auf die eine Bedingung zutrifft */
function eudr_namen(array $betriebe, callable $bedingung): array
{
    return array_values(array_map(fn($b) => $b['name'], array_filter($betriebe, $bedingung)));
}
/* Namen der Betriebe mit einer bestimmten Bewertung in einem Thema (eudr_betrieb_bewertung) */
function eudr_bewertet(array $betriebe, string $thema, string $stufe): array
{
    return eudr_namen($betriebe, fn($b) => $b['bewertung'][$thema] === $stufe);
}
/* Ein Kriterium des Profils: stand ok | hinweis | offen | kritisch */
function eudr_kriterium(string $id, string $titel, string $stand, string $text, array $betriebe = []): array
{
    return ['id' => $id, 'titel' => $titel, 'stand' => $stand, 'text' => $text, 'betriebe' => $betriebe];
}

/* Kriterien des Risikoprofils (Art. 10 der Verordnung) als Tabelle: jede Zeile bewertet die Sendung mit ihren Betrieben
   ($bs = Sichten der Betriebe) und liefert ein Kriterium. Neue Prüfungen kommen als weitere Zeile hinzu. */
function eudr_kriterien(): array
{
    return [
        'land' => function (array $s, array $bs): array {
            $titel = 'Einstufung des Herkunftslands';
            $name = fn(string $code): string => EUDR_LAENDER[$code]['name'] ?? $code;
            $codes = array_values(array_unique(array_merge([$s['land']], array_column($bs, 'land'))));
            $klassen = array_map(fn($c) => EUDR_LAENDER[$c]['klasse'] ?? null, $codes);
            $laender = implode(', ', array_map($name, $codes));
            if (in_array('hoch', $klassen, true)) return eudr_kriterium('land', $titel, 'kritisch', "$laender: ein Land mit hohem Risiko – verstärkte Prüfung nötig.");
            $fremd = eudr_namen($bs, fn($b) => $b['land'] !== $s['land']);
            if ($fremd) return eudr_kriterium('land', $titel, 'offen', 'Diese Farmer liegen laut ihren Angaben nicht in ' . $name($s['land']) . ' – Herkunftsland des Containers klären.', $fremd);
            if ($klassen === ['standard']) return eudr_kriterium('land', $titel, 'hinweis', "$laender: Standardrisiko – volle Sorgfaltspflicht mit Risikobewertung (keine Vereinfachung).");
            if ($klassen === ['niedrig']) return eudr_kriterium('land', $titel, 'ok', "$laender: niedriges Risiko – vereinfachte Sorgfaltspflicht.");
            return eudr_kriterium('land', $titel, 'offen', "Für $laender ist keine Einstufung hinterlegt – bitte in der Länderliste der EU nachsehen.");
        },
        'geo' => function (array $s, array $bs): array {
            $titel = 'Geolokalisierung der Farmer';
            $fehler = eudr_bewertet($bs, 'geo', 'kritisch');
            $offen = array_map(fn($n) => 'Nr. ' . $n, $s['offeneNummern']);
            if ($fehler || $offen) return eudr_kriterium('geo', $titel, 'kritisch', implode(' ', array_filter([
                $offen ? 'Zu diesen Farmer-Nummern aus den Papieren fehlen die Unterlagen mit der Geolokalisierung – beim Lieferanten anfordern.' : '',
                $fehler ? 'Die Geolokalisierung ist fehlerhaft und würde vom EU-Informationssystem abgelehnt – beim Lieferanten korrigieren lassen.' : ''])), [...$fehler, ...$offen]);
            if (!$bs) return eudr_kriterium('geo', $titel, 'kritisch', 'Dem Container ist kein Farmer zugeordnet – ohne Geolokalisierung ist keine Sorgfaltserklärung möglich.');
            $hinweise = eudr_namen($bs, fn($b) => $b['stand'] === 'hinweis');
            return eudr_kriterium('geo', $titel, $hinweise ? 'hinweis' : 'ok', count($bs) . ' Farmer mit einreichbarer Geolokalisierung' . ($hinweise ? ' – Hinweise beachten.' : '.'), $hinweise);
        },
        'rueckverfolgung' => fn(array $s, array $bs): array => eudr_kriterium('rueckverfolgung', 'Rückverfolgung Los → Farmer', ['ja' => 'ok', 'nein' => 'kritisch', 'offen' => 'offen'][$s['nachweis']['rueckverfolgung']],
            ['ja' => 'Die Unterlagen belegen, von welchen Farmern die Tiere der Schlachtlose stammen.', 'nein' => 'Die Lose lassen sich den Farmern nicht zuordnen.',
             'offen' => 'Noch nicht belegt, welche Schlachtlose' . ($s['lose'] !== '' ? ' (' . $s['lose'] . ')' : '') . ' von welchem Farmer stammen – Zuordnung beim Lieferanten anfordern.'][$s['nachweis']['rueckverfolgung']]),
        'haltung' => fn(array $s, array $bs): array => eudr_kriterium('haltung', 'Alle Haltungsbetriebe erfasst', ['ja' => 'ok', 'nein' => 'kritisch', 'offen' => 'offen'][$s['nachweis']['haltung']],
            ['ja' => 'Alle Betriebe, in denen die Tiere gehalten wurden (Geburt, Aufzucht, Mast), sind erfasst.', 'nein' => 'Es fehlen Betriebe, in denen die Tiere gehalten wurden.',
             'offen' => 'Bei Rindern verlangt die Verordnung die Geolokalisierung aller Betriebe, in denen die Tiere gehalten wurden – Bestätigung beim Lieferanten anfordern.'][$s['nachweis']['haltung']]),
        'entwaldung' => function (array $s, array $bs): array {
            $titel = 'Entwaldungsfrei seit 31.12.2020 (Bericht des Lieferanten)';
            if (!$bs) return eudr_kriterium('entwaldung', $titel, 'offen', 'Ohne Farmer nicht bewertbar.');
            $nicht = eudr_bewertet($bs, 'entwaldung', 'kritisch');
            if ($nicht) return eudr_kriterium('entwaldung', $titel, 'kritisch', 'Der Bericht weist Entwaldung nach dem Stichtag aus.', $nicht);
            $ohne = eudr_bewertet($bs, 'entwaldung', 'offen');
            if ($ohne) return eudr_kriterium('entwaldung', $titel, 'offen', 'Für diese Farmer liegt kein Nachweis der Entwaldungsfreiheit vor.', $ohne);
            $tag = $s['schlachtVon'] !== '' ? $s['schlachtVon'] : date('Y-m-d');
            $alt = eudr_namen($bs, fn($b) => $b['bericht']['datum'] === '' || $b['bericht']['datum'] < date('Y-m-d', strtotime($tag . ' -' . EUDR_BERICHT_MONATE . ' months')));
            if ($alt) return eudr_kriterium('entwaldung', $titel, 'offen', 'Der Bericht ist undatiert oder älter als ' . EUDR_BERICHT_MONATE . ' Monate vor der Schlachtung – aktuellen Bericht anfordern.', $alt);
            $luecke = eudr_namen($bs, fn($b) => $b['bericht']['bilderBis'] !== null && $b['bericht']['bilderBis'] < (int)substr($tag, 0, 4) - 1);
            if ($luecke) return eudr_kriterium('entwaldung', $titel, 'offen', 'Die ausgewerteten Satellitenbilder enden mehr als ein Jahr vor der Schlachtung – der Zeitraum danach ist nicht belegt.', $luecke);
            return eudr_kriterium('entwaldung', $titel, 'ok', 'Alle Farmer laut Bericht ohne Entwaldung seit dem Stichtag.');
        },
        'gegenpruefung' => function (array $s, array $bs): array {
            $titel = 'Eigene Gegenprüfung der Entwaldung';
            if (!$bs) return eudr_kriterium('gegenpruefung', $titel, 'offen', 'Ohne Farmer nicht bewertbar.');
            $befund = eudr_bewertet($bs, 'gegenpruefung', 'kritisch');
            if ($befund) return eudr_kriterium('gegenpruefung', $titel, 'kritisch', 'Die eigene Prüfung zeigt Baumverlust oder Warnmeldungen seit dem Stichtag – mit dem Lieferanten klären.', $befund);
            $ohne = eudr_bewertet($bs, 'gegenpruefung', 'offen');
            if ($ohne) return eudr_kriterium('gegenpruefung', $titel, 'offen', 'Noch nicht unabhängig geprüft – Fläche in Global Nature Watch oder Whisp ansehen und das Ergebnis am Farmer eintragen.', $ohne);
            return eudr_kriterium('gegenpruefung', $titel, 'ok', 'Alle Farmer unabhängig geprüft, ohne Befund.');
        },
        'gebiete' => function (array $s, array $bs): array {
            $titel = 'Schutzgebiete und indigene Gebiete';
            $nicht = eudr_bewertet($bs, 'gebiete', 'kritisch');
            if ($nicht) return eudr_kriterium('gebiete', $titel, 'kritisch', 'Überschneidung mit einem Schutzgebiet oder indigenen Gebiet.', $nicht);
            $ohne = eudr_bewertet($bs, 'gebiete', 'offen');
            if ($ohne || !$bs) return eudr_kriterium('gebiete', $titel, 'offen', 'Kein Nachweis, dass die Fläche außerhalb von Schutzgebieten und indigenen Gebieten liegt.', $ohne);
            return eudr_kriterium('gebiete', $titel, 'ok', 'Keine Überschneidung laut Bericht.');
        },
        'legalitaet' => function (array $s, array $bs): array {
            $titel = 'Legalität nach dem Recht des Erzeugerlands';
            $nicht = eudr_bewertet($bs, 'legalitaet', 'kritisch');
            if ($nicht) return eudr_kriterium('legalitaet', $titel, 'kritisch', 'Landnutzungsplan oder Umweltgenehmigung sind laut Bericht nicht konform.', $nicht);
            if ($s['nachweis']['legalitaet'] === 'ja') return eudr_kriterium('legalitaet', $titel, 'ok', 'Nachweise zur Einhaltung der einschlägigen Vorschriften liegen vor.');
            if ($s['nachweis']['legalitaet'] === 'nein') return eudr_kriterium('legalitaet', $titel, 'kritisch', 'Die Einhaltung der einschlägigen Vorschriften ist nicht belegt.');
            $ohne = eudr_bewertet($bs, 'legalitaet', 'offen');
            return eudr_kriterium('legalitaet', $titel, 'offen', $ohne
                ? 'Der Bericht enthält keine Angaben zu Landnutzungsplan und Umweltgenehmigung – Nachweise (Landtitel, Genehmigungen) beim Lieferanten anfordern.'
                : 'Bitte bestätigen, dass Nachweise zu Landnutzungsrechten, Umwelt- und Arbeitsrecht vorliegen.', $ohne);
        },
        'erklaerung' => fn(array $s, array $bs): array => $s['nachweis']['erklaerung'] !== ''
            ? eudr_kriterium('erklaerung', 'Erklärung des Lieferanten', 'ok', 'Erklärung vom ' . date('d.m.Y', strtotime($s['nachweis']['erklaerung'])) . ' liegt vor.')
            : eudr_kriterium('erklaerung', 'Erklärung des Lieferanten', 'offen', 'Erklärung des Lieferanten zur EUDR fehlt.'),
    ];
}

/* Risikoprofil einer Sendung: alle Kriterien, Gesamtstand (das schlechteste Kriterium) und ein Vorschlag.
   Die Bewertung selbst trifft der Bearbeiter beim Abschluss. */
function eudr_profil(array $s, array $bs): array
{
    $kriterien = array_values(array_map(fn(callable $k) => $k($s, $bs), eudr_kriterien()));
    $staende = array_column($kriterien, 'stand');
    $stand = in_array('kritisch', $staende, true) ? 'kritisch' : (in_array('offen', $staende, true) ? 'offen' : 'ok');
    return [
        'kriterien' => $kriterien, 'stand' => $stand,
        'vorschlag' => ['ok' => 'Kein Risiko erkennbar – die Sorgfaltserklärung kann abgegeben werden.',
            'offen' => 'Noch nicht bewertbar – offene Angaben beim Lieferanten anfordern.',
            'kritisch' => 'Risiko nicht vernachlässigbar – Ware nicht in Verkehr bringen, bis die Punkte geklärt sind.'][$stand],
        // Darf die Bewertung „Risiko vernachlässigbar“ lauten? ja | begruendung (nur mit Begründung) | nein
        'vernachlaessigbar' => ['ok' => 'ja', 'offen' => 'begruendung', 'kritisch' => 'nein'][$stand],
        'laenderStand' => EUDR_LAENDER_STAND,
    ];
}

/* Betriebe einer Sendung als Sichten: nach dem Abschluss der Schnappschuss, sonst der aktuelle Stand */
function eudr_sendung_betriebe(array $s, array $sichten): array
{
    if (!empty($s['abschluss'])) return $s['abschluss']['betriebe'];
    return array_values(array_filter($sichten, fn($b) => in_array($b['id'], $s['betriebe'], true)));
}

/* Abschluss einer Bewertung aus der Eingabe: Ergebnis, Begründung, Bearbeiter und Schnappschuss von Profil und Betrieben
   (GR-106). „Vernachlässigbar“ nie mit einem kritischen Kriterium, mit offenen Kriterien nur mit Begründung (422). */
function eudr_abschluss(array $s, array $eingabe, array $sichten, array $me): array
{
    $ergebnis = eudr_wahl($eingabe['ergebnis'] ?? null, ['vernachlaessigbar', 'nicht_vernachlaessigbar'], 'Ergebnis');
    $begruendung = eudr_text($eingabe['begruendung'] ?? '', 2000, 'Begründung');
    $bs = eudr_sendung_betriebe($s, $sichten);
    $profil = eudr_profil($s, $bs);
    if ($ergebnis === 'vernachlaessigbar' && $profil['vernachlaessigbar'] === 'nein') throw new InvalidArgumentException('Solange ein Kriterium kritisch ist, kann das Risiko nicht als vernachlässigbar bewertet werden.');
    if ($ergebnis === 'vernachlaessigbar' && $profil['vernachlaessigbar'] === 'begruendung' && mb_strlen($begruendung) < 20)
        throw new InvalidArgumentException('Es sind noch Punkte offen. Bitte begründen, warum das Risiko trotzdem vernachlässigbar ist (mindestens 20 Zeichen).');
    return ['ergebnis' => $ergebnis, 'begruendung' => $begruendung, 'wer' => eudr_wer($me), 'profil' => $profil, 'betriebe' => $bs];
}
/* Punkte der Umrisse, die die Sendungen in ihren Schnappschüssen festhalten (Abschluss und frühere Abschlüsse; ältere frühere
   ohne Farmer zählen nicht) – für EUDR_MAX_PUNKTE_SCHNAPPSCHUESSE */
function eudr_schnappschuss_punkte(array $sendungen): int
{
    $n = 0;
    foreach ($sendungen as $s) foreach ([$s['abschluss'] ?? null, ...($s['fruehere'] ?? [])] as $a)
        foreach ($a['betriebe'] ?? [] as $b) if (is_array($b['geometrie'] ?? null)) $n += geo_punktzahl($b['geometrie']);
    return $n;
}

/* Sendung für die Oberfläche: mit Profil – bei abgeschlossener Bewertung dem gespeicherten Schnappschuss; frühere
   Abschlüsse nur mit Ergebnis, Begründung und Grund. Der Name des Schlachthofs ($hofNamen: Kennung → Name) ist bei offener
   Bewertung der aktuelle, nach dem Abschluss der festgeschriebene. */
function eudr_sendung_sicht(array $s, array $betriebe, array $hofNamen): array
{
    $s['fruehere'] = array_map(fn($f) => array_diff_key($f, ['profil' => 1, 'betriebe' => 1]), $s['fruehere'] ?? []);   // Schnappschüsse bleiben gespeichert
    if (empty($s['abschluss'])) $s['schlachthofName'] = $hofNamen[$s['schlachthof']] ?? $s['schlachthofName'];
    $bs = eudr_sendung_betriebe($s, $betriebe);
    return $s + ['name' => eudr_container_name($s), 'containerPruefung' => eudr_containernummer($s['container']), 'profil' => !empty($s['abschluss']) ? $s['abschluss']['profil'] : eudr_profil($s, $bs),
        'farmerPruefung' => ci_farmer_pruefung($bs, $s['offeneNummern'])];
}

/* ---------- GeoJSON für das EU-Informationssystem ---------- */
/* FeatureCollection aus Betrieb-Sichten: Eigenschaften in der vorgeschriebenen Schreibweise, Fläche als Zahl.
   Betriebe mit fehlerhafter Geolokalisierung bleiben draußen und stehen in „ausgelassen“. */
function eudr_geojson(array $bs): array
{
    $features = []; $ausgelassen = [];
    foreach ($bs as $b) {
        if ($b['stand'] === 'fehler') { $ausgelassen[] = $b['name']; continue; }
        $features[] = ['type' => 'Feature',
            'properties' => ['ProducerName' => $b['erzeuger'] !== '' ? $b['erzeuger'] : $b['name'], 'ProducerCountry' => $b['land'],
                'ProductionPlace' => $b['name'] . ($b['kennung'] !== '' ? ' (' . $b['kennung'] . ')' : ''), 'Area' => $b['flaeche']],
            'geometry' => $b['geometrie']];
    }
    return ['geojson' => ['type' => 'FeatureCollection', 'features' => $features], 'ausgelassen' => $ausgelassen];
}

/* ---------- Stand für die Oberfläche ---------- */
/* Alle Betriebe und Sendungen mit abgeleiteten Werten, dazu Länder und Portale */
function eudr_stand(): array
{
    $betriebe = array_map('eudr_betrieb_sicht', eudr_betriebe()['liste']);
    $sendungen = eudr_sendungen()['liste'];
    $hoefe = ci_schlachthoefe()['liste'];
    $hofNamen = array_column($hoefe, 'name', 'id');
    return [
        'betriebe' => $betriebe,
        'sendungen' => array_map(fn($s) => eudr_sendung_sicht($s, $betriebe, $hofNamen), $sendungen),
        'offeneNummern' => ci_offene_nummern($sendungen, ci_nummern_index($betriebe)),
        'laender' => array_map(fn($l) => ['name' => $l['name'], 'klasse' => $l['klasse']], EUDR_LAENDER),
        'schlachthoefe' => $hoefe,
        'hafen' => ci_hafen_sicht($sendungen),
        'portale' => EUDR_PORTALE, 'staende' => EUDR_STAENDE, 'reedereien' => CI_REEDEREIEN, 'heute' => date('Y-m-d'),
        'dokumente' => (object)ci_dokumente_zahlen_lesen(), 'dokRegeln' => ci_dok_regeln(),
    ];
}
