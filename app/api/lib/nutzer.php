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
            'twofa' => !empty($u['totp']), 'lockedUntil' => (int)($u['lockedUntil'] ?? 0) > time() ? (int)$u['lockedUntil'] : null];
}
/* Ersteinrichtung im Browser nur auf einem wirklich leeren System – nie, wenn Nutzerdaten
   vorhanden, aber nicht lesbar sind, und nie auf dem Produktivserver (WA_INSTALLED=1). */
function setup_allowed(): bool
{
    if (getenv('WA_INSTALLED') === '1' || ($_SERVER['WA_INSTALLED'] ?? '') === '1') return false;
    return store_mtime('nutzer') === null && store_mtime('admin') === null;
}
/* Unter der Nutzersperre aufrufen: gilt für Passwort UND zweiten Anmeldeschritt. */
function login_failure(array &$u): bool
{
    $S = sec();
    $u['failCount'] = (int)($u['failCount'] ?? 0) + 1;
    if ($u['failCount'] < max(3, (int)$S['lockAfter'])) return false;
    $u['lockedUntil'] = time() + 60 * max(1, (int)$S['lockMinutes']);
    $u['failCount'] = 0;
    return true;
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
