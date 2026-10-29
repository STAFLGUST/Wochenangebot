<?php
declare(strict_types=1);
/* Benachrichtigungen an Mitarbeiter (E-Mail): welche Ereignisse an wen gehen, legt der Administrator fest.
   Ereignisse werden während der Anfrage vorgemerkt und erst nach der Antwort versendet (nach dem Speichern;
   bei einem Abbruch mit Rücksetzen verworfen). Häufige Ereignisse werden gebündelt (Pause je Ereignis). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

/* Reihenfolge = Anzeige. 'fest': Empfänger gehören zur Bestellfunktion (an, solange sie eingeschaltet ist).
   'pause': Mindestabstand zwischen zwei E-Mails in Sekunden; dazwischen wird nur gezählt.
   'ersatz': ohne eigene Empfänger geht die E-Mail an die Antwortadresse des Postfachs (sonst den Absender);
   ohne gespeicherte Einstellung ist das Ereignis dann an (bisheriges Verhalten).
   'manuell': nur auf Knopfdruck (immer bereit, kein Schalter; versendet von der jeweiligen Aktion). */
const NOTIFY_EVENTS = [
    'bestellung' => ['label' => 'Neuer Bestellwunsch', 'text' => 'Ein angemeldeter Kunde sendet einen Bestellwunsch über das Portal (mit allen Positionen).', 'fest' => true, 'pause' => 0],
    'sicherheit' => ['label' => 'Sicherheitsereignisse', 'text' => 'Anmeldesperre nach Fehlversuchen, Administrator-Anmeldung von neuem Gerät, Passwort in Datenleck, Änderungen an Nutzern und Rollen, Zwei-Faktor, Sicherheitseinstellungen, Wartungsmodus.', 'fest' => false, 'pause' => 600],
    'einkauf' => ['label' => 'Einkaufsbedarf', 'text' => 'Fehlmengen aus offenen Bestellwünschen – auf Knopfdruck im Bereich „Einkauf“ (Bearbeiter und Administratoren).', 'fest' => false, 'pause' => 0, 'manuell' => true],
    'abmeldung' => ['label' => 'Abmeldung vom Wochenangebot', 'text' => 'Ein Kunde bestellt das Wochenangebot per E-Mail ab oder wieder an.', 'fest' => false, 'pause' => 0, 'ersatz' => true],
];
const NOTIFY_MAX_TO = 5;
/* Protokoll-Vorgänge, die als Ereignis gemeldet werden */
const NOTIFY_AUDIT = ['security' => 'sicherheit', 'twofa' => 'sicherheit', 'user' => 'sicherheit', 'wartung' => 'sicherheit', 'setup' => 'sicherheit'];
/* (Abmeldungen haben eine eigene, ausführlichere E-Mail: abmelde_melden() in kundenmail.php) */

/* Gespeicherte Einstellungen: ['events' => [ereignis => ['on' => bool, 'to' => [...]]], 'updatedAt', 'updatedBy'].
   Die Empfänger der Bestellwünsche liegen weiterhin bei der Bestellfunktion (Dokument „bestellung“). */
function notify_settings(): array
{
    $d = store_read('benachrichtigungen');
    $ord = order_settings();
    $ev = [];
    foreach (NOTIFY_EVENTS as $k => $def) {
        if ($def['fest']) { $ev[$k] = ['on' => $ord['enabled'], 'to' => $ord['to']]; continue; }
        $e = is_array($d['events'][$k] ?? null) ? $d['events'][$k] : null;
        if ($e === null) { $ev[$k] = ['on' => !empty($def['ersatz']) || !empty($def['manuell']), 'to' => []]; continue; }
        $ev[$k] = ['on' => !empty($e['on']) || !empty($def['manuell']), 'to' => array_values(array_filter((array)($e['to'] ?? []), 'is_string'))];
    }
    return ['events' => $ev, 'updatedAt' => $d['updatedAt'] ?? null, 'updatedBy' => $d['updatedBy'] ?? ''];
}
function notify_view(): array
{
    $s = notify_settings();
    $out = [];
    $cfg = mail_cfg();
    $fallback = $cfg ? ($cfg['replyTo'] ?: $cfg['from']) : '';
    foreach (NOTIFY_EVENTS as $k => $def) $out[] = ['key' => $k, 'label' => $def['label'], 'text' => $def['text'], 'fest' => $def['fest'], 'manuell' => !empty($def['manuell']), 'ersatz' => !empty($def['ersatz']) ? $fallback : null] + $s['events'][$k];
    return ['events' => $out, 'updatedAt' => $s['updatedAt'], 'updatedBy' => $s['updatedBy'], 'max' => NOTIFY_MAX_TO];
}
/* Empfänger eines Ereignisses (leer = keine E-Mail); berücksichtigt den Ersatz (Antwortadresse) */
function notify_targets(string $ev, bool $evenIfOff = false): array
{
    $e = notify_settings()['events'][$ev] ?? null;
    if (!$e || (!$e['on'] && !$evenIfOff)) return [];
    if ($e['to'] || empty(NOTIFY_EVENTS[$ev]['ersatz'])) return $e['to'];
    $cfg = mail_cfg();
    $a = $cfg ? ($cfg['replyTo'] ?: $cfg['from']) : '';
    return $a !== '' ? [$a] : [];
}
/* Empfängerliste aus Text oder Liste prüfen (Komma, Semikolon, Leerzeichen); doppelte entfernt */
function notify_parse_to($raw, string $what): array
{
    $raw = is_array($raw) ? implode(',', array_map('strval', $raw)) : (string)$raw;
    $to = [];
    foreach (preg_split('/[\s,;]+/', $raw) as $a) {
        if ($a === '') continue;
        if (filter_var($a, FILTER_VALIDATE_EMAIL) === false) fail("„" . mb_substr($a, 0, 80) . "“ ist keine gültige E-Mail-Adresse.", 422);
        $to[strtolower($a)] = $a;
    }
    $to = array_values($to);
    if (count($to) > NOTIFY_MAX_TO) fail('Höchstens ' . NOTIFY_MAX_TO . " Empfänger für {$what}.", 422);
    return $to;
}

