<?php
/* Durable per-recipient jobs live in the same document/transaction as the order. */
function order_outbox_create(array $o): array
{
    $st = order_settings(); $jobs = [];
    foreach (array_unique($st['to']) as $to) {
        [$subject, $text, $html] = mail_tpl_bestellung($o, false);
        $jobs[] = ['id'=>bin2hex(random_bytes(12)), 'kind'=>'bestellung', 'to'=>$to, 'name'=>'', 'subject'=>$subject, 'text'=>$text, 'html'=>$html];
    }
    if ($st['copy'] && filter_var($o['kunde']['email'] ?? '', FILTER_VALIDATE_EMAIL)) {
        [$subject, $text, $html] = mail_tpl_bestellung($o, true);
        $jobs[] = ['id'=>bin2hex(random_bytes(12)), 'kind'=>'bestellkopie', 'to'=>$o['kunde']['email'], 'name'=>$o['kunde']['ansprechpartner'] ?: $o['kunde']['firma'], 'subject'=>$subject, 'text'=>$text, 'html'=>$html];
    }
    return array_map(fn($j) => $j + ['state'=>'queued', 'attempts'=>0, 'updatedAt'=>now(), 'error'=>'', 'history'=>[]], $jobs);
}
function order_outbox_summary(array &$o): void
{
    $internal = array_filter($o['outbox'], fn($j) => $j['kind'] === 'bestellung');
    $sent = count(array_filter($internal, fn($j) => $j['state'] === 'sent'));
    $o['status'] = $sent ? 'gesendet' : 'fehler'; // compatible receipt; detail exposes each recipient
    $o['kopie'] = (bool)array_filter($o['outbox'], fn($j) => $j['kind'] === 'bestellkopie' && $j['state'] === 'sent');
    $pending = array_filter($o['outbox'], fn($j) => $j['state'] !== 'sent');
    $o['error'] = $pending ? 'Nicht alle E-Mails wurden bestätigt. Versandaufträge prüfen.' : '';
}
function order_outbox_view(array $o): array
{
    return array_map(fn($j) => array_intersect_key($j, array_flip(['id','kind','to','state','attempts','updatedAt','error','history'])), $o['outbox'] ?? []);
}
/* No SQLite transaction spans SMTP. A separate nonblocking process lock protects a retry
   even if the previous HTTP request is still running. Process death releases it. */
function order_outbox_send(string $nr, ?string $jobId = null, ?int $expected = null, string $by = 'Kunde'): array
{
    global $DATA;
    $lock = fopen($DATA . '/.order-mail-' . hash('sha256', $nr) . '.lock', 'c');
    if (!$lock) throw new RuntimeException('Versandsperre nicht verfügbar.');
    if (!flock($lock, LOCK_EX | LOCK_NB)) { fclose($lock); fail('Für diesen Bestellwunsch läuft bereits ein Versand. Bitte später neu laden.', 409); }
    try {
        $found = false;
        foreach (store_read('bestellungen') ?? [] as $order) if ($order['nr'] === $nr) { $found = true; break; }
        if (!$found) fail('Bestellwunsch nicht gefunden.', 404);
        if ($jobId !== null && !in_array($jobId, array_column($order['outbox'] ?? [], 'id'), true)) fail('Versandauftrag nicht gefunden. Ältere Vorgänge können hier nicht nachgesendet werden.', 404);
        foreach ($order['outbox'] ?? [] as $candidate) {
            if ($jobId !== null ? $candidate['id'] !== $jobId : $candidate['state'] !== 'queued') continue;
            $claimed = with_lock('bestellungen', function () use ($nr, $candidate, $jobId, $expected, $by) {
                $all = store_read('bestellungen') ?? [];
                foreach ($all as &$o) if ($o['nr'] === $nr) {
                    foreach ($o['outbox'] as &$j) if ($j['id'] === $candidate['id']) {
                        if ($jobId !== null && ($expected !== $j['attempts'] || $j['state'] === 'sent')) fail('Der Versandauftrag wurde inzwischen geändert oder bereits versendet. Bitte neu laden.', 409);
                        if ($jobId === null && $j['state'] !== 'queued') return null;
                        if ($j['kind'] === 'bestellkopie' && !array_filter($o['outbox'], fn($x) => $x['kind'] === 'bestellung' && $x['state'] === 'sent')) {
                            if ($jobId !== null) fail('Zuerst muss mindestens ein interner Empfänger den Bestellwunsch erhalten.', 409);
                            return null;
                        }
                        $j['state'] = 'sending'; $j['attempts']++; $j['updatedAt'] = now(); $j['error'] = '';
                        $j['history'][] = ['t'=>now(), 'by'=>$by, 'attempt'=>$j['attempts'], 'state'=>'sending'];
                        store_write('bestellungen', $all);
                        return ['job'=>$j, 'order'=>$o];
                    }
                }
                return null;
            });
            if (!$claimed) continue;
            $j = $claimed['job']; $o = $claimed['order'];
            try {
                $cfg = mail_cfg();
                if (!$cfg) throw new RuntimeException('E-Mail-Versand ist nicht eingerichtet.');
                if ($j['kind'] === 'bestellung' && filter_var($o['kunde']['email'] ?? '', FILTER_VALIDATE_EMAIL)) $cfg['replyTo'] = $o['kunde']['email'];
                $result = mail_send_many($cfg, [$j])[0];
            } catch (Throwable $e) { $result = ['ok'=>false, 'error'=>$e->getMessage()]; }
            with_lock('bestellungen', function () use ($nr, $j, $result, $by) {
                $all = store_read('bestellungen') ?? [];
                foreach ($all as &$o) if ($o['nr'] === $nr) {
                    foreach ($o['outbox'] as &$saved) if ($saved['id'] === $j['id']) {
                        $saved['state'] = $result['ok'] ? 'sent' : 'failed'; $saved['updatedAt'] = now();
                        $saved['error'] = $result['ok'] ? '' : mb_substr($result['error'] ?? 'Unbekannter Versandfehler', 0, 500);
                        $saved['history'][] = ['t'=>now(), 'by'=>$by, 'attempt'=>$j['attempts'], 'state'=>$saved['state']];
                    }
                    unset($saved); order_outbox_summary($o);
                }
                unset($o); store_write('bestellungen', $all);
            });
            with_lock('mailversand', function () use ($o, $j, $result, $by) {
                $l = store_read('mailversand') ?? [];
                $l[] = ['t'=>now(), 'typ'=>$j['kind'], 'kid'=>$o['kid'], 'firma'=>$o['firma'], 'to'=>$j['to'], 'ok'=>$result['ok'], 'error'=>$result['error'] ?? '', 'by'=>$by];
                store_write('mailversand', array_slice($l, -3000));
            });
        }
        foreach (store_read('bestellungen') ?? [] as $o) if ($o['nr'] === $nr) return $o;
        throw new RuntimeException('Bestellwunsch nicht mehr vorhanden.');
    } finally { flock($lock, LOCK_UN); fclose($lock); }
}
