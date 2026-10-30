<?php
declare(strict_types=1);
/* Qualitätssicherung · Vorlagen und Lenkungsangaben in Word- und Excel-Dateien (Bauabschnitt 3, nur bei Bedarf geladen von
   app/api/aktionen/qs.php). Neue Arbeitsanweisungen, Formblätter, Listen und Excel-Dokumente entstehen aus einer Vorlage (Art
   „V“, z. B. „Vorlage F“): die Datei der gültigen Vorlagen-Version wird kopiert, Platzhalter wie {{Nr}} und {{Titel}} werden
   ausgefüllt, die Datei liegt danach im Entwurf. Bei der Freigabe trägt der Server die Lenkungsangaben ein ({{Version}},
   {{Datum}}, {{Erstellt}}, {{Geprüft}}, {{Freigegeben}} …) und legt die ausgefüllte Fassung neben der Rohfassung ab (Feld „roh“
   in der Datei; eine Überarbeitung übernimmt die Rohfassung mit ihren Platzhaltern). Vorlagen selbst werden nie ausgefüllt.

   Platzhalter: {{Name}} in Text von Word (Dokument, Kopf- und Fußzeilen – auch über mehrere Textstücke verteilt, wie Word
   sie beim Tippen zerlegt) und Excel (Zellen, Kopf- und Fußzeilen). Groß/Klein, Umlaute und Leerzeichen egal; unbekannte
   Namen bleiben stehen. Unterstützt: .docx, .dotx, .xlsx, .xltx, .xlsm (Office Open XML); .dotx/.xltx werden beim Erzeugen
   zu .docx/.xlsx. ZIP ohne PHP-Erweiterung „zip“: gelesen werden nur die Textteile, alle anderen Einträge (Bilder, Makros)
   werden unverändert übernommen. Grenzen gegen ZIP-Bomben: höchstens 2000 Einträge, je Textteil 30 MB entpackt. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar
require_once __DIR__ . '/../../lib/dateiablage.php';

const QS_OFFICE = ['docx' => 'word', 'dotx' => 'word', 'xlsx' => 'excel', 'xltx' => 'excel', 'xlsm' => 'excel'];
const QS_OFFICE_DOKUMENT = ['dotx' => 'docx', 'xltx' => 'xlsx'];   // Vorlagendatei → Dokument
const QS_ZIP_EINTRAEGE = 2000;
const QS_ZIP_TEIL_MAX = 30 * 1024 * 1024;
/* Platzhalter (Schlüssel ohne Umlaute, Leerzeichen und Satzzeichen) → Feld */
const QS_PLATZHALTER = ['nr' => 'nr', 'nummer' => 'nr', 'doknr' => 'nr', 'dokumentennr' => 'nr', 'dokumentnr' => 'nr', 'titel' => 'titel',
    'kapitel' => 'kapitel', 'art' => 'art', 'zustaendig' => 'zustaendig', 'vertreter' => 'vertreter', 'version' => 'version', 'datum' => 'datum',
    'freigabedatum' => 'datum', 'erstellt' => 'erstellt', 'geprueft' => 'geprueft', 'freigegeben' => 'freigegeben', 'aenderungen' => 'aenderungen',
    'aenderung' => 'aenderungen', 'grund' => 'grund', 'aenderungsgrund' => 'grund'];
const QS_PLATZHALTER_TEXT = ['nr' => 'Nr', 'titel' => 'Titel', 'kapitel' => 'Kapitel', 'art' => 'Art', 'zustaendig' => 'Zuständig', 'vertreter' => 'Vertreter',
    'version' => 'Version', 'datum' => 'Datum', 'erstellt' => 'Erstellt', 'geprueft' => 'Geprüft', 'freigegeben' => 'Freigegeben', 'aenderungen' => 'Änderungen',
    'grund' => 'Grund'];
const QS_PLATZHALTER_RE = '/\{\{\s*([^{}<>]{1,40}?)\s*\}\}/u';

