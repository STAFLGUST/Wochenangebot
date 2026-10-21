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
