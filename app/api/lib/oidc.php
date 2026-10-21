<?php
declare(strict_types=1);
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Mitarbeiteranmeldung über Keycloak (ADR-003, GR-110) – Roadmap 7b, vorerst nur in CI und lokaler Testumgebung.

   Das OpenID-Connect-Protokoll spricht nicht diese Anwendung, sondern das Apache-Modul mod_auth_openidc (OpenID-zertifiziert):
   Weiterleitung mit state, nonce und PKCE, Code-Tausch, Prüfung von Signatur, Aussteller, Zielgruppe und Ablauf, eigene
   hostgebundene Sitzung (__Host-Cookie), Abmelden und Back-Channel-Logout. Der Host ist nur dann ein Keycloak-Host, wenn
   der Webserver WA_OIDC=1 setzt (SetEnv im jeweiligen VirtualHost) – ohne diese Einstellung verhält sich alles wie bisher
   (angebot-stafl.de). Die geprüfte Identität kommt ausschließlich aus Umgebungsvariablen des Servers (REMOTE_USER,
   OIDC_CLAIM_*); Kopfzeilen eines Browsers landen in HTTP_* und werden nie gelesen.

   Rechte bleiben bei uns (GR-103): Keycloak sagt nur „wer“. Rolle, Rechte und „aktiv“ stehen im Nutzerkonto (Dokument
   nutzer) und werden bei jeder Anfrage frisch gelesen – ein gesperrtes Konto ist sofort ausgesperrt. Verknüpfung: Feld
   oidcSub im Nutzerkonto (Datenformat nur erweitert, GR-006). Bei der ersten Anmeldung wird ein noch nicht verknüpftes
   Konto mit gleichem Benutzernamen verknüpft; danach zählt nur noch die unveränderliche Kennung (sub) – ein später in
   Keycloak gleich benannter Nutzer erhält keinen Zugang zu einem bereits verknüpften Konto.

   Grenzen dieser Stufe: Eine hier beendete Sitzung (Verwaltung → Sitzungen) entsteht beim nächsten Aufruf neu, solange die
   Keycloak-Sitzung gilt – zentral beenden heißt in Keycloak abmelden bzw. das Konto sperren (wirkt sofort). Aktionen mit
   Passwortbestätigung gelten nur kurz nach der Anmeldung bei Keycloak (auth_time); erneute Anmeldung folgt (7b-2). */

function oidc_modus(): bool
{
    return oidc_einstellung('WA_OIDC') === '1';
}
/* Einstellung des Webservers (SetEnv) bzw. des Prozesses – nie aus Kopfzeilen (die heißen HTTP_…) */
function oidc_einstellung(string $name): string
{
    $v = $_SERVER[$name] ?? getenv($name);
    return is_string($v) ? $v : '';
}

/* Vom Webserver geprüfte Identität oder null */
function oidc_identitaet(): ?array
{
    if (!oidc_modus()) return null;
    $sub = (string)($_SERVER['OIDC_CLAIM_sub'] ?? '');
    $iss = (string)($_SERVER['OIDC_CLAIM_iss'] ?? '');
    $erwartet = oidc_einstellung('WA_OIDC_ISSUER');
    if ($sub === '' || $erwartet === '' || !hash_equals($erwartet, $iss)) return null;
    if ((string)($_SERVER['REMOTE_USER'] ?? '') !== $sub) return null;   // vom Modul gesetzt (OIDCRemoteUserClaim sub)
    return ['sub' => $sub, 'name' => (string)($_SERVER['OIDC_CLAIM_preferred_username'] ?? ''),
            'authTime' => (int)($_SERVER['OIDC_CLAIM_auth_time'] ?? 0), 'sid' => (string)($_SERVER['OIDC_CLAIM_sid'] ?? '')];
}

