<?php
declare(strict_types=1);
/* Einkauf: Fehlmengen aus offenen Bestellwünschen gegenüber der zuletzt übernommenen Bestandsliste.
   Fehlmenge je Artikelnummer = Summe der bestellten Mengen (offene Vorgänge) − eingelagerter Bestand. */
if (!defined('WA_API')) { http_response_code(404); exit; }   // nur über api/index.php nutzbar

const EINKAUF_OFFEN = ['neu', 'in_bearbeitung', 'bestaetigt'];

/* $mitKunden: Firmennamen der Bestellwünsche (nur Bearbeiter/Administrator) */
function einkauf_bedarf(bool $mitKunden): array
{
    $st = store_read('bestand');
    $hasStock = is_array($st) && !empty($st['articles']);
    $stock = []; $stockName = [];
    if ($hasStock) foreach ($st['articles'] as $a) { $k = code_key((string)$a['code']); $stock[$k] = (float)$a['kg']; $stockName[$k] = (string)($a['name'] ?? ''); }
    $need = []; $ohneNr = 0; $offen = 0;
    foreach (store_read('bestellungen') ?? [] as $o) {
        if (!in_array($o['workflow'] ?? 'neu', EINKAUF_OFFEN, true)) continue;
        $offen++;
        $per = [];   // je Artikel und Vorgang zusammenfassen (gleicher Artikel mehrfach im selben Bestellwunsch)
        foreach ($o['positions'] ?? [] as $p) {
            $qty = (float)($p['qty'] ?? 0);
            if ($qty <= 0) continue;
            $code = trim((string)($p['code'] ?? ''));
            if ($code === '') { $ohneNr++; continue; }
            $k = code_key($code);
            if (!isset($need[$k])) $need[$k] = ['code' => $code, 'name' => (string)($p['name'] ?? ''), 'qty' => 0.0, 'orders' => []];
            $need[$k]['qty'] += $qty;
            $per[$k] = ($per[$k] ?? 0.0) + $qty;
        }
        foreach ($per as $k => $qty) {
            $ref = ['nr' => (string)$o['nr'], 't' => (string)($o['t'] ?? ''), 'termin' => (string)($o['termin'] ?? ''), 'qty' => round($qty, 3), 'workflow' => (string)($o['workflow'] ?? 'neu')];
            if ($mitKunden) $ref['firma'] = (string)($o['firma'] ?? '');
            $need[$k]['orders'][] = $ref;
        }
    }
    $meld = store_read('einkauf-meldungen') ?? [];
    $items = [];
    if ($hasStock) foreach ($need as $k => $e) {
        $avail = $stock[$k] ?? 0.0;
        $short = round($e['qty'] - $avail, 3);
        if ($short <= 0.0005) continue;
        $termine = array_filter(array_column($e['orders'], 'termin'));
        usort($e['orders'], function ($a, $b) { return strcmp($a['termin'] ?: '9999', $b['termin'] ?: '9999') ?: strcmp($a['t'], $b['t']); });
        $m = is_array($meld[$k] ?? null) ? $meld[$k] : null;
        $items[] = ['code' => $e['code'], 'name' => $e['name'] !== '' ? $e['name'] : ($stockName[$k] ?? ''), 'ordered' => round($e['qty'], 3), 'available' => round($avail, 3),
                    'short' => $short, 'termin' => $termine ? min($termine) : '', 'orders' => $e['orders'],
                    'gemeldet' => $m ? ['t' => (string)$m['t'], 'by' => (string)$m['by'], 'kg' => (float)$m['kg']] : null,
                    'neu' => !$m || $short > (float)$m['kg'] + 0.0005];
    }
    usort($items, function ($a, $b) { return strcmp($a['termin'] ?: '9999', $b['termin'] ?: '9999') ?: $b['short'] <=> $a['short']; });
    return ['stock' => $hasStock ? ['date' => $st['date'] ?? null, 'importedAt' => $st['importedAt'] ?? null, 'source' => (string)($st['source'] ?? '')] : null,
            'items' => $items, 'openOrders' => $offen, 'ohneNr' => $ohneNr, 'shortTotal' => round(array_sum(array_column($items, 'short')), 3)];
}

