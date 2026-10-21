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
    return ['id' => $u['id'], 'username' => $u['username'], 'name' => $u['name'], 'vorname' => (string)($u['vorname'] ?? ''), 'nachname' => (string)($u['nachname'] ?? ''),
            'email' => (string)($u['email'] ?? ''), 'mailInfo' => $u['mailInfo'] ?? null, 'role' => $u['role'], 'active' => (bool)$u['active'],
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
/* Antworten auf fehlgeschlagene Anmeldungen gleich lang machen (ab Beginn der Anfrage), unabhängig davon, ob es den Namen
   gibt und wie aufwendig sein Passwort-Prüfwert ist (bcrypt-Kosten 10–12) – bremst zugleich das Durchprobieren */
const ANMELDUNG_ANTWORT_SEK = 0.6;
function anmeldung_angleichen(): void
{
    $start = (float)($_SERVER['REQUEST_TIME_FLOAT'] ?? microtime(true));
    $rest = $start + ANMELDUNG_ANTWORT_SEK - microtime(true);
    usleep($rest > 0 ? (int)($rest * 1e6) : 0);
}
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
/* Benutzername aus Vor- und Nachname: „vorname-nachname“, klein, Umlaute als ae/oe/ue/ss, Akzente ohne Zeichen,
   Leerzeichen und Sonderzeichen werden zu „-“; belegt → „-2“, „-3“ … (höchstens 32 Zeichen). */
function benutzername_vorschlag(string $vorname, string $nachname, array $belegt = []): string
{
    $teil = function (string $s): string {
        $s = mb_strtolower(trim($s));
        $s = strtr($s, ['ä' => 'ae', 'ö' => 'oe', 'ü' => 'ue', 'ß' => 'ss']);
        $t = @iconv('UTF-8', 'ASCII//TRANSLIT//IGNORE', $s);
        $s = $t !== false ? strtolower($t) : $s;
        return trim(preg_replace('/[^a-z0-9]+/', '-', $s) ?? '', '-');
    };
    $basis = trim(implode('-', array_filter([$teil($vorname), $teil($nachname)], 'strlen')), '-');
    $basis = rtrim(substr($basis, 0, 32), '-');
    if (strlen($basis) < 2) return '';
    $belegt = array_map('strtolower', $belegt);
    $u = $basis; $n = 2;
    while (in_array($u, $belegt, true)) { $suf = '-' . $n++; $u = rtrim(substr($basis, 0, 32 - strlen($suf)), '-') . $suf; }
    return $u;
}
/* Name, Vorname, Nachname und E-Mail eines Nutzers aus der Anfrage. Ältere Oberflächen schicken nur „name“. */
function nutzer_person(array $b, bool $neu = true): array
{
    $vor = s($b['vorname'] ?? '', 40) ?? '';
    $nach = s($b['nachname'] ?? '', 40) ?? '';
    $mail = strtolower(trim((string)($b['email'] ?? '')));
    if ($mail !== '' && (strlen($mail) > 160 || filter_var($mail, FILTER_VALIDATE_EMAIL) === false || preg_match('/[\r\n]/', $mail))) throw new InvalidArgumentException('Die E-Mail-Adresse ist ungültig.');
    if ($vor !== '' || $nach !== '') {
        // Neu: beides Pflicht. Ältere Zugänge mit einwortigem Namen (z. B. „Administrator“) bleiben speicherbar.
        if ($neu && ($vor === '' || $nach === '')) throw new InvalidArgumentException('Bitte Vorname und Nachname angeben.');
        $name = trim($vor . ' ' . $nach);
    } else {
        $name = s($b['name'] ?? '', 80, false);
        if ($name === null || $name === '') throw new InvalidArgumentException('Bitte Vorname und Nachname angeben.');
    }
    return ['name' => mb_substr($name, 0, 80), 'vorname' => $vor, 'nachname' => $nach, 'email' => $mail];
}
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
    if (!empty($S['pwLeak']) && ($n = pw_datenleck($pw)) > 0) {
        throw new InvalidArgumentException('Dieses Passwort ist in bekannten Datenlecks aufgetaucht' . ($n > 1 ? ' (' . number_format($n, 0, ',', '.') . '-mal)' : '') . ' und gilt deshalb als unsicher. Bitte ein anderes wählen.');
    }
    return $pw;
}

