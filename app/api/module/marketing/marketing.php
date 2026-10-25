<?php
declare(strict_types=1);
/* Marketing · Redaktionsplan: Daten und Regeln des Moduls „marketing“ (Oberfläche marketing.intern, Aktionen in
   app/api/aktionen/marketing.php) – Planung von Social-Media-Inhalten von der Idee bis zur Veröffentlichung.

   Eigene Dokumente (alle Schreibvorgänge unter der Sperre „marketing-beitraege“, eine Sperre für alle drei):
     marketing-beitraege     Beiträge: Titel, Marke, Kanäle, Format, Content-Säule, Kampagne, Verantwortliche/r, Termine
                             (Dreh, Produktion bis, Veröffentlichung), Hook, Text, Hashtags, Call-to-Action, Skript/Briefing,
                             Checkliste, Links zum Material, KI-Kennzeichen, Status mit Freigabe, Veröffentlichungs-Links und
                             Kennzahlen je Kanal, Kommentare und Verlauf (mit Namen als Schnappschuss, GR-106)
     marketing-kampagnen     Kampagnen mit Zeitraum, Ziel und Farbe
     marketing-einstellungen Marken, Kanäle, Formate und Content-Säulen (fehlt das Dokument, gelten die Grundwerte)
   Gelesen (Eigentümer Plattform, über users_load): Mitarbeiter, die als Verantwortliche wählbar sind.
   Ablauf: idee → planung → produktion → freigabe → geplant → veroeffentlicht (jederzeit: verworfen). „geplant“ setzt nur,
   wer marketing.freigeben hat; ändert jemand ohne dieses Recht einen freigegebenen Beitrag inhaltlich, geht er zurück in
   die Freigabe. Rechte (GR-103): marketing.sehen, marketing.bearbeiten, marketing.freigeben, marketing.verwalten.
   Gespeicherte Felder, die diese Fassung nicht kennt, bleiben beim Speichern erhalten (GR-006). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const MKT_STATUS = ['idee' => 'Idee', 'planung' => 'In Planung', 'produktion' => 'In Produktion', 'freigabe' => 'Zur Freigabe',
    'geplant' => 'Freigegeben & geplant', 'veroeffentlicht' => 'Veröffentlicht', 'verworfen' => 'Verworfen'];
const MKT_PRIO = ['normal', 'hoch'];
const MKT_MAX_BEITRAEGE = 20000;
const MKT_MAX_KAMPAGNEN = 500;
const MKT_MAX_LINKS = 15;
const MKT_MAX_CHECKLISTE = 40;
const MKT_MAX_KOMMENTARE = 300;
const MKT_MAX_VERLAUF = 200;
const MKT_MAX_LISTE = 30;          // Einträge je Einstellungsliste (Marken, Kanäle, Formate, Säulen)
// Felder, deren Änderung eine erteilte Freigabe zurücknimmt (Inhalt und Termin dessen, was veröffentlicht wird)
const MKT_FREIGABE_FELDER = ['titel', 'marke', 'kanaele', 'format', 'veroeffentlichung', 'hook', 'text', 'hashtags', 'cta', 'ki'];
const MKT_FARBEN = ['#8c1d2c', '#2f7a52', '#2f6fb0', '#c27a1a', '#7a4fb0', '#1f8a8a', '#b0446c', '#5c6b7a'];

/* ---------- Grundwerte der Einstellungen ---------- */
function mkt_grundwerte(): array
{
    return [
        'marken' => [['id' => 'standard-fleisch', 'name' => 'Standard-Fleisch', 'farbe' => '#8c1d2c', 'aktiv' => true],
                     ['id' => 'fleischmeister', 'name' => 'Fleischmeister', 'farbe' => '#2f7a52', 'aktiv' => true]],
        // limit: Zeichen für den Beitragstext (Hinweis in der Oberfläche), hashtags: empfohlene Höchstzahl
        'kanaele' => [['id' => 'instagram', 'name' => 'Instagram', 'aktiv' => true, 'limit' => 2200, 'hashtags' => 30],
                      ['id' => 'facebook', 'name' => 'Facebook', 'aktiv' => true, 'limit' => 63206, 'hashtags' => 0],
                      ['id' => 'linkedin', 'name' => 'LinkedIn', 'aktiv' => true, 'limit' => 3000, 'hashtags' => 0],
                      ['id' => 'tiktok', 'name' => 'TikTok', 'aktiv' => true, 'limit' => 2200, 'hashtags' => 0],
                      ['id' => 'youtube', 'name' => 'YouTube', 'aktiv' => true, 'limit' => 5000, 'hashtags' => 15],
                      ['id' => 'website', 'name' => 'Website', 'aktiv' => true, 'limit' => 0, 'hashtags' => 0],
                      ['id' => 'newsletter', 'name' => 'Newsletter', 'aktiv' => true, 'limit' => 0, 'hashtags' => 0]],
        'formate' => [['id' => 'reel', 'name' => 'Reel / Kurzvideo', 'aktiv' => true], ['id' => 'karussell', 'name' => 'Karussell', 'aktiv' => true],
                      ['id' => 'bild', 'name' => 'Bild-Post', 'aktiv' => true], ['id' => 'story', 'name' => 'Story', 'aktiv' => true],
                      ['id' => 'video', 'name' => 'Video (lang)', 'aktiv' => true], ['id' => 'live', 'name' => 'Live', 'aktiv' => true],
                      ['id' => 'artikel', 'name' => 'Artikel / Text', 'aktiv' => true]],
        'saeulen' => [['id' => 'produkt', 'name' => 'Produkt & Qualität', 'farbe' => '#8c1d2c', 'aktiv' => true],
                      ['id' => 'kulissen', 'name' => 'Hinter den Kulissen', 'farbe' => '#2f6fb0', 'aktiv' => true],
                      ['id' => 'wissen', 'name' => 'Wissen & Tipps', 'farbe' => '#2f7a52', 'aktiv' => true],
                      ['id' => 'team', 'name' => 'Team & Recruiting', 'farbe' => '#7a4fb0', 'aktiv' => true],
                      ['id' => 'aktion', 'name' => 'Aktionen & Angebote', 'farbe' => '#c27a1a', 'aktiv' => true],
                      ['id' => 'branche', 'name' => 'Branche & Markt', 'farbe' => '#1f8a8a', 'aktiv' => true]],
    ];
}

