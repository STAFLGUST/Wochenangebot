<?php
declare(strict_types=1);
/* Mitarbeiter-Sitzung, Rollen, Passwortbestätigung, CSRF */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Sitzung ---------------- */

/* App-Zugriff (docs/app-api.md): Die App sendet „X-WA-Client: app“ und trägt die Sitzungskennung in der Kopfzeile
   „X-WA-Sitzung“ statt in einem Cookie; jede Antwort nennt die aktuelle Kennung (nach der Anmeldung neu vergeben,
   nach dem Abmelden leer). Es sind dieselben Sitzungen wie im Browser: gleiche Anmeldung, Zwei-Faktor, Sperren,
   CSRF-Prüfung, Abmeldung nach Inaktivität und Widerruf durch Administratoren – kein zusätzlicher Zugangsschlüssel.
   Fremde Webseiten können diese Kopfzeilen nicht setzen (keine CORS-Freigabe). */
function app_client(): bool { return strtolower(trim((string)($_SERVER['HTTP_X_WA_CLIENT'] ?? ''))) === 'app'; }
$APP_SITZUNG = false;
function app_session_header(): void
{
    global $APP_SITZUNG;
    if (!$APP_SITZUNG || headers_sent()) return;
    header('X-WA-Sitzung: ' . (session_status() === PHP_SESSION_ACTIVE ? session_id() : ''));
    header('Cache-Control: no-store');
}

/* Name des Sitzungs-Cookies (Mitarbeiter und Kunden). Über HTTPS mit Präfix „__Host-“: der Browser nimmt das Cookie
   nur vom Server selbst an (Secure, Pfad /, ohne Domain) – eine Nachbar-Subdomain wie test.<Domain> kann es weder setzen
   noch überschreiben (GR-108, ADR-003 Befund B-1). Über einfaches HTTP (nur lokale Tests) ohne Präfix, weil Browser
   „__Host-“ dort verwerfen. Das frühere Cookie ohne Präfix wird über HTTPS nicht mehr gelesen, sondern gelöscht. */
const SITZUNG_COOKIE = 'WA_ADMIN';
function sitzung_cookie_name(): string { return (is_https() ? '__Host-' : '') . SITZUNG_COOKIE; }

function start_session(): void
{
    global $CFG, $APP_SITZUNG;
    if (session_status() === PHP_SESSION_ACTIVE) return;
    $https = is_https();
    ini_set('session.use_strict_mode', '1');
    ini_set('session.use_only_cookies', '1');
    if (app_client()) {
        // Kennung nur aus der Kopfzeile; unbekannte Kennungen verwirft PHP (strict mode) und vergibt eine neue
        ini_set('session.use_cookies', '0');
        $sid = (string)($_SERVER['HTTP_X_WA_SITZUNG'] ?? '');
        if (preg_match('/^[A-Za-z0-9,-]{22,256}$/D', $sid)) session_id($sid);
        $APP_SITZUNG = true;
    }
    session_name(sitzung_cookie_name());
    session_set_cookie_params(['lifetime' => 0, 'path' => '/', 'secure' => $https, 'httponly' => true, 'samesite' => 'Strict']);
    // Altes Cookie ohne Präfix (vor dem Umstieg gesetzt oder von einer Nachbar-Subdomain untergeschoben) nie übernehmen,
    // sondern im Browser löschen. Ein Cookie einer Nachbar-Subdomain mit Domain-Angabe lässt sich so nicht löschen – es
    // wird aber ohnehin nicht gelesen.
    if ($https && !$APP_SITZUNG && isset($_COOKIE[SITZUNG_COOKIE]) && !headers_sent()) {
        setcookie(SITZUNG_COOKIE, '', ['expires' => 1, 'path' => '/', 'secure' => true, 'httponly' => true, 'samesite' => 'Strict']);
    }
    session_start();
    $max = (int)sec()['idleMinutes'] * 60;
    if (!empty($_SESSION['uid']) && (time() - (int)($_SESSION['seen'] ?? 0)) > $max) { $_SESSION = []; session_regenerate_id(true); }
    if (!empty($_SESSION['uid']) && !bg_request()) $_SESSION['seen'] = time();
}
/* Automatische Abfragen im Hintergrund (Abgleich mit anderen Bearbeitern) zählen nicht als Aktivität –
   die Abmeldung nach Inaktivität bleibt wirksam. */
