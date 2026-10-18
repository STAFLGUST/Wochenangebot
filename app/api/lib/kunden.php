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
const CUSTOMER_FIELDS = ['nr' => 30, 'firma' => 120, 'ansprechpartner' => 120, 'strasse' => 120, 'plz' => 10, 'ort' => 80, 'land' => 60, 'email' => 160, 'telefon' => 40, 'notiz' => 500];
const CUSTOMER_LABELS = ['mailAngebot' => 'Wochenangebot per E-Mail', 'nr' => 'Kundennummer', 'firma' => 'Firma', 'ansprechpartner' => 'Ansprechpartner', 'strasse' => 'Straße', 'plz' => 'PLZ', 'ort' => 'Ort',
                         'land' => 'Land', 'email' => 'E-Mail', 'telefon' => 'Telefon', 'notiz' => 'Notiz', 'angebote' => 'Angebote', 'active' => 'Kunde aktiv'];