/* ---------- Laden und Schreiben ---------- */
function mkt_beitraege_doc(): array
{
    $d = store_read('marketing-beitraege');
    return ['rev' => (int)($d['rev'] ?? 0), 'liste' => is_array($d['liste'] ?? null) ? array_values($d['liste']) : []] + (is_array($d) ? $d : []);
}
function mkt_kampagnen_doc(): array
{
    $d = store_read('marketing-kampagnen');
    return ['rev' => (int)($d['rev'] ?? 0), 'liste' => is_array($d['liste'] ?? null) ? array_values($d['liste']) : []] + (is_array($d) ? $d : []);
}
/* Einstellungen: gespeicherte Listen, fehlende Listen aus den Grundwerten */
function mkt_einstellungen(): array
{
    $d = store_read('marketing-einstellungen');
    $d = is_array($d) ? $d : [];
    $out = ['rev' => (int)($d['rev'] ?? 0)];
    foreach (mkt_grundwerte() as $k => $grund) $out[$k] = is_array($d[$k] ?? null) && $d[$k] ? array_values($d[$k]) : $grund;
    return $out + $d;
}
function mkt_schreiben(string $name, array $doc): void
{
    $doc['rev'] = (int)($doc['rev'] ?? 0) + 1;
    $doc['updatedAt'] = now();
    store_write($name, $doc);
}
function mkt_id(string $praefix): string { return $praefix . bin2hex(random_bytes(6)); }
function mkt_ids(array $liste): array { return array_values(array_map(function ($x) { return (string)$x['id']; }, $liste)); }