/* Ereignis vormerken; versendet wird nach der Antwort (notify_flush) */
function notify(string $ev, string $title, array $facts = []): void
{
    if (!isset(NOTIFY_EVENTS[$ev]) || NOTIFY_EVENTS[$ev]['fest'] || !empty(NOTIFY_EVENTS[$ev]['manuell'])) return;
    if (empty($GLOBALS['notify_queue'])) {
        $GLOBALS['notify_queue'] = [];
        if (empty($GLOBALS['notify_registered'])) { $GLOBALS['notify_registered'] = true; register_shutdown_function('notify_flush'); }
    }
    if (count($GLOBALS['notify_queue']) < 20) $GLOBALS['notify_queue'][] = ['ev' => $ev, 'title' => $title, 'facts' => $facts, 't' => now()];
}
/* Aus dem Protokoll: passende Vorgänge als Ereignis melden (Wer, IP, Änderungen) */
function notify_from_audit(string $a, string $s, array $d, ?array $who): void
{
    $ev = NOTIFY_AUDIT[$a] ?? null;
    if (!$ev) return;
    $facts = [];
    if ($who && ($who['name'] ?? '') !== '') $facts[] = ['Durch', $who['name'] . (($who['username'] ?? '') !== '' ? " ({$who['username']})" : '')];
    $facts[] = ['IP-Adresse', client_ip()];
    foreach (array_slice($d, 0, 8) as $c) {
        if (!is_array($c)) continue;
        $f = trim((string)($c['name'] ?? '') . ' · ' . (string)($c['f'] ?? ''), ' ·');
        $facts[] = [$f !== '' ? $f : 'Änderung', trim((string)($c['from'] ?? '') . ' → ' . (string)($c['to'] ?? ''), ' →')];
    }
    if (count($d) > 8) $facts[] = ['…', (count($d) - 8) . ' weitere Änderungen (siehe Protokoll)'];
    notify($ev, $s, $facts);
}

/* Inhalt einer Benachrichtigung: [Betreff, Text, HTML] */
function notify_mail(string $ev, array $items, int $skipped, bool $test = false): array
{
    global $CFG;
    $def = NOTIFY_EVENTS[$ev];
    $first = $items[0];
    $subject = '[' . $CFG['company'] . '] ' . $def['label'] . ': ' . mb_substr($first['title'], 0, 120) . (count($items) > 1 ? ' (+' . (count($items) - 1) . ')' : '');
    $base = mail_base_url();
    $t = "Hallo,\n\n" . ($test ? "dies ist eine Test-Benachrichtigung. So sieht eine E-Mail zum Ereignis „{$def['label']}“ aus.\n" : "im Angebotsportal ist Folgendes passiert:\n");
    $h = '<p style="margin:0 0 14px;">Hallo,</p><p style="margin:0 0 14px;">' . mail_h($test ? "dies ist eine Test-Benachrichtigung. So sieht eine E-Mail zum Ereignis „{$def['label']}“ aus." : 'im Angebotsportal ist Folgendes passiert:') . '</p>';
    foreach ($items as $it) {
        $when = date('d.m.Y, H:i', strtotime($it['t'])) . ' Uhr';
        $t .= "\n" . $it['title'] . "\n" . str_pad('Zeit:', 18) . $when . "\n";
        foreach ($it['facts'] as [$k, $v]) $t .= str_pad(mb_substr($k, 0, 40) . ':', 18) . $v . "\n";
        $rows = '<tr><td style="padding:3px 12px 3px 0;color:#857c72;white-space:nowrap;vertical-align:top;">Zeit</td><td style="padding:3px 0;">' . mail_h($when) . '</td></tr>';
        foreach ($it['facts'] as [$k, $v]) $rows .= '<tr><td style="padding:3px 12px 3px 0;color:#857c72;vertical-align:top;">' . mail_h(mb_substr($k, 0, 40)) . '</td><td style="padding:3px 0;">' . mail_h(mb_substr((string)$v, 0, 300)) . '</td></tr>';
        $h .= '<p style="margin:16px 0 6px;font-weight:bold;">' . mail_h($it['title']) . '</p><table role="presentation" cellpadding="0" cellspacing="0" style="font-size:14px;">' . $rows . '</table>';
    }
    if ($skipped > 0) {
        $t .= "\nSeit der letzten Benachrichtigung gab es {$skipped} weitere Ereignisse dieser Art (siehe Protokoll).\n";
        $h .= '<p style="margin:16px 0 0;padding:10px 12px;background:#f7efe9;border-radius:8px;">Seit der letzten Benachrichtigung gab es ' . $skipped . ' weitere Ereignisse dieser Art – Details im Protokoll.</p>';
    }
    $ziel = alter_zugang_aus() ? eingabe_adresse() : ($base ? $base . '/admin/' : '');   // alter Zugang stillgelegt: neuer Eingabebereich
    if ($ziel) { $t .= "\nEingabebereich: {$ziel}\n"; $h .= '<p style="margin:16px 0 0;"><a href="' . mail_h($ziel) . '" style="color:#7b1e2b;">Eingabebereich öffnen</a></p>'; }
    $foot = 'Automatisch erzeugt vom Angebotsportal. Einstellbar unter Verwaltung → E-Mail → Benachrichtigungen.';
    $t .= "\n" . $foot . "\n";
    return [$subject, $t, mail_layout($subject, $h, '', $foot)];
}
/* An die Empfänger eines Ereignisses senden und im Versandprotokoll vermerken; Ergebnis je Empfänger.
   $inhalt: fertige E-Mail [Betreff, Text, HTML] statt der Ereignisliste (z. B. Wochenbericht des Moduls Sicherheit). */
