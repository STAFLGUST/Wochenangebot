<?php
/*
 * E-Mail-Versand über einen SMTP-Server (z. B. das IONOS-Postfach der Firma).
 * Zugangsdaten entweder im Eingabebereich (Verwaltung → E-Mail; Passwort verschlüsselt im Datenordner, der Schlüssel
 * liegt getrennt davon und wird nicht mitgesichert) oder als Umgebungsvariablen aus .env (docker-compose.yml).
 * Im Eingabebereich gespeicherte Werte haben Vorrang. Nie im Code.
 *
 *   MAIL_SMTP_HOST     z. B. smtp.ionos.de
 *   MAIL_SMTP_PORT     587 (STARTTLS) oder 465 (SSL)
 *   MAIL_SMTP_SECURE   starttls | ssl   (none nur für einen Server auf demselben Rechner, z. B. Tests)
 *   MAIL_SMTP_USER     Benutzername des Postfachs (meist die E-Mail-Adresse)
 *   MAIL_SMTP_PASS     Passwort des Postfachs
 *   MAIL_FROM          Absenderadresse, z. B. angebot@standard-fleisch.de
 *   MAIL_FROM_NAME     Absendername (Voreinstellung: Firmenname)
 *   MAIL_REPLY_TO      optional: Antworten an diese Adresse
 *   MAIL_SMTP_CAFILE   optional: eigene Zertifizierungsstelle (nur für interne Server/Tests)
 *   WA_URL             optional: Adresse der Seite für Links; sonst https://DOMAIN
 *
 * Zwei Postfächer (seit 29.10.2026): das Postfach für Kunden-E-Mails (oben, Dokument „mailkonto“ oder .env) und optional
 * ein eigenes Postfach für interne E-Mails (Dokument „mailkonto-intern“, nur im Eingabebereich), z. B.
 * verwaltung@dashboard-stafl.de. Intern = alles, was nur an Mitarbeiter geht: Zugangsdaten, Benachrichtigungen,
 * Einkaufsbedarf, Bestellwünsche an das Team, Notfall/Probealarm und die E-Mails der zentralen Anmeldung (Keycloak).
 * Ohne eigenes internes Postfach gilt das Kunden-Postfach (mail_cfg_intern() fällt darauf zurück).
 */
declare(strict_types=1);
if (realpath((string)($_SERVER['SCRIPT_FILENAME'] ?? '')) === __FILE__) { http_response_code(404); exit; }

