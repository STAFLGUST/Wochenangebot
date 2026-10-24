<?php
declare(strict_types=1);
/* CRM · Vertrieb: Daten und Regeln des Moduls „crm“ (Oberfläche crm.intern, Aktionen in app/api/aktionen/crm.php)

   Kundenstammdaten (Nummer, Firma, Anschrift, Telefon, E-Mail, Vertreter, Gruppe, aktiv) gehören der Verwaltung
   (Entscheidung E-1) und werden hier nur über deren Funktionen gelesen (customers_load, vertreter_load,
   kundengruppen_load) – das CRM ändert sie nie. Das CRM ergänzt je Kunde eigene Angaben:
     crm-kunden        Ansprechpartner, Segment, Phase, Anruf-Rhythmus und -Status, Potenzial, nächster Schritt,
                       Wiedervorlage, Notiz – je Kunde (Schlüssel = Kunden-ID der Verwaltung) bzw. Interessent
     crm-interessenten Interessenten, die (noch) keine Kunden der Verwaltung sind – mit eigenen Adressangaben
     crm-aktivitaeten  Verlauf: Telefonat, E-Mail, Besuch, Muster, Angebot, Bestellung, Notiz – mit Schnappschuss von
                       Firma und Kundennummer (GR-106: spätere Stammdatenänderungen ändern den Verlauf nicht)
   Alle Schreibvorgänge sperren „crm-kunden“ (eine Sperre für alle drei Dokumente, keine Verklemmung).
   Rechte (GR-103): crm.sehen, crm.bearbeiten, crm.exportieren – geprüft in jeder Aktion. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const CRM_SEGMENTE = ['Fleischerei', 'Einzelhandel', 'Cash & Carry', 'Catering', 'Gastronomie', 'Großhandel', 'Industrie', 'Sonstige', 'Nicht zugeordnet'];
const CRM_PHASEN = ['Interessent', 'Erstkontakt', 'Muster/Probe', 'Angebot', 'Verhandlung', 'Bestandskunde', 'Verloren'];
const CRM_ANRUF = ['Offen', 'Erledigt', 'Nochmal'];
const CRM_ARTEN = ['Telefonat', 'E-Mail', 'Besuch', 'Muster/Probe', 'Angebot', 'Bestellung', 'Notiz'];
const CRM_TAGE = ['Montag', 'Dienstag', 'Mittwoch', 'Donnerstag', 'Freitag', 'Samstag'];
const CRM_MAX_KONTAKTE = 12;
const CRM_MAX_INTERESSENTEN = 5000;
const CRM_MAX_AKTIVITAETEN = 50000;   // darüber fallen die ältesten Einträge weg (bei ~20 am Tag nach etwa 7 Jahren)

/* Anruf-Rhythmen (Wiedervorlage „Wann“) wie in der bisherigen Vertriebsliste */
function crm_rhythmen(): array
{
    static $r = null;
    if ($r !== null) return $r;
    $r = [];
    foreach (CRM_TAGE as $t) $r[] = "$t - wöchentlich";
    foreach (CRM_TAGE as $t) $r[] = "$t - 14-tägig (gerade KW)";
    foreach (CRM_TAGE as $t) $r[] = "$t - 14-tägig (ungerade KW)";
    $r[] = 'Monatlich';
    return $r;
}

/* ---------- Laden und Schreiben ---------- */
function crm_kunden_doc(): array
{
    $d = store_read('crm-kunden');
    return ['rev' => (int)($d['rev'] ?? 0), 'eintraege' => is_array($d['eintraege'] ?? null) ? $d['eintraege'] : []];
}
function crm_interessenten_doc(): array
{
    $d = store_read('crm-interessenten');
    return ['rev' => (int)($d['rev'] ?? 0), 'liste' => is_array($d['liste'] ?? null) ? array_values($d['liste']) : []];
}
function crm_aktivitaeten_doc(): array
{
    $d = store_read('crm-aktivitaeten');
    return ['rev' => (int)($d['rev'] ?? 0), 'liste' => is_array($d['liste'] ?? null) ? array_values($d['liste']) : []];
}
function crm_schreiben(string $name, array $doc): void
{
    $doc['rev'] = (int)($doc['rev'] ?? 0) + 1;
    $doc['updatedAt'] = now();
    store_write($name, $doc);
}
function crm_id(string $praefix): string { return $praefix . bin2hex(random_bytes(6)); }

