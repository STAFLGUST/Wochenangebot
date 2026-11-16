<?php
declare(strict_types=1);
/* QM-System · Dokumentenablage: Regeln je Stelle, Archiv der Ordner und externen Dokumente, Eingang und Ordner-Import
   (eingebunden von module/qs/qs.php, Aktionen in aktionen/qs.php). Die Dateien selbst liegen in der Dateiablage des
   Plattformkerns (lib/dateiablage.php, Bereich „qs“). Wo welche Metadaten stehen, welche Regeln gelten und wie der
   Ordner-Import zuordnet, steht an einer Stelle: docs/entwickler/05-daten.md, Abschnitt „QM-System: Dokumentenablage“. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const QS_MAX_DATEIEN = 1000;      // aktive Dateien je Version
const QS_MAX_ORDNER = 10000;      // aktive Dateien je Ordner/externem Dokument
const QS_MAX_EINGANG = 20000;     // aktive Dateien im Eingang
const QS_MAX_ABLAGE = 50000;      // shortcut: jeder Schreibvorgang schreibt qs-ablage ganz (50 000 ≈ 0,5–0,8 s), darüber in Teildokumente aufteilen
const QS_MAX_VERWORFEN = 20000;   // gemerkte Prüfsummen endgültig gelöschter Eingangsdateien
const QS_IMPORT_MAX = 30000;      // Dateien je Lauf des Ordner-Imports
const QS_IMPORT_BUENDEL = 100;    // fertige Uploads je Schreibvorgang (qs_import_eintragen)
const QS_EINGANG = 'eingang';     // Ziel „Eingang“ in qs-ablage
const QS_WEITERE = 'Weitere Dateien';   // Ordner-Dokument für Dateien direkt im Kapitelordner
const QS_BEREICH_AB = 90;         // Kennungen neuer Bereiche (Kapitel mit „bereich“)
const QS_KAPITEL_RE = '/^(\d{1,2}(?:\.\d{1,2}){0,2})(?:\s|$)/';
const QS_FREMD_RE = '/^(?:_|alt_|alt$)/i';
const QS_EXPORT_UNTER = ['_ältere Versionen', '_Entwurf'];   // Unterordner des eigenen ZIP-Exports

function qs_dateien_aktiv($liste): array
{
    return array_values(array_filter(is_array($liste) ? $liste : [], function ($f) { return is_array($f) && empty($f['entfernt']); }));
}

/* ---------- Regeln je Stelle ---------- */
/* Darf $me an dieser Stelle Dateien ablegen ('hochladen'), aus dem Eingang zuordnen ('zuordnen') oder entfernen ('entfernen')?
   $d = Dokument oder null für den Eingang, $ver = Version-ID ('' am Ordner/externen Dokument), $belegt = aktive Dateien am Ordner,
   externen Dokument bzw. im Eingang, $neu = so viele kommen dazu. Rückgabe [Index der Version oder null, Fehlertext oder null, HTTP-Status]. */
function qs_ablage_regel(?array $d, string $ver, array $me, string $was, int $belegt = 0, int $neu = 1): array
{
    if ($d === null) {
        if ($ver !== '') return [null, 'Der Eingang hat keine Versionen.', 422];
        if ($was === 'entfernen') return [null, 'Dateien im Eingang werden zugeordnet oder gelöscht.', 409];
        if ($belegt + $neu > QS_MAX_EINGANG) return [null, 'Der Eingang ist voll (höchstens ' . QS_MAX_EINGANG . ' Dateien) – bitte zuerst zuordnen oder löschen.', 422];
        return [null, null, 200];
    }
    if (!empty($d['eingezogen'])) return [null, 'Das Dokument ist eingezogen – die Ablage ist geschlossen.', 409];
    if (!in_array($d['art'] ?? '', QS_GELENKT, true)) {
        if ($ver !== '') return [null, 'Ordner und externe Dokumente haben keine Versionen.', 422];
        if ($was !== 'entfernen' && $belegt + $neu > QS_MAX_ORDNER) return [null, 'Zu viele Dateien (höchstens ' . QS_MAX_ORDNER . ' je Ordner).', 422];
        return [null, null, 200];
    }
    $vi = null;
    foreach ((array)($d['versionen'] ?? []) as $i => $v) if (($v['id'] ?? '') === $ver && $ver !== '') $vi = $i;
    if ($vi === null) return [null, 'Version nicht gefunden.', 404];
    $st = (string)$d['versionen'][$vi]['status'];
    if (in_array($st, ['pruefung', 'geprueft'], true)) return [null, 'Die Überarbeitung liegt zur Prüfung vor – Dateien lassen sich nur im Entwurf ändern (zurückgeben lassen).', 409];
    if ($st === 'verworfen') return [null, 'Die Version ist verworfen.', 409];
    if (in_array($st, ['freigegeben', 'ersetzt'], true)) {
        if ($was === 'zuordnen') return [null, 'Aus dem Eingang wird nur Ordnern, externen Dokumenten und Entwürfen zugeordnet – zu einer freigegebenen Version bitte nachtragen.', 409];
        if (!may($me, 'qs.freigeben')) return [null, 'Dateien einer freigegebenen Version trägt nur nach oder entfernt, wer prüfen und freigeben darf.', 403];
    }
    if ($was !== 'entfernen' && count(qs_dateien_aktiv($d['versionen'][$vi]['dateien'] ?? [])) + $neu > QS_MAX_DATEIEN) return [null, 'Zu viele Dateien (höchstens ' . QS_MAX_DATEIEN . ').', 422];
    return [$vi, null, 200];
}
function qs_ablage_stelle(?array $d, string $ver, array $me, string $was, int $belegt = 0, int $neu = 1): ?int
{
    [$vi, $fehler, $code] = qs_ablage_regel($d, $ver, $me, $was, $belegt, $neu);
    if ($fehler !== null) fail($fehler, $code);
    return $vi;
}
/* Aktive Dateien eines Ordners/externen Dokuments: ältere in qs-dokumente (dateien) und die in qs-ablage ($je aus qs_ablage_je) */
function qs_ablage_belegt(?array $d, array $je): int
{
    return $d === null ? (int)($je[QS_EINGANG]['dateien'] ?? 0) : count(qs_dateien_aktiv($d['dateien'] ?? [])) + (int)($je[(string)$d['id']]['dateien'] ?? 0);
}
/* Einstellungen für die Oberfläche: erlaubte Dateiendungen und Größen (vom Plattformkern), Grenzen je Stelle */
function qs_ablage_einstellungen(): array
{
    require_once __DIR__ . '/vorlagen.php';
    return ['arten' => array_keys(ABLAGE_ARTEN), 'max' => ABLAGE_DATEI_MAX, 'teil' => ABLAGE_TEIL_MAX, 'dateien' => QS_MAX_DATEIEN, 'ordner' => QS_MAX_ORDNER,
            'eingang' => QS_MAX_EINGANG, 'importMax' => QS_IMPORT_MAX, 'buendel' => QS_IMPORT_BUENDEL,
            'office' => array_keys(QS_OFFICE), 'platzhalter' => QS_PLATZHALTER_TEXT, 'nrStruktur' => QS_NR_STRUKTUR];
}