/* Mitarbeiter, die Beiträge bearbeiten dürfen (wählbar als Verantwortliche) – Schnittstelle der Plattform (users_load) */
function mkt_team(): array
{
    $out = [];
    foreach (users_load() as $u) {
        if (empty($u['active']) || ($u['zugang'] ?? true) === false || !may($u, 'marketing.bearbeiten')) continue;
        $out[] = ['id' => (string)$u['id'], 'name' => (string)($u['name'] ?? $u['username'] ?? '')];
    }
    usort($out, function ($a, $b) { return strnatcasecmp($a['name'], $b['name']); });
    return $out;
}

/* ---------- Prüfen der Eingaben ---------- */
function mkt_text($v, int $max, string $was): string
{
    if ($v !== null && !is_string($v) && !is_numeric($v)) throw new InvalidArgumentException("$was: ungültiger Wert.");
    $t = trim(str_replace("\r", '', (string)$v));
    if (mb_strlen($t) > $max) throw new InvalidArgumentException("$was: höchstens $max Zeichen.");
    return preg_replace('/[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]/u', '', $t) ?? '';
}
function mkt_datum($v, string $was): string
{
    $v = is_string($v) ? trim($v) : '';
    if ($v === '') return '';
    if (!preg_match('/^\d{4}-\d{2}-\d{2}$/', $v) || !checkdate((int)substr($v, 5, 2), (int)substr($v, 8, 2), (int)substr($v, 0, 4))) throw new InvalidArgumentException("$was: bitte ein gültiges Datum angeben.");
    return $v;
}
/* Veröffentlichung: Datum, optional mit Uhrzeit (Ortszeit), „JJJJ-MM-TT“ oder „JJJJ-MM-TTTHH:MM“ */
function mkt_termin($v, string $was): string
{
    $v = is_string($v) ? trim($v) : '';
    if ($v === '') return '';
    if (!preg_match('/^(\d{4}-\d{2}-\d{2})(?:T([01]\d|2[0-3]):([0-5]\d))?$/', $v, $m)) throw new InvalidArgumentException("$was: bitte Datum (und Uhrzeit) angeben.");
    mkt_datum($m[1], $was);
    return $v;
}
function mkt_url($v, string $was): string
{
    $t = mkt_text($v, 500, $was);
    if ($t === '') return '';
    // nur Webadressen – keine javascript:/data:-Verweise in Links, die andere anklicken
    if (!preg_match('#^https?://[^\s<>"]+$#i', $t) || filter_var($t, FILTER_VALIDATE_URL) === false) throw new InvalidArgumentException("$was: bitte eine Webadresse mit https:// angeben.");
    return $t;
}
function mkt_wahl($v, array $erlaubt, string $was, bool $leer = true): string
{
    $v = is_string($v) ? trim($v) : '';
    if ($v === '' && $leer) return '';
    if (!in_array($v, $erlaubt, true)) throw new InvalidArgumentException("$was: ungültige Auswahl.");
    return $v;
}
function mkt_zahl($v, string $was): ?int
{
    if ($v === null || $v === '') return null;
    if (is_string($v)) $v = str_replace(['.', ' '], '', trim($v));
    if (!is_numeric($v) || (float)$v < 0 || (float)$v > 1e12) throw new InvalidArgumentException("$was: bitte eine Zahl ab 0 angeben.");
    return (int)round((float)$v);
}
function mkt_farbe($v, string $was): string
{
    $v = is_string($v) ? strtolower(trim($v)) : '';
    if (!preg_match('/^#[0-9a-f]{6}$/', $v)) throw new InvalidArgumentException("$was: ungültige Farbe.");
    return $v;
}

/* ---------- Beitrag ---------- */
/* Grundform eines Beitrags (für neue Beiträge und zum Auffüllen älterer Fassungen beim Lesen) */
function mkt_beitrag_leer(): array
{
    return ['id' => '', 'titel' => '', 'status' => 'idee', 'prioritaet' => 'normal', 'marke' => '', 'kanaele' => [], 'format' => '', 'saeule' => '',
            'kampagne' => '', 'verantwortlich' => '', 'drehtermin' => '', 'produktionBis' => '', 'veroeffentlichung' => '', 'hook' => '', 'text' => '',
            'hashtags' => '', 'cta' => '', 'notizen' => '', 'checkliste' => [], 'links' => [], 'ki' => false, 'freigabe' => null,
            'veroeffentlicht' => [], 'ergebnisse' => [], 'kommentare' => [], 'verlauf' => [], 'rev' => 0];
}

