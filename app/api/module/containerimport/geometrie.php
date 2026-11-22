<?php
declare(strict_types=1);
/* Container-Import · Geometrie der Produktionsorte (EUDR): reine Rechenfunktionen ohne Speicherzugriff.
   Umrechnung UTM → WGS84, Fläche auf dem Ellipsoid, Normalisieren (6 Nachkommastellen, geschlossener Ring, Umlauf gegen
   den Uhrzeigersinn) und Prüfen nach den Regeln des EU-Informationssystems (TRACES, „EUDR GeoJSON File Description“):
   Längengrad vor Breitengrad in WGS84, Polygon mit mindestens vier Positionen, erste = letzte, keine Löcher, keine
   Selbstüberschneidung, keine doppelten Punkte nach dem Runden. Alle Funktionen liefern Werte und werfen nie. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const GEO_A = 6378137.0;                 // WGS84: große Halbachse in Metern
const GEO_F = 1 / 298.257223563;         // WGS84: Abplattung
const GEO_STELLEN = 6;                   // das Informationssystem verarbeitet 6 Nachkommastellen
const GEO_MAX_PUNKTE = 5000;             // je Produktionsort
const GEO_MAX_VERGLEICHE = 300000;       // Kantenvergleiche je Umriss – die Punktzahl allein hält die Prüfung auf
                                         // Selbstüberschneidung nicht unter einer Sekunde: sie ist quadratisch in der
                                         // Punktzahl, und wie viele Kanten einander überlappen, bestimmt allein der
                                         // Einsender der Datei (gemessen 4,1 s bei 4998 Punkten, gutartige 5000 Punkte
                                         // brauchen 12 493 Vergleiche). 300 000 sind rund 0,15 s.
const GEO_MAX_BETRAG = 1e9;              // größere Zahlen sind keine Koordinaten (UTM-Werte bleiben als Fehler „bereich“ lesbar)
const GEO_PUNKT_HA = 4.0;                // Fläche eines Punktes ohne Angabe (Vorgabe des Informationssystems)
const GEO_DORN_GRAD = 2.0;               // spitzer Winkel, unter dem eine Ecke als „Dorn“ gemeldet wird
/* Korrekturen beim Normalisieren (ändern die Fläche nicht): Kennung → Text für die Anzeige */
const GEO_KORREKTUREN = ['doppelt' => 'Doppelte Punkte nach dem Runden auf 6 Nachkommastellen entfernt', 'offen' => 'Offenen Umriss geschlossen (erster Punkt am Ende ergänzt)'];
const GEO_LINIE = 1e-10;                 // ebene Fläche in Quadratgrad (rund 1 m²), unter der ein Umriss als Linie gilt

/* UTM (Rechtswert, Hochwert in Metern, Zone 1–60, Südhalbkugel ja/nein) → [Längengrad, Breitengrad] in WGS84 */
function geo_utm_nach_wgs84(float $rechts, float $hoch, int $zone, bool $sued): array
{
    $k0 = 0.9996; $e2 = GEO_F * (2 - GEO_F); $ep2 = $e2 / (1 - $e2);
    $x = $rechts - 500000.0; $y = $hoch - ($sued ? 10000000.0 : 0.0);
    $mu = ($y / $k0) / (GEO_A * (1 - $e2 / 4 - 3 * $e2 ** 2 / 64 - 5 * $e2 ** 3 / 256));
    $e1 = (1 - sqrt(1 - $e2)) / (1 + sqrt(1 - $e2));
    $p = $mu + (3 * $e1 / 2 - 27 * $e1 ** 3 / 32) * sin(2 * $mu) + (21 * $e1 ** 2 / 16 - 55 * $e1 ** 4 / 32) * sin(4 * $mu)
        + (151 * $e1 ** 3 / 96) * sin(6 * $mu) + (1097 * $e1 ** 4 / 512) * sin(8 * $mu);
    $c = $ep2 * cos($p) ** 2; $t = tan($p) ** 2;
    $n = GEO_A / sqrt(1 - $e2 * sin($p) ** 2); $r = GEO_A * (1 - $e2) / (1 - $e2 * sin($p) ** 2) ** 1.5; $d = $x / ($n * $k0);
    $lat = $p - ($n * tan($p) / $r) * ($d ** 2 / 2 - (5 + 3 * $t + 10 * $c - 4 * $c ** 2 - 9 * $ep2) * $d ** 4 / 24
        + (61 + 90 * $t + 298 * $c + 45 * $t ** 2 - 252 * $ep2 - 3 * $c ** 2) * $d ** 6 / 720);
    $lon = ($d - (1 + 2 * $t + $c) * $d ** 3 / 6 + (5 - 2 * $c + 28 * $t - 3 * $c ** 2 + 8 * $ep2 + 24 * $t ** 2) * $d ** 5 / 120) / cos($p);
    return [rad2deg($lon) + ($zone * 6 - 183), rad2deg($lat)];
}

