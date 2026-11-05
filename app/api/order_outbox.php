<?php
/* Versandaufträge eines Bestellwunschs: je Empfänger ein Auftrag im selben Dokument (bestellungen) wie der Vorgang.
   ADR-007 Stufe 2b – Empfänger und Inhalt bestimmt nie die Kundenseite:
   - Ab Trennstufe 2 nur an Adressen, die beim Versand erlaubt sind: an das Team nur an heutige oder frühere Empfänger der
     Bestellfunktion, die Kopie nur an die Adresse aus den Stammdaten des Kunden (order_outbox_pruefen). Andere Aufträge werden
     verworfen und gemeldet. Den Inhalt erzeugt der Versand dann selbst aus dem Vorgang (mail_tpl_bestellung) – gespeicherte Texte
     werden nie verschickt. Bis Trennstufe 2 (gemeinsame Daten) gilt wie bisher der gespeicherte Originalstand.
   - Ab Trennstufe 2 kennt die Kundenseite weder die Empfänger noch Anschrift und E-Mail des Kunden: Sie legt nur einen offenen
     Auftrag an (kind „offen“). Daraus macht order_outbox_vorbereiten() beim ersten Versand die Aufträge je Empfänger und ergänzt
     den Schnappschuss des Kunden aus den internen Stammdaten (einmalig, GR-106).
   - Je Kunde höchstens ORDER_MAIL_TAG Bestellwünsche am Tag (Versandprotokoll, intern) – auch wenn jemand die Kundenseite übernimmt. */
const ORDER_MAIL_TAG = 30;
function order_outbox_job(string $kind, string $to, string $name): array
{
    return ['id' => bin2hex(random_bytes(12)), 'kind' => $kind, 'to' => $to, 'name' => $name, 'state' => 'queued', 'attempts' => 0, 'updatedAt' => now(), 'error' => '', 'history' => []];
}
/* Aufträge eines neuen Bestellwunschs; ohne Sicht auf die internen Daten (Kundenseite ab Trennstufe 2) nur der offene Auftrag */
function order_outbox_create(array $o): array
{
    if (kunden_geteilt() && !store_innen()) return [order_outbox_job('offen', '', '')];
    return order_outbox_empfaenger($o);
}
/* Aufträge je Empfänger aus den aktuellen Einstellungen (Team) und den Stammdaten des Kunden (Kopie). Der Inhalt bleibt wie bisher
   dabei (nur für ältere Stände nach einem Rückfall, GR-006) – verschickt wird er nie, der Versand erzeugt ihn neu. */
function order_outbox_empfaenger(array $o): array
{
    $st = order_settings(); $jobs = [];
    foreach (array_unique($st['to']) as $to) {
        [$subject, $text, $html] = mail_tpl_bestellung($o, false);
        $jobs[] = order_outbox_job('bestellung', $to, '') + ['subject' => $subject, 'text' => $text, 'html' => $html];
    }
    $mail = order_kunden_email((string)($o['kid'] ?? ''));
    if ($st['copy'] && $mail !== null) {
        [$subject, $text, $html] = mail_tpl_bestellung($o, true);
        $jobs[] = order_outbox_job('bestellkopie', $mail, order_kopie_name($o)) + ['subject' => $subject, 'text' => $text, 'html' => $html];
    }
    return $jobs;
}
function order_kopie_name(array $o): string { return (string)(($o['kunde']['ansprechpartner'] ?? '') ?: ($o['kunde']['firma'] ?? '')); }
/* Adresse eines Kunden aus den Stammdaten (null: unbekannt, inaktiv oder ohne gültige Adresse) – nie aus dem Vorgang */
function order_kunden_email(string $kid): ?string
{
    foreach (customers_load()['customers'] as $c) if (($c['id'] ?? '') === $kid) {
        $e = trim((string)($c['email'] ?? ''));
        return !empty($c['active']) && filter_var($e, FILTER_VALIDATE_EMAIL) ? $e : null;
    }
    return null;
}
/* Offenen Auftrag der Kundenseite ausführen (unter der Versandsperre des Vorgangs): Schnappschuss ergänzen, Aufträge je Empfänger
   anlegen. Nur auf einem Server mit Sicht auf die internen Daten (Postausgang, Mitarbeiterseite). */
