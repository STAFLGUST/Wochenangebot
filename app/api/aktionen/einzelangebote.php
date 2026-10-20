<?php
declare(strict_types=1);
/* Aktionen: Einzelangebote (Angebot bearbeiten → Einzelangebote). Beschreibung: lib/einzelangebote.php
   Rechte: einzelangebote.sehen (setzt kunden.sehen voraus), einzelangebote.bearbeiten; E-Mail an den Kunden mit Passwortbestätigung.
   Wird von api/index.php im globalen Gültigkeitsbereich eingebunden; jede Aktion endet mit respond()/fail(). */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

switch ($action) {
        case 'einzel_liste': {
            require_perm('einzelangebote.sehen');
            header('Cache-Control: no-store');
            $k = einzel_kunden_map();
            $list = array_map(function ($e) use ($k) { $v = einzel_view($e, $k); $v['positionCount'] = count($e['positions']); unset($v['positions']); return $v; }, einzel_load()['list']);
            usort($list, function ($a, $b) { return strcmp((string)$b['changed'], (string)$a['changed']); });
            respond(['ok' => true, 'list' => $list]);
        }

        case 'einzel_detail': {
            require_perm('einzelangebote.sehen');
            header('Cache-Control: no-store');
            $d = einzel_load();
            $i = einzel_find($d, (string)($_GET['id'] ?? ''));
            if ($i === null) fail('Einzelangebot nicht gefunden.', 404);
            respond(['ok' => true, 'angebot' => einzel_view($d['list'][$i], einzel_kunden_map()), 'fracht' => fracht_hinweis()]);
        }

        case 'einzel_pdf': {   // PDF im Design der Angebotsansicht (Vorschau des E-Mail-Anhangs)
            require_perm('einzelangebote.sehen');
            $d = einzel_load();
            $i = einzel_find($d, (string)($_GET['id'] ?? ''));
            if ($i === null) fail('Einzelangebot nicht gefunden.', 404);
            $e = $d['list'][$i];
            $pdf = einzel_pdf($e, einzel_kunden_map()[$e['kid']] ?? null);
            header('Content-Type: application/pdf');
            header('Content-Disposition: inline; filename="' . einzel_pdf_name($e) . '"');
            header('Cache-Control: private, no-store');
            header('X-Content-Type-Options: nosniff');
            header('Content-Length: ' . strlen($pdf));
            echo $pdf;
            exit;
        }

        case 'einzel_artikel': {
            $me = require_perm('einzelangebote.bearbeiten');
            header('Cache-Control: no-store');
            respond(['ok' => true] + einzel_artikel(may($me, 'bestand.sehen'), may($me, 'bestand.einkaufspreise')));
        }

        case 'einzel_save': {
            $me = require_perm('einzelangebote.bearbeiten', true);
            $b = body();
            [$c, $data] = einzel_clean($b);
            $id = is_string($b['id'] ?? null) ? $b['id'] : '';
            $e = with_lock('einzelangebote', function () use ($id, $b, $data, $me) {
                $d = einzel_load();
                if ($id === '') {
                    $y = date('Y');
                    $n = (int)($d['seq'][$y] ?? 0) + 1;
                    $d['seq'][$y] = $n;
                    $e = ['id' => bin2hex(random_bytes(5)), 'nr' => sprintf('E-%s-%04d', $y, $n)] + $data
                       + ['status' => 'entwurf', 'revision' => 1, 'created' => now(), 'createdBy' => $me['name'], 'changed' => now(), 'changedBy' => $me['name'], 'freigegebenAt' => null, 'gesendet' => []];
                    $d['list'][] = $e;
                } else {
                    $i = einzel_find($d, $id);
                    if ($i === null) fail('Einzelangebot nicht gefunden.', 404);
                    $e = $d['list'][$i];
                    if (!is_int($b['revision'] ?? null) || $b['revision'] !== (int)$e['revision']) fail('Das Einzelangebot wurde inzwischen geändert. Bitte neu laden.', 409);
                    $e = array_merge($e, $data, ['revision' => (int)$e['revision'] + 1, 'changed' => now(), 'changedBy' => $me['name']]);
                    if ($e['status'] === 'freigegeben' && !$e['positions']) fail('Ein im Portal freigegebenes Einzelangebot braucht mindestens eine Position. Bitte zuerst die Freigabe beenden.', 422);
                    if ($e['status'] === 'freigegeben') $e['freigegebenAt'] = einzel_stand($e['freigegebenAt'] ?? null);   // Kunde sieht die Änderung sofort; alte Bestellstände werden abgewiesen
                    $d['list'][$i] = $e;
                }
                store_write('einzelangebote', $d);
                return $e;
            });
            audit('einzelangebot', "Einzelangebot {$e['nr']} für „{$c['firma']}“ " . ($id === '' ? 'angelegt' : 'gespeichert') . ' (' . count($e['positions']) . ' Positionen)');
            respond(['ok' => true, 'angebot' => einzel_view($e, einzel_kunden_map())]);
        }

        case 'einzel_status': {
            $me = require_perm('einzelangebote.bearbeiten', true);
            $b = body();
            $status = (string)($b['status'] ?? '');
            if (!in_array($status, EINZEL_STATUS, true)) fail('Ungültiger Status.', 422);
            $e = with_lock('einzelangebote', function () use ($b, $status, $me) {
                $d = einzel_load();
                $i = einzel_find($d, (string)($b['id'] ?? ''));
                if ($i === null) fail('Einzelangebot nicht gefunden.', 404);
                $e = $d['list'][$i];
                if (!is_int($b['revision'] ?? null) || $b['revision'] !== (int)$e['revision']) fail('Das Einzelangebot wurde inzwischen geändert. Bitte neu laden.', 409);
                if ($status === 'freigegeben' && !$e['positions']) fail('Bitte zuerst Positionen eintragen.', 422);
                if ($status === 'freigegeben' && !einzel_gueltig($e)) fail('Das Angebot ist bereits abgelaufen. Bitte „gültig bis“ anpassen.', 422);
                $e['status'] = $status;
                $e['revision'] = (int)$e['revision'] + 1;
                $e['changed'] = now(); $e['changedBy'] = $me['name'];
                if ($status === 'freigegeben') $e['freigegebenAt'] = einzel_stand($e['freigegebenAt'] ?? null);
                $d['list'][$i] = $e;
                store_write('einzelangebote', $d);
                return $e;
            });
            $txt = ['freigegeben' => 'im Portal freigegeben', 'entwurf' => 'zurück auf Entwurf gesetzt', 'zurueckgezogen' => 'zurückgezogen'][$status];
            audit('einzelangebot', "Einzelangebot {$e['nr']} $txt");
            respond(['ok' => true, 'angebot' => einzel_view($e, einzel_kunden_map())]);
        }

        case 'einzel_loeschen': {
            require_perm('einzelangebote.bearbeiten', true);
            $b = body();
            $e = with_lock('einzelangebote', function () use ($b) {
                $d = einzel_load();
                $i = einzel_find($d, (string)($b['id'] ?? ''));
                if ($i === null) fail('Einzelangebot nicht gefunden.', 404);
                $e = $d['list'][$i];
                array_splice($d['list'], $i, 1);
                store_write('einzelangebote', $d);
                return $e;
            });
            audit('einzelangebot', "Einzelangebot {$e['nr']} gelöscht");
            respond(['ok' => true]);
        }

        case 'einzel_senden': {
            $me = require_perm_confirmed('einzelangebote.bearbeiten', 'einzel_senden');
            $cfg = require_mail();
            $b = body();
            $d = einzel_load();
            $i = einzel_find($d, (string)($b['id'] ?? ''));
            if ($i === null) fail('Einzelangebot nicht gefunden.', 404);
            $e = $d['list'][$i];
            if (!$e['positions']) fail('Das Einzelangebot hat noch keine Positionen.', 422);
            if (($e['status'] ?? '') === 'zurueckgezogen') fail('Das Einzelangebot ist zurückgezogen und wird nicht mehr versendet.', 422);
            if (!einzel_gueltig($e)) fail('Das Einzelangebot ist abgelaufen. Bitte zuerst „gültig bis“ anpassen.', 422);
            $c = einzel_kunden_map()[$e['kid']] ?? null;
            if (!$c) fail('Der Kunde existiert nicht mehr.', 404);
            if (empty($c['email'])) fail("Für „{$c['firma']}“ ist keine E-Mail-Adresse hinterlegt.", 422);
            $note = mb_substr(trim((string)($b['note'] ?? '')), 0, 1000);
            $format = (string)($b['format'] ?? 'liste');
            if (!in_array($format, ['liste', 'pdf'], true)) fail('Unbekanntes Format.', 422);
            [$sub, $txt, $html] = mail_tpl_einzel($c, $e, $note, $format);
            @set_time_limit(120);
            $job = ['to' => $c['email'], 'name' => ($c['ansprechpartner'] ?? '') ?: $c['firma'], 'subject' => $sub, 'text' => $txt, 'html' => $html];
            if ($format === 'pdf') $job['anhaenge'] = [['name' => einzel_pdf_name($e), 'type' => 'application/pdf', 'data' => einzel_pdf($e, $c)]];
            $r = mail_send_many($cfg, ['x' => $job])['x'];
            mail_record([['kid' => $c['id'], 'firma' => $c['firma'], 'to' => $c['email'], 'typ' => 'einzelangebot', 'ok' => $r['ok'], 'error' => $r['error'] ?? '']]);
            $e = with_lock('einzelangebote', function () use ($e, $c, $r, $me, $format) {
                $d = einzel_load();
                $i = einzel_find($d, $e['id']);
                if ($i === null) return $e;
                $d['list'][$i]['gesendet'][] = ['t' => now(), 'to' => $c['email'], 'by' => $me['name'], 'ok' => $r['ok'], 'format' => $format];
                $d['list'][$i]['gesendet'] = array_slice($d['list'][$i]['gesendet'], -50);
                store_write('einzelangebote', $d);
                return $d['list'][$i];
            });
            audit('mail', "Einzelangebot {$e['nr']} an „{$c['firma']}“ ({$c['email']}) " . ($format === 'pdf' ? 'als PDF ' : '') . ($r['ok'] ? 'versendet' : 'nicht zugestellt: ' . ($r['error'] ?? '')));
            if (!$r['ok']) fail('Die E-Mail konnte nicht zugestellt werden: ' . ($r['error'] ?? 'unbekannter Fehler'), 502);
            respond(['ok' => true, 'angebot' => einzel_view($e, einzel_kunden_map())]);
        }
}
