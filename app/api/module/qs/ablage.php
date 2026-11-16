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
const QS_MAX_ABLAGE = 25000;      // shortcut: qs-ablage wird bei jedem Schreiben ganz gelesen und geschrieben (Plan und Bündel bleiben so unter 128 MB), darüber je Kapitel teilen
const QS_MAX_VERWORFEN = 20000;   // gemerkte Prüfsummen endgültig gelöschter Eingangsdateien
const QS_IMPORT_MAX = 30000;      // Dateien je Lauf des Ordner-Imports
const QS_IMPORT_BUENDEL = 100;    // fertige Uploads je Schreibvorgang (qs_import_eintragen)
const QS_IMPORT_BUENDEL_BYTES = 1024 * 1024 * 1024;   // Bytes je Bündel (so viel liegt höchstens fertig in .teile)
const QS_IMPORT_LENKUNG_BYTES = 40 * 1024 * 1024;     // Word/Excel-Nachträge je Bündel: die Lenkung läuft unter der Sperre
const QS_IMPORT_ABLEGEN = ['ablage', 'eingang', 'dokument', 'nachtragen'];   // Plan-Status, die hochgeladen werden
const QS_IMPORT_LISTE = 'Dokumentenliste.csv';   // ganz oben in der Auswahl = eigener ZIP-Export
const QS_EINGANG = 'eingang';     // Ziel „Eingang“ in qs-ablage
const QS_WEITERE = 'Weitere Dateien';   // Ordner-Dokument für Dateien direkt im obersten Ordner
const QS_BEREICH_AB = 90;         // Kennungen von Bereichen (Kapitel mit „bereich“): 90 bis 99
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
/* Einstellungen für die Oberfläche: erlaubte Dateiendungen und Größen (vom Plattformkern), Grenzen je Stelle und je Bündel */
function qs_ablage_einstellungen(): array
{
    require_once __DIR__ . '/vorlagen.php';
    return ['arten' => array_keys(ABLAGE_ARTEN), 'max' => ABLAGE_DATEI_MAX, 'teil' => ABLAGE_TEIL_MAX, 'dateien' => QS_MAX_DATEIEN, 'ordner' => QS_MAX_ORDNER,
            'eingang' => QS_MAX_EINGANG, 'importMax' => QS_IMPORT_MAX, 'buendel' => QS_IMPORT_BUENDEL, 'buendelBytes' => QS_IMPORT_BUENDEL_BYTES,
            'lenkungBytes' => QS_IMPORT_LENKUNG_BYTES, 'office' => array_keys(QS_OFFICE), 'platzhalter' => QS_PLATZHALTER_TEXT, 'nrStruktur' => QS_NR_STRUKTUR];
}

/* ---------- Leser beider Ablageorte: ältere Dateien am Ordner (qs-dokumente, „dateien“) und qs-ablage ----------
   Nur diese vier Funktionen lesen „dateien“ an Ordnern und externen Dokumenten (werkzeuge/qs_ablage_leser.py prüft das). */
/* Einträge von qs-ablage je Ziel (Index für qs_ordner_dateien) */
function qs_ablage_nach_ziel(array $ablage): array
{
    $je = [];
    foreach ($ablage as $f) $je[(string)$f['ziel']][] = $f;
    return $je;
}
/* Alle Dateien eines Ordners/externen Dokuments, auch entfernte: ältere am Dokument und die aus $index (qs_ablage_nach_ziel; leer = nur die älteren) */
function qs_ordner_dateien(array $d, array $index): array
{
    return array_merge(array_values((array)($d['dateien'] ?? [])), $index[(string)$d['id']] ?? []);
}
/* Aktive Dateien eines Ordners/externen Dokuments (ältere und $je aus qs_ablage_je bzw. qs-ablage-zahlen) bzw. des Eingangs ($d = null) */
function qs_ablage_belegt(?array $d, array $je): int
{
    return $d === null ? (int)($je[QS_EINGANG]['dateien'] ?? 0) : count(qs_dateien_aktiv($d['dateien'] ?? [])) + (int)($je[(string)$d['id']]['dateien'] ?? 0);
}
/* Datei suchen – in qs-dokumente (Versionen, ältere am Ordner), sonst in qs-ablage: [Datei, Dokument-Index, Version-Index, Index] oder null.
   Dokument-Index null: Eintrag in qs-ablage. Nach einem Abbruch beim Zuordnen kann eine Kennung an beiden Orten stehen – qs-dokumente zählt. */
function qs_datei_suchen(array $liste, string $id): ?array
{
    if (!preg_match('/^[a-z0-9]{12,40}$/D', $id)) return null;
    foreach ($liste as $i => $d) {
        foreach (qs_ordner_dateien($d, []) as $k => $f) if ((string)($f['id'] ?? '') === $id) return [$f, $i, null, $k];
        foreach ((array)($d['versionen'] ?? []) as $j => $v) foreach ((array)($v['dateien'] ?? []) as $k => $f) if ((string)($f['id'] ?? '') === $id) return [$f, $i, $j, $k];
    }
    foreach (qs_doc('qs-ablage')['liste'] as $k => $f) if ((string)($f['id'] ?? '') === $id) return [$f, null, null, $k];
    return null;
}

/* ---------- qs-ablage und qs-ablage-zahlen ---------- */
function qs_im_eingang(array $f): bool { return ($f['ziel'] ?? '') === QS_EINGANG && empty($f['entfernt']); }
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
/* Zahl und Bytes je Ordner/externem Dokument für qs_start: qs-ablage-zahlen und die älteren Dateien am Dokument (ohne Eingang) */
function qs_ablage_uebersicht(array $dokumente): array
{
    $je = array_diff_key(qs_ablage_zahlen(), [QS_EINGANG => true]);
    foreach ($dokumente as $d) if (!in_array($d['art'] ?? '', QS_GELENKT, true) && ($alt = qs_dateien_aktiv(qs_ordner_dateien($d, [])))) {
        $id = (string)$d['id'];
        $je[$id] = ['dateien' => (int)($je[$id]['dateien'] ?? 0) + count($alt), 'bytes' => (int)($je[$id]['bytes'] ?? 0) + array_sum(array_map('intval', array_column($alt, 'groesse')))];
    }
    return $je;
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
        foreach (qs_ordner_dateien($d, []) as $f) $ids[(string)$f['id']] = true;
        foreach ((array)($d['versionen'] ?? []) as $v) foreach ((array)($v['dateien'] ?? []) as $f) { $ids[(string)$f['id']] = true; if (!empty($f['roh'])) $ids[(string)$f['roh']] = true; }
    }
    return $ids;
}
/* Am Ende der Anfrage die hier abgelegten bzw. erzeugten Dateien entfernen, die nicht gespeichert sind – registriert vor dem Ablegen, damit
   auch ein Abbruch mittendrin aufräumt. $gespeichert setzt der Aufrufer, sobald der Schreibvorgang abgeschlossen ist; alles andere prüft sie
   gegen den gespeicherten Stand (nach einem Fehler ist im Dateimodus qs-dokumente womöglich schon geschrieben, SQLite setzt alles zurück). */
