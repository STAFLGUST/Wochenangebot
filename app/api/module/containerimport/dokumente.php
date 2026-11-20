<?php
declare(strict_types=1);
/* STAFL-Plattform · Modul Container-Import – Dokumente je Container (Auftrag des Inhabers 20.11.2026: alle Unterlagen eines
   Containerordners – Kaufbestätigung, Rechnungen, Zertifikate, B/L, Versicherung, Spedition, Kalkulation, E-Mails – mehrere
   Dateien je Container, PDF, Word, Excel (auch .xls), E-Mail (.eml, .msg) und Bilder (.jpg, .png, z. B. ein Handyfoto eines
   Zertifikats); GoBD-konform abgelegt). Die Dateien liegen in der Dateiablage des Plattformkerns (lib/dateiablage.php, Bereich
   „containerimport“), die Metadaten im eigenen Dokument containerimport-dokumente, die Zahlen je Container für die Liste in
   containerimport-dokumente-zahlen (bei jedem Schreiben neu gezählt; Aufbau: docs/entwickler/05-daten.md).
   GoBD (Verfahren: docs/plattform/inbetriebnahme-containerimport.md, Abschnitt „Dokumente je Container“): eine Datei wird nie
   überschrieben oder gelöscht. Je Datei stehen Kennung, Originalname, Dateiart, Größe, SHA-256, wer und wann hochgeladen hat
   und ein Schnappschuss von Partie, Akte, Containernummer und Lieferant zu diesem Zeitpunkt (GR-106). Eine Datei trägt eine
   oder mehrere Dokumentarten (Sammel-PDF). Arten ändern und Entfernen sind Vermerke (verlauf, entfernt mit Pflicht-Grund);
   eine entfernte Datei bleibt abrufbar. „Nicht nötig“ in der Checkliste ist ein Vermerk in checkliste (nur anhängen).
   Jeder Vorgang steht zusätzlich im Protokoll (ohne Dateinamen und Gründe, wie im QM-System).
   Rechte (GR-103): ansehen, herunterladen, ZIP mit containerimport.eudr_sehen – für alle Arten gleich (Entscheidung des
   Inhabers 20.11.2026, auch die Kalkulation); hochladen, Arten ändern, entfernen, Checkliste mit containerimport.eudr_bearbeiten.
   Gesperrt wird mit EUDR_SPERRE (Schnappschuss aus dem Dokument der Container), immer hier in den Modulfunktionen.
   Helfer (eudr_wer, eudr_text, eudr_holen …): eudr.php. */
if (!defined('WA_API')) { http_response_code(404); exit; }
require_once __DIR__ . '/../../lib/dateiablage.php';

const CI_DOK_BEREICH = 'containerimport';   // Bereich in der Dateiablage
const CI_DOK_DOKUMENT = 'containerimport-dokumente';
const CI_DOK_ZAHLEN = 'containerimport-dokumente-zahlen';   // abgeleitet: Zahlen je Container, damit der Stand der Seite nicht alle Dateien liest
const CI_DOK_MAX = 20000;                   // shortcut: das Dokument wird bei jedem Schreiben ganz gelesen und geschrieben; darüber je Jahr teilen
const CI_DOK_MAX_JE_CONTAINER = 300;        // Dateien je Container, entfernte eingeschlossen
/* Angaben des Containers, die eine Datei beim Hochladen festhält (GR-106); nummer = Auftragsnummer (Name älterer Container ohne Partie) */
const CI_DOK_SCHNAPPSCHUSS = ['partie' => 1, 'akte' => 1, 'container' => 1, 'lieferant' => 1, 'nummer' => 1];
/* Erlaubte Dateiarten am Container; ob der Inhalt zur Endung passt, prüft die Ablage (ABLAGE_ARTEN, ablage_inhalt_passt) */
const CI_DOK_ENDUNGEN = ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'xlsm', 'xlsb', 'odt', 'ods', 'eml', 'msg', 'jpg', 'jpeg', 'png'];
/* Dokumentarten – die eine Liste (Bezeichnungen hier ändern; die Schlüssel stehen an den Dateien: nie umbenennen oder
   entfernen, nur ergänzen, GR-006). Reihenfolge = Anzeige und Reihenfolge der Arten an einer Datei (die erste bestimmt den
   Ordner im ZIP). checkliste: Platzhalter am Container („fehlt“, solange keine Datei diese Art trägt und sie nicht als
   „nicht nötig“ vermerkt ist). */
