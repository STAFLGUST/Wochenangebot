<?php
declare(strict_types=1);
/* E-Mails an Kunden, Abmelden, Bestellwunsch-Vorlagen, Einmal-Links, Versand */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* ---------------- E-Mail an Kunden ---------------- */
const TOKEN_DAYS = ['invite' => 7, 'reset' => 2];
function mail_settings(): array
{
    global $CFG;
    $d = store_read('mailvorlage');
    return is_array($d) ? $d + ['signature' => ''] : ['signature' => "Mit freundlichen Grüßen\n" . $CFG['company']];
}
function require_mail(): array
{
    $m = mail_cfg();
    if (!$m) fail('Der E-Mail-Versand ist noch nicht eingerichtet (Zugangsdaten des Postfachs in .env auf dem Server).', 409);
    if (!mail_base_url()) fail('Die Adresse der Angebotsseite für Links fehlt (DOMAIN bzw. WA_URL in .env).', 409);
    return $m;
}
function mail_week(): ?array
{
    $o = store_read('angebot');
    $w = (int)($o['meta']['week'] ?? 0); $y = (int)($o['meta']['year'] ?? 0);
    if (!$o || $w < 1 || $y < 2000) return null;
    $mo = (new DateTimeImmutable())->setISODate($y, $w);
    return ['week' => $w, 'year' => $y, 'from' => $mo->format('d.m.'), 'to' => $mo->modify('+6 days')->format('d.m.Y'), 'publishedAt' => $o['publishedAt'] ?? null];
}
function mail_offer_links(array $c): array
{
    $base = mail_base_url();
    $out = [];
    foreach (customer_offers($c) as $id) { $d = offer_def($id); if ($d) $out[] = [$d['name'], $base . '/' . ($id === OFFER_STD ? '' : '?angebot=' . rawurlencode($id))]; }
    return $out;
}
function mail_footer(string $kind): string
{
    global $CFG;
    return $kind === 'angebot'
        ? "Sie erhalten diese E-Mail als Kunde von {$CFG['company']}. Sie können das Wochenangebot per E-Mail jederzeit mit einem Klick abbestellen – Ihr Zugang zum Angebotsportal bleibt davon unberührt."
        : "Diese E-Mail wurde von {$CFG['company']} über das Angebotsportal versendet. Falls Sie keinen Zugang erwartet haben, können Sie sie ignorieren.";
}
/* ---------- Abmelden vom Wochenangebot ----------
   Fester Abmeldecode je Kunde: HMAC über die Kundennummer mit einem geheimen Schlüssel (wird mitgesichert,
   damit Links in alten E-Mails nach einer Wiederherstellung weiter funktionieren). Kein Login nötig. */