function order_outbox_vorbereiten(string $nr): void
{
    if (!store_innen()) throw new RuntimeException('Versand nur mit Zugriff auf die internen Daten (Postausgang).');
    with_lock('bestellungen', function () use ($nr) {
        $all = store_read('bestellungen') ?? [];
        foreach ($all as $i => $o) {
            if (($o['nr'] ?? '') !== $nr) continue;
            $offen = array_values(array_filter($o['outbox'] ?? [], fn($j) => ($j['kind'] ?? '') === 'offen' && ($j['state'] ?? '') !== 'sent'));
            if (!$offen) return;
            $kunde = null;
            foreach (customers_load()['customers'] as $c) if (($c['id'] ?? '') === ($o['kid'] ?? null)) $kunde = $c;
            if ($kunde !== null && empty($o['kundeErgaenzt'])) {   // einmalig: Schnappschuss aus den internen Stammdaten (GR-106)
                $o['kunde'] = array_merge($o['kunde'] ?? [], array_intersect_key(kunde_schnappschuss($kunde), array_flip(KUNDE_SCHNAPPSCHUSS)));
                unset($o['kunde']['emailMaske']);
                $o['kundeErgaenzt'] = now();
            }
            $jobs = $kunde !== null ? order_outbox_empfaenger($o) : [];
            $rest = array_values(array_filter($o['outbox'] ?? [], fn($j) => ($j['kind'] ?? '') !== 'offen'));
            if ($jobs) {
                $o['outbox'] = array_merge($rest, $jobs);
            } else {
                $grund = $kunde === null ? 'Kunde nicht (mehr) in den Stammdaten – Versand verworfen' : 'Keine Empfänger für Bestellwünsche eingetragen';
                $o['outbox'] = array_merge($rest, [array_merge($offen[0], ['state' => 'failed', 'updatedAt' => now(), 'error' => $grund])]);
                $o['status'] = 'fehler'; $o['error'] = $grund;
            }
            $all[$i] = $o;
            store_write('bestellungen', $all);
            return;
        }
    });
}
/* Darf dieser Auftrag jetzt verschickt werden? null = ja, sonst der Grund (Auftrag wird verworfen, nicht wiederholt).
   Bis Trennstufe 2 teilen sich beide Seiten ohnehin alle Daten – dort gilt wie bisher der gespeicherte Originalstand. Ab Stufe 2: an
   das Team nur an heutige oder frühere Empfänger der Bestellfunktion (so bleibt der Originalempfänger beim Nachsenden), die Kopie nur
   an die heutige Adresse aus den Stammdaten des Kunden. */