/* ---------- qs-ablage und qs-ablage-zahlen ---------- */
/* Zahl und Bytes der aktiven Dateien je Ziel */
function qs_ablage_je(array $liste): array
{
    $je = [];
    foreach ($liste as $f) if (empty($f['entfernt'])) {
        $z = (string)$f['ziel'];
        $je[$z]['dateien'] = ($je[$z]['dateien'] ?? 0) + 1;
        $je[$z]['bytes'] = ($je[$z]['bytes'] ?? 0) + (int)($f['groesse'] ?? 0);
    }
    return $je;
}
/* qs-ablage schreiben und qs-ablage-zahlen neu zählen – immer beide, unter der Sperre „qs-dokumente“ */
function qs_ablage_schreiben(array $ab): void
{
    $ab['liste'] = array_values($ab['liste']);
    $ab['verworfen'] = array_slice(array_values(array_unique($ab['verworfen'] ?? [])), -QS_MAX_VERWORFEN);
    qs_schreiben('qs-ablage', $ab);
    qs_schreiben('qs-ablage-zahlen', ['rev' => $ab['rev'], 'je' => qs_ablage_je($ab['liste'])]);
}
function qs_ablage_zahlen(): array
{
    $d = store_read('qs-ablage-zahlen');
    return is_array($d['je'] ?? null) ? $d['je'] : [];
}
/* Eintrag einer hochgeladenen Datei (Version oder qs-ablage); pfad nur, wenn gesetzt */
function qs_datei_eintrag(array $datei, array $me, string $pfad): array
{
    return ['id' => (string)$datei['id'], 'name' => (string)$datei['name'], 'art' => (string)$datei['art'], 'mime' => (string)$datei['mime'], 'groesse' => (int)$datei['groesse'],
            'sha256' => (string)$datei['sha256'], 'hochgeladen' => qs_wer($me)] + ($pfad !== '' ? ['pfad' => $pfad] : []);
}
/* Ordnerpfad „pfad“ (Anzeige, Ordnerbaum, Suche – nie ein Pfad im Dateisystem), Format in 05-daten.md */
function qs_pfad($v): string
{
    $teile = [];
    foreach (preg_split('~[/\\\\]+~', is_string($v) ? $v : '') ?: [] as $t) {
        $t = trim(preg_replace('/[\p{Cc}\x{FEFF}]/u', '', preg_replace('/\s+/u', ' ', $t) ?? '') ?? '');
        if ($t !== '' && $t !== '.' && $t !== '..') $teile[] = mb_substr($t, 0, 120);
    }
    $p = implode('/', array_slice($teile, 0, 12));
    while (strlen($p) > 500 && ($k = strrpos($p, '/')) !== false) $p = substr($p, 0, $k);
    return $p;
}
/* Auswahl im Eingang: eindeutige Datei-Kennungen (als Text, auch wenn sie nur aus Ziffern bestehen) */
function qs_ablage_auswahl($v): array
{
    if (!is_array($v) || !$v || count($v) > QS_MAX_EINGANG) throw new InvalidArgumentException('Bitte Dateien aus dem Eingang wählen.');
    foreach ($v as $x) if (!is_string($x) || !preg_match('/^[a-z0-9]{12,40}$/D', $x)) throw new InvalidArgumentException('Ungültige Datei-Kennung.');
    return array_map('strval', array_keys(array_flip($v)));
}
/* Kennungen aller Dateien in qs-dokumente (auch Rohfassungen ausgefüllter Dateien) */
function qs_dokumente_dateien(array $liste): array
{
    $ids = [];
    foreach ($liste as $d) {
        foreach ((array)($d['dateien'] ?? []) as $f) $ids[(string)$f['id']] = true;
        foreach ((array)($d['versionen'] ?? []) as $v) foreach ((array)($v['dateien'] ?? []) as $f) { $ids[(string)$f['id']] = true; if (!empty($f['roh'])) $ids[(string)$f['roh']] = true; }
    }
    return $ids;
}

/* ---------- Eintragen: Version (qs-dokumente) oder qs-ablage ---------- */
/* Datei $f in die Version $vi eintragen. Im Entwurf zählen $me und wer die Datei hochgeladen hat als Bearbeiter (4-Augen-Prinzip);
   an freigegebenen Versionen wird nachgetragen (Lenkungsangaben gleich eingetragen, dann unter neuer Kennung). Platzhalter ermittelt
   der Aufrufer vor der Sperre. Rückgabe [Dokument, Kennung der abgelegten Datei]. */