function bg_request(): bool
{
    global $action;
    return ($action ?? '') === 'draft_ping' || (($action ?? '') === 'draft' && ($_GET['bg'] ?? '') === '1');
}
/* Angemeldeter Nutzer – Rolle und Status werden bei jeder Anfrage frisch gelesen */
$ME = null;
function current_user(): ?array
{
    global $ME;
    if ($ME !== null) return $ME;
    if (oidc_modus()) return $ME = oidc_nutzer();   // Keycloak-Host: Identität vom Webserver (lib/oidc.php, GR-110)
    start_session();
    if (empty($_SESSION['uid'])) return null;
    $users = users_load();
    $i = user_find($users, (string)$_SESSION['uid']);
    if ($i === null || !$users[$i]['active'] || (int)$users[$i]['sv'] !== (int)($_SESSION['sv'] ?? -1)) { $_SESSION = []; return null; }
    // Sitzung muss im Register stehen (Administrator kann sie beenden)
    $sid = (string)($_SESSION['sid'] ?? '');
    $reg = store_read('sitzungen') ?? [];
    if ($sid === '' || !isset($reg[$sid]) || $reg[$sid]['uid'] !== $users[$i]['id']) { $_SESSION = []; return null; }
    if (!bg_request() && ((int)$reg[$sid]['seen'] < time() - 60 || $reg[$sid]['ip'] !== client_ip())) {
        with_lock('sitzungen', function () use ($sid) {
            $l = store_read('sitzungen') ?? [];
            if (isset($l[$sid])) { $l[$sid]['seen'] = time(); $l[$sid]['ip'] = client_ip(); store_write('sitzungen', sess_prune($l)); }
        });
    }
    return $ME = $users[$i];
}
function require_auth(bool $write = false, string $role = 'viewer'): array
{
    $u = current_user();
    if (!$u) fail('Bitte erneut anmelden.', 401);
    header('Cache-Control: private, no-store');   // Daten nach Anmeldung nie im Browser-Cache ablegen (gemeinsam genutzte Rechner)
    if ($write) {
        $tok = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
        if (!is_string($tok) || !hash_equals((string)($_SESSION['csrf'] ?? ''), $tok)) fail('Sicherheitsprüfung fehlgeschlagen – bitte Seite neu laden.', 403);
    }
    // Passwort und zweiter Faktor prüft auf Keycloak-Hosts Keycloak (Pflicht im Realm), nicht diese Anwendung
    if (!oidc_modus() && !empty($u['mustChange'])) fail('Bitte zuerst ein neues Passwort festlegen.', 403);
    if (!oidc_modus() && twofa_required($u) && !has_second_factor($u)) fail('Bitte zuerst die Zwei-Faktor-Anmeldung einrichten.', 403);
    if (ROLES[$u['role']] < ROLES[$role]) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
    return $u;
}
function sign_in(array $u): string
{
    global $ME;
    session_regenerate_id(true);
    $_SESSION['uid'] = $u['id'];
    $_SESSION['sv'] = (int)$u['sv'];
    $_SESSION['seen'] = time();
    $_SESSION['authAt'] = time();   // Zeitpunkt der Passwort-Anmeldung (z. B. für die Ersteinrichtung der Zwei-Faktor-Anmeldung)
    $_SESSION['csrf'] = bin2hex(random_bytes(32));
    unset($_SESSION['pend'], $_SESSION['totpPending'], $_SESSION['pkReg'], $_SESSION['pkAuth']);
    mark_admin_confirmed($u);
    sess_register($u);
    $ME = $u;
    return $_SESSION['csrf'];
}
function me_payload(array $u): array
{
    if (oidc_modus()) {
        // Zentrale Anmeldung: Passwort, zweiter Faktor und Passkeys verwaltet Keycloak
        return ['id' => $u['id'], 'username' => $u['username'], 'name' => $u['name'], 'role' => $u['role'], 'mustChange' => false, 'mustChangeGrund' => '',
                'twofa' => true, 'passkeys' => 0, 'needTwofa' => false, 'twofaRequired' => false, 'zentral' => true,
                'perms' => function_exists('user_perms') ? user_perms($u) : []];
    }
    return ['id' => $u['id'], 'username' => $u['username'], 'name' => $u['name'], 'role' => $u['role'], 'mustChange' => (bool)($u['mustChange'] ?? false),
            'mustChangeGrund' => !empty($u['mustChange']) ? (string)($u['mustChangeGrund'] ?? '') : '',
            'twofa' => !empty($u['totp']), 'passkeys' => count((array)($u['passkeys'] ?? [])),
            'needTwofa' => twofa_required($u) && !has_second_factor($u), 'twofaRequired' => twofa_required($u),
            'perms' => function_exists('user_perms') ? user_perms($u) : []];
}
/* Nutzer innerhalb der Sperre ändern und speichern */
function user_update(string $id, callable $fn): ?array
{
    return with_lock('nutzer', function () use ($id, $fn) {
        $users = users_load();
        $i = user_find($users, $id);
        if ($i === null) return null;
        $fn($users[$i]);
        users_save($users);
        return $users[$i];
    });
}
/* Kurze, sitzungsgebundene Freigabe sensibler Verwaltungsaktionen. */
// Gültigkeit einer Passwortbestätigung: bestaetigung_sekunden() (Sicherheit → Passwortbestätigung, Standard 5 Minuten)
const CONFIRM_MAX_FAILURES = 5;
const CONFIRM_LOCK_SECONDS = 600;
function mark_admin_confirmed(array $u): void
{
    $_SESSION['adminConfirmedAt'] = time();
    $_SESSION['adminConfirmedSv'] = (int)$u['sv'];
}
function confirmation_locked(array $u): void
{
    $remaining = (int)($u['confirmUntil'] ?? 0) - time();
    if ($remaining > 0) {
        header('Retry-After: ' . $remaining);
        respond(['ok' => false, 'code' => 'confirmation_locked', 'error' => 'Zu viele falsche Passwortbestätigungen. Bitte in ' . (int)ceil($remaining / 60) . ' Minuten erneut versuchen.'], 429);
    }
}
/* $key: Aktion im Katalog BESTAETIGUNG (lib/sicherheit.php) – ist die Bestätigung abgeschaltet, genügt die Administrator-Anmeldung */
function require_admin_confirmation(string $key = ''): array
{
    if ($key !== '' && !bestaetigung_noetig($key)) return require_auth(true, 'admin');
    $u = require_auth(true, 'admin');
    confirmation_locked($u);
    $at = (int)($_SESSION['adminConfirmedAt'] ?? 0);
    if ($at <= time() && $at > time() - bestaetigung_sekunden() && (int)($_SESSION['adminConfirmedSv'] ?? -1) === (int)$u['sv']) return $u;
    respond(['ok' => false, 'code' => 'confirmation_required', 'error' => 'Bitte bestätigen Sie diese Verwaltungsaktion mit Ihrem aktuellen Passwort.'], 403);
}
/* Gemeinsame, kontoweite Bremse für Passwortbestätigungen; nie durch neue Sitzungen zurücksetzen. */
function confirm_password(array $me, string $password, int $invalidStatus = 422): array
{
    // Keycloak-Host: kein eigenes Passwort; Bestätigung durch erneute Anmeldung bei Keycloak (folgt, Roadmap 7b-2)
    if (oidc_modus()) respond(['ok' => false, 'code' => 'reauth_required', 'error' => 'Bitte melden Sie sich erneut an, um diese Aktion zu bestätigen.'], 403);
    $result = with_lock('nutzer', function () use ($me, $password) {
        $users = users_load();
        $i = user_find($users, $me['id']);
        if ($i === null || !$users[$i]['active'] || (int)$users[$i]['sv'] !== (int)$me['sv']) fail('Bitte erneut anmelden.', 401);
        $u = &$users[$i];
        confirmation_locked($u);
        $ok = password_verify($password, (string)$u['hash']);
        if ($ok) {
            unset($u['confirmFailures'], $u['confirmSeen'], $u['confirmUntil']);
        } else {
            $n = (int)($u['confirmSeen'] ?? 0) <= time() - CONFIRM_LOCK_SECONDS || !empty($u['confirmUntil']) ? 0 : (int)($u['confirmFailures'] ?? 0);
            $u['confirmFailures'] = $n + 1;
            $u['confirmSeen'] = time();
            $u['confirmUntil'] = $n + 1 >= CONFIRM_MAX_FAILURES ? time() + CONFIRM_LOCK_SECONDS : 0;
        }
        users_save($users);
        return [$ok, $u];
    });
    [$ok, $u] = $result;
    $GLOBALS['ME'] = $u;
    if (!$ok) {
        audit('reauth_fail', 'Passwortbestätigung fehlgeschlagen', [], $u);
        confirmation_locked($u);
        respond(['ok' => false, 'code' => 'confirmation_invalid', 'error' => 'Das aktuelle Passwort ist nicht korrekt.'], $invalidStatus);
    }
    return $u;
}
/* Nach Änderungen am zweiten Faktor nur die bestätigende Sitzung behalten. */
function keep_current_session(array $u): void
{
    $_SESSION['sv'] = (int)$u['sv'];
    // Eine vorhandene Freigabe nicht verlängern, nur an die neue Sitzungsversion binden.
    $_SESSION['adminConfirmedSv'] = (int)$u['sv'];
    unset($_SESSION['totpPending'], $_SESSION['pkReg']);
    $GLOBALS['ME'] = $u;
    $sid = (string)($_SESSION['sid'] ?? '');
    sess_remove(function ($k, $v) use ($u, $sid) { return $v['uid'] === $u['id'] && $k !== $sid; });
}
function require_csrf(): void
{
    $tok = $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
    if (!is_string($tok) || !hash_equals((string)($_SESSION['csrf'] ?? ''), $tok)) fail('Sicherheitsprüfung fehlgeschlagen – bitte Seite neu laden.', 403);
}