/* Fläche eines Rings in Hektar auf dem WGS84-Ellipsoid, mit Vorzeichen: positiv = gegen den Uhrzeigersinn.
   Flächentreu über die Zonenfläche des Ellipsoids zwischen Äquator und Breite (Kanten als kurze Strecken). */
function geo_ring_ha(array $ring): float
{
    $e = sqrt(GEO_F * (2 - GEO_F)); $b2 = GEO_A ** 2 * (1 - $e ** 2);
    $q = function (float $lat) use ($e): float {
        $s = sin(deg2rad($lat));
        return $s / (1 - $e ** 2 * $s ** 2) + log((1 + $e * $s) / (1 - $e * $s)) / (2 * $e);
    };
    $summe = 0.0;
    for ($i = 0, $n = count($ring) - 1; $i < $n; $i++) {
        $summe += deg2rad($ring[$i + 1][0] - $ring[$i][0]) * ($q($ring[$i][1]) + $q($ring[$i + 1][1])) / 2;
    }
    return -$summe * $b2 / 2 / 10000;
}

/* Fläche eines Rings in der Ebene (Quadratgrad, mit Vorzeichen) – nur zum Erkennen entarteter Umrisse */
function geo_ring_eben(array $ring): float
{
    $summe = 0.0;
    for ($i = 0, $n = count($ring) - 1; $i < $n; $i++) $summe += $ring[$i][0] * $ring[$i + 1][1] - $ring[$i + 1][0] * $ring[$i][1];
    return $summe / 2;
}

/* Schneiden sich die Strecken p–q und r–s echt (nicht nur an einem gemeinsamen Endpunkt)? */
function geo_schnitt(array $p, array $q, array $r, array $s): bool
{
    $o = fn(array $a, array $b, array $c): float => ($b[0] - $a[0]) * ($c[1] - $a[1]) - ($b[1] - $a[1]) * ($c[0] - $a[0]);
    $d1 = $o($p, $q, $r); $d2 = $o($p, $q, $s); $d3 = $o($r, $s, $p); $d4 = $o($r, $s, $q);
    if ($d1 * $d2 < 0 && $d3 * $d4 < 0) return true;
    $auf = fn(array $a, array $b, array $c): bool => min($a[0], $b[0]) <= $c[0] && $c[0] <= max($a[0], $b[0]) && min($a[1], $b[1]) <= $c[1] && $c[1] <= max($a[1], $b[1]);
    return ($d1 == 0 && $auf($p, $q, $r)) || ($d2 == 0 && $auf($p, $q, $s)) || ($d3 == 0 && $auf($r, $s, $p)) || ($d4 == 0 && $auf($r, $s, $q));
}

/* Erste Selbstüberschneidung eines geschlossenen Rings als [Kante i, Kante j] (Nummern ab 1) oder null.
   Kanten nach kleinstem Längengrad sortiert: verglichen werden nur Kanten, deren Längen- und Breitenbereiche sich überlappen.
   Die Einsparung greift nicht, wenn fast alle Kanten einander überlappen (ein „Kamm“ aus dünnen, schrägen Zacken) – dann ist
   die Prüfung quadratisch in der Punktzahl. Deshalb ein Budget an Kantenvergleichen (GEO_MAX_VERGLEICHE): reicht es nicht,
   wird $abbruch gesetzt und der Umriss gilt als nicht prüfbar (Befund „komplex“ in geo_pruefen), statt jede Antwort des
   Moduls beliebig teuer zu machen. Das Budget gilt je Umriss; mehr als fünf Umrisse können es bei GEO_MAX_PUNKTE nicht
   ausschöpfen, die Zusage „unter einer Sekunde“ je Produktionsort bleibt damit gewahrt. */
