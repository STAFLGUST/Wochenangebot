<?php
declare(strict_types=1);
/* Konten der zentralen Anmeldung (Keycloak, Realm „mitarbeiter“) aus der Verwaltung steuern – EIN Passwort für alles.
   Die Anwendung prüft weiterhin kein Passwort selbst (GR-110): sie bittet Keycloak über dessen Verwaltungsschnittstelle
   (Admin-REST-API), ein Passwort zu setzen, eine Sperre nach Fehlversuchen aufzuheben, den Link zum Passwort-Festlegen
   zu schicken oder ein fehlendes Konto anzulegen. Zugang: eigener vertraulicher Client „konten“ nur mit Service-Account
   und den Rollen view-users und manage-users (realm-management) – keine Realm-, Client- oder Rollenverwaltung, kein
   Anmelden als andere Person. Einrichtung: deploy/anmeldung/konten.sh realm-aktualisieren (Stand 8, Geheimnis
   OIDC_SECRET_KONTEN nur in .env). Fehlt es, melden alle Funktionen „nicht eingerichtet“ (keine Fehler 500).

   Zuordnung Mitarbeiterkonto → Keycloak-Konto: verknüpftes Konto (oidcSub = Keycloak-ID), sonst exakt gleicher
   Benutzername (wie bei der ersten Anmeldung, lib/oidc.php). Ein gleich benanntes Keycloak-Konto mit anderer ID als die
   Verknüpfung wird nie angefasst. Passwörter werden weder gespeichert noch protokolliert; ein vom Server erzeugtes
   Startpasswort geht genau einmal in der Antwort zurück. Zweiter Faktor und Passkeys bleiben beim Setzen erhalten. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const KONTEN_REALM = 'mitarbeiter';
const KONTEN_CLIENT = 'konten';
const KONTEN_LINK_STUNDEN = 72;   // wie konten.sh einladen
const KONTEN_EINRICHTEN = 'In der Serverkonsole: sh deploy/anmeldung/konten.sh realm-aktualisieren, danach docker compose up -d app.';

/* Fachlicher Fehler mit HTTP-Status für die Antwort (Meldung auf Deutsch, ohne Interna) */
final class KontenFehler extends RuntimeException
{
    public function __construct(string $meldung, public readonly int $status = 502) { parent::__construct($meldung); }
}

/* Einstellungen: Adresse von Keycloak im internen Netz (Betrieb http://keycloak:8080) und Geheimnis des Clients */
function konten_einstellung(): ?array
{
    $geheim = oidc_einstellung('OIDC_SECRET_KONTEN');
    if ($geheim === '' || $geheim === 'noch-nicht-eingerichtet') return null;
    $url = rtrim(oidc_einstellung('WA_KONTEN_URL') ?: 'http://keycloak:8080', '/');
    if (!preg_match('#^https?://[a-z0-9.-]+(:[0-9]+)?$#i', $url)) return null;
    return ['url' => $url, 'geheim' => $geheim, 'realm' => oidc_einstellung('WA_KONTEN_REALM') ?: KONTEN_REALM];
}
function konten_eingerichtet(): bool { return konten_einstellung() !== null; }

/* Eine Anfrage an Keycloak: [Status, JSON|null, Kopfzeilen]. Kurze Zeitlimits, keine Weiterleitungen. */
function konten_http(string $methode, string $url, ?string $inhalt = null, array $kopf = []): array
{
    $ctx = stream_context_create(['http' => ['method' => $methode, 'header' => implode("\r\n", $kopf), 'content' => $inhalt ?? '',
        'timeout' => 8, 'ignore_errors' => true, 'follow_location' => 0, 'max_redirects' => 0, 'user_agent' => 'STAFL-Plattform']]);
    $http_response_header = [];
    $roh = @file_get_contents($url, false, $ctx);
    if ($roh === false && !$http_response_header) throw new KontenFehler('Die zentrale Anmeldung ist gerade nicht erreichbar. Bitte später erneut versuchen.', 502);
    $status = preg_match('#^HTTP/\S+\s+(\d{3})#', (string)($http_response_header[0] ?? ''), $m) ? (int)$m[1] : 0;
    $json = $roh !== false && $roh !== '' ? json_decode($roh, true) : null;
    return [$status, is_array($json) ? $json : null, $http_response_header];
}