/* Felder einer Anfrage prüfen – nur die mitgeschickten (Teiländerung, z. B. Termin beim Verschieben im Kalender) */
function mkt_felder_pruefen(array $f, array $einst, array $kampagnen, array $team): array
{
    $marken = mkt_ids($einst['marken']); $kanaele = mkt_ids($einst['kanaele']); $formate = mkt_ids($einst['formate']); $saeulen = mkt_ids($einst['saeulen']);
    $out = [];
    foreach ($f as $k => $v) {
        switch ($k) {
            case 'titel': $out[$k] = mkt_text($v, 140, 'Titel'); if ($out[$k] === '') throw new InvalidArgumentException('Bitte einen Titel angeben.'); break;
            case 'prioritaet': $out[$k] = mkt_wahl($v, MKT_PRIO, 'Priorität', false); break;
            case 'marke': $out[$k] = mkt_wahl($v, $marken, 'Marke'); break;
            case 'format': $out[$k] = mkt_wahl($v, $formate, 'Format'); break;
            case 'saeule': $out[$k] = mkt_wahl($v, $saeulen, 'Content-Säule'); break;
            case 'kampagne': $out[$k] = mkt_wahl($v, mkt_ids($kampagnen), 'Kampagne'); break;
            case 'verantwortlich':
                $v = is_string($v) ? trim($v) : '';
                if ($v !== '' && !in_array($v, mkt_ids($team), true)) throw new InvalidArgumentException('Verantwortlich: bitte eine Person mit Bearbeitungsrecht wählen.');
                $out[$k] = $v; break;
            case 'kanaele':
                if (!is_array($v)) throw new InvalidArgumentException('Kanäle: ungültige Auswahl.');
                $out[$k] = [];
                foreach ($v as $x) { $x = mkt_wahl($x, $kanaele, 'Kanal', false); if (!in_array($x, $out[$k], true)) $out[$k][] = $x; }
                break;
            case 'drehtermin': $out[$k] = mkt_datum($v, 'Drehtermin'); break;
            case 'produktionBis': $out[$k] = mkt_datum($v, 'Produktion bis'); break;
            case 'veroeffentlichung': $out[$k] = mkt_termin($v, 'Veröffentlichung'); break;
            case 'hook': $out[$k] = mkt_text($v, 300, 'Hook'); break;
            case 'text': $out[$k] = mkt_text($v, 5000, 'Text'); break;
            case 'hashtags': $out[$k] = mkt_text($v, 1000, 'Hashtags'); break;
            case 'cta': $out[$k] = mkt_text($v, 200, 'Call-to-Action'); break;
            case 'notizen': $out[$k] = mkt_text($v, 20000, 'Skript / Briefing'); break;
            case 'ki': if (!is_bool($v)) throw new InvalidArgumentException('KI-Kennzeichen: ungültiger Wert.'); $out[$k] = $v; break;
            case 'checkliste':
                if (!is_array($v) || count($v) > MKT_MAX_CHECKLISTE) throw new InvalidArgumentException('Checkliste: höchstens ' . MKT_MAX_CHECKLISTE . ' Punkte.');
                $out[$k] = [];
                foreach (array_values($v) as $i => $p) {
                    if (!is_array($p)) throw new InvalidArgumentException('Checkliste: ungültige Angaben.');
                    $t = mkt_text($p['text'] ?? '', 200, 'Checkliste ' . ($i + 1));
                    if ($t !== '') $out[$k][] = ['text' => $t, 'erledigt' => !empty($p['erledigt'])];
                }
                break;
            case 'links':
                if (!is_array($v) || count($v) > MKT_MAX_LINKS) throw new InvalidArgumentException('Material: höchstens ' . MKT_MAX_LINKS . ' Links.');
                $out[$k] = [];
                foreach (array_values($v) as $i => $l) {
                    if (!is_array($l)) throw new InvalidArgumentException('Material: ungültige Angaben.');
                    $n = $i + 1; $url = mkt_url($l['url'] ?? '', "Link $n"); $t = mkt_text($l['titel'] ?? '', 80, "Bezeichnung $n");
                    if ($url !== '') $out[$k][] = ['titel' => $t, 'url' => $url];
                }
                break;
            case 'veroeffentlicht':   // Link zum veröffentlichten Beitrag je Kanal
                if (!is_array($v)) throw new InvalidArgumentException('Veröffentlichte Beiträge: ungültige Angaben.');
                $out[$k] = [];
                foreach ($v as $kanal => $url) { $kanal = mkt_wahl((string)$kanal, $kanaele, 'Kanal', false); $u = mkt_url($url, 'Link ' . $kanal); if ($u !== '') $out[$k][$kanal] = $u; }
                break;
            case 'ergebnisse':        // Kennzahlen je Kanal (von Hand aus den Statistiken der Netzwerke)
                if (!is_array($v)) throw new InvalidArgumentException('Kennzahlen: ungültige Angaben.');
                $out[$k] = [];
                foreach ($v as $kanal => $z) {
                    $kanal = mkt_wahl((string)$kanal, $kanaele, 'Kanal', false);
                    if (!is_array($z)) throw new InvalidArgumentException('Kennzahlen: ungültige Angaben.');
                    $row = ['reichweite' => mkt_zahl($z['reichweite'] ?? null, 'Reichweite'), 'interaktionen' => mkt_zahl($z['interaktionen'] ?? null, 'Interaktionen'),
                            'aufrufe' => mkt_zahl($z['aufrufe'] ?? null, 'Aufrufe')];
                    if (array_filter($row, function ($x) { return $x !== null; })) $out[$k][$kanal] = $row;
                }
                break;
            default: throw new InvalidArgumentException('Unbekanntes Feld: ' . substr((string)$k, 0, 40));
        }
    }
    return $out;
}