function geo_selbstschnitt(array $ring, bool &$abbruch = false): ?array
{
    $abbruch = false;
    $n = count($ring) - 1;
    $kanten = [];
    for ($i = 0; $i < $n; $i++) $kanten[] = [min($ring[$i][0], $ring[$i + 1][0]), max($ring[$i][0], $ring[$i + 1][0]), $i, min($ring[$i][1], $ring[$i + 1][1]), max($ring[$i][1], $ring[$i + 1][1])];
    usort($kanten, fn($a, $b) => $a[0] <=> $b[0]);
    $budget = GEO_MAX_VERGLEICHE;
    for ($a = 0; $a < $n; $a++) {
        for ($b = $a + 1; $b < $n && $kanten[$b][0] <= $kanten[$a][1]; $b++) {
            if (--$budget <= 0) { $abbruch = true; return null; }
            if ($kanten[$b][3] > $kanten[$a][4] || $kanten[$b][4] < $kanten[$a][3]) continue;   // Breitenbereiche getrennt
            $i = min($kanten[$a][2], $kanten[$b][2]); $j = max($kanten[$a][2], $kanten[$b][2]);
            if ($j - $i <= 1 || ($i === 0 && $j === $n - 1)) continue;   // Nachbarkanten teilen sich einen Punkt
            if (geo_schnitt($ring[$i], $ring[$i + 1], $ring[$j], $ring[$j + 1])) return [$i + 1, $j + 1];
        }
    }
    return null;
}

/* Kleinster Innenwinkel an einer Ecke unter GEO_DORN_GRAD: Nummer des Punktes (ab 0) oder null */
function geo_dorn(array $ring): ?int
{
    $n = count($ring) - 1;
    for ($i = 0; $i < $n; $i++) {
        $v = $ring[($i + $n - 1) % $n]; $p = $ring[$i]; $w = $ring[$i + 1];
        $ax = $v[0] - $p[0]; $ay = $v[1] - $p[1]; $bx = $w[0] - $p[0]; $by = $w[1] - $p[1];
        $la = hypot($ax, $ay); $lb = hypot($bx, $by);
        if ($la == 0.0 || $lb == 0.0) continue;
        if (rad2deg(acos(max(-1.0, min(1.0, ($ax * $bx + $ay * $by) / ($la * $lb))))) < GEO_DORN_GRAD) return $i;
    }
    return null;
}

/* Ist der Wert eine Position [Längengrad, Breitengrad] aus zwei Zahlen in vernünftiger Größe? */
function geo_position($v): bool
{
    return is_array($v) && array_is_list($v) && count($v) >= 2 && (is_int($v[0]) || is_float($v[0])) && (is_int($v[1]) || is_float($v[1]))
        && abs((float)$v[0]) <= GEO_MAX_BETRAG && abs((float)$v[1]) <= GEO_MAX_BETRAG;
}

/* Ring normalisieren: auf 6 Stellen runden, aufeinanderfolgende Doppelte entfernen, schließen, gegen den Uhrzeigersinn
   drehen. Liefert [Ring, Kennungen der vorgenommenen Korrekturen (GEO_KORREKTUREN)]. */
function geo_ring_normal(array $ring): array
{
    $aus = []; $korrekturen = [];
    foreach ($ring as $p) {
        $q = [round((float)$p[0], GEO_STELLEN), round((float)$p[1], GEO_STELLEN)];
        if ($aus && $aus[count($aus) - 1] === $q) { $korrekturen['doppelt'] = true; continue; }
        $aus[] = $q;
    }
    if (count($aus) >= 3 && $aus[0] !== $aus[count($aus) - 1]) { $aus[] = $aus[0]; $korrekturen['offen'] = true; }
    if (count($aus) >= 4 && geo_ring_ha($aus) < 0) $aus = array_reverse($aus);
    return [$aus, array_keys($korrekturen)];
}