function env_str(string $k): string
{
    $v = getenv($k);
    if ($v === false) $v = (string)($_SERVER[$k] ?? '');
    return trim((string)$v);
}
/* ---------- Verschlüsselung des gespeicherten Postfach-Passworts ---------- */
const MAIL_KEY_STORE = 'mail-schluessel';     // wird bei der Datensicherung bewusst ausgelassen (deploy/sichern.sh)
function mail_key(bool $create = false): ?string
{
    $k = store_read(MAIL_KEY_STORE);
    $raw = is_array($k) ? base64_decode((string)($k['key'] ?? ''), true) : false;
    if (is_string($raw) && strlen($raw) === SODIUM_CRYPTO_SECRETBOX_KEYBYTES) return $raw;
    if (!$create) return null;
    $raw = sodium_crypto_secretbox_keygen();
    store_write(MAIL_KEY_STORE, ['key' => base64_encode($raw), 'created' => gmdate('Y-m-d\TH:i:s\Z')]);
    return $raw;
}
function mail_encrypt(string $plain): string
{
    if (!function_exists('sodium_crypto_secretbox')) throw new RuntimeException('Verschlüsselung (sodium) ist auf dem Server nicht verfügbar.');
    $n = random_bytes(SODIUM_CRYPTO_SECRETBOX_NONCEBYTES);
    return 'v1:' . base64_encode($n . sodium_crypto_secretbox($plain, $n, mail_key(true)));
}
function mail_decrypt(string $enc): ?string
{
    $key = function_exists('sodium_crypto_secretbox_open') ? mail_key() : null;
    $raw = strpos($enc, 'v1:') === 0 ? base64_decode(substr($enc, 3), true) : false;
    if (!$key || !is_string($raw) || strlen($raw) <= SODIUM_CRYPTO_SECRETBOX_NONCEBYTES) return null;
    $p = sodium_crypto_secretbox_open(substr($raw, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES), substr($raw, 0, SODIUM_CRYPTO_SECRETBOX_NONCEBYTES), $key);
    return $p === false ? null : $p;
}
/* Im Eingabebereich gespeichertes Postfach (oder null); $konto 'kunden' (Standard) oder 'intern' */
const MAIL_KONTEN = ['kunden' => 'mailkonto', 'intern' => 'mailkonto-intern'];
function mail_account(string $konto = 'kunden'): ?array
{
    $a = $konto === 'intern' ? store_read('mailkonto-intern') : store_read('mailkonto');
    return is_array($a) && !empty($a['host']) && !empty($a['from']) ? $a : null;
}
/* Versanddaten aus einem gespeicherten Postfach (Passwort entschlüsselt; passError, wenn das nicht geht) */
function mail_cfg_aus_konto(array $a, string $source): array
{
    global $CFG;
    $pass = isset($a['passEnc']) && $a['passEnc'] !== '' ? mail_decrypt((string)$a['passEnc']) : '';
    return [
        'host' => (string)$a['host'], 'port' => (int)$a['port'], 'secure' => (string)$a['secure'],
        'user' => (string)($a['user'] ?? ''), 'pass' => (string)$pass, 'passError' => $pass === null,
        'from' => (string)$a['from'], 'fromName' => mail_clean_header((string)($a['fromName'] ?? '') ?: (string)$CFG['company']),
        'replyTo' => (string)($a['replyTo'] ?? ''), 'cafile' => env_str('MAIL_SMTP_CAFILE'), 'source' => $source,
    ];
}
/* Anzeige eines gespeicherten Postfachs für die Verwaltung – nie das Passwort, nur ob eines gespeichert ist */
function mail_konto_view(?array $a): ?array
{
    return $a ? ['host' => $a['host'], 'port' => (int)$a['port'], 'secure' => $a['secure'], 'user' => $a['user'] ?? '', 'from' => $a['from'], 'fromName' => $a['fromName'] ?? '',
                 'replyTo' => $a['replyTo'] ?? '', 'password' => !empty($a['passEnc']), 'updatedAt' => $a['updatedAt'] ?? null, 'updatedBy' => $a['updatedBy'] ?? ''] : null;
}
/* Versand für interne E-Mails (nur an Mitarbeiter): eigenes Postfach, sonst das Kunden-Postfach (oder null) */
function mail_cfg_intern(): ?array
{
    $a = mail_account('intern');
    return $a ? mail_cfg_aus_konto($a, 'intern') : mail_cfg();
}
/* Mail-Konfiguration oder null, wenn der Versand nicht eingerichtet ist */
function mail_cfg(): ?array
{
    global $CFG;
    if (function_exists('testumgebung') && testumgebung() && !mail_account() && env_str('MAIL_SMTP_HOST') === '') {
        return ['host' => 'testpostfach', 'port' => 0, 'secure' => 'none', 'user' => '', 'pass' => '', 'passError' => false, 'from' => 'test@example.invalid',
                'fromName' => (string)$CFG['company'], 'replyTo' => '', 'cafile' => '', 'source' => 'test'];
    }
    $a = mail_account();
    if ($a) return mail_cfg_aus_konto($a, 'admin');
    $host = env_str('MAIL_SMTP_HOST');
    $from = env_str('MAIL_FROM');
    if ($host === '' || $from === '' || filter_var($from, FILTER_VALIDATE_EMAIL) === false) return null;
    $secure = strtolower(env_str('MAIL_SMTP_SECURE')) ?: 'starttls';
    if (!in_array($secure, ['starttls', 'ssl', 'none'], true)) $secure = 'starttls';
    $port = (int)(env_str('MAIL_SMTP_PORT') ?: ($secure === 'ssl' ? 465 : 587));
    $reply = env_str('MAIL_REPLY_TO');
    return [
        'host' => $host, 'port' => $port, 'secure' => $secure,
        'user' => env_str('MAIL_SMTP_USER'), 'pass' => (string)(getenv('MAIL_SMTP_PASS') ?: ($_SERVER['MAIL_SMTP_PASS'] ?? '')),
        'from' => $from, 'fromName' => mail_clean_header(env_str('MAIL_FROM_NAME') ?: (string)$CFG['company']),
        'replyTo' => filter_var($reply, FILTER_VALIDATE_EMAIL) ? $reply : '',
        'cafile' => env_str('MAIL_SMTP_CAFILE'), 'passError' => false, 'source' => 'env',
    ];
}
/* Basisadresse der Angebotsseite für Links in E-Mails – nie aus dem Host-Header der Anfrage */
function mail_base_url(): ?string
{
    $u = rtrim(env_str('WA_URL'), '/');
    if ($u === '') { $d = env_str('DOMAIN'); if ($d !== '' && preg_match('/^[a-z0-9.-]+$/i', $d)) $u = 'https://' . strtolower($d); }
    return preg_match('#^https?://[a-z0-9.-]+(:\d+)?(/[a-z0-9._/-]*)?$#i', $u) ? $u : null;
}
function mail_clean_header(string $s): string { return trim(preg_replace('/[\r\n\t\x00-\x1f]+/', ' ', $s) ?? ''); }
function mail_enc_header(string $s): string
{
    $s = mail_clean_header($s);
    return preg_match('/^[\x20-\x7e]*$/', $s) ? $s : '=?UTF-8?B?' . base64_encode($s) . '?=';
}
function mail_addr(string $email, string $name = ''): string
{
    $email = mail_clean_header($email);
    if ($name === '') return '<' . $email . '>';
    $n = mail_clean_header($name);
    $n = preg_match('/^[A-Za-z0-9 .\'-]*$/', $n) ? '"' . $n . '"' : mail_enc_header($n);
    return $n . ' <' . $email . '>';
}
/* Vollständige Nachricht (Text + HTML), optional mit Anhängen [{name, type, data}] (dann multipart/mixed) */
function mail_build(array $cfg, string $to, string $toName, string $subject, string $text, string $html, array $extra = [], array $anhaenge = []): string
{
    $b = 'wa' . bin2hex(random_bytes(12));
    $dom = substr(strrchr($cfg['from'], '@'), 1) ?: 'localhost';
    $h = [
        'Date: ' . date('r'),
        'From: ' . mail_addr($cfg['from'], $cfg['fromName']),
        'To: ' . mail_addr($to, $toName),
        'Subject: ' . mail_enc_header($subject),
        'Message-ID: <' . bin2hex(random_bytes(16)) . '@' . $dom . '>',
        'MIME-Version: 1.0',
    ];
    $m = 'wm' . bin2hex(random_bytes(12));
    $h[] = $anhaenge ? 'Content-Type: multipart/mixed; boundary="' . $m . '"' : 'Content-Type: multipart/alternative; boundary="' . $b . '"';
    if ($cfg['replyTo'] !== '') $h[] = 'Reply-To: ' . mail_addr($cfg['replyTo']);
    foreach ($extra as $k => $v) if (preg_match('/^[A-Za-z-]+$/', (string)$k)) $h[] = $k . ': ' . mail_clean_header((string)$v);
    $part = function (string $type, string $body) use ($b) {
        return "--$b\r\nContent-Type: $type; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n" . rtrim(chunk_split(base64_encode($body), 76, "\r\n")) . "\r\n";
    };
    $alt = $part('text/plain', $text) . $part('text/html', $html) . "--$b--\r\n";
    if (!$anhaenge) return implode("\r\n", $h) . "\r\n\r\n" . $alt;
    $body = "--$m\r\nContent-Type: multipart/alternative; boundary=\"$b\"\r\n\r\n" . $alt;
    foreach ($anhaenge as $a) {
        $name = preg_replace('/[^A-Za-z0-9._-]/', '_', (string)$a['name']) ?: 'anhang';
        $type = preg_match('#^[a-z]+/[a-z0-9.+-]+$#', (string)$a['type']) ? $a['type'] : 'application/octet-stream';
        $body .= "--$m\r\nContent-Type: $type; name=\"$name\"\r\nContent-Disposition: attachment; filename=\"$name\"\r\nContent-Transfer-Encoding: base64\r\n\r\n"
               . rtrim(chunk_split(base64_encode((string)$a['data']), 76, "\r\n")) . "\r\n";
    }
    return implode("\r\n", $h) . "\r\n\r\n" . $body . "--$m--\r\n";
}