/* Mitarbeiterkonto zur Identität; ohne aktives Konto 403 (nicht 401 – sonst meldete der Browser sich endlos neu an) */
function oidc_konto(array $id): array
{
    $users = users_load();
    foreach ($users as $u) {
        if ((string)($u['oidcSub'] ?? '') === $id['sub']) return oidc_aktiv($u);
    }
    $kandidat = null;
    if ($id['name'] !== '') {
        foreach ($users as $u) {
            if (empty($u['oidcSub']) && strcasecmp((string)$u['username'], $id['name']) === 0) { $kandidat = $u; break; }
        }
    }
    if ($kandidat === null) {
        audit('oidc_ohne_konto', 'Anmeldung über Keycloak ohne Mitarbeiterkonto', ['benutzer' => substr($id['name'], 0, 60)]);
        fail('Für diese Anmeldung gibt es hier kein Mitarbeiterkonto. Bitte an einen Administrator wenden.', 403);
    }
    $neu = user_update($kandidat['id'], function (array &$u) use ($id) { if (empty($u['oidcSub'])) $u['oidcSub'] = $id['sub']; });
    if ($neu === null || (string)($neu['oidcSub'] ?? '') !== $id['sub']) fail('Für diese Anmeldung gibt es hier kein Mitarbeiterkonto.', 403);
    audit('oidc_verknuepft', 'Mitarbeiterkonto mit der zentralen Anmeldung verknüpft', [], $neu);
    return oidc_aktiv($neu);
}
function oidc_aktiv(array $u): array
{
    if (empty($u['active'])) fail('Ihr Mitarbeiterkonto ist gesperrt. Bitte an einen Administrator wenden.', 403);
    return $u;
}

/* Angemeldeter Mitarbeiter auf einem Keycloak-Host. Die PHP-Sitzung dieses Hosts (eigenes __Host-Cookie) trägt nur noch
   CSRF-Token und Sitzungsregister; sie folgt der Keycloak-Sitzung (sid) und wird bei jedem Wechsel neu vergeben. */
function oidc_nutzer(): ?array
{
    $id = oidc_identitaet();
    if ($id === null) return null;
    $u = oidc_konto($id);
    start_session();
    $passt = ($_SESSION['uid'] ?? '') === $u['id'] && ($_SESSION['oidcSub'] ?? '') === $id['sub'] && ($_SESSION['oidcSid'] ?? '') === $id['sid']
        && (int)($_SESSION['sv'] ?? -1) === (int)$u['sv'] && isset((store_read('sitzungen') ?? [])[(string)($_SESSION['sid'] ?? '')]);
    if (!$passt) {
        $_SESSION = [];
        sign_in($u);
        $_SESSION['oidcSub'] = $id['sub'];
        $_SESSION['oidcSid'] = $id['sid'];
        $_SESSION['authAt'] = $id['authTime'];
        // Bestätigung sensibler Aktionen = Zeitpunkt der letzten echten Anmeldung bei Keycloak, nicht der Sitzungsbeginn hier
        $_SESSION['adminConfirmedAt'] = $id['authTime'];
    } else {
        oidc_gesehen();
    }
    return $u;
}
/* Sitzungsregister aktuell halten (Anzeige „zuletzt aktiv“, Adresse) – wie bei der bisherigen Anmeldung */
function oidc_gesehen(): void
{
    $sid = (string)($_SESSION['sid'] ?? '');
    $reg = store_read('sitzungen') ?? [];
    if ($sid === '' || bg_request() || !isset($reg[$sid]) || ((int)$reg[$sid]['seen'] >= time() - 60 && $reg[$sid]['ip'] === client_ip())) return;
    with_lock('sitzungen', function () use ($sid) {
        $l = store_read('sitzungen') ?? [];
        if (isset($l[$sid])) { $l[$sid]['seen'] = time(); $l[$sid]['ip'] = client_ip(); store_write('sitzungen', sess_prune($l)); }
    });
}

/* Abmelden auf einem Keycloak-Host: eigene Sitzung beenden; der Browser meldet sich danach über das Modul bei Keycloak ab
   (beendet die zentrale Sitzung, Keycloak meldet alle anderen Anwendungen per Back-Channel-Logout ab). */
function oidc_abmelde_adresse(): string
{
    $ziel = 'https://' . strtolower((string)($_SERVER['HTTP_HOST'] ?? '')) . '/dashboard/abgemeldet.html';
    return '/oidc/callback?logout=' . rawurlencode($ziel);
}