/* Geometrie aus fremder Eingabe lesen und normalisieren. Erlaubt: Point, Polygon, MultiPolygon (MultiPoint wird zu
   einzelnen Punkten nicht zerlegt – das macht der Leser der Datei). Liefert ['geometrie' => …, 'korrekturen' => […]]
   oder ['fehler' => 'Text'], wenn die Eingabe keine brauchbare Geometrie ist. */
function geo_lesen($g): array
{
    if (!is_array($g) || !is_string($g['type'] ?? null) || !is_array($g['coordinates'] ?? null)) return ['fehler' => 'Keine Geometrie mit „type“ und „coordinates“.'];
    $k = $g['coordinates'];
    if ($g['type'] === 'Point') {
        if (!geo_position($k)) return ['fehler' => 'Punkt ohne zwei Zahlen (Längengrad, Breitengrad).'];
        return ['geometrie' => ['type' => 'Point', 'coordinates' => [round((float)$k[0], GEO_STELLEN), round((float)$k[1], GEO_STELLEN)]], 'korrekturen' => []];
    }
    if ($g['type'] !== 'Polygon' && $g['type'] !== 'MultiPolygon') {
        return ['fehler' => 'Geometrieart „' . mb_substr($g['type'], 0, 30) . '“ wird vom EU-Informationssystem nicht angenommen (erlaubt: Point, Polygon, MultiPolygon).'];
    }
    $teile = $g['type'] === 'Polygon' ? [$k] : $k;
    if (!$teile || !array_is_list($teile)) return ['fehler' => 'Geometrie ohne Koordinaten.'];
    $aus = []; $korrekturen = []; $punkte = 0;
    foreach ($teile as $polygon) {
        if (!is_array($polygon) || !$polygon || !array_is_list($polygon)) return ['fehler' => 'Polygon ohne Umriss.'];
        $ringe = [];
        foreach ($polygon as $ring) {
            if (!is_array($ring) || !array_is_list($ring)) return ['fehler' => 'Umriss ist keine Liste von Punkten.'];
            foreach ($ring as $p) if (!geo_position($p)) return ['fehler' => 'Umriss enthält einen Punkt ohne zwei Zahlen (Längengrad, Breitengrad).'];
            $punkte += count($ring);
            if ($punkte > GEO_MAX_PUNKTE) return ['fehler' => 'Mehr als ' . GEO_MAX_PUNKTE . ' Punkte in einem Produktionsort.'];
            [$r, $kor] = geo_ring_normal($ring);
            $ringe[] = $r; $korrekturen = array_merge($korrekturen, $kor);
        }
        $aus[] = $ringe;
    }
    $geometrie = count($aus) === 1 ? ['type' => 'Polygon', 'coordinates' => $aus[0]] : ['type' => 'MultiPolygon', 'coordinates' => $aus];
    return ['geometrie' => $geometrie, 'korrekturen' => array_values(array_unique($korrekturen))];
}

/* Polygone einer gespeicherten Geometrie als Liste von Ringlisten (Point: leer) */
function geo_polygone(array $g): array
{
    return $g['type'] === 'Polygon' ? [$g['coordinates']] : ($g['type'] === 'MultiPolygon' ? $g['coordinates'] : []);
}

/* Kennzahlen einer normalisierten Geometrie: Fläche in Hektar (Point: null), Mittelpunkt, Rahmen, Zahl der Punkte */
function geo_kennzahlen(array $g): array
{
    if ($g['type'] === 'Point') {
        [$x, $y] = $g['coordinates'];
        return ['flaeche' => null, 'mitte' => [$x, $y], 'rahmen' => [$x, $y, $x, $y], 'punkte' => 1];
    }
    $ha = 0.0; $punkte = 0; $xs = []; $ys = [];
    foreach (geo_polygone($g) as $polygon) {
        foreach ($polygon as $nr => $ring) {
            if (count($ring) >= 4) $ha += ($nr === 0 ? 1 : -1) * abs(geo_ring_ha($ring));
            $punkte += max(0, count($ring) - 1);
            foreach ($ring as $p) { $xs[] = $p[0]; $ys[] = $p[1]; }
        }
    }
    if (!$xs) return ['flaeche' => 0.0, 'mitte' => [0.0, 0.0], 'rahmen' => [0.0, 0.0, 0.0, 0.0], 'punkte' => 0];
    $rahmen = [min($xs), min($ys), max($xs), max($ys)];
    return ['flaeche' => round($ha, 2), 'mitte' => [round(($rahmen[0] + $rahmen[2]) / 2, GEO_STELLEN), round(($rahmen[1] + $rahmen[3]) / 2, GEO_STELLEN)], 'rahmen' => $rahmen, 'punkte' => $punkte];
}