/* ---------- Stammdaten der Verwaltung (nur lesend, Schnittstelle des Eigentümers) ---------- */
function crm_vertreter(): array
{
    $out = [];
    foreach (vertreter_load()['groups'] as $v) $out[] = ['nr' => (string)$v['nr'], 'name' => (string)$v['name'], 'kurz' => (string)($v['kurz'] ?? '')];
    return $out;
}
/* Kunden der Verwaltung: Kunden-ID → Kunde */
function crm_stammkunden(): array
{
    $out = [];
    foreach (customers_load()['customers'] as $c) if (is_array($c) && isset($c['id'])) $out[(string)$c['id']] = $c;
    return $out;
}
/* Ist der Schlüssel ein Kunde der Verwaltung oder ein Interessent des CRM? */
function crm_schluessel_gueltig(string $key): bool
{
    if ($key === '' || strlen($key) > 40) return false;
    if ($key[0] === 'i') { foreach (crm_interessenten_doc()['liste'] as $i) if ($i['id'] === $key) return true; return false; }
    return isset(crm_stammkunden()[$key]);
}
function crm_firma_nr(string $key): array
{
    if ($key !== '' && $key[0] === 'i') { foreach (crm_interessenten_doc()['liste'] as $i) if ($i['id'] === $key) return [(string)$i['firma'], '']; return ['', '']; }
    $c = crm_stammkunden()[$key] ?? null;
    return $c ? [(string)($c['firma'] ?? ''), (string)($c['nr'] ?? '')] : ['', ''];
}

/* Aktiv-Stand eines Kunden bzw. Interessenten – derselbe Standard für „Aktiv in der Wiedervorlage“ wie in crm_liste */
function crm_ist_aktiv(string $key): bool
{
    if ($key !== '' && $key[0] === 'i') { foreach (crm_interessenten_doc()['liste'] as $i) if ($i['id'] === $key) return !empty($i['aktiv']); return false; }
    return !empty((crm_stammkunden()[$key] ?? [])['active']);
}

