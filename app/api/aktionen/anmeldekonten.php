<?php
declare(strict_types=1);
/* Aktionen: Konten der zentralen Anmeldung (Keycloak) aus Verwaltung → Mitarbeiter (nur Administratoren).
   anmeldekonto (lesen): Zustand des Kontos · anmeldekonto_aendern (schreibend, immer mit Bestätigung): Passwort setzen,
   Sperre aufheben, Link zum Passwort-Festlegen per Mail, fehlendes Konto anlegen (mit „einladen“ gleich samt Einladung per
   Mail). Logik und Grenzen: lib/anmeldekonten.php.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Mitarbeiterkonto zur Kennung oder 404 */
function anmeldekonto_nutzer(string $id): array
{
    $users = users_load();
    $i = user_find($users, $id);
    if ($i === null) fail('Mitarbeiter nicht gefunden.', 404);
    return $users[$i];
}

/* Administratoren und Konten mit Pflicht zum zweiten Faktor: Passwort nur vorübergehend setzen (muss bei der nächsten
   Anmeldung geändert werden) – sonst kennte der setzende Administrator ein dauerhaftes Passwort dieser Konten */
function anmeldekonto_nur_temporaer(array $u): bool
{
    return ($u['role'] ?? '') === 'admin' || twofa_required($u);
}

switch ($action) {
        case 'anmeldekonto': {
            require_auth(false, 'admin');
            header('Cache-Control: no-store');
            $u = anmeldekonto_nutzer((string)($_GET['id'] ?? ''));
            if (!nutzer_hat_zugang($u)) respond(['ok' => true, 'konto' => ['eingerichtet' => konten_eingerichtet(), 'ohneAnmeldung' => true]]);
            try { $k = konten_status($u); }
            catch (KontenFehler $e) { $k = ['eingerichtet' => $e->status !== 503, 'fehler' => $e->getMessage()]; }
            respond(['ok' => true, 'konto' => $k + ['nurTemporaer' => anmeldekonto_nur_temporaer($u)]]);
        }

        case 'anmeldekonto_aendern': {
            $me = require_admin_confirmation('anmeldekonto');
            header('Cache-Control: no-store');
            $b = body();
            $u = anmeldekonto_nutzer((string)($b['id'] ?? ''));
            $was = (string)($b['was'] ?? '');
            if (!in_array($was, ['passwort', 'entsperren', 'link', 'anlegen'], true)) fail('Unbekannte Aktion.', 422);
            if ($u['id'] === $me['id']) fail('Das eigene Konto ändern Sie über die Anmeldeseite (Passwort vergessen bzw. Konto) – oder ein anderer Administrator.', 403);
            if (!nutzer_hat_zugang($u)) fail('Dieser Mitarbeiter hat keine Anmeldung („ohne Anmeldung“).', 422);
            if (empty($u['active']) && $was !== 'entsperren') fail('Der Zugang ist deaktiviert – bitte zuerst aktivieren.', 422);
            $antwort = ['ok' => true];
            try {
                if ($was === 'passwort') {
                    $erzeugt = !empty($b['erzeugen']);
                    $pw = $erzeugt ? konten_startpasswort() : $b['passwort'] ?? null;
                    if (!is_string($pw) || mb_strlen($pw) < 12 || mb_strlen($pw) > 200) fail('Das Passwort muss mindestens 12 Zeichen lang sein.', 422);
                    $temporaer = !array_key_exists('aendern', $b) || !empty($b['aendern']) || anmeldekonto_nur_temporaer($u);
                    konten_passwort($u, $pw, $temporaer);
                    audit('security', 'Passwort für „' . $u['username'] . '“ in der zentralen Anmeldung gesetzt' . ($temporaer ? ' (muss bei der nächsten Anmeldung geändert werden)' : ' (dauerhaft)'));
                    if ($erzeugt) $antwort['passwort'] = $pw;   // nur dieses eine Mal, nie gespeichert
                    $antwort['temporaer'] = $temporaer;
                } elseif ($was === 'entsperren') {
                    konten_entsperren($u);
                    audit('security', 'Konto „' . $u['username'] . '“ in der zentralen Anmeldung entsperrt');
                } elseif ($was === 'link') {
                    $an = konten_link($u);
                    audit('security', 'Link zum Passwort-Festlegen an „' . $u['username'] . '“ geschickt (' . $an . ', ' . KONTEN_LINK_STUNDEN . ' Stunden gültig)');
                    $antwort['an'] = $an;
                } else {
                    konten_anlegen($u);
                    audit('security', 'Konto „' . $u['username'] . '“ in der zentralen Anmeldung angelegt und verknüpft');
                    $u = anmeldekonto_nutzer((string)$u['id']);
                    // Gleich die Einladung (Link zum Passwort-Festlegen) – das Konto bleibt angelegt, auch wenn der Versand scheitert
                    if (!empty($b['einladen'])) {
                        try {
                            $an = konten_link($u);
                            audit('security', 'Einladung (Link zum Passwort-Festlegen) an „' . $u['username'] . '“ geschickt (' . $an . ', ' . KONTEN_LINK_STUNDEN . ' Stunden gültig)');
                            $antwort['an'] = $an;
                        } catch (KontenFehler $e) { $antwort['einladungFehler'] = $e->getMessage(); }
                    }
                }
                $antwort['konto'] = konten_status($u) + ['nurTemporaer' => anmeldekonto_nur_temporaer($u)];
            } catch (KontenFehler $e) { fail($e->getMessage(), $e->status); }
            respond($antwort);
        }
}