function qs_datei_eintragen(array $d, int $vi, array $me, array $f, array &$erzeugt): array
{
    require_once __DIR__ . '/vorlagen.php';
    $v = $d['versionen'][$vi];
    $v['dateien'] = is_array($v['dateien'] ?? null) ? array_values($v['dateien']) : [];
    if ($v['status'] === 'entwurf') {
        $b = array_map('strval', (array)($v['bearbeiter'] ?? []));
        foreach ([(string)$me['id'], (string)($f['hochgeladen']['vonId'] ?? '')] as $id) if ($id !== '' && !in_array($id, $b, true)) $b[] = $id;
        $v['bearbeiter'] = $b;
    } else {
        $f['nachgetragen'] = true;
        $f = qs_lenkung_datei($d, $v, $f, qs_stamm(), $me, $erzeugt);
    }
    $v['dateien'][] = $f;
    $d['versionen'][$vi] = $v;
    return [$d, (string)$f['id']];
}
/* Ein Verlaufseintrag je Vorgang: im Entwurf an der Version, an freigegebenen Versionen auch am Dokument (nachgetragen) */
function qs_ablage_vermerk(array &$d, int $vi, array $me, array $namen, string $wie): void
{
    $n = count($namen);
    $was = $n === 1 ? 'Datei' : "$n Dateien";
    $name = $n === 1 ? ': ' . $namen[0] : '';
    if ($d['versionen'][$vi]['status'] === 'entwurf') { qs_verlauf($d['versionen'][$vi], $me, "$was $wie$name"); return; }
    qs_verlauf($d['versionen'][$vi], $me, "$was nachgetragen$name");
    qs_verlauf($d, $me, "$was zu Version " . ($d['versionen'][$vi]['nr'] ?? '?') . " nachgetragen$name");
}
/* Hochgeladene Dateien eintragen – eine Datei (qs_datei_hochladen) oder ein Bündel des Ordner-Imports (qs_import_eintragen).
   $neu: Liste ['datei' => aus ablage_teil, 'dokument' => Kennung oder „eingang“, 'version', 'pfad', 'herkunft', 'platzhalter'].
   Ohne $import bricht ein gesperrtes Ziel ab (fail); mit $import kommt die Datei in den Eingang, und gleiche Dateien (Prüfsumme) und
   früher im Eingang gelöschte werden nicht abgelegt. Ein Schreibvorgang je Dokument; Rückgabe [je Eintrag Ergebnis, qs-dokumente]. */
function qs_ablage_eintragen(array $neu, array $me, bool $import, array &$erzeugt): array
{
    $doc = qs_doc('qs-dokumente'); $ab = qs_doc('qs-ablage');
    $pos = []; foreach ($doc['liste'] as $i => $d) $pos[(string)$d['id']] = $i;
    $je = qs_ablage_je($ab['liste']);
    $verworfen = array_flip($ab['verworfen'] ?? []);
    $da = []; foreach ($ab['liste'] as $f) $da[$f['ziel'] . "\n" . ($f['pfad'] ?? '') . "\n" . $f['name'] . "\n" . $f['sha256']] = (string)$f['id'];
    $aus = []; $namen = []; $abNeu = false;
    foreach ($neu as $n => $e) {
        $f = qs_datei_eintrag($e['datei'], $me, (string)$e['pfad']) + (!empty($e['platzhalter']) ? ['platzhalter' => $e['platzhalter']] : []);
        if ($import && isset($verworfen[$f['sha256']])) { $aus[$n] = ['status' => 'verworfen']; continue; }
        $dok = (string)$e['dokument']; $i = $pos[$dok] ?? null; $grund = '';
        [$vi, $fehler, $code] = $dok !== QS_EINGANG && $i === null ? [null, 'Dokument nicht gefunden.', 404]
            : qs_ablage_regel($i === null ? null : $doc['liste'][$i], (string)$e['version'], $me, 'hochladen', qs_ablage_belegt($i === null ? null : $doc['liste'][$i], $je));
        if ($fehler !== null) {
            if (!$import) fail($fehler, $code);
            [$dok, $i, $vi, $grund] = [QS_EINGANG, null, null, $fehler];
            $f = ['pfad' => (string)($e['herkunft'] ?? '')] + $f;
            if ($f['pfad'] === '') unset($f['pfad']);
            unset($f['platzhalter']);
            [, $fehler] = qs_ablage_regel(null, '', $me, 'hochladen', qs_ablage_belegt(null, $je));
            if ($fehler !== null) { $aus[$n] = ['status' => 'fehler', 'grund' => $fehler]; continue; }
        }
        if ($vi !== null) {
            if ($import && ($gleich = qs_datei_gleich($doc['liste'][$i], $vi, $f['sha256'])) !== null) { $aus[$n] = ['status' => 'vorhanden', 'datei' => $gleich]; continue; }
            [$doc['liste'][$i], $f['id']] = qs_datei_eintragen($doc['liste'][$i], $vi, $me, $f, $erzeugt);
            $namen[$i][$vi][] = $f['name'];
        } else {
            $k = $dok . "\n" . ($f['pfad'] ?? '') . "\n" . $f['name'] . "\n" . $f['sha256'];
            if ($import && isset($da[$k])) { $aus[$n] = ['status' => 'vorhanden', 'datei' => $da[$k]]; continue; }
            if (count($ab['liste']) >= QS_MAX_ABLAGE) {
                if (!$import) fail('Die Dokumentenablage ist voll (höchstens ' . QS_MAX_ABLAGE . ' Dateien in Ordnern und im Eingang).', 422);
                $aus[$n] = ['status' => 'fehler', 'grund' => 'Die Dokumentenablage ist voll.']; continue;
            }
            $ab['liste'][] = $f + ['ziel' => $dok];
            $da[$k] = $f['id'];
            $je[$dok]['dateien'] = ($je[$dok]['dateien'] ?? 0) + 1;
            $abNeu = true;
        }
        $aus[$n] = ['status' => $grund !== '' ? 'eingang' : 'abgelegt', 'datei' => $f['id']] + ($grund !== '' ? ['grund' => $grund] : []);
    }
    // gelenkte Dokumente zuerst (im Dateimodus kein Eintrag in qs-ablage ohne gespeichertes Ziel), dann qs-ablage
    foreach ($namen as $i => $versionen) {
        foreach ($versionen as $vi => $l) qs_ablage_vermerk($doc['liste'][$i], $vi, $me, $l, $import ? 'abgelegt (Ordner-Import)' : 'abgelegt');
        $doc['liste'][$i]['rev'] = (int)($doc['liste'][$i]['rev'] ?? 0) + 1;
        $doc['liste'][$i]['geaendert'] = qs_wer($me);
    }
    if ($namen) qs_schreiben('qs-dokumente', $doc);
    if ($abNeu) qs_ablage_schreiben($ab);
    return [$aus, $doc['liste']];
}
/* Liegt in dieser Version schon eine aktive Datei mit diesem Inhalt (SHA-256, auch Rohfassung)? Kennung oder null */
function qs_datei_gleich(array $d, int $vi, string $sha): ?string
{
    if (!preg_match('/^[0-9a-f]{64}$/D', $sha)) return null;
    foreach (qs_dateien_aktiv($d['versionen'][$vi]['dateien'] ?? []) as $f)
        if (hash_equals($sha, (string)($f['sha256'] ?? '')) || hash_equals($sha, (string)($f['sha256Roh'] ?? ''))) return (string)$f['id'];
    return null;
}