/* Schlanker SMTP-Client: eine Verbindung für mehrere Nachrichten */
final class Smtp
{
    private $fh = null;
    private array $cfg;
    public function __construct(array $cfg)
    {
        if (function_exists('testumgebung') && testumgebung()) throw new RuntimeException('In der Testumgebung wird kein Mailserver verwendet – E-Mails landen im Testpostfach.');
        $this->cfg = $cfg;
    }

    private function err(string $m): void { throw new RuntimeException($m); }
    private function read(): array
    {
        $lines = [];
        while (true) {
            $l = fgets($this->fh, 2048);
            if ($l === false) $this->err('Der Mailserver hat die Verbindung beendet.');
            $lines[] = rtrim($l, "\r\n");
            if (strlen($l) < 4 || $l[3] !== '-') break;
        }
        return [(int)substr($lines[0], 0, 3), $lines];
    }
    private function cmd(string $c, array $ok, string $what): array
    {
        fwrite($this->fh, $c . "\r\n");
        [$code, $lines] = $this->read();
        if (!in_array($code, $ok, true)) $this->err($what . ' – Antwort des Mailservers: ' . mb_substr(implode(' ', $lines), 0, 200));
        return $lines;
    }
    private function ctx()
    {
        $ssl = ['verify_peer' => true, 'verify_peer_name' => true, 'peer_name' => $this->cfg['host'], 'SNI_enabled' => true];
        if ($this->cfg['cafile'] !== '') $ssl['cafile'] = $this->cfg['cafile'];
        return stream_context_create(['ssl' => $ssl]);
    }
    public function open(): void
    {
        if (!empty($this->cfg['passError'])) $this->err('Das gespeicherte Postfach-Passwort kann nicht entschlüsselt werden (z. B. nach einer Wiederherstellung). Bitte unter Verwaltung → E-Mail neu eingeben.');
        try { $this->connect(); } catch (RuntimeException $e) { if ($this->fh) @fclose($this->fh); $this->fh = null; throw $e; }
    }
    private function connect(): void
    {
        $c = $this->cfg;
        if ($c['secure'] === 'none' && !in_array($c['host'], ['127.0.0.1', 'localhost', '::1'], true)) $this->err('Unverschlüsselter Versand ist nur an einen Server auf demselben Rechner erlaubt (MAIL_SMTP_SECURE).');
        $target = ($c['secure'] === 'ssl' ? 'ssl://' : 'tcp://') . $c['host'] . ':' . $c['port'];
        $fh = @stream_socket_client($target, $no, $str, 20, STREAM_CLIENT_CONNECT, $this->ctx());
        if (!$fh) $this->err("Keine Verbindung zum Mailserver {$c['host']}:{$c['port']} ($str).");
        $this->fh = $fh;
        stream_set_timeout($fh, 30);
        [$code, $lines] = $this->read();
        if ($code !== 220) $this->err('Mailserver nicht bereit: ' . mb_substr(implode(' ', $lines), 0, 200));
        $ehlo = 'EHLO ' . (preg_replace('/[^a-z0-9.-]/i', '', (string)gethostname()) ?: 'localhost');
        $caps = $this->cmd($ehlo, [250], 'Begrüßung');
        if ($c['secure'] === 'starttls') {
            if (!preg_grep('/^250[ -]STARTTLS/i', $caps)) $this->err('Der Mailserver bietet keine Verschlüsselung (STARTTLS) an.');
            $this->cmd('STARTTLS', [220], 'Verschlüsselung');
            if (!@stream_socket_enable_crypto($fh, true, STREAM_CRYPTO_METHOD_TLSv1_2_CLIENT | STREAM_CRYPTO_METHOD_TLSv1_3_CLIENT)) $this->err('Verschlüsselte Verbindung zum Mailserver fehlgeschlagen (Zertifikat?).');
            $caps = $this->cmd($ehlo, [250], 'Begrüßung');
        }
        if ($c['user'] !== '') {
            $auth = implode(' ', preg_grep('/^250[ -]AUTH/i', $caps) ?: []);
            if (stripos($auth, 'PLAIN') !== false) {
                $this->cmd('AUTH PLAIN ' . base64_encode("\0" . $c['user'] . "\0" . $c['pass']), [235], 'Anmeldung am Mailserver fehlgeschlagen');
            } else {
                $this->cmd('AUTH LOGIN', [334], 'Anmeldung am Mailserver');
                $this->cmd(base64_encode($c['user']), [334], 'Anmeldung am Mailserver');
                $this->cmd(base64_encode($c['pass']), [235], 'Anmeldung am Mailserver fehlgeschlagen');
            }
        }
    }
    public function send(string $to, string $message): void
    {
        if (!$this->fh) $this->open();
        $to = mail_clean_header($to);
        if (filter_var($to, FILTER_VALIDATE_EMAIL) === false) $this->err('Ungültige Empfängeradresse.');
        try {
            $this->cmd('MAIL FROM:<' . $this->cfg['from'] . '>', [250], 'Absender abgelehnt');
            $this->cmd('RCPT TO:<' . $to . '>', [250, 251], 'Empfänger abgelehnt');
            $this->cmd('DATA', [354], 'Versand abgelehnt');
            $data = preg_replace('/^\./m', '..', $message);                 // Punkt am Zeilenanfang verdoppeln
            fwrite($this->fh, $data . "\r\n.\r\n");
            [$code, $lines] = $this->read();
            if ($code !== 250) $this->err('Nachricht abgelehnt – Antwort des Mailservers: ' . mb_substr(implode(' ', $lines), 0, 200));
        } catch (RuntimeException $e) {
            try { if ($this->fh) { fwrite($this->fh, "RSET\r\n"); $this->read(); } } catch (Throwable $x) { $this->close(); }
            throw $e;
        }
    }
    public function close(): void
    {
        if ($this->fh) { @fwrite($this->fh, "QUIT\r\n"); @fclose($this->fh); }
        $this->fh = null;
    }
}