const CI_DOKUMENTARTEN = [
    'kaufbestaetigung' => ['name' => 'Kaufbestätigung', 'checkliste' => true],
    'proforma' => ['name' => 'Proforma-Rechnung'],
    'handelsrechnung' => ['name' => 'Handelsrechnung', 'checkliste' => true],
    'packliste' => ['name' => 'Packliste', 'checkliste' => true],
    'lot' => ['name' => 'Lot-Nummernliste / Rückverfolgbarkeit', 'checkliste' => true],
    'gesundheit' => ['name' => 'Gesundheitszertifikat', 'checkliste' => true],
    'echtheit' => ['name' => 'Echtheitszertifikat (Hilton, Angus)', 'checkliste' => true],
    'quote' => ['name' => 'Quotenzertifikat (Mercosur-Kontingent)'],
    'ursprung' => ['name' => 'Ursprungszeugnis', 'checkliste' => true],
    'bl' => ['name' => 'B/L (Konnossement)', 'checkliste' => true],
    'salmonellen' => ['name' => 'Salmonellen-Zertifikat'],
    'halal' => ['name' => 'Halal-Zertifikat'],
    'eudr' => ['name' => 'EUDR-Dokument (Sorgfaltserklärung)', 'checkliste' => true],
    'versicherung' => ['name' => 'Versicherungsanmeldung', 'checkliste' => true],
    'spedition' => ['name' => 'Spedition / Buchungsbestätigung'],
    'shipment' => ['name' => 'Shipment details'],
    'kalkulation' => ['name' => 'Kalkulation', 'checkliste' => true],
    'email' => ['name' => 'E-Mail / Schriftverkehr'],
    'sonst' => ['name' => 'Sonstiges'],
];
/* Vorschlag der Arten aus dem Dateinamen (dokumente.js): die erste Regel, deren Muster auf den Namen in Kleinbuchstaben
   passt, gewinnt – nur ein Vorschlag, immer änderbar; ohne Treffer wählt der Nutzer. Muster in der Schreibweise von
   JavaScript (RegExp); geprüft als Tabelle in der Gruppe containerimport_dokumente. Nur allgemeine Begriffe – keine Namen von
   Lieferanten oder Dienstleistern (GR-007). Reihenfolge zählt: Versicherung vor der Kaufbestätigung („Insurance
   confirmation“); „Hilton“ und „Angus“ (das Fleischprogramm) zuletzt, weil sie auch auf Rechnung, Packliste, B/L und
   Zeugnissen stehen. */
const CI_DOK_VORSCHLAEGE = [
    ['\.(eml|msg)$', ['email']],
    ['(^|[^a-z])docs([^a-z]|$)', ['handelsrechnung', 'packliste', 'gesundheit', 'ursprung', 'bl']],   // Sammel-PDF des Lieferanten
    ['proforma', ['proforma']],
    ['booking|buchung|spedition|forwarder', ['spedition']],
    ['shipment.?details', ['shipment']],
    ['meldung.?container|versicherung|insurance', ['versicherung']],
    ['(^|[^a-z])g-?conf|(order|purchase|sales).?confirm|kaufbest', ['kaufbestaetigung']],
    ['kalkul|calcul', ['kalkulation']],
    ['eudr|(^|[^a-z])dds([^a-z]|$)|sorgfalt|due.?diligence', ['eudr']],
    ['authentic|autentic|echtheit', ['echtheit']],
    ['health|sanit|gesundheit|veterin', ['gesundheit']],
    ['cupo|quota|kontingent', ['quote']],
    ['salmonel', ['salmonellen']],
    ['halal', ['halal']],
    ['bill.?of.?lading|lading|konnossement|(^|[^a-z])h?b.?l([^a-z]|$)', ['bl']],
    ['invoice|factura|rechnung', ['handelsrechnung']],
    ['packing|pack.?list', ['packliste']],
    ['(^|[^a-z])lot|trazab|traceab|romaneo|rueckverfolg|rückverfolg', ['lot']],
    ['origin(?!al)|origen|ursprung', ['ursprung']],
    ['hilton|angus', ['echtheit']],
];