/* ---------- Werte der Platzhalter ---------- */
function qs_platzhalter_feld(string $name): ?string
{
    $k = strtr(mb_strtolower($name), ['ä' => 'ae', 'ö' => 'oe', 'ü' => 'ue', 'ß' => 'ss']);
    $k = preg_replace('/[^a-z0-9]+/', '', $k) ?? '';
    return QS_PLATZHALTER[$k] ?? null;
}
function qs_werte_stamm(array $d, array $stamm): array
{
    $kt = ''; foreach ($stamm['kapitel'] as $k) if ((string)$k['id'] === (string)$d['kapitel']) $kt = (string)$k['titel'];
    return ['nr' => (string)$d['nr'], 'titel' => (string)$d['titel'], 'kapitel' => trim($d['kapitel'] . ' ' . $kt), 'art' => QS_ARTEN[$d['art']] ?? (string)$d['art'],
            'zustaendig' => (string)($d['zustaendig'] ?? ''), 'vertreter' => (string)($d['vertreter'] ?? '')];
}
/* Wer (Kürzel aus der Verknüpfung, sonst Schnappschuss-Kürzel, sonst Name) */
function qs_wer_kurz(array $stamm, $wer, $kuerzel): string
{
    if (is_array($wer)) {
        $k = qs_kuerzel_von($stamm, (string)($wer['vonId'] ?? ''));
        if ($k) return $k[0];
    }
    if (is_string($kuerzel) && $kuerzel !== '') return $kuerzel;
    return is_array($wer) ? (string)($wer['von'] ?? '') : '';
}
function qs_werte_lenkung(array $d, array $v, array $stamm): array
{
    $k = is_array($v['kuerzel'] ?? null) ? $v['kuerzel'] : [];
    $dat = (string)($v['datum'] ?? '');
    return qs_werte_stamm($d, $stamm) + ['version' => (string)($v['nr'] ?? ''), 'datum' => $dat !== '' ? substr($dat, 8, 2) . '.' . substr($dat, 5, 2) . '.' . substr($dat, 0, 4) : '',
        'erstellt' => qs_wer_kurz($stamm, $v['erstellt'] ?? null, $k['erstellt'] ?? null), 'geprueft' => qs_wer_kurz($stamm, $v['geprueft'] ?? null, $k['geprueft'] ?? null),
        'freigegeben' => qs_wer_kurz($stamm, $v['freigegeben'] ?? null, $k['freigegeben'] ?? null),
        'aenderungen' => (string)($v['aenderungen'] ?? ''), 'grund' => (string)($v['grund'] ?? '')];
}

/* ---------- ZIP lesen und schreiben (Office Open XML) ---------- */
/* Einträge in Reihenfolge: name → [methode, crc, komp, roh, flags, pos (Beginn der gepackten Daten in $z)] oder null, wenn kein
   lesbares ZIP. Die Daten selbst bleiben in $z (kein zweites Exemplar im Speicher). */
