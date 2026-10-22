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
   Keycloak-Sitzung gilt – zentral beenden heißt in Keycloak abmelden bzw. das Konto sperren (wirkt sofort). Sensible
   Aktionen (sonst Passwortbestätigung) verlangen eine erneute Anmeldung bei Keycloak (max_age=0, oidc_neu_anmelden); als
   Bestätigung zählt der Anmeldezeitpunkt (auth_time) innerhalb der eingestellten Bestätigungsdauer. */

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
            'authTime' => (int)($_SERVER['OIDC_CLAIM_auth_time'] ?? 0), 'sid' => (string)($_SERVER['OIDC_CLAIM_sid'] ?? ''),
            'acr' => (string)($_SERVER['OIDC_CLAIM_acr'] ?? ''),
            // Anmeldemethoden (Keycloak-Mapper „amr“: pwd, otp, hwk); das Modul reicht Listen kommagetrennt weiter
            'amr' => array_values(array_filter(array_map('trim', explode(',', (string)($_SERVER['OIDC_CLAIM_amr'] ?? '')))))];
}

/* Anmeldestärke: Den zweiten Faktor verlangen wir nur von Konten, für die er vorgeschrieben ist: Administratoren immer,
   übrige nach Sicherheitseinstellung bzw. einzeln verpflichtet (twofa_required). Nachweis: Keycloak meldet die
   Stufe „mfa“ (acr, nach erzwungener zweiter Stufe) oder Einmalcode/Passkey unter den Anmeldemethoden (amr). Wer den
   zweiten Faktor freiwillig eingerichtet hat, wird bei Keycloak ohnehin danach gefragt. */
function oidc_zweiter_faktor(array $id): bool
{
    $stufe = oidc_einstellung('WA_OIDC_ACR');
    return hash_equals($stufe !== '' ? $stufe : 'mfa', $id['acr']) || array_intersect($id['amr'], ['otp', 'hwk', 'swk']) !== [];
}
function oidc_stufe_ok(array $id, array $u): bool
{
    // Administratoren immer (Entscheidung Inhaber 22.10.2026), übrige nach Sicherheitseinstellung bzw. Einzelpflicht
    return !(($u['role'] ?? '') === 'admin' || twofa_required($u)) || oidc_zweiter_faktor($id);
}
/* Anmeldung mit zweitem Faktor bei Keycloak anfordern (zweite Stufe; fehlt er, richtet der Mitarbeiter ihn dort ein) */
function oidc_stufe_adresse(): string
{
    return '/oidc/callback?' . http_build_query(['iss' => oidc_einstellung('WA_OIDC_ISSUER'), 'auth_request_params' => 'acr_values=mfa'], '', '&', PHP_QUERY_RFC3986)
        . '&target_link_uri=';
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
    if (!oidc_stufe_ok($id, $u)) {
        start_session();
        // Schutz vor einer Endlosschleife, falls Keycloak die zweite Stufe nicht bestätigt (Einstellung falsch):
        // höchstens drei Anforderungen in zehn Minuten, danach Hinweis statt erneuter Weiterleitung
        $a = $_SESSION['oidcStufeAngefordert'] ?? [];
        $a = array_values(array_filter(is_array($a) ? $a : [], fn($t) => (int)$t > time() - 600));
        if (count($a) >= 3) {
            audit('oidc_stufe', 'Zweite Stufe bei Keycloak mehrfach angefordert, aber nicht bestätigt', ['stufe' => substr($id['acr'], 0, 20)], $u);
            fail('Die Anmeldung mit zweitem Faktor wurde nicht bestätigt. Bitte erneut anmelden oder an einen Administrator wenden.', 403);
        }
        $a[] = time();
        $_SESSION['oidcStufeAngefordert'] = $a;
        audit('oidc_stufe', 'Anmeldung über Keycloak ohne vorgeschriebenen zweiten Faktor – zweite Stufe angefordert', ['stufe' => substr($id['acr'], 0, 20)], $u);
        respond(['ok' => false, 'code' => 'reauth_required', 'anmelden' => oidc_stufe_adresse(),
                 'error' => 'Für Ihr Konto ist die Anmeldung mit zweitem Faktor (Einmalcode oder Passkey) vorgeschrieben.'], 403);
        exit;
    }
    start_session();
    unset($_SESSION['oidcStufeAngefordert']);
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
        // Erneute Anmeldung bei Keycloak (oidc_neu_anmelden): neuer Anmeldezeitpunkt bestätigt sensible Aktionen
        if ($id['authTime'] > (int)($_SESSION['authAt'] ?? 0)) {
            $_SESSION['authAt'] = $id['authTime'];
            $_SESSION['adminConfirmedAt'] = $id['authTime'];
            $_SESSION['adminConfirmedSv'] = (int)$u['sv'];
            audit('reauth', 'Erneut bei Keycloak angemeldet (Bestätigung)', [], $u);
        }
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

/* Erneute Anmeldung bei Keycloak statt eigener Passwortabfrage (ADR-003: max_age=0). Das Modul startet dafür eine neue
   Anmeldung (Drittanbieter-Einstieg über die eigene Rücksprungadresse); Ziel ist nur der eigene Host (OIDCRedirectURLsAllowed).
   Die Oberfläche hängt die aktuelle Seite als target_link_uri an. */
function oidc_neu_anmelden_adresse(): string
{
    return '/oidc/callback?' . http_build_query(['iss' => oidc_einstellung('WA_OIDC_ISSUER'), 'auth_request_params' => 'max_age=0'], '', '&', PHP_QUERY_RFC3986)
        . '&target_link_uri=';
}
function oidc_neu_anmelden(): never
{
    respond(['ok' => false, 'code' => 'reauth_required', 'anmelden' => oidc_neu_anmelden_adresse(),
             'error' => 'Bitte melden Sie sich zur Bestätigung erneut an.'], 403);
    exit;
}