/* Prüfung gegen „Pwned Passwords“ (haveibeenpwned.com) mit k-Anonymität: Übertragen werden nur die ersten 5 Zeichen des
   SHA-1-Prüfwerts; der Abgleich der Antwort (alle Prüfwerte mit diesem Anfang, aufgefüllt) geschieht hier. Liefert die Anzahl
   der Funde, 0 = nicht bekannt, null = Dienst nicht erreichbar (dann wird nichts blockiert). */
const PW_LEAK_URL = 'https://api.pwnedpasswords.com/range/%s';
function pw_datenleck(string $pw): ?int
{
    static $cache = [];   // je Anfrage: Vorabprüfung außerhalb der Datensperre, danach ohne erneuten Netzzugriff
    $h = strtoupper(sha1($pw));
    if (array_key_exists($h, $cache)) return $cache[$h];
    $st = store_read('datenleck');
    if (is_array($st) && empty($st['ok']) && (int)($st['t'] ?? 0) > time() - 600) return $cache[$h] = null;   // nach einem Ausfall 10 Minuten Pause
    $ctx = stream_context_create(['http' => ['timeout' => 3, 'ignore_errors' => false, 'user_agent' => 'Wochenangebot',
                                             'header' => "Add-Padding: true\r\n"], 'ssl' => ['verify_peer' => true]]);
    $url = sprintf(getenv('WA_PWNED_URL') ?: PW_LEAK_URL, substr($h, 0, 5));   // WA_PWNED_URL nur in den Tests
    $t0 = microtime(true);
    $body = @file_get_contents($url, false, $ctx, 0, 2 * 1024 * 1024);
    $ok = is_string($body) && $body !== '';
    pw_datenleck_status($ok);
    if (!$ok) { error_log('[wochenangebot] Datenleck-Prüfung nicht erreichbar (' . round(microtime(true) - $t0, 1) . ' s)'); return $cache[$h] = null; }
    $suffix = substr($h, 5);
    foreach (preg_split('/\R/', $body) as $line) {
        $p = explode(':', trim($line));
        if (count($p) === 2 && hash_equals(strtoupper($p[0]), $suffix)) return $cache[$h] = max(0, (int)$p[1]);   // aufgefüllte Einträge haben 0
    }
    return $cache[$h] = 0;
}
/* Vorab (vor dem Sperren der Nutzer-/Kundendaten) prüfen, damit die Anfrage beim Dienst keine anderen Anmeldungen aufhält */
function pw_datenleck_vorab($pw): void { if (is_string($pw) && $pw !== '' && strlen($pw) <= 200 && !empty(sec()['pwLeak'])) pw_datenleck($pw); }

/* Letztes Ergebnis merken (Konfigurationsprüfung zeigt, ob der Dienst erreichbar war); Fehler stören nicht */
function pw_datenleck_status(bool $ok): void
{
    try {
        $alt = store_read('datenleck') ?? [];
        if (($alt['ok'] ?? null) === $ok && (int)($alt['t'] ?? 0) > time() - ($ok ? 3600 : 600)) return;   // selten schreiben (Ausfall: Pause 10 Min., s. o.)
        store_write('datenleck', ['ok' => $ok, 't' => time()]);
    } catch (Throwable $e) { error_log('[wochenangebot] datenleck-status: ' . $e->getMessage()); }
}

/* Bei der Anmeldung: bestehendes Passwort einmal je Passwort prüfen (Merker = Prüfwert des gespeicherten Hashes). Ist es
   betroffen, muss es sofort geändert werden. Läuft außerhalb der Sperre der Nutzerdaten; Ausfall des Dienstes blockiert nicht.
   Liefert true, wenn das Passwort betroffen ist; $merker ist dann bzw. bei unauffälligem Ergebnis der neue Merker. */