/* ---------- Eingang ---------- */
/* Dateien aus dem Eingang zuordnen: an einen Ordner/ein externes Dokument ändert sich nur „ziel“ (ein Schreibvorgang), in einen
   Entwurf wandert der Eintrag nach qs-dokumente (zuerst das Ziel, dann qs-ablage). Alles oder nichts. Rückgabe [Dokument, Rest im Eingang]. */
function qs_eingang_zuordnen(array $ids, string $dok, string $ver, array $me, array $platzhalter, array &$erzeugt): array
{
    $doc = qs_doc('qs-dokumente'); $ab = qs_doc('qs-ablage');
    $i = qs_dokument_index($doc, $dok); $d = $doc['liste'][$i];
    $wahl = array_flip($ids); $treffer = [];
    foreach ($ab['liste'] as $k => $f) if (isset($wahl[(string)$f['id']]) && ($f['ziel'] ?? '') === QS_EINGANG && empty($f['entfernt'])) $treffer[$k] = $f;
    if (count($treffer) !== count($ids)) fail('Mindestens eine Datei liegt nicht (mehr) im Eingang.', 404);
    $je = qs_ablage_je($ab['liste']);
    $vi = qs_ablage_stelle($d, $ver, $me, 'zuordnen', qs_ablage_belegt($d, $je), count($ids));
    if ($vi === null) foreach ($treffer as $k => $f) $ab['liste'][$k]['ziel'] = (string)$d['id'];
    else {
        foreach ($treffer as $k => $f) {
            unset($f['ziel']);
            if (!empty($platzhalter[$f['id']])) $f['platzhalter'] = $platzhalter[$f['id']];
            [$d] = qs_datei_eintragen($d, $vi, $me, $f, $erzeugt);
            unset($ab['liste'][$k]);
        }
        qs_ablage_vermerk($d, $vi, $me, array_column($treffer, 'name'), 'aus dem Eingang zugeordnet');
        $d = qs_dok_ablegen($doc, $i, $d, $me);
    }
    qs_ablage_schreiben($ab);
    return [$d, (int)(qs_ablage_je($ab['liste'])[QS_EINGANG]['dateien'] ?? 0)];
}
/* Dateien im Eingang endgültig löschen: Einträge weg, Prüfsummen gemerkt (ein erneuter Import legt sie nicht wieder ab).
   Rückgabe [Kennungen, deren Dateien gelöscht werden dürfen, Rest im Eingang] – nie eine, die qs-dokumente noch verwendet. */
function qs_eingang_loeschen(array $ids): array
{
    $ab = qs_doc('qs-ablage');
    $wahl = array_flip($ids); $weg = []; $rest = [];
    foreach ($ab['liste'] as $f) {
        if (isset($wahl[(string)$f['id']]) && ($f['ziel'] ?? '') === QS_EINGANG && empty($f['entfernt'])) $weg[] = $f;
        else $rest[] = $f;
    }
    if (count($weg) !== count($ids)) fail('Mindestens eine Datei liegt nicht (mehr) im Eingang.', 404);
    $ab['liste'] = $rest;
    $ab['verworfen'] = array_merge($ab['verworfen'] ?? [], array_column($weg, 'sha256'));
    qs_ablage_schreiben($ab);
    $benutzt = qs_dokumente_dateien(qs_doc('qs-dokumente')['liste']);
    return [array_values(array_filter(array_map('strval', array_column($weg, 'id')), function ($id) use ($benutzt) { return !isset($benutzt[$id]); })),
            (int)(qs_ablage_je($rest)[QS_EINGANG]['dateien'] ?? 0)];
}

/* ---------- Archiv: Dateien eines Ordners/externen Dokuments ---------- */
/* Ältere Dateien am Dokument (qs-dokumente) und die in qs-ablage zusammen – für Ordnerbaum, Download, ZIP */
function qs_archiv_dateien(array $d, array $ablage): array
{
    $l = (array)($d['dateien'] ?? []);
    foreach ($ablage as $f) if (($f['ziel'] ?? '') === (string)$d['id']) $l[] = $f;
    return $l;
}
/* Datei für Ordnerbaum und Eingang (ohne Prüfsumme und Dateiart – hält die Antwort klein) */
function qs_archiv_antwort(array $f): array
{
    return ['id' => (string)$f['id'], 'name' => (string)$f['name'], 'groesse' => (int)($f['groesse'] ?? 0), 'pfad' => (string)($f['pfad'] ?? ''),
            'hochgeladen' => ['t' => (string)($f['hochgeladen']['t'] ?? ''), 'von' => (string)($f['hochgeladen']['von'] ?? '')]]
        + (!empty($f['entfernt']) ? ['entfernt' => ['t' => (string)$f['entfernt']['t'], 'von' => (string)$f['entfernt']['von'], 'grund' => (string)($f['entfernt']['grund'] ?? '')]] : []);
}
/* Datei eines Ordners/externen Dokuments in qs-ablage als „entfernt“ vermerken (mit Grund; die Datei bleibt). Im Eingang: 409.
   Rückgabe wie qs_datei_entfernen: [Dokument, Name, ''] */