/* ---------- Prüfen der Eingaben ---------- */
function crm_datum($v, string $was): string
{
    $v = is_string($v) ? trim($v) : '';
    if ($v === '') return '';
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $v) || !checkdate((int)substr($v, 5, 2), (int)substr($v, 8, 2), (int)substr($v, 0, 4))) throw new InvalidArgumentException("$was: bitte ein gültiges Datum angeben.");
    return $v;
}
function crm_zahl($v, string $was): ?float
{
    if ($v === null || $v === '') return null;
    if (is_string($v)) $v = str_replace(',', '.', trim($v));
    if (!is_numeric($v)) throw new InvalidArgumentException("$was: bitte eine Zahl angeben.");
    $n = round((float)$v, 2);
    if ($n < 0 || $n > 10000000) throw new InvalidArgumentException("$was: Wert außerhalb des erlaubten Bereichs.");
    return $n;
}
function crm_wahl($v, array $erlaubt, string $was, bool $leer = true): string
{
    $v = is_string($v) ? trim($v) : '';
    if ($v === '' && $leer) return '';
    if (!in_array($v, $erlaubt, true)) throw new InvalidArgumentException("$was: ungültige Auswahl.");
    return $v;
}
function crm_text($v, int $max, string $was): string
{
    if ($v !== null && !is_string($v) && !is_numeric($v)) throw new InvalidArgumentException("$was: ungültiger Wert.");
    $t = trim(str_replace("\r", '', (string)$v));
    if (mb_strlen($t) > $max) throw new InvalidArgumentException("$was: höchstens $max Zeichen.");
    return preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', $t) ?? '';
}
function crm_email($v, string $was): string
{
    $t = crm_text($v, 160, $was);
    if ($t !== '' && filter_var($t, FILTER_VALIDATE_EMAIL) === false) throw new InvalidArgumentException("$was: die E-Mail-Adresse ist ungültig.");
    return $t;
}
function crm_kontakte($v): array
{
    if (!is_array($v)) throw new InvalidArgumentException('Ansprechpartner: ungültige Angaben.');
    if (count($v) > CRM_MAX_KONTAKTE) throw new InvalidArgumentException('Höchstens ' . CRM_MAX_KONTAKTE . ' Ansprechpartner je Kunde.');
    $out = [];
    foreach (array_values($v) as $i => $k) {
        if (!is_array($k)) throw new InvalidArgumentException('Ansprechpartner: ungültige Angaben.');
        $n = $i + 1;
        $row = ['name' => crm_text($k['name'] ?? '', 80, "Ansprechpartner $n"), 'funktion' => crm_text($k['funktion'] ?? '', 60, "Funktion $n"),
                'telefon' => crm_text($k['telefon'] ?? '', 40, "Telefon $n"), 'email' => crm_email($k['email'] ?? '', "E-Mail $n")];
        if (implode('', $row) === '') continue;   // leere Zeile weglassen
        $out[] = $row;
    }
    return $out;
}

/* Felder eines Kundenblatts: Name => [Bezeichnung, Prüfung, im Protokoll mit Wert] */
function crm_felder(): array
{
    return [
        'segment' => ['Segment', function ($v) { return crm_wahl($v, CRM_SEGMENTE, 'Segment'); }, true],
        'phase' => ['Phase', function ($v) { return crm_wahl($v, CRM_PHASEN, 'Phase'); }, true],
        'kontakte' => ['Ansprechpartner', 'crm_kontakte', false],
        'rhythmus1' => ['Wann', function ($v) { return crm_wahl($v, crm_rhythmen(), 'Wann'); }, true],
        'rhythmus2' => ['Wann 2', function ($v) { return crm_wahl($v, crm_rhythmen(), 'Wann 2'); }, true],
        'anrufStatus' => ['Erledigt', function ($v) { return crm_wahl($v, CRM_ANRUF, 'Erledigt-Status', false); }, true],
        'anrufAktiv' => ['Aktiv in der Wiedervorlage', function ($v) { if (!is_bool($v)) throw new InvalidArgumentException('Aktiv: ungültiger Wert.'); return $v; }, true],
        'potenzialKg' => ['Potenzial kg', function ($v) { return crm_zahl($v, 'Potenzial kg'); }, true],
        'preisKg' => ['Nettoverkaufspreis €/kg', function ($v) { return crm_zahl($v, 'Nettoverkaufspreis'); }, true],
        'dbKg' => ['DB €/kg', function ($v) { return crm_zahl($v, 'DB €/kg'); }, true],
        'bestellKg' => ['Ø Bestellmenge kg', function ($v) { return crm_zahl($v, 'Ø Bestellmenge'); }, true],
        'letzterAuftrag' => ['Letzter Auftrag', function ($v) { return crm_datum($v, 'Letzter Auftrag'); }, true],
        'letzterKontakt' => ['Letzter Kontakt', function ($v) { return crm_datum($v, 'Letzter Kontakt'); }, true],
        'naechsterSchritt' => ['Nächster Schritt', function ($v) { return crm_text($v, 160, 'Nächster Schritt'); }, false],
        'wiedervorlage' => ['Wiedervorlage am', function ($v) { return crm_datum($v, 'Wiedervorlage'); }, true],
        'praeferenz' => ['Kontaktpräferenz', function ($v) { return crm_text($v, 120, 'Kontaktpräferenz'); }, false],
        'notiz' => ['Gesprächsnotiz / Bedarf', function ($v) { return crm_text($v, 2000, 'Notiz'); }, false],
    ];
}
/* Standardwerte eines Kundenblatts (nichts gespeichert = Standard) */
function crm_standard(bool $interessent, bool $aktiv): array
{
    return ['segment' => 'Nicht zugeordnet', 'phase' => $interessent ? 'Interessent' : 'Bestandskunde', 'kontakte' => [], 'rhythmus1' => '', 'rhythmus2' => '',
            'anrufStatus' => 'Offen', 'anrufAktiv' => $aktiv, 'potenzialKg' => null, 'preisKg' => null, 'dbKg' => null, 'bestellKg' => null,
            'letzterAuftrag' => '', 'letzterKontakt' => '', 'naechsterSchritt' => '', 'wiedervorlage' => '', 'praeferenz' => '', 'notiz' => ''];
}
/* Gespeichertes Kundenblatt auf bekannte Felder beschränken (ältere/neuere Fassungen bleiben lesbar, GR-006) */
function crm_blatt(?array $e, bool $interessent, bool $aktiv): array
{
    $out = crm_standard($interessent, $aktiv);
    foreach ($out as $k => $_) if (is_array($e) && array_key_exists($k, $e)) $out[$k] = $e[$k];
    if (!is_array($out['kontakte'])) $out['kontakte'] = [];
    $out['geaendert'] = is_array($e) ? ($e['geaendert'] ?? null) : null;
    $out['geaendertVon'] = is_array($e) ? (string)($e['geaendertVon'] ?? '') : '';
    return $out;
}

