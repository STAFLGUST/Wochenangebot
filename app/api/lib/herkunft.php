<?php
declare(strict_types=1);
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Herkunftsprüfung im API-Einstieg (GR-109, ADR-003 §1): Die Schnittstelle beantwortet nur Anfragen, die von der eigenen
   Seite (gleicher Host) kommen. Browser melden die Herkunft in `Sec-Fetch-Site`; `same-site` (z. B. von
   test.angebot-stafl.de) und `cross-site` werden abgewiesen – SameSite-Cookies schützen nur gegen fremde Domains, nicht
   gegen Nachbar-Subdomains. Für Anfragen, die etwas ändern können (alles außer GET/HEAD), muss zusätzlich ein
   mitgesendeter `Origin` genau der eigene sein. Ohne diese Kopfzeilen (App, ältere Browser, Server-zu-Server) gilt
   unverändert der bisherige Schutz: CSRF-Token, JSON-Pflicht, SameSite=Strict. Ausnahmen nur über das Registerfeld
   `fremde_herkunft` (Ein-Klick-Abmeldung aus dem E-Mail-Programm). Ergänzt die CSRF-Prüfung, ersetzt sie nicht. */

function herkunft_eigene(): string
{
    return (is_https() ? 'https' : 'http') . '://' . strtolower(trim((string)($_SERVER['HTTP_HOST'] ?? '')));
}

/* Grund der Abweisung oder null, wenn die Anfrage von der eigenen Seite stammt */
function herkunft_fremd(?array $aktion, string $method): ?string
{
    if ($aktion !== null && !empty($aktion['fremde_herkunft'])) return null;
    $site = strtolower(trim((string)($_SERVER['HTTP_SEC_FETCH_SITE'] ?? '')));
    if ($site !== '' && $site !== 'same-origin' && $site !== 'none') return 'Sec-Fetch-Site: ' . substr($site, 0, 20);
    if ($method !== 'GET' && $method !== 'HEAD' && isset($_SERVER['HTTP_ORIGIN'])) {
        $origin = strtolower(trim((string)$_SERVER['HTTP_ORIGIN']));
        if (!hash_equals(herkunft_eigene(), $origin)) return 'Origin';
    }
    return null;
}

/* Abweisen, ohne die Firewall zu belasten: eine fremde Seite darf ihre Besucher nicht sperren lassen (vgl. fw_fremd) */
function herkunft_pruefen(?array $aktion, string $method): void
{
    if (herkunft_fremd($aktion, $method) === null) return;
    header('Cache-Control: no-store');
    header('Vary: Origin, Sec-Fetch-Site');
    fail('Diese Anfrage kam nicht von unserer Seite und wurde abgewiesen.', 403);
}

/* Aktion ↔ Host (GR-109, ADR-003 §3): Auf einem Keycloak-Host meldet der Webserver seine Oberfläche (SetEnv
   WA_OBERFLAECHE, nie aus Kopfzeilen). Aktionen einer Oberfläche mit eigener Seite – jede Oberfläche außer dem gemeinsamen
   Eingabebereich angebot.*, für die das Aktionsregister Aktionen führt (heute hr.intern, crm.intern, marketing.intern, sicherheit.intern) – beantwortet nur ihr eigener
   Host. Auf einem solchen Host gibt es außer ihnen nur die Grundaktionen der Plattform, die auch während einer Wartung
   erreichbar bleiben (Status, Abmelden, Modulübersicht) – ebenso auf dem Dashboard-Host (host_nur_grundaktionen).
   Angebot, Verwaltung und Bestand teilen sich weiter den Eingabebereich (Aktionen unter angebot.eingabe). Ohne Angabe des Webservers (angebot-stafl.de, App, Testserver) gilt
   das Bisherige. Ergänzt die Rechteprüfung jeder Aktion (GR-103), ersetzt sie nicht. */
function host_eigene_seite(string $oberflaeche): bool
{
    static $mitAktionen = null;
    if ($mitAktionen === null) {
        $mitAktionen = [];
        foreach (AKTIONEN as $a) $mitAktionen[(string)$a['oberflaeche']] = true;
    }
    return $oberflaeche !== '' && strpos($oberflaeche, 'angebot.') !== 0 && isset($mitAktionen[$oberflaeche]);
}

/* Hosts ohne Fachaktionen: das Dashboard (dashboard-stafl.de) braucht nur Status, Modulübersicht, Darstellung und Abmelden.
   Ohne diese Regel nähme es jede Aktion des gemeinsamen Eingabebereichs an – und dort verlangt kein Modulzugang etwas
   (Modul „dashboard“ hat keinen eigenen Zugang): Wem „angebot.zugang“ entzogen war, der hätte Entwurf, Bestellungen und
   Kunden über die Dashboard-Adresse weiter abrufen können (Einzelrechte vorausgesetzt). */
function host_nur_grundaktionen(string $host): bool
{
    return explode('.', $host, 2)[0] === 'dashboard';
}

/* true, wenn die Aktion auf diesem Host nicht angeboten wird */
function host_fremd(?array $aktion): bool
{
    if ($aktion === null || !oidc_modus()) return false;
    $host = oidc_einstellung('WA_OBERFLAECHE');
    if ($host === '') return false;
    $eigen = (string)$aktion['oberflaeche'];
    if (host_eigene_seite($eigen)) return $eigen !== $host;
    if (host_eigene_seite($host) || host_nur_grundaktionen($host)) return !($aktion['modul'] === 'plattform' && $aktion['wartung_frei']);
    return false;
}

function host_pruefen(?array $aktion): void
{
    if (!host_fremd($aktion)) return;
    header('Cache-Control: no-store');
    fail('Diese Aktion gibt es unter dieser Adresse nicht.', 404);
}