function pw_leak_bei_anmeldung(string $pw, array $acc, ?string &$merker = null): bool
{
    $merker = null;
    if (empty(sec()['pwLeak']) || empty($acc['hash'])) return false;
    $m = hash('sha256', 'leak|' . (string)$acc['hash']);
    if (hash_equals((string)($acc['leakGeprueft'] ?? ''), $m)) return false;
    $n = pw_datenleck($pw);
    if ($n === null) return false;   // später erneut versuchen
    $merker = $m;
    return $n > 0;
}

/* E-Mail an einen Mitarbeiter mit seinen Zugangsdaten (Verwaltung → Nutzer). Das Startpasswort steht nur darin,
   wenn es mitgegeben wurde (und zum gespeicherten Passwort passt – geprüft in der Aktion user_mail). */
function mail_tpl_nutzer(array $u, ?string $startPw, string $note = ''): array
{
    global $CFG;
    $company = (string)($CFG['company'] ?? '');
    $url = mail_base_url() . '/admin/';
    $vor = (string)($u['vorname'] ?? '') !== '' ? $u['vorname'] : '';
    $gruss = $vor !== '' ? "Hallo $vor," : 'Guten Tag ' . $u['name'] . ',';
    $rolle = ROLE_LABELS[$u['role']] ?? $u['role'];
    $subject = 'Ihr Zugang zum Eingabebereich' . ($company !== '' ? " – $company" : '');
    $pwSatz = $startPw !== null
        ? 'Bei der ersten Anmeldung legen Sie ein eigenes Passwort fest; das Startpasswort gilt danach nicht mehr.'
        : (!empty($u['mustChange']) ? 'Ihr Startpasswort erhalten Sie separat. Bei der ersten Anmeldung legen Sie ein eigenes Passwort fest.' : 'Ihr Passwort erhalten Sie separat.');
    $intro = "für Sie wurde ein Zugang zum Eingabebereich des Wochenangebots eingerichtet (Rolle: $rolle).";
    $sig = mail_settings()['signature'];
    $foot = "Diese E-Mail wurde von $company über den Eingabebereich versendet. Falls Sie keinen Zugang erwartet haben, wenden Sie sich bitte an Ihren Administrator.";
    $t = "$gruss\n\n$intro\n\n" . ($note !== '' ? $note . "\n\n" : '')
       . "Adresse:       $url\nBenutzername:  {$u['username']}\n" . ($startPw !== null ? "Startpasswort: $startPw\n" : '')
       . "\n$pwSatz\nBitte geben Sie Ihr Passwort nicht weiter.\n\n$sig\n\n-- \n$foot\n";
    $row = function (string $k, string $v, bool $mono = false) {
        return '<tr><td style="padding:6px 14px 6px 0;color:#857c72;white-space:nowrap;vertical-align:top;">' . mail_h($k) . '</td><td style="padding:6px 0;font-weight:600;'
            . ($mono ? 'font-family:Consolas,Menlo,monospace;font-size:15px;letter-spacing:.02em;' : '') . '">' . mail_h($v) . '</td></tr>';
    };
    $h = '<p style="margin:0 0 14px;">' . mail_h($gruss) . '</p><p style="margin:0 0 14px;">' . mail_h($intro) . '</p>'
       . ($note !== '' ? '<p style="margin:0 0 14px;padding:12px 14px;background:#f7efe9;border-radius:8px;">' . nl2br(mail_h($note)) . '</p>' : '')
       . '<table role="presentation" cellpadding="0" cellspacing="0" style="font-size:14px;margin:0 0 14px;border-collapse:collapse;">'
       . $row('Benutzername', $u['username'], true) . ($startPw !== null ? $row('Startpasswort', $startPw, true) : '') . '</table>'
       . mail_button($url, 'Zum Eingabebereich')
       . '<p style="margin:12px 0 6px;">' . mail_h($pwSatz) . '</p><p style="margin:0 0 14px;font-size:12.5px;color:#857c72;">Bitte geben Sie Ihr Passwort nicht weiter.</p>';
    return [$subject, $t, mail_layout($subject, $h, $sig, $foot)];
}

