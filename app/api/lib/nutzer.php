<?php
declare(strict_types=1);
/* Mitarbeiter-Zugänge und Passwortregeln */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- Nutzer ---------------- */

const ROLES = ['viewer' => 1, 'editor' => 2, 'admin' => 3];
const ROLE_LABELS = ['viewer' => 'Nur ansehen', 'editor' => 'Bearbeiter', 'admin' => 'Administrator'];

/* Exklusive Sperre für Lese-Ändere-Schreibe-Vorgänge (Nutzerliste, Protokoll) */
/* Nutzerliste; bisherige Einzel-Passwort-Installation wird einmalig zum Nutzer „admin“ */
function users_load(): array
{
    $u = store_read('nutzer');
    if (is_array($u) && isset($u['users'])) return $u['users'];
    $old = store_read('admin');
    if ($old && !empty($old['hash'])) {
        return with_lock('nutzer', function () use ($old) {
            $u = store_read('nutzer');
            if (is_array($u) && isset($u['users'])) return $u['users'];
            $users = [[
                'id' => 'u' . bin2hex(random_bytes(6)), 'username' => 'admin', 'name' => 'Administrator', 'role' => 'admin',
                'active' => true, 'hash' => (string)$old['hash'], 'mustChange' => false, 'sv' => 1,
                'created' => $old['created'] ?? now(), 'createdBy' => 'Übernahme', 'lastLogin' => null,
            ]];
            store_write('nutzer', ['users' => $users]);
            store_delete('admin');
            return $users;
        });
    }
    return [];
}
function users_save(array $users): void { store_write('nutzer', ['users' => array_values($users)]); }
function user_find(array $users, string $id): ?int { foreach ($users as $i => $u) if ($u['id'] === $id) return $i; return null; }
function user_public(array $u): array
{
    return ['id' => $u['id'], 'username' => $u['username'], 'name' => $u['name'], 'role' => $u['role'], 'active' => (bool)$u['active'],
            'mustChange' => (bool)($u['mustChange'] ?? false), 'created' => $u['created'] ?? null, 'createdBy' => $u['createdBy'] ?? '',
            'lastLogin' => $u['lastLogin'] ?? null, 'changed' => $u['changed'] ?? null,
            'twofa' => !empty($u['totp']), 'passkeys' => count((array)($u['passkeys'] ?? [])), 'lockedUntil' => (int)($u['lockedUntil'] ?? 0) > time() ? (int)$u['lockedUntil'] : null,
            'geraete' => function_exists('geraete_public') ? geraete_public($u) : [],
            'grant' => array_values((array)($u['grant'] ?? [])), 'deny' => array_values((array)($u['deny'] ?? [])),
            'perms' => function_exists('user_perms') ? user_perms($u) : []];
}
/* Ersteinrichtung im Browser nur auf einem wirklich leeren System – nie, wenn Nutzerdaten
   vorhanden, aber nicht lesbar sind, und nie auf dem Produktivserver (WA_INSTALLED=1). */
function setup_allowed(): bool
{
    if (getenv('WA_INSTALLED') === '1' || ($_SERVER['WA_INSTALLED'] ?? '') === '1') return false;
    return store_mtime('nutzer') === null && store_mtime('admin') === null;
}
/* Unter der Nutzersperre aufrufen: gilt für Passwort UND zweiten Anmeldeschritt. */
/* Vergleichswert für unbekannte Benutzernamen: gleiche Rechenzeit wie bei einem vorhandenen Zugang. Die Kosten richten sich
   nach den gespeicherten Passwörtern (PHP 8.4 erhöht den Standard von 10 auf 12; sonst wären unbekannte Namen schneller). */
const DUMMY_HASHES = [
    10 => '$2y$10$mvZvmdEAVEQ3qaAv8iuXuuDEFqUa7vwt.m2SPPnd0efnA2gP5.1fi',
    11 => '$2y$11$270c1FHrghnxeifZDDTN7eUHr00fuM/TZpKbxj6eqHnAlU6GOrKLy',
    12 => '$2y$12$viN1CkKfMccsPR4Vk0FnNu0lBewb6H2IuPzvHS4UyiDtgFZeArpUO',
    13 => '$2y$13$afHdYZG5U990s5BOYZrAou8JrcS9e.7kkqfubrzPW2igqN8grOZjS',
];
function dummy_kosten(array $hashes): int
{
    foreach ($hashes as $h) {
        $i = is_string($h) ? password_get_info($h) : [];
        if (($i['algoName'] ?? '') === 'bcrypt' && isset(DUMMY_HASHES[(int)($i['options']['cost'] ?? 0)])) return (int)$i['options']['cost'];
    }
    $std = defined('PASSWORD_BCRYPT_DEFAULT_COST') ? (int)PASSWORD_BCRYPT_DEFAULT_COST : 10;
    return isset(DUMMY_HASHES[$std]) ? $std : 10;
}
function dummy_verify(string $pw, array $hashes): void { password_verify($pw, DUMMY_HASHES[dummy_kosten($hashes)]); }
function login_failure(array &$u): bool
{
    $S = sec();
    // Fehlversuche verfallen nach 24 Stunden ohne weiteren Fehlversuch – wie bei unbekannten Namen (ghost_lock), damit beide
    // gleich reagieren und vereinzelte Vertipper nicht monatelang mitzählen
    if ((int)($u['failAt'] ?? 0) < time() - 86400) $u['failCount'] = 0;
    $u['failAt'] = time();
    $u['failCount'] = (int)($u['failCount'] ?? 0) + 1;
    if ($u['failCount'] < max(3, (int)$S['lockAfter'])) return false;
    $u['lockedUntil'] = time() + 60 * max(1, (int)$S['lockMinutes']);
    $u['failCount'] = 0;
    unset($u['lockTries']);   // neue Sperre: Code-Versuche neu zählen (keine Reste einer früheren Sperre)
    return true;
}
/* Fehlversuche für unbekannte Benutzernamen wie bei echten Zugängen zählen: gleiche Sperrmeldung nach gleich vielen
   Versuchen, damit die Antwort nicht verrät, ob es einen Benutzernamen gibt. Gibt das Sperrende zurück (0 = nicht gesperrt);
   $neu ist true, wenn die Sperre gerade durch diesen Fehlversuch begonnen hat. */
