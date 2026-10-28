<?php
declare(strict_types=1);
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Adressen → Koordinaten auf dem eigenen Server (Plattformkern, genutzt von der CRM-Karte)

   Schlägt Straße + Hausnummer + PLZ/Ort in einem Adressverzeichnis aus OpenStreetMap nach (ODbL; erzeugt von
   deploy/karte/adressen.py, geladen mit deploy/adressen-laden.sh). Keine Anfrage an fremde Dienste: die Datei liegt
   nur lesend im Container (/var/www/karte/adressen.sqlite, Umgebungsvariable WA_ADRESSEN für Tests) und wird nie
   ausgeliefert. Fehlt sie, liefert adressen_punkt() null – die Karte nimmt dann wie bisher den PLZ-Mittelpunkt.

   Genauigkeit: 'haus' (Hausnummer gefunden; ohne Treffer auch die Nummer ohne Zusatz, 12a → 12) oder 'strasse'
   (Mittel aller bekannten Adressen der Straße). Die Schreibweisen-Regeln (adressen_norm_*) müssen zu
   deploy/karte/adressen.py passen – gemeinsame Prüffälle: tests/fixtures/karte/normalisierung.json. */

const ADRESSEN_FORMAT = '1';
const ADRESSEN_FAKTOR = 100000;   // Koordinaten in der Datei: Grad × 100000
const ADRESSEN_ZEICHEN = ['ä' => 'ae', 'ö' => 'oe', 'ü' => 'ue', 'ß' => 'ss', 'é' => 'e', 'è' => 'e', 'ê' => 'e', 'ë' => 'e',
    'á' => 'a', 'à' => 'a', 'â' => 'a', 'å' => 'a', 'ç' => 'c', 'í' => 'i', 'ì' => 'i', 'î' => 'i', 'ï' => 'i', 'ñ' => 'n',
    'ó' => 'o', 'ò' => 'o', 'ô' => 'o', 'ø' => 'o', 'ú' => 'u', 'ù' => 'u', 'û' => 'u', 'ý' => 'y', 'æ' => 'ae', 'œ' => 'oe',
    'ł' => 'l', 'š' => 's', 'ž' => 'z', 'č' => 'c'];

/* ---------- Schreibweisen (wie deploy/karte/adressen.py) ---------- */
function adressen_klein(string $s): string
{
    return strtr(mb_strtolower($s, 'UTF-8'), ADRESSEN_ZEICHEN);
}
function adressen_norm_text(string $s): string
{
    return (string)preg_replace('/[^a-z0-9]/', '', adressen_klein($s));
}
function adressen_norm_strasse(string $s): string
{
    $s = (string)preg_replace('/str\.?(?![a-z])/', 'strasse', adressen_klein($s));
    return (string)preg_replace('/[^a-z0-9]/', '', $s);
}
function adressen_norm_nr(string $s): string
{
    return (string)preg_replace('/[^0-9a-z\/-]/', '', mb_strtolower($s, 'UTF-8'));
}
function adressen_norm_plz(string $s): string
{
    $s = (string)preg_replace('/\D/', '', $s);
    return strlen($s) === 5 ? $s : '';
}
/* Straßenfeld der Stammdaten („Hauptstr. 12 a“, „Am Markt 3-5“) → [Straße, Hausnummer]; ohne Nummer: [Straße, ''] */
function adressen_teilen(string $feld): array
{
    $feld = trim(preg_replace('/\s+/u', ' ', $feld) ?? '');
    if (preg_match('/^(.*\D)\s*,?\s+(\d+\s?[a-zA-Z]?(?:\s?[-\/]\s?\d+\s?[a-zA-Z]?)?)$/u', $feld, $m) && trim($m[1], " ,") !== '') {
        return [trim($m[1], ' ,'), $m[2]];
    }
    return [$feld, ''];
}