function qs_zip_lesen(string $z): ?array
{
    $n = strlen($z);
    if ($n < 22) return null;
    $ab = max(0, $n - 65557);
    $e = strrpos(substr($z, $ab), "PK\x05\x06");
    if ($e === false) return null;
    $e += $ab;
    $k = unpack('vdisk/vcddisk/vanz1/vanz/Vcdgroesse/Vcdpos', substr($z, $e + 4, 16));
    if ($k['anz'] > QS_ZIP_EINTRAEGE || $k['disk'] !== 0 || $k['cdpos'] >= $n) return null;
    $pos = $k['cdpos']; $aus = [];
    for ($i = 0; $i < $k['anz']; $i++) {
        if (substr($z, $pos, 4) !== "PK\x01\x02") return null;
        $c = unpack('vver/vbraucht/vflags/vmethode/vzeit/vdatum/Vcrc/Vkomp/Vroh/vnamelen/vextralen/vkommlen/vdisknr/vintattr/Vextattr/Vlocal', substr($z, $pos + 4, 42));
        $name = substr($z, $pos + 46, $c['namelen']);
        $pos += 46 + $c['namelen'] + $c['extralen'] + $c['kommlen'];
        if (($c['flags'] & 1) || $c['komp'] === 0xFFFFFFFF || $c['roh'] === 0xFFFFFFFF || $c['local'] === 0xFFFFFFFF) return null;   // verschlüsselt oder Zip64
        if (!in_array($c['methode'], [0, 8], true) || $name === '' || isset($aus[$name])) return null;
        $l = $c['local'];
        if (substr($z, $l, 4) !== "PK\x03\x04") return null;
        $lh = unpack('vnamelen/vextralen', substr($z, $l + 26, 4));
        $start = $l + 30 + $lh['namelen'] + $lh['extralen'];
        if ($start + $c['komp'] > $n) return null;
        $aus[$name] = ['methode' => $c['methode'], 'crc' => $c['crc'], 'komp' => $c['komp'], 'roh' => $c['roh'], 'flags' => $c['flags'] & 0x0800, 'pos' => $start];
    }
    return $aus;
}
/* Inhalt eines Eintrags entpacken (Grenze gegen ZIP-Bomben, Prüfsumme) oder null */
function qs_zip_inhalt(string $z, array $e): ?string
{
    if ($e['roh'] > QS_ZIP_TEIL_MAX) return null;
    $daten = substr($z, $e['pos'], $e['komp']);
    if ($e['methode'] === 0) $t = $daten;
    elseif ($e['roh'] === 0) $t = '';
    else { $t = @gzinflate($daten, $e['roh']); if ($t === false) return null; }
    if (strlen($t) !== $e['roh'] || crc32($t) !== $e['crc']) return null;
    return $t;
}
/* ZIP schreiben: Einträge wie von qs_zip_lesen (gepackte Daten aus $z); mit 'neu' => Inhalt neu gepackt, sonst unverändert übernommen */
function qs_zip_bauen(array $eintraege, string $z): string
{
    $t = getdate();
    $zeit = ($t['hours'] << 11) | ($t['minutes'] << 5) | intdiv($t['seconds'], 2);
    $datum = (max(0, $t['year'] - 1980) << 9) | ($t['mon'] << 5) | $t['mday'];
    $aus = ''; $verz = ''; $anz = 0;
    foreach ($eintraege as $name => $e) {
        $name = (string)$name;
        if (array_key_exists('neu', $e)) {
            $roh = (string)$e['neu'];
            $gepackt = gzdeflate($roh, 6);
            $e = ['methode' => 8, 'crc' => crc32($roh), 'roh' => strlen($roh), 'daten' => $gepackt, 'komp' => strlen($gepackt), 'flags' => $e['flags'] ?? 0];
        } else $e['daten'] = substr($z, $e['pos'], $e['komp']);
        $flags = (preg_match('/[^\x20-\x7e]/', $name) ? 0x0800 : 0) | ($e['flags'] ?? 0);
        $kopf = "PK\x03\x04" . pack('vvvvvVVVvv', 20, $flags, $e['methode'], $zeit, $datum, $e['crc'], $e['komp'], $e['roh'], strlen($name), 0) . $name;
        $verz .= "PK\x01\x02" . pack('vvvvvvVVVvvvvvVV', 20, 20, $flags, $e['methode'], $zeit, $datum, $e['crc'], $e['komp'], $e['roh'], strlen($name), 0, 0, 0, 0, 0, strlen($aus)) . $name;
        $aus .= $kopf . $e['daten'];
        $anz++;
    }
    return $aus . $verz . "PK\x05\x06" . pack('vvvvVVv', 0, 0, $anz, $anz, strlen($verz), strlen($aus), 0);
}

/* ---------- Platzhalter ersetzen ---------- */
/* Textstücke einer Gruppe (Absatz, Zelle): $seg = [['t' => Text], …]; ersetzt Platzhalter auch über Stückgrenzen.
   $offen sammelt bekannte, aber nicht gefüllte Platzhalter. Rückgabe: Anzahl ersetzt. */