/* Verlaufseintrag (Name als Schnappschuss, GR-106) */
function mkt_verlauf(array &$e, array $me, string $was): void
{
    $e['verlauf'] = is_array($e['verlauf'] ?? null) ? $e['verlauf'] : [];
    $e['verlauf'][] = ['t' => now(), 'von' => (string)$me['name'], 'was' => $was];
    if (count($e['verlauf']) > MKT_MAX_VERLAUF) $e['verlauf'] = array_slice($e['verlauf'], -MKT_MAX_VERLAUF);
}

/* Statuswechsel nach den Regeln des Ablaufs. Gibt den Verlaufstext zurück. */
function mkt_status_setzen(array &$e, string $neu, array $me): string
{
    if (!isset(MKT_STATUS[$neu])) throw new InvalidArgumentException('Unbekannter Status.');
    $alt = (string)($e['status'] ?? 'idee');
    if ($alt === $neu) return '';
    $freigeber = may($me, 'marketing.freigeben');
    if ($neu === 'geplant') {
        if (!$freigeber) fail('Freigeben darf nur, wer das Recht „Beiträge freigeben“ hat. Bitte auf „Zur Freigabe“ setzen.', 403);
        if (($e['veroeffentlichung'] ?? '') === '') throw new InvalidArgumentException('Zum Freigeben bitte zuerst den Veröffentlichungstermin eintragen.');
        if (!($e['kanaele'] ?? [])) throw new InvalidArgumentException('Zum Freigeben bitte mindestens einen Kanal wählen.');
        $e['freigabe'] = ['t' => now(), 'von' => (string)$me['name'], 'vonId' => (string)$me['id']];
    } elseif ($neu === 'veroeffentlicht') {
        if ($alt !== 'geplant' && !$freigeber) fail('Veröffentlicht werden nur freigegebene Beiträge. Bitte zuerst freigeben lassen.', 409);
        if (!$e['freigabe'] && $freigeber) $e['freigabe'] = ['t' => now(), 'von' => (string)$me['name'], 'vonId' => (string)$me['id']];
        $e['veroeffentlichtAm'] = now();
    } elseif ($neu !== 'verworfen') {
        // zurück in eine frühere Stufe: eine erteilte Freigabe gilt nicht mehr
        if ($alt === 'veroeffentlicht' && !$freigeber) fail('Einen veröffentlichten Beitrag zurückstufen darf nur, wer freigeben darf.', 403);
        $e['freigabe'] = null;
        unset($e['veroeffentlichtAm']);
    }
    $e['status'] = $neu;
    return 'Status: ' . MKT_STATUS[$alt] . ' → ' . MKT_STATUS[$neu];
}