function qs_ablage_aufraeumen(array &$abgelegt, array &$erzeugt, array &$gespeichert): void
{
    register_shutdown_function(function () use (&$abgelegt, &$erzeugt, &$gespeichert) {
        $offen = array_values(array_filter(array_merge($abgelegt, $erzeugt), function ($id) use (&$gespeichert) { return !isset($gespeichert[$id]); }));
        if (!$offen) return;
        try { $benutzt = qs_dokumente_dateien(qs_doc('qs-dokumente')['liste']) + array_flip(array_map('strval', array_column(qs_doc('qs-ablage')['liste'], 'id'))); }
        catch (Throwable $e) { return; }   // Stand nicht lesbar: lieber liegen lassen
        foreach ($offen as $id) if (!isset($benutzt[$id])) { try { ablage_entfernen('qs', $id); } catch (Throwable $e) { /* bleibt liegen */ } }
    });
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
/* Hochgeladene Dateien eintragen (Kern für Upload und Ordner-Import, ohne fail()). $neu je Eintrag: datei (aus ablage_teil), ziel (Dokument
   oder „eingang“), version, pfad, platzhalter, grund und eingang – der Ordnerpfad im Eingang nur beim Ordner-Import: dann kommt ein gesperrtes
   Ziel in den Eingang, eine gleiche Datei am Ziel wird nicht abgelegt („vorhanden“), eine früher im Eingang gelöschte nicht wieder in den
   Eingang („verworfen“); ohne eingang (null) ist ein gesperrtes Ziel ein Fehler. Ein Schreibvorgang je Dokument, zuerst qs-dokumente, dann
   qs-ablage. Rückgabe [je Eintrag status abgelegt|eingang|vorhanden|verworfen|fehler mit datei bzw. grund und code, qs-dokumente]. */
function qs_ablage_eintragen(array $neu, array $me, string $wie, array &$erzeugt): array
{
    $doc = qs_doc('qs-dokumente'); $ab = qs_doc('qs-ablage');
    $pos = []; foreach ($doc['liste'] as $i => $d) $pos[(string)$d['id']] = $i;
    $je = qs_ablage_je($ab['liste']);
    $verworfen = array_flip($ab['verworfen'] ?? []);
    $da = []; foreach ($ab['liste'] as $f) $da[qs_import_schluessel((string)$f['ziel'], (string)($f['pfad'] ?? ''), (string)$f['name'], (string)$f['sha256'])] = (string)$f['id'];
    $aus = []; $namen = []; $abNeu = false;
    foreach ($neu as $n => $e) {
        $import = ($e['eingang'] ?? null) !== null;
        $f = qs_datei_eintrag($e['datei'], $me, (string)($e['pfad'] ?? '')) + (!empty($e['platzhalter']) ? ['platzhalter' => $e['platzhalter']] : []);
        $dok = (string)$e['ziel']; $i = $pos[$dok] ?? null; $grund = (string)($e['grund'] ?? '');
        [$vi, $fehler, $code] = $dok !== QS_EINGANG && $i === null ? [null, 'Dokument nicht gefunden.', 404]
            : qs_ablage_regel($i === null ? null : $doc['liste'][$i], (string)($e['version'] ?? ''), $me, 'hochladen', qs_ablage_belegt($i === null ? null : $doc['liste'][$i], $je));
        if ($fehler !== null && $import && $dok !== QS_EINGANG) {
            [$dok, $i, $grund] = [QS_EINGANG, null, $fehler];
            $f = qs_datei_eintrag($e['datei'], $me, (string)$e['eingang']);
            [$vi, $fehler, $code] = qs_ablage_regel(null, '', $me, 'hochladen', qs_ablage_belegt(null, $je));
        }
        if ($fehler !== null) { $aus[$n] = ['status' => 'fehler', 'grund' => $fehler, 'code' => $code]; continue; }
        if ($vi !== null) {
            if ($import && ($gleich = qs_datei_gleich($doc['liste'][$i], $vi, $f['sha256'])) !== null) { $aus[$n] = ['status' => 'vorhanden', 'datei' => $gleich]; continue; }
            [$doc['liste'][$i], $f['id']] = qs_datei_eintragen($doc['liste'][$i], $vi, $me, $f, $erzeugt);
            $namen[$i][$vi][] = $f['name'];
        } else {
            $k = qs_import_schluessel($dok, (string)($f['pfad'] ?? ''), $f['name'], $f['sha256']);
            if ($import && $dok === QS_EINGANG && isset($verworfen[$f['sha256']])) { $aus[$n] = ['status' => 'verworfen']; continue; }
            if ($import && isset($da[$k])) { $aus[$n] = ['status' => 'vorhanden', 'datei' => $da[$k]]; continue; }
            if (count($ab['liste']) >= QS_MAX_ABLAGE) { $aus[$n] = ['status' => 'fehler', 'grund' => 'Die Dokumentenablage ist voll (höchstens ' . QS_MAX_ABLAGE . ' Dateien in Ordnern und im Eingang).', 'code' => 422]; continue; }
            $ab['liste'][] = $f + ['ziel' => $dok];
            $da[$k] = $f['id'];
            $je[$dok]['dateien'] = ($je[$dok]['dateien'] ?? 0) + 1;
            $abNeu = true;
        }
        $aus[$n] = ['status' => $dok === QS_EINGANG ? 'eingang' : 'abgelegt', 'datei' => $f['id']] + ($grund !== '' ? ['grund' => $grund] : []);
    }
    // gelenkte Dokumente zuerst (im Dateimodus kein Eintrag in qs-ablage ohne gespeichertes Ziel), dann qs-ablage
    foreach ($namen as $i => $versionen) {
        foreach ($versionen as $vi => $l) qs_ablage_vermerk($doc['liste'][$i], $vi, $me, $l, $wie);
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
/* Dateien im Eingang für die Oberfläche (qs_eingang) */
function qs_eingang_dateien(): array
{
    return array_map('qs_archiv_antwort', array_values(array_filter(qs_doc('qs-ablage')['liste'], 'qs_im_eingang')));
}
/* Ziele, denen $me aus dem Eingang zuordnen darf (qs_ablage_regel 'zuordnen'): Ordner, externe Dokumente, Entwürfe – je {dok, ver} */
function qs_eingang_ziele(array $dokumente, array $me): array
{
    $aus = [];
    foreach ($dokumente as $d) {
        $gelenkt = in_array($d['art'] ?? '', QS_GELENKT, true);
        $o = $gelenkt ? qs_ver_index($d, QS_VER_OFFEN) : null;
        if ($gelenkt && $o === null) continue;
        $ver = $o === null ? '' : (string)$d['versionen'][$o]['id'];
        if (qs_ablage_regel($d, $ver, $me, 'zuordnen', 0, 0)[1] === null) $aus[] = ['dok' => (string)$d['id'], 'ver' => $ver];
    }
    return $aus;
}
/* Platzhalter der Word-/Excel-Dateien im Eingang, die in einen Entwurf zugeordnet werden – vor der Sperre gelesen */
function qs_eingang_platzhalter(array $ids): array
{
    require_once __DIR__ . '/vorlagen.php';
    $wahl = array_flip($ids); $aus = [];
    foreach (qs_doc('qs-ablage')['liste'] as $f) if (isset($wahl[(string)$f['id']]) && qs_im_eingang($f) && ($p = qs_platzhalter_vorab($f)) !== null) $aus[(string)$f['id']] = $p;
    return $aus;
}
/* Dateien aus dem Eingang zuordnen: an einen Ordner/ein externes Dokument ändert sich nur „ziel“ (ein Schreibvorgang), in einen
   Entwurf wandert der Eintrag nach qs-dokumente (zuerst das Ziel, dann qs-ablage; steht die Kennung nach einem Abbruch schon im Entwurf,
   wird sie nicht doppelt eingetragen). Alles oder nichts. Rückgabe [Dokument, Rest im Eingang]. */
function qs_eingang_zuordnen(array $ids, string $dok, string $ver, array $me, array $platzhalter, array &$erzeugt): array
{
    $doc = qs_doc('qs-dokumente'); $ab = qs_doc('qs-ablage');
    $i = qs_dokument_index($doc, $dok); $d = $doc['liste'][$i];
    $wahl = array_flip($ids); $treffer = [];
    foreach ($ab['liste'] as $k => $f) if (isset($wahl[(string)$f['id']]) && qs_im_eingang($f)) $treffer[$k] = $f;
    if (count($treffer) !== count($ids)) fail('Mindestens eine Datei liegt nicht (mehr) im Eingang.', 404);
    $je = qs_ablage_je($ab['liste']);
    $vi = qs_ablage_stelle($d, $ver, $me, 'zuordnen', qs_ablage_belegt($d, $je), count($ids));
    if ($vi === null) foreach ($treffer as $k => $f) $ab['liste'][$k]['ziel'] = (string)$d['id'];
    else {
        $schon = array_flip(array_map('strval', array_column((array)($d['versionen'][$vi]['dateien'] ?? []), 'id')));
        foreach ($treffer as $k => $f) {
            unset($f['ziel']);
            if (!empty($platzhalter[$f['id']])) $f['platzhalter'] = $platzhalter[$f['id']];
            if (!isset($schon[(string)$f['id']])) [$d] = qs_datei_eintragen($d, $vi, $me, $f, $erzeugt);
            unset($ab['liste'][$k]);
        }
        qs_ablage_vermerk($d, $vi, $me, array_column($treffer, 'name'), 'aus dem Eingang zugeordnet');
        $d = qs_dok_ablegen($doc, $i, $d, $me);
    }
    qs_ablage_schreiben($ab);
    return [$d, (int)(qs_ablage_je($ab['liste'])[QS_EINGANG]['dateien'] ?? 0)];
}
/* Dateien im Eingang endgültig löschen: Einträge weg, Prüfsummen gemerkt (ein erneuter Import legt sie nicht wieder in den Eingang).
   Rückgabe [Kennungen, deren Dateien gelöscht werden dürfen, Rest im Eingang] – nie eine, die qs-dokumente noch verwendet. */
function qs_eingang_loeschen(array $ids): array
{
    $ab = qs_doc('qs-ablage');
    $wahl = array_flip($ids); $weg = []; $rest = [];
    foreach ($ab['liste'] as $f) {
        if (isset($wahl[(string)$f['id']]) && qs_im_eingang($f)) $weg[] = $f;
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
/* Dateien eines Ordners/externen Dokuments (ältere und qs-ablage, auch entfernte) – für Ordnerbaum, ZIP */
function qs_archiv_dateien(array $d): array
{
    return qs_ordner_dateien($d, qs_ablage_nach_ziel(qs_doc('qs-ablage')['liste']));
}
/* Datei für Ordnerbaum und Eingang (ohne Prüfsumme und Dateiart – hält die Antwort klein) */
function qs_archiv_antwort(array $f): array
{
    return ['id' => (string)$f['id'], 'name' => (string)$f['name'], 'groesse' => (int)($f['groesse'] ?? 0), 'pfad' => (string)($f['pfad'] ?? ''),
            'hochgeladen' => ['t' => (string)($f['hochgeladen']['t'] ?? ''), 'von' => (string)($f['hochgeladen']['von'] ?? '')]]
        + (!empty($f['entfernt']) ? ['entfernt' => ['t' => (string)$f['entfernt']['t'], 'von' => (string)$f['entfernt']['von'], 'grund' => (string)($f['entfernt']['grund'] ?? '')]] : []);
}
/* Datei eines Ordners/externen Dokuments in qs-ablage als „entfernt“ vermerken (mit Grund; die Datei bleibt). Im Eingang: 409.
   Rückgabe wie in qs_datei_entfernen: [Dokument, Name, '', false] */
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
    return [$d, (string)$f['name'], '', false];
}
function qs_dateien_text(int $n): string { return $n === 1 ? '1 Datei' : "$n Dateien"; }
/* Zahl der aktiven Dateien in qs-dokumente und qs-ablage (Datenpaket: ersetzt nicht, sobald Dateien liegen) – qs-ablage direkt gezählt */
function qs_dateien_zahl(array $liste): int
{
    $n = count(qs_dateien_aktiv(qs_doc('qs-ablage')['liste']));
    foreach ($liste as $d) {
        $n += count(qs_dateien_aktiv(qs_ordner_dateien($d, [])));
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
   Dazu die Dokumentenliste als CSV (kennzeichnet beim Ordner-Import den eigenen Export). */
function qs_ablage_eintraege(array $dokumente, array $stamm, string $kapitel, bool $alle, string $heute): array
{
    $kt = []; foreach ($stamm['kapitel'] as $k) $kt[(string)$k['id']] = (string)$k['titel'];
    $wurzel = 'QM-System';
    $e = [];
    $gewaehlt = array_values(array_filter($dokumente, function ($d) use ($kapitel) { return $kapitel === '' || (string)$d['kapitel'] === $kapitel; }));
    usort($gewaehlt, function ($a, $b) { return qs_nat_cmp((string)$a['kapitel'], (string)$b['kapitel']) ?: strnatcasecmp((string)$a['nr'], (string)$b['nr']); });
    $index = qs_ablage_nach_ziel(qs_doc('qs-ablage')['liste']);
    foreach ($gewaehlt as $d) {
        $eingezogen = !empty($d['eingezogen']);
        if ($eingezogen && !$alle) continue;
        $kap = ablage_zip_pfad(trim($d['kapitel'] . ' ' . ($kt[$d['kapitel']] ?? '')));
        $ordner = $wurzel . '/' . ($eingezogen ? '_eingezogen/' : '') . $kap . '/' . ablage_zip_pfad(trim(($d['nr'] !== '' ? $d['nr'] . ' ' : '') . $d['titel']));
        foreach (qs_dateien_aktiv(qs_ordner_dateien($d, $index)) as $f) $e[] = ['pfad' => $ordner . '/' . qs_archiv_zip_pfad($f), 'bereich' => 'qs', 'id' => (string)$f['id']];
        foreach ((array)($d['versionen'] ?? []) as $v) {
            $st = (string)($v['status'] ?? '');
            if ($st === 'freigegeben') $unter = '';
            elseif (!$alle || $st === 'verworfen') continue;
            elseif ($st === 'ersetzt') $unter = '/_ältere Versionen/Version ' . ($v['nr'] ?? '?');
            else $unter = '/_Entwurf';
            foreach (qs_dateien_aktiv($v['dateien'] ?? []) as $f) $e[] = ['pfad' => $ordner . $unter . '/' . ablage_zip_pfad((string)$f['name']), 'bereich' => 'qs', 'id' => (string)$f['id']];
        }
    }
    array_unshift($e, ['pfad' => $wurzel . '/' . QS_IMPORT_LISTE, 'inhalt' => qs_csv_dokumente($gewaehlt, $stamm, $heute)]);
    return $e;
}

/* ---------- Ordner-Import (Regeln in 05-daten.md, nur hier berechnet) ----------
   Plan (qs_import_plan) und Eintragen (qs_import_eintragen) entscheiden jede Datei mit derselben reinen Funktion qs_import_datei. */
function qs_norm(string $t): string { return mb_strtolower(trim(preg_replace('/\s+/u', ' ', $t) ?? '')); }
function qs_norm_trenner(string $t): string { return qs_norm(preg_replace('/[\s_\-]+/u', ' ', $t) ?? ''); }
/* Schlüssel aus mehreren Teilen (Ordner-Dokument, schon Abgelegtes, gleiche Datei) */
function qs_import_schluessel(string ...$teile): string { return implode("\n", $teile); }
/* Dokumenten-Nr. „<Kapitel>-<Art><Nr.>“ als Schlüssel („1.4-f01“ = „1.4-F1“) oder '' */
function qs_nr_schluessel(string $nr): string
{
    return preg_match('/^(\d+(?:\.\d+){0,3})\s*-\s*([A-Za-z])\s*0*(\d{1,3})$/D', trim($nr), $m) ? $m[1] . '-' . strtoupper($m[2]) . (int)$m[3] : '';
}
/* Ordnernamen eines Pfads aus dem Browser („/“ oder „\“ getrennt); kein Text oder zu lang → 422 */
function qs_import_teile($pfad): array
{
    if (!is_string($pfad) || strlen($pfad) > 2000) throw new InvalidArgumentException('Ungültiger Ordnerpfad.');
    return array_values(array_filter(preg_split('~[/\\\\]+~', $pfad) ?: [], 'strlen'));
}
/* Ordnerliste der Anfrage [[Ordnerpfad wie gewählt, [[Name, Größe], …]], …] prüfen → [[Ordnerpfad, Ordnernamen, [[Name, Größe], …]], …] */
function qs_import_ordner_lesen($ordner): array
{
    if (!is_array($ordner)) throw new InvalidArgumentException('Ungültige Ordnerliste.');
    $aus = []; $n = 0;
    foreach ($ordner as $o) {
        if (!is_array($o) || !is_array($o[1] ?? null)) throw new InvalidArgumentException('Ungültige Ordnerliste.');
        $l = [];
        foreach ($o[1] as $x) {
            if (!is_array($x) || !is_string($x[0] ?? null) || $x[0] === '' || strlen($x[0]) > 255 || !is_int($x[1] ?? null) || $x[1] < 0) throw new InvalidArgumentException('Ungültige Ordnerliste.');
            $l[] = [$x[0], $x[1]];
        }
        if (($n += count($l)) > QS_IMPORT_MAX) throw new InvalidArgumentException('Höchstens ' . QS_IMPORT_MAX . ' Dateien je Lauf – bitte Kapitel einzeln importieren.');
        $aus[] = [$o[0], qs_import_teile($o[0] ?? null), $l];
    }
    return $aus;
}
/* Angaben des Nutzers (Plan und Eintragen): wurzel {name, art sf|kapitel|neu|'' (keine Antwort), kapitel, titel}, wahl und freigaben
   {nachtragen, entwurf} je oberstem Ordner, ohne (abgewählte Dateien „Ordnerpfad/Name“), export (nur beim Eintragen, aus dem Plan) */
function qs_import_angaben(array $b): array
{
    $w = is_array($b['wurzel'] ?? null) ? $b['wurzel'] : [];
    $ohne = [];
    foreach (is_array($b['ohne'] ?? null) ? $b['ohne'] : [] as $x) if (is_string($x)) $ohne[$x] = true;
    return ['wurzel' => ['name' => is_string($w['name'] ?? null) ? $w['name'] : '', 'art' => in_array($w['art'] ?? '', ['sf', 'kapitel', 'neu'], true) ? $w['art'] : '']
                        + array_intersect_key($w, ['kapitel' => 1, 'titel' => 1]),
            'wahl' => is_array($b['wahl'] ?? null) ? $b['wahl'] : [], 'freigaben' => is_array($b['freigaben'] ?? null) ? $b['freigaben'] : [],
            'ohne' => $ohne, 'export' => !empty($b['export'])];
}
function qs_import_kapitel(array $stamm): array
{
    $kap = []; foreach ($stamm['kapitel'] as $k) $kap[(string)$k['id']] = $k;
    return $kap;
}
/* Kapitel (kein Bereich), dessen Nummer vorn im Ordnernamen steht, oder null */
function qs_import_erkannt(string $name, array $kap): ?string
{
    return preg_match(QS_KAPITEL_RE, $name, $m) && isset($kap[$m[1]]) && empty($kap[$m[1]]['bereich']) ? $m[1] : null;
}
/* Heißt der Ordner genau wie das Kapitel („<Nr>“, „<Nr> <Titel>“) bzw. wie der Bereich (auch nur der Titel, auch mit „_“ vorn)? */
function qs_import_exakt(string $name, array $k): bool
{
    $id = (string)$k['id']; $t = (string)$k['titel'];
    $namen = [$id, "$id $t", ablage_zip_pfad("$id $t")];
    if (!empty($k['bereich'])) $namen[] = $t;
    return in_array(qs_norm_trenner(ltrim($name, '_')), array_map('qs_norm_trenner', $namen), true);
}
function qs_import_bereich_name(string $name, array $kap): ?string
{
    foreach ($kap as $id => $k) if (!empty($k['bereich']) && qs_import_exakt($name, $k)) return (string)$id;
    return null;
}
/* Darf der gemeinsame erste Ordner wegfallen? Nicht mit Kapitelnummer, „_“/„alt“ vorn oder dem Namen eines Bereichs (der gilt dann) */
function qs_import_weglassbar(string $name, array $kap): bool
{
    return $name !== '' && !preg_match(QS_KAPITEL_RE, $name) && !preg_match(QS_FREMD_RE, $name) && qs_import_bereich_name($name, $kap) === null;
}
/* Ordnernamen ab dem obersten Ordner. Die Wurzel ($A['wurzel']) fällt weg, außer sie gehört laut Antwort in einen Bereich (art kapitel/neu:
   dann ist sie selbst der oberste Ordner mit dieser Zuordnung). Ohne Antwort fällt sie weg, Kapitelordner darin bleiben aber offen.
   Rückgabe [Ordnernamen, Zuordnung aus der Antwort oder null, offen]. */
function qs_import_oben(array $t, array $A, array $kap): array
{
    $w = $A['wurzel'];
    if ($w['name'] === '' || ($t[0] ?? null) !== $w['name'] || !qs_import_weglassbar($w['name'], $kap)) return [$t, null, false];
    if (in_array($w['art'], ['kapitel', 'neu'], true)) return [$t, $w, false];
    return [array_slice($t, 1), null, $w['art'] !== 'sf'];
}
/* Zuordnung eines obersten Ordners: die Wahl des Nutzers ($x bzw. $A['wahl'][$name]) gilt immer; ohne Wahl ein Kapitelordner (genau „<Nr>“
   oder „<Nr> <Titel>“: Nummern und Archiv), ein Vorschlag (andere Ordner mit Kapitelnummer: nur Archiv), ein Bereich gleichen Namens oder
   der Eingang. art: offen | eingang | aus | genau | kapitel | neu; imPfad: der Ordnername bleibt vorn im pfad (nicht genau das Kapitel);
   nachtragen/entwurf: Freigaben für gültige Versionen (Vorgabe aus) und Entwürfe (Vorgabe an). */
function qs_import_zuordnung(string $name, ?array $x, bool $offen, array $A, array $kap): array
{
    $erkannt = qs_import_erkannt($name, $kap);
    if ($offen && $erkannt !== null) return ['art' => 'offen', 'erkannt' => $erkannt];
    $x = $x ?? (is_array($A['wahl'][$name] ?? null) ? $A['wahl'][$name] : null);
    if ($x === null) {
        $bereich = qs_import_bereich_name($name, $kap);
        $x = $erkannt !== null ? ['art' => qs_import_exakt($name, $kap[$erkannt]) ? 'genau' : 'kapitel', 'kapitel' => $erkannt]
            : ($bereich !== null ? ['art' => 'kapitel', 'kapitel' => $bereich] : ['art' => 'eingang']);
    }
    $f = is_array($A['freigaben'][$name] ?? null) ? $A['freigaben'][$name] : [];
    $z = ['art' => (string)($x['art'] ?? ''), 'erkannt' => $erkannt, 'nachtragen' => !empty($f['nachtragen']), 'entwurf' => !array_key_exists('entwurf', $f) || !empty($f['entwurf'])];
    $ort = '„' . mb_substr($name, 0, 60) . '“';
    if (in_array($z['art'], ['eingang', 'aus'], true)) return $z;
    if ($z['art'] === 'genau') {
        if ($erkannt === null) throw new InvalidArgumentException("$ort trägt keine Kapitelnummer.");
        return ['kapitel' => $erkannt, 'imPfad' => false] + $z;
    }
    if ($z['art'] === 'neu') {
        $nr = rtrim(qs_text($x['kapitel'] ?? '', 12, 'Bereich'), '.'); $titel = qs_text($x['titel'] ?? '', 120, 'Bereich');
        if (!preg_match('/^9\d$/D', $nr) || $titel === '') throw new InvalidArgumentException('Neuer Bereich: Nummer von ' . QS_BEREICH_AB . ' bis 99 und Titel angeben.');
        if (!isset($kap[$nr])) return ['kapitel' => $nr, 'titel' => $titel, 'imPfad' => !qs_import_exakt($name, ['id' => $nr, 'titel' => $titel, 'bereich' => true])] + $z;
        if (empty($kap[$nr]['bereich']) || qs_norm((string)$kap[$nr]['titel']) !== qs_norm($titel)) throw new InvalidArgumentException("Die Nummer $nr ist schon vergeben.");
        $z['art'] = 'kapitel'; $x['kapitel'] = $nr;   // schon angelegt (erneuter Plan, Fortsetzen)
    }
    if ($z['art'] !== 'kapitel') throw new InvalidArgumentException("$ort: ungültige Zuordnung.");
    $k = (string)($x['kapitel'] ?? '');
    if (!isset($kap[$k])) throw new InvalidArgumentException("$ort: unbekanntes Kapitel.");
    return ['kapitel' => $k, 'imPfad' => !qs_import_exakt($name, $kap[$k])] + $z;
}
/* Verzeichnisse aus qs-dokumente (beim Eintragen unter der Sperre neu gebaut): Nummern gelenkter Dokumente – ohne Bereiche, dort nie per
   Nummer –, Ordnernamen „Nr Titel“ des eigenen Exports, Ordner-Dokumente je (Kapitel, Titel) */
function qs_import_verzeichnis(array $dokumente, array $kap): array
{
    $V = ['nr' => [], 'frei' => [], 'export' => [], 'ordner' => []];
    foreach ($dokumente as $d) {
        if (in_array($d['art'] ?? '', QS_GELENKT, true)) {
            if (!empty($kap[(string)$d['kapitel']]['bereich'])) continue;
            if (($s = qs_nr_schluessel((string)$d['nr'])) !== '') $V['nr'][$s][] = $d; elseif ((string)$d['nr'] !== '') $V['frei'][] = $d;
            $V['export'][qs_norm(ablage_zip_pfad(trim($d['nr'] . ' ' . $d['titel'])))][] = $d;
        } elseif (($d['art'] ?? '') === 'O') {
            $k = qs_import_schluessel((string)$d['kapitel'], qs_norm((string)$d['titel']));
            if (!isset($V['ordner'][$k]) || !empty($V['ordner'][$k]['eingezogen'])) $V['ordner'][$k] = $d;
        }
    }
    usort($V['frei'], function ($a, $b) { return mb_strlen((string)$b['nr']) <=> mb_strlen((string)$a['nr']); });
    return $V;
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
function qs_import_nr_dok(string $name, string $kap, array $V): ?array
{
    $basis = preg_replace('/\.[^.]*$/', '', $name) ?? $name;
    if (preg_match('/^(\d+(?:\.\d+){0,3})\s*-\s*([A-Za-z])\s*0*(\d{1,3})(?!\d)(.*)$/su', $basis, $m))
        foreach ($V['nr'][$m[1] . '-' . strtoupper($m[2]) . (int)$m[3]] ?? [] as $d) if (qs_import_kapitel_passt($d, $kap) && qs_import_rest_passt($m[4], $d)) return $d;
    foreach ($V['frei'] as $d) {
        $n = (string)$d['nr'];
        if (mb_stripos($basis, $n) !== 0 || !qs_import_kapitel_passt($d, $kap)) continue;
        $rest = mb_substr($basis, mb_strlen($n));
        if (($rest === '' || preg_match('/^[\s_\-]/u', $rest)) && qs_import_rest_passt($rest, $d)) return $d;
    }
    return null;
}
/* Ziel eines gelenkten Dokuments: ein offener Entwurf geht vor (dokument), sonst die gültige Version (nachtragen, nur mit Freigaberecht);
   gesperrt → Eingang */
function qs_import_gelenkt(array $d, string $name, int $groesse, string $voll, array $me): array
{
    $gesperrt = function (string $grund) use ($voll) { return ['status' => 'eingang', 'ziel' => QS_EINGANG, 'pfad' => $voll, 'grund' => $grund]; };
    if (!empty($d['eingezogen'])) return $gesperrt('Dokument eingezogen');
    $o = qs_ver_index($d, QS_VER_OFFEN); $g = qs_ver_index($d, ['freigegeben']);
    if ($o !== null && $d['versionen'][$o]['status'] !== 'entwurf') return $gesperrt('Überarbeitung liegt zur Prüfung');
    if ($o === null && $g === null) return $gesperrt('noch ohne Version');
    if ($o === null && !may($me, 'qs.freigeben')) return $gesperrt('gültige Version nur mit Freigaberecht');
    $v = $d['versionen'][$o ?? $g];
    $da = false;
    foreach (qs_dateien_aktiv($v['dateien'] ?? []) as $f) if ((string)$f['name'] === $name && (int)$f['groesse'] === $groesse) $da = true;
    return ['status' => $o !== null ? 'dokument' : 'nachtragen', 'ziel' => (string)$d['id'], 'ver' => (string)$v['id']] + ($da ? ['schonDa' => true] : []);
}
/* Archiv: Ordner-Dokument je (Kapitel, Unterordner der ersten Ebene bzw. „Weitere Dateien“), tiefere Ebenen als pfad; der Name des obersten
   Ordners steht vorn im pfad, wenn er nicht genau das Kapitel ist. Fehlt das Ordner-Dokument noch: ordner = [Kapitel, Titel]. */
function qs_import_archiv(array $z, array $t, string $voll, array $V): array
{
    $rel = array_slice($t, 1);
    $titel = $rel ? qs_pfad($rel[0]) : '';
    if ($titel === '') $titel = QS_WEITERE;
    $pfad = qs_pfad(implode('/', array_merge($z['imPfad'] ? [$t[0]] : [], array_slice($rel, 1))));
    $od = $V['ordner'][qs_import_schluessel($z['kapitel'], qs_norm($titel))] ?? null;
    if ($od !== null && !empty($od['eingezogen'])) return ['status' => 'eingang', 'ziel' => QS_EINGANG, 'pfad' => $voll, 'grund' => 'Ordner eingezogen'];
    return ['status' => 'ablage', 'pfad' => $pfad] + ($od !== null ? ['ziel' => (string)$od['id']] : ['ordner' => [$z['kapitel'], $titel]]);
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
/* Entscheidung für eine Datei (rein; Plan und Eintragen). $t: Ordnernamen ab dem obersten Ordner (qs_import_oben), $z: dessen Zuordnung
   (null = lose Datei), $ohne: in der Vorschau abgewählt (nie in eine Version: Archiv), $export: eigener Export gewählt (Ordner „Nr Titel“).
   Rückgabe status (QS_IMPORT_ABLEGEN oder übersprungen bzw. offen), ziel, ver, pfad, grund, schonDa; ordner = noch anzulegendes
   Ordner-Dokument; kandidat (nachtragen|dokument) und dok, wenn die Nummer zu einem gelenkten Dokument passt – gültige Version nur mit dem
   Häkchen des obersten Ordners, Entwurf nur mit dem zweiten (Vorgabe an), sonst in den Eingang. */
function qs_import_datei(array $t, string $name, int $groesse, ?array $z, bool $ohne, array $V, bool $export, array $me): array
{
    $e = qs_import_ueberspringen($name, $groesse, $t === []);
    if ($e !== null) return $e;
    $voll = qs_pfad(implode('/', $t));
    if ($z === null) return ['status' => 'eingang', 'ziel' => QS_EINGANG, 'pfad' => $voll, 'grund' => 'lose Datei'];
    if (in_array($z['art'], ['offen', 'aus'], true)) return ['status' => $z['art']];
    if ($z['art'] === 'eingang') return ['status' => 'eingang', 'ziel' => QS_EINGANG, 'pfad' => $voll];
    $d = null;
    if ($z['art'] === 'genau') {
        $rel = array_slice($t, 1);
        $exportDok = null;
        if ($export && $rel) foreach ($V['export'][qs_norm($rel[0])] ?? [] as $x) if (qs_import_kapitel_passt($x, $z['kapitel'])) $exportDok = $x;
        if ($exportDok && isset($rel[1]) && in_array($rel[1], QS_EXPORT_UNTER, true)) return ['status' => 'export'];
        $d = !$rel ? qs_import_nr_dok($name, $z['kapitel'], $V) : (count($rel) === 1 ? $exportDok : null);
    }
    if ($d === null) return qs_import_archiv($z, $t, $voll, $V);
    $e = qs_import_gelenkt($d, $name, $groesse, $voll, $me);
    if (!in_array($e['status'], ['nachtragen', 'dokument'], true)) return $e;
    $k = ['kandidat' => $e['status'], 'dok' => (string)$d['id']] + (!empty($e['schonDa']) ? ['schonDa' => true] : []);
    if ($ohne) return qs_import_archiv($z, $t, $voll, $V) + $k;
    if (!$z[$e['status'] === 'nachtragen' ? 'nachtragen' : 'entwurf']) return ['status' => 'eingang', 'ziel' => QS_EINGANG, 'pfad' => $voll, 'grund' => 'ohne Häkchen'] + $k;
    return $e + $k;
}
/* Zuordnungsplan (Aktion qs_sammel_plan). $ordner aus qs_import_ordner_lesen, $A aus qs_import_angaben. Rückgabe: wurzel {name (gemeinsamer
   erster Ordner), weg (fällt weg), frage (darin erkannte Kapitel: Antwort nötig)}, offen (Antwort fehlt – nichts startet), export,
   oberste (Zuordnung je oberstem Ordner mit Freigaben und Vorschlag für einen neuen Bereich), dateien (je Datei in derselben
   Reihenfolge wie qs_import_datei, dazu oben = Nummer des obersten Ordners, neu = Nummer des anzulegenden Ordner-Dokuments), neu, bereiche. */
function qs_import_plan(array $ordner, array $A, array $me, array $stamm, array $dokumente, array $ablage): array
{
    $kap = qs_import_kapitel($stamm);
    $erste = [];
    foreach ($ordner as [, $t]) $erste[$t[0] ?? ''] = true;
    $gemeinsam = count($erste) === 1 ? (string)array_key_first($erste) : '';
    $w = qs_import_weglassbar($gemeinsam, $kap) ? $gemeinsam : '';
    $A['wurzel'] = $w !== '' && $A['wurzel']['name'] === $w ? $A['wurzel'] : ['name' => $w, 'art' => ''];
    $frage = false; $export = false;
    foreach ($ordner as [, $t, $l]) {
        if ($w !== '' && isset($t[1]) && qs_import_erkannt($t[1], $kap) !== null) $frage = true;
        if (qs_import_oben($t, $A, $kap)[0] === []) foreach ($l as [$n]) if (strcasecmp($n, QS_IMPORT_LISTE) === 0) $export = true;
    }
    $V = qs_import_verzeichnis($dokumente, $kap);
    // schon Abgelegtes: am Ziel (Archiv, auch ältere Dateien am Ordner) oder irgendwo mit dem ganzen Ordnerpfad (Eingang, auch danach zugeordnet)
    $index = qs_ablage_nach_ziel($ablage); $je = qs_ablage_je($ablage);
    $da = []; $irgendwo = []; $belegt = [QS_EINGANG => qs_ablage_belegt(null, $je)];
    foreach ($dokumente as $d) {
        if (in_array($d['art'] ?? '', QS_GELENKT, true)) {
            foreach ((array)($d['versionen'] ?? []) as $v) foreach (qs_dateien_aktiv($v['dateien'] ?? []) as $f)
                if (($f['pfad'] ?? '') !== '') $irgendwo[qs_import_schluessel((string)$f['pfad'], (string)$f['name'], (string)$f['groesse'])] = true;
            continue;
        }
        $belegt[(string)$d['id']] = qs_ablage_belegt($d, $je);
        foreach (qs_ordner_dateien($d, $index) as $f) $da[qs_import_schluessel((string)$d['id'], (string)($f['pfad'] ?? ''), (string)$f['name'], (string)$f['groesse'])] = true;
    }
    foreach ($ablage as $f) $irgendwo[qs_import_schluessel((string)($f['pfad'] ?? ''), (string)$f['name'], (string)$f['groesse'])] = true;
    unset($index, $je);
    $oberste = []; $nummer = []; $dateien = []; $neu = []; $neuIdx = []; $plus = [];
    foreach ($ordner as [$roh, $t0, $l]) {
        [$t, $x, $offen] = qs_import_oben($t0, $A, $kap);
        $top = $t[0] ?? null;
        if ($top !== null && !isset($oberste[$top])) {
            $oberste[$top] = qs_import_zuordnung($top, $x, $offen, $A, $kap) + ($x !== null ? ['wurzel' => true] : []);
            $nummer[$top] = count($nummer);
        }
        $z = $top === null ? null : $oberste[$top];
        $voll = qs_pfad(implode('/', $t));
        foreach ($l as [$name, $groesse]) {
            $e = qs_import_datei($t, $name, $groesse, $z, isset($A['ohne'][$roh . '/' . $name]), $V, $export, $me);
            if (in_array($e['status'], QS_IMPORT_ABLEGEN, true)) {
                if (!empty($e['schonDa']) || isset($irgendwo[qs_import_schluessel($voll, $name, (string)$groesse)])
                        || (isset($e['ziel']) && $e['status'] === 'ablage' && isset($da[qs_import_schluessel($e['ziel'], $e['pfad'], $name, (string)$groesse)]))) {
                    $e = ['schonDa' => true] + array_diff_key($e, ['kandidat' => 1, 'dok' => 1]);
                } else {
                    if (isset($e['ordner'])) {
                        $k = qs_import_schluessel($e['ordner'][0], qs_norm($e['ordner'][1]));
                        if (!isset($neuIdx[$k])) { $neuIdx[$k] = count($neu); $neu[] = ['kapitel' => $e['ordner'][0], 'titel' => $e['ordner'][1]]; }
                        $e['neu'] = $neuIdx[$k]; unset($e['ordner']);
                    }
                    if ($e['status'] === 'ablage' && isset($e['ziel']) && ($belegt[$e['ziel']] ?? 0) + ($plus[$e['ziel']] ?? 0) >= QS_MAX_ORDNER)
                        $e = ['status' => 'eingang', 'ziel' => QS_EINGANG, 'pfad' => $voll, 'grund' => 'Ordner voll'] + array_intersect_key($e, ['kandidat' => 1, 'dok' => 1]);
                    if ($e['status'] === 'eingang' && $belegt[QS_EINGANG] + ($plus[QS_EINGANG] ?? 0) >= QS_MAX_EINGANG) $e = ['status' => 'voll'];
                    if (isset($e['ziel'])) $plus[$e['ziel']] = ($plus[$e['ziel']] ?? 0) + 1;
                }
            }
            $dateien[] = $top === null ? $e : $e + ['oben' => $nummer[$top]];
        }
    }
    $bereiche = [];
    foreach ($oberste as $z) if ($z['art'] === 'neu') {
        if (isset($bereiche[$z['kapitel']]) && $bereiche[$z['kapitel']] !== $z['titel']) throw new InvalidArgumentException('Die Nummer ' . $z['kapitel'] . ' ist schon vergeben.');
        $bereiche[$z['kapitel']] = $z['titel'];
    }
    $naechste = QS_BEREICH_AB;
    while (isset($kap[(string)$naechste]) || isset($bereiche[(string)$naechste])) $naechste++;
    $vorschlag = function (string $name) use ($naechste) { return ['kapitel' => (string)$naechste, 'titel' => trim(ltrim($name, '_'))]; };
    $aus = [];
    foreach ($oberste as $name => $z) $aus[] = ['name' => (string)$name] + $z + ['bereichVorschlag' => $vorschlag((string)$name)];
    return ['wurzel' => ['name' => $gemeinsam, 'weg' => $w !== '' && !in_array($A['wurzel']['art'], ['kapitel', 'neu'], true), 'frage' => $frage, 'bereichVorschlag' => $vorschlag($gemeinsam)],
            'offen' => $frage && $A['wurzel']['art'] === '', 'export' => $export, 'oberste' => $aus, 'dateien' => $dateien, 'neu' => $neu, 'bereiche' => $bereiche];
}
/* Bereiche und Ordner-Dokumente des Plans anlegen (unter der Sperre): erst alle Grenzen prüfen, dann schreiben; danach zeigen die Einträge
   des Plans auf die neuen Kennungen (der Plan wird nicht neu gerechnet). Rückgabe [angelegte Ordner-Dokumente, angelegte Bereiche]. */
function qs_import_anlegen(array &$plan, array $me, array $stamm, array &$doc): array
{
    if ($plan['offen']) throw new InvalidArgumentException('Bitte zuerst wählen, wohin der Ordner „' . mb_substr($plan['wurzel']['name'], 0, 60) . '“ gehört.');
    if (count($doc['liste']) + count($plan['neu']) > QS_MAX_DOKUMENTE) throw new InvalidArgumentException('Zu viele Dokumente (höchstens ' . QS_MAX_DOKUMENTE . ').');
    if ($plan['bereiche']) {
        foreach ($plan['bereiche'] as $id => $titel) $stamm['kapitel'][] = ['id' => (string)$id, 'titel' => $titel, 'zustaendig' => '', 'vertreter' => '', 'aktiv' => true, 'bereich' => true];
        $stamm['kapitel'] = qs_kapitel_liste_pruefen($stamm['kapitel'], $stamm['kapitel'], []);
    }
    $ids = []; $neu = [];
    foreach ($plan['neu'] as $n) {
        $d = ['id' => qs_id('d')] + qs_dokument_pruefen(['art' => 'O', 'kapitel' => $n['kapitel'], 'nr' => '', 'titel' => $n['titel']], null, $stamm, $doc['liste'])
            + ['erstellt' => qs_wer($me), 'quelle' => 'import', 'verlauf' => [], 'rev' => 1];
        qs_verlauf($d, $me, 'angelegt (Ordner-Import)');
        $neu[] = $d; $ids[] = $d['id'];
    }
    if ($plan['bereiche']) qs_schreiben('qs-stamm', $stamm);
    if ($neu) { $doc['liste'] = array_merge($doc['liste'], $neu); qs_schreiben('qs-dokumente', $doc); }
    foreach ($plan['dateien'] as $k => $e) if (isset($e['neu'])) { $plan['dateien'][$k]['ziel'] = $ids[$e['neu']]; unset($plan['dateien'][$k]['neu']); }
    foreach ($plan['oberste'] as $k => $z) if ($z['art'] === 'neu') $plan['oberste'][$k]['art'] = 'kapitel';
    $zahl = [count($plan['neu']), count($plan['bereiche'])];
    $plan['neu'] = []; $plan['bereiche'] = [];
    return $zahl;
}
/* Ordner-Import, Schritt 1 (Aktion qs_sammel_plan): Plan; mit anlegen unter der Sperre einmal gerechnet und danach Bereiche und
   Ordner-Dokumente angelegt. Einen neuen Bereich wählt nur, wer verwalten darf. Rückgabe [Plan, angelegte Ordner-Dokumente, Bereiche]. */
function qs_import_planen(array $b, array $me): array
{
    $ordner = qs_import_ordner_lesen($b['ordner'] ?? null);
    $A = qs_import_angaben($b);
    $neu = $A['wurzel']['art'] === 'neu';
    foreach ($A['wahl'] as $x) if (is_array($x) && ($x['art'] ?? '') === 'neu') $neu = true;
    if ($neu && !may($me, 'qs.verwalten')) fail('Einen neuen Bereich legt nur an, wer das QM-System verwalten darf.', 403);
    if (empty($b['anlegen'])) return [qs_import_plan($ordner, $A, $me, qs_stamm(), qs_doc('qs-dokumente')['liste'], qs_doc('qs-ablage')['liste']), 0, 0];
    return with_lock('qs-dokumente', function () use ($ordner, $A, $me) {
        $stamm = qs_stamm(); $doc = qs_doc('qs-dokumente');
        $plan = qs_import_plan($ordner, $A, $me, $stamm, $doc['liste'], qs_doc('qs-ablage')['liste']);
        $zahl = qs_import_anlegen($plan, $me, $stamm, $doc);
        return array_merge([$plan], $zahl);
    });
}
/* Uploads eines Bündels aus der Anfrage: [[upload, erwarteter Status (QS_IMPORT_ABLEGEN), Version, abgewählt], …], 1 bis QS_IMPORT_BUENDEL */
function qs_import_uploads($v): array
{
    if (!is_array($v) || !$v || count($v) > QS_IMPORT_BUENDEL) throw new InvalidArgumentException('Bitte 1 bis ' . QS_IMPORT_BUENDEL . ' fertige Uploads angeben.');
    $aus = [];
    foreach ($v as $u) {
        if (!is_array($u) || !is_string($u['upload'] ?? null) || !in_array($u['status'] ?? '', QS_IMPORT_ABLEGEN, true) || !is_string($u['ver'] ?? ''))
            throw new InvalidArgumentException('Ungültige Uploads.');
        $aus[$u['upload']] = [$u['upload'], $u['status'], (string)($u['ver'] ?? ''), !empty($u['ohne'])];
    }
    return array_values($aus);
}
/* Ordner-Import, Schritt 2 (Aktion qs_import_eintragen): fertige Uploads (qs_datei_hochladen mit sammeln) in einem Schreibvorgang eintragen.
   Das Ziel berechnet der Server unter der Sperre neu (qs_import_datei aus Herkunft und Name des Uploads und den Angaben $A); weicht es vom
   erwarteten ab (Entwurf inzwischen freigegeben, Version ersetzt, Häkchen fehlt), kommt die Datei in den Eingang. Was nicht abgelegt wird,
   verschwindet wieder. Rückgabe je Upload status abgelegt|eingang|vorhanden|verworfen|fehler, datei, grund. */
function qs_import_eintragen(array $ups, array $A, array $me): array
{
    require_once __DIR__ . '/vorlagen.php';
    $abgelegt = []; $erzeugt = []; $gespeichert = []; $neu = []; $ergebnis = []; $lenkung = 0;
    qs_ablage_aufraeumen($abgelegt, $erzeugt, $gespeichert);
    foreach ($ups as [$u, $status, $ver, $ohne]) {
        try {
            $r = ablage_fertig_ablegen('qs', (string)$me['id'], $u);
            $datei = $r['datei']; $abgelegt[] = (string)$datei['id'];
            if (empty($r['ziel']['sammeln']) || !is_string($r['ziel']['herkunft'] ?? null)) throw new InvalidArgumentException('Der Upload gehört nicht zum Ordner-Import.');
            $office = $status === 'nachtragen' && isset(QS_OFFICE[$datei['art']]);
            if ($office && $lenkung > 0 && $lenkung + $datei['groesse'] > QS_IMPORT_LENKUNG_BYTES) throw new InvalidArgumentException('Zu viele Word-/Excel-Nachträge in einem Bündel – bitte noch einmal importieren.');
            if ($office) $lenkung += $datei['groesse'];
            $neu[$u] = ['datei' => $datei, 'herkunft' => $r['ziel']['herkunft'], 'erwartet' => [$status, $ver], 'ohne' => $ohne,
                        'platzhalter' => in_array($status, ['nachtragen', 'dokument'], true) ? qs_platzhalter_vorab($datei) : null];
        } catch (Throwable $e) {
            $ergebnis[$u] = ['status' => 'fehler', 'grund' => $e instanceof InvalidArgumentException ? $e->getMessage() : 'Die Datei konnte nicht abgelegt werden.'];
        }
    }
    if (!$neu) return $ergebnis;
    $aus = with_lock('qs-dokumente', function () use ($neu, $A, $me, &$erzeugt) {
        $kap = qs_import_kapitel(qs_stamm());
        $V = qs_import_verzeichnis(qs_doc('qs-dokumente')['liste'], $kap);
        $oberste = []; $eintraege = [];
        foreach ($neu as $u => $n) {
            [$t, $x, $offen] = qs_import_oben(qs_import_teile($n['herkunft']), $A, $kap);
            $z = $t ? ($oberste[$t[0]] ??= qs_import_zuordnung($t[0], $x, $offen, $A, $kap)) : null;
            $voll = qs_pfad(implode('/', $t));
            $e = qs_import_datei($t, (string)$n['datei']['name'], (int)$n['datei']['groesse'], $z, $n['ohne'], $V, $A['export'], $me);
            if ($e['status'] !== $n['erwartet'][0] || (string)($e['ver'] ?? '') !== $n['erwartet'][1]) $e = ['ziel' => QS_EINGANG, 'pfad' => $voll, 'grund' => 'inzwischen geändert – bitte prüfen'];
            elseif (!isset($e['ziel'])) $e = ['ziel' => QS_EINGANG, 'pfad' => $voll, 'grund' => 'Ordner fehlt'];
            $eintraege[$u] = ['datei' => $n['datei'], 'ziel' => $e['ziel'], 'version' => $e['ver'] ?? '', 'pfad' => $e['pfad'] ?? '', 'platzhalter' => $n['platzhalter'],
                              'grund' => $e['grund'] ?? '', 'eingang' => $voll];
        }
        return qs_ablage_eintragen($eintraege, $me, 'abgelegt (Ordner-Import)', $erzeugt)[0];
    });
    foreach ($aus as $u => $e) {
        if (in_array($e['status'], ['abgelegt', 'eingang'], true)) $gespeichert[(string)$neu[$u]['datei']['id']] = true;
        unset($e['code']);
        $ergebnis[$u] = $e;
    }
    foreach ($erzeugt as $id) $gespeichert[$id] = true;
    return $ergebnis;
}