function qs_stuecke_ersetzen(array &$seg, array $werte, array &$offen): int
{
    $voll = ''; $start = [];
    foreach ($seg as $i => $s) { $start[$i] = strlen($voll); $voll .= $s['t']; }
    if (strpos($voll, '{{') === false || !preg_match_all(QS_PLATZHALTER_RE, $voll, $mm, PREG_SET_ORDER | PREG_OFFSET_CAPTURE)) return 0;
    $n = 0;
    foreach (array_reverse($mm) as $m) {
        $feld = qs_platzhalter_feld($m[1][0]);
        if ($feld === null) continue;
        if (!array_key_exists($feld, $werte)) { $offen[$feld] = true; continue; }
        $s = $m[0][1]; $e = $s + strlen($m[0][0]); $erst = true;
        foreach ($seg as $i => $x) {
            $a = $start[$i]; $b = $a + strlen($x['t']);   // Grenzen der Originalstücke (Ersetzungen weiter hinten verschieben sie nicht)
            if ($b <= $s) continue;
            if ($a >= $e) break;
            $von = max($s, $a) - $a; $bis = min($e, $b) - $a;
            $seg[$i]['t'] = substr($seg[$i]['t'], 0, $von) . ($erst ? (string)$werte[$feld] : '') . substr($seg[$i]['t'], $bis);
            $seg[$i]['neu'] = true;
            $erst = false;
        }
        $n++;
    }
    return $n;
}
/* XML mit Gruppen (<w:p>/<si>/<is>) und Textelementen (<w:t>/<t>): Platzhalter je Gruppe ersetzen */
function qs_xml_ersetzen(string $xml, string $gruppe, string $tt, array $werte, array &$offen, int &$n): string
{
    $re = '#<' . $gruppe . '(?=[\s>/])[^>]*>|</' . $gruppe . '>|<' . $tt . '(?=[\s>])([^>]*)>(.*?)</' . $tt . '>#s';
    if (strpos($xml, '{{') === false || !preg_match_all($re, $xml, $mm, PREG_SET_ORDER | PREG_OFFSET_CAPTURE)) return $xml;
    $stapel = [[]]; $aenderungen = [];
    $abschliessen = function (array $seg) use ($werte, &$offen, &$n, &$aenderungen, $tt) {
        $k = $seg ? qs_stuecke_ersetzen($seg, $werte, $offen) : 0;
        if ($k === 0) return;
        foreach ($seg as $s) {
            if (empty($s['neu'])) continue;
            $attr = $s['attr'];
            if (preg_match('/^\s|\s$/u', $s['t']) && strpos($attr, 'xml:space') === false) $attr .= ' xml:space="preserve"';
            $aenderungen[] = [$s['pos'], $s['laenge'], '<' . $tt . $attr . '>' . htmlspecialchars($s['t'], ENT_XML1 | ENT_QUOTES, 'UTF-8') . '</' . $tt . '>'];
        }
        $n += $k;
    };
    foreach ($mm as $m) {
        $tag = $m[0][0];
        if (strncmp($tag, '</', 2) === 0) { if (count($stapel) > 1) $abschliessen(array_pop($stapel)); }
        elseif (isset($m[2]) && $m[2][1] >= 0 && strncmp($tag, '<' . $tt, strlen($tt) + 1) === 0 && !preg_match('#^<' . $gruppe . '[\s>/]#', $tag)) {
            $stapel[count($stapel) - 1][] = ['pos' => $m[0][1], 'laenge' => strlen($tag), 'attr' => $m[1][0], 't' => html_entity_decode($m[2][0], ENT_QUOTES | ENT_XML1, 'UTF-8')];
        } elseif (substr($tag, -2) !== '/>') $stapel[] = [];
    }
    while ($stapel) $abschliessen(array_pop($stapel));
    usort($aenderungen, function ($a, $b) { return $b[0] <=> $a[0]; });
    foreach ($aenderungen as [$pos, $laenge, $neu]) $xml = substr_replace($xml, $neu, $pos, $laenge);
    return $xml;
}
/* Kopf- und Fußzeilen in Excel (Text mit Steuerzeichen „&“: ein echtes & wird „&&“) */
function qs_excel_kopf_ersetzen(string $xml, array $werte, array &$offen, int &$n): string
{
    return preg_replace_callback('#<((?:odd|even|first)(?:Header|Footer))>(.*?)</\1>#s', function ($m) use ($werte, &$offen, &$n) {
        $t = html_entity_decode($m[2], ENT_QUOTES | ENT_XML1, 'UTF-8');
        $neu = preg_replace_callback(QS_PLATZHALTER_RE, function ($p) use ($werte, &$offen, &$n) {
            $feld = qs_platzhalter_feld($p[1]);
            if ($feld === null) return $p[0];
            if (!array_key_exists($feld, $werte)) { $offen[$feld] = true; return $p[0]; }
            $n++;
            return str_replace('&', '&&', (string)$werte[$feld]);
        }, $t) ?? $t;
        return $neu === $t ? $m[0] : '<' . $m[1] . '>' . htmlspecialchars($neu, ENT_XML1 | ENT_QUOTES, 'UTF-8') . '</' . $m[1] . '>';
    }, $xml) ?? $xml;
}
/* Word-/Excel-Datei ausfüllen. $werte: nur diese Felder werden ersetzt (andere bekannte Platzhalter bleiben und stehen in „offen“).
   $alsDokument: Vorlagendatei (.dotx/.xltx) wird zum Dokument. Rückgabe ['daten', 'ersetzt', 'offen' => [Feld…]] oder null (nicht lesbar). */