function qs_archiv_entfernen(array $doc, string $id, array $b, array $me): array
{
    $ab = qs_doc('qs-ablage');
    $k = null;
    foreach ($ab['liste'] as $j => $f) if ((string)$f['id'] === $id) $k = $j;
    if ($k === null) fail('Datei nicht gefunden.', 404);
    $f = $ab['liste'][$k];
    $d = $f['ziel'] === QS_EINGANG ? null : $doc['liste'][qs_dokument_index($doc, $f['ziel'])];
    qs_ablage_stelle($d, '', $me, 'entfernen');
    if (!empty($f['entfernt'])) fail('Die Datei ist schon entfernt.', 409);
    $grund = qs_text($b['grund'] ?? '', 500, 'Grund');
    if ($grund === '') throw new InvalidArgumentException('Bitte einen Grund angeben – die Datei bleibt als „entfernt“ vermerkt.');
    $ab['liste'][$k]['entfernt'] = qs_wer($me) + ['grund' => $grund];
    qs_ablage_schreiben($ab);
    return [$d, (string)$f['name'], ''];
}
function qs_dateien_text(int $n): string { return $n === 1 ? '1 Datei' : "$n Dateien"; }
/* Datei in qs-ablage suchen: Eintrag oder null */
function qs_ablage_finden(array $ablage, string $id): ?array
{
    foreach ($ablage as $f) if ((string)($f['id'] ?? '') === $id) return $f;
    return null;
}
/* Datei in qs-dokumente suchen: [Dokument-Index, Version-Index oder null, Datei-Index] oder null */
function qs_datei_finden(array $liste, string $id): ?array
{
    if (!preg_match('/^[a-z0-9]{12,40}$/D', $id)) return null;
    foreach ($liste as $i => $d) {
        foreach ((array)($d['dateien'] ?? []) as $k => $f) if (($f['id'] ?? '') === $id) return [$i, null, $k];
        foreach ((array)($d['versionen'] ?? []) as $j => $v) foreach ((array)($v['dateien'] ?? []) as $k => $f) if (($f['id'] ?? '') === $id) return [$i, $j, $k];
    }
    return null;
}
/* Zahl der aktiven Dateien in qs-dokumente und qs-ablage (Datenpaket: ersetzt nicht, sobald Dateien liegen) */
function qs_dateien_zahl(array $liste): int
{
    $n = array_sum(array_column(qs_ablage_zahlen(), 'dateien'));
    foreach ($liste as $d) {
        $n += count(qs_dateien_aktiv($d['dateien'] ?? []));
        foreach ((array)($d['versionen'] ?? []) as $v) $n += count(qs_dateien_aktiv($v['dateien'] ?? []));
    }
    return $n;
}
/* ZIP-Pfad einer Archivdatei unter dem Ordner des Dokuments: <pfad>/<Datei> */
function qs_archiv_zip_pfad(array $f): string
{
    $teile = array_map('ablage_zip_pfad', array_filter(explode('/', (string)($f['pfad'] ?? '')), 'strlen'));
    return implode('/', array_merge($teile, [ablage_zip_pfad((string)$f['name'])]));
}
/* Einträge für den ZIP-Export „QM-System/<Kapitel>/<Dokument>/<Datei>“: gültige Version bzw. Archivdateien (mit Unterordnern aus pfad);
   mit $alle zusätzlich ältere Versionen und offene Entwürfe in Unterordnern. Eingezogene Dokumente nur mit $alle (Ordner „_eingezogen“).
   Dazu die Dokumentenliste als CSV. */
function qs_ablage_eintraege(array $dokumente, array $ablage, array $stamm, string $kapitel, bool $alle, string $heute): array
{
    $kt = []; foreach ($stamm['kapitel'] as $k) $kt[(string)$k['id']] = (string)$k['titel'];
    $wurzel = 'QM-System';
    $e = [];
    $gewaehlt = array_values(array_filter($dokumente, function ($d) use ($kapitel) { return $kapitel === '' || (string)$d['kapitel'] === $kapitel; }));
    usort($gewaehlt, function ($a, $b) { return qs_nat_cmp((string)$a['kapitel'], (string)$b['kapitel']) ?: strnatcasecmp((string)$a['nr'], (string)$b['nr']); });
    $je = []; foreach ($ablage as $f) $je[(string)$f['ziel']][] = $f;
    foreach ($gewaehlt as $d) {
        $eingezogen = !empty($d['eingezogen']);
        if ($eingezogen && !$alle) continue;
        $kap = ablage_zip_pfad(trim($d['kapitel'] . ' ' . ($kt[$d['kapitel']] ?? '')));
        $ordner = $wurzel . '/' . ($eingezogen ? '_eingezogen/' : '') . $kap . '/' . ablage_zip_pfad(trim(($d['nr'] !== '' ? $d['nr'] . ' ' : '') . $d['titel']));
        foreach (qs_dateien_aktiv(array_merge((array)($d['dateien'] ?? []), $je[(string)$d['id']] ?? [])) as $f) $e[] = ['pfad' => $ordner . '/' . qs_archiv_zip_pfad($f), 'bereich' => 'qs', 'id' => (string)$f['id']];
        foreach ((array)($d['versionen'] ?? []) as $v) {
            $st = (string)($v['status'] ?? '');
            if ($st === 'freigegeben') $unter = '';
            elseif (!$alle || $st === 'verworfen') continue;
            elseif ($st === 'ersetzt') $unter = '/_ältere Versionen/Version ' . ($v['nr'] ?? '?');
            else $unter = '/_Entwurf';
            foreach (qs_dateien_aktiv($v['dateien'] ?? []) as $f) $e[] = ['pfad' => $ordner . $unter . '/' . ablage_zip_pfad((string)$f['name']), 'bereich' => 'qs', 'id' => (string)$f['id']];
        }
    }
    array_unshift($e, ['pfad' => $wurzel . '/Dokumentenliste.csv', 'inhalt' => qs_csv_dokumente($gewaehlt, $stamm, $heute)]);
    return $e;
}