/* Beitrag für die Oberfläche: Grundform aufgefüllt, Name der/des Verantwortlichen */
function mkt_beitrag_aus(array $e, array $teamNamen): array
{
    $e = $e + mkt_beitrag_leer();
    $e['verantwortlichName'] = $e['verantwortlich'] !== '' ? ($teamNamen[$e['verantwortlich']] ?? (string)($e['verantwortlichSchnappschuss'] ?? '')) : '';
    return $e;
}
function mkt_team_namen(): array
{
    $n = [];
    foreach (users_load() as $u) $n[(string)$u['id']] = (string)($u['name'] ?? $u['username'] ?? '');
    return $n;
}

/* ---------- Einstellungen und Kampagnen ---------- */
/* Eine Einstellungsliste prüfen; vorhandene Kennungen bleiben, neue entstehen aus dem Namen. Weitere Felder je Eintrag bleiben. */
function mkt_liste_pruefen($v, string $was, bool $mitFarbe, bool $kanal, array $alt): array
{
    if (!is_array($v) || !$v) throw new InvalidArgumentException("$was: mindestens ein Eintrag.");
    if (count($v) > MKT_MAX_LISTE) throw new InvalidArgumentException("$was: höchstens " . MKT_MAX_LISTE . ' Einträge.');
    $altNach = []; foreach ($alt as $a) if (is_array($a) && isset($a['id'])) $altNach[(string)$a['id']] = $a;
    $vorhanden = [];   // in der Anfrage ausdrücklich genannte Kennungen – neue Kennungen dürfen sie nicht belegen
    foreach ($v as $x) if (is_array($x) && is_string($x['id'] ?? null) && $x['id'] !== '') $vorhanden[] = trim($x['id']);
    $out = []; $ids = [];
    foreach (array_values($v) as $i => $x) {
        if (!is_array($x)) throw new InvalidArgumentException("$was: ungültige Angaben.");
        $name = mkt_text($x['name'] ?? '', 60, "$was " . ($i + 1));
        if ($name === '') throw new InvalidArgumentException("$was " . ($i + 1) . ': bitte einen Namen angeben.');
        $id = is_string($x['id'] ?? null) ? trim($x['id']) : '';
        if ($id === '' || !preg_match('/^[a-z0-9-]{1,40}$/', $id)) {
            $basis = trim(preg_replace('/[^a-z0-9]+/', '-', strtr(mb_strtolower($name), ['ä' => 'ae', 'ö' => 'oe', 'ü' => 'ue', 'ß' => 'ss'])) ?? '', '-');
            $basis = substr($basis !== '' ? $basis : 'eintrag', 0, 32); $id = $basis; $n = 2;
            while (in_array($id, $ids, true) || in_array($id, $vorhanden, true) || isset($altNach[$id])) $id = $basis . '-' . $n++;
        }
        if (in_array($id, $ids, true)) throw new InvalidArgumentException("$was: „$name“ ist doppelt.");
        $ids[] = $id;
        $row = ($altNach[$id] ?? []);
        $row['id'] = $id; $row['name'] = $name; $row['aktiv'] = !array_key_exists('aktiv', $x) || !empty($x['aktiv']);
        if ($mitFarbe) $row['farbe'] = mkt_farbe($x['farbe'] ?? MKT_FARBEN[$i % count(MKT_FARBEN)], "$was „{$name}“");
        if ($kanal) {
            $row['limit'] = (int)(mkt_zahl($x['limit'] ?? 0, "Zeichengrenze „{$name}“") ?? 0);
            $row['hashtags'] = (int)(mkt_zahl($x['hashtags'] ?? 0, "Hashtags „{$name}“") ?? 0);
            if ($row['limit'] > 100000 || $row['hashtags'] > 100) throw new InvalidArgumentException("„{$name}“: Grenze zu hoch.");
        }
        $out[] = $row;
    }
    return $out;
}
function mkt_kampagne_pruefen(array $b, ?array $alt, array $einst): array
{
    $row = $alt ?? [];
    $row['name'] = mkt_text($b['name'] ?? '', 100, 'Name');
    if ($row['name'] === '') throw new InvalidArgumentException('Bitte einen Namen für die Kampagne angeben.');
    $row['ziel'] = mkt_text($b['ziel'] ?? '', 500, 'Ziel');
    $row['von'] = mkt_datum($b['von'] ?? '', 'Beginn');
    $row['bis'] = mkt_datum($b['bis'] ?? '', 'Ende');
    if ($row['von'] !== '' && $row['bis'] !== '' && $row['bis'] < $row['von']) throw new InvalidArgumentException('Das Ende liegt vor dem Beginn.');
    $row['marke'] = mkt_wahl($b['marke'] ?? '', mkt_ids($einst['marken']), 'Marke');
    $row['farbe'] = mkt_farbe($b['farbe'] ?? MKT_FARBEN[0], 'Farbe');
    $row['archiviert'] = !empty($b['archiviert']);
    return $row;
}

