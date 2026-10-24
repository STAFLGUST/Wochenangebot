<?php
declare(strict_types=1);
/* Kundenstammdaten und Kunden-Sitzung */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Kunden ----------------
   Kunden melden sich auf der Angebotsseite an (eigene Anmeldung, getrennt vom Eingabebereich) und sehen nur
   die Angebote, für die sie freigeschaltet sind. Kunden erhalten nie Zugriff auf Aktionen des Eingabebereichs:
   dort zählt nur die Mitarbeiter-Anmeldung ($_SESSION['uid']), Kunden haben $_SESSION['kid']. */
function customers_load(): array
{
    $d = store_read('kunden');
    return is_array($d) && isset($d['customers']) ? $d : ['rev' => 0, 'customers' => [], 'updatedAt' => null];
}
/* Freigeschaltete Angebote: direkt beim Kunden eingetragen (angebote) oder über seine Kundengruppe (Stammdaten → Angebote) */
function customer_offers_direct(array $c): array
{
    $known = array_merge([OFFER_STD], offer_ids());
    return array_values(array_filter($c['angebote'] ?? [], function ($o) use ($known) { return in_array($o, $known, true); }));
}
/* Über die Kundengruppe: das Angebot, dem die Gruppe zugeordnet ist (Stammdaten → Angebote). Hat die Gruppe kein
   Angebot, gilt automatisch das Wochenangebot. Kunden ohne Gruppe sehen nur ihre direkten Freischaltungen. */