/* ---------- Ordner-Import: Zuordnungsplan (Regeln in 05-daten.md, nur hier berechnet) ---------- */
function qs_norm(string $t): string { return mb_strtolower(trim(preg_replace('/\s+/u', ' ', $t) ?? '')); }
function qs_norm_trenner(string $t): string { return qs_norm(preg_replace('/[\s_\-]+/u', ' ', $t) ?? ''); }
/* Dokumenten-Nr. „<Kapitel>-<Art><Nr.>“ als Schlüssel („1.4-f01“ = „1.4-F1“) oder '' */
function qs_nr_schluessel(string $nr): string
{
    return preg_match('/^(\d+(?:\.\d+){0,3})\s*-\s*([A-Za-z])\s*0*(\d{1,3})$/D', trim($nr), $m) ? $m[1] . '-' . strtoupper($m[2]) . (int)$m[3] : '';
}
/* Ordnernamen eines Pfads aus dem Browser („/“ oder „\“ getrennt) */
function qs_import_teile(string $pfad): array
{
    return array_values(array_filter(preg_split('~[/\\\\]+~', $pfad) ?: [], 'strlen'));
}
/* Passt der Rest hinter der Nummer zum Dokument? Leer oder der Titel (Trenner Leerzeichen, „_“, „-“) */
function qs_import_rest_passt(string $rest, array $d): bool
{
    $r = qs_norm_trenner($rest);
    return $r === '' || $r === qs_norm_trenner((string)$d['titel']);
}
function qs_import_kapitel_passt(array $d, string $kap): bool
{
    return (string)$d['kapitel'] === $kap || explode('-', (string)$d['nr'])[0] === $kap;
}
/* Datei direkt im Kapitelordner: Name ohne Endung beginnt mit der Nummer, der Rest ist leer oder der Titel */
function qs_import_nr_dok(string $name, string $kap, array $nr, array $frei): ?array
{
    $basis = preg_replace('/\.[^.]*$/', '', $name) ?? $name;
    if (preg_match('/^(\d+(?:\.\d+){0,3})\s*-\s*([A-Za-z])\s*0*(\d{1,3})(?!\d)(.*)$/su', $basis, $m))
        foreach ($nr[$m[1] . '-' . strtoupper($m[2]) . (int)$m[3]] ?? [] as $d) if (qs_import_kapitel_passt($d, $kap) && qs_import_rest_passt($m[4], $d)) return $d;
    foreach ($frei as $d) {
        $n = (string)$d['nr'];
        if (mb_stripos($basis, $n) !== 0 || !qs_import_kapitel_passt($d, $kap)) continue;
        $rest = mb_substr($basis, mb_strlen($n));
        if (($rest === '' || preg_match('/^[\s_\-]/u', $rest)) && qs_import_rest_passt($rest, $d)) return $d;
    }
    return null;
}
/* Ziel eines gelenkten Dokuments: gültige Version (nachtragen, nur mit Freigaberecht) oder Entwurf; gesperrt → Eingang */
function qs_import_gelenkt(array $d, string $name, int $groesse, string $voll, array $me): array
{
    $gesperrt = function (string $grund) use ($voll) { return ['status' => 'eingang', 'ziel' => QS_EINGANG, 'pfad' => $voll, 'grund' => $grund]; };
    if (!empty($d['eingezogen'])) return $gesperrt('Dokument eingezogen');
    $g = qs_ver_index($d, ['freigegeben']); $o = qs_ver_index($d, QS_VER_OFFEN);
    if ($g !== null && !may($me, 'qs.freigeben')) return $gesperrt('gültige Version nur mit Freigaberecht');
    if ($g === null && ($o === null || $d['versionen'][$o]['status'] !== 'entwurf')) return $gesperrt($o !== null ? 'Entwurf liegt zur Prüfung' : 'noch ohne Version');
    $v = $d['versionen'][$g ?? $o];
    $da = false;
    foreach (qs_dateien_aktiv($v['dateien'] ?? []) as $f) if ((string)$f['name'] === $name && (int)$f['groesse'] === $groesse) $da = true;
    return ['status' => $g !== null ? 'nachtragen' : 'dokument', 'ziel' => (string)$d['id'], 'ver' => (string)$v['id']] + ($da ? ['schonDa' => true] : []);
}
/* Grund zum Überspringen (Systemdatei, Liste eines eigenen Exports, Dateiart, leer, zu groß) oder null */
function qs_import_ueberspringen(string $name, int $groesse, bool $oben): ?array
{
    if (preg_match('/^(\.|~\$)/', $name) || preg_match('/^(thumbs\.db|desktop\.ini)$/i', $name) || preg_match('/\.lnk$/i', $name)) return ['status' => 'system'];
    if ($oben && preg_match('/^(Dokumentenliste\.csv|Hinweise\.txt)$/i', $name)) return ['status' => 'export'];
    $endung = strtolower(pathinfo($name, PATHINFO_EXTENSION));
    if (!isset(ABLAGE_ARTEN[$endung])) return ['status' => 'art', 'grund' => $endung !== '' ? '.' . $endung : 'ohne Endung'];
    if ($groesse < 1) return ['status' => 'leer'];
    if ($groesse > ABLAGE_DATEI_MAX) return ['status' => 'gross'];
    return null;
}
/* Zuordnungsplan. $ordner: [[Ordnerpfad wie gewählt, [[Name, Größe], …]], …]; $wahl: oberster Ordner → {art: eingang|aus|kapitel|neu,
   kapitel, titel}. Rückgabe: wurzel (weggelassener gemeinsamer Ordner), oberste (Zuordnung je oberstem Ordner), dateien (je Datei in
   derselben Reihenfolge: status, ziel, ver, pfad, grund, schonDa), neu (anzulegende Ordner-Dokumente), bereiche (anzulegende Bereiche). */