/* ---------- Speicher ---------- */
/* Dokument mit Vorgaben; Felder einer späteren Version bleiben beim Schreiben erhalten (GR-006) */
function ci_dokumente(): array
{
    $d = store_read(CI_DOK_DOKUMENT);
    $d = is_array($d) ? $d : [];
    return ['rev' => (int)($d['rev'] ?? 0), 'liste' => array_values(is_array($d['liste'] ?? null) ? $d['liste'] : []),
            'checkliste' => array_values(is_array($d['checkliste'] ?? null) ? $d['checkliste'] : [])] + $d;
}
/* Schreiben (unter EUDR_SPERRE) zählt containerimport-dokumente-zahlen neu – immer beide (Muster qs-ablage-zahlen) */
function ci_dokumente_schreiben(array $doc): array
{
    $doc = eudr_fortschreiben($doc);
    store_write(CI_DOK_DOKUMENT, $doc);
    store_write(CI_DOK_ZAHLEN, ['rev' => $doc['rev'], 'je' => ci_dokumente_zahlen($doc)]);
    return $doc;
}
/* Zahlen je Container für den Stand der Seite; fehlt das Dokument (vor dem ersten Schreiben), aus containerimport-dokumente */
function ci_dokumente_zahlen_lesen(): array
{
    $z = store_read(CI_DOK_ZAHLEN);
    return is_array($z['je'] ?? null) ? $z['je'] : ci_dokumente_zahlen(ci_dokumente());
}
/* Stempel mit Nutzer-Kennung: ein Name kann sich ändern, die Kennung nicht */
function ci_dok_wer(array $me): array { return eudr_wer($me) + ['vonId' => (string)$me['id']]; }
/* Arten aus der Eingabe: mindestens eine, alle bekannt; Ergebnis in der Reihenfolge der Liste, ohne Doppelte */
function ci_dok_arten($v): array
{
    if (!is_array($v) || !$v) throw new InvalidArgumentException('Bitte mindestens eine Dokumentart wählen.');
    foreach ($v as $a) if (!is_string($a) || !isset(CI_DOKUMENTARTEN[$a])) throw new InvalidArgumentException('Unbekannte Dokumentart.');
    return array_values(array_intersect(array_keys(CI_DOKUMENTARTEN), $v));
}
function ci_dok_artname(string $art): string { return CI_DOKUMENTARTEN[$art]['name'] ?? $art; }   // Art einer späteren Version: ihr Schlüssel
function ci_dok_artnamen(array $arten): string { return implode(', ', array_map('ci_dok_artname', $arten)); }
/* Datei nach Kennung (404) samt Stelle */
function ci_dok_holen(array $doc, $id): array { return eudr_holen($doc, $id, 'Dokument nicht gefunden.'); }
/* Container nach Kennung oder null */
function ci_dok_container(string $sendung): ?array
{
    $l = eudr_sendungen()['liste'];
    $i = eudr_stelle($l, $sendung);
    return $i === null ? null : $l[$i];
}
/* Grenzen vor dem Hochladen und noch einmal unter der Sperre (zwei gleichzeitige Uploads) */
function ci_dok_grenzen(array $liste, string $sendung): void
{
    if (count($liste) >= CI_DOK_MAX) throw new InvalidArgumentException('Die Ablage der Container-Dokumente ist voll. Bitte an den Administrator wenden.');
    if (count(ci_dok_von($liste, $sendung)) >= CI_DOK_MAX_JE_CONTAINER) throw new InvalidArgumentException('An diesem Container liegen schon ' . CI_DOK_MAX_JE_CONTAINER . ' Dateien.');
}
function ci_dok_von(array $liste, string $sendung): array { return array_values(array_filter($liste, fn($e) => ($e['sendung'] ?? '') === $sendung)); }

/* ---------- Sichten ---------- */
/* Was die Oberfläche zum Hochladen und Anzeigen braucht */
function ci_dok_regeln(): array
{
    return ['arten' => CI_DOKUMENTARTEN, 'vorschlaege' => CI_DOK_VORSCHLAEGE, 'endungen' => CI_DOK_ENDUNGEN];
}
/* Als „nicht nötig“ vermerkte Arten eines Containers: der letzte Vermerk je Art gilt */
function ci_dok_nicht_noetig(array $checkliste, string $sendung): array
{
    $stand = [];
    foreach ($checkliste as $v) if (($v['sendung'] ?? '') === $sendung) $stand[$v['art']] = empty($v['noetig']);
    return array_keys(array_filter($stand));
}
/* Je Container mit Dokumenten oder Vermerken: {anzahl, arten: {art: n}, nichtNoetig: [art]} – aktive Dateien; eine Datei zählt
   bei jeder ihrer Arten. Für den Zähler in der Liste und die Checkliste. */