/* ---------- Interessenten ---------- */
const CRM_INTERESSENT_FELDER = ['firma' => [120, 'Firma'], 'ansprechpartner' => [120, 'Ansprechpartner'], 'strasse' => [120, 'Straße'], 'plz' => [10, 'PLZ'],
    'ort' => [80, 'Ort'], 'land' => [60, 'Land'], 'telefon' => [40, 'Telefon'], 'email' => [160, 'E-Mail'], 'vertreter' => [10, 'Vertreter'], 'vertreter2' => [10, 'Vertreter 2']];
function crm_interessent_pruefen(array $b, ?array $alt): array
{
    $row = [];
    foreach (CRM_INTERESSENT_FELDER as $f => [$max, $was]) $row[$f] = $f === 'email' ? crm_email($b[$f] ?? '', $was) : crm_text($b[$f] ?? '', $max, $was);
    if (mb_strlen($row['firma']) < 2) throw new InvalidArgumentException('Bitte den Namen der Firma angeben.');
    $vt = array_column(crm_vertreter(), 'nr');
    foreach (['vertreter', 'vertreter2'] as $f) if ($row[$f] !== '' && $row[$f] !== (string)($alt[$f] ?? '') && !in_array($row[$f], $vt, true)) throw new InvalidArgumentException('Diesen Vertreter gibt es nicht. Vertreter werden in der Verwaltung unter Stammdaten → Vertreter gepflegt.');
    // Postleitzahl: nur bei Änderung geprüft (ältere Einträge bleiben speicherbar); Deutschland (Land leer oder „Deutschland“/„DE“)
    // fünfstellig, sonst Ziffern/Buchstaben/Leerzeichen/Bindestrich mit mindestens einer Ziffer (z. B. „1010“, „SW1A 1AA“)
    if ($row['plz'] !== '' && $row['plz'] !== (string)($alt['plz'] ?? '')) {
        $de = in_array(mb_strtolower($row['land']), ['', 'deutschland', 'de', 'germany'], true);
        if ($de ? !preg_match('/^\d{5}$/', $row['plz']) : !preg_match('/^(?=.*\d)[A-Za-z0-9 \-]{3,10}$/', $row['plz']))
            throw new InvalidArgumentException($de ? 'PLZ: bitte fünf Ziffern angeben.' : 'PLZ: bitte eine gültige Postleitzahl angeben.');
    }
    $row['aktiv'] = !array_key_exists('aktiv', $b) || !empty($b['aktiv']);
    return $row;
}

