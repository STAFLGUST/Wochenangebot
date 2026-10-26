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

   Ablauf und Beenden: Eine hier beendete Sitzung (Verwaltung → Sitzungen) und eine wegen Inaktivität abgelaufene Sitzung
   (Sicherheitseinstellung) entstehen nicht stillschweigend neu, sondern verlangen eine erneute Anmeldung bei Keycloak
   (oidc_ende_zeit, seit 26.10.2026). Sofort überall aussperren: Konto sperren (Anwendung oder Keycloak). Sensible
   Aktionen (sonst Passwortbestätigung) verlangen eine erneute Anmeldung bei Keycloak (max_age=0, oidc_neu_anmelden); als
   Bestätigung zählt der Anmeldezeitpunkt (auth_time) innerhalb der eingestellten Bestätigungsdauer. */

function oidc_modus(): bool
{
    return oidc_einstellung('WA_OIDC') === '1';
}
/* Bisheriger Eingabebereich mit eigener Anmeldung (angebot-stafl.de/admin/) stillgelegt (Entscheidung Inhaber 23.10.2026):
   WA_EIGENE_ANMELDUNG=aus (Betrieb: docker-compose.anmeldung.yml). Mitarbeiter arbeiten nur noch über die zentrale
   Anmeldung; Kundenseite und Kundenanmeldung bleiben unverändert. Notzugang (Keycloak gestört): deploy/notzugang.sh an */