function ci_dokumente_zahlen(array $doc): array
{
    $z = [];
    foreach ($doc['liste'] as $f) {
        if (!empty($f['entfernt'])) continue;
        $s = &$z[$f['sendung']];
        $s['anzahl'] = ($s['anzahl'] ?? 0) + 1;
        foreach ($f['arten'] as $a) $s['arten'][$a] = ($s['arten'][$a] ?? 0) + 1;
        unset($s);
    }
    foreach (array_unique(array_column($doc['checkliste'], 'sendung')) as $sid) $z[$sid]['nichtNoetig'] = ci_dok_nicht_noetig($doc['checkliste'], $sid);
    return array_map(fn($s) => $s + ['anzahl' => 0, 'arten' => [], 'nichtNoetig' => []], $z);
}
/* Antwort der Aktionen: Zahlen aller Container (leer als {}), Dateien (auch entfernte, älteste zuerst) und Vermerke der
   Checkliste des einen */
function ci_dokumente_antwort(array $doc, string $sendung): array
{
    return ['ok' => true, 'dokumente' => (object)ci_dokumente_zahlen($doc), 'dokDateien' => ci_dok_von($doc['liste'], $sendung), 'dokVermerke' => ci_dok_von($doc['checkliste'], $sendung)];
}

/* ---------- Hochladen, Arten ändern, Entfernen, Checkliste ---------- */
/* Einen Teil annehmen ($b wie ablage_teil, dazu sendung und arten). Der erste Teil prüft Container, Dateiart und Grenzen, bevor
   etwas auf der Platte liegt; der letzte trägt die Datei mit Schnappschuss ein. Rückgabe: ablage_teil (nicht fertig) oder
   ['fertig' => true, 'eintrag' => …, 'doc' => …]. Scheitert das Eintragen, wird die eben abgelegte Datei wieder entfernt – sie
   war nie verzeichnet. Auch an abgeschlossenen und archivierten Containern: Unterlagen kommen oft später. */
function ci_dokument_hochladen(array $me, array $b): array
{
    $sendung = is_string($b['sendung'] ?? null) ? $b['sendung'] : '';
    $arten = ci_dok_arten($b['arten'] ?? null);
    if ((is_string($b['upload'] ?? null) ? $b['upload'] : '') === '') {   // wie ablage_teil: kein Text = erster Teil
        if (ci_dok_container($sendung) === null) fail('Container nicht gefunden.', 404);
        $endung = strtolower(pathinfo(ablage_dateiname($b['name'] ?? ''), PATHINFO_EXTENSION));
        if (!in_array($endung, CI_DOK_ENDUNGEN, true)) throw new InvalidArgumentException('Am Container liegen nur PDF-, Word-, Excel-, E-Mail- und Bilddateien (' . implode(', ', CI_DOK_ENDUNGEN) . ').');
        ci_dok_grenzen(ci_dokumente()['liste'], $sendung);
    }
    $r = ablage_teil(CI_DOK_BEREICH, (string)$me['id'], ['sendung' => $sendung, 'arten' => $arten], $b);
    if (!$r['fertig']) return $r;
    $datei = $r['datei'];
    try {
        return with_lock(EUDR_SPERRE, function () use ($datei, $sendung, $arten, $me) {
            $s = ci_dok_container($sendung) ?? throw new InvalidArgumentException('Container nicht gefunden.');
            $doc = ci_dokumente();
            ci_dok_grenzen($doc['liste'], $sendung);
            foreach ($doc['liste'] as $f)
                if ($f['sendung'] === $sendung && empty($f['entfernt']) && $f['sha256'] === $datei['sha256']) throw new InvalidArgumentException('Diese Datei liegt schon an diesem Container („' . $f['name'] . '“).');
            $e = ['id' => $datei['id'], 'sendung' => $sendung, 'arten' => $arten, 'name' => $datei['name'], 'endung' => $datei['art'], 'mime' => $datei['mime'],
                  'groesse' => $datei['groesse'], 'sha256' => $datei['sha256'], 'hochgeladen' => ci_dok_wer($me),
                  'schnappschuss' => array_intersect_key($s, CI_DOK_SCHNAPPSCHUSS), 'verlauf' => []];
            $doc['liste'][] = $e;
            return ['fertig' => true, 'eintrag' => $e, 'doc' => ci_dokumente_schreiben($doc), 'container' => $s];
        });
    } catch (Throwable $t) {
        ablage_entfernen(CI_DOK_BEREICH, $datei['id']);
        throw $t;
    }
}
/* Arten einer Datei ändern: Vermerk im Verlauf (alte und neue Arten); entfernte Dateien bleiben, wie sie sind (409).
   Rückgabe [Datei, Dokument, Vermerk] */