function abmelde_key(): string
{
    $k = store_read('abmelde-schluessel');
    $raw = is_array($k) ? base64_decode((string)($k['key'] ?? ''), true) : false;
    if (is_string($raw) && strlen($raw) === 32) return $raw;
    return with_lock('abmelde-schluessel', function () {
        $k = store_read('abmelde-schluessel');
        $raw = is_array($k) ? base64_decode((string)($k['key'] ?? ''), true) : false;
        if (is_string($raw) && strlen($raw) === 32) return $raw;
        $raw = random_bytes(32);
        store_write('abmelde-schluessel', ['key' => base64_encode($raw), 'created' => now()]);
        return $raw;
    });
}
function abmelde_token(string $kid): string
{
    return $kid . '.' . substr(rtrim(strtr(base64_encode(hash_hmac('sha256', 'abmelden|' . $kid, abmelde_key(), true)), '+/', '-_'), '='), 0, 32);
}
function abmelde_kunde(string $tok): ?array
{
    if (!preg_match('/^(k[a-f0-9]{12})\.[A-Za-z0-9_-]{32}$/', $tok, $m) || !hash_equals(abmelde_token($m[1]), $tok)) return null;
    foreach (customers_load()['customers'] as $c) if ($c['id'] === $m[1]) return $c;
    return null;
}
function abmelde_url(array $c): string { return mail_base_url() . '/#abmelden=' . (!empty($c['id']) ? abmelde_token($c['id']) : 'BEISPIEL'); }
/* Abmelden/Wiederanmelden speichern; true, wenn sich der Status geändert hat */
function abmelde_setzen(array $c, bool $ab, string $via): bool
{
    return with_lock('kunden', function () use ($c, $ab, $via) {
        $d = customers_load();
        foreach ($d['customers'] as $i => $x) if ($x['id'] === $c['id']) {
            $was = !array_key_exists('mailAngebot', $x) || !empty($x['mailAngebot']);
            if ($was === !$ab) return false;
            $d['customers'][$i]['mailAngebot'] = !$ab;
            if ($ab) $d['customers'][$i]['abgemeldet'] = ['t' => now(), 'via' => $via];
            else unset($d['customers'][$i]['abgemeldet']);
            $d['rev'] = (int)$d['rev'] + 1;
            store_write('kunden', $d);
            return true;
        }
        return false;
    });
}
function abmelde_melden(array $c, bool $ab, string $via): void
{
    global $CFG;
    $who = ['username' => 'kunde:' . ($c['login']['username'] ?? $c['id']), 'name' => $c['firma'], 'role' => 'kunde'];
    $txt = $ab ? 'Kunde hat sich vom Wochenangebot per E-Mail abgemeldet' . ($via === '1klick' ? ' (Ein-Klick im E-Mail-Programm)' : '') : 'Kunde hat sich wieder für das Wochenangebot per E-Mail angemeldet';
    audit('kunde_abmeldung', $txt, [['k' => "c{$c['id']}|mailAngebot", 'code' => $c['nr'] ?? '', 'name' => $c['firma'], 'f' => 'Wochenangebot per E-Mail', 'from' => $ab ? 'ja' : 'nein', 'to' => $ab ? 'nein' : 'ja']], $who);
    // Hinweis an uns (Antwortadresse, sonst Absender) – Fehler dabei stören den Kunden nicht
    $cfg = mail_cfg();
    if (!$cfg || !mail_base_url()) return;
    $to = $cfg['replyTo'] ?: $cfg['from'];
    $sub = ($ab ? 'Abmeldung' : 'Wiederanmeldung') . " Wochenangebot: {$c['firma']}";
    $body = ($ab ? "{$c['firma']} hat sich vom Wochenangebot per E-Mail abgemeldet und erhält es nicht mehr." : "{$c['firma']} möchte das Wochenangebot wieder per E-Mail erhalten.")
        . "

Kundennummer: " . (($c['nr'] ?? '') ?: '–') . "
E-Mail: {$c['email']}
Zeit: " . date('d.m.Y, H:i') . " Uhr

Die E-Mail-Adresse bleibt in den Stammdaten gespeichert. Einladungen und Passwort-Links können weiterhin gesendet werden.
";
    $r = mail_send_many($cfg, [['to' => $to, 'name' => '', 'subject' => $sub, 'text' => $body, 'html' => mail_layout($sub, '<p style="margin:0;">' . nl2br(mail_h($body)) . '</p>', '', '')]])[0];
    with_lock('mailversand', function () use ($to, $r, $c) {
        $l = store_read('mailversand') ?? [];
        $l[] = ['t' => now(), 'typ' => 'hinweis', 'kid' => $c['id'], 'firma' => $c['firma'], 'to' => $to, 'ok' => $r['ok'], 'error' => $r['error'] ?? '', 'by' => 'automatisch'];
        store_write('mailversand', array_slice($l, -3000));
    });
}