function ghost_lock(string $scope, string $name, bool $fail, ?bool &$neu = null): int
{
    $neu = false;
    if ($name === '') return 0;
    return (int)with_lock('anmeldenamen', function () use ($scope, $name, $fail, &$neu) {
        $S = sec();
        $now = time();
        $a = store_read('anmeldenamen') ?? [];
        foreach ($a as $k => $v) if ((int)($v['until'] ?? 0) < $now && (int)($v['t'] ?? 0) < $now - 86400) unset($a[$k]);
        if (count($a) > 5000) {   // Größe begrenzen: laufende Sperren nie vorzeitig entfernen (sonst verriete ihr Ende den Namen), sonst die ältesten
            $aktiv = array_filter($a, fn($v) => (int)($v['until'] ?? 0) >= $now);
            if (count($aktiv) > 20000) { uasort($aktiv, fn($x, $y) => (int)$y['until'] <=> (int)$x['until']); $aktiv = array_slice($aktiv, 0, 20000, true); }   // Obergrenze auch für laufende Sperren
            $rest = array_diff_key($a, $aktiv);
            uasort($rest, fn($x, $y) => (int)($y['t'] ?? 0) <=> (int)($x['t'] ?? 0));
            $a = $aktiv + array_slice($rest, 0, max(0, 4000 - count($aktiv)), true);
        }
        $k = $scope . ':' . hash('sha256', $name);
        $g = $a[$k] ?? ['n' => 0, 'until' => 0, 't' => 0];
        if ((int)$g['until'] > $now) return (int)$g['until'];
        if (!$fail) return 0;
        $g['n'] = (int)$g['n'] + 1;
        $g['t'] = $now;
        $g['until'] = 0;
        if ($g['n'] >= max(3, (int)$S['lockAfter'])) { $g['until'] = $now + 60 * max(1, (int)$S['lockMinutes']); $g['n'] = 0; $neu = true; }
        $a[$k] = $g;
        store_write('anmeldenamen', $a);
        return (int)$g['until'];
    });
}
function active_admins(array $users): int { $n = 0; foreach ($users as $u) if ($u['role'] === 'admin' && $u['active']) $n++; return $n; }
function clean_username($v): string
{
    $v = is_string($v) ? strtolower(trim($v)) : '';
    if (!preg_match('/^[a-z0-9][a-z0-9._-]{1,31}$/', $v)) throw new InvalidArgumentException('Benutzername: 2–32 Zeichen, nur Buchstaben a–z, Ziffern, Punkt, Binde- und Unterstrich.');
    return $v;
}
const COMMON_PASSWORDS = ['passwort', 'password', 'passwort1', 'passwort123', 'password1', 'password123', '123456789', '1234567890', '12345678910',
    'qwertz123', 'qwertzuiop', 'qwertyuiop', 'hallo12345', 'hallohallo', 'sommer2026', 'winter2026', 'herbst2026', 'fruehling2026', 'frühling2026',
    'sommer2025', 'winter2025', 'willkommen', 'willkommen1', 'willkommen123', 'administrator', 'admin12345', 'adminadmin', 'standardfleisch',
    'standard-fleisch', 'fleischmeister', 'wochenangebot', 'geheim1234', 'iloveyou12', 'abc1234567', '0000000000', '1111111111', 'letmein123'];
function check_password($pw, string $username = ''): string
{
    $pw = is_string($pw) ? $pw : '';
    $S = sec();
    $min = max(10, (int)$S['pwMin']);
    if (mb_strlen($pw) < $min) throw new InvalidArgumentException("Das Passwort muss mindestens $min Zeichen lang sein.");
    if (strlen($pw) > 200) throw new InvalidArgumentException('Das Passwort ist zu lang.');
    $low = mb_strtolower($pw);
    if (in_array($low, COMMON_PASSWORDS, true) || preg_match('/^(.)\1+$/u', $pw)) throw new InvalidArgumentException('Dieses Passwort ist zu leicht zu erraten. Bitte ein anderes wählen.');
    if ($username !== '' && strlen($username) >= 3 && strpos($low, strtolower($username)) !== false) throw new InvalidArgumentException('Das Passwort darf den Benutzernamen nicht enthalten.');
    if (!empty($S['pwComplex'])) {
        $classes = (int)preg_match('/[a-zäöüß]/u', $pw) + (int)preg_match('/[A-ZÄÖÜ]/u', $pw) + (int)preg_match('/\d/', $pw) + (int)preg_match('/[^\p{L}\d]/u', $pw);
        if ($classes < 3) throw new InvalidArgumentException('Das Passwort braucht mindestens drei der vier Zeichenarten: Kleinbuchstaben, Großbuchstaben, Ziffern, Sonderzeichen.');
    }
    return $pw;
}