/* ---------- Verzeichnis ---------- */
function adressen_pfad(): string
{
    $p = getenv('WA_ADRESSEN');
    return is_string($p) && $p !== '' ? $p : '/var/www/karte/adressen.sqlite';
}
/* Verbindung (nur lesend) oder null, wenn die Datei fehlt oder ein unbekanntes Format hat */
function adressen_db(): ?PDO
{
    static $db = false;
    if ($db !== false) return $db;
    $db = null;
    $pfad = adressen_pfad();
    if (!is_file($pfad) || !is_readable($pfad)) return null;
    try {
        $p = new PDO('sqlite:' . $pfad, null, null, [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION, PDO::SQLITE_ATTR_OPEN_FLAGS => PDO::SQLITE_OPEN_READONLY]);
        $f = $p->query("SELECT wert FROM info WHERE schluessel = 'format'")->fetchColumn();
        if ((string)$f === ADRESSEN_FORMAT) $db = $p;
    } catch (Throwable $e) {
        $db = null;
    }
    return $db;
}
/* Stand des Verzeichnisses für die Oberfläche: ['adressen' => n, 'erzeugt' => 'JJJJ-MM-TT'] oder null */
function adressen_stand(): ?array
{
    $db = adressen_db();
    if (!$db) return null;
    $i = [];
    foreach ($db->query('SELECT schluessel, wert FROM info') as $r) $i[(string)$r['schluessel']] = (string)$r['wert'];
    return ['adressen' => (int)($i['adressen'] ?? 0), 'erzeugt' => (string)($i['erzeugt'] ?? '')];
}

/* Koordinate einer Anschrift: ['lat' => …, 'lon' => …, 'genau' => 'haus'|'strasse'] oder null (unbekannt/keine Datei) */
function adressen_punkt(string $strasseFeld, string $plz, string $ort): ?array
{
    $db = adressen_db();
    if (!$db) return null;
    [$name, $nr] = adressen_teilen($strasseFeld);
    $n = adressen_norm_strasse($name);
    if ($n === '') return null;
    $p = adressen_norm_plz($plz);
    $o = adressen_norm_text($ort);
    static $q = null;
    if ($q === null) {
        $q = [
            'plz' => $db->prepare('SELECT id, ort, lat, lon, anzahl FROM strassen WHERE plz = ? AND name = ?'),
            'ort' => $db->prepare('SELECT id, plz, lat, lon, anzahl FROM strassen WHERE ort = ? AND name = ?'),
            'nr' => $db->prepare('SELECT lat, lon FROM adressen WHERE strasse = ? AND nr = ?'),
        ];
    }
    // Straßen-Kandidaten: zuerst gleiche PLZ (passender Ort zuerst), sonst gleicher Ort ohne PLZ in OpenStreetMap
    $kand = [];
    if ($p !== '') {
        $q['plz']->execute([$p, $n]);
        $kand = $q['plz']->fetchAll(PDO::FETCH_ASSOC);
        usort($kand, function ($a, $b) use ($o) { return [(int)($b['ort'] === $o), (int)$b['anzahl']] <=> [(int)($a['ort'] === $o), (int)$a['anzahl']]; });
    }
    $ortKand = [];
    if ($o !== '') {
        $q['ort']->execute([$o, $n]);
        $ortKand = $q['ort']->fetchAll(PDO::FETCH_ASSOC);
        if (!$kand) {
            // Ohne PLZ-Treffer nur eindeutige Straßen: Einträge ohne PLZ, oder genau eine PLZ (sonst andere Stadtteile)
            $kand = array_values(array_filter($ortKand, function ($s) use ($p, $ortKand) { return $s['plz'] === '' || $p === '' && count($ortKand) === 1; }));
        }
    }
    // Hausnummer: genau, dann ohne Zusatz (12a → 12, 3-5 → 3); zusätzlich in Einträgen derselben Straße im Ort ohne PLZ
    // (gleichnamige Straßen anderer Stadtteile mit eigener PLZ bleiben außen vor)
    $nrn = [];
    $nn = adressen_norm_nr($nr);
    if ($nn !== '') {
        $nrn[] = $nn;
        if (preg_match('/^(\d+[a-z]?)/', $nn, $m)) $nrn[] = $m[1];
        if (preg_match('/^(\d+)/', $nn, $m)) $nrn[] = $m[1];
        $nrn = array_values(array_unique($nrn));
    }
    $suche = $kand;
    foreach ($ortKand as $s) if ($s['plz'] === '' && !in_array($s['id'], array_column($suche, 'id'), true)) $suche[] = $s;
    foreach ($nrn as $x) {
        foreach ($suche as $s) {
            $q['nr']->execute([(int)$s['id'], $x]);
            $r = $q['nr']->fetch(PDO::FETCH_ASSOC);
            if ($r) return ['lat' => (int)$r['lat'] / ADRESSEN_FAKTOR, 'lon' => (int)$r['lon'] / ADRESSEN_FAKTOR, 'genau' => 'haus'];
        }
    }
    if ($kand) return ['lat' => (int)$kand[0]['lat'] / ADRESSEN_FAKTOR, 'lon' => (int)$kand[0]['lon'] / ADRESSEN_FAKTOR, 'genau' => 'strasse'];
    return null;
}