/* Zugangstoken des Clients „konten“ (client_credentials), nur im Speicher dieser Anfrage */
function konten_token(): string
{
    static $token = null;
    if ($token !== null) return $token;
    $e = konten_einstellung();
    if (!$e) throw new KontenFehler('Die Verwaltung der Anmeldekonten ist noch nicht eingerichtet. ' . KONTEN_EINRICHTEN, 503);
    [$st, $j] = konten_http('POST', $e['url'] . '/realms/' . rawurlencode($e['realm']) . '/protocol/openid-connect/token',
        http_build_query(['grant_type' => 'client_credentials', 'client_id' => KONTEN_CLIENT, 'client_secret' => $e['geheim']]),
        ['Content-Type: application/x-www-form-urlencoded']);
    if ($st === 400 || $st === 401) throw new KontenFehler('Die zentrale Anmeldung lehnt den Zugang der Anwendung ab (Client „konten“ fehlt oder Geheimnis passt nicht). ' . KONTEN_EINRICHTEN, 503);
    if ($st !== 200 || !is_string($j['access_token'] ?? null)) throw new KontenFehler('Die zentrale Anmeldung antwortet nicht wie erwartet. Bitte später erneut versuchen.', 502);
    return $token = $j['access_token'];
}

/* Aufruf der Verwaltungsschnittstelle des Realms: $pfad relativ zu /admin/realms/<realm>/ */
function konten_api(string $methode, string $pfad, $daten = null): array
{
    $e = konten_einstellung();
    if (!$e) throw new KontenFehler('Die Verwaltung der Anmeldekonten ist noch nicht eingerichtet. ' . KONTEN_EINRICHTEN, 503);
    $kopf = ['Authorization: Bearer ' . konten_token(), 'Accept: application/json'];
    if ($daten !== null) $kopf[] = 'Content-Type: application/json';
    [$st, $j, $h] = konten_http($methode, $e['url'] . '/admin/realms/' . rawurlencode($e['realm']) . '/' . $pfad,
        $daten === null ? null : json_encode($daten, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES), $kopf);
    if ($st === 401 || $st === 403) throw new KontenFehler('Der Anwendung fehlen Rechte in der zentralen Anmeldung (Rollen view-users/manage-users). ' . KONTEN_EINRICHTEN, 503);
    return [$st, $j, $h];
}

/* Keycloak-Konto zum Mitarbeiterkonto: [Konto|null, Hinweis]. Verknüpft (oidcSub) → nur diese ID; sonst exakter Name. */
function konten_finden(array $u): array
{
    $sub = (string)($u['oidcSub'] ?? '');
    if ($sub !== '') {
        if (!preg_match('/^[A-Za-z0-9-]{1,64}$/', $sub)) return [null, 'verknuepfung'];
        [$st, $j] = konten_api('GET', 'users/' . rawurlencode($sub));
        if ($st === 200 && is_array($j)) return [$j, ''];
        if ($st !== 404) throw new KontenFehler('Konto in der zentralen Anmeldung nicht lesbar (' . $st . ').', 502);
        return [null, 'verknuepfung_fehlt'];
    }
    [$st, $j] = konten_api('GET', 'users?exact=true&briefRepresentation=false&username=' . rawurlencode(strtolower((string)$u['username'])));
    if ($st !== 200 || !is_array($j)) throw new KontenFehler('Konten der zentralen Anmeldung nicht lesbar (' . $st . ').', 502);
    foreach ($j as $k) {
        if (!is_array($k) || strcasecmp((string)($k['username'] ?? ''), (string)$u['username']) !== 0) continue;
        // gehört schon zu einem anderen Mitarbeiterkonto (verknüpft) – nie anfassen
        foreach (users_load() as $x) if ((string)$x['id'] !== (string)$u['id'] && (string)($x['oidcSub'] ?? '') === (string)($k['id'] ?? '')) return [null, 'fremd'];
        return [$k, ''];
    }
    return [null, ''];
}

/* Zustand für die Verwaltung (nur lesen) */
function konten_status(array $u): array
{
    if (!konten_eingerichtet()) return ['eingerichtet' => false, 'hinweis' => 'Die Verwaltung der Anmeldekonten ist noch nicht eingerichtet. ' . KONTEN_EINRICHTEN];
    [$k, $grund] = konten_finden($u);
    if (!$k) {
        return ['eingerichtet' => true, 'vorhanden' => false, 'verknuepft' => (string)($u['oidcSub'] ?? '') !== '',
                'fremd' => $grund === 'fremd',
                'hinweis' => $grund === 'verknuepfung_fehlt' ? 'Das verknüpfte Konto gibt es in der zentralen Anmeldung nicht mehr. „Konto anlegen“ legt es neu an und verknüpft es.'
                    : ($grund === 'fremd' ? 'Das gleich benannte Konto in der zentralen Anmeldung ist mit einem anderen Mitarbeiter verknüpft – bitte in Keycloak prüfen.' : '')];
    }
    $id = (string)$k['id'];
    [, $cred] = konten_api('GET', 'users/' . rawurlencode($id) . '/credentials');
    [, $bf] = konten_api('GET', 'attack-detection/brute-force/users/' . rawurlencode($id));
    $arten = array_count_values(array_map(fn($c) => (string)($c['type'] ?? ''), is_array($cred) ? $cred : []));
    return ['eingerichtet' => true, 'vorhanden' => true, 'verknuepft' => (string)($u['oidcSub'] ?? '') === $id,
            'aktiv' => !empty($k['enabled']), 'gesperrt' => !empty($bf['disabled']), 'fehlversuche' => (int)($bf['numFailures'] ?? 0),
            'passwort' => !empty($arten['password']), 'einmalcode' => (int)($arten['otp'] ?? 0),
            'passkeys' => (int)($arten['webauthn'] ?? 0) + (int)($arten['webauthn-passwordless'] ?? 0),
            'passwortAendern' => in_array('UPDATE_PASSWORD', (array)($k['requiredActions'] ?? []), true),
            'email' => (string)($k['email'] ?? ''), 'erstellt' => isset($k['createdTimestamp']) ? gmdate('c', (int)($k['createdTimestamp'] / 1000)) : null];
}

