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
function customer_offers(array $c): array
{
    $known = array_merge([OFFER_STD], offer_ids());
    return array_values(array_filter($c['angebote'] ?? [], function ($o) use ($known) { return in_array($o, $known, true); }));
}
function customer_public(array $c): array
{
    $out = $c;
    $l = $c['login'] ?? null;
    $out['angebote'] = customer_offers($c);
    $out['login'] = $l ? ['username' => $l['username'], 'active' => !empty($l['active']), 'mustChange' => !empty($l['mustChange']),
                          'lastLogin' => $l['lastLogin'] ?? null, 'pwSet' => $l['pwSet'] ?? null,
                          'lockedUntil' => (int)($l['lockedUntil'] ?? 0) > time() ? (int)$l['lockedUntil'] : 0,
                          'hasPassword' => !empty($l['hash']),
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
    return ['firma' => $c['firma'], 'ansprechpartner' => $c['ansprechpartner'] ?? '', 'username' => $c['login']['username'],
            'mustChange' => !empty($c['login']['mustChange']), 'angebote' => $names];
}
const CUSTOMER_FIELDS = ['nr' => 30, 'gruppe' => 10, 'firma' => 120, 'ansprechpartner' => 120, 'strasse' => 120, 'plz' => 10, 'ort' => 80, 'land' => 60, 'email' => 160, 'telefon' => 40, 'notiz' => 500];
const CUSTOMER_LABELS = ['mailAngebot' => 'Wochenangebot per E-Mail', 'nr' => 'Kundennummer', 'gruppe' => 'Kundengruppe', 'firma' => 'Firma', 'ansprechpartner' => 'Ansprechpartner', 'strasse' => 'Straße', 'plz' => 'PLZ', 'ort' => 'Ort',
                         'land' => 'Land', 'email' => 'E-Mail', 'telefon' => 'Telefon', 'notiz' => 'Notiz', 'angebote' => 'Angebote', 'active' => 'Kunde aktiv'];

/* ---------------- Kundengruppen (Stammdaten → Kundengruppen) ----------------
   Dokument „kundengruppen“: { rev, groups: [{ nr, name, klasse, kategorie }], updatedAt, updatedBy }.
   Kunden verweisen über das Feld „gruppe“ auf die Nummer. */
const KUNDENGRUPPEN_MAX = 2000;
function kundengruppen_load(): array
{
    $d = store_read('kundengruppen');
    return ['rev' => (int)($d['rev'] ?? 0), 'groups' => is_array($d['groups'] ?? null) ? $d['groups'] : [], 'updatedAt' => $d['updatedAt'] ?? null, 'updatedBy' => (string)($d['updatedBy'] ?? '')];
}
function kundengruppen_clean($list): array
{
    if (!is_array($list)) throw new InvalidArgumentException('Kundengruppen fehlen.');
    if (count($list) > KUNDENGRUPPEN_MAX) throw new InvalidArgumentException('Zu viele Kundengruppen (höchstens ' . KUNDENGRUPPEN_MAX . ').');
    $out = []; $seen = [];
    foreach ($list as $g) {
        if (!is_array($g)) continue;
        $nr = s($g['nr'] ?? null, 10, false);
        if ($nr === null || !preg_match('/^[0-9A-Za-z._-]{1,10}$/', $nr)) throw new InvalidArgumentException('Jede Kundengruppe braucht eine Nummer (bis 10 Zeichen, Buchstaben/Ziffern).');
        $key = ctype_digit($nr) ? (ltrim($nr, '0') === '' ? '0' : ltrim($nr, '0')) : strtoupper($nr);
        if (isset($seen[$key])) throw new InvalidArgumentException("Die Kundengruppe $nr kommt doppelt vor.");
        $seen[$key] = true;
        $name = s($g['name'] ?? null, 120, false);
        if ($name === null || mb_strlen($name) < 1) throw new InvalidArgumentException("Kundengruppe $nr: Bezeichnung fehlt.");
        $out[] = ['nr' => $nr, 'name' => $name, 'klasse' => s($g['klasse'] ?? '', 20) ?? '', 'kategorie' => s($g['kategorie'] ?? '', 20) ?? ''];
    }
    usort($out, function ($a, $b) { return strnatcasecmp($a['nr'], $b['nr']); });
    return $out;
}