/* E-Mail an den Einkauf: [Betreff, Text, HTML] */
function einkauf_mail(array $items, array $stock, string $note, string $by): array
{
    global $CFG;
    $sum = array_sum(array_column($items, 'short'));
    $subject = "[{$CFG['company']}] Einkaufsbedarf: " . count($items) . ' Artikel, ' . de_qty($sum) . ' kg Fehlmenge';
    $stand = $stock['date'] ? date('d.m.Y', strtotime($stock['date'])) : ($stock['importedAt'] ? date('d.m.Y, H:i', strtotime($stock['importedAt'])) . ' Uhr' : 'unbekannt');
    $intro = "für folgende Artikel reicht der Bestand nicht für die offenen Bestellwünsche (Bestand vom {$stand}):";
    $t = "Hallo,\n\n{$intro}\n\n";
    $th = 'style="text-align:left;padding:6px 6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;"';
    $thr = 'style="text-align:right;padding:6px 6px;border-bottom:2px solid #e6e0d8;font-size:12px;color:#857c72;"';
    $h = '<p style="margin:0 0 14px;">Hallo,</p><p style="margin:0 0 14px;">' . mail_h($intro) . '</p>';
    if ($note !== '') { $t .= "Hinweis von {$by}:\n{$note}\n\n"; $h .= '<p style="margin:0 0 14px;padding:10px 12px;background:#f7efe9;border-radius:8px;"><strong>Hinweis von ' . mail_h($by) . ':</strong><br>' . nl2br(mail_h($note)) . '</p>'; }
    $h .= '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="font-size:13.5px;border-collapse:collapse;"><tr><th ' . $th . '>Art.-Nr.</th><th ' . $th . '>Artikel</th><th ' . $thr . '>Bestellt</th><th ' . $thr . '>Bestand</th><th ' . $thr . '>Fehlmenge</th><th ' . $thr . '>Termin</th></tr>';
    foreach ($items as $i => $it) {
        $termin = $it['termin'] ? date('d.m.Y', strtotime($it['termin'])) : 'offen';
        $refs = implode(', ', array_map(function ($o) { return $o['nr'] . (isset($o['firma']) && $o['firma'] !== '' ? " ({$o['firma']})" : '') . ': ' . de_qty($o['qty']) . ' kg'; }, $it['orders']));
        $t .= sprintf("%2d. %s %s – bestellt %s kg, Bestand %s kg, FEHLMENGE %s kg, frühester Termin %s\n    %s\n", $i + 1, $it['code'], $it['name'], de_qty($it['ordered']), de_qty($it['available']), de_qty($it['short']), $termin, $refs);
        $td = 'style="padding:6px 6px;border-bottom:1px solid #eee8e1;vertical-align:top;"'; $tdr = 'style="padding:6px 6px;border-bottom:1px solid #eee8e1;text-align:right;white-space:nowrap;vertical-align:top;"';
        $h .= '<tr><td ' . $td . '>' . mail_h($it['code']) . '</td><td ' . $td . '>' . mail_h($it['name']) . '<br><span style="font-size:11.5px;color:#857c72;">' . mail_h($refs) . '</span></td><td ' . $tdr . '>' . de_qty($it['ordered']) . ' kg</td><td ' . $tdr . '>' . de_qty($it['available']) . ' kg</td><td ' . $tdr . '><strong style="color:#7b1e2b;">' . de_qty($it['short']) . ' kg</strong></td><td ' . $tdr . '>' . mail_h($termin) . '</td></tr>';
    }
    $h .= '<tr><td colspan="4" style="padding:8px 6px;font-weight:bold;">Fehlmenge gesamt</td><td style="padding:8px 6px;text-align:right;font-weight:bold;white-space:nowrap;">' . de_qty($sum) . ' kg</td><td></td></tr></table>';
    $t .= "\nFehlmenge gesamt: " . de_qty($sum) . " kg\nGesendet von {$by} über das Angebotsportal.\n";
    $base = mail_base_url();
    $ziel = alter_zugang_aus() ? eingabe_adresse() : ($base ? $base . '/admin/' : '');   // alter Zugang stillgelegt: neuer Eingabebereich
    if ($ziel) { $t .= "Bereich Einkauf: {$ziel}\n"; $h .= '<p style="margin:16px 0 0;"><a href="' . mail_h($ziel) . '" style="color:#7b1e2b;">Bereich Einkauf öffnen</a></p>'; }
    $foot = "Gesendet von {$by} über das Angebotsportal. Empfänger: Verwaltung → E-Mail → Benachrichtigungen.";
    return [$subject, $t, mail_layout($subject, $h, '', $foot)];
}