function qs_office_fuellen(string $daten, string $art, array $werte, bool $alsDokument = false): ?array
{
    $typ = QS_OFFICE[$art] ?? null;
    if ($typ === null) return null;
    $z = qs_zip_lesen($daten);
    if ($z === null || !isset($z['[Content_Types].xml'])) return null;
    $n = 0; $offen = []; $geaendert = false;
    foreach ($z as $name => $e) {
        $word = $typ === 'word' && preg_match('#^word/(document|header\d*|footer\d*)\.xml$#', $name);
        $strings = $typ === 'excel' && $name === 'xl/sharedStrings.xml';
        $blatt = $typ === 'excel' && preg_match('#^xl/worksheets/sheet\d+\.xml$#', $name);
        $typen = $alsDokument && $name === '[Content_Types].xml';
        if (!$word && !$strings && !$blatt && !$typen) continue;
        $xml = qs_zip_inhalt($daten, $e);
        if ($xml === null) return null;
        $vorher = $n; $neu = $xml;
        if ($word) $neu = qs_xml_ersetzen($xml, 'w:p', 'w:t', $werte, $offen, $n);
        elseif ($strings) $neu = qs_xml_ersetzen($xml, 'si', 't', $werte, $offen, $n);
        elseif ($blatt) $neu = qs_excel_kopf_ersetzen(qs_xml_ersetzen($xml, 'is', 't', $werte, $offen, $n), $werte, $offen, $n);
        else $neu = str_replace(['wordprocessingml.template.main+xml', 'spreadsheetml.template.main+xml'], ['wordprocessingml.document.main+xml', 'spreadsheetml.sheet.main+xml'], $xml);
        if ($neu !== $xml) { $z[$name]['neu'] = $neu; $geaendert = true; }
        elseif ($n !== $vorher) $geaendert = true;
    }
    return ['daten' => $geaendert ? qs_zip_bauen($z, $daten) : $daten, 'ersetzt' => $n, 'offen' => array_values(array_intersect(array_keys(QS_PLATZHALTER_TEXT), array_keys($offen)))];
}
/* Welche bekannten Platzhalter enthält die Datei? (für die Anzeige im Entwurf) – Liste der Felder oder null */
function qs_office_platzhalter(string $daten, string $art): ?array
{
    $r = qs_office_fuellen($daten, $art, []);
    return $r === null ? null : $r['offen'];
}

/* ---------- Anwenden ---------- */
/* Gültige Version einer Vorlage mit ihren Word-/Excel-Dateien (oder Fehler 422) */
function qs_vorlage_dateien(array $vd): array
{
    if (($vd['art'] ?? '') !== 'V') throw new InvalidArgumentException('Das gewählte Dokument ist keine Vorlage (Art „Vorlage“).');
    if (!empty($vd['eingezogen'])) throw new InvalidArgumentException('Die Vorlage ist eingezogen.');
    $gi = qs_ver_index($vd, ['freigegeben']);
    if ($gi === null) throw new InvalidArgumentException('Die Vorlage hat noch keine freigegebene Version.');
    $v = $vd['versionen'][$gi];
    $f = array_values(array_filter(qs_dateien_aktiv($v['dateien'] ?? []), function ($x) { return isset(QS_OFFICE[$x['art'] ?? '']); }));
    if (!$f) throw new InvalidArgumentException('Die gültige Version der Vorlage enthält keine Word- oder Excel-Datei (.docx, .dotx, .xlsx, .xltx, .xlsm).');
    return [$v, $f];
}
/* Neues Dokument aus der Vorlage: Dateien gefüllt mit den Stammangaben ablegen, Einträge für die erste Version zurückgeben.
   $erzeugt sammelt die neuen Kennungen (zum Aufräumen, falls das Speichern danach scheitert). */