function ci_dokument_arten_aendern(array $b, array $me): array
{
    return with_lock(EUDR_SPERRE, function () use ($b, $me) {
        $doc = ci_dokumente();
        [$i, $f] = ci_dok_holen($doc, $b['id'] ?? '');
        if (!empty($f['entfernt'])) fail('Die Datei ist entfernt – ihre Arten bleiben, wie sie waren.', 409);
        $neu = ci_dok_arten($b['arten'] ?? null);
        if ($neu === $f['arten']) throw new InvalidArgumentException('Die Datei hat schon diese Arten.');
        $v = ci_dok_wer($me) + ['was' => 'arten', 'alt' => $f['arten'], 'neu' => $neu];
        $f['verlauf'] = [...($f['verlauf'] ?? []), $v];
        $f['arten'] = $neu;
        $doc['liste'][$i] = $f;
        return [$f, ci_dokumente_schreiben($doc), $v];
    });
}
/* Datei als entfernt vermerken (Grund Pflicht); sie bleibt in der Ablage und für Berechtigte abrufbar. Rückgabe [Datei, Dokument, Vermerk] */
function ci_dokument_entfernen(array $b, array $me): array
{
    return with_lock(EUDR_SPERRE, function () use ($b, $me) {
        $doc = ci_dokumente();
        [$i, $f] = ci_dok_holen($doc, $b['id'] ?? '');
        if (!empty($f['entfernt'])) fail('Die Datei ist schon entfernt.', 409);
        $f['entfernt'] = ci_dok_wer($me) + ['grund' => eudr_text($b['grund'] ?? '', 500, 'Grund', true)];
        $doc['liste'][$i] = $f;
        return [$f, ci_dokumente_schreiben($doc), $f['entfernt']];
    });
}
/* Punkt der Checkliste als „nicht nötig“ vermerken oder wieder als nötig (noetig: true/false) – nur anhängen.
   Rückgabe [Container, Dokument, Vermerk] */
function ci_dokument_checkliste(array $b, array $me): array
{
    $sendung = is_string($b['sendung'] ?? null) ? $b['sendung'] : '';
    $art = $b['art'] ?? null;
    if (!is_string($art) || empty(CI_DOKUMENTARTEN[$art]['checkliste'])) throw new InvalidArgumentException('Unbekannter Punkt der Checkliste.');
    if (!is_bool($b['noetig'] ?? null)) throw new InvalidArgumentException('Bitte angeben, ob der Punkt nötig ist.');
    return with_lock(EUDR_SPERRE, function () use ($sendung, $art, $b, $me) {
        $s = ci_dok_container($sendung) ?? fail('Container nicht gefunden.', 404);
        $doc = ci_dokumente();
        if (!in_array($art, ci_dok_nicht_noetig($doc['checkliste'], $sendung), true) === $b['noetig'])
            throw new InvalidArgumentException($b['noetig'] ? 'Der Punkt gilt schon als nötig.' : 'Der Punkt ist schon als „nicht nötig“ vermerkt.');
        $v = ['sendung' => $sendung, 'art' => $art, 'noetig' => $b['noetig']] + ci_dok_wer($me);
        $doc['checkliste'][] = $v;
        return [$s, ci_dokumente_schreiben($doc), $v];
    });
}