function alter_zugang_aus(): bool
{
    return oidc_einstellung('WA_EIGENE_ANMELDUNG') === 'aus';
}
/* Gilt für diese Anfrage: Host ohne zentrale Anmeldung und alter Zugang aus */
function eigene_anmeldung_stillgelegt(): bool
{
    return !oidc_modus() && alter_zugang_aus();
}
/* Neuer Eingabebereich (Hinweis, Weiterleitung, Verweise in Mails) – nur https-Adressen */
function eingabe_adresse(): string
{
    $a = oidc_einstellung('WA_EINGABE_ADRESSE');
    return preg_match('#^https://[a-z0-9.-]+(:[0-9]+)?/[^\s"\'<>]*$#i', $a) ? $a : 'https://angebot.dashboard-stafl.de/admin/';
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
        // Stufe und gemeldete Anmeldemethoden mitschreiben (nur Kürzel wie pwd/otp/hwk – zur Fehlersuche bei doppelter Code-Abfrage)
        audit('oidc_stufe', 'Anmeldung über Keycloak ohne vorgeschriebenen zweiten Faktor – zweite Stufe angefordert',
              ['stufe' => substr($id['acr'], 0, 20), 'methoden' => substr(implode(',', array_map(fn($m) => preg_replace('/[^a-z0-9_-]/i', '', (string)$m), $id['amr'])), 0, 60)], $u);
        respond(['ok' => false, 'code' => 'reauth_required', 'anmelden' => oidc_stufe_adresse(),
                 'error' => 'Für Ihr Konto ist die Anmeldung mit zweitem Faktor (Einmalcode oder Passkey) vorgeschrieben.'], 403);
        exit;
    }
    start_session();
    unset($_SESSION['oidcStufeAngefordert']);
    // Abgelaufen (Inaktivität) oder in Verwaltung → Sitzungen beendet: weiter erst nach erneuter Anmeldung bei Keycloak
    [$ende, $grund] = oidc_ende_zeit($id, $u);
    if ($ende > 0) {
        // Inaktivität: Anmeldezeitpunkt bei Keycloak zum Zeitpunkt des Ablaufs merken – weiter erst mit einer NEUEN Anmeldung
        // (späterer auth_time). Unabhängig von Uhrabweichungen zwischen Keycloak und diesem Server.
        if ($grund === 'inaktiv' && !isset($_SESSION['oidcEndeAuth'])) $_SESSION['oidcEndeAuth'] = $id['authTime'];
        $neu = $grund === 'inaktiv' ? $id['authTime'] > (int)$_SESSION['oidcEndeAuth'] : $id['authTime'] > $ende;
        if (!$neu) oidc_erneuern($u, $grund, $ende, $id['authTime']);
        unset($_SESSION['oidcEnde'], $_SESSION['oidcEndeAuth'], $_SESSION['oidcErneuert']);
    }
    $passt = ($_SESSION['uid'] ?? '') === $u['id'] && ($_SESSION['oidcSub'] ?? '') === $id['sub'] && ($_SESSION['oidcSid'] ?? '') === $id['sid']
        && (int)($_SESSION['sv'] ?? -1) === (int)$u['sv'] && isset((store_read('sitzungen') ?? [])[(string)($_SESSION['sid'] ?? '')]);
    if (!$passt) {
        $_SESSION = [];
        sign_in($u);
        $_SESSION['oidcSub'] = $id['sub'];
        $_SESSION['oidcSid'] = $id['sid'];
        oidc_sitzung_vermerken((string)($_SESSION['sid'] ?? ''), $id['sid']);
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
/* ---------- Ablauf und Beenden von Sitzungen auf Keycloak-Hosts ----------
   Die PHP-Sitzung eines Keycloak-Hosts entsteht neu, sobald sie fehlt – solange die Sitzung des Webserver-Moduls gilt.
   Damit Abmeldung nach Inaktivität (Sicherheitseinstellung) und „Sitzung beenden“ (Verwaltung → Sitzungen) wirken,
   merkt sich der Server das Ende: Inaktivität in der (geleerten) PHP-Sitzung (start_session), beendete Sitzungen im
   Dokument „oidc-abmeldungen“ je Keycloak-Sitzung (sid) bzw. – ohne bekannte sid oder für alle Sitzungen eines
   Mitarbeiters – je Mitarbeiter. Weiter geht es erst nach erneuter Anmeldung bei Keycloak (max_age=0, auth_time danach). */
const OIDC_ABMELDUNG_HALTEN = 39600;   // Sekunden; länger als die Höchstdauer der Modul-Sitzung (OIDCSessionMaxDuration 36000)
function oidc_abmeldungen(): array
{
    $d = store_read('oidc-abmeldungen') ?? [];
    $grenze = time() - OIDC_ABMELDUNG_HALTEN;
    $f = function ($l) use ($grenze) { return array_filter(is_array($l) ? $l : [], fn($t) => is_int($t) && $t > $grenze); };
    return ['sid' => $f($d['sid'] ?? []), 'nutzer' => $f($d['nutzer'] ?? [])];
}
/* Beendete Sitzungen vermerken (Keycloak-sid bzw. Mitarbeiter-Kennungen) */
function oidc_abmeldung_merken(array $sids, array $uids): void
{
    $sids = array_values(array_filter(array_map('strval', $sids), fn($x) => $x !== ''));
    $uids = array_values(array_filter(array_map('strval', $uids), fn($x) => $x !== ''));
    if (!$sids && !$uids) return;
    with_lock('oidc-abmeldungen', function () use ($sids, $uids) {
        $d = oidc_abmeldungen();
        foreach ($sids as $x) $d['sid'][$x] = time();
        foreach ($uids as $x) $d['nutzer'][$x] = time();
        store_write('oidc-abmeldungen', $d);
    });
}
/* Zeitpunkt, bis zu dem eine Anmeldung bei Keycloak nicht mehr genügt, und Grund ('inaktiv' | 'beendet'); 0 = keiner */
function oidc_ende_zeit(array $id, array $u): array
{
    $ende = (int)($_SESSION['oidcEnde'] ?? 0); $grund = $ende ? 'inaktiv' : '';
    $a = oidc_abmeldungen();
    foreach ([$a['sid'][$id['sid']] ?? 0, $a['nutzer'][(string)$u['id']] ?? 0] as $t) if ($t > $ende) { $ende = $t; $grund = 'beendet'; }
    return [$ende, $grund];
}
/* Erneute Anmeldung bei Keycloak verlangen; Schutz vor Endlosschleifen wie bei der zweiten Stufe (3 in 10 Minuten) */
function oidc_erneuern(array $u, string $grund, int $ende, int $authTime = 0): never
{
    $a = $_SESSION['oidcErneuert'] ?? [];
    $a = array_values(array_filter(is_array($a) ? $a : [], fn($t) => (int)$t > time() - 600));
    if (count($a) >= 3) fail('Die erneute Anmeldung wurde nicht bestätigt. Bitte abmelden und neu anmelden.', 403);
    $a[] = time();
    $_SESSION['oidcErneuert'] = $a;
    if ((int)($_SESSION['oidcEndeGemeldet'] ?? 0) !== $ende) {
        $_SESSION['oidcEndeGemeldet'] = $ende;
        audit('oidc_ablauf', $grund === 'beendet' ? 'Beendete Sitzung: erneute Anmeldung bei Keycloak verlangt' : 'Sitzung wegen Inaktivität abgelaufen: erneute Anmeldung bei Keycloak verlangt', [], $u);
    }
    // Keycloak rechnet auth_time in ganzen Sekunden: liegen Anmeldung und Ende in derselben Sekunde, gilt max_age=0 dort
    // noch als erfüllt (keine Passwortabfrage) – dann kurz warten, damit die erneute Anmeldung wirklich verlangt wird
    if (time() <= $ende + 1) { session_write_close(); sleep(1); }
    respond(['ok' => false, 'code' => 'reauth_required', 'anmelden' => oidc_neu_anmelden_adresse(),
             'stand' => ['anmeldung' => $authTime, 'ende' => $ende, 'grund' => $grund],   // nur Zeitpunkte der eigenen Sitzung (Fehlersuche)
             'error' => $grund === 'beendet' ? 'Ihre Sitzung wurde beendet. Bitte melden Sie sich erneut an.' : 'Ihre Sitzung ist wegen Inaktivität abgelaufen. Bitte melden Sie sich erneut an.'], 403);
    exit;
}
/* Keycloak-Sitzung (sid) am Eintrag im Sitzungsregister vermerken – für „Sitzung beenden“ */
function oidc_sitzung_vermerken(string $regSid, string $kcSid): void
{
    if ($regSid === '' || $kcSid === '') return;
    with_lock('sitzungen', function () use ($regSid, $kcSid) {
        $l = store_read('sitzungen') ?? [];
        if (isset($l[$regSid])) { $l[$regSid]['oidcSid'] = $kcSid; store_write('sitzungen', $l); }
    });
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