/* ---------- Bestellwünsche ---------- */
function order_settings(): array
{
    $d = store_read('bestellung');
    return ['enabled' => !empty($d['enabled']), 'to' => array_values(array_filter((array)($d['to'] ?? []), 'is_string')), 'copy' => !is_array($d) || !array_key_exists('copy', $d) || !empty($d['copy']),
            'updatedAt' => $d['updatedAt'] ?? null, 'updatedBy' => $d['updatedBy'] ?? ''];
}
function order_enabled(): bool { $o = order_settings(); return $o['enabled'] && $o['to'] && mail_cfg() && mail_base_url(); }
function de_num(float $v, int $dec = 2): string { return number_format($v, $dec, ',', '.'); }
function de_qty(float $v): string { $s = number_format($v, 2, ',', '.'); return preg_replace('/,?0+$/', '', $s) ?: '0'; }
/* Mail an uns bzw. Kopie an den Kunden: [Betreff, Text, HTML] */
function mail_tpl_bestellung(array $o, bool $copy): array
{
    global $CFG;
    $c = $o['kunde'];
    $subject = $copy ? "Ihr Bestellwunsch {$o['nr']} – {$CFG['company']}" : "Bestellwunsch {$o['nr']} – {$c['firma']}" . ($o['week'] ? " (KW {$o['week']})" : '');
    $intro = $copy
        ? "vielen Dank für Ihren Bestellwunsch. Wir haben ihn erhalten und melden uns mit der Bestätigung bei Ihnen. Bitte beachten Sie: Erst mit unserer Bestätigung ist die Bestellung verbindlich."
        : "über das Angebotsportal ist ein neuer Bestellwunsch eingegangen.";
    $kopf = [['Bestellwunsch', $o['nr']], ['Eingang', date('d.m.Y, H:i', strtotime($o['t'])) . ' Uhr'], ['Angebot', $o['angebotName'] . ($o['week'] ? " · KW {$o['week']}/{$o['year']}" : '')]];
    if (!$copy) {
        $kopf[] = ['Kunde', $c['firma'] . ($c['nr'] ? " (Kd.-Nr. {$c['nr']})" : '')];
        if ($c['ansprechpartner']) $kopf[] = ['Ansprechpartner', $c['ansprechpartner']];
        $adr = trim(implode(', ', array_filter([$c['strasse'], trim($c['plz'] . ' ' . $c['ort'])])));
        if ($adr !== '') $kopf[] = ['Anschrift', $adr];
        if ($c['email']) $kopf[] = ['E-Mail', $c['email']];
        if ($c['telefon']) $kopf[] = ['Telefon', $c['telefon']];
        $kopf[] = ['Benutzerkennung', $c['username']];
    }
    if ($o['termin']) $kopf[] = ['Wunschtermin', date('d.m.Y', strtotime($o['termin']))];
    if ($o['referenz'] !== '') $kopf[] = ['Ihre Referenz', $o['referenz']];
    $pr = function ($p) { return $p['price'] !== null ? de_num($p['price']) . ' €/kg' : 'auf Anfrage'; };
    $sum = function ($p) { return $p['sum'] !== null ? de_num($p['sum']) . ' €' : '–'; };
    $t = ($copy ? mail_greeting($c) : 'Hallo,') . "\n\n" . $intro . "\n\n";
    foreach ($kopf as [$k, $v]) $t .= str_pad($k . ':', 18) . $v . "\n";
    $t .= "\nPositionen:\n";
    foreach ($o['positions'] as $i => $p) $t .= sprintf("%2d. %s%s – %s kg × %s = %s\n", $i + 1, $p['code'] ? $p['code'] . ' ' : '', $p['name'], de_qty($p['qty']), $pr($p), $sum($p));
    $t .= "\nGesamtmenge: " . de_qty($o['totalQty']) . " kg\nWarenwert (ca.): " . de_num($o['total']) . " €" . ($o['onRequest'] ? " zzgl. {$o['onRequest']} Position(en) mit Preis auf Anfrage" : '') . "\n";
    if ($o['bemerkung'] !== '') $t .= "\nBemerkung:\n{$o['bemerkung']}\n";
    $t .= "\nPreise laut Angebot (freibleibend, netto); abgerechnet wird nach tatsächlichem Gewicht.\n";
    if ($copy) $t .= "\n" . mail_settings()['signature'] . "\n";
    $row = function ($k, $v) { return '<tr><td style="padding:3px 12px 3px 0;color:#857c72;white-space:nowrap;vertical-align:top;">' . mail_h($k) . '</td><td style="padding:3px 0;">' . mail_h($v) . '</td></tr>'; };
    $h = '<p style="margin:0 0 14px;">' . mail_h($copy ? mail_greeting($c) : 'Hallo,') . '</p><p style="margin:0 0 14px;">' . mail_h($intro) . '</p>'
        . '<table role="presentation" cellpadding="0" cellspacing="0" style="font-size:14px;margin:0 0 16px;">' . implode('', array_map(function ($r) use ($row) { return $row($r[0], $r[1]); }, $kopf)) . '</table>';
    $th = 'style="text-align:left;padding:6px 6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;"';
    $thr = 'style="text-align:right;padding:6px 6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;"';
    $h .= '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:13.5px;border-collapse:collapse;"><tr><th ' . $th . '>Art.-Nr.</th><th ' . $th . '>Artikel</th><th ' . $thr . '>Menge</th><th ' . $thr . '>Preis</th><th ' . $thr . '>Summe</th></tr>';
    foreach ($o['positions'] as $p) {
        $td = 'style="padding:6px 6px;border-bottom:1px solid #eee8e1;vertical-align:top;"'; $tdr = 'style="padding:6px 6px;border-bottom:1px solid #eee8e1;text-align:right;white-space:nowrap;vertical-align:top;"';
        $h .= '<tr><td ' . $td . '>' . mail_h($p['code']) . '</td><td ' . $td . '>' . mail_h($p['name']) . ($p['group'] ? '<br><span style="font-size:11.5px;color:#857c72;">' . mail_h($p['group']) . '</span>' : '') . '</td><td ' . $tdr . '>' . de_qty($p['qty']) . ' kg</td><td ' . $tdr . '>' . mail_h($pr($p)) . '</td><td ' . $tdr . '>' . mail_h($sum($p)) . '</td></tr>';
    }
    $h .= '<tr><td colspan="2" style="padding:8px 6px;font-weight:bold;">Summe (ca.)</td><td style="padding:8px 6px;text-align:right;font-weight:bold;white-space:nowrap;">' . de_qty($o['totalQty']) . ' kg</td><td></td><td style="padding:8px 6px;text-align:right;font-weight:bold;white-space:nowrap;">' . de_num($o['total']) . ' €</td></tr></table>'
        . ($o['onRequest'] ? '<p style="margin:6px 0 0;font-size:12.5px;color:#857c72;">Zzgl. ' . $o['onRequest'] . ' Position(en) mit Preis auf Anfrage.</p>' : '')
        . ($o['bemerkung'] !== '' ? '<p style="margin:14px 0 0;padding:10px 12px;background:#f7efe9;border-radius:8px;"><strong>Bemerkung:</strong><br>' . nl2br(mail_h($o['bemerkung'])) . '</p>' : '')
        . '<p style="margin:14px 0 0;font-size:12.5px;color:#857c72;">Preise laut Angebot (freibleibend, netto); abgerechnet wird nach tatsächlichem Gewicht.</p>';
    return [$subject, $t, mail_layout($subject, $h, $copy ? mail_settings()['signature'] : '', $copy ? "Diese E-Mail bestätigt den Eingang Ihres Bestellwunsches bei {$CFG['company']}." : 'Automatisch erzeugt vom Angebotsportal. Antworten gehen direkt an den Kunden.')];
}

