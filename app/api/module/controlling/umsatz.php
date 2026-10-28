<?php
declare(strict_types=1);
/* Controlling · Bereich Umsatzstatistik: Kg, Umsatz und Deckungsbeitrag je Vertreter und Monat (Monatsmeldung von Hand),
   ausgewertet in der Oberfläche (Kennzahlen, Anteile, Spanne = DB ÷ Umsatz, Monatsvergleich).
   Dokument „controlling-umsatz“ (vertraulich): { rev, jahre: { "JJJJ": { "MM": { "<Vertreter-Nr>": { kg, umsatz, db } } } },
   vertreter: { "<Nr>": { name, kurz } } (Schnappschuss der Namen, GR-106), geaendert }.
   Vertreter kommen aus den Stammdaten der Verwaltung (vertreter_load, nur lesend, GR-101). Wer dort entfällt, behält seine
   gespeicherten Werte und erscheint weiter in der Auswertung („ausgeschieden“); erfassen lassen sich nur aktuelle Vertreter. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Gespeichertes Dokument mit Standardwerten; unbekannte (neuere) Felder bleiben erhalten (GR-006) */
function controlling_umsatz_doc(): array
{
    $d = store_read('controlling-umsatz') ?? [];
    return ['rev' => (int)($d['rev'] ?? 0), 'jahre' => is_array($d['jahre'] ?? null) ? $d['jahre'] : [],
            'vertreter' => is_array($d['vertreter'] ?? null) ? $d['vertreter'] : [], 'geaendert' => $d['geaendert'] ?? null] + $d;
}

/* Aktuelle Vertreter aus den Stammdaten: Nummer → Name, Kürzel */
function controlling_umsatz_stammvertreter(): array
{
    $out = [];
    foreach ((array)(vertreter_load()['groups'] ?? []) as $v) {
        if (!is_array($v)) continue;
        $nr = trim((string)($v['nr'] ?? ''));
        if ($nr === '') continue;
        $out[$nr] = ['name' => trim((string)($v['name'] ?? '')), 'kurz' => trim((string)($v['kurz'] ?? ''))];
    }
    return $out;
}

/* Vertreter für die Oberfläche: aktuelle aus den Stammdaten, dazu ausgeschiedene mit gespeicherten Werten (Name aus dem Schnappschuss) */
function controlling_umsatz_vertreter(array $doc): array
{
    $stamm = controlling_umsatz_stammvertreter();
    $mitWerten = [];
    foreach ($doc['jahre'] as $monate) foreach ((array)$monate as $werte) foreach (array_keys((array)$werte) as $nr) $mitWerten[(string)$nr] = true;
    $out = [];
    foreach ($stamm + array_fill_keys(array_keys($mitWerten), null) as $nr => $v) {
        $nr = (string)$nr;
        $aktiv = isset($stamm[$nr]);
        $v = $aktiv ? $stamm[$nr] : (is_array($doc['vertreter'][$nr] ?? null) ? $doc['vertreter'][$nr] : ['name' => '', 'kurz' => '']);
        $name = (string)($v['name'] ?? ''); $kurz = (string)($v['kurz'] ?? '');
        $out[] = ['nr' => $nr, 'name' => $name, 'kurz' => $kurz, 'aktiv' => $aktiv,
                  'anzeige' => $nr . ' – ' . ($kurz !== '' ? $kurz : ($name !== '' ? $name : $nr)) . ($aktiv ? '' : ' (ausgeschieden)')];
    }
    usort($out, fn($a, $b) => $a['aktiv'] === $b['aktiv'] ? strnatcasecmp($a['nr'], $b['nr']) : ($a['aktiv'] ? -1 : 1));   // aktuelle zuerst
    return $out;
}

/* Monatsmeldung prüfen: Jahr, Monat und Werte je aktuellem Vertreter. Nicht mitgeschickte Vertreter behalten ihre Werte. */
function controlling_umsatz_eingabe(array $b): array
{
    $jahr = controlling_jahr($b['jahr'] ?? null);
    $monat = controlling_monat($b['monat'] ?? null);
    $stamm = controlling_umsatz_stammvertreter();
    if (!$stamm) throw new InvalidArgumentException('Es sind keine Vertreter in den Stammdaten eingetragen (Verwaltung → Vertreter).');
    $eingaben = $b['werte'] ?? null;
    if (!is_array($eingaben) || !array_is_list($eingaben) || !$eingaben || count($eingaben) > 500) throw new InvalidArgumentException('Keine Werte übermittelt.');
    $werte = [];
    foreach ($eingaben as $e) {
        if (!is_array($e)) throw new InvalidArgumentException('Ein Vertreterdatensatz ist ungültig.');
        $nr = s($e['vertreterNr'] ?? '', 40, false);
        if ($nr === null || !isset($stamm[$nr])) throw new InvalidArgumentException('Unbekannter Vertreter „' . ($nr ?? '') . '“ – nur Vertreter aus den Stammdaten.');
        if (isset($werte[$nr])) throw new InvalidArgumentException("Vertreter $nr ist doppelt eingetragen.");
        $werte[$nr] = ['kg' => controlling_zahl($e['kg'] ?? null, 3, false, "Vertreter $nr: Kg"),
                       'umsatz' => controlling_zahl($e['umsatz'] ?? null, 2, false, "Vertreter $nr: Umsatz"),
                       'db' => controlling_zahl($e['db'] ?? null, 2, true, "Vertreter $nr: DB")];
    }
    return ['jahr' => $jahr, 'monat' => $monat, 'werte' => $werte, 'stamm' => $stamm];
}

/* Antwort für die Oberfläche */
function controlling_umsatz_antwort(array $me): array
{
    $d = controlling_umsatz_doc();
    $monate = [];
    foreach (CONTROLLING_MONATE as $nr => $name) $monate[] = ['nr' => sprintf('%02d', $nr), 'name' => $name];   // „10“–„12“ sind in PHP Zahlenschlüssel
    return ['ok' => true, 'rev' => $d['rev'], 'jahre' => (object)$d['jahre'], 'monate' => $monate, 'vertreter' => controlling_umsatz_vertreter($d),
            'geaendert' => $d['geaendert'], 'rechte' => ['bearbeiten' => may($me, 'controlling.umsatz_bearbeiten')]];
}