function customer_offers_gruppe(array $c): array
{
    $g = (string)($c['gruppe'] ?? '');
    if ($g === '') return [];
    $out = [];
    foreach (offers_load()['offers'] as $o) if (in_array($g, $o['gruppen'] ?? [], true)) $out[] = $o['id'];
    return $out ?: [OFFER_STD];
}
function customer_offers(array $c): array
{
    $all = array_unique(array_merge(customer_offers_direct($c), customer_offers_gruppe($c)));
    $order = array_merge([OFFER_STD], offer_ids());   // Reihenfolge wie in der Angebotsverwaltung
    return array_values(array_filter($order, function ($o) use ($all) { return in_array($o, $all, true); }));
}
function customer_public(array $c): array
{
    $out = $c;
    $l = $c['login'] ?? null;
    $out['angebote'] = customer_offers($c);                 // wirksam (direkt + über Kundengruppe)
    $out['angeboteDirekt'] = customer_offers_direct($c);
    $out['angeboteGruppe'] = customer_offers_gruppe($c);
    $out['login'] = $l ? ['username' => $l['username'], 'active' => !empty($l['active']), 'mustChange' => !empty($l['mustChange']),
                          'lastLogin' => $l['lastLogin'] ?? null, 'pwSet' => $l['pwSet'] ?? null,
                          'lockedUntil' => (int)($l['lockedUntil'] ?? 0) > time() ? (int)$l['lockedUntil'] : 0,
                          'hasPassword' => !empty($l['hash']),
                          'geraete' => function_exists('geraete_public') ? geraete_public($l) : [],
                          'link' => !empty($l['token']) && (int)$l['token']['exp'] > time() ? ['p' => $l['token']['p'], 'exp' => (int)$l['token']['exp']] : null] : null;
    $out['mailAngebot'] = !array_key_exists('mailAngebot', $c) || !empty($c['mailAngebot']);
    return $out;
}
function kunde_clear(): void { foreach (['kid', 'ksv', 'kseen', 'kcsrf', 'ksid'] as $k) unset($_SESSION[$k]); }
function ksess_prune(array $list): array
{
    $max = (int)sec()['idleMinutes'] * 60;
    foreach ($list as $k => $v) if ((int)($v['seen'] ?? 0) < time() - $max) unset($list[$k]);
    return $list;
}
function ksess_remove(callable $match): int
{
    return with_lock('kundensitzungen', function () use ($match) {
        $list = store_read('kundensitzungen') ?? [];
        $n = 0;
        foreach ($list as $k => $v) if ($match($k, $v)) { unset($list[$k]); $n++; }
        if ($n) store_write('kundensitzungen', $list);
        return $n;
    });
}
/* Angemeldeter Kunde – Stammdaten, Freigabe und Zugang werden bei jeder Anfrage frisch gelesen */
$KUNDE = null;
function current_customer(): ?array
{
    global $KUNDE;
    if ($KUNDE !== null) return $KUNDE ?: null;
    start_session();
    $KUNDE = false;
    if (empty($_SESSION['kid'])) return null;
    if (time() - (int)($_SESSION['kseen'] ?? 0) > (int)sec()['idleMinutes'] * 60) { kunde_clear(); return null; }
    $c = null;
    foreach (customers_load()['customers'] as $x) if ($x['id'] === $_SESSION['kid']) { $c = $x; break; }
    $l = $c['login'] ?? null;
    if (!$c || empty($c['active']) || !$l || empty($l['active']) || (int)($l['sv'] ?? 0) !== (int)($_SESSION['ksv'] ?? -1)) { kunde_clear(); return null; }
    $sid = (string)($_SESSION['ksid'] ?? '');
    $reg = store_read('kundensitzungen') ?? [];
    if ($sid === '' || !isset($reg[$sid]) || $reg[$sid]['kid'] !== $c['id']) { kunde_clear(); return null; }
    if ((int)$reg[$sid]['seen'] < time() - 60) {
        with_lock('kundensitzungen', function () use ($sid) {
            $r = store_read('kundensitzungen') ?? [];
            if (isset($r[$sid])) { $r[$sid]['seen'] = time(); $r[$sid]['ip'] = client_ip(); store_write('kundensitzungen', ksess_prune($r)); }
        });
    }
    $_SESSION['kseen'] = time();
    return $KUNDE = $c;
}
function require_customer_csrf(): void
{
    $tok = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
    if (!is_string($tok) || !hash_equals((string)($_SESSION['kcsrf'] ?? ''), $tok)) fail('Sicherheitsprüfung fehlgeschlagen – bitte Seite neu laden.', 403);
}
function kunde_payload(array $c): array
{
    $names = [];
    foreach (customer_offers($c) as $id) { $d = offer_def($id); if ($d) $names[] = ['id' => $id, 'name' => $d['name']]; }
    foreach (einzel_fuer_kunde($c) as $e) $names[] = ['id' => 'e-' . $e['id'], 'name' => einzel_titel($e), 'einzel' => true, 'gueltigBis' => $e['gueltigBis'] ?? null];
    return ['firma' => $c['firma'], 'ansprechpartner' => $c['ansprechpartner'] ?? '', 'username' => $c['login']['username'],
            'mustChange' => !empty($c['login']['mustChange']), 'mustChangeGrund' => !empty($c['login']['mustChange']) ? (string)($c['login']['mustChangeGrund'] ?? '') : '', 'angebote' => $names];
}
const CUSTOMER_FIELDS = ['nr' => 30, 'gruppe' => 10, 'vertreter' => 10, 'vertreter2' => 10, 'firma' => 120, 'ansprechpartner' => 120, 'strasse' => 120, 'plz' => 10, 'ort' => 80, 'land' => 60, 'email' => 160, 'telefon' => 40, 'notiz' => 500];
const CUSTOMER_LABELS = ['mailAngebot' => 'Wochenangebot per E-Mail', 'nr' => 'Kundennummer', 'gruppe' => 'Kundengruppe', 'vertreter' => 'Vertreter', 'vertreter2' => 'Vertreter 2', 'firma' => 'Firma', 'ansprechpartner' => 'Ansprechpartner', 'strasse' => 'Straße', 'plz' => 'PLZ', 'ort' => 'Ort',
                         'land' => 'Land', 'email' => 'E-Mail', 'telefon' => 'Telefon', 'notiz' => 'Notiz', 'angebote' => 'Angebote', 'active' => 'Kunde aktiv'];

