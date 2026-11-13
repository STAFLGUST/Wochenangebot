<?php
declare(strict_types=1);
/* Aktionen: Modul Versand – Wochenangebot und Kundenangebote veröffentlichen und per E-Mail an Kunden senden (Oberfläche
   versand.intern; Funktionen in app/api/module/versand/versand.php, Daten und Regeln beim Angebot: lib/angebote.php,
   lib/kundenmail.php).
   Rechte (GR-103): Modulzugang versand.zugang für jede Aktion (API-Einstieg), dazu
     versand_start, versand_verlauf      nur Zahlen, Namen der Angebote und der Mitarbeiter
     versand_aenderungen                 Modulzugang Angebot (die Liste enthält Preise, auch Kundenpreise)
     versand_veroeffentlichen            angebot.veroeffentlichen; veröffentlicht den gespeicherten Entwurf, Revision Pflicht (409)
     versand_empfaenger, _vorschau       wochenangebot.senden bzw. sonderposten.senden (Firmen und E-Mail-Adressen)
     versand_senden                      dasselbe Recht mit Bestätigung (Katalog BESTAETIGUNG: kunden_rundmail, kunden_restposten)
   Sonderposten gehen nur an Kunden des jeweiligen Angebots (GR-005, sonderposten_senden).
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Art der Sendung aus der Anfrage: 'woche' oder 'sonderposten' (sonst 422) */
function vs_art($v): string
{
    if ($v !== 'woche' && $v !== 'sonderposten') fail('Unbekannte Art der Sendung.', 422);
    return $v;
}
/* Angebot der Sonderposten aus der Anfrage (404, wenn es das Angebot nicht gibt) */
function vs_angebot($v): array
{
    $def = offer_def(is_string($v) ? $v : '');
    if (!$def) fail('Angebot nicht gefunden.', 404);
    return $def;
}

switch ($action) {
        /* Stand der Seite: Entwurf, veröffentlichtes Angebot, Zahl der Änderungen, Angebote der Woche, Versand, eigene Rechte */
        case 'versand_start': {
            $me = require_modulzugang('versand');
            header('Cache-Control: no-store');
            respond(['ok' => true, 'name' => $me['name'], 'rechte' => vs_rechte($me)] + vs_stand($me));
        }

        /* Änderungsliste Entwurf ↔ veröffentlicht mit Preisen: nur mit Modulzugang Angebot (wie die Aktion draft) */
        case 'versand_aenderungen': {
            require_modulzugang('versand');
            require_modulzugang('angebot');
            header('Cache-Control: no-store');
            $namen = [];
            foreach (angebot_stand()['angebote'] as $a) $namen[$a['id']] = $a['name'];
            respond(['ok' => true, 'angebote' => $namen] + angebot_aenderungen());
        }

        /* Gespeicherten Entwurf veröffentlichen. „revision“ ist Pflicht: Hat inzwischen jemand gespeichert, antwortet der
           Server mit 409 und die Seite zeigt die Liste neu – niemand veröffentlicht etwas, das er nicht gesehen hat. */
        case 'versand_veroeffentlichen': {
            $me = require_perm('angebot.veroeffentlichen', true);
            require_modulzugang('versand', true);
            $b = body();
            if (!array_key_exists('revision', $b) || !is_int($b['revision'])) fail('Bitte die Seite neu laden und die Änderungen erneut prüfen.', 422);
            $r = angebot_veroeffentlichen(null, $b['revision']);
            respond(['ok' => true] + $r);
        }

        /* Empfänger: Wochenangebot (alle Kunden mit Zugang, Angebot und E-Mail) bzw. Sonderposten eines Angebots */
        case 'versand_empfaenger': {
            require_modulzugang('versand');
            header('Cache-Control: no-store');
            $art = vs_art($_GET['art'] ?? '');
            $postfach = (bool)mail_cfg() && (bool)mail_base_url();
            if ($art === 'woche') {
                require_perm('wochenangebot.senden');
                $namen = [];
                foreach (angebot_stand()['angebote'] as $a) $namen[$a['id']] = $a['name'];
                respond(['ok' => true, 'art' => 'woche', 'postfach' => $postfach, 'angebote' => $namen] + wochenmail_empfaenger());
            }
            require_perm('sonderposten.senden');
            respond(['ok' => true, 'art' => 'sonderposten', 'postfach' => $postfach] + sonderposten_empfaenger(vs_angebot($_GET['angebot'] ?? '')));
        }

        /* Vorschau der E-Mail für einen Empfänger (ohne Versand) */
        case 'versand_vorschau': {
            $me = require_modulzugang('versand', true);
            $b = body();
            $art = vs_art($b['art'] ?? '');
            if (!may($me, $art === 'woche' ? 'wochenangebot.senden' : 'sonderposten.senden')) fail('Dafür fehlt Ihnen die Berechtigung. Bitte an einen Administrator wenden.', 403);
            if (!mail_base_url()) fail('Die Adresse der Angebotsseite für Links fehlt (DOMAIN bzw. WA_URL in .env).', 409);
            $c = null;
            foreach (customers_load()['customers'] as $x) if ($x['id'] === ($b['id'] ?? '')) $c = $x;
            if (!$c) fail('Kunde nicht gefunden.', 404);
            $note = mb_substr(trim((string)($b['note'] ?? '')), 0, 1000);
            if ($art === 'woche') [$sub, , $html] = mail_tpl_angebot($c, $note, mail_week());
            else { $def = vs_angebot($b['angebot'] ?? ''); [$sub, , $html] = mail_tpl_restposten($c, $def, restposten_items($def), $note); }
            header('Cache-Control: no-store');
            respond(['ok' => true, 'subject' => $sub, 'html' => $html, 'to' => (string)($c['email'] ?? ''), 'firma' => (string)$c['firma']]);
        }

        /* Senden (ein Teil der Auswahl; die Seite schickt die Kunden in Teilen zu zehn) – mit Bestätigung wie bisher */
        case 'versand_senden': {
            require_modulzugang('versand', true);
            $b = body();
            $art = vs_art($b['art'] ?? '');
            $ids = is_array($b['ids'] ?? null) ? $b['ids'] : [];
            if ($art === 'woche') {
                require_perm_confirmed('wochenangebot.senden', 'kunden_rundmail');
                $cfg = require_mail();
                respond(['ok' => true, 'results' => wochenmail_senden($cfg, $ids, (string)($b['note'] ?? ''), (int)($b['week'] ?? 0), (int)($b['year'] ?? 0))]);
            }
            require_perm_confirmed('sonderposten.senden', 'kunden_restposten');
            $cfg = require_mail();
            respond(['ok' => true, 'results' => sonderposten_senden($cfg, vs_angebot($b['angebot'] ?? ''), $ids, (string)($b['note'] ?? ''), (string)($b['publishedAt'] ?? ''))]);
        }

        /* Verlauf: Veröffentlichungen und Sendungen der letzten Monate (monate=2, „Alle anzeigen“: bis zur Aufbewahrungsgrenze) */
        case 'versand_verlauf': {
            require_modulzugang('versand');
            header('Cache-Control: no-store');
            respond(['ok' => true, 'verlauf' => vs_verlauf((int)($_GET['monate'] ?? 2)), 'monateMax' => PROTOKOLL_MONATE]);
        }
}