function order_outbox_pruefen(array $o, array $j): ?string
{
    if (!kunden_geteilt()) return null;
    $to = mb_strtolower(trim((string)($j['to'] ?? '')));
    if (($j['kind'] ?? '') === 'bestellung') {
        $st = order_settings();
        if (!in_array($to, array_map('mb_strtolower', array_merge($st['to'], $st['frueher'])), true)) return 'Versand verworfen: Empfänger gehört nicht zu den Empfängern der Bestellwünsche';
        if (order_tageszahl((string)($o['kid'] ?? ''), 'bestellung', $to) >= ORDER_MAIL_TAG) return 'Versand verworfen: mehr als ' . ORDER_MAIL_TAG . ' Bestellwünsche dieses Kunden in 24 Stunden';
        return null;
    }
    if (($j['kind'] ?? '') === 'bestellkopie') {
        if (!order_settings()['copy']) return 'Versand verworfen: Kopie an den Kunden ist ausgeschaltet';
        $mail = order_kunden_email((string)($o['kid'] ?? ''));
        if ($mail === null || mb_strtolower($mail) !== $to) return 'Versand verworfen: Adresse stimmt nicht mit den Stammdaten des Kunden überein';
        if (order_tageszahl((string)($o['kid'] ?? ''), 'bestellkopie', $to) >= ORDER_MAIL_TAG) return 'Versand verworfen: mehr als ' . ORDER_MAIL_TAG . ' Kopien an diesen Kunden in 24 Stunden';
        return null;
    }
    return 'Versand verworfen: unbekannte Art des Auftrags';
}
/* Zugestellte E-Mails dieser Art an diese Adresse für diesen Kunden in den letzten 24 Stunden (Versandprotokoll) */
function order_tageszahl(string $kid, string $typ, string $to): int
{
    $seit = gmdate('Y-m-d\TH:i:s', time() - 86400);
    $n = 0;
    foreach (store_read('mailversand') ?? [] as $e) {
        if (($e['typ'] ?? '') === $typ && ($e['kid'] ?? '') === $kid && !empty($e['ok']) && mb_strtolower((string)($e['to'] ?? '')) === $to && (string)($e['t'] ?? '') >= $seit) $n++;
    }
    return $n;
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
/* Sperrdateien abgeschlossener Vorgänge gelegentlich entfernen (älter als 2 Tage, nicht die eigene). */
function order_outbox_cleanup_locks(string $own): void
{
    global $DATA;
    if (random_int(1, 20) !== 1) return;
    foreach (glob($DATA . '/.order-mail-*.lock') ?: [] as $f) if ($f !== $own && @filemtime($f) < time() - 172800) @unlink($f);
}
/* No SQLite transaction spans SMTP. A separate nonblocking process lock protects a retry
   even if the previous HTTP request is still running. Process death releases it. */
function order_outbox_send(string $nr, ?string $jobId = null, ?int $expected = null, string $by = 'Kunde'): array
{
    global $DATA;
    $lp = $DATA . '/.order-mail-' . hash('sha256', $nr) . '.lock';
    $lock = @fopen($lp, 'c') ?: (is_file($lp) ? @fopen($lp, 'r') : false);
    if (!$lock) throw new RuntimeException('Versandsperre nicht verfügbar.');
    if (!flock($lock, LOCK_EX | LOCK_NB)) { fclose($lock); fail('Für diesen Bestellwunsch läuft bereits ein Versand. Bitte später neu laden.', 409); }
    @touch($lp);              // aktiv genutzte Sperren werden nicht aufgeräumt
    order_outbox_cleanup_locks($lp);
    try {
        $found = false;
        foreach (store_read('bestellungen') ?? [] as $order) if ($order['nr'] === $nr) { $found = true; break; }
        if (!$found) fail('Bestellwunsch nicht gefunden.', 404);
        if ($jobId !== null && !in_array($jobId, array_column($order['outbox'] ?? [], 'id'), true)) fail('Versandauftrag nicht gefunden. Ältere Vorgänge können hier nicht nachgesendet werden.', 404);
        // offener Auftrag der Kundenseite (ab Trennstufe 2): erst Empfänger bestimmen – ein gezielter Neuversand gilt dann allen
        if (array_filter($order['outbox'] ?? [], fn($j) => ($j['kind'] ?? '') === 'offen' && ($j['state'] ?? '') !== 'sent')) {
            order_outbox_vorbereiten($nr);
            foreach (store_read('bestellungen') ?? [] as $order) if ($order['nr'] === $nr) break;
            if ($jobId !== null && !in_array($jobId, array_column($order['outbox'] ?? [], 'id'), true)) { $jobId = null; $expected = null; }
        }
        foreach ($order['outbox'] ?? [] as $candidate) {
            if ($jobId !== null ? $candidate['id'] !== $jobId : $candidate['state'] !== 'queued') continue;
            if (($candidate['kind'] ?? '') === 'offen') continue;   // ohne Empfänger (z. B. keine eingetragen) – steht als fehlgeschlagen beim Vorgang
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
            $verworfen = order_outbox_pruefen($o, $j);
            try {
                if ($verworfen !== null) throw new RuntimeException($verworfen);
                $cfg = $j['kind'] === 'bestellung' ? mail_cfg_intern() : mail_cfg();   // an das Team: internes Postfach; Kopie an den Kunden: Kunden-Postfach
                if (!$cfg) throw new RuntimeException('E-Mail-Versand ist nicht eingerichtet.');
                $kundeMail = trim((string)($o['kunde']['email'] ?? ''));
                if ($j['kind'] === 'bestellung' && filter_var($kundeMail, FILTER_VALIDATE_EMAIL)) $cfg['replyTo'] = $kundeMail;
                // ab Trennstufe 2 Inhalt immer neu aus dem Vorgang – nie gespeicherte Texte (die könnte eine übernommene Kundenseite
                // verändert haben); bis dahin wie bisher der gespeicherte Originalstand
                [$subject, $text, $html] = !kunden_geteilt() && isset($j['subject'], $j['text'], $j['html']) ? [$j['subject'], $j['text'], $j['html']] : mail_tpl_bestellung($o, $j['kind'] === 'bestellkopie');
                $name = $j['kind'] !== 'bestellkopie' ? '' : (kunden_geteilt() ? order_kopie_name($o) : (string)($j['name'] ?? ''));
                $result = mail_send_many($cfg, [['to' => $j['to'], 'name' => $name, 'subject' => $subject, 'text' => $text, 'html' => $html]])[0];
            } catch (Throwable $e) { $result = ['ok'=>false, 'error'=>$e->getMessage()]; }
            if ($verworfen !== null) {
                error_log('[postausgang] ' . $nr . ': ' . $verworfen);
                audit('security', 'Versandauftrag zu Bestellwunsch ' . $nr . ' verworfen', [['k' => 'outbox|' . $nr, 'code' => $nr, 'name' => (string)($o['firma'] ?? ''), 'f' => 'Empfänger ' . mb_substr((string)$j['to'], 0, 120), 'from' => '', 'to' => mb_substr($verworfen, 19)]],
                      ['username' => 'postausgang', 'name' => 'Postausgang', 'role' => 'system']);
            }
            with_lock('bestellungen', function () use ($nr, $j, $result, $by) {
                $all = store_read('bestellungen') ?? [];
                foreach ($all as &$o) if ($o['nr'] === $nr) {
                    foreach ($o['outbox'] as &$saved) if ($saved['id'] === $j['id']) {
                        $saved['state'] = $result['ok'] ? 'sent' : 'failed'; $saved['updatedAt'] = now();
                        $saved['error'] = $result['ok'] ? '' : mb_substr($result['error'] ?? 'Unbekannter Versandfehler', 0, 500);
                        // Angenommene Nachrichten werden nie erneut gesendet: Inhalt nicht weiter mitschleppen (Dokumentgröße)
                        if ($result['ok']) unset($saved['subject'], $saved['text'], $saved['html']);
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