/* Geometrie nach den Regeln des EU-Informationssystems prüfen. Liefert eine Liste von Befunden
   ['stufe' => 'fehler'|'hinweis', 'code' => …, 'text' => …]; Fehler führen dort zur Ablehnung der Datei. */
function geo_pruefen(array $g): array
{
    $befunde = [];
    $abbruch = false;   // von geo_selbstschnitt gesetzt, wenn das Vergleichsbudget nicht reichte
    $melden = function (string $stufe, string $code, string $text) use (&$befunde): void { $befunde[] = ['stufe' => $stufe, 'code' => $code, 'text' => $text]; };
    $bereich = fn(array $p): bool => abs($p[0]) <= 180 && abs($p[1]) <= 90;
    if ($g['type'] === 'Point') {
        if (!$bereich($g['coordinates'])) $melden('fehler', 'bereich', 'Koordinaten außerhalb des gültigen Bereichs (Breite ±90, Länge ±180).');
        return $befunde;
    }
    foreach (geo_polygone($g) as $nr => $polygon) {
        $teil = $g['type'] === 'MultiPolygon' ? 'Teilfläche ' . ($nr + 1) . ': ' : '';
        if (count($polygon) > 1) $melden('fehler', 'loch', $teil . 'Die Fläche hat ein Loch (innerer Umriss). Das EU-Informationssystem lehnt solche Flächen ab – bitte in zwei Flächen ohne Loch teilen lassen.');
        $ring = $polygon[0];
        foreach ($ring as $p) if (!$bereich($p)) { $melden('fehler', 'bereich', $teil . 'Koordinaten außerhalb des gültigen Bereichs (Breite ±90, Länge ±180) – vermutlich ein anderes Koordinatensystem.'); continue 2; }
        if (count($ring) < 4) { $melden('fehler', 'punkte', $teil . 'Zu wenige Punkte: eine Fläche braucht mindestens drei verschiedene Eckpunkte.'); continue; }
        $doppelt = count($ring) - 1 - count(array_unique(array_map(fn($p) => $p[0] . ' ' . $p[1], array_slice($ring, 0, -1))));
        if ($doppelt > 0) $melden('fehler', 'beruehrung', $teil . 'Der Umriss läuft ' . ($doppelt === 1 ? 'einen Punkt' : $doppelt . ' Punkte') . ' doppelt an (berührt sich selbst).');
        $schnitt = geo_selbstschnitt($ring, $abbruch);
        if ($abbruch) $melden('fehler', 'komplex', $teil . 'Der Umriss ist zu verschachtelt, um ihn auf Selbstüberschneidung zu prüfen – bitte vom Lieferanten vereinfachen lassen.');
        elseif ($schnitt) $melden('fehler', 'schnitt', $teil . 'Der Umriss überschneidet sich selbst (Kante ' . $schnitt[0] . ' mit Kante ' . $schnitt[1] . ').');
        elseif (abs(geo_ring_eben($ring)) < GEO_LINIE) $melden('fehler', 'linie', $teil . 'Die Punkte liegen auf einer Linie und ergeben keine Fläche.');
        elseif (($dorn = geo_dorn($ring)) !== null) $melden('hinweis', 'dorn', $teil . 'Sehr spitze Ecke bei Punkt ' . $dorn . ' (Umriss läuft fast auf sich selbst zurück) – bitte auf der Karte ansehen.');
    }
    return $befunde;
}

/* Zahl der Punkte einer Geometrie (für die Obergrenzen je Anfrage und im Speicher) */
function geo_punktzahl(array $g): int
{
    $n = $g['type'] === 'Point' ? 1 : 0;
    foreach (geo_polygone($g) as $polygon) foreach ($polygon as $ring) $n += count($ring);
    return $n;
}