/* Vorhandenes Konto oder Fehler (für schreibende Funktionen) */
function konten_pflicht(array $u): array
{
    [$k, $grund] = konten_finden($u);
    if (!$k && $grund === 'fremd') throw new KontenFehler('Das gleich benannte Konto in der zentralen Anmeldung ist mit einem anderen Mitarbeiter verknüpft – bitte in Keycloak prüfen.', 409);
    if (!$k) throw new KontenFehler($grund === 'verknuepfung_fehlt' ? 'Das verknüpfte Konto gibt es in der zentralen Anmeldung nicht mehr – bitte „Konto anlegen“.'
        : 'Für „' . $u['username'] . '“ gibt es noch kein Konto in der zentralen Anmeldung – bitte „Konto anlegen“.', 404);
    return $k;
}

/* Richtlinienfehler von Keycloak (Passwort) auf Deutsch */
function konten_passwort_meldung(?array $j): string
{
    $code = (string)($j['error'] ?? '') . ' ' . (string)($j['error_description'] ?? $j['errorMessage'] ?? '');
    $t = [
        'MinLength' => 'Das Passwort ist zu kurz (mindestens 12 Zeichen).', 'History' => 'Dieses Passwort wurde kürzlich schon verwendet – bitte ein anderes wählen.',
        'NotUsername' => 'Das Passwort darf nicht der Benutzername sein.', 'NotEmail' => 'Das Passwort darf nicht die E-Mail-Adresse sein.',
        'Digits' => 'Das Passwort braucht mehr Ziffern.', 'UpperCase' => 'Das Passwort braucht mehr Großbuchstaben.', 'LowerCase' => 'Das Passwort braucht mehr Kleinbuchstaben.',
        'SpecialChars' => 'Das Passwort braucht mehr Sonderzeichen.', 'Blacklisted' => 'Dieses Passwort ist zu bekannt – bitte ein anderes wählen.', 'MaxLength' => 'Das Passwort ist zu lang.',
    ];
    foreach ($t as $k => $text) if (stripos($code, $k) !== false) return $text;
    return 'Die zentrale Anmeldung hat das Passwort abgelehnt (Passwortregeln: mindestens 12 Zeichen, nicht Benutzername oder E-Mail).';
}

/* Gut vorlesbares Startpasswort wie konten.sh (16 Zeichen in Vierergruppen, ohne 0/O/1/l/I) */
function konten_startpasswort(): string
{
    $z = 'ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789';
    $s = '';
    for ($i = 0; $i < 16; $i++) $s .= $z[random_int(0, strlen($z) - 1)];
    return implode('-', str_split($s, 4));
}

/* Passwort setzen; $temporaer = bei der nächsten Anmeldung ändern. Zweiter Faktor und Passkeys bleiben. */
function konten_passwort(array $u, string $passwort, bool $temporaer): void
{
    $k = konten_pflicht($u);
    [$st, $j] = konten_api('PUT', 'users/' . rawurlencode((string)$k['id']) . '/reset-password', ['type' => 'password', 'value' => $passwort, 'temporary' => $temporaer]);
    if ($st === 400) throw new KontenFehler(konten_passwort_meldung($j), 422);
    if ($st !== 204 && $st !== 200) throw new KontenFehler('Das Passwort konnte nicht gesetzt werden (' . $st . ').', 502);
}