/* Wochenangebot / Angebotslink: [Betreff, Text, HTML] */
function mail_tpl_angebot(array $c, string $note, ?array $wk): array
{
    global $CFG;
    $links = mail_offer_links($c);
    $kw = $wk ? "KW {$wk['week']}/{$wk['year']}" : '';
    $subject = ($kw ? "Wochenangebot $kw" : 'Ihr Angebot') . ' – ' . $CFG['company'];
    $intro = $wk ? "unser Angebot für KW {$wk['week']} ({$wk['from']} – {$wk['to']}) ist online." : 'hier ist der Link zu Ihrem Angebot.';
    $user = $c['login']['username'] ?? '';
    $sig = mail_settings()['signature'];
    $t = mail_greeting($c) . "\n\n" . $intro . "\n\n" . ($note !== '' ? $note . "\n\n" : '');
    foreach ($links as [$n, $u]) $t .= "$n:\n$u\n\n";
    if ($user !== '') $t .= "Anmeldung mit Ihrer Benutzerkennung: $user\nPasswort vergessen? Antworten Sie einfach auf diese E-Mail.\n\n";
    $ab = abmelde_url($c);
    $t .= $sig . "\n\n-- \n" . mail_footer('angebot') . "\nVom Wochenangebot abmelden: $ab\n";
    $h = '<p style="margin:0 0 14px;">' . mail_h(mail_greeting($c)) . '</p><p style="margin:0 0 14px;">' . mail_h($intro) . '</p>'
        . ($note !== '' ? '<p style="margin:0 0 14px;padding:12px 14px;background:#f7efe9;border-radius:8px;">' . nl2br(mail_h($note)) . '</p>' : '');
    foreach ($links as [$n, $u]) $h .= mail_button($u, $n . ' ansehen');
    if ($user !== '') $h .= '<p style="margin:14px 0 0;font-size:13px;color:#4a443e;">Anmeldung mit Ihrer Benutzerkennung <strong>' . mail_h($user) . '</strong>. Passwort vergessen? Antworten Sie einfach auf diese E-Mail.</p>';
    $abBtn = '<p style="max-width:560px;margin:10px auto 0;text-align:center;"><a href="' . mail_h($ab) . '" style="display:inline-block;padding:7px 14px;border:1px solid #cfc6bb;border-radius:8px;color:#5f574f;font-size:12px;text-decoration:none;">Vom Wochenangebot abmelden</a></p>';
    return [$subject, $t, mail_layout($subject, $h, $sig, mail_footer('angebot'), $abBtn)];
}
/* Sonderposten eines Angebots – nur dessen Artikel und Preise: [Betreff, Text, HTML] */
function restposten_items(array $def): array
{
    $pub = store_read('angebot');
    if (!$pub) return [];
    $off = offer_resolve($pub, $def);
    return array_values(array_filter($off['items'], function ($it) { return !empty($it['sale']); }));
}
function mail_tpl_restposten(array $c, array $def, array $items, string $note): array
{
    global $CFG;
    $subject = 'Sonderposten – solange der Vorrat reicht – ' . $CFG['company'];
    $intro = 'folgende Artikel bieten wir Ihnen zum Sonderpreis an – nur solange der Vorrat reicht:';
    $url = mail_base_url() . '/' . ($def['id'] === OFFER_STD ? '' : '?angebot=' . rawurlencode($def['id']));
    $login = !empty($c['login']['active']) ? ($c['login']['username'] ?? '') : '';
    $sig = mail_settings()['signature'];
    $pr = function ($it) { return de_num((float)$it['price']['value']) . ' €/kg' . (isset($it['regular']) ? ' (statt ' . de_num((float)$it['regular']) . ' €/kg)' : ''); };
    $t = mail_greeting($c) . "\n\n" . $intro . "\n\n" . ($note !== '' ? $note . "\n\n" : '');
    foreach ($items as $it) $t .= '- ' . (($it['code'] ?? '') !== '' ? $it['code'] . ' ' : '') . $it['name'] . ': ' . $pr($it) . "\n";
    $t .= "\nPreise freibleibend, netto; abgerechnet wird nach tatsächlichem Gewicht.\n";
    if ($login !== '') $t .= "\nZum Angebot (Anmeldung mit Ihrer Benutzerkennung $login):\n$url\n";
    $ab = abmelde_url($c);
    $t .= "\n" . $sig . "\n\n-- \n" . mail_footer('angebot') . "\nVom Wochenangebot abmelden: $ab\n";
    $td = 'style="padding:7px 6px;border-bottom:1px solid #eee8e1;vertical-align:top;"';
    $tdr = 'style="padding:7px 6px;border-bottom:1px solid #eee8e1;text-align:right;white-space:nowrap;vertical-align:top;"';
    $th = 'style="text-align:left;padding:6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;"';
    $h = '<p style="margin:0 0 14px;">' . mail_h(mail_greeting($c)) . '</p><p style="margin:0 0 14px;">' . mail_h($intro) . '</p>'
        . ($note !== '' ? '<p style="margin:0 0 14px;padding:12px 14px;background:#f7efe9;border-radius:8px;">' . nl2br(mail_h($note)) . '</p>' : '')
        . '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:14px;border-collapse:collapse;margin:0 0 12px;"><tr><th ' . $th . '>Art.-Nr.</th><th ' . $th . '>Artikel</th><th style="text-align:right;padding:6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;">Sonderpreis</th></tr>';
    foreach ($items as $it) {
        $h .= '<tr><td ' . $td . '>' . mail_h((string)($it['code'] ?? '')) . '</td><td ' . $td . '>' . mail_h($it['name']) . '</td><td ' . $tdr . '><strong style="color:#b42318;">' . de_num((float)$it['price']['value']) . ' €/kg</strong>'
            . (isset($it['regular']) ? '<br><span style="font-size:12px;color:#857c72;text-decoration:line-through;">' . de_num((float)$it['regular']) . ' €/kg</span>' : '') . '</td></tr>';
    }
    $h .= '</table><p style="margin:0 0 14px;font-size:12.5px;color:#857c72;">Solange der Vorrat reicht. Preise freibleibend, netto; abgerechnet wird nach tatsächlichem Gewicht.</p>';
    if ($login !== '') $h .= mail_button($url, 'Zum Angebot') . '<p style="margin:8px 0 0;font-size:13px;color:#4a443e;">Anmeldung mit Ihrer Benutzerkennung <strong>' . mail_h($login) . '</strong>.</p>';
    $abBtn = '<p style="max-width:560px;margin:10px auto 0;text-align:center;"><a href="' . mail_h($ab) . '" style="display:inline-block;padding:7px 14px;border:1px solid #cfc6bb;border-radius:8px;color:#5f574f;font-size:12px;text-decoration:none;">Vom Wochenangebot abmelden</a></p>';
    return [$subject, $t, mail_layout($subject, $h, $sig, mail_footer('angebot'), $abBtn)];
}
/* Wer bekommt die Sonderposten eines Angebots? Nur Kunden, denen genau dieses Angebot freigeschaltet ist. */
function restposten_reason(array $c, string $oid): string
{
    if (!in_array($oid, customer_offers($c), true)) return 'Angebot nicht freigeschaltet';
    if (empty($c['active'])) return 'Kunde inaktiv';
    if (empty($c['email'])) return 'keine E-Mail-Adresse';
    if (array_key_exists('mailAngebot', $c) && empty($c['mailAngebot'])) return !empty($c['abgemeldet']) ? 'hat sich vom Wochenangebot abgemeldet' : 'Angebote per E-Mail nicht gewünscht';
    return '';
}
/* Einladung / Passwort zurücksetzen */
function mail_tpl_zugang(array $c, string $url, string $purpose, int $exp): array
{
    global $CFG;
    $inv = $purpose === 'invite';
    $subject = $inv ? "Ihr Zugang zum Angebotsportal von {$CFG['company']}" : "Passwort für Ihren Zugang neu festlegen – {$CFG['company']}";
    $until = date('d.m.Y, H:i', $exp) . ' Uhr';
    $user = $c['login']['username'];
    $lines = $inv
        ? ["für Sie ist ein Zugang zu unserem Angebotsportal eingerichtet. Dort sehen Sie jederzeit Ihr aktuelles Angebot.", "Ihre Benutzerkennung: $user", "Bitte legen Sie über den folgenden Link Ihr persönliches Passwort fest. Der Link ist bis $until gültig und kann nur einmal verwendet werden."]
        : ["für Ihren Zugang zu unserem Angebotsportal (Benutzerkennung: $user) wurde ein neues Passwort angefordert.", "Bitte legen Sie über den folgenden Link ein neues Passwort fest. Der Link ist bis $until gültig und kann nur einmal verwendet werden."];
    $sig = mail_settings()['signature'];
    $t = mail_greeting($c) . "\n\n" . implode("\n\n", $lines) . "\n\n" . $url . "\n\n" . $sig . "\n\n-- \n" . mail_footer('zugang') . "\n";
    $h = '<p style="margin:0 0 14px;">' . mail_h(mail_greeting($c)) . '</p>';
    foreach ($lines as $l) $h .= '<p style="margin:0 0 14px;">' . mail_h($l) . '</p>';
    $h .= mail_button($url, $inv ? 'Passwort festlegen' : 'Neues Passwort festlegen')
        . '<p style="margin:12px 0 0;font-size:12px;color:#857c72;word-break:break-all;">Falls die Schaltfläche nicht funktioniert: ' . mail_h($url) . '</p>';
    return [$subject, $t, mail_layout($subject, $h, $sig, mail_footer('zugang'))];
}
/* Einmal-Link erzeugen (gespeichert wird nur der Hash) */
function kunde_token_new(string $kid, string $purpose): array
{
    $tok = rtrim(strtr(base64_encode(random_bytes(32)), '+/', '-_'), '=');
    $exp = time() + 86400 * TOKEN_DAYS[$purpose];
    $c = with_lock('kunden', function () use ($kid, $tok, $exp, $purpose) {
        $d = customers_load();
        foreach ($d['customers'] as $i => $x) if ($x['id'] === $kid && !empty($x['login'])) {
            $d['customers'][$i]['login']['token'] = ['h' => hash('sha256', $tok), 'exp' => $exp, 'p' => $purpose, 't' => now()];
            store_write('kunden', $d);
            return $d['customers'][$i];
        }
        return null;
    });
    if (!$c) fail('Kunde oder Zugang nicht gefunden.', 404);
    return [$tok, $exp, $c];
}
function kunde_by_token(string $tok): ?array
{
    if (!preg_match('/^[A-Za-z0-9_-]{40,64}$/', $tok)) return null;
    $h = hash('sha256', $tok);
    foreach (customers_load()['customers'] as $c) {
        $t = $c['login']['token'] ?? null;
        if ($t && hash_equals((string)$t['h'], $h) && (int)$t['exp'] > time() && !empty($c['active']) && !empty($c['login']['active'])) return $c;
    }
    return null;
}
/* Mehrere Nachrichten über eine Verbindung; Ergebnis je Auftrag */
function mail_send_many(array $cfg, array $jobs): array
{
    $smtp = new Smtp($cfg);
    $res = [];
    try {
        foreach ($jobs as $k => $j) {
            try {
                $smtp->send($j['to'], mail_build($cfg, $j['to'], $j['name'] ?? '', $j['subject'], $j['text'], $j['html'], $j['headers'] ?? []));
                $res[$k] = ['ok' => true];
            } catch (RuntimeException $e) {
                $res[$k] = ['ok' => false, 'error' => $e->getMessage()];
                if (preg_match('/Verbindung|Anmeldung|Verschlüssel|nicht bereit|Begrüßung|nur an einen Server|entschlüsselt/', $e->getMessage())) {
                    foreach ($jobs as $k2 => $x) if (!isset($res[$k2])) $res[$k2] = ['ok' => false, 'error' => $e->getMessage()];
                    break;
                }
            }
        }
    } finally { $smtp->close(); }
    return $res;
}
/* Versand an Kunden vermerken (letzte E-Mail, Wochenversand) und ins Versandprotokoll schreiben */
function mail_record(array $entries, ?array $wk = null): void
{
    global $ME;
    with_lock('kunden', function () use ($entries, $wk) {
        $d = customers_load();
        foreach ($d['customers'] as $i => $c) foreach ($entries as $e) if ($e['kid'] === $c['id']) {
            $d['customers'][$i]['mailLast'] = ['typ' => $e['typ'], 't' => now(), 'ok' => $e['ok'], 'to' => $e['to']];
            if ($e['ok'] && $e['typ'] === 'woche' && $wk) $d['customers'][$i]['weekly'] = ['week' => $wk['week'], 'year' => $wk['year'], 't' => now()];
        }
        store_write('kunden', $d);
    });
    with_lock('mailversand', function () use ($entries, $ME) {
        $l = store_read('mailversand') ?? [];
        foreach ($entries as $e) $l[] = ['t' => now(), 'typ' => $e['typ'], 'kid' => $e['kid'], 'firma' => $e['firma'], 'to' => $e['to'], 'ok' => $e['ok'], 'error' => $e['error'] ?? '', 'by' => $ME['name'] ?? ''];
        store_write('mailversand', array_slice($l, -3000));
    });
}
const MAIL_TYP = ['woche' => 'Wochenangebot', 'angebot' => 'Angebotslink', 'invite' => 'Einladung', 'reset' => 'Passwort-Link', 'test' => 'Testmail', 'hinweis' => 'Hinweis Abmeldung', 'bestellung' => 'Bestellwunsch', 'bestellkopie' => 'Kopie Bestellwunsch', 'restposten' => 'Sonderposten'];
function mail_job_for(array $c, string $typ, string $note = '', ?array $wk = null): array
{
    if (empty($c['email'])) throw new InvalidArgumentException("Für „{$c['firma']}“ ist keine E-Mail-Adresse hinterlegt.");
    [$sub, $txt, $html] = mail_tpl_angebot($c, $note, $wk);
    // Ein-Klick-Abmeldung im E-Mail-Programm (RFC 8058) – erwartet u. a. von Gmail/Yahoo bei regelmäßigen Sendungen
    $one = mail_base_url() . '/api/?action=abmelden1&t=' . rawurlencode(abmelde_token($c['id']));
    return ['to' => $c['email'], 'name' => $c['ansprechpartner'] ?: $c['firma'], 'subject' => $sub, 'text' => $txt, 'html' => $html,
            'headers' => ['List-Unsubscribe' => '<' . $one . '>', 'List-Unsubscribe-Post' => 'List-Unsubscribe=One-Click']];
}
/* Kunde anmelden (nach Passwortprüfung oder Einmal-Link) */
function kunde_sign_in(array $c): void
{
    session_regenerate_id(true);
    kunde_clear();
    $_SESSION['kid'] = $c['id'];
    $_SESSION['ksv'] = (int)($c['login']['sv'] ?? 0);
    $_SESSION['kseen'] = time();
    $_SESSION['kcsrf'] = bin2hex(random_bytes(32));
    with_lock('kundensitzungen', function () use ($c) {
        $r = ksess_prune(store_read('kundensitzungen') ?? []);
        $sid = bin2hex(random_bytes(12));
        $r[$sid] = ['kid' => $c['id'], 'ip' => client_ip(), 'ua' => mb_substr((string)($_SERVER['HTTP_USER_AGENT'] ?? ''), 0, 240), 'created' => now(), 'seen' => time()];
        store_write('kundensitzungen', $r);
        $_SESSION['ksid'] = $sid;
    });
    $GLOBALS['KUNDE'] = $c;
}