/* ---------- Vorlagen ---------- */
function mail_h(string $s): string { return htmlspecialchars($s, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
function mail_layout(string $title, string $bodyHtml, string $signature, string $footer, string $footHtml = ''): string
{
    $sig = nl2br(mail_h($signature));
    $foot = mail_h($footer);
    return '<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' . mail_h($title) . '</title></head>'
        . '<body style="margin:0;padding:0;background:#f4f1ec;font-family:Arial,Helvetica,sans-serif;color:#1d1a17;">'
        . '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1ec;padding:24px 12px;"><tr><td align="center">'
        . '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:12px;border:1px solid #e6e0d8;">'
        . '<tr><td style="padding:22px 28px 0;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#7b1e2b;font-weight:bold;">' . mail_h(mail_cfg()['fromName'] ?? '') . '</td></tr>'
        . '<tr><td style="padding:10px 28px 24px;font-size:15px;line-height:1.55;">' . $bodyHtml
        . ($sig !== '' ? '<p style="margin:22px 0 0;color:#4a443e;">' . $sig . '</p>' : '') . '</td></tr></table>'
        . ($foot !== '' ? '<p style="max-width:560px;margin:14px auto 0;font-size:12px;line-height:1.5;color:#857c72;">' . $foot . '</p>' : '')
        . $footHtml
        . '</td></tr></table></body></html>';
}
/* Einladungen und Passwort-Links: gleiche Farben wie mail_layout, dazu dunkles Kopfband, große Überschrift, hervorgehobener
   Knopf und kurze Schritte. Nur Tabellen und Inline-Stile (Outlook, Gmail, Apple Mail), keine Bilder (nichts wird
   nachgeladen, kein Zählpixel). $schritte: kurze Texte, nummeriert untereinander (auch auf schmalen Bildschirmen lesbar). */
function mail_layout_einladung(string $title, string $bereich, string $ueberschrift, string $bodyHtml, string $signature, string $footer, array $schritte = []): string
{
    $sig = nl2br(mail_h($signature));
    $foot = mail_h($footer);
    global $CFG;
    $absender = mail_h((string)((mail_cfg()['fromName'] ?? '') ?: ($CFG['company'] ?? '')));
    $st = '';
    foreach (array_values($schritte) as $i => $s) {
        $st .= '<tr><td width="34" valign="top" style="padding:0 0 10px;"><div style="width:24px;height:24px;line-height:24px;border-radius:12px;background:#f1e7e3;color:#7b1e2b;font-size:13px;font-weight:bold;text-align:center;">' . ($i + 1) . '</div></td>'
            . '<td valign="top" style="padding:2px 0 10px;font-size:14px;line-height:1.45;color:#4a443e;">' . mail_h($s) . '</td></tr>';
    }
    return '<!doctype html><html lang="de"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="color-scheme" content="light"><title>' . mail_h($title) . '</title></head>'
        . '<body style="margin:0;padding:0;background:#f4f1ec;font-family:Arial,Helvetica,sans-serif;color:#1d1a17;">'
        . '<div style="display:none;max-height:0;overflow:hidden;opacity:0;">' . mail_h($ueberschrift) . '</div>'
        . '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f1ec;padding:28px 12px;"><tr><td align="center">'
        . '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:560px;background:#ffffff;border-radius:16px;border:1px solid #e6e0d8;overflow:hidden;">'
        . '<tr><td style="background:#1d1a17;padding:18px 28px;"><table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>'
        . '<td style="font-size:13px;letter-spacing:.12em;text-transform:uppercase;color:#ffffff;font-weight:bold;">' . $absender . '</td>'
        . '<td align="right" style="font-size:12px;color:#c9bfb4;">' . mail_h($bereich) . '</td></tr></table></td></tr>'
        . '<tr><td style="height:4px;background:#7b1e2b;font-size:0;line-height:0;">&nbsp;</td></tr>'
        . '<tr><td style="padding:30px 28px 8px;"><h1 style="margin:0;font-size:24px;line-height:1.25;font-weight:bold;color:#1d1a17;">' . mail_h($ueberschrift) . '</h1></td></tr>'
        . '<tr><td style="padding:14px 28px 6px;font-size:15px;line-height:1.6;">' . $bodyHtml . '</td></tr>'
        . ($st !== '' ? '<tr><td style="padding:10px 28px 4px;"><div style="border-top:1px solid #eee7df;padding-top:18px;font-size:12px;letter-spacing:.08em;text-transform:uppercase;color:#857c72;font-weight:bold;margin-bottom:12px;">So geht es weiter</div>'
            . '<table role="presentation" cellpadding="0" cellspacing="0">' . $st . '</table></td></tr>' : '')
        . ($sig !== '' ? '<tr><td style="padding:12px 28px 28px;font-size:15px;line-height:1.55;color:#4a443e;">' . $sig . '</td></tr>' : '<tr><td style="height:16px;"></td></tr>')
        . '</table>'
        . ($foot !== '' ? '<p style="max-width:560px;margin:16px auto 0;font-size:12px;line-height:1.5;color:#857c72;">' . $foot . '</p>' : '')
        . '</td></tr></table></body></html>';
}
/* Großer Knopf (Einladung): volle Breite auf schmalen Bildschirmen über max-width, sonst so breit wie der Text */
function mail_button_gross(string $url, string $label): string
{
    return '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:22px 0 10px;"><tr><td style="border-radius:10px;background:#7b1e2b;">'
        . '<a href="' . mail_h($url) . '" style="display:inline-block;padding:14px 28px;color:#ffffff;text-decoration:none;font-weight:bold;font-size:16px;letter-spacing:.01em;">' . mail_h($label) . ' &rarr;</a></td></tr></table>';
}
/* Hervorgehobene Angabe (z. B. Benutzerkennung) */
function mail_feld(string $label, string $wert): string
{
    return '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:18px 0 4px;"><tr><td style="background:#f6f3ef;border:1px solid #eee7df;border-radius:10px;padding:12px 16px;">'
        . '<div style="font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:#857c72;margin-bottom:4px;">' . mail_h($label) . '</div>'
        . '<div style="font-family:Menlo,Consolas,\'Courier New\',monospace;font-size:17px;font-weight:bold;color:#1d1a17;">' . mail_h($wert) . '</div></td></tr></table>';
}
function mail_button(string $url, string $label): string
{
    return '<table role="presentation" cellpadding="0" cellspacing="0" style="margin:8px 0;"><tr><td style="border-radius:8px;background:#7b1e2b;">'
        . '<a href="' . mail_h($url) . '" style="display:inline-block;padding:11px 20px;color:#ffffff;text-decoration:none;font-weight:bold;font-size:15px;">' . mail_h($label) . '</a></td></tr></table>';
}
function mail_greeting(array $c): string
{
    $n = trim((string)($c['ansprechpartner'] ?? ''));
    return $n !== '' ? 'Guten Tag ' . $n . ',' : 'Guten Tag,';
}
