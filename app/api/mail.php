<?php
/*
 * E-Mail-Versand über einen SMTP-Server (z. B. das IONOS-Postfach der Firma).
 * Zugangsdaten nur als Umgebungsvariablen (aus .env auf dem Server, siehe docker-compose.yml) – nie im Code.
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
 */
declare(strict_types=1);
if (realpath((string)($_SERVER['SCRIPT_FILENAME'] ?? '')) === __FILE__) { http_response_code(404); exit; }

function env_str(string $k): string
{
    $v = getenv($k);
    if ($v === false) $v = (string)($_SERVER[$k] ?? '');
    return trim((string)$v);
}
/* Mail-Konfiguration oder null, wenn der Versand nicht eingerichtet ist */
function mail_cfg(): ?array
{
    global $CFG;
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
        'cafile' => env_str('MAIL_SMTP_CAFILE'),
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
/* Vollständige Nachricht (Text + HTML) */
function mail_build(array $cfg, string $to, string $toName, string $subject, string $text, string $html): string
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
        'Content-Type: multipart/alternative; boundary="' . $b . '"',
    ];
    if ($cfg['replyTo'] !== '') $h[] = 'Reply-To: ' . mail_addr($cfg['replyTo']);
    $part = function (string $type, string $body) use ($b) {
        return "--$b\r\nContent-Type: $type; charset=UTF-8\r\nContent-Transfer-Encoding: base64\r\n\r\n" . rtrim(chunk_split(base64_encode($body), 76, "\r\n")) . "\r\n";
    };
    return implode("\r\n", $h) . "\r\n\r\n" . $part('text/plain', $text) . $part('text/html', $html) . "--$b--\r\n";
}

/* Schlanker SMTP-Client: eine Verbindung für mehrere Nachrichten */
final class Smtp
{
    private $fh = null;
    private array $cfg;
    public function __construct(array $cfg) { $this->cfg = $cfg; }

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
function mail_layout(string $title, string $bodyHtml, string $signature, string $footer): string
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
        . '</td></tr></table></body></html>';
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