/* ---------------- Listen der Stammdaten (Kundengruppen, VK-Gruppen, Vertreter) ----------------
   Dokument je Liste (Name wie die Liste): { rev, groups: [{ nr, name, …Felder der Liste }], updatedAt, updatedBy }.
   Kunden verweisen über „gruppe“ auf eine Kundengruppe und über „vertreter“/„vertreter2“ auf Vertreter,
   Artikel (Stammdaten) über „vkGruppe“ auf eine VK-Gruppe. Felder: Name => [Länge, Pflicht]. */
const GRUPPEN_MAX = 2000;
const GRUPPEN_FELDER = ['name' => [120, true], 'klasse' => [20, false], 'kategorie' => [20, false]];
const GRUPPEN_LISTEN = [
    'kundengruppen' => ['eine' => 'Kundengruppe', 'viele' => 'Kundengruppen', 'felder' => GRUPPEN_FELDER],
    'vkgruppen' => ['eine' => 'VK-Gruppe', 'viele' => 'VK-Gruppen', 'felder' => GRUPPEN_FELDER],
    'vertreter' => ['eine' => 'Vertreter', 'viele' => 'Vertreter', 'felder' => ['name' => [120, true], 'kurz' => [40, false], 'telefon' => [40, false], 'plz' => [10, false], 'ort' => [80, false], 'land' => [60, false]]],
];
function gruppen_load(string $liste): array
{
    $d = store_read($liste);
    return ['rev' => (int)($d['rev'] ?? 0), 'groups' => is_array($d['groups'] ?? null) ? $d['groups'] : [], 'updatedAt' => $d['updatedAt'] ?? null, 'updatedBy' => (string)($d['updatedBy'] ?? '')];
}
/* $alt: gespeicherte Einträge nach Nummer – Felder, die ein Eintrag der Anfrage nicht enthält, und Felder, die dieser
   Stand nicht kennt (neuere Fassung), bleiben dann erhalten (GR-006). Ein absichtlich geleertes Feld kommt als "". */
function gruppen_clean(string $liste, $list, array $alt = []): array
{
    $L = GRUPPEN_LISTEN[$liste];
    if (!is_array($list)) throw new InvalidArgumentException("{$L['viele']} fehlen.");
    if (count($list) > GRUPPEN_MAX) throw new InvalidArgumentException("Zu viele {$L['viele']} (höchstens " . GRUPPEN_MAX . ').');
    $out = []; $seen = [];
    foreach ($list as $g) {
        if (!is_array($g)) continue;
        $nr = s($g['nr'] ?? null, 10, false);
        if ($nr === null || !preg_match('/^[0-9A-Za-z._-]{1,10}$/', $nr)) throw new InvalidArgumentException("Jede {$L['eine']} braucht eine Nummer (bis 10 Zeichen, Buchstaben/Ziffern).");
        $key = ctype_digit($nr) ? (ltrim($nr, '0') === '' ? '0' : ltrim($nr, '0')) : strtoupper($nr);
        if (isset($seen[$key])) throw new InvalidArgumentException("{$L['eine']} $nr kommt doppelt vor.");
        $seen[$key] = true;
        $row = ['nr' => $nr];
        $vorher = is_array($alt[$nr] ?? null) ? $alt[$nr] : [];
        foreach ($L['felder'] as $f => [$max, $pflicht]) {
            $v = array_key_exists($f, $g) || !array_key_exists($f, $vorher) ? (s($g[$f] ?? '', $max) ?? '') : (string)$vorher[$f];
            if ($pflicht && $v === '') throw new InvalidArgumentException("{$L['eine']} $nr: " . ($f === 'name' ? ($liste === 'vertreter' ? 'Name' : 'Bezeichnung') : $f) . ' fehlt.');
            $row[$f] = $v;
        }
        $out[] = $row + $vorher;
    }
    usort($out, function ($a, $b) { return strnatcasecmp($a['nr'], $b['nr']); });
    return $out;
}
function kundengruppen_load(): array { return gruppen_load('kundengruppen'); }
function kundengruppen_clean($list): array { return gruppen_clean('kundengruppen', $list); }
function vertreter_load(): array { return gruppen_load('vertreter'); }