/* Sperre nach Fehlversuchen aufheben (und ein in Keycloak gesperrtes Konto wieder aktivieren, wie konten.sh entsperren) */
function konten_entsperren(array $u): void
{
    $k = konten_pflicht($u);
    $id = rawurlencode((string)$k['id']);
    if (empty($k['enabled'])) {
        [$st] = konten_api('PUT', 'users/' . $id, ['enabled' => true]);
        if ($st !== 204 && $st !== 200) throw new KontenFehler('Konto konnte nicht aktiviert werden (' . $st . ').', 502);
    }
    [$st] = konten_api('DELETE', 'attack-detection/brute-force/users/' . $id);
    if ($st !== 204 && $st !== 200) throw new KontenFehler('Die Sperre konnte nicht aufgehoben werden (' . $st . ').', 502);
}

/* Mail mit Link zum Passwort-Festlegen (72 Stunden, nur „Passwort aktualisieren“) */
function konten_link(array $u): string
{
    $k = konten_pflicht($u);
    if ((string)($k['email'] ?? '') === '') throw new KontenFehler('Das Konto in der zentralen Anmeldung hat keine E-Mail-Adresse – bitte im Mitarbeiter eine E-Mail eintragen und „Konto anlegen“ bzw. die Adresse in Keycloak ergänzen.', 422);
    [$st] = konten_api('PUT', 'users/' . rawurlencode((string)$k['id']) . '/execute-actions-email?lifespan=' . (KONTEN_LINK_STUNDEN * 3600) . '&client_id=dashboard', ['UPDATE_PASSWORD']);
    if ($st === 500 || $st === 400) throw new KontenFehler('Die zentrale Anmeldung konnte die Mail nicht senden – ist der Mailversand eingerichtet? In der Serverkonsole: sh deploy/anmeldung/konten.sh mail-einrichten', 502);
    if ($st !== 204 && $st !== 200) throw new KontenFehler('Die Mail konnte nicht ausgelöst werden (' . $st . ').', 502);
    return (string)$k['email'];
}

/* Fehlendes Konto anlegen (Benutzername, Name, E-Mail aus dem Mitarbeiterkonto) und verknüpfen. Rückgabe: Keycloak-ID. */
function konten_anlegen(array $u): string
{
    [$k, $grund] = konten_finden($u);
    if ($k) throw new KontenFehler('Für „' . $u['username'] . '“ gibt es bereits ein Konto in der zentralen Anmeldung.', 409);
    if ($grund === 'fremd') throw new KontenFehler('Das gleich benannte Konto in der zentralen Anmeldung ist mit einem anderen Mitarbeiter verknüpft.', 409);
    $name = strtolower((string)$u['username']);
    if ($grund === 'verknuepfung_fehlt' || $grund === 'verknuepfung') {
        // Verknüpfung zeigt ins Leere: gleich benanntes, fremdes Konto nie übernehmen
        [$st, $j] = konten_api('GET', 'users?exact=true&username=' . rawurlencode($name));
        if ($st === 200 && is_array($j) && $j) throw new KontenFehler('In der zentralen Anmeldung gibt es ein anderes Konto „' . $name . '“, das nicht mit diesem Mitarbeiter verknüpft ist. Bitte in Keycloak prüfen.', 409);
    }
    [$vor, $nach] = [(string)($u['vorname'] ?? ''), (string)($u['nachname'] ?? '')];
    if ($vor === '' && $nach === '') { $t = preg_split('/\s+/u', trim((string)$u['name'])) ?: []; $nach = count($t) > 1 ? (string)array_pop($t) : ''; $vor = implode(' ', $t); }
    $neu = ['username' => $name, 'enabled' => true, 'firstName' => $vor, 'lastName' => $nach, 'requiredActions' => ['UPDATE_PASSWORD']];
    $mail = (string)($u['email'] ?? '');
    if ($mail !== '') { $neu['email'] = $mail; $neu['emailVerified'] = true; }
    [$st, $j, $h] = konten_api('POST', 'users', $neu);
    if ($st === 409) throw new KontenFehler('Benutzername oder E-Mail-Adresse ist in der zentralen Anmeldung schon vergeben.', 409);
    if ($st !== 201) throw new KontenFehler('Das Konto konnte nicht angelegt werden (' . $st . ').', 502);
    $id = '';
    foreach ($h as $z) if (preg_match('#^Location:\s*\S*/users/([A-Za-z0-9-]+)\s*$#i', $z, $m)) $id = $m[1];
    if ($id === '') { [$k] = konten_finden(['username' => $name, 'oidcSub' => '']); $id = (string)($k['id'] ?? ''); }
    if ($id === '') throw new KontenFehler('Das Konto wurde angelegt, ist aber nicht auffindbar. Bitte neu laden.', 502);
    // Verknüpfen: ab jetzt zählt nur noch diese ID (wie nach der ersten Anmeldung, lib/oidc.php)
    user_update((string)$u['id'], function (array &$x) use ($id) { $x['oidcSub'] = $id; });
    return $id;
}