function qs_vorlage_anwenden(array $vd, array $d, array $stamm, array $me, array &$erzeugt): array
{
    [$v, $dateien] = qs_vorlage_dateien($vd);
    $aus = [];
    foreach ($dateien as $f) {
        $daten = ablage_lesen('qs', (string)$f['id']);
        if ($daten === null) throw new InvalidArgumentException("Die Vorlagendatei „{$f['name']}“ fehlt in der Ablage.");
        $r = qs_office_fuellen($daten, (string)$f['art'], qs_werte_stamm($d, $stamm), true);
        if ($r === null) throw new InvalidArgumentException("Die Vorlagendatei „{$f['name']}“ ist keine lesbare Word- oder Excel-Datei.");
        $ext = QS_OFFICE_DOKUMENT[$f['art']] ?? (string)$f['art'];
        $abl = ablage_ablegen('qs', $r['daten']);
        $erzeugt[] = $abl['id'];
        $aus[] = ['id' => $abl['id'], 'name' => ablage_dateiname($d['nr'] . ' ' . $d['titel'] . '.' . $ext), 'art' => $ext, 'mime' => ABLAGE_ARTEN[$ext][0],
                  'groesse' => $abl['groesse'], 'sha256' => $abl['sha256'], 'hochgeladen' => qs_wer($me),
                  'vorlage' => ['dokument' => (string)$vd['id'], 'nr' => (string)$vd['nr'], 'version' => $v['nr'] ?? null], 'platzhalter' => $r['offen']];
    }
    return $aus;
}
/* Bei der Freigabe: Lenkungsangaben in die Word-/Excel-Dateien der Version eintragen (nicht bei Vorlagen). Die ausgefüllte
   Fassung bekommt eine neue Kennung, die Rohfassung bleibt als „roh“. Nicht lesbare Dateien bleiben unverändert (Verlauf). */
function qs_lenkung_eintragen(array $d, array &$v, array $stamm, array $me, array &$erzeugt): void
{
    foreach ((array)($v['dateien'] ?? []) as $k => $f) $v['dateien'][$k] = qs_lenkung_datei($d, $v, $f, $stamm, $me, $erzeugt);
}
/* Eine Datei einer freigegebenen Version ausfüllen (auch beim Nachtragen); unverändert, wenn nicht nötig oder nicht lesbar */
function qs_lenkung_datei(array $d, array &$v, array $f, array $stamm, array $me, array &$erzeugt): array
{
    if (!in_array($d['art'] ?? '', QS_NR_STRUKTUR, true) || !empty($f['entfernt']) || !isset(QS_OFFICE[$f['art'] ?? '']) || !empty($f['roh'])) return $f;
    $daten = ablage_lesen('qs', (string)$f['id']);
    $r = $daten === null ? null : qs_office_fuellen($daten, (string)$f['art'], qs_werte_lenkung($d, $v, $stamm));
    if ($r === null) { qs_verlauf($v, $me, 'Lenkungsangaben in „' . $f['name'] . '“ nicht eingetragen (Datei nicht lesbar)'); return $f; }
    if ($r['ersetzt'] === 0) return $f;
    $abl = ablage_ablegen('qs', $r['daten']);
    $erzeugt[] = $abl['id'];
    $neu = array_merge($f, ['id' => $abl['id'], 'groesse' => $abl['groesse'], 'sha256' => $abl['sha256'], 'roh' => (string)$f['id'], 'sha256Roh' => (string)($f['sha256'] ?? ''),
                            'ausgefuellt' => ['t' => now(), 'felder' => $r['ersetzt']]]);
    unset($neu['platzhalter']);
    return $neu;
}
/* Überarbeitung: Dateien der gültigen Version (Rohfassung mit Platzhaltern) als Kopie in den neuen Entwurf */
function qs_dateien_uebernehmen(array $g, array $me, array &$erzeugt): array
{
    $aus = [];
    foreach (qs_dateien_aktiv($g['dateien'] ?? []) as $f) {
        $quelle = (string)($f['roh'] ?? $f['id']);
        $k = ablage_kopieren('qs', $quelle);
        if ($k === null) continue;
        $erzeugt[] = $k['id'];
        $neu = ['id' => $k['id'], 'name' => (string)$f['name'], 'art' => (string)$f['art'], 'mime' => (string)($f['mime'] ?? ''), 'groesse' => $k['groesse'],
                'sha256' => $k['sha256'], 'hochgeladen' => qs_wer($me), 'uebernommen' => $g['nr'] ?? null];
        if (isset(QS_OFFICE[$f['art']])) { $p = qs_office_platzhalter((string)ablage_lesen('qs', $k['id']), (string)$f['art']); if ($p) $neu['platzhalter'] = $p; }
        $aus[] = $neu;
    }
    return $aus;
}
/* Neu erzeugte Dateien wieder entfernen, wenn das Speichern scheitert (Aufruf am Ende der Anfrage) */
function qs_erzeugte_aufraeumen(array &$erzeugt, bool &$fertig): void
{
    register_shutdown_function(function () use (&$erzeugt, &$fertig) {
        if ($fertig) return;
        foreach ($erzeugt as $id) { try { ablage_entfernen('qs', $id); } catch (Throwable $e) { /* bleibt liegen */ } }
    });
}
