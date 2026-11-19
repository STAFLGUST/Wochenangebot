<?php
declare(strict_types=1);
/* STAFL-Plattform · Modul Container-Import – Schlachthöfe: Stammdaten unter dem Lieferanten (Entscheidung des Inhabers
   19.11.2026: der Lieferant ist der Produzent, ihm gehören Schlachthöfe, an sie liefern die Farmer).
   Ein Schlachthof gehört zu genau einem Lieferanten – wie am Container mit der Nummer der Stammdaten der Verwaltung oder,
   solange der Lieferant dort fehlt, als freier Text (eudr_lieferant). Ein Container nennt höchstens einen Schlachthof
   seines Lieferanten; dessen Name steht am Container mit (schlachthofName) und folgt einer Umbenennung, bis die Bewertung
   des Containers abgeschlossen ist (GR-106).
   Dokument: containerimport-schlachthoefe (Liste; nichts wird gelöscht – archivieren). Gesperrt wird mit EUDR_SPERRE, weil
   Container auf Schlachthöfe verweisen. Speicher- und Prüfhelfer (eudr_liste, eudr_text …) stehen in eudr.php. */
if (!defined('WA_API')) { http_response_code(404); exit; }

const CI_MAX_SCHLACHTHOEFE = 2000;

/* Dokument der Schlachthöfe */
function ci_schlachthoefe(): array { return eudr_liste(store_read('containerimport-schlachthoefe')); }

/* Gehören zwei Einträge (Container, Schlachthof) zum selben Lieferanten? Mit Nummer der Stammdaten zählt die Nummer, ohne
   sie der Name ohne Rücksicht auf Groß- und Kleinschreibung. Dieselbe Regel filtert in schlachthoefe.js die Auswahl. */
function ci_lieferant_gleich(array $a, array $b): bool
{
    if ($a['lieferantNr'] !== '' || $b['lieferantNr'] !== '') return $a['lieferantNr'] === $b['lieferantNr'];
    return mb_strtolower($a['lieferant']) === mb_strtolower($b['lieferant']);
}

/* Felder eines Schlachthofs aus der Eingabe prüfen (ohne id, rev und Zeitstempel) */
function ci_schlachthof_pruefen(array $b, ?array $alt): array
{
    return [
        'name' => eudr_text($b['name'] ?? '', 120, 'Name', true),
        ...eudr_lieferant($b, $alt),
        'land' => eudr_land($b['land'] ?? ''),
        'ort' => eudr_text($b['ort'] ?? '', 120, 'Ort'),
        'zulassung' => eudr_text($b['zulassung'] ?? '', 40, 'Zulassungsnummer'),
        'notiz' => eudr_text($b['notiz'] ?? '', 2000, 'Notiz'),
        'aktiv' => !array_key_exists('aktiv', $b) || (bool)$b['aktiv'],
    ];
}

/* Schlachthof anlegen oder ändern (innerhalb der Sperre EUDR_SPERRE aufrufen). Der Name ist je Lieferant eindeutig.
   Eine Umbenennung geht an alle Container des Schlachthofs, deren Bewertung noch offen ist. */
function ci_schlachthof_speichern(array $b, array $me): array
{
    $doc = ci_schlachthoefe();
    $alt = null; $i = null;
    if (($b['id'] ?? '') !== '') {
        $i = eudr_stelle($doc['liste'], is_string($b['id']) ? $b['id'] : '');
        if ($i === null) fail('Schlachthof nicht gefunden.', 404);
        $alt = $doc['liste'][$i];
        eudr_rev_pruefen($b, $alt, 'Der Schlachthof');
    } elseif (count($doc['liste']) >= CI_MAX_SCHLACHTHOEFE) fail('Zu viele Schlachthöfe.', 422);
    // „+ $alt“ am Ende: Felder, die dieser Stand nicht kennt (nach einem Rückfall von einer neueren Version), bleiben erhalten
    $neu = ['id' => $alt['id'] ?? eudr_id('h')] + ci_schlachthof_pruefen($b, $alt) + ['erstellt' => $alt['erstellt'] ?? eudr_wer($me)] + ($alt ?? []);
    foreach ($doc['liste'] as $k => $x) {
        if ($k !== $i && ci_lieferant_gleich($x, $neu) && mb_strtolower($x['name']) === mb_strtolower($neu['name']))
            fail('Diesen Schlachthof gibt es bei dem Lieferanten schon' . ($x['aktiv'] ? '' : ' (archiviert)') . '.', 422);
    }
    if ($alt && $alt['name'] !== $neu['name']) {
        $sendungen = eudr_sendungen();
        foreach ($sendungen['liste'] as $k => $s) {
            if ($s['schlachthof'] === $neu['id'] && empty($s['abschluss'])) $sendungen['liste'][$k]['schlachthofName'] = $neu['name'];
        }
        eudr_sendungen_schreiben($sendungen);
    }
    $neu['rev'] = (int)($alt['rev'] ?? 0) + 1; $neu['geaendert'] = eudr_wer($me);
    if ($i === null) $doc['liste'][] = $neu; else $doc['liste'][$i] = $neu;
    store_write('containerimport-schlachthoefe', eudr_fortschreiben($doc));
    return $neu;
}

/* Schlachthof eines Containers aus der Eingabe: leer oder ein Schlachthof desselben Lieferanten; sein Name wird am Container
   mitgespeichert. Fehlt die Angabe (älterer Stand der Seite), bleibt der gespeicherte Schlachthof. Ein archivierter
   Schlachthof bleibt, wo er schon steht, lässt sich aber nicht neu wählen. */
function ci_schlachthof_am_container(array $b, array $lieferant, ?array $alt): array
{
    $bisher = (string)($alt['schlachthof'] ?? '');
    $id = eudr_text($b['schlachthof'] ?? $bisher, 20, 'Schlachthof');
    if ($id === '') return ['schlachthof' => '', 'schlachthofName' => ''];
    $liste = ci_schlachthoefe()['liste'];
    $i = eudr_stelle($liste, $id);
    if ($i === null) throw new InvalidArgumentException('Der gewählte Schlachthof ist nicht (mehr) vorhanden. Bitte neu laden.');
    $h = $liste[$i];
    if (!ci_lieferant_gleich($h, $lieferant)) throw new InvalidArgumentException('Der Schlachthof „' . $h['name'] . '“ gehört zu einem anderen Lieferanten. Bitte den Schlachthof neu wählen oder leer lassen.');
    if (!$h['aktiv'] && $id !== $bisher) throw new InvalidArgumentException('Der Schlachthof „' . $h['name'] . '“ ist archiviert.');
    return ['schlachthof' => $id, 'schlachthofName' => $h['name']];
}