function notify_send(string $ev, array $to, array $items, int $skipped, bool $test, string $by, ?array $inhalt = null): array
{
    $cfg = mail_cfg_intern();   // Benachrichtigungen gehen nur an Mitarbeiter: internes Postfach
    if (!$cfg || !$to) return [];
    [$subject, $text, $html] = $inhalt ?? notify_mail($ev, $items, $skipped, $test);
    $jobs = [];
    foreach ($to as $a) $jobs[] = ['to' => $a, 'name' => '', 'subject' => $subject, 'text' => $text, 'html' => $html];
    // Benachrichtigungen gehen auch im Notfallmodus raus (nur an die eingetragenen Empfänger, lib/notfall.php)
    $GLOBALS['NOTFALL_MAIL_FREI'] = true;
    try { $res = mail_send_many($cfg, $jobs); } finally { $GLOBALS['NOTFALL_MAIL_FREI'] = false; }
    with_lock('mailversand', function () use ($jobs, $res, $by, $ev) {
        $l = store_read('mailversand') ?? [];
        foreach ($jobs as $k => $j) $l[] = ['t' => now(), 'typ' => 'benachrichtigung', 'kid' => '', 'firma' => NOTIFY_EVENTS[$ev]['label'], 'to' => $j['to'], 'ok' => !empty($res[$k]['ok']), 'error' => $res[$k]['error'] ?? '', 'by' => $by];
        store_write('mailversand', array_slice($l, -3000));
    });
    $out = [];
    foreach ($jobs as $k => $j) $out[] = ['to' => $j['to'], 'ok' => !empty($res[$k]['ok']), 'error' => $res[$k]['error'] ?? ''];
    return $out;
}
/* Nach der Antwort: vorgemerkte Ereignisse je Art bündeln, Pause beachten, versenden. Fehler nie nach außen. */
function notify_flush(): void
{
    $q = $GLOBALS['notify_queue'] ?? [];
    $GLOBALS['notify_queue'] = [];
    if (!$q) return;
    try {
        if (!empty($GLOBALS['store_tx'])) return;   // nicht gespeichert → nichts melden
        $by = [];
        foreach ($q as $it) if (notify_targets($it['ev'])) $by[$it['ev']][] = $it;
        if (!$by || !mail_cfg_intern()) return;
        if (function_exists('fastcgi_finish_request')) fastcgi_finish_request();
        ignore_user_abort(true);
        foreach ($by as $ev => $items) {
            $pause = (int)NOTIFY_EVENTS[$ev]['pause'];
            $skipped = with_lock('benachrichtigung-stand', function () use ($ev, $items, $pause) {
                $st = store_read('benachrichtigung-stand') ?? [];
                $e = is_array($st[$ev] ?? null) ? $st[$ev] : ['last' => 0, 'skipped' => 0];
                if ($pause > 0 && (int)$e['last'] > time() - $pause) {
                    $e['skipped'] = (int)$e['skipped'] + count($items);
                    $st[$ev] = $e; store_write('benachrichtigung-stand', $st);
                    return -1;
                }
                $n = (int)$e['skipped'];
                $st[$ev] = ['last' => time(), 'skipped' => 0]; store_write('benachrichtigung-stand', $st);
                return $n;
            });
            if ($skipped < 0) continue;
            notify_send($ev, notify_targets($ev), $items, $skipped, false, 'Benachrichtigung');
        }
    } catch (Throwable $e) {
        error_log('[wochenangebot] Benachrichtigung: ' . $e->getMessage());
    }
}