/* ---------- Liste für die Oberfläche ---------- */
/* Kunden der Verwaltung und Interessenten mit Kundenblatt; Angebote nur als Namen (Schnittstelle des Angebots) */
function crm_liste(): array
{
    $blaetter = crm_kunden_doc()['eintraege'];
    $zahl = [];
    foreach (crm_aktivitaeten_doc()['liste'] as $a) $zahl[$a['key']] = ($zahl[$a['key']] ?? 0) + 1;
    $gruppen = [];
    foreach (kundengruppen_load()['groups'] as $g) $gruppen[(string)$g['nr']] = (string)$g['name'];
    $angebotName = [];
    $out = [];
    foreach (crm_stammkunden() as $id => $c) {
        $aktiv = !empty($c['active']);
        $namen = [];
        foreach (customer_offers($c) as $oid) {
            if (!array_key_exists($oid, $angebotName)) { $d = offer_def($oid); $angebotName[$oid] = $d ? (string)$d['name'] : ''; }
            if ($angebotName[$oid] !== '') $namen[] = $angebotName[$oid];
        }
        $out[] = ['key' => $id, 'art' => 'kunde', 'nr' => (string)($c['nr'] ?? ''), 'firma' => (string)($c['firma'] ?? ''), 'ansprechpartner' => (string)($c['ansprechpartner'] ?? ''),
                  'strasse' => (string)($c['strasse'] ?? ''), 'plz' => (string)($c['plz'] ?? ''), 'ort' => (string)($c['ort'] ?? ''), 'land' => (string)($c['land'] ?? ''),
                  'telefon' => (string)($c['telefon'] ?? ''), 'email' => (string)($c['email'] ?? ''), 'vertreter' => (string)($c['vertreter'] ?? ''),
                  'vertreter2' => (string)($c['vertreter2'] ?? ''), 'gruppe' => $gruppen[(string)($c['gruppe'] ?? '')] ?? '', 'aktiv' => $aktiv, 'angebote' => $namen,
                  'crm' => crm_blatt($blaetter[$id] ?? null, false, $aktiv), 'aktivitaeten' => $zahl[$id] ?? 0];
    }
    foreach (crm_interessenten_doc()['liste'] as $i) {
        $aktiv = !empty($i['aktiv']);
        $row = ['key' => $i['id'], 'art' => 'interessent', 'nr' => '', 'gruppe' => '', 'aktiv' => $aktiv, 'angebote' => []];
        foreach (CRM_INTERESSENT_FELDER as $f => $_) $row[$f] = (string)($i[$f] ?? '');
        $row['crm'] = crm_blatt($blaetter[$i['id']] ?? null, true, $aktiv);
        $row['aktivitaeten'] = $zahl[$i['id']] ?? 0;
        $out[] = $row;
    }
    usort($out, function ($a, $b) { return strnatcasecmp($a['firma'], $b['firma']) ?: strcmp($a['key'], $b['key']); });
    return $out;
}

/* Aktivität für die Oberfläche (ohne interne Kennungen der Person) */
function crm_aktivitaet_aus(array $a): array
{
    return ['id' => $a['id'], 'key' => $a['key'], 'art' => $a['art'], 'notiz' => (string)($a['notiz'] ?? ''), 'naechster' => (string)($a['naechster'] ?? ''),
            'faellig' => (string)($a['faellig'] ?? ''), 'at' => $a['at'], 'von' => (string)($a['von'] ?? ''), 'firma' => (string)($a['firma'] ?? ''), 'nr' => (string)($a['nr'] ?? '')];
}

