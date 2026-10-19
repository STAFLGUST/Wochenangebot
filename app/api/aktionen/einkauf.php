<?php
declare(strict_types=1);
/* Aktionen: Einkauf (Fehlmengen aus offenen Bestellwünschen)
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        /* Ansehen: alle Mitarbeiter; Kundennamen nur für Bearbeiter und Administratoren */
        case 'einkauf': {
            $me = require_perm('einkauf.sehen');
            header('Cache-Control: no-store');
            $mit = may($me, 'bestellungen.sehen');
            $send = may($me, 'einkauf.melden');
            respond(['ok' => true, 'canSend' => $send, 'recipients' => $send ? count(notify_targets('einkauf')) : null, 'mail' => (bool)mail_cfg() && (bool)mail_base_url()] + einkauf_bedarf($mit));
        }

        /* Einkauf per E-Mail benachrichtigen (Bearbeiter): ausgewählte oder alle Fehlmengen */
        case 'einkauf_melden': {
            $me = require_perm('einkauf.melden', true);
            $b = body();
            $note = mb_substr(trim(str_replace("\r", '', preg_replace('/[\x00-\x08\x0b-\x1f]/u', '', (string)($b['note'] ?? '')) ?? '')), 0, 1000);
            $codes = is_array($b['codes'] ?? null) ? array_map(function ($c) { return code_key((string)$c); }, array_slice($b['codes'], 0, 2000)) : null;
            $bed = einkauf_bedarf(may($me, 'bestellungen.sehen'));
            if (!$bed['stock']) fail('Es ist keine Bestandsliste vorhanden – Fehlmengen lassen sich nicht berechnen.', 409);
            $items = $codes === null ? $bed['items'] : array_values(array_filter($bed['items'], function ($it) use ($codes) { return in_array(code_key($it['code']), $codes, true); }));
            if (!$items) fail($codes === null ? 'Derzeit gibt es keine Fehlmengen.' : 'Bitte mindestens einen Artikel mit Fehlmenge auswählen.', 422);
            $to = notify_targets('einkauf');
            if (!$to) fail('Für „Einkaufsbedarf“ sind noch keine Empfänger eingetragen. Ein Administrator legt sie unter Verwaltung → E-Mail → Benachrichtigungen fest.', 409);
            $cfg = require_mail();
            [$subject, $text, $html] = einkauf_mail($items, $bed['stock'], $note, $me['name']);
            $jobs = array_map(function ($a) use ($subject, $text, $html) { return ['to' => $a, 'name' => '', 'subject' => $subject, 'text' => $text, 'html' => $html]; }, $to);
            $res = mail_send_many($cfg, $jobs);
            $results = [];
            foreach ($jobs as $k => $j) $results[] = ['to' => $j['to'], 'ok' => !empty($res[$k]['ok']), 'error' => $res[$k]['error'] ?? ''];
            $okAny = (bool)array_filter($results, function ($r) { return $r['ok']; });
            with_lock('mailversand', function () use ($results, $me) {
                $l = store_read('mailversand') ?? [];
                foreach ($results as $r) $l[] = ['t' => now(), 'typ' => 'einkauf', 'kid' => '', 'firma' => 'Einkauf', 'to' => $r['to'], 'ok' => $r['ok'], 'error' => $r['error'], 'by' => $me['name']];
                store_write('mailversand', array_slice($l, -3000));
            });
            if ($okAny) {
                with_lock('einkauf-meldungen', function () use ($items, $me) {
                    $m = store_read('einkauf-meldungen') ?? [];
                    foreach ($items as $it) $m[code_key($it['code'])] = ['t' => now(), 'by' => $me['name'], 'kg' => $it['short']];
                    store_write('einkauf-meldungen', $m);
                });
                audit('einkauf', 'Einkauf benachrichtigt: ' . count($items) . ' Artikel, ' . de_qty(array_sum(array_column($items, 'short'))) . ' kg Fehlmenge',
                    array_map(function ($it) { return ['k' => 'ek|' . $it['code'], 'code' => $it['code'], 'name' => $it['name'], 'f' => 'Fehlmenge', 'from' => '', 'to' => de_qty($it['short']) . ' kg']; }, array_slice($items, 0, 200)));
            }
            respond(['ok' => $okAny, 'results' => $results, 'error' => $okAny ? null : 'Die E-Mail konnte nicht zugestellt werden.', 'canSend' => true, 'recipients' => count($to), 'mail' => true] + einkauf_bedarf(may($me, 'bestellungen.sehen')), $okAny ? 200 : 502);
        }
}