/* ---------- ZIP für Betriebsprüfung und Datenträgerüberlassung ---------- */
/* shortcut: Kopie von qs_csv_zelle (module/qs) – gehört in eine Plattform-PR als lib/csv.php, dann beide umstellen */
function ci_csv(array $zeilen): string
{
    $zelle = function ($v): string {
        $s = str_replace(["\r", "\n"], ' ', (string)$v);
        if ($s !== '' && strpbrk($s[0], "=+-@\t") !== false && !preg_match('/^-?\d+([.,]\d+)?$/', $s)) $s = "'" . $s;   // keine Formeln (CSV-Injection)
        return '"' . str_replace('"', '""', $s) . '"';
    };
    return "\xEF\xBB\xBF" . implode("\r\n", array_map(fn($z) => implode(';', array_map($zelle, $z)), $zeilen)) . "\r\n";
}
/* Dateiname im ZIP: nur der Stamm wird gekürzt (ablage_zip_pfad, 100 Zeichen), die Endung bleibt */
function ci_dok_zip_name(string $name): string
{
    $e = pathinfo($name, PATHINFO_EXTENSION);
    return $e === '' ? ablage_zip_pfad($name) : ablage_zip_pfad(substr($name, 0, -strlen($e) - 1)) . '.' . $e;
}
/* Einträge für ablage_zip_senden: <Container>/<erste Art>/<Datei>, entfernte unter <Container>/_entfernt/<erste Art>/, dazu
   index.csv mit allen Angaben je Datei (alle Arten, Verlauf) und checkliste.csv mit allen Vermerken der Checkliste.
   Originalformat bleibt (keine Umwandlung). Gleiche Pfade bekommen hier schon „ (2)“, damit index.csv den Pfad im ZIP genau
   nennt. */
function ci_dokumente_zip_eintraege(array $s, array $dateien, array $vermerke): array
{
    $wurzel = ablage_zip_pfad('Dokumente ' . eudr_container_name($s));
    $gesehen = [];
    $eintraege = []; $index = [['Kennung', 'Datei', 'Dokumentarten', 'Dateiart', 'Größe (Bytes)', 'SHA-256', 'hochgeladen am (UTC)', 'hochgeladen von',
        'Partie beim Hochladen', 'Akte beim Hochladen', 'Container beim Hochladen', 'Lieferant beim Hochladen', 'Verlauf', 'entfernt am (UTC)', 'entfernt von', 'Grund', 'Pfad im ZIP']];
    foreach ($dateien as $f) {
        $basis = (!empty($f['entfernt']) ? '_entfernt/' : '') . ablage_zip_pfad(ci_dok_artname($f['arten'][0])) . '/' . ci_dok_zip_name($f['name']);
        for ($pfad = $basis, $n = 1; isset($gesehen[mb_strtolower($pfad)]);) $pfad = preg_replace('/(\.[^.\/]*)?$/', ' (' . ++$n . ')$1', $basis, 1);
        $gesehen[mb_strtolower($pfad)] = true;
        $eintraege[] = ['pfad' => "$wurzel/$pfad", 'bereich' => CI_DOK_BEREICH, 'id' => $f['id']];
        $ss = $f['schnappschuss'] ?? [];
        $verlauf = implode(' | ', array_map(fn($v) => $v['t'] . ' ' . $v['von'] . ': ' . ci_dok_artnamen($v['alt']) . ' → ' . ci_dok_artnamen($v['neu']), $f['verlauf'] ?? []));
        $index[] = [$f['id'], $f['name'], ci_dok_artnamen($f['arten']), $f['endung'], $f['groesse'], $f['sha256'], $f['hochgeladen']['t'], $f['hochgeladen']['von'],
            $ss['partie'] ?? '', $ss['akte'] ?? '', $ss['container'] ?? '', $ss['lieferant'] ?? '', $verlauf,
            $f['entfernt']['t'] ?? '', $f['entfernt']['von'] ?? '', $f['entfernt']['grund'] ?? '', $pfad];
    }
    $checkliste = [['Dokumentart', 'Vermerk', 'vermerkt von', 'vermerkt am (UTC)'],
        ...array_map(fn($v) => [ci_dok_artname($v['art']), $v['noetig'] ? 'nötig' : 'nicht nötig', $v['von'], $v['t']], $vermerke)];
    return [['pfad' => "$wurzel/index.csv", 'inhalt' => ci_csv($index)], ['pfad' => "$wurzel/checkliste.csv", 'inhalt' => ci_csv($checkliste)], ...$eintraege];
}