/* Protokolleintrag (GR-106 unberührt): ohne Kontaktdaten und Notizen – nur Kundennummer, Feld und bei Auswahlfeldern der Wert */
function crm_protokoll_aenderungen(string $key, string $nr, array $alt, array $neu): array
{
    $d = [];
    $txt = function ($v) { return is_bool($v) ? ($v ? 'ja' : 'nein') : (is_array($v) ? (string)count($v) : (string)($v ?? '')); };
    foreach (crm_felder() as $f => [$label, , $mitWert]) {
        if (!array_key_exists($f, $neu)) continue;
        $a = $alt[$f] ?? null; $b = $neu[$f];
        if (json_encode($a) === json_encode($b)) continue;
        $d[] = ['k' => "crm:$key|$f", 'code' => $nr !== '' ? $nr : 'Interessent', 'name' => '', 'f' => $label,
                'from' => $mitWert ? $txt($a) : '', 'to' => $mitWert ? $txt($b) : 'geändert'];
    }
    return $d;
}

/* CSV (Semikolon, UTF-8 mit BOM – öffnet in Excel direkt richtig) */
function crm_csv(array $liste, array $vertreter): string
{
    $vn = []; foreach ($vertreter as $v) $vn[$v['nr']] = $v['name'];
    $kopf = ['Art', 'Kundennummer', 'Firma', 'Aktiv', 'Vertreter', 'Vertreter 2', 'Kundengruppe', 'Segment', 'Phase', 'Straße', 'PLZ', 'Ort', 'Land', 'Telefon', 'E-Mail',
             'Ansprechpartner', 'Weitere Ansprechpartner', 'Wann', 'Wann 2', 'Erledigt', 'Nächster Schritt', 'Wiedervorlage', 'Letzter Kontakt', 'Letzter Auftrag',
             'Potenzial kg', 'Netto €/kg', 'DB €/kg', 'Ø Bestellmenge kg', 'Kontaktpräferenz', 'Notiz'];
    $zelle = function ($v) {
        $s = is_float($v) ? str_replace('.', ',', (string)$v) : (string)$v;
        if ($s !== '' && strpbrk($s[0], '=+-@') !== false) $s = "'" . $s;   // keine Formeln in Excel (CSV-Injection)
        return '"' . str_replace('"', '""', str_replace(["\r", "\n"], ' ', $s)) . '"';
    };
    $zeilen = [implode(';', array_map($zelle, $kopf))];
    foreach ($liste as $k) {
        $c = $k['crm'];
        $weitere = implode(' | ', array_map(function ($p) { return trim(implode(', ', array_filter([$p['name'], $p['funktion'], $p['telefon'], $p['email']]))); }, $c['kontakte']));
        $zeilen[] = implode(';', array_map($zelle, [$k['art'] === 'kunde' ? 'Kunde' : 'Interessent', $k['nr'], $k['firma'], $k['aktiv'] ? 'Ja' : 'Nein',
            $vn[$k['vertreter']] ?? $k['vertreter'], $vn[$k['vertreter2']] ?? $k['vertreter2'], $k['gruppe'], $c['segment'], $c['phase'], $k['strasse'], $k['plz'], $k['ort'],
            $k['land'], $k['telefon'], $k['email'], $k['ansprechpartner'], $weitere, $c['rhythmus1'], $c['rhythmus2'], $c['anrufStatus'], $c['naechsterSchritt'],
            $c['wiedervorlage'], $c['letzterKontakt'], $c['letzterAuftrag'], $c['potenzialKg'] ?? '', $c['preisKg'] ?? '', $c['dbKg'] ?? '', $c['bestellKg'] ?? '',
            $c['praeferenz'], $c['notiz']]));
    }
    return "\xEF\xBB\xBF" . implode("\r\n", $zeilen) . "\r\n";
}