/* ---------- Liste als CSV (Excel) ---------- */
function mkt_csv(array $liste, array $einst, array $kampagnen): string
{
    $name = function (array $l, string $id) { foreach ($l as $x) if ($x['id'] === $id) return (string)$x['name']; return $id; };
    $kopf = ['Titel', 'Status', 'Veröffentlichung', 'Marke', 'Kanäle', 'Format', 'Content-Säule', 'Kampagne', 'Verantwortlich', 'Drehtermin', 'Produktion bis',
             'Priorität', 'KI-generiert', 'Hook', 'Text', 'Hashtags', 'Call-to-Action', 'Freigegeben von', 'Freigegeben am', 'Links veröffentlicht', 'Reichweite', 'Interaktionen'];
    $zelle = function ($v) {
        $s = (string)$v;
        if ($s !== '' && strpbrk($s[0], '=+-@') !== false) $s = "'" . $s;   // keine Formeln in Excel (CSV-Injection)
        return '"' . str_replace('"', '""', str_replace(["\r", "\n"], ' ', $s)) . '"';
    };
    $zeilen = [implode(';', array_map($zelle, $kopf))];
    foreach ($liste as $e) {
        $reich = 0; $inter = 0;
        foreach ($e['ergebnisse'] as $z) { $reich += (int)($z['reichweite'] ?? 0); $inter += (int)($z['interaktionen'] ?? 0); }
        $zeilen[] = implode(';', array_map($zelle, [$e['titel'], MKT_STATUS[$e['status']] ?? $e['status'], str_replace('T', ' ', $e['veroeffentlichung']),
            $e['marke'] !== '' ? $name($einst['marken'], $e['marke']) : '', implode(', ', array_map(function ($k) use ($name, $einst) { return $name($einst['kanaele'], $k); }, $e['kanaele'])),
            $e['format'] !== '' ? $name($einst['formate'], $e['format']) : '', $e['saeule'] !== '' ? $name($einst['saeulen'], $e['saeule']) : '',
            $e['kampagne'] !== '' ? $name($kampagnen, $e['kampagne']) : '', $e['verantwortlichName'], $e['drehtermin'], $e['produktionBis'],
            $e['prioritaet'] === 'hoch' ? 'hoch' : 'normal', $e['ki'] ? 'Ja' : 'Nein', $e['hook'], $e['text'], $e['hashtags'], $e['cta'],
            $e['freigabe']['von'] ?? '', isset($e['freigabe']['t']) ? substr($e['freigabe']['t'], 0, 10) : '', implode(' ', array_values($e['veroeffentlicht'])),
            $reich ?: '', $inter ?: '']));
    }
    return "\xEF\xBB\xBF" . implode("\r\n", $zeilen) . "\r\n";
}