function qs_import_plan(array $ordner, array $wahl, array $me, array $stamm, array $dokumente, array $ablage): array
{
    $kap = []; foreach ($stamm['kapitel'] as $k) $kap[(string)$k['id']] = $k;
    $erste = [];
    foreach ($ordner as $o) $erste[(string)(qs_import_teile((string)$o[0])[0] ?? '')] = true;
    $w = count($erste) === 1 ? (string)array_key_first($erste) : '';
    $wurzel = $w !== '' && !preg_match(QS_KAPITEL_RE, $w) && !preg_match(QS_FREMD_RE, $w) ? $w : '';
    // Zuordnung der obersten Ordner: Kapitelordner automatisch, sonst Wahl des Nutzers (Vorgabe Eingang)
    $oberste = []; $bereiche = [];
    foreach ($ordner as $o) {
        $t = qs_import_teile((string)$o[0]);
        if ($wurzel !== '') array_shift($t);
        if (!$t || isset($oberste[$t[0]])) continue;
        if (preg_match(QS_KAPITEL_RE, $t[0], $m) && isset($kap[$m[1]]) && empty($kap[$m[1]]['bereich'])) { $oberste[$t[0]] = ['art' => 'auto', 'kapitel' => $m[1]]; continue; }
        $x = is_array($wahl[$t[0]] ?? null) ? $wahl[$t[0]] : [];
        $z = ['art' => in_array($x['art'] ?? '', ['aus', 'kapitel', 'neu'], true) ? $x['art'] : 'eingang'];
        if ($z['art'] === 'kapitel') {
            $z['kapitel'] = (string)($x['kapitel'] ?? '');
            if (!isset($kap[$z['kapitel']])) throw new InvalidArgumentException('„' . mb_substr($t[0], 0, 60) . '“: unbekanntes Kapitel.');
        }
        if ($z['art'] === 'neu') {
            if (!may($me, 'qs.verwalten')) fail('Einen neuen Bereich legt nur an, wer das QM-System verwalten darf.', 403);
            $z['kapitel'] = rtrim(qs_text($x['kapitel'] ?? '', 12, 'Bereich'), '.');
            $z['titel'] = qs_text($x['titel'] ?? '', 120, 'Bereich');
            if (!preg_match('/^\d{1,2}(\.\d{1,2}){0,2}$/D', $z['kapitel']) || $z['titel'] === '') throw new InvalidArgumentException('Neuer Bereich: Nummer wie „90“ und Titel angeben.');
            if (isset($kap[$z['kapitel']]) || isset($bereiche[$z['kapitel']])) throw new InvalidArgumentException('Die Nummer ' . $z['kapitel'] . ' ist schon vergeben.');
            $bereiche[$z['kapitel']] = $z['titel'];
        }
        $oberste[$t[0]] = $z;
    }
    $naechste = QS_BEREICH_AB;
    while (isset($kap[(string)$naechste]) || isset($bereiche[(string)$naechste])) $naechste++;
    foreach ($oberste as $name => $z) if ($z['art'] !== 'auto') $oberste[$name]['vorschlag'] = ['kapitel' => (string)$naechste, 'titel' => trim(ltrim((string)$name, '_'))];
    // Verzeichnisse: Nummern gelenkter Dokumente, Ordnernamen des eigenen Exports, Ordner-Dokumente je Kapitel, schon Abgelegtes
    $nr = []; $frei = []; $export = []; $ordnerDok = []; $da = []; $irgendwo = []; $alt = [];
    foreach ($dokumente as $d) {
        if (in_array($d['art'] ?? '', QS_GELENKT, true)) {
            if (($s = qs_nr_schluessel((string)$d['nr'])) !== '') $nr[$s][] = $d; elseif ((string)$d['nr'] !== '') $frei[] = $d;
            $export[qs_norm(ablage_zip_pfad(trim($d['nr'] . ' ' . $d['titel'])))][] = $d;
            foreach ((array)($d['versionen'] ?? []) as $v) foreach (qs_dateien_aktiv($v['dateien'] ?? []) as $f) if (($f['pfad'] ?? '') !== '') $irgendwo[$f['pfad'] . "\n" . $f['name'] . "\n" . $f['groesse']] = true;
            continue;
        }
        $k = $d['kapitel'] . "\n" . qs_norm((string)$d['titel']);
        if (($d['art'] ?? '') === 'O' && (!isset($ordnerDok[$k]) || !empty($ordnerDok[$k]['eingezogen']))) $ordnerDok[$k] = $d;
        $alt[(string)$d['id']] = count(qs_dateien_aktiv($d['dateien'] ?? []));
        foreach ((array)($d['dateien'] ?? []) as $f) $da[$d['id'] . "\n\n" . $f['name'] . "\n" . $f['groesse']] = true;
    }
    usort($frei, function ($a, $b) { return mb_strlen((string)$b['nr']) <=> mb_strlen((string)$a['nr']); });
    foreach ($ablage as $f) {
        $da[$f['ziel'] . "\n" . ($f['pfad'] ?? '') . "\n" . $f['name'] . "\n" . $f['groesse']] = true;
        $irgendwo[($f['pfad'] ?? '') . "\n" . $f['name'] . "\n" . $f['groesse']] = true;
    }
    $belegt = qs_ablage_je($ablage);
    $plus = []; $neu = []; $neuIdx = []; $dateien = []; $zahl = 0;
    foreach ($ordner as $o) {
        if (!is_array($o) || !is_string($o[0] ?? null) || !is_array($o[1] ?? null)) throw new InvalidArgumentException('Ungültige Ordnerliste.');
        $t = qs_import_teile($o[0]);
        if ($wurzel !== '') array_shift($t);
        $z = $t ? $oberste[$t[0]] : ['art' => 'lose'];
        $voll = qs_pfad(implode('/', $t));
        $rel = array_slice($t, 1);
        $auto = $z['art'] === 'auto';
        $exportDok = null;
        if ($auto && $rel) foreach ($export[qs_norm($rel[0])] ?? [] as $d) if (qs_import_kapitel_passt($d, $z['kapitel'])) $exportDok = $d;
        foreach ($o[1] as $x) {
            if (++$zahl > QS_IMPORT_MAX) throw new InvalidArgumentException('Höchstens ' . QS_IMPORT_MAX . ' Dateien je Lauf – bitte Kapitel einzeln importieren.');
            $name = is_array($x) && is_string($x[0] ?? null) ? $x[0] : ''; $groesse = is_array($x) && is_int($x[1] ?? null) ? $x[1] : 0;
            $e = qs_import_ueberspringen($name, $groesse, $t === []);
            if ($e === null && in_array($z['art'], ['lose', 'eingang'], true)) $e = ['status' => 'eingang', 'ziel' => QS_EINGANG, 'pfad' => $voll] + ($z['art'] === 'lose' ? ['grund' => 'lose Datei'] : []);
            if ($e === null && $z['art'] === 'aus') $e = ['status' => 'aus'];
            if ($e === null && $exportDok && isset($rel[1]) && in_array($rel[1], QS_EXPORT_UNTER, true)) $e = ['status' => 'export'];
            if ($e === null && $auto && !$rel && ($d = qs_import_nr_dok($name, $z['kapitel'], $nr, $frei))) $e = qs_import_gelenkt($d, $name, $groesse, $voll, $me);
            if ($e === null && $exportDok && count($rel) === 1) $e = qs_import_gelenkt($exportDok, $name, $groesse, $voll, $me);
            if ($e === null) {   // Archiv: Ordner-Dokument je (Kapitel, Unterordner der ersten Ebene), tiefere Ebenen als pfad
                $titel = $rel ? qs_pfad($rel[0]) : QS_WEITERE;
                $k = $z['kapitel'] . "\n" . qs_norm($titel);
                $od = $ordnerDok[$k] ?? null;
                if ($od && !empty($od['eingezogen'])) $e = ['status' => 'eingang', 'ziel' => QS_EINGANG, 'pfad' => $voll, 'grund' => 'Ordner eingezogen'];
                elseif ($od && $alt[(string)$od['id']] + ($belegt[(string)$od['id']]['dateien'] ?? 0) + ($plus[(string)$od['id']] ?? 0) >= QS_MAX_ORDNER)
                    $e = ['status' => 'eingang', 'ziel' => QS_EINGANG, 'pfad' => $voll, 'grund' => 'Ordner voll'];
                else {
                    if (!$od && !isset($neuIdx[$k])) { $neuIdx[$k] = count($neu); $neu[] = ['kapitel' => $z['kapitel'], 'titel' => $titel]; }
                    $e = ['status' => 'ablage', 'ziel' => $od ? (string)$od['id'] : 'neu:' . $neuIdx[$k], 'pfad' => qs_pfad(implode('/', array_slice($rel, 1)))];
                }
            }
            // schon abgelegt: am Ziel (Archiv) oder irgendwo mit dem ganzen Ordnerpfad (Eingang, auch danach zugeordnet)
            if (in_array($e['status'], ['ablage', 'eingang', 'dokument', 'nachtragen'], true) && (isset($irgendwo[$voll . "\n" . $name . "\n" . $groesse])
                    || ($e['status'] === 'ablage' && isset($da[$e['ziel'] . "\n" . $e['pfad'] . "\n" . $name . "\n" . $groesse])))) $e['schonDa'] = true;
            if ($e['status'] === 'eingang' && empty($e['schonDa']) && ($belegt[QS_EINGANG]['dateien'] ?? 0) + ($plus[QS_EINGANG] ?? 0) >= QS_MAX_EINGANG) $e = ['status' => 'voll'];
            if (in_array($e['status'], ['ablage', 'eingang', 'dokument', 'nachtragen'], true) && empty($e['schonDa'])) $plus[$e['ziel']] = ($plus[$e['ziel']] ?? 0) + 1;
            $dateien[] = $e;
        }
    }
    $aus = [];
    foreach ($oberste as $name => $z) $aus[] = ['name' => (string)$name] + $z;
    return ['wurzel' => $wurzel, 'oberste' => $aus, 'dateien' => $dateien, 'neu' => $neu, 'bereiche' => $bereiche];
}
/* Bereiche und Ordner-Dokumente des Plans anlegen (unter der Sperre). Rückgabe: $wahl mit den neuen Bereichen als Kapitel */
function qs_import_anlegen(array $plan, array $wahl, array $me, array &$stamm, array &$doc): array
{
    if ($plan['bereiche']) {
        foreach ($plan['bereiche'] as $id => $titel) $stamm['kapitel'][] = ['id' => (string)$id, 'titel' => $titel, 'zustaendig' => '', 'vertreter' => '', 'aktiv' => true, 'bereich' => true];
        $stamm['kapitel'] = qs_kapitel_liste_pruefen($stamm['kapitel'], $stamm['kapitel'], []);
        qs_schreiben('qs-stamm', $stamm);
        $stamm = qs_stamm();
        foreach ($plan['oberste'] as $z) if ($z['art'] === 'neu') $wahl[$z['name']] = ['art' => 'kapitel', 'kapitel' => $z['kapitel']];
    }
    if ($plan['neu']) {
        if (count($doc['liste']) + count($plan['neu']) > QS_MAX_DOKUMENTE) fail('Zu viele Dokumente.', 422);
        foreach ($plan['neu'] as $n) {
            $d = ['id' => qs_id('d')] + qs_dokument_pruefen(['art' => 'O', 'kapitel' => $n['kapitel'], 'nr' => '', 'titel' => $n['titel']], null, $stamm, $doc['liste'])
                + ['erstellt' => qs_wer($me), 'quelle' => 'import', 'verlauf' => [], 'rev' => 1];
            qs_verlauf($d, $me, 'angelegt (Ordner-Import)');
            $doc['liste'][] = $d;
        }
        qs_schreiben('qs-dokumente', $doc);
    }
    return $wahl;
}
