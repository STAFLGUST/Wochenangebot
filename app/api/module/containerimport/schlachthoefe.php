<?php
declare(strict_types=1);
/* STAFL-Plattform · Modul Container-Import – Schlachthöfe: Stammdaten unter dem Lieferanten (Entscheidung des Inhabers
   19.11.2026: der Lieferant ist der Produzent, ihm gehören Schlachthöfe, an sie liefern die Farmer).
   Ein Schlachthof gehört zu genau einem Lieferanten – wie am Container mit der Nummer der Stammdaten der Verwaltung oder,
   solange der Lieferant dort fehlt, als freier Text (eudr_lieferant). Ein Container nennt höchstens einen Schlachthof
   seines Lieferanten. Den Namen zeigt ein Container mit offener Bewertung immer aktuell (eudr_sendung_sicht löst ihn beim
   Lesen auf); mit dem Abschluss wird er am Container festgeschrieben (GR-106). Am Container gespeichert ist sonst nur der
   zuletzt bekannte Name – für ältere Stände der Seite.
   Dokument: containerimport-schlachthoefe (Liste; nichts wird gelöscht – archivieren). Gesperrt wird mit EUDR_SPERRE, weil
   Container auf Schlachthöfe verweisen. Speicher- und Prüfhelfer (eudr_liste, eudr_text …) stehen in eudr.php. */
if (!defined('WA_API')) { http_response_code(404); exit; }

const CI_MAX_SCHLACHTHOEFE = 2000;

/* Dokument der Schlachthöfe */
function ci_schlachthoefe(): array { return eudr_liste(store_read('containerimport-schlachthoefe')); }

/* Namen aller Schlachthöfe nach ihrer Kennung */
function ci_schlachthof_namen(): array { return array_column(ci_schlachthoefe()['liste'], 'name', 'id'); }

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
   Wechselt der Lieferant eines Schlachthofs, an dem schon Container stehen:
   - war er mit den Stammdaten verknüpft, wird abgelehnt – sonst nennte ein Container den Schlachthof eines fremden Lieferanten;
   - war er freier Text (Tippfehler berichtigen, mit den Stammdaten verknüpfen), ist es derselbe Lieferant unter neuem Namen:
     die Container dieses Schlachthofs mit offener Bewertung und dem bisherigen Lieferanten bekommen ihn mit. */
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
    $lieferant = ci_lieferant_schluessel($neu);
    foreach ($doc['liste'] as $k => $x) {
        if ($k !== $i && ci_lieferant_schluessel($x) === $lieferant && mb_strtolower($x['name']) === mb_strtolower($neu['name']))
            fail('Diesen Schlachthof gibt es bei dem Lieferanten schon' . ($x['aktiv'] ? '' : ' (archiviert)') . '.', 422);
    }
    if ($alt && ci_lieferant_schluessel($alt) !== $lieferant) ci_schlachthof_lieferant_wechseln($alt, $neu);
    $neu['rev'] = (int)($alt['rev'] ?? 0) + 1; $neu['geaendert'] = eudr_wer($me);
    if ($i === null) $doc['liste'][] = $neu; else $doc['liste'][$i] = $neu;
    store_write('containerimport-schlachthoefe', eudr_fortschreiben($doc));
    return $neu;
}
/* Folgen eines Lieferantenwechsels am Schlachthof für seine Container (Regel siehe ci_schlachthof_speichern). Geschrieben
   wird vor dem Schlachthof: scheitert danach etwas, bringt die Wiederholung beide Dokumente wieder zusammen. */
function ci_schlachthof_lieferant_wechseln(array $alt, array $neu): void
{
    $sendungen = eudr_sendungen();
    $betroffen = array_keys(array_filter($sendungen['liste'], fn($s) => $s['schlachthof'] === $alt['id']));
    if (!$betroffen) return;
    if ($alt['lieferantNr'] !== '') fail('Dem Schlachthof sind schon Container zugeordnet – sein Lieferant lässt sich nicht mehr wechseln. Legen Sie für den anderen Lieferanten einen eigenen Schlachthof an.', 422);
    $bisher = ci_lieferant_schluessel($alt);
    foreach ($betroffen as $k) {
        $s = $sendungen['liste'][$k];
        if (empty($s['abschluss']) && ci_lieferant_schluessel($s) === $bisher) $sendungen['liste'][$k] = ['lieferantNr' => $neu['lieferantNr'], 'lieferant' => $neu['lieferant']] + $s;
    }
    eudr_sendungen_schreiben($sendungen);
}

/* Schlachthof eines Containers aus der Eingabe: leer oder ein Schlachthof desselben Lieferanten ($lieferant = Eintrag mit
   lieferantNr und lieferant). $bisher = der gespeicherte Schlachthof: er bleibt, wenn die Angabe fehlt (älterer Stand der
   Seite), und er bleibt auch archiviert wählbar – neu wählen lässt sich ein archivierter nicht. */
function ci_schlachthof_am_container(array $b, array $lieferant, string $bisher): array
{
    $id = eudr_text($b['schlachthof'] ?? $bisher, 20, 'Schlachthof');
    if ($id === '') return ['schlachthof' => '', 'schlachthofName' => ''];
    $liste = ci_schlachthoefe()['liste'];
    $i = eudr_stelle($liste, $id);
    if ($i === null) throw new InvalidArgumentException('Der gewählte Schlachthof ist nicht (mehr) vorhanden. Bitte neu laden.');
    $h = $liste[$i];
    if (ci_lieferant_schluessel($h) !== ci_lieferant_schluessel($lieferant)) throw new InvalidArgumentException('Der Schlachthof „' . $h['name'] . '“ gehört zu einem anderen Lieferanten. Bitte den Schlachthof neu wählen oder leer lassen.');
    if (!$h['aktiv'] && $id !== $bisher) throw new InvalidArgumentException('Der Schlachthof „' . $h['name'] . '“ ist archiviert.');
    return ['schlachthof' => $id, 'schlachthofName' => $h['name']];
}
